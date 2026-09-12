import type { BotPosition, BotStatus } from '@/types'

/**
 * ONE reading of a bot's state, for every list of bots — the Bots page and the Overview.
 *
 * 🔴 **Rebuilt 2026-09-12 from a pile of tags.** A row carried up to five of them beside the bot's
 * name — no link, trading off, halted, review, trade open — each its own colour and shape, and on
 * the live account two of them wrapped and cut the name to "SOS …". Aaron: *"my eyes don't know
 * where to go."* A row now says ONE thing: on a running bot the worst problem, else what it is
 * doing. Any other problem is counted beside that word and spelled out on hover.
 *
 * ⚠ **Colour marks the EXCEPTION.** `bad` needs a person, `warn` is worth a look, and a healthy
 * running bot is a green dot beside grey words — the dot is the only colour it gets.
 *
 * ⚠ **Every flag is read as the field states it: `=== false` / `=== true` only.** `null` is
 * could-not-ask, and a problem is never raised off a question nobody answered (rule 1).
 *
 * ⚠ **Only a RUNNING bot's problem takes the word.** A stopped, errored or benched bot keeps its own
 * word and counts its problems beside it — the problems explain the stop, a red dot beside "Needs
 * review" alone reads as a running bot, and on the Overview, where benched bots share one list with
 * the rest, "Benched" is the only thing saying so.
 */

export type Tone = 'bad' | 'warn' | 'ok' | 'idle' | 'unknown'
export type IssueKey = 'halted' | 'review' | 'trading-off' | 'no-link' | 'locked'
export type StateKey =
  IssueKey | 'running' | 'in-trade' | 'stopped' | 'error' | 'benched' | 'unknown'

export interface Issue {
  key: IssueKey
  tone: 'bad' | 'warn'
  word: string
  detail: string
}

/** The trade a bot holds AT THE BROKER, as its heartbeat read it. */
export interface TradeView {
  /** "Long 0.40 lots" — the unit is named, because a bare figure here is where ounces get read
   *  as lots. */
  head: string
  /** "+1.2R" and its sign, or `null` when the risk the trade opened with is unknown. */
  r: { text: string; sign: -1 | 0 | 1 } | null
  title: string
}

export interface Condition {
  /** What the row's one word names: the lead problem's key, else the bot's base state. */
  state: StateKey
  tone: Tone
  word: string
  /** The tone of what the WORD names — its problem's, or the bot's own state's. The dot carries
   *  the row's worst; the word carries only its own, so "Benched" is never painted red for a
   *  problem it does not name. */
  wordTone: Tone
  /** Problems beyond the one the word names — counted beside it, spelled out on hover. */
  more: number
  /** The worst of those, so a "+1" hiding a halt says so in its colour. `null` when there are none. */
  moreTone: 'bad' | 'warn' | null
  issues: Issue[]
  /** Set whenever the bot holds a trade, whatever else is wrong: a halted bot WITH a position is
   *  the case where the position matters most. */
  trade: TradeView | null
  /** Everything, in words: the state and how long it has run, each problem, and the trade. */
  title: string
}

const RANK: Record<Tone, number> = { unknown: 0, idle: 1, ok: 2, warn: 3, bad: 4 }

/** "44m", "3h 12m", "1d 20h". */
export function formatUptime(seconds: number): string {
  if (seconds < 3600) return `${Math.floor(seconds / 60)}m`
  const h = Math.floor(seconds / 3600)
  const m = Math.floor((seconds % 3600) / 60)
  if (h >= 24) return `${Math.floor(h / 24)}d ${h % 24}h`
  return `${h}h ${m}m`
}

const sentence = (s: string) => (s ? `${s[0].toUpperCase()}${s.slice(1)}` : s)
const stop = (s: string) => (/[.!?]$/.test(s) ? s : `${s}.`)

const price = (v: number) =>
  v.toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 5 })
const dollars = (v: number) =>
  `$${Math.abs(v).toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`
const signedDollars = (v: number) => `${v < 0 ? '−' : '+'}${dollars(v)}`
const signed = (v: number, digits: number) =>
  `${v > 0 ? '+' : v < 0 ? '−' : ''}${Math.abs(v).toFixed(digits)}`

/** "+1.2R", "−0.4R" or "0.0R" — one decimal, and the sign read off the ROUNDED figure, so +0.04R
 *  reads 0.0R, uncoloured. `null` when the R is unknown: never a figure off a stop that moved. */
function positionR(p?: BotPosition | null): TradeView['r'] {
  if (p?.r == null || !Number.isFinite(p.r)) return null
  const v = Math.round(p.r * 10) / 10
  return { text: `${signed(v, 1)}R`, sign: v > 0 ? 1 : v < 0 ? -1 : 0 }
}

function positionHead(p?: BotPosition | null): string {
  if (!p) return 'In a trade'
  const side = p.side === 'mixed' ? 'Both sides' : sentence(p.side)
  return `${side} ${p.lots.toFixed(2)} lots`
}

