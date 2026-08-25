/**
 * The Rebuild control on a price chart that has NOTHING to draw.
 *
 * 🔴 **The rule this pins: a recovery control must not live inside the thing that failed.** Rebuild
 * rode on the ChartPanel's tool strip, and that panel only mounts once there are candles — so the
 * one state where a reader needs it was the one state that hid it. Reported from the screen
 * 2026-08-25 over a charged re-run whose chart came back empty: *"there is no way to rebuild chart
 * or anything."*
 *
 * ⚠ **A fail-watch against HEAD is VACUOUS here** — the button in that state is new, so a red only
 * proves the locator. Non-vacuity is by MUTATION: dropping the button from the empty/error box
 * turns both of these red and nothing else.
 *
 * ⚠ Each check asserts the STATE first (the message) and the button second. An empty viewport and
 * a withheld button look identical otherwise — the trap `cost-switch.spec.ts` records.
 *
 * ⚠ Mocked, so it needs no bars and no MT5 terminal: an empty spec cannot be produced on demand.
 */
import { test, expect } from '@playwright/test'

const RUN_ID = 'chartempty01'

const RUN = {
  run_id: RUN_ID,
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
  cost_layers: ['bid_ask_fills', 'commission', 'swap'],
  broker_profile: 'vantage_demo',
  status: 'complete',
  error_message: null,
  created_at: '2026-08-25T10:00:00Z',
  started_at: '2026-08-25T10:00:00Z',
  completed_at: '2026-08-25T10:05:00Z',
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
  source_run_id: 'origin000001',
  runner: 'python',
  sizing_mode: 'consistent',
  sized: false,
  sized_timeline: [],
}

/** Serve the run, and answer its chart-spec request however the check needs. */
async function mock(
  page: import('@playwright/test').Page,
  spec: { json: unknown } | { status: number }
) {
  await page.route('**/api/**', async (route) => {
    const u = new URL(route.request().url())
    if (u.pathname.endsWith(`/backtests/runs/${RUN_ID}/chart-spec`)) {
      return 'json' in spec
        ? route.fulfill({ json: spec.json })
        : route.fulfill({ status: spec.status, json: { detail: 'boom' } })
    }
    if (u.pathname.endsWith(`/backtests/runs/${RUN_ID}`)) return route.fulfill({ json: RUN })
    return route.continue()
  })
}

async function openPriceTab(page: import('@playwright/test').Page) {
  await page.goto(`/backtests/runs/${RUN_ID}`)
  await page.getByRole('button', { name: 'Price', exact: true }).click()
}

test('a chart with no candles still offers Rebuild', async ({ page }) => {
  // MUTATION: delete the button from `box()` and this goes red on the missing control.
  await mock(page, {
    json: {
      instrument: 'XAUUSD',
      baseTimeframe: 'M15',
      runTimeframe: 'M15',
      historyStartMs: 1704067200000,
      brokerGmtOffsetHours: 0,
      candles: [],
      sessions: [],
      trades: [],
    },
  })
  await openPriceTab(page)

  // The STATE first — an empty viewport and a withheld button are otherwise indistinguishable.
  await expect(page.getByText('No price data available for this run.')).toBeVisible()
  await expect(page.getByRole('button', { name: 'Rebuild chart' })).toHaveCount(1)
})

test('a chart whose spec FAILED to load still offers Rebuild', async ({ page }) => {
  // The other half, and it is the one a reader hits after a backend fix: the spec 500s, and the
  // only way forward is to ask for it again.
  await mock(page, { status: 500 })
  await openPriceTab(page)

  await expect(page.getByText("Couldn't load chart data for this run.")).toBeVisible()
  await expect(page.getByRole('button', { name: 'Rebuild chart' })).toHaveCount(1)
})
