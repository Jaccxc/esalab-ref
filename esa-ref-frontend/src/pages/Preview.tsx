import { useState } from 'react'
import { jobs, type Item, type Meta } from '../api'
import { Doi, MATCH, Mark, STAGES, Shell, Tag, authorsOf, btn, go, input, sourceName, type Me } from '../ui'
import { useJob } from '../useJob'
import { Ref } from './JobDetail'

const label = (it: Item) => it.kind === 'fix' ? `[${it.number}]` : `+${it.line}`

const Paper = ({ m, chosen }: { m: Meta; chosen?: boolean }) => (
  <div className={`flex flex-col gap-1.5 border bg-white p-4.5 ${chosen ? 'border-ink' : 'border-line'}`}>
    <span className="text-base leading-snug font-semibold">{m.title}</span>
    {m.authors?.length ? <span className="text-sm text-dim">{authorsOf(m)}{m.year ? ` · ${m.year}` : ''}</span> : m.year ? <span className="text-sm text-dim">{m.year}</span> : null}
    {m.venue && <span className="text-sm text-dim"><em>{m.venue}</em></span>}
    <span className="flex flex-wrap items-center gap-3 font-mono text-xs"><Doi doi={m.doi} />{m.source && <span className="bg-mist px-1.5 py-0.5 text-dim">{sourceName(m.source)}</span>}</span>
  </div>
)

const Cand = ({ c, disabled, onPick }: { c: Meta; disabled: boolean; onPick: () => void }) => (
  <div className="flex flex-wrap items-center gap-x-5 gap-y-2 border-b border-line py-3.5">
    <span className="flex min-w-0 flex-[1_1_360px] flex-col gap-1">
      <span className="text-[15px] font-semibold">{c.title}</span>
      <span className="text-[13px] text-dim">{[authorsOf(c), c.year, c.venue && <em key="v">{c.venue}</em>].filter(Boolean).map((x, j) => <span key={j}>{j ? ' · ' : ''}{x}</span>)} · <Doi doi={c.doi} /> · {sourceName(c.source)}</span>
    </span>
    <button type="button" disabled={disabled} className={`${btn.outline} min-h-10 font-bold max-md:min-h-11 max-md:w-full max-md:justify-center`} onClick={onPick}>就是這篇</button>
  </div>
)

