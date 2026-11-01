---
scope: project
severity: preference
triggers: []
domain: ''
title: "retrieval: Read the 'Organization' column of data_list.csv as 'Ordering Organization'"
pr: 55
merged: 2026-10-16
branch: "fix/org-csv-header"
---

# retrieval: Read the 'Organization' column of data_list.csv as 'Ordering Organization'

What. Fixed the issue where the retriever could not read the team shared `data/data_list.csv` and stopped at the start stage. It now reads the organization column name by changing it from `발주 기관` to `발주기관`.

Why. The team changed the header of `data_list.csv` to `파일명,발주기관` (no spaces). `golden_pipeline/plan.py` already reads the new name, but the retriever `read_csv_orgs` was still reading the old name `row["발주 기관"]`. Before: `HybridIndex(artifacts, cfg)` → `KeyError: '발주 기관'`. 02 Indexing · Search, 04 Generation, and Question screens all fail to start. After: `HybridIndex` is created with the same CSV, and "Tell me about the Gyeongsangbuk-do Bonghwa-gun Disaster Integrated Management System Advancement Project" is routed from organization `경상북도 봉화군` → 1 document. …

Source. PR #55 · `fix/org-csv-header`
