import { useEffect, useLayoutEffect, useRef, useState, type ReactNode } from 'react'
import { auth } from './api'
import { Mark, btn, go, type Me } from './ui'
import { OrderDemo, SCENARIOS } from './pages/OrderDemo'
import { Found, Generated } from './pages/Lookup'

/* Onboarding tour: three stations (settings -> lookup -> work). The stage reached is stored per user on the server
   (prefs.tour); the module cache keeps it current between hash navigations without refetching /api/me. */
export type Stage = 'settings' | 'lookup' | 'work'
type Step =
  | { kind: 'spot'; target: string; title: string; body: ReactNode }
  | { kind: 'dialog'; title: string; body: ReactNode; wide?: boolean; danger?: boolean }

const NEXT: Record<Stage, Stage | 'done'> = { settings: 'lookup', lookup: 'work', work: 'done' }
const PATH: Record<Stage, string> = { settings: '/settings', lookup: '/lookup', work: '/' }
const LABEL: Record<Stage, string> = { settings: '第 1 站 · 設定', lookup: '第 2 站 · 單筆查詢', work: '第 3 站 · 工作台' }
const cache: { stage?: Stage | 'done' } = {}
const EV = 'esalab-tour'  // restartTour -> the mounted Tour picks the new stage up without a reload

const SAMPLE_META = { match: 'exact' as const, candidates: [], source: 'crossref', title: 'Attention is all you need', year: 2017, venue: 'Advances in Neural Information Processing Systems',
  doi: '10.5555/3295222.3295349', authors: [{ given: 'Ashish', family: 'Vaswani' }, { given: 'Noam', family: 'Shazeer' }, { given: 'Niki', family: 'Parmar' }], seconds: 1.8 }
const SAMPLE_GEN = { reference: 'A. Vaswani et al., "Attention is all you need," in *Proc. 31st Int. Conf. Neural Inf. Process. Syst. (NeurIPS)*, Long Beach, CA, USA, Dec. 2017, pp. 6000–6010.',
  type: 'conference', issues: ['書目資料沒有會議日期，已依年份填 Dec. 2017，請核對。'], check: { ok: true, problems: [] }, seconds: 47 }

const Demo = ({ k, note }: { k: keyof typeof SCENARIOS; note: string }) => (
  <div className="flex flex-col gap-3"><OrderDemo scenario={SCENARIOS[k]} /><p className="m-0 font-tc text-sm leading-relaxed text-dim">{note}</p></div>
)

