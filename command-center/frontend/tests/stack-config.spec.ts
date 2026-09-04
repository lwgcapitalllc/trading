/**
 * The stack form's broker, cost switch and per-leg risk — added 2026-09-02.
 *
 * The single-run form has carried all three for weeks and this one had none of them, so a stack
 * fell through to the two typed cost figures (which default to zero) and every leg ran its stored
 * default risk. **Every stack this lab has produced is therefore a GROSS number**, and the one
 * question a shared account exists to ask — how the balance is divided between the legs — had no
 * control on the page at all.
 *
 * ⚠ Every response is INTERCEPTED, so this suite needs only the dev server — no backend, no SSH
 * tunnel, no live MT5 box. That is the shape this folder prefers wherever a page allows it, and
 * it matters here: booting the backend is a person's decision because it can start things on the
 * trading box.
 *
 * ⚠ A fail-watch against HEAD is VACUOUS for all of these — none of these controls existed, so
 * every check would go red on an element being absent, which proves the locator and nothing else.
 * **Non-vacuity is by MUTATION, named in a comment on each check.**
 *
 * ⚠ Every locator is scoped to the modal. The page behind it carries its own buttons, and a
 * page-wide `getByRole` matching one of those is the vacuous pass this folder has now recorded
 * five times.
 */
import { test, expect, type Page } from '@playwright/test'

const UI = 'http://localhost:5173'

/**
 * Two profiles, and the SECOND one is attached.
 *
 * ⚠ The order is the point: the form falls back to the first profile only when nothing is
 * attached, so a fixture whose attached profile is also first cannot tell a working default from
 * `useState(profiles[0])` — and `vantage_demo` as a hardcoded literal is exactly what this
 * replaces on the single-run form.
 */
const PROFILES = [
  {
    id: 'vantage_demo',
    spread: 0.22,
    commission_per_side_per_lot: 0,
    swap_long_points: null,
    swap_short_points: null,
    contract_size: 100,
    server: 'VantageInternational-Demo',
    account: 111,
    symbol_suffix: '',
    attached: false,
  },
  {
    id: 'puprime_ecn',
    spread: 0.12,
    commission_per_side_per_lot: 1,
    swap_long_points: -12,
    swap_short_points: 26.98,
    contract_size: 100,
    server: 'PUPrime-Demo',
    account: 700152905,
    symbol_suffix: '.p',
    attached: true,
  },
]

/**
 * A leg whose stored settings are MORE THAN the one field the risk box edits.
 *
 * 🔴 This is the whole point of the fixture. The backend reads
 * `params_by_strategy[id] OR the strategy's defaults` — never both — so an override carrying only
 * the edited field runs that leg with ONE setting and silently drops every other. Nothing fails:
 * the leg replays, produces trades, and lands in the table looking ordinary.
 */
const STRATEGIES = [
  {
    id: 'sos_fade',
    name: 'SOS Fade',
    runner: 'python',
    suggested_instrument: 'XAUUSD',
    default_params: { exec_risk_pct: 10, exec_sl_deep: true, exec_tp1_pct: 40 },
    param_schema: [],
  },
  {
    id: 'extreme_leg',
    name: 'Extreme Leg',
    runner: 'python',
    suggested_instrument: 'XAUUSD',
    default_params: { exec_risk_pct: 1, exec_tp1_pct: 50 },
    param_schema: [],
  },
]

/**
 * ⚠ Route on `u.pathname` against the `/api` PREFIX, never on an `http://localhost:8000` string.
 * The app fetches through the Vite proxy (`api/client.ts` → `const BASE = '/api'`), so a route
 * keyed on the backend's own origin matches NOTHING and the page quietly reads the live lab.
 */
