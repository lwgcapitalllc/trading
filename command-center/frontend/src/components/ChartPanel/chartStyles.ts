/**
 * klinecharts style object, derived entirely from the app theme — no hardcoded hex.
 * This is the chart-component equivalent of `@/themes/chart`: klinecharts paints to a
 * canvas, so (like Recharts) it can't use Tailwind classes and must read raw theme values.
 *
 * Grid is OFF by design (the surrounding card supplies the surface). Swapping the app
 * theme automatically restyles the chart — nothing here is theme-specific.
 */
import {
  TooltipShowRule,
  utils,
  type CandleTooltipCustomCallback,
  type DeepPartial,
  type KLineData,
  type Styles,
} from 'klinecharts'
import t from '@/themes/dark-2026'

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
      //
      // ⚠ `Always` is only safe BECAUSE of `makeCandleTooltip` below, which index.tsx installs over
      // this. Read the note there before touching either — on its own, `Always` reads a bar that is
      // not on screen.
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

/**
 * The pinned top-left readout, built ourselves rather than left to the library's default.
 *
 * 🔴 **IT EXISTS BECAUSE THE DEFAULT READOUT DESCRIBES A BAR THAT IS NOT ON SCREEN.** With the
 * readout pinned on (`showRule: Always`) and the pointer off the chart, klinecharts falls back to
 * `dataList[dataList.length - 1]` — the NEWEST bar in the loaded run, wherever you have scrolled
 * to. On 2026-08-23 that printed `2026-08-21 15:45 … 4,603.31` across the top of a chart showing
 * August 2025 around 3,330, and it was read as the date of the trade on screen. **Nothing was
 * wrong with the data; the chart was showing two different moments at once with no sign that it
 * was doing it** — the same failure shape as a probe whose negative answer a healthy system also
 * produces. TradingView does not do this: its legend follows the visible window.
 *
 * Two rules, both TradingView's:
 *
 *  1. **The bar is the RIGHT-MOST VISIBLE one**, never the end of the dataset — `resolveBar` in
 *    index.tsx decides, and while the pointer is on a bar the crosshair's bar wins, because that
 *    is the bar the reader is asking about.
 *  2. **No timestamp.** The default readout leads with `{time}` and that single field is what
 *    misled a reader for a whole conversation. The date now lives in exactly one place — the
 *    crosshair's own tag on the time axis — so a date you can see is always the bar you are
 *    pointing at.
 *
 * ⚠ **Both paths format through ONE branch**, so the hovered and the pinned readout cannot drift
 * into disagreeing about how a price is written. That is why the `{open}`-style templates are not
 * used for the hover path even though they would work there: two formatters is two answers.
 */
export function makeCandleTooltip(
  resolveBar: (current: KLineData) => KLineData,
  getPrecision: () => { price: number; volume: number }
): CandleTooltipCustomCallback {
  return (data) => {
    if (!data.current) return []
    const bar = resolveBar(data.current) ?? data.current
    const p = getPrecision()
    const px = (v: number) => utils.formatThousands(utils.formatPrecision(v, p.price), ',')
    const vol =
      bar.volume == null
        ? '\u2013'
        : utils.formatThousands(
            utils.formatBigNumber(utils.formatPrecision(bar.volume, p.volume)),
            ','
          )
    return [
      { title: 'open', value: px(bar.open) },
      { title: 'high', value: px(bar.high) },
      { title: 'low', value: px(bar.low) },
      { title: 'close', value: px(bar.close) },
      { title: 'volume', value: vol },
    ]
  }
}
