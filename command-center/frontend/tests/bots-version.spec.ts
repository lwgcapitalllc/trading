/**
 * The Bots page's version banner — "am I behind, and by how much".
 *
 * The subject is the question that tab exists for and could not answer until 2026-08-07: the
 * version row read `v0`, because `strategy_version` defaults to 0 in `algos/live/live_config.py`
 * and nothing has ever written it. Aaron: *"I just wanna know what is the version that I have
 * compiled in my backtester versus the version that is deployed... and if I'm behind, there should
 * be a big nice button."*
 *
 * ⚠ A fail-watch against HEAD is VACUOUS here — the banner did not exist, so every check goes red
 * for the trivial reason that the element is absent, which proves the locator and nothing else.
 * Non-vacuity is established by MUTATION instead, and the mutations are named per check.
 *
 * ⚠ Like `calendar.spec.ts` this needs NO BACKEND and no VPS — the two bot endpoints are
 * intercepted whole. That matters more here than anywhere: the real `/version` route SSHes to the
 * live trading box, and `/promote` deploys code onto it.
 */
import { test, expect, type Page } from '@playwright/test'
import type { BotDeployedVersion, BotVersionCompare } from '../src/types'

// ── fixture ─────────────────────────────────────────────────────────────────────

function compare(over: Partial<BotVersionCompare> = {}): BotVersionCompare {
  return {
    deployed_version: 100,
    local_version: 121,
    versions_behind: 21,
    uncommitted_files: [],
    comparable: true,
    reason: '',
    changes: [
      { commit: 'a624d93', subject: 'feat(sec): one re-entry per primary', date: '2026-08-07', areas: ['engines'] },
    ],
    setting_changes: [
      {
        name: 'exec_time_stop_mode', label: 'Time stop', group: 'Exit ladder',
        desc: 'Close a trade that has been open for the hours below.',
        is_new: true, was: '', now: 'Before TP1 only', stated: false,
      },
      {
        name: 'exec_secondary', label: 'Secondary re-entries (1m SOS)', group: 'What arms a setup',
        desc: 'The 1m sniper re-entry.',
        is_new: false, was: 'Off', now: 'On', stated: true,
      },
    ],
    ...over,
  }
}

function version(cmp: BotVersionCompare | null): BotDeployedVersion {
  return {
    frozen: true,
    hash: 'fbf3b94bebf0b96e1d9f238b982dcb9c',
    commit: '4e97565',
    promoted_at: '2026-08-05',
    strategy_package: 'mpc_sos_fade',
    strategy_class: 'MpcSosFadeStrategy',
    strategy_version: 0,
    files: 97,
    params: {},
    repo_commit: 'a9bf348',
    commits_ahead: 71,
    snapshot_ok: true,
    running_hash: 'fbf3b94bebf0b96e1d9f238b982dcb9c',
    params_drift: [],
    compare: cmp,
  }
}

/** Intercept every bot endpoint the Configure tab touches. Nothing reaches the live box. */
async function mockBot(page: Page, cmp: BotVersionCompare | null, opts: {
  promoteOk?: boolean; restarted?: boolean
} = {}) {
  await page.route('**/api/bots/*/version', r =>
    r.fulfill({ json: version(cmp) }))
  await page.route('**/api/bots/*/promote/preview', r =>
    r.fulfill({ json: { ok: true, output: 'dry run — nothing was deployed.', restarted: false } }))
  await page.route('**/api/bots/*/promote', r =>
    r.fulfill({
      json: {
        ok: opts.promoteOk ?? true,
        restarted: opts.restarted ?? true,
        output: 'pinned 556bf70c18b7 (a9bf348, 2026-08-07)',
      },
    }))
}

/** ⚠ Every assertion is scoped to this. The Risk-per-trade card carries its OWN `Deploy`
 *  button, so a page-wide "no deploy button" check passes against a broken banner — the
 *  vacuous-locator trap recorded in `frontend/CLAUDE.md` three times over. */
function banner(page: Page) {
  return page.getByTestId('version-banner')
}

async function openConfigure(page: Page) {
  await page.goto('/bots?tab=configure')
  await expect(banner(page)).toBeVisible({ timeout: 20_000 })
}

// ── the headline ────────────────────────────────────────────────────────────────

test('it says how many versions behind, and names both versions', async ({ page }) => {
  // MUTATION: render `v{v.strategy_version}` (the dead field) instead of the compare numbers.
  await mockBot(page, compare())
  await openConfigure(page)
  await expect(banner(page).getByText(/is 21 versions behind/)).toBeVisible()
  await expect(banner(page).getByText('v100').first()).toBeVisible()
  await expect(banner(page).getByText('v121').first()).toBeVisible()
})

test('the deploy button names the version it would move the bot to', async ({ page }) => {
  // MUTATION: label the button a bare "Promote". The whole complaint was that the old control
  // said nothing about what it would change.
  await mockBot(page, compare())
  await openConfigure(page)
  await expect(banner(page).getByRole('button', { name: /Deploy v100 → v121/ })).toBeVisible()
})

test('an up-to-date bot offers no prominent deploy, only a quiet re-deploy', async ({ page }) => {
  // MUTATION: drop the `behind > 0` branch so the amber button renders unconditionally — a page
  // permanently urging a deploy is one nobody reads.
  await mockBot(page, compare({ versions_behind: 0, deployed_version: 121, changes: [], setting_changes: [] }))
  await openConfigure(page)
  await expect(banner(page).getByText(/is up to date/)).toBeVisible()
  await expect(banner(page).getByRole('button', { name: /Deploy v/ })).toHaveCount(0)
  await expect(banner(page).getByRole('button', { name: /Re-deploy/ })).toBeVisible()
})

