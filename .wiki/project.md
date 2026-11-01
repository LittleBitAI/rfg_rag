---
scope: project
severity: preference
triggers: []
slots: []
sources: []
links: []
---

# rfg_rag — a RAG question-answering system over Korean public-sector RFPs, built as five notebook pipelines plus a browser screen

## What it is for

The product (named 입찰메이트 in `README.md`) reads public-agency requests for proposals (RFP, about 98 PDF / HWP / HWPX documents) and answers questions about them with cited evidence. A question is rewritten with the recent conversation, searched with hybrid BM25 + embedding retrieval (routed to one agency's documents when the question names it), and answered by an OpenAI model from the retrieved chunks only. The same answers file is then scored four ways so a wrong answer can be traced to retrieval, generation or grounding. Results and measurement reports live under `docs/`; team reports are binary files under `docs/reports/`.

The repository rules for agents are `CLAUDE.md` and `AGENTS.md` (byte-identical). They fix the pipeline split, ownership, the dataset-privacy rule, the dependency rule and the pre-commit checks; read them before changing code.

## Top-level layout

| Path | Role |
| --- | --- |
| `01_preprocessing.ipynb` … `05_evaluation.ipynb` | One notebook per pipeline. Configuration, function calls and result display only; no logic. Each reads the previous one's outputs from `artifacts/`. |
| `config.yaml` | Shared settings, one block per pipeline (`paths`, `parsing`, `ocr`, `ocr_benchmark`, `chunking`, `embedding`, `retrieval`, `rewrite`, `validation`, `llm`, `evaluation`). Notebook settings cells override values in memory without editing the file. |
| `rag/` | All pipeline logic (see below). |
| `golden_pipeline/` | Per-topic golden dataset builder for pipeline 3 (Validation). Self-contained: imports nothing from `rag/`, writes only under `golden_pipeline/outputs/` (ignored). Own CLI `python -m golden_pipeline.cli`, launched by `golden_pipeline/golden.cmd` / `golden.command`; topic specs in `golden_pipeline/configs/`, prompts in `golden_pipeline/prompts/`. Described in `golden_pipeline/README.md`. |
| `frontend/` | Pipeline 6: browser screens over the RAG modules, holding no RAG logic. |
| `preprocessing/` | The preprocessing owner's EDA and chunking-experiment notebooks (history, not part of the pipeline run). |
| `tools/paddle_ocr.py` | Runs PaddleOCR-VL in its own separate environment and records per-image text and seconds. |
| `tests/` | The pytest gate; `tests/golden/` covers `golden_pipeline/`. |
| `docs/` | Topic documents (`retrieval.md`, `evaluation.md`, `ocr.md`, `quantity_filter*.md`, `index_rollback.md`, …), benchmark reports (`docs/benchmarks/seven_model/`), review notes (`docs/research/`), team reports (`docs/reports/`). |
| `data/` | Local inputs, mostly untracked: `data/rfp.zip`, `data/data_list.csv` (file name → agency), `data/ocr_captions.jsonl`. Only aggregate OCR benchmark JSON under `data/ocr_benchmark/` is tracked. |
| `artifacts/` | Untracked. Every file the notebooks hand to each other, plus `api_usage.csv`, OCR labels and review scratch. |
| `requirements.txt`, `requirements-benchmark.txt` | Main environment; the second adds pinned versions for the separate embedding-benchmark environment (`.venv-benchmark*`). |
| `pyproject.toml` | Ruff config: only `C901` (max complexity 8) and `PLR0915`. |
| `.claude/settings.json` | Agent permission denials (in-place `sed`/`perl` edits, `powershell`, `git reset --hard`, `git clean -fdx`). |

## Inside `rag/`

| Module | Pipeline | Does |
| --- | --- | --- |
| `rag/config.py` | shared | Loads `config.yaml` and `.env`; JSONL read/write/append and checkpoint reading. |
| `rag/usage.py` | shared | Appends one row per paid API call (stage `ocr`, `rewrite`, `answer`, `judge`) to `artifacts/api_usage.csv`, with cost; summaries for notebook last cells. |
| `rag/preprocessing/parsing.py`, `chunking.py` | 1 | PDF / HWP / HWPX parsing (with runtime patches for known bugs in `langchain-community` and `hwp-hwpx-parser`), chunking, reading a prepared preprocessing package. |
| `rag/preprocessing/ocr_captions.py`, `ocr_selection.py`, `craft_detector.py`, `ocr_benchmark.py` | 1 | Saved OCR captions (default path, no API calls), CRAFT-based image selection, the OCR engine benchmark. |
| `rag/retrieval/indexing.py` | 2 | `build_index`: Kiwi-tokenised BM25 + KURE-v1 FAISS embeddings, requirement-code extraction, quantity index. User dictionary in `rag/retrieval/kiwi_user_words.json`. |
| `rag/retrieval/rewrite.py` | 2 | `rewrite_question`: LLM rewrite of the question using conversation history. |
| `rag/retrieval/retrieval.py` | 2 | The index object with `search` and `search_with_candidates` (pre-packing candidate snapshot); agency routing, RRF or min-max fusion, linked-chunk expansion, dedup, token-budget packing. |
| `rag/retrieval/quantity_filter.py`, `quantities.py`, `quantity_metadata.py` | 2 | Filter for multi-project numeric-condition questions (for example a budget threshold). |
| `rag/retrieval/benchmark/` | 2 | Offline seven-embedding-model benchmark, `python -m rag.retrieval.benchmark prepare|run|summarize`. |
| `rag/validation/validation.py`, `evidence.py`, `local_inputs.py` | 3 | Loads and checks evaluation items (`load_eval_items`, `check_eval_items`), maps gold evidence to chunk IDs. |
| `rag/generation/generation.py` | 4 | `answer_question` (rewrite → search → generate with citations) and checkpointed `answer_questions` over an eval set. |
| `rag/evaluation/evaluation.py`, `ir.py` | 5 | `evaluate_retrieval`, `evaluate_generation`, `evaluate_grounding`, `evaluate_end_to_end`, and `rerun_retrieval` (retrieval-only rerun without API calls); IR metrics in `ir.py`. RAGAS judges or a local judge. |

## How the parts talk

Data moves through files in `artifacts/`, in notebook order:

1. `01` writes `artifacts/chunks.jsonl` and `docs.jsonl`.
2. `02` builds `artifacts/index/` and `retrieval_settings.jsonl` from the chunks.
3. `03` writes `artifacts/eval_set.jsonl` (golden items, optionally from `golden_pipeline` releases).
4. `04` loads the index, answers the eval set and writes `artifacts/answers.jsonl` with ranked candidates, rewrite, sent chunk IDs and retrieval settings per row.
5. `05` scores that one answers file and writes `retrieval.csv`, `generation.csv`, `grounding.csv`, `end_to_end.csv` beside it.

The frontend calls the same Python functions instead of reimplementing them. `frontend/server.py` is a FastAPI app whose `/api/ask` wraps `answer_question` over the index loaded at startup (port 8767). `frontend/ocr_select/server.py` is a second FastAPI app under `/ocr-api/*` (port 8766) for OCR image labelling and saved-result review, writing labels and verdicts to `artifacts/ocr_labels/`. `frontend/web/` is a React + Vite app with three entry pages (`index.html` chat, `ocr.html` labelling, `review.html` review) whose dev server (port 5173) proxies to both APIs via `frontend/web/vite.config.js`. Screen design notes are in `frontend/DESIGN.md`.

External services: the OpenAI API (rewrite, answer, RAGAS judges, optional OCR), optional Gemini via its OpenAI-compatible endpoint for OCR, and optional Langfuse Cloud tracing when `.env` has its keys. Every path must run without Langfuse keys.

## Build, run, test

- Setup (`README.md`, "빠른 시작"): Python 3.10 venv at `.venv`, install the CUDA 12.8 build of `torch` and `torchvision` first, then `requirements.txt`. `.env` holds `OPENAI_API_KEY` and optional Langfuse keys. `data/` and `.env` are passed around by hand, never committed.
- Run the pipeline: open the five notebooks with the `.venv` kernel and run 01 → 05. The first run downloads KURE-v1. Rebuild the index (02's load, settings and `build_index` cells) whenever `indexing.py` or the dictionary changes; `docs/index_rollback.md` covers rolling back.
- Run the screens: `frontend\start.cmd` (Windows) or `frontend/start.command` (macOS) starts both APIs and the Vite dev server in one window; or run `uvicorn frontend.server:app --port 8767` plus `npm run dev` in `frontend/web` by hand. Needs Node.js and the artifacts from 01 and 02.
- Team VM `codeit` (Linux, NVIDIA L4) runs the same code over VS Code Remote-SSH; its gate uses `.venv/bin/python`.
- Checks before every commit: `ruff check .` clean; the gate `.venv\Scripts\python -m pytest -q tests` (the `gate_cmd` slot in `.wiki/adapter.toml`); `git diff --no-index CLAUDE.md AGENTS.md` empty. `tests/conftest.py` redirects the usage CSV to a temp directory and blanks the Langfuse keys, so tests behave like a teammate's environment without keys.