async function mock(page: Page, opts: { profiles?: typeof PROFILES } = {}) {
  const launches: Record<string, unknown>[] = []
  const previews: Record<string, unknown>[] = []

  await page.route(
    (u) => u.pathname.endsWith('/api/strategies'),
    (r) => r.fulfill({ json: STRATEGIES })
  )
  await page.route(
    (u) => u.pathname.endsWith('/api/backtests/broker-profiles'),
    (r) => r.fulfill({ json: opts.profiles ?? PROFILES })
  )
  await page.route(
    (u) => u.pathname.endsWith('/api/backtests/running-job'),
    (r) =>
      r.fulfill({
        json: {
          nt8: { running: false },
          mt5: { running: false },
          python: { running: false },
        },
      })
  )
  await page.route(
    (u) => u.pathname.includes('/api/backtests/history-limit'),
    (r) => r.fulfill({ json: null })
  )
  // ONE existing stack, so the header's "New stack" button renders (the empty state has its own).
  await page.route(
    (u) => u.pathname.endsWith('/api/backtests/stacks'),
    (r) =>
      r.fulfill({
        json: [
          {
            stack_id: 'st_existing1',
            instrument: 'XAUUSD',
            start_date: '2024-01-01',
            end_date: '2024-12-31',
            total_strategies: 2,
            completed_strategies: 2,
            failed_strategies: 0,
            status: 'complete',
            created_at: '2026-09-01T10:00:00Z',
            strategy_names: 'SOS Fade + Extreme Leg',
            mode: 'shared',
            risk_cap_pct: 10,
          },
        ],
      })
  )
  await page.route(
    (u) => u.pathname.endsWith('/api/backtests/stacks/preview'),
    async (r) => {
      previews.push(JSON.parse(r.request().postData() ?? '{}'))
      await r.fulfill({ json: { legs: [], reuse_count: 0, run_count: 2 } })
    }
  )
  await page.route(
    (u) => u.pathname.endsWith('/api/backtests/stack'),
    async (r) => {
      launches.push(JSON.parse(r.request().postData() ?? '{}'))
      await r.fulfill({
        status: 202,
        json: { stack_id: 'st_new00001', run_ids: [], status: 'running' },
      })
    }
  )
  // Everything the page renders AROUND the modal — never the modal's own data.
  await page.route(
    (u) => u.pathname.includes('/api/') && !u.pathname.endsWith('/api/backtests/stack'),
    (r) => r.fallback()
  )
  return { launches, previews }
}

/** Open the Stacks tab and the New-stack modal, and return the modal's own root. */
async function openModal(page: Page) {
  await page.goto(`${UI}/backtests?tab=stacks`)
  await page.getByRole('button', { name: /New stack/i }).click()
  const modal = page.locator('[data-testid="stack-broker"]').locator('xpath=ancestor::div[3]')
  await expect(page.getByTestId('stack-broker')).toBeVisible()
  return modal
}

/** Fill in the two things the form needs before it will submit, and tick both legs. */
async function fillForm(page: Page) {
  await page.getByRole('button', { name: /SOS Fade/ }).click()
  await page.getByRole('button', { name: /Extreme Leg/ }).click()
  const instrument = page.getByPlaceholder('e.g. XAUUSD')
  await expect(instrument).toHaveValue('XAUUSD')
}

