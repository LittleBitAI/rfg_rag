---
scope: project
severity: preference
triggers: []
domain: ''
title: "golden: v12 evidence adapter and validation 30 · held-out 30 remeasurement (a30v12)"
pr: 68
merged: 2026-10-19
branch: "LittleBitAI/golden-a-validation-rerun"
---

# golden: v12 evidence adapter and validation 30 · held-out 30 remeasurement (a30v12)

What. Changed the adapter to read golden dataset evidence from the v12 team package, and increased the adoption test share of the A self-improvement loop to validation 30 · held-out 30. In the results remeasured with this setting for seven topics (a30v12), none of the 9 prevention rules were adopted.

Why. In abc7, prevention rule adoption was set to 2 validation sets. Since it is a structure where adoption only occurs if both sets improve, it was difficult to believe the result that there were no adoptions. In the meantime, the evidence package has changed to `Golden_Dev396_v12_Team_Package`. The v11 adapter cannot read the v12 file structure.

Source. PR #68 · `LittleBitAI/golden-a-validation-rerun`
