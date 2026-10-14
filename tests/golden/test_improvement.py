"""A 의 자기 개선 loop. 생성 · 검증은 가짜 클라이언트로 돌린다. API 호출은 없다."""
import json
import re
from pathlib import Path

import pytest

from golden_pipeline import improvement, storage
from golden_pipeline.generation import generate, import_c
from golden_pipeline.improvement import PREVENTION_RULES, PREVENTION_VERSION, improve, thresholds
from golden_pipeline.plan import load_plan, make_plan
from golden_pipeline.validation import release, validate

PRICED = {"usd_per_million_input_tokens": 1.0, "usd_per_million_output_tokens": 4.0}
LOOP = {
    "max_rounds": 3, "max_calls": 50, "budget_usd": 1.0,
    "generator": {"model": "generator-test", "reasoning_effort": "low", **PRICED},
    "validator": {"model": "validator-test", "reasoning_effort": "high", **PRICED},
}
BUDGET = {"question": "사업 예산은 얼마인가?", "answer": "130,000,000원(부가세 포함)", "evidence": ["E1"],
          "structure": {"value": "130,000,000", "unit": "원"}, "secondary_tags": []}
# 같은 질문에 근거의 다른 값(계약 기간)을 답한 후보. 독립 답과 달라 거절된다.
WRONG = {**BUDGET, "answer": "12개월", "structure": {"value": "12", "unit": "개월"}}
BOND = {"question": "입찰 보증금은 입찰 금액의 몇 % 이상인가?", "answer": "입찰 금액의 5% 이상", "evidence": ["E2"],
        "structure": {"value": "5", "unit": "%"}, "secondary_tags": []}
VERDICTS = {
    ("E1",): {"answerable": True, "answer": "130,000,000원", "conditions": ["부가세 포함"], "conflict": False,
              "comparison": None},
    ("E2",): {"answerable": True, "answer": "입찰 금액의 5% 이상", "conditions": [], "conflict": False,
              "comparison": None},
}


class Generator:
    """예산 묶음은 answer_mismatch 예방 규칙을 받기 전엔 틀린 값을, 받은 뒤엔 맞는 값을 답한다.
    보증금 묶음은 늘 맞게 답하고, 표 묶음은 늘 JSON 이 아닌 글을 낸다 (고쳐지지 않는 실패)."""

    def __init__(self):
        self.requests = []

    def __call__(self, model, reasoning_effort, messages):
        self.requests.append(messages)
        system, context = messages[0]["content"], messages[1]["content"]
        if "130,000,000원" in context:
            text = json.dumps(BUDGET if PREVENTION_RULES["answer_mismatch"] in system else WRONG, ensure_ascii=False)
        elif "5%" in context:
            text = json.dumps(BOND, ensure_ascii=False)
        else:
            text = "표만으로는 질문을 만들 수 없습니다"
        return {"model": "generator-test", "text": text, "input_tokens": 10, "output_tokens": 10}


class Validator:
    """받은 근거 라벨 조합에 VERDICTS (와 덮어쓴 답)를 돌려준다. crash_on 번째 호출에서 끊긴다."""

    def __init__(self, crash_on=None, **overrides):
        self.calls = 0
        self.crash_on = crash_on
        self.verdicts = {**VERDICTS, **{(label,): {**VERDICTS[(label,)], **o} for label, o in overrides.items()}}

    def __call__(self, model, reasoning_effort, messages):
        self.calls += 1
        if self.calls == self.crash_on:
            raise ConnectionError("검증 도중 끊김")
        labels = tuple(unit["label"] for unit in json.loads(messages[1]["content"])["evidence"])
        return {"model": "validator-test", "text": json.dumps(self.verdicts[labels], ensure_ascii=False),
                "input_tokens": 10, "output_tokens": 10}


@pytest.fixture
def loop_config(evidence_run, tmp_path):
    """계획 p3: numeric 묶음 셋 (예산 · 보증금 · 표). 목표 개수도 3 이다."""
    make_plan("p3", "ev1", {"numeric": 3}, 2000, package=evidence_run)

    def write(**overrides):
        path = tmp_path / "loop.json"
        path.write_text(json.dumps({**LOOP, **overrides}), encoding="utf-8")
        return path
    return write


@pytest.fixture
def looped(loop_config):
    before = thresholds()
    report = improve("numeric", "p3", "l1", loop_config(), Generator(), Validator())
    return report, before


