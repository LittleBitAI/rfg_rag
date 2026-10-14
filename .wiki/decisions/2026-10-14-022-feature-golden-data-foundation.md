---
scope: project
severity: preference
triggers: []
domain: ''
title: "golden_pipeline based: golden item schema · state model · topic-specific storage protocol · output path protection"
pr: 22
merged: 2026-10-14
branch: "feature/golden-data-foundation"
---

# golden_pipeline based: golden item schema · state model · topic-specific storage protocol · output path protection

What. ③ Add the foundation for the new package `golden_pipeline/` belonging to the verification pipeline. It only contains the item schema, state model, topic-specific storage protocol, shared catalog, and output path protection for golden question/answer data; generation, verification, v11 reading, and executors are attached in later stages. `CLAUDE.md` · `AGENTS.md` Section 4 noted this package as the only exception outside `rag/` (③ verification affiliation, same person in charge).

Why. To create and verify golden data by topic (number, table, condition, comparison, multiple evidence) using various methods (A, B, C) for release, it must first be fixed what the items contain, where they are used, and what states they go through. If you build the generator first without this protocol, the format will change with every run, and the same question will be included in two topics, contaminating the evaluation. Do not expand the existing ③ verification (`rag/validation/validation.py`) but keep it separate. `rag/` helpers (e.g., `rag/usage.py`) are not imported because they are used in `artifacts/`. To avoid putting the new package in `requirements.txt`, schema verification is done with standard libraries (no jsonschema/pydantic used). …

Source. PR #22 · `feature/golden-data-foundation`
