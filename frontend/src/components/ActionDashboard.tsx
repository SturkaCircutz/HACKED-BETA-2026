import { useState } from 'react'
import type { AgentResponse, NearbyPlace, RunEvent } from '../api'
import { PlanAnalysis } from './PlanAnalysis'

interface Props {
  response: AgentResponse
  userName: string
  onAskAboutPlan?: () => void
  analysisEvents?: RunEvent[]
}

function publicUrl(value?: string | null): string | undefined {
  if (!value) return undefined
  try {
    const url = new URL(value)
    return ['https:', 'http:'].includes(url.protocol) ? url.href : undefined
  } catch { return undefined }
}

function humanName(raw: string): string {
  const value = (raw || '').split('@')[0].replace(/[_-]+/g, ' ').trim().slice(0, 40)
  return value ? value.charAt(0).toUpperCase() + value.slice(1) : 'there'
}

function placeType(p: NearbyPlace): string {
  if (p.kind === 'public_bin') return 'Mapped waste basket'
  if (p.kind === 'recycling_depot') return 'Recycling depot'
  if (p.kind === 'public_sorting_station') return 'City-listed sorting station'
  return 'Public facility · bin not verified'
}

function placeWalking(p: NearbyPlace): string {
  if (p.route_verified && typeof p.walking_minutes === 'number')
    return `${p.walking_minutes.toFixed(1)} min walking route · estimated`
  if (typeof p.walking_minutes_estimate === 'number')
    return `~${p.walking_minutes_estimate.toFixed(1)} min by proximity · walking route unverified`
  return 'Walking distance unknown'
}

function certainty(value: boolean | null | undefined, unknown = 'Not verified'): string {
  return value === true ? 'YES' : value === false ? 'NO' : unknown
}

