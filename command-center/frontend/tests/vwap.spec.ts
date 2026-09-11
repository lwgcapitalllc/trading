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
 * ⚠ It replays a RECORDED spec (`recordings/chart-sos-fade.json`), taken off a real server-side
 * engine replay — not a hand-written one, which would be testing the mock. The absent-`defaultOn`
 * case is the one thing the lab cannot supply — the only run carrying an ATR pane is a
 * London-breakout one, and this run is not — so that case MUTATES the recorded response rather
 * than being hand-written, the same discipline the Overview and Stress Tests suites use.
 *
 * ⚠ `data-indicators-on` on the panel root is a declared TEST SEAM. An indicator draws into the
 * candle pane's CANVAS, so "is the line on screen" has no DOM answer, and a check that settled for
 * "the menu row is ticked" would pass against a panel drawing nothing.
 */
import { expect, type Page } from '@playwright/test'
import { offlineTest } from './offline'

// A year of M15 bars that carry VOLUME — without it there is no Session VWAP layer at all — so the
// series is a real one of ~23,700 points rather than a handful.
const { test, recorded, recordedRun } = offlineTest('chart-sos-fade')
const RUN = recordedRun()
const SPEC = `/backtests/runs/${RUN}/chart-spec`

const VWAP = 'Session VWAP'

type Spec = { indicators: { name: string; series: unknown[] }[] }

/** The recorded spec with an ATR pane added that states NO `defaultOn` — see the two checks below. */
function specPlusAtr(): Spec {
  const spec = recorded<Spec>(SPEC)
  const vwap = spec.indicators.find((i) => i.name === VWAP)!
  spec.indicators = [
    ...spec.indicators,
    { name: 'ATR', pane: 'sub', series: vwap.series.slice(0, 500) } as Spec['indicators'][number],
  ]
  return spec
}

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
  // into the RECORDED spec rather than the whole response being hand-written.
  await page.route(`**/backtests/runs/${RUN}/chart-spec*`, (route) =>
    route.fulfill({ json: specPlusAtr() })
  )

  await openPriceTab(page)

  const on = await drawn(page)
  expect(on).toContain('ATR')
  expect(on).not.toContain(VWAP)
})

test("the reader's choice survives a chart rebuild rather than being re-seeded", async ({
  page,
}) => {
  // `reconcileToggles`. **Rebuild chart** re-fetches the spec with `?refresh=true` and writes the
  // result into the cache, so a spec that came back DIFFERENT gives `spec.indicators` a new
  // identity, `indicatorRoster` recomputes, and the effect that seeds `indicatorsOn` fires. A plain
  // re-seed there switches the reader's layer off under them, on a button whose whole promise is
  // that it rebuilds the DATA.
  //
  // ⚠ The rebuilt spec has to actually DIFFER, and that is the non-obvious part. TanStack applies
  // structural sharing, so a rebuild returning identical content hands back the OLD object and the
  // roster never recomputes — a version of this check that rebuilt an unchanged spec passed against
  // the very re-seed it was written to catch. Gaining a layer is also the realistic case: it is
  // exactly what a spec cached before the VWAP existed does when it is rebuilt.
  //
  // ⚠ An earlier version switched the display TIMEFRAME instead and was briefly deleted as
  // unreachable, on a `grep` that had silently skipped this app's largest page. See
  // `ChartPanel/CLAUDE.md`.
  await openStructureMenu(page)

  await page.getByRole('button', { name: new RegExp(VWAP) }).click()
  await expect.poll(() => drawn(page)).toContain(VWAP)
  await page.keyboard.press('Escape')

  // The rebuild comes back carrying one layer the reader has never seen.
  await page.route('**/chart-spec?*refresh=true*', (route) =>
    route.fulfill({ json: specPlusAtr() })
  )

  await page.getByRole('button', { name: /rebuild chart/i }).click()
  await expect.poll(() => drawn(page), { timeout: 30_000 }).toContain('ATR')

  // The layer the READER turned on is still on; only the genuinely new key took a default.
  expect(await drawn(page)).toContain(VWAP)
})
