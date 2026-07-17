import { runnerScope, RUNNER_FULL_LABEL } from '@/lib/runner'

// Accepts runner values ("ninjatrader", "mt5", "python") or platform values ("NT8", "MT5").
type Props = { runner: string; size?: number; className?: string }

const ICON: Record<'nt8' | 'mt5', string> = {
  nt8: '/nt8-icon.png',
  mt5: '/mt5-icon.png',
}

export function RunnerBadge({ runner, size = 22, className = '' }: Props) {
  const scope = runnerScope(runner)
  const label = RUNNER_FULL_LABEL[scope]

  // Python is local, not a vendor platform — it has no product icon, so it gets a text mark.
  if (scope === 'python') {
    return (
      <span
        title={label}
        aria-label={label}
        style={{ width: size, height: size }}
        className={`inline-flex items-center justify-center rounded bg-gold-muted text-gold-text font-semibold leading-none tabular-nums ${className}`}
      >
        <span style={{ fontSize: Math.round(size * 0.45) }}>PY</span>
      </span>
    )
  }

  return (
    <img
      src={ICON[scope]}
      alt={label}
      title={label}
      width={size}
      height={size}
      className={`inline-block object-contain ${className}`}
    />
  )
}
