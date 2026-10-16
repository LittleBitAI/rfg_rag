@echo off
rem Question screen: API server on 8765 + Vite dev server on 5173, opened in the default browser.
rem The OCR image labelling screen (Settings > OCR, /ocr.html) has its own API server on 8766.
rem All run in this one window (start /b), so closing it stops all of them.
rem Keep this file ASCII: cmd.exe reads it in the console code page, not UTF-8.
title rfg_rag question screen - close this window to stop
cd /d "%~dp0.."
start /b "" .venv\Scripts\python -m uvicorn frontend.server:app --port 8765
start /b "" .venv\Scripts\python -m uvicorn frontend.ocr_select.server:app --port 8766
cd frontend\web
rem Every run, not only when node_modules is missing: a pulled package.json may add a package (about 1 s when up to date)
call npm install --no-audit --no-fund
call npm run dev -- --open
