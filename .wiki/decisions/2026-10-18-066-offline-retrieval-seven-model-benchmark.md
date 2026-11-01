---
scope: project
severity: preference
triggers: []
domain: ''
title: "retrieval: Added a comparison tool for 7 local embedding searches"
pr: 66
merged: 2026-10-18
branch: "offline-retrieval-seven-model-benchmark"
---

# retrieval: Added a comparison tool for 7 local embedding searches

What. Add an offline benchmark that compares search methods and local embedding models in development materials under the same conditions. Do not change the production search model, active index, or default values. Do not disclose dataset records such as actual questions, answers, or evidence. Depending on user confirmation, aggregate counts, quality scores, latency, memory measurements, and reports explaining them may be published. Do not delete documents solely because they only contain measurements.

Why. If the existing evaluation input was used as is, questions necessary for search evaluation could be omitted due to the `key_facts` condition for answer string scoring. For example, multi-evidence questions that have evidence but are `key_facts=[]` are now also kept as search targets. Check the exact evidence ref and context block of the original plan and connect to the current chunk only with the existing exact mapping rules. Do not score questions with only partial evidence mapping as a complete answer set. Production search has code promotion and quantity filter paths, which can be mixed with the contributions of BM25 and embedding rankings. Therefore, we provide both isolated comparisons that maintain the same engine routing and integrated comparisons that maintain production behavior. …

Source. PR #66 · `offline-retrieval-seven-model-benchmark`
