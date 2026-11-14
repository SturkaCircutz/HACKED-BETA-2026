import { useCallback, useEffect, useRef, useState } from 'react'
import { api, currentUser, streamRun, type CallDraft, type Run, type RunEvent } from '../api'
import { ApprovalCard } from './ApprovalCard'
import { Md } from './Md'
import { ActionDashboard } from './ActionDashboard'
import { PlanStats } from './PlanStats'

interface Props {
  runId: string
  onShowPin: (reportId: string) => void
  onBackToMap: () => void
  onRestart: (runId: string) => void
}

const statusLabel: Record<Run['status'], string> = {
  running: 'Preparing your plan', paused: 'Ready for your review', done: 'Guidance ready',
  rejected: 'Previous run ended', failed: 'Needs another try', cancelled: 'Paused by you',
}

function appendEvents(current: Run, events: RunEvent[]): Run {
  const byId = new Map(current.events.map((event) => [event.id, event]))
  events.forEach((event) => byId.set(event.id, event))
  return { ...current, events: [...byId.values()].sort((a, b) => a.id - b.id) }
}

export function Workspace({ runId, onShowPin, onBackToMap, onRestart }: Props) {
  const [run, setRun] = useState<Run | null>(null)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')
  const [followup, setFollowup] = useState('')
  const [resolved, setResolved] = useState(false)
  const [notice, setNotice] = useState('')
  const body = useRef<HTMLDivElement>(null)
  const composer = useRef<HTMLInputElement>(null)
  const stopStream = useRef<() => void>(() => {})
  const live = useRef(false)

  const refreshRun = useCallback(async () => {
    const latest = await api.getRun(runId)
    if (live.current) setRun(latest)
    return latest
  }, [runId])

  const follow = useCallback((after: number) => {
    stopStream.current()
    stopStream.current = streamRun(runId, after,
      (event) => { if (live.current) setRun((r) => r ? appendEvents(r, [event]) : r) },
      () => { refreshRun().catch((e) => { if (live.current) setError(e.message) }) })
  }, [runId, refreshRun])

  useEffect(() => {
    let active = true
    live.current = true
    api.getRun(runId).then((r) => {
      if (!active) return
      setRun(r)
      if (r.status === 'running') follow(r.events.at(-1)?.id ?? 0)
      api.getReport(r.report_id).then((report) => {
        if (active) setResolved(report.status === 'resolved')
      }).catch(() => {})
    }).catch((e) => { if (active) setError(e.message) })
    return () => { active = false; live.current = false; stopStream.current() }
  }, [runId, follow])

  useEffect(() => {
    if (run?.status !== 'running') return
    const timer = window.setInterval(() => { refreshRun().catch(() => {}) }, 5000)
    return () => window.clearInterval(timer)
  }, [run?.status, refreshRun])

  async function guard(fn: () => Promise<void>) {
    setBusy(true); setError('')
    try { await fn() } catch (e) { if (live.current) setError((e as Error).message) }
    finally { if (live.current) setBusy(false) }
  }

  function resume(payload: Parameters<typeof api.resume>[1]) {
    return guard(async () => {
      const lastId = run?.events.at(-1)?.id ?? 0
      await api.resume(runId, payload)
      if (!live.current) return
      setRun((r) => r ? { ...r, status: 'running' } : r)
      follow(lastId)
    })
  }

  function sendFollowup(e: React.FormEvent) {
    e.preventDefault()
    const text = followup.trim()
    if (!text || busy || run?.status === 'running') return
    guard(async () => {
      const events = await api.sendMessage(runId, text)
      if (!live.current) return
      setFollowup('')
      setRun((r) => r ? appendEvents(r, events) : r)
      requestAnimationFrame(() => body.current?.scrollTo({ top: body.current.scrollHeight, behavior: 'smooth' }))
    })
  }

  function askAboutPlan() {
    setFollowup('Can you explain the recommended next steps for this report?')
    composer.current?.focus()
  }

  function retryAnalysis() {
    if (!run || busy) return
    return guard(async () => {
      const next = await api.startRun({ report_id: run.report_id })
      if (live.current) onRestart(next.id)
    })
  }

  function markCleaned() {
    if (!run) return
    guard(async () => {
      const report = await api.confirm(run.report_id, 'gone')
      if (!live.current) return
      setResolved(report.status === 'resolved')
      setNotice(report.status === 'resolved' ? 'Your local pin is now marked as resolved. Thank you for taking action.' : 'Your update was recorded. This pin is awaiting further confirmation.')
    })
  }

  if (!run) return (
    <section className="workspace zh-workspace">
      <div className="panel"><div className="panel-head"><button className="btn" onClick={onBackToMap}>Back to map</button></div>
        <div className="panel-body empty">{error || 'Opening your case...'}</div></div>
    </section>
  )

  const aiResponse = run.result?.ai_response
  const messages = run.events.filter((event) => event.type === 'message')
  const firstMessage = messages[0]
  const trace = run.events.filter((event) => event.type === 'step')
  const interrupt = [...run.events].reverse().find((event) => event.type === 'interrupt')
  const reviewOpen = run.status === 'paused' && interrupt
  const needs311 = aiResponse?.assessment?.requires_311 ?? aiResponse?.reporting.requires_311
  const earlierRun = ['rejected', 'failed', 'cancelled'].includes(run.status)

  return (
    <div className="workspace zh-workspace">
      <section className="panel zh-conversation" aria-label="Case conversation">
        <div className="panel-head zh-case-header">
          <button className="btn zh-back" onClick={() => onShowPin(run.report_id)}><span aria-hidden="true">←</span> Back to map</button>
          <span className={`zh-run-state zh-run-${run.status}`} role="status">{resolved ? 'Local pin resolved' : run.status === 'done' && !run.result?.ai_response ? 'Analysis unavailable' : statusLabel[run.status]}</span>
        </div>
        <div className="panel-body zh-conversation-body" ref={body}>
          <div className="zh-case-heading zh-main-plan-heading"><span className="eyebrow">ZERO HERO</span><h1>Your action plan</h1></div>
          {aiResponse && <PlanStats response={aiResponse} />}
          {firstMessage && <div className="turn user zh-user-message"><div className="who">YOUR REPORT</div><p>{firstMessage.content}</p></div>}
          {run.status === 'done' && aiResponse?.meta?.llm_used === false && <div className="error-box" role="status">
            The advanced AI interpretation was unavailable. These are basic safety-first recommendations, not a verified AI assessment. <button className="btn" type="button" disabled={busy} onClick={retryAnalysis}>Retry AI analysis</button>
          </div>}
          {aiResponse && <ActionDashboard response={aiResponse} userName={currentUser()} analysisEvents={trace} onAskAboutPlan={askAboutPlan} />}
          {run.status === 'running' && <div className="running zh-working" role="status"><span className="spinner" /> Finding the next helpful step for your report...</div>}
          {run.status === 'done' && !aiResponse && <section className="zh-completion" role="alert">
            <h2>Your detailed recommendations could not be generated.</h2>
            <p>Your report and map pin are saved. Try the analysis again to get tailored disposal instructions and 311 options.</p>
            <div className="row"><button className="btn go" type="button" disabled={busy} onClick={retryAnalysis}>Retry AI analysis</button>
              <a className="btn" href="https://www.edmonton.ca/programs_services/311-city-services" target="_blank" rel="noopener noreferrer">Edmonton 311 service information</a></div>
            <p>No 311 request has been submitted automatically.</p>
          </section>}
          {reviewOpen && run.result?.draft && <ApprovalCard key={interrupt.id} actionType={run.result.action_type!} draft={run.result.draft} busy={busy}
            onApprove={(edited) => resume({ decision: 'approve', draft: edited })}
            onEdit={(instructions) => resume({ decision: 'edit', instructions })}
            onContinue={() => resume({ decision: 'continue' })} />}
          {run.status === 'done' && !!aiResponse && run.result?.delivery?.kind === 'call' && needs311 !== false && <CallCard run={run} />}
          {run.status === 'done' && !!aiResponse && <section className="zh-completion" aria-labelledby="zh-complete-title">
            <div><span className="eyebrow">YOUR NEXT CHAPTER</span><h2 id="zh-complete-title">{resolved ? 'A little cleaner. A little greener.' : 'Your guidance is ready. What happens next is up to you.'}</h2>
              <p>{resolved ? 'Your local pin has been marked as resolved. This does not close any separate City service request.' : 'Receiving a plan does not mean the litter is gone or that the City has acted. Update this pin after you take action.'}</p></div>
            <div className="row">
              {!resolved && <button className="btn go" disabled={busy} onClick={markCleaned}>I cleaned it up</button>}
              <button className="btn" onClick={() => onShowPin(run.report_id)}>View pin on map</button>
            </div>
            {notice && <p role="status">{notice}</p>}
          </section>}
          {earlierRun && <section className="zh-completion">
            <h2>Keep this case moving</h2><p>{run.status === 'failed' ? 'The previous run could not finish. Your pin is still available.' : 'This earlier run ended, but your report has not been deleted.'}</p>
            <button className="btn go" disabled={busy} onClick={retryAnalysis}>Run agent again</button>
          </section>}
          {messages.slice(1).map((event) => <div className={`turn zh-message ${event.node === 'user' ? 'user' : 'assistant'}`} key={event.id}>
            <div className="who">{event.node === 'user' ? 'YOU' : 'ZERO HERO'}</div>
            {event.node === 'user' ? <div className="text">{event.content}</div> : <Md>{event.content}</Md>}
          </div>)}
          {busy && <div className="running" role="status"><span className="spinner" /> Working on it...</div>}
          {(error || run.error) && <div className="error-box" role="alert">{error || run.error}</div>}
        </div>
        <form className="composer zh-composer" onSubmit={sendFollowup}>
          <label className="zh-sr-only" htmlFor="zh-followup">Ask about this report</label>
          <input id="zh-followup" ref={composer} value={followup} onChange={(e) => setFollowup(e.target.value)} placeholder="Ask about this report..." disabled={run.status === 'running'} />
          <button className="btn primary" disabled={!followup.trim() || busy || run.status === 'running'}>Send <span aria-hidden="true">↗</span></button>
        </form>
      </section>
    </div>
  )
}

