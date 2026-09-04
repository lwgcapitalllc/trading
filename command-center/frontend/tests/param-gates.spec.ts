/**
 * A toggle's labels READ the setting they describe, and a toggle that cannot matter is HIDDEN.
 *
 * 🔴 THE SUBJECT (2026-08-15): `exec_sl_deep` read `Always the level above` / `1.0 past 0.786` —
 * two labels describing a NEIGHBOURING widget rather than what this one does, neither of which
 * names the stop it produces. It also stayed live with `Stop fib level` already at `1.0`, where
 * both of its states place the stop in the same spot. The Pine has greyed it out since it was
 * written (`strategies/tradingview/sos_fade_strategy.pine:116` → `active = execSlLevel != "1.0"`); this
 * is the Python UI catching up, not a new idea.
 *
 * ⚠ IT DRIVES THE REAL `sos_fade` SCHEMA off the running backend, deliberately — the same rule
 * `strategies.spec.ts` states at the top of itself. A hand-written fixture would pass against a
 * scanner that never whitelisted `disable_if`, which is exactly the silent hop this feature has to
 * clear (`_PARAM_META_KEYS` drops an unknown key without a word). So this suite needs the backend
 * on :8000 as well as the dev server on :5173, and it needs a **Scan** to have picked up the meta.
 *
 * ⚠ A fail-watch against HEAD is VACUOUS: `disable_if` and the `{token}` syntax are part of the
 * fix, so every check goes red on a schema key that does not exist rather than on behaviour.
 * Non-vacuity is by MUTATION, named on each check. The backend half's mutations are in
 * `backend/tests/test_param_gates.py`.
 */
import { test, expect, type Page } from '@playwright/test'
import { requireRun } from './fixtures'

const RUN_ID = 'paramgates01'

/** A completed python run on sos_fade — the Tune page is the cheapest route to the editor
 *  that needs no VPS, no history probe and no platform lock. */
function run(params: Record<string, unknown>) {
  return {
    run_id: RUN_ID,
    strategy_id: 'sos_fade',
    strategy_name: 'SOS Fade',
    instrument: 'XAUUSD',
    status: 'complete',
    runner: 'python',
    bar_type: 'Minute',
    bar_value: 15,
    start_date: '2020-01-01',
    end_date: '2026-08-01',
    created_at: 1_755_000_000,
    params,
    evaluations: [],
    equity_curve: [],
    daily_pnl: [],
    regime_timeline: [],
    kpis: {},
  }
}

async function mock(page: Page, params: Record<string, unknown>) {
  await page.route(`**/api/backtests/runs/${RUN_ID}*`, (r) => r.fulfill({ json: run(params) }))
  await page.route('**/api/backtests/runs?**', (r) => r.fulfill({ json: [] }))
  await page.route('**/api/backtests/running-job', (r) =>
    r.fulfill({
      json: { nt8: { running: false }, mt5: { running: false }, python: { running: false } },
    })
  )
}

/**
 * Opens the tuning workbench and expands the group holding the toggle.
 *
 * ⚠ BOTH params live in the `Risk & stop` accordion, and it is CLOSED on arrival — only the group
 * holding the FIRST core param opens by itself. Until 2026-08-15 `exec_sl_level` was rendered up
 * front in an Essentials card, so waiting on it worked and the toggle beside it did not; the card
 * is gone (it duplicated every param it showed), so the group has to be opened before either is
 * on screen.
 */
async function openEditor(page: Page, params: Record<string, unknown> = {}) {
  await mock(page, {
    exec_sl_level: '0.886',
    exec_sl_custom: 0.95,
    exec_sl_deep: false,
    ...params,
  })
  await page.goto(`/backtests/runs/${RUN_ID}/tune`)
  await page
    .getByRole('button', { name: /Risk & stop/ })
    .first()
    .click()
  await expect(page.getByText('Stop fib level (deep side of 0.5)').first()).toBeVisible()
  await expect(page.getByText('Entries at 0.786 or deeper stop at 1.0').first()).toBeVisible()
}

