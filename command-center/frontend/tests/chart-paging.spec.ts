/**
 * The price chart's "go to date" jump — it is seamless now, and these pin the two ways it stops
 * being seamless without producing an error.
 *
 * 🔴 The defect Aaron reported (2026-08-06): jumping back six years took a REAL ninety seconds —
 * MEASURED at 90.3s and 14 network pages on run 211384ddbea4 at M15 — because the spec shipped only
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
 * ⚠ It drives the REAL backend rather than intercepting the candles route. The thing under test is
 * a full-history spec being sliced, so a mocked feed would be testing the mock.
 */
import { test, expect } from '@playwright/test'

// The longest python run in the lab — 2020-01-01 → 2026-08-01 at M15, so a 2020 target is about as
// far from the shipped right edge as this lab can ask for.
const RUN = '211384ddbea4'
const TARGET = '2020-06-01'

// Generous against the 2.0s measured, and an order of magnitude under the 90.3s this replaced. It
// is a REGRESSION guard, not a benchmark: anything that reintroduces per-window fetching or a
// full-history `applyNewData` lands in the tens of seconds and trips it.
const JUMP_BUDGET_MS = 20_000

const dayMs = (iso: string) => new Date(`${iso}T00:00:00`).getTime()

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
  await page.locator('input[type="date"]').fill(iso)
  await page.getByRole('button', { name: 'Go', exact: true }).click()
}

test('a six-year jump lands on the requested date in seconds, not minutes', async ({ page }) => {
  test.setTimeout(120_000)
  await openPriceTab(page)

  const before = await appliedWindow(page)
  // The target must genuinely be outside the applied window, or the jump is a scroll and this test
  // proves nothing. (Vacuity guard: the shipped window used to be ~17 months and is now ~4 months
  // of applied bars, so a 2020 target is well outside either — but assert it rather than assume.)
  expect(dayMs(TARGET)).toBeLessThan(before.lo)

  const t0 = Date.now()
  await jumpTo(page, TARGET)
  await expect
    .poll(async () => {
      const w = await appliedWindow(page)
      return dayMs(TARGET) >= w.lo && dayMs(TARGET) <= w.hi
    }, { timeout: JUMP_BUDGET_MS, intervals: [200] })
    .toBe(true)

  expect(Date.now() - t0).toBeLessThan(JUMP_BUDGET_MS)
})

test('a jump applies a BOUNDED window, not everything from the target to the present', async ({ page }) => {
  test.setTimeout(120_000)
  await openPriceTab(page)
  await jumpTo(page, TARGET)

  await expect
    .poll(async () => {
      const w = await appliedWindow(page)
      return dayMs(TARGET) >= w.lo && dayMs(TARGET) <= w.hi
    }, { timeout: JUMP_BUDGET_MS, intervals: [200] })
    .toBe(true)

  // 🔴 This is the structural half of the check above, and it is the one that says WHY the jump is
  // fast. The spec holds the whole run in memory, so it is one word's difference between slicing a
  // window around the target and slicing from the target to the newest bar — and the second hands
  // klinecharts ~155,000 candles, which is a MEASURED 30.8s of frozen main thread. The time budget
  // alone would let that through on a fast enough machine; the window's own span cannot.
  //
  // ~12,000 M15 bars is ~4 months of calendar. A year is loose enough not to pin `APPLIED_BARS` to
  // a number, tight enough that target→present (6 years) fails outright.
  const w = await appliedWindow(page)
  const spanDays = (w.hi - w.lo) / 86_400_000
  expect(spanDays).toBeLessThan(365)
})
