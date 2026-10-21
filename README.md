# esalab · 論文參考文獻修訂工具

兩個容器、一個 compose：

| 資料夾 | 內容 | 容器 |
|---|---|---|
| `esa-ref-backend/` | FastAPI API + OpenCode agent engine + SQLite（users / jobs / refs / lookups 快取），Word 修訂寫回 | `backend`（內部 :8000） |
| `esa-ref-frontend/` | React 19 + Vite + TypeScript + Tailwind v4 的 SPA；nginx 提供靜態檔並把 `/api` 轉給 backend（SSE 不緩衝） | `frontend`（對外 `PORT`，預設 8080） |
| `docs/ui-spec.md` | 給 Claude Design 的前端功能規格與 API 契約 | — |

## 跑起來（Linux，Docker）
```bash
cp esa-ref-backend/.env.example esa-ref-backend/.env   # 或自己建：OPENCODE_MODEL、JWT_SECRET、ADMIN_PASSWORD
PORT=8080 docker compose up -d --build
# http://<host>:8080  ；管理員帳號由 .env 的 ADMIN_USER / ADMIN_PASSWORD 決定
```
資料只在 volume `esalab-data`（SQLite 檔）。

## 開發
```bash
# backend（需 opencode serve，見 esa-ref-backend/README.md）
cd esa-ref-backend && uv sync && uv run uvicorn esalab.app:app --port 8000
# frontend：Vite dev server 會把 /api 代理到 127.0.0.1:8000（可用 API_URL 覆寫）
cd esa-ref-frontend && npm install && npm run dev
```

## 為什麼選 React + Vite + Tailwind
Claude Design 的產出就是 HTML/CSS，照搬成 React/Tailwind 元件不用翻譯；沒有 SSR 需求，靜態 build 丟 nginx 最省。`src/api.ts` 包好 token、SSE 與所有端點；頁面在 `src/pages/`（Login、Workbench、JobDetail、Preview、Lookup、Admin），路由用 hash（`#/jobs/<id>/preview`），不另裝 router。
