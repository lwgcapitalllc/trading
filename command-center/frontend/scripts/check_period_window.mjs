#!/usr/bin/env node
/**
 * The PERIOD window's arithmetic, pinned outside the browser.
 *
 * Run it:  node scripts/check_period_window.mjs
 *   Needs nothing running. It is step 10 of `scripts/run_all_tests.sh`.
 *
 * 🔴 WHY IT EXISTS. `cutPeriod` returns the constant that EVERY dollar on two different pages is
 * multiplied by — the single-backtest page and the stack page both read it. Until 2026-09-03 this
 * logic lived inside a hook, reachable only from a browser, which is the same shape that let the
 * trade box draw a wrong adverse band on real trades for as long as it sat inside a chart callback.
 * A wrong scale here is not a broken chart; it is a plausible dollar figure nobody can tell is wrong.
 *
 * ⚠ The module is TRANSPILED, never re-implemented. A check that restates the arithmetic in its own
 * terms passes against a module that disagrees with it, which is the one thing it is for.
 *
 * ⚠ NON-VACUITY IS BY MUTATION, and this map was RUN rather than reasoned. That is not a formality
 * here: the FIRST version of cases 12-15 could not fail. They used a window opening on the book's
 * own first trade, where the entering balance IS the deposit and the scale is therefore exactly 1 —
 * so "this field is multiplied by the scale" and "this field is left alone" are the same assertion.
 * Scaling `r` and dropping the `favorable` scaling both SURVIVED against four green cases. The
 * fixture now uses a window whose scale is not 1, and the case throws if that ever stops being true.
 *
 *   narrowed is always true ................... kills 4 5
 *   `from` becomes exclusive .................. kills 17
 *   `to` becomes exclusive .................... kills 18
 *   scale inverted ............................ kills 9 10 11
 *   R gets scaled too ......................... kills 15
 *   favorable stops scaling ................... kills 12
 *   a zero entering balance is allowed ........ kills 23
 *   an undated trade is kept in range ......... kills 24
 *   index not renumbered ...................... kills 16
 *   equity restarts at the window balance ..... kills 11
 *
 * ⚠ Cases 1 2 3 6 7 8 13 14 19 20 21 22 25 are killed by NO mutation above and are listed rather
 * than quietly left in. Each is a direction check — the unfiltered behaviour that must keep working
 * while the windowed case lands, the negative half of a case whose positive half is pinned, or (25)
 * the linearity invariant, which cannot fail while the scale is a single constant. A case that
 * cannot go red is worth saying so about rather than counting.
 */
import { readFileSync, writeFileSync, mkdtempSync } from 'node:fs'
import { join, dirname } from 'node:path'
import { tmpdir } from 'node:os'
import { fileURLToPath, pathToFileURL } from 'node:url'
import { transformSync } from 'esbuild'

const HERE = dirname(fileURLToPath(import.meta.url))
const SRC = join(HERE, '..', 'src', 'components', 'periodWindow.ts')

// The module imports a TYPE only, so `transformSync` erases it and there is no alias to resolve at
// run time. A VALUE import added there would break this loader with an unhelpful MODULE_NOT_FOUND.
const js = transformSync(readFileSync(SRC, 'utf8'), { loader: 'ts', format: 'esm' }).code
const out = join(mkdtempSync(join(tmpdir(), 'periodwin-')), 'periodWindow.mjs')
writeFileSync(out, js)
const { cutPeriod } = await import(pathToFileURL(out).href)

// A four-trade book opening at $10,000. Equity is the running balance AFTER each trade, which is
// the shape both pages hand in.
const BOOK = [
  { index: 1, date: '2020-03-01', equity: 11000, profit: 1000, r: 2, favorable: 1500, adverse: -300, costs_usd: -10 },
  { index: 2, date: '2021-06-01', equity: 10500, profit: -500, r: -1, favorable: 200, adverse: -700 },
  { index: 3, date: '2022-09-01', equity: 21000, profit: 10500, r: 3, favorable: 12000, adverse: -900, costs_usd: -40 },
  { index: 4, date: '2023-12-01', equity: 16000, profit: -5000, r: -1 },
]

let failed = 0
const check = (why, got, want) => {
  const ok = Math.abs(got - want) < 1e-9 || got === want
  if (!ok) {
    failed += 1
    console.log(`  \x1b[31m✗\x1b[0m ${why}\n      got ${got}, want ${want}`)
  }
}
const checkIs = (why, got, want) => {
  if (got !== want) {
    failed += 1
    console.log(`  \x1b[31m✗\x1b[0m ${why}\n      got ${JSON.stringify(got)}, want ${JSON.stringify(want)}`)
  }
}

// 1-3 — an unset window must leave the book alone, not route it through a rebuild.
{
  const c = cutPeriod(BOOK, '', '')
  checkIs('1 unset window does not narrow', c.narrowed, false)
  checkIs('2 unset window builds no curve', c.curve, null)
  checkIs('3 unset window offers no scale', c.scale, null)
}

