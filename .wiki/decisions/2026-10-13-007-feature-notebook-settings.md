---
scope: project
severity: preference
triggers: []
domain: ''
title: "Added cells to adjust model, reasoning effort, chunking, and search ratio per notebook"
pr: 7
merged: 2026-10-13
branch: "feature/notebook-settings"
---

# Added cells to adjust model, reasoning effort, chunking, and search ratio per notebook

What. | Notebook | Variable in configuration cell | Actual application location | |---|---|---| | 01 Preprocessing | OCR, OCR_MODEL, OCR_REASONING_EFFORT, OCR_MAX_TOKENS, CHUNK_SIZE | OCR parser creation and chunk splitting | | 02 Search | REWRITE_MODEL, REWRITE_REASONING_EFFORT, REWRITE_MAX_TOKENS, DENSE_WEIGHT | Search examples and rewrite/search settings read by 04 | | …

Why. Although question rewrite was implemented in PR #6, modifying the model, reasoning_effort, chunking size, and search ratio required editing config.yaml. There were no adjustment cells within the requested 01, 02, 04, and 05 notebooks, and the OCR model, token limit, and reasoning effort were still hardcoded in the Python code. This PR allows each pipeline owner to adjust values in their notebook's configuration cell. Default values are read from config.yaml, and values changed by the user in the cell are applied to the memory settings for that execution. It does not automatically overwrite the common config.yaml file. The rewrite and search ratio changed in 02 must also be applied to the actual answer generation in 04. …

Source. PR #7 · `feature/notebook-settings`
