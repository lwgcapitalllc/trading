/**
 * The Calendar page's regression suite.
 *
 * Every check is a defect that shipped on 2026-08-05, and they share the Overview suite's shape:
 * NOT ONE of them rendered an error. The page showed the previous week's rows under the new week's
 * header, threw a good week away over one failed poll, went on asking for last week after midnight,
 * and answered a hand-typed URL with a confident "No events". A calendar that is wrong about the
 * week is worse than one that says it does not know.
 *
 * ⚠ EVERY ONE OF THESE WAS WATCHED TO FAIL against the page as it was before the fix. A suite
 * written after a fix and never run against the defect is a description of the fix, not a test of
 * it.
 *
 * ⚠ Unlike `overview.spec.ts` this file needs NO BACKEND — only the dev server on :5173
 * (`npm run dev`). Every response it depends on is intercepted, which is deliberate: the calendar
 * reads one endpoint, so mocking it whole means this suite never needs the SSH tunnel or the live
 * MT5 box to run. Prefer that shape for a new suite when the page allows it.
 */
import { test, expect, type Page } from '@playwright/test'
import type { CalendarEvent, CalendarResponse } from '../src/types'

// ── fixture ─────────────────────────────────────────────────────────────────────

function ev(over: Partial<CalendarEvent> & { timestamp_ms: number }): CalendarEvent {
  return {
    currency: 'USD',
    impact: 'HIGH',
    title: 'Non Farm Payrolls',
    category: 'Labor',
    forecast: '150K',
    previous: '140K',
    actual: null,
    surprise: null,
    ...over,
  }
}

/** Local Monday 00:00 of the week `offset` weeks from `now` — the page's own `localWeekStart`. */
function weekStart(now: Date, offset = 0): Date {
  const d = new Date(now)
  d.setHours(0, 0, 0, 0)
  d.setDate(d.getDate() - ((d.getDay() + 6) % 7) + offset * 7)
  return d
}

type Opts = {
  /** Fail every response after the Nth (0 = fail immediately). */
  failAfter?: number
  /** Delay each response, to make the loading window observable. */
  delayMs?: number
  /** Build the week's events from its Monday. Default: one event per weekday at noon. */
  build?: (monday: Date) => CalendarEvent[]
  /** The roster `/calendar/currencies` serves. Deliberately NOT the real nine by default — a test
   *  that asserts the shipped list would pass just as well against a hardcoded copy of it. */
  currencies?: string[]
}

/** Intercept /api/calendar and serve a week generated from the requested window.
 *  Returns a live count of how many times it answered. */
async function mockCalendar(page: Page, opts: Opts = {}) {
  const served = { n: 0 }
  // Registered first; the glob below cannot match it (Playwright's `*` stops at a `/`).
  await page.route('**/api/calendar/currencies', route =>
    route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({ currencies: opts.currencies ?? ['USD', 'EUR', 'GBP'] }),
    }))
  await page.route('**/api/calendar*', async route => {
    if (opts.failAfter !== undefined && served.n >= opts.failAfter) {
      served.n++
      return route.fulfill({ status: 502, contentType: 'application/json', body: '{"detail":"feed down"}' })
    }
    served.n++
    const from = new Date(new URL(route.request().url()).searchParams.get('from')!)
    const events = opts.build
      ? opts.build(from)
      : [0, 1, 2, 3, 4].map(i => {
          const d = new Date(from)
          d.setDate(d.getDate() + i)
          d.setHours(12, 0, 0, 0)
          return ev({ timestamp_ms: d.getTime(), title: `Event ${from.getDate()}-${i}` })
        })
    const body: CalendarResponse = {
      events,
      server_now_ms: Date.now(),
      from_ms: from.getTime(),
      to_ms: from.getTime() + 7 * 86_400_000,
    }
    if (opts.delayMs) await new Promise(r => setTimeout(r, opts.delayMs))
    await route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify(body) })
  })
  // The shell mounts on every page; stub it so this suite needs no backend at all.
  await page.route('**/api/system/**', r =>
    r.fulfill({ status: 200, contentType: 'application/json', body: '{}' }))
  return served
}

