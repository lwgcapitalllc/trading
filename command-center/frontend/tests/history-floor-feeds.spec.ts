/**
 * The date picker's floor depends on the run's PARAMS, not just its chart timeframe.
 *
 * 🔴 THE DEFECT (2026-08-15, run `50331c7cbe96`): `exec_secondary` replays a 1m feed alongside
 * the 15m chart, and Vantage XAUUSD reaches 2018-09-13 at M15 but only 2018-09-14 at M1. The
 * picker read the CHART floor, offered 2018-09-13, the pre-flight agreed, and the run died at
 * 8% on the 1m load. **Retry could not fix it either** — the rerun modal read the same
 * chart-only floor and re-offered the same illegal date, so the only way out was deleting the
 * run and building a new one by hand, which is what was reported.
 *
 * ⚠ EVERY route here is intercepted, so this suite needs NO backend and no live MT5 terminal —
 * the `calendar.spec.ts` shape. The real `/history-limit` probes a broker through the SSH
 * tunnel, so an unmocked one reaches the live box from a unit check.
 *
 * ⚠ A fail-watch against HEAD is VACUOUS for the moved-to-floor check: `data-testid` is part of
 * the fix, so it would go red on the element being absent. Non-vacuity is by MUTATION, named on
 * each check.
 *
 * Needs the dev server on :5173.
 */
import { test, expect } from '@playwright/test'

// The production shape: two feeds, one day apart.
const M15_FLOOR = '2018-09-13'
const M1_FLOOR = '2018-09-14'

const RUN_ID = 'feedfloor0001'

function limitFor(minutes: number) {
  const floor = minutes === 1 ? M1_FLOOR : M15_FLOOR
  return {
    instrument: 'XAUUSD',
    runner: 'python',
    timeframe_minutes: minutes,
    earliest_date: floor,
    broker: 'VantageMarkets-Demo',
    verified: '2026-07-25',
    source: 'probed',
    note: `XAUUSD has no real ${minutes}-minute bars before ${floor} on VantageMarkets-Demo.`,
  }
}

/** A failed run whose stored start is BELOW the 1m floor — the reported run's exact shape. */
function failedRun(params: Record<string, unknown>) {
  return {
    run_id: RUN_ID,
    strategy_id: 'sos_fade',
    strategy_name: 'SOS Fade',
    instrument: 'XAUUSD',
    status: 'failed_error',
    runner: 'python',
    bar_type: 'Minute',
    bar_value: 15,
    start_date: M15_FLOOR,
    end_date: '2026-08-15',
    created_at: 1_755_000_000,
    params,
    evaluations: [],
    equity_curve: [],
    daily_pnl: [],
    regime_timeline: [],
    error_message: 'XAUUSD has no real 1-minute history before 2018-09-14',
  }
}

/**
 * Serves the limit the BACKEND would serve for the flags the page actually sent. That is the
 * whole subject: a page that sends no flags gets the chart floor and offers an illegal date.
 */
async function mock(page: import('@playwright/test').Page, params: Record<string, unknown>) {
  const seen: string[][] = []

  await page.route('**/api/backtests/history-limit*', async (route) => {
    const flags = new URL(route.request().url()).searchParams.getAll('flags')
    seen.push(flags)
    const minutes = flags.includes('exec_secondary') ? 1 : 15
    await route.fulfill({ json: limitFor(minutes) })
  })

  await page.route(`**/api/backtests/runs/${RUN_ID}`, async (route) => {
    await route.fulfill({ json: failedRun(params) })
  })
  // Everything else this page pulls; empty is fine — none of it is the subject.
  for (const p of ['**/api/backtests/runs?**', '**/api/rulesets*', '**/api/strategies*']) {
    await page.route(p, (route) => route.fulfill({ json: [] }))
  }
  await page.route('**/api/backtests/running-job', (route) =>
    route.fulfill({
      json: { nt8: { running: false }, mt5: { running: false }, python: { running: false } },
    })
  )

  return seen
}

