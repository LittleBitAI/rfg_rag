---
scope: project
severity: contract
triggers: ["대화\\s*(모델|프롬프트|응답|생성)", "응답\\s*(정책|수리|스키마)", "페르소나", "말투", "gemini", "openai"]
domain: dialogue
title: "retrieval: Rewrite follow-up questions based on the last 10 conversations and route the organization using the rewritten question."
pr: 52
merged: 2026-10-16
branch: "fix-followup-rewrite-routing"
---

# retrieval: Rewrite follow-up questions based on the last 10 conversations and route the organization using the rewritten question.

What. Supplement follow-up questions like `그 사업 예산은?` with previous conversations for retrieval, and select the ordering organization using the rewritten question. If you ask about a Korea University project and then ask a follow-up question, it will search within Korea University documents.

Why. Previously, previous conversations were only passed for response generation. If there was no organization name in the follow-up question, rewriting and organization routing could not restore the target, resulting in retrieving evidence from other organizations across all documents.

Source. PR #52 · `fix-followup-rewrite-routing`
