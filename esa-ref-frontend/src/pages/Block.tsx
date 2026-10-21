import { useEffect, useRef, useState, type ReactNode } from 'react'
import { jobs, type Ask } from '../api'
import { Mark, Shell, Tag, btn, go, type Me } from '../ui'
import { useJob } from '../useJob'
import { OrderDemo, SCENARIOS } from './OrderDemo'

const REASON: Record<Ask['reason'], string> = {
  no_heading: '找不到 References 標題',
  empty: '標題下方沒有內容',
  no_labels: '段落開頭沒有 [n] 編號',
  blob: '標題下方只有一段，沒有 [n] 編號',
}

function Help({ open, onClose, children }: { open: boolean; onClose: () => void; children: ReactNode }) {
  const ref = useRef<HTMLDialogElement>(null)
  useEffect(() => { const d = ref.current; if (!d) return; if (open && !d.open) d.showModal(); else if (!open && d.open) d.close() }, [open])
  return (
    <dialog ref={ref} onClose={onClose} onClick={e => { if (e.target === ref.current) onClose() }}
      className="m-auto w-[min(820px,calc(100vw-32px))] border-2 border-ink bg-white p-0 text-ink backdrop:bg-[rgba(11,11,13,0.62)]">
      <div className="flex flex-col gap-4 p-7 max-md:p-4">{open && children}<button type="button" className={`${btn.primary} self-end`} onClick={onClose}>知道了</button></div>
    </dialog>
  )
}

