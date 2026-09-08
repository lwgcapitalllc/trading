/** The instruments you picked last, per broker terminal.
 *
 *  Browser storage rather than the lab database, deliberately: this is a per-machine convenience
 *  in the same class as the collapsed sidebar and the chart's fib ladder, and putting it on the
 *  server would make one person's habits the other person's dropdown.
 *
 *  🔴 **BUCKETED BY SERVER, and that is the whole reason this file is not a one-liner.** A recent
 *  is a click that fills the box, so a recent from a broker you are no longer attached to fills it
 *  with a name the current terminal does not quote — the exact failure the hardcoded list caused,
 *  arriving through a convenience feature. `XAUUSD` is right on Vantage and unanswerable on PU
 *  Prime, which spells it `XAUUSD.p`.
 *
 *  ⚠ **An unknown server reads back NOTHING, never the last bucket.** "Which broker are we on"
 *  being unanswerable is not the same as "we are on the broker we were on this morning", and
 *  offering the old list would be a guess dressed as a memory.
 */

const STORE_KEY = 'lab_instrument_recents'

/** How many to keep per broker. Enough to cover a session's worth of switching between a couple
 *  of pairs and a metal; past that the row wraps and stops being a glance. */
export const MAX_RECENTS = 8

type Buckets = Record<string, string[]>

/** Everything stored, or `{}` when storage is unavailable or holds something unreadable.
 *
 *  ⚠ A corrupt store must not break the form — a browser in private mode has no storage at all,
 *  and a picker that throws there would take the whole modal with it. */
function readAll(): Buckets {
  try {
    const raw = localStorage.getItem(STORE_KEY)
    if (!raw) return {}
    const parsed = JSON.parse(raw)
    if (!parsed || typeof parsed !== 'object' || Array.isArray(parsed)) return {}
    const out: Buckets = {}
    for (const [server, list] of Object.entries(parsed as Record<string, unknown>)) {
      if (!Array.isArray(list)) continue
      out[server] = list.filter((s): s is string => typeof s === 'string' && s.length > 0)
    }
    return out
  } catch {
    return {}
  }
}

function writeAll(buckets: Buckets): void {
  try {
    localStorage.setItem(STORE_KEY, JSON.stringify(buckets))
  } catch {
    // Storage full, or unavailable. A convenience that cannot be saved is not worth an error.
  }
}

/** The recent picks for one broker terminal, most recent first.
 *
 *  Returns `[]` for a blank server — see the header: unknown is not "the usual one". */
export function readRecents(server: string): string[] {
  if (!server) return []
  return (readAll()[server] || []).slice(0, MAX_RECENTS)
}

/** Record a pick. Most recent first, de-duplicated case-insensitively, capped.
 *
 *  ⚠ **De-duplication compares case-insensitively but STORES what was passed**, because the
 *  terminal's spelling is the one that has to go back into the box — `Nikkei225.s` is not
 *  `NIKKEI225.S` to MT5. */
export function pushRecent(server: string, symbol: string): string[] {
  const sym = (symbol || '').trim()
  if (!server || !sym) return readRecents(server)
  const buckets = readAll()
  const rest = (buckets[server] || []).filter((s) => s.toUpperCase() !== sym.toUpperCase())
  const next = [sym, ...rest].slice(0, MAX_RECENTS)
  buckets[server] = next
  writeAll(buckets)
  return next
}

/** Forget one pick — the small × on a recent chip. */
export function removeRecent(server: string, symbol: string): string[] {
  if (!server) return []
  const buckets = readAll()
  buckets[server] = (buckets[server] || []).filter(
    (s) => s.toUpperCase() !== (symbol || '').toUpperCase()
  )
  writeAll(buckets)
  return buckets[server]
}
