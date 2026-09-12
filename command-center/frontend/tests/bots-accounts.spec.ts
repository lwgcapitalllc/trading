import { expect, Page } from '@playwright/test'
import { offlineTest } from './offline'

const { test } = offlineTest('bots-page', { clockFactor: 10 })

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
    key,
    display,
    symbol: 'XAUUSD.s',
    magic,
    strategy_package: key,
    risk_pct: risk,
    cap_pct: cap,
    unreadable: false,
  }
}

/** A group's defaults, so a check states only the field it is about. */
function group(over: Record<string, unknown> = {}) {
  return {
    account: ACCOUNT,
    server: 'PUPrime-Demo',
    kind: 'account',
    bots: [],
    risk_cap_pct: null,
    cap_agrees: true,
    cap_unknown: false,
    stacked: false,
    cap_takes_turns: false,
    // `null` = the shares could not be totalled, which is the safe default for a fixture: a
    // number here would be a second statement of the sum the backend computes, and it would go
    // stale the moment a check changed its bots. A check about the total states it.
    share_total_pct: null,
    share_overflow_reason: null,
    magic_clash: [],
    ...over,
  }
}

/**
 * The server's answer to "would this budget fit?" — `POST /bots/accounts/{a}/risk-plan`. Defaults to
 * FITS, so a check about adding or saving states the refusal it is about rather than inheriting one.
 */
function plan(over: Record<string, unknown> = {}) {
  return {
    account: ACCOUNT,
    fits: true,
    reason: null,
    refused: null,
    risk_cap_pct: 10,
    cap_changed: false,
    share_total_pct: null,
    room_pct: null,
    bots: [],
    changed: true,
    fit_cap: null,
    fit_shares: null,
    applies: 'Each bot picks this up the next time it has no open trade — no restart.',
    written: [],
    deployed: null,
    detail: '',
    ...over,
  }
}

/** One terminal on the box, so the drawer has a list to draw. */
const TERMINAL = {
  key: 'c:\\mt5_scalper',
  install: 'C:\\MT5_Scalper',
  state: 'probed',
  running: true,
  owned_by_bots: [],
  account: 34957946,
  server: 'PUPrime-Live',
  kind: 'live',
  company: 'PU Prime Ltd',
  currency: 'USD',
  leverage: 500,
  symbol_suffix: '.p',
  symbol_suffix_how: null,
  reason: null,
  error: null,
  account_source: 'terminal',
  verdict: 'known',
  conflicts: [],
  suggested: null,
}

/**
 * What the scan says Sync WOULD change — the drawer's first answer, and a read. Defaults to "the
 * list already matches". `plan_id` is what a press sends back; a check about it states its own.
 */
function preview(over: Record<string, unknown> = {}) {
  return {
    asked: true,
    scanned_at: new Date().toISOString(),
    reason: null,
    terminals: [TERMINAL],
    registry: [],
    changes: [],
    attention: [],
    blocked: null,
    plan_id: 'plan-a',
    ...over,
  }
}

/** What one Sync press did. `now` is the list re-judged after it — a preview in its own right. */
function syncResult(over: Record<string, unknown> = {}) {
  return {
    now: preview(),
    changes: [],
    failed: [],
    plan_changed: false,
    deployed: false,
    deploy_error: null,
    ...over,
  }
}

/** A live account the box is logged into and the list does not have. An ADD has no "was". */
const ADD_LIVE = {
  account: 34957946,
  action: 'add',
  label: '',
  diffs: [
    { what: 'Server', before: null, after: 'PUPrime-Live', why: 'Read off MT5_Scalper.' },
    { what: 'Demo or live', before: null, after: 'live', why: 'The broker says so.' },
  ],
  said: [
    'Logged in on MT5_Scalper and not in your list. It arrives with no terminal or password, so no bot can use it until you add both.',
  ],
  live: true,
}

/** A row claiming a terminal that is logged into something else — the case that started this. */
const CLEAR_TERMINAL = {
  account: 700107749,
  action: 'update',
  label: 'retired',
  diffs: [
    {
      what: 'Terminal',
      before: 'MT5_FFT',
      after: 'none',
      why: 'MT5_FFT is logged into #700152905, not this account.',
    },
  ],
  said: ['No bot can be put on this account until you give it a terminal again.'],
  live: false,
}

/**
 * Route the scan (a GET) and the sync (a POST) from a script, and COUNT both. The count is the
 * point: *"sync is 100% manually triggered by me only"*, so a check about who writes has to see
 * every request, not just the last answer.
 *
 * ⚠ Registered AFTER `mock()`, so it wins — Playwright matches the most recent handler first.
 */
async function routeSync(
  page: Page,
  opts: {
    scan?: (n: number) => Record<string, unknown> | 'fail'
    sync?: (body: Record<string, unknown>, n: number) => Record<string, unknown> | 'fail'
  } = {}
) {
  const seen = { scans: 0, syncs: 0, bodies: [] as Record<string, unknown>[] }
  const fail = { status: 502, json: { detail: 'ssh to forexvps failed' } }
  await page.route('**/api/bots/accounts/scan', (route) => {
    seen.scans += 1
    const r = opts.scan ? opts.scan(seen.scans) : preview()
    return route.fulfill(r === 'fail' ? fail : { json: r })
  })
  await page.route('**/api/bots/accounts/registry/sync', (route) => {
    seen.syncs += 1
    const body = route.request().postDataJSON() as Record<string, unknown>
    seen.bodies.push(body)
    const r = opts.sync ? opts.sync(body, seen.syncs) : syncResult()
    return route.fulfill(r === 'fail' ? fail : { json: r })
  })
  return seen
}

/**
 * A registry row's defaults, so a check states only the field it is about.
 *
 * ⚠ `has_password: true` here is a fixture convenience — three checks below are specifically
 * about the OTHER two states, and each overrides it.
 */
export function reg(over: Record<string, unknown> = {}) {
  return {
    account: ACCOUNT,
    label: 'PU Prime ECN demo',
    broker: 'PU Prime',
    tier: 'ECN',
    kind: 'demo',
    server: 'PUPrime-Demo',
    mt5_path: 'C:\\MT5_FFT\\terminal64.exe',
    symbol_suffix: '.p',
    account_profile: 'puprime_ecn',
    note: '',
    assignable: true,
    unassignable_reason: '',
    has_password: true,
    bot_keys: [],
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
  // FIRST, so it sits UNDER this spec's own handlers and only ever sees what they fell through
  // on. `route.fallback()` below is allow-by-default, and this backend writes to the live box.
  await page.route('**/*', async (route) => {
    const u = new URL(route.request().url())
    if (u.pathname === '/api/bots/accounts/registry') {
      return route.fulfill({ json: registry })
    }
    if (u.pathname === '/api/bots/accounts') {
      return route.fulfill({ json: groups })
    }
    // The budget PLAN — a question that writes nothing. Answered "fits" by default, so a panel that
    // asks it (an edit, an Add bot list, a move) is not failed by the offline harness for an
    // unrouted request; a check about a refusal routes its own answer over this.
    const rp = u.pathname.match(/^\/api\/bots\/accounts\/(\d+)\/risk-plan$/)
    if (rp) {
      return route.fulfill({ json: plan({ account: Number(rp[1]) }) })
    }
    // Adding an account starts from the Sync VPS drawer, which SCANS on opening — and the real
    // scan SSHes to the trading box and attaches to its terminals, while the real sync COMMITS.
    // Both routed to "nothing to change"; a check about either routes its own answer over these.
    if (u.pathname === '/api/bots/accounts/registry/sync') {
      return route.fulfill({ json: syncResult() })
    }
    if (u.pathname === '/api/bots/accounts/scan') {
      return route.fulfill({ json: preview() })
    }
    // Every bot's latest deploy, which the page watches for the row's version pill. `null` is
    // "no deploy run" — left to the real backend, a deploy somebody ran there today would turn a
    // pill in these checks into "deploying".
    if (
      /^\/api\/bots\/[^/]+\/promote\/job$/.test(u.pathname) &&
      route.request().method() === 'GET'
    ) {
      return route.fulfill({ json: null })
    }
    // Every bot's version, keyed by bot in the path. The Monitor and Accounts tables both
    // render a VersionPill off this, and without the mock they would fall through to the live
    // backend, which SSHes to the VPS.
    const v = u.pathname.match(/^\/api\/bots\/([^/]+)\/version$/)
    if (v) {
      return route.fulfill({
        json: {
          frozen: true,
          hash: 'abc',
          commit: 'c0ffee',
          promoted_at: '2026-08-05',
          strategy_package: 'p',
          strategy_class: 'C',
          strategy_version: 0,
          files: 3,
          params: {},
          repo_commit: 'dead',
          commits_ahead: 0,
          snapshot_ok: true,
          running_hash: 'abc',
          params_drift: [],
          compare:
            v[1] === 'b_leg'
              ? null
              : {
                  deployed_version: 100,
                  local_version: 121,
                  versions_behind: 21,
                  uncommitted_files: [],
                  comparable: true,
                  reason: '',
                  changes: [],
                  setting_changes: [],
                },
        },
      })
    }
    // One bot's own settings, which the BOT drawer needs before it renders anything you can act
    // on — the account selector included. Routed rather than left to fall through, because the
    // real endpoint reads an instance config off the live trading box.
    const p = u.pathname.match(/^\/api\/bots\/([^/]+)\/params$/)
    if (p) {
      return route.fulfill({
        json: {
          bot_key: p[1],
          display_name: p[1],
          identity: {
            account: ACCOUNT,
            server: 'PUPrime-Demo',
            symbol: 'XAUUSD.p',
            timeframe: 'M15',
            mt5_path: 'C:\\MT5_FFT\\terminal64.exe',
            magic: 770115,
          },
          version: {
            strategy_package: p[1],
            strategy_class: 'C',
            strategy_version: 1,
            strategy_source_hash: 'abc',
            promoted_commit: 'c0ffee',
            promoted_at: '2026-08-05',
          },
          runtime: [],
          strategy: [],
          notes: {},
          readme: null,
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
            { key: 'sos_fade', name: 'SOS Fade', status: 'RUNNING', account_type: 'demo' },
            { key: 'b_leg', name: 'B-LEG', status: 'STOPPED', account_type: 'demo' },
          ],
          scheduled_jobs: [],
          telegram: { name: 'Telegram', status: 'RUNNING' },
        },
      })
    }
    return route.fallback()
  })
}

/**
 * Open one account's drawer — where the ceiling and every warning about it now live.
 *
 * 🔴 **These checks used to reach the same controls through `?tab=accounts`, and that tab stopped
 * existing on 2026-09-05** when the four tabs collapsed into one list plus a drawer. The page
 * ignores the parameter entirely, so every one of them silently landed on the default view and
 * failed looking for a control that was one click away.
 *
 * ⚠ **Going straight to the URL rather than clicking the heading is deliberate.** The drawer is
 * addressed by `?account=`, so a check about the CEILING does not also depend on the heading
 * button's markup — a layout change would otherwise redden a dozen checks that are not about
 * layout, which is most of how this file came to be red in the first place.
 */
/**
 * Open the by-hand account form, which lives inside the Sync VPS drawer since 2026-09-10 — the
 * header's own "Add account" button went, so adding starts from what the box reports.
 */
async function openManualAdd(page: Page) {
  await page.goto('/bots')
  await page.getByTestId('sync-vps').click()
  await page.getByTestId('add-account').click()
}

async function openAccount(page: Page, account: number = ACCOUNT) {
  await page.goto(`/bots?account=${account}`)
  await expect(page.getByRole('complementary', { name: 'Account settings' })).toBeVisible()
}

// ⚠ Two bots at 10% under a 10% ceiling really IS over-subscribed, so this fixture carries the
// refusal the backend would serve for it. Stating only the shares would describe an account the
// backend cannot produce, which is a fixture more capable than production.
const STACKED = [
  group({
    bots: [bot('sos_fade', 'SOS Fade', 770115, 10), bot('b_leg', 'B-LEG', 770116, 10)],
    risk_cap_pct: 10,
    stacked: true,
    cap_takes_turns: true,
    share_total_pct: 20,
    share_overflow_reason:
      'the risk shares on this account add up to 20%, which is more than its 10% ceiling',
  }),
]

test('two bots on one account render as ONE card, not one card each', async ({ page }) => {
  // 🔴 The property is that a shared BALANCE is one row — two cards would be two accounts, and
  // this is the shape where a fleet total double-counts. The old `Stacked · 2` chip stated it in
  // words and went on 2026-09-05 with the rest of the per-row counts (Aaron: "I could see two
  // bots are trading… too much duplication"); the card itself is what now carries it, and the
  // drawer names who is on it.
  // MUTATION: group by bot rather than by account → two cards and this goes red.
  await mock(page, STACKED)
  await page.goto('/bots')
  await expect(page.getByTestId('account-card')).toHaveCount(1)
  await openAccount(page)
  await expect(page.getByText('Bots on this balance · 2')).toBeVisible()
})

test('a cap equal to the per-trade risk says the bots take turns', async ({ page }) => {
  // This is the fact neither number states on its own, and it is why 10% is not "both may hold
  // 10%". MUTATION: drop `cap_takes_turns` from the payload → red.
  await mock(page, STACKED)
  await openAccount(page)
  await expect(page.getByTestId('cap-takes-turns')).toContainText('take turns')
})

test('the running total of the shares is on screen beside the ceiling', async ({ page }) => {
  // Splitting a cap between two bots is what this panel is for, and until 2026-09-04 the number
  // being split appeared only in the take-turns note above — which needs the cap to be at or
  // under the largest single share, so the INTENDED configuration never showed it at all.
  // MUTATION: drop `share_total_pct` from the payload → the line says the shares cannot be
  // totalled and this goes red.
  await mock(page, STACKED)
  await openAccount(page)
  await expect(page.getByTestId('cap-shares')).toContainText('20% per trade')
  await expect(page.getByTestId('cap-shares')).toContainText('against 10%')
})

test('an over-subscribed account says so BEFORE anybody saves', async ({ page }) => {
  // The same sentence the write is refused with, served rather than re-derived here — so the
  // page cannot disagree with the save it is standing in front of.
  // MUTATION: drop `share_overflow_reason` from the payload → the banner disappears.
  await mock(page, STACKED)
  await openAccount(page)
  await expect(page.getByTestId('cap-overflow')).toContainText('more than its 10% ceiling')
})

test('shares that cannot be totalled are NOT rendered as a number', async ({ page }) => {
  // 🔴 `null` means a bot's share could not be READ, which is not a share of zero — the page's
  // own reduce used `?? 0` and printed a total that fitted under a cap the backend would refuse.
  // MUTATION: render `null` as 0 → this goes red on the sentence.
  await mock(page, [
    group({
      bots: [bot('sos_fade', 'SOS Fade', 770115, 10), bot('b_leg', 'B-LEG', 770116, 10)],
      risk_cap_pct: 10,
      stacked: true,
      share_total_pct: null,
    }),
  ])
  await openAccount(page)
  await expect(page.getByTestId('cap-shares')).toContainText('cannot be totalled')
  await expect(page.getByTestId('cap-shares')).not.toContainText('0%')
})

test('a cap disagreement is named and no cap is quoted', async ({ page }) => {
  // The dangerous shape: one capped bot beside one uncapped one. The uncapped bot fills the
  // account freely while the capped one is refused, so the guard only handicaps the bot that
  // was configured correctly. MUTATION: report `risk_cap_pct: 10` with `cap_agrees: false` →
  // the chip would quote a ceiling nobody configured and the `Cap 10%` assertion below flips.
  await mock(page, [
    group({
      bots: [bot('sos_fade', 'SOS Fade', 770115, 10), bot('b_leg', 'B-LEG', 770116, null)],
      risk_cap_pct: null,
      cap_agrees: false,
      stacked: true,
    }),
  ])
  await openAccount(page)
  await expect(page.getByTestId('cap-disagreement')).toBeVisible()
  // ⚠ The heading chip is checked on the LIST, not in the drawer — it is the half a reader sees
  // without opening anything, and it is where quoting a ceiling nobody configured would do the
  // damage. The drawer's own field is blank for the same reason, and now says why.
  await page.goto('/bots')
  await expect(page.getByTestId('cap-chip')).toContainText('disagreement')
  await expect(page.getByTestId('cap-chip')).not.toContainText('Cap 10%')
})