function positionTitle(p?: BotPosition | null): string {
  const lines: string[] = []
  if (!p) {
    lines.push('It holds a position at the broker; its details could not be read.')
  } else {
    const side =
      p.side === 'mixed' ? 'Positions on BOTH sides' : p.side === 'long' ? 'Long' : 'Short'
    lines.push(
      `${side} ${p.lots.toFixed(2)} lots` +
        (p.entry != null ? ` at ${price(p.entry)}${p.tickets > 1 ? ' (average)' : ''}` : '') +
        (p.stop != null ? ` · stop ${price(p.stop)}` : ' · no stop at the broker')
    )
    if (p.side === 'mixed') lines.push('The bot halts on this: it takes one side at a time.')
    if (p.profit_usd == null) lines.push('Open profit not reported.')
    else if (p.r != null && p.risk_usd != null)
      lines.push(
        `Open profit ${signedDollars(p.profit_usd)}: ${signed(p.r, 2)}R of the ` +
          `${dollars(p.risk_usd)} risked at entry.`
      )
    else
      lines.push(
        `Open profit ${signedDollars(p.profit_usd)}. ` +
          'R unknown: the risk this trade opened with is not on record.'
      )
    if (p.tickets > 1)
      lines.push(
        `${p.tickets} positions: the trade plus ${p.tickets - 1} added lot${p.tickets > 2 ? 's' : ''}.`
      )
  }
  lines.push('Read off the broker by the bot every 10 seconds; this page refreshes every minute.')
  return lines.join('\n')
}

function tradeView(p?: BotPosition | null): TradeView {
  return { head: positionHead(p), r: positionR(p), title: positionTitle(p) }
}

/** Every problem the bot reports, worst first. */
function issuesOf(bot: BotStatus): Issue[] {
  const out: Issue[] = []
  if (bot.bridge_state === 'halted') {
    out.push({
      key: 'halted',
      tone: 'bad',
      word: 'Halted',
      detail: [
        'it places no orders until it is restarted.',
        bot.halt_reason ? stop(sentence(bot.halt_reason)) : '',
        'Anything open keeps its broker stop.',
      ]
        .filter(Boolean)
        .join(' '),
    })
  }
  const review = bot.review
  const reviewIssue: Issue | null = review
    ? {
        key: 'review',
        tone: review.level === 'alert' ? 'bad' : 'warn',
        word: 'Needs review',
        detail: '\n' + review.findings.map((f) => `• ${f.title}\n  ${f.detail}`).join('\n'),
      }
    : null
  if (reviewIssue?.tone === 'bad') out.push(reviewIssue)
  if (bot.trade_allowed === false) {
    out.push({
      key: 'trading-off',
      tone: 'warn',
      word: 'Trading off',
      detail:
        `${stop(sentence(bot.trade_block || 'the broker or the terminal will not let this account trade'))} ` +
        'Every order it sends will be refused until it is back on.',
    })
  }
  if (bot.mt5_link === false) {
    out.push({
      key: 'no-link',
      tone: 'warn',
      word: 'No MT5 link',
      detail:
        'it is running, but its MT5 terminal is not answering, so it receives no bars. It ' +
        'retries every 30s; if this persists, restart it.',
    })
  }
  if (reviewIssue?.tone === 'warn') out.push(reviewIssue)
  if (bot.day_locked) {
    out.push({
      key: 'locked',
      tone: 'warn',
      word: 'Locked for the day',
      detail: 'it takes no new trade until the next trading day.',
    })
  }
  return out
}

/**
 * The one status a row shows.
 *
 * `asked` is whether the trading box answered for this bot at all — an unanswered snapshot is not
 * a stopped bot. `onAccount` separates a bot benched ON PURPOSE (no account, stopped by design) from
 * one that stopped while it holds an account.
 */
export function botCondition(
  bot: BotStatus | undefined,
  opts: { asked: boolean; onAccount: boolean }
): Condition {
  if (!opts.asked || !bot) {
    return {
      state: 'unknown',
      tone: 'unknown',
      word: 'Unknown',
      wordTone: 'unknown',
      more: 0,
      moreTone: null,
      issues: [],
      trade: null,
      title: 'The trading box has not answered for this bot — its state is unknown, not stopped.',
    }
  }

  const running = bot.status === 'RUNNING'
  const issues = issuesOf(bot)
  const trade = running && bot.in_trade === true ? tradeView(bot.position) : null

  let base: { state: StateKey; tone: Tone; word: string; line: string }
  if (running) {
    const line =
      bot.uptime_seconds != null ? `Running for ${formatUptime(bot.uptime_seconds)}.` : 'Running.'
    base = trade
      ? { state: 'in-trade', tone: 'ok', word: trade.head, line }
      : { state: 'running', tone: 'ok', word: 'Running', line }
  } else if (!opts.onAccount) {
    base = {
      state: 'benched',
      tone: 'idle',
      word: 'Benched',
      line: 'On no account, so it trades nothing until it is given one.',
    }
  } else if (bot.status === 'ERROR') {
    base = { state: 'error', tone: 'bad', word: 'Error', line: 'Its process reported an error.' }
  } else {
    base = {
      state: 'stopped',
      tone: 'bad',
      word: 'Stopped',
      line: 'Stopped — it trades nothing until it is started.',
    }
  }

  // On a running bot the worst problem IS the headline; any other keeps its own word (see the note
  // up top).
  const lead = running && issues.length ? issues[0] : null
  const rest = lead ? issues.slice(1) : issues
  const tone = issues.reduce<Tone>((t, i) => (RANK[i.tone] > RANK[t] ? i.tone : t), base.tone)
  const lines = [base.line, ...issues.map((i) => `${i.word}: ${i.detail}`)]
  if (trade) lines.push(trade.title)

  return {
    state: lead ? lead.key : base.state,
    tone,
    word: lead ? lead.word : base.word,
    wordTone: lead ? lead.tone : base.tone,
    more: rest.length,
    moreTone: rest.some((i) => i.tone === 'bad') ? 'bad' : rest.length ? 'warn' : null,
    issues,
    trade,
    title: lines.join('\n\n'),
  }
}
