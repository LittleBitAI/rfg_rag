"""독립 검증 · 난도 · 출시. 생성은 가짜 생성기로, 검증은 가짜 검증기로 돌린다. API 호출은 없다."""
import json
from collections import deque

import pytest

from golden_pipeline import evidence, generation, improvement, report, storage, validation
from golden_pipeline.generation import comparison_answer, generate, import_c, with_document
from golden_pipeline.plan import load_plan, make_plan
from golden_pipeline.plan import topic_spec as load_topic_spec
from golden_pipeline.schema import DIFFICULTIES
from golden_pipeline.validation import (
    VALIDATOR_VERSION, _premise_absent, difficulty, quantities, release, same_answer, same_comparison, validate,
)
from conftest import DOC_2, UNITS, _write_jsonl

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
    pytest.param("numeric", {**NUMERIC, "question": "사업 예산의 값과 단위는 무엇인가?"},
                 {"*": verdict("1억 3천만원", ["부가세 포함"])}, "auto_validated", "자동 검증 통과",
                 id="named-numeric-target-passes"),
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
    make_plan("p3", "ev1", {"numeric": 1, "comparison": 1}, 2000, package=config.parent / "v12")
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


@pytest.mark.parametrize("max_calls", [1, CONFIG["max_calls"]])
def test_duplicates_and_items_from_the_same_evidence_group_are_rejected_through_the_catalog(config, tmp_path, max_calls):
    validator = Validator({"*": verdict("130,000,000원", ["부가세 포함"])})
    rows = [
        NUMERIC,
        {**NUMERIC, "question": "사업비는 얼마로 잡혀 있나?"},
        {**NUMERIC, "question": " 사업 예산은  얼마인가? ", "evidence": ["E1", "E2"]},
    ]
    import_rows(tmp_path, "numeric", rows)
    capped = tmp_path / "duplicates.json"
    capped.write_text(json.dumps({**CONFIG, "max_calls": max_calls}), encoding="utf-8")
    run_dir = validate("numeric", "C", "c1", capped, validator)
    c1 = validated(run_dir)
    record = json.loads((run_dir / "validation.json").read_text(encoding="utf-8"))
    assert record["pending"] == [] and record["status"] == "complete"
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


def test_uncited_blank_table_rows_do_not_reject_validation_or_release(config):
    # 묶음의 비고 행이 비어 있어도 인용한 예산 행과 머리글은 명확하다.
    planned = load_plan("p1")[0]
    table = next(group for group in planned["bundles"] if group["topic"] == "table")
    table["units"][2]["text"] = "비고 | | 별도"
    table["context"] = "\n\n".join(f"[{unit['label']}]\n{unit['text']}" for unit in table["units"])
    storage._write_json(storage.OUTPUTS / "plans" / "p1.json", planned)
    generate("A", "table", "p1", "a1", config, Generator(TABLE))
    validator = Validator({"*": verdict("1억원")})

    run_dir = validate("table", "A", "a1", config, validator)
    release_dir = release("table", "v1", [("A", "a1")], config, Screener())

    assert len(read_jsonl(run_dir / "accepted.jsonl")) == len(validator.requests) == 1
    assert len(read_jsonl(release_dir / "golden.jsonl")) == 1


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


def test_resume_counts_only_the_calls_a_candidate_has_not_already_settled_against_the_call_cap(config, tmp_path):
    # multi_hop 후보는 호출 셋(전체 · E1 · E2)이다. 전체가 정산된 뒤 E1 이 실험 장부에 거절되면 남은 호출은 둘이다.
    # 호출 기록에는 역할이 없다. 검증기가 보낼 요청을 다시 만들어 요청 SHA-256 으로 정산된 호출을 찾는다.
    export, sidecar = tmp_path / "multi.jsonl", tmp_path / "sidecar.json"
    export.write_text(json.dumps({**MULTI_HOP, "bundle_id": bundle("p2", "multi_hop")["bundle_id"]}, ensure_ascii=False) + "\n",
                      encoding="utf-8")
    sidecar.write_text("{}", encoding="utf-8")
    import_c("multi_hop", "p2", "c1", [export], sidecar)
    validator = Validator({("E1", "E2"): verdict("2년"), ("E1",): verdict("", answerable=False), ("E2",): verdict("1년", ["이내"])})

    def refuse_singles(model, reasoning_effort, messages):
        if len(Validator.labels(messages)) == 1:
            raise generation.BudgetExceeded("실험 상한")
        return validator(model, reasoning_effort, messages)

    validate("multi_hop", "C", "c1", config, refuse_singles)
    capped = tmp_path / "capped.json"
    capped.write_text(json.dumps({**CONFIG, "max_calls": 2}), encoding="utf-8")
    run_dir = validation.resume_validation("multi_hop", "C", "c1", capped, validator)

    # 정산된 전체 호출은 다시 쓰므로 한도 2 로 E1 · E2 를 보내 끝낸다.
    assert [Validator.labels(messages) for messages in validator.requests] == [("E1", "E2"), ("E1",), ("E2",)]
    [item] = validated(run_dir).values()
    assert item["state"] == "auto_validated"


