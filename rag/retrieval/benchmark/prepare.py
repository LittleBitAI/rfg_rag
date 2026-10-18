"""점수 계산 전에 원본 dev 입력과 그룹별 분할을 동결한다."""
from __future__ import annotations

import json
import random
import shutil
import subprocess
from collections import Counter, defaultdict
from datetime import datetime, timezone

from rag.config import read_jsonl, write_jsonl
from rag.evaluation.ir import exclusion_report
from rag.validation.evidence import _chunk_label, _context_labels, normalize_evidence
from rag.validation.validation import load_eval_items

from .common import MODEL_IGNORE_PATTERNS, OUT, RECORD, ROOT, SEED, WEIGHTS, digest, models, protected_files, save_json
from .full_dev import load_full_dev


def verify_provenance(rows):
    dev_path = ROOT / "eval/golden/dev.jsonl"
    dev = {r["candidate_id"]: r for r in read_jsonl(dev_path)}
    release = json.loads((ROOT / "eval/golden/manifest.json").read_text(encoding="utf-8"))
    assert digest(dev_path) == release["dev"]["sha256"]
    yaml = {r["id"]: r for r in load_eval_items(["eval/eval_questions.yaml"])}
    for row in rows:
        if row["evidence_source"] != "golden":
            assert row["question"] == yaml[row["id"]]["question"]
            continue
        source = dev[row["id"]]
        assert (row["question"], row["reference"]) == (source["question"], source["answer"])
        assert [(e["doc_sha"], e["golden_chunk_id"]) for e in row["evidence"]] == [
            (e["doc_sha"], e["chunk_id"]) for e in source["evidence"]]
        for evidence in row["evidence"]:
            _context_labels(evidence["text"], source["context"])
    return dev


def remap(rows, chunks, dev):
    by_doc = defaultdict(list)
    for chunk in chunks:
        assert chunk["doc_id"] == chunk["source_sha256"]
        by_doc[chunk["doc_id"]].append((chunk["chunk_id"], normalize_evidence(chunk["body"])))
    mapped = []
    for row in rows:
        evidence = []
        for ref in row["evidence"]:
            doc = ref["doc_sha"] if ref["doc_sha"] in by_doc else None
            evidence.append({**ref, "doc_id": doc, **_chunk_label(ref["text"], doc, by_doc)})
        mapped.append({**row, "evidence": evidence, "bundle_id": dev.get(row["id"], {}).get("bundle_id"),
                       "doc_ids": sorted({e["doc_id"] for e in evidence if e["doc_id"]})})
    return mapped


def evidence_groups(rows):
    parents = list(range(len(rows)))

    def root(i):
        while parents[i] != i:
            i = parents[i]
        return i

    keys = {}
    for i, row in enumerate(rows):
        tags = [("question", normalize_evidence(row["question"]))]
        tags += [("evidence", e["doc_sha"], e["golden_chunk_id"]) for e in row["evidence"]]
        tags += [("mapped", e["doc_sha"], e["chunk_id"]) for e in row["evidence"] if e.get("chunk_id")]
        if row.get("bundle_id"):
            tags.append(("bundle", row["bundle_id"]))
        for tag in tags:
            if tag in keys:
                parents[root(i)] = root(keys[tag])
            keys[tag] = i
    groups = defaultdict(list)
    for i, row in enumerate(rows):
        groups[root(i)].append(row)
    return list(groups.values())


def grouped_split(rows):
    groups = evidence_groups(rows)
    random.Random(SEED).shuffle(groups)
    groups.sort(key=len, reverse=True)
    target = Counter(r["primary_topic"] or "yaml" for r in rows)
    assigned = Counter()
    partitions = {"tuning": [], "validation": []}
    for group in groups:
        counts = Counter(r["primary_topic"] or "yaml" for r in group)
        before = sum((assigned[t] - n / 2) ** 2 / n for t, n in target.items())
        after = sum((assigned[t] + counts[t] - n / 2) ** 2 / n for t, n in target.items())
        name = "tuning" if after < before else "validation"
        partitions[name].extend(r["id"] for r in group)
        if name == "tuning":
            assigned.update(counts)
    return {"seed": SEED, "target_tuning_share": 0.5, "ids": {k: sorted(v) for k, v in partitions.items()},
            "group_sizes": sorted([len(g) for g in groups], reverse=True),
            "topic_counts": {k: dict(Counter(r["primary_topic"] or "yaml" for r in rows if r["id"] in v))
                             for k, v in partitions.items()},
            "group_rule": "Connected duplicate normalized questions, shared original or valid mapped golden chunk, or bundle ID; no group crosses partitions",
            "limitations": "Earlier subset scores and prior Kiwi dev scores were already inspected. This split holds out weight tuning only, not prior development or a final test. Documents can cross partitions; whole evidence groups limit topic balance."}


