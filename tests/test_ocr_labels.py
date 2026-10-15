"""OCR 라벨링 화면: 같은 그림 묶기, 그림 저장 경로 · PDF 자리 실패, 위치마다 카드 하나와 라벨 · CRAFT 기록의 마지막 줄 우선,
문서 순서 다섯 묶음, 묶음 결과 합치기, 1~3 밖 라벨 거부, images/ 밖 파일 차단."""
import io

import pymupdf
import pytest
from fastapi import HTTPException
from PIL import Image
from pydantic import ValidationError

from frontend.ocr_select import extract, server
from frontend.ocr_select.extract import group_images
from frontend.ocr_select.merge import merge

DOC = {"doc_id": "a_1", "source": "a.hwp", "document_sha256": "doc-a"}
LOGO_1 = {**DOC, "format": "hwp", "image_name": "BIN1.png", "marker_start": 10, "repeated_occurrences": 1}
PAGE_IMG = {"doc_id": "b_2", "source": "b.pdf", "document_sha256": "doc-b", "format": "pdf",
            "page": 3, "image_index": 0, "xref": 18, "bbox_points": [[0, 0, 10, 10]]}


def test_group_images_one_row_per_hash_with_every_location():
    found = [
        {"image_sha256": "s1", "file": "s1.png", "reason": None, "occurrence": LOGO_1},
        {"image_sha256": "s2", "file": "s2.wmf", "reason": "Unsupported vector image encoding",
         "occurrence": {**LOGO_1, "image_name": "BIN2.wmf"}},
        {"image_sha256": "s1", "file": "s1.png", "reason": None, "occurrence": PAGE_IMG},
    ]

    rows = group_images(found)

    assert [r["image_sha256"] for r in rows] == ["s1", "s2"]
    assert rows[0]["file"] == "s1.png"
    assert rows[0]["occurrences"] == [LOGO_1, PAGE_IMG]
    assert rows[1]["viewable"] is False and rows[1]["reason"] == "Unsupported vector image encoding"


def _write_pdf(path, colors):
    with pymupdf.open() as document:
        page = document.new_page()
        for i, color in enumerate(colors):
            payload = io.BytesIO()
            Image.new("RGB", (8, 8), color).save(payload, format="PNG")
            page.insert_image(pymupdf.Rect(40 + 70 * i, 60, 100 + 70 * i, 120), stream=payload.getvalue())
        document.save(path)


def test_same_named_documents_in_different_folders_keep_their_own_images(tmp_path, monkeypatch):
    # 두 문서는 doc_id 와 그림 이름(p1_0_x5.png)이 같고 그림 바이트만 다르다
    monkeypatch.setattr(extract, "IMAGES", tmp_path / "images")
    paths = []
    for folder, color in (("a", "red"), ("b", "blue")):
        (tmp_path / folder).mkdir()
        paths.append(tmp_path / folder / "request.pdf")
        _write_pdf(paths[-1], [color])

    items = [item for path in paths for item in extract._document_images(str(path))]

    assert items[0]["occurrence"]["doc_id"] == items[1]["occurrence"]["doc_id"]
    shown = [Image.open(extract.IMAGES / item["file"]).convert("RGB").getpixel((0, 0)) for item in items]
    assert shown == [(255, 0, 0), (0, 0, 255)]


def test_pdf_placement_failure_keeps_every_image(tmp_path, monkeypatch):
    path = tmp_path / "two.pdf"
    _write_pdf(path, ["red", "green"])
    get_image_rects = pymupdf.Page.get_image_rects
    calls = []

    def first_fails(page, xref, *args, **kwargs):
        calls.append(xref)
        if len(calls) == 1:
            raise RuntimeError("broken placement")
        return get_image_rects(page, xref, *args, **kwargs)

    monkeypatch.setattr(pymupdf.Page, "get_image_rects", first_fails)

    found = extract.pdf_images(str(path))

    assert [f["reason"] for f in found] == [None, None]
    assert found[0]["location"]["bbox_points"] == []
    assert found[1]["location"]["bbox_points"]


