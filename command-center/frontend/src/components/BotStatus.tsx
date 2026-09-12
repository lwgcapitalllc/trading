import type { Condition, Tone, TradeView } from '@/lib/botCondition'

/**
 * How a bot's state is DRAWN, on the Bots page and the Overview alike — one dot, one word.
 *
 * The decision is `lib/botCondition.ts`; this only paints it, so the two pages cannot word one
 * fact two ways. See that file for why a row says one thing rather than carrying a tag per fact.
 *
 * ⚠ **No glow, no pill, no background.** Colour is the exception here: the dot is green for a
 * healthy running bot and is the only colour a healthy row carries besides its P&L.
 */

const DOT: Record<Tone, string> = {
  bad: 'bg-neg',
  warn: 'bg-warn',
  ok: 'bg-pos',
  idle: 'border border-text-tertiary/60',
  unknown: 'border border-text-tertiary',
}

const WORD: Record<Tone, string> = {
  bad: 'text-neg-text',
  warn: 'text-warn-text',
  ok: 'text-text-tertiary',
  idle: 'text-text-tertiary',
  unknown: 'text-text-tertiary',
}

type Size = 'row' | 'list'

export function StatusDot({ cond, size = 'row' }: { cond: Condition; size?: Size }) {
  const d = size === 'row' ? 'w-[7px] h-[7px]' : 'w-[6px] h-[6px]'
  return (
    <span
      data-testid="status-dot"
      data-tone={cond.tone}
      title={cond.title}
      className={`inline-block ${d} rounded-full shrink-0 ${DOT[cond.tone]}`}
    />
  )
}

function Trade({ trade }: { trade: TradeView }) {
  return (
    <span data-testid="trade-open" title={trade.title} className="truncate text-text-primary">
      {trade.head}
      {trade.r && (
        <>
          {' · '}
          {/* Only the R is coloured: it is the money, and the side is not. */}
          <span
            className={trade.r.sign > 0 ? 'text-pos-text' : trade.r.sign < 0 ? 'text-neg-text' : ''}
          >
            {trade.r.text}
          </span>
        </>
      )}
    </span>
  )
}

/**
 * The one word — or, for a bot in a trade, the trade itself. Every other problem is a `+N` beside
 * it, and the whole story is on hover.
 *
 * ⚠ **A bot holding a trade shows it whatever else is wrong.** A halted bot with an open position
 * is the case where that position matters most, so it follows the problem's word rather than
 * hiding behind it.
 */
export function StatusText({ cond, size = 'row' }: { cond: Condition; size?: Size }) {
  const text = size === 'row' ? 'text-[12px]' : 'text-[11px]'
  return (
    <span
      data-testid="bot-status"
      data-state={cond.state}
      data-tone={cond.tone}
      title={cond.title}
      className={`flex items-baseline gap-[6px] min-w-0 whitespace-nowrap cursor-default ${text}`}
    >
      {cond.state === 'in-trade' && cond.trade ? (
        <Trade trade={cond.trade} />
      ) : (
        <span
          className={`shrink-0 ${cond.wordTone === 'bad' || cond.wordTone === 'warn' ? 'font-medium' : ''} ${WORD[cond.wordTone]}`}
        >
          {cond.word}
        </span>
      )}
      {/* The count takes the colour of the worst thing it hides, so "+1" over a halt is red. */}
      {cond.more > 0 && (
        <span
          data-testid="status-more"
          data-tone={cond.moreTone ?? undefined}
          className={`shrink-0 text-[11px] font-medium ${cond.moreTone ? WORD[cond.moreTone] : 'text-text-tertiary'}`}
        >
          +{cond.more}
        </span>
      )}
      {cond.state !== 'in-trade' && cond.trade && (
        <>
          <span className="shrink-0 text-text-tertiary">·</span>
          <Trade trade={cond.trade} />
        </>
      )}
    </span>
  )
}
