"""독립 검증 · 난도 · 출시. 생성은 가짜 생성기로, 검증은 가짜 검증기로 돌린다. API 호출은 없다."""
import json

import pytest

from golden_pipeline import storage
from golden_pipeline.generation import comparison_answer, generate, import_c, with_document
from golden_pipeline.plan import load_plan, make_plan
from golden_pipeline.schema import DIFFICULTIES
from golden_pipeline.validation import (
    VALIDATOR_VERSION, difficulty, quantities, release, same_answer, same_comparison, validate,
)

CONFIG = {
    "model": "validator-test", "reasoning_effort": "high", "max_calls": 20, "budget_usd": 1.0,
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

    def __call__(self, model, reasoning_effort, messages):
        text = json.dumps(self.rows.pop(0), ensure_ascii=False)
        return {"model": "generator-test", "text": text, "input_tokens": 10, "output_tokens": 10}


class Validator:
    """검증기 대역. 받은 메시지를 기록하고, 받은 근거 라벨 조합에 정해 둔 답을 돌려준다 ('*' 는 그 밖의 조합).

    판정기 프롬프트로 온 호출에는 same 을 돌려준다.
    """

    def __init__(self, verdicts, same=None):
        self.verdicts = verdicts
        self.same = same
        self.requests = []

    def __call__(self, model, reasoning_effort, messages):
        self.requests.append(messages)
        if messages[0]["content"] == (storage.PROMPTS / "judge.txt").read_text(encoding="utf-8"):
            reply = {"same": self.same}
        else:
            reply = self.verdicts.get(self.labels(messages), self.verdicts.get("*"))
        return {"model": "validator-test", "text": json.dumps(reply, ensure_ascii=False),
                "input_tokens": 10, "output_tokens": 10}

    @staticmethod
    def labels(messages):
        return tuple(unit["label"] for unit in json.loads(messages[1]["content"])["evidence"])


class Screener:
    """출시 전 쓸모 판정 대역. 질문 끝말에 replies[끝말] 을 글 그대로 돌려주고, 없으면 쓸모 있다고 답한다."""

    def __init__(self, replies=None):
        self.replies = replies or {}
        self.requests = []

    def __call__(self, model, reasoning_effort, messages):
        self.requests.append(messages)
        question = json.loads(messages[1]["content"])["question"]
        reply = next((text for end, text in self.replies.items() if question.endswith(end)),
                     json.dumps({"useful": True, "code": None, "reason": "예산을 묻는다"}, ensure_ascii=False))
        return {"model": "screen-test", "text": reply, "input_tokens": 10, "output_tokens": 10}


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
    rows = [row for name in ("accepted.jsonl", "rejected.jsonl") for row in read_jsonl(run_dir / name)]
    return {row["candidate_id"]: row for row in rows if "candidate_id" in row}


def test_validator_sees_only_the_question_and_the_cited_evidence_units(config):
    # 생성기의 답 · 근거 해설 · 자기 평가가 검증기 입력에 섞이면 독립 답과의 비교가 의미를 잃는다.
    row = {**NUMERIC, "answer": "130,000,000원(부가세 포함). 생성기 자기 평가: 확실함, 근거 해설: E1 첫 문장"}
    generate("A", "numeric", "p1", "a1", config, Generator(row))
    validator = Validator({"*": verdict("130,000,000원", ["부가세 포함"])})

    validate("numeric", "A", "a1", config, validator)

    numeric = bundle("p1", "numeric")
    question = with_document(row["question"], numeric["doc"])
    question_and_units = {"question": question, "evidence": [{"label": "E1", "text": numeric["units"][0]["text"]}]}
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
    pytest.param("numeric", NUMERIC, {"*": verdict("1억 3천만원", ["부가세 포함"])}, "auto_validated", "자동 검증 통과",
                 id="numeric-passes"),
    pytest.param("numeric", NUMERIC, {"*": verdict("13,000,000원", ["부가세 포함"])}, "rejected", "독립 답과 다릅니다",
                 id="numeric-value-differs"),
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
    # 애매한 판정은 실패 코드가 없어 자기 개선에 쓸 수 없다. 모든 후보는 통과 아니면 거절로 끝난다.
    pytest.param("numeric", NUMERIC, {"*": verdict("130,000,000원", conflict=True)}, "rejected", "근거 충돌",
                 id="evidence-conflict"),
    pytest.param("numeric", NUMERIC, {"*": "검증기 출력이 깨졌습니다"}, "rejected", "검증기 출력 오류",
                 id="broken-validator-output"),
    # 값 · 글자로 정하지 못한 답은 판정기가 정한다.
    pytest.param("numeric", {**NUMERIC, "answer": "130,000,000원, 2억원(부가세 포함)"},
                 {"*": verdict("사업 예산 130,000,000원, 예비비 2억원")}, "rejected", "독립 답과 다릅니다",
                 id="unattributed-values-judged-different"),
    pytest.param("condition", CONDITION, {"*": verdict("우편 접수 불가", ["우편 접수는 받지 않는다"])},
                 "rejected", "독립 답과 다릅니다", id="reworded-text-judged-different"),
])
def test_each_check_sends_the_candidate_to_its_state(config, topic, row, verdicts, state, reason):
    generate("A", topic, "p1", "a1", config, Generator(row))

    run_dir = validate(topic, "A", "a1", config, Validator(verdicts, same=False))

    [item] = validated(run_dir).values()
    assert (item["state"], item["state_history"][-1]["reason"][:len(reason)]) == (state, reason)
    file = {"auto_validated": "accepted.jsonl", "rejected": "rejected.jsonl"}[state]
    assert item in read_jsonl(run_dir / file)
    assert item["validator_version"] == VALIDATOR_VERSION and item["difficulty"] in DIFFICULTIES
    record = json.loads((run_dir / "validation.json").read_text(encoding="utf-8"))
    assert record["validator_version"] == VALIDATOR_VERSION and record["difficulty_rule"].startswith("difficulty-2")