def test_one_card_per_location_with_its_last_label_and_last_craft_row():
    # 첫 줄은 그림의 두 위치를 함께 3 으로, 다음 줄은 PDF 위치만 1 로 다시 매겼다
    labels = server.latest_labels([{"image_sha256": "s1", "label": 3, "occurrences": [LOGO_1, PAGE_IMG]},
                                   {"image_sha256": "s1", "label": 1, "occurrences": [PAGE_IMG]}])
    craft_rows = [
        {"classification": "REVIEW_REQUIRED", "source": {"document_sha256": "doc-a"}, "location": LOGO_1},
        {"classification": "OCR_CANDIDATE", "source": {"document_sha256": "doc-a"},
         "location": {**LOGO_1, "marker_start": 99}},
        {"classification": "OCR_UNNECESSARY", "source": {"document_sha256": "doc-b"}, "location": PAGE_IMG},
        {"classification": "OCR_CANDIDATE", "source": {"document_sha256": "doc-b"},
         "location": {**PAGE_IMG, "xref": 19}},
    ]
    images = [{"image_sha256": "s1", "occurrences": [LOGO_1, PAGE_IMG]},
              {"image_sha256": "s2", "occurrences": [{**LOGO_1, "image_name": "BIN2.wmf"}]}]

    out = server.cards(images, labels, server.craft_verdicts(craft_rows))

    assert [(c["image_sha256"], c["occurrence"]) for c in out] == [
        ("s1", LOGO_1), ("s2", {**LOGO_1, "image_name": "BIN2.wmf"}), ("s1", PAGE_IMG)]
    assert [c["label"] for c in out] == [3, None, 1]
    assert [c["craft"] for c in out] == ["OCR_CANDIDATE", None, "OCR_UNNECESSARY"]
    assert len({c["key"] for c in out}) == 3


def test_same_hwp_image_twice_in_one_document_gets_two_keys():
    again = {**LOGO_1, "marker_start": 500, "repeated_occurrences": 2}
    assert server.occurrence_key(LOGO_1) != server.occurrence_key(again)


def test_cards_cut_into_five_even_batches_in_document_order():
    # 11곳: b.pdf 7쪽 (뒤섞어 넣음) + a.hwp 표시 3곳 + 본문 표시 없는 그림 1곳 → a.hwp 먼저, 표시 없는 그림은 그 문서 끝
    pages = [{**PAGE_IMG, "page": p} for p in (5, 1, 7, 2, 6, 3, 4)]
    hwp = [{**LOGO_1, "marker_start": m} for m in (300, 20, 100)]
    unmarked = {**LOGO_1, "image_name": "BIN0.png", "marker_start": None, "repeated_occurrences": 0}
    images = [{"image_sha256": "s1", "occurrences": pages[:4] + [unmarked]},
              {"image_sha256": "s2", "occurrences": hwp + pages[4:]}]

    out = server.cards(images, {}, {})

    assert [(c["occurrence"]["source"], c["occurrence"].get("marker_start"), c["occurrence"].get("page"))
            for c in out[:5]] == [("a.hwp", 20, None), ("a.hwp", 100, None), ("a.hwp", 300, None),
                                  ("a.hwp", None, None), ("b.pdf", None, 1)]
    assert [c["occurrence"]["page"] for c in out[4:]] == [1, 2, 3, 4, 5, 6, 7]
    assert [c["batch"] for c in out] == [1, 1, 1, 2, 2, 3, 3, 4, 4, 5, 5]


def test_merge_keeps_the_later_label_per_location_and_counts_unknown_locations():
    images = [{"image_sha256": "s1", "occurrences": [LOGO_1, PAGE_IMG]}]
    rows = [  # 두 사람의 파일을 이어 붙인 것 — 파일 순서가 아니라 labelled_at 이 늦은 라벨이 이긴다
        # 마지막 줄은 다른 시간대로 적힌 것: 문자열로는 앞서지만 시각으로는 한 시간 늦다
        {"image_sha256": "s1", "label": 3, "labelled_at": "2026-10-15T02:00:00+00:00", "occurrences": [LOGO_1]},
        {"image_sha256": "s1", "label": 2, "labelled_at": "2026-10-15T12:00:00+09:00", "occurrences": [PAGE_IMG]},
        {"image_sha256": "s1", "label": 1, "labelled_at": "2026-10-15T10:00:00+09:00", "occurrences": [LOGO_1]},
        {"image_sha256": "s9", "label": 3, "labelled_at": "2026-10-15T09:00:00+09:00",
         "occurrences": [{**PAGE_IMG, "document_sha256": "doc-z"}]},
    ]

    merged, all_cards, unknown = merge(rows, images)

    assert [(r["occurrences"], r["label"], r["batch"]) for r in merged] == [([LOGO_1], 3, 1), ([PAGE_IMG], 2, 3)]
    assert len(all_cards) == 2 and unknown == 1


@pytest.mark.parametrize("label", [0, 4, "1", None])
def test_label_outside_1_to_3_is_rejected(label):
    with pytest.raises(ValidationError):
        server.LabelRequest(key="k", label=label)


def test_file_endpoint_refuses_paths_outside_images(tmp_path, monkeypatch):
    images = tmp_path / "images"
    (images / "a_1").mkdir(parents=True)
    (images / "a_1" / "BIN1.png").write_bytes(b"png")
    (tmp_path / "labels.jsonl").write_text("{}", encoding="utf-8")
    monkeypatch.setattr(server, "IMAGES", images)

    assert server.file_endpoint("a_1/BIN1.png").path == (images / "a_1" / "BIN1.png").resolve()
    with pytest.raises(HTTPException):
        server.file_endpoint("../labels.jsonl")
