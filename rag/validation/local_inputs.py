"""추적 해제된 평가 입력과 OCR 캡션을 무시된 로컬 보관소에 복원한다."""
import argparse
import hashlib
import json
import subprocess
from pathlib import Path

from rag.config import ROOT


RELEASE_SOURCE_COMMIT = "31a44d81fc044a50cd90f4b06e73ec114a1a419d"
EVAL_INPUTS = {"eval/golden/dev.jsonl": "golden/dev.jsonl",
               "eval/golden/test.jsonl": "golden/test.jsonl",
               "eval/golden/manifest.json": "golden/manifest.json",
               "eval/eval_questions.yaml": "eval_questions.yaml"}
INPUTS = {**EVAL_INPUTS, "data/ocr_captions.jsonl": "ocr_captions.jsonl"}


def input_bytes(root, logical, source):
    relative = INPUTS[logical]
    if source is not None:
        return (source / relative).read_bytes()
    for path in (root / "artifacts/local_inputs" / relative, root / logical):
        if path.is_file():
            return path.read_bytes()
    result = subprocess.run(["git", "show", f"{RELEASE_SOURCE_COMMIT}:{logical}"], cwd=root,
                            stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    if result.returncode:
        raise FileNotFoundError("Local inputs are missing. Restore an owner-provided private bundle with "
                                "python -m rag.validation.local_inputs --from-directory PATH. No network recovery is attempted.")
    return result.stdout


def validate_release(payloads):
    if "golden/manifest.json" not in payloads:
        return
    manifest = json.loads(payloads["golden/manifest.json"])
    for split in ("dev", "test"):
        actual = hashlib.sha256(payloads[f"golden/{split}.jsonl"]).hexdigest()
        if actual != manifest[split]["sha256"]:
            raise ValueError(f"Private {split} release does not match its manifest; nothing was restored")


def restore_inputs(root=ROOT, source=None, inputs=INPUTS):
    root = Path(root)
    source = Path(source) if source is not None else None
    payloads = {relative: input_bytes(root, logical, source) for logical, relative in inputs.items()}
    validate_release(payloads)
    destination = root / "artifacts/local_inputs"
    for name, raw in payloads.items():
        target = destination / name
        if target.exists() and target.read_bytes() != raw:
            raise FileExistsError("Private input destination differs; existing inputs were not overwritten")
    for name, raw in payloads.items():
        target = destination / name
        target.parent.mkdir(parents=True, exist_ok=True)
        if not target.exists():
            with target.open("xb") as stream:
                stream.write(raw)
    return destination


def local_input(root, path):
    root, path = Path(root), Path(path)
    if path.is_absolute():
        try:
            path = path.relative_to(root)
        except ValueError:
            return path
    logical = path.as_posix()
    if logical not in INPUTS:
        return root / path
    target = root / "artifacts/local_inputs" / INPUTS[logical]
    if not target.is_file():
        inputs = EVAL_INPUTS if logical in EVAL_INPUTS else {logical: INPUTS[logical]}
        restore_inputs(root, inputs=inputs)
    return target


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--from-directory", type=Path)
    args = parser.parse_args()
    inputs = INPUTS
    if args.from_directory is not None:
        inputs = {logical: relative for logical, relative in INPUTS.items()
                  if (args.from_directory / relative).is_file()}
        if not inputs:
            parser.error("Private bundle contains no supported local inputs")
        if any(logical in EVAL_INPUTS for logical in inputs):
            inputs = {**inputs, **EVAL_INPUTS}
    restore_inputs(source=args.from_directory, inputs=inputs)
    print("Local inputs ready under ignored artifacts/local_inputs; no inference or network calls.")


if __name__ == "__main__":
    main()
