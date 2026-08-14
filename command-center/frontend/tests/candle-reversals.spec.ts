/**
 * The Candlestick Reversals layer on the backtest price chart — one candle repainted navy per
 * setup, the pattern candle at the turn.
 *
 * The layer's own SELECTION rules (which anchor gets a mark, which bar of the window it lands on,
 * the direction rule, the winner-vs-loser window) are the backend's and are pinned there by
 * `backend/tests/test_candle_overlays.py`, mutation-proven. What these five check is the half
 * that only exists in the browser:
 *
 *   1. the layer is OFFERED with its count and arrives switched OFF, like every analysis layer
 *      added since the fair value gaps;
 *   2. ticking it actually REPAINTS CANDLES — this one has to read the canvas, because the layer's
 *      whole output is pixels and a check that settled for "the menu row is ticked" would pass
 *      against a panel drawing nothing;
 *   3. it is WITHDRAWN off the base timeframe. A candlestick pattern is a property of ONE bar size
 *      — an M15 hammer is not an H1 hammer — so a resample has nothing honest to paint, and the
 *      row has to go with the drawing rather than sit there switched on over an empty chart;
 *   4. the pattern NAME is off by default and comes on from Chart settings. These tags carry no
 *      cross-overlay de-collision, unlike the batched `LABEL` template, so two marks a few bars
 *      apart write their names over the neighbouring candles — which is how it was reported;
 *   5. that setting's EXPLANATION is behind the ⓘ rather than printed under its label. A settings
 *      list is read by scanning names, and a paragraph under every row triples the height of a
 *      panel that has to fit beside a chart.
 *
 * ⚠ It drives the REAL backend, because the marks come from a server-side engine replay over the
 * run's own candles and a mocked spec would be testing the mock.
 *
 * ⚠ A fail-watch against HEAD is vacuous — the layer did not exist, so every check would go red on
 * the element simply being absent, which proves the locator and nothing else. Check 2 is instead
 * non-vacuous BY CONSTRUCTION: it measures the same pixels with the layer off and on, so it can
 * only pass on a real change. Checks 1, 3, 4 and 5 were proven by MUTATION (see each one's
 * comment).
 */
import { expect, test, type Page } from '@playwright/test'

// The longest python run in the lab: 2020-01-01 → 2026-08-06 at M15. Its anchor set is 159 trades
// + 35 three-of-three misses = 194, and each anchor is a SPAN, so it draws ~820 marks — the layer
// is exercised on a real set rather than a handful. (It was 518 anchors / 424 marks until blocked
// setups were dropped, and 194 / 153 while each anchor drew a single candle; both on 2026-08-08.
// See `services/chart_spec.reversal_anchors`.)
const RUN = '997c14cc53bc'

// A date this run has a mark on — 2026-07-30 05:30, a Bearish Engulfing inside a trade's span.
// Needed because the newest bars often carry none, and a pixel check on an empty viewport reads
// exactly like a layer that does not draw.
const DATE_WITH_A_MARK = '2026-07-30'

const LAYER = 'Candlestick Reversals'

// The `help` text `chartSettings.SECTIONS` declares for `candleMarkLabels`.
const HELP = /Off = the candle is painted navy/

/** The navy body the backend emits (`_NAVY` = #2f5fe0 = rgb(47,95,224)), counted across every
 *  canvas. Read from PIXELS on purpose: the repaint has no DOM presence at all. */
async function navyPixels(page: Page) {
  return page.evaluate(() => {
    let n = 0
    for (const c of Array.from(document.querySelectorAll('canvas'))) {
      const g = c.getContext('2d')
      if (!g || !c.width || !c.height) continue
      const d = g.getImageData(0, 0, c.width, c.height).data
      for (let i = 0; i < d.length; i += 4) {
        // A tolerance, because the body is stroked with a lighter edge and antialiased against it.
        if (
          Math.abs(d[i] - 47) < 14 &&
          Math.abs(d[i + 1] - 95) < 14 &&
          Math.abs(d[i + 2] - 224) < 14
        )
          n++
      }
    }
    return n
  })
}

