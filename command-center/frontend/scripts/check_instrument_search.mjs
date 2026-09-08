#!/usr/bin/env node
/**
 * The instrument picker's ranking and its recents, pinned outside the browser.
 *
 * Run it:  node scripts/check_instrument_search.mjs
 *   Needs nothing running. It is step 11 of `scripts/run_all_tests.sh`.
 *
 * 🔴 WHY IT EXISTS. Three pieces of this frontend have now been wrong on real inputs for as long
 * as they lived inside a component — the trade box's adverse band, the run form's visibility rule,
 * the period window's rebase — and every one was reachable only by a browser. Ranking is the same
 * shape: it is right or wrong on data, it has no pixels in it, and a wrong rank does not look
 * broken. It looks like a list with the instrument you wanted three pages down, which the reader
 * reads as "the broker does not have it".
 *
 * ⚠ The fixture is CUT FROM THE LIVE TERMINAL (2026-09-07), not invented: real spellings, real
 * groups, real trade modes. `EURUSD` is disabled on that account while `EURUSD.p` trades, and
 * `AAPL` and `AAPL.24H` are both quoted — the two cases an invented fixture would have tidied
 * away are the two that decide the tie-breaks.
 *
 * ⚠ The modules are TRANSPILED, never re-implemented. A check that restates the ranking in its
 * own arithmetic passes against a module that disagrees with it, which is the one thing it is for.
 *
 * ⚠ NON-VACUITY IS BY MUTATION, and this map was RUN, not reasoned — which is the only reason it
 * is right. It has now been wrong TWICE from inspection, both times in the flattering direction.
 *
 *   rankOne: drop the BASE tier ............................. 5
 *   rankOne: description word match becomes plain `includes` . 10
 *   rankOne: drop the description branch .................... 9 10 11 17
 *   rankOne: baseName returns the symbol unchanged .......... 5 23
 *   searchInstruments: an empty query is RANKED, not kept .... 12
 *   searchInstruments: an empty query matches nothing ....... 12 13 14 18
 *   searchInstruments: drop the tradable tie-break .......... 6 15 16
 *   searchInstruments: drop the length tie-break ............ 6 7 15
 *   searchInstruments: drop the alphabetical compare ........ 15
 *   searchInstruments: ranked path ignores the class filter .. 16
 *   searchInstruments: ranked path reports `hidden` as 0 ..... 17
 *   searchInstruments: drop the null-universe guard ......... 19 (throws)
 *   isQuotedVerbatim: compare on the base name .............. 21
 *   isQuotedVerbatim: a null universe answers true .......... 22
 *   isQuotedVerbatim: nothing is ever quoted ................ 20
 *   pushRecent: store under a constant key .................. 24 26 28 29 30
 *   pushRecent: de-duplicate case-SENSITIVELY ............... 28
 *   pushRecent: drop the cap ................................ 30
 *   readRecents: a blank server returns the first bucket .... 27
 *   readAll: drop the corrupt-store guard ................... 31 (throws)
 *
 * 🔴 THREE MUTATIONS SURVIVED THE FIRST VERSION OF THIS FILE, and every one was fixed rather than
 * documented away:
 *
 *   - Dropping the BASE tier changed NOTHING. A base name is always a prefix of the symbol, so
 *     every fixture symbol fell through to PREFIX and landed in the same place. The tier is only
 *     observable against a symbol that starts with the query WITHOUT the query being its base —
 *     `TSLA.24H` against `TSLAUSD` — and the fixture had no such pair. It does now.
 *   - The description-word rule was asserted with the phrase `ARK Innovation`, which matches as a
 *     word AND as a substring. A case whose input cannot separate the two behaviours it names is
 *     the arithmetic version of a scale of 1: green either way. Case 10 uses a real pair instead.
 *   - Case 6 originally claimed to pin the tradable tie-break while asserting on two ETFs that are
 *     BOTH restricted on this account, so it asserted nothing about tradability at all. `EURUSD`
 *     (disabled) against `EURUSD.p` is the pair that can see it.
 *
 * 🔴 AND THREE MORE WENT UNCOVERED WHEN A LATER FIX REROUTED THEIR CASES. Keeping the server's
 * order for an empty query moved the class-filter and limit checks onto the early-return path,
 * where a mutation of the RANKED path can no longer reach them — and the alphabetical compare
 * became unobservable once the fixture was sorted the way the server sends it, because a stable
 * sort returning 0 then preserves the order the compare would have produced. Cases 15-17 exist
 * for exactly those three. **A fix that reroutes a case can silently un-cover the branch that
 * case used to exercise, and re-running the whole map is the only thing that shows it.**
 *
 * ⚠ ONE BRANCH WAS DELETED RATHER THAN COVERED. `rankOne` had a "base name starts with the query"
 * tier that no mutation could kill, because it is unreachable: the base is a prefix of the symbol,
 * so the PREFIX check above it has always already returned. Unreachable code that reads like a
 * rule is worse than no rule — a reader takes it for a covered branch.
 *
 * ⚠ Cases 1 2 3 4 8 25 are killed by no mutation above and are named rather than quietly left in.
 * Each is a DIRECTION check — the headline behaviour that must keep working while the tiers move
 * beneath it, and the negative half of a case whose positive half is pinned elsewhere.
 */
