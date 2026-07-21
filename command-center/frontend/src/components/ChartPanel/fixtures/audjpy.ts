/**
 * Hand-written AUDJPY ChartSpec fixture — the scaffold's stand-in until the lab emits
 * real specs (Step 7). Candles are generated deterministically (seeded, no Math.random)
 * so the chart renders identically every load.
 *
 * All fields are populated: candles (1), sessions (3), trades (4), overlays (5), indicators (6).
 * The overlays mimic a breakout structure (range box + buy/sell levels + a breakout marker) and
 * the indicators are a main-pane EMA + a sub-pane ATR — all purely DATA; the chart has no idea
 * what strategy made them.
 */
import type { ChartCandle, ChartIndicator, ChartOverlay, ChartSpec } from '../types'

const M5_MS = 5 * 60 * 1000

/** Deterministic AUDJPY-like M5 series around ~96.50, seeded LCG (stable across loads). */
function makeCandles(start: number, count: number, base: number): ChartCandle[] {
  let seed = 1337
  const rnd = () => {
    seed = (seed * 1664525 + 1013904223) >>> 0
    return seed / 0xffffffff
  }
  const candles: ChartCandle[] = []
  let price = base
  for (let i = 0; i < count; i++) {
    const drift = Math.sin(i / 18) * 0.045 // slow organic wave
    const noise = (rnd() - 0.5) * 0.06
    const open = price
    const close = +(open + drift + noise).toFixed(3)
    const high = +(Math.max(open, close) + rnd() * 0.04).toFixed(3)
    const low = +(Math.min(open, close) - rnd() * 0.04).toFixed(3)
    candles.push({
      time: start + i * M5_MS,
      open: +open.toFixed(3),
      high,
      low,
      close,
      volume: Math.round(200 + rnd() * 800),
    })
    price = close
  }
  return candles
}

// Anchor: 2024-05-13 00:00:00 UTC (Mon). 576 M5 bars = two 24h days, so the daily session
// break (Step 6) and a second day of sessions are visible.
const START = Date.UTC(2024, 4, 13, 0, 0, 0)
const CANDLES = makeCandles(START, 576, 96.5)

// Indicator series are SHIPPED from the run (computed here from the candles), not recomputed
// in the browser — the panel just draws the values.
function emaSeries(candles: ChartCandle[], period: number) {
  const k = 2 / (period + 1)
  let prev = candles[0].close
  return candles.map((c, i) => {
    prev = i === 0 ? c.close : c.close * k + prev * (1 - k)
    return { time: c.time, value: +prev.toFixed(3) }
  })
}

function atrSeries(candles: ChartCandle[], period: number) {
  let prevClose = candles[0].close
  let atr: number | null = null
  return candles.map((c, i) => {
    const tr = i === 0 ? c.high - c.low : Math.max(c.high - c.low, Math.abs(c.high - prevClose), Math.abs(c.low - prevClose))
    atr = atr === null ? tr : (atr * (period - 1) + tr) / period
    prevClose = c.close
    return { time: c.time, value: +atr.toFixed(4) }
  })
}

const INDICATORS: ChartIndicator[] = [
  { name: 'EMA(20)', params: { period: 20 }, pane: 'main', series: emaSeries(CANDLES, 20) },
  { name: 'ATR(14)', params: { period: 14 }, pane: 'sub', series: atrSeries(CANDLES, 14) },
]