def run_dir(round_no):
    return storage.run_path("numeric", "A", f"l1-r{round_no}")


def read_jsonl(path):
    return [json.loads(line) for line in Path(path).read_text(encoding="utf-8").splitlines()]


def manifest(round_no):
    return json.loads((run_dir(round_no) / "manifest.json").read_text(encoding="utf-8"))["generation"]


def memory(round_no):
    return read_jsonl(storage.OUTPUTS / "goldens" / "numeric" / "failure_memory" / f"A_l1-r{round_no}.jsonl")


def test_a_failed_candidate_stays_and_its_revision_gets_a_new_id_with_the_parent(loop_config):
    # 다시 만든 후보가 원래 후보를 덮어쓰면 무엇이 왜 거절됐는지가 사라진다.
    generator, frozen = Generator(), {}

    def watching(model, reasoning_effort, messages):
        if "예방 규칙" in messages[0]["content"] and not frozen:
            frozen.update(storage.snapshot(run_dir(1)))
        return generator(model, reasoning_effort, messages)

    improve("numeric", "p3", "l1", loop_config(), watching, Validator())

    assert frozen and storage.snapshot(run_dir(1)) == frozen
    [failed] = [row for row in read_jsonl(run_dir(1) / "rejected.jsonl") if "candidate_id" in row]
    assert (failed["answer"], failed["state"]) == ("12개월", "rejected")
    [revised] = read_jsonl(run_dir(2) / "accepted.jsonl")
    assert revised["parent_candidate_id"] == failed["candidate_id"] != revised["candidate_id"]
    assert revised["answer"] == BUDGET["answer"]


def test_failure_memory_holds_code_evidence_rule_and_version_but_no_answer(looped):
    entries = memory(1)
    rejected = read_jsonl(run_dir(1) / "rejected.jsonl")
    assert [entry["failure_code"] for entry in entries] == ["output_format", "answer_mismatch"]
    for entry in entries:
        row = rejected[entry["evidence"]["line"] - 1]
        assert entry["evidence"] == {"run": "A/l1-r1", "line": entry["evidence"]["line"],
                                     "candidate_id": row.get("candidate_id"), "bundle_id": row["bundle_id"]}
        assert entry["prevention_rule"] == PREVENTION_RULES[entry["failure_code"]]
        assert entry["rule_version"] == PREVENTION_VERSION
    stored = json.dumps(entries, ensure_ascii=False)
    for text in ("12개월", "130,000,000", BUDGET["question"]):
        assert text not in stored


def test_next_round_gets_rules_for_the_topics_failure_codes_and_records_its_policy(loop_config):
    # 다른 주제의 실패 기록이 섞이면 주제와 무관한 규칙이 붙는다.
    other = storage.OUTPUTS / "goldens" / "table" / "failure_memory"
    other.mkdir(parents=True)
    (other / "A_t1.jsonl").write_text(json.dumps({"entry_id": "t1:1", "failure_code": "table_relation"}) + "\n",
                                      encoding="utf-8")
    generator = Generator()
    improve("numeric", "p3", "l1", loop_config(), generator, Validator())

    first, second = manifest(1), manifest(2)
    assert first["policy"]["failures"] == {} and "예방 규칙" not in generator.requests[0][0]["content"]
    entry_ids = {entry["failure_code"]: [entry["entry_id"]] for entry in memory(1)}
    assert second["policy"]["failures"] == entry_ids
    assert (second["policy"]["version"], second["policy"]["round"]) == (PREVENTION_VERSION, 2)
    system = generator.requests[3][0]["content"]
    assert PREVENTION_RULES["answer_mismatch"] in system and PREVENTION_RULES["output_format"] in system
    assert PREVENTION_RULES["table_relation"] not in system
    assert second["prompt_sha256"] == first["prompt_sha256"] == storage._sha256(storage.PROMPTS / "A" / "numeric.txt")
    assert second["policy"]["prevention_sha256"] != first["policy"]["prevention_sha256"]


