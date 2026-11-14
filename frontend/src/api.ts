// Typed client for the backend API.

const BASE = import.meta.env.VITE_API_BASE ?? ''

export type Geometry =
  | { type: 'Point'; coordinates: [number, number] }
  | { type: 'Polygon'; coordinates: [number, number][][] }

export type Status = 'open' | 'action_sent' | 'acknowledged' | 'resolved' | 'archived'

export const CATEGORIES = ['trash', 'dumping', 'water', 'air', 'noise', 'graffiti', 'pothole', 'tree', 'other'] as const

export interface Report {
  id: string
  user_id: string
  geometry: Geometry
  lat: number
  lng: number
  story: string
  category: string
  status: Status
  address: string | null
  jurisdiction_id: string | null
  followup_at: string | null
  created_at: string
}

export interface Photo {
  id: string
  kind: 'before' | 'after'
  url: string
  analysis: { issue_type?: string; severity?: string; description?: string } | null
}

export interface ReportDetail extends Report {
  photos: Photo[]
  still_there: number
  gone: number
}

export interface StatusEvent {
  id: number
  status: Status
  note: string
  actor: string
  created_at: string
}

export interface EmailDraft {
  to: string
  to_name: string
  subject: string
  body: string
  contact_verified: boolean
  photo_ids: string[]
}

export interface CallDraft {
  phone: string | null
  contact_name: string
  hours: string | null
  script: string[]
  contact_verified: boolean
}

export interface RunEvent {
  id: number
  type: 'step' | 'message' | 'interrupt' | 'status' | 'error'
  node: string | null
  title: string
  content: string
  data: Record<string, unknown> | null
  created_at: string
}

export type RunStatus = 'running' | 'paused' | 'done' | 'rejected' | 'failed' | 'cancelled'

export interface NearbyPlace {
  name: string
  kind: 'public_bin' | 'library' | 'recycling_depot' | 'public_sorting_station' | string
  address: string
  lat: number
  lng: number
  note: string
  bin_status: string
  maps_url: string
  distance_m?: number
  route_verified: boolean
  walking_minutes: number | null
  walking_minutes_estimate: number | null
}
export interface AgentResponse {
  schema_version: string
  report_id: string | null
  category: string
  priority: 'routine' | 'urgent' | 'emergency'
  summary: string
  jurisdiction: { status: 'inside' | 'outside' | 'unknown'; city: string | null; warnings: string[] }
  clarification: string | null
  reporting: {
    reportable: boolean | null
    requires_311?: boolean | null
    requires_311_reason?: string
    contact_name: string | null
    phone: string | null
    url: string | null
    report_text: string
    status: string
    submitted: boolean
    direct_submission_enabled?: boolean
  }
  assessment?: {
    risk: { level: number; label: string; basis: string }
    requires_311: boolean | null
    requires_311_reason: string
    official_instructions: string[]
    official_instructions_url: string
    materials: Array<{
      name: string
      sustainability_friendly: boolean | null
      recyclable: boolean | null
      recycling_condition: string
      source_url: string
    }>
  }
  steps: string[]
  nearby_places: NearbyPlace[]
  thank_you: string
  follow_up?: string
  sources: Array<{ title: string; url: string }>
  warnings: string[]
  markdown: string
  meta?: { llm_used?: boolean; processing_warning?: string | null }
}
export interface RunResult {
  action_type?: 'email' | 'call'
  draft?: EmailDraft | CallDraft
  delivery?: { kind: 'email' | 'call' | 'guidance'; status: string; action_id?: string; phone?: string | null }
  address?: string
  category?: string
  ai_response?: AgentResponse | null
}

export interface Run {
  id: string
  report_id: string
  status: RunStatus
  result: RunResult | null
  error: string | null
  events: RunEvent[]
}

export interface ChatMessage {
  role: 'user' | 'assistant'
  content: string
}

export interface Branch {
  id: string
  run_id: string
  anchor_event_id: number
  selection: string
  title: string
  messages: ChatMessage[]
  closed: number
}

export interface Me {
  user_id: string
  pins_by_status: Record<string, number>
  notifications: { id: number; report_id: string | null; message: string; created_at: string }[]
}

export function currentUser(): string {
  try {
    return localStorage.getItem('eco311.user') || 'demo'
  } catch {
    return 'demo'
  }
}

function headers(extra: Record<string, string> = {}): Record<string, string> {
  // Dev auth. In production replace with `Authorization: Bearer <JWT>` from the identity provider.
  return { 'X-User-Id': currentUser(), ...extra }
}

async function req<T>(method: string, path: string, body?: unknown): Promise<T> {
  const res = await fetch(BASE + path, {
    method,
    headers: headers(body !== undefined ? { 'Content-Type': 'application/json' } : {}),
    body: body !== undefined ? JSON.stringify(body) : undefined,
  })
  if (!res.ok) {
    const text = await res.text()
    let detail = text
    try {
      detail = JSON.parse(text).detail ?? text
    } catch {
      /* plain text error */
    }
    throw new Error(`${res.status}: ${typeof detail === 'string' ? detail : JSON.stringify(detail)}`)
  }
  return res.status === 204 ? (undefined as T) : res.json()
}

