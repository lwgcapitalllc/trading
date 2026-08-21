/**
 * Chart settings → Trades → **Annotate trades** — the trade's words, on or off.
 *
 * Aaron's ask (2026-08-20): reading a run with several trades on screen, the `Entry` / `SL` / `TP1`
 * / `Furthest` / `Deepest` chips are most of what is drawn, and the bands already say which way it
 * went — *"I will just be able to eye it off of the colour."* So the annotations became a setting,
 * and the one thing that survives it is whatever NAMES the trade (a stack's strategy, a `SEC` /
 * `REC` book tag, an add lot), because that is the fact the colours cannot carry.
 *
 * ⚠ **A fail-watch against HEAD is VACUOUS for every check here** — the setting did not exist, so a
 * red would only prove the row is absent, which is the locator and nothing else. **Non-vacuity is
 * by MUTATION, named in a comment on each check**, except the second, which is non-vacuous BY
 * CONSTRUCTION: it measures the SAME pixels three times, so it can only pass on a real change that
 * really reverses.
 *
 * ⚠ **The drawing is measured in PIXELS, not in the DOM.** A trade annotation is painted into
 * klinecharts' canvas and has no element of its own — a check that settled for "the toggle reads
 * Off" would be asserting the toggle.
 *
 * ⚠ It drives the REAL backend: the trades come from the run's own spec, and a mocked one would be
 * testing the mock. Needs the backend on :8000 and the dev server on :5173 (`./start.sh`).
 */
import { test, expect, type Page } from '@playwright/test'
import type { BacktestDetail, BacktestSummary } from '../src/types'

const API = 'http://localhost:8000'

async function getJson<T>(path: string): Promise<T> {
  const res = await fetch(API + path)
  if (!res.ok) throw new Error(`backend not answering for ${path} (${res.status}) — is it running?`)
  return res.json() as Promise<T>
}

/**
 * Does this run have a built ChartSpec? Without one the Price tab renders "No price data" and every
 * locator below times out for a reason that has nothing to do with annotations.
 *
 * ⚠ ABORTED AFTER THE HEADERS — the spec is tens of MB and this only asks for the status.
 */
async function hasChartSpec(runId: string): Promise<boolean> {
  const ctl = new AbortController()
  try {
    const res = await fetch(`${API}/backtests/runs/${runId}/chart-spec`, { signal: ctl.signal })
    return res.ok
  } catch {
    return false
  } finally {
    ctl.abort()
  }
}

/**
 * Any completed python run carrying trades and a spec.
 *
 * ⚠ It RESOLVES the run rather than naming one. A spec pinned to a literal run id is a spec with an
 * expiry date, and this folder has been bitten by that three times — see `../../CLAUDE.md` → *A
 * FIXTURE PINNED TO A DATABASE ROW*. What this check needs is a SHAPE (a trade to draw), not a
 * particular book, so nothing here has to name one.
 */
async function resolveRun(): Promise<string> {
  const runs = await getJson<BacktestSummary[]>('/backtests/runs')
  for (const r of runs) {
    if (r.status !== 'complete' || (r.trade_count ?? 0) < 1) continue
    const d = await getJson<BacktestDetail>(`/backtests/runs/${r.run_id}?timeline=false`)
    if (d.runner !== 'python') continue
    if (!(await hasChartSpec(r.run_id))) continue
    return r.run_id
  }
  throw new Error('no completed python run with trades and a chart spec — this suite needs one')
}

let RUN = ''

test.beforeAll(async () => {
  RUN = await resolveRun()
})

/**
 * Open the Price tab and PARK ON A TRADE.
 *
 * 🔴 The step is not a nicety, and the first version of this file proved it: the chart opens on the
 * newest bars, which need not carry a trade, and **an empty viewport is pixel-identical to a
 * setting that removed everything** — the diff check passed at 0 with nothing on screen to annotate.
 *
 * ⚠ **PREVIOUS, not next.** The chart opens at the right edge, so every marker in the run is BEHIND
 * the viewport centre and `Next marker` has nothing to step to — it is enabled (nothing is selected
 * yet) and does nothing, which is exactly what made the vacuous pass look like a working fixture.
 *
 * ⚠ The pill is asserted to be PARKED afterwards. That is the guard: it reads `Step` with a bare
 * total while nothing is selected, and its verdict plus `n/total` once it lands on one.
 */
