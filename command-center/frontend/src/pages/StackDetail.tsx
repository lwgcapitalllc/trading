import { useMemo, useState, useEffect, useCallback } from 'react'
import { useParams, useNavigate } from 'react-router-dom'
import { ArrowLeft, CheckCircle2, ChevronDown, Loader2, XCircle, Layers, Trash2, Square, Play } from 'lucide-react'
import StickyHeader from '@/components/StickyHeader'
import { useStack, useDeleteStack, useCancelStack, useStackChartSpec, useRunCandles, useStackContention } from '@/hooks/useLab'
import { ChartTabPanel, ChartModal } from '@/components/ChartTabPanel'
import { StackConfigModal } from '@/components/StackConfigModal'
import { XModeToggle } from '@/components/XModeToggle'
import { RegimeOverlayToggle, useRegimeOverlay } from '@/components/RegimeOverlayToggle'
import InfoTip from '@/components/InfoTip'
import { getXMode, setXModePref, regimeBandsFromTimeline, regimeBandsByIndex, type XMode } from '@/lib/chartAxis'
import {
  PerformancePanel, computeFallbacks, worstLosingStreakOf, EquityCurveChart, DrawdownChart, DailyPnlChart,
  DirectionBreakdown, PriceChartView, SeriesToggle, panelCardCls, CardHead, CardHero, PanelRows,
  usePerfCollapsed, PerfCollapseToggle, type FallbackMetrics, type PanelRow,
} from '@/pages/BacktestDetail'
import { C } from '@/themes/chart'
import type { StackStrategyLeg, BacktestDetail as RunDetail, EquityPoint, DailyPnlPoint, StackSharedReport, StackMode } from '@/types'

// ── Formatters ────────────────────────────────────────────────────────────────

// Local midnight, not UTC — a bare 'YYYY-MM-DD' otherwise renders a day early west of
// Greenwich. Same fix in BacktestDetail/SweepDetail/OptimizationDetail/StressTestDetail.
function fmtDate(iso: string) {
  return new Date(`${iso.slice(0, 10)}T00:00:00`).toLocaleDateString('en-US', { month: 'short', day: 'numeric', year: 'numeric' })
}
function fmtMoney(v: number, signed = true): string {
  const sign = v >= 0 ? (signed ? '+' : '') : '-'
  return `${sign}$${Math.abs(v).toLocaleString('en-US', { maximumFractionDigits: 0 })}`
}
function dateMsOf(s?: string): number { return s ? new Date(s).getTime() : 0 }

// Strategy-line palette. The PORTFOLIO line is `C.pos` (green) and a leg must be a colour nobody
// could mistake for it — or for the loss red.
//
// 🔴 This was `C.series.filter(c => c !== C.pos && c !== C.neg)` until 2026-08-10, which is a
// STRING comparison against a palette holding near-misses: `series[1]` is `#00ff7f` against
// `C.pos`'s `#00ff82` — three units apart in one channel, i.e. the same green to any eye — and
// `series[5]` is `#ff3b5c` against `C.neg`'s `#ff496b`. Both passed the filter, so the second leg
// on every two-strategy stack drew in the portfolio's own colour and the legend showed two green
// swatches. Reported off the screen; exact inequality cannot express "not confusable with".
//
// ⚠ Keep this an explicit list rather than a filter. A filter over a shared palette is a rule that
// silently re-breaks the day somebody adds a colour to `C.series`.
const LEG_COLORS = [
  '#00e5ff',  // cyan
  '#ffb300',  // amber
  '#a78bfa',  // violet
  '#4da6ff',  // blue
]

// ── Combined-portfolio payload ─────────────────────────────────────────────────
// A stack IS a portfolio: the union of its enabled legs' trades over one shared account. From that
// we synthesize a single backtest-shaped `run` + a portfolio equity curve, so StackDetail can reuse
// BacktestDetail's exact KpiGrid and chart components — pixel-identical KPIs and charts. Recomputes
// on every toggle (client-side, no re-backtest).

// The overlay-tagged equity point: a portfolio trade that ALSO carries each leg's running balance
// as a `leg_<id>` field, so the real EquityCurveChart can draw a line per strategy on the same axis.
// `_legOwner` names the overlay line this point's trade actually belongs to, so each strategy line
// dots only on its OWN trades (every point carries every leg's balance).
type ComboPoint = EquityPoint & { _legOwner?: string } & Partial<Record<`leg_${string}`, number>>

// ── Which BOOK the numbers on screen come from ────────────────────────────────
//
// 🔴 This distinction is the whole reason the leg toggles are trustworthy, and it did not exist
// until 2026-08-10. Aaron switched MPC SOS Fade off on a shared stack and read that MPC B-LEG had
// made $47,758,999, then ran that same strategy standalone over the same window and got $21,064.
// Both numbers were right. The B-LEG's trades in a SHARED book are sized off a balance A+ grew to
// ~$169M, so its last trade risks $16,925,791 where alone it risks $3,102 — 5,456x — for the
// identical +0.014R. **Same 99 trades, same entry and stop prices, same 17.8674R, 2,266x the
// dollars.** Composing a subset from shared trades answers "what did this leg contribute to an
// account the others built", and reads as "what this leg made". Those are different questions.
type Basis =
  | 'screen'      // every leg had its own full account, so any subset is honestly additive
  | 'shared'      // every leg on: the shared book, exactly as replayed
  | 'solo'        // one leg on: its SOLO CONTROL replay, i.e. genuinely "if the others never existed"
  | 'unmeasured'  // a subset nobody replayed — refuse rather than compose one

interface Combined {
  run: RunDetail
  equity: ComboPoint[]
  dailyPnl: DailyPnlPoint[]
  /** Trades each enabled leg contributed — the Verdict card's per-row value. */
  legTrades: Map<string, number>
  /** R each enabled leg contributed. The ONLY figure that is the same shared or solo. */
  legR: Map<string, number>
  balance: number
  fallback: FallbackMetrics
  hasResults: boolean
  hasDirection: boolean
  activeCount: number
  completeCount: number
  basis: Basis
}

