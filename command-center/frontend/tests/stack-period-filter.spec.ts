/**
 * The PERIOD window on a stack — the control that did not exist here until 2026-09-03.
 *
 * Aaron: *"one thing that is missing is the date filter feature I have on standalone backtest
 * doesn't exist on stacked backtest."* The single-backtest page has had it since 2026-08-16 and
 * `period-filter.spec.ts` covers it there; this file covers the stack.
 *
 * 🔴 THE POINT IS NOT THAT A CHIP APPEARS. It is that every figure BELOW the chip follows it. A
 * stack composes its portfolio line, its KPIs and its per-leg rows client-side from each leg's
 * book, so a window applied to one and not the others produces a filtered headline sitting over
 * unfiltered rows — which reads as correct and is the defect this control could most easily
 * introduce. The per-leg assertions here are the ones that matter.
 *
 * ⚠ Every response is INTERCEPTED, so this needs only the dev server — no backend, no VPS, and no
 * dependence on which stacks are in the lab today.
 *
 * ⚠ A fail-watch against HEAD is VACUOUS — the control did not exist, so every check would go red
 * on a missing element, proving the locator and nothing else. Non-vacuity is by MUTATION, and the
 * map below was RUN rather than reasoned:
 *
 *   per-leg TRADE COUNT ignores the window ............. kills 1
 *   the Trades column reads the stored whole-run count . kills 1
 *   per-leg R ignores the window ...................... kills 4
 *   the window never reaches the composed books ....... kills 1
 *   an empty window falls back to the whole run ....... kills 6
 *
 * 🔴 THE FIRST VERSION OF THIS SUITE WAS GREEN AND TWO OF THOSE SURVIVED IT. Every check asserted
 * on the per-leg R column and nothing else, so a build that never applied the window to the
 * composed books at all, and one whose trade counts stayed at their whole-run values, both passed.
 * The second of those was a REAL DEFECT sitting in the page at the time — the Trades column was
 * reading `leg.trade_count` while the R beside it was windowed. Five green checks did not see it;
 * the mutation run did.
 *
 * ⚠ The rebase ARITHMETIC is pinned separately and outside the browser by
 * `scripts/check_period_window.mjs`, whose own mutation map is in its own header — and which had
 * the same lesson land on it the same day, from the other direction: four scaling cases written
 * against a window whose scale happened to be exactly 1.
 */
import { test, expect, type Page } from '@playwright/test'

const UI = 'http://localhost:5173'
const ID = 'st_period01'

// Two legs, eight trades, spread across 2024 so a window can actually narrow. The single-trade
// fixture in `stacks.spec.ts` cannot exercise this at all: with every trade on one date, a window
// either keeps everything or empties the book, and the interesting case is neither.
//
// ⚠ Balances are the running account AFTER each trade across BOTH legs in date order, which is the
// shape the page composes from. Opening balance $10,000.
const TRADES = {
  sos_fade: [
    { date: '2024-02-01', profit: 1000, r: 2 },
    { date: '2024-05-01', profit: 2000, r: 3 },
    { date: '2024-08-01', profit: -500, r: -1 },
    { date: '2024-11-01', profit: 1500, r: 2 },
  ],
  b_leg: [
    { date: '2024-03-01', profit: 500, r: 1 },
    { date: '2024-06-01', profit: -200, r: -1 },
    { date: '2024-09-01', profit: 800, r: 2 },
    { date: '2024-12-01', profit: 400, r: 1 },
  ],
} as const

function legOf(id: keyof typeof TRADES, name: string) {
  let bal = 10_000
  const equity_curve = TRADES[id].map((t, i) => {
    bal += t.profit
    return {
      trade_number: i + 1,
      index: i + 1,
      equity: bal,
      profit: t.profit,
      date: t.date,
      direction: 'Long' as const,
      entry_ms: Date.parse(`${t.date}T09:00:00Z`),
      exit_ms: Date.parse(`${t.date}T10:00:00Z`),
      r: t.r,
    }
  })
  return {
    run_id: `r_${id}`,
    strategy_id: id,
    strategy_name: name,
    status: 'complete',
    net_pnl: TRADES[id].reduce((a, t) => a + t.profit, 0),
    max_drawdown: -500,
    trade_count: TRADES[id].length,
    sharpe: 1.1,
    avg_trade_duration_min: 60,
    error_message: null,
    daily_pnl: TRADES[id].map((t) => ({ date: t.date, pnl: t.profit })),
    equity_curve,
  }
}

function detail() {
  return {
    stack_id: ID,
    instrument: 'XAUUSD',
    start_date: '2024-01-01',
    end_date: '2024-12-31',
    bar_type: 'Minute',
    bar_value: 15,
    commission_per_side: 0,
    slippage_ticks: 0,
    total_strategies: 2,
    completed_strategies: 2,
    status: 'complete',
    created_at: '2026-09-03T10:00:00Z',
    completed_at: '2026-09-03T10:20:00Z',
    regime_timeline: [],
    strategies: [legOf('sos_fade', 'SOS Fade'), legOf('b_leg', 'B-LEG')],
    mode: 'screen',
    account_size: null,
    risk_cap_pct: null,
    entry_floor_pct: null,
  }
}

