"""v11 근거 어댑터: 작은 가짜 패키지 두 사본으로 고정·개수·연결·판정을 확인한다."""
import copy
import csv
import hashlib
import json

import pytest

from golden_pipeline import evidence

RAW_BYTES = b"original hwp bytes"
DOC = hashlib.sha256(RAW_BYTES).hexdigest()
IMAGE = "c" * 64
STREAM = "BodyText/Section0"
RECORD = f"{DOC}:body:0:0-40"
IMAGE_RECORD = f"{DOC}:verified_ocr_v11:1"
TEXT = "사업 예산은 1억원이다"


def _record(record_id, **fields):
    return {
        "record_id": record_id, "doc_id": DOC, "sha256": DOC, "source_paths": ["기관_사업.hwp"],
        "element_type": "body", "raw_start": 0, "raw_end": 40, "pdf_page_number": 3,
        "requirement_ids": ["SFR-001"], **fields,
    }


def _element(element_id, record_id, text, table=None, native=None):
    location = {
        "record_id": record_id,
        "span_text_field": "search_text",
        "supplier_metadata": {"sha256": DOC, "requirement_ids": []},
    }
    if native is not None:
        location["final_verified_native_table"] = {"original_address": {"stream": STREAM, "table_control_record": native}}
    return {"element_id": element_id, "kind": "table" if table else "paragraph", "search_text": text,
            "table": table, "location": location}


def _chunk(chunk_id, spans, body, requirement_key=None):
    return {"chunk_id": chunk_id, "spans": spans, "body": body, "requirement_key": requirement_key}


def _status(unit_id, elements, chunks, status="PASS", reason=""):
    return {"source_unit_id": unit_id, "status": status, "reason": reason,
            "element_ids": json.dumps(elements), "chunk_ids": json.dumps(chunks)}


BASE = {
    "records": [
        _record(RECORD),
        _record(IMAGE_RECORD, element_type="image_ocr", requirement_ids=[],
                image_source={"asset_sha256": IMAGE, "scope": "FULL_VISIBLE_TEXT"},
                verified_region_text="접수\n심사\n지급"),
    ],
    "elements": [
        _element("e-text", RECORD, TEXT),
        _element("e-table", RECORD, "| 구분 | 금액 |\n| 예산 | 1억 |", table={"rows": 2, "cols": 2, "cells": []}, native=7),
        _element("e-image", IMAGE_RECORD, "접수\n심사"),
    ],
    "chunks": [
        _chunk("c-text", [{"element_id": "e-text", "start": 0, "end": 5}], "사업 예산"),
        _chunk("c-table", [{"element_id": "e-table", "rows": [0, 1]}], "| 구분 | 금액 |", requirement_key="SFR-001"),
        _chunk("c-image", [{"element_id": "e-image", "start": 0, "end": 5}], "접수\n심사"),
        _chunk("c-marker", [{"element_id": "e-text", "start": 0, "end": 2}], "[IMAGE]\n[IMAGE]"),
    ],
    "status": [
        _status(f"{DOC}:{STREAM}:ParaText:10", ["e-text"], ["c-text"]),
        _status(f"{DOC}:{STREAM}:ParaText:11", ["e-table"], ["c-table"]),
    ],
    "grids": [
        {"source_document_sha256": DOC, "stream": STREAM, "control": 7, "rows": 1, "cols": 1,
         "cells": [{"row": 0, "col": 0, "text_records": [11]}]},
    ],
}


