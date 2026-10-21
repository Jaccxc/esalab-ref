import { useState, type ReactNode } from 'react'
import { jobs, type Item, type JobState } from '../api'
import { Doi, Mark, MatchTag, STAGES, Shell, Tag, fmtDur, fmtTime, type Me, type Shape } from '../ui'
import { useJob } from '../useJob'
import { ShareDialog } from './Share'

// `*text*` from the formatter is italic (the docx writer does the same mapping).
export const Ref = ({ text }: { text: string }) => <>{text.split(/(\*[^*]+\*)/).map((p, i) => p.startsWith('*') && p.endsWith('*') && p.length > 2 ? <em key={i}>{p.slice(1, -1)}</em> : p)}</>

// Word-level diff (italic spans kept whole, so a journal name stays one token): what the formatter changed in one line.
const TOK = /\*[^*]+\*|[^\s*]+|\*|\s+/g
type Seg = { k: 'eq' | 'del' | 'ins'; text: string }
// Same canon as the backend's norm_marks: NFC accents, split italic runs merged, spaces / trailing punctuation outside *...*.
const norm = (s: string) => s.normalize('NFC').replace(/\*(\s+)\*/g, '$1').replace(/\*(\s*)([^*]*?)([\s,;:]*)\*/g, '$1*$2*$3')
const tokenDiff = (a: string, b: string): Seg[] => {
  const A = norm(a).match(TOK) ?? [], B = norm(b).match(TOK) ?? [], n = A.length, m = B.length
  const L: number[][] = Array.from({ length: n + 1 }, () => new Array<number>(m + 1).fill(0))
  for (let i = n - 1; i >= 0; i--) for (let j = m - 1; j >= 0; j--) L[i][j] = A[i] === B[j] ? L[i + 1][j + 1] + 1 : Math.max(L[i + 1][j], L[i][j + 1])
  const out: Seg[] = []
  const push = (k: Seg['k'], text: string) => { const last = out[out.length - 1]; if (last && last.k === k) last.text += text; else out.push({ k, text }) }
  for (let i = 0, j = 0; i < n || j < m;) {
    if (i < n && j < m && A[i] === B[j]) { push('eq', A[i]); i++; j++ }
    else if (i < n && (j >= m || L[i + 1][j] >= L[i][j + 1])) { push('del', A[i]); i++ }
    else { push('ins', B[j]); j++ }
  }
  return out
}
const Diff = ({ a, b }: { a: string; b: string }) => <>{tokenDiff(a, b).map((s, i) => s.k === 'eq' ? <Ref key={i} text={s.text} /> : s.k === 'del' ? <del key={i}><Ref text={s.text} /></del> : <ins key={i}><Ref text={s.text} /></ins>)}</>

const label = (it: Item) => it.kind === 'fix' ? `[${it.number}]` : `[+${it.line}]`
const finalLabel = (it: Item) => {
  if (it.status === 'duplicate') return label(it)
  return it.number_final && it.number_final !== it.number ? `${label(it)} → [${it.number_final}]` : label(it)
}

export default function JobDetail({ me, id }: { me: Me; id: string }) {
  const { job, err } = useJob(id)
  const [sharing, setSharing] = useState(false)
  if (err) return <Shell me={me} active="work"><p className="font-mono text-fail">{err}</p></Shell>
  if (!job) return <Shell me={me} active="work"><p className="font-tc text-dim">載入中…</p></Shell>
  return (
    <Shell me={me} active="work">
      <JobBody job={job} id={id} onShare={() => setSharing(true)} />
      {job.status === 'done' && <ShareDialog id={id} open={sharing} onClose={() => setSharing(false)} />}
    </Shell>
  )
}

