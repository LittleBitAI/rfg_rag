"""OCR 이미지 라벨링 화면의 API — 그림 목록 · 그림 파일 · 라벨 저장.

라벨은 artifacts/ocr_labels/labels.jsonl 에 덧붙이기만 한다. 다시 매긴 라벨도 새 줄이고, 읽을 때 그림마다 마지막 줄이 이긴다.
artifacts/ocr_selection.jsonl(CRAFT 선별 기록)이 있으면 위치마다 CRAFT 분류를 붙여 보여 주기만 한다.
저장소 최상위에서 실행: .venv\\Scripts\\python -m uvicorn frontend.ocr_select.server:app --port 8766
"""
from __future__ import annotations

import json
import threading
from datetime import datetime
from typing import Literal

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from pydantic import BaseModel

from frontend.ocr_select.extract import IMAGES, OUT
from rag.config import ARTIFACTS, read_jsonl

LABELS = OUT / "labels.jsonl"
CRAFT = ARTIFACTS / "ocr_selection.jsonl"
_append_lock = threading.Lock()


class LabelRequest(BaseModel):
    image_sha256: str
    label: Literal[1, 2, 3]  # 1 꼭 인식 · 2 인식해야 하나 어려움 · 3 필요 없음


def location_key(document_sha256: str, location: dict) -> tuple:
    """CRAFT 기록과 그림 위치를 잇는 열쇠. CRAFT 는 다시 인코딩한 PNG 의 해시를 적으므로 그림 해시로는 이을 수 없다."""
    if location.get("format") == "pdf":
        return document_sha256, "pdf", location.get("page"), location.get("image_index"), location.get("xref")
    return document_sha256, "hwp", location.get("image_name")


def craft_verdicts(rows: list[dict]) -> dict[tuple, str]:
    """위치 → CRAFT 분류. 다시 돌린 CRAFT 는 같은 위치를 또 덧붙이므로 마지막 줄이 이긴다."""
    return {location_key(r["source"]["document_sha256"], r["location"]): r["classification"] for r in rows}


def latest_labels(rows: list[dict]) -> dict[str, int]:
    """그림 해시 → 라벨. 같은 그림의 마지막 줄이 이긴다."""
    return {r["image_sha256"]: r["label"] for r in rows}


def cards(images: list[dict], labels: dict[str, int], verdicts: dict[tuple, str]) -> list[dict]:
    """images.jsonl 의 줄마다 지금 라벨과 위치별 CRAFT 분류(없으면 None)를 붙인다."""
    return [{**row, "label": labels.get(row["image_sha256"]),
             "occurrences": [{**o, "craft": verdicts.get(location_key(o["document_sha256"], o))}
                             for o in row["occurrences"]]}
            for row in images]


def _read_images() -> list[dict]:
    path = OUT / "images.jsonl"
    if not path.exists():
        raise HTTPException(404, "artifacts/ocr_labels/images.jsonl 이 없습니다. "
                                 "먼저 python -m frontend.ocr_select.extract 를 실행하세요.")
    return read_jsonl(path)


app = FastAPI()


@app.get("/ocr-api/images")
def images_endpoint() -> list[dict]:
    labels = latest_labels(read_jsonl(LABELS)) if LABELS.exists() else {}
    verdicts = craft_verdicts(read_jsonl(CRAFT)) if CRAFT.exists() else {}
    return cards(_read_images(), labels, verdicts)


@app.get("/ocr-api/files/{path:path}")
def file_endpoint(path: str) -> FileResponse:
    file = (IMAGES / path).resolve()
    if not file.is_relative_to(IMAGES.resolve()) or not file.is_file():  # ../ 로 images/ 밖을 읽지 못하게
        raise HTTPException(404)
    return FileResponse(file)


@app.post("/ocr-api/labels")
def label_endpoint(req: LabelRequest) -> dict:
    row = next((r for r in _read_images() if r["image_sha256"] == req.image_sha256), None)
    if row is None:
        raise HTTPException(404, "images.jsonl 에 없는 그림입니다.")
    entry = {"image_sha256": req.image_sha256, "label": req.label,
             "labelled_at": datetime.now().astimezone().isoformat(timespec="seconds"),
             "occurrences": row["occurrences"]}
    LABELS.parent.mkdir(parents=True, exist_ok=True)
    with _append_lock, LABELS.open("a", encoding="utf-8") as f:  # 반복 로고 한 줄은 수십 KB — 동시 저장이 줄을 섞지 않게
        f.write(json.dumps(entry, ensure_ascii=False) + "\n")
    return {"image_sha256": req.image_sha256, "label": req.label}