// 4-5 — a window covering everything is NOT narrowed. This is the case a naive `from <= d` would
// get wrong by rebuilding an identical curve and flipping the page into its "filtered" chrome.
{
  const c = cutPeriod(BOOK, '2020-01-01', '2024-01-01')
  checkIs('4 a window covering the whole book does not narrow', c.narrowed, false)
  checkIs('5 ...and builds no curve', c.curve, null)
}

// 6-11 — the real case. Entering 2022-09-01 the account held $10,500, so the scale is 10000/10500.
{
  const c = cutPeriod(BOOK, '2022-01-01', '')
  checkIs('6 narrows to the trades in range', c.kept.length, 2)
  check('7 window balance is what the account really held entering it', c.windowBalance, 10500)
  check('8 open balance is the book\'s own deposit', c.openBalance, 10000)
  check('9 scale is open over entering', c.scale, 10000 / 10500)
  check('10 first rebased profit scales by it', c.curve[0].profit, 10500 * (10000 / 10500))
  check('11 equity restarts from the deposit', c.curve[0].equity, 10000 + 10500 * (10000 / 10500))
}

// 12-15 — WHICH fields scale. `r` must not: it is P&L over the risk the trade was sized to, so it
// is invariant under a change of account size, and it is what a windowed row is compared on.
//
// 🔴 THE WINDOW HERE MUST BE ONE WHOSE SCALE IS NOT 1, AND THAT IS THE WHOLE POINT OF THE CASE.
// These four first used a window opening on the book's FIRST trade — where the entering balance IS
// the deposit, so the scale is exactly 1 and multiplying by it changes nothing. All four passed,
// and a mutation run showed two of them could not fail: scaling `r` and dropping the `favorable`
// scaling both SURVIVED. A scaling assertion at scale 1 asserts nothing.
{
  const c = cutPeriod(BOOK, '2022-01-01', '')
  const s = c.scale
  if (Math.abs(s - 1) < 1e-9) throw new Error('cases 12-15 need a scale != 1 or they assert nothing')
  check('12 favorable scales', c.curve[0].favorable, 12000 * s)
  check('13 adverse scales', c.curve[0].adverse, -900 * s)
  check('14 costs scale', c.curve[0].costs_usd, -40 * s)
  checkIs('15 R is NOT scaled', c.curve[0].r, 3)
}

// 16 — trades renumber from 1, so a trade-# axis counts the trades actually shown.
{
  const c = cutPeriod(BOOK, '2022-01-01', '')
  checkIs('16 index renumbers from 1', c.curve.map((p) => p.index).join(','), '1,2')
}

// 17-19 — bounds are INCLUSIVE on both ends, and a date outside is out.
{
  checkIs('17 `from` is inclusive', cutPeriod(BOOK, '2021-06-01', '').kept.length, 3)
  checkIs('18 `to` is inclusive', cutPeriod(BOOK, '', '2021-06-01').kept.length, 2)
  checkIs('19 a day later excludes it', cutPeriod(BOOK, '2021-06-02', '').kept.length, 2)
}

// 20-21 — a window with nothing in it is a real answer (the strategy stood still) and must not be
// dressed up as a rebase.
{
  const c = cutPeriod(BOOK, '2019-01-01', '2019-12-31')
  checkIs('20 an empty window keeps nothing', c.kept.length, 0)
  checkIs('21 ...and refuses to rebase', c.curve, null)
}

// 22-23 — REFUSE, don't guess. A window entered at a non-positive balance has no defined scale, and
// inventing one would put a made-up constant under every dollar on the page.
{
  const blown = [
    { index: 1, date: '2020-03-01', equity: 0, profit: -10000 },
    { index: 2, date: '2021-06-01', equity: 500, profit: 500 },
  ]
  const c = cutPeriod(blown, '2021-01-01', '')
  check('22 a window entered at zero is detected', c.windowBalance, 0)
  checkIs('23 ...and is refused rather than scaled', c.curve, null)
}

// 24 — an undated trade cannot be placed in or out of a window. The hook disables the control on
// such a book; this pins that `cutPeriod` drops rather than silently keeps it.
{
  const mixed = [...BOOK, { index: 5, equity: 17000, profit: 1000 }]
  checkIs('24 an undated trade is dropped, never assumed in range', cutPeriod(mixed, '2022-01-01', '').kept.length, 2)
}

// 25 — the invariant the whole design rests on: the rebased curve's net, divided by the scale, is
// the window's real net. If this ever fails the scale has stopped being a single constant.
{
  const c = cutPeriod(BOOK, '2022-01-01', '')
  const rebasedNet = c.curve.reduce((a, p) => a + p.profit, 0)
  const realNet = c.kept.reduce((a, p) => a + p.profit, 0)
  check('25 rebased net over scale is the real net', rebasedNet / c.scale, realNet)
}

if (failed) {
  console.log(`\n\x1b[31m✗ period window: ${failed} case(s) failed\x1b[0m`)
  process.exit(1)
}
console.log('\x1b[32m✓\x1b[0m period window: 25 cases')
