"""깨끗한 업데이트와 비공개 인계 모두에서 원본을 손실 없이 복원한다."""
import hashlib
import json
import subprocess

import pytest

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
    return folder


def test_private_handoff_is_validated_idempotent_and_never_overwrites(tmp_path, private_bundle):
    root = tmp_path / "checkout"
    root.mkdir()
    destination = local_inputs.restore_inputs(root, private_bundle)
    expected = {relative: (private_bundle / relative).read_bytes() for relative in local_inputs.INPUTS.values()}
    assert local_inputs.restore_inputs(root, private_bundle) == destination
    assert {relative: (destination / relative).read_bytes() for relative in expected} == expected
    for logical, relative in local_inputs.INPUTS.items():
        assert local_inputs.local_input(root, logical) == destination / relative
        assert local_inputs.local_input(root, root / logical) == destination / relative
    (destination / "eval_questions.yaml").write_text("existing private input\n", encoding="utf-8")
    with pytest.raises(FileExistsError):
        local_inputs.restore_inputs(root, private_bundle)
    assert (destination / "eval_questions.yaml").read_text(encoding="utf-8") == "existing private input\n"


@pytest.mark.parametrize("split", ("dev", "test"))
def test_corrupt_handoff_writes_nothing(tmp_path, private_bundle, split):
    (private_bundle / f"golden/{split}.jsonl").write_bytes(b"changed\n")
    root = tmp_path / "checkout"
    root.mkdir()
    with pytest.raises(ValueError, match="manifest"):
        local_inputs.restore_inputs(root, private_bundle)
    assert not (root / "artifacts").exists()


def test_shallow_checkout_without_private_bundle_names_the_restore_command(tmp_path):
    with pytest.raises(FileNotFoundError, match="--from-directory"):
        local_inputs.local_input(tmp_path, "eval/golden/dev.jsonl")
    assert not (tmp_path / "artifacts").exists()


def test_clean_update_recovers_release_and_validation_and_benchmark_can_read_it(tmp_path, private_bundle, monkeypatch):
    root = tmp_path / "checkout"
    root.mkdir()
    subprocess.run(["git", "init", "-q", str(root)], check=True)
    subprocess.run(["git", "config", "core.autocrlf", "false"], cwd=root, check=True)
    for logical, relative in local_inputs.INPUTS.items():
        target = root / logical
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes((private_bundle / relative).read_bytes())
    (root / ".gitignore").write_text("artifacts/\neval/golden/\neval/eval_questions.yaml\n", encoding="utf-8")
    subprocess.run(["git", "add", "--force", "."], cwd=root, check=True)
    commit = ["git", "-c", "user.name=Synthetic", "-c", "user.email=synthetic@example.invalid",
              "-c", "commit.gpgsign=false", "commit", "-qm"]
    subprocess.run([*commit, "before untracking"], cwd=root, check=True)
    baseline = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=root, text=True).strip()
    subprocess.run(["git", "rm", "-qr", "eval"], cwd=root, check=True)
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
    assert not subprocess.check_output(["git", "status", "--porcelain"], cwd=root)
    for relative in local_inputs.INPUTS.values():
        assert (root / "artifacts/local_inputs" / relative).read_bytes() == (private_bundle / relative).read_bytes()
