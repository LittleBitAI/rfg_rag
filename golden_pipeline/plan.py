"""분포 계획: 주제별 개수, 문서 범위, 근거 묶음을 한 번 정해 파일 해시로 고정한다.

A · B · C 는 같은 계획 파일을 읽으므로 같은 근거 묶음과 같은 컨텍스트를 받는다.
근거 묶음은 근거 어댑터가 eligible 로 판정한 단위로만 만든다.
"""
import hashlib
import json
import re
from collections import defaultdict
from pathlib import Path

from golden_pipeline import evidence, storage
from golden_pipeline.schema import EVIDENCE_FIELDS, TOPICS


def make_plan(plan_id, evidence_run, counts, max_context_chars, package=evidence.PACKAGE):
    """근거 어댑터 run 의 eligible 단위로 주제별 근거 묶음을 골라 outputs/plans/{plan_id}.json 에 쓴다."""
    unknown = sorted(set(counts) - set(TOPICS))
    if unknown or not all(isinstance(n, int) and n > 0 for n in counts.values()):
        raise ValueError(f"counts 는 주제 {TOPICS} 별 양의 정수여야 합니다: {counts}")
    path = storage._child(storage.OUTPUTS / "plans", f"{plan_id}.json")
    run_dir = storage._child(storage.OUTPUTS / "evidence", evidence_run)
    pinned = storage._read_json(run_dir / "manifest.json")["pinned_sha256"]
    _check_package(package, pinned)
    units = eligible_units(run_dir, package)
    names = doc_names(package, {unit["ref"]["doc_sha"] for unit in units})

    specs = {topic: topic_spec(topic) for topic in TOPICS if topic in counts}
    bundles, used = [], set()
    # 한 단위는 한 주제의 묶음에만 들어간다. 카탈로그가 같은 근거 묶음을 두 주제에 두지 않기 때문이다.
    for topic, (spec, _) in specs.items():
        chosen = _pick(_groups(topic, spec, units, used, max_context_chars, names), counts[topic])
        used.update(unit["unit_id"] for bundle in chosen for unit in bundle["units"])
        bundles += chosen

    plan = {
        "plan_id": plan_id,
        "created_at": storage._now(),
        "code_commit": storage._code_commit(),
        "evidence_run": evidence_run,
        "v11_manifest_sha256": pinned["manifest.json"],
        "topic_specs": {topic: sha for topic, (_, sha) in specs.items()},
        "max_context_chars": max_context_chars,
        "counts": {topic: counts[topic] for topic in specs},
        "planned": {topic: sum(b["topic"] == topic for b in bundles) for topic in specs},
        "coverage": _coverage(bundles),
        "bundles": bundles,
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("x", encoding="utf-8") as f:
        f.write(json.dumps(plan, ensure_ascii=False, indent=1) + "\n")
    return path


def load_plan(plan_id):
    """계획과 그 파일의 SHA-256 을 돌려준다. run 매니페스트는 이 해시로 어떤 계획을 썼는지 남긴다."""
    path = storage._child(storage.OUTPUTS / "plans", f"{plan_id}.json")
    return storage._read_json(path), storage._sha256(path)


def topic_spec(topic):
    """주제 명세(configs/topics/{topic}.json)와 그 파일의 SHA-256."""
    path = storage.CONFIGS / "topics" / f"{topic}.json"
    return storage._read_json(path), storage._sha256(path)


def eligible_units(run_dir, package):
    """eligible 판정을 받은 단위만, 근거 참조 필드와 패키지에서 읽은 본문을 붙여 패키지 순서대로 돌려준다."""
    eligible = {
        row["unit_id"] for row in evidence._iter_jsonl(run_dir / "judgments.jsonl") if row["judgment"] == "eligible"
    }
    units = [
        {"unit_id": unit["unit_id"], "ref": {name: unit[name] for name in EVIDENCE_FIELDS}}
        for unit in evidence._iter_jsonl(run_dir / "units.jsonl") if unit["unit_id"] in eligible
    ]
    elements = _elements(package, {unit["ref"]["element_id"] for unit in units})
    for unit in units:
        unit["text"] = _unit_text(unit["ref"], elements[unit["ref"]["element_id"]])
    return [unit for unit in units if unit["text"].strip()]


def doc_names(package, docs):
    """문서 SHA → 원본 파일 이름(확장자 뺌, "발주 기관_사업명"). v11 레코드의 source_paths 첫 파일에서 읽는다.

    문서 98개 가운데 어느 문서의 질문인지 밝히려면 생성기가 문서 이름을 알아야 한다. 파일 이름은 잘려 있을 수 있다.
    """
    names = {}
    for record in evidence._iter_jsonl(package / evidence.RECORDS):
        if record["doc_id"] in docs and record["doc_id"] not in names:
            names[record["doc_id"]] = Path(record["source_paths"][0]).stem
    return names


def _check_package(package, pinned):
    """근거 어댑터가 판정한 패키지와 지금 읽을 패키지가 같아야 본문이 판정과 맞는다."""
    for name, sha in pinned.items():
        if storage._sha256(package / name) != sha:
            raise evidence.PackageMismatch(f"{name} SHA-256 이 근거 어댑터 run 에 고정된 값과 다릅니다")


def _elements(package, wanted):
    elements = {}
    for element in evidence._iter_jsonl(package / evidence.ELEMENTS):
        if element["element_id"] in wanted:
            cells = (element["table"] or {}).get("cells", [])
            elements[element["element_id"]] = {
                "text": element[element["location"]["span_text_field"]],
                "cells": sorted(cells, key=lambda cell: (cell["row"], cell["col"])),
            }
    return elements


def _unit_text(ref, element):
    """글자 span 은 요소 본문의 그 구간, 표 행은 그 행 칸들을 | 로 이은 것이다."""
    location = ref["location"]
    if location["kind"] == "char":
        return element["text"][location["start"]:location["end"]]
    return " | ".join(cell["text"] for cell in element["cells"] if cell["row"] == location["row"])


def _groups(topic, spec, units, used, max_context_chars, names):
    """문서마다 주제에 맞는 단위를 패키지 순서대로 bundle_units 개씩 묶는다. 컨텍스트가 한도를 넘는 묶음은 버린다."""
    # 다른 주제가 이미 가진 머리글 행은 붙이지 않는다. 그 표의 나머지 행은 묶음이 되지 못한다.
    headers = {unit["ref"]["element_id"]: unit for unit in units if _table_row(unit) == 0 and unit["unit_id"] not in used}
    pattern = re.compile(spec["pattern"]) if spec["pattern"] else None
    by_doc = defaultdict(list)
    for unit in units:
        is_table = unit["ref"]["location"]["kind"] == "table"
        if unit["unit_id"] in used or (spec["table_only"] and not is_table):
            continue
        if pattern is None or pattern.search(unit["text"]):
            by_doc[unit["ref"]["doc_sha"]].append(unit)
    size = spec["bundle_units"]
    groups = {}
    for doc, doc_units in sorted(by_doc.items()):
        chunks = [_with_headers(doc_units[i:i + size], headers) for i in range(0, len(doc_units) - size + 1, size)]
        bundles = [_bundle(topic, chunk, names[doc]) for chunk in chunks if chunk]
        groups[doc] = [b for b in bundles if len(b["context"]) <= max_context_chars]
    return groups


def _with_headers(chunk, headers):
    """표 행이 든 묶음 앞에 그 표의 머리글 행(논리 표 0행)을 붙인다. 열 이름 없이는 칸을 가리킬 수 없기 때문이다.

    머리글 행이 eligible 이 아니면 None 을 돌려 그 묶음을 버린다.
    """
    have = {unit["ref"]["element_id"] for unit in chunk if _table_row(unit) == 0}
    need = sorted({unit["ref"]["element_id"] for unit in chunk if _table_row(unit)} - have)
    if not all(element_id in headers for element_id in need):
        return None
    return [headers[element_id] for element_id in need] + chunk


def _table_row(unit):
    location = unit["ref"]["location"]
    return location["row"] if location["kind"] == "table" else None


def _pick(groups, count):
    """문서를 돌아가며 하나씩 골라 문서 범위를 넓힌다. 묶음이 모자라면 모자란 채로 둔다 (planned 에 남는다)."""
    queues = [list(bundles) for bundles in groups.values() if bundles]
    chosen = []
    while len(chosen) < count and any(queues):
        for queue in queues:
            if queue and len(chosen) < count:
                chosen.append(queue.pop(0))
    return chosen


def _bundle(topic, units, doc_name):
    """근거 묶음. 컨텍스트 첫 줄은 [문서] 이름이고 근거가 아니다 (검증기에는 근거 단위만 간다)."""
    labelled = [{"label": f"E{i}", **unit} for i, unit in enumerate(units, 1)]
    ids = "\n".join(unit["unit_id"] for unit in units)
    body = "\n\n".join(f"[{unit['label']}]\n{unit['text']}" for unit in labelled)
    return {
        "bundle_id": "b-" + hashlib.sha256(ids.encode("utf-8")).hexdigest()[:16],
        "topic": topic,
        "doc_sha": units[0]["ref"]["doc_sha"],
        "doc_name": doc_name,
        "units": labelled,
        "context": f"[문서] {doc_name}\n\n{body}",
    }


def _coverage(bundles):
    coverage = defaultdict(lambda: defaultdict(int))
    for bundle in bundles:
        coverage[bundle["topic"]][bundle["doc_sha"]] += 1
    return {topic: dict(docs) for topic, docs in coverage.items()}
