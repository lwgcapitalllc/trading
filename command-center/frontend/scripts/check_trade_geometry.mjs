#!/usr/bin/env node
/**
 * The trade overlay's two price rules, pinned outside the browser.
 *
 * Run it:  node scripts/check_trade_geometry.mjs
 *   Needs nothing running. It is step 8 of `scripts/run_all_tests.sh`.
 *
 * 🔴 WHY THIS IS NOT A PLAYWRIGHT CHECK. A trade annotation is painted into klinecharts' canvas
 * and has no element of its own, so everything `tests/chart-trade-labels.spec.ts` can do is
 * measure pixels through a live backend and a live dev server — which is why that suite is not in
 * the automated gate. The two rules below are ARITHMETIC on prices, so they can be driven
 * directly, and both of them were wrong on real trades for as long as they existed.
 *
 * ⚠ **A fail-watch against HEAD is VACUOUS for every case here** — `tradeGeometry.ts` did not
 * exist, so a red would only prove the import failed. **Non-vacuity is by MUTATION**, and the map
 * below was RUN rather than reasoned. That is not pedantry: the first version of this comment was
 * written from inspection and three of its entries were wrong, in the direction that flatters —
 * each claimed a mutation was killed by more cases than actually died.
 *
 *   exitMarker:   the OLD rule, only an exact-price fill merges  #16
 *   exitMarker:   forget the fill merge entirely ............... #15 #16
 *   exitMarker:   forget the stop merge ........................ #13
 *   exitMarker:   refuse an unbanked exit (the older OLD rule) . #12 #14
 *   exitMarker:   invent an exit never recorded ................ #17
 *   adverseFloor: the OLD rule, a loser runs to its stop ....... #1 #2 #7 #8 #10
 *   adverseFloor: drop the stop clamp .......................... #6
 *   adverseFloor: never take the stop-out branch ............... #5
 *   adverseFloor: drop the went-against-it guard ............... #8
 *   adverseFloor: an unrecorded worst price reads as full ...... #9
 *   stoppedOut:   always false ................................. #5 #22 #23 #25
 *   exitSide:     demand real profit before favourable ......... #18
 *   exitSide:     never say adverse ............................ #19 #20
 *   exitSide:     forget a short is the mirror ................. #20
 *
 * ⚠ **Six cases no mutation above kills — #3 #4 #11 #21 #24 #26 — and they are listed rather than
 * quietly left in.** Each is a place where two paths through the module agree, so no single edit
 * separates them: a stop-out's floor comes out the same whether it is read off the stop-fill or
 * off the clamp. They are kept as DIRECTION and SHAPE checks (the short mirror, an exit exactly
 * on the entry, an absent field), not as proof of a branch. A case that cannot go red is worth
 * saying so about — this repo has shipped at least eight tests that passed against their own bug.
 *
 * THE TRADES ARE REAL. #1/#2/#12/#18 are the long of 2020-10-13 (entry 1901.71, stop 1879.72306,
 * worst 1882.36, came off at 1902.01 on its staged breakeven stop and still netted a loss on
 * costs) — the trade that showed a drawdown band running 2.64 past anything it traded, with no
 * exit drawn anywhere on it. #10/#11/#15 are the re-entry short of 2020-11-04, whose runner came
 * off at exactly its second rung — and whose two fills, 1895.40058 and 1895.72498, average to
 * the 1895.56278 that #16 refuses to draw.
 */
import { readFileSync, writeFileSync, mkdtempSync } from 'node:fs'
import { join } from 'node:path'
import { tmpdir } from 'node:os'
import { fileURLToPath, pathToFileURL } from 'node:url'
import { dirname } from 'node:path'
import { transformSync } from 'esbuild'

const HERE = dirname(fileURLToPath(import.meta.url))
const SRC = join(HERE, '..', 'src', 'components', 'ChartPanel', 'tradeGeometry.ts')

// ⚠ Transpiled rather than re-implemented. A check that restates the rule in its own arithmetic
// passes against a module that disagrees with it, which is the one thing it exists to catch.
const js = transformSync(readFileSync(SRC, 'utf8'), { loader: 'ts', format: 'esm' }).code
const out = join(mkdtempSync(join(tmpdir(), 'tradegeom-')), 'tradeGeometry.mjs')
writeFileSync(out, js)
const { adverseFloor, exitMarker, exitSide, stoppedOut } = await import(pathToFileURL(out).href)

let failed = 0
let n = 0
const eq = (got, want, what) => {
  n += 1
  const ok = got === want || (got === null && want === null)
  if (!ok) {
    failed += 1
    console.log(`  \x1b[31m✗\x1b[0m #${n} ${what}\n      got ${got}, want ${want}`)
  }
}

// ── adverseFloor ─────────────────────────────────────────────────────────────

// The trade the rule was written for. It came off ABOVE its entry and still lost, on costs.
const oct13 = {
  entryPrice: 1901.71,
  stopPrice: 1879.72306,
  maePrice: 1882.36,
  exitPrice: 1902.01,
  sign: 1,
}
eq(adverseFloor(oct13), 1882.36, 'a non-stopped loser floors at the worst price it TRADED')
eq(adverseFloor(oct13) === 1879.72306, false, 'and never at a stop it did not reach')