async function openPriceTab(page: Page) {
  await page.goto(`/backtests/runs/${RUN}`)
  await page.getByRole('button', { name: /price/i }).click()
  // The panel is warm-mounted and klinecharts lays the applied window out on mount; the Go to date
  // pill only renders once the chart has a loaded range to bound itself to.
  await expect(page.getByTitle('Go to date')).toBeVisible({ timeout: 90_000 })
}

/** The lighter EDGE colour (`_NAVY_EDGE` = #7ea2ff), which the pattern TAG is drawn in and the navy
 *  body is not — so this is what separates "the mark is drawn" from "the mark is drawn AND named". */
async function edgePixels(page: Page) {
  return page.evaluate(() => {
    let n = 0
    for (const c of Array.from(document.querySelectorAll('canvas'))) {
      const g = c.getContext('2d')
      if (!g || !c.width || !c.height) continue
      const d = g.getImageData(0, 0, c.width, c.height).data
      for (let i = 0; i < d.length; i += 4) {
        if (
          Math.abs(d[i] - 126) < 20 &&
          Math.abs(d[i + 1] - 162) < 20 &&
          Math.abs(d[i + 2] - 255) < 20
        )
          n++
      }
    }
    return n
  })
}

async function toggleAnalysis(page: Page) {
  await page.getByRole('button', { name: /^Analysis/ }).click()
}

/** ⚠ The gear is a TOGGLE, not an open button — a second click closes the panel. Closing it via a
 *  `.getByRole('button').last()` inside the panel picks up the fib editor's own delete buttons. */
async function toggleSettings(page: Page) {
  await page.getByTitle(/Chart settings/).click()
}

async function goToDate(page: Page, iso: string) {
  await page.getByTitle('Go to date').click()
  const input = page.locator('input[type="date"]')
  await input.fill(iso)
  await input.press('Enter')
}

test('the layer is offered with its count and starts switched OFF', async ({ page }) => {
  // Proven by MUTATION: defaulting the group ON (dropping it from `isAnalysisGroup`'s reach in
  // `groupDefault`) turns the second assertion red.
  await openPriceTab(page)
  expect(await navyPixels(page)).toBe(0)

  await toggleAnalysis(page)
  const row = page.getByRole('button', { name: new RegExp(LAYER) })
  await expect(row).toBeVisible()
  // The count is what makes a layer legible before you switch it on — 820 marks and 4 read very
  // differently. It is the anchor set's answer, so it must be a real number, never blank.
  await expect(row).toContainText(/\d/)
})

test('ticking it repaints candles, and unticking it puts them back', async ({ page }) => {
  await openPriceTab(page)
  // ⚠ Go somewhere a mark EXISTS before measuring. This check used to read the opening viewport,
  // which worked only while blocked setups were anchors and the run carried 424 marks; an empty
  // viewport is pixel-identical to a layer that never draws.
  await goToDate(page, DATE_WITH_A_MARK)
  const off = await navyPixels(page)
  expect(off).toBe(0)

  await toggleAnalysis(page)
  await page.getByRole('button', { name: new RegExp(LAYER) }).click()
  await toggleAnalysis(page) // close the menu so it cannot be counted as chart pixels
  await expect.poll(() => navyPixels(page), { timeout: 20_000 }).toBeGreaterThan(0)

  // And back — a layer that cannot be switched off is not a toggle. This also rules out the navy
  // having come from anywhere but this layer.
  await toggleAnalysis(page)
  await page.getByRole('button', { name: new RegExp(LAYER) }).click()
  await toggleAnalysis(page)
  await expect.poll(() => navyPixels(page), { timeout: 20_000 }).toBe(0)
})

