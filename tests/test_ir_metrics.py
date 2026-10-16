"""검색 순위·컨텍스트·라벨 누락을 유료 호출 없이 확인한다."""
import math
from unittest.mock import MagicMock

import pandas as pd
import pytest

from rag.config import read_jsonl, write_jsonl
from rag.evaluation import evaluation
from rag.evaluation.ir import (component_table, coverage_table, evidence_coverage, exclusion_report,
                               ir_scores, mrr_at_k, recall_at_k)
from rag.generation import generation
from test_retrieval import make_index
from test_usage import _answer_row


@pytest.mark.parametrize("k,recall,mrr", [(1, 0, 0), (2, 0.5, 0.5), (5, 1, 0.5)])
def test_ranking_counts_gold_set_but_keeps_chunk_positions(k, recall, mrr):
    ranking = ["other", "a", "a", "b", "other"]
    assert recall_at_k(ranking, {"a", "b"}, k) == recall
    assert mrr_at_k(ranking, {"a", "b"}, k) == mrr
    assert mrr_at_k(ranking, {"absent"}, k) == 0


@pytest.mark.parametrize("sent,coverage,full", [([], 0, 0), (["a", "a"], 0.5, 0), (["b", "a", "other"], 1, 1)])
def test_evidence_coverage_requires_every_gold_chunk(sent, coverage, full):
    assert evidence_coverage(sent, {"a", "b"}) == {"evidence_coverage": coverage, "full_evidence_coverage": full}


def _component_row():
    candidates = [{"chunk_id": f"c{i}", "doc_id": "gold-a" if i in (2, 3) else "other",
                   "fused_rank": i, "dense_rank": 7 - i, "dense_score": i / 10,
                   "bm25_rank": i if i != 6 else None, "bm25_score": 7 - i if i != 6 else None,
                   "exact_code_match": i == 6} for i in range(1, 7)]
    candidates[-1]["doc_id"] = "gold-b"
    return {**_answer_row(), "primary_topic": "multi_hop", "ranked_candidates": candidates,
            "evidence": [{"chunk_id": "c2", "doc_id": "gold-a"}, {"chunk_id": "c6", "doc_id": "gold-b"}],
            "context_chunk_ids": ["c6"]}


def test_component_split_keeps_ranked_chunks_and_measures_context_separately():
    scores = ir_scores(_component_row())
    assert scores["doc_fused_recall_at_5"] == scores["chunk_fused_recall_at_5"] == 0.5
    assert scores["doc_dense_recall_at_5"] == scores["chunk_dense_recall_at_5"] == 1
    assert scores["doc_bm25_recall_at_20"] == scores["chunk_bm25_recall_at_20"] == 0.5
    assert scores["doc_exact_code_recall"] == scores["chunk_exact_code_recall"] == 0.5
    assert scores["doc_mrr_at_5"] == scores["chunk_mrr_at_5"] == 0.5
    assert scores["chunk_fused_recall_at_10"] == scores["chunk_fused_recall_at_20"] == 1
    assert scores["evidence_coverage"] == 0.5
    assert scores["full_evidence_coverage"] == 0
    late = {**_component_row(), "evidence": [{"chunk_id": "c6", "doc_id": "gold-b"}]}
    assert ir_scores(late)["chunk_mrr_at_5"] == ir_scores(late)["doc_mrr_at_5"] == 0
    assert ir_scores(late)["chunk_mrr_at_10"] == pytest.approx(1 / 6)


def test_mapping_exclusions_and_coverage_groups_survive_csv_without_api(monkeypatch, tmp_path):
    monkeypatch.setattr(evaluation, "_ragas", MagicMock(side_effect=AssertionError("유료 호출")))
    full = _component_row()
    partial = {**full, "id": "partial", "evidence": [full["evidence"][0], {"doc_id": "gold-b", "chunk_id": None}]}
    unlabelled = {**full, "id": "none", "evidence": [{"doc_id": "gold-a", "chunk_id": None}]}
    unmapped = {**full, "id": "unmapped", "evidence": [{"doc_id": None, "chunk_id": None}]}
    refusal = {**full, "id": "refusal", "answerable": False}
    yaml = {**full, "id": "yaml", "primary_topic": None, "evidence": []}
    single = {**_answer_row(), "id": "single"}
    rows = [full, partial, unlabelled, unmapped, refusal, yaml, single]
    answers = tmp_path / "answers.jsonl"
    write_jsonl(rows, answers)

    table = evaluation.evaluate_retrieval(answers, {})
    by_id = table.set_index("id")
    assert by_id.loc["partial", "doc_fused_recall_at_5"] == 0.5
    assert math.isnan(by_id.loc["partial", "chunk_fused_recall_at_5"])
    assert math.isnan(by_id.loc["partial", "evidence_coverage"])
    for item_id in ("none", "unmapped", "refusal", "yaml"):
        assert math.isnan(by_id.loc[item_id, "chunk_mrr_at_5"])
    report = exclusion_report(rows).set_index(["primary_topic", "level"])
    chunk = report.loc[("ALL", "chunk")]
    assert [chunk[s] for s in ("fully_labelled", "partly_labelled", "unlabelled", "unanswerable", "no_golden_evidence")] == [2, 1, 2, 1, 1]
    assert chunk["mapping_exclusion_rate"] == 3 / 5
    assert report.loc[("multi_hop", "chunk"), "partly_labelled"] == 1
    components = component_table(table, "chunk").set_index("component")
    assert components.loc["fused", "Recall@5"] == 0.75
    assert components.loc["fused", "mapping_exclusion_rate"] == 3 / 5
    assert components.loc["exact_code_membership", "Recall (membership)"] == 0.25
    coverage = coverage_table(table)
    assert coverage.loc["multi_evidence", "scored_questions"] == 1
    assert coverage.loc["single_evidence", "full_evidence_coverage"] == 1
    assert (tmp_path / "retrieval_exclusions.csv").is_file()
    assert "retrieval_settings" in pd.read_csv(tmp_path / "retrieval.csv")
    assert not (tmp_path / "api_usage.csv").exists()


def test_rerun_uses_stored_rewrite_and_changed_settings_without_any_llm(monkeypatch, tmp_path):
    fail = MagicMock(side_effect=AssertionError("유료 호출"))
    monkeypatch.setattr(generation, "rewrite_question", fail)
    monkeypatch.setattr(generation, "generate", fail)
    monkeypatch.setattr(evaluation, "_ragas", fail)
    index = make_index(["새 근거", "긴 근거"], [2, 10], budget=3)
    for c in index.chunks:
        c.update(source="문서.pdf", page=1)
    index._dense = MagicMock(return_value={0: 0.8, 1: 0.2})
    index._sparse = MagicMock(return_value={1: 2.0})
    answers, output = tmp_path / "answers.jsonl", tmp_path / "rerun" / "answers.jsonl"
    write_jsonl([_answer_row()], answers)

    [row] = evaluation.rerun_retrieval(answers, output, index)
    assert row == read_jsonl(output)[0]
    assert read_jsonl(answers) == [_answer_row()]
    index.router.route.assert_called_once_with("재작성 질문")
    assert index._dense.call_args.args[0] == "재작성 질문"
    assert row["context_chunk_ids"] == ["c0"]
    assert len(row["ranked_candidates"]) == 2
    assert row["retrieval_settings"] == {**index.rcfg, "chunk_file": index.chunk_file,
                                         "k_values": [5, 10, 20], "stored_rewrites_reused": True}
    assert row["answer"] == "근거"
    evaluation.evaluate_retrieval(output, {})
    fail.assert_not_called()
    assert not (tmp_path / "api_usage.csv").exists()