// Trades anchored to real candles so entry/exit prices sit on the price (indices are M5 bars).
// Profit-depth fields (mfe/mae/legs/stop) are synthesised from the candles in the hold so the
// fixture exercises the rich trade view: a winner banks in two rungs and runs a touch further; a
// loser banks nothing but still shows how far it ran into profit before the stop.
function tradeAt(i0: number, i1: number, dir: 'long' | 'short', id: string, exitReason: string) {
  const slice = CANDLES.slice(i0, i1 + 1)
  const entryPrice = CANDLES[i0].close
  const exitPrice = CANDLES[i1].close
  const isLong = dir === 'long'
  const won = exitReason !== 'stop'
  const r3 = (v: number) => +v.toFixed(3)
  const mfePrice = r3(isLong ? Math.max(...slice.map(c => c.high)) : Math.min(...slice.map(c => c.low)))
  const maePrice = r3(isLong ? Math.min(...slice.map(c => c.low)) : Math.max(...slice.map(c => c.high)))
  const stopPrice = r3(entryPrice - (isLong ? 1 : -1) * Math.max(Math.abs(exitPrice - entryPrice), 0.05))
  // Winner banks two rungs partway to the favourable extreme; loser banks nothing.
  const profitLegs = won
    ? [
        { price: r3(entryPrice + (mfePrice - entryPrice) * 0.45), label: 'TP1' },
        { price: r3(entryPrice + (mfePrice - entryPrice) * 0.8), label: 'TP2' },
      ]
    : []
  // TP target ladder (nearest→furthest): TP1 at 45% of the fav run, TP2 just PAST the extreme, so
  // the chart's "next unhit TP" near-miss line has something to draw on a winner.
  const tpTargets = [
    r3(entryPrice + (mfePrice - entryPrice) * 0.45),
    r3(entryPrice + (mfePrice - entryPrice) * 1.15),
  ]
  return {
    id, dir,
    entryTime: CANDLES[i0].time,
    entryPrice,
    exitTime: CANDLES[i1].time,
    exitPrice,
    pnl: won ? 1 : -1,   // sign drives the win/loss colour in the fixture
    exitReason,
    mfePrice, maePrice, stopPrice, profitLegs, tpTargets,
  }
}

// Range over the formation window [rangeStart..rangeEnd], levels extend to the end of data.
const RANGE_START = 36 // 03:00
const RANGE_END = 84 // 07:00
const BREAKOUT = 96 // 08:00
const LAST = CANDLES.length - 1
const rangeSlice = CANDLES.slice(RANGE_START, RANGE_END + 1)
const rangeTop = Math.max(...rangeSlice.map(c => c.high))
const rangeBottom = Math.min(...rangeSlice.map(c => c.low))

const OVERLAYS: ChartOverlay[] = [
  {
    type: 'box',
    group: 'Range',
    t0: CANDLES[RANGE_START].time,
    t1: CANDLES[RANGE_END].time,
    top: rangeTop,
    bottom: rangeBottom,
    style: { color: '#e6bd6a' }, // gold
  },
  {
    type: 'hline',
    group: 'Levels',
    t0: CANDLES[RANGE_END].time,
    t1: CANDLES[LAST].time,
    price: rangeTop,
    label: 'Buy',
    style: { color: '#33ff99', lineStyle: 'dashed' }, // green
  },
  {
    type: 'hline',
    group: 'Levels',
    t0: CANDLES[RANGE_END].time,
    t1: CANDLES[LAST].time,
    price: rangeBottom,
    label: 'Sell',
    style: { color: '#ff6680', lineStyle: 'dashed' }, // red
  },
  {
    type: 'vline',
    group: 'Breakout',
    t: CANDLES[BREAKOUT].time,
    style: { color: '#00e5ff', lineStyle: 'dashed' }, // accent
  },
]

export const AUDJPY_FIXTURE: ChartSpec = {
  instrument: 'AUDJPY.s',
  baseTimeframe: 'M5',
  brokerGmtOffsetHours: 3,
  candles: CANDLES,
  // Generic market-session windows (data, not strategy logic). Times are local to each `tz`;
  // the panel places them on the broker-time axis (DST-aware). Colors are display tints.
  sessions: [
    { name: 'Tokyo', tz: 'Asia/Tokyo', start: '09:00', end: '15:00', color: '#8b5cf6' },
    { name: 'London', tz: 'Europe/London', start: '08:00', end: '16:00', color: '#00e5ff' },
  ],
  trades: [
    tradeAt(38, 66, 'long', 'T1', 'target'),   // ~03:10 → ~05:30 (Tokyo)
    tradeAt(124, 144, 'short', 'T2', 'stop'),  // ~10:20 → ~12:00 (London)
    tradeAt(168, 198, 'long', 'T3', 'target'), // ~14:00 → ~16:30
  ],
  overlays: OVERLAYS,
  indicators: INDICATORS,
}
