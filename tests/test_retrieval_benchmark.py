"""실험 통제와 동결된 그룹 분할을 API 없이 확인한다."""
import socket
from unittest.mock import MagicMock

import numpy as np
import pytest

from rag.retrieval.benchmark.common import MODEL_IGNORE_PATTERNS, no_network
from rag.retrieval.benchmark.embedding import LocalEmbedder, cosine_vectors
from rag.retrieval.benchmark.prepare import evidence_groups, grouped_split, remap
from rag.retrieval.benchmark.search import BenchmarkIndex
from test_retrieval import make_index


def test_duplicate_and_shared_evidence_groups_never_cross_partitions():
    def row(i, text, chunk, topic="numeric"):
        return {"id": str(i), "question": text, "primary_topic": topic,
                "evidence": [{"doc_sha": "doc", "golden_chunk_id": chunk}], "bundle_id": None}

    rows = [row(0, "same question", "a"), row(1, "same  question", "b"), row(2, "other", "b"),
            row(3, "different", "c"), row(4, "table", "d", "table")]
    groups = evidence_groups(rows)
    assert sorted(len(g) for g in groups) == [1, 1, 3]
    split = grouped_split(rows)
    assert split == grouped_split(rows)
    ids = split["ids"]
    assert set(ids["tuning"]).isdisjoint(ids["validation"])
    assert set(ids["tuning"] + ids["validation"]) == {str(i) for i in range(5)}
    assert any({"0", "1", "2"} <= set(partition) for partition in ids.values())


def test_remap_anchors_short_evidence_with_the_golden_context():
    anchor = "계약 담당 부서는 정보화사업팀이며 문의처를 함께 적습니다."
    chunks = [{"chunk_id": cid, "doc_id": "doc", "source_sha256": "doc", "body": body}
              for cid, body in (("a", anchor + " 180일"), ("b", "다른 사업 180일"))]
    rows = [{"id": "q", "evidence": [{"doc_sha": "doc", "text": "180일"}]}]
    dev = {"q": {"context": f"[E1]\n180일\n\n[E2]\n{anchor}", "bundle_id": None}}

    [row] = remap(rows, chunks, dev)

    assert (row["evidence"][0]["chunk_id"], row["evidence"][0]["reason"]) == ("a", None)


def test_int8_output_is_cast_before_cosine_normalization():
    raw = np.array([[127, -128, 2], [-2, 7, 5]], dtype=np.int8)
    result = cosine_vectors(raw)
    expected = raw.astype(np.float64)
    expected /= np.linalg.norm(expected, axis=1, keepdims=True)
    np.testing.assert_allclose(result, expected, rtol=1e-6)
    assert result.dtype == np.float32 and result.flags.c_contiguous


def test_offline_snapshot_checks_only_the_prepared_formats(monkeypatch):
    from rag.retrieval.benchmark import embedding

    download = MagicMock(return_value="local/snapshot")
    monkeypatch.setattr(embedding, "snapshot_download", download)
    assert embedding.snapshot({"id": "model", "revision": "pinned"}) == "local/snapshot"
    download.assert_called_once_with("model", revision="pinned", local_files_only=True,
                                     ignore_patterns=MODEL_IGNORE_PATTERNS)


def test_empty_quantity_phrase_is_not_encoded_and_keeps_its_slot():
    from rag.retrieval.benchmark.run import quantity_vectors

    embedder = MagicMock()
    embedder.spec = {"dimensions": 2}

    def encode(texts, progress):
        assert texts == ["budget", "duration"]
        return np.eye(2, dtype=np.float32)

    embedder.encode.side_effect = encode
    vectors = quantity_vectors(["budget", "", "duration"], embedder)
    np.testing.assert_array_equal(vectors, [[1, 0], [0, 0], [0, 1]])


def test_model_prompts_adapter_and_batch_one_are_forwarded():
    embedder = LocalEmbedder.__new__(LocalEmbedder)
    embedder.spec = {"task": "retrieval", "query_prompt": "query", "document_prompt": "document",
                     "dimensions": 2, "batch_size": 4}
    embedder.raw_dtypes = set()
    embedder.model = MagicMock()
    embedder.model.encode.return_value = np.array([[3.0, 4.0]])
    assert embedder.embed_query("question") == pytest.approx([0.6, 0.8])
    assert embedder.model.encode.call_args.kwargs["task"] == "retrieval"
    assert embedder.model.encode.call_args.kwargs["prompt_name"] == "query"
    assert embedder.model.encode.call_args.kwargs["batch_size"] == 1
    embedder.encode(["document"])
    assert embedder.model.encode.call_args.kwargs["prompt_name"] == "document"
    assert embedder.model.encode.call_args.kwargs["batch_size"] == 4


def test_sparse_preparation_reuses_production_tokens_of_requirement_labelled_chunks(monkeypatch, tmp_path):
    """상세 내용 청크에 요구사항 머리말이 붙어도 운영 색인과 같은 검색 글로 토큰을 만든다"""
    import json

    from rag.config import write_jsonl
    from rag.retrieval.benchmark import run
    from rag.retrieval.indexing import KiwiTokenizer, search_texts

    chunks = [{"chunk_id": f"c{i}", "doc_id": "d", "text": text, "body": text, "requirement_key": "TST-901"}
              for i, text in enumerate(["요구사항 고유번호 | TST-901\n요구사항 명칭 | 시험 데이터 보관", "예시 점검 절차"])]
    write_jsonl(chunks, tmp_path / "out/input/chunks.jsonl")
    tokenizer = KiwiTokenizer()
    production = {"tokenizer": tokenizer.fingerprint, "tokens": tokenizer.batch(search_texts(chunks))}
    (tmp_path / "artifacts/index").mkdir(parents=True)
    (tmp_path / "artifacts/index/bm25_tokens.json").write_text(json.dumps(production, ensure_ascii=False), encoding="utf-8")
    monkeypatch.setattr(run, "OUT", tmp_path / "out")
    monkeypatch.setattr(run, "ROOT", tmp_path)

    run.prepare_sparse()

    assert json.loads((tmp_path / "out/kiwi_tokens.json").read_text(encoding="utf-8")) == production


