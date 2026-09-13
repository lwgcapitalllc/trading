import { useState } from 'react'
import { ChevronDown, ChevronUp } from 'lucide-react'
import { WorthinessBadge } from './WorthinessBadge'
import type { WorthinessScore } from '@/types'

// Explains the worthiness Score shown in the Runs table's Score column — the automatic verdict on a
// completed run (how good it is + what to do next). Mirrors backend services/worthiness.py exactly:
// Tier 3 is checked first, Tier 1 needs all three bars, and Tier 2 is everything in between — which
// is why a strong run with 30–49 trades lands in OPTIMIZE, and the row says so.
// Collapsible — reference info, default closed. Companion to GradeLegend (which explains stress A–F).

const ROWS: { tier: WorthinessScore['tier']; desc: string }[] = [
  {
    tier: 'TIER_1_STRESS_TEST',
    desc: 'Profit factor above 1.3, drawdown under 70% of the limit, and 50 or more trades.',
  },
  {
    tier: 'TIER_2_OPTIMIZE',
    desc: 'Inside the limit with 30 or more trades, but short of the stress-test bar.',
  },
  {
    tier: 'TIER_3_DISCARD',
    desc: 'Fewer than 30 trades, drawdown past the limit, or profit factor below 0.8.',
  },
]

export default function WorthinessLegend({ forceCollapsed = false }: { forceCollapsed?: boolean }) {
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
          Score key
        </span>
        {isOpen ? (
          <ChevronUp size={15} className="text-text-tertiary" />
        ) : (
          <ChevronDown size={15} className="text-text-tertiary" />
        )}
      </button>
      {isOpen && (
        <div className="px-4 pb-4 pt-3 space-y-3 border-t border-border-subtle">
          <div className="text-[12px] text-text-secondary leading-relaxed">
            The next step for a finished run, judged against the strictest drawdown limit it was
            checked against. A run checked against no limit gets no score.
          </div>
          {ROWS.map((r) => (
            <div key={r.tier} className="flex items-start gap-3">
              <div className="w-[92px] flex-shrink-0 pt-[1px]">
                <WorthinessBadge
                  worthiness={{ tier: r.tier, reason: null, computed_against_firm: null }}
                />
              </div>
              <div className="min-w-0 text-[12px] leading-snug text-text-tertiary">{r.desc}</div>
            </div>
          ))}
        </div>
      )}
    </div>
  )
}
