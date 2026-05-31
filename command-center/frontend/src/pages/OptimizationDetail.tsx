import { useParams, useNavigate } from 'react-router-dom'
import { ArrowLeft, Sliders, Download } from 'lucide-react'
import { WorthinessBadge } from '@/components/WorthinessBadge'
import { OptimizationHeatmap } from '@/components/OptimizationHeatmap'
import { useOptimization } from '@/hooks/useLab'
import type { BacktestSummary } from '@/types'

function fmtDate(iso: string) {
  return new Date(iso).toLocaleDateString('en-US', { month: 'short', day: 'numeric', year: 'numeric' })
}

function fmtMoney(n: number | null) {
  if (n == null) return '—'
  const abs = Math.abs(n)
  return `${n < 0 ? '-' : '+'}$${abs.toLocaleString('en-US', { maximumFractionDigits: 0 })}`
}

function exportCsv(runs: BacktestSummary[], paramKeys: string[]) {
  const headers = ['rank', ...paramKeys, 'net_pnl', 'max_drawdown', 'profit_factor', 'win_rate', 'trade_count', 'sharpe', 'worthiness']
  const rows = runs
    .filter(r => r.status === 'complete')
    .sort((a, b) => (b.profit_factor ?? -Infinity) - (a.profit_factor ?? -Infinity))
    .map((r, i) => [
      i + 1,
      ...paramKeys.map(k => r.params?.[k] ?? ''),
      r.net_pnl ?? '',
      r.max_drawdown ?? '',
      r.profit_factor ?? '',
      r.win_rate ?? '',
      r.trade_count ?? '',
      r.sharpe ?? '',
      r.worthiness?.tier ?? '',
    ].join(','))
  const csv = [headers.join(','), ...rows].join('\n')
  const blob = new Blob([csv], { type: 'text/csv' })
  const url = URL.createObjectURL(blob)
  const a = document.createElement('a')
  a.href = url; a.download = 'optimization_results.csv'; a.click()
  URL.revokeObjectURL(url)
}

