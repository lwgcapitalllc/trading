import { useMemo } from 'react'
import type { HistoryLimit } from '@/types'

// Backtest period control — two date inputs plus the quick-range presets. Shared by the Run
// Backtest modal (Strategies) and the Rerun modal (BacktestDetail) so a period is picked the
// same way everywhere. Dates are plain ISO days (YYYY-MM-DD), the format the API stores.

export function today(): string {
  return new Date().toISOString().split('T')[0]
}

export function yearsAgo(n: number): string {
  const d = new Date()
  d.setFullYear(d.getFullYear() - n)
  return d.toISOString().split('T')[0]
}

/** Small pill toggle — also used for the bar-size presets, hence exported. */
export function PresetBtn({
  label,
  active,
  onClick,
}: {
  label: string
  active?: boolean
  onClick: () => void
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      className={`px-[10px] py-[3px] rounded text-[11px] border transition-colors ${
        active
          ? 'text-accent bg-accent/10 border-accent/50'
          : 'text-text-tertiary hover:text-accent hover:bg-accent/10 border-border-subtle hover:border-accent/30'
      }`}
    >
      {label}
    </button>
  )
}

const INPUT_CLS =
  'bg-bg-sunken border border-border-subtle rounded-md px-3 py-[6px] text-[13px] text-text-primary w-full focus:outline-none focus:border-accent transition-colors'
const DATE_CLS = `${INPUT_CLS} [&::-webkit-calendar-picker-indicator]:invert [&::-webkit-calendar-picker-indicator]:opacity-50 [&::-webkit-calendar-picker-indicator]:cursor-pointer`

export function PeriodPicker({
  start,
  end,
  onChange,
  limit,
}: {
  start: string
  end: string
  /** Fired for either input and for a preset (which sets both at once). */
  onChange: (start: string, end: string) => void
  /**
   * Broker history floor for this instrument + timeframe, from `useHistoryLimit`.
   * `null`/`undefined` = unknown, and the range is left open — the backend and the data
   * layer still refuse a bad window, so guessing a limit here would only be wrong.
   */
  limit?: HistoryLimit | null
}) {
  const todayStr = useMemo(() => today(), [])
  const floor = limit?.earliest_date ?? null

  // Presets are CLAMPED to the floor, so "5Y" on a broker with 4 years of history asks for
  // what exists instead of a window the backend will refuse. "All" means all there IS.
  const presets = useMemo(() => {
    const clamp = (d: string) => (floor && d < floor ? floor : d)
    return [
      { label: '1Y', start: clamp(yearsAgo(1)), end: todayStr },
      { label: '3Y', start: clamp(yearsAgo(3)), end: todayStr },
      { label: '5Y', start: clamp(yearsAgo(5)), end: todayStr },
      { label: 'All', start: floor ?? '2019-01-01', end: todayStr },
    ]
  }, [todayStr, floor])

  const activePreset = presets.find((p) => p.start === start && p.end === end)?.label ?? null
  const beforeFloor = !!(floor && start && start < floor)

  return (
    <>
      <div className="grid grid-cols-[1fr_16px_1fr] items-center gap-1 mb-2">
        <input
          type="date"
          value={start}
          min={floor ?? undefined}
          max={todayStr}
          onChange={(e) => onChange(e.target.value, end)}
          className={`${DATE_CLS} ${beforeFloor ? 'border-neg-text/60' : ''}`}
        />
        <span className="text-text-tertiary text-center text-[12px]">→</span>
        <input
          type="date"
          value={end}
          min={floor ?? undefined}
          max={todayStr}
          onChange={(e) => onChange(start, e.target.value)}
          className={DATE_CLS}
        />
      </div>
      {start && end && start >= end && (
        <p className="text-[11px] text-neg-text mb-2">Start must be before end.</p>
      )}
      {/* A native `min` stops the picker but not a typed/pasted date, so say it plainly too —
          and offer the fix as a click rather than making the user retype the date. */}
      {beforeFloor && (
        <p className="text-[11px] text-neg-text mb-2">
          No real data before {floor}.{' '}
          <button
            type="button"
            className="underline hover:text-accent"
            onClick={() => onChange(floor!, end)}
          >
            Start at {floor}
          </button>
        </p>
      )}
      {floor && !beforeFloor && (
        <p className="text-[11px] text-text-tertiary mb-2" title={limit?.note}>
          {limit?.broker || 'Broker'} data starts {floor}
          {limit?.timeframe_minutes ? ` on ${limit.timeframe_minutes}m` : ''}
          {limit?.source === 'seed' ? ' (last known — terminal unreachable)' : ''}
        </p>
      )}
      <div className="flex gap-2">
        {presets.map((p) => (
          <PresetBtn
            key={p.label}
            label={p.label}
            active={activePreset === p.label}
            onClick={() => onChange(p.start, p.end)}
          />
        ))}
      </div>
    </>
  )
}
