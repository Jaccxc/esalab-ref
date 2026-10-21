import { useEffect, useState } from 'react'
import { admin, type Event, type JobSummary, type Stats } from '../api'
import { Mark, STAGES, STATUS, Shell, btn, fmtTime, type Me } from '../ui'

const Stat = ({ label, children }: { label: string; children: React.ReactNode }) => (
  <div className="flex flex-col gap-2.5 border-r border-b border-line p-6"><span className="font-tc text-[13px] text-graphite">{label}</span>{children}</div>
)
const Big = ({ n, unit, cls = '' }: { n: React.ReactNode; unit?: string; cls?: string }) => (
  <span className={`text-[56px] leading-none font-semibold tracking-[-0.04em] ${cls}`}>{n}{unit && <span className="text-lg text-graphite"> {unit}</span>}</span>
)
const Panel = ({ title, sub, cls = '', children }: { title: string; sub?: string; cls?: string; children: React.ReactNode }) => (
  <section className={`flex flex-col gap-5 border border-line p-6 ${cls}`}>
    <div className="flex items-baseline justify-between gap-3"><h2 className="m-0 font-tc text-base font-bold">{title}</h2>{sub && <span className="font-mono text-xs text-graphite">{sub}</span>}</div>
    {children}
  </section>
)
const Sub = ({ children, top = false }: { children: React.ReactNode; top?: boolean }) => <h3 className={`m-0 font-tc text-sm font-bold ${top ? 'border-t border-line pt-4' : ''}`}>{children}</h3>
// Horizontal bars, largest first (keep = given order, zeros shown). labels: key -> display text.
const HBars = ({ data, labels = {}, color = '#0B0B0D', keep = false }: { data: Record<string, number>; labels?: Record<string, string>; color?: string; keep?: boolean }) => {
  const rows = Object.entries(data).filter(([, n]) => keep || n > 0)
  if (!keep) rows.sort((a, b) => b[1] - a[1])
  const max = Math.max(1, ...rows.map(r => r[1]))
  if (!rows.length) return <span className="font-mono text-xs text-graphite">尚無資料</span>
  return (
    <div className="flex flex-col gap-2">
      {rows.map(([k, n]) => (
        <div key={k} className="grid grid-cols-[minmax(96px,170px)_1fr_44px] items-center gap-3">
          <span className="truncate font-tc text-[13px]" title={k}>{labels[k] ?? k}</span>
          <div className="h-3 bg-line"><div className="h-full" style={{ width: `${(n / max) * 100}%`, background: color }} /></div>
          <span className="text-right font-mono text-xs">{n}</span>
        </div>
      ))}
    </div>
  )
}
// One segmented bar with a legend: [label, count, colour].
const Stack = ({ parts }: { parts: [string, number, string][] }) => {
  const total = parts.reduce((s, p) => s + p[1], 0)
  return (
    <div className="flex flex-col gap-2.5">
      <div className="flex h-3 gap-0.5">{total ? parts.filter(p => p[1] > 0).map(p => <div key={p[0]} style={{ flex: p[1], background: p[2] }} title={`${p[0]} ${p[1]}`} />) : <div className="flex-1 bg-line" />}</div>
      <div className="flex flex-wrap gap-x-4 gap-y-1 font-mono text-xs text-dim">{parts.map(p => <span key={p[0]} className="flex items-center gap-1.5"><Mark shape="square" color={p[2]} size={8} />{p[0]} {p[1]}{total ? ` · ${Math.round((p[1] / total) * 100)}%` : ''}</span>)}</div>
    </div>
  )
}
const Num = ({ label, n, cls = '' }: { label: string; n: React.ReactNode; cls?: string }) => (
  <div className="flex flex-col gap-1"><span className="font-tc text-xs text-graphite">{label}</span><span className={`text-[28px] leading-none font-semibold tracking-[-0.03em] ${cls}`}>{n}</span></div>
)
const Legend = ({ items }: { items: [string, string][] }) => (
  <div className="flex flex-wrap gap-x-4 gap-y-1 font-mono text-xs text-dim">{items.map(([l, c]) => <span key={l} className="flex items-center gap-1.5"><Mark shape="square" color={c} size={8} />{l}</span>)}</div>
)