const rows = (page: Page) => page.locator('[data-testid="calendar-row"]')

// ── the week is derived from the clock, not frozen at mount ─────────────────────

test.describe('Calendar — the week window', () => {
  test('rolls over at midnight with no reload', async ({ page }) => {
    // 🔴 `useMemo(() => localWeekStart(weekOffset), [weekOffset])`. `weekOffset` does not change at
    // midnight, so a tab left open across Sunday→Monday asked for LAST week for ever — the same
    // defect the Overview fixed, whose comment claimed THIS page already recomputed. It did not.
    const asked: string[] = []
    page.on('request', r => {
      const m = r.url().match(/\/api\/calendar\?from=([^&]+)/)
      if (m) asked.push(decodeURIComponent(m[1]).slice(0, 10))
    })
    await mockCalendar(page)
    await page.clock.install({ time: new Date(2026, 7, 9, 23, 59, 50) }) // Sunday, 10s to midnight
    await page.goto('/calendar')
    await page.waitForLoadState('networkidle')
    await page.waitForTimeout(1200)
    expect(asked).toContain('2026-08-03')

    await page.clock.fastForward('00:30')
    await page.waitForTimeout(1500)
    expect(asked).toContain('2026-08-10')
  })

  test('the week-range pill follows it over midnight', async ({ page }) => {
    await mockCalendar(page)
    await page.clock.install({ time: new Date(2026, 7, 9, 23, 59, 50) })
    await page.goto('/calendar')
    await page.waitForLoadState('networkidle')
    await expect(page.getByText(/Aug 3\s*–\s*Aug 9/)).toBeVisible()
    await page.clock.fastForward('00:30')
    await expect(page.getByText(/Aug 10\s*–\s*Aug 16/)).toBeVisible()
  })
})

// ── loading a different week must not render the old one ───────────────────────

test.describe('Calendar — paging a week', () => {
  test('never shows the previous week under the new week header', async ({ page }) => {
    // 🔴 `placeholderData: prev` held the OLD week's payload while the new one loaded, and the page
    // only checked `isLoading` (false, because placeholder data exists). So the pill read the new
    // week over an all-zero day strip and a list of the week before.
    await mockCalendar(page, { delayMs: 1200 })
    await page.goto('/calendar')
    await page.waitForLoadState('networkidle')
    const firstRow = await rows(page).first().textContent()

    await page.getByTitle('Next week').click()
    // Mid-flight: the old rows must be gone and the page must say which week it is fetching.
    await expect(page.getByText(/^Loading .* – .*…$/)).toBeVisible()
    expect(await rows(page).count()).toBe(0)
    // and the strip must not claim an empty week
    await expect(page.getByTestId('day-count').first()).toHaveText('—')

    await expect(page.getByText(/^Loading /)).toBeHidden({ timeout: 10_000 })
    expect(await rows(page).first().textContent()).not.toBe(firstRow)
  })
})

// ── a failed poll must not delete a good week ──────────────────────────────────

