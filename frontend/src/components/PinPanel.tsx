import { useCallback, useEffect, useState } from 'react'
import { api, currentUser, type ReportDetail, type StatusEvent } from '../api'
import { Lifecycle, STATUS_LABEL } from './Lifecycle'

interface Props {
  reportId: string
  onClose: () => void
  onOpenCase: (runId: string) => void
  onChanged: () => void
}

export function PinPanel({ reportId, onClose, onOpenCase, onChanged }: Props) {
  const [report, setReport] = useState<ReportDetail | null>(null)
  const [events, setEvents] = useState<StatusEvent[]>([])
  const [runs, setRuns] = useState<{ id: string; status: string }[]>([])
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')

  const load = useCallback(async () => {
    const [r, ev] = await Promise.all([api.getReport(reportId), api.reportEvents(reportId)])
    setReport(r)
    setEvents(ev)
    setRuns(r.user_id === currentUser() ? await api.runsForReport(reportId) : [])
  }, [reportId])

  useEffect(() => {
    load().catch((e) => setError(e.message))
  }, [load])

  async function act(fn: () => Promise<unknown>) {
    setBusy(true)
    setError('')
    try {
      await fn()
      await load()
      onChanged()
    } catch (e) {
      setError((e as Error).message)
    } finally {
      setBusy(false)
    }
  }

  if (!report) return <div className="panel" style={{ height: '100%' }}><div className="panel-body muted">{error || 'Loading…'}</div></div>
  const mine = report.user_id === currentUser()

  return (
    <div className="panel" style={{ height: '100%' }}>
      <div className="panel-head">
        <span className="panel-label main">{report.category}</span>
        <span className="spacer" />
        <button className="btn ghost sm" onClick={onClose} aria-label="Close">✕</button>
      </div>
      <div className="panel-body stack">
        <Lifecycle status={report.status} />
        <div>
          <div className="eyebrow">Location</div>
          <div>{report.address ?? `${report.lat.toFixed(5)}, ${report.lng.toFixed(5)}`}</div>
        </div>
        <div>
          <div className="eyebrow">Story</div>
          <div>{report.story || <span className="muted">No story</span>}</div>
        </div>
        {report.photos.length > 0 && (
          <div>
            <div className="eyebrow">Photos (before / after)</div>
            <div className="photos">
              {report.photos.map((p) => (
                <figure key={p.id}>
                  <a href={p.url} target="_blank" rel="noreferrer"><img src={p.url} alt={p.analysis?.description || `${p.kind} photo`} /></a>
                  <figcaption>{p.kind}</figcaption>
                </figure>
              ))}
            </div>
          </div>
        )}

        <div>
          <div className="eyebrow">Is it still there?</div>
          <div className="row">
            <button className="btn" disabled={busy} onClick={() => act(() => api.confirm(reportId, 'still_there'))}>
              Still there · {report.still_there}
            </button>
            <button className="btn" disabled={busy} onClick={() => act(() => api.confirm(reportId, 'gone'))}>
              Gone · {report.gone}
            </button>
            <label className="btn sm ghost" style={{ cursor: 'pointer' }}>
              + after photo
              <input type="file" accept="image/*" capture="environment" hidden onChange={(e) => {
                const f = e.target.files?.[0]
                if (f) act(async () => api.attachPhoto(reportId, await api.uploadPhoto(f), 'after'))
              }} />
            </label>
          </div>
        </div>

        <div>
          <div className="eyebrow">Timeline</div>
          <ul className="timeline">
            {events.map((ev) => (
              <li key={ev.id} style={{ ['--c' as string]: `var(--s-${ev.status})` }}>
                <strong>{STATUS_LABEL[ev.status]}</strong> <span className="muted small">{new Date(ev.created_at).toLocaleString()}</span>
                {ev.note && <div className="small muted">{ev.note}</div>}
              </li>
            ))}
          </ul>
          {report.followup_at && <div className="small muted">Next “still there?” check: {new Date(report.followup_at).toLocaleDateString()}</div>}
        </div>
        {error && <div className="error-box">{error}</div>}
      </div>
      <div className="composer" style={{ flexWrap: 'wrap' }}>
        {mine ? (
          <>
            {runs[0] && <button className="btn" onClick={() => onOpenCase(runs[0].id)}>Open case</button>}
            <button className="btn primary" disabled={busy}
              onClick={() => act(async () => onOpenCase((await api.startRun({ report_id: reportId })).id))}>
              {runs.length ? 'Run agent again' : 'Ask the agent'}
            </button>
            <span className="spacer" />
            <button className="btn danger sm" disabled={busy}
              onClick={() => act(async () => { await api.deleteReport(reportId); onClose() })}>Remove pin</button>
          </>
        ) : (
          <button className="btn" disabled={busy} onClick={() => act(() => api.subscribe(reportId))}>Follow this pin</button>
        )}
      </div>
    </div>
  )
}
