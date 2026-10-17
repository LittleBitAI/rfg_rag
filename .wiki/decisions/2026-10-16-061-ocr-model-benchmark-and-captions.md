---
scope: project
severity: preference
triggers: []
domain: ''
title: "preprocessing: Comparison by OCR type and connection of 391 stored transcriptions"
pr: 61
merged: 2026-10-16
branch: "ocr-model-benchmark-and-captions"
---

# preprocessing: Comparison by OCR type and connection of 391 stored transcriptions

What. We transcribed 320 images of labels 1 and 2 using an OCR engine compared by type and connected them to 391 locations within the document. `gemini-3.5-flash-lite` was selected for tables and text, and `gpt-6-luna` for diagrams. `01_preprocessing.ipynb` reads `data/ocr_captions.jsonl` and creates a `image_caption` record at the corresponding location, and this stored transcription does not require an API key or paid calls to use.

Why. In the existing default `OCR = False`, text in images was not included in the chunks. To read images with `OCR = True`, OpenAI Vision calls had to be made in each execution environment, and it was impossible to compare quality and cost with Gemini or PaddleOCR under the existing OpenAI-only and local VLM prohibition rules. Since the required recognition capabilities differ by type, we measured quality and cost per image from the same reference images to select an engine, and changed it so that team members can execute 01 without re-calling by saving the results in `data/`. API candidates are selected in the order of keyword recall, precision, and low cost. A local model becomes the winner for that type when its recall is within 5%p lower than the top API and its precision is not lower. …

Source. PR #61 · `ocr-model-benchmark-and-captions`
