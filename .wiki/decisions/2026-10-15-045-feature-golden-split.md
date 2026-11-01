---
scope: project
severity: preference
triggers: []
domain: ''
title: "golden_pipeline: A split command that divides the release version into dev 30% and test 70% by document unit."
pr: 45
merged: 2026-10-15
branch: "feature/golden-split"
---

# golden_pipeline: A split command that divides the release version into dev 30% and test 70% by document unit.

What. Added a `split` command that divides the release version of five topics into dev 30% and test 70%. All questions from one document go to one side, and the dev portion is adjusted to be close to 30% for each topic × difficulty cell. It does not call the API.

Why. To evaluate with the golden dataset `final2` (1,326 items), there must be a separate dev for selecting settings and a test for calculating the final score. Reason for not splitting purely at random: If topics and difficulties are concentrated on one side, the settings chosen in dev will be evaluated on a different distribution in test. Among the 8 cells, the smallest, table-easy, has only 20 items. Reason for splitting by document unit rather than question unit: - The team looks at questions missed in dev and inserts aliases or Kiwi user words tailored to that document. - If questions from the same document are also in test, such corrections would inflate the test score, making the test appear better than it actually is. Reason for keeping dev small at 30%: dev is used every time settings are changed …

Source. PR #45 · `feature/golden-split`
