"""분포 계획: 주제별 개수, 문서 범위, 근거 묶음을 한 번 정해 파일 해시로 고정한다.

A · B · C 는 같은 계획 파일을 읽으므로 같은 근거 묶음과 같은 컨텍스트를 받는다.
근거 묶음은 근거 어댑터가 eligible 로 판정한 단위로만 만든다.
"""
import csv
import hashlib
import json
import re
import unicodedata
from collections import defaultdict
from pathlib import Path

from golden_pipeline import evidence, storage
from golden_pipeline.schema import EVIDENCE_FIELDS, TOPICS

# 줄 끝에 쪽 번호가 붙은 목차 줄 (1. 용역개요 02). 목차로 만든 질문은 RFP 내용을 묻지 않는다.
TOC_LINE = re.compile(r"\S\s+\d{1,3}\s*$")


def make_plan(plan_id, evidence_run, counts, max_context_chars, package=evidence.PACKAGE, skip_plans=(), side=None):
    """근거 어댑터 run 의 eligible 단위로 주제별 근거 묶음을 골라 outputs/plans/{plan_id}.json 에 쓴다.

    skip_plans 의 계획이 쓴 단위는 넣지 않는다. 묶음은 늘 같은 순서로 고르므로, 빼지 않으면 앞 계획의 묶음이 다시 뽑힌다.
    side 는 (분할 version, dev 또는 test) 이고, 주면 질문이 묻는 문서가 그 분할의 그쪽에 있는 묶음만 고른다.
    새 주제를 앞 분할에 더할 때 한쪽만 모자라면 그쪽 문서로만 다시 만들어, 반대쪽에 쓸 호출을 아낀다.
    """
    unknown = sorted(set(counts) - set(TOPICS))
    if unknown or not all(isinstance(n, int) and n > 0 for n in counts.values()):
        raise ValueError(f"counts 는 주제 {TOPICS} 별 양의 정수여야 합니다: {counts}")
    path = storage._child(storage.OUTPUTS / "plans", f"{plan_id}.json")
    run_dir = storage._child(storage.OUTPUTS / "evidence", evidence_run)
    pinned = storage._read_json(run_dir / "manifest.json")["pinned_sha256"]
    _check_package(package, pinned)
    units = [unit for unit in eligible_units(run_dir, package) if not _is_toc(unit["text"])]
    names = doc_names(package, {unit["ref"]["doc_sha"] for unit in units})

    specs = {topic: topic_spec(topic) for topic in TOPICS if topic in counts}
    bundles = []
    skipped = {skipped_id: load_plan(skipped_id) for skipped_id in skip_plans}
    used = {unit["unit_id"] for planned, _ in skipped.values() for bundle in planned["bundles"] for unit in bundle["units"]}
    wanted = _side_documents(*side) if side else None
    # 한 단위는 한 주제의 묶음에만 들어간다. 카탈로그가 같은 근거 묶음을 두 주제에 두지 않기 때문이다.
    for topic, (spec, _) in specs.items():
        groups = _groups(topic, spec, units, used, max_context_chars, names)
        if wanted is not None:
            groups = {doc: [b for b in found if b["doc_sha"] in wanted] for doc, found in groups.items()}
        chosen = _pick(groups, counts[topic])
        used.update(unit["unit_id"] for bundle in chosen for unit in bundle["units"])
        bundles += chosen

    plan = {
        "plan_id": plan_id,
        "created_at": storage._now(),
        "code_commit": storage._code_commit(),
        "evidence_run": evidence_run,
        "skipped_plans": {skipped_id: sha for skipped_id, (_, sha) in skipped.items()},
        "side": side and {"split": side[0], "part": side[1],
                          "manifest_sha256": storage._sha256(storage.OUTPUTS / "splits" / side[0] / "manifest.json")},
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


def document_units(run_dir, package, docs):
    """문서 SHA → 그 문서의 모든 근거 단위(eligible 과 held) {unit_id, text}, 패키지 순서대로.

    문서에 무엇이 없음을 보이려면 보류된 단위(UNVERIFIED 원문, 범위 없는 OCR, 원본 그리드 셀)까지 읽어야 한다.
    eligible 만 보면 보류된 글에 든 답을 놓친다. 원본 그리드 셀의 글은 원본 그리드 참고 파일에서 읽는다.
    """
    units = [unit for unit in evidence._iter_jsonl(run_dir / "units.jsonl") if unit["doc_sha"] in docs]
    elements = _elements(package, {unit["element_id"] for unit in units if unit["chunk_id"]})
    cells = {
        f"grid:{grid['source_document_sha256']}:{grid['stream']}:{grid['control']}:{cell['row']}:{cell['col']}": cell["text"]
        for grid in evidence._iter_jsonl(package / evidence.GRIDS) if grid["source_document_sha256"] in docs
        for cell in grid["cells"]
    }
    found = defaultdict(list)
    for unit in units:
        text = _unit_text(unit, elements[unit["element_id"]]) if unit["chunk_id"] else cells[unit["unit_id"]]
        found[unit["doc_sha"]].append({"unit_id": unit["unit_id"], "text": text})
    return found


def _side_documents(version, part):
    """분할 version 의 part(dev · test) 질문이 묻는 문서들. 파일이 분할 매니페스트의 SHA-256 과 다르면 멈춘다."""
    split_dir = storage._child(storage.OUTPUTS / "splits", version)
    if storage._sha256(split_dir / f"{part}.jsonl") != storage._read_json(split_dir / "manifest.json")[part]["sha256"]:
        raise ValueError(f"분할 {version} 의 {part}.jsonl 이 매니페스트의 SHA-256 과 다릅니다")
    return {asked_document(item) for item in storage._read_jsonl(split_dir / f"{part}.jsonl")}


def asked_document(item):
    """질문이 묻는 문서의 SHA. 대개 근거의 문서이고, unanswerable 은 근거와 다른 문서라 계획 묶음의 doc_sha 다.

    생성 뒤 계획 파일이 바뀌었으면 묶음의 doc_sha 가 질문을 만들 때의 문서가 아닐 수 있으므로 멈춘다.
    """
    if item["primary_topic"] != "unanswerable":
        return item["evidence"][0]["doc_sha"]
    run_dir = storage.run_path(item["primary_topic"], item["method"], item["run_id"])
    generated = storage._read_json(run_dir / "manifest.json")["generation"]
    planned, sha = load_plan(generated["plan_id"])
    if sha != generated["plan_sha256"]:
        raise ValueError(f"계획 {generated['plan_id']} 가 생성 run {item['run_id']} 을 만든 뒤 바뀌었습니다. 새 run 을 만드세요")
    return next(bundle["doc_sha"] for bundle in planned["bundles"] if bundle["bundle_id"] == item["bundle_id"])


def doc_names(package, docs):
    """문서 SHA → {"agency": 발주 기관, "title": 사업 이름}. 문서 98개 가운데 어느 문서의 질문인지 밝히는 데 쓴다.

    v11 레코드의 source_paths 첫 파일 이름("기관_사업명.hwp")으로 패키지 옆 data_list.csv 의 정리된 발주 기관을 찾고,
    사업 이름은 파일 이름의 _ 뒤에서 앞머리 [재공고] 같은 표시를 뺀 것이다. 파일 이름이 잘려 사업 이름도 잘려 있을 수 있다.
    한 기관에 문서가 여럿이라 기관 이름만으로는 문서를 가리지 못한다.
    """
    with (package.parent / "data_list.csv").open(encoding="utf-8-sig") as f:
        agencies = {unicodedata.normalize("NFC", row["파일명"]): row["발주기관"] for row in csv.DictReader(f)}
    names = {}
    for record in evidence._iter_jsonl(package / evidence.RECORDS):
        if record["doc_id"] in docs and record["doc_id"] not in names:
            # 원본 파일 이름 일부는 한글이 자모로 풀린 NFD 라 csv 의 NFC 이름과 맞지 않는다.
            file = Path(unicodedata.normalize("NFC", record["source_paths"][0]))
            title = re.sub(r"^(\[[^\]]*\])+", "", file.stem.split("_", 1)[-1]).strip()
            names[record["doc_id"]] = {"agency": agencies[file.name], "title": title}
    return names


def _is_toc(text):
    lines = [line for line in text.splitlines() if line.strip()]
    return len(lines) >= 2 and 2 * sum(bool(TOC_LINE.search(line)) for line in lines) >= len(lines)


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
        if topic == "multi_hop":
            windows = _spanning(doc_units, size)
        else:
            windows = [doc_units[i:i + size] for i in range(0, len(doc_units) - size + 1, size)]
        windows = [_with_headers(window, headers) for window in windows]
        bundles = [_bundle(topic, window, names[doc]) for window in windows if window]
        groups[doc] = [b for b in bundles if len(b["context"]) <= max_context_chars]
    if topic == "unanswerable":
        groups = {doc: [_borrowed(bundle, doc, names) for bundle in bundles] for doc, bundles in groups.items()}
    return groups


def _borrowed(bundle, source, names):
    """unanswerable 묶음은 문서 A(source)의 근거로 다른 문서 B 에 묻는다. doc_sha · doc 는 질문이 묻는 문서 B 다.

    B 는 문서를 SHA 차례로 늘어놓은 고리에서 A 의 맞은편 문서다. 늘 같은 B 가 골라진다.
    ponytail: 맞은편 문서가 비슷한 사업이면 속성이 B 에도 있어 거절된다. 거절이 많으면 사업 분야가 다른 문서를 고른다.
    """
    docs = sorted(names)
    target = docs[(docs.index(source) + len(docs) // 2) % len(docs)]
    return {**bundle, "doc_sha": target, "doc": names[target]}


def _spanning(units, size):
    """이어진 단위 size 개씩 묶되, 청크 둘 이상에 걸친 묶음만 낸다 (multi_hop).

    한 청크 안의 단위만 받은 생성기는 청크 둘을 이어야 하는 질문을 만들 수 없어 그 묶음은 늘 거절된다.
    """
    windows, start = [], 0
    while start + size <= len(units):
        window = units[start:start + size]
        if len({unit["ref"]["chunk_id"] for unit in window}) >= 2:
            windows.append(window)
            start += size
        else:
            start += 1
    return windows


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


def _bundle(topic, units, doc):
    """근거 묶음. doc 은 그 문서의 발주 기관 · 사업 이름이고, 생성이 질문 앞에 붙인다."""
    labelled = [{"label": f"E{i}", **unit} for i, unit in enumerate(units, 1)]
    ids = "\n".join(unit["unit_id"] for unit in units)
    chunks = list(dict.fromkeys(unit["ref"]["chunk_id"] for unit in units))

    def header(unit):
        label = unit["label"]
        # 표 행은 | 로 이은 글이라, 표시가 없으면 생성기는 어느 행이 열 이름을 가진 머리글인지 알 수 없다.
        if _table_row(unit) == 0:
            label += " · 머리글 행"
        # multi_hop 은 청크 둘을 이어야 하는데, 라벨만으로는 생성기가 어느 근거가 같은 청크인지 알 수 없다.
        if topic == "multi_hop":
            label += f" · 청크 {chunks.index(unit['ref']['chunk_id']) + 1}"
        return label

    return {
        "bundle_id": "b-" + hashlib.sha256(ids.encode("utf-8")).hexdigest()[:16],
        "topic": topic,
        "doc_sha": units[0]["ref"]["doc_sha"],
        "doc": doc,
        "units": labelled,
        "context": "\n\n".join(f"[{header(unit)}]\n{unit['text']}" for unit in labelled),
    }


def _coverage(bundles):
    coverage = defaultdict(lambda: defaultdict(int))
    for bundle in bundles:
        coverage[bundle["topic"]][bundle["doc_sha"]] += 1
    return {topic: dict(docs) for topic, docs in coverage.items()}
