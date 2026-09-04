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

const UI = 'http://localhost:5173'
const SHARED_ID = 'st_shared01'
const SCREEN_ID = 'st_screen01'

const LEGS = [
  { run_id: 'r_a', strategy_id: 'sos_fade', strategy_name: 'SOS Fade' },
  { run_id: 'r_b', strategy_id: 'b_leg', strategy_name: 'B-LEG' },
]

/**
 * One leg, with the two books a SHARED stack really has on disk.
 *
 * ⚠ `pnl` and `soloPnl` differ by design and `r` is IDENTICAL between them — that is the whole
 * shape of the defect this fixture exists to pin. Inside a shared account a leg sizes off a
 * balance every strategy grew, so the same trades at the same R are worth wildly different
 * dollars; measured on the live stack `st_94aeb25f0c`, B-LEG posts 17.8674R either way and
 * $47,758,999 against $21,064. `solo` omitted models a stack replayed before the control book was
 * kept (or a screen, which has no control at all).
 */
function leg(l: (typeof LEGS)[number], pnl: number, r: number, soloPnl?: number) {
  const point = (profit: number) => ({
    trade_number: 1,
    equity: 10000 + profit,
    profit,
    date: '2024-03-01',
    direction: 'Long',
    entry_ms: 1709251200000,
    exit_ms: 1709254800000,
    r,
  })
  return {
    ...l,
    status: 'complete',
    net_pnl: pnl,
    max_drawdown: -100,
    trade_count: 17,
    sharpe: 1.2,
    avg_trade_duration_min: 60,
    error_message: null,
    daily_pnl: [{ date: '2024-03-01', pnl }],
    equity_curve: [point(pnl)],
    ...(soloPnl == null
      ? {}
      : {
          solo_equity_curve: [point(soloPnl)],
          solo_daily_pnl: [{ date: '2024-03-01', pnl: soloPnl }],
        }),
  }
}

/** `solo: false` models a shared stack replayed before the control book was kept. */
function stackDetail(mode: 'screen' | 'shared', opts: { solo?: boolean } = {}) {
  const keepSolo = mode === 'shared' && opts.solo !== false
  return {
    stack_id: mode === 'shared' ? SHARED_ID : SCREEN_ID,
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
    created_at: '2026-08-09T10:00:00Z',
    completed_at: '2026-08-09T10:20:00Z',
    regime_timeline: [],
    strategies: [
      leg(LEGS[0], 14183, 20.04, keepSolo ? 3000 : undefined),
      leg(LEGS[1], 2622, 6.31, keepSolo ? 500 : undefined),
    ],
    mode,
    account_size: mode === 'shared' ? 10000 : null,
    risk_cap_pct: mode === 'shared' ? 10 : null,
    entry_floor_pct: mode === 'shared' ? 0 : null,
  }
}

/** The measured shape: nothing refused, and every leg posting the same R shared as solo. */
function sharedReport(over: Record<string, unknown> = {}) {
  return {
    stack_id: SHARED_ID,
    available: true,
    opening_balance: 10000,
    closing_balance: 36805.85,
    risk_cap_pct: 10,
    entry_floor_pct: 0,
    peak_open_risk_pct: 10,
    peak_concurrent_legs: 2,
    leg_count: 2,
    combined_trades: 33,
    combined_r: 26.35,
    contention_events: 0,
    legs: [
      {
        strategy_id: 'sos_fade',
        run_id: 'r_a',
        shared_trades: 17,
        shared_r: 20.04,
        solo_trades: 17,
        solo_r: 20.04,
        solo_closing_balance: 21681.11,
        shrunk: 0,
        blocked: 0,
        risk_refused: 0,
      },
      {
        strategy_id: 'b_leg',
        run_id: 'r_b',
        shared_trades: 16,
        shared_r: 6.31,
        solo_trades: 16,
        solo_r: 6.31,
        solo_closing_balance: 15188.43,
        shrunk: 0,
        blocked: 0,
        risk_refused: 0,
      },
    ],
    events: [],
    neutral: {
      checkable: true,
      ok: true,
      reason:
        'nothing was refused and every leg posts the same R shared as solo, so the shared ' +
        'account changed the dollars and moved no decision',
    },
    progress: { phase: 'complete', pct: 100, message: '33 trades on one account' },
    ...over,
  }
}

/**
 * A shared report that has NOT arrived yet — `available: false` with a live phase.
 *
 * ⚠ Every scalar is explicitly `null` rather than omitted. That is what the backend really sends
 * while a replay is in flight, and a fixture that quietly leaves them out is describing a payload
 * shape the server never produces.
 */
function replaying(progress?: { phase: string; pct: number; message: string }) {
  return {
    stack_id: SHARED_ID,
    available: false,
    legs: [],
    events: [],
    neutral: null,
    opening_balance: null,
    closing_balance: null,
    risk_cap_pct: null,
    entry_floor_pct: null,
    peak_open_risk_pct: null,
    peak_concurrent_legs: null,
    leg_count: null,
    combined_trades: null,
    combined_r: null,
    contention_events: null,
    progress: progress ?? {
      phase: 'solo:b_leg',
      pct: 86,
      message: 'solo:b_leg · bar 15,872 / 23,712',
    },
  }
}

/**
 * Re-point the stack detail at a stack that is still RUNNING, with no leg finished.
 *
 * ⚠ Registered AFTER `mock`, and it has to be — Playwright matches the most recently registered
 * route first, so calling this before `mock` leaves the finished fixture in place and the check
 * asserts on a stack that is not running.
 */
async function runningStack(page: Page) {
  await page.route(
    (u) => /\/api\/backtests\/stacks\/st_\w+$/.test(u.pathname),
    (r) => {
      const d = stackDetail('shared')
      return r.fulfill({
        json: {
          ...d,
          status: 'running',
          completed_at: null,
          completed_strategies: 0,
          strategies: d.strategies.map((s) => ({
            ...s,
            status: 'running',
            net_pnl: null,
            trade_count: null,
            equity_curve: [],
            solo_equity_curve: [],
            daily_pnl: [],
            solo_daily_pnl: [],
          })),
        },
      })
    }
  )
}

