/**
 * The Fibs layer on a B-LEG run's price chart.
 *
 * The B-LEG bot is the more fib-native of the two — it rests its limit on the 0.5 of the frozen
 * SOS leg, stops at that leg's 1.0 and takes TP1 at its 0.0 — and until 2026-08-11 it recorded no
 * ladder at all, because it overrides `_place_entries` and the recording hung off the parent's.
 * So the Fibs row was ABSENT on every B-LEG run while the layer worked fine on A+ runs, which
 * reads as the feature being broken rather than as a bot that never filled the field.
 *
 * The ladder's ARITHMETIC is the strategy's and is pinned there by
 * `strategies/python/mpc_bleg/tests/test_bleg_fib.py`, mutation-proven — including the load-bearing
 * one, that the band's far edge records as 0.618 (measured from the leg extreme, the drawing
 * convention) and not as the 0.382 the bot's own code calls it (measured from the leg origin).
 * What these two check is the half that only exists in the browser.
 *
 * ⚠ Drives the REAL backend: the ladder is written into the run's equity curve at REPLAY time, so
 * a mocked spec would be testing the mock, and — unlike most layers — no chart rebuild can supply
 * it. A run made before this change needs re-running, not "Reload charts".
 *
 * ⚠ A fail-watch against HEAD is genuinely meaningful here, unlike a brand-new layer: the Fibs row
 * and its template both already existed and worked on A+ runs, and were absent on this run only
 * because `tradeFibCount` was 0. Check 1 was WATCHED RED against HEAD for that reason. Check 2 is
 * non-vacuous by construction — it measures the same pixels with the layer off and on.
 */
import { expect, test, type Page } from '@playwright/test'
import { requireRun } from './fixtures'

// A full-history B-LEG run: XAUUSD M15, 2020-01-01 → 2026-08-03, 99 trades. Every one of the 99
// carries a ladder, because a B leg cannot be priced without one — which is what makes the count
// assertion below a real number rather than "some".
const RUN = '45795fcedf8c'

// Fail by NAME if this pinned run has left the lab, instead of timing out on a chart
// that never rendered and sending the reader at the feature. See `fixtures.ts`.
test.beforeAll(async () => {
  await requireRun(RUN, 'an mpc_bleg run whose trades carry a recorded fib leg')
})
const EXPECTED_FIBS = 99

/** Total pixels drawn in the three factory fib colours the ladder uses — green (0.382/0.5), blue
 *  (0.618/0.702/0.786) and red (0.886). Read from PIXELS because the ladder is canvas output with
 *  no DOM presence, so a check that settled for "the menu row is ticked" would pass against a
 *  panel drawing nothing. */
async function fibPixels(page: Page) {
  return page.evaluate(() => {
    const WANT = [
      [34, 197, 94],
      [41, 98, 255],
      [239, 83, 80],
    ]
    let n = 0
    for (const c of Array.from(document.querySelectorAll('canvas'))) {
      const g = c.getContext('2d')
      if (!g || !c.width || !c.height) continue
      const d = g.getImageData(0, 0, c.width, c.height).data
      for (let i = 0; i < d.length; i += 4) {
        for (const [r, gr, b] of WANT) {
          if (
            Math.abs(d[i] - r) < 12 &&
            Math.abs(d[i + 1] - gr) < 12 &&
            Math.abs(d[i + 2] - b) < 12
          ) {
            n++
            break
          }
        }
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

async function toggleAnalysis(page: Page) {
  await page.getByRole('button', { name: /^Analysis/ }).click()
}

async function goToDate(page: Page, iso: string) {
  await page.getByTitle('Go to date').click()
  const input = page.locator('input[type="date"]')
  await input.fill(iso)
  await input.press('Enter')
}

// ⚠ The opening viewport is the newest bars and this bot takes ~2 trades a month, so it usually
// holds no trade at all — and a pixel check on a viewport with nothing in it reads exactly like a
// layer that does not draw. T99 entered 2026-07-20 11:30 and its leg starts the same day, so this
// date puts both the ladder and its trade on screen. Same trap the Candlestick Reversals spec
// records; it cost that suite a check that passed for the wrong reason.
const DATE_WITH_A_TRADE = '2026-07-20'

test('a B-LEG run offers Fibs, with a count, switched OFF', async ({ page }) => {
  // WATCHED RED against HEAD: before the bot recorded a ladder, `tradeFibCount` was 0 on this run
  // and the row was not rendered at all, so `toBeVisible` failed.
  await openPriceTab(page)
  await toggleAnalysis(page)

  const row = page.getByRole('button', { name: /Fibs/ })
  await expect(row).toBeVisible()
  // The count is what makes the layer legible before you switch it on, and it must be the real
  // number — a B leg without a ladder is not a B leg, so anything under 99 means trades are
  // silently recording nothing.
  await expect(row).toContainText(String(EXPECTED_FIBS))
})

test('ticking Fibs draws the ladder, unticking puts it back', async ({ page }) => {
  await openPriceTab(page)
  await goToDate(page, DATE_WITH_A_TRADE)
  const before = await fibPixels(page)

  await toggleAnalysis(page)
  await page.getByRole('button', { name: /Fibs/ }).click()
  await expect.poll(() => fibPixels(page), { timeout: 30_000 }).toBeGreaterThan(before)

  await page.getByRole('button', { name: /Fibs/ }).click()
  await expect.poll(() => fibPixels(page), { timeout: 30_000 }).toBe(before)
})
