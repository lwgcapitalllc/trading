import { useState, useEffect, useRef } from 'react'
import { FileText, Play, RotateCcw, Square, RefreshCw } from 'lucide-react'
import type { LucideIcon } from 'lucide-react'
import {
  useBotSnapshot, useBotLog,
  useBotStart, useBotStop, useBotRestart,
  useBotStartOne, useBotStopOne, useBotRestartOne,
} from '@/hooks/useBots'
import { StatCard } from '@/components/StatCard'
import type { BotStatus, JobStatus } from '@/types'

type AccountFilter = 'all' | 'demo' | 'live'

// Per-bot transition: set on action trigger, cleared when snapshot confirms expected state
type PendingTransition = {
  label: string
  expectedStatus: 'RUNNING' | 'STOPPED'
  since: number
}

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

function StatusPill({ status }: { status: string }) {
  const isRunning = status === 'RUNNING'
  const isError   = status === 'ERROR'
  const cls   = isRunning ? 'bg-pos-muted text-pos-text' : 'bg-neg-muted text-neg-text'
  const label = isRunning ? 'Running' : isError ? 'Error' : 'Stopped'
  return (
    <span className={`inline-flex text-[10px] font-semibold px-2 py-[3px] rounded-pill uppercase tracking-[0.4px] ${cls}`}>
      {label}
    </span>
  )
}

