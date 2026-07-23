import { Layers } from 'lucide-react'

// Regime-band on/off pill for the equity charts. SHARED by BacktestDetail's equity chart and the
// tuning workbench's overlay — the tune page used to carry a plain checkbox, so the same control
// looked like two different things on two charts that are meant to read as one system.
export function RegimeOverlayToggle({ on, onChange }: { on: boolean; onChange: (v: boolean) => void }) {
  return (
    <button
      onClick={() => onChange(!on)}
      title={on ? 'Hide regime bands' : 'Show regime bands'}
      className={`flex items-center gap-1.5 px-2 py-[4px] rounded text-[11px] transition-colors ${
        on
          ? 'text-accent bg-accent/10 border border-accent/25'
          : 'text-text-tertiary hover:text-text-secondary border border-border-subtle'
      }`}
    >
      <Layers size={11} />
      Regimes
    </button>
  )
}
