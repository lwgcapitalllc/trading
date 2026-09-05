/**
 * Bots — one list, one drawer.
 *
 * 🔴 **This was four tabs, then two, and both were the same mistake: several views of the same
 * three objects.** Version, account, status, balance and risk each appeared in three places;
 * putting one bot on an account meant one tab to assign it, another to set how it trades and a
 * third to see whether it came up; every row of a stacked account repeated that account's balance,
 * which is what made the fleet total add one pot of money twice. Aaron, 2026-09-05: *"too much
 * information, too much duplication … make it very, very simple."*
 *
 * **The structure is the fix, and it is one sentence: accounts are headings, bots are rows, and
 * clicking either opens a drawer holding only what you can change.**
 *
 * ⚠ **Every number is stated once, on the thing it belongs to.** Balance, cap and account number
 * belong to the ACCOUNT and live on its heading. Version, risk and uptime belong to the BOT and
 * live on its row. Nothing is repeated to make a row look complete.
 *
 * ⚠ **State is a dot, not a word.** `RUNNING` was written on every row of every tab; the colour
 * carries it, and the drawer says it in words where there is room to be exact.
 *
 * ⚠ **Fleet controls and the scheduled jobs are NOT here** — they moved to Overview on
 * 2026-09-05. This page manages bots one at a time; those act on all of them or on the box, and
 * sitting the two together is what made each row's own buttons read like a fleet kill.
 *
 * ⚠ **An account with no bots collapses to one line.** It still has to be visible — you cannot
 * move a bot onto an account you cannot see — but it earns one line, not a card.
 */
import { useState, useEffect } from 'react'
import { useSearchParams } from 'react-router-dom'
import {
  FileText,
  Play,
  RotateCcw,
  Square,
  RefreshCw,
  Copy,
  Check,
  Unplug,
  AlertTriangle,
} from 'lucide-react'
import {
  useBotSnapshot,
  useBotAccounts,
  useRegisteredAccounts,
  useBotLog,
  useBotVersions,
  useUsers,
  useBotStartOne,
  useBotStopOne,
  useBotRestartOne,
} from '@/hooks/useBots'
import { VersionPill } from '@/components/VersionPill'
import type { BotStatus, BotReview, BotAccountGroup, BotAccountRegistration } from '@/types'
import { UsersTab } from './UsersTab'
import { BotDrawer } from './BotDrawer'
import { AccountDrawer } from './AccountDrawer'
import { AccountForm, nameOf } from './AccountsTab'