function CallCard({ run }: { run: Run }) {
  const draft = run.result!.draft as CallDraft
  const [outcome, setOutcome] = useState('')
  const [ticket, setTicket] = useState('')
  const [done, setDone] = useState(false)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')

  async function logCall() {
    if (!outcome.trim() || busy) return
    setBusy(true); setError('')
    try {
      await api.logCall({ report_id: run.report_id, run_id: run.id, to: draft.phone ?? draft.contact_name,
        outcome: outcome.trim(), ticket_number: ticket.trim() || undefined })
      setDone(true)
    } catch (e) { setError((e as Error).message) }
    finally { setBusy(false) }
  }

  return <details className="card zh-call-card">
    <summary>Optional: record a call you made</summary>
    <div className="stack">
      <p>The app has not placed a call. Only log a call after you have spoken with the service.</p>
      {draft.phone && <a className="btn go" href={`tel:${draft.phone.replace(/[^\d+]/g, '')}`}>Call {draft.contact_name} · {draft.phone}</a>}
      <ol>
        {draft.script.map((s, i) => (
          <li key={i}>{s.replace(/^\s*\d+[.)]\s*/, '')}</li>
        ))}
      </ol>
      {done ? <p role="status">Your call has been recorded on this local pin.</p> : <>
        <input className="input" aria-label="Call outcome" placeholder="What did they say?" value={outcome} onChange={(e) => setOutcome(e.target.value)} />
        <div className="row"><input className="input" aria-label="Ticket or reference number" placeholder="Ticket / reference number (optional)" value={ticket} onChange={(e) => setTicket(e.target.value)} />
          <button className="btn primary" disabled={busy || !outcome.trim()} onClick={logCall}>Save call record</button></div>
      </>}
      {error && <p className="error-box" role="alert">{error}</p>}
    </div>
  </details>
}
