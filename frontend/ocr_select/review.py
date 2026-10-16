"""저장된 OCR 전사 검토: 그림별 묶기와 덧붙이기 전용 판정 기록. OCR을 실행하지 않는다."""
from __future__ import annotations

import json
import threading
from datetime import datetime
from pathlib import Path
from typing import Literal

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, ConfigDict

ROOT = Path(__file__).resolve().parents[2]
CAPTIONS = ROOT / "data" / "ocr_captions.jsonl"
IMAGES = ROOT / "artifacts" / "ocr_labels" / "images.jsonl"
REVIEWS = ROOT / "artifacts" / "ocr_labels" / "reviews.jsonl"
router = APIRouter(prefix="/ocr-api/review")
_append_lock = threading.Lock()
_CONTENT = {"image_sha256", "text", "engine", "image_type", "label"}


class VerdictRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    image_sha256: str
    verdict: Literal["ok", "partly_wrong", "wrong"]


def read_rows(path: Path) -> list[dict]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def review_cards(captions: list[dict], images: list[dict], reviews: list[dict]) -> list[dict]:
    """같은 그림은 카드 하나로 묶고 모든 위치를 남긴다. 판정은 파일의 마지막 줄이 이긴다."""
    files = {row["image_sha256"]: row["file"] for row in images}
    latest = {row["image_sha256"]: row for row in reviews}
    grouped = {}
    for row in captions:
        sha = row["image_sha256"]
        if sha not in grouped:
            saved = latest.get(sha, {})
            grouped[sha] = {key: row[key] for key in ("image_sha256", "text", "engine", "image_type")}
            grouped[sha].update(file=files[sha], occurrences=[], verdict=saved.get("verdict"),
                                reviewed_at=saved.get("reviewed_at"))
        grouped[sha]["occurrences"].append({key: value for key, value in row.items() if key not in _CONTENT})
    return list(grouped.values())


@router.get("")
def get_reviews() -> list[dict]:
    reviews = read_rows(REVIEWS) if REVIEWS.exists() else []
    return review_cards(read_rows(CAPTIONS), read_rows(IMAGES), reviews)


@router.post("/verdicts")
def save_verdict(req: VerdictRequest) -> dict:
    if req.image_sha256 not in {row["image_sha256"] for row in read_rows(CAPTIONS)}:
        raise HTTPException(404, "저장된 OCR 결과에 없는 그림입니다.")
    entry = {"image_sha256": req.image_sha256, "verdict": req.verdict,
             "reviewed_at": datetime.now().astimezone().isoformat(timespec="seconds")}
    REVIEWS.parent.mkdir(parents=True, exist_ok=True)
    with _append_lock, REVIEWS.open("a", encoding="utf-8") as file:
        file.write(json.dumps(entry, ensure_ascii=False) + "\n")
    return entry
