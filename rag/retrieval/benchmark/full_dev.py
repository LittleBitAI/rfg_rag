"""정답 문자열 채점 필터 없이 릴리스 dev 전체와 원본 계획의 정확 근거를 복원한다."""
import json

from rag.config import read_jsonl
from rag.validation.evidence import _context_labels
from rag.validation.validation import load_eval_items
from rag.validation.local_inputs import local_input

from .common import ROOT


def reference_key(bundle_id, reference):
    return bundle_id, json.dumps(reference, sort_keys=True, ensure_ascii=False)


def plan_evidence(dev):
    needed = {reference_key(row["bundle_id"], ref) for row in dev for ref in row["evidence"]}
    found = {}
    paths = sorted((ROOT / "golden_pipeline/outputs/plans").glob("*.json"),
                   key=lambda path: (not path.name.startswith("v11-"), path.name))
    for path in paths:
        plan = json.loads(path.read_text(encoding="utf-8"))
        for bundle in plan["bundles"]:
            for unit in bundle["units"]:
                key = reference_key(bundle["bundle_id"], unit["ref"])
                if key in needed:
                    remember_evidence(found, key, unit["text"], path)
    assert set(found) == needed, "Some dev evidence lacks an exact saved plan reference"
    return found


def remember_evidence(found, key, text, path):
    if key in found:
        assert found[key]["text"] == text, "Conflicting text for the same exact evidence reference"
    else:
        found[key] = {"text": text, "path": path}


def restore_row(item, source, found):
    evidence = []
    for ref in source["evidence"]:
        saved = found[reference_key(source["bundle_id"], ref)]
        labels = _context_labels(saved["text"], source["context"])
        evidence.append({**ref, "golden_chunk_id": ref["chunk_id"], "text": saved["text"],
                         "context_labels": labels,
                         "evidence_plan": str(saved["path"].relative_to(ROOT)).replace("\\", "/")})
    return {**{k: v for k, v in item.items() if k not in ("conv", "golden_context", "golden_evidence")},
            "evidence": evidence}


def load_full_dev():
    dev_path = local_input(ROOT, "eval/golden/dev.jsonl")
    dev = read_jsonl(dev_path)
    found = plan_evidence(dev)
    source = {row["candidate_id"]: row for row in dev}
    items = load_eval_items([str(dev_path)])
    rows = [restore_row(item, source[item["id"]], found) for item in items]
    assert len(rows) == len(source)
    assert {row["id"] for row in rows} == set(source)
    paths = sorted({value["path"] for value in found.values()})
    return rows, paths
