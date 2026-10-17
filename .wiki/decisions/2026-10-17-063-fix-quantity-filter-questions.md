---
scope: project
severity: preference
triggers: []
domain: ''
title: "retrieval: Querying all projects and overviews by quantity conditions"
pr: 63
merged: 2026-10-17
branch: "fix-quantity-filter-questions"
---

# retrieval: Querying all projects and overviews by quantity conditions

What. I reproduced F7, where `- | - | -` following data containing unit declarations was mistaken for a separator row, deleting the year and turning the subsequent number into an amount. In a test extending the existing voice regression, 8 cases of short separator cells failed, while 2 general data control groups passed. I modified one common judgment point to require 3 or more hyphens in all cells. Long separator rows and left/right/center alignment are maintained.

Why. Existing hybrid search finds chunks similar to the question as top candidates. Therefore, even if it could find eligibility clauses containing `1억원 이상`, it could not compare actual budgets by document to list all applicable projects. The 2,500-token body budget of general search was also insufficient to convey the values and overviews of dozens of projects. Since the cause of the problem is the absence of value selection and condition application for the entire document, I did not resolve it solely by adjusting search weights or prompts. I store quantities and item names during indexing, compare the meanings of items using the existing local Embedder, and then select all projects with a decisive filter. Units use Kiwi parts-of-speech instead of a fixed list. I do not add LLM/API calls or CSV budget columns to indexing, routing, or filtering. …

Source. PR #63 · `fix-quantity-filter-questions`
