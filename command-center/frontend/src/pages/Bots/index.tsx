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

/** ⚠ THE PER-BOT COLOUR PALETTE IS GONE (2026-09-06), with both things that read it: the row
 *  rail Aaron read as decoration, and the split bar whose segments duplicated the P&L column.
 *  Note for whoever wants one back — the rule that made it safe was that the list was EXPLICIT
 *  rather than `series.filter(c => c !== pos)`: the shared palette holds near-misses (`#00ff7f`
 *  against pos `#00ff82`), which is how a stack leg once drew in the portfolio's own colour. */

/** ONE column template for the heading row and every bot row under it. Two hand-written
 *  lists is how a heading ends up over the wrong column. */
const GRID = 'grid-cols-[minmax(150px,225px)_142px_92px_50px_74px_1fr_auto]'

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

/** The money an account made that NO BOT here recorded making.
 *
 * 🔴 **This was a stacked bar with a segment per bot, and the segments were a second copy of the
 * P&L column.** Aaron, 2026-09-06: *"is the purpose of it to show the breakdown of which strategy
 * added how much equity per account? because if that's the case, I thought that's what the P&L
 * column is for."* He was right — and the answer is not to explain the bar better, it is that only
 * ONE of its segments was saying something the row above could not.
 *
 * ⚠ **That one is worth keeping on its own.** MEASURED on the live PU Prime ECN demo: the account
 * is up $4,541.89, the bots' own closed trades are $1,197.09, and the remaining **$3,344.80 was
 * four duplicate positions a broker-timeout defect opened and Aaron closed by hand.** A page that
 * silently folded that into "the bots" would have reported a fixed bug as a strategy result.
 *
 * ⚠ **It renders only when there IS a remainder.** A permanent row reading `$0.00` is a green tick
 * nobody reads by the second day, and this line only earns its space on the days it has something
 * to say.
 *
 * ⚠ **`bots_without_record` still qualifies the claim.** While a bot here has no record the
 * remainder includes whatever it may have done, so the sentence says the split is a floor rather
 * than asserting the money came from nowhere. */
