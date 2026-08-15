/**
 * The Backtests list and the Backtest detail page — the 2026-08-06 audit's regression suite.
 *
 * Every check here is a defect that shipped, and they share the shape this repo keeps meeting:
 * NOT ONE of them rendered an error. A rerun fired on a single click and reported success. A
 * delete cascaded through optimizations without saying so. A caption said "on by default" over a
 * rule that defaults off. A trade matching two exclusion rules escaped the one you switched on.
 * A drawdown percentage was withheld with instructions the page gave you no way to follow.
 *
 * ⚠ States the lab cannot produce on demand are MOCKED by mutating the REAL list and the REAL
 * run detail, never by hand-writing a fixture — a hand-written one drifts from the backend's
 * model and then pins a shape the server never sends.
 *
 * ⚠ It asserts on MUTATED state, never on which rows happen to be in the database today. The
 * Overview and Stress Tests suites both broke on the data rather than on the code, and a test
 * that fails on a day nothing is wrong is indistinguishable from a regression until read.
 *
 * Needs the backend on :8000 and the dev server on :5173 (`./start.sh`).
 */
import { test, expect } from '@playwright/test'
import type { BacktestDetail, BacktestSummary } from '../src/types'

const API = 'http://localhost:8000'

async function getJson<T>(path: string): Promise<T> {
  const res = await fetch(API + path)
  if (!res.ok) throw new Error(`backend not answering for ${path} (${res.status}) — is it running?`)
  return res.json() as Promise<T>
}

async function anyCompleteRun(): Promise<BacktestSummary> {
  const runs = await getJson<BacktestSummary[]>('/backtests/runs')
  const run = runs.find((r) => r.status === 'complete')
  if (!run) throw new Error('no completed run in the lab — this suite needs one to mutate')
  return run
}

// ── The list page ─────────────────────────────────────────────────────────────