/** The `Stop fib level` dropdown — found by its own options, not by a position in the list. */
const levelSelect = (page: Page) =>
  page
    .locator('select')
    .filter({ has: page.locator('option[value="0.886"]') })
    .first()

const offLabel = (page: Page, text: string) =>
  page.getByRole('button', { name: text, exact: true }).first()

test.describe('an option label states the setting it produces', () => {
  test('the OFF label reads the dropdown, and MOVES when the dropdown moves', async ({ page }) => {
    // MUTATION: make `fillTokens` return `schema` untouched — the toggle renders the literal
    // `Stop {exec_sl_level}` and both halves of this go red.
    await openEditor(page)

    await expect(offLabel(page, 'Stop 0.886')).toBeVisible()
    await levelSelect(page).selectOption('0.786')
    await expect(offLabel(page, 'Stop 0.786')).toBeVisible()
    // The ON side is genuinely constant — the deep rule always anchors at 1.0.
    await expect(offLabel(page, 'Stop 1.0')).toBeVisible()
  })

  test('a CUSTOM level is RESOLVED, never printed as the word "Custom"', async ({ page }) => {
    // MUTATION: drop the `custom_from` branch from `readerFor` and the label reads `Stop Custom` —
    // technically the dropdown's value, and useless to the reader.
    await openEditor(page)

    await levelSelect(page).selectOption('Custom')
    await expect(offLabel(page, 'Stop 0.95')).toBeVisible()
    await expect(page.getByRole('button', { name: /Stop Custom/ })).toHaveCount(0)
  })
})

test.describe('a toggle that cannot matter is HIDDEN', () => {
  /**
   * 🔴 THIS SUITE ASSERTED THE OPPOSITE UNTIL 2026-08-27, and the reversal is the point.
   *
   * The row used to be drawn greyed with its reason beside it, on the rule that a setting which
   * vanishes reads as one that does not exist. Aaron reversed it reading the run form: on
   * `sos_fade` SEVENTEEN rows are greyed under the shipped defaults, so the reader hunting the
   * one live setting reads past a screen of dead controls first. The old rule protects a reader
   * looking for a specific row; the count says that is not the common reader.
   *
   * ⚠ The REASON did not die with the greying — `disable_note` is still required on every row and
   * the finished-run params panel still prints it, because a run already taken has to be able to
   * say why a setting did nothing. `backend/tests/test_param_gates.py` owns that half.
   */
  test('at 1.0 the row is GONE, not greyed', async ({ page }) => {
    // MUTATION: drop `&& !inert(p)` from `visible` in ParamEditor and the row comes back — both
    // assertions go red. The second one is what stops a fix that hides the row while leaving the
    // greyed note behind it.
    await openEditor(page)

    await levelSelect(page).selectOption('1.0')
    await expect(page.getByText('Entries at 0.786 or deeper stop at 1.0')).toHaveCount(0)
    await expect(page.getByTestId('param-inert-exec_sl_deep')).toHaveCount(0)
  })

  test('below 1.0 it is back — the guard against hiding it unconditionally', async ({ page }) => {
    // 🔴 The dangerous direction. A row hidden always satisfies every check above, and a setting
    // that can never be reached is strictly worse than one greyed out — there is nothing on
    // screen to notice. MUTATION: make `isInert` return true always and this goes red.
    await openEditor(page)

    await levelSelect(page).selectOption('1.0')
    await expect(page.getByText('Entries at 0.786 or deeper stop at 1.0')).toHaveCount(0)
    await levelSelect(page).selectOption('0.886')
    await expect(page.getByText('Entries at 0.786 or deeper stop at 1.0').first()).toBeVisible()
    await expect(offLabel(page, 'Stop 0.886')).toBeEnabled()
  })

  test('CUSTOM set to 1.0 hides it exactly as the dropdown does', async ({ page }) => {
    // 🔴 The half a value-blind gate gets wrong: Custom = 1.0 IS 1.0, so a row left on screen
    // there is one whose two states cannot differ. MUTATION: drop the `custom_from` resolution
    // from `isInert` and this goes red while every other check stays green.
    await openEditor(page, { exec_sl_level: 'Custom', exec_sl_custom: 1.0 })

    await expect(page.getByText('Entries at 0.786 or deeper stop at 1.0')).toHaveCount(0)
  })

  test('the dropdown that KILLS it is itself untouched', async ({ page }) => {
    // A cascade that eats its own parent is the failure mode of hiding rather than greying: the
    // reader sets the level to 1.0, the dependent row goes, and if the parent went too there is
    // no way back to 0.886. MUTATION: give `exec_sl_level` the same `disable_if` and this goes red.
    await openEditor(page)

    await levelSelect(page).selectOption('1.0')
    await expect(levelSelect(page)).toBeVisible()
    await expect(levelSelect(page)).toBeEnabled()
  })
})

