/**
 * Shared-account stacks — the mode a stack is in, and the panel a screen cannot produce.
 *
 * A stack is now one of two DIFFERENT experiments over the same legs. A screen adds up N
 * standalone runs, so no leg could ever block another and the result is an upper bound; a shared
 * stack replays them together on one balance with one risk budget. **Every check here is about
 * keeping the two distinguishable on screen**, because two rows reporting different numbers with
 * nothing to tell them apart is a comparison the reader cannot make.
 *
 * ⚠ Every response is INTERCEPTED, so this suite needs only the dev server — no backend, no VPS,
 * and no dependence on which stacks happen to be in the lab today. Two suites in this folder have
 * broken on the data rather than on the code (`overview.spec.ts`, `stress.spec.ts`), and a test
 * that fails on a day nothing is wrong is indistinguishable from a regression until somebody
 * reads it.
 *
 * ⚠ A fail-watch against HEAD is VACUOUS here — none of this existed, so every check would go red
 * on an element being absent, which proves the locator and nothing else. Non-vacuity is by
 * MUTATION, named in a comment on each check.
 */
import { test, expect, type Page } from '@playwright/test'

const API = 'http://localhost:8000'
const UI = 'http://localhost:5173'
const SHARED_ID = 'st_shared01'
const SCREEN_ID = 'st_screen01'

const LEGS = [
  { run_id: 'r_a', strategy_id: 'mpc_sos_fade', strategy_name: 'MPC SOS Fade' },
  { run_id: 'r_b', strategy_id: 'mpc_bleg', strategy_name: 'MPC B-LEG' },
]

function leg(l: typeof LEGS[number], pnl: number) {
  return {
    ...l, status: 'complete', net_pnl: pnl, max_drawdown: -100, trade_count: 17,
    sharpe: 1.2, avg_trade_duration_min: 60, error_message: null,
    daily_pnl: [{ date: '2024-03-01', pnl }],
    equity_curve: [{
      trade_number: 1, equity: 10000 + pnl, profit: pnl, date: '2024-03-01',
      direction: 'Long', entry_ms: 1709251200000, exit_ms: 1709254800000,
    }],
  }
}

function stackDetail(mode: 'screen' | 'shared') {
  return {
    stack_id: mode === 'shared' ? SHARED_ID : SCREEN_ID,
    instrument: 'XAUUSD', start_date: '2024-01-01', end_date: '2024-12-31',
    bar_type: 'Minute', bar_value: 15, commission_per_side: 0, slippage_ticks: 0,
    total_strategies: 2, completed_strategies: 2, status: 'complete',
    created_at: '2026-08-09T10:00:00Z', completed_at: '2026-08-09T10:20:00Z',
    regime_timeline: [],
    strategies: [leg(LEGS[0], 14183), leg(LEGS[1], 2622)],
    mode,
    account_size: mode === 'shared' ? 10000 : null,
    risk_cap_pct: mode === 'shared' ? 10 : null,
    entry_floor_pct: mode === 'shared' ? 0 : null,
  }
}

/** The measured shape: nothing refused, and every leg posting the same R shared as solo. */
function sharedReport(over: Record<string, unknown> = {}) {
  return {
    stack_id: SHARED_ID, available: true,
    opening_balance: 10000, closing_balance: 36805.85,
    risk_cap_pct: 10, entry_floor_pct: 0,
    peak_open_risk_pct: 10, peak_concurrent_legs: 2, leg_count: 2,
    combined_trades: 33, combined_r: 26.35, contention_events: 0,
    legs: [
      {
        strategy_id: 'mpc_sos_fade', run_id: 'r_a', shared_trades: 17, shared_r: 20.04,
        solo_trades: 17, solo_r: 20.04, solo_closing_balance: 21681.11,
        shrunk: 0, blocked: 0, risk_refused: 0,
      },
      {
        strategy_id: 'mpc_bleg', run_id: 'r_b', shared_trades: 16, shared_r: 6.31,
        solo_trades: 16, solo_r: 6.31, solo_closing_balance: 15188.43,
        shrunk: 0, blocked: 0, risk_refused: 0,
      },
    ],
    events: [],
    neutral: {
      checkable: true, ok: true,
      reason: 'nothing was refused and every leg posts the same R shared as solo, so the shared ' +
        'account changed the dollars and moved no decision',
    },
    progress: { phase: 'complete', pct: 100, message: '33 trades on one account' },
    ...over,
  }
}