export default function Block({ me, id }: { me: Me; id: string }) {
  const { job, err } = useJob(id)
  const [picked, setPicked] = useState<Set<number> | null>(null)
  const [manual, setManual] = useState<string | null>(null)  // the textarea mode: one entry per line
  const [busy, setBusy] = useState<'split' | 'send' | null>(null)
  const [help, setHelp] = useState(false)
  if (err) return <Shell me={me} active="work"><p className="font-mono text-fail">{err}</p></Shell>
  if (!job) return <Shell me={me} active="work"><p className="font-tc text-dim">載入中…</p></Shell>
  const ask = job.ask
  if (!ask) return <Shell me={me} active="work"><p className="font-tc text-dim">這份工作沒有在等參考文獻區塊的回答。<a href={`#/jobs/${id}`} className="text-ink">看工作詳情</a></p></Shell>

  const cands = ask.candidates
  const sel = picked ?? new Set(cands.filter(c => c.likely).map(c => c.index))
  const text = manual ?? (ask.blob ? cands.map(c => c.text).join('\n') : cands.filter(c => sel.has(c.index)).map(c => c.text).join('\n'))
  const lines = text.split('\n').map(l => l.trim()).filter(Boolean)
  const textMode = ask.blob || ask.reason === 'empty' || manual !== null
  const titles = job.titles.filter(t => t.trim()).length

  const send = async (body: { paras: number[]; entries?: string[]; append?: boolean }) => {
    setBusy('send')
    try { await jobs.block(id, { heading: ask.heading, ...body }); go(`/jobs/${id}`) } catch (x) { alert((x as Error).message); setBusy(null) }
  }
  const split = async () => {
    setBusy('split')
    try { const r = await jobs.split(id, text); setManual(r.entries.join('\n')) } catch (x) { alert((x as Error).message) }
    setBusy(null)
  }
  const toggle = (i: number) => { const n = new Set(sel); if (n.has(i)) n.delete(i); else n.add(i); setPicked(n) }
  const appendBtn = (
    <button type="button" className={btn.ghost} disabled={busy !== null} onClick={() => send({ paras: [], append: true })}
      title={titles ? `查書目、確認後，把 ${titles} 筆新書目寫成新的 References 段` : '沒有新書目可加，工作會直接完成'}>
      此文件沒有 reference 段，直接在文末新增
    </button>
  )

  return (
    <Shell me={me} active="work">
      <div className="flex flex-col gap-8">
        <div className="flex flex-col gap-3">
          <a href={`#/jobs/${id}`} className="flex min-h-8 items-center self-start font-tc text-sm text-dim no-underline max-md:min-h-11">← 工作詳情</a>
          <div className="flex flex-wrap items-baseline gap-x-5 gap-y-2.5">
            <h1 className="m-0 font-tc text-[34px] font-bold max-md:basis-full max-md:text-[26px]">先告訴系統參考文獻在哪</h1><span className="text-lg font-semibold max-md:min-w-0 max-md:truncate max-md:text-base">{job.filename}</span><Tag>{job.mode}</Tag>
            <button type="button" className={`${btn.outline} ml-auto max-md:basis-full max-md:ml-0`} onClick={() => setHelp(true)}>教學：這一頁要做什麼</button>
          </div>
          <p className="m-0 max-w-[760px] font-tc text-[15px] leading-relaxed text-dim">無法確認參考文獻區塊：{REASON[ask.reason]}。</p>
        </div>

        {!textMode && (
          <section className="flex flex-col gap-4">
            <h2 className="m-0 font-tc text-xl font-bold">這些段落是你的參考文獻清單嗎？</h2>
            <div className="flex flex-wrap items-center gap-3">
              <span className="font-tc text-sm text-dim">{ask.heading != null ? '標題下方' : '文件最後'}共 {cands.length} 段，像書目的已先勾好（已勾 {sel.size} 段）。勾起來的會依序成為 [1]…[n]，沒勾的原樣留在文件裡。</span>
              <button type="button" className={`${btn.ghost} min-h-9 px-3 text-[13px]`} onClick={() => setPicked(new Set(cands.map(c => c.index)))}>全選</button>
              <button type="button" className={`${btn.ghost} min-h-9 px-3 text-[13px]`} onClick={() => setPicked(new Set())}>全不選</button>
            </div>
            <ol className="m-0 flex list-none flex-col border-t border-line p-0">
              {cands.map((c, k) => (
                <li key={c.index} className={`flex items-start gap-4 border-b border-line px-2 py-3 max-md:flex-wrap max-md:gap-x-3 max-md:px-0 ${sel.has(c.index) ? 'bg-white' : 'bg-mist text-dim'}`}>
                  <input type="checkbox" className="mt-1 size-4 accent-ink" checked={sel.has(c.index)} onChange={() => toggle(c.index)} aria-label={`第 ${k + 1} 段`} />
                  <span className="w-10 shrink-0 font-mono text-sm text-graphite max-md:w-8">{sel.has(c.index) ? `[${[...sel].filter(i => i < c.index).length + 1}]` : '—'}</span>
                  <span className="min-w-0 flex-1 font-serif text-[14px] leading-snug">{c.text}</span>
                  {c.numbered && <span className="shrink-0 border border-edge px-1.5 py-0.5 font-mono text-[11px] text-dim max-md:order-last max-md:ml-[72px] max-md:shrink max-md:basis-full max-md:border-0 max-md:p-0 max-md:before:content-['→_']">{c.numbered.includes('%') ? 'Word 自動編號' : `開頭 ${c.numbered}`}</span>}
                </li>
              ))}
            </ol>
            <div className="flex flex-wrap items-center gap-3 max-md:flex-col max-md:items-stretch">
              <button type="button" className={btn.primary} disabled={busy !== null || sel.size === 0} onClick={() => send({ paras: [...sel].sort((a, b) => a - b) })}>
                對，這 {sel.size} 段是清單，幫我加上 [n] 編號
              </button>
              <button type="button" className={btn.outline} disabled={busy !== null} onClick={() => setManual(text)}>不對，我自己整理（一行一筆）</button>
              {appendBtn}
            </div>
          </section>
        )}

        {textMode && (
          <section className="flex flex-col gap-4">
            <h2 className="m-0 font-tc text-xl font-bold">這是你的參考文獻區塊嗎？</h2>
            <p className="m-0 max-w-[760px] font-tc text-[15px] leading-relaxed text-dim">
              一行一筆，行首不用編號。連換行都沒有的話，按「讓 LLM 初排」切行（只切行，內容不改）。
            </p>
            <textarea className="min-h-[360px] w-full border border-edge bg-white p-3 font-serif text-[14px] leading-relaxed max-md:text-base" value={text} onChange={e => setManual(e.target.value)} spellCheck={false} placeholder="一行一筆，貼進來" />
            <div className="flex flex-wrap items-center gap-3 max-md:flex-col max-md:items-stretch">
              <span className="font-tc text-sm text-dim">目前 {lines.length} 筆</span>
              <button type="button" className={btn.primary} disabled={busy !== null || lines.length === 0} onClick={() => send({ paras: ask.blob ? cands.map(c => c.index) : [...sel].sort((a, b) => a - b), entries: lines })}>
                對，一行一筆，加上編號繼續
              </button>
              <button type="button" className={btn.outline} disabled={busy !== null || !text.trim()} onClick={split}>{busy === 'split' ? 'LLM 初排中…' : '讓 LLM 初排成一行一筆'}</button>
              {appendBtn}
              {manual !== null && !ask.blob && ask.reason !== 'empty' && <button type="button" className={btn.ghost} onClick={() => setManual(null)}>回到勾選</button>}
            </div>
          </section>
        )}
      </div>

      <Help open={help} onClose={() => setHelp(false)}>
        <div className="flex items-center gap-3"><Mark shape="square" color="#0B0B0D" size={12} /><h2 className="m-0 font-tc text-xl font-bold">{textMode ? '清單擠在一段時怎麼辦' : '勾出清單，系統加上編號'}</h2></div>
        <OrderDemo scenario={textMode ? SCENARIOS.blob : SCENARIOS.pick} />
        <p className="m-0 font-tc text-[15px] leading-relaxed text-dim">
          {textMode
            ? '系統要的是「一筆一段、開頭 [n]」。整段擠在一起時先用「讓 LLM 初排」切成一行一筆（內容一字不改），檢查無誤按「確認」，系統加上編號、以 Word 修訂寫回，再接著查書目、套格式。'
            : '系統要的是「一筆一段、開頭 [n]」。段落已經分好、只缺編號時，勾出屬於清單的段落按「幫我加上 [n] 編號」就好；沒勾的段落原樣留著。'}
          文件還沒有清單的話，選「在文末新增 References 段」：有填新書目就查書目、確認後寫成新段落；沒填就直接完成。
        </p>
      </Help>
    </Shell>
  )
}