test.describe('Calendar — a feed that stops answering', () => {
  test('with nothing held, the failure takes the page', async ({ page }) => {
    // The other half of the rule: an error with NO data is the one case that may replace the list.
    await mockCalendar(page, { failAfter: 0 })
    await page.goto('/calendar')
    await page.waitForLoadState('networkidle')
    await expect(page.getByText("Couldn't load the calendar")).toBeVisible()
  })

  test('a refetch failure leaves the rows up behind a dated notice', async ({ page }) => {
    // ⚠ The failure is driven by FAST-FORWARDING past the 45s poll, not by dispatching a `focus`
    // event: the app sets a global `staleTime: 30_000`, so a focus refetch on a query fetched a
    // second ago is skipped entirely and the test would pass by never refetching at all.
    let n = 0
    await page.route('**/api/calendar*', async route => {
      n++
      if (n > 1) return route.fulfill({ status: 502, contentType: 'application/json', body: '{}' })
      const from = new Date(new URL(route.request().url()).searchParams.get('from')!)
      const d = new Date(from); d.setDate(d.getDate() + 1); d.setHours(12, 0, 0, 0)
      const body: CalendarResponse = {
        events: [ev({ timestamp_ms: d.getTime(), title: 'Held Event' })],
        server_now_ms: from.getTime() + 86_400_000,
        from_ms: from.getTime(), to_ms: from.getTime() + 7 * 86_400_000,
      }
      await route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify(body) })
    })
    await page.route('**/api/system/**', r => r.fulfill({ status: 200, contentType: 'application/json', body: '{}' }))
    await page.clock.install()
    await page.goto('/calendar?day=1')
    await page.waitForLoadState('networkidle')
    await expect(rows(page)).toHaveCount(1)

    await page.clock.fastForward('01:00')   // past the 45s poll → the 502
    await expect(page.getByText(/didn't answer the last refresh/)).toBeVisible({ timeout: 15_000 })
    await expect(rows(page)).toHaveCount(1)   // the rows survive
  })
})

// ── URL state a human can type ─────────────────────────────────────────────────

test.describe('Calendar — filter state from the URL', () => {
  test('a rubbish ?day= does not render as an empty week', async ({ page }) => {
    // 🔴 `parseInt('abc')` gave NaN, which matches no event, so the page said "No events" with
    // every filter looking untouched.
    await mockCalendar(page)
    await page.goto('/calendar?day=abc')
    await page.waitForLoadState('networkidle')
    expect(await rows(page).count()).toBeGreaterThan(0)
  })

  test('an out-of-range ?day= does not render as an empty week', async ({ page }) => {
    await mockCalendar(page)
    await page.goto('/calendar?day=99')
    await page.waitForLoadState('networkidle')
    expect(await rows(page).count()).toBeGreaterThan(0)
  })

  test('a category this week has none of explains itself', async ({ page }) => {
    // 🔴 The `<select>` matched no option and rendered BLANK over an empty list — which reads as
    // the page breaking rather than as a filter still being applied.
    await mockCalendar(page)
    await page.goto('/calendar?cat=Housing')
    await page.waitForLoadState('networkidle')
    await expect(page.getByText(/No .Housing. events this week/)).toBeVisible()
    await expect(page.getByRole('combobox')).toHaveValue('Housing')
  })
})

// ── the "now" marker belongs to the week containing now ────────────────────────

test.describe('Calendar — the now line', () => {
  test('is absent on a week that does not contain now', async ({ page }) => {
    await mockCalendar(page)
    await page.goto('/calendar')
    await page.waitForLoadState('networkidle')
    await expect(page.getByTestId('now-line')).toBeVisible()

    await page.getByTitle('Next week').click()
    await page.waitForLoadState('networkidle')
    await expect(page.getByTestId('now-line')).toHaveCount(0)
  })
})

// ── real feed data has duplicate (time, currency, title) rows ──────────────────

test.describe('Calendar — duplicate events', () => {
  test('two identical rows both render, with no duplicate-key warning', async ({ page }) => {
    // The live feed really does carry two `CAD Budget Balance` rows at one timestamp.
    const warnings: string[] = []
    page.on('console', m => { if (/same key|duplicate/i.test(m.text())) warnings.push(m.text()) })
    await mockCalendar(page, {
      build: monday => {
        const d = new Date(monday); d.setDate(d.getDate() + 1); d.setHours(12, 0, 0, 0)
        return [
          ev({ timestamp_ms: d.getTime(), currency: 'CAD', title: 'Budget Balance' }),
          ev({ timestamp_ms: d.getTime(), currency: 'CAD', title: 'Budget Balance' }),
        ]
      },
    })
    // ⚠ `?day=1` is explicit because the page OPENS ON TODAY — a fixture built on a fixed weekday
    // renders as an empty list on every other day of the real week, and the test would then be
    // green four days in seven for the wrong reason.
    await page.goto('/calendar?day=1')
    await page.waitForLoadState('networkidle')
    expect(await rows(page).count()).toBe(2)
    expect(warnings).toEqual([])
  })
})

