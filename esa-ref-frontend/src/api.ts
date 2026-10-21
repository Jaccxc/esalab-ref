// Thin client for esa-ref-backend. The token is the only client-side state; identity is always resolved server-side.
const KEY = 'token'
export const getToken = () => localStorage.getItem(KEY) || ''
export const setToken = (t: string) => (t ? localStorage.setItem(KEY, t) : localStorage.removeItem(KEY))

// Public base URL for links we hand out (share links, MCP endpoint): the server's PUBLIC_URL, else where the browser opened us.
let PUBLIC = ''
export const base = () => PUBLIC || location.origin
export const loadConfig = () => api<{ public_url: string }>('/api/config').then(c => { PUBLIC = c.public_url }).catch(() => {})

export class ApiError extends Error {
  status: number
  constructor(status: number, message: string) { super(message); this.status = status }
}

export async function api<T = unknown>(path: string, init: RequestInit = {}): Promise<T> {
  const headers = new Headers(init.headers)
  if (getToken()) headers.set('Authorization', `Bearer ${getToken()}`)
  if (init.body && !(init.body instanceof FormData)) headers.set('Content-Type', 'application/json')
  const r = await fetch(path, { ...init, headers })
  if (r.status === 401) setToken('')
  if (!r.ok) throw new ApiError(r.status, (await r.json().catch(() => ({}))).detail || r.statusText)
  return r.status === 204 ? (undefined as T) : r.json()
}

// EventSource cannot send headers, so the token travels as a query parameter (the backend accepts both).
export const withToken = (path: string) => `${path}?token=${encodeURIComponent(getToken())}`

export type Status = 'queued' | 'running' | 'waiting' | 'done' | 'failed'
export type Mode = 'smart' | 'fix' | 'add'
export type Match = 'exact' | 'fuzzy' | 'none'

export type JobSummary = {
  id: string; user: string; filename: string; mode: Mode; status: Status
  stage: string | null; percent: number; started: number; elapsed: number; changed: number | null; error: string | null; entries: number; ask: boolean; expired: boolean
}

export type Meta = {
  match: Match; candidates: Meta[]; source?: string | null; title?: string; year?: number | null; venue?: string | null
  doi?: string | null; authors?: { given?: string | null; family?: string | null; name?: string | null }[]; kept?: boolean; error?: string
}

export type Item = {
  kind: 'fix' | 'add'; index: number | null; label: string | null; number?: number; line?: number; original: string
  status: 'pending' | 'looked-up' | 'duplicate' | 'formatted' | 'checked'; meta?: Meta; uncertain?: boolean; duplicate_of?: number
  number_final?: number; formatted?: string; final?: string; type?: string; issues?: string[]
  check?: { ok: boolean; problems: string[] }; changed?: boolean; skip?: boolean
}

export type OrderPlan = {
  ok: boolean; order: (number | string)[]; renumber: Record<string, number>; placeholders: Record<string, number>
  uncited: (number | string)[]; unknown: (number | string)[]
}

export type Ask = { reason: 'no_heading' | 'empty' | 'no_labels' | 'blob'; heading: number | null; blob: boolean
  candidates: { index: number; text: string; numbered: string | null; likely: boolean }[] }

export type JobState = Omit<JobSummary, 'ask'> & { ask: Ask | null } & {
  author: string; titles: string[]; review: boolean; stage_done: number; stage_total: number; eta_seconds: number | null
  model: { providerID: string; modelID: string }; items: Item[]; order: OrderPlan | null; log: string[]; body_changed?: number
}

export type Facts = { entries: number; adds: number; changed: number; dup: number; skipped: number; kept: number; unsure: number; passed: number; checked: number; renumbered: number; uncited: number; unknown: number; order_ok: boolean | null; seconds: number }
export type Share = { token: string; user: string; created: number; job: JobState; facts: Facts }
export const share = {
  create: (id: string) => api<Share>(`/api/jobs/${id}/share`, { method: 'POST' }),
  get: (token: string) => api<Share>(`/api/share/${token}`),
  hit: (token: string, via: string) => api(`/api/share/${token}/hit`, { method: 'POST', body: JSON.stringify({ via }) }),
  cardUrl: (token: string) => `/api/share/${token}/card.png`,
  cardSquareUrl: (token: string) => `/api/share/${token}/card-square.png`,
}

export type Me = { username: string; admin: boolean; author: string; tour: string | null }
export type Health = { opencode: boolean; model: unknown; throttled: { source: string; status: number; at: number }[] }
export type GenResult = { reference: string; type: string | null; issues: string[]; check: { ok: boolean; problems: string[] } }
export type Ref = { id: string; created: number; query: string; reference: string; type: string | null; issues: string[]; check: { ok: boolean; problems: string[] } }

