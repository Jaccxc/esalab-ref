import React, { useEffect, useState } from 'react'
import { refs, type Meta, type Ref as RefRow } from '../api'
import { Doi, MATCH, Mark, Shell, Tag, authorsOf, btn, copyRef, fmtTime, sourceName, type Me } from '../ui'
import { Ref } from './JobDetail'

export type Gen = Awaited<ReturnType<typeof refs.wait>> & { seconds: number }
const RUN = 'single-run'  // the task in flight, so a reload resumes polling instead of losing it


// The lookup result and the generated entry, shared with the onboarding tour (which feeds them sample data).
export function Found({ meta, onPick, onGenerate }: { meta: Meta & { seconds: number }; onPick?: (k: number) => void; onGenerate?: () => void }) {
  const mt = MATCH[meta.match]
  return (
    <section className="flex flex-col gap-4">
      <div className="flex flex-wrap items-center gap-x-3.5 gap-y-2.5">
        <span className="flex items-center gap-1.5 px-2.5 py-1 font-mono text-xs font-medium" style={{ background: meta.match === 'exact' ? '#0E7C47' : meta.match === 'fuzzy' ? '#FACC15' : '#C8281E', color: meta.match === 'fuzzy' ? '#422006' : '#fff' }}>
          <Mark shape={mt.shape} color={meta.match === 'fuzzy' ? '#422006' : '#fff'} size={8} />{meta.match}</span>
        <span className="font-tc text-sm text-dim">{meta.match === 'none' ? '查不到' : meta.match === 'exact' ? '找到了' : '找到相近的'} · {meta.seconds.toFixed(1)} 秒 · 未使用 LLM</span>
      </div>
      {meta.match === 'none'
        ? <div className="flex items-center gap-3.5 border border-dashed border-edge p-4.5"><Mark shape="dashed" color="#A1A1AA" size={36} /><span className="font-tc text-sm leading-relaxed text-dim">{meta.error || 'Crossref、OpenAlex、Semantic Scholar 都查不到。試試 DOI 或更完整的標題。'}</span></div>
        : <div className="flex flex-wrap items-start gap-6">
          <div className="flex flex-[1_1_420px] flex-col gap-2 border border-ink p-6">
            <span className="text-xl leading-snug font-semibold">{meta.title}</span>
            <span className="text-sm leading-relaxed text-dim">{authorsOf(meta)}{meta.year ? ` · ${meta.year}` : ''}</span>
            {meta.venue && <span className="text-sm text-dim"><em>{meta.venue}</em></span>}
            <span className="flex flex-wrap items-center gap-3 pt-1 font-mono text-xs"><Doi doi={meta.doi} /><span className="bg-mist px-1.5 py-0.5 text-dim">{sourceName(meta.source)}</span></span>
          </div>
          {meta.candidates.length > 0 && (
            <div className="flex flex-[1_1_320px] flex-col gap-2">
              <span className="font-tc text-xs font-medium text-graphite">其他候選 · {meta.candidates.length}</span>
              <div className="flex flex-col border-t border-line">
              {meta.candidates.map((c, k) => (
                <div key={k} className="flex flex-col gap-2.5 border-b border-line py-4">
                  <span className="text-[15px] font-semibold">{c.title}</span>
                  <span className="text-[13px] text-dim">{authorsOf(c)}{c.year ? ` · ${c.year}` : ''}{c.venue ? <> · <em>{c.venue}</em></> : ''}</span>
                  <Doi doi={c.doi} />
                  <button type="button" className={`${btn.outline} min-h-10 self-start font-bold`} onClick={() => onPick?.(k)}>就是這篇</button>
                </div>
              ))}
              </div>
            </div>
          )}
        </div>}
      {meta.match !== 'none' && onGenerate && (
        <button type="button" onClick={onGenerate} className="flex min-h-14 cursor-pointer items-center gap-4 self-start border-0 bg-signal px-6 font-tc text-base font-bold text-white">產生參考文獻 <span className="font-mono text-xs font-normal text-[#C9D1FF]">約 30–60 秒</span></button>
      )}
    </section>
  
  )
}

