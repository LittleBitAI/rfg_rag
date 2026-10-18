"""합성 자료로 로컬 산출물을 검사하며 실제 데이터셋을 테스트에 넣지 않는다."""
import gzip
import json
import random

import pytest

from rag.config import write_jsonl
from rag.evaluation.ir import ir_scores
from rag.retrieval.benchmark import summarize, verify
from rag.retrieval.benchmark.common import SEED, digest, save_json
from rag.retrieval.benchmark.prepare import grouped_split
from rag.retrieval.benchmark.run import configurations


def write_gzip(path, rows):
    path.parent.mkdir(parents=True, exist_ok=True)
    with gzip.open(path, "wt", encoding="utf-8") as stream:
        for row in rows:
            stream.write(json.dumps(row) + "\n")


def synthetic_result(question, partition, weight):
    evidence = question["evidence"][0]
    row = {"id": question["id"], "partition": partition, "route": "ordinary",
           "doc_label_state": "fully_labelled", "chunk_label_state": "fully_labelled",
           "context_chunk_ids": [evidence["chunk_id"]], "context_sha256": ["0" * 64],
           "ranked_candidates": [{"doc_id": evidence["doc_id"], "chunk_id": evidence["chunk_id"],
                                  "fused_rank": 1, "dense_rank": None if weight == 0 else 1,
                                  "bm25_rank": None if weight == 1 else 1, "exact_code_match": False}]}
    return {**row, "scores": ir_scores({**question, **row})}


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
    save_json(complete, folder / "complete.json")
    for sparse, weight in configurations(spec):
        for mode in ("isolated", "integrated"):
            name = summarize.config_name(mode, sparse, weight)
            rows = [synthetic_result(q, partitions[q["id"]], weight) for q in questions]
            write_gzip(folder / f"{name}.jsonl.gz", rows)
            write_gzip(folder / f"{name}-latency.jsonl.gz", synthetic_timings(questions, partitions))


@pytest.fixture(params=(1, 2), ids=("archived_format", "current_format"))
def local_record(tmp_path, monkeypatch, request):
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
    manifest = {"version": request.param, "counts": {"questions": len(questions), "chunks": len(questions)}}
    for name, suffix in (("questions", "jsonl"), ("split", "json"), ("models", "json")):
        manifest[f"{name}_sha256"] = digest(record / f"{name}.{suffix}")
    save_json(manifest, record / "manifest.json")
    release = tmp_path / "eval/golden/dev.jsonl"
    release.parent.mkdir(parents=True)
    write_jsonl([{"candidate_id": q["id"]} for q in questions], release)
    monkeypatch.setattr(verify, "ROOT", tmp_path)
    monkeypatch.setattr(verify, "models", lambda: [spec])
    monkeypatch.setattr(summarize, "models", lambda: [spec])
    write_model(record, spec, manifest, questions, split)
    choices = {spec["key"]: summarize.choose_weights(spec, record / "results", {q["id"]: q for q in questions})}
    save_json(choices, record / "chosen_weights.json")
    return record


def test_local_artifact_verification_accepts_complete_synthetic_records(local_record):
    verify.verify_record(local_record)


@pytest.mark.parametrize("damage", ("score", "rank", "context", "pass", "position", "duration", "sample_count"))
def test_local_artifact_verification_rejects_corrupted_records(local_record, damage):
    latency = damage in ("pass", "position", "duration", "sample_count")
    suffix = "-latency" if latency else ""
    path = local_record / f"results/kure/isolated-kiwi-0.6{suffix}.jsonl.gz"
    rows = summarize.load_results(path)
    if damage == "score":
        rows[0]["scores"]["chunk_fused_recall_at_10"] = 0.0
    elif damage == "rank":
        rows[0]["ranked_candidates"][0]["fused_rank"] = 2
    elif damage == "context":
        rows[0]["context_sha256"] = []
    else:
        corrupt_timing(rows, damage)
    write_gzip(path, rows)
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
