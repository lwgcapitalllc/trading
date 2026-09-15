import type { Condition, Tone, TradeView } from '@/lib/botCondition'

/**
 * How a bot's state is DRAWN — on the Bots rows, both panels and the Overview alike: ONE pill in
 * the state's colour, a count of anything else, and the rest on hover.
 *
 * The decision is `lib/botCondition.ts`; this only paints it, so the pages cannot word one fact two
 * ways. See that file for why a row says one thing rather than carrying a tag per fact.
 *
 * 🔴 **A PILL, coloured, everywhere (2026-09-13).** Aaron: *"the status for running or stopped
 * should be color coded … whether that is a pill or a dot make it consistent. Same thing when I
 * open the draw, running isn't consistent in style."* Grey words for a healthy bot read as no status
 * at all, and the panel header and the account panel each drew the state their own way. Now one
 * pill: green running, amber worth a look, red stopped / halted / error, grey benched, dashed grey
 * unknown — the app's own status colours, in the shape of the Stopping / Starting pill that stands
 * in for the buttons while an action runs.
 * ⚠ **Still no dot beside the NAME** (2026-09-12) — the pill is the one element.
 * ⚠ **The pill carries the WORD's tone, not the row's worst**: "Benched" is never red for a problem
 * it does not name. The worst thing a row hides is the `+N` count's colour.
 */

/** A tone's text colour — for the `+N` count and the bot panel's list of problems. */
export const TONE_TEXT: Record<Tone, string> = {
  bad: 'text-neg-text',
  warn: 'text-warn-text',
  ok: 'text-text-tertiary',
  idle: 'text-text-tertiary',
  unknown: 'text-text-tertiary',
}

/** A tone's pill — border, tint and text. */
const PILL: Record<Tone, string> = {
  ok: 'border-pos/40 bg-pos-muted text-pos-text',
  warn: 'border-warn/40 bg-warn-muted text-warn-text',
  bad: 'border-neg/40 bg-neg-muted text-neg-text',
  idle: 'border-border-default bg-bg-surface-2 text-text-secondary',
  unknown: 'border-dashed border-border-default text-text-tertiary',
}

/** A tone's SOLID dot — for a space too tight for the pill (a compact rail row, say), where a
 *  wrapping pill+badge would change that row's height. Only `bad`/`warn` are ever meant to be
 *  drawn: an `ok`/`idle`/`unknown` dot would be the exact "green means nothing is wrong" noise
 *  the pill form already avoids by only colouring a real finding. Same solid-fill convention this
 *  app already uses for a kind's own dot (`pages/Bots/kind.tsx`'s `KIND_TINT[...].dot`). */
export const TONE_DOT: Record<Tone, string> = {
  ok: 'bg-pos',
  warn: 'bg-warn',
  bad: 'bg-neg',
  idle: 'bg-text-tertiary',
  unknown: 'bg-text-tertiary',
}

type Size = 'row' | 'list'

function Trade({ trade, inPill = false }: { trade: TradeView; inPill?: boolean }) {
  return (
    <span
      data-testid="trade-open"
      title={trade.title}
      className={`truncate ${inPill ? '' : 'text-text-primary'}`}
    >
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
 * The one pill — its word, or for a bot in a trade the trade itself. Every other problem is a `+N`
 * beside it, and the whole story is on hover.
 *
 * ⚠ **A bot holding a trade shows it whatever else is wrong.** A halted bot with an open position
 * is the case where that position matters most, so it follows the problem's pill rather than
 * hiding behind it.
 */
export function StatusText({ cond, size = 'row' }: { cond: Condition; size?: Size }) {
  const text = size === 'row' ? 'text-[11px]' : 'text-[10.5px]'
  return (
    <span
      data-testid="bot-status"
      data-state={cond.state}
      data-tone={cond.tone}
      title={cond.title}
      className="flex items-center gap-[6px] min-w-0 whitespace-nowrap cursor-default"
    >
      <span
        data-testid="status-pill"
        data-tone={cond.wordTone}
        className={`inline-flex items-center min-w-0 max-w-full px-[7px] py-[2px] rounded-pill border font-medium ${text} ${PILL[cond.wordTone]}`}
      >
        {cond.state === 'in-trade' && cond.trade ? (
          <Trade trade={cond.trade} inPill />
        ) : (
          <span className="truncate">{cond.word}</span>
        )}
      </span>
      {/* The count takes the colour of the worst thing it hides, so "+1" over a halt is red. */}
      {cond.more > 0 && (
        <span
          data-testid="status-more"
          data-tone={cond.moreTone ?? undefined}
          className={`shrink-0 text-[11px] font-medium ${cond.moreTone ? TONE_TEXT[cond.moreTone] : 'text-text-tertiary'}`}
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
