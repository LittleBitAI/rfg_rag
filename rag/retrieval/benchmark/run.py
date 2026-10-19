"""로컬 색인을 순차 구축하고 캐시 없는 단건 질의를 세 번 측정한다."""
from __future__ import annotations

import gzip
import hashlib
import json
import os
import random
import shutil
import time

import faiss
import numpy as np
import torch
import yaml

from rag.config import read_jsonl
from rag.evaluation.ir import coverage_group, label_state
from rag.retrieval.indexing import KiwiTokenizer, find_codes
from rag.retrieval.retrieval import FilterHits

from .common import OUT, RECORD, ROOT, SEED, WEIGHTS, digest, no_network, protected_files, save_json, verify_source
from .embedding import LocalEmbedder, snapshot
from .prepare import freeze_inputs
from .resources import ResourceMonitor, machine
from .search import BenchmarkIndex


def configurations(spec):
    configs = [("kiwi", 0.6), ("kiwi", 1.0)]
    if spec["key"] == "kure":
        configs += [("kiwi", 0.0), ("whitespace", 0.0), ("whitespace", 0.6)]
    configs += [("kiwi", w) for w in WEIGHTS if w != 0.6]
    if spec["key"] == "kure":
        configs += [("whitespace", w) for w in WEIGHTS if w != 0.6]
    return configs


def build_private_index(embedder, folder):
    chunks = read_jsonl(OUT / "input/chunks.jsonl")
    texts = [c["text"] for c in chunks]
    folder.mkdir(parents=True, exist_ok=True)
    with ResourceMonitor() as monitor:
        vectors = embedder.encode(texts, progress=True)
        index = faiss.IndexFlatIP(vectors.shape[1])
        index.add(vectors)
        faiss.write_index(index, str(folder / "faiss.index"))
        empty_quantity_phrases = build_quantity_vectors(chunks, embedder, folder)
    result = monitor.result()
    result.update(chunks=len(chunks), documents=len({c["doc_id"] for c in chunks}),
                  dimensions=int(vectors.shape[1]), indexing_batch_size=embedder.spec["batch_size"],
                  chunks_per_second=len(chunks) / result["seconds"],
                  index_bytes=sum(p.stat().st_size for p in folder.iterdir() if p.is_file()),
                  faiss_bytes=(folder / "faiss.index").stat().st_size,
                  quantity_empty_placeholders=empty_quantity_phrases,
                  document_truncation=embedder.truncation_report(texts),
                  quantity_truncation=embedder.truncation_report(json.loads((folder / "quantity_phrases.json").read_text(encoding="utf-8"))))
    save_json(result, folder / "build.json")
    return result


def build_quantity_vectors(chunks, embedder, folder):
    source = ROOT / "artifacts/index"
    rows = read_jsonl(source / "quantities.jsonl")
    phrases = json.loads((source / "quantity_phrases.json").read_text(encoding="utf-8"))
    live_ids = {c["chunk_id"] for c in chunks}
    assert all(r["chunk_id"] in live_ids for r in rows)
    assert phrases == list(dict.fromkeys(r["phrase"] for r in rows))
    for name in ("quantities.jsonl", "quantity_phrases.json"):
        shutil.copyfile(source / name, folder / name)
    np.save(folder / "quantity_vectors.npy", quantity_vectors(phrases, embedder))
    return phrases.count("")


def quantity_vectors(phrases, embedder):
    # 운영 필터는 빈 구절을 제외하며 Perplexity의 빈 구절 벡터는 코사인을 정의할 수 없다.
    positions = [i for i, phrase in enumerate(phrases) if phrase]
    vectors = np.zeros((len(phrases), embedder.spec["dimensions"]), dtype=np.float32)
    vectors[positions] = embedder.encode([phrases[i] for i in positions], progress=True)
    return vectors


def prepare_sparse():
    target = OUT / "kiwi_tokens.json"
    tokenizer = KiwiTokenizer()
    if target.exists():
        stored = json.loads(target.read_text(encoding="utf-8"))
        assert stored["tokenizer"] == tokenizer.fingerprint
        return
    chunks = read_jsonl(OUT / "input/chunks.jsonl")
    start = time.perf_counter()
    tokens = tokenizer.batch([c["text"] for c in chunks])
    stored = json.loads((ROOT / "artifacts/index/bm25_tokens.json").read_text(encoding="utf-8"))
    assert stored == {"tokenizer": tokenizer.fingerprint, "tokens": tokens}
    save_json(stored, target)
    save_json({"kiwi_seconds": time.perf_counter() - start, "tokenizer": tokenizer.fingerprint}, OUT / "sparse_build.json")


def question_result(row, hits, candidates):
    record = {"id": row["id"], "primary_topic": row["primary_topic"] or "yaml",
              "route": "filter" if isinstance(hits, FilterHits) else "ordinary", "coverage_group": coverage_group(row),
              "code_query": bool(find_codes(row["question"])),
              "doc_label_state": label_state(row, "doc"), "chunk_label_state": label_state(row, "chunk"),
              "context_chunk_ids": [h["chunk_id"] for h in hits], "ranked_candidates": [dict(c) for c in candidates]}
    record["context_sha256"] = [hashlib.sha256(h["body"].encode("utf-8")).hexdigest() for h in hits]
    if isinstance(hits, FilterHits):
        record["filter_values"] = hits.values
        record["filter_chosen_document_count"] = len(hits.chosen)
        record["filter_summary"] = hits.summary
    return record