// Scheduled jobs: running = green glow, waiting = gold glow, both with tooltip
function JobDot({ status }: { status: string }) {
  const title = status === 'RUNNING' ? 'Running' : 'Scheduled — waiting for next trigger'
  if (status === 'RUNNING') {
    return (
      <span
        title={title}
        className="inline-block w-[7px] h-[7px] rounded-full flex-shrink-0 bg-pos shadow-[0_0_6px_#34d399] cursor-default"
      />
    )
  }
  return (
    <span
      title={title}
      className="inline-block w-[7px] h-[7px] rounded-full flex-shrink-0 bg-gold shadow-[0_0_6px_#d9a441] cursor-default"
    />
  )
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

// Standard confirm modal for start / stop / restart
function ConfirmModal({
  label, description, confirmLabel, confirmClass,
  onConfirm, onCancel, isPending,
}: {
  label: string
  description: string
  confirmLabel: string
  confirmClass: string
  onConfirm: () => void
  onCancel: () => void
  isPending: boolean
}) {
  return (
    <div className="fixed inset-0 bg-black/60 flex items-center justify-center z-50 p-6" onClick={onCancel}>
      <div className="bg-bg-surface border border-border-default rounded-lg w-full max-w-sm p-5" onClick={e => e.stopPropagation()}>
        <p className="text-[14px] font-semibold mb-[6px]">{label}</p>
        <p className="text-[12px] text-text-tertiary mb-5">{description}</p>
        <div className="flex gap-2 justify-end">
          <button onClick={onCancel} className="px-4 py-[7px] text-small rounded-md border border-border-default bg-bg-surface text-text-secondary hover:bg-bg-hover transition-colors">
            Cancel
          </button>
          <button
            onClick={onConfirm}
            disabled={isPending}
            className={`px-4 py-[7px] text-small rounded-md font-medium transition-colors ${confirmClass} ${isPending ? 'opacity-50 cursor-not-allowed' : ''}`}
          >
            {isPending ? 'Sending…' : confirmLabel}
          </button>
        </div>
      </div>
    </div>
  )
}

// Compact icon button for per-row actions
function RowActionBtn({
  icon: Icon, title, onClick, disabled = false, variant = 'default',
}: {
  icon: LucideIcon
  title: string
  onClick: () => void
  disabled?: boolean
  variant?: 'default' | 'pos' | 'warn' | 'neg'
}) {
  const variantCls = {
    default: 'text-text-secondary hover:text-text-primary hover:bg-bg-hover hover:border-border-strong',
    pos:     'text-pos hover:text-pos-text hover:bg-pos-muted hover:border-pos/40',
    warn:    'text-warn hover:text-warn-text hover:bg-warn-muted hover:border-warn/40',
    neg:     'text-neg hover:text-neg-text hover:bg-neg-muted hover:border-neg/40',
  }[variant]

  return (
    <button
      title={title}
      onClick={onClick}
      disabled={disabled}
      className={`flex items-center justify-center w-[26px] h-[26px] rounded-md border border-border-subtle transition-colors duration-[100ms]
        ${disabled ? 'opacity-25 cursor-not-allowed' : variantCls}`}
    >
      <Icon size={12} />
    </button>
  )
}

export function Bots() {
  const { data: snapshot, isLoading, isFetching, error, dataUpdatedAt, refetch } = useBotSnapshot()
  const [filter, setFilter]         = useState<AccountFilter>('all')
  const [logBot, setLogBot]         = useState<string | null>(null)
  const [confirm, setConfirm]       = useState<'start' | 'stop' | 'restart' | null>(null)
  const [confirmStopBot, setConfirmStopBot] = useState<string | null>(null)

  // Per-bot transitions: persists after mutation resolves until snapshot confirms expected status
  const [pendingTransitions, setPendingTransitions] = useState<Record<string, PendingTransition>>({})

  // Hard-clear timers — ensure spinners always clear even when snapshot polling fails
  const transitionTimers = useRef<Record<string, ReturnType<typeof setTimeout>>>({})

  // Global control mutations
  const startMut     = useBotStart()
  const stopMut      = useBotStop()
  const restartMut   = useBotRestart()
  // Per-bot control mutations
  const startOne   = useBotStartOne()
  const stopOne    = useBotStopOne()
  const restartOne = useBotRestartOne()

  // Cancel all timers on unmount
  useEffect(() => {
    return () => { Object.values(transitionTimers.current).forEach(clearTimeout) }
  }, [])

  // ── Transition helpers ────────────────────────────────────────────────────────

  function setPendingFor(botName: string, action: 'start' | 'stop' | 'restart') {
    const map = {
      start:   { label: 'Starting…',   expectedStatus: 'RUNNING'  as const },
      stop:    { label: 'Stopping…',   expectedStatus: 'STOPPED'  as const },
      restart: { label: 'Restarting…', expectedStatus: 'RUNNING'  as const },
    }
    // Cancel any existing timer for this bot before setting a new one
    if (transitionTimers.current[botName]) clearTimeout(transitionTimers.current[botName])
    setPendingTransitions(prev => ({
      ...prev,
      [botName]: { ...map[action], since: Date.now() },
    }))
    // Hard-clear after 30 s: fires if snapshot polling fails or is too slow
    transitionTimers.current[botName] = setTimeout(() => clearPendingFor(botName), 30_000)
  }

  function clearPendingFor(botName: string) {
    if (transitionTimers.current[botName]) {
      clearTimeout(transitionTimers.current[botName])
      delete transitionTimers.current[botName]
    }
    setPendingTransitions(prev => {
      if (!prev[botName]) return prev
      const next = { ...prev }
      delete next[botName]
      return next
    })
  }

  // ── Clear transitions when snapshot confirms expected state or 45s timeout ───

  useEffect(() => {
    if (!snapshot) return
    const now = Date.now()
    setPendingTransitions(prev => {
      if (Object.keys(prev).length === 0) return prev
      const next = { ...prev }
      let changed = false
      for (const [name, t] of Object.entries(next)) {
        const bot = snapshot.bots.find(b => b.name === name)
        const timedOut = now - t.since > 45_000
        const met = bot && (
          t.expectedStatus === 'RUNNING'
            ? bot.status === 'RUNNING'
            : bot.status !== 'RUNNING'
        )
        if (timedOut || met) {
          delete next[name]
          changed = true
        }
      }
      return changed ? next : prev
    })
  }, [snapshot])

  // ── Poll every 3 s while any transition is pending ───────────────────────────

  const hasPendingTransitions = Object.keys(pendingTransitions).length > 0
  useEffect(() => {
    if (!hasPendingTransitions) return
    const id = setInterval(() => refetch(), 3_000)
    return () => clearInterval(id)
  }, [hasPendingTransitions, refetch])

  // ── Derived values ────────────────────────────────────────────────────────────

  const bots = (snapshot?.bots ?? []).filter(
    b => filter === 'all' || b.account_type === filter
  )

  const running      = snapshot?.bots.filter(b => b.status === 'RUNNING').length ?? 0
  const total        = snapshot?.bots.length ?? 0
  const totalBalance = snapshot?.bots.reduce((s, b) => s + (b.balance ?? 0), 0) ?? 0
  const allJobsOk    = snapshot?.scheduled_jobs.every(j => j.status === 'RUNNING') ?? false
  // anyRunning / noFilteredBots use the filtered list so the control panel reflects what's visible
  const filteredRunning = bots.filter(b => b.status === 'RUNNING').length
  const anyRunning     = filteredRunning > 0   // Start All requires everything stopped
  const noFilteredBots = bots.length === 0

  const anyGlobalPending    = startMut.isPending || stopMut.isPending || restartMut.isPending
  const anyPerBotPending    = startOne.isPending || stopOne.isPending || restartOne.isPending
  // anyPending includes active transitions — keeps controls locked until VPS confirms state change
  const anyPending          = anyGlobalPending || anyPerBotPending || hasPendingTransitions

  // Which bot + action is mid-flight (HTTP request not yet returned)
  const pendingBotName: string | undefined =
    startOne.isPending   ? startOne.variables :
    stopOne.isPending    ? stopOne.variables :
    restartOne.isPending ? restartOne.variables :
    undefined
  const pendingBotActionLabel: string | null =
    startOne.isPending   ? 'Starting…'   :
    stopOne.isPending    ? 'Stopping…'   :
    restartOne.isPending ? 'Restarting…' :
    null

  const lastRefresh = dataUpdatedAt ? new Date(dataUpdatedAt).toLocaleTimeString() : '—'

  return (
    <div>
      {/* ── Header ────────────────────────────────────────────────────────────── */}
      <div className="flex items-center gap-3 mb-[18px]">
        <h1 className="text-h1 font-semibold">Bots</h1>
        <span className="text-[12px] text-text-tertiary">
          {hasPendingTransitions ? 'polling 3s · ' : 'auto-refresh 60s · '}last {lastRefresh}
        </span>
        <button
          onClick={() => refetch()}
          disabled={isFetching}
          title="Refresh now"
          className="ml-auto flex items-center gap-[6px] px-3 py-[6px] rounded-md text-small border border-border-default bg-bg-surface text-text-secondary hover:bg-bg-hover hover:text-text-primary transition-colors disabled:opacity-40 disabled:cursor-not-allowed"
        >
          <RefreshCw size={13} className={isFetching ? 'animate-spin' : ''} />
          {isFetching ? 'Refreshing…' : 'Refresh'}
        </button>
      </div>

      {/* ── Loading ───────────────────────────────────────────────────────────── */}
      {isLoading && (
        <div className="animate-pulse">
          <div className="grid grid-cols-4 gap-[10px] mb-4">
            {[...Array(4)].map((_, i) => (
              <div key={i} className="bg-bg-surface border border-border-subtle rounded-lg p-4">
                <div className="h-[10px] w-24 bg-bg-surface-2 rounded mb-3" />
                <div className="h-[28px] w-16 bg-bg-surface-2 rounded mb-2" />
                <div className="h-[10px] w-20 bg-bg-surface-2 rounded" />
              </div>
            ))}
          </div>
          <div className="bg-bg-surface border border-border-subtle rounded-lg overflow-hidden">
            <div className="h-[38px] bg-bg-surface-2 border-b border-border-subtle" />
            {[...Array(4)].map((_, i) => (
              <div key={i} className="flex items-center gap-4 px-[14px] py-[12px] border-b border-border-subtle last:border-0">
                <div className="h-[12px] w-28 bg-bg-surface-2 rounded" />
                <div className="h-[12px] w-20 bg-bg-surface-2 rounded" />
                <div className="ml-auto h-[12px] w-16 bg-bg-surface-2 rounded" />
                <div className="h-[12px] w-16 bg-bg-surface-2 rounded" />
                <div className="h-[12px] w-12 bg-bg-surface-2 rounded" />
              </div>
            ))}
          </div>
          <div className="flex items-center justify-center gap-2 mt-5 text-[11px] text-text-tertiary font-mono">
            <svg className="animate-spin h-[13px] w-[13px] text-accent" fill="none" viewBox="0 0 24 24">
              <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" />
              <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z" />
            </svg>
            Connecting to VPS…
          </div>
        </div>
      )}

      {error && (
        <div className="text-neg-text text-small py-4 bg-neg-muted border border-neg-muted rounded-md px-4 mb-4">
          VPS fetch failed: {String(error)}
        </div>
      )}

      {snapshot && (
        <>
          {/* ── Stat cards ────────────────────────────────────────────────────── */}
          <div className="grid grid-cols-3 gap-[10px] mb-4">
            <StatCard
              label="Bots running"
              value={`${running} / ${total}`}
              sub={running === total ? 'all running' : running === 0 ? 'all stopped' : `${total - running} stopped`}
              subVariant={running === total ? 'pos' : running === 0 ? 'neg' : 'neutral'}
            />
            <StatCard
              label="Total balance"
              value={'$' + totalBalance.toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}
            />
            <StatCard
              label="Scheduled Jobs"
              value={snapshot.scheduled_jobs.length.toString()}
              sub={allJobsOk ? 'all running' : 'scheduled / waiting'}
              subVariant={allJobsOk ? 'pos' : 'neutral'}
            />
          </div>

          {/* ── Filter ────────────────────────────────────────────────────────── */}
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

          {/* ── Bots table ────────────────────────────────────────────────────── */}
          <div className="bg-bg-surface border border-border-subtle rounded-lg overflow-hidden mb-4">
            <table className="w-full border-collapse">
              <thead>
                <tr>
                  {['Bot', 'Account', 'Balance', 'Status', 'Uptime', 'Day P&L', 'Actions'].map(h => (
                    <th
                      key={h}
                      className={`text-left text-[10px] font-semibold uppercase tracking-[0.7px] text-text-tertiary px-[14px] py-[10px] bg-bg-surface-2 border-b border-border-subtle whitespace-nowrap align-middle
                        ${['Balance', 'Uptime', 'Day P&L', 'Actions'].includes(h) ? 'text-right' : ''}`}
                    >
                      {h}
                    </th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {bots.map((bot: BotStatus) => {
                  const isRunning = bot.status === 'RUNNING'
                  // Row is busy while HTTP request is in-flight OR while awaiting VPS state confirmation
                  const isThisRowBusy = (pendingBotName === bot.name) || !!pendingTransitions[bot.name]
                  const thisRowLabel  =
                    pendingBotName === bot.name
                      ? pendingBotActionLabel
                      : (pendingTransitions[bot.name]?.label ?? null)
                  // All rows lock while any action is in-flight or transitioning
                  const anyBusy = anyPending
                  return (
                    <tr key={bot.name} className="border-b border-border-subtle last:border-0">
                      <td className="px-[14px] py-[11px] font-medium align-middle">{bot.name}</td>
                      <td className="px-[14px] py-[11px] align-middle">
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
                      <td className="px-[14px] py-[11px] text-right font-mono text-small align-middle">
                        {bot.balance != null
                          ? '$' + bot.balance.toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 })
                          : '—'}
                      </td>
                      <td className="px-[14px] py-[11px] align-middle">
                        <StatusPill status={bot.status} />
                      </td>
                      <td className="px-[14px] py-[11px] text-right font-mono text-small text-text-secondary align-middle">
                        {bot.uptime_seconds != null ? formatUptime(bot.uptime_seconds) : '—'}
                      </td>
                      <td className="px-[14px] py-[11px] text-right font-mono text-small align-middle">
                        {bot.daily_pnl_pct != null
                          ? <span className={bot.daily_pnl_pct >= 0 ? 'text-pos-text' : 'text-neg-text'}>
                              {bot.daily_pnl_pct >= 0 ? '+' : ''}{bot.daily_pnl_pct.toFixed(1)}%
                            </span>
                          : <span className="text-text-tertiary">—</span>
                        }
                      </td>
                      {/* Per-row actions — locked while this row OR any row is transitioning */}
                      <td className="px-[14px] py-[11px] align-middle">
                        {isThisRowBusy ? (
                          // Show inline executing status on the active row until VPS confirms
                          <div className="flex items-center justify-end gap-[6px] text-[11px] text-accent">
                            <svg className="animate-spin h-[11px] w-[11px] flex-shrink-0" fill="none" viewBox="0 0 24 24">
                              <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" />
                              <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z" />
                            </svg>
                            {thisRowLabel}
                          </div>
                        ) : (
                          <div className="flex items-center justify-end gap-[4px]">
                            <RowActionBtn
                              icon={Play}
                              title="Start bot"
                              variant="pos"
                              disabled={isRunning || anyBusy}
                              onClick={() => {
                                setPendingFor(bot.name, 'start')
                                startOne.mutate(bot.name, { onError: () => clearPendingFor(bot.name) })
                              }}
                            />
                            <RowActionBtn
                              icon={Square}
                              title="Stop bot"
                              variant="neg"
                              disabled={!isRunning || anyBusy}
                              onClick={() => setConfirmStopBot(bot.name)}
                            />
                            <RowActionBtn
                              icon={RotateCcw}
                              title="Restart bot"
                              disabled={anyBusy}
                              onClick={() => {
                                setPendingFor(bot.name, 'restart')
                                restartOne.mutate(bot.name, { onError: () => clearPendingFor(bot.name) })
                              }}
                            />
                            <RowActionBtn
                              icon={FileText}
                              title="View log"
                              onClick={() => setLogBot(bot.name)}
                            />
                          </div>
                        )}
                      </td>
                    </tr>
                  )
                })}
                {bots.length === 0 && (
                  <tr>
                    <td colSpan={7} className="text-center py-12 text-text-tertiary text-small">
                      No bots match filter.
                    </td>
                  </tr>
                )}
              </tbody>
            </table>
          </div>

          {/* ── System + controls ────────────────────────────────────────────── */}
          <div className="grid grid-cols-2 gap-3">

            {/* System — scheduled tasks + services */}
            <div className="bg-bg-surface border border-border-subtle rounded-lg p-4">
              <div className="text-[13px] font-semibold mb-[14px]">System</div>

              {/* Scheduled tasks */}
              <p className="text-[10px] font-semibold uppercase tracking-[0.6px] text-text-tertiary mb-[4px]">Jobs</p>
              <table className="w-full text-micro mb-[12px]">
                <tbody>
                  {snapshot.scheduled_jobs.map((j: JobStatus) => (
                    <tr key={j.name}>
                      <td className="py-[6px]">
                        <div className="flex items-center gap-2">
                          <JobDot status={j.status} />
                          <span className={j.status === 'RUNNING' ? 'text-text-primary' : 'text-text-secondary'}>
                            {j.name}
                          </span>
                        </div>
                      </td>
                      <td className="text-right text-text-tertiary py-[6px]">{j.schedule}</td>
                    </tr>
                  ))}
                </tbody>
              </table>

              {/* Services — long-running processes */}
              <div className="border-t border-border-subtle/60 pt-[10px]">
                <p className="text-[10px] font-semibold uppercase tracking-[0.6px] text-text-tertiary mb-[6px]">Services</p>
                <div className="flex items-center justify-between">
                  <span className="text-micro text-text-secondary">Telegram</span>
                  <StatusPill status={snapshot.telegram.status} />
                </div>
              </div>
            </div>

            {/* Global control actions */}
            <div className="bg-bg-surface border border-border-subtle rounded-lg p-4">
              <div className="flex items-center mb-[14px]">
                <span className="text-[13px] font-semibold">Control Actions</span>
                {anyGlobalPending && (
                  <span className="ml-auto text-[11px] text-accent animate-pulse">Executing…</span>
                )}
              </div>
              <div className="flex gap-2 flex-wrap">
                <button
                  onClick={() => setConfirm('start')}
                  disabled={anyPending || anyRunning || noFilteredBots}
                  title={
                    noFilteredBots ? 'No bots in this filter' :
                    anyRunning     ? 'Stop all bots first — use ▷ on a row to start an individual bot' :
                                     'Start all bots via SYS_STARTUP'
                  }
                  className="flex items-center gap-[6px] px-3 py-[6px] rounded-md text-small border border-border-default bg-bg-surface text-text-primary hover:bg-bg-hover hover:border-pos/40 transition-colors disabled:opacity-40 disabled:cursor-not-allowed"
                >
                  <Play size={13} className="text-pos" />
                  Start all
                </button>
                <button
                  onClick={() => setConfirm('stop')}
                  disabled={anyPending || noFilteredBots}
                  title={noFilteredBots ? 'No bots in this filter' : 'Stop all bots'}
                  className="flex items-center gap-[6px] px-3 py-[6px] rounded-md text-small border border-neg/40 bg-neg-muted text-neg-text hover:bg-neg/10 hover:border-neg/70 transition-colors disabled:opacity-40 disabled:cursor-not-allowed"
                >
                  <Square size={13} />
                  Stop all
                </button>
                <button
                  onClick={() => setConfirm('restart')}
                  disabled={anyPending || noFilteredBots}
                  title={noFilteredBots ? 'No bots in this filter' : 'Restart all bots'}
                  className="flex items-center gap-[6px] px-3 py-[6px] rounded-md text-small border border-border-default bg-bg-surface text-text-primary hover:bg-bg-hover transition-colors disabled:opacity-40 disabled:cursor-not-allowed"
                >
                  <RotateCcw size={13} />
                  Restart all
                </button>
              </div>
              {noFilteredBots ? (
                <p className="text-[11px] text-warn-text mt-3">
                  No accounts in this filter — switch to All or a filter with accounts to enable controls.
                </p>
              ) : (
                <p className="text-[11px] text-text-tertiary mt-3">
                  Start / Stop apply to all bots. Use per-row buttons above to control individual bots.
                </p>
              )}
            </div>
          </div>
        </>
      )}

      {/* ── Log modal ─────────────────────────────────────────────────────────── */}
      {logBot && <LogModal botName={logBot} onClose={() => setLogBot(null)} />}

      {/* ── Confirm modals ────────────────────────────────────────────────────── */}
      {confirm === 'start' && (
        <ConfirmModal
          label="Start all bots?"
          description="This will run the SYS_STARTUP scheduled task on the VPS, starting all configured bot instances."
          confirmLabel="Start"
          confirmClass="bg-pos-muted text-pos-text border border-pos/40 hover:bg-pos/10"
          onConfirm={() => {
            startMut.mutate()
            snapshot?.bots.forEach(b => setPendingFor(b.name, 'start'))
            setConfirm(null)
          }}
          onCancel={() => setConfirm(null)}
          isPending={startMut.isPending}
        />
      )}
      {confirm === 'stop' && (
        <ConfirmModal
          label="Stop all bots?"
          description="This will delete the MT5 lock file and kill all python.exe processes on the VPS. Bots will not restart until SYS_STARTUP is triggered."
          confirmLabel="Stop all"
          confirmClass="bg-warn-muted text-warn-text border border-warn/40 hover:bg-warn/10"
          onConfirm={() => {
            stopMut.mutate()
            snapshot?.bots.forEach(b => setPendingFor(b.name, 'stop'))
            setConfirm(null)
          }}
          onCancel={() => setConfirm(null)}
          isPending={stopMut.isPending}
        />
      )}
      {confirm === 'restart' && (
        <ConfirmModal
          label="Restart all bots?"
          description="This will stop all bots (kill python.exe + delete lock), wait 3 seconds, then fire SYS_STARTUP to bring them back up."
          confirmLabel="Restart"
          confirmClass="bg-accent-muted text-accent-text border border-accent/30 hover:bg-accent/10"
          onConfirm={() => {
            restartMut.mutate()
            snapshot?.bots.forEach(b => setPendingFor(b.name, 'restart'))
            setConfirm(null)
          }}
          onCancel={() => setConfirm(null)}
          isPending={restartMut.isPending}
        />
      )}
      {confirmStopBot && (
        <ConfirmModal
          label={`Stop ${confirmStopBot}?`}
          description={`This will terminate the ${confirmStopBot} process on the VPS. The bot will stop trading immediately. Restart it manually when ready.`}
          confirmLabel="Stop bot"
          confirmClass="bg-neg-muted text-neg-text border border-neg/40 hover:bg-neg/10"
          onConfirm={() => {
            setPendingFor(confirmStopBot, 'stop')
            stopOne.mutate(confirmStopBot, { onError: () => clearPendingFor(confirmStopBot) })
            setConfirmStopBot(null)
          }}
          onCancel={() => setConfirmStopBot(null)}
          isPending={stopOne.isPending}
        />
      )}
    </div>
  )
}
