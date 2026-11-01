---
scope: project
severity: contract
triggers: ["대화\\s*(모델|프롬프트|응답|생성)", "응답\\s*(정책|수리|스키마)", "페르소나", "말투", "gemini", "openai"]
domain: dialogue
title: "rewrite: Send the previous conversation as a quoted text and insert the organization name into the follow-up question."
pr: 82
merged: 2026-10-21
branch: "retrieval/rewrite-history"
---

# rewrite: Send the previous conversation as a quoted text and insert the organization name into the follow-up question.

What. When asking a follow-up question on the question screen as shown below, it replied that it "cannot confirm" the project period and project budget in the document.

Why. (a) The rewrite wrote the answer instead of the question. When sending the previous conversation in user/assistant order, the rewrite model did not rewrite "What is the project period?" but continued writing the previous answer. Therefore, an answer sentence like "...the project period cannot be confirmed from the provided information." became the search query. (b) The organization name was omitted in the follow-up question. "What is the project cost?" was rewritten as "How much is the project budget (project cost)?", so the organization routing was not triggered, and 31 irrelevant chunks were retrieved from the entire document. (c) The general project question could not find the overview chunk. It was rewritten as "What is the content of the Korea University project?", so the overview chunk was pushed to 11th place and could not be included in the context.

Source. PR #82 · `retrieval/rewrite-history`
