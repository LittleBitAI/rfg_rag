"""로컬 측정 산출물을 검사하며 저장소 테스트에는 실제 데이터가 필요하지 않다."""
import json
import math
import random

from rag.config import read_jsonl
from rag.evaluation.ir import label_state

from .common import ROOT, SEED, digest, models, verify_source
from .prepare import evidence_groups, grouped_split
from .run import configurations, measurement_files
from .summarize import choose_weights, config_name, load_results


def verify_result(record, question):
    for level in ("doc", "chunk"):
        assert record[f"{level}_label_state"] == label_state(question, level)
    assert [c["fused_rank"] for c in record["ranked_candidates"]] == list(
        range(1, len(record["ranked_candidates"]) + 1))
    assert len(record["context_chunk_ids"]) == len(record["context_sha256"])


def verify_timing(path, questions, partitions):
    with path.open(encoding="utf-8") as stream:
        times = [json.loads(line) for line in stream]
    assert len(times) == 3 * len(questions)
    for pass_id in range(3):
        expected = list(questions)
        random.Random(SEED + pass_id).shuffle(expected)
        selected = times[pass_id * len(questions):(pass_id + 1) * len(questions)]
        assert [r["id"] for r in selected] == [r["id"] for r in expected]
        assert [r["position"] for r in selected] == list(range(len(questions)))
        assert all(r["pass"] == pass_id and r["partition"] == partitions[r["id"]]
                   and r["route"] == "ordinary" and math.isfinite(r["milliseconds"])
                   and r["milliseconds"] > 0 for r in selected)


def verify_partition(record, manifest):
    for name, suffix in (("questions", "jsonl"), ("split", "json"), ("models", "json")):
        assert digest(record / f"{name}.{suffix}") == manifest[f"{name}_sha256"]
    rows = read_jsonl(record / "questions.jsonl")
    split = json.loads((record / "split.json").read_text(encoding="utf-8"))
    assert manifest["version"] == 3, "Unbound historical records require a new measured run"
    assert grouped_split(rows) == split
    assert {r["id"] for r in rows} == {r["candidate_id"] for r in read_jsonl(ROOT / "eval/golden/dev.jsonl")}
    partitions = {qid: name for name, ids in split["ids"].items() for qid in ids}
    assert all(len({partitions[r["id"]] for r in group}) == 1 for group in evidence_groups(rows))
    assert len(partitions) == sum(map(len, split["ids"].values())) == len(rows) == manifest["counts"]["questions"]
    return rows, partitions


def verify_configuration(folder, name, questions, partitions, mode, weight):
    by_id = {r["id"]: r for r in questions}
    rows = load_results(folder / f"{name}.jsonl.gz")
    assert len(rows) == len(by_id) and {r["id"] for r in rows} == set(by_id)
    for row in rows:
        assert row["partition"] == partitions[row["id"]]
        assert row["route"] == "ordinary"
        verify_result(row, by_id[row["id"]])
    candidates = [c for row in rows for c in row["ranked_candidates"]]
    if mode == "isolated":
        assert not any(c["exact_code_match"] for c in candidates)
    if weight == 0:
        assert all(c["dense_rank"] is None for c in candidates)
    if weight == 1:
        assert all(c["bm25_rank"] is None for c in candidates)
    verify_timing(folder / f"{name}-latency.jsonl", questions, partitions)


def verify_completion(folder, spec, manifest):
    complete = json.loads((folder / "complete.json").read_text(encoding="utf-8"))
    assert complete["source_commit"] == manifest["base_commit"], "Model source commit differs from frozen source"
    assert complete["source_hashes"] == manifest["source_hashes"], "Model source hashes differ from frozen source"
    expected = set(measurement_files(spec))
    assert set(complete.get("artifact_sha256", {})) == expected, "Missing or unexpected measurement artifact seals"
    assert all((folder / name).is_file() and digest(folder / name) == complete["artifact_sha256"][name]
               for name in expected), "Measurement artifact changed after completion"
    assert complete["model"] == spec
    assert complete["protected_unchanged"] and complete["network_attempts"] == []
    assert complete["test_split_executed"] is False
    assert complete["frozen_questions_sha256"] == manifest["questions_sha256"]
    assert complete["frozen_split_sha256"] == manifest["split_sha256"]
    assert "RTX 3080" in complete["machine_before"]["gpu"]
    assert complete["indexing"]["chunks"] == manifest["counts"]["chunks"]
    return complete


def verify_model(record, spec, manifest, questions, partitions):
    folder = record / "results" / spec["key"]
    verify_completion(folder, spec, manifest)
    for sparse, weight in configurations(spec):
        for mode in ("isolated", "integrated"):
            verify_configuration(folder, config_name(mode, sparse, weight), questions, partitions, mode, weight)


def verify_record(record):
    manifest = json.loads((record / "manifest.json").read_text(encoding="utf-8"))
    verify_source(manifest)
    questions, partitions = verify_partition(record, manifest)
    for spec in models():
        verify_model(record, spec, manifest, questions, partitions)
    choices = {spec["key"]: choose_weights(spec, record / "results", {r["id"]: r for r in questions})
               for spec in models()}
    assert choices == json.loads((record / "chosen_weights.json").read_text(encoding="utf-8"))
