"""v11 전처리 패키지를 읽기만 하는 근거 어댑터.

두 사본(data/ 와 내려받은 폴더)의 파일 SHA-256 을 고정하고, 청크 → 요소 → 레코드 → 원문 단위를 ID 로 잇고,
근거 단위마다 자동 승인 가능(eligible) 또는 보류(held)를 이유와 함께 별도 판정 기록으로 남긴다.
패키지는 고치지 않으며, 패키지의 verify_package.py · load_retriever_inputs.py 를 import 하거나 실행하지 않는다.
"""
import argparse
import csv
import json
import re
import unicodedata
from collections import Counter, defaultdict
from pathlib import Path

from golden_pipeline import storage

REPO = storage.PACKAGE.parent
PACKAGE = REPO / "data" / "RFP_Preprocessing_Final_v11_Team"
RAW = REPO / "artifacts" / "raw"
CHUNKS = "final_chunks.jsonl"
ELEMENTS = "final_elements.jsonl"
RECORDS = "final_records.jsonl"
STATUS = "validation/source_status_merged.csv"
GRIDS = "validation/복구표_원본그리드_참고.jsonl"
PINNED = ("manifest.json", CHUNKS, ELEMENTS, RECORDS, STATUS, GRIDS)
# 패키지 README 의 검색 입력 Chunks 18,984 는 본문이 [IMAGE] 표시뿐인 청크를 뺀 수다.
IMAGE_ONLY = re.compile(r"(?:\s*\[IMAGE\]\s*)+")
IMAGE_RECORDS = ("image_ocr", "image_panel")
OCR_SCOPES = {
    "FULL_VISIBLE_TEXT": "full_visible_text",
    "PARTIAL_REGION": "partial_region",
    "PARTIAL_REGIONS": "partial_region",
}
SHA256 = re.compile(r"[0-9a-f]{64}")
GRID_UNVERIFIED = "원본 그리드 참고 파일은 검증되지 않았습니다 (매니페스트 original_grid_file)"


class PackageMismatch(ValueError):
    pass


def run(run_id, copy, package=PACKAGE, raw=RAW):
    """패키지를 고정·확인하고 근거 단위, 판정, artifacts/raw 연결, 매니페스트를 outputs/evidence/{run_id}/ 에 쓴다."""
    out = storage._child(storage.OUTPUTS / "evidence", run_id)
    hashes = pin(package, copy)
    pkg = load(package)
    counts, excluded, included = check_counts(pkg)
    grid_file = grid_file_verdict(pkg["grids"])
    pairs = [pair for chunk in included for pair in chunk_units(chunk, pkg)]
    pairs += [pair for grid in pkg["grids"] for pair in grid_units(grid, pkg)]
    units = [unit for unit, _ in pairs]
    judgments = [judge(unit, reasons) for unit, reasons in pairs]
    if len({unit["unit_id"] for unit in units}) != len(units):
        raise PackageMismatch("근거 단위 id 가 겹칩니다")
    raw_links = link_raw(raw, pkg["records"])

    out.mkdir(parents=True, exist_ok=False)
    storage._write_jsonl(out / "units.jsonl", units)
    storage._write_jsonl(out / "judgments.jsonl", judgments)
    storage._write_jsonl(out / "raw_links.jsonl", raw_links)
    storage._write_json(out / "manifest.json", {
        "run_id": run_id,
        "created_at": storage._now(),
        "code_commit": storage._code_commit(),
        "package": str(Path(package).resolve()),
        "copy": str(Path(copy).resolve()),
        "pinned_sha256": hashes,
        "counts": counts,
        "excluded_chunks": excluded,
        "original_grid_file": grid_file,
        "raw_links": _raw_counts(raw_links),
        "units": _unit_counts(units, judgments),
    })
    return out


