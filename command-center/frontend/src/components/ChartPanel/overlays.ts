/**
 * Custom klinecharts overlay templates — all generic and data-driven (no strategy logic).
 * Each template renders from the points + `extendData` it is given; the panel decides what to
 * create from the spec. `registerChartOverlays()` is idempotent and called once on mount.
 */
import { registerOverlay, type OverlayCreateFiguresCallbackParams, type OverlayFigure } from 'klinecharts'

/** A rectangle hugging the candles inside a session window (Step 3). */
export const SESSION_BOX = 'lwgSessionBox'

/** Entry arrow + dashed line to exit + exit dot for one trade (Step 4). */
export const TRADE = 'lwgTrade'

/** Generic strategy-structure overlays (Step 5), driven entirely by spec.overlays. */
export const BOX = 'lwgBox'
export const HLINE = 'lwgHline'
export const VLINE = 'lwgVline'

/** Point-anchored text label (Step 7c) — market-structure break tags (BOS/SOS/iBOS) and
 *  swing-point labels (HH/HL/LH/LL/ASH/ASL + internal iSH…). */
export const LABEL = 'lwgLabel'

/** Market-structure overlay groups (emitted by backend `structure_overlays.py`). Kept in one place
 *  so the panel can (a) default them OFF — unlike other overlay groups — and (b) order them together
 *  in the Layers menu. MUST match the GROUP_* names in the backend module. */
export const STRUCTURE_GROUPS = [
  'External Structure',
  'Internal Structure',
  'Internal (Historic)',
  'Swing Point Labels',
] as const

/** Daily session-break marker (Step 6) — a vline drawn under a separate name so the generic
 *  vline group and the day breaks can be removed/toggled independently. */
export const DAY_BREAK = 'lwgDayBreak'

/** Drill-down data edge — a red dashed "no earlier data" line at the broker's oldest available bar
 *  for the current sub-base TF (a TRUE feed limit, not our render cap). */
export const DATA_EDGE = 'lwgDataEdge'

/** User-drawn Fibonacci retracement tool (2 anchor points → horizontal levels + price labels). */
export const FIB = 'lwgFib'

interface FibLevel { ratio: number; color: string }
interface FibExtend { levels?: FibLevel[]; precision?: number; chipBg?: string }

// Aaron's Fibonacci retracement levels + colours (his TradingView setup). 0 & 1 share a neutral
// grey; the retracement zone runs green (shallow) → blue (the OTE band) → red (deep 0.886).
export const DEFAULT_FIB_LEVELS: FibLevel[] = [
  { ratio: 0,     color: '#9598a1' }, // neutral (same as 1)
  { ratio: 0.382, color: '#22c55e' }, // green
  { ratio: 0.5,   color: '#22c55e' }, // green
  { ratio: 0.618, color: '#2962ff' }, // blue
  { ratio: 0.702, color: '#2962ff' }, // blue
  { ratio: 0.786, color: '#2962ff' }, // blue
  { ratio: 0.886, color: '#ef5350' }, // red
  { ratio: 1,     color: '#9598a1' }, // neutral (same as 0)
]

/** Style + label passed to generic overlays via `extendData`. Mirrors spec OverlayStyle. */
interface OverlayExtend {
  color?: string
  fillColor?: string
  lineStyle?: 'solid' | 'dashed'
  lineWidth?: number
  label?: string
}

/** One structure text label — the batched LABEL overlay carries an array of these in `extendData.items`,
 *  parallel to its `points`, so all chips de-collide together in the callback. */
export interface LabelItem {
  text: string
  color: string
  placement?: 'above' | 'below' | 'center'
}

/** Everything the profit-depth TRADE overlay reads. All prices optional — the overlay
 *  degrades to the plain outcome box when the rich fields (mfe / legs) are absent. */
