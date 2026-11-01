---
scope: project
severity: landmine
repeat: rule
triggers: ['데이터셋', '골든', '(?i)golden', '(?i)\.jsonl', '정답', '질문', 'OCR 텍스트', '전사', '(?i)artifacts', '(?i)\bpush', '푸시', '(?i)gitignore', '(?i)data/']
slots: []
sources: ['https://github.com/LittleBitAI/rfg_rag/pull/66', 'commit d7d1682', 'https://github.com/LittleBitAI/rfg_rag/pull/67', 'CLAUDE.md#L45', '.gitignore#L42']
links: []
---

# Real dataset records never enter git; only aggregate measurements do

Rule. Never commit or upload actual dataset records: real questions, answers,
document or evidence text, saved OCR text, or exports that disclose them, in
JSONL or any other format. Keep them under ignored `artifacts/` (restored
inputs live in `artifacts/local_inputs/`). Counts, scores, latency, cost and
reports about those values may be committed, as may code, configs, generic
prompts and synthetic test fixtures. Ignore rules do not untrack a tracked
file: before any push, check `git ls-files` for tracked datasets and flag
them. Never add a `.gitignore` exception for a file holding records.

Why. Golden dev/test splits, evaluation questions and saved OCR captions
were once tracked. PR #66 (d7d1682) had to untrack them, restore them as
private local inputs (`rag/validation/local_inputs.py`) and sanitise tracked
content; PR #67 then restored the aggregate measurements that the clean-up
had over-removed. `CLAUDE.md` section 1.4 records the resulting rule.

What goes wrong. Pushing records discloses private data that deleting later
cannot recall; over-correcting deletes measurements the team needs.
