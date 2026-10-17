"""저장된 OCR 전사 검토: 그림별 묶기와 덧붙이기 전용 판정 기록. OCR을 실행하지 않는다."""
from __future__ import annotations

import hashlib
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
    transcription_sha256: str
    verdict: Literal["ok", "partly_wrong", "wrong"]


def read_rows(path: Path) -> list[dict]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def transcription_sha256(row: dict) -> str:
    content = [row[key] for key in ("text", "engine", "image_type")]
    return hashlib.sha256(json.dumps(content, ensure_ascii=False).encode("utf-8")).hexdigest()


def review_cards(captions: list[dict], images: list[dict], reviews: list[dict]) -> list[dict]:
    """같은 그림은 카드 하나로 묶는다. 같은 그림과 전사에 매긴 마지막 판정만 적용한다."""
    files = {row["image_sha256"]: row["file"] for row in images}
    latest = {(row["image_sha256"], row.get("transcription_sha256")): row for row in reviews}
    grouped = {}
    for row in captions:
        sha = row["image_sha256"]
        if sha not in grouped:
            transcription = transcription_sha256(row)
            saved = latest.get((sha, transcription), {})
            grouped[sha] = {key: row[key] for key in ("image_sha256", "text", "engine", "image_type")}
            grouped[sha].update(file=files[sha], transcription_sha256=transcription,
                                occurrences=[], verdict=saved.get("verdict"),
                                reviewed_at=saved.get("reviewed_at"))
        grouped[sha]["occurrences"].append({key: value for key, value in row.items() if key not in _CONTENT})
    return list(grouped.values())


@router.get("")
def get_reviews() -> list[dict]:
    reviews = read_rows(REVIEWS) if REVIEWS.exists() else []
    return review_cards(read_rows(CAPTIONS), read_rows(IMAGES), reviews)


@router.post("/verdicts")
def save_verdict(req: VerdictRequest) -> dict:
    caption = next((row for row in read_rows(CAPTIONS) if row["image_sha256"] == req.image_sha256), None)
    if caption is None:
        raise HTTPException(404, "저장된 OCR 결과에 없는 그림입니다.")
    if req.transcription_sha256 != transcription_sha256(caption):
        raise HTTPException(409, "OCR 결과가 바뀌었습니다. 새로고침한 뒤 다시 검토하세요.")
    entry = {"image_sha256": req.image_sha256, "transcription_sha256": req.transcription_sha256,
             "verdict": req.verdict,
             "reviewed_at": datetime.now().astimezone().isoformat(timespec="seconds")}
    REVIEWS.parent.mkdir(parents=True, exist_ok=True)
    with _append_lock, REVIEWS.open("a", encoding="utf-8") as file:
        file.write(json.dumps(entry, ensure_ascii=False) + "\n")
    return entry
