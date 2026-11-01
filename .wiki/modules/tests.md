---
scope: project
severity: preference
triggers: []
slots: []
sources: []
links: []
---

# tests/ — the pytest gate for rag/, frontend/, tools/ and golden_pipeline/, offline and without Langfuse keys

## What it is for

`tests/` is the repository gate: `.venv\Scripts\python -m pytest -q tests` on Windows, `.venv/bin/python -m pytest -q tests` on Linux, before every commit (`CLAUDE.md`, section 6; `.wiki/adapter.toml` `gate_cmd`). It holds 31 top-level files and 15 under `tests/golden/`, about 448 test functions. Tests use fakes and synthetic fixtures and make no paid calls.

## Layout

| Path | Covers |
| --- | --- |
| `tests/conftest.py` | Autouse fixtures for every test: redirects the usage CSV to a temp dir (`tests/conftest.py:7-9`) and blanks the Langfuse keys, disabling tracing (`tests/conftest.py:12-21`). |
| `tests/test_smoke.py` | Imports every module under `rag/` (`tests/test_smoke.py:10-16`). |
| `tests/test_retrieval.py`, `test_indexing.py`, `test_index_migration.py`, `test_rewrite.py`, `test_quantity_filter.py`, `test_retrieval_benchmark*.py` | Pipeline 2: codes, token budget, dedup, routing (`tests/test_retrieval.py:1`); atomic index rebuilds (`tests/test_indexing.py:54-102`); the offline embedding benchmark with synthetic records (`tests/test_retrieval_benchmark_artifacts.py:1`). |
| `tests/test_eval_items.py`, `test_evidence_mapping.py`, `test_local_inputs.py`, `test_v11_package.py` | Pipelines 1 and 3: eval items, evidence labelling, private-input restore (`tests/test_local_inputs.py:39-66`), package loading (`tests/test_v11_package.py:16-72`). |
| `tests/test_answer_records.py`, `test_ir_metrics.py`, `test_key_fact_matching.py`, `test_local_judge.py` | Pipeline 5: answer-file contract checked before paid calls (`tests/test_answer_records.py:36`), metrics, the local judge. |
| `tests/test_checkpoints.py` | Resume after interruption for parsing, embedding, answers and judge scores (`tests/test_checkpoints.py:1`). |
| `tests/test_usage.py` | Cost maths, concurrent CSV writes, Langfuse off without keys (`tests/test_usage.py:31-60`). |
| `tests/test_notebook_settings.py` | Notebook settings reach the code, and no notebook has saved outputs (`tests/test_notebook_settings.py:15-21`). |
| `tests/test_ocr_*.py`, `test_craft_detector.py` | OCR captions, selection, benchmark, labelling and review screens. |
| `tests/test_server.py` | Chat API trims history and returns answer and sources (`tests/test_server.py:5`). |
| `tests/test_paddle_ocr.py` | `tools/paddle_ocr.py` with stub `paddle` modules (`tests/test_paddle_ocr.py:18-20`). |
| `tests/golden/` | `golden_pipeline/`; its `conftest.py` isolates outputs and builds a valid sample item and a fake evidence run (`tests/golden/conftest.py:1`). |
| `tests/index_migration_worker.py` | Helper run as a subprocess by the migration test, not a test file (`tests/index_migration_worker.py:9-14`). |

## Dependencies

- Needs the `.venv` with `requirements.txt` installed; a missing module fails the smoke test rather than skipping (`tests/test_smoke.py:13`).
- Imports rely on the repository root being on `sys.path`, which `python -m pytest` from the root provides; tests also import sibling test modules directly, for example `from test_indexing import snapshot` (`tests/test_index_migration.py:8`).

## What trips a newcomer

- Never reach the real `.env` keys. Deleting the Langfuse variables is not enough because `load_dotenv` would bring the real keys back; the fixture sets them to empty strings (`tests/conftest.py:13-21`, `rag/config.py:17-20`).
- `tests/test_index_migration.py` exports `rag/` from a fixed older commit with `git archive` (`tests/test_index_migration.py:12-18`) and runs both revisions in subprocesses with a 120-second timeout (`tests/test_index_migration.py:21-24`). A shallow clone without that commit fails this test.
- The notebook test fails on any saved output or execution count, including in `preprocessing/*.ipynb` (`tests/test_notebook_settings.py:15-21`). Clear outputs before committing a notebook.
- There are no `skip` or `xfail` markers in the suite; a test that cannot run is a failure.
- Fixtures must be synthetic. Real dataset records are never committed (`CLAUDE.md`, section 1.4); a local selection fixture, `tests/fixtures/craft_selection50.json`, is ignored on purpose (`.gitignore:44`).
