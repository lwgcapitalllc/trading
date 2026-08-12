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

/**
 * A registry row's defaults, so a check states only the field it is about.
 *
 * ⚠ `has_password: true` here is a fixture convenience — three checks below are specifically
 * about the OTHER two states, and each overrides it.
 */
export function reg(over: Record<string, unknown> = {}) {
  return {
    account: ACCOUNT, label: 'PU Prime ECN demo', broker: 'PU Prime', tier: 'ECN',
    kind: 'demo', server: 'PUPrime-Demo', mt5_path: 'C:\\MT5_FFT\\terminal64.exe',
    symbol_suffix: '.p', account_profile: 'puprime_ecn', note: '',
    assignable: true, unassignable_reason: '', has_password: true, bot_keys: [],
    ...over,
  }
}

/**
 * ⚠ **`registry` defaults to EMPTY, which is what keeps every pre-registry check unchanged** —
 * an account a bot names but nobody registered still renders, with its gap named. It must also be
 * routed rather than left to `route.fallback()`: the registry endpoint asks the VPS whether a
 * password is stored, so an unmocked one would reach the live box from a unit check.
 */
async function mock(page: Page, groups: unknown[], registry: unknown[] = []) {
  await page.route('**/*', async route => {
    const u = new URL(route.request().url())
    if (u.pathname === '/api/bots/accounts/registry') {
      return route.fulfill({ json: registry })
    }
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
    // The page reads this for the Users tab's count chip, on every tab. Routed so the count is a
    // fixture rather than whoever happens to be in `users.json` on this machine.
    if (u.pathname === '/api/bots/users') {
      return route.fulfill({
        json: [
          { name: 'Aaron', chat_id: '1', role: 'admin', added: '2026-01-01' },
          { name: 'Brother', chat_id: '2', role: 'readonly', added: '2026-01-01' },
        ],
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
  // ⚠ Scoped to the RAIL and then to the DETAIL, because since the tab became master–detail
  // (2026-08-12) `data-kind` is on both — a bare `[data-kind="bench"]` matches two elements and
  // the strict-mode violation reads as a missing card rather than a duplicated one.
  const railBench = page.locator('[data-testid="account-rail-item"][data-kind="bench"]')
  await expect(railBench).toHaveCount(1)
  await railBench.click()
  const card = page.locator('[data-testid="account-card"][data-kind="bench"]')
  await expect(card).toContainText('Not on an account')
  // No cap editor on the bench: there is no account for a ceiling to describe.
  await expect(card.getByTestId('cap-save')).toHaveCount(0)
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

// ── The account REGISTRY — added 2026-08-12 ───────────────────────────────────
//
// 🔴 These cover the gap that made moving the live bot to the ECN demo a manual afternoon: the
// grouping is DERIVED from instance configs, which is right, and it could therefore only ever see
// accounts a bot was already on — so the first bot onto a new account had nothing to be moved to.

test('a registered account with NO bots is a card you can add one to', async ({ page }) => {
  // MUTATION: drop `registered` from the card list in AccountsTab (render only `groups`) → red.
  // This is the whole point of the registry; before it, this account did not exist on the page.
  await mock(page, [], [reg()])
  await page.goto('/bots?tab=accounts')

  await expect(page.getByTestId('account-card')).toHaveCount(1)
  await expect(page.getByTestId('no-bots')).toContainText('No bot trades this account yet')
  await expect(page.getByTestId('add-bot')).toBeEnabled()
})

test('an account with no terminal cannot be added to, and says why', async ({ page }) => {
  // MUTATION: make `assignable` always true in bot_account_registry → Add bot enables and this
  // goes red. A bot assigned to an account no terminal is logged into would be written,
  // committed, pushed and pulled, and THEN fail at connect() with a message about credentials —
  // pointing the reader at the password rather than at the missing terminal.
  await mock(page, [], [reg({
    mt5_path: '', assignable: false,
    unassignable_reason: 'account 700107749 has no terminal on the VPS logged into it',
  })])
  await page.goto('/bots?tab=accounts')

  await expect(page.getByTestId('no-terminal')).toBeVisible()
  await expect(page.getByTestId('add-bot')).toBeDisabled()
  await expect(page.getByTestId('no-bots')).toContainText('Log a terminal into it')
})

test('a password the VPS could not be asked about reads UNKNOWN, never "no password"',
  async ({ page }) => {
    // MUTATION: in routers/bots._registration, return `entry.account in (with_password or set())`
    // instead of the three-state → this reads "No password" and goes red.
    //
    // ⚠ Both halves are asserted, and the second is what makes it bite: a check for the presence
    // of "Password unknown" alone would pass against a chip that ALSO said no password somewhere.
    // Rendering an unanswered question as a missing credential sends the reader to re-enter one
    // that is already there, and refuses a move that would have worked.
    await mock(page, [], [reg({ has_password: null })])
    await page.goto('/bots?tab=accounts')

    const chip = page.getByTestId('password-chip')
    await expect(chip).toContainText('Password unknown')
    await expect(chip).not.toContainText('No password')
  })

test('an account with no stored password says so before you try to move a bot onto it',
  async ({ page }) => {
    // The backend refuses the move (409) on a DEFINITE no; this is the same fact stated before
    // the click rather than after it.
    await mock(page, [], [reg({ has_password: false })])
    await page.goto('/bots?tab=accounts')
    await expect(page.getByTestId('password-chip')).toContainText('No password')
  })

test('adding an account sends the SYMBOL SUFFIX, which is the field the ECN move forgot',
  async ({ page }) => {
    // MUTATION: drop `symbol_suffix` from the AccountForm submit body → red on the last assertion.
    //
    // This is the field that, left behind on 2026-08-12, would have pointed the bot at XAUUSD.s on
    // an ECN book that does not quote it — connecting cleanly, warming up, and receiving no bars.
    let body: Record<string, unknown> | null = null
    await mock(page, [], [])
    await page.route('**/api/bots/accounts/registry/**', async route => {
      if (route.request().method() !== 'PUT') return route.fallback()
      body = route.request().postDataJSON()
      return route.fulfill({ json: reg({ account: 700152905 }) })
    })

    await page.goto('/bots?tab=accounts')
    await page.getByTestId('add-account').click()
    await page.getByTestId('f-account').fill('700152905')
    await page.getByTestId('f-server').fill('PUPrime-Demo')
    await page.getByTestId('f-suffix').fill('.p')
    await page.getByTestId('f-profile').fill('puprime_ecn')
    await page.getByTestId('save-account').click()

    await expect.poll(() => body).not.toBeNull()
    expect(body!.account).toBe(700152905)
    expect(body!.server).toBe('PUPrime-Demo')
    expect(body!.symbol_suffix).toBe('.p')
  })

test('an unticked suffix box sends NULL, not an empty string', async ({ page }) => {
  // MUTATION: send `symbol_suffix: suffix` unconditionally → this sends "" and goes red.
  //
  // ⚠ They are different answers and collapsing them is destructive. `""` means this broker
  // quotes BARE symbols, so a move would rewrite XAUUSD.s → XAUUSD; `null` means nobody recorded
  // it, so the move leaves the symbol alone and says so. The empty string is the one that
  // silently strips a suffix off a live instrument.
  let body: Record<string, unknown> | null = null
  await mock(page, [], [])
  await page.route('**/api/bots/accounts/registry/**', async route => {
    if (route.request().method() !== 'PUT') return route.fallback()
    body = route.request().postDataJSON()
    return route.fulfill({ json: reg() })
  })

  await page.goto('/bots?tab=accounts')
  await page.getByTestId('add-account').click()
  await page.getByTestId('f-account').fill('700152905')
  await page.getByTestId('f-server').fill('PUPrime-Demo')
  await page.getByTestId('f-has-suffix').uncheck()
  await page.getByTestId('save-account').click()

  await expect.poll(() => body).not.toBeNull()
  expect(body!.symbol_suffix).toBeNull()
})

test('an account a bot still trades cannot be unregistered', async ({ page }) => {
  // MUTATION: drop the `group.bots.length > 0` guard → the button enables and this goes red.
  // The bot would go on trading an account this page can no longer describe.
  await mock(page, [group({ bots: [bot('mpc_sos_fade', 'MPC SOS Fade', 770115, null)] })], [reg()])
  await page.goto('/bots?tab=accounts')
  await expect(page.getByTestId(`unregister-${ACCOUNT}`)).toBeDisabled()
})

test('an account nobody registered still renders, with the gap named', async ({ page }) => {
  // Backwards compatibility, and it is the half that keeps the registry from being a wall: the
  // account still works, and the reader is told what this page cannot do with it.
  await mock(page, [group({ bots: [bot('mpc_sos_fade', 'MPC SOS Fade', 770115, null)] })], [])
  await page.goto('/bots?tab=accounts')
  await expect(page.getByTestId('unregistered')).toBeVisible()
  await expect(page.getByTestId('password-chip')).toHaveCount(0)
})

/**
 * Drag a bot's row out of the detail pane onto another account in the RAIL.
 *
 * ⚠ **The rail is the drop target since the tab became master–detail (2026-08-12), and it had to
 * be**: only one account's card is on screen at a time, so a card-to-card drag can no longer
 * reach a destination. The rail is the one surface that always shows every account.
 *
 * ⚠ **It fires the SAME mutation Add bot and the Move menu fire**, so what is checked here is the
 * GESTURE reaching that mutation with the right account — not a second write path, which is
 * exactly what this must never grow into.
 */
async function dragBotOnto(page: Page, botKey: string, railIndex: number) {
  // ⚠ **Wait for BOTH ends before dispatching.** `page.evaluate` runs the moment the document
  // exists, so a `querySelector(...)!` on a row React has not rendered yet throws — and that
  // failure is a null-reference inside the harness, which reads exactly like the drop handler
  // being missing. It passed alone and failed in a full run, i.e. purely on how loaded the box was.
  await page.getByTestId(`bot-row-${botKey}`).waitFor()
  await page.getByTestId('account-rail-item').nth(railIndex).waitFor()
  // HTML5 drag-and-drop is dispatched by hand rather than with `dragTo`: Playwright's helper is
  // unreliable across the mouse-move heuristics, and what this check is about is the DATA the drop
  // carries, which the manual events model exactly.
  await page.evaluate(({ botKey, railIndex }) => {
    const row = document.querySelector(`[data-testid="bot-row-${botKey}"]`)!
    const target = document.querySelectorAll('[data-testid="account-rail-item"]')[railIndex]!
    const dt = new DataTransfer()
    row.dispatchEvent(new DragEvent('dragstart', { dataTransfer: dt, bubbles: true }))
    target.dispatchEvent(new DragEvent('dragover', { dataTransfer: dt, bubbles: true }))
    target.dispatchEvent(new DragEvent('drop', { dataTransfer: dt, bubbles: true }))
  }, { botKey, railIndex })
}

test('dragging a bot onto another account moves it there', async ({ page }) => {
  // MUTATION: drop the `onDrop` handler from the card → no request is made and this goes red.
  const OTHER = 700152905
  let moved: { url: string; body: Record<string, unknown> } | null = null

  await mock(page,
    [group({ bots: [bot('mpc_bleg', 'MPC B-LEG', 770116, null)] })],
    [reg({ account: ACCOUNT }), reg({ account: OTHER, label: 'ECN' })])
  await page.route('**/api/bots/*/account', async route => {
    moved = { url: route.request().url(), body: route.request().postDataJSON() }
    return route.fulfill({
      json: { status: 'ok', changed: true, bot: 'mpc_bleg', account: OTHER,
              restart_required: true, notes: [] },
    })
  })

  await page.goto('/bots?tab=accounts')
  await expect(page.getByTestId('account-rail-item')).toHaveCount(2)
  await dragBotOnto(page, 'mpc_bleg', 1)

  await expect.poll(() => moved).not.toBeNull()
  expect(moved!.url).toContain('/bots/mpc_bleg/account')
  expect(moved!.body.account).toBe(OTHER)
})

test('a RUNNING bot cannot be dragged at all', async ({ page }) => {
  // MUTATION: make `draggable` unconditional → the attribute reads "true" and this goes red.
  //
  // It read its config at startup, so a write cannot reach the live process — the page would show
  // it under one account while it went on trading another. Same guard as the Remove button, and
  // the backend refuses it with a 409 regardless; this is it stated before the gesture.
  await mock(page,
    [group({ bots: [bot('mpc_sos_fade', 'MPC SOS Fade', 770115, null)] })], [reg()])
  await page.goto('/bots?tab=accounts')
  await expect(page.getByTestId('bot-row-mpc_sos_fade')).toHaveAttribute('draggable', 'false')
})

test('an account with no terminal refuses the drop rather than reporting it afterwards',
  async ({ page }) => {
    // MUTATION: drop the `registration?.assignable === false` early return in onDragOver → the
    // card highlights and this goes red.
    //
    // ⚠ Only `preventDefault` on dragover makes an element a valid drop target, so declining to
    // call it IS the refusal — the cursor says no while the row is still being held. Asserting the
    // highlight is what makes that observable: `data-dropping` is set in the same handler.
    const OTHER = 700152905
    await mock(page,
      [group({ bots: [bot('mpc_bleg', 'MPC B-LEG', 770116, null)] })],
      [reg({ account: ACCOUNT }),
       reg({ account: OTHER, mt5_path: '', assignable: false,
             unassignable_reason: 'no terminal on the VPS logged into it' })])

    await page.goto('/bots?tab=accounts')
    // Same race as `dragBotOnto` — see the note there.
    await page.getByTestId('bot-row-mpc_bleg').waitFor()
    await page.getByTestId('account-rail-item').nth(1).waitFor()
    await page.evaluate(() => {
      const row = document.querySelector('[data-testid="bot-row-mpc_bleg"]')!
      const target = document.querySelectorAll('[data-testid="account-rail-item"]')[1]!
      const dt = new DataTransfer()
      row.dispatchEvent(new DragEvent('dragstart', { dataTransfer: dt, bubbles: true }))
      target.dispatchEvent(new DragEvent('dragover', { dataTransfer: dt, bubbles: true }))
    })

    const rail = page.getByTestId('account-rail-item')
    await expect(rail.nth(1)).not.toHaveAttribute('data-dropping', 'true')
  })

// ── The rail, and the Move menu that makes a move discoverable ─────────────────
//
// 🔴 Added 2026-08-12 with the master–detail rebuild. Aaron, off the screen: *"the more accounts I
// add, it's just gonna keep scrolling up and down… I can't tell easily what bot is trading on what
// account… I don't see an easy way to add bots or remove bots from accounts."*

test('the rail lists every account and only ONE detail pane is on screen', async ({ page }) => {
  // MUTATION: render the entries as a stack of cards again (drop the rail/detail split) → the
  // detail-pane count goes to 3 and this goes red. One pane is the property that keeps the page a
  // fixed height however many accounts are registered.
  await mock(page, [group({ bots: [bot('mpc_sos_fade', 'MPC SOS Fade', 770115, 10)] })], [
    reg({ account: ACCOUNT, broker: 'PU Prime', tier: 'Standard' }),
    reg({ account: 700152905, broker: 'PU Prime', tier: 'ECN' }),
    reg({ account: 700119432, broker: 'PU Prime', tier: 'Prime' }),
  ])
  await page.goto('/bots?tab=accounts')

  await expect(page.getByTestId('account-rail-item')).toHaveCount(3)
  await expect(page.getByTestId('account-card')).toHaveCount(1)

  // ⚠ Identity is asserted on the RAIL, because that is what the rebuild was for: broker, then
  // number, then tier, in that order, so an account can be picked out of a list of them.
  const first = page.getByTestId('account-rail-item').first()
  await expect(first).toContainText('PU Prime')
  await expect(first).toContainText(`#${ACCOUNT}`)
  await expect(first).toContainText('Standard')
})

test('picking an account in the rail swaps the detail pane and survives a reload',
  async ({ page }) => {
    // MUTATION: hold the selection in `useState` instead of `?account=` → the reload lands back on
    // the first account and this goes red. A selection that dies on refresh is one the reader has
    // to re-make every time they come back to the tab.
    await mock(page, [], [
      reg({ account: ACCOUNT, broker: 'PU Prime', tier: 'Standard' }),
      reg({ account: 700152905, broker: 'Vantage', tier: 'ECN' }),
    ])
    await page.goto('/bots?tab=accounts')

    await expect(page.getByTestId('account-card')).toContainText(`#${ACCOUNT}`)
    await page.getByTestId('account-rail-item').nth(1).click()
    await expect(page.getByTestId('account-card')).toContainText('#700152905')
    await expect(page.getByTestId('account-card')).toContainText('Vantage')

    await page.reload()
    await expect(page.getByTestId('account-card')).toContainText('#700152905')
  })

test('the Move menu moves a bot, and lists an unassignable account DISABLED', async ({ page }) => {
  // MUTATION: drop the `<select>` and leave drag as the only route → red. Dragging is the fast
  // path and nothing on screen advertises it; a move has to be reachable with a trackpad.
  //
  // ⚠ The disabled option is the second half and is not decoration: hiding an account with no
  // terminal makes one that exists look like one that does not, which is the same rule the Add bot
  // list follows for a running bot.
  const OTHER = 700152905
  const NO_TERM = 700119432
  let moved: Record<string, unknown> | null = null

  await mock(page,
    [group({ bots: [bot('mpc_bleg', 'MPC B-LEG', 770116, null)] })],
    [reg({ account: ACCOUNT }),
     reg({ account: OTHER, broker: 'PU Prime', tier: 'ECN' }),
     reg({ account: NO_TERM, mt5_path: '', assignable: false,
           unassignable_reason: 'no terminal on the VPS logged into it' })])
  await page.route('**/api/bots/*/account', async route => {
    moved = route.request().postDataJSON()
    return route.fulfill({
      json: { status: 'ok', changed: true, bot: 'mpc_bleg', account: OTHER,
              restart_required: true, notes: [] },
    })
  })

  await page.goto('/bots?tab=accounts')
  const menu = page.getByTestId('move-mpc_bleg')
  await expect(menu.locator(`option[value="${NO_TERM}"]`)).toBeDisabled()
  await expect(menu.locator(`option[value="${ACCOUNT}"]`)).toHaveCount(0)  // it is already here

  await menu.selectOption(String(OTHER))
  await expect.poll(() => moved).toEqual({ account: OTHER, deploy: true })
})

test('a RUNNING bot cannot be moved from the menu either', async ({ page }) => {
  // MUTATION: drop `running` from the select's `disabled` → it enables and this goes red.
  // The Remove button beside it has always been guarded; a second control that is not is a way
  // round the guard rather than a convenience.
  await mock(page,
    [group({ bots: [bot('mpc_sos_fade', 'MPC SOS Fade', 770115, null)] })],
    [reg({ account: ACCOUNT }), reg({ account: 700152905 })])
  await page.goto('/bots?tab=accounts')
  await expect(page.getByTestId('move-mpc_sos_fade')).toBeDisabled()
})

test('the tab chips carry the counts, so "how many accounts" is answered without opening the tab', async ({ page }) => {
  // MUTATION: return `registry.length` alone from `useAccountCount` → the chip reads 2 and this
  // goes red on the unregistered account nobody counted.
  // The fixture has to carry an UNREGISTERED account or the mutation cannot bite — two registered
  // rows count 2 whichever way the hook is written.
  await mock(page,
    [group({ bots: [bot('mpc_sos_fade', 'MPC SOS Fade', 770115, null)] }),
     group({ account: 700152905, bots: [] })],           // a bot names it, nobody registered it
    [reg({ account: ACCOUNT }), reg({ account: 700119432 })])

  await page.goto('/bots?tab=monitor')
  // Read from the MONITOR tab on purpose: the whole point of a count on the chip is that it is
  // readable from somewhere else.
  await expect(page.getByTestId('tab-count-accounts')).toHaveText('3')
  await expect(page.getByTestId('tab-count-users')).toHaveText('2')
})

test('a bot row opens that bot on Configure — the tab that answers a different question', async ({ page }) => {
  // MUTATION: drop the Configure button from the row → this goes red on the locator.
  // The two tabs are one journey: this one decides WHICH account, that one decides how the bot
  // trades on it, and nothing on the page said so before.
  await mock(page,
    [group({ bots: [bot('mpc_sos_fade', 'MPC SOS Fade', 770115, null)] })],
    [reg({ account: ACCOUNT })])
  await page.goto('/bots?tab=accounts')

  await page.getByTestId('configure-mpc_sos_fade').click()
  await expect.poll(() => new URL(page.url()).searchParams.get('tab')).toBe('configure')
  expect(new URL(page.url()).searchParams.get('bot')).toBe('mpc_sos_fade')
})

test('the rail and the detail pane are the same height and both reach the bottom of the page', async ({ page }) => {
  // MUTATION: drop the measured height (`style={undefined}` on the shell) → the panes fall back
  // to their own content and the two differ by 216px, red on the first assertion.
  // ⚠ `items-stretch` alone is NOT what makes this pass and the comment must not claim it is —
  // swapping it for `items-start` leaves the check green, because the shell has an explicit height
  // and each pane carries `h-full`. Measured, not reasoned about.
  // Aaron: "make the site navigation where all the accounts are the height of the page. Also make
  // the details on the right the same height of the page."
  await mock(page,
    [group({ bots: [bot('mpc_sos_fade', 'MPC SOS Fade', 770115, null)] })],
    [reg({ account: ACCOUNT })])
  await page.goto('/bots?tab=accounts')
  await expect(page.getByTestId('account-card')).toBeVisible()

  const rail = (await page.getByTestId('account-rail-item').first()
    .locator('xpath=ancestor::div[contains(@class,"rounded-lg")][1]').boundingBox())!
  const card = (await page.getByTestId('account-card').boundingBox())!
  const view = page.viewportSize()!

  expect(Math.abs(rail.height - card.height)).toBeLessThan(2)
  expect(Math.abs(rail.y - card.y)).toBeLessThan(2)
  // …and the bottom edge is the bottom of the page, not wherever the content ended.
  expect(view.height - (card.y + card.height)).toBeLessThan(40)
})

test('the Accounts tab renders while the VPS snapshot is still loading', async ({ page }) => {
  // 🔴 WATCHED RED against HEAD: the Monitor tab's loading skeleton was ungated, so opening
  // Accounts drew ~400px of fake Monitor cards above it until the VPS answered — and the accounts
  // list needs no VPS at all. The observable is where the card SITS, because the skeleton has no
  // testid and pushing the pane down is the whole damage.
  let release: () => void = () => {}
  const held = new Promise<void>(r => { release = r })
  await mock(page,
    [group({ bots: [bot('mpc_sos_fade', 'MPC SOS Fade', 770115, null)] })],
    [reg({ account: ACCOUNT })])
  await page.route('**/api/bots/snapshot', async route => {
    await held
    await route.fulfill({
      json: {
        fetched_at: new Date().toISOString(),
        bots: [], scheduled_jobs: [], telegram: { name: 'Telegram', status: 'RUNNING' },
      },
    })
  })

  await page.goto('/bots?tab=accounts')
  const card = page.getByTestId('account-card')
  await expect(card).toBeVisible()
  expect((await card.boundingBox())!.y).toBeLessThan(200)
  // The State column says `—` while the snapshot is unanswered, which is the honest reading —
  // never "Stopped".
  await expect(page.getByTestId('bot-row-mpc_sos_fade')).toContainText('—')
  release()
})
