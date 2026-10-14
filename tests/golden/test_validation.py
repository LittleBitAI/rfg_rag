"""독립 검증 · 난도 · 출시. 생성은 가짜 생성기로, 검증은 가짜 검증기로 돌린다. API 호출은 없다."""
import json

import pytest

from golden_pipeline import storage
from golden_pipeline.generation import comparison_answer, generate, import_c
from golden_pipeline.plan import load_plan, make_plan
from golden_pipeline.schema import DIFFICULTIES
from golden_pipeline.validation import VALIDATOR_VERSION, difficulty, quantities, release, same_answer, validate

CONFIG = {
    "model": "validator-test", "max_calls": 20, "budget_usd": 1.0,
    "usd_per_million_input_tokens": 1.0, "usd_per_million_output_tokens": 4.0,
}
NUMERIC = {
    "question": "사업 예산은 얼마인가?", "answer": "130,000,000원(부가세 포함)", "evidence": ["E1"],
    "structure": {"value": "130,000,000", "unit": "원"}, "secondary_tags": [],
}
MULTI_HOP = {
    "question": "계약 기간과 하자 보수 기간을 이으면 계약 시작부터 최대 몇 년인가?", "answer": "2년",
    "evidence": ["E1", "E2"], "structure": {}, "secondary_tags": [],
}


def verdict(answer, conditions=(), answerable=True, conflict=False, comparison=None):
    return {"answerable": answerable, "answer": answer, "conditions": list(conditions), "conflict": conflict,
            "comparison": comparison}


class Generator:
    """정해 둔 출력 행을 차례로 돌려주는 생성기 대역."""

    def __init__(self, *rows):
        self.rows = list(rows)

    def __call__(self, model, messages):
        text = json.dumps(self.rows.pop(0), ensure_ascii=False)
        return {"model": "generator-test", "text": text, "input_tokens": 10, "output_tokens": 10}


class Validator:
    """검증기 대역. 받은 메시지를 기록하고, 받은 근거 라벨 조합에 정해 둔 답을 돌려준다 ('*' 는 그 밖의 조합)."""

    def __init__(self, verdicts):
        self.verdicts = verdicts
        self.requests = []

    def __call__(self, model, messages):
        self.requests.append(messages)
        reply = self.verdicts.get(self.labels(messages), self.verdicts.get("*"))
        return {"model": "validator-test", "text": json.dumps(reply, ensure_ascii=False),
                "input_tokens": 10, "output_tokens": 10}

    @staticmethod
    def labels(messages):
        return tuple(unit["label"] for unit in json.loads(messages[1]["content"])["evidence"])


@pytest.fixture
def config(evidence_run, tmp_path):
    """p1 은 numeric · table · condition 묶음이 하나씩, p2 는 multi_hop 묶음 하나 (E1 · E2 · E3 = u1 · u2 · u3)."""
    make_plan("p1", "ev1", {"numeric": 1, "table": 1, "condition": 1}, 2000, package=evidence_run)
    make_plan("p2", "ev1", {"multi_hop": 1}, 2000, package=evidence_run)
    path = tmp_path / "validator.json"
    path.write_text(json.dumps(CONFIG), encoding="utf-8")
    return path


def bundle(plan_id, topic):
    return next(b for b in load_plan(plan_id)[0]["bundles"] if b["topic"] == topic)


def import_rows(tmp_path, topic, rows, run_id="c1"):
    export = tmp_path / f"{run_id}.jsonl"
    bundle_id = bundle("p1", topic)["bundle_id"]
    export.write_text("".join(json.dumps({**row, "bundle_id": bundle_id}, ensure_ascii=False) + "\n" for row in rows),
                      encoding="utf-8")
    sidecar = tmp_path / "sidecar.json"
    sidecar.write_text("{}", encoding="utf-8")
    return import_c(topic, "p1", run_id, [export], sidecar)


def read_jsonl(path):
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]


def validated(run_dir):
    """검증한 항목 전부 (rejected.jsonl 의 생성 거절 행은 뺀다)."""
    rows = [row for name in ("accepted.jsonl", "review.jsonl", "rejected.jsonl") for row in read_jsonl(run_dir / name)]
    return {row["candidate_id"]: row for row in rows if "candidate_id" in row}


