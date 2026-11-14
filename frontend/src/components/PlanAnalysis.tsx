import type { AgentResponse, RunEvent } from '../api'
import { Md } from './Md'
import './PlanAnalysis.css'

type Props = {
  events: RunEvent[]
  response?: AgentResponse
}

const titles: Record<string, string> = {
  intake: 'Understand the report',
  geo_resolve: 'Resolve location',
  nearby_reports: 'Check nearby reports',
  retrieve_contacts: 'Find the right contact',
  draft_action: 'Choose a safe next step',
}

export function visiblePlanEvents(events: RunEvent[]): RunEvent[] {
  const latest = new Map<string, RunEvent>()
  for (const event of events) {
    if (event.type !== 'step' || !event.node || !(event.node in titles)) continue
    if (event.node === 'retrieve_contacts') {
      const contacts = event.data?.contacts
      if (Array.isArray(contacts) && contacts.length === 0) { latest.delete(event.node); continue }
      if (/no (?:relevant |verified )?contact found|no contacts? (?:were )?found/i.test(event.content)) { latest.delete(event.node); continue }
    }
    latest.set(event.node, event)
  }
  return [...latest.values()]
}

function contentFor(event: RunEvent, response?: AgentResponse): string {
  if (event.node === 'geo_resolve') {
    return event.content.replace(/^\s*Jurisdiction\s*:.*$/gim, '').trim()
  }
  if (event.node === 'draft_action') {
    return response?.steps?.[0]
      ? `Recommended first step: ${response.steps[0]} No call or City request is made automatically.`
      : 'Your plan is being prepared. No call or City request has been made.'
  }
  return event.content
}

export function PlanAnalysis({ events, response }: Props) {
  const visible = visiblePlanEvents(events)
  if (!visible.length) return null
  return (
    <section className="zh-plan-analysis" aria-label="Report analysis">
      <h3>What we found</h3>
      <ul className="zh-plan-bullets">
        {visible.map((event) => (
          <li className="zh-plan-bullet" key={event.id}>
            <div className="zh-plan-point">
              <h4>{titles[event.node!]}</h4>
              <Md>{contentFor(event, response)}</Md>
            </div>
          </li>
        ))}
      </ul>
    </section>
  )
}
