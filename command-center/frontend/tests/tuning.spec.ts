/**
 * The Tuning workbench's regression suite.
 *
 * Every check here is a defect that shipped, and they share a shape: this page exists ONLY to
 * compare a child run against its parent, so a defect that makes the two incomparable — or hides
 * a child, or ranks them wrongly — is invisible on any other page in the app. That is why none of
 * these was ever caught by using the lab.
 *
 * ⚠ The leaderboard states that cannot be produced on demand are MOCKED by mutating the REAL runs
 * list and the REAL run detail, never by hand-writing a fixture — a hand-written one drifts from
 * the backend's model and then tests a shape the server never sends. The mocked children are a
 * grandchild (which the page used to drop), a sweep child (which it used to show as a tweak) and a
 * 3-trade fluke at PF 99 (which it used to star).
 *
 * Needs the backend on :8000 and the dev server on :5173 (`./start.sh`), and it needs run
 * BASELINE_ID to still be in the lab — the test says so rather than silently passing on an empty
 * table.
 */
import { test, expect, type Page } from '@playwright/test'
import type { BacktestDetail, BacktestSummary } from '../src/types'

const API = 'http://localhost:8000'
const BASELINE_ID = '211384ddbea4'

/** A synthetic child of the baseline. `pf`/`trades` are what each assertion turns on. */
interface Child {
  id: string
  parent: string
  pf: number
  trades: number
  edits: Record<string, unknown>
  sweep?: string
}

const CHILDREN: Child[] = [
  // The real winner: best PF among the runs with a defensible sample.
  { id: 'aaa111aaa111', parent: BASELINE_ID, pf: 4.9, trades: 120, edits: { exec_tp1_pct: 40 } },
  { id: 'bbb222bbb222', parent: BASELINE_ID, pf: 2.0, trades: 90, edits: { exec_tp2_pct: 25 } },
  // A GRANDCHILD — tuning an iteration. The page listed direct children only and dropped it.
  {
    id: 'ccc333ccc333',
    parent: 'aaa111aaa111',
    pf: 3.0,
    trades: 80,
    edits: { exec_tp1_pct: 40, exec_risk_pct: 5 },
  },
  // Highest PF on the page and three trades behind it. It may rank first; it may not be starred.
  { id: 'fff444fff444', parent: BASELINE_ID, pf: 99.0, trades: 3, edits: { exec_tp1_pct: 90 } },
  // A SWEEP child. `source_run_id` is stamped by sweeps and optimizations too, so this used to
  // appear in the leaderboard as a tweak.
  { id: 'swp555swp555', parent: BASELINE_ID, pf: 50.0, trades: 200, edits: {}, sweep: 'sw_1' },
]

async function getJson<T>(path: string): Promise<T> {
  const res = await fetch(API + path)
  if (!res.ok) throw new Error(`backend not answering for ${path} (${res.status}) — is it running?`)
  return res.json() as Promise<T>
}

/** Records every run-detail URL the page asked for, so the payload trim can be asserted. */
type Fixture = { detailUrls: string[] }

