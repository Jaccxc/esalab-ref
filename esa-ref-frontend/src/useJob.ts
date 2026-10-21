import { useCallback, useEffect, useState } from 'react'
import { jobs, type JobState } from './api'

// One job's live state: SSE while it runs, a single fetch otherwise. `reload` is for after review actions.
export function useJob(id: string) {
  const [job, setJob] = useState<JobState | null>(null)
  const [err, setErr] = useState('')
  const reload = useCallback(() => jobs.get(id).then(setJob).catch(x => setErr((x as Error).message)), [id])
  useEffect(() => { reload() }, [reload])
  const live = job?.status === 'running' || job?.status === 'queued'
  useEffect(() => {
    if (!live) return
    const es = jobs.events(id)
    es.onmessage = e => setJob(JSON.parse(e.data))
    // shortcut: on SSE failure (proxy without buffering off, restart) fall back to polling until the page reloads
    let poll: ReturnType<typeof setInterval> | undefined
    es.onerror = () => { es.close(); poll = poll || setInterval(reload, 3000) }
    return () => { es.close(); if (poll) clearInterval(poll) }
  }, [id, live, reload])
  return { job, err, reload }
}
