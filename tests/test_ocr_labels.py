"""OCR 라벨링 화면: 같은 그림 묶기, 위치마다 카드 하나와 라벨 · CRAFT 기록의 마지막 줄 우선, 1~3 밖 라벨 거부, images/ 밖 파일 차단."""
import pytest
from fastapi import HTTPException
from pydantic import ValidationError

from frontend.ocr_select import server
from frontend.ocr_select.extract import group_images

DOC = {"doc_id": "a_1", "source": "a.hwp", "document_sha256": "doc-a"}
LOGO_1 = {**DOC, "format": "hwp", "image_name": "BIN1.png", "marker_start": 10, "repeated_occurrences": 1}
PAGE_IMG = {"doc_id": "b_2", "source": "b.pdf", "document_sha256": "doc-b", "format": "pdf",
            "page": 3, "image_index": 0, "xref": 18, "bbox_points": [[0, 0, 10, 10]]}


def test_group_images_one_row_per_hash_with_every_location():
    found = [
        {"image_sha256": "s1", "file": "a_1/BIN1.png", "reason": None, "occurrence": LOGO_1},
        {"image_sha256": "s2", "file": "a_1/BIN2.wmf", "reason": "Unsupported vector image encoding",
         "occurrence": {**LOGO_1, "image_name": "BIN2.wmf"}},
        {"image_sha256": "s1", "file": "b_2/p3_0_x18.png", "reason": None, "occurrence": PAGE_IMG},
    ]

    rows = group_images(found)

    assert [r["image_sha256"] for r in rows] == ["s1", "s2"]
    assert rows[0]["file"] == "a_1/BIN1.png"
    assert rows[0]["occurrences"] == [LOGO_1, PAGE_IMG]
    assert rows[1]["viewable"] is False and rows[1]["reason"] == "Unsupported vector image encoding"


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
        ("s1", LOGO_1), ("s1", PAGE_IMG), ("s2", {**LOGO_1, "image_name": "BIN2.wmf"})]
    assert [c["label"] for c in out] == [3, 1, None]
    assert [c["craft"] for c in out] == ["OCR_CANDIDATE", "OCR_UNNECESSARY", None]
    assert len({c["key"] for c in out}) == 3


def test_same_hwp_image_twice_in_one_document_gets_two_keys():
    again = {**LOGO_1, "marker_start": 500, "repeated_occurrences": 2}
    assert server.occurrence_key(LOGO_1) != server.occurrence_key(again)


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