// ⚠ Route on `u.pathname` against the `/api` PREFIX, never on an `http://localhost:8000` string.
// The app fetches through the Vite proxy (`api/client.ts` → `const BASE = '/api'`), so a route
// keyed on the backend's own origin matches NOTHING and the page quietly reads the live lab
// instead — which is how three of these checks passed on their first run while asserting on
// whichever stacks happened to be in the database. That is the same vacuous-pass trap this
// folder already records for `svg.first()` and the page-header Retry button.
async function mock(
  page: Page,
  mode: 'screen' | 'shared',
  report?: Record<string, unknown>,
  opts: { solo?: boolean } = {}
) {
  await page.route(
    (u) => u.pathname.endsWith('/contention'),
    (r) => r.fulfill({ json: report ?? sharedReport() })
  )
  await page.route(
    (u) => /\/api\/backtests\/stacks\/st_\w+$/.test(u.pathname),
    (r) => r.fulfill({ json: stackDetail(mode, opts) })
  )
  await page.route(
    (u) => u.pathname.endsWith('/chart-spec'),
    (r) => r.fulfill({ status: 404, json: { detail: 'no chart in this test' } })
  )
  await page.route(
    (u) => u.pathname.endsWith('/api/backtests/stacks'),
    (r) =>
      r.fulfill({
        json: [
          {
            stack_id: SHARED_ID,
            instrument: 'XAUUSD',
            start_date: '2024-01-01',
            end_date: '2024-12-31',
            total_strategies: 2,
            completed_strategies: 2,
            failed_strategies: 0,
            status: 'complete',
            created_at: '2026-08-09T10:00:00Z',
            strategy_names: 'SOS Fade + B-LEG',
            mode: 'shared',
            risk_cap_pct: 10,
          },
          {
            stack_id: SCREEN_ID,
            instrument: 'XAUUSD',
            start_date: '2024-01-01',
            end_date: '2024-12-31',
            total_strategies: 2,
            completed_strategies: 2,
            failed_strategies: 0,
            status: 'complete',
            created_at: '2026-08-08T10:00:00Z',
            strategy_names: 'SOS Fade + B-LEG',
            mode: 'screen',
            risk_cap_pct: null,
          },
        ],
      })
  )
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
    await page.route(
      (u) => u.pathname.endsWith('/contention'),
      (r) => {
        asked++
        return r.fulfill({ json: sharedReport() })
      }
    )
    await page.goto(`${UI}/backtests/stacks/${SCREEN_ID}`)
    // ⚠ Wait on the Verdict card, not on the shared panel — the panel's absence is the thing under
    // test, so waiting for anything derived from it would be waiting for the assertion.
    await expect(page.getByTestId('stack-verdict-card')).toBeVisible()
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
    // Visible on the chip, at a glance.
    await expect(panel).toContainText('Nothing refused')
    // ⚠ And the REASONING is still reachable — it moved onto the chip's ⓘ when the panel was
    // condensed (2026-08-10), it was not deleted. Asserting only the chip would pass against a
    // build that dropped the explanation entirely, which is what turns a measured result back
    // into a number nobody can interpret.
    await panel.getByTestId('contention-chip').locator('.cursor-help').hover()
    const tip = page.locator('body > span', { hasText: 'rarely have had anything to arbitrate' })
    await expect(tip).toContainText('Nothing was ever refused')
    await expect(tip).toContainText('current') // ...to each trade's CURRENT stop
  })

  test('together-vs-apart is computed off the SOLO controls', async ({ page }) => {
    // MUTATION: sum the legs' shared R instead of their solo closing balances → red.
    // The solo controls are each leg on its own full account, so this is a like-for-like
    // comparison against a replay that really happened rather than an estimate.
    // 21,681.11 + 15,188.43 − 10,000 = 26,869.54 apart; 36,805.85 together; +9,936.31.
    // (`fmtMoney` renders whole dollars, so the assertions are on the rounded figures.)
    await mock(page, 'shared')
    await page.goto(`${UI}/backtests/stacks/${SHARED_ID}`)
    const row = page.getByTestId('together-apart')
    await expect(row).toContainText('$36,806')
    await expect(row).toContainText('$26,870')
    await expect(row).toContainText('+$9,936')
    // ⚠ The gap is meaningless — worse, it reads as extra RISK — without the sentence saying it is
    // compounding: on one account the second strategy sizes off a balance the first has grown, and
    // `docs/SHARED_RISK_STACK.md` predicted the opposite SIGN from exactly that misreading. When
    // the panel was condensed the sentence moved onto the ⓘ; it must still be reachable.
    await row.locator('.cursor-help').hover()
    await expect(page.locator('body > span', { hasText: 'COMPOUNDING' })).toContainText(
      'never on these dollars'
    )
  })

  test('the cap and the peak risk are stated together', async ({ page }) => {
    // MUTATION: drop the cap from the caption → red. A peak open risk with no cap beside it is a
    // number the reader cannot judge — 10% is either the ceiling or a third of it.
    await mock(page, 'shared')
    await page.goto(`${UI}/backtests/stacks/${SHARED_ID}`)
    const panel = page.getByTestId('shared-account-panel')
    await expect(panel).toContainText('10.00%')
    await expect(panel).toContainText('of a 10.00% cap')
    await expect(panel).toContainText('2 of 2 holding at once')
  })

  test('the per-strategy table is folded away when the budget refused nothing', async ({
    page,
  }) => {
    // MUTATION: render the table unconditionally → the first assertion goes red.
    // On every run measured so far its Shrunk / Blocked / Risk-refused columns are entirely
    // em-dashes, so unfolded it is the largest thing on the page saying the least.
    // ⚠ The SECOND half is the one that matters: with contention it must open ITSELF, or the one
    // state the table exists for is a click away behind a control nobody has reason to press.
    await mock(page, 'shared')
    await page.goto(`${UI}/backtests/stacks/${SHARED_ID}`)
    const panel = page.getByTestId('shared-account-panel')
    // 🔴 WAIT FOR THE PANEL FIRST. `locator('table')).toHaveCount(0)` is satisfied the instant the
    // PANEL is absent too, so asserting it straight after `goto` passed against the mutation that
    // renders the table unconditionally — a fourth instance of this folder's vacuous-pass trap,
    // caught only by running the mutation.
    await expect(panel.getByRole('button', { name: /per-strategy detail/i })).toBeVisible()
    await expect(panel.locator('table')).toHaveCount(0)
    await panel.getByRole('button', { name: /per-strategy detail/i }).click()
    await expect(panel.locator('table')).toBeVisible()

    await mock(page, 'shared', sharedReport({ contention_events: 3 }))
    await page.goto(`${UI}/backtests/stacks/${SHARED_ID}`)
    await expect(page.getByTestId('shared-account-panel').locator('table')).toBeVisible()
  })

  test('the strategies are toggled from INSIDE the Verdict card, and the KPIs follow', async ({
    page,
  }) => {
    // MUTATION: pass a fixed leg set to `composeCombined` instead of `enabled` → red.
    // This is the whole reason the legs moved into the Verdict card: the control that decides
    // what Made / Risked / Trusted count now sits in the same row as the numbers it recomputes,
    // where it used to be a chip strip in a section of its own further down the page.
    await mock(page, 'shared')
    await page.goto(`${UI}/backtests/stacks/${SHARED_ID}`)
    const verdict = page.getByTestId('stack-verdict-card')
    // Both legs on: 17 + 1 trades in the fixture's equity curves (one point each carries a
    // direction, so the union is 2 — the hero counts the UNION, not the legs' own totals).
    await expect(verdict).toContainText('2 of 2 on')
    const before = await verdict.locator('.text-\\[34px\\]').innerText()

    await verdict.getByRole('button', { name: /B-LEG/ }).click()
    await expect(verdict).toContainText('1 of 2 on')
    await expect(verdict.locator('.text-\\[34px\\]')).not.toHaveText(before)
  })

  test('the last strategy left on cannot be switched off', async ({ page }) => {
    // MUTATION: drop the `isLastOn` guard → red. A portfolio of no strategies has nothing to
    // measure, so every card beside this one would render an empty run rather than a smaller one.
    await mock(page, 'shared')
    await page.goto(`${UI}/backtests/stacks/${SHARED_ID}`)
    const verdict = page.getByTestId('stack-verdict-card')
    await verdict.getByRole('button', { name: /B-LEG/ }).click()
    await expect(verdict).toContainText('1 of 2 on')
    // The remaining leg is no longer a button at all — a disabled-looking control you can still
    // press is the version of this that fails silently.
    await expect(verdict.getByRole('button', { name: /SOS Fade/ })).toHaveCount(0)
  })

  test('switching a strategy off swaps in the SOLO control, not its share of the stack', async ({
    page,
  }) => {
    // 🔴 THE DEFECT THIS FILE EXISTS FOR MOST. Reported off the screen 2026-08-10: with SOS
    // Fade switched off, the page said B-LEG had made $47,758,999 — while the same strategy
    // run standalone over the same window made $21,064. Both were right. Composing the remaining
    // leg from its SHARED trades answers "what did it contribute to an account the others built";
    // the reader hears "what would this have made alone", and inside the stack it sizes off a
    // balance every strategy grew (measured: same 99 trades, same 17.8674R, 2,266x the dollars).
    //
    // MUTATION: drop the `basis === 'solo'` branch in `composeCombined`, so `books` always uses
    // `equity_curve` → Made reads the shared +$2,622 instead of the solo +$500 → red.
    await mock(page, 'shared')
    await page.goto(`${UI}/backtests/stacks/${SHARED_ID}`)
    const verdict = page.getByTestId('stack-verdict-card')
    await expect(verdict).toContainText('2 of 2 on')
    // Both on: the shared book, exactly as replayed — 14,183 + 2,622.
    await expect(page.getByTestId('basis-chip')).toContainText('the shared account, as it ran')
    await expect(page.locator('.text-\\[34px\\]').nth(1)).toContainText('16,805')

    await verdict.getByRole('button', { name: /SOS Fade/ }).click()
    await expect(verdict).toContainText('1 of 2 on')
    // The SOLO figure ($500), never the leg's share of the shared book ($2,622).
    await expect(page.locator('.text-\\[34px\\]').nth(1)).toContainText('500')
    await expect(page.locator('.text-\\[34px\\]').nth(1)).not.toContainText('2,622')
    // And the page SAYS which book it is showing — the numbers move by orders of magnitude here,
    // so a silent swap is its own defect even when every number is right.
    await expect(page.getByTestId('basis-chip')).toContainText('on its own account')
  })

  test('a leg row is stated in R, which is the one figure a shared account cannot move', async ({
    page,
  }) => {
    // MUTATION: make the row value `counts.get(id)` again → red on the R assertions.
    // The row used to read the trade count with "It made <net_pnl> on its own account" on its
    // tooltip — and on a shared stack `net_pnl` is the leg's dollars INSIDE the portfolio, so that
    // sentence was false by 2,266x on the measured stack. R is normalised to each trade's own
    // risk, so it is identical shared or solo; the dollars are the thing that moves.
    await mock(page, 'shared')
    await page.goto(`${UI}/backtests/stacks/${SHARED_ID}`)
    const verdict = page.getByTestId('stack-verdict-card')
    await expect(verdict).toContainText('+20.04R')
    await expect(verdict).toContainText('+6.31R')

    // ⚠ And it stays in R when the leg is switched OFF. It fell back to the trade count there,
    // so one row read `+20.04R` and the other `17` on the same card — two units, one column.
    await verdict.getByRole('button', { name: /SOS Fade/ }).click()
    await expect(verdict).toContainText('1 of 2 on')
    await expect(verdict).toContainText('+20.04R')
  })

  test('a shared stack with no stored control REFUSES rather than composing one', async ({
    page,
  }) => {
    // MUTATION: fall back to the shared curves when `solo_equity_curve` is absent → red, because
    // the page would then render KPIs (and no refusal card) off the wrong book.
    // A stack replayed before 2026-08-10 kept only `solo_r` and `solo_closing_balance`, so there
    // is no control book to show. Composing one from the shared trades is precisely the defect —
    // this is the *no data is not the same as cannot ask* rule, on the page that met it.
    await mock(page, 'shared', undefined, { solo: false })
    await page.goto(`${UI}/backtests/stacks/${SHARED_ID}`)
    const verdict = page.getByTestId('stack-verdict-card')
    await verdict.getByRole('button', { name: /SOS Fade/ }).click()
    await expect(verdict).toContainText('1 of 2 on')
    await expect(page.getByTestId('basis-chip')).toContainText('never replayed')
    await expect(page.getByTestId('unmeasured-card')).toBeVisible()
    // ⚠ The toggles have to survive it. The Verdict card holds them, so hiding the panel with the
    // KPIs would strand the reader in a state they cannot click their way out of.
    await expect(verdict).toBeVisible()
    await page.getByRole('button', { name: /switch every strategy back on/i }).click()
    await expect(verdict).toContainText('2 of 2 on')
    await expect(page.getByTestId('unmeasured-card')).toHaveCount(0)
  })

  test('a SCREEN stays additive — any subset of it is a real reading', async ({ page }) => {
    // MUTATION: drop the `mode !== 'shared'` branch so a screen takes the shared rules → red,
    // because one leg of a screen would then be called `never replayed`.
    // On a screen every leg traded its OWN full account, so nothing could block anything and
    // removing one removes only its own trades. It needs no control book and must never refuse.
    await mock(page, 'screen')
    await page.goto(`${UI}/backtests/stacks/${SCREEN_ID}`)
    const verdict = page.getByTestId('stack-verdict-card')
    await expect(page.getByTestId('basis-chip')).toContainText('own account')
    await verdict.getByRole('button', { name: /SOS Fade/ }).click()
    await expect(verdict).toContainText('1 of 2 on')
    await expect(page.getByTestId('unmeasured-card')).toHaveCount(0)
    // Its own dollars, straight from the leg — a screen has one book and this is it.
    await expect(page.locator('.text-\\[34px\\]').nth(1)).toContainText('2,622')
  })

  test('a shared run still replaying shows its phase, not an empty panel', async ({ page }) => {
    // MUTATION: return null from the unavailable branch → red. A multi-minute replay with no
    // feedback reads as a page that failed; `available: false` here means STILL RUNNING and the
    // progress line is what separates it from "this is a screen" and "it failed".
    await mock(page, 'shared', {
      stack_id: SHARED_ID,
      available: false,
      legs: [],
      events: [],
      neutral: null,
      opening_balance: null,
      closing_balance: null,
      risk_cap_pct: null,
      entry_floor_pct: null,
      peak_open_risk_pct: null,
      peak_concurrent_legs: null,
      leg_count: null,
      combined_trades: null,
      combined_r: null,
      contention_events: null,
      progress: { phase: 'solo:b_leg', pct: 86, message: 'solo:b_leg · bar 15,872 / 23,712' },
    })
    await page.goto(`${UI}/backtests/stacks/${SHARED_ID}`)
    await expect(page.getByTestId('shared-account-panel')).toContainText('bar 15,872')
    await expect(page.getByTestId('shared-account-panel')).toContainText('86%')
  })

  test('a RUNNING stack has one progress readout, not two', async ({ page }) => {
    // MUTATION: drop `!sharedInBanner` from the shared-account section's render guard → red on the
    // second assertion, with two live progress readouts on screen exactly as reported.
    //
    // 🔴 The banner counted finished STRATEGIES while the panel below it counted BARS inside the
    // current leg, each under its own heading. Two readouts of ONE job, saying different numbers,
    // with nothing on screen saying they are the same job.
    await mock(page, 'shared', replaying())
    await runningStack(page)
    await page.goto(`${UI}/backtests/stacks/${SHARED_ID}`)
    // ⚠ Wait for the progress block FIRST. `toHaveCount(0)` on the panel is satisfied while the
    // whole page is still loading, so asserting it straight after `goto` passes against the
    // mutation — the vacuous-pass trap this file has now recorded four times.
    await expect(page.getByTestId('stack-progress')).toBeVisible()
    await expect(page.getByTestId('shared-account-panel')).toHaveCount(0)
    // The bar counter is the finer measurement and survives the merge; the leg count becomes its
    // caption. Losing either is losing half of what the reader was watching.
    await expect(page.getByTestId('stack-progress')).toContainText('bar 15,872')
    await expect(page.getByTestId('stack-progress')).toContainText('0 of 2 strategies complete')
    // 🔴 And the phase is said in WORDS. `solo:b_leg` is the machine's name for it and tells the
    // person watching nothing — asserting only the bar count would pass against a banner printing
    // the raw phase straight through.
    await expect(page.getByTestId('stack-progress')).toContainText('Replaying B-LEG')
    await expect(page.getByTestId('stack-progress')).not.toContainText('solo:')
  })

  test('a FAILED shared replay keeps its own panel even while the stack runs', async ({ page }) => {
    // MUTATION: drop 'failed' from `STOPPED_PHASES` → red. This is the load-bearing exclusion: a
    // failure has a SENTENCE to show, not a percentage, and folding a stopped replay into a
    // progress bar is how a dead job comes to look like a slow one.
    await mock(
      page,
      'shared',
      replaying({ phase: 'failed', pct: 41, message: 'no bars for XAUUSD.p' })
    )
    await runningStack(page)
    await page.goto(`${UI}/backtests/stacks/${SHARED_ID}`)
    await expect(page.getByTestId('shared-account-panel')).toContainText('shared replay failed')
    await expect(page.getByTestId('shared-account-panel')).toContainText('no bars for XAUUSD.p')
  })

  test('a CANCELLED shared replay says so instead of spinning at 100%', async ({ page }) => {
    // MUTATION 1: drop 'cancelled' from `STOPPED_PHASES` → red, the panel gone and the banner
    // headlining the backend's own word `cancelled` beside a spinner and a full bar.
    // MUTATION 2: put the panel's cancelled branch back behind its `running` gate → red the same
    // way, because the branch that has the sentence never runs.
    //
    // \u{1F534} BOTH mutations are needed and neither alone is the bug. The two halves are one
    // decision — who draws a stopped replay — and until 2026-09-03 they disagreed: the banner
    // excluded failures only, the panel spoke only once nothing was running, so a cancellation
    // arriving mid-replay was drawn by NEITHER and fell through to raw machine text.
    await mock(page, 'shared', replaying({ phase: 'cancelled', pct: 100, message: 'cancelled' }))
    await runningStack(page)
    await page.goto(`${UI}/backtests/stacks/${SHARED_ID}`)
    await expect(page.getByTestId('shared-account-panel')).toContainText(
      'shared replay was cancelled'
    )
    await expect(page.getByTestId('shared-account-panel')).toContainText('Rerun the stack')
    // And the banner must not be drawing the same replay a second time. The stopped one belongs to
    // the panel, so the banner falls back to the leg count — and never puts a stopped phase's name
    // next to a spinner, which is how a dead job comes to look like a slow one.
    await expect(page.getByTestId('stack-progress')).toContainText('0 of 2 strategies complete')
    await expect(page.getByTestId('stack-progress')).not.toContainText('cancelled')
  })

  test('the loading phase is said in words, not in its log line', async ({ page }) => {
    // MUTATION: delete the `starting` entry from `PHASE_WORDS` → red, the banner falling back to
    // the message and reading 'loading bars…'.
    //
    // The message is written for a log line and is not a fallback worth relying on, so every phase
    // the backend can emit is named. This is the check that the map is CONSULTED — without it a
    // backend message reworded tomorrow silently becomes this page's headline.
    await mock(page, 'shared', replaying({ phase: 'starting', pct: 1, message: 'loading bars…' }))
    await runningStack(page)
    await page.goto(`${UI}/backtests/stacks/${SHARED_ID}`)
    await expect(page.getByTestId('stack-progress')).toContainText('Loading the bars')
  })

  test('an UNRECOGNISED phase still draws exactly ONE readout', async ({ page }) => {
    // MUTATION: make the banner absorb only the phases it knows (`solo:` / `shared` / `PHASE_WORDS`)
    // → red, the panel drawing its own spinner alongside the banner and the page back to TWO
    // readouts of one job.
    //
    // \u{1F534} This pins a JUDGEMENT rather than a fact, and it is the one in this merge. An
    // unknown phase is absorbed on purpose: handing it to the panel is the defect this whole
    // change exists to fix, and one readout a beat coarse beats two that disagree. If a future
    // STOPPED phase is added to the backend it must be added to `STOPPED_PHASES` in the same
    // change — that is the cost of this direction, and it is the cheaper of the two.
    await mock(
      page,
      'shared',
      replaying({ phase: 'warming', pct: 12, message: 'warming · bar 4 / 9' })
    )
    await runningStack(page)
    await page.goto(`${UI}/backtests/stacks/${SHARED_ID}`)
    await expect(page.getByTestId('stack-progress')).toBeVisible()
    await expect(page.getByTestId('shared-account-panel')).toHaveCount(0)
    // Degrades to the message's own first segment — machine-ish, but the bar count is kept and the
    // reader is never shown two disagreeing readouts.
    await expect(page.getByTestId('stack-progress')).toContainText('bar 4 / 9')
  })

  test('a seam failure is called out rather than left in a column to be spotted', async ({
    page,
  }) => {
    // MUTATION: render `neutral.reason` in the neutral style regardless of `ok` → red.
    // R is normalised to the trade's own risk, so with a full budget a leg MUST post the same R
    // shared as solo. A difference is the shared account moving a decision it must not touch —
    // a defect in the seam, not a portfolio effect — and it is invisible in a table of numbers.
    await mock(
      page,
      'shared',
      sharedReport({
        neutral: {
          checkable: true,
          ok: false,
          drifted: ['b_leg'],
          reason: 'nothing was refused, yet these legs post different R shared and solo',
        },
      })
    )
    await page.goto(`${UI}/backtests/stacks/${SHARED_ID}`)
    await expect(page.getByTestId('shared-account-panel')).toContainText('Seam check failed')
  })

  test('the Stacks list says which mode each row is', async ({ page }) => {
    // MUTATION: drop the Mode column → red. Two rows over the same legs and window, reporting
    // different numbers, with nothing on screen accounting for the gap.
    await mock(page, 'shared')
    await page.goto(`${UI}/backtests?tab=stacks`)
    const shared = page.locator('tr', { hasText: 'SOS Fade + B-LEG' }).first()
    await expect(shared).toContainText('Shared')
    await expect(page.locator('tbody')).toContainText('Screen')
  })
})

