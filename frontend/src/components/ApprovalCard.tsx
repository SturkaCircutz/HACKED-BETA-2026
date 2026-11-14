import { useState } from 'react'
import type { CallDraft, EmailDraft } from '../api'

interface Props {
  actionType: 'email' | 'call'
  draft: EmailDraft | CallDraft
  busy: boolean
  onApprove: (edited: Partial<EmailDraft & CallDraft>) => void
  onEdit: (instructions: string) => void
  onReject: () => void
}

/** HUMAN REVIEW: shows the exact action that is about to be executed. */
export function ApprovalCard({ actionType, draft, busy, onApprove, onEdit, onReject }: Props) {
  const email = actionType === 'email' ? (draft as EmailDraft) : null
  const call = actionType === 'call' ? (draft as CallDraft) : null
  const [to, setTo] = useState(email?.to ?? '')
  const [subject, setSubject] = useState(email?.subject ?? '')
  const [body, setBody] = useState(email?.body ?? '')
  const [script, setScript] = useState(call?.script.join('\n') ?? '')
  const [askEdit, setAskEdit] = useState(false)
  const [instructions, setInstructions] = useState('')

  function approve() {
    if (email) onApprove({ to, subject, body })
    else onApprove({ script: script.split('\n').map((s) => s.trim()).filter(Boolean) })
  }

  return (
    <div className="card approval" role="region" aria-label="Approval required">
      <h4>{email ? 'Email send approval' : 'Call plan approval'}</h4>
      {!draft.contact_verified && (
        <div className="warn" style={{ marginBottom: 12 }}>
          This contact is <strong>unverified</strong>. Check it against the source before sending.
        </div>
      )}
      {email ? (
        <div className="kv">
          <span>To</span>
          <div>
            <div className="small muted">{email.to_name}</div>
            <input className="input" value={to} onChange={(e) => setTo(e.target.value)} aria-label="Recipient" />
          </div>
          <span>Subject</span>
          <input className="input" value={subject} onChange={(e) => setSubject(e.target.value)} aria-label="Subject" />
          <span>Body</span>
          <textarea className="textarea" rows={10} value={body} onChange={(e) => setBody(e.target.value)} aria-label="Body" />
        </div>
      ) : (
        <div className="kv">
          <span>Call</span>
          <div style={{ paddingTop: 9 }}>
            <strong>{call!.contact_name}</strong> {call!.phone ?? <span className="muted">(number not found)</span>}
            {call!.hours && <div className="small muted">Hours: {call!.hours}</div>}
          </div>
          <span>Script</span>
          <textarea className="textarea" rows={7} value={script} onChange={(e) => setScript(e.target.value)} aria-label="Call script, one step per line" />
        </div>
      )}
      {askEdit && (
        <div className="row" style={{ marginBottom: 12 }}>
          <input className="input" style={{ flex: 1 }} autoFocus value={instructions} placeholder="What should the agent change?"
            onChange={(e) => setInstructions(e.target.value)}
            onKeyDown={(e) => { if (e.key === 'Enter' && instructions.trim()) onEdit(instructions) }} />
          <button className="btn" disabled={busy || !instructions.trim()} onClick={() => onEdit(instructions)}>Redraft</button>
        </div>
      )}
      <div className="row" style={{ justifyContent: 'center' }}>
        <button className="btn go" disabled={busy || (!!email && !to.trim())} onClick={approve}>
          {email ? 'Approve & Send' : 'Approve call plan'}
        </button>
        <button className="btn" disabled={busy} onClick={() => setAskEdit(!askEdit)}>Ask agent to edit</button>
        <button className="btn danger" disabled={busy} onClick={onReject}>Reject</button>
      </div>
    </div>
  )
}
