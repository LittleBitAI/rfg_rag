import json
import subprocess

import pytest

from golden_pipeline import storage
from golden_pipeline.state import transition


def read_jsonl(path):
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]


def run_items(make_item):
    candidate = make_item(candidate_id="n-1")
    accepted = transition(make_item(candidate_id="n-2", question="계약 기간은?"), "auto_validated", "통과")
    held = transition(make_item(candidate_id="n-3", question="하자 보수 기간은?"), "held", "격자 미확인")
    rejected = transition(make_item(candidate_id="n-4", question="입찰 마감은?"), "rejected", "근거와 답 불일치")
    return [candidate, accepted, held, rejected]


def ids(path):
    return [item["candidate_id"] for item in read_jsonl(path)]


def test_run_writes_state_files_failure_memory_and_manifest(outputs, make_item):
    (outputs / "configs" / "run.yaml").write_text("seed: 1\n", encoding="utf-8")
    (outputs / "prompts" / "numeric.txt").write_text("질문을 만드세요\n", encoding="utf-8")

    run_dir = storage.write_run("numeric", "A", "r1", run_items(make_item))

    assert run_dir == (outputs / "outputs/goldens/numeric/runs/A/r1").resolve()
    assert ids(run_dir / "candidates.jsonl") == ["n-1", "n-2", "n-3", "n-4"]
    assert ids(run_dir / "accepted.jsonl") == ["n-2"]
    assert ids(run_dir / "review.jsonl") == ["n-3"]
    assert ids(run_dir / "rejected.jsonl") == ["n-4"]
    memory = read_jsonl(outputs / "outputs/goldens/numeric/failure_memory/A_r1.jsonl")
    assert [(m["candidate_id"], m["reason"]) for m in memory] == [("n-4", "근거와 답 불일치")]

    manifest = json.loads((run_dir / "manifest.json").read_text(encoding="utf-8"))
    head = subprocess.run(["git", "rev-parse", "HEAD"], capture_output=True, text=True, check=True).stdout.strip()
    assert manifest["code_commit"] == head
    assert manifest["config_snapshot"] == {"run.yaml": storage._sha256(outputs / "configs" / "run.yaml")}
    assert manifest["prompt_snapshot"] == {"numeric.txt": storage._sha256(outputs / "prompts" / "numeric.txt")}
    assert manifest["counts"] == {
        "candidates.jsonl": 4, "accepted.jsonl": 1, "rejected.jsonl": 1, "review.jsonl": 1,
    }


def test_existing_run_id_is_refused_not_overwritten(outputs, make_item):
    run_dir = storage.write_run("numeric", "A", "r1", [make_item(candidate_id="n-1")])
    before = (run_dir / "candidates.jsonl").read_bytes()

    with pytest.raises(FileExistsError):
        storage.write_run("numeric", "A", "r1", [make_item(candidate_id="n-9", question="다른 질문")])

    assert (run_dir / "candidates.jsonl").read_bytes() == before
    assert [entry["candidate_id"] for entry in storage.read_catalog()] == ["n-1"]


def test_release_writes_golden_and_refuses_existing_version(outputs, make_item):
    items = run_items(make_item)
    storage.write_run("numeric", "A", "r1", items)
    released = [transition(items[1], "released", "출시")]

    release_dir = storage.write_release("numeric", "v1", released)

    assert read_jsonl(release_dir / "golden.jsonl") == released
    manifest = json.loads((release_dir / "manifest.json").read_text(encoding="utf-8"))
    assert manifest["count"] == 1
    assert manifest["runs"] == ["A/r1"]
    assert manifest["golden_sha256"] == storage._sha256(release_dir / "golden.jsonl")
    before = (release_dir / "golden.jsonl").read_bytes()

    with pytest.raises(FileExistsError):
        storage.write_release("numeric", "v1", [transition(items[2], "released", "출시")])
    assert (release_dir / "golden.jsonl").read_bytes() == before


def test_release_refuses_items_not_released_or_not_in_catalog(outputs, make_item):
    storage.write_run("numeric", "A", "r1", [make_item(candidate_id="n-1")])
    with pytest.raises(ValueError, match="출시 상태"):
        storage.write_release("numeric", "v1", [make_item(candidate_id="n-1")])
    with pytest.raises(storage.CatalogError):
        storage.write_release("numeric", "v1", [make_item(candidate_id="n-x", state="released")])


def test_same_item_under_second_topic_is_refused(outputs, make_item):
    storage.write_run("numeric", "A", "r1", [make_item(candidate_id="n-1")])
    copied = make_item(candidate_id="n-1", primary_topic="table", secondary_tags=["numeric"])
    same_evidence = make_item(candidate_id="t-1", primary_topic="table", secondary_tags=[])

    with pytest.raises(storage.CatalogError, match="이미 등록"):
        storage.write_run("table", "A", "r1", [copied])
    with pytest.raises(storage.CatalogError, match="numeric 주제 소유"):
        storage.write_run("table", "A", "r1", [same_evidence])

    assert not (outputs / "outputs/goldens/table/runs").exists()
    assert [(e["candidate_id"], e["topic"]) for e in storage.read_catalog()] == [("n-1", "numeric")]
