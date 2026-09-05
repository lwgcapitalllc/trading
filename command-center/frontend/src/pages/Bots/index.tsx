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
  SlidersHorizontal,
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
import type {
  BotStatus,
  BotReview,
  BotAccountGroup,
  BotAccountRegistration,
  BotEarnings,
  AccountEarnings,
} from '@/types'
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

/** Dollars, signed, with the sign leading the currency the way money is written.
 *  ⚠ `null` renders as a dash, never `$0.00` — this page's whole discipline is that a figure
 *  nobody measured and a measured zero may not look alike. */
function money(v: number | null | undefined, sign = true): string {
  if (v == null) return '—'
  const s = Math.abs(v).toLocaleString('en-US', {
    minimumFractionDigits: 2,
    maximumFractionDigits: 2,
  })
  const lead = !sign ? '' : v > 0 ? '+' : v < 0 ? '−' : ''
  return `${lead}$${s}`
}

/** Green up, red down, quiet at exactly flat.
 *  ⚠ Colour is reserved for the P&L numbers on this page. Everything else stays neutral, so a
 *  green figure always means the same thing rather than meaning "this row rendered". */
function pnlCls(v: number | null | undefined): string {
  if (v == null) return 'text-text-tertiary'
  if (v > 0) return 'text-pos-text'
  if (v < 0) return 'text-neg-text'
  return 'text-text-secondary'
}

/** A bot's identity colour, so one bot reads as the same thing in every row it appears in.
 *
 *  ⚠ **Explicit, never `series.filter(c => c !== pos)`.** The shared palette holds near-misses —
 *  `#00ff7f` against pos `#00ff82` is the same green to any eye — and a filter let a stack leg
 *  draw in the portfolio's own colour on the chart page. Same trap, same answer: list them.
 *  ⚠ Green and red are absent BY CONSTRUCTION: they mean up and down on this page. */
const BOT_TINTS = ['#00e5ff', '#ffb300', '#a78bfa', '#4da6ff'] as const

function tintOf(index: number): string {
  return BOT_TINTS[index % BOT_TINTS.length]
}

/** What ONE bot's own closed trades came to.
 *
 *  🔴 **This is NOT the account's growth wearing the bot's name.** Every bot on a balance used to
 *  report `total_pnl_pct`, which is the ACCOUNT's move — so a bot deployed yesterday claimed
 *  credit for everything the account had ever done. Aaron, 2026-09-05: *"that 45% increase was
 *  only from the SOS Fade. That should still be showing zero percent from the extreme leg."*
 *
 *  ⚠ **A bot with no record says so in words.** *Never traded* and *no record to read* are
 *  different answers and only one is a measurement; printing a confident `0.0%` for the second
 *  is this repo's rule 1 in a table cell. */
function Contribution({ e }: { e: BotEarnings | undefined }) {
  if (!e) return <span className="text-[12px] text-text-tertiary">—</span>
  if (!e.traded)
    return (
      <span
        title={e.reason ?? 'No record has been read for this bot.'}
        className="text-[11.5px] text-text-tertiary cursor-default"
      >
        no record yet
      </span>
    )
  if (!e.closed_trades)
    return (
      <span
        title={`Its record runs ${e.records_from} → ${e.records_to} and holds no closed trade.`}
        className="text-[11.5px] text-text-secondary cursor-default"
      >
        nothing closed
      </span>
    )
  return (
    <span
      title={`${e.closed_trades} closed ${e.closed_trades === 1 ? 'trade' : 'trades'} · ${e.wins}W / ${e.losses}L · ${(e.realised_r ?? 0) > 0 ? '+' : ''}${e.realised_r?.toFixed(2)}R · recorded ${e.records_from} → ${e.records_to}`}
      className="flex flex-col leading-tight cursor-default"
    >
      <span className={`text-[13px] font-mono tabular-nums font-medium ${pnlCls(e.realised_usd)}`}>
        {money(e.realised_usd)}
      </span>
      <span className="text-[10px] font-mono tabular-nums text-text-tertiary">
        {e.pct_of_opening != null
          ? `${e.pct_of_opening > 0 ? '+' : ''}${e.pct_of_opening.toFixed(1)}% of account`
          : ''}
      </span>
    </span>
  )
}