export function OptimizationDetail() {
  const { optimizationId } = useParams<{ optimizationId: string }>()
  const navigate           = useNavigate()
  const { data: opt, isLoading, isFetching, refetch } = useOptimization(optimizationId ?? null)

  const isRunning = opt && opt.status === 'running'

  const paramKeys = opt ? Object.keys(opt.param_grid) : []
  const sweptKeys = paramKeys.filter(k => {
    const spec = opt?.param_grid[k]
    return Array.isArray(spec) ? spec.length > 1 : typeof spec === 'object' && spec !== null
  })

  const is2D     = sweptKeys.length === 2
  const completeRuns = opt?.runs.filter(r => r.status === 'complete') ?? []
  const top10    = [...completeRuns]
    .sort((a, b) => (b.profit_factor ?? -Infinity) - (a.profit_factor ?? -Infinity))
    .slice(0, 10)

  const bestRun  = opt?.best_run_id
    ? opt.runs.find(r => r.run_id === opt.best_run_id)
    : top10[0]

  return (
    <div>
      <button
        onClick={() => navigate('/backtests?tab=optimizations')}
        className="flex items-center gap-2 text-[13px] text-text-tertiary hover:text-text-secondary mb-5 transition-colors"
      >
        <ArrowLeft size={14} /> Optimizations
      </button>

      {isLoading && (
        <div className="animate-pulse space-y-4">
          <div className="h-6 w-64 bg-bg-surface rounded" />
          <div className="h-4 w-80 bg-bg-surface rounded" />
          <div className="h-[300px] bg-bg-surface rounded-lg" />
        </div>
      )}

      {opt && (
        <div className="space-y-7">
          {/* Header */}
          <div className="flex items-start justify-between gap-4">
            <div>
              <div className="flex items-center gap-2">
                <Sliders size={18} className="text-gold-text" />
                <h1 className="text-h1 font-semibold">Optimization</h1>
              </div>
              <div className="flex flex-wrap items-center gap-x-3 gap-y-1 mt-2 text-[13px] text-text-secondary">
                <span className="font-mono text-text-primary">{opt.strategy_name || opt.strategy_id}</span>
                <span className="text-text-tertiary">·</span>
                <span className="font-mono text-accent">{opt.instrument}</span>
                <span className="text-text-tertiary">·</span>
                <span>{fmtDate(opt.start_date)} → {fmtDate(opt.end_date)}</span>
                <span className="text-text-tertiary">·</span>
                <span className="capitalize">{opt.mode} mode</span>
                <span className="text-text-tertiary">·</span>
                <span className="capitalize">{opt.search_method}</span>
              </div>
            </div>
            <div className="flex items-center gap-3 flex-shrink-0">
              {isRunning && (
                <button
                  onClick={() => refetch()}
                  disabled={isFetching}
                  className="text-[11px] text-accent hover:underline disabled:opacity-50"
                >
                  {isFetching ? 'Refreshing…' : 'Refresh'}
                </button>
              )}
              <div className="text-right">
                <div className="text-[13px] font-semibold text-text-primary">
                  {opt.completed_runs} / {opt.estimated_runs} runs
                </div>
                <span className={`text-[11px] capitalize ${opt.status === 'complete' ? 'text-pos-text' : opt.status === 'running' ? 'text-accent' : 'text-neg-text'}`}>
                  {opt.status}
                </span>
              </div>
            </div>
          </div>

          {/* Progress bar */}
          <div className="w-full bg-bg-surface rounded-full h-[5px] overflow-hidden">
            <div
              className="h-full bg-accent transition-all duration-500"
              style={{ width: `${opt.estimated_runs > 0 ? (opt.completed_runs / opt.estimated_runs) * 100 : 0}%` }}
            />
          </div>

          {/* Best param set callout */}
          {bestRun && (
            <div className="bg-gold-muted border border-gold-text/25 rounded-lg px-4 py-3 flex flex-wrap items-center gap-x-6 gap-y-2">
              <div>
                <div className="text-[11px] text-gold-text/70 uppercase tracking-wide font-semibold mb-1">
                  Best param set
                </div>
                <div className="flex items-center gap-2 flex-wrap">
                  {sweptKeys.map(k => (
                    <span key={k} className="text-[12px] font-mono">
                      <span className="text-text-tertiary">{k}=</span>
                      <span className="text-gold-text font-semibold">{String(bestRun.params?.[k] ?? '?')}</span>
                    </span>
                  ))}
                </div>
              </div>
              <div className="flex items-center gap-4 ml-auto">
                <div className="text-center">
                  <div className="text-[11px] text-text-tertiary">P&L</div>
                  <div className={`text-[14px] font-semibold font-mono ${(bestRun.net_pnl ?? 0) >= 0 ? 'text-pos-text' : 'text-neg-text'}`}>
                    {fmtMoney(bestRun.net_pnl)}
                  </div>
                </div>
                <div className="text-center">
                  <div className="text-[11px] text-text-tertiary">PF</div>
                  <div className="text-[14px] font-semibold font-mono text-text-primary">
                    {bestRun.profit_factor?.toFixed(2) ?? '—'}
                  </div>
                </div>
                <WorthinessBadge worthiness={bestRun.worthiness} size="md" />
                <button
                  onClick={() => navigate(`/backtests/runs/${bestRun.run_id}`)}
                  className="text-[12px] text-accent hover:underline"
                >
                  View run →
                </button>
              </div>
            </div>
          )}

          {/* Visualization */}
          {completeRuns.length > 0 && (
            <div>
              <h2 className="text-[11px] font-semibold text-text-secondary uppercase tracking-[0.7px] mb-3">
                {is2D ? 'Heatmap' : `Top ${Math.min(10, top10.length)} results`}
              </h2>

              {is2D ? (
                <OptimizationHeatmap
                  runs={opt.runs}
                  paramX={sweptKeys[0]}
                  paramY={sweptKeys[1]}
                />
              ) : (
                <ResultsTable runs={top10} sweptKeys={sweptKeys} navigate={navigate} />
              )}
            </div>
          )}

          {/* Full table (for all runs) */}
          {completeRuns.length > 10 && !is2D && (
            <details className="group">
              <summary className="cursor-pointer text-[12px] text-accent hover:underline list-none">
                View all {completeRuns.length} results
              </summary>
              <div className="mt-3">
                <ResultsTable runs={completeRuns} sweptKeys={sweptKeys} navigate={navigate} />
              </div>
            </details>
          )}

          {/* Export CSV */}
          {completeRuns.length > 0 && (
            <div className="flex justify-end">
              <button
                onClick={() => exportCsv(opt.runs, paramKeys)}
                className="flex items-center gap-2 px-3 py-[6px] rounded-md text-[12px] text-text-secondary hover:text-text-primary bg-bg-surface border border-border-subtle hover:border-border-default transition-colors"
              >
                <Download size={13} />
                Export CSV
              </button>
            </div>
          )}
        </div>
      )}
    </div>
  )
}