@pytest.mark.parametrize("method", ["B", "C"])
@pytest.mark.parametrize("previous_version", ["validation-7", "validation-8", "validation-9", "validation-10", "validation-11", "validation-12", "validation-13", "validation-14"])
def test_resume_refuses_pending_candidates_validated_under_previous_versions(config, monkeypatch, tmp_path, method, previous_version):
    current = validation.VALIDATOR_VERSION
    generator = Generator(NUMERIC)
    if method == "B":
        generate(method, "numeric", "p1", "old", config, generator)
    else:
        import_rows(tmp_path, "numeric", [NUMERIC], run_id="old")
    monkeypatch.setattr(validation, "VALIDATOR_VERSION", previous_version)

    def exhausted(**kwargs):
        raise generation.BudgetExceeded("실험 상한")

    run_dir = validate("numeric", method, "old", config, exhausted)
    assert storage._read_json(run_dir / "validation.json")["pending"]
    before = storage.snapshot(run_dir)
    monkeypatch.setattr(validation, "VALIDATOR_VERSION", current)
    client = Validator({"*": verdict("130,000,000원", ["부가세 포함"])})
    with pytest.raises(ValueError, match="validator_version"):
        validation.resume_validation("numeric", method, "old", config, client)
    assert client.requests == [] and storage.snapshot(run_dir) == before


def test_a_settled_judge_call_does_not_count_as_a_paid_validator_call(config):
    # 판정기 요청은 같은 질문 · 근거에 두 답이 더 있어 검증기 요청과 SHA-256 이 다르다. 그 출력이 남아 있어도 검증기 호출 셋은 그대로 사야 한다.
    planned = bundle("p2", "multi_hop")
    item = {**MULTI_HOP, "primary_topic": "multi_hop", "evidence": [unit["ref"] for unit in planned["units"][:2]]}
    units = validation.evidence_units(item, planned)
    asked = validation.validator_input(item["question"], units)
    judged = json.dumps({**asked, "answer_a": "2년", "answer_b": "2년"}, ensure_ascii=False)
    judge = validation._request_sha256((storage.PROMPTS / "judge.txt").read_text(encoding="utf-8"), judged)
    validator = (storage.PROMPTS / "validator.txt").read_text(encoding="utf-8")

    assert validation._calls_left(item, units, None, {(judge, 0): deque(['{"same": true}'])}, validator) == 3


def test_free_rejections_are_recorded_even_after_a_candidate_blocked_by_the_call_cap(config, tmp_path):
    # 앞 후보는 유료 호출이 필요해 pending 이어도 뒤 후보의 무료 거절과 실패 코드는 남아야 한다.
    planned = load_plan("p2")[0]
    group = planned["bundles"][0]
    group["units"][2]["ref"]["chunk_id"] = group["units"][1]["ref"]["chunk_id"]
    storage._write_json(storage.OUTPUTS / "plans" / "p2.json", planned)
    rows = [MULTI_HOP, {**MULTI_HOP, "question": "이 두 근거를 이으면 몇 년인가?", "evidence": ["E2", "E3"]}]
    export = tmp_path / "multi.jsonl"
    export.write_text("".join(json.dumps({**row, "bundle_id": group["bundle_id"]}, ensure_ascii=False) + "\n"
                              for row in rows), encoding="utf-8")
    sidecar = tmp_path / "sidecar.json"
    sidecar.write_text("{}", encoding="utf-8")
    import_c("multi_hop", "p2", "c1", [export], sidecar)
    capped = tmp_path / "capped.json"
    capped.write_text(json.dumps({**CONFIG, "max_calls": 1}), encoding="utf-8")
    validator = Validator({"*": verdict("2년")})

    run_dir = validate("multi_hop", "C", "c1", capped, validator)

    record = json.loads((run_dir / "validation.json").read_text(encoding="utf-8"))
    [rejected] = read_jsonl(run_dir / "rejected.jsonl")
    assert (record["status"], record["pending"], record["calls"]) == ("call_cap", ["multi_hop-C-c1-0001"], [])
    assert rejected["candidate_id"] == "multi_hop-C-c1-0002"
    assert rejected["state_history"][-1]["reason"].startswith("multi_hop 아님")
    assert validator.requests == []


