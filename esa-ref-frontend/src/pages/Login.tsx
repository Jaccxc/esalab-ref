import { useState } from 'react'
import { auth, setToken } from '../api'
import { Logo, Mark, input, usePlay } from '../ui'

export default function Login({ onDone }: { onDone: () => void }) {
  const [tab, setTab] = useState<'login' | 'register'>('login')
  const [err, setErr] = useState('')
  const [busy, setBusy] = useState(false)
  const submit = async (e: React.FormEvent<HTMLFormElement>) => {
    e.preventDefault()
    const f = new FormData(e.currentTarget)
    setBusy(true)
    try { setToken((await (tab === 'login' ? auth.login : auth.register)(String(f.get('u')), String(f.get('p')))).token); onDone() }
    catch (x) { setErr((x as Error).message) }
    setBusy(false)
  }
  const sq = usePlay(), tri = usePlay()
  const tabCls = (t: typeof tab) => `h-11 cursor-pointer border-0 bg-transparent font-tc text-[15px] ${tab === t ? 'font-bold text-ink shadow-[inset_0_-2px_0_#0B0B0D]' : 'font-medium text-dim'}`
  return (
    <div className="flex min-h-screen flex-wrap bg-white">
      <section className="relative flex min-h-[420px] flex-[1_1_560px] flex-col justify-between overflow-hidden bg-ink px-14 py-12 text-white">
        <div className="flex items-center gap-3.5"><Logo size={14} light /><span className="text-lg font-semibold">ESA Lab</span><span className="font-mono text-[11px] tracking-[0.12em] text-[#8A8A93]">NTPU CSIE</span></div>
        <div className="py-10" aria-hidden="true">
          <div className="hero relative h-[129px] w-[396px]">
            <div {...sq} className={`absolute top-[7px] left-0 h-[120px] w-[120px] bg-white ${sq.className}`} />
            <div className="absolute top-[5px] left-[139px] h-[124px] w-[124px] rounded-full" style={{ boxShadow: 'inset 0 0 0 2px #fff' }} />
            <div {...tri} className={`absolute top-0 left-[261px] h-[127px] w-[135px] bg-signal ${tri.className}`} style={{ clipPath: 'polygon(50% 0, 100% 100%, 0 100%)' }} />
          </div>
        </div>
        <div className="flex max-w-[520px] flex-col gap-3.5">
          <h1 className="m-0 font-tc text-[40px] leading-[1.3] font-bold">參考文獻，<br />交給系統修。</h1>
          <p className="m-0 font-tc text-base leading-[1.75] text-faint">上傳論文 .docx，參考文獻依實驗室 IEEE 格式修正，以 Word 修訂模式寫回。</p>
        </div>
      </section>
      <section className="flex flex-[1_1_440px] items-center justify-center px-6 py-12">
        <form onSubmit={submit} className="flex w-full max-w-[380px] flex-col gap-6">
          <div className="flex flex-col gap-2">
            <div className="font-mono text-xs tracking-[0.12em] text-graphite">REFERENCE REVISER</div>
            <h2 className="m-0 font-tc text-[28px] font-bold">{tab === 'login' ? '歡迎回來' : '建立帳號'}</h2>
          </div>
          <div role="tablist" className="grid grid-cols-2 border-b border-line">
            <button type="button" role="tab" aria-selected={tab === 'login'} className={tabCls('login')} onClick={() => { setTab('login'); setErr('') }}>登入</button>
            <button type="button" role="tab" aria-selected={tab === 'register'} className={tabCls('register')} onClick={() => { setTab('register'); setErr('') }}>註冊</button>
          </div>
          <label className="flex flex-col gap-2 font-tc text-[13px] font-medium">帳號<input name="u" required maxLength={64} autoComplete="username" className={`${input} h-12`} /></label>
          <label className="flex flex-col gap-2 font-tc text-[13px] font-medium">密碼<input name="p" type="password" required minLength={tab === 'register' ? 6 : 1}
            autoComplete={tab === 'login' ? 'current-password' : 'new-password'} className={`${input} h-12 ${err ? 'border-fail' : ''}`} /></label>
          <div role="alert" className="flex min-h-5 items-center gap-2 font-mono text-[13px] text-fail">{err && <><Mark shape="tri" color="#C8281E" size={8} />{err}</>}</div>
          <button type="submit" disabled={busy} className="flex h-13 cursor-pointer items-center justify-between border-0 bg-ink px-5 font-tc text-base font-bold text-white disabled:bg-faint">
            <span>{tab === 'login' ? '登入' : '註冊'}</span><span aria-hidden="true">→</span>
          </button>
          <p className="m-0 font-tc text-[13px] text-graphite">註冊時密碼至少 6 碼，帳號 1–64 字。</p>
        </form>
      </section>
    </div>
  )
}
