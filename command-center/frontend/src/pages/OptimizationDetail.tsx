import { useEffect, useMemo, useRef, useState } from 'react'
import { useParams, useNavigate } from 'react-router-dom'
import { runningJobFor, runnerScope } from '@/lib/runner'
import { ArrowLeft, Download, CheckCircle2, Loader2, XCircle, AlertTriangle, RotateCcw, Square, Trash2, Activity, ChevronUp, ChevronDown, Copy, Check, SlidersHorizontal } from 'lucide-react'
import { useOptimization, useCancelOptimization, useRetryOptimization, useRerunOptimization, useDeleteOptimization, useRetryBacktest, useRunningVpsJob, useOptimizationLog, useBacktestRuns, useBacktestRun } from '@/hooks/useLab'
import { useRunningStressLock, useStressTests } from '@/hooks/useStressTests'
import type { BacktestSummary, OptimizationDetail as Opt } from '@/types'
import StickyHeader from '@/components/StickyHeader'

// ── Formatters ────────────────────────────────────────────────────────────────

// Local midnight, not UTC — a bare 'YYYY-MM-DD' otherwise renders a day early west of
// Greenwich. Same fix in BacktestDetail/SweepDetail/StackDetail/StressTestDetail.
function fmtDate(iso: string) {
  return new Date(`${iso.slice(0, 10)}T00:00:00`).toLocaleDateString('en-US', { month: 'short', day: 'numeric', year: 'numeric' })
}

function fmtDuration(seconds: number): string {
  if (seconds < 60)  return `${seconds}s`
  if (seconds < 3600) return `${Math.floor(seconds / 60)}m ${seconds % 60}s`
  const h = Math.floor(seconds / 3600)
  const m = Math.floor((seconds % 3600) / 60)
  return `${h}h ${m}m`
}

function firmShortName(firmId: string): string {
  const parts = firmId.split('_')
  if (parts.length < 3) return firmId
  const brandMap: Record<string, string> = { lucidflex: 'LF', apex: 'Apex', tradeify: 'TF' }
  const brand = brandMap[parts[0]] ?? parts[0].slice(0, 2).toUpperCase()
  const size  = (parts[1] ?? '').toUpperCase()
  const tier  = parts[2] === 'eval' ? 'Eval' : parts[2] === 'funded' ? 'Funded' : (parts[2] ?? '')
  return `${brand}${size} ${tier}`
}

function firmChipCls(firmId: string): string {
  if (firmId.includes('_eval'))   return 'bg-warn-muted text-warn-text border border-warn-text/20'
  if (firmId.includes('_funded')) return 'bg-pos-muted text-pos-text border border-pos-text/20'
  return 'bg-bg-surface border border-border-subtle text-text-tertiary'
}

// ── Live elapsed timer ────────────────────────────────────────────────────────

// Returns null when there is no honest number to show — a finished job with no end time is a
// row written before `fail_optimization` recorded one, and counting up to now() on it produced
// "Ran for 74h" on something that died on Tuesday.
function useElapsed(startIso: string | null, endIso: string | null, running: boolean): number | null {
  const [elapsed, setElapsed] = useState<number | null>(null)
  useEffect(() => {
    if (!startIso) { setElapsed(null); return }
    const start = new Date(startIso).getTime()
    if (!running) {
      setElapsed(endIso ? Math.round((new Date(endIso).getTime() - start) / 1000) : null)
      return
    }
    const tick = () => setElapsed(Math.round((Date.now() - start) / 1000))
    tick()
    const id = setInterval(tick, 1000)
    return () => clearInterval(id)
  }, [startIso, endIso, running])
  return elapsed
}

// ── CSV export ────────────────────────────────────────────────────────────────

