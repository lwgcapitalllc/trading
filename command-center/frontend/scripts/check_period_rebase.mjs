#!/usr/bin/env node
/**
 * The period filter's arithmetic, pinned outside the browser.
 *
 * 🔴 WHY THIS IS NOT A PLAYWRIGHT CHECK. The three properties below are numeric IDENTITIES, and
 * the page renders them through `FitMoney`, `dollar()` and a two-decimal formatter. Asserting them
 * through rendered text would be asserting on the formatter — it would pass against a rebase that
 * was wrong in the fourth decimal and fail on a currency-symbol change. `tests/period-filter.spec.ts`
 * checks that the CONTROL exists, reaches every section and says what it is doing; this checks that
 * what it is doing is right.
 *
 * Run it:  node scripts/check_period_rebase.mjs [runId] [fromDate]
 *   Needs the backend on :8000. With no arguments it picks the newest completed run carrying ≥20
 *   dated trades and splits it in half — deliberately NOT a named run, because a script pinned to
 *   one row is a script with an expiry date (two suites in this folder have already broken that
 *   way).
 *
 * WHAT IT PROVES, and each is a claim the feature's comments make out loud:
 *
 *   1. THE REBASE IS THE R-REPLAY. Scaling every profit in the window by one constant —
 *      the run's opening balance over the balance entering the window — lands on the same final
 *      equity as compounding `balance *= 1 + r × (risk_usd / balance_before)` from that opening
 *      balance. That is what makes the rebase exact arithmetic rather than a model, and it is only
 *      true because the scale is a single constant.
 *
 *   2. EVERY RATIO IS INVARIANT. Profit factor, win rate and peak-relative drawdown must be
 *      IDENTICAL before and after the rebase. If one ever differs, the scale has stopped being
 *      constant and the rebase is wrong — do not special-case the ratio.
 *
 *   3. R IS UNTOUCHED. The per-trade `r` is P&L over the risk the trade was sized to, so it cannot
 *      move when the account size does. The page leads with it for exactly that reason.
 *
 * ⚠ It does NOT re-implement the hook. It restates the two-line identity the hook rests on; if the
 * hook grows a second definition of the scale, this stops being evidence about it — which is the
 * point at which the hook has a bug.
 */
import fs from 'node:fs'
import path from 'node:path'
import { fileURLToPath } from 'node:url'

const API = process.env.CC_API ?? 'http://localhost:8000'
const REPORTS = path.resolve(
  path.dirname(fileURLToPath(import.meta.url)),
  '../../backend/reports/lab'
)

/**
 * The stored trade list for a run, if this machine has it.
 *
 * 🔴 IT IS NEEDED, AND WHY IS THE INTERESTING PART. `risk_usd` is written to
 * `equity_curve.json` and is NOT declared on the backend's `EquityPoint` model, so FastAPI drops
 * it and the API's copy of a trade cannot answer the R-replay question. That is this repo's
 * recorded "the model drops any field it does not declare" trap — met here as a limit on what can
 * be PROVEN rather than as a rendering bug, since nothing in the browser needs the field (the
 * rebase is a pure scale). Declaring it purely to satisfy this script would put ~8 bytes × every
 * trade on every run-detail request for a check that runs on a dev box.
 *
 * ⚠ So the identity is checked against the RECORD rather than the response, and the script SAYS
 * which source it used. A skip is reported as a skip, never folded into a pass.
 */
function storedCurve(runId) {
  const p = path.join(REPORTS, runId, 'equity_curve.json')
  try {
    return JSON.parse(fs.readFileSync(p, 'utf8'))
  } catch {
    return null
  }
}

async function get(path) {
  const res = await fetch(API + path)
  if (!res.ok) throw new Error(`backend not answering for ${path} (${res.status}) — is it running?`)
  return res.json()
}

async function pickRun(minTrades = 20) {
  const runs = await get('/backtests/runs')
  for (const r of runs) {
    if (r.status !== 'complete' || (r.trade_count ?? 0) < minTrades) continue
    const detail = await get(`/backtests/runs/${r.run_id}?timeline=false`)
    const dated = detail.equity_curve.filter((p) => p.profit != null && p.date)
    if (dated.length >= minTrades) return { runId: r.run_id, dated }
  }
  throw new Error(`no completed run with >= ${minTrades} dated trades`)
}

const pf = (ts) => {
  let w = 0,
    l = 0
  for (const t of ts) t.profit > 0 ? (w += t.profit) : (l -= t.profit)
  return l > 0 ? w / l : null
}
const winRate = (ts) => ts.filter((t) => t.profit > 0).length / ts.length
const maxDdPct = (ts, base) => {
  let eq = base,
    peak = base,
    worst = 0
  for (const t of ts) {
    eq += t.profit
    peak = Math.max(peak, eq)
    worst = Math.max(worst, (peak - eq) / peak)
  }
  return worst
}

