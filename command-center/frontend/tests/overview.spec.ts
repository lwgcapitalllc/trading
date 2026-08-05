/**
 * The Overview's regression suite.
 *
 * Every check here is a defect that shipped, and the shape they share is why the suite exists:
 * NOT ONE of them showed an error. Each rendered a confident, healthy-looking answer on the one
 * page whose whole job is answering "is anything wrong". A green dashboard is this page's
 * failure mode, so a test that only asserts the happy path is worth very little here.
 *
 * ⚠ MOST OF THESE STATES CANNOT BE PRODUCED BY THE LIVE BOX, which is exactly why they broke:
 * a blind bot, a fleet that half-reports, an empty fleet, a VPS that dies mid-session, a dead
 * calendar feed. They are mocked by intercepting the API, and the mock is built by MUTATING THE
 * REAL SNAPSHOT rather than by hand-writing a fixture — a hand-written one drifts from the
 * backend's model and then tests a shape the server never sends.
 *
 * Needs the backend on :8000 and the dev server on :5173 (`./start.sh`).
 */
import { test, expect, type Page } from '@playwright/test'
import type { BotSnapshot } from '../src/types'

const API = 'http://localhost:8000'

async function liveSnapshot(): Promise<BotSnapshot> {
  const res = await fetch(`${API}/bots/snapshot`)
  if (!res.ok) throw new Error(`backend not answering (${res.status}) — is it running?`)
  return res.json()
}

/** Serve a mutated copy of the REAL snapshot. `failAfterFirst` lets the VPS die mid-session. */
async function mockSnapshot(
  page: Page,
  mutate: (s: BotSnapshot) => void,
  opts: { failAfterFirst?: boolean } = {},
) {
  const real = await liveSnapshot()
  let served = 0
  await page.route('**/api/bots/snapshot', async route => {
    if (opts.failAfterFirst && served > 0) {
      return route.fulfill({ status: 503, contentType: 'application/json', body: '{"detail":"ssh dead"}' })
    }
    served++
    const snap = JSON.parse(JSON.stringify(real)) as BotSnapshot
    mutate(snap)
    await route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify(snap) })
  })
}

const statCard = (page: Page, label: string) => page.locator(`button:has-text("${label}")`).first()
/** The calendar rows, by their leading HH:MM — the stat row is also `grid-cols-2`. */
const eventRows = (page: Page) => page.getByRole('button').filter({ hasText: /^\d{1,2}:\d{2}/ })

test.describe('Overview — the live box', () => {
  test('a DISABLED job never wears the "scheduled" pill, and a STOPPED one still does', async ({ page }) => {
    await page.goto('/')
    await page.waitForLoadState('networkidle')

    const pills = await page.$$eval('span[title]', els => els
      .filter(e => /Scheduled — waiting|Disabled — will not run|^Running$/.test(e.getAttribute('title')!))
      .map(e => ({ text: e.textContent!.trim(), title: e.getAttribute('title')!, cls: e.className })))
    const byName = Object.fromEntries(pills.map(p => [p.text, p]))

    // A task that will never fire must not read as covered. This is the whole defect.
    for (const disabled of ['P&L Tracker', 'Reporter']) {
      expect(byName[disabled], `${disabled} should be reported`).toBeDefined()
      expect(byName[disabled].title).toMatch(/^Disabled/)
      expect(byName[disabled].cls).not.toContain('text-gold-text')
    }
    // ⚠ STOPPED is NOT the same claim — a scheduled task that is not executing right this second
    // is healthy, and painting it grey would be the same bug in reverse.
    expect(byName['Monitor'].title).toMatch(/^Scheduled/)
    expect(byName['Monitor'].cls).toContain('text-gold-text')
  })

  test('a calendar row lands on that event\'s own day, not the bare week', async ({ page }) => {
    await page.goto('/')
    await page.waitForLoadState('networkidle')
    const row = eventRows(page).first()
    test.skip(await row.count() === 0, 'no upcoming events left this week')
    await row.click()
    await expect(page).toHaveURL(/\/calendar\?day=\d/)
  })

  test('renders with no console errors', async ({ page }) => {
    const errors: string[] = []
    page.on('console', m => { if (m.type() === 'error') errors.push(m.text()) })
    page.on('pageerror', e => errors.push(String(e)))
    await page.goto('/')
    await page.waitForLoadState('networkidle')
    await page.waitForTimeout(1500)
    expect(errors).toEqual([])
  })
})

