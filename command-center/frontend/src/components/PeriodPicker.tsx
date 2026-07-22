import { useMemo } from 'react'

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
export function PresetBtn({ label, active, onClick }: { label: string; active?: boolean; onClick: () => void }) {
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

const INPUT_CLS = 'bg-bg-sunken border border-border-subtle rounded-md px-3 py-[6px] text-[13px] text-text-primary w-full focus:outline-none focus:border-accent transition-colors'
const DATE_CLS  = `${INPUT_CLS} [&::-webkit-calendar-picker-indicator]:invert [&::-webkit-calendar-picker-indicator]:opacity-50 [&::-webkit-calendar-picker-indicator]:cursor-pointer`

export function PeriodPicker({ start, end, onChange }: {
  start: string
  end: string
  /** Fired for either input and for a preset (which sets both at once). */
  onChange: (start: string, end: string) => void
}) {
  const todayStr = useMemo(() => today(), [])
  const presets = useMemo(() => [
    { label: '1Y',  start: yearsAgo(1),  end: todayStr },
    { label: '3Y',  start: yearsAgo(3),  end: todayStr },
    { label: '5Y',  start: yearsAgo(5),  end: todayStr },
    { label: 'All', start: '2019-01-01', end: todayStr },
  ], [todayStr])

  const activePreset = presets.find(p => p.start === start && p.end === end)?.label ?? null

  return (
    <>
      <div className="grid grid-cols-[1fr_16px_1fr] items-center gap-1 mb-2">
        <input type="date" value={start} onChange={e => onChange(e.target.value, end)} className={DATE_CLS} />
        <span className="text-text-tertiary text-center text-[12px]">→</span>
        <input type="date" value={end} onChange={e => onChange(start, e.target.value)} className={DATE_CLS} />
      </div>
      {start && end && start >= end && (
        <p className="text-[11px] text-neg-text mb-2">Start must be before end.</p>
      )}
      <div className="flex gap-2">
        {presets.map(p => (
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