/** The account's own move, and what it is measured FROM.
 *
 *  ⚠ **The opening balance is on screen beside it.** A percentage with no referent is the defect
 *  the backtest page already recorded: *1439.7x of what*. Here it is worse — two bots on one
 *  balance state different anchors, so the number is only checkable if the page says which one
 *  it divided by and which bot stated it. */
function AccountNet({ e }: { e: AccountEarnings | undefined }) {
  if (!e || e.net_usd == null || e.net_pct == null)
    return (
      <span
        title={e?.opening_note ?? 'Nothing on this account has recorded what it opened at.'}
        className="text-[11px] text-text-tertiary cursor-default"
      >
        net unknown
      </span>
    )
  const up = e.net_usd >= 0
  return (
    <span
      title={`Opened at ${money(e.opening_balance, false)}, recorded by ${e.opening_from}. Now ${money(e.balance, false)}.`}
      className={`inline-flex items-baseline gap-[6px] px-[8px] py-[3px] rounded-pill cursor-default ${
        up ? 'bg-pos-muted' : 'bg-neg-muted'
      }`}
    >
      <span
        className={`text-[13px] font-mono tabular-nums font-semibold ${up ? 'text-pos-text' : 'text-neg-text'}`}
      >
        {e.net_pct > 0 ? '+' : ''}
        {e.net_pct.toFixed(1)}%
      </span>
      <span
        className={`text-[11px] font-mono tabular-nums ${up ? 'text-pos-text/70' : 'text-neg-text/70'}`}
      >
        {money(e.net_usd)}
      </span>
    </span>
  )
}

/** Where the account's growth CAME FROM — one bar, one segment per source.
 *
 *  🔴 **The last segment is the money no bot here recorded making, and it is the point of the
 *  chart rather than a rounding strip.** MEASURED on the live PU Prime ECN demo 2026-09-05: the
 *  account is up $4,541.89 and the bots' own closed trades are $1,197.09 of it — so **74% of
 *  what this page used to credit to "the bots" was not theirs.** Dividing an account's growth
 *  between the bots on it by any arithmetic credits a strategy with money it did not make.
 *
 *  ⚠ **Widths are absolute magnitudes, colours carry the sign.** A losing bot still occupies the
 *  room it moved the account by — a bar that shrank toward nothing as a bot lost more would read
 *  as a bot doing less.
 *
 *  ⚠ **It is withheld, never faked, when the account's net is unmeasured.** A bar with no total
 *  behind it would be a shape with no scale, which is the most confident-looking way to be wrong.
 *
 *  ⚠ **A segment under 1.5% still draws at 1.5%** so a real contribution can never vanish into a
 *  hairline that reads as "made nothing" — and the LEGEND under it carries the true figures, so
 *  nothing is read off the pixels. */
