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
