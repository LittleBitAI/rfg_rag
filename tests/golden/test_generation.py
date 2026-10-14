"""후보 생성: A · B 는 가짜 클라이언트로, C 는 내보낸 파일로 같은 출력 계약 검사와 저장을 거친다. API 호출은 없다."""
import json
from pathlib import Path

import pytest

from golden_pipeline import storage
from golden_pipeline.generation import UNOBSERVED, check_structure, generate, import_c
from golden_pipeline.plan import load_plan, make_plan, topic_spec

DOC_1 = "1" * 64
REPORTED = "gpt-test-2026-10-01"
CONFIG = {
    "model": "gpt-test", "max_calls": 10, "budget_usd": 1.0,
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

    def __call__(self, model, messages):
        self.requests.append({"model": model, "messages": messages})
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
    for name in ("accepted.jsonl", "review.jsonl", "rejected.jsonl"):
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
    ("예산은 999원이다", {"value": "999", "unit": "원"}),
])
def test_numeric_candidate_without_a_value_from_evidence_is_rejected_as_type_mismatch(planned, answer, structure):
    # 값 없이 설명만 하는 답이 numeric 후보로 남던 경우를 막는다. 근거에 없는 값도 같은 이유로 거절한다.
    run_dir = generate("A", "numeric", "p1", "a1", planned, Client({**NUMERIC, "answer": answer, "structure": structure}))

    assert read_jsonl(run_dir / "candidates.jsonl") == []
    [reject] = read_jsonl(run_dir / "rejected.jsonl")
    assert reject["reason"].startswith("유형 불일치")
    assert reject["bundle_id"] == bundle("numeric")["bundle_id"]


def unit(text, kind="char"):
    location = {"kind": "table", "row": 0} if kind == "table" else {"kind": "char"}
    return {"text": text, "ref": {"location": location}}


@pytest.mark.parametrize("topic, structure, cited, ok", [
    ("table", {"row": "예산", "column": "A안"}, [unit("구분 | A안", "table"), unit("예산 | 1억원", "table")], True),
    ("table", {"row": "예산", "column": "A안"}, [unit("구분 A안 예산 1억원")], False),
    ("table", {"row": "인력", "column": "A안"}, [unit("구분 | A안", "table")], False),
    ("condition", {"condition": "우편 접수는 받지 않는다"}, [unit("단, 우편 접수는 받지 않는다.")], True),
    ("condition", {"condition": "방문 접수만 받는다"}, [unit("단, 우편 접수는 받지 않는다.")], False),
    ("comparison", {"entities": ["A안", "B안"]}, [unit("구분 | A안 | B안")], True),
    ("comparison", {"entities": ["A안"]}, [unit("구분 | A안 | B안")], False),
    ("multi_hop", {}, [unit("가"), unit("나")], True),
    ("multi_hop", {}, [unit("가")], False),
    ("numeric", {"value": "5"}, [unit("5%")], False),
])
def test_each_topic_requires_its_structure(topic, structure, cited, ok):
    row = {"answer": "A안은 1억원, 5% 이고 우편 접수는 받지 않는다", "structure": structure}
    reason = check_structure(topic, topic_spec(topic)[0], row, cited)
    assert (reason is None) == ok, reason


def test_b_prompt_hash_is_constant_and_b_reads_no_failure_memory(planned, monkeypatch):
    memory = storage.OUTPUTS / "goldens" / "numeric" / "failure_memory"
    memory.mkdir(parents=True)
    (memory / "A_old.jsonl").write_text('{"reason": "MEMORY-MARKER"}\n', encoding="utf-8")
    reads = []
    real_open = Path.open

    def spy(path, mode="r", *args, **kwargs):
        if "r" in mode:
            reads.append(str(path))
        return real_open(path, mode, *args, **kwargs)

    clients = [Client(NUMERIC), Client(NUMERIC)]
    with monkeypatch.context() as patch:
        patch.setattr(Path, "open", spy)
        runs = [generate("B", "numeric", "p1", run_id, planned, c) for run_id, c in zip(("b1", "b2"), clients)]

    infos = [manifest(run_dir)["generation"] for run_dir in runs]
    assert infos[0]["prompt_sha256"] == infos[1]["prompt_sha256"] == storage._sha256(storage.PROMPTS / "B.txt")
    assert clients[0].requests == clients[1].requests
    assert "MEMORY-MARKER" not in json.dumps(clients[0].requests, ensure_ascii=False)
    assert reads and not [path for path in reads if "failure_memory" in path]

    a = manifest(generate("A", "numeric", "p1", "a1", planned, Client(NUMERIC)))["generation"]
    for name in ("model_requested", "plan_sha256", "v11_manifest_sha256", "topic_spec_sha256", "bundle_ids"):
        assert infos[0][name] == a[name]
    assert infos[0]["prompt_sha256"] != a["prompt_sha256"]


@pytest.mark.parametrize("name", ["model", "max_calls", "budget_usd"])
def test_model_call_cap_and_budget_are_required_with_no_default(planned, name):
    config = {key: value for key, value in CONFIG.items() if key != name}
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
