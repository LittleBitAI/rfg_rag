"""깨끗한 업데이트와 비공개 인계 모두에서 원본을 손실 없이 복원한다."""
import hashlib
import json
import subprocess
import sys

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from frontend.ocr_select import review
from rag.preprocessing import ocr_captions
from rag.retrieval.benchmark import full_dev, prepare
from rag.validation import local_inputs, validation
from test_eval_items import _release_row


@pytest.fixture
def private_bundle(tmp_path):
    folder = tmp_path / "private-bundle"
    golden = folder / "golden"
    golden.mkdir(parents=True)
    dev = _release_row("numeric", "83일", {"value": "83", "unit": "일"})
    payloads = {"dev": (json.dumps(dev) + "\n").encode(),
                "test": b'{"candidate_id":"synthetic-test-only"}\n'}
    for split, raw in payloads.items():
        (golden / f"{split}.jsonl").write_bytes(raw)
    manifest = {split: {"sha256": hashlib.sha256(raw).hexdigest()} for split, raw in payloads.items()}
    (golden / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
    (folder / "eval_questions.yaml").write_text("[]\n", encoding="utf-8")
    caption = {"doc_id": "synthetic-caption-doc", "image_sha256": "synthetic-image",
               "format": "hwp", "image_name": "synthetic.png", "marker_start": 0,
               "text": "독립적으로 만든 그림 설명", "engine": "synthetic-engine", "image_type": "diagram"}
    (folder / "ocr_captions.jsonl").write_text(json.dumps(caption) + "\n", encoding="utf-8")
    return folder


@pytest.mark.parametrize("conflict", ["eval_questions.yaml", "ocr_captions.jsonl"])
def test_private_handoff_is_validated_idempotent_and_never_overwrites(tmp_path, private_bundle, conflict):
    root = tmp_path / "checkout"
    root.mkdir()
    destination = local_inputs.restore_inputs(root, private_bundle)
    expected = {relative: (private_bundle / relative).read_bytes() for relative in local_inputs.INPUTS.values()}
    assert local_inputs.restore_inputs(root, private_bundle) == destination
    assert {relative: (destination / relative).read_bytes() for relative in expected} == expected
    for logical, relative in local_inputs.INPUTS.items():
        assert local_inputs.local_input(root, logical) == destination / relative
        assert local_inputs.local_input(root, root / logical) == destination / relative
    (destination / conflict).write_text("existing private input\n", encoding="utf-8")
    with pytest.raises(FileExistsError):
        local_inputs.restore_inputs(root, private_bundle)
    assert (destination / conflict).read_text(encoding="utf-8") == "existing private input\n"


@pytest.mark.parametrize("split", ("dev", "test"))
def test_corrupt_handoff_writes_nothing(tmp_path, private_bundle, split):
    (private_bundle / f"golden/{split}.jsonl").write_bytes(b"changed\n")
    root = tmp_path / "checkout"
    root.mkdir()
    with pytest.raises(ValueError, match="manifest"):
        local_inputs.restore_inputs(root, private_bundle)
    assert not (root / "artifacts").exists()


@pytest.mark.parametrize("logical", ["eval/golden/dev.jsonl", "data/ocr_captions.jsonl"])
def test_shallow_checkout_without_private_bundle_names_the_restore_command(tmp_path, logical):
    with pytest.raises(FileNotFoundError, match="--from-directory"):
        local_inputs.local_input(tmp_path, logical)
    assert not (tmp_path / "artifacts").exists()


@pytest.mark.parametrize("first_reader", ["preprocessing", "get", "post"])
def test_clean_update_recovers_inputs_for_all_consumers(tmp_path, private_bundle, monkeypatch, first_reader):
    root = tmp_path / "checkout"
    root.mkdir()
    subprocess.run(["git", "init", "-q", str(root)], check=True)
    subprocess.run(["git", "config", "core.autocrlf", "false"], cwd=root, check=True)
    for logical, relative in local_inputs.INPUTS.items():
        target = root / logical
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes((private_bundle / relative).read_bytes())
    (root / ".gitignore").write_text("artifacts/\neval/golden/\neval/eval_questions.yaml\ndata/\n", encoding="utf-8")
    subprocess.run(["git", "add", "--force", "."], cwd=root, check=True)
    commit = ["git", "-c", "user.name=Synthetic", "-c", "user.email=synthetic@example.invalid",
              "-c", "commit.gpgsign=false", "commit", "-qm"]
    subprocess.run([*commit, "before untracking"], cwd=root, check=True)
    baseline = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=root, text=True).strip()
    subprocess.run(["git", "rm", "-qr", "eval", "data"], cwd=root, check=True)
    subprocess.run([*commit, "remove tracked private inputs"], cwd=root, check=True)
    assert not (root / "eval/golden/dev.jsonl").exists()
    monkeypatch.setattr(local_inputs, "RELEASE_SOURCE_COMMIT", baseline)
    monkeypatch.setattr(validation, "ROOT", root)
    monkeypatch.setattr(full_dev, "ROOT", root)
    monkeypatch.setattr(prepare, "ROOT", root)
    [item] = validation.load_eval_items(["eval/golden/dev.jsonl"])
    assert item["id"] == "synthetic-numeric" and item["key_facts"] == ["83일"]
    rows, _ = full_dev.load_full_dev()
    assert set(prepare.verify_provenance(rows)) == {"synthetic-numeric"}
    assert not (root / "artifacts/local_inputs/ocr_captions.jsonl").exists()
    _check_caption_consumers(root, monkeypatch, first_reader)
    assert not subprocess.check_output(["git", "status", "--porcelain"], cwd=root)
    for relative in local_inputs.INPUTS.values():
        assert (root / "artifacts/local_inputs" / relative).read_bytes() == (private_bundle / relative).read_bytes()


