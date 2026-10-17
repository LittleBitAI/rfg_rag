---
scope: project
severity: contract
triggers: ["화면", "vision", "프레임", "스크린", "캡처", "공유"]
domain: vision
title: "frontend: Added screen for reviewing saved OCR results"
pr: 62
merged: 2026-10-17
branch: "ocr-result-review"
---

# frontend: Added screen for reviewing saved OCR results

What. Add `OCR 결과 검토` directly below `OCR 이미지 라벨링` in `설정` on the question screen. Group the 391 locations of saved OCR results by image hash to compare 320 original images and transcriptions side-by-side, and save the `OK` · `일부 틀림` · `틀림` judgment. Since the judgment is tied not only to the image but also to the actual reviewed transcription text, engine, and image type, it must be reviewed again if the OCR output changes.

Why. The existing labeling screen was for selecting whether an image is an OCR target by location, so it was not possible to compare the quality of saved transcriptions with the original or record review results. Since the original and transcription are already on disk, only the saved data is read without re-recognition. Group the same images into one card while keeping all appearance locations, and reuse the 8766 server of the existing executor and the installed Markdown package. Even if the image bytes are the same, the OCR output can be updated. If judgments are linked only by image hash, changed transcriptions will be incorrectly marked as already reviewed. Therefore, record the SHA-256 of the text, engine, and image type separately and apply only the judgments that match the current output. …

Source. PR #62 · `ocr-result-review`
