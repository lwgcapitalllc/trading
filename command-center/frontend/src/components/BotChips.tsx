import { AlertTriangle } from 'lucide-react'
import type { BotPosition } from '@/types'

/**
 * Two tags a bot's row carries about its TRADING (2026-09-12), drawn the same way on the Bots page
 * and the Overview: whether the bot holds a trade at the broker, and whether its order bridge has
 * halted. One file, so the two pages cannot word one fact two ways.
 *
 * ⚠ The page decides NOTHING here. Every figure is the bot's own heartbeat reading, passed through
 * by the backend only while the bot runs. Rules: `algos/CLAUDE.md` → *The heartbeat says what the
 * bot holds at the broker*.
 *
 * ⚠ Only the two tags are exported. The wording helpers stay private, because a file that exports
 * anything besides components loses fast refresh — and nothing outside needs them.
 */

type Size = 'row' | 'list'

const BASE =
  'inline-flex items-center gap-[3px] font-semibold rounded-pill uppercase tracking-[0.4px] cursor-default whitespace-nowrap'
const SIZE: Record<Size, string> = {
  row: 'text-[10px] px-[6px] py-[2px]',
  list: 'text-[9px] px-[5px] py-[1px]',
}

const price = (v: number) =>
  v.toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 5 })
const dollars = (v: number) =>
  `$${Math.abs(v).toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`
const signedDollars = (v: number) => `${v < 0 ? '−' : '+'}${dollars(v)}`
const signed = (v: number, digits: number) =>
  `${v > 0 ? '+' : v < 0 ? '−' : ''}${Math.abs(v).toFixed(digits)}`

/** "+1.2R", "−0.4R" or "0.0R", and its sign — or `null` when the R is unknown. One decimal: a
 *  row tag, not a ledger. The sign is read off the ROUNDED figure, so +0.04R reads 0.0R, uncoloured. */
function positionR(p?: BotPosition | null): { text: string; sign: -1 | 0 | 1 } | null {
  if (p?.r == null || !Number.isFinite(p.r)) return null
  const v = Math.round(p.r * 10) / 10
  return { text: `${signed(v, 1)}R`, sign: v > 0 ? 1 : v < 0 ? -1 : 0 }
}

/** The tag's words before the R: "long 0.40 lots". A reading the backend could not check still
 *  says the bot holds something, and never pretends to know the size. */
function positionHead(p?: BotPosition | null): string {
  if (!p) return 'in a trade'
  return `${p.side === 'mixed' ? 'both sides' : p.side} ${p.lots.toFixed(2)} lots`
}

function positionTitle(p?: BotPosition | null): string {
  const lines: string[] = []
  if (!p) {
    lines.push('The bot holds a position at the broker; its details could not be read.')
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

function haltedTitle(reason?: string | null): string {
  const lines = ['The bot has HALTED. It is still running but places no orders until restarted.']
  if (reason) lines.push(`${reason[0].toUpperCase()}${reason.slice(1)}`)
  lines.push('Anything open keeps its broker stop.')
  return lines.join('\n')
}

/** The order bridge has HALTED — the process runs and the heartbeat ticks, and the bot places
 *  nothing until it is restarted (a halt latches). 🔴 The row read RUNNING through every halt
 *  until 2026-09-12; the hourly review chip was the only sign, up to an hour late. ⚠ Beside the
 *  running dot, never instead of it: alive and halted are both true. ⚠ Drawn for `halted` only —
 *  `warming` also places nothing but clears itself, and `null` is could-not-ask. Red: it needs a
 *  person. */
export function HaltedChip({ reason, size = 'row' }: { reason?: string | null; size?: Size }) {
  return (
    <span
      data-testid="halted"
      title={haltedTitle(reason)}
      className={`${BASE} ${SIZE[size]} bg-neg-muted text-neg-text`}
    >
      <AlertTriangle size={size === 'row' ? 9 : 8} /> halted
    </span>
  )
}

/** What the bot holds AT THE BROKER — "LONG 0.40 LOTS · +1.2R". The bot reads the broker every
 *  10s and the page re-reads the fleet every 60s. ⚠ Drawn on `in_trade === true` only: `false` is
 *  flat and `null` is could-not-ask, and neither is a trade. ⚠ Only the R carries colour — colour
 *  on these pages is money, and a side is not. */
export function TradeOpenChip({
  position,
  size = 'row',
}: {
  position?: BotPosition | null
  size?: Size
}) {
  const r = positionR(position)
  return (
    <span
      data-testid="trade-open"
      title={positionTitle(position)}
      className={`${BASE} ${SIZE[size]} bg-bg-sunken text-text-primary`}
    >
      {positionHead(position)}
      {r && (
        <>
          {' · '}
          <span className={r.sign > 0 ? 'text-pos-text' : r.sign < 0 ? 'text-neg-text' : ''}>
            {r.text}
          </span>
        </>
      )}
    </span>
  )
}
