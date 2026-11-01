---
scope: project
severity: preference
triggers: []
domain: ''
title: "retrieval: Split requirements · Table chunk linked retrieval (Retrieval branch port 1/6)"
pr: 70
merged: 2026-10-19
branch: "retrieval-port/requirement-links"
---

# retrieval: Split requirements · Table chunk linked retrieval (Retrieval branch port 1/6)

What. Links split requirement chunks and table chunks for retrieval. - Indexes by attaching a `[요구사항 ID 명칭]` header before the detailed content chunk (`search_texts`). - Sets other chunks of the same requirement (`requirement_key` · `requirement_ids`) and the same table (`table_refs`) as linked chunks and sends them together during packing. - The v11 package loader passes the requirement affiliation information. …

Why. (the PR body has no reason section; the grounds for this decision were not recorded)

Source. PR #70 · `retrieval-port/requirement-links`
