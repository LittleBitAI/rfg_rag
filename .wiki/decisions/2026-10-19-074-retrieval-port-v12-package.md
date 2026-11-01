---
scope: project
severity: preference
triggers: []
domain: ''
title: "preprocessing: Reading v12 search corpus and image description chunks (Retrieval branch port 5/6)"
pr: 74
merged: 2026-10-19
branch: "retrieval-port/v12-package"
---

# preprocessing: Reading v12 search corpus and image description chunks (Retrieval branch port 5/6)

What. Augmented Golden dev 396 package (v12) search corpus is read directly from 01. - `load_package`: The folder (`data/Golden_Dev396_v12_Team_Package/corpus`) containing `chunks.jsonl` · `docs.jsonl` is read as is, and the `final_chunks.jsonl` package is moved to the existing `load_v11_package`. - Next to `ocr_captions. …

Why. (the PR body has no reason section; the grounds for this decision were not recorded)

Source. PR #74 · `retrieval-port/v12-package`
