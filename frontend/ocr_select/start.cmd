@echo off
rem OCR image labelling screen: API server on 8766 + Vite dev server on 5174, opened in the default browser.
rem Run ".venv\Scripts\python -m frontend.ocr_select.extract" from the repository root first.
rem Port 5174 lets this run next to the question screen (5173). Close this window to stop both.
rem Keep this file ASCII: cmd.exe reads it in the console code page, not UTF-8.
title rfg_rag OCR labelling - close this window to stop
cd /d "%~dp0..\.."
start /b "" .venv\Scripts\python -m uvicorn frontend.ocr_select.server:app --port 8766
cd frontend\web
call npm install --no-audit --no-fund
call npm run dev -- --port 5174 --open /ocr.html
