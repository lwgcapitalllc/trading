import { useMemo } from 'react'
import { useNavigate } from 'react-router-dom'
import {
  Bot,
  Radar,
  FlaskConical,
  BookOpen,
  ClipboardList,
  BarChart2,
  Sliders,
  Activity,
  CalendarDays,
  ChevronRight,
  Loader2,
  Unplug,
  AlertCircle,
} from 'lucide-react'
import type { ReactNode } from 'react'
import { useBotSnapshot } from '@/hooks/useBots'
import { useSmartMoneyRuns, useRunProgress } from '@/hooks/useSmartMoney'
import {
  useBacktestRuns,
  useStrategies,
  useOptimizations,
  useRulesets,
  useReadiness,
} from '@/hooks/useLab'
import { useStressTests } from '@/hooks/useStressTests'
import { useCalendar, useServerClock } from '@/hooks/useCalendar'
import { FEATURES } from '@/lib/features'
import {
  flagOf,
  IMPACT_DOT,
  IMPACT_LABEL,
  fmtTime,
  fmtCountdown,
  localWeekStart,
  localWeekEnd,
  dayIndexOf as weekDayIndex,
} from '@/lib/calendar'
import { StatCard } from '@/components/StatCard'
import { WorthinessBadge } from '@/components/WorthinessBadge'
import RobustnessGradeBadge from '@/components/RobustnessGradeBadge'
import type { BotStatus, BacktestSummary, CalendarEvent } from '@/types'

/** A "best result" needs a sample size behind it or profit factor ranks luck.
 *
 * Two trades at PF 8.0 outrank two hundred at PF 2.0, and PF has no opinion about which is the
 * better strategy. Same floor, and the same reasoning, as the optimizer modal's `min_trades`
 * default — a run under it still exists and is still one click away in Runs; it just cannot be
 * held up here as the best thing the lab has produced. */
const MIN_TRADES_FOR_BEST = 30

// ── Helpers ────────────────────────────────────────────────────────────────────

function relativeTime(dt: string | Date, nowMs: number): string {
  const diff = nowMs - new Date(dt).getTime()
  const mins = Math.floor(diff / 60_000)
  if (mins < 1) return 'just now'
  if (mins < 60) return `${mins}m ago`
  const hrs = Math.floor(mins / 60)
  if (hrs < 24) return `${hrs}h ago`
  const days = Math.floor(hrs / 24)
  return `${days}d ago`
}

function fmt$(n: number): string {
  return '$' + n.toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 })
}

/** Profit factor is `gross win / gross loss`, so a run with no losing trade divides by zero.
 *  JSON cannot carry Infinity, so it arrives as null or a huge float depending on the writer —
 *  either way `toFixed` on it is a number nobody can read. */
function fmtPf(pf: number | null | undefined): string {
  if (pf == null || !Number.isFinite(pf)) return '∞'
  return pf.toFixed(2)
}

// ── Sub-components ─────────────────────────────────────────────────────────────

function StatusPill({ status }: { status: string }) {
  const isRunning = status === 'RUNNING'
  const isError = status === 'ERROR'
  const cls = isRunning ? 'bg-pos-muted text-pos-text' : 'bg-neg-muted text-neg-text'
  const label = isRunning ? 'Running' : isError ? 'Error' : 'Stopped'
  return (
    <span
      className={`inline-flex text-[10px] font-semibold px-2 py-[3px] rounded-pill uppercase tracking-[0.4px] ${cls}`}
    >
      {label}
    </span>
  )
}

/** Running, but not talking to its terminal — the same chip the Bots page draws, for the same
 *  reason, and it has to be on BOTH pages: the incident it exists for (MetaTrader auto-updated
 *  under the live bot on 2026-08-04 and it sat blind for 50 minutes) presented as a healthy
 *  RUNNING row, and this page is the one a reader checks first.
 *
 *  ⚠ It sits BESIDE the Running pill, never instead of it — the process being ALIVE and being
 *  BLIND are both true and are different facts. ⚠ `=== false`, never falsy: `null` means the
 *  bot has not stamped a link state, which is not the claim "disconnected". */
function NoLinkChip() {
  return (
    <span
      title="The bot is running but its MT5 terminal is not answering, so it is receiving no bars. It retries every 30s; if this persists, restart the bot."
      className="inline-flex items-center gap-[3px] text-[9px] font-semibold px-[5px] py-[1px]
                 rounded-pill uppercase tracking-[0.4px] bg-warn-muted text-warn-text cursor-default"
    >
      <Unplug size={8} /> No link
    </span>
  )
}

