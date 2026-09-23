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
import { getJson, refuseLiveWrites } from './fixtures'

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
  const button = page.getByRole('button', { name: /^Stress Test/ })
  // ⚠ Wait for it to EXIST first. A stack replaying in the same backend slows every page, and a
  // 5s "enabled?" on a button not rendered yet is a failure about load, not about this rule.
  await expect(button).toBeVisible({ timeout: 60_000 })
  return button
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

// ── The stack page ────────────────────────────────────────────────────────────
//
// A stack is all python legs, so its Stress Test waits on the Python slot. Any finished SHARED
// stack will do; whether it is gradable is answered here, so only the busy flag is the subject.
async function openStackWith(page: Page, pythonRunning: boolean) {
  const stacks =
    await getJson<{ stack_id: string; mode: string; status: string }[]>('/backtests/stacks')
  const stack = stacks.find((s) => s.mode === 'shared' && s.status === 'complete')
  if (!stack) throw new Error('NO FIXTURE: the lab holds no finished shared stack')
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
  await page.route('**/api/stress-tests/gradable*', (r) =>
    r.fulfill({ json: { gradable: true, reason: null, trade_count: 400 } })
  )
  await page.goto(`/backtests/stacks/${stack.stack_id}`)
  const button = page.getByTestId('stack-stress-test')
  await expect(button).toBeVisible({ timeout: 60_000 }) // see `openWith`
  return button
}

test("a busy Python slot greys a STACK's Stress Test and names Python", async ({ page }) => {
  // MUTATION: drop `|| !!stressBusy` from the stack page's `stressOff` and this goes red.
  const button = await openStackWith(page, true)
  await expect(button).toBeDisabled()
  await expect(button).toHaveAttribute('title', /^A Python job is already running/)
})

test("a free platform leaves a gradable stack's Stress Test pressable", async ({ page }) => {
  const button = await openStackWith(page, false)
  await expect(button).toBeEnabled()
})