// ── refusing to answer ──────────────────────────────────────────────────────────

test('an unanswerable comparison shows the reason and NO deploy button', async ({ page }) => {
  // MUTATION: render `versions_behind ?? 0`. Zero reads as UP TO DATE — the most reassuring
  // answer available and the one most likely to be wrong. Same rule as `mt5_link`.
  await mockBot(page, compare({
    comparable: false, versions_behind: null, deployed_version: null,
    reason: 'This machine has not fetched the commit the bot was deployed from (4e97565). Pull, then reload.',
    changes: [], setting_changes: [],
  }))
  await openConfigure(page)
  await expect(banner(page).getByText(/Version unknown/)).toBeVisible()
  await expect(banner(page).getByText(/has not fetched the commit/)).toBeVisible()
  await expect(banner(page).getByRole('button', { name: /Deploy|Re-deploy/ })).toHaveCount(0)
  await expect(banner(page).getByText(/is up to date/)).toHaveCount(0)
})

// ── what would change ───────────────────────────────────────────────────────────

test('a setting that would move is listed, and a PINNED one is listed apart from it', async ({ page }) => {
  // MUTATION: filter `stated` rows out entirely. Dropping them leaves the reader unable to tell
  // "not affected" from "not checked" — and this is the one the promote preview does not report.
  await mockBot(page, compare())
  await openConfigure(page)
  await expect(banner(page).getByText('1 setting would change on this bot')).toBeVisible()
  await expect(banner(page).getByText('Time stop', { exact: true })).toBeVisible()
  await expect(banner(page).getByText(/this bot pins it, so it will not move/)).toBeVisible()
  await expect(banner(page).getByText(/Secondary re-entries \(1m SOS\) \(Off → On\)/)).toBeVisible()
})

test('a setting the deployed version never had says so — it does not claim it was Off', async ({ page }) => {
  // MUTATION: render `was || 'Off'`. The old code had no such lever at all, and "Off" is the lie
  // in the safe-looking direction.
  await mockBot(page, compare())
  await openConfigure(page)
  await expect(banner(page).getByText('not in v100').first()).toBeVisible()
  await expect(banner(page).getByText(/Off\s*→\s*Before TP1 only/)).toHaveCount(0)
})

test('uncommitted edits are called out with the file named', async ({ page }) => {
  // MUTATION: drop the dirty-tree block. `promote.py` refuses a dirty tree, so without this the
  // reader meets that refusal with no explanation — and the backtester really is running those
  // edits while the version number describes a commit.
  await mockBot(page, compare({ uncommitted_files: ['backtest/replay/loop.py'] }))
  await openConfigure(page)
  await expect(banner(page).getByText(/1 edited file/)).toBeVisible()
  await expect(banner(page).getByText(/backtest\/replay\/loop\.py/)).toBeVisible()
})

// ── the bug Aaron hit: a finished deploy that read as a pending one ─────────────

test('a finished deploy says DEPLOYED and withdraws the deploy button', async ({ page }) => {
  // 🔴 THE REGRESSION. `output` was a bare string, so the promote's result rendered under the
  // PREVIEW's caption ("nothing deployed yet") with Deploy & restart still sitting there — Aaron
  // pressed it, it worked, and the page gave him no way to tell.
  // MUTATION: collapse `result.kind` back to a plain string.
  await mockBot(page, compare(), { promoteOk: true, restarted: true })
  await openConfigure(page)

  await banner(page).getByRole('button', { name: /Deploy v100 → v121/ }).click()
  await expect(banner(page).getByText(/nothing deployed yet/)).toBeVisible()

  await banner(page).getByRole('button', { name: /Deploy & restart/ }).click()
  await expect(banner(page).getByText(/Deployed — .* restarted and is running v121/)).toBeVisible()
  await expect(banner(page).getByText(/nothing deployed yet/)).toHaveCount(0)
  await expect(banner(page).getByRole('button', { name: /Deploy & restart/ })).toHaveCount(0)
  await expect(banner(page).getByRole('button', { name: 'Close' })).toBeVisible()
})

test('a FAILED deploy says the bot is untouched rather than reporting a version it is not on', async ({ page }) => {
  // MUTATION: branch on nothing and always print the success line. A promote that failed leaves
  // the running bot exactly as it was — saying otherwise sends somebody to debug a bot that is fine.
  await mockBot(page, compare(), { promoteOk: false, restarted: false })
  await openConfigure(page)

  await banner(page).getByRole('button', { name: /Deploy v100 → v121/ }).click()
  await banner(page).getByRole('button', { name: /Deploy & restart/ }).click()
  await expect(banner(page).getByText(/Deploy failed/)).toBeVisible()
  await expect(banner(page).getByText(/still on v100/)).toBeVisible()
})

test('a deploy that did NOT restart says the bot is still on the old code', async ({ page }) => {
  // MUTATION: ignore `restarted` and always claim it is running the new version. The snapshot is
  // on disk and the OLD one is still trading — the single most misleading state this page can be in.
  await mockBot(page, compare(), { promoteOk: true, restarted: false })
  await openConfigure(page)

  await banner(page).getByRole('button', { name: /Deploy v100 → v121/ }).click()
  await banner(page).getByRole('button', { name: /Deploy & restart/ }).click()
  await expect(banner(page).getByText(/restart .* to pick it up/)).toBeVisible()
  await expect(banner(page).getByText(/is running v121/)).toHaveCount(0)
})
