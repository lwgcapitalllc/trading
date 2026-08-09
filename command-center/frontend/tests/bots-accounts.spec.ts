import { test, expect, Page } from '@playwright/test'

/**
 * The Bots page's Accounts tab — which bots share a balance, and the ceiling over it.
 *
 * ⚠ **Mocked whole, so this needs no VPS.** The real `/bots/snapshot` SSHes to the live trading
 * box; `/bots/accounts` does not, but the page renders both, and the states worth checking here
 * (two bots on one account, a cap disagreement, an unreadable config) cannot be produced on
 * demand against a one-bot fleet.
 *
 * ⚠ **Routes match on `u.pathname` against the `/api` prefix**, never on `http://localhost:8000`.
 * The app fetches through the Vite proxy (`api/client.ts` → `const BASE = '/api'`), so a mock
 * keyed on the backend's own origin matches NOTHING and the check silently reads the live lab —
 * three checks in `stacks.spec.ts` did exactly that.
 *
 * ⚠ **A fail-watch against HEAD is vacuous for this tab** (it did not exist), so non-vacuity is
 * by MUTATION and each check names its own.
 */

const ACCOUNT = 700107749

function bot(key: string, display: string, magic: number, cap: number | null, risk = 10) {
  return {
    key, display, symbol: 'XAUUSD.s', magic,
    strategy_package: key, risk_pct: risk, cap_pct: cap, unreadable: false,
  }
}

async function mock(page: Page, groups: unknown[]) {
  await page.route('**/*', async route => {
    const u = new URL(route.request().url())
    if (u.pathname === '/api/bots/accounts') {
      return route.fulfill({ json: groups })
    }
    if (u.pathname === '/api/bots/snapshot') {
      return route.fulfill({
        json: {
          fetched_at: new Date().toISOString(),
          bots: [
            { key: 'mpc_sos_fade', name: 'MPC SOS Fade', status: 'RUNNING', account_type: 'demo' },
            { key: 'mpc_bleg', name: 'MPC B-LEG', status: 'STOPPED', account_type: 'demo' },
          ],
          scheduled_jobs: [],
          telegram: { name: 'Telegram', status: 'RUNNING' },
        },
      })
    }
    return route.fallback()
  })
}

const STACKED = [{
  account: ACCOUNT, server: 'PUPrime-Demo',
  bots: [bot('mpc_sos_fade', 'MPC SOS Fade', 770115, 10),
         bot('mpc_bleg', 'MPC B-LEG', 770116, 10)],
  risk_cap_pct: 10, cap_agrees: true, cap_unknown: false,
  stacked: true, cap_takes_turns: true,
}]

test('two bots on one account render as one stacked card', async ({ page }) => {
  // MUTATION: make `stacked` false in the payload → the chip disappears and this goes red.
  await mock(page, STACKED)
  await page.goto('/bots?tab=accounts')
  await expect(page.getByTestId('account-card')).toHaveCount(1)
  await expect(page.getByTestId('stacked-chip')).toContainText('Stacked · 2')
})

test('a cap equal to the per-trade risk says the bots take turns', async ({ page }) => {
  // This is the fact neither number states on its own, and it is why 10% is not "both may hold
  // 10%". MUTATION: drop `cap_takes_turns` from the payload → red.
  await mock(page, STACKED)
  await page.goto('/bots?tab=accounts')
  await expect(page.getByTestId('cap-takes-turns')).toContainText('take turns')
})

test('a cap disagreement is named and no cap is quoted', async ({ page }) => {
  // The dangerous shape: one capped bot beside one uncapped one. The uncapped bot fills the
  // account freely while the capped one is refused, so the guard only handicaps the bot that
  // was configured correctly. MUTATION: report `risk_cap_pct: 10` with `cap_agrees: false` →
  // the chip would quote a ceiling nobody configured and the `Cap 10%` assertion below flips.
  await mock(page, [{
    ...STACKED[0],
    bots: [bot('mpc_sos_fade', 'MPC SOS Fade', 770115, 10),
           bot('mpc_bleg', 'MPC B-LEG', 770116, null)],
    risk_cap_pct: null, cap_agrees: false, cap_takes_turns: false,
  }])
  await page.goto('/bots?tab=accounts')
  await expect(page.getByTestId('cap-disagreement')).toBeVisible()
  await expect(page.getByTestId('cap-chip')).toContainText('disagreement')
  await expect(page.getByTestId('cap-chip')).not.toContainText('Cap 10%')
})

