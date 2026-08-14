import { useState } from 'react'
import { ChevronDown, ChevronUp } from 'lucide-react'
import { WorthinessBadge } from './WorthinessBadge'
import type { WorthinessScore } from '@/types'

// Explains the worthiness Score shown in the Runs table's Score column — the automatic verdict on a
// completed run (how good it is + what to do next). Mirrors the tiers in backend services/worthiness.py.
// Collapsible — reference info, default closed. Companion to GradeLegend (which explains stress A–F).

const ROWS: { tier: WorthinessScore['tier']; desc: string }[] = [
  {
    tier: 'TIER_1_STRESS_TEST',
    desc: 'Strong enough to stress test next. Profit factor above 1.3, drawdown safely under the firm limit, and at least 50 trades.',
  },
  {
    tier: 'TIER_2_OPTIMIZE',
    desc: 'Promising but not there yet. Profit factor between 0.8 and 1.3, or drawdown nearing the limit — worth optimizing. At least 30 trades.',
  },
  {
    tier: 'TIER_3_DISCARD',
    desc: 'Not viable as-is. Profit factor below 0.8, drawdown over the firm limit, or fewer than 30 trades.',
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
          Score key — what each score means
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
            The Score is an automatic verdict on each completed run — how good the result is and
            what to do with it next.
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