const STEPS: Record<Stage, Step[]> = {
  settings: [
    { kind: 'dialog', title: '歡迎使用 ESA Lab 參考文獻工具', body: '這套工具會讀你的論文 .docx、查每一筆參考文獻、套實驗室 IEEE 格式，再以 Word 修訂模式寫回，每一筆都能在 Word 裡接受或拒絕。接下來花兩分鐘走過三站：設定、單筆查詢、工作台。每個帳號第一次登入都會看到這段，之後可在說明頁最上方重看。' },
    { kind: 'spot', target: 'author', title: '預設修訂作者', body: 'Word 修訂裡顯示的名字。建立新工作時會自動帶入，留空就用 ESALab-RefBot。建議填自己的名字，之後看修訂才知道是誰改的。' },
    { kind: 'spot', target: 'save', title: '儲存', body: '改完按儲存就生效。下一站：單筆查詢。' },
  ],
  lookup: [
    { kind: 'spot', target: 'query', title: '貼標題、DOI 或網址', body: '一次一筆。DOI 與 arXiv 編號最準；標題要完整，系統會依序比對 Crossref、OpenAlex、Semantic Scholar。' },
    { kind: 'spot', target: 'search', title: '先查查看', body: '只查資料庫，幾秒回來，不跑 LLM。結果有三種：exact 完全相同；fuzzy 最像的一筆，其他列成候選，可按「就是這篇」換掉；none 查不到。' },
    { kind: 'dialog', wide: true, title: '確定是這篇，再產生', body: <div className="flex flex-col gap-5">
      <p className="m-0 font-tc text-[15px] leading-relaxed text-dim">查到後畫面長這樣（以下是範例）：先確認標題、作者、年份都對，再按「產生參考文獻」。LLM 依實驗室規則套格式，再由第二個 LLM 審查，約 30 到 90 秒。</p>
      <Found meta={SAMPLE_META} onGenerate={() => {}} />
      <p className="m-0 font-tc text-[15px] leading-relaxed text-dim">產生後會出現這一區：按「複製」可直接貼進 Word，斜體會保留；黃色附註是 LLM 提醒你查不到、需要自己補的欄位。紀錄留在頁面下方。下一站：工作台。</p>
      <Generated gen={SAMPLE_GEN} />
    </div> },
  ],
  work: [
    { kind: 'spot', target: 'upload', title: '上傳論文 .docx', body: '整份論文直接上傳，系統自己找參考文獻清單與本文裡的 [n] 引用。' },
    { kind: 'spot', target: 'mode', title: '三種模式', body: '智慧模式：修舊條目、加新書目，並核對引用順序。修正模式只修舊的；新增模式只加新的。平常用智慧模式。接下來三個示範是智慧模式最常用的情況。' },
    { kind: 'dialog', wide: true, title: '基本情況一：只要貼標題，格式交給系統', body: <Demo k="format" note="參考文獻清單裡每一行貼標題、從 Google Scholar 複製的字串或 DOI 連結就好，完全不用排格式。上傳後系統查書目、依實驗室 IEEE 規則重寫，以 Word 修訂寫回，你在 Word 裡逐筆接受即可。" /> },
    { kind: 'dialog', wide: true, title: '基本情況二：換一篇引用，直接改本文數字', body: <Demo k="swap" note="唯一的事實是：上傳當下清單裡的論文，以及本文每個數字當時指到的那一篇。系統只重排編號，數字會變，但每個引用對應的論文絕對不變。要換引用對象，就改本文的數字。" /> },
    { kind: 'dialog', wide: true, danger: true, title: '常見錯誤：同一篇引用了兩處，只改一處', body: <Demo k="trap" note="忘了改的那處會被重新編號，看起來像換成功了，其實仍指舊的那篇。同一篇在本文引用了幾處就要改幾處；改之前先用 Word 搜尋「[3]」把每一處找出來。系統只認數字指到的論文，不猜你的意圖。" /> },
    { kind: 'spot', target: 'titles', title: '要新增的書目與 [+1]、[+2]、[+3]', body: '每行一筆標題、DOI 或網址，左側就是它的佔位編號。本文要引用第 1 筆的位置打 [+1]、第 2 筆打 [+2]、第 3 筆打 [+3]，系統會換成正式編號並把條目插進清單。' },
    { kind: 'dialog', wide: true, title: '[+k] 佔位符示範', body: <Demo k="placeholder" note="k 是左側編號（第幾筆新書目），不是行數。本文沒放 [+k] 的新書目會排在清單最後，並列進「內文沒引用到」。" /> },
    { kind: 'spot', target: 'submit', title: '開始', body: '上傳後查完書目會停下來讓你預覽確認 fuzzy 與 none 的條目，確認後才套格式與寫回。勾「跳過人工確認」就一路跑完。' },
    { kind: 'spot', target: 'history', title: '我的紀錄', body: '工作進度都在這裡：等待確認的會以橘色提示，完成後按下載拿 原檔名_esaref_日期.docx。可以離開頁面，伺服器會繼續跑。' },
    { kind: 'dialog', title: '教學完成', body: '想重看，到說明頁最上方按「重看新手教學」。說明頁還有引用順序的幾個動畫情境、縮寫的來源，以及用 AI 客戶端接入的方式。' },
  ],
}

export const restartTour = async () => { await auth.tour('settings'); cache.stage = 'settings'; dispatchEvent(new Event(EV)); go('/settings') }

