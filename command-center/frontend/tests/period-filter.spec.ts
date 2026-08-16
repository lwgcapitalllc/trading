/**
 * The period filter on BacktestDetail — cut a window out of a finished run and re-read the whole
 * page on it, with no rerun.
 *
 * ⚠ A FAIL-WATCH AGAINST HEAD IS VACUOUS FOR MOST OF THIS FILE and that is stated rather than
 * glossed: the control did not exist, so nearly every check would go red because the element is
 * absent, which proves the locator and nothing else. **Non-vacuity is by MUTATION, named in a
 * comment on each check.** The exceptions are the two that pin behaviour HEAD already had and got
 * WRONG — the Breakdown tab ignoring the filters above it, and the regime table doing the same —
 * and those two were watched red against HEAD for the right reason.
 *
 * ⚠ The arithmetic is pinned OUTSIDE the browser as well, in `scripts/check_period_rebase.mjs`,
 * because the properties that matter here are numeric identities and asserting them through
 * rendered, abbreviated, currency-formatted text would be asserting on the formatter. What the
 * browser checks is that the control exists, that it reaches every section, and that it says what
 * it is doing.
 *
 * ⚠ It asserts on a MUTATED payload, never on which runs happen to be in the lab today. Two suites
 * in this folder have already broken on the data rather than on the code.
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

/**
 * A completed run with enough dated trades to cut in half.
 *
 * ⚠ It RESOLVES the run rather than naming one. A spec pinned to a literal run id is a spec with
 * an expiry date — `tuning.spec.ts` lost eight checks the day its run was deleted, and the failure
 * pointed at the leaderboard, which was fine.
 */
async function runWithTrades(
  minTrades = 20
): Promise<{ run: BacktestSummary; detail: BacktestDetail }> {
  const runs = await getJson<BacktestSummary[]>('/backtests/runs')
  for (const run of runs) {
    if (run.status !== 'complete') continue
    if ((run.trade_count ?? 0) < minTrades) continue
    const detail = await getJson<BacktestDetail>(`/backtests/runs/${run.run_id}`)
    const dated = detail.equity_curve.filter((p) => p.profit != null && p.date)
    if (dated.length >= minTrades) return { run, detail }
  }
  throw new Error(`no completed run with ≥${minTrades} dated trades — this suite needs one`)
}

/** The date that splits a run's trades roughly in half — so a window is guaranteed to narrow it. */
function midDate(detail: BacktestDetail): string {
  const dated = detail.equity_curve.filter((p) => p.profit != null && p.date)
  return (dated[Math.floor(dated.length / 2)].date ?? '').slice(0, 10)
}