function composeCombined(legs: StackStrategyLeg[], enabled: Set<string>, mode: StackMode): Combined {
  const complete = legs.filter(l => l.status === 'complete')
  const active = complete.filter(l => enabled.has(l.strategy_id))

  // A screen replayed each leg on its own full account, so a subset of it is a real experiment —
  // nothing could ever have blocked anything, and removing a leg removes only its own trades. A
  // SHARED stack has exactly two books on disk: the one where every leg ran, and one solo control
  // per leg. Anything between them was never replayed.
  const allOn = active.length === complete.length
  const soloOf = (l: StackStrategyLeg) => (l.solo_equity_curve?.length ? l : null)
  const basis: Basis =
    mode !== 'shared' ? 'screen'
      : allOn ? 'shared'
        : active.length === 1 && soloOf(active[0]) ? 'solo'
          : 'unmeasured'

  // On the solo basis the leg's own control book REPLACES its shared one — same trades, sized off
  // its own account instead of the portfolio's.
  const books = active.map(l => (
    basis === 'solo'
      ? { leg: l, equity_curve: l.solo_equity_curve ?? [], daily_pnl: l.solo_daily_pnl ?? [] }
      : { leg: l, equity_curve: l.equity_curve, daily_pnl: l.daily_pnl }
  ))

  // Portfolio daily P&L = per-date sum across enabled legs.
  const dailyMap = new Map<string, number>()
  for (const b of books) for (const d of b.daily_pnl) dailyMap.set(d.date, (dailyMap.get(d.date) ?? 0) + d.pnl)
  const dailyPnl: DailyPnlPoint[] = Array.from(dailyMap.entries())
    .sort((a, b) => (a[0] < b[0] ? -1 : 1))
    .map(([date, pnl]) => ({ date, pnl }))

  // ONE shared account. Every leg was backtested against the SAME opening balance, so the portfolio
  // starts THERE — not at the sum of the legs. Summing showed $20k for two legs of a $10k account and
  // halved every balance-relative KPI. (A stack configures all legs together so their starts agree;
  // max is the safe pick if a reused run ever carried a different one.)
  const legStart = new Map<string, number>()
  for (const b of books) {
    const e0 = b.equity_curve[0]
    legStart.set(b.leg.strategy_id, e0 ? (e0.equity ?? 0) - (e0.profit ?? 0) : 10_000)
  }
  const balance = legStart.size ? Math.max(...legStart.values()) : 10_000

  // Union of every leg's trades in time order → one portfolio equity curve. Each point also records
  // EVERY leg's running balance (the overlay lines), so a strategy's line rides the same x-axis.
  const tagged = books.flatMap(b => b.equity_curve.filter(p => p.direction).map(p => ({ p, legId: b.leg.strategy_id })))
  tagged.sort((a, b) => (a.p.entry_ms ?? dateMsOf(a.p.date)) - (b.p.entry_ms ?? dateMsOf(b.p.date)))
  // Every strategy line starts on the SAME point as the portfolio line (the combined opening
  // balance) and then rides its own cumulative P&L — "what this leg alone did to the account".
  // Starting each leg at its own 10k slice would draw the lines below the portfolio's start line.
  const legBal = new Map<string, number>(active.map(l => [l.strategy_id, balance]))
  let bal = balance
  const equity: ComboPoint[] = tagged.map(({ p, legId }, i) => {
    bal += p.profit ?? 0
    legBal.set(legId, legBal.get(legId)! + (p.profit ?? 0))
    const pt: ComboPoint = {
      index: i + 1, equity: Number(bal.toFixed(2)), date: p.date, entry_ms: p.entry_ms,
      direction: p.direction, profit: p.profit, favorable: p.favorable, adverse: p.adverse, exit_name: p.exit_name,
      _legOwner: `leg_${legId}`,
    }
    for (const leg of active) pt[`leg_${leg.strategy_id}`] = Number(legBal.get(leg.strategy_id)!.toFixed(2))
    return pt
  })

  // ⚠ Both maps cover every COMPLETE leg, not only the switched-on ones. A leg's trade count and
  // its R are facts about that leg, so a row must not fall back to a different unit the moment the
  // reader switches it off — that made one row read `+17.87R` and the other `160` on the same card.
  const legTrades = new Map(complete.map(l => [l.strategy_id, l.equity_curve.filter(p => p.direction).length]))

  // R per leg — the Verdict card's row value. It is the ONE figure that does not move between the
  // shared book and the solo control (R is normalised to each trade's own risk, so re-sizing a
  // position cannot touch it), which is exactly why the row leads with it rather than with dollars.
  // `shared_summary.json` stores the same number per leg and the two agree to 4dp; deriving it here
  // means the row still has an answer on a screen, which has no summary at all.
  const legR = new Map(complete.map(l => [
    l.strategy_id,
    l.equity_curve.reduce((a, p) => a + (p.direction ? (p.r ?? 0) : 0), 0),
  ]))

  // KPIs from the union of trades.
  const trades = tagged.map(t => t.p)
  const profits = trades.map(t => t.profit ?? 0)
  const wins = profits.filter(p => p > 0)
  const losses = profits.filter(p => p < 0)
  const grossWin = wins.reduce((a, b) => a + b, 0)
  const grossLoss = Math.abs(losses.reduce((a, b) => a + b, 0))
  const net = profits.reduce((a, b) => a + b, 0)
  const winRate = trades.length ? wins.length / trades.length : null
  // No losing trade = no denominator, not unknown: report ∞ so the card matches a single backtest.
  const pf = grossLoss > 0 ? grossWin / grossLoss : (grossWin > 0 ? Infinity : null)
  const avgWin = wins.length ? grossWin / wins.length : null
  const avgLoss = losses.length ? losses.reduce((a, b) => a + b, 0) / losses.length : null

  // Portfolio dollar drawdown (peak-to-trough of the combined equity).
  let peak = -Infinity, maxDd = 0
  for (const e of equity) { peak = Math.max(peak, e.equity); maxDd = Math.max(maxDd, peak - e.equity) }

  // Portfolio avg trade duration = each leg's own average weighted by how many trades it contributed
  // (legs that never reported a duration sit out of both sums rather than dragging it to zero).
  // Weighted by the trades in the book actually on screen, NOT by `legTrades` — that map covers
  // every complete leg so the rows stay in one unit, and weighting an average by legs that are
  // switched off would describe a portfolio nobody is looking at.
  const durLegs = books.filter(b => b.leg.avg_trade_duration_min != null)
  const durCount = (b: typeof books[number]) => b.equity_curve.filter(p => p.direction).length
  const durTrades = durLegs.reduce((a, b) => a + durCount(b), 0)
  const avgDuration = durTrades > 0
    ? durLegs.reduce((a, b) => a + b.leg.avg_trade_duration_min! * durCount(b), 0) / durTrades
    : null

  // Sharpe comes from computeFallbacks — this was a third private copy of the formula, and like
  // the one in computeFallbacks it scored only the days that traded, so a stack printed 13.06.
  // Flat weekdays are real observations; the shared helper zero-fills them the way the backend does.
  const fallback = computeFallbacks(dailyPnl)

  // Synthetic backtest-shaped run carrying exactly the fields KpiGrid reads.
  const run = {
    net_pnl: net,
    trade_count: trades.length,
    win_rate: winRate,
    profit_factor: pf,
    avg_win: avgWin,
    avg_loss: avgLoss,
    max_drawdown: maxDd || null,
    sharpe: fallback.sharpe,
    platform_sharpe: null,
    sharpe_low_sample: dailyPnl.length < 10 ? 1 : 0,
    worst_day_pnl: fallback.worstDay,
    // Counted off the portfolio's TRADES, which is the unit the row is labelled in. `profits` is
    // in entry order (tagged is sorted above), which a streak requires.
    worst_losing_streak: worstLosingStreakOf(profits),
    avg_trade_duration_min: avgDuration,
    profit_concentration_pct: null,
    daily_pnl: dailyPnl,
  } as unknown as RunDetail

  return {
    run, equity, dailyPnl, legTrades, legR, balance, fallback,
    // `unmeasured` has no book, so it has no results — the page renders the refusal instead of a
    // composed answer. Everything above still runs (it is cheap and the leg rows read `legR`), it
    // simply must not be shown as a portfolio.
    hasResults: basis !== 'unmeasured' && dailyPnl.length > 0,
    hasDirection: trades.some(t => t.direction),
    activeCount: active.length,
    completeCount: complete.length,
    basis,
  }
}

