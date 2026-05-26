import { useState } from 'react'
import { FileText, Play, RotateCcw, AlertOctagon } from 'lucide-react'
import { useBotSnapshot, useBotLog } from '@/hooks/useBots'
import { StatCard } from '@/components/StatCard'
import { ScaffoldBanner } from '@/components/ScaffoldBanner'
import type { BotStatus, JobStatus } from '@/types'

type AccountFilter = 'all' | 'demo' | 'live'

function formatUptime(seconds: number): string {
  if (seconds < 3600) return `${Math.floor(seconds / 60)}m`
  const h = Math.floor(seconds / 3600)
  const m = Math.floor((seconds % 3600) / 60)
  if (h >= 24) {
    const d = Math.floor(h / 24)
    return `${d}d ${h % 24}h ${m}m`
  }
  return `${h}h ${m}m`
}

function StatusDot({ status }: { status: string }) {
  const cls = status === 'RUNNING'
    ? 'bg-pos' + ' shadow-[0_0_6px_#34d399]'
    : status === 'ERROR'
    ? 'bg-neg'
    : 'bg-neutral'
  return <span className={`inline-block w-[7px] h-[7px] rounded-full flex-shrink-0 ${cls}`} />
}

function LogModal({ botName, onClose }: { botName: string; onClose: () => void }) {
  const { data: log, isLoading, error } = useBotLog(botName)
  return (
    <div className="fixed inset-0 bg-black/60 flex items-center justify-center z-50 p-6" onClick={onClose}>
      <div className="bg-bg-surface border border-border-default rounded-lg w-full max-w-3xl max-h-[80vh] flex flex-col" onClick={e => e.stopPropagation()}>
        <div className="flex items-center justify-between px-4 py-3 border-b border-border-subtle">
          <span className="text-[13px] font-semibold">{botName} — stdout log</span>
          <button onClick={onClose} className="text-text-tertiary hover:text-text-primary text-[18px] leading-none">×</button>
        </div>
        <div className="flex-1 overflow-y-auto p-4 font-mono text-[11px] text-text-secondary bg-bg-sunken">
          {isLoading && <span className="text-text-tertiary">Loading…</span>}
          {error && <span className="text-neg-text">Failed to load log: {String(error)}</span>}
          {log && <pre className="whitespace-pre-wrap break-all">{log}</pre>}
        </div>
      </div>
    </div>
  )
}

