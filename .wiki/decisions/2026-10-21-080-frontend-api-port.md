---
scope: project
severity: preference
triggers: ["화면", "vision", "프레임", "스크린", "캡처", "공유"]
domain: vision
title: "frontend: Question screen API port 8765 → 8767"
pr: 80
merged: 2026-10-21
branch: "frontend/api-port"
---

# frontend: Question screen API port 8765 → 8767

What. Move the question screen API port from 8765 to 8767. - On this PC, 8765 is being used by another program (local TTS server), so the launcher's `start.cmd` question API could not start, and the screen's `/api` request went to that program. - 8767 is the number right next to the OCR labeling API (8766). - Changed locations: `frontend/start.cmd`, `frontend/start.command`, `frontend/web/vite. …

Why. (the PR body has no reason section; the grounds for this decision were not recorded)

Source. PR #80 · `frontend/api-port`
