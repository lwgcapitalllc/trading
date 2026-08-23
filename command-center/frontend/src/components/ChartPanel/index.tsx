/**
 * ChartPanel — strategy-agnostic backtest chart (klinecharts v9).
 *
 * Renders whatever a `ChartSpec` declares (see ./types). Contains ZERO strategy-specific
 * logic: no instrument names, no session names, no breakout/range concepts. Adding a new
 * strategy means its spec lists different overlays — this file does not change.
 *
 * Lazy-mounted: imported via React.lazy from the backtest page so klinecharts + the fixture
 * only load once the panel's section is opened (page performance).
 */
import { Fragment, useCallback, useEffect, useMemo, useRef, useState, type ReactNode } from 'react'
import {
  AlignJustify,
  CalendarSearch,
  Camera,
  Check,
  ChevronDown,
  ChevronLeft,
  ChevronRight,
  Eye,
  EyeOff,
  Loader2,
  RotateCcw,
  Ruler,
  Settings,
  Settings2,
  Trash2,
} from 'lucide-react'
import { toast } from 'sonner'
import { DATE_INDICATOR_CLS } from '@/lib/inputs'
import {
  ActionType,
  DomPosition,
  IndicatorSeries,
  LoadDataType,
  dispose,
  init,
  type Chart,
  type KLineData,
} from 'klinecharts'
import type {
  ChartBlock,
  ChartBlockReason,
  ChartCandle,
  ChartMiss,
  ChartOverlay,
  ChartPage,
  ChartSpec,
  ChartTrade,
  TradeOutcome,
} from './types'
import { chartStyles, makeCandleTooltip } from './chartStyles'
import { AUDJPY_FIXTURE } from './fixtures/audjpy'
import {
  ANALYSIS_GROUPS,
  ANALYSIS_GROUP_COLOR,
  BLOCK,
  BOX,
  CANDLE_MARK,
  DATA_EDGE,
  DAY_BREAK,
  FIB,
  FOCUS,
  GROUP_CANDLE_MARKS,
  HLINE,
  LABEL,
  type LabelItem,
  LOADING_EDGE,
  MISS,
  SESSION_BOX,
  STRUCTURE_GROUPS,
  STRUCTURE_GROUP_COLOR,
  TRADE,
  TRADE_ADD,
  TRADE_FIB,
  VLINE,
  registerChartOverlays,
  withAlpha,
} from './overlays'
import FibSettings from './FibSettings'
import FibLevelEditor from './FibLevelEditor'
import ChartSettingsPanel from './ChartSettingsPanel'
import { loadChartSettings, saveChartSettings, type ChartSettings } from './chartSettings'
import {
  DEFAULT_FIB_LEVELS,
  loadFibLevels,
  sameFibLevels,
  saveFibLevels,
  type FibLevel,
} from './fibLevels'
import { ensureSeriesIndicator } from './indicators'
import { sessionWindows } from './sessions'
import theme from '@/themes/dark-2026'

interface MeasureRect {
  x: number
  y: number
  w: number
  h: number
  startTs: number
  endTs: number
  startVal: number
  endVal: number
}
interface LockedMeasurement extends MeasureRect {
  id: string
}

function fmtDuration(ms: number): string {
  const m = Math.round(ms / 60_000)
  const d = Math.floor(m / 1440)
  const h = Math.floor((m % 1440) / 60)
  const min = m % 60
  if (d > 0) return h > 0 ? `${d}d ${h}h` : `${d}d`
  if (h > 0) return min > 0 ? `${h}h ${min}m` : `${h}h`
  return `${min}m`
}

function fmtDiff(v: number): string {
  const a = Math.abs(v)
  return a >= 100 ? a.toFixed(2) : a >= 1 ? a.toFixed(4) : a.toFixed(5)
}

const CHART_HEIGHT = 520
const DAY_MS = 24 * 60 * 60 * 1000
const TRADE_WIN_COLOR = theme.pos // green box — trade won
const TRADE_LOSS_COLOR = theme.neg // red box — trade lost
// A SCRATCH is off the win/loss axis, like a blocked setup: neither green nor red, because the
// trade did not resolve either way. Painting it red is what made a $0.00 trade read as a loss.
// 🔴 It was `theme.textSecondary` until 2026-08-20 and that was the wrong kind of neutral — the
// SAME grey the chart already uses for body text, the entry marker and every unlayered chip, so a
// scratch chip did not read as a THIRD verdict, it read as a chip nobody had coloured in. Orange
// is off the green/red axis just as cleanly AND is findable by eye in a run full of wins and
// losses (Aaron's call).
// ⚠ NOT `theme.warn` (#ffb300), which was the obvious pick and is wrong: `MISS_COLOR` below is
// already amber (#ff9800) and the two are ΔE 15.8 apart in Lab — the same colour on a 10px chip,
// so a scratched trade and a setup that never finished would have been one signal. MEASURED across
// every colour this chart puts on screen; #ff5c00 is ΔE 31.4 from the miss amber, 49.3 from the
// loss red, 80.9 from the blocked pink and 101.5 from the grey it replaces. **Re-run that check
// before adding any warm colour here** — the collision is invisible in code and obvious on screen.
// ⚠ Change it HERE and nowhere else: this constant feeds the box, the outcome chip (through the
// overlay's `scratchColor`), the Step navigator pill and the Show filters via `outcomeColor`, and
// a second literal would let two of them grade the same trade in two colours.
const TRADE_SCRATCH_COLOR = '#ff5c00'

/** WON / SCRATCH / LOST for one trade — the ONE place the chart decides, so the chip, the box
 *  colour, the Step navigator and the Show filters can never grade the same trade differently.
 *
 *  The verdict is the BACKEND's when it graded the run (`outcome`, measured against the run's own
 *  median full loss — the same bar its `scratch_count` KPI uses). A run it could not grade — no
 *  losing trade to scale against — carries none, and the sign of the P&L is the fallback. ⚠ The
 *  fallback never returns `scratch`: an ungraded trade is not a measured flat one. */
function tradeOutcome(tr: Pick<ChartTrade, 'pnl' | 'outcome'>): TradeOutcome {
  return tr.outcome ?? (tr.pnl > 0 ? 'won' : 'lost')
}

/** The colour that verdict is drawn in — box, chip, navigator pill. */
function outcomeColor(v: TradeOutcome): string {
  return v === 'won' ? TRADE_WIN_COLOR : v === 'scratch' ? TRADE_SCRATCH_COLOR : TRADE_LOSS_COLOR
}
// Profit-fill mint — deliberately LIGHTER than the candle up-colour (theme.pos) so the
// profit-depth band never blends into the green candles inside it (Aaron 2026-07-20).
const TRADE_PROFIT_FILL = '#8ef2b8'
// Blocked setups get their OWN colour, off the win/loss axis entirely — a refused trade is not a
// loser, and painting it red would read as one. Pink, matching the Pine's `TRADE BLOCKED` tag.
// Candles handed to klinecharts on open — the newest slice of a spec that now carries the whole run.
//
// 🔴 **This exists because klinecharts' layout cost is the binding constraint, MEASURED: applying
// 155,798 bars freezes the main thread for 30.8 seconds; 33,046 bars cost 2.2s.** So the number
// here is a RENDER budget, and it is deliberately not the payload budget it replaced — holding six
// years of candles in JS is nothing, laying them out is everything.
// 12,000 at M15 is ~175 trading days, which is more than a screen and cheap to extend.
const APPLIED_BARS = 12_000
// One scroll-left page of older history, in BARS. Since 2026-08-06 a page is a SLICE of the
// in-memory spec rather than a fetch, so this is a render-cost knob only.
const PAGE_BARS = 12_000
// ⚠ A JUMP DELIBERATELY USES THE SAME PAGE SIZE, and bulk-paging it was BUILT, MEASURED AND
// REVERTED (2026-08-06). The per-bar arithmetic says bulk should win: measured against the live
// backend on run 211384ddbea4 at M15 with analysis on, a 175d/11,188-bar page costs 6.63s
// (0.59 ms/bar) against 875d/56,632 bars at 20.23s (0.36 ms/bar). Driven end to end over a real
// six-year jump it bought **6%** — 89.4s → 83.9s — because the span is fixed and the analysis
// replay dominates either way, and it cost the thing the change was FOR: the progress readout
// stepped 3 times instead of ~14, i.e. 25 seconds of stillness between updates instead of 6.
// A minute-long wait that looks alive beats one that is 6% shorter and looks hung.
// The real lever is the ANALYSIS, not the page size — see `loadOlder`.
const BLOCK_COLOR = '#ff2e9a'
// Missed setups sit on the same "the trade that never happened" axis as Blocked, so they take a
// sibling colour rather than a new one: amber, matching the Pine's orange 2-of-3 callout, and
// still nowhere near the win/loss green/red. Blocked pink = a rule said no; missed amber = the
// setup never finished. Two answers to one question, readable apart at a glance.
const MISS_COLOR = '#ff9800'
const TIP_W = 260 // hover-card width; feeds the viewport clamp
const TIP_H = 220 // ~its height with a met list + a reason; same clamp
const DEFAULT_OVERLAY_COLOR = theme.textTertiary // fallback when a spec overlay omits a color
const DAY_BREAK_COLOR = theme.textTertiary // muted vertical line for daily session breaks
const INDICATOR_PALETTE = [theme.gold, theme.series[4], theme.accent, theme.series[1]] // line colors

type TfOption = { label: string; min: number }

/** One row in a header dropdown: a coloured dot, a label, an optional count, a tick when on.
 *  `sub` indents it under the row above (a filter of that layer rather than a peer of it). */
interface MenuToggle {
  key: string
  label: string
  color: string
  on: boolean
  toggle: () => void
  sub?: boolean
  count?: number
  /** Caption + rule drawn ABOVE this row, i.e. this row opens a new section of the menu. */
  section?: string
  /** This row is an ACTION (a preset), not a layer — so it is left out of the header's `on/total`
   *  count. Counting a shortcut as a layer would make "Analysis 4/7" describe something that isn't
   *  a set of layers, and the count is what the reader uses to see how much is drawn. */
  action?: boolean
  chips?: undefined
}

/** One VALUE of a filter — a reason, a score, a direction. Not a layer: it narrows a layer that is
 *  already on, and it is never a thing the chart draws on its own. */
interface MenuChip {
  key: string
  label: string
  on: boolean
  toggle: () => void
  count?: number
}

/** A filter's whole value set, drawn as wrapped chips under its own caption rather than as one row
 *  per value.
 *
 *  ⚠ **The caption is the point, not the space it saves.** The Missed layer offers two INDEPENDENT
 *  filters — score and missing-confluence — and each is a complete partition of the same setups
 *  (measured on the shipped run: 35 + 417 = 452, and 179 + 238 + 21 + 10 + 4 = 452). Listed as one
 *  indented column of seven they read as seven sub-filters of one thing, and the counts read as
 *  double-counting. Naming each set is what says they answer different questions. */
interface MenuChips {
  key: string
  /** The FILTER's name — "Score", "Missing", "Direction". Not a layer name. */
  label: string
  color: string
  chips: MenuChip[]
  section?: string
}

type MenuItem = MenuToggle | MenuChips

/** The hover answer behind a would-be-entry marker (Blocked or Missed), and where to float it.
 *  `met` is what the setup DID have (empty for a block, which by definition had everything);
 *  `reasons` is what stopped it. Page coordinates — see where this is set. */
interface MarkerTip {
  x: number
  y: number
  color: string
  title: string
  met: string[]
  reasons: ChartBlockReason[]
  price: number
  /** Portfolio stack only — WHOSE rule refused this setup, or whose confluence was missing. Absent
   *  on a single run, where the question does not arise. It is the reason these two layers were
   *  dropped from a stack chart until 2026-08-10: a merged chart with no name on the card cannot
   *  say which strategy is speaking, and a refusal attributed to the wrong bot is worse than none. */
  strategy?: string
}

/** The card itself. ONE component for both marker layers: they answer the same question ("why is
 *  there no trade here?") in the same shape, and two cards would drift in styling and in clamp
 *  maths. `pointerEvents: none` so it can never eat the hover that spawned it (which would
 *  flicker it on and off), and viewport-`fixed` + clamped like the right-click menu, so a marker
 *  at the right or bottom edge of the chart still shows its whole card. */
function MarkerTipCard({ tip, precision }: { tip: MarkerTip; precision: number }) {
  return (
    <div
      style={{
        position: 'fixed',
        left: Math.max(6, Math.min(tip.x + 14, window.innerWidth - TIP_W - 6)),
        top: Math.max(6, Math.min(tip.y + 12, window.innerHeight - TIP_H - 6)),
        width: TIP_W,
        pointerEvents: 'none',
        zIndex: 60,
      }}
      className="rounded-md border border-border-subtle bg-bg-surface px-2.5 py-2 shadow-lg"
    >
      <div className="text-[11px] font-semibold" style={{ color: tip.color }}>
        {tip.title}
      </div>
      {tip.strategy && <div className="text-[10px] text-text-tertiary">{tip.strategy}</div>}
      {/* What it HAD — only a miss carries these; a block had everything by definition. */}
      {tip.met.length > 0 && (
        <div className="mt-1.5">
          <div className="text-[10px] uppercase tracking-wide text-text-tertiary">Met</div>
          {tip.met.map((line, i) => (
            <div key={i} className="text-[11px] leading-snug text-text-secondary">
              {line}
            </div>
          ))}
        </div>
      )}
      {/* …and what stopped it, in the strategy's own precedence order (primary first) — the tag
          carries only a count or a score, so this is where the reasons live. */}
      {tip.met.length > 0 && (
        <div className="mt-1.5 text-[10px] uppercase tracking-wide text-text-tertiary">Missing</div>
      )}
      {tip.reasons.map((r, i) => (
        <div key={i} className={tip.met.length > 0 ? '' : 'mt-1.5'}>
          <div className="text-[11px] font-medium text-text-primary">{r.label}</div>
          <div className="text-[11px] leading-snug text-text-secondary">{r.reason}</div>
        </div>
      ))}
      <div className="mt-1.5 border-t border-border-subtle pt-1.5 text-[10px] text-text-tertiary">
        Entry would have rested at{' '}
        <span className="font-mono tabular-nums text-text-secondary">
          {tip.price.toFixed(precision)}
        </span>
      </div>
    </div>
  )
}

/** The header's multi-select dropdown — Layers, Analysis and Strategies are all this component
 *  with different items, so a row can never render three different ways. It owns its own open
 *  state + click-outside close, and deliberately stays OPEN while toggling (these menus are used
 *  to compare combinations, not to make one choice). */
function ToggleMenu({
  title,
  items,
  minWidth = 172,
}: {
  title: string
  items: MenuItem[]
  minWidth?: number
}) {
  const [open, setOpen] = useState(false)
  const ref = useRef<HTMLDivElement>(null)
  useEffect(() => {
    if (!open) return
    const onDown = (e: MouseEvent) => {
      if (ref.current && !ref.current.contains(e.target as Node)) setOpen(false)
    }
    document.addEventListener('mousedown', onDown)
    return () => document.removeEventListener('mousedown', onDown)
  }, [open])
  // LAYERS only. An `action` row is a preset and a `chips` row is a filter's value set — neither is
  // something drawn — so counting either would make the header's `on/total` stop describing how much
  // is on the chart, which is its whole job.
  const layers = items.filter((it): it is MenuToggle => !it.chips && !it.action)
  const activeCount = layers.filter((it) => it.on).length
  return (
    <div ref={ref} className="relative">
      <button
        onClick={() => setOpen((o) => !o)}
        className="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-md border border-border-subtle bg-bg-sunken text-[11px] font-medium text-text-secondary hover:text-text-primary transition-colors"
      >
        {title}
        <span className="font-mono text-text-tertiary">
          {activeCount}/{layers.length}
        </span>
        <ChevronDown
          className={`w-3 h-3 text-text-tertiary transition-transform ${open ? 'rotate-180' : ''}`}
        />
      </button>
      {open && (
        // ⚠ BOUNDED, because this menu grows with the run. Fully expanded on a full-history run it
        // MEASURES 741px against a 940px viewport, and the header it hangs from is rarely at the
        // top of the page — so unbounded it runs off the bottom and the rows down there cannot be
        // reached at all. (It was 862px before the filters became chips.)
        <div
          className="absolute left-0 mt-1 overflow-y-auto rounded-md border border-border-subtle bg-bg-surface py-1 shadow-lg"
          style={{ zIndex: 50, minWidth, maxHeight: 'min(70vh, 620px)' }}
        >
          {items.map((it, i) => (
            <Fragment key={it.key}>
              {/* A section caption, with a rule above it unless it opens the menu. This is what lets
                  one menu carry both the presets and the layers they set without either reading as
                  a stray row in the other's list. */}
              {it.section && (
                <div
                  className={`px-3 pb-1 text-[9px] uppercase tracking-wide text-text-tertiary ${
                    i === 0 ? 'pt-0.5' : 'mt-1 pt-1.5 border-t border-border-subtle'
                  }`}
                >
                  {it.section}
                </div>
              )}
              {it.chips ? (
                // A filter's values, captioned and wrapped. Indented to the `sub` gutter so they
                // still read as belonging to the layer above, but they are deliberately NOT rows:
                // a row is a thing the chart draws, and none of these is.
                <div className="pl-7 pr-3 pb-1">
                  <div className="pb-1 text-[9px] uppercase tracking-wide text-text-tertiary">
                    {it.label}
                  </div>
                  <div className="flex flex-wrap gap-1">
                    {it.chips.map((c) => (
                      <button
                        key={c.key}
                        onClick={c.toggle}
                        aria-pressed={c.on}
                        className="rounded px-1.5 py-0.5 text-[10px] font-medium transition-colors"
                        style={{
                          color: c.on ? theme.textPrimary : theme.textTertiary,
                          background: c.on ? withAlpha(it.color, 0.18) : 'transparent',
                          boxShadow: `inset 0 0 0 1px ${c.on ? withAlpha(it.color, 0.55) : theme.borderSubtle}`,
                        }}
                      >
                        {c.label}
                        {c.count != null && (
                          <span className="ml-1 font-mono opacity-70">{c.count}</span>
                        )}
                      </button>
                    ))}
                  </div>
                </div>
              ) : (
                /* Every row here is a TOGGLE, and its on-state was carried only by a colour dot and a
                   tick glyph — so nothing outside the pixels could read it. `aria-pressed` states it
                   for a screen reader and, equally, for a browser check: a test that has to infer a
                   toggle's state from an icon is asserting the icon. */
                <button
                  onClick={it.toggle}
                  aria-pressed={it.on}
                  className={`flex w-full items-center gap-2 py-1.5 pr-3 text-left text-[11px] font-medium transition-colors hover:bg-bg-sunken ${it.sub ? 'pl-7' : 'pl-3'}`}
                >
                  <span
                    className="w-2 h-2 rounded-full flex-shrink-0"
                    style={{
                      background: it.on ? it.color : 'transparent',
                      boxShadow: `inset 0 0 0 1px ${it.color}`,
                      opacity: it.on ? 1 : 0.5,
                    }}
                  />
                  <span className={it.on ? 'text-text-primary' : 'text-text-tertiary'}>
                    {it.label}
                  </span>
                  {it.count != null && (
                    <span className="font-mono text-text-tertiary">{it.count}</span>
                  )}
                  {it.on && <Check className="w-3 h-3 ml-auto flex-shrink-0 text-accent" />}
                </button>
              )}
            </Fragment>
          ))}
        </div>
      )}
    </div>
  )
}

/** One thing the Step navigator can park on. Deliberately NOT "a trade": the layers already on the
 *  chart — winners, losers, blocked setups, missed setups — are all answers to "where did the
 *  strategy act", and stepping should reach whichever of them are on screen. */
interface NavMarker {
  id: string // kind-prefixed, so a trade and a block can never collide on one id
  ts: number // the bar the chart parks on (a trade's ENTRY, a block/miss's own bar)
  kind: 'win' | 'scratch' | 'loss' | 'block' | 'miss'
  label: string // the word the pill prints — "Win" / "Scratch" / "Loss" / "Blocked" / "Missed"
  color: string
  note: string // the extra line on hover (direction + P&L, or the refusing rule)
}

const NAV_KIND_LABEL: Record<NavMarker['kind'], string> = {
  win: 'Win',
  scratch: 'Scratch',
  loss: 'Loss',
  block: 'Blocked',
  miss: 'Missed',
}

/** Epoch ms → "YYYY-MM-DD HH:MM" in LOCAL time — the axis's own timezone (see `toIsoDay`). */
function fmtStamp(ms: number): string {
  const d = new Date(ms)
  const p = (n: number) => String(n).padStart(2, '0')
  return `${toIsoDay(ms)} ${p(d.getHours())}:${p(d.getMinutes())}`
}

/** "Step" — ◀ / ▶ through the markers currently ON the chart, oldest to newest.
 *
 *  It has no set of its own and no filters of its own: the set is whatever the Analysis dropdown is
 *  showing. Turn Losers off and ◀ walks the winners; turn Trades off and leave Blocked on and it
 *  walks the refusals. That is the whole design — a second place to choose "winners only" would be
 *  a second place for it to disagree with the chart.
 *
 *  A pure control, like `GoToDate`: it reports a direction and prints where it is. Paging the
 *  history in and centring the bar belong to the host. */
function MarkerNav({
  current,
  idx,
  total,
  onStep,
}: {
  current: NavMarker | null
  idx: number // 0-based position of `current` in the set, or -1 when parked nowhere
  total: number
  onStep: (dir: 1 | -1) => void
}) {
  // At an end the arrow is dead, and it says so by going dim rather than by doing nothing on click.
  const atStart = idx === 0
  const atEnd = idx >= 0 && idx === total - 1
  const btn =
    'flex items-center justify-center w-6 h-[22px] transition-colors disabled:opacity-30 disabled:cursor-default'
  return (
    <div
      className="inline-flex items-center rounded-md border border-border-subtle bg-bg-sunken overflow-hidden"
      title={
        current
          ? `${current.label} — ${fmtStamp(current.ts)}\n${current.note}\n← / → steps (or hover the chart and use the arrow keys)`
          : `${total} on the chart — ← / → steps through them, oldest to newest`
      }
    >
      <button
        onClick={() => onStep(-1)}
        disabled={atStart}
        aria-label="Previous marker"
        className={`${btn} text-text-secondary hover:text-text-primary hover:bg-bg-surface`}
      >
        <ChevronLeft className="w-3.5 h-3.5" />
      </button>
      {/* The readout is the point of the control: what you are parked on, and where that sits in
          the set. With nothing selected it states the SIZE of the set, so the first press is not a
          jump into the dark. */}
      <div className="flex items-center gap-1.5 px-2 h-[22px] border-x border-border-subtle text-[11px] leading-none">
        {current && (
          <span
            className="w-1.5 h-1.5 rounded-full flex-shrink-0"
            style={{ background: current.color }}
          />
        )}
        <span className={current ? 'text-text-primary' : 'text-text-tertiary'}>
          {current ? current.label : 'Step'}
        </span>
        <span className="font-mono tabular-nums text-text-tertiary">
          {current ? `${idx + 1}/${total}` : total}
        </span>
      </div>
      <button
        onClick={() => onStep(1)}
        disabled={atEnd}
        aria-label="Next marker"
        className={`${btn} text-text-secondary hover:text-text-primary hover:bg-bg-surface`}
      >
        <ChevronRight className="w-3.5 h-3.5" />
      </button>
    </div>
  )
}

/** The layers **Deep debug** adds: the context you want behind a trade you are interrogating — the
 *  fib leg its entry was priced off, the break structure it traded off, and the gaps that were live
 *  when it fired. (The fib is a trade sub-layer rather than an overlay group, so it is switched
 *  alongside these rather than listed in here.)
 *
 *  Taken from the panel's own group vocabulary in `overlays.ts` rather than retyped, so a rename
 *  there carries instead of silently turning nothing on.
 *
 *  ⚠ **Order Blocks is deliberately NOT in here** (Aaron's call, 2026-08-03 — "don't add it to the
 *  deep debug yet"). It is a live Analysis row like any other; this preset is a curated set, and a
 *  layer joins it only when it has earned a place in the every-trade reading. That is also why the
 *  indices below are `[0]` and not a spread of the whole list. */
const DEBUG_ON_GROUPS: readonly string[] = [
  STRUCTURE_GROUPS[0], // External Structure — BOS/SOS break lines + the active swing rays
  ANALYSIS_GROUPS[0], // Fair Value Gaps
]

/** **Deep debug** — one row at the top of the Analysis menu, on or off.
 *
 *  Reading a run one trade at a time means the same context every time: the fib leg the entry was
 *  priced off, the structure it broke, the gaps that were open. Three switches across two dropdowns,
 *  set and unset constantly. This is that set, as one toggle.
 *
 *  **It is purely ADDITIVE, and that is what makes it a toggle rather than a mode** (Aaron's call,
 *  and the third shape this control took — it began as a segmented `Winners | Losers` pill, then a
 *  four-way radio, both of which owned the outcome filter and so had to answer "what does OFF
 *  restore?"). It does not touch WHICH trades are drawn: Winners / Losers / Blocked / Missed stay
 *  exactly where the reader set them, and Deep debug just deepens whatever is on screen. So the
 *  question "winners, losers or both" has one answer in one place — the rows below it — instead of
 *  being asked twice and able to disagree.
 *
 *  **On/off is DERIVED from those layers, never remembered** (`debugOn`): switch the gaps off by
 *  hand and the row unticks itself, because deep debug is no longer what is on screen. A remembered
 *  flag is precisely how a label starts claiming something the chart is not doing.
 *
 *  ⚠ **Only layers the run actually CARRIES are counted** — a run with no recorded fibs and no
 *  structure has nothing to deepen, so the row is hidden rather than sitting permanently unticked
 *  (or, worse, permanently ticked because every condition was vacuously true). */

/** "Go to date" — a header pill that opens a date box and scrolls the chart there, so reaching an
 *  old part of a long run is one entry instead of a long drag.
 *
 *  It is a pure INPUT: it collects a date, clamps it to the range the host says is reachable, and
 *  hands back epoch ms. Everything about how the chart gets there belongs to the host.
 *
 *  ⚠ **It carried a `busy` state and a PROGRESS READOUT until 2026-08-06, and both are gone because
 *  the wait they described is gone.** A jump used to page every window between here and the target
 *  over the network — 14 round trips and 90 seconds to reach 2020 — so the pill reported the date
 *  already reached and a bar that filled, which was the right answer to that problem. A jump now
 *  re-slices an array already in the browser. A progress bar for an instant operation is worse than
 *  none: it implies a wait, and it flashes.
 *
 *  `lo`/`hi` set the native `min`/`max`, but the clamp is done in code as well: a native bound stops
 *  the calendar widget and nothing else, so a typed or pasted date walks straight past it (the same
 *  lesson `PeriodPicker` learned about the broker's history floor). */