/**
 * 🔴 "Advanced" was Commission and Slippage and NOTHING ELSE — both of them costs, sitting under
 * their own heading past a divider while the Costs section's own rows said "charges the figure
 * below". Aaron, reading the modal: *"what is the point of advanced section ... isnt that cost
 * also?"* It is the `exec_sl_deep` defect one component out: a label pointing at a widget
 * somewhere else. On the python runner each figure now sits under the LAYER that charges it, and
 * only while that layer is ticked — an untick used to leave the number on screen looking live.
 *
 * ⚠ NT8 and MT5 keep a Costs section holding both, because they have no layers at all (their own
 * tester charges these two directly and `cost_layers` is sent as null). Nothing here asserts on
 * that path — it is unchanged, and `strategies.spec.ts` owns the NT8 row.
 */
test.describe('a cost figure sits under the cost that charges it', () => {
  /** The Run modal on a PYTHON strategy — the only runner that has cost layers at all. */
  async function openRunModal(page: Page) {
    await page.route('**/api/backtests/history-limit*', (r) => r.fulfill({ json: null }))
    await page.goto('/strategies')
    const row = page.locator('tbody tr').filter({ hasText: 'SOS Fade' }).first()
    await row.getByRole('button', { name: /^Run$/ }).click()
    // The modal title is a plain div, not a heading — assert on the text.
    await expect(page.getByText('Run Backtest', { exact: true }).first()).toBeVisible()
    // Folded by default; open it to reach the layers.
    await page.getByRole('button', { name: /^Costs/ }).click()
  }

  test('there is no ADVANCED section left on a python run', async ({ page }) => {
    // The whole complaint: two cost fields under a heading that named neither of them.
    // MUTATION: restore the `Advanced` SectionHead and this goes red.
    await openRunModal(page)
    await expect(page.getByText('Advanced', { exact: true })).toHaveCount(0)
  })

  test('the Commission box appears only once its own layer is ticked', async ({ page }) => {
    // 🔴 An untick left the number on screen looking live — the same "a label points at a widget
    // that is not listening" shape as the toggle above.
    // MUTATION: render `costInputs[row.id]` unconditionally rather than behind `on`, and the
    // first assertion goes red.
    await openRunModal(page)
    const box = page.getByLabel('Commission / side ($)')

    await expect(page.getByText('Commission / side ($)')).toHaveCount(0)
    await page.getByRole('button', { name: /Commission/ }).click()
    await expect(page.getByText('Commission / side ($)')).toBeVisible()
    await expect(box.or(page.locator('input[type="number"][step="0.01"]')).first()).toBeVisible()
  })

  test('the folded header still says what is charged', async ({ page }) => {
    // ⚠ A collapsed section is only safe because its header stands for what it hides. MUTATION:
    // drop `summary` from the Costs `SectionHead` and this goes red.
    await page.route('**/api/backtests/history-limit*', (r) => r.fulfill({ json: null }))
    await page.goto('/strategies')
    await page
      .locator('tbody tr')
      .filter({ hasText: 'SOS Fade' })
      .first()
      .getByRole('button', { name: /^Run$/ })
      .click()
    // The modal title is a plain div, not a heading — assert on the text.
    await expect(page.getByText('Run Backtest', { exact: true }).first()).toBeVisible()

    // Folded, nothing ticked. Scoped to the header BUTTON — the word also sits in the section's
    // tooltip, which is in the DOM at all times behind a hover.
    await expect(page.getByRole('button', { name: /Costs.*frictionless/ })).toBeVisible()
    await page.getByRole('button', { name: /^Costs/ }).click()
    await page.getByRole('button', { name: /Overnight swap/ }).click()
    await page.getByRole('button', { name: /^Costs/ }).click()
    await expect(page.getByRole('button', { name: /Costs.*overnight swap/ })).toBeVisible()
  })
})