// Equity-chart legend — the combined curve + a swatch per enabled strategy line.
function StackEquityLegend({ activeLegs, colorFor }: { activeLegs: StackStrategyLeg[]; colorFor: (id: string) => string }) {
  return (
    <div className="flex items-center gap-4 mb-1 flex-wrap">
      <span className="flex items-center gap-1.5 text-[11px] text-text-tertiary">
        <span className="w-4 h-[2.5px] rounded" style={{ background: C.pos }} /> Portfolio
      </span>
      {activeLegs.map(leg => (
        <span key={leg.strategy_id} className="flex items-center gap-1.5 text-[11px] text-text-tertiary">
          <span className="w-4 h-[2px] rounded" style={{ background: colorFor(leg.strategy_id) }} />
          {leg.strategy_name}
        </span>
      ))}
    </div>
  )
}

// ── Which book is on screen ───────────────────────────────────────────────────
//
// The chip is beside the Performance heading rather than buried in a tooltip, because it changes
// what every number under it MEANS. `screen` and `shared` are the run as it happened and say so
// quietly; `solo` is the one that has to announce itself, since the reader got there by switching
// a strategy off and the numbers jump by orders of magnitude when they do.
function BasisChip({ basis }: { basis: Basis }) {
  if (basis === 'screen' || basis === 'shared') {
    return (
      <span className="text-[10px] text-text-tertiary flex items-center gap-1" data-testid="basis-chip">
        {basis === 'shared' ? 'the shared account, as it ran' : 'every strategy on its own account'}
        <InfoTip text={basis === 'shared'
          ? 'Every strategy is on, so these are the numbers the shared replay actually produced — one balance, one risk budget they competed for.'
          : 'This is a screen: each strategy was replayed on its own full account and the results added up. Nothing could block anything, so any combination of them is a real reading.'} />
      </span>
    )
  }
  if (basis === 'solo') {
    return (
      <span
        data-testid="basis-chip"
        className="text-[10px] px-2 py-[3px] rounded-pill bg-accent/10 text-accent border border-accent/25 flex items-center gap-1"
      >
        on its own account
        <InfoTip text="One strategy is left on, so the page is showing its SOLO CONTROL — the replay where it traded a full account by itself, exactly as if the others never existed. That is a different book from its share of the stack: the trades and the R are identical, the dollars are not, because inside the stack it sizes off a balance every strategy grew." />
      </span>
    )
  }
  return (
    <span
      data-testid="basis-chip"
      className="text-[10px] px-2 py-[3px] rounded-pill bg-warn-muted text-warn-text flex items-center gap-1"
    >
      never replayed
      <InfoTip text="This combination of strategies was never run on a shared account, so there are no numbers for it. Only two books exist: every strategy together, and each one alone." />
    </span>
  )
}

// The stand-in for the three KPI cards when the reader has picked a combination nobody replayed.
// It states what exists rather than what is missing, and offers the way back.
function UnmeasuredCard({ onAllOn }: { onAllOn: () => void }) {
  return (
    <div className={`${panelCardCls(false, false, 'flex-1')}`} data-testid="unmeasured-card">
      <CardHead title="No numbers for this combination" />
      <div className="text-[12px] text-text-secondary leading-[1.5] mt-1">
        A shared account was replayed <strong className="text-text-primary">twice</strong>: once with every
        strategy competing for one balance, and once per strategy running alone. Any other subset is a
        different experiment that nobody has run.
      </div>
      <div className="text-[11px] text-text-tertiary leading-[1.45] mt-2">
        Composing one from the stored trades would be misleading rather than approximate — inside the shared
        book each strategy sizes off a balance <em>all</em> of them grew, so its dollars there are not what it
        would have made without the others. Leave one strategy on to see its solo replay, or switch them all
        back on for the portfolio.
      </div>
      <button
        type="button"
        onClick={onAllOn}
        className="mt-3 self-start text-[11px] px-2.5 py-[5px] rounded border border-accent/30 text-accent hover:bg-accent/10 transition-colors"
      >
        Switch every strategy back on
      </button>
    </div>
  )
}

// ── The Verdict card ──────────────────────────────────────────────────────────
//
// A stack sits in the same four-column Performance row a single backtest does — Verdict, Made,
// Risked, Trusted — and this is the first card. A backtest grades itself against a firm's rules
// there; a stack has no ruleset to grade against, so the card answers the question that IS the
// stack's own: WHAT IS THIS MADE OF, and which of those parts are in the numbers to the right.
//
// The legs are ROWS, and each row is the toggle. That is the whole point of putting them here:
// the chips used to live in a section of their own further down the page, so the control that
// decides what every KPI counts was nowhere near the KPIs, and nothing on the panel said which
// strategies were in it. A row is 24px whatever it says (see PanelRows), so the card stays in
// line with the three beside it however long a strategy name is.
function StackVerdictCard({ legs, enabled, colorFor, onToggle, counts, legR, total, spanDays, mode }: {
  legs: StackStrategyLeg[]
  enabled: Set<string>
  colorFor: (id: string) => string
  onToggle: (id: string) => void
  counts: Map<string, number>
  legR: Map<string, number>
  total: number
  spanDays: number | null
  mode: StackMode
}) {
  const activeCount = legs.filter(l => enabled.has(l.strategy_id) && l.status === 'complete').length

  // Same cadence line a backtest's verdict card carries, off the stack's own window.
  const months = spanDays != null && spanDays > 0 ? spanDays / 30.44 : null
  const years = months != null ? months / 12 : null
  const perMonth = months != null && months >= 1 ? total / months : null
  const cadence = [
    years != null && years >= 1 ? `${years.toFixed(1)} yrs` : months != null ? `${months.toFixed(0)} mo` : null,
    perMonth != null ? `≈${perMonth < 1 ? perMonth.toFixed(1) : perMonth.toFixed(0)}/month` : null,
  ].filter(Boolean).join(' · ')

  const rows: PanelRow[] = legs.map(leg => {
    const on = enabled.has(leg.strategy_id)
    const done = leg.status === 'complete'
    const failed = leg.status.startsWith('failed')
    const isLastOn = on && done && activeCount === 1
    // A leg that cannot be toggled is still LISTED — "not finished" and "not in this stack" are
    // different answers, and hiding the first one makes a stack look smaller than it is.
    const clickable = done && !isLastOn
    const r = legR.get(leg.strategy_id)
    const trades = counts.get(leg.strategy_id) ?? leg.trade_count ?? 0

    // 🔴 What this leg CONTRIBUTED, and the unit is the fix. The row used to say
    // "It made <net_pnl> on its own account" — and on a SHARED stack `net_pnl` is the leg's dollars
    // inside the portfolio, sized off a balance every leg compounded onto, so that sentence was
    // false by 2,266x on the measured stack. R is the same number either way.
    const solo = leg.solo_equity_curve?.length ? leg.solo_equity_curve : null
    const soloNet = solo ? (solo[solo.length - 1].equity ?? 0) - ((solo[0].equity ?? 0) - (solo[0].profit ?? 0)) : null
    const made = mode === 'shared'
      ? (soloNet != null
          ? ` Alone on its own account it makes ${fmtMoney(soloNet)}; inside this stack the same trades are worth ${fmtMoney(leg.net_pnl ?? 0)}, because here it sizes off a balance every strategy grew.`
          : (leg.net_pnl != null ? ` It is worth ${fmtMoney(leg.net_pnl)} inside this shared account — not what it would make alone, because here it sizes off a balance every strategy grew.` : ''))
      : (leg.net_pnl != null ? ` It made ${fmtMoney(leg.net_pnl)} on its own full account.` : '')

    return {
      key: leg.strategy_id,
      label: leg.strategy_name,
      lead: (
        <span
          className="w-2.5 h-2.5 rounded-[3px] shrink-0 mr-1.5"
          style={{
            backgroundColor: on && done ? colorFor(leg.strategy_id) : 'transparent',
            border: on && done ? 'none' : `1.5px solid ${C.axisTick}`,
          }}
        />
      ),
      value: done
        ? (r != null && r !== 0 ? `${r > 0 ? '+' : ''}${r.toFixed(2)}R` : trades)
        : failed
          ? <XCircle size={12} className="inline text-neg-text" />
          : <Loader2 size={12} className="inline animate-spin text-accent" />,
      cls: failed ? 'text-neg-text' : undefined,
      muted: !on || !done,
      onClick: clickable ? () => onToggle(leg.strategy_id) : undefined,
      tip: !done
        ? (failed
            ? `This leg failed, so none of its trades are in the numbers beside this card. ${leg.error_message ?? 'No error was recorded.'}`
            : 'This leg is still replaying. It joins the portfolio numbers the moment it finishes.')
        : `${trades} trades${r != null ? `, ${r > 0 ? '+' : ''}${r.toFixed(2)}R` : ''}. R is its result over the risk it was sized to, so it is the same number here as it is alone — the dollars are not.${made} ${
            isLastOn
              ? 'At least one strategy has to stay on — a portfolio of none has nothing to measure.'
              : on
                ? 'Click to take it out and watch every number recompute.'
                : 'Excluded — none of its trades are in the numbers beside this card. Click to put it back.'
          }`,
    }
  })

  return (
    /* ⚠ `collapsed: false`, always. The other three cards fold their supporting ROWS away; this
       card's rows are a CONTROL, and the panel's collapse means "hero numbers only", not "hide the
       switch that decides what the heroes count". Hiding it would put the toggles a click behind a
       preference the reader set on a different page. It costs ~24px per leg. */
    <div data-testid="stack-verdict-card" className={panelCardCls(false, false, 'border-t-2 border-t-accent/45')}>
      <CardHead
        title="Verdict"
        aside={<span className="text-[10px] text-text-tertiary shrink-0">{activeCount} of {legs.length} on</span>}
      />
      <CardHero
        value={total}
        unit="trades"
        cls="text-accent"
        tip="Every trade the switched-on strategies took, and the sample every number beside this card rests on. Toggle a strategy in the rows below and this — and Made, Risked and Trusted — recompute over whatever is left on."
      />
      <div className="text-[11px] text-text-tertiary leading-[1.35] mt-2 truncate">
        {legs.length}-strategy portfolio
      </div>
      {cadence && <div className="font-mono text-[10.5px] text-text-tertiary">{cadence}</div>}
      {rows.length > 0 && <PanelRows rows={rows} />}
    </div>
  )
}

