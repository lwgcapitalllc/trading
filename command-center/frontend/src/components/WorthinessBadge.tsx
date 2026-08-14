import type { WorthinessScore } from '@/types'

const TIER_CONFIG = {
  TIER_1_STRESS_TEST: {
    label: 'STRESS TEST',
    cls: 'bg-pos-muted text-pos-text border border-pos-text/20',
  },
  TIER_2_OPTIMIZE: {
    label: 'OPTIMIZE',
    cls: 'bg-warn-muted text-warn-text border border-warn-text/20',
  },
  TIER_3_DISCARD: { label: 'DISCARD', cls: 'bg-neg-muted text-neg-text border border-neg-text/20' },
} as const

interface Props {
  worthiness: WorthinessScore | null | undefined
  size?: 'sm' | 'md'
}

export function WorthinessBadge({ worthiness, size = 'sm' }: Props) {
  if (!worthiness) return null

  const cfg = TIER_CONFIG[worthiness.tier as keyof typeof TIER_CONFIG]
  if (!cfg) return null

  const padding = size === 'md' ? 'px-3 py-1 text-[12px]' : 'px-[7px] py-[3px] text-[10px]'

  const tooltip = [
    worthiness.reason ? `Reason: ${worthiness.reason.replace(/_/g, ' ')}` : null,
    worthiness.computed_against_firm ? `Scored against: ${worthiness.computed_against_firm}` : null,
  ]
    .filter(Boolean)
    .join(' · ')

  return (
    <span
      title={tooltip || undefined}
      className={`inline-flex items-center rounded-pill font-semibold uppercase tracking-[0.5px] ${padding} ${cfg.cls}`}
    >
      {cfg.label}
    </span>
  )
}
