import { useEffect, useState } from 'react'
import { api, type Me, type Report } from '../api'
import { StatusPill } from './Lifecycle'

export function MyPins({ onSelect, refresh }: { onSelect: (r: Report) => void; refresh: number }) {
  const [pins, setPins] = useState<Report[] | null>(null)
  const [me, setMe] = useState<Me | null>(null)

  useEffect(() => {
    api.myReports().then(setPins).catch(() => setPins([]))
    api.me().then(setMe).catch(() => setMe(null))
  }, [refresh])

  return (
    <div className="panel" style={{ height: '100%' }}>
      <div className="panel-head"><span className="panel-label main">My pins</span></div>
      <div className="panel-body stack">
        {pins === null ? <div className="muted">Loading…</div> : pins.length === 0 ? (
          <div className="empty">
            <div className="big">No reports yet</div>
            Click “Report” and tap the map where you saw the problem.
          </div>
        ) : (
          <ul className="pin-list">
            {pins.map((p) => (
              <li key={p.id}>
                <button onClick={() => onSelect(p)}>
                  <div className="row" style={{ justifyContent: 'space-between' }}>
                    <strong style={{ textTransform: 'capitalize' }}>{p.category}</strong>
                    <StatusPill status={p.status} />
                  </div>
                  <div className="small muted clamp">{p.story}</div>
                </button>
              </li>
            ))}
          </ul>
        )}
        {me && me.notifications.length > 0 && (
          <div>
            <hr className="sep" />
            <div className="eyebrow">Notifications</div>
            <ul className="timeline">
              {me.notifications.slice(0, 8).map((n) => (
                <li key={n.id}><div className="small">{n.message}</div>
                  <div className="small muted">{new Date(n.created_at).toLocaleString()}</div></li>
              ))}
            </ul>
          </div>
        )}
      </div>
    </div>
  )
}
