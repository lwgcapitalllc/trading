/**
 * The chart's own bar size must always be in the timeframe list.
 *
 * 🔴 It was missing for a 1-minute run until 2026-10-03. The list starts at M5, so an M1 run opened
 * on M1 with no M1 row: one click to M5 and there was no way back. Reported off run fa6d52fb5faa.
 *
 * ⚠ The recorded run ships M15 bars; the spec is relabelled M1 on the way in. The list is built from
 * the label alone, so that is the case under test — the candles themselves do not matter here.
 *
 * ✅ Watched RED with the fix reverted (no M1 row after picking M5).
 */
import { expect } from '@playwright/test'
import { offlineTest } from './offline'

const { test, recorded, recordedRun } = offlineTest('chart-sos-fade')
const RUN = recordedRun()

test('a 1-minute run can switch away from M1 and back', async ({ page }) => {
  const spec = recorded<Record<string, unknown>>(`/backtests/runs/${RUN}/chart-spec`)
  await page.route(`**/api/backtests/runs/${RUN}/chart-spec`, (route) =>
    route.fulfill({ json: { ...spec, baseTimeframe: 'M1', runTimeframe: 'M1' } })
  )
  await page.goto(`/backtests/runs/${RUN}`)
  await page.getByRole('button', { name: /price/i }).click()
  await expect(page.getByTitle('Go to date')).toBeVisible({ timeout: 90_000 })

  const tfButton = page.locator('[data-applied-lo]').first().getByRole('button', { name: /^M1$/ })
  await expect(tfButton).toBeVisible()

  await tfButton.click()
  await page.getByRole('button', { name: 'M5', exact: true }).click()
  const m5Button = page.locator('[data-applied-lo]').first().getByRole('button', { name: /^M5$/ })
  await expect(m5Button).toBeVisible()

  await m5Button.click()
  await page.getByRole('button', { name: 'M1', exact: true }).click()
  await expect(tfButton).toBeVisible()
})
