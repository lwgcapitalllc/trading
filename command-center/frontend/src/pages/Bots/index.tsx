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
 * 🔴 **Two tabs (2026-09-10): *Trading* holds only accounts with a bot on them, *Unassigned* the
 * accounts with none and the bots on none** (Aaron: *"I just only wanna focus on the accounts that
 * have bots on them"*). An account with no bots still earns a line there — you cannot move a bot
 * onto an account you cannot see — but not a place in the first look.
 *
 * 🔴 **An account bots have TRADED on stays on Trading when they leave, as the SAME card
 * (2026-09-11).** Aaron, after a set went live from demo: *"moving bots to live doesn't mean we
 * don't trade on the demo still… what if I wanted to test out more bots on a demo account while the
 * live bot is also trading… it shouldn't matter."* It was a separate "history" card — no balance,
 * no cap, headed *no bots on it now* — which read as a closed account, and it VANISHED the moment a
 * new bot joined, taking the departed bots' record and the demo score with it. Now it is one card
 * whatever happens: its balance (the last one a bot read, with the time), the bots on it now, an
 * Add-a-bot row when there are none, and the bots that left as rows saying where they went.
 *
 * 🔴 **On Trading, live and demo are two sections, and the side ahead reads "Leading"** (*"I want
 * live and demo split… easily identify the winner"*). The winner is judged in R per trade — see
 * `PerTrade` for why dollars, share of the account and total R all crown demo.
 *
 * 🔴 **Nothing on the page says a fact twice (2026-09-10, *"we don't need to be redundant on data
 * anywhere on this page"*).** A section heading names the kind, so no card repeats it; the net pill
 * carries the account's sign, so no edge colour repeats it; a side's pooled score shows only when it
 * pools two or more bots, because a pool of one is that bot's row.
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
  TrendingUp,
  Trophy,
  Plus,
} from 'lucide-react'
import {
  useBotSnapshot,
  useBotAccounts,
  useRegisteredAccounts,
  useBotLog,
  useBotVersions,
  usePromoteJobs,
  useUsers,
  useBotStartOne,
  useBotStopOne,
  useBotRestartOne,
} from '@/hooks/useBots'
import { VersionPill } from '@/components/VersionPill'
import { Shimmer } from '@/components/Shimmer'
import { openingRecorder } from '@/lib/accountEarnings'
import { botLabel as labelOf } from '@/lib/botLabel'
import type {
  BotStatus,
  BotReview,
  BotAccountBot,
  BotAccountGroup,
  BotAccountRegistration,
  BotEarnings,
  AccountEarnings,
} from '@/types'
import { BotActionPill, type BotAction } from './BotStatusPill'
import { UsersTab } from './UsersTab'
import { BotDrawer } from './BotDrawer'
import { AccountDrawer } from './AccountDrawer'
import { emptyGroup, nameOf } from './AccountForm'
import { VpsSyncDrawer } from './VpsSyncDrawer'
import { KIND_NAME, KIND_TINT, KindChip, tintOf } from './kind'

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

/** The broker or the terminal will not let this account trade — every order will be refused.
 *  🔴 Written after 2026-09-11: the live account was read-only for seven hours, every order came
 *  back refused, and nothing on this page said so. ⚠ `=== false` only: `null` means the bot could
 *  not ask, which is not the claim "trading is off". Amber, not red — red means a loss here. */
function TradingOffChip({ reason }: { reason?: string | null }) {
  const why = reason
    ? `${reason[0].toUpperCase()}${reason.slice(1)}`
    : 'The broker or the terminal will not let this account trade'
  return (
    <span
      data-testid="trading-off"
      title={`${why}. Every order the bot sends will be refused until it is back on.`}
      className="inline-flex items-center gap-[3px] text-[10px] font-semibold px-[6px] py-[2px] rounded-pill uppercase tracking-[0.4px] bg-warn-muted text-warn-text cursor-default"
    >
      trading off
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
/** When a past balance reading was taken, in the reader's own clock — "10 Sep, 23:51". */
function readTime(iso: string): string {
  const d = new Date(iso)
  if (Number.isNaN(d.getTime())) return iso
  return d.toLocaleString('en-GB', {
    day: 'numeric',
    month: 'short',
    hour: '2-digit',
    minute: '2-digit',
  })
}

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
 *  lists is how a heading ends up over the wrong column.
 *
 *  🔴 **One value per cell (2026-09-10, Aaron: *"I don't want anything stacked on top of each
 *  other in columns like that"*).** The return % sat under the dollars and the trade count under
 *  the R, so each cell held two different measurements and the reader could not tell whether the
 *  % and the R said the same thing. They are their own columns now: Bot | P&L | Return % | Trades |
 *  Per trade | Version | Risk | Uptime | Actions.
 *
 *  ⚠ The version column is 136px because a behind pill ("v201 · 7 behind") MEASURES 115px on
 *  one line (2026-09-10); at 92px it wrapped into a two-line blob. ⚠ The rest are sized to their
 *  widest real value so every column still fits a 1280px screen with the name at its 150px floor.
 *
 *  🔴 **Every track is FIXED except the name and the spacer — the actions too.** Each row is its
 *  own grid, and an `auto` actions track sizes to ITS row: the word "Actions" in the heading row,
 *  ~185px of buttons in a bot row. On a 1280px screen the bot row ran out of room, squeezed its name
 *  column, and every value sat ~50px left of its heading while the heading row did not move. */
const GRID = 'grid-cols-[minmax(150px,225px)_100px_64px_52px_80px_136px_48px_64px_1fr_190px]'

/** R per trade: what a bot's closed trades made on average, in units of the risk each one took.
 *  `null` when there is nothing to average — no record, or no closed trade — never 0. */
function perTradeOf(e: BotEarnings | undefined): number | null {
  if (!e?.traded || !e.closed_trades || e.realised_r == null) return null
  return e.realised_r / e.closed_trades
}

function fmtR(r: number): string {
  return `${r > 0 ? '+' : r < 0 ? '−' : ''}${Math.abs(r).toFixed(2)}R`
}

/** Two scores closer than this read the same at two decimals, so neither may be called ahead. */
const TIE_R = 0.005

/**
 * The score a winner is picked on — R per trade. Its sample is the Trades column beside it.
 *
 * 🔴 **The winner is judged in R per trade, never dollars** (Aaron, 2026-09-10: *"I want to be able
 * to easily identify the winner"*, with live and demo both running). A live account is smaller,
 * runs lower risk and started later than the demo beside it, so dollars, a share of the account and
 * even total R would all crown the demo by default. R per trade is the one figure none of those
 * three can move. MEASURED the day it landed: the two demo bots read $1,305.58 against $1,197.09 —
 * near a tie in dollars — and +2.10R against +0.46R a trade.
 *
 * ⚠ **The trade count sits BESIDE it, in the Trades column.** On one or two trades a lead is not a
 * verdict; that is said as a caveat next to the number, never by hiding it (root CLAUDE.md →
 * Trading Philosophy).
 */
function PerTrade({
  e,
  asking,
  top,
}: {
  e: BotEarnings | undefined
  asking: boolean
  top: boolean
}) {
  if (!e && asking) return <Shimmer className="h-[13px] w-[56px]" />
  const r = perTradeOf(e)
  if (r == null || !e?.closed_trades) return <Dash />
  const n = e.closed_trades
  return (
    <span
      data-testid="per-trade"
      data-top={top ? 'true' : undefined}
      title={`${fmtR(r)} a trade over ${n} closed ${n === 1 ? 'trade' : 'trades'} (${fmtR(e.realised_r ?? 0)} in all)${
        top ? ' — the best of every bot shown, so it holds the trophy' : ''
      }${n < 10 ? '. A handful of trades is a lead, not a verdict.' : ''}`}
      className={`flex items-center gap-[5px] text-[13px] font-mono tabular-nums font-medium cursor-default ${pnlCls(r)}`}
    >
      {top && <Trophy size={12} className="text-gold-text shrink-0" />}
      {fmtR(r)}
    </span>
  )
}

/** An empty cell. A dash, never `0` — nothing was measured here. */
function Dash() {
  return <span className="text-[12px] text-text-tertiary cursor-default">—</span>
}

/** What this bot's own closed trades made as a share of the account's CAPITAL — what went in
 *  (deposits less withdrawals) once its bots read the broker's history, its opening balance before.
 *  ⚠ Its own column, never under the dollars: it is a different measurement from R per trade
 *  (the account's size is in it; R is not), and stacked under the P&L the two read as one. */
function ReturnPct({ e, asking }: { e: BotEarnings | undefined; asking: boolean }) {
  if (!e && asking) return <Shimmer className="h-[13px] w-[44px]" />
  if (!e?.traded || e.pct_of_opening == null) return <Dash />
  const p = e.pct_of_opening
  return (
    <span
      data-testid="return-pct"
      title={`${p > 0 ? '+' : ''}${p.toFixed(2)}% — this bot's own closed trades as a share of the account's capital: what went in, deposits less withdrawals (its opening balance where the bots have not read the account's history yet)`}
      className={`text-[13px] font-mono tabular-nums font-medium cursor-default ${pnlCls(p)}`}
    >
      {p > 0 ? '+' : p < 0 ? '−' : ''}
      {Math.abs(p).toFixed(1)}%
    </span>
  )
}

/** How many trades this bot has CLOSED — the sample every figure beside it rests on.
 *  ⚠ `0` is a measurement (its record was read and holds none); a dash means no record. */
function TradeCount({ e, asking }: { e: BotEarnings | undefined; asking: boolean }) {
  if (!e && asking) return <Shimmer className="h-[13px] w-[22px]" />
  if (!e?.traded) return <Dash />
  return (
    <span
      data-testid="trades"
      title={`${e.wins ?? 0} won, ${e.losses ?? 0} lost · recorded ${e.records_from} → ${e.records_to}`}
      className="text-[13px] font-mono tabular-nums text-text-secondary cursor-default"
    >
      {e.closed_trades ?? 0}
    </span>
  )
}

/** One side's score in the live-vs-demo head-to-head. Summed from the bots' own records, so it
 *  is never the account's growth — `scored` counts the bots with a closed trade, `unread` the bots
 *  whose record could not be read, and a side carrying one is PARTIAL. */
interface SideScore {
  key: 'live' | 'demo'
  r: number
  trades: number
  bots: number
  scored: number
  unread: number
}

/**
 * Which side is ahead on R per trade, or nobody.
 *
 * ⚠ **A leader is called only when BOTH sides have closed trades and every bot on both has been
 * read.** "Demo leads" against a live side that has not traded yet is a default, not a result, and
 * a side missing a bot's record is a partial score that could flip once it lands.
 */
function leadOf(live: SideScore, demo: SideScore): 'live' | 'demo' | null {
  const per = (s: SideScore) => (s.trades ? s.r / s.trades : null)
  const pl = per(live)
  const pd = per(demo)
  if (pl == null || pd == null || live.unread || demo.unread || Math.abs(pl - pd) < TIE_R)
    return null
  return pl > pd ? 'live' : 'demo'
}

/**
 * One side's POOLED score, at the end of its own section heading — and only when it pools.
 *
 * 🔴 **It was a pair of tiles above the page, and they went (2026-09-10).** Aaron: *"what is the
 * purpose of this section? If I select demo only then it goes away."* A comparison block has to
 * vanish under a filter; a side's score on its own heading survives one.
 *
 * 🔴 **A pool of ONE scored bot is that bot's own number, so it is withheld** (Aaron, same day:
 * *"we don't need to be redundant on data anywhere on this page"*). A subtotal of one row is a copy
 * of the row, so the heading carries a number only when two or more bots on the side have closed
 * trades; otherwise the bot's own Per trade cell IS the side's score. ⚠ **Nothing is lost**: total R
 * and won/lost went too — the first is this figure times the trade count, the second is on the
 * bot's row tooltip — and the rows already say "no record yet" and "nothing closed", so the heading
 * no longer repeats them. ⚠ **The Leading chip stays either way** — who is ahead is the verdict.
 */
function SideScoreLine({
  side,
  leading,
  asking,
}: {
  side: SideScore
  leading: boolean
  asking: boolean
}) {
  const r = side.scored >= 2 ? side.r / side.trades : null
  // Shimmer only where a pooled number could land — a side with one bot never shows one.
  if (asking && side.bots >= 2 && !side.trades) return <Shimmer className="h-[12px] w-[150px]" />
  return (
    <span
      data-testid={`score-${side.key}`}
      data-leading={leading ? 'true' : undefined}
      className="flex items-baseline gap-[8px] text-[11.5px] cursor-default"
    >
      {r != null && (
        <span data-testid="side-pooled" className="flex items-baseline gap-[8px]">
          <span
            title="R per trade: what each closed trade made on average, in units of the risk it took — every bot on this side pooled."
            className={`text-[14px] font-mono tabular-nums font-semibold ${pnlCls(r)}`}
          >
            {fmtR(r)}
          </span>
          <span className="text-text-tertiary">
            a trade · {side.trades} trades from {side.scored} bots
          </span>
          {side.unread > 0 && (
            <span className="text-warn-text">
              · {side.unread} {side.unread === 1 ? 'record' : 'records'} not read — partial
            </span>
          )}
        </span>
      )}
      {leading && (
        <span
          data-testid="leading"
          title="Ahead of the other side on R per trade — what each closed trade made in units of the risk it took, so account size, risk and how long a side has run cannot decide it."
          className="self-center inline-flex items-center gap-[4px] ml-[4px] px-[7px] py-[2px] rounded-pill text-[10px] font-semibold uppercase tracking-[0.6px] bg-gold-muted text-gold-text border border-gold/40"
        >
          {/* ⚠ NOT the trophy. The trophy marks the one best BOT; this marks the SIDE ahead on
              average — two questions, and the best bot can sit on the side that is behind.
              The same icon for both would read as one winner in two places. */}
          <TrendingUp size={11} /> Leading
        </span>
      )}
    </span>
  )
}

/**
 * Live / demo — TWO independent switches, both ON by default, each turning its side on or off.
 *
 * 🔴 **The pill's look IS its state.** It was a pick-one filter where *no pill pressed* meant both,
 * so the default showed both sides under two pills that looked off — and when the unpressed look
 * was painted in colour, two pills that looked on while neither was (Aaron, 2026-09-10: *"both look
 * selected by default but they are not"*, then *"I should be able to turn on both live and demo at
 * the same time"*). Now on is filled in the side's colour, off is grey with only its dot coloured,
 * and both start on because both are shown.
 *
 * ⚠ **The last side on stays on**: a page switched to show nothing looks exactly like one that
 * failed to load. ⚠ So the URL still holds one of three states (`?kind=` absent = both, or the one
 * side left on) and nothing downstream changed. ⚠ They sit with the tabs, not the actions, because
 * both decide WHAT you are looking at.
 */
function KindFilter({ kind, onPick }: { kind: string | null; onPick: (k: string | null) => void }) {
  return (
    <div className="flex items-center gap-[6px]">
      {(['live', 'demo'] as const).map((k) => {
        const other = k === 'live' ? 'demo' : 'live'
        const on = !kind || kind === k
        const last = kind === k
        const t = KIND_TINT[k]
        const name = KIND_NAME[k]
        return (
          <button
            key={k}
            data-testid={`kind-${k}`}
            aria-pressed={on}
            onClick={() => {
              if (!on) onPick(null)
              else if (!last) onPick(other)
            }}
            title={
              !on
                ? `${name} is off — click to show it too`
                : last
                  ? `${name} is the only side shown — turn ${KIND_NAME[other]} on to add it back`
                  : `Showing ${name} — click to hide it`
            }
            className={`inline-flex items-center gap-[6px] text-[11px] font-semibold uppercase tracking-[0.6px] px-[11px] py-[4px] rounded-pill border transition-colors ${
              on ? t.on : t.off
            } ${last ? 'cursor-default' : ''}`}
          >
            <span className={`w-[7px] h-[7px] rounded-full ${t.dot}`} />
            {k}
          </button>
        )
      })}
    </div>
  )
}

/** A labelled group — one side's accounts, or one kind of unassigned thing — so nothing interleaves. */
function SideSection({
  side,
  label,
  hint,
  aside,
  children,
}: {
  side: string
  label: React.ReactNode
  hint?: React.ReactNode
  aside?: React.ReactNode
  children: React.ReactNode
}) {
  const t = tintOf(side)
  return (
    <section data-testid={`section-${side}`} className="flex flex-col gap-[12px]">
      <div className="flex items-center gap-[9px] px-[2px]">
        {KIND_TINT[side] && <span className={`w-[8px] h-[8px] rounded-full ${t.dot}`} />}
        <span className={`text-[11.5px] font-semibold uppercase tracking-[0.7px] ${t.text}`}>
          {label}
        </span>
        {hint && <span className="text-[11.5px] text-text-tertiary">{hint}</span>}
        <span className="h-px flex-1 bg-border-subtle" />
        {aside}
      </div>
      {children}
    </section>
  )
}

/** What ONE bot's own closed trades came to.
 *
 *  🔴 **This is NOT the account's growth wearing the bot's name.** Every bot on a balance used to
 *  report `total_pnl_pct`, which is the ACCOUNT's move — so a bot deployed yesterday claimed
 *  credit for everything the account had ever done. Aaron, 2026-09-05: *"that 45% increase was
 *  only from the SOS Fade. That should still be showing zero percent from the extreme leg."*
 *
 *  ⚠ **A bot with no record says so in words.** *Never traded* and *no record to read* are
 *  different answers and only one is a measurement; printing a confident `$0.00` for the second
 *  is this repo's rule 1 in a table cell. A record holding no closed trade IS a measurement, so
 *  it reads `$0.00` here and `0` in Trades — "nothing closed" went with the Trades column.
 *
 *  ⚠ **One line.** The return % used to sit under the dollars; it has its own column now. */
function Contribution({ e, asking }: { e: BotEarnings | undefined; asking: boolean }) {
  if (!e && asking) return <Shimmer className="h-[13px] w-[80px]" />
  if (!e) return <Dash />
  if (!e.traded)
    return (
      <span
        title={e.reason ?? 'No record has been read for this bot.'}
        className="text-[11.5px] text-text-tertiary cursor-default"
      >
        no record yet
      </span>
    )
  return (
    <span
      data-testid="bot-pnl"
      title={`What this bot's own closed trades came to · recorded ${e.records_from} → ${e.records_to}${carriedNote(e)}`}
      className={`text-[13px] font-mono tabular-nums font-medium cursor-default ${pnlCls(e.realised_usd)}`}
    >
      {money(e.realised_usd)}
    </span>
  )
}

/** Whose trades on this account a row CARRIES ON from — the bots that left it running the same
 *  strategy (2026-09-11, Aaron: *"if I add back bots on the demo they should just pick up where they
 *  left off"*). The server folds them in; this only names them, so a row never shows a trade count
 *  its own bot did not make without saying whose they are. */
function carriedNote(e: BotEarnings): string {
  const from = e.carried_from ?? []
  if (!from.length) return ''
  return ` · includes ${from
    .map((c) => {
      const n = c.closed_trades ?? 0
      const where = c.moved_to != null ? ` to account ${c.moved_to}` : ''
      return `${n} trade${n === 1 ? '' : 's'} ${c.name} closed here before it moved${where}`
    })
    .join(', and ')}`
}

/** The account's own move, and what it is measured FROM.
 *
 *  ⚠ **The opening balance is on screen beside it.** A percentage with no referent is the defect
 *  the backtest page already recorded: *1439.7x of what*. Here it is worse — two bots on one
 *  balance state different anchors, so the number is only checkable if the page says which one
 *  it divided by and which bot stated it. */
function AccountNet({ e, asking }: { e: AccountEarnings | undefined; asking: boolean }) {
  // ⚠ `net unknown` is a FINDING and may only appear once the box has answered — while it is
  // still being asked, the same words would report a fault that has not happened.
  // Ghost content in the pill's own layout, so it lands on the same baseline as the real one.
  if (!e && asking)
    return (
      <Shimmer shape="pill">
        <span className="inline-flex items-baseline gap-[6px] px-[8px] py-[3px]">
          <span className="text-[13px] font-mono tabular-nums font-semibold">+00.0%</span>
          <span className="text-[11px] font-mono tabular-nums">+$0,000.00</span>
        </span>
      </Shimmer>
    )
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
  // ⚠ A PAST reading says so — "Now" over a balance nothing has read since is a claim about this
  // moment that nothing measured. Worded to be true whether its bots left or have not reported yet.
  const then = e.balance_read_at
    ? `Last read at ${money(e.balance, false)} on ${readTime(e.balance_read_at)} — nothing on it has reported one since.`
    : `Now ${money(e.balance, false)}.`
  // 🔴 On the DEPOSITS basis the net is the balance less what went IN and the % is time-weighted,
  // so a deposit or a withdrawal is never a return (2026-09-12). The referent is the money put in:
  // an account opened at $451.97 and topped up to $10,312.48 is measured against the $10,312.48.
  const from =
    e.net_basis === 'deposits' && e.capital_in != null
      ? `${money(e.capital_in, false)} put in (deposits less withdrawals). The % is time-weighted, so a deposit or a withdrawal never counts as a return.`
      : `Opened at ${money(e.opening_balance, false)}${
          openingRecorder(e) ? `, recorded by ${openingRecorder(e)}` : ''
        }.`
  return (
    <span
      title={`${from} ${then}`}
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
  // 🔴 `=== false`, never falsy. An older payload carries no such field, and reading a missing
  // one as "the record is behind" would put a caveat on every split that never needed it.
  const provisional = e.records_live === false
  return (
    <div className="flex flex-col gap-[3px] px-4 py-[9px] border-t border-border-subtle bg-bg-sunken/40">
      <div className="flex items-center gap-[10px]">
        <span className="text-[11px] text-text-tertiary">Not from these bots</span>
        <span className={`text-[12px] font-mono tabular-nums ${pnlCls(e.unattributed_usd)}`}>
          {money(e.unattributed_usd)}
        </span>
        <span className="text-[10.5px] text-text-tertiary">
          {/* On the deposits basis a deposit or a withdrawal is already out of the net, so it is not
           *  one of the causes this line may name (2026-09-12). */}
          {missing > 0
            ? `— a manual fill, ${e.net_basis === 'deposits' ? '' : 'a deposit, '}or ${missing === 1 ? 'a bot whose record has' : `${missing} bots whose records have`} not arrived`
            : `— a manual fill, ${e.net_basis === 'deposits' ? '' : 'a deposit, '}or a trade older than the record`}
        </span>
      </div>
      {provisional && e.attribution_note && (
        <span className="text-[10.5px] text-gold-text">{e.attribution_note}</span>
      )}
    </div>
  )
}

/** The labels over a card's bot rows — ONE component for the real card and its placeholder, on
 *  the same column template, so neither can end up with a heading over the wrong column.
 *  ⚠ One set of headings for every card, whether its bots are on it or have left: an account
 *  whose card changed shape when its bots moved is the defect this page was fixed for. */
function ColumnHeadings() {
  return (
    <div
      className={`grid ${GRID} items-center gap-3 pr-4 py-[6px] border-b border-border-subtle bg-bg-sunken/50 text-[9.5px] font-semibold uppercase tracking-[0.7px] text-text-tertiary`}
    >
      <span className="pl-4">Bot</span>
      <span title="What this bot's own closed trades came to">P&amp;L</span>
      <span title="Return % — this bot's own closed trades as a share of the account's capital: what went in, deposits less withdrawals (its opening balance where the bots have not read the account's history yet)">
        Return %
      </span>
      <span title="How many trades this bot has closed — the sample every figure beside it rests on">
        Trades
      </span>
      <span title="R per trade — what each closed trade made on average, in units of the risk it took. The top bot is picked on this, never on dollars.">
        Per trade
      </span>
      <span>Version</span>
      <span title="Risk per trade">Risk</span>
      <span>Uptime</span>
      <span />
      <span className="text-right">Actions</span>
    </div>
  )
}

/** The page before the ACCOUNT LIST has answered: one account card, the shape the real one will
 *  take, built on the same column template so the swap does not shift a pixel. It is on screen
 *  only for the local read of the instance configs; the slow part — the trading box — shimmers
 *  inside the real cards instead, because the account list does not have to wait for it. */
function BotsPageSkeleton() {
  return (
    <div
      aria-busy="true"
      aria-label="Loading bots"
      data-testid="bots-skeleton"
      className="bg-bg-surface border border-border-subtle rounded-lg overflow-hidden"
    >
      <div className="flex items-center gap-3 px-4 py-[13px]">
        <Shimmer className="h-[15px] w-[92px]" />
        <Shimmer className="h-[13px] w-[64px]" />
        <Shimmer shape="pill" className="h-[22px] w-[64px]" />
        {/* The SAME loading states the real card renders — never a private copy of them. */}
        <span className="ml-auto flex items-baseline gap-[10px]">
          <span className="text-[17px] font-mono tabular-nums font-medium">
            <Shimmer>$00,000.00</Shimmer>
          </span>
          <AccountNet e={undefined} asking />
        </span>
      </div>
      <div className="border-t border-border-subtle">
        {/* The headings are fixed words, so they are REAL, not shimmered — a placeholder stands in
         *  for what is not known yet, never for what already is. */}
        <ColumnHeadings />
        {[0, 1].map((i) => (
          <div
            key={i}
            className={`grid ${GRID} items-center gap-3 pr-4 py-[10px] ${
              i > 0 ? 'border-t border-border-subtle' : ''
            }`}
          >
            <span className="flex items-center gap-[9px] pl-4">
              <Shimmer shape="dot" className="h-[7px] w-[7px]" />
              <Shimmer className="h-[13px] w-[96px]" />
            </span>
            <Contribution e={undefined} asking />
            <ReturnPct e={undefined} asking />
            <TradeCount e={undefined} asking />
            <PerTrade e={undefined} asking top={false} />
            <VersionPill version={undefined} loading />
            <Shimmer className="h-[12px] w-[26px]" />
            <Shimmer className="h-[12px] w-[44px]" />
            <span />
            <span className="flex gap-[3px] justify-end">
              <Shimmer className="h-[26px] w-[26px]" />
              <Shimmer className="h-[26px] w-[26px]" />
              <Shimmer className="h-[26px] w-[26px]" />
              <Shimmer className="h-[26px] w-[92px] ml-[6px]" />
            </span>
          </div>
        ))}
      </div>
    </div>
  )
}

export function Bots() {
  const { data: snapshot, isLoading, isFetching, error, dataUpdatedAt, refetch } = useBotSnapshot()
  const { data: accountGroups, isPending: accountsPending } = useBotAccounts()
  const { data: registry, isPending: registryPending } = useRegisteredAccounts()
  // 🔴 THE TRADING BOX HAS NOT ANSWERED YET — its FIRST read is in flight. This is the only thing
  // the snapshot shimmers decide on, and it is deliberately NOT `!snapshot`: a snapshot that
  // FAILED is also absent, and shimmering over a dead link would make a page that looks busy for
  // ever while the box is down. Once the read fails, the words (`unknown`, `balance unread`) and
  // the error line take over; once it answers, the numbers do. A 60s background refetch keeps the
  // numbers on screen and never shimmers.
  const asking = isLoading
  const { data: users } = useUsers()
  const [params, setParams] = useSearchParams()

  const [logBot, setLogBot] = useState<string | null>(null)
  const [syncOpen, setSyncOpen] = useState(false)
  // Which bot is mid start/stop/restart, and WHICH of the three — the pill names the action.
  const [pending, setPending] = useState<{ key: string; action: BotAction } | null>(null)

  const startOne = useBotStartOne()
  const stopOne = useBotStopOne()
  const restartOne = useBotRestartOne()
  const busy = startOne.isPending || stopOne.isPending || restartOne.isPending
  useEffect(() => {
    if (!busy) setPending(null)
  }, [busy])

  const bots: BotStatus[] = snapshot?.bots ?? []
  // 🔴 The version reads are keyed off the CONFIG list as well as the snapshot (2026-09-10). A
  // version needs only the bot's key, and the config list answers in milliseconds — keyed off the
  // snapshot alone, the ~4.5s version reads could not START until the ~4s snapshot had finished,
  // so the column waited for both back to back, and until then every pill said "No version"
  // (a finding) instead of loading. Now they run side by side with the snapshot.
  const fleetKeys = [
    ...new Set([
      ...(accountGroups ?? []).flatMap((g) => g.bots.map((b) => b.key)),
      ...bots.map((b) => b.key),
    ]),
  ]
  const versionQueries = useBotVersions(fleetKeys)
  const versionByKey = new Map(fleetKeys.map((k, i) => [k, versionQueries[i]]))
  // 🔴 Every bot's deploy is watched HERE, on the page, never inside the drawer (2026-09-10) — a
  // drawer closed mid-deploy stopped the watch, so the row said "behind" through the whole deploy
  // and the finish went unnoticed. The row's pill and the drawer both read this one watch.
  const jobQueries = usePromoteJobs(fleetKeys)
  const jobByKey = new Map(fleetKeys.map((k, i) => [k, jobQueries[i]?.data]))

  const statusByKey = new Map<string, string>(bots.map((b) => [b.key, b.status]))
  const botByKey = new Map(bots.map((b) => [b.key, b]))

  // Selection lives in the URL, like every other view state in this app, so a link to one bot is
  // a real link and a refresh does not move you to a different bot's Deploy button.
  const view = params.get('view')
  // Which sides are ON, in the URL like every other view state here — so a link to "just the live
  // accounts" is a real link and a refresh does not put the demos back. Absent = both on; `live`
  // or `demo` = the one side left on. ⚠ **Both on is the default**: every account on this box is a
  // demo today, so opening on live alone would show an empty page, which looks like a failed load.
  // ⚠ Anything else in the parameter reads as both — a hand-typed value may not hide the fleet.
  const kindParam = params.get('kind')
  const kind = kindParam === 'live' || kindParam === 'demo' ? kindParam : null
  // Which tab. ⚠ Absent means TRADING — the first look is the accounts that have bots on them.
  const show = params.get('show') === 'unassigned' ? 'unassigned' : 'trading'
  const selBot = params.get('bot') ? (botByKey.get(params.get('bot') as string) ?? null) : null
  const selAccount = params.get('account')

  const set = (k: string, v: string | null) => {
    const next = new URLSearchParams(params)
    if (v === null) next.delete(k)
    else next.set(k, v)
    // Only one drawer at a time — opening a bot closes an account and the reverse.
    if (k === 'bot' && v !== null) next.delete('account')
    if (k === 'account' && v !== null) next.delete('bot')
    // "Add a bot" opens the account's panel with its picker already out; closing the panel ends it.
    if (k === 'account') next.delete('add')
    setParams(next, { replace: true })
  }
  /** Open an account's panel straight into its bot picker — the card's "Add a bot". */
  const openToAdd = (account: number) => {
    const next = new URLSearchParams(params)
    next.set('account', String(account))
    next.set('add', '1')
    next.delete('bot')
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
  const balanceOf = (rows: { live: BotStatus | undefined }[]) =>
    rows.find((r) => r.live?.balance != null)?.live?.balance ?? null

  /**
   * Accounts that have bots, then the unassigned, then the empty ones as one-liners.
   *
   * 🔴 **A ROW IS THE CONFIG, AND THE VPS READING IS ATTACHED TO IT (2026-09-06).** It used to be
   * the snapshot row alone, dropped when the snapshot did not carry it — so an account whose bots
   * the box had not answered for **did not render at all**, and while the trading box was
   * unreachable this page showed no accounts whatsoever. The account list needs no VPS: it is read
   * from the instance configs, and reporting nothing because a *different* source is quiet is the
   * page telling you there are no accounts.
   *
   * ⚠ **`live` is undefined when the box has not answered, and that is a THIRD state** — not
   * stopped. Every reader below has to branch on it rather than on `status === 'RUNNING'`, or a
   * dead link renders as a quiet fleet, which is this repo's oldest rule.
   */
  const trading: {
    account: number
    group: BotAccountGroup
    rows: { cfg: BotAccountBot; live: BotStatus | undefined }[]
  }[] = []
  for (const [account, group] of groupByAccount) {
    if (!group.bots.length) continue
    trading.push({
      account,
      group,
      rows: group.bots.map((b) => ({ cfg: b, live: botByKey.get(b.key) })),
    })
  }
  /**
   * An account bots TRADED on and then left — the demo account a set went live from. It is an
   * account on the Trading tab like any other, with no bot on it yet (2026-09-11).
   *
   * 🔴 **Not a separate "history" card, and not an entry under Unassigned.** Aaron: *"moving bots
   * to live doesn't mean we don't trade on the demo still… it shouldn't matter."* Its record is the
   * evidence the promotion was made on and the demo score reads it, and it is still an account you
   * can put the next bot on. ⚠ It has no group in the config grouping (no bot names it), so the
   * registry row stands in for one — the same group the drawer builds for an empty account.
   */
  for (const e of snapshot?.earnings ?? []) {
    if (groupByAccount.get(e.account)?.bots.length) continue
    if (!e.bots.some((b) => b.former && b.closed_trades)) continue
    const reg = regByAccount.get(e.account)
    // ⚠ An account nobody registered still carries its record — `emptyGroup` reads only the
    // number and the server off what it is handed, so the bare pair is enough.
    const group =
      groupByAccount.get(e.account) ??
      emptyGroup(reg ?? ({ account: e.account, server: '' } as BotAccountRegistration))
    trading.push({ account: e.account, group, rows: [] })
  }
  const assigned = new Set(trading.flatMap((a) => a.rows.map((r) => r.cfg.key)))
  const onTrading = new Set(trading.map((a) => a.account))
  /**
   * Bots whose instance config could NOT BE READ — a fault, not a resting state.
   *
   * 🔴 **They were folded in with the deliberately-benched ones (fixed 2026-09-06)**, under a
   * heading reading *trades nothing until you give it one* — which is an instruction that cannot
   * fix a broken file, and it is the one sentence the reader acts on. The grouping has always
   * kept these apart (its own type says so: one is a state somebody chose, the other is a fault),
   * and this page was the only place merging them again.
   */
  const unreadable = new Set(
    (accountGroups ?? [])
      .filter((g) => g.kind === 'unknown')
      .flatMap((g) => g.bots.map((b) => b.key))
  )
  const unassigned = bots.filter((b) => !assigned.has(b.key) && !unreadable.has(b.key))
  const broken = bots.filter((b) => unreadable.has(b.key))
  // ⚠ Not an account on the Trading tab — one place per account, never both.
  const emptyAccounts = (registry ?? []).filter((a) => !onTrading.has(a.account))

  // ⚠ Filtered LAST, on the assembled lists, so the derivations above stay the whole truth —
  // `assigned` in particular decides which bots count as unassigned, and computing that against
  // a filtered set would invent bots with no account whenever a filter was on.
  const keep = (t: string | undefined) => !kind || t === kind
  /** Demo or live. The VPS row is the first answer; the registry is the fallback, because the
   *  live-vs-demo FILTER must not silently drop every account while the box is quiet. Neither
   *  answers ⇒ `undefined`, which the filter reads as unknown rather than as demo. */
  const typeOf = (account: number, rows: { live: BotStatus | undefined }[]) =>
    rows.find((r) => r.live?.account_type)?.live?.account_type ?? regByAccount.get(account)?.kind
  const shownAccounts = trading.filter((a) => keep(typeOf(a.account, a.rows)))
  const shownEmpty = emptyAccounts.filter((a) => keep(a.kind))
  const shownUnassigned = unassigned.filter((b) => keep(b.account_type))
  const shownBroken = broken.filter((b) => keep(b.account_type))
  // Per TAB, so the note under each one counts only what that tab would have shown.
  const hiddenByFilter =
    show === 'trading'
      ? trading.length - shownAccounts.length
      : emptyAccounts.length - shownEmpty.length + (unassigned.length - shownUnassigned.length)
  // ⚠ A switched-off side that empties the page must SAY it did. A blank list and a fleet that
  // really is empty look identical, and only one of them is a finding. One note, both tabs.
  const filterNote = kind && hiddenByFilter > 0 && (
    <p data-testid="filter-note" className="text-[11.5px] text-text-tertiary px-[2px]">
      {hiddenByFilter} {hiddenByFilter === 1 ? 'account or bot is' : 'accounts and bots are'} hidden
      because{' '}
      <span className="text-text-secondary">{KIND_NAME[kind === 'live' ? 'demo' : 'live']}</span> is
      off.{' '}
      <button onClick={() => set('kind', null)} className="text-accent hover:underline">
        Show both
      </button>
    </p>
  )

  const running = bots.filter((b) => b.status === 'RUNNING').length

  // 🔴 Computed SERVER-SIDE and only rendered here. What an account made and what its bots made
  // are two different measurements, and whether they agree is the finding — deriving either in
  // the browser would be the same rule written twice in two languages, which is how the risk
  // share total already drifted once on this very page.
  const earnByAccount = new Map((snapshot?.earnings ?? []).map((e) => [e.account, e]))
  // 🔴 KEYED BY ACCOUNT AND BOT, never by bot alone (2026-09-11). A bot that moved has a row on
  // each account it traded — its demo record on demo, its live one on live — and a bot-keyed map
  // handed every row whichever entry came last, which put the demo trades under the live heading.
  const earnAt = new Map(
    (snapshot?.earnings ?? []).flatMap((e) =>
      e.bots.map((b) => [`${e.account}:${b.bot_key}`, b] as const)
    )
  )
  const earnOf = (account: number | string | null | undefined, key: string) =>
    account == null || account === '' ? undefined : earnAt.get(`${Number(account)}:${key}`)
  /** The account a bot's CONFIG names — what the rows are laid out by, so the bot's panel reads
   *  the record of the account its row sits under. The box's report is the fallback. */
  const accountOfBot = (key: string) =>
    trading.find((a) => a.rows.some((r) => r.cfg.key === key))?.account ?? null

  /**
   * An account's balance, and — when it is a PAST reading — when it was read.
   *
   * 🔴 **One answer for the card, the panel and the header count (2026-09-11).** The bots on it
   * report the balance live; when none of them has — no bot is on it, or the ones on it have not
   * reported since they started — it is the last one a bot read here, served WITH its time. It fell
   * back only for an account NO bot is on, so adding the first bot to the demo account blanked a
   * balance that had been on screen a minute earlier, until the new bot's first report.
   */
  const balanceAt = (account: number, live: number | null) => {
    if (live != null) return { balance: live, readAt: null as string | null }
    const e = earnByAccount.get(account)
    return { balance: e?.balance ?? null, readAt: e?.balance_read_at ?? null }
  }
  // ⚠ Only accounts a bot is ON can have an unread balance — one with no bot has nothing to read
  // it, and counting it would raise a warning about a healthy fleet.
  const unread = trading.filter(
    (a) => a.rows.length && balanceAt(a.account, balanceOf(a.rows)).balance == null
  ).length

  // The open account panel's balance, exactly as its card shows it.
  const selNum = selAccount ? Number(selAccount) : null
  const selOnIt = selNum != null ? (groupByAccount.get(selNum)?.bots ?? []) : []
  const selEarn = selNum != null ? earnByAccount.get(selNum) : undefined
  const { balance: selBalance, readAt: selReadAt } =
    selNum != null
      ? balanceAt(
          selNum,
          selOnIt.length ? balanceOf(selOnIt.map((b) => ({ live: botByKey.get(b.key) }))) : null
        )
      : { balance: null, readAt: null }

  // ── live against demo ─────────────────────────────────────────────────────
  /** Which side an account sits on. ⚠ While neither the box nor the registry has answered, its
   *  type is still being ASKED — filing it under "neither" would move the card between sections
   *  the moment the answer lands, so it waits in a section of its own with a shimmering heading. */
  type Side = 'pending' | 'live' | 'demo' | 'other'
  const sideOf = (t: string | undefined): Side =>
    t === 'live'
      ? 'live'
      : t === 'demo'
        ? 'demo'
        : t === undefined && (asking || registryPending)
          ? 'pending'
          : 'other'
  // Real money first. ⚠ "Neither" is a section, never a silent drop: an account whose type nobody
  // stated still has to be on the page.
  const SECTIONS: { key: Side; label: React.ReactNode }[] = [
    { key: 'pending', label: <Shimmer className="h-[10px] w-[70px]" /> },
    { key: 'live', label: 'Live · real money' },
    { key: 'demo', label: 'Demo' },
    { key: 'other', label: 'Not marked demo or live' },
  ]

  /** One side's score, summed from its bots' OWN records — never from the account's growth, which
   *  carries money no bot here made. A bot whose record could not be read makes the side PARTIAL. */
  const scoreOf = (key: 'live' | 'demo'): SideScore => {
    const s: SideScore = { key, r: 0, trades: 0, bots: 0, scored: 0, unread: 0 }
    const add = (e: BotEarnings | undefined) => {
      s.bots += 1
      if (!e?.traded) {
        s.unread += 1
        return
      }
      if (e.closed_trades && e.realised_r != null) {
        s.r += e.realised_r
        s.trades += e.closed_trades
        s.scored += 1
      }
    }
    for (const a of trading) {
      if (sideOf(typeOf(a.account, a.rows)) !== key) continue
      for (const { cfg } of a.rows) add(earnOf(a.account, cfg.key))
      // 🔴 The record of bots that have LEFT an account still belongs to its side — the demo trades
      // a set was promoted on are what its live trades are compared against. ⚠ On EVERY account,
      // including one a new bot has joined: it used to be read only off an account with no bot on
      // it, so putting the next bot on demo dropped the whole departed record from the score.
      for (const b of earnByAccount.get(a.account)?.bots ?? []) if (b.former) add(b)
    }
    return s
  }

  // 🔴 From EVERY account, never the filtered ones: a filter changes what is on screen, and a side's
  // score or who leads changing with it would be the filter talking.
  const liveScore = scoreOf('live')
  const demoScore = scoreOf('demo')
  const lead = leadOf(liveScore, demoScore)

  /** The bot holding the trophy: best R per trade among the bots shown. ⚠ Only when there is a
   *  CONTEST — two bots with a score, a clear gap between the first two, and every shown bot's
   *  record read. One bot alone, a tie, or a missing record all leave the trophy unawarded. */
  const shownRows = shownAccounts.flatMap((a) => a.rows.map((r) => ({ ...r, account: a.account })))
  const ranked = shownRows
    .map(({ cfg, account }) => ({ key: cfg.key, r: perTradeOf(earnOf(account, cfg.key)) }))
    .filter((x): x is { key: string; r: number } => x.r != null)
    .sort((a, b) => b.r - a.r)
  const allRead = shownRows.every(({ cfg, account }) => earnOf(account, cfg.key)?.traded)
  const topBot =
    allRead && ranked.length >= 2 && ranked[0].r - ranked[1].r >= TIE_R ? ranked[0].key : null

  // ⚠ THERE IS DELIBERATELY NO FLEET TOTAL HERE ANY MORE (2026-09-06). Summing balances across
  // ACCOUNTS was correct — two bots on one balance share one pot, and summing across BOTS is what
  // added the same money twice on 2026-09-04 — but the figure was a second copy of what each
  // account already states. It came off with the header line it fed. If a fleet total is ever
  // wanted again, sum per ACCOUNT and leave an unmeasured one OUT rather than folding it in as
  // zero; that is the part that was hard to get right.

  function act(key: string, action: BotAction, fn: () => void) {
    setPending({ key, action })
    fn()
  }

  /** One account's card: its heading, then one row per bot. A function rather than inline JSX
   *  because the live and demo sections both draw it — one card, never a copy per section. */
  const renderAccount = ({ account, group, rows }: (typeof trading)[number]) => {
    const cap = group.cap_agrees ? group.risk_cap_pct : null
    const reg = regByAccount.get(account)
    const earn = earnByAccount.get(account)
    // With nothing on it reporting, the balance is the LAST one a bot read here, with its time —
    // never a live figure, and the card says so beside it. See `balanceAt`.
    const idle = rows.length === 0
    const { balance, readAt } = balanceAt(account, idle ? null : balanceOf(rows))
    // The bots that TRADED here and left, as rows under the ones on it now.
    const past = (earn?.bots ?? []).filter((b) => b.former)
    // 🔴 NO COLOURED EDGE, AND NO LIVE/DEMO CHIP (2026-09-10, Aaron: *"we don't need to be
    // redundant on data anywhere on this page"*). The edge was green when the account was up and
    // red when down — the sign the net pill beside the balance already carries in the same colours.
    // The chip said live or demo under a section heading that says it. Each was a second copy of a
    // fact on screen. ⚠ Unknown-kind accounts lose nothing: they sit under their own heading.
    return (
      <div
        key={account}
        data-testid="account-card"
        className="bg-bg-surface border border-border-subtle rounded-lg overflow-hidden"
      >
        <button
          onClick={() => set('account', String(account))}
          title="Open this account — balance, risk cap, and which bots are on it"
          className="w-full flex items-center gap-3 px-4 py-[13px] text-left hover:bg-bg-surface-2 transition-colors"
        >
          {/* 🔴 THE NUMBER LEADS (2026-09-06, Aaron: *"the account number should be the
           *  thing prefix in the account"*). The login is what the broker, the terminal,
           *  the instance config and every refusal message name it by; the label is a
           *  nickname somebody typed here. When the two disagree the number is the one
           *  that is right, so it is the one the eye lands on first. */}
          <span className="text-[14px] font-mono font-semibold tabular-nums">{account}</span>
          {/* The broker name comes off the registry, which asks the box whether a
           *  password is stored and so is slow — until it answers, the fallback
           *  "Account N" would be a guess at a name, so the name shimmers instead. */}
          {!reg && registryPending ? (
            <Shimmer className="h-[13px] w-[64px]" />
          ) : (
            <span className="text-[13px] text-text-secondary">{nameOf(reg, group)}</span>
          )}

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
          {/* 🔴 **THREE states, and collapsing two of them was a live defect (fixed
           *  2026-09-06).** A DISAGREEMENT rendered as `no cap`, whose own tooltip said
           *  *nothing here refuses a trade for being too large* — the opposite of what
           *  is true. When the bots on one balance state different ceilings, NONE of
           *  them will start, so the account is not uncapped, it is broken. **Rule 1 in
           *  a chip: *nobody set one* and *they cannot agree* are different facts and
           *  only one of them is safe to read as quiet.**
           *
           *  ⚠ **A figure is never quoted while they disagree** — `cap` is already
           *  forced to null above, because printing one bot's number would name a
           *  ceiling nothing is running. ⚠ The drawer carries the same finding with the
           *  fix beside it; this is the half a reader sees without opening anything.
           *
           *  ⚠ **No chip at all while no bot is on the account.** The ceiling is stored on each
           *  bot, so with none there is no cap to state — and "no cap" in warn over an account
           *  nothing is trading is an alarm about nothing. It returns with the first bot. */}
          {idle ? null : !group.cap_agrees ? (
            <span
              data-testid="cap-chip"
              title="The bots on this account do not state the same risk ceiling, so none of them will start. Open the account to set one figure for all of them."
              className="inline-flex items-center text-[10.5px] font-semibold px-[7px] py-[3px] rounded-pill uppercase tracking-[0.4px] bg-neg-muted text-neg-text border border-neg/40 cursor-default"
            >
              cap disagreement
            </span>
          ) : cap == null ? (
            <span
              data-testid="cap-chip"
              title="No risk ceiling is set on this account — nothing here refuses a trade for being too large."
              className="inline-flex items-center text-[10.5px] font-semibold px-[7px] py-[3px] rounded-pill uppercase tracking-[0.4px] bg-warn-muted text-warn-text border border-warn/40 cursor-default"
            >
              no cap
            </span>
          ) : (
            <span
              data-testid="cap-chip"
              title={`Open risk across every bot on this account is capped at ${cap}% of its balance.`}
              className="inline-flex items-baseline gap-[4px] text-[11px] px-[7px] py-[3px] rounded-pill bg-gold-muted border border-gold/30 cursor-default"
            >
              <span className="font-mono tabular-nums font-semibold text-gold-text">{cap}%</span>
              <span className="text-[10px] text-gold-text/70 uppercase tracking-[0.4px]">cap</span>
            </span>
          )}

          <span className="ml-auto flex items-baseline gap-[10px]">
            <span className="text-[17px] font-mono tabular-nums font-medium">
              {/* ⚠ `balance unread` is a warning and is only true once the box has
               *  answered without one — while it is still being asked it shimmers. */}
              {balance == null && asking ? (
                <Shimmer>$00,000.00</Shimmer>
              ) : balance == null && idle ? (
                // Not a fault: nothing is on the account to read it, and no bot that left it
                // took a reading. Grey, never the warning a silent bot earns.
                <span
                  title="No bot is on this account, and none that traded here left a reading of its balance."
                  className="text-[12px] text-text-tertiary"
                >
                  balance not read
                </span>
              ) : balance == null ? (
                <span className="text-[12px] text-warn-text">balance unread</span>
              ) : readAt ? (
                <span
                  title={
                    idle
                      ? `The last balance a bot read here, on ${readTime(readAt)}, before it left. No bot is on this account now, so nothing reads it live.`
                      : `The last balance a bot read here, on ${readTime(readAt)}. No bot on this account has reported one since it started, so this is not a live figure yet.`
                  }
                  className="inline-flex items-baseline gap-[7px] cursor-default"
                >
                  {money(balance, false)}
                  <span
                    data-testid="balance-read-at"
                    className="text-[10.5px] font-sans font-normal text-text-tertiary"
                  >
                    read {readTime(readAt)}
                  </span>
                </span>
              ) : (
                money(balance, false)
              )}
            </span>
            <AccountNet e={earn} asking={asking} />
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
           *  that is confidently over the wrong number is worse than none. The loading
           *  placeholder renders the same component for the same reason. */}
          <ColumnHeadings />
          {rows.map(({ cfg, live }, i) => {
            const be = earnOf(account, cfg.key)
            // ⚠ THREE states. `asked` is whether the box answered for this bot at all —
            // an unanswered snapshot is not a stopped bot, and the controls below branch
            // on it rather than on `running`, so nothing offers Start for a bot whose
            // state nobody knows.
            const asked = live !== undefined
            const running = live?.status === 'RUNNING'
            // The NAME comes from the config, which is always readable — a bot the box
            // has not answered for still has one, and falling back to its key would make
            // an unreachable box look like a page full of unknown bots.
            const name = live?.name ?? cfg.display
            return (
              <div
                key={cfg.key}
                data-testid="bot-row"
                data-bot={cfg.key}
                className={`group grid ${GRID} items-center gap-3 pr-4 py-[10px] transition-colors hover:bg-bg-surface-2 ${
                  i > 0 ? 'border-t border-border-subtle' : ''
                }`}
              >
                {/* The NAME is the button, not the whole row — the row now carries
                 *  four controls and a row-wide click behind them makes every miss
                 *  open a drawer over the thing you were aiming at. */}
                <button
                  onClick={() => set('bot', cfg.key)}
                  title={`Open ${name} — risk, version, account and its settings`}
                  className="flex items-center gap-[9px] font-medium text-[13px] text-left min-w-0 pl-4"
                >
                  {/* ⚠ NO identity rail here. It was a 3px bar per bot and Aaron read it
                   *  as meaningless decoration — which it was, on a row that already
                   *  names the bot.
                   *
                   *  🔴 **THREE states, not two (2026-09-06).** Red meant *stopped* and
                   *  was also what an UNANSWERED box drew — so a dead link to the VPS
                   *  rendered as a fleet sitting quietly, which is the failure this repo
                   *  keeps paying for. Unknown is hollow and says so on hover. */}
                  {/* A FOURTH look for the first read: shimmering, it is still being
                   *  asked; hollow, it was asked and nobody answered. */}
                  {!asked && asking ? (
                    <Shimmer shape="dot" className="h-[7px] w-[7px]" />
                  ) : (
                    <span
                      title={
                        asked
                          ? running
                            ? 'Running'
                            : 'Stopped'
                          : 'The trading box has not answered for this bot — its state is unknown, not stopped.'
                      }
                      className={`inline-block w-[7px] h-[7px] rounded-full shrink-0 ${
                        !asked
                          ? 'border border-text-tertiary'
                          : running
                            ? 'bg-pos shadow-[0_0_7px_#00ff7f]'
                            : 'bg-neg'
                      }`}
                    />
                  )}
                  <span className="truncate group-hover:text-accent transition-colors">{name}</span>
                  {live?.mt5_link === false && <NoLinkChip />}
                  {live?.trade_allowed === false && <TradingOffChip reason={live.trade_block} />}
                  {live?.review && <ReviewChip review={live.review} />}
                </button>

                {/* 🔴 The money sits NEXT TO THE NAME, not out at the far edge with the
                 *  machinery. It is the answer to the question this row is read with —
                 *  what has this bot done — and 400px of empty grid between the two made
                 *  the row read as a name with some settings after it. */}
                <Contribution e={be} asking={asking} />
                <ReturnPct e={be} asking={asking} />
                <TradeCount e={be} asking={asking} />
                <PerTrade e={be} asking={asking} top={topBot === cfg.key} />

                <VersionPill
                  version={versionByKey.get(cfg.key)?.data}
                  loading={versionByKey.get(cfg.key)?.isPending}
                  deploying={jobByKey.get(cfg.key)?.status === 'running'}
                  error={versionByKey.get(cfg.key)?.error}
                />

                <span
                  title="Risk per trade — its share of this account's ceiling"
                  className="text-[12px] font-mono text-text-secondary cursor-default"
                >
                  {typeof cfg.risk_pct === 'number' ? `${cfg.risk_pct}%` : '—'}
                </span>

                <span
                  title="How long it has been running without a restart"
                  className="text-[12px] font-mono text-text-tertiary cursor-default"
                >
                  {live?.uptime_seconds != null ? (
                    formatUptime(live.uptime_seconds)
                  ) : !asked && asking ? (
                    <Shimmer className="h-[12px] w-[44px]" />
                  ) : (
                    '—'
                  )}
                </span>

                <span />

                <span className="flex gap-[3px] justify-end">
                  {/* 🔴 **NOTHING IS OFFERED WHILE THE STATE IS UNKNOWN (2026-09-06).**
                   *  The old branch was `running ? stop/restart : start`, so a bot the box
                   *  had not answered for was handed a START button — and pressing start
                   *  on a bot that is already trading is the one mistake this row can
                   *  make that costs money. An unanswered box is a reason to ask again,
                   *  never a reason to act. */}
                  {pending?.key === cfg.key ? (
                    <BotActionPill action={pending.action} />
                  ) : !asked && asking ? (
                    // The Start/Stop controls are withheld until the state is known —
                    // their SHAPE stands in, so the row's actions do not jump when they
                    // land. Still nothing to press: an unknown state offers no action.
                    <>
                      <Shimmer className="h-[26px] w-[26px]" />
                      <Shimmer className="h-[26px] w-[26px]" />
                    </>
                  ) : !asked ? (
                    <span
                      title="The trading box has not answered for this bot, so there is nothing safe to offer here — its state is unknown, not stopped."
                      className="text-[11px] text-text-tertiary pr-1 cursor-default"
                    >
                      unknown
                    </span>
                  ) : running ? (
                    <>
                      <IconBtn
                        icon={Square}
                        title="Stop"
                        tone="neg"
                        disabled={busy}
                        onClick={() => act(cfg.key, 'stop', () => stopOne.mutate(cfg.key))}
                      />
                      <IconBtn
                        icon={RotateCcw}
                        title="Restart"
                        disabled={busy}
                        onClick={() => act(cfg.key, 'restart', () => restartOne.mutate(cfg.key))}
                      />
                    </>
                  ) : (
                    <IconBtn
                      icon={Play}
                      title="Start"
                      tone="pos"
                      disabled={busy}
                      onClick={() => act(cfg.key, 'start', () => startOne.mutate(cfg.key))}
                    />
                  )}
                  {/* Hidden while this bot's pill shows — the pill needs the room (see
                   *  `BotActionPill`). The drawer keeps its own Logs button throughout. */}
                  {pending?.key !== cfg.key && (
                    <IconBtn icon={FileText} title="Logs" onClick={() => setLogBot(cfg.key)} />
                  )}
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
                      set('bot', cfg.key)
                    }}
                    title={`Configure ${name} — risk per trade, version, account and all its settings`}
                    className="flex items-center gap-[5px] ml-[6px] px-[9px] h-[26px] rounded-md border border-border-default text-[11.5px] text-text-secondary hover:text-text-primary hover:border-accent/50 hover:bg-accent-muted transition-colors"
                  >
                    <SlidersHorizontal size={11} />
                    Configure
                  </button>
                </span>
              </div>
            )
          })}

          {/* No bot on it now — and that is an invitation, not a tombstone. The demo account a
           *  set went live from is where the next bot gets tried, so the way to put one there is
           *  on the card rather than a drawer away. ⚠ Disabled with the reason, never hidden, when
           *  the account cannot take a bot (no terminal logged into it). */}
          {idle && (
            <div
              data-testid="no-bot-row"
              className={`grid ${GRID} items-center gap-3 pr-4 py-[10px]`}
            >
              <span className="col-span-9 flex items-center gap-[9px] pl-4 text-[12.5px] text-text-tertiary">
                <span className="inline-block w-[7px] h-[7px] rounded-full shrink-0 border border-text-tertiary/60" />
                No bot is on this account now
              </span>
              <span className="flex justify-end">
                {reg && (
                  <button
                    data-testid="add-bot-here"
                    disabled={!reg.assignable}
                    onClick={() => openToAdd(account)}
                    title={
                      reg.assignable
                        ? 'Put a bot on this account'
                        : `Cannot add a bot here — ${reg.unassignable_reason || 'this account is not assignable'}.`
                    }
                    className="flex items-center gap-[5px] px-[9px] h-[26px] rounded-md border border-border-default text-[11.5px] text-text-secondary hover:text-text-primary hover:border-accent/50 hover:bg-accent-muted transition-colors disabled:opacity-40 disabled:cursor-not-allowed"
                  >
                    <Plus size={11} />
                    Add a bot
                  </button>
                )}
              </span>
            </div>
          )}

          {/* The bots that TRADED here and left. Their record is the account's own — it is what
           *  the live-against-demo score reads — so it stays under the bots on it now, whether
           *  that is none or a new set. ⚠ No controls: the bot is run from its new account's
           *  card, and a Stop here would read as stopping it on THIS account. */}
          {past.map((b) => {
            const where = b.moved_to != null ? regByAccount.get(b.moved_to)?.kind : undefined
            return (
              <div
                key={`past-${b.bot_key}`}
                data-testid="past-row"
                data-bot={b.bot_key}
                className={`grid ${GRID} items-center gap-3 pr-4 py-[10px] border-t border-border-subtle`}
              >
                <span className="flex items-center gap-[9px] font-medium text-[13px] min-w-0 pl-4 text-text-secondary">
                  {/* A spacer the width of a status dot, so the name lines up with the rows
                   *  above — a bot that is not here has no state here to show. */}
                  <span className="inline-block w-[7px] h-[7px] shrink-0" />
                  <span className="truncate">{b.name}</span>
                </span>
                <Contribution e={b} asking={false} />
                <ReturnPct e={b} asking={false} />
                <TradeCount e={b} asking={false} />
                <PerTrade e={b} asking={false} top={false} />
                <span className="col-span-5 text-[12px] text-text-tertiary">
                  {b.moved_to != null
                    ? `Moved to ${where ? `${where} account` : 'account'} ${b.moved_to}`
                    : 'Moved off this account'}
                </span>
              </div>
            )
          })}
        </div>

        {earn && <Unattributed e={earn} />}
      </div>
    )
  }

  /** Accounts with nothing on them: one line each. The NUMBER leads, as it does on a card.
   *  ⚠ The kind chip stays HERE — this list mixes live and demo under one heading, so the chip is
   *  the only place a row says which. ⚠ No "no bots" tag: the heading says it. */
  const renderEmpty = (list: BotAccountRegistration[]) => (
    <div className="bg-bg-surface border border-border-subtle rounded-lg overflow-hidden">
      {list.map((a: BotAccountRegistration, i) => (
        <button
          key={a.account}
          data-testid="empty-account"
          onClick={() => set('account', String(a.account))}
          title="Open this account — put a bot on it from here"
          className={`w-full flex items-center gap-3 px-4 py-[9px] text-left text-text-tertiary hover:bg-bg-surface-2 transition-colors ${
            i > 0 ? 'border-t border-border-subtle' : ''
          }`}
        >
          <span className="text-[13px] font-mono font-semibold tabular-nums text-text-primary">
            {a.account}
          </span>
          <span className="text-[13px] text-text-secondary">
            {a.label || a.broker || `Account ${a.account}`}
          </span>
          <KindChip kind={a.kind} />
        </button>
      ))}
    </div>
  )

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
      <div className="flex items-baseline gap-[14px] flex-wrap pb-[10px]">
        <h1 className="text-[19px] font-semibold">Bots</h1>
        {/* 🔴 THE MONEY CAME OFF THIS LINE (2026-09-06). It carried the fleet balance and the
         *  fleet net, and both are already on the account they belong to a few pixels below —
         *  Aaron: *"I don't know if that information is necessary. Like, I could just look and
         *  see."* ⚠ The rule it is an instance of is this page's oldest one: a number restating
         *  what is already on screen is not a summary, it is a second copy that can disagree.
         *  ⚠ The count STAYS, because *how many are running* is the one thing you cannot read
         *  off the rows without counting them yourself. */}
        {asking && <Shimmer className="h-[13px] w-[96px] self-center" />}
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
          {/* 🔴 **IT OPENS THE DRAWER AND NOTHING ELSE (Aaron, 2026-09-10: "it doesn't show me
           *  what it is going to do before I do it").** The drawer scans — a read — and lists
           *  every change; the Sync button there is the only thing that writes. It is also the
           *  one way to add an account: the by-hand form lives inside the drawer, for a terminal
           *  that is not running. */}
          <button
            data-testid="sync-vps"
            onClick={() => setSyncOpen(true)}
            title="See what's out of sync between your account list and the VPS — nothing changes until you press Sync"
            className="text-[12px] px-[10px] py-[5px] rounded-md border border-border-default text-text-secondary hover:text-text-primary hover:bg-bg-hover transition-colors"
          >
            Sync VPS
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

      {/* ── what you are looking at: which half, and which side ──────────────────
       *  🔴 **TWO TABS, AND THE FIRST LOOK IS ONLY WHAT IS TRADING** (Aaron, 2026-09-10: *"when I
       *  click on this page… I just only wanna focus on the accounts that have bots on them. If an
       *  account has no bots on them, then I don't care"*). The page mixed three kinds of thing
       *  in one scroll — accounts with bots, accounts with none, bots on no account — and read as
       *  scattered. ⚠ **This is NOT the tab mistake this page was rebuilt to remove**: those tabs
       *  were several views of the SAME objects; these two hold DISJOINT sets, so nothing is shown
       *  twice. ⚠ Tab state lives in the URL, like every tab in this app. */}
      <div className="flex items-end justify-between border-b border-border-subtle mb-[18px]">
        <div role="tablist" className="flex items-center">
          {(
            [
              {
                id: 'trading',
                label: 'Trading',
                // ⚠ Once the box's first read is in: an account whose bots LEFT is known only from
                // the trade record it carries, and a count that grows as the box replies reads as
                // an account appearing.
                count: accountGroups && !asking ? shownAccounts.length : null,
                title: 'Accounts with a bot on them, or a record of bots that traded there',
              },
              {
                id: 'unassigned',
                label: 'Unassigned',
                // Only once every source it counts has answered — a count that grows as the box
                // replies would read as things appearing.
                count: registry && snapshot ? shownEmpty.length + shownUnassigned.length : null,
                title: 'Accounts with no bot on them, and bots on no account',
              },
            ] as const
          ).map((t) => (
            <button
              key={t.id}
              role="tab"
              data-testid={`tab-${t.id}`}
              aria-selected={show === t.id}
              onClick={() => set('show', t.id === 'trading' ? null : t.id)}
              title={t.title}
              className={`flex items-center gap-1.5 px-4 py-2 text-[13px] font-medium transition-colors -mb-px border-b-2 ${
                show === t.id
                  ? 'text-text-primary border-accent'
                  : 'text-text-tertiary border-transparent hover:text-text-secondary'
              }`}
            >
              {t.label}
              {t.count != null && (
                <span
                  className={`text-[11px] font-mono tabular-nums px-[5px] py-[1px] rounded-full ${
                    show === t.id ? 'bg-accent/15 text-accent' : 'bg-bg-hover text-text-tertiary'
                  }`}
                >
                  {t.count}
                </span>
              )}
            </button>
          ))}
        </div>
        <div className="pb-[7px]">
          <KindFilter kind={kind} onPick={(k) => set('kind', k)} />
        </div>
      </div>

      {/* A DRAWER, not an inline panel (Aaron, 2026-09-10: "I don't know what I'm looking at").
       *  Inline, it pushed the fleet down and read as part of whichever demo/live filter was on,
       *  when it has nothing to do with either. */}
      <VpsSyncDrawer open={syncOpen} onClose={() => setSyncOpen(false)} />

      {/* "Reading the box…" went (2026-09-10): the values waiting on the box now shimmer where
       *  they will land, which says the same thing without a line of text above the page. */}
      {(accountsPending || registryPending) && !accountGroups && !registry && <BotsPageSkeleton />}
      {error && (
        <p className="text-[12px] text-neg-text">
          Could not reach the trading box: {String(error)}
        </p>
      )}

      {/* 🔴 **NOT GATED ON THE SNAPSHOT (2026-09-06), AND THAT GATE WAS THE WHOLE DEFECT.** The
       *  accounts and their bots are read from the instance configs, which need no VPS at all —
       *  but the entire list sat behind `{snapshot && …}`, so while the trading box was
       *  unreachable this page rendered NO ACCOUNTS WHATSOEVER. Reporting nothing because a
       *  DIFFERENT source is quiet is the page telling you there are no accounts, which is the
       *  most reassuring answer available and the one most likely to be wrong.
       *
       *  ⚠ The failure banner above still says the box could not be reached, and each row's own
       *  dot says its state is unknown rather than stopped. **Three separate statements, none of
       *  which may be collapsed into an empty page.** */}
      {/* 🔴 **NOT GATED ON THE SNAPSHOT** — see the note above: the accounts come from the
       *  instance configs, and an unreachable box must never read as a page with no accounts. */}
      {(accountGroups || registry) && show === 'trading' && (
        <div className="flex flex-col gap-[22px]">
          {SECTIONS.map(({ key, label }) => {
            const accounts = shownAccounts.filter((a) => sideOf(typeOf(a.account, a.rows)) === key)
            if (!accounts.length) return null
            return (
              <SideSection
                key={key}
                side={key}
                label={label}
                aside={
                  key === 'live' || key === 'demo' ? (
                    <SideScoreLine
                      side={key === 'live' ? liveScore : demoScore}
                      leading={lead === key}
                      asking={asking}
                    />
                  ) : undefined
                }
              >
                {accounts.map(renderAccount)}
              </SideSection>
            )
          })}

          {/* An empty Trading tab says where everything went, rather than reading as a page with
           *  nothing on it. A FILTER that emptied it is said by the note below instead. */}
          {accountGroups && !asking && trading.length === 0 && (
            <p
              data-testid="trading-empty"
              className="text-[12.5px] text-text-tertiary py-6 text-center"
            >
              No account has a bot on it.{' '}
              <button
                onClick={() => set('show', 'unassigned')}
                className="text-accent hover:underline"
              >
                See what is unassigned
              </button>
            </p>
          )}

          {/* ⚠ A config that cannot be READ stays on THIS tab. It is a fault, not a resting state,
           *  and nothing says the bot behind it is not running — a fault may not sit behind a tab. */}
          {/* ── bots whose config could not be READ ─────────────────────────── */}
          {/* 🔴 **A SEPARATE SECTION, and merging it with the one above was the defect (fixed
           *  2026-09-06).** A benched bot is a state somebody chose; an unreadable config is a
           *  fault, and the heading above tells the reader to *give it an account* — an
           *  instruction that cannot fix a broken file and sends them to the wrong control.
           *  ⚠ **No Configure button here**, deliberately: that panel reads the same config, so
           *  offering it is offering a door onto the thing that is broken. Logs is what is left,
           *  and it is where the parse error actually is. */}
          {shownBroken.length > 0 && (
            <div>
              <p className="text-[12px] text-neg-text mb-[7px] px-[2px]">
                Configuration could not be read{' '}
                <span className="text-text-tertiary">
                  — not benched, and not fixable from this page: read the log and repair the file
                </span>
              </p>
              <div className="bg-bg-surface border border-neg/30 rounded-lg overflow-hidden">
                {shownBroken.map((bot, i) => (
                  <div
                    key={bot.key}
                    data-testid="bot-row-broken"
                    className={`flex items-center gap-3 pr-4 py-[10px] ${
                      i > 0 ? 'border-t border-border-subtle' : ''
                    }`}
                  >
                    <span className="flex items-center gap-[9px] font-medium text-[13px] pl-4">
                      <span className="inline-block w-[7px] h-[7px] rounded-full shrink-0 bg-neg" />
                      {bot.name}
                    </span>
                    <span className="ml-auto">
                      <IconBtn icon={FileText} title="Logs" onClick={() => setLogBot(bot.key)} />
                    </span>
                  </div>
                ))}
              </div>
            </div>
          )}

          {filterNote}

          {/* 🔴 Only once the box has ANSWERED (2026-09-10). The bot list comes from the
           *  snapshot, so for the ~4s it takes — and for as long as the box is unreachable — it
           *  is empty, and this line printed "No bots registered" over a fleet of three. */}
          {snapshot && bots.length === 0 && (
            <p className="text-[12px] text-text-tertiary py-8 text-center">No bots registered.</p>
          )}
        </div>
      )}

      {/* ── the Unassigned tab: accounts with no bot, and bots on no account ─────────
       *  ⚠ Grouped by WHAT each thing is, not by live or demo — every account here says its kind
       *  on its own chip, live first, and nothing on this tab trades. */}
      {(accountGroups || registry) && show === 'unassigned' && (
        <div className="flex flex-col gap-[22px]">
          {shownEmpty.length > 0 && (
            <SideSection
              side="no-bots"
              label="Accounts with no bots"
              hint="— open one to put a bot on it"
            >
              {renderEmpty(
                [...shownEmpty].sort(
                  (a, b) => (a.kind === 'live' ? 0 : 1) - (b.kind === 'live' ? 0 : 1)
                )
              )}
            </SideSection>
          )}

          {shownUnassigned.length > 0 && (
            <SideSection
              side="no-account"
              label="Bots on no account"
              hint="— trade nothing until you give them one"
            >
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
            </SideSection>
          )}

          {registry &&
            snapshot &&
            shownEmpty.length === 0 &&
            shownUnassigned.length === 0 &&
            !kind && (
              <p className="text-[12.5px] text-text-tertiary py-6 text-center">
                Nothing is unassigned — every account has a bot and every bot has an account.
              </p>
            )}

          {filterNote}
        </div>
      )}

      {selBot && (
        <BotDrawer
          bot={selBot}
          earnings={earnOf(accountOfBot(selBot.key) ?? selBot.account, selBot.key)}
          job={jobByKey.get(selBot.key)}
          busy={busy}
          pendingAction={pending?.key === selBot.key ? pending.action : null}
          // The CONFIG's account, or `undefined` until the configs are read — never "on no
          // account" for a list that has not arrived, or the panel would hide Remove on a bot
          // that is on one.
          configAccount={accountGroups === undefined ? undefined : accountOfBot(selBot.key)}
          onClose={() => set('bot', null)}
          onLogs={() => setLogBot(selBot.key)}
          onStart={() => act(selBot.key, 'start', () => startOne.mutate(selBot.key))}
          onStop={() => act(selBot.key, 'stop', () => stopOne.mutate(selBot.key))}
          onRestart={() => act(selBot.key, 'restart', () => restartOne.mutate(selBot.key))}
          onOpenAccount={(a) => set('account', String(a))}
        />
      )}

      {/* 🔴 **A REGISTERED ACCOUNT WITH NO BOTS OPENS TOO (2026-09-06).** The drawer used to
       *  render only for an account in the GROUPING — which is derived from the instance configs
       *  and therefore holds only accounts a bot is already on — so the one account that most
       *  needs the Add bot control could not open at all. That is the registry's whole purpose,
       *  re-broken. ⚠ The synthesized group states `share_total_pct: 0`, never `null`: nothing has
       *  been handed out, which is different from a share that could not be read. */}
      {selAccount &&
        (groupByAccount.get(Number(selAccount)) || regByAccount.get(Number(selAccount))) && (
          <AccountDrawer
            group={
              groupByAccount.get(Number(selAccount)) ??
              emptyGroup(regByAccount.get(Number(selAccount)) as BotAccountRegistration)
            }
            reg={regByAccount.get(Number(selAccount))}
            registry={registry ?? []}
            earnings={selEarn}
            balance={selBalance}
            balanceReadAt={selReadAt}
            startAdding={params.get('add') === '1'}
            asking={asking}
            statusByKey={statusByKey}
            onClose={() => set('account', null)}
            // A bot's name on the account panel opens that bot's panel (and closes this one).
            onOpenBot={(k) => set('bot', k)}
            onStart={(k) => act(k, 'start', () => startOne.mutate(k))}
            onStop={(k) => act(k, 'stop', () => stopOne.mutate(k))}
            pendingKey={pending?.key ?? null}
            pendingAction={pending?.action ?? null}
            busy={busy}
          />
        )}

      {logBot && (
        <LogModal
          botName={logBot}
          botLabel={(() => {
            // Name plus LIVE or demo — two copies of one strategy share a name, and a log
            // window floats over the page with nothing else saying whose log it is.
            const b = botByKey.get(logBot)
            return b ? labelOf(b) : logBot
          })()}
          onClose={() => setLogBot(null)}
        />
      )}
    </div>
  )
}
