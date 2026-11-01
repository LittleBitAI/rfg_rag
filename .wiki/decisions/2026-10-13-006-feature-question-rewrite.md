---
scope: project
severity: preference
triggers: []
domain: ''
title: "Added query rewriting before search and model/reasoning effort settings"
pr: 6
merged: 2026-10-13
branch: "feature/question-rewrite"
---

# Added query rewriting before search and model/reasoning effort settings

What. | Step | Before Change | After Change | |---|---|---| | Query Rewriting | None | Pass original query to OpenAI API to generate search query | | Organization Routing | Select organization/document with original query | Select organization/document with original query | | Dense/BM25 Search | Use original query | Use rewritten search query | | Answer Generation | Pass original query and search evidence | Pass original query and evidence found with rewritten search | | Evaluation Input | Original query, correct answer, key facts …

Why. The current search pipeline passes the user-inputted query directly to Dense/BM25 search. Without a step to refine it into a search query, typos or Korean/English keyboard errors cannot be corrected, and there is no target to connect the requested rewrite model and reasoning_effort settings. This PR implements the query rewriting step first and connects it for actual use in 02 Search Example and 04 Answer Generation. Rewriting is limited to the role of refining search expressions. If the rewritten results were used for organization routing or answer generation, the target organization or the question to be answered might change due to the expressions altered by the model, so the original query is maintained for those two steps and evaluation data. At the time of adding the rewriting API, the search query, model, tokens, and latency are also recorded. …

Source. PR #6 · `feature/question-rewrite`
