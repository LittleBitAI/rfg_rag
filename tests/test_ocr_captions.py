import hashlib
import io

import pymupdf
import pytest
from PIL import Image

from rag.config import write_jsonl
from rag.preprocessing import parsing
from rag.preprocessing.chunking import chunk_documents
from rag.preprocessing.ocr_captions import add_pdf_captions


def _png(color):
    buffer = io.BytesIO()
    Image.new("RGB", (2, 2), color).save(buffer, format="PNG")
    return buffer.getvalue()


def test_saved_hwp_caption_at_marker_and_unplaced_at_end(tmp_path, monkeypatch):
    image = b"image bytes"
    sha = hashlib.sha256(image).hexdigest()
    body = "앞 본문\n[IMAGE: BIN001.png]\n뒤 본문"

    def raw_text(path, image_dir):
        from pathlib import Path
        (Path(image_dir) / "BIN001.png").write_bytes(image)
        (Path(image_dir) / "BIN002.png").write_bytes(image)
        return body

    monkeypatch.setattr(parsing, "_hwp_raw_text", raw_text)
    monkeypatch.setattr(parsing, "_ocr_parser", lambda *a: (_ for _ in ()).throw(AssertionError("API")))
    path = tmp_path / "document.hwp"
    path.write_bytes(b"document")
    common = {"image_sha256": sha, "doc_id": parsing.make_doc_id(str(path)), "format": "hwp",
              "document_sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
              "engine": "gpt-6-luna", "image_type": "table"}
    captions = tmp_path / "captions.jsonl"
    write_jsonl([{**common, "image_name": "BIN001.png", "marker_start": body.index("[IMAGE:"),
                  "text": "표: 금액 42원"},
                 {**common, "image_name": "BIN002.png", "marker_start": None, "text": "별도 그림"}], captions)
    cfg = {"skip_first_pages": 0, "hanja_mode": "none"}
    docs = parsing.parse_documents([str(path)], cfg, False, {}, captions)
    assert docs[0]["records"] == [
        {"page": None, "kind": "text", "text": "앞 본문"},
        {"page": None, "kind": "image_caption", "text": "[그림/도표 설명] 표: 금액 42원"},
        {"page": None, "kind": "text", "text": "뒤 본문"},
        {"page": None, "kind": "image_caption", "text": "[그림/도표 설명] 별도 그림"},
    ]
    cfg = {"chunk_size": 200, "overlap_ratio": 0, "table_size_factor": 1, "min_chunk_chars": 5}
    positioned = chunk_documents(docs, cfg, position_captions=True)
    assert [(c["kind"], c["body"]) for c in positioned] == [(r["kind"], r["text"]) for r in docs[0]["records"]]
    assert all(set(c) == {"chunk_id", "doc_id", "source", "title", "doc_type", "page", "kind", "section", "text", "body"}
               for c in positioned)
    assert [(c["kind"], c["body"]) for c in chunk_documents(docs, cfg)] == [
        ("text", "앞 본문\n\n뒤 본문"),
        ("image_caption", "[그림/도표 설명] 표: 금액 42원"),
        ("image_caption", "[그림/도표 설명] 별도 그림"),
    ]


def test_positioned_captions_keep_existing_table_minimum():
    records = [{"page": 1, "kind": "text", "text": "앞의 짧은 본문"},
               {"page": 1, "kind": "table", "text": "| A | B |\n| C | D |"},
               {"page": 1, "kind": "image_caption", "text": "[그림/도표 설명] 42"},
               {"page": 1, "kind": "text", "text": "뒤의 짧은 본문"}]
    doc = {"doc_id": "short", "source": "short.hwp", "title": "Short", "doc_type": "hwp", "records": records}
    cfg = {"chunk_size": 200, "overlap_ratio": 0, "table_size_factor": 1, "min_chunk_chars": 30}
    chunks = chunk_documents([doc], cfg, position_captions=True)
    assert [(c["kind"], c["body"]) for c in chunks] == [(r["kind"], r["text"]) for r in records if r["kind"] != "table"]


def test_pdf_captions_split_body_at_image_positions_and_keep_cover(tmp_path):
    path = tmp_path / "source.pdf"
    with pymupdf.open() as pdf:
        pdf.new_page().insert_image((72, 100, 100, 150), stream=_png("red"))
        page = pdf.new_page()
        page.insert_text((72, 72), "1. Overview")
        page.insert_text((72, 100), "Previous page")
        page = pdf.new_page()
        for y, text in [(72, "Before"), (200, "Middle"), (350, "After")]:
            page.insert_text((72, y), text)
        page.insert_image((72, 100, 100, 150), stream=_png("red"))
        page.insert_image((72, 250, 100, 300), stream=_png("blue"))
        pdf.save(path)
    previous = "1. Overview\nPrevious page"
    records = [{"page": 2, "kind": "text", "text": previous},
               {"page": 3, "kind": "text", "text": "Before\nMiddle\nAfter"}]
    rows = [{"page": 3, "image_index": 1, "text": "두 번째"},
            {"page": 1, "image_index": 0, "text": "표지 그림"},
            {"page": 3, "image_index": 0, "text": "첫 번째"},
            {"page": 3, "image_index": 0, "text": ""}]
    positioned = add_pdf_captions(records, rows, str(path))
    assert [(r["page"], r["text"].strip()) for r in positioned] == [
        (1, "[그림/도표 설명] 표지 그림"), (2, previous), (3, "Before"), (3, "[그림/도표 설명] 첫 번째"),
        (3, "Middle"), (3, "[그림/도표 설명] 두 번째"), (3, "After")]
    doc = {"doc_id": "pdf", "source": str(path), "title": "PDF", "doc_type": "pdf", "records": positioned}
    cfg = {"chunk_size": 25, "overlap_ratio": 0, "table_size_factor": 1, "min_chunk_chars": 5}
    chunks = chunk_documents([doc], cfg, position_captions=True)
    assert [(c["page"], c["body"]) for c in chunks] == [(r["page"], r["text"].strip()) for r in positioned]


