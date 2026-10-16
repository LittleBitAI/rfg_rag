"""OCR 비교: 같은 입력·지시문, 호출별 비용·시간, 표준 라이브러리 지표."""
from __future__ import annotations

import base64
import io
import os
import re
import time
import unicodedata
from collections import defaultdict
from pathlib import Path

from PIL import Image
from openai import OpenAI

from rag.config import load_config, read_jsonl
from rag.usage import record_usage

INSTRUCTION = (
    "이미지에 보이는 글자를 읽기 순서대로 빠짐없이 전사하세요. "
    "숫자, 코드, 고유명사, 표 머리글을 원문 그대로 유지하세요. "
    "표는 Markdown으로, 도식은 각 상자의 글자와 화살표 연결을 글로 기록하세요. "
    "보이지 않거나 읽을 수 없는 내용은 추측하지 마세요. 전사 결과만 출력하세요."
)
MODELS = ("PaddleOCR-VL-1.5", "gpt-6-luna", "gemini-3.5-flash-lite")
TOKEN = re.compile(r"[A-Za-z가-힣]+(?:[-_/][A-Za-z0-9가-힣]+)*|\d+(?:[.,]\d+)*%?")


def normalized(text: str) -> str:
    return " ".join(unicodedata.normalize("NFC", text).casefold().split())


def edit_similarity(reference: str, output: str) -> float:
    reference, output = normalized(reference), normalized(output)
    previous = list(range(len(output) + 1))
    for i, a in enumerate(reference, 1):
        current = [i]
        for j, b in enumerate(output, 1):
            current.append(min(current[-1] + 1, previous[j] + 1, previous[j - 1] + (a != b)))
        previous = current
    return 1 - previous[-1] / len(reference) if reference else float(not output)


def key_metrics(reference: str, key_tokens: list[str], output: str) -> dict:
    expected = {normalized(k) for k in key_tokens}
    key_words = set(TOKEN.findall(" ".join(expected)))
    actual = set(TOKEN.findall(normalized(output)))
    # 출력의 숫자·코드와 기준 핵심어를 센다. 기준에 없는 한글 단어도 환각 후보로 센다.
    vocabulary = set(TOKEN.findall(normalized(reference)))
    candidates = {t for t in actual if t in key_words or t not in vocabulary or re.search(r"[a-z0-9]", t)}
    correct = candidates & vocabulary
    found = {k for k in expected if re.search(r"(?<!\w)" + re.escape(k) + r"(?!\w)", normalized(output))}
    return {"key_recall": len(found) / len(expected) if expected else 1.0,
            "key_precision": len(correct) / len(candidates) if candidates else 0.0}


def score(reference: dict, result: dict) -> dict:
    return {"edit_similarity": edit_similarity(reference["text"], result["text"]),
            **key_metrics(reference["text"], reference["key_tokens"], result["text"]),
            "cost_usd": result.get("cost_usd"), "seconds": result["seconds"],
            "empty": float(not result["text"].strip())}


def summarize(references: list[dict], results: list[dict]) -> list[dict]:
    refs = {r["image_sha256"]: r for r in references}
    groups = defaultdict(list)
    seen = set()
    for result in results:
        key = result["engine"], result["image_sha256"]
        if key in seen:
            raise ValueError(f"Duplicate benchmark result: {key}")
        seen.add(key)
        ref = refs[result["image_sha256"]]
        groups[result["engine"], ref["image_type"]].append(score(ref, result))
    expected = {(model, sha) for model in MODELS for sha in refs}
    if seen != expected:
        raise ValueError(f"Incomplete benchmark: {len(expected - seen)} missing results")
    return [_summary(model, kind, rows) for (model, kind), rows in sorted(groups.items())]


def _summary(model: str, kind: str, rows: list[dict]) -> dict:
    means = {name: sum(r[name] for r in rows) / len(rows)
             for name in ("edit_similarity", "key_recall", "key_precision", "seconds", "empty")}
    cost = None if model == MODELS[0] else sum(r["cost_usd"] for r in rows) / len(rows)
    return {"engine": model, "image_type": kind, "n": len(rows), **means, "cost_usd": cost}


def winners(summary: list[dict]) -> dict[str, str]:
    chosen = {}
    for kind in ("table", "text", "diagram"):
        rows = [r for r in summary if r["image_type"] == kind]
        best = max((r for r in rows if r["engine"] != MODELS[0]),
                   key=lambda r: (r["key_recall"], r["key_precision"], -r["cost_usd"]))
        local = next(r for r in rows if r["engine"] == MODELS[0])
        eligible = local["key_recall"] >= best["key_recall"] - 0.05 and local["key_precision"] >= best["key_precision"]
        chosen[kind] = local["engine"] if eligible else best["engine"]
    return chosen


def estimate(images: int, prices: list[float], input_tokens=2000, output_tokens=2000) -> dict:
    return {"images": images, "input_tokens_per_image": input_tokens,
            "output_tokens_per_image": output_tokens,
            "cost_usd": images * (input_tokens * prices[0] + output_tokens * prices[2]) / 1e6}


def api_ocr(path: Path, model: str, subject: str, stage: str) -> dict:
    cfg = load_config()["ocr_benchmark"][model]
    options = {"max_retries": 0}
    if model.startswith("gemini-"):
        options.update(api_key=os.environ["GEMINI_API_KEY"],
                       base_url="https://generativelanguage.googleapis.com/v1beta/openai/")
    client = OpenAI(**options)
    with Image.open(path) as image:
        buffer = io.BytesIO()
        image.convert("RGB").save(buffer, format="PNG")
    encoded = base64.b64encode(buffer.getvalue()).decode("ascii")
    started = time.perf_counter()
    response = client.chat.completions.create(
        model=model, max_completion_tokens=8192,
        messages=[{"role": "user", "content": [
            {"type": "text", "text": INSTRUCTION},
            {"type": "image_url", "image_url": {"url": f"data:image/png;base64,{encoded}"}},
        ]}])
    seconds = time.perf_counter() - started
    usage = record_usage("ocr", model, response.usage.model_dump(), cfg["usd_per_1m_tokens"],
                         subject=subject, evaluation=stage)
    return {"engine": model, "text": response.choices[0].message.content or "",
            "seconds": seconds, "finish_reason": response.choices[0].finish_reason, **usage}


def run_api(images: list[dict], image_dir: Path, model: str, output: Path, stage: str):
    import json

    done = {(r["engine"], r["image_sha256"]) for r in read_jsonl(output)} if output.exists() else set()
    output.parent.mkdir(parents=True, exist_ok=True)
    for image in images:
        sha = image["image_sha256"]
        if (model, sha) in done:
            continue
        result = api_ocr(image_dir / image["file"], model, sha, stage)
        with output.open("a", encoding="utf-8") as stream:
            stream.write(json.dumps({"image_sha256": sha, **result}, ensure_ascii=False) + "\n")
        print(model, sha, result["cost_usd"], result["seconds"], flush=True)


def caption_rows(places: list[dict], inventory: list[dict], results: list[dict], chosen: dict) -> list[dict]:
    types = {r["image_sha256"]: r["image_type"] for r in inventory}
    lookup = {(r["engine"], r["image_sha256"]): r for r in results}
    rows = []
    for place in places:
        sha = place["image_sha256"]
        kind = types[sha]
        engine = chosen[kind]
        result = lookup[engine, sha]
        for occurrence in place["occurrences"]:
            rows.append({"image_sha256": sha, **occurrence, "label": place["label"],
                         "engine": engine, "image_type": kind, "text": result["text"]})
    return rows
