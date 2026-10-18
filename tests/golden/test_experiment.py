"""비교 실험: 계획 고정, 실험 상태 분리, 실험 장부. 네트워크 호출은 없다."""
import json
import threading

import httpx
import openai
import pytest

from golden_pipeline import adoption, cli, comparison, experiment, generation, storage
from golden_pipeline.schema import TOPICS

REQUEST = httpx.Request("POST", "https://api.test/v1/chat/completions")
# 단가 1 · 4 USD / 100만 토큰, 호출마다 출력 최대 100 토큰.
BUDGET = {"ceiling_usd": 0.01, "max_output_tokens": 100, "prices": {"m": [1, 4]}}
MESSAGES = [{"role": "system", "content": "시"}, {"role": "user", "content": "ab"}]
# 입력 상한: 바이트 3 + 2 와 메시지마다 16. 출력 상한 100.
RESERVED = ((3 + 16 + 2 + 16) * 1 + 100 * 4) / 1_000_000


def write_pool(outputs, parts):
    """주제마다 묶음 id 와 그 몫을 정한 큰 계획. adoption.split 이 그 몫을 돌려주게 바꾼다."""
    bundles = [{"bundle_id": bundle_id, "topic": topic, "doc_sha": "d", "units": [], "context": "c"}
               for topic in TOPICS for bundle_id in parts[topic]]
    (outputs / "configs/topics").mkdir()
    for topic in TOPICS:
        (outputs / f"configs/topics/{topic}.json").write_text('{"requires": "r", "structure": {}}', encoding="utf-8")
    specs = {topic: storage._sha256(outputs / f"configs/topics/{topic}.json") for topic in TOPICS}
    pool = {"plan_id": "pool", "evidence_run": "ev", "v11_manifest_sha256": "v", "topic_specs": specs, "bundles": bundles}
    (outputs / "outputs/plans").mkdir(parents=True)
    (outputs / "outputs/plans/pool.json").write_text(json.dumps(pool), encoding="utf-8")
    (outputs / "outputs/evidence/ev").mkdir(parents=True)
    (outputs / "outputs/evidence/ev/manifest.json").write_text('{"pinned_sha256": {"manifest.json": "x"}}', encoding="utf-8")
    return {bundle_id: part for found in parts.values() for bundle_id, part in found.items()}


def test_freeze_takes_six_two_two_per_topic_in_plan_order_and_records_hashes(outputs, monkeypatch):
    # 몫마다 앞에서부터 고르므로 9 번째 train 묶음 같은 남는 묶음은 빠진다.
    order = ["train"] * 8 + ["validation"] * 3 + ["held_out"] * 3
    parts = {topic: {f"{topic}-{n}": part for n, part in enumerate(order)} for topic in TOPICS}
    split = write_pool(outputs, parts)
    monkeypatch.setattr(adoption, "split", split.get)

    record = json.loads(experiment.freeze("x1", "pool").read_text(encoding="utf-8"))

    frozen = json.loads((outputs / "outputs/plans/x1.json").read_text(encoding="utf-8"))
    numeric = [b["bundle_id"] for b in frozen["bundles"] if b["topic"] == "numeric"]
    assert numeric == [f"numeric-{n}" for n in (0, 1, 2, 3, 4, 5, 8, 9, 11, 12)]
    assert record["part_counts"]["false_premise"] == experiment.PARTS
    assert record["plan"]["sha256"] == storage._sha256(outputs / "outputs/plans/x1.json")
    assert record["pool_plan"]["plan_id"] == "pool" and record["source"]["pinned_sha256"] == {"manifest.json": "x"}


def test_freeze_refuses_a_topic_with_an_empty_part_and_writes_no_plan(outputs, monkeypatch):
    parts = {topic: {f"{topic}-{n}": "train" if n < 8 else "validation" for n in range(12)} for topic in TOPICS}
    monkeypatch.setattr(adoption, "split", write_pool(outputs, parts).get)

    with pytest.raises(ValueError, match="numeric 묶음이 모자랍니다"):
        experiment.freeze("x1", "pool")
    assert not (outputs / "outputs/plans/x1.json").exists()