test('an unreadable config blocks the save rather than writing to the rest', async ({ page }) => {
  // Writing the cap to three of four configs leaves exactly the disagreement the whole thing
  // exists to prevent, and it would report success.
  // MUTATION: drop the `group.cap_unknown` clause from the button's `disabled` → red.
  await mock(page, [{
    ...STACKED[0],
    bots: [bot('mpc_sos_fade', 'MPC SOS Fade', 770115, 10),
           { key: 'broken', display: 'broken', symbol: '', magic: 0, strategy_package: '',
             risk_pct: null, cap_pct: null, unreadable: true }],
    cap_unknown: true,
  }])
  await page.goto('/bots?tab=accounts')
  await expect(page.getByTestId('cap-save')).toBeDisabled()
})

test('saving a cap says a restart is needed, never that it applied', async ({ page }) => {
  // A written cap is not a running cap — it is read by the order bridge at startup only. This is
  // the one state that reads as protected and is not.
  // MUTATION: drop `restart_required` from the toast wording → red.
  await mock(page, STACKED)
  let sent: Record<string, unknown> | null = null
  await page.route('**/*', async route => {
    const u = new URL(route.request().url())
    if (u.pathname === `/api/bots/accounts/${ACCOUNT}/risk-cap`) {
      sent = route.request().postDataJSON()
      return route.fulfill({
        json: { status: 'ok', changed: true, deployed: true, updated: ['mpc_sos_fade', 'mpc_bleg'],
                restart_required: true, bots: ['mpc_sos_fade', 'mpc_bleg'],
                detail: `account ${ACCOUNT} risk cap → 20%` },
      })
    }
    return route.fallback()
  })

  await page.goto('/bots?tab=accounts')
  await page.getByTestId('cap-input').fill('20')
  await page.getByTestId('cap-save').click()

  await expect(page.getByText(/restart them to apply/i)).toBeVisible()
  expect(sent).toEqual({ risk_cap_pct: 20, deploy: true })
})

test('clearing the cap sends null, which means uncapped rather than unchanged', async ({ page }) => {
  // There is deliberately no separate clear action, so the absent value keeps meaning one thing.
  // MUTATION: send `0` instead of `null` → the backend refuses it (0 blocks every order) and the
  // request body assertion goes red.
  await mock(page, STACKED)
  let sent: Record<string, unknown> | null = null
  await page.route('**/*', async route => {
    const u = new URL(route.request().url())
    if (u.pathname === `/api/bots/accounts/${ACCOUNT}/risk-cap`) {
      sent = route.request().postDataJSON()
      return route.fulfill({
        json: { status: 'ok', changed: true, updated: ['mpc_sos_fade'], restart_required: true,
                bots: ['mpc_sos_fade'], detail: 'uncapped' },
      })
    }
    return route.fallback()
  })

  await page.goto('/bots?tab=accounts')
  await page.getByTestId('cap-enabled').uncheck()
  await page.getByTestId('cap-save').click()
  await expect.poll(() => sent).toEqual({ risk_cap_pct: null, deploy: true })
})

test('the monitor row carries a Stacked chip', async ({ page }) => {
  // Aaron's ask: from the page that shows which bots are running, a stacked account has to be
  // visible without opening another tab.
  // MUTATION: make `stacked` false on the group → both rows lose the chip and this goes red.
  await mock(page, STACKED)
  await page.goto('/bots?tab=monitor')
  await expect(page.getByTestId('row-stacked-chip')).toHaveCount(2)
})

test('a single-bot account shows no stacked chip anywhere', async ({ page }) => {
  // The chip must not become decoration. MUTATION: render it whenever the group exists → red.
  await mock(page, [{
    account: ACCOUNT, server: 'PUPrime-Demo',
    bots: [bot('mpc_sos_fade', 'MPC SOS Fade', 770115, 10)],
    risk_cap_pct: 10, cap_agrees: true, cap_unknown: false,
    stacked: false, cap_takes_turns: false,
  }])
  await page.goto('/bots?tab=monitor')
  await expect(page.getByTestId('row-stacked-chip')).toHaveCount(0)
  await page.goto('/bots?tab=accounts')
  await expect(page.getByTestId('stacked-chip')).toHaveCount(0)
})