function formatUptime(seconds: number): string {
  if (seconds < 3600) return `${Math.floor(seconds / 60)}m`
  const h = Math.floor(seconds / 3600)
  const m = Math.floor((seconds % 3600) / 60)
  if (h >= 24) return `${Math.floor(h / 24)}d ${h % 24}h`
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

/** Running, but not talking to its terminal — both are true and they are different facts.
 *  ⚠ `=== false` and never falsy: `null` means the bot has not stamped a link state, and
 *  rendering an unanswered question as a failure is its own defect. */
function NoLinkChip() {
  return (
    <span
      title="The bot is running but its MT5 terminal is not answering, so it is receiving no bars. It retries every 30s; if this persists, restart it."
      className="inline-flex items-center gap-[3px] text-[10px] font-semibold px-[6px] py-[2px] rounded-pill uppercase tracking-[0.4px] bg-warn-muted text-warn-text cursor-default"
    >
      <Unplug size={9} /> no link
    </span>
  )
}

/** The hourly record review's standing flag. A Telegram alert is a MOMENT; this is a STATE.
 *  ⚠ Not hidden on a stopped bot — *it crashed*, *it refused to start* are exactly the findings
 *  you can only read once it is no longer running. */
function ReviewChip({ review }: { review: BotReview }) {
  return (
    <span
      title={review.findings.map((f) => `• ${f.title}\n  ${f.detail}`).join('\n\n')}
      className={`inline-flex items-center gap-[3px] text-[10px] font-semibold px-[6px] py-[2px] rounded-pill uppercase tracking-[0.4px] cursor-default ${
        review.level === 'alert' ? 'bg-neg-muted text-neg-text' : 'bg-warn-muted text-warn-text'
      }`}
    >
      <AlertTriangle size={9} /> review
      {review.findings.length > 1 ? ` ${review.findings.length}` : ''}
    </span>
  )
}

function LogModal({
  botName,
  botLabel,
  onClose,
}: {
  botName: string
  botLabel: string
  onClose: () => void
}) {
  const { data: log, isLoading, error } = useBotLog(botName)
  const [copied, setCopied] = useState(false)
  return (
    <div
      className="fixed inset-0 bg-black/60 flex items-center justify-center z-[60] p-6"
      onClick={onClose}
    >
      <div
        className="bg-bg-surface border border-border-default rounded-lg w-full max-w-3xl max-h-[80vh] flex flex-col"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="flex items-center justify-between px-4 py-3 border-b border-border-subtle">
          <span className="text-[13px] font-semibold">{botLabel} — stdout log</span>
          <div className="flex items-center gap-2">
            {log && (
              <button
                onClick={() => {
                  navigator.clipboard.writeText(log)
                  setCopied(true)
                  setTimeout(() => setCopied(false), 1500)
                }}
                title="Copy log"
                className="p-1 rounded hover:bg-bg-hover text-text-tertiary hover:text-text-secondary transition-colors"
              >
                {copied ? <Check size={13} className="text-accent" /> : <Copy size={13} />}
              </button>
            )}
            <button
              onClick={onClose}
              className="text-text-tertiary hover:text-text-primary text-[18px] leading-none"
            >
              ×
            </button>
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

function IconBtn({
  icon: Icon,
  title,
  onClick,
  tone,
  disabled,
}: {
  icon: typeof Play
  title: string
  onClick: () => void
  tone?: 'pos' | 'neg'
  disabled?: boolean
}) {
  const hover =
    tone === 'neg'
      ? 'hover:text-neg-text hover:border-neg/40'
      : tone === 'pos'
        ? 'hover:text-pos-text hover:border-pos/40'
        : 'hover:text-text-primary hover:border-border-default'
  return (
    <button
      title={title}
      aria-label={title}
      disabled={disabled}
      onClick={(e) => {
        // The row itself opens the drawer. A control inside it acts on the bot and must not
        // also open a panel over the thing it just did.
        e.stopPropagation()
        onClick()
      }}
      className={`w-[26px] h-[26px] grid place-items-center rounded-md border border-transparent text-text-tertiary transition-colors ${hover} hover:bg-bg-surface-2 disabled:opacity-30 disabled:cursor-not-allowed`}
    >
      <Icon size={12} />
    </button>
  )
}

export function Bots() {
  const { data: snapshot, isLoading, isFetching, error, dataUpdatedAt, refetch } = useBotSnapshot()
  const { data: accountGroups } = useBotAccounts()
  const { data: registry } = useRegisteredAccounts()
  const { data: users } = useUsers()
  const [params, setParams] = useSearchParams()

  const [logBot, setLogBot] = useState<string | null>(null)
  const [adding, setAdding] = useState(false)
  const [pending, setPending] = useState<string | null>(null)

  const startOne = useBotStartOne()
  const stopOne = useBotStopOne()
  const restartOne = useBotRestartOne()
  const busy = startOne.isPending || stopOne.isPending || restartOne.isPending
  useEffect(() => {
    if (!busy) setPending(null)
  }, [busy])

  const bots: BotStatus[] = snapshot?.bots ?? []
  const versionQueries = useBotVersions(bots.map((b) => b.key))
  const versionByKey = new Map(bots.map((b, i) => [b.key, versionQueries[i]]))

  const statusByKey = new Map<string, string>(bots.map((b) => [b.key, b.status]))
  const botByKey = new Map(bots.map((b) => [b.key, b]))

  // Selection lives in the URL, like every other view state in this app, so a link to one bot is
  // a real link and a refresh does not move you to a different bot's Deploy button.
  const view = params.get('view')
  const selBot = params.get('bot') ? (botByKey.get(params.get('bot') as string) ?? null) : null
  const selAccount = params.get('account')

  const set = (k: string, v: string | null) => {
    const next = new URLSearchParams(params)
    if (v === null) next.delete(k)
    else next.set(k, v)
    // Only one drawer at a time — opening a bot closes an account and the reverse.
    if (k === 'bot' && v !== null) next.delete('account')
    if (k === 'account' && v !== null) next.delete('bot')
    setParams(next, { replace: true })
  }

  const regByAccount = new Map((registry ?? []).map((a) => [a.account, a]))
  const groupByAccount = new Map(
    (accountGroups ?? [])
      .filter((g) => g.kind === 'account' && g.account !== null)
      .map((g) => [g.account as number, g])
  )

  /** Every bot on one account reports the SAME balance — one pot of money, not one each. The
   *  first that answers is the account's; a stopped neighbour reporting none does not change
   *  what the account holds. */
  const balanceOf = (rows: BotStatus[]) => rows.find((b) => b.balance != null)?.balance ?? null

  // Accounts that actually have bots, then the unassigned, then the empty ones as one-liners.
  const withBots: { account: number; group: BotAccountGroup; rows: BotStatus[] }[] = []
  for (const [account, group] of groupByAccount) {
    const rows = group.bots.map((b) => botByKey.get(b.key)).filter((b): b is BotStatus => !!b)
    if (rows.length) withBots.push({ account, group, rows })
  }
  const assigned = new Set(withBots.flatMap((a) => a.rows.map((b) => b.key)))
  const unassigned = bots.filter((b) => !assigned.has(b.key))
  const emptyAccounts = (registry ?? []).filter((a) => !groupByAccount.get(a.account)?.bots.length)

  const running = bots.filter((b) => b.status === 'RUNNING').length
  const totalBalance = withBots.reduce((s, a) => s + (balanceOf(a.rows) ?? 0), 0)
  const unread = withBots.filter((a) => balanceOf(a.rows) == null).length

  function act(key: string, fn: () => void) {
    setPending(key)
    fn()
  }

  if (view === 'users') {
    return (
      <div>
        <div className="flex items-center gap-3 pb-[14px] mb-[18px] border-b border-border-subtle">
          <h1 className="text-[19px] font-semibold">Who can command the bots</h1>
          <button
            onClick={() => set('view', null)}
            className="ml-auto text-[12px] text-text-secondary hover:text-text-primary transition-colors"
          >
            ← Bots
          </button>
        </div>
        <UsersTab />
      </div>
    )
  }

  return (
    <div>
      {/* ── one line, where three stat cards and a fleet strip used to be ──────── */}
      <div className="flex items-baseline gap-[14px] flex-wrap pb-[14px] mb-[18px] border-b border-border-subtle">
        <h1 className="text-[19px] font-semibold">Bots</h1>
        {snapshot && (
          <p className="text-[13px] text-text-secondary">
            <span className="text-text-primary font-medium">{running}</span> of{' '}
            <span className="text-text-primary font-medium">{bots.length}</span> running ·{' '}
            <span className="text-text-primary font-medium font-mono tabular-nums">
              $
              {totalBalance.toLocaleString('en-US', {
                minimumFractionDigits: 2,
                maximumFractionDigits: 2,
              })}
            </span>{' '}
            on {withBots.length} account{withBots.length === 1 ? '' : 's'}
            {/* Never silently low: an account nobody could read is said, not counted as zero. */}
            {unread > 0 && <span className="text-warn-text"> · {unread} unreadable</span>}
          </p>
        )}
        <div className="ml-auto flex items-center gap-2">
          <button
            onClick={() => setAdding(true)}
            className="text-[12px] px-[10px] py-[5px] rounded-md border border-border-default text-text-secondary hover:text-text-primary hover:bg-bg-hover transition-colors"
          >
            Add account
          </button>
          <button
            onClick={() => set('view', 'users')}
            className="text-[12px] px-[10px] py-[5px] rounded-md border border-border-default text-text-secondary hover:text-text-primary hover:bg-bg-hover transition-colors"
          >
            Users {users?.length ?? ''}
          </button>
          <button
            onClick={() => refetch()}
            title={
              dataUpdatedAt
                ? `Updated ${relativeTime(new Date(dataUpdatedAt).toISOString())}`
                : 'Refresh'
            }
            className="w-[28px] h-[28px] grid place-items-center rounded-md border border-border-default text-text-tertiary hover:text-text-primary hover:bg-bg-hover transition-colors"
          >
            <RefreshCw size={12} className={isFetching ? 'animate-spin' : ''} />
          </button>
        </div>
      </div>

      {adding && (
        <div className="mb-4">
          <AccountForm onClose={() => setAdding(false)} />
        </div>
      )}

      {isLoading && <p className="text-[12px] text-text-tertiary">Reading the box…</p>}
      {error && (
        <p className="text-[12px] text-neg-text">
          Could not reach the trading box: {String(error)}
        </p>
      )}

      {snapshot && (
        <div className="flex flex-col gap-[14px]">
          {/* ── accounts that are trading ──────────────────────────────────── */}
          {withBots.map(({ account, group, rows }) => {
            const balance = balanceOf(rows)
            const cap = group.cap_agrees ? group.risk_cap_pct : null
            const live = rows.filter((b) => b.status === 'RUNNING').length
            const reg = regByAccount.get(account)
            return (
              <div
                key={account}
                className="bg-bg-surface border border-border-subtle rounded-lg overflow-hidden"
              >
                <button
                  onClick={() => set('account', String(account))}
                  className="w-full flex items-center gap-3 px-4 py-[12px] text-left hover:bg-bg-surface-2 transition-colors"
                >
                  <span className="text-[14px] font-semibold">{nameOf(reg, group)}</span>
                  <span className="inline-flex text-[10px] font-semibold px-[6px] py-[2px] rounded-pill uppercase tracking-[0.4px] bg-bg-surface-2 text-text-secondary border border-border-subtle">
                    {rows[0].account_type}
                  </span>
                  <span className="text-[12px] font-mono text-text-tertiary">{account}</span>
                  <span className="ml-auto text-[14px] font-mono tabular-nums">
                    {balance == null ? (
                      <span className="text-[12px] text-warn-text">balance unread</span>
                    ) : (
                      '$' +
                      balance.toLocaleString('en-US', {
                        minimumFractionDigits: 2,
                        maximumFractionDigits: 2,
                      })
                    )}
                  </span>
                  <span className="text-[11px] text-text-tertiary w-[150px] text-right">
                    {rows.length} bot{rows.length === 1 ? '' : 's'} ·{' '}
                    {cap == null ? 'no cap' : `${cap}% cap`} · {live} trading
                  </span>
                </button>

                <div className="border-t border-border-subtle">
                  {rows.map((bot, i) => (
                    <button
                      key={bot.key}
                      onClick={() => set('bot', bot.key)}
                      className={`w-full grid grid-cols-[1fr_84px_60px_86px_auto] items-center gap-3 px-4 py-[10px] text-left hover:bg-bg-surface-2 transition-colors ${
                        i > 0 ? 'border-t border-border-subtle' : ''
                      }`}
                    >
                      <span className="flex items-center gap-[9px] font-medium text-[13px]">
                        <span
                          className={`inline-block w-[7px] h-[7px] rounded-full shrink-0 ${
                            bot.status === 'RUNNING' ? 'bg-pos shadow-[0_0_7px_#00ff7f]' : 'bg-neg'
                          }`}
                        />
                        {bot.name}
                        {bot.mt5_link === false && <NoLinkChip />}
                        {bot.review && <ReviewChip review={bot.review} />}
                      </span>
                      <VersionPill
                        version={versionByKey.get(bot.key)?.data}
                        loading={versionByKey.get(bot.key)?.isPending}
                      />
                      <span className="text-[12px] font-mono text-text-secondary">
                        {typeof group.bots.find((b) => b.key === bot.key)?.risk_pct === 'number'
                          ? `${group.bots.find((b) => b.key === bot.key)!.risk_pct}%`
                          : '—'}
                      </span>
                      <span className="text-[12px] font-mono text-text-tertiary">
                        {bot.uptime_seconds != null ? formatUptime(bot.uptime_seconds) : '—'}
                      </span>
                      <span className="flex gap-[3px] justify-end">
                        {pending === bot.key ? (
                          <span className="text-[11px] text-accent animate-pulse pr-1">…</span>
                        ) : bot.status === 'RUNNING' ? (
                          <>
                            <IconBtn
                              icon={Square}
                              title="Stop"
                              tone="neg"
                              disabled={busy}
                              onClick={() => act(bot.key, () => stopOne.mutate(bot.key))}
                            />
                            <IconBtn
                              icon={RotateCcw}
                              title="Restart"
                              disabled={busy}
                              onClick={() => act(bot.key, () => restartOne.mutate(bot.key))}
                            />
                          </>
                        ) : (
                          <IconBtn
                            icon={Play}
                            title="Start"
                            tone="pos"
                            disabled={busy}
                            onClick={() => act(bot.key, () => startOne.mutate(bot.key))}
                          />
                        )}
                        <IconBtn icon={FileText} title="Logs" onClick={() => setLogBot(bot.key)} />
                      </span>
                    </button>
                  ))}
                </div>
              </div>
            )
          })}

          {/* ── bots with no account ───────────────────────────────────────── */}
          {unassigned.length > 0 && (
            <div>
              <p className="text-[12px] text-text-secondary mb-[7px] px-[2px]">
                Not on an account{' '}
                <span className="text-text-tertiary">— trades nothing until you give it one</span>
              </p>
              <div className="bg-bg-surface border border-border-subtle rounded-lg overflow-hidden">
                {unassigned.map((bot, i) => (
                  <button
                    key={bot.key}
                    onClick={() => set('bot', bot.key)}
                    className={`w-full flex items-center gap-3 px-4 py-[10px] text-left hover:bg-bg-surface-2 transition-colors ${
                      i > 0 ? 'border-t border-border-subtle' : ''
                    }`}
                  >
                    <span className="flex items-center gap-[9px] font-medium text-[13px]">
                      <span className="inline-block w-[7px] h-[7px] rounded-full shrink-0 bg-text-tertiary/50" />
                      {bot.name}
                      {bot.review && <ReviewChip review={bot.review} />}
                    </span>
                    <span className="ml-auto text-[12px] text-text-tertiary">
                      {versionByKey.get(bot.key)?.data?.frozen ? 'idle' : 'never deployed'}
                    </span>
                    <IconBtn icon={FileText} title="Logs" onClick={() => setLogBot(bot.key)} />
                  </button>
                ))}
              </div>
            </div>
          )}

          {/* ── accounts with nothing on them: one line each ───────────────── */}
          {emptyAccounts.length > 0 && (
            <div className="bg-bg-surface border border-border-subtle rounded-lg overflow-hidden">
              {emptyAccounts.map((a: BotAccountRegistration, i) => (
                <button
                  key={a.account}
                  onClick={() => set('account', String(a.account))}
                  className={`w-full flex items-center gap-3 px-4 py-[9px] text-left text-text-tertiary hover:bg-bg-surface-2 transition-colors ${
                    i > 0 ? 'border-t border-border-subtle' : ''
                  }`}
                >
                  <span className="text-[13px] text-text-secondary font-medium">
                    {a.label || a.broker || `Account ${a.account}`}
                  </span>
                  <span className="inline-flex text-[10px] font-semibold px-[6px] py-[2px] rounded-pill uppercase tracking-[0.4px] bg-bg-surface-2 text-text-secondary border border-border-subtle">
                    {a.kind}
                  </span>
                  <span className="text-[12px] font-mono">{a.account}</span>
                  <span className="ml-auto text-[12px]">no bots</span>
                </button>
              ))}
            </div>
          )}

          {bots.length === 0 && (
            <p className="text-[12px] text-text-tertiary py-8 text-center">No bots registered.</p>
          )}
        </div>
      )}

      {selBot && (
        <BotDrawer
          bot={selBot}
          busy={busy}
          onClose={() => set('bot', null)}
          onLogs={() => setLogBot(selBot.key)}
          onStart={() => act(selBot.key, () => startOne.mutate(selBot.key))}
          onStop={() => act(selBot.key, () => stopOne.mutate(selBot.key))}
          onRestart={() => act(selBot.key, () => restartOne.mutate(selBot.key))}
        />
      )}

      {selAccount && groupByAccount.get(Number(selAccount)) && (
        <AccountDrawer
          group={groupByAccount.get(Number(selAccount)) as BotAccountGroup}
          reg={regByAccount.get(Number(selAccount))}
          balance={balanceOf(
            (groupByAccount.get(Number(selAccount)) as BotAccountGroup).bots
              .map((b) => botByKey.get(b.key))
              .filter((b): b is BotStatus => !!b)
          )}
          statusByKey={statusByKey}
          onClose={() => set('account', null)}
        />
      )}

      {logBot && (
        <LogModal
          botName={logBot}
          botLabel={botByKey.get(logBot)?.name ?? logBot}
          onClose={() => setLogBot(null)}
        />
      )}
    </div>
  )
}
