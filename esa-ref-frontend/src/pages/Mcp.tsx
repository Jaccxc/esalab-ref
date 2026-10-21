import { useState } from 'react'
import { auth, base as publicBase } from '../api'
import { Shell, btn, copyRef, type Me } from '../ui'

const TOOLS: [string, string][] = [
  ['how_to_upload', '回傳填好網址與 token 的 curl 指令，AI 客戶端照著上傳 .docx 就拿到工作編號'],
  ['list_jobs / get_job', '你的工作清單、進度、記錄與引用順序計畫（重新編號、佔位符、沒引用到、清單沒有）'],
  ['reference_block / set_reference_block', 'get_job 的 ask=true 時工作停在讀取條目：前者回傳原因與候選段落，後者用 paras（段落索引）或 entries（一行一筆）指出清單；split_reference_text 讓 LLM 先切行'],
  ['review_job', '需要確認的條目：目前採用的論文、候選、原始文字；all_entries=true 列全部'],
  ['research', '用 DOI / 網址 / 完整標題重查一筆，只回傳結果不改動'],
  ['choose', '採用 research 回傳的那筆（meta），或候選的第幾個（candidate）'],
  ['skip', '跳過不調整（只重新編號），可一次多筆，skip=false 取消'],
  ['continue_job', '確認完畢，接著核對順序、LLM 套格式、審查、寫回'],
  ['job_entries', '完成後每一筆的最終文字、是否改動、LLM 附註與審查問題'],
  ['result_link', '帶 token 的下載網址與存檔用的 curl'],
  ['lookup_reference', '單筆查書目，不跑 LLM，幾秒回來'],
  ['format_reference / get_task', '單筆產生 IEEE 格式（LLM，1 到 3 分鐘），逾時回任務編號再查'],
  ['資源 esalab://rules', '實驗室 IEEE 格式規則全文，客戶端自己的模型也能照著排'],
]

const Snippet = ({ title, text, note }: { title: string; text: string; note?: string }) => (
  <div className="flex flex-col gap-2">
    <div className="flex items-center gap-3 max-md:flex-wrap"><span className="font-tc text-sm font-bold">{title}</span>{note && <span className="font-tc text-xs text-dim max-md:order-last max-md:basis-full">{note}</span>}
      <button type="button" className={`${btn.ghost} ml-auto min-h-8 shrink-0 px-3 text-xs`} onClick={e => copyRef(text, e)}>複製</button></div>
    <pre className="m-0 overflow-x-auto border border-line bg-mist p-3.5 font-mono text-[12.5px] leading-relaxed whitespace-pre-wrap break-all">{text}</pre>
  </div>
)