interface TradeExtend {
  dir?: 'long' | 'short'
  kind?: 'primary' | 'secondary'
  pnl?: number
  color?: string       // outcome colour (win green / loss red) — the fallback box
  dirColor?: string    // entry-arrow colour (long green / short red) — fallback box only
  favColor?: string    // favourable-side green (the profit fill / lines — a LIGHT mint, kept
                       // distinct from the candle up-colour so the band never blends into green candles)
  advColor?: string    // adverse-side red (loser fill + the stop)
  entryColor?: string  // entry bubble + line + chip (neutral)
  chipBg?: string      // side-label chip background (dark, for legibility over candles)
  neutralColor?: string
  entryPrice?: number
  exitPrice?: number
  mfePrice?: number
  maePrice?: number
  profitLegs?: Array<number | { price: number; label: string }> // {price,label}; bare number tolerated
  stopPrice?: number
  tpTargets?: number[] // TP ladder nearest→furthest; first UNHIT one drawn faintly (near-miss view)
}

// Draw the next UNHIT take-profit only when the trade got at least this far toward it (mfe covered
// this fraction of the gap from the last hit level) — the "close enough to the next TP" filter, so a
// trade that barely nudged past TP1 doesn't sprout a far-away TP2 line.
const NEXT_TP_SHOW_FRAC = 0.33

/** '#rrggbb' / '#rgb' → 'rgba(r,g,b,a)'. Non-hex input is returned unchanged. */
function withAlpha(color: string, a: number): string {
  if (!color.startsWith('#')) return color
  const h = color.slice(1)
  const full = h.length === 3 ? h.split('').map(c => c + c).join('') : h
  const r = parseInt(full.slice(0, 2), 16)
  const g = parseInt(full.slice(2, 4), 16)
  const b = parseInt(full.slice(4, 6), 16)
  return `rgba(${r}, ${g}, ${b}, ${a})`
}

let registered = false

