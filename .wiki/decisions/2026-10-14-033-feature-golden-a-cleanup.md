---
scope: project
severity: preference
triggers: []
domain: ''
title: "golden_pipeline summary: one failure record exit, one limit rule, folding overlapping tests"
pr: 33
merged: 2026-10-14
branch: "feature/golden-a-cleanup"
---

# golden_pipeline summary: one failure record exit, one limit rule, folding overlapping tests

What. Before the paid pilot, we organize `golden_pipeline/` and `tests/golden/`. The behavior described in the documentation remains the same, and branches added during reviews and overlapping tests have been folded into a single rule. There are no API calls, and there is no path where items currently held · rejected change to auto_validated · released.

Why. All functions are within the ruff C901 limit (8) (maximum 7), but after 7~8 review rounds, small helpers and overlapping tests have accumulated. We will organize the code first so that the pilot runs the remaining code (rejected: pilot first, both in one PR). Failure records have been blocked by `write_memory` receiving items from the outside and performing three checks (format · rule · reference). Since all items are determined at the `rejected.jsonl` line, if we do not receive items and create them only at that line, there will be nothing to block.

Source. PR #33 · `feature/golden-a-cleanup`