// The page body; without onShare it is the public shared copy (no back link, no download, no share button).
export function JobBody({ job, id, onShare }: { job: JobState; id: string; onShare?: () => void }) {
  const [onlyChanged, setOnlyChanged] = useState(false)
  const shared = !onShare
  const st = job.status
  const adds = job.items.filter(i => i.kind === 'add').length
  const fixes = job.items.length - adds
  const pct = st === 'done' ? '100' : job.percent.toFixed(1)
  const [pi, pd] = pct.split('.')
  const curIdx = STAGES.findIndex(s => s[0] === job.stage)
  const barColor = { running: '#2F4BF0', queued: '#2F4BF0', waiting: '#FDB022', done: '#32D583', failed: '#F97066' }[st]
  const plan = job.order
  const shown = job.items.filter(it => !onlyChanged || it.changed)

  return (
      <div className="flex flex-col gap-10">
        <div className="flex flex-col gap-3">
          {!shared && <a href="#/" className="flex min-h-8 items-center self-start font-tc text-sm text-dim no-underline">← 回工作台</a>}
          <div className="flex flex-wrap items-baseline gap-x-5 gap-y-3">
            <h1 className="m-0 text-4xl font-semibold tracking-tight">{job.filename}</h1>
            <Tag>{job.mode}</Tag>
            <span className="bg-mist px-2 py-0.5 font-tc text-xs text-dim">{job.review ? '人工確認：開' : '跳過人工確認'}</span>
            <span className="font-mono text-[13px] text-graphite">建立 {fmtTime(job.started)} · 修訂作者 {job.author} · {fixes} 條{adds ? ` + ${adds} 筆新書目` : ''}</span>
          </div>
        </div>

        <section className="flex flex-col gap-9 bg-ink p-10 text-white">
          <div className="flex flex-wrap items-end gap-x-12 gap-y-6">
            <div className="flex items-baseline gap-1.5">
              <span className="text-[120px] leading-[0.85] font-semibold tracking-[-0.05em]">{pi}</span>
              <span className="text-[40px] font-medium text-faint">{pd ? `.${pd}` : ''}%</span>
            </div>
            <div className="flex flex-[1_1_320px] flex-col gap-3 pb-1.5">
              {(st === 'running' || st === 'queued') && <>
                <div className="flex flex-wrap gap-x-8 gap-y-2 font-mono text-sm">
                  <span><span className="text-[#8A8A93]">已用</span> {fmtDur(job.elapsed)}</span>
                  <span><span className="text-[#8A8A93]">剩餘</span> {job.eta_seconds != null ? `約 ${Math.max(1, Math.round(job.eta_seconds / 60))} 分` : '估算中'}</span>
                  {job.stage_total > 0 && <span><span className="text-[#8A8A93]">目前</span> 第 {job.stage_done} / {job.stage_total} 筆</span>}
                </div>
                <p className="m-0 font-tc text-sm text-faint">免費模型 20 筆左右約需 5–8 分鐘。可以關閉頁面，稍後從紀錄回來看。</p>
              </>}
              {st === 'waiting' && job.ask && <>
                <div className="flex items-center gap-2.5 font-tc text-xl font-bold text-[#FDB022]"><Mark shape="circle" color="#FDB022" size={12} />等你指出參考文獻在哪</div>
                <p className="m-0 font-tc text-sm leading-relaxed text-edge">讀不出「一筆一段、開頭 [n]」的清單。勾出屬於清單的段落，或貼成一行一筆，系統會加上編號再繼續查書目。</p>
                <a href={`#/jobs/${id}/block`} className="btn flex min-h-13 items-center gap-3.5 self-start bg-[#FDB022] hover:bg-[#F0A010] px-5.5 font-tc text-base font-bold text-[#1C1003] no-underline">去指出清單 <span aria-hidden="true">→</span></a>
              </>}
              {st === 'waiting' && !job.ask && <>
                <div className="flex items-center gap-2.5 font-tc text-xl font-bold text-[#FDB022]"><Mark shape="circle" color="#FDB022" size={12} />等你預覽確認</div>
                <p className="m-0 font-tc text-sm leading-relaxed text-edge">查到 {job.items.length} 筆論文，其中 {job.items.filter(i => i.uncertain).length} 筆需要你看一下。確認後工作會接著核對順序與套格式。</p>
                <a href={`#/jobs/${id}/preview`} className="btn flex min-h-13 items-center gap-3.5 self-start bg-[#FDB022] hover:bg-[#F0A010] px-5.5 font-tc text-base font-bold text-[#1C1003] no-underline">前往預覽確認 <span aria-hidden="true">→</span></a>
              </>}
              {st === 'done' && <div className="flex flex-wrap items-center gap-4">
                {!shared && !job.expired && <a href={jobs.resultUrl(id)} className="flex min-h-14 items-center gap-3.5 bg-white px-6 font-tc text-base font-bold text-ink no-underline">下載修訂後的 .docx <span aria-hidden="true">↓</span></a>}
                {!shared && job.expired && <span className="font-tc text-sm text-[#8A8A93]">檔案已超過 30 天，已清除</span>}
                {onShare && <button type="button" onClick={onShare} className="btn flex min-h-14 cursor-pointer items-center gap-3.5 border border-white bg-transparent px-6 font-tc text-base font-bold text-white">分享 <span aria-hidden="true">↗</span></button>}
                <span className="flex items-center gap-2.5 font-tc text-base"><Mark shape="square" color="#32D583" size={12} />完成 · {job.changed ?? 0} 筆修訂 · 耗時 {fmtDur(job.elapsed)}</span>
              </div>}
              {st === 'failed' && <>
                <div className="flex items-center gap-2.5 font-tc text-lg font-bold text-[#F97066]"><Mark shape="ring" color="#F97066" size={12} />失敗</div>
                <p className="m-0 font-mono text-[13px] text-[#FDA29B]">{job.error}</p>
              </>}
            </div>
          </div>
          <div className="h-1 bg-[#27272A]"><div className="h-1" style={{ width: `${st === 'done' ? 100 : job.percent}%`, background: barColor }} /></div>
          <ol className="m-0 grid list-none grid-cols-[repeat(auto-fit,minmax(130px,1fr))] gap-x-4 gap-y-5 p-0">
            {STAGES.map(([key, name], i) => {
              const skipped = key === 'review' && !job.review
              const done = st === 'done' || i < curIdx || (i === curIdx && st !== 'running' && st !== 'waiting' && st !== 'failed')
              const cur = i === curIdx && !done && !skipped
              let shape: Shape = 'ring', color = '#3F3F46', text = 'text-graphite', sub = '—'
              if (done) { shape = 'square'; color = '#FFFFFF'; text = 'text-white'; sub = '完成' }
              if (cur) { text = 'text-white'; ({ shape, color, sub } = st === 'waiting' ? { shape: 'circle', color: '#FDB022', sub: '等待確認' } : st === 'failed' ? { shape: 'ring', color: '#F97066', sub: '中斷' } : { shape: 'tri', color: '#2F4BF0', sub: job.stage_total ? `第 ${job.stage_done} / ${job.stage_total} 筆` : '進行中' }) }
              return (
                <li key={key} className="flex min-w-0 flex-col gap-2.5">
                  {skipped ? <span className="my-[7px] h-0.5 w-4 bg-graphite" aria-hidden="true" /> : <Mark shape={shape} color={color} size={16} />}
                  <span className="font-mono text-[11px] tracking-[0.1em] text-graphite">0{i + 1}</span>
                  <span className={`font-tc text-[15px] font-medium ${skipped ? 'text-[#8A8A93] line-through' : text}`}>{name}</span>
                  <span className="font-mono text-xs text-[#8A8A93]">{skipped ? '已略過' : sub}</span>
                </li>
              )
            })}
          </ol>
        </section>

        {plan && (
          <section className="flex flex-col gap-5">
            <div className="flex flex-wrap items-end gap-x-5 gap-y-3">
              <div className="flex flex-col gap-1.5"><div className="font-mono text-xs tracking-[0.12em] text-graphite">CITATION ORDER</div><h2 className="m-0 font-tc text-2xl font-bold">引用順序</h2></div>
              {plan.ok
                ? <span className="flex items-center gap-2 bg-[#E6F4EC] px-3 py-1.5 font-tc text-sm font-bold text-[#0A6639]"><Mark shape="square" color="#0E7C47" />順序正確，內文不需改動</span>
                : <span className="flex items-center gap-2 bg-[#FFF4E5] px-3 py-1.5 font-tc text-sm font-bold text-[#93370D]"><Mark shape="circle" color="#B54708" />順序不正確 · 已以 Word 修訂重新編號</span>}
              <span className="font-tc text-[13px] text-graphite">IEEE：依內文第一次出現的順序編號，清單跟著排。</span>
            </div>
            <div className="grid grid-cols-[repeat(auto-fit,minmax(280px,1fr))] gap-4">
              {Object.keys(plan.renumber).length > 0 && <Card title="重新編號">{Object.entries(plan.renumber).slice(0, 12).map(([a, b]) => <span key={a}><span className="text-faint">[{a}]</span> → [{b}]</span>)}
                {Object.keys(plan.renumber).length > 12 && <span className="font-tc text-xs text-graphite">…共 {Object.keys(plan.renumber).length} 筆</span>}</Card>}
              {Object.keys(plan.placeholders).length > 0 && <Card title="佔位符" cls="border-signal" titleCls="text-signal">{Object.entries(plan.placeholders).map(([a, b]) => <span key={a}><span className="text-faint">[{a}]</span> → [{b}]</span>)}</Card>}
              {plan.uncited.length > 0 && <Card title="警告 · 內文沒引用到" cls="border-[#F5C99B] bg-[#FFFBF5]" titleCls="text-[#93370D]" mark={<Mark shape="circle" color="#B54708" />}>
                <span>{plan.uncited.map(n => { const f = typeof n === 'string' ? plan.placeholders[n] : plan.renumber[n]; return f ? `[${n}]→[${f}]` : `[${n}]` }).join('  ')}</span><span className="font-tc text-[13px] leading-relaxed text-dim">清單有，但內文沒有引用。保留在清單，請確認要刪除或在內文補上引用。</span></Card>}
              {plan.unknown.length > 0 && <Card title="錯誤 · 清單裡沒有" cls="border-[#F3B4AF] bg-[#FFFBFA]" titleCls="text-[#9F1F17]" mark={<Mark shape="ring" color="#C8281E" />}>
                <span>{plan.unknown.map(n => `[${n}]`).join(' ')}</span><span className="font-tc text-[13px] leading-relaxed text-dim">內文引用了這個編號，但清單沒有。系統不會自動處理，請手動修正。</span></Card>}
            </div>
          </section>
        )}

        <section className="flex flex-col gap-4">
          <div className="flex flex-wrap items-end gap-4">
            <div className="flex flex-col gap-1.5"><div className="font-mono text-xs tracking-[0.12em] text-graphite">ENTRIES · {job.items.length}</div><h2 className="m-0 font-tc text-2xl font-bold">條目比對</h2></div>
            <div className="ml-auto flex items-center gap-4 font-tc text-xs text-dim">
              <span><del>刪除</del></span><span><ins>新增</ins></span>
              <label className="flex cursor-pointer items-center gap-1.5"><input type="checkbox" checked={onlyChanged} onChange={e => setOnlyChanged(e.target.checked)} className="accent-ink" />只看有變更的</label>
            </div>
          </div>
          <div className="overflow-x-auto border-t border-ink">
            <div className="min-w-[1180px]">
              <div className="grid grid-cols-[88px_minmax(0,3fr)_190px_minmax(0,3fr)_170px_56px] gap-5 border-b border-line px-1 py-3 font-tc text-xs font-medium text-graphite">
                <span>[n] → 最終</span><span>原始條目</span><span>書目查詢</span><span>格式化結果</span><span>審查</span><span>變更</span>
              </div>
              {shown.map((it, i) => <Row key={i} it={it} job={job} />)}
              {!shown.length && <p className="py-8 text-center font-tc text-[13px] text-dim">沒有符合的條目</p>}
            </div>
          </div>
        </section>

        <details className="border-t border-line pt-2">
          <summary className="flex min-h-11 cursor-pointer items-center font-tc text-[15px] font-medium">紀錄 log <span className="ml-2.5 font-mono text-xs text-graphite">{job.log.length} 行</span></summary>
          <pre className="mt-2 mb-0 overflow-x-auto bg-ink p-5 font-mono text-[13px] leading-[1.8] text-edge">{job.log.join('\n')}</pre>
        </details>
      </div>
  )
}

