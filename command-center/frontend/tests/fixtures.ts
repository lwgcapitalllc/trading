/**
 * Shared helpers for the browser suites that read the REAL backend.
 *
 * 🔴 `requireRun` lived here — it made a spec pinned to a lab run fail by NAME when that run left
 * the lab, instead of as a 120-second timeout pointing at a feature that was fine. Its seven
 * callers (the chart specs) moved to RECORDINGS on 2026-09-11 (`tests/offline.ts`), where the run a
 * check needs cannot leave, and it was deleted with no caller left. **A spec that needs a run
 * carrying particular LAYERS replays a recording now** — record one rather than naming a lab row.
 */
export const API = 'http://localhost:8000'

export async function getJson<T>(path: string): Promise<T> {
  const res = await fetch(API + path)
  if (!res.ok) throw new Error(`backend not answering for ${path} (${res.status}) — is it running?`)
  return res.json() as Promise<T>
}

/**
 * Refuse any WRITE that falls through a spec's own mocks to the real backend.
 *
 * 🔴 **Both bot suites end their catch-all with `route.fallback()`, which is allow-by-default.**
 * Every write they trigger today is routed in its own test — CHECKED, not assumed — but that is a
 * property of the tests as they are written rather than of the harness, and this backend PATCHes
 * an instance config, pushes it, and pulls it on the live trading box. A check that reaches that
 * path once has already spent the thing it was protecting.
 *
 * ⚠ **Register it BEFORE a spec's own `mock()`.** Playwright matches the most recently registered
 * handler first and `fallback()` walks backwards, so this only sees what the spec did not answer
 * — which is exactly the set that would otherwise leave the machine.
 *
 * ⚠ **It ABORTS rather than fulfilling a plausible success.** A fake 200 would let a test pass
 * while proving nothing about the request it meant to make, which is the vacuous-pass trap; an
 * abort turns it into a failure naming the unrouted call.
 *
 * ⚠ **Reads are allowed through.** They are what makes these suites worth running against a real
 * backend at all, and the worst a read costs is a slow test.
 */
export async function refuseLiveWrites(page: import('@playwright/test').Page) {
  await page.route('**/*', async (route) => {
    const req = route.request()
    const method = req.method()
    if (method === 'GET' || method === 'HEAD' || method === 'OPTIONS') return route.fallback()
    const url = new URL(req.url())
    if (!url.pathname.startsWith('/api/')) return route.fallback()

    console.error(
      `[refuseLiveWrites] BLOCKED an unrouted ${method} ${url.pathname} — ` +
        `this test would have written to the live trading box. Route it in the test.`
    )
    return route.abort('blockedbyclient')
  })
}