def pin(package, copy):
    """두 사본의 고정 파일 SHA-256 이 서로 같고 manifest.json 의 선언과도 같아야 한다. 하나라도 다르면 멈춘다."""
    hashes = {}
    for name in PINNED:
        sha, other = storage._sha256(Path(package) / name), storage._sha256(Path(copy) / name)
        if sha != other:
            raise PackageMismatch(f"두 사본의 {name} SHA-256 이 다릅니다: {sha} != {other}")
        hashes[name] = sha
    declared = json.loads((Path(package) / "manifest.json").read_text(encoding="utf-8"))["files"]
    for name in PINNED[1:]:
        if declared[name]["sha256"] != hashes[name]:
            raise PackageMismatch(f"{name} SHA-256 이 manifest.json 의 선언과 다릅니다")
    return hashes


def load(package):
    package = Path(package)
    pkg = {
        "manifest": json.loads((package / "manifest.json").read_text(encoding="utf-8")),
        "chunks": list(_iter_jsonl(package / CHUNKS)),
        "elements": {e["element_id"]: _element(e) for e in _iter_jsonl(package / ELEMENTS)},
        "records": {r["record_id"]: _record(r) for r in _iter_jsonl(package / RECORDS)},
        "status": _status(package / STATUS),
        "grids": list(_iter_jsonl(package / GRIDS)),
    }
    pkg["docs"] = {record["doc_sha"] for record in pkg["records"].values()}
    # 원본 그리드 표는 요소의 final_verified_native_table 이 가리키는 (문서 SHA, stream, 표 컨트롤) 로 잇는다.
    pkg["by_native"] = {
        (element["doc_sha"], *element["native"]): element_id
        for element_id, element in pkg["elements"].items() if element["native"]
    }
    return pkg


def check_counts(pkg):
    """파일에서 센 수가 manifest.json 과 다르면 멈춘다. 제외한 청크는 id 와 이유로 남긴다."""
    included = [c for c in pkg["chunks"] if not IMAGE_ONLY.fullmatch(c["body"])]
    excluded = [
        {"chunk_id": c["chunk_id"], "reason": "본문이 [IMAGE] 표시뿐입니다"}
        for c in pkg["chunks"] if IMAGE_ONLY.fullmatch(c["body"])
    ]
    counts = {
        "documents": len(pkg["docs"]),
        "records": len(pkg["records"]),
        "elements": len(pkg["elements"]),
        "chunks": len(pkg["chunks"]),
        "filtered_chunk_search_inputs": len(included),
    }
    declared = {name: pkg["manifest"][name] for name in counts}
    if counts != declared:
        raise PackageMismatch(f"파일에서 센 수 {counts} 가 manifest.json {declared} 과 다릅니다")
    return counts, excluded, included


def grid_file_verdict(grids):
    """원본 그리드 참고 파일이 검증된 것인지 확인한다.

    v11 의 그리드 레코드에는 검증 상태 필드가 없고, 패키지 노트북 7절은 이 파일을
    모든 표의 원본 구조를 증명하지 않는 일부 근거라고 적는다. 그래서 검증되지 않은 것으로 기록한다.
    검증 필드가 생긴 파일은 읽는 법을 정하기 전까지 멈춘다 (SHA 를 고정했으므로 v11 에서는 일어나지 않는다).
    """
    fields = sorted({name for grid in grids for name in grid if "verif" in name or "status" in name})
    if fields:
        raise PackageMismatch(f"원본 그리드 파일에 검증 필드가 있습니다. 읽는 법을 먼저 정하세요: {fields}")
    return {
        "verified": False,
        "tables": len(grids),
        "reason": "그리드 레코드에 검증 상태 필드가 없고, 패키지 노트북 7절이 원본 구조를 증명하지 않는 참고 근거라고 적음",
    }


def chunk_units(chunk, pkg):
    """청크의 span 마다 근거 단위를 만든다. 글자 span 은 한 단위, 표 행 span 은 행마다 한 단위 (논리 행)."""
    pairs = []
    for span in chunk["spans"]:
        element = pkg["elements"].get(span["element_id"])
        record = pkg["records"].get(element["record_id"]) if element else None
        base = _chunk_base(chunk, span["element_id"], element, record)
        if "rows" in span:
            # 행만의 텍스트는 따로 없으므로 OCR 범위는 요소 본문 전체로 확인한다 (행보다 넓어 보수적이다).
            text = element["text"] if element else ""
            for row in span["rows"]:
                location = {"kind": "table", "grid": "logical_restored", "row": row, "cell": None}
                pairs.append(_chunk_unit(base, location, _row_error(row, element), text, pkg))
        else:
            location = {"kind": "char", "start": span["start"], "end": span["end"]}
            text = element["text"][span["start"]:span["end"]] if element else ""
            pairs.append(_chunk_unit(base, location, _char_error(span, element), text, pkg))
    return pairs