const Card = ({ title, cls = 'border-line', titleCls = '', mark, children }: { title: string; cls?: string; titleCls?: string; mark?: ReactNode; children: ReactNode }) => (
  <div className={`flex flex-col gap-3.5 border p-5 ${cls}`}>
    <span className={`flex items-center gap-2 font-tc text-[13px] font-bold ${titleCls}`}>{mark}{title}</span>
    <div className="flex flex-col gap-2.5 font-mono text-lg">{children}</div>
  </div>
)

function Row({ it, job }: { it: Item; job: JobState }) {
  const dup = it.status === 'duplicate'
  const isAdd = it.kind === 'add'
  const busy = job.status === 'running' && job.stage === 'format' && it.status === 'looked-up' && job.items.filter(x => x.status === 'looked-up')[0] === it
  return (
    <div className={`grid grid-cols-[88px_minmax(0,3fr)_190px_minmax(0,3fr)_170px_56px] items-start gap-5 border-b border-line px-1 py-4.5 ${dup ? 'bg-[#FAFAFA]' : isAdd ? 'bg-[#F7F8FF]' : ''}`}>
      <span className={`font-mono text-sm font-medium ${dup ? 'text-graphite' : isAdd ? 'text-signal' : ''}`}>{finalLabel(it)}</span>
      <p className={`m-0 leading-relaxed text-dim ${isAdd ? 'font-mono text-[13px]' : 'font-serif text-[15px]'}`}>{isAdd ? it.original : <Ref text={it.original} />}</p>
      <div className="flex flex-col gap-1.5 font-mono text-xs">
        <MatchTag meta={it.meta} />
        {it.meta?.kept ? <span className="font-tc text-dim">預覽時選擇保留原樣</span> : it.meta?.doi ? <Doi doi={it.meta.doi} /> : null}
      </div>
      {dup ? <span className="flex items-center gap-2 font-tc text-sm text-dim"><span className="border border-faint px-1.5 text-[11px]">重複</span>與原 [{it.duplicate_of}] 相同，不新增；內文 [+{it.line}] 換成 [{job.order?.placeholders[`+${it.line}`] ?? it.duplicate_of}]</span>
        : busy ? <div className="flex flex-col gap-2 pt-1.5" aria-label="格式化中"><div className="h-2.5 w-[92%] bg-[#E4E7FB]" /><div className="h-2.5 w-[78%] bg-[#E4E7FB]" /><div className="h-2.5 w-[40%] bg-[#E4E7FB]" /></div>
        : it.formatted ? <p className="m-0 font-serif text-[15px] leading-relaxed">{isAdd ? <Ref text={it.final || it.formatted} /> : <Diff a={it.original} b={it.final || it.formatted} />}</p>
        : <p className="m-0 font-serif text-[15px] text-faint">{job.status === 'done' || job.status === 'failed' ? '—' : '等待中'}</p>}
      <div className="flex flex-col gap-1.5 font-tc text-[13px]">
        {it.check ? (it.check.ok
          ? <span className="flex items-center gap-2 text-ok"><Mark shape="square" color="#0E7C47" />通過</span>
          : <><span className="flex items-center gap-2 text-signal"><Mark shape="tri" color="#2F4BF0" />已修正</span><span className="leading-snug text-dim">{it.check.problems.join('；')}</span></>)
          : busy ? <span className="flex items-center gap-2 font-mono text-xs text-signal"><Mark shape="tri" color="#2F4BF0" />formatting…</span>
          : dup ? <span className="text-faint">—</span>
          : <span className="flex items-center gap-2 font-mono text-xs text-graphite"><Mark shape="dashed" color="#A1A1AA" />{it.status}</span>}
      </div>
      <span className="font-tc text-[13px]">{it.changed === undefined ? <span className="text-faint">—</span> : it.changed ? <b className="font-medium">是</b> : <span className="text-graphite">否</span>}</span>
    </div>
  )
}