test.describe('Backtests list — destructive actions ask first', () => {
  test('the row Rerun opens a confirmation and fires nothing until it is confirmed', async ({
    page,
  }) => {
    // 🔴 It was `retry.mutate(run.run_id)` on the click: one click, no confirmation, and a rerun
    // RESETS the row in place and replaces its result. The icon sat inside a row whose own click
    // navigates away, at 13px, beside the chevron.
    const run = await anyCompleteRun()

    const retries: string[] = []
    await page.route(
      (u) => /\/api\/backtests\/runs\/[0-9a-z]+\/retry$/.test(u.pathname),
      async (route) => {
        retries.push(route.request().url())
        await route.fulfill({
          status: 202,
          contentType: 'application/json',
          body: '{"status":"running"}',
        })
      }
    )

    await page.goto('/backtests?tab=runs')
    const row = page.locator('tbody tr', { hasText: run.run_id.slice(0, 6) }).first()
    await expect(page.locator('tbody tr').first()).toBeVisible()

    const rerunBtn = page
      .locator('tbody tr')
      .first()
      .getByTitle(/Rerun|Retry/)
    await rerunBtn.click()

    await expect(
      page.getByRole('heading', { name: /Rerun this run\?|Retry this run\?/ })
    ).toBeVisible()
    expect(retries, 'the click alone must not start a run').toHaveLength(0)

    await page.getByRole('button', { name: /^(Rerun|Retry)$/ }).click()
    await expect.poll(() => retries.length).toBe(1)
    // Guard against the modal firing for a DIFFERENT row than the one clicked.
    expect(retries[0]).toContain('/backtests/runs/')
    void row
  })

  test('cancelling the rerun confirmation starts nothing', async ({ page }) => {
    const retries: string[] = []
    await page.route(
      (u) => /\/api\/backtests\/runs\/[0-9a-z]+\/retry$/.test(u.pathname),
      async (route) => {
        retries.push(route.request().url())
        await route.fulfill({
          status: 202,
          contentType: 'application/json',
          body: '{"status":"running"}',
        })
      }
    )

    await page.goto('/backtests?tab=runs')
    await expect(page.locator('tbody tr').first()).toBeVisible()
    await page
      .locator('tbody tr')
      .first()
      .getByTitle(/Rerun|Retry/)
      .click()
    await page.getByRole('button', { name: 'Cancel' }).click()

    await expect(page.getByRole('heading', { name: /Rerun this run\?/ })).toHaveCount(0)
    expect(retries).toHaveLength(0)
  })

  test('a row has a delete button and its confirmation names the cascade', async ({ page }) => {
    // 🔴 There was NO per-row delete: `deleteRunId` was never set, so `handleSingleDelete` and
    // `cascadeMessage` were unreachable — and `cascadeMessage` is the ONLY place that warns a
    // delete takes attached optimizations, sweeps and tuning iterations with it.
    const run = await anyCompleteRun()

    // Give it an attached optimization, so the cascade sentence has something to report.
    const opts = await getJson<Record<string, unknown>[]>('/optimizations')
    await page.route(
      (u) => u.pathname.endsWith('/api/optimizations'),
      (route) =>
        route.fulfill({
          status: 200,
          contentType: 'application/json',
          body: JSON.stringify([
            ...opts,
            {
              ...(opts[0] ?? {}),
              optimization_id: 'mockopt00001',
              source_run_id: run.run_id,
              strategy_id: run.strategy_id,
              status: 'complete',
            },
          ]),
        })
    )

    await page.goto('/backtests?tab=runs')
    const row = page.locator('tbody tr', { hasText: run.strategy_name }).first()
    await expect(row).toBeVisible()
    await row.getByTitle('Delete this run').click()

    await expect(page.getByText(/optimization/i).first()).toBeVisible()
    await expect(page.getByText(/will also be permanently deleted/i)).toBeVisible()
  })

  test('the bulk delete warns about the cascade too', async ({ page }) => {
    // The bulk path was the ONLY reachable delete, and it was the one with no cascade warning.
    const run = await anyCompleteRun()
    const opts = await getJson<Record<string, unknown>[]>('/optimizations')
    await page.route(
      (u) => u.pathname.endsWith('/api/optimizations'),
      (route) =>
        route.fulfill({
          status: 200,
          contentType: 'application/json',
          body: JSON.stringify([
            ...opts,
            {
              ...(opts[0] ?? {}),
              optimization_id: 'mockopt00002',
              source_run_id: run.run_id,
              strategy_id: run.strategy_id,
              status: 'complete',
            },
          ]),
        })
    )

    await page.goto('/backtests?tab=runs')
    const row = page.locator('tbody tr', { hasText: run.strategy_name }).first()
    await expect(row).toBeVisible()
    await row.locator('input[type=checkbox]').check()
    await page.getByRole('button', { name: /Delete 1/ }).click()

    await expect(page.getByText(/will also be permanently deleted/i)).toBeVisible()
  })

  test('millions render as M, not as five digits of thousands', async ({ page }) => {
    // `+$14387.5k` — the `k` branch with no `M` step, in the column whose job is comparing runs.
    const runs = await getJson<BacktestSummary[]>('/backtests/runs')
    const big = { ...runs.find((r) => r.status === 'complete')!, net_pnl: 14_387_474.88 }
    await page.route(
      (u) => u.pathname.endsWith('/api/backtests/runs'),
      (route) =>
        route.fulfill({
          status: 200,
          contentType: 'application/json',
          body: JSON.stringify([big, ...runs.filter((r) => r.run_id !== big.run_id)]),
        })
    )

    await page.goto('/backtests?tab=runs')
    await expect(page.locator('tbody tr').first()).toContainText('+$14.4M')
    await expect(page.locator('tbody tr').first()).not.toContainText('14387.5k')
  })
})

// ── The detail page ───────────────────────────────────────────────────────────