test.describe('Overview — states the live box cannot produce', () => {
  test('a bot that is RUNNING and BLIND is not a healthy fleet', async ({ page }) => {
    await mockSnapshot(page, s => { s.bots[0].mt5_link = false })
    await page.goto('/')
    await page.waitForLoadState('networkidle')

    // ⚠ BESIDE the Running pill, never instead of it: the process is alive AND it is blind, and
    // those are different facts. Collapsing them loses whichever half the reader came for.
    await expect(page.getByText('No link')).toBeVisible()
    await expect(page.getByText('Running').first()).toBeVisible()

    const sub = await statCard(page, 'Bots Running').textContent()
    expect(sub).not.toMatch(/all bots live/)
    expect(sub).toMatch(/no MT5 link/)
    // warn, not neg — it is not a failure, and not pos — it is not fine.
    const cls = await statCard(page, 'Bots Running').locator('div').last().getAttribute('class')
    expect(cls).toContain('text-warn-text')
  })

  test('a balance that could not be read is named, never summed as $0', async ({ page }) => {
    await mockSnapshot(page, s => { s.bots[0].balance = null })
    await page.goto('/')
    await page.waitForLoadState('networkidle')
    const sub = await statCard(page, 'Balance').textContent()
    expect(sub).toMatch(/1 of 1 not reporting/)
    expect(sub).not.toMatch(/\$0\.00/)
  })

  test('a partly-reporting fleet flags the total as incomplete', async ({ page }) => {
    await mockSnapshot(page, s => {
      const second = JSON.parse(JSON.stringify(s.bots[0]))
      second.key = 'orb_live'; second.name = 'ORB'; second.balance = null; second.account_type = 'live'
      s.bots.push(second)
    })
    await page.goto('/')
    await page.waitForLoadState('networkidle')
    expect(await statCard(page, 'Balance').textContent()).toMatch(/1 of 2 not reporting/)
  })

  test('an empty fleet does not read "all bots live"', async ({ page }) => {
    await mockSnapshot(page, s => { s.bots = [] })
    await page.goto('/')
    await page.waitForLoadState('networkidle')
    // `runningBots === totalBots` is TRUE at 0 / 0 — the branch order is the fix.
    const sub = await statCard(page, 'Bots Running').textContent()
    expect(sub).not.toMatch(/all bots live/)
    expect(sub).toMatch(/none registered/)
    // The trailing stop scopes this to the card's own line — the stat card's sub-line reads
    // "no bots registered" too, and an unanchored match is ambiguous across the two.
    await expect(page.getByText('No bots registered.')).toBeVisible()
  })

  /**
   * ⚠ THE SLOW ONE (~65s), and it has to be. It waits out `useBotSnapshot`'s real 60s poll,
   * because that is the only thing that re-fetches here — two faster routes were tried and both
   * assert the WRONG BRANCH:
   *   - `page.goto` is a full page load, which destroys the query cache. With no stale data left
   *     the page correctly shows the plain failure, not the dated one.
   *   - client-side nav away and back does not re-fetch either: `main.tsx` sets a global
   *     `staleTime: 30_000`, so a remount inside 30s is served from cache and the mock is never
   *     called a second time (measured — the route was hit exactly once).
   * It is kept in the default run rather than tagged and skipped: this is the branch that decides
   * whether a dead VPS looks like a healthy fleet, and a test nobody runs protects nothing.
   */
  test('a VPS that dies mid-session dates its stale rows instead of passing them off as live', async ({ page }) => {
    test.setTimeout(120_000)
    await mockSnapshot(page, s => s, { failAfterFirst: true })
    await page.goto('/')
    await page.waitForLoadState('networkidle')
    await expect(page.getByText('MPC SOS Fade')).toBeVisible()   // a good snapshot first

    // TanStack keeps the last good `data` through a failed refetch, so the error and real bot
    // rows render together — and those rows still say RUNNING. Dating them is the whole fix.
    await expect(page.getByText(/showing the snapshot from \d/)).toBeVisible({ timeout: 90_000 })
  })

  test('a dead calendar feed reads as unavailable, not "Loading…" for ever', async ({ page }) => {
    await page.route('**/api/calendar*', r =>
      r.fulfill({ status: 502, contentType: 'application/json', body: '{"detail":"feed down"}' }))
    await page.goto('/')
    await page.waitForLoadState('networkidle')
    await expect(page.getByText('Calendar unavailable')).toBeVisible()
    await expect(page.getByText('Loading…')).toHaveCount(0)
  })

  test('one upcoming event, promoted into the callout, leaves no empty grid', async ({ page }) => {
    const week = await (await fetch(
      `${API}/calendar?from=${new Date(Date.now() - 3 * 864e5).toISOString()}` +
      `&to=${new Date(Date.now() + 4 * 864e5).toISOString()}`)).json()
    await page.route('**/api/calendar*', r => r.fulfill({
      status: 200, contentType: 'application/json',
      body: JSON.stringify({
        ...week,
        events: week.events.filter((e: { timestamp_ms: number }) => e.timestamp_ms > week.server_now_ms)
          .slice(0, 1).map((e: object) => ({ ...e, impact: 'HIGH' })),
      }),
    }))
    await page.goto('/')
    await page.waitForLoadState('networkidle')
    // `upcoming.length === 0` is false here, so the grid branch used to render with no children.
    await expect(eventRows(page)).toHaveCount(0)
    await expect(page.getByText('Nothing else this week')).toBeVisible()
  })
})