def test_pro_packets_refuse_a_c_prompt_or_topic_spec_changed_after_freeze(outputs, monkeypatch):
    # 고정한 뒤 바뀐 프롬프트 · 주제 명세로 만든 Pro 프롬프트는 A · B 와 다른 실험 정의를 C 에 준다.
    order = ["train"] * 6 + ["validation"] * 2 + ["held_out"] * 2
    monkeypatch.setattr(adoption, "split", write_pool(outputs, {t: {f"{t}-{n}": p for n, p in enumerate(order)} for t in TOPICS}).get)
    c_prompt, spec = outputs / "prompts/C.txt", outputs / "configs/topics/numeric.json"
    c_prompt.write_text("$topic $requires $structure $count $bundles", encoding="utf-8")
    experiment.freeze("x1", "pool")

    for path, changed in ((c_prompt, "$topic $requires $structure $count\n$bundles"), (spec, '{"requires": "r2", "structure": {}}')):
        original = path.read_text(encoding="utf-8")
        path.write_text(changed, encoding="utf-8")
        with pytest.raises(ValueError, match="고정한 뒤 바뀌었습니다"):
            experiment.pro_packets("x1")
        path.write_text(original, encoding="utf-8")
    assert len(list(experiment.pro_packets("x1").glob("*.txt"))) == len(TOPICS)


def test_review_quality_is_unmeasured_unless_every_sampled_output_is_judged_exactly_once(outputs):
    # 빠진 행은 표본을 고르게 줄이지 않고, 겹친 행은 한 출력을 두 번 센다. 둘 다 판정이 다 된 것처럼 보이면 안 된다.
    storage.EXPERIMENT = "x1"
    folder = outputs / "outputs/experiments/x1/review"
    folder.mkdir(parents=True)
    entries = [{"review_id": review_id, "method": "A", "topic": "numeric", "stratum": "rejected"} for review_id in ("R01", "R02")]
    (folder / "key.json").write_text(json.dumps({"entries": entries}), encoding="utf-8")
    header = "review_id,evidence_support,answer_correct,topic_fit,useful,note"
    judged = {"R01": "R01,Y,Y,Y,Y,", "R02": "R02,N,Y,Y,Y,", "R03": "R03,Y,Y,Y,Y,", "R01 짧음": "R01,Y,Y", "R02 짧음": "R02,N,Y"}

    for rows in ([], ["R01"], ["R01", "R01", "R02"], ["R01", "R02", "R03"], ["R01 짧음", "R02 짧음"]):
        (folder / "judgments.csv").write_text("\n".join([header, *(judged[r] for r in rows)]) + "\n", encoding="utf-8-sig")
        assert comparison._human("x1")["measured"] is False, rows
    # 사람이 고치는 파일이라 열이 빠질 수 있다. 판정 열이나 review_id 열이 없거나 빈 파일이면 잴 수 없다.
    names = header.split(",")
    for dropped in range(5):
        lines = [[cell for i, cell in enumerate(line.split(",")) if i != dropped] for line in [header, judged["R01"], judged["R02"]]]
        (folder / "judgments.csv").write_text("\n".join(map(",".join, lines)) + "\n", encoding="utf-8-sig")
        assert comparison._human("x1")["measured"] is False, names[dropped]
    (folder / "judgments.csv").write_bytes(b"")
    assert comparison._human("x1")["measured"] is False
    # note 열은 아무도 읽지 않으므로 없어도 잰다.
    no_note = [line.rsplit(",", 1)[0] for line in [header, judged["R01"], judged["R02"]]]
    (folder / "judgments.csv").write_text("\n".join(no_note) + "\n", encoding="utf-8-sig")
    assert comparison._human("x1")["cells"]["A · all"] == {"numerator": 1, "denominator": 2, "value": 0.5}


def test_experiment_state_ignores_the_shared_catalog_owner_and_keeps_its_own(outputs, make_item):
    # 지난 run 이 다른 주제로 가진 근거 묶음이 실험의 run 을 막으면, 지난 상태가 방식 비교에 끼어든다.
    storage.write_run("numeric", "A", "r1", [make_item(candidate_id="n-1")])
    storage.EXPERIMENT = "x1"
    storage.write_run("table", "B", "b1", [make_item(candidate_id="t-1", primary_topic="table", secondary_tags=[],
                                                     method="B", run_id="b1")])

    assert [e["candidate_id"] for e in storage.read_catalog()] == ["t-1"]
    assert (outputs / "outputs/experiments/x1/goldens/table/runs/B/b1/candidates.jsonl").exists()
    storage.EXPERIMENT = None
    assert [e["candidate_id"] for e in storage.read_catalog()] == ["n-1"]


def response(input_tokens=10, output_tokens=10):
    return {"model": "m-2026", "text": "{}", "input_tokens": input_tokens, "output_tokens": output_tokens}