test.describe('the stack config modal', () => {
  test('a NEW stack is a shared account, with no screen to pick by mistake', async ({ page }) => {
    // MUTATION: default `mode` back to 'screen', or restore the two-button picker → red.
    // Aaron never wants a screen ("that's what a stack IS — we're sharing the same resource"), and
    // offering it as an equal choice made the one mode he wants a coin flip. The account fields
    // are the tell that it really is shared: a screen has no account, so the backend stores NULL
    // for all three and the fields would be settings the run never had.
    await mock(page, 'shared')
    await page.goto(`${UI}/backtests?tab=stacks`)
    await page.getByRole('button', { name: /new stack/i }).click()

    await expect(page.getByTestId('stack-account-fields')).toBeVisible()
    await expect(page.getByTestId('stack-mode-screen')).toHaveCount(0)
    await expect(page.getByTestId('stack-mode-shared')).toHaveCount(0)
    // ⚠ And it says what it is measuring — the replay cost is not optional information: `1 + legs`
    // full replays is minutes of work, and the solo control is what separates *the cap bit* from
    // *the shared balance re-sized everything*.
    await expect(page.getByTestId('stack-mode-blurb')).toContainText('nothing is reused')
    await expect(page.getByTestId('stack-mode-blurb')).toContainText('compete for')
  })
})

