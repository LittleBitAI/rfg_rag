"""OCR 이미지 라벨링 화면의 API — 그림 목록 · 그림 파일 · 라벨 저장 · 원본 보기.

화면의 카드는 그림이 나온 위치 하나씩이다 (같은 그림이 여러 곳에 나오면 카드도 여러 장).
카드를 문서 이름 · 문서 안 위치 순서로 세워 BATCHES 묶음으로 고르게 자른다. 팀원이 묶음을 하나씩 맡아 각자 매기고
결과 내보내기(ocr_labels_batchN.jsonl)를 frontend/ocr_select/merge.py 로 합친다.
라벨은 artifacts/ocr_labels/labels.jsonl 에 덧붙이기만 한다. 다시 매긴 라벨도 새 줄이고, 읽을 때 위치마다 마지막 줄이 이긴다.
artifacts/ocr_selection.jsonl(CRAFT 선별 기록)이 있으면 위치마다 CRAFT 분류를 붙여 보여 주기만 한다.
원본 보기: PDF 는 문서 파일을 그대로 내주고(화면이 #page=N 으로 연다), HWP 는 쪽 번호가 없어 그림 표시 앞뒤의 본문을 내준다.
저장소 최상위에서 실행: .venv\\Scripts\\python -m uvicorn frontend.ocr_select.server:app --port 8766
"""
from __future__ import annotations

import hashlib
import json
import tempfile
import threading
from datetime import datetime
from functools import lru_cache
from pathlib import Path
from typing import Literal

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse, Response
from pydantic import BaseModel

from frontend.ocr_select.extract import IMAGES, OUT, hwp_text
from rag.config import ARTIFACTS, ROOT, load_config, read_jsonl
from rag.preprocessing.parsing import _IMG_MARK, collect_inputs

LABELS = OUT / "labels.jsonl"
CRAFT = ARTIFACTS / "ocr_selection.jsonl"
BATCHES = 5
CONTEXT_CHARS = 1000  # 원본 보기에서 그림 앞 · 뒤로 보일 본문 글자 수
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


def _find(key: str) -> tuple[dict, dict]:
    """위치 이름 → (images.jsonl 의 그림 줄, 그 위치)"""
    found = next(((r, o) for r in _read_images() for o in r["occurrences"] if occurrence_key(o) == key), None)
    if found is None:
        raise HTTPException(404, "images.jsonl 에 없는 위치입니다.")
    return found


@lru_cache(maxsize=1)
def _documents() -> dict[str, Path]:
    """문서 해시 → 경로. extract 와 같은 collect_inputs 로 찾는다 (ZIP 이면 artifacts/raw 에 풀린 파일).
    파일 이름이 아니라 해시로 잇는 것은 다른 폴더의 같은 이름 문서가 있을 수 있어서다."""
    paths = collect_inputs(ROOT / load_config()["paths"]["input"], ARTIFACTS / "raw")
    return {hashlib.sha256(Path(p).read_bytes()).hexdigest(): Path(p) for p in paths}


def _document(document_sha256: str) -> Path:
    if document_sha256 not in _documents():
        _documents.cache_clear()  # 서버를 띄운 채 extract 를 다시 돌렸다면 새 문서 해시는 다시 찾아야 나온다
    if document_sha256 not in _documents():
        raise HTTPException(404, "원본 문서를 찾을 수 없습니다. 그림 목록을 만든 뒤 문서가 바뀌었다면 "
                                 "python -m frontend.ocr_select.extract 를 다시 실행하세요.")
    return _documents()[document_sha256]


@lru_cache(maxsize=8)
def _hwp_text(document_sha256: str) -> str:
    """한 문서를 읽는 데 1초 남짓 걸려, 같은 문서의 그림을 잇달아 볼 때 다시 읽지 않게 최근 문서 몇 개를 둔다.
    경로가 아니라 문서 해시로 두어, 같은 경로의 문서가 바뀌면 새로 읽는다."""
    with tempfile.TemporaryDirectory(prefix="ocr_context_") as image_dir:
        return hwp_text(str(_document(document_sha256)), image_dir)


def context(text: str, start: int) -> dict:
    """start 에 있는 그림 표시와 그 앞 · 뒤 CONTEXT_CHARS 글자. 잘린 맨 앞 · 맨 끝 줄은 버려 줄 중간에서 시작하지 않는다."""
    marker = _IMG_MARK.match(text, start)
    before = text[max(0, start - CONTEXT_CHARS):start]
    after = text[marker.end():marker.end() + CONTEXT_CHARS]
    if start > CONTEXT_CHARS:
        before = before.split("\n", 1)[-1]
    if marker.end() + CONTEXT_CHARS < len(text):
        after = after.rsplit("\n", 1)[0]
    return {"before": before, "marker": marker.group(0), "after": after}


@app.get("/ocr-api/documents/{document_sha256}")
def document_endpoint(document_sha256: str) -> FileResponse:
    """원본 문서 파일. 화면은 PDF 만 #page=N 을 붙여 새 탭으로 연다. 목록에 있는 문서 해시만 받아 다른 파일은 읽지 못한다."""
    return FileResponse(_document(document_sha256))


@app.get("/ocr-api/context")
def context_endpoint(key: str) -> dict:
    """HWP 그림 위치의 앞뒤 본문. HWP 에는 쪽 번호가 없어 원본 보기를 파일 대신 이 글로 보인다."""
    _, o = _find(key)
    if o["format"] != "hwp" or o["marker_start"] is None:
        raise HTTPException(404, "본문에 표시가 있는 HWP 그림만 앞뒤 본문을 보일 수 있습니다.")
    text = _hwp_text(o["document_sha256"])
    if not _IMG_MARK.match(text, o["marker_start"]):  # 그림 목록을 만든 코드와 지금 본문 정리가 다르면 위치가 어긋난다
        raise HTTPException(409, "그림 위치가 지금 본문과 맞지 않습니다. python -m frontend.ocr_select.extract 를 다시 실행하세요.")
    return context(text, o["marker_start"])


@app.post("/ocr-api/labels")
def label_endpoint(req: LabelRequest) -> dict:
    row, occurrence = _find(req.key)
    entry = {"image_sha256": row["image_sha256"], "label": req.label,
             "labelled_at": datetime.now().astimezone().isoformat(timespec="seconds"),
             "occurrences": [occurrence]}
    LABELS.parent.mkdir(parents=True, exist_ok=True)
    with _append_lock, LABELS.open("a", encoding="utf-8") as f:  # 동시 저장이 한 줄 안에서 섞이지 않게
        f.write(json.dumps(entry, ensure_ascii=False) + "\n")
    return {"key": req.key, "label": req.label}
