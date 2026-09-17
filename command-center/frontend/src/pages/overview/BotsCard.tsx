import { useNavigate } from 'react-router-dom'
import { Bot, ChevronRight, AlertCircle } from 'lucide-react'
import { useRegisteredAccounts } from '@/hooks/useBots'
import { botCondition } from '@/lib/botCondition'
import { fmtTime } from '@/lib/calendar'
import { StatusText } from '@/components/BotStatus'
import { Shimmer } from '@/components/Shimmer'
import type { BotStatus } from '@/types'

/**
 * The Overview's bot list, GROUPED BY ACCOUNT (redesign 2026-09-16).
 *
 * 🔴 **It was one flat list, and a live and a demo copy share a display name** — on the day it was
 * redrawn it read "SOS Fade LIVE" twice with nothing to say which account either was on, and the
 * same return printed on every bot of an account as though each had earned it. Balance and return
 * are ACCOUNT facts (every bot on one reports the same figure), so they now sit once on the
 * account's header, and a bot row says only what is the bot's own: its name and its state.
 *
 * ⚠ Live accounts first, then demo, then the bots on no account — the order a reader's worry runs.
 */

type Snapshot = {
  bots: BotStatus[]
  fetched_at: string
  scheduled_jobs: { name: string; status: string; schedule?: string }[]
  telegram: { name: string; status: string; schedule?: string }
}

interface AccountGroup {
  account: string
  kind: 'live' | 'demo'
  label: string | null
  bots: BotStatus[]
  /** `null` = no bot on it could report — never $0. */
  balance: number | null
  pnlPct: number | null
}

function fmt$(n: number): string {
  return '$' + n.toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 })
}

function fmtPct(n: number): string {
  return `${n >= 0 ? '+' : ''}${n.toFixed(2)}%`
}

/** One reading per account. A RUNNING bot's figure wins — a stopped one's is as old as its stop. */
function groupByAccount(bots: BotStatus[], labels: Map<string, string>): AccountGroup[] {
  const map = new Map<string, BotStatus[]>()
  for (const b of bots) {
    if (!b.account) continue
    map.set(b.account, [...(map.get(b.account) ?? []), b])
  }
  const pick = (rows: BotStatus[], f: (b: BotStatus) => number | null) => {
    const running = rows.find((b) => b.status === 'RUNNING' && f(b) != null)
    const any = rows.find((b) => f(b) != null)
    return running ? f(running) : any ? f(any) : null
  }
  return [...map.entries()]
    .map(([account, rows]) => ({
      account,
      kind: rows.some((b) => b.account_type === 'live') ? ('live' as const) : ('demo' as const),
      label: labels.get(account) ?? null,
      bots: rows,
      balance: pick(rows, (b) => b.balance),
      pnlPct: pick(rows, (b) => b.total_pnl_pct),
    }))
    .sort((a, b) => (a.kind === b.kind ? 0 : a.kind === 'live' ? -1 : 1))
}

function KindTag({ kind }: { kind: 'live' | 'demo' }) {
  return (
    <span
      className={`text-[9px] font-semibold px-[5px] py-[1px] rounded-pill uppercase tracking-[0.4px] flex-shrink-0 ${
        kind === 'live' ? 'bg-warn-muted text-warn-text' : 'bg-bg-sunken text-text-tertiary'
      }`}
    >
      {kind}
    </span>
  )
}

/** A bot: its name and its one-word state (`lib/botCondition.ts`, shared with the Bots page). */
function BotRow({ bot }: { bot: BotStatus }) {
  const cond = botCondition(bot, { asked: true, onAccount: !!bot.account })
  return (
    <div className="flex items-center gap-[10px] py-[5px] pl-[12px]">
      <span className="text-[13px] text-text-primary min-w-0 truncate flex-1">{bot.name}</span>
      <StatusText cond={cond} size="list" />
    </div>
  )
}

function AccountBlock({ group }: { group: AccountGroup }) {
  const pnlColor =
    group.pnlPct == null
      ? ''
      : group.pnlPct > 0
        ? 'text-pos-text'
        : group.pnlPct < 0
          ? 'text-neg-text'
          : 'text-text-tertiary'
  return (
    <div
      data-testid="account-block"
      className={`rounded-md border px-[10px] py-[7px] ${
        group.kind === 'live' ? 'border-warn-text/25' : 'border-border-subtle/60'
      }`}
    >
      <div className="flex items-center gap-[8px] pb-[4px] mb-[2px] border-b border-border-subtle/40">
        <KindTag kind={group.kind} />
        <span className="text-[12px] text-text-secondary min-w-0 truncate flex-1">
          {group.label || `Account ${group.account}`}
          {group.label && (
            <span className="text-text-tertiary font-mono ml-[6px]">{group.account}</span>
          )}
        </span>
        {group.pnlPct != null && (
          <span className={`text-[11px] font-mono tabular-nums ${pnlColor}`}>
            {fmtPct(group.pnlPct)}
          </span>
        )}
        {group.balance != null ? (
          <span className="text-[13px] font-mono tabular-nums text-text-primary">
            {fmt$(group.balance)}
          </span>
        ) : (
          <span className="text-[11px] text-warn-text">not reporting</span>
        )}
      </div>
      {group.bots.map((b) => (
        <BotRow key={b.key} bot={b} />
      ))}
    </div>
  )
}

