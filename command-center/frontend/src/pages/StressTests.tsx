import { Activity } from 'lucide-react'
import { ScaffoldBanner } from '@/components/ScaffoldBanner'
import { EmptyState } from '@/components/EmptyState'
import { useStressTestResults } from '@/hooks/useStressTests'

export function StressTests() {
  useStressTestResults() // wired — returns empty until implemented

  return (
    <div>
      <div className="flex items-end gap-3 mb-[18px]">
        <h1 className="text-h1 font-semibold">Stress Tests</h1>
      </div>
      <ScaffoldBanner message="Scaffolded route. Monte Carlo fan charts and drawdown percentiles; built after backtests." />

      {/* Fan chart section */}
      <div className="mb-6">
        <h2 className="text-[13px] font-semibold text-text-secondary uppercase tracking-[0.7px] mb-3">
          Equity Curve Fan Chart
        </h2>
        <div className="bg-bg-surface border border-border-subtle rounded-lg h-[240px] flex items-center justify-center text-text-tertiary text-small">
          Many simulated equity paths overlaid — fan chart renders here once stress tests are connected.
        </div>
      </div>

      {/* KPI stats section */}
      <div>
        <h2 className="text-[13px] font-semibold text-text-secondary uppercase tracking-[0.7px] mb-3">
          Key Risk Statistics
        </h2>
        <EmptyState
          icon={<Activity size={22} />}
          title="Monte Carlo stress tests"
          description="Worst-1% drawdown, breach probability, eval pass rate, and P&L distribution for backtest survivors."
        />
      </div>
    </div>
  )
}
