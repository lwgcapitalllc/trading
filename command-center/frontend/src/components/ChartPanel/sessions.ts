/**
 * Session placement math. A session is declared in its own IANA timezone (`tz`) with a
 * local start/end; candle timestamps are broker wall-clock expressed as epoch ms
 * (true UTC + the spec's broker GMT offset). To place a session we convert its local time
 * → true UTC (DST-aware, via Intl) → broker axis. This keeps sessions correct year-round
 * across daylight-saving changes — the conversion reads the actual offset on each date.
 */
import type { ChartCandle, ChartSession } from './types'

const DAY_MS = 24 * 60 * 60 * 1000

/** Minutes `timeZone` is ahead of UTC at the given instant — DST-aware via Intl. */
export function tzOffsetMinutes(timeZone: string, atUtcMs: number): number {
  const dtf = new Intl.DateTimeFormat('en-US', {
    timeZone,
    hourCycle: 'h23',
    year: 'numeric',
    month: '2-digit',
    day: '2-digit',
    hour: '2-digit',
    minute: '2-digit',
    second: '2-digit',
  })
  const parts = dtf.formatToParts(new Date(atUtcMs))
  const get = (t: string) => Number(parts.find((p) => p.type === t)?.value)
  const asUtc = Date.UTC(
    get('year'),
    get('month') - 1,
    get('day'),
    get('hour'),
    get('minute'),
    get('second')
  )
  return Math.round((asUtc - atUtcMs) / 60_000)
}

function hhmm(s: string): { h: number; m: number } {
  const [h, m] = s.split(':').map(Number)
  return { h: h || 0, m: m || 0 }
}

/** A session box on the broker-time axis, hugging the high/low of the candles inside it. */
export interface SessionWindow {
  t0: number
  t1: number
  top: number
  bottom: number
}

/**
 * Broker-axis windows for one session across the candle range. One per day the session
 * overlaps; each hugs the high/low of the candles actually inside it. Candles must be
 * sorted ascending by time.
 */
export function sessionWindows(
  candles: ChartCandle[],
  session: ChartSession,
  brokerGmtOffsetHours: number
): SessionWindow[] {
  if (candles.length === 0) return []
  const tMin = candles[0].time
  const tMax = candles[candles.length - 1].time
  const brokerMs = brokerGmtOffsetHours * 3600_000
  const { h: sh, m: sm } = hhmm(session.start)
  const { h: eh, m: em } = hhmm(session.end)

  const windows: SessionWindow[] = []
  const firstDay = Math.floor(tMin / DAY_MS) - 1
  const lastDay = Math.floor(tMax / DAY_MS) + 1
  for (let day = firstDay; day <= lastDay; day++) {
    const base = new Date(day * DAY_MS)
    const y = base.getUTCFullYear()
    const mo = base.getUTCMonth()
    const d = base.getUTCDate()
    const startWallUtc = Date.UTC(y, mo, d, sh, sm)
    const endWallUtc0 = Date.UTC(y, mo, d, eh, em)
    // Overnight sessions (end <= start) roll into the next day.
    const endWallUtc = endWallUtc0 > startWallUtc ? endWallUtc0 : endWallUtc0 + DAY_MS
    const t0 = startWallUtc - tzOffsetMinutes(session.tz, startWallUtc) * 60_000 + brokerMs
    const t1 = endWallUtc - tzOffsetMinutes(session.tz, endWallUtc) * 60_000 + brokerMs
    if (t1 < tMin || t0 > tMax) continue

    let top = -Infinity
    let bottom = Infinity
    for (const c of candles) {
      if (c.time < t0 || c.time > t1) continue
      if (c.high > top) top = c.high
      if (c.low < bottom) bottom = c.low
    }
    if (top === -Infinity) continue
    windows.push({ t0, t1, top, bottom })
  }
  return windows
}
