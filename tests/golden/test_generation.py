"""후보 생성: A · B 는 가짜 클라이언트로, C 는 내보낸 파일로 같은 출력 계약 검사와 저장을 거친다. API 호출은 없다."""
import json

import pytest

from golden_pipeline import storage
from golden_pipeline.generation import UNOBSERVED, check_structure, generate, import_c
from golden_pipeline.plan import load_plan, make_plan, topic_spec

DOC_1 = "1" * 64
REPORTED = "gpt-test-2026-10-01"
CONFIG = {
    "model": "gpt-test", "reasoning_effort": "low", "max_calls": 10, "budget_usd": 1.0,
    "usd_per_million_input_tokens": 1.0, "usd_per_million_output_tokens": 4.0,
}
NUMERIC = {
    "question": "사업 예산은 얼마인가?", "answer": "130,000,000원(부가세 포함)", "evidence": ["E1"],
    "structure": {"value": "130,000,000", "unit": "원"}, "secondary_tags": [],
}


class Client:
    """요청을 기록하고 정해 둔 답을 차례로 돌려준다. 응답 모델은 요청한 이름과 다르다."""

    def __init__(self, *replies):
        self.replies = [json.dumps(r, ensure_ascii=False) if isinstance(r, dict) else r for r in replies]
        self.requests = []

    def __call__(self, model, reasoning_effort, messages):
        self.requests.append({"model": model, "reasoning_effort": reasoning_effort, "messages": messages})
        return {"model": REPORTED, "text": self.replies.pop(0), "input_tokens": 1000, "output_tokens": 200}


@pytest.fixture
def planned(evidence_run, tmp_path):
    """numeric · table · condition 묶음이 하나씩 있는 계획 p1 과 run 설정 파일 경로."""
    make_plan("p1", "ev1", {"numeric": 1, "table": 1, "condition": 1}, 2000, package=evidence_run)
    config = tmp_path / "run.json"
    config.write_text(json.dumps(CONFIG), encoding="utf-8")
    return config


def read_jsonl(path):
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]


def manifest(run_dir):
    return json.loads((run_dir / "manifest.json").read_text(encoding="utf-8"))


def bundle(topic):
    return next(b for b in load_plan("p1")[0]["bundles"] if b["topic"] == topic)


def test_a_writes_candidates_with_bundle_id_and_the_exact_context_sent(planned, evidence_run):
    client = Client(NUMERIC)
    run_dir = generate("A", "numeric", "p1", "a1", planned, client)

    [item] = read_jsonl(run_dir / "candidates.jsonl")
    numeric = bundle("numeric")
    assert item["state"] == "candidate" and item["state_history"] == [] and item["validator_version"] is None
    assert item["bundle_id"] == numeric["bundle_id"]
    assert item["context"] == client.requests[0]["messages"][1]["content"] == numeric["context"]
    assert item["evidence"] == [numeric["units"][0]["ref"]]
    for name in ("accepted.jsonl", "rejected.jsonl"):
        assert read_jsonl(run_dir / name) == []

    info = manifest(run_dir)["generation"]
    assert client.requests[0]["model"] == info["model_requested"] == "gpt-test"
    assert info["model_reported"] == [REPORTED]
    assert info["prompt_sha256"] == item["prompt_version"] == storage._sha256(storage.PROMPTS / "A" / "numeric.txt")
    assert info["run_config_sha256"] == storage._sha256(planned)
    assert info["plan_sha256"] == load_plan("p1")[1]
    assert info["v11_manifest_sha256"] == storage._sha256(evidence_run / "manifest.json")
    assert info["topic_spec_sha256"] == topic_spec("numeric")[1]
    assert info["bundle_ids"] == [numeric["bundle_id"]]
    assert info["document_scope"] == [DOC_1]
    assert info["input_limits"] == {"max_context_chars": 2000}
    assert info["status"] == "complete"
    assert info["cost_usd"] == pytest.approx((1000 * 1.0 + 200 * 4.0) / 1_000_000)


