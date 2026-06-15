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

/** Daily session-break marker (Step 6) — a vline drawn under a separate name so the generic
 *  vline group and the day breaks can be removed/toggled independently. */
export const DAY_BREAK = 'lwgDayBreak'

/** Style + label passed to generic overlays via `extendData`. Mirrors spec OverlayStyle. */
interface OverlayExtend {
  color?: string
  fillColor?: string
  lineStyle?: 'solid' | 'dashed'
  lineWidth?: number
  label?: string
}

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
            color: withAlpha(color, 0.08),
            borderColor: withAlpha(color, 0.5),
            borderSize: 1,
            borderStyle: 'solid',
          },
          ignoreEvent: true,
        },
      ]
      return figures
    },
  })

  registerOverlay({
    name: TRADE,
    totalStep: 2,
    lock: true,
    needDefaultPointFigure: false,
    needDefaultXAxisFigure: false,
    needDefaultYAxisFigure: false,
    createPointFigures: ({ coordinates, overlay }) => {
      if (coordinates.length < 2) return []
      const [entry, exit] = coordinates
      const data = (overlay.extendData ?? {}) as { dir?: 'long' | 'short'; color?: string }
      const color = data.color ?? '#4da6ff'
      const isLong = data.dir !== 'short'

      // Long: up-arrow below the entry, pointing up. Short: down-arrow above, pointing down.
      const HALF = 6
      const HEIGHT = 9
      const GAP = 5
      const apexY = isLong ? entry.y + GAP : entry.y - GAP
      const baseY = isLong ? entry.y + GAP + HEIGHT : entry.y - GAP - HEIGHT
      const arrow = [
        { x: entry.x, y: apexY },
        { x: entry.x - HALF, y: baseY },
        { x: entry.x + HALF, y: baseY },
      ]

      const figures: OverlayFigure[] = [
        // Dashed line from entry to exit — the trade's length.
        {
          type: 'line',
          attrs: { coordinates: [entry, exit] },
          styles: { color, size: 1, style: 'dashed', dashedValue: [4, 4] },
          ignoreEvent: true,
        },
        // Entry arrow (direction by orientation, not color).
        {
          type: 'polygon',
          attrs: { coordinates: arrow },
          styles: { style: 'fill', color },
          ignoreEvent: true,
        },
        // Exit dot.
        {
          type: 'circle',
          attrs: { x: exit.x, y: exit.y, r: 3 },
          styles: { style: 'fill', color },
          ignoreEvent: true,
        },
      ]
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
            color: d.fillColor ?? withAlpha(color, 0.06),
            borderColor: color,
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
}
