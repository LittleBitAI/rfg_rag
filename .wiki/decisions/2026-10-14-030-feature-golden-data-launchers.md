---
scope: project
severity: preference
triggers: []
domain: ''
title: "golden_pipeline executor · CLI: run · import · audit · resume · release flow, B · C verification continuation, A · B · C comparison report"
pr: 30
merged: 2026-10-14
branch: "feature/golden-data-launchers"
---

# golden_pipeline executor · CLI: run · import · audit · resume · release flow, B · C verification continuation, A · B · C comparison report

What. ③ Attach one CLI and two executors, B · C verification continuation, and A · B · C comparison report to `golden_pipeline/` of the verification. `golden_pipeline\golden.cmd` (Windows) and `golden_pipeline/golden.command` (macOS) only pass all received arguments to `python -m golden_pipeline.cli` and do not run the notebook or question screen server. …

Why. Until now, each step had to be called directly as a Python function, and configuration files for paid runs had to be written by hand. To ensure team members run the same flow with the same command, we provide one CLI and two executors that only call that CLI (rejected: logic kept separately for each executor). Paid calls must not be made before the model, maximum call count, and budget are set. Therefore, paid commands must receive all these values as flags to start, and no default values are provided. The verification in #26 ended by leaving the remaining candidates as `pending` when reaching the call limit or budget, and the same run could not be verified again (deferred in README as "attached at the executor stage"). …

Source. PR #30 · `feature/golden-data-launchers`
