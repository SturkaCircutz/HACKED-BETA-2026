import type { Status } from '../api'

export const STATUS_LABEL: Record<Status, string> = {
  open: 'Open',
  action_sent: 'Action sent',
  acknowledged: 'Acknowledged',
  resolved: 'Resolved',
  archived: 'Archived',
}
const ORDER: Status[] = ['open', 'action_sent', 'acknowledged', 'resolved', 'archived']

export function StatusPill({ status }: { status: Status }) {
  return (
    <span className="pill">
      <span className="dot" style={{ background: `var(--s-${status})` }} />
      {STATUS_LABEL[status]}
    </span>
  )
}

/** OPEN -> ACTION SENT -> ACKNOWLEDGED -> RESOLVED -> ARCHIVED */
export function Lifecycle({ status }: { status: Status }) {
  const idx = ORDER.indexOf(status)
  return (
    <div className="lifecycle" aria-label={`Status: ${STATUS_LABEL[status]}`}>
      {ORDER.map((s, i) => (
        <span key={s} className={i <= idx ? 'on' : ''} style={i <= idx ? { background: `var(--s-${s})` } : undefined}>
          {STATUS_LABEL[s]}
        </span>
      ))}
    </div>
  )
}
