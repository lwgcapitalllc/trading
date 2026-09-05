/**
 * Shared fixture guards for the browser suites.
 *
 * 🔴 WHY THIS EXISTS. Six spec files pin a LITERAL run id (`const RUN = '997c14cc53bc'` and
 * friends) because what they check needs a run carrying particular LAYERS — a VWAP series, a fib
 * leg, candle reversals — and "any completed run" cannot supply that. That is a legitimate reason
 * to name a row, and it is not the problem.
 *
 * The problem is what happens the day the named row leaves the lab. On 2026-08-16
 * `chart-paging.spec.ts` lost both its checks because `211384ddbea4` had been deleted: the run
 * endpoint 404s, so the price chart never renders, `Go to date` never appears, and the failure is
 * a 120-second timeout pointing squarely at the paging code — which was fine. **A test that fails
 * on a day nothing is wrong is indistinguishable from a regression until somebody reads it**, and
 * this folder has now been bitten three times (`tuning.spec.ts` lost eight checks the same way,
 * `backtests.spec.ts`'s millions check before that).
 *
 * `requireRun` does not remove the pin — it makes the pin ANNOUNCE ITSELF. One await at the top of
 * a suite turns a mystery timeout into a sentence naming the run, the file and the fix.
 *
 * ⚠ It is a diagnosis, not a repair. A suite whose fixture has died is still red and still needs a
 * human to re-point it at a run carrying the same layers. The only thing this changes is that the
 * next reader is sent to the lab instead of to the feature.
 *
 * ⚠ Prefer RESOLVING a run over naming one wherever the check allows it — `chart-paging.spec.ts`
 * and `period-filter.spec.ts` both do, because they need a shape ("longest intraday python run",
 * "any run with 20 dated trades") rather than a specific book.
 */
export const API = 'http://localhost:8000'

export async function getJson<T>(path: string): Promise<T> {
  const res = await fetch(API + path)
  if (!res.ok) throw new Error(`backend not answering for ${path} (${res.status}) — is it running?`)
  return res.json() as Promise<T>
}

/**
 * Fail FAST and by NAME when a suite's pinned run is gone.
 *
 * @param runId  the literal this suite is built on
 * @param needs  what the replacement has to carry, in the words of whoever pinned it — this is the
 *               half a bare "not found" cannot supply, and the half the next reader actually needs
 */
export async function requireRun(runId: string, needs: string): Promise<void> {
  const res = await fetch(`${API}/backtests/runs/${runId}`).catch(() => null)
  if (res?.ok) return
  if (!res) {
    throw new Error(
      `The backend is not answering on ${API} — start it with ./start.sh before running this suite.`
    )
  }
  throw new Error(
    `FIXTURE GONE, not a regression: run ${runId} is no longer in the lab (HTTP ${res.status}).\n` +
      `This suite pins that run because it needs ${needs}.\n` +
      `Re-point its RUN constant at a run that carries the same, then re-read any date constants ` +
      `beside it — they are tied to that run's own data and do not travel.`
  )
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
