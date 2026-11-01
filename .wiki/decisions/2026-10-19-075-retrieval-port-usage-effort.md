---
scope: project
severity: preference
triggers: []
domain: ''
title: "usage: Record inference intensity per call (Retrieval branch port 6/6)"
pr: 75
merged: 2026-10-19
branch: "retrieval-port/usage-effort"
---

# usage: Record inference intensity per call (Retrieval branch port 6/6)

What. Record the inference intensity (`reasoning_effort`) sent per call to `artifacts/api_usage.csv`. - Column order: `timestamp, stage, evaluation, subject, model, reasoning_effort, …토큰 · 비용`. `usage_summary` is grouped by model and inference intensity. - CSV files used as old headers are rewritten with new columns filled with blanks and then appended (if appended as is, values will be shifted by one column). …

Why. (the PR body has no reason section; the grounds for this decision were not recorded)

Source. PR #75 · `retrieval-port/usage-effort`
