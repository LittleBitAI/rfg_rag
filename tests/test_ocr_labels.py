"""OCR 라벨링 화면: 같은 그림 묶기, 라벨 · CRAFT 기록의 마지막 줄 우선, 1~3 밖 라벨 거부, images/ 밖 파일 차단."""
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


def test_last_label_and_last_craft_row_win():
    labels = server.latest_labels([{"image_sha256": "s1", "label": 3}, {"image_sha256": "s1", "label": 1}])
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

    assert [c["label"] for c in out] == [1, None]
    assert [o["craft"] for o in out[0]["occurrences"]] == ["OCR_CANDIDATE", "OCR_UNNECESSARY"]
    assert out[1]["occurrences"][0]["craft"] is None


@pytest.mark.parametrize("label", [0, 4, "1", None])
def test_label_outside_1_to_3_is_rejected(label):
    with pytest.raises(ValidationError):
        server.LabelRequest(image_sha256="s1", label=label)


def test_file_endpoint_refuses_paths_outside_images(tmp_path, monkeypatch):
    images = tmp_path / "images"
    (images / "a_1").mkdir(parents=True)
    (images / "a_1" / "BIN1.png").write_bytes(b"png")
    (tmp_path / "labels.jsonl").write_text("{}", encoding="utf-8")
    monkeypatch.setattr(server, "IMAGES", images)

    assert server.file_endpoint("a_1/BIN1.png").path == (images / "a_1" / "BIN1.png").resolve()
    with pytest.raises(HTTPException):
        server.file_endpoint("../labels.jsonl")
