import { useState, useEffect, Fragment } from 'react'
import { useSearchParams } from 'react-router-dom'
import { FileText, Play, RotateCcw, Square, RefreshCw, ChevronRight, Copy, Check, Unplug, AlertTriangle, Layers } from 'lucide-react'
import type { LucideIcon } from 'lucide-react'
import {
  useBotSnapshot, useBotAccounts, useBotLog, useBotVersions, useUsers,
  useBotStart, useBotStop, useBotRestart,
  useBotStartOne, useBotStopOne, useBotRestartOne,
} from '@/hooks/useBots'
import { StatCard } from '@/components/StatCard'
import { VersionPill } from '@/components/VersionPill'
import { BotStatusPill } from './BotStatusPill'
import type { BotStatus, BotReview, JobStatus } from '@/types'
import { AccountsTab, useAccountCount } from './AccountsTab'
import { ConfigureTab } from './ConfigureTab'
import { UsersTab } from './UsersTab'

type AccountFilter = 'all' | 'demo' | 'live'
type PageTab = 'monitor' | 'accounts' | 'configure' | 'users'

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

function relativeTime(iso: string): string {
  const diff = Date.now() - new Date(iso).getTime()
  const mins = Math.floor(diff / 60_000)
  if (mins < 1) return 'just now'
  if (mins < 60) return `${mins}m ago`
  const hrs = Math.floor(mins / 60)
  if (hrs < 24) return `${hrs}h ago`
  return `${Math.floor(hrs / 24)}d ago`
}

/** This bot shares its trading account with at least one other bot.
 *
 * ⚠ Derived from the instance configs (`GET /bots/accounts`), not from a stored grouping — two
 * bots naming the same account ARE sharing a balance whether anybody grouped them or not.
 * Absent when the accounts query has not answered: unknown is not "not stacked", and this is
 * the one chip whose false absence understates how much risk is on. */
function StackedChip({ n, cap }: { n: number; cap: number | null }) {
  return (
    <span
      data-testid="row-stacked-chip"
      title={`${n} bots trade this account, so they share one balance.\n`
             + (cap === null
                ? 'No account risk cap is set — nothing stops them holding full risk at once.'
                : `Account risk cap ${cap}% of the live balance.`)}
      className="inline-flex items-center gap-[3px] text-[10px] font-semibold px-2 py-[3px]
                 rounded-pill uppercase tracking-[0.4px] bg-accent-muted text-text-primary cursor-default"
    >
      <Layers size={9} /> Stacked
    </span>
  )
}

/** Running, but not talking to its terminal.
 *
 * This sits BESIDE the Running pill rather than replacing it, because both are true and they
 * are different facts: the process is alive (so restarting it is the fix, and the watchdog is
 * right not to have fired) and it is blind (so it is taking no trades and managing none).
 * Collapsing the two into one word would lose whichever half the reader needed.
 *
 * ⚠ `=== false` and never falsy — `null` means the bot has not stamped a link state, which is
 * not the same claim. Rendering an unanswered question as a failure is the mistake this chip
 * was added to stop, in the other direction. */
function NoLinkChip() {
  return (
    <span
      title="The bot is running but its MT5 terminal is not answering, so it is receiving no bars. It retries every 30s; if this persists, restart the bot."
      className="inline-flex items-center gap-[3px] text-[10px] font-semibold px-2 py-[3px]
                 rounded-pill uppercase tracking-[0.4px] bg-warn-muted text-warn-text cursor-default"
    >
      <Unplug size={9} /> No MT5 link
    </span>
  )
}

/** The standing "needs review" flag, raised by the hourly `algos/notifications/log_review.py`.
 *
 * ⚠ It exists because a Telegram alert is a MOMENT and this is a STATE. The ping you scrolled
 * past at 3am is gone; this chip is still on the row tomorrow. That pair is the whole design —
 * the notification gets your attention, the chip survives not having had it.
 *
 * ⚠ It is deliberately NOT hidden on a stopped bot. The findings that matter most — it crashed,
 * it was killed, it refused to start — are exactly the ones you can only read once the bot is
 * no longer running, so hiding it there would suppress the explanation at the moment somebody
 * is looking for it.
 *
 * The title carries every finding, because the whole point is that the chip has to be readable
 * without opening a log file on a Windows box. */
