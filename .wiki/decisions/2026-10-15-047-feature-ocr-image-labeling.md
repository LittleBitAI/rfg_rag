---
scope: project
severity: contract
triggers: ["화면", "vision", "프레임", "스크린", "캡처", "공유"]
domain: vision
title: "frontend: OCR image labeling screen"
pr: 47
merged: 2026-10-15
branch: "feature/ocr-image-labeling"
---

# frontend: OCR image labeling screen

What. A screen where a human must mark each image extracted from the RFP document as `1` must recognize · `2` difficult to recognize · `3` not necessary, indicating whether OCR is required.

Why. CRAFT selection keeps only the location and deletes the image from the temporary folder, and there are almost no image assets in the v11 package. Using the existing parsing function, images are extracted along with the same location fields and collected in `artifacts/ocr_labels/` where human labels are not mixed with CRAFT results. The task of having 01 preprocessing read the labels was left as a separate change for the person in charge of preprocessing. `rag/` · notebook · `golden_pipeline/` · `config.yaml` · `frontend/server.py` · `index.html` were not touched.

Source. PR #47 · `feature/ocr-image-labeling`