test('the layer is withdrawn off the timeframe it was computed on', async ({ page }) => {
  // Proven by MUTATION: dropping the `atBaseTf` clause from `analysisGroups` leaves the row listed
  // at H1, and dropping the matching `continue` in the render loop leaves it PAINTING M15 bars over
  // H1 candles — which is the more dangerous half, because it states something nobody measured.
  await openPriceTab(page)
  await goToDate(page, DATE_WITH_A_MARK) // see the note in the check above
  await toggleAnalysis(page)
  await page.getByRole('button', { name: new RegExp(LAYER) }).click()
  await toggleAnalysis(page)
  await expect.poll(() => navyPixels(page), { timeout: 20_000 }).toBeGreaterThan(0)

  // Resample up. M15 → H1 is display-only, so the bars on screen are no longer the ones the
  // patterns were detected on.
  await page.getByRole('button', { name: /^M15$/ }).click()
  await page.getByText('H1', { exact: true }).click()

  await expect.poll(() => navyPixels(page), { timeout: 20_000 }).toBe(0)
  await toggleAnalysis(page)
  await expect(page.getByRole('button', { name: new RegExp(LAYER) })).toHaveCount(0)
})

test('the pattern name is off by default and comes on from Chart settings', async ({ page }) => {
  // Proven by MUTATION: defaulting `candleMarkLabels` to true, or dropping the setting from the
  // tag expression in the `candle` render branch, each turn one half of this red.
  //
  // ⚠ It counts the EDGE colour, not the navy body — the body is drawn either way, so a check on
  // `navyPixels` would be satisfied by a mark with no tag and would prove nothing about the toggle.
  await openPriceTab(page)
  await toggleAnalysis(page)
  await page.getByRole('button', { name: new RegExp(LAYER) }).click()
  await toggleAnalysis(page)
  // The newest bars often carry none — go where one is.
  await goToDate(page, DATE_WITH_A_MARK)
  await expect.poll(() => navyPixels(page), { timeout: 30_000 }).toBeGreaterThan(0)

  const off = await edgePixels(page)

  await toggleSettings(page)
  const nameIt = page.getByText('Name the pattern').locator('xpath=../..').getByRole('switch')
  await expect(nameIt).toHaveAttribute('aria-checked', 'false')
  await nameIt.click()
  await toggleSettings(page)
  // The tag is many pixels of text beside a mark that was already drawn, so this is a large jump,
  // not a marginal one — measured 52 → 423 on this date.
  await expect.poll(() => edgePixels(page), { timeout: 20_000 }).toBeGreaterThan(off * 2)

  // And back — a preference that cannot be switched off is not a preference.
  await toggleSettings(page)
  await nameIt.click()
  await toggleSettings(page)
  await expect.poll(() => edgePixels(page), { timeout: 20_000 }).toBe(off)
})

test('the setting explains itself from the ⓘ, not from a paragraph under its label', async ({
  page,
}) => {
  // Proven by MUTATION: rendering `def.help` inline again turns the first assertion red, and
  // dropping the `<InfoTip>` turns the second red.
  //
  // ⚠ Both halves are needed. Checking only that the paragraph is gone would pass against a panel
  // that simply DELETED the explanation, which is the same tidy-up with the answer thrown away.
  await openPriceTab(page)
  await toggleSettings(page)
  await expect(page.getByText('Name the pattern')).toBeVisible()

  // Not on screen while nobody has asked for it.
  await expect(page.getByText(HELP)).toHaveCount(0)

  // ...and one hover away. `InfoTip` portals to <body>, so this also rules out the panel's own
  // scroll box cropping it — the reason the shared control is used here rather than a local span.
  await page
    .getByText('Name the pattern')
    .locator('xpath=../..')
    .locator('span.cursor-help')
    .hover()
  await expect(page.getByText(HELP)).toBeVisible()
})