export function Generated({ gen }: { gen: Gen }) {
  return (
    <section className="flex flex-col gap-4">
      <div className="flex flex-wrap items-center gap-x-4 gap-y-2.5">
        <h2 className="m-0 font-tc text-[22px] font-bold">參考文獻</h2>
        {gen.type && <Tag>{gen.type}</Tag>}
        {gen.check.ok ? <span className="flex items-center gap-2 font-tc text-sm text-ok"><Mark shape="square" color="#0E7C47" size={10} />審查通過</span>
          : <span className="flex items-center gap-2 font-tc text-sm text-signal"><Mark shape="tri" color="#2F4BF0" size={10} />審查後已修正</span>}
        <span className="ml-auto font-mono text-xs text-graphite">{gen.seconds} 秒</span>
      </div>
      <div className="flex flex-wrap items-start gap-5 bg-mist p-7">
        <p className="m-0 flex-[1_1_480px] font-serif text-lg leading-[1.7]"><Ref text={gen.reference} /></p>
        <button type="button" className={btn.primary} onClick={e => copyRef(gen.reference, e)}>複製</button>
      </div>
      {[...gen.issues, ...gen.check.problems].map((x, i) => (
        <div key={i} className="flex items-center gap-2.5 border border-[#F5D77A] bg-[#FFFDF2] px-4 py-3 font-tc text-sm text-[#713F12]"><Mark shape="circle" color="#CA8A04" />LLM 註記：{x}</div>
      ))}
    </section>
  
  )
}