async function openOnATrade(page: Page) {
  await page.goto(`/backtests/runs/${RUN}`)
  await page.getByRole('button', { name: /price/i }).click()
  await expect(page.getByTitle('Go to date')).toBeVisible({ timeout: 60_000 })
  await page.getByRole('button', { name: 'Previous marker' }).click()
  await expect(page.locator('div[title*="steps"]').first()).not.toContainText('Step', {
    timeout: 30_000,
  })
  // The jump re-applies data and scrolls a frame later; give the canvas time to settle before the
  // first snapshot, or the "restored exactly" check compares two different viewports.
  await expect.poll(() => ink(page), { timeout: 30_000 }).toBeGreaterThan(0)
  await page.waitForTimeout(1_500)
}

/** Everything painted, across every canvas — the denominator the annotation diff is judged against. */
function ink(page: Page) {
  return page.evaluate(() => {
    let n = 0
    for (const c of Array.from(document.querySelectorAll('canvas'))) {
      const g = c.getContext('2d')
      if (!g || !c.width || !c.height) continue
      const d = g.getImageData(0, 0, c.width, c.height).data
      for (let i = 3; i < d.length; i += 4) if (d[i] > 0) n++
    }
    return n
  })
}

/**
 * Park a copy of every canvas on `window`, so the next call can diff against it IN THE PAGE.
 *
 * ⚠ The pixels never cross into Node. A full-panel frame is millions of bytes and serialising two
 * of them per assertion is the difference between a check and a timeout.
 */
function snapshot(page: Page) {
  return page.evaluate(() => {
    const w = window as unknown as { __snap?: { w: number; h: number; d: number[] }[] }
    w.__snap = Array.from(document.querySelectorAll('canvas'))
      .map((c) => {
        const g = c.getContext('2d')
        if (!g || !c.width || !c.height) return null
        return {
          w: c.width,
          h: c.height,
          d: Array.from(g.getImageData(0, 0, c.width, c.height).data),
        }
      })
      .filter(Boolean) as { w: number; h: number; d: number[] }[]
  })
}

/** How many pixels differ from the parked snapshot. `-1` if the canvases changed shape under us. */
function diffFromSnapshot(page: Page) {
  return page.evaluate(() => {
    const w = window as unknown as { __snap?: { w: number; h: number; d: number[] }[] }
    const prev = w.__snap ?? []
    const now = Array.from(document.querySelectorAll('canvas')).filter((c) => {
      const g = c.getContext('2d')
      return g && c.width && c.height
    })
    if (now.length !== prev.length) return -1
    let n = 0
    for (let k = 0; k < now.length; k++) {
      const c = now[k]
      if (c.width !== prev[k].w || c.height !== prev[k].h) return -1
      const d = c.getContext('2d')!.getImageData(0, 0, c.width, c.height).data
      for (let i = 0; i < d.length; i += 4) {
        if (
          d[i] !== prev[k].d[i] ||
          d[i + 1] !== prev[k].d[i + 1] ||
          d[i + 2] !== prev[k].d[i + 2] ||
          d[i + 3] !== prev[k].d[i + 3]
        )
          n++
      }
    }
    return n
  })
}

/** ⚠ The gear is a TOGGLE, not an open button — a second click closes the panel. */
async function toggleSettings(page: Page) {
  await page.getByTitle(/Chart settings/).click()
}

/** ⚠ Scoped to the row's own seam, not to its words. A settings row is a label, an ⓘ and a control
 *  in three sibling elements, so a text-built locator lands on the label's wrapper and never sees
 *  the switch beside it — the check then fails as *element not found*, which reads as a missing
 *  setting rather than as a bad locator. */
const row = (page: Page, key: string) => page.locator(`[data-setting="${key}"]`)