def signature(record):
    stable = {k: record[k] for k in ("context_chunk_ids", "ranked_candidates", "context_sha256")}
    return hashlib.sha256(json.dumps(stable, sort_keys=True).encode("utf-8")).hexdigest()


def timed_configuration(index, rows, folder, mode, sparse, weight, partitions):
    name = f"{mode}-{sparse}-{weight:.1f}"
    index.configure(sparse, weight, mode)
    for row in rows[:3]:
        index.search_with_candidates(row["question"])
    expected = {}
    with gzip.open(folder / f"{name}.jsonl.gz", "wt", encoding="utf-8") as results, \
            (folder / f"{name}-latency.jsonl").open("w", encoding="utf-8") as latency:
        for pass_id in range(3):
            order = list(rows)
            random.Random(SEED + pass_id).shuffle(order)
            for position, row in enumerate(order):
                torch.cuda.synchronize()
                start = time.perf_counter_ns()
                hits, candidates = index.search_with_candidates(row["question"])
                torch.cuda.synchronize()
                ms = (time.perf_counter_ns() - start) / 1e6
                record = question_result(row, hits, candidates)
                record["partition"] = partitions[row["id"]]
                stamp = signature(record)
                if pass_id == 0:
                    expected[row["id"]] = stamp
                    results.write(json.dumps(record, ensure_ascii=False, allow_nan=False) + "\n")
                else:
                    assert expected[row["id"]] == stamp, (name, pass_id, row["id"], "nondeterministic search")
                latency.write(json.dumps({"id": row["id"], "pass": pass_id, "position": position,
                                          "milliseconds": ms, "partition": record["partition"], "route": record["route"]}) + "\n")
            latency.flush()
            results.flush()
            print("TIMED", name, "pass", pass_id + 1, len(rows), flush=True)


def measure_queries(index, spec, folder):
    rows = read_jsonl(RECORD / "questions.jsonl")
    split = json.loads((RECORD / "split.json").read_text(encoding="utf-8"))
    partitions = {qid: name for name, ids in split["ids"].items() for qid in ids}
    for sparse, weight in configurations(spec):
        for mode in ("isolated", "integrated"):
            timed_configuration(index, rows, folder, mode, sparse, weight, partitions)
    return index.embedder.truncation_report([r["question"] for r in rows], query=True)


def measurement_files(spec):
    return [f"{mode}-{sparse}-{weight:.1f}{suffix}"
            for sparse, weight in configurations(spec) for mode in ("isolated", "integrated")
            for suffix in (".jsonl.gz", "-latency.jsonl")]


def run_model(spec):
    manifest = freeze_inputs()
    os.environ["CUBLAS_WORKSPACE_CONFIG"] = ":4096:8"
    torch.manual_seed(SEED)
    np.random.seed(SEED)
    torch.use_deterministic_algorithms(True)
    folder = OUT / spec["key"]
    assert not (folder / "complete.json").exists(), "Completed measurements are immutable; choose a fresh experiment directory to repeat"
    with no_network() as attempts:
        before = machine()
        assert before["gpu_free_bytes"] > 6 * 1024 ** 3 and before["disk_free_bytes"] > 15 * 1024 ** 3
        prepare_sparse()
        with ResourceMonitor() as loading_monitor:
            embedder = LocalEmbedder(spec)
        loading_resources = loading_monitor.result()
        build = build_private_index(embedder, folder / "index")
        cfg = yaml.safe_load((OUT / "input/config.yaml").read_text(encoding="utf-8"))
        assert cfg["retrieval"]["candidate_k"] == 50 and cfg["retrieval"]["token_budget"] == 2500
        start = time.perf_counter()
        index = BenchmarkIndex(embedder, cfg, folder / "index")
        search_setup_seconds = time.perf_counter() - start
        with ResourceMonitor() as monitor:
            query_truncation = measure_queries(index, spec, folder)
        resources = monitor.result()
        after = protected_files()
        assert after == manifest["protected_before"], "Protected application artifacts changed"
        assert not attempts, attempts
        identity = verify_source(manifest)
        result = {"model": spec, "machine_before": before, "model_load_seconds": embedder.load_seconds,
                  **identity,
                  "model_load_resources": loading_resources,
                  "search_setup_seconds": search_setup_seconds, "indexing": build, "query_resources": resources,
                  "query_truncation": query_truncation, "raw_vector_dtypes": sorted(embedder.raw_dtypes),
                  "network_attempts": attempts, "protected_unchanged": True, "test_split_executed": False,
                  "frozen_questions_sha256": digest(RECORD / "questions.jsonl"),
                  "frozen_split_sha256": digest(RECORD / "split.json"),
                  "artifact_sha256": {name: digest(folder / name) for name in measurement_files(spec)},
                  "model_file_hashes": model_file_hashes(spec)}
        save_json(result, folder / "complete.json")
        print("COMPLETE", spec["id"], "protected files unchanged; zero network attempts", flush=True)


def model_file_hashes(spec):
    from pathlib import Path

    path = Path(snapshot(spec))
    return {str(p.relative_to(path)).replace("\\", "/"): digest(p) for p in path.rglob("*") if p.is_file()}
