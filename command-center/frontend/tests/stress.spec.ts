/**
 * The Stress Tests page — its regression suite, added with the 2026-08-05 audit.
 *
 * The frame: the `stress_tests` table held ONE row, written three days before the accuracy pass
 * that was meant to fix this feature. So none of this had ever been driven end to end, and the
 * shape every defect shares is the same one the Overview's suite exists for — **not one of them
 * showed an error.** A magnitude drawn as a loss, a null drawn as 0%, a dollar figure drawn under
 * a grade decided in percent: each renders a confident number.
 *
 * ⚠ Most of these states cannot be produced on demand — a compounding run graded on percent, a
 * walk-forward that crashed, a native path with no Sharpes, a shift whose child failed. They are
 * mocked by MUTATING THE REAL detail response, never by hand-writing a fixture, so the mock cannot
 * drift into a shape the server never sends.
 *
 * Needs the backend on :8000 and the dev server on :5173 (`./start.sh`).
 */
import { test, expect, type Page } from '@playwright/test'
import type { StressTestDetail, StressTest } from '../src/types'

const API = 'http://localhost:8000'

async function anyStressTest(): Promise<StressTest> {
  const res = await fetch(`${API}/stress-tests`)
  if (!res.ok) throw new Error(`backend not answering (${res.status}) — is it running?`)
  const rows: StressTest[] = await res.json()
  if (!rows.length) throw new Error('no stress tests in the lab to mutate')
  return rows[0]
}

async function liveDetail(id: string): Promise<StressTestDetail> {
  const res = await fetch(`${API}/stress-tests/${id}`)
  if (!res.ok) throw new Error(`detail ${id} → ${res.status}`)
  return res.json()
}

/** Serve a mutated copy of the REAL detail for one stress test, and open its page. */
async function openMutated(page: Page, mutate: (d: StressTestDetail) => void) {
  const row = await anyStressTest()
  const real = await liveDetail(row.stress_test_id)
  await page.route(`**/api/stress-tests/${row.stress_test_id}`, async (route) => {
    const copy: StressTestDetail = JSON.parse(JSON.stringify(real))
    mutate(copy)
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify(copy),
    })
  })
  await page.goto(`http://localhost:5173/stress-tests/${row.stress_test_id}`)
  await page.waitForLoadState('networkidle')
  return real
}

// ── The drawdown basis ────────────────────────────────────────────────────────

test('a compounding run shows its drawdown in PERCENT, the unit the grade read', async ({
  page,
}) => {
  // 🔴 The page read neither `dd_basis` nor the percent columns. It printed dollars against a
  // dollar limit and coloured them over/under, while the letter beside them had been decided on
  // percentages — so a red "over limit" could sit next to an A.
  await openMutated(page, (d) => {
    d.dd_basis = 'percent'
    d.pct1_max_dd = 43_444
    d.pct1_max_dd_pct = 62.1
    d.pct5_max_dd = 31_000
    d.pct5_max_dd_pct = 53.2
    d.median_max_dd = 24_675
    d.median_max_dd_pct = 31.0
    d.status = 'complete'
  })
  await expect(page.getByText('drawdown in %')).toBeVisible()
  // The percent value is on screen and the dollar one is NOT — showing both is what let a reader
  // compare a percent drawdown against a dollar limit.
  await expect(page.getByText('62.1%', { exact: true })).toBeVisible()
  await expect(page.getByText('$43,444', { exact: true })).toHaveCount(0)
})

test('a fixed-size run still shows dollars', async ({ page }) => {
  await openMutated(page, (d) => {
    d.dd_basis = 'dollars'
    d.pct1_max_dd_pct = null
    d.pct5_max_dd_pct = null
    d.median_max_dd_pct = null
    d.pct1_max_dd = 43_444
    d.status = 'complete'
  })
  await expect(page.getByText('drawdown in $')).toBeVisible()
  await expect(page.getByText('$43,444', { exact: true })).toBeVisible()
})

// ── Why this grade ────────────────────────────────────────────────────────────

