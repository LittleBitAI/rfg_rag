---
scope: project
severity: preference
triggers: []
domain: ''
title: "docs: Restore aggregate metrics and selection conclusions"
pr: 67
merged: 2026-10-19
branch: "restore-aggregate-measurements"
---

# docs: Restore aggregate metrics and selection conclusions

What. Restores the aggregate report missing along with raw records from the PR #66 cleanup. Excludes actual questions, answers, evidence, OCR transcripts, and excerpts, replacing examples with independently written synthetic content. Retains existing scores, denominators, costs, times, selection conclusions, and limitations; no new benchmarks, paid API calls, or tests are added.

Why. Distinguishes between raw record cleanup and permitted aggregate archiving so that team members can verify selection evidence in Git. Restored by section to avoid reverting to raw records, and kept only aggregates and general interpretations in mixed reports. Previous revisions cleaned up current content and work ancestors but failed to prove the blocking of remote access. Guidance on the location of past objects left in public documents and PR bodies also had to be removed. Detailed thought lists are kept only in ignored local files, leaving only counts, processing status, and limitations in public records. Additionally, claims regarding automatic diff folding in historical reports and public provenance review were corrected to the current public scope as they did not match actual repository properties.

Source. PR #67 · `restore-aggregate-measurements`
