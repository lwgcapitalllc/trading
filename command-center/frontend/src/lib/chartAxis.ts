// Shared axis maths for the two equity charts (BacktestDetail's run curve and the tuning
// workbench's overlay). They MUST read identically — same starting-balance anchor, same ticks,
// same regime bands — so the numbers live here once instead of being re-derived per page.

export interface TimeBand {
  x1: number
  x2: number
  regime: string
}

/**
 * Equity-chart x-axis. 'date' is the default and canonical view — regime bands only have a true
 * width on it, drawdown DURATION is a time metric, and two runs can only be compared on a shared
 * calendar. 'trade' spaces every trade evenly, for per-trade forensics (streaks, excursions).
 * Both equity charts read the SAME stored preference, so flipping one flips the other and the run
 * page and the tuning workbench never disagree about what you're looking at.
 */
export type XMode = 'date' | 'trade'
const XMODE_KEY = 'equity_x_mode'

export function getXMode(): XMode {
  try {
    return localStorage.getItem(XMODE_KEY) === 'trade' ? 'trade' : 'date'
  } catch {
    return 'date'
  }
}
export function setXModePref(v: XMode) {
  try {
    localStorage.setItem(XMODE_KEY, v)
  } catch {
    /* quota */
  }
}

/** Evenly spaced integer ticks across [0, n] — the trade-number axis. */
export function tradeTicks(n: number, max = 10): number[] {
  if (n <= 0) return [0]
  const step = Math.max(1, Math.ceil(n / max))
  const out: number[] = []
  for (let t = step; t <= n; t += step) out.push(t)
  return out
}

/**
 * Regime bands on a TRADE-NUMBER axis: each trade takes its date's regime, and consecutive trades
 * sharing one carry a band. Approximate by nature (the market between two trades is compressed to
 * nothing), which is exactly why 'date' is the default.
 */
export function regimeBandsByIndex(
  points: Array<{ index: number; date?: string | null }>,
  dateToRegime: Map<string, string>
): TimeBand[] {
  const bands: TimeBand[] = []
  for (const p of points) {
    const regime = (p.date ? dateToRegime.get(p.date.slice(0, 10)) : undefined) ?? 'UNKNOWN'
    const last = bands[bands.length - 1]
    if (last && last.regime === regime) last.x2 = p.index
    else bands.push({ x1: p.index, x2: p.index, regime })
  }
  for (let i = 0; i < bands.length - 1; i++) bands[i].x2 = bands[i + 1].x1
  return bands.filter((b) => b.regime !== 'UNKNOWN')
}

/** 'YYYY-MM-DD' (or an ISO timestamp) → local-midnight epoch ms. */
export function dateMs(d?: string | null): number | null {
  if (!d) return null
  const t = new Date(`${d.slice(0, 10)}T00:00:00`).getTime()
  return Number.isFinite(t) ? t : null
}

/** A "nice" round tick step (1/2/5 × 10ⁿ) near the requested size. */
export function niceStep(raw: number): number {
  if (raw <= 0) return 1
  const mag = Math.pow(10, Math.floor(Math.log10(raw)))
  const n = raw / mag
  return (n <= 1 ? 1 : n <= 2 ? 2 : n <= 5 ? 5 : 10) * mag
}

/**
 * Explicit month-start ticks across [from, to], thinned to ~`max`. Recharts' automatic ticks on a
 * time axis land on arbitrary days, so two neighbouring ticks inside one month both render "Sep 25".
 */
export function monthTicks(from: number, to: number, max = 10): number[] {
  if (!Number.isFinite(from) || !Number.isFinite(to) || to <= from) return []
  const out: number[] = []
  const d = new Date(from)
  d.setDate(1)
  d.setHours(0, 0, 0, 0)
  if (d.getTime() < from) d.setMonth(d.getMonth() + 1)
  while (d.getTime() <= to) {
    out.push(d.getTime())
    d.setMonth(d.getMonth() + 1)
  }
  const every = Math.ceil(out.length / max) || 1
  return out.filter((_, i) => i % every === 0)
}