// ── Chart preferences shared across every page with an equity curve ────────────
//
// Aaron, 2026-08-10: *"Regimes, take it off by default. I don't wanna see the regimes on the
// equity curve — that's the same thing whether I'm on a backtest, a stack, an optimization, a
// tune, all those pages that have equity curves."*
//
// ⚠ There were THREE definitions of this before that day — BacktestDetail's `getOverlayPref`
// (persisted, defaulted ON) plus a bare `useState(true)` on the stack page and another in the
// tuning workbench (neither persisted at all) — so switching it off on two of the three surfaces
// did not even survive a navigation. `useRegimeOverlay` is the single one now.
test.describe('the regime overlay', () => {
  test('is OFF by default on every page that draws an equity curve', async ({ page }) => {
    // MUTATION: flip `useRegimeOverlay`'s stored check back to `!== 'false'` (i.e. default ON), or
    // point either page back at its own `useState(true)` → red.
    // ⚠ The state is read off the pill's own styling, because the bands are drawn INTO the chart
    // and an SVG `ReferenceArea` is not something a locator can count reliably. `aria-pressed`
    // would be better and the pill does not carry one; the accent class is what it has.
    await mock(page, 'shared')
    // ⚠ The pill is gated on the stack HAVING a regime timeline, and the shared fixture ships
    // none — so without this override the check passes on an absent pill, which is the vacuous
    // shape this file already carries three notes about. Registered after `mock` so it wins
    // (Playwright matches the most recently registered route first).
    //
    // ⚠ It is `has_regime_timeline`, NOT a populated `regime_timeline` — the page fetches the
    // stack with `?timeline=false` (the calendar is 43% of that payload and this overlay defaults
    // OFF), so `regime_timeline` is empty on every real response and a fixture that populated it
    // would be testing a shape production never sends.
    await page.route(
      (u) => /\/api\/backtests\/stacks\/st_\w+$/.test(u.pathname),
      (r) =>
        r.fulfill({
          json: { ...stackDetail('shared'), has_regime_timeline: true },
        })
    )
    await page.route(
      (u) => u.pathname.endsWith('/regime-timeline'),
      (r) =>
        r.fulfill({
          json: { regime_timeline: [{ date: '2024-03-01', regime: 'TRENDING' }] },
        })
    )
    await page.goto(`${UI}/backtests/stacks/${SHARED_ID}`)
    const pill = page.getByRole('button', { name: 'Regimes' })
    await expect(pill).toBeVisible()
    await expect(pill).toHaveAttribute('title', 'Show regime bands') // i.e. it is currently OFF

    // ...and the answer PERSISTS, which is the half that never worked on this page: turn it on,
    // reload, and it must still be on. A `useState(true)` would come back on regardless, so this
    // assertion only means anything alongside the default check above.
    await pill.click()
    await expect(pill).toHaveAttribute('title', 'Hide regime bands')
    await page.reload()
    await expect(page.getByRole('button', { name: 'Regimes' })).toHaveAttribute(
      'title',
      'Hide regime bands'
    )
  })
})

