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
 * ⚠ Like `calendar.spec.ts` the bot endpoints it acts through are intercepted whole. That matters
 * more here than anywhere: the real `/version` route SSHes to the live trading box, and
 * `/promote/job` deploys code onto it — which is why the whole page runs OFFLINE (offline.ts).
 */
import { expect, type Page } from '@playwright/test'
import type {
  BotDeployedVersion,
  BotPromoteJob,
  BotRunningCode,
  BotSnapshot,
  BotStatus,
  BotVersionCompare,
} from '../src/types'
import { offlineTest } from './offline'

// OFFLINE (2026-09-10): every read this page makes beyond the two routed below is answered from
// `recordings/bots-page.json`, and anything else is aborted and fails the check — see offline.ts.
// Before this the snapshot and the health dots were read off the REAL backend, which reached the
// live trading box on every check and cost ~4s of SSH each.
const { test, recorded } = offlineTest('bots-page', { clockFactor: 10 })

/**
 * The bot snapshot, with `sos_fade_demo` on the account type THIS check needs.
 *
 * ⚠ Stated, never inherited: the recording holds whatever the box said the day it was taken — on
 * 2026-09-10 that was a LIVE account — and every check here except the live one is about a demo.
 */
async function pinSnapshot(page: Page, live = false, bot: Partial<BotStatus> = {}) {
  await page.route('**/api/bots/snapshot', (r) => {
    const snap = recorded<BotSnapshot>('/bots/snapshot')
    for (const b of snap.bots)
      if (b.key === 'sos_fade_demo') Object.assign(b, { account_type: live ? 'live' : 'demo' }, bot)
    return r.fulfill({ json: snap })
  })
}

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

