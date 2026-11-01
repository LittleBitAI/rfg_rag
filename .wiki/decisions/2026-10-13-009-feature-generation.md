---
scope: project
severity: preference
triggers: ["대화\\s*(모델|프롬프트|응답|생성)", "응답\\s*(정책|수리|스키마)", "페르소나", "말투", "gemini", "openai"]
domain: dialogue
title: "Add conversation context so that the RAG chat bot can respond to follow-up questions."
pr: 9
merged: 2026-10-13
branch: "feature/Generation"
---

# Add conversation context so that the RAG chat bot can respond to follow-up questions.

What. Modify the existing structure, which cannot refer to previous conversations, to record and transmit previous conversations and generated responses.

Why. (the PR body has no reason section; the grounds for this decision were not recorded)

Source. PR #9 · `feature/Generation`
