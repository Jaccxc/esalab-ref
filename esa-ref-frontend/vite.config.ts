import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'
import tailwindcss from '@tailwindcss/vite'

// Dev: the API is proxied, so the app is same-origin in dev and behind nginx alike (no CORS, SSE works).
export default defineConfig({
  plugins: [react(), tailwindcss()],
  server: {
    proxy: { '/api': { target: process.env.API_URL || 'http://127.0.0.1:8000', changeOrigin: true } },
  },
})