// ⚠ Route on `u.pathname` against the `/api` PREFIX, never on an `http://localhost:8000` string.
// The app fetches through the Vite proxy (`api/client.ts` → `const BASE = '/api'`), so a route
// keyed on the backend's own origin matches NOTHING and the page quietly reads the live lab
// instead — which is how three of these checks passed on their first run while asserting on
// whichever stacks happened to be in the database. That is the same vacuous-pass trap this
// folder already records for `svg.first()` and the page-header Retry button.
async function mock(page: Page, mode: 'screen' | 'shared', report?: Record<string, unknown>) {
  await page.route(u => u.pathname.endsWith('/contention'), r =>
    r.fulfill({ json: report ?? sharedReport() }))
  await page.route(u => /\/api\/backtests\/stacks\/st_\w+$/.test(u.pathname), r =>
    r.fulfill({ json: stackDetail(mode) }))
  await page.route(u => u.pathname.endsWith('/chart-spec'), r =>
    r.fulfill({ status: 404, json: { detail: 'no chart in this test' } }))
  await page.route(u => u.pathname.endsWith('/api/backtests/stacks'), r => r.fulfill({
    json: [
      {
        stack_id: SHARED_ID, instrument: 'XAUUSD', start_date: '2024-01-01',
        end_date: '2024-12-31', total_strategies: 2, completed_strategies: 2,
        failed_strategies: 0, status: 'complete', created_at: '2026-08-09T10:00:00Z',
        strategy_names: 'MPC SOS Fade + MPC B-LEG', mode: 'shared', risk_cap_pct: 10,
      },
      {
        stack_id: SCREEN_ID, instrument: 'XAUUSD', start_date: '2024-01-01',
        end_date: '2024-12-31', total_strategies: 2, completed_strategies: 2,
        failed_strategies: 0, status: 'complete', created_at: '2026-08-08T10:00:00Z',
        strategy_names: 'MPC SOS Fade + MPC B-LEG', mode: 'screen', risk_cap_pct: null,
      },
    ],
  }))
}

