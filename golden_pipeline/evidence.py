"""v12 팀 패키지(Golden_Dev396_v12_Team_Package)를 읽기만 하는 근거 어댑터.

검색 입력 청크 하나가 근거 단위 하나다. v12 는 요소 · 레코드 · 원문 단위 파일을 주지 않고,
표 청크의 칸 안 줄바꿈 때문에 줄을 표 행으로 되돌릴 수도 없어 청크보다 잘게 나눌 근거가 없다.
청크마다 자동 승인 가능(eligible) 또는 보류(held)를 이유와 함께 별도 판정 기록으로 남긴다. 패키지는 고치지 않는다.
"""
import json
from collections import Counter
from pathlib import Path

from golden_pipeline import storage

REPO = storage.PACKAGE.parent
PACKAGE = REPO / "data" / "Golden_Dev396_v12_Team_Package"
CHUNKS = "corpus/chunks.jsonl"
DOCS = "corpus/docs.jsonl"
AGENCIES = "data/data_list.csv"
PINNED = ("manifest.json", CHUNKS, DOCS, AGENCIES)
# 패키지가 원본 대조에서 예외(띄어 쓴 단어 · 빈 작성 칸 · 독음 미확정 한자 등)를 남긴 위치. 원문 의미를 확인하지 않았다.
EXCEPTION = "예외 검토 필요"
OCR_SCOPES = {
    "FULL_VISIBLE_TEXT": "full_visible_text",
    "PARTIAL_REGION": "partial_region",
    "PARTIAL_REGIONS": "partial_region",
}


class PackageMismatch(ValueError):
    pass


def run(run_id, package=PACKAGE):
    """패키지를 고정·확인하고 근거 단위, 판정, 매니페스트를 outputs/evidence/{run_id}/ 에 쓴다."""
    out = storage._child(storage.OUTPUTS / "evidence", run_id)
    package = Path(package)
    hashes = pin(package)
    chunks = list(_iter_jsonl(package / CHUNKS))
    docs = {doc["doc_id"] for doc in _iter_jsonl(package / DOCS)}
    counts = {"v12_search_chunks": len(chunks), "v12_documents": len(docs)}
    declared = {name: storage._read_json(package / "manifest.json")["counts"][name] for name in counts}
    if counts != declared:
        raise PackageMismatch(f"파일에서 센 수 {counts} 가 manifest.json {declared} 과 다릅니다")
    pairs = [chunk_unit(chunk, docs) for chunk in chunks]
    units = [unit for unit, _ in pairs]
    judgments = [judge(unit, reasons) for unit, reasons in pairs]

    out.mkdir(parents=True, exist_ok=False)
    storage._write_jsonl(out / "units.jsonl", units)
    storage._write_jsonl(out / "judgments.jsonl", judgments)
    storage._write_json(out / "manifest.json", {
        "run_id": run_id,
        "created_at": storage._now(),
        "code_commit": storage._code_commit(),
        "package": str(package.resolve()),
        "pinned_sha256": hashes,
        "counts": counts,
        "units": _unit_counts(units, judgments),
    })
    return out


def pin(package):
    """고정 파일의 SHA-256 이 manifest.json 의 선언과 같아야 한다. 하나라도 다르면 멈춘다."""
    hashes = {name: storage._sha256(package / name) for name in PINNED}
    declared = storage._read_json(package / "manifest.json")["files"]
    for name in PINNED[1:]:
        if declared[name]["sha256"] != hashes[name]:
            raise PackageMismatch(f"{name} SHA-256 이 manifest.json 의 선언과 다릅니다")
    return hashes


def chunk_unit(chunk, docs):
    """청크 하나의 근거 단위와 보류 이유. 위치는 청크의 첫 표 span(없으면 첫 span)이고, 본문은 청크 body 전체다."""
    tables = [span for span in chunk["spans"] if "rows" in span]
    first = tables[0] if tables else chunk["spans"][0]
    if tables:
        location = {"kind": "table", "grid": "logical_restored", "row": first["rows"][0], "cell": None}
    else:
        location = {"kind": "char", "start": first["start"], "end": first["end"]}
    sources = {source["element_id"]: source["location"] for source in chunk["source_locations"]}
    image = chunk["image_source"]
    unit = {
        "unit_id": f"chunk:{chunk['chunk_id']}",
        "doc_sha": chunk["doc_id"],
        "chunk_id": chunk["chunk_id"],
        "element_id": first["element_id"],
        "record_id": sources[first["element_id"]]["record_id"],
        "location": location,
        "page": chunk["page"],
        "requirement_ids": chunk["requirement_ids"],
        "image_sha": image["asset_sha256"] if image else None,
        "ocr_scope": OCR_SCOPES.get(image.get("scope"), "hold") if image else None,
        "text": chunk["body"],
    }
    errors = _link_errors(chunk, sources, docs)
    gaps = _meaning_gaps(unit, [location["supplier_metadata"] for location in sources.values()])
    unit.update(ids_linked=not errors, meaning_verified=not gaps)
    return unit, [*errors, *gaps]


def judge(unit, reasons):
    """별도 판정 기록. ID 연결과 원문 의미 검증이 둘 다 참이고 보류 이유가 없을 때만 eligible 이다."""
    eligible = unit["ids_linked"] and unit["meaning_verified"] and not reasons
    return {"unit_id": unit["unit_id"], "judgment": "eligible" if eligible else "held", "reasons": reasons}


def _link_errors(chunk, sources, docs):
    errors = [] if chunk["doc_id"] in docs else [f"문서 {chunk['doc_id']} 가 {DOCS} 에 없습니다"]
    if chunk["source_sha256"] != chunk["doc_id"]:
        errors.append("청크의 source_sha256 이 doc_id 와 다릅니다")
    if any(location["supplier_metadata"]["sha256"] != chunk["doc_id"] for location in sources.values()):
        errors.append("청크 원본 위치의 문서 SHA 가 doc_id 와 다릅니다")
    return errors


def _meaning_gaps(unit, metadata):
    """원문 의미가 검증되지 않은 이유. 패키지가 예외를 남긴 위치가 하나라도 있으면 그 예외 종류를 적는다."""
    excepted = [meta for meta in metadata if meta["review_status"] == EXCEPTION]
    gaps = []
    if excepted:
        kinds = sorted({kind for meta in excepted for kind in meta["exception_kinds"]})
        gaps.append(f"원본 대조 예외: {', '.join(kinds)}")
    if unit["ocr_scope"] == "hold":
        gaps.append("OCR 범위 hold: 선언된 검증 범위가 없습니다")
    return gaps


def _unit_counts(units, judgments):
    counts = Counter(judgment["judgment"] for judgment in judgments)
    return {
        "total": len(units),
        "eligible": counts["eligible"],
        "held": counts["held"],
        "ids_linked": sum(unit["ids_linked"] for unit in units),
        "meaning_verified": sum(unit["meaning_verified"] for unit in units),
    }


def _iter_jsonl(path):
    with path.open(encoding="utf-8") as f:
        for line in f:
            if line.strip():
                yield json.loads(line)