test.describe('Overview — the clock', () => {
  /** A HIGH event 90s out, where the countdown carries SECONDS. Above an hour it renders whole
   *  minutes and a short sample cannot prove the clock moves — which is how a frozen one shipped. */
  async function eventInNinetySeconds(page: Page) {
    const week = await (await fetch(
      `${API}/calendar?from=${new Date(Date.now() - 3 * 864e5).toISOString()}` +
      `&to=${new Date(Date.now() + 4 * 864e5).toISOString()}`)).json()
    await page.route('**/api/calendar*', r => r.fulfill({
      status: 200, contentType: 'application/json',
      body: JSON.stringify({
        ...week,
        server_now_ms: Date.now(),
        events: [{ ...week.events[0], impact: 'HIGH', timestamp_ms: Date.now() + 90_000 }],
      }),
    }))
  }

  test('the Overview countdown ticks rather than freezing on server_now_ms', async ({ page }) => {
    await eventInNinetySeconds(page)
    await page.goto('/')
    const cd = page.locator('text=/^in \\d+m \\d+s$/').first()
    const first = await cd.textContent()
    await page.waitForTimeout(2200)
    expect(await cd.textContent()).not.toBe(first)
  })

  test('the Calendar page shares that clock and still ticks', async ({ page }) => {
    await eventInNinetySeconds(page)
    await page.goto('/calendar')
    const cd = page.locator('text=/\\d+m \\d+s/').first()
    const first = await cd.textContent()
    await page.waitForTimeout(2200)
    expect(await cd.textContent()).not.toBe(first)
  })

  test('the week window rolls over at midnight with no reload', async ({ page }) => {
    // The window was `useMemo(..., [])`, so a dashboard left open past Sunday midnight asked for
    // LAST week for ever and read "no more events this week". ⚠ This test is only evidence
    // because it FAILS against that code — it did, when it was run against it.
    const asked: string[] = []
    page.on('request', r => {
      const m = r.url().match(/\/api\/calendar\?from=([^&]+)/)
      if (m) asked.push(decodeURIComponent(m[1]).slice(0, 10))
    })
    await page.clock.install({ time: new Date(2026, 7, 9, 23, 59, 50) })  // Sunday, 10s to midnight
    await page.goto('/')
    await page.waitForLoadState('networkidle')
    await page.waitForTimeout(1500)
    expect(asked).toContain('2026-08-03')

    await page.clock.fastForward('00:30')
    await page.waitForTimeout(1500)
    expect(asked).toContain('2026-08-10')
  })

  test('a week containing a DST changeover spans a real 7 days', async ({ page }) => {
    const asked: [string, string][] = []
    page.on('request', r => {
      const m = r.url().match(/\/api\/calendar\?from=([^&]+)&to=([^&]+)/)
      if (m) asked.push([decodeURIComponent(m[1]), decodeURIComponent(m[2])])
    })
    await page.goto('/calendar?week=12')   // US fall-back, 2026-11-01
    await page.waitForLoadState('networkidle')
    await page.waitForTimeout(1000)
    const [from, to] = asked.at(-1)!
    // 169h, not the 168h a flat `+ 7 * 86_400_000` gives — which silently dropped the last hour
    // of that Sunday.
    expect((new Date(to).getTime() - new Date(from).getTime()) / 3.6e6).toBe(169)
  })
})

