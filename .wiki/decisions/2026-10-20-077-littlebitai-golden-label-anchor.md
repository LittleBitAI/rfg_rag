---
scope: project
severity: preference
triggers: []
domain: ''
title: "validation: Connect short golden evidence with context anchors and remeasure seven models"
pr: 77
merged: 2026-10-20
branch: "LittleBitAI/golden-label-anchor"
---

# validation: Connect short golden evidence with context anchors and remeasure seven models

What. Connect short or multi-chunk golden evidence into one chunk with other evidence blocks in the same context (context anchor). The number of chunk scoring questions increased from 194 to 329 in dev, and seven local embedding models were remeasured with these labels under v3 sealing conditions. The production retrieval model, weights, index, and Kiwi dictionary remain unchanged. The original questions, answers, and evidence are not uploaded, only the aggregates.

Why. The exact match rule did not label evidence under 20 characters and evidence spanning multiple chunks (repeated table headers, etc.). As a result, 206 out of 400 dev questions (51.5%) were excluded from chunk scoring. Only 2 out of 96 table questions remained, so the average was effectively the score for numeric and conditional questions. Context anchors are connected only when there is only one chunk containing both the evidence and another `[E]` block of 20 characters or more in the same golden context. Similarity scores are not used. The existing 379 labels remain, and when anchors were applied to the existing labels, 279 pointed to the same chunk, and there were 0 cases where they pointed to a different chunk.

Source. PR #77 · `LittleBitAI/golden-label-anchor`
