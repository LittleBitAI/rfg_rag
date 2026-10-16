"""저장 답변의 값 계약을 유료 평가 전에 검사하고 허용되는 빈 값은 보존한다."""
import re
from unittest.mock import MagicMock

import pytest

from rag.config import read_jsonl, write_jsonl
from rag.evaluation import evaluation
from test_usage import _answer_row


@pytest.mark.parametrize("name", ["retrieval", "generation", "grounding", "end_to_end", "rerun"])
@pytest.mark.parametrize("path,value", [
    ("id", None), ("question", 42), ("reference", {}), ("answer", []), ("answerable", 1),
    ("trace_id", 12), ("primary_topic", False), ("latency_s", None), ("latency_s", True),
    ("input_tokens", 1.5), ("output_tokens", None), ("cached_input_tokens", "0"), ("reasoning_tokens", True),
    ("cost_usd", None), ("cost_usd", "0.1"), ("cost_usd", False),
    ("cost_usd", float("nan")), ("cost_usd", float("inf")), ("cost_usd", float("-inf")),
    ("key_facts", "근거"), ("key_facts.0", 42), ("contexts", None), ("contexts.0", False),
    ("context_chunk_ids", {}), ("context_chunk_ids.0", None),
    ("rewrite", None), ("rewrite.question", None), ("rewrite.input_tokens", "20"),
    ("rewrite.output_tokens", 1.5), ("rewrite.cached_input_tokens", True), ("rewrite.reasoning_tokens", None),
    ("rewrite.cost_usd", None), ("rewrite.cost_usd", "0.1"), ("rewrite.cost_usd", False),
    ("rewrite.cost_usd", float("nan")), ("rewrite.cost_usd", float("inf")), ("rewrite.cost_usd", float("-inf")),
    ("retrieval_settings", None), ("retrieval_settings.dense_weight", "0.6"),
    ("retrieval_settings.candidate_k", 50.5), ("retrieval_settings.token_budget", True),
    ("retrieval_settings.chunk_file", None), ("retrieval_settings.k_values", "5,10,20"),
    ("retrieval_settings.k_values.0", True), ("retrieval_settings.stored_rewrites_reused", "false"),
    ("ranked_candidates", None), ("ranked_candidates.1", None),
    ("ranked_candidates.1.chunk_id", None), ("ranked_candidates.1.doc_id", []),
    ("ranked_candidates.1.fused_rank", None), ("ranked_candidates.1.dense_rank", "1"),
    ("ranked_candidates.1.bm25_rank", 1.5), ("ranked_candidates.1.dense_score", "0.7"),
    ("ranked_candidates.1.bm25_score", True), ("ranked_candidates.1.exact_code_match", 1),
    ("evidence", None), ("evidence.1", None), ("evidence.1.doc_id", {}), ("evidence.1.chunk_id", []),
])
def test_invalid_saved_values_stop_all_consumers_before_side_effects(monkeypatch, tmp_path, name, path, value):
    judge, publish, index = MagicMock(), MagicMock(), MagicMock()
    monkeypatch.setattr(evaluation, "_ragas", judge)
    monkeypatch.setattr(evaluation, "_send_scores", publish)
    row = _answer_row()
    row["ranked_candidates"].append(row["ranked_candidates"][0].copy())
    row["evidence"].append(row["evidence"][0].copy())
    record = row
    keys = [int(key) if key.isdecimal() else key for key in path.split(".")]
    for key in keys[:-1]:
        record = record[key]
    record[keys[-1]] = value
    answers, output = tmp_path / "answers.jsonl", tmp_path / "rerun.jsonl"
    write_jsonl([_answer_row(), row], answers)

    with pytest.raises(ValueError, match="03 → 02 설정 셀 → 04") as error:
        if name == "rerun":
            evaluation.rerun_retrieval(answers, output, index)
        else:
            getattr(evaluation, f"evaluate_{name}")(answers, {})

    field = re.sub(r"\.(\d+)", r"[\1]", path)
    assert f"row[2].{field}" in str(error.value)
    judge.assert_not_called()
    publish.assert_not_called()
    index.search_with_candidates.assert_not_called()
    assert not output.exists()
    assert not list(tmp_path.glob("*.csv"))


def test_valid_saved_values_preserve_nullability_metadata_and_end_to_end_cost(monkeypatch, tmp_path):
    rows = [_answer_row()]
    for cost in (0, 0.0):
        zero = _answer_row()
        for usage in (zero, zero["rewrite"]):
            usage.update(input_tokens=0, output_tokens=0, cached_input_tokens=0, reasoning_tokens=0, cost_usd=cost)
        zero.update(latency_s=0)
        rows.append(zero)
    nullable = _answer_row()
    nullable.update(trace_id=None, primary_topic=None, evidence=[{"doc_id": None, "chunk_id": None}])
    nullable["ranked_candidates"][0].update(dense_rank=None, dense_score=None, bm25_rank=None, bm25_score=None)
    rows.append(nullable)
    empty = {**_answer_row(), "evidence": [], "ranked_candidates": [], "contexts": [],
             "context_chunk_ids": [], "key_facts": []}
    rows.append(empty)
    metadata = {**_answer_row(), "model": "producer-model", "sources": ["문서.pdf"], "conv": None}
    metadata["rewrite"].update(model="rewrite-model", latency_s=0.5)
    metadata["evidence"][0].update(context_labels=["E1"], reason=None)
    rows.append(metadata)
    answers = tmp_path / "answers.jsonl"
    write_jsonl(rows, answers)
    judge = MagicMock(return_value=[{"factual_correctness(mode=f1)": 1.0}] * len(rows))
    monkeypatch.setattr(evaluation, "_ragas", judge)
    monkeypatch.setattr(evaluation, "_send_scores", MagicMock())

    assert evaluation._read_answers(answers) == read_jsonl(answers) == rows
    table = evaluation.evaluate_end_to_end(answers, {})

    assert table.columns.tolist() == [
        "id", "question", "factual_correctness", "latency_s", "input_tokens", "output_tokens", "cached_input_tokens",
        "reasoning_tokens", "rewrite_input_tokens", "rewrite_output_tokens", "rewrite_cached_input_tokens",
        "rewrite_reasoning_tokens", "answer_cost_usd", "rewrite_cost_usd", "cost_usd"]
    assert table.loc[0, "cost_usd"] == 0.000101
    assert table.loc[1:2, "cost_usd"].tolist() == [0, 0]
    assert table.loc[0, "answer_cost_usd"] == 0.000076
    assert table.loc[0, "rewrite_cost_usd"] == 0.000025
    assert judge.call_count == 1