function ReviewChip({ review }: { review: BotReview }) {
  const alert = review.level === 'alert'
  return (
    <span
      title={review.findings.map(f => `• ${f.title}\n  ${f.detail}`).join('\n\n')
             + `\n\nChecked ${review.checked_at}`}
      className={`inline-flex items-center gap-[3px] text-[10px] font-semibold px-2 py-[3px]
                  rounded-pill uppercase tracking-[0.4px] cursor-default ${
                    alert ? 'bg-neg-muted text-neg-text' : 'bg-warn-muted text-warn-text'}`}
    >
      <AlertTriangle size={9} /> Needs review{review.findings.length > 1
        ? ` (${review.findings.length})` : ''}
    </span>
  )
}

function JobDot({ status }: { status: string }) {
  if (status === 'RUNNING') {
    return (
      <span
        title="Running"
        className="inline-block w-[7px] h-[7px] rounded-full flex-shrink-0 bg-pos shadow-[0_0_6px_#00ff7f] cursor-default"
      />
    )
  }
  // Switched off on purpose — no glow. A gold "waiting for next trigger" dot on a task
  // that will never fire is worse than no dot: it says the job is covered when it isn't.
  if (status === 'DISABLED') {
    return (
      <span
        title="Disabled — will not run until re-enabled on the VPS"
        className="inline-block w-[7px] h-[7px] rounded-full flex-shrink-0 bg-text-tertiary/40 cursor-default"
      />
    )
  }
  return (
    <span
      title="Scheduled — waiting for next trigger"
      className="inline-block w-[7px] h-[7px] rounded-full flex-shrink-0 bg-gold shadow-[0_0_6px_#d9a441] cursor-default"
    />
  )
}

