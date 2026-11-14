import { useCallback, useEffect, useState } from 'react'
import { api, currentUser, type Geometry, type Report } from './api'
import { MapView, type BBox, type PickMode } from './components/MapView'
import { MyPins } from './components/MyPins'
import { PinPanel } from './components/PinPanel'
import { ReportForm } from './components/ReportForm'
import { Workspace } from './components/Workspace'

type View = 'home' | 'map' | 'case'

const SUSTAINABILITY_SLIDES = [
  {
    title: 'What is sustainability?',
    description: "Sustainability means meeting our needs today without limiting the opportunities of future generations. It connects the health of our environment with the well-being of our communities and the way we use resources. The goal is to make choices that still make sense tomorrow.",
  },
  {
    title: 'Keep resources in use.',
    description: "Making and transporting everyday products takes materials, water, and energy. Choosing less, using things longer, repairing what we can, and recycling items accepted by local programs can reduce unnecessary waste. Often, the most sustainable item is one we already own.",
  },
  {
    title: 'Cleaner spaces protect more than appearances.',
    description: "Litter and illegal dumping can threaten wildlife, affect waterways, and make public places less welcoming. Small, safe cleanups help, but sharp objects, unknown chemicals, and other hazards need the right professionals and disposal services. Good intentions matter most when the action is safe.",
  },
  {
    title: 'Community change starts locally.',
    description: "Sustainability grows through consistent choices and shared responsibility. Notice an issue, learn the local guidance, take the safe next step, and follow through when needed. Zero Hero helps turn an observation into a practical action, one neighbourhood at a time.",
  },
] as const

function readRoute(): { view: View; runId: string | null } {
  const hash = window.location.hash
  if (hash === '#/map') return { view: 'map', runId: null }
  if (hash.startsWith('#/case/')) {
    try {
      const id = decodeURIComponent(hash.slice(7))
      if (id) return { view: 'case', runId: id }
    } catch { return { view: 'home', runId: null } }
  }
  return { view: 'home', runId: null }
}

