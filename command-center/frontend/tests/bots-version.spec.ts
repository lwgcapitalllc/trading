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
    unpushed_commits: [],
    comparable: true,
    reason: '',
    changes: [
      {
        commit: 'a624d93',
        subject: 'feat(sec): one re-entry per primary',
        date: '2026-08-07',
        areas: ['engines'],
      },
    ],
    setting_changes: [
      {
        name: 'exec_time_stop_mode',
        label: 'Time stop',
        group: 'Exit ladder',
        desc: 'Close a trade that has been open for the hours below.',
        is_new: true,
        was: '',
        now: 'Before TP1 only',
        stated: false,
      },
      {
        name: 'exec_secondary',
        label: 'Secondary re-entries (1m SOS)',
        group: 'What arms a setup',
        desc: 'The 1m sniper re-entry.',
        is_new: false,
        was: 'Off',
        now: 'On',
        stated: true,
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
    strategy_package: 'sos_fade',
    strategy_class: 'SosFadeStrategy',
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

/**
 * Intercept every bot endpoint the Configure tab touches. Nothing reaches the live box.
 *
 * ⚠ **`/version` ANSWERS DIFFERENTLY AFTER A SUCCESSFUL PROMOTE, and a fixed payload would make
 * three of these checks vacuous.** `usePromoteBot` invalidates that query on success, so the real
 * banner re-reads the deployed version and re-renders off the NEW state. A mock frozen at
 * `deployed_version: 100` would leave the page saying "21 versions behind" after a deploy —
 * indistinguishable from the defect being tested — and would let the success line quote
 * `local_version` for ever without anything noticing. `landsAt` is the version the promote
 * actually reaches, which is NOT always `local_version`: see the unpushed-commits check.
 */
async function mockBot(
  page: Page,
  cmp: BotVersionCompare | null,
  opts: {
    promoteOk?: boolean
    restarted?: boolean
    landsAt?: number
  } = {}
) {
  let promoted = false
  const after = (): BotVersionCompare | null => {
    if (!cmp || !promoted) return cmp
    const at = opts.landsAt ?? cmp.local_version ?? 0
    const behind = Math.max(0, (cmp.local_version ?? 0) - at)
    return {
      ...cmp,
      deployed_version: at,
      versions_behind: behind,
      changes: behind ? cmp.changes : [],
      setting_changes: behind ? cmp.setting_changes : [],
    }
  }
  await page.route('**/api/bots/*/version', (r) => r.fulfill({ json: version(after()) }))
  await page.route('**/api/bots/*/promote/preview', (r) =>
    r.fulfill({ json: { ok: true, output: 'dry run — nothing was deployed.', restarted: false } })
  )
  await page.route('**/api/bots/*/promote', (r) => {
    if (opts.promoteOk ?? true) promoted = true
    return r.fulfill({
      json: {
        ok: opts.promoteOk ?? true,
        restarted: opts.restarted ?? true,
        output: 'pinned 556bf70c18b7 (a9bf348, 2026-08-07)',
      },
    })
  })
}

/** ⚠ Every assertion is scoped to this. The Risk-per-trade card carries its OWN `Deploy`
 *  button, so a page-wide "no deploy button" check passes against a broken banner — the
 *  vacuous-locator trap recorded in `frontend/CLAUDE.md` three times over. */
function banner(page: Page) {
  return page.getByTestId('version-banner')
}

/**
 * ⚠ **The bot is NAMED in the URL since 2026-09-04, and it has to be.** Configure and Accounts
 * merged into one Setup tab whose two panes are chosen by `?bot=`: with no bot named it shows the
 * ACCOUNTS pane, and every assertion below would fail on a missing banner rather than on anything
 * about versions. `?tab=configure` still resolves to Setup, so only the selection was missing.
 *
 * ⚠ It names `sos_fade_demo` because that is what the old `bots[0]` fallback resolved to — this
 * reproduces the previous behaviour rather than choosing a new subject, and the mocked version
 * payload above is that bot's.
 */
async function openConfigure(page: Page) {
  await page.goto('/bots?tab=setup&bot=sos_fade_demo')
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
  await mockBot(
    page,
    compare({ versions_behind: 0, deployed_version: 121, changes: [], setting_changes: [] })
  )
  await openConfigure(page)
  await expect(banner(page).getByText(/is up to date/)).toBeVisible()
  await expect(banner(page).getByRole('button', { name: /Deploy v/ })).toHaveCount(0)
  await expect(banner(page).getByRole('button', { name: /Re-deploy/ })).toBeVisible()
})

// ── refusing to answer ──────────────────────────────────────────────────────────

test('an unanswerable comparison shows the reason and NO deploy button', async ({ page }) => {
  // MUTATION: render `versions_behind ?? 0`. Zero reads as UP TO DATE — the most reassuring
  // answer available and the one most likely to be wrong. Same rule as `mt5_link`.
  await mockBot(
    page,
    compare({
      comparable: false,
      versions_behind: null,
      deployed_version: null,
      reason:
        'This machine has not fetched the commit the bot was deployed from (4e97565). Pull, then reload.',
      changes: [],
      setting_changes: [],
    })
  )
  await openConfigure(page)
  await expect(banner(page).getByText(/Version unknown/)).toBeVisible()
  await expect(banner(page).getByText(/has not fetched the commit/)).toBeVisible()
  await expect(banner(page).getByRole('button', { name: /Deploy|Re-deploy/ })).toHaveCount(0)
  await expect(banner(page).getByText(/is up to date/)).toHaveCount(0)
})

// ── what would change ───────────────────────────────────────────────────────────

test('a setting that would move is listed, and a PINNED one is listed apart from it', async ({
  page,
}) => {
  // MUTATION: filter `stated` rows out entirely. Dropping them leaves the reader unable to tell
  // "not affected" from "not checked" — and this is the one the promote preview does not report.
  await mockBot(page, compare())
  await openConfigure(page)
  await expect(banner(page).getByText('1 setting would change on this bot')).toBeVisible()
  await expect(banner(page).getByText('Time stop', { exact: true })).toBeVisible()
  await expect(banner(page).getByText(/this bot pins it, so it will not move/)).toBeVisible()
  await expect(banner(page).getByText(/Secondary re-entries \(1m SOS\) \(Off → On\)/)).toBeVisible()
})

test('a setting the deployed version never had says so — it does not claim it was Off', async ({
  page,
}) => {
  // MUTATION: render `was || 'Off'`. The old code had no such lever at all, and "Off" is the lie
  // in the safe-looking direction.
  await mockBot(page, compare())
  await openConfigure(page)
  await expect(banner(page).getByText('not in v100').first()).toBeVisible()
  await expect(banner(page).getByText(/Off\s*→\s*Before TP1 only/)).toHaveCount(0)
})

test('uncommitted edits are called out with the file named', async ({ page }) => {
  // MUTATION: drop the dirty-tree block. The backtester really is running those edits while the
  // version number beside them describes a commit, so a lab result and a deployed version can
  // silently disagree with nothing on screen accounting for it.
  //
  // 🔴 **It must NOT say a promote refuses a dirty tree, and it did until 2026-08-14.** These
  // files are on THIS machine; `promote.py::dirty_paths` runs on the VPS and measures the VPS's
  // own checkout. A promote of v168 succeeded with 54 files edited here, directly under a
  // sentence saying it would be refused.
  await mockBot(page, compare({ uncommitted_files: ['backtest/replay/loop.py'] }))
  await openConfigure(page)
  await expect(banner(page).getByText(/1 edited file/)).toBeVisible()
  await expect(banner(page).getByText(/backtest\/replay\/loop\.py/)).toBeVisible()
  await expect(banner(page).getByText(/refuses a dirty tree/)).toHaveCount(0)
})

// ── the bug Aaron hit: a finished deploy that read as a pending one ─────────────

test('a finished deploy says DEPLOYED and withdraws the deploy button', async ({ page }) => {
  // 🔴 THE REGRESSION. `output` was a bare string, so the promote's result rendered under the
  // PREVIEW's caption ("nothing deployed yet") with Deploy & restart still sitting there — Aaron
  // pressed it, it worked, and the page gave him no way to tell.
  // MUTATION: collapse `result.kind` back to a plain string.
  await mockBot(page, compare(), { promoteOk: true, restarted: true })
  await openConfigure(page)

  await banner(page)
    .getByRole('button', { name: /Deploy v100 → v121/ })
    .click()
  await expect(banner(page).getByText(/nothing deployed yet/)).toBeVisible()

  await banner(page)
    .getByRole('button', { name: /Deploy & restart/ })
    .click()
  // The confirmation is TERSE — the header beside it already reads "up to date · Deployed v121
  // · Backtester v121", and repeating the bot and the version there is what made a working
  // confirmation read as complicated.
  await expect(banner(page).getByText(/Deployed and restarted/)).toBeVisible()
  await expect(banner(page).getByText(/SOS Fade restarted/)).toHaveCount(0)
  await expect(banner(page).getByText(/nothing deployed yet/)).toHaveCount(0)
  await expect(banner(page).getByRole('button', { name: /Deploy & restart/ })).toHaveCount(0)
  await expect(banner(page).getByRole('button', { name: 'Close' })).toBeVisible()
})

test('a FAILED deploy says the bot is untouched rather than reporting a version it is not on', async ({
  page,
}) => {
  // MUTATION: branch on nothing and always print the success line. A promote that failed leaves
  // the running bot exactly as it was — saying otherwise sends somebody to debug a bot that is fine.
  await mockBot(page, compare(), { promoteOk: false, restarted: false })
  await openConfigure(page)

  await banner(page)
    .getByRole('button', { name: /Deploy v100 → v121/ })
    .click()
  await banner(page)
    .getByRole('button', { name: /Deploy & restart/ })
    .click()
  await expect(banner(page).getByText(/Deploy failed/)).toBeVisible()
  await expect(banner(page).getByText(/still on v100/)).toBeVisible()
})

test('a deploy that did NOT restart says the bot is still on the old code', async ({ page }) => {
  // MUTATION: ignore `restarted` and always claim it is running the new version. The snapshot is
  // on disk and the OLD one is still trading — the single most misleading state this page can be in.
  await mockBot(page, compare(), { promoteOk: true, restarted: false })
  await openConfigure(page)

  await banner(page)
    .getByRole('button', { name: /Deploy v100 → v121/ })
    .click()
  await banner(page)
    .getByRole('button', { name: /Deploy & restart/ })
    .click()
  await expect(banner(page).getByText(/restart .* to pick it up/)).toBeVisible()
  await expect(banner(page).getByText(/is running v121/)).toHaveCount(0)
})

// ── the accordion that would not close (2026-08-14) ─────────────────────────────
//
// Reported off the screen: *"even after I click the deploy button it always stays there enabled
// like it wants me to click it again … after deployment is successful still looks like I can
// click deploy still. The whole accordion should collapse and be back in a successful state."*

test('a successful deploy collapses the panel and stops offering the deploy it just did', async ({
  page,
}) => {
  // MUTATION: render the `<pre>` unconditionally again — it leaves the banner in its pre-deploy
  // shape under a green success line, which is what made a finished deploy read as a pending one
  // for a SECOND time.
  // ⚠ **The `!refreshing` guard on the changes block is NOT covered here, and the mutation for it
  // was RUN and stayed green.** That guard only governs the seconds between the promote returning
  // and the version refetch landing; a Playwright assertion retries until it settles, so it can
  // only ever see the settled state. Named rather than claimed.
  await mockBot(page, compare(), { promoteOk: true, restarted: true })
  await openConfigure(page)

  // The PREVIEW's output is shown without being asked for — it is what you read before deciding.
  await banner(page)
    .getByRole('button', { name: /Deploy v100 → v121/ })
    .click()
  await expect(banner(page).getByText(/dry run — nothing was deployed/)).toBeVisible()

  await banner(page)
    .getByRole('button', { name: /Deploy & restart/ })
    .click()
  await expect(banner(page).getByText(/Deployed and restarted/)).toBeVisible()

  // The banner has re-read the version and turned over to the up-to-date state.
  await expect(banner(page).getByText(/is up to date/)).toBeVisible()
  await expect(banner(page).getByRole('button', { name: /Deploy v100 → v121/ })).toHaveCount(0)
  await expect(banner(page).getByText(/setting would change on this bot/)).toHaveCount(0)
  // The promote output is no longer holding the panel open.
  await expect(banner(page).getByText(/pinned 556bf70c18b7/)).toHaveCount(0)
})

test('a preview disables the button that produced it — one live control at a time', async ({
  page,
}) => {
  // 🔴 THE SECOND HALF OF THE SAME REPORT, 2026-08-14: *"I click it. It just keeps repeating the
  // process over and over."* The top button stayed live over its own preview, so pressing it
  // re-ran the dry run and re-rendered an identical panel — indistinguishable from a dead button.
  // MUTATION: `disabled={busy}`. Goes red on the toBeDisabled line.
  await mockBot(page, compare())
  await openConfigure(page)

  const top = banner(page).getByRole('button', { name: /Deploy v100 → v121/ })
  await top.click()
  await expect(banner(page).getByText(/nothing deployed yet/)).toBeVisible()

  // The decision has moved down. Exactly one of the two is live, which is what makes the
  // two-step a confirmation rather than two ways to press the same thing.
  await expect(banner(page).getByRole('button', { name: /checked/ })).toBeDisabled()
  await expect(banner(page).getByRole('button', { name: /Deploy & restart/ })).toBeEnabled()

  // Cancel hands it back. The gate is re-runnable — the repo can move while you are reading.
  await banner(page).getByRole('button', { name: 'Cancel' }).click()
  await expect(top).toBeEnabled()
})

test('the promote output is one click away, not thrown away', async ({ page }) => {
  // MUTATION: drop the toggle and render nothing after a success. Collapsing a panel is only
  // honest if the thing collapsed can still be read — the same rule the Missed layer follows for
  // the reasons it unticks by default.
  await mockBot(page, compare(), { promoteOk: true, restarted: true })
  await openConfigure(page)

  await banner(page)
    .getByRole('button', { name: /Deploy v100 → v121/ })
    .click()
  await banner(page)
    .getByRole('button', { name: /Deploy & restart/ })
    .click()
  await expect(banner(page).getByText(/Deployed and restarted/)).toBeVisible()

  await banner(page).getByTestId('deploy-output-toggle').click()
  await expect(banner(page).getByText(/pinned 556bf70c18b7/)).toBeVisible()
})

test('a FAILED deploy keeps its output on screen without being asked', async ({ page }) => {
  // MUTATION: collapse the output on every deploy rather than on a successful one. A failure's
  // output is the only place the reason lives, so hiding it behind a click is the one case where
  // collapsing costs the reader the answer.
  await mockBot(page, compare(), { promoteOk: false, restarted: false })
  await openConfigure(page)

  await banner(page)
    .getByRole('button', { name: /Deploy v100 → v121/ })
    .click()
  await banner(page)
    .getByRole('button', { name: /Deploy & restart/ })
    .click()
  await expect(banner(page).getByText(/Deploy failed/)).toBeVisible()
  await expect(banner(page).getByText(/pinned 556bf70c18b7/)).toBeVisible()
  await expect(banner(page).getByTestId('deploy-output-toggle')).toHaveCount(0)
})

// ── the reason a successful deploy can leave a bot behind ───────────────────────
//
// 🔴 MEASURED 2026-08-14: a deploy of sos_fade_demo landed v164 while the backtester read
// v165, because the one commit between them was unpushed. The promote pulls on the VPS, so the
// remote is the ceiling — and the page said nothing, so the Deploy button looked broken.

test('unpushed commits are named, with the version a promote can actually reach', async ({
  page,
}) => {
  // MUTATION: drop the unpushed block. Every number on the banner stays correct and the reader is
  // left pressing a button that cannot change anything.
  await mockBot(
    page,
    compare({
      unpushed_commits: ['6a71a9f feat(signals): announce on the retrace'],
    })
  )
  await openConfigure(page)
  await expect(banner(page).getByText(/1 commit touching this bot is not pushed/)).toBeVisible()
  await expect(banner(page).getByText(/can only reach/)).toBeVisible()
  await expect(banner(page).getByText('v120').first()).toBeVisible()
})

test('nothing unpushed says nothing, and so does an unmeasurable upstream', async ({ page }) => {
  // MUTATION: render the block on `unpushed_commits != null` (or on length >= 0). A permanent
  // "0 commits are not pushed" line is a row nobody reads, on the banner whose whole value is
  // that every line on it means something. `null` is "no upstream to ask", not "all pushed" —
  // both are silent HERE, and collapsing them upstream is what makes the answer wrong.
  await mockBot(page, compare({ unpushed_commits: null }))
  await openConfigure(page)
  await expect(banner(page).getByText(/is 21 versions behind/)).toBeVisible()
  await expect(banner(page).getByText(/not pushed/)).toHaveCount(0)
})

test('the success line names the version that LANDED, not the one in the backtester', async ({
  page,
}) => {
  // 🔴 MEASURED 2026-08-14: it read `v{local_version}` — what the reader ASKED for — so a deploy
  // that could only reach v164 announced "running v165". Those differ exactly when the deploy
  // fell short, which is precisely when the sentence is read.
  // MUTATION: put `c.local_version` back in that line.
  await mockBot(
    page,
    compare({
      unpushed_commits: ['6a71a9f feat(signals): announce on the retrace'],
    }),
    { promoteOk: true, restarted: true, landsAt: 120 }
  )
  await openConfigure(page)

  await banner(page)
    .getByRole('button', { name: /Deploy v100 → v121/ })
    .click()
  await banner(page)
    .getByRole('button', { name: /Deploy & restart/ })
    .click()
  // ⚠ **The success line no longer names a version and this check MOVED rather than went**
  // (2026-08-14): the header carries it, so that is where the claim is now pinned. The rule is
  // unchanged and is the one that was live — a deploy that could not reach HEAD must never be
  // described as having landed there.
  await expect(banner(page).getByText(/Deployed and restarted/)).toBeVisible()
  await expect(banner(page).getByText('v120').first()).toBeVisible()
  // Nowhere on the banner does v121 read as the DEPLOYED version.
  await expect(banner(page).getByText(/running v121/)).toHaveCount(0)
  await expect(banner(page).getByText(/Deployed v121/)).toHaveCount(0)
  // And it is honest that the bot is still short of the backtester.
  await expect(banner(page).getByText(/is 1 version behind/)).toBeVisible()
})

// ── a badge that goes stale is a badge that lies ───────────────────────────────
//
// 🔴 **Reported 2026-08-28, off the screen, after a promote that had plainly worked:** the fleet
// summary read `1 restart pending` over a bot the box itself said was up to date, and `1 not
// frozen`, which meant nothing to the reader. MEASURED the same day: the deployment record and
// the running process agreed exactly, so the count was not wrong — it was OLD, and nothing was
// ever going to re-read it.
//
// 🔴 **THE STRIP THOSE CHECKS NAMED IS GONE, AND THE WARNINGS IT CARRIED WERE GOING WITH IT
// (2026-09-06).** The tab collapse left `ConfigureTab()` unrendered, so both the fleet summary and
// the deploy card under it stopped existing — and with them went the three per-bot warnings that
// say the banner's headline is FALSE. A bot promoted and never restarted showed a green *up to
// date* while the running process traded the old code, and nothing anywhere said so.
//
// ⚠ **So these are RE-POINTED onto the version banner, which is what survived**, and the rules
// are unchanged. The one check that genuinely went with the strip is named below rather than
// silently dropped.
//
// ⚠ **Every assertion is scoped to `version-banner`**, and that is not tidiness: the Risk card
// carries its own Deploy button and the drawer carries the bot's name three times over, so a
// page-wide locator matches something that is not this panel and passes against a broken one —
// the vacuous locator this folder has now recorded five times.

const restartWarn = (page: Page) => banner(page).getByTestId('banner-restart-pending')

/**
 * `/version` that reports a STALE running hash and then, after `settlesAfterMs`, a matching one —
 * i.e. a bot mid-restart that comes back.
 *
 * ⚠ **A fixed payload would make the whole point untestable.** The defect is that the page never
 * asks again; a mock that answers the same thing for ever cannot tell a page that re-read from one
 * that did not.
 */
async function mockRestartSettling(
  page: Page,
  settlesAfterMs: number,
  over: { frozen?: boolean } = {}
) {
  // ⚠ **The clock starts at the FIRST REQUEST, not at registration**, and that is not a detail.
  // Anchoring it here costs the page's whole boot — navigation, the bot snapshot, then the version
  // queries — so a 3s window had already elapsed before anything asked, the first answer came back
  // SETTLED, and the check failed on its opening assertion having proved nothing. A fixture that
  // measures from a moment the subject has not reached yet is a fixture testing its own timing.
  let firstAskedAt: number | null = null
  await page.route('**/api/bots/*/version', (r) => {
    firstAskedAt ??= Date.now()
    const settled = Date.now() - firstAskedAt > settlesAfterMs
    const v = version(
      compare({ versions_behind: 0, deployed_version: 121, changes: [], setting_changes: [] })
    )
    return r.fulfill({
      json: {
        ...v,
        ...over,
        // The live process reports a 12-char prefix of the deployed hash. A DIFFERENT one is the
        // whole restart-pending condition.
        running_hash: settled ? v.hash.slice(0, 12) : 'c1d3337df643',
      },
    })
  })
  await page.route('**/api/bots/*/promote/preview', (r) =>
    r.fulfill({ json: { ok: true, output: 'dry run', restarted: false } })
  )
}

test('a restart-pending warning clears ITSELF once the bot comes back — no reload', async ({
  page,
}) => {
  // 🔴 The reported bug, and the one check here with a CLEAN fail-watch: with the version query's
  // `refetchInterval` removed the warning sticks at its first reading for ever and the second
  // assertion times out. Nothing about the locator can make that pass.
  // ⚠ It asserts the TRANSITION rather than a count, so the size of the registry cannot break it.
  await mockRestartSettling(page, 3_000)
  await openConfigure(page)

  await expect(restartWarn(page)).toBeVisible()
  // No reload, no click, no navigation — the poll is the only thing that can move this.
  await expect(restartWarn(page)).toHaveCount(0, { timeout: 30_000 })
})

test('a restart-pending bot is NOT reported as up to date', async ({ page }) => {
  // 🔴 WATCHED RED on 2026-09-06 and this is the defect the re-point exposed. The banner's
  // headline compares the DEPLOYED version to the backtester's, which agree the moment a promote
  // lands — so it says *up to date* while the running process is still on the old code, and the
  // only thing that ever contradicted it lived in a card nothing renders any more.
  // MUTATION: drop the restart-pending block from the banner → the headline stands alone, red.
  await mockRestartSettling(page, 999_000)
  await openConfigure(page)

  await expect(banner(page).getByText(/is up to date/)).toBeVisible()
  // …and directly under it, the sentence that says the headline is not the whole truth.
  await expect(restartWarn(page)).toContainText(/still trading/)
})

test('it says NEVER DEPLOYED, never "not frozen"', async ({ page }) => {
  // 🔴 Aaron, 2026-08-28: *"1 not frozen — idk what that even means"*. "Frozen" is the word for the
  // MECHANISM (a deployed bot runs a frozen snapshot) and says nothing about the bot. What is true
  // is that nobody ever deployed it, so there is no pinned version and a pull on the box changes
  // what it trades.
  // MUTATION: put the old label back — the first assertion goes red on the absent warning and the
  // second on the resurrected wording.
  await mockRestartSettling(page, 999_000, { frozen: false })
  await openConfigure(page)

  await expect(banner(page).getByTestId('banner-never-deployed')).toContainText(/Never deployed/)
  await expect(banner(page).getByText(/not frozen/i)).toHaveCount(0)
})

// 🔴 **DELETED 2026-09-06 rather than re-pointed: *a non-zero count is a button that goes to the
// bot it is counting*.** It was about a FLEET summary — a count naming a condition and a number,
// where answering *which bot?* meant clicking every row of a rail — and that summary is gone with
// the tabs. The question it existed to answer no longer arises: these warnings render inside ONE
// bot's own drawer, so the bot is already selected and there is nowhere for a count to navigate.
//
// ⚠ **Recorded rather than removed silently.** The RULE behind it is live and applies to the next
// roll-up anybody builds: a count that names a condition without naming its subject has moved the
// question rather than answered it, and a zero must stay a plain span, because a button that
// navigates nowhere reads as a broken page.