def _check_caption_consumers(root, monkeypatch, first_reader):
    monkeypatch.setattr(ocr_captions, "ROOT", root)
    monkeypatch.setattr(review, "ROOT", root)
    monkeypatch.setattr(review, "CAPTIONS", root / "data/ocr_captions.jsonl")
    monkeypatch.setattr(review, "IMAGES", root / "artifacts/images.jsonl")
    monkeypatch.setattr(review, "REVIEWS", root / "artifacts/reviews.jsonl")
    review.IMAGES.write_text('{"image_sha256":"synthetic-image","file":"synthetic.png"}\n', encoding="utf-8")
    expected = json.loads(local_inputs.input_bytes(root, "data/ocr_captions.jsonl", None))
    app = FastAPI()
    app.include_router(review.router)
    with TestClient(app) as client:
        readers = {"preprocessing": lambda: ocr_captions.load_captions(review.CAPTIONS),
                   "get": lambda: client.get("/ocr-api/review").raise_for_status(),
                   "post": lambda: client.post("/ocr-api/review/verdicts", json={
                       "image_sha256": expected["image_sha256"],
                       "transcription_sha256": review.transcription_sha256(expected),
                       "verdict": "ok"}).raise_for_status()}
        readers[first_reader]()
        assert ocr_captions.load_captions(review.CAPTIONS) == {expected["doc_id"]: [expected]}
        [card] = client.get("/ocr-api/review").json()
        assert card["text"] == expected["text"] and card["verdict"] == ("ok" if first_reader == "post" else None)
    assert not review.CAPTIONS.exists()


@pytest.mark.parametrize("group", ["evaluation", "captions", "both"])
def test_cli_restores_independent_private_bundles(tmp_path, private_bundle, monkeypatch, group):
    bundle = tmp_path / "handoff"
    selected = {logical: relative for logical, relative in local_inputs.INPUTS.items()
                if group == "both" or (logical in local_inputs.EVAL_INPUTS) == (group == "evaluation")}
    for relative in selected.values():
        target = bundle / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes((private_bundle / relative).read_bytes())
    restore = local_inputs.restore_inputs
    root = tmp_path / "checkout"
    monkeypatch.setattr(local_inputs, "restore_inputs", lambda **kw: restore(root, **kw))
    monkeypatch.setattr(sys, "argv", ["local_inputs", "--from-directory", str(bundle)])
    local_inputs.main()
    actual = {path.relative_to(root / "artifacts/local_inputs").as_posix()
              for path in (root / "artifacts/local_inputs").rglob("*") if path.is_file()}
    assert actual == set(selected.values())
    for relative in actual:
        assert (root / "artifacts/local_inputs" / relative).read_bytes() == (bundle / relative).read_bytes()


@pytest.mark.parametrize("partial", [False, True])
def test_cli_rejects_empty_or_partial_evaluation_bundle_without_writing(tmp_path, monkeypatch, partial):
    bundle = tmp_path / "handoff"
    bundle.mkdir()
    if partial:
        (bundle / "eval_questions.yaml").write_text("[]\n", encoding="utf-8")
    restore = local_inputs.restore_inputs
    root = tmp_path / "checkout"
    monkeypatch.setattr(local_inputs, "restore_inputs", lambda **kw: restore(root, **kw))
    monkeypatch.setattr(sys, "argv", ["local_inputs", "--from-directory", str(bundle)])
    with pytest.raises(FileNotFoundError if partial else SystemExit):
        local_inputs.main()
    assert not (root / "artifacts").exists()