BUDGETS = {"A안": "1억원", "B안": "2억원"}


@pytest.mark.parametrize("values, choice, independent, same, state", [
    (BUDGETS, "B안", {"values": {"A안": "100,000,000원", "B안": "2억원"}, "choice": "B안"}, None, "auto_validated"),
    (BUDGETS, "A안", {"values": BUDGETS, "choice": "B안"}, None, "rejected"),
    ({"A안": "2억원", "B안": "1억원"}, "B안", {"values": BUDGETS, "choice": "B안"}, None, "rejected"),
    # 필드로 맞출 기준이 없으면 판정기가 정한다.
    (BUDGETS, "B안", None, True, "auto_validated"),
    (BUDGETS, "B안", {"values": {"A안": "1억원", "C안": "2억원"}, "choice": "B안"}, False, "rejected"),
])
def test_comparison_compares_each_entity_value_and_the_chosen_entity_with_the_validator(config, values, choice,
                                                                                        independent, same, state):
    # 비교 답의 결론(어느 대상을 골랐는지)은 글에서 읽을 수 없다. 후보 structure 와 검증기 comparison 을 필드로 맞춘다.
    make_plan("p3", "ev1", {"numeric": 1, "comparison": 1}, 2000, package=config.parent / "v11")
    structure = {"entities": ["A안", "B안"], "values": values, "choice": choice}
    row = {"question": "A안과 B안 중 예산이 더 많은 안은?", "answer": comparison_answer(structure),
           "evidence": ["E1", "E2"], "structure": structure, "secondary_tags": []}
    generate("A", "comparison", "p3", "a1", config, Generator(row))

    validator = Validator({"*": verdict("B안", comparison=independent)}, same=same)
    run_dir = validate("comparison", "A", "a1", config, validator)

    [item] = validated(run_dir).values()
    assert item["state"] == state
    assert len(validator.requests) == (1 if same is None else 2)


def test_a_reworded_text_answer_is_settled_by_the_judge_after_the_blind_independent_answer(config):
    # 글 답은 표현만 달라도 글자로는 다르다. 글자 비교만 하면 맞는 답이 거절로 쌓여 자기 개선이 엉뚱한 실패를 배운다.
    generate("A", "condition", "p1", "a1", config, Generator(CONDITION))
    validator = Validator({"*": verdict("우편 접수 불가", ["우편 접수는 받지 않는다"])}, same=True)

    run_dir = validate("condition", "A", "a1", config, validator)

    [item] = validated(run_dir).values()
    assert item["state"] == "auto_validated"
    blind, judged = validator.requests
    assert CONDITION["answer"] not in json.dumps(blind, ensure_ascii=False)
    sent = json.loads(judged[1]["content"])
    assert (sent["answer_a"], sent["answer_b"]) == ("우편 접수 불가", CONDITION["answer"])


@pytest.mark.parametrize("mine, theirs, same", [
    ("미지원", "지원", None),
    ("1억원 이상", "1억원", None),
    ("1억원", "2억원", False),
    ("구축 2억원, 운영 1억원", "구축 1억원, 운영 2억원", False),
    ("구축 130,000,000원, 운영 2억원", "구축 1억 3천만원, 운영 200,000,000원", True),
    ("제4회 회의 1억원", "제3회 회의 1억원", None),
    ("- 2억원 감액", "-200,000,000원 감액", True),
])
def test_structured_values_must_be_equal_not_just_contained(mine, theirs, same):
    # 값 필드는 담기가 아니라 같음을 본다. 미지원 은 지원 을 글자로 담지만 반대 뜻이다.
    structure = {"entities": ["A안", "B안"], "values": {"A안": mine, "B안": "2억원"}, "choice": None}
    assert same_comparison(structure, {"values": {"A안": theirs, "B안": "2억원"}, "choice": None}) is same


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
        release("numeric", "v1", [("A", "a1"), ("C", "c1")], config, Screener())


@pytest.mark.parametrize("question, proven, level", [
    ("사업 예산은 얼마인가?", False, "easy"),
    ("총 사업비는 얼마인가?", False, "medium"),
    ("사업 예산은 얼마인가?", True, "hard"),
])
def test_difficulty_follows_the_recorded_rule(question, proven, level):
    units = [{"text": "사업 예산은 130,000,000원(부가세 포함)이며 계약 기간은 12개월이다."}]
    assert difficulty(question, units, proven) == level


