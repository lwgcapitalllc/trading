import { useState } from 'react'
import { ChevronDown, ChevronUp } from 'lucide-react'
import RobustnessGradeBadge from './RobustnessGradeBadge'

// Explains the A–F robustness grade so the trader knows what each means and what to target before
// taking a strategy to a bot. Mirrors the backend rubric in services/grading.py (MC tail vs the
// drawdown limit + walk-forward degradation + sensitivity worst-case) — the 20/30 and 25/40 bars are
// its _WF_SOLID/_WF_OK and _SENS_SOLID/_SENS_OK. Collapsible — reference info, default closed.
//
// Worded for the accounts this lab grades today (2026-09-13): personal demo and live, not prop-firm
// "funded" and "evaluation". Every limit here is whatever the chosen ruleset states.

type Grade = 'A' | 'B' | 'C' | 'D' | 'F'
const ROWS: { g: Grade; title: string; desc: string }[] = [
  {
    g: 'A',
    title: 'Ready for real money',
    desc: 'Worst 1% of simulations stay inside the drawdown limit · walk-forward under 20% worse on unseen data · no settings nudge costs 25% or more.',
  },
  {
    g: 'B',
    title: 'Ready for demo',
    desc: 'Worst 5% stay inside the limit · walk-forward under 30% worse · no nudge costs 40% or more.',
  },
  {
    g: 'C',
    title: 'Keep testing',
    desc: 'The typical simulation stays inside the limit, but it misses the A and B bars.',
  },
  {
    g: 'D',
    title: 'Risky',
    desc: 'Profitable on average, but the typical simulation breaks the drawdown limit.',
  },
  { g: 'F', title: 'Unviable', desc: 'The typical simulation loses money.' },
]

export default function GradeLegend({ forceCollapsed = false }: { forceCollapsed?: boolean }) {
  const [open, setOpen] = useState(false)
  const isOpen = open && !forceCollapsed
  return (
    <div className="rounded-lg border border-border-subtle bg-bg-surface">
      <button
        onClick={() => setOpen((o) => !o)}
        disabled={forceCollapsed}
        className="w-full flex items-center justify-between px-4 py-2.5 text-left disabled:cursor-default"
      >
        <span className="text-[12px] font-semibold text-text-secondary uppercase tracking-[0.5px]">
          Grade key
        </span>
        {isOpen ? (
          <ChevronUp size={15} className="text-text-tertiary" />
        ) : (
          <ChevronDown size={15} className="text-text-tertiary" />
        )}
      </button>
      {isOpen && (
        <div className="px-4 pb-4 pt-3 space-y-3 border-t border-border-subtle">
          {ROWS.map((r) => (
            <div key={r.g} className="flex items-start gap-3">
              <div className="w-6 flex-shrink-0 pt-[1px]">
                <RobustnessGradeBadge grade={r.g} size="sm" />
              </div>
              <div className="min-w-0 text-[12px] leading-snug">
                <span className="font-semibold text-text-primary">{r.title}</span>
                <span className="text-text-tertiary"> — {r.desc}</span>
              </div>
            </div>
          ))}
          {/* The no-letter outcome is a real one (grading.py returns None), so the key shows it —
              a key that lists only letters leaves an ungraded test looking like a broken page. */}
          <div className="flex items-start gap-3">
            <div className="w-6 flex-shrink-0 pt-[1px]">
              <span className="inline-flex items-center rounded font-mono text-xs px-1.5 py-0.5 bg-bg-hover text-text-tertiary border border-border-subtle">
                —
              </span>
            </div>
            <div className="min-w-0 text-[12px] leading-snug">
              <span className="font-semibold text-text-primary">No grade</span>
              <span className="text-text-tertiary">
                {' '}
                — the ruleset sets no drawdown limit, so there is nothing to grade against.
              </span>
            </div>
          </div>
          <p className="text-[11px] text-text-tertiary leading-snug">
            Walk-forward and sensitivity count only when they ran. A walk-forward that ran but could
            not be judged holds the grade at B.
          </p>
        </div>
      )}
    </div>
  )
}
