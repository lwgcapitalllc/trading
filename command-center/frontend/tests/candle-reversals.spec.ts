/**
 * The Candlestick Reversals layer on the backtest price chart — one candle repainted navy per
 * setup, the pattern candle at the turn.
 *
 * The layer's own SELECTION rules (which anchor gets a mark, which bar of the window it lands on,
 * the direction rule, the winner-vs-loser window) are the backend's and are pinned there by
 * `backend/tests/test_candle_overlays.py`, mutation-proven. What these three check is the half
 * that only exists in the browser:
 *
 *   1. the layer is OFFERED with its count and arrives switched OFF, like every analysis layer
 *      added since the fair value gaps;
 *   2. ticking it actually REPAINTS CANDLES — this one has to read the canvas, because the layer's
 *      whole output is pixels and a check that settled for "the menu row is ticked" would pass
 *      against a panel drawing nothing;
 *   3. it is WITHDRAWN off the base timeframe. A candlestick pattern is a property of ONE bar size
 *      — an M15 hammer is not an H1 hammer — so a resample has nothing honest to paint, and the
 *      row has to go with the drawing rather than sit there switched on over an empty chart;
 *   4. the pattern NAME is off by default and comes on from Chart settings. These tags carry no
 *      cross-overlay de-collision, unlike the batched `LABEL` template, so two marks a few bars
 *      apart write their names over the neighbouring candles — which is how it was reported.
 *
 * ⚠ It drives the REAL backend, because the marks come from a server-side engine replay over the
 * run's own candles and a mocked spec would be testing the mock.
 *
 * ⚠ A fail-watch against HEAD is vacuous — the layer did not exist, so every check would go red on
 * the element simply being absent, which proves the locator and nothing else. Check 2 is instead
 * non-vacuous BY CONSTRUCTION: it measures the same pixels with the layer off and on, so it can
 * only pass on a real change. Checks 1 and 3 were proven by MUTATION (see each one's comment).
 */
import { expect, test, type Page } from '@playwright/test'

// The longest python run in the lab: 2020-01-01 → 2026-08-06 at M15. Its anchor set is 159 trades
// + 35 three-of-three misses = 194, of which 153 carry a pattern at their turn — so the layer is
// exercised on a real set rather than a handful. (It was 518 anchors and 424 marks until blocked
// setups were dropped on 2026-08-08; see `services/chart_spec.reversal_anchors`.)
const RUN = '997c14cc53bc'

// A date this run has a mark on — 2026-07-30 06:00, an Inverted Hammer at the turn of a winning
// long. Needed because 153 marks over 6.5 years means the newest bars usually have none on screen,
// and a pixel check on an empty viewport reads exactly like a layer that does not draw.
const DATE_WITH_A_MARK = '2026-07-30'

const LAYER = 'Candlestick Reversals'

/** The navy body the backend emits (`_NAVY` = #2f5fe0 = rgb(47,95,224)), counted across every
 *  canvas. Read from PIXELS on purpose: the repaint has no DOM presence at all. */
async function navyPixels(page: Page) {
  return page.evaluate(() => {
    let n = 0
    for (const c of Array.from(document.querySelectorAll('canvas'))) {
      const g = c.getContext('2d')
      if (!g || !c.width || !c.height) continue
      const d = g.getImageData(0, 0, c.width, c.height).data
      for (let i = 0; i < d.length; i += 4) {
        // A tolerance, because the body is stroked with a lighter edge and antialiased against it.
        if (Math.abs(d[i] - 47) < 14 && Math.abs(d[i + 1] - 95) < 14 && Math.abs(d[i + 2] - 224) < 14) n++
      }
    }
    return n
  })
}

async function openPriceTab(page: Page) {
  await page.goto(`/backtests/runs/${RUN}`)
  await page.getByRole('button', { name: /price/i }).click()
  // The panel is warm-mounted and klinecharts lays the applied window out on mount; the Go to date
  // pill only renders once the chart has a loaded range to bound itself to.
  await expect(page.getByTitle('Go to date')).toBeVisible({ timeout: 90_000 })
}

/** The lighter EDGE colour (`_NAVY_EDGE` = #7ea2ff), which the pattern TAG is drawn in and the navy
 *  body is not — so this is what separates "the mark is drawn" from "the mark is drawn AND named". */
async function edgePixels(page: Page) {
  return page.evaluate(() => {
    let n = 0
    for (const c of Array.from(document.querySelectorAll('canvas'))) {
      const g = c.getContext('2d')
      if (!g || !c.width || !c.height) continue
      const d = g.getImageData(0, 0, c.width, c.height).data
      for (let i = 0; i < d.length; i += 4) {
        if (Math.abs(d[i] - 126) < 20 && Math.abs(d[i + 1] - 162) < 20 && Math.abs(d[i + 2] - 255) < 20) n++
      }
    }
    return n
  })
}

async function toggleAnalysis(page: Page) {
  await page.getByRole('button', { name: /^Analysis/ }).click()
}

