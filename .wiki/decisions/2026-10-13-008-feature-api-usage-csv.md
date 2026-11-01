---
scope: project
severity: contract
triggers: ["지연", "latency", "텔레메트리", "턴 조립", "api 조립"]
domain: api
title: "Added automatic CSV saving for API usage/cost logs and evaluation results"
pr: 8
merged: 2026-10-13
branch: "feature/api-usage-csv"
---

# Added automatic CSV saving for API usage/cost logs and evaluation results

What. | Location | Changes | |---|---| | `rag/usage.py` | Accumulate usage, actual model, and estimated cost for every API response in `artifacts/api_usage.csv`. Provide LangChain callbacks for OCR/RAGAS and summaries of call counts, tokens, and costs by step, model, and evaluation type. CSV writing for asynchronous judge calls is protected by locks | | `rag/preprocessing/parsing.py` | Connect usage callback to OCR model. …

Why. Although question rewriting and notebook setup cells were added in PR #6 and #7, API usage was only recorded for some tokens in answers/rewrites and Langfuse traces. Team members without Langfuse keys could not check call counts, tokens, and costs for OCR and RAGAS judges, and End-to-End costs only included answer generation, failing to reflect rewrite costs and cache input discounts. In the third branch, usage for OCR, rewrite, answer generation, and Judge/RAGAS is automatically recorded to a local CSV, and existing evaluation result CSV saving is moved to the evaluation function.

Source. PR #8 · `feature/api-usage-csv`
