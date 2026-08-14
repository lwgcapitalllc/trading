/**
 * Shipped-series indicators. The strategy's indicator values arrive in the spec (computed by
 * the run, NOT recomputed in the browser), so the chart shows exactly what the strategy saw.
 *
 * klinecharts indicators are normally calc'd from candle data; here `calc` instead looks the
 * shipped value up by timestamp. One template is registered per indicator NAME (so multiple
 * indicators on the same pane don't collide — klinecharts keys instances by name per pane).
 */
import { registerIndicator } from 'klinecharts'

export interface ShippedPoint {
  time: number
  value: number
}

interface SeriesResult {
  value?: number
}

/**
 * Map a shipped (base-TF) series onto the currently displayed candles. For each displayed bar
 * we take the last shipped point inside that bar's [start, nextStart) window — i.e. the value
 * as of the bar's close. This makes higher-TF display correct without recomputing anything.
 * `series` and `dataList` must both be sorted ascending by time.
 */
export function mapSeriesToCandles(
  dataList: Array<{ timestamp: number }>,
  series: ShippedPoint[]
): SeriesResult[] {
  if (series.length === 0) return dataList.map(() => ({}))
  const out: SeriesResult[] = []
  let si = 0
  let lastVal: number | undefined // carry forward so D1 values fill every sub-day bar
  for (let i = 0; i < dataList.length; i++) {
    const nextT = i + 1 < dataList.length ? dataList[i + 1].timestamp : Infinity
    while (si < series.length && series[si].time < nextT) {
      lastVal = series[si].value
      si++
    }
    out.push(lastVal === undefined ? {} : { value: lastVal })
  }
  return out
}

const registered = new Set<string>()

/** Register a line indicator under `name` (idempotent). Color + series come via extendData. */
export function ensureSeriesIndicator(name: string): void {
  if (registered.has(name)) return
  registered.add(name)
  registerIndicator<SeriesResult>({
    name,
    shortName: name,
    figures: [
      {
        key: 'value',
        title: `${name}: `,
        type: 'line',
        styles: (_data, indicator) => ({
          color: (indicator.extendData?.color as string) ?? '#888888',
        }),
      },
    ],
    calc: (dataList, indicator) =>
      mapSeriesToCandles(dataList, (indicator.extendData?.series as ShippedPoint[]) ?? []),
  })
}
