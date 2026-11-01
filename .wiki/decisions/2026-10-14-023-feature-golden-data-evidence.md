---
scope: project
severity: preference
triggers: []
domain: ''
title: "golden_pipeline v11 evidence adapter: package SHA pinning · chunk→element→record→original text unit linking · eligible/held determination"
pr: 23
merged: 2026-10-14
branch: "feature/golden-data-evidence"
---

# golden_pipeline v11 evidence adapter: package SHA pinning · chunk→element→record→original text unit linking · eligible/held determination

What. ③ Add an evidence adapter (`evidence.py`) that only reads the v11 preprocessing package to the `golden_pipeline/` of verification. When starting execution, pin the SHA-256 of the core files of two copies: `data/RFP_Preprocessing_Final_v11_Team` and the folder inside the downloaded archive, and stop if the two copies are different or different from `manifest.json`. Then, link chunk → element → record → original text units by ID, and for each evidence unit …

Why. The evidence for golden questions and answers must be traceable back to the original text, and unverified original text must not be automatically approved as evidence. v11 `manifest.json` does not certify the preservation of the entire original text nor the OCR accuracy (`whole_original_information_preservation_certified: false`). Out of 305,651 non-empty original text units, only 217,866 are PASS. Therefore, for the determination of each original text unit, use the package's own `validation/source_status_merged.csv`, and hold UNVERIFIED. Do not re-verify the package or fix v11's text/numbers (rejected alternatives: trust all v11 chunks, re-verify package, modify original). …

Source. PR #23 · `feature/golden-data-evidence`
