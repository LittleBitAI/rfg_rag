---
scope: project
severity: landmine
repeat: rule
triggers: ['포트', '(?i)\bport', '8767', '8766', '5173', '(?i)start\.cmd', '(?i)start\.command', '(?i)golden\.cmd', '실행기', '(?i)launcher', '(?i)vite', '(?i)uvicorn', '(?i)cp949', '인코딩', '(?i)encoding']
slots: []
sources: ['commit 20813a8', 'frontend/start.cmd#L5', 'frontend/web/vite.config.js#L10', 'README.md#L223', 'golden_pipeline/cli.py#L23']
links: []
---

# Ports change in three places together; Windows launchers stay ASCII; Python CLIs force UTF-8 output

Rule. The chat API runs on 8767, the OCR API on 8766, Vite on 5173 with
`strictPort`. To change a port, change `frontend/start.cmd`,
`frontend/start.command` and the proxy in `frontend/web/vite.config.js` in
the same change. Keep every `.cmd` file pure ASCII (`frontend/start.cmd`,
`golden_pipeline/golden.cmd`), with Korean only in Python or docs. A Python
CLI whose output may be redirected on Windows reconfigures `sys.stdout` to
UTF-8, as `golden_pipeline/cli.py` does. Launchers start the repository
`.venv`, and closing the launcher window stops every server it started.

Why. `cmd.exe` reads `.cmd` files in the console code page, not UTF-8.
Redirected output on Windows is written in cp949, and a golden loop that had
run to the end crashed on characters such as `∙` when printing its result
(commit 20813a8). The Vite proxy hard-codes both API ports.

What goes wrong. A port changed in one place leaves the screen answering 502
or 404; a non-ASCII `.cmd` runs garbled commands; a long paid loop dies at
its last print.