async function mock(page: Page) {
  await page.route(
    (u) => /\/api\/backtests\/stacks\/st_\w+$/.test(u.pathname),
    (r) => r.fulfill({ json: detail() })
  )
  await page.route(
    (u) => u.pathname.endsWith('/chart-spec'),
    (r) => r.fulfill({ status: 404, json: { detail: 'no chart in this test' } })
  )
  await page.route(
    (u) => u.pathname.endsWith('/contention'),
    (r) => r.fulfill({ status: 404, json: { detail: 'screen has no contention' } })
  )
}

const rowFor = (page: Page, name: string) =>
  page.getByTestId('per-strategy-table').locator('tr', { hasText: name })

test.describe('a stack can be read over a PERIOD', () => {
  test.beforeEach(async ({ page }) => {
    await mock(page)
  })

  test('the window control is on the stack page at all', async ({ page }) => {
    // MUTATION: put the static date-range span back in place of the chip → red.
    await page.goto(`${UI}/backtests/stacks/${ID}`)
    await expect(page.getByTestId('period-filter')).toBeVisible()
  })

  test('a window narrows the stack, and every per-leg row follows it', async ({ page }) => {
    // MUTATION: drop the `inWindow` clause from `legR` → red on the R assertions.
    //
    // 2024-06-01 → 2024-12-31 keeps A's 08-01 and 11-01 (2 of 4) and B's 06-01, 09-01, 12-01
    // (3 of 4). R follows: A −1+2 = +1R against +6R whole-run, B −1+2+1 = +2R against +3R.
    await page.goto(`${UI}/backtests/stacks/${ID}`)
    await expect(rowFor(page, 'SOS Fade')).toContainText('+6.00R')
    await expect(rowFor(page, 'B-LEG')).toContainText('+3.00R')

    await page.goto(`${UI}/backtests/stacks/${ID}?from=2024-06-01&to=2024-12-31`)
    await expect(rowFor(page, 'SOS Fade')).toContainText('+1.00R')
    await expect(rowFor(page, 'B-LEG')).toContainText('+2.00R')
  })

  test('the TRADES column narrows with the R beside it', async ({ page }) => {
    // MUTATION: put `leg.trade_count` back in that cell → red.
    //
    // 🔴 THIS IS A REAL DEFECT THIS FILE CAUGHT, not a hypothetical. The column read the count the
    // backend stored for the WHOLE run while the R column one cell over was windowed — two figures
    // touching in one row, one filtered and one not, with nothing on screen to say which. It
    // survived the first version of this suite because every check here asserted on R alone.
    await page.goto(`${UI}/backtests/stacks/${ID}`)
    await expect(rowFor(page, 'SOS Fade').locator('td').nth(5)).toHaveText('4')
    await expect(rowFor(page, 'B-LEG').locator('td').nth(5)).toHaveText('4')

    await page.goto(`${UI}/backtests/stacks/${ID}?from=2024-06-01&to=2024-12-31`)
    await expect(rowFor(page, 'SOS Fade').locator('td').nth(5)).toHaveText('2')
    await expect(rowFor(page, 'B-LEG').locator('td').nth(5)).toHaveText('3')
  })

  test('the PORTFOLIO total narrows too, not just the rows', async ({ page }) => {
    // MUTATION: hand `composeCombined`'s downstream the unwindowed books (`wbooks = books`) → the
    // per-leg rows still narrow, because those read the leg curves directly, and only this goes
    // red. That asymmetry is exactly why this check exists separately from the row checks: the
    // first version of this suite asserted only on rows and could not see the books at all.
    await page.goto(`${UI}/backtests/stacks/${ID}`)
    await expect(page.getByTestId('stack-verdict-card')).toContainText('8')

    await page.goto(`${UI}/backtests/stacks/${ID}?from=2024-06-01&to=2024-12-31`)
    await expect(page.getByTestId('stack-verdict-card')).toContainText('5')
  })

  test('the window lives in the URL, so it survives a reload', async ({ page }) => {
    // MUTATION: hold the window in component state instead of the URL → red on reload.
    // ⚠ It is also what makes a window sendable to somebody else, which is how these get discussed.
    await page.goto(`${UI}/backtests/stacks/${ID}?from=2024-06-01&to=2024-12-31`)
    await expect(rowFor(page, 'B-LEG')).toContainText('+2.00R')
    await page.reload()
    await expect(rowFor(page, 'B-LEG')).toContainText('+2.00R')
  })

  test('clearing the window puts the whole stack back', async ({ page }) => {
    // MUTATION: make `active` true whenever a window is merely SET → the cleared page rebuilds
    // through the rebase instead of returning the untouched book. Red on the R going back.
    await page.goto(`${UI}/backtests/stacks/${ID}?from=2024-06-01&to=2024-12-31`)
    await expect(rowFor(page, 'B-LEG')).toContainText('+2.00R')
    await page.goto(`${UI}/backtests/stacks/${ID}`)
    await expect(rowFor(page, 'B-LEG')).toContainText('+3.00R')
    await expect(rowFor(page, 'SOS Fade')).toContainText('+6.00R')
  })

  test('a window a leg never traded in reads as zero, not as its whole run', async ({ page }) => {
    // MUTATION: fall back to the unwindowed count when a leg's windowed count is 0 → red.
    // 🔴 A leg that stood still is an ANSWER. Falling back to its full-run figure would put its
    // best year on a row inside a window it never traded, and nothing on screen would disagree.
    await page.goto(`${UI}/backtests/stacks/${ID}?from=2024-02-01&to=2024-02-28`)
    await expect(rowFor(page, 'SOS Fade')).toContainText('+2.00R')
    await expect(rowFor(page, 'B-LEG')).toContainText('0.00R')
  })
})
