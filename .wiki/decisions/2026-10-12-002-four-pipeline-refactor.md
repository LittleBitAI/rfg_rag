---
scope: project
severity: contract
triggers: ["화면", "vision", "프레임", "스크린", "캡처", "공유"]
domain: vision
title: "The code is divided into 5 pipelines (preprocessing, retrieval, validation, generation, evaluation), and each pipeline has its own rag/<pipeline>/ package and a notebook that simply calls it. The evaluation report separately reports on retrieval, generation, evidence, and end-to-end. Everything else and all dependencies that only it required have been deleted. OCR uses OpenAI vision behind a single flag that is off by default. If the owner's key is present, each answered question becomes one Langfuse Cloud trace (retrieval + generation including model, tokens, and cost) with evaluation scores attached to it."
pr: 2
merged: 2026-10-12
branch: "four-pipeline-refactor"
---

# The code is divided into 5 pipelines (preprocessing, retrieval, validation, generation, evaluation), and each pipeline has its own rag/<pipeline>/ package and a notebook that simply calls it. The evaluation report separately reports on retrieval, generation, evidence, and end-to-end. Everything else and all dependencies that only it required have been deleted. OCR uses OpenAI vision behind a single flag that is off by default. If the owner's key is present, each answered question becomes one Langfuse Cloud trace (retrieval + generation including model, tokens, and cost) with evaluation scores attached to it.

What. The code is divided into 5 pipelines (preprocessing, retrieval, validation, generation, evaluation), and each pipeline has its own rag/<pipeline>/ package and a notebook that simply calls it. The evaluation report separately reports on retrieval, generation, evidence, and end-to-end. Everything else and all dependencies that only it required have been deleted. OCR uses OpenAI vision behind a single flag that is off by default. …

Why. Evaluation is divided into retrieval, generation, evidence, and end-to-end, each of which maps to metrics already listed in config.yaml. — The person wants to say where bad answers come from. Existing RAGAS metrics already correspond to these four, so splitting them does not add new metric code. (Discarded: single integrated evaluation table) All four evaluations score one generation run. — One run is cheaper and does not require a second generation path. Retrieval and evidence already separate retrieval failure and hallucination. (Discarded: separate generation run using gold context doubles generation calls) Langfuse is kept for tracing only by using the observe decorator on two entry functions …

Source. PR #2 · `four-pipeline-refactor`