// ── The 2026-08-10 audit — five things this page said that were not true ──────
//
// Every check below is a defect that rendered no error. That is the shape this whole page keeps
// producing: a confident sentence, a plausible number, a spinner that never stops.
test.describe('the stack detail audit', () => {
  test('the per-strategy table names the BOOK its dollars came from', async ({ page }) => {
    // MUTATION: drop the `isShared` branch from the table header (back to a plain "Net P&L" with
    // no solo column) → red on the first assertion.
    //
    // 🔴 This is the $47M defect, repeated one section below the Verdict card that was rebuilt to
    // fix it. On a shared stack `net_pnl` is the leg's dollars INSIDE the portfolio, where it
    // sizes off a balance every strategy grew — measured on `st_94aeb25f0c`, one leg reads
    // $47,758,999 here and $21,064 alone, for the identical trades at the identical R. The column
    // said "Net P&L" and nothing else on the row disagreed.
    await mock(page, 'shared')
    await page.goto(`${UI}/backtests/stacks/${SHARED_ID}`)
    const table = page.getByTestId('per-strategy-table')
    await expect(table).toBeVisible()

    // The dollars are named for the book they came from, and BOTH books are on the row.
    await expect(table).toContainText('In this stack')
    await expect(table).toContainText('On its own')
    // The fixture's shared-vs-solo pair for B-LEG: +$2,622 inside the stack, +$500 alone.
    const bleg = table.locator('tr', { hasText: 'B-LEG' })
    await expect(bleg).toContainText('+$2,622')
    await expect(bleg).toContainText('+$500')
    // ⚠ And R leads, because it is the one per-trade figure a change of position size cannot
    // move — the same reasoning that put it at the front of the Verdict card's rows.
    await expect(bleg).toContainText('+6.31R')
  })

  test('a SCREEN keeps the plain column, because there is only one book', async ({ page }) => {
    // MUTATION: render the shared header unconditionally → red.
    // ⚠ The half that stops the fix becoming noise: on a screen every leg already traded its own
    // full account, so "In this stack" and "On its own" are the same number and offering both
    // would invent a distinction that does not exist there.
    await mock(page, 'screen')
    await page.goto(`${UI}/backtests/stacks/${SCREEN_ID}`)
    const table = page.getByTestId('per-strategy-table')
    await expect(table).toContainText('Net P&L')
    await expect(table).not.toContainText('On its own')
  })

  test('an unreplayed COMBINATION never claims there are no completed runs', async ({ page }) => {
    // MUTATION: restore the `!isRunning` empty-state as the fallback for `unmeasured` → red.
    //
    // 🔴 `hasResults` is false on the `unmeasured` basis, so the charts slot rendered "No
    // completed strategy runs to compose" — while the Verdict card two feet above was listing the
    // completed runs and explaining, correctly, that this SUBSET has no book. One screen, two
    // answers, and the false one is the larger.
    //
    // ⚠ `solo: false` is what makes the selection unmeasured rather than solo: with no control
    // book stored, one leg left on is a combination nobody replayed.
    await mock(page, 'shared', undefined, { solo: false })
    await page.goto(`${UI}/backtests/stacks/${SHARED_ID}`)
    const verdict = page.getByTestId('stack-verdict-card')
    await expect(verdict).toBeVisible()
    await verdict.getByText('B-LEG').click()

    await expect(page.getByTestId('unmeasured-card')).toBeVisible()
    await expect(page.getByText('No completed strategy runs to compose')).toHaveCount(0)
    // ⚠ And the way back is still on screen — the reader got here by clicking, so they must be
    // able to click out. This is what the refusal is allowed to cost.
    await expect(verdict).toBeVisible()
  })

  test('a stack that cannot be loaded says so instead of rendering nothing', async ({ page }) => {
    // MUTATION: drop the `isError` block → red.
    // 🔴 `useStack`'s `isError` was never read, so a bad id, a stale bookmark, or a stack deleted
    // in another tab left the back button over an empty page — which is pixel-identical to a page
    // still loading, i.e. the reader waits instead of going back.
    await page.route(
      (u) => /\/api\/backtests\/stacks\/st_\w+$/.test(u.pathname),
      (r) => r.fulfill({ status: 404, json: { detail: "Stack 'st_gone' not found" } })
    )
    await page.goto(`${UI}/backtests/stacks/st_gone`)
    await expect(page.getByTestId('stack-not-found')).toBeVisible()
    await expect(page.getByRole('button', { name: /back to stacks/i })).toBeVisible()
  })

  test('a stack with a FAILED leg stops polling', async ({ page }) => {
    // MUTATION: put the refetch condition back to `completed_strategies < total_strategies` → red.
    //
    // 🔴 A failed leg never completes, so that comparison is permanently true — and this response
    // is MEASURED at 226,036 bytes / 38 ms on the live lab, i.e. ~270 MB an hour for a tab left
    // open on a broken stack, with nothing on screen moving.
    //
    // ⚠ It counts REQUESTS rather than asserting on the DOM: a poll that never stops changes
    // nothing visible, which is exactly why it survived. The window is 8s against a 3s interval,
    // so a still-polling page lands at 3 or 4 and a fixed one stays at 1.
    let fetches = 0
    await page.route(
      (u) => u.pathname.endsWith('/contention'),
      (r) => r.fulfill({ json: sharedReport() })
    )
    await page.route(
      (u) => u.pathname.endsWith('/chart-spec'),
      (r) => r.fulfill({ status: 404, json: { detail: 'no chart in this test' } })
    )
    await page.route(
      (u) => /\/api\/backtests\/stacks\/st_\w+$/.test(u.pathname),
      (r) => {
        fetches++
        const d = stackDetail('shared')
        return r.fulfill({
          json: {
            ...d,
            status: 'partial',
            completed_strategies: 1,
            strategies: [
              d.strategies[0],
              { ...d.strategies[1], status: 'failed_error', error_message: 'boom' },
            ],
          },
        })
      }
    )
    await page.goto(`${UI}/backtests/stacks/${SHARED_ID}`)
    await expect(page.getByTestId('stack-verdict-card')).toBeVisible()
    await page.waitForTimeout(8_000)
    expect(fetches, 'a stack with a failed leg never completes — polling it is unbounded').toBe(1)
  })

  test('an ABANDONED shared replay says it will not arrive', async ({ page }) => {
    // MUTATION: drop the `!running && !progress` branch from `SharedAccountPanel` → red (it falls
    // through to the spinner, which is what it did until 2026-08-10).
    //
    // 🔴 `progress` lives in an IN-PROCESS dict, so a backend restart erases it while
    // `reset_stale_runs` marks the legs crashed. The panel then span "Replaying the strategies on
    // one account…" for ever, over a run that had been dead since the restart — and the poll
    // behind it never stopped either.
    await mock(page, 'shared', {
      stack_id: SHARED_ID,
      available: false,
      progress: null,
      legs: [],
      events: [],
    })
    // Registered AFTER `mock` so it wins — Playwright matches the most recently registered route
    // first, and a counter installed before it is shadowed and never increments.
    let asked = 0
    await page.route(
      (u) => u.pathname.endsWith('/contention'),
      (r) => {
        asked++
        return r.fulfill({
          json: { stack_id: SHARED_ID, available: false, progress: null, legs: [], events: [] },
        })
      }
    )
    await page.goto(`${UI}/backtests/stacks/${SHARED_ID}`)
    const panel = page.getByTestId('shared-account-panel')
    await expect(panel).toContainText('did not finish')
    await expect(panel).toContainText('Rerun the stack')
    // ⚠ And it must NOT be the spinner — asserting only the sentence above would pass against a
    // panel that rendered both.
    await expect(panel).not.toContainText('Replaying the strategies')

    // ⚠ The SECOND half, and it is the one nothing on screen could ever show: the poll behind that
    // spinner never stopped either, because it only ever stood down on `available` or a `failed`
    // phase. A report that will never arrive was requested every 3s for as long as the tab stayed
    // open. MUTATION: drop the `!data.progress && !stackRunning` clause from `useStackContention`
    // → this lands at 3 or 4 instead of 1.
    await page.waitForTimeout(8_000)
    expect(asked, 'nothing is driving this replay — the report will never arrive').toBe(1)
  })
})

