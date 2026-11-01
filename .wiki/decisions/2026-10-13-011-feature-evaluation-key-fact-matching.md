---
scope: project
severity: preference
triggers: []
domain: ''
title: "Modify core fact matching to compare numbers, dates, and negation based on meaning"
pr: 11
merged: 2026-10-13
branch: "feature/evaluation-key-fact-matching"
---

# Modify core fact matching to compare numbers, dates, and negation based on meaning

What. Change the method of scoring core facts by checking only for string overlap. Compare numbers by value and unit, dates by date and time, and check for negation around the matched expression. Recognize the same amount or deadline even if written in different notations, and prevent issues where different numbers or opposite conditions were accepted as correct answers.

Why. The existing `_key_fact_ratio` removed spaces and commas, converted to lowercase, and treated it as a match if the fact string was contained in the text. Therefore, `3초` was accepted because it is a part of `13초`, and `포함` was also accepted because it is inside `불포함`. In reality, search evidence or answers that did not meet the conditions could receive high scores. Conversely, `1억 3천만원` and `130,000,000원`, and `2024.6.11(화) 17:00` and `2024년 6월 11일 오후 5시` were not accepted even if they had the same meaning because the strings were different. Thus, the score was influenced by the notation method rather than whether the core fact was satisfied. This time, we used a rule to convert numbers, amounts, and dates into common expressions for comparison. …

Source. PR #11 · `feature/evaluation-key-fact-matching`