import { readFileSync, writeFileSync, mkdtempSync } from 'node:fs'
import { join, dirname } from 'node:path'
import { tmpdir } from 'node:os'
import { fileURLToPath, pathToFileURL } from 'node:url'
import { transformSync } from 'esbuild'

const HERE = dirname(fileURLToPath(import.meta.url))
const DIR = mkdtempSync(join(tmpdir(), 'instrsearch-'))

async function load(relPath, outName) {
  const src = join(HERE, '..', 'src', 'lib', relPath)
  const js = transformSync(readFileSync(src, 'utf8'), { loader: 'ts', format: 'esm' }).code
  const out = join(DIR, outName)
  writeFileSync(out, js)
  return import(pathToFileURL(out).href)
}

const { searchInstruments, isQuotedVerbatim, baseName } = await load(
  'instrumentSearch.ts',
  'instrumentSearch.mjs'
)

const FIXTURE = JSON.parse(
  readFileSync(join(HERE, '..', 'tests', 'fixtures', 'instrument-universe.json'), 'utf8')
)
const ALL = FIXTURE.symbols

let failed = 0
let n = 0
const check = (why, got, want) => {
  n += 1
  const g = JSON.stringify(got)
  const w = JSON.stringify(want)
  if (g !== w) {
    failed += 1
    console.log(`  \x1b[31m✗\x1b[0m #${n} ${why}\n      got ${g}\n      want ${w}`)
  }
}

const top = (q, k = 1, opts) =>
  searchInstruments(ALL, q, opts)
    .matches.slice(0, k)
    .map((s) => s.symbol)

// 1-2. 🔴 THE CASE THE WHOLE TIER EXISTS FOR. The broker spells gold with a suffix and the reader
// types the base name. Under a plain prefix rank that lands wherever the alphabet puts it.
check('XAUUSD finds the broker’s XAUUSD.p first', top('XAUUSD'), ['XAUUSD.p'])
check('lowercase types the same', top('xauusd'), ['XAUUSD.p'])

// 3. DIRECTION: an exact hit outranks a base hit, even when the exact one is disabled on this
// account. Typing a name in full means that name; the row says it is disabled.
check('an exact name wins its own query', top('EURUSD', 2), ['EURUSD', 'EURUSD.p'])

// 4. Both are quoted, and the shorter one is the plain instrument.
check('AAPL before AAPL.24H', top('AAPL', 2), ['AAPL', 'AAPL.24H'])