/** ⚠ A job that will never fire is dimmed and struck through; a waiting one is plain text — six
 *  gold names on every visit read as six warnings (2026-09-11). Mirrors `JobDot` on the Bots page. */
function JobPill({ job }: { job: { name: string; status: string; schedule?: string } }) {
  const running = job.status === 'RUNNING'
  const disabled = job.status === 'DISABLED'
  const dotCls = running ? 'bg-pos' : disabled ? 'bg-text-tertiary/30' : 'bg-text-secondary/60'
  const textCls = disabled ? 'text-text-tertiary line-through' : 'text-text-secondary'
  const state = running
    ? 'Running'
    : disabled
      ? 'Disabled — will not run until re-enabled on the VPS'
      : 'Scheduled — waiting for next trigger'
  const tip = job.schedule ? `${state}\nRuns ${job.schedule}` : state
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

/** Shaped like three account blocks — "no text beside a shimmer" (frontend/CLAUDE.md). */
function Skeleton() {
  return (
    <div className="space-y-[8px]">
      {[...Array(3)].map((_, i) => (
        <Shimmer key={i} className="block h-[58px] w-full rounded-md" />
      ))}
    </div>
  )
}

export function BotsCard({
  snapshot,
  isLoading,
  isError,
}: {
  snapshot: Snapshot | undefined
  isLoading: boolean
  isError: boolean
}) {
  const navigate = useNavigate()
  const { data: registry } = useRegisteredAccounts()
  const labels = new Map((registry ?? []).map((a) => [String(a.account), a.label]))

  const bots = snapshot?.bots ?? []
  const groups = groupByAccount(bots, labels)
  const benched = bots.filter((b) => !b.account)

  // ⚠ Summed per ACCOUNT, never per bot (2026-09-11: two bots on one account read double), and
  // only what was REPORTED — a silent account is named, never folded in as $0.
  const reported = groups.filter((g) => g.balance != null)
  const total = reported.reduce((s, g) => s + g.balance!, 0)
  const unreported = groups.length - reported.length
  const live = groups.filter((g) => g.kind === 'live').length
  const demo = groups.length - live
  const mix = [live && `${live} live`, demo && `${demo} demo`].filter(Boolean).join(' · ')
  const accountsWord = `account${groups.length === 1 ? '' : 's'}`
  // TanStack keeps the last good snapshot through a failed refetch — date it, never pass it as live.
  const stale = isError && !!snapshot

  return (
    <div className="bg-bg-surface border border-border-subtle rounded-lg overflow-hidden">
      <button
        onClick={() => navigate('/bots')}
        className="w-full flex items-center justify-between px-[15px] py-[10px] border-b border-border-subtle hover:bg-bg-hover transition-colors duration-[120ms] group"
      >
        <div className="flex items-center gap-[8px]">
          <Bot size={14} className="text-text-tertiary" />
          <span className="text-[11px] font-semibold uppercase tracking-[0.7px] text-text-secondary">
            Bots by account
          </span>
        </div>
        <div className="flex items-center gap-[6px] text-[11px] text-text-tertiary group-hover:text-text-secondary transition-colors">
          <span>Manage</span>
          <ChevronRight size={12} />
        </div>
      </button>

      <div className="px-[15px] py-[12px]">
        {isLoading && <Skeleton />}

        {isError &&
          !isLoading &&
          (stale ? (
            <p className="flex items-center gap-[6px] text-[11px] text-warn-text mb-[8px] px-[8px] py-[5px] rounded-md bg-warn-muted border border-warn-text/20">
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
            {groups.length > 0 && (
              <div
                data-testid="fleet-balance"
                className="flex items-baseline gap-[10px] pb-[10px] mb-[10px] border-b border-border-subtle/40"
              >
                <span className="text-[12px] text-text-tertiary">Total balance</span>
                <span
                  className={`text-[11px] flex-1 ${unreported > 0 ? 'text-warn-text' : 'text-text-tertiary'}`}
                >
                  {unreported > 0
                    ? `${unreported} of ${groups.length} ${accountsWord} not reporting`
                    : mix}
                </span>
                <span className="text-[18px] font-semibold font-mono tabular-nums text-text-primary">
                  {reported.length > 0 ? fmt$(total) : '—'}
                </span>
              </div>
            )}

            <div className="space-y-[8px]">
              {groups.map((g) => (
                <AccountBlock key={g.account} group={g} />
              ))}
            </div>

            {benched.length > 0 && (
              <div className="mt-[10px]">
                <p className="text-[10px] uppercase tracking-[0.5px] text-text-tertiary mb-[2px]">
                  On no account
                </p>
                {benched.map((b) => (
                  <BotRow key={b.key} bot={b} />
                ))}
              </div>
            )}

            {bots.length === 0 && (
              <p className="text-[12px] text-text-tertiary py-2">No bots registered.</p>
            )}

            <div className="mt-[12px] pt-[10px] border-t border-border-subtle/40">
              <p className="text-[10px] text-text-tertiary leading-none mb-[6px] uppercase tracking-[0.5px]">
                Background jobs on the VPS
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
  )
}