const KIND: Record<Event['kind'], [string, string]> = { upload: ['上傳', '#0B0B0D'], stage: ['階段', '#A1A1AA'], waiting: ['等待', '#B54708'], done: ['完成', '#0E7C47'], failed: ['失敗', '#C8281E'], single: ['單筆', '#2F4BF0'], web: ['網頁操作', '#60A5FA'], mcp: ['MCP', '#0D9488'], account: ['登入 / 註冊', '#7C3AED'], tour: ['教學', '#D946EF'], cron: ['巡檢', '#71717A'] }
// Same user + same text inside one bucket collapse into one line with a count.
const group = (b: Event[]) => { const m = new Map<string, Event & { n: number }>(); for (const e of b) { const k = e.user + e.text; const g = m.get(k); if (g) g.n++; else m.set(k, { ...e, n: 1 }) } return [...m.values()] }
const hm = (t: number) => { const d = new Date(t * 1000); return `${String(d.getHours()).padStart(2, '0')}:${String(d.getMinutes()).padStart(2, '0')}` }
const N = 72  // buckets on the strip: 5 / 10 / 20 minutes at 6 / 12 / 24 hours

// The activity strip: one column per bucket, one square per event, colour by kind; hover a column for the detail.
function Pulse() {
  const [hours, setHours] = useState(12)
  const [ev, setEv] = useState<Event[] | null>(null)
  const [hov, setHov] = useState<number | null>(null)
  useEffect(() => {
    const load = () => admin.activity(hours).then(setEv).catch(() => setEv([]))
    load(); const id = setInterval(load, 60000); return () => clearInterval(id)
  }, [hours])
  const now = Date.now() / 1000, span = hours * 3600, w = span / N, since = now - span
  const buckets = [...Array(N)].map((_, k) => (ev ?? []).filter(e => e.t >= since + k * w && e.t < since + (k + 1) * w))
  const latest = ev?.slice(-3).reverse() ?? []
  const ticks: number[] = []
  for (let t = Math.ceil(since / 3600) * 3600; t < now; t += 3600) if (new Date(t * 1000).getHours() % (hours / 6) === 0) ticks.push(t)
  const open = hov !== null && buckets[hov].length ? hov : null
  return (
    <section className="flex min-w-0 flex-col gap-4 border border-line p-6">
      <style>{'@keyframes pulse-dot{0%,100%{box-shadow:0 0 0 0 rgba(47,75,240,.55)}70%{box-shadow:0 0 0 7px rgba(47,75,240,0)}}'}</style>
      <div className="flex flex-wrap items-center justify-between gap-2">
        <span className="flex items-baseline gap-3"><h2 className="m-0 font-tc text-base font-bold">最新動態</h2><span className="font-mono text-xs text-graphite">近 {hours} 小時 · {ev?.length ?? '…'} 件</span></span>
        <span className="flex border border-line font-mono text-[11px]">{[6, 12, 24].map(h => <button key={h} type="button" onClick={() => { setHours(h); setHov(null) }} className={`min-h-6 cursor-pointer border-0 px-2 py-0.5 ${h === hours ? 'bg-ink text-white' : 'bg-white text-dim'}`}>{h}h</button>)}</span>
      </div>
      {latest.length
        ? <div className="flex flex-col gap-1.5">{latest.map((e, i) => <div key={i} className={`flex min-w-0 items-baseline gap-2.5 ${i ? 'text-graphite' : ''}`}><span className="font-mono text-xs text-graphite">{hm(e.t)}</span><Mark shape="square" color={KIND[e.kind][1]} size={8} className="shrink-0 self-center" /><span className={`truncate font-tc ${i ? 'text-sm' : 'text-[15px] font-semibold'}`} title={e.text}><span className="font-sans">{e.user}</span> {e.text}</span></div>)}</div>
        : <span className="font-tc text-[15px] text-dim">{ev ? '這段時間沒有動靜' : '載入中…'}</span>}
      <div className="relative" onMouseLeave={() => setHov(null)}>
        <div className="relative flex h-40 items-end gap-px border-b border-ink">
          {buckets.map((b, k) => (
            <div key={k} onMouseEnter={() => setHov(k)} onClick={() => setHov(hov === k ? null : k)} className={`flex h-full flex-1 cursor-crosshair flex-col-reverse items-center gap-px pb-px ${k === hov ? 'bg-mist' : ''}`}>
              {b.slice(0, 14).map((e, j) => <span key={j} className="block h-2.5 w-full max-w-3" style={{ background: KIND[e.kind][1] }} />)}
              {b.length > 14 && <span className="font-mono text-[9px] leading-none text-graphite">+{b.length - 14}</span>}
            </div>
          ))}
          <span className="absolute -right-1 -bottom-1 size-2 rounded-full bg-signal" style={{ animation: 'pulse-dot 2s ease-out infinite' }} title="現在" />
        </div>
        <div className="relative h-4">{ticks.map(t => <span key={t} className="absolute -translate-x-1/2 font-mono text-[10px] text-graphite" style={{ left: `${((t - since) / span) * 100}%` }}>{hm(t)}</span>)}</div>
        {open !== null && (
          <div className={`absolute bottom-full z-10 mb-2 w-[300px] max-w-full border border-ink bg-white p-3 text-xs shadow-[4px_4px_0_#0B0B0D] ${open < N / 2 ? 'left-0' : 'right-0'}`} style={open < N / 2 ? { left: `${(open / N) * 100}%` } : { right: `${((N - open - 1) / N) * 100}%` }}>
            <div className="mb-2 flex justify-between font-mono text-graphite"><span>{hm(since + open * w)}–{hm(since + (open + 1) * w)}</span><span>{buckets[open].length} 件</span></div>
            <ul className="m-0 flex list-none flex-col gap-1 p-0">
              {group(buckets[open]).slice(-8).map((e, j) => <li key={j} className="flex items-start gap-2"><span className="shrink-0 font-mono text-graphite">{hm(e.t)}</span><Mark shape="square" color={KIND[e.kind][1]} size={8} className="mt-1 shrink-0" /><span className="min-w-0 font-tc"><span className="font-sans font-semibold">{e.user}</span> {e.job ? <a href={`#/jobs/${e.job}`} className="text-ink">{e.text}</a> : e.text}{e.n > 1 && <span className="font-mono text-graphite"> ×{e.n}</span>}</span></li>)}
              {group(buckets[open]).length > 8 && <li className="font-mono text-graphite">…還有 {group(buckets[open]).length - 8} 種</li>}
            </ul>
          </div>
        )}
      </div>
      <div className="flex flex-wrap gap-x-3 gap-y-1 font-mono text-[11px] text-dim">{Object.entries(KIND).map(([k, [l, c]]) => <span key={k} className="flex items-center gap-1"><Mark shape="square" color={c} size={7} />{l}</span>)}</div>
    </section>
  )
}

