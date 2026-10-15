"""OCR 이미지 라벨링 화면의 API — 그림 목록 · 그림 파일 · 라벨 저장.

화면의 카드는 그림이 나온 위치 하나씩이다 (같은 그림이 여러 곳에 나오면 카드도 여러 장).
카드를 문서 이름 · 문서 안 위치 순서로 세워 BATCHES 묶음으로 고르게 자른다. 팀원이 묶음을 하나씩 맡아 각자 매기고
결과 내보내기(ocr_labels_batchN.jsonl)를 frontend/ocr_select/merge.py 로 합친다.
라벨은 artifacts/ocr_labels/labels.jsonl 에 덧붙이기만 한다. 다시 매긴 라벨도 새 줄이고, 읽을 때 위치마다 마지막 줄이 이긴다.
artifacts/ocr_selection.jsonl(CRAFT 선별 기록)이 있으면 위치마다 CRAFT 분류를 붙여 보여 주기만 한다.
저장소 최상위에서 실행: .venv\\Scripts\\python -m uvicorn frontend.ocr_select.server:app --port 8766
"""
from __future__ import annotations

import json
import threading
from datetime import datetime
from typing import Literal

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse, Response
from pydantic import BaseModel

from frontend.ocr_select.extract import IMAGES, OUT
from rag.config import ARTIFACTS, read_jsonl

LABELS = OUT / "labels.jsonl"
CRAFT = ARTIFACTS / "ocr_selection.jsonl"
BATCHES = 5
_append_lock = threading.Lock()


class LabelRequest(BaseModel):
    key: str  # occurrence_key — 카드 하나 = 그림이 나온 위치 하나
    label: Literal[1, 2, 3]  # 1 꼭 인식 · 2 인식해야 하나 어려움 · 3 필요 없음


def occurrence_key(o: dict) -> str:
    """그림이 나온 위치 하나의 이름. 한 문서에서 같은 그림이 여러 번 나오면 HWP 는 marker_start 로 가른다."""
    if o["format"] == "pdf":
        return f'{o["document_sha256"]}:pdf:{o["page"]}:{o["image_index"]}:{o["xref"]}'
    return f'{o["document_sha256"]}:hwp:{o["image_name"]}:{o["marker_start"]}'


def location_key(document_sha256: str, location: dict) -> tuple:
    """CRAFT 기록과 그림 위치를 잇는 열쇠. CRAFT 는 다시 인코딩한 PNG 의 해시를 적으므로 그림 해시로는 이을 수 없다."""
    if location.get("format") == "pdf":
        return document_sha256, "pdf", location.get("page"), location.get("image_index"), location.get("xref")
    return document_sha256, "hwp", location.get("image_name")


def craft_verdicts(rows: list[dict]) -> dict[tuple, str]:
    """위치 → CRAFT 분류. 다시 돌린 CRAFT 는 같은 위치를 또 덧붙이므로 마지막 줄이 이긴다."""
    return {location_key(r["source"]["document_sha256"], r["location"]): r["classification"] for r in rows}


def latest_labels(rows: list[dict]) -> dict[str, dict]:
    """위치 → 그 위치의 마지막 라벨 줄. 라벨 줄의 occurrences 마다 적용하고, 같은 위치는 마지막 줄이 이긴다."""
    return {occurrence_key(o): r for r in rows for o in r["occurrences"]}


def _document_order(o: dict) -> tuple:
    """문서 이름 → 문서 안 위치. 본문 표시가 없는 HWP 그림은 문서 끝에 이름 순으로 둔다."""
    if o["format"] == "pdf":
        return o["source"], (o["page"], o["image_index"]), ""
    return o["source"], (o["marker_start"] is None, o["marker_start"] or 0), o["image_name"]