export default function Mcp({ me }: { me: Me }) {
  const [tok, setTok] = useState('')
  const [err, setErr] = useState('')
  const base = publicBase()
  const T = tok || '<TOKEN>'
  const make = async () => { try { setTok((await auth.token()).token) } catch (x) { setErr((x as Error).message) } }
  return (
    <Shell me={me} active="mcp" wide={false}>
      <div className="flex flex-col gap-8">
        <div className="flex flex-col gap-2">
          <div className="font-mono text-xs tracking-[0.12em] text-graphite">MCP</div>
          <h1 className="m-0 font-tc text-4xl font-bold max-md:text-[26px]">用 AI 客戶端接入</h1>
          <p className="m-0 font-tc text-[15px] leading-relaxed">Claude Code、Cursor、Claude Desktop 這類支援 MCP 的客戶端可以直接操作這套系統：上傳論文用一行 curl，之後查進度、確認書目、繼續、下載都是工具呼叫。每個帳號用自己的 token，紀錄與網頁版共用。</p>
        </div>

        <section className="flex flex-col gap-4">
          <h2 className="m-0 border-b border-ink pb-2 font-tc text-[22px] font-bold">快速設定</h2>
          <p className="m-0 font-tc text-[15px] leading-relaxed text-dim">按一下產生 token，把下面這段整個貼給你的 coding agent（Claude Code、Cursor、Codex 等），它會自己把伺服器裝進自己的設定並測試連線。想手動設定再看第 1 到 3 步。</p>
          <div className="flex flex-wrap items-center gap-3">
            <button type="button" className={btn.primary} onClick={make}>{tok ? '再產生一把' : '產生一年期 token'}</button>
            {err && <span className="font-mono text-[13px] text-fail">{err}</span>}
          </div>
          <Snippet title="貼給 coding agent 的安裝提示詞" note={tok ? 'token 已帶入' : '先產生 token，否則要自己把 <TOKEN> 換掉'} text={`請把 ESA Lab 參考文獻工具的 MCP 伺服器加進你自己的 MCP 設定，名稱 esalab-ref：
- 傳輸方式：Streamable HTTP，網址 ${base}/mcp
- 認證：HTTP header「Authorization: Bearer ${T}」
- Claude Code 用：claude mcp add --transport http esalab-ref ${base}/mcp --header "Authorization: Bearer ${T}"
- Codex 把 [mcp_servers.esalab-ref] url = "${base}/mcp" http_headers = { Authorization = "Bearer ${T}" } 加進 ~/.codex/config.toml
- 其他客戶端把 {"mcpServers":{"esalab-ref":{"url":"${base}/mcp","headers":{"Authorization":"Bearer ${T}"}}}} 合併進 mcp.json（Claude Desktop 不支援 header，改用 npx -y mcp-remote ${base}/mcp --header "Authorization: Bearer ${T}"）
設定好之後呼叫 how_to_upload 工具確認連得上，並讀取資源 esalab://rules 了解格式規則。之後我要處理論文時，流程是：用 how_to_upload 給的 curl 上傳 .docx 取得 id → get_job 輪詢到 waiting → review_job → 逐筆 research / choose / skip → continue_job → get_job 到 done → result_link 下載。`} />
        </section>

        <section className="flex flex-col gap-4">
          <h2 className="m-0 border-b border-ink pb-2 font-tc text-[22px] font-bold">1 · 產生 token</h2>
          <p className="m-0 font-tc text-[15px] leading-relaxed text-dim">登入用的 token 一週就過期，上面產生的可用一年。它等同你的帳號，不要貼到公開的地方；要作廢只能請管理員換伺服器金鑰。</p>
          {tok && <Snippet title="你的 token" text={tok} note="下面的片段都已經帶入" />}
        </section>

        <section className="flex flex-col gap-5">
          <h2 className="m-0 border-b border-ink pb-2 font-tc text-[22px] font-bold">2 · 把伺服器加進客戶端</h2>
          <p className="m-0 font-tc text-[15px] leading-relaxed text-dim">伺服器網址是 <code className="bg-mist px-1 font-mono text-[13px]">{base}/mcp</code>，傳輸方式 Streamable HTTP，認證用 Bearer token。網址若換了（例如 ngrok 重啟），客戶端設定要跟著改。</p>
          <Snippet title="Claude Code" text={`claude mcp add --transport http esalab-ref ${base}/mcp --header "Authorization: Bearer ${T}"`} />
          <Snippet title="Codex" note="加進 ~/.codex/config.toml" text={`[mcp_servers.esalab-ref]
url = "${base}/mcp"
http_headers = { Authorization = "Bearer ${T}" }`} />
          <Snippet title="Cursor、Windsurf 或其他支援 HTTP 的客戶端" note="放進 mcp.json" text={JSON.stringify({ mcpServers: { "esalab-ref": { url: `${base}/mcp`, headers: { Authorization: `Bearer ${T}` } } } }, null, 2)} />
          <Snippet title="Claude Desktop" note="桌面版遠端連線只支援 OAuth，改經 mcp-remote 轉接；需要 Node.js" text={JSON.stringify({ mcpServers: { "esalab-ref": { command: 'npx', args: ['-y', 'mcp-remote', `${base}/mcp`, '--header', `Authorization: Bearer ${T}`] } } }, null, 2)} />
        </section>

        <section className="flex flex-col gap-5">
          <h2 className="m-0 border-b border-ink pb-2 font-tc text-[22px] font-bold">3 · 上傳論文</h2>
          <p className="m-0 font-tc text-[15px] leading-relaxed text-dim">上傳不走 MCP（論文檔太大），直接打 HTTP。能跑指令的客戶端會自己呼叫 <code className="bg-mist px-1 font-mono text-[13px]">how_to_upload</code> 拿到這段指令並執行；你也可以自己跑。回傳的 <code className="bg-mist px-1 font-mono text-[13px]">id</code> 就是工作編號。</p>
          <Snippet title="bash / macOS / WSL" text={`curl -sS -X POST "${base}/api/jobs" \\\n  -H "Authorization: Bearer ${T}" \\\n  -F "file=@論文.docx" -F "mode=smart" \\\n  -F "titles=第一篇新書目的標題或 DOI\n第二篇"`} />
          <Snippet title="Windows PowerShell" note="用 curl.exe，不是 PowerShell 內建的 curl 別名" text={`curl.exe -sS -X POST "${base}/api/jobs" -H "Authorization: Bearer ${T}" -F "file=@論文.docx" -F "mode=smart" -F "titles=第一篇新書目的標題或 DOI\`n第二篇"`} />
          <p className="m-0 font-tc text-[13px] leading-relaxed text-dim">欄位：mode 為 smart（預設）/ fix / add；titles 每行一筆、可省略；author 是修訂作者、可省略；review=false 會略過預覽確認直接跑完。</p>
        </section>

        <section className="flex flex-col gap-4">
          <h2 className="m-0 border-b border-ink pb-2 font-tc text-[22px] font-bold">4 · 工具一覽</h2>
          <div className="grid grid-cols-[auto_1fr] gap-x-5 gap-y-2.5 border-t border-line pt-3 max-md:grid-cols-1 max-md:gap-y-1">
            {TOOLS.map(([n, d]) => <div key={n} className="contents"><code className="font-mono text-[13px]">{n}</code><span className="font-tc text-sm leading-relaxed max-md:mb-2.5">{d}</span></div>)}
          </div>
          <p className="m-0 font-tc text-[15px] leading-relaxed text-dim">典型流程：how_to_upload → 執行 curl 取得 id → get_job 到 waiting（ask=true 就先 reference_block → set_reference_block）→ review_job → 逐筆 research / choose / skip → continue_job → get_job 到 done → result_link 下載。工作要跑十到三十分鐘，客戶端用 get_job 每隔一段時間查一次即可。</p>
        </section>

        <section className="flex flex-col gap-4">
          <h2 className="m-0 border-b border-ink pb-2 font-tc text-[22px] font-bold">5 · 貼給 AI 的提示詞範例</h2>
          <Snippet title="在 Claude Code 裡" text={`用 esalab-ref 這個 MCP 幫我處理 ./論文.docx：先用 how_to_upload 拿到指令上傳（智慧模式，新書目：「Attention is all you need」），等到 waiting 後用 review_job 看需要注意的條目；fuzzy 的若候選裡有明顯同一篇就 choose，查不到的學位論文或網頁用 skip，其餘用更完整的標題 research 再 choose。全部處理完 continue_job，完成後用 result_link 把檔案下載到 ./out/，最後用 job_entries 摘要哪些條目有附註要我補資料。`} />
        </section>
      </div>
    </Shell>
  )
}
