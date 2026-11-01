---
scope: project
severity: preference
triggers: []
domain: ''
title: "Added top-level rules (CLAUDE.md·AGENTS.md) and ruff complexity limits"
pr: 1
merged: 2026-10-12
branch: "korean-top-level-guidelines"
---

# Added top-level rules (CLAUDE.md·AGENTS.md) and ruff complexity limits

What. Added `CLAUDE.md` and `AGENTS.md` with the same content for coding agents. Since it is a document read by agents, it is written in English and structured with numbered sections and tables. 1. Priority rules: No unrequested implementation (including unnecessary validation, though tests themselves are allowed), readable code, no complex functions (based on ruff) 2. Dependencies: Only packages directly imported by the code or required by rules (pytest, ruff) are placed in `requirements.txt` 3. …

Why. The previous repository (project-codeit-mid) was abandoned because the code became too complex. Since rules left to judgment are easily broken, complexity is measured by a linter.

Source. PR #1 · `korean-top-level-guidelines`