function GoToDate({ lo, hi, onGo }: { lo: number; hi: number; onGo: (ts: number) => void }) {
  const [open, setOpen] = useState(false)
  const [value, setValue] = useState('')
  const ref = useRef<HTMLDivElement>(null)
  const inputRef = useRef<HTMLInputElement>(null)

  useEffect(() => {
    if (!open) return
    const onDown = (e: MouseEvent) => {
      if (ref.current && !ref.current.contains(e.target as Node)) setOpen(false)
    }
    document.addEventListener('mousedown', onDown)
    return () => document.removeEventListener('mousedown', onDown)
  }, [open])

  // Open on the newest bar's date and select it, so the box is usable from the keyboard alone.
  useEffect(() => {
    if (!open) return
    setValue((v) => v || toIsoDay(hi))
    const id = requestAnimationFrame(() => inputRef.current?.focus())
    return () => cancelAnimationFrame(id)
  }, [open, hi])

  const submit = () => {
    const ts = dayStartMs(value)
    if (ts == null) return
    const clamped = Math.min(Math.max(ts, lo), hi)
    onGo(clamped)
    setOpen(false)
  }

  return (
    <div ref={ref} className="relative">
      <button
        onClick={() => setOpen((o) => !o)}
        title="Go to date"
        className="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-md border border-border-subtle bg-bg-sunken text-[11px] font-medium text-text-secondary transition-colors hover:text-text-primary"
      >
        <CalendarSearch className="w-3.5 h-3.5" />
      </button>
      {open && (
        <div
          className="absolute left-0 mt-1 rounded-md border border-border-subtle bg-bg-surface p-2.5 shadow-lg"
          style={{ zIndex: 50, minWidth: 210 }}
        >
          <div className="text-[10px] uppercase tracking-wide text-text-tertiary">Go to date</div>
          <div className="mt-1.5 flex items-center gap-1.5">
            <input
              ref={inputRef}
              type="date"
              value={value}
              min={toIsoDay(lo)}
              max={toIsoDay(hi)}
              onChange={(e) => setValue(e.target.value)}
              onKeyDown={(e) => {
                if (e.key === 'Enter') {
                  e.preventDefault()
                  submit()
                }
                if (e.key === 'Escape') {
                  e.preventDefault()
                  setOpen(false)
                }
              }}
              className={`flex-1 rounded-md border border-border-subtle bg-bg-sunken px-2 py-1 text-[11px] font-mono text-text-primary focus:border-accent focus:outline-none ${DATE_INDICATOR_CLS}`}
            />
            <button
              onClick={submit}
              disabled={dayStartMs(value) == null}
              className="rounded-md border border-border-subtle bg-bg-sunken px-2 py-1 text-[11px] font-medium text-text-secondary hover:text-text-primary disabled:opacity-40 disabled:hover:text-text-secondary transition-colors"
            >
              Go
            </button>
          </div>
          {/* The reachable span, so a date outside the run reads as out of range before it's typed
              rather than as a jump that silently did nothing. */}
          <div className="mt-1.5 text-[10px] font-mono text-text-tertiary">
            {toIsoDay(lo)} → {toIsoDay(hi)}
          </div>
        </div>
      )}
    </div>
  )
}

// Display-timeframe ladder for the segmented control. Filtered per spec.baseTimeframe so we
// never offer a TF finer than the strategy's own bars (those come from the drill-down below).
const DISPLAY_TFS: readonly TfOption[] = [
  { label: 'M5', min: 5 },
  { label: 'M15', min: 15 },
  { label: 'M30', min: 30 },
  { label: 'H1', min: 60 },
  { label: 'H4', min: 240 },
  { label: 'D1', min: 1440 },
]

// Drill-down timeframes BELOW the chart's base bars — pulled live from the broker (they can't be
// resampled UP from the base). Offered only when an `onRequestCandles` fetcher is wired.
//
// The ladder deliberately covers every intraday TF, not just M1/M5, because the chart's base is NOT
// always the run's own bar size: `chart_spec._fit_timeframe` steps a long run's base UP to keep the
// shipped candle count sane (a 6.5-year 15m run ships H4). Without M15/M30/H1 here, that run could
// not be viewed at the timeframe it actually TRADED — the one view that matters most.
const FETCH_TFS: readonly TfOption[] = [
  { label: 'M1', min: 1 },
  { label: 'M5', min: 5 },
  { label: 'M15', min: 15 },
  { label: 'M30', min: 30 },
  { label: 'H1', min: 60 },
]

// How much history ONE drill-down request asks for, in BARS rather than days — because what a reader
// scrolls through is a count of bars, and the same 45 days is 65,000 M1 bars or 4,300 H1 ones. It
// matches `PAGE_BARS`, so scrolling back at M5 covers the same distance per page as scrolling back
// at the run's own timeframe.
//
// 🔴 **It used to be a fixed lookback ending at the RUN'S LAST BAR, and that is what made M1/M5 look
// broken (fixed 2026-08-06).** Pressing M5 while reading 2020 fetched the newest 270 days and threw
// the reader six years forward with nothing on screen saying so — reproduced from 2020-08-05, which
// landed on 2026-08-06 — while M30 and H1 stayed put because they are resamples of bars already in
// memory. That is exactly the split it was reported as: *"5 or 1 min does nothing, 30 and 1hr work"*.
// The window is anchored on the VIEWPORT now (`runFetch`) and the rest is paged in like any other
// history, so the lookback no longer has to be big enough to reach the feed's edge in one shot.
const FETCH_CHUNK_BARS = 12_000
// Bars → calendar milliseconds. Gold trades ~24/5, so a calendar week carries ~5 days of bars; 1.5
// covers that plus holidays. Overshooting is harmless — the request simply comes back with fewer
// bars than it asked for. UNDERSHOOTING is what would matter: a page arriving short reads exactly
// like the end of the broker's data.
const FETCH_SPAN_SLACK = 1.5
/** Calendar span one drill-down request covers at `min`-minute bars. */
function fetchSpanMs(min: number): number {
  return Math.round(FETCH_CHUNK_BARS * min * 60_000 * FETCH_SPAN_SLACK)
}
/** How far PAST the anchor a drill-down window reaches. The rest is behind it, for the same reason
 *  `goToDate` slices weighted-back: the reader is looking at a moment, and what led to it is the
 *  context that explains it. */
const FETCH_LEAD_FRAC = 0.25

/** A drill-down timeframe's loaded bars and the calendar range they were REQUESTED over.
 *  `edge` = the broker's true oldest bar for this timeframe, once a request has actually reached it
 *  (null = not reached, which is not the same as "there is no more"). */
type DrillWindow = {
  candles: ChartCandle[]
  overlays: ChartOverlay[]
  edge: number | null
  fromMs: number
  toMs: number
}

/** Identity of a structure overlay, for de-duplicating the windows a drill-down pages together.
 *  Two adjacent windows both replay the leg that straddles their boundary, so the same line/label
 *  arrives twice — and a doubled label is visible (the de-collider slides the copy off its anchor). */
/*  ⚠ Span via `'t' in ov`, NOT by listing the point-like `type`s. The first version enumerated
 *  `label`/`vline` and read `.t0`/`.t1` off everything else, which broke the moment `CandleOverlay`
 *  (a third point-like variant) joined the union — a compile error here, but the same shape reaches
 *  for a wrong field silently in any language that would let it. A property test narrows every
 *  present and future variant by what it HAS, so a new one cannot land in the wrong branch. */
function overlayKey(ov: ChartOverlay): string {
  const [a, b] = 't' in ov ? [ov.t, ov.t] : [ov.t0, ov.t1]
  return `${ov.type}|${ov.group}|${a}|${b}|${'price' in ov ? ov.price : ''}|${'text' in ov ? ov.text : ''}`
}

function mergeOverlays(...lists: ChartOverlay[][]): ChartOverlay[] {
  const seen = new Set<string>()
  const out: ChartOverlay[] = []
  for (const list of lists)
    for (const ov of list) {
      const k = overlayKey(ov)
      if (seen.has(k)) continue
      seen.add(k)
      out.push(ov)
    }
  return out
}

/** A server-side failure sentence, trimmed to something a one-line badge can hold.
 *
 *  It keeps the SERVER'S OWN WORDS rather than mapping the error to a phrase of ours, because the
 *  useful half is the specifics: `HistoryFloorError` says *"XAUUSD has no real 1-minute history
 *  before 2018-09-14 on VantageMarkets-Demo (measured, not assumed)"*, and a local paraphrase can
 *  only ever be a vaguer version of that. Drops the exception CLASS (`Foo: `) — that names our
 *  plumbing, not the reader's problem — and the parenthetical asides, which are for whoever reads
 *  the log. The whole sentence stays on the `title`. */
function shortNote(msg: string): string {
  let s = msg
    .replace(/^[A-Za-z_]*Error:\s*/, '')
    .replace(/\s*\([^)]*\)/g, '')
    .trim()
  const stop = s.search(/\.\s/)
  if (stop > 0) s = s.slice(0, stop)
  return s.length > 96 ? `${s.slice(0, 95).trimEnd()}…` : s
}

/** `<input type="date">` value ("YYYY-MM-DD") → epoch ms at LOCAL midnight, or null if malformed.
 *  Local, not UTC, on purpose: klinecharts prints its time axis in the browser's own timezone, so
 *  local midnight is the instant that sits under that date ON SCREEN. `new Date("2026-03-05")`
 *  would parse as UTC and land on the wrong side of the day for anyone west of Greenwich. */
function dayStartMs(iso: string): number | null {
  const m = /^(\d{4})-(\d{2})-(\d{2})$/.exec(iso)
  if (!m) return null
  const d = new Date(Number(m[1]), Number(m[2]) - 1, Number(m[3]))
  return Number.isNaN(d.getTime()) ? null : d.getTime()
}

/** Epoch ms → "YYYY-MM-DD" in LOCAL time — the inverse of `dayStartMs`, for the input's value/min/max.
 *  `toISOString().slice(0,10)` is the tempting one-liner and is wrong here: it converts to UTC first. */
function toIsoDay(ms: number): string {
  const d = new Date(ms)
  const p = (n: number) => String(n).padStart(2, '0')
  return `${d.getFullYear()}-${p(d.getMonth() + 1)}-${p(d.getDate())}`
}

/** Index of the first candle at or after `ts` (ascending list), clamped to the ends. A date with no
 *  bar of its own — a weekend, a holiday — therefore lands on the next trading bar rather than the
 *  previous one, which is what "take me to the 5th" means when the 5th is a Sunday. */
function indexAtOrAfter(candles: ChartCandle[], ts: number): number {
  let lo = 0
  let hi = candles.length - 1
  while (lo < hi) {
    const mid = (lo + hi) >> 1
    if (candles[mid].time < ts) lo = mid + 1
    else hi = mid
  }
  return lo
}

/** "M5" → 5, "M15" → 15, "H1" → 60, "H4" → 240, "D1" → 1440. Falls back to 5. */
function parseTfMinutes(tf: string): number {
  const m = /^([MHD])(\d+)$/.exec(tf.trim().toUpperCase())
  if (!m) return 5
  const n = Number(m[2])
  return m[1] === 'H' ? n * 60 : m[1] === 'D' ? n * 1440 : n
}

/** Merge a roster of `[key, default]` into an existing on/off map: a key the reader has ALREADY
 *  answered keeps THEIR answer, and only a genuinely new one takes the default.
 *
 *  This is what lets paged-in history extend a layer without resetting the panel. The rosters are
 *  DERIVED from the data (overlay groups, sessions, indicators), so every page rebuilds them — and a
 *  plain `setX(defaults)` on each rebuild would silently undo every toggle the reader had set, which
 *  is exactly the "it forgot my settings when it loaded more bars" bug. Returns `prev` unchanged when
 *  nothing moved, so the effect that calls it cannot loop. */
function reconcileToggles(
  prev: Record<string, boolean>,
  roster: Array<[string, boolean]>
): Record<string, boolean> {
  const next: Record<string, boolean> = {}
  for (const [key, dflt] of roster) next[key] = key in prev ? prev[key] : dflt
  const same =
    Object.keys(next).length === Object.keys(prev).length &&
    Object.keys(next).every((k) => next[k] === prev[k])
  return same ? prev : next
}

/** Candle `time` (epoch ms) → klinecharts `timestamp`. Pure field map. */
function candlesToKLine(candles: ChartCandle[]): KLineData[] {
  return candles.map((c) => ({
    timestamp: c.time,
    open: c.open,
    high: c.high,
    low: c.low,
    close: c.close,
    volume: c.volume,
  }))
}

/**
 * Aggregate base-TF candles up to `targetMs`-wide bars for display. Buckets are epoch-aligned
 * (floor(time / targetMs)). Higher-TF candles are DISPLAY aggregations only — the strategy's
 * own TF (spec.baseTimeframe) remains the source of truth. Input must be sorted ascending.
 */
function resample(candles: ChartCandle[], targetMs: number): ChartCandle[] {
  const out: ChartCandle[] = []
  let bucket: ChartCandle | null = null
  let bucketStart = -1
  for (const c of candles) {
    const start = Math.floor(c.time / targetMs) * targetMs
    if (bucket === null || start !== bucketStart) {
      if (bucket) out.push(bucket)
      bucketStart = start
      bucket = {
        time: start,
        open: c.open,
        high: c.high,
        low: c.low,
        close: c.close,
        volume: c.volume,
      }
    } else {
      bucket.high = Math.max(bucket.high, c.high)
      bucket.low = Math.min(bucket.low, c.low)
      bucket.close = c.close
      // ⚠ A bucket is UNDEFINED the moment any base bar in it has no volume, and `?? 0` here was
      // wrong in the direction that hides it: a bar we have no volume for is not a bar that traded
      // nothing, and summing it as zero reports a short total under a name that claims a measurement
      // (the readout would print a confident number for a window we only partly know). Same rule as
      // `backtest/data/resample.py::_volume_sum`, which returns NaN for exactly this case.
      bucket.volume =
        bucket.volume == null || c.volume == null ? undefined : bucket.volume + c.volume
    }
  }
  if (bucket) out.push(bucket)
  return out
}

