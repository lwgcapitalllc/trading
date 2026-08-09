/**
 * "Reset chart view" (the price chart's right-click menu) must restore BOTH axes.
 *
 * 🔴 It restored only the time axis until 2026-08-08. `setBarSpace`, `setOffsetRightDistance` and
 * `scrollToRealTime` are all horizontal; dragging the PRICE axis switches klinecharts' y axis off
 * auto-scale and it keeps that range for ever, so the reset returned you to the right date on a
 * chart still showing a price window price had left. Reported off a screen sitting at 5,100–5,460
 * with the market at 4,252 — a chart that looks EMPTY, which reads as the reset breaking it.
 *
 * ⚠ This reads PIXELS, and it has to: the applied window is exposed as `data-applied-lo/-hi`, but
 * the y RANGE has no DOM presence at all — klinecharts draws its price axis into the canvas. A
 * check that settled for "the reset handler ran" would pass against the half-finished version.
 *
 * ⚠ The mouse is parked off the plot before every measurement. The crosshair paints into the same
 * canvases, so a signature taken with the pointer over the chart differs for a reason that has
 * nothing to do with the view.
 */
import { expect, test, type Page } from '@playwright/test'

// The longest python run in the lab — any run works here, this one is already the suite's fixture.
const RUN = '997c14cc53bc'

type Box = { x: number; y: number; width: number; height: number }

/** A cheap hash of the plot's pixels — "the chart draws the same thing" and nothing finer. */
async function sig(page: Page, clip: Box): Promise<number> {
  await page.mouse.move(5, 5)
  await page.waitForTimeout(350)
  const shot = await page.screenshot({ clip })
  let h = 0
  for (const b of shot) h = (h * 31 + b) | 0
  return h
}

test('Reset chart view restores the PRICE axis, not only the time axis', async ({ page }) => {
  await page.goto(`/backtests/runs/${RUN}`)
  await page.getByRole('button', { name: /price/i }).click()
  await expect(page.getByTitle('Go to date')).toBeVisible({ timeout: 90_000 })
  await page.waitForTimeout(1500)

  const root = page.locator('[data-applied-lo]').first()
  await root.scrollIntoViewIfNeeded()
  await page.waitForTimeout(600)
  const box = (await root.boundingBox())!

  // Strictly inside the plot: past the header, and clear of the price axis gutter on the right.
  const clip = { x: box.x + 20, y: box.y + 130, width: box.width - 100, height: 280 }
  const cx = box.x + box.width / 2
  const cy = box.y + box.height / 2

  const before = await sig(page, clip)

  // Drag the PRICE axis — this is what takes the y axis off auto-scale.
  const axisX = box.x + box.width - 25
  await page.mouse.move(axisX, cy)
  await page.mouse.down()
  await page.mouse.move(axisX, cy - 200, { steps: 20 })
  await page.mouse.up()
  await page.waitForTimeout(600)

  // ...and then pan vertically, which is only possible once it IS manual. This is the state that
  // was reported: price scrolled clean out of the visible band.
  await page.mouse.move(cx, cy)
  await page.mouse.down()
  await page.mouse.move(cx, cy - 250, { steps: 20 })
  await page.mouse.up()
  await page.waitForTimeout(600)

  const messedUp = await sig(page, clip)
  expect(messedUp, 'the y-axis drag + pan must actually change the chart').not.toBe(before)

  await root.click({ button: 'right', position: { x: box.width / 2, y: box.height / 3 } })
  await page.getByText('Reset chart view').click()
  await page.waitForTimeout(1200)

  expect(await sig(page, clip), 'reset must restore the opening view').toBe(before)
})