@pytest.mark.parametrize("answer, structure", [
    ("예산은 사업 규모와 부가세 포함 여부에 따라 정해진다", {"value": "130,000,000", "unit": "원"}),
    ("예산은 사업 규모와 부가세 포함 여부에 따라 정해진다", {"value": "", "unit": ""}),
    # 근거의 12개월 은 값 12 와 단위 개월 이다. 값과 단위를 다르게 나눠도 안 된다.
    ("기간은 12개월이다", {"value": "12개", "unit": "월"}),
])
def test_numeric_candidate_without_a_value_from_evidence_is_rejected_as_type_mismatch(planned, answer, structure):
    # 값 없이 설명만 하는 답이 numeric 후보로 남던 경우를 막는다. 근거에 없는 값은 아래 쌍 검사가 거절한다.
    run_dir = generate("A", "numeric", "p1", "a1", planned, Client({**NUMERIC, "answer": answer, "structure": structure}))

    assert read_jsonl(run_dir / "candidates.jsonl") == []
    [reject] = read_jsonl(run_dir / "rejected.jsonl")
    assert reject["reason"].startswith("유형 불일치")
    assert reject["bundle_id"] == bundle("numeric")["bundle_id"]


def test_a_table_row_cited_without_its_header_row_gets_the_header_row_as_evidence(planned):
    # 생성기는 답에 쓴 행만 인용하곤 해, 열 이름이 근거에 없다며 표 후보 대부분이 거절됐다.
    output = {"question": "예산의 A안 값은?", "answer": "1억원", "evidence": ["E2"],
              "structure": {"row": "예산", "column": "A안"}, "secondary_tags": []}
    run_dir = generate("A", "table", "p1", "a1", planned, Client(output))

    [item] = read_jsonl(run_dir / "candidates.jsonl")
    units = bundle("table")["units"]
    assert item["evidence"] == [units[0]["ref"], units[1]["ref"]]


def test_multi_hop_structure_with_fields_is_told_to_be_an_empty_object():
    # 이 이유 글이 실패 기록 · 묶음별 지난 실패로 다음 round 에 간다. "필드는 [] 여야" 로는 생성기가 필드를 채운 채 120 묶음이 거듭 거절됐다.
    row = {"answer": "5, 8", "structure": {"PER": "5", "DAR": "8"}}
    assert check_structure("multi_hop", topic_spec("multi_hop")[0], row, []) == "structure 는 빈 객체 {} 여야 합니다"


def unit(text, kind="char"):
    location = {"kind": "table", "row": 0} if kind == "table" else {"kind": "char"}
    return {"text": text, "ref": {"location": location}}


@pytest.mark.parametrize("value, unit_name, evidence, ok", [
    ("5", "%", "낙찰 하한율은 5%이다", True),
    ("6", "개월", "기간은 6 개월", True),
    # 조사는 단위에 붙는다 (12개월이다). 단위 끝을 글자 종류로 가르는 수정은 이 값을 거절한다.
    ("12", "개월", "계약 기간은 12개월이다", True),
    # 더 긴 수 안에 든 더 짧은 수다. 수는 통째로 맞아야 한다.
    ("30,000,000", "원", "예산은 130,000,000원이다", False),
    ("2", "개월", "기간은 12개월이다", False),
    # 부호는 값의 일부다.
    ("130,000,000", "원", "-130,000,000원", False),
    ("130,000,000", "원", "△130,000,000원", False),
    ("130,000,000", "원", "- 130,000,000원", False),
    ("5", "%", "금리를 5%p 올린다", False),
    ("5", "%", "금리를 5%포인트 올린다", False),
    ("3", "개", "3개년 계획", False),
    ("12", "개월", "기간은 10~12개월", False),
    ("123", "개월", "1, 2, 3개월 차에 점검", False),
    # 단위 끝이 막히면 더 짧은 단위로 물러나 읽지 않는다 (12개월간 은 12개 가 아니다).
    ("12", "개", "기간은 12개월간", False),
    ("5", "MB", "속도는 5MB/s", False),
    ("2025", "년", "2024년-2025년", False),
    ("3", "회", "제3회 회의", False),
    ("5", "만원", "5만원 이상", True),
])
def test_numeric_pair_must_be_the_whole_expression_in_evidence(value, unit_name, evidence, ok):
    # 근거에서 수의 앞(부호 · 범위)과 단위의 뒤(목록 밖의 더 긴 단위)를 버리고 맞추면 뜻이 다른 값이 근거가 된다.
    row = {"answer": f"{value}{unit_name}", "structure": {"value": value, "unit": unit_name}}
    reason = check_structure("numeric", topic_spec("numeric")[0], row, [unit(evidence)])
    assert reason is None if ok else "근거에 없습니다" in reason, reason