function BotRow({ bot }: { bot: BotStatus }) {
  const pnl = bot.total_pnl_pct
  const pnlStr = pnl != null ? (pnl >= 0 ? `+${pnl.toFixed(2)}%` : `${pnl.toFixed(2)}%`) : null
  const pnlColor =
    pnl == null ? '' : pnl > 0 ? 'text-pos-text' : pnl < 0 ? 'text-neg-text' : 'text-text-tertiary'

  return (
    <div className="flex items-center gap-[10px] py-[7px] border-b border-border-subtle/40 last:border-0">
      <span className="text-[13px] text-text-primary flex-1 min-w-0 truncate">{bot.name}</span>
      {pnlStr && <span className={`text-[11px] font-mono tabular-nums ${pnlColor}`}>{pnlStr}</span>}
      {bot.day_locked && (
        <span className="text-[9px] font-semibold px-[5px] py-[1px] rounded-pill bg-warn-muted text-warn-text uppercase tracking-[0.4px]">
          locked
        </span>
      )}
      {bot.mt5_link === false && <NoLinkChip />}
      <StatusPill status={bot.status} />
    </div>
  )
}

function JobPill({ job }: { job: { name: string; status: string } }) {
  const running = job.status === 'RUNNING'
  // Switched off on purpose gets NO glow and no gold. A "waiting for next trigger" pill on a task
  // that will never fire says the job is covered when it isn't — and two of the three jobs on the
  // box are disabled today. Mirrors `JobDot` on the Bots page, deliberately word for word.
  const disabled = job.status === 'DISABLED'
  const dotCls = running
    ? 'bg-pos shadow-[0_0_5px_#00ff7f]'
    : disabled
      ? 'bg-text-tertiary/40'
      : 'bg-gold shadow-[0_0_5px_#d9a441]'
  const textCls = running ? 'text-pos-text' : disabled ? 'text-text-tertiary' : 'text-gold-text'
  const tip = running
    ? 'Running'
    : disabled
      ? 'Disabled — will not run until re-enabled on the VPS'
      : 'Scheduled — waiting for next trigger'
  return (
    <span
      title={tip}
      className={`inline-flex items-center gap-[4px] mr-[10px] text-[11px] cursor-default ${textCls}`}
    >
      <span className={`inline-block w-[5px] h-[5px] rounded-full flex-shrink-0 ${dotCls}`} />
      {job.name}
    </span>
  )
}

function BacktestStatusPill({ status }: { status: string }) {
  const isFailed = status.startsWith('failed')
  const label = isFailed
    ? 'Failed'
    : status === 'complete'
      ? 'Complete'
      : status === 'running'
        ? 'Running'
        : status
  const cls =
    status === 'complete'
      ? 'bg-pos-muted text-pos-text'
      : status === 'running'
        ? 'bg-accent-muted text-accent'
        : 'bg-neg-muted text-neg-text'
  return (
    <span
      className={`inline-flex px-2 py-[2px] rounded-pill text-[10px] font-semibold uppercase tracking-[0.4px] ${cls}`}
    >
      {label}
    </span>
  )
}

// A clickable metric row that navigates to its own destination. Used in the
// Research card so Strategies / Runs / Optimizations / Stress Tests each go to
// their real page or tab instead of all landing on /backtests.
function NavStatRow({
  icon,
  label,
  onClick,
  children,
}: {
  icon: ReactNode
  label: string
  onClick: () => void
  children: ReactNode
}) {
  return (
    <button
      onClick={onClick}
      className="w-full flex items-center justify-between py-[8px] px-[8px] -mx-[8px] rounded-md hover:bg-bg-hover transition-colors duration-[120ms] group"
    >
      <div className="flex items-center gap-[8px]">
        <span className="text-text-tertiary group-hover:text-accent transition-colors">{icon}</span>
        <span className="text-[12px] text-text-secondary group-hover:text-text-primary transition-colors">
          {label}
        </span>
      </div>
      <div className="flex items-center gap-[8px]">
        {children}
        <ChevronRight
          size={12}
          className="text-text-tertiary/60 group-hover:text-text-secondary transition-colors"
        />
      </div>
    </button>
  )
}

function BotsCardSkeleton() {
  return (
    <div className="animate-pulse">
      {[...Array(4)].map((_, i) => (
        <div
          key={i}
          className="flex items-center gap-[10px] py-[7px] border-b border-border-subtle/40 last:border-0"
        >
          <div className="w-[7px] h-[7px] rounded-full bg-bg-surface-2 flex-shrink-0" />
          <div className="h-[11px] bg-bg-surface-2 rounded flex-1" />
          <div className="h-[11px] w-[42px] bg-bg-surface-2 rounded" />
          <div className="h-[11px] w-[50px] bg-bg-surface-2 rounded" />
        </div>
      ))}
      <div className="flex items-center justify-center gap-[6px] mt-3 pt-3 border-t border-border-subtle/40 text-[11px] text-text-tertiary">
        <svg className="animate-spin h-[11px] w-[11px] text-accent" fill="none" viewBox="0 0 24 24">
          <circle
            className="opacity-25"
            cx="12"
            cy="12"
            r="10"
            stroke="currentColor"
            strokeWidth="4"
          />
          <path
            className="opacity-75"
            fill="currentColor"
            d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z"
          />
        </svg>
        Connecting to VPS…
      </div>
    </div>
  )
}

// ── Page ───────────────────────────────────────────────────────────────────────

