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
 * ⚠ **State is one dot and one word (2026-09-12)** — the worst problem or what the bot is doing,
 * anything else counted beside it and spelled out on hover (`lib/botCondition.ts`). It was a bare
 * dot, and then a dot with up to five tags beside the name.
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
 * 🔴 **On Trading, live and demo are two sections** (*"I want live and demo split"*) — but there is
 * no SIDE-level "ahead" any more. A live-vs-demo pooled score was built and read three separate
 * times (a pair of tiles, then a section-heading figure, then a bar-heading figure) and Aaron
 * rejected all three, the third time in as many rounds: *"it does nothing for me... it looks kind
 * of out of place."* Removed outright rather than reskinned a fourth time — see
 * `notes/bots-page.md`'s three-strikes entry before ever re-adding one. The one winner this page
 * still names is per BOT, not per side: `PerTrade`'s own trophy, judged in R per trade — see that
 * component for why dollars, share of the account and total R would all crown the wrong one.
 *
 * 🔴 **Nothing on the page says a fact twice (2026-09-10, *"we don't need to be redundant on data
 * anywhere on this page"*).** A section heading names the kind, so no card repeats it; the net figure
 * carries the account's sign, so no edge colour repeats it.
 */
import { useState, useEffect, useRef } from 'react'
import { useIsFetching, useQueryClient } from '@tanstack/react-query'
import { useSearchParams } from 'react-router-dom'
import {
  FileText,
  Play,
  RotateCcw,
  RefreshCw,
  Copy,
  Check,
  MousePointerClick,
  SlidersHorizontal,
  Star,
  Trophy,
  Plus,
  GripVertical,
  Loader2,
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
  useSetAccountPin,
  useSaveAccountPriority,
} from '@/hooks/useBots'
import { VersionPill } from '@/components/VersionPill'
import { OverflowMenu } from '@/components/OverflowMenu'
import { Shimmer } from '@/components/Shimmer'
import { EmptyState } from '@/components/EmptyState'
import { openingRecorder } from '@/lib/accountEarnings'
import { botLabel as labelOf } from '@/lib/botLabel'
import type {
  BotStatus,
  BotAccountBot,
  BotAccountGroup,
  BotAccountRegistration,
  BotEarnings,
  AccountEarnings,
} from '@/types'
import { ACTION_DOING, BotActionPill, type BotAction } from './BotStatusPill'
import { UsersTab } from './UsersTab'
import { BotDrawer } from './BotDrawer'
import { AccountDrawer } from './AccountDrawer'
import { accountName, emptyGroup, nameOf } from './AccountForm'
import { VpsSyncDrawer } from './VpsSyncDrawer'
import { useStopFirst } from './stopFirst'
import { KIND_NAME, KIND_TINT, KindChip, tintOf } from './kind'
import { botCondition, worstCondition } from '@/lib/botCondition'
import { restartReason, versionNeed, type VersionNeed } from '@/lib/botVersion'
import { StatusText, TONE_DOT } from '@/components/BotStatus'

function relativeTime(iso: string): string {
  const diff = Date.now() - new Date(iso).getTime()
  const mins = Math.floor(diff / 60_000)
  if (mins < 1) return 'just now'
  if (mins < 60) return `${mins}m ago`
  const hrs = Math.floor(mins / 60)
  if (hrs < 24) return `${hrs}h ago`
  return `${Math.floor(hrs / 24)}d ago`
}

/** A benched bot's PROBLEMS only. "Benched" is what the list it sits in already says, so the row
 *  names nothing when nothing is wrong — and a crash or a refused start, which can only be read
 *  once a bot has stopped, still reaches it. */
function BenchedIssues({ bot }: { bot: BotStatus }) {
  const cond = botCondition(bot, { asked: true, onAccount: false })
  return cond.issues.length ? <StatusText cond={cond} /> : null
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
  testId,
}: {
  icon: typeof Play
  title: string
  onClick: () => void
  tone?: 'pos' | 'neg'
  disabled?: boolean
  testId?: string
}) {
  const hover =
    tone === 'neg'
      ? 'hover:text-neg-text hover:border-neg/40'
      : tone === 'pos'
        ? 'hover:text-pos-text hover:border-pos/40'
        : 'hover:text-text-primary hover:border-border-default'
  return (
    <button
      data-testid={testId}
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

/** The pin — one account per demo/live kind can hold it. A ★, gold only while held (root
 *  CLAUDE.md's colour rule: gold is for ★ markers and limits), so an unpinned account reads as a
 *  plain, unremarkable control rather than a second alarm shape beside the worst-status marker. */
function PinToggle({
  pinned,
  onClick,
  disabled,
}: {
  pinned: boolean
  onClick: () => void
  disabled?: boolean
}) {
  return (
    <button
      data-testid="pin-account"
      aria-pressed={pinned}
      disabled={disabled}
      onClick={(e) => {
        // A sibling of the row's own toggle button, not nested inside it — see the row markup.
        // `stopPropagation` still guards it against a future wrapper click handler.
        e.stopPropagation()
        onClick()
      }}
      title={
        pinned
          ? 'Pinned — open by default and first in its Live/Demo section. Click to unpin.'
          : 'Pin this account — open by default and first in its Live/Demo section.'
      }
      className={`w-[26px] h-[26px] shrink-0 grid place-items-center rounded-md border transition-colors disabled:opacity-40 disabled:cursor-not-allowed ${
        pinned
          ? 'border-gold/40 bg-gold-muted text-gold-text'
          : 'border-transparent text-text-tertiary hover:text-gold-text hover:border-gold/30 hover:bg-bg-surface-2'
      }`}
    >
      <Star size={12} className={pinned ? 'fill-current' : ''} />
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
 *  the R, so each cell held two different measurements.
 *
 *  🔴 **Bot | Status | P&L | Return % | Trades | Per trade | Risk | Version | Actions (2026-09-12).**
 *  Up to five tags beside the name became ONE status column, and the uptime column went into that
 *  status's hover.
 *
 *  🔴 **The spare width is SHARED, never parked in one blank track (2026-09-13).** Aaron: *"the
 *  columns 3-8 are all crowded, give them some space."* The slack went to a spacer before Actions,
 *  so P&L to Version sat packed at their floors beside a gap as wide as three of them. Every track
 *  now has a floor and a share (`minmax(floor, Nfr)`): a wide screen spaces the numbers out, a
 *  1280px one keeps the floors. ⚠ The status's share is only a little more than a number's — as the
 *  ONE flexible track it once took ~400px at 1600 wide and pushed every number to the far side.
 *
 *  ⚠ Version's floor is its widest state at the pill's 11px, and the rest their widest real value,
 *  so the row still fits a 1280px screen.
 *
 *  🔴 **The floors are FIXED lengths — never `auto` — and the actions track is fixed outright.**
 *  Each row is its own grid, and an `auto` track sizes to ITS row: the word "Actions" in the heading
 *  row, ~185px of buttons in a bot row. On a 1280px screen the bot row ran out of room, squeezed its
 *  name column, and every value sat ~50px left of its heading while the heading row did not move. A
 *  `minmax(fixed, fr)` track ignores what is in it, so every row still gets the same columns. */
//  🔴 **FIVE tracks since 2026-09-15, not nine** — Bot, Status, Performance, Version, Actions.
//  P&L, Trades and Per trade became ONE Performance cell; Return % and Risk left the row (the
//  bot panel states both, and the account band states the risk budget). See `Performance`.
const GRID =
  'grid-cols-[minmax(140px,1.3fr)_minmax(140px,1.2fr)_minmax(230px,2fr)_minmax(128px,1fr)_150px]'

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
 *
 * ⚠ **Uncoloured since 2026-09-12, like Return %.** P&L carries the sign's colour; three cells a
 * row repeating it made every healthy row a strip of green.
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
      className="flex items-center gap-[5px] text-[13px] font-mono tabular-nums text-text-secondary cursor-default"
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

/**
 * What a bot has done, on ONE line: its own closed-trade money, how many trades that rests on, and
 * R per trade — "+$1,305.58 · 1 trade · +2.10R" (2026-09-15, the fleet-table rebuild Aaron picked
 * off a mockup after *"does it feel too busy?"*).
 *
 * 🔴 **One LINE, never stacked.** Aaron, 2026-09-10: *"I don't want anything stacked on top of each
 * other in columns like that."* That is why these were three columns; they are one cell now because
 * three columns each printing nothing for a bot that has not traded was most of the ink on the
 * page. Inline with a `·` between them keeps each figure on its own, on one baseline.
 *
 * ⚠ **The trade count still sits BESIDE the R** — on one or two trades a lead is not a verdict, and
 * the count next to the score is the only thing on the row saying so (root CLAUDE.md → Trading
 * Philosophy). The trophy stays on the R, via `PerTrade`.
 *
 * ⚠ **Three states, three looks** (rule 1): no record → `Contribution`'s own words; a record holding
 * no closed trade → "no trades yet", a MEASURED zero said once in words; traded → the line.
 *
 * ⚠ **Return % left the row.** It is the one figure this rebuild drops from the page's face — the
 * bot panel still states it, and the account band carries the account's own return.
 */
function Performance({
  e,
  asking,
  top,
}: {
  e: BotEarnings | undefined
  asking: boolean
  top: boolean
}) {
  const body = (() => {
    if (!e && asking) return <Shimmer className="h-[13px] w-[170px]" />
    if (!e || !e.traded) return <Contribution e={e} asking={asking} />
    const n = e.closed_trades ?? 0
    const recorded = `recorded ${e.records_from} → ${e.records_to}`
    if (n === 0)
      return (
        <span
          data-testid="trades"
          data-count="0"
          title={`Its record was read and holds no closed trade · ${recorded}`}
          className="text-[12px] text-text-tertiary cursor-default"
        >
          no trades yet
        </span>
      )
    return (
      <>
        <Contribution e={e} asking={asking} />
        <span className="text-[11.5px] text-text-tertiary">·</span>
        <span
          title={`${e.wins ?? 0} won, ${e.losses ?? 0} lost · ${recorded}`}
          className="text-[12px] font-mono tabular-nums text-text-tertiary cursor-default"
        >
          <span data-testid="trades" data-count={n}>
            {n}
          </span>{' '}
          {n === 1 ? 'trade' : 'trades'}
        </span>
        <span className="text-[11.5px] text-text-tertiary">·</span>
        <PerTrade e={e} asking={asking} top={top} />
      </>
    )
  })()
  return (
    <span
      data-testid="performance"
      // Centred, not baseline — the trophy icon inside `PerTrade` has no text baseline, so on a
      // baseline row it lifted the top bot's R ~2px above the figures beside it.
      className="flex items-center gap-[6px] min-w-0 whitespace-nowrap"
    >
      {body}
    </span>
  )
}

/**
 * The account's risk cap, and whether there is room under it — "Cap 10% · full", "Cap 10% · 5%
 * free", "Cap 10% · 15% shared" — on the account band (2026-09-15).
 *
 * 🔴 **Shares that add up past the cap are a NORMAL state since 2026-09-15** (the bots share the
 * room — the server's `share_note`), so they read grey as "shared", never red. Red is kept for the
 * one thing still refused: a bot whose own share is above the whole cap (`share_overflow_reason`).
 *
 * 🔴 **It was "10% of 10% risk" with a filled bar for one pass, and Aaron did not like it** (*"only
 * thing I don't like is the 10 of 10 risks display"*). It read like a typo, and the bar was FULL
 * on every account — two bots at 5% under a 10% cap is the setup he chose (root CLAUDE.md → risk is
 * budgeted per account), so the loudest mark in the band was drawn over the normal state. What the
 * reader wants from this spot is two things: the ceiling, and whether another bot fits. So: the cap
 * as a number, and the room as a WORD — quiet when full or free, red only when over.
 *
 * 🔴 **Every figure comes off the server; the page adds and subtracts nothing** (`notes/bots-page.md`
 * → *The page may NOT add the risk shares up itself*). The room is the server's `room_pct`, whether
 * it FITS is its `share_overflow_reason`, and an unreadable share (`share_total_pct` of `null`) says
 * so rather than reading as zero. A payload without `room_pct` (cached before the field existed)
 * shows the cap alone — never a room worked out here.
 *
 * ⚠ **Nothing is drawn with no bot on the account, a cap disagreement, or no cap** — each already
 * has its own chip beside the account's name.
 */
function RiskBudget({
  group,
  cap,
  idle,
}: {
  group: BotAccountGroup
  cap: number | null
  idle: boolean
}) {
  if (idle || cap == null) return null
  const used = group.share_total_pct
  const room = group.room_pct
  const over = group.share_overflow_reason
  const pct = (x: number) => `${Number(x.toFixed(2))}%`
  const handedOut =
    typeof used === 'number'
      ? `${pct(used)} of the ${pct(cap)} cap is handed out to this account's bots`
      : ''
  const [state, tail, tone, title] =
    typeof used !== 'number'
      ? [
          'unreadable',
          'shares unreadable',
          'text-text-tertiary',
          "At least one bot's risk share could not be read, so nothing can say how much of the cap is in use.",
        ]
      : over
        ? ['over', 'a bot is over it', 'text-neg-text', over]
        : typeof room === 'number'
          ? room < 0
            ? [
                'shared',
                `${pct(used)} shared`,
                'text-text-tertiary',
                group.share_note ?? `${handedOut}.`,
              ]
            : room === 0
              ? [
                  'full',
                  'full',
                  'text-text-tertiary',
                  `${handedOut} — the whole cap. Another bot can still join; the bots then share the room.`,
                ]
              : ['free', `${pct(room)} free`, 'text-text-tertiary', `${handedOut}.`]
          : ['set', null, '', `${handedOut}.`]
  return (
    <span
      data-testid="risk-budget"
      data-state={state}
      title={title}
      className="flex items-baseline gap-[6px] text-[11.5px] cursor-default"
    >
      <span className="text-text-tertiary">Cap</span>
      <span className="font-mono tabular-nums font-semibold text-gold-text">{pct(cap)}</span>
      {tail && (
        <>
          <span className="text-text-tertiary">·</span>
          <span className={tone}>{tail}</span>
        </>
      )}
    </span>
  )
}

/**
 * The ONE action a bot row shows on its face — Start or Stop, whichever its state allows, in WORDS
 * (2026-09-15). Four near-identical icons a row was the busiest thing on the page, on a row where
 * one of them stops real money. Restart and Logs moved behind the row's "···" (`OverflowMenu`);
 * Configure stays on the row as its icon — see that button's own note.
 *
 * 🔴 **Stop is red at rest** (Aaron, 2026-09-16: *"just leave them all red by default"*). It was
 * neutral until hover so a healthy fleet would not read as six alarms; he preferred the control
 * that stops real money to always look like it. Start stays neutral until hover.
 */
function PrimaryBtn({
  label,
  tone,
  disabled,
  onClick,
}: {
  label: 'Start' | 'Stop'
  tone: 'pos' | 'neg'
  disabled?: boolean
  onClick: () => void
}) {
  return (
    <button
      type="button"
      title={label}
      disabled={disabled}
      onClick={(e) => {
        e.stopPropagation()
        onClick()
      }}
      className={`h-[26px] min-w-[52px] px-[10px] rounded-md border text-[11.5px] font-semibold transition-colors disabled:opacity-30 disabled:cursor-not-allowed ${
        tone === 'neg'
          ? 'text-neg-text border-neg/40 bg-neg-muted hover:border-neg/70'
          : 'border-border-default text-text-secondary hover:text-pos-text hover:border-pos/40 hover:bg-pos-muted'
      }`}
    >
      {label}
    </button>
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

/**
 * A labelled group — one side's accounts, or one kind of unassigned thing — so nothing interleaves.
 *
 * ⚠ **No `aside` slot any more (2026-09-15, third pass)** — it existed for exactly one caller
 * (the rail's Live/Demo heading, to fold in a pooled side score), and that caller now uses the
 * dedicated `RailGroupBar` instead (a full-width filled bar, not this component's small
 * dot-plus-label) — which itself dropped the score a few hours later (see `RailGroupBar`'s own
 * doc comment: three strikes on the same idea, removed rather than reskinned a fourth time).
 * `pending`/`other` — the only remaining callers, on the rail and on the Unassigned tab — never
 * had a score to show beside their label, so carrying the prop forward unused would be exactly
 * the speculative slot this repo's own mandate rules out.
 */
function SideSection({
  side,
  label,
  hint,
  children,
}: {
  side: string
  label: React.ReactNode
  hint?: React.ReactNode
  children: React.ReactNode
}) {
  const t = tintOf(side)
  return (
    <section data-testid={`section-${side}`} className="flex flex-col gap-[10px]">
      <div className="flex items-center gap-[9px] flex-wrap px-[2px]">
        {KIND_TINT[side] && <span className={`w-[8px] h-[8px] rounded-full ${t.dot}`} />}
        <span className={`text-[11.5px] font-semibold uppercase tracking-[0.7px] ${t.text}`}>
          {label}
        </span>
        {hint && <span className="text-[11.5px] text-text-tertiary">{hint}</span>}
        <span className="h-px flex-1 bg-border-subtle" />
      </div>
      {children}
    </section>
  )
}

/**
 * The Live / Demo group heading inside the rail — a QUIET sticky header: a coloured dot, the
 * group's name, and how many accounts are under it. Live is GOLD, demo the page's accent cyan,
 * and the colour is carried by the dot and the label only.
 *
 * 🔴 **It was a full-bleed filled colour band until 2026-09-15 (fourth pass) and that is what
 * made the whole column read as decoration** — a saturated band plus a saturated open row meant
 * roughly every pixel of a 250px column was a fill, so nothing in it could be emphasis any more.
 * A heading for a one- or two-row group is the least important thing in the rail and may not be
 * the loudest. Aaron, on the running page: *"the account list design looks ugly."* Colour in this
 * column now means exactly two things — the sign of a figure, and which account is open.
 *
 * 🔴 **A DELIBERATE, SCOPED exception to `KIND_TINT`** (`kind.tsx`), not a change to it — every
 * filter pill, chip and badge on this page still reads amber for live exactly as before.
 *
 * 🔴 **No pooled score in here — three shapes were tried and all three were read as noise.** See
 * `notes/bots-page.md`. This is the group's name and its count, nothing compared.
 *
 * ⚠ **Sticky** — the rail scrolls once a few accounts are on the box, and a group's name must
 * stay on screen while its own rows are under the pointer.
 */
function RailGroupBar({
  kind,
  label,
  count,
}: {
  kind: 'live' | 'demo'
  label: React.ReactNode
  count: number
}) {
  const text = kind === 'live' ? 'text-gold-text' : 'text-accent-text'
  const dot = kind === 'live' ? 'bg-gold' : 'bg-accent'
  return (
    <div
      data-testid={`rail-bar-${kind}`}
      /* ⚠ SUNKEN, not the raised surface an OPEN row uses — one surface may not mean two things
       *  in the same column, or "which account is showing on the right" stops being readable at a
       *  glance. A heading recedes; an open row rises. */
      className="sticky top-0 z-[1] flex items-center gap-[7px] px-[10px] py-[6px] bg-bg-sunken border-b border-border-subtle"
    >
      <span className={`w-[6px] h-[6px] rounded-full shrink-0 ${dot}`} />
      <span className={`text-[10px] font-bold uppercase tracking-[0.9px] ${text}`}>{label}</span>
      {/* How many accounts are under this heading — the one figure a group legitimately owns,
       *  since it counts rows rather than pooling anything the rows themselves state. */}
      <span className="ml-auto text-[10px] font-mono tabular-nums text-text-tertiary">{count}</span>
    </div>
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
function AccountNet({
  e,
  asking,
  compact,
}: {
  e: AccountEarnings | undefined
  asking: boolean
  /** The rail row's line 2 (2026-09-15) — the % only, no dollar amount beside it, and SMALLER
   *  than the full stat-cluster figure (11px vs 13px). The detail panel's own stat cluster is the
   *  full reading; a second figure crammed into a ~260px rail row would be the very duplication
   *  this page keeps getting rebuilt to remove, and the full sentence — % and $ together — is
   *  still one hover away via the same `title`. ⚠ **Deliberately quieter than line 1** (Aaron,
   *  on the mockup: the number/name must read as the dominant element, not the return figure
   *  beside it) — this is the one span on the row still allowed real colour (sign is a finding),
   *  so it stays smaller than line 1 rather than also competing on size. */
  compact?: boolean
}) {
  // ⚠ `net unknown` is a FINDING and may only appear once the box has answered — while it is
  // still being asked, the same words would report a fault that has not happened.
  // Ghost content in the pill's own layout, so it lands on the same baseline as the real one.
  if (!e && asking)
    return (
      <Shimmer>
        <span className="inline-flex items-baseline gap-[6px]">
          <span className="text-[13px] font-mono tabular-nums font-semibold">+00.0%</span>
          {!compact && <span className="text-[11px] font-mono tabular-nums">+$0,000.00</span>}
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
  // ⚠ Text, not a filled pill (2026-09-12): a green block on every account heading was a large
  // part of what read as "everything is green". The sign's colour stays on the figures.
  return (
    <span
      data-testid="account-net"
      title={`${from} ${then}`}
      className="inline-flex items-baseline gap-[6px] cursor-default"
    >
      <span
        className={`font-mono tabular-nums font-semibold ${compact ? 'text-[11px]' : 'text-[13px]'} ${up ? 'text-pos-text' : 'text-neg-text'}`}
      >
        {e.net_pct > 0 ? '+' : ''}
        {e.net_pct.toFixed(1)}%
      </span>
      {!compact && (
        <span
          className={`text-[11px] font-mono tabular-nums ${up ? 'text-pos-text/70' : 'text-neg-text/70'}`}
        >
          {money(e.net_usd)}
        </span>
      )}
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
      data-testid="column-headings"
      className={`grid ${GRID} items-center gap-3 pr-3 py-[7px] rounded-t-lg border-b border-border-default bg-bg-sunken text-[9.5px] font-semibold uppercase tracking-[0.7px] text-text-tertiary`}
    >
      <span className="pl-4">Bot</span>
      <span title="What the bot is doing, or the worst thing wrong with it — hover a row for everything">
        Status
      </span>
      <span title="What this bot's own closed trades came to, how many trades that rests on, and R per trade — what each trade made in units of the risk it took. The top bot is picked on R per trade, never on dollars.">
        Performance
      </span>
      <span>Version</span>
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
      className="bg-bg-surface border border-border-subtle rounded-lg"
    >
      {/* The headings are fixed words, so they are REAL, not shimmered — a placeholder stands in
       *  for what is not known yet, never for what already is. */}
      <ColumnHeadings />
      <div className="flex items-center gap-3 pl-4 pr-3 py-[10px] bg-bg-sunken/60 border-b border-border-subtle">
        <Shimmer className="h-[14px] w-[92px]" />
        <Shimmer className="h-[13px] w-[64px]" />
        <span className="ml-auto flex items-center gap-[18px]">
          <AccountNet e={undefined} asking />
          <span className="min-w-[112px] text-right text-[16px] font-mono tabular-nums font-semibold">
            <Shimmer>$00,000.00</Shimmer>
          </span>
        </span>
      </div>
      {[0, 1].map((i) => (
        <div
          key={i}
          className={`grid ${GRID} items-center gap-3 pr-3 py-[10px] ${
            i > 0 ? 'border-t border-border-subtle' : ''
          }`}
        >
          <span className="flex items-center pl-4">
            <Shimmer className="h-[13px] w-[96px]" />
          </span>
          <Shimmer className="h-[12px] w-[90px]" />
          <Performance e={undefined} asking top={false} />
          <VersionPill version={undefined} loading />
          <span className="flex gap-[4px] justify-end">
            <Shimmer className="h-[26px] w-[52px]" />
            <Shimmer className="h-[26px] w-[26px]" />
            <Shimmer className="h-[26px] w-[26px]" />
          </span>
        </div>
      ))}
    </div>
  )
}

/** An account group's identity for expand/collapse and for the pin's reordering — the same value
 *  the card is already keyed by (its account number), stringified so a Set can hold it.
 *  ⚠ `bench`/`unknown` groups carry no account number and fall back to their `kind` — they never
 *  render as a card on this page today, but a shared identity function has to survive being
 *  handed one without crashing, since nothing stops a future caller doing exactly that. */
function accountKey(group: BotAccountGroup): string {
  return group.account != null ? String(group.account) : group.kind
}

/** The pinned account first, the rest in their existing order — never across sections, since a
 *  pin only ever wins within its own Live/Demo side (root CLAUDE.md: one pin per kind). At most
 *  one entry is ever pinned (the backend enforces it), but this reads fine even if more than one
 *  claims it. */
function withPinnedFirst<T extends { group: BotAccountGroup }>(accounts: T[]): T[] {
  const pinned = accounts.filter((a) => a.group.pinned)
  if (!pinned.length) return accounts
  return [...pinned, ...accounts.filter((a) => !a.group.pinned)]
}

export function Bots() {
  const { data: snapshot, isLoading, error, dataUpdatedAt } = useBotSnapshot()
  const qc = useQueryClient()
  // 🔴 **THE REFRESH BUTTON RE-READS EVERYTHING THE PAGE SHOWS, NOT JUST THE SNAPSHOT
  // (2026-09-24).** It called the snapshot's own `refetch`, so it re-read status and P&L and left
  // every VERSION badge on whatever it last read. The version is a separate per-bot query with no
  // poll of its own, so after a deploy the page did not start — the CLI, the trading-box tool, the
  // other clone — the badges went on saying "behind" through any number of clicks, and only a full
  // reload cleared them. Aaron: *"I click that refresh icon… and it still said they were not up to
  // latest versions."* A button labelled Refresh that refreshes part of the screen is a label
  // with no code behind it (rule 7).
  //
  // ⚠ **The whole `['bots']` prefix, deliberately** — snapshot, versions, deploy jobs, params,
  // accounts. Listing keys here would be a second statement of what the page reads, stale the day
  // someone adds a query. The version reads are one SSH round trip per bot (measured 4.5s), which
  // is why nothing polls them — and a person clicking a button is exactly when that cost is
  // wanted.
  const refreshAll = () => qc.invalidateQueries({ queryKey: ['bots'] })
  const refreshing = useIsFetching({ queryKey: ['bots'] }) > 0
  const { data: accountGroups, isPending: accountsPending } = useBotAccounts()
  const { data: registry, isPending: registryPending } = useRegisteredAccounts()
  // 🔴 THE TRADING BOX HAS NOT ANSWERED YET — its FIRST read is in flight. This is the only thing
  // the snapshot shimmers decide on, and it is deliberately NOT `!snapshot`: a snapshot that
  // FAILED is also absent, and shimmering over a dead link would make a page that looks busy for
  // ever while the box is down. Once the read fails, the words (`unknown`) and the error line take
  // over, and the equity is a dash; once it answers, the numbers do. A 60s background refetch
  // keeps the numbers on screen and never shimmers.
  const asking = isLoading
  const { data: users } = useUsers()
  const [params, setParams] = useSearchParams()

  const [logBot, setLogBot] = useState<string | null>(null)
  const [syncOpen, setSyncOpen] = useState(false)
  // Which bots are mid start/stop/restart, and WHICH of the three — the pill names the action.
  // 🔴 **PER BOT, NOT ONE FOR THE PAGE (2026-09-24).** This was a single slot, and one flag off it
  // greyed out every bot's buttons on every account until that one action finished — so two bots
  // could only be restarted one after the other, with a wait for each. Nothing needed that: the
  // server refuses nothing, and two bots on ONE account already take turns at the broker login on
  // the box (`algos/shared/mt5_lock.py`). Now only the bot being acted on is locked.
  const [pending, setPending] = useState<ReadonlyMap<string, BotAction>>(() => new Map())

  /**
   * Which accounts show their bot table — the OPEN set, matching this app's `openLegs` idiom
   * (`StackDetail.tsx`): tracked as what is SHOWN rather than what is hidden, because as the
   * account count grows, opening everything by default is exactly the wall this feature exists
   * to remove (the same reasoning `openLegs` gives for a stack's settings). Defaulted below, and
   * kept live until the reader touches a toggle; never written to storage — a fresh page load is
   * the only reset this state ever gets.
   */
  const [expandedAccounts, setExpandedAccounts] = useState<Set<string>>(new Set())
  // Flips the moment a reader opens or closes anything by hand — see the effect below. Once true,
  // nothing may overwrite `expandedAccounts` again for the rest of this page load.
  const userTouchedExpand = useRef(false)
  const toggleAccount = (key: string) => {
    userTouchedExpand.current = true
    setExpandedAccounts((prev) => {
      const next = new Set(prev)
      if (!next.delete(key)) next.add(key)
      return next
    })
  }
  const setPin = useSetAccountPin()

  /**
   * 🔴 **THE BOT ROWS THEMSELVES ARE THE PRIORITY ORDER, AND YOU DRAG THEM HERE (2026-09-16).**
   * Aaron: *"after I click an account… it shows the account on the right with the bots listed, I
   * should be able to drag those bots either up or down under the account, and the highest bot on
   * the account is the highest prioritized bot."* The same order was already draggable one click
   * away in the account panel, and it stays there (its arrows are the only keyboard route) — but
   * these rows were ALREADY being rendered in the saved order and gave no way to change it, which
   * is a list that looks like a ranking and does not act like one.
   *
   * ⚠ **One account is dragged at a time**, so one draft is enough — several detail panels may be
   * open, and the draft names the account it belongs to.
   *
   * ⚠ **The draft is bound to the SERVED order it was made against (`from`)**, the same guard the
   * account panel's list uses: this page refetches in the background, so a draft made against an
   * order that has since moved is DROPPED rather than saved over a change nobody saw.
   */
  const savePriority = useSaveAccountPriority()
  const [orderEdit, setOrderEdit] = useState<{
    account: number
    keys: string[]
    from: string
  } | null>(null)
  const [dragKey, setDragKey] = useState<string | null>(null)
  const [overKey, setOverKey] = useState<string | null>(null)
  const moveBot = (account: number, order: string[], from: string, key: string, to: number) => {
    const at = order.indexOf(key)
    if (at < 0 || to < 0 || to >= order.length || at === to) return
    const keys = [...order]
    keys.splice(at, 1)
    keys.splice(to, 0, key)
    setOrderEdit({ account, keys, from })
  }

  const startOne = useBotStartOne()
  const stopOne = useBotStopOne()
  const restartOne = useBotRestartOne()
  // A move or a removal that has to STOP the bot first, and waits on the box to say it has.
  const { stopThen, waitingFor, waitingAction } = useStopFirst()
  /** Whether THIS bot's controls are locked: its own start/stop/restart is in flight, a deploy of
   *  it is running, or a move or removal is waiting on the box. ⚠ The last stays page-wide on
   *  purpose — `useStopFirst` holds ONE waiting bot, so a second move started meanwhile would
   *  overwrite the first's wait.
   *
   *  🔴 **A RUNNING DEPLOY LOCKS ITS BOT (2026-09-24, Aaron: *"if I'm updating a bot I shouldn't be
   *  able to stop and restart it"*).** This read the start/stop/restart map and nothing else, so
   *  Stop and Restart stayed pressable mid-deploy, racing the deploy's own stop/start on a live
   *  process. The server refuses it too now (`services/bot_ops.py`); this is the page not offering
   *  what the server would refuse. ⚠ `jobByKey` is declared below — read at call time, in render. */
  const deployingNow = (key: string) => jobByKey.get(key)?.status === 'running'
  const busyFor = (key: string) => pending.has(key) || waitingFor !== null || deployingNow(key)
  /** What a bot is in the middle of: a start / stop / restart, the part of a move or a removal it
   *  is on — Stopping while the box catches up, Starting when a move starts it again — or a deploy. */
  const actionOf = (key: string): BotAction | null =>
    pending.get(key) ??
    (waitingFor === key ? waitingAction : null) ??
    (deployingNow(key) ? 'deploy' : null)
  /** Why a change reaching these bots must wait, or `null` — one of them is mid-action. For an
   *  ACCOUNT's settings (its cap, shares, priority and registration are read by every bot on it)
   *  and for the fleet-wide controls. The server refuses the same writes (`services/bot_ops.py`). */
  const lockOf = (keys: readonly string[]): string | null => {
    const k = keys.find((x) => actionOf(x) !== null)
    if (k === undefined) return null
    const b = botByKey.get(k)
    return `${b ? labelOf(b) : k} is ${ACTION_DOING[actionOf(k) as BotAction]} — wait until it finishes.`
  }

  const bots: BotStatus[] = snapshot?.bots ?? []
  // 🔴 The version reads are keyed off the CONFIG list as well as the snapshot (2026-09-10). A
  // version needs only the bot's key, and the config list answers in milliseconds — keyed off the
  // snapshot alone, the ~4.5s version reads could not START until the ~4s snapshot had finished,
  // so the column waited for both back to back, and until then every pill said "No version"
  // (a finding) instead of loading. Now they run side by side with the snapshot.
  //
  // 🔴 **…but they START once the snapshot has answered (2026-09-24).** Side by side stopped paying
  // once the fleet reached ten bots: the box has TWO CPUs, and ten version reads (each starts
  // Python there) buried the status read — MEASURED 3.1s alone, 26.7s beside them, so the whole
  // page shimmered for half a minute. Status and P&L are what the page is for; versions fill in
  // after. The KEYS still come off the config list, so a version never waits for its bot to show
  // up in the snapshot. ⚠ `!asking`, not `!!snapshot` — a FAILED snapshot must still let the
  // version column try, or a down box would leave it loading for ever.
  const fleetKeys = [
    ...new Set([
      ...(accountGroups ?? []).flatMap((g) => g.bots.map((b) => b.key)),
      ...bots.map((b) => b.key),
    ]),
  ]
  const versionQueries = useBotVersions(fleetKeys, !asking)
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

  /** Every bot on one account reports the SAME balance — one pot of money, not one each. A
   *  running bot's reading wins, else the newest a stopped one took; a stopped neighbour reporting
   *  none does not change what the account holds.
   *  ⚠ A STOPPED bot's figure is what MT5 said when it last read it, so it carries that time —
   *  shown as current it would read $0.00 on an account funded since (2026-09-14). */
  const balanceOf = (
    rows: { live: BotStatus | undefined }[]
  ): { balance: number; readAt: string | null } | null => {
    const read = rows
      .map((r) => r.live)
      .filter((b): b is BotStatus & { balance: number } => b?.balance != null)
    const b =
      read.find((x) => x.status === 'RUNNING') ??
      [...read].sort((x, y) => (y.last_updated ?? '').localeCompare(x.last_updated ?? ''))[0]
    return b ? { balance: b.balance, readAt: b.status === 'RUNNING' ? null : b.last_updated } : null
  }

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
  const balanceAt = (
    account: number,
    live: { balance: number; readAt: string | null } | null
  ): { balance: number | null; readAt: string | null } => {
    if (live != null) return live
    const e = earnByAccount.get(account)
    return { balance: e?.balance ?? null, readAt: e?.balance_read_at ?? null }
  }

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
  // stated still has to be on the page. ⚠ Just "Live" (2026-09-12, Aaron: *"we know it is live"*) —
  // the amber word says it; *real money* stays on the controls that spend it.
  const SECTIONS: { key: Side; label: React.ReactNode }[] = [
    { key: 'pending', label: <Shimmer className="h-[10px] w-[70px]" /> },
    { key: 'live', label: 'Live' },
    { key: 'demo', label: 'Demo' },
    { key: 'other', label: 'Not marked demo or live' },
  ]

  /**
   * Each section's accounts, PINNED ONE FIRST — one list, read by both the render below and the
   * expand default right after it, so "first in the section" can never mean two different things
   * in the same load. ⚠ Built off `shownAccounts` (the live/demo pill already applied), because
   * "first rendered" has to mean first among what is actually on screen, not among everything the
   * box knows about. ⚠ **This runs on whatever classification is CURRENTLY best-available** —
   * including the provisional `pending` bucket while the box or the registry has not answered —
   * because the account list itself needs neither: it is read off the local instance configs, and
   * a section built from it must never wait on the VPS to have something to show.
   */
  const sectionsWithAccounts = SECTIONS.map((s) => ({
    ...s,
    accounts: withPinnedFirst(
      shownAccounts.filter((a) => sideOf(typeOf(a.account, a.rows)) === s.key)
    ),
  }))

  /** Which accounts `sectionsWithAccounts` would default-open RIGHT NOW — the first (pinned or
   *  not) of each non-empty section. Recomputed every render; cheap, and its STRING form below is
   *  what decides whether the effect actually has new work. */
  const defaultExpandKeys = sectionsWithAccounts
    .filter((s) => s.accounts.length)
    .map((s) => accountKey(s.accounts[0].group))
  const defaultExpandSignature = defaultExpandKeys.join('|')

  /**
   * Default expand — KEPT LIVE until the reader touches a toggle, never again after.
   *
   * 🔴 **Two properties this has to hold AT ONCE, and a single "fire once" effect cannot (MEASURED
   * live, WATCHED RED in `bots-accounts.spec.ts`).** (1) Something must be open the instant the
   * account list renders — including with the VPS snapshot genuinely still pending, or the box
   * down — because the account list itself needs no VPS and a reader must never see every card
   * collapsed just because the box hasn't answered (this repo's rule 1, one layer up: visibility
   * of the row, not its status value). (2) Once Live/Demo classification actually resolves, the
   * default has to settle onto the CORRECT per-section pick — the bug this effect was first built
   * to fix, where firing the moment `accountGroups` landed (before `asking`/`registryPending`
   * cleared) put every account in one `pending` bucket and defaulted a single one open across the
   * WHOLE PAGE, forever, since a "fire once" ref never got a second chance once sections settled.
   *
   * The fix is to keep recomputing — `defaultExpandSignature` changes exactly when the pending
   * bucket resolves into real sections (or a pin moves) — and to stop FOREVER the moment the
   * reader has opened or closed anything by hand (`userTouchedExpand`, set inside `toggleAccount`).
   * Before that: every fresh classification is applied. After: nothing here writes again, so a
   * background 60s refetch or a pin write elsewhere can never silently override a manual choice.
   *
   * ⚠ **The pinned account IS "first" once `sectionsWithAccounts` reorders it** — rules 4 and 5
   * collapse into the same read: open whichever account is first in a section's rendered order,
   * pinned or not, provisional bucket or real one.
   */
  useEffect(() => {
    if (userTouchedExpand.current) return
    setExpandedAccounts(new Set(defaultExpandKeys))
    // ⚠ Depends on the SIGNATURE, not the array — `defaultExpandKeys` is a fresh array every
    // render, and depending on it would re-fire (and re-`setState`) every render forever, since a
    // shallow-equal array is still a new reference. The signature is a primitive: this only fires
    // again when the actual picks change.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [defaultExpandSignature])

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

  /** Run one bot's start/stop/restart, locking that bot alone until ITS call settles.
   *  ⚠ `mutateAsync`, never `mutate` with per-call callbacks: those fire only for the LATEST call
   *  on a mutation, so with two bots in flight the first one's lock would never clear. The hook's
   *  own `onError` still raises the toast; the rejection is caught here only so it is not
   *  reported twice. */
  function act(key: string, action: BotAction, fn: () => Promise<unknown>) {
    setPending((m) => new Map(m).set(key, action))
    fn()
      .catch(() => undefined)
      .finally(() =>
        setPending((m) => {
          const next = new Map(m)
          next.delete(key)
          return next
        })
      )
  }

  /**
   * Everything about one account, computed ONCE — read by both its compact rail row and its full
   * detail panel, so the two can never disagree about what an account IS (only about how much of
   * it to show at a time). Replaces the single `renderAccount` the fold/unfold accordion used,
   * split because a rail row and a detail panel are genuinely different views now, not one card
   * that folds — see `renderRailRow` / `renderDetailPanel` just below, and the note in
   * `notes/bots-page.md` for why the accordion was replaced the same day it shipped.
   */
  const prepareAccountView = ({ account, group, rows }: (typeof trading)[number]) => {
    const cap = group.cap_agrees ? group.risk_cap_pct : null
    const reg = regByAccount.get(account)
    const earn = earnByAccount.get(account)
    // With nothing on it reporting, the balance is the LAST one a bot read here, with its time —
    // never a live figure, and the card says so beside it. See `balanceAt`.
    const idle = rows.length === 0
    const { balance, readAt } = balanceAt(account, idle ? null : balanceOf(rows))
    // Computed once, up front — every ROW below reads its own entry rather than re-asking
    // `botCondition`, and the account's worst is the same reduce this page's own `worstCondition`
    // export runs for a single bot's own issues, just one level up.
    // ── the priority order ────────────────────────────────────────────────────
    // The rows arrive in the account's SAVED order already (the server sorts them: ranked first,
    // then anything unranked by name). A draft made by dragging replaces it until saved.
    //
    // ⚠ **`orderUnsaved` is the third state and it MATTERS** — with no rank saved, this list is
    // only the by-name fallback, so the top row is NOT the first to trade and nobody waits for
    // anybody. The bar below says exactly that rather than letting a ranked-looking list imply a
    // ranking that does not exist (rule 1: "no order" and "this order" may not look the same).
    const servedOrder = rows.map((r) => r.cfg.key)
    const servedSig = servedOrder.join('|')
    const draft =
      orderEdit && orderEdit.account === account && orderEdit.from === servedSig
        ? orderEdit.keys
        : null
    const order = draft ?? servedOrder
    const orderDirty = order.join('|') !== servedSig
    const orderUnsaved = rows.some((r) => r.cfg.priority == null)
    // One bot has nobody to go ahead of, and an unreadable config cannot be ranked — the server
    // refuses an order that is not exactly the account's bots, so it may not be offered here.
    // ⚠ And not while one of its bots is mid-action (2026-09-24): the order decides which bot sizes
    // first, and the server refuses the write then too.
    const orderLock = lockOf(rows.map((r) => r.cfg.key))
    const canReorder = rows.length > 1 && !rows.some((r) => r.cfg.unreadable) && orderLock === null
    const byKey = new Map(rows.map((r) => [r.cfg.key, r]))
    const rowConds = order
      .map((k) => byKey.get(k))
      .filter((r): r is (typeof rows)[number] => r !== undefined)
      .map(({ cfg, live }) => ({
        cfg,
        live,
        asked: live !== undefined,
        cond: botCondition(live, { asked: live !== undefined, onAccount: true }),
      }))
    // 🔴 THE RAIL MAY NOT HIDE A PROBLEM. 'ok'/'idle'/'unknown' are not findings: a healthy or
    // not-yet-answered bot earns no marker, only 'bad' (stopped, halted, error, an alert-level
    // review) and 'warn' (trading off, no MT5 link, locked, a warn-level review) do — the same
    // restraint the accordion's collapsed header used, just read by the rail row now instead.
    const worst = worstCondition(rowConds.map((r) => r.cond))
    return {
      account,
      group,
      rows,
      key: accountKey(group),
      cap,
      reg,
      earn,
      idle,
      balance,
      readAt,
      rowConds,
      worst,
      order,
      servedSig,
      orderDirty,
      orderUnsaved,
      canReorder,
    }
  }
  type AccountView = ReturnType<typeof prepareAccountView>

  /**
   * One compact line per account — the RAIL. Pin, worst-status marker, identity, two figures, and
   * the open/closed state itself — click toggles the account in the shared `expandedAccounts` set.
   * Any number from zero to all can be open; the open ones render in this same rail order in the
   * detail column.
   *
   * 🔴 **A LEDGER, NOT A STACK OF CARDS (2026-09-15, fourth pass — Aaron: *"the account list
   * design looks ugly"*).** Three things changed and each was a specific defect:
   *
   *  1. **The open row is no longer a saturated cyan fill.** It is the page's own raised surface
   *     plus a 2px coloured edge in its kind's colour. A filled block per open account, under a
   *     filled group band, left the column with no quiet ground to read anything against — and a
   *     fill that loud says "alarm" where all it means is "showing on the right".
   *  2. **The figures are RIGHT-ALIGNED in their own column**, mono and tabular, so % sits over %
   *     and equity over equity down the whole rail. They used to run inline after the name at two
   *     different sizes, which is why a column of money read as wrapped prose — the one thing a
   *     reader scans an account list FOR is the odd one out, and that needs a shared right edge.
   *  3. **Identity owns the left column**: number over name, both left-aligned on the same edge,
   *     with a fixed status gutter to the left of them so a row with a problem never shifts the
   *     number sideways relative to a row without one.
   *
   * ⚠ **The pin is revealed on hover/focus but keeps its space always** — a ★ outline on every
   * row was per-row noise in the corner of a 250px column, and collapsing its box on hover would
   * make every row twitch. Pinned rows show it permanently, because that one IS a state.
   *
   * ⚠ **Needs no VPS to render** — the account list is read off the local instance configs, so a
   * rail row (and its worst-status marker, off whatever the box HAS answered for) must never wait
   * on a slow or dead box.
   */
  const renderRailRow = (view: AccountView) => {
    const { account, group, key, reg, earn, worst, balance, readAt } = view
    const isOpen = expandedAccounts.has(key)
    const showWorst = !!worst && (worst.tone === 'bad' || worst.tone === 'warn')
    const pinned = !!group.pinned
    // The open row's edge takes the account's OWN kind colour — gold for real money, accent for
    // demo — so "which of these is open" and "which of these is live" are one glance, not two.
    // An unstated kind keeps the neutral accent rather than guessing live: see `kind.tsx`.
    const edge = reg?.kind === 'live' ? 'bg-gold' : 'bg-accent'
    return (
      <div
        key={key}
        data-testid="account-rail-row"
        className={`group/row relative flex items-stretch transition-colors ${
          isOpen ? 'bg-bg-surface-2' : 'hover:bg-bg-hover'
        }`}
      >
        {/* The open marker — a 2px edge, full row height. Drawn as an absolute sibling rather than
         *  a border on the row so opening an account never moves its text by 2px. */}
        <span
          aria-hidden
          className={`absolute left-0 top-0 bottom-0 w-[2px] ${isOpen ? edge : 'bg-transparent'}`}
        />
        <button
          data-testid="account-rail-toggle"
          onClick={() => toggleAccount(key)}
          aria-pressed={isOpen}
          title={
            isOpen
              ? `Hide account ${account} from the detail column`
              : `Show account ${account} in the detail column`
          }
          className="flex-1 min-w-0 grid grid-cols-[9px_minmax(0,1fr)_auto] items-center gap-x-[8px] gap-y-[2px] pl-[11px] pr-[2px] py-[9px] text-left"
        >
          {/* 🔴 A FIXED STATUS GUTTER, spanning both lines. 'ok'/'idle'/'unknown' are not findings
           *  — a healthy or not-yet-answered account earns no marker — but the COLUMN is always
           *  there, so the number beside it starts on the same x whether or not this account has a
           *  problem. The account's own worst-problem sentence is one hover away; the full pill
           *  still draws in the detail panel, where there is room for its words. */}
          <span className="col-start-1 row-start-1 row-span-2 flex items-center justify-center self-stretch">
            {showWorst && worst && (
              <span
                data-testid="rail-worst-dot"
                title={worst.title}
                className={`w-[6px] h-[6px] rounded-full shrink-0 ${TONE_DOT[worst.tone]}`}
              />
            )}
          </span>
          {/* LINE 1, LEFT — the account number, the row's identity and its dominant element. */}
          <span className="col-start-2 row-start-1 truncate text-[12.5px] font-mono font-bold tabular-nums text-text-primary">
            {account}
          </span>
          {/* LINE 1, RIGHT — the account's own return. The one span on this row still allowed real
           *  colour, because the sign of it is a finding. `compact` drops only the dollar
           *  net-change half (a different figure from the equity under it); the full sentence is
           *  one hover away on the same `title`. */}
          <span className="col-start-3 row-start-1 flex justify-end">
            <AccountNet e={earn} asking={asking} compact />
          </span>
          {/* LINE 2, LEFT — nickname else broker, off the same slow-to-answer registry the detail
           *  panel's own identity line reads (`nameOf`), so it shimmers for the same reason there
           *  rather than guessing "Account N" in the meantime. */}
          {!reg && registryPending ? (
            <Shimmer className="col-start-2 row-start-2 h-[11px] w-[56px]" />
          ) : (
            <span className="col-start-2 row-start-2 truncate text-[11.5px] text-text-secondary">
              {nameOf(reg, group)}
            </span>
          )}
          {/* LINE 2, RIGHT — equity, the same figure the detail panel's Equity stat shows, muted
           *  and smaller here since the rail's headline is the % above it. ⚠ Unread, not-read and
           *  a real balance are three different answers and each says which it is. */}
          <span className="col-start-3 row-start-2 flex justify-end min-w-0">
            {balance == null && asking ? (
              <Shimmer className="h-[10px] w-[52px]" />
            ) : balance == null ? (
              // Nothing has read it off MT5 — a dash, never a made-up word (Aaron, 2026-09-14:
              // "read exactly what's on the MT5. Don't create your own phrases").
              <span className="text-[10.5px] text-text-tertiary">—</span>
            ) : (
              <span
                title={readAt ? `Equity — last read ${readTime(readAt)}.` : 'Equity'}
                className="text-[10.5px] font-mono tabular-nums text-text-tertiary truncate"
              >
                {money(balance, false)}
              </span>
            )}
          </span>
        </button>
        {/* Pin — a sibling of the toggle button (never nested inside it), centred on the row now
         *  that the row is a two-line ledger rather than two stacked flex lines. Its BOX is always
         *  there; only its ink comes and goes, so no row moves when the pointer crosses it. */}
        <span
          className={`shrink-0 self-center pr-[4px] transition-opacity ${
            pinned
              ? 'opacity-100'
              : 'opacity-0 group-hover/row:opacity-100 focus-within:opacity-100'
          }`}
        >
          <PinToggle
            pinned={pinned}
            disabled={setPin.isPending && setPin.variables?.account === account}
            onClick={() => setPin.mutate({ account, pinned: !pinned })}
          />
        </span>
      </div>
    )
  }

  /**
   * One account inside the FLEET TABLE (2026-09-15, fifth pass — Aaron picked this off a mockup:
   * *"build the design from before"*). A BAND carrying the account, its bots on the shared
   * five-track grid, then its unattributed line. **No card and no headings of its own** — the
   * table draws both ONCE for every open account, which was the point of the rebuild: three open
   * accounts drew the same nine headings three times.
   *
   * 🔴 **What left the band, and where it went.** The old stat cluster (Cap / Return / Avg per bot
   * / Equity, each under its own label) became: the risk BUDGET (`RiskBudget` — the cap and how
   * much of it the bots hold, which is what decides whether another bot fits), the account's
   * return, and its equity. **Avg per bot went** — it was a mean of the per-bot Return % the rows
   * no longer carry, so it would have been a summary of figures nobody can see.
   *
   * ⚠ **Still no LIVE/DEMO chip here** (Aaron, 2026-09-10: *"we don't need to be redundant on data
   * anywhere on this page"*) — the rail's section heading and its open edge already say it.
   *
   * ⚠ **The equity is MT5's figure, or a dash** — never a made-up phrase (Aaron, 2026-09-14:
   * *"read exactly what's on the MT5"*). While the box is still being asked it shimmers.
   */
  const renderDetailPanel = (view: AccountView, index: number) => {
    const {
      account,
      group,
      key,
      cap,
      reg,
      earn,
      idle,
      balance,
      readAt,
      rowConds,
      order,
      servedSig,
      orderDirty,
      orderUnsaved,
      canReorder,
    } = view
    return (
      <section
        key={key}
        data-testid="account-detail"
        data-account={account}
        className={index > 0 ? 'border-t border-border-default' : ''}
      >
        {/* 🔴 The whole band opens the account (Aaron, 2026-09-16). Its own configure icon went: it
         *  could not sit under the bots' configure icons, because a bot row hides its "···" while a
         *  deploy pill shows, so their icon moves. */}
        <div
          data-testid="account-band"
          role="button"
          tabIndex={0}
          title="Open this account — balance, risk cap, and which bots are on it"
          onClick={() => set('account', String(account))}
          onKeyDown={(e) => {
            if (e.key === 'Enter' || e.key === ' ') {
              e.preventDefault()
              set('account', String(account))
            }
          }}
          className={`grid ${GRID} items-center gap-3 pr-3 py-[10px] bg-bg-sunken/60 border-b border-border-subtle cursor-pointer transition-colors hover:bg-bg-surface-2`}
        >
          {/* 🔴 THE NUMBER LEADS (2026-09-06) — the login is what the broker, the terminal and every
           *  refusal message name the account by; the nickname is something somebody typed here. */}
          <span className="col-span-2 flex items-center gap-3 min-w-0 pl-4">
            <span className="text-[13.5px] font-mono font-semibold tabular-nums shrink-0">
              {account}
            </span>
            {!reg && registryPending ? (
              <Shimmer className="h-[13px] w-[64px]" />
            ) : (
              <span className="text-[13px] text-text-secondary truncate">{nameOf(reg, group)}</span>
            )}
            {/* Only the states worth a glance get a pill: no bot on it (grey — a resting state), and
             *  the two cap FAULTS (a disagreement stops every bot here from starting; no cap means
             *  nothing refuses an oversized trade). A cap that is simply set is the budget line. */}
            {idle ? (
              <span
                data-testid="idle-chip"
                title="No bot is on this account right now. Its equity and return are what it grew to before its bots left — add a bot to trade it again."
                className="inline-flex items-center text-[10.5px] font-semibold px-[7px] py-[3px] rounded-pill uppercase tracking-[0.4px] bg-bg-surface-2 text-text-tertiary border border-border-default cursor-default"
              >
                no bot
              </span>
            ) : !group.cap_agrees ? (
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
            ) : null}
          </span>

          {/* 🔴 The band sits on the bots' own grid (Aaron, 2026-09-16), so each figure lines up
           *  with a column on every account: the return under Performance, the cap under Version,
           *  the equity under Actions. */}
          <span className="min-w-0">
            <AccountNet e={earn} asking={asking} />
          </span>
          <span className="min-w-0">
            <RiskBudget group={group} cap={cap} idle={idle} />
          </span>
          <span
            data-testid="account-equity"
            className="flex justify-end text-[16px] font-mono tabular-nums font-semibold"
          >
            {balance == null && asking ? (
              <Shimmer>$00,000.00</Shimmer>
            ) : balance == null ? (
              <span className="text-[12px] text-text-tertiary cursor-default">—</span>
            ) : readAt && idle ? (
              // No bot here, so the "no bot" pill already says this figure cannot be live; the
              // read time is a hover, not a second say-so beside the number.
              <span
                title={`What MT5 showed on ${readTime(readAt)}, before its bots left. No bot is on this account now, so nothing reads it live.`}
                className="cursor-default"
              >
                {money(balance, false)}
              </span>
            ) : readAt ? (
              // A bot IS here but none is reading it live — nothing else on the band says this
              // figure is old, so the time stays on screen.
              <span
                title={`What MT5 showed on ${readTime(readAt)}. No bot on this account is reading it live now.`}
                className="flex flex-col items-end gap-[1px] cursor-default"
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
        </div>

        {rowConds.map(({ cfg, live, asked, cond }, i) => {
          const be = earnOf(account, cfg.key)
          const running = live?.status === 'RUNNING'
          // The NAME comes from the config, which is always readable — a bot the box has not
          // answered for still has one.
          const name = live?.name ?? cfg.display
          const acting = actionOf(cfg.key)
          return (
            <div
              key={cfg.key}
              data-testid="bot-row"
              data-bot={cfg.key}
              draggable={canReorder}
              onDragStart={(e) => {
                if (!canReorder) return
                e.dataTransfer.effectAllowed = 'move'
                e.dataTransfer.setData('text/plain', cfg.key)
                setDragKey(cfg.key)
              }}
              onDragOver={(e) => {
                if (!dragKey) return
                e.preventDefault()
                e.dataTransfer.dropEffect = 'move'
                setOverKey(cfg.key)
              }}
              onDragLeave={() => setOverKey((k) => (k === cfg.key ? null : k))}
              onDrop={(e) => {
                e.preventDefault()
                if (dragKey) moveBot(account, order, servedSig, dragKey, i)
                setDragKey(null)
                setOverKey(null)
              }}
              onDragEnd={() => {
                setDragKey(null)
                setOverKey(null)
              }}
              className={`group grid ${GRID} items-center gap-3 pr-3 py-[10px] transition-colors hover:bg-bg-surface-2 ${
                i > 0 ? 'border-t border-border-subtle' : ''
              } ${dragKey === cfg.key ? 'opacity-40' : ''} ${
                overKey === cfg.key && dragKey !== cfg.key ? 'bg-accent/10' : ''
              }`}
            >
              {/* The NAME is the button, not the whole row — a row-wide click behind the controls
               *  would make every miss open a drawer over the thing you were aiming at. */}
              <span className="flex items-center min-w-0 pl-[2px]">
                {/* ⚠ **The grip KEEPS ITS SPACE on every row and is only REVEALED on hover** — the
                 *  rail's pin idiom, for the rail's reason: a box that collapses would twitch every
                 *  bot name sideways as the pointer crosses the list. An account with ONE bot gets
                 *  the space and no grip: there is nobody to go ahead of. */}
                <span
                  data-testid="bot-grip"
                  aria-hidden
                  title="Drag to set which bot trades first"
                  className={`w-[14px] shrink-0 flex justify-center text-text-tertiary ${
                    canReorder
                      ? 'opacity-0 group-hover:opacity-100 transition-opacity cursor-grab active:cursor-grabbing'
                      : 'invisible'
                  }`}
                >
                  <GripVertical size={12} />
                </span>
                <button
                  onClick={() => set('bot', cfg.key)}
                  title={`Open ${name} — risk, return, version, account and its settings`}
                  className="flex items-center font-medium text-[13px] text-left min-w-0"
                >
                  <span className="truncate group-hover:text-accent transition-colors">{name}</span>
                </button>
              </span>

              {/* 🔴 ONE status per row (2026-09-12) — the worst problem or what the bot is doing,
               *  a count of anything else, and the whole story on hover. */}
              {!asked && asking ? (
                <Shimmer className="h-[12px] w-[90px]" />
              ) : (
                <StatusText cond={cond} />
              )}

              <Performance e={be} asking={asking} top={topBot === cfg.key} />

              {/* Calm when current, amber only when it needs a person — the pill's own rule, and
               *  the same one the "needs you" line above the table counts by (`versionNeed`). */}
              <VersionPill
                version={versionByKey.get(cfg.key)?.data}
                loading={versionByKey.get(cfg.key)?.isPending}
                deploying={jobByKey.get(cfg.key)?.status === 'running'}
                error={versionByKey.get(cfg.key)?.error}
                restart={restartReason(versionByKey.get(cfg.key)?.data, live, snapshot?.fetched_at)}
              />

              <span className="flex gap-[4px] justify-end items-center">
                {/* 🔴 **NOTHING IS OFFERED WHILE THE STATE IS UNKNOWN (2026-09-06).** Pressing
                 *  Start on a bot that is already trading is the one mistake this row can make
                 *  that costs money, and an unanswered box is a reason to ask again, never to act. */}
                {acting ? (
                  <BotActionPill action={acting} />
                ) : !asked && asking ? (
                  <>
                    <Shimmer className="h-[26px] w-[52px]" />
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
                  <PrimaryBtn
                    label="Stop"
                    tone="neg"
                    disabled={busyFor(cfg.key)}
                    onClick={() => act(cfg.key, 'stop', () => stopOne.mutateAsync(cfg.key))}
                  />
                ) : (
                  <PrimaryBtn
                    label="Start"
                    tone="pos"
                    disabled={busyFor(cfg.key)}
                    onClick={() => act(cfg.key, 'start', () => startOne.mutateAsync(cfg.key))}
                  />
                )}
                {/* ⚠ **Configure STAYS on the row, not in the "···" (2026-09-15).** Aaron lost this
                 *  control twice when it was something to find — once as a whole row, once as a bare
                 *  icon among three others (*"where is configure?"*). The menu takes only what a
                 *  reader never goes looking for. Same target as clicking the name. */}
                <IconBtn
                  testId="configure-bot"
                  icon={SlidersHorizontal}
                  title={`Configure ${name} — risk per trade, version, account and all its settings`}
                  onClick={() => set('bot', cfg.key)}
                />
                {/* Hidden while this bot's pill shows — the pill needs the room. The drawer keeps
                 *  its own Logs and Restart throughout. */}
                {!acting && (
                  <OverflowMenu
                    testId="bot-menu"
                    label={`More for ${name}`}
                    items={[
                      ...(asked && running
                        ? [
                            {
                              key: 'restart',
                              label: 'Restart',
                              icon: RotateCcw,
                              testId: 'bot-restart',
                              disabled: busyFor(cfg.key),
                              onSelect: () =>
                                act(cfg.key, 'restart', () => restartOne.mutateAsync(cfg.key)),
                            },
                          ]
                        : []),
                      {
                        key: 'logs',
                        label: 'Logs',
                        icon: FileText,
                        testId: 'bot-logs',
                        onSelect: () => setLogBot(cfg.key),
                      },
                    ]}
                  />
                )}
              </span>
            </div>
          )
        })}

        {/* ── who goes first ──────────────────────────────────────────────────
         *  Shown only when there is something to say: an order that has been DRAGGED and not yet
         *  saved, or an account whose bots have no saved order at all. An account already ranked
         *  and untouched says nothing — the row order IS the answer, and a permanent bar under
         *  every account repeating it is the redundancy this page has a rule against. */}
        {canReorder && (orderDirty || orderUnsaved) && (
          <div
            data-testid="priority-bar"
            data-state={orderDirty ? 'dirty' : 'unsaved'}
            className={`flex items-center gap-3 pl-4 pr-3 py-[8px] border-t border-border-subtle ${
              orderDirty ? 'bg-accent-muted/50' : ''
            }`}
          >
            <span className="text-[11.5px] text-text-tertiary leading-[1.5]">
              {orderDirty
                ? 'Top of the list trades first when two of these signal together. Save to keep this order.'
                : 'Drag a bot up or down to set which one trades first when two signal together — no order is saved here yet, so none of them waits for the others.'}
            </span>
            <span className="ml-auto flex items-center gap-2 shrink-0">
              {orderDirty && (
                <button
                  data-testid="priority-discard"
                  onClick={() => setOrderEdit(null)}
                  className="px-3 py-[5px] rounded-md text-[12px] border border-border-default text-text-secondary hover:bg-bg-hover hover:text-text-primary transition-colors"
                >
                  Discard
                </button>
              )}
              <button
                data-testid="priority-save"
                disabled={savePriority.isPending || lockOf(order) !== null}
                title={lockOf(order) ?? undefined}
                onClick={() =>
                  savePriority.mutate({ account, order }, { onSuccess: () => setOrderEdit(null) })
                }
                className="inline-flex items-center gap-[6px] px-3 py-[5px] rounded-md text-[12px] font-semibold bg-accent-muted text-accent-text border border-accent/50 hover:bg-accent/15 transition-colors disabled:opacity-40 disabled:cursor-not-allowed"
              >
                {savePriority.isPending && <Loader2 size={12} className="animate-spin" />}
                {savePriority.isPending ? 'Saving…' : 'Save order'}
              </button>
            </span>
          </div>
        )}

        {/* No bot on it now — an invitation, not a tombstone. ⚠ Disabled with the reason, never
         *  hidden, when the account cannot take a bot (no terminal logged into it). */}
        {idle && (
          <div
            data-testid="no-bot-row"
            className={`grid ${GRID} items-center gap-3 pr-3 py-[10px]`}
          >
            <span className="col-span-4 flex items-center pl-4 text-[12.5px] text-text-tertiary">
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

        {earn && <Unattributed e={earn} />}
      </section>
    )
  }

  /** Every account's view, computed ONCE and keyed by its identity — the rail and the detail
   *  column both read the same entry, so a rail row and its detail panel (when open) can never
   *  disagree about what an account IS. Built off `sectionsWithAccounts`, which already applies
   *  the live/demo pill and the pinned-first order both surfaces render in. */
  const accountViews = new Map(
    sectionsWithAccounts
      .flatMap((s) => s.accounts)
      .map((a) => [accountKey(a.group), prepareAccountView(a)])
  )
  /** The accounts to draw in the detail column, in RAIL ORDER — Live section's pinned-first
   *  order, then Demo's, then anything left (2026-09-15, Aaron's call via the coordinator: "in
   *  rail order… so toggling accounts on/off never reshuffles panels that are already open"). */
  const openAccountKeys = sectionsWithAccounts
    .flatMap((s) => s.accounts)
    .map((a) => accountKey(a.group))
    .filter((k) => expandedAccounts.has(k))

  /**
   * What needs a person RIGHT NOW, across every account with a bot on it — the "needs you" line
   * over the table (2026-09-15). Nothing on the page used to say it: two stopped bots and two
   * unpushed versions were found by reading every row.
   *
   * 🔴 **It invents no rule of its own.** A bot counts when its row's own status is a problem
   * (`botCondition`'s `bad`/`warn`, the same condition the Status cell draws) or its version pill is
   * amber (`versionNeed`, the same rule the pill draws by). Grouped by the row's own WORD, so the
   * line and the rows can never name one bot's problem two ways.
   *
   * ⚠ **Nothing while the box is still being asked** — a finding may not be shown before its
   * source has answered, and a bot the box did NOT answer for is `unknown`, which is not a problem
   * this line may claim.
   */
  const VERSION_WORD: Record<VersionNeed, string> = {
    undeployed: 'Not deployed',
    behind: 'Behind',
    restart: 'Needs a restart',
    unpushed: 'Not pushed',
  }
  const needs = (() => {
    if (asking) return []
    const byWord = new Map<string, { tone: 'bad' | 'warn'; bots: number; where: Set<string> }>()
    const note = (word: string, tone: 'bad' | 'warn', where: string) => {
      const e = byWord.get(word) ?? { tone, bots: 0, where: new Set<string>() }
      e.bots += 1
      e.where.add(where)
      if (tone === 'bad') e.tone = 'bad'
      byWord.set(word, e)
    }
    for (const v of accountViews.values()) {
      const where = nameOf(v.reg, v.group)
      for (const { cfg, live, asked, cond } of v.rowConds) {
        if (asked && (cond.tone === 'bad' || cond.tone === 'warn'))
          note(cond.word, cond.tone, where)
        const ver = versionByKey.get(cfg.key)?.data
        const need = versionNeed(ver, restartReason(ver, live, snapshot?.fetched_at))
        if (need) note(VERSION_WORD[need], 'warn', where)
      }
    }
    return [...byWord.entries()]
      .map(([word, e]) => ({ word, ...e, where: [...e.where] }))
      .sort((a, b) => (a.tone === b.tone ? 0 : a.tone === 'bad' ? -1 : 1))
  })()

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
            {accountName(a) ?? `Account ${a.account}`}
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
    // 🔴 **A FLEX COLUMN SIZED TO THE PAGE, not plain block flow (2026-09-15)** — Aaron: "I want
    // the accounts side panel to stretch the entire height of the page" / "when there's no
    // accounts open... just fill the whole page, this cropping behaviour... I don't like it."
    // `min-h-full`, not `h-full`: the app shell's `<main>` (`App.tsx`) is the scroll container
    // with a genuinely definite height (`flex-1` inside `h-screen`), so this resolves against a
    // real value — but `min-` rather than a hard height is what lets a tall Trading tab (many
    // accounts open, long bot tables) grow PAST the viewport and let `main`'s own scroll take
    // over, exactly the standard "sticky footer" flex pattern, instead of a fixed box that could
    // clip or fight that content. Only the trading tab's own accounts section below actually
    // stretches (`flex-1 min-h-0`, replacing a content-based `min-h-[420px]` floor) — the header
    // and tab strip keep their natural height as ordinary flex children.
    <div className="min-h-full flex flex-col">
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
            {/* The "N balances unread" count is gone (2026-09-14). A bot that cannot read MT5
             *  says so on its own row ("No MT5 link"), and an account nothing has read shows a
             *  dash where its equity goes — the count said the same thing a third time, in words
             *  nobody could act on. */}
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
            data-testid="refresh-bots"
            onClick={refreshAll}
            title={
              dataUpdatedAt
                ? `Updated ${relativeTime(new Date(dataUpdatedAt).toISOString())}`
                : 'Refresh'
            }
            className="w-[28px] h-[28px] grid place-items-center rounded-md border border-border-default text-text-tertiary hover:text-text-primary hover:bg-bg-hover transition-colors"
          >
            <RefreshCw size={12} className={refreshing ? 'animate-spin' : ''} />
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
      <VpsSyncDrawer open={syncOpen} onClose={() => setSyncOpen(false)} lock={lockOf(fleetKeys)} />

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
        <div className="flex flex-col gap-[22px] flex-1 min-h-0">
          {/* 🔴 RAIL + DETAIL (2026-09-15), replacing the fold/unfold accordion the SAME DAY it
           *  shipped — Aaron reviewed three layout mockups and picked this one. A compact line per
           *  account on the left; every account currently OPEN gets its full content stacked on
           *  the right, in rail order. Not single-select: any number from zero to all can be open.
           *  ⚠ **Only drawn once there is at least one account with a bot on it** — with none, the
           *  "No account has a bot on it" message below stands alone rather than sitting beside an
           *  empty rail and an empty detail column both saying the same thing a third way. */}
          {trading.length > 0 && (
            // 🔴 `items-stretch`, not `items-start` (2026-09-15, Aaron on the running page: "make
            // the side vertical bar look better... have it show it's the height of the page").
            // 🔴 **`flex-1 min-h-0`, not a `min-h-[420px]` floor (2026-09-15, third pass)** — Aaron,
            // on the real page with nothing open: "I want the accounts side panel to stretch the
            // entire height of the page," and a content-based floor is a GUESSED number that falls
            // short on anything taller than 420px. This row is now the sole `flex-1` child of the
            // page's own flex column (see the page root's own comment above this return), so its
            // height is genuinely "whatever is left of the viewport" — `min-h-0` lets it shrink
            // below its own content's natural size rather than refusing to (a flex item's default),
            // so it actually SETTLES at the leftover space instead of only ever growing past it.
            // The rail's own panel below is still `h-full` on its own inner child only — see that
            // panel's comment for the CSS trap this row's own height must stay clear of: a flex
            // item that stretches must never carry an explicit height itself (only `min-`/`flex-`),
            // or a percentage resolving against it can compute to `auto` and silently cancel the
            // stretch one level down, which is exactly what broke this same row in the second pass.
            <div className="flex items-stretch gap-4 flex-1 min-h-0">
              <div className="w-[248px] shrink-0">
                {/* 🔴 ONE PANEL, ONE BORDER (2026-09-15, exact spec, replacing the divided-subsections
                 *  version above). Live then Demo live INSIDE this single bordered panel now — not
                 *  two panels, and not `SideSection`'s small dot-plus-label heading — each named by
                 *  its own full-width `RailGroupBar` (gold/accent fill) instead. This is the panel
                 *  that stretches full height; nothing about that changed. `overflow-hidden` so each
                 *  bar's colour fill respects the panel's own rounded corners at the top. */}
                <div className="bg-bg-surface border border-border-subtle rounded-lg h-full flex flex-col overflow-hidden">
                  <div className="flex flex-col overflow-y-auto flex-1">
                    {sectionsWithAccounts
                      .filter((s) => s.accounts.length)
                      .map(({ key, label, accounts }, i) => {
                        const isKind = key === 'live' || key === 'demo'
                        // Hairlines sit BETWEEN rows within a group only — never after the last row,
                        // never between a group's own bar/label and its first row. `divide-y` gives
                        // exactly that for free on the row list; groups butt directly against each
                        // other with no extra divider of their own (the coloured bar, or the next
                        // group's label, is the only separation between groups).
                        const rowList = (
                          <div className="flex flex-col divide-y divide-border-subtle">
                            {accounts.map((a) =>
                              renderRailRow(accountViews.get(accountKey(a.group))!)
                            )}
                          </div>
                        )
                        if (isKind) {
                          return (
                            <div key={key} data-testid={`section-${key}`}>
                              <RailGroupBar kind={key} label={label} count={accounts.length} />
                              {rowList}
                            </div>
                          )
                        }
                        // `pending` (still classifying) and `other` (kind nobody stated) are not
                        // real live/demo groups, so they keep the page's existing subtle-label
                        // treatment rather than borrowing the gold/accent bar built for a kind.
                        return (
                          <div
                            key={key}
                            className={`px-[8px] pb-[8px] ${i === 0 ? 'pt-[8px]' : 'pt-[16px]'}`}
                          >
                            <SideSection side={key} label={label}>
                              {rowList}
                            </SideSection>
                          </div>
                        )
                      })}
                  </div>
                </div>
              </div>

              <div className="flex-1 min-w-0 flex flex-col gap-[12px]">
                {needs.length > 0 && (
                  <div
                    data-testid="needs-you"
                    className="flex items-baseline gap-x-[16px] gap-y-1 flex-wrap pl-3 py-[2px] border-l-2 border-warn text-[12.5px] text-text-secondary"
                  >
                    <span className="text-[10.5px] font-bold uppercase tracking-[0.8px] text-warn-text">
                      Needs you
                    </span>
                    {needs.map((n) => (
                      <span key={n.word} data-testid="needs-item" className="cursor-default">
                        <span
                          className={`font-semibold ${n.tone === 'bad' ? 'text-neg-text' : 'text-warn-text'}`}
                        >
                          {n.word}
                        </span>{' '}
                        — {n.bots} bot{n.bots === 1 ? '' : 's'} on {n.where.join(', ')}
                      </span>
                    ))}
                  </div>
                )}
                {openAccountKeys.length === 0 ? (
                  // 🔴 **`flex-1` + its own centering, not a content-sized box (2026-09-15)** — Aaron:
                  // *"when there's no accounts open... just fill the whole page, this cropping
                  // behaviour... I don't like it."* `EmptyState` pads itself to a fixed height
                  // (`py-[90px]`) and does not know how tall its parent is, so left alone this panel
                  // stopped wherever that padding ended — a hard edge partway down the page, with the
                  // rail (now genuinely full height) beside a shorter box. `flex-1` grows this panel
                  // to the SAME height the rail gets from the row's own stretch; `items-center
                  // justify-center` then centres `EmptyState`'s content inside that full height,
                  // rather than leaving it pinned to the top with the extra space sitting unused below.
                  <div className="bg-bg-surface border border-border-subtle rounded-lg flex-1 flex items-center justify-center">
                    <EmptyState
                      icon={<MousePointerClick size={20} />}
                      title="No account open"
                      description="Pick one or more accounts on the left to see their bots, risk and version."
                    />
                  </div>
                ) : (
                  // 🔴 **ONE TABLE for every open account (2026-09-15)** — its headings drawn once,
                  // each account a band inside it. ⚠ No `overflow-hidden`: a row's "···" menu opens
                  // past the table's edge on the last row, and clipping it would hide Restart.
                  <div
                    data-testid="fleet-table"
                    className="bg-bg-surface border border-border-subtle rounded-lg"
                  >
                    <ColumnHeadings />
                    {openAccountKeys.map((k, i) => renderDetailPanel(accountViews.get(k)!, i))}
                  </div>
                )}
              </div>
            </div>
          )}

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
                    </button>
                    <BenchedIssues bot={bot} />
                    <span className="ml-auto text-[12px] text-text-tertiary">
                      {versionByKey.get(bot.key)?.data?.frozen ? 'idle' : 'never deployed'}
                    </span>
                    <IconBtn icon={FileText} title="Logs" onClick={() => setLogBot(bot.key)} />
                    <IconBtn
                      testId="configure-bot"
                      icon={SlidersHorizontal}
                      title={`Configure ${bot.name}`}
                      onClick={() => set('bot', bot.key)}
                    />
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
          fetchedAt={snapshot?.fetched_at}
          job={jobByKey.get(selBot.key)}
          busy={busyFor(selBot.key)}
          pendingAction={actionOf(selBot.key)}
          // Its promise tells the panel when the whole thing is over — a removal closes it then.
          onStopThen={(what, then, opts) => stopThen(selBot.key, labelOf(selBot), what, then, opts)}
          // The CONFIG's account, or `undefined` until the configs are read — never "on no
          // account" for a list that has not arrived, or the panel would hide Remove on a bot
          // that is on one.
          configAccount={accountGroups === undefined ? undefined : accountOfBot(selBot.key)}
          onClose={() => set('bot', null)}
          onLogs={() => setLogBot(selBot.key)}
          onStart={() => act(selBot.key, 'start', () => startOne.mutateAsync(selBot.key))}
          onStop={() => act(selBot.key, 'stop', () => stopOne.mutateAsync(selBot.key))}
          onRestart={() => act(selBot.key, 'restart', () => restartOne.mutateAsync(selBot.key))}
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
            botByKey={botByKey}
            onClose={() => set('account', null)}
            // A bot's name on the account panel opens that bot's panel (and closes this one).
            onOpenBot={(k) => set('bot', k)}
            onStart={(k) => act(k, 'start', () => startOne.mutateAsync(k))}
            onStop={(k) => act(k, 'stop', () => stopOne.mutateAsync(k))}
            onStopThen={(k, label, what, then) => stopThen(k, label, what, then)}
            actionOf={actionOf}
            busyFor={busyFor}
            lock={lockOf(
              (
                groupByAccount.get(Number(selAccount)) ??
                emptyGroup(regByAccount.get(Number(selAccount)) as BotAccountRegistration)
              ).bots.map((b) => b.key)
            )}
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