test.describe('the stack form carries a broker, a cost switch and per-leg risk', () => {
  /**
   * MUTATION: drop the `attached` branch from the defaulting effect (fall back to `profiles[0]`)
   * and this goes red — it reads `vantage_demo`, which is also the literal the single-run form
   * used to hardcode.
   */
  test('the broker defaults to the ATTACHED terminal, not the first profile', async ({ page }) => {
    await mock(page)
    await openModal(page)
    await expect(page.getByTestId('stack-broker').locator('select')).toHaveValue('puprime_ecn')
  })

  /**
   * The load-bearing check. MUTATION: drop `charge_costs` from `previewBody` and this goes red on
   * the launch assertion, which is the one that decides whether a stack is priced.
   *
   * ⚠ It asserts the POSITIVE control first — that the switch reads as charging — so a form that
   * simply failed to render the toggle cannot pass the body assertion by accident.
   */
  test('a stack is CHARGED by default, and says which account it is charged on', async ({
    page,
  }) => {
    const { launches } = await mock(page)
    await openModal(page)
    await expect(page.getByTestId('stack-costs')).toContainText(/Charge this account's real costs/)

    await fillForm(page)
    await page.getByRole('button', { name: /Run stack/ }).click()
    await expect.poll(() => launches.length).toBe(1)
    expect(launches[0].charge_costs).toBe(true)
    expect(launches[0].broker_profile).toBe('puprime_ecn')
  })

  /**
   * MUTATION: drop `charge_costs` from the switch's `onClick` state (pin it `true`) and this goes
   * red — the body still says charged while the page says gross.
   */
  test('turning costs OFF warns, and the launch really is gross', async ({ page }) => {
    const { launches } = await mock(page)
    await openModal(page)
    await page.getByTestId('stack-costs').getByRole('switch').click()
    await expect(page.getByTestId('stack-costs')).toContainText(/gross figure/i)

    await fillForm(page)
    await page.getByRole('button', { name: /Run stack/ }).click()
    await expect.poll(() => launches.length).toBe(1)
    expect(launches[0].charge_costs).toBe(false)
  })

  /**
   * A tier whose spread has never been measured refuses at the backend rather than borrowing a
   * sibling's number — PU Prime's tiers measured 2.7x apart. Said before the click, not as a 400
   * after it.
   *
   * MUTATION: drop the `!(chargeCosts && brokerUnpriced)` clause from `canRun` and this goes red
   * on the disabled assertion.
   */
  test('an unpriced broker blocks the run and says so before the click', async ({ page }) => {
    await mock(page, {
      profiles: [{ ...PROFILES[1], id: 'puprime_prime', spread: -1, attached: true }],
    })
    await openModal(page)
    await fillForm(page)
    await expect(page.getByTestId('stack-costs')).toContainText(/never been measured/i)
    await expect(page.getByRole('button', { name: /Run stack/ })).toBeDisabled()
  })

  /**
   * 🔴 THE ONE THAT PINS THE TRAP. An override REPLACES a leg's whole settings — the backend reads
   * `params_by_strategy[id] OR the defaults`, never both — so sending only the edited field would
   * run that leg with ONE setting and silently drop every other.
   *
   * MUTATION: send `{ [RISK_FIELD]: edited }` instead of `{ ...base, [RISK_FIELD]: edited }` and
   * this goes red on the two sibling settings, while the risk assertion above it stays green —
   * which is exactly the shape of the defect.
   */
  test('an edited leg sends its COMPLETE settings, not just the field that moved', async ({
    page,
  }) => {
    const { launches } = await mock(page)
    await openModal(page)
    await fillForm(page)

    // Scoped by the risk box's own step/min, so the account Balance and Risk-cap inputs above
    // cannot be picked up instead — a page-wide spinbutton locator is the vacuous pass this
    // folder has recorded five times.
    const risk = page.locator('input[type="number"][step="0.5"][min="0.1"]').first()
    await expect(risk).toHaveValue('10') // the leg's stored default, before any edit
    await risk.fill('5')

    await page.getByRole('button', { name: /Run stack/ }).click()
    await expect.poll(() => launches.length).toBe(1)
    const byStrategy = launches[0].params_by_strategy as Record<string, Record<string, unknown>>
    expect(byStrategy.sos_fade.exec_risk_pct).toBe(5)
    // The two settings the reader never touched must survive the override.
    expect(byStrategy.sos_fade.exec_sl_deep).toBe(true)
    expect(byStrategy.sos_fade.exec_tp1_pct).toBe(40)
  })

  /**
   * An override DISABLES reuse for that leg, so a form that pre-filled every leg's risk would
   * silently turn every screen rerun into a full replay.
   *
   * MUTATION: drop the `edited !== baseline` guard from the params memo and this goes red — every
   * leg arrives carrying an override nobody asked for.
   */
  test('an untouched leg sends NO override at all', async ({ page }) => {
    const { launches } = await mock(page)
    await openModal(page)
    await fillForm(page)
    await page.getByRole('button', { name: /Run stack/ }).click()
    await expect.poll(() => launches.length).toBe(1)
    expect(launches[0].params_by_strategy).toEqual({})
  })
})