function ResultsTable({
  runs, sweptKeys, navigate,
}: {
  runs: BacktestSummary[]
  sweptKeys: string[]
  navigate: ReturnType<typeof useNavigate>
}) {
  const sorted = [...runs]
    .sort((a, b) => (b.profit_factor ?? -Infinity) - (a.profit_factor ?? -Infinity))

  return (
    <div className="bg-bg-surface border border-border-subtle rounded-lg overflow-hidden overflow-x-auto">
      <table className="w-full text-[12px]">
        <thead>
          <tr className="border-b border-border-subtle">
            <th className="text-left px-3 py-2 text-text-tertiary font-medium w-10">Rank</th>
            {sweptKeys.map(k => (
              <th key={k} className="text-left px-3 py-2 text-text-tertiary font-medium font-mono">{k}</th>
            ))}
            <th className="text-left px-3 py-2 text-text-tertiary font-medium">P&L</th>
            <th className="text-left px-3 py-2 text-text-tertiary font-medium">Max DD</th>
            <th className="text-left px-3 py-2 text-text-tertiary font-medium">PF</th>
            <th className="text-left px-3 py-2 text-text-tertiary font-medium">Trades</th>
            <th className="text-left px-3 py-2 text-text-tertiary font-medium">Score</th>
            <th className="px-3 py-2 w-16" />
          </tr>
        </thead>
        <tbody className="divide-y divide-border-subtle">
          {sorted.map((run, i) => {
            const pnlCls = (run.net_pnl ?? 0) >= 0 ? 'text-pos-text' : 'text-neg-text'
            return (
              <tr
                key={run.run_id}
                onClick={() => navigate(`/backtests/runs/${run.run_id}`)}
                className="hover:bg-bg-hover cursor-pointer transition-colors"
              >
                <td className="px-3 py-2 text-text-tertiary tabular-nums">{i + 1}</td>
                {sweptKeys.map(k => (
                  <td key={k} className="px-3 py-2 font-mono text-text-primary">
                    {String(run.params?.[k] ?? '—')}
                  </td>
                ))}
                <td className={`px-3 py-2 font-mono tabular-nums ${pnlCls}`}>
                  {run.net_pnl != null ? `${run.net_pnl >= 0 ? '+' : ''}$${Math.abs(run.net_pnl).toLocaleString('en-US', { maximumFractionDigits: 0 })}` : '—'}
                </td>
                <td className="px-3 py-2 font-mono tabular-nums text-neg-text">
                  {run.max_drawdown != null ? `$${run.max_drawdown.toLocaleString('en-US', { maximumFractionDigits: 0 })}` : '—'}
                </td>
                <td className="px-3 py-2 font-mono tabular-nums">
                  {run.profit_factor?.toFixed(2) ?? '—'}
                </td>
                <td className="px-3 py-2 tabular-nums text-text-secondary">
                  {run.trade_count ?? '—'}
                </td>
                <td className="px-3 py-2">
                  <WorthinessBadge worthiness={run.worthiness} />
                </td>
                <td className="px-3 py-2 text-right">
                  <span className="text-[11px] text-accent hover:underline">View →</span>
                </td>
              </tr>
            )
          })}
        </tbody>
      </table>
    </div>
  )
}
