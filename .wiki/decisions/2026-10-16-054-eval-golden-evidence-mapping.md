---
scope: project
severity: preference
triggers: []
domain: ''
title: "validation: Link golden evidence to current document/chunk labels"
pr: 54
merged: 2026-10-16
branch: "eval-golden-evidence-mapping"
---

# validation: Link golden evidence to current document/chunk labels

What. Link golden evidence to the document/chunk IDs of the current preprocessing output. 03 stores the document label and the unique chunk label per evidence or the reason for non-connection in `eval_set.jsonl`, and displays the label quality of the entire dev/test set and a comparison table of 30 pairs.

Why. The v11 chunk ID of the golden set matched the current local parser output in 0/716 dev and 0/1,639 test items. Since the existing evaluation set lacks document/chunk labels to resolve this discrepancy, it was necessary to verify which evidence can be trusted before designing chunk-level evaluation later. Also, `evidence` contains only cited items, while `context` also contains uncited blocks. Since the current dev set consists of 716 evidence items and 1,400 `[E]` blocks, we can pair the two lists in order or use the entire context as a single piece of evidence to label other texts. The previously assumed 573 blocks have been corrected to the actual count in the current file. Parser documents are linked by the SHA-256 of the original file. Folders and single files are read directly from `paths.input`. …

Source. PR #54 · `eval-golden-evidence-mapping`
