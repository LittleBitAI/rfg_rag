---
scope: project
severity: preference
triggers: []
domain: ''
title: "golden_pipeline A pilot: reasoning_effort mandatory setting, actual loop for five topics, fix for boundary bugs"
pr: 34
merged: 2026-10-14
branch: "feature/golden-a-pilot"
---

# golden_pipeline A pilot: reasoning_effort mandatory setting, actual loop for five topics, fix for boundary bugs

What. I have added `reasoning_effort` to the generator/validator settings as a mandatory field without a default value (for each role in run settings and loop settings, CLI `--reasoning-effort` · `--validator-reasoning-effort`). The value is passed as-is to the OpenAI call and remains in the `run_config` of the `start.json` · run manifest · `validation.json`. If the flag is missing, it stops before opening the API client. …

Why. (the PR body has no reason section; the grounds for this decision were not recorded)

Source. PR #34 · `feature/golden-a-pilot`