const th = 'px-2 py-3 font-medium'
const td = 'px-2 py-3.5'
const TOUR: Record<string, string> = { '': '未開始', settings: '設定', lookup: '單筆查詢', work: '工作台', done: '完成' }
const MODE: Record<string, string> = { smart: '智慧', fix: '只修訂', add: '只新增' }
const STAGE = Object.fromEntries(STAGES)
const ASK: Record<string, string> = { no_heading: '找不到標題', empty: '標題下沒內容', no_labels: '沒有 [n] 編號', blob: '擠在同一段' }
const BLOCK: Record<string, string> = { picked: '勾選段落', typed: '手動整理 / 初排', append: '文末新增' }
const ITEM: Record<string, string> = { fix: '原有條目', add: '新增書目', duplicate: '重複（已略過）', skipped: '使用者跳過', kept: '保留原文', uncertain: '完成時仍不確定', with_issues: '套格式有附註', check_failed: '審查未通過', error: '套格式失敗' }
const TYPE: Record<string, string> = { journal: '期刊', conference: '會議', book: '書籍', chapter: '書章', thesis: '學位論文', web: '網頁', arxiv: 'arXiv', other: '其他', unknown: '未判定' }
const TASK: Record<string, string> = { lookup: '查書目中', format: '套格式中', check: '審查中', done: '完成', failed: '失敗' }
const C = { ok: '#0E7C47', fail: '#C8281E', wait: '#B54708', signal: '#2F4BF0', ink: '#0B0B0D', faint: '#D4D4D8' }
const dayKey = (d: Date) => `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}-${String(d.getDate()).padStart(2, '0')}`
const EMPTY = { jobs: 0, done: 0, failed: 0, entries: 0, refs: 0 }
const sum = (o: Record<string, number>) => Object.values(o).reduce((a, b) => a + b, 0)