/**
 * 🔴 SETTLED params come off the editor and stay in the strategy.
 *
 * Aaron, 2026-08-15: *"I don't want you to delete the configurations because I might talk to you,
 * and you might be able to toggle it back on super easy… I just want you to regroup them and
 * remove the ones that we know we don't ever change."* So `hidden: true` in the meta takes a row
 * off the screen and changes nothing about the field, its default, or what gets submitted.
 *
 * ⚠ The load-bearing half is the ESCAPE: a hidden param sitting away from its default is shown
 * anyway. The value is still sent, so hiding a moved one would put a setting on the run that no
 * reader could see — a page that cannot show what it is about to submit.
 */
test.describe('a settled param is hidden, not removed', () => {
  test('the settled ones are off the editor, and the page SAYS how many', async ({ page }) => {
    // MUTATION: drop `&& !settled(p)` from `visible` and the first assertion goes red; drop the
    // `settledCount` block and the second does.
    await openEditor(page)

    // `exec_htf_weekly` heads a group that is now entirely settled — the group itself is gone.
    await expect(page.getByText('Weekly bias requirement')).toHaveCount(0)
    await expect(page.getByText('Higher-timeframe filter')).toHaveCount(0)
    await expect(page.getByTestId('param-settled-count')).toContainText('26 settled')
  })

  test('🔴 a settled param MOVED off its default comes back on its own', async ({ page }) => {
    // The guard that makes hiding safe at all. MUTATION: make `settled` return `!!p.hidden` and
    // this goes red — the run would carry `exec_longs: false` with nothing on screen saying so.
    await openEditor(page, { exec_longs: false })
    // `What arms a setup` holds the first core param, so it is the group that opens by itself.
    await expect(page.getByText('Trade longs')).toBeVisible()
    await expect(page.getByTestId('param-settled-count')).toContainText('25 settled')
  })

  test('the secondary re-entries have their own group now', async ({ page }) => {
    // Aaron's stated pet peeve: `exec_secondary` and its two children were filed under
    // "Direction & sessions", where nobody would look for them.
    // MUTATION: put them back in the old group and this goes red.
    //
    // ⚠ The group NAMES NO TIMEFRAME. It read `Secondary re-entries (1m)` until 2026-08-21, when
    // the re-entry's fill clock became a setting (5 minutes by default) — a heading that hardcodes
    // a number the row below it owns is the same defect one level up, so the assertion pins the
    // ABSENCE of one. It also pins the two sub-groups, because a reader told which trigger a
    // setting belongs to is the whole point of the split.
    await openEditor(page)
    await expect(page.getByRole('button', { name: /^Secondary re-entries$/ })).toBeVisible()
    await expect(page.getByText(/Secondary re-entries \(\d+m\)/)).toHaveCount(0)
    await expect(page.getByRole('button', { name: /Reclaim Entry only/ })).toBeVisible()
    await expect(page.getByRole('button', { name: /Structure shift only/ })).toBeVisible()
    await expect(page.getByText('Direction & sessions')).toHaveCount(0)
  })
})

/**
 * The finished-run params panel — the one surface where a settled param is FOLDED, never dropped.
 *
 * The editor (Run / Tune / Optimize) and the strategy page describe what you MAY set. This panel
 * describes what a finished run DID set, and a run report that silently omits inputs is a worse
 * defect than a long list — so the rule here is a `<details>` with its own count, not a filter.
 *
 * ⚠ Drives the REAL backend against a REAL completed run, because the point is that the panel's
 * fold agrees with the schema the scanner actually served. A mocked run would prove the mock.
 */