REFUSAL = "제공된 문서에서 확인할 수 없습니다."


def unanswerable(question, attribute, key_terms, evidence):
    return {"question": question, "answer": REFUSAL, "evidence": evidence, "secondary_tags": [],
            "structure": {"attribute": attribute, "key_terms": key_terms}}


@pytest.fixture
def borrowed(config):
    """p3: 문서 1 의 근거(E1 · E2 = u1 · u2)로 문서 2 에 묻는 unanswerable 묶음 하나."""
    make_plan("p3", "ev1", {"unanswerable": 1}, 2000, package=config.parent / "v12")
    return config


@pytest.mark.parametrize("topic", ["unanswerable", "false_premise"])
@pytest.mark.parametrize("change", ["source_with_repin", "adapter_body", "judgment"])
def test_document_validation_rejects_inconsistent_source_or_adapter_records(config, topic, change):
    package = config.parent / "v12"
    make_plan("p-document", "ev1", {topic: 1}, 2000, package=package)
    row = (unanswerable("계약 기간은 얼마인가?", "계약 기간", ["계약"], ["E1"]) if topic == "unanswerable"
           else {"question": "계약 기간 9개월은 언제 끝나나?", "answer": "계약 기간은 9개월이 아니라 12개월이다.",
                 "evidence": ["E1"], "structure": {"stated": "9개월", "actual": "12개월"}, "secondary_tags": []})
    generate("A", topic, "p-document", "a-document", config, Generator(row))
    evidence_dir = storage.OUTPUTS / "evidence/ev1"
    if change == "source_with_repin":
        path = package / evidence.CHUNKS
        path.write_text(path.read_text(encoding="utf-8") + '\n', encoding="utf-8")
        manifest_path = evidence_dir / "manifest.json"
        manifest = storage._read_json(manifest_path)
        manifest["pinned_sha256"][evidence.CHUNKS] = storage._sha256(path)
        manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
    else:
        path = evidence_dir / ("units.jsonl" if change == "adapter_body" else "judgments.jsonl")
        rows = storage._read_jsonl(path)
        rows[-1].update({"text": "tampered held evidence"} if change == "adapter_body" else {"judgment": "eligible"})
        _write_jsonl(path, rows)
    before = storage.snapshot(storage.OUTPUTS)
    validator = Validator({"*": verdict("12개월", answerable=topic != "unanswerable")})
    with pytest.raises(evidence.PackageMismatch, match="SHA-256|units.jsonl|judgments.jsonl"):
        validate(topic, "A", "a-document", config, validator)
    assert validator.requests == []
    assert storage.snapshot(storage.OUTPUTS) == before


def test_an_attribute_found_only_in_a_held_unit_of_the_asked_document_is_rejected(borrowed):
    # 문서 2 에서 하자 보수 기간은 원본 대조 예외로 보류된 청크에만 있다. eligible 만 보면 없는 것으로 잘못 출시된다.
    row = unanswerable("하자 보수 기간은 얼마인가?", "하자 보수 기간", ["하자"], ["E2"])
    generate("A", "unanswerable", "p3", "a1", borrowed, Generator(row))
    validator = Validator({"*": verdict("", answerable=False)})

    run_dir = validate("unanswerable", "A", "a1", borrowed, validator)

    [item] = validated(run_dir).values()
    assert item["state"] == "rejected"
    assert item["state_history"][-1]["reason"].startswith("대상 문서에 있음: 핵심어 ['하자'] 가 근거 단위 chunk:c-u9")
    assert validator.requests == []