export default function Admin({ me }: { me: Me }) {
  const [stats, setStats] = useState<Stats | null>(null)
  const [list, setList] = useState<JobSummary[]>([])
  const [err, setErr] = useState('')
  const reload = () => admin.stats().then(setStats).catch(x => setErr((x as Error).message))
  useEffect(() => { reload(); admin.jobs().then(setList).catch(() => {}) }, [])  // eslint-disable-line react-hooks/exhaustive-deps
  if (err) return <Shell me={me} active="admin"><p className="font-mono text-fail">{err}</p></Shell>
  if (!stats) return <Shell me={me} active="admin"><p className="font-tc text-dim">載入中…</p></Shell>

  const days = [...Array(30)].map((_, i) => { const d = new Date(); d.setDate(d.getDate() - 29 + i); return { label: `${d.getMonth() + 1}/${d.getDate()}`, ...(stats.per_day[dayKey(d)] || EMPTY) } })
  const dayMax = Math.max(1, ...days.map(d => d.jobs + d.refs))
  const hourMax = Math.max(1, ...stats.hours)
  const models = Object.entries(stats.models).sort((a, b) => b[1] - a[1])
  const modelTotal = models.reduce((s, m) => s + m[1], 0)
  const lk = stats.lookup
  const it = stats.items
  const sr = stats.single_refs
  const jobsTotal = sum(stats.jobs)
  const failed = stats.jobs.failed
  const pct = (a: number, b: number) => b ? `${Math.round((a / b) * 100)}%` : '—'

  return (
    <Shell me={me} active="admin">
      <div className="flex flex-col gap-12">
        <div className="flex flex-col gap-1.5"><div className="font-mono text-xs tracking-[0.12em] text-graphite">OVERVIEW</div><h1 className="m-0 font-tc text-[32px] font-bold">全站統計</h1></div>

        <div className="grid grid-cols-[repeat(auto-fit,minmax(200px,1fr))] border-t border-l border-t-ink border-l-line">
          <Stat label="使用者"><Big n={stats.users} /></Stat>
          <Stat label="工作"><Big n={jobsTotal} />
            <span className="flex flex-wrap gap-3 font-mono text-xs text-dim">
              <span className="flex items-center gap-1.5"><Mark shape="square" color={C.ok} size={8} />{stats.jobs.done} done</span>
              <span className="flex items-center gap-1.5"><Mark shape="ring" color={C.fail} size={8} />{stats.jobs.failed} failed</span>
              <span>{stats.jobs.running + stats.jobs.queued} running</span><span>{stats.jobs.waiting} waiting</span>
            </span></Stat>
          <Stat label="處理條目"><Big n={stats.entries} /></Stat>
          <Stat label="修訂總筆數"><Big n={stats.changed} /></Stat>
          <Stat label="平均耗時"><Big n={stats.avg_seconds ?? '—'} unit="秒" /></Stat>
          <Stat label="審查一次通過率"><Big cls="text-signal" n={stats.check_pass_rate == null ? '—' : <>{Math.round(stats.check_pass_rate * 100)}<span className="text-[22px]">%</span></>} /></Stat>
          <Stat label="單筆產生 / 審查通過"><span className="text-[40px] leading-tight font-semibold tracking-[-0.03em]">{sr.total}<span className="text-faint"> / </span><span className="text-ok">{sr.check_ok}</span></span></Stat>
          <Stat label="工作失敗率"><Big cls={failed ? 'text-fail' : ''} n={jobsTotal ? <>{Math.round((failed / jobsTotal) * 100)}<span className="text-[22px]">%</span></> : '—'} /></Stat>
          <div className="flex min-w-0 flex-col gap-2.5 border-r border-b border-line p-6 lg:[grid-column:3/-1]">
          <span className="font-tc text-[13px] text-graphite">每日活動 · 近 30 天 · 工作依結果分色，單筆查詢另計</span>
          <div className="flex h-16 items-end gap-1 border-b border-ink">
            {days.map((d, i) => { const n = d.jobs + d.refs; const active = d.jobs - d.done - d.failed; return (
              <div key={i} className="flex h-full flex-1 flex-col items-center justify-end gap-1" title={`${d.label}：${d.jobs} 件工作（完成 ${d.done}、失敗 ${d.failed}）、${d.entries} 條目、單筆 ${d.refs}`}>
                <div className="flex w-full flex-col-reverse" style={{ height: Math.max(2, Math.round((n / dayMax) * 60)) }}>
                  {n === 0 && <div className="h-full bg-line" />}
                  {d.done > 0 && <div style={{ flex: d.done, background: C.ok }} />}
                  {d.failed > 0 && <div style={{ flex: d.failed, background: C.fail }} />}
                  {active > 0 && <div style={{ flex: active, background: C.wait }} />}
                  {d.refs > 0 && <div style={{ flex: d.refs, background: C.signal }} />}
                </div>
              </div>) })}
          </div>
          <div className="flex gap-1">{days.map((d, i) => <span key={i} className="flex-1 text-center font-mono text-[10px] text-graphite">{i % 5 === 4 || i === 0 ? d.label : ''}</span>)}</div>
          <Legend items={[['完成', C.ok], ['失敗', C.fail], ['進行中 / 等待', C.wait], ['單筆查詢', C.signal]]} />
          </div>
        </div>

        <Pulse />

        <div className="grid grid-cols-[repeat(auto-fit,minmax(320px,1fr))] gap-6">
          <Panel title="工作組成" sub={`${jobsTotal} 件`}>
            <Stack parts={[['智慧', stats.modes.smart, C.ink], ['只修訂', stats.modes.fix, C.signal], ['只新增', stats.modes.add, C.wait]]} />
            <Stack parts={[['有預覽確認', stats.review.on, C.ink], ['直接跑完', stats.review.off, C.faint]]} />
            <div className="grid grid-cols-3 gap-4 border-t border-line pt-4">
              {(['smart', 'fix', 'add'] as const).map(m => <Num key={m} label={`${MODE[m]}平均耗時`} n={stats.seconds_by_mode[m] == null ? '—' : `${stats.seconds_by_mode[m]}s`} />)}
            </div>
          </Panel>

          <Panel title="每日巡檢" sub={stats.cron.ping.t ? `上次 ${fmtTime(stats.cron.ping.t)}` : '還沒跑過'}>
            <Sub>向外 API 存活信號（每天一次）</Sub>
            <div className="grid grid-cols-2 gap-4">
              {(['openalex', 'semanticscholar'] as const).map(a => { const r = stats.cron.ping.apis[a]; return <Num key={a} label={a} n={r == null ? '—' : r === 'ok' ? 'OK' : `失敗 ${r}`} cls={r == null ? '' : r === 'ok' ? 'text-ok' : 'text-fail'} /> })}
            </div>
            <Sub top>文件留存 {stats.cron.retain_days} 天</Sub>
            <div className="grid grid-cols-2 gap-4">
              <Num label="已清除檔案的工作" n={stats.cron.expired} />
              <Num label="上次清除" n={stats.cron.purge ? `${fmtTime(stats.cron.purge.t)} · ${stats.cron.purge.n} 份` : '—'} />
            </div>
          </Panel>

          <Panel title="失敗分析" sub={`${failed} 件失敗`}>
            <Sub>停在哪個階段</Sub>
            <HBars data={stats.failures.by_stage} labels={{ ...STAGE, queued: '尚未開始' }} color={C.fail} />
            <Sub top>錯誤類型</Sub>
            <HBars data={stats.failures.errors} color={C.fail} />
          </Panel>

          <Panel title="讀取條目：停下來問的情況" sub={`${sum(stats.asks)} 件待答`}>
            <Sub>目前在等回答的原因</Sub>
            <HBars data={stats.asks} labels={ASK} color={C.wait} />
            <Sub top>使用者怎麼回答</Sub>
            <HBars data={stats.blocks} labels={BLOCK} />
          </Panel>

          <Panel title="條目處理" sub={`${stats.entries} 筆`}>
            <HBars data={it} labels={ITEM} keep />
            <div className="grid grid-cols-3 gap-4 border-t border-line pt-4">
              <Num label="修訂比例" n={pct(stats.changed, stats.entries)} />
              <Num label="審查未通過" n={pct(it.check_failed, stats.entries)} cls={it.check_failed ? 'text-fail' : ''} />
              <Num label="有附註待補" n={pct(it.with_issues, stats.entries)} cls={it.with_issues ? 'text-wait' : ''} />
            </div>
          </Panel>

          <Panel title="書目查詢" sub={`快取 ${stats.cache} 筆`}>
            <Sub>命中率（已完成的工作）</Sub>
            <Stack parts={[['exact', lk.exact, C.ink], ['fuzzy', lk.fuzzy, C.wait], ['none', lk.none, C.faint]]} />
            <Sub top>資料來源</Sub>
            <HBars data={stats.sources} color={C.signal} />
          </Panel>

          <Panel title="文獻類型" sub="LLM 判定">
            <Sub>工作台條目</Sub>
            <HBars data={stats.types} labels={TYPE} />
            <Sub top>單筆查詢</Sub>
            <HBars data={sr.types} labels={TYPE} color={C.signal} />
          </Panel>

          <Panel title="引用順序修正" sub="已完成的工作">
            <div className="grid grid-cols-2 gap-5">
              <Num label="需要重排的工作" n={stats.order.jobs_reordered} />
              <Num label="改號的條目" n={stats.order.renumbered} />
              <Num label="解析的佔位符" n={stats.order.placeholders} />
              <Num label="本文引用找不到條目" n={stats.order.unknown} cls={stats.order.unknown ? 'text-fail' : ''} />
            </div>
          </Panel>

          <Panel title="單筆工具" sub={`${sr.total} 筆`}>
            <Stack parts={[['審查通過', sr.check_ok, C.ok], ['未通過', sr.total - sr.check_ok, C.fail]]} />
            <Sub top>任務狀態</Sub>
            <HBars data={sr.tasks} labels={TASK} color={C.signal} />
          </Panel>

          <Panel title="操作來源" sub={`登入 ${stats.api.logins} 次`}>
            <Stack parts={[['網頁', stats.api.via.web ?? 0, C.ink], ['curl', stats.api.via.cli ?? 0, C.wait], ['MCP', stats.api.via.mcp ?? 0, '#0D9488']]} />
            <Sub top>網頁 / curl 做了什麼</Sub>
            <HBars data={stats.api.web} color="#60A5FA" />
            <Sub top>教學走到</Sub>
            <HBars data={stats.api.tours} color="#D946EF" />
          </Panel>

          <Panel title="MCP 工具呼叫" sub={`${sum(stats.api.mcp)} 次`}>
            <HBars data={stats.api.mcp} color="#0D9488" />
            <Sub top>各帳號：網頁 vs MCP</Sub>
            <div className="flex flex-col gap-2">
              {Object.entries(stats.api.by_user).map(([u, n]) => <div key={u} className="grid grid-cols-[minmax(96px,170px)_1fr_80px] items-center gap-3"><span className="truncate font-sans text-[13px] font-semibold">{u}</span><div className="flex h-3 gap-0.5">{n.web > 0 && <div style={{ flex: n.web, background: C.ink }} />}{n.mcp > 0 && <div style={{ flex: n.mcp, background: '#0D9488' }} />}{!n.web && !n.mcp && <div className="flex-1 bg-line" />}</div><span className="text-right font-mono text-xs">{n.web} / {n.mcp}</span></div>)}
              {!Object.keys(stats.api.by_user).length && <span className="font-mono text-xs text-graphite">尚無資料</span>}
            </div>
          </Panel>

          <Panel title="分享" sub={`${stats.shares.total} 個分享連結`}>
            <div className="grid grid-cols-2 gap-4">
              <Num label="分享連結" n={stats.shares.total} />
              <Num label="分享頁被看了" n={stats.shares.views} cls="text-signal" />
            </div>
            <Sub top>分享動作</Sub>
            <HBars data={stats.shares.hits} color={C.signal} />
          </Panel>

          <Panel title="時段分布" sub="工作建立的小時 · 伺服器時區">
            <div className="flex h-[120px] items-end gap-0.5 border-b border-ink">
              {stats.hours.map((n, h) => <div key={h} className="flex-1" title={`${h}:00 — ${n} 件`} style={{ height: Math.max(2, Math.round((n / hourMax) * 110)), background: n ? C.ink : C.faint }} />)}
            </div>
            <div className="flex gap-0.5">{stats.hours.map((_, h) => <span key={h} className="flex-1 text-center font-mono text-[10px] text-graphite">{h % 6 === 0 ? h : ''}</span>)}</div>
          </Panel>

          <Panel title="模型使用分布">
            <div className="flex items-center gap-6">
              <div className="flex h-[120px] w-[120px] flex-none items-center justify-center rounded-full border-[18px] border-ink"><span className="text-xl font-semibold">{modelTotal}</span></div>
              <div className="flex min-w-0 flex-col gap-1.5">
                {models.map(([m, n]) => <span key={m} className="flex flex-col font-mono text-xs"><span className="flex items-center gap-2 break-all"><Mark shape="square" color={C.ink} size={8} />{m}</span><span className="pl-4 text-graphite">{n} 次 · {Math.round((n / modelTotal) * 100)}%</span></span>)}
                {!models.length && <span className="font-mono text-xs text-graphite">尚無資料</span>}
              </div>
            </div>
          </Panel>
        </div>

        <section className="flex flex-col gap-4">
          <h2 className="m-0 font-tc text-xl font-bold">使用者</h2>
          <div className="overflow-x-auto"><table className="w-full min-w-[860px] border-collapse text-sm">
            <thead><tr className="border-t border-b border-t-ink border-b-line text-left font-tc text-xs text-graphite"><th className={th}>帳號</th><th className={th}>註冊時間</th><th className={th}>教學</th><th className={`${th} text-right`}>工作數</th><th className={`${th} text-right`}>失敗</th><th className={`${th} text-right`}>條目數</th><th className={`${th} text-right`}>修訂數</th><th className={`${th} text-right`}>單筆</th><th className={th}>最後活動</th></tr></thead>
            <tbody className="font-mono text-[13px]">
              {stats.per_user.map(u => (
                <tr key={u.username} className="border-b border-line"><td className={`${td} font-sans text-[15px] font-semibold`}>{u.username}</td><td className={td}>{u.created ? fmtTime(u.created) : '—'}</td><td className={`${td} whitespace-nowrap`}>{TOUR[u.tour || ''] || u.tour}{u.tour !== 'settings' && <button type="button" className={`${btn.ghost} ml-2 min-h-7 px-2 text-xs`} onClick={() => admin.tour(u.username, 'settings').then(reload)}>重設</button>}</td><td className={`${td} text-right`}>{u.jobs}</td><td className={`${td} text-right ${u.failed ? 'text-fail' : ''}`}>{u.failed}</td><td className={`${td} text-right`}>{u.entries}</td><td className={`${td} text-right`}>{u.changed}</td><td className={`${td} text-right`}>{u.refs}</td><td className={td}>{u.last_active ? fmtTime(u.last_active) : '—'}</td></tr>
              ))}
            </tbody></table></div>
        </section>

        <section className="flex flex-col gap-4">
          <h2 className="m-0 font-tc text-xl font-bold">所有工作</h2>
          <div className="overflow-x-auto"><table className="w-full min-w-[960px] border-collapse text-sm">
            <thead><tr className="border-t border-b border-t-ink border-b-line text-left font-tc text-xs text-graphite"><th className={th}>使用者</th><th className={th}>檔名</th><th className={th}>模式</th><th className={th}>狀態</th><th className={`${th} text-right`}>進度</th><th className={th}>建立時間</th><th className={`${th} text-right`}>耗時</th><th className={`${th} text-right`}>條目</th><th className={`${th} text-right`}>修訂</th><th className={th}></th></tr></thead>
            <tbody className="font-mono text-[13px]">
              {list.map(j => { const s = STATUS[j.status]; return (
                <tr key={j.id} className="border-b border-line"><td className={`${td} font-sans font-semibold`}>{j.user}</td><td className={`${td} font-sans`}>{j.filename}</td><td className={td}>{j.mode}</td>
                  <td className={td}><span className="flex items-center gap-1.5" style={{ color: s.color }}><Mark shape={s.shape} color={s.color} size={8} />{j.status}{j.ask ? '（待答）' : ''}{j.expired ? '（已過期）' : ''}</span></td>
                  <td className={`${td} text-right`}>{j.status === 'failed' ? '—' : `${Math.round(j.percent)}%`}</td><td className={td}>{fmtTime(j.started)}</td><td className={`${td} text-right`}>{j.elapsed.toFixed(1)}s</td><td className={`${td} text-right`}>{j.entries}</td><td className={`${td} text-right`}>{j.changed ?? 0}</td>
                  <td className={`${td} text-right`}><a href={`#/jobs/${j.id}`} className="font-tc">詳情 →</a></td></tr>) })}
              {!list.length && <tr><td colSpan={10} className="px-2 py-8 text-center font-tc text-[13px] text-dim">還沒有工作</td></tr>}
            </tbody></table></div>
        </section>
      </div>
    </Shell>
  )
}
