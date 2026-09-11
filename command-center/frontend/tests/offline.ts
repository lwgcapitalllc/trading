/**
 * A spec's backend, answered from a RECORDING — and nothing else leaves the browser.
 *
 * 🔴 **WHY IT EXISTS.** `refuseLiveWrites` blocks writes and lets READS through to the real
 * backend, and on the Bots page several reads reach the live trading box: the bot snapshot is an
 * SSH round trip (~4s, paid by every check — most of why `bots-version.spec.ts` took 4 minutes) and
 * the health dots probe the box's agents. A suite that reads the live system also inherits its
 * STATE: on 2026-09-10 both bots moved to a live account, and every check assuming a demo account
 * would have gone red against the real backend on a day nothing in the page was wrong.
 *
 * So every `/api` request is answered by a route the SPEC registered, or by the recording (GET
 * only), or it is ABORTED and named in `unrouted` — and `offlineTest` fails the test on it at
 * teardown. **Deny by default**: a new read the page grows fails loudly instead of reaching the box.
 *
 * ⚠ **The recording is re-taken by a person** (`node scripts/record-api.mjs <file>`) — the one
 * step that touches the real backend — and its SHAPE is checked against the routes' own response
 * models on every backend run (`command-center/backend/tests/test_api_recordings.py`), so a
 * renamed field goes red there instead of as a confusing browser failure here.
 * ⚠ **A spec states the state it needs** (demo or live, running or stopped) by mutating a copy from
 * `recorded()` — never by trusting whatever the box happened to say on the day it was recorded.
 */
import { readFileSync } from 'node:fs'
import { test as base, expect, type Page } from '@playwright/test'

type Recording = { answers: Record<string, unknown> }

function load(name: string): Recording {
  return JSON.parse(readFileSync(new URL(`./recordings/${name}.json`, import.meta.url), 'utf8'))
}

export type Offline = { unrouted: string[] }

/**
 * Answer the page from `recording`; abort and record anything else.
 *
 * ⚠ **Register it BEFORE a spec's own routes.** Playwright matches the most recently registered
 * handler first and `fallback()` walks backwards, so this only sees what the spec did not answer.
 */
export async function offlineBackend(page: Page, recording: Recording): Promise<Offline> {
  const off: Offline = { unrouted: [] }
  await page.route('**/*', (route) => {
    const req = route.request()
    const url = new URL(req.url())
    if (!url.pathname.startsWith('/api/')) return route.fallback()
    const key = url.pathname.slice(4) + url.search
    if (req.method() === 'GET' && key in recording.answers) {
      return route.fulfill({ json: recording.answers[key] })
    }
    off.unrouted.push(`${req.method()} ${key}`)
    return route.abort('blockedbyclient')
  })
  return off
}

/**
 * Run the page's clock `factor` times faster than the wall clock, from before it loads.
 *
 * The deploy readout polls once a second and the restart warning every 15s, so a check that
 * watches either spends most of its life waiting. Every timer still fires, in the same order and
 * at the same page-time spacing — a poll is still a poll and a step still takes one — only sooner.
 *
 * ⚠ **Only the PAGE's clock.** A spec's route handler runs in Node on the real clock, so a mock
 * that times something itself (a delayed answer, a "settles after N ms") keeps real milliseconds.
 */
async function quickenClock(page: Page, factor: number): Promise<() => void> {
  await page.clock.install()
  let running = true
  const WALL_MS = 50
  void (async () => {
    while (running) {
      await new Promise((ok) => setTimeout(ok, WALL_MS))
      if (!running) break
      // The installed clock already moves WALL_MS on its own; this adds the rest of the factor.
      await page.clock.runFor(WALL_MS * (factor - 1)).catch(() => (running = false))
    }
  })()
  return () => (running = false)
}

/**
 * A `test` whose every check runs offline against `recordingName`, and fails if the page asked the
 * backend for anything neither the spec nor the recording answered.
 *
 * `clockFactor` runs every page's clock that many times faster (see `quickenClock`).
 */
export function offlineTest(recordingName: string, opts: { clockFactor?: number } = {}) {
  const recording = load(recordingName)
  const test = base.extend<{ recordedApi: Offline }>({
    recordedApi: [
      async ({ page }, use) => {
        const off = await offlineBackend(page, recording)
        const stopClock = opts.clockFactor ? await quickenClock(page, opts.clockFactor) : null
        await use(off)
        stopClock?.()
        expect(
          off.unrouted,
          'the page asked the backend for something neither this spec nor the recording answers ' +
            '— route it in the spec, or re-record with scripts/record-api.mjs --add <path>'
        ).toEqual([])
      },
      { auto: true },
    ],
  })
  /** A fresh copy of a recorded answer, for a spec to shape into the state it needs. */
  const recorded = <T>(path: string): T => {
    if (!(path in recording.answers))
      throw new Error(`${recordingName} holds no answer for ${path}`)
    return structuredClone(recording.answers[path]) as T
  }
  return { test, recorded }
}
