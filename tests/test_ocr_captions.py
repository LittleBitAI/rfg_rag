import hashlib

import pytest

from rag.config import write_jsonl
from rag.preprocessing import parsing
from rag.preprocessing.ocr_captions import add_pdf_captions


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


def test_pdf_captions_split_body_at_image_positions_and_keep_cover(tmp_path):
    import io
    import pymupdf
    from PIL import Image

    def png(color):
        buffer = io.BytesIO()
        Image.new("RGB", (2, 2), color).save(buffer, format="PNG")
        return buffer.getvalue()

    path = tmp_path / "source.pdf"
    with pymupdf.open() as pdf:
        pdf.new_page().insert_image((72, 100, 100, 150), stream=png("red"))
        pdf.new_page()
        page = pdf.new_page()
        for y, text in [(72, "Before"), (200, "Middle"), (350, "After")]:
            page.insert_text((72, y), text)
        page.insert_image((72, 100, 100, 150), stream=png("red"))
        page.insert_image((72, 250, 100, 300), stream=png("blue"))
        pdf.save(path)
    records = [{"page": 3, "kind": "text", "text": "Before\nMiddle\nAfter"}]
    rows = [{"page": 3, "image_index": 1, "text": "두 번째"},
            {"page": 1, "image_index": 0, "text": "표지 그림"},
            {"page": 3, "image_index": 0, "text": "첫 번째"},
            {"page": 3, "image_index": 0, "text": ""}]
    assert [(r["page"], r["text"].strip()) for r in add_pdf_captions(records, rows, str(path))] == [
        (1, "[그림/도표 설명] 표지 그림"), (3, "Before"), (3, "[그림/도표 설명] 첫 번째"),
        (3, "Middle"), (3, "[그림/도표 설명] 두 번째"), (3, "After")]


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