export const api = {
  // Map + reports
  listReports: (bbox: [number, number, number, number], opts: { mine?: boolean; status?: string } = {}) => {
    const q = new URLSearchParams({ bbox: bbox.join(',') })
    if (opts.mine) q.set('mine', 'true')
    if (opts.status) q.set('status', opts.status)
    return req<Report[]>('GET', `/api/reports?${q}`)
  },
  myReports: () => req<Report[]>('GET', '/api/reports?mine=true&status=open,action_sent,acknowledged,resolved'),
  getReport: (id: string) => req<ReportDetail>('GET', `/api/reports/${id}`),
  reportEvents: (id: string) => req<StatusEvent[]>('GET', `/api/reports/${id}/events`),
  patchReport: (id: string, body: Partial<Pick<Report, 'story' | 'category' | 'status'>> & { note?: string }) =>
    req<Report>('PATCH', `/api/reports/${id}`, body),
  deleteReport: (id: string) => req<void>('DELETE', `/api/reports/${id}`),
  confirm: (id: string, vote: 'still_there' | 'gone') => req<ReportDetail>('POST', `/api/reports/${id}/confirm`, { vote }),
  subscribe: (id: string) => req<void>('POST', `/api/reports/${id}/subscribe`),
  attachPhoto: (id: string, photo_id: string, kind: 'before' | 'after') =>
    req<Photo>('POST', `/api/reports/${id}/photos`, { photo_id, kind }),

  // Geo
  searchPlace: (q: string) => req<{ name: string; lat: number; lng: number }[]>('GET', `/api/geo/search?q=${encodeURIComponent(q)}`),

  // Photos: presign, then PUT the bytes straight to storage
  async uploadPhoto(file: File): Promise<string> {
    const pre = await req<{ photo_id: string; upload_url: string; headers: Record<string, string> }>(
      'POST', '/api/uploads/presign', { content_type: file.type || 'image/jpeg' })
    const res = await fetch(pre.upload_url, { method: 'PUT', headers: pre.headers, body: file })
    if (!res.ok) throw new Error(`upload failed: ${res.status}`)
    return pre.photo_id
  },

  // Agent
  startRun: (body: { report_id?: string; geometry?: Geometry; story?: string; category?: string; photo_ids?: string[] }) =>
    req<Run>('POST', '/api/agent/runs', body),
  runsForReport: (reportId: string) => req<Omit<Run, 'events'>[]>('GET', `/api/agent/runs?report_id=${reportId}`),
  getRun: (id: string) => req<Run>('GET', `/api/agent/runs/${id}`),
  resume: (id: string, body: { decision: 'approve' | 'edit' | 'continue'; draft?: Partial<EmailDraft & CallDraft>; instructions?: string }) =>
    req<Run>('POST', `/api/agent/runs/${id}/resume`, body),
  cancel: (id: string) => req<Run>('POST', `/api/agent/runs/${id}/cancel`),
  sendMessage: (id: string, content: string) => req<RunEvent[]>('POST', `/api/agent/threads/${id}/messages`, { content }),

  // Branches
  listBranches: (runId: string) => req<Branch[]>('GET', `/api/agent/runs/${runId}/branches`),
  createBranch: (runId: string, anchor_event_id: number, selection: string, question: string) =>
    req<Branch>('POST', `/api/agent/runs/${runId}/branches`, { anchor_event_id, selection, question }),
  branchMessage: (branchId: string, content: string) => req<Branch>('POST', `/api/agent/branches/${branchId}/messages`, { content }),
  setBranchClosed: (branchId: string, closed: boolean) => req<Branch>('PATCH', `/api/agent/branches/${branchId}?closed=${closed}`),

  // Actions
  logCall: (body: { report_id: string; run_id?: string; to: string; outcome: string; ticket_number?: string }) =>
    req('POST', '/api/actions/call-log', body),

  me: () => req<Me>('GET', '/api/me'),
}

/** Stream run events over SSE (fetch-based, so auth headers work). Returns an abort function. */
export function streamRun(runId: string, after: number, onEvent: (e: RunEvent) => void, onEnd: (status: RunStatus) => void): () => void {
  const ctrl = new AbortController()
  ;(async () => {
    try {
      const res = await fetch(`${BASE}/api/agent/runs/${runId}/stream?after=${after}`, { headers: headers(), signal: ctrl.signal })
      if (!res.body) return
      const reader = res.body.pipeThrough(new TextDecoderStream()).getReader()
      let buf = ''
      for (;;) {
        const { value, done } = await reader.read()
        if (done) break
        buf += value
        let idx
        while ((idx = buf.indexOf('\n\n')) >= 0) {
          const chunk = buf.slice(0, idx)
          buf = buf.slice(idx + 2)
          const type = /^event: (.*)$/m.exec(chunk)?.[1]
          const data = /^data: (.*)$/m.exec(chunk)?.[1]
          if (!data) continue
          if (type === 'end') onEnd(JSON.parse(data).status)
          else onEvent(JSON.parse(data))
        }
      }
    } catch (err) {
      if ((err as Error).name !== 'AbortError') console.error('stream error', err)
    }
  })()
  return () => ctrl.abort()
}
