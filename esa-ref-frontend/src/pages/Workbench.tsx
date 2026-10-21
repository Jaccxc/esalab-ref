import { useEffect, useRef, useState } from 'react'
import { jobs, type JobSummary, type Status } from '../api'
import { Confirm, Eyebrow, H1, Mark, STATUS, Shell, Tag, btn, fmtDur, fmtTime, go, input, stageName, type Me } from '../ui'

const MODES = [['fix', '修正模式', '只修既有 [n] 條目'], ['add', '新增模式', '只加書目，不碰既有條目']] as const
const FILTERS: [Status | 'all', string][] = [['all', '全部'], ['waiting', '等待確認'], ['running', '執行中'], ['done', '完成'], ['failed', '失敗']]

export default function Workbench({ me }: { me: Me }) {
  const [list, setList] = useState<JobSummary[]>([])
  const [filter, setFilter] = useState<Status | 'all'>('all')
  const [file, setFile] = useState<File | null>(null)
  const [err, setErr] = useState('')
  const [busy, setBusy] = useState(false)
  // One input per title so the [+k] number is always visible next to its line.
  const [lines, setLines] = useState([''])
  const [focus, setFocus] = useState<number | null>(null)
  const inputs = useRef<(HTMLInputElement | null)[]>([])
  useEffect(() => { if (focus !== null) { inputs.current[focus]?.focus(); setFocus(null) } }, [focus, lines])
  // A line emptied by editing (or left empty on blur) disappears, so the [+k] numbers always count real titles.
  const setLine = (i: number, v: string) => {
    if (!v && lines.length > 1) { setLines(l => l.filter((_, k) => k !== i)); setFocus(Math.max(0, i - 1)); return }
    setLines(l => l.map((x, k) => (k === i ? v : x)))
  }
  const onBlur = (i: number) => { if (!lines[i] && lines.length > 1) setLines(l => l.filter((_, k) => k !== i)) }
  const onKey = (i: number, e: React.KeyboardEvent<HTMLInputElement>) => {
    if (e.key === 'Enter') { e.preventDefault(); setLines(l => [...l.slice(0, i + 1), '', ...l.slice(i + 1)]); setFocus(i + 1) }
    else if (e.key === 'Backspace' && !lines[i] && lines.length > 1) { e.preventDefault(); setLines(l => l.filter((_, k) => k !== i)); setFocus(Math.max(0, i - 1)) }
    else if (e.key === 'ArrowUp' && i > 0) { e.preventDefault(); setFocus(i - 1) }
    else if (e.key === 'ArrowDown' && i < lines.length - 1) { e.preventDefault(); setFocus(i + 1) }
  }
  const onPaste = (i: number, e: React.ClipboardEvent<HTMLInputElement>) => {
    const rows = e.clipboardData.getData('text').split(/\r?\n/).filter(x => x.trim())
    if (rows.length < 2) return
    e.preventDefault(); setLines(l => [...l.slice(0, i), l[i] + rows[0], ...rows.slice(1), ...l.slice(i + 1)]); setFocus(i + rows.length - 1)
  }

  const load = () => jobs.list().then(setList).catch(() => {})
  useEffect(() => { load() }, [])
  // Running jobs are followed by polling here (SSE is for the detail page).
  const live = list.some(j => j.status === 'running' || j.status === 'queued')
  useEffect(() => { if (!live) return; const t = setInterval(load, 3000); return () => clearInterval(t) }, [live])

  const submit = async (e: React.FormEvent<HTMLFormElement>) => {
    e.preventDefault()
    if (!file) return setErr('請先選擇 .docx 檔')
    const fd = new FormData(e.currentTarget)
    fd.set('file', file)
    fd.set('review', fd.get('skip') ? 'false' : 'true'); fd.delete('skip')
    setBusy(true); setErr('')
    try { go(`/jobs/${(await jobs.create(fd)).id}`) } catch (x) { setErr((x as Error).message); setBusy(false) }
  }
  const [ask, setAsk] = useState<JobSummary | null>(null)  // the job whose deletion awaits confirmation
  const remove = async (ok: boolean) => { const j = ask; setAsk(null); if (ok && j) { try { await jobs.remove(j.id) } catch (x) { setErr((x as Error).message) } load() } }

  const waiting = list.filter(j => j.status === 'waiting')
  const shown = list.filter(j => filter === 'all' || j.status === filter)
  const count = (f: Status | 'all') => (f === 'all' ? list : list.filter(j => j.status === f)).length

  const banner = waiting.length > 0 && (
    <a href={`#/jobs/${waiting[0].id}/${waiting[0].ask ? 'block' : 'preview'}`} className="flex flex-wrap items-center gap-x-5 gap-y-3 bg-wait px-5 py-4.5 text-white no-underline max-md:flex-col max-md:items-stretch max-md:p-4">
      <span className="max-md:hidden"><Mark shape="circle" color="#FFFFFF" size={14} /></span>
      <span className="flex flex-[1_1_280px] flex-col gap-0.5 font-tc max-md:flex-none">
        <span className="flex items-center gap-2.5 text-base font-bold"><span className="md:hidden"><Mark shape="circle" color="#FFFFFF" size={12} /></span>{waiting.length} 份工作在等你確認</span>
        <span className="text-[13px] text-[#FFE4C7]">{waiting[0].filename} {waiting[0].ask ? '讀不出參考文獻清單，需要你指一下在哪' : '已查完書目，需要你看一下才會繼續'}。</span>
      </span>
      <span className="btn bg-white px-4 py-2.5 font-tc text-sm font-bold text-[#93370D] max-md:flex max-md:min-h-11 max-md:items-center max-md:px-3.5">{waiting[0].ask ? '去指出清單' : '前往預覽確認'} →</span>
    </a>
  )

  return (
    <Shell me={me} active="work">
      <div className="flex flex-wrap items-start gap-12 max-md:gap-7">
        {banner && <div className="basis-full md:hidden">{banner}</div>}
        <section className="flex max-w-[460px] flex-[1_1_380px] flex-col gap-6 max-md:-mx-4 max-md:max-w-none max-md:border-b-8 max-md:border-mist max-md:px-4 max-md:pb-8">
          <div className="flex flex-col gap-1.5"><Eyebrow>01 / NEW JOB</Eyebrow><H1>建立新工作</H1></div>
          <form onSubmit={submit} className="flex flex-col gap-6">
            <label data-tour="upload" className="flex cursor-pointer flex-col items-start gap-4 border border-dashed border-faint bg-[#FAFAFA] p-6 max-md:p-4"
              onDragOver={e => e.preventDefault()} onDrop={e => { e.preventDefault(); const f = e.dataTransfer.files[0]; if (f) setFile(f) }}>
              <span className="flex w-full items-center gap-3.5">
                <span className="flex h-12 w-10 flex-none items-end justify-center bg-ink pb-1.5 font-mono text-[9px] text-white" aria-hidden="true">DOCX</span>
                <span className="flex min-w-0 flex-col gap-0.5">
                  <span className="truncate text-[15px] font-semibold">{file ? file.name : '選擇論文 .docx'}</span>
                  <span className="font-mono text-xs text-graphite">{file ? `${(file.size / 1048576).toFixed(1)} MB · 點此或拖放以更換` : '點此或拖放檔案'}</span>
                </span>
              </span>
              <input type="file" accept=".docx" className="text-[13px] max-md:sr-only" onChange={e => setFile(e.target.files?.[0] || null)} />
            </label>

            <fieldset data-tour="mode" className="m-0 flex flex-col gap-2.5 border-0 p-0">
              <legend className="mb-2.5 p-0 font-tc text-[13px] font-medium">模式</legend>
              <label className="flex cursor-pointer gap-3.5 border-2 border-ink p-4 has-[:not(:checked)]:border-line">
                <input type="radio" name="mode" value="smart" defaultChecked className="mt-1 accent-ink" />
                <span className="flex flex-col gap-1 font-tc">
                  <span className="text-[15px] font-bold">智慧模式 <span className="font-mono text-[11px] font-normal text-graphite">smart · 預設</span></span>
                  <span className="text-[13px] leading-relaxed text-dim">新增你給的書目（已在清單裡就略過）、修正所有舊條目，最後核對並修正內文引用順序。</span>
                </span>
              </label>
              {MODES.map(([v, name, desc]) => (
                <label key={v} className="flex cursor-pointer gap-3.5 border-2 border-ink p-4 font-tc has-[:not(:checked)]:border-line">
                  <input type="radio" name="mode" value={v} className="mt-1 accent-ink" />
                  <span className="flex flex-col gap-1"><span className="text-[15px] font-bold">{name} <span className="font-mono text-[11px] font-normal text-graphite">{v}</span></span><span className="text-[13px] leading-relaxed text-dim">{desc}</span></span>
                </label>
              ))}
            </fieldset>

            <div data-tour="titles" className="flex flex-col gap-2">
              <span className="font-tc text-[13px] font-medium">要新增的書目 <span className="font-normal text-graphite">（每行一筆：標題、DOI 或 URL，可留空）</span></span>
              <input type="hidden" name="titles" value={lines.join('\n')} />
              <div className="flex flex-col border border-edge">
                {lines.map((l, i) => (
                  <div key={i} className="flex border-b border-line last:border-b-0">
                    <span className="flex w-12 flex-none items-center justify-center bg-mist font-mono text-xs font-medium text-signal" aria-hidden="true">[+{i + 1}]</span>
                    <input ref={el => { inputs.current[i] = el }} value={l} aria-label={`第 ${i + 1} 筆書目`} placeholder={i === 0 ? '標題、DOI 或 URL，Enter 換下一筆' : ''}
                      onChange={e => setLine(i, e.target.value)} onKeyDown={e => onKey(i, e)} onPaste={e => onPaste(i, e)} onBlur={() => onBlur(i)}
                      className="min-w-0 flex-1 border-0 bg-white px-3.5 py-2.5 font-mono text-[13px] text-ink max-md:text-base" />
                  </div>
                ))}
              </div>
              <div className="flex gap-2.5 bg-mist px-3.5 py-3 font-tc text-[13px] leading-[1.7] text-[#3F3F46]">
                <span className="flex-none font-mono font-medium text-signal">[+1]</span>
                <span>文中要引用新書目的位置先打 [+1]、[+2]…，數字就是左側編號（第幾篇新書目），系統會自動換成正確編號。</span>
              </div>
            </div>

            <div className="flex flex-col gap-2">
              <label htmlFor="author" className="font-tc text-[13px] font-medium">修訂作者 <span className="font-normal text-graphite">（Word 修訂顯示的名字）</span></label>
              <input id="author" name="author" defaultValue={me.author} placeholder="ESALab-RefBot" maxLength={64} className={input} />
            </div>

            <label className="flex cursor-pointer gap-3 border border-line px-4 py-3.5">
              <input type="checkbox" name="skip" value="1" className="mt-0.5 h-[18px] w-[18px] flex-none accent-ink" />
              <span className="flex flex-col gap-1 font-tc">
                <span className="text-sm font-medium">跳過人工確認，查到書目後直接修正</span>
                <span className="text-xs leading-relaxed text-graphite">不會停下來讓你預覽找到的論文。只對這次的工作有效，不會記住。</span>
              </span>
            </label>

            {err && <p role="alert" className="m-0 font-mono text-[13px] text-fail">{err}</p>}
            <button type="submit" data-tour="submit" disabled={busy} className="flex h-14 cursor-pointer items-center justify-between border-0 bg-ink px-5.5 font-tc text-base font-bold text-white disabled:bg-faint">
              <span>{busy ? '上傳中…' : '開始'}</span><span aria-hidden="true">→</span>
            </button>
          </form>
        </section>

        <section data-tour="history" className="flex min-w-0 flex-[999_1_560px] flex-col gap-5">
          <div className="flex flex-wrap items-end gap-4">
            <div className="flex flex-col gap-1.5"><Eyebrow>02 / HISTORY</Eyebrow><H1>我的紀錄</H1></div>
            <div className="ml-auto flex flex-wrap gap-1.5 font-tc text-[13px] max-md:-mr-4 max-md:-ml-4 max-md:basis-full max-md:flex-nowrap max-md:overflow-x-auto max-md:px-4">
              {FILTERS.map(([f, name]) => (
                <button key={f} type="button" onClick={() => setFilter(f)} className={`min-h-9 cursor-pointer px-3.5 max-md:min-h-10 max-md:flex-none ${filter === f ? 'border-0 bg-ink text-white' : f === 'waiting' && count(f) ? 'border border-wait bg-[#FFF4E5] font-bold text-[#93370D]' : 'border border-line bg-white'}`}>
                  {name} {count(f)}
                </button>
              ))}
            </div>
          </div>

          {banner && <div className="max-md:hidden">{banner}</div>}

          <div className="flex flex-col border-t border-ink max-md:-mx-4">
            {shown.map(j => {
              const s = STATUS[j.status]
              const label = j.status === 'running' ? `${stageName(j.stage)}` : s.label
              return (
                <article key={j.id} className={`flex flex-wrap items-center gap-x-6 gap-y-4 border-b border-line px-3 py-5 max-md:flex-col max-md:items-stretch max-md:gap-3 max-md:px-4 max-md:py-4.5 ${j.status === 'waiting' ? 'bg-[#FFF4E5]' : ''}`}>
                  <div className="flex min-w-0 flex-[1_1_260px] flex-col gap-1.5 max-md:flex-none">
                    <div className="flex flex-wrap items-center gap-2 max-md:flex-nowrap">
                      <a href={`#/jobs/${j.id}${j.status === 'waiting' ? (j.ask ? '/block' : '/preview') : ''}`} className="text-base font-semibold text-ink no-underline max-md:min-w-0 max-md:truncate">{j.filename}</a>
                      <Tag>{j.mode}</Tag>
                    </div>
                    <div className="font-mono text-xs text-graphite">{fmtTime(j.started)} · {j.status === 'done' || j.status === 'failed' ? '耗時' : '已用'} {fmtDur(j.elapsed)} · {j.entries} 條{j.changed != null ? ` · ${j.changed} 筆修訂` : ''}</div>
                    {j.status === 'failed' && j.error && <div className="font-tc text-[13px] text-fail">{j.error}</div>}
                    {j.status === 'done' && j.expired && <div className="font-tc text-[13px] text-graphite">檔案已超過 30 天，已清除</div>}
                    {j.status === 'waiting' && <div className="font-tc text-[13px] text-[#93370D]">{j.ask ? '讀取條目：找不到 [n] 清單，等你指出在哪' : '預覽確認：查到的論文等你處理'}</div>}
                  </div>
                  <div className="flex w-[240px] flex-none flex-col gap-2 max-md:w-auto">
                    <div className="flex items-center justify-between gap-2">
                      <span className={`flex items-center gap-2 font-tc text-[13px] ${j.status === 'waiting' ? 'bg-wait px-2.5 py-1 font-bold text-white' : 'font-medium'}`} style={j.status !== 'waiting' ? { color: s.color } : undefined}>
                        <Mark shape={s.shape} color={j.status === 'waiting' ? '#FFFFFF' : s.color} />{label}
                      </span>
                      <span className="text-xl font-semibold tracking-tight">{Math.round(j.percent)}<span className="text-xs text-graphite">%</span></span>
                    </div>
                    <div className="h-1 bg-line"><div className="h-1" style={{ width: `${j.percent}%`, background: s.color }} /></div>
                  </div>
                  <div className="flex w-[220px] flex-none justify-end gap-1.5 max-md:w-auto">
                    {j.status === 'done' && !j.expired && <a href={jobs.resultUrl(j.id)} className={`${btn.primary} min-h-10 px-3.5 text-[13px] max-md:min-h-11 max-md:flex-1 max-md:justify-center max-md:text-sm`}>下載</a>}
                    {j.status === 'waiting' && <a href={`#/jobs/${j.id}/${j.ask ? 'block' : 'preview'}`} className="btn flex min-h-10 items-center bg-wait px-3.5 font-tc text-[13px] font-bold text-white no-underline max-md:min-h-11 max-md:flex-1 max-md:justify-center max-md:text-sm">去確認</a>}
                    <a href={`#/jobs/${j.id}`} className={`${btn.ghost} min-h-10 px-3.5 text-[13px] max-md:min-h-11 max-md:flex-1 max-md:justify-center max-md:text-sm`}>詳情</a>
                    <button type="button" aria-label="刪除" onClick={() => setAsk(j)} className="min-h-10 w-10 max-md:min-h-11 max-md:w-11 cursor-pointer border border-edge bg-white text-base text-dim disabled:cursor-default disabled:text-edge">×</button>
                  </div>
                </article>
              )
            })}
            {!shown.length && <div className="flex flex-col items-center gap-3.5 py-12"><span className="h-14 w-14 rounded-full border-2 border-dashed border-faint" /><span className="font-tc text-[13px] text-dim">還沒有工作</span></div>}
          </div>
        </section>
      </div>
      <Confirm open={!!ask} danger={ask?.status === 'running' || ask?.status === 'queued'} onClose={remove}
        title={ask?.status === 'running' || ask?.status === 'queued' ? '中斷並刪除這筆工作？' : '刪除這筆工作？'}
        action={ask?.status === 'running' || ask?.status === 'queued' ? '中斷並刪除' : '刪除'}
        body={<><b className="text-ink">{ask?.filename}</b>{ask?.status === 'running' || ask?.status === 'queued'
          ? ' 還在執行中。刪除會立刻中斷，已經做完的部分不會保留，正在進行的那一筆 LLM 呼叫結束後才會真正停止。'
          : ' 的紀錄與結果檔會一起刪掉，無法復原。'}</>} />
    </Shell>
  )
}
