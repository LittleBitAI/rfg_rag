"""A 의 자기 개선 loop. 생성 · 검증은 가짜 클라이언트로 돌린다. API 호출은 없다."""
import json
import re
from pathlib import Path

import pytest

from golden_pipeline import improvement, storage
from golden_pipeline.generation import generate, import_c
from golden_pipeline.improvement import (
    PREVENTION_RULES, PREVENTION_VERSION, FailureMemoryError, improve, thresholds, write_memory,
)
from golden_pipeline.plan import load_plan, make_plan
from golden_pipeline.validation import release, validate

PRICED = {"usd_per_million_input_tokens": 1.0, "usd_per_million_output_tokens": 4.0}
LOOP = {
    "max_rounds": 3, "max_calls": 50, "budget_usd": 1.0,
    "generator": {"model": "generator-test", **PRICED}, "validator": {"model": "validator-test", **PRICED},
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

    def __call__(self, model, messages):
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

    def __call__(self, model, messages):
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

    def watching(model, messages):
        if "예방 규칙" in messages[0]["content"] and not frozen:
            frozen.update(storage.snapshot(run_dir(1)))
        return generator(model, messages)

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


def test_an_unverified_corrected_answer_cannot_be_written_as_a_fact(looped):
    # 고친 답을 검증 없이 실패 기록에 넣으면 다음 round 프롬프트에 사실처럼 들어가 후보를 오염시킨다.
    entry = memory(1)[1]
    corrected = [
        {**entry, "corrected_answer": "130,000,000원(부가세 포함)"},
        {**entry, "prevention_rule": "사업 예산의 정답은 130,000,000원(부가세 포함)이다."},
        {**entry, "rule_version": "prevention-0"},
    ]
    for bad in corrected:
        with pytest.raises(FailureMemoryError):
            write_memory("numeric", "l1-r1", [bad])


def test_memory_takes_only_the_failure_code_its_rejected_row_gives(looped):
    # 규칙이 없는 코드가 기록되면 다음 loop 가 그 규칙을 찾다 멈추고, 다른 코드는 그 줄과 무관한 규칙을 가르친다.
    entry = memory(1)[1]
    assert entry["failure_code"] == "answer_mismatch"
    for code, rule in (("unknown", None), ("output_format", PREVENTION_RULES["output_format"])):
        with pytest.raises(FailureMemoryError):
            write_memory("numeric", "l1-r1", [{**entry, "failure_code": code, "prevention_rule": rule}])


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


def test_resume_continues_after_the_last_completed_round_without_duplicate_ids(loop_config):
    # round 2 의 검증 도중 끊긴다 (round 1 검증 두 번, round 2 첫 검증 호출).
    generator = Generator()
    with pytest.raises(ConnectionError):
        improve("numeric", "p3", "l1", loop_config(), generator, Validator(crash_on=3))
    assert len(generator.requests) == 5

    report = improve("numeric", "p3", "l1", loop_config(), generator, Validator())

    # 끝난 round 1 과 생성까지 끝난 round 2 는 다시 부르지 않는다: 3 + 2 + 1 번.
    assert len(generator.requests) == 6
    assert [r["run_id"] for r in report["rounds"]] == ["l1-r1", "l1-r2", "l1-r3"]
    ids = [entry["candidate_id"] for entry in storage.read_catalog()]
    assert len(ids) == len(set(ids)) == 3
    with pytest.raises(FileExistsError):
        improve("numeric", "p3", "l1", loop_config(), generator, Validator())


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
        for name in ("related_failures", "record_failures", "write_memory", "open_bundles", "_revision"):
            patch.setattr(improvement, name, forbidden)
        generate("B", "numeric", "p3", "b1", run, generator)
        validate("numeric", "B", "b1", run, Validator())
        import_c("numeric", "p3", "c1", [export], sidecar)
        validate("numeric", "C", "c1", run, Validator())
        release("numeric", "v-b", [("B", "b1")])

    assert reads and not [path for path in reads if "failure_memory" in path]
    assert "MEMORY-MARKER" not in json.dumps(generator.requests, ensure_ascii=False)


def test_questions_answers_and_feedback_of_released_items_are_blocked_from_failure_memory(loop_config, tmp_path):
    # 출시본은 평가 정답이다. 그 질문 · 답 · 사람 확인 이유가 실패 기록에 들어가면 다음 생성으로 정답이 샌다.
    run = tmp_path / "run.json"
    run.write_text(json.dumps({**LOOP["generator"], "max_calls": 10, "budget_usd": 1.0}), encoding="utf-8")
    learned = [{"role": "system", "content": PREVENTION_RULES["answer_mismatch"]}]
    generate("A", "numeric", "p3", "a1", run, lambda model, messages: Generator()(model, learned + messages[1:]))
    # 예산 후보는 근거 충돌로 held 가 되고, 사람이 확인해 출시한다.
    validate("numeric", "A", "a1", run, Validator(E1={"conflict": True}))
    [held] = read_jsonl(storage.run_path("numeric", "A", "a1") / "review.jsonl")
    confirmations = tmp_path / "confirm.jsonl"
    confirmations.write_text(json.dumps({"candidate_id": held["candidate_id"], "reason": "원문 표와 대조해 확인함"},
                                        ensure_ascii=False) + "\n", encoding="utf-8")
    release("numeric", "v1", [("A", "a1")], confirmations)
    bond = next(item for item in read_jsonl(storage.OUTPUTS / "goldens/numeric/releases/v1/golden.jsonl")
                if item["candidate_id"] != held["candidate_id"])

    # a1 의 거절은 JSON 이 아닌 표 묶음 출력 한 줄뿐이다.
    [table] = read_jsonl(storage.run_path("numeric", "A", "a1") / "rejected.jsonl")
    rule = PREVENTION_RULES["output_format"]
    entry = {"entry_id": "a1:1", "failure_code": "output_format", "prevention_rule": rule,
             "rule_version": PREVENTION_VERSION,
             "evidence": {"run": "A/a1", "line": 1, "candidate_id": None, "bundle_id": table["bundle_id"]}}
    leaks = [
        {**entry, "prevention_rule": f"{rule} 예: {held['question']}"},
        {**entry, "prevention_rule": f"{rule} 예: {bond['answer']}"},
        {**entry, "prevention_rule": f"{rule} 사람 확인: 원문 표와 대조해 확인함"},
        {**entry, "entry_id": f"a1:1 {bond['answer']}"},
        {**entry, "evidence": {**entry["evidence"], "candidate_id": held["candidate_id"]}},
        {**entry, "evidence": {**entry["evidence"], "bundle_id": held["question"]}},
    ]
    for leak in leaks:
        with pytest.raises(FailureMemoryError):
            write_memory("numeric", "a1", [leak])
    assert write_memory("numeric", "a1", [entry]).exists()


def test_a_fixed_rule_is_recorded_even_when_a_released_answer_appears_in_its_text(loop_config):
    # 출시본 표 답 JSON 은 output_format 규칙 글에 들어 있다. 출시본 글을 부분 문자열로 막으면 정해 둔 규칙까지 막혀 loop 가 멈춘다.
    released = storage.OUTPUTS / "goldens/table/releases/v1"
    released.mkdir(parents=True)
    (released / "golden.jsonl").write_text(json.dumps(
        {"candidate_id": "table-A-t1-0001", "question": "산출물 형식은?", "answer": "JSON", "state_history": []},
        ensure_ascii=False) + "\n", encoding="utf-8")

    improve("numeric", "p3", "l1", loop_config(), Generator(), Validator())

    assert [entry["failure_code"] for entry in memory(1)] == ["output_format", "answer_mismatch"]


def test_a_topic_short_of_its_target_is_reported_with_thresholds_unchanged(looped):
    # 목표에 못 미쳤다고 기준을 낮추면 골든 데이터의 질이 목표 개수에 맞춰 떨어진다.
    report, before = looped

    assert (report["target"], report["auto_validated"], report["held"], report["shortfall"]) == (3, 2, 0, 1)
    assert report["thresholds"] == before == thresholds()
    for round_no in (1, 2, 3):
        record = json.loads((run_dir(round_no) / "validation.json").read_text(encoding="utf-8"))
        assert record["prompt_sha256"] == before["validator_prompt_sha256"]
        assert record["difficulty_rule"] == before["difficulty_rule"]