export const monthLabel = (t: number) =>
  new Date(t).toLocaleDateString('en-US', { month: 'short', year: '2-digit' })

/**
 * A dollar AXIS label — a level, not a gain, so no "+" prefix, and the sign leads the "$" the way
 * money is written (`-$4.2M`, never `$-4.2M`).
 *
 * ⚠ It steps k → M → B. It used to stop at "k", which is not a cosmetic limit: a compounding run
 * that reached $150,010,000 rendered as "$150010k", which reads a thousand times smaller than it is
 * and looks like a corrupt number rather than a large one. An axis label is the only place most
 * readers ever see the SCALE of a run, so a suffix that runs out is a wrong number, not an ugly one.
 */
export function balTick(v: number): string {
  const a = Math.abs(v)
  const sign = v < 0 ? '-' : ''
  if (a < 1000) return `${sign}$${Math.round(a)}`
  const [div, suffix] = a >= 1e9 ? [1e9, 'B'] : a >= 1e6 ? [1e6, 'M'] : [1e3, 'k']
  const n = a / div
  return `${sign}$${Number.isInteger(n) ? n : n.toFixed(1)}${suffix}`
}

/**
 * Y ticks on ROUND numbers, plus the starting balance as one extra tick so break-even is always
 * labelled.
 *
 * 🔴 It used to STEP FROM the starting balance, which carried that balance into every other label:
 * on a $10,000 account whose curve reached nine figures the step was $50M and the labels read
 * $10k / $50,010,000 / $100,010,000 / $150,010,000. Every one of those was arithmetically correct
 * and every one was unreadable — the "10k" tail is the opening balance riding along, and a reader
 * takes it for a formatting fault and stops trusting the axis. **An anchor that is meaningful at
 * 2x is pure contamination at 15,000x**, because the thing being anchored to has shrunk to noise
 * against the step. So the round ticks are computed independently and the anchor is INSERTED, which
 * keeps the property that motivated it without paying for it on every label.
 *
 * A round tick within 0.35 of a step of the starting balance is dropped instead, so the two labels
 * can never collide; the anchor wins because break-even is the more useful of the two.
 */
export function balanceTicks(startBal: number, yMin: number, yMax: number): number[] {
  if (!Number.isFinite(yMin) || !Number.isFinite(yMax) || yMax <= yMin) return [startBal]
  const step = niceStep((yMax - yMin) / 5)
  const ticks: number[] = []
  // Indexed off an integer multiple rather than accumulated, or the running total drifts and a
  // "round" tick prints as 150000.00000000003.
  for (let k = Math.ceil(yMin / step); k * step <= yMax; k++) {
    const t = k * step
    if (Math.abs(t - startBal) < step * 0.35) continue
    ticks.push(t)
  }
  if (startBal >= yMin && startBal <= yMax) ticks.push(startBal)
  return ticks.sort((a, b) => a - b)
}

/**
 * Regime bands on a TIME axis, from a run's full-calendar `regime_timeline` — every trading day in
 * the window, not just the days that traded. UNKNOWN days are dropped so the chart shows exactly
 * the regimes in the legend; a run that traded but has no timeline (completed before the backend
 * emitted one) gets an empty list and the caller falls back.
 */
export function regimeBandsFromTimeline(
  timeline: Array<{ date: string; regime: string }>
): TimeBand[] {
  const sorted = [...timeline].sort((a, b) => a.date.localeCompare(b.date))
  const bands: TimeBand[] = []
  for (const d of sorted) {
    const t = dateMs(d.date)
    if (t == null) continue
    const last = bands[bands.length - 1]
    if (last && last.regime === d.regime) last.x2 = t
    else bands.push({ x1: t, x2: t, regime: d.regime })
  }
  // Tile so there are no transparent seams between regimes.
  for (let i = 0; i < bands.length - 1; i++) bands[i].x2 = bands[i + 1].x1
  return bands.filter((b) => b.regime !== 'UNKNOWN')
}