def test_validator_sees_only_the_question_and_the_cited_evidence_units(config):
    # 생성기의 답 · 근거 해설 · 자기 평가가 검증기 입력에 섞이면 독립 답과의 비교가 의미를 잃는다.
    row = {**NUMERIC, "answer": "130,000,000원(부가세 포함). 생성기 자기 평가: 확실함, 근거 해설: E1 첫 문장"}
    generate("A", "numeric", "p1", "a1", config, Generator(row))
    validator = Validator({"*": verdict("130,000,000원", ["부가세 포함"])})

    validate("numeric", "A", "a1", config, validator)

    numeric = bundle("p1", "numeric")
    question_and_units = {"question": row["question"], "evidence": [{"label": "E1", "text": numeric["units"][0]["text"]}]}
    assert validator.requests == [[
        {"role": "system", "content": (storage.PROMPTS / "validator.txt").read_text(encoding="utf-8")},
        {"role": "user", "content": json.dumps(question_and_units, ensure_ascii=False)},
    ]]
    sent = json.dumps(validator.requests, ensure_ascii=False)
    for generator_side in ("자기 평가", "근거 해설", numeric["context"], (storage.PROMPTS / "A" / "numeric.txt").read_text(
            encoding="utf-8").splitlines()[0]):
        assert generator_side not in sent


@pytest.mark.parametrize("text, expected", [
    ("130,000,000원", {("130000000", "원")}),
    ("1억 3천만원", {("130000000", "원")}),
    ("1억3천만원(부가세 포함)", {("130000000", "원")}),
    ("5만원 이상", {("50000", "원")}),
    ("- 2억원", {("-200000000", "원")}),
    ("1.50%", {("1.5", "%")}),
    ("12개월간", {("12", "개월간")}),
    ("10~12개월", set()),
])
def test_quantities_normalize_value_and_unit(text, expected):
    assert quantities(text) == expected


@pytest.mark.parametrize("candidate, independent, same", [
    ("총 사업비 130,000,000원(부가세 포함)", "1억 3천만원", True),
    ("5만원", "50,000원", True),
    ("130,000,000원", "13,000,000원", False),
    ("계약 기간 12개월", "12개", False),
    ("5%p 인상", "5%", False),
    ("단, 우편 접수는 받지 않는다", "우편 접수는 받지 않는다", True),
    ("우편 접수도 받는다", "우편 접수는 받지 않는다", False),
    ("A안은 1억원, B안은 2억원", "A안 2억원, B안 1억원", False),
    ("B안 예산은 1억원이고 A안 예산은 2억원이다", "A안 2억원, B안 1억원", True),
    ("1차년도 2억원, 2차년도 1억원", "1차년도 1억원, 2차년도 2억원", False),
    ("C안은 2억원, D안은 1억원", "A안 2억원, B안 1억원", None),
    ("2억원, 1억원", "A안 2억원, B안 1억원", None),
])
def test_same_answer_compares_after_value_and_unit_normalization(candidate, independent, same):
    assert same_answer(candidate, independent) is same


@pytest.mark.parametrize("independent, state", [
    ("1억 3천만원", "auto_validated"),
    ("13,000,000원", "rejected"),
])
def test_independent_answer_mismatch_rejects_the_candidate(config, independent, state):
    generate("A", "numeric", "p1", "a1", config, Generator(NUMERIC))

    run_dir = validate("numeric", "A", "a1", config, Validator({"*": verdict(independent, ["부가세 포함"])}))

    [item] = validated(run_dir).values()
    assert item["state"] == state
    if state == "rejected":
        assert item["state_history"][-1]["reason"].startswith("독립 답과 다릅니다")


def test_a_plan_changed_after_generation_stops_validation_before_any_call(config):
    # 생성 뒤 계획의 근거 본문이 바뀌면 검증기는 후보가 보지 않은 근거로 답한다.
    generate("A", "numeric", "p1", "a1", config, Generator({**NUMERIC, "answer": "130,000,000원(부가세 별도)"}))
    path = storage.OUTPUTS / "plans" / "p1.json"
    path.write_text(path.read_text(encoding="utf-8").replace("부가세 포함", "부가세 별도"), encoding="utf-8")
    validator = Validator({"*": verdict("130,000,000원", ["부가세 별도"])})

    with pytest.raises(ValueError, match="바뀌었습니다"):
        validate("numeric", "A", "a1", config, validator)
    assert validator.requests == []


CONDITION = {"question": "제안서 제출 기한과 접수 제한은?", "evidence": ["E1"], "secondary_tags": [],
             "answer": "11월 3일까지 제출하며, 우편 접수는 받지 않는다", "structure": {"condition": "우편 접수는 받지 않는다"}}
