"""합성 자료로 로컬 산출물을 검사하며 실제 데이터셋을 테스트에 넣지 않는다."""
import gzip
import json
import random
import shutil
from unittest.mock import MagicMock

import pandas as pd
import pytest

from rag.config import read_jsonl, write_jsonl
from rag.retrieval.benchmark import common, prepare, run, summarize, verify
from rag.retrieval.benchmark.common import SEED, digest, save_json
from rag.retrieval.benchmark.prepare import grouped_split
from rag.retrieval.benchmark.run import configurations, measurement_files
from rag.retrieval.retrieval import FilterHits


def write_gzip(path, rows):
    path.parent.mkdir(parents=True, exist_ok=True)
    with gzip.open(path, "wt", encoding="utf-8") as stream:
        for row in rows:
            stream.write(json.dumps(row) + "\n")


def synthetic_result(question, partition, weight):
    evidence = question["evidence"][0]
    row = {"id": question["id"], "partition": partition, "route": "ordinary",
           "primary_topic": question["primary_topic"], "coverage_group": "single_evidence", "code_query": False,
           "doc_label_state": "fully_labelled", "chunk_label_state": "fully_labelled",
           "context_chunk_ids": ["non-gold-chunk"], "context_sha256": ["0" * 64],
           "ranked_candidates": [{"doc_id": evidence["doc_id"], "chunk_id": evidence["chunk_id"],
                                  "fused_rank": 1, "dense_rank": None if weight == 0 else 1,
                                  "bm25_rank": None if weight == 1 else 1, "exact_code_match": False},
                                 {"doc_id": "synthetic-other", "chunk_id": "non-gold-chunk", "fused_rank": 2,
                                  "dense_rank": None if weight == 0 else 2,
                                  "bm25_rank": None if weight == 1 else 2, "exact_code_match": False}]}
    return row


def synthetic_timings(questions, partitions):
    rows = []
    for pass_id in range(3):
        order = list(questions)
        random.Random(SEED + pass_id).shuffle(order)
        rows.extend({"id": q["id"], "pass": pass_id, "position": i, "milliseconds": 1.0,
                     "partition": partitions[q["id"]], "route": "ordinary"} for i, q in enumerate(order))
    return rows


def write_model(record, spec, manifest, questions, split):
    partitions = {qid: name for name, ids in split["ids"].items() for qid in ids}
    folder = record / "results" / spec["key"]
    complete = {"model": spec, "protected_unchanged": True, "network_attempts": [],
                "test_split_executed": False, "frozen_questions_sha256": manifest["questions_sha256"],
                "frozen_split_sha256": manifest["split_sha256"], "machine_before": {"gpu": "RTX 3080"},
                "indexing": {"chunks": manifest["counts"]["chunks"]}}
    complete.update(source_commit=manifest["base_commit"], source_hashes=manifest["source_hashes"])
    save_json(complete, folder / "complete.json")
    for sparse, weight in configurations(spec):
        for mode in ("isolated", "integrated"):
            name = summarize.config_name(mode, sparse, weight)
            rows = [synthetic_result(q, partitions[q["id"]], weight) for q in questions]
            write_gzip(folder / f"{name}.jsonl.gz", rows)
            write_jsonl(synthetic_timings(questions, partitions), folder / f"{name}-latency.jsonl")
    seal_model(folder, spec)


def seal_model(folder, spec):
    path = folder / "complete.json"
    complete = json.loads(path.read_text(encoding="utf-8"))
    complete["artifact_sha256"] = {name: digest(folder / name) for name in measurement_files(spec)}
    save_json(complete, path)