export function Bots() {
  const { data: snapshot, isLoading, error, dataUpdatedAt } = useBotSnapshot()
  const [filter, setFilter] = useState<AccountFilter>('all')
  const [logBot, setLogBot] = useState<string | null>(null)

  const bots = (snapshot?.bots ?? []).filter(
    b => filter === 'all' || b.account_type === filter
  )

  const running = snapshot?.bots.filter(b => b.status === 'RUNNING').length ?? 0
  const total = snapshot?.bots.length ?? 0
  const totalBalance = snapshot?.bots.reduce((s, b) => s + (b.balance ?? 0), 0) ?? 0
  const allJobsOk = snapshot?.scheduled_jobs.every(j => j.status === 'RUNNING') ?? false

  const lastRefresh = dataUpdatedAt
    ? new Date(dataUpdatedAt).toLocaleTimeString()
    : '—'

  return (
    <div>
      <div className="flex items-end gap-3 mb-[18px]">
        <h1 className="text-h1 font-semibold">Bots</h1>
        <span className="text-[12px] text-text-tertiary pb-[2px]">
          auto-refresh 60s · last {lastRefresh}
        </span>
      </div>

      <ScaffoldBanner message="Monitoring is live and read from bot_state.json. Control actions (start / stop / restart / emergency) are disabled in this build until monitoring is proven against algo.py." />

      {isLoading && (
        <div className="text-text-tertiary text-small py-12 text-center">Fetching VPS snapshot…</div>
      )}
      {error && (
        <div className="text-neg-text text-small py-4 bg-neg-muted border border-neg-muted rounded-md px-4 mb-4">
          VPS fetch failed: {String(error)}
        </div>
      )}

      {snapshot && (
        <>
          {/* Stat cards */}
          <div className="grid grid-cols-4 gap-[10px] mb-4">
            <StatCard label="Bots running" value={`${running} / ${total}`} sub={`${total - running} stopped`} />
            <StatCard label="Total balance" value={`$${totalBalance.toLocaleString(undefined, { maximumFractionDigits: 0 })}`} />
            <StatCard
              label="Scheduled jobs"
              value={snapshot.scheduled_jobs.length.toString()}
              sub={allJobsOk ? 'all healthy' : 'check status'}
              subVariant={allJobsOk ? 'pos' : 'neg'}
            />
            <StatCard
              label="Telegram"
              value={snapshot.telegram.status}
              subVariant={snapshot.telegram.status === 'RUNNING' ? 'pos' : 'neg'}
            />
          </div>

          {/* Filter */}
          <div className="flex items-center gap-2 mb-3">
            <div className="flex bg-bg-surface border border-border-subtle rounded-md overflow-hidden">
              {(['all', 'demo', 'live'] as AccountFilter[]).map(f => (
                <span
                  key={f}
                  onClick={() => setFilter(f)}
                  className={`text-micro px-3 py-[6px] cursor-pointer select-none capitalize transition-colors duration-[100ms] ${filter === f ? 'bg-accent-muted text-text-primary' : 'text-text-secondary hover:bg-bg-hover'}`}
                >
                  {f === 'all' ? 'All' : f.charAt(0).toUpperCase() + f.slice(1)}
                </span>
              ))}
            </div>
            <span className="ml-auto text-micro text-text-tertiary">{total} trading bots · {snapshot.scheduled_jobs.length} jobs</span>
          </div>

          {/* Bots table */}
          <div className="bg-bg-surface border border-border-subtle rounded-lg overflow-hidden mb-4">
            <table className="w-full border-collapse">
              <thead>
                <tr>
                  {['Bot', 'Account', 'Balance', 'Status', 'Uptime', 'Day P&L', ''].map(h => (
                    <th key={h} className={`text-left text-[10px] font-semibold uppercase tracking-[0.7px] text-text-tertiary px-[14px] py-[10px] bg-bg-surface-2 border-b border-border-subtle whitespace-nowrap ${['Balance', 'Uptime', 'Day P&L'].includes(h) ? 'text-right' : ''}`}>
                      {h}
                    </th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {bots.map((bot: BotStatus) => (
                  <tr key={bot.name} className="border-b border-border-subtle last:border-0">
                    <td className="px-[14px] py-[11px] font-medium">{bot.name}</td>
                    <td className="px-[14px] py-[11px]">
                      <span className="font-mono text-[11px] text-text-secondary">{bot.account}</span>
                      <span className="ml-[4px] inline-flex text-[10px] font-semibold px-2 py-[3px] rounded-pill uppercase tracking-[0.4px] bg-bg-surface-2 text-text-secondary">
                        {bot.account_type}
                      </span>
                      {bot.day_locked && (
                        <span className="ml-[4px] inline-flex text-[10px] font-semibold px-2 py-[3px] rounded-pill uppercase bg-warn-muted text-warn-text">
                          locked
                        </span>
                      )}
                    </td>
                    <td className="px-[14px] py-[11px] text-right font-mono text-small">
                      {bot.balance != null ? `$${bot.balance.toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 })}` : '—'}
                    </td>
                    <td className="px-[14px] py-[11px]">
                      <div className="flex items-center gap-2">
                        <StatusDot status={bot.status} />
                        <span className="text-small">{bot.status}</span>
                      </div>
                    </td>
                    <td className="px-[14px] py-[11px] text-right font-mono text-small text-text-secondary">
                      {bot.uptime_seconds != null ? formatUptime(bot.uptime_seconds) : '—'}
                    </td>
                    <td className="px-[14px] py-[11px] text-right font-mono text-small">
                      {bot.daily_pnl_pct != null
                        ? <span className={bot.daily_pnl_pct >= 0 ? 'text-pos-text' : 'text-neg-text'}>
                            {bot.daily_pnl_pct >= 0 ? '+' : ''}{bot.daily_pnl_pct.toFixed(1)}%
                          </span>
                        : <span className="text-text-tertiary">—</span>
                      }
                    </td>
                    <td className="px-[14px] py-[11px] text-right">
                      <button
                        onClick={() => setLogBot(bot.name)}
                        className="flex items-center justify-center w-7 h-7 rounded-md border border-border-default bg-bg-surface text-text-primary hover:bg-bg-hover transition-colors"
                        title="View log"
                      >
                        <FileText size={13} />
                      </button>
                    </td>
                  </tr>
                ))}
                {bots.length === 0 && (
                  <tr><td colSpan={7} className="text-center py-12 text-text-tertiary text-small">No bots match filter.</td></tr>
                )}
              </tbody>
            </table>
          </div>

          {/* Scheduled jobs + controls */}
          <div className="grid grid-cols-2 gap-3">
            <div className="bg-bg-surface border border-border-subtle rounded-lg p-4">
              <div className="text-[13px] font-semibold mb-[14px]">Scheduled jobs</div>
              <table className="w-full text-micro">
                <tbody>
                  {snapshot.scheduled_jobs.map((j: JobStatus) => (
                    <tr key={j.name}>
                      <td className="py-[6px]">
                        <StatusDot status={j.status} />
                        <span className="ml-2">{j.name}</span>
                      </td>
                      <td className="text-right text-text-secondary py-[6px]">{j.schedule}</td>
                    </tr>
                  ))}
                  <tr>
                    <td className="py-[6px]">
                      <StatusDot status={snapshot.telegram.status} />
                      <span className="ml-2">Telegram</span>
                    </td>
                    <td className="text-right text-text-secondary py-[6px]">{snapshot.telegram.status}</td>
                  </tr>
                </tbody>
              </table>
            </div>

            <div className="bg-bg-surface border border-border-subtle rounded-lg p-4">
              <div className="flex items-center mb-[14px]">
                <span className="text-[13px] font-semibold">Control actions</span>
                <span className="text-micro text-text-tertiary ml-auto">disabled this build</span>
              </div>
              <div className="flex gap-2 flex-wrap">
                {[
                  { label: 'Start all',      icon: Play },
                  { label: 'Restart all',    icon: RotateCcw },
                  { label: 'Emergency stop', icon: AlertOctagon },
                ].map(({ label, icon: Icon }) => (
                  <button
                    key={label}
                    disabled
                    title="Control actions disabled — monitoring must be verified against algo.py first"
                    className="flex items-center gap-[6px] px-3 py-[6px] rounded-md text-small border border-border-default bg-bg-surface text-text-primary opacity-40 cursor-not-allowed"
                  >
                    <Icon size={14} />
                    {label}
                  </button>
                ))}
                <button
                  onClick={() => bots[0] && setLogBot(bots[0].name)}
                  className="flex items-center gap-[6px] px-3 py-[6px] rounded-md text-small border border-border-default bg-bg-surface text-text-primary hover:bg-bg-hover transition-colors"
                >
                  <FileText size={14} />
                  View log
                </button>
              </div>
              <div className="text-micro text-text-tertiary mt-3">
                View log is enabled — reading a log file is read-only and safe.
              </div>
            </div>
          </div>
        </>
      )}

      {logBot && <LogModal botName={logBot} onClose={() => setLogBot(null)} />}
    </div>
  )
}