test.describe('a finished run FOLDS its settled params rather than dropping them', () => {
  // A completed full-history sos_fade run. Every one of its params is at the shipped default,
  // which is what makes the count equal the whole settled set rather than "some".
  const DONE_RUN = '7a77391d6568'

  // Fail by NAME if this pinned run has left the lab. Its `Settled · 26` assertion is tied to
  // THIS run's params being all-default, so a replacement has to satisfy that too — which is
  // exactly the sentence a bare 404 timeout cannot supply. See `fixtures.ts`.
  test.beforeAll(async () => {
    await requireRun(
      DONE_RUN,
      'a completed full-history sos_fade run with EVERY param at its shipped default — that is what makes the settled count the whole set rather than "some"'
    )
  })

  test('the settled ones are behind a fold that COUNTS them, and the values are still there', async ({
    page,
  }) => {
    // MUTATION: drop `&& !settledKey(k, v)` from `tunable` and the first assertion goes red (the
    // key is back in the main list); drop the `settled` block and the fold disappears entirely.
    await page.goto(`/backtests/runs/${DONE_RUN}`)
    const panel = page.getByTestId('run-settled-params')
    await expect(panel).toBeVisible({ timeout: 30_000 })
    // ⚠ 31, not the 26 this pinned for its whole life: the fold gained the settings a run could
    // not act on (this run has the secondary OFF) alongside the ones past testing settled. The
    // number is pinned on purpose — it is what makes this a check on the RULE rather than on
    // "some params are folded", and a change to either rule has to come here and say why.
    await expect(panel).toContainText('Already decided · 31')

    // ⚠ Asserted on the WORDS, because the words are what the panel shows. It printed field
    // names until 2026-08-20 — `div_rsi_len` for this row — which made the one surface that
    // records what a run charged unreadable without the source open. Every param in this
    // strategy's metadata carries a unique label, so a label still identifies a row exactly.
    // Exactly ONE copy on the page — the fold's. A settled key that is ALSO still in the main
    // list is the mutation this catches; scoping the check to the fold alone would not see it.
    await expect(page.getByText('RSI length', { exact: true })).toHaveCount(1)
    await expect(panel.getByText('RSI length', { exact: true })).not.toBeVisible()
    // ...and one click puts the value back on screen. Nothing was dropped.
    await panel.getByText(/^Already decided · /).click()
    await expect(panel.getByText('RSI length', { exact: true })).toBeVisible()
  })
  /**
   * 🔴 EVERY SECTION IS OPEN ON ARRIVAL, AND COLLAPSING IS THE READER'S CHOICE.
   *
   * The panel's whole job is showing at a glance what a run charged, so a shut section is a
   * question the reader has to click to answer. The state therefore tracks what is SHUT, never
   * what is open — a set of OPEN groups starts empty, which renders every section collapsed on
   * first paint, and that is the exact inversion this pins. `ParamEditor`'s compact layout
   * carries the same rule for the same reason.
   *
   * MUTATION: flip `shutGroups` to an `openGroups` set and the first assertion goes red.
   *
   * ⚠ A shut section still states its COUNT. A collapsed group showing no number reads as a
   * group with nothing in it, which is the one thing a record of a run's inputs may never imply.
   */
  test('🔴 sections start OPEN, collapse one at a time, and a shut one still counts', async ({
    page,
  }) => {
    await page.goto(`/backtests/runs/${DONE_RUN}`)
    const zone = page.getByRole('button', { name: /Entry zone/ })
    await expect(zone).toBeVisible({ timeout: 30_000 })

    // Open on arrival — a setting inside the section is on screen without a click.
    await expect(zone).toHaveAttribute('aria-expanded', 'true')
    await expect(page.getByText('Require an FVG', { exact: true })).toBeVisible()

    await zone.click()
    await expect(zone).toHaveAttribute('aria-expanded', 'false')
    await expect(page.getByText('Require an FVG', { exact: true })).toHaveCount(0)
    await expect(zone, 'a shut section that states no count reads as an empty one').toContainText(
      /\d+$/
    )

    // Its neighbours are untouched — this collapses ONE section, not the panel.
    await expect(page.getByRole('button', { name: /Risk & stop/ })).toHaveAttribute(
      'aria-expanded',
      'true'
    )

    await zone.click()
    await expect(page.getByText('Require an FVG', { exact: true })).toBeVisible()
  })

  /**
   * One icon, and it offers the action the panel is NOT already in.
   *
   * ⚠ Two buttons would leave a dead one on screen at each extreme, and a control that does
   * nothing when clicked reads as broken rather than as already-done. So the assertion that
   * matters is that the label FLIPS — a single fixed "Collapse all" would pass a test that only
   * checked the sections.
   */
  /**
   * 🔴 A SETTING WHOSE PARENT IS OFF DID NOTHING ON THIS RUN, AND IS FOLDED AWAY.
   *
   * Fourteen secondary re-entry rows sat in the main list on every run with the secondary
   * switched off, and the same shape repeats through every cascade in the schema. Aaron:
   * *"if secondary trades is off in the strategy you DON'T need to show all the params related
   * to it… same goes for anything cascading."*
   *
   * ⚠ FOLDED, never dropped — this panel is the RECORD of what a run sent, so the values stay
   * one click away. That is the assertion the second half makes, and it is the one that stops
   * this from becoming a page unable to show what it submitted.
   *
   * ⚠ The PARENT toggle itself stays in the main list. A section that empties completely reads
   * as a section that does not apply to this strategy; leaving the switch visible says WHY the
   * rest is gone. That is what the first assertion pins.
   *
   * MUTATION: drop the `show_if` arm of `isOutOfPlay` and the dependants come back into the
   * main list, reddening the first two assertions.
   */
  test('🔴 the secondary is off, so its dependants fold away — parent and values still there', async ({
    page,
  }) => {
    // The pinned run has `exec_secondary: false`, which is what makes this case real rather
    // than mocked. `requireRun` above already fails by NAME if it leaves the lab.
    await page.goto(`/backtests/runs/${DONE_RUN}`)
    const secondary = page.getByRole('button', { name: /Secondary re-entries/ })
    await expect(secondary).toBeVisible({ timeout: 30_000 })

    // The switch itself is on the list...
    await expect(page.getByText('Secondary re-entries', { exact: true }).first()).toBeVisible()

    // ...and the settings it governs are not ON SCREEN. ⚠ Asserted on VISIBILITY, not on a DOM
    // count: a closed `<details>` still renders its children, so `toHaveCount(0)` would be red
    // against a correct page — and `getByText` matches a wrapper as well as the row, so the
    // count is not 1 either. What this panel promises is about what you can SEE.
    // ⚠ These two params, because they are what THIS run actually stored — it predates the rest
    // of the secondary block. Asserting on one the run never sent would pass for the wrong
    // reason: folded away and never there look identical.
    const oncePer = page.getByText('One per primary', { exact: true }).first()
    const retrace = page.getByText('Entry retrace', { exact: true }).first()
    await expect(oncePer).not.toBeVisible()
    await expect(retrace).not.toBeVisible()

    // Folded, NOT dropped — one click and this run's values are on screen.
    const panel = page.getByTestId('run-settled-params')
    await panel.getByText(/^Already decided · /).click()
    await expect(oncePer).toBeVisible()
    await expect(retrace).toBeVisible()
  })

  test('the expand/collapse-all icon flips, and moves every section', async ({ page }) => {
    await page.goto(`/backtests/runs/${DONE_RUN}`)
    const collapseAll = page.getByRole('button', { name: 'Collapse all sections' })
    await expect(collapseAll).toBeVisible({ timeout: 30_000 })

    await collapseAll.click()
    for (const g of [/What arms a setup/, /Entry zone/, /Risk & stop/]) {
      await expect(page.getByRole('button', { name: g })).toHaveAttribute('aria-expanded', 'false')
    }

    // The same control now offers the opposite, and performs it.
    const expandAll = page.getByRole('button', { name: 'Expand all sections' })
    await expect(expandAll).toBeVisible()
    await expandAll.click()
    for (const g of [/What arms a setup/, /Entry zone/, /Risk & stop/]) {
      await expect(page.getByRole('button', { name: g })).toHaveAttribute('aria-expanded', 'true')
    }
  })
})

