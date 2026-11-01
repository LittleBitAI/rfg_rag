---
scope: project
severity: preference
triggers: []
domain: ''
title: "validation: evaluation dataset as golden dev split — year-end tax settlement · chunk QA removal"
pr: 48
merged: 2026-10-15
branch: "feature/eval-golden-input"
---

# validation: evaluation dataset as golden dev split — year-end tax settlement · chunk QA removal

What. 03 validation now creates `artifacts/eval_set.jsonl` using only the golden dev split (`eval/golden/dev.jsonl`, 30 documents, 396 questions) and RFP questions from `eval/eval_questions.yaml`. Year-end tax settlement questions and QA created from chunks were removed from the evaluation input. 03 no longer calls the OpenAI API.

Why. Reason for reading only dev: The golden release is divided by document into dev 30% · test 70% (#45). To ensure that settings fixed per document in dev do not inflate test scores, test (68 documents, 930 questions) is only committed and no code reads it. Reason for copying to `eval/golden/`: `golden_pipeline/outputs/` is not committed. Team members and VM `codeit` must receive the same questions using only `git pull`, and `golden_pipeline` only uses their own `outputs/`. Reason for removing year-end tax settlement · chunk QA: The RFP corpus lacks tax law evidence, so those scores do not indicate RFP quality. Chunk QA depends on the input (parser) …

Source. PR #48 · `feature/eval-golden-input`
