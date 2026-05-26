import { BarChart2 } from 'lucide-react'
import { ScaffoldBanner } from '@/components/ScaffoldBanner'
import { EmptyState } from '@/components/EmptyState'
import { useBacktestRuns } from '@/hooks/useBacktests'

export function Backtests() {
  useBacktestRuns() // wired — returns empty until implemented

  return (
    <div>
      <div className="flex items-end gap-3 mb-[18px]">
        <h1 className="text-h1 font-semibold">Backtests</h1>
      </div>
      <ScaffoldBanner message="Scaffolded route. Layout and data contract defined in the build spec; built after Smart Money and Bots ship." />

      {/* Results grid section */}
      <div className="mb-6">
        <h2 className="text-[13px] font-semibold text-text-secondary uppercase tracking-[0.7px] mb-3">
          Strategy / Instrument Results
        </h2>
        <EmptyState
          icon={<BarChart2 size={22} />}
          title="LucidFlex backtest results"
          description="KEEP / WARN / DISCARD grid across the 6 strategy-instrument combos, tiered KPIs, and per-combo equity curves."
        />
      </div>

      {/* KPI cards section */}
      <div>
        <h2 className="text-[13px] font-semibold text-text-secondary uppercase tracking-[0.7px] mb-3">
          KPI Tiers
        </h2>
        <div className="bg-bg-surface border border-border-subtle rounded-lg p-4 text-text-tertiary text-small">
          Tiered KPIs (Tier 1 prop-specific, Tier 2 edge quality, Tier 3 standard) will render here once the backtest pipeline is connected.
        </div>
      </div>
    </div>
  )
}
