"""칸 비교 규칙은 단일 요구사항과 생성 때 고정한 패키지에서도 같게 적용한다. API 호출은 없다."""
import json

import pytest

from golden_pipeline import evidence, generation, improvement, plan, storage, validation
from golden_pipeline.state import transition
from conftest import DOC_1, _write_jsonl


FIELD_CASES = ["same_row", "split_rows", "research_name", "research_description", "research_note", "repository_fields", "arbitrary_fields"]


def write_json(path, value):
    path.write_text(json.dumps(value, ensure_ascii=False), encoding="utf-8")


@pytest.fixture
def field_run(evidence_run, make_item, tmp_path, request):
    case = getattr(request, "param", "same_row")
    entities = {
        "same_row": ["고유번호", "분류"], "split_rows": ["분류", "응낙수준"],
        "research_name": ["요구사항명", "수용여부"], "research_description": ["상세설명", "제약사항"],
        "research_note": ["비고", "수용여부"],
        "repository_fields": ["요구분류", "결과물"],
        "arbitrary_fields": ["속성-X", "속성-Y"],
    }.get(case, ["요구분류", "결과물"])
    values = {"고유번호": "QUR-001", "분류": "기능 요구사항", "응낙수준": "필수", "요구사항명": "본인 인증",
              "수용여부": "필수", "상세설명": "두 단계 인증", "제약사항": "외부망 차단", "비고": "별도 협의",
              "요구분류": "처리", "결과물": "합성 보고문", "속성-X": "합성 분류", "속성-Y": "합성 기준"}
    names = entities if case == "same_row" else ["고유번호", *entities]
    separator = " | " if case == "same_row" else "\n"
    text = separator.join(f"{name} | {values[name]}" for name in names) + "\n실명 인증 | 3초\n로그인 | 1초"
    roles = {"fields": names, "entities": ["실명 인증", "로그인"]}
    if case in ("partial_roles", "declared_entities"):
        roles = {"fields": ["고유번호"], "entities": entities if case == "declared_entities" else []}
    chunk = {"chunk_id": "c-fields", "doc_id": DOC_1, "source_sha256": DOC_1, "body": text,
             "requirement_ids": ["QUR-001"], "spans": [{"element_id": "e-fields", "rows": [0, 2]}],
             "source_locations": [{"element_id": "e-fields", "location": {"record_id": "r-fields", "supplier_metadata": {
                 "sha256": DOC_1, "review_status": "자동 검사 완료", "exception_kinds": []}}}], "image_source": None, "page": 1}
    if case != "missing_roles":
        chunk["roles"] = roles
    _write_jsonl(evidence_run / evidence.CHUNKS, [chunk])
    write_json(evidence_run / "manifest.json", {
        "counts": {"v12_search_chunks": 1, "v12_documents": 2},
        "files": {name: {"sha256": storage._sha256(evidence_run / name)} for name in evidence.PINNED[1:]},
    })
    ev_dir = evidence.run("ev-roles", package=evidence_run)
    structure = {"entities": entities, "values": {name: values[name] for name in entities}, "choice": entities[-1]}
    if case == "detail_entities":
        structure = {"entities": ["실명 인증", "로그인"], "values": {"실명 인증": "3초", "로그인": "1초"}, "choice": "로그인"}
    item = make_item(candidate_id="comparison-C-c1-0001", primary_topic="comparison", secondary_tags=[],
                     method="C", run_id="c1", structure=structure, answer=generation.comparison_answer(structure))
    [unit] = plan.eligible_units(ev_dir)
    item["evidence"] = [unit["ref"]]
    bundle = plan._bundle("comparison", [unit], {"agency": "가기관", "title": "가사업 구축"})
    item.update(bundle_id=bundle["bundle_id"], context=bundle["context"])
    path = storage.OUTPUTS / "plans/p-fields.json"
    if case == "missing_roles":
        # New plans exclude unannotated requirements; only this case models a legacy plan.
        path.parent.mkdir()
        write_json(path, {"evidence_run": "ev-roles", "topic_specs": {"comparison": plan.topic_spec("comparison")[1]}, "bundles": [bundle]})
    else:
        spec_path = storage.CONFIGS / "topics/comparison.json"
        write_json(spec_path, {**plan.topic_spec("comparison")[0], "bundle_units": 1})
        plan.make_plan("p-fields", "ev-roles", {"comparison": 1}, 2000, package=evidence_run)
    run_dir = storage.write_run("comparison", "C", "c1", [item],
                                info={"plan_id": "p-fields", "plan_sha256": storage._sha256(path)})
    config = tmp_path / "validator.json"
    write_json(config, {"model": "test", "reasoning_effort": "low", "max_calls": 2, "budget_usd": 1,
                        "usd_per_million_input_tokens": 1, "usd_per_million_output_tokens": 1})
    return item, validation.evidence_units(item, bundle), config, run_dir


def previously_accepted(item, stage):
    if stage == "validate":
        return
    accepted = transition(item, "auto_validated", "이전 검증 통과", validator_version="validation-10", difficulty="easy")
    storage.write_validation("comparison", "C", "c1", [accepted], {"pending": [], "calls": []})
    if stage == "rename":
        storage.write_release("comparison", "v1", [transition(accepted, "released", "출시")], [("C", "c1")])