function Unattributed({ e }: { e: AccountEarnings }) {
  if (e.unattributed_usd == null || Math.abs(e.unattributed_usd) < 0.01) return null
  const missing = e.bots_without_record.length
  return (
    <div className="flex items-center gap-[10px] px-4 py-[9px] border-t border-border-subtle bg-bg-sunken/40">
      <span className="text-[11px] text-text-tertiary">Not from these bots</span>
      <span className={`text-[12px] font-mono tabular-nums ${pnlCls(e.unattributed_usd)}`}>
        {money(e.unattributed_usd)}
      </span>
      <span className="text-[10.5px] text-text-tertiary">
        {missing > 0
          ? `— a manual fill, a deposit, or ${missing === 1 ? 'a bot whose record has' : `${missing} bots whose records have`} not arrived`
          : '— a manual fill, a deposit, or a trade older than the record'}
      </span>
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
  // Live / demo, in the URL like every other view state here — so a link to "just the live
  // accounts" is a real link and a refresh does not put the demos back.
  //
  // ⚠ **Absent means ALL, and that is the default deliberately.** Aaron asked for live-vs-demo
  // and said he does not care about an "all" — but every account on this box is a demo today, so
  // defaulting to LIVE would open the page empty, which is indistinguishable from a page that
  // failed to load. The control is what he asked for; the default is the one that cannot lie.
  const kind = params.get('kind')
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

  // ⚠ Filtered LAST, on the assembled lists, so the derivations above stay the whole truth —
  // `assigned` in particular decides which bots count as unassigned, and computing that against
  // a filtered set would invent bots with no account whenever a filter was on.
  const keep = (t: string | undefined) => !kind || t === kind
  const shownAccounts = withBots.filter((a) => keep(a.rows[0]?.account_type))
  const shownEmpty = emptyAccounts.filter((a) => keep(a.kind))
  const shownUnassigned = unassigned.filter((b) => keep(b.account_type))
  const hiddenByFilter =
    withBots.length -
    shownAccounts.length +
    (emptyAccounts.length - shownEmpty.length) +
    (unassigned.length - shownUnassigned.length)

  const running = bots.filter((b) => b.status === 'RUNNING').length
  const unread = withBots.filter((a) => balanceOf(a.rows) == null).length

  // 🔴 Computed SERVER-SIDE and only rendered here. What an account made and what its bots made
  // are two different measurements, and whether they agree is the finding — deriving either in
  // the browser would be the same rule written twice in two languages, which is how the risk
  // share total already drifted once on this very page.
  const earnByAccount = new Map((snapshot?.earnings ?? []).map((e) => [e.account, e]))
  const earnByBot = new Map(
    (snapshot?.earnings ?? []).flatMap((e) => e.bots.map((b) => [b.bot_key, b] as const))
  )

  // ⚠ THERE IS DELIBERATELY NO FLEET TOTAL HERE ANY MORE (2026-09-06). Summing balances across
  // ACCOUNTS was correct — two bots on one balance share one pot, and summing across BOTS is what
  // added the same money twice on 2026-09-04 — but the figure was a second copy of what each
  // account already states. It came off with the header line it fed. If a fleet total is ever
  // wanted again, sum per ACCOUNT and leave an unmeasured one OUT rather than folding it in as
  // zero; that is the part that was hard to get right.

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
        {/* 🔴 THE MONEY CAME OFF THIS LINE (2026-09-06). It carried the fleet balance and the
         *  fleet net, and both are already on the account they belong to a few pixels below —
         *  Aaron: *"I don't know if that information is necessary. Like, I could just look and
         *  see."* ⚠ The rule it is an instance of is this page's oldest one: a number restating
         *  what is already on screen is not a summary, it is a second copy that can disagree.
         *  ⚠ The count STAYS, because *how many are running* is the one thing you cannot read
         *  off the rows without counting them yourself. */}
        {snapshot && (
          <p className="text-[13px] text-text-secondary">
            <span className={running > 0 ? 'text-pos-text font-medium' : 'text-text-primary'}>
              {running}
            </span>{' '}
            of <span className="text-text-primary font-medium">{bots.length}</span> running
            {/* Never silently low: an account nobody could read is SAID, never counted as zero.
             *  It survives the trim because it is a FAULT, and a fault has no other home. */}
            {unread > 0 && (
              <span className="text-warn-text">
                {' · '}
                {unread} balance{unread === 1 ? '' : 's'} unread
              </span>
            )}
          </p>
        )}
        <div className="ml-auto flex items-center gap-2">
          {/* 🔴 TWO CHIPS, NOT THREE. Aaron asked for live-vs-demo and said plainly he does not
           *  care about an "All" — so ALL is the state with NEITHER chip pressed, reached by
           *  pressing the active one again, rather than a third button competing for the eye.
           *  ⚠ The pressed chip carries `aria-pressed` and a border: a filter you cannot see is
           *  still a filter that is applied, and this page can hide an entire account. */}
          {(['live', 'demo'] as const).map((k) => (
            <button
              key={k}
              aria-pressed={kind === k}
              onClick={() => set('kind', kind === k ? null : k)}
              title={
                kind === k
                  ? `Showing ${k} accounts only — click to show every account`
                  : `Show only ${k} accounts`
              }
              className={`text-[11px] font-semibold uppercase tracking-[0.4px] px-[9px] py-[5px] rounded-md border transition-colors ${
                kind === k
                  ? k === 'live'
                    ? 'bg-warn-muted text-warn-text border-warn/50'
                    : 'bg-accent-muted text-accent border-accent/50'
                  : 'border-border-default text-text-tertiary hover:text-text-primary hover:bg-bg-hover'
              }`}
            >
              {k}
            </button>
          ))}
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
          {shownAccounts.map(({ account, group, rows }) => {
            const balance = balanceOf(rows)
            const cap = group.cap_agrees ? group.risk_cap_pct : null
            const reg = regByAccount.get(account)
            const earn = earnByAccount.get(account)
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
                  {/* 🔴 THE NUMBER LEADS (2026-09-06, Aaron: *"the account number should be the
                   *  thing prefix in the account"*). The login is what the broker, the terminal,
                   *  the instance config and every refusal message name it by; the label is a
                   *  nickname somebody typed here. When the two disagree the number is the one
                   *  that is right, so it is the one the eye lands on first. */}
                  <span className="text-[14px] font-mono font-semibold tabular-nums">
                    {account}
                  </span>
                  <span className="text-[13px] text-text-secondary">{nameOf(reg, group)}</span>
                  {/* ⚠ A LIVE account is tinted, a demo is not. Same treatment everywhere an
                   *  account appears — its cost is different in KIND, not degree. */}
                  <span
                    className={`inline-flex text-[10px] font-semibold px-[6px] py-[2px] rounded-pill uppercase tracking-[0.4px] border ${
                      rows[0].account_type === 'live'
                        ? 'bg-warn-muted text-warn-text border-warn/40'
                        : 'bg-bg-surface-2 text-text-secondary border-border-subtle'
                    }`}
                  >
                    {rows[0].account_type}
                  </span>

                  {/* The cap is the ONLY count left here. `2 bots · 2 trading` went on
                   *  2026-09-05 — Aaron: "I could see two is trading… I could see two bots."
                   *  The rows below state both, and a number restating what is already on
                   *  screen is the duplication this page was rebuilt to remove.
                   *
                   *  🔴 It is a CHIP, not grey prose. As tertiary text beside the account
                   *  number it read as another piece of identity — Aaron: *"the cap is missing.
                   *  Well, not missing. It's just not obvious."* It is the one number here that
                   *  can refuse a trade, so it gets a border and the gold the page reserves for
                   *  a limit. ⚠ NO CAP is the LOUD state, in warn: an account with no ceiling
                   *  is the condition worth noticing, and rendering it quieter than a set cap
                   *  is backwards. */}
                  {cap == null ? (
                    <span
                      title="No risk ceiling is set on this account — nothing here refuses a trade for being too large."
                      className="inline-flex items-center text-[10.5px] font-semibold px-[7px] py-[3px] rounded-pill uppercase tracking-[0.4px] bg-warn-muted text-warn-text border border-warn/40 cursor-default"
                    >
                      no cap
                    </span>
                  ) : (
                    <span
                      title={`Open risk across every bot on this account is capped at ${cap}% of its balance.`}
                      className="inline-flex items-baseline gap-[4px] text-[11px] px-[7px] py-[3px] rounded-pill bg-gold-muted border border-gold/30 cursor-default"
                    >
                      <span className="font-mono tabular-nums font-semibold text-gold-text">
                        {cap}%
                      </span>
                      <span className="text-[10px] text-gold-text/70 uppercase tracking-[0.4px]">
                        cap
                      </span>
                    </span>
                  )}

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
                  {/* 🔴 The rows are a TABLE and were unlabelled — Aaron: *"since this is a kind
                   *  of a table format, I would like titles."* Four numeric columns with no
                   *  heading means the reader decodes them from their own shape, and `5%` beside
                   *  `+12.0% of account` is exactly the pair that gets read as the same kind of
                   *  thing.
                   *
                   *  ⚠ ONE grid template, shared with the rows below by a constant. A hand-copied
                   *  column list is how a heading ends up over the wrong column — and a heading
                   *  that is confidently over the wrong number is worse than none. */}
                  <div
                    className={`grid ${GRID} items-center gap-3 pr-4 py-[6px] border-b border-border-subtle bg-bg-sunken/50 text-[9.5px] font-semibold uppercase tracking-[0.7px] text-text-tertiary`}
                  >
                    <span className="pl-[19px]">Bot</span>
                    <span title="What this bot's own closed trades came to">P&amp;L</span>
                    <span>Version</span>
                    <span title="Risk per trade">Risk</span>
                    <span>Uptime</span>
                    <span />
                    <span className="text-right">Actions</span>
                  </div>
                  {rows.map((bot, i) => {
                    const be = earnByBot.get(bot.key)
                    const running = bot.status === 'RUNNING'
                    return (
                      <div
                        key={bot.key}
                        data-testid="bot-row"
                        className={`group grid ${GRID} items-center gap-3 pr-4 py-[10px] transition-colors hover:bg-bg-surface-2 ${
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
                          {/* ⚠ NO identity rail here. It was a 3px bar per bot and Aaron read it
                           *  as meaningless decoration — which it was, on a row that already
                           *  names the bot. The split bar below still tints its segments,
                           *  because two segments have no other way to be told apart, and its
                           *  legend spells out which is which. */}
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
                          <IconBtn
                            icon={FileText}
                            title="Logs"
                            onClick={() => setLogBot(bot.key)}
                          />
                          {/* 🔴 THE CONTROL AARON COULD NOT FIND, TWICE. First it was only the
                           *  row itself; then it was an ICON among three other icons, and he
                           *  still asked *"where is configure? We used to have a Configure tab.
                           *  That's gone completely now."*
                           *
                           *  ⚠ **It says the word.** An icon is a rebus for anybody who has not
                           *  already learned it, and the whole reason this control keeps going
                           *  missing is that the tab it replaced had a NAME. The other three
                           *  stay icons because they are verbs you can guess from a shape;
                           *  "configure" is not a shape.
                           *
                           *  ⚠ It is the same target as clicking the name — one drawer, one
                           *  route in. A second way in is fine; a second IMPLEMENTATION is what
                           *  this page keeps being rebuilt to remove. */}
                          <button
                            data-testid="configure-bot"
                            onClick={(e) => {
                              e.stopPropagation()
                              set('bot', bot.key)
                            }}
                            title={`Configure ${bot.name} — risk per trade, version, account and all its settings`}
                            className="flex items-center gap-[5px] ml-[6px] px-[9px] h-[26px] rounded-md border border-border-default text-[11.5px] text-text-secondary hover:text-text-primary hover:border-accent/50 hover:bg-accent-muted transition-colors"
                          >
                            <SlidersHorizontal size={11} />
                            Configure
                          </button>
                        </span>
                      </div>
                    )
                  })}
                </div>

                {earn && <Unattributed e={earn} />}
              </div>
            )
          })}

          {/* ── bots with no account ───────────────────────────────────────── */}
          {shownUnassigned.length > 0 && (
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
                {shownUnassigned.map((bot, i) => (
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
                    <IconBtn icon={FileText} title="Logs" onClick={() => setLogBot(bot.key)} />
                    <button
                      data-testid="configure-bot"
                      onClick={() => set('bot', bot.key)}
                      title={`Configure ${bot.name}`}
                      className="flex items-center gap-[5px] ml-[6px] px-[9px] h-[26px] rounded-md border border-border-default text-[11.5px] text-text-secondary hover:text-text-primary hover:border-accent/50 hover:bg-accent-muted transition-colors"
                    >
                      <SlidersHorizontal size={11} />
                      Configure
                    </button>
                  </div>
                ))}
              </div>
            </div>
          )}

          {/* ── accounts with nothing on them: one line each ───────────────── */}
          {shownEmpty.length > 0 && (
            <div className="bg-bg-surface border border-border-subtle rounded-lg overflow-hidden">
              {shownEmpty.map((a: BotAccountRegistration, i) => (
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

          {/* ⚠ A filter that empties the page must SAY it did. A blank list and a fleet that
           *  really is empty look identical, and only one of them is a finding. */}
          {kind && hiddenByFilter > 0 && (
            <p className="text-[11.5px] text-text-tertiary px-[2px]">
              {hiddenByFilter}{' '}
              {hiddenByFilter === 1 ? 'account or bot is' : 'accounts and bots are'} hidden by the{' '}
              <span className="text-text-secondary">{kind}</span> filter.{' '}
              <button onClick={() => set('kind', null)} className="text-accent hover:underline">
                Show everything
              </button>
            </p>
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