/**
 * The Run modal shows every setting AND lets you edit it in place — one view, no modes.
 *
 * 🔴 The first attempt was a read-only summary with an Edit button, and Aaron rejected it:
 * *"what's the point of essentials if I have a read only view and an edit view?"* A curation of
 * "the important ones" only earns its place when the rest are hidden, and it DUPLICATED those
 * params. So this layout has no Essentials card, no Simple/Expert switch, and nothing to click
 * before a value can be changed.
 *
 * ⚠ Drives the REAL schema off the backend, same rule as the rest of this file.
 */
test.describe('the Run modal is one editable view of every setting', () => {
  async function openModal(page: Page) {
    await page.route('**/api/backtests/running-job', (r) =>
      r.fulfill({
        json: { nt8: { running: false }, mt5: { running: false }, python: { running: false } },
      })
    )
    await page.goto('/strategies')
    const row = page.locator('tbody tr').filter({ hasText: 'SOS Fade' }).first()
    await row.getByRole('button', { name: 'Run' }).click()
    await expect(page.getByTestId('param-compact')).toBeVisible({ timeout: 20_000 })
  }

  test('no Essentials card, no Simple/Expert, and every group is open', async ({ page }) => {
    // MUTATION: render the stacked layout here and the first two go red.
    await openModal(page)
    await expect(page.getByText('ESSENTIALS')).toHaveCount(0)
    await expect(page.getByRole('button', { name: 'Expert' })).toHaveCount(0)
    // Groups are open on arrival — the point of the layout is reading all of it at once.
    for (const g of ['What arms a setup', 'Risk & stop', 'Exit ladder', 'Divergence veto']) {
      await expect(page.getByRole('button', { name: new RegExp(g, 'i') })).toBeVisible()
    }
    await expect(page.getByTestId('param-row-exec_risk_pct')).toBeVisible()
  })

  test('🔴 a setting is edited IN PLACE, and its dependants react', async ({ page }) => {
    // The whole claim of this layout: no Edit step. MUTATION: drop `onChange` from CompactRow and
    // the count never appears.
    await openModal(page)
    await expect(page.getByTestId('run-params-changed')).toHaveCount(0)

    // `exec_nogap_arm` is gated on `exec_req_fvg` being OFF, so it is absent while a gap is
    // required and appears the moment it is not — show_if still driving the compact rows.
    await expect(page.getByTestId('param-row-exec_nogap_arm')).toHaveCount(0)
    await page.getByTestId('param-row-exec_req_fvg').locator('select').selectOption('false')
    await expect(page.getByTestId('param-row-exec_nogap_arm')).toBeVisible()
    await expect(page.getByTestId('run-params-changed')).toContainText('1 changed from default')
  })

  test('a settled param is still off the list, and the count says so', async ({ page }) => {
    // MUTATION: drop the `isSettled` clause from `visibleParams` and both go red — the
    // compact grid is built from that same exported function.
    await openModal(page)
    await expect(page.getByTestId('param-row-exec_longs')).toHaveCount(0)
    await expect(page.getByTestId('param-row-exec_close_opp_sos')).toHaveCount(0)
    await expect(page.getByTestId('param-settled-count')).toContainText('26 settled')
  })

  test('the strategy name is in the TITLE and the setup fits one row', async ({ page }) => {
    // MUTATION: put the Strategy section back and the first assertion goes red (two copies).
    await openModal(page)
    const modal = page.locator('div.fixed.inset-0.z-50')
    await expect(modal.getByText('SOS Fade', { exact: true })).toHaveCount(1)
    // The bar-size presets became a select, so no `15m` button survives.
    await expect(page.getByRole('button', { name: '15m', exact: true })).toHaveCount(0)
  })
})
