/** Type-ahead over the broker's own instrument list — the ranking, with no React in it.
 *
 *  🔴 WHY IT IS A MODULE AND NOT A `useMemo` INSIDE THE PICKER. The three pieces of frontend logic
 *  this repo has been bitten by — the trade box's adverse band, the run form's visibility rule,
 *  the period window's rebase — were all correct-looking code living inside a component, reachable
 *  only by a browser, and each was wrong on real inputs for as long as it lived there. Ranking is
 *  the same shape: it is right or wrong on data, it has no pixels in it, and a wrong rank is not a
 *  broken screen — it is a plausible list with the instrument you wanted three pages down.
 *  `scripts/check_instrument_search.mjs` drives this file with nothing running.
 *
 *  ⚠ **The broker's suffix is why a plain `startsWith` is not enough.** PU Prime quotes gold as
 *  `XAUUSD.p`, and a reader types `XAUUSD`. Under a bare prefix rank that lands wherever the
 *  alphabet puts it; the base-name tier below pulls it to the top, where an exact-looking match
 *  belongs.
 */

/** One instrument as the backend serves it. Mirrors `models.BrokerSymbol`. */
export interface BrokerSymbol {
  symbol: string
  description: string
  /** The broker's own folder name, suffix trimmed — e.g. `Gold`, `Equity-US`, `US.24H`. */
  broker_group: string
  /** That group read through keywords — `Metals`, `Shares` — or the group itself when the
   *  keywords did not recognise it. The two being EQUAL is the honest fallback, not a bug. */
  asset_class: string
  /** True only when the account may OPEN a position. Still listed and still backtestable when
   *  false: a restriction on the account says nothing about the instrument's history. */
  tradable: boolean
  trade_mode_label: string
  digits: number
  contract_size: number
  volume_min: number
  volume_step: number
  /** The venue lot ceiling. Part of what a run is measured on, so it travels with the symbol. */
  volume_max: number
}

export interface BrokerSymbolClass {
  label: string
  count: number
}

/** What the terminal answered, or an honest statement that it could not be asked.
 *
 *  🔴 `symbols` is `null` when `available` is false, NEVER `[]`. A caller that renders an empty
 *  array as "this broker offers nothing" would be describing an outage as a product decision. */
export interface BrokerUniverse {
  available: boolean
  reason: string | null
  server: string
  account: number | null
  fetched_at: string | null
  count: number | null
  total_on_terminal: number | null
  classes: BrokerSymbolClass[]
  symbols: BrokerSymbol[] | null
}

/** The base name a broker's suffix hangs off — `XAUUSD.p` → `XAUUSD`, `TSLA.24H` → `TSLA`.
 *
 *  ⚠ Used for MATCHING only. Never send this to a terminal: the suffix is the name it quotes. */
export function baseName(symbol: string): string {
  return symbol.split('.')[0]
}

/** Ranking tiers, best first. Exported so the check can name them rather than assert on integers.
 *
 *  ⚠ **The ORDER is the behaviour.** `EXACT` above `BASE` above `PREFIX` is what puts `XAUUSD.p`
 *  at the top when somebody types `XAUUSD`, and description matches below every symbol match is
 *  what stops "Gold US Dollar" outranking a ticker the reader typed in full. */
export const RANK = {
  EXACT: 0,
  BASE: 1,
  PREFIX: 2,
  CONTAINS: 3,
  DESC_WORD: 4,
  DESC_CONTAINS: 5,
  NONE: 6,
} as const

// 🔴 **A "base name starts with the query" tier was written here and DELETED as unreachable.**
// The base is always a prefix of the symbol, so `base.startsWith(q)` implies `symbol.startsWith(q)`
// and the PREFIX check above it had already returned. It read like a rule, it could never fire,
// and no mutation could kill it — which is the shape a reader mistakes for a covered branch.

/** How well one instrument answers a query. `RANK.NONE` means it does not. */
export function rankOne(sym: BrokerSymbol, query: string): number {
  const q = query.trim().toUpperCase()
  if (!q) return RANK.NONE
  const s = sym.symbol.toUpperCase()
  const b = baseName(s)
  if (s === q) return RANK.EXACT
  if (b === q) return RANK.BASE
  if (s.startsWith(q)) return RANK.PREFIX
  if (s.includes(q)) return RANK.CONTAINS
  const d = (sym.description || '').toUpperCase()
  if (!d) return RANK.NONE
  // A word boundary, so typing `ARK` surfaces "ARK Genomic Revolution" ahead of every description
  // that merely contains those three letters inside a longer word.
  if (d.split(/[^A-Z0-9]+/).some((w) => w.startsWith(q))) return RANK.DESC_WORD
  if (d.includes(q)) return RANK.DESC_CONTAINS
  return RANK.NONE
}