def test_a_retried_bundle_is_told_its_own_failed_question_and_why_but_not_an_answer(loop_config):
    # 주제 전체 규칙만으로는 생성기가 이 묶음에서 무엇을 틀렸는지 모른다. 묶음마다 지난 질문과 실패 규칙을 붙인다.
    generator = Generator()
    improve("numeric", "p3", "l1", loop_config(), generator, Validator())

    budget, table = generator.requests[3][1]["content"], generator.requests[4][1]["content"]
    note = "\n\n이 근거 묶음에서 거절된 지난 시도\n"
    assert budget.endswith(f"{note}- 질문 {BUDGET['question']!r}: {PREVENTION_RULES['answer_mismatch']}")
    assert table.endswith(f"{note}- 출력 (항목이 되지 못함): {PREVENTION_RULES['output_format']}")
    assert note not in generator.requests[0][1]["content"]
    assert manifest(2)["policy"]["notes"][manifest(2)["bundle_ids"][0]] == budget[budget.index(note):]


@pytest.mark.parametrize("limits, reason, rounds", [
    ({}, "max_rounds", 3),
    ({"max_calls": 4}, "call_cap", 1),
    ({"budget_usd": 0.0001}, "budget", 1),
])
def test_rounds_stop_at_the_configured_bound_and_record_why(loop_config, limits, reason, rounds):
    report = improve("numeric", "p3", "l1", loop_config(**limits), Generator(), Validator())

    assert report["stop_reason"] == reason and len(report["rounds"]) == rounds
    assert report["calls"] <= {**LOOP, **limits}["max_calls"]
    saved = json.loads((storage.OUTPUTS / "goldens/numeric/loops/l1/report.json").read_text(encoding="utf-8"))
    assert saved == report


@pytest.mark.parametrize("change, changed", [
    ("config", ["config"]),
    ("plan", ["plan_id", "plan_sha256"]),
    ("validator_prompt", ["thresholds"]),
])
def test_resume_refuses_a_loop_whose_config_plan_or_criteria_changed(loop_config, evidence_run, change, changed):
    # 이어 돌면서 한도 · 계획 · 검증 기준이 바뀌면 한 loop 의 round 들이 서로 다른 조건으로 돌고 report 가 그것을 숨긴다.
    with pytest.raises(ConnectionError):
        improve("numeric", "p3", "l1", loop_config(), Generator(), Validator(crash_on=3))
    config, plan_id = loop_config(), "p3"
    if change == "config":
        config = loop_config(max_calls=99)
    elif change == "plan":
        make_plan("p1", "ev1", {"numeric": 1}, 2000, package=evidence_run)
        plan_id = "p1"
    else:
        prompt = storage.PROMPTS / "validator.txt"
        prompt.write_text(prompt.read_text(encoding="utf-8") + "\n바뀐 기준", encoding="utf-8")

    generator, validator = Generator(), Validator()
    with pytest.raises(ValueError, match=re.escape(f"시작할 때와 다릅니다: {changed}")):
        improve("numeric", plan_id, "l1", config, generator, validator)
    assert not generator.requests and not validator.calls


@pytest.mark.parametrize("collision, run_id, changed", [
    ("standalone_run_of_another_plan", "l1-r1", ["loop_id", "plan_id", "plan_sha256", "round", "start_sha256"]),
    ("standalone_run_after_an_interruption", "l1-r3", ["loop_id", "round", "start_sha256"]),
    ("recreated_loop_record", "l1-r1", ["start_sha256"]),
])
def test_a_loop_refuses_a_run_under_its_name_that_it_did_not_make(loop_config, evidence_run, tmp_path,
                                                                   collision, run_id, changed):
    # run 이름만 같다고 이어 쓰면 다른 계획이나 loop 밖에서 만든 run 이 이 loop 의 round 로 검증 · 보고된다.
    run = tmp_path / "run.json"
    run.write_text(json.dumps({**LOOP["generator"], "max_calls": 10, "budget_usd": 1.0}), encoding="utf-8")
    if collision == "standalone_run_of_another_plan":
        make_plan("p1", "ev1", {"numeric": 1}, 2000, package=evidence_run)
        generate("A", "numeric", "p1", "l1-r1", run, Generator())
    else:
        with pytest.raises(ConnectionError):
            improve("numeric", "p3", "l1", loop_config(), Generator(), Validator(crash_on=3))
        if collision == "standalone_run_after_an_interruption":
            generate("A", "numeric", "p3", "l1-r3", run, Generator())
        else:
            # 시작 기록을 지우고 다른 한도로 다시 만든다. 같은 바이트로 다시 만든 기록은 같은 loop 로 본다.
            (storage.OUTPUTS / "goldens/numeric/loops/l1/start.json").unlink()

    config = loop_config(max_calls=99) if collision == "recreated_loop_record" else loop_config()
    generator = Generator()
    with pytest.raises(ValueError, match=re.escape(f"{run_id} 은 loop l1 가 round {run_id[-1]} 에 만든 run 이 아닙니다: {changed}")):
        improve("numeric", "p3", "l1", config, generator, Validator())
    assert not generator.requests
    assert not (storage.OUTPUTS / "goldens/numeric/loops/l1/report.json").exists()


