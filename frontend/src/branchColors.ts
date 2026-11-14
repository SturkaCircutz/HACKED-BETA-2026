import type { Branch } from './api'

/** Branch A -> 0, B -> 1, ... (colors cycle through --b0..--b5). */
export function branchIndex(b: Branch): number {
  return Math.max(0, b.title.charCodeAt(b.title.length - 1) - 65)
}

export function branchVars(i: number): React.CSSProperties {
  return { ['--bc' as string]: `var(--b${i % 6})`, ['--bcbg' as string]: `var(--b${i % 6}-bg)` }
}
