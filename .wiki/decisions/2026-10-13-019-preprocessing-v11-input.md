---
scope: project
severity: preference
triggers: []
domain: ''
title: "v11 preprocessing package input and 2048 token embedding support"
pr: 19
merged: 2026-10-13
branch: "preprocessing-v11-input"
---

# v11 preprocessing package input and 2048 token embedding support

What. In 01, I enabled direct reading of the v11 package by the preprocessor, allowing it to be saved as `docs.jsonl` and `chunks.jsonl` used by the existing 02 search. The default value is the current parser. The maximum input length for embedding has been increased from 512 to 2048. Se hui Hwang in README and this PR

Why. ### Review R1 F1: v11 body quality summary fix I first reproduced the issue where the body, which is `kind=prose` in the existing synthetic fixture, had a 0% truncation rate in the middle of sentences, but became 100% when changed to `kind=text` without changing the body itself. This is because `chunk_summary` only calculates `text`, which is the body type of the repository. I modified it to normalize only `prose → text` in `load_v11_package`. Other chunk types remain as they are. The field mapping description in the README has also been aligned with the same policy. There are 2 other downstream consumers to which the same rules can be applied. …

Source. PR #19 · `preprocessing-v11-input`
