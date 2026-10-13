#!/bin/bash
# 질문 화면: API 서버(8765)와 Vite 개발 서버(5173)를 켜고 기본 브라우저로 연다.
# Finder 에서 더블클릭하면 홈 폴더에서 실행되므로 먼저 이 파일의 폴더로 옮긴다.
cd "$(dirname "$0")/.." || exit 1
.venv/bin/python -m uvicorn frontend.server:app --port 8765 &
API_PID=$!
# 창을 닫거나 Ctrl+C 로 끝내면 API 서버도 끈다
trap 'kill $API_PID' EXIT
cd frontend/web || exit 1
# node_modules 가 있어도 매번 — pull 로 package.json 에 패키지가 늘었을 수 있다 (최신이면 1초 남짓)
npm install --no-audit --no-fund
npm run dev -- --open
