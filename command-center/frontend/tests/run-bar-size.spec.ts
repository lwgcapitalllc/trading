/**
 * The Run form starts on the frame a strategy was MEASURED on, and can offer 1 minute.
 *
 * 🔴 Run 2db0e08a8ccc (2026-09-22): FFT runs on 1-minute bars only, and this form's list for a
 * python strategy was 5m and up. Every FFT run went out on 5m or coarser and came back
 * "complete, 0 trades" — its 1m-against-5m rule compared one series with itself. The backend now
 * refuses that frame; this pins the form half, so the right frame is the one a reader gets.
 *
 * Reads the real strategies list (FFT states 1m, SOS Fade 15m) and never presses Run.
 */
import { test, expect, type Page } from '@playwright/test'
import { refuseLiveWrites } from './fixtures'

async function openRunModal(page: Page, name: string) {
  await refuseLiveWrites(page)
  await page.route('**/api/backtests/history-limit*', (r) => r.fulfill({ json: null }))
  await page.goto('/strategies')
  const row = page.locator('tbody tr').filter({ hasText: name }).first()
  await row.getByRole('button', { name: /^Run$/ }).click()
  await expect(page.getByText('Run Backtest', { exact: true }).first()).toBeVisible()
  return page
    .locator('label', { hasText: /^Bar size$/ })
    .locator('xpath=../..')
    .locator('select')
}

test('FFT opens on 1-minute bars, marked as the frame it was measured on', async ({ page }) => {
  // MUTATION: drop `measuredBar ??` from the barValue default — it opens on 15m and goes red.
  // MUTATION: take 1 back out of the python presets — the option is only there because it is
  // the measured frame, so the label check still passes but the next test goes red.
  const bar = await openRunModal(page, 'FFT')
  await expect(bar).toHaveValue('1')
  await expect(bar.locator('option:checked')).toHaveText('1m · measured')
})

test('a 15m strategy still opens on 15m, and can be moved to 1m', async ({ page }) => {
  // The control, and the list: 1m is offered to every python strategy, not only to FFT.
  const bar = await openRunModal(page, 'SOS Fade')
  await expect(bar).toHaveValue('15')
  await bar.selectOption('1')
  await expect(bar).toHaveValue('1')
})