async function mockLeaderboard(page: Page): Promise<Fixture> {
  const runs = await getJson<BacktestSummary[]>('/backtests/runs')
  const base = runs.find((r) => r.run_id === BASELINE_ID)
  if (!base)
    throw new Error(`run ${BASELINE_ID} is not in the lab any more — pick another baseline`)
  const baseDetail = await getJson<BacktestDetail>(`/backtests/runs/${BASELINE_ID}`)
  expect(
    baseDetail.regime_timeline.length,
    'the baseline must carry a timeline for the slim path'
  ).toBeGreaterThan(0)

  const summaries: BacktestSummary[] = CHILDREN.map((c, i) => ({
    ...base,
    run_id: c.id,
    source_run_id: c.parent,
    sweep_id: c.sweep ?? null,
    profit_factor: c.pf,
    trade_count: c.trades,
    // Distinct enough to tell the drawdown column's percent from its dollars.
    max_drawdown_pct: 40 + i,
    created_at: `2026-08-0${i + 1}T00:00:00Z`,
    params: { ...base.params, ...c.edits },
  }))

  await page.route(
    (u) => u.pathname.endsWith('/api/backtests/runs'),
    (route) =>
      route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify([...runs, ...summaries]),
      })
  )

  const fixture: Fixture = { detailUrls: [] }
  await page.route(
    (u) => /\/api\/backtests\/runs\/[0-9a-z]+$/.test(u.pathname),
    async (route) => {
      const url = new URL(route.request().url())
      fixture.detailUrls.push(url.pathname.split('/').pop()! + url.search)
      const id = url.pathname.split('/').pop()!
      const child = CHILDREN.find((c) => c.id === id)
      if (!child) return route.continue()
      const body: BacktestDetail = {
        ...baseDetail,
        run_id: id,
        source_run_id: child.parent,
        profit_factor: child.pf,
        trade_count: child.trades,
        params: { ...baseDetail.params, ...child.edits },
        // The endpoint's own contract — the page asks for this and must survive getting it.
        regime_timeline:
          url.searchParams.get('timeline') === 'false' ? [] : baseDetail.regime_timeline,
      }
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify(body),
      })
    }
  )
  return fixture
}

/** The leaderboard's Run cell, top to bottom. Scoped to the FIRST table: the per-regime table
 *  further down the page is also a `tbody` of rows whose 2nd cell is a number. */
const runCells = (page: Page) => page.locator('table').first().locator('tbody tr td:nth-child(2)')

