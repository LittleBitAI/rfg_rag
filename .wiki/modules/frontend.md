---
scope: project
severity: preference
triggers: []
slots: []
sources: []
links: []
---

# frontend/ — browser chat screen and OCR labelling/review screens over the RAG modules, with no RAG logic of its own

## What it is for

Pipeline 6 (`CLAUDE.md:90`). Three screens in one React + Vite app: the question chat, the OCR image labelling screen and the saved-OCR-result review screen. Two FastAPI servers sit behind them. The chat server wraps `answer_question` with the same settings as `04_generation.ipynb` (`frontend/server.py:1-3`); the OCR server reuses preprocessing functions to show images and records labels and verdicts in `artifacts/ocr_labels/` (`frontend/ocr_select/server.py:1-9`).

## Layout and entry points

| Path | Entry point | Does |
| --- | --- | --- |
| `frontend/server.py` | `uvicorn frontend.server:app --port 8767` | `POST /api/ask` (`frontend/server.py:51-53`). At startup loads `config.yaml`, overlays `artifacts/retrieval_settings.jsonl` and opens `HybridIndex` (`frontend/server.py:38-45`). Returns only answer, sources and contexts (`frontend/server.py:29-34`). |
| `frontend/ocr_select/server.py` | `uvicorn frontend.ocr_select.server:app --port 8766` | `/ocr-api/images`, `/ocr-api/export?batch=N`, `/ocr-api/files/...`, `/ocr-api/documents/...`, `/ocr-api/context`, `POST /ocr-api/labels` (`frontend/ocr_select/server.py:113-209`). Mounts the review router (`frontend/ocr_select/server.py:106`). |
| `frontend/ocr_select/review.py` | router under `/ocr-api/review` | `GET` cards and `POST /verdicts` with `ok` / `partly_wrong` / `wrong` (`frontend/ocr_select/review.py:20`, `frontend/ocr_select/review.py:29`, `frontend/ocr_select/review.py:60-77`). Never runs OCR (`frontend/ocr_select/review.py:1`). |
| `frontend/ocr_select/extract.py` | `python -m frontend.ocr_select.extract` | Pulls every image from the RFPs into `artifacts/ocr_labels/images.jsonl` and `images/` (`frontend/ocr_select/extract.py:1-6`). |
| `frontend/ocr_select/merge.py` | `python -m frontend.ocr_select.merge ocr_labels_batch1.jsonl ...` | Merges teammates' exported batches into `merged_labels.jsonl` (`frontend/ocr_select/merge.py:1-4`). |
| `frontend/web/` | `npm run dev` (port 5173) | Pages `index.html`, `ocr.html`, `review.html` (`frontend/web/vite.config.js:12`); sources in `frontend/web/src/App.jsx`, `src/ocr/Ocr.jsx`, `src/review/Review.jsx`. |
| `frontend/start.cmd`, `frontend/start.command` | double-click | Start both uvicorn servers and the Vite dev server in one window (`frontend/start.cmd:8-13`, `frontend/start.command:5-15`). |
| `frontend/DESIGN.md` | — | Design tokens (colours, type scale, spacing, layout widths) for the screens (`frontend/DESIGN.md:1-25`). |

## Dependencies

- Python side imports `rag.config`, `rag.generation.generation.answer_question` and `rag.retrieval.retrieval.HybridIndex` (`frontend/server.py:12-14`); the OCR side imports `collect_inputs`, `make_doc_id`, `_hwp_raw_text` and `_IMG_MARK` from `rag.preprocessing.parsing` (`frontend/ocr_select/extract.py:20-21`, `frontend/ocr_select/server.py:29`) and `local_input` from validation (`frontend/ocr_select/review.py:14`).
- Needs the artifacts of 01 and 02 (chunks, docs, index, retrieval settings) and `OPENAI_API_KEY` (`README.md`, "질문 화면"); each chat question is a paid call logged to `artifacts/api_usage.csv`.
- Web side: React 19, `react-markdown`, `remark-gfm`, Pretendard, Vite (`frontend/web/package.json:9-18`). Vite proxies `/api` to 8767 and `/ocr-api` to 8766 (`frontend/web/vite.config.js:10`).
- Tests: `tests/test_server.py:5`, `tests/test_ocr_labels.py`, `tests/test_ocr_review.py`.
- Nothing else in the repository imports `frontend/`; `merge.py` imports helpers from the OCR server module (`frontend/ocr_select/merge.py:14`).

## What trips a newcomer

- The chat server holds no conversation state. The tab keeps the thread and sends prior turns with each question (`frontend/server.py:2`); the server keeps the last 10 (`frontend/server.py:16`, `frontend/server.py:32`), and the tab builds history only from answered turns (`frontend/web/src/App.jsx:25`). Answers that arrive after `새 스레드` are dropped (`frontend/web/src/App.jsx:30`, `frontend/web/src/App.jsx:76`).
- Startup unpacks exactly one row from `retrieval_settings.jsonl` (`frontend/server.py:41`); a missing file or one with more rows stops the server. Loading the index and KURE-v1 takes tens of seconds, so wait for `Application startup complete` (`README.md:219`). Code or index changes need a launcher restart (`README.md:220`).
- Ports live in three places: the two launchers and the Vite proxy (`README.md:223`, `frontend/web/vite.config.js:4-10`). Vite uses `strictPort`, so a busy 5173 fails instead of moving (`frontend/web/vite.config.js:9`).
- Keep `start.cmd` ASCII: `cmd.exe` reads it in the console code page (`frontend/start.cmd:5`). Both launchers run `npm install` every time on purpose (`frontend/start.cmd:11-12`, `frontend/start.command:13-14`).
- The labelling screen needs `extract` first; without `images.jsonl` the API answers 404 with that instruction (`frontend/ocr_select/server.py:97-102`). Re-running `extract` deletes the old images but keeps `labels.jsonl` (`frontend/ocr_select/extract.py:140`).
- Labels and verdicts are append-only JSONL; the last row per location wins on read (`frontend/ocr_select/server.py:6`, `frontend/ocr_select/server.py:200-209`). Label values are only 1, 2 or 3 (`frontend/ocr_select/server.py:40`). Cards are cut into 5 batches in document order (`frontend/ocr_select/server.py:33`), and the batch sits in the URL (`frontend/web/src/ocr/Ocr.jsx:51`).
- `merge` recounts batches against this machine's `images.jsonl`, so extract from the same `data/rfp.zip` before merging (`frontend/ocr_select/merge.py:3`); a later label wins by time, compared as a timestamp, not a string (`frontend/ocr_select/merge.py:19-20`).
- A review verdict is bound to a hash of the transcription's text, engine and image type (`frontend/ocr_select/review.py:37-39`); changing a caption makes the old verdict stale and its save is rejected (`tests/test_ocr_review.py:85`).
- The OCR modules import private names (`_IMG_MARK`, `_hwp_raw_text`) from `parsing.py` (`frontend/ocr_select/extract.py:20`), so renaming those in preprocessing breaks the frontend.
- The file endpoint refuses paths that resolve outside `images/` (`frontend/ocr_select/server.py:129-134`); keep that guard when touching it.