// ── Page ──────────────────────────────────────────────────────────────────────

const CHART_TABS = [['equity', 'Equity'], ['price', 'Price'], ['breakdown', 'Breakdown']] as const
const CHART_SUBS: Record<string, string> = {
  equity: 'Steadily rising = good. Big peak then long decline = giving back gains.',
  price: 'Candles with each enabled strategy\'s trades layered in its colour. Structure, fib + measurement tools included.',
  breakdown: 'Drawdown from peak, daily P&L, and long vs short — for the combined portfolio.',
}

// ── The shared account ────────────────────────────────────────────────────────
//
// A screen cannot answer any of this: it runs each leg on its own full account, so nothing was
// ever refused and there is no budget to report on. This is the ONLY thing on the page a single
// backtest has no counterpart for, which is why it survives as its own section and why it is one
// card rather than the three-cards-plus-table it started as.
//
// 🔴 It was rebuilt on 2026-08-10 because it read as jargon: `One account` / `The screen promised`
// / `Peak open risk` were three big figures with nothing saying what any of them was FOR, over a
// seven-column table that was five columns of em-dashes on every run measured so far. Every fact
// is still here; each one now arrives with the sentence that makes it mean something, and the
// per-strategy table — which only says anything when the budget actually refused something — is
// behind a disclosure instead of being the largest thing on the page.
//
// ⚠ The two facts that must never be dropped: the peak open risk has to be stated WITH the cap
// (10% is either the ceiling or a third of it, and the number alone cannot say which), and an
// empty contention log has to be stated in WORDS as a measurement.
function SharedAccountPanel({ report, colorFor, nameFor }: {
  report: StackSharedReport
  colorFor: (id: string) => string
  nameFor: (id: string) => string
}) {
  const [showLegs, setShowLegs] = useState(false)
  // ⚠ The test seam is on ALL THREE branches, not only the finished one. A panel that is still
  // replaying and a panel that failed are both this panel — putting the id on the happy path only
  // means a check for "it says what it is doing while running" can never find it, and would pass
  // or fail for the wrong reason.
  if (!report.available) {
    const p = report.progress
    if (p && p.phase === 'failed') {
      return (
        <div data-testid="shared-account-panel"
             className="rounded-lg border border-neg-text/25 bg-neg-muted/20 px-4 py-3">
          <div className="text-[13px] font-semibold text-neg-text mb-1">The shared replay failed</div>
          <div className="text-[12px] text-text-secondary font-mono break-words">{p.message}</div>
        </div>
      )
    }
    return (
      <div data-testid="shared-account-panel"
           className="flex items-center gap-2 rounded-lg border border-accent/20 bg-accent/5 px-4 py-3 text-[13px] text-accent">
        <Loader2 size={14} className="animate-spin" />
        {p ? `${p.message} · ${p.pct}%` : 'Replaying the strategies on one account…'}
      </div>
    )
  }

  // The screen is the sum of the SOLO controls — each leg on its own full account, which is
  // exactly what a screen-mode stack would have produced. So this is a like-for-like comparison
  // against a run that really happened, not against an estimate.
  const opening = report.opening_balance ?? 0
  const screenClosing = report.legs.reduce((a, l) => a + (l.solo_closing_balance - opening), opening)
  const sharedClosing = report.closing_balance ?? 0
  const delta = sharedClosing - screenClosing
  const anyContention = (report.contention_events ?? 0) > 0
  const capPct = report.risk_cap_pct ?? 0
  const peakPct = report.peak_open_risk_pct ?? 0
  const fill = capPct > 0 ? Math.min(100, (peakPct / capPct) * 100) : 0

  const seamFailed = !!report.neutral?.checkable && report.neutral?.ok === false

  return (
    <div data-testid="shared-account-panel"
         className="rounded-xl border border-border-default bg-bg-surface px-4 py-3.5 space-y-3">

      {/* ── How full the budget ever got, and whether it ever had to say no ──
          ⚠ Every FACT here was already on screen before 2026-08-10; what changed is that the prose
          explaining each one moved onto its ⓘ. Aaron: "does this section need to be so verbose?
          Like I'm reading a storybook." The rules those paragraphs stated are load-bearing and are
          NOT deleted — an empty contention log still has to read as a measurement, and the
          together-vs-apart gap still has to name compounding — they are one hover away instead of
          four lines of body text nobody re-reads. */}
      <div className="flex flex-wrap items-baseline justify-between gap-x-4 gap-y-1">
        <span className="flex items-baseline text-[12.5px] text-text-secondary">
          <span className="font-mono tabular-nums text-[15px] font-semibold text-text-primary">{peakPct.toFixed(2)}%</span>
          <span className="ml-1.5">peak open risk</span>
          <InfoTip text={`The most open risk the account ever carried at once, as a share of its balance, measured to each trade's CURRENT stop. Against a ${capPct.toFixed(2)}% cap, with ${report.peak_concurrent_legs} of ${report.leg_count} strategies holding at the peak.`} />
        </span>
        <span data-testid="contention-chip" className={`inline-flex items-center rounded-full pl-2.5 pr-1.5 py-[3px] text-[10px] font-bold uppercase tracking-[0.4px] shrink-0 ${
          anyContention ? 'bg-warn-muted text-warn-text' : 'bg-bg-sunken text-text-secondary'
        }`}>
          {anyContention ? `${report.contention_events} refused` : 'Nothing refused'}
          <InfoTip text={anyContention
            ? `The budget was full ${report.contention_events} times when a strategy asked, so its entry was shrunk to fit or refused outright. Every difference between this and the same strategies run apart traces to one of these — the per-strategy rows below say which strategy wore them.`
            : 'Nothing was ever refused. That is a measurement, not a missing one — open risk is measured to each trade’s current stop, so a stop moved to breakeven releases its room before the other strategy asks. Read it as “the budget would rarely have had anything to arbitrate”, never as “a cap is unnecessary”.'} />
        </span>
      </div>
      <div className="h-[5px] rounded-full bg-bg-sunken overflow-hidden">
        <div className="h-full rounded-full bg-accent" style={{ width: `${fill}%` }} />
      </div>
      <div className="text-[11px] text-text-tertiary">
        of a {capPct.toFixed(2)}% cap · {report.peak_concurrent_legs} of {report.leg_count} holding at once
      </div>

      {/* The one thing this panel can CHECK rather than report. R is normalised to the trade's own
          risk, so with a full budget a leg must post the same R shared as solo — a difference there
          is the shared account moving a decision it must not touch, which is a defect in the seam
          and not a portfolio effect. A FAILURE is never folded into the disclosure below. */}
      {seamFailed && (
        <div className="text-[11px] px-3 py-2 rounded-lg border border-neg-text/25 bg-neg-muted/20 text-neg-text">
          <strong>Seam check failed — </strong>{report.neutral!.reason}
        </div>
      )}

      {/* ── Per-strategy detail ──
          Behind a disclosure because on every run measured so far its Shrunk / Blocked / Risk
          refused columns are entirely em-dashes — it is the answer to "what did the budget do to
          each strategy" and the answer is usually "nothing". It OPENS ITSELF when there is
          contention, so the one state it exists for is never a click away. */}
      <div className="border-t border-border-subtle pt-2">
        <div className="flex flex-wrap items-center justify-between gap-x-4 gap-y-1">
          <button
            onClick={() => setShowLegs(v => !v)}
            className="flex items-center gap-1.5 text-[11px] font-medium text-text-tertiary hover:text-text-secondary transition-colors"
          >
            <ChevronDown size={12} className={`transition-transform ${showLegs || anyContention ? '' : '-rotate-90'}`} />
            Per-strategy detail
          </button>
          {/* What sharing one balance changed, as three figures on one line with the reasoning on
              the ⓘ. ⚠ The tooltip's job is to stop the gap being read as risk: it is mostly
              COMPOUNDING, and `docs/SHARED_RISK_STACK.md` predicted the opposite sign from exactly
              that misreading before the first real run disproved it. */}
          <span data-testid="together-apart" className="flex items-baseline text-[11px] text-text-tertiary">
            together
            <span className="ml-1 font-mono tabular-nums text-text-primary">{fmtMoney(sharedClosing, false)}</span>
            <span className="mx-1.5">·</span>
            apart
            <span className="ml-1 font-mono tabular-nums text-text-secondary">{fmtMoney(screenClosing, false)}</span>
            <span className={`ml-1.5 font-mono tabular-nums ${delta >= 0 ? 'text-pos-text' : 'text-neg-text'}`}>{fmtMoney(delta)}</span>
            <InfoTip text={`One balance took ${fmtMoney(opening, false)} to ${fmtMoney(sharedClosing, false)}. Run apart on their own full accounts these same strategies closed ${fmtMoney(screenClosing, false)} between them. ⚠ That gap is mostly COMPOUNDING, not risk — on one account the second strategy sizes off a balance the first has already grown — so judge the sharing on the R columns below, never on these dollars.`} />
          </span>
        </div>
        {(showLegs || anyContention) && (
          <div className="mt-2 overflow-x-auto">
            <table className="w-full text-[12px]">
              <thead className="text-text-tertiary">
                <tr className="text-left">
                  <th className="px-2 py-1.5 font-medium">Strategy</th>
                  <th className="px-2 py-1.5 font-medium text-right">Shared R</th>
                  <th className="px-2 py-1.5 font-medium text-right">Alone R</th>
                  <th className="px-2 py-1.5 font-medium text-right">Trades</th>
                  <th className="px-2 py-1.5 font-medium text-right">Shrunk</th>
                  <th className="px-2 py-1.5 font-medium text-right">Blocked</th>
                  <th className="px-2 py-1.5 font-medium text-right">Risk refused</th>
                </tr>
              </thead>
              <tbody>
                {report.legs.map(l => (
                  <tr key={l.strategy_id} className="border-t border-border-subtle">
                    <td className="px-2 py-1.5">
                      <span className="inline-flex items-center gap-1.5">
                        <span className="w-2 h-2 rounded-full" style={{ background: colorFor(l.strategy_id) }} />
                        {nameFor(l.strategy_id)}
                      </span>
                    </td>
                    <td className="px-2 py-1.5 text-right font-mono tabular-nums">{l.shared_r.toFixed(2)}</td>
                    <td className="px-2 py-1.5 text-right font-mono tabular-nums text-text-secondary">{l.solo_r.toFixed(2)}</td>
                    <td className="px-2 py-1.5 text-right font-mono tabular-nums">
                      {l.shared_trades}
                      {l.shared_trades !== l.solo_trades && (
                        <span className="text-text-tertiary"> / {l.solo_trades} alone</span>
                      )}
                    </td>
                    <td className="px-2 py-1.5 text-right font-mono tabular-nums">{l.shrunk || '—'}</td>
                    <td className="px-2 py-1.5 text-right font-mono tabular-nums">{l.blocked || '—'}</td>
                    <td className="px-2 py-1.5 text-right font-mono tabular-nums">
                      {l.risk_refused ? fmtMoney(l.risk_refused, false) : '—'}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
            {report.neutral && !seamFailed && (
              <div className="mt-2 text-[11px] text-text-tertiary">{report.neutral.reason}</div>
            )}
          </div>
        )}
      </div>
    </div>
  )
}

export function StackDetail() {
  const { stackId } = useParams<{ stackId: string }>()
  const navigate = useNavigate()
  const { data: stack, isLoading } = useStack(stackId ?? null)
  const mode: StackMode = stack?.mode ?? 'screen'
  const isShared = mode === 'shared'
  // Gated on the mode: a screen has no account to contend over, so polling one would be asking a
  // question that can never be answered.
  const { data: shared } = useStackContention(stackId ?? null, isShared)
  const deleteStack = useDeleteStack()
  const cancelStack = useCancelStack()
  const [confirmDelete, setConfirmDelete] = useState(false)
  const [showRerun, setShowRerun] = useState(false)
  // ONE preference, shared with a single backtest's Performance panel — the same control on the
  // same panel must not remember two answers depending on which page you last pressed it on.
  const [perfCollapsed, togglePerfCollapsed] = usePerfCollapsed()

  const isRunning = stack?.status === 'running'
  const legs = useMemo(() => stack?.strategies ?? [], [stack])
  const stackTitle = legs.map(l => l.strategy_name).join(' + ')

  // Enabled set — every completed leg starts on. Rebuilds when the completed set changes.
  const completeIds = useMemo(
    () => legs.filter(l => l.status === 'complete').map(l => l.strategy_id).join(','),
    [legs],
  )
  const [enabled, setEnabled] = useState<Set<string>>(new Set())
  useEffect(() => { setEnabled(new Set(completeIds ? completeIds.split(',') : [])) }, [completeIds])

  const colorFor = useMemo(() => {
    const idx = new Map(legs.map((l, i) => [l.strategy_id, i]))
    return (id: string) => LEG_COLORS[(idx.get(id) ?? 0) % LEG_COLORS.length]
  }, [legs])

  const combined = useMemo(() => composeCombined(legs, enabled, mode), [legs, enabled, mode])
  const hasResults = combined.hasResults

  const toggle = (id: string) => setEnabled(prev => {
    const next = new Set(prev)
    if (next.has(id)) { if (next.size > 1) next.delete(id) } else next.add(id)
    return next
  })

  const activeLegs = legs.filter(l => enabled.has(l.strategy_id) && l.status === 'complete')

  // Calendar span of the stack's window, for the Verdict card's trades-per-month cadence — the
  // same reading a single backtest prints there.
  const spanDays = useMemo(() => {
    if (!stack) return null
    const ms = dateMsOf(stack.end_date) - dateMsOf(stack.start_date)
    return ms > 0 ? ms / 86_400_000 : null
  }, [stack])

  // Built once and rendered by BOTH branches of the Performance block — the leg toggles live in
  // this card, so a selection with no book to compute KPIs from still has to show it, or the
  // reader lands in a state they cannot click their way out of.
  const verdictCard = (
    <StackVerdictCard
      legs={legs}
      enabled={enabled}
      colorFor={colorFor}
      onToggle={toggle}
      counts={combined.legTrades}
      legR={combined.legR}
      total={combined.run.trade_count ?? 0}
      spanDays={spanDays}
      mode={mode}
    />
  )

  // ── Chart state — same toggles as a single backtest ──
  const [chartTab, setChartTab] = useState<string>('equity')
  const [fullscreen, setFullscreen] = useState<string | null>(null)
  const [histOn, setHistOn] = useState(false)
  const [rudOn, setRudOn] = useState(false)
  const [overlayOn, setOverlayOn] = useRegimeOverlay()
  const [xMode, setXMode] = useState<XMode>(getXMode)
  const toggleXMode = useCallback((v: XMode) => { setXMode(v); setXModePref(v) }, [])

  // Per-strategy overlay lines on the equity chart (fields tagged onto each point by composeCombined).
  const overlayLines = useMemo(
    () => activeLegs.map(l => ({ id: `leg_${l.strategy_id}`, color: colorFor(l.strategy_id), name: l.strategy_name })),
    [activeLegs, colorFor],
  )
  const hasExcursion = combined.equity.some(d => d.favorable != null || d.adverse != null)

  // Regime bands from the stack's full-calendar timeline (a market property, same as a backtest).
  const hasRegimes = (stack?.regime_timeline?.length ?? 0) > 0
  const regimeBands = useMemo(() => {
    if (!overlayOn || !stack?.regime_timeline?.length) return []
    return xMode === 'trade'
      ? regimeBandsByIndex(combined.equity, new Map(stack.regime_timeline.map(d => [d.date, d.regime])))
      : regimeBandsFromTimeline(stack.regime_timeline)
  }, [overlayOn, xMode, stack?.regime_timeline, combined.equity])

  // Merged price-chart spec — loads once results exist (candles come from the base leg's cached spec).
  const { data: rawSpec, isLoading: specLoading, isError: specError } = useStackChartSpec(stackId ?? null, completeIds, hasResults)
  const requestCandles = useRunCandles(rawSpec?.base_run_id ?? null)
  const priceSpec = useMemo(() => {
    if (!rawSpec) return undefined
    // Each trade carries its strategy's colour AND name — the chart prints the name in the trade's
    // outcome chip ("SOS Fade · Won") and derives its Strategies dropdown from these same fields.
    const nameOf = new Map(rawSpec.layers.map(l => [l.strategy_id, l.strategy_name]))
    const trades = rawSpec.trades
      .filter(t => t.layer && enabled.has(t.layer))
      .map(t => ({ ...t, layerColor: colorFor(t.layer!), layerName: nameOf.get(t.layer!) ?? t.layer }))
    return { ...rawSpec, trades }
  }, [rawSpec, enabled, colorFor])

  const chartControls = (key: string) => key === 'equity' ? (
    <>
      <SeriesToggle label={hasExcursion ? 'Trade excursions' : 'Histogram'} on={histOn} onChange={setHistOn} />
      <SeriesToggle label="Run-ups & drawdowns" on={rudOn} onChange={setRudOn} />
      <XModeToggle value={xMode} onChange={toggleXMode} />
      {hasRegimes && <RegimeOverlayToggle on={overlayOn} onChange={setOverlayOn} />}
    </>
  ) : null

  const renderChart = (key: string, h: number, isModal = false) => {
    switch (key) {
      case 'equity':
        // Real EquityCurveChart on the COMBINED portfolio (so it inherits every backtest toggle —
        // excursions, run-ups, date/trade, regimes, expand) with a line per enabled strategy overlaid.
        return (
          <>
            <StackEquityLegend activeLegs={activeLegs} colorFor={colorFor} />
            <EquityCurveChart
              data={combined.equity}
              overlayLines={overlayLines}
              bands={regimeBands}
              showHistogram={histOn}
              showRunupDrawdown={rudOn}
              xMode={xMode}
              windowStart={stack?.start_date ?? null}
              height={h}
            />
          </>
        )
      case 'price': {
        if (isModal) return null   // price manages its own fullscreen (position:fixed)
        return (
          <PriceChartView
            spec={priceSpec}
            isLoading={specLoading}
            isError={specError}
            requestCandles={priceSpec?.baseTimeframe !== 'D1' ? requestCandles : undefined}
            height={h}
            isFullscreen={fullscreen === 'price'}
            onFullscreenClose={() => setFullscreen(null)}
          />
        )
      }
      case 'breakdown': {
        const hDraw = Math.max(140, Math.round((h - 56) * 0.45))
        const hRow = Math.max(160, Math.round((h - 56) * 0.55))
        return (
          <div className="space-y-8">
            <div>
              <div className="text-[11px] font-semibold text-text-secondary uppercase tracking-[0.7px] mb-2">Drawdown from peak</div>
              <DrawdownChart equity={combined.equity} height={hDraw} />
            </div>
            <div className={combined.hasDirection ? 'grid gap-6 lg:grid-cols-2' : ''}>
              <div>
                <div className="text-[11px] font-semibold text-text-secondary uppercase tracking-[0.7px] mb-2">Daily P&L</div>
                <DailyPnlChart data={combined.dailyPnl} netPnl={combined.run.net_pnl} height={hRow} />
              </div>
              {combined.hasDirection && (
                <div>
                  <div className="text-[11px] font-semibold text-text-secondary uppercase tracking-[0.7px] mb-2">Long vs Short</div>
                  <DirectionBreakdown equity={combined.equity} />
                </div>
              )}
            </div>
          </div>
        )
      }
      default:
        return null
    }
  }

  return (
    <div>
      <StickyHeader>
        {scrolled => (
          <div className={`flex items-center justify-between gap-3 ${scrolled ? 'mb-4' : 'mb-5'}`}>
            <div className="flex items-center gap-2.5 min-w-0">
              <button
                onClick={() => navigate('/backtests?tab=stacks')}
                className="flex items-center gap-2 text-[13px] text-text-tertiary hover:text-text-secondary transition-colors flex-shrink-0"
              >
                <ArrowLeft size={14} /> {!scrolled && 'Stacks'}
              </button>
              {scrolled && stack && (
                <>
                  <span className="text-text-tertiary flex-shrink-0">·</span>
                  <h1 className="text-[14px] font-semibold truncate">{stackTitle}</h1>
                </>
              )}
            </div>
            {stack && !isRunning && (
              <div className="flex items-center gap-2 flex-shrink-0">
                <button
                  onClick={() => setShowRerun(true)}
                  className="flex items-center gap-[6px] px-3 py-[6px] rounded-md text-[12px] font-medium text-text-secondary hover:text-text-primary border border-border-default hover:bg-bg-hover transition-colors"
                >
                  <Play size={12} /> Rerun
                </button>
                <button
                  onClick={() => setConfirmDelete(true)}
                  className="flex items-center gap-[6px] px-3 py-[6px] rounded-md text-[12px] font-medium text-text-tertiary hover:text-neg-text hover:bg-neg-muted border border-transparent hover:border-neg-text/20 transition-colors"
                >
                  <Trash2 size={12} /> Delete
                </button>
              </div>
            )}
          </div>
        )}
      </StickyHeader>

      {confirmDelete && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 px-4" onClick={e => { if (e.target === e.currentTarget) setConfirmDelete(false) }}>
          <div className="bg-bg-surface border border-border-default rounded-xl w-full max-w-[400px] shadow-2xl">
            <div className="px-5 py-4 border-b border-border-subtle"><div className="text-[15px] font-semibold">Delete this stack?</div></div>
            <div className="px-5 py-4">
              <p className="text-[13px] text-text-secondary">
                The stack and any runs it created will be removed. Reused standalone runs stay in your Runs tab. This cannot be undone.
              </p>
            </div>
            <div className="flex items-center justify-end gap-3 px-5 py-4 border-t border-border-subtle">
              <button onClick={() => setConfirmDelete(false)} className="px-4 py-[7px] rounded-md text-[13px] text-text-secondary hover:text-text-primary hover:bg-bg-hover transition-colors">Cancel</button>
              <button
                onClick={() => deleteStack.mutate(stackId!, { onSuccess: () => navigate('/backtests?tab=stacks') })}
                disabled={deleteStack.isPending}
                className="px-4 py-[7px] rounded-md text-[13px] font-medium bg-neg-muted text-neg-text border border-neg/40 hover:bg-neg/15 disabled:opacity-50 transition-colors"
              >
                {deleteStack.isPending ? 'Deleting…' : 'Delete stack'}
              </button>
            </div>
          </div>
        </div>
      )}

      {showRerun && stack && (
        <StackConfigModal
          title="Rerun stack"
          submitLabel="Rerun stack"
          initial={{
            strategyIds: legs.map(l => l.strategy_id),
            instrument: stack.instrument,
            barValue: stack.bar_value,
            commPerSide: stack.commission_per_side,
            slippageTicks: stack.slippage_ticks,
            start: stack.start_date,
            end: stack.end_date,
            // The mode and its account knobs are part of what a stack IS, so a rerun that
            // silently reverted to a screen would produce a different experiment under the word
            // "rerun" — and the two report different numbers with nothing on screen to explain it.
            mode: stack.mode,
            accountSize: stack.account_size ?? undefined,
            riskCapPct: stack.risk_cap_pct ?? undefined,
            entryFloorPct: stack.entry_floor_pct ?? undefined,
          }}
          onClose={() => setShowRerun(false)}
        />
      )}

      {isLoading && (
        <div className="animate-pulse space-y-4">
          <div className="h-7 w-80 bg-bg-surface rounded" />
          <div className="h-4 w-56 bg-bg-surface rounded" />
          <div className="h-[300px] bg-bg-surface rounded-xl" />
        </div>
      )}

      {stack && (
        <div className="space-y-6">
          {/* Header */}
          <div>
            <div className="flex items-center gap-2 mb-2">
              <Layers size={18} className="text-gold-text" />
              <h1 className="text-h1 font-semibold leading-tight">{stackTitle}</h1>
            </div>
            <div className="flex flex-wrap gap-1.5">
              <span className="inline-flex items-center px-2 py-[3px] rounded text-[11px] font-semibold font-mono bg-gold-muted text-gold-text border border-gold-text/20">
                {stack.total_strategies}-strategy Stack
              </span>
              <span className="inline-flex items-center px-2 py-[3px] rounded text-[11px] font-medium bg-bg-surface border border-border-subtle text-text-secondary font-mono">{stack.instrument}</span>
              <span className="inline-flex items-center px-2 py-[3px] rounded text-[11px] font-medium bg-bg-surface border border-border-subtle text-text-secondary font-mono">
                {fmtDate(stack.start_date)} → {fmtDate(stack.end_date)}
              </span>
              {/* The mode belongs in the header, beside the window: a screen and a shared run over
                  the same legs report different numbers, and the reader has to know which one they
                  are looking at BEFORE reading any of them. */}
              {isShared ? (
                <span
                  data-testid="stack-mode-chip"
                  title="One balance and one risk budget the strategies competed for."
                  className="inline-flex items-center px-2 py-[3px] rounded text-[11px] font-semibold bg-accent/10 text-accent border border-accent/30 font-mono"
                >
                  Shared account · {stack.risk_cap_pct?.toFixed(2)}% cap
                </span>
              ) : (
                <span
                  data-testid="stack-mode-chip"
                  title="Each strategy ran on its own full account and the results were added together, so no strategy could ever block another. Read it as an upper bound."
                  className="inline-flex items-center px-2 py-[3px] rounded text-[11px] font-medium bg-bg-surface border border-border-subtle text-text-tertiary font-mono"
                >
                  Screen · upper bound
                </span>
              )}
            </div>
          </div>

          {/* Running / cancel banner */}
          {isRunning && (
            <div className="flex items-center justify-between gap-4 rounded-lg border border-accent/20 bg-accent/5 px-4 py-3">
              <div className="flex items-center gap-2 text-[13px] text-accent">
                <Loader2 size={14} className="animate-spin" />
                Running — {stack.completed_strategies} of {stack.total_strategies} strategies complete
                <span className="text-text-tertiary text-[11px]">· auto-refreshing</span>
              </div>
              <button
                onClick={() => cancelStack.mutate(stackId!)}
                disabled={cancelStack.isPending}
                className="flex items-center gap-[6px] px-3 py-[6px] rounded-md text-[12px] font-medium border border-neg-text/30 text-neg-text hover:bg-neg-muted disabled:opacity-50 transition-colors"
              >
                <Square size={11} /> {cancelStack.isPending ? 'Cancelling…' : 'Cancel'}
              </button>
            </div>
          )}

          {/* ── Performance ──
              THE SAME PANEL A SINGLE BACKTEST RENDERS: one row of four question cards — Verdict,
              Made, Risked, Trusted — behind the same collapsible header reading the same stored
              preference. A stack used to wear a full-width strategy ribbon over three cards, which
              made two pages showing the same numbers look like two different features (Aaron's
              call, 2026-08-10: "I don't want stack stuff here and a regular backtest details page
              to look two different").

              The legs live INSIDE the Verdict card now, as rows you click. They were a section of
              their own further down the page, so the control deciding what every KPI counts was
              nowhere near the KPIs it recomputes. */}
          {(hasResults || combined.basis === 'unmeasured') && (
            <div className="space-y-2.5">
              <div className="flex items-center justify-between gap-3 mb-2">
                <PerfCollapseToggle collapsed={perfCollapsed} onToggle={togglePerfCollapsed} />
                <BasisChip basis={combined.basis} />
              </div>
              {/* 🔴 An UNMEASURED selection still renders the Verdict card, and it has to: the leg
                  toggles live inside it, so hiding the panel would leave the reader in a state they
                  could not click their way out of. The three KPI cards are replaced by the reason,
                  because there is no book to compute them from. */}
              {combined.basis === 'unmeasured' ? (
                <div className="flex flex-col lg:flex-row gap-2.5 items-stretch">
                  <div className="lg:w-[285px] shrink-0">
                    {verdictCard}
                  </div>
                  <UnmeasuredCard onAllOn={() => setEnabled(new Set(completeIds.split(',')))} />
                </div>
              ) : (
                <PerformancePanel
                  run={combined.run} fallback={combined.fallback} equity={combined.equity}
                  balance={combined.balance}
                  collapsed={perfCollapsed}
                  verdict={verdictCard}
                />
              )}
            </div>
          )}

          {/* The shared account — the ONE section a single backtest has no counterpart for, which
              is exactly why it is the only thing on this page that does not mirror one. It sits
              BELOW Performance and is deliberately not driven by the leg toggles above: the budget
              is a property of the run as it happened, not of whichever legs are currently on. */}
          {isShared && shared && (
            <div>
              <h2 className="text-[11px] font-semibold text-text-secondary uppercase tracking-[0.7px] mb-3">
                The shared account
              </h2>
              <SharedAccountPanel
                report={shared}
                colorFor={colorFor}
                nameFor={(id) => legs.find(l => l.strategy_id === id)?.strategy_name ?? id}
              />
            </div>
          )}

          {/* Charts — Equity / Price / Breakdown, exactly like a single backtest */}
          {hasResults ? (
            <div className="space-y-4">
              <div className="text-[11px] font-semibold text-text-secondary uppercase tracking-[0.7px]">Charts</div>
              <ChartTabPanel
                tabs={CHART_TABS}
                active={chartTab}
                onActive={setChartTab}
                sub={CHART_SUBS[chartTab]}
                height={520}
                onExpand={() => setFullscreen(chartTab)}
                render={(k, h) => renderChart(k, h)}
                right={chartControls(chartTab)}
              />
              {fullscreen && fullscreen !== 'price' && (
                <ChartModal
                  title={fullscreen === 'equity' ? 'Equity Curve' : 'Breakdown'}
                  onClose={() => setFullscreen(null)}
                  render={h => renderChart(fullscreen, h, true)}
                  controls={chartControls(fullscreen)}
                />
              )}
            </div>
          ) : !isRunning ? (
            <div className="rounded-xl border border-border-subtle bg-bg-surface px-6 py-10 text-center text-[13px] text-text-tertiary">
              No completed strategy runs to compose. {legs.some(l => l.status.startsWith('failed')) && 'Some runs failed — check the chips above.'}
            </div>
          ) : (
            <div className="rounded-xl border border-border-subtle bg-bg-surface px-6 py-10 text-center text-[13px] text-text-tertiary">
              Waiting for the first strategy to finish…
            </div>
          )}

          {/* Per-strategy table — each row opens that leg's own backtest (back returns here) */}
          {legs.some(l => l.status === 'complete') && (
            <div>
              <h2 className="text-[11px] font-semibold text-text-secondary uppercase tracking-[0.7px] mb-3">Per-strategy results</h2>
              <div className="bg-bg-surface border border-border-subtle rounded-xl overflow-hidden overflow-x-auto">
                <table className="w-full text-[12px]">
                  <thead>
                    <tr className="border-b border-border-subtle bg-bg-sunken">
                      <th className="text-left px-3 py-2 text-text-tertiary font-medium">Strategy</th>
                      <th className="text-left px-3 py-2 text-text-tertiary font-medium">Net P&L</th>
                      <th className="text-left px-3 py-2 text-text-tertiary font-medium">Max DD</th>
                      <th className="text-left px-3 py-2 text-text-tertiary font-medium">Sharpe</th>
                      <th className="text-left px-3 py-2 text-text-tertiary font-medium">Trades</th>
                      <th className="text-left px-3 py-2 text-text-tertiary font-medium">Status</th>
                      <th className="px-3 py-2 w-16" />
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-border-subtle">
                    {legs.map(leg => {
                      const done = leg.status === 'complete'
                      const failed = leg.status.startsWith('failed')
                      return (
                        <tr
                          key={leg.run_id}
                          onClick={() => done && navigate(`/backtests/runs/${leg.run_id}`, { state: { fromStack: stackId, fromStackTitle: stackTitle } })}
                          className={`transition-colors ${done ? 'hover:bg-bg-hover cursor-pointer' : ''}`}
                        >
                          <td className="px-3 py-[9px] font-semibold text-text-primary">
                            <span className="inline-flex items-center gap-2">
                              <span className="w-2.5 h-2.5 rounded-[3px] flex-shrink-0" style={{ backgroundColor: colorFor(leg.strategy_id) }} />
                              {leg.strategy_name}
                            </span>
                          </td>
                          <td className={`px-3 py-[9px] font-mono tabular-nums ${(leg.net_pnl ?? 0) >= 0 ? 'text-pos-text' : 'text-neg-text'}`}>
                            {leg.net_pnl != null ? fmtMoney(leg.net_pnl) : '—'}
                          </td>
                          <td className="px-3 py-[9px] font-mono tabular-nums text-neg-text">
                            {leg.max_drawdown != null ? fmtMoney(-Math.abs(leg.max_drawdown), false) : '—'}
                          </td>
                          <td className="px-3 py-[9px] font-mono tabular-nums text-text-secondary">
                            {leg.sharpe != null ? leg.sharpe.toFixed(2) : '—'}
                          </td>
                          <td className="px-3 py-[9px] tabular-nums text-text-secondary">{leg.trade_count ?? '—'}</td>
                          <td className="px-3 py-[9px]">
                            {done && <span className="inline-flex items-center gap-1.5 text-[11px] text-accent"><CheckCircle2 size={11} /> complete</span>}
                            {failed && <span className="inline-flex items-center gap-1.5 text-[11px] text-neg-text" title={leg.error_message ?? ''}><XCircle size={11} /> failed</span>}
                            {!done && !failed && <span className="inline-flex items-center gap-1.5 text-[11px] text-text-tertiary"><Loader2 size={11} className="animate-spin" /> running</span>}
                          </td>
                          <td className="px-3 py-[9px] text-right">{done && <span className="text-[11px] text-accent">View →</span>}</td>
                        </tr>
                      )
                    })}
                  </tbody>
                </table>
              </div>
            </div>
          )}
        </div>
      )}
    </div>
  )
}
