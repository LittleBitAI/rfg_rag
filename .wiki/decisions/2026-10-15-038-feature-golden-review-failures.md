---
scope: project
severity: preference
triggers: []
domain: ''
title: "golden_pipeline: Items excluded from release without human review are added to the failure log, and the regeneration plan excludes the evidence from the previous plan."
pr: 38
merged: 2026-10-15
branch: "feature/golden-review-failures"
---

# golden_pipeline: Items excluded from release without human review are added to the failure log, and the regeneration plan excludes the evidence from the previous plan.

What. There is no human-led reading and decision step in golden data generation (RRSI). Items that passed validation but are unusable for evaluation are automatically excluded by rule checks and release utility judgments, and the excluded items are entered into the failure log along with a failure code to become preventive rules for the next generation. The regeneration plan excludes the evidence used by previous plans and selects a new batch.

Why. (the PR body has no reason section; the grounds for this decision were not recorded)

Source. PR #38 · `feature/golden-review-failures`
