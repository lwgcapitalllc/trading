/**
 * The Strategies page's regression suite.
 *
 * Every check here is a defect that shipped on 2026-08-06, and they share ONE shape: with a VPS
 * agent unreachable the page rendered confident, healthy-looking answers. "No files deployed" over
 * a box nobody could ask. A strategy that needed deploying offering a Run button. A green "In sync"
 * pill over a deployment whose file had been deleted. None of them showed an error, which is why
 * none was ever caught by using the page — the only visible symptom was a stream of error toasts,
 * and toasts are what people learn to dismiss.
 *
 * ⚠ EVERY STATE HERE IS MOCKED BY MUTATING THE REAL RESPONSE, never by hand-writing a fixture — a
 * hand-written one drifts from the backend's model and then pins a shape the server never sends.
 * That matters more than usual here: the two endpoints under test just CHANGED shape (bare list →
 * envelope), and a fixture written to the new shape would pass against a backend still serving the
 * old one.
 *
 * Needs the backend on :8000 and the dev server on :5173 (`./start.sh`). It does NOT need the VPS:
 * every VPS-dependent response is intercepted, which is the whole point — these are the states the
 * live box cannot be asked to produce on demand.
 */
import { test, expect, type Page } from '@playwright/test'
import type { StrategyFilesResponse, StrategyFileSyncResponse } from '../src/types'

const API = 'http://localhost:8000'

/** Fetch a real response so every mock starts from the server's actual shape. */
async function real<T>(page: Page, path: string): Promise<T> {
  const res = await page.request.get(`${API}${path}`)
  expect(res.ok(), `${path} must answer — start the backend first`).toBeTruthy()
  return (await res.json()) as T
}

/** The NT8 strategy's row, found by its PLATFORM badge rather than its name.
 *
 * ⚠ The Name column renders `name || class_name` — the DISPLAY name — so `ORB`
 * matches nothing and `Opening Range Breakout` is a label somebody may rename.
 * The platform badge is what makes this row the one under test. */
function nt8Row(page: Page) {
  return page
    .locator('tbody tr')
    .filter({ has: page.getByRole('img', { name: 'NinjaTrader 8' }) })
    .first()
}

/** Serve a mutated copy of one endpoint. */
async function mock(page: Page, path: string, body: unknown) {
  await page.route(`**/api${path}`, (r) =>
    r.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify(body) })
  )
}

/** Make one endpoint fail the way an unreachable agent really fails. */
async function fail(page: Page, path: string, detail: string) {
  await page.route(`**/api${path}`, (r) =>
    r.fulfill({ status: 502, contentType: 'application/json', body: JSON.stringify({ detail }) })
  )
}

const AGENT_DOWN =
  'Could not reach VPS agent: VPS agent /files/strategies: Remote end closed connection without response'

// ── The Deployed tab must not report an unreachable box as an empty one ───────

test('a dead agent does not render as "No files deployed"', async ({ page }) => {
  await fail(page, '/strategy-files', AGENT_DOWN)
  await page.goto('/strategies?tab=deployed')

  await expect(page.getByText(/Can’t read the VPS strategy folder/i)).toBeVisible()
  // The old page said this, which is a claim about a VPS it never reached.
  await expect(page.getByText('Drop a strategy file above to deploy it.')).toHaveCount(0)
})

test('one dead platform still lists the other, and names the one that failed', async ({ page }) => {
  const listing = await real<StrategyFilesResponse>(page, '/strategy-files')
  await mock(page, '/strategy-files', {
    ...listing,
    files: listing.files.filter((f) => f.platform === 'MT5'),
    nt8_error: AGENT_DOWN,
    mt5_error: null,
  })
  await page.goto('/strategies?tab=deployed')

  await expect(page.getByText(/Can’t reach the NT8 agent/i)).toBeVisible()
  // The MT5 half is still real data and still on screen — a dead NT8 agent used
  // to 502 the whole request and take these rows with it.
  await expect(page.getByText('LondonBreakout.mq5')).toBeVisible()
})

// ── The Strategies tab must not offer Run for a strategy it cannot vouch for ──