def grid_units(grid, pkg):
    """원본 그리드 참고 파일의 셀마다 근거 단위를 만든다. 논리 행 단위와 다른 격자 종류로 두고 섞지 않는다."""
    sha, stream, control = grid["source_document_sha256"], grid["stream"], grid["control"]
    element_id = pkg["by_native"].get((sha, stream, control))
    element = pkg["elements"].get(element_id)
    record = pkg["records"].get(element["record_id"]) if element else None
    errors = [] if sha in pkg["docs"] else [f"문서 SHA {sha} 가 v11 레코드에 없습니다"]
    if element is None:
        errors.append("이 표를 가리키는 요소가 없습니다 (final_verified_native_table)")
    else:
        errors += _link_errors(element_id, element, record)
    base = {
        "doc_sha": sha,
        "chunk_id": None,
        "element_id": element_id,
        "record_id": element["record_id"] if element else None,
        **_record_fields(record),
        "requirement_ids": record["requirement_ids"] if record else [],
        "image_sha": None,
        "ocr_scope": None,
    }
    return [_cell_unit(base, stream, control, cell, errors, pkg) for cell in grid["cells"]]


def judge(unit, reasons):
    """별도 판정 기록. ID 연결과 원문 의미 검증이 둘 다 참이고 보류 이유가 없을 때만 eligible 이다."""
    eligible = unit["ids_linked"] and unit["meaning_verified"] and not reasons
    return {"unit_id": unit["unit_id"], "judgment": "eligible" if eligible else "held", "reasons": reasons}


def link_raw(raw_dir, records):
    """artifacts/raw 파일은 SHA-256 이 v11 문서 SHA 와 같을 때만 잇는다. 이름만 같은 파일은 연결하지 않고 따로 표시한다.

    artifacts/raw 와 v11 source_paths 의 파일명은 둘 다 잘려 있어 이름으로는 문서를 가릴 수 없다.
    """
    docs = {record["doc_sha"] for record in records.values()}
    names = {_nfc(name) for record in records.values() for name in record["source_names"]}
    rows = []
    for path in sorted(Path(raw_dir).iterdir()):
        if not path.is_file():
            continue
        sha = storage._sha256(path)
        if sha in docs:
            status = "linked"
        elif _nfc(path.name) in names:
            status = "unlinked_filename_only"
        else:
            status = "unlinked"
        rows.append({"file": path.name, "sha256": sha, "doc_sha": sha if sha in docs else None, "status": status})
    return rows


def _chunk_base(chunk, element_id, element, record):
    """청크 span 이 가리키는 요소·레코드에서 근거 단위의 공통 필드, 연결 오류, 값 충돌을 모은다."""
    errors = _link_errors(element_id, element, record)
    requirement_ids = sorted(set(record["requirement_ids"]) | set(element["requirement_ids"])) if record else []
    key = chunk["requirement_key"]
    conflicts = []
    if key and requirement_ids and key not in requirement_ids:
        conflicts.append(f"같은 사실의 값이 다릅니다: 청크 requirement_key {key}, 레코드·요소 requirement_ids {requirement_ids}")
    image = record["image"] if record else None
    fields = {
        "doc_sha": record["doc_sha"] if record else None,
        "chunk_id": chunk["chunk_id"],
        "element_id": element_id,
        "record_id": element["record_id"] if element else None,
        **_record_fields(record),
        "requirement_ids": requirement_ids,
        "image_sha": image["sha"] if image else None,
        "ocr_scope": image["scope"] if image else None,
    }
    return {"fields": fields, "errors": errors, "conflicts": conflicts, "image": image}


