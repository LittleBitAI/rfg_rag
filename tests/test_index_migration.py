import io
import json
import subprocess
import sys
import tarfile
from pathlib import Path

from test_indexing import snapshot


ROOT = Path(__file__).resolve().parents[1]
BASE = "2f746f38dba1d5fdbdfc924fbce3eac3297081b7"


def export_base(target):
    data = subprocess.check_output(["git", "archive", BASE, "rag"], cwd=ROOT)
    with tarfile.open(fileobj=io.BytesIO(data)) as archive:
        archive.extractall(target)


def run_revision(code, operation, artifacts, failure=None):
    command = [sys.executable, str(ROOT / "tests/index_migration_worker.py"), str(code),
               str(ROOT / "tests"), operation, str(artifacts)]
    result = subprocess.run(command, capture_output=True, text=True, encoding="utf-8", timeout=120)
    if failure:
        assert result.returncode != 0 and failure in result.stderr, result.stderr
        return None
    assert result.returncode == 0, result.stderr
    record = json.loads(next(line[7:] for line in result.stdout.splitlines() if line.startswith("RESULT ")))
    assert record["loaded_source"] == str((code / "rag/retrieval/indexing.py").resolve())
    return record


def test_stopped_reader_downgrade_restores_base_artifacts_and_search_after_upgrade(tmp_path):
    base = tmp_path / "base"
    export_base(base)
    active = tmp_path / "active"
    initial = run_revision(base, "build", active)
    assert initial["corpus_size"] == initial["score_length"] == 3
    assert initial["query_tokens"] == ["개인", "정보", "처리", "시스템"]
    assert initial["bm25_hits"] == ["0"]
    baseline = snapshot(active / "index")
    run_revision(ROOT, "search", active, failure="BM25 tokenizer mismatch")
    assert snapshot(active / "index") == baseline
    upgraded = run_revision(ROOT, "build", active)
    assert upgraded["corpus_size"] == upgraded["score_length"] == 3
    assert upgraded["query_tokens"] == ["개인정보처리시스템"]
    assert upgraded["bm25_hits"] == ["0"]
    head_artifacts = snapshot(active / "index")
    negative = run_revision(base, "search", active)
    assert negative["corpus_size"] == negative["score_length"] == 2
    assert "broadcast" in negative["search_error"]

    (active / "index").rename(active / "index.before-downgrade")
    failed = tmp_path / "failed-downgrade-staging"
    run_revision(base, "fail-build", failed, failure="injected rebuild failure")
    assert not (active / "index").exists()
    run_revision(base, "search", active, failure="faiss.index")
    assert snapshot(active / "index.before-downgrade") == head_artifacts

    staged = tmp_path / "downgrade-staging"
    run_revision(base, "build", staged)
    assert run_revision(base, "search", staged) == initial
    assert set(snapshot(staged / "index")) == {
        "faiss.index", "bm25_tokens.json", "quantities.jsonl", "quantity_phrases.json", "quantity_vectors.npy"}
    assert snapshot(staged / "index") == baseline
    (staged / "index").rename(active / "index")
    assert run_revision(base, "search", active) == initial
    assert snapshot(active / "index") == baseline
    assert snapshot(active / "index.before-downgrade") == head_artifacts
