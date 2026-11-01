---
scope: project
severity: preference
triggers: []
domain: ''
title: "rewrite: Rewrite cost questions using the RFP term 'project budget'."
pr: 81
merged: 2026-10-21
branch: "retrieval/budget-term"
---

# rewrite: Rewrite cost questions using the RFP term 'project budget'.

What. I added a line to the rewrite instructions: Questions asking about cost, price, amount, or budget should use the RFP term 'project budget (project cost)'. Do not change the index or tokenizer.

Why. When asking "What is the difference in project costs between Korea University and Hanyoung University?" on the question screen, Hanyoung University's budget appeared as "not in document". Hanyoung University's RFP states "project budget: within the range of 130,000,000 KRW (VAT included)". 1. The rewritten question used the word "cost" ("How do the costs of the Korea University and Hanyoung University projects differ?"). 2. The document uses the compound term "project budget", and the Kiwi user dictionary (#64) indexes this as a single token `사업예산`. The "cost" and "project budget" (→ `사업`, `예산`) in the question do not match in BM25. 3. Therefore, the budget chunk was not in the BM25 candidates (dense 22nd place), and the RRF fusion rank was pushed to 58th place, failing to make it into the token budget. …

Source. PR #81 · `retrieval/budget-term`
