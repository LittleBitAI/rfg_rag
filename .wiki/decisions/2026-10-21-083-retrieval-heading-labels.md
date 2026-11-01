---
scope: project
severity: preference
triggers: []
domain: ''
title: "retrieval: Attach separated section titles to the body search text, and rewrite detailed/evaluation questions as RFP section names."
pr: 83
merged: 2026-10-21
branch: "retrieval/heading-labels"
---

# retrieval: Attach separated section titles to the body search text, and rewrite detailed/evaluation questions as RFP section names.

What. When asked "Tell me about the Hanyoung University project" followed by "Tell me in detail what kind of project this is and evaluate it," the response stated, "Specific business functions or construction scope are not in the context." The document contains the background, construction goals, and construction scope.

Why. The section title became a chunk separated from the body. A title like "3 | Construction Scope" was read as a single-line table and became a separate chunk, and the body chunk contains neither the word "Construction Scope" nor section information. There are 228 such title chunks in 38 out of 98 documents. "Please evaluate the project" remained in the rewritten search query. Since 'evaluation' in the RFP refers to the proposal evaluation sheet, the evaluation scoring table chunks took up more than half of the search budget. The construction scope body was pushed to 31st place and the construction goals to 55th place, so they were not delivered.

Source. PR #83 · `retrieval/heading-labels`
