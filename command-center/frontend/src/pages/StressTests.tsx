import { Activity } from 'lucide-react'
import { ScaffoldBanner } from '@/components/ScaffoldBanner'
import { EmptyState } from '@/components/EmptyState'

export function StressTests() {
  return (
    <div>
      <div className="flex items-end gap-3 mb-[18px]">
        <h1 className="text-h1 font-semibold">Stress Tests</h1>
      </div>
      <ScaffoldBanner message="Use the Stress Tests tab in Backtests to view and run stress tests on individual backtest runs." />

      <EmptyState
        icon={<Activity size={22} />}
        title="Stress Tests"
        description="Navigate to Backtests → Stress Tests tab to view all stress test results."
      />
    </div>
  )
}
