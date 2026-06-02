import type { StressTest } from '@/types'

const GRADE_CONFIG: Record<string, { label: string; cls: string }> = {
  A: { label: 'A', cls: 'bg-pos-muted text-pos-text border border-pos-text/30' },
  B: { label: 'B', cls: 'bg-accent-muted text-accent border border-accent/30' },
  C: { label: 'C', cls: 'bg-warn-muted text-warn-text border border-warn-text/30' },
  D: { label: 'D', cls: 'bg-neg-muted text-neg-text border border-neg-text/20' },
  F: { label: 'F', cls: 'bg-neg-muted text-neg-text border border-neg-text/30' },
}

interface Props {
  grade: StressTest['grade']
  size?: 'sm' | 'md' | 'lg'
}

export default function RobustnessGradeBadge({ grade, size = 'md' }: Props) {
  if (!grade) return null
  const cfg = GRADE_CONFIG[grade] ?? { label: grade, cls: 'bg-bg-hover text-text-secondary border border-border-subtle' }
  const sizeClass = size === 'sm' ? 'text-xs px-1.5 py-0.5' : size === 'lg' ? 'text-2xl px-3 py-1 font-black' : 'text-sm px-2 py-0.5 font-bold'
  return (
    <span className={`inline-flex items-center rounded font-mono ${sizeClass} ${cfg.cls}`}>
      {cfg.label}
    </span>
  )
}