test.describe('Overview — the silent-failure warnings', () => {
  const degraded = {
    warnings: [
      'news calendar cache is EMPTY — the News & Holiday filter will tag nothing.',
      'algos/credentials.json missing — every Telegram notification is a no-op',
    ],
    checked_at: new Date().toISOString(),
  }

  test('names each degraded dependency', async ({ page }) => {
    await page.route('**/api/system/readiness', r =>
      r.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify(degraded) }))
    await page.goto('/')
    await page.waitForLoadState('networkidle')
    await expect(page.getByText('2 dependencies are degraded')).toBeVisible()
    await expect(page.getByText(/News & Holiday filter will tag nothing/)).toBeVisible()
    await expect(page.getByText(/Telegram notification is a no-op/)).toBeVisible()
  })

  test('renders NOTHING when everything is fine', async ({ page }) => {
    // ⚠ Not "all dependencies OK". A permanent green tick in this spot teaches the reader to
    // stop looking at it, and this is the one row that must be read the day it speaks up.
    await page.route('**/api/system/readiness', r => r.fulfill({
      status: 200, contentType: 'application/json',
      body: JSON.stringify({ warnings: [], checked_at: new Date().toISOString() }),
    }))
    await page.goto('/')
    await page.waitForLoadState('networkidle')
    await expect(page.getByText(/dependenc(y|ies) (is|are) degraded/)).toHaveCount(0)
  })
})

test.describe('Sidebar — the running dots', () => {
  test('reads three booleans, and does NOT pull the run list to do it', async ({ page }) => {
    // The whole point of the change: Sidebar.tsx is mounted on every page, so deriving these
    // client-side made a ~137 KB runs response a permanent cost of having the app open.
    const calls: string[] = []
    page.on('request', r => {
      const m = r.url().match(/\/api\/(backtests\/runs|optimizations|stress-tests|system\/activity)(\?|$)/)
      if (m) calls.push(m[1])
    })
    // A page that does not itself render any of those lists.
    await page.goto('/rulesets')
    await page.waitForLoadState('networkidle')
    await page.waitForTimeout(6000)   // past one activity poll

    expect(calls).toContain('system/activity')
    expect(calls).not.toContain('backtests/runs')
    expect(calls).not.toContain('optimizations')
    expect(calls).not.toContain('stress-tests')
  })

  test('lights the Backtests dot when the endpoint says so', async ({ page }) => {
    await page.route('**/api/system/activity', r => r.fulfill({
      status: 200, contentType: 'application/json',
      body: JSON.stringify({ backtests: true, optimizations: false, stress_tests: false }),
    }))
    await page.goto('/rulesets')
    await page.waitForLoadState('networkidle')
    await expect(page.getByText('Running').first()).toBeVisible()
  })
})

test.describe('Overview — layout', () => {
  // 6px of bleed hid inside the card's 15px padding, so this was invisible by eye at every width
  // including the one the first verification pass called "verified".
  for (const width of [1670, 1280, 1024]) {
    test(`nothing overflows its container at ${width}px`, async ({ page }) => {
      await mockSnapshot(page, s => { s.bots[0].mt5_link = false; s.bots[0].day_locked = true })
      await page.setViewportSize({ width, height: 940 })
      await page.goto('/')
      await page.waitForLoadState('networkidle')
      await page.waitForTimeout(1000)
      const overflowing = await page.evaluate(() => {
        const out: string[] = []
        for (const el of Array.from(document.querySelectorAll('div,span,p,button'))) {
          if (el.scrollWidth > el.clientWidth + 1 && el.clientWidth > 0
              && getComputedStyle(el).overflowX === 'visible'
              && !String(el.className).includes('truncate')) {
            out.push(`${el.tagName} ${el.scrollWidth}>${el.clientWidth} ${String(el.className).slice(0, 60)}`)
          }
        }
        return out
      })
      expect(overflowing).toEqual([])
      expect(await page.evaluate(() =>
        document.documentElement.scrollWidth > window.innerWidth)).toBe(false)
    })
  }
})
