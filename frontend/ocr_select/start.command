#!/bin/bash
# OCR 이미지 라벨링 화면: API 서버(8766)와 Vite 개발 서버(5174)를 켜고 기본 브라우저로 연다.
# 먼저 저장소 최상위에서 .venv/bin/python -m frontend.ocr_select.extract 를 실행해 둔다.
# 5174 라서 질문 화면(5173)과 함께 띄울 수 있다.
# Finder 에서 더블클릭하면 홈 폴더에서 실행되므로 먼저 저장소 최상위로 옮긴다.
cd "$(dirname "$0")/../.." || exit 1
.venv/bin/python -m uvicorn frontend.ocr_select.server:app --port 8766 &
API_PID=$!
# 창을 닫거나 Ctrl+C 로 끝내면 API 서버도 끈다
trap 'kill $API_PID' EXIT
cd frontend/web || exit 1
npm install --no-audit --no-fund
npm run dev -- --port 5174 --open /ocr.html