function LogModal({ botName, botLabel, onClose }: {
  /** The bot KEY — what the API is called with. */
  botName: string
  /** What a human calls it — what the header shows. Separate, so a rename never changes
   *  which bot's log is fetched. */
  botLabel: string
  onClose: () => void
}) {
  const { data: log, isLoading, error } = useBotLog(botName)
  const [copied, setCopied] = useState(false)
  function copyLog() {
    if (!log) return
    navigator.clipboard.writeText(log)
    setCopied(true)
    setTimeout(() => setCopied(false), 1500)
  }
  return (
    <div className="fixed inset-0 bg-black/60 flex items-center justify-center z-50 p-6" onClick={onClose}>
      <div className="bg-bg-surface border border-border-default rounded-lg w-full max-w-3xl max-h-[80vh] flex flex-col" onClick={e => e.stopPropagation()}>
        <div className="flex items-center justify-between px-4 py-3 border-b border-border-subtle">
          <span className="text-[13px] font-semibold">{botLabel} — stdout log</span>
          <div className="flex items-center gap-2">
            {log && (
              <button onClick={copyLog} title="Copy log" className="p-1 rounded hover:bg-bg-hover text-text-tertiary hover:text-text-secondary transition-colors">
                {copied ? <Check size={13} className="text-accent" /> : <Copy size={13} />}
              </button>
            )}
            <button onClick={onClose} className="text-text-tertiary hover:text-text-primary text-[18px] leading-none">×</button>
          </div>
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

function ConfirmModal({
  label, description, confirmLabel, confirmClass,
  onConfirm, onCancel, isPending,
}: {
  label: string
  /** ReactNode, so a fleet action can LIST the bots it is about to hit. "Are you sure?"
   *  trains you to click yes; the names of four accounts do not. Same rule the risk-change
   *  dialog on Configure follows — the confirmation carries the facts, not the question. */
  description: React.ReactNode
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
        <div className="text-[12px] text-text-tertiary mb-5">{description}</div>
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

/**
 * The bots a FLEET action is about to hit, by name.
 *
 * The three fleet dialogs used to describe the mechanism ("kills all python.exe processes")
 * and never the subjects, so the one fact a reader needs to catch a misclick — *which
 * accounts* — was the one thing not on screen. A live account is called out, because that is
 * the row whose cost is different in kind rather than degree.
 */
function AffectedBots({ bots }: { bots: BotStatus[] }) {
  if (bots.length === 0) return null
  return (
    <div className="mt-3 bg-bg-sunken border border-border-subtle rounded-md p-[10px] max-h-[160px] overflow-y-auto">
      <p className="text-[10px] font-semibold uppercase tracking-[0.6px] text-text-tertiary mb-[6px]">
        Affects {bots.length} {bots.length === 1 ? 'bot' : 'bots'}
      </p>
      {bots.map(b => (
        <div key={b.key} className="flex items-center gap-[6px] py-[2px]">
          <span className={`w-[5px] h-[5px] rounded-full flex-shrink-0 ${
            b.status === 'RUNNING' ? 'bg-pos' : 'bg-neg'
          }`} />
          <span className="text-[11px] text-text-secondary truncate">{b.name}</span>
          {b.account_type === 'live' && (
            <span className="ml-auto inline-flex text-[9px] font-semibold px-[5px] py-[1px] rounded-pill uppercase tracking-[0.4px] bg-warn-muted text-warn-text flex-shrink-0">
              live
            </span>
          )}
        </div>
      ))}
    </div>
  )
}

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
  // Which bots share a balance. Separate query on purpose: it reads instance configs rather
  // than the VPS, so it still answers when the box is down, and a stale snapshot must not be
  // able to hide a stacked account.
  const { data: accountGroups } = useBotAccounts()
  const stackedByKey = new Map<string, { n: number; cap: number | null }>()
  for (const g of accountGroups ?? []) {
    if (!g.stacked) continue
    // A disagreement is NOT a cap, so the chip says 'no cap' rather than quoting one of them.
    const cap = g.cap_agrees ? g.risk_cap_pct : null
    for (const b of g.bots) stackedByKey.set(b.key, { n: g.bots.length, cap })
  }
  const [searchParams, setSearchParams] = useSearchParams()
  const tab = (searchParams.get('tab') ?? 'monitor') as PageTab
  // The numbers on the tab chips. Both are cheap cached reads the tabs themselves already make,
  // so showing them costs no extra request once either tab has been opened.
  const accountCount = useAccountCount()
  const { data: users } = useUsers()
  const tabCount: Record<PageTab, number | undefined> = {
    monitor: undefined,          // the fleet size is a stat card on that tab, not a chip
    accounts: accountCount,
    configure: undefined,        // Configure lists the same bots Monitor does
    users: users?.length,
  }
  // Merge rather than replace — Configure keeps its selected bot in `?bot=`, and rebuilding
  // the whole query string would drop it, so leaving the tab and coming back would land you
  // on a different bot's promote button than the one you left.
  const setTab = (t: PageTab) => setSearchParams(prev => {
    const next = new URLSearchParams(prev)
    next.set('tab', t)
    return next
  }, { replace: true })
  const [filter, setFilter]               = useState<AccountFilter>('all')
  const [expandedBot, setExpandedBot]     = useState<string | null>(null)
  const [logBot, setLogBot]               = useState<string | null>(null)
  const [confirm, setConfirm]             = useState<'start' | 'stop' | 'restart' | null>(null)
  const [confirmStopBot, setConfirmStopBot] = useState<string | null>(null)

  // Global control mutations
  const startMut   = useBotStart()
  const stopMut    = useBotStop()
  const restartMut = useBotRestart()
  // Per-bot control mutations
  const startOne   = useBotStartOne()
  const stopOne    = useBotStopOne()
  const restartOne = useBotRestartOne()

  // ── Derived values ────────────────────────────────────────────────────────────

  const allBots = snapshot?.bots ?? []
  const bots = allBots.filter(b => filter === 'all' || b.account_type === filter)

  // Which version each bot is RUNNING. Shares `useBotVersion`'s cache entries, so this row, the
  // Accounts tab and the Configure tab's banner are one fetch and cannot disagree — see
  // `useBotVersions`. Keyed over ALL bots, not the filtered list, so switching the demo/live
  // filter does not re-key the queries and re-fetch what is already in hand.
  const versionQueries = useBotVersions(allBots.map(b => b.key))
  const versionByKey = new Map(allBots.map((b, i) => [b.key, versionQueries[i]]))

  const running      = allBots.filter(b => b.status === 'RUNNING').length
  const total        = allBots.length
  const totalBalance = allBots.reduce((s, b) => s + (b.balance ?? 0), 0)
  const allJobsOk    = snapshot?.scheduled_jobs.every(j => j.status === 'RUNNING') ?? false

  // ⚠ These gate the FLEET buttons, so they are counted over ALL bots — never over the
  // filtered list. The filter is a view of the table; `POST /bots/{start,stop,restart}`
  // fires SYS_STARTUP / kills python on the VPS and has no idea a filter exists. Deriving
  // the guard from the filtered set is how "Stop all bots first" gets defeated by choosing
  // a tab: with the live filter on and no live bot running, `anyRunning` read false while
  // the demo bots were up.
  const anyRunning  = allBots.some(b => b.status === 'RUNNING')
  const noBots      = allBots.length === 0
  const liveBots    = allBots.filter(b => b.account_type === 'live')
  const filterHides = allBots.length - bots.length

  const anyGlobalPending = startMut.isPending || stopMut.isPending || restartMut.isPending
  const anyPerBotPending = startOne.isPending || stopOne.isPending || restartOne.isPending
  const anyBusy          = anyGlobalPending || anyPerBotPending

  // These four all hold a bot KEY, never a display name — see `BotStatus.key`. A name is a
  // label chosen for a human and is the field that eventually changes; state that ADDRESSES
  // a bot has to survive that. Display text is looked up from the row instead.
  const pendingBotKey: string | undefined =
    startOne.isPending   ? startOne.variables :
    stopOne.isPending    ? stopOne.variables :
    restartOne.isPending ? restartOne.variables :
    undefined
  const pendingBotActionLabel: string | null =
    startOne.isPending   ? 'Starting…'   :
    stopOne.isPending    ? 'Stopping…'   :
    restartOne.isPending ? 'Restarting…' :
    null

  // Key → what a human calls it. State addresses a bot by key; every string a person reads
  // goes through here, so a rename changes the copy and never the target.
  const labelOf = (key: string) => allBots.find(b => b.key === key)?.name ?? key

  const lastRefresh = dataUpdatedAt ? new Date(dataUpdatedAt).toLocaleTimeString() : '—'

  const [, setTick] = useState(0)
  useEffect(() => {
    const id = setInterval(() => setTick(t => t + 1), 1000)
    return () => clearInterval(id)
  }, [])
  const secondsLeft = dataUpdatedAt
    ? Math.max(0, 60 - Math.floor((Date.now() - dataUpdatedAt) / 1000))
    : null

  return (
    <div>
      {/* ── Header ────────────────────────────────────────────────────────────── */}
      <div className="flex items-center gap-3 mb-[18px]">
        <h1 className="text-h1 font-semibold">Bots</h1>

        {/* Tab switcher.
            ⚠ **The count belongs on the TAB, not inside the tab it describes.** Aaron: "accounts
            on the left navigation as account four — just put that count inside the accounts tab
            where I could see it." A number on the chip answers *how many are there* without
            opening anything; the same number inside the panel only answers it once you are
            already looking. Each count has ONE definition and it is not here — see
            `useAccountCount`, and `useUsers` for the other. */}
        <div className="flex bg-bg-surface border border-border-subtle rounded-md overflow-hidden">
          {(['monitor', 'accounts', 'configure', 'users'] as PageTab[]).map(t => (
            <span
              key={t}
              onClick={() => setTab(t)}
              className={`text-micro px-3 py-[6px] cursor-pointer select-none capitalize transition-colors duration-[100ms] flex items-center gap-[6px] ${tab === t ? 'bg-accent-muted text-text-primary' : 'text-text-secondary hover:bg-bg-hover'}`}
            >
              {t}
              {/* An unanswered query renders NO chip rather than a `0` — "none registered" is a
                  claim, and it is never the true one here. */}
              {tabCount[t] !== undefined && (
                <span data-testid={`tab-count-${t}`}
                      className={`inline-flex items-center justify-center min-w-[16px] h-[16px] px-[4px]
                                  rounded-pill text-[10px] font-mono tabular-nums ${
                        tab === t ? 'bg-bg-base/60 text-text-secondary'
                          : 'bg-bg-surface-2 text-text-tertiary'}`}>
                  {tabCount[t]}
                </span>
              )}
            </span>
          ))}
        </div>

        <button
            onClick={() => refetch()}
            disabled={isFetching}
            title="Refresh now"
            className="ml-auto flex items-center gap-[6px] px-3 py-[6px] rounded-md text-small border border-border-default bg-bg-surface text-text-secondary hover:bg-bg-hover hover:text-text-primary transition-colors disabled:opacity-40 disabled:cursor-not-allowed"
          >
            <RefreshCw size={13} className={isFetching ? 'animate-spin' : ''} />
            {isFetching ? (
              <span>Refreshing…</span>
            ) : (
              <>
                <span className="font-mono text-accent tabular-nums">
                  {secondsLeft !== null ? `${secondsLeft}s` : '—'}
                </span>
                <span className="text-text-tertiary">·</span>
                <span className="text-text-tertiary">last {lastRefresh}</span>
              </>
            )}
          </button>
      </div>

      {/* ── Loading ───────────────────────────────────────────────────────────────
          🔴 **Gated on the MONITOR tab (2026-08-12).** This skeleton is a picture of Monitor's
          stat cards and bot table, and it rendered on every tab — so opening Accounts drew ~400px
          of fake Monitor rows above it for the four seconds the VPS snapshot takes, then snapped
          away and moved everything up. The Accounts and Users tabs do not read the snapshot to
          render at all (Accounts joins it only for the State column, which honestly says `—`), so
          they were being blocked by a fetch neither of them needs. */}
      {isLoading && tab === 'monitor' && (
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

      {/* ── Monitor tab ───────────────────────────────────────────────────────── */}
      {snapshot && tab === 'monitor' && (
        <>
          {/* ── Stat cards ──────────────────────────────────────────────────── */}
          <div className="grid grid-cols-3 gap-[10px] mb-4">
            <StatCard
              label="Bots running"
              value={`${running} / ${total}`}
              sub={running === total ? 'All Running' : running === 0 ? 'all stopped' : `${total - running} stopped`}
              subVariant={running === total ? 'pos' : running === 0 ? 'neg' : 'neutral'}
            />
            <StatCard
              label="Total balance"
              value={'$' + totalBalance.toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}
            />
            <StatCard
              label="Scheduled Jobs"
              value={snapshot.scheduled_jobs.length.toString()}
              sub={allJobsOk ? 'All Running' : 'scheduled / waiting'}
              subVariant={allJobsOk ? 'pos' : 'neutral'}
            />
          </div>

          {/* ── Filter ──────────────────────────────────────────────────────── */}
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

          {/* ── Bots table ──────────────────────────────────────────────────── */}
          <div className="bg-bg-surface border border-border-subtle rounded-lg overflow-hidden mb-4">
            <table className="w-full border-collapse">
              <thead>
                <tr>
                  {/* "This bot" rather than "Actions": the fleet card below has buttons that
                      look the same and mean something else entirely, and the column header is
                      the only place the SCOPE of a row's buttons can be stated once. */}
                  {['Bot', 'Status', 'Version', 'Balance', 'Overall P&L', 'Account', 'Uptime', 'This bot', 'Logs'].map(h => (
                    <th
                      key={h}
                      className="text-left text-[10px] font-semibold uppercase tracking-[0.7px] text-text-tertiary px-6 py-[10px] bg-bg-surface-2 border-b border-border-subtle whitespace-nowrap align-middle"
                    >
                      {h}
                    </th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {bots.map((bot: BotStatus) => {
                  const isRunning     = bot.status === 'RUNNING'
                  const isThisRowBusy = pendingBotKey === bot.key
                  const isExpanded    = expandedBot === bot.key
                  return (
                    <Fragment key={bot.key}>

                      {/* ── Main row ────────────────────────────── */}
                      <tr className="border-b border-border-subtle hover:bg-bg-hover/40 transition-colors duration-[80ms]">
                        <td
                          className="px-6 py-[11px] font-medium align-middle cursor-pointer select-none"
                          onClick={() => setExpandedBot(isExpanded ? null : bot.key)}
                        >
                          <div className="flex items-center gap-[7px]">
                            <ChevronRight
                              size={12}
                              className={`text-text-tertiary flex-shrink-0 transition-transform duration-150 ${isExpanded ? 'rotate-90' : ''}`}
                            />
                            {bot.name}
                          </div>
                        </td>
                        <td className="px-6 py-[11px] align-middle">
                          <div className="flex items-center gap-[6px]">
                            <BotStatusPill status={bot.status} />
                            {stackedByKey.has(bot.key) && (
                              <StackedChip n={stackedByKey.get(bot.key)!.n}
                                           cap={stackedByKey.get(bot.key)!.cap} />
                            )}
                            {bot.mt5_link === false && <NoLinkChip />}
                            {bot.review && <ReviewChip review={bot.review} />}
                          </div>
                        </td>
                        <td className="px-6 py-[11px] align-middle">
                          <VersionPill version={versionByKey.get(bot.key)?.data}
                                       loading={versionByKey.get(bot.key)?.isPending} />
                        </td>
                        <td className="px-6 py-[11px] font-mono text-small align-middle">
                          {bot.balance != null
                            ? '$' + bot.balance.toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 })
                            : <span className={bot.mt5_link === false ? 'text-warn-text' : 'text-text-tertiary'}>
                                {bot.mt5_link === false ? 'no link' : '—'}
                              </span>}
                        </td>
                        <td className="px-6 py-[11px] font-mono text-small align-middle">
                          {bot.total_pnl_pct != null
                            ? <span className={bot.total_pnl_pct >= 0 ? 'text-pos-text' : 'text-neg-text'}>
                                {bot.total_pnl_pct >= 0 ? '+' : ''}{bot.total_pnl_pct.toFixed(1)}%
                              </span>
                            : <span className="text-text-tertiary">—</span>
                          }
                        </td>
                        <td className="px-6 py-[11px] align-middle">
                          <div className="flex items-center gap-[6px]">
                            <span className="font-mono text-[11px] text-text-secondary">{bot.account}</span>
                            {filter === 'all' && (
                              <span className="inline-flex text-[10px] font-semibold px-2 py-[3px] rounded-pill uppercase tracking-[0.4px] bg-bg-surface-2 text-text-secondary">
                                {bot.account_type}
                              </span>
                            )}
                            {bot.day_locked && (
                              <span className="inline-flex text-[10px] font-semibold px-2 py-[3px] rounded-pill uppercase bg-warn-muted text-warn-text">
                                locked
                              </span>
                            )}
                          </div>
                        </td>
                        <td className="px-6 py-[11px] font-mono text-small text-text-secondary align-middle">
                          {bot.uptime_seconds != null ? formatUptime(bot.uptime_seconds) : '—'}
                        </td>
                        <td className="px-6 py-[11px] align-middle">
                          {isThisRowBusy ? (
                            <div className="flex items-center gap-[6px] text-[11px] text-accent">
                              <svg className="animate-spin h-[11px] w-[11px] flex-shrink-0" fill="none" viewBox="0 0 24 24">
                                <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" />
                                <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z" />
                              </svg>
                              {pendingBotActionLabel}
                            </div>
                          ) : (
                            <div className="flex items-center gap-[4px]">
                              {isRunning ? (
                                <>
                                  <RowActionBtn
                                    icon={Square}
                                    title="Stop bot"
                                    variant="neg"
                                    disabled={anyGlobalPending}
                                    onClick={() => setConfirmStopBot(bot.key)}
                                  />
                                  <RowActionBtn
                                    icon={RotateCcw}
                                    title="Restart bot"
                                    disabled={anyGlobalPending}
                                    onClick={() => restartOne.mutate(bot.key)}
                                  />
                                </>
                              ) : (
                                <RowActionBtn
                                  icon={Play}
                                  title="Start bot"
                                  variant="pos"
                                  disabled={anyGlobalPending}
                                  onClick={() => startOne.mutate(bot.key)}
                                />
                              )}
                            </div>
                          )}
                        </td>
                        <td className="px-6 py-[11px] align-middle">
                          <RowActionBtn
                            icon={FileText}
                            title="View log"
                            onClick={() => setLogBot(bot.key)}
                          />
                        </td>
                      </tr>

                      {/* ── Expanded detail row ──────────────────── */}
                      {isExpanded && (
                        <tr className="bg-bg-sunken border-b border-border-subtle">
                          <td colSpan={9} className="px-6 py-[14px]">

                            {/* ── Config strip ─────────────────────────────────────────
                                Four stat tiles (Daily P&L / Weekly P&L / Trades Today /
                                Peak Balance) and three cap chips (Goal / Daily cap / Weekly
                                cap) stood here until 2026-08-05. Every one was written by
                                `algos/notifications/pnl_tracker.py`, deleted that day — it
                                had carried an empty bot registry since June, so all seven
                                had been drawing an em-dash or nothing for six weeks while
                                looking like fields that were merely quiet. Balance, Overall
                                P&L and Uptime are in the row above and the bot writes them
                                itself. Do not re-add a tile here without a writer behind
                                it: a `number | null` nothing populates reads as "no P&L
                                today" rather than "nothing measures this". ────────────── */}
                            <div className="flex items-center gap-[12px] text-[11px] text-text-tertiary flex-wrap">
                              {bot.last_updated && (
                                <span>Updated <span className="text-text-secondary ml-[4px]">{relativeTime(bot.last_updated)}</span></span>
                              )}
                            </div>

                            {/* ── Lock banner ──────────────────────── */}
                            {bot.day_locked && (
                              <div className="mt-[10px] pt-[10px] border-t border-border-subtle/40 flex items-center gap-[6px]">
                                <span className="text-[11px] text-warn-text">
                                  🔒 Day locked{bot.lock_reason ? ` — ${bot.lock_reason}` : ''}
                                </span>
                              </div>
                            )}

                          </td>
                        </tr>
                      )}

                    </Fragment>
                  )
                })}
                {bots.length === 0 && (
                  <tr>
                    <td colSpan={9} className="text-center py-12 text-text-tertiary text-small">
                      No bots match filter.
                    </td>
                  </tr>
                )}
              </tbody>
            </table>
          </div>

          {/* ── System + controls ───────────────────────────────────────────── */}
          <div className="grid grid-cols-2 gap-3">

            <div className="bg-bg-surface border border-border-subtle rounded-lg p-4">
              <div className="text-[13px] font-semibold mb-[14px]">System</div>
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
              <div className="border-t border-border-subtle/60 pt-[10px]">
                <p className="text-[10px] font-semibold uppercase tracking-[0.6px] text-text-tertiary mb-[6px]">Services</p>
                <div className="flex items-center justify-between">
                  <span className="text-micro text-text-secondary">Telegram</span>
                  <BotStatusPill status={snapshot.telegram.status} />
                </div>
              </div>
            </div>

            {/* ── Fleet controls ───────────────────────────────────────────────
                G11's third bullet: these buttons and the ▷ ■ ↻ in every table row were
                rendered in the same visual language, and they are not the same kind of
                thing — one restarts a bot, the other kills every python process on the
                VPS. With one bot registered the distinction is academic; with four it is
                the click that takes the book down when you meant one row.

                So the card is DANGER-TINTED, says its scope in its own title, and every
                button carries the COUNT it will hit. A label that is a number cannot say
                one thing while the table says another — the same rule the news filter's
                "Excluding N trades" follows. */}
            <div className="bg-bg-surface border border-neg/30 rounded-lg p-4">
              <div className="flex items-center mb-[4px]">
                <span className="text-[13px] font-semibold">Fleet controls</span>
                <span className="ml-[8px] inline-flex text-[10px] font-semibold px-2 py-[3px] rounded-pill uppercase tracking-[0.4px] bg-neg-muted text-neg-text">
                  all {total} {total === 1 ? 'bot' : 'bots'}
                </span>
                {anyGlobalPending && (
                  <span className="ml-auto text-[11px] text-accent animate-pulse">Executing…</span>
                )}
              </div>
              <p className="text-[11px] text-text-tertiary mb-[14px] leading-[1.5]">
                These act on every registered bot at once. To control one bot, use the
                buttons in its row above.
              </p>
              <div className="flex gap-2 flex-wrap">
                <button
                  onClick={() => setConfirm('start')}
                  disabled={anyBusy || anyRunning || noBots}
                  title={
                    noBots     ? 'No bots registered' :
                    anyRunning ? 'Something is already running — use ▷ on a row to start an individual bot' :
                                 'Start every bot via SYS_STARTUP'
                  }
                  className="flex items-center gap-[6px] px-3 py-[6px] rounded-md text-small border border-border-default bg-bg-surface text-text-primary hover:bg-bg-hover hover:border-pos/40 transition-colors disabled:opacity-40 disabled:cursor-not-allowed"
                >
                  <Play size={13} className="text-pos" />
                  Start all {total}
                </button>
                <button
                  onClick={() => setConfirm('stop')}
                  disabled={anyBusy || noBots}
                  title={noBots ? 'No bots registered' : `Stop all ${total} bots`}
                  className="flex items-center gap-[6px] px-3 py-[6px] rounded-md text-small border border-neg/40 bg-neg-muted text-neg-text hover:bg-neg/10 hover:border-neg/70 transition-colors disabled:opacity-40 disabled:cursor-not-allowed"
                >
                  <Square size={13} />
                  Stop all {total}
                </button>
                <button
                  onClick={() => setConfirm('restart')}
                  disabled={anyBusy || noBots}
                  title={noBots ? 'No bots registered' : `Restart all ${total} bots`}
                  className="flex items-center gap-[6px] px-3 py-[6px] rounded-md text-small border border-border-default bg-bg-surface text-text-primary hover:bg-bg-hover transition-colors disabled:opacity-40 disabled:cursor-not-allowed"
                >
                  <RotateCcw size={13} />
                  Restart all {total}
                </button>
              </div>

              {noBots && (
                <p className="text-[11px] text-warn-text mt-3">
                  No bots registered — nothing for these to act on.
                </p>
              )}

              {/* The filter is a view of the TABLE and these endpoints have never heard of
                  it. Saying so only when it can actually mislead — i.e. when the filter is
                  hiding a bot these buttons would still hit. */}
              {filterHides > 0 && (
                <p className="text-[11px] text-warn-text mt-3 flex items-start gap-[6px]">
                  <span aria-hidden>⚠</span>
                  <span>
                    The <strong>{filter}</strong> filter is hiding {filterHides}{' '}
                    {filterHides === 1 ? 'bot' : 'bots'}. These buttons still act on all {total}.
                  </span>
                </p>
              )}
              {liveBots.length > 0 && (
                <p className="text-[11px] text-warn-text mt-2">
                  {liveBots.length} of these {liveBots.length === 1 ? 'is a LIVE account' : 'are LIVE accounts'}.
                </p>
              )}
            </div>
          </div>
        </>
      )}

      {/* ── Configure tab ─────────────────────────────────────────────────────── */}
      {tab === 'accounts' && <AccountsTab />}

      {tab === 'configure' && <ConfigureTab />}

      {/* ── Users tab ─────────────────────────────────────────────────────────── */}
      {tab === 'users' && <UsersTab />}

      {/* ── Log modal ─────────────────────────────────────────────────────────── */}
      {logBot && <LogModal botName={logBot} botLabel={labelOf(logBot)}
                           onClose={() => setLogBot(null)} />}

      {/* ── Confirm modals ────────────────────────────────────────────────────── */}
      {confirm === 'start' && (
        <ConfirmModal
          label={`Start all ${total} bots?`}
          description={
            <>
              <p>This runs the SYS_STARTUP scheduled task on the VPS, starting every configured
                 bot instance. It skips any bot already running.</p>
              <AffectedBots bots={allBots} />
            </>
          }
          confirmLabel="Start"
          confirmClass="bg-pos-muted text-pos-text border border-pos/40 hover:bg-pos/10"
          onConfirm={() => { startMut.mutate(undefined); setConfirm(null) }}
          onCancel={() => setConfirm(null)}
          isPending={startMut.isPending}
        />
      )}
      {confirm === 'stop' && (
        <ConfirmModal
          label={`Stop all ${total} bots?`}
          description={
            <>
              <p>This deletes the MT5 lock file and kills all python.exe processes on the VPS.
                 Bots will not restart until SYS_STARTUP is triggered.</p>
              <AffectedBots bots={allBots} />
            </>
          }
          confirmLabel={`Stop all ${total}`}
          confirmClass="bg-warn-muted text-warn-text border border-warn/40 hover:bg-warn/10"
          onConfirm={() => { stopMut.mutate(undefined); setConfirm(null) }}
          onCancel={() => setConfirm(null)}
          isPending={stopMut.isPending}
        />
      )}
      {confirm === 'restart' && (
        <ConfirmModal
          label={`Restart all ${total} bots?`}
          description={
            <>
              <p>This stops all bots (kill python.exe + delete lock), waits 3 seconds, then fires
                 SYS_STARTUP to bring them back up.</p>
              <AffectedBots bots={allBots} />
            </>
          }
          confirmLabel={`Restart all ${total}`}
          confirmClass="bg-accent-muted text-accent-text border border-accent/30 hover:bg-accent/10"
          onConfirm={() => { restartMut.mutate(undefined); setConfirm(null) }}
          onCancel={() => setConfirm(null)}
          isPending={restartMut.isPending}
        />
      )}
      {confirmStopBot && (
        <ConfirmModal
          label={`Stop ${labelOf(confirmStopBot)}?`}
          description={`This will terminate the ${labelOf(confirmStopBot)} process on the VPS. The bot will stop trading immediately. Restart it manually when ready.`}
          confirmLabel="Stop bot"
          confirmClass="bg-neg-muted text-neg-text border border-neg/40 hover:bg-neg/10"
          onConfirm={() => { stopOne.mutate(confirmStopBot); setConfirmStopBot(null) }}
          onCancel={() => setConfirmStopBot(null)}
          isPending={stopOne.isPending}
        />
      )}
    </div>
  )
}