// ── the countdown ──────────────────────────────────────────────────────────────

test.describe('Calendar — the countdown', () => {
  test('reads in days for an event days away, not 152h', async ({ page }) => {
    const now = new Date(2026, 7, 3, 9, 0, 0)   // Monday morning
    await page.clock.install({ time: now })
    await mockCalendar(page, {
      build: monday => {
        const d = new Date(monday); d.setDate(d.getDate() + 4); d.setHours(12, 0, 0, 0)
        return [ev({ timestamp_ms: d.getTime(), title: 'Distant NFP' })]
      },
    })
    await page.goto('/calendar?day=4')   // the day the event is on; see the note above
    await page.waitForLoadState('networkidle')
    await expect(page.getByTestId('now-line')).toContainText(/\dd \d+h/)
  })
})

// ── the filter roster ──────────────────────────────────────────────────────────
//
// Both of these are about a filter that is applied but cannot be SEEN. The currency chips were a
// hardcoded copy of a list only the backend knows, so a bloc it started querying would have had no
// chip; and a NONE-impact row was governed by a hidden "all three ticked" rule rather than by a
// control of its own. Neither would ever have rendered an error.

test.describe('Calendar — the filter roster', () => {
  test('the currency chips are the backend roster, not a list held in the page', async ({ page }) => {
    // A roster the shipped page has never contained. The old hardcoded nine would ignore this
    // entirely and draw its own chips — which is the defect, stated as a test.
    await mockCalendar(page, { currencies: ['USD', 'SEK', 'NOK'] })
    await page.goto('/calendar')
    await page.waitForLoadState('networkidle')
    const chips = page.getByTestId('currency-chip')
    await expect(chips).toHaveText([/USD/, /SEK/, /NOK/])
  })

  test('a currency held in the URL but absent from the roster is still offered', async ({ page }) => {
    // Otherwise a stale bookmark filters the list with no way to clear it — the same trap the
    // category dropdown had.
    await mockCalendar(page, { currencies: ['USD', 'EUR'] })
    await page.goto('/calendar?cur=ZAR')
    await page.waitForLoadState('networkidle')
    await expect(page.locator('[data-testid="currency-chip"][title="ZAR"]')).toBeVisible()
  })

  test('a NONE-impact row gets its own chip and survives unticking another level', async ({ page }) => {
    // ⚠ THE OLD RULE: NONE rows were shown only while all three chips were ticked, so unticking
    // `Low` — a different level entirely — silently took them with it.
    await mockCalendar(page, {
      build: monday => {
        const d = new Date(monday); d.setDate(d.getDate() + 1); d.setHours(12, 0, 0, 0)
        return [
          ev({ timestamp_ms: d.getTime(), impact: 'NONE', title: 'Unrated Release' }),
          ev({ timestamp_ms: d.getTime() + 3600_000, impact: 'LOW', title: 'Minor Release' }),
        ]
      },
    })
    await page.goto('/calendar?day=1')
    await page.waitForLoadState('networkidle')
    expect(await rows(page).count()).toBe(2)

    await page.getByTestId('impact-chip').filter({ hasText: 'Low' }).click()
    await expect(rows(page)).toHaveCount(1)
    await expect(rows(page).first()).toContainText('Unrated Release')

    await page.getByTestId('impact-chip').filter({ hasText: 'None' }).click()
    await expect(rows(page)).toHaveCount(0)
  })

  test('no None chip on a week that has no unrated row', async ({ page }) => {
    // A control for a state that cannot occur is UI nobody can read. MEASURED: zero NONE-impact
    // events in 2,000 real ones — so on the live feed this chip is simply never drawn.
    // ⚠ This one is red at HEAD only because the testid did not exist there; the three-chip
    // behaviour it asserts was already right. Kept to pin that half, not claimed as a catch.
    await mockCalendar(page)
    await page.goto('/calendar')
    await page.waitForLoadState('networkidle')
    await expect(page.getByTestId('impact-chip')).toHaveText([/High/, /Medium/, /Low/])
  })
})