async function openRerun(page: import('@playwright/test').Page) {
  await page.goto(`/backtests/runs/${RUN_ID}`)
  // The page HEADER's Retry — the only one, since 2026-08-15. It opened off the banner's own
  // button until the duplicate was removed; see `backtests.spec.ts` for why there is one.
  await page.getByRole('button', { name: /Retry/ }).click()
  await expect(page.getByRole('heading', { name: 'Rerun Backtest' })).toBeVisible()
}

test.describe('the floor follows the feeds the run actually loads', () => {
  test('a run with the secondary ON sends its flag, so the picker gets the 1m floor', async ({
    page,
  }) => {
    // MUTATION: drop `run.params` from the RerunModal's useHistoryLimit call — no flags are
    // sent, the served floor is the 15m one, and this goes red.
    const seen = await mock(page, { exec_secondary: true, exec_sl_deep: true })
    await openRerun(page)

    await expect.poll(() => seen.some((f) => f.includes('exec_secondary'))).toBe(true)
  })

  test('a run with the secondary OFF sends no feed flag, and is NOT narrowed', async ({ page }) => {
    // The guard against fixing this in the dangerous direction. `exec_sl_deep` is truthy and is
    // NOT a feed flag, so it may be SENT but must not move the floor — the backend intersects.
    // MUTATION: make `feeds_from_flags` accept any name and this run's floor jumps a day.
    const seen = await mock(page, { exec_secondary: false, exec_sl_deep: true })
    await openRerun(page)

    await expect.poll(() => seen.length).toBeGreaterThan(0)
    expect(seen.every((f) => !f.includes('exec_secondary'))).toBe(true)
    // The start it offers is the run's own — legal at M15, so nothing is moved.
    await expect(page.getByTestId('rerun-moved-to-floor')).toHaveCount(0)
    await expect(page.locator('input[type="date"]').first()).toHaveValue(M15_FLOOR)
  })
})

test.describe('Retry can fix a run that failed ON the floor', () => {
  test('an illegal start is MOVED to the floor and the modal says why', async ({ page }) => {
    // 🔴 The reported experience: "you should just be able to hit re-run". Before this the modal
    // re-offered 2018-09-13 and the rerun failed identically.
    // MUTATION: delete the `setStart(floor)` effect — the input keeps the illegal date, the
    // notice never renders, and Rerun stays disabled with nothing explaining it.
    await mock(page, { exec_secondary: true })
    await openRerun(page)

    await expect(page.getByTestId('rerun-moved-to-floor')).toBeVisible()
    await expect(page.locator('input[type="date"]').first()).toHaveValue(M1_FLOOR)
  })

  test('the notice NAMES the feed and the broker, not just a date', async ({ page }) => {
    // A picker that silently jumps a day reads as broken. It has to say which feed bound it —
    // the reader's chart is 15m and the floor that moved is the 1m one.
    // MUTATION: drop `timeframe_minutes` / `broker` from the sentence and this goes red.
    await mock(page, { exec_secondary: true })
    await openRerun(page)

    const notice = page.getByTestId('rerun-moved-to-floor')
    await expect(notice).toContainText('1m history')
    await expect(notice).toContainText('VantageMarkets-Demo')
  })

  test('Rerun is enabled AND armed with a date the run can actually serve', async ({ page }) => {
    // The point of the whole change: hitting Retry then Rerun works, with no delete-and-rebuild.
    //
    // 🔴 THIS CHECK WAS VACUOUS ON ITS FIRST WRITING and survived the params mutation. It
    // asserted only that Rerun was ENABLED — and under the defect the modal believes 2018-09-13
    // is legal (it read the 15m floor), so the button is enabled there too. It was green while
    // arming a rerun that the backend refuses with a 400: the exact wall being fixed.
    // **Enabled is not the property that matters; enabled with a SERVABLE date is.**
    // MUTATION: drop `run.params` from the hook and the value assertion goes red.
    await mock(page, { exec_secondary: true })
    await openRerun(page)

    await expect(page.locator('input[type="date"]').first()).toHaveValue(M1_FLOOR)
    await expect(page.getByRole('button', { name: 'Rerun', exact: true })).toBeEnabled()
  })
})