export function Tour({ me, page }: { me: Me; page: Stage | null }) {
  const [stage, setStage] = useState<Stage | 'done'>(cache.stage ?? ((me.tour || 'settings') as Stage | 'done'))  // state, not just the cache: skipping on step 1 must re-render
  const [i, setI] = useState(0)
  const [rect, setRect] = useState<DOMRect | null>(null)
  const steps = stage === 'done' ? [] : STEPS[stage]
  const step = steps[i] as Step | undefined
  const active = stage !== 'done' && page === stage
  useEffect(() => { const f = () => { setStage(cache.stage ?? 'settings'); setI(0) }; addEventListener(EV, f); return () => removeEventListener(EV, f) }, [])
  // every page is part of the tour until it is done: land on the station the user has reached
  useEffect(() => { if (stage !== 'done' && page !== stage) go(PATH[stage]) }, [stage, page])
  useLayoutEffect(() => {
    if (!active || step?.kind !== 'spot') { setRect(null); return }
    const el = document.querySelector(`[data-tour="${step.target}"]`)
    if (!el) { setRect(null); return }  // target missing: the step shows as a dialog instead
    el.scrollIntoView({ block: 'center' })
    const m = () => setRect(el.getBoundingClientRect())
    m(); addEventListener('resize', m); return () => removeEventListener('resize', m)
  }, [active, step])
  useEffect(() => {
    if (!active || !rect) return
    const o = document.body.style.overflow; document.body.style.overflow = 'hidden'; return () => { document.body.style.overflow = o }
  }, [active, rect])
  const advance = async (n: Stage | 'done') => {
    cache.stage = n; setStage(n); setI(0)
    try { await auth.tour(n) } catch { /* the stage is kept in memory; the next login starts from the last saved one */ }
    if (n !== 'done') go(PATH[n])
  }
  const next = () => (i + 1 < steps.length ? setI(i + 1) : advance(NEXT[stage as Stage]))
  if (!active || !step) return null
  const nav = (
    <div className="flex items-center gap-2.5 pt-1">
      <span className="font-mono text-xs text-graphite">{i + 1} / {steps.length}</span>
      <button type="button" className="cursor-pointer border-0 bg-transparent p-0 font-tc text-xs text-graphite underline" onClick={() => advance('done')}>略過教學</button>
      <button type="button" className={`${btn.ghost} ml-auto`} disabled={i === 0} onClick={() => setI(i - 1)}>上一步</button>
      <button type="button" className={btn.primary} onClick={next}>{i + 1 < steps.length ? '下一步' : stage === 'work' ? '完成' : '下一站'}</button>
    </div>
  )
  if (step.kind === 'spot' && rect) {
    const below = rect.bottom + 260 < innerHeight
    const left = Math.max(16, Math.min(rect.left, innerWidth - 416))
    return (
      <div className="fixed inset-0 z-40" role="dialog" aria-modal="true" aria-label={step.title}>
        <div className="absolute border-2 border-signal shadow-[0_0_0_9999px_rgba(11,11,13,0.62)]" style={{ left: rect.left - 6, top: rect.top - 6, width: rect.width + 12, height: rect.height + 12 }} />
        <div className="absolute flex w-[min(400px,calc(100vw-32px))] flex-col gap-3 border-2 border-ink bg-white p-5" style={below ? { left, top: rect.bottom + 14 } : { left, bottom: innerHeight - rect.top + 14 }}>
          <span className="font-mono text-xs tracking-[0.12em] text-graphite">新手教學 · {LABEL[stage as Stage]}</span>
          <h2 className="m-0 font-tc text-lg font-bold">{step.title}</h2>
          <p className="m-0 font-tc text-sm leading-relaxed text-dim">{step.body}</p>
          {nav}
        </div>
      </div>
    )
  }
  return <TourDialog key={`${stage}-${i}`} title={step.title} wide={step.kind === 'dialog' && step.wide} danger={step.kind === 'dialog' && step.danger} label={LABEL[stage as Stage]} nav={nav}>{step.body}</TourDialog>
}

function TourDialog({ title, label, wide, danger, nav, children }: { title: string; label: string; wide?: boolean; danger?: boolean; nav: ReactNode; children: ReactNode }) {
  const ref = useRef<HTMLDialogElement>(null)
  useEffect(() => { const d = ref.current; if (d && !d.open) d.showModal(); return () => { if (d?.open) d.close() } }, [])
  return (
    <dialog ref={ref} onCancel={e => e.preventDefault()} className={`m-auto border-2 bg-white p-0 text-ink backdrop:bg-[rgba(11,11,13,0.62)] ${danger ? 'border-fail' : 'border-ink'} ${wide ? 'w-[min(820px,calc(100vw-32px))]' : 'w-[min(540px,calc(100vw-32px))]'}`}>
      <div className="flex flex-col gap-4 p-7">
        <span className="font-mono text-xs tracking-[0.12em] text-graphite">新手教學 · {label}</span>
        <div className="flex items-center gap-3"><Mark shape={danger ? 'tri' : 'square'} color={danger ? '#C8281E' : '#0B0B0D'} size={12} /><h2 className="m-0 font-tc text-xl font-bold">{title}</h2></div>
        {typeof children === 'string' ? <p className="m-0 font-tc text-[15px] leading-relaxed text-dim">{children}</p> : children}
        {nav}
      </div>
    </dialog>
  )
}
