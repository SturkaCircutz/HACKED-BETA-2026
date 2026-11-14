import { useCallback, useEffect, useLayoutEffect, useRef, useState } from 'react'
import { api, streamRun, type Branch, type CallDraft, type Run } from '../api'
import { ApprovalCard } from './ApprovalCard'
import { branchIndex, branchVars } from '../branchColors'
import { BranchPanel, type DraftBranch } from './BranchPanel'
import { Md } from './Md'

interface Props { runId: string; onShowPin: (reportId: string) => void }

/** Reference-pinned split workspace: LEFT = main conversation (pinned), RIGHT = active branch. */
export function Workspace({ runId, onShowPin }: Props) {
  const [run, setRun] = useState<Run | null>(null)
  const [branches, setBranches] = useState<Branch[]>([])
  const [activeId, setActiveId] = useState<string | null>(null)
  const [draft, setDraft] = useState<DraftBranch | null>(null)
  const [busy, setBusy] = useState(false)
  const [branchBusy, setBranchBusy] = useState(false)
  const [error, setError] = useState('')
  const [followup, setFollowup] = useState('')
  const [selPop, setSelPop] = useState<{ x: number; y: number; eventId: number; text: string } | null>(null)
  const leftBody = useRef<HTMLDivElement>(null)
  const ws = useRef<HTMLDivElement>(null)
  const rightCol = useRef<HTMLDivElement>(null)
  const [arrow, setArrow] = useState<{ x1: number; x2: number; y: number; color: string } | null>(null)

  // ---- load + stream -------------------------------------------------------------------------
  const follow = useCallback((after: number) => {
    return streamRun(runId, after,
      (ev) => setRun((r) => (r && !r.events.some((e) => e.id === ev.id) ? { ...r, events: [...r.events, ev] } : r)),
      () => api.getRun(runId).then(setRun))
  }, [runId])

  useEffect(() => {
    let stop = () => {}
    setRun(null); setBranches([]); setActiveId(null); setDraft(null)
    api.getRun(runId).then((r) => {
      setRun(r)
      if (r.status === 'running') stop = follow(r.events.at(-1)?.id ?? 0)
    }).catch((e) => setError(e.message))
    api.listBranches(runId).then((bs) => {
      setBranches(bs)
      setActiveId(bs.find((b) => !b.closed)?.id ?? null)
    })
    return () => stop()
  }, [runId, follow])

  // ---- anchors + connector arrow -------------------------------------------------------------
  const anchorsByEvent = new Map<number, Branch[]>()
  branches.filter((b) => !b.closed).forEach((b) => anchorsByEvent.set(b.anchor_event_id, [...(anchorsByEvent.get(b.anchor_event_id) ?? []), b]))
  const activeBranch = branches.find((b) => b.id === activeId)
  const activeAnchor = draft?.anchorEventId ?? activeBranch?.anchor_event_id ?? null

  const updateArrow = useCallback(() => {
    const el = activeAnchor != null ? document.getElementById(`step-${activeAnchor}`) : null
    if (!el || !ws.current || !leftBody.current || !rightCol.current) return setArrow(null)
    const w = ws.current.getBoundingClientRect()
    const a = el.getBoundingClientRect()
    const viewport = leftBody.current.getBoundingClientRect()
    const y = a.top + Math.min(a.height / 2, 40)
    if (y < viewport.top || y > viewport.bottom) return setArrow(null)
    const idx = draft ? branches.length : activeBranch ? branchIndex(activeBranch) : 0
    setArrow({ x1: a.right - w.left, x2: rightCol.current.getBoundingClientRect().left - w.left - 4, y: y - w.top,
      color: `var(--b${idx % 6})` })
  }, [activeAnchor, draft, activeBranch, branches.length])

  useLayoutEffect(updateArrow, [updateArrow, run?.events.length])
  useEffect(() => {
    window.addEventListener('resize', updateArrow)
    return () => window.removeEventListener('resize', updateArrow)
  }, [updateArrow])

  function jumpTo(eventId: number) {
    document.getElementById(`step-${eventId}`)?.scrollIntoView({ behavior: 'smooth', block: 'center' })
  }

  // ---- actions -------------------------------------------------------------------------------
  async function guard(fn: () => Promise<void>, setB = setBusy) {
    setB(true); setError('')
    try { await fn() } catch (e) { setError((e as Error).message) } finally { setB(false) }
  }

  const resume = (body: Parameters<typeof api.resume>[1]) => guard(async () => {
    const lastId = run?.events.at(-1)?.id ?? 0
    await api.resume(runId, body)
    setRun((r) => (r ? { ...r, status: 'running' } : r))
    follow(lastId)
  })

  function openBranchDraft(eventId: number, selection = '') {
    const ev = run?.events.find((e) => e.id === eventId)
    setDraft({ anchorEventId: eventId, selection, anchorTitle: ev?.title ?? '' })
    setSelPop(null)
  }

  const createBranch = (question: string) => guard(async () => {
    const b = await api.createBranch(runId, draft!.anchorEventId, draft!.selection, question)
    setBranches((bs) => [...bs, b]); setActiveId(b.id); setDraft(null)
  }, setBranchBusy)

  const sendBranch = (id: string, text: string) => guard(async () => {
    setBranches((bs) => bs.map((b) => (b.id === id ? { ...b, messages: [...b.messages, { role: 'user', content: text }] } : b)))
    const b = await api.branchMessage(id, text)
    setBranches((bs) => bs.map((x) => (x.id === id ? b : x)))
  }, setBranchBusy)

  const setClosed = (id: string, closed: boolean) => guard(async () => {
    const b = await api.setBranchClosed(id, closed)
    const next = branches.map((x) => (x.id === id ? b : x))
    setBranches(next)
    if (closed && activeId === id) setActiveId(next.find((x) => !x.closed)?.id ?? null)
    if (!closed) { setActiveId(id); setDraft(null) }
  }, setBranchBusy)

  const sendFollowup = (e: React.FormEvent) => {
    e.preventDefault()
    const text = followup.trim()
    if (!text) return
    setFollowup('')
    guard(async () => {
      const evs = await api.sendMessage(runId, text)
      setRun((r) => (r ? { ...r, events: [...r.events, ...evs] } : r))
      requestAnimationFrame(() => leftBody.current?.scrollTo({ top: leftBody.current.scrollHeight, behavior: 'smooth' }))
    })
  }

  function onMouseUp() {
    const sel = window.getSelection()
    const text = sel?.toString().trim()
    if (!sel || !text || sel.rangeCount === 0) return setSelPop(null)
    const node = sel.anchorNode instanceof Element ? sel.anchorNode : sel.anchorNode?.parentElement
    const stepEl = node?.closest<HTMLElement>('[data-event-id]')
    if (!stepEl) return setSelPop(null)
    const rect = sel.getRangeAt(0).getBoundingClientRect()
    setSelPop({ x: rect.left + rect.width / 2, y: rect.top, eventId: Number(stepEl.dataset.eventId), text: text.slice(0, 400) })
  }

  if (!run) return <div className="empty">{error || 'Loading case…'}</div>

  // ---- render --------------------------------------------------------------------------------
  const lastInterrupt = [...run.events].reverse().find((e) => e.type === 'interrupt')
  const reviewOpen = run.status === 'paused' && lastInterrupt
  const stepNos = new Map(run.events.filter((e) => e.type === 'step').map((e, i) => [e.id, i + 1]))

  return (
    <div className="workspace" ref={ws} style={{ height: '100%', gridTemplateRows: '1fr auto' }}>
      <section className="panel" aria-label="Main conversation">
        <div className="panel-head">
          <span className="panel-label main">Left&nbsp;&nbsp;|&nbsp;&nbsp;Main conversation</span>
          <span className="spacer" />
          <button className="btn sm" onClick={() => onShowPin(run.report_id)}>Show pin</button>
          {run.status === 'running' && <button className="btn sm danger" onClick={() => guard(async () => { setRun(await api.getRun((await api.cancel(runId)).id)) })}>Stop</button>}
        </div>
        <div className="panel-body" ref={leftBody} onScroll={() => { updateArrow(); setSelPop(null) }} onMouseUp={onMouseUp}>
          {run.events.map((ev) => {
            if (ev.type === 'message') {
              const who = ev.node === 'user' ? 'User' : 'Assistant'
              return (
                <div key={ev.id} id={`step-${ev.id}`} data-event-id={ev.id} className={`turn ${ev.node === 'user' ? 'user' : ''}`}>
                  <div className="who">{who}</div>
                  {ev.node === 'user' ? <div className="text">{ev.content}</div> : <Md>{ev.content}</Md>}
                  {ev.node === 'user' && <hr className="sep" />}
                </div>
              )
            }
            if (ev.type === 'step') {
              const stepNo = stepNos.get(ev.id)!
              const anchors = anchorsByEvent.get(ev.id) ?? []
              const first = anchors[0]
              const isActive = ev.id === activeAnchor
              return (
                <div key={ev.id}>
                  {stepNo === 1 && <div className="who turn" style={{ marginBottom: 8 }}>Assistant</div>}
                  <div id={`step-${ev.id}`} data-event-id={ev.id}
                    className={`step ${first || isActive ? 'anchored' : ''} ${isActive ? 'active' : ''}`}
                    style={first ? branchVars(branchIndex(isActive && activeBranch ? activeBranch : first)) : isActive ? branchVars(branches.length) : undefined}>
                    <div className="step-head">
                      <span className="step-num">Step {stepNo}</span>
                      <span className="step-title">{ev.title}</span>
                    </div>
                    <div className="step-body"><Md>{ev.content}</Md></div>
                    <div className="step-actions">
                      <button className="btn sm" onClick={() => openBranchDraft(ev.id)}>Branch ↗</button>
                    </div>
                    {anchors.length > 0 && (
                      <div className="anchors">
                        {anchors.map((b) => (
                          <button key={b.id} className="anchor-badge" style={branchVars(branchIndex(b))}
                            onClick={() => { setActiveId(b.id); setDraft(null) }}>Anchor {b.title.slice(-1)}</button>
                        ))}
                      </div>
                    )}
                  </div>
                </div>
              )
            }
            if (ev.type === 'interrupt') return null
            return (
              <div key={ev.id} className={`small ${ev.type === 'error' ? 'error-box' : 'muted'}`} style={{ margin: '8px 0 16px' }}>
                — {ev.title}{ev.content ? `: ${ev.content}` : ''}
              </div>
            )
          })}

          {run.status === 'running' && <div className="running"><span className="spinner" /> Agent is working…</div>}
          {reviewOpen && run.result?.draft && (
            <ApprovalCard key={lastInterrupt.id} actionType={run.result.action_type!} draft={run.result.draft} busy={busy}
              onApprove={(edited) => resume({ decision: 'approve', draft: edited })}
              onEdit={(instructions) => resume({ decision: 'edit', instructions })}
              onReject={() => resume({ decision: 'reject' })} />
          )}
          {run.status === 'done' && run.result?.delivery?.kind === 'call' && (
            <CallCard run={run} />
          )}
          {error && <div className="error-box">{error}</div>}
        </div>
        <form className="composer" onSubmit={sendFollowup}>
          <input value={followup} onChange={(e) => setFollowup(e.target.value)} placeholder="Ask a follow-up about this case…" aria-label="Follow-up message" />
          <button className="btn" disabled={!followup.trim() || busy}>Send</button>
        </form>
      </section>

      <div ref={rightCol} style={{ display: 'flex', minHeight: 0 }}>
        <div style={{ flex: 1, display: 'flex', minWidth: 0 }}>
          <BranchPanel branches={branches} activeId={activeId} draft={draft} busy={branchBusy}
            anchorTitle={(id) => run.events.find((e) => e.id === id)?.title ?? ''}
            onSwitch={(id) => { setActiveId(id); setDraft(null); const b = branches.find((x) => x.id === id); if (b) jumpTo(b.anchor_event_id) }}
            onCloseBranch={(id) => setClosed(id, true)} onReopen={(id) => setClosed(id, false)}
            onJumpToAnchor={jumpTo} onCreate={createBranch} onSend={sendBranch} onCancelDraft={() => setDraft(null)} />
        </div>
      </div>

      <div className="workspace-foot">Click another branch: LEFT jumps to its anchor; RIGHT restores its chat.</div>

      {arrow && (
        <svg className="connector" style={{ left: 0, top: 0, width: '100%', height: '100%' }} aria-hidden>
          <line x1={arrow.x1} y1={arrow.y} x2={arrow.x2 - 2} y2={arrow.y} stroke={arrow.color} strokeWidth="2.5" />
          <path d={`M ${arrow.x2 - 14} ${arrow.y - 8} L ${arrow.x2} ${arrow.y} L ${arrow.x2 - 14} ${arrow.y + 8}`}
            fill="none" stroke={arrow.color} strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round" />
        </svg>
      )}
      {selPop && (
        <div className="sel-pop" style={{ left: selPop.x, top: selPop.y }}>
          <button className="btn primary sm" onMouseDown={(e) => e.preventDefault()}
            onClick={() => openBranchDraft(selPop.eventId, selPop.text)}>Ask in a branch ↗</button>
        </div>
      )}
    </div>
  )
}