export function Overview() {
  const navigate = useNavigate()

  const { data: snapshot, isLoading: botsLoading, isError: botsError } = useBotSnapshot()

  // Hidden means not fetched. `useRunProgress` polls every 30s forever, so a card
  // that is merely not rendered would go on costing a request twice a minute.
  const smartMoney = FEATURES.smartMoney
  const { data: runs } = useSmartMoneyRuns(smartMoney)
  const { data: progress } = useRunProgress(smartMoney)
  const { data: backtestRuns } = useBacktestRuns()
  const { data: strategies } = useStrategies()
  const { data: rulesets } = useRulesets()
  const { data: optimizations } = useOptimizations()
  const { data: stressTests } = useStressTests()
  const { data: readiness } = useReadiness()

  const latestRun = runs?.[0] ?? null
  const totalStrategies = strategies?.length ?? 0

  // Rulesets — split prop vs personal/demo, the meaningful distinction (the grading lens)
  const personalRulesets =
    rulesets?.filter((r) => r.ruleset_type === 'personal' || r.ruleset_type === 'demo').length ?? 0
  const propRulesets = (rulesets?.length ?? 0) - personalRulesets

  // Standalone runs only (exclude optimization children). Memoized because the page re-renders
  // once a second to keep the calendar countdown honest, and these walk every run in the lab.
  const { totalStandaloneRuns, latestBacktest, bestRun, tier1Count, runningBacktests } =
    useMemo(() => {
      const standalone = backtestRuns?.filter((r) => !r.optimization_id) ?? []
      // Ranked on profit factor, but only among runs with a real sample behind them — see
      // MIN_TRADES_FOR_BEST. `!Number.isFinite` keeps a no-losing-trade run (PF ∞) eligible.
      const ranked = standalone
        .filter(
          (r) =>
            r.status === 'complete' &&
            r.profit_factor != null &&
            (r.trade_count ?? 0) >= MIN_TRADES_FOR_BEST
        )
        .sort((a, b) => {
          const pf = (r: BacktestSummary) =>
            Number.isFinite(r.profit_factor!) ? r.profit_factor! : Infinity
          return pf(b) - pf(a)
        })
      return {
        totalStandaloneRuns: standalone.length,
        latestBacktest: standalone[0] ?? null,
        bestRun: ranked[0] ?? null,
        tier1Count: standalone.filter((r) => r.worthiness?.tier === 'TIER_1_STRESS_TEST').length,
        runningBacktests: standalone.filter((r) => r.status === 'running').length,
      }
    }, [backtestRuns])

  const totalOptimizations = optimizations?.length ?? 0
  const runningOpt = optimizations?.find((o) => o.status === 'running') ?? null

  const { robustCount, bestGrade, runningStressTest } = useMemo(() => {
    const GRADE_ORDER = ['A', 'B', 'C', 'D', 'F']
    const completed = stressTests?.filter((s) => s.grade != null) ?? []
    return {
      robustCount: completed.filter((s) => s.grade === 'A' || s.grade === 'B').length,
      bestGrade: (completed.length > 0
        ? completed.reduce(
            (best, s) =>
              GRADE_ORDER.indexOf(s.grade!) < GRADE_ORDER.indexOf(best) ? s.grade! : best,
            'F' as 'A' | 'B' | 'C' | 'D' | 'F'
          )
        : null) as 'A' | 'B' | 'C' | 'D' | 'F' | null,
      runningStressTest: stressTests?.some((s) => s.status.startsWith('running')) ?? false,
    }
  }, [stressTests])

  const bots = snapshot?.bots ?? []
  const runningBots = bots.filter((b) => b.status === 'RUNNING').length
  const totalBots = bots.length
  // A bot whose process is alive but whose terminal is not answering. It is RUNNING and it is
  // trading nothing, so a stat card calling the fleet healthy is wrong — see `NoLinkChip`.
  const blindBots = bots.filter((b) => b.mt5_link === false).length
  // ⚠ Sum only what was actually REPORTED, and say how many were not. `?? 0` folds "this bot
  // could not tell me" into the total as a real zero, which understates the fleet with nothing
  // on screen to show for it — the same "no data ≠ cannot ask" rule the link chip exists for.
  const reportedBal = bots.filter((b) => b.balance != null)
  const totalBalance = reportedBal.reduce((s, b) => s + (b.balance ?? 0), 0)
  const unreported = totalBots - reportedBal.length
  const liveBots = bots.filter((b) => b.account_type === 'live').length
  const accountLabel =
    totalBots === 0
      ? ''
      : liveBots === 0
        ? 'demo account'
        : liveBots === totalBots
          ? 'live account'
          : `${liveBots} live · ${totalBots - liveBots} demo`
  // TanStack keeps the last good snapshot through a failed refetch, so an error and real rows
  // render together. Say WHEN the rows were true rather than leaving them looking live.
  const snapshotStale = botsError && !!snapshot

  const pipelineRunning = progress?.status === 'running'

  // Economic calendar — a preview of what's still to come this week (whole week fetched, filtered
  // here). ⚠ The window is recomputed EVERY RENDER, not memoized on `[]`: this dashboard is left
  // open for days, and a window frozen at mount stops being "this week" the moment the clock
  // passes Monday midnight — after which the card reads "no more events this week" for ever
  // while the Calendar page, which recomputes, is right.
  const calFrom = localWeekStart(0)
  const calTo = localWeekEnd(calFrom)
  // 5 min, not the page's 45s: this preview shows a title, a time and an impact dot, none of
  // which change once an event is published. It re-pulls the whole 33 KB week either way.
  const {
    data: calendar,
    isError: calError,
    dataUpdatedAt: calUpdatedAt,
  } = useCalendar(calFrom, calTo, 300_000)
  // Ticks every second off the SERVER's clock, which is also what advances `calFrom` past
  // midnight. Reading `server_now_ms` straight from the response freezes "now" between polls,
  // so the countdown sits still and a fired event stays listed as upcoming.
  const calNow = useServerClock(calendar?.server_now_ms)
  const upcoming = (calendar?.events ?? []).filter((e) => e.timestamp_ms > calNow)
  const nextHigh = upcoming.find((e) => e.impact === 'HIGH') ?? null
  const upcomingList = upcoming.filter((e) => e !== nextHigh).slice(0, 6)
  // The Calendar page keeps the selected day in the URL (0 = Monday), so a click can land on
  // the day the event is on instead of dumping the reader on the current week.
  // ⚠ `dayIndexOf` is the SHARED one in `lib/calendar.ts`, not a private copy. This page WRITES the
  // index the Calendar page READS, so two definitions is two ways to answer one question.
  const goToEvent = (ts: number) => navigate(`/calendar?day=${weekDayIndex(ts, calFrom)}`)

  return (
    <div>
      <h1 className="text-h1 font-semibold mb-[18px]">Overview</h1>

      {/* ── Silent-failure warnings ───────────────────────────────────────────
          The dependencies that break by doing NOTHING: an un-backfilled news calendar makes the
          News & Holiday filter tag zero trades (indistinguishable from a filter that works and
          found none), and missing credentials make every Telegram send a no-op. Neither raises,
          neither is visible anywhere else in the app, and both are exactly what this page is for.

          ⚠ It renders only when there is something to say. A card reading "all dependencies OK"
          is a permanent green tick that teaches the reader to stop looking at this spot — and
          this is the one row that must be read on the day it finally says something. */}
      {readiness && readiness.warnings.length > 0 && (
        <div className="mb-5 rounded-lg border border-warn-text/25 bg-warn-muted px-[15px] py-[11px]">
          <div className="flex items-center gap-[7px] mb-[6px]">
            <AlertCircle size={13} className="text-warn-text flex-shrink-0" />
            <span className="text-[11px] font-semibold uppercase tracking-[0.7px] text-warn-text">
              {readiness.warnings.length === 1
                ? 'A dependency is degraded'
                : `${readiness.warnings.length} dependencies are degraded`}
            </span>
          </div>
          <ul className="space-y-[3px]">
            {readiness.warnings.map((w) => (
              // Keyed on the message: the backend returns a list of sentences with no ids, and
              // the sentence IS the finding — two identical ones would be one finding twice.
              <li key={w} className="text-[12px] text-text-secondary leading-[1.45] pl-[20px]">
                {w}
              </li>
            ))}
          </ul>
          <p className="text-[11px] text-text-tertiary mt-[7px] pl-[20px]">
            These fail by doing nothing, so nothing else will report them.
          </p>
        </div>
      )}

      {/* ── Stat Row ──────────────────────────────────────────────────────────── */}
      {/* Column count follows what is actually rendered — two cards in a 4-column
          grid leaves half the row blank, which reads as data that failed to load. */}
      <div className={`grid ${smartMoney ? 'grid-cols-4' : 'grid-cols-2'} gap-[10px] mb-5`}>
        <StatCard
          label="Bots Running"
          value={botsLoading ? '—' : `${runningBots} / ${totalBots}`}
          sub={
            botsLoading
              ? 'connecting…'
              : snapshotStale
                ? `VPS unreachable — as of ${fmtTime(new Date(snapshot!.fetched_at).getTime())}`
                : botsError
                  ? 'VPS unreachable'
                  : !snapshot
                    ? 'no data'
                    : // ⚠ Order matters. A blind bot is RUNNING, so any healthy-sounding line below would
                      // win the tie and the fleet would read green while it traded nothing.
                      blindBots > 0
                      ? `${blindBots} running with no MT5 link`
                      : totalBots === 0
                        ? 'none registered' // `runningBots === totalBots` is TRUE at 0/0
                        : runningBots === totalBots
                          ? 'all bots live'
                          : runningBots === 0
                            ? 'all stopped'
                            : `${totalBots - runningBots} stopped`
          }
          subVariant={
            botsLoading || botsError || !snapshot
              ? 'neutral'
              : blindBots > 0
                ? 'warn'
                : totalBots === 0
                  ? 'neutral'
                  : runningBots === totalBots
                    ? 'pos'
                    : runningBots === 0
                      ? 'neg'
                      : 'neutral'
          }
          onClick={() => navigate('/bots')}
        />

        <StatCard
          label="Balance"
          value={botsLoading ? '—' : reportedBal.length > 0 ? fmt$(totalBalance) : '—'}
          sub={
            botsLoading
              ? ''
              : botsError
                ? 'unavailable'
                : totalBots === 0
                  ? 'no bots registered'
                  : // A missing balance is not a zero balance. Name the gap rather than quietly summing
                    // the bots that answered and presenting it as the fleet total.
                    unreported > 0
                    ? `${unreported} of ${totalBots} not reporting`
                    : accountLabel
          }
          subVariant={
            !botsLoading && !botsError && unreported > 0 && totalBots > 0 ? 'warn' : 'neutral'
          }
          onClick={() => navigate('/bots')}
        />

        {smartMoney && (
          <>
            <StatCard
              label="Last Scan"
              value={latestRun ? relativeTime(latestRun.generated_at, calNow) : '—'}
              sub={latestRun ? `run ${latestRun.run_id.slice(0, 8)}…` : 'no runs yet'}
              onClick={() => navigate('/smart-money')}
            />

            <StatCard
              label="Candidates"
              value={latestRun ? String(latestRun.total_qualified) : '—'}
              sub={pipelineRunning ? 'scan in progress' : latestRun ? 'from last run' : 'no data'}
              subVariant={latestRun && latestRun.total_qualified > 0 ? 'pos' : 'neutral'}
              onClick={() => navigate('/smart-money')}
            />
          </>
        )}
      </div>

      {/* ── Module Cards ──────────────────────────────────────────────────────── */}
      <div className={`grid ${smartMoney ? 'grid-cols-3' : 'grid-cols-2'} gap-[14px]`}>
        {/* ── Bots ──────────────────────────────────────────────── */}
        <div className="bg-bg-surface border border-border-subtle rounded-lg overflow-hidden">
          {/* Card header — navigates to Bots page */}
          <button
            onClick={() => navigate('/bots')}
            className="w-full flex items-center justify-between px-[15px] py-[10px] border-b border-border-subtle hover:bg-bg-hover transition-colors duration-[120ms] group"
          >
            <div className="flex items-center gap-[8px]">
              <Bot size={14} className="text-accent" style={{ opacity: 0.85 }} />
              <span className="text-[11px] font-semibold uppercase tracking-[0.7px] text-text-secondary">
                Bots
              </span>
            </div>
            <div className="flex items-center gap-[6px] text-[11px] text-text-tertiary group-hover:text-text-secondary transition-colors">
              <span>View all</span>
              <ChevronRight size={12} />
            </div>
          </button>

          <div className="px-[15px] py-[10px]">
            {botsLoading && <BotsCardSkeleton />}

            {/* A failed refetch leaves the LAST GOOD snapshot on screen — so this says how old
                these rows are instead of letting them read as live. With no snapshot at all it
                is the plain failure. */}
            {botsError &&
              !botsLoading &&
              (snapshotStale ? (
                <p className="flex items-center gap-[6px] text-[11px] text-warn-text mb-[6px] px-[8px] py-[5px] rounded-md bg-warn-muted border border-warn-text/20">
                  <AlertCircle size={11} className="flex-shrink-0" />
                  VPS unreachable — showing the snapshot from{' '}
                  {fmtTime(new Date(snapshot!.fetched_at).getTime())}
                </p>
              ) : (
                <p className="text-[12px] text-neg-text py-3">
                  VPS connection failed — check SSH access.
                </p>
              ))}

            {snapshot && (
              <>
                {/* Keyed by `key`, never `name`: a name is a label chosen for a human and two
                    bots may share one. */}
                {snapshot.bots.map((bot) => (
                  <BotRow key={bot.key} bot={bot} />
                ))}

                {snapshot.bots.length === 0 && (
                  <p className="text-[12px] text-text-tertiary py-2">No bots registered.</p>
                )}

                <div className="mt-[10px] pt-[9px] border-t border-border-subtle/40">
                  <p className="text-[11px] text-text-tertiary leading-none mb-[5px] uppercase tracking-[0.5px]">
                    Scheduled
                  </p>
                  <div className="flex flex-wrap gap-y-[3px]">
                    {snapshot.scheduled_jobs.map((j) => (
                      <JobPill key={j.name} job={j} />
                    ))}
                    <JobPill job={snapshot.telegram} />
                  </div>
                </div>
              </>
            )}
          </div>
        </div>

        {/* ── Smart Money ───────────────────────────────────────── */}
        {smartMoney && (
          <div className="bg-bg-surface border border-border-subtle rounded-lg overflow-hidden">
            {/* Card header — navigates to Smart Money page */}
            <button
              onClick={() => navigate('/smart-money')}
              className="w-full flex items-center justify-between px-[15px] py-[10px] border-b border-border-subtle hover:bg-bg-hover transition-colors duration-[120ms] group"
            >
              <div className="flex items-center gap-[8px]">
                <Radar size={14} className="text-accent" style={{ opacity: 0.85 }} />
                <span className="text-[11px] font-semibold uppercase tracking-[0.7px] text-text-secondary">
                  Smart Money
                </span>
              </div>
              <div className="flex items-center gap-[6px] text-[11px] text-text-tertiary group-hover:text-text-secondary transition-colors">
                <span>View scanner</span>
                <ChevronRight size={12} />
              </div>
            </button>

            <div className="px-[15px] py-[12px]">
              {/* Pipeline running banner */}
              {pipelineRunning && (
                <div className="flex items-center gap-[8px] mb-[12px] px-[10px] py-[7px] rounded-md bg-accent-muted border border-accent/20 text-[12px] text-accent-text">
                  <span className="relative flex h-[8px] w-[8px] flex-shrink-0">
                    <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-accent opacity-60" />
                    <span className="relative inline-flex rounded-full h-[8px] w-[8px] bg-accent" />
                  </span>
                  <span>
                    Scan running — {progress!.pct}% · {progress!.stage_name}
                    {progress!.qualified_so_far > 0 && ` · ${progress!.qualified_so_far} found`}
                  </span>
                </div>
              )}

              {latestRun ? (
                <div className="space-y-[10px]">
                  <div className="flex items-baseline justify-between">
                    <span className="text-[12px] text-text-tertiary">Last run</span>
                    <span className="text-[13px] text-text-primary">
                      {relativeTime(latestRun.generated_at, calNow)}
                    </span>
                  </div>
                  <div className="flex items-center justify-between">
                    <span className="text-[12px] text-text-tertiary">Candidates found</span>
                    <span className="text-[26px] font-semibold tracking-tight leading-none text-pos-text">
                      {latestRun.total_qualified}
                    </span>
                  </div>
                  <div className="flex items-baseline justify-between">
                    <span className="text-[12px] text-text-tertiary">Run ID</span>
                    <span className="text-[11px] font-mono text-text-tertiary">
                      {latestRun.run_id.slice(0, 18)}…
                    </span>
                  </div>

                  {runs && runs.length > 1 && (
                    <div className="pt-[8px] border-t border-border-subtle/40">
                      <span className="text-[11px] text-text-tertiary">
                        {runs.length} historical runs available
                      </span>
                    </div>
                  )}
                </div>
              ) : (
                <div className="py-4 text-center">
                  <p className="text-[13px] text-text-tertiary">No runs yet</p>
                  <p className="text-[11px] text-text-tertiary/60 mt-[4px]">
                    Go to Smart Money to run a scan
                  </p>
                </div>
              )}
            </div>
          </div>
        )}

        {/* ── Research ──────────────────────────────────────── */}
        <div className="bg-bg-surface border border-border-subtle rounded-lg overflow-hidden">
          <button
            onClick={() => navigate('/backtests?tab=runs')}
            className="w-full flex items-center justify-between px-[15px] py-[10px] border-b border-border-subtle hover:bg-bg-hover transition-colors duration-[120ms] group"
          >
            <div className="flex items-center gap-[8px]">
              <FlaskConical size={14} className="text-accent" style={{ opacity: 0.85 }} />
              <span className="text-[11px] font-semibold uppercase tracking-[0.7px] text-text-secondary">
                Research
              </span>
            </div>
            <div className="flex items-center gap-[6px] text-[11px] text-text-tertiary group-hover:text-text-secondary transition-colors">
              <span>Open runs</span>
              <ChevronRight size={12} />
            </div>
          </button>

          <div className="px-[15px] py-[10px]">
            {/* Running backtest banner. Optimizations and stress tests each had one; a plain
                backtest — the most common job on the box — announced itself nowhere, because
                its status pill only rendered in the branch where no best run exists. */}
            {runningBacktests > 0 && (
              <div className="flex items-center gap-[8px] px-[10px] py-[7px] rounded-md bg-accent-muted border border-accent/20 text-[12px] text-accent mb-[8px]">
                <Loader2 size={12} className="animate-spin flex-shrink-0" />
                <span>
                  {runningBacktests === 1
                    ? 'Backtest running…'
                    : `${runningBacktests} backtests running…`}
                </span>
              </div>
            )}

            {/* Running stress test banner */}
            {runningStressTest && (
              <div className="flex items-center gap-[8px] px-[10px] py-[7px] rounded-md bg-warn-muted border border-warn-text/20 text-[12px] text-warn-text mb-[8px]">
                <Loader2 size={12} className="animate-spin flex-shrink-0" />
                <span>Stress test running…</span>
              </div>
            )}

            {/* Running optimization banner */}
            {runningOpt && (
              <div className="flex items-center gap-[8px] px-[10px] py-[7px] rounded-md bg-accent-muted border border-accent/20 text-[12px] text-accent mb-[8px]">
                <Loader2 size={12} className="animate-spin flex-shrink-0" />
                <span>
                  Optimization running — {runningOpt.completed_runs}/{runningOpt.estimated_runs}{' '}
                  runs
                </span>
              </div>
            )}

            <NavStatRow
              icon={<BookOpen size={13} />}
              label="Strategies"
              onClick={() => navigate('/strategies')}
            >
              <span className="text-[13px] font-mono text-text-primary">
                {totalStrategies > 0 ? totalStrategies : '—'}
              </span>
            </NavStatRow>

            <NavStatRow
              icon={<ClipboardList size={13} />}
              label="Rulesets"
              onClick={() => navigate('/rulesets')}
            >
              {rulesets && rulesets.length > 0 ? (
                <span className="text-[11px] font-mono text-text-tertiary">
                  {propRulesets} prop · {personalRulesets} personal
                </span>
              ) : (
                <span className="text-[13px] font-mono text-text-primary">—</span>
              )}
            </NavStatRow>

            <NavStatRow
              icon={<BarChart2 size={13} />}
              label="Runs"
              onClick={() => navigate('/backtests?tab=runs')}
            >
              {runningBacktests > 0 && (
                <span className="w-[6px] h-[6px] rounded-full bg-accent animate-pulse" />
              )}
              {bestRun ? (
                <span className="text-[11px] font-mono text-text-tertiary">
                  {totalStandaloneRuns} · best PF {fmtPf(bestRun.profit_factor)}
                </span>
              ) : latestBacktest ? (
                <BacktestStatusPill status={latestBacktest.status} />
              ) : (
                <span className="text-[13px] font-mono text-text-primary">
                  {totalStandaloneRuns > 0 ? totalStandaloneRuns : '—'}
                </span>
              )}
            </NavStatRow>

            <NavStatRow
              icon={<Sliders size={13} />}
              label="Optimizations"
              onClick={() => navigate('/optimizations')}
            >
              {runningOpt && (
                <span className="w-[6px] h-[6px] rounded-full bg-accent animate-pulse" />
              )}
              <span className="text-[13px] font-mono text-text-primary">
                {totalOptimizations > 0 ? totalOptimizations : '—'}
              </span>
            </NavStatRow>

            <NavStatRow
              icon={<Activity size={13} />}
              label="Stress Tests"
              onClick={() => navigate('/stress-tests')}
            >
              {runningStressTest && (
                <span className="w-[6px] h-[6px] rounded-full bg-warn-text animate-pulse" />
              )}
              {robustCount > 0 && (
                <span className="text-[11px] text-pos-text font-mono">{robustCount} robust</span>
              )}
              {bestGrade ? (
                <RobustnessGradeBadge grade={bestGrade} size="sm" />
              ) : (
                <span className="text-[13px] font-mono text-text-primary">—</span>
              )}
            </NavStatRow>

            {(tier1Count > 0 || bestRun) && (
              <div className="mt-[8px] pt-[8px] border-t border-border-subtle/40 space-y-[8px]">
                {tier1Count > 0 && (
                  <div className="flex items-center justify-between px-[1px]">
                    <span className="text-[12px] text-text-tertiary">Tier 1 passes</span>
                    <span className="text-[13px] font-mono font-semibold text-pos-text">
                      {tier1Count}
                    </span>
                  </div>
                )}
                {bestRun && (
                  <button
                    onClick={() => navigate(`/backtests/runs/${bestRun.run_id}`)}
                    className="w-full flex items-center justify-between py-[6px] px-[8px] -mx-[8px] rounded-md hover:bg-bg-hover transition-colors group"
                  >
                    <span className="text-[12px] text-text-tertiary group-hover:text-text-primary transition-colors">
                      Best result
                    </span>
                    <div className="flex items-center gap-2">
                      {/* The sample is stated beside the ratio, because profit factor on its own
                          says nothing about how much history is behind it. */}
                      <span className="text-[11px] font-mono text-text-tertiary">
                        {bestRun.trade_count} trades
                      </span>
                      <span className="text-[12px] font-mono font-semibold text-text-primary">
                        PF {fmtPf(bestRun.profit_factor)}
                      </span>
                      <WorthinessBadge worthiness={bestRun.worthiness} size="sm" />
                      <ChevronRight
                        size={12}
                        className="text-text-tertiary/60 group-hover:text-text-secondary transition-colors"
                      />
                    </div>
                  </button>
                )}
              </div>
            )}
          </div>
        </div>
      </div>

      {/* ── Economic Calendar preview ─────────────────────────────────────────── */}
      <div className="mt-[14px] bg-bg-surface border border-border-subtle rounded-lg overflow-hidden">
        <button
          onClick={() => navigate('/calendar')}
          className="w-full flex items-center justify-between px-[15px] py-[10px] border-b border-border-subtle hover:bg-bg-hover transition-colors duration-[120ms] group"
        >
          <div className="flex items-center gap-[8px]">
            <CalendarDays size={14} className="text-accent" style={{ opacity: 0.85 }} />
            <span className="text-[11px] font-semibold uppercase tracking-[0.7px] text-text-secondary">
              Economic Calendar
            </span>
          </div>
          <div className="flex items-center gap-[6px] text-[11px] text-text-tertiary group-hover:text-text-secondary transition-colors">
            <span>View calendar</span>
            <ChevronRight size={12} />
          </div>
        </button>

        <div className="px-[15px] py-[12px]">
          {nextHigh && (
            <button
              onClick={() => goToEvent(nextHigh.timestamp_ms)}
              className="w-full flex items-center gap-[8px] mb-[10px] px-[10px] py-[7px] rounded-md bg-accent-muted border border-accent/20 text-left hover:bg-accent/10 transition-colors"
            >
              <span className="text-[10px] font-semibold uppercase tracking-[0.5px] text-accent flex-shrink-0">
                Next high-impact
              </span>
              <span className="text-base leading-none flex-shrink-0" title={nextHigh.currency}>
                {flagOf(nextHigh.currency)}
              </span>
              <span className="text-[12px] text-text-primary truncate flex-1 min-w-0">
                {nextHigh.title}
              </span>
              <span className="text-[11px] font-mono tabular-nums text-accent flex-shrink-0">
                in {fmtCountdown(nextHigh.timestamp_ms - calNow)}
              </span>
            </button>
          )}

          {/* A failed fetch must not render as "Loading…" for ever — the feed is a third party and
              it does go down. But a failed REFRESH over a week already on screen must not delete
              it either: those rows were true, so they stay and the notice DATES them. Only a
              failure with nothing to show takes the card. Same rule as the bot snapshot above. */}
          {calError && !calendar ? (
            <p className="flex items-center justify-center gap-[6px] text-[12px] text-neg-text py-2">
              <AlertCircle size={12} className="flex-shrink-0" />
              Calendar unavailable — the feed did not answer.
            </p>
          ) : !calendar ? (
            <p className="text-[12px] text-text-tertiary py-2 text-center">Loading…</p>
          ) : calError ? (
            <>
              <p className="flex items-center gap-[6px] text-[11px] text-warn-text mb-[6px]">
                <AlertCircle size={11} className="flex-shrink-0" />
                Feed didn't answer the last refresh — as of{' '}
                <span className="font-mono tabular-nums">{fmtTime(calUpdatedAt)}</span>.
              </p>
              <CalendarUpcoming events={upcomingList} onPick={goToEvent} />
            </>
          ) : upcomingList.length === 0 ? (
            // Not `upcoming.length` — with the only remaining event promoted into the callout
            // above, that test passes and renders an empty grid: a blank strip under the banner.
            <p className="text-[12px] text-text-tertiary py-2 text-center">
              {upcoming.length === 0 ? 'No more events this week' : 'Nothing else this week'}
            </p>
          ) : (
            <CalendarUpcoming events={upcomingList} onPick={goToEvent} />
          )}
        </div>
      </div>
    </div>
  )
}