const fails = []
const check = (name, ok, detail) => {
  console.log(`${ok ? '  PASS' : '  FAIL'}  ${name}${detail ? `  — ${detail}` : ''}`)
  if (!ok) fails.push(name)
}

const [, , argRun, argFrom] = process.argv
let runId, dated
if (argRun) {
  runId = argRun
  const detail = await get(`/backtests/runs/${runId}?timeline=false`)
  dated = detail.equity_curve.filter((p) => p.profit != null && p.date)
} else {
  ;({ runId, dated } = await pickRun())
}
const from = argFrom ?? (dated[Math.floor(dated.length / 2)].date ?? '').slice(0, 10)

const kept = dated.filter((p) => (p.date ?? '').slice(0, 10) >= from)
const openBal = dated[0].equity - (dated[0].profit ?? 0)
const windowBal = kept[0].equity - (kept[0].profit ?? 0)
const scale = openBal / windowBal

console.log(`run ${runId} · window from ${from}`)
console.log(
  `  ${kept.length} of ${dated.length} trades · opened $${openBal.toLocaleString()} · entered the window at $${Math.round(windowBal).toLocaleString()} · scale ×${scale.toFixed(6)}\n`
)

if (kept.length === dated.length) throw new Error('the window did not narrow — nothing is pinned')

// The rebase, exactly as `useDateFilter` performs it.
let cum = 0
const rebased = kept.map((p) => {
  cum += (p.profit ?? 0) * scale
  return { ...p, equity: openBal + cum, profit: (p.profit ?? 0) * scale }
})

// 1 — the rebase IS the R-replay. Read off the STORED curve, which is the only copy carrying
// `risk_usd` (see `storedCurve`).
const stored = storedCurve(runId)
const storedKept = (stored ?? [])
  .filter((p) => p.profit != null && p.date)
  .filter((p) => p.date.slice(0, 10) >= from)
const hasR = storedKept.length === kept.length && storedKept.every((t) => t.r != null && t.risk_usd)
if (!hasR) {
  console.log(
    stored
      ? '  SKIP  the R-replay identity — this run stores no per-trade r / risk_usd'
      : `  SKIP  the R-replay identity — no stored curve at ${path.join(REPORTS, runId)}`
  )
} else {
  let bal = openBal
  for (const t of storedKept) bal *= 1 + t.r * (t.risk_usd / (t.equity - t.profit))
  const got = rebased[rebased.length - 1].equity
  const drift = Math.abs(got - bal) / bal
  check(
    'the rebase reproduces the R-replay (from the stored curve)',
    drift < 1e-4,
    `$${got.toFixed(2)} vs $${bal.toFixed(2)} (${(drift * 100).toFixed(6)}%)`
  )
}

// 2 — every ratio is invariant under the rebase.
const same = (a, b) => (a == null || b == null ? a === b : Math.abs(a - b) < 1e-9)
check('profit factor is invariant', same(pf(kept), pf(rebased)), `${pf(kept)?.toFixed(9)}`)
check('win rate is invariant', same(winRate(kept), winRate(rebased)), `${winRate(kept).toFixed(9)}`)
check(
  'peak-relative drawdown is invariant',
  same(maxDdPct(kept, windowBal), maxDdPct(rebased, openBal)),
  `${(maxDdPct(kept, windowBal) * 100).toFixed(6)}%`
)

// 3 — R is untouched by the rebase.
if (hasR) {
  const rBefore = kept.reduce((a, t) => a + t.r, 0)
  const rAfter = rebased.reduce((a, t) => a + t.r, 0)
  check('R is untouched', same(rBefore, rAfter), `${rBefore.toFixed(4)}R`)
}

// A guard against the whole thing being vacuous: the dollars MUST move, or every identity above
// is trivially satisfied by a rebase that did nothing.
const netBefore = kept.reduce((a, t) => a + t.profit, 0)
const netAfter = rebased.reduce((a, t) => a + t.profit, 0)
check(
  'the dollars really were rebased (this check is not vacuous)',
  Math.abs(netBefore - netAfter) > Math.abs(netBefore) * 1e-6,
  `$${Math.round(netBefore).toLocaleString()} → $${Math.round(netAfter).toLocaleString()}`
)

console.log(fails.length ? `\n${fails.length} FAILED` : '\nall checks passed')
process.exit(fails.length ? 1 : 0)
