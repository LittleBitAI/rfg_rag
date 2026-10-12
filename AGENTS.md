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

The work is split into five pipelines, listed in data-flow order. Each pipeline has exactly one owner.

| # | Pipeline | Covers | Hands on |
|---|---|---|---|
| 1 | Preprocessing | HWP and PDF parsing, chunking, OCR | Chunk file, read by retrieval |
| 2 | Retrieval | Building the index, searching it | Retrieved chunks |
| 3 | Validation | Building and checking the evaluation dataset | Evaluation dataset |
| 4 | Generation | Answering questions from retrieved chunks | Answers |
| 5 | Evaluation | Four evaluations of one answers file: Retrieval, Generation, Grounding, End-to-End | Four score tables and CSV files |

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
All logic lives in modules under `rag/`.

Images in documents become text only through the OpenAI API (LangChain's `LLMImageBlobParser`),
and only when `OCR = True` in `01_preprocessing.ipynb`; it is `False` by default.
Do not add a local OCR model or a local VLM such as Qwen2.5-VL; the team decided against running one.

## 5. Evaluation results

All four evaluations score the same answers file from `04_generation.ipynb`,
so a bad answer can be traced to where it went wrong.

| Evaluation | Judges | Metrics | CSV |
|---|---|---|---|
| Retrieval | Did search bring back what the answer needs | RAGAS context_precision, context_recall; key facts in retrieved chunks | `artifacts/retrieval.csv` |
| Generation | Does the answer address the question and hold the key facts | RAGAS answer_relevancy; key facts in the answer | `artifacts/generation.csv` |
| Grounding | Does the answer stay within the retrieved chunks | RAGAS faithfulness | `artifacts/grounding.csv` |
| End-to-End | Is the final answer right, and what did it cost | RAGAS factual_correctness; latency, tokens, estimated cost | `artifacts/end_to_end.csv` |

| Who | Reads results in |
|---|---|
| Project owner | The same tables, plus one Langfuse Cloud trace per question (`answer-question` holding `retrieve-context` and `generate-answer`) with the evaluation scores attached, through the keys in `.env` |
| Team members | Tables in `05_evaluation.ipynb`, CSV files under `artifacts/` |

Team members have no Langfuse keys, so every code path must run without them.

## 6. Before every commit

1. `ruff check .` reports nothing new (section 1.3).
2. The gate passes: `.venv\Scripts\python -m pytest -q tests` on Windows,
   `.venv/bin/python -m pytest -q tests` on Linux (the team VM `codeit`).
   `.venv` is the Python 3.10 environment set up as `README.md` describes.
3. `git diff --no-index CLAUDE.md AGENTS.md` prints nothing.
