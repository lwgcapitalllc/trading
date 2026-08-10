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

/** A group's defaults, so a check states only the field it is about. */
function group(over: Record<string, unknown> = {}) {
  return {
    account: ACCOUNT, server: 'PUPrime-Demo', kind: 'account',
    bots: [], risk_cap_pct: null, cap_agrees: true, cap_unknown: false,
    stacked: false, cap_takes_turns: false, magic_clash: [],
    ...over,
  }
}

async function mock(page: Page, groups: unknown[]) {
  await page.route('**/*', async route => {
    const u = new URL(route.request().url())
    if (u.pathname === '/api/bots/accounts') {
      return route.fulfill({ json: groups })
    }
    // Every bot's version, keyed by bot in the path. The Monitor and Accounts tables both
    // render a VersionPill off this, and without the mock they would fall through to the live
    // backend, which SSHes to the VPS.
    const v = u.pathname.match(/^\/api\/bots\/([^/]+)\/version$/)
    if (v) {
      return route.fulfill({
        json: {
          frozen: true, hash: 'abc', commit: 'c0ffee', promoted_at: '2026-08-05',
          strategy_package: 'p', strategy_class: 'C', strategy_version: 0, files: 3,
          params: {}, repo_commit: 'dead', commits_ahead: 0, snapshot_ok: true,
          running_hash: 'abc', params_drift: [],
          compare: v[1] === 'mpc_bleg' ? null : {
            deployed_version: 100, local_version: 121, versions_behind: 21,
            uncommitted_files: [], comparable: true, reason: '',
            changes: [], setting_changes: [],
          },
        },
      })
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

const STACKED = [group({
  bots: [bot('mpc_sos_fade', 'MPC SOS Fade', 770115, 10),
         bot('mpc_bleg', 'MPC B-LEG', 770116, 10)],
  risk_cap_pct: 10, stacked: true, cap_takes_turns: true,
})]

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
  await mock(page, [group({
    bots: [bot('mpc_sos_fade', 'MPC SOS Fade', 770115, 10),
           bot('mpc_bleg', 'MPC B-LEG', 770116, null)],
    risk_cap_pct: null, cap_agrees: false, stacked: true,
  })])
  await page.goto('/bots?tab=accounts')
  await expect(page.getByTestId('cap-disagreement')).toBeVisible()
  await expect(page.getByTestId('cap-chip')).toContainText('disagreement')
  await expect(page.getByTestId('cap-chip')).not.toContainText('Cap 10%')
})

test('an unreadable config blocks the save rather than writing to the rest', async ({ page }) => {
  // Writing the cap to three of four configs leaves exactly the disagreement the whole thing
  // exists to prevent, and it would report success.
  // MUTATION: drop the `group.cap_unknown` clause from the button's `disabled` → red.
  await mock(page, [group({
    bots: [bot('mpc_sos_fade', 'MPC SOS Fade', 770115, 10),
           { key: 'broken', display: 'broken', symbol: '', magic: 0, strategy_package: '',
             risk_pct: null, cap_pct: null, unreadable: true }],
    risk_cap_pct: 10, cap_unknown: true, stacked: true,
  })])
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
  await mock(page, [group({
    bots: [bot('mpc_sos_fade', 'MPC SOS Fade', 770115, 10)],
    risk_cap_pct: 10,
  })])
  await page.goto('/bots?tab=monitor')
  await expect(page.getByTestId('row-stacked-chip')).toHaveCount(0)
  await page.goto('/bots?tab=accounts')
  await expect(page.getByTestId('stacked-chip')).toHaveCount(0)
})


// ── add / remove, the bench, and the version pill (2026-08-09) ────────────────
//
// Aaron: *"I don't see no ability to say, like, add bot… Same thing if I wanna remove a bot from
// account, I can remove it, and the next one could just continue."* Removing has to land
// somewhere, and that somewhere is the BENCH — `account: null`, a bot registered and trading
// nothing, which is a state and not a deletion.

const BENCHED = group({
  account: null, server: '', kind: 'bench',
  bots: [bot('mpc_bleg', 'MPC B-LEG', 770116, null)],
})

test('a benched bot gets its own card, not the unreadable one', async ({ page }) => {
  // MUTATION: render `kind: 'bench'` and `kind: 'unknown'` with one heading → red.
  // One is a state somebody chose and the other is a broken file; the same card would give a
  // broken config the same controls as a resting bot.
  await mock(page, [
    group({ bots: [bot('mpc_sos_fade', 'MPC SOS Fade', 770115, 10)], risk_cap_pct: 10 }),
    BENCHED,
  ])
  await page.goto('/bots?tab=accounts')
  await expect(page.locator('[data-testid="account-card"][data-kind="bench"]')).toHaveCount(1)
  await expect(page.locator('[data-kind="bench"]')).toContainText('Not on an account')
  // No cap editor on the bench: there is no account for a ceiling to describe.
  await expect(page.locator('[data-kind="bench"] [data-testid="cap-save"]')).toHaveCount(0)
})

test('a benched bot is offered as something to add, and says where it comes from',
  async ({ page }) => {
    // MUTATION: build the candidate list from the account's own bots → the list is empty and the
    // "nothing to add" message renders instead.
    await mock(page, [
      group({ bots: [bot('mpc_sos_fade', 'MPC SOS Fade', 770115, 10)], risk_cap_pct: 10 }),
      BENCHED,
    ])
    await page.goto('/bots?tab=accounts')
    await page.locator('[data-kind="account"] [data-testid="add-bot"]').click()
    await expect(page.getByTestId('add-mpc_bleg')).toBeVisible()
    await expect(page.getByTestId('add-mpc_bleg')).toContainText('not on an account')
  })

test('adding a bot sends its key and the account it is joining', async ({ page }) => {
  await mock(page, [
    group({ bots: [bot('mpc_sos_fade', 'MPC SOS Fade', 770115, 10)], risk_cap_pct: 10 }),
    BENCHED,
  ])
  let sent: Record<string, unknown> | null = null
  await page.route('**/*', async route => {
    const u = new URL(route.request().url())
    if (u.pathname === '/api/bots/mpc_bleg/account') {
      sent = route.request().postDataJSON()
      return route.fulfill({
        json: { status: 'ok', changed: true, deployed: true, bot: 'mpc_bleg',
                account: ACCOUNT, restart_required: true, detail: 'moved' },
      })
    }
    return route.fallback()
  })

  await page.goto('/bots?tab=accounts')
  await page.locator('[data-kind="account"] [data-testid="add-bot"]').click()
  await page.getByTestId('add-mpc_bleg').click()
  await expect.poll(() => sent).toEqual({ account: ACCOUNT, deploy: true })
  // Never "added and trading" — a bot reads its account at startup.
  await expect(page.getByText(/start it to trade/i)).toBeVisible()
})

test('removing a bot sends null, which is the bench rather than a delete', async ({ page }) => {
  // MUTATION: send `0` or omit the field → the backend would read a missing body as no change,
  // and `0` is not an account. `null` is the only spelling of "on no account".
  await mock(page, STACKED)
  let sent: Record<string, unknown> | null = null
  await page.route('**/*', async route => {
    const u = new URL(route.request().url())
    if (u.pathname === '/api/bots/mpc_bleg/account') {
      sent = route.request().postDataJSON()
      return route.fulfill({
        json: { status: 'ok', changed: true, deployed: true, bot: 'mpc_bleg',
                account: null, restart_required: true, detail: 'benched' },
      })
    }
    return route.fallback()
  })

  await page.goto('/bots?tab=accounts')
  await page.getByTestId('remove-mpc_bleg').click()
  await expect.poll(() => sent).toEqual({ account: null, deploy: true })
  await expect(page.getByText(/will not start until it is on one again/i)).toBeVisible()
})

test('a RUNNING bot cannot be removed from its account', async ({ page }) => {
  // MUTATION: drop `running` from the button's `disabled` → red. Its config was read at startup,
  // so the write cannot reach the live process: the page would show it under one account while
  // it went on trading another.
  await mock(page, STACKED)   // the snapshot mock has mpc_sos_fade RUNNING, mpc_bleg STOPPED
  await page.goto('/bots?tab=accounts')
  await expect(page.getByTestId('remove-mpc_sos_fade')).toBeDisabled()
  await expect(page.getByTestId('remove-mpc_bleg')).toBeEnabled()
})

test('an account with nothing left to add says so instead of an empty list', async ({ page }) => {
  // MUTATION: render the picker unconditionally → an empty box with no explanation, which reads
  // as a broken control rather than as an answer.
  await mock(page, STACKED)
  await page.goto('/bots?tab=accounts')
  await page.getByTestId('add-bot').click()
  await expect(page.getByTestId('no-candidates')).toContainText('already on this account')
})

test('the magic clash is named only when there is one', async ({ page }) => {
  // The fact the raw `magic` column was trying to convey, shown when it matters and never
  // otherwise. MUTATION: render the banner whenever the group exists → the healthy case fails.
  await mock(page, [group({
    bots: [bot('a', 'A', 770115, 10), bot('b', 'B', 770115, 10)],
    risk_cap_pct: 10, stacked: true, magic_clash: ['a', 'b'],
  })])
  await page.goto('/bots?tab=accounts')
  await expect(page.getByTestId('magic-clash')).toContainText('share an order tag')

  await mock(page, STACKED)
  await page.goto('/bots?tab=accounts')
  await expect(page.getByTestId('magic-clash')).toHaveCount(0)
})

test('there is no raw magic column left to misread', async ({ page }) => {
  // Aaron: *"I don't know what the column magic even means."* It is gone, replaced by the
  // clash banner above — so this asserts the header is absent AND that the number is too.
  await mock(page, STACKED)
  await page.goto('/bots?tab=accounts')
  await expect(page.locator('th', { hasText: /^Magic$/ })).toHaveCount(0)
  await expect(page.getByTestId('account-card')).not.toContainText('770115')
})

test('the version pill reports the DEPLOYED version and how far behind it is',
  async ({ page }) => {
    // MUTATION: render `local_version` instead → it shows v121 and this goes red. v121 is the
    // backtester's and is running nowhere; the number a fleet row must answer for is the box's.
    await mock(page, STACKED)
    await page.goto('/bots?tab=accounts')
    const pill = page.locator('[data-testid="version-pill"][data-state="behind"]').first()
    await expect(pill).toContainText('v100')
    await expect(pill).toContainText('21 behind')
  })

test('a bot whose version cannot be worked out says so rather than showing a number',
  async ({ page }) => {
    // MUTATION: fall back to `v0` → red. `v0` is the reassuring answer to a question nobody
    // could answer, and this pill is what you check before deciding anything.
    await mock(page, STACKED)   // the version mock returns compare: null for mpc_bleg
    await page.goto('/bots?tab=accounts')
    await expect(page.locator('[data-testid="version-pill"][data-state="unknown"]'))
      .toHaveCount(1)
    await expect(page.locator('[data-testid="version-pill"][data-state="unknown"]'))
      .toContainText('No version')
  })

test('the monitor page carries the same version pill', async ({ page }) => {
  // Aaron asked for it on both pages, from one component, so the two cannot disagree.
  await mock(page, STACKED)
  await page.goto('/bots?tab=monitor')
  await expect(page.locator('th', { hasText: /^Version$/ })).toHaveCount(1)
  await expect(page.locator('[data-testid="version-pill"]')).toHaveCount(2)
})
