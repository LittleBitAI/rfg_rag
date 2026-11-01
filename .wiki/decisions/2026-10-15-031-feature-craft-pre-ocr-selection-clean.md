---
scope: project
severity: contract
triggers: ["화면", "vision", "프레임", "스크린", "캡처", "공유"]
domain: vision
title: "[Preprocessing] Added selective CRAFT image screening before Vision OCR"
pr: 31
merged: 2026-10-15
branch: "feature/craft-pre-ocr-selection-clean"
---

# [Preprocessing] Added selective CRAFT image screening before Vision OCR

What. Connects selective CRAFT region detection before the existing OpenAI Vision OCR. CRAFT does not read text but only screens candidates, while character recognition and response use the existing Vision path. The default is OFF.

Why. This change aims to distinguish candidates where text regions are detected before sending all document images to the paid OCR. Since treating detection failures or absence of regions as unnecessary may result in loss of content, uncertain images are recorded in the review queue. PDF connection errors found during review have also been fixed. Grayscale scans, which were previously dropped due to array decoding failures, are now passed to Vision as normal candidates. If image batch location lookup fails, instead of discarding the entire PDF, only the relevant image is left in the review queue, and normal body/table processing continues.

Source. PR #31 · `feature/craft-pre-ocr-selection-clean`
