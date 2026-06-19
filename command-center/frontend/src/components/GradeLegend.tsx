import { useState } from 'react'
import { ChevronDown, ChevronUp } from 'lucide-react'
import RobustnessGradeBadge from './RobustnessGradeBadge'

// Explains the A–F robustness grade so the trader knows what each means and what to target before
// taking a strategy to a bot. Mirrors the backend rubric in services/grading.py (MC tail vs the loss
// limit + walk-forward degradation + sensitivity worst-case). Collapsible — reference info, default closed.

type Grade = 'A' | 'B' | 'C' | 'D' | 'F'
const ROWS: { g: Grade; title: string; desc: string }[] = [
  { g: 'A', title: 'Bot-ready · funded',  desc: 'Worst 1% of simulations stays under the loss limit, walk-forward degradation < 20%, parameter sensitivity worst-case < 25%.' },
  { g: 'B', title: 'Eval-ready',          desc: 'Worst 5% stays under the limit, walk-forward degradation < 30%, sensitivity worst-case < 40%.' },
  { g: 'C', title: 'Demo · keep testing', desc: 'Median stays under the limit, but it misses the A/B robustness bars. Not ready for real money.' },
  { g: 'D', title: 'Risky',               desc: 'Median is profitable but the median drawdown breaches the limit — too likely to fail.' },
  { g: 'F', title: 'Unviable',            desc: 'The median simulation loses money.' },
]

export default function GradeLegend({ forceCollapsed = false }: { forceCollapsed?: boolean }) {
  const [open, setOpen] = useState(false)
  const isOpen = open && !forceCollapsed
  return (
    <div className="rounded-lg border border-border-subtle bg-bg-surface">
      <button
        onClick={() => setOpen(o => !o)}
        disabled={forceCollapsed}
        className="w-full flex items-center justify-between px-4 py-2.5 text-left disabled:cursor-default"
      >
        <span className="text-[12px] font-semibold text-text-secondary uppercase tracking-[0.5px]">
          Grade key — what each grade means
        </span>
        {isOpen ? <ChevronUp size={15} className="text-text-tertiary" /> : <ChevronDown size={15} className="text-text-tertiary" />}
      </button>
      {isOpen && (
        <div className="px-4 pb-4 pt-3 space-y-3 border-t border-border-subtle">
          <div className="text-[12px] text-text-secondary leading-relaxed">
            Target <span className="text-pos-text font-semibold">A</span> or <span className="text-accent font-semibold">B</span> before deploying to a bot —
            <span className="text-pos-text font-semibold"> A</span> for funded accounts, <span className="text-accent font-semibold">B</span> is the minimum for a paid evaluation.
          </div>
          {ROWS.map(r => (
            <div key={r.g} className="flex items-start gap-3">
              <div className="w-6 flex-shrink-0 pt-[1px]"><RobustnessGradeBadge grade={r.g} size="sm" /></div>
              <div className="min-w-0 text-[12px] leading-snug">
                <span className="font-semibold text-text-primary">{r.title}</span>
                <span className="text-text-tertiary"> — {r.desc}</span>
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  )
}
