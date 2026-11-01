---
scope: project
severity: preference
triggers: []
domain: ''
title: "retrieval: Kiwi BM25 dev measurement results and application of winner tokenizer"
pr: 64
merged: 2026-10-17
branch: "review-kiwi-bm25-tokenizer"
---

# retrieval: Kiwi BM25 dev measurement results and application of winner tokenizer

What. We reviewed the issue where BM25 splits `개인정보처리시스템` into multiple morphemes and leaves function words like `및` as dev search metrics. After measuring each of the five candidates, we adopted only noise removal and data-driven user dictionaries that passed the criteria. The fused chunk Recall@10 increased by 1.34%p from 0.747312 to 0.760753, and among the 36 Recall/MRR metrics, none declined by more than 0.01.

Why. The existing user dictionary only had 7 manually defined terms, so it could not sufficiently preserve actual organization names and recurring compound words. Conversely, some morphemes used as functions remained in both search queries and chunks. Since we could not guarantee that BM25 improvement alone would lead to actual fusion search improvement, we adopted the fused chunk Recall@10 increase and the preservation of 36 metrics (document/chunk × 3 components × Recall/MRR × k=5/10/20) as the adoption criteria. We compared compound noun combination, noise removal, dictionary expansion, hyphen identifiers, and mixed character identifiers with the baseline, respectively. `ISMS-P` and `GS인증` were measured as separate candidates. We did not adopt them based on cumulative experiments or BM25 scores alone. …

Source. PR #64 · `review-kiwi-bm25-tokenizer`
