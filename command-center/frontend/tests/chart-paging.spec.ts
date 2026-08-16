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
 * ⚠ It drives the REAL backend rather than intercepting the candles route. The thing under test is
 * a full-history spec being sliced, so a mocked feed would be testing the mock.
 */
import { test, expect } from '@playwright/test'
import type { BacktestDetail, BacktestSummary } from '../src/types'

// 🔴 THE RUN IS RESOLVED, NOT NAMED, AND THAT IS A REPAIR (2026-08-16). This file carried
// `const RUN = '211384ddbea4'`, and the day that run left the lab BOTH checks failed: the endpoint
// 404s, so the price chart never renders, `Go to date` never appears and the click times out —
// pointing squarely at the paging code, which was fine. **A test that asserts on which rows happen
// to be in the database is a test that will fail on a day nothing is wrong**, and the failure is
// indistinguishable from a regression until somebody reads it. Third instance in this folder:
// `tuning.spec.ts` lost eight checks the same way and `backtests.spec.ts`'s millions check before
// it. The TARGET is derived from the resolved run for the same reason — pinning a date would move
// the expiry from the run id to the calendar rather than removing it.
const API = 'http://localhost:8000'

// Generous against the 2.0s measured, and an order of magnitude under the 90.3s this replaced. It
// is a REGRESSION guard, not a benchmark: anything that reintroduces per-window fetching or a
// full-history `applyNewData` lands in the tens of seconds and trips it.
const JUMP_BUDGET_MS = 20_000

/**
 * The jump has to be LONG or these checks pin nothing — a target already inside the applied window
 * is a scroll. Three years is well past the ~4 months of bars the panel applies, and every python
 * run in this lab spans six or more, so it selects rather than excludes.
 */
const MIN_SPAN_YEARS = 3

const dayMs = (iso: string) => new Date(`${iso}T00:00:00`).getTime()
const spanYears = (r: { start_date: string; end_date: string }) =>
  (dayMs(r.end_date) - dayMs(r.start_date)) / (365.25 * 86_400_000)

async function getJson<T>(path: string): Promise<T> {
  const res = await fetch(API + path)
  if (!res.ok) throw new Error(`backend not answering for ${path} (${res.status}) — is it running?`)
  return res.json() as Promise<T>
}

/**
 * Does this run have a built ChartSpec? Without one the Price tab renders "No price data" and every
 * locator below times out for a reason that has nothing to do with paging.
 *
 * ⚠ ABORTED AFTER THE HEADERS. The spec is ~33 MB and the backend ignores `Range`, so reading the
 * body to learn a status code would pull it in full — per candidate. `fetch` resolves as soon as
 * the headers land, which is all this asks.
 */
async function hasChartSpec(runId: string): Promise<boolean> {
  const ctl = new AbortController()
  try {
    const res = await fetch(`${API}/backtests/runs/${runId}/chart-spec`, { signal: ctl.signal })
    return res.ok
  } catch {
    return false
  } finally {
    ctl.abort()
  }
}

/**
 * The longest-spanning INTRADAY python run the lab currently holds, with the trades and the spec
 * this suite needs. Longest wins because the jump's whole point is reaching for the far end.
 */
async function resolveFixture(): Promise<{ runId: string; target: string }> {
  const runs = await getJson<BacktestSummary[]>('/backtests/runs')
  const candidates = runs
    .filter((r) => r.status === 'complete' && (r.trade_count ?? 0) > 0)
    .filter((r) => !!r.start_date && !!r.end_date && spanYears(r) >= MIN_SPAN_YEARS)
    .sort((a, b) => spanYears(b) - spanYears(a))

  for (const r of candidates) {
    // `bar_type` is on the DETAIL, not the summary — an M15 run is what pages; a D1 run has no
    // sub-base bars and the panel disables drill-down entirely.
    const d = await getJson<BacktestDetail>(`/backtests/runs/${r.run_id}?timeline=false`)
    if (d.runner !== 'python') continue
    if (d.bar_type !== 'Minute') continue
    if (!d.equity_curve?.length) continue
    if (!(await hasChartSpec(r.run_id))) continue
    // Six months in from the run's own start: inside the data with room to spare, and years from
    // the right edge the chart opens on. Derived, so it moves with whatever run is resolved.
    const t = new Date(`${d.start_date}T00:00:00`)
    t.setMonth(t.getMonth() + 6)
    return { runId: r.run_id, target: t.toISOString().slice(0, 10) }
  }
  throw new Error(
    `no completed intraday python run spanning ≥${MIN_SPAN_YEARS}y with trades and a chart spec — this suite needs one`
  )
}

let RUN = ''
let TARGET = ''

test.beforeAll(async () => {
  ;({ runId: RUN, target: TARGET } = await resolveFixture())
})

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
  // proves nothing. (Vacuity guard: the shipped window used to be ~17 months and is now ~4 months
  // of applied bars, so a target six months into a multi-year run is well outside either — but
  // assert it rather than assume, since the fixture is now resolved rather than named.)
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