def open_ledger(outputs, budget=BUDGET):
    (outputs / "configs/experiments").mkdir(parents=True, exist_ok=True)
    (outputs / "configs/experiments/x1.json").write_text(json.dumps(budget), encoding="utf-8")
    storage.EXPERIMENT = "x1"
    return experiment.ledger("x1")


def test_ledger_refuses_a_call_whose_worst_case_would_pass_the_ceiling_before_sending(outputs):
    sent = []
    with open_ledger(outputs, {**BUDGET, "ceiling_usd": RESERVED + 30 / 1_000_000}) as book:
        call = book.guard(lambda *args: sent.append(args) or response())
        call("m", "low", MESSAGES)
        # 첫 호출은 10 · 10 토큰으로 정산되어 상한 아래지만, 둘째 호출의 최악 비용을 더하면 넘는다.
        with pytest.raises(generation.BudgetExceeded):
            call("m", "low", MESSAGES)

    assert len(sent) == 1 and sent[0][3] == 100
    assert experiment.usage("x1")["settled_usd"] == pytest.approx((10 + 40) / 1_000_000)


def test_ledger_counts_in_flight_reservations_of_concurrent_calls(outputs):
    # 함께 날아가는 호출이 서로의 잡아 둔 비용을 보지 못하면, 상한 바로 아래에서 여럿이 함께 넘는다.
    started, release = threading.Barrier(3, timeout=5), threading.Event()
    with open_ledger(outputs, {**BUDGET, "ceiling_usd": RESERVED * 2.5}) as book:
        def send(*args):
            started.wait()
            release.wait(5)
            return response()
        call = book.guard(send)
        threads = [threading.Thread(target=call, args=("m", "low", MESSAGES)) for _ in range(2)]
        for thread in threads:
            thread.start()
        started.wait()
        with pytest.raises(generation.BudgetExceeded):
            call("m", "low", MESSAGES)
        release.set()
        for thread in threads:
            thread.join()


def test_uncertain_failures_keep_their_reservation_and_rate_limits_release_it_across_resumptions(outputs, monkeypatch):
    monkeypatch.setattr(experiment.time, "sleep", lambda seconds: None)
    failures = iter([openai.APIConnectionError(request=REQUEST),
                     openai.RateLimitError("429", response=httpx.Response(429, request=REQUEST), body=None)])

    def send(*args):
        error = next(failures, None)
        if error:
            raise error
        return response()

    with open_ledger(outputs, {**BUDGET, "ceiling_usd": 1}) as book:
        book.guard(send)("m", "low", MESSAGES)

    # 연결 오류는 청구됐을 수 있어 잡아 둔 비용이 남고, 429 는 풀린다. 이어 연 장부도 같은 값을 읽는다.
    expected = RESERVED + (10 + 40) / 1_000_000
    with experiment.ledger("x1") as book:
        assert book.committed == pytest.approx(expected)
    summary = experiment.usage("x1")
    assert summary["events"] == {"reserve": 3, "uncertain": 1, "rate_limited": 1, "settled": 1}
    assert summary["committed_usd"] == pytest.approx(expected)


@pytest.mark.parametrize("change", [{"max_output_tokens": 0}, {"prices": {"m": [-1, 4]}}, {"ceiling_usd": 0},
                                    {"max_output_tokens": True}, {"prices": {}}])
def test_a_budget_that_cannot_bound_the_worst_case_is_refused_before_any_call(outputs, change):
    # 출력 상한 0 은 출력 비용을 잡지 않고 API 에 상한도 보내지 않으며, 음수 단가는 잡아 둔 비용을 줄여 상한을 푼다.
    with pytest.raises(ValueError, match="0 보다 큰 수"):
        with open_ledger(outputs, {**BUDGET, **change}):
            pass


def test_a_second_command_cannot_open_the_same_ledger(outputs):
    with open_ledger(outputs):
        with pytest.raises(FileExistsError):
            with experiment.ledger("x1"):
                pass
    with experiment.ledger("x1"):
        pass


def test_experiment_api_client_stops_before_opening_openai_without_an_approved_budget(outputs, monkeypatch):
    monkeypatch.setattr(cli.openai, "OpenAI", lambda **kwargs: pytest.fail("OpenAI 를 열면 안 됩니다"))
    monkeypatch.setattr(cli, "load_dotenv", lambda path: None)
    storage.EXPERIMENT = "x1"

    with pytest.raises(ValueError, match="승인된 실험 예산이 없어"):
        with cli.api_client():
            pass