// The regime calendar is 43% of the stack payload (96,766 of 226,036 bytes, measured on the live
// stack `st_94aeb25f0c`) and the overlay it feeds defaults OFF — so the common page load has no
// use for it at all. It is fetched separately, only once the reader switches the overlay on.
test.describe('the regime calendar is fetched only when it is wanted', () => {
  test('loading the page asks for the stack WITHOUT its calendar, and never fetches one', async ({
    page,
  }) => {
    // MUTATION: drop `?timeline=false` from `useStack`, or fire `useStackRegimeTimeline` without
    // its `enabled` gate → red on the respective assertion.
    await mock(page, 'shared')
    let calendars = 0
    await page.route(
      (u) => u.pathname.endsWith('/regime-timeline'),
      (r) => {
        calendars++
        return r.fulfill({
          json: { regime_timeline: [{ date: '2024-03-01', regime: 'TRENDING' }] },
        })
      }
    )
    const slim: boolean[] = []
    await page.route(
      (u) => /\/api\/backtests\/stacks\/st_\w+$/.test(u.pathname),
      (r) => {
        slim.push(new URL(r.request().url()).searchParams.get('timeline') === 'false')
        return r.fulfill({ json: { ...stackDetail('shared'), has_regime_timeline: true } })
      }
    )

    await page.goto(`${UI}/backtests/stacks/${SHARED_ID}`)
    // ⚠ Wait on the PAGE having rendered, not on a timer — asserting a request count straight
    // after `goto` is the vacuous shape this file records four times, because zero fetches is also
    // what an unmounted page produces.
    await expect(page.getByRole('button', { name: 'Regimes' })).toBeVisible()

    expect(slim.length).toBeGreaterThan(0)
    expect(slim.every(Boolean)).toBe(true)
    expect(calendars).toBe(0)
  })

  test('switching the overlay on fetches it once, and switching off and on again does not refetch', async ({
    page,
  }) => {
    // MUTATION: remove `staleTime: Infinity` from `useStackRegimeTimeline` → the second toggle
    // refetches and the final count is 2.
    // ⚠ The second half is the one worth having: a finished stack's window is fixed, so the
    // calendar cannot change, and a reader flicking the overlay to compare should not pay for it.
    await mock(page, 'shared')
    let calendars = 0
    await page.route(
      (u) => u.pathname.endsWith('/regime-timeline'),
      (r) => {
        calendars++
        return r.fulfill({
          json: { regime_timeline: [{ date: '2024-03-01', regime: 'TRENDING' }] },
        })
      }
    )
    await page.route(
      (u) => /\/api\/backtests\/stacks\/st_\w+$/.test(u.pathname),
      (r) => r.fulfill({ json: { ...stackDetail('shared'), has_regime_timeline: true } })
    )

    await page.goto(`${UI}/backtests/stacks/${SHARED_ID}`)
    const pill = page.getByRole('button', { name: 'Regimes' })
    await expect(pill).toHaveAttribute('title', 'Show regime bands')
    expect(calendars).toBe(0)

    await pill.click()
    await expect(pill).toHaveAttribute('title', 'Hide regime bands')
    await expect.poll(() => calendars).toBe(1)

    await pill.click()
    await expect(pill).toHaveAttribute('title', 'Show regime bands')
    await pill.click()
    await expect(pill).toHaveAttribute('title', 'Hide regime bands')
    expect(calendars).toBe(1)
  })

  test('a stack with NO calendar offers no overlay control at all', async ({ page }) => {
    // MUTATION: make the page gate on `regime_timeline.length` again → the pill disappears on the
    // check above too, so BOTH go red; gate on nothing → this one goes red alone.
    // ⚠ `has_regime_timeline: false` is a MEASUREMENT — the window was classified and has nothing
    // to show — so offering a toggle that draws nothing would read as a broken overlay.
    await mock(page, 'shared')
    await page.route(
      (u) => /\/api\/backtests\/stacks\/st_\w+$/.test(u.pathname),
      (r) => r.fulfill({ json: { ...stackDetail('shared'), has_regime_timeline: false } })
    )

    await page.goto(`${UI}/backtests/stacks/${SHARED_ID}`)
    // ⚠ Scoped to a control that only exists once the page has rendered its charts, so "absent"
    // cannot be satisfied by the page simply not being there yet.
    await expect(page.getByTestId('per-strategy-table')).toBeVisible()
    await expect(page.getByRole('button', { name: 'Regimes' })).toHaveCount(0)
  })
})