test('an unreadable config blocks the save rather than writing to the rest', async ({ page }) => {
  // Writing the cap to three of four configs leaves exactly the disagreement the whole thing
  // exists to prevent, and it would report success.
  // MUTATION: drop the `group.cap_unknown` clause from the button's `disabled` → red.
  await mock(page, [
    group({
      bots: [
        bot('sos_fade', 'SOS Fade', 770115, 10),
        {
          key: 'broken',
          display: 'broken',
          symbol: '',
          magic: 0,
          strategy_package: '',
          risk_pct: null,
          cap_pct: null,
          unreadable: true,
        },
      ],
      risk_cap_pct: 10,
      cap_unknown: true,
      stacked: true,
    }),
  ])
  await openAccount(page)
  await expect(page.getByTestId('cap-save')).toBeDisabled()
})

test('saving a cap says WHEN it applies, and never asks for a restart', async ({ page }) => {
  // 🔴 Re-pointed 2026-09-11. This check used to pin "restart them to apply" — true while the bot
  // read its cap only at startup. A running bot now adopts a new cap the next time it has no open
  // trade (algos/live, RUNTIME_RELOADABLE_ACCOUNT), so that toast would send the reader to restart
  // bots for nothing. The rule underneath is unchanged: the toast says when a write takes effect.
  // MUTATION: drop the server's `applies` sentence from the toast → red on the wording.
  // MUTATION: send the save to the old `/risk-cap` endpoint → nothing answers, red on the body.
  await mock(page, STACKED)
  let sent: Record<string, unknown> | null = null
  await page.route('**/*', async (route) => {
    const u = new URL(route.request().url())
    if (u.pathname === `/api/bots/accounts/${ACCOUNT}/risk`) {
      sent = route.request().postDataJSON()
      return route.fulfill({
        json: plan({
          changed: true,
          cap_changed: true,
          risk_cap_pct: 20,
          written: ['sos_fade', 'b_leg'],
          deployed: true,
          detail: `account ${ACCOUNT} — cap 10% → 20%`,
        }),
      })
    }
    return route.fallback()
  })

  await openAccount(page)
  await page.getByTestId('cap-input').fill('20')
  await page.getByTestId('cap-save').click()

  // ⚠ Scoped to the TOAST: the footer states the same sentence while the edit is on screen, so a
  // page-wide match would pass on the footer and say nothing about what the save reported.
  const toast = page.locator('[data-sonner-toast]').filter({ hasText: /cap 10% → 20%/ })
  await expect(toast).toContainText(/next time it has no open trade/i)
  await expect(page.getByText(/restart them/i)).toHaveCount(0)
  expect(sent).toEqual({ risk_cap_pct: 20, deploy: true })
})

test('clearing the cap sends null, which means uncapped rather than unchanged', async ({
  page,
}) => {
  // There is deliberately no separate clear action, so the absent value keeps meaning one thing.
  // MUTATION: send `0` instead of `null` → the backend refuses it (0 blocks every order) and the
  // request body assertion goes red.
  await mock(page, STACKED)
  let sent: Record<string, unknown> | null = null
  await page.route('**/*', async (route) => {
    const u = new URL(route.request().url())
    if (u.pathname === `/api/bots/accounts/${ACCOUNT}/risk`) {
      sent = route.request().postDataJSON()
      return route.fulfill({
        json: plan({ changed: true, cap_changed: true, risk_cap_pct: null, detail: 'uncapped' }),
      })
    }
    return route.fallback()
  })

  await openAccount(page)
  await page.getByTestId('cap-enabled').uncheck()
  await page.getByTestId('cap-save').click()
  await expect.poll(() => sent).toEqual({ risk_cap_pct: null, deploy: true })
})

// 🔴 **DELETED 2026-09-06: *the fleet groups a stacked account under ONE header* and *a
// single-bot account shows no stacked claim anywhere*.** Both were about a `Stacked · 2` chip,
// and that chip went on 2026-09-05 with the rest of the per-row counts — Aaron: *"I could see two
// is trading… I could see two bots"*, a number restating what the rows already say.
//
// ⚠ **The PROPERTY under them is live and is covered above, not lost**: *two bots on one account
// render as ONE card* asserts the same thing directly (one card, and the drawer naming both bots
// on that balance), which is the never-sum-a-shared-balance rule these were really protecting.
// ⚠ **The second one had become vacuous rather than merely redundant** — it asserted a count of
// ZERO for two testids nothing renders, so it passed against any page at all. **A test whose
// subject no longer exists does not fail; it goes quietly green and reads as coverage.**

test('an old ?tab=monitor link still lands on the fleet', async ({ page }) => {
  // The four tabs became two on 2026-09-04 and then none on 2026-09-05. `?tab=monitor` is in
  // browser history and in links this app built for itself, so it has to land somewhere usable.
  // MUTATION: make an unrecognised parameter render an empty state → red.
  //
  // ⚠ It asserts the LIST, not a tab: the page ignores the parameter entirely now, and asserting
  // on a tab that no longer exists is what left a dozen checks in this file pointed at a page
  // nobody has.
  await mock(page, STACKED)
  await page.goto('/bots?tab=monitor')
  await expect(page.getByTestId('account-card')).toHaveCount(1)
  await expect(page.getByTestId('bot-row')).toHaveCount(2)
})

// ── add / remove, the bench, and the version pill (2026-08-09) ────────────────
//
// Aaron: *"I don't see no ability to say, like, add bot… Same thing if I wanna remove a bot from
// account, I can remove it, and the next one could just continue."* Removing has to land
// somewhere, and that somewhere is the BENCH — `account: null`, a bot registered and trading
// nothing, which is a state and not a deletion.

const BENCHED = group({
  account: null,
  server: '',
  kind: 'bench',
  bots: [bot('b_leg', 'B-LEG', 770116, null)],
})

test('a benched bot is listed apart from one whose config could not be READ', async ({ page }) => {
  // 🔴 WATCHED RED on 2026-09-06 and this was a live defect, not test rot. The rail this used to
  // assert on went with the tabs — but so did the DISTINCTION: the page derived its no-account
  // list from the VPS snapshot alone, so a bot whose instance config could not be parsed landed
  // under *trades nothing until you give it one*. That instruction cannot fix a broken file, and
  // it is the one sentence the reader acts on.
  // MUTATION: fold the unreadable bots back into the unassigned list → the broken row disappears
  // and this goes red on both counts.
  //
  // One is a state somebody chose; the other is a fault. The grouping has always kept them apart
  // — its own type says so — and this page was the only place merging them again.
  await mock(page, [
    group({ bots: [bot('sos_fade', 'SOS Fade', 770115, 10)], risk_cap_pct: 10 }),
    group({
      account: null,
      server: '',
      kind: 'unknown',
      bots: [bot('b_leg', 'B-LEG', 770116, null)],
    }),
  ])
  await page.goto('/bots')

  // ⚠ The fault is on the FIRST tab — it may not sit behind one, since nothing says the bot is
  // not running. MUTATION: move the unreadable block to the Unassigned tab → red here.
  const broken = page.getByTestId('bot-row-broken')
  await expect(broken).toHaveCount(1)
  await expect(broken).toContainText('B-LEG')
  // …and it is NOT offered the control that reads the very file that cannot be read.
  await expect(broken.getByTestId('configure-bot')).toHaveCount(0)
  // The benched list lives on the Unassigned tab since 2026-09-10, so it is asserted THERE —
  // on the Trading tab it is absent whatever the page does, which would make this check vacuous.
  await page.getByTestId('tab-unassigned').click()
  await expect(page.getByText('Nothing is unassigned')).toBeVisible()
  await expect(page.getByTestId('section-no-account')).toHaveCount(0)
})

test('a benched bot IS told to be given an account', async ({ page }) => {
  // The positive control for the check above — without it a page that simply dropped both lists
  // would pass, because an absent row and a correctly-filed one are the same DOM.
  await mock(page, [
    group({ bots: [bot('sos_fade', 'SOS Fade', 770115, 10)], risk_cap_pct: 10 }),
    BENCHED,
  ])
  await page.goto('/bots')
  await expect(page.getByTestId('bot-row-broken')).toHaveCount(0)

  await page.getByTestId('tab-unassigned').click()
  const benched = page.getByTestId('section-no-account')
  await expect(benched).toContainText('trade nothing until you give them one')
  await expect(benched).toContainText('B-LEG')
})

test('only a FREE bot is offered, named with its risk and never its symbol', async ({ page }) => {
  // 🔴 2026-09-11: the list offered every bot not already here, so the demo account listed both
  // LIVE bots — greyed while running, one click from real money once stopped. Aaron: *"it should
  // just show available bots that is it"* — and the symbol went: *"the account doesn't care."*
  // MUTATION: list every bot not on this account again → `add-extreme` renders and goes red.
  await mock(page, [
    group({ bots: [bot('sos_fade', 'SOS Fade', 770115, 10)], risk_cap_pct: 10 }),
    group({
      account: 700152905,
      bots: [bot('extreme', 'Extreme Leg', 770117, 10, 5)],
      risk_cap_pct: 10,
    }),
    BENCHED,
  ])
  await openAccount(page)
  await page.getByTestId('add-bot').click()
  const free = page.getByTestId('add-b_leg')
  await expect(free).toBeVisible()
  await expect(free).toContainText('Risks 10% a trade')
  await expect(free).not.toContainText('XAUUSD')
  await expect(page.getByTestId('add-bot-row')).not.toContainText('not on an account')
  await expect(page.getByTestId('add-extreme')).toHaveCount(0)
})

test('adding a bot sends its key and the account it is joining', async ({ page }) => {
  await mock(page, [
    group({ bots: [bot('sos_fade', 'SOS Fade', 770115, 10)], risk_cap_pct: 10 }),
    BENCHED,
  ])
  let sent: Record<string, unknown> | null = null
  await page.route('**/*', async (route) => {
    const u = new URL(route.request().url())
    if (u.pathname === '/api/bots/b_leg/account') {
      sent = route.request().postDataJSON()
      return route.fulfill({
        json: {
          status: 'ok',
          changed: true,
          deployed: true,
          bot: 'b_leg',
          account: ACCOUNT,
          restart_required: true,
          detail: 'moved',
        },
      })
    }
    return route.fallback()
  })

  // ⚠ Re-pointed 2026-09-06 with its sibling above: the control moved into the ACCOUNT drawer.
  await openAccount(page)
  await page.getByTestId('add-bot').click()
  await page.getByTestId('add-b_leg').click()
  await expect.poll(() => sent).toEqual({ account: ACCOUNT, deploy: true })
  // Never "added and trading" — a bot reads its account at startup.
  await expect(page.getByText(/start it to trade/i)).toBeVisible()
})

test('removing a bot sends null, which is the bench rather than a delete', async ({ page }) => {
  // MUTATION: send `0` or omit the field → the backend would read a missing body as no change,
  // and `0` is not an account. `null` is the only spelling of "on no account".
  await mock(page, STACKED)
  let sent: Record<string, unknown> | null = null
  await page.route('**/*', async (route) => {
    const u = new URL(route.request().url())
    if (u.pathname === '/api/bots/b_leg/account') {
      sent = route.request().postDataJSON()
      return route.fulfill({
        json: {
          status: 'ok',
          changed: true,
          deployed: true,
          bot: 'b_leg',
          account: null,
          restart_required: true,
          detail: 'benched',
        },
      })
    }
    return route.fallback()
  })

  // ⚠ Re-pointed twice. The account card's own Remove button went with the tab collapse
  // (2026-09-06) and removal became the last option in the bot's account selector, which nobody
  // found — Aaron: *"we can stop but we can't remove"*. It is its own button again (2026-09-11).
  // **The RULE is untouched and is the whole check: `null` is the only spelling of "on no
  // account" — `0` is not an account, and omitting the field reads to the backend as no change.**
  await openBot(page, 'b_leg')
  const remove = page.getByTestId('remove-b_leg')
  await remove.click()
  await remove.click()
  await expect.poll(() => sent).toEqual({ account: null, deploy: true })
  await expect(page.getByText(/will not start until it is on one again/i)).toBeVisible()
})

/** Answers a removal of `b_leg` and records every body sent, so a check can COUNT the writes. */
async function recordRemovals(page: Page) {
  const sent: unknown[] = []
  await page.route('**/*', async (route) => {
    const u = new URL(route.request().url())
    if (u.pathname === '/api/bots/b_leg/account') {
      sent.push(route.request().postDataJSON())
      return route.fulfill({
        json: {
          status: 'ok',
          changed: true,
          deployed: true,
          bot: 'b_leg',
          account: null,
          restart_required: true,
          detail: 'benched',
        },
      })
    }
    return route.fallback()
  })
  return sent
}

test('Remove takes a SECOND click — the first only arms it', async ({ page }) => {
  // It is one press from taking a bot off the account it trades, so it works like the live
  // deploy: the first click re-labels the button, only the second sends.
  // MUTATION: drop the arming branch → the first click sends and this goes red.
  await mock(page, STACKED)
  const sent = await recordRemovals(page)
  await openBot(page, 'b_leg')
  const remove = page.getByTestId('remove-b_leg')
  await expect(remove).toHaveText(/Remove from account/)
  await remove.click()
  await expect(remove).toHaveText(/Click again to remove/)
  expect(sent).toHaveLength(0)
})

test('an armed Remove disarms itself, so a stray click later is not the second one', async ({
  page,
}) => {
  // MUTATION: drop the 6s disarm → the button stays armed and this goes red. (The page's clock
  // runs ten times fast here, so the six seconds pass in under one.)
  await mock(page, STACKED)
  const sent = await recordRemovals(page)
  await openBot(page, 'b_leg')
  const remove = page.getByTestId('remove-b_leg')
  await remove.click()
  await expect(remove).toHaveText(/Click again to remove/)
  await expect(remove).toHaveText(/Remove from account/, { timeout: 5_000 })
  expect(sent).toHaveLength(0)
})

test('a RUNNING bot cannot be removed from its account', async ({ page }) => {
  // It read its account at startup, so taking it off cannot reach the running process — the page
  // would list it as unassigned while it went on trading. The server refuses it; so does this.
  // MUTATION: drop `running` from the button's `disabled` → it enables and this goes red. The
  // stopped-bot checks above are the positive control.
  await mock(page, [group({ bots: [bot('sos_fade', 'SOS Fade', 770115, null)] })], [reg()])
  await openBot(page, 'sos_fade') // the snapshot mock has sos_fade RUNNING
  await expect(page.getByTestId('remove-sos_fade')).toBeDisabled()
})

test('a bot the CONFIG has on no account offers no Remove, whatever it last reported', async ({
  page,
}) => {
  // 🔴 The panel's bot record carries the account the bot last REPORTED, which stays on the old
  // account until its next start — so a bot just taken off an account still "reports" it. A
  // removal is decided off the CONFIG, or the panel offers Remove on a bot already removed.
  // MUTATION: gate Remove on the bot's own report → it is offered here and this goes red.
  await mock(page, [BENCHED], [reg()])
  await page.route('**/*', async (route) => {
    const u = new URL(route.request().url())
    if (u.pathname === '/api/bots/snapshot') {
      return route.fulfill({
        json: {
          fetched_at: new Date().toISOString(),
          bots: [
            {
              key: 'b_leg',
              name: 'B-LEG',
              status: 'STOPPED',
              account_type: 'demo',
              account: String(ACCOUNT),
            },
          ],
          scheduled_jobs: [],
          telegram: { name: 'Telegram', status: 'RUNNING' },
        },
      })
    }
    return route.fallback()
  })
  await openBot(page, 'b_leg')
  // The configs have landed once the selector leaves the bot's own report — the positive control
  // that the absence below is an answer, not a panel still waiting on the configs.
  await expect(page.getByTestId('move-b_leg')).toHaveValue('')
  await expect(page.getByTestId('remove-b_leg')).toHaveCount(0)
})

