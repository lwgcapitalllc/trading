import type { XMode } from '@/lib/chartAxis'

// Equity x-axis switch, shared by the run page's equity chart and the tuning workbench's overlay
// (they read one stored preference, so the two pages always agree). Calendar is the default and
// the canonical view; Trade # spaces every trade evenly for per-trade forensics.
export function XModeToggle({ value, onChange }: { value: XMode; onChange: (v: XMode) => void }) {
  return (
    <div className="inline-flex items-center rounded border border-border-subtle overflow-hidden">
      {(['date', 'trade'] as const).map((m) => (
        <button
          key={m}
          onClick={() => onChange(m)}
          title={m === 'date' ? 'Plot against the calendar' : 'Plot against trade number'}
          className={`px-2 py-[4px] text-[11px] transition-colors ${
            value === m
              ? 'text-accent bg-accent/10'
              : 'text-text-tertiary hover:text-text-secondary'
          }`}
        >
          {m === 'date' ? 'Date' : 'Trade #'}
        </button>
      ))}
    </div>
  )
}
