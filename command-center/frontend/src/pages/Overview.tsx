import { LayoutDashboard } from 'lucide-react'
import { EmptyState } from '@/components/EmptyState'

export function Overview() {
  return (
    <div>
      <div className="flex items-end gap-3 mb-[18px]">
        <h1 className="text-h1 font-semibold">Overview</h1>
      </div>
      <EmptyState
        icon={<LayoutDashboard size={22} />}
        title="Overview — scaffolded"
        description="A cross-module summary: smart-money run status, bot health, recent backtests at a glance. Route exists; built after the two priority modules."
      />
    </div>
  )
}
