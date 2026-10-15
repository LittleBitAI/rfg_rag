---
scope: project
severity: preference
triggers: []
domain: ''
title: "golden_pipeline candidate generation: topic specification · distribution plan · A/B generation · C retrieval"
pr: 24
merged: 2026-10-14
branch: "feature/golden-data-generation"
---

# golden_pipeline candidate generation: topic specification · distribution plan · A/B generation · C retrieval

What. ③ Add topic-specific candidate generation to the `golden_pipeline/` of verification. Select topic-specific evidence bundles only from evidence units determined as `eligible` by the evidence adapter (#23), fix them into a distribution plan file, and save candidates where A (initial generation), B (fixed prompt), and C (web result retrieval) undergo the same plan, same output contract, and same inspection. All outputs are in the `candidate` state, and this step does not approve anything. …

Why. To compare the three generation methods, the source version, target distribution, evidence bundle, output contract, and post-inspection must be identical. Therefore, one plan file is fixed with SHA-256 for A, B, and C to read together, and all three methods are made to pass through one inspection function (`_candidate`) and `write_run` (rejection: separate inspection for each method). Even if `numeric` is selected, if the explanatory answer remains as a candidate, topic classification is meaningless. Require an output `structure` for each topic and verify that the value is exactly as written in the evidence. The web environment (C) does not guarantee or provide the model name, tokens, or cost. Leave unobserved values as `unobserved` and do not assume it is an API model …

Source. PR #24 · `feature/golden-data-generation`
