"""벤치마크에서 만든 OCR 결과를 위치별로 읽는다. API는 호출하지 않는다."""
from __future__ import annotations

import hashlib
import re
import tempfile
from collections import defaultdict
from pathlib import Path

from rag.config import read_jsonl


def load_captions(path: Path | None) -> dict[str, list[dict]]:
    by_document = defaultdict(list)
    if path is not None and path.exists():
        seen = set()
        for row in read_jsonl(path):
            fields = ("image_name", "marker_start") if row["format"] == "hwp" else ("page", "image_index")
            key = (row["image_sha256"], row["doc_id"], *(row[name] for name in fields))
            if key in seen:
                raise ValueError(f"Duplicate OCR caption place: {key}")
            seen.add(key)
            by_document[row["doc_id"]].append(row)
    return dict(by_document)


def caption_record(text: str, page=None) -> dict:
    return {"page": page, "kind": "image_caption", "text": f"[그림/도표 설명] {text}"}


def check_document(path: str, rows: list[dict]):
    sha = hashlib.sha256(Path(path).read_bytes()).hexdigest()
    if any(row["document_sha256"] != sha for row in rows):
        raise ValueError(f"OCR document changed: {path}")


def hwp_caption_text(path: str, rows: list[dict]) -> tuple[str, list[str]]:
    from .parsing import _IMG_MARK, _hwp_raw_text, clean_tab_garbage, repair_md_tables

    with tempfile.TemporaryDirectory(prefix="saved_ocr_") as image_dir:
        text = repair_md_tables(clean_tab_garbage(_hwp_raw_text(path, image_dir)))
        by_marker = {r["marker_start"]: r for r in rows if r["marker_start"] is not None}
        captions = []
        matched = set()

        def replace(match):
            row = by_marker.get(match.start())
            if row is None:
                return ""
            name = (match.group(1) or "").strip()
            if name != row["image_name"]:
                raise ValueError(f"OCR marker changed: {path}: {match.start()}")
            _check_image(Path(image_dir) / name, row)
            matched.add(match.start())
            return _placeholder(row["text"], captions)

        body = _IMG_MARK.sub(replace, text)
        if matched != set(by_marker):
            raise ValueError(f"OCR markers missing: {path}: {set(by_marker) - matched}")
        for row in rows:
            if row["marker_start"] is None:
                _check_image(Path(image_dir) / row["image_name"], row)
                body += _placeholder(row["text"], captions)
        return body, captions


def _check_image(path: Path, row: dict):
    if hashlib.sha256(path.read_bytes()).hexdigest() != row["image_sha256"]:
        raise ValueError(f"OCR image changed: {path.name}")


def _placeholder(text: str, captions: list[str]) -> str:
    if not text.strip():
        return ""
    captions.append(text)
    return f"\n[[IMG:{len(captions) - 1}]]\n"


def front_captions(front: str, captions: list[str]) -> list[dict]:
    return [caption_record(captions[int(i)]) for i in re.findall(r"\[\[IMG:(\d+)\]\]", front)]


def add_pdf_captions(records: list[dict], rows: list[dict], path: str) -> list[dict]:
    import pymupdf

    by_page = defaultdict(list)
    for row in sorted(rows, key=lambda r: (r["page"], r["image_index"])):
        if row["text"].strip():
            by_page[row["page"]].append(row)
    output = []
    with pymupdf.open(path) as document:
        for page in sorted({r["page"] for r in records} | set(by_page)):
            original = [r for r in records if r["page"] == page]
            if page not in by_page:
                output.extend(original)
                continue
            text = next((r["text"] for r in original if r["kind"] == "text"), "")
            tables = [r for r in original if r["kind"] == "table"]
            output.extend(_pdf_page_captions(text, document[page - 1], by_page[page], tables))
    return output


def _pdf_page_captions(text: str, page, rows: list[dict], tables: list[dict]) -> list[dict]:
    anchors = _pdf_table_anchors(page, tables)
    anchors += [(_pdf_image_top(page, row), caption_record(row["text"], page.number + 1)) for row in rows]
    lines = _pdf_line_offsets(text, page)
    positioned = [(_pdf_offset(lines, top), top, record) for top, record in anchors]
    records = []
    previous = 0
    for offset, _, record in sorted(positioned, key=lambda entry: entry[:2]):
        if text[previous:offset].strip():
            records.append({"page": page.number + 1, "kind": "text", "text": text[previous:offset]})
        records.append(record)
        previous = offset
    if text[previous:].strip():
        records.append({"page": page.number + 1, "kind": "text", "text": text[previous:]})
    return records


def _pdf_table_anchors(page, records: list[dict]) -> list[tuple[float, dict]]:
    from .parsing import _md_table_blocks

    if not records:
        return []
    tops = [table.bbox[1] for table in page.find_tables().tables
            for block in _md_table_blocks(table.to_markdown()) if block.count("|") >= 4]
    return list(zip(tops, records, strict=True))


def _pdf_image_top(page, row: dict) -> float:
    xref = page.get_images()[row["image_index"]][0]
    if "xref" in row and xref != row["xref"]:
        raise ValueError(f"OCR PDF image changed: page {page.number + 1}")
    return min(rect.y0 for rect in page.get_image_rects(xref))


def _pdf_line_offsets(text: str, page) -> list[tuple[float, int]]:
    offsets = []
    cursor = 0
    for block in page.get_text("dict")["blocks"]:
        for line in block.get("lines", []):
            value = "".join(span["text"] for span in line["spans"]).strip()
            pattern = r"\s*".join(re.escape(c) for c in value if not c.isspace())
            match = re.compile(pattern).search(text, cursor) if pattern else None
            if match is not None:
                cursor = match.end()
                offsets.append((line["bbox"][3], cursor))
    return offsets


def _pdf_offset(lines: list[tuple[float, int]], top: float) -> int:
    return max((offset for bottom, offset in lines if bottom <= top), default=0)
