import { useState } from 'react'
import { auth } from '../api'
import { Shell, btn, input, type Me } from '../ui'

export default function Settings({ me, onSaved }: { me: Me; onSaved: () => void }) {
  const [author, setAuthor] = useState(me.author)
  const [msg, setMsg] = useState('')
  const save = async (e: React.FormEvent) => {
    e.preventDefault()
    try { await auth.save({ author: author.trim() }); setMsg('已儲存'); onSaved() } catch (x) { setMsg((x as Error).message) }
  }
  return (
    <Shell me={me} active="settings" wide={false}>
      <form onSubmit={save} className="flex max-w-[520px] flex-col gap-6">
        <div className="flex flex-col gap-2">
          <div className="font-mono text-xs tracking-[0.12em] text-graphite">SETTINGS</div>
          <h1 className="m-0 font-tc text-4xl font-bold max-md:text-[26px]">設定</h1>
        </div>
        <label className="flex flex-col gap-2 font-tc text-[13px] font-medium">預設修訂作者 <span className="font-normal text-graphite">（建立新工作時自動填入；留空則用 ESALab-RefBot）</span>
          <input data-tour="author" value={author} onChange={e => setAuthor(e.target.value)} maxLength={64} placeholder="ESALab-RefBot" className={`${input} h-12`} />
        </label>
        <div className="flex items-center gap-4">
          <button type="submit" data-tour="save" className={btn.primary}>儲存</button>
          <span role="status" className="font-tc text-sm text-ok">{msg}</span>
        </div>
      </form>
    </Shell>
  )
}