@pytest.fixture
def local_record(tmp_path, monkeypatch):
    spec = {"key": "kure", "id": "synthetic/model"}
    questions = [{"id": f"q-{i}", "question": f"synthetic question {i}", "primary_topic": "numeric",
                  "answerable": True, "bundle_id": f"bundle-{i}", "evidence": [
                      {"doc_sha": "synthetic-doc", "doc_id": "synthetic-doc", "golden_chunk_id": f"old-{i}",
                       "chunk_id": f"chunk-{i}"}]} for i in range(4)]
    record = tmp_path / "artifacts/record"
    record.mkdir(parents=True)
    write_jsonl(questions, record / "questions.jsonl")
    split = grouped_split(questions)
    save_json(split, record / "split.json")
    save_json([spec], record / "models.json")
    identity = {"source_commit": "a" * 40, "source_hashes": {"search.py": "b" * 64}}
    manifest = {"version": 3, "counts": {"questions": len(questions), "chunks": len(questions) + 1},
                "base_commit": identity["source_commit"], "source_hashes": identity["source_hashes"],
                "models": [spec], "protected_before": {}, "inputs": {}}
    for name, suffix in (("questions", "jsonl"), ("split", "json"), ("models", "json")):
        manifest[f"{name}_sha256"] = digest(record / f"{name}.{suffix}")
    save_json(manifest, record / "manifest.json")
    release = tmp_path / "artifacts/local_inputs/golden/dev.jsonl"
    release.parent.mkdir(parents=True)
    write_jsonl([{"candidate_id": q["id"]} for q in questions], release)
    monkeypatch.setattr(verify, "ROOT", tmp_path)
    monkeypatch.setattr(common, "source_identity", lambda: identity)
    monkeypatch.setattr(prepare, "RECORD", record)
    monkeypatch.setattr(prepare, "OUT", record.parent)
    monkeypatch.setattr(prepare, "models", lambda: [spec])
    monkeypatch.setattr(prepare, "protected_files", lambda: {})
    monkeypatch.setattr(verify, "models", lambda: [spec])
    monkeypatch.setattr(summarize, "models", lambda: [spec])
    write_model(record, spec, manifest, questions, split)
    choices = {spec["key"]: summarize.choose_weights(spec, record / "results", {q["id"]: q for q in questions})}
    save_json(choices, record / "chosen_weights.json")
    return record


def test_local_artifact_verification_accepts_complete_synthetic_records(local_record):
    verify.verify_record(local_record)


@pytest.mark.parametrize("damage", ("rank", "context", "pass", "position", "duration", "sample_count"))
def test_local_artifact_verification_rejects_corrupted_records(local_record, damage):
    latency = damage in ("pass", "position", "duration", "sample_count")
    suffix = "-latency" if latency else ""
    extension = ".jsonl" if latency else ".jsonl.gz"
    path = local_record / f"results/kure/isolated-kiwi-0.6{suffix}{extension}"
    rows = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()] if latency else summarize.load_results(path)
    if damage == "rank":
        rows[0]["ranked_candidates"][0]["fused_rank"] = 2
    elif damage == "context":
        rows[0]["context_sha256"] = []
    else:
        corrupt_timing(rows, damage)
    if latency:
        write_jsonl(rows, path)
    else:
        write_gzip(path, rows)
    # 소스 파일 지문 검사와 별개로 행·패스 의미 검증도 계속 지킨다.
    seal_model(path.parent, {"key": "kure"})
    with pytest.raises(AssertionError):
        verify.verify_record(local_record)


def corrupt_timing(rows, damage):
    if damage == "sample_count":
        rows.pop()
    else:
        field = {"pass": "pass", "position": "position", "duration": "milliseconds"}[damage]
        rows[0][field] = -1


def test_frozen_weights_cannot_be_replaced(local_record, monkeypatch):
    save_json({}, local_record / "chosen_weights.json")
    monkeypatch.setattr(summarize, "OUT", local_record / "results")
    monkeypatch.setattr(summarize, "RECORD", local_record)
    with pytest.raises(AssertionError, match="Frozen tuning choices changed"):
        summarize.summarize()


def synthetic_search_hits(question, partition, weight, filter_id, matched):
    row = synthetic_result(question, partition, weight)
    candidates = row["ranked_candidates"]
    hits = [{"chunk_id": row["context_chunk_ids"][0], "body": "synthetic ordinary context"}]
    if question["id"] == filter_id:
        candidates = [{**candidates[0], "dense_rank": None, "bm25_rank": None}] if matched else []
        hits = [{"chunk_id": candidates[0]["chunk_id"], "body": "synthetic filtered context"}] if matched else []
        values = [{"doc_id": question["evidence"][0]["doc_id"], "value": 123}] if matched else []
        chosen = {row["doc_id"]: row for row in values}
        hits = FilterHits(hits, "synthetic quantity-filter summary", values, chosen)
    return hits, candidates


