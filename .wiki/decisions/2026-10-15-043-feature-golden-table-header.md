---
scope: project
severity: preference
triggers: []
domain: ''
title: "golden_pipeline: display table headers, try one failure code per round, new data_list name, comparison target rules"
pr: 43
merged: 2026-10-15
branch: "feature/golden-table-header"
---

# golden_pipeline: display table headers, try one failure code per round, new data_list name, comparison target rules

What. There are 4 improvements to golden data generation quality and 1 release tool. - Display header rows in table bundles. - The adoption lower bound tries only one failure code per round. - Reads the changed `data/data_list.csv`. - Added comparison target rules. - Added a `rename` command to reissue without an API by changing only the document name.

Why. Table headers: Out of about 90 verification rejections in table fill1, 80 were `table_relation`. Because it was not visible in the evidence context which row was the header, the generator asked for header cells as values or swapped rows and columns. Try one code at a time: When multiple failure codes were tested at once, helpful rules were discarded along with harmful ones. In fill1, all 11 rules for table and comparison were discarded. data_list: The team changed column names to `발주기관` and corrected the names of 19 out of 98 institutions (e.g., KOICA → Korea International Cooperation Agency). If left as is, plan generation stops at `KeyError: '발주 기관'`, and the same document is released under two names within a single release version. …

Source. PR #43 · `feature/golden-table-header`
