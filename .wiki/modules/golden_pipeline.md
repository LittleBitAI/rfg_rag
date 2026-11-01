---
scope: project
severity: preference
triggers: []
slots: []
sources: []
links: []
---

# golden_pipeline/ — per-topic golden QA builder for validation, deliberately cut off from rag/

## What it is for

Builds, validates and releases golden question/answer items per topic for evaluation, comparing three generation methods A, B and C (`golden_pipeline/README.md:1-8`). It belongs to pipeline 3, Validation, with the same owner, but is kept apart from `rag/validation/validation.py` on purpose (`CLAUDE.md:105-108`, `golden_pipeline/README.md:4`). Topics are `numeric`, `table`, `condition`, `comparison`, `multi_hop`, `unanswerable`, `false_premise` (`golden_pipeline/README.md:105`), each specified in `golden_pipeline/configs/topics/{topic}.json` (`golden_pipeline/README.md:308-310`).

## Entry points

- One CLI, `python -m golden_pipeline.cli` (`golden_pipeline/cli.py:20-25`), wrapped by `golden_pipeline/golden.cmd` and `golden.command`, which only forward arguments and show `--help` on double-click (`golden_pipeline/golden.cmd:8-14`).
- Commands, in the usual order: `evidence` → `plan` → `run` / `import` → `audit` / `resume` → `release` → `rename` → `split`, plus `report` and the experiment commands `freeze`, `estimate`, `pro-packets`, `review-packets`, `compare` (`golden_pipeline/README.md:43-55`, `golden_pipeline/cli.py:175-269`). `run`, `audit`, `resume` and `release` are paid; the rest make no API calls (`golden_pipeline/README.md:43-55`).

## Modules

| File | Does |
| --- | --- |
| `schema.py`, `state.py` | Exact item schema (`SchemaError` on missing or extra fields) and the state machine `candidate → auto_validated → released`, with `rejected` terminal (`golden_pipeline/README.md:95-142`). |
| `storage.py` | Run/release writes, shared catalog, output path guard (`golden_pipeline/storage.py:23-26`, `golden_pipeline/storage.py:43-47`). |
| `evidence.py` | Read-only adapter over the v12 package: one evidence unit per chunk, `eligible` / `held` judgment (`golden_pipeline/evidence.py:1`, `golden_pipeline/README.md:185-227`). |
| `plan.py` | Fixed distribution plan of bundles per topic so A, B and C see the same inputs (`golden_pipeline/README.md:241-282`). |
| `generation.py`, `validation.py`, `improvement.py`, `adoption.py` | A/B generation and C import; independent validation, difficulty and release; A's self-improvement rounds with failure memory; adoption lower bounds. |
| `split.py` | Document-level dev 30% / test 70% split of releases (`golden_pipeline/split.py:19-29`). |
| `report.py`, `comparison.py`, `experiment.py` | A/B/C comparison reports and the `abc7` experiment (`golden_pipeline/experiment_abc7.md`). |
| `prompts/`, `configs/` | Generator, validator, judge and screen prompts; topic and experiment configs. Each run records their SHA-256 (`golden_pipeline/README.md` table "구성"). |

## Dependencies

- Imports nothing from `rag/` (`golden_pipeline/README.md:10`, `CLAUDE.md:108`); uses the standard library, `kiwipiepy`, `openai` and `python-dotenv` (`golden_pipeline/README.md:11`).
- Reads `data/Golden_Dev396_v12_Team_Package` only, never running its scripts (`golden_pipeline/evidence.py:16`, `golden_pipeline/README.md:187-189`).
- Writes only under `golden_pipeline/outputs/` (ignored, `golden_pipeline/.gitignore:1`), layout in `golden_pipeline/README.md:146-173`.
- Downstream: its released dev split becomes the private golden input `eval/golden/dev.jsonl` read by `rag/validation` (`config.yaml:78`), resolved through `artifacts/local_inputs/` (`rag/validation/local_inputs.py:12-15`). The copy between the two is not automated in code.
- Tests live in `tests/golden/`, so the gate runs them (`CLAUDE.md`, section 4); `tests/golden/conftest.py:1` isolates outputs and builds fake evidence runs.

## What trips a newcomer

- Any write outside `golden_pipeline/outputs` raises `OutputPathError`, including `data/`, `artifacts/` and `eval/` (`golden_pipeline/storage.py:43-47`, `golden_pipeline/README.md:183`, `tests/golden/test_guard.py:17`).
- Existing `run_id`, release `version` and report ids are never overwritten; reuse raises `FileExistsError` (`golden_pipeline/README.md:175`, `golden_pipeline/split.py:29`). Pick a new id instead of deleting.
- Paid commands refuse to start unless model, reasoning effort, prices, max calls and budget are all given; there are no defaults (`golden_pipeline/README.md:84-87`).- The only API entry is `api_client` in `cli.py` (`golden_pipeline/README.md:12`, `golden_pipeline/cli.py:28-45`); generators and validators take the call as an argument, and tests use only fakes. With `--experiment`, the ledger owns retries and the SDK retries are turned off (`golden_pipeline/cli.py:40-41`).
- `storage.PACKAGE` is the `golden_pipeline/` folder (`golden_pipeline/storage.py:23`), while `evidence.PACKAGE` is the v12 data package (`golden_pipeline/evidence.py:16`). Same name, different things.
- Agency names come from the package's own `data/data_list.csv`, matched after NFC normalisation because some source file names are NFD (`golden_pipeline/evidence.py:19`, `golden_pipeline/plan.py:144-149`).
- `plan` replays the evidence adapter and stops if any unit or judgment differs from the pinned run, even when manifests were rehashed (`golden_pipeline/README.md:250-255`). Changing the package means a new evidence run and a new plan.
- Bundle selection is deterministic, so a new plan with the same counts picks the same bundles; use `--skip-plan` to draw fresh evidence (`golden_pipeline/README.md:274-276`).
- There is no human-review hold state; validation ends in pass or reject only (`golden_pipeline/README.md:137`). Gaps are filled by regenerating, not by manual review.
- Windows console output is forced to UTF-8 because cp949 crashed long loops on characters such as `∙` (`golden_pipeline/cli.py:22-24`). Keep `golden.cmd` ASCII (`golden_pipeline/golden.cmd:3`).
