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
  // Grey, not red (2026-09-13): a run to throw away is the one row that needs nothing from you, and
  // red on it made the list shout loudest about the runs that matter least.
  TIER_3_DISCARD: {
    label: 'DISCARD',
    cls: 'bg-bg-hover text-text-tertiary border border-border-subtle',
  },
} as const

// The backend's reason codes (services/worthiness.py), in words. An unknown code falls back to the
// code with its underscores spaced out, so a new one still reads rather than vanishing.
const REASON_TEXT: Record<string, string> = {
  no_trades: 'No trades.',
  insufficient_signal: 'Fewer than 30 trades.',
  drawdown_breach: 'Drawdown went past the limit.',
  low_profit_factor: 'Profit factor below 0.8.',
}

interface Props {
  worthiness: WorthinessScore | null | undefined
  size?: 'sm' | 'md'
}

export function WorthinessBadge({ worthiness, size = 'sm' }: Props) {
  if (!worthiness) return null

  const cfg = TIER_CONFIG[worthiness.tier as keyof typeof TIER_CONFIG]
  if (!cfg) return null

  const padding = size === 'md' ? 'px-3 py-1 text-[12px]' : 'px-[7px] py-[3px] text-[10px]'

  // The reason only; the ruleset it was scored against is already named in the row's Challenge
  // column, and its raw id here said the same thing in code.
  const tooltip = worthiness.reason
    ? (REASON_TEXT[worthiness.reason] ?? worthiness.reason.replace(/_/g, ' '))
    : undefined

  return (
    <span
      title={tooltip}
      className={`inline-flex items-center rounded-pill font-semibold uppercase tracking-[0.5px] ${padding} ${cfg.cls}`}
    >
      {cfg.label}
    </span>
  )
}
