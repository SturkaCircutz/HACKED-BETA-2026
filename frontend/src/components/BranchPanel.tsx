import { useLayoutEffect, useRef, useState } from 'react'
import type { Branch } from '../api'
import { branchIndex, branchVars } from '../branchColors'
import { Md } from './Md'

export interface DraftBranch { anchorEventId: number; selection: string; anchorTitle: string }

interface Props {
  branches: Branch[]
  activeId: string | null
  draft: DraftBranch | null
  busy: boolean
  anchorTitle: (eventId: number) => string
  onSwitch: (id: string) => void
  onCloseBranch: (id: string) => void
  onReopen: (id: string) => void
  onJumpToAnchor: (eventId: number) => void
  onCreate: (question: string) => void
  onSend: (branchId: string, text: string) => void
  onCancelDraft: () => void
}

export function BranchPanel(p: Props) {
  const [text, setText] = useState('')
  const [showClosed, setShowClosed] = useState(false)
  const body = useRef<HTMLDivElement>(null)
  const scrollPos = useRef<Record<string, number>>({})
  const open = p.branches.filter((b) => !b.closed)
  const closed = p.branches.filter((b) => b.closed)
  const active = p.draft ? null : p.branches.find((b) => b.id === p.activeId) ?? null
  const key = p.draft ? 'draft' : active?.id ?? ''

  // Restore scroll position per branch on switch; new messages scroll to bottom.
  useLayoutEffect(() => {
    if (!body.current) return
    body.current.scrollTop = scrollPos.current[key] ?? body.current.scrollHeight
  }, [key])
  useLayoutEffect(() => {
    if (body.current) body.current.scrollTop = body.current.scrollHeight
  }, [active?.messages.length])

  function submit(e: React.FormEvent) {
    e.preventDefault()
    const t = text.trim()
    if (!t || p.busy) return
    if (p.draft) p.onCreate(t)
    else if (active) p.onSend(active.id, t)
    setText('')
  }

  const vars = p.draft ? branchVars(p.branches.length) : active ? branchVars(branchIndex(active)) : {}
  const source = p.draft ? (p.draft.selection || p.draft.anchorTitle) : active ? (active.selection || p.anchorTitle(active.anchor_event_id)) : ''

  return (
    <section className="panel" aria-label="Active branch" style={{ ...vars, flex: 1, minWidth: 0 }}>
      <div className="panel-head"><span className="panel-label branch">Right&nbsp;&nbsp;|&nbsp;&nbsp;Active branch</span></div>
      <div className="panel-body" ref={body} onScroll={(e) => { scrollPos.current[key] = e.currentTarget.scrollTop }}>
        <div className="tabs" role="tablist" style={{ marginBottom: 24 }}>
          {open.map((b) => (
            <span key={b.id} role="tab" tabIndex={0} className="tab" aria-selected={!p.draft && b.id === p.activeId}
              style={branchVars(branchIndex(b))} onClick={() => p.onSwitch(b.id)}
              onKeyDown={(e) => { if (e.key === 'Enter') p.onSwitch(b.id) }}>
              {b.title}
              <button className="x" aria-label={`Close ${b.title}`} title="Close (kept, not deleted)"
                onClick={(e) => { e.stopPropagation(); p.onCloseBranch(b.id) }}>×</button>
            </span>
          ))}
          {p.draft && <span className="tab" aria-selected style={vars}>New branch
            <button className="x" aria-label="Cancel new branch" onClick={p.onCancelDraft}>×</button></span>}
          {closed.length > 0 && (
            <button className="btn ghost sm" onClick={() => setShowClosed(!showClosed)}>{closed.length} closed ▾</button>
          )}
        </div>
        {showClosed && closed.length > 0 && (
          <div className="row" style={{ marginTop: -12, marginBottom: 20 }}>
            {closed.map((b) => <button key={b.id} className="btn sm" onClick={() => { p.onReopen(b.id); setShowClosed(false) }}>Reopen {b.title}</button>)}
          </div>
        )}

        {!p.draft && !active ? (
          <div className="empty">
            <div className="big">Explore a step without leaving the main answer</div>
            Hover a step on the left and click <strong>Branch</strong>, or highlight any text in it.
          </div>
        ) : (
          <>
            <div className="eyebrow">Source selection</div>
            <button className="source-box" onClick={() => p.onJumpToAnchor(p.draft ? p.draft.anchorEventId : active!.anchor_event_id)}
              title="Show in main conversation">{source}</button>
            <div style={{ height: 28 }} />
            {active?.messages.map((m, i) => (
              <div key={i} className="turn">
                <div className="who">{m.role === 'user' ? 'You' : 'AI'}</div>
                {m.role === 'user' ? <div className="text" style={{ fontSize: 16 }}>{m.content}</div> : <Md>{m.content}</Md>}
                {m.role === 'user' && <hr className="sep" style={{ marginBottom: 0 }} />}
              </div>
            ))}
            {p.busy && <div className="running"><span className="spinner" /> Thinking…</div>}
          </>
        )}
      </div>
      {(p.draft || active) && (
        <form className="composer" onSubmit={submit}>
          <input value={text} onChange={(e) => setText(e.target.value)} autoFocus={!!p.draft}
            placeholder={p.draft ? 'Ask about this step…' : 'Continue this branch…'} aria-label="Branch message" />
          <button className="btn primary" disabled={!text.trim() || p.busy}>Send</button>
        </form>
      )}
    </section>
  )
}
