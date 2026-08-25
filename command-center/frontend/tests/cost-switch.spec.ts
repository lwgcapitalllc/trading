/**
 * The cost switch on a finished run — the paired re-run that replaced the dead re-price control.
 *
 * **The rule these pin.** Re-pricing is strictly ADDITIVE: the server can only charge a layer the
 * run did not. Since the charged default (2026-08-24) an ordinary run already carries every
 * re-priceable layer, so the pill's only possible outcome is "no change" — and a control that can
 * never change anything is indistinguishable from a broken one. The page offers the free twin
 * instead, which is the only honest answer anyway: charged fills change WHICH setups exist
 * (measured 161 trades → 159), and no arithmetic over a stored trade list can invent a trade the
 * list does not contain.
 *
 * ⚠ **A fail-watch against HEAD is VACUOUS for all of these** — none of this existed, so a red
 * only proves the locator. **Non-vacuity is by MUTATION, named per check** — four run, each
 * turning its own named check red and leaving the others green.
 *
 * 🔴 **TWO of these were VACUOUS on the first pass and the mutations are the only reason it was
 * found.** (1) The no-twin check used `runner: 'mt5'` AND `cost_layers: null`, so the runner clause
 * alone withheld the button and a mutation deleting the null clause left it green — **two guards in
 * one assertion pin neither**; they are now one fixture each. (2) Both no-twin checks then passed
 * against a mutation that deleted the guard outright, because the Performance header had not
 * rendered and **an absent header is indistinguishable from a withheld button** — the same trap
 * this folder records for an empty chart viewport. Each asserts the header is visible FIRST.
 *
 * ⚠ **Everything is mocked, so this needs NO backend and no MT5 terminal** — the states it covers
 * (a fully charged run, an unpriced broker) cannot be produced on demand, and the real run route
 * pulls bars through the VPS tunnel. The `calendar.spec.ts` shape.
 */
import { test, expect } from '@playwright/test'
import type { BacktestDetail } from '../src/types'

/** A python run detail, charged or free. Hand-shaped is acceptable ONLY because every field here
 *  is one the page reads directly; anything derived comes from the same payload. */
function runDetail(over: Partial<BacktestDetail>): BacktestDetail {
  return {
    run_id: 'costswitch01',
    strategy_id: 's1',
    strategy_name: 'Test Strategy',
    instrument: 'XAUUSD',
    params: {},
    bar_type: 'Minute',
    bar_value: 15,
    start_date: '2024-01-01',
    end_date: '2024-06-30',
    commission_per_side: 1,
    slippage_ticks: 0,
    cost_layers: [],
    broker_profile: 'vantage_demo',
    status: 'complete',
    error_message: null,
    created_at: '2026-08-24T10:00:00Z',
    started_at: '2026-08-24T10:00:00Z',
    completed_at: '2026-08-24T10:05:00Z',
    net_pnl: 5000,
    max_drawdown: -500,
    profit_factor: 2,
    win_rate: 0.6,
    win_count: 6,
    trade_count: 10,
    sharpe: 1.2,
    platform_sharpe: null,
    sharpe_low_sample: false,
    profit_concentration_pct: null,
    max_drawdown_pct: 10,
    scratch_count: null,
    trade_concentration_pct: null,
    sortino: null,
    cagr: null,
    avg_win: 100,
    avg_loss: -50,
    avg_trade_duration_min: 60,
    worst_day_pnl: null,
    worst_losing_streak: null,
    equity_curve: Array.from({ length: 10 }, (_, i) => ({
      index: i + 1,
      equity: 10_000 + (i + 1) * 500,
      profit: 500,
      date: `2024-0${(i % 6) + 1}-01`,
    })),
    daily_pnl: [],
    regime_timeline: [],
    regime_breakdown: [],
    evaluations: [],
    worthiness: null,
    sweep_id: null,
    optimization_id: null,
    source_run_id: null,
    runner: 'python',
    sizing_mode: 'consistent',
    sized: false,
    sized_timeline: [],
    ...over,
  } as BacktestDetail
}