test('the Missed layer filters by SCORE as well as by reason', async ({ page }) => {
  // Aaron, 2026-08-08: *"sometimes I just want to see 2/3 vs 3/3 because they are legit
  // different"*. A 3/3 had every confluence and still did not trade; a 2/3 never got there.
  //
  // ⚠ It reads the layer's own COUNT rather than pixels, deliberately — the miss markers are DOM-
  // free canvas draws like everything else here, but the count is what the filter is for and a
  // pixel check could not tell 35 markers from 179. Proven by MUTATION: dropping the score clause
  // from `missVisible` leaves the count unmoved and turns this red.
  await openPriceTab(page)
  await toggleAnalysis(page)
  const missed = page.getByRole('button', { name: /^Missed/ })
  await missed.click() // switch the layer on to reveal its filters

  // ⚠ Every score starts SHOWN, and this assertion is why the check is not vacuous. The layer's
  // opening view is the emitter's `missNoise` recommendation; a score defaulting to hidden would be
  // a SECOND answer to "what do I see first", and a reader would have no way to tell which of the
  // two had hidden a marker. Without this, a mutation defaulting `2/3` hidden passes.
  for (const s of ['3 of 3', '2 of 3']) {
    await expect(page.getByRole('button', { name: new RegExp(`^${s}`) })).toHaveAttribute(
      'aria-pressed',
      'true'
    )
  }

  const count = async () => Number((await missed.textContent())!.replace(/\D/g, ''))
  const all = await count()
  expect(all).toBeGreaterThan(0)

  // Hiding one score must leave strictly fewer, and hiding both must leave none — the second half
  // is what proves the filter is doing the work rather than the layer being off.
  await page.getByRole('button', { name: /^2 of 3/ }).click()
  const threeOnly = await count()
  expect(threeOnly).toBeGreaterThan(0)
  expect(threeOnly).toBeLessThan(all)

  await page.getByRole('button', { name: /^3 of 3/ }).click()
  await expect.poll(count).toBe(0)

  // ...and back, because a filter that cannot be undone is a narrowing, not a filter.
  await page.getByRole('button', { name: /^3 of 3/ }).click()
  await page.getByRole('button', { name: /^2 of 3/ }).click()
  expect(await count()).toBe(all)
})

test("the Missed layer's two filters cross — each side counts what the other is showing", async ({
  page,
}) => {
  // Aaron, 2026-08-08, reading it off the screen: *"if I have on missed 3/3 or 2/3 shouldn't the
  // knobs that influence that toggle accordingly also?"* With "3 of 3" alone the layer drew 35
  // markers while the MISSING chips went on reading 179 / 238 / 21 / 10 / 4 — which sum to 452, the
  // whole set. **A chip's number is a claim about what ticking it would change**, so conditioned on
  // nothing it is a claim about markers that are not on the chart.
  //
  // ⚠ WATCHED RED against HEAD, where the reason counts do not move at all when a score is hidden.
  await openPriceTab(page)
  await toggleAnalysis(page)
  await page.getByRole('button', { name: /^Missed/ }).click()

  /** A chip's trailing count — `No FVG in zone 179` → 179. */
  const chip = async (name: string) => {
    const t = await page.getByRole('button', { name: new RegExp(`^${name}`) }).textContent()
    return Number(t!.trim().match(/(\d+)$/)![1])
  }

  const bothScores = await chip('No FVG in zone')
  expect(bothScores).toBeGreaterThan(0)

  // Hide the 2/3s. "No FVG in zone" cannot be a 3/3's missing confluence — a 3/3 met all three —
  // so its count must fall to exactly 0. That is a stronger assertion than "it went down", and it
  // is the answer the reader wants: this reason does not occur at this score.
  await page.getByRole('button', { name: /^2 of 3/ }).click()
  await expect.poll(() => chip('No FVG in zone')).toBe(0)

  // ⚠ The chip must still BE there at 0. Shrinking the roster to the values present in the filtered
  // subset would delete the control the instant its count hit zero, and a control that disappears
  // when it reaches zero is one the reader cannot use to get back.
  await expect(page.getByRole('button', { name: /^No FVG in zone/ })).toBeVisible()

  // …and the mirror: the SCORE counts follow the reason filter. `No retrace` starts hidden (it is
  // in the emitter's `missNoise`), so ticking it back on can only ever ADD misses to a score.
  await page.getByRole('button', { name: /^2 of 3/ }).click() // both scores shown again
  const before = await chip('2 of 3')
  await page.getByRole('button', { name: /^No retrace/ }).click()
  await expect.poll(() => chip('2 of 3')).toBeGreaterThan(before)
})