export default function Lookup({ me }: { me: Me }) {
  const [q, setQ] = useState('')
  const [meta, setMeta] = useState<(Meta & { seconds: number }) | null>(null)
  const [gen, setGen] = useState<Gen | null>(null)
  const [busy, setBusy] = useState<'search' | 'gen' | null>(null)
  const [tick, setTick] = useState(0)
  const [t0, setT0] = useState(0)
  const [stage, setStage] = useState('format')
  const [err, setErr] = useState('')
  const [history, setHistory] = useState<RefRow[]>([])
  const [open, setOpen] = useState<string | null>(null)
  const loadHistory = () => refs.history().then(setHistory).catch(() => {})
  useEffect(() => { loadHistory() }, [])
  useEffect(() => { if (busy !== 'gen') return; const f = () => setTick(Math.floor((Date.now() - t0) / 1000)); f(); const t = setInterval(f, 1000); return () => clearInterval(t) }, [busy, t0])
  const wait = async (id: string, from: number) => {
    setBusy('gen'); setErr(''); setStage('lookup'); setT0(from)
    try { setGen({ ...(await refs.wait(id, setStage)), seconds: Math.round((Date.now() - from) / 1000) }); loadHistory() } catch (x) { setErr((x as Error).message) }
    localStorage.removeItem(RUN); setBusy(null)
  }
  useEffect(() => { const r = localStorage.getItem(RUN); if (r) { const { id, q, t0 } = JSON.parse(r); setQ(q); wait(id, t0) } }, [])  // eslint-disable-line react-hooks/exhaustive-deps

  const search = async (e: React.FormEvent) => {
    e.preventDefault()
    setBusy('search'); setErr(''); setGen(null); setMeta(null)
    const t0 = Date.now()
    try { setMeta({ ...(await refs.search(q.trim())), seconds: (Date.now() - t0) / 1000 }) } catch (x) { setErr((x as Error).message) }
    setBusy(null)
  }
  const generate = async () => {
    if (!meta) return
    const from = Date.now()
    try { const { id } = await refs.start(q.trim(), meta); localStorage.setItem(RUN, JSON.stringify({ id, q: q.trim(), t0: from })); await wait(id, from) } catch (x) { setErr((x as Error).message) }
  }
  // swap in another candidate: it becomes the chosen work, the previous one joins the candidates
  const pick = (k: number) => { if (!meta) return; const c = meta.candidates[k]; const rest = meta.candidates.filter((_, j) => j !== k); const { candidates: _c, match: _m, seconds: _s, ...prev } = meta; void _c; void _m; void _s; setMeta({ ...c, match: 'exact', candidates: [prev as Meta, ...rest], seconds: meta.seconds }); setGen(null) }

  return (
    <Shell me={me} active="lookup" wide={false}>
      <div className="flex flex-col gap-10">
        <div className="flex flex-col gap-5">
          <div className="flex flex-col gap-2">
            <div className="font-mono text-xs tracking-[0.12em] text-graphite">SINGLE LOOKUP</div>
            <h1 className="m-0 font-tc text-4xl font-bold">單筆查詢</h1>
            <p className="m-0 font-tc text-[15px] leading-relaxed text-dim">輸入標題、DOI 或網址，依序比對 Crossref、OpenAlex、Semantic Scholar 的書目資料。</p>
          </div>
          <form onSubmit={search} className="flex flex-wrap gap-2.5">
            <input data-tour="query" aria-label="標題、DOI 或 URL" value={q} onChange={e => setQ(e.target.value)} required placeholder="標題、DOI 或 URL" className="h-15 flex-[1_1_420px] border-2 border-ink px-5 text-lg text-ink" />
            <button type="submit" data-tour="search" disabled={busy !== null} className="min-h-15 flex-none cursor-pointer border-0 bg-ink px-7 font-tc text-base font-bold text-white disabled:bg-faint">{busy === 'search' ? '查詢中…' : '先查查看'}</button>
          </form>
          {err && <p role="alert" className="m-0 font-mono text-[13px] text-fail">{err}</p>}
        </div>

        {meta && <Found meta={meta} onPick={pick} onGenerate={!gen && busy !== 'gen' ? generate : undefined} />}

        {busy === 'gen' && (
          <section className="flex flex-wrap items-center gap-x-10 gap-y-6 bg-ink p-8 text-white">
            <div className="flex h-12 items-end gap-1.5" aria-hidden="true">
              {[14, 26, 40, 48, 34, 20, 12].map((h, i) => <div key={i} className="bar" style={{ width: 6, height: h, animationDelay: `${i * 0.1}s`, background: i === 3 ? '#2F4BF0' : i === 2 ? '#FFFFFF' : '#3F3F46' }} />)}
            </div>
            <div className="flex flex-[1_1_300px] flex-col gap-1.5">
              <span className="font-tc text-lg font-bold">{stage === 'check' ? 'LLM 依規則審查中…' : stage === 'format' ? 'LLM 套格式中…' : '查書目中…'}</span>
              <span className="font-mono text-[13px] text-faint">第 {stage === 'check' ? 2 : 1} / 2 步 · 已 {tick} 秒{tick > 60 ? ' · 就快完成了…' : tick > 30 ? ' · LLM 正在努力核對中…' : ''}</span>
            </div>
          </section>
        )}

        {gen && <Generated gen={gen} />}

        <section className="flex flex-col gap-4">
          <h2 className="m-0 font-tc text-xl font-bold">我的單筆產生紀錄</h2>
          <div className="overflow-x-auto">
            <table className="w-full min-w-[760px] border-collapse">
              <thead><tr className="border-t border-b border-t-ink border-b-line text-left font-tc text-xs text-graphite">
                <th className="px-2 py-3 font-medium">查詢</th><th className="px-2 py-3 font-medium">結果</th><th className="px-2 py-3 font-medium">時間</th><th className="px-2 py-3 font-medium">審查</th><th className="px-2 py-3"></th></tr></thead>
              <tbody>
                {history.map(r => { const notes = [...r.issues, ...r.check.problems]; return (<React.Fragment key={r.id}>
                  <tr className={`cursor-pointer border-b border-line align-top ${open === r.id ? 'bg-[#FAFAFA]' : ''}`} onClick={() => setOpen(open === r.id ? null : r.id)} aria-expanded={open === r.id}>
                    <td className="w-[220px] px-2 py-4 font-mono text-[13px] break-all"><span className="mr-1.5 inline-block text-graphite" aria-hidden="true">{open === r.id ? '▾' : '▸'}</span>{r.query}</td>
                    <td className="px-2 py-4 font-serif text-[15px] leading-relaxed"><Ref text={r.reference} /></td>
                    <td className="px-2 py-4 font-mono text-xs whitespace-nowrap text-dim">{fmtTime(r.created)}</td>
                    <td className="px-2 py-4">{r.check.ok
                      ? <span className="flex items-center gap-1.5 font-tc text-[13px] whitespace-nowrap text-ok"><Mark shape="square" color="#0E7C47" size={8} />通過</span>
                      : <span className="flex items-center gap-1.5 font-tc text-[13px] whitespace-nowrap text-fail"><Mark shape="ring" color="#C8281E" size={8} />已修正</span>}
                      {notes.length > 0 && <span className="mt-1 block font-mono text-[11px] whitespace-nowrap text-graphite">{notes.length} 則附註</span>}</td>
                    <td className="px-2 py-3"><button type="button" className={`${btn.ghost} min-h-9 px-3 text-[13px] whitespace-nowrap`} onClick={e => { e.stopPropagation(); copyRef(r.reference, e) }}>複製</button></td>
                  </tr>
                  {open === r.id && <tr className="border-b border-line bg-[#FAFAFA]"><td colSpan={5} className="px-2 pt-1 pb-4">
                    {notes.length ? <ul className="m-0 flex list-none flex-col gap-1.5 p-0">{notes.map((x, i) => <li key={i} className="flex items-start gap-2.5 font-tc text-[13px] leading-relaxed text-[#713F12]"><span className="mt-[7px] flex-none"><Mark shape="circle" color="#CA8A04" size={8} /></span><span><Ref text={x} /></span></li>)}</ul>
                      : <span className="font-tc text-[13px] text-dim">沒有附註</span>}
                  </td></tr>}
                </React.Fragment>) })}
                {!history.length && <tr><td colSpan={5} className="px-2 py-8 text-center font-tc text-[13px] text-dim">還沒有產生過單筆參考文獻</td></tr>}
              </tbody>
            </table>
          </div>
        </section>
      </div>
    </Shell>
  )
}