export function ActionDashboard({ response, userName, onAskAboutPlan, analysisEvents = [] }: Props) {
  const [copyStatus, setCopyStatus] = useState('')
  const assessment = response.assessment
  const risk = assessment?.risk ?? { level: response.priority === 'emergency' ? 5 : response.priority === 'urgent' ? 4 : 2,
    label: 'Estimate', basis: 'Based on the report description only.' }
  const needed = assessment?.requires_311 ?? response.reporting?.requires_311 ?? null
  const materials = assessment?.materials ?? []
  const officialUrl = publicUrl(assessment?.official_instructions_url)
  const reportingUrl = publicUrl(response.reporting.url)
  const isEmergency = response.priority === 'emergency'
  const noCitySubmission = response.reporting.submitted !== true
  const reportText = response.reporting.report_text || ''
  const nearby = (response.nearby_places || []).filter((place) => place.kind !== 'library')

  async function copyReport() {
    if (!reportText) return
    try {
      if (!navigator.clipboard) throw new Error('Clipboard not available')
      await navigator.clipboard.writeText(reportText)
      setCopyStatus('Copied to clipboard')
    } catch {
      setCopyStatus('Select the report text below to copy it manually')
    }
  }

  return (
    <article className="eco-action" aria-label="Zero Hero environmental action plan">
      <header className="eco-action-hero">
        <span className="zh-logo zh-logo-small" aria-hidden="true"><img src="/zero-hero-logo.webp" alt="" /></span>
        <div className="eco-action-intro">
          <div className="eco-eyebrow">PERSONAL ACTION PLAN</div>
          <h2>Hi, {humanName(userName)}! <span aria-hidden="true">👋</span></h2>
          <p>Thanks for looking out for your neighbourhood. Here's what you can do.</p>
        </div>
        <span className="eco-action-location">📍 {response.jurisdiction.status === 'inside' ? 'Edmonton' : 'Location unconfirmed'}</span>
      </header>

      <section className="eco-summary" aria-label="Report summary and environmental assessment">
        <div className="eco-summary-heading">
          <div><div className="eco-eyebrow">REPORT OVERVIEW</div><p>{response.summary}</p></div>
          <span className="eco-status">Local pin · {response.report_id ? 'created' : 'draft'}</span>
        </div>
        <p className="eco-footnote">{risk.basis} Conditions have not been checked in person.</p>
      </section>

      <section className="eco-action-section eco-steps-section" aria-labelledby="eco-now-title">
        <div className="eco-section-title"><span aria-hidden="true">✓</span><h3 id="eco-now-title">What you can do</h3></div>
        <ul className="eco-action-steps">
          {response.steps.map((step, i) => <li key={i}><span className="eco-step-index zh-step-dot" aria-hidden="true" /><p>{step}</p></li>)}
        </ul>
        <div className="eco-official-guidance">
          <div className="eco-official-heading">FROM THE CITY OF EDMONTON</div>
          {assessment?.official_instructions?.length ? <ul className="eco-city-steps">
            {assessment.official_instructions.slice(0, 3).map((step, i) => <li key={i}>{step}</li>)}
          </ul> : <p>For your next step, consult the City's cleanup and sorting guidance before handling unfamiliar items.</p>}
          {officialUrl && <a className="eco-action-link" href={officialUrl} target="_blank" rel="noopener noreferrer">Read official guidance ↗</a>}
          {materials.length > 0 && <details className="eco-details">
            <summary>Recycling guidance by item</summary>
            <ul className="eco-material-list">
              {materials.map((m, i) => <li key={i}>
                <strong>{m.name}</strong><span className="eco-material-flags"> · Recyclable: {certainty(m.recyclable)} · Sustainable: {certainty(m.sustainability_friendly)}</span>
                <p>{m.recycling_condition}</p>
                {publicUrl(m.source_url) && <a href={publicUrl(m.source_url)} target="_blank" rel="noopener noreferrer">Official sorting reference ↗</a>}
              </li>)}
            </ul>
          </details>}
        </div>
      </section>

      <section className="eco-action-section" aria-labelledby="eco-near-title">
        <div className="eco-section-title"><span aria-hidden="true">⌖</span><h3 id="eco-near-title">Nearby disposal options</h3></div>
        <p className="eco-subtitle">Live map results, not guaranteed available containers. Walking times are estimates unless a route was verified.</p>
        {nearby.length ? <ul className="eco-nearby-list">
          {nearby.map((place, i) => <li className="eco-nearby-item" key={`${place.name}-${place.lat}-${place.lng}-${i}`}>
            <span className="eco-nearby-number" aria-hidden="true">•</span>
            <div className="eco-nearby-details">
              <strong>{place.name}</strong>
              <span>{placeType(place)}{place.address ? ` · ${place.address}` : ''}</span>
              <span className="eco-walk">{placeWalking(place)}</span>
              <p>{place.note}</p>
              {publicUrl(place.maps_url) && <a href={publicUrl(place.maps_url)} target="_blank" rel="noopener noreferrer">Walking directions ↗</a>}
            </div>
          </li>)}
        </ul> : <div className="eco-empty-place">No confirmed public disposal location was found within the available data. Check the <a href="https://www.edmonton.ca/programs_services/garbage_waste/managing-your-waste-public" target="_blank" rel="noopener noreferrer">City's official waste-container map</a>. Never leave rubbish beside a bin.</div>}
      </section>

      <section className="eco-action-section" aria-labelledby="eco-city311-title">
        <div className="eco-section-title"><span aria-hidden="true">☎</span><h3 id="eco-city311-title">Need help from 311?</h3></div>
        <div className={`eco-311-panel ${needed === true ? 'eco-311-yes' : ''}`}>
          <strong>{isEmergency ? 'Emergency service required — do not wait for 311' : needed === true ? 'YES — City assistance recommended' : needed === false ? 'NO — 311 not required for this issue' : 'Confirm the right municipality or service'}</strong>
          <p>{assessment?.requires_311_reason ?? response.reporting.requires_311_reason ?? 'Contact the City only when the responsible service has been confirmed.'}</p>
          {response.clarification && <p><strong>Additional detail needed:</strong> {response.clarification}</p>}
          <div className="eco-action-buttons">
            {reportingUrl && <a className="eco-button primary" href={reportingUrl} target="_blank" rel="noopener noreferrer">Open official 311 ↗</a>}
            {response.reporting.phone && <a className="eco-button" href={`tel:${response.reporting.phone.replace(/[^\d+]/g, '')}`}>Call {response.reporting.phone}</a>}
            {reportText && <button className="eco-button" type="button" onClick={copyReport}>Copy report text</button>}
          </div>
          {copyStatus && <p className="eco-feedback" role="status">{copyStatus}</p>}
          {reportText && <details className="eco-details"><summary>Suggested report description</summary><textarea className="eco-copy-text" readOnly value={reportText} aria-label="Suggested report description" /></details>}
          <div className="eco-submission-note">{noCitySubmission ? 'No request has been submitted to Edmonton 311. Your Zero Hero pin is separate.' : 'City request status must be confirmed with a service reference number.'}</div>
        </div>
      </section>

      <PlanAnalysis events={analysisEvents} response={response} />

      <footer className="eco-action-footer">
        <span className="eco-footer-leaf" aria-hidden="true">♥</span>
        <div><strong>Thanks for helping keep your neighbourhood clean.</strong>
          <p>We’ll help you keep track of your report. Mark it cleaned when the issue is resolved; City action is not guaranteed.</p></div>
      </footer>
      <div className="eco-action-meta">
        {onAskAboutPlan && <button type="button" onClick={onAskAboutPlan}>Ask about this plan ↓</button>}
        <details><summary>Sources and data limitations</summary>
          {response.sources?.length ? <ul>{response.sources.map((s, i) => <li key={i}>{publicUrl(s.url) ? <a href={publicUrl(s.url)} target="_blank" rel="noopener noreferrer">{s.title}</a> : s.title}</li>)}</ul> : null}
          {response.warnings?.length ? <ul>{response.warnings.map((warning, i) => <li key={i}>{warning}</li>)}</ul> : null}
        </details>
      </div>
    </article>
  )
}
