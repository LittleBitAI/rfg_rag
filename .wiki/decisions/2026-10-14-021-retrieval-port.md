---
scope: project
severity: preference
triggers: []
domain: ''
title: "The current development environment's retriever includes the feature/Retrieval changes from commit 1ed2d72 (requirement code matching and token_budget packing including BM25 code tokens, Kiwi user words, aliases and negative tokens, deduplication, agency routing with org_csv support, and TOC regex fix in parsing.py), maintains question rewriting and per-agency interleaving, and the PR shows ⑤ before and after for the same set of questions."
pr: 21
merged: 2026-10-14
branch: "retrieval-port"
---

# The current development environment's retriever includes the feature/Retrieval changes from commit 1ed2d72 (requirement code matching and token_budget packing including BM25 code tokens, Kiwi user words, aliases and negative tokens, deduplication, agency routing with org_csv support, and TOC regex fix in parsing.py), maintains question rewriting and per-agency interleaving, and the PR shows ⑤ before and after for the same set of questions.

What. Port the `feature/Retrieval` search improvements from search manager [@mitguchin](https://github.com/mitguchin)] and integrate the requested exact `main` commit `38087242282d5e8474a4bf416fa346c972e88d0d` into the working branch. Find chunks containing requirement codes first, pack results into the body token budget, and exclude nearly identical evidence. …

Why. The existing search split `SFR-001` into multiple tokens via morphological analysis and sorted them only by Dense/BM25 scores. Therefore, evidence containing the exact code could be limited by the candidate count or placed behind general sentences, and the method of cutting results into five chunks did not account for chunk length or repetitive content. Agency names were also only collected from file titles and the beginning of documents, failing to utilize the agency list held by the manager. The source is [`feature/Retrieval`'s `1ed2d72`](https://github.com/LittleBitAI/rfg_rag/commit/1ed2d7285e711fc53badeb64af70bf69b8c20364)]. It has been pinned to the version specified by the original specification. …

Source. PR #21 · `retrieval-port`
