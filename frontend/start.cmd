@echo off
rem Question screen: API server on 8765 + Vite dev server on 5173, opened in the default browser.
rem Both run in this one window (start /b), so closing it stops both.
rem Keep this file ASCII: cmd.exe reads it in the console code page, not UTF-8.
title rfg_rag question screen - close this window to stop
cd /d "%~dp0.."
start /b "" .venv\Scripts\python -m uvicorn frontend.server:app --port 8765
cd frontend\web
if not exist node_modules call npm install
call npm run dev -- --open
