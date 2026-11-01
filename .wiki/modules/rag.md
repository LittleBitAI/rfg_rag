---
scope: project
severity: preference
triggers: []
slots: []
sources: []
links: []
---

# rag/ — all RAG pipeline logic: preprocessing, retrieval, validation, generation, evaluation, plus shared config and usage logging

## What it is for

Every piece of logic the five notebooks call lives here; notebooks only configure, call and display (`CLAUDE.md`, section 4). One subpackage per pipeline, each owned by one person, plus two shared modules. Files hand over through `artifacts/` in notebook order.

| Subpackage | Pipeline | Main entry points |
| --- | --- | --- |
| `rag/config.py` | shared | `load_config`, `write_jsonl`, `read_jsonl`, `append_jsonl`, `read_checkpoint`; `ROOT`, `ARTIFACTS` (`rag/config.py:11-55`) |
| `rag/usage.py` | shared | `record_usage`, `UsageCallback`, `usage_summary` (`rag/usage.py:16`, `rag/usage.py:52`, `rag/usage.py:67`) |
| `rag/preprocessing/` | 1 | `parsing.collect_inputs`, `parsing.parse_documents` (`rag/preprocessing/parsing.py:73`, `rag/preprocessing/parsing.py:624`); `chunking.chunk_documents`, `load_package`, `load_v11_package`, `save_chunks` (`rag/preprocessing/chunking.py:148-244`) |
| `rag/retrieval/` | 2 | `indexing.build_index` (`rag/retrieval/indexing.py:206`); `retrieval.HybridIndex` with `search` and `search_with_candidates` (`rag/retrieval/retrieval.py:150`, `rag/retrieval/retrieval.py:200-223`); `rewrite.rewrite_question` (`rag/retrieval/rewrite.py:34`) |
| `rag/validation/` | 3 | `validation.load_eval_items`, `check_eval_items` (`rag/validation/validation.py:162`, `rag/validation/validation.py:190`); `evidence.label_evidence` and reports (`rag/validation/evidence.py:126-196`); `local_inputs` CLI (`rag/validation/local_inputs.py:80-93`) |
| `rag/generation/` | 4 | `answer_question`, `answer_questions` (`rag/generation/generation.py:94`, `rag/generation/generation.py:130`) |
| `rag/evaluation/` | 5 | `evaluate_retrieval`, `evaluate_generation`, `evaluate_grounding`, `evaluate_end_to_end`, `rerun_retrieval` (`rag/evaluation/evaluation.py:415-474`); IR metrics in `rag/evaluation/ir.py:12-101` |

## How the parts call each other

- 01: `parse_documents` turns PDF / HWP / HWPX into records (`rag/preprocessing/parsing.py:1-2`); `chunking` writes `artifacts/chunks.jsonl` and `docs.jsonl` for 02 and 03 (`rag/preprocessing/chunking.py:1-2`). Saved OCR captions are read by `ocr_captions.py` with no API call (`rag/preprocessing/ocr_captions.py:1`).
- 02: `build_index` writes `faiss.index`, `bm25_tokens.json`, `texts.sha256` and the quantity files under `artifacts/index/` (`rag/retrieval/indexing.py:265-293`). `HybridIndex` loads them plus chunks, docs and the agency CSV (`rag/retrieval/retrieval.py:160-182`).
- 04: `answer_question` runs rewrite → `retrieval_fields` → `generate` (`rag/generation/generation.py:94-108`). `retrieval_fields` is the one place that turns a search into the saved fields `ranked_candidates`, `context_chunk_ids`, `retrieval_settings` (`rag/retrieval/retrieval.py:38-44`). The same function serves `rerun_retrieval` (`rag/evaluation/evaluation.py:428-438`).
- 05: every evaluator first validates the answers file against `ANSWER_FIELDS` (`rag/evaluation/evaluation.py:362-374`, `rag/evaluation/evaluation.py:405-412`).
- Cross-package imports to know: generation imports `EVAL_ITEM_FIELDS` from validation (`rag/generation/generation.py:20`); evaluation imports `Reranker` from indexing for the local judge (`rag/evaluation/evaluation.py:30`); `quantity_filter` and `quantity_metadata` feed both index building and the quantity path in search (`rag/retrieval/indexing.py:21`, `rag/retrieval/retrieval.py:23`).
- `rag/retrieval/benchmark/` is an offline seven-model embedding benchmark, `python -m rag.retrieval.benchmark prepare|run|summarize` (`rag/retrieval/benchmark/__main__.py:1-29`). It reads model definitions from `docs/benchmarks/seven_model/models.json` and writes to `artifacts/seven_model_anchor` (`rag/retrieval/benchmark/common.py:13-15`, `rag/retrieval/benchmark/common.py:34-35`), and runs in the separate benchmark environment (`requirements-benchmark.txt`).

## Who depends on it

