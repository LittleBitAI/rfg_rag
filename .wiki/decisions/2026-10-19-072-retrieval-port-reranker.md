---
scope: project
severity: preference
triggers: []
domain: ''
title: "retrieval: local reranker, default off (Retrieval branch port 3/6)"
pr: 72
merged: 2026-10-19
branch: "retrieval-port/reranker"
---

# retrieval: local reranker, default off (Retrieval branch port 3/6)

What. Add local cross-encoder reranker(`dragonkue/bge-reranker-v2-m3-ko`) but default is off. - `config.yaml` `retrieval.rerank.enabled: false` — If turned on, only the top `top_n`(30) fused results are rescored, and chunks with project name preference or code matches are placed at the front. - Added `RERANK` to the 02 notebook configuration cell. If off, the model is not downloaded and behavior remains the same.

Why. (the PR body has no reason section; the grounds for this decision were not recorded)

Source. PR #72 · `retrieval-port/reranker`