@pytest.mark.parametrize("reply, state, reason", [
    (verdict("", answerable=False), "auto_validated", "자동 검증 통과"),
    # 핵심어를 다른 말로 쓴 근거는 글자 검사를 지나므로, 대상 문서에서 고른 근거로 검증기가 답하면 거절한다.
    (verdict("11월 3일까지"), "rejected", "대상 문서에 있음: 검증기"),
    # 근거끼리 값이 다르면 속성은 문서에 있다. 답을 고르지 못했다고 없는 것으로 통과시키지 않는다.
    (verdict("", answerable=False, conflict=True), "rejected", "근거 충돌"),
])
def test_an_attribute_absent_from_every_unit_of_the_asked_document_is_kept_unless_the_validator_answers(
        borrowed, reply, state, reason):
    row = unanswerable("계약 기간은 얼마인가?", "계약 기간", ["계약"], ["E1"])
    generate("A", "unanswerable", "p3", "a1", borrowed, Generator(row))
    validator = Validator({"*": reply})

    run_dir = validate("unanswerable", "A", "a1", borrowed, validator)

    [item] = validated(run_dir).values()
    assert (item["state"], item["state_history"][-1]["reason"][:len(reason)]) == (state, reason)
    # 검증기는 근거 묶음(문서 1)이 아니라 질문이 묻는 문서 2 의 근거만 받는다.
    [request] = validator.requests
    sent = {unit["text"] for unit in json.loads(request[1]["content"])["evidence"]}
    assert sent == {body for _, doc, body, _ in UNITS if doc == DOC_2}


def test_absence_is_certified_only_after_the_validator_has_read_every_unit_of_the_asked_document(borrowed, monkeypatch):
    # 질문 낱말을 많이 담은 단위 몇 개만 주면, 다른 말로 적힌 답(문서 끝의 하자 보수 청크)은 검증기가 보지 못해 통과했다.
    monkeypatch.setattr(validation, "DOCUMENT_BATCH_CHARS", 1)
    monkeypatch.setattr(validation, "DOCUMENT_OVERLAP_CHARS", 0)
    row = unanswerable("계약 기간은 얼마인가?", "계약 기간", ["계약"], ["E1"])
    generate("A", "unanswerable", "p3", "a1", borrowed, Generator(row))
    last = f"E{sum(doc == DOC_2 for _, doc, _, _ in UNITS)}"
    validator = Validator({(last,): verdict("2년"), "*": verdict("", answerable=False)})

    run_dir = validate("unanswerable", "A", "a1", borrowed, validator)

    [item] = validated(run_dir).values()
    assert item["state_history"][-1]["reason"].startswith("대상 문서에 있음: 검증기")
    assert [Validator.labels(request) for request in validator.requests][-1] == (last,)


def doc_unit(unit_id, text, element_id=None, row=None):
    """document_units 와 같은 꼴의 단위. row 가 있으면 그 행부터 시작하는 표 청크다."""
    location = {"kind": "char"} if row is None else {"kind": "table", "row": row}
    return {"unit_id": unit_id, "element_id": element_id, "location": location, "text": text}


TABLES = [
    doc_unit("p1", "사업 개요 " * 6),
    doc_unit("t0", "시스템 | 하자담보책임기간 | 무상 기술지원기간", "e-t", 0),
    doc_unit("t1", "A시스템 | 12개월 | 36개월", "e-t", 1),
    doc_unit("t2", "B시스템 | 24개월 | 12개월", "e-t", 2),
]
# 표의 행과 그 표의 머리글. 검증기는 어느 한 묶음에서 이 글을 함께 읽어야 한다.
ROWS = [{"시스템 | 하자담보책임기간", "A시스템 | 12개월"}, {"시스템 | 하자담보책임기간", "B시스템 | 24개월"}]


def read_together(batches, texts):
    return any(all(text in "\n".join(unit["text"] for unit in batch) for text in texts) for batch in batches)


@pytest.mark.parametrize("overlap", [0, 20])
@pytest.mark.parametrize("limit", [40, 70, 1])
def test_every_table_row_is_read_in_one_batch_with_its_header(monkeypatch, limit, overlap):
    # 글자 수로만 자르면 머리글이 앞 묶음에, 행이 뒤 묶음에 가서 어느 묶음으로도 '하자담보책임기간 12개월' 을 읽을 수 없었다.
    # 40 은 표가 다음 묶음에 통째로 들어가고, 70 은 맨 자르기가 표 안에 떨어지며, 1 은 표가 어느 묶음보다 크다.
    monkeypatch.setattr(validation, "DOCUMENT_BATCH_CHARS", limit)
    monkeypatch.setattr(validation, "DOCUMENT_OVERLAP_CHARS", overlap)

    batches = validation.document_batches(TABLES)

    assert all(read_together(batches, {unit["text"]}) for unit in TABLES)
    assert [texts for texts in ROWS if not read_together(batches, texts)] == []