The five root notebooks; `frontend/server.py:12-14` and the OCR screens; `tests/`. `golden_pipeline/` deliberately imports nothing from here (`golden_pipeline/README.md:10`).

## What trips a newcomer

- Langfuse is optional everywhere. `load_config` turns tracing off unless both keys are set (`rag/config.py:19-20`), and scores are sent only for rows with a `trace_id` (`rag/evaluation/evaluation.py:332-343`). Generation and rewrite use Langfuse's wrapped `openai` module (`rag/generation/generation.py:14`, `rag/retrieval/rewrite.py:6`), so keep that import when touching the call.
- Every paid call must go through `record_usage` or `UsageCallback` into `artifacts/api_usage.csv` (`rag/generation/generation.py:87`, `rag/retrieval/rewrite.py:49`, `rag/usage.py:52-64`). Cost subtracts cached input and does not add reasoning tokens twice (`rag/usage.py:18-26`). An older CSV header is rewritten with the new columns before appending (`rag/usage.py:33-49`).
- The index refuses to load when it no longer matches: the BM25 tokenizer fingerprint hashes the whole `indexing.py` source, the user dictionary and Kiwi versions (`rag/retrieval/indexing.py:174-179`, `rag/retrieval/retrieval.py:162-165`), and `texts.sha256` must match the current chunks (`rag/retrieval/retrieval.py:141-147`). Any edit to `indexing.py`, even a comment, means rerunning 02's `build_index`.
- `build_index` builds into a temporary sibling folder and swaps it in, restoring the old index on failure (`rag/retrieval/indexing.py:206-227`); do not write into `artifacts/index/` directly.
- Search routes and ranks with the rewritten query but generation answers the original question (`rag/retrieval/retrieval.py:200-210`, `rag/generation/generation.py:97-103`). An empty rewrite falls back to the original (`rag/retrieval/rewrite.py:51`). History goes to rewrite as quoted text, not as assistant turns, because assistant turns made the model continue the answer (`rag/retrieval/rewrite.py:35-38`).
- `search()` must keep its return values and order; `search_with_candidates` adds only a read-only snapshot of `MappingProxyType` rows (`rag/retrieval/retrieval.py:205-223`, `rag/retrieval/retrieval.py:266-277`, `CLAUDE.md`, section 5).
- Numeric-condition questions without an agency route take a separate quantity-filter path that returns `FilterHits` (`rag/retrieval/retrieval.py:211-213`, `rag/retrieval/retrieval.py:225-249`). `rag/retrieval/quantities.py` is a copy of a parser from `golden_pipeline`, maintained separately (`rag/retrieval/quantities.py:1`).
- With `fusion: minmax`, a component weighted 0 contributes no candidates at all (`rag/retrieval/retrieval.py:300-303`).
- Answer checkpoints are keyed by index fingerprint plus LLM, rewrite and history settings (`rag/generation/generation.py:111-115`, `rag/retrieval/retrieval.py:191-197`). Saved answers are reused only up to the first changed question, because earlier answers become later history (`rag/generation/generation.py:118-127`). `reset_context` clears history before an item (`rag/generation/generation.py:151-152`).
- 04 stops before any paid call when the eval set lacks a field in `EVAL_ITEM_FIELDS` (`rag/generation/generation.py:139-141`, `rag/validation/validation.py:187`); 05 does the same for the answers file (`rag/evaluation/evaluation.py:405-412`). Booleans are rejected where numbers are expected (`rag/evaluation/evaluation.py:399-402`).
- `evaluation.judge: local` scores faithfulness and factual correctness with the local cross-encoder, at no API cost (`rag/evaluation/evaluation.py:6-8`, `rag/evaluation/evaluation.py:322-325`); its scale differs from RAGAS. End-to-end cost sums answer and rewrite only, not judge cost (`rag/evaluation/evaluation.py:471-472`).
- `write_jsonl` writes a temp file and swaps it in; `read_checkpoint` drops a half-written last line, including one cut mid-character (`rag/config.py:24-30`, `rag/config.py:45-55`).
- Private eval inputs (`eval/golden/*.jsonl`, `eval/eval_questions.yaml`, `data/ocr_captions.jsonl`) are logical paths resolved under `artifacts/local_inputs/` (`rag/validation/local_inputs.py:12-16`, `rag/validation/local_inputs.py:63-77`).
- `parsing.py` patches two third-party bugs at runtime: a PyMuPDF image-skip bug, only when OCR is on, and a `hwp-hwpx-parser` infinite loop on hyperlinks (`rag/preprocessing/parsing.py:239-240`, `rag/preprocessing/parsing.py:285-307`). The OCR path uses LangChain's `LLMImageBlobParser` (`rag/preprocessing/parsing.py:521-527`).
- Functions over ruff's limits (C901 8, PLR0915 50) must be split, never silenced (`pyproject.toml`, `CLAUDE.md`, section 1.3).
