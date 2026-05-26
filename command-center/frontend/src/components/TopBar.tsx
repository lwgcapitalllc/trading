import { RefreshCw } from 'lucide-react'
import { useQueryClient } from '@tanstack/react-query'
import { useLocation } from 'react-router-dom'
import { useState } from 'react'

const ROUTE_LABELS: Record<string, string> = {

  '/':             'Overview',
  '/smart-money':  'Smart Money',
  '/bots':         'Bots',
  '/backtests':    'Backtests',
  '/stress-tests': 'Stress Tests',
  '/settings':     'Settings',
}

function usePageLabel() {
  const { pathname } = useLocation()
  // Match longest prefix
  const key = Object.keys(ROUTE_LABELS)
    .filter(k => pathname === k || pathname.startsWith(k + '/'))
    .sort((a, b) => b.length - a.length)[0]
  return ROUTE_LABELS[key] ?? pathname
}

export function TopBar() {
  const qc = useQueryClient()
  const label = usePageLabel()
  const [refreshing, setRefreshing] = useState(false)
  const [lastRefresh, setLastRefresh] = useState(() => new Date())

  const handleRefresh = async () => {
    setRefreshing(true)
    await qc.invalidateQueries()
    setLastRefresh(new Date())
    setRefreshing(false)
  }

  const ago = Math.round((Date.now() - lastRefresh.getTime()) / 1000)
  const agoLabel = ago < 60 ? `${ago}s ago` : `${Math.round(ago / 60)}m ago`

  return (
    <div className="h-[52px] flex-shrink-0 border-b border-border-subtle bg-bg-base flex items-center px-[22px] gap-[14px]">
      <div className="text-[13px] text-text-secondary">
        LWG Capital Command Center{' '}
        <span className="text-text-tertiary">/</span>{' '}
        <b className="text-text-primary font-semibold">{label}</b>
      </div>
      <div className="ml-auto flex items-center gap-[10px]">
        <span className="text-micro text-text-tertiary">Updated {agoLabel}</span>
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