export default function ChartPanel({
  spec = AUDJPY_FIXTURE,
  height = CHART_HEIGHT,
  onRequestCandles,
  headerLeading,
  headerTrailing,
  toolActions,
  headerClassName,
  showCopy = false,
}: {
  spec?: ChartSpec
  height?: number
  /**
   * Drill-down data source: fetch finer-than-base candles for a bounded window (e.g. 1m under a
   * 15m run, to see a trade's exact entry). When provided, the timeframe control offers sub-base
   * TFs (1m/5m) that pull the visible window live; omitted (e.g. the fixture) → panel behaves as
   * before. `available: false` means the feed could not be ASKED; an empty list under `available: true`
   * means it answered and has nothing that far back. See `ChartPage`.
   */
  onRequestCandles?: (tf: string, fromMs: number, toMs: number) => Promise<ChartPage>
  /**
   * Optional header-bar slots so a host can fold its OWN chrome onto the panel's single top row
   * (rather than stacking a second bar above it). `headerLeading` renders at the far left, before
   * the timeframe control; `headerTrailing` at the far right, after Copy. `headerClassName` is
   * appended to the header row (e.g. a `border-b` when it doubles as a modal title bar). Used by
   * the fullscreen wrapper to put its "Price" title + exit X on the same row as TF/Layers/Copy.
   *
   * `toolActions` is NOT a header slot: it renders on the vertical TOOL STRIP, in the bottom
   * cluster directly above the Chart settings cog. That is where a host ACTION belongs — the strip
   * is inside the panel, so it survives fullscreen (which is `position: fixed` over the whole app
   * and takes the host's own chrome off screen), and it is where a reader already looks for
   * controls that are about the chart rather than about the run. Icon-sized: the strip is 40px.
   */
  headerLeading?: ReactNode
  headerTrailing?: ReactNode
  toolActions?: ReactNode
  headerClassName?: string
  /** Show the snapshot (camera) button. FULLSCREEN ONLY by convention — the whole app puts
   *  copy-as-image on the expanded chart, never the inline one. */
  showCopy?: boolean
}) {
  const containerRef = useRef<HTMLDivElement>(null)
  const chartRef = useRef<Chart | null>(null)
  // The panel root — carries the declared test seams; see them at the render.
  const rootRef = useRef<HTMLDivElement>(null)

  const baseMin = useMemo(() => parseTfMinutes(spec.baseTimeframe), [spec.baseTimeframe])
  const options = useMemo<TfOption[]>(() => {
    const up = DISPLAY_TFS.filter((tf) => tf.min >= baseMin && tf.min % baseMin === 0).map(
      (tf) => ({ label: tf.label, min: tf.min })
    )
    const base: TfOption[] = up.length
      ? up
      : [{ label: spec.baseTimeframe.toUpperCase(), min: baseMin }]
    // Sub-base TFs (below the run's own bars) are DRILL-DOWN — can't be resampled from the base,
    // so only offered when a fetcher is wired to pull them live.
    const down: TfOption[] = onRequestCandles ? FETCH_TFS.filter((tf) => tf.min < baseMin) : []
    return [...down, ...base]
  }, [baseMin, spec.baseTimeframe, onRequestCandles])

  // The timeframe the run actually TRADED — the chart's default view, because that is the only
  // timeframe its trades and blocked setups line up with bar-for-bar. It is often FINER than the
  // shipped `baseTimeframe` (the emitter steps a long run up to keep the payload sane), in which case
  // opening on it means opening in drill-down. Falls back to the shipped bars when the run TF isn't
  // offered — no fetcher wired, or a spec cached before `runTimeframe` existed.
  const openMin = useMemo(() => {
    const want = parseTfMinutes(spec.runTimeframe ?? spec.baseTimeframe)
    return options.some((o) => o.min === want) ? want : baseMin
  }, [spec.runTimeframe, spec.baseTimeframe, options, baseMin])

  // Selected display TF (minutes). Component-local UI state.
  const [selectedMin, setSelectedMin] = useState<number>(() => openMin)
  // Timeframe dropdown (TradingView-style) open state + click-outside to close.
  const [tfOpen, setTfOpen] = useState(false)
  const tfRef = useRef<HTMLDivElement>(null)
  useEffect(() => {
    if (!tfOpen) return
    const onDown = (e: MouseEvent) => {
      if (tfRef.current && !tfRef.current.contains(e.target as Node)) setTfOpen(false)
    }
    document.addEventListener('mousedown', onDown)
    return () => document.removeEventListener('mousedown', onDown)
  }, [tfOpen])

  // Reset selection to the run's own TF when the spec (and thus its options) changes.
  useEffect(() => {
    setSelectedMin(openMin)
  }, [openMin])

  // Drill-down (sub-base) fetch state. `isFetchMode` = a TF finer than the run's own bars is
  // selected; then `fetched` (pulled live for the visible window) replaces the resampled candles.
  const [fetched, setFetched] = useState<ChartCandle[]>([])
  // The drill-down window's OWN structure overlays, computed by the backend on the bars it served.
  // Replaces `spec.overlays` while a finer timeframe is showing — see `allOverlays`.
  const [drillOverlays, setDrillOverlays] = useState<ChartOverlay[]>([])
  const [fetchStatus, setFetchStatus] = useState<'idle' | 'loading' | 'ok' | 'empty' | 'error'>(
    'idle'
  )
  // WHY a drill-down came back with nothing, and it is two completely different facts:
  // `offline` = the feed could not be reached (`available: false` — the MT5 agent or its terminal is
  // down), `no-history` = the feed answered and the broker simply has no bars that far back at that
  // timeframe. ⚠ **They were one message until 2026-08-07** — *"no data here (feed offline, or none
  // this far back?)"* — a sentence that asks the reader the question the response had already
  // answered, and this repo's *never let "no" and "cannot ask" be the same value* rule broken by a
  // string rather than by a type. `available` has been on the payload the whole time and nothing read it.
  const [fetchNote, setFetchNote] = useState<string | null>(null)
  // The broker's TRUE oldest bar for the active drill-down TF (M1 ~30d back, M5 ~240d) — drawn as a
  // red dashed "no earlier data" line. null = no hard edge (feed has more, or nothing loaded).
  const [dataEdge, setDataEdge] = useState<{ ts: number; tf: number } | null>(null)
  // In-session cache per drill-down TF, and it carries the RANGE it covers as well as the bars.
  // ⚠ The range is the load-bearing half: a completed run's bars never change, but a drill-down no
  // longer holds one fixed window — it is anchored on where the reader is and grown by paging, so a
  // cache keyed on the timeframe ALONE would answer a drill at 2020 with the window pulled for 2026.
  // A hit therefore requires the anchor to fall inside what was actually fetched.
  const fetchCacheRef = useRef<Map<number, DrillWindow>>(new Map())
  const fetchTokenRef = useRef(0)
  const isFetchMode = onRequestCandles != null && selectedMin < baseMin
  // Are the bars on screen the ones the spec's per-bar layers were computed on? A resample up and a
  // drill-down both make that false, and the candle-repaint layer is gated on it — see
  // `analysisGroups`. Zone layers (gaps, blocks) are price/time and do not care.
  const atBaseTf = selectedMin === baseMin
  // Read by the load-data callback and by `goToDate`, both of which are registered once and would
  // otherwise close over the first render's timeframe for ever.
  const isFetchModeRef = useRef(isFetchMode)
  useEffect(() => {
    isFetchModeRef.current = isFetchMode
  }, [isFetchMode])
  const selectedMinRef = useRef(selectedMin)
  useEffect(() => {
    selectedMinRef.current = selectedMin
  }, [selectedMin])
  const fetchedRef = useRef(fetched)
  useEffect(() => {
    fetchedRef.current = fetched
  }, [fetched])
  const drillOverlaysRef = useRef(drillOverlays)
  useEffect(() => {
    drillOverlaysRef.current = drillOverlays
  }, [drillOverlays])

  // The candles HANDED TO KLINECHARTS: the newest `APPLIED_BARS` of the spec, grown backwards as you
  // scroll left. The spec itself carries the WHOLE run (2026-08-06) — this is the window applied to
  // the chart, not the window we hold.
  //
  // 🔴 **The chart must never be handed the whole run, and this was MEASURED after being got wrong.**
  // Shipping full history and applying all of it froze the main thread for **30.8 seconds** on a
  // 155,798-bar run, against **2.2s** for the 33k-bar capped spec it replaced — klinecharts lays
  // every candle out synchronously on `applyNewData`, and the app is dead for the duration.
  //
  // ⚠ **A prior measurement said candles were nearly free and it was measuring something else:**
  // eleven PREPENDS of 12k-bar chunks into an existing chart totalled 682 ms. Prepending into a
  // built chart and building one from 155k bars are different operations, and only the second is
  // what "just ship everything" does. Read a per-bar cost off the operation you are about to
  // perform, not off a neighbouring one.
  //
  // What the full spec buys is that growing this window is now a SLICE, not a fetch — see
  // `loadOlder`. So the reader still reaches every bar of the run, and reaching them costs
  // milliseconds instead of a 7-second round trip per page.
  const [baseCandles, setBaseCandles] = useState<ChartCandle[]>(() =>
    spec.candles.slice(-APPLIED_BARS)
  )
  useEffect(() => {
    setBaseCandles(spec.candles.slice(-APPLIED_BARS))
  }, [spec.candles])
  // Read by the load callback, which is registered once on mount and would otherwise close over the
  // first render's candles forever.
  const baseCandlesRef = useRef(baseCandles)
  useEffect(() => {
    baseCandlesRef.current = baseCandles
  }, [baseCandles])

  // 🟢 **There is no PAGED ANALYSIS any more, and its absence is the point (2026-08-06).**
  // Everything on this chart except the trades used to be emitted per-window — the spec's overlays,
  // blocks and misses all stopped at the shipped candles — so scrolling past that boundary silently
  // emptied every layer while its toggle still read ON. The 2026-08-02 fix answered that by fetching
  // each page's analysis and merging it (`pagedAnalysis` / `mergePageAnalysis`, both now deleted).
  //
  // The spec now carries the WHOLE run's analysis, built once, so the hole cannot open: there is no
  // boundary left for a layer to stop at. That also removes the merge's own hazards — a page's
  // overlays arriving out of order, an id colliding across windows, and the reconcile-vs-re-seed
  // trap that could switch the reader's layers off mid-scroll.
  //
  // ⚠ `reconcileToggles` and `seededNoiseRef` below are KEPT even though only a new spec can move
  // their rosters now. They encode "keep an answer the reader has already given", which is a rule
  // about the reader, not about paging.

  // The DISPLAY-side candles, memoized apart from the drill-down state on purpose.
  //
  // 🔴 **Folding this into `displayCandles` is what made a timeframe switch lose the reader's place
  // (measured 2026-08-07).** `displayCandles` lists `fetched` among its dependencies, and the
  // drill-down effect calls `setFetched([])` on every timeframe change — a FRESH empty array each
  // time — so switching M15 → H1 recomputed the resample a second time, and the second
  // `applyNewData` re-parked the view on the newest bar AFTER `pendingJumpRef` had already scrolled
  // it to the right place and been consumed. **Traced by logging the applies, not by reading the
  // effect**: `apply n=3002` → `flush 2020-08-05` → `apply n=3002` again, landing 42 days out.
  // Keyed only on what a resample actually depends on, the second apply cannot happen.
  const resampled = useMemo(
    () => (selectedMin === baseMin ? baseCandles : resample(baseCandles, selectedMin * 60_000)),
    [baseCandles, selectedMin, baseMin]
  )

  const displayCandles = useMemo(() => {
    // In drill-down, show the SHIPPED bars until the finer ones land. They arrive in the spec, so
    // they paint on the first frame; the drill-down is a network pull. Returning `fetched` straight
    // out means an empty chart for the length of that pull — and since the panel now OPENS in
    // drill-down (the run's own TF is usually finer than the shipped bars), that turned every chart
    // open into a blank screen where it used to be instant. Coarse bars now, correct bars in a
    // moment, never nothing.
    if (isFetchMode) return fetched.length ? fetched : baseCandles
    return resampled
  }, [isFetchMode, fetched, baseCandles, resampled])
  // True while the chart is showing shipped bars that are NOT the selected TF — the header says so,
  // because bars that don't match the TF button would otherwise be a silent lie.
  const showingPlaceholder = isFetchMode && fetched.length === 0 && baseCandles.length > 0
  // A drill-down request is in flight. Drives the spinner on the timeframe button and the badge over
  // the plot — see the badge for why an 11px header note was not enough.
  const drillPending = isFetchMode && fetchStatus === 'loading'
  // A drill-down that finished with nothing to show. It gets the SAME badge as the loading state,
  // because it is the answer to the same question the reader asked — and because the chart is still
  // showing the coarser bars underneath, which without a visible line is a silent lie about what
  // timeframe is on screen.
  const drillUnavailable = isFetchMode && (fetchStatus === 'empty' || fetchStatus === 'error')

  // Time bounds of the LOADED candles (ascending). Overlays anchored OUTSIDE this range must not be
  // drawn: klinecharts clamps an out-of-range point to the plot edge, so in a drill-down TF (whose
  // data only goes back to the broker's edge) every older trade/session/day-break piles up in the
  // empty no-data region. Only the red DATA_EDGE line lives out there. Null when no candles loaded.
  const [loadedLoTs, loadedHiTs] = useMemo<[number | null, number | null]>(
    () =>
      displayCandles.length
        ? [displayCandles[0].time, displayCandles[displayCandles.length - 1].time]
        : [null, null],
    [displayCandles]
  )

  const drillLabel = (min: number) => FETCH_TFS.find((tf) => tf.min === min)?.label ?? `M${min}`

  // Pull ONE window of a drill-down TF, anchored on `anchorMs` — the moment the reader is actually
  // looking at, never the run's tail. Older bars arrive by PAGING (`drillOlder`), exactly as they do
  // at the run's own timeframe, so this is a chunk rather than a whole depth.
  //
  // Returns the candles it applied, or null if the request was superseded, failed, or was answered
  // from cache with the identical array — `goToDate` needs to know whether a redraw is coming.
  const runFetch = async (
    min: number,
    anchorMs: number,
    force = false
  ): Promise<ChartCandle[] | null> => {
    if (!onRequestCandles) return null
    const cached = fetchCacheRef.current.get(min)
    if (!force && cached && anchorMs >= cached.fromMs && anchorMs <= cached.toMs) {
      setFetched(cached.candles)
      setDrillOverlays(cached.overlays)
      setDataEdge(cached.edge != null ? { ts: cached.edge, tf: min } : null)
      setFetchStatus(cached.candles.length ? 'ok' : 'empty')
      setFetchNote(null)
      return cached.candles === fetchedRef.current ? null : cached.candles
    }
    const span = fetchSpanMs(min)
    const runEnd = spec.candles[spec.candles.length - 1]?.time ?? Date.now()
    // Never reach past the run's own last bar: there is nothing out there to draw, and the lead would
    // simply be spent on empty calendar instead of on bars the reader can scroll into.
    const to = Math.min(runEnd, anchorMs + Math.round(span * FETCH_LEAD_FRAC))
    const from = to - span
    const token = ++fetchTokenRef.current
    setFetchStatus('loading')
    try {
      const res = await onRequestCandles(drillLabel(min), from, to)
      if (token !== fetchTokenRef.current) return null // a newer fetch superseded this one
      const edge = res.hardEdge && res.dataStartMs != null ? res.dataStartMs : null
      fetchCacheRef.current.set(min, {
        candles: res.candles,
        overlays: res.overlays ?? [],
        edge,
        fromMs: from,
        toMs: to,
      })
      setFetched(res.candles)
      setDrillOverlays(res.overlays ?? [])
      setDataEdge(edge != null ? { ts: edge, tf: min } : null)
      setFetchStatus(res.candles.length ? 'ok' : 'empty')
      // The SERVER's own sentence, verbatim — it is the only one that can name the date. Asking
      // for M1 before the broker's measured floor comes back with "XAUUSD has no real 1-minute
      // history before 2018-09-14 on VantageMarkets-Demo (measured, not assumed)", which is the
      // whole answer; anything this side could write instead would be a vaguer paraphrase of it.
      setFetchNote(res.candles.length ? null : (res.feedError ?? null))
      return res.candles
    } catch {
      if (token === fetchTokenRef.current) setFetchStatus('error')
      return null
    }
  }

  // `runFetch` is re-created every render (it reads `spec.candles`), while `drillTo` and the load
  // callback are registered once — so they go through this rather than closing over the first one.
  const runFetchRef = useRef(runFetch)
  runFetchRef.current = runFetch

  // ── Paging a DRILL-DOWN timeframe ────────────────────────────────────────────────────────────
  // The mirror of `loadOlder`/`loadNewer` for bars that are not in the spec: they come off the feed
  // one `fetchSpanMs` chunk at a time, and the accumulated list is written back into the cache so a
  // re-select restores everything the reader had already scrolled through.
  //
  // ⚠ **Without this, anchoring the fetch alone would only MOVE the wall.** A window that stops mid
  // history has no `hardEdge`, so the red "no earlier data" line correctly does not draw — leaving a
  // blank strip with nothing saying why, which is the one thing this panel's paging markers exist to
  // prevent.
  const drillOlder = useCallback(async (): Promise<{ bars: ChartCandle[]; more: boolean }> => {
    const min = selectedMinRef.current
    const loaded = fetchedRef.current
    const oldest = loaded[0]?.time
    if (!onRequestCandles || oldest == null) return { bars: [], more: false }
    const cached = fetchCacheRef.current.get(min)
    // Already at the broker's true oldest bar — the red edge is drawn there and there is nothing behind it.
    if (cached?.edge != null && oldest <= cached.edge) return { bars: [], more: false }
    const span = fetchSpanMs(min)
    const from = oldest - span
    const res = await onRequestCandles(drillLabel(min), from, oldest)
    // Strictly older, so a feed answering with an overlapping window cannot duplicate a bar.
    const bars = res.candles.filter((c) => c.time < oldest)
    const edge = res.hardEdge && res.dataStartMs != null ? res.dataStartMs : (cached?.edge ?? null)
    if (edge != null) setDataEdge({ ts: edge, tf: min })
    // The older window replays its own structure; merge rather than replace, or scrolling left
    // would drop the legs already on screen.
    const mergedOld = mergeOverlays(res.overlays ?? [], drillOverlaysRef.current)
    setDrillOverlays(mergedOld)
    fetchCacheRef.current.set(min, {
      candles: [...bars, ...loaded],
      overlays: mergedOld,
      edge,
      fromMs: Math.min(from, cached?.fromMs ?? from),
      toMs: cached?.toMs ?? oldest,
    })
    // A hard edge in this answer means the page reached it, so there is nothing left to ask for.
    return { bars, more: bars.length > 0 && !(res.hardEdge && res.dataStartMs != null) }
  }, [onRequestCandles])

  const drillNewer = useCallback(async (): Promise<{ bars: ChartCandle[]; more: boolean }> => {
    const min = selectedMinRef.current
    const loaded = fetchedRef.current
    const newest = loaded[loaded.length - 1]?.time
    const runEnd = spec.candles[spec.candles.length - 1]?.time
    if (!onRequestCandles || newest == null || runEnd == null || newest >= runEnd) {
      return { bars: [], more: false }
    }
    const to = Math.min(runEnd, newest + fetchSpanMs(min))
    const res = await onRequestCandles(drillLabel(min), newest, to)
    const bars = res.candles.filter((c) => c.time > newest)
    const cached = fetchCacheRef.current.get(min)
    const mergedNew = mergeOverlays(drillOverlaysRef.current, res.overlays ?? [])
    setDrillOverlays(mergedNew)
    fetchCacheRef.current.set(min, {
      candles: [...loaded, ...bars],
      overlays: mergedNew,
      edge: cached?.edge ?? null,
      fromMs: cached?.fromMs ?? newest,
      toMs: Math.max(to, cached?.toMs ?? to),
    })
    return { bars, more: bars.length > 0 && to < runEnd }
  }, [onRequestCandles, spec.candles])

  // ── Paging older history (scroll left) — an IN-MEMORY SLICE since 2026-08-06 ─────────────────
  // klinecharts asks for more the moment you scroll past the left edge. This used to answer with a
  // network round trip per page; the spec now carries the whole run, so it answers by extending the
  // applied window backwards over an array that is already in the browser.
  //
  // ✅ **That is the change the whole pass was for.** MEASURED before: a page cost ~7.2s (of which
  // ~60% was the server replaying that window's structure and gap engines) and a six-year jump was
  // 14 pages and **90.3 seconds**. The analysis no longer has to be replayed per window at all,
  // because the spec was built with all of it once — so the cost of reaching a date collapses to
  // klinecharts re-laying the bars.
  //
  // ⚠ **It keeps the async signature deliberately.** The load callback, the jump loop and the
  // `LOADING_EDGE` overlay are all written around a page that may take time, and a drill-down TF
  // still genuinely fetches. Making this synchronous would mean rewriting three call sites for a
  // function that returns in under a millisecond either way.
  //
  // 🔴 MEASURED 2026-08-06, and it is where a deep jump's minute actually goes: the ANALYSIS is
  // ~60% of a page. On run 211384ddbea4 at M15 a 175d page is 2.61s bare against 6.63s with
  // `analysis=true`, and an 875d one is 8.24s against 20.23s. So a six-year jump is ~90s today and
  // would be ~35s if the intermediate pages fetched BARS ONLY. That change is not made here,
  // because it trades away the guarantee the 2026-08-02 fix bought — every layer reaching exactly
  // as far back as the bars do — and a page scrolled past would draw no overlays with its toggle
  // still ON, which is the defect that fix existed to remove. Doing it safely means backfilling
  // each skipped window's analysis after the jump lands, and that is its own change.
  const loadOlder = useCallback(async (): Promise<{ bars: ChartCandle[]; more: boolean }> => {
    if (isFetchMode) return drillOlder()
    const all = spec.candles
    const oldest = baseCandlesRef.current[0]?.time
    // Nothing loaded, or the applied window already starts at the run's first bar.
    if (oldest == null || !all.length || oldest <= all[0].time) return { bars: [], more: false }
    // Binary search rather than `findIndex`: this runs per page on a 155k-bar array, and a jump
    // runs it once per page in a loop.
    let lo = 0,
      hi = all.length - 1,
      idx = all.length
    while (lo <= hi) {
      const mid = (lo + hi) >> 1
      if (all[mid].time < oldest) lo = mid + 1
      else {
        idx = mid
        hi = mid - 1
      }
    }
    if (idx <= 0) return { bars: [], more: false }
    const from = Math.max(0, idx - PAGE_BARS)
    return { bars: all.slice(from, idx), more: from > 0 }
  }, [spec.candles, isFetchMode, drillOlder])
  const loadOlderRef = useRef(loadOlder)
  useEffect(() => {
    loadOlderRef.current = loadOlder
  }, [loadOlder])

  // The mirror of `loadOlder`, and it exists BECAUSE a jump re-centres (see `goToDate`). Before the
  // spec carried the whole run, the applied window always ran to the newest bar, so "newer than what
  // is loaded" could not happen and klinecharts' Backward branch was answered with nothing. Landing
  // a jump in 2020 puts the window's RIGHT edge mid-history, and without this the reader hits an
  // invisible wall scrolling back toward the present.
  const loadNewer = useCallback(async (): Promise<{ bars: ChartCandle[]; more: boolean }> => {
    if (isFetchMode) return drillNewer()
    const all = spec.candles
    const loaded = baseCandlesRef.current
    const newest = loaded[loaded.length - 1]?.time
    if (newest == null || !all.length || newest >= all[all.length - 1].time)
      return { bars: [], more: false }
    let lo = 0,
      hi = all.length - 1,
      idx = all.length
    while (lo <= hi) {
      const mid = (lo + hi) >> 1
      if (all[mid].time <= newest) lo = mid + 1
      else {
        idx = mid
        hi = mid - 1
      }
    }
    if (idx >= all.length) return { bars: [], more: false }
    const to = Math.min(all.length, idx + PAGE_BARS)
    return { bars: all.slice(idx, to), more: to < all.length }
  }, [spec.candles, isFetchMode, drillNewer])
  const loadNewerRef = useRef(loadNewer)
  useEffect(() => {
    loadNewerRef.current = loadNewer
  }, [loadNewer])
  // Set when a candle change came from a PAGE rather than a TF/spec switch. klinecharts has already
  // merged those bars and holds the scroll position; re-running `applyNewData` would throw both away
  // and snap the view back — the jump-on-every-page bug.
  const skipApplyRef = useRef(false)
  // True while a scroll-left page is in flight. Drives the on-chart LOADING_EDGE marker: scrolling
  // past the loaded bars gives a blank strip that otherwise reads exactly like the end of the run's
  // data, with nothing saying more is coming.
  const [pagingOlder, setPagingOlder] = useState(false)

  // ── Go to date ───────────────────────────────────────────────────────────────
  // True while a jump is pulling older pages in. Shown on the pill, and it parks klinecharts' own
  // scroll-left paging so the two can't both be splicing onto the front of the same array.
  const jumpingRef = useRef(false)
  // How far back the jump has actually GOT, so the wait can report itself.
  //
  // 🔴 A deep jump is a minute of wall clock — MEASURED at 14 pages / ~93s for six years at M15 —
  // and until this landed the only sign of life was a static `loading 2020-01-05…`. A label that
  // never changes for 90 seconds is indistinguishable from a hang, which is exactly how it was
  // reported. The loop knows the answer at every step: it can see where the oldest loaded bar has
  // reached, and it knows where it was told to stop.
  //
  // ⚠ Progress is measured in TIME COVERED, not in pages completed. A page span is clamped at the
  // run's own start, so the last page is usually short — counting pages would sit at "3 of 4" and
  // then finish, and a page count also cannot be known in advance when the feed decides how far
  // back it can answer.
  // A jump target waiting for its bars. Set only when the jump had to PAGE — the redraw that follows
  // is what flushes it; a jump inside the loaded window scrolls straight away.
  const pendingJumpRef = useRef<number | null>(null)

  // Park the target bar in the MIDDLE of the plot, not on the right edge where `scrollToDataIndex`
  // leaves it: a date with nothing after it reads as the end of the run's data. Scrolling to
  // `target + half a screen` puts the target centre-stage with its lead-up still visible.
  const scrollToTs = useCallback((ts: number, candles: ChartCandle[]) => {
    const chart = chartRef.current
    if (!chart || candles.length === 0) return
    const idx = indexAtOrAfter(candles, ts)
    const range = chart.getVisibleRange()
    const half = Math.max(1, Math.floor((range.to - range.from) / 2))
    chart.scrollToDataIndex(Math.min(candles.length - 1, idx + half))
  }, [])

  const drillSeqRef = useRef(0)
  // Whether the previous render was in drill-down — the leaving-drill branch needs to fire on the
  // TRANSITION, not on every render that happens not to be a drill-down (which includes the mount).
  const wasFetchRef = useRef(false)

  // Change timeframe and STAY WHERE THE READER IS — Aaron's requirement, in his words: *"I should be
  // able to switch from any time frame to any time frame."*
  //
  // A timeframe switch is a real data swap, so the apply effect calls `applyNewData`, which parks the
  // view on the NEWEST bar it was handed. While the applied window ran to the present that was
  // invisible; since a jump can leave the window's right edge mid-history, it means every switch
  // throws you forward to the end of whatever is loaded — measured at ~6 weeks after a jump to
  // 2020-08-05. It is the same complaint as the drill-down teleport, one control over.
  //
  // The two refs `goToDate` already owns do the work: `jumpingRef` holds paging off across the swap,
  // and `pendingJumpRef` puts the view back on the bar that was under the middle of the plot.
  //
  // ⚠ **This is NOT the runaway-paging guard described below.** That one was written against a
  // 90-second freeze that turned out not to exist, and was removed. This is a positioning fix for a
  // behaviour that was measured, and it happens to use the same two refs.
  // 🔴 **The release below is not belt-and-braces, and the check that found it is the one that
  // matters most in this file.** `pendingJumpRef` is consumed by an effect keyed on `displayCandles`,
  // and a timeframe switch does NOT always change that identity — going from a drill-down back to
  // the run's own timeframe hands back the very same `baseCandles` array. So the effect never fires,
  // the guard is never dropped, and `goToDate` returns immediately on every later call: **the chart
  // silently refuses every jump and every page for the rest of the session, looking perfectly
  // healthy.** Two frames is long enough for a real re-apply to have consumed it.
  const pickTimeframe = useCallback(
    (min: number) => {
      const centre = viewCentreRef.current
      if (centre != null) {
        jumpingRef.current = true
        pendingJumpRef.current = centre
        // ⚠ The hand-off is by SEQUENCE, not by comparing the pending timestamp — and the first
        // version compared the timestamp, which broke the drill-down that had been working. Entering
        // a drill-down, `drillTo` runs in an effect (before the frames below) and sets its own pending
        // jump to the SAME instant, since both anchor on the viewport centre. So the value test could
        // not tell "nobody handled it" from "the drill owns it now", and this fallback consumed the
        // drill's landing mid-fetch — leaving the view parked on the applied right edge when the bars
        // finally arrived.
        const seq = drillSeqRef.current
        requestAnimationFrame(() =>
          requestAnimationFrame(() => {
            if (drillSeqRef.current !== seq) return // a drill-down took ownership
            if (pendingJumpRef.current == null) return // a redraw came and the flush handled it
            pendingJumpRef.current = null
            scrollToTs(centre, displayCandlesRef.current)
            jumpingRef.current = false
          })
        )
      }
      setSelectedMin(min)
    },
    [scrollToTs]
  )

  // ⚠ **A suspected runaway-paging freeze on a DISPLAY timeframe switch was investigated on
  // 2026-08-06 and NOT REPRODUCED — recorded here so the next reader does not re-derive it.** A
  // Playwright click on M30 after a jump to 2020 timed out past 90 seconds, which is what a frozen
  // main thread looks like from outside, and the plausible mechanism was there: a switch re-applies,
  // `applyNewData` parks on the newest loaded bar, and after a jump that bar is mid-history, so
  // klinecharts could ask `loadNewer` for page after page from the edge it had just parked on.
  // **The page is not frozen and does not walk forward.** An in-page 50 ms timer logged 2,407
  // samples over 120 s — i.e. it never missed a tick — and the applied window went from
  // `2020-03-19 00:15 .. 2020-09-20 23:30` to `00:00 .. 23:30`, which is the M30 resample and
  // nothing else. It reproduces identically at HEAD, so it is not the drill-down change either.
  // The blocked click is the harness; `dispatchEvent` applies the switch fine. **No guard was added,
  // because the bug it would have guarded does not exist.**

  // Fetch a drill-down window around `target` and LAND ON IT, borrowing `goToDate`'s own machinery.
  // Used both by a date jump in drill-down and by the timeframe switch itself.
  //
  // 🔴 **The scroll is not a nicety, and driving it is what showed why (2026-08-06).** Anchoring the
  // fetch alone already keeps the reader in the right YEAR, but `applyNewData` parks the view on the
  // newest bar of whatever it was handed — so pressing M5 while reading 2020-08-05 landed on
  // 2020-10-22, two and a half months past the moment being read, and klinecharts then requested a
  // NEWER page from the edge it had parked on, walking it further away and paying a round trip to do
  // it. `jumpingRef` refuses that page and the flush effect puts the view on the target instead.
  const drillTo = useCallback(async (min: number, target: number, force: boolean) => {
    // ⚠ Sequenced, because the release below is destructive. Switch M5 → M1 while the M5 request is
    // still out and the older call returns null (superseded by the token in `runFetch`) — without
    // this it would then clear the NEWER call's `pendingJumpRef` and drop its `jumpingRef`, so the
    // second switch would land wherever `applyNewData` parked it and paging would reopen mid-swap.
    const seq = ++drillSeqRef.current
    jumpingRef.current = true
    pendingJumpRef.current = target
    const got = await runFetchRef.current(min, target, force)
    if (seq !== drillSeqRef.current) return // a newer drill owns the guard now
    // Nothing new applied (superseded, refused, or the feed had nothing back there) ⇒ no redraw is
    // coming, so the flush effect will never run and the guard has to be released here, or every
    // later jump and every page is refused for the rest of the session.
    if (!got || !got.length) {
      pendingJumpRef.current = null
      jumpingRef.current = false
    }
  }, [])

  // The reachable span the date box bounds itself to: everything APPLIED, plus everything the pager
  // can still reach.
  //
  // ⚠ It used to gate the reachable half on `onRequestCandles` — correct while paging was a network
  // call through that fetcher, and wrong since paging became a slice of `spec.candles` (2026-08-06).
  // A host that wires no fetcher can still page the whole run; only the DRILL-DOWN needs one.
  //
  // ⚠ **A drill-down reaches the whole run too, as of the anchored-fetch fix.** It used to be bounded
  // by the one window that had been fetched, which was honest then and would now be a box refusing
  // dates the chart can perfectly well go to. The floor is the broker's own edge for this timeframe
  // once a request has MEASURED one — never a guess at how much M1 history the feed keeps.
  const jumpRange = useMemo(() => {
    if (loadedLoTs == null || loadedHiTs == null) return null
    const runEnd = spec.candles[spec.candles.length - 1]?.time ?? loadedHiTs
    const edge = isFetchMode && dataEdge?.tf === selectedMin ? dataEdge.ts : null
    const start = edge ?? spec.historyStartMs ?? null
    return {
      lo: start != null ? Math.min(start, loadedLoTs) : loadedLoTs,
      hi: Math.max(loadedHiTs, isFetchMode ? runEnd : loadedHiTs),
    }
  }, [
    loadedLoTs,
    loadedHiTs,
    isFetchMode,
    spec.historyStartMs,
    spec.candles,
    dataEdge,
    selectedMin,
  ])

  // 🟢 **A jump RE-CENTRES the applied window; it does not grow it from the right edge.** That is
  // the difference between a jump being instant and a jump being the slowest thing on the page.
  //
  // MEASURED, and the middle row is the one worth keeping — it is what this looked like after the
  // spec started carrying the whole run but before the window was re-centred:
  //
  //   paging each window over the network, 14 round trips          90.3 s
  //   paging in memory, but still growing to cover target..now     47.6 s
  //   re-centring on the target                                    see `tests/chart-paging.spec.ts`
  //
  // The 47.6s is entirely one `applyNewData`: growing to cover 2020→now IS the whole run, so the
  // jump handed klinecharts 155,798 bars and paid the 30-second layout. Slicing around the target
  // hands it `APPLIED_BARS` instead, and the cost stops depending on how far back you asked to go.
  //
  // ⚠ **This is why `loadNewer` had to exist.** Landing mid-history puts the window's right edge in
  // the past, so scrolling back toward the present now needs a real answer.
  const goToDate = useCallback(
    async (target: number) => {
      if (!chartRef.current || jumpingRef.current) return
      // A drill-down holds a fetched WINDOW rather than a slice of the spec, so a date outside it is a
      // re-anchored request rather than a re-slice. Before 2026-08-06 this branch did not exist and the
      // jump silently degraded to a scroll inside whatever the one-shot fetch happened to hold.
      if (isFetchModeRef.current) {
        const f = fetchedRef.current
        if (f.length > 0 && target >= f[0].time && target <= f[f.length - 1].time) {
          scrollToTs(target, f)
          return
        }
        await drillTo(selectedMinRef.current, target, true)
        return
      }
      const all = spec.candles
      const loaded = baseCandlesRef.current
      const inWindow =
        loaded.length > 0 && target >= loaded[0].time && target <= loaded[loaded.length - 1].time
      // Already applied, or nothing to slice ⇒ this is a plain scroll.
      if (inWindow || !all.length) {
        scrollToTs(target, displayCandles)
        return
      }
      // First bar at or after the target. The target may be a weekend or a holiday, which has no bar
      // of its own — landing on the next trading bar is what "take me to the 5th" means then.
      let lo = 0,
        hi = all.length - 1,
        idx = all.length - 1
      while (lo <= hi) {
        const mid = (lo + hi) >> 1
        if (all[mid].time < target) lo = mid + 1
        else {
          idx = mid
          hi = mid - 1
        }
      }
      // Weighted back, not centred: the reader asked to see a date, and what LED to it is the context
      // that explains it. `scrollToTs` then centres the bar itself within this slice.
      const from = Math.max(0, idx - Math.floor(APPLIED_BARS * 0.75))
      const slice = all.slice(from, Math.min(all.length, from + APPLIED_BARS))
      // `jumpingRef` shuts the load callback while the re-apply and its scroll are in flight, so a
      // page cannot splice into the same array this is replacing. It is cleared by the scroll flush,
      // one frame after the view has left the edge the re-apply parked it on.
      //
      // ⚠ **An earlier version of this comment claimed the guard was load-bearing against the jump
      // walking FORWARD off its own target — `applyNewData` snapping to the right edge, klinecharts
      // asking for a Backward page, `loadNewer` answering — and cited a jump to 2020-06-01 landing on
      // 2021-01-19. That claim is WITHDRAWN: it does not reproduce.** Removing the guard entirely and
      // probing the applied window once a second for 12s after the same jump gives a dead-stable
      // `2020-01-10 .. 2020-07-16` (2026-08-06). The reason is this slice: the target is centred with
      // ~3,000 bars of window to its right, so the viewport never reaches the newest loaded bar and
      // the Backward request is never made. The guard stays because a re-apply racing a page is a
      // real hazard and it costs nothing — but it is defence, not a fix for an observed bug, and
      // `tests/chart-paging.spec.ts` deliberately does not pretend to cover it.
      jumpingRef.current = true
      // NOT `skipApplyRef` — klinecharts has never seen this window, so it must re-apply. The scroll
      // therefore waits for the redraw instead of running now (`pendingJumpRef`, flushed by the
      // effect declared after the apply effect).
      pendingJumpRef.current = target
      baseCandlesRef.current = slice
      setBaseCandles(slice)
    },
    [spec.candles, displayCandles, scrollToTs]
  )

  // Session boxes are derived from the BASE candles (high/low envelope is TF-invariant) and
  // anchored by timestamp, so they stay put across timeframe switches. Show on ALL candle days.
  const sessionBoxes = useMemo(
    () =>
      spec.sessions.map((s) => ({
        name: s.name,
        color: s.color,
        windows: sessionWindows(baseCandles, s, spec.brokerGmtOffsetHours),
      })),
    [baseCandles, spec.sessions, spec.brokerGmtOffsetHours]
  )

  // Per-session visibility (component-local UI state). Defaults all OFF — the chart opens on just
  // the trades; sessions are opt-in from the on-chart legend. Resets with the spec.
  const [sessionsOn, setSessionsOn] = useState<Record<string, boolean>>(
    () =>
      Object.fromEntries(spec.sessions.map((s) => [s.name, false] as [string, boolean])) as Record<
        string,
        boolean
      >
  )
  useEffect(() => {
    setSessionsOn(
      Object.fromEntries(spec.sessions.map((s) => [s.name, false] as [string, boolean])) as Record<
        string,
        boolean
      >
    )
  }, [spec.sessions])
  const toggleSession = (name: string) => setSessionsOn((v) => ({ ...v, [name]: !v[name] }))
  const setAllSessions = (on: boolean) =>
    setSessionsOn(
      Object.fromEntries(spec.sessions.map((s) => [s.name, on])) as Record<string, boolean>
    )
  // On-chart "Sessions" legend popover (TradingView indicator-legend style) open state + outside-close.
  const [sessionsLegendOpen, setSessionsLegendOpen] = useState(false)
  const sessionsLegendRef = useRef<HTMLDivElement>(null)
  useEffect(() => {
    if (!sessionsLegendOpen) return
    const onDown = (e: MouseEvent) => {
      if (sessionsLegendRef.current && !sessionsLegendRef.current.contains(e.target as Node))
        setSessionsLegendOpen(false)
    }
    document.addEventListener('mousedown', onDown)
    return () => document.removeEventListener('mousedown', onDown)
  }, [sessionsLegendOpen])

  // Trades: one on/off toggle for all of them, driven from the right-click chart menu.
  const [tradesOn, setTradesOn] = useState(true)

  // Outcome filters — winners, scratches and losers toggle independently, so the chart can show
  // just one kind. All default ON (a run opens on every trade). Every one of them reads the SAME
  // `tradeOutcome` the overlay's chip and colour read, so a trade's chip and its filter can never
  // disagree — which is the whole reason the verdict is a function and not three inline `pnl > 0`
  // tests. Scratches get their own chip rather than being folded in with the losers: a trade that
  // netted $0.00 is not a loss, and the run's own KPI row has always counted it separately.
  const [winnersOn, setWinnersOn] = useState(true)
  const [scratchesOn, setScratchesOn] = useState(true)
  const [losersOn, setLosersOn] = useState(true)
  const outcomeVisible = useCallback(
    (tr: ChartTrade) => {
      const v = tradeOutcome(tr)
      return v === 'won' ? winnersOn : v === 'scratch' ? scratchesOn : losersOn
    },
    [winnersOn, scratchesOn, losersOn]
  )
  const outcomeCounts = useMemo(() => {
    let wins = 0,
      scratches = 0
    for (const tr of spec.trades) {
      const v = tradeOutcome(tr)
      if (v === 'won') wins++
      else if (v === 'scratch') scratches++
    }
    return { wins, scratches, losses: spec.trades.length - wins - scratches }
  }, [spec.trades])

  // Trade fibs — each trade's OWN fib leg, the ladder the strategy priced its entry, stop and
  // targets off. Default OFF and listed only when trades actually carry one: NT8/MT5 record none,
  // and neither does a Python run finished before the field existed (there is no backfill — it
  // would mean replaying the strategy), so the toggle vanishes rather than sitting there inert.
  const [tradeFibsOn, setTradeFibsOn] = useState(false)
  const tradeFibCount = useMemo(
    () => spec.trades.reduce((n, tr) => n + (tr.fib?.levels?.length ? 1 : 0), 0),
    [spec.trades]
  )

  // SCALE-IN DETAIL — every add lot drawn as the trade it is (Aaron's call, 2026-08-19). A lot has
  // its own entry, its own excursion and its own exit, and the panel could previously say only that
  // one was BOUGHT: a dotted `Add` line at its fill price and nothing else. So the questions a
  // reader asks of any trade — how far did it run, what was its drawdown, where did it come off —
  // had no answer for the part of the position that often carries most of the size.
  //
  // Default OFF, for the same reason Fibs is: a runner with four adds becomes five overlapping
  // boxes, and the run reads fine without it. It is a peer row rather than a sub-toggle of Trades —
  // it is its own reading of the chart — but it does NOT draw with Trades off, because an add box
  // floating with no parent trade under it is unreadable in a way a fib leg is not.
  //
  // ⚠ Counted on `exitPrice`, NOT on `adds.length`. A run stored before the strategy recorded the
  // per-lot fields carries the bare `{price, ms, qty}`, which has nothing to draw a box from — so
  // the row vanishes for it rather than sitting there toggling nothing. Same rule the Fibs row
  // follows, and there is no backfill: re-run the backtest.
  const [tradeAddsOn, setTradeAddsOn] = useState(false)
  const tradeAddCount = useMemo(
    () =>
      spec.trades.reduce(
        (n, tr) => n + (tr.adds ?? []).filter((a) => typeof a.exitPrice === 'number').length,
        0
      ),
    [spec.trades]
  )

  // Blocked setups — the trades that never happened. Default OFF: they are a diagnostic view
  // ("is this rule protecting me or costing me?"), not part of reading the run's result, and on a
  // long run there are more of them than there are trades.
  // NORMALISED on read. A `chart_spec.json` is CACHED per run, so a spec built before `reasons`
  // became a list is still on disk carrying a single `label`/`reason` pair — and every read below
  // (`b.reasons.length`, the filter roster, the hover card) would throw on it, taking the whole
  // panel down. A stale cache must degrade, never crash.
  // Ids are the record's index in the run's own `blocked_setups.json`, so they are stable across
  // windows and a page that overlaps another cannot double up.
  const blocks = useMemo<ChartBlock[]>(
    () =>
      (spec.blocks ?? [])
        .map((b) => {
          const legacy = b as unknown as { label?: string; reason?: string }
          return {
            ...b,
            reasons: b.reasons?.length
              ? b.reasons
              : legacy.label
                ? [{ label: legacy.label, reason: legacy.reason ?? '' }]
                : [],
          }
        })
        .filter((b) => b.reasons.length > 0),
    [spec.blocks]
  )
  const [blocksOn, setBlocksOn] = useState(false)
  // The hovered marker's card + where to float it. ONE state and one card for BOTH the Blocked and
  // Missed layers — they carry the same shape of answer, so two cards would drift.
  // klinecharts fires the hover on its own canvas, so the card is a plain DOM node placed at the
  // cursor. It reads the event's PAGE coordinates and renders viewport-`fixed` (the right-click
  // menu's pattern) rather than positioning inside the chart wrapper: the overlay event's `x`/`y`
  // are pane-relative, so any wrapper padding or a second pane would silently offset the card.
  // Page coords have one origin, in every layout and fullscreen.
  const [markerTip, setMarkerTip] = useState<MarkerTip | null>(null)

  // Layers hidden from the chart (isolate one strategy on a portfolio stack). Ids only — a stale id
  // from a spec change is inert, so no reconciliation needed.
  //
  // ⚠ **Declared HERE, above every predicate that reads it**, which is further up than it belongs
  // by subject. `blockVisible` / `missVisible` / `overlayLayerVisible` all list it in a dependency
  // array, and a `const` referenced above its own declaration is a TDZ crash at render — the same
  // trap the two Missed-layer filters already carry a note about, and the one `tsc` cannot see when
  // the reference is inside a closure.
  const [hiddenLayers, setHiddenLayers] = useState<Set<string>>(new Set())

  /** Does this overlay belong to a strategy that is currently shown?
   *
   *  ⚠ **ANY, not every.** A gap / order block / liquidity level on a stack carries the layers of
   *  EVERY leg that fired near it, because it is one market fact selected for drawing by several
   *  strategies — so isolating one leg must not remove a zone the other leg also traded into. An
   *  overlay with no `layers` (a single run, or a stack's structure overlays) always draws. */
  const overlayLayerVisible = useCallback(
    (ov: ChartOverlay) => !ov.layers?.length || ov.layers.some((l) => !hiddenLayers.has(l)),
    [hiddenLayers]
  )

  // Per-reason filters. The roster is DERIVED from the blocks themselves — first-seen order, keyed
  // on the strategy's own label — so the panel stays strategy-agnostic: it sees reasons as data,
  // exactly like overlay groups and stack layers, and a strategy with a different rule set needs no
  // change here. Counts are how many setups EACH rule refused, which is the number the whole layer
  // exists to produce ("is this rule protecting me or costing me?").
  const blockReasons = useMemo(() => {
    const counts = new Map<string, number>()
    for (const b of blocks)
      for (const r of b.reasons) counts.set(r.label, (counts.get(r.label) ?? 0) + 1)
    return Array.from(counts, ([label, count]) => ({ label, count }))
  }, [blocks])
  // Reasons hidden from the chart. A stale label from a spec change is inert, so no reconciliation.
  const [hiddenReasons, setHiddenReasons] = useState<Set<string>>(new Set())
  const toggleReason = (label: string) =>
    setHiddenReasons((prev) => {
      const next = new Set(prev)
      if (next.has(label)) next.delete(label)
      else next.add(label)
      return next
    })
  // A block draws while ANY of its reasons is still on. Requiring ALL would make "show me the veto
  // blocks" hide the ones the final hour was also refusing — which are still veto blocks.
  //
  // ⚠ **The layer gate is INSIDE the predicate, not applied at the call sites**, so the Step
  // navigator, the counts on the menu rows and the drawing effect all agree — the navigator must
  // never park on a marker belonging to a strategy the reader has isolated away.
  const blockVisible = useCallback(
    (b: ChartBlock) =>
      (!b.layer || !hiddenLayers.has(b.layer)) &&
      b.reasons.some((r) => !hiddenReasons.has(r.label)),
    [hiddenReasons, hiddenLayers]
  )
  const shownBlockCount = useMemo(
    () => blocks.reduce((n, b) => n + (blockVisible(b) ? 1 : 0), 0),
    [blocks, blockVisible]
  )

  // Missed setups — the other half of "why didn't this trade". A block was a trade the strategy
  // had READY and refused; a miss got partway and died. Default OFF for the same reason Blocked
  // is: a diagnostic view, and there are far more of them than there are trades.
  const misses = useMemo<ChartMiss[]>(
    () => (spec.misses ?? []).filter((m) => m.reasons?.length > 0),
    [spec.misses]
  )
  const [missesOn, setMissesOn] = useState(false)

  // ── The Missed layer's TWO filters ───────────────────────────────────────────────────────────
  // Both hidden-sets are declared BEFORE either count, because each count now reads the OTHER
  // filter's set (see below) — and a `const` referenced above its declaration is a TDZ crash that
  // a typecheck will happily bless when the reference is inside a closure.

  // Seeded from the EMITTER's `missNoise` — the reasons it says aren't worth opening on. The panel
  // treats them as opaque strings (it has no idea one of them means "price never retraced"); it
  // just starts them unticked, and one click brings any of them back. That is what reproduces the
  // Pine's default view without the chart learning a strategy concept, and it is why the layer is
  // usable the moment you switch it on instead of burying the interesting misses under the routine
  // ones. Re-seeded when the spec changes; a stale label is inert.
  //
  // ⚠ The seed is applied on a NEW SPEC only. It used to also take labels from each page of older
  // history, because the shipped window could carry a noise list the rest of the run did not — the
  // spec now covers the whole run, so there is one list and it arrives once.
  const [hiddenMissReasons, setHiddenMissReasons] = useState<Set<string>>(
    () => new Set(spec.missNoise ?? [])
  )
  useEffect(() => {
    setHiddenMissReasons(new Set(spec.missNoise ?? []))
  }, [spec.missNoise])
  const toggleMissReason = (label: string) =>
    setHiddenMissReasons((prev) => {
      const next = new Set(prev)
      if (next.has(label)) next.delete(label)
      else next.add(label)
      return next
    })

  // All scores start SHOWN. The layer's opening view is the emitter's `missNoise` recommendation and
  // this must not quietly narrow it — a second default would be a second answer to "what do I see
  // first", and the reader would have no way to tell which one hid a marker.
  const [hiddenMissScores, setHiddenMissScores] = useState<Set<string>>(() => new Set())
  useEffect(() => {
    setHiddenMissScores(new Set())
  }, [spec.misses])
  const toggleMissScore = (key: string) =>
    setHiddenMissScores((prev) => {
      const next = new Set(prev)
      if (next.has(key)) next.delete(key)
      else next.add(key)
      return next
    })

  // ⚠ **EACH AXIS COUNTS WHAT THE OTHER IS LETTING THROUGH, and the roster is separate from the
  // count.** Both halves are load-bearing, for different reasons.
  //
  // The CROSS-FILTERED count, because the two filters compose: with "3 of 3" alone the layer draws
  // 35 markers while the reason chips went on reading 179 / 238 / 21 / 10 / 4 — which sum to 452,
  // the whole set. Reported off the screen. **A chip's number is a claim about what ticking it
  // would change**, so conditioned on nothing it is a claim about markers that are not on the
  // chart. A reason that cannot occur at this score now reads 0, which is itself the answer.
  //
  // The SEPARATE roster, because shrinking it to the values PRESENT in the filtered subset would
  // delete a chip the instant its count hit 0 — and a control that disappears when it reaches zero
  // is one the reader cannot use to get back.
  const missReasons = useMemo(() => {
    const counts = new Map<string, number>()
    // Roster: every label in the run, in first-seen order, seeded at 0.
    for (const m of misses)
      for (const r of m.reasons) if (!counts.has(r.label)) counts.set(r.label, 0)
    // Count: only the misses the SCORE filter is letting through.
    for (const m of misses) {
      if (hiddenMissScores.has(`${m.met}/${m.of}`)) continue
      for (const r of m.reasons) counts.set(r.label, (counts.get(r.label) ?? 0) + 1)
    }
    return Array.from(counts, ([label, count]) => ({ label, count }))
  }, [misses, hiddenMissScores])

  // SCORE chips — "3 of 3" / "2 of 3" (Aaron, 2026-08-08: *"sometimes I just want to see 2/3 vs 3/3
  // because they are legit different"*). A 3/3 had every confluence and still did not trade; a 2/3
  // never got there. Reading one is a different question from reading the other, and the reason list
  // could not express it: the labels map onto the scores in THIS strategy, so the filter existed,
  // but only for a reader who already knew which of the seven labels meant which.
  //
  // ⚠ Derived from the data and OPAQUE, exactly like the reason chips — the panel does not know what
  // a confluence is, only that a miss carries `met`/`of`. A strategy scoring out of four lists
  // "3 of 4" here without this file changing, which is the same contract `of` already had.
  //
  // ⚠ The MIRROR of `missReasons`: roster from every miss, count from only those the REASON filter
  // is letting through.
  const missScores = useMemo(() => {
    const counts = new Map<string, number>()
    for (const m of misses) {
      if (!m.of) continue // a record that counted nothing cannot be filed under a score
      const k = `${m.met}/${m.of}`
      if (!counts.has(k)) counts.set(k, 0)
      if (m.reasons.some((r) => !hiddenMissReasons.has(r.label)))
        counts.set(k, (counts.get(k) ?? 0) + 1)
    }
    // Best score first — a 3/3 is the one worth opening on, and a descending list puts it at the top
    // whatever the denominator.
    return Array.from(counts, ([key, count]) => ({ key, count })).sort(
      (a, b) => Number(b.key.split('/')[0]) - Number(a.key.split('/')[0])
    )
  }, [misses, hiddenMissReasons])

  // Score AND reason. Two independent axes, so unticking "2 of 3" must not also decide anything
  // about the reasons — that is the whole point of splitting them.
  const missVisible = useCallback(
    (m: ChartMiss) =>
      (!m.layer || !hiddenLayers.has(m.layer)) &&
      !hiddenMissScores.has(`${m.met}/${m.of}`) &&
      m.reasons.some((r) => !hiddenMissReasons.has(r.label)),
    [hiddenMissReasons, hiddenMissScores, hiddenLayers]
  )
  const shownMissCount = useMemo(
    () => misses.reduce((n, m) => n + (missVisible(m) ? 1 : 0), 0),
    [misses, missVisible]
  )

  useEffect(() => {
    setMarkerTip(null)
  }, [blocks, blocksOn, hiddenReasons, misses, missesOn, hiddenMissReasons, hiddenMissScores])

  // Portfolio-stack layers. The roster is DERIVED from the trades themselves (`layer`/`layerName`/
  // `layerColor`), so the panel stays strategy-agnostic — it sees layers as data, exactly like
  // overlay groups. Empty on a single-run spec, which is what hides the Strategies dropdown.
  const tradeLayers = useMemo(() => {
    const seen = new Map<string, { id: string; name: string; color: string }>()
    for (const tr of spec.trades) {
      if (!tr.layer || seen.has(tr.layer)) continue
      seen.set(tr.layer, {
        id: tr.layer,
        name: tr.layerName ?? tr.layer,
        color: tr.layerColor ?? DEFAULT_OVERLAY_COLOR,
      })
    }
    return Array.from(seen.values())
  }, [spec.trades])
  // A leg's display name for the marker hover cards. It falls back to the id rather than to nothing:
  // a raw `mpc_bleg` is worse to read than the name and is still an ANSWER, where a blank line would
  // read as a marker belonging to no strategy.
  const layerName = useCallback(
    (id: string) => tradeLayers.find((l) => l.id === id)?.name ?? id,
    [tradeLayers]
  )
  const toggleLayer = (id: string) =>
    setHiddenLayers((prev) => {
      const next = new Set(prev)
      if (next.has(id)) next.delete(id)
      else next.add(id)
      return next
    })

  // ── Step navigator ───────────────────────────────────────────────────────────
  // The set the ◀ / ▶ arrows walk: every marker the Analysis dropdown is currently SHOWING, oldest
  // first. It reuses that dropdown's own predicates rather than offering its own filters, which is
  // what makes "show me only the losers, then step" work with no extra control — and what stops the
  // navigator from ever walking to something that isn't drawn.
  //
  // The one place it deliberately parts company with the drawing effects is the loaded-candle clip:
  // those skip a marker outside the loaded window because klinecharts would clamp it onto the plot
  // edge; the navigator must still LIST it, because reaching it is exactly what the arrows are for
  // (the jump pages the history in on the way, like Go to date).
  const navMarkers = useMemo<NavMarker[]>(() => {
    const out: NavMarker[] = []
    if (tradesOn) {
      for (const tr of spec.trades) {
        if (tr.layer && hiddenLayers.has(tr.layer)) continue
        const verdict = tradeOutcome(tr)
        if (!outcomeVisible(tr)) continue
        out.push({
          // Layer-qualified: a stack merges several runs' trade lists, and two legs numbering their
          // own trades from 1 would otherwise share an id — which the step lookup reads as one
          // marker and walks in circles on.
          id: `t:${tr.layer ?? ''}:${tr.id}`,
          ts: tr.entryTime,
          kind: verdict === 'won' ? 'win' : verdict === 'scratch' ? 'scratch' : 'loss',
          label:
            NAV_KIND_LABEL[verdict === 'won' ? 'win' : verdict === 'scratch' ? 'scratch' : 'loss'],
          color: outcomeColor(verdict),
          note:
            `${tr.dir === 'long' ? '▲ Long' : '▼ Short'} · ${tr.pnl >= 0 ? '+' : '−'}${Math.abs(tr.pnl).toFixed(2)}` +
            (tr.layerName ? ` · ${tr.layerName}` : ''),
        })
      }
    }
    if (blocksOn) {
      for (const b of blocks) {
        if (!blockVisible(b)) continue
        out.push({
          id: `b:${b.id}`,
          ts: b.time,
          kind: 'block',
          label: NAV_KIND_LABEL.block,
          color: BLOCK_COLOR,
          note: `${b.dir === 'long' ? '▲ Long' : '▼ Short'} · ${b.reasons.map((r) => r.label).join(', ')}`,
        })
      }
    }
    if (missesOn) {
      for (const m of misses) {
        if (!missVisible(m)) continue
        out.push({
          id: `m:${m.id}`,
          ts: m.time,
          kind: 'miss',
          label: NAV_KIND_LABEL.miss,
          color: MISS_COLOR,
          note: `${m.dir === 'long' ? '▲ Long' : '▼ Short'} · ${m.met}/${m.of} · ${m.reasons.map((r) => r.label).join(', ')}`,
        })
      }
    }
    return out.sort((a, b) => a.ts - b.ts)
  }, [
    spec.trades,
    tradesOn,
    outcomeVisible,
    hiddenLayers,
    blocks,
    blocksOn,
    blockVisible,
    misses,
    missesOn,
    missVisible,
  ])

  // Where the navigator is parked. The TIMESTAMP is kept beside the id on purpose: a marker can
  // leave the set under you (untick Losers while parked on a loss) and the next press must still
  // continue FROM THERE rather than teleporting back to the viewport.
  const [navAt, setNavAt] = useState<{ id: string; ts: number } | null>(null)
  const navIdx = useMemo(
    () => (navAt ? navMarkers.findIndex((m) => m.id === navAt.id) : -1),
    [navAt, navMarkers]
  )
  // Parked on something the spec no longer has (a new run, a reloaded chart) ⇒ park nowhere.
  useEffect(() => {
    setNavAt(null)
  }, [spec])

  const navMarkersRef = useRef(navMarkers)
  useEffect(() => {
    navMarkersRef.current = navMarkers
  }, [navMarkers])
  const navAtRef = useRef(navAt)
  useEffect(() => {
    navAtRef.current = navAt
  }, [navAt])
  const displayCandlesRef = useRef(displayCandles)
  useEffect(() => {
    displayCandlesRef.current = displayCandles
  }, [displayCandles])

  // The bar under the middle of the plot — the anchor for the FIRST press, so ◀ means "the last one
  // before what I'm looking at" rather than "the last one in the run".
  const visibleCentreTs = useCallback((): number | null => {
    const chart = chartRef.current
    const candles = displayCandlesRef.current
    if (!chart || candles.length === 0) return null
    const r = chart.getVisibleRange()
    const mid = Math.floor((r.from + r.to) / 2)
    return candles[Math.max(0, Math.min(candles.length - 1, mid))]?.time ?? null
  }, [])

  const stepMarker = useCallback(
    (dir: 1 | -1) => {
      const list = navMarkersRef.current
      // A jump that has to page history is a real wait, and `goToDate` refuses to start a second one.
      // Bailing here keeps the readout honest — otherwise the pill would advance and the chart wouldn't.
      if (!list.length || jumpingRef.current) return
      const at = navAtRef.current
      const idx = at ? list.findIndex((m) => m.id === at.id) : -1
      let target: NavMarker | undefined
      if (idx >= 0) {
        target = list[idx + dir]
      } else {
        // Not parked on anything in the current set — anchor on where we left off if we have it,
        // otherwise on the middle of the plot. Strict comparison, so an anchor that IS a marker
        // steps off it rather than onto itself.
        const anchor = at?.ts ?? visibleCentreTs() ?? list[list.length - 1].ts
        target =
          dir === 1
            ? list.find((m) => m.ts > anchor)
            : [...list].reverse().find((m) => m.ts < anchor)
      }
      if (!target) return
      setNavAt({ id: target.id, ts: target.ts })
      void goToDate(target.ts)
    },
    [goToDate, visibleCentreTs]
  )
  const stepMarkerRef = useRef(stepMarker)
  useEffect(() => {
    stepMarkerRef.current = stepMarker
  }, [stepMarker])
  // Pointer-over-panel gate for the ← / → keys — see the keydown effect for why it is gated.
  const hoveredRef = useRef(false)

  // Every overlay the chart may draw: the spec's own (the shipped window) plus every window paged
  // in behind it. One list, so the group roster, the counts and the render effect all describe the
  // same set — a group listed off one source and drawn off another is how a toggle ends up claiming
  // to show something that isn't there.
  // 🔴 **In a DRILL-DOWN this is the window's OWN structure, not the spec's.** The spec's overlays
  // describe the timeframe the run TRADED; a drill-down swaps the candles underneath them, and
  // until 2026-08-08 nothing swapped the overlays — so an M5 view of a 15m run drew M15 swings on
  // M5 bars, every label sitting at a price that is not a swing on anything visible. It reads as
  // the structure engine disagreeing with the TradingView indicator it was ported from, which is
  // exactly how it was reported. Structure is a property of the BARS.
  //
  // ⚠ **While the drill is still loading, `displayCandles` shows the BASE bars** (see the
  // placeholder branch there), so the base overlays are the correct ones for what is on screen —
  // hence the `fetched.length` gate rather than `isFetchMode` alone. The two must stay in step: a
  // mismatch here is the same defect in miniature.
  //
  // ⚠ **The ANALYSIS layers (fair value gaps, order blocks, liquidity) drop out of a drill-down,
  // deliberately.** They are anchored to the run's own trades/blocks/misses and computed on its
  // bars, so there is no honest version of them at another timeframe — and drawing the base ones
  // is the very defect above. Their toggles go with them rather than showing an empty layer.
  const allOverlays = useMemo(
    () => (isFetchMode && fetched.length ? drillOverlays : spec.overlays),
    [isFetchMode, fetched.length, drillOverlays, spec.overlays]
  )

  // Generic overlays (box/hline/vline) carry strategy structure, grouped by `group`. Each group
  // is independently toggleable. The chart never knows which strategy produced them.
  const overlayGroups = useMemo(() => {
    const seen = new Map<string, string>() // group → representative (first) color
    for (const ov of allOverlays) {
      if (!seen.has(ov.group)) seen.set(ov.group, ov.style?.color ?? DEFAULT_OVERLAY_COLOR)
    }
    // Market structure always shows ALL FOUR toggles once the run carries any structure at all —
    // they're the Pine's four checkboxes, and a checkbox that vanishes when its layer happens to be
    // empty reads as a missing feature. "Internal Structure" is the one this bites: it holds only the
    // CURRENT external leg, which is legitimately empty on most runs (everything older is Historic).
    if (STRUCTURE_GROUPS.some((g) => seen.has(g))) {
      for (const g of STRUCTURE_GROUPS) if (!seen.has(g)) seen.set(g, STRUCTURE_GROUP_COLOR[g])
    }
    // Non-structure groups first (in first-seen order), then the market-structure groups in their
    // fixed canonical order so the four Layers toggles always read External → Internal → Historic →
    // Swing Labels, regardless of which fired first in the spec.
    const all = Array.from(seen, ([name, color]) => ({ name, color }))
    const structureOrder = (n: string) =>
      STRUCTURE_GROUPS.indexOf(n as (typeof STRUCTURE_GROUPS)[number])
    const nonStruct = all.filter((g) => structureOrder(g.name) < 0)
    const struct = all
      .filter((g) => structureOrder(g.name) >= 0)
      .sort((a, b) => structureOrder(a.name) - structureOrder(b.name))
    return [...nonStruct, ...struct]
  }, [allOverlays])

  // Overlay groups are split by the QUESTION they answer, exactly like the two dropdowns: an
  // ANALYSIS group (fair value gaps, drawn only around trades/blocks/misses) is about the strategy's
  // signals and belongs beside Trades/Blocked/Missed; everything else is market structure. One
  // roster still backs `groupsOn` — only the MENU each row appears in differs.
  const isAnalysisGroup = (name: string) =>
    ANALYSIS_GROUPS.includes(name as (typeof ANALYSIS_GROUPS)[number])
  const structureGroups = useMemo(
    () => overlayGroups.filter((g) => !isAnalysisGroup(g.name)),
    [overlayGroups]
  )
  // Each analysis group carries its BOX COUNT, the way Blocked and Missed carry theirs — a layer
  // that draws 41 gaps and one that draws 4 read very differently before you switch it on.
  //
  // ⚠ **The ROSTER comes from every overlay and only the COUNT is layer-filtered** — the same rule
  // the Missed layer's chips follow. A row that vanished when the reader isolated a strategy would
  // be a control they could not use to get back, and a `0` beside a live row is an answer.
  const analysisGroups = useMemo(() => {
    const counts = new Map<string, number>()
    const present = new Set<string>()
    for (const ov of allOverlays) {
      if (!isAnalysisGroup(ov.group)) continue
      present.add(ov.group)
      if (overlayLayerVisible(ov)) counts.set(ov.group, (counts.get(ov.group) ?? 0) + 1)
    }
    return (
      ANALYSIS_GROUPS
        // ⚠ The candle repaint is DROPPED off the timeframe it was computed on, and the row goes with
        // it rather than sitting there drawing nothing. A candlestick pattern is a property of ONE
        // bar size — an M15 hammer is not an H1 hammer — so painting the H1 bar that happens to
        // CONTAIN it would state something nobody measured, and at M1 there is no single bar that is
        // the pattern at all. Every other analysis group is a price/time zone and resamples fine.
        .filter((g) => present.has(g) && (g !== GROUP_CANDLE_MARKS || atBaseTf))
        .map((g) => ({
          name: g as string,
          color: ANALYSIS_GROUP_COLOR[g],
          count: counts.get(g) ?? 0,
        }))
    )
  }, [allOverlays, atBaseTf, overlayLayerVisible])

  // Candlestick reversals — a DIRECTION filter, the same shape as the Missed layer's score rows
  // (Aaron, 2026-08-08: *"other times it's showing candle patterns that [point] nothing in the
  // direction of the trade — if I take a long, it's showing my bearish engulfing"*).
  //
  // ⚠ **All three start ON, and the opposing one is not special-cased away.** It is half the point
  // of the layer — *"if it lines up with my trades, then great. If not, it will show me why I was
  // wrong"* — so this is a control the reader reaches for, never a default that quietly decides
  // there was nothing at the turn. `patternDir` is the source Pine's own +1/-1/0, so the panel is
  // filtering on a value it was handed rather than on one it invented.
  const CANDLE_DIRS = useMemo(
    () =>
      [
        { key: 'with', label: 'With the setup' },
        { key: 'neutral', label: 'Neutral' },
        { key: 'against', label: 'Against it' },
      ] as const,
    []
  )
  const [hiddenCandleDirs, setHiddenCandleDirs] = useState<Set<string>>(() => new Set())
  // Which TRADES had a reversal candle in their span. Aaron, 2026-08-08: *"if there's no candle
  // pattern where I took the trade, put an indicator inside the Won/Lost label that shows whether
  // there was a pattern or not."*
  //
  // ⚠ Read off each mark's `spans`, NOT from "is there a mark between entry and exit". Spans overlap
  // — a 3/3 miss's retrace can sit inside a trade's hold — so a time-range test would credit this
  // trade with somebody else's candle. The anchor list is `trades ++ misses` in spec order, so
  // anchor `i` IS trade `i`, and the backend carries that index through the off-chart drop for
  // exactly this reason.

  const candleDirCounts = useMemo(() => {
    const n: Record<string, number> = {}
    for (const ov of allOverlays) {
      if (ov.type !== 'candle' || ov.group !== GROUP_CANDLE_MARKS) continue
      const k = ov.align ?? 'against'
      n[k] = (n[k] ?? 0) + 1
    }
    return n
  }, [allOverlays])
  const toggleCandleDir = (key: string) =>
    setHiddenCandleDirs((prev) => {
      const next = new Set(prev)
      if (next.has(key)) next.delete(key)
      else next.add(key)
      return next
    })
  // ⚠ `align` comes from the BACKEND and must not be re-derived from `patternDir`. That is the
  // pattern's OWN direction; whether a bullish candle points the setup's way depends on the setup's
  // side, which a mark does not carry and cannot — one bar can sit inside a long's span and a
  // short's at once, and the anchor that names the bar is the one that answers for it.
  const candleDirKey = (ov: ChartOverlay) =>
    ov.type === 'candle' ? (ov.align ?? 'against') : 'against'

  // ⚠ It NAMES the pattern rather than ticking a box. `Won · ✓` was the first attempt and it is
  // unreadable — a tick beside "Won" says *confirmed win*, not *a candle was there* (Aaron: *"how
  // would I know a tick means a candle was there and an x means none?"*). The name needs no legend,
  // and it is free: the span's DEEPEST mark is the reversal at the turn, which is the one worth
  // naming when only one fits.
  const tradePattern = useMemo(() => {
    const named = new Map<number, string>()
    const any = new Set<number>()
    for (const ov of allOverlays) {
      if (ov.type !== 'candle' || ov.group !== GROUP_CANDLE_MARKS) continue
      // Follows the direction filter, so the chip agrees with the candles on screen — reading
      // "Won · Bearish Engulfing" with the opposing tier hidden and no navy candle anywhere is
      // exactly the kind of two-sources-one-answer this chart keeps being bitten by.
      if (hiddenCandleDirs.has(candleDirKey(ov))) continue
      for (const n of ov.spans ?? []) any.add(n)
      // `deepestNames` before `label`: the bar's own label is whichever anchor reached it first, and
      // on a bar that is the deepest of both a losing trade and a miss those two want opposite
      // directions. The per-anchor name is the only one that can answer both.
      //
      // ⚠ **A `deepestNames` OBJECT that lacks this anchor's key is an ANSWER, not a gap** — the
      // backend withholds the name when the span's only candles point against the setup, so falling
      // back to `label` there would put the opposing candle's name back on the chip, which is the
      // defect. `label` is the fallback ONLY when the field is absent altogether, i.e. a spec cached
      // before per-anchor naming existed. The repo's own rule: never let "no" and "cannot ask" be
      // the same value.
      for (const n of ov.deepestOf ?? []) {
        const name = ov.deepestNames ? ov.deepestNames[String(n)] : ov.label
        if (name) named.set(n, name)
      }
    }
    return { named, any }
  }, [allOverlays, hiddenCandleDirs])

  // Every overlay group defaults ON, EXCEPT the market-structure groups and the analysis groups —
  // both are opt-in (a chart would be unreadable with all of BOS/SOS/swings/internal drawn by
  // default, and the gap layer is a diagnostic view like Blocked and Missed beside it).
  const groupDefault = (name: string): boolean =>
    !STRUCTURE_GROUPS.includes(name as (typeof STRUCTURE_GROUPS)[number]) && !isAnalysisGroup(name)
  const [groupsOn, setGroupsOn] = useState<Record<string, boolean>>(
    () =>
      Object.fromEntries(
        overlayGroups.map((g) => [g.name, groupDefault(g.name)] as [string, boolean])
      ) as Record<string, boolean>
  )
  // RECONCILED, never overwritten. The roster is DERIVED from the overlays, so it is rebuilt every
  // time a page of older history lands — and re-seeding it with the defaults on each rebuild
  // switched the reader's layers back off mid-scroll, which is the bug this whole path exists to
  // fix. A group already answered keeps its answer; only a genuinely new one takes the default.
  // Defaults return only on a NEW spec, i.e. a different run.
  const groupSpecRef = useRef(spec)
  useEffect(() => {
    const freshRun = groupSpecRef.current !== spec
    groupSpecRef.current = spec
    const roster = overlayGroups.map((g) => [g.name, groupDefault(g.name)] as [string, boolean])
    setGroupsOn((prev) => reconcileToggles(freshRun ? {} : prev, roster))
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [spec, overlayGroups])
  const toggleGroup = (name: string) => setGroupsOn((v) => ({ ...v, [name]: !v[name] }))

  // ── Deep debug ───────────────────────────────────────────────────────────────
  // One toggle for the context layers you want behind any trade you are interrogating. It writes to
  // the SAME state the rows below it write to — there is no second copy of layer state — and it is
  // deliberately ADDITIVE: it never touches WHICH trades are drawn, so "winners, losers or both"
  // keeps one answer in one place instead of being asked twice.
  //
  // Only what the run actually CARRIES counts. A run with no recorded fibs and no structure has
  // nothing to deepen: including it would make `debugOn` vacuously true and pin the row ON for ever,
  // and `debugAvailable` is what hides it instead.
  const debugFibs = tradeFibCount > 0
  const debugGroups = useMemo(
    () => DEBUG_ON_GROUPS.filter((g) => overlayGroups.some((og) => og.name === g)),
    [overlayGroups]
  )
  const debugAvailable = debugFibs || debugGroups.length > 0
  const debugOn =
    debugAvailable && (!debugFibs || tradeFibsOn) && debugGroups.every((g) => groupsOn[g])

  // Setting a layer the run never emitted is inert — an absent group is dropped by the next
  // `reconcileToggles`, and `tradeFibsOn` with no recorded fib draws nothing — so the write is
  // unconditional even though the READ above is not.
  const toggleDebug = useCallback(() => {
    const next = !debugOn
    setTradeFibsOn(next)
    setGroupsOn((v) => ({ ...v, ...Object.fromEntries(DEBUG_ON_GROUPS.map((g) => [g, next])) }))
  }, [debugOn])

  // Daily breaks: one vertical line at the start of each TRADING DAY present in the data — a
  // regular daily grid like TradingView, independent of where trades landed (the old code scoped
  // these to trade days, which is why they looked irregularly spaced). Each line is anchored to
  // that day's FIRST candle so it always lands on a real bar (weekend/holiday days have no candle
  // and so no line — separators sit between consecutive trading days). The opening day is skipped.
  const dailyBreaks = useMemo(() => {
    if (baseCandles.length === 0) return []
    const firstOfDay = new Map<number, number>() // dayStart(UTC) → first candle time that day
    for (const c of baseCandles) {
      const day = Math.floor(c.time / DAY_MS) * DAY_MS
      if (!firstOfDay.has(day)) firstOfDay.set(day, c.time)
    }
    return Array.from(firstOfDay.values())
      .sort((a, b) => a - b)
      .slice(1)
  }, [baseCandles])
  const [dayBreaksOn, setDayBreaksOn] = useState(false)

  // The on-chart Sessions legend governs everything CLOCK-driven — the session windows AND the daily
  // session breaks. One roster so the pill's count, the dot and Show/Hide-all all describe the same
  // set; counting day breaks in the pill but leaving them out of "all" would be a quiet lie.
  const clockLayerCount = useMemo(() => {
    const extra = dailyBreaks.length > 0 ? 1 : 0
    return {
      on: spec.sessions.filter((s) => sessionsOn[s.name]).length + (dayBreaksOn && extra ? 1 : 0),
      total: spec.sessions.length + extra,
    }
  }, [spec.sessions, sessionsOn, dayBreaksOn, dailyBreaks.length])
  const anyClockLayerOn = clockLayerCount.on > 0
  const setAllClockLayers = (on: boolean) => {
    setAllSessions(on)
    setDayBreaksOn(on)
  }

  // Indicators (shipped series). One on/off per indicator; sub-pane ids tracked for removal.
  // Each carries its OWN default (`defaultOn`, absent ⇒ on) — the ATR pane has always opened on,
  // and an analysis layer like the session VWAP must not.
  const indicatorRoster = useMemo(
    () => spec.indicators.map((i) => [i.name, i.defaultOn !== false] as [string, boolean]),
    [spec.indicators]
  )
  const [indicatorsOn, setIndicatorsOn] = useState<Record<string, boolean>>(
    () => Object.fromEntries(indicatorRoster) as Record<string, boolean>
  )
  // RECONCILED, never re-seeded — the same rule `groupsOn` follows, and for the same reason: a
  // plain re-seed on a spec swap silently undoes every toggle the reader has set.
  useEffect(() => {
    setIndicatorsOn((prev) => reconcileToggles(prev, indicatorRoster))
  }, [indicatorRoster])
  const toggleIndicator = (name: string) => setIndicatorsOn((v) => ({ ...v, [name]: !v[name] }))
  const indicatorPanesRef = useRef<Map<string, string>>(new Map()) // indicator name → pane id
  // Test seam. An indicator draws into the candle pane's CANVAS, so whether a layer is on screen
  // has no DOM answer; this publishes the names the create pass actually handed to klinecharts.
  const [drawnIndicatorNames, setDrawnIndicatorNames] = useState<string[]>([])

  // Measurement tool: click to anchor, move to preview, click to lock. One at a time.
  // Clicking a locked measurement clears it. Events bubble from the canvas so klinecharts
  // crosshair still draws — no capture layer needed.
  const [measureMode, setMeasureMode] = useState(false)
  const [measurement, setMeasurement] = useState<LockedMeasurement | null>(null)
  const [anchor, setAnchor] = useState<{ x: number; y: number; ts: number; val: number } | null>(
    null
  )
  const [liveDrag, setLiveDrag] = useState<MeasureRect | null>(null)

  // Fibonacci drawings — the source of truth is React state (each = id + its two anchor points as
  // timestamp/value), so the tool survives TF switches / data reloads (which clear klinecharts
  // overlays). A persistence effect re-creates them from state after every data change.
  // `levels` is an OVERRIDE and is normally absent: a fib with no ladder of its own FOLLOWS the
  // tool default live, so retuning the default retunes every drawing that has not been customised.
  // Snapshotting the default at draw time instead would make "change my levels" silently do nothing
  // to the fibs already on screen.
  const [fibs, setFibs] = useState<
    { id: string; points: { timestamp: number; value: number }[]; levels?: FibLevel[] }[]
  >([])
  const selectedFibRef = useRef<string | null>(null) // fib currently selected (for the Delete key)
  const ctxFibRef = useRef<string | null>(null) // fib the right-click landed on (→ "Delete this fib")

  // The tool's DEFAULT ladder — a setting, so it persists across reloads (a drawing does not).
  const [fibLevels, setFibLevels] = useState<FibLevel[]>(() => loadFibLevels())
  useEffect(() => {
    saveFibLevels(fibLevels)
  }, [fibLevels])
  // How the reader wants the chart DRAWN — persisted per browser, never part of a run. Same
  // load-once / save-on-change shape as the fib ladder above; see `chartSettings.ts`.
  const [chartSettings, setChartSettings] = useState<ChartSettings>(() => loadChartSettings())
  useEffect(() => {
    saveChartSettings(chartSettings)
  }, [chartSettings])
  const [settingsAt, setSettingsAt] = useState<{ x: number; y: number } | null>(null)
  // The open level editor. `fibId: null` = editing the default ladder (from the tool strip);
  // a fib id = editing that one drawing's override (from its right-click menu).
  const [fibEditor, setFibEditor] = useState<{ x: number; y: number; fibId: string | null } | null>(
    null
  )
  // Bumped whenever the editor's rows must be re-seeded from state rather than from typing —
  // a reset, or dropping a per-drawing override. See `resetKey` in FibSettings.
  const [fibEditorSeq, setFibEditorSeq] = useState(0)
  // Default zoom/scroll captured at init, restored by "Reset chart view" (right-click menu).
  const defaultBarSpaceRef = useRef<number | null>(null)
  const defaultOffsetRef = useRef<number | null>(null)
  // Right-click context menu (viewport-fixed at the cursor). null = closed. `fibId` = the fib the
  // cursor was over when it opened (→ "Delete this fib"); null when opened over empty chart.
  const [ctxMenu, setCtxMenu] = useState<{ x: number; y: number; fibId: string | null } | null>(
    null
  )

  // Price decimals for the fib level labels, inferred from the instrument's magnitude
  // (gold/JPY ~2dp, FX majors ~5dp). Good enough for a label; not used for any math.
  const pricePrecision = useMemo(() => {
    const p = spec.candles[spec.candles.length - 1]?.close ?? 1
    return p >= 20 ? 2 : 5
  }, [spec.candles])

  // Escape: cancel anchor / clear measurement and exit measure mode
  useEffect(() => {
    if (!measureMode) return
    const onKey = (e: KeyboardEvent) => {
      if (e.key === 'Escape') {
        setMeasureMode(false)
        setAnchor(null)
        setLiveDrag(null)
        setMeasurement(null)
      }
    }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [measureMode])

  const pixelToChart = (clientX: number, clientY: number) => {
    const el = containerRef.current
    if (!el || !chartRef.current) return null
    const rect = el.getBoundingClientRect()
    const x = clientX - rect.left
    const y = clientY - rect.top
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    const res = (chartRef.current as any)?.convertFromPixel?.([{ x, y }], { paneId: 'candle_pane' })
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    const raw = (Array.isArray(res) ? res[0] : res) as any
    if (!raw) return null
    // timestamp is null when x maps to a data index outside the loaded range (e.g. y-axis area).
    // Fall back to the nearest candle's timestamp using the raw dataIndex klinecharts always sets.
    let ts: number | undefined = raw.timestamp
    if (!ts && typeof raw.dataIndex === 'number' && raw.dataIndex >= 0) {
      const idx = Math.min(raw.dataIndex, displayCandles.length - 1)
      ts = displayCandles[idx]?.time
    }
    if (!ts || raw.value == null) return null
    return { x, y, ts, val: raw.value as number }
  }

  const makeMeasureRect = (
    a: { x: number; y: number; ts: number; val: number },
    b: { x: number; y: number; ts: number; val: number }
  ): MeasureRect => ({
    x: Math.min(a.x, b.x),
    y: Math.min(a.y, b.y),
    w: Math.abs(b.x - a.x),
    h: Math.abs(b.y - a.y),
    startTs: a.ts,
    endTs: b.ts,
    startVal: a.val,
    endVal: b.val,
  })

  // Click inside the chart wrapper: clear locked measurement → anchor → lock.
  const handleChartClick = (e: React.MouseEvent) => {
    if (!measureMode) return
    if (!anchor && measurement) {
      setMeasurement(null)
      return
    }
    const pt = pixelToChart(e.clientX, e.clientY)
    if (!pt) return
    if (!anchor) {
      setAnchor(pt)
      setLiveDrag(null)
    } else {
      const r = makeMeasureRect(anchor, pt)
      if (r.w >= 5) setMeasurement({ id: crypto.randomUUID(), ...r })
      setAnchor(null)
      setLiveDrag(null)
    }
  }

  // Move inside the chart wrapper: update live preview while anchor is set.
  const handleChartMove = (e: React.MouseEvent) => {
    if (!measureMode || !anchor) return
    const pt = pixelToChart(e.clientX, e.clientY)
    if (!pt) return
    setLiveDrag(makeMeasureRect(anchor, pt))
  }

  // Chart inset, MEASURED from klinecharts: the right price-axis WIDTH and the bottom time-axis
  // HEIGHT of the plot. Used to line the header's Copy button up flush with the y-axis line and to
  // cap the left tool strip at the x-axis line — so the chrome forms clean right angles with the
  // plot rectangle instead of floating over the price scale / past the time axis.
  const [chartInset, setChartInset] = useState<{ axisW: number; xAxisH: number }>({
    axisW: 0,
    xAxisH: 0,
  })
  const measureInset = useCallback(() => {
    const chart = chartRef.current
    if (!chart) return
    const axisW = Math.round(chart.getSize('candle_pane', DomPosition.YAxis)?.width ?? 0)
    const xAxisH = Math.round(chart.getSize('x_axis_pane', DomPosition.Root)?.height ?? 0)
    setChartInset((prev) =>
      prev.axisW === axisW && prev.xAxisH === xAxisH ? prev : { axisW, xAxisH }
    )
  }, [])

  // ── The pinned top-left readout, and the current-price line ────────────────────────────────
  // Both used to describe the END OF THE RUN while you were looking at somewhere else in it. The
  // full story is on `makeCandleTooltip` in chartStyles.ts; these three refs are the state it and
  // the price line need, and they are refs rather than state because the visible-range effect
  // below runs on every frame of a drag — the same reason the view centre is written to the DOM by
  // hand rather than through state.
  const tipEdgeBarRef = useRef<KLineData | null>(null) // the RIGHT-MOST VISIBLE bar
  const newestTsRef = useRef<number | null>(null) // …and the timestamp of the LAST bar in the run
  const lastMarkOnRef = useRef(true) // is the newest bar in view → may the price line draw

  // Which bar the readout describes. 🔴 **THERE IS DELIBERATELY NO "IS THE POINTER ON THE CHART"
  // FLAG, and the first version of this had one and was WRONG.** klinecharts clears its crosshair
  // through more than one path and at least one of them updates it without firing the change
  // action, so a flag fed by that action sticks at "hovering" and the readout goes on naming the
  // newest bar — which is the exact defect this exists to fix, surviving its own fix. MEASURED in
  // a real browser: after the pointer left the chart the action never fired again.
  //
  // The question is answerable without one. klinecharts hands us the CROSSHAIR's bar while the
  // pointer is on one and the LAST bar in the run when it is not, so the only ambiguous case is
  // the last bar itself — and if that bar is on screen, it is also the right-most visible bar, so
  // both readings agree and there is nothing to decide. Substitute only when the last bar is off
  // screen AND it is the bar we were handed: then it cannot be something the reader is pointing at.
  const resolveTipBar = useCallback(
    (current: KLineData) =>
      !lastMarkOnRef.current && current.timestamp === newestTsRef.current
        ? (tipEdgeBarRef.current ?? current)
        : current,
    []
  )

  // Init once on mount; dispose on unmount. Data is applied by the effect below.
  useEffect(() => {
    const el = containerRef.current
    if (!el) return
    registerChartOverlays()
    const chart = init(el)
    if (!chart) return
    chartRef.current = chart
    chart.setStyles(chartStyles)
    // The pinned readout describes the RIGHT-MOST VISIBLE bar and carries no date — see
    // `makeCandleTooltip`. Installed here rather than in `chartStyles` because it closes over live
    // chart state; the styles object is the theme, this is the behaviour.
    chart.setStyles({
      candle: {
        tooltip: {
          custom: makeCandleTooltip(resolveTipBar, () => chart.getPriceVolumePrecision()),
        },
      },
    })
    defaultBarSpaceRef.current = chart.getBarSpace() // remembered for "Reset chart view"
    defaultOffsetRef.current = chart.getOffsetRightDistance()

    // Paging, BOTH directions. Registered ONCE (klinecharts keeps one callback) and delegating
    // through refs, so it always sees the current candles/timeframe instead of the first render's.
    // klinecharts names them from the DATA's point of view: Forward = older, Backward = newer.
    //
    // ⚠ **A merged page must NOT re-apply** (`skipApplyRef`): klinecharts has already spliced the
    // bars in AND kept the scroll position, so re-applying throws both away and snaps the view.
    // This is also what keeps growth cheap — the 30-second freeze is a full `applyNewData`, and
    // page merges never perform one however far the window grows.
    chart.setLoadDataCallback(({ type, callback }) => {
      // A jump is rewriting the whole applied window — two writers would duplicate or drop bars.
      if (jumpingRef.current) {
        callback([], type === LoadDataType.Forward)
        return
      }
      const older = type === LoadDataType.Forward
      const load = older ? loadOlderRef.current : loadNewerRef.current
      if (older) setPagingOlder(true)
      void load()
        .then(({ bars, more }) => {
          if (bars.length) {
            skipApplyRef.current = true
            // The applied list is `fetched` in drill-down and `baseCandles` otherwise, and splicing
            // base-timeframe bars into a 1-minute chart is exactly what the old blanket paging guard
            // existed to prevent — so the page goes to whichever list `displayCandles` is reading.
            if (isFetchModeRef.current)
              setFetched((prev) => (older ? [...bars, ...prev] : [...prev, ...bars]))
            else setBaseCandles((prev) => (older ? [...bars, ...prev] : [...prev, ...bars]))
          }
          callback(candlesToKLine(bars), more)
        })
        .catch(() => callback([], false))
        .finally(() => {
          if (older) setPagingOlder(false)
        })
    })

    const ro = new ResizeObserver(() => {
      chart.resize()
      measureInset()
    })
    ro.observe(el)
    requestAnimationFrame(measureInset)
    return () => {
      ro.disconnect()
      dispose(el)
      chartRef.current = null
      indicatorPanesRef.current.clear()
    }
  }, [measureInset])

  // (Re)feed candles whenever the displayed timeframe (or spec) changes — no re-init. Re-measure the
  // inset after: a new price range can widen/narrow the y-axis (digit count).
  useEffect(() => {
    if (!chartRef.current) return
    // A PAGE is already merged by klinecharts (which also kept the scroll position) — re-applying
    // would reset the view on every page. Everything else is a real data swap and must re-apply.
    if (skipApplyRef.current) skipApplyRef.current = false
    else chartRef.current.applyNewData(candlesToKLine(displayCandles))
    const id = requestAnimationFrame(measureInset)
    return () => cancelAnimationFrame(id)
  }, [displayCandles, measureInset])

  // Flush a jump that had to page. Declared AFTER the apply effect above so the bars are in the
  // chart by the time this runs, and only ever fires on the redraw that jump asked for.
  useEffect(() => {
    const ts = pendingJumpRef.current
    if (ts == null) return
    pendingJumpRef.current = null
    scrollToTs(ts, displayCandles)
    // Release the paging guard only AFTER the view has left the right edge the re-apply parked it
    // on — see `goToDate`. Clearing it before the scroll lets klinecharts' pending Backward request
    // through and the jump walks forward off its own target. A frame's grace, because the request
    // is queued from the layout the scroll is about to replace.
    requestAnimationFrame(() => {
      jumpingRef.current = false
    })
  }, [displayCandles, scrollToTs])

  // ── The DRAW WINDOW — overlay creation follows the VIEWPORT, not the loaded history ─────────
  //
  // 🔴 **Overlays are this chart's entire budget, and the cost is SUPERLINEAR in the count.**
  // MEASURED in a real browser on the klinecharts build this app ships: 4,017 overlays cost 561 ms
  // to create and 247 ms to paint; 6,600 cost 1,206 / 400 ms; **17,246 cost 8,025 / 3,504 ms**.
  // Candles are nearly free beside that — 155,776 of them are 40 MB of heap, and eleven prepends
  // totalled 682 ms with the viewport held throughout. So the thing to bound is the OVERLAY count,
  // and bounding the candles (which is what `_capped_start` did) was bounding the cheap half.
  //
  // A chart shows ~200 bars at a time however much history it holds, so building an overlay for
  // every swing in six years is work for something nobody can see — and a layer TOGGLE re-creates
  // all of them, which is why the 8-second figure above is a figure a reader actually waits for.
  //
  // ⚠ **The window is committed in TIMESTAMPS, never in indices.** A page prepends bars and every
  // index shifts under it; a timestamp range survives that, which is what lets this coexist with
  // paging without a recompute ordering rule between them.
  const [drawRange, setDrawRange] = useState<[number, number] | null>(null)
  // The timestamp under the middle of the plot, tracked continuously — the drill-down's fetch anchor.
  //
  // ⚠ **`visibleCentreTs()` cannot do this job and it is worth saying why.** That reads the chart's
  // visible INDEX range against `displayCandlesRef`, so it is only correct while the two agree — and
  // the one instant they do not is a timeframe switch, which is precisely when the anchor is needed:
  // the array has already been swapped for the new timeframe's while klinecharts' index range still
  // describes the old one. A timestamp recorded before the swap survives it.
  const viewCentreRef = useRef<number | null>(null)

  useEffect(() => {
    const chart = chartRef.current
    if (!chart) return
    const clampIdx = (i: number, n: number) => Math.max(0, Math.min(n - 1, Math.round(i)))
    const recompute = () => {
      const c = displayCandlesRef.current
      const ch = chartRef.current
      if (!ch || !c.length) return
      const r = ch.getVisibleRange()

      // ── What the pinned readout and the current-price line are allowed to describe ──────────
      // Both follow the WINDOW, not the end of the run. `to` is EXCLUSIVE and already clamped to
      // the data length, so the right-most visible bar is `to - 1` and "the newest bar is on
      // screen" is `to >= length`. Read off klinecharts' own list rather than `displayCandles`,
      // because these two indices are ITS indices — the lists differ for a frame during a page.
      const kl = ch.getDataList()
      tipEdgeBarRef.current = kl.length ? (kl[clampIdx(r.to - 1, kl.length)] ?? null) : null
      newestTsRef.current = kl.length ? (kl[kl.length - 1]?.timestamp ?? null) : null
      // ⚠ The price line is a fact about the LIVE edge, so it must go quiet when that edge is off
      // screen — left on, klinecharts clamps it to the top of the scale, where a bright line and a
      // price tag read as a level in the market you are looking at. It is not one.
      const markOn = kl.length > 0 && r.to >= kl.length
      if (markOn !== lastMarkOnRef.current) {
        lastMarkOnRef.current = markOn
        // Guarded on CHANGE: `setStyles` redraws the whole chart, and this runs on every frame of
        // a drag.
        ch.setStyles({ candle: { priceMark: { last: { show: markOn } } } })
      }

      const span = Math.max(1, r.to - r.from)
      const visLo = c[clampIdx(r.from, c.length)].time
      const visHi = c[clampIdx(r.to, c.length)].time
      viewCentreRef.current = c[clampIdx((r.from + r.to) / 2, c.length)].time
      // Written to the DOM imperatively, NOT through state: this runs on every frame of a drag, and
      // a `setState` here would re-render the whole panel at 60fps to publish a test seam.
      rootRef.current?.setAttribute('data-view-centre', String(viewCentreRef.current))
      setDrawRange((prev) => {
        // Already covered? Then do nothing. This is the common case on EVERY FRAME of a drag, and
        // recommitting here would re-create every overlay 60 times a second — i.e. it would turn
        // the fix into a worse version of the problem it exists to solve. The margin below is what
        // makes this branch the usual one.
        if (prev && visLo >= prev[0] && visHi <= prev[1]) return prev
        // One screen either side, so an ordinary drag is already drawn before it arrives and the
        // rebuild lands off-screen rather than under the reader.
        return [c[clampIdx(r.from - span, c.length)].time, c[clampIdx(r.to + span, c.length)].time]
      })
    }
    // rAF-coalesced: klinecharts fires this action several times per gesture, and the work below
    // is a `getVisibleRange` read plus a containment test, so one per frame is the right cadence.
    let raf = 0
    const onChange = () => {
      if (raf) return
      raf = requestAnimationFrame(() => {
        raf = 0
        recompute()
      })
    }
    chart.subscribeAction(ActionType.OnVisibleRangeChange, onChange)
    recompute() // the first window: nothing has moved yet, so no action has fired
    return () => {
      if (raf) cancelAnimationFrame(raf)
      chart.unsubscribeAction(ActionType.OnVisibleRangeChange, onChange)
    }
  }, [displayCandles])

  // The bounds the generic overlay effect actually draws between: the loaded candles intersected
  // with the draw window. ⚠ `drawRange` null means the window has not been measured yet (the very
  // first frame, or a chart with no candles) — it falls back to the LOADED range rather than to
  // nothing, because drawing everything for one frame is a cost and drawing nothing is a missing
  // layer, and only one of those looks like a bug.
  const [drawLoTs, drawHiTs] = useMemo<[number | null, number | null]>(() => {
    if (loadedLoTs == null || loadedHiTs == null) return [null, null]
    if (!drawRange) return [loadedLoTs, loadedHiTs]
    return [Math.max(loadedLoTs, drawRange[0]), Math.min(loadedHiTs, drawRange[1])]
  }, [loadedLoTs, loadedHiTs, drawRange])

  // Drill-down: when a sub-base TF is selected, pull the window the reader is LOOKING AT; clear on
  // leave. The anchor is the viewport's centre, falling back to the run's last bar only when nothing
  // has been rendered yet — which is the open case, and the only case the old fixed anchor was ever
  // right for.
  useEffect(() => {
    if (!isFetchMode) {
      // ⚠ `prev.length ? [] : prev` — never a fresh `[]` when it is already empty. A new array here
      // is a new identity, which is half of the double-apply described on `resampled` above; the
      // memo split is the other half, and both are kept because either alone leaves the hazard live
      // for the next reader who adds a dependency.
      setFetched((prev) => (prev.length ? [] : prev))
      setDrillOverlays((prev) => (prev.length ? [] : prev))
      setFetchStatus('idle')
      setFetchNote(null)
      setDataEdge(null)
      // Coming back UP from a drill-down, the reader can be somewhere the applied base window does
      // not cover — they paged M1 back past its left edge. `pickTimeframe`'s scroll would then clamp
      // to whichever end of the loaded bars is nearest, which is a silent few weeks off. Re-slicing
      // the spec around them is what `goToDate` already does, so ask it.
      const centre = viewCentreRef.current
      const b = baseCandlesRef.current
      if (
        wasFetchRef.current &&
        centre != null &&
        b.length &&
        (centre < b[0].time || centre > b[b.length - 1].time)
      ) {
        void goToDate(centre)
      }
      wasFetchRef.current = false
      return
    }
    wasFetchRef.current = true
    const anchor =
      viewCentreRef.current ?? spec.candles[spec.candles.length - 1]?.time ?? Date.now()
    void drillTo(selectedMin, anchor, false)
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [isFetchMode, selectedMin])

  // The chart now OPENS in drill-down (the run's own TF is usually finer than the shipped bars), so
  // a feed that can't serve it would leave a blank chart where the shipped candles used to be. Fall
  // back to those once, and only for the AUTO-chosen TF — a TF the user picked keeps its honest
  // "no data" message instead of silently jumping somewhere they didn't ask for.
  const autoFellBackRef = useRef(false)
  useEffect(() => {
    autoFellBackRef.current = false
  }, [openMin])
  useEffect(() => {
    if (autoFellBackRef.current || selectedMin !== openMin || openMin === baseMin) return
    if (fetchStatus !== 'empty' && fetchStatus !== 'error') return
    // ⚠ Only the OPENING fetch may fall back. Since the drill-down window follows the reader
    // (2026-08-06), an empty answer is also what jumping to a date behind the broker's M1 depth
    // returns — and silently changing timeframe under someone who has just asked for a date is the
    // "jumped somewhere they didn't ask for" failure this guard exists to prevent, arriving by a
    // route that did not exist when it was written.
    if (fetchCacheRef.current.get(selectedMin)?.candles.length) return
    autoFellBackRef.current = true
    setSelectedMin(baseMin)
  }, [fetchStatus, selectedMin, openMin, baseMin])

  // Rebuild session overlays after data changes (applyNewData can clear them) or a toggle.
  // Declared AFTER the data effect so candles are present when overlays are created.
  useEffect(() => {
    const chart = chartRef.current
    if (!chart) return
    chart.removeOverlay({ name: SESSION_BOX })
    for (const s of sessionBoxes) {
      if (!sessionsOn[s.name]) continue
      for (const w of s.windows) {
        // Skip a session window that falls entirely outside the loaded candles (no-data region).
        if (loadedLoTs == null || loadedHiTs == null || w.t1 < loadedLoTs || w.t0 > loadedHiTs)
          continue
        chart.createOverlay({
          name: SESSION_BOX,
          lock: true,
          points: [
            { timestamp: w.t0, value: w.top },
            { timestamp: w.t1, value: w.bottom },
          ],
          extendData: { color: s.color },
        })
      }
    }
  }, [sessionBoxes, sessionsOn, displayCandles, loadedLoTs, loadedHiTs]) // sessionBoxes already covers all days

  // Rebuild trade overlays after data changes or a toggle (same anchoring rationale as sessions).
  useEffect(() => {
    const chart = chartRef.current
    if (!chart) return
    chart.removeOverlay({ name: TRADE })
    if (!tradesOn) return
    if (loadedLoTs == null || loadedHiTs == null) return
    // Which trades are actually drawn, in the order they open. Collected BEFORE the draw loop
    // because a trade's chips now have to know what is beside them — see `barsToPrev` below — and
    // collected ONCE, so the two passes can never disagree about which trades are on the chart.
    // ⚠ A hidden trade must not crowd anything: everything filtered out here is not on the chart,
    // so it cannot be collided with, and the gaps are measured over the survivors only.
    const drawn = spec.trades
      .map((tr, i) => [i, tr] as const)
      // Only draw a trade whose ENTRY is within the loaded candles — one older than the data edge
      // would otherwise clamp its markers onto the plot's left edge (the no-data region).
      .filter(([, tr]) => tr.entryTime >= loadedLoTs && tr.entryTime <= loadedHiTs)
      .filter(([, tr]) => !(tr.layer && hiddenLayers.has(tr.layer))) // isolated via Strategies
      .filter(([, tr]) => outcomeVisible(tr)) // Winners / Scratches / Losers (Analysis menu)
      // ⚠ SORTED by entry, never assumed. A stack merges several strategies' books into one list
      // and nothing promises they arrive interleaved by time; "the trade before this one" has to
      // mean the one to its LEFT on the chart or the whole measurement is about the wrong pair.
      .sort(([, a], [, b]) => a.entryTime - b.entryTime)
    // Bar index of a timestamp — the last loaded bar at or before it. Binary search rather than a
    // time→index map: a trade's entry/exit is stamped by the runner's own timeframe, so on any
    // resampled or drilled view it lands INSIDE a bar rather than on its open, and an exact-match
    // map would report "not found" on most of them.
    const barAt = (ts: number) => {
      let lo = 0,
        hi = displayCandles.length - 1,
        at = 0
      while (lo <= hi) {
        const mid = (lo + hi) >> 1
        if (displayCandles[mid].time <= ts) {
          at = mid
          lo = mid + 1
        } else hi = mid - 1
      }
      return at
    }
    // Room either side of each entry, in BARS. Pixels are the overlay's business — it is the only
    // one that knows the zoom. Left is measured to the furthest-right bar of EVERYTHING already
    // drawn, not to the previous entry, so a long hold that is still open across the next two
    // entries is not reported as clear air.
    const gapPrev = new Map<number, number>()
    const gapNext = new Map<number, number>()
    let openTo = -Infinity
    for (const [k, [i, tr]] of drawn.entries()) {
      const entryBar = barAt(tr.entryTime)
      if (openTo > -Infinity) gapPrev.set(i, entryBar - openTo)
      const next = drawn[k + 1]
      if (next) gapNext.set(i, barAt(next[1].entryTime) - entryBar)
      openTo = Math.max(openTo, barAt(tr.exitTime))
    }
    for (const [i, tr] of drawn) {
      chart.createOverlay({
        name: TRADE,
        lock: true,
        points: [
          { timestamp: tr.entryTime, value: tr.entryPrice },
          { timestamp: tr.exitTime, value: tr.exitPrice },
        ],
        extendData: {
          dir: tr.dir,
          kind: tr.kind,
          // What the trade this one FOLLOWED did — decides `BE+` vs `SL+` on a re-entry. Absent on
          // every primary, and on any run stored before the field existed.
          after: tr.after,
          pnl: tr.pnl,
          outcome: tradeOutcome(tr), // won / scratch / lost — the chip and the fallback box colour
          // Scale-in lots. Without them the box can show a short exiting BELOW its entry for a
          // P&L of zero, with nothing on the chart to say where the profit went.
          adds: tr.adds,
          // …but not while the DETAIL layer is drawing them: each lot then gets a full box with its
          // own `Entry` label on the same pixel row, and two labels for one fill is noise that
          // reads as two fills.
          addsDetailed: tradeAddsOn && tradeAddCount > 0,
          // AMBER, not the entry's colour (Aaron's call, 2026-08-20). An add IS an entry, which is
          // why it used to share that colour — and the result was that the one line on the box
          // which is NOT the trade you opened looked identical to the line that is. `theme.warn` is
          // the palette's amber and already the third series colour, so it reads as its own thing
          // against the green/red the box is built from without adding a hue the chart lacks.
          // ⚠ Close in family to `TRADE_SCRATCH_COLOR` (#ff5c00) on the outcome chip; they are
          // #ffb300 amber vs orange-red and never share a pixel row, but if either moves, move it
          // AWAY from the other rather than toward it.
          addColor: theme.warn,
          color: outcomeColor(tradeOutcome(tr)), // fallback box (win green / scratch orange / loss red)
          dirColor: tr.dir === 'long' ? theme.pos : theme.neg, // entry arrow (buy green / sell red)
          // Profit-depth inputs — prices, converted to pixels in the overlay via the y-axis.
          // Absent fields make the overlay fall back to the plain entry→exit box.
          precision: pricePrecision, // every side label prints its own price
          showPrices: chartSettings.tradeLabelPrices, // reader preference — Chart settings → Trades
          // …and whether the annotations are drawn AT ALL. Off leaves the bands, the level lines
          // and their dots — the trade is read by shape and colour — and cuts the outcome chip
          // down to whatever NAMES this trade. See `Chart settings` in this folder's CLAUDE.md.
          showLabels: chartSettings.tradeLabels,
          entryPrice: tr.entryPrice,
          exitPrice: tr.exitPrice,
          mfePrice: tr.mfePrice,
          maePrice: tr.maePrice,
          profitLegs: tr.profitLegs,
          stopPrice: tr.stopPrice,
          tpTargets: tr.tpTargets, // TP ladder — first UNHIT one drawn faintly (near-miss view)
          // How much room the side chips have either way, in bars. Absent = nothing drawn that
          // side. The overlay turns them into pixels against the live bar width and parks its chips
          // on the side that is clear — the answer changes with the zoom, which is why it cannot be
          // decided here. See `barsToPrev` in `overlays.ts`.
          barsToPrev: gapPrev.get(i),
          barsToNext: gapNext.get(i),
          favColor: TRADE_PROFIT_FILL, // light mint — profit fill + take-profit lines
          advColor: TRADE_LOSS_COLOR, // red — adverse side + the stop
          // Portfolio stack: the entry marker takes the strategy's layer colour so overlapping
          // strategies read apart; a single-run trade has no layer → neutral, unchanged.
          entryColor: tr.layerColor ?? theme.textSecondary,
          scratchColor: TRADE_SCRATCH_COLOR, // orange outcome chip — a scratch is a THIRD verdict
          layerColor: tr.layerColor, // outcome-chip border + dot accent (stack only)
          layerName: tr.layerName, // named in the outcome chip: "SOS Fade · Won" (stack only)
          chipBg: theme.bgSurface, // dark chip behind the side labels (legible over candles)
          // The reversal candle at this trade's turn, by name — or `no candle` if its span had
          // none. `undefined` while the layer is OFF, and `undefined` must NOT render as "no": the
          // run has not been asked. Only switching the layer on turns the question into an answer.
          patternName:
            groupsOn[GROUP_CANDLE_MARKS] && atBaseTf
              ? // ⚠ Three states, not two. `no candle` = the span held no pattern at all;
                // `no matching candle` = it held some and none pointed the way this outcome asks about,
                // so the marks ARE on the chart and none of them earns the chip. Collapsing the two
                // would report a setup that plainly had candles in it as having had none.
                (tradePattern.named.get(i) ??
                (tradePattern.any.has(i) ? 'no matching candle' : 'no candle'))
              : undefined,
          neutralColor: theme.textTertiary,
        },
      })
    }
  }, [
    spec.trades,
    tradesOn,
    outcomeVisible,
    hiddenLayers,
    displayCandles,
    loadedLoTs,
    loadedHiTs,
    chartSettings,
    tradePattern,
    groupsOn,
    atBaseTf,
    tradeAddsOn,
    tradeAddCount,
  ])

  // SCALE-IN DETAIL — one full trade box per add lot. Same overlay template as a trade (registered
  // a second time as `TRADE_ADD`), so a lot gets the identical profit-depth view: the two-tone
  // green run, `Furthest`, `Deepest`, the exit line, the outcome chip. That reuse is the point —
  // a bespoke renderer here would be a second implementation of the trade box, free to disagree
  // with the real one about what "how far it ran" means.
  //
  // It reuses the TRADES effect's own predicates — the loaded-candle clip, the layer isolation, the
  // Winners/Losers filters — so the two layers can never disagree about which trades are of
  // interest, the same rule Trade fibs and the Step navigator follow. The lot is clipped on the
  // PARENT's entry rather than its own, for the same reason: a lot whose parent is off-screen has
  // nothing to sit under.
  //
  // ⚠ Unlike Trade fibs it DOES require `tradesOn` — an add box with no parent trade under it
  // reads as a trade the run never took.
  useEffect(() => {
    const chart = chartRef.current
    if (!chart) return
    chart.removeOverlay({ name: TRADE_ADD })
    if (!tradeAddsOn || !tradesOn) return
    for (const tr of spec.trades) {
      if (loadedLoTs == null || loadedHiTs == null) break
      if (tr.entryTime < loadedLoTs || tr.entryTime > loadedHiTs) continue
      if (tr.layer && hiddenLayers.has(tr.layer)) continue
      if (!outcomeVisible(tr)) continue
      for (const a of tr.adds ?? []) {
        // A lot with no recorded exit is one this run never measured — an older spec, or a
        // strategy that adds without tracking its lots. There is no box to draw from a fill price
        // alone, and inventing one from the parent's exit would report the BASE's exit as the
        // lot's. It keeps the plain `Add` line the parent draws and nothing more.
        if (typeof a.exitPrice !== 'number' || typeof a.exitTime !== 'number') continue
        // The lot's verdict is the SIGN of its own P&L and nothing better exists: the backend
        // grades whole trades against the run's median full loss, and a lot has no such scale of
        // its own. So there is no `scratch` here — three states would claim a measurement that was
        // never made. The chip says `Add · Won` / `Add · Lost` so it can never be mistaken for the
        // graded verdict on the trade it sits inside.
        const won = (a.pnl ?? 0) > 0
        const verdict: TradeOutcome = won ? 'won' : 'lost'
        chart.createOverlay({
          name: TRADE_ADD,
          lock: true,
          points: [
            { timestamp: a.ms, value: a.price },
            { timestamp: a.exitTime, value: a.exitPrice },
          ],
          extendData: {
            dir: tr.dir,
            pnl: a.pnl,
            outcome: verdict,
            color: outcomeColor(verdict),
            dirColor: tr.dir === 'long' ? theme.pos : theme.neg,
            precision: pricePrecision,
            showPrices: chartSettings.tradeLabelPrices,
            // With annotations off a lot keeps its `Add` chip — that is its NAME, and it is the
            // only thing separating a lot's box from the trade's own box drawn around it.
            showLabels: chartSettings.tradeLabels,
            entryPrice: a.price,
            exitPrice: a.exitPrice,
            mfePrice: a.mfePrice,
            maePrice: a.maePrice,
            // ⚠ NO `stopPrice`, and its absence is deliberate. A lot dies on the BASE's stop as the
            // base has trailed it, which is neither the base's initial 1R (what `tr.stopPrice`
            // holds) nor anything recorded per lot — so any line drawn here would be a stop the lot
            // never had. The overlay degrades without it; a wrong one would not announce itself.
            //
            // `tpTargets` is left out for the same reason: the adds bank on their OWN target
            // (`L-ATP`), not on the base's fib ladder, so the base's targets would draw a near-miss
            // against a level this lot was never aiming at.
            profitLegs: [{ price: a.exitPrice, label: a.exitReason?.split('-').pop() || 'Exit' }],
            favColor: TRADE_PROFIT_FILL,
            advColor: TRADE_LOSS_COLOR,
            // The lot's own `Entry` label takes the SAME amber the `Add` lines use, so one colour
            // means "this is an add" whichever of the two layers you are reading. On a stack the
            // parent trade still tints its entry by strategy; a lot does not, because which
            // strategy it belongs to is already stated by the trade box it sits inside.
            entryColor: theme.warn,
            // ⚠ Carried but UNREACHABLE for a lot, and deliberately so: `verdict` above is
            // `won ? 'won' : 'lost'`, because the backend grades whole trades against the run's
            // median full loss and a lot has no such scale of its own. Kept so the two layers pass
            // the same shape; if a lot ever gains a real third verdict, this is already right.
            scratchColor: TRADE_SCRATCH_COLOR,
            layerName: 'Add',
            chipBg: theme.bgSurface,
            neutralColor: theme.textTertiary,
          },
        })
      }
    }
  }, [
    spec.trades,
    tradeAddsOn,
    tradesOn,
    outcomeVisible,
    hiddenLayers,
    displayCandles,
    loadedLoTs,
    loadedHiTs,
    chartSettings,
    pricePrecision,
  ])

  // Trade fibs — the leg each trade was priced off. Rebuilt on data change like every other
  // overlay effect (`applyNewData` clears them).
  //
  // It reuses the TRADES effect's own predicates on purpose — the loaded-candle clip, the layer
  // isolation, the Winners/Losers filters — so the two layers can never disagree about WHICH trades
  // are of interest. Its own filters would be a second place for them to differ, which is the same
  // rule the Step navigator follows.
  //
  // It does NOT require `tradesOn`, because the row is a peer of Blocked/Missed rather than a
  // sub-toggle of Trades: a switch that is on while its layer draws nothing, with nothing on screen
  // saying why, is exactly the failure the per-window paging bug produced.
  useEffect(() => {
    const chart = chartRef.current
    if (!chart) return
    chart.removeOverlay({ name: TRADE_FIB })
    if (!tradeFibsOn) return
    for (const tr of spec.trades) {
      const fib = tr.fib
      if (!fib?.levels?.length) continue
      if (loadedLoTs == null || loadedHiTs == null) break
      if (tr.entryTime < loadedLoTs || tr.entryTime > loadedHiTs) continue
      if (tr.layer && hiddenLayers.has(tr.layer)) continue
      if (!outcomeVisible(tr)) continue
      // The leg's start, clamped into the loaded bars: a leg that began before the oldest loaded
      // candle would otherwise have klinecharts clamp its left edge onto the plot boundary, which
      // draws the ladder across the no-data region as if the leg started there.
      const from = Math.max(fib.startTime ?? tr.entryTime, loadedLoTs)
      chart.createOverlay({
        name: TRADE_FIB,
        lock: true,
        points: [
          { timestamp: from, value: fib.levels[0].price },
          { timestamp: tr.exitTime, value: fib.levels[fib.levels.length - 1].price },
        ],
        // The LADDER only. `entryRatio` / `deepestRatio` are still computed and still ride on the
        // spec — they are the two readings a price ladder cannot state — but nothing draws them:
        // the trade's own `Entry` and `Deepest` annotations say the same thing at the same price,
        // and two layers labelling one price row is what made this chart look doubled up.
        extendData: { levels: fib.levels, chipBg: theme.bgSurface },
      })
    }
  }, [
    spec.trades,
    tradeFibsOn,
    outcomeVisible,
    hiddenLayers,
    displayCandles,
    loadedLoTs,
    loadedHiTs,
  ])

  // Blocked setups — same rebuild-on-data-change rationale as the trades effect. Each marker
  // carries its own hover handlers, which is what turns the tag into "why didn't this trade":
  // klinecharts hands back the event's pixel coordinates, and the card is rendered in React.
  useEffect(() => {
    const chart = chartRef.current
    if (!chart) return
    chart.removeOverlay({ name: BLOCK })
    setMarkerTip(null)
    if (!blocksOn) return
    for (const b of blocks) {
      // Clipped to the loaded candles, like every other auto-generated overlay — klinecharts
      // clamps an out-of-range point onto the plot edge, which would pile every older marker
      // into the no-data region left of the drill-down edge.
      if (loadedLoTs == null || loadedHiTs == null) break
      if (b.time < loadedLoTs || b.time > loadedHiTs) continue
      if (!blockVisible(b)) continue // per-reason filters
      chart.createOverlay({
        name: BLOCK,
        lock: true,
        points: [{ timestamp: b.time, value: b.price }],
        extendData: {
          dir: b.dir,
          color: BLOCK_COLOR,
          textColor: theme.bgBase,
          text: b.reasons.length > 1 ? `Blocked ${b.reasons.length}` : 'Blocked',
        },
        onMouseEnter: (e) => {
          setMarkerTip({
            x: (e.pageX ?? 0) - window.scrollX,
            y: (e.pageY ?? 0) - window.scrollY,
            color: BLOCK_COLOR,
            title:
              `${b.dir === 'long' ? '▲ Long' : '▼ Short'} blocked` +
              (b.reasons.length > 1 ? ` — ${b.reasons.length} rules` : ''),
            met: [],
            reasons: b.reasons,
            price: b.price,
            strategy: b.layer ? layerName(b.layer) : undefined,
          })
          return true
        },
        onMouseLeave: () => {
          setMarkerTip(null)
          return true
        },
      })
    }
  }, [blocks, blocksOn, blockVisible, displayCandles, loadedLoTs, loadedHiTs, layerName])

  // Missed setups — identical machinery to Blocked (same template, same clipping, same hover
  // card), with the score on the tag instead of a rule count. `row: 1` parks these one step
  // further from the pane edge so the two layers shown together don't stack their tags.
  useEffect(() => {
    const chart = chartRef.current
    if (!chart) return
    chart.removeOverlay({ name: MISS })
    setMarkerTip(null)
    if (!missesOn) return
    for (const m of misses) {
      if (loadedLoTs == null || loadedHiTs == null) break
      if (m.time < loadedLoTs || m.time > loadedHiTs) continue
      if (!missVisible(m)) continue
      chart.createOverlay({
        name: MISS,
        lock: true,
        points: [{ timestamp: m.time, value: m.price }],
        extendData: {
          dir: m.dir,
          color: MISS_COLOR,
          textColor: theme.bgBase,
          row: 1,
          text: `${m.met}/${m.of}`,
        },
        onMouseEnter: (e) => {
          setMarkerTip({
            x: (e.pageX ?? 0) - window.scrollX,
            y: (e.pageY ?? 0) - window.scrollY,
            color: MISS_COLOR,
            title: `${m.dir === 'long' ? '▲ Long' : '▼ Short'} — ${m.met} of ${m.of}`,
            met: m.metLines,
            reasons: m.reasons,
            price: m.price,
            strategy: m.layer ? layerName(m.layer) : undefined,
          })
          return true
        },
        onMouseLeave: () => {
          setMarkerTip(null)
          return true
        },
      })
    }
  }, [misses, missesOn, missVisible, displayCandles, loadedLoTs, loadedHiTs, layerName])

  // The Step navigator's parked marker — one accent vline through it. A step CENTRES its target
  // rather than isolating it, so with several markers on screen "which one am I on?" has no answer
  // without this. Same rebuild-on-data-change rationale as every overlay above; same loaded-window
  // clip, which is also what makes the line vanish while a jump's bars are still landing.
  useEffect(() => {
    const chart = chartRef.current
    if (!chart) return
    chart.removeOverlay({ name: FOCUS })
    if (!navAt || loadedLoTs == null || loadedHiTs == null) return
    if (navAt.ts < loadedLoTs || navAt.ts > loadedHiTs) return
    chart.createOverlay({
      name: FOCUS,
      lock: true,
      points: [{ timestamp: navAt.ts, value: baseCandles[0]?.close ?? 0 }],
      extendData: { color: theme.accent, lineStyle: 'dashed', lineWidth: 1 },
    })
  }, [navAt, displayCandles, baseCandles, loadedLoTs, loadedHiTs])

  // Fibonacci drawings — re-created from state after any data change (applyNewData clears overlays,
  // same rationale as the trade/session effects), so a fib survives TF switches. Each carries
  // per-instance callbacks: onSelected marks it for the Delete key; onPressedMoveEnd writes an
  // anchor-drag back to state so the move persists too.
  useEffect(() => {
    const chart = chartRef.current
    if (!chart) return
    chart.removeOverlay({ name: FIB })
    for (const f of fibs) {
      chart.createOverlay({
        name: FIB,
        id: f.id,
        points: f.points,
        // No override → the tool default, read live (not snapshotted) — see the `fibs` state note.
        extendData: {
          levels: f.levels ?? fibLevels,
          precision: pricePrecision,
          chipBg: theme.bgSurface,
        },
        onSelected: () => {
          selectedFibRef.current = f.id
          return false
        },
        onDeselected: () => {
          if (selectedFibRef.current === f.id) selectedFibRef.current = null
          return false
        },
        // klinecharts REMOVES an overlay on right-click when onRightClick returns falsy — return true
        // to keep the fib, and stash its id so the React context menu offers "Delete this fib" instead.
        onRightClick: () => {
          ctxFibRef.current = f.id
          return true
        },
        onPressedMoveEnd: (e) => {
          const pts = (e.overlay.points ?? [])
            .filter((p) => typeof p.timestamp === 'number' && typeof p.value === 'number')
            .map((p) => ({ timestamp: p.timestamp as number, value: p.value as number }))
          if (pts.length >= 2)
            setFibs((prev) => prev.map((x) => (x.id === f.id ? { ...x, points: pts } : x)))
          return false
        },
      })
    }
  }, [fibs, fibLevels, displayCandles, pricePrecision])

  // Rebuild generic overlays (box/hline/vline) by group, after data changes or a group toggle.
  useEffect(() => {
    const chart = chartRef.current
    if (!chart) return
    chart.removeOverlay({ name: BOX })
    chart.removeOverlay({ name: HLINE })
    chart.removeOverlay({ name: VLINE })
    chart.removeOverlay({ name: LABEL })
    chart.removeOverlay({ name: CANDLE_MARK })
    const dummyValue = baseCandles[0]?.close ?? 0 // vline ignores y; needs a valid number
    // All visible structure labels go into ONE overlay so they de-collide together (see LABEL in
    // overlays.ts). Collected here, created after the loop.
    const labelPoints: { timestamp: number; value: number }[] = []
    const labelItems: LabelItem[] = []
    for (const ov of allOverlays) {
      if (!groupsOn[ov.group]) continue
      // Nested layers: an overlay can also depend on OTHER groups being on (see `requires` in
      // types.ts). This is what makes the four market-structure toggles nest exactly like the
      // TradingView ones — e.g. swing tags vanish with the structure that owns them, and historic
      // internal content needs "Internal Structure" on as well as its own toggle.
      if (ov.requires?.some((g) => groupsOn[g] === false)) continue
      // Portfolio stack: an anchored overlay draws while ANY leg that reported it is shown, so
      // isolating one strategy removes only the zones nothing else fired into. Inert on a single
      // run, where nothing carries `layers`.
      if (!overlayLayerVisible(ov)) continue
      // Skip any structure overlay outside the DRAW WINDOW — the viewport widened by a screen
      // either side, itself already clipped to the loaded candles (klinecharts clamps an
      // out-of-range point onto the plot edge, which is what piles old markers into the no-data
      // region of a drill-down). See the draw-window block above for why this is the viewport and
      // not the loaded history: overlay cost is superlinear in the count, and a chart shows ~200
      // bars whatever it holds.
      if (drawLoTs == null || drawHiTs == null) break
      const pointLike = ov.type === 'vline' || ov.type === 'label' || ov.type === 'candle'
      const oStart = pointLike ? ov.t : ov.t0
      const oEnd = pointLike ? ov.t : ov.t1
      if (oEnd < drawLoTs || oStart > drawHiTs) continue
      const style = {
        color: ov.style?.color ?? DEFAULT_OVERLAY_COLOR,
        fillColor: ov.style?.fillColor,
        lineStyle: ov.style?.lineStyle,
        lineWidth: ov.style?.lineWidth,
      }
      if (ov.type === 'box') {
        chart.createOverlay({
          name: BOX,
          lock: true,
          points: [
            { timestamp: ov.t0, value: ov.top },
            { timestamp: ov.t1, value: ov.bottom },
          ],
          extendData: { ...style, label: ov.label, labelAlign: ov.labelAlign },
        })
      } else if (ov.type === 'hline') {
        chart.createOverlay({
          name: HLINE,
          lock: true,
          points: [
            { timestamp: ov.t0, value: ov.price },
            { timestamp: ov.t1, value: ov.price },
          ],
          extendData: { ...style, label: ov.label },
        })
      } else if (ov.type === 'vline') {
        chart.createOverlay({
          name: VLINE,
          lock: true,
          points: [{ timestamp: ov.t, value: dummyValue }],
          extendData: style,
        })
      } else if (ov.type === 'candle') {
        // The row is hidden off the base timeframe (see `analysisGroups`), but `groupsOn` KEEPS the
        // reader's answer across the switch — so the draw has to be gated too, or a layer that is
        // no longer offered would still paint bars it does not describe.
        if (!atBaseTf) continue
        // Two reader filters, both of which only ever REMOVE marks the backend already decided to
        // draw — neither can invent one, which is what keeps them preferences rather than analysis.
        if (hiddenCandleDirs.has(candleDirKey(ov))) continue
        if (chartSettings.candleMarkDeepestOnly && !ov.deepestOf?.length) continue
        // FOUR points at ONE timestamp — high, low, open, close — so the template gets one x and
        // four y's and can rebuild the bar. klinecharts keeps every point it is handed regardless
        // of `totalStep`, which is what makes a 4-point overlay on a 2-step template legal.
        chart.createOverlay({
          name: CANDLE_MARK,
          lock: true,
          points: [
            { timestamp: ov.t, value: ov.high },
            { timestamp: ov.t, value: ov.low },
            { timestamp: ov.t, value: ov.open },
            { timestamp: ov.t, value: ov.close },
          ],
          extendData: {
            ...style,
            // OFF by default (Chart settings → Candlestick reversals). These tags carry no
            // cross-overlay de-collision — unlike the batched `LABEL` template — so two marks a few
            // bars apart write their names over the neighbouring candles. The navy IS the marker;
            // the name is what you switch on when you are asking which pattern it was.
            // ⚠ It names EVERY pattern on the bar, joined. It used to print `${label} +1`, which
            // reads as a claim about the PATTERN — *"how could a pattern have more than one
            // name?"* — when it is a fact about the BAR: one candle can satisfy several
            // definitions at once, and every Hanging Man is also a Hammer by construction. Two
            // names is a wider tag than one, and a tag nobody can interpret is worse.
            label:
              chartSettings.candleMarkLabels && ov.label
                ? ov.patterns?.length
                  ? ov.patterns.join(' · ')
                  : ov.label
                : undefined,
          },
        })
      } else if (ov.type === 'label') {
        labelPoints.push({ timestamp: ov.t, value: ov.price })
        labelItems.push({ text: ov.text, color: style.color, placement: ov.placement })
      }
    }
    if (labelPoints.length) {
      chart.createOverlay({
        name: LABEL,
        lock: true,
        points: labelPoints,
        extendData: { items: labelItems },
      })
    }
    // `chartSettings` is a dep because the candle-mark tag reads it; toggling it must redraw.
  }, [
    allOverlays,
    baseCandles,
    groupsOn,
    displayCandles,
    drawLoTs,
    drawHiTs,
    atBaseTf,
    chartSettings,
    hiddenCandleDirs,
    overlayLayerVisible,
  ])

  // Daily session-break vlines. Rebuilt after data changes (applyNewData can clear overlays).
  useEffect(() => {
    const chart = chartRef.current
    if (!chart) return
    chart.removeOverlay({ name: DAY_BREAK })
    if (!dayBreaksOn) return
    const dummyValue = baseCandles[0]?.close ?? 0
    for (const t of dailyBreaks) {
      // Skip a day break outside the loaded candles (no-data region).
      if (loadedLoTs == null || loadedHiTs == null || t < loadedLoTs || t > loadedHiTs) continue
      chart.createOverlay({
        name: DAY_BREAK,
        lock: true,
        points: [{ timestamp: t, value: dummyValue }],
        extendData: { color: DAY_BREAK_COLOR, lineStyle: 'dashed', lineWidth: 1 },
      })
    }
  }, [dailyBreaks, dayBreaksOn, displayCandles, baseCandles, loadedLoTs, loadedHiTs])

  // Drill-down data edge — a red dashed "no earlier data" line at the broker's oldest bar for the
  // active sub-base TF, so a true feed limit reads as a hard wall (not a blank chart). Rebuilt after
  // data changes (applyNewData clears overlays), same as the other vline overlays.
  useEffect(() => {
    const chart = chartRef.current
    if (!chart) return
    chart.removeOverlay({ name: DATA_EDGE })
    if (!dataEdge || dataEdge.tf !== selectedMin) return
    // Named off the ACTIVE drill-down TF, so every rung of the ladder reads correctly.
    const tfLabel = FETCH_TFS.find((tf) => tf.min === selectedMin)?.label
    const label = tfLabel ? `No earlier ${tfLabel} data` : 'No earlier data'
    chart.createOverlay({
      name: DATA_EDGE,
      lock: true,
      points: [{ timestamp: dataEdge.ts, value: displayCandles[0]?.close ?? 0 }],
      extendData: { color: theme.neg, label },
    })
  }, [dataEdge, selectedMin, displayCandles])

  // "Loading earlier bars" — the same marker for the opposite state: a dashed line at the oldest
  // loaded bar with the empty strip behind it shaded, while a page is in flight. Without it,
  // scrolling past the loaded bars is a blank screen that reads as the end of the data. Rebuilt
  // after every data change like the other vline overlays.
  //
  // ⚠ **It now fires for a fraction of a frame and that is correct, not dead.** A page used to be a
  // ~6s network round trip; since the spec carries the whole run it is an array slice. The overlay
  // is kept because the state it reports is still real — and because the drill-down path can still
  // genuinely wait on a broker. Its JUMP wording is gone with the jump's own progress readout: a
  // jump no longer pages at all.
  useEffect(() => {
    const chart = chartRef.current
    if (!chart) return
    chart.removeOverlay({ name: LOADING_EDGE })
    if (!pagingOlder || displayCandles.length === 0) return
    chart.createOverlay({
      name: LOADING_EDGE,
      lock: true,
      points: [{ timestamp: displayCandles[0].time, value: displayCandles[0].close }],
      extendData: { color: theme.accent, label: 'Loading earlier bars…' },
    })
  }, [pagingOlder, displayCandles])

  // Indicators (shipped series). Created once per spec/visibility; klinecharts re-runs the
  // indicator calc automatically on TF switch, so this does NOT depend on displayCandles.
  useEffect(() => {
    const chart = chartRef.current
    if (!chart) return
    for (const [name, paneId] of indicatorPanesRef.current) chart.removeIndicator(paneId, name)
    indicatorPanesRef.current.clear()
    const drawn: string[] = []
    spec.indicators.forEach((ind, i) => {
      if (!indicatorsOn[ind.name]) return
      drawn.push(ind.name)
      ensureSeriesIndicator(ind.name)
      const create = {
        name: ind.name,
        shortName: ind.name,
        series: ind.pane === 'main' ? IndicatorSeries.Price : IndicatorSeries.Normal,
        extendData: { series: ind.series, color: INDICATOR_PALETTE[i % INDICATOR_PALETTE.length] },
      }
      if (ind.pane === 'main') {
        chart.createIndicator(create, true, { id: 'candle_pane' })
        indicatorPanesRef.current.set(ind.name, 'candle_pane')
      } else {
        const paneId = chart.createIndicator(create, false, { height: 90 })
        if (paneId) indicatorPanesRef.current.set(ind.name, paneId)
      }
    })
    // Test seam only — see `data-indicators-on` on the root. Set from the same pass that creates
    // them, so it cannot claim a layer the chart is not drawing.
    setDrawnIndicatorNames((prev) =>
      prev.length === drawn.length && prev.every((n, i) => n === drawn[i]) ? prev : drawn
    )
  }, [spec.indicators, indicatorsOn])

  const measureStats = (rect: MeasureRect) => {
    if (rect.w < 5) return null
    const priceDiff = rect.endVal - rect.startVal
    const lo = Math.min(rect.startTs, rect.endTs)
    const hi = Math.max(rect.startTs, rect.endTs)
    return {
      priceDiff,
      pctChange: (priceDiff / rect.startVal) * 100,
      bars: displayCandles.filter((c) => c.time >= lo && c.time <= hi).length,
      durMs: Math.abs(rect.endTs - rect.startTs),
      up: priceDiff >= 0,
    }
  }

  const renderMeasRect = (rect: MeasureRect, key: string, strokeOpacity: number) => {
    const up = rect.endVal >= rect.startVal
    const fill = up ? 'rgba(38,166,154,0.2)' : 'rgba(239,83,80,0.2)'
    const stroke = up ? `rgba(38,166,154,${strokeOpacity})` : `rgba(239,83,80,${strokeOpacity})`
    const textColor = up ? '#26a69a' : '#ef5350'
    const stats = measureStats(rect)
    const labelW = 160
    const containerW = containerRef.current?.clientWidth ?? 9999
    const labelLeft =
      rect.x + rect.w + 8 + labelW > containerW ? rect.x - labelW - 8 : rect.x + rect.w + 8
    return (
      <Fragment key={key}>
        <div
          style={{
            position: 'absolute',
            left: rect.x,
            top: rect.y,
            width: Math.max(rect.w, 1),
            height: Math.max(rect.h, 1),
            background: fill,
            border: `1px solid ${stroke}`,
          }}
        />
        {stats && (
          <div
            style={{
              position: 'absolute',
              left: labelLeft,
              top: rect.y,
              width: labelW,
              background: '#1e222d',
              border: `1px solid ${stroke}`,
              borderRadius: 5,
              padding: '5px 9px',
              fontSize: 11,
              fontFamily: 'ui-monospace, monospace',
              lineHeight: 1.7,
              whiteSpace: 'nowrap',
              color: '#e2e8f0',
            }}
          >
            <div style={{ color: textColor }}>
              {up ? '↑' : '↓'} {up ? '+' : '−'}
              {fmtDiff(stats.priceDiff)} ({up ? '+' : '−'}
              {Math.abs(stats.pctChange).toFixed(2)}%)
            </div>
            <div style={{ color: '#94a3b8' }}>
              {stats.bars} bar{stats.bars !== 1 ? 's' : ''} · {fmtDuration(stats.durMs)}
            </div>
          </div>
        )}
      </Fragment>
    )
  }

  // Copy the current chart view as a PNG — like TradingView's snapshot button. klinecharts
  // renders the canvas (candles + every overlay: trades, sessions, indicators) to a data URL;
  // we copy it to the clipboard so it pastes straight into a chat, and fall back to a download
  // when the browser blocks clipboard image writes. The React measurement layer is a separate
  // DOM overlay and is deliberately not part of the snapshot.
  const [copied, setCopied] = useState(false)
  const copyChartImage = async () => {
    const chart = chartRef.current
    if (!chart) return
    let url: string
    try {
      url = chart.getConvertPictureUrl(true, 'png', theme.bgBase)
    } catch {
      toast.error('Could not render the chart image')
      return
    }
    const toBlob = fetch(url).then((r) => r.blob()) // pass the Promise to ClipboardItem (Safari-safe)
    try {
      const canClipboard = typeof ClipboardItem !== 'undefined' && !!navigator.clipboard?.write
      if (!canClipboard) throw new Error('clipboard unavailable')
      await navigator.clipboard.write([new ClipboardItem({ 'image/png': toBlob })])
      setCopied(true)
      setTimeout(() => setCopied(false), 1500)
      toast.success('Chart copied — paste it into the chat')
    } catch {
      const blob = await toBlob
      const href = URL.createObjectURL(blob)
      const tf =
        options.find((o) => o.min === selectedMin)?.label ?? spec.baseTimeframe.toUpperCase()
      const a = document.createElement('a')
      a.href = href
      a.download = `${spec.instrument}-${tf}.png`
      a.click()
      URL.revokeObjectURL(href)
      toast.message('Clipboard blocked — image downloaded instead')
    }
  }

  // Reset chart view (right-click menu) — restore the zoom/scroll captured at init, like TradingView.
  //
  // 🔴 **The PRICE axis has to be reset too, and it is a separate mechanism from the other three.**
  // `setBarSpace` / `setOffsetRightDistance` / `scrollToRealTime` are all the TIME axis; dragging
  // the price axis (or panning vertically once it is manual) switches the y axis off auto-scale and
  // klinecharts keeps that range for ever. So "Reset chart view" restored the horizontal view onto a
  // chart still showing a price window price had left — reported off a screen showing 5,100–5,460
  // with the market at 4,252, i.e. a chart that looks EMPTY, which reads as the reset having broken
  // it rather than half-finished it.
  //
  // ⚠ **klinecharts exposes no `resetYAxis`** — the only public route back is `setStyles` with a
  // valid `yAxis.type`, which flips the candle pane's `autoCalcTickFlag` back on and re-adjusts the
  // viewport. It is passed the type the chart already uses, so this changes nothing visually and is
  // purely the reset. Double-clicking the price axis is the same reset by hand, and the reason
  // nobody found this: the chart CAN be recovered, just not by the control that says it resets it.
  const resetView = () => {
    const chart = chartRef.current
    if (!chart) return
    if (defaultBarSpaceRef.current != null) chart.setBarSpace(defaultBarSpaceRef.current)
    if (defaultOffsetRef.current != null) chart.setOffsetRightDistance(defaultOffsetRef.current)
    chart.setStyles({ yAxis: { type: chart.getStyles().yAxis.type } })
    chart.scrollToRealTime()
  }

  // Fibonacci tool — arm klinecharts' native 2-click draw. On completion lift the two anchor points
  // into React state (the source of truth); the persistence effect re-creates it (and drops the
  // transient drawing overlay). Exits measure mode first so the two tools never fight for clicks.
  const startFib = () => {
    const chart = chartRef.current
    if (!chart) return
    setMeasureMode(false)
    setAnchor(null)
    setLiveDrag(null)
    setMeasurement(null)
    chart.createOverlay({
      name: FIB,
      extendData: { levels: fibLevels, precision: pricePrecision, chipBg: theme.bgSurface },
      onDrawEnd: (e) => {
        const pts = (e.overlay.points ?? [])
          .filter((p) => typeof p.timestamp === 'number' && typeof p.value === 'number')
          .map((p) => ({ timestamp: p.timestamp as number, value: p.value as number }))
        if (pts.length >= 2)
          setFibs((prev) => [...prev, { id: crypto.randomUUID(), points: pts.slice(0, 2) }])
        return false
      },
    })
  }

  const removeFib = (id: string) => {
    if (selectedFibRef.current === id) selectedFibRef.current = null
    if (ctxFibRef.current === id) ctxFibRef.current = null
    setFibs((prev) => prev.filter((f) => f.id !== id))
    setFibEditor((e) => (e?.fibId === id ? null : e)) // never leave the editor pointing at a deleted fib
  }

  // ── Level editor plumbing ───────────────────────────────────────────────────────────────────
  // The ladder the open editor is editing. A drawing with no override edits a COPY of the default,
  // which is what makes the first keystroke on a fib create its override rather than silently
  // retune every other fib on the chart.
  const fibEditorTarget = fibEditor?.fibId
    ? (fibs.find((f) => f.id === fibEditor.fibId) ?? null)
    : null
  const fibEditorLevels = fibEditor?.fibId ? (fibEditorTarget?.levels ?? fibLevels) : fibLevels

  const setFibEditorLevels = (next: FibLevel[]) => {
    if (!fibEditor) return
    if (fibEditor.fibId)
      setFibs((prev) => prev.map((f) => (f.id === fibEditor.fibId ? { ...f, levels: next } : f)))
    else setFibLevels(next)
  }

  const openFibEditor = (x: number, y: number, fibId: string | null) => {
    setFibEditor({ x, y, fibId })
    setFibEditorSeq((n) => n + 1) // re-seed the rows for the new target
  }

  // Promote this drawing's ladder to the default, then DROP its override so it goes back to
  // following — the two are identical at that moment, and following means later default edits keep
  // reaching it. Leaving the override behind would quietly freeze the fib you just saved from.
  const saveFibLevelsAsDefault = () => {
    if (!fibEditor?.fibId) return
    setFibLevels(fibEditorLevels)
    setFibs((prev) => prev.map((f) => (f.id === fibEditor.fibId ? { ...f, levels: undefined } : f)))
  }

  const clearFibOverride = () => {
    if (!fibEditor?.fibId) return
    setFibs((prev) => prev.map((f) => (f.id === fibEditor.fibId ? { ...f, levels: undefined } : f)))
    setFibEditorSeq((n) => n + 1)
  }

  const resetFibLevels = () => {
    setFibLevels(DEFAULT_FIB_LEVELS)
    setFibEditorSeq((n) => n + 1)
  }

  // Delete/Backspace removes the selected fib (ignored while typing); Escape closes the menu;
  // ← / → step the marker navigator — but ONLY while the pointer is over this panel. The arrow keys
  // belong to the page (and to any control on it) everywhere else, and a chart that swallowed them
  // globally would be a bug on every host that ever embeds two of these.
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      const el = document.activeElement as HTMLElement | null
      const tag = (el?.tagName ?? '').toLowerCase()
      const typing = tag === 'input' || tag === 'textarea' || !!el?.isContentEditable
      if (!typing && (e.key === 'Delete' || e.key === 'Backspace') && selectedFibRef.current) {
        const id = selectedFibRef.current
        selectedFibRef.current = null
        setFibs((prev) => prev.filter((f) => f.id !== id))
        e.preventDefault()
      }
      if (!typing && hoveredRef.current && (e.key === 'ArrowLeft' || e.key === 'ArrowRight')) {
        e.preventDefault()
        stepMarkerRef.current(e.key === 'ArrowRight' ? 1 : -1)
      }
      if (e.key === 'Escape') {
        setCtxMenu(null)
        setFibEditor(null)
      }
    }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [])

  // Close the right-click menu on any click/press outside it (the menu stops its own mousedown).
  useEffect(() => {
    if (!ctxMenu) return
    const close = () => setCtxMenu(null)
    window.addEventListener('mousedown', close)
    return () => window.removeEventListener('mousedown', close)
  }, [ctxMenu])

  // Same for the level editor (it stops its own mousedown, so every press inside is safe).
  useEffect(() => {
    if (!fibEditor) return
    const close = () => setFibEditor(null)
    window.addEventListener('mousedown', close)
    return () => window.removeEventListener('mousedown', close)
  }, [fibEditor])

  return (
    // The hover gate for the ← / → step keys covers the WHOLE panel, header included: clicking a
    // step arrow leaves the pointer on the button, and the keys must keep working from there.
    //
    // ⚠ `data-applied-lo`/`-hi` are a TEST SEAM and nothing reads them at runtime. klinecharts draws
    // its time axis into the CANVAS, so which window is applied is unreadable from the DOM — and
    // that is the one thing `tests/chart-paging.spec.ts` has to assert, because "the jump was fast"
    // is satisfied by a jump that lands nowhere near the date asked for. Measured before the paging
    // guard existed: a jump to 2020-06-01 came to rest on 2021-01-19 with a perfectly healthy chart
    // and no error. They are `displayCandles`' own bounds, reused — never a second derivation.
    //
    // ⚠ `data-view-centre` is the third such seam and the one that finally made "does a timeframe
    // switch keep my place?" answerable. The applied WINDOW is not the answer — a switch can leave
    // the window exactly where it was and still park the VIEW on its right edge, which is six weeks
    // from the date being read and is precisely what was reported. It is the same value the
    // drill-down anchors on, published rather than re-derived.
    //
    // ⚠ `data-indicators-on` is the same kind of seam for the same kind of reason: an indicator is
    // drawn INTO the candle pane's canvas, so "is the VWAP line on screen" has no DOM answer, and a
    // check that settles for "the menu row is ticked" would pass against a panel that draws nothing.
    // It reports the names actually handed to `createIndicator`, read off the same ref the removal
    // pass uses — never a second derivation of which layers are live.
    <div
      data-applied-lo={loadedLoTs ?? undefined}
      data-applied-hi={loadedHiTs ?? undefined}
      ref={rootRef}
      data-indicators-on={drawnIndicatorNames.join('|')}
      onMouseEnter={() => {
        hoveredRef.current = true
      }}
      onMouseLeave={() => {
        hoveredRef.current = false
      }}
    >
      {/* Header — TradingView layout: symbol/interval controls top-LEFT (timeframe + layers),
          the snapshot (Copy) top-RIGHT by the fullscreen exit. Chart TOOLS live on the vertical
          strip down the left edge of the chart body (below), not in this row. A host may inject its
          own title/exit via headerLeading/headerTrailing so its chrome shares this single top row. */}
      <div
        className={`relative flex items-center justify-between gap-2 flex-wrap mb-2 ${headerClassName ?? ''}`}
      >
        {/* Left cluster: optional host title + timeframe dropdown + layers dropdown + fetch status. */}
        <div className="flex items-center gap-2">
          {headerLeading}
          {/* Timeframe dropdown (TradingView-style): a button showing the current TF, opening a
              selectable list. Drill-down TFs (below the run's base) sit above a divider from the
              display TFs. */}
          <div ref={tfRef} className="relative">
            <button
              onClick={() => setTfOpen((o) => !o)}
              className="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-md border border-border-subtle bg-bg-sunken text-[11px] font-mono font-medium text-text-secondary hover:text-text-primary transition-colors"
            >
              {options.find((o) => o.min === selectedMin)?.label ??
                spec.baseTimeframe.toUpperCase()}
              {/* A drill-down is a network round trip (~4.5s measured), and until this landed the
                  ONLY sign of it was an 11px grey line further along the header — while the chart
                  went on showing the previous timeframe's candles, which look exactly like nothing
                  having happened. Reported as "1 min isn't working". */}
              {drillPending && <Loader2 className="w-3 h-3 text-accent animate-spin" />}
              <ChevronDown
                className={`w-3 h-3 text-text-tertiary transition-transform ${tfOpen ? 'rotate-180' : ''}`}
              />
            </button>
            {tfOpen && (
              <div
                className="absolute left-0 mt-1 min-w-[92px] rounded-md border border-border-subtle bg-bg-surface py-1 shadow-lg"
                style={{ zIndex: 50 }}
              >
                {options.map((tf, i) => {
                  // a thin rule between the sub-base drill-down TFs and the run's own display TFs
                  const divider = i > 0 && options[i - 1].min < baseMin && tf.min >= baseMin
                  return (
                    <Fragment key={tf.label}>
                      {divider && <div className="my-1 border-t border-border-subtle" />}
                      <button
                        onClick={() => {
                          pickTimeframe(tf.min)
                          setTfOpen(false)
                        }}
                        className={`block w-full px-3 py-1.5 text-left text-[11px] font-mono font-medium transition-colors ${
                          tf.min === selectedMin
                            ? 'bg-accent/10 text-accent'
                            : 'text-text-tertiary hover:bg-bg-sunken hover:text-text-secondary'
                        }`}
                      >
                        {tf.label}
                      </button>
                    </Fragment>
                  )
                })}
              </div>
            )}
          </div>

          {/* Go to date — sits next to the timeframe because it answers the other half of "what am I
              looking at": the TF picks the bar size, this picks WHERE. Bounded by the span the chart
              can actually reach, and hidden until there are candles to reach into. */}
          {jumpRange && <GoToDate lo={jumpRange.lo} hi={jumpRange.hi} onGo={goToDate} />}

          {/* Step — the other way of answering "WHERE": Go to date takes a calendar date, this walks
              the markers themselves, so reading a run's losers back to back costs two keys instead
              of a scroll hunt. It sits next to Go to date because they share that question, and it
              drives the same pager underneath. Hidden when the chart is showing nothing to step. */}
          {navMarkers.length > 0 && (
            <MarkerNav
              current={navIdx >= 0 ? navMarkers[navIdx] : null}
              idx={navIdx}
              total={navMarkers.length}
              onStep={stepMarker}
            />
          )}

          {/* Analysis: what the strategy DID with its signals — the trades it took (split by
              outcome) and the setups its own rules refused (split by reason). Deliberately its own
              dropdown, separate from Structure: Structure is what the MARKET drew, Analysis is what
              to interrogate about the run. Trades ALSO toggles from the right-click chart menu —
              both drive the same `tradesOn` state. */}
          {(spec.trades.length > 0 ||
            blocks.length > 0 ||
            misses.length > 0 ||
            analysisGroups.length > 0) && (
            <ToggleMenu
              title="Analysis"
              // Wider than the other two menus: the filter chips wrap inside it, and at 198 a
              // two-word reason ("No FVG in zone") took a line to itself, which is the one-row-per-
              // value shape the chips exist to replace.
              minWidth={262}
              items={[
                // ── Deep debug ───────────────────────────────────────────────────────────────
                // One row, at the top, above the layers it switches. It is ADDITIVE — it deepens
                // whatever the rows below are showing and never decides WHICH trades are drawn —
                // so it reads as "and show me the detail", not as a mode that owns the menu.
                // Hidden when the run carries nothing to deepen.
                ...(debugAvailable
                  ? [
                      {
                        key: 'deep-debug',
                        label: 'Deep debug',
                        color: theme.accent,
                        on: debugOn,
                        toggle: toggleDebug,
                        action: true,
                      },
                    ]
                  : []),
                // ── The layers themselves ────────────────────────────────────────────────────
                ...(spec.trades.length > 0
                  ? [
                      {
                        key: 'trades',
                        label: 'Trades',
                        color: TRADE_WIN_COLOR,
                        on: tradesOn,
                        toggle: () => setTradesOn((o) => !o),
                        count: spec.trades.length,
                        section: 'Signals',
                      },
                    ]
                  : []),
                // Winners/Losers FILTER Trades — so they are chips under the layer, not rows beside
                // it. Listed only while something they filter is on the chart: that is Trades or
                // Fibs, since both effects apply these two predicates, and hiding them with Fibs on
                // alone would leave the fibs silently filtered by a control nobody can see. Each
                // carries its count so the split is readable without opening the table.
                ...(spec.trades.length > 0 && (tradesOn || (tradeFibsOn && tradeFibCount > 0))
                  ? [
                      {
                        key: 'trade-outcome',
                        label: 'Show',
                        color: TRADE_WIN_COLOR,
                        chips: [
                          {
                            key: 'winners',
                            label: 'Winners',
                            on: winnersOn,
                            toggle: () => setWinnersOn((o) => !o),
                            count: outcomeCounts.wins,
                          },
                          // Listed only when the run HAS any — a permanently 0 chip on a strategy
                          // with no scratch band (or none in the band) is a control nobody can use,
                          // and its absence is the honest statement that nothing landed there.
                          ...(outcomeCounts.scratches > 0
                            ? [
                                {
                                  key: 'scratches',
                                  label: 'Scratches',
                                  on: scratchesOn,
                                  toggle: () => setScratchesOn((o) => !o),
                                  count: outcomeCounts.scratches,
                                },
                              ]
                            : []),
                          {
                            key: 'losers',
                            label: 'Losers',
                            on: losersOn,
                            toggle: () => setLosersOn((o) => !o),
                            count: outcomeCounts.losses,
                          },
                        ],
                      },
                    ]
                  : []),
                // Blocked sits under Trades — same subject (what happened to a signal), opposite
                // answer. Listed only when the run reports any: a runner that can't tell us would
                // otherwise show a permanently empty toggle.
                ...(blocks.length > 0
                  ? [
                      {
                        key: 'blocks',
                        label: 'Blocked',
                        color: BLOCK_COLOR,
                        on: blocksOn,
                        toggle: () => setBlocksOn((o) => !o),
                        count: shownBlockCount,
                      },
                    ]
                  : []),
                // …and one chip per REASON, so a rule can be isolated ("show me only what the veto
                // refused") or excluded. Each count is how many setups that rule refused — the
                // number this whole layer exists to produce. Same "only while the parent is on" rule
                // as Winners/Losers.
                ...(blocksOn && blockReasons.length > 0
                  ? [
                      {
                        key: 'blk-reasons',
                        label: 'Refused by',
                        color: BLOCK_COLOR,
                        chips: blockReasons.map((r) => ({
                          key: `blk-${r.label}`,
                          label: r.label,
                          count: r.count,
                          on: !hiddenReasons.has(r.label),
                          toggle: () => toggleReason(r.label),
                        })),
                      },
                    ]
                  : []),
                // Missed = the setups that never got as far as being refused. Listed after
                // Blocked because it's the same question one step earlier in the setup's life,
                // and only when the run reports any (an NT8/MT5 run reports none).
                ...(misses.length > 0
                  ? [
                      {
                        key: 'misses',
                        label: 'Missed',
                        color: MISS_COLOR,
                        on: missesOn,
                        toggle: () => setMissesOn((o) => !o),
                        count: shownMissCount,
                      },
                    ]
                  : []),
                // …the SCORE first, because it is the coarser cut and the one that separates two
                // genuinely different questions: a 3/3 had every confluence and still did not
                // trade, a 2/3 never got there. All start ON, so this narrows nothing until it is
                // used. Listed above the reasons deliberately — reason answers "why", score answers
                // "how close", and the reader picks the axis before the value.
                //
                // ⚠ THESE TWO SETS ARE EACH A COMPLETE PARTITION OF THE SAME MISSES, which is why
                // they are two CAPTIONED chip groups and not one indented list. Measured on the
                // shipped run: 35 + 417 = 452, and 179 + 238 + 21 + 10 + 4 = 452. Seven rows in one
                // column read as seven sub-filters of one thing and the counts read as
                // double-counting — reported from the screen in exactly those words.
                ...(missesOn && missScores.length > 0
                  ? [
                      {
                        key: 'mis-scores',
                        label: 'Score',
                        color: MISS_COLOR,
                        chips: missScores.map((s) => ({
                          key: `mis-score-${s.key}`,
                          label: s.key.replace('/', ' of '),
                          count: s.count,
                          on: !hiddenMissScores.has(s.key),
                          toggle: () => toggleMissScore(s.key),
                        })),
                      },
                    ]
                  : []),
                // …then one chip per MISSING confluence, same shape as Blocked's. Some start OFF —
                // the ones the strategy flagged as routine (see `spec.missNoise`) — so the layer
                // opens on the misses worth studying rather than every setup that simply never
                // retraced. Their counts are still listed, so nothing is hidden silently.
                ...(missesOn && missReasons.length > 0
                  ? [
                      {
                        key: 'mis-reasons',
                        label: 'Missing',
                        color: MISS_COLOR,
                        chips: missReasons.map((r) => ({
                          key: `mis-${r.label}`,
                          label: r.label,
                          count: r.count,
                          on: !hiddenMissReasons.has(r.label),
                          toggle: () => toggleMissReason(r.label),
                        })),
                      },
                    ]
                  : []),
                // ── CONTEXT ──────────────────────────────────────────────────────────────────
                // Everything below answers a different question from the three layers above it:
                // those are what the strategy DID with its signals, these are what was on the chart
                // when it did. They were peers in one flat list of nineteen rows, which is most of
                // why the menu read as a wall — nine of those rows are context and three of them
                // are one family. The caption is the whole fix; the rows are unchanged.
                ...(() => {
                  const LIQ = 'Liquidity — '
                  const row = (g: (typeof analysisGroups)[number], label: string) => ({
                    key: `ag-${g.name}`,
                    label,
                    color: g.color,
                    on: groupsOn[g.name],
                    toggle: () => toggleGroup(g.name),
                    count: g.count,
                  })
                  // Fibs — the fib LEG each trade was priced off. A PEER row, not a sub-toggle of
                  // Trades (Aaron's call, 2026-08-03): it is its own reading of the chart, and it
                  // draws with Trades off. It still obeys Winners/Losers, which is why those two are
                  // listed whenever this is on. Default OFF: eight lines per trade is a lot of
                  // chart, and the run reads fine without it.
                  const fibs: MenuItem[] =
                    tradeFibCount > 0
                      ? [
                          {
                            key: 'tradefibs',
                            label: 'Fibs',
                            color: theme.accent,
                            on: tradeFibsOn,
                            toggle: () => setTradeFibsOn((o) => !o),
                            count: tradeFibCount,
                          },
                        ]
                      : []
                  // Scale-in detail — every add lot as its own trade box. Listed only when the run's
                  // trades actually carry per-lot exits: a strategy that never adds has none, and a
                  // run finished before the strategy recorded them carries a fill price and nothing
                  // to draw a box from. The count is LOTS, not trades — it is how many extra boxes
                  // the toggle puts on the chart, which is the thing a reader is deciding about.
                  const scaleIns: MenuItem[] =
                    tradeAddCount > 0
                      ? [
                          {
                            key: 'tradeadds',
                            label: 'Scale-in detail',
                            color: theme.textSecondary,
                            on: tradeAddsOn,
                            toggle: () => setTradeAddsOn((o) => !o),
                            count: tradeAddCount,
                          },
                        ]
                      : []
                  // The zone layers — gaps, order blocks, the candle repaint. Each is drawn only
                  // where a trade was taken, refused or missed, so each is "and show me what this
                  // looked like there". Default OFF; the count is how many the run produced.
                  const zones: MenuItem[] = analysisGroups
                    .filter((g) => !g.name.startsWith(LIQ))
                    .flatMap((g) => [
                      row(g, g.name),
                      // …and, for the candle repaint only, the DIRECTION filter relative to the setup.
                      // All three start ON: the opposing tier is half the point of the layer, so
                      // hiding it is something the reader asks for and never a default that quietly
                      // answers "there was nothing at the turn".
                      ...(g.name === GROUP_CANDLE_MARKS && groupsOn[g.name]
                        ? [
                            {
                              key: 'candle-dirs',
                              label: 'Direction',
                              color: g.color,
                              chips: CANDLE_DIRS.map((d) => ({
                                key: `cd-${d.key}`,
                                label: d.label,
                                count: candleDirCounts[d.key] ?? 0,
                                on: !hiddenCandleDirs.has(d.key),
                                toggle: () => toggleCandleDir(d.key),
                              })),
                            },
                          ]
                        : []),
                    ])
                  // The three liquidity tiers take their own caption and drop the shared prefix from
                  // their labels. They are one family — H4 alone is 58% of every level a run draws —
                  // so as three peers of Fair Value Gaps they were three long wrapping rows saying
                  // the same word three times. The GROUP NAME is untouched: it is the contract with
                  // the backend and with `groupsOn`, and only the displayed label shortens.
                  const liq: MenuItem[] = analysisGroups
                    .filter((g) => g.name.startsWith(LIQ))
                    .map((g, i) => ({
                      ...row(g, g.name.slice(LIQ.length)),
                      ...(i === 0 ? { section: 'Liquidity' } : {}),
                    }))
                  const ctx = [...fibs, ...scaleIns, ...zones, ...liq]
                  // The caption opens the section, so it belongs on whichever row happens to be
                  // first — and never on top of a caption that is already there (a run carrying
                  // nothing but liquidity keeps "Liquidity", which is the more specific answer).
                  if (ctx.length > 0 && !ctx[0].section) ctx[0] = { ...ctx[0], section: 'Context' }
                  return ctx
                })(),
              ]}
            />
          )}

          {/* Structure: what the MARKET drew — the strategy-structure "bricks" and shipped indicators.
              Everything clock-driven (sessions, day breaks) lives in the on-chart legend instead. */}
          <ToggleMenu
            title="Structure"
            items={[
              ...structureGroups.map((g) => ({
                key: `g-${g.name}`,
                label: g.name,
                color: g.color,
                on: groupsOn[g.name],
                toggle: () => toggleGroup(g.name),
              })),
              ...spec.indicators.map((ind, i) => ({
                key: `i-${ind.name}`,
                label: ind.name,
                color: INDICATOR_PALETTE[i % INDICATOR_PALETTE.length],
                on: indicatorsOn[ind.name],
                toggle: () => toggleIndicator(ind.name),
              })),
            ]}
          />

          {/* Strategies: its OWN dropdown (not folded into Analysis — a stack's legs are a different
              kind of thing from a run's own trades). Appears only when the spec carries layered
              trades, i.e. a portfolio stack; a single-run chart never sees it. Toggling isolates one
              strategy's trades on the chart. */}
          {tradeLayers.length > 0 && (
            <ToggleMenu
              title="Strategies"
              minWidth={180}
              items={tradeLayers.map((l) => ({
                key: l.id,
                label: l.name,
                color: l.color,
                on: !hiddenLayers.has(l.id),
                toggle: () => toggleLayer(l.id),
              }))}
            />
          )}

          {isFetchMode &&
            (() => {
              // The TF itself is already shown in the dropdown — don't echo it here. Only surface a
              // STATE worth calling out (loading / feed offline / failed / at the broker's data edge).
              const warn = fetchStatus === 'empty' || fetchStatus === 'error'
              // While loading, the chart is showing the SHIPPED bars rather than nothing — say which,
              // because bars that don't match the TF button would otherwise be a silent lie.
              const text =
                fetchStatus === 'loading'
                  ? showingPlaceholder
                    ? `showing ${spec.baseTimeframe.toUpperCase()} — loading these bars…`
                    : 'loading these bars…'
                  : fetchStatus === 'empty'
                    ? 'none this far back'
                    : fetchStatus === 'error'
                      ? 'fetch failed'
                      : dataEdge
                        ? 'all the broker still has'
                        : ''
              if (!text) return null
              return (
                <span
                  className="text-[11px] font-mono"
                  style={{ color: warn ? theme.gold : theme.textTertiary }}
                >
                  {text}
                </span>
              )
            })()}
        </div>

        {/* Right cluster: the snapshot (Copy) button — camera icon only, right-inset by the chart's
            y-axis WIDTH so its right edge lands exactly on the price-axis line (a clean right angle),
            not over the price scale. The host's exit X (headerTrailing) is pinned to the far corner,
            beyond it. */}
        <div className="flex items-center gap-2" style={{ paddingRight: chartInset.axisW }}>
          {showCopy && (
            <button
              onClick={copyChartImage}
              title={copied ? 'Copied' : 'Copy chart image to clipboard'}
              className="inline-flex items-center justify-center w-8 h-8 text-text-tertiary hover:text-text-secondary transition-colors"
            >
              {copied ? (
                <Check className="w-[18px] h-[18px] text-accent" />
              ) : (
                <Camera className="w-[18px] h-[18px]" />
              )}
            </button>
          )}
        </div>
        {headerTrailing && (
          // Centred over the price-axis (y-axis) COLUMN on the right — the rightmost `axisW` px —
          // so the minimize button sits above the price scale, not jammed in the corner.
          <div
            className="absolute top-1/2 -translate-y-1/2 flex items-center justify-center"
            style={{ right: 0, width: Math.max(chartInset.axisW, 28) }}
          >
            {headerTrailing}
          </div>
        )}
      </div>

      {/* Chart body = a vertical TOOL STRIP (far left, like TradingView's drawing toolbar) + the
          chart. The toolbar sits OUTSIDE the measure-capturing wrapper on purpose, so clicking a
          tool button never registers as a measurement click. */}
      <div className="flex">
        <div
          className="flex flex-col items-center gap-1 py-2 border-r border-border-subtle bg-bg-sunken flex-shrink-0"
          style={{ width: 40 }}
        >
          <button
            onClick={() => {
              setMeasureMode((m) => !m)
              setAnchor(null)
              setLiveDrag(null)
              setMeasurement(null)
            }}
            title="Measure — click to anchor, move, click to lock. Click a measurement to clear."
            className={`flex items-center justify-center w-8 h-8 rounded-md border transition-colors ${
              measureMode
                ? 'border-accent/60 text-accent bg-accent/10'
                : 'border-transparent text-text-tertiary hover:text-text-secondary hover:bg-bg-surface'
            }`}
          >
            <Ruler className="w-5 h-5" />
          </button>
          <button
            onClick={startFib}
            title="Fibonacci retracement — click one swing, then the other. Right-click a fib → Fib levels / Delete this fib (or select it + Delete)."
            className="flex items-center justify-center w-8 h-8 rounded-md border border-transparent text-text-tertiary hover:text-text-secondary hover:bg-bg-surface transition-colors"
          >
            <AlignJustify className="w-5 h-5" />
          </button>
          {/* ⚠ The fib tool's own gear used to sit here, opening the DEFAULT ladder. It moved into
              Chart settings on 2026-08-06 (Aaron's ask) and was NOT left behind as a shortcut: two
              controls editing one ladder is two places for it to be answered from. One drawing's
              own levels are still reached by right-clicking that drawing, which is a different
              scope rather than a second route to this one. */}
          {/* More tools land here. */}

          {/* Chart settings — how the chart is DRAWN, for this reader, across every run. It sits at
              the BOTTOM of the strip (`mt-auto`), away from the drawing tools, because it is not a
              tool: those configure a DRAWING, this configures the chart. The full-size cog and the
              gap are the same distinction said twice. */}
          <div className="mt-auto" />
          {/* Host ACTIONS sit in the bottom cluster with the cog rather than in the header, so they
              survive fullscreen — the panel goes `position: fixed` over the whole app and takes the
              host's own chrome (its tab strip) off screen with it. Aaron's placement, 2026-08-08. */}
          {toolActions}
          <button
            onClick={(e) => {
              const r = e.currentTarget.getBoundingClientRect()
              setSettingsAt((s) => (s ? null : { x: r.right + 8, y: r.top }))
            }}
            title="Chart settings — how the chart is drawn (labels, colours). Saved in this browser; it never changes what a run measured."
            className={`flex items-center justify-center w-8 h-8 rounded-md border transition-colors ${
              settingsAt
                ? 'border-accent/60 text-accent bg-accent/10'
                : 'border-transparent text-text-tertiary hover:text-text-secondary hover:bg-bg-surface'
            }`}
          >
            <Settings className="w-4 h-4" />
          </button>
        </div>

        <div
          className="flex-1"
          style={{ position: 'relative' }}
          onClick={handleChartClick}
          onMouseMove={handleChartMove}
          onContextMenu={(e) => {
            e.preventDefault()
            // klinecharts' right-click (mousedown, button 2) fires BEFORE this DOM contextmenu, so a
            // right-click ON a fib has already stashed its id in ctxFibRef. Read + clear it: a fib
            // right-click → fib-only menu; an empty right-click (ref null) → chart-only menu.
            const fibId = ctxFibRef.current
            ctxFibRef.current = null
            // Clamp box for the menu — both branches carry two rows (fib: levels + delete;
            // chart: reset view + show/hide trades). Bump these if either grows a row.
            const MENU_W = 190,
              MENU_H = 96
            setCtxMenu({
              x: Math.min(e.clientX, window.innerWidth - MENU_W),
              y: Math.min(e.clientY, window.innerHeight - MENU_H),
              fibId,
            })
          }}
        >
          <div ref={containerRef} className="w-full" style={{ height }} />

          {/* 🔴 **The loading badge, and it is the fix for "1 min isn't working".** A drill-down is a
              real round trip — MEASURED at ~4.5s per 12,000-bar window on a warm cache — and the
              panel deliberately keeps the PREVIOUS timeframe's candles on screen throughout, because
              a blank chart is worse. The consequence nobody had answered for is that the two states
              look identical: the same candles, the same position, and an 11px grey line in the
              header as the only difference. So it is a badge over the plot, it NAMES BOTH
              timeframes — the one being fetched and the one you are looking at meanwhile — and it is
              `pointer-events: none` so it cannot eat a click on the chart under it. */}
          {(drillPending || drillUnavailable) && (
            <div
              className={`absolute left-1/2 -translate-x-1/2 flex items-center gap-2 rounded-md border bg-bg-surface/95 px-3 py-1.5 shadow-lg ${
                drillPending ? 'border-accent/40' : 'border-warn-text/50'
              }`}
              style={{ top: 12, pointerEvents: 'none', zIndex: 3 }}
              title={fetchNote ?? undefined}
            >
              {drillPending ? (
                <Loader2 className="w-3.5 h-3.5 text-accent animate-spin" />
              ) : (
                <EyeOff className="w-3.5 h-3.5 text-warn-text" />
              )}
              <span className="text-[11px] font-mono text-text-secondary">
                {drillPending ? (
                  <>
                    loading <span className="text-accent">{drillLabel(selectedMin)}</span> bars
                    {showingPlaceholder && (
                      <> — showing {spec.baseTimeframe.toUpperCase()} meanwhile</>
                    )}
                  </>
                ) : (
                  <>
                    <span className="text-warn-text">{drillLabel(selectedMin)}</span>
                    {' — '}
                    {fetchNote
                      ? shortNote(fetchNote)
                      : fetchStatus === 'error'
                        ? 'the request failed'
                        : 'no bars this far back'}
                    {showingPlaceholder && <> · showing {spec.baseTimeframe.toUpperCase()}</>}
                  </>
                )}
              </span>
            </div>
          )}

          {/* Measurement display layer — pointer-events:none so klinecharts canvas gets all events
              (crosshair, scrolling, etc.) and our onClick/onMouseMove handlers fire via bubbling */}
          <div
            style={{
              position: 'absolute',
              top: 0,
              left: 0,
              right: 0,
              bottom: 0,
              pointerEvents: 'none',
              zIndex: 1,
            }}
          >
            {measurement && renderMeasRect(measurement, measurement.id, 1)}
            {liveDrag && renderMeasRect(liveDrag, 'live', 0.85)}
          </div>

          {/* Marker hover card — the "why is there no trade here?" answer, shared by the Blocked
              and Missed layers. */}
          {markerTip && <MarkerTipCard tip={markerTip} precision={pricePrecision} />}

          {/* On-chart "Sessions" legend (TradingView indicator-legend style) — everything CLOCK-driven
              lives here: the session windows and the daily session breaks. Day breaks used to sit in
              the header dropdown, which put the two halves of "when did the day/session start" in two
              different places. Sits on LINE 2, directly under the pinned OHLC readout (line 1), so it
              no longer covers the statistics.
              stopPropagation so a click here never trips measure-mode anchoring. */}
          {(spec.sessions.length > 0 || dailyBreaks.length > 0) && (
            <div
              ref={sessionsLegendRef}
              className="absolute"
              style={{ top: 32, left: 8, zIndex: 2 }}
              onClick={(e) => e.stopPropagation()}
            >
              <button
                onClick={() => setSessionsLegendOpen((o) => !o)}
                className="inline-flex items-center gap-1.5 px-2 py-1 rounded-md border border-border-subtle bg-bg-surface text-[11px] font-medium text-text-secondary hover:text-text-primary transition-colors shadow-sm"
              >
                <span
                  className="w-2 h-2 rounded-full"
                  style={{
                    background: anyClockLayerOn ? theme.accent : 'transparent',
                    boxShadow: `inset 0 0 0 1px ${theme.accent}`,
                  }}
                />
                Sessions
                <span className="font-mono text-text-tertiary">
                  {clockLayerCount.on}/{clockLayerCount.total}
                </span>
                <ChevronDown
                  className={`w-3 h-3 text-text-tertiary transition-transform ${sessionsLegendOpen ? 'rotate-180' : ''}`}
                />
              </button>
              {sessionsLegendOpen && (
                <div className="mt-1 min-w-[168px] rounded-md border border-border-subtle bg-bg-surface py-1 shadow-lg">
                  <button
                    onClick={() => setAllClockLayers(!anyClockLayerOn)}
                    className="flex w-full items-center gap-2 px-3 py-1.5 text-left text-[11px] font-medium text-text-secondary hover:bg-bg-sunken hover:text-text-primary transition-colors"
                  >
                    {anyClockLayerOn ? (
                      <EyeOff className="w-3 h-3 text-text-tertiary" />
                    ) : (
                      <Eye className="w-3 h-3 text-text-tertiary" />
                    )}
                    {anyClockLayerOn ? 'Hide all' : 'Show all'}
                  </button>
                  <div className="my-1 border-t border-border-subtle" />
                  {spec.sessions.map((s) => (
                    <button
                      key={s.name}
                      onClick={() => toggleSession(s.name)}
                      className="flex w-full items-center gap-2 px-3 py-1.5 text-left text-[11px] font-medium transition-colors hover:bg-bg-sunken"
                    >
                      <span
                        className="w-2 h-2 rounded-full flex-shrink-0"
                        style={{
                          background: sessionsOn[s.name] ? s.color : 'transparent',
                          boxShadow: `inset 0 0 0 1px ${s.color}`,
                          opacity: sessionsOn[s.name] ? 1 : 0.5,
                        }}
                      />
                      <span
                        className={sessionsOn[s.name] ? 'text-text-primary' : 'text-text-tertiary'}
                      >
                        {s.name}
                      </span>
                      {sessionsOn[s.name] && (
                        <Check className="w-3 h-3 ml-auto flex-shrink-0 text-accent" />
                      )}
                    </button>
                  ))}
                  {/* Day breaks — the DAILY session boundary, so it belongs with the session windows
                      rather than in the header. Ruled off because it draws a different shape (a
                      vertical line, not a box). */}
                  {dailyBreaks.length > 0 && (
                    <>
                      {spec.sessions.length > 0 && (
                        <div className="my-1 border-t border-border-subtle" />
                      )}
                      <button
                        onClick={() => setDayBreaksOn((o) => !o)}
                        className="flex w-full items-center gap-2 px-3 py-1.5 text-left text-[11px] font-medium transition-colors hover:bg-bg-sunken"
                      >
                        <span
                          className="w-2 h-2 rounded-full flex-shrink-0"
                          style={{
                            background: dayBreaksOn ? DAY_BREAK_COLOR : 'transparent',
                            boxShadow: `inset 0 0 0 1px ${DAY_BREAK_COLOR}`,
                            opacity: dayBreaksOn ? 1 : 0.5,
                          }}
                        />
                        <span className={dayBreaksOn ? 'text-text-primary' : 'text-text-tertiary'}>
                          Day breaks
                        </span>
                        {dayBreaksOn && (
                          <Check className="w-3 h-3 ml-auto flex-shrink-0 text-accent" />
                        )}
                      </button>
                    </>
                  )}
                </div>
              )}
            </div>
          )}
        </div>
      </div>

      {/* Right-click context menu (viewport-fixed at the cursor) — TradingView-style. Stops its own
          mousedown so a click inside doesn't trip the outside-close listener. */}
      {ctxMenu && (
        <div
          onMouseDown={(e) => e.stopPropagation()}
          className="fixed min-w-[172px] rounded-md border border-border-subtle bg-bg-surface py-1 shadow-xl"
          style={{ left: ctxMenu.x, top: ctxMenu.y, zIndex: 60 }}
        >
          {ctxMenu.fibId ? (
            // Right-clicked ON a fib → fib-only menu (managing a fib is its own context; deleting one
            // at a time, per Aaron — no reset, no bulk remove here).
            <>
              <button
                onClick={() => {
                  openFibEditor(ctxMenu.x, ctxMenu.y, ctxMenu.fibId)
                  setCtxMenu(null)
                }}
                className="flex w-full items-center gap-2 px-3 py-1.5 text-left text-[11px] font-medium text-text-secondary hover:bg-bg-sunken hover:text-text-primary transition-colors"
              >
                <Settings2 className="w-3 h-3 text-text-tertiary" /> Fib levels
              </button>
              <button
                onClick={() => {
                  removeFib(ctxMenu.fibId!)
                  setCtxMenu(null)
                }}
                className="flex w-full items-center gap-2 px-3 py-1.5 text-left text-[11px] font-medium text-neg-text hover:bg-bg-sunken transition-colors"
              >
                <Trash2 className="w-3 h-3" /> Delete this fib
              </button>
            </>
          ) : (
            // Right-clicked on empty chart → chart-only menu: reset the view + show/hide trades.
            <>
              <button
                onClick={() => {
                  resetView()
                  setCtxMenu(null)
                }}
                className="flex w-full items-center gap-2 px-3 py-1.5 text-left text-[11px] font-medium text-text-secondary hover:bg-bg-sunken hover:text-text-primary transition-colors"
              >
                <RotateCcw className="w-3 h-3 text-text-tertiary" /> Reset chart view
              </button>
              {spec.trades.length > 0 && (
                <button
                  onClick={() => {
                    setTradesOn((o) => !o)
                    setCtxMenu(null)
                  }}
                  className="flex w-full items-center gap-2 px-3 py-1.5 text-left text-[11px] font-medium text-text-secondary hover:bg-bg-sunken hover:text-text-primary transition-colors"
                >
                  {tradesOn ? (
                    <EyeOff className="w-3 h-3 text-text-tertiary" />
                  ) : (
                    <Eye className="w-3 h-3 text-text-tertiary" />
                  )}
                  {tradesOn ? 'Hide trades' : 'Show trades'}
                </button>
              )}
            </>
          )}
        </div>
      )}

      {/* Fib level editor — one component, two targets: the tool's default ladder (gear on the tool
          strip) or one drawing's own (its right-click menu). Rendered at the panel root, like the
          context menu, so the chart body's measure-mode click handler can never see its clicks. */}
      {fibEditor && (
        <FibSettings
          x={fibEditor.x}
          y={fibEditor.y}
          scope={fibEditor.fibId ? 'drawing' : 'default'}
          levels={fibEditorLevels}
          resetKey={`${fibEditor.fibId ?? 'default'}:${fibEditorSeq}`}
          isCustom={!!fibEditorTarget?.levels && !sameFibLevels(fibEditorTarget.levels, fibLevels)}
          onChange={setFibEditorLevels}
          onClose={() => setFibEditor(null)}
          onSaveAsDefault={saveFibLevelsAsDefault}
          onUseDefault={clearFibOverride}
          onResetFactory={resetFibLevels}
        />
      )}

      {/* Chart settings — rendered at the panel root like the fib editor and the context menu, so
          the chart body's measure-mode click handler can never see its clicks. */}
      {settingsAt && (
        <ChartSettingsPanel
          x={settingsAt.x}
          y={settingsAt.y}
          settings={chartSettings}
          onChange={setChartSettings}
          onClose={() => setSettingsAt(null)}
          renderCustom={(section) =>
            section === 'fibLevels' ? (
              <FibLevelEditor
                scope="default"
                levels={fibLevels}
                // The panel is mounted only while open, so the editor seeds from the live ladder on
                // every open; the seq is what re-seeds it when Reset replaces the set underneath.
                // Shared with the per-drawing popover deliberately — `resetFibLevels` bumps it and
                // both editors are showing the same ladder at that moment.
                resetKey={`default:${fibEditorSeq}`}
                maxRowsHeight={220}
                onChange={setFibLevels}
                onResetFactory={resetFibLevels}
              />
            ) : null
          }
        />
      )}
    </div>
  )
}
