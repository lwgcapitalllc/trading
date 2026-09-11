/**
 * The price chart's "go to date" jump — it is seamless now, and these pin the two ways it stops
 * being seamless without producing an error.
 *
 * 🔴 The defect Aaron reported (2026-08-06): jumping back six years took a REAL ninety seconds —
 * MEASURED at 90.3s and 14 network pages on run `211384ddbea4` at M15 (that run has since left the
 * lab; the figure stands, the id is history) — because the spec shipped only
 * the newest ~17 months and every older window was fetched, with its analysis replayed server-side.
 * The spec carries the whole run now and the panel slices it in memory: **90.3s → 2.0s, measured**.
 *
 * ⚠ These two checks REPLACED two that pinned the jump's progress readout (a reached-date label and
 * a filling bar), which was the right fix for a ninety-second wait and is meaningless for a
 * two-second one — there is no longer a wait to report, and the readout was deleted with it. What
 * has to be pinned instead is that the jump stays FAST and lands where it was asked to — one check
 * on the clock, one on the shape, because the failure this rewrite actually produced was invisible
 * to both on its own: growing the applied window from the target to the present instead of slicing
 * around the target gave the RIGHT answer in 47.6s.
 *
 * ✅ Both were watched RED by MUTATION (2026-08-06): `all.slice(from)` in place of
 * `all.slice(from, from + APPLIED_BARS)` fails the first on time and the second on span.
 *
 * ✅ OFFLINE since 2026-09-11: the run is `recordings/chart-sos-fade.json`, a year of M15 (23,714
 * bars). It replaced a fixture RESOLVED from the lab at start-up (the longest python run there),
 * which it did because a NAMED run had left the lab and taken both checks with it on 2026-08-16. A
 * recording cannot leave. ⚠ **What the shorter fixture costs, stated rather than hidden**: on
 * 23,714 bars the unbounded mutation (`all.slice(from)`) applies ~22,000 candles in a few seconds,
 * so it no longer fails the FIRST check on time — it fails the SECOND, which asserts the rule
 * itself: the applied window does not reach the newest bar. Mutation map re-run on this fixture.
 */
import { expect } from '@playwright/test'
import { offlineTest } from './offline'

const { test, recorded, recordedRun } = offlineTest('chart-sos-fade')
const RUN = recordedRun()
const RUN_START = recorded<{ start_date: string }>(`/backtests/runs/${RUN}`).start_date
const CANDLES = recorded<{ candles: { time: number }[] }>(
  `/backtests/runs/${RUN}/chart-spec`
).candles
const NEWEST_BAR = CANDLES[CANDLES.length - 1].time

// Generous against the 2.0s measured, and an order of magnitude under the 90.3s this replaced. It
// is a REGRESSION guard, not a benchmark: anything that reintroduces per-window fetching lands in
// the tens of seconds and trips it — and offline, a per-window fetch is also an unrecorded read,
// which the harness fails by name.
const JUMP_BUDGET_MS = 20_000

const dayMs = (iso: string) => new Date(`${iso}T00:00:00`).getTime()

// A month in from the run's own start: inside the data, and ~6 months before the ~12,000 bars the
// panel opens on, so the jump is a real one (the vacuity guard below asserts it). Derived from the
// recorded run, so it moves with it.
const TARGET = (() => {
  const t = new Date(`${RUN_START}T00:00:00`)
  t.setMonth(t.getMonth() + 1)
  return t.toISOString().slice(0, 10)
})()

async function openPriceTab(page: import('@playwright/test').Page) {
  await page.goto(`/backtests/runs/${RUN}`)
  await page.getByRole('button', { name: /price/i }).click()
  // The panel is warm-mounted and klinecharts lays the applied window out on mount; the Go to date
  // pill only renders once the chart has a loaded range to bound itself to.
  await expect(page.getByTitle('Go to date')).toBeVisible({ timeout: 60_000 })
}

/** The window klinecharts currently has applied, off the panel's own bounds. */
async function appliedWindow(page: import('@playwright/test').Page) {
  const root = page.locator('[data-applied-lo]').first()
  const [lo, hi] = await Promise.all([
    root.getAttribute('data-applied-lo'),
    root.getAttribute('data-applied-hi'),
  ])
  return { lo: Number(lo), hi: Number(hi) }
}

async function jumpTo(page: import('@playwright/test').Page, iso: string) {
  await page.getByTitle('Go to date').click()
  // ⚠ SCOPED TO THE PANEL'S OWN ROOT. It was a page-wide `input[type="date"]`, which was safe
  // exactly as long as this page had one date input — and BacktestDetail's period filter added two
  // more to the header on 2026-08-16. A page-wide locator matching a control that is not the one
  // under test is this folder's most-repeated trap, and it fails by PASSING.
  await page.locator('[data-applied-lo]').first().locator('input[type="date"]').fill(iso)
  await page.getByRole('button', { name: 'Go', exact: true }).click()
}

test('a long jump lands on the requested date in seconds, not minutes', async ({ page }) => {
  test.setTimeout(120_000)
  await openPriceTab(page)

  const before = await appliedWindow(page)
  // The target must genuinely be outside the applied window, or the jump is a scroll and this test
  // proves nothing. Asserted rather than assumed: it depends on the recording's length and on
  // `APPLIED_BARS`, and a change to either could quietly turn the jump into a scroll.
  expect(dayMs(TARGET)).toBeLessThan(before.lo)

  const t0 = Date.now()
  await jumpTo(page, TARGET)
  await expect
    .poll(
      async () => {
        const w = await appliedWindow(page)
        return dayMs(TARGET) >= w.lo && dayMs(TARGET) <= w.hi
      },
      { timeout: JUMP_BUDGET_MS, intervals: [200] }
    )
    .toBe(true)

  expect(Date.now() - t0).toBeLessThan(JUMP_BUDGET_MS)
})

test('a jump applies a BOUNDED window, not everything from the target to the present', async ({
  page,
}) => {
  test.setTimeout(120_000)
  await openPriceTab(page)
  await jumpTo(page, TARGET)

  await expect
    .poll(
      async () => {
        const w = await appliedWindow(page)
        return dayMs(TARGET) >= w.lo && dayMs(TARGET) <= w.hi
      },
      { timeout: JUMP_BUDGET_MS, intervals: [200] }
    )
    .toBe(true)

  // 🔴 This is the structural half of the check above, and it is the one that says WHY the jump is
  // fast. The spec holds the whole run in memory, so it is one word's difference between slicing a
  // window around the target and slicing from the target to the newest bar — and on a full-history
  // run the second hands klinecharts ~155,000 candles, a MEASURED 30.8s of frozen main thread.
  //
  // So assert the rule itself: the window stops short of the newest bar. The target sits ~11
  // months before it and ~12,000 M15 bars is ~6 months, so a bounded window cannot reach it and
  // the unbounded one always does — without pinning `APPLIED_BARS` to a number.
  const w = await appliedWindow(page)
  expect(w.hi).toBeLessThan(NEWEST_BAR)
  expect((w.hi - w.lo) / 86_400_000).toBeLessThan(365)
})
