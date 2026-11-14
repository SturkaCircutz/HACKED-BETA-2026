import { useCallback, useEffect, useState } from 'react'
import { api, currentUser, type Geometry, type Report } from './api'
import { MapView, type BBox, type PickMode } from './components/MapView'
import { MyPins } from './components/MyPins'
import { PinPanel } from './components/PinPanel'
import { ReportForm } from './components/ReportForm'
import { Workspace } from './components/Workspace'

type View = 'map' | 'case'

export default function App() {
  const [view, setView] = useState<View>('map')
  const [runId, setRunId] = useState<string | null>(null)
  const [user, setUser] = useState(currentUser())

  // map state
  const [bbox, setBbox] = useState<BBox | null>(null)
  const [reports, setReports] = useState<Report[]>([])
  const [mode, setMode] = useState<PickMode>('browse')
  const [vertices, setVertices] = useState<[number, number][]>([])
  const [draft, setDraft] = useState<Geometry | null>(null)
  const [selected, setSelected] = useState<string | null>(null)
  const [flyTo, setFlyTo] = useState<{ lng: number; lat: number; seq: number } | null>(null)
  const [refresh, setRefresh] = useState(0)
  const [q, setQ] = useState('')
  const [hits, setHits] = useState<{ name: string; lat: number; lng: number }[]>([])

  const reporting = mode !== 'browse'

  useEffect(() => {
    if (!bbox) return
    const t = setTimeout(() => api.listReports(bbox).then(setReports).catch(() => {}), 200)
    return () => clearTimeout(t)
  }, [bbox, refresh])

  function startReport(m: 'point' | 'polygon') {
    setSelected(null); setDraft(null); setVertices([]); setMode(m)
  }
  function cancelReport() {
    setMode('browse'); setDraft(null); setVertices([])
  }
  const finishPolygon = useCallback(() => {
    setVertices((vs) => {
      if (vs.length >= 3) setDraft({ type: 'Polygon', coordinates: [[...vs, vs[0]]] })
      return vs
    })
  }, [])

  function openCase(id: string) {
    setRunId(id); setView('case'); cancelReport(); setRefresh((n) => n + 1)
  }

  function showPin(reportId: string) {
    setView('map'); setSelected(reportId)
    api.getReport(reportId).then((r) => setFlyTo({ lng: r.lng, lat: r.lat, seq: Date.now() })).catch(() => {})
  }

  async function search(e: React.FormEvent) {
    e.preventDefault()
    if (q.trim().length > 1) setHits(await api.searchPlace(q).catch(() => []))
  }

  let side
  if (reporting) {
    side = <ReportForm geometry={draft} vertexCount={vertices.length} onCancel={cancelReport} onStarted={openCase} />
  } else if (selected) {
    side = <PinPanel key={selected + refresh} reportId={selected} onClose={() => setSelected(null)} onOpenCase={openCase}
      onChanged={() => setRefresh((n) => n + 1)} />
  } else {
    side = <MyPins refresh={refresh} onSelect={(r) => { setSelected(r.id); setFlyTo({ lng: r.lng, lat: r.lat, seq: Date.now() }) }} />
  }

  return (
    <div className="app">
      <header className="topbar">
        <div className="brand"><span className="brand-dot" />Eco311</div>
        <nav className="nav" aria-label="Views">
          <button aria-current={view === 'map' ? 'page' : undefined} onClick={() => setView('map')}>Map</button>
          <button aria-current={view === 'case' ? 'page' : undefined} disabled={!runId} onClick={() => setView('case')}>Case workspace</button>
        </nav>
        <span className="spacer" />
        <label className="user-chip">
          dev user
          <input value={user} onChange={(e) => setUser(e.target.value)} onBlur={() => {
            try { localStorage.setItem('eco311.user', user || 'demo') } catch { /* storage unavailable */ }
            setRefresh((n) => n + 1)
          }} />
        </label>
      </header>

      <main style={{ minHeight: 0, display: 'grid' }}>
        <div className="map-view" style={{ display: view === 'map' ? undefined : 'none' }}>
          <div className="map-wrap">
            <MapView reports={reports} mode={mode} draft={draft} draftVertices={vertices} selectedId={selected} flyTo={flyTo}
              onBounds={setBbox} onSelect={setSelected}
              onPoint={(ll) => setDraft({ type: 'Point', coordinates: ll })}
              onVertex={(ll) => { if (!draft) setVertices((vs) => [...vs, ll]) }}
              onFinishPolygon={finishPolygon} />
            <div className="map-toolbar">
              <div className="seg" role="group" aria-label="Map mode">
                <button aria-pressed={mode === 'browse'} onClick={cancelReport}>Browse</button>
                <button aria-pressed={mode === 'point'} onClick={() => startReport('point')}>Report · pin</button>
                <button aria-pressed={mode === 'polygon'} onClick={() => startReport('polygon')}>Report · area</button>
              </div>
              <form className="search" onSubmit={search}>
                <input value={q} onChange={(e) => { setQ(e.target.value); if (!e.target.value) setHits([]) }} placeholder="Search a place…" aria-label="Search a place" />
                {hits.length > 0 && (
                  <ul>{hits.map((h) => (
                    <li key={h.name}><button type="button" onClick={() => { setFlyTo({ ...h, seq: Date.now() }); setHits([]) }}>{h.name}</button></li>
                  ))}</ul>
                )}
              </form>
            </div>
            {mode === 'polygon' && !draft && <div className="map-hint">Click to add corners · double-click to finish{vertices.length ? ` (${vertices.length})` : ''}</div>}
            {mode === 'point' && !draft && <div className="map-hint">Click where you saw the problem</div>}
            {(draft && reporting) && <div className="map-hint">Region selected · <button className="btn ghost sm" onClick={() => { setDraft(null); setVertices([]) }}>Redo</button></div>}
            <div className="legend" aria-label="Legend">
              {(['open', 'action_sent', 'acknowledged', 'resolved'] as const).map((s) => (
                <span key={s} className="row" style={{ gap: 6 }}><span className="pill" style={{ padding: 0, border: 0 }}><span className="dot" style={{ background: `var(--s-${s})` }} /></span>{s.replace('_', ' ')}</span>
              ))}
            </div>
          </div>
          <aside className="side">{side}</aside>
        </div>
        {view === 'case' && runId && <Workspace runId={runId} onShowPin={showPin} />}
      </main>
    </div>
  )
}
