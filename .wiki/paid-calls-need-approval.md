---
scope: project
severity: contract
repeat: rule
triggers: ['유료', '비용', '단가', '요금', '(?i)\bapi\b', '(?i)openai', '(?i)gemini', '(?i)ragas', '심판', '(?i)judge', '(?i)\btest\b ?(셋|set)', '(?i)\bdev\b', '(?i)\bocr\b', '(?i)--budget']
slots: []
sources: ['CLAUDE.md#L116', 'CLAUDE.md#L174', 'golden_pipeline/README.md#L84', 'rag/usage.py#L16']
links: []
---

# Show a price estimate and wait for approval before a paid run; log every paid call; run test once

Rule. Before the first paid call of an OCR benchmark, a full OCR run, the
paid 30-question dev sample, or any paid `golden_pipeline` command, show a
per-model token-price estimate (rewrite, answer and both judges where they
apply) and wait for the person's approval. Every paid call goes through
`rag/usage.py` into `artifacts/api_usage.csv`, including judge retries;
PaddleOCR records seconds per image instead. Tune on dev only. Build the
labelled test set with 03's existing functions, then run 04 and all four 05
evaluations on test once, with fixed settings, for the final result; never
run test while developing retrieval metrics.

Why. The OpenAI key is shared, so an unannounced run spends other people's
budget. `CLAUDE.md` sections 4 and 5 fix the approval points and the dev/test
split; `golden_pipeline` paid commands refuse to start without model,
reasoning effort, price, max calls and budget (`golden_pipeline/README.md:84-87`).
Reruns of retrieval alone use `rerun_retrieval`, which makes no API calls.

What goes wrong. Spend nobody approved, usage missing from the cost tables,
or a test score tuned on test and no longer a fair final result.