export default function App() {
  const [view, setView] = useState<View>(() => readRoute().view)
  const [runId, setRunId] = useState<string | null>(() => readRoute().runId)
  const [user, setUser] = useState(currentUser())
  const [sustainIndex, setSustainIndex] = useState(0)
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
    const onRoute = () => {
      const next = readRoute()
      setView(next.view)
      if (next.runId) setRunId(next.runId)
    }
    window.addEventListener('hashchange', onRoute)
    return () => window.removeEventListener('hashchange', onRoute)
  }, [])

  useEffect(() => {
    if (!bbox || view !== 'map') return
    let active = true
    const t = setTimeout(() => api.listReports(bbox).then((value) => {
      if (active) setReports(value)
    }).catch(() => {}), 200)
    return () => { active = false; clearTimeout(t) }
  }, [bbox, refresh, view])

  function navigate(next: View, id = runId) {
    if (next === 'case' && !id) return
    setView(next)
    window.location.hash = next === 'home' ? '/' : next === 'map' ? '/map' : `/case/${encodeURIComponent(id!)}`
  }

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
    setRunId(id); cancelReport(); setRefresh((n) => n + 1); navigate('case', id)
  }

  function showPin(reportId: string) {
    cancelReport(); setSelected(reportId); setRefresh((n) => n + 1); navigate('map')
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
    <div className={`app zh-app ${view === 'home' ? 'zh-at-home' : ''}`}>
      <header className="topbar">
        <button className="brand zh-brand" onClick={() => navigate('home')} aria-label="Zero Hero home">
          <span className="zh-logo zh-logo-nav"><img src="/zero-hero-logo.webp" alt="" /></span>
          <span>ZERO <span className="zh-brand-accent">HERO</span><small>Small actions. Greener tomorrow.</small></span>
        </button>
        <nav className="nav" aria-label="Main navigation">
          <button aria-current={view === 'home' ? 'page' : undefined} onClick={() => navigate('home')}>Home</button>
          <button aria-current={view === 'map' ? 'page' : undefined} onClick={() => navigate('map')}>Explore map</button>
          {runId && <button aria-current={view === 'case' ? 'page' : undefined} onClick={() => navigate('case')}>My case</button>}
        </nav>
        <label className="user-chip">
          Your name
          <input aria-label="Your name" value={user} onChange={(e) => setUser(e.target.value)} onBlur={() => {
            try { localStorage.setItem('eco311.user', user.trim() || 'demo') } catch {}
            setUser(user.trim() || 'demo'); setRefresh((n) => n + 1)
          }} />
        </label>
      </header>
      <main className={`zh-main ${view === 'home' ? 'zh-main-home' : ''}`}>
        {view === 'home' && <section className="zh-landing" aria-labelledby="zh-home-title">
          <div className="zh-hero-stage">
            <div className="zh-hero-copy">
              <h1 id="zh-home-title">Zero <span>Hero.</span></h1>
              <p className="zh-hero-tagline">Less waste.<br />More possibility.</p>
              <p className="zh-hero-description">Your neighbourhood is worth caring for. See an issue, find a better next step, and make a difference.</p>
              <button className="zh-start" onClick={() => navigate('map')}>Get started <span aria-hidden="true">↗</span></button>
            </div>
            <div className="zh-hero-art">
              <span className="zh-logo zh-logo-hero"><img src="/zero-hero-logo.webp" alt="Zero Hero: a smiling recycling bin beside a green tree" fetchPriority="high" /></span>
            </div>
          </div>
          <section className="zh-sustain-section" aria-labelledby="zh-sustain-title">
            <div className="zh-sustain-container" role="region" aria-roledescription="carousel" aria-label="Sustainability explained">
              <h2 id="zh-sustain-title">A greener future starts with understanding.</h2>
              <article className="zh-sustain-slide" aria-live="polite" aria-atomic="true">
                <h3>{SUSTAINABILITY_SLIDES[sustainIndex].title}</h3>
                <p>{SUSTAINABILITY_SLIDES[sustainIndex].description}</p>
              </article>
              <div className="zh-sustain-controls" aria-label="Sustainability carousel controls">
                <button type="button" className="zh-sustain-arrow" aria-label="Previous sustainability topic" onClick={() => setSustainIndex((i) => (i - 1 + SUSTAINABILITY_SLIDES.length) % SUSTAINABILITY_SLIDES.length)}>←</button>
                <div className="zh-sustain-progress" aria-label={`Topic ${sustainIndex + 1} of ${SUSTAINABILITY_SLIDES.length}`}>
                  {SUSTAINABILITY_SLIDES.map((slide, index) => (
                    <button key={slide.title} type="button" className={`zh-sustain-progress-step ${index === sustainIndex ? 'is-active' : ''}`} aria-label={`Show topic ${index + 1}: ${slide.title}`} aria-current={index === sustainIndex ? 'step' : undefined} onClick={() => setSustainIndex(index)} />
                  ))}
                </div>
                <button type="button" className="zh-sustain-arrow" aria-label="Next sustainability topic" onClick={() => setSustainIndex((i) => (i + 1) % SUSTAINABILITY_SLIDES.length)}>→</button>
              </div>
              <span className="zh-sustain-count">{String(sustainIndex + 1).padStart(2, '0')} / {String(SUSTAINABILITY_SLIDES.length).padStart(2, '0')}</span>
            </div>
          </section>
        </section>}
        {view === 'map' && <div className="map-view">
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
                {hits.length > 0 && <ul>{hits.map((h) => (
                  <li key={h.name}><button type="button" onClick={() => { setFlyTo({ ...h, seq: Date.now() }); setHits([]) }}>{h.name}</button></li>
                ))}</ul>}
              </form>
            </div>
            {mode === 'polygon' && !draft && <div className="map-hint">Click to add corners · double-click to finish{vertices.length ? ` (${vertices.length})` : ''}</div>}
            {mode === 'point' && !draft && <div className="map-hint">Click where you saw the problem</div>}
            {draft && reporting && <div className="map-hint">Region selected · <button className="btn ghost sm" onClick={() => { setDraft(null); setVertices([]) }}>Redo</button></div>}
            <div className="legend" aria-label="Legend">
              {(['open', 'action_sent', 'acknowledged', 'resolved'] as const).map((s) => (
                <span key={s} className="row" style={{ gap: 6 }}><span className="pill" style={{ padding: 0, border: 0 }}><span className="dot" style={{ background: `var(--s-${s})` }} /></span>{s.replace('_', ' ')}</span>
              ))}
            </div>
          </div>
          <aside className="side">{side}</aside>
        </div>}
        {view === 'case' && runId && <Workspace key={runId} runId={runId} onShowPin={showPin} onBackToMap={() => navigate('map')} onRestart={openCase} />}
      </main>
    </div>
  )
}