test.describe('Tuning workbench — the leaderboard', () => {
  test('a grandchild is listed and a sweep child is not', async ({ page }) => {
    await mockLeaderboard(page)
    await page.goto(`/backtests/runs/${BASELINE_ID}/tune`)
    await expect(page.getByText('Iterations (5)')).toBeVisible()

    const labels = await runCells(page).allInnerTexts()
    // Baseline + 4 tweaks. The grandchild is there because descendants are walked transitively.
    expect(labels.some((t) => t.includes('Tweak ccc333'))).toBe(true)
    // The sweep child is excluded by its own sweep_id, not by hoping nothing else stamps
    // source_run_id.
    expect(labels.some((t) => t.includes('Tweak swp555'))).toBe(false)
  })

  test('the table is ordered by profit factor, because that is what its caption says', async ({
    page,
  }) => {
    await mockLeaderboard(page)
    await page.goto(`/backtests/runs/${BASELINE_ID}/tune`)
    await expect(page.getByText('Iterations (5)')).toBeVisible()

    const order = (await runCells(page).allInnerTexts()).map((t) => t.split('\n')[0].trim())
    // 99.0, 4.9, 3.781 (the real baseline), 3.0, 2.0
    expect(order).toEqual([
      'Tweak fff444',
      'Tweak aaa111',
      'Baseline',
      'Tweak ccc333',
      'Tweak bbb222',
    ])
  })

  test('the ★ goes to the best profit factor with a real sample, not to a 3-trade fluke', async ({
    page,
  }) => {
    await mockLeaderboard(page)
    await page.goto(`/backtests/runs/${BASELINE_ID}/tune`)
    await expect(page.getByText('Iterations (5)')).toBeVisible()

    // The fluke ranks FIRST and is still not the winner — the two facts have to hold together, or
    // the sort and the floor are testing each other rather than the page.
    const starred = await page
      .locator('table tbody tr')
      .filter({ has: page.locator('svg.lucide-star') })
      .locator('td:nth-child(2)')
      .innerText()
    expect(starred).toContain('Tweak aaa111')
    // And the floor is on screen, because a threshold nobody can see reads as a bug.
    await expect(page.getByText(/best over 10 trades/)).toBeVisible()
  })

  test('Max DD leads with the peak-relative percent and keeps the dollars beneath it', async ({
    page,
  }) => {
    await mockLeaderboard(page)
    await page.goto(`/backtests/runs/${BASELINE_ID}/tune`)
    await expect(page.getByText('Iterations (5)')).toBeVisible()

    // The baseline's own stored figure — 55.92% off a $1,725,524 fall. In dollars alone that reads
    // as ~12% of the profit beside it, which is the misreading this column was fixed for.
    const row = page.locator('table tbody tr').filter({ hasText: 'Baseline' }).first()
    const dd = await row.locator('td:nth-child(4)').innerText()
    expect(dd).toContain('55.9%')
    expect(dd).toContain('$1,725,524')
  })

  test('a run is named by what it CHANGED wherever it is named alone', async ({ page }) => {
    await mockLeaderboard(page)
    await page.goto(`/backtests/runs/${BASELINE_ID}/tune`)
    await expect(page.getByText('Iterations (5)')).toBeVisible()
    // The chart legend and the regime table — `Tweak aaa111` there tells the reader nothing about
    // which line is which.
    await expect(page.getByText('exec_tp1_pct=40', { exact: false }).first()).toBeVisible()
  })

  test('the regime bands get a key, and the iterations skip the 96 KB calendar', async ({
    page,
  }) => {
    const fx = await mockLeaderboard(page)
    await page.goto(`/backtests/runs/${BASELINE_ID}/tune`)
    await expect(page.getByText('Iterations (5)')).toBeVisible()
    await expect(page.locator('text=Equity overlay')).toBeVisible()
    // Wait for the overlay to have drawn something before reading what was fetched.
    await expect(page.locator('.recharts-wrapper').first()).toBeVisible()

    // The baseline is fetched WHOLE (the chart bands off its calendar); every iteration is slimmed.
    const forBase = fx.detailUrls.filter((u) => u.startsWith(BASELINE_ID))
    expect(forBase.length).toBeGreaterThan(0)
    expect(forBase.every((u) => !u.includes('timeline=false'))).toBe(true)
    for (const c of CHILDREN.filter((c) => !c.sweep)) {
      const asked = fx.detailUrls.filter((u) => u.startsWith(c.id))
      expect(asked.length, `${c.id} was never fetched`).toBeGreaterThan(0)
      expect(
        asked.every((u) => u.includes('timeline=false')),
        `${c.id} was fetched whole`
      ).toBe(true)
    }
  })
})

test.describe('Tuning workbench — what the run will be measured on', () => {
  test('the panel states the costs and sizing the iteration inherits', async ({ page }) => {
    await mockLeaderboard(page)
    await page.goto(`/backtests/runs/${BASELINE_ID}/tune`)
    await expect(page.getByText('Iterations (5)')).toBeVisible()
    // This run charged nothing, and the page has to SAY so — the defect was that it said nothing
    // at all while quietly sending nothing either.
    await expect(page.getByText(/Same window and costs as the baseline/)).toBeVisible()
    await expect(page.getByText(/no costs charged/)).toBeVisible()
    await expect(page.getByText(/sizing\s*consistent/)).toBeVisible()
  })

  test('an edit survives leaving the page and coming back', async ({ page }) => {
    await mockLeaderboard(page)
    await page.goto(`/backtests/runs/${BASELINE_ID}/tune`)
    await expect(page.getByText('Iterations (5)')).toBeVisible()

    // Clicking a leaderboard row to inspect it is the ordinary way to leave, and it used to throw
    // the form away.
    const field = page.locator('input[type="number"]').first()
    await field.fill('7')
    await field.blur()
    await expect(page.getByRole('button', { name: /Run with 1 change/ })).toBeVisible()

    await page.goto(`/backtests/runs/${BASELINE_ID}`)
    await page.goBack()
    await expect(page.getByRole('button', { name: /Run with 1 change/ })).toBeVisible()
  })
})
