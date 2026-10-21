# esa-ref-backend — 參考文獻 → Word 修訂模式

上傳論文 .docx，工具會找出 References 底下的 `[n]` 條目，查 Crossref / OpenAlex 取得可信書目，
交給 agent 依 **ESA Lab 規則**（`rules/esalab-ieee-rules.md`，整理自教授投影片與兩份已核可論文）
套格式並再做一次規則審查，最後以 **Word 修訂模式** 寫回，前端即時顯示階段、百分比與預估剩餘時間。

```
瀏覽器 ──SSE 進度──▶ FastAPI (uv, Python 3.12+)
                     ├─ docx_track.py   讀 [n] 條目 / 以 <w:ins><w:del> 寫回（純 OOXML，不需 Word）
                     ├─ lookup.py       Crossref 精確標題 → OpenAlex → Crossref 模糊（標記 fuzzy）
                     ├─ pipeline.py     job 狀態機：extract → lookup → format → check → apply，狀態與輸入/輸出 .docx 都存在 SQLite jobs 表
                     └─ agent.py  ───▶  opencode serve（Linux，別人維護的 agent 引擎，預設免費模型 opencode/glm-5.3-flash-free）
```

LLM 只做兩件事、不能改檔案或跑指令（`opencode.json` 的 `refs` agent 只開 webfetch）：
1. **format**：原始條目 + 書目 metadata → 單一條目（`*斜體*` 標記）＋ issues
2. **check**：對照規則審查，不合格就回傳修正版

## 跑起來（Linux / 伺服器）

```bash
curl -fsSL https://opencode.ai/install | bash      # agent 引擎
curl -LsSf https://astral.sh/uv/install.sh | sh    # Python 套件管理
uv sync
bash scripts/start.sh                              # 起 opencode serve(4096) + uvicorn(8000)
```
或 `docker build -t esalab . && docker run -p 8000:8000 esalab`。開 http://localhost:8000。

免費模型不需金鑰（`opencode` provider 預設已連線）。要換模型設 `OPENCODE_MODEL=opencode/big-pickle`
或任何 OpenCode 支援的 `provider/model`；要用自己的金鑰就 `opencode auth login` 或在 `opencode.json` 加 provider。
若 opencode 設了 `OPENCODE_SERVER_PASSWORD`，本服務讀同一個環境變數。

## Windows 開發

OpenCode 跑在 WSL Ubuntu：`cd /mnt/c/projects/jacc/esalab && opencode serve --port 4097`，
`.env` 裡 `OPENCODE_URL=http://127.0.0.1:4097`。然後 `uv run uvicorn esalab.app:app --port 8000`。

## API

| 方法 | 路徑 | 說明 |
|---|---|---|
| POST | `/api/jobs` | multipart：`file`(.docx)、`mode`=`smart`(預設：補缺的、修舊的、校引用順序) / `fix` / `add`、`titles`(每行一篇：標題、DOI 或 URL)、`author`、`review`(預設 true：查完書目先暫停讓使用者確認) → `{id}` |
| POST | `/api/jobs/{id}/research`、`/choose`、`/continue` | 審閱階段：重查某筆 `{index, query}`、選候選/保留原樣 `{index, choice | keep}`、繼續 |
| POST | `/api/search` | `{query}` 預查：系統找不找得到這篇（不經 LLM） |
| POST | `/api/reference` | `{query, meta?}` 單筆產生參考文獻（各自獨立的 OpenCode session），存進 `refs` 表；`GET /api/references` 看自己的歷史 |
| GET | `/api/jobs/{id}` | 完整狀態（status 含 `waiting`、stage、percent、eta_seconds、items[]、order、log[]） |
| GET | `/api/jobs/{id}/events` | SSE，每次狀態變動推一筆 |
| GET | `/api/jobs/{id}/result.docx` | 修訂後的檔案 |
| GET | `/api/health` | opencode 是否可連、使用的模型 |
| — | 書目查詢快取 | `lookups` 表以正規化後的查詢字串為 key，30 天內不重查；`none` 結果不快取 |
| POST | `/api/register` / `/api/login` | JSON `{username, password}` → `{token}`（JWT，7 天） |
| GET | `/api/me` | 目前登入者 `{username, admin}` |
| DELETE | `/api/jobs/{id}` | 刪除自己的已結束工作 |
| GET | `/api/admin/stats`、`/api/admin/jobs` | 管理員（`ADMIN_USER`/`ADMIN_PASSWORD` 設定，`ADMIN_USERS` 可列多人）：全站統計、所有人的工作 |

### 登入與多使用者
- 前端功能規格（給設計用）在 `docs/ui-spec.md`。
- 唯一的持久化儲存是 SQLite `data/esalab.db`：`users`（scrypt 雜湊密碼）、`jobs`（狀態 JSON＋輸入/輸出 .docx blob）、`settings`（JWT 金鑰）。部署時把 `data/` 掛成 volume 即可。
- 除了 `/`、`/api/register`、`/api/login`，**每個端點都要 JWT**：`Authorization: Bearer <token>`；SSE 與下載連結瀏覽器無法帶 header，改用 `?token=<token>`。
- 身分一律由 token 解出，jobs 以 `jobs.user` 欄位歸屬，別人的 job 看不到（404）。
- 簽章金鑰：環境變數 `JWT_SECRET`；沒設就自動產生一次並存在 `settings` 表。

## 測試

```bash
uv run pytest -q
```
