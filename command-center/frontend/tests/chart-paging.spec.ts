/**
 * The price chart's "go to date" jump reports its own progress.
 *
 * 🔴 The defect (reported by Aaron 2026-08-06): paging back years of history is a REAL minute of
 * wall clock — measured at 90s for a six-year jump on run 211384ddbea4 at M15 — and the only sign
 * of life was a static `loading 2020-02-03…`. A label that does not change for ninety seconds is
 * indistinguishable from a hang, which is how it was reported: *"there's no intuitive indicator
 * that something isn't broken."*
 *
 * ⚠ This drives the REAL backend rather than intercepting the candles route, and that is the
 * point: the thing under test is that the readout tracks pages actually landing, so a mocked feed
 * would be testing the mock's cadence. The jump is kept SHORT (about a year, ~2 pages) so the test
 * costs ~20s instead of the 90s a full-history jump does.
 */
import { test, expect } from '@playwright/test'

// The longest python run in the lab — 2020-01-01 → 2026-08-01 at M15, so the shipped window is
// ~17 months and anything before 2024 has to be paged in.
const RUN = '211384ddbea4'

async function openPriceTab(page: import('@playwright/test').Page) {
  await page.goto(`/backtests/runs/${RUN}`)
  await page.getByRole('button', { name: /price/i }).click()
  // The panel is warm-mounted and klinecharts lays 33k candles out on mount; the Go to date pill
  // only renders once the chart has a loaded range to bound itself to.
  await expect(page.getByTitle('Go to date')).toBeVisible({ timeout: 60_000 })
}

test('a jump that has to page history names the date it has REACHED, not just the target', async ({ page }) => {
  test.setTimeout(180_000)
  await openPriceTab(page)

  const pill = page.getByTitle('Go to date')
  await pill.click()
  // Far enough back to need at least two pages, near enough to keep the test short.
  await page.locator('input[type="date"]').fill('2023-06-01')
  await page.getByRole('button', { name: 'Go', exact: true }).click()

  // The reached date is the load-bearing half: a percentage alone still reads as a guess, and the
  // TARGET is what the pill already said for the whole ninety seconds before this landed.
  const reached = page.getByTestId('jump-reached')
  await expect(reached).toBeVisible({ timeout: 30_000 })
  const first = await reached.textContent()

  // …and it MOVES. A date that appears once and then sits there is the same defect one step on.
  await expect
    .poll(async () => (await reached.textContent()) ?? '', { timeout: 120_000, intervals: [500] })
    .not.toBe(first)

  // It walks BACKWARDS toward the target, which is what says the wait is progressing rather than
  // merely repainting.
  const later = (await reached.textContent()) ?? ''
  expect(later.localeCompare(first ?? '')).toBeLessThan(0)

  // And the jump ends: the busy readout goes away entirely.
  await expect(reached).toBeHidden({ timeout: 150_000 })
})

test('the progress bar fills rather than sitting at zero', async ({ page }) => {
  test.setTimeout(180_000)
  await openPriceTab(page)

  await page.getByTitle('Go to date').click()
  await page.locator('input[type="date"]').fill('2023-06-01')
  await page.getByRole('button', { name: 'Go', exact: true }).click()

  const bar = page.getByTestId('jump-bar')
  await expect(bar).toBeVisible({ timeout: 30_000 })

  // ⚠ Asserting "> 0%" would be VACUOUS — the bar carries a 3% floor so it is visible at the very
  // start, so a completely dead progress value would still pass. It has to actually grow.
  const widthOf = async () => parseFloat(((await bar.getAttribute('style')) ?? '').match(/width:\s*([\d.]+)%/)?.[1] ?? '0')
  const w0 = await widthOf()
  await expect.poll(widthOf, { timeout: 120_000, intervals: [500] }).toBeGreaterThan(w0)
})