def _chunk_unit(base, location, location_error, text, pkg):
    fields = base["fields"]
    kind = "char:{start}-{end}" if location["kind"] == "char" else "row:{row}"
    errors = [*base["errors"], location_error] if location_error else base["errors"]
    if base["image"]:
        # OCR 단위는 source_status_merged.csv 에 없으므로 (분모 제외) 이미지의 검증 범위로만 판단한다.
        units, gaps = [], _image_gaps(base["image"], text)
    else:
        units = _chunk_source_units(pkg, fields["element_id"], fields["chunk_id"])
        gaps = _text_gaps(units)
    unit = {
        "unit_id": f"chunk:{fields['chunk_id']}:{fields['element_id']}:{kind.format(**location)}",
        **fields,
        "location": location,
        "source_units": [u["id"] for u in units],
        "ids_linked": not errors,
        "meaning_verified": not gaps,
    }
    return unit, [*errors, *base["conflicts"], *gaps]


def _cell_unit(base, stream, control, cell, errors, pkg):
    """셀의 원문 단위는 셀 텍스트 레코드의 source_unit_id 로 바로 찾는다."""
    ids = [f"{base['doc_sha']}:{stream}:ParaText:{text_record}" for text_record in cell["text_records"]]
    known = pkg["status"]["units"]
    errors = errors + [f"원문 단위 {i} 가 source_status_merged.csv 에 없습니다" for i in ids if i not in known]
    gaps = _text_gaps([known[i] for i in ids if i in known])
    unit = {
        "unit_id": f"grid:{base['doc_sha']}:{stream}:{control}:{cell['row']}:{cell['col']}",
        **base,
        "location": {"kind": "table", "grid": "original_reference", "row": cell["row"], "cell": cell["col"]},
        "source_units": ids,
        "ids_linked": not errors,
        "meaning_verified": not gaps,
    }
    return unit, [*errors, *gaps, GRID_UNVERIFIED]


def _link_errors(element_id, element, record):
    if element is None:
        return [f"요소 {element_id} 가 final_elements.jsonl 에 없습니다"]
    if record is None:
        return [f"레코드 {element['record_id']} 가 final_records.jsonl 에 없습니다"]
    errors = []
    if not SHA256.fullmatch(record["doc_sha"]) or record["doc_sha"] != record["doc_id"]:
        errors.append(f"레코드 {element['record_id']} 의 문서 SHA 가 SHA-256 형식이 아니거나 doc_id 와 다릅니다")
    if element["doc_sha"] != record["doc_sha"]:
        errors.append(f"요소 {element_id} 와 레코드 {element['record_id']} 의 문서 SHA 가 다릅니다")
    return errors


def _char_error(span, element):
    if element and not 0 <= span["start"] < span["end"] <= len(element["text"]):
        return f"글자 span {span['start']}-{span['end']} 이 요소 {span['element_id']} 의 본문 밖입니다"
    return None


def _row_error(row, element):
    if element and (element["table_rows"] is None or not 0 <= row < element["table_rows"]):
        return f"표 행 {row} 이 요소의 표 밖입니다"
    return None


def _chunk_source_units(pkg, element_id, chunk_id):
    """요소에 걸린 원문 단위 중 이 청크의 것. 청크 id 가 빈 단위는 어느 청크인지 모르므로 보수적으로 포함한다."""
    return [u for u in pkg["status"]["by_element"].get(element_id, []) if not u["chunks"] or chunk_id in u["chunks"]]


def _text_gaps(units):
    """원문 의미가 검증되지 않은 이유. 원문 단위가 있고 모두 PASS 일 때만 빈 리스트다."""
    if not units:
        return ["근거 없음: source_status_merged.csv 에 이 근거를 덮는 원문 단위가 없습니다"]
    unverified = [u for u in units if u["status"] != "PASS"]
    if not unverified:
        return []
    causes = "; ".join(sorted({u["reason"] for u in unverified}))
    return [f"UNVERIFIED 원문 단위 {len(unverified)}/{len(units)}개: {causes}"]


