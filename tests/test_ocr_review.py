import json
from datetime import datetime

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from frontend.ocr_select import review


def write_rows(path, rows):
    path.write_text("".join(json.dumps(row, ensure_ascii=False) + "\n" for row in rows), encoding="utf-8")


@pytest.fixture
def saved_results(tmp_path, monkeypatch):
    captions = []
    for index in range(7):
        image = index % 5
        location = {"format": "pdf", "page": index + 1, "image_index": 0, "xref": index} if index < 3 else {
            "format": "hwp", "image_name": f"BIN{index}.png", "marker_start": None if index % 5 == 0 else index * 10}
        captions.append({"image_sha256": f"image-{image}", "text": f"# 전사 {image}\n\n| A | B |\n| --- | --- |\n| 1 | 2 |",
                         "engine": "saved-engine", "image_type": "table" if image % 2 else "diagram", "label": 1,
                         "doc_id": f"doc-{index}", "document_sha256": f"document-{index}",
                         "source": f"문서 {index}.{location['format']}", **location})
    images = [{"image_sha256": f"image-{i}", "file": f"image-{i}.png"} for i in range(5)]
    monkeypatch.setattr(review, "CAPTIONS", tmp_path / "captions.jsonl")
    monkeypatch.setattr(review, "IMAGES", tmp_path / "images.jsonl")
    monkeypatch.setattr(review, "REVIEWS", tmp_path / "reviews.jsonl")
    write_rows(review.CAPTIONS, captions)
    write_rows(review.IMAGES, images)
    app = FastAPI()
    app.include_router(review.router)
    with TestClient(app) as client:
        yield client, captions


def test_shared_images_group_with_all_places_and_unchanged_transcriptions(saved_results):
    client, captions = saved_results
    response = client.get("/ocr-api/review")
    assert response.status_code == 200
    cards = response.json()
    assert len(cards) == len({card["image_sha256"] for card in cards}) == 5
    assert sum(len(card["occurrences"]) for card in cards) == 7
    for card in cards:
        originals = [row for row in captions if row["image_sha256"] == card["image_sha256"]]
        assert card["occurrences"] == [{key: value for key, value in row.items()
                                        if key not in {"image_sha256", "text", "engine", "image_type", "label"}}
                                       for row in originals]
        assert (card["text"], card["engine"], card["image_type"]) == (
            originals[0]["text"], originals[0]["engine"], originals[0]["image_type"])
        assert card["file"] == f"{card['image_sha256']}.png"
        assert card["verdict"] is None and card["reviewed_at"] is None


def test_verdicts_append_and_reload_uses_last_row_without_changing_inputs_or_usage(saved_results):
    client, captions = saved_results
    usage = review.ROOT / "artifacts" / "api_usage.csv"
    before = {path: path.read_bytes() for path in (review.CAPTIONS, review.IMAGES, usage) if path.exists()}
    card = client.get("/ocr-api/review").json()[0]
    identity = {key: card[key] for key in ("image_sha256", "transcription_sha256")}
    entries = []
    for verdict in ("wrong", "partly_wrong", "ok"):
        prefix = review.REVIEWS.read_bytes() if review.REVIEWS.exists() else b""
        response = client.post("/ocr-api/review/verdicts", json={**identity, "verdict": verdict})
        assert response.status_code == 200
        entry = response.json()
        assert set(entry) == {"image_sha256", "transcription_sha256", "verdict", "reviewed_at"}
        assert entry["transcription_sha256"] == identity["transcription_sha256"]
        assert entry["verdict"] == verdict
        assert datetime.fromisoformat(entry["reviewed_at"]).tzinfo is not None
        assert review.REVIEWS.read_bytes().startswith(prefix)
        entries.append(entry)
    assert review.read_rows(review.REVIEWS) == entries
    reloaded = client.get("/ocr-api/review").json()
    assert reloaded[0]["verdict"] == "ok" and reloaded[0]["reviewed_at"] == entries[-1]["reviewed_at"]
    assert all(card["verdict"] is None for card in reloaded[1:])
    assert all(path.read_bytes() == payload for path, payload in before.items())
    captions[0]["source"] = "renamed.pdf"
    write_rows(review.CAPTIONS, captions)
    assert client.get("/ocr-api/review").json()[0]["verdict"] == "ok"


@pytest.mark.parametrize("field,value", [("text", "변경된 전사"), ("engine", "new-engine"), ("image_type", "text")])
def test_changed_transcription_requires_new_review_and_rejects_stale_save(saved_results, field, value):
    client, captions = saved_results
    original = client.get("/ocr-api/review").json()[0]
    payload = {key: original[key] for key in ("image_sha256", "transcription_sha256")}
    assert client.post("/ocr-api/review/verdicts", json={**payload, "verdict": "ok"}).status_code == 200
    before = review.REVIEWS.read_bytes()
    for row in captions:
        if row["image_sha256"] == original["image_sha256"]:
            row[field] = value
    write_rows(review.CAPTIONS, captions)

    changed = client.get("/ocr-api/review").json()[0]
    assert changed[field] == value
    assert changed["transcription_sha256"] != original["transcription_sha256"]
    assert changed["verdict"] is None and changed["reviewed_at"] is None
    assert client.post("/ocr-api/review/verdicts", json={**payload, "verdict": "wrong"}).status_code == 409
    assert review.REVIEWS.read_bytes() == before

    payload["transcription_sha256"] = changed["transcription_sha256"]
    assert client.post("/ocr-api/review/verdicts", json={**payload, "verdict": "partly_wrong"}).status_code == 200
    assert client.get("/ocr-api/review").json()[0]["verdict"] == "partly_wrong"
    entries = review.read_rows(review.REVIEWS)
    assert [row["transcription_sha256"] for row in entries] == [
        original["transcription_sha256"], changed["transcription_sha256"]]
    assert review.REVIEWS.read_bytes().startswith(before)


def test_legacy_verdict_without_transcription_identity_is_preserved_but_not_applied(saved_results):
    client, _ = saved_results
    write_rows(review.REVIEWS, [{"image_sha256": "image-0", "verdict": "ok", "reviewed_at": "2026-10-17T00:00:00Z"}])
    before = review.REVIEWS.read_bytes()
    card = client.get("/ocr-api/review").json()[0]
    assert card["verdict"] is None and card["reviewed_at"] is None
    assert client.post("/ocr-api/review/verdicts", json={"image_sha256": "image-0", "verdict": "ok"}).status_code == 422
    assert review.REVIEWS.read_bytes() == before


@pytest.mark.parametrize("payload,status", [
    ({"image_sha256": "unknown", "transcription_sha256": "unknown", "verdict": "ok"}, 404),
    ({"image_sha256": "image-0", "verdict": "maybe"}, 422),
    ({"image_sha256": "image-0", "verdict": "ok", "text": "edited"}, 422),
])
def test_invalid_verdict_does_not_create_a_review_file(saved_results, payload, status):
    client, _ = saved_results
    card = client.get("/ocr-api/review").json()[0]
    identity = {key: card[key] for key in ("image_sha256", "transcription_sha256")}
    assert client.post("/ocr-api/review/verdicts", json={**identity, **payload}).status_code == status
    assert not review.REVIEWS.exists()