function version(
  cmp: BotVersionCompare | null,
  runningCode: BotRunningCode | null = null
): BotDeployedVersion {
  return {
    running_code: runningCode,
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
 * How a scripted deploy JOB ends. The page reads `GET /promote/job` once a second and each read
 * here advances one step, so the progress readout is driven the way the backend drives it — step
 * by step — rather than jumping straight to an answer.
 */
type JobPlan = {
  /** `done` (default), `refused` (promote.py said no), or `raised` (the box dropped mid-stop). */
  outcome?: 'done' | 'refused' | 'raised'
  restarted?: boolean
  confirm?: 'done' | 'unconfirmed'
  /** Stop advancing with this step ACTIVE, for ever. A check about what the panel looks like
   *  MID-deploy must read it while one is running — racing a job that advances every second can
   *  pass because the deploy already finished, which is a check the defect cannot fail. */
  holdAt?: (typeof STEP_KEYS)[number]
}

const STEP_KEYS = ['pull', 'build', 'stop', 'start', 'confirm'] as const

function jobFrames(plan: JobPlan): BotPromoteJob[] {
  const outcome = plan.outcome ?? 'done'
  const restarted = plan.restarted ?? true
  // How far the job gets before it ends.
  const reach = outcome === 'refused' ? 1 : outcome === 'raised' ? 2 : restarted ? 4 : 1
  const frame = (active: number): BotPromoteJob => ({
    job_id: 'pj_test',
    bot: 'sos_fade_demo',
    status: 'running',
    seconds: active * 3 + 1,
    result: null,
    error: null,
    stages: STEP_KEYS.map((key, i) => ({
      key,
      state: i < active ? 'done' : i === active ? 'active' : 'pending',
      seconds: i <= active ? 3 : null,
    })),
  })
  const frames = Array.from({ length: reach + 1 }, (_, i) => frame(i))
  if (plan.holdAt) return frames.slice(0, STEP_KEYS.indexOf(plan.holdAt) + 1)
  const last = frames[frames.length - 1]
  const settled: BotPromoteJob = {
    ...last,
    status: outcome === 'done' ? 'done' : 'failed',
    result:
      outcome === 'raised'
        ? null
        : {
            ok: outcome === 'done',
            restarted: outcome === 'done' && restarted,
            output:
              outcome === 'refused'
                ? 'Refusing to promote — the staged snapshot does not import\n  pinned 556bf70c18b7'
                : 'pinned 556bf70c18b7 (a9bf348, 2026-08-07)',
          },
    error:
      outcome === 'raised'
        ? 'Stopping the bot could not reach the trading box. The new code IS deployed; check the bot.'
        : null,
    stages: last.stages.map((s, i) => ({
      ...s,
      state:
        i < reach
          ? 'done'
          : i === reach
            ? outcome === 'done'
              ? s.key === 'confirm'
                ? plan.confirm === 'unconfirmed'
                  ? 'unconfirmed'
                  : 'done'
                : 'done'
              : 'failed'
            : 'skipped',
    })),
  }
  return [...frames, settled]
}

/**
 * Intercept every bot endpoint the deploy panel touches. Nothing reaches the live box.
 *
 * 🔴 **The deploy is a POST that, unrouted, would deploy code onto the live trading box.** The
 * offline backend (`offlineTest`, registered before any of these) aborts anything not answered
 * here and fails the check naming it, so a write this spec forgot to route cannot leave the page.
 *
 * ⚠ **`/version` ANSWERS DIFFERENTLY AFTER A SUCCESSFUL DEPLOY, and a fixed payload would make
 * several of these checks vacuous.** The job's finish invalidates that query, so the real banner
 * re-reads the deployed version and re-renders off the NEW state. A mock frozen at
 * `deployed_version: 100` would leave the page saying "21 versions behind" after a deploy —
 * indistinguishable from the defect being tested. `landsAt` is the version the deploy actually
 * reaches, which is NOT always `local_version`: see the unpushed-commits check.
 *
 * ⚠ **Only `sos_fade_demo` has a deploy (2026-09-10).** The page watches EVERY bot's job, so a
 * script answered to all of them would put every row mid-deploy and step the frames once per bot.
 */
async function mockBot(
  page: Page,
  cmp: BotVersionCompare | null,
  opts: JobPlan & {
    landsAt?: number
    /** A job already RUNNING when the page opens — the drawer reopened mid-deploy. HELD on its
     *  first step until `release()`: the page watches deploys from load, so a job that advanced
     *  through the snapshot's few seconds could finish before the drawer ever opened. */
    runningOnOpen?: boolean
    /** Put the bot on a LIVE account (the RECORDED snapshot, mutated — never a hand-written one). */
    live?: boolean
    /** Hold the version re-read a deploy's finish triggers — the window where every readout
     *  would otherwise still describe the state before the deploy. */
    reReadDelayMs?: number
    /** The bot's own report, stated rather than inherited from the recording. */
    bot?: Partial<BotStatus>
    /** What the bot's current run started on, against what a restart would load. */
    runningCode?: BotRunningCode
  } = {}
) {
  await pinSnapshot(page, !!opts.live, opts.bot)
  let promoted = false
  let frames: BotPromoteJob[] | null = opts.runningOnOpen ? jobFrames(opts) : null
  let idx = 0
  let held = !!opts.runningOnOpen
  const posts: string[] = []
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
  await page.route('**/api/bots/*/version', async (r) => {
    if (promoted && opts.reReadDelayMs)
      await new Promise((ok) => setTimeout(ok, opts.reReadDelayMs))
    return r.fulfill({ json: version(after(), opts.runningCode ?? null) })
  })
  await page.route('**/api/bots/*/promote/job', (r) => {
    if (!r.request().url().includes('/bots/sos_fade_demo/')) {
      return r.request().method() === 'GET' ? r.fulfill({ json: null }) : r.fallback()
    }
    if (r.request().method() === 'POST') {
      posts.push(r.request().url())
      frames = jobFrames(opts)
      idx = 1
      return r.fulfill({ status: 202, json: frames[0] })
    }
    if (!frames) return r.fulfill({ json: null })
    if (held) return r.fulfill({ json: frames[0] })
    const f = frames[Math.min(idx, frames.length - 1)]
    idx++
    if (f.status === 'done') promoted = true
    return r.fulfill({ json: f })
  })
  return { posts, release: () => (held = false) }
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

/** The version pill on `sos_fade_demo`'s ROW — outside the drawer, so it answers with it closed. */
const rowPill = (page: Page) =>
  page.locator('[data-testid="bot-row"][data-bot="sos_fade_demo"] [data-testid="version-pill"]')

/**
 * Record every state the row's pill passes through, from now on. A check that reads the pill at
 * one moment can land either side of a flash that lasts one SSH round trip, and pass on luck.
 */
async function recordPillStates(page: Page) {
  await expect(rowPill(page)).toBeVisible()
  await page.evaluate(() => {
    const w = window as unknown as { __pill: string[] }
    w.__pill = []
    const row = document.querySelector('[data-testid="bot-row"][data-bot="sos_fade_demo"]')!
    const read = () => {
      const s =
        row.querySelector('[data-testid="version-pill"]')?.getAttribute('data-state') ?? 'none'
      if (w.__pill[w.__pill.length - 1] !== s) w.__pill.push(s)
    }
    read()
    new MutationObserver(read).observe(row, { subtree: true, childList: true, attributes: true })
  })
}
const pillStates = (page: Page) =>
  page.evaluate(() => (window as unknown as { __pill: string[] }).__pill)

// ── which copy: the panel says LIVE or demo (2026-09-11) ────────────────────────
//
// Two copies of one strategy share a display name since 2026-09-11 (a name is the strategy;
// demo or live belongs to the account), and this panel is where their risk and their code are
// changed — so it says which kind of account it is on, in the words Telegram uses.

test('the panel names a bot WITH its account kind, in its title and its deploy line', async ({
  page,
}) => {
  // MUTATION: render `bot.name` (not `labelOf(bot)`) in BotDrawer -> red.
  await mockBot(page, compare(), { live: true })
  await openConfigure(page)
  const panel = page.getByRole('complementary', { name: /settings/ })
  await expect(panel.getByText('SOS Fade · LIVE', { exact: true })).toBeVisible()
  await expect(banner(page).getByTestId('version-heading')).toContainText(
    'SOS Fade · LIVE is 21 versions behind'
  )
})

test('a bot on NO account keeps its plain name — never a guessed kind', async ({ page }) => {
  // MUTATION: drop the no-account guard in `lib/botLabel.ts` -> red: the registry's hardcoded
  // `account_type` would tag a benched bot "demo" about an account it is not on.
  await pinSnapshot(page)
  await page.route('**/api/bots/*/version', (r) => r.fulfill({ json: version(compare()) }))
  await page.route('**/api/bots/*/promote/job', (r) =>
    r.request().method() === 'GET' ? r.fulfill({ json: null }) : r.fallback()
  )
  const benched = recorded<BotSnapshot>('/bots/snapshot').bots.find((b) => !b.account)
  expect(benched, 'the recording holds no benched bot - this check has no subject').toBeTruthy()
  // Its settings list is not recorded; the recorded one of another bot stands in, because this
  // check is about the TITLE and nothing the list says can move it.
  await page.route(`**/api/bots/${benched!.key}/params`, (r) =>
    r.fulfill({ json: recorded('/bots/sos_fade_demo/params') })
  )
  await page.goto(`/bots?tab=setup&bot=${benched!.key}`)
  const panel = page.getByRole('complementary', { name: /settings/ })
  await expect(panel.getByText(benched!.name, { exact: true })).toBeVisible({ timeout: 20_000 })
  await expect(panel.getByText(/ · (LIVE|demo)$/)).toHaveCount(0)
})

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
  await expect(
    banner(page).getByRole('button', { name: /Deploy & restart v100 → v121/ })
  ).toBeVisible()
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
  await expect(banner(page).getByRole('button', { name: /Deploy & restart/ })).toHaveCount(0)
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

// ── ONE button, ONE progress readout (2026-09-10) ──────────────────────────────
//
// Aaron: *"When I am promoting I want to see a progress bar of some sort; a static disabled button
// doesn't catch my focus"* and *"I have to scroll down and there is another button to click to
// deploy and restart … I am only acting on one CTA and there is only 1 progress indicator."*
//
// ⚠ A fail-watch against the previous panel is VACUOUS for most of these — the progress readout
// did not exist — so each check names the MUTATION that turns it red.

const progress = (page: Page) => banner(page).getByTestId('deploy-progress')
const step = (page: Page, key: string) => progress(page).locator(`[data-step="${key}"]`)
const caption = (page: Page) => banner(page).getByTestId('deploy-caption')

test('ONE click deploys — no preview, no second button to scroll to', async ({ page }) => {
  // MUTATION: restore the preview-then-confirm flow — the first click then starts nothing, no job
  // POST is made, and the progress readout never appears.
  const { posts } = await mockBot(page, compare())
  await openConfigure(page)

  await banner(page)
    .getByRole('button', { name: /Deploy & restart v100 → v121/ })
    .click()
  await expect(progress(page)).toBeVisible()
  expect(posts).toHaveLength(1)
  // While it runs there is nothing else to press — the readout is the thing to look at.
  await expect(
    banner(page).getByRole('button', { name: /Deploy|Try again|Re-deploy/ })
  ).toHaveCount(0)
  await expect(banner(page).getByTestId('version-heading')).toContainText(/Deploying SOS Fade/)
})

test('the readout moves step by step, with the step it is on MOVING', async ({ page }) => {
  // MUTATION: map every job step to `done` in `jobSteps` — the stop step is never seen `active`.
  // ⚠ HELD on the stop step (2026-09-10): these four assertions read one moment of a moving job,
  // and passed only because a real one-second poll was slower than they were. The fast clock
  // finished the deploy between the first and the second — the race `holdAt` exists for.
  await mockBot(page, compare(), { holdAt: 'stop' })
  await openConfigure(page)
  await banner(page).getByTestId('deploy-button').click()

  await expect(step(page, 'stop')).toHaveAttribute('data-state', 'active', { timeout: 15_000 })
  await expect(caption(page)).toContainText(/Asking the bot to stop/)
  // The earlier steps are finished by then, the later ones not started.
  await expect(step(page, 'build')).toHaveAttribute('data-state', 'done')
  await expect(step(page, 'start')).toHaveAttribute('data-state', 'pending')
})

test('mid-deploy there is ONE spinner, on the heading — none on the steps', async ({ page }) => {
  // Aaron, 2026-09-10: *"I don't need a spinner and a progress bar … I don't need the secondary
  // spinner on each progress section."* The running step moves through its bar's travelling band;
  // a spinner beside its label as well is two motions saying the same thing.
  // MUTATION: give the active step's icon `animate-spin` again → the progress count reads 1.
  // ⚠ The job is HELD on a running step. The first version of this check raced a job advancing
  // every second, and went red on the WRONG line under its mutation — the deploy had already
  // finished, so neither spinner was on screen and the step count passed for free.
  await mockBot(page, compare(), { holdAt: 'stop' })
  await openConfigure(page)
  await banner(page).getByTestId('deploy-button').click()

  await expect(step(page, 'stop')).toHaveAttribute('data-state', 'active', { timeout: 15_000 })
  await expect(banner(page).getByTestId('version-heading').locator('.animate-spin')).toHaveCount(1)
  await expect(step(page, 'stop').locator('.animate-step-sweep')).toHaveCount(1)
  await expect(progress(page).locator('.animate-spin')).toHaveCount(0)
})

test('a finished deploy says DEPLOYED, is confirmed by the bot, and withdraws the button', async ({
  page,
}) => {
  // MUTATION: drop the `confirmState` branch and always print the confirmed line — then an
  // unconfirmed restart reads green too (see the next check).
  await mockBot(page, compare(), { confirm: 'done' })
  await openConfigure(page)
  await banner(page).getByTestId('deploy-button').click()

  await expect(caption(page)).toContainText(/restarted and reported the new version/, {
    timeout: 20_000,
  })
  await expect(step(page, 'confirm')).toHaveAttribute('data-state', 'done')
  await expect(banner(page).getByText(/is up to date/)).toBeVisible()
  await expect(banner(page).getByTestId('deploy-button')).toHaveCount(0)
  // What a deploy would change describes the state BEFORE it — gone once one is on screen.
  await expect(banner(page).getByText(/setting would change on this bot/)).toHaveCount(0)
  // The output is not holding the panel open after a success…
  await expect(banner(page).getByText(/pinned 556bf70c18b7/)).toHaveCount(0)
  // …but it is one click away rather than thrown away.
  await banner(page).getByTestId('deploy-output-toggle').click()
  await expect(banner(page).getByText(/pinned 556bf70c18b7/)).toBeVisible()
  await banner(page).getByRole('button', { name: 'Close' }).click()
  await expect(progress(page)).toHaveCount(0)
})

test('a restart the bot never CONFIRMED is amber — never the green success', async ({ page }) => {
  // MUTATION: map `unconfirmed` to `done` in `jobSteps` and drop its caption branch. Green there
  // would claim a measurement nobody took.
  await mockBot(page, compare(), { confirm: 'unconfirmed' })
  await openConfigure(page)
  await banner(page).getByTestId('deploy-button').click()

  await expect(caption(page)).toContainText(/had not reported the new version/, { timeout: 20_000 })
  await expect(step(page, 'confirm')).toHaveAttribute('data-state', 'warn')
  await expect(caption(page)).not.toContainText(/reported the new version\./)
})

test('a REFUSED deploy says the bot is untouched, keeps its output open, and offers Try again', async ({
  page,
}) => {
  // MUTATION: branch on nothing and print the success line. A refused promote leaves the running
  // bot exactly as it was — saying otherwise sends somebody to debug a bot that is fine.
  await mockBot(page, compare(), { outcome: 'refused' })
  await openConfigure(page)
  await banner(page).getByTestId('deploy-button').click()

  await expect(caption(page)).toContainText(/Deploy refused/, { timeout: 15_000 })
  await expect(caption(page)).toContainText(/still on v100/)
  await expect(step(page, 'build')).toHaveAttribute('data-state', 'failed')
  // A step the failure never reached reads as SKIPPED, never as done.
  await expect(step(page, 'stop')).toHaveAttribute('data-state', 'skipped')
  // The reason lives in the output, so it is on screen without a click.
  await expect(banner(page).getByText(/does not import/)).toBeVisible()
  await expect(banner(page).getByTestId('deploy-output-toggle')).toHaveCount(0)
  // The same ONE button comes back, as the way to try again.
  await expect(banner(page).getByRole('button', { name: 'Try again' })).toBeVisible()
})

test('a failure that RAISED shows what the backend said, never a stock "untouched"', async ({
  page,
}) => {
  // MUTATION: ignore `job.error` and print the refused sentence. Mid-stop the code IS deployed;
  // "untouched" there would send the reader to redeploy code that is already live.
  await mockBot(page, compare(), { outcome: 'raised' })
  await openConfigure(page)
  await banner(page).getByTestId('deploy-button').click()

  await expect(caption(page)).toContainText(/IS deployed/, { timeout: 15_000 })
  await expect(caption(page)).not.toContainText(/untouched/)
  await expect(step(page, 'stop')).toHaveAttribute('data-state', 'failed')
})

test('a deploy that did NOT restart says the bot is still on the old code', async ({ page }) => {
  // MUTATION: ignore `restarted` and always claim the new version is running. The snapshot is on
  // disk and the OLD one is still trading — the single most misleading state this page can be in.
  await mockBot(page, compare(), { restarted: false })
  await openConfigure(page)
  await banner(page).getByTestId('deploy-button').click()

  await expect(caption(page)).toContainText(/restart .* to pick it up/, { timeout: 15_000 })
  await expect(step(page, 'start')).toHaveAttribute('data-state', 'skipped')
})

test('a deploy already RUNNING when the panel opens is shown — not a second Deploy over it', async ({
  page,
}) => {
  // MUTATION: delete the line that ADOPTS a running job into `shownJob` — the reopened drawer then
  // offers Deploy over a deploy that is mid-flight.
  const { posts, release } = await mockBot(page, compare(), { runningOnOpen: true })
  await openConfigure(page)

  await expect(progress(page)).toBeVisible()
  await expect(banner(page).getByTestId('deploy-button')).toHaveCount(0)
  // …and once it finishes, its result stays on screen rather than vanishing: this panel watched it.
  release()
  await expect(caption(page)).toContainText(/reported the new version/, { timeout: 20_000 })
  expect(posts).toHaveLength(0)
})

// ── the deploy is watched by the PAGE, not by the drawer ────────────────────────
//
// 🔴 Aaron, 2026-09-10: *"while it was deploying, I closed the side drawer… on the row that's being
// deployed, all it says is behind still… it should have some indicator."* The job was watched from
// inside the drawer, so closing it stopped the watch: the row never learned a deploy was running,
// and nothing noticed the finish until the drawer was reopened.

const closeDrawer = (page: Page) =>
  page
    .getByRole('complementary', { name: /settings/ })
    .getByRole('button', { name: 'Close', exact: true })
    .first()
    .click()

test('with the drawer CLOSED mid-deploy, the row says deploying and names the target', async ({
  page,
}) => {
  // MUTATION: watch only the bot whose drawer is open (the old placement) — the row reads
  // "behind" through the deploy and never moves on. MUTATION: drop `deploying` from the row's pill.
  await mockBot(page, compare(), { holdAt: 'stop' })
  await openConfigure(page)
  await banner(page).getByTestId('deploy-button').click()
  await expect(progress(page)).toBeVisible()
  await closeDrawer(page)
  await expect(banner(page)).toHaveCount(0)

  await expect(rowPill(page)).toHaveAttribute('data-state', 'deploying')
  await expect(rowPill(page)).toContainText('Deploying v121')
})

test('the finish is noticed with the drawer closed, and the row moves to the new version', async ({
  page,
}) => {
  // MUTATION: watch only the bot whose drawer is open — the finish is never seen, so the version
  // is never re-read and the row sits on "21 behind" for ever.
  await mockBot(page, compare())
  await openConfigure(page)
  await banner(page).getByTestId('deploy-button').click()
  await expect(progress(page)).toBeVisible()
  await closeDrawer(page)

  await expect(rowPill(page)).toHaveAttribute('data-state', 'current', { timeout: 20_000 })
  await expect(rowPill(page)).toContainText('v121')
})

test('a finished deploy never flashes the old "behind" while its version is re-read', async ({
  page,
}) => {
  // 🔴 The finish re-reads the version over SSH, and for that round trip every readout still shows
  // the state BEFORE the deploy. MUTATION: drop the `await` on that re-read in `usePromoteJobs` —
  // the job reads done at once and the row falls back to "behind" for the 3s held here.
  await mockBot(page, compare(), { reReadDelayMs: 3_000 })
  await openConfigure(page)
  await recordPillStates(page)
  await banner(page).getByTestId('deploy-button').click()

  await expect(rowPill(page)).toHaveAttribute('data-state', 'current', { timeout: 25_000 })
  const states = await pillStates(page)
  const from = states.indexOf('deploying')
  // Positive control: it WAS seen deploying, so the slice below is not empty by construction.
  expect(from).toBeGreaterThanOrEqual(0)
  expect(states.slice(from)).not.toContain('behind')
  // …and the drawer's own heading moved straight to the answer too.
  await expect(banner(page).getByText(/is up to date/)).toBeVisible()
})

test('a LIVE-account bot takes a second click on the SAME button', async ({ page }) => {
  // MUTATION: drop the `live && !armed` branch — the first click then deploys to real money.
  const { posts } = await mockBot(page, compare(), { live: true })
  await openConfigure(page)

  const btn = banner(page).getByTestId('deploy-button')
  await btn.click()
  await expect(btn).toContainText(/Click again — this bot trades real money/)
  expect(posts).toHaveLength(0)
  await btn.click()
  await expect(progress(page)).toBeVisible()
  expect(posts).toHaveLength(1)
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

test('the deploy names — and lands on — the version a promote can REACH', async ({ page }) => {
  // 🔴 MEASURED 2026-08-14: a deploy that could only reach v164 announced "running v165" — what
  // the reader ASKED for, not what landed. Those differ exactly when the deploy falls short, which
  // is precisely when the sentence is read. The button now names the reachable version too.
  // MUTATION: label the button with `c.local_version` — it then promises v121.
  await mockBot(
    page,
    compare({
      unpushed_commits: ['6a71a9f feat(signals): announce on the retrace'],
    }),
    { landsAt: 120 }
  )
  await openConfigure(page)

  await banner(page)
    .getByRole('button', { name: /Deploy & restart v100 → v120/ })
    .click()
  await expect(caption(page)).toContainText(/reported the new version/, { timeout: 20_000 })
  await expect(step(page, 'confirm')).toContainText('Running v120')
  await expect(banner(page).getByText('v120').first()).toBeVisible()
  // Nowhere on the banner does v121 read as the DEPLOYED version…
  await expect(banner(page).getByText(/Deployed v121/)).toHaveCount(0)
  // …and it is honest that the bot is still short of the backtester — by a PUSH, not a deploy.
  await expect(banner(page).getByTestId('version-heading')).toContainText(
    /has everything that is pushed/
  )
  await expect(rowPill(page)).toHaveAttribute('data-state', 'unpushed')
})

test('behind ONLY by unpushed commits: no deploy is offered, and the fix is named as a push', async ({
  page,
}) => {
  // 🔴 Aaron, 2026-09-10, straight after a deploy that worked: the row said "1 behind" and the panel
  // offered "Deploy & restart v218 → v218" — a restart for nothing, under a heading saying behind.
  // MUTATION: gate the big button on `behind > 0` again → it offers "Deploy & restart v120 → v120".
  // MUTATION: gate the pill on `behind > 0` alone → the row reads "1 behind".
  await mockBot(
    page,
    compare({
      deployed_version: 120,
      versions_behind: 1,
      unpushed_commits: ['035f28d docs(sos_fade): golden export notes'],
    })
  )
  await openConfigure(page)

  await expect(banner(page).getByTestId('version-heading')).toContainText(
    /has everything that is pushed/
  )
  await expect(banner(page).getByRole('button', { name: /Deploy & restart/ })).toHaveCount(0)
  await expect(banner(page).getByRole('button', { name: 'Re-deploy' })).toBeVisible()
  const note = banner(page).getByTestId('banner-unpushed-only')
  await expect(note).toContainText(/1 commit touching this bot is only on this machine/)
  await expect(note).toContainText('v121')
  // A deploy changes none of these, so "would change" is not offered either.
  await expect(banner(page).getByText(/would change on this bot/)).toHaveCount(0)
  await expect(rowPill(page)).toHaveAttribute('data-state', 'unpushed')
  await expect(rowPill(page)).toContainText('v120 · not pushed')
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
  // No deploy job — these checks are about the version read, and the page asks for one on open.
  await page.route('**/api/bots/*/promote/job', (r) => r.fulfill({ json: null }))
  await pinSnapshot(page)
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

// ── the code that RUNS the bot, which the version number does not count (2026-09-12) ─────────
//
// 🔴 The version counts the strategy only. The code that talks to the broker and writes what this
// page reads moves only when the bot restarts — so both live bots read "up to date" eight fixes
// behind. Aaron: "you keep saying redeploy but I am not seeing me behind on any version".

const UP_TO_DATE = compare({
  deployed_version: 121,
  versions_behind: 0,
  changes: [],
  setting_changes: [],
})

/** A bot running for `uptimeS`, whose newest start on record was `startedBeforeFetchS` before the
 *  recorded snapshot was taken. The row measures the process's start off the SNAPSHOT's clock, so
 *  the fixture has to as well — a fixture on this machine's clock would describe a different run. */
function olderCode(uptimeS: number, startedBeforeFetchS: number) {
  const fetched = Date.parse(recorded<BotSnapshot>('/bots/snapshot').fetched_at)
  return {
    bot: { status: 'RUNNING', uptime_seconds: uptimeS },
    runningCode: {
      commit: '569ae98f',
      started_at: new Date(fetched - startedBeforeFetchS * 1000).toISOString(),
      changes_waiting: 8,
      changes: ['c03f4d0c feat(live): the heartbeat says what the bot holds at the broker'],
      reason: '',
    },
  }
}

test('a RUNNING bot on older code than the box holds reads RESTART, on the row and the panel', async ({
  page,
}) => {
  // MUTATION: drop `restart` from the row's pill → red on its state.
  // MUTATION: drop the runner half of `restartReason` → red on the pill AND the banner.
  // MUTATION: measure the banner off this machine's clock rather than the snapshot's → red on the
  // banner (the recording is days old, so the running process reads as a newer run).
  // MUTATION: measure the ROW off this machine's clock → red on the pill, the same way.
  await mockBot(page, UP_TO_DATE, olderCode(3600, 3600 + 120))
  await openConfigure(page)
  await expect(rowPill(page)).toHaveAttribute('data-state', 'restart')
  await expect(rowPill(page)).toHaveText(/v121 · restart/)
  await expect(rowPill(page)).toHaveAttribute('title', /8 changes to the code that runs this bot/)
  await expect(banner(page).getByTestId('version-heading')).toHaveText(/is running older code/)
  await expect(banner(page).getByTestId('banner-restart')).toContainText('Re-deploy')
  await expect(banner(page).getByTestId('deploy-button')).toHaveText(/Re-deploy & restart/)
})

test('a bot that RESTARTED since that start was read is not asked to restart again', async ({
  page,
}) => {
  // The reading names the newest start on record; a process that began well after it is a newer
  // run, and asking it to restart would be asking for the restart it just had.
  // MUTATION: drop the same-run check → red on both.
  await mockBot(page, UP_TO_DATE, olderCode(60, 3600))
  await openConfigure(page)
  await expect(rowPill(page)).toHaveAttribute('data-state', 'current')
  await expect(banner(page).getByTestId('banner-restart')).toHaveCount(0)
})

test('a STOPPED bot is not asked to restart — it loads the new code when it starts', async ({
  page,
}) => {
  // MUTATION: drop the RUNNING check → red on both.
  const o = olderCode(3600, 3600 + 120)
  await mockBot(page, UP_TO_DATE, { ...o, bot: { status: 'STOPPED', uptime_seconds: null } })
  await openConfigure(page)
  await expect(rowPill(page)).toHaveAttribute('data-state', 'current')
  await expect(banner(page).getByTestId('banner-restart')).toHaveCount(0)
})

test('the panel header says what the row says — a halted bot never reads a green Running', async ({
  page,
}) => {
  // 🔴 2026-09-12: the panel drew its own green "Running" over a halted bot while the row beside it
  // said Halted. It reads the row's one condition now.
  // MUTATION: hand the header a reading without the halt → red on its state and its dot.
  await mockBot(page, UP_TO_DATE, {
    bot: {
      status: 'RUNNING',
      uptime_seconds: 3600,
      bridge_state: 'halted',
      halt_reason: 'the strategy believes it is in a position but MT5 holds none',
    },
  })
  await openConfigure(page)
  const panel = page.getByRole('complementary', { name: /settings/ })
  await expect(panel.getByTestId('bot-status')).toHaveAttribute('data-state', 'halted')
  await expect(panel.getByTestId('bot-status')).toHaveAttribute('title', /MT5 holds none/)
  await expect(panel.getByTestId('status-dot')).toHaveAttribute('data-tone', 'bad')
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

test('a version the box would not give is UNREAD on the row and the panel — and nothing toasts', async ({
  page,
}) => {
  // 🔴 2026-09-11: a crowded box refused a third of SSH connections, and every Bots-page load put a
  // toast per bot on screen (a 500 each, twice with the retry). The failure is RENDERED now, in its
  // own words — "No version" is an answer (never deployed), this is the box not answering.
  // ⚠ Toasts are COUNTED as they appear, never read at the end: at this spec's quick clock a toast
  // lives ~0.4s, so a count taken after the assertions could miss one that came and went.
  // MUTATION: drop `silent: true` from the version read — the toast count goes red (killed 2026-09-11).
  // MUTATION: drop the pill's unread branch — the row reads "No version" and goes red (killed 2026-09-11).
  // MUTATION: drop the banner's unread branch — it reads "Version unknown" and goes red (killed 2026-09-11).
  await page.addInitScript(() => {
    const w = window as unknown as { __toasts: number }
    w.__toasts = 0
    new MutationObserver((muts) => {
      for (const m of muts)
        for (const n of m.addedNodes)
          if (n instanceof Element)
            // A first toast can arrive INSIDE a newly added list, so look below the node too.
            w.__toasts +=
              (n.matches('[data-sonner-toast]') ? 1 : 0) +
              n.querySelectorAll('[data-sonner-toast]').length
    }).observe(document, { childList: true, subtree: true })
  })
  await pinSnapshot(page)
  const refused =
    'Cannot reach the VPS — kex_exchange_identification: read: Connection reset by peer'
  let reads = 0
  await page.route('**/api/bots/*/version', (r) => {
    reads++
    return r.fulfill({ status: 502, json: { detail: refused } })
  })
  await page.route('**/api/bots/*/promote/job', (r) => r.fulfill({ json: null }))
  await page.goto('/bots?tab=setup&bot=sos_fade_demo')

  await expect(banner(page)).toHaveAttribute('data-state', 'unread', { timeout: 20_000 })
  await expect(banner(page)).toContainText('kex_exchange_identification')
  await expect(banner(page).getByRole('button', { name: 'Try again' })).toBeVisible()
  await expect(rowPill(page)).toHaveAttribute('data-state', 'unread')
  await expect(rowPill(page)).toContainText('Unread')
  expect(reads, 'the version reads really failed').toBeGreaterThan(0)
  expect(await page.evaluate(() => (window as unknown as { __toasts: number }).__toasts)).toBe(0)
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
