"""출력 경로 보호와, 이 브랜치가 golden_pipeline/ 밖을 바꾸지 않았는지 확인한다."""
import subprocess

import pytest

from golden_pipeline import storage

REPO = storage.PACKAGE.parent


@pytest.mark.parametrize("path", [
    REPO / "data" / "golden.jsonl",
    REPO / "artifacts" / "eval_set.jsonl",
    REPO / "eval" / "golden_set.jsonl",
    REPO / "golden_pipeline" / "configs" / "x.json",
    REPO / "golden_pipeline" / "outputs" / ".." / "x.json",
    REPO / "golden_pipeline" / "outputs_other" / "x.json",
])
def test_guard_refuses_paths_outside_outputs(path):
    with pytest.raises(storage.OutputPathError):
        storage.guard(path)


def test_guard_accepts_paths_inside_outputs():
    path = REPO / "golden_pipeline" / "outputs" / "goldens" / "numeric" / "x.jsonl"
    assert storage.guard(path) == path.resolve()


@pytest.mark.parametrize("run_id", ["../../../../data", "..", "a/b", "../../../../../../artifacts"])
def test_run_id_cannot_escape_its_run_directory(outputs, make_item, run_id):
    with pytest.raises(storage.OutputPathError):
        storage.write_run("numeric", "A", run_id, [make_item(run_id=run_id)])


def test_branch_changes_only_golden_pipeline():
    changed = subprocess.run(
        ["git", "diff", "--name-only", "origin/dev...HEAD"],
        cwd=REPO, capture_output=True, text=True, check=True,
    ).stdout.split()
    assert [path for path in changed if not path.startswith("golden_pipeline/")] == []
