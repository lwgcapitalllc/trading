/**
 * A STACK's price chart carries "Rebuild chart" too, and clicking it refreshes the STACK spec.
 *
 * 🔴 It did not until 2026-08-10. `PriceChartView` has taken `onRebuild` since the button moved
 * onto the tool strip, and `StackDetail` passed nothing — the comment beside the prop even said a
 * stack "has no single run to rebuild", which is true and is not a reason to have no control: a
 * stack's chart is built from its legs' cached specs, so it goes stale for exactly the reasons a
 * run's does, and every candlestick-layer fix this week has ended "existing runs need Rebuild
 * chart". Aaron: *"the rebuild chart button is missing on stacks still"*.
 *
 * ⚠ Locators are scoped to the CHART PANEL's own root (`[data-applied-lo]`), for the reason
 * `chart-rebuild-fullscreen.spec.ts` records at length: anything the host renders is outside that
 * root, and a page-wide `getByRole` would match it and pass against the broken page.
 *
 * ⚠ It asserts a page-wide count of exactly ONE. The stack page has its own header actions, and a
 * count is the only assertion that says the control lives on the chart rather than being
 * duplicated beside it.
 *
 * ⚠ Non-vacuity by MUTATION rather than by a fail-watch note: removing the `onRebuild` /
 * `rebuilding` props from `StackDetail`'s `PriceChartView` turns this red on the first assertion.
 *
 * ⚠ It drives the REAL lab and names a stack id, the same coupling `chart-rebuild-fullscreen`
 * has. A merged stack spec is built by replaying every leg's engines server-side, so a mocked one
 * would be testing the mock. If this goes red, check the stack still exists before touching it.
 */
import { expect, test } from '@playwright/test'

const STACK = 'st_94aeb25f0c'

test('a stack price chart can rebuild itself', async ({ page }) => {
  const errors: string[] = []
  page.on('console', m => { if (m.type() === 'error') errors.push(m.text()) })

  // A real rebuild re-runs every leg's own spec build — two full-history replays, ~55s measured.
  // Serve the CACHED merge instead: the click only has to prove it reaches the endpoint with
  // refresh=true, and the panel still gets a real payload so nothing downstream is mocked.
  let refreshes = 0
  await page.route(/\/stacks\/[^/]+\/chart-spec\?.*refresh=true/, async route => {
    refreshes += 1
    await route.continue({ url: route.request().url().replace(/\?.*$/, '') })
  })

  await page.goto(`/backtests/stacks/${STACK}`)
  await page.getByRole('button', { name: /^price$/i }).click()
  await expect(page.getByTitle('Go to date')).toBeVisible({ timeout: 180_000 })

  const panel = page.locator('[data-applied-lo]').first()
  const inPanel = panel.getByRole('button', { name: /rebuild chart/i })
  await expect(inPanel).toBeVisible()
  await expect(page.getByRole('button', { name: /rebuild chart/i })).toHaveCount(1)

  await inPanel.click()
  await expect.poll(() => refreshes, { timeout: 60_000 }).toBeGreaterThan(0)

  expect(errors).toEqual([])
})