export type Stats = {
  users: number; jobs: Record<Status, number>; modes: Record<Mode, number>; review: { on: number; off: number }
  entries: number; changed: number; avg_seconds: number | null; seconds_by_mode: Record<Mode, number | null>
  check_pass_rate: number | null; lookup: Record<Match, number>; sources: Record<string, number>
  items: { fix: number; add: number; duplicate: number; skipped: number; uncertain: number; kept: number; with_issues: number; check_failed: number; error: number }
  types: Record<string, number>; order: { jobs_reordered: number; renumbered: number; placeholders: number; unknown: number }
  asks: Record<string, number>; blocks: Record<string, number>; failures: { by_stage: Record<string, number>; errors: Record<string, number> }
  single_refs: { total: number; check_ok: number; types: Record<string, number>; tasks: Record<string, number> }; cache: number
  api: { via: Record<string, number>; web: Record<string, number>; mcp: Record<string, number>; by_user: Record<string, { web: number; mcp: number }>; logins: number; tours: Record<string, number> }
  shares: { total: number; views: number; hits: Record<string, number> }
  cron: { ping: { t: number | null; apis: Record<string, string> }; purge: { t: number; n: number } | null; expired: number; retain_days: number }
  per_day: Record<string, { jobs: number; done: number; failed: number; entries: number; refs: number }>; hours: number[]; models: Record<string, number>
  per_user: { username: string; created: number | null; tour: string | null; jobs: number; failed: number; entries: number; changed: number; refs: number; last_active: number | null }[]
}

export const auth = {
  login: (username: string, password: string) => api<{ token: string }>('/api/login', { method: 'POST', body: JSON.stringify({ username, password }) }),
  register: (username: string, password: string) => api<{ token: string }>('/api/register', { method: 'POST', body: JSON.stringify({ username, password }) }),
  me: () => api<Me>('/api/me'),
  save: (prefs: { author: string }) => api<Me>('/api/me', { method: 'PUT', body: JSON.stringify(prefs) }),
  tour: (stage: string) => api<{ tour: string }>('/api/me/tour', { method: 'PUT', body: JSON.stringify({ stage }) }),
  health: () => api<Health>('/api/health'),
  token: () => api<{ token: string }>('/api/token', { method: 'POST' }),
}

export const jobs = {
  list: () => api<JobSummary[]>('/api/jobs'),
  get: (id: string) => api<JobState>(`/api/jobs/${id}`),
  create: (fd: FormData) => api<{ id: string }>('/api/jobs', { method: 'POST', body: fd }),
  events: (id: string) => new EventSource(withToken(`/api/jobs/${id}/events`)),
  resultUrl: (id: string) => withToken(`/api/jobs/${id}/result.docx`),
  remove: (id: string) => api(`/api/jobs/${id}`, { method: 'DELETE' }),
  research: (id: string, index: number, query: string) => api<Meta>(`/api/jobs/${id}/research`, { method: 'POST', body: JSON.stringify({ index, query }) }),
  choose: (id: string, index: number, choice?: number, meta?: Meta) => api<Item>(`/api/jobs/${id}/choose`, { method: 'POST', body: JSON.stringify({ index, choice, meta }) }),
  skip: (id: string, indexes: number[], skip: boolean) => api(`/api/jobs/${id}/skip`, { method: 'POST', body: JSON.stringify({ indexes, skip }) }),
  resume: (id: string) => api(`/api/jobs/${id}/continue`, { method: 'POST' }),
  block: (id: string, body: { heading: number | null; paras: number[]; entries?: string[]; append?: boolean }) => api(`/api/jobs/${id}/block`, { method: 'POST', body: JSON.stringify(body) }),
  split: (id: string, text: string) => api<{ entries: string[] }>(`/api/jobs/${id}/split`, { method: 'POST', body: JSON.stringify({ text }) }),
}

export const refs = {
  search: (query: string) => api<Meta>('/api/search', { method: 'POST', body: JSON.stringify({ query }) }),
  // start() kicks off a background task; wait() polls it every 2 s until done/failed, calling onStage with lookup/format/check.
  start: (query: string, meta?: Meta) => api<{ id: string }>('/api/reference', { method: 'POST', body: JSON.stringify({ query, meta }) }),
  wait: async (id: string, onStage: (s: string) => void) => {
    for (;;) {
      const st = await api<{ stage: string; result: GenResult | null; error: string | null }>(`/api/reference/${id}`)
      if (st.stage === 'done' && st.result) return st.result
      if (st.stage === 'failed') throw new ApiError(500, st.error || 'failed')
      onStage(st.stage)
      await new Promise(r => setTimeout(r, 2000))
    }
  },
  history: () => api<Ref[]>('/api/references'),
}

export type Event = { t: number; kind: 'upload' | 'stage' | 'waiting' | 'done' | 'failed' | 'single' | 'account' | 'web' | 'mcp' | 'tour' | 'cron'; user: string; text: string; job: string | null }

export const admin = {
  stats: () => api<Stats>('/api/admin/stats'),
  activity: (hours: number) => api<Event[]>(`/api/admin/activity?hours=${hours}`),
  jobs: () => api<JobSummary[]>('/api/admin/jobs'),
  tour: (username: string, stage: string) => api(`/api/admin/users/${encodeURIComponent(username)}/tour`, { method: 'PUT', body: JSON.stringify({ stage }) }),
}