@pytest.mark.parametrize("topic, structure, cited, ok", [
    ("table", {"row": "예산", "column": "A안"}, [unit("구분 | A안", "table"), unit("예산 | 1억원", "table")], True),
    ("table", {"row": "예산", "column": "A안"}, [unit("구분 A안 예산 1억원")], False),
    ("table", {"row": "인력", "column": "A안"}, [unit("구분 | A안", "table")], False),
    ("condition", {"condition": "우편 접수는 받지 않는다"}, [unit("단, 우편 접수는 받지 않는다.")], True),
    ("condition", {"condition": "방문 접수만 받는다"}, [unit("단, 우편 접수는 받지 않는다.")], False),
    ("condition", {"condition": "1년 이내"}, [unit("계약 종료 후 11년 이내로 한다.")], False),
    # 띄어 쓴 두 수는 다른 수다. 공백을 지운 뒤 경계를 보면 앞 줄 끝의 13 과 이어진 131 로 읽어 거절한다.
    ("condition", {"condition": "1. 입찰참가자격 13"}, [unit("Ⅲ. 입찰 안내사항 13\n 1. 입찰참가자격 13")], True),
    # 줄바꿈으로 쉼표 뒤가 벌어진 세 자리 묶음은 한 수다. 앞뒤 어느 쪽에서도 그 일부와 맞추지 않는다.
    ("condition", {"condition": "300,000원 이하"}, [unit("1,\n300,000원 이하")], False),
    ("condition", {"condition": "최대 1,300"}, [unit("최대 1,300,\n000원")], False),
    # 세 자리 묶음이 아닌 쉼표 뒤는 나열이다.
    ("condition", {"condition": "2차 평가"}, [unit("1, 2차 평가")], True),
    ("multi_hop", {}, [unit("가"), unit("나")], True),
    ("multi_hop", {}, [unit("가")], False),
    ("numeric", {"value": "5"}, [unit("5%")], False),
])
def test_each_topic_requires_its_structure(topic, structure, cited, ok):
    row = {"answer": "A안은 1억원, 5% 이고 우편 접수는 받지 않는다", "structure": structure}
    reason = check_structure(topic, topic_spec(topic)[0], row, cited)
    assert (reason is None) == ok, reason


BUDGETS = {"A안": "1억원", "B안": "2억원"}