// 4b. 🔴 THE CASE THAT WAS MISSING, and its absence left a whole ranking tier dead in green.
// `TSLA.24H` has TSLA as its BASE; `TSLAUSD` merely starts with it and is one character SHORTER.
// Drop the base tier and both fall to plain prefixes, where the length tie-break puts the
// tokenised product above Tesla's own CFD. The first fixture had no symbol of this shape, so the
// tier could be deleted outright with 25 cases still passing.
check('a base-name match beats a shorter plain prefix', top('TSLA', 3), [
  'TSLA',
  'TSLA.24H',
  'TSLAUSD',
])

// 5. 🔴 THE TRADABLE TIE-BREAK, on inputs that can actually see it. The first version of this case
// named tradability while asserting on two ETFs that are BOTH restricted on this account — so
// "sorts the tradable one first" and "ignores tradability entirely" were the same assertion, and
// the tie-break could be deleted with every case still green. `EURUSD` is disabled here and
// `EURUSD.p` trades: at equal rank the disabled one must sink, even though it is SHORTER and would
// otherwise win on length.
check('a disabled symbol sinks below tradable ones at the same rank', top('US', 4), [
  'BTCUSD',
  'SPCXUSD',
  'TSLAUSD',
  'EURUSD.p',
])

// 6. Same rank, same tradability — the shorter symbol is the more likely target.
check('equal rank sorts short-first', top('AU', 2), ['TSLAUSD', 'GAUUSD.p'])

// 6b. …and alphabetically once length ties too.
check('then alphabetically', top('ARK', 2), ['ARKG', 'ARKK'])

// 7-9. The description is the half that makes a name searchable by a person.
check('a company name finds its ticker', top('APPLE', 2), ['AAPL', 'AAPL.24H'])
// 🔴 ALSO MISSING, and for the same reason: the first version asserted a phrase that matched as a
// word AND as a substring, so it could not tell the two rules apart. "Space Exploration
// Technologies Corp." has a WORD starting `CO`; "Bitcoin" merely contains those letters. Only a
// pair like this makes the word boundary observable.
check('a description WORD beats a description substring', top('CO', 4), [
  'COPPER-Cs',
  'AMAZON',
  'SPCXUSD',
  'BTCUSD',
])
check('GOLD reaches every gold instrument', searchInstruments(ALL, 'GOLD').matches.length, 3)

// 10a. 🔴 FOUND BY OPENING THE PICKER, NOT BY READING IT. The backend orders the universe liquid
// class first; ranking an empty query flattened every symbol to one tier and handed the list to the
// length tie-break, so the panel opened on `A`, `AA`, `AC`, `ABT` — the shortest US share tickers
// on the terminal — for somebody running a gold strategy. Every rule involved was individually
// correct. This pins the ORDER an empty box opens on.
check('an empty query opens on the liquid classes, not the shortest tickers', top('', 4), [
  'EURUSD',
  'EURUSD.p',
  'GBPUSD.p',
  'GAUUSD.p',
])

// 10-11. An empty query is the whole class, not a blank panel.
check('an empty query lists everything', searchInstruments(ALL, '').matches.length, ALL.length)
check('a class with an empty query lists that class', top('', 9, { assetClass: 'Metals' }), [
  'GAUUSD.p',
  'XAGUSD.p',
  'XAUEUR.p',
  'XAUUSD.p',
])

// 11a-c. 🔴 THE RANKED PATH'S OWN FILTER, CAP AND ALPHABETICAL TIE-BREAK, and all three were left
// UNCOVERED by the empty-query fix above — the class and limit cases below it had quietly moved
// onto the early-return path, where a mutation of the ranked code cannot reach them. Found by
// re-running the whole mutation map after the restructure rather than adjusting the case numbers
// by hand. **A fix that reroutes a case can silently un-cover the branch it used to exercise.**
// `GBPUSD.p` sits BEFORE `GAUUSD.p` in the served order (different classes), so their order here
// can only come from the alphabetical compare.
check('the ranked path sorts equals alphabetically', top('USD', 6).slice(3), [
  'EURUSD.p',
  'GAUUSD.p',
  'GBPUSD.p',
])
check('the ranked path honours the class filter', top('USD', 9, { assetClass: 'Forex' }), [
  'EURUSD.p',
  'GBPUSD.p',
  'EURUSD',
])
const rankedCap = searchInstruments(ALL, 'USD', { limit: 3 })
check('the ranked path reports what it hid', [rankedCap.matches.length, rankedCap.hidden], [3, 8])

