import { useEffect, useRef, useState, type ReactNode } from 'react'
import { type Health, type Me, auth, setToken, type Match, type Meta, type Status } from './api'

// Hash router: `#/jobs/abc/preview` -> ['jobs','abc','preview']. No dependency needed for five routes.
export const useRoute = () => {
  const [hash, setHash] = useState(location.hash)
  useEffect(() => { const f = () => setHash(location.hash); addEventListener('hashchange', f); return () => removeEventListener('hashchange', f) }, [])
  return hash.replace(/^#\/?/, '').split('/').filter(Boolean)
}
export const go = (path: string) => { location.hash = path }

// Hover-triggered animation that always plays out: `play` goes on at mouseenter and off when the last animation ends.
export const usePlay = () => {
  const [on, setOn] = useState(false)
  return {
    className: on ? 'play' : '',
    onMouseEnter: () => setOn(true),
    onAnimationEnd: (e: React.AnimationEvent<Element>) => { const el = e.currentTarget; if (e.target === el || e.target === el.lastElementChild) setOn(false) },
  }
}

// The brand's three primitives: square (embedded), ring (system), triangle (algorithm, the only colored one).
// Ring→triangle gap is 14px at the 120px size vs 20px square→ring (Claude Design), i.e. 0.7× the gap; scaled here.
// The triangle sits 16px closer to the ring at the 120px size (Claude Design), scaled for small logos.
export const Logo = ({ size = 12, light = false }: { size?: number; light?: boolean }) => {
  const c = light ? '#FFFFFF' : '#0B0B0D'
  const play = usePlay()
  // Geometry copied from the Claude Design header mark (46x15 at size 14).
  return (
    <svg {...play} className={`logo block overflow-visible ${play.className}`} width={size * 47 / 14} height={size * 15 / 14} viewBox="0 -5.5 335.7 107.3" aria-hidden="true">
      <rect x="0" y="0" width="100" height="100" fill={c} />
      <circle cx="167.8" cy="50" r="44.8" fill="none" stroke={c} strokeWidth="14" />
      <polygon points="279.3,-5.5 335.7,100 222.9,100" fill="#2F4BF0" />
    </svg>
  )
}

export type Shape = 'square' | 'circle' | 'tri' | 'ring' | 'dashed'
export const Mark = ({ shape, color, size = 9, className = '' }: { shape: Shape; color: string; size?: number; className?: string }) => {
  const s: React.CSSProperties = { width: size, height: size, boxSizing: 'border-box', flex: 'none', display: 'block' }
  if (shape === 'square') Object.assign(s, { background: color })
  if (shape === 'circle') Object.assign(s, { background: color, borderRadius: '50%' })
  if (shape === 'tri') Object.assign(s, { background: color, clipPath: 'polygon(50% 0, 100% 100%, 0 100%)' })
  if (shape === 'ring') Object.assign(s, { border: `2px solid ${color}` })
  if (shape === 'dashed') Object.assign(s, { border: `2px dashed ${color}`, borderRadius: '50%' })
  return <span className={className} style={s} aria-hidden="true" />
}

// Status -> label/shape/color, shared by the history list, the admin table and the job header.
export const STATUS: Record<Status, { label: string; shape: Shape; color: string }> = {
  queued: { label: '排隊中', shape: 'ring', color: '#A1A1AA' },
  running: { label: '執行中', shape: 'tri', color: '#2F4BF0' },
  waiting: { label: '等待確認', shape: 'circle', color: '#B54708' },
  done: { label: '完成', shape: 'square', color: '#0E7C47' },
  failed: { label: '失敗', shape: 'ring', color: '#C8281E' },
}
export const StatusMark = ({ status, label }: { status: Status; label?: string }) => {
  const s = STATUS[status]
  return <span className="flex items-center gap-2 font-tc text-[13px]" style={{ color: s.color }}><Mark shape={s.shape} color={s.color} />{label ?? s.label}</span>
}

// Same order and keys as pipeline.STAGES on the backend.
export const STAGES: [string, string][] = [['extract', '讀取條目'], ['lookup', '查書目'], ['review', '預覽確認'], ['order', '核對順序'], ['format', 'LLM 套格式'], ['check', 'LLM 審查'], ['apply', '寫入修訂']]
export const stageName = (s: string | null) => STAGES.find(x => x[0] === s)?.[1] || s || ''

export const MATCH: Record<Match, { bg: string; fg: string; shape: Shape }> = {
  exact: { bg: '#E6F4EC', fg: '#0A6639', shape: 'square' },
  fuzzy: { bg: '#FEF3C7', fg: '#854D0E', shape: 'circle' },
  none: { bg: '#FDE8E7', fg: '#9F1F17', shape: 'ring' },
}
const SOURCE: Record<string, string> = { crossref: 'Crossref', openalex: 'OpenAlex', semanticscholar: 'Semantic Scholar', s2: 'Semantic Scholar', datacite: 'DataCite' }
export const sourceName = (s?: string | null) => (s ? SOURCE[s] || s : '')
export const MatchTag = ({ meta }: { meta?: Meta }) => {
  if (!meta) return <span className="font-mono text-xs text-graphite">—</span>
  const m = MATCH[meta.match] || MATCH.none
  return (
    <span className="flex items-center gap-1.5 font-mono text-xs">
      <span className="px-1.5 py-0.5" style={{ background: m.bg, color: m.fg }}>{meta.match}</span>
      {meta.source && <span className="text-graphite">{sourceName(meta.source)}</span>}
    </span>
  )
}

export const authorsOf = (m: Meta) => (m.authors || [])
  .map(a => a.name || [a.given && a.given.split(/[\s-]+/).filter(Boolean).map(g => g[0] + '.').join(' '), a.family].filter(Boolean).join(' ')).join(', ')
export const Doi = ({ doi }: { doi?: string | null }) => doi
  ? <a className="font-mono text-xs break-all" href={`https://doi.org/${doi}`} target="_blank" rel="noreferrer">{doi}</a>
  : <span className="font-mono text-xs text-graphite">無 DOI</span>

export const Eyebrow = ({ children }: { children: ReactNode }) => <div className="font-mono text-xs tracking-[0.12em] text-graphite">{children}</div>
export const H1 = ({ children }: { children: ReactNode }) => <h1 className="m-0 font-tc text-[28px] font-bold max-md:text-2xl">{children}</h1>
export const H2 = ({ children }: { children: ReactNode }) => <h2 className="m-0 font-tc text-[22px] font-bold">{children}</h2>
export const Tag = ({ children }: { children: ReactNode }) => <span className="border border-edge px-2 py-0.5 font-mono text-xs">{children}</span>

export const btn = {
  primary: 'btn inline-flex min-h-11 cursor-pointer items-center justify-center gap-3 border-0 bg-ink px-5 font-tc text-sm font-bold text-white no-underline disabled:cursor-default disabled:bg-faint',
  outline: 'btn inline-flex min-h-11 cursor-pointer items-center justify-center border border-ink bg-white px-4 font-tc text-sm text-ink no-underline disabled:cursor-default disabled:border-edge disabled:text-faint',
  ghost: 'btn inline-flex min-h-11 cursor-pointer items-center justify-center border border-edge bg-white px-4 font-tc text-sm text-ink no-underline',
}
// Copies HTML (italics kept, so Word pastes the formatted entry) plus plain text, then flies a "已複製!" from the pointer.
export const copyRef = async (text: string, e: React.MouseEvent) => {
  const plain = text.replace(/\*/g, '')
  const esc = text.replace(/[&<>]/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;' })[c] as string)
  try { await navigator.clipboard.write([new ClipboardItem({ 'text/html': new Blob([esc.replace(/\*([^*]+)\*/g, '<i>$1</i>')], { type: 'text/html' }), 'text/plain': new Blob([plain], { type: 'text/plain' }) })]) }
  catch { await navigator.clipboard.writeText(plain) }
  const a = -Math.PI * (0.1 + Math.random() * 0.8)
  const el = Object.assign(document.createElement('span'), { className: 'fly', textContent: '已複製!' })
  el.style.cssText = `left:${e.clientX}px;top:${e.clientY}px;--dx:${Math.cos(a) * 56}px;--dy:${Math.sin(a) * 56}px;--r:${Math.round(Math.random() * 50 - 25)}deg`
  el.onanimationend = () => el.remove()
  document.body.append(el)
}
export const input = 'h-11 border border-edge bg-white px-3.5 text-[15px] text-ink max-md:h-12 max-md:text-base'  // 16px on phones: iOS zooms into smaller inputs

export const fmtTime = (t: number) => { const d = new Date(t * 1000); return `${d.getMonth() + 1}/${d.getDate()} ${String(d.getHours()).padStart(2, '0')}:${String(d.getMinutes()).padStart(2, '0')}` }
export const fmtDur = (s: number) => `${Math.floor(s / 60)} 分 ${Math.round(s % 60)} 秒`

// /api/health returns the agent's model as {providerID, modelID}
const modelName = (m: unknown) => (typeof m === 'string' ? m : m && typeof m === 'object' ? String((m as { modelID?: string }).modelID || '') : '')

export type { Me }

// Page chrome shared by every signed-in screen; the admin tab shows only for admins.
export function Shell({ me, active, wide = true, children }: { me: Me; active: 'work' | 'lookup' | 'guide' | 'mcp' | 'settings' | 'admin'; wide?: boolean; children: ReactNode }) {
  const [health, setHealth] = useState<Health | null>(null)
  useEffect(() => { auth.health().then(setHealth).catch(() => setHealth({ opencode: false, model: '', throttled: [] })) }, [])
  const nav = (key: typeof active, href: string, label: string) => (
    <a href={href} aria-current={active === key ? 'page' : undefined}
      className={`flex min-h-16 items-center px-3.5 no-underline max-md:min-h-11 max-md:justify-center max-md:px-0 ${active === key ? 'font-bold text-ink shadow-[inset_0_-2px_0_#0B0B0D]' : 'text-dim'}`}>{label}</a>
  )
  return (
    <div className="min-h-screen bg-white">
      <header className="border-b border-line">
        {/* phone: a 56px row (logo, OpenCode pill, account button) with the nav wrapped under it as a 3-column grid */}
        <div className="mx-auto flex min-h-16 max-w-[1360px] flex-wrap items-center gap-x-7 px-6 max-md:gap-x-2.5 max-md:pr-3 max-md:pl-4">
          <a href="#/" className="flex items-center gap-3 text-ink no-underline max-md:h-14 max-md:gap-2.5"><Logo /><span className="text-base font-semibold">ESA Lab</span>
            {active === 'admin' && <span className="bg-ink px-1.5 py-0.5 font-mono text-[11px] text-white">ADMIN</span>}</a>
          <nav aria-label="主選單" className="flex font-tc text-sm max-md:order-last max-md:-mr-3 max-md:-ml-4 max-md:grid max-md:basis-full max-md:grid-cols-3 max-md:border-t max-md:border-line">
            {nav('work', '#/', '工作台')}{nav('lookup', '#/lookup', '單筆查詢')}{nav('settings', '#/settings', '設定')}{nav('mcp', '#/mcp', 'MCP')}{nav('guide', '#/guide', '說明')}{me.admin && nav('admin', '#/admin', '管理頁')}
          </nav>
          <div className="ml-auto flex flex-wrap items-center gap-x-4 gap-y-2 py-2.5 max-md:flex-nowrap max-md:gap-x-2.5 max-md:py-0">
            {!!health?.throttled?.length && <span title="免費額度用完或被限流，書目查詢暫時少了這些來源；在伺服器設定 API key 可解除。" className="flex h-8 items-center gap-2 bg-[#FEF3C7] px-3 font-tc text-xs text-[#854D0E] max-md:h-7 max-md:px-2.5">
              <Mark shape="tri" color="#B54708" size={8} />限流 <span className="font-mono max-md:hidden">{health.throttled.map(t => sourceName(t.source)).join('、')}</span></span>}
            {health && <span className="flex h-8 items-center gap-2 bg-mist px-3 font-mono text-xs max-md:h-7 max-md:px-2.5 max-md:text-[11px]">
              <Mark shape="circle" color={health.opencode ? '#0E7C47' : '#C8281E'} size={8} />OpenCode <span className="text-graphite max-md:hidden">{modelName(health.model) || '離線'}</span></span>}
            <span className="text-sm text-graphite max-md:hidden">{me.username}</span>
            <button type="button" className={`${btn.ghost} max-md:hidden`} onClick={() => { setToken(''); location.reload() }}>登出</button>
            <details className="relative md:hidden">
              <summary aria-label={`帳號選單（${me.username}）`} className="flex size-11 cursor-pointer list-none items-center justify-center rounded-full bg-ink text-[15px] font-semibold text-white [&::-webkit-details-marker]:hidden">{me.username.slice(0, 1).toUpperCase()}</summary>
              <div className="absolute top-full right-0 z-30 mt-1 flex min-w-40 flex-col gap-3 border-2 border-ink bg-white p-4">
                <span className="text-sm text-graphite">{me.username}</span>
                <button type="button" className={btn.ghost} onClick={() => { setToken(''); location.reload() }}>登出</button>
              </div>
            </details>
          </div>
        </div>
      </header>
      <main className={`mx-auto px-6 pt-8 pb-20 max-md:px-4 max-md:pt-5 max-md:pb-16 ${wide ? 'max-w-[1360px]' : 'max-w-[1080px]'}`}>{children}</main>
    </div>
  )
}

export const EmptyRing = ({ text }: { text: string }) => (
  <div className="flex flex-col items-center gap-3.5 py-12 text-center">
    <span className="h-14 w-14 rounded-full border-2 border-dashed border-faint" aria-hidden="true" />
    <span className="font-tc text-[13px] text-dim">{text}</span>
  </div>
)

// Confirmation in the house style; the native <dialog> gives the focus trap, Esc and the backdrop for free.
export function Confirm({ open, title, body, action, danger, onClose }: { open: boolean; title: string; body: ReactNode; action: string; danger?: boolean; onClose: (ok: boolean) => void }) {
  const ref = useRef<HTMLDialogElement>(null)
  useEffect(() => { const d = ref.current; if (!d) return; if (open && !d.open) d.showModal(); else if (!open && d.open) d.close() }, [open])
  return (
    <dialog ref={ref} onClose={() => onClose(false)} onClick={e => { if (e.target === ref.current) onClose(false) }}
      className="m-auto w-[min(480px,calc(100vw-32px))] border-2 border-ink bg-white p-0 text-ink backdrop:bg-[rgba(11,11,13,0.45)]">
      <div className="flex flex-col gap-5 p-7">
        <div className="flex items-center gap-3"><Mark shape={danger ? 'tri' : 'square'} color={danger ? '#C8281E' : '#0B0B0D'} size={12} /><h2 className="m-0 font-tc text-xl font-bold">{title}</h2></div>
        <p className="m-0 font-tc text-[15px] leading-relaxed text-dim">{body}</p>
        <div className="flex justify-end gap-2.5">
          <button type="button" className={btn.ghost} onClick={() => onClose(false)}>取消</button>
          <button type="button" className={btn.primary} style={danger ? { background: '#C8281E' } : undefined} onClick={() => onClose(true)}>{action}</button>
        </div>
      </div>
    </dialog>
  )
}