export function registerChartOverlays(): void {
  if (registered) return
  registered = true

  registerOverlay({
    name: SESSION_BOX,
    totalStep: 2,
    lock: true,
    needDefaultPointFigure: false,
    needDefaultXAxisFigure: false,
    needDefaultYAxisFigure: false,
    createPointFigures: ({ coordinates, overlay }) => {
      if (coordinates.length < 2) return []
      const [a, b] = coordinates
      const x = Math.min(a.x, b.x)
      const y = Math.min(a.y, b.y)
      const width = Math.max(1, Math.abs(b.x - a.x))
      const height = Math.max(1, Math.abs(b.y - a.y))
      const data = (overlay.extendData ?? {}) as { color?: string; label?: string }
      const color = data.color ?? '#888888'

      const figures: OverlayFigure[] = [
        {
          type: 'rect',
          attrs: { x, y, width, height },
          styles: {
            style: 'stroke_fill',
            color: withAlpha(color, 0.10),
            borderColor: withAlpha(color, 0.45),
            borderSize: 1,
            borderStyle: 'solid',
          },
          ignoreEvent: true,
        },
      ]
      return figures
    },
  })

  // Profit-depth trade view. From the entry it fills BOTH sides of the trade. Favourable (green):
  // solid entry→where profit was actually banked (`profitLegs` / the exit), faint on to the deepest
  // point it ran (`mfePrice`) without banking. Adverse (red): the mirror — a winner shows one FAINT
  // band entry→`maePrice` (the drawdown it sat through and recovered), a loser a DARKER band
  // entry→stop (up to the stop line) with a faint tail if price ran past the stop. It draws a green
  // line at each real profit-take; entry / stop / deepest are guide lines. When the rich fields are
  // absent it degrades to the plain entry→exit outcome box, so it works for any runner/strategy.
  // Prices → pixels via the callback's `yAxis`; the two overlay points give the entry/exit x-span.
  registerOverlay({
    name: TRADE,
    totalStep: 2,
    lock: true,
    needDefaultPointFigure: false,
    needDefaultXAxisFigure: false,
    needDefaultYAxisFigure: false,
    createPointFigures: ({ coordinates, overlay, yAxis }) => {
      if (coordinates.length < 2) return []
      const [entry, exit] = coordinates
      const d = (overlay.extendData ?? {}) as TradeExtend
      const favColor = d.favColor ?? '#00ff7f'
      const advColor = d.advColor ?? '#ff3b5c'
      const outcome = d.color ?? favColor
      const arrowColor = d.dirColor ?? outcome
      const isLong = d.dir !== 'short'
      const secondary = d.kind === 'secondary'
      const sign = isLong ? 1 : -1 // favourable ⇔ (price − entry) * sign > 0

      const x0 = Math.min(entry.x, exit.x)
      const x1 = Math.max(entry.x, exit.x)
      const w = Math.max(1, x1 - x0)
      const yOf = (p?: number): number | null =>
        (yAxis && typeof p === 'number') ? yAxis.convertToPixel(p) : null

      // Small entry marker (orientation carries direction): long = up-triangle below the bar,
      // short = down-triangle above it.
      const HALF = 6, HEIGHT = 9, GAP = 4
      const arrowFig = (): OverlayFigure => ({
        type: 'polygon',
        attrs: { coordinates: [
          { x: entry.x, y: isLong ? entry.y + GAP : entry.y - GAP },
          { x: entry.x - HALF, y: isLong ? entry.y + GAP + HEIGHT : entry.y - GAP - HEIGHT },
          { x: entry.x + HALF, y: isLong ? entry.y + GAP + HEIGHT : entry.y - GAP - HEIGHT },
        ] },
        styles: { style: 'fill', color: arrowColor },
        ignoreEvent: true,
      })

      // Each leg is {price, label} from chart_spec; tolerate a bare number too (older cached
      // specs) by auto-labelling in exit order (TP1, TP2, …, last = Exit).
      const legs = (d.profitLegs ?? [])
        .map((l, i, a): { price: number; label: string } =>
          typeof l === 'number'
            ? { price: l, label: i === a.length - 1 && a.length > 1 ? 'Exit' : `TP${i + 1}` }
            : l)
        .filter(l => l && typeof l.price === 'number')
      const legPrices = legs.map(l => l.price)
      // banked = deepest price where real profit was taken; a plain win with no leg detail banks
      // at its exit price.
      const bankedPrice: number | null =
        legPrices.length ? (isLong ? Math.max(...legPrices) : Math.min(...legPrices))
        : (typeof d.pnl === 'number' && d.pnl > 0 && typeof d.exitPrice === 'number') ? d.exitPrice
        : null
      const mfePrice: number | undefined =
        typeof d.mfePrice === 'number' ? d.mfePrice
        : bankedPrice != null ? bankedPrice
        : d.exitPrice
      const rich = yAxis != null && typeof mfePrice === 'number' &&
        (legs.length > 0 || typeof d.mfePrice === 'number')

      if (!rich) {
        // Degrade: the plain entry→exit outcome box + entry arrow (a data-poor NT8/MT5 trade).
        const y = Math.min(entry.y, exit.y)
        const h = Math.max(1, Math.abs(exit.y - entry.y))
        return [
          { type: 'rect', attrs: { x: x0, y, width: w, height: h },
            styles: { style: 'stroke_fill', color: withAlpha(outcome, 0.16),
              borderColor: withAlpha(outcome, 0.9), borderSize: 1,
              borderStyle: secondary ? 'dashed' : 'solid', borderDashedValue: [4, 4] },
            ignoreEvent: true },
          arrowFig(),
        ]
      }

      const profitColor = favColor              // light mint — profit fill + level lines
      const entryColor = d.entryColor ?? '#c9cdd6'
      const stopColor = advColor
      const labelBg = withAlpha(d.chipBg ?? '#0d0d1a', 0.82) // subtle dark behind the side labels

      const figures: OverlayFigure[] = []
      const rect = (yA: number, yB: number, color: string) => figures.push({
        type: 'rect',
        attrs: { x: x0, y: Math.min(yA, yB), width: w, height: Math.max(1, Math.abs(yB - yA)) },
        styles: { style: 'fill', color },
        ignoreEvent: true,
      })
      // A thin dotted line across the trade at a price level.
      const crossLine = (p: number | undefined, color: string, size = 1) => {
        const y = yOf(p); if (y == null) return
        figures.push({ type: 'line', attrs: { coordinates: [{ x: x0, y }, { x: x1, y }] },
          styles: { color, size, style: 'dashed', dashedValue: [2, 3] }, ignoreEvent: true })
      }
      // A small marker dot on a level, at the trade's left edge (the "bubble").
      const dot = (p: number | undefined, color: string) => {
        const y = yOf(p); if (y == null) return
        figures.push({ type: 'circle', attrs: { x: x0, y, r: 3 },
          styles: { style: 'fill', color }, ignoreEvent: true })
      }
      // Side labels are collected first, de-collided, then drawn — so a cluster of close levels
      // (e.g. TP1 near the entry) never stacks on itself.
      const labels: { y: number; text: string; color: string }[] = []
      const addLabel = (p: number | undefined, text: string, color: string) => {
        const y = yOf(p); if (y != null) labels.push({ y, text, color })
      }

      const entryY = entry.y
      const yMfe = yOf(mfePrice)!
      const entryP = d.entryPrice
      // Favourable fill (light mint): SOLID entry→banked (took profit), FAINT banked→mfe (ran, unbanked).
      if (bankedPrice != null && typeof entryP === 'number' && (bankedPrice - entryP) * sign > 1e-9) {
        const yBank = yOf(bankedPrice)!
        rect(entryY, yBank, withAlpha(profitColor, 0.22))
        if ((mfePrice - bankedPrice) * sign > 1e-9) rect(yBank, yMfe, withAlpha(profitColor, 0.07))
      } else if (typeof entryP === 'number' && (mfePrice - entryP) * sign > 1e-9) {
        // nothing banked (e.g. a loser that ran into profit, then stopped) → all faint green
        rect(entryY, yMfe, withAlpha(profitColor, 0.10))
      }
      // Adverse red — the mirror of the favourable green, on the loss side, so the drawdown the
      // trade sat through reads as clearly as the profit it ran. A LOSER actually gave it back:
      // a DARKER band entry→stop (up to the stop line), plus a faint tail if price ran past the
      // stop (gap/slippage) on to the true worst (`maePrice`). A WINNER only sat through the
      // drawdown and recovered it: one FAINT band entry→mae — the "runner" equivalent, showing
      // how deep it went against before working out.
      const isLoser = typeof d.pnl === 'number' && d.pnl < 0
      if (isLoser && typeof d.stopPrice === 'number' && (d.stopPrice - entryP!) * sign < -1e-9) {
        rect(entryY, yOf(d.stopPrice)!, withAlpha(advColor, 0.22))
        if (typeof d.maePrice === 'number' && (d.maePrice - d.stopPrice) * sign < -1e-9) {
          rect(yOf(d.stopPrice)!, yOf(d.maePrice)!, withAlpha(advColor, 0.07))
        }
      } else if (typeof d.maePrice === 'number' && typeof entryP === 'number' &&
                 (d.maePrice - entryP) * sign < -1e-9) {
        rect(entryY, yOf(d.maePrice)!, withAlpha(advColor, 0.10))
      }

      // Deepest-run guide (faint, unlabelled — it's just the top edge of the faint band).
      crossLine(mfePrice, withAlpha(profitColor, 0.4))
      // Stop: dotted line across + dot + "SL".
      crossLine(d.stopPrice, withAlpha(stopColor, 0.85)); dot(d.stopPrice, stopColor); addLabel(d.stopPrice, 'SL', stopColor)
      // Each real profit-take: a thin dotted mint line + a dot + its label (TP1/TP2/TP3/Exit). A
      // plain win with no per-rung detail draws one "Exit" at the banked price.
      const drawnLegs = legs.length ? legs
        : (bankedPrice != null ? [{ price: bankedPrice, label: 'Exit' }] : [])
      for (const lg of drawnLegs) { crossLine(lg.price, profitColor); dot(lg.price, profitColor); addLabel(lg.price, lg.label, profitColor) }
      // Entry: NO line across — just a short tick where the green begins, a dot, and the label.
      figures.push({ type: 'line', attrs: { coordinates: [{ x: x0, y: entryY }, { x: x0 + 16, y: entryY }] },
        styles: { color: entryColor, size: 1.5, style: 'solid', dashedValue: [] }, ignoreEvent: true })
      dot(entryP, entryColor); addLabel(entryP, 'Entry', entryColor)

      // Next UNHIT take-profit (near-miss view): the trade banked its earlier rungs but never tagged
      // the FOLLOWING target — draw that target as a FAINT dashed line + a faint label, so you can
      // see how far the runner still had to go. Only when it got CLOSE (NEXT_TP_SHOW_FRAC of the gap).
      const targets = (d.tpTargets ?? []).filter(t => typeof t === 'number')
      if (targets.length && typeof entryP === 'number' && typeof mfePrice === 'number') {
        const favOf = (p: number) => (p - entryP) * sign          // favourable distance from entry
        const mfeFav = favOf(mfePrice)
        const nextIdx = targets.findIndex(t => favOf(t) > mfeFav + 1e-9) // first the mfe didn't reach
        if (nextIdx >= 0) {
          const refFav = nextIdx > 0 ? favOf(targets[nextIdx - 1]) : 0  // last hit target, else entry
          const covered = (mfeFav - refFav) / (favOf(targets[nextIdx]) - refFav)
          if (covered >= NEXT_TP_SHOW_FRAC) {
            crossLine(targets[nextIdx], withAlpha(profitColor, 0.5))
            dot(targets[nextIdx], withAlpha(profitColor, 0.5))
            addLabel(targets[nextIdx], `TP${nextIdx + 1}`, withAlpha(profitColor, 0.7))
          }
        }
      }

      // De-collide the labels top→down (min 15px apart), then draw each as a compact rounded chip
      // just OUTSIDE the box to the left — flipping inside only if it would clip the pane edge.
      labels.sort((a, b) => a.y - b.y)
      const MIN_GAP = 15
      for (let i = 1; i < labels.length; i++) {
        if (labels[i].y - labels[i - 1].y < MIN_GAP) labels[i].y = labels[i - 1].y + MIN_GAP
      }
      const LBL_GAP = 9
      const chip = (x: number, y: number, text: string, color: string, align: 'left' | 'right' | 'center') =>
        figures.push({
          type: 'text',
          attrs: { x, y, text, align, baseline: 'middle' },
          styles: {
            style: 'stroke_fill', color, size: 10, weight: 'bold',
            backgroundColor: labelBg, borderColor: withAlpha(color, 0.4), borderSize: 1,
            borderStyle: 'solid', borderRadius: 3,
            paddingLeft: 5, paddingRight: 5, paddingTop: 2, paddingBottom: 2,
          },
          ignoreEvent: true,
        })
      for (const { y, text, color } of labels) {
        const clipsLeft = x0 - LBL_GAP - (text.length * 6.3 + 12) < 2
        chip(clipsLeft ? x0 + LBL_GAP : x0 - LBL_GAP, y, text, color, clipsLeft ? 'left' : 'right')
      }

      // Outcome chip — a small "Won"/"Lost" tag, same subtle style as the level labels. Now that a
      // winner ALSO shows a red drawdown band, the result isn't obvious from colour alone, so it's
      // stated once per trade. It sits horizontally CENTRED over the trade, just BEYOND the trade's
      // resolved extreme — a WIN past the furthest favourable point (`mfePrice`), a LOSS past the
      // furthest adverse point (`maePrice`, behind the stop) — so it always points the way the trade
      // resolved: above a long win / below a long loss, mirrored for a short.
      if (typeof d.pnl === 'number') {
        const won = d.pnl > 0
        const extY = won ? yMfe : (yOf(d.maePrice ?? d.stopPrice) ?? exit.y)
        const outPix = won ? -sign : sign      // beyond the extreme, away from entry (px: up = −)
        chip((x0 + x1) / 2, extY + outPix * 12, won ? 'Won' : 'Lost',
             won ? profitColor : stopColor, 'center')
      }

      return figures
    },
  })

  // ── Fibonacci retracement (USER-DRAWN) ────────────────────────────────────────
  // Two anchor points (swing A → swing B) define the 0↔1 price range; each configured level draws a
  // thin horizontal line spanning EXACTLY the box the user dragged (both anchor x's — width AND
  // height follow the drag) plus a right-aligned "<ratio> (<price>)" chip in the level's colour.
  // Unlike the other overlays this one is NOT lock:true — it's interactive: drawn, selected/moved by
  // its anchor handles, and its lines respond to hover/click so a right-click can delete it. Only the
  // labels ignore events (they sit on the lines). Levels/precision/chip bg come via `extendData`.
  registerOverlay({
    name: FIB,
    totalStep: 3, // 2 points + 1
    needDefaultPointFigure: true, // anchor handles for select/move
    needDefaultXAxisFigure: false,
    needDefaultYAxisFigure: false,
    createPointFigures: ({ coordinates, overlay, yAxis }) => {
      if (coordinates.length < 2 || !yAxis) return []
      const [a, b] = coordinates
      const p0 = overlay.points[0]?.value
      const p1 = overlay.points[1]?.value
      if (typeof p0 !== 'number' || typeof p1 !== 'number') return []
      const d = (overlay.extendData ?? {}) as FibExtend
      const levels = d.levels?.length ? d.levels : DEFAULT_FIB_LEVELS
      const precision = d.precision ?? 2
      const chipBg = withAlpha(d.chipBg ?? '#0d0d1a', 0.82)
      const xLeft = Math.min(a.x, b.x)
      const xRight = Math.max(a.x, b.x)
      const figures: OverlayFigure[] = []
      for (const lvl of levels) {
        const price = p0 + (p1 - p0) * lvl.ratio
        const y = yAxis.convertToPixel(price)
        figures.push({
          type: 'line',
          attrs: { coordinates: [{ x: xLeft, y }, { x: xRight, y }] },
          styles: { color: lvl.color, size: 0.5, style: 'solid' },
        })
        // Label = decimal ratio + price in parens, e.g. "0.886 (3987.45)" — same dark rounded chip as
        // the trade level labels (SL/TP1…), so it reads over candles instead of a bare colour string.
        figures.push({
          type: 'text',
          attrs: { x: xRight, y, text: `${lvl.ratio} (${price.toFixed(precision)})`, align: 'right', baseline: 'middle' },
          styles: {
            style: 'stroke_fill', color: lvl.color, size: 10, weight: 'bold',
            backgroundColor: chipBg, borderColor: withAlpha(lvl.color, 0.4), borderSize: 1,
            borderStyle: 'solid', borderRadius: 3,
            paddingLeft: 5, paddingRight: 5, paddingTop: 2, paddingBottom: 2,
          },
          ignoreEvent: true,
        })
      }
      return figures
    },
  })

  // ── Generic strategy-structure overlays (box / hline / vline) ──────────────────
  registerOverlay({
    name: BOX,
    totalStep: 2,
    lock: true,
    needDefaultPointFigure: false,
    needDefaultXAxisFigure: false,
    needDefaultYAxisFigure: false,
    createPointFigures: ({ coordinates, overlay }) => {
      if (coordinates.length < 2) return []
      const [a, b] = coordinates
      const x = Math.min(a.x, b.x)
      const y = Math.min(a.y, b.y)
      const width = Math.max(1, Math.abs(b.x - a.x))
      const height = Math.max(1, Math.abs(b.y - a.y))
      const d = (overlay.extendData ?? {}) as OverlayExtend
      const color = d.color ?? '#888888'
      const figures: OverlayFigure[] = [
        {
          type: 'rect',
          attrs: { x, y, width, height },
          styles: {
            style: 'stroke_fill',
            color: d.fillColor ?? withAlpha(color, 0.12),
            borderColor: withAlpha(color, 0.50),
            borderSize: d.lineWidth ?? 1,
            borderStyle: d.lineStyle === 'dashed' ? 'dashed' : 'solid',
            borderDashedValue: [4, 4],
          },
          ignoreEvent: true,
        },
      ]
      if (d.label) {
        figures.push({
          type: 'text',
          attrs: { x: x + 4, y: y + 3, text: d.label, baseline: 'top' },
          styles: { color, size: 10, weight: 'bold' },
          ignoreEvent: true,
        })
      }
      return figures
    },
  })

  registerOverlay({
    name: HLINE,
    totalStep: 2,
    lock: true,
    needDefaultPointFigure: false,
    needDefaultXAxisFigure: false,
    needDefaultYAxisFigure: false,
    createPointFigures: ({ coordinates, overlay }) => {
      if (coordinates.length < 2) return []
      const [a, b] = coordinates // both points share the price → same y
      const d = (overlay.extendData ?? {}) as OverlayExtend
      const color = d.color ?? '#888888'
      const figures: OverlayFigure[] = [
        {
          type: 'line',
          attrs: { coordinates: [{ x: a.x, y: a.y }, { x: b.x, y: a.y }] },
          styles: {
            color,
            size: d.lineWidth ?? 1,
            style: d.lineStyle === 'dashed' ? 'dashed' : 'solid',
            dashedValue: [4, 4],
          },
          ignoreEvent: true,
        },
      ]
      if (d.label) {
        figures.push({
          type: 'text',
          attrs: { x: Math.max(a.x, b.x) - 4, y: a.y - 3, text: d.label, align: 'right', baseline: 'bottom' },
          styles: { color, size: 10, weight: 'bold' },
          ignoreEvent: true,
        })
      }
      return figures
    },
  })

  // VLINE and DAY_BREAK render identically (a full-height vertical line) but under distinct
  // names so they can be toggled / removed independently.
  const vline = {
    totalStep: 1,
    lock: true,
    needDefaultPointFigure: false,
    needDefaultXAxisFigure: false,
    needDefaultYAxisFigure: false,
    createPointFigures: ({ coordinates, bounding, overlay }: OverlayCreateFiguresCallbackParams): OverlayFigure[] => {
      if (coordinates.length < 1) return []
      const a = coordinates[0]
      const d = (overlay.extendData ?? {}) as OverlayExtend
      const color = d.color ?? '#888888'
      return [
        {
          type: 'line',
          attrs: { coordinates: [{ x: a.x, y: 0 }, { x: a.x, y: bounding.height }] },
          styles: {
            color,
            size: d.lineWidth ?? 1,
            style: d.lineStyle === 'dashed' ? 'dashed' : 'solid',
            dashedValue: [4, 4],
          },
          ignoreEvent: true,
        },
      ]
    },
  }
  registerOverlay({ name: VLINE, ...vline })
  registerOverlay({ name: DAY_BREAK, ...vline })

  // ── Point-anchored text labels (market-structure tags), de-collided ───────────
  // ONE overlay holds EVERY visible structure label (its `points` are the anchors, `extendData.items`
  // the parallel text/colour/placement). klinecharts maps every point to a coordinate, so the callback
  // sees them all at once and can push overlapping chips apart in PIXEL space (like the trade overlay's
  // level labels) — the only way to de-collide across separate labels, since a per-label overlay can't
  // see its neighbours. `placement` sets the initial nudge + which way a chip slides to get clear (a
  // high tag slides up, a low tag down) so it never covers its own candle.
  registerOverlay({
    name: LABEL,
    totalStep: 1,
    lock: true,
    needDefaultPointFigure: false,
    needDefaultXAxisFigure: false,
    needDefaultYAxisFigure: false,
    createPointFigures: ({ coordinates, overlay, bounding }: OverlayCreateFiguresCallbackParams): OverlayFigure[] => {
      const items = ((overlay.extendData ?? {}) as { items?: LabelItem[] }).items ?? []
      if (!items.length) return []
      const CHAR_W = 6.2, PAD = 10, H = 15, GAP = 2 // chip metrics (must track the text styles below)
      type Box = { x: number; y: number; half: number; text: string; color: string; up: boolean }
      const boxes: Box[] = []
      for (let i = 0; i < items.length && i < coordinates.length; i++) {
        const c = coordinates[i]
        const it = items[i]
        if (!c || !it?.text) continue
        const w = it.text.length * CHAR_W + PAD
        if (c.x < -w || c.x > bounding.width + w) continue // off-screen — skip (don't pile at the edge)
        const up = it.placement !== 'below'
        // Initial nudge OFF the anchor (wick tip / break line), ~ chip half-height + margin so the
        // chip clears the candle instead of resting on it — the pixel echo of Pine's newline offset.
        const y0 = c.y + (it.placement === 'above' ? -13 : it.placement === 'below' ? 13 : 0)
        boxes.push({ x: c.x, y: y0, half: w / 2, text: it.text, color: it.color ?? '#888888', up })
      }
      // Greedy left→right packing: each chip slides away from its anchor until it clears every
      // already-placed chip it overlaps in x. Only visible chips are processed, so this stays cheap.
      boxes.sort((a, b) => a.x - b.x || a.y - b.y)
      const placed: Box[] = []
      for (const b of boxes) {
        for (let guard = 0; guard < 80; guard++) {
          let hit = false
          for (const p of placed) {
            if (Math.abs(p.x - b.x) < p.half + b.half && Math.abs(p.y - b.y) < H) {
              const push = H - Math.abs(p.y - b.y) + GAP
              b.y += b.up ? -push : push
              hit = true
              break
            }
          }
          if (!hit) break
        }
        placed.push(b)
      }
      // Flat text — no chip/box/border/background (Aaron's call; also matches the Pine, which uses
      // color(na) for the label background). klinecharts' DEFAULT overlay-text style has a BLUE
      // backgroundColor + borderColor (#1677FF), and omitting those fields falls back to it — so they
      // must be set transparent (and borderSize 0) explicitly to leave just the coloured text.
      return placed.map((b): OverlayFigure => ({
        type: 'text',
        attrs: { x: b.x, y: b.y, text: b.text, align: 'center', baseline: 'middle' },
        styles: {
          color: b.color, size: 10, weight: 'bold',
          backgroundColor: 'transparent', borderColor: 'transparent', borderSize: 0,
          paddingLeft: 0, paddingRight: 0, paddingTop: 0, paddingBottom: 0,
        },
        ignoreEvent: true,
      }))
    },
  })

  // Drill-down data edge — a red dashed FULL-HEIGHT line at the broker's oldest available bar for the
  // current sub-base TF, with a dark label chip to its RIGHT (where data still exists). Marks a TRUE
  // feed limit so a hard "no more data" boundary reads as a wall, not a blank chart.
  registerOverlay({
    name: DATA_EDGE,
    totalStep: 1,
    lock: true,
    needDefaultPointFigure: false,
    needDefaultXAxisFigure: false,
    needDefaultYAxisFigure: false,
    createPointFigures: ({ coordinates, bounding, overlay }: OverlayCreateFiguresCallbackParams): OverlayFigure[] => {
      if (coordinates.length < 1) return []
      const a = coordinates[0]
      const d = (overlay.extendData ?? {}) as OverlayExtend
      const color = d.color ?? '#ef5350'
      const figures: OverlayFigure[] = [
        {
          type: 'line',
          attrs: { coordinates: [{ x: a.x, y: 0 }, { x: a.x, y: bounding.height }] },
          styles: { color, size: 1, style: 'dashed', dashedValue: [5, 4] },
          ignoreEvent: true,
        },
      ]
      if (d.label) {
        figures.push({
          type: 'text',
          attrs: { x: a.x + 6, y: 8, text: d.label, align: 'left', baseline: 'top' },
          styles: {
            style: 'stroke_fill', color, size: 10, weight: 'bold',
            backgroundColor: withAlpha('#0d0d1a', 0.82), borderColor: withAlpha(color, 0.5), borderSize: 1,
            borderStyle: 'solid', borderRadius: 3,
            paddingLeft: 5, paddingRight: 5, paddingTop: 2, paddingBottom: 2,
          },
          ignoreEvent: true,
        })
      }
      return figures
    },
  })
}