@pytest.fixture(params=[False, True], ids=["empty-filter", "matching-filter"])
def filtered_record(local_record, monkeypatch, request):
    questions = read_jsonl(local_record / "questions.jsonl")
    split = json.loads((local_record / "split.json").read_text(encoding="utf-8"))
    partitions = {qid: name for name, ids in split["ids"].items() for qid in ids}
    filter_id = split["ids"]["validation"][0]
    by_query = {q["question"]: q for q in questions}
    state = {}
    index = MagicMock()
    index.configure.side_effect = lambda sparse, weight, mode: state.update(weight=weight)

    def search(query):
        question = by_query[query]
        return synthetic_search_hits(question, partitions[question["id"]], state["weight"], filter_id, request.param)

    index.search_with_candidates.side_effect = search
    monkeypatch.setattr(run.torch.cuda, "synchronize", lambda: None)
    folder = local_record / "results/kure"
    spec = {"key": "kure", "id": "synthetic/model"}
    for sparse, weight in configurations(spec):
        run.timed_configuration(index, questions, folder, "integrated", sparse, weight, partitions)
    seal_model(folder, spec)
    return local_record, request.param


def test_measured_filter_results_summarize_and_verify_separately(filtered_record, monkeypatch):
    record, matched = filtered_record
    measurements = record / "measurements"
    shutil.copytree(record / "results/kure", measurements / "kure")
    monkeypatch.setattr(summarize, "OUT", measurements)
    monkeypatch.setattr(summarize, "RECORD", record)
    summarize.summarize()
    verify.verify_record(record)
    quality = pd.read_csv(record / "quality.csv")
    quality = quality[(quality["mode"] == "integrated") & (quality.label == "kiwi_hybrid_fixed")
                      & (quality.partition == "validation") & (quality.topic == "ALL") & (quality.group == "ALL")]
    [filtered] = quality[quality.route == "filter"].to_dict("records")
    assert filtered["questions"] == 1
    assert filtered["evidence_coverage"] == float(matched)
    assert quality.questions.sum() == len(json.loads((record / "split.json").read_text(encoding="utf-8"))["ids"]["validation"])
    latency = pd.read_csv(record / "latency.csv")
    filtered = latency[(latency["mode"] == "integrated") & (latency.label == "kiwi_hybrid_fixed")
                       & (latency.partition == "validation") & (latency.route == "filter") & (latency["pass"] == "ALL")]
    assert filtered.samples.tolist() == [3]
    rows = summarize.load_results(record / "results/kure/integrated-kiwi-0.6.jsonl.gz")
    [row] = [r for r in rows if r["route"] == "filter"]
    assert row["filter_summary"] == "synthetic quantity-filter summary"
    assert row["filter_chosen_document_count"] == int(matched)


@pytest.mark.parametrize("artifact,mode,question_kind,route", [
    ("results", "integrated", "filter", "unknown"),
    ("results", "isolated", "filter", "filter"),
    ("latency", "integrated", "filter", "ordinary"),
    ("latency", "integrated", "ordinary", "filter"),
    ("latency", "integrated", "filter", "unknown"),
    ("latency", "isolated", "ordinary", "filter"),
])
def test_invalid_or_inconsistent_routes_are_rejected(filtered_record, artifact, mode, question_kind, route):
    record, _ = filtered_record
    folder = record / "results/kure"
    split = json.loads((record / "split.json").read_text(encoding="utf-8"))
    filter_id = split["ids"]["validation"][0]
    qid = filter_id if question_kind == "filter" else next(q["id"] for q in read_jsonl(record / "questions.jsonl")
                                                         if q["id"] != filter_id)
    suffix = ".jsonl.gz" if artifact == "results" else "-latency.jsonl"
    path = folder / f"{mode}-kiwi-0.6{suffix}"
    rows = summarize.load_results(path) if artifact == "results" else read_jsonl(path)
    selected = next(r for r in rows if r["id"] == qid and (artifact == "results" or r["pass"] == 1))
    selected["route"] = route
    if artifact == "results":
        write_gzip(path, rows)
    else:
        write_jsonl(rows, path)
    seal_model(folder, {"key": "kure"})
    with pytest.raises(AssertionError, match="route"):
        verify.verify_record(record)