test('the grade reasons are rendered — they were computed, stored, and shown nowhere', async ({
  page,
}) => {
  await openMutated(page, (d) => {
    d.status = 'complete'
    d.grade = null
    d.grade_reasons = [
      "Not graded — 'Unconstrained (No Limits)' has no drawdown limit, and every grade is a statement about drawdown vs a limit",
      'Set the drawdown percent you are willing to accept on a ruleset and re-run',
    ]
  })
  await expect(page.getByText('Why this test is not graded')).toBeVisible()
  await expect(page.getByText(/has no drawdown limit/)).toBeVisible()
  await expect(page.getByText(/Set the drawdown percent/)).toBeVisible()
})

test('a completed test with no letter says NOT GRADED, not nothing', async ({ page }) => {
  // It rendered a card with no letter and no explanation, which reads as a broken page.
  //
  // ⚠ `exact` is load-bearing and was added 2026-08-06. The subject here is the BADGE on the grade
  // card, and a bare `getByText('not graded')` is a substring match that also catches the reasons
  // panel's heading ("Why this test is not graded") and the reason line itself ("Not graded — …").
  // It passed while the lab held one row whose reasons were empty, and became a strict-mode
  // violation the moment a real ungraded row carried them — i.e. it was coupled to the DATA in the
  // lab, not to the rule. The reasons panel has its own test directly above.
  await openMutated(page, (d) => {
    d.status = 'complete'
    d.grade = null
  })
  await expect(page.getByText('not graded', { exact: true })).toBeVisible()
})

test('a phase that ran and FAILED says so', async ({ page }) => {
  // A crashed walk-forward left the summary NULL, which grading read as "not run" — explicitly
  // unpenalised — so the test could be handed an A with the caveat "walk-forward not run".
  await openMutated(page, (d) => {
    d.status = 'complete'
    d.phases_requested = ['monte_carlo', 'walk_forward']
    d.phase_failures = { walk_forward: 'every walk-forward backtest failed (10 of 10 periods)' }
  })
  await expect(page.getByText(/failed: every walk-forward backtest failed/)).toBeVisible()
})

// ── Null is not zero ──────────────────────────────────────────────────────────

test('a ruleset with no limit shows n/a, never 0%', async ({ page }) => {
  // `st.prob_pass_eval ?? 0` rendered "0%" — "this strategy never passes" about a measurement
  // never taken. The backend made both fields nullable for exactly this reason.
  await openMutated(page, (d) => {
    d.status = 'complete'
    d.prob_breach = null
    d.prob_pass_eval = null
    d.median_final_pnl = d.median_final_pnl ?? 1000
  })
  await expect(page.getByText('no limit to breach')).toBeVisible()
  // No probability card is claiming a number.
  await expect(page.getByText('Prob. Pass')).toHaveCount(0)
})

// ── Walk-forward ──────────────────────────────────────────────────────────────

test('the out-of-sample trade counts are on screen — the whole verdict turns on them', async ({
  page,
}) => {
  // `is_trades`/`oos_trades` were written by the engine and undeclared on the API model, so
  // Pydantic dropped them and the page could never show that every window closed 6 trades.
  await openMutated(page, (d) => {
    d.status = 'complete'
    d.walk_forward_summary = [1, 2, 3, 4, 5].map((w) => ({
      window: w,
      is_pnl: 100,
      oos_pnl: 50,
      is_sharpe: 1.5,
      oos_sharpe: 0.5,
      is_trades: 15,
      oos_trades: 6,
      is_pf: null,
      oos_pf: null,
    }))
    d.walk_forward_degradation = null
  })
  await page.getByRole('button', { name: 'Walk-Forward', exact: true }).click()
  await expect(page.getByText('Out-of-Sample Trades')).toBeVisible()
  await expect(page.getByText('5 of 5 windows too thin')).toBeVisible()
})

test('the native path reports PROFIT FACTOR, not a row of zero Sharpes', async ({ page }) => {
  // It has no trade-level data and writes `is_sharpe: null` deliberately; the chart did
  // `is_sharpe ?? 0` and drew five pairs of zero bars asserting "Sharpe 0.00 in and out".
  await openMutated(page, (d) => {
    d.status = 'complete'
    d.walk_forward_summary = [1, 2, 3].map((w) => ({
      window: w,
      is_pnl: 100,
      oos_pnl: 50,
      is_sharpe: null,
      oos_sharpe: null,
      is_trades: null,
      oos_trades: null,
      is_pf: 1.8,
      oos_pf: 1.2,
    }))
  })
  await page.getByRole('button', { name: 'Walk-Forward', exact: true }).click()
  await expect(page.getByText('profit factor').first()).toBeVisible()
  // The averages are the PF ones, so they are not dashes.
  await expect(page.getByText('1.80', { exact: true })).toBeVisible()
})

