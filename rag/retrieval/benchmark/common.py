"""실험 경로와 입력 지문을 고정하고 측정 중 네트워크를 차단한다."""
from __future__ import annotations

import hashlib
import json
import os
import socket
import subprocess
from contextlib import contextmanager
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[3]
OUT = ROOT / "artifacts/seven_model_full_dev"
RECORD = OUT / "record"
SEED = 20261018
WEIGHTS = (0.2, 0.4, 0.6, 0.8)
MODEL_IGNORE_PATTERNS = ["onnx/*", "openvino/*", "assets/*", "*.png", "*.jpg", "*.bin", "trainer_state.json"]


def digest(path):
    result = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            result.update(block)
    return result.hexdigest()


def save_json(value, path):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False) + "\n", encoding="utf-8")


def models():
    return json.loads((ROOT / "docs/benchmarks/seven_model/models.json").read_text(encoding="utf-8"))


def source_fingerprints():
    paths = list((ROOT / "rag/retrieval").rglob("*.py"))
    paths += list((ROOT / "rag/validation").rglob("*.py"))
    paths += [ROOT / name for name in ("rag/config.py", "rag/evaluation/ir.py")]
    return {str(path.relative_to(ROOT)).replace("\\", "/"): digest(path) for path in sorted(paths)}


def source_identity():
    paths = ["rag/retrieval", "rag/validation", "rag/config.py", "rag/evaluation/ir.py"]
    status = subprocess.check_output(["git", "status", "--porcelain", "--", *paths], cwd=ROOT, text=True)
    assert not status.strip(), "Benchmark source has uncommitted changes"
    commit = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip()
    return {"source_commit": commit, "source_hashes": source_fingerprints()}


def verify_source(manifest):
    identity = source_identity()
    assert identity["source_commit"] == manifest["base_commit"], "Benchmark source commit changed"
    assert identity["source_hashes"] == manifest.get("source_hashes"), "Benchmark source hashes changed or missing"
    return identity


def offline_environment():
    os.environ.update(HF_HUB_OFFLINE="1", TRANSFORMERS_OFFLINE="1", HF_HUB_DISABLE_TELEMETRY="1",
                      LANGFUSE_TRACING_ENABLED="false", LANGFUSE_PUBLIC_KEY="", LANGFUSE_SECRET_KEY="",
                      RAGAS_DO_NOT_TRACK="true", DO_NOT_TRACK="1", TOKENIZERS_PARALLELISM="false")


@contextmanager
def no_network():
    attempts = []

    def blocked(*args, **kwargs):
        attempts.append(str(args[1:] if isinstance(args[0], socket.socket) else args))
        raise RuntimeError("Benchmark outbound connections are blocked")

    with patch.object(socket.socket, "connect", blocked), patch.object(socket.socket, "connect_ex", blocked), \
            patch.object(socket, "create_connection", blocked), patch.object(socket, "getaddrinfo", blocked):
        yield attempts


def protected_files():
    paths = [ROOT / "config.yaml", ROOT / "artifacts/active.json", ROOT / "artifacts/chunks.jsonl",
             ROOT / "artifacts/docs.jsonl", ROOT / "artifacts/eval_set.jsonl"]
    paths += list((ROOT / "artifacts").rglob("*usage*.csv"))
    paths += [p for p in (ROOT / "artifacts/index").rglob("*") if p.is_file()]
    active = json.loads((ROOT / "artifacts/active.json").read_text(encoding="utf-8"))
    for name in ("docs_meta_path", "chunks_path", "bm25_path", "faiss_dir"):
        path = ROOT / active[name]
        if path.is_dir():
            paths.extend(p for p in path.rglob("*") if p.is_file())
        else:
            paths.append(path)
    return {str(p.relative_to(ROOT)).replace("\\", "/"): digest(p) for p in sorted(set(paths)) if p.exists()}