test.describe('Trade annotations switch off from Chart settings', () => {
  test('the setting is offered under Trades, defaults ON, and explains itself from the ⓘ', async ({
    page,
  }) => {
    // ✅ WATCHED RED BY MUTATION: defaulting `tradeLabels` to false in `DEFAULT_CHART_SETTINGS`
    // reddens this on the aria-checked assertion (and the third check with it, which reads the
    // sub-row's enabled state from the same default). Dropping the row from `SECTIONS` reddens the
    // whole check.
    await openOnATrade(page)
    await toggleSettings(page)

    const labels = row(page, 'tradeLabels')
    await expect(labels).toBeVisible()
    await expect(labels.getByRole('switch')).toHaveAttribute('aria-checked', 'true')

    // The explanation is BEHIND the ⓘ, never printed under the label — and BOTH halves are
    // asserted, because checking only that the paragraph is gone would pass against a panel that
    // deleted the answer. Same rule the candlestick-reversal setting's check follows.
    await expect(labels).not.toContainText(/no Entry \/ SL \/ TP chips/)
    await labels.locator('svg').first().hover()
    await expect(page.getByText(/no Entry \/ SL \/ TP chips/)).toBeVisible()
  })

  test('switching it off changes what is drawn, and switching it back restores it exactly', async ({
    page,
  }) => {
    // NON-VACUOUS BY CONSTRUCTION: the same pixels are measured three times, so this can only pass
    // on a change that really happens and really reverses.
    // ✅ AND WATCHED RED BY MUTATION: pinning `withLabels = true` in the overlay — the drawing
    // ignoring the setting — leaves `off` at 0, and the other two checks stay green, because they
    // read the panel rather than the canvas.
    await openOnATrade(page)
    const painted = await ink(page)
    expect(painted).toBeGreaterThan(0)

    await snapshot(page)
    await toggleSettings(page)
    await row(page, 'tradeLabels').getByRole('switch').click()
    await toggleSettings(page)
    await page.waitForTimeout(500)

    const off = await diffFromSnapshot(page)
    expect(off).toBeGreaterThan(0)
    // The annotations are a MINORITY of the trade's drawing — the bands, the level lines and their
    // dots are all still there. A diff approaching the whole frame would mean the setting took the
    // chart out rather than its words.
    expect(off).toBeLessThan(painted * 0.5)

    await toggleSettings(page)
    await row(page, 'tradeLabels').getByRole('switch').click()
    await toggleSettings(page)
    await page.waitForTimeout(500)

    // ⚠ NOT byte-identical, and the residue was MEASURED rather than tolerated: 127 pixels, all in
    // the single column x=509 spanning the plot's full height — the Step navigator's dashed focus
    // line. Rebuilding the trade overlays re-creates them ON TOP of it, so where the two cross, the
    // line is now painted under the box. Pre-existing paint order, unrelated to this setting, and
    // 1% of the 11,959 pixels the annotations themselves move.
    const restored = await diffFromSnapshot(page)
    expect(restored).toBeLessThan(off * 0.05)
  })

  test('the price sub-setting goes inert while annotations are off, and keeps its value', async ({
    page,
  }) => {
    // ✅ WATCHED RED BY MUTATION: removing `dependsOn: 'tradeLabels'` from the registry row reddens
    // this one alone. The `disabled` prop on the panel's Toggle is the other half of the same rule
    // and reddens it the same way.
    await openOnATrade(page)
    await toggleSettings(page)

    const prices = row(page, 'tradeLabelPrices').getByRole('switch')
    await expect(prices).toBeEnabled()

    await row(page, 'tradeLabels').getByRole('switch').click()
    // A control that changes nothing on the chart is shown greyed and refuses the click, rather
    // than moving a switch with no effect.
    await expect(prices).toBeDisabled()
    // …and it KEEPS its answer: switching annotations back on must restore the reader's own
    // preference, not reset it.
    await expect(prices).toHaveAttribute('aria-checked', 'true')

    await row(page, 'tradeLabels').getByRole('switch').click()
    await expect(prices).toBeEnabled()
    await expect(prices).toHaveAttribute('aria-checked', 'true')
  })
})
