---
scope: project
severity: preference
triggers: []
domain: ''
title: "docs: RFP chunking comparison · preprocessing improvement history notebook, output cleared (Author: hwangsiiiii)"
pr: 79
merged: 2026-10-20
branch: "preprocessing-notebooks"
---

# docs: RFP chunking comparison · preprocessing improvement history notebook, output cleared (Author: hwangsiiiii)

What. I am uploading 2 out of 4 RFP preprocessing notebooks by `origin/feature/preprocessing`(Author: hwangsiiiii) to `preprocessing/` in dev. Both notebooks have had their output cells cleared.

Why. There are no experiment records from the preprocessing lead in dev. If the branch is merged as is, the RFP text excerpts stored in the notebook outputs will be uploaded as well. These include table contents, requirement sentences, OCR original text comparisons, and cover page text, which violates CLAUDE.md 1.4. Therefore, only the two notebooks that remain valid without output were recommitted with the output cleared under the original author's name.

Source. PR #79 · `preprocessing-notebooks`
