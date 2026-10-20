"""칸 비교 규칙은 단일 요구사항과 생성 때 고정한 패키지에서도 같게 적용한다. API 호출은 없다."""
import json

import pytest

from golden_pipeline import evidence, generation, plan, storage, validation
from golden_pipeline.state import transition
from conftest import DOC_1, _write_jsonl


def write_json(path, value):
    path.write_text(json.dumps(value, ensure_ascii=False), encoding="utf-8")


@pytest.fixture
def field_run(evidence_run, make_item, tmp_path, request):
    split_rows = getattr(request, "param", "same_row") == "split_rows"
    text = ("고유번호 | QUR-001\n분류 | 기능 요구사항\n응낙수준 | 필수" if split_rows
            else "고유번호 | QUR-001 | 분류 | 기능 요구사항") + "\n실명 인증 | 3초\n로그인 | 1초"
    _write_jsonl(evidence_run / evidence.CHUNKS, [
        {"doc_id": DOC_1, "requirement_ids": ["QUR-001"], "body": text},
    ])
    ev_dir = storage.OUTPUTS / "evidence/ev1"
    write_json(ev_dir / "manifest.json", {
        "pinned_sha256": {name: storage._sha256(evidence_run / name) for name in evidence.PINNED},
    })
    entities = ["분류", "응낙수준"] if split_rows else ["고유번호", "분류"]
    values = {"고유번호": "QUR-001", "분류": "기능 요구사항", "응낙수준": "필수"}
    structure = {"entities": entities, "values": {name: values[name] for name in entities}, "choice": entities[-1]}
    item = make_item(candidate_id="comparison-C-c1-0001", primary_topic="comparison", secondary_tags=[],
                     method="C", run_id="c1", structure=structure, answer=generation.comparison_answer(structure))
    item["evidence"] = [{**item["evidence"][0], "doc_sha": DOC_1, "requirement_ids": ["QUR-001"]}]
    unit = {"unit_id": "u1", "ref": item["evidence"][0], "text": text, "titled": False}
    bundle = plan._bundle("comparison", [unit], {"agency": "가기관", "title": "가사업 구축"})
    item.update(bundle_id=bundle["bundle_id"], context=bundle["context"])
    planned = {"evidence_run": "ev1", "topic_specs": {"comparison": plan.topic_spec("comparison")[1]}, "bundles": [bundle]}
    path = storage.OUTPUTS / "plans/p-fields.json"
    path.parent.mkdir()
    write_json(path, planned)
    run_dir = storage.write_run("comparison", "C", "c1", [item],
                                info={"plan_id": "p-fields", "plan_sha256": storage._sha256(path)})
    config = tmp_path / "validator.json"
    write_json(config, {"model": "test", "reasoning_effort": "low", "max_calls": 2, "budget_usd": 1,
                        "usd_per_million_input_tokens": 1, "usd_per_million_output_tokens": 1})
    return item, validation.evidence_units(item, bundle), config, run_dir


@pytest.mark.parametrize("field_run", ["same_row", "split_rows"], indirect=True)
def test_single_requirement_detail_entities_are_not_fields(field_run):
    item, units, _, _ = field_run
    item["structure"] = {"entities": ["실명 인증", "로그인"], "values": {"실명 인증": "3초", "로그인": "1초"}, "choice": "로그인"}
    assert validation.rule_reason(item, units) is None


@pytest.mark.parametrize("field_run", ["same_row", "split_rows"], indirect=True)
@pytest.mark.parametrize("stage", ["validate", "release", "rename"])
def test_single_requirement_fields_are_rejected_without_calls_in_every_consumer(field_run, stage):
    item, _, config, run_dir = field_run
    if stage != "validate":
        accepted = transition(item, "auto_validated", "이전 검증 통과", validator_version="validation-8", difficulty="easy")
        storage.write_validation("comparison", "C", "c1", [accepted], {"pending": [], "calls": []})
        if stage == "rename":
            storage.write_release("comparison", "v1", [transition(accepted, "released", "출시")], [("C", "c1")])

    def no_calls(**kwargs):
        raise AssertionError("칸 비교는 유료 호출 없이 거절해야 합니다")

    if stage == "validate":
        validation.validate("comparison", "C", "c1", config, no_calls)
        [rejected] = storage._read_jsonl(run_dir / "rejected.jsonl")
        assert rejected["state_history"][-1]["reason"].startswith("칸 비교")
        assert storage._read_jsonl(run_dir / "accepted.jsonl") == []
    else:
        released = (validation.release("comparison", "v2", [("C", "c1")], config, no_calls) if stage == "release"
                    else validation.rename("comparison", "v2", ["v1"]))
        assert storage._read_jsonl(released / "golden.jsonl") == []
        [dropped] = storage._read_json(released / "manifest.json")["release"]["dropped"]
        assert dropped["reason"].startswith("칸 비교")


@pytest.mark.parametrize("stage", ["validate", "release", "rename"])
@pytest.mark.parametrize("change", ["body", "requirement_ids"])
def test_changed_package_stops_comparison_rules_before_any_writes_or_calls(field_run, evidence_run, stage, change):
    item, units, config, run_dir = field_run
    if stage != "validate":
        accepted = transition(item, "auto_validated", "이전 검증 통과", validator_version="validation-7", difficulty="easy")
        storage.write_validation("comparison", "C", "c1", [accepted], {"pending": [], "calls": []})
        if stage == "rename":
            storage.write_release("comparison", "v1", [transition(accepted, "released", "출시")], [("C", "c1")])
    # 캐시를 채운 뒤 같은 경로의 파생 패키지를 바꿔도 고정 해시를 다시 확인해야 한다.
    validation.rule_reason(item, units)
    before = storage.snapshot(storage.OUTPUTS)
    [chunk] = storage._read_jsonl(evidence_run / evidence.CHUNKS)
    chunk[change] = "다른 본문" if change == "body" else []
    _write_jsonl(evidence_run / evidence.CHUNKS, [chunk])

    def no_calls(**kwargs):
        raise AssertionError("패키지가 바뀌면 호출 전에 멈춰야 합니다")

    with pytest.raises(evidence.PackageMismatch, match="corpus/chunks.jsonl SHA-256"):
        if stage == "validate":
            validation.validate("comparison", "C", "c1", config, no_calls)
        elif stage == "release":
            validation.release("comparison", "v2", [("C", "c1")], config, no_calls)
        else:
            validation.rename("comparison", "v2", ["v1"])
    assert storage.snapshot(storage.OUTPUTS) == before
    assert json.loads((run_dir / "manifest.json").read_text(encoding="utf-8"))["generation"]["plan_sha256"] == plan.load_plan("p-fields")[1]