@pytest.mark.parametrize("table_tops", [[100], [210], [100, 210, 360]],
                         ids=["table-before-image", "table-between-images", "multiple-tables"])
def test_pdf_tables_and_captions_follow_page_positions(tmp_path, table_tops):
    path = tmp_path / "tables.pdf"
    with pymupdf.open() as pdf:
        page = pdf.new_page()
        for y, text in [(72, "Before"), (280, "Middle"), (450, "After")]:
            page.insert_text((72, y), text)
        page.insert_image((72, 160, 100, 190), stream=_png("red"))
        page.insert_image((72, 310, 100, 340), stream=_png("blue"))
        for index, top in enumerate(table_tops):
            for x in (72, 170, 270):
                page.draw_line((x, top), (x, top + 40))
            for y in (top, top + 20, top + 40):
                page.draw_line((72, y), (270, y))
            for x, y, text in [(80, top + 14, "Budget"), (180, top + 14, "Amount"),
                               (80, top + 34, f"Project{index}"), (180, top + 34, "42")]:
                page.insert_text((x, y), text)
        tables = [table.to_markdown() for table in page.find_tables().tables]
        assert len(tables) == len(table_tops)
        pdf.save(path)
    records = [{"page": 1, "kind": "text", "text": "Before\nMiddle\nAfter"}]
    records += [{"page": 1, "kind": "table", "text": text} for text in tables]
    rows = [{"page": 1, "image_index": index, "text": text}
            for index, text in enumerate(["first", "second"])]
    positioned = add_pdf_captions(records, rows, str(path))
    expected = [(72, "text", "Before"), (280, "text", "Middle"), (450, "text", "After"),
                (160, "image_caption", "[그림/도표 설명] first"),
                (310, "image_caption", "[그림/도표 설명] second")]
    expected += [(top, "table", text) for top, text in zip(table_tops, tables, strict=True)]
    assert [(r["kind"], r["text"].strip()) for r in positioned] == [
        (kind, text.strip()) for _, kind, text in sorted(expected)]
    doc = {"doc_id": "tables", "source": str(path), "title": "Tables", "doc_type": "pdf", "records": positioned}
    cfg = {"chunk_size": 1000, "overlap_ratio": 0, "table_size_factor": 1, "min_chunk_chars": 5}
    chunks = chunk_documents([doc], cfg, position_captions=True)
    assert [(c["kind"], c["body"]) for c in chunks] == [(r["kind"], r["text"].strip()) for r in positioned]


@pytest.mark.parametrize("body", ["Header\nHeader", "Header Header"])
def test_pdf_caption_uses_the_above_image_occurrence_of_repeated_text(tmp_path, body):
    path = tmp_path / "repeated.pdf"
    with pymupdf.open() as pdf:
        page = pdf.new_page()
        page.insert_text((72, 72), "Header")
        page.insert_image((72, 100, 100, 150), stream=_png("red"))
        page.insert_text((72, 200), "Header")
        pdf.save(path)
    records = [{"page": 1, "kind": "text", "text": body}]
    rows = [{"page": 1, "image_index": 0, "text": "between headers"}]
    positioned = add_pdf_captions(records, rows, str(path))
    assert [(r["kind"], r["text"].strip()) for r in positioned] == [
        ("text", "Header"), ("image_caption", "[그림/도표 설명] between headers"), ("text", "Header")]


def test_changed_saved_image_stops_instead_of_dropping_document(tmp_path, monkeypatch):
    from pathlib import Path

    def raw_text(path, image_dir):
        (Path(image_dir) / "image.png").write_bytes(b"changed")
        return "[IMAGE: image.png]"

    monkeypatch.setattr(parsing, "_hwp_raw_text", raw_text)
    path = tmp_path / "source.hwp"
    path.write_bytes(b"document")
    captions = tmp_path / "captions.jsonl"
    write_jsonl([{"image_sha256": hashlib.sha256(b"original").hexdigest(),
                  "document_sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
                  "doc_id": parsing.make_doc_id(str(path)), "format": "hwp",
                  "image_name": "image.png", "marker_start": 0, "text": "저장 전사"}], captions)
    with pytest.raises(ValueError, match="OCR image changed"):
        parsing.parse_documents([str(path)], {}, False, {}, captions)
