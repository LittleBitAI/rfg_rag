---
scope: project
severity: preference
triggers: []
domain: ''
title: "pipeline: parsing · embedding · answering · judgment score continuation (Retrieval branch porting 4/6)"
pr: 73
merged: 2026-10-19
branch: "retrieval-port/checkpoints"
---

# pipeline: parsing · embedding · answering · judgment score continuation (Retrieval branch porting 4/6)

What. If it stops and runs again, it continues. - 01 parsing: saved to `artifacts/checkpoints/parsed/` for each document (file SHA · parsing · OCR settings are keys) — OCR costs are not incurred again. - 02 embedding: saved to `artifacts/checkpoints/embedding/` for every 1,000 chunk bundle, only changed chunk bundles are recalculated. - 04 answering: for each question …

Why. (the PR body has no reason section; the grounds for this decision were not recorded)

Source. PR #73 · `retrieval-port/checkpoints`