test.describe('shared-account stacks', () => {
  test('the header says WHICH experiment this stack is', async ({ page }) => {
    // MUTATION: drop the mode chip → red. Without it a screen and a shared run over the same
    // legs are two pages of different numbers with nothing explaining the difference.
    await mock(page, 'shared')
    await page.goto(`${UI}/backtests/stacks/${SHARED_ID}`)
    await expect(page.getByTestId('stack-mode-chip')).toContainText('Shared account')
    await expect(page.getByTestId('stack-mode-chip')).toContainText('10.00% cap')

    await mock(page, 'screen')
    await page.goto(`${UI}/backtests/stacks/${SCREEN_ID}`)
    await expect(page.getByTestId('stack-mode-chip')).toContainText('Screen')
    // ⚠ The words that matter: a screen is an UPPER BOUND, and saying so is the whole reason the
    // chip exists on a screen at all rather than only on a shared run.
    await expect(page.getByTestId('stack-mode-chip')).toContainText('upper bound')
  })

  test('a screen never even ASKS about contention', async ({ page }) => {
    // MUTATION: drop the `isShared` argument from `useStackContention` → red.
    //
    // ⚠ Asserting only that the panel is absent is VACUOUS and passed against that mutation.
    // With the hook disabled the report is `undefined`, so `shared && <panel/>` renders nothing
    // whichever way the render condition is written — the render guard and the fetch guard are
    // not separable from the DOM. The FETCH is the real guard: enabled on a screen, the endpoint
    // answers `available: false`, and the panel would sit on a finished screen showing a
    // permanent "replaying the strategies on one account…" spinner for a run that is not one.
    await mock(page, 'screen')
    // ⚠ Registered AFTER `mock`, and it has to be: Playwright matches the MOST RECENTLY
    // registered route first, so a counter installed before `mock` is shadowed by mock's own
    // handler and never increments — which makes the assertion below trivially true. That is a
    // third vacuous pass in this one file; every one of them looked like a green test.
    let asked = 0
    await page.route(u => u.pathname.endsWith('/contention'), r => { asked++; return r.fulfill({ json: sharedReport() }) })
    await page.goto(`${UI}/backtests/stacks/${SCREEN_ID}`)
    await expect(page.getByText('Strategies in this stack')).toBeVisible()
    await expect(page.getByTestId('shared-account-panel')).toHaveCount(0)
    expect(asked, 'a screen has no account to contend over — it must not poll for one').toBe(0)
  })

  test('an empty contention log reads as a MEASUREMENT, not as a missing one', async ({ page }) => {
    // MUTATION: render nothing when `contention_events === 0` → red.
    // ⚠ This is the check that matters most, because the measured 6.5-year two-bot run refused
    // NOTHING — so the expected state of this panel is the empty one, and a panel that goes blank
    // there is indistinguishable from one that failed to load.
    await mock(page, 'shared')
    await page.goto(`${UI}/backtests/stacks/${SHARED_ID}`)
    const panel = page.getByTestId('shared-account-panel')
    await expect(panel).toContainText('Nothing was ever refused')
    await expect(panel).toContainText('current')          // ...to each trade's CURRENT stop
    await expect(panel).toContainText('rarely have had anything to arbitrate')
  })

  test('the screen-vs-shared delta is computed off the SOLO controls', async ({ page }) => {
    // MUTATION: sum the legs' shared R instead of their solo closing balances → red.
    // The solo controls ARE the screen — each leg on its own full account — so this is a
    // like-for-like comparison against a replay that really happened rather than an estimate.
    // 21,681.11 + 15,188.43 − 10,000 = 26,869.54 promised; 36,805.85 delivered; +9,936.31.
    // (`fmtMoney` renders whole dollars, so the assertions are on the rounded figures.)
    await mock(page, 'shared')
    await page.goto(`${UI}/backtests/stacks/${SHARED_ID}`)
    const panel = page.getByTestId('shared-account-panel')
    await expect(panel).toContainText('$36,806')
    await expect(panel).toContainText('$26,870')
    await expect(panel).toContainText('+$9,936 on one account')
  })

  test('the cap and the peak risk are stated together', async ({ page }) => {
    // MUTATION: drop the cap from the caption → red. A peak open risk with no cap beside it is a
    // number the reader cannot judge — 10% is either the ceiling or a third of it.
    await mock(page, 'shared')
    await page.goto(`${UI}/backtests/stacks/${SHARED_ID}`)
    const panel = page.getByTestId('shared-account-panel')
    await expect(panel).toContainText('10.00%')
    await expect(panel).toContainText('against a 10.00% cap')
    await expect(panel).toContainText('2 of 2 holding at once')
  })

  test('a shared run still replaying shows its phase, not an empty panel', async ({ page }) => {
    // MUTATION: return null from the unavailable branch → red. A multi-minute replay with no
    // feedback reads as a page that failed; `available: false` here means STILL RUNNING and the
    // progress line is what separates it from "this is a screen" and "it failed".
    await mock(page, 'shared', {
      stack_id: SHARED_ID, available: false, legs: [], events: [], neutral: null,
      opening_balance: null, closing_balance: null, risk_cap_pct: null, entry_floor_pct: null,
      peak_open_risk_pct: null, peak_concurrent_legs: null, leg_count: null,
      combined_trades: null, combined_r: null, contention_events: null,
      progress: { phase: 'solo:mpc_bleg', pct: 86, message: 'solo:mpc_bleg · bar 15,872 / 23,712' },
    })
    await page.goto(`${UI}/backtests/stacks/${SHARED_ID}`)
    await expect(page.getByTestId('shared-account-panel')).toContainText('bar 15,872')
    await expect(page.getByTestId('shared-account-panel')).toContainText('86%')
  })

  test('a seam failure is called out rather than left in a column to be spotted', async ({ page }) => {
    // MUTATION: render `neutral.reason` in the neutral style regardless of `ok` → red.
    // R is normalised to the trade's own risk, so with a full budget a leg MUST post the same R
    // shared as solo. A difference is the shared account moving a decision it must not touch —
    // a defect in the seam, not a portfolio effect — and it is invisible in a table of numbers.
    await mock(page, 'shared', sharedReport({
      neutral: {
        checkable: true, ok: false, drifted: ['mpc_bleg'],
        reason: 'nothing was refused, yet these legs post different R shared and solo',
      },
    }))
    await page.goto(`${UI}/backtests/stacks/${SHARED_ID}`)
    await expect(page.getByTestId('shared-account-panel')).toContainText('Seam check failed')
  })

  test('the Stacks list says which mode each row is', async ({ page }) => {
    // MUTATION: drop the Mode column → red. Two rows over the same legs and window, reporting
    // different numbers, with nothing on screen accounting for the gap.
    await mock(page, 'shared')
    await page.goto(`${UI}/backtests?tab=stacks`)
    const shared = page.locator('tr', { hasText: 'MPC SOS Fade + MPC B-LEG' }).first()
    await expect(shared).toContainText('Shared')
    await expect(page.locator('tbody')).toContainText('Screen')
  })
})

test.describe('the stack config modal', () => {
  test('the account fields appear only in shared mode', async ({ page }) => {
    // MUTATION: render the fields unconditionally → red. On a screen there is no account — each
    // leg traded its own — so a balance and a cap there would be settings the run never had, and
    // the backend stores NULL for all three.
    await mock(page, 'shared')
    await page.goto(`${UI}/backtests?tab=stacks`)
    await page.getByRole('button', { name: /new stack/i }).click()

    await expect(page.getByTestId('stack-account-fields')).toHaveCount(0)
    await page.getByTestId('stack-mode-shared').click()
    await expect(page.getByTestId('stack-account-fields')).toBeVisible()
    await page.getByTestId('stack-mode-screen').click()
    await expect(page.getByTestId('stack-account-fields')).toHaveCount(0)
  })

  test('shared mode says it reuses nothing and costs a control per leg', async ({ page }) => {
    // MUTATION: drop the replay-count line → red. `1 + legs` full replays is minutes of work, and
    // the solo control is not optional: without it a difference in the shared book is a mixture
    // of *the cap bit* and *the shared balance re-sized everything*.
    await mock(page, 'shared')
    await page.goto(`${UI}/backtests?tab=stacks`)
    await page.getByRole('button', { name: /new stack/i }).click()
    await page.getByTestId('stack-mode-shared').click()
    await expect(page.getByText(/Every leg is re-run — nothing is reused/)).toBeVisible()
  })
})
