---
scope: project
severity: preference
triggers: []
domain: ''
title: "golden_pipeline: Cannot answer · False premise topic — Added to evaluation dataset"
pr: 49
merged: 2026-10-16
branch: "feature/golden-absent-premise"
---

# golden_pipeline: Cannot answer · False premise topic — Added to evaluation dataset

What. Added two topics for automatic verification to golden data. No items were selected by humans. - `unanswerable` — Asks about the attributes of another business document (A) in a document (B). The correct answer is `제공된 문서에서 확인할 수 없습니다.`. - `false_premise` — Inserts an amount, period, count, or date different from the document into the question, and the correct answer corrects it to the value in the document.

Why. (the PR body has no reason section; the grounds for this decision were not recorded)

Source. PR #49 · `feature/golden-absent-premise`
