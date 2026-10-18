"""전체 dev의 빈 key_facts 보존, 정확 근거 복원과 유효 청크 그룹을 검사한다."""
import json

import pytest

from rag.retrieval.benchmark.full_dev import plan_evidence, reference_key, restore_row
from rag.retrieval.benchmark.prepare import evidence_groups


def test_empty_key_facts_does_not_drop_multi_hop_and_plan_ref_selects_the_exact_block(monkeypatch, tmp_path):
    from rag.retrieval.benchmark import full_dev

    monkeypatch.setattr(full_dev, "ROOT", tmp_path)
    folder = tmp_path / "golden_pipeline/outputs/plans"
    folder.mkdir(parents=True)
    ref = {"doc_sha": "doc", "chunk_id": "old", "element_id": "e", "location": {"start": 5, "end": 25}}
    text = "this is the second exact evidence block"
    source = {"bundle_id": "bundle", "evidence": [ref], "context": "[E1]\nunrelated\n\n[E2]\n" + text}
    plan = {"bundles": [{"bundle_id": "bundle", "units": [{"ref": ref, "text": text}]}]}
    (folder / "v11-saved.json").write_text(json.dumps(plan), encoding="utf-8")
    found = plan_evidence([source])
    item = {"id": "multi", "primary_topic": "multi_hop", "key_facts": [], "golden_evidence": [ref], "conv": None}
    restored = restore_row(item, source, found)
    assert restored["id"] == "multi" and restored["key_facts"] == []
    assert restored["evidence"][0]["text"] == text
    assert restored["evidence"][0]["context_labels"] == ["E2"]
    assert restored["evidence"][0]["golden_chunk_id"] == "old"
    assert "conv" not in restored and "golden_evidence" not in restored
    with pytest.raises(ValueError, match="블록"):
        restore_row(item, {**source, "context": "[E1]\nwrong text"}, found)
    with pytest.raises(AssertionError, match="exact saved plan reference"):
        plan_evidence([{**source, "evidence": [{**ref, "chunk_id": "different"}]}])


def test_conflicting_exact_plan_references_are_rejected(monkeypatch, tmp_path):
    from rag.retrieval.benchmark import full_dev

    monkeypatch.setattr(full_dev, "ROOT", tmp_path)
    folder = tmp_path / "golden_pipeline/outputs/plans"
    folder.mkdir(parents=True)
    source = {"bundle_id": "b", "evidence": [{"chunk_id": "c"}]}
    for name, text in (("a", "one"), ("b", "other")):
        plan = {"bundles": [{"bundle_id": "b", "units": [{"ref": {"chunk_id": "c"}, "text": text}]}]}
        (folder / f"{name}.json").write_text(json.dumps(plan), encoding="utf-8")
    with pytest.raises(AssertionError, match="Conflicting text"):
        plan_evidence([source])
    assert reference_key("b", {"a": 1, "b": 2}) == reference_key("b", {"b": 2, "a": 1})


def test_distinct_original_chunks_mapping_to_one_live_chunk_stay_in_one_group():
    rows = [{"id": str(i), "question": f"different question {i}", "evidence": [
        {"doc_sha": "doc", "golden_chunk_id": f"old-{i}", "chunk_id": "shared-current"}]} for i in range(2)]
    assert len(evidence_groups(rows)) == 1