// The stop took it: the stop IS the drawdown, whatever worse number the run recorded.
eq(
  adverseFloor({
    entryPrice: 1901.71,
    stopPrice: 1879.72,
    maePrice: 1879.72,
    exitPrice: 1879.72,
    sign: 1,
  }),
  1879.72,
  'a stop-out floors at the stop'
)
eq(
  adverseFloor({
    entryPrice: 1901.71,
    stopPrice: 1879.72,
    maePrice: 1871.0,
    exitPrice: 1879.72,
    sign: 1,
  }),
  1879.72,
  'a stop-out ignores a worst price recorded BEYOND the stop (the pre-fix runs)'
)
eq(
  adverseFloor({
    entryPrice: 1901.71,
    stopPrice: 1879.72,
    maePrice: 1885.0,
    exitPrice: 1879.72,
    sign: 1,
  }),
  1879.72,
  'a stop FILL is itself proof price reached the stop, even when the recorded worst price falls short of it'
)

// Not stopped, yet the stored worst price is past the stop — a defect, not a measurement.
eq(
  adverseFloor({
    entryPrice: 1901.71,
    stopPrice: 1879.72,
    maePrice: 1871.0,
    exitPrice: 1908.0,
    sign: 1,
  }),
  1879.72,
  'a worst price past an UNHIT stop is clamped to the stop'
)
eq(
  adverseFloor({
    entryPrice: 1901.71,
    stopPrice: 1879.72,
    maePrice: 1890.0,
    exitPrice: 1908.0,
    sign: 1,
  }),
  1890.0,
  'a winner that sat through a drawdown floors at that drawdown'
)
eq(
  adverseFloor({
    entryPrice: 1901.71,
    stopPrice: 1879.72,
    maePrice: 1901.71,
    exitPrice: 1908.0,
    sign: 1,
  }),
  null,
  'a trade that never went against its entry gets no band at all'
)
eq(
  adverseFloor({ entryPrice: 1901.71, stopPrice: 1879.72, exitPrice: 1908.0, sign: 1 }),
  null,
  'a run that never recorded a worst price gets NO band — unasked is not the same as a full drawdown'
)

// The re-entry short of 2020-11-04 — the mirror, where adverse is UP.
eq(
  adverseFloor({
    entryPrice: 1904.93,
    stopPrice: 1912.55354,
    maePrice: 1909.8,
    exitPrice: 1895.56278,
    sign: -1,
  }),
  1909.8,
  'a short floors at the HIGHEST price it traded'
)
eq(
  adverseFloor({
    entryPrice: 1904.93,
    stopPrice: 1912.55354,
    maePrice: 1914.0,
    exitPrice: 1912.55354,
    sign: -1,
  }),
  1912.55354,
  'a stopped-out short floors at its stop, not above it'
)

// ── exitMarker ───────────────────────────────────────────────────────────────

eq(
  exitMarker({ exitPrice: 1902.01, legPrices: [], stopPrice: 1879.72306 }),
  'draw',
  'an exit that banked nothing is STILL drawn'
)
eq(
  exitMarker({ exitPrice: 1879.72, legPrices: [], stopPrice: 1879.72 }),
  'stop',
  'an exit AT the stop renames the SL chip instead of stacking a second line on it'
)
eq(
  exitMarker({ exitPrice: 1871.0, legPrices: [], stopPrice: 1879.72 }),
  'draw',
  'a stop-out that GAPPED past its stop is drawn where it really filled'
)
eq(
  exitMarker({ exitPrice: 1895.72498, legPrices: [1895.40058, 1895.72498], stopPrice: 1912.55354 }),
  'leg',
  'an exit a fill already draws is not drawn twice'
)
eq(
  exitMarker({ exitPrice: 1895.56278, legPrices: [1895.40058, 1895.72498], stopPrice: 1912.55354 }),
  'leg',
  'the size-weighted AVERAGE of two fills is never drawn — nothing traded there'
)
eq(exitMarker({ legPrices: [], stopPrice: 1879.72 }), 'none', 'no exit price, no marker')

// ── exitSide ─────────────────────────────────────────────────────────────────

eq(
  exitSide(1901.71, 1902.01, 1),
  'favourable',
  'a breakeven-stop exit reads FAVOURABLE on price, though the trade netted a loss on costs'
)
eq(exitSide(1901.71, 1879.72, 1), 'adverse', 'a long stopped out reads adverse')
eq(exitSide(1904.93, 1912.55, -1), 'adverse', 'a short stopped out reads adverse')
eq(exitSide(1901.71, 1901.71, 1), 'flat', 'an exit exactly at the entry reads flat')

// ── stoppedOut ───────────────────────────────────────────────────────────────

eq(stoppedOut(1879.72, 1879.72, 1), true, 'a long that filled at its stop is stopped out')
eq(stoppedOut(1871.0, 1879.72, 1), true, 'a long that gapped through its stop is stopped out')
eq(stoppedOut(1902.01, 1879.72306, 1), false, 'a long that came off above its stop is NOT')
eq(stoppedOut(1912.56, 1912.55354, -1), true, 'a short that filled at its stop is stopped out')
eq(stoppedOut(undefined, 1879.72, 1), false, 'a trade with no exit price cannot be called stopped')

console.log(failed ? `\n  ${failed} of ${n} FAILED\n` : `  trade geometry: ${n} cases green`)
process.exit(failed ? 1 : 0)