@pytest.mark.parametrize("structure, answer, ok", [
    ({"entities": ["A안", "B안"], "values": BUDGETS, "choice": "B안"}, "A안 1억원, B안 2억원. 답: B안", True),
    # 고르지 않는 비교는 값을 나란히 조회할 뿐이라 comparison 이 아니다.
    ({"entities": ["A안", "B안"], "values": BUDGETS, "choice": None}, "A안 1억원, B안 2억원", False),
    ({"entities": ["A안", "B안"], "values": BUDGETS, "choice": "B안"}, "A안 1억원, B안 2억원으로 A안이 더 많다", False),
    ({"entities": ["A안", "B안"], "values": BUDGETS, "choice": "C안"}, "A안 1억원, B안 2억원. 답: C안", False),
    ({"entities": ["A안", "B안"], "values": {"A안": "1억원"}, "choice": None}, "A안 1억원", False),
    ({"entities": ["A안", "B안"], "values": {"A안": "3억원", "B안": "2억원"}, "choice": None}, "A안 3억원, B안 2억원", False),
    ({"entities": ["A안"], "values": {"A안": "1억원"}, "choice": None}, "A안 1억원", False),
    # 값이 대상 이름이면 견줄 값이 없다.
    ({"entities": ["A안", "B안"], "values": {"A안": "A안", "B안": "B안"}, "choice": "B안"}, "A안 A안, B안 B안. 답: B안", False),
    ({"entities": ["A안", "B안"], "values": {"A안": "B안", "B안": "A안"}, "choice": "B안"}, "A안 B안, B안 A안. 답: B안", False),
    ({"entities": [{"name": "A안"}, {"name": "B안"}], "values": BUDGETS, "choice": None}, "A안 1억원, B안 2억원", False),
])
def test_comparison_answer_is_the_text_built_from_its_structure(structure, answer, ok):
    # 결론은 structure 의 choice 로 검증한다. 답 글이 structure 와 다른 결론을 쓰면 검증을 비켜 가므로 생성에서 막는다.
    cited = [unit("구분 | A안 | B안", "table"), unit("예산 | 1억원 | 2억원", "table")]
    reason = check_structure("comparison", topic_spec("comparison")[0], {"answer": answer, "structure": structure}, cited)
    assert (reason is None) == ok, reason


def test_b_prompt_hash_is_constant(planned):
    # B 가 실패 기록을 읽지 않는 것은 test_improvement 의 B · C 경로 테스트가 지킨다.
    clients = [Client(NUMERIC), Client(NUMERIC)]
    runs = [generate("B", "numeric", "p1", run_id, planned, c) for run_id, c in zip(("b1", "b2"), clients)]

    infos = [manifest(run_dir)["generation"] for run_dir in runs]
    assert infos[0]["prompt_sha256"] == infos[1]["prompt_sha256"] == storage._sha256(storage.PROMPTS / "B.txt")
    assert clients[0].requests == clients[1].requests

    a = manifest(generate("A", "numeric", "p1", "a1", planned, Client(NUMERIC)))["generation"]
    for name in ("model_requested", "plan_sha256", "v11_manifest_sha256", "topic_spec_sha256", "bundle_ids"):
        assert infos[0][name] == a[name]
    assert infos[0]["prompt_sha256"] != a["prompt_sha256"]


def test_model_call_cap_and_budget_are_required_with_no_default(planned):
    config = {key: value for key, value in CONFIG.items() if key != "budget_usd"}
    planned.write_text(json.dumps(config), encoding="utf-8")
    client = Client(NUMERIC)

    with pytest.raises(ValueError, match="run 설정"):
        generate("A", "numeric", "p1", "a1", planned, client)
    assert client.requests == []
    assert not (storage.OUTPUTS / "goldens").exists()


@pytest.mark.parametrize("limit, status", [({"max_calls": 1}, "call_cap"), ({"budget_usd": 0.001}, "budget")])
def test_call_cap_and_budget_stop_the_run(evidence_run, tmp_path, limit, status):
    make_plan("p2", "ev1", {"numeric": 2}, 2000, package=evidence_run)
    config = tmp_path / "run.json"
    config.write_text(json.dumps({**CONFIG, **limit}), encoding="utf-8")
    client = Client(NUMERIC, NUMERIC)

    info = manifest(generate("A", "numeric", "p2", "a1", config, client))["generation"]
    assert len(client.requests) == 1
    assert info["status"] == status
    assert len(info["bundle_ids"]) == len(info["calls"]) == 1


@pytest.mark.parametrize("run_id", ["a1", "a/b"])
def test_unwritable_run_id_stops_before_any_call(planned, run_id):
    generate("A", "numeric", "p1", "a1", planned, Client(NUMERIC))
    client = Client(NUMERIC)

    with pytest.raises((FileExistsError, storage.OutputPathError)):
        generate("A", "numeric", "p1", run_id, planned, client)
    assert client.requests == []