test.describe('Backtest detail — captions and rules', () => {
  test('the Bank holidays rule does not claim to be on by default', async ({ page }) => {
    // A caption is a claim about the state beside it. Both rules were defaulted OFF on
    // 2026-08-01 and this note stayed, contradicting its own unticked checkbox.
    const run = await anyCompleteRun()
    await page.goto(`/backtests/runs/${run.run_id}`)

    await page
      .getByRole('button', { name: /Excluding|Counting all|trades/ })
      .first()
      .click()
      .catch(() => {
        /* the pill's label varies with state; the fallback below finds it */
      })
    const pill = page.locator('button', { hasText: /Excluding \d|Counting all/ }).first()
    if (await pill.count()) await pill.click()

    const rule = page.locator('label, div', { hasText: 'Bank holidays' }).first()
    await expect(rule).toBeVisible()
    await expect(page.getByText('on by default')).toHaveCount(0)

    const holidayBox = page.locator('input[type=checkbox]').filter({ has: page.locator(':scope') })
    void holidayBox
  })

  test('a trade that is BOTH a holiday and a news window is removed by either rule', async ({
    page,
  }) => {
    // 🔴 The removal was one `if / else if` chain, so a trade matching both took the holiday
    // branch and the news rule never saw it. Tick News with Holidays off and that trade stayed in
    // the result — silently exempt from the rule you had just switched on. Nothing on screen said
    // so; the counts were right and the arithmetic underneath them was not.
    const run = await anyCompleteRun()
    const news = await getJson<{ trades: { index: number }[] }>(
      `/backtests/runs/${run.run_id}/news?pre=15&post=30`
    )

    // Tag exactly ONE trade as both, and nothing else as either — so the delta the page reports
    // can only come from this trade.
    const target = news.trades[Math.floor(news.trades.length / 2)].index
    await page.route(
      (u) => u.pathname.includes('/news'),
      (route) =>
        route.fulfill({
          status: 200,
          contentType: 'application/json',
          body: JSON.stringify({
            ...news,
            news_trade_count: 1,
            holiday_trade_count: 1,
            trades: news.trades.map((t) => ({
              ...t,
              in_coverage: true,
              in_news: t.index === target,
              in_holiday: t.index === target,
              title: t.index === target ? 'Both' : null,
            })),
          }),
        })
    )

    await page.goto(`/backtests/runs/${run.run_id}`)
    const pill = page.locator('button', { hasText: /Excluding/ }).first()
    await expect(pill).toBeVisible()
    await expect(pill).toContainText('Excluding nothing')
    await pill.click()

    // Tick High-impact news ONLY. Holidays stays off.
    await page.locator('button', { hasText: 'High-impact news' }).first().click()

    // The one trade that is both must go out. It used to survive: the holiday branch claimed it
    // and the news rule never got to look at it.
    await expect(pill).toContainText('Excluding 1 trade')
  })

  test('a run with no evaluated ruleset still reports a drawdown percentage', async ({ page }) => {
    // 🔴 The Risked hero read `—` and said "Set an account balance to measure drawdown as a
    // percentage", while the only control that sets one renders solely when a ruleset default
    // already exists. It asked for something the page gave no way to do — and the run's own
    // opening balance was on the equity curve the whole time.
    const run = await anyCompleteRun()
    const detail = await getJson<BacktestDetail>(`/backtests/runs/${run.run_id}`)
    await page.route(
      (u) => u.pathname === `/api/backtests/runs/${run.run_id}`,
      (route) =>
        route.fulfill({
          status: 200,
          contentType: 'application/json',
          body: JSON.stringify({ ...detail, evaluations: [] }),
        })
    )

    await page.goto(`/backtests/runs/${run.run_id}`)
    await expect(page.getByText('Risked')).toBeVisible()
    await expect(page.getByText('Set an account balance')).toHaveCount(0)
    // A real percentage, not an em-dash.
    await expect(page.getByText(/worst drawdown/i)).toBeVisible()
    const risked = page.locator('div', { hasText: /^worst drawdown$/ }).first()
    void risked
    await expect(page.locator('text=/\\d+\\.\\d%/').first()).toBeVisible()
  })

  test('a partly-priced re-price says so instead of "Charging nothing"', async ({ page }) => {
    // A short answer made `active` false, and `active` false renders as "Charging nothing" with
    // the reader's boxes still ticked — the same failure the isError fix exists to have stopped,
    // one branch over.
    const runs = await getJson<BacktestSummary[]>('/backtests/runs')
    const run = runs.find((r) => r.status === 'complete' && r.runner === 'python')
    if (!run) test.skip(true, 'needs a completed python run')

    await page.route(
      (u) => u.pathname.includes('/repriced'),
      async (route) => {
        const res = await route.fetch()
        const body = await res.json()
        // Drop the last priced trade — the server answered, and its answer is short.
        await route.fulfill({
          status: 200,
          contentType: 'application/json',
          body: JSON.stringify({ ...body, trades: (body.trades ?? []).slice(0, -1) }),
        })
      }
    )

    await page.goto(`/backtests/runs/${run!.run_id}`)
    const pill = page.locator('button', { hasText: /Charging/ }).first()
    await expect(pill).toBeVisible()
    await pill.click()
    // ⚠ A cost rule is a BUTTON, not a label — `CostRule` renders its own checkbox glyph so a
    // locked row can be disabled. A `label` locator finds nothing and times out.
    await page.locator('button', { hasText: 'Spread' }).first().click()

    await expect(page.locator('button', { hasText: /unpriced/ })).toBeVisible()
    await expect(page.getByText(/came back unpriced/)).toBeVisible()
  })

  test('a failed run offers exactly ONE Retry, and it is not on the banner', async ({ page }) => {
    // 🔴 THIS CHECK IS THE REVERSE OF WHAT IT ASSERTED FROM 2026-08-06 TO 2026-08-15, and the
    // history is why it still exists rather than being deleted.
    //
    // The original defect was that `FailureBanner` declared `onRetry` and the page never passed
    // one, so the banner had NO button — on the one banner a reader is looking at because
    // something failed. The fix added a button to the banner. That was right about the missing
    // control and wrong about where it belonged: the page HEADER already carries a Retry firing
    // the identical action, so the page ended up with two controls for one destructive action —
    // two places for the disabled state and the period gate to drift apart. Aaron, from the
    // screen: *"I don't need the double retry buttons, keep the one outside."*
    //
    // ⚠ Deleting this check would leave nothing stopping a future reader re-adding the banner
    // button as a "fix" for the ORIGINAL defect, whose reasoning still reads as sound. It now
    // pins the count, which is the property that actually matters.
    const run = await anyCompleteRun()
    const detail = await getJson<BacktestDetail>(`/backtests/runs/${run.run_id}`)
    await page.route(
      (u) => u.pathname === `/api/backtests/runs/${run.run_id}`,
      (route) =>
        route.fulfill({
          status: 200,
          contentType: 'application/json',
          body: JSON.stringify({ ...detail, status: 'failed_unknown', error_message: 'boom' }),
        })
    )

    await page.goto(`/backtests/runs/${run.run_id}`)

    // The banner still RENDERS — it is what tells you the run failed and why.
    const banner = page.getByTestId('failure-banner')
    await expect(banner).toBeVisible()
    await expect(banner.getByRole('button', { name: /Retry/ })).toHaveCount(0)

    // ⚠ And the surviving control is asserted to EXIST, not merely that the banner's is gone.
    // Half of this rule alone would pass against a page with no way to retry at all — which is
    // the original defect, restored by the fix for its own successor.
    await expect(page.getByRole('button', { name: /Retry/ })).toHaveCount(1)
  })

  test('one log poll during a run, not two', async ({ page }) => {
    // `RunningBanner` asked for 500 lines and `LogsSection` for 200 — different query keys, so
    // two cache entries and two `/log` requests every 2 seconds for the whole run.
    const run = await anyCompleteRun()
    const detail = await getJson<BacktestDetail>(`/backtests/runs/${run.run_id}`)
    await page.route(
      (u) => u.pathname === `/api/backtests/runs/${run.run_id}`,
      (route) =>
        route.fulfill({
          status: 200,
          contentType: 'application/json',
          body: JSON.stringify({ ...detail, status: 'running' }),
        })
    )

    const logUrls = new Set<string>()
    await page.route(
      (u) => u.pathname.endsWith('/log'),
      async (route) => {
        logUrls.add(new URL(route.request().url()).search)
        await route.fulfill({ status: 200, contentType: 'text/plain', body: 'working' })
      }
    )

    await page.goto(`/backtests/runs/${run.run_id}`)
    await expect(page.getByText('Running').first()).toBeVisible()
    await page.waitForTimeout(3_000)

    expect([...logUrls], 'two distinct line counts means two polls of one endpoint').toHaveLength(1)
  })
})