export default function Preview({ me, id }: { me: Me; id: string }) {
  const { job, err, reload } = useJob(id)
  const [showAll, setShowAll] = useState(false)
  const [busy, setBusy] = useState<number | 'continue' | null>(null)
  const [queries, setQueries] = useState<Record<number, string>>({})
  const [found, setFound] = useState<Record<number, Meta>>({})  // re-query results, shown until the user picks one
  if (err) return <Shell me={me} active="work"><p className="font-mono text-fail">{err}</p></Shell>
  if (!job) return <Shell me={me} active="work"><p className="font-tc text-dim">載入中…</p></Shell>
  if (job.ask) { go(`/jobs/${id}/block`); return null }

  const act = async (i: number, f: () => Promise<unknown>) => { setBusy(i); try { await f(); await reload() } catch (x) { alert((x as Error).message) } setBusy(null) }
  const cont = async () => { setBusy('continue'); try { await jobs.resume(id); go(`/jobs/${id}`) } catch (x) { alert((x as Error).message); setBusy(null) } }

  const items = job.items.map((it, i) => ({ it, i }))
  const attention = items.filter(x => x.it.uncertain && x.it.status !== 'duplicate').sort((a, b) => (a.it.meta?.match === 'none' ? 0 : 1) - (b.it.meta?.match === 'none' ? 0 : 1))
  const rest = items.filter(x => !attention.includes(x))
  const counts = { exact: 0, fuzzy: 0, none: 0 }
  job.items.forEach(it => { if (it.meta) counts[it.meta.match]++ })
  const adds = job.items.filter(i => i.kind === 'add').length
  const waiting = job.status === 'waiting'
  const editable = items.filter(x => x.it.status !== 'duplicate')
  const skipped = editable.filter(x => x.it.skip).length
  const skipAll = (on: boolean) => act(-1, () => jobs.skip(id, editable.map(x => x.i), on))
  const skipBox = (it: Item, i: number) => <input type="checkbox" className="size-4 accent-ink" aria-label="跳過，不調整" checked={!!it.skip} disabled={busy !== null || !waiting} onChange={e => act(i, () => jobs.skip(id, [i], e.target.checked))} />

  return (
    <Shell me={me} active="work">
      <div className="flex flex-col gap-9">
        <div className="flex flex-col gap-3">
          <a href={`#/jobs/${id}`} className="flex min-h-8 items-center self-start font-tc text-sm text-dim no-underline max-md:min-h-11">← 工作詳情</a>
          <div className="flex flex-wrap items-baseline gap-x-5 gap-y-2.5">
            <h1 className="m-0 font-tc text-[34px] font-bold max-md:basis-full max-md:text-[26px]">預覽找到的論文</h1><span className="text-lg font-semibold max-md:min-w-0 max-md:truncate max-md:text-base">{job.filename}</span><Tag>{job.mode}</Tag>
          </div>
          <p className="m-0 font-tc text-[15px] leading-relaxed text-dim">{waiting
            ? '查完書目了，工作暫停在這裡。確認每一筆對到的是正確的論文，再按頁尾的「確認無誤，繼續」。'
            : '這份工作已不在等待確認的狀態，以下是查書目的結果。'}</p>
        </div>

        <ol className="m-0 grid list-none grid-cols-[repeat(auto-fit,minmax(130px,1fr))] gap-4 border-y border-line px-0 py-5 max-md:flex max-md:gap-1 max-md:py-4">
          {STAGES.map(([key, name], i) => (
            <li key={key} className={`flex min-w-0 items-center gap-2.5 max-md:h-1 max-md:flex-1 max-md:overflow-hidden max-md:[&>*]:invisible ${i < 2 ? 'max-md:bg-ink' : i === 2 ? 'max-md:bg-wait' : 'max-md:bg-edge'}`}>
              <Mark size={12} shape={i < 2 ? 'square' : i === 2 ? 'circle' : 'ring'} color={i < 2 ? '#0B0B0D' : i === 2 ? '#B54708' : '#D4D4D8'} />
              <span className={`font-tc text-sm ${i < 2 ? 'text-ink' : i === 2 ? 'font-bold text-[#93370D]' : 'text-graphite'}`}>{name}</span>
            </li>
          ))}
        </ol>
        <p className="-mt-6 m-0 font-tc text-[13px] text-dim md:hidden">步驟 3 / {STAGES.length} · <b className="text-[#93370D]">{STAGES[2][1]}</b> · 下一步：{STAGES[3][1]}</p>

        <div className="flex flex-wrap items-end gap-x-14 gap-y-8 max-md:gap-y-4 max-md:bg-mist max-md:p-5">
          <div className="flex items-baseline gap-2.5">
            <span className="text-[88px] leading-[0.85] font-semibold tracking-[-0.05em] max-md:text-[56px]">{job.items.length}</span>
            <span className="font-tc text-[15px] text-dim">筆查詢<br />{job.items.length - adds} 舊條目 + {adds} 新書目</span>
          </div>
          <div className="flex flex-[1_1_420px] flex-col gap-3">
            <div className="flex h-2.5 gap-0.5">
              {counts.none > 0 && <div style={{ flex: counts.none, background: '#C8281E' }} />}
              {counts.fuzzy > 0 && <div style={{ flex: counts.fuzzy, background: '#EAB308' }} />}
              {counts.exact > 0 && <div style={{ flex: counts.exact, background: '#0E7C47' }} />}
            </div>
            <div className="flex flex-wrap gap-x-6 gap-y-2 font-mono text-[13px]">
              <span className="flex items-center gap-2 text-[#9F1F17]"><Mark shape="ring" color="#C8281E" />none {counts.none}</span>
              <span className="flex items-center gap-2 text-[#854D0E]"><Mark shape="circle" color="#EAB308" />fuzzy {counts.fuzzy}</span>
              <span className="flex items-center gap-2 text-[#0A6639]"><Mark shape="square" color="#0E7C47" />exact {counts.exact}</span>
            </div>
          </div>
        </div>

        <div className="flex flex-wrap items-center gap-x-3 gap-y-2 border border-line px-5 py-3 font-tc text-sm">
          <span>跳過不調整的條目 <span className="font-mono">{skipped} / {editable.length}</span></span>
          <span className="text-dim">勾選的條目保持原樣寫回，只會跟著重新編號。</span>
          <span className="ml-auto flex gap-2">
            <button type="button" disabled={busy !== null || !waiting} className={btn.ghost} onClick={() => skipAll(true)}>全選</button>
            <button type="button" disabled={busy !== null || !waiting} className={btn.ghost} onClick={() => skipAll(false)}>全不選</button>
          </span>
        </div>

        <section className="flex flex-col gap-4">
          <div className="flex items-baseline gap-3"><h2 className="m-0 font-tc text-[22px] font-bold">需要注意</h2><span className="font-mono text-[13px] text-graphite">{attention.length} 筆 · none 與 fuzzy 排在最前面</span></div>
          {!attention.length && <p className="m-0 border border-line px-5 py-4 font-tc text-sm text-dim">沒有需要注意的條目，可以直接繼續。</p>}
          {attention.map(({ it, i }) => {
            const m = it.meta!
            const none = m.match === 'none'
            const isAdd = it.kind === 'add'
            return (
              <article key={i} className={`flex flex-col gap-5 border-2 p-6 max-md:gap-4 max-md:p-4 ${none ? 'border-fail bg-[#FFFBFA]' : 'border-[#EAB308] bg-[#FFFDF2]'} ${it.skip ? 'opacity-50' : ''}`}>
                <div className="flex flex-wrap items-center gap-x-3.5 gap-y-2.5">
                  <label className="order-last ml-auto flex cursor-pointer items-center gap-2 font-tc text-sm">{skipBox(it, i)}跳過，不調整</label>
                  <span className={`font-mono text-base font-medium ${isAdd ? 'text-signal' : ''}`}>{label(it)}</span>
                  {isAdd && <span className="border border-signal px-2 py-0.5 font-tc text-xs text-signal">新增書目 · 第 {it.line} 行</span>}
                  {none ? <span className="flex items-center gap-1.5 bg-fail px-2.5 py-1 font-mono text-xs font-medium text-white"><Mark shape="ring" color="#FFFFFF" size={8} />none</span>
                    : <span className="flex items-center gap-1.5 bg-[#FACC15] px-2.5 py-1 font-mono text-xs font-medium text-[#422006]"><Mark shape="circle" color="#422006" size={8} />fuzzy</span>}
                  <span className={`font-tc text-sm ${none ? 'text-[#9F1F17]' : 'text-[#854D0E]'}`}>{m.error ? `查詢失敗：${m.error}` : none ? 'Crossref、OpenAlex、Semantic Scholar 都查不到' : '標題不完全相同，請確認是否為同一篇'}</span>
                </div>
                <div className="grid grid-cols-[repeat(auto-fit,minmax(320px,1fr))] gap-6 max-md:grid-cols-1 max-md:gap-4">
                  <div className="flex flex-col gap-2">
                    <span className="font-tc text-xs font-medium text-graphite">{isAdd ? '你輸入的書目' : '原始條目'}</span>
                    <p className={`m-0 leading-[1.65] ${isAdd ? 'font-mono text-[15px]' : 'font-serif text-base'}`}>{isAdd ? it.original : <Ref text={it.original} />}</p>
                  </div>
                  <div className="flex flex-col gap-2">
                    <span className="font-tc text-xs font-medium text-graphite">系統找到的論文 {!none && <span className="ml-1.5 bg-ink px-1.5 py-0.5 text-[11px] text-white">目前採用</span>}</span>
                    {none
                      ? <div className="flex items-center gap-3.5 border border-dashed border-edge bg-white p-4.5"><Mark shape="dashed" color="#A1A1AA" size={36} /><span className="font-tc text-sm leading-relaxed text-dim">沒有相符的論文。學位論文常不在這些資料庫裡；確定條目沒錯的話，勾選「跳過，不調整」即可。</span></div>
                      : <Paper m={m} chosen />}
                  </div>
                </div>
                {m.candidates.length > 0 && (
                  <div className="flex flex-col gap-2">
                    <span className="font-tc text-xs font-medium text-graphite">其他候選 · {m.candidates.length}</span>
                    <div className="flex flex-col border-t border-line">
                      {m.candidates.map((c, k) => <Cand key={k} c={c} disabled={busy !== null || !waiting} onPick={() => act(i, () => jobs.choose(id, i, k))} />)}
                    </div>
                  </div>
                )}
                <div className="flex flex-wrap items-end gap-2.5">
                  <label className="flex flex-[1_1_360px] flex-col gap-1.5 font-tc text-[13px] font-medium max-md:flex-[1_1_200px]">用更精確的資訊重查
                    <input className={`${input} text-sm`} placeholder="DOI、URL 或完整標題" value={queries[i] || ''} onChange={e => setQueries({ ...queries, [i]: e.target.value })} disabled={!waiting} /></label>
                  <button type="button" disabled={busy !== null || !waiting || !(queries[i] || '').trim()} className={`${btn.outline} max-md:min-h-12`} onClick={() => act(i, async () => setFound({ ...found, [i]: await jobs.research(id, i, queries[i].trim()) }))}>{busy === i ? '查詢中…' : '重查'}</button>
                </div>
                {found[i] && (() => {
                  const f = found[i], list = f.match === 'none' ? [] : [f, ...f.candidates]
                  return (
                    <div className="flex flex-col gap-2">
                      <span className="font-tc text-xs font-medium text-graphite">重查結果 · {list.length}<span className="ml-2 font-normal">目前採用的不變，選一篇才會換</span></span>
                      {list.length
                        ? <div className="flex flex-col border-t border-line">{list.map((c, k) => <Cand key={k} c={c} disabled={busy !== null || !waiting} onPick={() => act(i, () => jobs.choose(id, i, undefined, c))} />)}</div>
                        : <p className="m-0 font-tc text-sm text-[#9F1F17]">{f.error || '查不到，試試 DOI 或更完整的標題。'}</p>}
                    </div>
                  )
                })()}
              </article>
            )
          })}
        </section>

        <section className="flex flex-col gap-3">
          <div className="flex items-baseline gap-3"><h2 className="m-0 font-tc text-[22px] font-bold">精確命中</h2><span className="font-mono text-[13px] text-graphite">{rest.length} 筆</span></div>
          <div className="overflow-x-auto border-t border-ink">
            <div className="min-w-[960px] max-md:min-w-0">
                <div className="flex items-center gap-2 px-1 py-2 font-tc text-xs text-graphite">左側勾選 = 跳過，不調整</div>
              {(showAll ? rest : rest.slice(0, 5)).map(({ it, i }) => {
                const m = it.meta
                const dup = it.status === 'duplicate'
                const mt = m ? MATCH[m.match] : MATCH.none
                return (
                  <div key={i} className={`grid grid-cols-[20px_56px_minmax(0,4fr)_minmax(0,4fr)_150px_120px] items-center gap-5 border-b border-line px-1 py-4 max-md:grid-cols-[20px_minmax(0,1fr)] max-md:items-start max-md:gap-x-3 max-md:gap-y-1.5 max-md:[grid-template-areas:'box_label'_'box_orig'_'box_found'_'box_doi'_'box_match'] ${dup ? 'bg-[#FAFAFA]' : ''} ${it.skip ? 'opacity-50' : ''}`}>
                    <span className="flex max-md:[grid-area:box]">{!dup && skipBox(it, i)}</span>
                    <span className={`font-mono text-sm max-md:[grid-area:label] ${it.kind === 'add' ? 'text-signal' : ''}`}>{label(it)}</span>
                    <span className={`truncate text-dim max-md:[grid-area:orig] ${it.kind === 'add' ? 'font-mono text-[13px]' : 'font-serif text-[15px]'}`}>{it.kind === 'add' ? it.original : <Ref text={it.original} />}</span>
                    {dup ? <span className="flex items-center gap-2 font-tc text-[13px] text-dim max-md:[grid-area:found]"><span className="border border-faint px-1.5 text-[11px]">重複</span>已在清單 [{it.duplicate_of}]，不重複新增</span>
                      : m?.kept ? <span className="font-tc text-[13px] text-dim max-md:[grid-area:found]">保留原樣</span>
                      : <span className="flex min-w-0 flex-col gap-0.5 max-md:[grid-area:found]"><span className="truncate text-sm font-semibold">{m?.title}</span><span className="text-xs text-dim">{m?.year}{m?.venue ? <> · <em>{m.venue}</em></> : ''}</span></span>}
                    <span className="truncate max-md:[grid-area:doi]"><Doi doi={m?.doi} /></span>
                    <span className="flex items-center gap-2 font-mono text-xs max-md:[grid-area:match]"><span className="px-1.5 py-0.5" style={{ background: mt.bg, color: mt.fg }}>{m?.match}</span><span className="text-graphite">{sourceName(m?.source)}</span></span>
                  </div>
                )
              })}
            </div>
          </div>
          {rest.length > 5 && !showAll && <button type="button" className={`${btn.ghost} self-start max-md:justify-center max-md:self-stretch`} onClick={() => setShowAll(true)}>顯示其餘 {rest.length - 5} 筆</button>}
        </section>

        {waiting && (
          <div className="flex flex-wrap items-center gap-x-8 gap-y-5 border-t-2 border-ink pt-7 max-md:sticky max-md:bottom-0 max-md:-mx-4 max-md:gap-y-3 max-md:bg-white max-md:px-4 max-md:pt-3.5 max-md:pb-5">
            <p className="m-0 flex-[1_1_360px] font-tc text-sm leading-relaxed text-dim max-md:text-xs">{attention.filter(x => !x.it.skip).length ? `還有 ${attention.filter(x => !x.it.skip).length} 筆需要注意未處理。直接繼續的話，fuzzy 會採用「目前採用」的論文，none 以原始條目套格式；勾選跳過的不會改動。` : '全部確認完畢，繼續後會核對引用順序並套用格式。'}</p>
            <button type="button" disabled={busy !== null} onClick={cont} className="flex min-h-[68px] flex-[0_1_420px] cursor-pointer items-center justify-between gap-4 border-0 bg-ink px-7 font-tc text-lg font-bold text-white disabled:bg-faint max-md:min-h-[60px] max-md:basis-full max-md:px-5">
              <span>{busy === 'continue' ? '繼續中…' : '確認無誤，繼續'}</span><span aria-hidden="true">→</span>
            </button>
          </div>
        )}
      </div>
    </Shell>
  )
}
