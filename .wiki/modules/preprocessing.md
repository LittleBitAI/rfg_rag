---
scope: project
severity: preference
triggers: []
slots: []
sources: []
links: []
---

# preprocessing/ — the preprocessing owner's EDA, chunking-comparison and change-history notebooks; a record, not part of the pipeline

## What it is for

Three notebooks that document how the preprocessing packages (v11, v12, v13) were made and checked (`README.md:310`). They are history and evidence for the team's preprocessing reports, not a step of the running pipeline. The pipeline's preprocessing step is `01_preprocessing.ipynb` at the repository root with `rag/preprocessing/parsing.py` and `chunking.py` (`CLAUDE.md:94`, `README.md:165`).

| Notebook | Covers | Runs with |
| --- | --- | --- |
| `preprocessing/01_RFP 전처리+EDA.ipynb` | Raw-document EDA, parsing, cleaning, structuring and quality checks; final EDA on v13 (`preprocessing/01_RFP 전처리+EDA.ipynb:58`) | Nothing external. By default it only redisplays results saved in its own notebook metadata, `rfp_saved_eda` (`preprocessing/01_RFP 전처리+EDA.ipynb:101-105`, `preprocessing/01_RFP 전처리+EDA.ipynb:5179`); the original computation stays as commented-out code. |
| `preprocessing/02_RFP_청킹_비교실험.ipynb` | Length-based versus structure-based chunking on the same input | `RFP_EXPERIMENT_ROOT` is required (`preprocessing/02_RFP_청킹_비교실험.ipynb:23-25`); `RFP_V12_DIR`, `RFP_TEAM_SRC`, `RFP_NATIVE_ELEMENTS` and `RFP_CHUNK_OUTPUT_DIR` also apply (`preprocessing/02_RFP_청킹_비교실험.ipynb:7`). Output defaults to `artifacts/chunking_review_outputs` (`preprocessing/02_RFP_청킹_비교실험.ipynb:29`). |
| `preprocessing/03_RFP_전처리_실험및개선이력.ipynb` | Change ledgers and replays of earlier cleaning, table repair and record splitting | `RFP_EXTERNAL_ROOT` pointing at an external bundle with `project/`, `history/`, `archives/`, `packages/` (`preprocessing/03_RFP_전처리_실험및개선이력.ipynb:7`, `preprocessing/03_RFP_전처리_실험및개선이력.ipynb:34`). New output goes to `artifacts/preprocessing_experiments` (`preprocessing/03_RFP_전처리_실험및개선이력.ipynb:34`). |

## Dependencies

- Nothing in `rag/`, `frontend/`, `golden_pipeline/`, `tests/` or the root notebooks reads these notebooks.
- Notebook 03 imports legacy modules (`preprocess`, `structure_source`, `repair_confirmed_tables`) from the external bundle by inserting its `original_sources/legacy/src` into `sys.path` (`preprocessing/03_RFP_전처리_실험및개선이력.ipynb:34`, `preprocessing/03_RFP_전처리_실험및개선이력.ipynb:52`, `preprocessing/03_RFP_전처리_실험및개선이력.ipynb:95`). Those modules are not in this repository.
- Notebook 02 needs the external team chunking source at a recorded SHA and extra packages (tiktoken, psycopg, pgvector and others) that are not in `requirements.txt` (`preprocessing/02_RFP_청킹_비교실험.ipynb:7`).
- Notebook 03 finds the repository root by `pyproject.toml`, `rag/` and `preprocessing/` (`preprocessing/03_RFP_전처리_실험및개선이력.ipynb:34`), so moving or renaming this folder breaks it.

## What trips a newcomer

- Three things share the word "preprocessing": this folder, `rag/preprocessing/` (the code) and `01_preprocessing.ipynb` (the pipeline notebook). Changes to the pipeline go to the latter two.
- Notebook 01's final EDA describes v13, while the team's default data is v12 Team; its numbers are not v12 results (`preprocessing/01_RFP 전처리+EDA.ipynb:58`, `preprocessing/01_RFP 전처리+EDA.ipynb:4888`).
- Saved tables and PASS counts are outputs of past runs, with private paths masked; the notebooks were not rerun for publication (`preprocessing/03_RFP_전처리_실험및개선이력.ipynb:7`). `${RFP_EXTERNAL_ROOT}` in old outputs is a masking substitution, and recorded SHA-256 values are of the unmasked originals (`preprocessing/03_RFP_전처리_실험및개선이력.ipynb:7`).
- Notebook 02's chunking functions are written for the experiment and are not the team's chunking module (`preprocessing/02_RFP_청킹_비교실험.ipynb:7`). Its samples are a chosen document, not a random sample, so its results do not generalise to all documents (`preprocessing/02_RFP_청킹_비교실험.ipynb:7`).
- Notebooks hold no outputs in git cells (outputs are kept in metadata in 01); never add real document or OCR text to their outputs when re-saving (`CLAUDE.md`, section 1.4). Configuration files with personal paths must not be committed (`preprocessing/03_RFP_전처리_실험및개선이력.ipynb:7`).
