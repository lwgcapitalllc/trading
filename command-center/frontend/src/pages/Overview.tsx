import { useNavigate } from 'react-router-dom'
import { Bot, Radar, ChevronRight } from 'lucide-react'
import { useBotSnapshot } from '@/hooks/useBots'
import { useSmartMoneyRuns, useRunProgress } from '@/hooks/useSmartMoney'
import { StatCard } from '@/components/StatCard'
import type { BotStatus } from '@/types'

// ── Helpers ────────────────────────────────────────────────────────────────────

function relativeTime(dt: string | Date): string {
  const diff = Date.now() - new Date(dt).getTime()
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

// ── Sub-components ─────────────────────────────────────────────────────────────

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

function BotRow({ bot }: { bot: BotStatus }) {
  const pnl = bot.daily_pnl_pct
  const pnlStr = pnl != null
    ? (pnl >= 0 ? `+${pnl.toFixed(2)}%` : `${pnl.toFixed(2)}%`)
    : null
  const pnlColor =
    pnl == null ? '' :
    pnl > 0  ? 'text-pos-text' :
    pnl < 0  ? 'text-neg-text' :
               'text-text-tertiary'

  return (
    <div className="flex items-center gap-[10px] py-[7px] border-b border-border-subtle/40 last:border-0">
      <span className="text-[13px] text-text-primary flex-1 min-w-0 truncate">{bot.name}</span>
      {pnlStr && (
        <span className={`text-[11px] font-mono tabular-nums ${pnlColor}`}>{pnlStr}</span>
      )}
      {bot.day_locked && (
        <span className="text-[9px] font-semibold px-[5px] py-[1px] rounded-pill bg-warn-muted text-warn-text uppercase tracking-[0.4px]">
          locked
        </span>
      )}
      <StatusPill status={bot.status} />
    </div>
  )
}

function JobPill({ job }: { job: { name: string; status: string } }) {
  const running = job.status === 'RUNNING'
  const dotCls  = running ? 'bg-pos shadow-[0_0_4px_#34d399]' : 'bg-gold shadow-[0_0_4px_#d9a441]'
  const textCls = running ? 'text-pos-text' : 'text-gold-text'
  const tip     = running ? 'Running' : 'Scheduled — waiting for next trigger'
  return (
    <span title={tip} className={`inline-flex items-center gap-[4px] mr-[10px] text-[11px] cursor-default ${textCls}`}>
      <span className={`inline-block w-[5px] h-[5px] rounded-full flex-shrink-0 ${dotCls}`} />
      {job.name}
    </span>
  )
}

function BotsCardSkeleton() {
  return (
    <div className="animate-pulse">
      {[...Array(4)].map((_, i) => (
        <div key={i} className="flex items-center gap-[10px] py-[7px] border-b border-border-subtle/40 last:border-0">
          <div className="w-[7px] h-[7px] rounded-full bg-bg-surface-2 flex-shrink-0" />
          <div className="h-[11px] bg-bg-surface-2 rounded flex-1" />
          <div className="h-[11px] w-[42px] bg-bg-surface-2 rounded" />
          <div className="h-[11px] w-[50px] bg-bg-surface-2 rounded" />
        </div>
      ))}
      <div className="flex items-center justify-center gap-[6px] mt-3 pt-3 border-t border-border-subtle/40 text-[11px] text-text-tertiary">
        <svg className="animate-spin h-[11px] w-[11px] text-accent" fill="none" viewBox="0 0 24 24">
          <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" />
          <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z" />
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
  const { data: runs } = useSmartMoneyRuns()
  const { data: progress } = useRunProgress()

  const latestRun = runs?.[0] ?? null

  const runningBots  = snapshot?.bots.filter(b => b.status === 'RUNNING').length ?? 0
  const totalBots    = snapshot?.bots.length ?? 0
  const totalBalance = snapshot?.bots.reduce((s, b) => s + (b.balance ?? 0), 0) ?? 0
  const accountType  = snapshot?.bots[0]?.account_type ?? 'demo'

  const pipelineRunning = progress?.status === 'running'

  return (
    <div>
      <div className="flex items-end gap-3 mb-[18px]">
        <h1 className="text-h1 font-semibold">Overview</h1>
      </div>

      {/* ── Stat Row ──────────────────────────────────────────────────────────── */}
      <div className="grid grid-cols-4 gap-[10px] mb-5">

        <StatCard
          label="Bots Running"
          value={botsLoading ? '—' : `${runningBots} / ${totalBots}`}
          sub={
            botsLoading ? 'connecting…' :
            botsError   ? 'VPS unreachable' :
            snapshot    ? (
              runningBots === totalBots ? 'all bots live' :
              runningBots === 0         ? 'all stopped' :
                                          `${totalBots - runningBots} stopped`
            ) : 'no data'
          }
          subVariant={
            botsLoading || botsError || !snapshot ? 'neutral' :
            runningBots === totalBots             ? 'pos' :
            runningBots === 0                     ? 'neg' :
                                                    'neutral'
          }
          onClick={() => navigate('/bots')}
        />

        <StatCard
          label="Balance"
          value={botsLoading ? '—' : totalBalance > 0 ? fmt$(totalBalance) : '—'}
          sub={
            botsLoading ? '' :
            botsError   ? 'unavailable' :
                          `${accountType} account`
          }
          onClick={() => navigate('/bots')}
        />

        <StatCard
          label="Last Scan"
          value={latestRun ? relativeTime(latestRun.generated_at) : '—'}
          sub={latestRun ? `run ${latestRun.run_id.slice(0, 8)}…` : 'no runs yet'}
          onClick={() => navigate('/smart-money')}
        />

        <StatCard
          label="Candidates"
          value={latestRun ? String(latestRun.total_qualified) : '—'}
          sub={
            pipelineRunning ? 'scan in progress' :
            latestRun       ? 'from last run' :
                              'no data'
          }
          subVariant={latestRun && latestRun.total_qualified > 0 ? 'pos' : 'neutral'}
          onClick={() => navigate('/smart-money')}
        />

      </div>

      {/* ── Module Cards ──────────────────────────────────────────────────────── */}
      <div className="grid grid-cols-2 gap-[14px]">

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

            {botsError && !botsLoading && (
              <p className="text-[12px] text-neg-text py-3">
                VPS connection failed — check SSH access.
              </p>
            )}

            {snapshot && (
              <>
                {snapshot.bots.map(bot => <BotRow key={bot.name} bot={bot} />)}

                <div className="mt-[10px] pt-[9px] border-t border-border-subtle/40">
                  <p className="text-[11px] text-text-tertiary leading-none mb-[5px] uppercase tracking-[0.5px]">
                    Scheduled
                  </p>
                  <div className="flex flex-wrap gap-y-[3px]">
                    {snapshot.scheduled_jobs.map(j => <JobPill key={j.name} job={j} />)}
                    <JobPill job={snapshot.telegram} />
                  </div>
                </div>
              </>
            )}
          </div>
        </div>

        {/* ── Smart Money ───────────────────────────────────────── */}
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
                  <span className="text-[13px] text-text-primary">{relativeTime(latestRun.generated_at)}</span>
                </div>
                <div className="flex items-center justify-between">
                  <span className="text-[12px] text-text-tertiary">Candidates found</span>
                  <span className="text-[26px] font-semibold tracking-tight leading-none text-pos-text">
                    {latestRun.total_qualified}
                  </span>
                </div>
                <div className="flex items-baseline justify-between">
                  <span className="text-[12px] text-text-tertiary">Run ID</span>
                  <span className="text-[11px] font-mono text-text-tertiary">{latestRun.run_id.slice(0, 18)}…</span>
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

      </div>
    </div>
  )
}
