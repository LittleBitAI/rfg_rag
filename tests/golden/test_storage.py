import json
import subprocess

import pytest

from golden_pipeline import storage
from golden_pipeline.schema import SchemaError
from golden_pipeline.state import transition


def read_jsonl(path):
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]


def validated(make_item, candidate_id, question, to, reason):
    return transition(make_item(candidate_id=candidate_id, question=question, validator_version="val-0.1"), to, reason)


def run_items(make_item):
    candidate = make_item(candidate_id="n-1")
    accepted = validated(make_item, "n-2", "계약 기간은?", "auto_validated", "통과")
    held = validated(make_item, "n-3", "하자 보수 기간은?", "held", "격자 미확인")
    rejected = validated(make_item, "n-4", "입찰 마감은?", "rejected", "근거와 답 불일치")
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
    items = run_items(make_item)
    storage.write_run("numeric", "A", "r1", items)
    with pytest.raises(ValueError, match="출시 상태"):
        storage.write_release("numeric", "v1", [items[1]])
    unregistered = transition({**items[1], "candidate_id": "n-x"}, "released", "출시")
    with pytest.raises(storage.CatalogError, match="등록되지 않았습니다"):
        storage.write_release("numeric", "v1", [unregistered])


@pytest.mark.parametrize("field", [
    "question", "answer", "method", "run_id", "evidence", "validator_version", "state_history",
])
def test_release_refuses_content_that_differs_from_its_registered_run(outputs, make_item, field):
    # candidate_id 만 카탈로그와 맞추고 내용·출처를 바꿔 끼운 항목이
    # 출시본과 매니페스트(원본 run)에 그대로 들어가던 결함을 막는다.
    items = run_items(make_item)
    storage.write_run("numeric", "A", "r1", items)
    other = make_item(question="바꿔 끼운 질문", answer="바꿔 끼운 답", method="B", run_id="r9", validator_version="val-9")
    other["evidence"][0]["chunk_id"] = "c-99"
    other = transition(other, "auto_validated", "다른 검증 기록")
    substituted = transition({**items[1], field: other[field]}, "released", "출시")

    with pytest.raises(storage.CatalogError, match="등록된 기록과 다릅니다"):
        storage.write_release("numeric", "v1", [substituted])
    assert not (outputs / "outputs/goldens/numeric/releases").exists()


def test_invalid_item_leaves_no_partial_run_so_the_run_id_can_be_retried(outputs, make_item):
    # 저장 도중 실패하면 run 폴더만 남아 같은 run_id 를 다시 쓸 수 없었다. 검증은 폴더를 만들기 전에 끝나야 한다.
    broken = validated(make_item, "n-1", "계약 기간은?", "auto_validated", "통과")
    broken["state_history"][0]["at"] = object()
    with pytest.raises(SchemaError):
        storage.write_run("numeric", "A", "r1", [broken])
    assert not (outputs / "outputs/goldens/numeric/runs").exists()

    storage.write_run("numeric", "A", "r1", run_items(make_item))


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
