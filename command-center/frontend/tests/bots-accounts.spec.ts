import { test, expect, Page } from '@playwright/test'
import { refuseLiveWrites } from './fixtures'

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
  await refuseLiveWrites(page)
  await page.route('**/*', async (route) => {
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

test('saving a cap says a restart is needed, never that it applied', async ({ page }) => {
  // A written cap is not a running cap — it is read by the order bridge at startup only. This is
  // the one state that reads as protected and is not.
  // MUTATION: drop `restart_required` from the toast wording → red.
  await mock(page, STACKED)
  let sent: Record<string, unknown> | null = null
  await page.route('**/*', async (route) => {
    const u = new URL(route.request().url())
    if (u.pathname === `/api/bots/accounts/${ACCOUNT}/risk-cap`) {
      sent = route.request().postDataJSON()
      return route.fulfill({
        json: {
          status: 'ok',
          changed: true,
          deployed: true,
          updated: ['sos_fade', 'b_leg'],
          restart_required: true,
          bots: ['sos_fade', 'b_leg'],
          detail: `account ${ACCOUNT} risk cap → 20%`,
        },
      })
    }
    return route.fallback()
  })

  await openAccount(page)
  await page.getByTestId('cap-input').fill('20')
  await page.getByTestId('cap-save').click()

  await expect(page.getByText(/restart them to apply/i)).toBeVisible()
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
    if (u.pathname === `/api/bots/accounts/${ACCOUNT}/risk-cap`) {
      sent = route.request().postDataJSON()
      return route.fulfill({
        json: {
          status: 'ok',
          changed: true,
          updated: ['sos_fade'],
          restart_required: true,
          bots: ['sos_fade'],
          detail: 'uncapped',
        },
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

  const broken = page.getByTestId('bot-row-broken')
  await expect(broken).toHaveCount(1)
  await expect(broken).toContainText('B-LEG')
  // …and it is NOT offered the control that reads the very file that cannot be read.
  await expect(broken.getByTestId('configure-bot')).toHaveCount(0)
  // The benched list is empty here, so nothing tells the reader to give this bot an account.
  await expect(page.getByText('Not on an account')).toHaveCount(0)
})

test('a benched bot IS told to be given an account', async ({ page }) => {
  // The positive control for the check above — without it a page that simply dropped both lists
  // would pass, because an absent row and a correctly-filed one are the same DOM.
  await mock(page, [
    group({ bots: [bot('sos_fade', 'SOS Fade', 770115, 10)], risk_cap_pct: 10 }),
    BENCHED,
  ])
  await page.goto('/bots')

  await expect(page.getByText('Not on an account')).toBeVisible()
  await expect(page.getByTestId('bot-row-broken')).toHaveCount(0)
})

test('a benched bot is offered as something to add, and says where it comes from', async ({
  page,
}) => {
  // MUTATION: build the candidate list from the account's own bots → the list is empty and the
  // "nothing to add" message renders instead.
  await mock(page, [
    group({ bots: [bot('sos_fade', 'SOS Fade', 770115, 10)], risk_cap_pct: 10 }),
    BENCHED,
  ])
  // ⚠ Re-pointed 2026-09-06: the control moved from a card in a rail into the ACCOUNT drawer,
  // and the candidate list itself (`AddBotRow`) is the same component it always was.
  await openAccount(page)
  await page.getByTestId('add-bot').click()
  await expect(page.getByTestId('add-b_leg')).toBeVisible()
  await expect(page.getByTestId('add-b_leg')).toContainText('not on an account')
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

  // ⚠ Re-pointed 2026-09-06. The account card's own Remove button went with the tab collapse;
  // taking a bot OFF an account is the same write from the other side, and it is now the last
  // option in the bot's own account selector. **The RULE is untouched and is the whole check:
  // `null` is the only spelling of "on no account" — `0` is not an account, and omitting the
  // field reads to the backend as no change at all.**
  await openBot(page, 'b_leg')
  await page.getByTestId('move-b_leg').selectOption('')
  await expect.poll(() => sent).toEqual({ account: null, deploy: true })
  await expect(page.getByText(/will not start until it is on one again/i)).toBeVisible()
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
  await expect(page.getByTestId('no-candidates')).toContainText('already on this account')
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

test('a registered account with NO bots can still be OPENED and added to', async ({ page }) => {
  // 🔴 WATCHED RED on 2026-09-06, and it is the registry's whole purpose re-broken. The drawer
  // rendered only for an account in the GROUPING — which is derived from the instance configs and
  // therefore holds only accounts a bot is ALREADY on — so the one account that most needs the
  // Add bot control could not be opened at all.
  // MUTATION: require the grouping again → the drawer never renders and this goes red.
  await mock(page, [], [reg()])
  await openAccount(page)

  await expect(page.getByTestId('no-bots')).toContainText('trades nothing')
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

  await page.goto('/bots')
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
  await page.route('**/api/bots/accounts/registry/**', async (route) => {
    if (route.request().method() !== 'PUT') return route.fallback()
    body = route.request().postDataJSON()
    return route.fulfill({ json: reg() })
  })

  await page.goto('/bots')
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
  await expect(row).toContainText('unknown')
  // ⚠ `{ exact: true }`, and it is not tidiness: Playwright's title matcher is a CASE-INSENSITIVE
  // SUBSTRING by default, so a bare 'Start' matches the uptime cell's own
  // *"how long it has been running without a re**start**"* and this check failed against a page
  // that was behaving perfectly. **A locator loose enough to match its own neighbours reports the
  // opposite of the truth** — the mirror image of the vacuous-locator trap this file records.
  await expect(row.getByTitle('Start', { exact: true })).toHaveCount(0)
  release()
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