def cards(images: list[dict], labels: dict[str, dict], verdicts: dict[tuple, str]) -> list[dict]:
    """images.jsonl 의 위치마다 카드 하나 — 그림 정보에 그 위치의 라벨 · CRAFT 분류(없으면 None) · 묶음 번호를 붙인다.
    묶음은 문서 순서로 세운 카드를 BATCHES 개로 고르게 자른 것이라 같은 images.jsonl 이면 어느 컴퓨터에서나 같다."""
    out = []
    for row in images:
        image = {k: v for k, v in row.items() if k != "occurrences"}
        for o in row["occurrences"]:
            key = occurrence_key(o)
            out.append({**image, "key": key, "occurrence": o, "label": labels[key]["label"] if key in labels else None,
                        "craft": verdicts.get(location_key(o["document_sha256"], o))})
    out.sort(key=lambda c: _document_order(c["occurrence"]))
    for i, card in enumerate(out):
        card["batch"] = i * BATCHES // len(out) + 1
    return out


def result_rows(cards: list[dict], labels: dict[str, dict]) -> list[dict]:
    """라벨이 있는 카드마다 결과 한 줄 — labels.jsonl 과 같은 모양에 묶음 번호를 더하고, occurrences 는 그 위치 하나."""
    return [{"image_sha256": c["image_sha256"], "label": labels[c["key"]]["label"],
             "labelled_at": labels[c["key"]]["labelled_at"], "occurrences": [c["occurrence"]], "batch": c["batch"]}
            for c in cards if c["key"] in labels]


def _read_images() -> list[dict]:
    path = OUT / "images.jsonl"
    if not path.exists():
        raise HTTPException(404, "artifacts/ocr_labels/images.jsonl 이 없습니다. "
                                 "먼저 python -m frontend.ocr_select.extract 를 실행하세요.")
    return read_jsonl(path)


app = FastAPI()


def _labels() -> dict[str, dict]:
    return latest_labels(read_jsonl(LABELS)) if LABELS.exists() else {}


@app.get("/ocr-api/images")
def images_endpoint() -> list[dict]:
    verdicts = craft_verdicts(read_jsonl(CRAFT)) if CRAFT.exists() else {}
    return cards(_read_images(), _labels(), verdicts)


@app.get("/ocr-api/export")
def export_endpoint(batch: int) -> Response:
    """묶음 하나의 결과를 ocr_labels_batchN.jsonl 로 내려받게 한다."""
    labels = _labels()
    rows = result_rows([c for c in cards(_read_images(), labels, {}) if c["batch"] == batch], labels)
    body = "".join(json.dumps(r, ensure_ascii=False) + "\n" for r in rows)
    return Response(body, media_type="application/x-ndjson",
                    headers={"Content-Disposition": f'attachment; filename="ocr_labels_batch{batch}.jsonl"'})


@app.get("/ocr-api/files/{path:path}")
def file_endpoint(path: str) -> FileResponse:
    file = (IMAGES / path).resolve()
    if not file.is_relative_to(IMAGES.resolve()) or not file.is_file():  # ../ 로 images/ 밖을 읽지 못하게
        raise HTTPException(404)
    return FileResponse(file)


@app.post("/ocr-api/labels")
def label_endpoint(req: LabelRequest) -> dict:
    found = next(((r, o) for r in _read_images() for o in r["occurrences"] if occurrence_key(o) == req.key), None)
    if found is None:
        raise HTTPException(404, "images.jsonl 에 없는 위치입니다.")
    row, occurrence = found
    entry = {"image_sha256": row["image_sha256"], "label": req.label,
             "labelled_at": datetime.now().astimezone().isoformat(timespec="seconds"),
             "occurrences": [occurrence]}
    LABELS.parent.mkdir(parents=True, exist_ok=True)
    with _append_lock, LABELS.open("a", encoding="utf-8") as f:  # 동시 저장이 한 줄 안에서 섞이지 않게
        f.write(json.dumps(entry, ensure_ascii=False) + "\n")
    return {"key": req.key, "label": req.label}
