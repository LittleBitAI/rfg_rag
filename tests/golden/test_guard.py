"""출력 경로 보호: golden_pipeline/outputs 밖(data/, artifacts/, eval/ 포함)으로는 쓰지 못한다."""
import pytest

from golden_pipeline import storage

REPO = storage.PACKAGE.parent


@pytest.mark.parametrize("path", [
    REPO / "data" / "golden.jsonl",
    REPO / "artifacts" / "eval_set.jsonl",
    REPO / "eval" / "golden" / "dev.jsonl",
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


@pytest.mark.parametrize("run_id", ["../../../../data", "..", "a/b"])
def test_run_id_cannot_escape_its_run_directory(outputs, make_item, run_id):
    with pytest.raises(storage.OutputPathError):
        storage.write_run("numeric", "A", run_id, [make_item(run_id=run_id)])
