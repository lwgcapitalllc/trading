/**
 * "Rebuild chart" lives on the price chart's own TOOL STRIP, so it is reachable in both views.
 *
 * 🔴 It sat in the host's tab strip until 2026-08-08, and the price chart goes fullscreen by
 * `position: fixed` over the whole app — so expanding the chart, which is when a reader is looking
 * closely enough to notice the marks are stale, took the only way to rebuild them off screen.
 * Reported in those words: *"allow me to rebuild chart on full screenview also it only allows me to
 * do on minimized view"*, then placed beside the Chart settings cog on Aaron's call.
 *
 * ⚠ Every locator is scoped to the CHART PANEL's own root (`[data-applied-lo]`), and it has to be.
 * Anything the HOST renders is outside that root — and in fullscreen the host's chrome is still in
 * the DOM behind the overlay, merely covered, so a page-wide `getByRole` matches it and PASSES
 * against the broken page. That trap has been recorded four times in this folder (the sidebar logo
 * as `svg.first()`, the page header's own Retry, the risk card's own Deploy).
 *
 * ⚠ It also asserts there is exactly ONE on the page. The button was MOVED, not copied, and a
 * count of 1 is the only thing that says so — a check that merely found it inside the panel would
 * stay green if the tab strip's copy came back.
 */
import { expect, test } from '@playwright/test'
import { requireRun } from './fixtures'

const RUN = '997c14cc53bc'

// Fail by NAME if this pinned run has left the lab, instead of timing out on a chart
// that never rendered and sending the reader at the feature. See `fixtures.ts`.
test.beforeAll(async () => {
  await requireRun(
    RUN,
    'a python run with a rebuildable ChartSpec (NT8/MT5 runs have no Rebuild button)'
  )
})

test('Rebuild chart is on the chart itself, in both views, exactly once', async ({ page }) => {
  // A real rebuild re-fetches candles and replays every engine (~7.6s cold, measured). Serve the
  // CACHED spec instead: the click only has to prove it reaches the endpoint, and the panel still
  // gets a real payload back so nothing downstream is mocked into a shape the server never sends.
  let refreshes = 0
  await page.route(/\/chart-spec\?.*refresh=true/, async (route) => {
    refreshes += 1
    await route.continue({ url: route.request().url().replace(/\?.*$/, '') })
  })

  await page.goto(`/backtests/runs/${RUN}`)
  await page.getByRole('button', { name: /price/i }).click()
  await expect(page.getByTitle('Go to date')).toBeVisible({ timeout: 90_000 })

  const panel = page.locator('[data-applied-lo]').first()
  const inPanel = panel.getByRole('button', { name: /rebuild chart/i })
  const anywhere = page.getByRole('button', { name: /rebuild chart/i })

  await expect(inPanel).toBeVisible()
  await expect(anywhere).toHaveCount(1)

  await page.getByRole('button', { name: /expand/i }).click()
  await expect(page.getByTitle('Minimize (Esc)')).toBeVisible()

  await expect(inPanel).toBeVisible()
  await expect(anywhere).toHaveCount(1)

  await inPanel.click()
  await expect.poll(() => refreshes, { timeout: 30_000 }).toBeGreaterThan(0)
})
