import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

// API 포트는 start.cmd · start.command 가 띄우는 uvicorn 포트(8765)와 같아야 한다
// /ocr-api 는 OCR 이미지 라벨링 화면(ocr.html)의 서버 — frontend/ocr_select/start.cmd · start.command 의 8766
export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173, strictPort: true,
    proxy: { '/api': 'http://127.0.0.1:8765', '/ocr-api': 'http://127.0.0.1:8766' },
  },
  build: { rollupOptions: { input: ['index.html', 'ocr.html'] } },
})
