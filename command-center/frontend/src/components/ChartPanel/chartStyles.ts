/**
 * klinecharts style object, derived entirely from the app theme — no hardcoded hex.
 * This is the chart-component equivalent of `@/themes/chart`: klinecharts paints to a
 * canvas, so (like Recharts) it can't use Tailwind classes and must read raw theme values.
 *
 * Grid is OFF by design (the surrounding card supplies the surface). Swapping the app
 * theme automatically restyles the chart — nothing here is theme-specific.
 */
import { TooltipShowRule, type DeepPartial, type Styles } from 'klinecharts'
import t from '@/themes/electric-indigo'

export const chartStyles: DeepPartial<Styles> = {
  grid: { show: false },
  candle: {
    bar: {
      upColor: t.pos,
      downColor: t.neg,
      noChangeColor: t.neutral,
      upBorderColor: t.pos,
      downBorderColor: t.neg,
      noChangeBorderColor: t.neutral,
      upWickColor: t.pos,
      downWickColor: t.neg,
      noChangeWickColor: t.neutral,
    },
    priceMark: {
      last: {
        // Last-price line + label both read upColor/downColor (the line style omits `color`).
        upColor: t.accent,
        downColor: t.accent,
        text: { color: t.textInverse },
      },
      // Highest/lowest-visible-price marks OFF: they land on the exact visual extreme, which is
      // where the trade overlay puts its "Won"/"Lost" chip — so they collided. Low-value clutter
      // (they just label the window's high/low); the last-price line (above) is the useful one.
      high: { show: false, color: t.textTertiary },
      low: { show: false, color: t.textTertiary },
    },
    tooltip: {
      // Pinned top-left (line 1) — the OHLC "statistics" Aaron wants always visible. Our on-chart
      // "Sessions" legend is stacked BELOW it (line 2, top:32 in index.tsx), TradingView-style, so
      // the two no longer collide.
      showRule: TooltipShowRule.Always,
      text: { color: t.textSecondary },
    },
  },
  indicator: {
    // Indicator name/value legend stays hover-only so the persistent top-left stack is just the one
    // OHLC line — the Sessions chip on line 2 never fights a main-pane indicator legend.
    tooltip: { showRule: TooltipShowRule.FollowCross },
  },
  xAxis: {
    axisLine: { color: t.borderDefault },
    tickLine: { color: t.borderDefault },
    tickText: { color: t.textTertiary },
  },
  yAxis: {
    axisLine: { color: t.borderDefault },
    tickLine: { color: t.borderDefault },
    tickText: { color: t.textTertiary },
  },
  crosshair: {
    horizontal: {
      line: { color: t.textTertiary },
      text: { color: t.textPrimary, backgroundColor: t.bgSurface2, borderColor: t.borderStrong },
    },
    vertical: {
      line: { color: t.textTertiary },
      text: { color: t.textPrimary, backgroundColor: t.bgSurface2, borderColor: t.borderStrong },
    },
  },
}
