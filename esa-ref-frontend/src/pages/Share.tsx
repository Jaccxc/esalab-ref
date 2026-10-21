import { useEffect, useRef, useState } from 'react'
import { base, share, type Share } from '../api'
import { Logo, Mark, btn, fmtTime } from '../ui'
import { JobBody } from './JobDetail'

const link = (t: string) => `${base()}/s/${t}`
// Social share intents: name, label, brand colour, url builder (u = share link, t = one-line blurb). Logos: public/brand/*.svg (simple-icons).
const CH: [string, string, string, (u: string, t: string) => string][] = [
  ['x', 'X', '#000000', (u, t) => `https://twitter.com/intent/tweet?url=${encodeURIComponent(u)}&text=${encodeURIComponent(t)}`],
  ['threads', 'Threads', '#000000', (u, t) => `https://www.threads.net/intent/post?text=${encodeURIComponent(`${t} ${u}`)}`],
  ['facebook', 'Facebook', '#0866FF', u => `https://www.facebook.com/sharer/sharer.php?u=${encodeURIComponent(u)}`],
  ['line', 'LINE', '#06C755', (u, t) => `https://social-plugins.line.me/lineit/share?url=${encodeURIComponent(u)}&text=${encodeURIComponent(t)}`],
]
// Plain and factual, same text as the backend's og:description: the file and the numbers worth sharing (zeros left out).
const blurbOf = (sh: Share) => {
  const f = sh.facts
  const parts = [`${f.entries} 條 reference`, f.changed && `${f.changed} 筆修訂`, f.adds && `${f.adds} 筆新增書目`, f.renumbered && `${f.renumbered} 處順序重編`].filter(Boolean)
  return `${sh.job.filename} 的參考文獻修訂報告：${parts.join('，')}`
}
// The brand mark in white, from the single-colour SVG, via a CSS mask.
const Brand = ({ k }: { k: string }) => { const m = `url(/brand/${k}.svg) center / contain no-repeat`; return <span aria-hidden="true" className="size-4 shrink-0 bg-white" style={{ mask: m, WebkitMask: m }} /> }

export function ShareDialog({ id, open, onClose }: { id: string; open: boolean; onClose: () => void }) {
  const ref = useRef<HTMLDialogElement>(null)
  const [sh, setSh] = useState<Share | null>(null)
  const [err, setErr] = useState('')
  const [copied, setCopied] = useState(false)
  useEffect(() => { const d = ref.current; if (!d) return; if (open && !d.open) d.showModal(); else if (!open && d.open) d.close() }, [open])
  useEffect(() => { if (open && !sh) share.create(id).then(setSh).catch(e => setErr((e as Error).message)) }, [open, id, sh])
  const url = sh ? link(sh.token) : ''
  const blurb = sh ? blurbOf(sh) : ''
  const hit = (via: string) => { if (sh) share.hit(sh.token, via).catch(() => {}) }
  const copy = () => { navigator.clipboard.writeText(url).then(() => { setCopied(true); hit('copy'); setTimeout(() => setCopied(false), 1500) }) }
  const native = () => navigator.share({ title: blurb, url }).then(() => hit('native')).catch(() => {})
  return (
    <dialog ref={ref} onClose={onClose} onClick={e => { if (e.target === ref.current) onClose() }}
      className="m-auto w-[min(720px,calc(100vw-32px))] border-2 border-ink bg-white p-0 text-ink backdrop:bg-[rgba(11,11,13,0.45)]">
      <div className="flex flex-col gap-5 p-7 max-md:gap-4 max-md:p-4">
        <div className="flex items-center gap-3"><Mark shape="square" color="#2F4BF0" size={12} /><h2 className="m-0 font-tc text-xl font-bold">分享這篇的修訂報告</h2>
          <button type="button" aria-label="關閉" onClick={onClose} className="ml-auto flex size-9 cursor-pointer items-center justify-center border border-edge bg-white text-lg text-dim">×</button></div>
        {err && <p className="m-0 font-mono text-sm text-fail">{err}</p>}
        {sh && <>
          <img src={share.cardUrl(sh.token)} alt="分享卡片" className="block aspect-[1200/630] w-full border border-line bg-ink" />
          <div className="flex flex-col gap-2">
            <div className="flex border border-ink">
              <input readOnly value={url} onFocus={e => e.currentTarget.select()} className="min-w-0 flex-1 border-0 bg-mist px-3 font-mono text-[13px] text-ink outline-none" />
              <button type="button" onClick={copy} className={`${btn.primary} min-w-28 hover:transform-none!`}>{copied ? '已複製 ✓' : '複製連結'}</button>
            </div>
            <p className="m-0 font-tc text-xs text-graphite">打開連結的人會看到跟你一模一樣的這一頁，但不能下載修訂後的 .docx。圖片保留 30 天，之後需要時會重新產生。</p>
          </div>
          <div className="flex flex-wrap gap-2 max-md:grid max-md:grid-cols-2">
            {'share' in navigator && <button type="button" onClick={native} className={`${btn.outline} max-md:col-span-2 max-md:justify-center`}>分享到…</button>}
            {CH.map(([k, label, color, f]) => <a key={k} href={f(url, blurb)} target="_blank" rel="noopener" onClick={() => hit(k)} style={{ background: color }} className="btn inline-flex min-h-11 items-center gap-2.5 px-4 font-tc text-sm font-bold text-white no-underline max-md:justify-center"><Brand k={k} />{label}</a>)}
            <a href={share.cardUrl(sh.token)} download={`esalab-${sh.job.filename.replace(/\.docx$/i, '')}.png`} onClick={() => hit('image')} className={`${btn.ghost} ml-auto max-md:col-span-2 max-md:ml-0 max-md:justify-center`}>下載圖片 ↓</a>
          </div>
        </>}
      </div>
    </dialog>
  )
}

// Public, read-only copy of the job page (no login, no docx download).
export function SharePage({ token }: { token: string }) {
  const [sh, setSh] = useState<Share | null>(null)
  const [err, setErr] = useState('')
  useEffect(() => { share.get(token).then(setSh).catch(e => setErr((e as Error).message)) }, [token])
  return (
    <div className="min-h-screen bg-white text-ink">
      <header className="border-b border-line">
        <div className="mx-auto flex min-h-16 max-w-[1360px] flex-wrap items-center gap-x-7 px-6 max-md:min-h-14 max-md:px-4">
          <span className="flex items-center gap-3"><Logo /><span className="text-base font-semibold">ESA Lab</span><span className="bg-mist px-1.5 py-0.5 font-mono text-[11px] text-dim">SHARED</span></span>
          <a href="#/" className={`${btn.outline} ml-auto min-h-9 px-3.5 text-[13px]`}>我也要修參考文獻 →</a>
        </div>
      </header>
      <main className="mx-auto max-w-[1360px] px-6 pt-8 pb-20 max-md:px-4 max-md:pt-5 max-md:pb-16">
        {err ? <p className="font-tc text-fail">{err === 'Not Found' ? '這個分享連結不存在，或原本的工作已被刪除。' : err}</p>
          : !sh ? <p className="font-tc text-dim">載入中…</p>
          : <div className="flex flex-col gap-10">
            <div className="flex flex-col gap-3 border-l-4 border-signal pl-5">
              <span className="font-tc text-[13px] text-graphite">由 <b className="font-sans font-semibold text-ink">{sh.user}</b> 分享 · {fmtTime(sh.created)}</span>
            </div>
            <JobBody job={sh.job} id={sh.job.id} />
          </div>}
      </main>
    </div>
  )
}