TABLE = {"question": "A안의 예산은?", "answer": "1억원", "evidence": ["E1", "E2"],
         "structure": {"row": "예산", "column": "A안"}, "secondary_tags": []}


@pytest.mark.parametrize("topic, row, verdicts, state, reason", [
    pytest.param("numeric", NUMERIC, {"*": verdict("130,000,000원", ["부가세 포함"])}, "auto_validated", "자동 검증 통과",
                 id="numeric-passes"),
    pytest.param("condition", CONDITION, {"*": verdict("11월 3일까지", ["우편 접수는 받지 않는다"])}, "auto_validated",
                 "자동 검증 통과", id="condition-passes"),
    pytest.param("table", TABLE, {"*": verdict("1억원")}, "auto_validated", "자동 검증 통과", id="table-passes"),
    pytest.param("numeric", {**NUMERIC, "question": "사업 예산 130,000,000원은 부가세를 포함하는가?"},
                 {"*": verdict("130,000,000원", ["부가세 포함"])}, "rejected", "복사형", id="copy-style"),
    pytest.param("numeric", NUMERIC, {"*": verdict("부가세를 포함한 금액")}, "rejected", "유형 불일치",
                 id="topic-mismatch"),
    pytest.param("condition", {**CONDITION, "question": "입찰 보증금은 얼마 이상인가?", "evidence": ["E2"],
                               "answer": "입찰 금액의 5%p 이상", "structure": {"condition": "이상"}},
                 {"*": verdict("입찰 금액의 5% 이상", ["이상"])}, "rejected", "독립 답과 다릅니다", id="wrong-unit"),
    pytest.param("condition", {**CONDITION, "answer": "11월 3일까지 제출한다"},
                 {"*": verdict("11월 3일까지", ["우편 접수는 받지 않는다"])}, "rejected", "조건 · 예외 누락",
                 id="missing-condition"),
    pytest.param("numeric", {**NUMERIC, "answer": "130,000,000원"}, {"*": verdict("130,000,000원", ["부가세 포함"])},
                 "rejected", "조건 · 예외 누락", id="missing-exception"),
    pytest.param("table", {**TABLE, "answer": "2억원"}, {"*": verdict("1억원")}, "rejected", "표 관계",
                 id="table-wrong-cell"),
    pytest.param("numeric", NUMERIC, {"*": verdict("130,000,000원", conflict=True)}, "held", "근거 충돌",
                 id="evidence-conflict"),
    pytest.param("numeric", NUMERIC, {"*": "검증기 출력이 깨졌습니다"}, "held", "검증기 출력 오류",
                 id="broken-validator-output"),
    pytest.param("numeric", {**NUMERIC, "answer": "130,000,000원, 2억원(부가세 포함)"},
                 {"*": verdict("사업 예산 130,000,000원, 예비비 2억원")}, "held", "대상 확인 불가",
                 id="unattributed-values"),
])
def test_each_check_sends_the_candidate_to_its_state(config, topic, row, verdicts, state, reason):
    generate("A", topic, "p1", "a1", config, Generator(row))

    run_dir = validate(topic, "A", "a1", config, Validator(verdicts))

    [item] = validated(run_dir).values()
    assert (item["state"], item["state_history"][-1]["reason"][:len(reason)]) == (state, reason)
    file = {"auto_validated": "accepted.jsonl", "held": "review.jsonl", "rejected": "rejected.jsonl"}[state]
    assert item in read_jsonl(run_dir / file)
    assert item["validator_version"] == VALIDATOR_VERSION and item["difficulty"] in DIFFICULTIES
    record = json.loads((run_dir / "validation.json").read_text(encoding="utf-8"))
    assert record["validator_version"] == VALIDATOR_VERSION and record["difficulty_rule"].startswith("difficulty-1")


BUDGETS = {"A안": "1억원", "B안": "2억원"}