function CallCard({ run }: { run: Run }) {
  const d = run.result!.draft as CallDraft
  const [outcome, setOutcome] = useState('')
  const [ticket, setTicket] = useState('')
  const [done, setDone] = useState(false)
  const [err, setErr] = useState('')
  return (
    <div className="card">
      <h4>Call</h4>
      <div className="stack">
        {d.phone ? <a className="btn go" style={{ justifyContent: 'center' }} href={`tel:${d.phone.replace(/[^\d+]/g, '')}`}>Call {d.contact_name} · {d.phone}</a>
          : <div className="warn">No number found. Check your city's website for its non-emergency line.</div>}
        <ol style={{ margin: 0, paddingLeft: 20 }}>{d.script.map((s, i) => <li key={i}>{s}</li>)}</ol>
        {done ? <div className="small" style={{ color: 'var(--ok)' }}>Call logged. The pin is being tracked.</div> : (
          <>
            <input className="input" placeholder="What did they say?" value={outcome} onChange={(e) => setOutcome(e.target.value)} />
            <div className="row">
              <input className="input" style={{ flex: 1 }} placeholder="Ticket / reference # (optional)" value={ticket} onChange={(e) => setTicket(e.target.value)} />
              <button className="btn primary" onClick={() => api.logCall({ report_id: run.report_id, run_id: run.id, to: d.phone ?? d.contact_name,
                outcome, ticket_number: ticket || undefined }).then(() => setDone(true)).catch((e) => setErr(e.message))}>Log call</button>
            </div>
            {err && <div className="error-box">{err}</div>}
          </>
        )}
      </div>
    </div>
  )
}

