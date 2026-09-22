/**
 * Stress Test greys out while its platform is busy, and says which platform.
 *
 * 🔴 2026-09-22: a Python stack held the Python slot and Stress Test on a Python run stayed
 * pressable; its one outcome was "409 An NT8 job is already running" (the name fixed in the
 * backend the same day). Rerun and Optimize already greyed out on the same flag.
 *
 * Reads the real run 038101714bd9 (FFT, python) and answers only the busy flag. Never starts a test.
 */
import { test, expect, type Page } from '@playwright/test'
import { refuseLiveWrites } from './fixtures'

const RUN = '038101714bd9'

async function openWith(page: Page, pythonRunning: boolean) {
  await refuseLiveWrites(page)
  const idle = { running: false }
  await page.route('**/api/backtests/running-job', (r) =>
    r.fulfill({
      json: {
        nt8: idle,
        mt5: idle,
        python: pythonRunning ? { running: true, job_type: 'stack', job_id: 'stk_busy' } : idle,
      },
    })
  )
  await page.route('**/api/stress-tests/running-lock', (r) =>
    r.fulfill({ json: { forex: false, futures: false } })
  )
  await page.goto(`/backtests/runs/${RUN}`)
  return page.getByRole('button', { name: /^Stress Test/ })
}

test('a busy Python slot greys Stress Test and names Python', async ({ page }) => {
  // MUTATION: drop `|| !!stressBusy` from the button's `disabled` and this goes red.
  const button = await openWith(page, true)
  await expect(button).toBeDisabled()
  await expect(button).toHaveAttribute('title', /^A Python job is already running/)
})

test('a free platform leaves Stress Test pressable', async ({ page }) => {
  // The control: the flag must be what greys it, not something else on this run.
  const button = await openWith(page, false)
  await expect(button).toBeEnabled()
})
