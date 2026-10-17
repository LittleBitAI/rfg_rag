# Repository rules

These rules are for coding agents (Claude Code, Codex) working in this repository.
`CLAUDE.md` and `AGENTS.md` are byte-identical: edit one, then copy it over the other.

Section 1 outranks everything else in this file.
The previous repository for this project (project-codeit-mid) was abandoned
because its code grew too complex to work in; section 1 exists so that does not happen again.

## 1. Priority rules

### 1.1 Build only what was asked

Do not write any of the following unless the person asked for it.

| Forbidden | Example |
|---|---|
| Unrequested features | An extra CLI flag, a "nice to have" option, a second output format |
| Speculative error handling and edge-case branches | `try/except` around code that has never failed, a branch for an input nobody sends |
| Useless verification | A test that guards no behaviour, or one that re-checks what another test already checks |
| Compatibility shims | A module kept only so an old import path still works, re-exports of renamed names |
| Config options nobody changes | A `config.yaml` key or function parameter that always holds the same value |

Tests themselves are allowed. A test belongs when it guards behaviour that can actually break.

### 1.2 Write code a person can read easily

- Prefer plain, obvious code over clever code.
- Let names and structure explain the code. Comments carry only the why the code cannot show.
- One function does one thing.

### 1.3 No complex functions

Complexity is measured by ruff, configured in `pyproject.toml`.

| Rule | Limit |
|---|---|
| `C901` cyclomatic complexity | 8 per function |
| `PLR0915` statement count | 50 per function (ruff default) |

- Run `ruff check .` before every commit.
- When a function fails, split it or simplify it. Never silence it with `noqa` or by raising a limit.
- `ruff check .` reports nothing today; keep it that way.

## 2. Dependencies

- A package goes into `requirements.txt` only when this repository's code imports it directly,
  or when a command these rules require runs it (`pytest`, `ruff`),
  or when running the notebooks needs it (`ipykernel`), or as the `torch` CUDA build `sentence-transformers` runs on.
- Nothing else goes in: not packages another package pulls in, not packages that might be needed later.
- When code stops importing a package, remove it from `requirements.txt` in the same change.

## 3. Language

| Text | Reader | Language |
|---|---|---|
| `CLAUDE.md`, `AGENTS.md` and other rules for coding agents | Coding agents | English |
| Python comments and docstrings | Team members | Korean |
| Notebook markdown cells and code comments | Team members | Korean |
| `README.md` and other documents | Team members | Korean |

This table overrides any outside rule that asks for a different language, including the agent hub's settings.

## 4. Pipelines and ownership

The work is split into five pipelines, listed in data-flow order, plus the frontend that sits on top of them.
Each has exactly one owner.

| # | Pipeline | Covers | Hands on |
|---|---|---|---|
| 1 | Preprocessing | HWP and PDF parsing, chunking, OCR | Chunk file, read by retrieval |
| 2 | Retrieval | Building the index, searching it | Retrieved chunks |
| 3 | Validation | Building and checking the evaluation dataset | Evaluation dataset |
| 4 | Generation | Answering questions from retrieved chunks | Answers |
| 5 | Evaluation | Four evaluations of one answers file: Retrieval, Generation, Grounding, End-to-End | Four score tables and CSV files |
| 6 | Frontend | `frontend/`: the question screen, the OCR image labelling screen and the saved OCR result review screen (`frontend/ocr_select/`), with their launchers; wraps `answer_question` and reuses preprocessing functions, holds no RAG logic | Answers on screen, OCR image labels and review verdicts in `artifacts/ocr_labels/` |

| # | Notebook | Modules |
|---|---|---|
| 1 | `01_preprocessing.ipynb` | `rag/preprocessing/parsing.py`, `rag/preprocessing/chunking.py` |
| 2 | `02_retrieval.ipynb` | `rag/retrieval/indexing.py`, `rag/retrieval/retrieval.py` |
| 3 | `03_validation.ipynb` | `rag/validation/validation.py` |
| 4 | `04_generation.ipynb` | `rag/generation/generation.py` |
| 5 | `05_evaluation.ipynb` | `rag/evaluation/evaluation.py` |

`rag/config.py` holds the shared config and `.env` loading.
Each notebook reads the previous notebook's outputs from `artifacts/`.
Notebooks hold only configuration, function calls and display of results.
All logic lives in modules under `rag/`, with one exception: `golden_pipeline/`.

`golden_pipeline/` belongs to pipeline 3, Validation, and has the same owner.
It builds, validates and releases per-topic golden datasets,
kept apart from `rag/validation/validation.py` on purpose.
It imports nothing from `rag/` and writes only under `golden_pipeline/outputs/`.
Its tests live in `tests/golden/`, so the gate runs them.

