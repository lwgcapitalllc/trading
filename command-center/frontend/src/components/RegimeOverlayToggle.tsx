import { useCallback, useState } from 'react'
import { Layers } from 'lucide-react'

// Regime-band on/off pill for the equity charts. SHARED by BacktestDetail's equity chart, the
// stack page and the tuning workbench's overlay — the tune page used to carry a plain checkbox, so
// the same control looked like two different things on two charts that are meant to read as one
// system.
export function RegimeOverlayToggle({
  on,
  onChange,
}: {
  on: boolean
  onChange: (v: boolean) => void
}) {
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

// ── The preference ────────────────────────────────────────────────────────────
//
// ONE hook behind ONE key, and it lives with the control rather than in whichever page happened
// to want it first. There were THREE definitions of this before 2026-08-10 — BacktestDetail's
// `getOverlayPref`, StackDetail's bare `useState(true)` and TuningWorkbench's bare
// `useState(true)` — so only one of the three surfaces even remembered the reader's answer, and
// the other two came back on at every visit however many times they were switched off.
//
// ⚠ DEFAULT OFF (Aaron, 2026-08-10: "I don't wanna see the regimes on by default", on every page
// with an equity curve). The bands are context you go looking for, not the reading itself, and on
// by default they tint the whole plot behind the one line the page exists to show. Note the
// polarity of the stored check: `=== 'true'`, so an unset key reads OFF — the old
// `!== 'false'` spelling is what made it default ON, and flipping the DEFAULT means flipping that
// comparison, not adding a second key.
const _KEY = 'regime_overlay_enabled'

export function useRegimeOverlay(): [boolean, (v: boolean) => void] {
  const [on, setOn] = useState(() => {
    try {
      return localStorage.getItem(_KEY) === 'true'
    } catch {
      return false
    }
  })
  const set = useCallback((v: boolean) => {
    setOn(v)
    try {
      localStorage.setItem(_KEY, String(v))
    } catch {
      /* quota */
    }
  }, [])
  return [on, set]
}