@pytest.fixture
def judged(config, tmp_path):
    """c1: 0001 은 auto_validated, 0002 · 0003 은 근거 충돌로 rejected."""
    rows = [
        NUMERIC,
        {**NUMERIC, "question": "사업 예산의 부가세 포함 여부는?", "evidence": ["E1", "E2"]},
        {"question": "하자 보수 기간은?", "answer": "1년 이내", "evidence": ["E2"],
         "structure": {"value": "1", "unit": "년"}, "secondary_tags": []},
    ]
    import_rows(tmp_path, "numeric", rows)
    validator = Validator({("E1",): verdict("130,000,000원", ["부가세 포함"]), "*": verdict("1년", conflict=True)})
    return validate("numeric", "C", "c1", config, validator)


def test_release_collects_only_accepted_items_and_refuses_an_existing_version(judged, config):
    run_dir = judged
    screener = Screener()

    release_dir = release("numeric", "v1", [("C", "c1")], config, screener)

    golden = read_jsonl(release_dir / "golden.jsonl")
    assert [(item["candidate_id"], item["state_history"][-1]["reason"]) for item in golden] == [
        ("numeric-C-c1-0001", "자동 검증 · 쓸모 판정 통과"),
    ]
    # 판정기는 질문과 답만 받는다.
    assert json.loads(screener.requests[0][1]["content"]) == {"question": golden[0]["question"], "answer": golden[0]["answer"]}
    manifest = json.loads((release_dir / "manifest.json").read_text(encoding="utf-8"))
    assert (manifest["runs"], manifest["count"]) == (["C/c1"], 1)
    assert manifest["golden_sha256"] == storage._sha256(release_dir / "golden.jsonl")
    assert manifest["release"]["screen_prompt_sha256"] == storage._sha256(storage.PROMPTS / "screen.txt")
    for name in ("candidates.jsonl", "accepted.jsonl", "manifest.json", "validation.json"):
        assert manifest["sources"]["C/c1"][name] == storage._sha256(run_dir / name)
    before = (release_dir / "golden.jsonl").read_bytes()

    with pytest.raises(FileExistsError):
        release("numeric", "v1", [("C", "c1")], config, Screener())
    assert (release_dir / "golden.jsonl").read_bytes() == before


@pytest.mark.parametrize("reply, code, reason", [
    (json.dumps({"useful": False, "code": "structure_question", "reason": "쪽 번호를 묻는다"}, ensure_ascii=False),
     "structure_question", "쪽 번호를 묻는다"),
    # 출력이 두 번 다 계약을 어기면 애매하게 남기지 않고 뺀다. 코드가 없으면 실패 기록에 쓸 수 없어 계약 위반이다.
    ("쓸모 있음", None, "판정기 출력 오류: JSON 이 아닙니다"),
    (json.dumps({"useful": False, "code": None, "reason": "쪽 번호를 묻는다"}, ensure_ascii=False), None, "판정기 출력 오류: code"),
])
def test_an_item_the_screen_rejects_is_left_out_with_its_code_and_reason(judged, config, reply, code, reason):
    # 목차 · 쪽 번호를 묻는 질문은 답이 근거와 맞아 검증을 통과하지만 RAG 평가에 쓸모가 없다.
    screener = Screener({"얼마인가?": reply})

    release_dir = release("numeric", "v1", [("C", "c1")], config, screener)

    assert read_jsonl(release_dir / "golden.jsonl") == []
    info = json.loads((release_dir / "manifest.json").read_text(encoding="utf-8"))["release"]
    [dropped] = info["dropped"]
    assert dropped["candidate_id"] == "numeric-C-c1-0001" and dropped["reason"].startswith(reason)
    assert (dropped["method"], dropped["code"]) == ("C", code)
    assert (info["screened"], info["calls"]) == (1, len(screener.requests))


def test_release_stops_without_writing_when_the_screen_would_pass_its_call_cap(judged, tmp_path):
    path = tmp_path / "screen.json"
    path.write_text(json.dumps({**CONFIG, "max_calls": 1}), encoding="utf-8")
    with pytest.raises(ValueError, match="call_cap"):
        release("numeric", "v1", [("C", "c1")], path, Screener())
    assert not (storage.OUTPUTS / "goldens" / "numeric" / "releases").exists()


def test_release_refuses_files_changed_after_validation(judged, config):
    # 거절 항목을 accepted.jsonl 로 옮겨 출시본에 끼워 넣지 못하게 한다.
    run_dir = judged
    rejected = [line for line in (run_dir / "rejected.jsonl").read_text(encoding="utf-8").splitlines()
                if "candidate_id" in line]
    with (run_dir / "accepted.jsonl").open("a", encoding="utf-8") as f:
        f.write("\n".join(rejected) + "\n")
    with pytest.raises(storage.CatalogError, match="validation.json"):
        release("numeric", "v1", [("C", "c1")], config, Screener())
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