export interface SearchOptions {
  /** Show only this asset class. Empty or undefined means every class. */
  assetClass?: string
  /** Most rows to return. The terminal carries over a thousand instruments and a dropdown that
   *  renders all of them is a dropdown that stutters on every keystroke. */
  limit?: number
}

export interface SearchResult {
  matches: BrokerSymbol[]
  /** How many matched but were cut by `limit`. Shown to the reader, because a silently truncated
   *  list and a genuinely short one look identical — and one of them means "keep typing". */
  hidden: number
}

/** The rows to show for a query, best first.
 *
 *  ⚠ **An EMPTY query is not an empty result** — it is the whole class, alphabetically. Somebody
 *  who has picked `Metals` and typed nothing wants to see the five metals, not a blank panel.
 *
 *  ⚠ **Ties break on TRADABLE first.** 59 of PU Prime's 1,085 are disabled, close-only or
 *  long-only; they stay in the list because their history is still replayable, but a symbol the
 *  account can actually open belongs above one it cannot. */
export function searchInstruments(
  all: BrokerSymbol[] | null,
  query: string,
  opts: SearchOptions = {}
): SearchResult {
  if (!all) return { matches: [], hidden: 0 }
  const limit = opts.limit ?? 60
  const cls = opts.assetClass || ''
  const q = query.trim()

  // 🔴 **AN EMPTY QUERY KEEPS THE SERVER'S ORDER AND IS NOT SORTED, and that was found by opening
  // the thing.** The backend orders the universe by asset class, liquid first, precisely so the
  // panel opens on the instruments anybody here actually trades. Ranking an empty query gave every
  // symbol the same tier, which handed the whole list to the length tie-break — so the picker
  // opened on `A`, `AA`, `AC`, `ABT`: the shortest US share tickers on the terminal, offered first
  // to somebody running a gold strategy. Every individual rule was right and the composition was
  // useless.
  // ⚠ **The tie-breaks are for RANKED results only.** They answer "which of these matches best",
  // and with nothing typed there is no match to be best.
  if (!q) {
    const inClass = cls ? all.filter((s) => s.asset_class === cls) : all
    return {
      matches: inClass.slice(0, limit),
      hidden: Math.max(0, inClass.length - limit),
    }
  }

  const scored: Array<{ sym: BrokerSymbol; rank: number }> = []
  for (const sym of all) {
    if (cls && sym.asset_class !== cls) continue
    const rank = rankOne(sym, q)
    if (rank === RANK.NONE) continue
    scored.push({ sym, rank })
  }

  scored.sort((a, b) => {
    if (a.rank !== b.rank) return a.rank - b.rank
    if (a.sym.tradable !== b.sym.tradable) return a.sym.tradable ? -1 : 1
    if (a.sym.symbol.length !== b.sym.symbol.length) {
      return a.sym.symbol.length - b.sym.symbol.length
    }
    return a.sym.symbol.localeCompare(b.sym.symbol)
  })

  return {
    matches: scored.slice(0, limit).map((x) => x.sym),
    hidden: Math.max(0, scored.length - limit),
  }
}

/** Does the attached terminal quote this exact name?
 *
 *  🔴 **This is what stops the broker rewrite mangling a name the reader picked.** The Run form
 *  appends the selected broker's suffix to whatever is in the box — right for the 64 forex and
 *  metal names PU Prime spells with one, and wrong for the other 1,021, where it turns `AAPL`
 *  into `AAPL.p`, a symbol the terminal has never quoted. A name the terminal itself listed needs
 *  no rebasing, and asking the list is a measurement where a "did the user pick it" flag would be
 *  a memory. */
export function isQuotedVerbatim(all: BrokerSymbol[] | null, symbol: string): boolean {
  if (!all || !symbol) return false
  const s = symbol.trim().toUpperCase()
  return all.some((x) => x.symbol.toUpperCase() === s)
}