def freeze_inputs():
    manifest_path = RECORD / "manifest.json"
    if manifest_path.exists():
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        assert manifest["protected_before"] == protected_files()
        assert models() == manifest["models"], "Pinned model specifications changed"
        for name in ("questions", "split", "models"):
            suffix = "jsonl" if name == "questions" else "json"
            assert digest(RECORD / f"{name}.{suffix}") == manifest[f"{name}_sha256"]
        for name, fingerprint in manifest["inputs"].items():
            assert digest(OUT / "input" / name) == fingerprint
        return manifest
    destination = OUT / "input"
    destination.mkdir(parents=True, exist_ok=True)
    sources = {"original_eval.jsonl": "artifacts/eval_set.jsonl", "chunks.jsonl": "artifacts/chunks.jsonl",
               "docs.jsonl": "artifacts/docs.jsonl", "config.yaml": "config.yaml", "orgs.csv": "data/data_list.csv",
               "dev.jsonl": "eval/golden/dev.jsonl", "golden_manifest.json": "eval/golden/manifest.json",
               "eval_questions.yaml": "eval/eval_questions.yaml", "kiwi_user_words.json": "rag/retrieval/kiwi_user_words.json"}
    rows, plans = load_full_dev()
    sources.update({f"plans/{p.name}": str(p.relative_to(ROOT)).replace("\\", "/") for p in plans})
    for name, source in sources.items():
        (destination / name).parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(ROOT / source, destination / name)
    RECORD.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(ROOT / "docs/benchmarks/seven_model/models.json", RECORD / "models.json")
    chunks = read_jsonl(destination / "chunks.jsonl")
    dev = verify_provenance(rows)
    mapped = remap(rows, chunks, dev)
    write_jsonl(mapped, RECORD / "questions.jsonl")
    split = grouped_split(mapped)
    save_json(split, RECORD / "split.json")
    exclusion_report(mapped).to_csv(RECORD / "exclusions.csv", index=False, encoding="utf-8")
    manifest = make_manifest(sources, mapped, chunks, split)
    save_json(manifest, manifest_path)
    print("FROZEN", len(rows), "questions;", len(chunks), "chunks; partitions", split["topic_counts"], flush=True)
    return manifest


def make_manifest(sources, rows, chunks, split):
    return {"version": 2, "frozen_at_utc": datetime.now(timezone.utc).isoformat(),
            "base_commit": subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip(),
            "inputs": {name: digest(OUT / "input" / name) for name in sources}, "source_paths": sources,
            "questions_sha256": digest(RECORD / "questions.jsonl"), "split_sha256": digest(RECORD / "split.json"),
            "models_sha256": digest(RECORD / "models.json"), "models": models(),
            "protected_before": protected_files(), "counts": {"questions": len(rows), "chunks": len(chunks),
                "documents": len({c["doc_id"] for c in chunks}),
                "original_release_dev": len(read_jsonl(ROOT / "eval/golden/dev.jsonl")),
                "selected_golden_dev": len(rows), "yaml": 0, "not_selected_release_dev": 0},
            "protocol": {"candidate_k": 50, "bm25": {"k1": 1.5, "b": 0.75}, "ordinary_token_budget": 2500,
                "budget_tokenizer": models()[0]["id"], "budget_revision": models()[0]["revision"],
                "weight_grid": list(WEIGHTS), "fixed_weight": 0.6, "tuning_objective": "mean ordinary chunk Recall@10",
                "tie_break": "closest to 0.6, then lower weight", "timed_passes": 3,
                "query_batch_size": 1, "order_seeds": [SEED + p for p in range(3)],
                "first_measurement": "fixed 0.6 before grid; raw ranks only during timing; compute tuning scores and freeze weights before validation scoring",
                "partitions": {k: len(v) for k, v in split["ids"].items()},
                "isolated": "production routing/interleaving/dedup/packing; no exact promotion or quantity bypass",
                "integrated": "production routing, exact promotion, quantity route, filtering, dedup and packing",
                "test_split_executed": False, "network": "socket connect/connect_ex/create_connection/DNS denied during measurement"}}


def download_models():
    from huggingface_hub import snapshot_download

    for spec in models():
        folder = OUT / "models" / spec["key"]
        folder.mkdir(parents=True, exist_ok=True)
        path = snapshot_download(spec["id"], revision=spec["revision"],
                                 ignore_patterns=MODEL_IGNORE_PATTERNS)
        (folder / "snapshot.txt").write_text(path, encoding="utf-8")
        print("PREPARED", spec["id"], spec["revision"], flush=True)
