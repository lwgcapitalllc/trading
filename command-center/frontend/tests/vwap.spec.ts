/**
 * The Session VWAP layer on the backtest price chart.
 *
 * The layer is an entry in `ChartSpec.indicators`, so the panel's existing indicator machinery
 * draws it and there is very little new code to test. What IS new, and what these pin, is the
 * two-sided contract around it:
 *
 *   1. it must arrive switched OFF (`defaultOn: false`) — every analysis layer added since the
 *      fair value gaps does — while an indicator that OMITS the field must still arrive ON,
 *      because the ATR sub-pane has opened on since it shipped and the field did not exist
 *      before this layer needed it;
 *   2. a reader's answer must SURVIVE a roster rebuild, which is the half that would break
 *      silently. `indicatorsOn` was re-seeded from `spec.indicators` on every change rather than
 *      reconciled — safe only while nothing carried a non-default, and a silent reset of the
 *      reader's toggle the moment one did.
 *
 * ⚠ It drives the REAL backend for the layer's own existence, because that is a server-side engine
 * replay reaching the chart and a mocked spec would be testing the mock. The absent-`defaultOn`
 * case is the one thing the live lab cannot supply — the only run carrying an ATR pane is a
 * London-breakout one, and this run is not — so that case MUTATES the real response rather than
 * being hand-written, the same discipline the Overview and Stress Tests suites use.
 *
 * ⚠ `data-indicators-on` on the panel root is a declared TEST SEAM. An indicator draws into the
 * candle pane's CANVAS, so "is the line on screen" has no DOM answer, and a check that settled for
 * "the menu row is ticked" would pass against a panel drawing nothing.
 */
import { expect, test, type Page } from '@playwright/test'

// The longest python run in the lab: 2020-01-01 → 2026-08-06 at M15, ~156k candles, so the VWAP
// series is a real full-history one rather than a handful of points.
const RUN = '997c14cc53bc'

const VWAP = 'Session VWAP'

/** The indicator names klinecharts currently holds, off the panel's own create pass. */
async function drawn(page: Page) {
  const attr = await page.locator('[data-indicators-on]').first().getAttribute('data-indicators-on')
  return (attr ?? '').split('|').filter(Boolean)
}

async function openPriceTab(page: Page) {
  await page.goto(`/backtests/runs/${RUN}`)
  await page.getByRole('button', { name: /price/i }).click()
  // The panel is warm-mounted and klinecharts lays the applied window out on mount; the Go to date
  // pill only renders once the chart has a loaded range to bound itself to.
  await expect(page.getByTitle('Go to date')).toBeVisible({ timeout: 90_000 })
}

async function openStructureMenu(page: Page) {
  await openPriceTab(page)
  await page.getByRole('button', { name: /^Structure/ }).click()
}

test('the VWAP is offered as a layer and starts switched OFF', async ({ page }) => {
  await openStructureMenu(page)

  await expect(page.getByRole('button', { name: new RegExp(VWAP) })).toBeVisible()
  // Off on arrival. A chart opens on the run; each extra reading is something the reader asks for.
  expect(await drawn(page)).not.toContain(VWAP)
})

test('ticking it draws the line', async ({ page }) => {
  await openStructureMenu(page)

  await page.getByRole('button', { name: new RegExp(VWAP) }).click()
  await expect.poll(() => drawn(page)).toContain(VWAP)
})

test('an indicator that omits defaultOn still arrives ON', async ({ page }) => {
  // The rule the ATR sub-pane depends on, and the one a `?? false` default would silently break.
  // No run in this lab carries both an ATR pane and a VWAP, so the second indicator is injected
  // into the REAL spec rather than the whole response being hand-written.
  await page.route(`**/backtests/runs/${RUN}/chart-spec*`, async route => {
    const res = await route.fetch()
    const spec = await res.json()
    const vwap = spec.indicators.find((i: { name: string }) => i.name === VWAP)
    spec.indicators = [
      ...spec.indicators,
      { name: 'ATR', pane: 'sub', series: vwap.series.slice(0, 500) }, // no defaultOn
    ]
    await route.fulfill({ response: res, json: spec })
  })

  await openPriceTab(page)

  const on = await drawn(page)
  expect(on).toContain('ATR')
  expect(on).not.toContain(VWAP)
})

// 🔴 A FIFTH CHECK WAS WRITTEN, PASSED, AND WAS DELETED FOR FAILING TO BITE.
//
// It claimed the reader's toggle survives a roster rebuild — the `reconcileToggles` rule, which
// `groupsOn` genuinely needed. It switched the display timeframe and asserted the VWAP was still
// drawn, and it **passed with `reconcileToggles` replaced by a plain re-seed**, which is the exact
// defect it named.
//
// The reason is that the condition cannot be produced from the UI. `indicatorRoster` is memoized on
// `spec.indicators`, a timeframe switch is a display-only resample that never touches the spec, and
// `useRefreshChartSpec` — the one thing that would swap the object — has NO CALLERS. So nothing in
// this app rebuilds that roster during a session, and a green test there was asserting that a
// timeframe switch does not do something it was never going to do.
//
// The reconcile STAYS in the panel: it costs nothing and it is the correct shape for a roster
// derived from data. But it is defensive rather than exercised, and this comment is the honest
// record of that, because a passing test would have claimed otherwise.
