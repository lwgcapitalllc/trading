/**
 * The price chart's DRILL-DOWN (M1/M5) and the timeframe control.
 *
 * Three defects Aaron reported off the screen on 2026-08-06/07, all in this one control:
 *   1. pressing M5 while reading 2020 threw the chart forward to 2026 — the fetch anchored on the
 *      run's LAST bar, never on the viewport;
 *   2. a drill-down's only sign of life was an 11px grey line in the header while the chart went on
 *      showing the previous timeframe's candles, so a ~4.5s fetch read as nothing happening;
 *   3. a window the feed refuses said "no data here (feed offline, or none this far back?)" —
 *      hedging, because the backend's `available` was `bool(candles)` and could not tell the two
 *      apart even though the fetch knew.
 *
 * ⚠ Three of these drive the REAL backend rather than intercepting the candle route, which is the
 * opposite call from `calendar.spec.ts` and deliberate: what is under test is where the chart LANDS
 * after a real fetch, and a mocked feed would be measuring the mock. The refusal check is mocked,
 * because the only way to produce it for real is to take the MT5 terminal down.
 *
 * ⚠ The applied WINDOW is not the same question as where the view is PARKED — a switch can leave
 * the window untouched and still sit on its right edge, six weeks from the date being read. Hence
 * `data-view-centre`, a declared test seam beside `data-applied-lo`/`-hi`; klinecharts draws its
 * time axis into the canvas, so none of this is otherwise readable from the DOM.
 */
import { test, expect, type Page } from '@playwright/test'
import { requireRun } from './fixtures'

const RUN = '997c14cc53bc'

// Fail by NAME if this pinned run has left the lab, instead of timing out on a chart
// that never rendered and sending the reader at the feature. See `fixtures.ts`.
test.beforeAll(async () => {
  await requireRun(
    RUN,
    'a long M15 python run with 1m history behind it, so a drill-down has finer bars to fetch'
  )
})
const DATE = '2020-08-05'
const TARGET = new Date(`${DATE}T00:00:00Z`).getTime()
const DAY = 86_400_000

async function openPriceTab(page: Page) {
  await page.goto(`/backtests/runs/${RUN}`)
  await page.getByRole('button', { name: /price/i }).click()
  await expect(page.getByTitle('Go to date')).toBeVisible({ timeout: 180_000 })
}

async function jumpTo(page: Page, iso: string) {
  await page.getByTitle('Go to date').click()
  const box = page.locator('input[type="date"]')
  await box.fill(iso)
  await box.press('Enter')
  await page.waitForTimeout(5000)
}

/** ⚠ Playwright's real click on a dropdown item is blocked here by the date control that was just
 *  used; the page itself is responsive (proved with an in-page 50ms timer: 2,407 samples over
 *  120s). `dispatchEvent` still runs React's onClick, which is the thing under test. */
async function pickTf(page: Page, tf: string) {
  await page
    .locator('button')
    .filter({ hasText: /^(M1|M5|M15|M30|H1|H4|D1)$/ })
    .first()
    .click()
  await page.waitForTimeout(250)
  await page
    .locator('button')
    .filter({ hasText: new RegExp(`^${tf}$`) })
    .last()
    .dispatchEvent('click')
}

async function settleDrill(page: Page) {
  await expect(page.getByText(/loading .* bars/)).toHaveCount(0, { timeout: 180_000 })
  await page.waitForTimeout(2000)
}

const applied = async (page: Page) => ({
  lo: Number(await page.locator('[data-applied-lo]').getAttribute('data-applied-lo')),
  hi: Number(await page.locator('[data-applied-lo]').getAttribute('data-applied-hi')),
})
const viewCentre = async (page: Page) =>
  Number(await page.locator('[data-applied-lo]').getAttribute('data-view-centre'))