def _image_gaps(image, text):
    """이미지 근거는 SHA 와 선언된 OCR 범위가 있고, 본문 줄이 모두 검증 전사 안에 있을 때만 검증된 것이다."""
    gaps = [] if image["sha"] else ["이미지 SHA 가 없습니다"]
    if image["scope"] == "hold":
        return [*gaps, "OCR 범위 hold: 선언된 검증 범위가 없습니다"]
    verified = {line.strip() for line in (image["verified_text"] or "").splitlines()}
    outside = [line for line in text.splitlines() if line.strip() and line.strip() not in verified]
    if outside:
        gaps.append(f"검증된 OCR 범위 밖의 내용 {len(outside)}줄")
    return gaps


def _record_fields(record):
    if record is None:
        return {"page": None, "raw_start": None, "raw_end": None}
    return {"page": record["page"], "raw_start": record["raw_start"], "raw_end": record["raw_end"]}


def _element(element):
    location = element["location"]
    native = location.get("final_verified_native_table")
    address = native["original_address"] if native else None
    return {
        "record_id": location["record_id"],
        "doc_sha": location["supplier_metadata"]["sha256"],
        "text": element[location["span_text_field"]],
        "table_rows": element["table"]["rows"] if element["table"] else None,
        "requirement_ids": location["supplier_metadata"]["requirement_ids"],
        "native": (address["stream"], address["table_control_record"]) if address else None,
    }


def _record(record):
    return {
        "doc_sha": record["sha256"],
        "doc_id": record["doc_id"],
        "source_names": [Path(path).name for path in record["source_paths"]],
        "raw_start": record["raw_start"],
        "raw_end": record["raw_end"],
        "page": record["pdf_page_number"],
        "requirement_ids": record["requirement_ids"],
        "image": _image(record),
    }


def _image(record):
    """이미지 레코드의 SHA 와 OCR 범위. 범위를 선언하지 않은 이미지는 hold 다."""
    if record["element_type"] not in IMAGE_RECORDS:
        return None
    source = record.get("image_source") or {}
    links = record.get("image_source_links") or []
    sha = source.get("asset_sha256") or (links[0]["image_sha256"] if len(links) == 1 else None)
    return {
        "sha": sha,
        "scope": OCR_SCOPES.get(source.get("scope"), "hold"),
        "verified_text": record.get("verified_region_text"),
    }


def _status(path):
    """원문 단위를 id 와 요소 id 로 찾게 한다."""
    by_unit, by_element = {}, defaultdict(list)
    with path.open(encoding="utf-8", newline="") as f:
        for row in csv.DictReader(f):
            unit = {
                "id": row["source_unit_id"],
                "status": row["status"],
                "reason": row["reason"],
                "chunks": frozenset(json.loads(row["chunk_ids"])),
            }
            by_unit[unit["id"]] = unit
            for element_id in json.loads(row["element_ids"]):
                by_element[element_id].append(unit)
    return {"units": by_unit, "by_element": by_element}


def _raw_counts(rows):
    counts = Counter(row["status"] for row in rows)
    return {
        "linked": counts["linked"],
        "unlinked": counts["unlinked"] + counts["unlinked_filename_only"],
        "unlinked_filename_only": counts["unlinked_filename_only"],
    }


def _unit_counts(units, judgments):
    counts = Counter(judgment["judgment"] for judgment in judgments)
    return {
        "total": len(units),
        "eligible": counts["eligible"],
        "held": counts["held"],
        "ids_linked": sum(unit["ids_linked"] for unit in units),
        "meaning_verified": sum(unit["meaning_verified"] for unit in units),
        "by_source": dict(Counter(unit["unit_id"].split(":", 1)[0] for unit in units)),
    }


def _nfc(name):
    return unicodedata.normalize("NFC", name)


def _iter_jsonl(path):
    with path.open(encoding="utf-8") as f:
        for line in f:
            if line.strip():
                yield json.loads(line)


def main():
    parser = argparse.ArgumentParser(description="v11 패키지 근거 어댑터 (읽기 전용)")
    parser.add_argument("run_id")
    parser.add_argument("copy", help="내려받은 압축의 안쪽 RFP_Preprocessing_Final_v11_Team 폴더")
    args = parser.parse_args()
    print(run(args.run_id, args.copy))


if __name__ == "__main__":
    main()
