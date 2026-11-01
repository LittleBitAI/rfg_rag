---
scope: project
severity: preference
triggers: []
domain: ''
title: "retrieval: Remaining changes in Retrieval branch — porting 2/6~6/6 · local judge · RRF (written by: mitguchin)"
pr: 78
merged: 2026-10-20
branch: "retrieval-port/land-stack"
---

# retrieval: Remaining changes in Retrieval branch — porting 2/6~6/6 · local judge · RRF (written by: mitguchin)

What. `origin/feature/Retrieval`(written by: mitguchin) Uploading all changes currently missing from dev among the commits. There are three bundles.

Why. #70~#75 stacked PRs like a chain, each using the branch of the immediately preceding PR as its base. Only #70 has been merged into dev. #71(base `retrieval-port/requirement-links`) was closed 2 minutes after #70 was merged. There is no remaining record, so the exact reason is unknown. It appears to have been closed automatically as the base branch was deleted. Subsequently, #72~#75 were each merged only into the branch of the preceding PR. Therefore, the 2/6~6/6 code exists only in the `retrieval-port/*` branch and not in dev. In the meantime, mitguchin uploaded two more commits to the branch (6d1023a short answer grading, bc19ad1 RRF). The local judge that was not moved in #72 is also being moved this time.

Source. PR #78 · `retrieval-port/land-stack`