@pytest.mark.parametrize("values, choice, independent, state", [
    (BUDGETS, "B안", {"values": {"A안": "100,000,000원", "B안": "2억원"}, "choice": "B안"}, "auto_validated"),
    (BUDGETS, "A안", {"values": BUDGETS, "choice": "B안"}, "rejected"),
    ({"A안": "2억원", "B안": "1억원"}, "B안", {"values": BUDGETS, "choice": "B안"}, "rejected"),
    (BUDGETS, "B안", None, "held"),
    (BUDGETS, "B안", {"values": {"A안": "1억원", "C안": "2억원"}, "choice": "B안"}, "held"),
])
def test_comparison_compares_each_entity_value_and_the_chosen_entity_with_the_validator(config, values, choice,
                                                                                        independent, state):
    # 비교 답의 결론(어느 대상을 골랐는지)은 글에서 읽을 수 없다. 후보 structure 와 검증기 comparison 을 필드로 맞춘다.
    make_plan("p3", "ev1", {"numeric": 1, "comparison": 1}, 2000, package=config.parent / "v11")
    structure = {"entities": ["A안", "B안"], "values": values, "choice": choice}
    row = {"question": "A안과 B안 중 예산이 더 많은 안은?", "answer": comparison_answer(structure),
           "evidence": ["E1", "E2"], "structure": structure, "secondary_tags": []}
    generate("A", "comparison", "p3", "a1", config, Generator(row))

    run_dir = validate("comparison", "A", "a1", config, Validator({"*": verdict("B안", comparison=independent)}))

    [item] = validated(run_dir).values()
    assert item["state"] == state


@pytest.mark.parametrize("e2_alone, state, reason", [
    (verdict("1년", ["이내"]), "auto_validated", "자동 검증 통과"),
    (verdict("2년"), "rejected", "multi_hop 아님: 근거 E2 하나로 답이 나옵니다"),
])
def test_multi_hop_is_approved_only_if_no_single_unit_yields_the_answer(config, e2_alone, state, reason):
    generate("A", "multi_hop", "p2", "a1", config, Generator(MULTI_HOP))
    validator = Validator({("E1", "E2"): verdict("2년"), ("E1",): verdict("", answerable=False), ("E2",): e2_alone})

    run_dir = validate("multi_hop", "A", "a1", config, validator)

    assert [Validator.labels(messages) for messages in validator.requests] == [("E1", "E2"), ("E1",), ("E2",)]
    [item] = validated(run_dir).values()
    assert (item["state"], item["state_history"][-1]["reason"][:len(reason)]) == (state, reason)
    assert item["difficulty"] == ("hard" if state == "auto_validated" else "medium")


def test_duplicates_and_items_from_the_same_evidence_group_are_rejected_through_the_catalog(config, tmp_path):
    validator = Validator({"*": verdict("130,000,000원", ["부가세 포함"])})
    rows = [
        NUMERIC,
        {**NUMERIC, "question": "사업비는 얼마로 잡혀 있나?"},
        {**NUMERIC, "question": " 사업 예산은  얼마인가? ", "evidence": ["E1", "E2"]},
    ]
    import_rows(tmp_path, "numeric", rows)
    c1 = validated(validate("numeric", "C", "c1", config, validator))
    assert [(item["state"], item["state_history"][-1]["reason"]) for item in c1.values()] == [
        ("auto_validated", "자동 검증 통과"),
        ("rejected", "중복: numeric-C-c1-0001 와 같은 근거 묶음이나 질문입니다"),
        ("rejected", "중복: numeric-C-c1-0001 와 같은 근거 묶음이나 질문입니다"),
    ]

    # 다른 방식은 같은 계획의 같은 근거 묶음을 받는 것이 비교의 전제라 중복이 아니다.
    generate("A", "numeric", "p1", "a1", config, Generator(NUMERIC))
    [a1] = validated(validate("numeric", "A", "a1", config, validator)).values()
    assert a1["state"] == "auto_validated"
    # 같은 방식의 다른 run 은 카탈로그로 찾아 중복으로 거절한다.
    generate("A", "numeric", "p1", "a2", config, Generator(NUMERIC))
    [a2] = validated(validate("numeric", "A", "a2", config, validator)).values()
    assert a2["state_history"][-1]["reason"] == "중복: numeric-A-a1-0001 와 같은 근거 묶음이나 질문입니다"
    # 방식을 섞어 낸 출시본에도 같은 근거 묶음의 항목이 둘 들어가지 않는다.
    with pytest.raises(ValueError, match="같은 근거 묶음"):
        release("numeric", "v1", [("A", "a1"), ("C", "c1")])


@pytest.mark.parametrize("question, proven, level", [
    ("사업 예산은 얼마인가?", False, "easy"),
    ("총 사업비는 얼마인가?", False, "medium"),
    ("사업 예산은 얼마인가?", True, "hard"),
])
def test_difficulty_follows_the_recorded_rule(question, proven, level):
    units = [{"text": "사업 예산은 130,000,000원(부가세 포함)이며 계약 기간은 12개월이다."}]
    assert difficulty(question, units, proven) == level