def test_output_citing_evidence_another_topic_owns_is_rejected_not_lost(planned, evidence_run):
    # p1 의 numeric 묶음(u1, u2)이 p2 에서는 multi_hop 묶음의 E1 · E2 다.
    two = {**NUMERIC, "evidence": ["E1", "E2"]}
    generate("A", "numeric", "p1", "a1", planned, Client(two))
    make_plan("p2", "ev1", {"multi_hop": 1}, 2000, package=evidence_run)

    run_dir = generate("A", "multi_hop", "p2", "a1", planned, Client({**two, "structure": {}}))

    assert read_jsonl(run_dir / "candidates.jsonl") == []
    [reject] = read_jsonl(run_dir / "rejected.jsonl")
    assert reject["reason"] == "근거 묶음이 이미 numeric 주제 소유입니다"
    assert len(manifest(run_dir)["generation"]["calls"]) == 1


def test_topic_spec_changed_after_planning_stops_before_any_call(planned):
    spec = storage.CONFIGS / "topics" / "numeric.json"
    spec.write_text(spec.read_text(encoding="utf-8").replace('"version": 1', '"version": 2'), encoding="utf-8")
    client = Client(NUMERIC)

    with pytest.raises(ValueError, match="주제 명세"):
        generate("A", "numeric", "p1", "a1", planned, client)
    assert client.requests == []


def test_c_rows_pass_the_same_checks_and_unobserved_fields_stay_unobserved(planned, tmp_path):
    numeric = bundle("numeric")["bundle_id"]
    rows = [
        {**NUMERIC, "bundle_id": numeric},
        "{not json",
        {**NUMERIC, "bundle_id": bundle("table")["bundle_id"]},
        {**NUMERIC, "bundle_id": numeric, "question": ""},
        {**NUMERIC, "bundle_id": numeric, "answer": "예산은 규모에 따라 다르다"},
        {**NUMERIC, "bundle_id": numeric, "evidence": ["E9"]},
        {"bundle_id": numeric, "question": "필드가 모자란 행"},
        {**NUMERIC, "bundle_id": [numeric]},
    ]
    exports = [tmp_path / "c1.jsonl", tmp_path / "c2.jsonl"]
    lines = [r if isinstance(r, str) else json.dumps(r, ensure_ascii=False) for r in rows]
    exports[0].write_text("\n".join(lines[:3]) + "\n", encoding="utf-8")
    exports[1].write_text("\n".join(lines[3:]) + "\n", encoding="utf-8")
    sidecar = tmp_path / "sidecar.json"
    sidecar.write_text(json.dumps({"run_date": "2026-10-20", "provided_files": ["p1.json"], "tool_use": None}),
                       encoding="utf-8")

    run_dir = import_c("numeric", "p1", "c1", exports, sidecar)

    [item] = read_jsonl(run_dir / "candidates.jsonl")
    assert (item["method"], item["state"], item["prompt_version"]) == ("C", "candidate", UNOBSERVED)
    assert item["context"] == bundle("numeric")["context"]
    reasons = [reject["reason"] for reject in read_jsonl(run_dir / "rejected.jsonl")]
    expected_reasons = ["JSON", "계획에 없는", "스키마: question", "유형 불일치", "evidence", "출력 필드", "계획에 없는"]
    assert len(reasons) == len(expected_reasons)
    for expected, reason in zip(expected_reasons, reasons):
        assert reason.startswith(expected), reason

    info = manifest(run_dir)["generation"]
    assert info["model"] == {"observed_label": UNOBSERVED}
    assert "model_reported" not in info and "model_requested" not in info
    assert info["observed"] == {
        "model_label": UNOBSERVED, "run_date": "2026-10-20", "provided_files": ["p1.json"],
        "tool_use": UNOBSERVED, "input_limits": UNOBSERVED,
    }
    assert info["input_limits"] == UNOBSERVED
    assert info["exports"] == [{"file": path.name, "sha256": storage._sha256(path)} for path in exports]


