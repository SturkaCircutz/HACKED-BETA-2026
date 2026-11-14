import type { AgentResponse } from '../api'
import './PlanStats.css'

type Props = {
  response: AgentResponse
}

export function PlanStats({ response }: Props) {
  const assessment = response.assessment
  const riskLevel = assessment?.risk?.level
  const risk = typeof riskLevel === 'number' && Number.isInteger(riskLevel) && riskLevel >= 1 && riskLevel <= 5
    ? `${riskLevel}/5` : 'Not assessed'
  const needs311 = assessment?.requires_311 ?? response.reporting?.requires_311 ?? null
  const materials = assessment?.materials ?? []
  const verified = materials.map((item) => item.recyclable).filter((value): value is boolean => typeof value === 'boolean')
  const recyclable = !verified.length ? 'Not verified'
    : verified.length !== materials.length ? 'Conditional'
      : verified.every(Boolean) ? 'Yes'
        : verified.every((value) => !value) ? 'No' : 'Conditional'
  const category = ({ trash: 'Litter', dumping: 'Illegal dumping', water: 'Water issue', air: 'Air quality', noise: 'Noise', graffiti: 'Graffiti', pothole: 'Pothole', tree: 'Tree issue', other: 'Other' } as Record<string, string>)[response.category]
    ?? response.category.replace(/_/g, ' ').replace(/^./, (letter) => letter.toUpperCase())

  return (
    <section className="zh-metrics-card" aria-label="Report safety and category overview">
      <div className="zh-metrics-item">
        <span className="zh-metrics-label">Safety risk</span>
        <strong className="zh-metrics-value zh-metrics-risk">{risk}</strong>
      </div>
      <div className="zh-metrics-item">
        <span className="zh-metrics-label">311 assistance</span>
        <strong className="zh-metrics-value">{needs311 === true ? 'YES — Recommended' : needs311 === false ? 'NO — Optional' : 'Not confirmed'}</strong>
      </div>
      <div className="zh-metrics-item">
        <span className="zh-metrics-label">Recyclable</span>
        <strong className="zh-metrics-value">{recyclable}</strong>
      </div>
      <div className="zh-metrics-item">
        <span className="zh-metrics-label">Category</span>
        <strong className="zh-metrics-value">{category}</strong>
      </div>
    </section>
  )
}