test('a STOPPED bot may be moved — the positive control for the running guard', async ({
  page,
}) => {
  // Without this, *a RUNNING bot cannot be moved* passes against a page that disabled the control
  // for everybody. An absent action and a withheld one are the same DOM, and this file has now
  // recorded that trap six times.
  await mock(page, STACKED, [reg(), reg({ account: OTHER, label: 'ECN' })])
  await openBot(page, 'b_leg') // the snapshot mock has sos_fade RUNNING, b_leg STOPPED
  await expect(page.getByTestId('move-b_leg')).toBeEnabled()
})

test('an account with nothing left to add says so instead of an empty list', async ({ page }) => {
  // MUTATION: render the picker unconditionally → an empty box with no explanation, which reads
  // as a broken control rather than as an answer.
  await mock(page, STACKED)
  await openAccount(page)
  await page.getByTestId('add-bot').click()
  await expect(page.getByTestId('no-candidates')).toContainText('No bot is free')
})

test('the FIRST bot on an empty account carries the cap chosen with it', async ({ page }) => {
  // 🔴 2026-09-11: the cap is stored per bot, so an empty account has none — the first bot
  // started uncapped, the watchdog started it within a minute, and a cap saved after could not
  // reach the running process. The add now carries it; unticked is `null` (uncapped CHOSEN).
  // MUTATION: drop `riskCapPct` from the pick → the body has no cap and both asserts go red.
  await mock(page, [BENCHED], [reg()])
  const sent: Record<string, unknown>[] = []
  await page.route('**/*', async (route) => {
    const u = new URL(route.request().url())
    if (u.pathname === '/api/bots/b_leg/account') {
      sent.push(route.request().postDataJSON())
      return route.fulfill({
        json: {
          status: 'ok',
          changed: true,
          deployed: true,
          bot: 'b_leg',
          account: ACCOUNT,
          restart_required: true,
          detail: 'moved',
        },
      })
    }
    return route.fallback()
  })

  await openAccount(page)
  await page.getByTestId('add-bot').click()
  await expect(page.getByTestId('first-cap-input')).toHaveValue('10')
  await page.getByTestId('add-b_leg').click()
  await expect.poll(() => sent[0]).toEqual({ account: ACCOUNT, risk_cap_pct: 10, deploy: true })
  // The toast names the bot, never its key.
  await expect(page.getByText('B-LEG added to account')).toBeVisible()

  await page.getByTestId('first-cap-on').uncheck()
  await page.getByTestId('add-b_leg').click()
  await expect.poll(() => sent[1]).toEqual({ account: ACCOUNT, risk_cap_pct: null, deploy: true })
})

test('an account with bots sends NO cap when one is added', async ({ page }) => {
  // The joining bot adopts the account's cap on the server; a cap sent here would be a second
  // answer, and the server refuses one that differs. MUTATION: send the cap whatever the account
  // holds → the body gains `risk_cap_pct` and this goes red.
  await mock(page, [
    group({ bots: [bot('sos_fade', 'SOS Fade', 770115, 10)], risk_cap_pct: 10 }),
    BENCHED,
  ])
  let sent: Record<string, unknown> | null = null
  await page.route('**/*', async (route) => {
    const u = new URL(route.request().url())
    if (u.pathname === '/api/bots/b_leg/account') {
      sent = route.request().postDataJSON()
      return route.fulfill({
        json: { status: 'ok', changed: true, bot: 'b_leg', account: ACCOUNT, detail: 'moved' },
      })
    }
    return route.fallback()
  })
  await openAccount(page)
  await page.getByTestId('add-bot').click()
  await expect(page.getByTestId('first-cap')).toHaveCount(0)
  await page.getByTestId('add-b_leg').click()
  await expect.poll(() => sent).toEqual({ account: ACCOUNT, deploy: true })
})

test('an empty account says where its cap is set instead of offering a save that cannot work', async ({
  page,
}) => {
  // Saving a cap on an account with no bot answered 404 — there is no config to write it into.
  // MUTATION: render the cap editor on an empty account again → `cap-input` appears.
  await mock(page, [BENCHED], [reg()])
  await openAccount(page)
  await expect(page.getByTestId('cap-empty')).toContainText('The first bot you add sets it')
  await expect(page.getByTestId('cap-input')).toHaveCount(0)
})

test('the magic clash is named only when there is one', async ({ page }) => {
  // The fact the raw `magic` column was trying to convey, shown when it matters and never
  // otherwise. MUTATION: render the banner whenever the group exists → the healthy case fails.
  await mock(page, [
    group({
      bots: [bot('a', 'A', 770115, 10), bot('b', 'B', 770115, 10)],
      risk_cap_pct: 10,
      stacked: true,
      magic_clash: ['a', 'b'],
    }),
  ])
  await openAccount(page)
  await expect(page.getByTestId('magic-clash')).toContainText('share an order tag')

  await mock(page, STACKED)
  await openAccount(page)
  await expect(page.getByTestId('magic-clash')).toHaveCount(0)
})

test('there is no raw magic column left to misread', async ({ page }) => {
  // Aaron: *"I don't know what the column magic even means."* It is gone, replaced by the
  // clash banner above — so this asserts the header is absent AND that the number is too.
  await mock(page, STACKED)
  await page.goto('/bots')
  await expect(page.locator('th', { hasText: /^Magic$/ })).toHaveCount(0)
  await expect(page.getByTestId('account-card')).not.toContainText('770115')
})

test('the version pill reports the DEPLOYED version and how far behind it is', async ({ page }) => {
  // MUTATION: render `local_version` instead → it shows v121 and this goes red. v121 is the
  // backtester's and is running nowhere; the number a fleet row must answer for is the box's.
  await mock(page, STACKED)
  await page.goto('/bots')
  const pill = page.locator('[data-testid="version-pill"][data-state="behind"]').first()
  await expect(pill).toContainText('v100')
  await expect(pill).toContainText('21 behind')
})

test('a bot whose version cannot be worked out says so rather than showing a number', async ({
  page,
}) => {
  // MUTATION: fall back to `v0` → red. `v0` is the reassuring answer to a question nobody
  // could answer, and this pill is what you check before deciding anything.
  await mock(page, STACKED) // the version mock returns compare: null for b_leg
  await page.goto('/bots')
  await expect(page.locator('[data-testid="version-pill"][data-state="unknown"]')).toHaveCount(1)
  await expect(page.locator('[data-testid="version-pill"][data-state="unknown"]')).toContainText(
    'No version'
  )
})

test('every bot row carries the same version pill, under a labelled column', async ({ page }) => {
  // Aaron asked for it wherever a bot is listed, from ONE component, so two surfaces cannot
  // disagree about which version is deployed.
  // MUTATION: drop the pill from the row → the count goes to 0, red.
  //
  // ⚠ Re-pointed 2026-09-06: the rows were a `<table>` and are a grid now, so the heading is a
  // `<span>` — the COLUMN still has to be labelled, because four numeric columns with no heading
  // means the reader decodes them from their own shape.
  await mock(page, STACKED)
  await page.goto('/bots')
  await expect(page.getByText('Version', { exact: true })).toHaveCount(1)
  await expect(page.locator('[data-testid="version-pill"]')).toHaveCount(2)
})

// ── The account REGISTRY — added 2026-08-12 ───────────────────────────────────
//
// 🔴 These cover the gap that made moving the live bot to the ECN demo a manual afternoon: the
// grouping is DERIVED from instance configs, which is right, and it could therefore only ever see
// accounts a bot was already on — so the first bot onto a new account had nothing to be moved to.

test('Take live is offered on a DEMO account with bots on it', async ({ page }) => {
  // The positive control for the check below: without it, "not drawn on a live account" would
  // pass against a page that never draws the button anywhere.
  await mock(page, STACKED, [reg()])
  await openAccount(page)
  await expect(page.getByTestId('go-live')).toBeVisible()
})

test('Take live is NOT DRAWN on a live account', async ({ page }) => {
  // 🔴 2026-09-11, the day the first set went live: the live account's panel still carried it,
  // disabled as "already live". Aaron: *"this should only be present for demo accounts."*
  // ⚠ The account's own controls are asserted FIRST — an absent button is also what a panel
  // still waiting on the registry draws, and that would pass for the wrong reason.
  // MUTATION: drop the demo-only condition → the button is drawn (disabled) and this goes red.
  const LIVE_ACCOUNT = 34957946
  await mock(
    page,
    STACKED.map((g) => ({ ...g, account: LIVE_ACCOUNT, server: 'PUPrime-Live' })),
    [reg({ account: LIVE_ACCOUNT, kind: 'live', server: 'PUPrime-Live' })]
  )
  await openAccount(page, LIVE_ACCOUNT)
  const drawer = page.getByRole('complementary', { name: 'Account settings' })
  await expect(drawer.getByRole('button', { name: 'Edit' })).toBeVisible()
  await expect(drawer.getByTestId('go-live')).toHaveCount(0)
})

test('Backtest these bots is offered on a DEMO account', async ({ page }) => {
  // The positive control for the check below, for the same reason as Take live's.
  await mock(page, STACKED, [reg()])
  await openAccount(page)
  await expect(page.getByTestId('backtest-account-bots')).toBeVisible()
})

test('Backtest these bots is NOT DRAWN on a live account', async ({ page }) => {
  // 🔴 2026-09-11, Aaron: *"backtest these bots should only be on demo accounts, not live
  // accounts."* Demo is where a set is tried; the live bots run what was tested there.
  // ⚠ The account's own Edit control is asserted FIRST, so the absence is an answer rather than
  // a panel still waiting on the registry.
  // MUTATION: drop the demo-only condition → the button is drawn and this goes red.
  const LIVE_ACCOUNT = 34957946
  await mock(
    page,
    STACKED.map((g) => ({ ...g, account: LIVE_ACCOUNT, server: 'PUPrime-Live' })),
    [reg({ account: LIVE_ACCOUNT, kind: 'live', server: 'PUPrime-Live' })]
  )
  await openAccount(page, LIVE_ACCOUNT)
  const drawer = page.getByRole('complementary', { name: 'Account settings' })
  await expect(drawer.getByRole('button', { name: 'Edit' })).toBeVisible()
  await expect(drawer.getByTestId('backtest-account-bots')).toHaveCount(0)
})

test('a registered account with NO bots can still be OPENED and added to', async ({ page }) => {
  // 🔴 WATCHED RED on 2026-09-06, and it is the registry's whole purpose re-broken. The drawer
  // rendered only for an account in the GROUPING — which is derived from the instance configs and
  // therefore holds only accounts a bot is ALREADY on — so the one account that most needs the
  // Add bot control could not be opened at all.
  // MUTATION: require the grouping again → the drawer never renders and this goes red.
  await mock(page, [], [reg()])
  await openAccount(page)

  // The wording moved in 44e1d69c ("an account its bots left is still an account").
  await expect(page.getByTestId('no-bots')).toContainText('No bot is on this account now')
  await expect(page.getByTestId('add-bot')).toBeEnabled()
})

test('an account with no terminal cannot be added to, and says why', async ({ page }) => {
  // MUTATION: make `assignable` always true in bot_account_registry → Add bot enables and this
  // goes red. A bot assigned to an account no terminal is logged into would be written,
  // committed, pushed and pulled, and THEN fail at connect() with a message about credentials —
  // pointing the reader at the password rather than at the missing terminal.
  await mock(
    page,
    [],
    [
      reg({
        mt5_path: '',
        assignable: false,
        unassignable_reason: 'account 700107749 has no terminal on the VPS logged into it',
      }),
    ]
  )
  // 🔴 WATCHED RED on 2026-09-06: neither the chip nor the guard survived the tab collapse, so
  // the drawer offered Add bot on an account no terminal is logged into.
  await openAccount(page)

  await expect(page.getByTestId('no-terminal')).toBeVisible()
  await expect(page.getByTestId('add-bot')).toBeDisabled()
  // ⚠ The REASON, not merely the disabled state — a greyed control with no explanation reads as
  // a rendering fault, and the reader cannot tell it from an account that is simply busy.
  await expect(page.getByTestId('no-terminal')).toHaveAttribute('title', /no terminal/)
})

test('a password the VPS could not be asked about reads UNKNOWN, never "no password"', async ({
  page,
}) => {
  // MUTATION: in routers/bots._registration, return `entry.account in (with_password or set())`
  // instead of the three-state → this reads "No password" and goes red.
  //
  // ⚠ Both halves are asserted, and the second is what makes it bite: a check for the presence
  // of "Password unknown" alone would pass against a chip that ALSO said no password somewhere.
  // Rendering an unanswered question as a missing credential sends the reader to re-enter one
  // that is already there, and refuses a move that would have worked.
  //
  // 🔴 WATCHED RED on 2026-09-06 — the chip went off screen entirely with the tab collapse, so
  // all three answers rendered as nothing at all, which reads as *no problem here*.
  await mock(page, [], [reg({ has_password: null })])
  await openAccount(page)

  const chip = page.getByTestId('password-chip')
  await expect(chip).toContainText(/password unknown/i)
  await expect(chip).not.toContainText(/no password/i)
})

test('an account with no stored password says so before you try to move a bot onto it', async ({
  page,
}) => {
  // The backend refuses the move (409) on a DEFINITE no; this is the same fact stated before
  // the click rather than after it.
  await mock(page, [], [reg({ has_password: false })])
  await openAccount(page)
  await expect(page.getByTestId('password-chip')).toContainText(/no password/i)
})