// A shared stack REUSES NOTHING by construction — `routers/stacks.py` refuses to drop a finished
// standalone run, measured un-contended, into a contended portfolio — so the preview can only ever
// come back saying every leg runs. And when a screen's rerun DOES ask, the query key is the whole
// request body, so a body rebuilt on every keystroke fired a POST on every keystroke.
test.describe('the stack preview is only asked when it has something to say', () => {
  test('configuring a NEW (shared) stack never asks for a reuse preview', async ({ page }) => {
    // MUTATION: pass `settingsReady` instead of `askPreview` to `useStackPreview` → red.
    await mock(page, 'shared')
    let previews = 0
    await page.route(
      (u) => u.pathname.endsWith('/stacks/preview'),
      (r) => {
        previews++
        return r.fulfill({ json: { legs: [], reuse_count: 0, run_count: 2 } })
      }
    )
    await page.route(
      (u) => u.pathname.endsWith('/api/strategies'),
      (r) =>
        r.fulfill({
          json: [
            {
              id: 'sos_fade',
              name: 'SOS Fade',
              runner: 'python',
              suggested_instrument: 'XAUUSD',
              param_schema: [],
              default_params: {},
              needs_scan: false,
            },
            {
              id: 'b_leg',
              name: 'B-LEG',
              runner: 'python',
              suggested_instrument: 'XAUUSD',
              param_schema: [],
              default_params: {},
              needs_scan: false,
            },
          ],
        })
    )

    await page.goto(`${UI}/backtests?tab=stacks`)
    await page.getByRole('button', { name: /new stack/i }).click()
    await page.getByRole('button', { name: /SOS Fade/ }).click()
    await page.getByRole('button', { name: /B-LEG/ }).click()

    // ⚠ Wait on the settings genuinely being COMPLETE — the account fields visible with two legs
    // ticked is the state that would have fired the preview. Asserting a count of 0 before that is
    // satisfied by a modal that has not finished opening, which is this file's recorded trap.
    await expect(page.getByTestId('stack-account-fields')).toBeVisible()
    await expect(page.getByTestId('stack-mode-blurb')).toContainText('nothing is reused')
    await page.waitForTimeout(1200) // past the 350ms debounce, several times over
    expect(previews).toBe(0)
  })
})