@pytest.mark.parametrize("field_run", ["declared_entities", "detail_entities"], indirect=True)
@pytest.mark.parametrize("stage", ["validate", "release", "rename"])
def test_explicit_entities_can_pass_validation_release_and_rename(field_run, stage):
    item, _, config, run_dir = field_run
    previously_accepted(item, stage)
    calls = []

    def client(**kwargs):
        calls.append(kwargs)
        result = ({"answerable": True, "answer": item["answer"], "conditions": [], "conflict": False,
                   "comparison": {"values": item["structure"]["values"], "choice": item["structure"]["choice"]}}
                  if stage == "validate" else {"useful": True, "code": None, "reason": "같은 종류의 대상을 비교한다"})
        return {"model": "test", "text": json.dumps(result, ensure_ascii=False), "input_tokens": 1, "output_tokens": 1}

    if stage == "validate":
        validation.validate("comparison", "C", "c1", config, client)
        [accepted] = storage._read_jsonl(run_dir / "accepted.jsonl")
        assert accepted["candidate_id"] == item["candidate_id"]
    else:
        released = (validation.release("comparison", "v2", [("C", "c1")], config, client) if stage == "release"
                    else validation.rename("comparison", "v2", ["v1"]))
        assert [row["candidate_id"] for row in storage._read_jsonl(released / "golden.jsonl")] == [item["candidate_id"]]
    assert len(calls) == (0 if stage == "rename" else 1)


@pytest.mark.parametrize("field_run", [*FIELD_CASES, "missing_roles", "partial_roles"], indirect=True)
@pytest.mark.parametrize("stage", ["validate", "release", "rename"])
def test_single_requirement_fields_are_rejected_without_calls_in_every_consumer(field_run, stage, request):
    item, _, config, run_dir = field_run
    previously_accepted(item, stage)

    def no_calls(**kwargs):
        raise AssertionError("칸 비교는 유료 호출 없이 거절해야 합니다")

    reason = "비교 역할 미확정" if request.node.callspec.params["field_run"] in ("missing_roles", "partial_roles") else "칸 비교"
    if stage == "validate":
        validation.validate("comparison", "C", "c1", config, no_calls)
        [rejected] = storage._read_jsonl(run_dir / "rejected.jsonl")
        actual_reason = rejected["state_history"][-1]["reason"]
        assert storage._read_jsonl(run_dir / "accepted.jsonl") == []
    else:
        released = (validation.release("comparison", "v2", [("C", "c1")], config, no_calls) if stage == "release"
                    else validation.rename("comparison", "v2", ["v1"]))
        assert storage._read_jsonl(released / "golden.jsonl") == []
        [dropped] = storage._read_json(released / "manifest.json")["release"]["dropped"]
        actual_reason = dropped["reason"]
    assert actual_reason.startswith(reason)
    assert improvement.failure_code(actual_reason) == "invalid_comparison"


@pytest.mark.parametrize("stage", ["validate", "release", "rename"])
@pytest.mark.parametrize("change", ["body", "requirement_ids", "roles"])
def test_changed_package_stops_comparison_rules_before_any_writes_or_calls(field_run, evidence_run, stage, change):
    item, units, config, run_dir = field_run
    previously_accepted(item, stage)
    # 캐시를 채운 뒤 같은 경로의 파생 패키지를 바꿔도 고정 해시를 다시 확인해야 한다.
    validation.rule_reason(item, units)
    before = storage.snapshot(storage.OUTPUTS)
    [chunk] = storage._read_jsonl(evidence_run / evidence.CHUNKS)
    chunk[change] = {"body": "다른 본문", "requirement_ids": [], "roles": {"fields": [], "entities": ["고유번호", "분류"]}}[change]
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


@pytest.mark.parametrize("stage", ["validate", "release", "rename"])
def test_plan_roles_cannot_override_the_pinned_source(field_run, stage):
    item, _, config, run_dir = field_run
    previously_accepted(item, stage)
    path = storage.OUTPUTS / "plans/p-fields.json"
    planned = storage._read_json(path)
    planned["bundles"][0]["units"][0]["roles"] = {"fields": [], "entities": item["structure"]["entities"]}
    write_json(path, planned)
    manifest = storage._read_json(run_dir / "manifest.json")
    manifest["generation"]["plan_sha256"] = storage._sha256(path)
    write_json(run_dir / "manifest.json", manifest)
    before = storage.snapshot(storage.OUTPUTS)

    def no_calls(**kwargs):
        raise AssertionError("원문과 다른 역할은 호출 전에 막아야 합니다")

    with pytest.raises(evidence.PackageMismatch, match="roles.*고정 원문"):
        if stage == "validate":
            validation.validate("comparison", "C", "c1", config, no_calls)
        elif stage == "release":
            validation.release("comparison", "v2", [("C", "c1")], config, no_calls)
        else:
            validation.rename("comparison", "v2", ["v1"])
    assert storage.snapshot(storage.OUTPUTS) == before


@pytest.mark.parametrize("field_run", ["missing_roles"], indirect=True)
def test_new_comparison_plans_exclude_unannotated_requirement_chunks(field_run, evidence_run):
    spec_path = storage.CONFIGS / "topics/comparison.json"
    write_json(spec_path, {**plan.topic_spec("comparison")[0], "bundle_units": 1})
    path = plan.make_plan("new", "ev-roles", {"comparison": 1}, 2000, package=evidence_run)
    assert storage._read_json(path)["planned"]["comparison"] == 0


def test_new_plans_refuse_roles_changed_in_adapter_output(field_run, evidence_run):
    path = storage.OUTPUTS / "evidence/ev-roles/units.jsonl"
    [unit] = storage._read_jsonl(path)
    unit["roles"] = {"fields": [], "entities": ["고유번호", "분류"]}
    _write_jsonl(path, [unit])
    with pytest.raises(evidence.PackageMismatch, match="roles.*고정 원문"):
        plan.make_plan("new", "ev-roles", {"comparison": 1}, 2000, package=evidence_run)
    assert not (storage.OUTPUTS / "plans/new.json").exists()
