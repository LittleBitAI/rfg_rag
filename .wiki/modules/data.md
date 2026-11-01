---
scope: project
severity: preference
triggers: []
slots: []
sources: []
links: []
---

# data/ — local raw inputs, ignored by git except four aggregate OCR benchmark files

## What it is for

`data/` holds the inputs the pipelines start from: the RFP documents, the file-name → agency list, optional preprocessing packages handed over by the preprocessing owner, and the saved OCR captions. Almost all of it is private dataset material and stays out of git (`.gitignore:45`). The only tracked files are four aggregate OCR benchmark records under `data/ocr_benchmark/` (`.gitignore:46-51`), which the dataset-privacy rule allows because they hold counts, scores and costs, not records (`CLAUDE.md`, section 1.4).

## What lives here

| Path | Tracked | Role |
| --- | --- | --- |
| `data/rfp.zip` (or a folder) | no | The RFP originals; `paths.input` in `config.yaml:7`. Nested ZIPs are unpacked recursively (`rag/preprocessing/parsing.py:73-90`). |
| `data/data_list.csv` | no | File name → agency (`파일명`, `발주기관`); `paths.org_csv` in `config.yaml:6`, marked required. Not generated; it comes from the owner (`README.md`, "3. 데이터 준비"). |
| `data/ocr_captions.jsonl` | no | Saved OCR text per image location, produced by the OCR benchmark's full run; `paths.ocr_captions` in `config.yaml:8`. |
| `data/RFP_Preprocessing_Final_v11_Team`, `data/Golden_Dev396_v12_Team_Package` | no | Preprocessing packages to reuse instead of parsing (`docs/preprocessing_package.md:8-13`). |
| `data/ocr_labels/` | no | Team OCR label batches (`ocr_labels_batch1..5.jsonl`), the benchmark's label sources (`data/ocr_benchmark/preparation.json:6`, `docs/ocr_benchmark.md:14`). |
| `data/ocr_benchmark/summary.json`, `full_run_plan.json`, `full_run_summary.json`, `preparation.json` | yes | Aggregate benchmark results, run plan with approval, actual usage, preparation hashes (`docs/ocr_benchmark.md:201-204`). |

## Who reads it

- `01_preprocessing.ipynb` parses `paths.input` unless `PREPROCESSED` names a package folder under `data/` (`01_preprocessing.ipynb:33`).
- Retrieval's agency router reads `paths.org_csv` when an index is opened (`rag/retrieval/retrieval.py:174`), so the frontend and 04 also need it.
- `03_validation.ipynb` points `package_dir` at the v11 package (`03_validation.ipynb:30`).
- `golden_pipeline/evidence.py` reads only the v12 package (`golden_pipeline/evidence.py:16`), and pins its manifest, chunks, docs and the package's own `data/data_list.csv` by SHA-256 (`golden_pipeline/evidence.py:17-20`).
- `frontend/ocr_select/extract.py` pulls images from `paths.input` (`frontend/ocr_select/extract.py:139`); `frontend/ocr_select/review.py` reads the saved captions (`frontend/ocr_select/review.py:17`).
- Nothing in code reads `data/ocr_benchmark/*.json`; they are records for people and reports.

## What trips a newcomer

- `data/ocr_captions.jsonl` is a logical name, not where the file is read from. `local_input` maps it to `artifacts/local_inputs/ocr_captions.jsonl` (`rag/validation/local_inputs.py:16`, `rag/validation/local_inputs.py:73`) and every reader goes through it (`rag/preprocessing/ocr_captions.py:17`, `frontend/ocr_select/review.py:33`). `docs/ocr.md:17` says the same.
- When the local copy is missing, `input_bytes` falls back to `git show` of a fixed older commit, then fails with a message to restore an owner-provided bundle via `python -m rag.validation.local_inputs --from-directory PATH` (`rag/validation/local_inputs.py:11`, `rag/validation/local_inputs.py:26-30`). It never fetches over the network.
- The tracked benchmark JSON are historical aggregates restored after a cleanup, not remeasured (`data/ocr_benchmark/summary.json:2`). Do not treat them as outputs of the current code.
- `golden_pipeline` and the RAG pipeline read different agency lists: the package's inner `data/data_list.csv` (`golden_pipeline/evidence.py:19`) versus the repository's `data/data_list.csv` (`config.yaml:6`).
- A new file here stays untracked unless `.gitignore` whitelists it (`.gitignore:45-51`); adding a whitelist entry for anything holding real questions, answers, document text or OCR text breaks the privacy rule.
- `data/` is copied by hand to teammates and the VM (`README.md`, "3. 데이터 준비"); a fresh clone has none of it, and anything that opens the index (04, the frontend) fails without `data/data_list.csv` (`rag/retrieval/retrieval.py:174`).
