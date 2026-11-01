---
scope: project
severity: preference
triggers: []
domain: ''
title: "golden_pipeline independent verification · difficulty · release: compare with the verifier's answer which only received the question and evidence, held is released after human confirmation"
pr: 26
merged: 2026-10-14
branch: "feature/golden-data-validation"
---

# golden_pipeline independent verification · difficulty · release: compare with the verifier's answer which only received the question and evidence, held is released after human confirmation

What. ③ Add independent verification · difficulty judgment · release to the `golden_pipeline/` of verification. The verifier does not see the generator's conversation · answer · self-evaluation, but receives only the question and the cited evidence units to answer on its own, and compares that independent answer with the candidate's answer after normalizing values · units. Candidates that pass type · numerical · unit · condition · table relationship · topic · duplication checks are `auto_validated`, and candidates to pass judgment to a human (evidence conflict, etc.) are `held` as `review. …

Why. The topic structure check in the generation stage (#24) is a format check. It checks if the value is written in the evidence, but it does not know if the answer is correct, if the question already contains the answer, or if it is a multi_hop that can be solved with one even if multiple pieces of evidence are cited. Therefore, it is compared with the result answered by a verifier separated from the generator that only looks at the evidence. If the verifier sees the generator's answer or explanation, it becomes easy to follow that answer, making the comparison meaningless. Therefore, the verifier input was fixed to `{"question", "evidence": [{"label", "text"}]}` (rejection: showing the generator's reasoning to the verifier). multi_hop is not determined by the number of cited evidence, but by the verifier's answer that was given only one piece of evidence at a time. …

Source. PR #26 · `feature/golden-data-validation`