test('a strategy that needs deploying still says so with the agent down', async ({ page }) => {
  const sync = await real<StrategyFileSyncResponse>(page, '/strategy-files/sync-status')
  const nt8 = sync.statuses.find((s) => s.expected_filename.endsWith('.cs'))
  test.skip(!nt8, 'needs at least one NT8 strategy registered')

  await mock(page, '/strategy-files/sync-status', {
    ...sync,
    nt8_error: AGENT_DOWN,
    statuses: sync.statuses.map((s) =>
      s.expected_filename.endsWith('.cs')
        ? // What the backend now serves when NT8 is unreachable: the hash-derived
          // fields survive, the agent-derived ones go null.
          {
            ...s,
            file_exists_on_vps: null,
            in_sync: null,
            needs_deploy: true,
            needs_compile: false,
          }
        : s
    ),
  })
  await page.goto('/strategies')

  const row = nt8Row(page)
  await expect(row.getByText('Needs deploy')).toBeVisible()
  // The defect: `needs_deploy` was undefined when the request died, undefined is
  // falsy, and the row fell through to a Run button that submits to a dead agent.
  await expect(row.getByRole('button', { name: /^Run$/ })).toHaveCount(0)
  await expect(row.getByRole('button', { name: /Deploy/ })).toBeVisible()
})

test('a whole sync failure never leaves a deploying strategy offering Run', async ({ page }) => {
  // The sync request dying OUTRIGHT (backend down) is the case the row-level
  // guard exists for: `needs_deploy`/`needs_compile` are then `undefined`, which
  // is falsy, so the action cell used to fall through to Run — for a strategy
  // whose deploy state is completely unknown.
  //
  // ⚠ This is a SEPARATE test from the one above on purpose. That one mocks a
  // per-platform failure with `needs_deploy: true` still present, so the Deploy
  // button renders whether or not the guard exists — proven by mutation: removing
  // the guard left that test GREEN. A test that cannot fail on the defect it
  // names is worse than no test.
  await fail(page, '/strategy-files/sync-status', AGENT_DOWN)
  await page.goto('/strategies')

  const row = nt8Row(page)
  await expect(row).toBeVisible()
  await expect(row.getByRole('button', { name: /^Run$/ })).toHaveCount(0)
  await expect(row.getByText('unknown')).toBeVisible()
  // A python strategy has no deploy step at all, so its Run button is correct
  // here — the guard must not blanket-disable the page.
  const py = page
    .locator('tbody tr')
    .filter({ has: page.getByRole('img', { name: /Python/i }) })
    .first()
  if (await py.count()) await expect(py.getByRole('button', { name: /^Run$/ })).toBeVisible()
})

test('a deployment whose file is gone from the VPS is not "In sync"', async ({ page }) => {
  const sync = await real<StrategyFileSyncResponse>(page, '/strategy-files/sync-status')
  const nt8 = sync.statuses.find((s) => s.expected_filename.endsWith('.cs'))
  test.skip(!nt8, 'needs at least one NT8 strategy registered')

  await mock(page, '/strategy-files/sync-status', {
    ...sync,
    statuses: sync.statuses.map((s) =>
      s.expected_filename.endsWith('.cs')
        ? // Hashes agree — so every pill the page used to draw reads green — but the
          // file was deleted off the box by hand. `file_exists_on_vps` and `in_sync`
          // were computed for exactly this and rendered nowhere.
          {
            ...s,
            needs_deploy: false,
            needs_compile: false,
            file_exists_on_vps: false,
            in_sync: false,
          }
        : s
    ),
  })
  await page.goto('/strategies')

  const row = nt8Row(page)
  await expect(row.getByText('Missing on VPS')).toBeVisible()
  await expect(row.getByText('In sync')).toHaveCount(0)
  await expect(row.getByRole('button', { name: /Redeploy/ })).toBeVisible()
})

test('an unconfirmable deployment says so instead of claiming "In sync"', async ({ page }) => {
  const sync = await real<StrategyFileSyncResponse>(page, '/strategy-files/sync-status')
  test.skip(!sync.statuses.length, 'needs at least one deploying strategy registered')

  await mock(page, '/strategy-files/sync-status', {
    ...sync,
    nt8_error: AGENT_DOWN,
    mt5_error: AGENT_DOWN,
    statuses: sync.statuses.map((s) => ({
      ...s,
      needs_deploy: false,
      needs_compile: false,
      file_exists_on_vps: null,
      in_sync: null,
    })),
  })
  await page.goto('/strategies')

  await expect(page.getByText('VPS unknown').first()).toBeVisible()
  await expect(page.getByText('In sync')).toHaveCount(0)
})

// ── The compile modal must always be closable ────────────────────────────────