// ── Sensitivity ───────────────────────────────────────────────────────────────

test('a shift that IMPROVED the result is not drawn as a loss', async ({ page }) => {
  // `degradation` is a magnitude; the page drew `-degradation * 100`, inventing a direction, so an
  // improvement rendered as a long red bar and "Median Change" was negative by construction.
  await openMutated(page, (d) => {
    d.status = 'complete'
    d.sensitivity_summary = {
      aplus_window: {
        '+10%': {
          degradation: 0.31,
          pf_delta_pct: 31.0,
          profit_factor: 5.4,
          run_id: 'a',
          new_value: 4752,
        },
        '-10%': {
          degradation: 0.12,
          pf_delta_pct: -12.0,
          profit_factor: 3.6,
          run_id: 'b',
          new_value: 3888,
        },
      },
    }
    d.sensitivity_max_degradation = 0.31
  })
  await page.getByRole('button', { name: 'Sensitivity', exact: true }).click()
  // The most sensitive shift is the +31% one, and it is stated as a POSITIVE change.
  // ⚠ Scope to the chart's own tspan: the label also appears in the KPI card and in Recharts'
  // hidden measurement span, so a bare getByText is a strict-mode violation rather than a miss.
  await expect(page.locator('tspan', { hasText: 'aplus_window +10%' })).toBeVisible()
  await expect(page.getByText('+31% vs baseline')).toBeVisible()
  // And the losing shift is drawn on the other side of zero.
  await expect(page.locator('tspan', { hasText: 'aplus_window -10%' })).toBeVisible()
})

test('a shift whose backtest failed is not drawn as a flat zero bar', async ({ page }) => {
  // `: 0` rendered "tested, no effect" — the most reassuring answer available — for a measurement
  // that never happened.
  await openMutated(page, (d) => {
    d.status = 'complete'
    d.sensitivity_summary = {
      only_param: {
        '+10%': { degradation: null, pf_delta_pct: null, run_id: 'a', new_value: 11 },
        '-10%': {
          degradation: 0.2,
          pf_delta_pct: -20,
          profit_factor: 3.0,
          run_id: 'b',
          new_value: 9,
        },
      },
    }
    d.sensitivity_max_degradation = 0.2
  })
  await page.getByRole('button', { name: 'Sensitivity', exact: true }).click()
  // Only the MEASURED shift has a row on the chart. The failed one is dropped, not drawn at 0.
  await expect(page.locator('tspan', { hasText: 'only_param -10%' })).toBeVisible()
  await expect(page.locator('tspan', { hasText: 'only_param +10%' })).toHaveCount(0)
})

// ── The fan may not draw a reference it cannot support ───────────────────────

test('the equity fan carries no drawdown-limit line', async ({ page }) => {
  // It drew one at `y = -max_loss_eod` on a CUMULATIVE-P&L axis. A drawdown is peak-to-trough, so
  // a path can breach many times over without crossing a line below zero — a fan sitting entirely
  // above it read "no simulation breaches" while Prob. Breach said otherwise.
  // A ruleset limit has to EXIST for the old code to have drawn the line, so the mock states one.
  await openMutated(page, (d) => {
    d.status = 'complete'
    d.dd_basis = 'dollars'
    d.pct1_max_dd_pct = null
    d.pct5_max_dd_pct = null
    d.median_max_dd_pct = null
    d.ruleset_id = 'personal_forex_risk'
  })
  await expect(page.getByText('Equity Path Fan')).toBeVisible()
  // ⚠ Scoped to the FAN's own container, not `svg` — the sidebar logo is an svg too, so a
  // page-wide search passes vacuously and the test proves nothing.
  const fan = page
    .locator('div')
    .filter({ hasText: /^Equity Path Fan$/ })
    .locator('..')
  await expect(fan.locator('tspan', { hasText: 'Limit' })).toHaveCount(0)
  await expect(fan.getByText('Limit', { exact: true })).toHaveCount(0)
  // The histogram, which DOES measure drawdown, still carries its limit line.
  await expect(page.getByText('Max Drawdown Distribution')).toBeVisible()
})
