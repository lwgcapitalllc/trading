import { RefreshCw } from 'lucide-react'
import { useQueryClient } from '@tanstack/react-query'
import { useState } from 'react'

export function TopBar() {
  const qc = useQueryClient()
  const [refreshing, setRefreshing] = useState(false)

  const handleRefresh = async () => {
    setRefreshing(true)
    await qc.invalidateQueries()
    setRefreshing(false)
  }

  return (
    <div
      className="h-[56px] flex-shrink-0 bg-bg-base flex items-center px-6 relative"
      style={{
        borderBottom: '1px solid rgba(0,229,255,0.18)',
        boxShadow: '0 1px 0 rgba(0,229,255,0.07), 0 4px 28px rgba(0,0,0,0.55)',
      }}
    >
      {/* Subtle left-side cyan wash */}
      <div
        className="absolute inset-0 pointer-events-none"
        style={{ background: 'linear-gradient(90deg, rgba(0,229,255,0.05) 0%, transparent 40%)' }}
      />

      {/* ── Brand wordmark ────────────────────────────────────────── */}
      <div className="relative flex items-baseline gap-[6px] select-none">
        <span
          className="text-[23px] font-black tracking-tight leading-none"
          style={{
            background: 'linear-gradient(90deg, #00e5ff 0%, #d9a441 100%)',
            WebkitBackgroundClip: 'text',
            WebkitTextFillColor: 'transparent',
            backgroundClip: 'text',
            filter: 'drop-shadow(0 0 8px rgba(0,229,255,0.6))',
          }}
        >
          LWG
        </span>
        <span className="text-[23px] font-bold tracking-tight text-white leading-none">
          Capital
        </span>
      </div>

      {/* ── Refresh ───────────────────────────────────────────────── */}
      <div className="relative ml-auto">
        <button
          onClick={handleRefresh}
          className="flex items-center justify-center w-8 h-8 rounded-md border border-border-default bg-bg-surface text-text-primary hover:bg-bg-hover hover:border-border-strong transition-colors duration-[120ms]"
          title="Refresh all data"
        >
          <RefreshCw size={14} className={refreshing ? 'animate-spin' : ''} />
        </button>
      </div>
    </div>
  )
}