test('a compile whose status cannot be read is still dismissible', async ({ page }) => {
  const listing = await real<StrategyFilesResponse>(page, '/strategy-files')
  test.skip(
    !listing.files.some((f) => f.platform === 'NT8'),
    'needs an NT8 file for the compile button'
  )

  await page.route('**/api/strategy-files/compile', (r) =>
    r.fulfill({
      status: 202,
      contentType: 'application/json',
      body: JSON.stringify({ compile_job_id: 'stuck-job' }),
    })
  )
  await fail(
    page,
    '/strategy-files/compile/stuck-job',
    'VPS agent /compile/stuck-job: HTTP Error 404: NOT FOUND'
  )

  await page.goto('/strategies?tab=deployed')
  await page.getByRole('button', { name: /Compile NT8/ }).click()

  // The defect: `isError` was never read, so `job` stayed undefined, `running`
  // stayed true, and the footer holding the ONLY close button never rendered.
  // A page reload was the only way out.
  await expect(page.getByText(/Lost contact with the compiler/i)).toBeVisible()
  await page.getByRole('button', { name: 'Close', exact: true }).last().click()
  await expect(page.getByText(/Lost contact with the compiler/i)).toHaveCount(0)
})

test('escape closes the compile modal', async ({ page }) => {
  const listing = await real<StrategyFilesResponse>(page, '/strategy-files')
  test.skip(
    !listing.files.some((f) => f.platform === 'NT8'),
    'needs an NT8 file for the compile button'
  )

  await page.route('**/api/strategy-files/compile', (r) =>
    r.fulfill({
      status: 202,
      contentType: 'application/json',
      body: JSON.stringify({ compile_job_id: 'running-job' }),
    })
  )
  await mock(page, '/strategy-files/compile/running-job', {
    compile_job_id: 'running-job',
    status: 'running',
    errors: [],
    warnings: [],
  })

  await page.goto('/strategies?tab=deployed')
  await page.getByRole('button', { name: /Compile NT8/ }).click()
  await expect(page.getByText(/Compiling…/)).toBeVisible()

  // A modal with no terminal status renders no footer button at all, so Escape
  // is the only exit that exists while it is genuinely still running.
  await page.keyboard.press('Escape')
  await expect(page.getByText(/Compiling…/)).toHaveCount(0)
})

// ── The version chip must name what is RUNNING ───────────────────────────────

test('with a compile pending, the chip does not claim the new version is running', async ({
  page,
}) => {
  const sync = await real<StrategyFileSyncResponse>(page, '/strategy-files/sync-status')
  const nt8 = sync.statuses.find((s) => s.expected_filename.endsWith('.cs'))
  test.skip(!nt8, 'needs at least one NT8 strategy registered')

  await mock(page, '/strategy-files/sync-status', {
    ...sync,
    statuses: sync.statuses.map((s) =>
      s.expected_filename.endsWith('.cs')
        ? // v7 deployed, v6 compiled: NinjaTrader is still EXECUTING v6, because it
          // runs the DLL and not the source. The chip used to read "running v7".
          {
            ...s,
            current_version: 7,
            deployed_version: 7,
            compiled_version: 6,
            needs_deploy: false,
            needs_compile: true,
            file_exists_on_vps: true,
            in_sync: true,
          }
        : s
    ),
  })
  await page.goto('/strategies')

  const chip = nt8Row(page).getByText('v7', { exact: true })
  await expect(chip).toHaveAttribute('title', /compiled v6 is what runs/)
})

// ── Orphans are visible without pressing Scan ────────────────────────────────

test('an orphaned strategy offers Reconcile on a cold page load', async ({ page }) => {
  const strategies = await real<Array<Record<string, unknown>>>(page, '/strategies')
  test.skip(!strategies.length, 'needs at least one strategy registered')

  await mock(
    page,
    '/strategies',
    strategies.map((s, i) => (i === 0 ? { ...s, is_orphan: true } : s))
  )
  await page.goto('/strategies')

  // The defect: this button read `scan.data?.orphans` — MUTATION state — so an
  // orphan was invisible until somebody happened to press Scan.
  await expect(page.getByRole('button', { name: /Reconcile \(1\)/ })).toBeVisible()
})

// ── The toast storm ──────────────────────────────────────────────────────────

test('a failing poll does not toast', async ({ page }) => {
  await fail(page, '/strategy-files', AGENT_DOWN)
  await fail(page, '/strategy-files/sync-status', AGENT_DOWN)
  await page.goto('/strategies')

  // Both queries have failed by now; the page renders the state instead.
  await expect(page.getByText(/Can’t reach the/i).first()).toBeVisible()
  // sonner renders toasts into a list with this role. Any error toast here is
  // one per failed poll, for as long as the page stays open.
  await expect(page.locator('[data-sonner-toast]')).toHaveCount(0)
})
