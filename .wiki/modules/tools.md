---
scope: project
severity: preference
triggers: []
slots: []
sources: []
links: []
---

# tools/ — one standalone script, tools/paddle_ocr.py, run in a separate PaddleOCR environment

## What it is for

`tools/paddle_ocr.py` runs PaddleOCR-VL-1.5 over a list of images and records the recognised text and seconds per image (`tools/paddle_ocr.py:1`). It is one of the three OCR engines the OCR benchmark compares; the other two are the OpenAI and Gemini APIs, which `rag/preprocessing/ocr_benchmark.py` calls (`CLAUDE.md`, section 4; `docs/ocr_benchmark.md:155-157`).

## Entry point

`python tools/paddle_ocr.py <manifest> <image_dir> <output.jsonl>` from the separate PaddleOCR environment (`tools/paddle_ocr.py:59-60`, `docs/ocr_benchmark.md:161`).

- Reads the manifest as JSONL rows with `image_sha256` and `file` (`tools/paddle_ocr.py:41`, `tools/paddle_ocr.py:49`).
- Builds `PaddleOCRVL(pipeline_version="v1.5", device="gpu:0", use_layout_detection=False)`, since inputs are already cropped images (`tools/paddle_ocr.py:38`, `docs/ocr_benchmark.md:163`).
- Appends one row per image with `engine`, `image_sha256`, `text`, `seconds` and `cost_usd: null` (`tools/paddle_ocr.py:52-55`). HTML tables in the output become `|`-separated plain text (`tools/paddle_ocr.py:11-31`).

## Dependencies

- Only the standard library at import time; `paddle` and `paddleocr` are imported inside `main` (`tools/paddle_ocr.py:1-8`, `tools/paddle_ocr.py:35-36`). That lets the project `.venv` import the module for tests without installing paddle (`tests/test_paddle_ocr.py:18-20`).
- Nothing in `rag/` imports it. Its output feeds the OCR benchmark summary by hand, and its only code consumer is `tests/test_paddle_ocr.py:6`.

## What trips a newcomer

- Do not install paddle into the project `.venv` (`docs/ocr_benchmark.md:161`), and do not add paddle to `requirements.txt`: the dependency rule admits only packages this repository's own environment imports (`CLAUDE.md`, section 2).
- Reruns resume: images whose `image_sha256` is already in the output file are skipped (`tools/paddle_ocr.py:40`, `tools/paddle_ocr.py:45-46`). To measure again, write to a new output file.
- `seconds` covers only `pipeline.predict`; table clean-up happens after the timer stops (`tools/paddle_ocr.py:48-52`, `docs/ocr_benchmark.md:164`). The CUDA cache is emptied before each image (`tools/paddle_ocr.py:47`).
- PaddleOCR has no API cost, so its row records time instead of cost (`tools/paddle_ocr.py:53`). The repository requires seconds per image for PaddleOCR, while paid engines log cost through `rag/usage.py` (`CLAUDE.md`, section 4).
- `tools/` has no `__init__.py`; `from tools.paddle_ocr import main` works as a namespace package from the repository root (`tests/test_paddle_ocr.py:6`).
- The output holds OCR text from real documents, so it belongs under ignored `artifacts/`, never in git (`CLAUDE.md`, section 1.4).