// ── Round 4 of the stacks audit ────────────────────────────────────────────────────────────
//
// Two defects with no backend surface at all, so a browser check is the only thing that can see
// either of them. Non-vacuity is by MUTATION, named on each check.

test.describe('a leg the reader switched off stays off while the stack finishes', () => {
  /**
   * 🔴 The enabled set was RE-SEEDED from the completed legs on every poll, and a running stack
   * polls every 3s with its legs landing one at a time. So switching a leg off and waiting was
   * the page undoing your click the moment its sibling finished — the exact "a roster DERIVED
   * from data must be RECONCILED, never re-seeded" rule the price chart's `groupsOn` already
   * carries, met again two pages over.
   *
   * MUTATION: replace the reconcile effect in `StackDetail` with
   * `setEnabled(new Set(completeIds ? completeIds.split(',') : []))` and this goes red — the
   * switched-off leg comes back on when the third leg lands.
   *
   * 🔴 THIS CHECK WAS VACUOUS ON ITS FIRST WRITING AND PASSED AGAINST THAT MUTATION, which is
   * the only reason the fixture is this shape. It used TWO legs and toggled after the last one
   * landed — and the effect is keyed on `completeIds`, so with nothing left to finish it never
   * re-ran and the re-seed had no moment to happen in. Two legs cannot express this at all: with
   * one complete you cannot switch it off (the toggle refuses to remove the last leg on), and
   * once both are complete nothing changes again. **The defect needs a leg landing AFTER the
   * reader has answered**, so it needs three.
   */
  test('a third leg finishing does not switch a chosen one back on', async ({ page }) => {
    const THIRD = { run_id: 'r_c', strategy_id: 'bos', strategy_name: 'BOS' }
    let allDone = false
    await page.route(
      (u) => u.pathname.endsWith('/contention'),
      (r) => r.fulfill({ json: sharedReport() })
    )
    await page.route(
      (u) => u.pathname.endsWith('/chart-spec'),
      (r) => r.fulfill({ status: 404, json: { detail: 'no chart in this test' } })
    )
    await page.route(
      (u) => /\/api\/backtests\/stacks\/st_\w+$/.test(u.pathname),
      (r) => {
        const d = stackDetail('shared') as Record<string, unknown>
        const third = leg(THIRD, 900, 3.5, 400)
        d.strategies = [
          ...(d.strategies as unknown[]),
          allDone ? third : { ...third, status: 'running' },
        ]
        d.total_strategies = 3
        d.completed_strategies = allDone ? 3 : 2
        d.status = allDone ? 'complete' : 'running'
        return r.fulfill({ json: d })
      }
    )

    await page.goto(`${UI}/backtests/stacks/${SHARED_ID}`)
    const verdict = page.getByTestId('stack-verdict-card')
    // Two finished, one still replaying. Both finished legs start ON, which is the right default.
    await expect(verdict).toContainText('2 of 3 on')

    // The reader answers: switch the first one off.
    await verdict.getByRole('button', { name: new RegExp(LEGS[0].strategy_name) }).click()
    await expect(verdict).toContainText('1 of 3 on')

    // 🔴 The third leg lands. This is the moment `completeIds` changes, i.e. the only moment the
    // re-seed could ever have fired — and the observation is that the answer already given
    // SURVIVES it while the newly-finished leg comes on by itself: 1 chosen + 1 new = 2 of 3.
    // A re-seed reads 3 of 3.
    allDone = true
    await expect.poll(async () => verdict.innerText(), { timeout: 15_000 }).toContain('of 3 on')
    await expect(verdict).toContainText('2 of 3 on')
  })
})

test.describe('a stack says what it was replayed with', () => {
  /**
   * 🔴 A single backtest has carried its params in a side panel since the day it existed and a
   * stack had them NOWHERE — which left one class of value invisible: a param the STACK pinned.
   * The backend forces `exec_secondary: false` onto every shared leg before it replays, so the
   * run genuinely differs from the strategy's own default for a reason nothing on screen said.
   *
   * MUTATION: drop the `params` field from the leg fixture (or the Settings block from
   * `StackDetail`) and this goes red.
   */
  test('each leg lists the settings it ran with, including a pinned one', async ({ page }) => {
    await page.route(
      (u) => u.pathname.endsWith('/contention'),
      (r) => r.fulfill({ json: sharedReport() })
    )
    await page.route(
      (u) => u.pathname.endsWith('/chart-spec'),
      (r) => r.fulfill({ status: 404, json: { detail: 'no chart in this test' } })
    )
    await page.route(
      (u) => /\/api\/backtests\/stacks\/st_\w+$/.test(u.pathname),
      (r) => {
        const d = stackDetail('shared')
        d.strategies = d.strategies.map((s) => ({
          ...s,
          // `exec_secondary` is the PINNED one: the strategy's own default is true and a shared
          // leg cannot run it, so this is the value that exists nowhere else on the page.
          params: { exec_secondary: false, exec_risk_pct: 10 },
        }))
        return r.fulfill({ json: d })
      }
    )

    await page.goto(`${UI}/backtests/stacks/${SHARED_ID}`)
    const settings = page.getByTestId('stack-settings')
    await expect(settings).toBeVisible()

    // Open the first leg's disclosure and read the pinned value.
    await settings.locator('summary').first().click()
    await expect(settings).toContainText('exec_secondary')
    // 🔴 `false` must RENDER. A boolean dropped as falsy, or printed as an em-dash, would hide
    // exactly the pinned value this section exists to show — and it would look like a tidy
    // empty cell rather than a missing fact.
    await expect(settings.getByText('false', { exact: true }).first()).toBeVisible()
  })
})