def controlled_index():
    original = make_index(["SFR-001 exact", "first agency", "second agency", "another hit"], [2] * 4,
                          doc_ids=["a", "a", "b", "b"])
    original.router.route.return_value = {"one": {"a"}, "two": {"b"}}
    original._dense = MagicMock(side_effect=lambda q, allowed: {i: 1.0 for i in [1, 2, 3] if allowed[i]})
    original._sparse = MagicMock(return_value={})
    experiment = BenchmarkIndex.__new__(BenchmarkIndex)
    experiment.__dict__.update(original.__dict__)
    return original, experiment


def test_integrated_matches_production_and_isolated_removes_only_exact_promotion():
    original, experiment = controlled_index()
    experiment.mode = "integrated"
    expected_hits, expected_candidates = original.search_with_candidates("SFR-001")
    hits, candidates = experiment.search_with_candidates("SFR-001")
    assert hits == expected_hits and candidates == expected_candidates
    assert [c["chunk_id"] for c in candidates] == ["c0", "c2", "c1", "c3"]
    experiment.mode = "isolated"
    _, candidates = experiment.search_with_candidates("SFR-001")
    assert [c["chunk_id"] for c in candidates] == ["c1", "c2", "c3"]
    assert not any(c["exact_code_match"] for c in candidates)


def test_quantity_bypass_is_preserved_only_in_integrated_path(monkeypatch):
    import rag.retrieval.retrieval as production

    original, experiment = controlled_index()
    original.router.route.return_value = {}
    monkeypatch.setattr(production, "project_condition", lambda q: "condition")
    experiment._filter = MagicMock(return_value=([], ()))
    experiment.mode = "integrated"
    assert experiment.search_with_candidates("quantity question") == ([], ())
    experiment._filter.assert_called_once_with("condition")
    experiment.mode = "isolated"
    _, candidates = experiment.search_with_candidates("quantity question")
    assert len(candidates) == 3
    assert experiment._filter.call_count == 1


def test_measurement_blocks_connections_and_records_attempts():
    with no_network() as attempts:
        with pytest.raises(RuntimeError, match="outbound connections"):
            socket.create_connection(("example.com", 443))
        with socket.socket() as sock:
            with pytest.raises(RuntimeError, match="outbound connections"):
                sock.connect(("127.0.0.1", 12345))
    assert len(attempts) == 2


def test_weight_selection_ignores_validation_scores(monkeypatch, tmp_path):
    from rag.retrieval.benchmark import summarize

    def records(path):
        weight = float(path.name.removesuffix(".jsonl.gz").rsplit("-", 1)[1])
        return [{"partition": partition, "route": "ordinary", "chunk_label_state": "fully_labelled",
                 "diagnostic_score": score}
                for partition, score in [("tuning", float(weight in (0.4, 0.6))), ("validation", float(weight == 0.8))]]

    def score(row, questions):
        assert row["partition"] == "tuning", "Validation must not be scored before weights freeze"
        return {"chunk_fused_recall_at_10": row["diagnostic_score"]}

    monkeypatch.setattr(summarize, "load_results", records)
    monkeypatch.setattr(summarize, "score_fields", score)
    result = summarize.choose_weights({"key": "another-model"}, tmp_path, {})
    assert {choice["weight"] for choice in result.values()} == {0.6}


def test_empty_filter_route_has_explicit_zero_counts():
    from rag.retrieval.benchmark.summarize import quality_groups

    rows = [{"partition": "validation", "route": "ordinary", "primary_topic": "numeric",
             "coverage_group": "single_evidence", "code_query": False,
             "doc_label_state": "fully_labelled", "chunk_label_state": "fully_labelled",
             "scores": {"chunk_fused_recall_at_10": 1.0}}]
    groups = list(quality_groups(rows, {}))
    empty = next(r for r in groups if r["partition"] == "validation" and r["route"] == "filter")
    assert empty["questions"] == empty["doc_eligible"] == empty["chunk_eligible"] == 0
    assert np.isnan(empty["chunk_fused_recall_at_10"])


def test_paired_fixed_and_tuned_comparisons_use_matching_kure_baselines():
    from rag.retrieval.benchmark.summarize import paired_differences

    rows = []
    for model, label, values in [("kure", "kiwi_hybrid_fixed", [0, 1]),
                                  ("kure", "kiwi_hybrid_tuned", [1, 1]),
                                  ("other", "kiwi_hybrid_fixed", [1, 1]),
                                  ("other", "kiwi_hybrid_tuned", [0, 1])]:
        rows += [{"model": model, "label": label, "id": str(i), "mode": "isolated", "route": "ordinary",
                  "primary_topic": "numeric", "chunk_fused_recall_at_10": value} for i, value in enumerate(values)]
    paired = [r for r in paired_differences(rows) if r["model"] == "other" and r["topic"] == "ALL"]
    assert {r["label"]: r["mean_difference"] for r in paired} == {"kiwi_hybrid_fixed": 0.5, "kiwi_hybrid_tuned": -0.5}
    assert all(r["baseline_label"] == r["label"] and r["paired_questions"] == 2 for r in paired)