test.describe('The period filter cuts a window and the whole page follows', () => {
  test('clicking the period chip opens the picker and a window narrows the trade count', async ({
    page,
  }) => {
    // MUTATION: drop the `narrowed` guard from `useDateFilter` so a window never activates → the
    // header suffix never appears → red.
    const { run, detail } = await runWithTrades()
    const from = midDate(detail)

    await page.goto(`/backtests/runs/${run.run_id}`)
    const chip = page.getByTestId('period-filter')
    await expect(chip).toBeVisible()

    await page.getByTestId('period-filter-open').click()
    await page.getByTestId('period-from').fill(from)

    // The Performance header states the window and BOTH counts. A label that is a number cannot
    // say one thing while the grid says another.
    const header = page.getByTestId('perf-collapse-toggle')
    await expect(header).toContainText(/of \d+ trades/)
    const dated = detail.equity_curve.filter((p) => p.profit != null && p.date)
    const kept = dated.filter((p) => (p.date ?? '').slice(0, 10) >= from).length
    await expect(header).toContainText(`${kept} of ${dated.length} trades`)
    expect(kept, 'the fixture must actually narrow, or this check pins nothing').toBeLessThan(
      dated.length
    )
  })

  test('the window survives a reload — it lives in the URL', async ({ page }) => {
    // MUTATION: move `from`/`to` into `useState` → red.
    // Page-level view state lives in the URL by house rule, and a window you picked has to survive
    // a refresh, a Back out of the price chart, and being sent to somebody else.
    const { run, detail } = await runWithTrades()
    const from = midDate(detail)

    await page.goto(`/backtests/runs/${run.run_id}?from=${from}`)
    const header = page.getByTestId('perf-collapse-toggle')
    await expect(header).toContainText(/of \d+ trades/)

    await page.reload()
    await expect(page.getByTestId('perf-collapse-toggle')).toContainText(/of \d+ trades/)
    expect(page.url()).toContain(`from=${from}`)
  })

  test('clearing puts the whole run back', async ({ page }) => {
    // MUTATION: make the × call `setRange(from, '')` instead of clearing both → red.
    const { run, detail } = await runWithTrades()
    const from = midDate(detail)

    await page.goto(`/backtests/runs/${run.run_id}?from=${from}`)
    await expect(page.getByTestId('period-filter-clear')).toBeVisible()
    await page.getByTestId('period-filter-clear').click()

    await expect(page.getByTestId('period-filter-clear')).toHaveCount(0)
    await expect(page.getByTestId('perf-collapse-toggle')).not.toContainText(/of \d+ trades/)
    expect(page.url()).not.toContain('from=')
  })

  test('the picker states the rebase — what it started from, and what was really there', async ({
    page,
  }) => {
    // MUTATION: delete the rebase paragraph from the popover → red.
    // 🔴 THIS IS THE CHECK THAT MATTERS MOST ON THIS PAGE. The window's dollars are scaled onto the
    // run's own opening balance, so a reader comparing the headline to the run's would otherwise
    // have no way to know why it moved. Asserting only that a window applies would pass against a
    // build that rebased silently — which is a page reporting a balance nobody ever had.
    const { run, detail } = await runWithTrades()
    const from = midDate(detail)

    await page.goto(`/backtests/runs/${run.run_id}?from=${from}`)
    await page.getByTestId('period-filter-open').click()

    const popover = page.getByTestId('period-filter')
    await expect(popover).toContainText(/Reads as if you started with/)
    await expect(popover).toContainText(/The account really held/)
    // Both halves: that it is scaled, AND that ratios are not. Dropping the second sentence would
    // leave a reader unsure whether the profit factor moved too.
    await expect(popover).toContainText(/scaled by ×/)
    await expect(popover).toContainText(/profit factor, win rate, R, drawdown % — are untouched/)
    // And that it is NOT a rerun. The whole feature exists to replace reruns, so the one way it
    // differs from one is the sentence a reader most needs.
    await expect(popover).toContainText(/It is not a rerun/)
  })

  test('the Breakdown tab follows the filters above it', async ({ page }) => {
    // 🔴 WATCHED RED AGAINST HEAD, for a defect that PREDATES this feature: all three breakdown
    // charts read `effRun`, so they followed neither the NEWS filter nor the COSTS pill — three
    // charts under a header reading "139 of 142 trades" drawing all 142.
    //
    // ⚠ IT ASSERTS ON RENDERED TEXT, AND THE FIRST VERSION OF THIS CHECK DID NOT — it compared
    // SCREENSHOTS of the drawdown chart and PASSED against the mutation, because Recharts animates
    // on mount and two page loads differ by a few pixels of tween whatever the data is. A
    // `not.toBe(0)` on a screenshot is satisfied by noise. Both observables below are text and
    // neither is animated.
    //
    // ⚠ It covers TWO of the three charts by two different props, and says which: the x-axis of
    // `DrawdownChart` (`equity`) and the trade counts of `DirectionBreakdown` (`equity`). Reverting
    // only one of them turns only its half red, which is the point of asserting both.
    const { run, detail } = await runWithTrades(40)
    const from = midDate(detail)

    const openBreakdown = async (qs: string) => {
      await page.goto(`/backtests/runs/${run.run_id}${qs}`)
      await page.getByRole('button', { name: 'Breakdown', exact: true }).click()
      await expect(page.getByText('Drawdown from peak')).toBeVisible()
      // ⚠ `allTextContents`, NOT `allInnerTexts`, and scoped to `.xAxis`. A Recharts tick is a
      // `<text>` with nested `<tspan>`s, and `allInnerTexts()` on SVG returns a row of `null` —
      // which then compares equal to another row of `null` and passes whatever the chart drew.
      // That is the third shape of vacuous pass this one check walked into.
      const axis = await page
        .locator('.recharts-wrapper')
        .first()
        .locator('.xAxis .recharts-cartesian-axis-tick-value')
        .allTextContents()
      const counts = (await page.getByText(/^\d+ trades · avg /).allInnerTexts()).map(
        (t) => parseInt(t, 10) || 0
      )
      return { axis, traded: counts.reduce((a, b) => a + b, 0) }
    }

    const whole = await openBreakdown('')
    const windowed = await openBreakdown(`?from=${from}`)

    const dated = detail.equity_curve.filter((p) => p.profit != null && p.date)
    const kept = dated.filter((p) => (p.date ?? '').slice(0, 10) >= from).length
    expect(kept, 'the fixture must actually narrow').toBeLessThan(dated.length)

    expect(
      windowed.traded,
      'Long vs Short must count only the window — it read `effRun` and ignored every filter'
    ).toBe(kept)
    expect(whole.traded, 'and the unfiltered page must still count them all').toBe(dated.length)
    // The FIRST tick is an endpoint, so Recharts renders it as a full date (`Jan 3 '23`) rather
    // than a month. Asserting it lands in the window's own year is specific — merely asserting the
    // two tick rows DIFFER would pass on a chart that had shifted its ticks for any reason.
    expect(whole.axis.length, 'the fixture must render a date axis').toBeGreaterThan(2)
    expect(
      windowed.axis[0],
      'the drawdown chart’s axis must START in the window — it read `effRun` and ignored it'
    ).toContain(`'${from.slice(2, 4)}`)
    expect(whole.axis[0], 'and the unfiltered page must still start at the run').not.toBe(
      windowed.axis[0]
    )
  })

  test('Performance by Regime is recomputed on the window, not left at the run’s stored rows', async ({
    page,
  }) => {
    // 🔴 WATCHED RED AGAINST HEAD. `regime_breakdown` is computed server-side over every trade, and
    // the table rendered it verbatim under a Performance panel that was already filtered.
    // ⚠ It asserts the TRADE COUNTS fall, not that the table merely re-renders — a table that
    // re-rendered identical rows is exactly the defect.
    const { run, detail } = await runWithTrades(40)
    const from = midDate(detail)
    test.skip(!detail.regime_breakdown?.length, 'this run carries no regime breakdown')

    const totalOf = async () => {
      const table = page.locator('table', { hasText: 'Prof. Factor' }).first()
      await expect(table).toBeVisible()
      const cells = await table.locator('tbody tr td:nth-child(3)').allInnerTexts()
      return cells.reduce((a, t) => a + (parseInt(t.replace(/[^0-9]/g, ''), 10) || 0), 0)
    }

    await page.goto(`/backtests/runs/${run.run_id}`)
    const whole = await totalOf()

    await page.goto(`/backtests/runs/${run.run_id}?from=${from}`)
    const windowed = await totalOf()

    expect(windowed, 'the per-regime trade counts must fall with the window').toBeLessThan(whole)
    expect(whole, 'the fixture must have counts to fall from').toBeGreaterThan(0)
  })

  test('the price chart is handed only the window’s candles and trades', async ({ page }) => {
    // MUTATION: return `spec` unclipped from `PriceChartPanel` → red.
    // ⚠ Scoped to the PANEL's own root. Anything the host renders is outside it, and a page-wide
    // locator is this folder's most-repeated trap — four instances recorded.
    const { run, detail } = await runWithTrades(40)
    const from = midDate(detail)

    await page.goto(`/backtests/runs/${run.run_id}?from=${from}`)
    await page.getByRole('button', { name: 'Price', exact: true }).click()

    const panel = page.locator('[data-applied-lo]')
    await expect(panel).toBeVisible({ timeout: 30_000 })
    // The panel's applied window cannot start before the filter's start. This is the observable
    // the clip actually moves; a screenshot would pass against a panel that merely scrolled.
    const lo = await panel.getAttribute('data-applied-lo')
    expect(lo, 'the panel must report the window it is drawing').toBeTruthy()
    expect(Number(lo)).toBeGreaterThanOrEqual(Date.parse(`${from}T00:00:00Z`))
  })

  test('a window with no trades says the strategy stood still — it does not read as unfiltered', async ({
    page,
  }) => {
    // MUTATION: return `{ kept: rawTrades }` when a window matches nothing → red.
    // A window that produced nothing is a REAL answer, and the one most easily mistaken for the
    // filter being off. Same rule as `DrawdownMeter` refusing to draw an unmeasured tail as zero.
    const { run } = await runWithTrades()
    await page.goto(`/backtests/runs/${run.run_id}?from=1990-01-01&to=1990-01-02`)
    await page.getByTestId('period-filter-open').click()
    await expect(page.getByTestId('period-filter')).toContainText(/No trades in this period/)
  })

  test('a firm’s sized numbers refuse the filter and say why', async ({ page }) => {
    // MUTATION: drop `blocked` from `PeriodFilterChip` → the chip stays clickable → red.
    // A sized account opened at the FIRM's account size; rebasing it onto the run's own deposit
    // would state a prop account that never existed. Same guard the news and cost pills carry.
    const { run, detail } = await runWithTrades()
    test.skip(!detail.sized, 'this run is not engine-sized — nothing to refuse')

    await page.goto(`/backtests/runs/${run.run_id}`)
    await expect(page.getByTestId('period-filter-open')).toBeDisabled()
  })
})