/** The preview's upcoming-event grid. Extracted so the healthy branch and the stale-after-error
 *  branch render ONE list — two copies is two places for the row markup to drift. */
function CalendarUpcoming({
  events,
  onPick,
}: {
  events: CalendarEvent[]
  onPick: (ts: number) => void
}) {
  return (
    // The bleed for the rows' hover fill lives on the CONTAINER, not on each row. A grid ITEM
    // cannot carry a negative margin without escaping its own track — the rows had `-mx-[6px]`
    // and the grid overflowed by exactly 6px at every width, hover fill included, since a track
    // is sized before the margin is applied.
    <div className="grid grid-cols-2 gap-x-6 gap-y-[2px] -mx-[6px]">
      {/* ⚠ The position is part of the key: `(time, currency, title)` is NOT unique in real feed
          data (two `CAD Budget Balance` rows share a timestamp), and a duplicate key is how React
          silently drops or mis-reuses a row. Same fix on the Calendar page. */}
      {events.map((e, i) => (
        <button
          key={`${e.timestamp_ms}|${e.currency}|${e.title}|${i}`}
          onClick={() => onPick(e.timestamp_ms)}
          className="flex items-center gap-[8px] py-[5px] px-[6px] min-w-0 rounded-md hover:bg-bg-hover transition-colors text-left group"
        >
          <span className="text-[11px] font-mono tabular-nums text-text-tertiary w-[42px] flex-shrink-0">
            {fmtTime(e.timestamp_ms)}
          </span>
          <span className="text-sm leading-none flex-shrink-0" title={e.currency}>
            {flagOf(e.currency)}
          </span>
          <span
            className={`inline-block w-[7px] h-[7px] rounded-full flex-shrink-0 ${IMPACT_DOT[e.impact]}`}
            title={`${IMPACT_LABEL[e.impact]} impact`}
          />
          <span className="text-[12px] text-text-secondary group-hover:text-text-primary transition-colors truncate flex-1 min-w-0">
            {e.title}
          </span>
        </button>
      ))}
    </div>
  )
}