// 12. A truncated list and a short one look identical, and one of them means keep typing.
const capped = searchInstruments(ALL, '', { limit: 5 })
check('a truncated list reports what it hid', [capped.matches.length, capped.hidden], [5, 17])

// 13. Nothing loaded is not a crash and not a match.
check('a null universe is empty, never an exception', searchInstruments(null, 'XAUUSD'), {
  matches: [],
  hidden: 0,
})

// 14-15. 🔴 The guard that stops the broker rewrite mangling a picked name. `XAUUSD` is NOT quoted
// by this terminal — `XAUUSD.p` is — so the base name must not answer true, or the rewrite would
// stand down for a name the terminal has never heard of.
check('the terminal’s exact spelling is quoted', isQuotedVerbatim(ALL, 'xauusd.p'), true)
check('its base name is not', isQuotedVerbatim(ALL, 'XAUUSD'), false)
check('and nothing is quoted when nothing loaded', isQuotedVerbatim(null, 'XAUUSD.p'), false)
check('baseName strips the broker suffix', baseName('TSLA.24H'), 'TSLA')

// ── Recents ──────────────────────────────────────────────────────────────────
// A tiny storage stub. The module must survive a store that is missing, full or holding rubbish,
// so those are cases rather than assumptions.
const store = new Map()
globalThis.localStorage = {
  getItem: (k) => (store.has(k) ? store.get(k) : null),
  setItem: (k, v) => store.set(k, v),
}

const { readRecents, pushRecent, removeRecent, MAX_RECENTS } = await load(
  'instrumentRecents.ts',
  'instrumentRecents.mjs'
)

const PU = 'PUPrime-Demo'
const VANTAGE = 'VantageMarkets-Demo'

pushRecent(PU, 'XAUUSD.p')
pushRecent(PU, 'EURUSD.p')
check('most recent first', readRecents(PU), ['EURUSD.p', 'XAUUSD.p'])

// 18. 🔴 A recent is a click that FILLS THE BOX, so one from another broker fills it with a name
// this terminal does not quote — the hardcoded-list failure arriving through a convenience.
check('another broker’s recents are not offered', readRecents(VANTAGE), [])
pushRecent(VANTAGE, 'XAUUSD')
check('each broker keeps its own', [readRecents(VANTAGE), readRecents(PU).length], [['XAUUSD'], 2])

// 17. Unknown is not "the one we were on this morning".
check('a blank server reads back nothing', readRecents(''), [])

// 19. De-duplicate case-insensitively, but keep the spelling that was passed: `Nikkei225.s` is
// not `NIKKEI225.S` to MT5.
pushRecent(PU, 'xauusd.p')
check('a repeat moves to the front without duplicating', readRecents(PU), ['xauusd.p', 'EURUSD.p'])

// 20. The cap, or the row stops being a glance.
for (let i = 0; i < MAX_RECENTS + 4; i += 1) pushRecent(PU, `SYM${i}`)
check('the row is capped', readRecents(PU).length, MAX_RECENTS)

check('one can be forgotten', removeRecent(PU, `SYM${MAX_RECENTS + 3}`).length, MAX_RECENTS - 1)

// A store holding rubbish must not take the modal with it.
store.set('lab_instrument_recents', 'not json')
check('a corrupt store reads back empty', readRecents(PU), [])

if (failed) {
  console.log(`\x1b[31m✗ instrument search: ${failed}/${n} failed\x1b[0m`)
  process.exit(1)
}
console.log(`\x1b[32m✓\x1b[0m instrument search: ${n} cases`)