test.describe('price chart — drill-down', () => {
  test('a drill-down loads the window being READ, not the newest bars', async ({ page }) => {
    test.setTimeout(360_000)
    await openPriceTab(page)
    await jumpTo(page, DATE)
    await pickTf(page, 'M5')
    await settleDrill(page)

    const { lo, hi } = await applied(page)
    // Before the fix this window was 2025-11-09 .. 2026-08-06 — six years from the date on screen.
    expect(lo).toBeLessThanOrEqual(TARGET)
    expect(hi).toBeGreaterThanOrEqual(TARGET)
    // And the VIEW is on it, not parked on the window's right edge (which measured 2.5 months out).
    expect(Math.abs((await viewCentre(page)) - TARGET)).toBeLessThan(2 * DAY)
  })

  test('a drill-down says it is loading, on the chart and on the button', async ({ page }) => {
    test.setTimeout(360_000)
    await openPriceTab(page)
    await jumpTo(page, DATE)
    await pickTf(page, 'M1')
    // The badge names BOTH timeframes: the one being fetched, and the one on screen meanwhile. The
    // chart keeps showing the coarser bars throughout, so without this the two states are identical.
    await expect(page.getByText(/loading M1 bars/)).toBeVisible({ timeout: 30_000 })
    await expect(page.getByText(/showing M15 meanwhile/)).toBeVisible()
    await settleDrill(page)
    await expect(page.getByText(/loading M1 bars/)).toHaveCount(0)
  })

  test('switching display timeframes keeps the reader on their date', async ({ page }) => {
    test.setTimeout(360_000)
    await openPriceTab(page)
    await jumpTo(page, DATE)
    // M15 -> H1 landed 42 days out before the fix: `applyNewData` parks on the newest loaded bar,
    // and after a jump that bar is mid-history.
    await pickTf(page, 'H1')
    await page.waitForTimeout(3000)
    expect(Math.abs((await viewCentre(page)) - TARGET)).toBeLessThan(2 * DAY)
  })

  test('a window the feed refuses says WHY, in the feed’s own words', async ({ page }) => {
    test.setTimeout(360_000)
    // The only way to get this for real is to take the MT5 terminal down, so the refusal is mocked —
    // with the exact payload the backend produces, measured against the live one:
    //   available:false + feed_error "HistoryFloorError: XAUUSD has no real 1-minute history
    //   before 2018-09-14 on VantageMarkets-Demo (measured, not assumed). You asked for ..."
    await page.route('**/backtests/runs/*/candles*', (route) =>
      route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({
          instrument: 'XAUUSD',
          timeframe: 'M1',
          candles: [],
          available: false,
          feed_error:
            'HistoryFloorError: XAUUSD has no real 1-minute history before 2018-09-14 on ' +
            'VantageMarkets-Demo (measured, not assumed). You asked for 2010-03-01.',
          data_start_ms: null,
          hard_edge: false,
        }),
      })
    )
    await openPriceTab(page)
    await pickTf(page, 'M1')
    // The old message asked the reader the question the fetch had already answered. The date is the
    // whole point of the sentence, so it has to survive to the screen.
    await expect(page.getByText(/no real 1-minute history before 2018-09-14/)).toBeVisible({
      timeout: 60_000,
    })
    // The exception CLASS is our plumbing and must NOT be shown.
    await expect(page.getByText(/HistoryFloorError/)).toHaveCount(0)
    // And it still says which bars are actually on screen underneath.
    await expect(page.getByText(/showing M15/)).toBeVisible()
  })
})

/**
 * The three drill-down paths that shipped in 8b50be7 REASONED THROUGH BUT NOT DRIVEN, named in
 * `ChartPanel/CLAUDE.md` rather than left to look covered. Closing them here.
 *
 * Two are mocked, and that is the opposite call from the checks above — deliberately. Producing a
 * broker's true data edge for real means scrolling 12,000 bars, and producing an empty answer means
 * taking the MT5 terminal down; neither is a thing under test, they are just how you ARRIVE at the
 * branch. The payloads are the shapes the live endpoint actually returns.
 */