function NetSplit({ e, tintFor }: { e: AccountEarnings; tintFor: (key: string) => string }) {
  if (e.net_usd == null) return null

  const parts = [
    ...e.bots
      .filter((b) => b.traded && b.realised_usd != null && Math.abs(b.realised_usd) >= 0.01)
      .map((b) => ({
        key: b.bot_key,
        label: b.name,
        usd: b.realised_usd as number,
        color: tintFor(b.bot_key),
      })),
    ...(e.unattributed_usd != null && Math.abs(e.unattributed_usd) >= 0.01
      ? [
          {
            key: '__rest',
            label: 'Not from these bots',
            usd: e.unattributed_usd,
            color: '#3a3a55',
          },
        ]
      : []),
  ]
  if (!parts.length) return null

  const scale = parts.reduce((s, p) => s + Math.abs(p.usd), 0)
  if (scale <= 0) return null

  const missing = e.bots_without_record.length

  return (
    <div className="px-4 py-[11px] border-t border-border-subtle bg-bg-sunken/40">
      <div className="flex h-[7px] rounded-full overflow-hidden gap-[2px] mb-[9px]">
        {parts.map((p) => (
          <span
            key={p.key}
            title={`${p.label}: ${money(p.usd)}`}
            style={{
              width: `${Math.max(1.5, (Math.abs(p.usd) / scale) * 100)}%`,
              background: p.color,
              opacity: p.usd < 0 ? 0.45 : 1,
            }}
            className="block first:rounded-l-full last:rounded-r-full"
          />
        ))}
      </div>
      <div className="flex items-center gap-x-[18px] gap-y-[3px] flex-wrap">
        {parts.map((p) => (
          <span key={p.key} className="flex items-center gap-[6px] text-[11px]">
            <span
              className="inline-block w-[7px] h-[7px] rounded-sm shrink-0"
              style={{ background: p.color, opacity: p.usd < 0 ? 0.45 : 1 }}
            />
            <span className={p.key === '__rest' ? 'text-text-tertiary' : 'text-text-secondary'}>
              {p.label}
            </span>
            <span className={`font-mono tabular-nums ${pnlCls(p.usd)}`}>{money(p.usd)}</span>
            <span className="font-mono tabular-nums text-text-tertiary">
              {Math.round((Math.abs(p.usd) / scale) * 100)}%
            </span>
          </span>
        ))}
        <span className="ml-auto text-[10.5px] text-text-tertiary">
          {missing > 0
            ? `${missing === 1 ? 'one bot has' : `${missing} bots have`} no record here yet — this split is a floor`
            : 'the rest is a manual fill, a deposit, or a trade older than the record'}
        </span>
      </div>
    </div>
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

  // 🔴 Computed SERVER-SIDE and only rendered here. What an account made and what its bots made
  // are two different measurements, and whether they agree is the finding — deriving either in
  // the browser would be the same rule written twice in two languages, which is how the risk
  // share total already drifted once on this very page.
  const earnByAccount = new Map((snapshot?.earnings ?? []).map((e) => [e.account, e]))
  const earnByBot = new Map(
    (snapshot?.earnings ?? []).flatMap((e) => e.bots.map((b) => [b.bot_key, b] as const))
  )

  // ⚠ Summed across ACCOUNTS, never across bots — two bots on one balance share one pot, which
  // is what made this header add the same money twice on 2026-09-04. An account whose net could
  // not be measured is counted as UNKNOWN and named, never folded in as zero.
  const netAccounts = withBots
    .map((a) => earnByAccount.get(a.account))
    .filter((e): e is AccountEarnings => !!e && e.net_usd != null)
  const fleetNet = netAccounts.length ? netAccounts.reduce((s, e) => s + (e.net_usd ?? 0), 0) : null

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
            <span className={running > 0 ? 'text-pos-text font-medium' : 'text-text-primary'}>
              {running}
            </span>{' '}
            of <span className="text-text-primary font-medium">{bots.length}</span> running ·{' '}
            <span className="text-text-primary font-medium font-mono tabular-nums">
              {money(totalBalance, false)}
            </span>{' '}
            on {withBots.length} account{withBots.length === 1 ? '' : 's'}
            {/* The fleet's own move, and it is summed across ACCOUNTS. An account whose net
             *  nobody could measure is left OUT and said, never added in as a zero. */}
            {fleetNet != null && (
              <>
                {' · '}
                <span className={`font-mono tabular-nums font-medium ${pnlCls(fleetNet)}`}>
                  {money(fleetNet)}
                </span>
                {netAccounts.length < withBots.length && (
                  <span className="text-warn-text">
                    {' '}
                    from {netAccounts.length} of {withBots.length}
                  </span>
                )}
              </>
            )}
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
            const reg = regByAccount.get(account)
            const earn = earnByAccount.get(account)
            // ONE map from bot key to colour, read by the row's rail AND by the split bar's
            // segments. Two hand-written lookups is how a bar segment ends up a different
            // colour from the row it names, on the one chart whose whole job is saying which
            // bot is which.
            const tintByKey = new Map(rows.map((b, i) => [b.key, tintOf(i)]))
            const tintFor = (key: string) => tintByKey.get(key) ?? '#3a3a55'
            // Green when the account is up, red when it is down, neutral when nothing has
            // measured it. The rail is the only large block of colour on the card, so it may
            // not be decorative — it says one thing and it is the same thing everywhere.
            const railCls =
              earn?.net_usd == null
                ? 'bg-border-default'
                : earn.net_usd > 0
                  ? 'bg-pos/70'
                  : earn.net_usd < 0
                    ? 'bg-neg/70'
                    : 'bg-border-strong'
            return (
              <div
                key={account}
                data-testid="account-card"
                className="relative bg-bg-surface border border-border-subtle rounded-lg overflow-hidden"
              >
                <span className={`absolute left-0 top-0 bottom-0 w-[3px] ${railCls}`} />

                <button
                  onClick={() => set('account', String(account))}
                  title="Open this account — balance, risk cap, and which bots are on it"
                  className="w-full flex items-center gap-3 pl-[19px] pr-4 py-[13px] text-left hover:bg-bg-surface-2 transition-colors"
                >
                  <span className="text-[14px] font-semibold">{nameOf(reg, group)}</span>
                  <span className="inline-flex text-[10px] font-semibold px-[6px] py-[2px] rounded-pill uppercase tracking-[0.4px] bg-bg-surface-2 text-text-secondary border border-border-subtle">
                    {rows[0].account_type}
                  </span>
                  <span className="text-[12px] font-mono text-text-tertiary">{account}</span>

                  {/* The cap is the ONLY count left here. `2 bots · 2 trading` went on
                   *  2026-09-05 — Aaron: "I could see two is trading… I could see two bots."
                   *  The rows below state both, and a number restating what is already on
                   *  screen is the duplication this page was rebuilt to remove. */}
                  <span className="text-[11px] text-text-tertiary">
                    {cap == null ? 'no cap' : `${cap}% cap`}
                  </span>

                  <span className="ml-auto flex items-baseline gap-[10px]">
                    <span className="text-[17px] font-mono tabular-nums font-medium">
                      {balance == null ? (
                        <span className="text-[12px] text-warn-text">balance unread</span>
                      ) : (
                        money(balance, false)
                      )}
                    </span>
                    <AccountNet e={earn} />
                  </span>
                </button>

                <div className="border-t border-border-subtle">
                  {rows.map((bot, i) => {
                    const be = earnByBot.get(bot.key)
                    const running = bot.status === 'RUNNING'
                    return (
                      <div
                        key={bot.key}
                        data-testid="bot-row"
                        className={`group grid grid-cols-[minmax(150px,225px)_142px_92px_50px_74px_1fr_auto] items-center gap-3 pr-4 py-[10px] transition-colors hover:bg-bg-surface-2 ${
                          i > 0 ? 'border-t border-border-subtle' : ''
                        }`}
                      >
                        {/* The NAME is the button, not the whole row — the row now carries
                         *  four controls and a row-wide click behind them makes every miss
                         *  open a drawer over the thing you were aiming at. */}
                        <button
                          onClick={() => set('bot', bot.key)}
                          title={`Open ${bot.name} — risk, version, account and its settings`}
                          className="flex items-center gap-[9px] font-medium text-[13px] text-left min-w-0 pl-[19px]"
                        >
                          {/* This bot's identity colour, carried on every surface it appears
                           *  on so two bots on one balance never blur together. */}
                          <span
                            className="inline-block w-[3px] h-[17px] rounded-full shrink-0 -ml-[11px]"
                            style={{ background: tintFor(bot.key) }}
                          />
                          <span
                            className={`inline-block w-[7px] h-[7px] rounded-full shrink-0 ${
                              running ? 'bg-pos shadow-[0_0_7px_#00ff7f]' : 'bg-neg'
                            }`}
                          />
                          <span className="truncate group-hover:text-accent transition-colors">
                            {bot.name}
                          </span>
                          {bot.mt5_link === false && <NoLinkChip />}
                          {bot.review && <ReviewChip review={bot.review} />}
                        </button>

                        {/* 🔴 The money sits NEXT TO THE NAME, not out at the far edge with the
                         *  machinery. It is the answer to the question this row is read with —
                         *  what has this bot done — and 400px of empty grid between the two made
                         *  the row read as a name with some settings after it. */}
                        <Contribution e={be} />

                        <VersionPill
                          version={versionByKey.get(bot.key)?.data}
                          loading={versionByKey.get(bot.key)?.isPending}
                        />

                        <span
                          title="Risk per trade — its share of this account's ceiling"
                          className="text-[12px] font-mono text-text-secondary cursor-default"
                        >
                          {typeof group.bots.find((b) => b.key === bot.key)?.risk_pct === 'number'
                            ? `${group.bots.find((b) => b.key === bot.key)!.risk_pct}%`
                            : '—'}
                        </span>

                        <span
                          title="How long it has been running without a restart"
                          className="text-[12px] font-mono text-text-tertiary cursor-default"
                        >
                          {bot.uptime_seconds != null ? formatUptime(bot.uptime_seconds) : '—'}
                        </span>

                        <span />

                        <span className="flex gap-[3px] justify-end">
                          {pending === bot.key ? (
                            <span className="text-[11px] text-accent animate-pulse pr-1">…</span>
                          ) : running ? (
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
                          {/* 🔴 The one control Aaron could not find: "there's no more edit
                           *  button. I don't see a way to configure anything." The drawer had
                           *  always held it, but a row you have to GUESS is clickable is a
                           *  feature nobody has. */}
                          <IconBtn
                            icon={SlidersHorizontal}
                            title={`Configure ${bot.name} — risk, version, account, settings`}
                            onClick={() => set('bot', bot.key)}
                          />
                          <IconBtn
                            icon={FileText}
                            title="Logs"
                            onClick={() => setLogBot(bot.key)}
                          />
                        </span>
                      </div>
                    )
                  })}
                </div>

                {earn && <NetSplit e={earn} tintFor={tintFor} />}
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
                {/* 🔴 A row is a DIV whose NAME is the button, never a button holding
                 *  buttons. `<button>` inside `<button>` is invalid markup — React says so at
                 *  runtime and this row had been saying it since the rewrite — and the nested
                 *  control's click is what the browser is entitled to do anything with. */}
                {unassigned.map((bot, i) => (
                  <div
                    key={bot.key}
                    data-testid="bot-row"
                    className={`group flex items-center gap-3 pr-4 py-[10px] hover:bg-bg-surface-2 transition-colors ${
                      i > 0 ? 'border-t border-border-subtle' : ''
                    }`}
                  >
                    <button
                      onClick={() => set('bot', bot.key)}
                      title={`Open ${bot.name} — put it on an account, then configure it`}
                      className="flex items-center gap-[9px] font-medium text-[13px] text-left pl-4"
                    >
                      <span className="inline-block w-[7px] h-[7px] rounded-full shrink-0 bg-text-tertiary/50" />
                      <span className="group-hover:text-accent transition-colors">{bot.name}</span>
                      {bot.review && <ReviewChip review={bot.review} />}
                    </button>
                    <span className="ml-auto text-[12px] text-text-tertiary">
                      {versionByKey.get(bot.key)?.data?.frozen ? 'idle' : 'never deployed'}
                    </span>
                    <IconBtn
                      icon={SlidersHorizontal}
                      title={`Configure ${bot.name}`}
                      onClick={() => set('bot', bot.key)}
                    />
                    <IconBtn icon={FileText} title="Logs" onClick={() => setLogBot(bot.key)} />
                  </div>
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
          earnings={earnByBot.get(selBot.key)}
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
          earnings={earnByAccount.get(Number(selAccount))}
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
