---
scope: project
severity: preference
triggers: []
domain: ''
title: "golden_pipeline A self-improvement: failure code · prevention rule recording, reflection in next round, limit · iteration"
pr: 28
merged: 2026-10-14
branch: "feature/golden-data-self-improvement"
---

# golden_pipeline A self-improvement: failure code · prevention rule recording, reflection in next round, limit · iteration

What. ③ Attach A-style self-improvement to the `golden_pipeline/` of verification. Run A in the order of generation per round → independent verification → failure recording, and leave rejected candidates as they are while recording them in the `failure_memory` of the topic with failure codes and prevention rules. In the next round, attach the prevention rule corresponding to the failure code of that topic to the A prompt, and call only the evidence bundles that have not yet passed again. …

Why. Verification (#26) leaves a reason for rejection, but since that reason is not conveyed to the next generation, A repeats the same mistake. Therefore, group rejections into codes and attach the prevention rules set for each code to the next round. Do not include corrected answers in the failure record. This is because if an unverified answer enters the next prompt as a fact, subsequent candidates will follow that answer and become contaminated (Rejection: feeding corrected answers back into the prompt). Therefore, the record items only contain the failure code, a reference pointing to the preserved failure, and the rule text and version. The release version is the evaluation answer. Since the question · answer · human verification reason would contaminate the evaluation if they leaked to the generation side through the failure record, block them in the only function (`write_memory`) used for writing to the failure record. …

Source. PR #28 · `feature/golden-data-self-improvement`