test.describe('price chart — drill-down, the paths that were not driven', () => {
  /**
   * 🔴 **`drillNewer` — paging RIGHT toward the present — HAS NO CHECK HERE, and that is a
   * deliberate outcome rather than an oversight.**
   *
   * It WORKS, and it was verified by hand: driving the real page and counting the candle requests,
   * scrolling right issued **36 further requests at `tf=M5`** and carried the window from
   * 2021-06-29 to 2024-11-26 — the drill timeframe throughout, never base-timeframe bars spliced in.
   *
   * What could not be built is a check that BITES. Three drafts:
   *   - scroll from the landing → passed only while the view was wrongly parked on the applied right
   *     edge, i.e. it would have gone GREEN ON THE DEFECT this suite exists to catch;
   *   - compare `data-applied-hi` before/after → a race with how far the landing itself pages;
   *   - park near the newest bar with `goToDate`, then scroll → the reader now lands mid-window with
   *     ~9,000 M5 bars to their right, and no wheel loop in a test crosses that.
   *
   * A green test that cannot fail is worse than no test, because it reads as coverage. Recorded
   * here instead, with the measurement, so the next person knows exactly what was and was not done.
   */

  /**
   * ⚠ **This check pins the SHAPE, not the `edge` guard, and mutation proved the difference.**
   * Deleting `drillOlder`'s `oldest <= cached.edge` early return leaves it GREEN — because without
   * the guard the request still goes out, still comes back with nothing strictly older, still
   * answers `more: false`, and the pager still stops in the right place. The guard saves a round
   * trip; it is not what makes the pager terminate. Kept anyway, because "reaching the broker's
   * limit stops the pager rather than looping on the same window for ever" is worth pinning and is
   * a rule stated nowhere else — but it must not be read as covering the guard it sits beside.
   */
  test('the broker’s data edge stops the pager instead of asking for ever', async ({ page }) => {
    test.setTimeout(360_000)
    let start = 0
    await page.route('**/backtests/runs/*/candles*', async (route) => {
      const url = new URL(route.request().url())
      const to = Number(url.searchParams.get('to_ms'))
      // A feed with EXACTLY one window and nothing behind it: every request is answered from the
      // same floor, flagged as the broker's true limit.
      start = start || to - 3 * DAY
      const candles = []
      for (let t = start; t <= to; t += 5 * 60_000) {
        candles.push({ time: t, open: 1800, high: 1801, low: 1799, close: 1800, volume: 10 })
      }
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({
          instrument: 'XAUUSD',
          timeframe: 'M5',
          candles,
          available: true,
          feed_error: null,
          data_start_ms: start,
          hard_edge: true,
        }),
      })
    })
    await openPriceTab(page)
    await pickTf(page, 'M5')
    await settleDrill(page)
    const box = await page.locator('canvas').first().boundingBox()
    if (!box) throw new Error('no canvas')
    for (let i = 0; i < 300; i++) {
      await page.mouse.move(box.x + box.width * 0.5, box.y + box.height * 0.5)
      await page.mouse.wheel(-400, 0)
    }
    await page.waitForTimeout(4000)
    // `drillOlder` must refuse once the loaded oldest bar IS the reported edge. Without that guard
    // it keeps requesting the same window for ever, prepending nothing each time.
    expect((await applied(page)).lo).toEqual(start)
  })

  test('a drill-down that comes back empty does not freeze every later jump', async ({ page }) => {
    test.setTimeout(360_000)
    // 🔴 This is the failure mode that made the path worth closing: `drillTo` sets `jumpingRef`
    // before the fetch, and `goToDate` returns immediately while it is set. If an empty answer does
    // not release it, the chart refuses EVERY later jump and every page for the rest of the session
    // — silently, with a perfectly healthy-looking chart.
    let blockAll = true
    await page.route('**/backtests/runs/*/candles*', async (route) => {
      if (!blockAll) return route.continue()
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({
          instrument: 'XAUUSD',
          timeframe: 'M5',
          candles: [],
          available: true,
          feed_error: null,
          data_start_ms: null,
          hard_edge: false,
        }),
      })
    })
    await openPriceTab(page)
    await pickTf(page, 'M5')
    await settleDrill(page)
    // Back to a display timeframe, where a jump needs no feed at all — so if it still cannot move,
    // the guard is stuck rather than the data missing.
    blockAll = false
    await pickTf(page, 'M15')
    await page.waitForTimeout(2000)
    await jumpTo(page, DATE)
    expect(Math.abs((await viewCentre(page)) - TARGET)).toBeLessThan(2 * DAY)
  })
})
