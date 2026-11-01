---
scope: project
severity: preference
triggers: []
domain: ''
title: "requirements: pin langchain-hwp-hwpx-loader to less than 0.2"
pr: 59
merged: 2026-10-16
branch: "fix/pin-hwp-loader"
---

# requirements: pin langchain-hwp-hwpx-loader to less than 0.2

What. Block the `requirements.txt` of `langchain-hwp-hwpx-loader>=0.1.1` with `>=0.1.1,<0.2`. This is because the naming convention for saving HWP images changed starting from 0.2, causing our code to fail to find any HWP images.

Why. While reinstalling the `.venv` on this PC, pip installed the latest version 0.2.0 that meets the conditions. Team members performing a fresh installation now receive 0.2.1. 0.1.1: Saves images as `images_dir/BIN0003.bmp`, exactly as they appear in the document. 0.2.0: Saves them with numbered names like `images_dir/<문서별 하위폴더>/image_0000.png`. The document display remains `[IMAGE: BIN0003.bmp]`. Our code searches for image files using the document display name (`os.path.join(image_dir, name)`). Therefore, in 0.2, all three of the following locations miss HWP images. | Location | 0. …

Source. PR #59 · `fix/pin-hwp-loader`