def test_calls_of_an_interrupted_validation_count_against_the_loop_limit(loop_config):
    # 끊긴 검증의 호출을 세지 않으면 이어 돌 때 한도를 처음부터 다시 받아 max_calls 를 넘는다.
    generator, interrupted = Generator(), Validator(crash_on=2)
    with pytest.raises(ConnectionError):
        improve("numeric", "p3", "l1", loop_config(max_calls=5), generator, interrupted)
    resumed = Validator()
    report = improve("numeric", "p3", "l1", loop_config(max_calls=5), generator, resumed)

    answered = len(generator.requests) + (interrupted.calls - 1) + resumed.calls
    assert (report["calls"], report["stop_reason"]) == (answered, "call_cap") and answered == 5
    # 호출마다 입력 10 · 출력 10 토큰, 단가 1 · 4 USD / 100만 토큰.
    assert report["cost_usd"] == pytest.approx(answered * 50 / 1_000_000)


def test_b_and_c_code_paths_never_read_failure_memory(looped, monkeypatch, tmp_path):
    # B 는 고정 프롬프트, C 는 사람이 웹에서 만든 결과다. 실패 기록이 섞이면 A 와의 비교가 무너진다.
    (storage.OUTPUTS / "goldens/numeric/failure_memory/A_marker.jsonl").write_text(
        '{"failure_code": "MEMORY-MARKER"}\n', encoding="utf-8")
    run = tmp_path / "run.json"
    run.write_text(json.dumps({**LOOP["generator"], "max_calls": 10, "budget_usd": 1.0}), encoding="utf-8")
    bundle_id = next(b["bundle_id"] for b in load_plan("p3")[0]["bundles"] if "130,000,000원" in b["context"])
    export, sidecar = tmp_path / "c.jsonl", tmp_path / "sidecar.json"
    export.write_text(json.dumps({**BUDGET, "bundle_id": bundle_id}, ensure_ascii=False) + "\n", encoding="utf-8")
    sidecar.write_text("{}", encoding="utf-8")
    with pytest.raises(ValueError, match="A 만"):
        generate("B", "numeric", "p3", "b0", run, Generator(), {"parents": {}, "prevention": "", "policy": {}})

    reads, real_open = [], Path.open

    def spy(path, mode="r", *args, **kwargs):
        if "r" in mode:
            reads.append(str(path))
        return real_open(path, mode, *args, **kwargs)

    def forbidden(*args, **kwargs):
        raise AssertionError("B · C 경로가 실패 기록 모듈을 불렀습니다")

    generator = Generator()
    with monkeypatch.context() as patch:
        patch.setattr(Path, "open", spy)
        for name in ("related_failures", "record_failures", "open_bundles", "_revision"):
            patch.setattr(improvement, name, forbidden)
        generate("B", "numeric", "p3", "b1", run, generator)
        validate("numeric", "B", "b1", run, Validator())
        import_c("numeric", "p3", "c1", [export], sidecar)
        validate("numeric", "C", "c1", run, Validator())
        release("numeric", "v-b", [("B", "b1")])

    assert reads and not [path for path in reads if "failure_memory" in path]
    assert "MEMORY-MARKER" not in json.dumps(generator.requests, ensure_ascii=False)


def test_a_topic_short_of_its_target_is_reported_with_thresholds_unchanged(looped):
    # 목표에 못 미쳤다고 기준을 낮추면 골든 데이터의 질이 목표 개수에 맞춰 떨어진다.
    report, before = looped

    assert (report["target"], report["auto_validated"], report["held"], report["shortfall"]) == (3, 2, 0, 1)
    assert report["thresholds"] == before == thresholds()
    for round_no in (1, 2, 3):
        record = json.loads((run_dir(round_no) / "validation.json").read_text(encoding="utf-8"))
        assert record["prompt_sha256"] == before["validator_prompt_sha256"]
        assert record["difficulty_rule"] == before["difficulty_rule"]
