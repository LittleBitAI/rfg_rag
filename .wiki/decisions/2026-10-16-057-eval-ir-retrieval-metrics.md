---
scope: project
severity: preference
triggers: []
domain: ''
title: "evaluation: Convert search evaluation to deterministic IR metrics"
pr: 57
merged: 2026-10-16
branch: "eval-ir-retrieval-metrics"
---

# evaluation: Convert search evaluation to deterministic IR metrics

What. Change the search evaluation of 05 to deterministic Recall@k, MRR@k, and Evidence Coverage based on golden document/chunk labels. Since 04 stores the candidate ranking before packing and the chunks sent to actual generation, we can separate the issues of search ranking and context packing. By re-running only the search with the stored rewrite, we can compare dev settings without API costs.

Why. Existing Retrieval used LLM context_precision/context_recall, and Generation used answer_relevancy. Comparing search settings also incurred judge costs, and answer-question similarity could not show the performance of the dense search component itself. Also, if only the body text was stored after packing, it was impossible to distinguish whether the correct evidence was in the candidates but was excluded due to budget or deduplication. We separate document/chunk-level metrics and report fused/dense/BM25/code matching together. For questions where only some evidence is labeled, we exclude them from the average at that level to avoid overestimating completeness based only on the labeled parts, and display the count by topic and the exclusion rate. We maintain core fact string matching but do not mark it as semantic accuracy judgment.

Source. PR #57 · `eval-ir-retrieval-metrics`
