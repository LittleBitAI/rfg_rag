@echo off
rem Question screen: API server on 8765 (own window) + Vite dev server on 5173, opened in the default browser.
rem Keep this file ASCII: cmd.exe reads it in the console code page, not UTF-8.
cd /d "%~dp0.."
start "rfg_rag API :8765" .venv\Scripts\python -m uvicorn frontend.server:app --port 8765
cd frontend\web
if not exist node_modules call npm install
call npm run dev -- --open