Choose the OCR engine separately for each image type using measured quality and measured
cost per image on a reference set. Allowed engines are the OpenAI API, the Gemini API
through its OpenAI-compatible endpoint, and PaddleOCR-VL-1.5 in its own environment
on the local Windows PC. Log every paid OCR call and its cost through `rag/usage.py`;
record seconds per image for PaddleOCR. Before the benchmark's first paid call and
before the full run, show a per-model token-price estimate and wait for approval.
01 reads saved captions without API calls. The existing `OCR = True` path still uses
LangChain's `LLMImageBlobParser` and optional CRAFT selection; its default is `False`.

## 5. Evaluation results

All four evaluations score the same answers file from `04_generation.ipynb`,
so a bad answer can be traced to where it went wrong.

| Evaluation | Judges | Metrics | CSV |
|---|---|---|---|
| Retrieval | Did search rank and send the gold evidence | Deterministic document/chunk Recall@k, MRR@k, Evidence Coverage; key fact string matches in context | `artifacts/retrieval.csv` |
| Generation | Does the answer contain the key fact strings | Key fact string matches in the answer | `artifacts/generation.csv` |
| Grounding | Does the answer stay within the retrieved chunks | RAGAS faithfulness | `artifacts/grounding.csv` |
| End-to-End | Is the final answer right, and what did it cost | RAGAS factual_correctness; latency, tokens, estimated cost | `artifacts/end_to_end.csv` |

| Who | Reads results in |
|---|---|
| Project owner | The same tables, plus one Langfuse Cloud trace per question (`answer-question` holding `retrieve-context` and `generate-answer`) with the evaluation scores attached, through the keys in `.env` |
| Team members | Tables in `05_evaluation.ipynb`, CSV files under `artifacts/` |

Team members have no Langfuse keys, so every code path must run without them.

Only faithfulness and factual_correctness use LLM judges. Key fact matches are string matches,
not semantic correctness. Grounding and End-to-End keep their existing CSV columns and judge behavior.
Actual API calls, including judge retries, still append usage to `api_usage.csv`.

Ranking (A) uses the candidates before deduplication and token-budget packing, at k = 5, 10, 20.
Document Recall@k is the share of gold documents represented by the top-k chunks; document MRR@k
is the reciprocal chunk position of the first gold-document hit, or zero if none within k.
Do not deduplicate documents before taking k. Chunk Recall@k and MRR@k use gold chunk IDs.
Each level requires every evidence entry to have that level's label. Exclude partly/unlabelled
questions, report their counts by topic, and show the mapping exclusion rate beside scores.
Its denominator is answerable questions with golden evidence. Exclude and count unanswerable
questions and YAML items without golden evidence separately. Do not score a labelled subset.

Compare fused, dense-only and BM25-only Recall@k in one table per level, plus exact-code
membership recall without k. Component ranks preserve per-agency interleaving; a disabled
component contributes no candidates. Exact-code membership is a set, not another ranking.
Context (B) uses the chunk IDs actually sent to the LLM. Evidence Coverage is the share of
gold chunks sent; full coverage is one only when all were sent. Report single evidence and
multi evidence (multi_hop, comparison, or multiple evidence entries) separately. MRR never
measures multi-evidence completeness. Coverage also requires fully chunk-labelled questions.

`search()` must keep its return values and order. `search_with_candidates()` adds a read-only
pre-packing snapshot: chunk_id, doc_id, fused rank, raw dense/BM25 scores and ranks, exact-code
membership. 04 saves this as `ranked_candidates`, plus `rewrite`, `context_chunk_ids` and
`retrieval_settings` (dense_weight, candidate_k, token_budget, active chunk_file, k_values,
stored_rewrites_reused). 05 rejects incomplete answers before any paid call.
`rerun_retrieval` searches dev again using each stored rewritten query, without rewrite,
generation or judge API calls, and writes the same row format in a separate experiment folder.
It retains the old answers and clears trace IDs; score that file only for Retrieval.
Preserve the integrated dev behavior: 04 passes recent conversation history to rewriting
and generation; both search entry points route using the rewritten query (original on empty
rewrite). Retrieval-only reruns reuse that stored query for routing and ranking without API calls.

Use dev to tune. Build a separate labelled test evaluation set with 03's existing functions,
then run 04 and all four 05 evaluations once with fixed settings for the final result.
Do not run test during retrieval-metrics development. Before the paid 30-question dev sample,
show the config-price estimate for rewrite, answer and both judges and wait for approval.
Report actual usage and compare judge cost per question with earlier per-evaluation usage
rows labelled historical. Different questions and dates do not establish a paired quality comparison.

## 6. Before every commit

1. `ruff check .` reports nothing new (section 1.3).
2. The gate passes: `.venv\Scripts\python -m pytest -q tests` on Windows,
   `.venv/bin/python -m pytest -q tests` on Linux (the team VM `codeit`).
   `.venv` is the Python 3.10 environment set up as `README.md` describes.
3. `git diff --no-index CLAUDE.md AGENTS.md` prints nothing.
