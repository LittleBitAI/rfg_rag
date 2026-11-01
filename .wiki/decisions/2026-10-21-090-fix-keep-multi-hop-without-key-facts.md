---
scope: project
severity: preference
triggers: []
domain: ''
title: "validation: Leaving multi-hop evidence questions without key facts in the evaluation set"
pr: 90
merged: 2026-10-21
branch: "fix/keep-multi-hop-without-key-facts"
---

# validation: Leaving multi-hop evidence questions without key facts in the evaluation set

What. 03(Validation) removed the check that entirely excluded golden questions without key_facts from the evaluation dataset. Now, such questions are only excluded from the Generation key fact score, but are included in retrieval metrics and both judge evaluations (Faithfulness · Factual Correctness).

Why. The key facts for multi-hop questions are extracted from the cell values of the evidence table. Since the correct answer is descriptive, if the cell value does not cover 60% of the correct answer, `_multi_hop_key_facts` returns an empty list (to prevent full marks when only part of the answer is correct, #48). However, the "no key_facts" check in `check_eval_items` entirely excluded these questions from the evaluation dataset. Metrics that do not require key facts were unable to see these questions (Retrieval Recall@k · MRR · Evidence Coverage, Faithfulness, Factual Correctness). Based on golden final6, the number of excluded questions is 24 for dev and 63 for test, totaling 87, all of which are multi-hop.

Source. PR #90 · `fix/keep-multi-hop-without-key-facts`