test('adding an account sends the SYMBOL SUFFIX, which is the field the ECN move forgot', async ({
  page,
}) => {
  // MUTATION: drop `symbol_suffix` from the AccountForm submit body → red on the last assertion.
  //
  // This is the field that, left behind on 2026-08-12, would have pointed the bot at XAUUSD.s on
  // an ECN book that does not quote it — connecting cleanly, warming up, and receiving no bars.
  let body: Record<string, unknown> | null = null
  await mock(page, [], [])
  await page.route('**/api/bots/accounts/registry/**', async (route) => {
    if (route.request().method() !== 'PUT') return route.fallback()
    body = route.request().postDataJSON()
    return route.fulfill({ json: reg({ account: 700152905 }) })
  })

  await openManualAdd(page)
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

// ── Sync VPS: scan first, then a Sync button ──────────────────────────────────────────────────
//
// 🔴 **Opening the drawer READS; only the Sync button under the plan WRITES** (Aaron, 2026-09-10:
// "it doesn't show me what it is going to do before I do it"). Every check here counts requests
// through `routeSync`, because "who wrote" is a question about requests, not about what is drawn.
//
// ⚠ A fail-watch against HEAD is vacuous for most of these (the preview did not exist), so each
// names the mutation that turns it red, and every one was RUN.

test('adding by hand is still reachable when the SCAN fails, and is the only add control', async ({
  page,
}) => {
  // MUTATION: render the by-hand link only once the scan has answered → red, because the
  // failed-scan card is showing and the link is gone.
  // MUTATION: offer Sync over a failed scan → red on the count of zero.
  //
  // A stopped terminal can never show up in a scan, and neither can anything while the box is
  // unreachable — so the by-hand form is the ONLY way that account gets onto the list. Hiding it
  // behind a successful scan would leave it with no way in at all.
  await mock(page, [], [])
  await routeSync(page, { scan: () => 'fail' })
  await page.goto('/bots')
  await expect(page.getByTestId('add-account')).toHaveCount(0)
  await page.getByTestId('sync-vps').click()
  // Positive control first: the failure is what is on screen, so the link is being checked in
  // the state it exists for — not in a drawer that simply has not answered yet.
  await expect(page.getByTestId('sync-hero')).toContainText('Couldn’t reach the VPS')
  await expect(page.getByTestId('sync-hero')).toContainText('ssh to forexvps failed')
  await expect(page.getByTestId('sync-hero')).toContainText('Nothing was changed')
  await expect(page.getByTestId('sync-apply')).toHaveCount(0)
  await expect(page.getByTestId('scan-again')).toBeEnabled()
  await expect(page.getByTestId('add-account')).toHaveCount(1)
  await page.getByTestId('add-account').click()
  await expect(page.getByTestId('f-account')).toBeVisible()
})

test('opening Sync VPS SCANS and writes nothing — only the Sync button writes', async ({
  page,
}) => {
  // MUTATION: sync from an effect once the plan arrives → red on "opening wrote nothing" (RUN).
  // MUTATION: keep the scan cached across opens (drop `gcTime: 0`) → red on the second scan.
  // MUTATION: post without `expect_plan` → red on the body.
  // MUTATION: scan from the page on load → red on the first count of zero.
  await mock(page, [group()], [reg()])
  const seen = await routeSync(page, {
    scan: () => preview({ changes: [CLEAR_TERMINAL], plan_id: 'plan-a' }),
  })
  await page.goto('/bots')
  // Positive control: the page has loaded far enough that anything it does on load has done it.
  // The Unassigned count appears only once the registry AND the box have answered, so it is the
  // latest thing the page waits on. (The account text this used to wait for moved to that tab.)
  await expect(page.getByTestId('tab-unassigned')).toContainText(/\d/)
  await page.waitForTimeout(500)
  expect(seen.scans).toBe(0)
  expect(seen.syncs).toBe(0)

  await page.getByTestId('sync-vps').click()
  await expect(page.getByTestId('sync-change')).toHaveCount(1)
  expect(seen.scans).toBe(1)
  await page.waitForTimeout(400)
  expect(seen.syncs).toBe(0)

  // Close and reopen: a FRESH scan, never the plan from last time — and still nothing written.
  await page.keyboard.press('Escape')
  await page.getByTestId('sync-vps').click()
  await expect.poll(() => seen.scans).toBe(2)
  await expect(page.getByTestId('sync-change')).toHaveCount(1)
  expect(seen.syncs).toBe(0)

  // The press carries the plan it approves, so the server can refuse one that moved.
  await page.getByTestId('sync-apply').click()
  await expect.poll(() => seen.syncs).toBe(1)
  expect(seen.bodies[0].expect_plan).toBe('plan-a')
})

test('the plan is listed field by field — what it is now, what it will be, and how we know', async ({
  page,
}) => {
  // MUTATION: drop the struck-out old value → red on the update's "before".
  // MUTATION: draw an old value for an ADD (`before ?? 'none'`) → red: "not in your list yet" is
  // not a blank field, and drawing one says the list had this account empty.
  // MUTATION: drop the Real money tag → red. MUTATION: drop the "needs you" section → red.
  await mock(page, [group()], [reg()])
  const seen = await routeSync(page, {
    scan: () =>
      preview({
        changes: [ADD_LIVE, CLEAR_TERMINAL],
        attention: [
          {
            account: ACCOUNT,
            label: 'PU Prime ECN demo',
            said: ['SOS Fade trades this account, so sync left it alone.'],
          },
        ],
      }),
  })
  await page.goto('/bots')
  await page.getByTestId('sync-vps').click()

  await expect(page.getByTestId('sync-hero')).toContainText('2 changes to make')
  await expect(page.locator('[data-step="Review"]')).toHaveAttribute('data-state', 'active')
  const cards = page.getByTestId('sync-change')
  await expect(cards).toHaveCount(2)

  const upd = cards.filter({ hasText: '#700107749' })
  await expect(upd).toContainText('Update')
  await expect(upd.getByTestId('diff-before')).toHaveText('MT5_FFT')
  await expect(upd.getByTestId('diff-after')).toHaveText('none')
  await expect(upd).toContainText('is logged into #700152905')

  const add = cards.filter({ hasText: '#34957946' })
  await expect(add).toContainText('New')
  await expect(add.getByTestId('diff-after').first()).toHaveText('PUPrime-Live')
  await expect(add.getByTestId('diff-before')).toHaveCount(0)
  await expect(add).toContainText('Real money')

  await expect(page.getByTestId('sync-attention')).toContainText('left it alone')
  await expect(page.getByTestId('sync-apply')).toHaveText(/Sync 2 changes/)
  await expect(page.getByText('Nothing is saved until you press Sync.')).toBeVisible()
  expect(seen.syncs).toBe(0)
})

test('a press whose plan MOVED saves nothing and puts the NEW plan on screen', async ({ page }) => {
  // 🔴 A terminal can switch account between the scan and the press. The server re-scans, writes
  // nothing and hands back the new plan; this pins that the page SAYS so, shows that plan in place
  // of the old one, and that the next press approves the new plan rather than the stale one.
  // MUTATION: read a refused press as a receipt → red on the phase: the banner alone does not
  // catch it, because it is driven separately and still shows — the hero would claim a save.
  // MUTATION: keep the old plan on screen (no `setQueryData(now)`) → red on the card and the body.
  await mock(page, [group()], [reg()])
  const seen = await routeSync(page, {
    scan: () => preview({ changes: [CLEAR_TERMINAL], plan_id: 'plan-a' }),
    sync: (body) =>
      body.expect_plan === 'plan-b'
        ? syncResult({ changes: [ADD_LIVE], deployed: true })
        : syncResult({
            now: preview({ changes: [ADD_LIVE], plan_id: 'plan-b' }),
            plan_changed: true,
          }),
  })
  await page.goto('/bots')
  await page.getByTestId('sync-vps').click()
  await page.getByTestId('sync-apply').click()

  await expect(page.getByTestId('sync-plan-changed')).toBeVisible()
  await expect(page.getByTestId('sync-hero')).toHaveAttribute('data-phase', 'review')
  await expect(page.getByTestId('sync-saved')).toHaveCount(0)
  const cards = page.getByTestId('sync-change')
  await expect(cards).toHaveCount(1)
  await expect(cards).toContainText('#34957946')

  await page.getByTestId('sync-apply').click()
  await expect.poll(() => seen.syncs).toBe(2)
  expect(seen.bodies[1].expect_plan).toBe('plan-b')
  await expect(page.getByTestId('sync-saved')).toHaveCount(1)
  await expect(page.getByTestId('sync-plan-changed')).toHaveCount(0)
})

test('after a sync: what was saved, and the list as it now is — without asking the box again', async ({
  page,
}) => {
  // MUTATION: put the preview under the accounts prefix, so the post-sync refresh re-asks it →
  // red on the scan count. `now` arrives WITH the sync; a second scan is minutes of SSH for an
  // answer already on screen.
  // MUTATION: drop the receipt → red. MUTATION: offer Sync over a finished, matching list → red.
  await mock(page, [group()], [reg()])
  const seen = await routeSync(page, {
    scan: () => preview({ changes: [CLEAR_TERMINAL] }),
    sync: () =>
      syncResult({
        changes: [CLEAR_TERMINAL],
        deployed: true,
        now: preview({
          registry: [
            {
              account: 700107749,
              label: 'retired',
              verdict: 'confirmed',
              detail: '',
              conflicts: [],
              seen_on: null,
            },
          ],
        }),
      }),
  })
  await page.goto('/bots')
  await page.getByTestId('sync-vps').click()
  await page.getByTestId('sync-apply').click()

  await expect(page.getByTestId('sync-hero')).toContainText('Synced — 1 change saved')
  await expect(page.getByTestId('sync-hero')).toContainText('Saved and sent to the VPS.')
  await expect(page.locator('[data-step="Sync"]')).toHaveAttribute('data-state', 'done')
  const saved = page.getByTestId('sync-saved')
  await expect(saved).toHaveCount(1)
  await expect(saved.getByTestId('diff-before')).toHaveText('MT5_FFT')
  await expect(page.getByTestId('sync-change')).toHaveCount(0)
  await expect(page.getByText(/Your list now: 1 matches the VPS/)).toBeVisible()
  await expect(page.getByTestId('sync-done')).toBeVisible()
  await expect(page.getByTestId('sync-apply')).toHaveCount(0)
  await page.waitForTimeout(500)
  expect(seen.scans).toBe(1)

  // Scan again is a new question: the receipt goes and the box is asked afresh.
  await page.getByTestId('scan-again').click()
  await expect.poll(() => seen.scans).toBe(2)
  await expect(page.getByTestId('sync-saved')).toHaveCount(0)
})

test('a sync whose push never reached the VPS says the bots cannot see it', async ({ page }) => {
  // MUTATION: drop the deploy-error banner → red. Without it "saved" describes a change the
  // bots, which read the VPS's copy, will never see.
  await mock(page, [group()], [reg()])
  await routeSync(page, {
    scan: () => preview({ changes: [CLEAR_TERMINAL] }),
    sync: () =>
      syncResult({ changes: [CLEAR_TERMINAL], deploy_error: 'git push failed: rejected' }),
  })
  await page.goto('/bots')
  await page.getByTestId('sync-vps').click()
  await page.getByTestId('sync-apply').click()
  const banner = page.getByTestId('sync-deploy-error')
  await expect(banner).toContainText('Saved here, but not sent to the VPS')
  await expect(banner).toContainText('rejected')
  await expect(page.getByTestId('sync-hero')).toContainText('not sent to the VPS')
})

test('a list that already matches says so and offers nothing to sync', async ({ page }) => {
  // MUTATION: offer the Sync button over an empty plan → red on the count of zero. A button
  // whose press can change nothing reads as broken the moment it is pressed.
  await mock(page, [group()], [reg()])
  await routeSync(page)
  await page.goto('/bots')
  await page.getByTestId('sync-vps').click()
  await expect(page.getByTestId('sync-hero')).toContainText('Your list matches the VPS')
  await expect(page.locator('[data-step="Sync"]')).toHaveAttribute('data-state', 'skipped')
  await expect(page.getByTestId('sync-apply')).toHaveCount(0)
  await page.getByTestId('sync-done').click()
  await expect(page.getByTestId('sync-hero')).toHaveCount(0)
})

test('a blocked plan says sync can’t run and why, and the button is off', async ({ page }) => {
  // MUTATION: ignore `blocked` → red: "Your list matches the VPS" would be claimed about a scan
  // that could not tell which accounts the bots trade.
  await mock(page, [group()], [reg()])
  await routeSync(page, {
    scan: () => preview({ blocked: "A bot's settings file couldn't be read." }),
  })
  await page.goto('/bots')
  await page.getByTestId('sync-vps').click()
  await expect(page.getByTestId('sync-hero')).toContainText('Sync can’t run right now')
  await expect(page.getByTestId('sync-hero')).toContainText("settings file couldn't be read")
  await expect(page.getByTestId('sync-apply')).toBeDisabled()
  await expect(page.getByText('Your list matches the VPS')).toHaveCount(0)
})

test('a sync that FAILS keeps the plan on screen and says so', async ({ page }) => {
  // MUTATION: drop the failure banner → red. MUTATION: hide the plan once a sync has failed →
  // red: the reader would lose the list they were about to approve because a press went
  // unanswered, and could not press again without scanning.
  await mock(page, [group()], [reg()])
  const seen = await routeSync(page, {
    scan: () => preview({ changes: [CLEAR_TERMINAL] }),
    sync: () => 'fail',
  })
  await page.goto('/bots')
  await page.getByTestId('sync-vps').click()
  await page.getByTestId('sync-apply').click()
  await expect(page.getByTestId('sync-error')).toContainText('The sync didn’t finish')
  await expect(page.getByTestId('sync-error')).toContainText('ssh to forexvps failed')
  await expect(page.getByTestId('sync-change')).toHaveCount(1)
  await expect(page.getByTestId('sync-apply')).toBeEnabled()
  expect(seen.syncs).toBe(1)
})

test('a scan the box REFUSED is an answer, not a failure, and offers no sync', async ({ page }) => {
  // MUTATION: render a refusal as the failed-scan card → red. Sending somebody to check the
  // network when the box refused on purpose is the wrong repair.
  await mock(page, [group()], [reg()])
  await routeSync(page, {
    scan: () =>
      preview({
        asked: false,
        reason: 'no instance directory - refusing to scan rather than attaching',
        terminals: [],
      }),
  })
  await page.goto('/bots')
  await page.getByTestId('sync-vps').click()
  await expect(page.getByTestId('sync-hero')).toContainText('The VPS refused the scan')
  await expect(page.getByTestId('sync-hero')).toContainText('refusing to scan')
  await expect(page.getByTestId('sync-apply')).toHaveCount(0)
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
  await page.route('**/api/bots/accounts/registry/**', async (route) => {
    if (route.request().method() !== 'PUT') return route.fallback()
    body = route.request().postDataJSON()
    return route.fulfill({ json: reg() })
  })

  await openManualAdd(page)
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
  await mock(page, [group({ bots: [bot('sos_fade', 'SOS Fade', 770115, null)] })], [reg()])
  await openAccount(page)
  await expect(page.getByTestId(`unregister-${ACCOUNT}`)).toBeDisabled()
})

test('an account nobody registered still renders, with the gap named', async ({ page }) => {
  // Backwards compatibility, and it is the half that keeps the registry from being a wall: the
  // account still works, and the reader is told what this page cannot do with it.
  await mock(page, [group({ bots: [bot('sos_fade', 'SOS Fade', 770115, null)] })], [])
  await openAccount(page)
  await expect(page.getByTestId('unregistered')).toBeVisible()
  // ⚠ And NO password chip, because nothing was ever asked about a login nobody registered —
  // a chip reading "no password" there would be a claim off a measurement that was never taken.
  await expect(page.getByTestId('password-chip')).toHaveCount(0)
})

// ── Live against demo: split, and scored so the winner is easy to see ─────────────────────────
//
// Aaron, 2026-09-10: *"when we are on the all page I want live and demo split. I could [have] both
// running and I want to be able to easily identify the winner."*
//
// 🔴 **The winner is judged in R PER TRADE, and the fixture is built so every other measure gets it
// wrong.** Demo made more dollars AND more total R; live made more per trade. A live account is
// smaller, runs lower risk and started later, so dollars or total R would crown demo by default.
// ⚠ A fail-watch against HEAD is vacuous (none of this existed), so each check names the mutation
// that turns it red, and every one was RUN.

const LIVE = 34957946
const LIVE_EMPTY = 34950001

function earn(bot_key: string, over: Record<string, unknown> = {}) {
  return {
    bot_key,
    name: bot_key,
    traded: true,
    reason: null,
    closed_trades: 0,
    realised_usd: 0,
    realised_r: 0,
    wins: 0,
    losses: 0,
    records_from: '2026-09-01',
    records_to: '2026-09-10',
    records_through: null,
    record_source: 'live',
    pct_of_opening: 0,
    ...over,
  }
}

function acctEarn(account: number, bots: ReturnType<typeof earn>[]) {
  return {
    account,
    balance: 10000,
    opening_balance: 9000,
    opening_from: bots[0]?.bot_key ?? null,
    opening_note: null,
    net_usd: 1000,
    net_pct: 11.1,
    attributed_usd: 1000,
    unattributed_usd: 0,
    records_live: true,
    attribution_lag_seconds: 0,
    attribution_note: null,
    bots_without_record: [],
    bots,
  }
}

/** Demo: SOS Fade +$1,500 / +0.91R over 2, Extreme Leg +$1,305 / +2.10R over 1 → +1.00R a trade.
 *  Live: SOS Fade live +$412 / +2.95R over 2 → +1.48R a trade, plus a second live bot. */
const SCORED = {
  sos_fade: {
    closed_trades: 2,
    realised_usd: 1500,
    realised_r: 0.91,
    wins: 2,
    pct_of_opening: 16.7,
  },
  ext_leg: {
    closed_trades: 1,
    realised_usd: 1305.58,
    realised_r: 2.1,
    wins: 1,
    pct_of_opening: 14.5,
  },
  sos_live: {
    closed_trades: 2,
    realised_usd: 412.3,
    realised_r: 2.95,
    wins: 2,
    pct_of_opening: 20.6,
  },
  ext_live: {},
}

/**
 * One demo account and one live account, each with bots, plus an EMPTY account of each kind — so
 * the split has something to put on both sides. `earnings` states each bot's record by key; a key
 * left out is a bot whose record was NOT read.
 */
async function mockBothSides(
  page: Page,
  earnings: Record<string, Record<string, unknown>>,
  benched: Record<string, unknown>[] = [],
  // A third demo bot, so one side can pool two scored bots while a third record is unread.
  thirdDemo = false,
  // Figures stated over an account's own earnings, keyed by account — e.g. which basis its net is.
  acctOver: Record<number, Record<string, unknown>> = {},
  // Fields stated over a bot's own row in the fleet snapshot, keyed by bot — e.g. its trade flag.
  botOver: Record<string, Record<string, unknown>> = {}
) {
  const third = thirdDemo
    ? [{ key: 'realign', name: 'Realign', status: 'RUNNING', account_type: 'demo' }]
    : []
  const demoGroup = group({
    bots: [
      bot('sos_fade', 'SOS Fade', 770115, 10, 5),
      bot('ext_leg', 'Extreme Leg', 770117, 10, 5),
      ...(thirdDemo ? [bot('realign', 'Realign', 770118, 10, 5)] : []),
    ],
    risk_cap_pct: 10,
  })
  const liveGroup = group({
    account: LIVE,
    server: 'PUPrime-Live',
    bots: [
      bot('sos_live', 'SOS Fade live', 880115, 10, 5),
      bot('ext_live', 'Extreme Leg live', 880117, 10, 5),
    ],
    risk_cap_pct: 10,
  })
  await mock(
    page,
    [demoGroup, liveGroup],
    [
      reg(),
      reg({ account: LIVE, kind: 'live', label: 'Aaron Live', server: 'PUPrime-Live' }),
      // ⚠ Demo spare BEFORE live spare, on purpose: the page must put live first, and a fixture
      // already in that order would pass with the sort deleted.
      reg({ account: EMPTY, kind: 'demo', label: 'Spare demo' }),
      reg({ account: LIVE_EMPTY, kind: 'live', label: 'Spare live' }),
    ]
  )
  const pick = (keys: string[]) =>
    keys.filter((k) => k in earnings).map((k) => earn(k, earnings[k]))
  await page.route('**/api/bots/snapshot', (route) =>
    route.fulfill({
      json: {
        fetched_at: new Date().toISOString(),
        bots: [
          { key: 'sos_fade', name: 'SOS Fade', status: 'RUNNING', account_type: 'demo' },
          { key: 'ext_leg', name: 'Extreme Leg', status: 'RUNNING', account_type: 'demo' },
          { key: 'sos_live', name: 'SOS Fade live', status: 'RUNNING', account_type: 'live' },
          { key: 'ext_live', name: 'Extreme Leg live', status: 'STOPPED', account_type: 'live' },
          ...third,
          ...benched,
        ].map((b) => ({ ...b, ...botOver[b.key as string] })),
        scheduled_jobs: [],
        telegram: { name: 'Telegram', status: 'RUNNING' },
        earnings: [
          { ...acctEarn(ACCOUNT, pick(['sos_fade', 'ext_leg', 'realign'])), ...acctOver[ACCOUNT] },
          { ...acctEarn(LIVE, pick(['sos_live', 'ext_live'])), ...acctOver[LIVE] },
        ],
      },
    })
  )
  await page.goto('/bots')
  await expect(page.getByTestId('section-demo')).toBeVisible()
}

test('an account measured off what went IN says so, and no longer blames a deposit', async ({
  page,
}) => {
  // 🔴 2026-09-12: a $9,860.51 transfer read as +2,181.67% — the net was the balance less the
  // opening. On the deposits basis the net's referent is what went IN, and the remainder line stops
  // offering "a deposit" as a cause, because a deposit is already out of the net.
  // MUTATION: ignore `net_basis` in the account net → red on the tooltip.
  // MUTATION: keep "a deposit" in the remainder line → red on the sentence.
  await mockBothSides(page, SCORED, [], false, {
    [ACCOUNT]: {
      net_basis: 'deposits',
      capital_in: 10312.48,
      net_usd: 25,
      net_pct: 0.2,
      unattributed_usd: 25,
    },
  })
  await expect(page.getByTitle(/put in \(deposits less withdrawals\)/)).toHaveCount(1)
  await expect(page.getByText('— a manual fill, or a trade older than the record')).toBeVisible()
  // The account still on the older basis keeps its opening, so the branch is PER ACCOUNT — a page
  // that switched every account at once would pass the two lines above.
  await expect(page.getByTitle(/^Opened at /)).toHaveCount(1)
})

test('a bot whose account cannot trade says so on its row, and nothing else does', async ({
  page,
}) => {
  // 🔴 2026-09-11: the broker put the live account on read-only and no screen said so until the
  // bot halted. The bot now reads whether its account may trade, and the row carries the answer.
  // MUTATION: drop the chip from the row → red on the count.
  // MUTATION: draw it on anything but `false` → red on the count (the unasked bot's `null` is
  // "could not ask", never "off", and every other bot states nothing at all).
  await mockBothSides(
    page,
    SCORED,
    [],
    false,
    {},
    {
      sos_live: {
        trade_allowed: false,
        trade_block: 'the broker has switched trading off for this account — it is read-only',
      },
      ext_leg: { trade_allowed: null },
    }
  )
  const chip = page.getByTestId('trading-off')
  await expect(chip).toHaveCount(1)
  await expect(chip).toHaveAttribute('title', /read-only/)
})

test('with no filter, live and demo are split — every account under its own side', async ({
  page,
}) => {
  // MUTATION: file every account under one section → red on the live section's card.
  // MUTATION: draw demo before live → red on the order.
  await mockBothSides(page, SCORED)
  const live = page.getByTestId('section-live')
  const demo = page.getByTestId('section-demo')
  await expect(live.getByTestId('account-card')).toHaveCount(1)
  await expect(live.getByTestId('account-card')).toContainText(String(LIVE))
  await expect(demo.getByTestId('account-card')).toHaveCount(1)
  await expect(demo.getByTestId('account-card')).toContainText(String(ACCOUNT))
  // Real money first.
  const order = await page
    .locator('[data-testid^="section-"]')
    .evaluateAll((els) => els.map((e) => e.getAttribute('data-testid')))
  expect(order.indexOf('section-live')).toBeLessThan(order.indexOf('section-demo'))
})

test('the first look is ONLY accounts with bots — the rest is one tab away, grouped by what it is', async ({
  page,
}) => {
  // Aaron, 2026-09-10: *"when I click on this page… I just only wanna focus on the accounts that
  // have bots on them. If an account has no bots on them, then I don't care."*
  // MUTATION: draw the no-bot accounts on the Trading tab → red on the first count.
  // MUTATION: draw the benched bots on the Trading tab → red on the second.
  // MUTATION: keep the tab out of the URL → red after the reload.
  // MUTATION: drop the live-first sort → red on the order of the spares.
  await mockBothSides(page, SCORED, [
    { key: 'b_leg', name: 'B-LEG', status: 'STOPPED', account_type: 'demo' },
  ])
  await expect(page.getByTestId('tab-trading')).toHaveAttribute('aria-selected', 'true')
  await expect(page.getByTestId('account-card')).toHaveCount(2)
  await expect(page.getByTestId('empty-account')).toHaveCount(0)
  await expect(page.getByText('B-LEG')).toHaveCount(0)
  await expect(page.getByTestId('tab-unassigned')).toContainText('3')

  await page.getByTestId('tab-unassigned').click()
  await page.reload()
  await expect(page.getByTestId('tab-unassigned')).toHaveAttribute('aria-selected', 'true')
  await expect(page.getByTestId('account-card')).toHaveCount(0)
  const spares = page.getByTestId('section-no-bots').getByTestId('empty-account')
  await expect(spares).toHaveCount(2)
  await expect(spares.first()).toContainText('Spare live')
  await expect(spares.nth(1)).toContainText('Spare demo')
  await expect(page.getByTestId('section-no-account')).toContainText('B-LEG')
})

test('live and demo are two switches, both ON at first, each looking exactly as on as it is', async ({
  page,
}) => {
  // Aaron, 2026-09-10: *"both look selected by default but they are not"*, then *"I should be
  // able to turn on both live and demo at the same time."* Both sides are shown at first, so both
  // pills are ON; each switches its own side off; the last one on stays on.
  // MUTATION: start with both pills off (a pick-one filter again) → red on the first aria-pressed.
  // MUTATION: leave an on pill unfilled → red on "filled".
  // MUTATION: paint an off pill in its side's colour → red on "an off pill is grey".
  // MUTATION: let the last side on be switched off → red on "stays on".
  await mockBothSides(page, SCORED)
  const style = (l: ReturnType<Page['getByTestId']>) =>
    l.evaluate((e) => ({
      color: getComputedStyle(e).color,
      bg: getComputedStyle(e).backgroundColor,
    }))
  const live = page.getByTestId('kind-live')
  const demo = page.getByTestId('kind-demo')
  await expect(live).toHaveAttribute('aria-pressed', 'true')
  await expect(demo).toHaveAttribute('aria-pressed', 'true')
  await expect(page.getByTestId('section-live')).toBeVisible()
  await expect(page.getByTestId('section-demo')).toBeVisible()
  // On is filled, in the colour its own heading uses. Polled: the pill eases between looks.
  const heading = page.getByTestId('section-live').getByText('Live · real money')
  const liveColor = await heading.evaluate((e) => getComputedStyle(e).color)
  await expect.poll(async () => (await style(live)).color).toBe(liveColor)
  await expect.poll(async () => (await style(live)).bg).not.toBe('rgba(0, 0, 0, 0)')

  // Live OFF: its side goes, demo stays, and the page says why.
  await live.click()
  await expect(live).toHaveAttribute('aria-pressed', 'false')
  await expect(demo).toHaveAttribute('aria-pressed', 'true')
  await expect(page.getByTestId('section-live')).toHaveCount(0)
  await expect(page.getByTestId('section-demo')).toBeVisible()
  await expect(page.getByTestId('filter-note')).toContainText('Live is off')
  // Off is grey and unfilled. The pointer leaves first — a hovered off pill previews its colour.
  await page.mouse.move(0, 0)
  await expect.poll(async () => (await style(live)).bg).toBe('rgba(0, 0, 0, 0)')
  await expect.poll(async () => (await style(live)).color).not.toBe(liveColor)

  // The last side on stays on: a page switched to show nothing looks like one that failed.
  await demo.click()
  await expect(demo).toHaveAttribute('aria-pressed', 'true')
  await expect(page.getByTestId('section-demo')).toBeVisible()

  // And live switches back on beside it.
  await live.click()
  await expect(live).toHaveAttribute('aria-pressed', 'true')
  await expect(demo).toHaveAttribute('aria-pressed', 'true')
  await expect(page.getByTestId('section-live')).toBeVisible()
})

test('no fact is said twice: the heading names the side, so no card repeats it', async ({
  page,
}) => {
  // Aaron, 2026-09-10: *"we don't need to be redundant on data anywhere on this page."*
  // MUTATION: put the live/demo chip back on the account card → red on the count.
  // MUTATION: put "no bots" back on an account under "Accounts with no bots" → red.
  await mockBothSides(page, SCORED)
  await expect(page.getByTestId('account-card')).toHaveCount(2)
  await expect(page.getByTestId('account-card').getByTestId('kind-chip')).toHaveCount(0)

  // The Unassigned list mixes live and demo under one heading, so there the chip is the only
  // place a row says which — it stays, and the heading's "no bots" is not repeated on each row.
  await page.getByTestId('tab-unassigned').click()
  const spares = page.getByTestId('section-no-bots').getByTestId('empty-account')
  await expect(spares).toHaveCount(2)
  await expect(spares.getByTestId('kind-chip')).toHaveCount(2)
  await expect(spares.filter({ hasText: 'no bots' })).toHaveCount(0)
})

test('the side ahead on R PER TRADE leads — not the one with more dollars or more total R', async ({
  page,
}) => {
  // MUTATION: score sides by dollars → red (demo made $2,805 to live's $412).
  // MUTATION: score sides by total R → red (demo 3.01R to live 2.95R).
  // MUTATION: show a pooled score over ONE scored bot → red: live's +1.48R is already that bot's
  // own row, and a subtotal of one row is a copy of it.
  // ⚠ Asserted on the pooled block's own testid, never on text like "R a trade": the number and
  // the words are separate spans, so the page's text reads "+1.48Ra trade" and a text match can
  // never fail. That version SURVIVED its mutation. Demo's block is the positive control.
  await mockBothSides(page, SCORED)
  const live = page.getByTestId('score-live')
  const demo = page.getByTestId('score-demo')
  await expect(live).toHaveAttribute('data-leading', 'true')
  await expect(live.getByTestId('leading')).toBeVisible()
  await expect(demo.getByTestId('side-pooled')).toContainText('+1.00R')
  await expect(demo.getByTestId('side-pooled')).toContainText('3 trades from 2 bots')
  await expect(live.getByTestId('side-pooled')).toHaveCount(0)
  await expect(live).not.toContainText('+1.48R')
  await expect(demo).not.toHaveAttribute('data-leading', 'true')
  await expect(page.getByTestId('leading')).toHaveCount(1)
})

test('the best bot on R per trade holds the one trophy, with its sample beside it', async ({
  page,
}) => {
  // MUTATION: rank bots by dollars → red (SOS Fade's $1,500 is the most money).
  // MUTATION: rank bots by total R → red (SOS Fade live's 2.95R is the most R).
  // MUTATION: drop the Trades column → red. On one trade a lead is not a verdict, and the count
  // beside the score is the only thing on the row that says so.
  await mockBothSides(page, SCORED)
  const top = page.locator('[data-testid="per-trade"][data-top="true"]')
  await expect(top).toHaveCount(1)
  const ext = page
    .getByTestId('bot-row')
    .filter({ hasText: 'Extreme Leg' })
    .filter({ hasNotText: 'live' })
  await expect(ext.locator('[data-top="true"]')).toHaveCount(1)
  await expect(ext.getByTestId('per-trade')).toHaveText('+2.10R')
  await expect(ext.getByTestId('trades')).toHaveText('1')
})

test('one value per cell — return % and the trade count each have their own column', async ({
  page,
}) => {
  // Aaron, 2026-09-10: *"I don't want anything stacked on top of each other in columns like
  // that."* The % sat under the dollars and the count under the R, and the two stacked figures read
  // as one thing.
  // MUTATION: stack the % back under the dollars → red on the P&L cell holding only dollars.
  // MUTATION: stack the count back under the R → red on the Per trade cell holding only R.
  // MUTATION: drop the Return % column → red.
  // MUTATION: count a record holding no closed trade as "no record" → red on its "0".
  await mockBothSides(page, SCORED)
  const heads = page.getByTestId('section-demo').getByTestId('account-card').first()
  await expect(heads).toContainText('Return %')
  await expect(heads).toContainText('Trades')
  const ext = page
    .getByTestId('bot-row')
    .filter({ hasText: 'Extreme Leg' })
    .filter({ hasNotText: 'live' })
  await expect(ext.getByTestId('bot-pnl')).toHaveText('+$1,305.58')
  await expect(ext.getByTestId('return-pct')).toHaveText('+14.5%')
  await expect(ext.getByTestId('trades')).toHaveText('1')
  await expect(ext.getByTestId('per-trade')).toHaveText('+2.10R')
  // A record that was read and holds no closed trade: a measured 0, never a dash.
  const idle = page.getByTestId('bot-row').filter({ hasText: 'Extreme Leg live' })
  await expect(idle.getByTestId('trades')).toHaveText('0')
})

test('every value sits under its own heading — on a 1280px screen too', async ({ page }) => {
  // 🔴 Each row is its own grid. With the actions track sized to its content, the heading row held
  // the word "Actions" and a bot row ~185px of buttons, so at 1280px the bot row squeezed its name
  // column and every value sat ~50px left of its heading. Wide screens never showed it.
  // MUTATION: size the actions column to its content again → red on the offset.
  await page.setViewportSize({ width: 1280, height: 900 })
  await mockBothSides(page, SCORED)
  const card = page.getByTestId('section-demo').getByTestId('account-card')
  const left = (l: ReturnType<Page['getByTestId']>) =>
    l.evaluate((e) => e.getBoundingClientRect().left)
  const head = await left(card.getByText('Trades', { exact: true }))
  const cell = await left(card.getByTestId('bot-row').first().getByTestId('trades'))
  expect(Math.abs(head - cell)).toBeLessThan(2)
})

test('no side leads, and no trophy is awarded, until there is a contest', async ({ page }) => {
  // Live has nothing closed; on demo only ONE bot has a score.
  // MUTATION: count a side with no trades as 0R a trade → red: demo would "lead" a side that has
  // not traded, which is a default rather than a result.
  // MUTATION: award the trophy to a lone scored bot → red.
  await mockBothSides(page, {
    sos_fade: {},
    ext_leg: SCORED.ext_leg,
    sos_live: {},
    ext_live: {},
  })
  // Neither heading carries a number: live has nothing to pool, demo only one scored bot.
  // MUTATION: pool a single scored bot → red: demo's heading would repeat Extreme Leg's +2.10R.
  await expect(page.getByTestId('score-live').getByTestId('side-pooled')).toHaveCount(0)
  await expect(page.getByTestId('score-demo').getByTestId('side-pooled')).toHaveCount(0)
  await expect(page.getByTestId('score-demo')).not.toContainText('+2.10R')
  await expect(page.getByTestId('leading')).toHaveCount(0)
  await expect(page.locator('[data-top="true"]')).toHaveCount(0)
})

test('a side missing a bot’s record is PARTIAL and cannot lead', async ({ page }) => {
  // Demo pools two scored bots while its third record was not read. Live reads best per trade,
  // but demo's score is partial and could overtake it when the record lands.
  // MUTATION: ignore the unread record → red: live would lead against half a score.
  // MUTATION: drop the partial note → red.
  await mockBothSides(
    page,
    {
      sos_fade: SCORED.sos_fade,
      ext_leg: SCORED.ext_leg,
      sos_live: SCORED.sos_live,
      ext_live: {},
    },
    [],
    true
  )
  await expect(page.getByTestId('score-demo')).toContainText('+1.00R')
  await expect(page.getByTestId('score-demo')).toContainText('1 record not read — partial')
  await expect(page.getByTestId('leading')).toHaveCount(0)
})

test('a filter shows one side — and that side keeps its score and its lead', async ({ page }) => {
  // 🔴 Aaron, 2026-09-10: *"what is the purpose of this section? If I select demo only then it
  // goes away."* The score was a pair of tiles a filter had to remove. It sits on each side's own
  // heading now, and is scored off EVERY account, so a filter changes what is shown, never what a
  // side scored or who leads.
  // MUTATION: score sides off the FILTERED accounts → red: live alone "leads" nothing.
  // MUTATION: withhold the score line under a filter → red on both halves.
  await mockBothSides(page, SCORED)
  // Demo off → live alone.
  await page.getByTestId('kind-demo').click()
  await expect(page.getByTestId('section-live')).toBeVisible()
  await expect(page.getByTestId('section-demo')).toHaveCount(0)
  await expect(page.getByTestId('score-live')).toHaveAttribute('data-leading', 'true')

  // Demo back on, live off → demo alone.
  await page.getByTestId('kind-demo').click()
  await page.getByTestId('kind-live').click()
  await expect(page.getByTestId('section-live')).toHaveCount(0)
  await expect(page.getByTestId('score-demo')).toContainText('+1.00R')
})

/** The demo account a set went live from, after the move: no bot on it, the two that left carried
 *  as `former` rows, and the balance the last of them READ before leaving — with its time. */
const READ_AT = '2026-09-10T23:51:13+00:00'
function departedDemo(bots: ReturnType<typeof earn>[] = []) {
  const moved = { former: true, moved_to: LIVE }
  return {
    ...acctEarn(ACCOUNT, [
      ...bots,
      // A NAME unlike its key, so a page printing the key cannot pass (`recorded by …`).
      earn('sos_fade', { ...SCORED.sos_fade, ...moved, name: 'SOS Fade' }),
      earn('ext_leg', { ...SCORED.ext_leg, ...moved }),
    ]),
    balance: 15844.46,
    balance_read_at: bots.length ? null : READ_AT,
    opening_balance: 9996.99,
    opening_from: 'sos_fade',
    net_usd: 5847.47,
    net_pct: 58.49,
    attributed_usd: 2805.58,
    unattributed_usd: 3041.89,
  }
}

/** Both bots on LIVE; `demoBots` puts a NEW set on the demo account they left. */
async function mockAfterGoLive(page: Page, demoBots: ReturnType<typeof bot>[] = []) {
  const liveGroup = group({
    account: LIVE,
    server: 'PUPrime-Live',
    bots: [
      bot('sos_fade', 'SOS Fade', 770115, 10, 5),
      bot('ext_leg', 'Extreme Leg', 770117, 10, 5),
    ],
    risk_cap_pct: 10,
  })
  const groups = demoBots.length
    ? [liveGroup, group({ bots: demoBots, risk_cap_pct: 10 })]
    : [liveGroup]
  await mock(page, groups, [
    reg(),
    reg({ account: LIVE, kind: 'live', label: 'Aaron Live', server: 'PUPrime-Live' }),
  ])
  await page.route('**/api/bots/snapshot', (route) =>
    route.fulfill({
      json: {
        fetched_at: new Date().toISOString(),
        bots: [
          { key: 'sos_fade', name: 'SOS Fade', status: 'RUNNING', account_type: 'live' },
          { key: 'ext_leg', name: 'Extreme Leg', status: 'RUNNING', account_type: 'live' },
          ...demoBots.map((b) => ({
            key: b.key,
            name: b.display,
            status: 'RUNNING',
            account_type: 'demo',
            balance: 15844.46,
          })),
        ],
        scheduled_jobs: [],
        telegram: { name: 'Telegram', status: 'RUNNING' },
        earnings: [
          { ...acctEarn(LIVE, [earn('sos_fade'), earn('ext_leg')]), net_usd: 0, attributed_usd: 0 },
          departedDemo(demoBots.map((b) => earn(b.key))),
        ],
      },
    })
  )
}

test('after a move to live, the demo trades stay on DEMO and the live rows start at zero', async ({
  page,
}) => {
  // 🔴 2026-09-11, the day the demo set went live: the live account showed the bots' DEMO trades as
  // its own (+264% on a $451.97 account that had not traded). A trade belongs to the account it was
  // made on. ⚠ The earnings list is in the SERVER's order — live before demo — so a map keyed by
  // bot alone (last entry wins) hands the live rows the demo figures, which is exactly the defect.
  // MUTATION: key the earnings by bot alone → red on the live row's dollars.
  // MUTATION: leave departed bots out of the demo score → red on the demo score line.
  await mockAfterGoLive(page)
  await page.goto('/bots')

  const liveRow = page
    .getByTestId('section-live')
    .getByTestId('bot-row')
    .filter({ hasText: 'SOS Fade' })
  await expect(liveRow).toContainText('$0.00')
  await expect(liveRow).not.toContainText('$1,500.00')
  await expect(page.getByTestId('score-demo')).toContainText('+1.00R')
})

test('the demo account the bots LEFT is still an account — its balance, its record, and a way to put the next bot on it', async ({
  page,
}) => {
  // 🔴 Aaron, 2026-09-11: *"moving bots to live doesn't mean we don't trade on the demo still…
  // what if I wanted to test out more bots on a demo account while the live bot is also trading…
  // it shouldn't matter."* It was a separate "history" card — no balance, no cap, headed *no bots on
  // it now* — which read as a closed account.
  // MUTATION: drop departed-only accounts from the Trading list → red on the card count.
  // MUTATION: drop the read time beside a past balance → red on `balance-read-at`.
  // MUTATION: draw the cap chip with no bot on the account → red on its count.
  // MUTATION: drop the Add-a-bot row → red.
  // MUTATION: open the panel without the picker out → red on `add-bot-row`.
  // MUTATION: keep the account on Unassigned too → red on the empty-account count.
  await mockAfterGoLive(page)
  await page.goto('/bots')

  const card = page.getByTestId('section-demo').getByTestId('account-card')
  await expect(card).toHaveCount(1)
  await expect(card).toContainText(String(ACCOUNT))
  // The balance is the last one a bot read — shown, and said to be a reading.
  await expect(card).toContainText('$15,844.46')
  await expect(card.getByTestId('balance-read-at')).toBeVisible()
  await expect(card).toContainText('+58.5%')
  // No bot on it, so no cap to state — "no cap" in warn would be an alarm about nothing.
  await expect(card.getByTestId('cap-chip')).toHaveCount(0)
  // Its record: the two bots that left, each saying where it went, with their own figures.
  const past = card.getByTestId('past-row')
  await expect(past).toHaveCount(2)
  await expect(past.first()).toContainText(`Moved to live account ${LIVE}`)
  await expect(card).toContainText('$1,500.00')
  await expect(card).toContainText('+16.7%')

  // One place per account: it is not ALSO under Unassigned.
  await page.getByTestId('tab-unassigned').click()
  await expect(page.getByTestId('empty-account').filter({ hasText: String(ACCOUNT) })).toHaveCount(
    0
  )
  await page.getByTestId('tab-trading').click()

  // The way to put the next bot there is on the card, and it opens straight into the picker.
  await card.getByTestId('no-bot-row').getByTestId('add-bot-here').click()
  const panel = page.getByRole('complementary', { name: 'Account settings' })
  await expect(panel.getByTestId('add-bot-row')).toBeVisible()
  await expect(panel.getByTestId('drawer-balance-read-at')).toBeVisible()
  // Who recorded the opening is named, never keyed (2026-09-11: it printed `sos_fade_demo`).
  // MUTATION: print `opening_from` raw again → red.
  await expect(panel).toContainText('recorded by SOS Fade')
  await expect(panel).not.toContainText('recorded by sos_fade')
})

test('a NEW bot on the demo account keeps the departed bots on its card and in the score', async ({
  page,
}) => {
  // 🔴 It shouldn't matter: putting the next bot on demo used to DROP the departed bots' record —
  // the page read it only off an account with no bot on it — taking the demo score with it.
  // MUTATION: show the departed rows only on an account with no bot → red on the past-row count.
  // MUTATION: read the departed record into the score only with no bot on it → red on the score.
  await mockAfterGoLive(page, [bot('b_leg', 'B-LEG', 770116, 10, 5)])
  await page.goto('/bots')

  const card = page.getByTestId('section-demo').getByTestId('account-card')
  await expect(card).toHaveCount(1)
  await expect(card.getByTestId('bot-row')).toHaveCount(1)
  await expect(card.getByTestId('bot-row')).toContainText('B-LEG')
  await expect(card.getByTestId('past-row')).toHaveCount(2)
  await expect(card.getByTestId('no-bot-row')).toHaveCount(0)
  // A bot is on it now, so the balance is its live one — no read time.
  await expect(card.getByTestId('balance-read-at')).toHaveCount(0)
  await expect(page.getByTestId('score-demo')).toContainText('+1.00R')
})

test('the bot panel says only what its row does not — won/lost, and how far the record reaches', async ({
  page,
}) => {
  // Aaron, 2026-09-10: *"we don't need to be redundant on data anywhere on this page."* The panel
  // led with the dollars, the % of the account, the trade count and the R — all on the row beside it.
  // MUTATION: put the dollar figure back in the panel → red on "not the row's $1,500".
  // MUTATION: drop the won/lost split → red.
  await mockBothSides(page, SCORED)
  await page.goto('/bots?bot=sos_fade')
  const panel = page.getByRole('complementary', { name: 'SOS Fade settings' })
  const record = panel.getByTestId('bot-record')
  await expect(record).toContainText('2 / 0')
  await expect(record).toContainText('2026-09-01 → 2026-09-10')
  await expect(panel).not.toContainText('$1,500.00')
  await expect(panel).not.toContainText('of the account')
})

// ── Moving a bot between accounts ─────────────────────────────────────────────
//
// 🔴 **THE GESTURE MOVED AND THE RULES DID NOT.** Dragging a row onto an account in a rail, and
// the Move menu beside it, both went with the tab collapse on 2026-09-05 — the page is one list
// of accounts plus a drawer now, and the single control that moves a bot lives in the BOT's own
// drawer. What these checks are about is unchanged: which account a bot is moved to, and the two
// refusals that stop a move nobody could act on.
//
// 🔴 **RE-POINTED RATHER THAN DELETED, and on 2026-09-06 every one of them turned out to be
// reporting a LIVE DEFECT.** The control the collapse left behind had no running guard, offered
// an account with no terminal on the box as an ordinary choice, and could not see a registered
// account no bot was on yet. **Deleting them as rot would have deleted the evidence** — the same
// thing that had already happened one screen over to the four account safety warnings.

const OTHER = 700152905
const NO_TERM = 700119432
const EMPTY = 700104441

/**
 * Open one bot's drawer — where the version, the risk and the account selector now live.
 *
 * ⚠ **Straight to `?bot=` rather than clicking the row**, for `openAccount`'s reason: a check
 * about MOVING a bot must not also depend on the row's markup, or a layout change reddens a
 * dozen checks that are not about layout.
 */
async function openBot(page: Page, botKey: string) {
  await page.goto(`/bots?bot=${botKey}`)
  await expect(page.getByTestId(`move-${botKey}`)).toBeVisible()
}

test('a RUNNING bot cannot be moved to another account', async ({ page }) => {
  // 🔴 WATCHED RED against the page as it stood on 2026-09-06: the selector was offered
  // unconditionally, so moving a live bot took the click and came back as an error toast from
  // the server. The server does refuse it — but a page offering a control the box will reject is
  // teaching the reader that its own controls mean nothing.
  // MUTATION: drop `running` from the select's `disabled` → it enables and this goes red.
  //
  // It read its account at startup, so the write cannot reach the running process: the page would
  // show it under the new account while it went on trading the old one, which is a screen lying
  // about a live position rather than a stale setting.
  await mock(
    page,
    [group({ bots: [bot('sos_fade', 'SOS Fade', 770115, null)] })],
    [reg(), reg({ account: OTHER, label: 'ECN' })]
  )
  await openBot(page, 'sos_fade')
  await expect(page.getByTestId('move-sos_fade')).toBeDisabled()
})

test('moving a bot names the account it is joining', async ({ page }) => {
  // MUTATION: send the option's label instead of its value → the body carries a string and this
  // goes red on the account.
  let moved: { url: string; body: Record<string, unknown> } | null = null
  await mock(
    page,
    [group({ bots: [bot('b_leg', 'B-LEG', 770116, null)] })],
    [reg(), reg({ account: OTHER, label: 'ECN' })]
  )
  await page.route('**/api/bots/*/account', async (route) => {
    moved = { url: route.request().url(), body: route.request().postDataJSON() }
    return route.fulfill({
      json: {
        status: 'ok',
        changed: true,
        bot: 'b_leg',
        account: OTHER,
        restart_required: true,
        notes: [],
      },
    })
  })

  await openBot(page, 'b_leg')
  await page.getByTestId('move-b_leg').selectOption(String(OTHER))

  await expect.poll(() => moved).not.toBeNull()
  expect(moved!.url).toContain('/bots/b_leg/account')
  expect(moved!.body.account).toBe(OTHER)
})

test('an account with no terminal is offered DISABLED, with the reason on it', async ({ page }) => {
  // 🔴 WATCHED RED on 2026-09-06 — every account was offered as an ordinary enabled choice.
  // MUTATION: drop `disabled={!d.assignable}` from the option → red.
  //
  // ⚠ Hiding it would make an account that EXISTS look like one that does not, and the write
  // would otherwise be committed, pushed and pulled before failing at connect() with a message
  // about credentials — pointing whoever reads it at the password rather than at the missing
  // terminal.
  await mock(
    page,
    [group({ bots: [bot('b_leg', 'B-LEG', 770116, null)] })],
    [
      reg(),
      reg({ account: OTHER, label: 'ECN' }),
      reg({
        account: NO_TERM,
        mt5_path: '',
        assignable: false,
        unassignable_reason: 'no terminal on the VPS logged into it',
      }),
    ]
  )
  await openBot(page, 'b_leg')

  const menu = page.getByTestId('move-b_leg')
  await expect(menu.locator(`option[value="${NO_TERM}"]`)).toBeDisabled()
  // ⚠ The REASON, not merely the disabled attribute — a greyed row with no explanation reads as
  // a rendering fault, and the reader cannot tell it from an account that is simply busy.
  await expect(menu.locator(`option[value="${NO_TERM}"]`)).toContainText('no terminal')
  // …and an assignable one beside it is still offered, or the check would pass against a control
  // that disabled everything.
  await expect(menu.locator(`option[value="${OTHER}"]`)).not.toBeDisabled()
})

test('an account nobody is on YET is still offered as a destination', async ({ page }) => {
  // 🔴 WATCHED RED on 2026-09-06, and this is the defect the registry query was written to close
  // in the first place. The destinations were read off the GROUPING, which is derived from the
  // instance configs — so it can only see accounts some bot is ALREADY on, and the first bot onto
  // a newly registered account was not offered here at all. That move had to be made by
  // hand-editing a config on the trading box.
  // MUTATION: read the destinations off the grouping again → the empty account disappears, red.
  await mock(
    page,
    [group({ bots: [bot('b_leg', 'B-LEG', 770116, null)] })],
    [reg(), reg({ account: EMPTY, label: 'Standard', broker: 'PU Prime' })]
  )
  await openBot(page, 'b_leg')
  await expect(page.getByTestId('move-b_leg').locator(`option[value="${EMPTY}"]`)).toHaveCount(1)
})

// ── The page's own state, and the three-state rule on every row ───────────────

test('the account you opened survives a reload', async ({ page }) => {
  // MUTATION: hold the selection in `useState` instead of `?account=` → the reload closes the
  // drawer and this goes red. A selection that dies on refresh is one the reader re-makes every
  // time they come back to the page.
  //
  // ⚠ The rail this used to assert on is gone; the PROPERTY it was protecting is not, and it is
  // the same one `openAccount` relies on for every check in this file.
  await mock(
    page,
    [
      group({ bots: [bot('sos_fade', 'SOS Fade', 770115, null)] }),
      group({ account: OTHER, bots: [bot('b_leg', 'B-LEG', 770116, null)] }),
    ],
    [reg(), reg({ account: OTHER, label: 'ECN', broker: 'Vantage' })]
  )
  await openAccount(page, OTHER)

  const drawer = page.getByRole('complementary', { name: 'Account settings' })
  await expect(drawer).toContainText(String(OTHER))
  await page.reload()
  await expect(drawer).toContainText(String(OTHER))
})

test('a bot row opens that bot, on the panel that answers a different question', async ({
  page,
}) => {
  // MUTATION: drop the Configure button from the row → this goes red on the locator.
  //
  // The two panels are one journey: the ACCOUNT drawer decides which balance a bot spends, this
  // one decides how it trades there. ⚠ It asserts `?bot=` and NOT `?tab=configure` — the tabs
  // went on 2026-09-05, and a check still naming one would be describing a page nobody has.
  await mock(
    page,
    [group({ bots: [bot('sos_fade', 'SOS Fade', 770115, null)] })],
    [reg({ account: ACCOUNT })]
  )
  await page.goto('/bots')

  await page.getByTestId('configure-bot').first().click()
  await expect.poll(() => new URL(page.url()).searchParams.get('bot')).toBe('sos_fade')
})

test('the accounts render while the VPS snapshot is still unanswered', async ({ page }) => {
  // 🔴 WATCHED RED on 2026-09-06, and it is rule 1 on a whole page rather than on one cell. A
  // row was the SNAPSHOT row and was dropped when the snapshot did not carry it — so an account
  // whose bots the box had not answered for did not render at all, and while the trading box was
  // unreachable this page showed NO ACCOUNTS WHATSOEVER. The accounts list needs no VPS: it is
  // read from the instance configs, and reporting nothing because a different source is quiet is
  // the page telling you there are no accounts.
  // MUTATION: drop the account again when no bot is in the snapshot → red on the card.
  let release: () => void = () => {}
  const held = new Promise<void>((r) => {
    release = r
  })
  await mock(
    page,
    [group({ bots: [bot('sos_fade', 'SOS Fade', 770115, null)] })],
    [reg({ account: ACCOUNT })]
  )
  await page.route('**/api/bots/snapshot', async (route) => {
    await held
    await route.fulfill({
      json: {
        fetched_at: new Date().toISOString(),
        bots: [],
        scheduled_jobs: [],
        telegram: { name: 'Telegram', status: 'RUNNING' },
      },
    })
  })

  await page.goto('/bots')
  await expect(page.getByTestId('account-card')).toBeVisible()
  // …and the bot is on it, named off the config rather than off a reading nobody took.
  await expect(page.getByTestId('account-card').getByTestId('bot-row')).toContainText('SOS Fade')
  release()
})

test('a bot the box has not answered for reads UNKNOWN, never stopped', async ({ page }) => {
  // 🔴 WATCHED RED on 2026-09-06. The dot was `running ? green : red`, so a bot the snapshot did
  // not carry drew the same red as a bot measured to be stopped — a dead link to the VPS
  // rendering as a fleet sitting quietly, which is this repo's oldest and most expensive rule.
  // MUTATION: collapse the dot back to two states → red here, and the row offers Start again.
  //
  // ⚠ It asserts the CONTROLS too, and that half is the one that costs money: the old branch was
  // `running ? stop/restart : start`, so a bot nobody had asked about was handed a START button —
  // and starting a bot that is already trading is the one mistake this row can make.
  let release: () => void = () => {}
  const held = new Promise<void>((r) => {
    release = r
  })
  await mock(
    page,
    [group({ bots: [bot('sos_fade', 'SOS Fade', 770115, null)] })],
    [reg({ account: ACCOUNT })]
  )
  await page.route('**/api/bots/snapshot', async (route) => {
    await held
    await route.fulfill({
      json: {
        fetched_at: new Date().toISOString(),
        bots: [],
        scheduled_jobs: [],
        telegram: { name: 'Telegram', status: 'RUNNING' },
      },
    })
  })

  await page.goto('/bots')
  // ⚠ Scoped to the CARD: the no-account list renders `bot-row` too, so a page-wide locator is
  // a strict-mode violation that reads as a missing row rather than as two matches.
  const row = page.getByTestId('account-card').getByTestId('bot-row')
  const start = row.getByTitle('Start', { exact: true })

  // 🔴 **WHILE THE FIRST READ IS IN FLIGHT the row may not say `unknown` yet (repointed
  // 2026-09-10).** This check used to assert `unknown` with the snapshot still HELD — which was
  // right until the shimmer pass made "a finding may not be shown while its source is still being
  // asked" a rule, and then it failed against a page doing exactly that. The hold is kept, because
  // the still-asking moment is a real state with its own rule; the release below is what reaches
  // the state this check is named for.
  // MUTATION: drop the still-asking branch from the row's controls → `unknown` shows mid-read and
  // the first assertion goes red.
  await expect(row).toContainText('SOS Fade')
  await expect(row).not.toContainText('unknown')
  await expect(start).toHaveCount(0)

  // The box ANSWERED, and this bot was not in the answer. Now it is a finding, and it says so.
  release()
  await expect(row).toContainText('unknown')
  // ⚠ `{ exact: true }`, and it is not tidiness: Playwright's title matcher is a CASE-INSENSITIVE
  // SUBSTRING by default, so a bare 'Start' matches the uptime cell's own
  // *"how long it has been running without a re**start**"* and this check failed against a page
  // that was behaving perfectly. **A locator loose enough to match its own neighbours reports the
  // opposite of the truth** — the mirror image of the vacuous-locator trap this file records.
  await expect(start).toHaveCount(0)
})

test('a bot the box DID answer for still offers the control its state allows', async ({ page }) => {
  // The positive control, and without it the check above passes against a row that offers nothing
  // to anybody — an absent button and a withheld one are the same DOM. This file has now recorded
  // that trap five times over.
  await mock(
    page,
    [group({ bots: [bot('sos_fade', 'SOS Fade', 770115, null)] })],
    [reg({ account: ACCOUNT })]
  )
  await page.goto('/bots')

  // ⚠ Scoped to the CARD: the no-account list renders `bot-row` too, so a page-wide locator is
  // a strict-mode violation that reads as a missing row rather than as two matches.
  const row = page.getByTestId('account-card').getByTestId('bot-row')
  // The fixture's snapshot has this one RUNNING, so Stop is what it may offer — never Start.
  await expect(row.getByTitle('Stop', { exact: true })).toHaveCount(1)
  await expect(row).not.toContainText('unknown')
})

// ── 2026-09-11: the demo account, after its bots went live and two copies were added back ────
//
// Aaron's screenshots, in one pass: the Risk cap box read "Capped" UNTICKED with Save live on a
// capped account; a yellow toast named a config field; a red 502 arrived with the add's own green
// toast; the balance went blank until the new bot reported; and the copies drew at $0 beside two
// rows holding the account's whole demo record — *"they should just pick up where they left off."*

/** Every toast, kept as it APPEARS. At this spec's quick clock one lives ~0.4s, so a count taken
 *  at the end could miss one that came and went — the version spec's counter, for the same reason.
 *  ⚠ The ELEMENTS are kept, and read at the end: a detached node keeps its text, while a toast's
 *  text may not be filled in yet at the mutation that inserts it. */
async function watchToasts(page: Page) {
  await page.addInitScript(() => {
    const w = window as unknown as { __toasts: Element[] }
    w.__toasts = []
    new MutationObserver((muts) => {
      for (const m of muts)
        for (const n of m.addedNodes)
          if (n instanceof Element) {
            if (n.matches('[data-sonner-toast]')) w.__toasts.push(n)
            w.__toasts.push(...n.querySelectorAll('[data-sonner-toast]'))
          }
    }).observe(document, { childList: true, subtree: true })
  })
  return () =>
    page.evaluate(() =>
      (window as unknown as { __toasts: Element[] }).__toasts.map((t) => t.textContent ?? '')
    )
}

test('the Risk cap box FOLLOWS the account — a bot added under an open panel shows its cap', async ({
  page,
}) => {
  // 🔴 The panel copied the cap ONCE, when it opened. Opened on an empty account and then given a
  // bot at a 10% cap, it went on showing "Capped" unticked with Save live — and Save would have sent
  // "no cap" to every bot on the account. MUTATION: seed the box from the cap once (useState) → red.
  await mock(page, [BENCHED], [reg()])
  let added = false
  await page.route('**/*', async (route) => {
    const u = new URL(route.request().url())
    if (u.pathname === '/api/bots/b_leg/account') {
      added = true
      return route.fulfill({
        json: {
          status: 'ok',
          changed: true,
          deployed: true,
          bot: 'b_leg',
          account: ACCOUNT,
          restart_required: true,
          detail: 'moved',
        },
      })
    }
    // The account re-read after the add: the bot on it, at the cap it was added with.
    if (u.pathname === '/api/bots/accounts' && added) {
      return route.fulfill({
        json: [group({ bots: [bot('b_leg', 'B-LEG', 770116, 10)], risk_cap_pct: 10 })],
      })
    }
    return route.fallback()
  })
  await openAccount(page)
  await expect(page.getByTestId('cap-empty')).toBeVisible()
  await page.getByTestId('add-bot').click()
  await page.getByTestId('add-b_leg').click()

  await expect(page.getByTestId('cap-enabled')).toBeChecked()
  await expect(page.getByTestId('cap-input')).toHaveValue('10')
  await expect(page.getByTestId('cap-save')).toBeDisabled()
})

test("a move's bookkeeping is never raised — only what it could not carry is", async ({ page }) => {
  // 🔴 A yellow toast named a config field on every add of a strategy without that setting —
  // bookkeeping that cannot change how it trades. The server serves it apart as `info` now.
  // MUTATION: raise `info` as warnings too → red on the bookkeeping text.
  // MUTATION: stop raising `notes` → red on the hazard (the positive control).
  const toasts = await watchToasts(page)
  const bookkeeping = 'account_profile was not written: this strategy does not have that setting'
  const hazard = `account ${ACCOUNT} records no symbol suffix`
  await mock(page, [
    group({ bots: [bot('sos_fade', 'SOS Fade', 770115, 10)], risk_cap_pct: 10 }),
    BENCHED,
  ])
  await page.route('**/*', async (route) => {
    const u = new URL(route.request().url())
    if (u.pathname === '/api/bots/b_leg/account') {
      return route.fulfill({
        json: {
          status: 'ok',
          changed: true,
          deployed: true,
          bot: 'b_leg',
          account: ACCOUNT,
          restart_required: true,
          detail: 'moved',
          notes: [hazard],
          info: [bookkeeping],
        },
      })
    }
    return route.fallback()
  })
  await openAccount(page)
  await page.getByTestId('add-bot').click()
  await page.getByTestId('add-b_leg').click()
  await expect.poll(async () => (await toasts()).join(' | ')).toContain(hazard)
  expect((await toasts()).join(' | ')).not.toContain(bookkeeping)
})

test('a fleet read the box turned away is SAID on the page, never raised as a pop-up', async ({
  page,
}) => {
  // 🔴 The add's green toast arrived with a red "502 Cannot reach the VPS" beside it: adding a bot
  // re-reads the fleet, and that read was the one on the page that still toasted — while the page
  // already says it in its own line. MUTATION: drop `silent` from the fleet read → red on the count.
  const toasts = await watchToasts(page)
  await mock(page, STACKED)
  let reads = 0
  await page.route('**/api/bots/snapshot', (r) => {
    reads++
    return r.fulfill({
      status: 502,
      json: { detail: 'Cannot reach the VPS — Connection closed by 45.82.164.112 port 22' },
    })
  })
  await page.goto('/bots')
  await expect(page.getByText(/Could not reach the trading box/)).toBeVisible({ timeout: 20_000 })
  expect(reads, 'the fleet read really failed').toBeGreaterThan(0)
  expect(await toasts()).toEqual([])
})

/** The fleet after the set went live, with ONE bot back on the demo account and `demo` as that
 *  account's earnings — the server's answer, stated rather than derived. */
async function routeDemoBack(
  page: Page,
  demoBot: { key: string; name: string; balance: number | null },
  demo: Record<string, unknown>
) {
  await page.route('**/api/bots/snapshot', (route) =>
    route.fulfill({
      json: {
        fetched_at: new Date().toISOString(),
        bots: [
          { key: 'sos_fade', name: 'SOS Fade', status: 'RUNNING', account_type: 'live' },
          { key: 'ext_leg', name: 'Extreme Leg', status: 'RUNNING', account_type: 'live' },
          { ...demoBot, status: 'RUNNING', account_type: 'demo' },
        ],
        scheduled_jobs: [],
        telegram: { name: 'Telegram', status: 'RUNNING' },
        earnings: [
          {
            ...acctEarn(LIVE, [earn('sos_fade'), earn('ext_leg')]),
            net_usd: 0,
            attributed_usd: 0,
          },
          demo,
        ],
      },
    })
  )
}

test('a bot on the account that has not REPORTED yet leaves the last balance up, with its time', async ({
  page,
}) => {
  // 🔴 Adding the first bot blanked the demo account's balance — "balance unread · net unknown" —
  // until the new bot's first report: the last reading was used only with NO bot on the account.
  // The card, the header count and the panel each read it, so each is asserted.
  // MUTATION: the card takes the last reading only with no bot → red on the balance.
  // MUTATION: the header counts off the bots' own reports alone → red on the count.
  // MUTATION: the panel takes the last reading only with no bot → red on its read time.
  await mockAfterGoLive(page, [bot('b_leg', 'B-LEG', 770116, 10, 5)])
  await routeDemoBack(
    page,
    { key: 'b_leg', name: 'B-LEG', balance: null },
    { ...departedDemo([earn('b_leg')]), balance_read_at: READ_AT }
  )
  await page.goto('/bots')
  const card = page.getByTestId('section-demo').getByTestId('account-card')
  await expect(card).toContainText('$15,844.46')
  await expect(card.getByTestId('balance-read-at')).toBeVisible()
  await expect(card).not.toContainText('balance unread')
  await expect(page.getByText(/\d+ balances? unread/)).toHaveCount(0)

  await page.goto(`/bots?account=${ACCOUNT}`)
  const panel = page.getByRole('complementary', { name: 'Account settings' })
  await expect(panel.getByTestId('drawer-balance-read-at')).toContainText(
    'no bot here has reported one since it started'
  )
})

test("a bot that CARRIES ON a strategy's record here says whose trades its row includes", async ({
  page,
}) => {
  // 🔴 *"if I add back bots on the demo they should just pick up where they left off."* The server
  // folds a departed bot's trades here into the one bot running the same strategy now (backend
  // CLAUDE.md), so the row carries them — and names whose they are, never a count its own bot did
  // not make without saying so. MUTATION: drop the carried note from the P&L tooltip → red.
  await mockAfterGoLive(page, [bot('sos_fade_2', 'SOS Fade (demo)', 770215, 10, 5)])
  await routeDemoBack(
    page,
    { key: 'sos_fade_2', name: 'SOS Fade (demo)', balance: 15844.46 },
    {
      ...departedDemo(),
      balance_read_at: null,
      bots: [
        earn('sos_fade_2', {
          ...SCORED.sos_fade,
          name: 'SOS Fade (demo)',
          carried_from: [
            { bot_key: 'sos_fade', name: 'SOS Fade', moved_to: LIVE, closed_trades: 2 },
          ],
        }),
      ],
    }
  )
  await page.goto('/bots')
  const card = page.getByTestId('section-demo').getByTestId('account-card')
  const row = card.getByTestId('bot-row')
  await expect(row).toHaveCount(1)
  await expect(row).toContainText('$1,500.00')
  await expect(card.getByTestId('past-row')).toHaveCount(0)
  await expect(row.getByTestId('bot-pnl')).toHaveAttribute(
    'title',
    /includes 2 trades SOS Fade closed here before it moved to account 34957946/
  )
})

// ── the risk budget as ONE thing, and adding / moving without dead ends (2026-09-11) ─────────────
//
// Aaron: *"I should be able to add bots to demo and live accounts … take bots off … increase or
// lower the percentage risk on the bot … increase or lower the max percentage traded on the account
// … seamlessly, with no issues."* Each of those had a way to end in a refusal nobody could act on:
// a cap and a share on two panels behind two writes, a bot that did not fit refused after the
// click, and a live account refused outright because nothing on the page could say "yes, real
// money". These pin the ways out.
//
// ⚠ **A fail-watch against HEAD is vacuous for every one of them** (none of these controls existed),
// so non-vacuity is by MUTATION, named per check.

/** Two bots at 5% each under a 10% cap — full, and exactly fitting. */
const FULL = group({
  bots: [bot('sos_fade', 'SOS Fade', 770115, 10, 5), bot('b_leg', 'B-LEG', 770116, 10, 5)],
  risk_cap_pct: 10,
  stacked: true,
  share_total_pct: 10,
  room_pct: 0,
})

/** One bot's settings as its panel reads them, with the risk share as its one runtime row. */
function paramsWithRisk(key: string, risk: number) {
  return {
    bot_key: key,
    display_name: key,
    identity: {
      account: ACCOUNT,
      server: 'PUPrime-Demo',
      symbol: 'XAUUSD.p',
      timeframe: 'M15',
      mt5_path: 'C:\\MT5_FFT\\terminal64.exe',
      magic: 770116,
    },
    version: {
      strategy_package: key,
      strategy_class: 'C',
      strategy_version: 1,
      strategy_source_hash: 'abc',
      promoted_commit: 'c0ffee',
      promoted_at: '2026-08-05',
    },
    runtime: [
      {
        name: 'exec_risk_pct',
        value: risk,
        label: 'Risk per trade',
        group: 'Risk',
        desc: null,
        unit: '%',
        type: 'float',
        options: null,
        choices: null,
        core: true,
        editable: true,
        min: 0.1,
        max: 100,
        note: null,
      },
    ],
    strategy: [],
    notes: {},
    readme: null,
  }
}

/** Answers the move of `b_leg` and records every body, so a check can COUNT the writes. */
async function recordMoves(page: Page, account: number | null, order?: string[]) {
  const sent: Record<string, unknown>[] = []
  await page.route('**/api/bots/b_leg/account', (route) => {
    order?.push('move')
    sent.push(route.request().postDataJSON())
    return route.fulfill({
      json: {
        status: 'ok',
        changed: true,
        deployed: true,
        bot: 'b_leg',
        account,
        restart_required: true,
        detail: 'moved',
      },
    })
  })
  return sent
}

test('one Save writes a changed share AND the cap together — one body, one commit', async ({
  page,
}) => {
  // 🔴 The cap and each share lived behind two writes on two panels, and the first was often
  // refused because the second had not happened yet. The panel now edits the budget and saves once.
  // MUTATION: drop `shares` from `saveAll` → the body is the cap alone and this goes red.
  await mock(page, [FULL], [reg()])
  let sent: Record<string, unknown> | null = null
  await page.route(`**/api/bots/accounts/${ACCOUNT}/risk`, (route) => {
    sent = route.request().postDataJSON()
    return route.fulfill({
      json: plan({ changed: true, detail: `account ${ACCOUNT} — B-LEG 5% → 4%; cap 10% → 12%` }),
    })
  })

  await openAccount(page)
  await page.getByTestId('share-b_leg').fill('4')
  await page.getByTestId('cap-input').fill('12')
  // The footer says exactly what Save will write, before it writes it.
  const changes = page.getByTestId('budget-changes')
  await expect(changes).toContainText(/B-LEG\s*5%\s*→\s*4%/)
  await expect(changes).toContainText(/Cap\s*10%\s*→\s*12%/)
  await page.getByTestId('cap-save').click()
  await expect.poll(() => sent).toEqual({ risk_cap_pct: 12, shares: { b_leg: 4 }, deploy: true })
})

test('a save the server would refuse is disabled, and its one-click fix fills the draft', async ({
  page,
}) => {
  // Raising a share on a full account adds risk the cap cannot hold — the save is refused, and the
  // panel says so BEFORE the click, with the server's own fix one press away.
  // MUTATION: drop `!p.refused` from `canSave` → Save enables on a refusal and this goes red.
  // MUTATION: make "Raise the cap" a SAVE rather than a draft edit → the cap box never moves, red.
  await mock(page, [FULL], [reg()])
  await page.route('**/api/bots/accounts/*/risk-plan', (route) => {
    const body = route.request().postDataJSON() as {
      shares?: Record<string, number>
      risk_cap_pct?: number
    }
    if (body.shares?.b_leg === 8 && body.risk_cap_pct === undefined)
      return route.fulfill({
        json: plan({
          fits: false,
          reason:
            'the risk shares on this account add up to 13%, which is more than its 10% ceiling',
          refused: `Raising B-LEG to 8% puts account ${ACCOUNT} at 13% — more than its 10% cap.`,
          share_total_pct: 13,
          room_pct: -3,
          fit_cap: 13,
          fit_shares: { sos_fade: 3.84, b_leg: 6.15 },
        }),
      })
    return route.fulfill({ json: plan({ share_total_pct: 13, risk_cap_pct: 13 }) })
  })

  await openAccount(page)
  await page.getByTestId('share-b_leg').fill('8')
  await expect(page.getByTestId('plan-refused')).toContainText('more than its 10% cap')
  await expect(page.getByTestId('cap-save')).toBeDisabled()

  await page.getByTestId('fix-cap').click()
  await expect(page.getByTestId('cap-input')).toHaveValue('13')
  await expect(page.getByTestId('cap-save')).toBeEnabled()
})

test('adding a bot to a LIVE account asks first, then tells the server it was confirmed', async ({
  page,
}) => {
  // The server refuses a move onto a live account without `confirm_live` (409), and until this
  // landed nothing on the page could send it — so a bot could not be added to live at all.
  // MUTATION: skip the confirmation on a live account → the move goes out on the first click and
  // the no-write assertion goes red. MUTATION: drop `confirm_live` from the body → red on the body.
  const LIVE = 34957946
  await mock(
    page,
    [
      group({
        account: LIVE,
        server: 'PUPrime-Live',
        bots: [bot('sos_fade', 'SOS Fade', 770115, 10, 5)],
        risk_cap_pct: 10,
        share_total_pct: 5,
        room_pct: 5,
      }),
      BENCHED,
    ],
    [reg({ account: LIVE, kind: 'live', server: 'PUPrime-Live' })]
  )
  const sent = await recordMoves(page, LIVE)

  await openAccount(page, LIVE)
  await page.getByTestId('add-bot').click()
  await page.getByTestId('add-b_leg').click()
  const confirm = page.getByTestId('live-confirm')
  await expect(confirm).toContainText(`Account ${LIVE} is a LIVE account`)
  expect(sent).toHaveLength(0)

  await confirm.getByTestId('live-confirm-go').click()
  await expect.poll(() => sent[0]).toEqual({ account: LIVE, confirm_live: true, deploy: true })
})

/** A plan saying B-LEG at 10% does not fit an account with 2% free — and the server's two fixes. */
const NO_ROOM = plan({
  fits: false,
  reason: 'the risk shares on this account add up to 18%, which is more than its 10% ceiling',
  refused: `Adding B-LEG at 10% puts account ${ACCOUNT} at 18% — more than its 10% cap.`,
  share_total_pct: 18,
  room_pct: -8,
  fit_cap: 18,
  fit_shares: { sos_fade: 4.44, b_leg: 5.55 },
  bots: [
    { key: 'sos_fade', display: 'SOS Fade', before: 8, after: 8, joining: false },
    { key: 'b_leg', display: 'B-LEG', before: null, after: 10, joining: true },
  ],
})

/** One bot at 8% under a 10% cap — 2% free — and B-LEG on the bench wanting 10%. */
const TIGHT = [
  group({
    bots: [bot('sos_fade', 'SOS Fade', 770115, 10, 8)],
    risk_cap_pct: 10,
    share_total_pct: 8,
    room_pct: 2,
  }),
  BENCHED,
]

test('a bot that does not fit is offered ways to make room — here, joining at the room left', async ({
  page,
}) => {
  // It used to be refused after the click, and the fix took two writes on two panels.
  // MUTATION: read "does not fit" as a plain Add → the row says Add and this goes red.
  // MUTATION: send the bot's own share instead of the room → red on `risk_pct`.
  await mock(page, TIGHT, [reg()])
  await page.route('**/api/bots/accounts/*/risk-plan', (route) => route.fulfill({ json: NO_ROOM }))
  const sent = await recordMoves(page, ACCOUNT)

  await openAccount(page)
  await page.getByTestId('add-bot').click()
  const row = page.getByTestId('add-b_leg')
  await expect(row).toContainText('Make room')
  await row.click()
  // Opening the choices writes nothing.
  expect(sent).toHaveLength(0)
  const choices = page.getByTestId('join-choices')
  await expect(choices).toContainText('more than its 10% cap')
  await expect(choices.getByTestId('join-at-room')).toContainText('Add at 2% a trade')
  await expect(choices.getByTestId('join-raise-cap')).toContainText('18%')

  await choices.getByTestId('join-at-room').click()
  await expect.poll(() => sent[0]).toEqual({ account: ACCOUNT, risk_pct: 2, deploy: true })
})

test('raising the cap to add a bot writes the cap FIRST, then the move', async ({ page }) => {
  // The move checks the budget as it stands, so the cap has to be written before it — the other
  // order is refused for the very reason the choice exists to remove. `useJoinAccount` awaits the
  // cap write before it sends the move, so the order below is the order on the wire.
  // MUTATION: drop the cap write from the raise-cap choice → the order reads move alone, red.
  await mock(page, TIGHT, [reg()])
  await page.route('**/api/bots/accounts/*/risk-plan', (route) => route.fulfill({ json: NO_ROOM }))
  const order: string[] = []
  let capBody: Record<string, unknown> | null = null
  await page.route(`**/api/bots/accounts/${ACCOUNT}/risk`, (route) => {
    order.push('cap')
    capBody = route.request().postDataJSON()
    return route.fulfill({ json: plan({ changed: true, cap_changed: true, risk_cap_pct: 18 }) })
  })
  const moves = await recordMoves(page, ACCOUNT, order)

  await openAccount(page)
  await page.getByTestId('add-bot').click()
  await page.getByTestId('add-b_leg').click()
  await page.getByTestId('join-raise-cap').click()

  await expect.poll(() => order).toEqual(['cap', 'move'])
  expect(capBody).toEqual({ risk_cap_pct: 18, deploy: true })
  expect(moves[0]).toEqual({ account: ACCOUNT, deploy: true })
})

test("a bot's risk on an account is saved through the account's budget, after a confirm", async ({
  page,
}) => {
  // 🔴 It saved through the bot's own runtime endpoint, which refused a raise on a full account and
  // offered no way out. On an account the share is part of the budget, so it goes through the
  // budget save — where the cap can be raised in the same write.
  // MUTATION: save a bot on an account through `/runtime` → the budget body never arrives, red.
  // MUTATION: save on the first click → a write before the confirm, red on the null.
  await mock(page, [FULL], [reg()])
  await page.route('**/api/bots/b_leg/params', (route) =>
    route.fulfill({ json: paramsWithRisk('b_leg', 5) })
  )
  await page.route('**/api/bots/accounts/*/risk-plan', (route) =>
    route.fulfill({ json: plan({ share_total_pct: 9 }) })
  )
  let sent: Record<string, unknown> | null = null
  let runtimeHit = false
  await page.route(`**/api/bots/accounts/${ACCOUNT}/risk`, (route) => {
    sent = route.request().postDataJSON()
    return route.fulfill({
      json: plan({ changed: true, detail: `account ${ACCOUNT} — B-LEG 5% → 4%` }),
    })
  })
  await page.route('**/api/bots/b_leg/runtime', (route) => {
    runtimeHit = true
    return route.fulfill({ json: { status: 'ok', changed: true, detail: 'x' } })
  })

  await openBot(page, 'b_leg')
  await page.getByTestId('risk-input').fill('4')
  await expect(page.getByTestId('risk-plan')).toContainText('Fits')
  await expect(page.getByTestId('risk-plan')).toContainText('9%')
  await page.getByTestId('risk-save').click()
  await expect(page.getByTestId('risk-confirm')).toContainText(/5%\s*→\s*4%/)
  expect(sent).toBeNull()

  await page.getByTestId('risk-confirm-go').click()
  await expect.poll(() => sent).toEqual({ shares: { b_leg: 4 }, deploy: true })
  expect(runtimeHit).toBe(false)
})

test('moving a bot onto a LIVE account from its own panel asks first', async ({ page }) => {
  // The one-bot move was the unguarded second door to real money; the server now refuses it
  // without `confirm_live`. The demo move above (*names the account it is joining*) is the positive
  // control that a demo destination still moves on the pick.
  // MUTATION: drop the live branch from `pickDestination` → the move goes out on the pick, red.
  const LIVE = 34957946
  await mock(
    page,
    [group({ bots: [bot('b_leg', 'B-LEG', 770116, null)] })],
    [reg(), reg({ account: LIVE, kind: 'live', server: 'PUPrime-Live', label: 'Live' })]
  )
  const sent = await recordMoves(page, LIVE)

  await openBot(page, 'b_leg')
  await page.getByTestId('move-b_leg').selectOption(String(LIVE))
  const confirm = page.getByTestId('live-confirm')
  await expect(confirm).toContainText(`Account ${LIVE} is a LIVE account`)
  expect(sent).toHaveLength(0)

  await confirm.getByTestId('live-confirm-go').click()
  await expect.poll(() => sent[0]).toEqual({ account: LIVE, confirm_live: true, deploy: true })
})

test('a bot is taken off from the ACCOUNT panel on a second click, and never while it runs', async ({
  page,
}) => {
  // Taking a bot off was only on the bot's own panel; the account panel lists who is spending its
  // balance and now takes one off where the reader is looking.
  // MUTATION: send on the first click → red on the empty list. MUTATION: drop `running` from the
  // button's disabled → the running bot's button enables, red.
  await mock(page, STACKED)
  const sent = await recordRemovals(page)

  await openAccount(page)
  await expect(page.getByTestId('take-off-sos_fade')).toBeDisabled() // RUNNING in the snapshot
  const off = page.getByTestId('take-off-b_leg') // STOPPED
  await off.click()
  await expect(off).toHaveText('Click again')
  expect(sent).toHaveLength(0)
  await off.click()
  await expect.poll(() => sent[0]).toEqual({ account: null, deploy: true })
})