@pytest.mark.parametrize("limit, overlap, document, needed, question", [
    (70, 20, TABLES, {"하자담보책임기간", "A시스템 | 12개월"}, "A시스템의 하자보수 기간은?"),
    # 표 밖의 소제목과 그 아래 글도 경계로 갈리면 따로는 답이 나오지 않는다. 새 묶음은 앞 묶음 끝을 다시 받는다.
    (70, 20, [doc_unit("p1", "사업 개요 " * 9), doc_unit("h", "A시스템 하자담보책임"), doc_unit("v", "기간: 준공 후 12개월")],
     {"A시스템 하자담보책임", "기간: 준공 후 12개월"}, "A시스템의 하자보수 기간은?"),
])
def test_absence_is_not_certified_when_the_answer_needs_units_on_both_sides_of_a_batch_boundary(
        monkeypatch, limit, overlap, document, needed, question):
    monkeypatch.setattr(validation, "DOCUMENT_BATCH_CHARS", limit)
    monkeypatch.setattr(validation, "DOCUMENT_OVERLAP_CHARS", overlap)

    def ask(question, batch):
        found = read_together([batch], needed)
        return verdict("1년" if found else "", answerable=found), None

    state, reason = validation._absent_verdict({"question": question}, document, ask)

    assert (state, reason[:len("대상 문서에 있음: 검증기")]) == ("rejected", "대상 문서에 있음: 검증기")


def test_an_unanswerable_release_names_the_asked_document_and_tells_the_screen_why_it_refuses(borrowed):
    row = unanswerable("계약 기간은 얼마인가?", "계약 기간", ["계약"], ["E1"])
    generate("A", "unanswerable", "p3", "a1", borrowed, Generator(row))
    validate("unanswerable", "A", "a1", borrowed, Validator({"*": verdict("", answerable=False)}))
    screener = Screener()

    release_dir = release("unanswerable", "v1", [("A", "a1")], borrowed, screener)

    [item] = read_jsonl(release_dir / "golden.jsonl")
    assert item["question"] == "나기관의 「나사업 운영」 사업에서 계약 기간은 얼마인가?"
    note = load_topic_spec("unanswerable")[0]["screen"]
    assert screener.requests[0][0]["content"].endswith(note)


@pytest.mark.parametrize("stated, state, reason", [
    ("9개월", "auto_validated", "자동 검증 통과"),
    # 6개월 은 문서 1 의 다른 근거(표 행)에 있다. 그 값을 전제한 질문은 틀린 전제가 아니다.
    ("6개월", "rejected", "전제가 문서에 있음"),
])
def test_a_false_premise_must_state_a_value_found_nowhere_in_its_document(config, stated, state, reason):
    make_plan("p4", "ev1", {"false_premise": 1}, 2000, package=config.parent / "v12")
    row = {"question": f"계약 기간 {stated}은 언제 끝나나?", "answer": f"계약 기간은 {stated}이 아니라 12개월이다.",
           "evidence": ["E1"], "structure": {"stated": stated, "actual": "12개월"}, "secondary_tags": []}
    generate("A", "false_premise", "p4", "a1", config, Generator(row))

    run_dir = validate("false_premise", "A", "a1", config, Validator({"*": verdict("12개월")}))

    [item] = validated(run_dir).values()
    assert (item["state"], item["state_history"][-1]["reason"][:len(reason)]) == (state, reason)


@pytest.mark.parametrize("text, found", [("응답 시간은 13초 이내", False), ("응답 시간은 3초 이내", True)])
def test_a_longer_number_in_the_document_is_not_the_stated_value(text, found):
    item = {"structure": {"stated": "3초", "actual": "5초"}}
    assert (_premise_absent(item, [], [{"unit_id": "u", "text": text}]) is not None) == found


def table_chunk(row, text, titled=False):
    location = {"kind": "table", "grid": "logical_restored", "row": row, "cell": None}
    return {"ref": {"element_id": "e-t", "location": location}, "text": text, "titled": titled}


@pytest.mark.parametrize("row, column, cell", [
    ("B시스템", "무상 기술지원기간", "12개월"),
    # 머리글 청크 뒤에 이어 붙은 청크의 행도 그 머리글로 읽는다.
    ("C시스템", "하자담보책임기간", "6개월"),
    ("시스템", "하자담보책임기간", None),
])
def test_a_table_cell_is_read_from_multi_line_table_chunks_under_their_header(row, column, cell):
    # v12 표 청크는 행을 줄로 잇는다. 한 청크를 한 행으로 읽으면 첫 줄 밖의 칸은 찾지 못했다.
    units = [table_chunk(0, "가. 유지보수\n시스템 | 하자담보책임기간 | 무상 기술지원기간\nA시스템 | 12개월 | 36개월\n"
                            "B시스템 | 24개월 | 12개월"),
             table_chunk(3, "C시스템 | 6개월 | 없음")]
    assert validation._cell(units, row, column) == cell