def test_c_sidecar_with_an_unknown_field_is_refused(planned, tmp_path):
    export = tmp_path / "c1.jsonl"
    export.write_text(json.dumps({**NUMERIC, "bundle_id": bundle("numeric")["bundle_id"]}) + "\n", encoding="utf-8")
    sidecar = tmp_path / "sidecar.json"
    sidecar.write_text(json.dumps({"api_model": "gpt-test"}), encoding="utf-8")

    with pytest.raises(ValueError, match="sidecar"):
        import_c("numeric", "p1", "c1", [export], sidecar)
    assert not (storage.OUTPUTS / "goldens").exists()


REFUSAL = "제공된 문서에서 확인할 수 없습니다."
DUE = "하자 보수 기간은 계약 종료 후 1년 이내로 한다."


@pytest.mark.parametrize("question, answer, structure, ok", [
    ("하자 보수 기간은 얼마인가?", REFUSAL, {"attribute": "하자 보수 기간", "key_terms": ["하자"]}, True),
    # 답이 거절 문장이 아니면 ④ 생성의 거절과 견줄 수 없다.
    ("하자 보수 기간은 얼마인가?", "1년 이내", {"attribute": "하자 보수 기간", "key_terms": ["하자"]}, False),
    # 빌린 속성은 근거에 적혀 있어야 한다.
    ("드론 해상도는?", REFUSAL, {"attribute": "드론 해상도", "key_terms": ["드론"]}, False),
    # 핵심어는 속성의 낱말이고 질문에도 있어야 한다. 아니면 문서 검사가 엉뚱한 낱말을 찾는다.
    ("하자 보수 기간은 얼마인가?", REFUSAL, {"attribute": "하자 보수 기간", "key_terms": ["입찰"]}, False),
    ("보수 기간은 얼마인가?", REFUSAL, {"attribute": "하자 보수 기간", "key_terms": ["하자"]}, False),
    ("하자 보수 기간은 얼마인가?", REFUSAL, {"attribute": "하자 보수 기간", "key_terms": ["하자 보수"]}, False),
])
def test_unanswerable_borrows_an_attribute_from_its_evidence_and_answers_with_the_refusal(question, answer, structure, ok):
    row = {"question": question, "answer": answer, "structure": structure}
    reason = check_structure("unanswerable", topic_spec("unanswerable")[0], row, [unit(DUE)])
    assert (reason is None) == ok, reason


BUDGET = "사업 예산은 130,000,000원(부가세 포함)이며 계약 기간은 12개월이다."


@pytest.mark.parametrize("question, answer, stated, actual, ok", [
    ("계약 기간 9개월은 언제 끝나나?", "계약 기간은 9개월이 아니라 12개월이다.", "9개월", "12개월", True),
    # actual 은 근거에 수 · 단위째 그대로 있어야 한다. 130,000,000원 안의 30,000,000원 은 근거의 값이 아니다.
    ("사업 예산 20,000,000원은 부가세를 포함하나?", "예산은 30,000,000원이다.", "20,000,000원", "30,000,000원", False),
    ("계약 기간 9개는 언제 끝나나?", "계약 기간은 9개가 아니라 12개다.", "9개", "12개", False),
    # 단위가 다르면 같은 값일 수 있다 (1년 = 12개월).
    ("계약 기간 1년은 언제 끝나나?", "계약 기간은 12개월이다.", "1년", "12개월", False),
    ("계약 기간 9개월, 즉 12개월은?", "12개월이다.", "9개월", "12개월", False),
    ("계약 기간 9개월은 언제 끝나나?", "9개월이 아니다.", "9개월", "12개월", False),
    # 금액 · 기간 · 개수 · 날짜만 전제로 쓴다.
    ("낙찰 하한율 3%는?", "5%이다.", "3%", "5%", False),
])
def test_false_premise_states_a_value_the_evidence_corrects(question, answer, stated, actual, ok):
    row = {"question": question, "answer": answer, "structure": {"stated": stated, "actual": actual}}
    reason = check_structure("false_premise", topic_spec("false_premise")[0], row, [unit(BUDGET)])
    assert (reason is None) == ok, reason
