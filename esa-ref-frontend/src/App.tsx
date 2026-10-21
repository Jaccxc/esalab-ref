import { useEffect, useState } from 'react'
import { auth, getToken, loadConfig } from './api'
import { useRoute, type Me } from './ui'
import Login from './pages/Login'
import Workbench from './pages/Workbench'
import JobDetail from './pages/JobDetail'
import Preview from './pages/Preview'
import Block from './pages/Block'
import Lookup from './pages/Lookup'
import Admin from './pages/Admin'
import Settings from './pages/Settings'
import Guide from './pages/Guide'
import Mcp from './pages/Mcp'
import { SharePage } from './pages/Share'
import { Tour, type Stage } from './Tour'

export default function App() {
  const [me, setMe] = useState<Me | null | undefined>(getToken() ? undefined : null)
  const [ready, setReady] = useState(false)
  const route = useRoute()
  const load = () => auth.me().then(setMe).catch(() => setMe(null))
  useEffect(() => { loadConfig().then(() => setReady(true)); if (getToken()) load() }, [])
  if (!ready) return null

  if (route[0] === 's' && route[1]) return <SharePage token={route[1]} />  // public, no login
  if (me === undefined) return null
  if (!me) return <Login onDone={load} />
  const page = () => {
    if (route[0] === 'jobs' && route[1]) return route[2] === 'preview' ? <Preview me={me} id={route[1]} /> : route[2] === 'block' ? <Block me={me} id={route[1]} /> : <JobDetail me={me} id={route[1]} />
    if (route[0] === 'lookup') return <Lookup me={me} />
    if (route[0] === 'guide') return <Guide me={me} />
    if (route[0] === 'mcp') return <Mcp me={me} />
    if (route[0] === 'settings') return <Settings me={me} onSaved={load} />
    if (route[0] === 'admin' && me.admin) return <Admin me={me} />
    return <Workbench me={me} />
  }
  const station: Stage | null = route[0] === 'settings' ? 'settings' : route[0] === 'lookup' ? 'lookup' : route.length === 0 ? 'work' : null
  return <>{page()}<Tour me={me} page={station} /></>
}
