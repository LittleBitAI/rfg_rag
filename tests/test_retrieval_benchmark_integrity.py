"""완료 기록과 무관한 소스·측정 파일이 집계에 들어오는 회귀를 막는다."""
import json
import shutil
import subprocess

import pytest

from rag.config import read_jsonl, write_jsonl
from rag.retrieval.benchmark import common, prepare, summarize, verify
from rag.retrieval.benchmark.common import save_json
from test_retrieval_benchmark_artifacts import local_record, write_gzip


@pytest.mark.parametrize("field", ("source_commit", "source_hashes"))
def test_prepare_rejects_changed_source(local_record, field):
    identity = common.source_identity()
    identity[field] = "c" * 40 if field == "source_commit" else {"search.py": "c" * 64}
    with pytest.raises(AssertionError, match="source"):
        prepare.freeze_inputs()


@pytest.mark.parametrize("entrypoint", ("verify", "summarize"))
@pytest.mark.parametrize("field", ("source_commit", "source_hashes"))
def test_mixed_model_source_is_rejected_before_scoring(local_record, monkeypatch, entrypoint, field):
    record = local_record
    path = record / "results/kure/complete.json"
    complete = json.loads(path.read_text(encoding="utf-8"))
    complete[field] = "c" * 40 if field == "source_commit" else {"search.py": "c" * 64}
    save_json(complete, path)
    monkeypatch.setattr(summarize, "RECORD", record)
    monkeypatch.setattr(summarize, "OUT", record / "results")
    monkeypatch.setattr(summarize, "choose_weights", lambda *args: pytest.fail("scoring reached"))
    with pytest.raises(AssertionError, match="source"):
        if entrypoint == "verify":
            verify.verify_record(record)
        else:
            summarize.summarize()


@pytest.mark.parametrize("field", ("context_chunk_ids", "doc_id", "chunk_id"))
@pytest.mark.parametrize("entrypoint", ("verify", "summarize"))
def test_rescored_result_changes_are_rejected(local_record, monkeypatch, field, entrypoint):
    record = local_record
    path = record / "results/kure/isolated-kiwi-0.6.jsonl.gz"
    rows = summarize.load_results(path)
    row = next(row for row in rows if row["partition"] == "validation")
    questions = {q["id"]: q for q in read_jsonl(record / "questions.jsonl")}
    metric = {"context_chunk_ids": "evidence_coverage", "doc_id": "doc_fused_recall_at_10",
              "chunk_id": "chunk_fused_recall_at_10"}[field]
    before = summarize.score_fields(row, questions)[metric]
    if field == "context_chunk_ids":
        row[field] = [row["ranked_candidates"][0]["chunk_id"]]
    else:
        row["ranked_candidates"][0][field] = "unreturned-id"
    assert summarize.score_fields(row, questions)[metric] != before
    rows = summarize.scored_rows(rows, questions)
    write_gzip(path, rows)
    monkeypatch.setattr(summarize, "RECORD", record)
    monkeypatch.setattr(summarize, "OUT", record / "results")
    monkeypatch.setattr(summarize, "choose_weights", lambda *args: pytest.fail("scoring reached"))
    with pytest.raises(AssertionError, match="artifact"):
        if entrypoint == "verify":
            verify.verify_record(record)
        else:
            summarize.summarize()


def test_changed_positive_latency_is_rejected(local_record):
    path = local_record / "results/kure/isolated-kiwi-0.6-latency.jsonl"
    rows = read_jsonl(path)
    rows[0]["milliseconds"] = 999.0
    write_jsonl(rows, path)
    with pytest.raises(AssertionError, match="artifact"):
        verify.verify_record(local_record)


def test_exports_retain_completion_time_bytes(local_record, monkeypatch):
    monkeypatch.setattr(summarize, "OUT", local_record / "results")
    monkeypatch.setattr(summarize, "RECORD", local_record / "export")
    spec = {"key": "kure", "id": "synthetic/model"}
    summarize.export_raw(spec)
    original = local_record / "results/kure"
    exported = local_record / "export/results/kure"
    manifest = json.loads((local_record / "manifest.json").read_text(encoding="utf-8"))
    verify.verify_completion(exported, spec, manifest)
    assert {p.name: p.read_bytes() for p in exported.iterdir()} == {p.name: p.read_bytes() for p in original.iterdir()}


def test_summarize_accepts_only_sealed_inputs_and_keeps_exports_verifiable(local_record, monkeypatch):
    measurements = local_record / "measurements"
    shutil.copytree(local_record / "results/kure", measurements / "kure")
    monkeypatch.setattr(summarize, "OUT", measurements)
    monkeypatch.setattr(summarize, "RECORD", local_record)
    summarize.summarize()
    assert (local_record / "quality.csv").is_file()
    assert (local_record / "latency.csv").is_file()
    verify.verify_record(local_record)


@pytest.mark.parametrize("field", ("source_hashes", "artifact_sha256"))
def test_unbound_historical_completion_is_rejected(local_record, field):
    path = local_record / "results/kure/complete.json"
    complete = json.loads(path.read_text(encoding="utf-8"))
    complete.pop(field)
    save_json(complete, path)
    with pytest.raises((AssertionError, KeyError)):
        verify.verify_record(local_record)


def test_dirty_and_committed_search_changes_cannot_reuse_a_source_freeze(tmp_path, monkeypatch):
    path = tmp_path / "rag/retrieval/benchmark/search.py"
    path.parent.mkdir(parents=True)
    path.write_text("VALUE = 1\n", encoding="utf-8")
    subprocess.run(["git", "init", "-q", str(tmp_path)], check=True)

    def commit():
        subprocess.run(["git", "add", "."], cwd=tmp_path, check=True)
        subprocess.run(["git", "-c", "user.name=Synthetic", "-c", "user.email=synthetic@example.invalid",
                        "-c", "commit.gpgsign=false", "commit", "-qm", "synthetic"], cwd=tmp_path, check=True)

    commit()
    monkeypatch.setattr(common, "ROOT", tmp_path)
    monkeypatch.setattr(common, "source_fingerprints", lambda: {"search.py": common.digest(path)})
    identity = common.source_identity()
    manifest = {"base_commit": identity["source_commit"], "source_hashes": identity["source_hashes"]}
    path.write_text("VALUE = 2\n", encoding="utf-8")
    with pytest.raises(AssertionError, match="source"):
        common.verify_source(manifest)
    commit()
    with pytest.raises(AssertionError, match="source"):
        common.verify_source(manifest)