test('the direction filter removes marks and every direction starts shown', async ({ page }) => {
  // Aaron, 2026-08-08: *"other times it's showing candle patterns that [point] nothing in the
  // direction of the trade — if I take a long, it's showing my bearish engulfing."*
  //
  // ⚠ Every direction starts ON. The opposing tier is half the point of the layer — *"if not, it
  // will show me why I was wrong"* — so hiding it must be something the reader asks for, never a
  // default that quietly answers "there was nothing at the turn". Proven by MUTATION: defaulting
  // `against` hidden turns the first assertion red, and dropping the `hiddenCandleDirs` guard from
  // the draw turns the second red.
  await openPriceTab(page)
  await toggleAnalysis(page)
  await page.getByRole('button', { name: new RegExp(LAYER) }).click()
  for (const d of ['With the setup', 'Neutral', 'Against it']) {
    await expect(page.getByRole('button', { name: new RegExp(`^${d}`) })).toHaveAttribute(
      'aria-pressed',
      'true'
    )
  }
  await toggleAnalysis(page)
  await goToDate(page, DATE_WITH_A_MARK)
  await expect.poll(() => navyPixels(page), { timeout: 30_000 }).toBeGreaterThan(0)
  const all = await navyPixels(page)

  // Hide every direction and the layer draws nothing — which is what proves the filter does the
  // work rather than the marks having been somewhere else.
  await toggleAnalysis(page)
  for (const d of ['With the setup', 'Neutral', 'Against it']) {
    await page.getByRole('button', { name: new RegExp(`^${d}`) }).click()
  }
  await toggleAnalysis(page)
  await expect.poll(() => navyPixels(page), { timeout: 20_000 }).toBe(0)

  // ...and back, because a filter that cannot be undone is a narrowing.
  await toggleAnalysis(page)
  for (const d of ['With the setup', 'Neutral', 'Against it']) {
    await page.getByRole('button', { name: new RegExp(`^${d}`) }).click()
  }
  await toggleAnalysis(page)
  await expect.poll(() => navyPixels(page), { timeout: 20_000 }).toBe(all)
})

test('"Only the deepest" thins the marks without emptying the layer', async ({ page }) => {
  // Aaron, 2026-08-08: *"a setting where I could take off all the reversal candles and only have the
  // deepest one show within that trading zone."* The two readings answer different questions — which
  // level offered the best entry, versus which levels offered one at all.
  //
  // ⚠ Both bounds matter. `< all` alone would pass against a setting that drew nothing, and `> 0`
  // alone against one that changed nothing — and "draws nothing" is exactly what a wrong `deepest`
  // flag produces. Proven by MUTATION: emitting `deepest: False` for every mark turns it red.
  await openPriceTab(page)
  await toggleAnalysis(page)
  await page.getByRole('button', { name: new RegExp(LAYER) }).click()
  await toggleAnalysis(page)
  await goToDate(page, DATE_WITH_A_MARK)
  await expect.poll(() => navyPixels(page), { timeout: 30_000 }).toBeGreaterThan(0)
  const all = await navyPixels(page)

  await toggleSettings(page)
  const only = page.getByText('Only the deepest').locator('xpath=../..').getByRole('switch')
  await expect(only).toHaveAttribute('aria-checked', 'false') // the full reading is the default
  await only.click()
  await toggleSettings(page)
  await expect.poll(() => navyPixels(page), { timeout: 20_000 }).toBeLessThan(all)
  expect(await navyPixels(page)).toBeGreaterThan(0)

  await toggleSettings(page)
  await only.click()
  await toggleSettings(page)
  await expect.poll(() => navyPixels(page), { timeout: 20_000 }).toBe(all)
})