/** Serve one run detail plus the re-price report the page asks for straight after. */
async function mock(page: import('@playwright/test').Page, run: BacktestDetail, already: string[]) {
  await page.route('**/api/**', async (route) => {
    const u = new URL(route.request().url())
    if (u.pathname.endsWith(`/backtests/runs/${run.run_id}/repriced`)) {
      return route.fulfill({
        json: {
          layers: [],
          broker_profile: run.broker_profile,
          is_exact: true,
          derived_basis: false,
          approximate_layers: [],
          needs_rerun: [],
          already_charged: already,
          initial_capital: 10_000,
          final_equity: 15_000,
          sum_r: 10,
          total_cost_usd: 0,
          total_cost_r: 0,
          layer_cost_r: { spread: 0, commission: 0, swap: 0 },
          trades: [],
        },
      })
    }
    if (u.pathname.endsWith(`/backtests/runs/${run.run_id}`)) return route.fulfill({ json: run })
    return route.continue()
  })
}

test('a CHARGED run offers the free twin and hides the re-price control', async ({ page }) => {
  // MUTATION: drop `!costs.spent` from the pill's render guard and the pill comes back over a run
  // where every row is locked at zero — the dead control this replaced.
  const run = runDetail({ cost_layers: ['bid_ask_fills', 'commission', 'swap'] })
  await mock(page, run, ['spread', 'commission', 'swap'])
  await page.goto(`/backtests/runs/${run.run_id}`)

  const pair = page.getByTestId('cost-pair-button')
  await expect(pair).toHaveText(/Run this free/)
  // The re-price pill must be GONE, not merely disabled — it can only ever add nothing here.
  await expect(page.getByRole('button', { name: /Charging/ })).toHaveCount(0)
})

test('a FREE run offers the charged twin and keeps the re-price control', async ({ page }) => {
  // The guard on the other side, and it is the load-bearing half: on a free run there really ARE
  // layers left to price, so hiding the pill everywhere would remove a working control.
  // MUTATION: hard-wire `spent` to true and this check goes red on the missing pill.
  const run = runDetail({ cost_layers: [] })
  await mock(page, run, [])
  await page.goto(`/backtests/runs/${run.run_id}`)

  await expect(page.getByTestId('cost-pair-button')).toHaveText(/Run this charged/)
  await expect(page.getByRole('button', { name: /Charging/ })).toHaveCount(1)
})

test('a PYTHON run with NO layer contract is offered no twin at all', async ({ page }) => {
  // `null` means the run predates layered costs — which is NOT `[]`, and is not a claim about what
  // it charged that a twin could be built on. Offering one would state a basis nobody measured.
  //
  // 🔴 **The runner is `python` DELIBERATELY, and the first version of this check used `mt5` and
  // was VACUOUS.** With `mt5` the runner clause alone withholds the button, so the null clause is
  // never reached and a mutation collapsing `== null` into `!length` left this green. The two
  // clauses have to be separated to pin either one.
  // MUTATION: relax `run.cost_layers == null` to `!run.cost_layers?.length` — a null then reads as
  // "free" and the page offers a charged twin of a run whose costs are unknown. Watched red.
  const run = runDetail({ cost_layers: null, runner: 'python' })
  await mock(page, run, [])
  await page.goto(`/backtests/runs/${run.run_id}`)
  // 🔴 POSITIVE CONTROL FIRST, and it is the whole reason this check is worth anything. Without
  // it the assertion below passed against a mutation that DELETED the guard — because the header
  // had not rendered yet, and an absent header is indistinguishable from a withheld button. Same
  // trap this repo already records for an empty chart viewport.
  await expect(page.getByTestId('perf-collapse-toggle')).toBeVisible()
  await expect(page.getByTestId('cost-pair-button')).toHaveCount(0)
})

test('a non-python run is offered no twin whatever its layers say', async ({ page }) => {
  // The other clause, pinned on its own for the same reason. NT8 and MT5 drive their own tester
  // and have no cost switch to flip.
  // MUTATION: drop the `run.runner !== 'python'` clause and this goes red.
  const run = runDetail({ cost_layers: ['commission'], runner: 'mt5' })
  await mock(page, run, [])
  await page.goto(`/backtests/runs/${run.run_id}`)
  await expect(page.getByTestId('perf-collapse-toggle')).toBeVisible() // positive control — see above
  await expect(page.getByTestId('cost-pair-button')).toHaveCount(0)
})