// RFC-4180 quoting. Without it a value containing a comma (a list-swept string, an error
// message) silently shifts every column to its right by one, which reads as corrupt data
// rather than as a formatting bug.
function csvCell(v: unknown): string {
  const s = v == null ? '' : String(v)
  return /[",\n\r]/.test(s) ? `"${s.replace(/"/g, '""')}"` : s
}

function exportCsv(runs: BacktestSummary[], paramKeys: string[], optId: string) {
  // run_id first: without it a row cannot be joined back to the run it describes, which is the
  // one thing you export a grid to do.
  const headers = ['rank', 'run_id', ...paramKeys, 'net_pnl', 'max_drawdown', 'profit_factor', 'win_rate', 'trade_count', 'sharpe', 'worthiness']
  const rows = runs
    .filter(r => r.status === 'complete')
    .sort((a, b) => (b.profit_factor ?? -Infinity) - (a.profit_factor ?? -Infinity))
    .map((r, i) => [
      i + 1, r.run_id,
      ...paramKeys.map(k => r.params?.[k] ?? ''),
      r.net_pnl ?? '', r.max_drawdown ?? '', r.profit_factor ?? '',
      r.win_rate ?? '', r.trade_count ?? '', r.sharpe ?? '',
      r.worthiness?.tier ?? '',
    ].map(csvCell).join(','))
  const csv   = [headers.map(csvCell).join(','), ...rows].join('\n')
  const blob  = new Blob([csv], { type: 'text/csv' })
  const url   = URL.createObjectURL(blob)
  const a     = document.createElement('a')
  a.href = url; a.download = `optimization_${optId}.csv`; a.click()
  URL.revokeObjectURL(url)
}

// ── Progress card ─────────────────────────────────────────────────────────────

function ProgressCard({ opt, onCancel, onRetry, cancelling, retrying, jobBlocked }: {
  opt: Opt
  onCancel: () => void
  onRetry: () => void
  cancelling: boolean
  retrying: boolean
  jobBlocked: boolean
}) {
  const isRunning  = opt.status === 'running'
  const isCancelled = opt.status === 'failed_cancelled'
  const isComplete = opt.status === 'complete'

  const completeCount = opt.runs.filter(r => r.status === 'complete').length
  const failedCount   = opt.runs.filter(r => r.status.startsWith('failed')).length
  const total         = opt.estimated_runs

  const completePct = total > 0 ? (completeCount / total) * 100 : 0
  const failedPct   = total > 0 ? (failedCount   / total) * 100 : 0
  const overallPct  = Math.round(completePct + failedPct)

  const hasFailures   = failedCount > 0
  const allFailed     = failedCount === total && total > 0
  const failingBadly  = isRunning && failedCount > 0

  const elapsed = useElapsed(opt.created_at, opt.completed_at ?? null, isRunning)

  const statusLabel = isRunning ? 'Running' : isComplete ? 'Complete' : isCancelled ? 'Cancelled' : 'Failed'
  const borderCls   = isComplete && !hasFailures ? 'border-accent/20 bg-accent/5'
    : allFailed || isCancelled ? 'border-neg-text/20 bg-neg-muted'
    : hasFailures && isComplete ? 'border-warn-text/25 bg-warn-muted/20'
    : 'border-border-default bg-bg-surface'

  return (
    <div className={`rounded-xl border px-6 py-5 ${borderCls}`}>
      <div className="flex items-start justify-between gap-6">
        {/* Left: status + progress */}
        <div className="flex-1 min-w-0">
          <div className="flex items-center gap-2 mb-3 flex-wrap">
            {isRunning   && <Loader2     size={14} className="text-accent animate-spin flex-shrink-0" />}
            {isComplete  && !hasFailures && <CheckCircle2 size={14} className="text-accent flex-shrink-0" />}
            {isComplete  && hasFailures  && <AlertTriangle size={14} className="text-warn-text flex-shrink-0" />}
            {!isRunning  && !isComplete  && <XCircle size={14} className="text-neg-text flex-shrink-0" />}
            <span className={`text-[13px] font-semibold ${
              isRunning ? 'text-accent'
              : isComplete && !hasFailures ? 'text-accent'
              : isComplete && hasFailures  ? 'text-warn-text'
              : 'text-neg-text'
            }`}>
              {statusLabel}
            </span>
            {isRunning && <span className="text-[11px] text-text-tertiary">· auto-refreshing</span>}
          </div>

          {/* Progress bar */}
          {isRunning && overallPct === 0 ? (
            <div className="w-full bg-bg-sunken rounded-full h-[7px] overflow-hidden mb-2">
              {opt.live_pct && opt.live_pct > 0 ? (
                <div
                  className="h-full bg-accent/80 rounded-full transition-all duration-700"
                  style={{ width: `${opt.live_pct}%` }}
                />
              ) : (
                <div className="h-full w-1/3 bg-accent/60 rounded-full animate-pulse" />
              )}
            </div>
          ) : (
            <div className="w-full bg-bg-sunken rounded-full h-[7px] overflow-hidden mb-2 flex">
              <div
                className="h-full bg-accent transition-all duration-700"
                style={{ width: `${completePct}%` }}
              />
              <div
                className="h-full bg-neg-text/70 transition-all duration-700"
                style={{ width: `${failedPct}%` }}
              />
            </div>
          )}

          <div className="flex items-center justify-between gap-4 flex-wrap">
            <div className="flex items-center gap-4 text-[12px]">
              {isRunning && overallPct === 0 ? (
                <span className="text-text-tertiary">
                  {opt.live_message ?? `Running ${total} combination${total !== 1 ? 's' : ''}…`}
                </span>
              ) : (
                <>
                  <span className="text-text-secondary">
                    <span className="font-mono font-semibold text-accent">{completeCount}</span>
                    <span className="text-text-tertiary"> passed</span>
                  </span>
                  {failedCount > 0 && (
                    <span className="text-text-secondary">
                      <span className="font-mono font-semibold text-neg-text">{failedCount}</span>
                      <span className="text-text-tertiary"> failed</span>
                    </span>
                  )}
                  <span className="text-text-tertiary">
                    of {total} combinations
                  </span>
                </>
              )}
            </div>
            <span className="text-[12px] font-mono font-semibold tabular-nums text-text-secondary">
              {isRunning && overallPct === 0
                ? (opt.live_pct ? `${opt.live_pct}%` : '')
                : `${overallPct}%`}
            </span>
          </div>

          {/* Inline failure warning while running */}
          {failingBadly && (
            <div className="mt-3 pt-3 border-t border-border-subtle flex items-start gap-2">
              <AlertTriangle size={13} className="text-warn-text flex-shrink-0 mt-[1px]" />
              <p className="text-[12px] text-warn-text">
                {failedCount} run{failedCount !== 1 ? 's are' : ' is'} failing.
                {runnerScope(opt.runner) === 'python'
                  ? ' Check the run logs — a local sweep needs the broker data cache and enough memory.'
                  : runnerScope(opt.runner) === 'mt5'
                  ? ' Check that the MT5 agent is running and the MT5_Lab terminal is available on the VPS.'
                  : ' Check that NT8 is open with the Strategy Analyzer window active on the VPS.'}
                {' '}You can cancel now and retry once the platform is ready.
              </p>
            </div>
          )}

          {!failingBadly && isRunning && (
            <p className="text-[11px] text-text-tertiary mt-3 pt-3 border-t border-border-subtle">
              {runnerScope(opt.runner) === 'python'
                ? 'Replaying all combinations locally across CPU cores. Results appear here when the full grid completes.'
                : runnerScope(opt.runner) === 'mt5'
                ? 'MT5 Strategy Tester is running all combinations. Results appear here when the full grid completes.'
                : 'NT8 is running all combinations in one job using its native optimizer. Results appear here when the full grid completes.'}
            </p>
          )}
        </div>

        {/* Right: timing + actions */}
        <div className="flex-shrink-0 flex flex-col items-end gap-3">
          <div className="text-right">
            <div className="text-[11px] text-text-tertiary mb-0.5">
              {isComplete ? 'Duration' : isRunning ? 'Elapsed' : 'Ran for'}
            </div>
            <div className="text-[20px] font-mono font-semibold text-text-primary tabular-nums leading-none">
              {elapsed == null ? <span className="text-text-tertiary">—</span> : fmtDuration(elapsed)}
            </div>
          </div>

          <div className="flex flex-col gap-2 items-end">
            {isRunning && (
              <button
                onClick={onCancel}
                disabled={cancelling}
                className="flex items-center gap-[6px] px-3 py-[6px] rounded-md text-[12px] font-medium border border-neg-text/30 text-neg-text hover:bg-neg-muted disabled:opacity-50 transition-colors"
              >
                <Square size={11} />
                {cancelling ? 'Cancelling…' : 'Cancel'}
              </button>
            )}
            {hasFailures && !isRunning && (
              <button
                onClick={onRetry}
                disabled={retrying || jobBlocked}
                title={jobBlocked ? 'Another NT8 job is running — wait for it to finish' : undefined}
                className="flex items-center gap-[6px] px-3 py-[6px] rounded-md text-[12px] font-medium border border-accent/30 text-accent hover:bg-accent/10 disabled:opacity-50 transition-colors"
              >
                <RotateCcw size={11} className={retrying ? 'animate-spin' : ''} />
                {retrying ? 'Starting…' : `Retry ${failedCount} failed`}
              </button>
            )}
            {/* No Retry button while running. `retry-failed` calls ensure_platform_idle, and
                this optimization IS the job holding that platform, so the request could only
                ever come back 409 — a button whose single outcome is an error toast. Cancel
                first, then retry; that path is one line above. */}
          </div>
        </div>
      </div>
    </div>
  )
}

// ── Failed runs table ─────────────────────────────────────────────────────────

function FailedRunsTable({ runs, sweptKeys, navigate, retryRun, jobBlocked }: {
  runs: BacktestSummary[]
  sweptKeys: string[]
  navigate: ReturnType<typeof useNavigate>
  retryRun: ReturnType<typeof useRetryBacktest>
  jobBlocked: boolean
}) {
  if (runs.length === 0) return null
  return (
    <div>
      <h2 className="text-[11px] font-semibold text-neg-text uppercase tracking-[0.7px] mb-3">
        Failed runs ({runs.length})
      </h2>
      <div className="bg-bg-surface border border-border-subtle rounded-xl overflow-hidden overflow-x-auto">
        <table className="w-full text-[12px]">
          <thead>
            <tr className="border-b border-border-subtle bg-bg-sunken">
              {sweptKeys.map(k => (
                <th key={k} className="text-left px-3 py-2 text-text-tertiary font-medium font-mono">{k}</th>
              ))}
              <th className="text-left px-3 py-2 text-text-tertiary font-medium">Status</th>
              <th className="text-left px-3 py-2 text-text-tertiary font-medium">Error</th>
              <th className="px-3 py-2 w-24" />
            </tr>
          </thead>
          <tbody className="divide-y divide-border-subtle">
            {runs.map(run => (
              <tr
                key={run.run_id}
                onClick={() => navigate(`/backtests/runs/${run.run_id}`)}
                className="hover:bg-bg-hover cursor-pointer transition-colors"
              >
                {sweptKeys.map(k => (
                  <td key={k} className="px-3 py-[9px] font-mono font-semibold text-text-primary">
                    {String(run.params?.[k] ?? '—')}
                  </td>
                ))}
                <td className="px-3 py-[9px] font-mono text-neg-text text-[11px]">
                  {run.status}
                </td>
                <td className="px-3 py-[9px] text-text-tertiary text-[11px] max-w-[320px] truncate">
                  {run.error_message ?? '—'}
                </td>
                <td className="px-3 py-[9px]">
                  <div className="flex items-center justify-end gap-2">
                    <button
                      onClick={(e) => { e.stopPropagation(); retryRun.mutate(run.run_id) }}
                      disabled={retryRun.isPending || jobBlocked}
                      title={jobBlocked ? 'Another NT8 job is running — wait for it to finish' : 'Retry this run'}
                      className="p-[4px] rounded text-text-tertiary hover:text-accent hover:bg-accent/10 disabled:opacity-40 transition-colors"
                    >
                      <RotateCcw size={11} className={retryRun.isPending && retryRun.variables === run.run_id ? 'animate-spin' : ''} />
                    </button>
                    <span className="text-[11px] text-accent">View →</span>
                  </div>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  )
}

// ── Results table ─────────────────────────────────────────────────────────────

function fmtMoney(val: number | null | undefined): string {
  if (val == null) return '—'
  const sign = val >= 0 ? '+' : '-'
  return `${sign}$${Math.round(Math.abs(val)).toLocaleString('en-US')}`
}

type SortKey = 'profit_factor' | 'net_pnl' | 'max_drawdown' | 'trade_count' | 'sharpe'

// Max drawdown is the one column where SMALLER is better, so its default direction is the
// opposite of every other column's. Sorting it descending like the rest would put the worst
// combination at the top under a header the reader has just clicked to find the best.
const SORT_ASC_DEFAULT: Record<SortKey, boolean> = {
  profit_factor: false, net_pnl: false, max_drawdown: true, trade_count: false, sharpe: false,
}

function SortHeader({ label, col, sort, setSort, title }: {
  label: string
  col: SortKey
  sort: { key: SortKey; asc: boolean }
  setSort: (s: { key: SortKey; asc: boolean }) => void
  title?: string
}) {
  const active = sort.key === col
  return (
    <th
      title={title}
      onClick={() => setSort(active ? { key: col, asc: !sort.asc } : { key: col, asc: SORT_ASC_DEFAULT[col] })}
      className={`text-left px-3 py-2 font-medium cursor-pointer select-none whitespace-nowrap hover:text-text-secondary transition-colors ${active ? 'text-accent' : 'text-text-tertiary'}`}
    >
      {label}
      <span className="ml-1 text-[9px]">{active ? (sort.asc ? '▲' : '▼') : '↕'}</span>
    </th>
  )
}

function ResultsTable({ runs, sweptKeys, navigate, bestRunId, minTrades, sort, setSort }: {
  runs: BacktestSummary[]
  sweptKeys: string[]
  navigate: ReturnType<typeof useNavigate>
  bestRunId?: string
  minTrades: number
  sort: { key: SortKey; asc: boolean }
  setSort: (s: { key: SortKey; asc: boolean }) => void
}) {
  // Memoised: a 1,000-row grid was re-sorted on every render, and the page re-renders every
  // 3 seconds while the job runs.
  const sorted = useMemo(() => {
    const dir = sort.asc ? 1 : -1
    const miss = sort.asc ? Infinity : -Infinity   // nulls sort last whichever way you're going
    return [...runs].sort((a, b) =>
      ((a[sort.key] ?? miss) - (b[sort.key] ?? miss)) * dir)
  }, [runs, sort])

  return (
    <div className="bg-bg-surface border border-border-subtle rounded-xl overflow-hidden overflow-x-auto">
      <table className="w-full text-[12px]">
        <thead>
          <tr className="border-b border-border-subtle bg-bg-sunken">
            <th className="px-3 py-2 w-6" />
            {sweptKeys.map(k => (
              <th key={k} className="text-left px-3 py-2 text-text-tertiary font-medium font-mono">{k}</th>
            ))}
            <SortHeader label="P&L"     col="net_pnl"       sort={sort} setSort={setSort} />
            <SortHeader label="Max DD"  col="max_drawdown"  sort={sort} setSort={setSort} />
            <SortHeader label="Trades"  col="trade_count"   sort={sort} setSort={setSort} />
            <SortHeader label="Sharpe"  col="sharpe"        sort={sort} setSort={setSort} />
            <SortHeader label="Profit factor" col="profit_factor" sort={sort} setSort={setSort}
              title="The optimizer's score for raw mode — gross wins ÷ gross losses" />
            <th className="px-3 py-2 w-16" />
          </tr>
        </thead>
        <tbody className="divide-y divide-border-subtle">
          {sorted.map(run => {
            // ★ is the winner the BACKEND chose, never "whatever is on row 1". Falling back to
            // row 1 made the star follow the sort, so re-sorting by trades appeared to crown a
            // different combination.
            const isBest = run.run_id === bestRunId
            const belowFloor = minTrades > 0 && (run.trade_count ?? 0) < minTrades
            const pnlCls = (run.net_pnl ?? 0) >= 0 ? 'text-pos-text' : 'text-neg-text'
            return (
              <tr
                key={run.run_id}
                onClick={() => navigate(`/backtests/runs/${run.run_id}`)}
                className={`hover:bg-bg-hover cursor-pointer transition-colors ${isBest ? 'border-l-2 border-l-gold-text bg-gold-muted/10' : ''} ${belowFloor ? 'opacity-45' : ''}`}
                title={belowFloor ? `Under the ${minTrades}-trade minimum — not eligible to win` : undefined}
              >
                <td className="px-3 py-[9px] w-6">
                  {isBest && <span className="text-gold-text font-bold">★</span>}
                </td>
                {sweptKeys.map(k => (
                  <td key={k} className={`px-3 py-[9px] text-left font-mono font-semibold ${isBest ? 'text-gold-text' : 'text-text-primary'}`}>
                    {String(run.params?.[k] ?? '—')}
                  </td>
                ))}
                <td className={`px-3 py-[9px] text-left font-mono tabular-nums ${pnlCls}`}>
                  {fmtMoney(run.net_pnl)}
                </td>
                <td className="px-3 py-[9px] text-left font-mono tabular-nums text-neg-text">
                  {run.max_drawdown != null ? `$${Math.round(run.max_drawdown).toLocaleString('en-US')}` : '—'}
                </td>
                <td className="px-3 py-[9px] text-left tabular-nums text-text-secondary">
                  {run.trade_count ?? '—'}
                </td>
                <td className="px-3 py-[9px] text-left font-mono tabular-nums text-text-secondary">
                  {run.sharpe?.toFixed(2) ?? '—'}
                </td>
                <td className={`px-3 py-[9px] text-left font-mono tabular-nums font-semibold ${isBest ? 'text-gold-text' : 'text-text-primary'}`}>
                  {run.profit_factor?.toFixed(2) ?? '—'}
                </td>
                <td className="px-3 py-[9px] text-left">
                  <span className="text-[11px] text-accent whitespace-nowrap">View →</span>
                </td>
              </tr>
            )
          })}
        </tbody>
      </table>
    </div>
  )
}

// ── Ranked bar chart ──────────────────────────────────────────────────────────

function RankedBars({ runs, sweptKeys, navigate, bestRunId }: {
  runs: BacktestSummary[]
  sweptKeys: string[]
  navigate: ReturnType<typeof useNavigate>
  bestRunId?: string
}) {
  const sorted = useMemo(
    () => [...runs].sort((a, b) => (b.profit_factor ?? -Infinity) - (a.profit_factor ?? -Infinity)),
    [runs],
  )
  const maxPf = Math.max(...sorted.map(r => r.profit_factor ?? 0), 1)

  function tierColor(run: BacktestSummary): string {
    const tier = run.worthiness?.tier
    if (tier === 'TIER_1_STRESS_TEST') return '#22c55e'
    if (tier === 'TIER_2_OPTIMIZE')    return '#06b6d4'
    return '#ef4444'
  }

  const BAR_H    = 34
  const LABEL_W  = 160
  const PF_W     = 44
  const BAR_AREA = 320
  const PAD_Y    = 4

  const svgH = sorted.length * (BAR_H + PAD_Y) + PAD_Y
  const svgW = LABEL_W + BAR_AREA + PF_W + 8

  return (
    <div className="bg-bg-surface border border-border-subtle rounded-xl p-5 overflow-x-auto">
      <svg width={svgW} height={svgH} className="font-mono">
        {sorted.map((run, i) => {
          const pf    = run.profit_factor ?? 0
          const isBest = run.run_id === bestRunId
          const barW  = Math.max(4, (pf / maxPf) * BAR_AREA)
          const cy    = PAD_Y + i * (BAR_H + PAD_Y)
          const label = sweptKeys.map(k => run.params?.[k] ?? '?').join(' / ')
          const color = tierColor(run)

          return (
            <g
              key={run.run_id}
              className="cursor-pointer"
              onClick={() => navigate(`/backtests/runs/${run.run_id}`)}
            >
              {/* Hover bg */}
              <rect x={0} y={cy} width={svgW} height={BAR_H} fill="transparent"
                className="hover:fill-white/[0.03]" rx={4} />

              {/* Label */}
              <text
                x={LABEL_W - 8}
                y={cy + BAR_H / 2 + 4}
                textAnchor="end"
                fontSize={11}
                fill={isBest ? '#f59e0b' : '#9ca3af'}
                fontWeight={isBest ? '600' : '400'}
              >
                {isBest ? '★ ' : ''}{label}
              </text>

              {/* Bar track */}
              <rect x={LABEL_W} y={cy + 9} width={BAR_AREA} height={16} rx={3} fill="#1f2937" />

              {/* Bar fill */}
              <rect
                x={LABEL_W} y={cy + 9}
                width={barW} height={16}
                rx={3}
                fill={color}
                fillOpacity={isBest ? 0.9 : 0.55}
              />

              {/* Gold border for winner */}
              {isBest && (
                <rect x={LABEL_W} y={cy + 9} width={barW} height={16} rx={3}
                  fill="none" stroke="#f59e0b" strokeWidth={1.5} />
              )}

              {/* PF value */}
              <text
                x={LABEL_W + BAR_AREA + 8}
                y={cy + BAR_H / 2 + 4}
                textAnchor="start"
                fontSize={11}
                fill={isBest ? '#f59e0b' : '#e5e7eb'}
                fontWeight={isBest ? '700' : '400'}
              >
                {pf.toFixed(2)}
              </text>
            </g>
          )
        })}
      </svg>
      <p className="text-[11px] text-text-tertiary mt-2">
        Sorted by profit factor. Bar color: <span className="text-pos-text">green</span> = Tier 1, <span className="text-accent">cyan</span> = Tier 2, <span className="text-neg-text">red</span> = Tier 3.
      </p>
    </div>
  )
}

// ── Robustness (grid sensitivity) ─────────────────────────────────────────────

// How isolated the winner is in the grid. The backend has computed and STORED this on every
// native optimization since the grid-sensitivity pass landed, and nothing displayed it — which
// made it the one number a parameter sweep exists to produce and the one number the page did
// not show. 0 = the neighbours score the same (a plateau you can actually trade). 1 = the
// neighbours collapse (a lone spike, i.e. the winner is a property of this history).
function RobustnessCard({ score, summary }: {
  score: number
  summary: Record<string, Partial<Record<'up' | 'down', { value: number; profit_factor: number; degradation: number }>>> | null
}) {
  const pct = Math.round(score * 100)
  const tone = score >= 0.5 ? { text: 'text-neg-text',  bg: 'bg-neg-muted',  border: 'border-neg-text/20' }
    : score >= 0.25       ? { text: 'text-warn-text', bg: 'bg-warn-muted/40', border: 'border-warn-text/20' }
    : { text: 'text-pos-text', bg: 'bg-pos-muted', border: 'border-pos-text/20' }
  const verdict = score >= 0.5
    ? 'Fragile — one step either side of the winner and the result largely disappears. That is the shape of a number fitted to this history.'
    : score >= 0.25
    ? 'Mixed — the winner sits on a slope. Nearby settings are worse but not worthless.'
    : 'Robust — the settings either side score about the same, so the winner is a plateau rather than a spike.'

  return (
    <div className={`rounded-xl border px-5 py-4 ${tone.bg} ${tone.border}`}>
      <div className="flex items-baseline gap-3 mb-1">
        <span className="text-[11px] font-semibold uppercase tracking-[0.7px] text-text-secondary">
          Winner robustness
        </span>
        <span className={`text-[18px] font-mono font-semibold tabular-nums ${tone.text}`}>{pct}%</span>
        <span className="text-[11px] text-text-tertiary">worst neighbour drop</span>
      </div>
      <p className="text-[12px] text-text-secondary leading-snug">{verdict}</p>
      {summary && Object.keys(summary).length > 0 && (
        <div className="mt-3 pt-3 border-t border-border-subtle/60 flex flex-wrap gap-x-5 gap-y-1.5">
          {Object.entries(summary).map(([param, sides]) => (
            <span key={param} className="text-[11px] font-mono text-text-tertiary">
              <span className="text-text-secondary">{param}</span>
              {(['down', 'up'] as const).map(d => sides[d] && (
                <span key={d} className="ml-2">
                  {d === 'down' ? '↓' : '↑'}{sides[d]!.value} → PF {sides[d]!.profit_factor.toFixed(2)}
                  <span className={sides[d]!.degradation >= 0.5 ? 'text-neg-text' : 'text-text-tertiary'}>
                    {' '}(−{Math.round(sides[d]!.degradation * 100)}%)
                  </span>
                </span>
              ))}
            </span>
          ))}
        </div>
      )}
    </div>
  )
}

// ── Baseline comparison ───────────────────────────────────────────────────────

// The run this optimization was launched FROM. Without it the grid is a ranking with no
// reference point — you can see which combination won and not whether it beat the settings you
// already had, which is the only question that decides whether to adopt it.
// Structural, not `BacktestSummary` — the baseline arrives as a BacktestDetail and the winner
// as a summary, and this only ever reads the four KPIs both carry.
type BaselineKpis = Pick<BacktestSummary, 'profit_factor' | 'net_pnl' | 'max_drawdown' | 'trade_count'>

function BaselineRow({ baseline, winner }: { baseline: BaselineKpis; winner?: BaselineKpis }) {
  const delta = (a: number | null | undefined, b: number | null | undefined) =>
    a == null || b == null ? null : a - b
  const pfDelta   = delta(winner?.profit_factor, baseline.profit_factor)
  const pnlDelta  = delta(winner?.net_pnl, baseline.net_pnl)
  const beat      = pfDelta != null && pfDelta > 0

  const Cell = ({ label, base, win, fmt }: {
    label: string; base: number | null | undefined; win: number | null | undefined
    fmt: (v: number | null | undefined) => string
  }) => (
    <div>
      <div className="text-[10px] uppercase tracking-wide text-text-tertiary mb-0.5">{label}</div>
      <div className="text-[13px] font-mono tabular-nums">
        <span className="text-text-tertiary">{fmt(base)}</span>
        <span className="text-text-tertiary mx-1.5">→</span>
        <span className="text-text-primary font-semibold">{fmt(win)}</span>
      </div>
    </div>
  )

  return (
    <div className="rounded-xl border border-border-subtle bg-bg-surface px-5 py-4">
      <div className="flex items-center gap-2 mb-3">
        <span className="text-[11px] font-semibold uppercase tracking-[0.7px] text-text-secondary">
          Starting run → winner
        </span>
        {winner && (
          <span className={`inline-flex px-2 py-[2px] rounded text-[10px] font-semibold ${beat ? 'bg-pos-muted text-pos-text' : 'bg-warn-muted/50 text-warn-text'}`}>
            {beat ? 'BEAT THE BASELINE' : 'DID NOT BEAT THE BASELINE'}
          </span>
        )}
      </div>
      <div className="flex flex-wrap gap-x-8 gap-y-3">
        <Cell label="Profit factor" base={baseline.profit_factor} win={winner?.profit_factor}
          fmt={v => v?.toFixed(2) ?? '—'} />
        <Cell label="Net P&L" base={baseline.net_pnl} win={winner?.net_pnl} fmt={fmtMoney} />
        <Cell label="Max DD" base={baseline.max_drawdown} win={winner?.max_drawdown}
          fmt={v => v == null ? '—' : `$${Math.round(v).toLocaleString('en-US')}`} />
        <Cell label="Trades" base={baseline.trade_count} win={winner?.trade_count}
          fmt={v => v == null ? '—' : String(v)} />
      </div>
      {pnlDelta != null && (
        <p className="text-[11px] text-text-tertiary mt-3">
          {beat
            ? `The winner is ${pfDelta!.toFixed(2)} profit factor better than the run you started from.`
            : 'The grid found nothing better than the settings you already had — the starting run stands.'}
        </p>
      )}
    </div>
  )
}

// ── Log section ───────────────────────────────────────────────────────────────

function OptLogSection({ optimizationId, isRunning, isComplete, isFailed }: {
  optimizationId: string
  isRunning: boolean
  isComplete: boolean
  isFailed: boolean
}) {
  const [open, setOpen] = useState(isRunning || isFailed)
  const [copied, setCopied] = useState(false)
  const { data: log, isFetching, refetch } = useOptimizationLog(open ? optimizationId : null, 300, isRunning)
  const prevLiveRef = useRef(isRunning)

  useEffect(() => {
    if (prevLiveRef.current && !isRunning) refetch()
    prevLiveRef.current = isRunning
  }, [isRunning, refetch])

  function copyLog(e: React.MouseEvent) {
    e.stopPropagation()
    if (!log) return
    navigator.clipboard.writeText(log)
    setCopied(true)
    setTimeout(() => setCopied(false), 1500)
  }

  return (
    <div className="bg-bg-sunken border border-border-subtle rounded-lg overflow-hidden">
      <button
        onClick={() => setOpen(o => !o)}
        className="w-full flex items-center justify-between px-4 py-[10px] border-b border-border-subtle hover:bg-bg-hover/40 transition-colors"
      >
        <div className="flex items-center gap-[10px]">
          {isRunning ? (
            <span className="relative flex h-[8px] w-[8px] flex-shrink-0">
              <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-accent opacity-60" />
              <span className="relative inline-flex rounded-full h-[8px] w-[8px] bg-accent" />
            </span>
          ) : isComplete ? (
            <span className="w-[8px] h-[8px] rounded-full bg-accent flex-shrink-0" />
          ) : isFailed ? (
            <span className="w-[8px] h-[8px] rounded-full bg-neg-text flex-shrink-0" />
          ) : (
            <span className="w-[8px] h-[8px] rounded-full bg-text-tertiary/30 flex-shrink-0" />
          )}
          <span className="text-small font-semibold font-mono tracking-wide uppercase text-text-secondary">
            VPS Log
          </span>
          {isRunning && <span className="text-micro text-text-tertiary font-mono">· live</span>}
          {isComplete && !isRunning && <span className="text-micro text-accent font-mono">· complete</span>}
          {isFailed && !isRunning && <span className="text-micro text-neg-text font-mono">· failed</span>}
        </div>
        <div className="flex items-center gap-2">
          {log && (
            <span
              role="button"
              onClick={copyLog}
              title="Copy log"
              className="p-1 rounded hover:bg-bg-hover text-text-tertiary hover:text-text-secondary transition-colors"
            >
              {copied ? <Check size={13} className="text-accent" /> : <Copy size={13} />}
            </span>
          )}
          {open ? <ChevronUp size={14} className="text-text-tertiary" /> : <ChevronDown size={14} className="text-text-tertiary" />}
        </div>
      </button>
      {open && (
        <div>
          {isFetching && !log ? (
            <div className="px-4 py-3 text-[12px] text-text-tertiary font-mono">Loading…</div>
          ) : log ? (
            <pre className="px-4 py-3 text-[11px] font-mono text-text-secondary leading-[1.6] overflow-x-auto whitespace-pre-wrap max-h-[400px] overflow-y-auto">
              {log}
            </pre>
          ) : (
            <div className="px-4 py-3 text-[12px] text-text-tertiary font-mono">No log output.</div>
          )}
        </div>
      )}
    </div>
  )
}


// ── Page ──────────────────────────────────────────────────────────────────────

export function OptimizationDetail() {
  const { optimizationId } = useParams<{ optimizationId: string }>()
  const navigate            = useNavigate()
  const { data: opt, isLoading } = useOptimization(optimizationId ?? null)
  const cancelOpt  = useCancelOptimization()
  const retryOpt   = useRetryOptimization()
  const rerunOpt   = useRerunOptimization()
  const deleteOpt  = useDeleteOptimization()
  const retryRun   = useRetryBacktest()
  const { data: runningJob } = useRunningVpsJob()
  const jobBlocked = !!runningJobFor(runningJob, opt?.runner)?.running

  const { data: stressLock } = useRunningStressLock()
  const stressRunIds = useMemo(() => new Set(stressLock?.run_ids ?? []), [stressLock])
  const bestRunId = opt?.best_run_id ?? undefined
  // Tuning iterations spawned from the winner run (standalone runs with source_run_id = winner).
  // Scoped to this strategy — the unfiltered call pulled EVERY run in the lab on a page that
  // needs at most a handful, and it polls.
  const { data: allRunsForTune } = useBacktestRuns(
    opt?.strategy_id ? { strategy_id: opt.strategy_id } : undefined)
  const tuneIterations = useMemo(
    () => (allRunsForTune ?? []).filter(r => bestRunId && r.source_run_id === bestRunId && !r.sweep_id && !r.optimization_id),
    [allRunsForTune, bestRunId],
  )
  // The run this optimization was launched from, for the baseline comparison.
  const { data: baselineRun } = useBacktestRun(opt?.source_run_id ?? null)
  const tuneRunning = tuneIterations.filter(r => r.status === 'running').length
  const hasRunningStress = !!bestRunId && stressRunIds.has(bestRunId)
  const { data: bestRunStressTests } = useStressTests(hasRunningStress ? bestRunId : undefined)
  const latestStress = bestRunStressTests?.find(s => !s.status.startsWith('failed') && s.status !== 'complete')

  const [confirmDelete, setConfirmDelete] = useState(false)
  const [viewMode, setViewMode]           = useState<'table' | 'bars'>('table')
  const [sort, setSort] = useState<{ key: SortKey; asc: boolean }>({ key: 'profit_factor', asc: false })
  // Hide combos under the optimization's own trade floor. Off by default so the grid is never
  // silently narrower than it says it is — the ineligible rows are dimmed either way.
  const [hideBelowFloor, setHideBelowFloor] = useState(false)

  const paramKeys = useMemo(() => (opt ? Object.keys(opt.param_grid) : []), [opt])
  const sweptKeys = useMemo(() => paramKeys.filter(k => {
    const spec = opt?.param_grid[k]
    return Array.isArray(spec) ? spec.length > 1 : typeof spec === 'object' && spec !== null
  }), [paramKeys, opt])

  const isRunning    = opt?.status === 'running'
  const minTrades    = opt?.min_trades ?? 0
  const completeRuns = useMemo(
    () => opt?.runs.filter(r => r.status === 'complete') ?? [], [opt])
  const failedRuns   = useMemo(
    () => opt?.runs.filter(r => r.status.startsWith('failed')) ?? [], [opt])
  const visibleRuns  = useMemo(
    () => (hideBelowFloor && minTrades > 0
      ? completeRuns.filter(r => (r.trade_count ?? 0) >= minTrades)
      : completeRuns),
    [completeRuns, hideBelowFloor, minTrades])
  const belowFloorCount = completeRuns.length - (minTrades > 0
    ? completeRuns.filter(r => (r.trade_count ?? 0) >= minTrades).length
    : completeRuns.length)
  const winnerRun = completeRuns.find(r => r.run_id === bestRunId)

  return (
    <div>
      <StickyHeader>
        {scrolled => (
          <div className={`flex items-center justify-between gap-3 ${scrolled ? 'mb-4' : 'mb-5'}`}>
            <div className="flex items-center gap-2.5 min-w-0">
              <button
                onClick={() => navigate('/optimizations')}
                className="flex items-center gap-2 text-[13px] text-text-tertiary hover:text-text-secondary transition-colors flex-shrink-0"
              >
                <ArrowLeft size={14} /> {!scrolled && 'Optimizations'}
              </button>
              {scrolled && opt && (
                <>
                  <span className="text-text-tertiary flex-shrink-0">·</span>
                  <h1 className="text-[14px] font-semibold truncate">{opt.strategy_name || opt.strategy_id}</h1>
                  <span className="inline-flex items-center px-1.5 py-[1px] rounded text-[11px] font-semibold font-mono bg-accent/10 text-accent border border-accent/20 flex-shrink-0">
                    {opt.instrument}
                  </span>
                </>
              )}
            </div>
            {opt && !isRunning && (
              <div className="flex items-center gap-2 flex-shrink-0">
            {opt.status.startsWith('failed') && (
              <button
                onClick={() => rerunOpt.mutate(optimizationId!)}
                disabled={rerunOpt.isPending}
                className="flex items-center gap-[6px] px-3 py-[6px] rounded-md text-[12px] font-medium text-accent hover:bg-accent/10 border border-accent/30 hover:border-accent/50 disabled:opacity-50 transition-colors"
              >
                <RotateCcw size={12} />
                {rerunOpt.isPending ? 'Starting…' : 'Re-run'}
              </button>
            )}
            <button
              onClick={() => setConfirmDelete(true)}
              className="flex items-center gap-[6px] px-3 py-[6px] rounded-md text-[12px] font-medium text-text-tertiary hover:text-neg-text hover:bg-neg-muted border border-transparent hover:border-neg-text/20 transition-colors"
            >
              <Trash2 size={12} />
              Delete
            </button>
              </div>
            )}
          </div>
        )}
      </StickyHeader>

      {confirmDelete && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 px-4" onClick={e => { if (e.target === e.currentTarget) setConfirmDelete(false) }}>
          <div className="bg-bg-surface border border-border-default rounded-xl w-full max-w-[400px] shadow-2xl">
            <div className="px-5 py-4 border-b border-border-subtle">
              <div className="text-[15px] font-semibold">Delete this optimization?</div>
            </div>
            <div className="px-5 py-4">
              <p className="text-[13px] text-text-secondary">
                All {opt?.estimated_runs} child runs, their evaluations, and result files will be permanently removed. This cannot be undone.
              </p>
            </div>
            <div className="flex items-center justify-end gap-3 px-5 py-4 border-t border-border-subtle">
              <button onClick={() => setConfirmDelete(false)} className="px-4 py-[7px] rounded-md text-[13px] text-text-secondary hover:text-text-primary hover:bg-bg-hover transition-colors">
                Cancel
              </button>
              <button
                onClick={() => deleteOpt.mutate(optimizationId!, { onSuccess: () => navigate('/optimizations') })}
                disabled={deleteOpt.isPending}
                className="px-4 py-[7px] rounded-md text-[13px] font-medium bg-neg-muted text-neg-text border border-neg/40 hover:bg-neg/15 disabled:opacity-50 transition-colors"
              >
                {deleteOpt.isPending ? 'Deleting…' : 'Delete optimization'}
              </button>
            </div>
          </div>
        </div>
      )}

      {isLoading && (
        <div className="animate-pulse space-y-4">
          <div className="h-7 w-72 bg-bg-surface rounded" />
          <div className="h-4 w-48 bg-bg-surface rounded" />
          <div className="h-[120px] bg-bg-surface rounded-xl" />
        </div>
      )}

      {opt && (
        <div className="space-y-6">
          {/* Header */}
          <div>
            <h1 className="text-h1 font-semibold leading-tight mb-2">
              {opt.strategy_name || opt.strategy_id}
            </h1>
            <div className="flex flex-wrap gap-1.5">
              <span className="inline-flex items-center px-2 py-[3px] rounded text-[11px] font-semibold font-mono bg-accent/10 text-accent border border-accent/20">
                {opt.instrument}
              </span>
              <span className="inline-flex items-center px-2 py-[3px] rounded text-[11px] font-medium bg-bg-surface border border-border-subtle text-text-secondary font-mono">
                {fmtDate(opt.start_date)} → {fmtDate(opt.end_date)}
              </span>
              {opt.ruleset_id ? (
                <span className={`inline-flex items-center px-2 py-[3px] rounded text-[11px] font-semibold font-mono ${firmChipCls(opt.ruleset_id)}`}>
                  {firmShortName(opt.ruleset_id)}
                </span>
              ) : (
                <span className="inline-flex items-center px-2 py-[3px] rounded text-[11px] font-medium font-mono bg-bg-surface border border-border-subtle text-text-tertiary">
                  No ruleset
                </span>
              )}
              {opt.regime_filter && (
                <span className="inline-flex items-center px-2 py-[3px] rounded text-[11px] font-medium font-mono bg-bg-surface border border-border-subtle text-text-tertiary">
                  Regime: {opt.regime_filter.replace('_', ' ').toLowerCase().replace(/\b\w/g, c => c.toUpperCase())}
                </span>
              )}
              {/* What the grid was CHARGED. A ranking produced on a free book is not comparable
                  to a priced run, and until this chip existed nothing on the page said which
                  one you were looking at. `null` (pre-layers) and `[]` (charged nothing on
                  purpose) are different answers and are worded differently. */}
              <span
                className="inline-flex items-center px-2 py-[3px] rounded text-[11px] font-medium font-mono bg-bg-surface border border-border-subtle text-text-tertiary"
                title={opt.cost_layers?.length
                  ? `Charged on the ${opt.broker_profile} profile`
                  : 'Every combination was replayed with no spread, swap or commission'}
              >
                {opt.cost_layers === null ? 'Costs: not recorded'
                  : opt.cost_layers.length ? `Costs: ${opt.cost_layers.join(', ')}`
                  : 'Costs: none charged'}
              </span>
              {minTrades > 0 && (
                <span className="inline-flex items-center px-2 py-[3px] rounded text-[11px] font-medium font-mono bg-bg-surface border border-border-subtle text-text-tertiary">
                  Min {minTrades} trades to win
                </span>
              )}
            </div>
          </div>

          {/* The winner was picked by a fallback, not by the rule the chips above name. */}
          {opt.winner_note && (
            <div className="flex items-start gap-2 px-4 py-3 rounded-lg bg-warn-muted/30 border border-warn-text/20">
              <AlertTriangle size={14} className="text-warn-text flex-shrink-0 mt-[1px]" />
              <p className="text-[12px] text-warn-text leading-snug">{opt.winner_note}</p>
            </div>
          )}

          {/* Progress */}
          <ProgressCard
            opt={opt}
            onCancel={() => cancelOpt.mutate(optimizationId!)}
            onRetry={() => retryOpt.mutate(optimizationId!)}
            cancelling={cancelOpt.isPending}
            retrying={retryOpt.isPending}
            jobBlocked={jobBlocked}
          />

          {latestStress && (
            <button
              onClick={() => navigate(`/stress-tests/${latestStress.stress_test_id}`)}
              className="w-full flex items-center justify-between gap-3 px-4 py-2.5 rounded-lg border border-accent/20 bg-accent/5 text-left hover:bg-accent/10 transition-colors"
            >
              <div className="flex items-center gap-2 text-sm text-accent">
                <Activity size={14} className="animate-pulse flex-shrink-0" />
                Stress test in progress on winner run
              </div>
              <span className="text-xs text-text-tertiary">View →</span>
            </button>
          )}


          {/* Robustness + baseline — the two things that decide whether to ADOPT the winner */}
          {!isRunning && opt.grid_sensitivity_score != null && completeRuns.length > 1 && (
            <RobustnessCard
              score={opt.grid_sensitivity_score}
              summary={opt.grid_sensitivity_summary}
            />
          )}
          {!isRunning && baselineRun && completeRuns.length > 0 && (
            <BaselineRow baseline={baselineRun} winner={winnerRun} />
          )}

          {/* Results */}
          {completeRuns.length > 0 && (
            <div>
              <div className="flex items-center justify-between mb-3">
                <div className="flex items-center gap-2">
                  <h2 className="text-[11px] font-semibold text-text-secondary uppercase tracking-[0.7px]">
                    {isRunning
                      ? `Results so far — ${completeRuns.length} of ${opt.estimated_runs} complete`
                      : `Results — ${completeRuns.length} of ${opt.estimated_runs} combinations`}
                  </h2>
                  {tuneRunning > 0 && (
                    <span title="A tuning iteration is running on the winner (★)"
                      className="inline-flex items-center gap-[3px] px-[5px] py-[2px] rounded text-[10px] font-semibold bg-accent/10 text-accent">
                      <SlidersHorizontal size={9} className="animate-pulse" />
                      TUNING WINNER
                    </span>
                  )}
                </div>
                <div className="flex items-center gap-2">
                  {belowFloorCount > 0 && (
                    <label className="flex items-center gap-1.5 text-[11px] text-text-tertiary cursor-pointer select-none">
                      <input
                        type="checkbox"
                        checked={hideBelowFloor}
                        onChange={e => setHideBelowFloor(e.target.checked)}
                        className="w-3 h-3 rounded accent-accent cursor-pointer"
                      />
                      Hide {belowFloorCount} under {minTrades} trades
                    </label>
                  )}
                  {/* View toggle */}
                  <div className="flex rounded-md border border-border-subtle overflow-hidden text-[11px]">
                    {(['table', 'bars'] as const).map(v => (
                      <button
                        key={v}
                        onClick={() => setViewMode(v)}
                        className={`px-3 py-[5px] transition-colors ${
                          viewMode === v
                            ? 'bg-accent/10 text-accent border-r border-border-subtle last:border-r-0'
                            : 'text-text-tertiary hover:text-text-secondary bg-bg-surface border-r border-border-subtle last:border-r-0'
                        }`}
                      >
                        {v === 'table' ? 'Table' : 'Bar Chart'}
                      </button>
                    ))}
                  </div>
                  {opt.best_run_id && (
                    <button
                      onClick={() => navigate(`/backtests/runs/${opt.best_run_id}/tune`)}
                      className="flex items-center gap-2 px-3 py-[5px] rounded-md text-[11px] font-medium bg-accent/10 text-accent border border-accent/20 hover:bg-accent/15 transition-colors"
                      title={tuneRunning > 0 ? 'A tuning iteration is running — open the workbench to watch' : 'Take the winning parameter set into the tuning workbench'}
                    >
                      {tuneRunning > 0
                        ? <Loader2 size={12} className="animate-spin" />
                        : <SlidersHorizontal size={12} />}
                      {tuneRunning > 0 ? 'Tuning…' : 'Tune winner'}
                    </button>
                  )}
                  <button
                    onClick={() => exportCsv(opt.runs, paramKeys, opt.optimization_id)}
                    className="flex items-center gap-2 px-3 py-[5px] rounded-md text-[11px] text-text-secondary hover:text-text-primary bg-bg-surface border border-border-subtle hover:border-border-default transition-colors"
                  >
                    <Download size={12} />
                    Export CSV
                  </button>
                </div>
              </div>

              {viewMode === 'table' && (
                <ResultsTable
                  runs={visibleRuns}
                  sweptKeys={sweptKeys}
                  navigate={navigate}
                  bestRunId={opt.best_run_id ?? undefined}
                  minTrades={minTrades}
                  sort={sort}
                  setSort={setSort}
                />
              )}
              {viewMode === 'bars' && (
                <RankedBars
                  runs={visibleRuns}
                  sweptKeys={sweptKeys}
                  navigate={navigate}
                  bestRunId={opt.best_run_id ?? undefined}
                />
              )}
            </div>
          )}

          {/* Failed runs — debugging info, always below results */}
          <FailedRunsTable runs={failedRuns} sweptKeys={sweptKeys} navigate={navigate} retryRun={retryRun} jobBlocked={jobBlocked} />

          {/* VPS log — collapsible, preserved after completion */}
          {optimizationId && (
            <OptLogSection
              optimizationId={optimizationId}
              isRunning={isRunning}
              isComplete={opt.status === 'complete'}
              isFailed={opt.status.startsWith('failed')}
            />
          )}
        </div>
      )}
    </div>
  )
}