def write_package(root, pkg, counts=None):
    """패키지 파일을 쓰고, 실제 개수와 파일 SHA 로 manifest.json 을 만든다."""
    (root / "validation").mkdir(parents=True)
    for name, key in ((evidence.CHUNKS, "chunks"), (evidence.ELEMENTS, "elements"),
                      (evidence.RECORDS, "records"), (evidence.GRIDS, "grids")):
        (root / name).write_text("".join(json.dumps(row, ensure_ascii=False) + "\n" for row in pkg[key]),
                                 encoding="utf-8")
    with (root / evidence.STATUS).open("w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=list(BASE["status"][0]))
        writer.writeheader()
        writer.writerows(pkg["status"])
    manifest = {
        "documents": len({r["sha256"] for r in pkg["records"]}),
        "records": len(pkg["records"]),
        "elements": len(pkg["elements"]),
        "chunks": len(pkg["chunks"]),
        "filtered_chunk_search_inputs": sum(1 for c in pkg["chunks"] if not c["body"].startswith("[IMAGE]")),
        **(counts or {}),
        "files": {name: {"sha256": hashlib.sha256((root / name).read_bytes()).hexdigest()}
                  for name in evidence.PINNED[1:]},
    }
    (root / "manifest.json").write_text(json.dumps(manifest, ensure_ascii=False), encoding="utf-8")
    return root


@pytest.fixture
def package(tmp_path):
    """data/ 사본, 내려받은 사본, artifacts/raw 를 같은 내용으로 만든다. 고쳐 쓸 패키지 dict 를 받는다."""
    def make(pkg=None, counts=None):
        pkg = pkg or copy.deepcopy(BASE)
        main = write_package(tmp_path / "data" / "v11", pkg, counts)
        other = write_package(tmp_path / "download" / "v11", pkg, counts)
        raw = tmp_path / "raw"
        raw.mkdir(exist_ok=True)
        (raw / "잘린 이름.hwp").write_bytes(RAW_BYTES)
        (raw / "기관_사업.hwp").write_bytes(b"same name, other bytes")
        return main, other, raw
    return make


def units_of(main):
    pkg = evidence.load(main)
    _, _, included = evidence.check_counts(pkg)
    pairs = [pair for chunk in included for pair in evidence.chunk_units(chunk, pkg)]
    pairs += [pair for grid in pkg["grids"] for pair in evidence.grid_units(grid, pkg)]
    return {unit["unit_id"]: (unit, evidence.judge(unit, reasons)) for unit, reasons in pairs}


def test_run_pins_counts_links_and_writes_separate_judgments(outputs, package):
    main, other, raw = package()
    out = evidence.run("r1", other, package=main, raw=raw)

    manifest = json.loads((out / "manifest.json").read_text(encoding="utf-8"))
    assert set(manifest["pinned_sha256"]) == set(evidence.PINNED)
    assert manifest["counts"] == {"documents": 1, "records": 2, "elements": 3, "chunks": 4,
                                  "filtered_chunk_search_inputs": 3}
    assert manifest["excluded_chunks"] == [{"chunk_id": "c-marker", "reason": "본문이 [IMAGE] 표시뿐입니다"}]
    assert manifest["original_grid_file"]["verified"] is False
    units = [json.loads(line) for line in (out / "units.jsonl").read_text(encoding="utf-8").splitlines()]
    judgments = [json.loads(line) for line in (out / "judgments.jsonl").read_text(encoding="utf-8").splitlines()]
    assert [j["unit_id"] for j in judgments] == [u["unit_id"] for u in units]
    text = next(u for u in units if u["chunk_id"] == "c-text")
    assert text["doc_sha"] == DOC and text["record_id"] == RECORD
    assert (text["raw_start"], text["raw_end"], text["page"]) == (0, 40, 3)
    assert text["source_units"] == [f"{DOC}:{STREAM}:ParaText:10"]
    assert next(j for j in judgments if j["unit_id"] == text["unit_id"])["judgment"] == "eligible"


def test_run_stops_when_the_two_copies_differ(outputs, package):
    main, other, raw = package()
    with (other / evidence.CHUNKS).open("ab") as f:
        f.write(b"\n")
    with pytest.raises(evidence.PackageMismatch, match="두 사본"):
        evidence.run("r1", other, package=main, raw=raw)
    assert not (outputs / "outputs" / "evidence" / "r1").exists()


def test_run_stops_when_files_differ_from_manifest_declaration(package):
    main, other, _ = package()
    for root in (main, other):
        manifest = json.loads((root / "manifest.json").read_text(encoding="utf-8"))
        manifest["files"][evidence.CHUNKS]["sha256"] = "0" * 64
        (root / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
    with pytest.raises(evidence.PackageMismatch, match="manifest.json"):
        evidence.pin(main, other)


@pytest.mark.parametrize("field", ["documents", "records", "elements", "chunks", "filtered_chunk_search_inputs"])
def test_counts_read_from_files_must_equal_manifest(package, field):
    main, _, _ = package(counts={field: 999})
    with pytest.raises(evidence.PackageMismatch, match=field):
        evidence.check_counts(evidence.load(main))


def _wrong_id(pkg):
    pkg["chunks"][0]["spans"][0]["element_id"] = "e-missing"


def _wrong_hash(pkg):
    pkg["elements"][0]["location"]["supplier_metadata"]["sha256"] = "d" * 64


def _missing_link(pkg):
    pkg["elements"][0]["location"]["record_id"] = f"{DOC}:body:0:99-100"


@pytest.mark.parametrize("break_link, message", [
    (_wrong_id, "요소 e-missing 가 final_elements.jsonl 에 없습니다"),
    (_wrong_hash, "문서 SHA 가 다릅니다"),
    (_missing_link, "final_records.jsonl 에 없습니다"),
])
def test_broken_link_is_detected_and_held(package, break_link, message):
    pkg = copy.deepcopy(BASE)
    break_link(pkg)
    main, _, _ = package(pkg)
    unit, judgment = next(pair for pair in units_of(main).values() if pair[0]["chunk_id"] == "c-text")
    assert unit["ids_linked"] is False
    assert judgment["judgment"] == "held"
    assert any(message in reason for reason in judgment["reasons"])


def test_grid_cell_of_an_element_with_a_missing_record_is_not_linked(package):
    pkg = copy.deepcopy(BASE)
    pkg["elements"][1]["location"]["record_id"] = "missing-record"
    main, _, _ = package(pkg)
    unit, judgment = next(pair for pair in units_of(main).values() if pair[0]["unit_id"].startswith("grid:"))
    assert unit["ids_linked"] is False
    assert any("레코드 missing-record 가 final_records.jsonl 에 없습니다" in r for r in judgment["reasons"])


def test_raw_files_link_only_by_sha(package):
    main, _, raw = package()
    rows = {row["file"]: row for row in evidence.link_raw(raw, evidence.load(main)["records"])}
    assert rows["잘린 이름.hwp"]["status"] == "linked" and rows["잘린 이름.hwp"]["doc_sha"] == DOC
    assert rows["기관_사업.hwp"]["status"] == "unlinked_filename_only" and rows["기관_사업.hwp"]["doc_sha"] is None
    assert evidence._raw_counts(list(rows.values())) == {"linked": 1, "unlinked": 1, "unlinked_filename_only": 1}


def test_logical_rows_and_original_grid_cells_stay_separate(package):
    main, _, _ = package()
    units = units_of(main)
    rows = [unit for unit, _ in units.values() if unit["chunk_id"] == "c-table"]
    cells = [unit for unit, _ in units.values() if unit["unit_id"].startswith("grid:")]
    # 같은 표(e-table ↔ 컨트롤 7)라도 논리 행과 원본 셀은 다른 단위·다른 격자 종류로 남는다.
    assert [unit["location"]["grid"] for unit in rows] == ["logical_restored", "logical_restored"]
    assert [unit["location"]["grid"] for unit in cells] == ["original_reference"]
    assert cells[0]["element_id"] == "e-table" and cells[0]["chunk_id"] is None
    assert {unit["unit_id"] for unit in rows}.isdisjoint(unit["unit_id"] for unit in cells)
    assert evidence.GRID_UNVERIFIED in units[cells[0]["unit_id"]][1]["reasons"]


@pytest.mark.parametrize("source, verified_text, judgment, reason", [
    ({"asset_sha256": IMAGE, "scope": "FULL_VISIBLE_TEXT"}, "접수\n심사\n지급", "eligible", None),
    ({"asset_sha256": IMAGE, "scope": "PARTIAL_REGIONS"}, "접수", "held", "검증된 OCR 범위 밖의 내용 1줄"),
    ({"asset_sha256": IMAGE}, None, "held", "OCR 범위 hold"),
    ({"scope": "FULL_VISIBLE_TEXT"}, "접수\n심사", "held", "이미지 SHA 가 없습니다"),
])
def test_image_evidence_carries_sha_and_scope_and_holds_content_outside_it(
        package, source, verified_text, judgment, reason):
    pkg = copy.deepcopy(BASE)
    pkg["records"][1].update(image_source=source, verified_region_text=verified_text)
    main, _, _ = package(pkg)
    unit, result = next(pair for pair in units_of(main).values() if pair[0]["chunk_id"] == "c-image")
    assert unit["image_sha"] == source.get("asset_sha256")
    assert unit["ocr_scope"] == evidence.OCR_SCOPES.get(source.get("scope"), "hold")
    assert result["judgment"] == judgment
    assert reason is None or any(reason in r for r in result["reasons"])


@pytest.mark.parametrize("row_text, judgment", [("접수\n심사", "eligible"), ("검증 전사에 없는 행", "held")])
def test_ocr_table_row_is_checked_against_the_verified_transcription(package, row_text, judgment):
    pkg = copy.deepcopy(BASE)
    pkg["elements"][2].update(search_text=row_text, table={"rows": 1, "cols": 1, "cells": []})
    pkg["chunks"][2].update(body=row_text, spans=[{"element_id": "e-image", "rows": [0]}])
    main, _, _ = package(pkg)
    unit, result = units_of(main)["chunk:c-image:e-image:row:0"]
    assert unit["meaning_verified"] is (judgment == "eligible")
    assert result["judgment"] == judgment


def _unverified(pkg):
    pkg["status"][0].update(status="UNVERIFIED", reason="GLYPH_MEANING_OR_CHECK_STATE_UNCONFIRMED")


def _no_source_unit(pkg):
    del pkg["status"][0]


def _conflict(pkg):
    pkg["chunks"][0]["requirement_key"] = "SFR-002"


@pytest.mark.parametrize("make_case, meaning_verified, reason", [
    (_unverified, False, "GLYPH_MEANING_OR_CHECK_STATE_UNCONFIRMED"),
    (_no_source_unit, False, "근거 없음"),
    (_conflict, True, "같은 사실의 값이 다릅니다: 청크 requirement_key SFR-002"),
])
def test_unverified_missing_and_conflicting_evidence_is_held_although_ids_link(
        package, make_case, meaning_verified, reason):
    pkg = copy.deepcopy(BASE)
    make_case(pkg)
    main, _, _ = package(pkg)
    unit, judgment = next(pair for pair in units_of(main).values() if pair[0]["chunk_id"] == "c-text")
    # ID 연결만으로는 원문 의미 검증도 승인도 되지 않는다.
    assert unit["ids_linked"] is True
    assert unit["meaning_verified"] is meaning_verified
    assert judgment["judgment"] == "held"
    assert any(reason in r for r in judgment["reasons"])


def test_linked_unit_without_verified_meaning_is_never_eligible():
    unit = {"unit_id": "u", "ids_linked": True, "meaning_verified": False}
    assert evidence.judge(unit, [])["judgment"] == "held"


def test_package_files_are_identical_before_and_after_run(outputs, package):
    main, other, raw = package()

    def hashes():
        return {path: hashlib.sha256(path.read_bytes()).hexdigest()
                for root in (main, other, raw) for path in sorted(root.rglob("*")) if path.is_file()}

    before = hashes()
    evidence.run("r1", other, package=main, raw=raw)
    assert hashes() == before