def test_a_title_line_naming_the_column_is_not_read_as_the_header():
    # 표 앞 소제목이 열 이름과 같으면, 소제목을 머리글로 읽어 행 이름을 칸 값으로 돌려줬다.
    units = [table_chunk(0, "무상 기술지원기간\n시스템 | 무상 기술지원기간\nA시스템 | 12개월")]
    assert validation._cell(units, "A시스템", "무상 기술지원기간") == "12개월"


def test_multi_hop_asks_a_header_chunk_alone_and_gives_later_chunks_only_the_header_line():
    # v12 의 0행 청크는 데이터 행도 담는다. 단독 검사에서 빼면 그 청크 하나로 답이 나와도 통과했다.
    first = {**table_chunk(0, "시스템 | 하자담보책임기간\nA시스템 | 12개월"), "label": "E1"}
    later = {**table_chunk(3, "B시스템 | 24개월"), "label": "E2"}
    assert [[unit["text"] for unit in asked] for _, asked in validation._single_units([first, later])] == [
        [first["text"]], ["시스템 | 하자담보책임기간", "B시스템 | 24개월"]]

    def ask(question, units):
        return verdict("12개월"), None

    assert validation._single_unit_verdict({"question": "A시스템의 하자담보책임기간은?"}, [first, later],
                                           verdict("12개월"), ask, None) == (
        "rejected", "multi_hop 아님: 근거 E1 하나로 답이 나옵니다")


def test_a_one_cell_header_row_does_not_lend_the_next_data_row_to_a_single_unit_check():
    # 한 칸짜리 0행을 건너뛰고 칸이 둘 이상인 첫 줄을 붙이면, 다른 청크의 데이터 행이 단독 검사에 섞였다.
    first = {**table_chunk(0, "연계\nA사업 | 운영팀"), "label": "E1"}
    later = {**table_chunk(2, "운영팀 | 코드 Z9"), "label": "E2"}

    def ask(question, units):
        text = "\n".join(unit["text"] for unit in units)
        both = "A사업 | 운영팀" in text and "운영팀 | 코드 Z9" in text
        return verdict("Z9" if both else "", answerable=both), None

    assert validation._single_unit_verdict({"question": "A사업 담당 팀의 코드는?"}, [first, later],
                                           verdict("Z9"), ask, None)[0] == "auto_validated"


@pytest.mark.parametrize("title, expected", [
    ("", "multi_hop 아님: 근거 E2 하나로 답이 나옵니다"),
    # 제목 줄을 머리글로 붙이면 열 이름 없이 물어 단순 조회가 다단계로 통과했다.
    ("유지보수\n", "multi_hop 판정 불가: 근거 E2 의 표는 앞에 제목이 붙어 머리글 줄을 가릴 수 없습니다"),
])
def test_a_simple_table_lookup_is_not_accepted_as_multi_hop_with_or_without_a_title(title, expected):
    first = {**table_chunk(0, f"{title}시스템 | 하자담보책임기간 | 무상 기술지원기간\nA시스템 | 12개월 | 36개월",
                           titled=bool(title)), "label": "E1"}
    later = {**table_chunk(2, "B시스템 | 24개월 | 6개월"), "label": "E2"}

    def ask(question, units):
        text = "\n".join(unit["text"] for unit in units)
        both = "하자담보책임기간" in text and "B시스템" in text
        return verdict("24개월" if both else "", answerable=both), None

    item = {"question": "B시스템의 하자담보책임기간은?", "primary_topic": "multi_hop"}
    assert validation._single_unit_verdict(item, [first, later], verdict("24개월"), ask, None) == ("rejected", expected)
    # 실패 기록과 비교 보고서가 이 거절을 코드로 바꾸지 못하면 A loop 와 보고서가 멈췄다.
    assert improvement.failure_code(expected) == report._code(expected) == "not_multi_hop"
    # 한도에 세는 요청 수: 함께 한 번 + 판정이 멈추기 전까지의 단독 검사.
    assert len(validation._validator_unit_lists(item, [first, later], None)) == (2 if title else 3)