@pytest.fixture
def reviewed(config, tmp_path):
    """c1: 0001 은 auto_validated, 0002 · 0003 은 근거 충돌로 held. 사람이 0002 만 확인한 기록 파일."""
    rows = [
        NUMERIC,
        {**NUMERIC, "question": "사업 예산의 부가세 포함 여부는?", "evidence": ["E1", "E2"]},
        {"question": "하자 보수 기간은?", "answer": "1년 이내", "evidence": ["E2"],
         "structure": {"value": "1", "unit": "년"}, "secondary_tags": []},
    ]
    import_rows(tmp_path, "numeric", rows)
    validator = Validator({("E1",): verdict("130,000,000원", ["부가세 포함"]), "*": verdict("1년", conflict=True)})
    run_dir = validate("numeric", "C", "c1", config, validator)
    confirmations = tmp_path / "confirmed.jsonl"
    confirmations.write_text(json.dumps({"candidate_id": "numeric-C-c1-0002", "reason": "원문 대조: 두 근거는 다른 사실"},
                                        ensure_ascii=False) + "\n", encoding="utf-8")
    return run_dir, confirmations


def test_release_collects_accepted_and_person_confirmed_items_and_refuses_an_existing_version(reviewed):
    run_dir, confirmations = reviewed
    assert [item["candidate_id"] for item in read_jsonl(run_dir / "review.jsonl")] == [
        "numeric-C-c1-0002", "numeric-C-c1-0003",
    ]

    release_dir = release("numeric", "v1", [("C", "c1")], confirmations)

    golden = read_jsonl(release_dir / "golden.jsonl")
    assert [(item["candidate_id"], item["state_history"][-1]["reason"]) for item in golden] == [
        ("numeric-C-c1-0001", "자동 검증 통과"),
        ("numeric-C-c1-0002", "사람 확인: 원문 대조: 두 근거는 다른 사실"),
    ]
    manifest = json.loads((release_dir / "manifest.json").read_text(encoding="utf-8"))
    assert manifest["runs"] == ["C/c1"]
    for name in ("candidates.jsonl", "accepted.jsonl", "review.jsonl", "manifest.json", "validation.json"):
        assert manifest["sources"]["C/c1"][name] == storage._sha256(run_dir / name)
    assert manifest["release"]["confirmations"] == {"file": "confirmed.jsonl", "sha256": storage._sha256(confirmations)}
    before = (release_dir / "golden.jsonl").read_bytes()

    with pytest.raises(FileExistsError):
        release("numeric", "v1", [("C", "c1")])
    assert (release_dir / "golden.jsonl").read_bytes() == before


def test_release_refuses_a_confirmation_of_a_non_held_item_and_files_changed_after_validation(reviewed, tmp_path):
    run_dir, _ = reviewed
    accepted_id = tmp_path / "wrong.jsonl"
    accepted_id.write_text('{"candidate_id": "numeric-C-c1-0001", "reason": "확인"}\n', encoding="utf-8")
    with pytest.raises(ValueError, match="보류"):
        release("numeric", "v1", [("C", "c1")], accepted_id)

    # 보류 항목을 accepted.jsonl 로 옮겨 사람 확인을 건너뛰지 못하게 한다.
    review = run_dir / "review.jsonl"
    with (run_dir / "accepted.jsonl").open("a", encoding="utf-8") as f:
        f.write(review.read_text(encoding="utf-8"))
    with pytest.raises(storage.CatalogError, match="validation.json"):
        release("numeric", "v1", [("C", "c1")])
    assert not (storage.OUTPUTS / "goldens" / "numeric" / "releases").exists()


def test_run_is_validated_once_and_the_call_cap_leaves_candidates_pending(config, tmp_path):
    generate("A", "multi_hop", "p2", "a1", config, Generator(MULTI_HOP))
    capped = tmp_path / "capped.json"
    capped.write_text(json.dumps({**CONFIG, "max_calls": 2}), encoding="utf-8")
    validator = Validator({"*": verdict("2년")})

    # multi_hop 후보 하나는 호출 셋(전체 · E1 · E2)이 필요하다. 한 후보를 도중에 끊지 않고 남긴다.
    run_dir = validate("multi_hop", "A", "a1", capped, validator)

    record = json.loads((run_dir / "validation.json").read_text(encoding="utf-8"))
    assert (record["status"], record["pending"], record["calls"]) == ("call_cap", ["multi_hop-A-a1-0001"], [])
    assert validated(run_dir) == {}
    with pytest.raises(FileExistsError, match="이미 검증한"):
        validate("multi_hop", "A", "a1", config, validator)
    assert validator.requests == []