/** ⚠ The gear is a TOGGLE, not an open button — a second click closes the panel. Closing it via a
 *  `.getByRole('button').last()` inside the panel picks up the fib editor's own delete buttons. */
async function toggleSettings(page: Page) {
  await page.getByTitle(/Chart settings/).click()
}

async function goToDate(page: Page, iso: string) {
  await page.getByTitle('Go to date').click()
  const input = page.locator('input[type="date"]')
  await input.fill(iso)
  await input.press('Enter')
}

test('the layer is offered with its count and starts switched OFF', async ({ page }) => {
  // Proven by MUTATION: defaulting the group ON (dropping it from `isAnalysisGroup`'s reach in
  // `groupDefault`) turns the second assertion red.
  await openPriceTab(page)
  expect(await navyPixels(page)).toBe(0)

  await toggleAnalysis(page)
  const row = page.getByRole('button', { name: new RegExp(LAYER) })
  await expect(row).toBeVisible()
  // The count is what makes a layer legible before you switch it on — 424 marks and 4 read very
  // differently. It is the anchor set's answer, so it must be a real number, never blank.
  await expect(row).toContainText(/\d/)
})

test('ticking it repaints candles, and unticking it puts them back', async ({ page }) => {
  await openPriceTab(page)
  // ⚠ Go somewhere a mark EXISTS before measuring. This check used to read the opening viewport,
  // which worked only while blocked setups were anchors and the run carried 424 marks; at 153 the
  // newest bars have none, and an empty viewport is pixel-identical to a layer that never draws.
  await goToDate(page, DATE_WITH_A_MARK)
  const off = await navyPixels(page)
  expect(off).toBe(0)

  await toggleAnalysis(page)
  await page.getByRole('button', { name: new RegExp(LAYER) }).click()
  await toggleAnalysis(page)          // close the menu so it cannot be counted as chart pixels
  await expect.poll(() => navyPixels(page), { timeout: 20_000 }).toBeGreaterThan(0)

  // And back — a layer that cannot be switched off is not a toggle. This also rules out the navy
  // having come from anywhere but this layer.
  await toggleAnalysis(page)
  await page.getByRole('button', { name: new RegExp(LAYER) }).click()
  await toggleAnalysis(page)
  await expect.poll(() => navyPixels(page), { timeout: 20_000 }).toBe(0)
})

test('the layer is withdrawn off the timeframe it was computed on', async ({ page }) => {
  // Proven by MUTATION: dropping the `atBaseTf` clause from `analysisGroups` leaves the row listed
  // at H1, and dropping the matching `continue` in the render loop leaves it PAINTING M15 bars over
  // H1 candles — which is the more dangerous half, because it states something nobody measured.
  await openPriceTab(page)
  await goToDate(page, DATE_WITH_A_MARK)   // see the note in the check above
  await toggleAnalysis(page)
  await page.getByRole('button', { name: new RegExp(LAYER) }).click()
  await toggleAnalysis(page)
  await expect.poll(() => navyPixels(page), { timeout: 20_000 }).toBeGreaterThan(0)

  // Resample up. M15 → H1 is display-only, so the bars on screen are no longer the ones the
  // patterns were detected on.
  await page.getByRole('button', { name: /^M15$/ }).click()
  await page.getByText('H1', { exact: true }).click()

  await expect.poll(() => navyPixels(page), { timeout: 20_000 }).toBe(0)
  await toggleAnalysis(page)
  await expect(page.getByRole('button', { name: new RegExp(LAYER) })).toHaveCount(0)
})

test('the pattern name is off by default and comes on from Chart settings', async ({ page }) => {
  // Proven by MUTATION: defaulting `candleMarkLabels` to true, or dropping the setting from the
  // tag expression in the `candle` render branch, each turn one half of this red.
  //
  // ⚠ It counts the EDGE colour, not the navy body — the body is drawn either way, so a check on
  // `navyPixels` would be satisfied by a mark with no tag and would prove nothing about the toggle.
  await openPriceTab(page)
  await toggleAnalysis(page)
  await page.getByRole('button', { name: new RegExp(LAYER) }).click()
  await toggleAnalysis(page)
  // 153 marks over 6.5 years, so the newest bars carry none — go where one is.
  await goToDate(page, DATE_WITH_A_MARK)
  await expect.poll(() => navyPixels(page), { timeout: 30_000 }).toBeGreaterThan(0)

  const off = await edgePixels(page)

  await toggleSettings(page)
  const nameIt = page.getByText('Name the pattern').locator('xpath=../..').getByRole('switch')
  await expect(nameIt).toHaveAttribute('aria-checked', 'false')
  await nameIt.click()
  await toggleSettings(page)
  // The tag is many pixels of text beside a mark that was already drawn, so this is a large jump,
  // not a marginal one — measured 52 → 423 on this date.
  await expect.poll(() => edgePixels(page), { timeout: 20_000 }).toBeGreaterThan(off * 2)

  // And back — a preference that cannot be switched off is not a preference.
  await toggleSettings(page)
  await nameIt.click()
  await toggleSettings(page)
  await expect.poll(() => edgePixels(page), { timeout: 20_000 }).toBe(off)
})
