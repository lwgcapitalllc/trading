# CLAUDE.md — News (Economic-Calendar) Engine Subsystem

**Purpose:** Turn the clock into news EVENTS a bot can gate on — for each closed bar, report whether
trading is inside a **blackout** around a scheduled economic release, which release is *coming up*,
*happening now*, or *just finished*, and whether this bar even has calendar data. The signal is the
flag ("in_blackout", "FOMC in 12 min", "NFP just released"), not a decision — the bot decides to
skip or trade.
**Scope:** Economic-calendar (scheduled macro releases: NFP/CPI/FOMC/PCE/ISM/EIA…) blackout gating +
coverage tracking. NOT headline/sentiment NLP, NOT single-stock earnings, NOT trading decisions, NOT
position sizing, NOT UI. The engine emits facts; a bot owns the policy and the skip/trade call.
**Status:** Built 2026-07-05. Unit-tested (47 tests, green) + validated live end-to-end against the
real Forex Factory calendar (live weekly feed + a real Feb-2025 history backfill → cache → engine
blackout). **Off the roadmap and NOT a Pine port** — see "Validation".
**Last reviewed:** 2026-09-01 — the cache had gone a month stale on this machine and the backend's
readiness banner was the only thing that noticed, because **nothing on either machine was topping
the cache up**. `backfill.py` gained `--top-up` (+ `--if-stale`) and `./go` now runs it. Engine core
unchanged. See "Keeping the cache current". Earlier:
2026-08-02 — no engine code changed; a **third consumer** was recorded. The
command center now checks this cache at backend startup (`services/readiness.py`) and warns when it
is empty or stops more than 30 days back, because the honest-coverage rule is invisible from
outside: an unbackfilled range makes the lab's News & Holiday filter *inert*, which is
indistinguishable from a broken one. Read-only — no fetch, no write, no policy. Earlier:
2026-07-29 — the FF history scraper's browser fingerprint is now a fallback chain
(Cloudflare started 403-ing every `chrome*` profile); 2021-01 → 2026-07 backfilled (27,363 events)

---

## Why this one is different (read first)

Every other engine in `engines/` is a **line-by-line port of `indicators/engines/mpc_assistant.pine`**,
validated at **100% Pine parity**. This one has **no Pine source** — the economic calendar comes
from an external API, not the chart. So:

- It cannot be, and is not, Pine-parity-validated. Validation = unit tests on the pure core + a
  **live feed smoke test** (`tools/fetch_smoke.py`) + a **real history backfill** proven to gate a
  past bar. That is the deliberate, one-time break from the roadmap pattern.
- Its *shape* still matches the house style: **time-driven** (input = the bar's epoch-ms UTC
  timestamp, exactly like `engines/sessions/`), streaming (one closed bar per `update()`), emits
  **events, not visuals**, single canonical implementation, `algos/shared/` shim when a bot first
  consumes it.

It is a **macro** calendar keyed by currency, so it serves FX, gold and index/rates futures alike
(pick the currency per instrument). It does **not** carry single-stock earnings or unscheduled
headlines.

---

## Key paths

```
engines/news/
├── engine.py       ← NewsEngine: the pure, streaming state machine (events + policy -> per-bar out)
├── types.py        ← Impact, NewsEvent, NewsPolicy, NewsEvents (the per-bar output)
├── store.py        ← EventStore: local JSON CACHE of fetched events (+ covered date ranges)
├── sources/
│   ├── base.py                 ← CalendarSource interface + FetchResult (events + covered ranges)
│   ├── forex_factory.py        ← ForexFactorySource: free faireconomy JSON feed (current week, no dep)
│   ├── forex_factory_history.py← ForexFactoryHistorySource: scrapes the FF WEBSITE for any month
│   │                              (past Cloudflare via curl_cffi) — historical backfill
│   └── tradingview.py          ← TradingViewSource: free TradingView calendar API, arbitrary date
│                                  window + `actual` results + a `category` label — powers the live tab
├── data/           ← the cache (events.json) — GIT-IGNORED (fetched data, not source)
├── tools/
│   ├── refresh.py      ← live pipeline: pull the free weekly feed + upsert the cache (schedule it)
│   ├── backfill.py     ← history: fetch missing months from the website into the cache (curl_cffi)
│   │                     `--top-up` resumes from the cache's own coverage end — the scheduled one
│   └── fetch_smoke.py  ← manual live-feed sanity check (stands in for the Pine parity harness)
├── tests/          ← test_engine.py, test_store.py, test_forex_factory.py, test_history_parser.py,
│                     test_tradingview.py (offline parser tests on a saved sample),
│                     test_backfill_top_up.py (the top-up's decisions — no network)
├── __init__.py     ← public API
└── CLAUDE.md       ← this file
```

Runnable scripts live in `tools/` (not the package root) **on purpose**: a script run from inside the
package dir puts `engines/news/` on `sys.path[0]`, and `news/types.py` would then shadow the stdlib
`types` module (circular-import crash). Keep runnable scripts in `tools/`.

---

## The three layers (and why they are split)

1. **Pure core — `NewsEngine` (engine.py).** No network, no clock, no files. Takes an already-loaded
   `NewsEvent` list + a bot-owned `NewsPolicy` (+ optional covered ranges) and answers each bar.
   Deterministic and testable, and a **backtest feeds it a historical list exactly as live feeds it a
   fetched one** — that is the whole reason fetch is kept out of it.
2. **Sources — `sources/` (`CalendarSource`).** Three implementations feed the same shape; all
   normalise to plain `NewsEvent`s (UTC epoch-ms, currency code, `Impact` enum):
   - `ForexFactorySource` — the **free faireconomy JSON feed**, current week only, **zero deps**.
     For live/forward gating (`tools/refresh.py`). Carries bank holidays (the blackout filter needs
     them); no per-event `actual`.
   - `ForexFactoryHistorySource` — scrapes the **FF website** for any month (parses the embedded
     `calendarComponentStates`, using each event's `dateline` = UTC unix seconds). The site is
     behind Cloudflare, so it needs `curl_cffi` (browser impersonation) — **lazy-imported and
     isolated here**, so the core + live feed stay pure-stdlib. For historical backfill
     (`tools/backfill.py`). **The browser fingerprint is a FALLBACK CHAIN (`_PROFILES`), never one
     hardcoded profile** — Cloudflare blocks them per-family and changes its mind: on 2026-07-28
     every `chrome*` profile started returning 403 while `safari18_0`/`firefox133` still returned
     the page, the exact reverse of when this source was written. `_get` walks the chain and
     remembers the first profile that answers 200, so a 66-month backfill pays for the search once;
     `impersonate=` still pins one explicitly, and the chain rescues it if that one is refused. If
     the WHOLE chain fails, upgrade `curl_cffi` and put its newer profiles at the front.
   - `TradingViewSource` — the **free TradingView calendar API** (`economic-calendar.tradingview.com`,
     needs an `Origin` header, no key). Unlike FF it takes an **arbitrary date window**, carries the
     released **`actual`** result, and tags each row with a **`category`** (Labor, Prices, …). No bank
     holidays. `fetch()` = current week (the parameterless interface); `fetch_window(from,to)` = the
     range the live tab asks for. **The live News Calendar tab's source** — it does NOT write the
     shared cache (`store.py`), it's read fresh per request. Parser is pure/stdlib (`parse_result`),
     tested offline on a saved sample.
   Swap in a paid provider later as a fourth file; nothing downstream changes.
3. **Cache — `EventStore` (store.py).** A local JSON cache of everything fetched, de-duped by
   `(time, currency, title)`, tracking the date ranges covered. Historical events are static, so a
   month is fetched **once** and read forever; `backfill.py` skips months already cached. The
   store's earliest covered ms is the backtest "news starts here" boundary.

---

## What it computes (semantics)

Per bar (`NewsEvents`):

- **`in_blackout`** — THE gate. True iff `has_coverage` is True AND this bar is inside a relevant
  timed event's `[event - pre_minutes, event + post_minutes]` window — **plus** a matching **bank
  holiday**'s whole day, but only if the bot opted in with `block_holidays=True`. Overlapping windows
  merge into one continuous blackout.
- **`has_coverage`** — does this bar's timestamp fall inside a fetched date range? Drives the
  "trade normally where we have no news data" behaviour. See coverage rules below.
- **`is_holiday` / `active_holiday`** — this bar's day is a bank holiday for a currency the policy
  cares about, and the holiday event making it so. **Always reported** (independent of
  `block_holidays`) so the strategy can decide for itself whether a holiday means "stand aside".
- **Phases** — `next_event`/`minutes_to_next` (coming up), `active_event` (the window we are inside
  now; highest-impact on overlap), `last_event`/`minutes_since_last` (finished). Timed events only —
  holidays report via `is_holiday`.
- **Edges** — `entered_blackout` / `exited_blackout` (state flipped this bar), `released` (relevant
  events whose time fell in `(prev bar, this bar]` — i.e. just went live).

**Relevance** is the bot-owned `NewsPolicy`. A *timed* event counts iff `impact >= min_impact` and
(if `currencies` is non-empty) its currency is in `currencies`, and blacks out ±`pre`/`post` minutes.
A *bank holiday* (`ev.is_holiday`, from FF's "Holiday" folder) for a matching currency is **always
reported** via `is_holiday`; it is folded into `in_blackout` (whole UTC day, day-granular) **only if
the bot passes `block_holidays=True`** — the engine reports, the strategy decides. `NewsPolicy.usd()`
(alias `.gold()`) = high-impact USD, ±30 min, **holidays reported but not blocked** (default) — the
right default for gold/ES/NQ/CL/bonds (widen `currencies` per instrument: EUR for the DAX, GBP for
the FTSE…; pass `block_holidays=True` to also auto-block them).

### Coverage rules (the "news starts here" boundary)

`covered_ranges` passed to `NewsEngine` decides coverage — it is NOT derived from the events
(a quiet-but-fetched week must not read as a data gap):

| `covered_ranges` | meaning | `has_coverage` | `coverage_start_ms` |
|---|---|---|---|
| `None` (omitted) | coverage unknown → don't gate | always `True` | `None` |
| a list of `(lo,hi)` | gate strictly on these (the real flow) | inside a range | earliest `lo` |
| `[]` | known-empty (empty store) | always `False` | `None` |

In the real flow you always pass `EventStore.load()`'s ranges. Before the earliest covered ms,
`has_coverage` is False → `in_blackout` forced False → **a backtest trades normally with the filter
off**. `coverage_start_ms` is exactly where a backtest UI draws its vertical "news data starts here"
line. **That line is a command-center backtest-lab (UI) job — this engine only exposes the boundary
fact; it draws nothing.** (Follow-up, not built here.)

---

## Public API

```python
from news import NewsEngine, NewsPolicy, NewsEvent, NewsEvents, Impact
from news import EventStore

events, covered = EventStore().load()  # the cache: events + fetched date ranges
eng = NewsEngine(events, policy=NewsPolicy.usd(), covered_ranges=covered)

for bar in feed:  # closed bars; timestamp = epoch ms, UTC
    out = eng.update(bar.index, bar.timestamp_ms)
    if out.has_coverage and out.in_blackout:  # bot's gate
        continue  # stand aside around the release
    # ...trade. Where has_coverage is False (before the cache begins) the filter is inert.

eng.coverage_start_ms  # the backtest "news starts here" boundary
eng.set_events(new_events, covered_ranges=new_ranges)  # live refresh without losing edge state
```

Data pipelines (both write the one cache; run from repo root):
```bash
python engines/news/tools/refresh.py                       # live: current week, no deps
python engines/news/tools/backfill.py --from 2021-01       # first fill: scrape months -> cache (curl_cffi)
python engines/news/tools/backfill.py --top-up --if-stale  # keep it current — what ./go runs
```
`backfill.py` only fetches months not already cached (static history), so the first run over a long
range does the work once and later runs are instant.

---

## Keeping the cache current (2026-09-01)

**The cache does not maintain itself, and until this date NOTHING maintained it.** It was filled by
hand to 2026-07-31, and on 2026-09-01 the backend's startup banner said *"news calendar cache ends
2026-07-31 (32d ago) — trades after that date come back untagged, not unaffected"*. That banner is
the readiness check working exactly as designed. **It was also the only thing in the whole system
that knew**, which is a reporting layer doing a maintenance layer's job.

**Top it up with the tool, and do not hand it a date:**

```bash
python engines/news/tools/backfill.py --top-up             # resume from the cache's coverage end
python engines/news/tools/backfill.py --top-up --if-stale  # ...and do nothing if it is current
```

`--top-up` reads its own start month off `EventStore.coverage_end_ms()`, so nothing has to remember
when the cache was last filled. ⚠ **It REFUSES on an empty cache rather than defaulting to a start
year** — the repo rule that a default start date is a hardcode with better manners, failing quietly
in the direction nobody checks. An empty cache needs a deliberate `--from`.

⚠ **`--if-stale` answers from the cache alone and never touches the network**, so a launcher can ask
on every run for nothing. It is also why the answer is usually *no*: a fetched month records the
WHOLE month as covered, so coverage normally runs to month end and the top-up genuinely fires about
once a month.

⚠ **The start month is clamped to the CURRENT month even when coverage already runs past today.**
The current month is the one still publishing its released figures, so a resume point after it would
freeze those rows at whatever they were on the day it was fetched.

**MEASURED 2026-09-01:** stale by one month → 2 months fetched, 750 events, **3.7s** end to end.
Already current → **1.1s**, no network (that second is python starting and reading a 28k-event JSON).

### 🔴 The launcher had been asking the wrong question for a month

`./go` step 6 checked that `data/events.json` EXISTS. The file has existed since July, so every
launch printed *"news calendar present"* while the calendar inside it stopped four weeks back.
**Presence is not freshness, and the check that reads a file's existence cannot tell you a thing
about the dates inside it.** It now runs `--top-up --if-stale`, and reports *current*, *topped up*,
or a warning that names what went wrong. It is never fatal: coverage that stops early leaves the app
completely usable, and killing a launcher over a git-ignored data file would be the worse trade.

🔴 **The first version of that wiring reproduced this engine's own oldest bug and was caught by
RUNNING it, not by reading it.** It decided worked-or-not by grepping the tool's output for
*"nothing to top up"* — and the tool's REFUSAL on an empty cache contained that same phrase, so a
machine with no calendar at all was told its calendar was current. **A failure and a success arrived
as the same value**, which is rule 1 of the monorepo, one level up from where it usually bites. The
launcher now branches on the EXIT CODE, which is structural, and the two messages were pulled apart
so the text cannot collide again either.

⚠ **This is per-machine and always will be.** The cache is git-ignored, so each clone keeps its own
and each machine tops up its own on its own `./go`. There is deliberately no shared copy and no
second writer — see the monorepo's ledger-sync story for what two machines committing one file costs.

⚠ **`./go` is the only thing that runs this today, so a machine that does not launch the Command
Center does not top up.** That is enough for both machines here; if that stops being true the answer
is a scheduled task, not a second checker.

---

## Relationship to the other engines

**Standalone** — depends on nothing but the bar's timestamp (like `engines/sessions/`, unlike the
price-driven engines). It does not consume `engines/market_structure/` or `engines/sessions/`. A bot
composes it alongside the others: structure/OB/fib give the *setup*, this gives a *veto* around
news. Gets an `algos/shared/` shim when a bot first uses it (none do yet — the bot suite is being
rebuilt).

**First consumer — the command-center backtest lab** (2026-07-05). `command-center/backend/services/news_filter.py` composes this engine (imports it by bare name; **not** a second impl) to tag a finished run's trades as `in_news` / `in_holiday` for the BacktestDetail "News & Holiday Filter" card — the lab runs backtests raw, then removes news/holiday trades as a post-run view. Lab policy: high-impact USD, window **15 min before / 30 min after**, **holidays always excluded** (the bot/UI still owns the policy — the engine only reports). Consumer detail lives in `command-center/backend/CLAUDE.md` ("News filter (post-run)"). **Only NT8 (UTC) is wired; the MT5/forex path is TODO #3** — it needs its own `entry_ms` capture and non-UTC broker-clock handling before this engine can veto forex backtests.

**Second consumer — the command-center live News Calendar tab** (2026-07-17).
`command-center/backend/services/calendar_service.py` calls `TradingViewSource.fetch_window()` for a
live, read-only calendar view (a whole week fetched, filtered client-side). It is a **separate path
from the blackout filter**: it does NOT touch `store.py` / the shared cache, and its source is
TradingView (not FF) because the tab needs `actual` results + categories, not holidays. Consumer
detail: `command-center/backend/CLAUDE.md` ("Live calendar tab").

**Third consumer — the command center's readiness report** (2026-08-02).
`command-center/backend/services/readiness.py` calls `EventStore().load()` at backend startup and
warns when the cache is EMPTY or STOPS more than 30 days back. It reads only — no fetch, no write,
no policy — and exists because **this engine's honest-coverage rule is invisible from the outside**:
outside a fetched range `has_coverage` is False, so the lab's News & Holiday filter tags nothing and
removes nothing, which looks *exactly* like a broken filter rather than an unbackfilled one. The
cache is git-ignored, so every machine starts empty and a fresh clone hits this by default. A cache
that stops PARTWAY is the nastier case and is reported with the date it ends — trades after it come
back *untagged, not unaffected*. If `EventStore.load()`'s return shape or `NewsEvent.timestamp_ms`
is renamed, that check degrades to a startup warning about an unreadable cache (it catches
everything — it runs inside the startup hook, and raising there would stop the backend booting over
a git-ignored file).

**Fourth consumer — the Command Center launcher** (2026-09-01). `./go` step 6 runs
`tools/backfill.py --top-up --if-stale` before it starts the app. It is the only thing that KEEPS
the cache current on either machine; the readiness check next to it only reports. Root
`CLAUDE.md` routes here rather than restating any of it.

---

## Do

- Keep fetch/IO out of `NewsEngine`. The core stays pure so backtests and live share one code path.
- Add a new provider as a `CalendarSource` subclass in `sources/`; do not teach the engine about
  provider quirks. Normalise everything to UTC epoch-ms + currency code + `Impact` in the source.
- Pass the store's real `covered_ranges` to the engine, never derive coverage from events.
- Keep runnable scripts in `tools/` (the `types.py`-shadowing trap above).
- Keep `curl_cffi` lazy-imported inside `forex_factory_history.py` only — the core, the live feed and
  the tests must import + run with no third-party deps.
- Backfill gently: the history source sleeps between month requests. Do not hammer the FF website;
  rely on the cache (a fetched month is static — never re-fetch it).
- Top up with `--top-up`, and let it read its own start date off the cache. A tool that is HANDED a
  date is a tool somebody has to remember to update.
- When you add a field or event, update this file's Public API + the tests in the same commit.

## Never do

- Do not claim Pine parity — there is no Pine source. Validate with the tests + the live checks.
- Do not put trade decisions, sizing, or a blackout policy default *inside a bot* here — the bot owns
  its `NewsPolicy`, same as it owns its `REGIME_RISK_TABLE`.
- Do not draw the coverage line or any visual here — expose `coverage_start_ms`; the UI draws it.
- Do not commit `data/events.json` — it is fetched/cached data (git-ignored), not source.
- Do not give the top-up a default start date to fall back on when the cache is empty. Refusing is
  the answer; a default would silently narrow every run that did not pass `--from`.
- Do not judge this cache by whether its FILE exists. Coverage is what the filter reads, and a
  present file with month-old coverage is the exact case the readiness banner exists to catch.
- Do not read a tool's MESSAGE to decide whether it worked — read its exit code. The refusal and the
  all-clear here were one grep apart, and the launcher believed the wrong one.
- Do not make the engine core, the live feed, or the tests depend on `curl_cffi` — history only.
- Do not build a second economic-calendar/news engine anywhere. This is the canonical one.

---

## Validation (no Pine parity — tests + live checks)

**Unit tests — GREEN:** `PYTHONPATH=engines python3 -m pytest engines/news/tests/ -q` (47 tests:
blackout window inclusivity + merging, the three coverage modes, next/active/last phases, edges,
policy filtering, whole-day bank-holiday blackout + the `block_holidays`/currency switches, the three
parsers on saved samples — incl. the TradingView `actual`/unit/category parse — the cache store, and
the top-up's decisions). The 12 top-up tests were watched RED against HEAD (9 of 12 fail there; the 3
argparse cases pass by accident and are named as such) and every one is pinned by a mutation that was
watched to kill it — the list is in `tests/test_backfill_top_up.py`'s docstring.

**`NewsEvent.category`** (added 2026-07-17) is a display-only grouping label (Labor, Prices, …) a
source sets if it has one, else `None`. It rides through `to_dict`/`from_dict` but the engine core
**never reads it** — same character as the display-string `forecast`/`actual` fields. It exists for
the live tab's category dropdown; the FF sources leave it `None`.

**Live checks — GREEN (2026-07-05):**
- `python3 engines/news/tools/fetch_smoke.py` reached the free feed (74 events this week), parsed the
  high-impact USD events (ISM Services PMI, FOMC Minutes), ran end-to-end through `NewsEngine`.
- `python3 engines/news/tools/backfill.py --from 2025-02 --to 2025-02` scraped **422 real Feb-2025
  events** past Cloudflare into the cache; a re-run fetched **0** (cache-skip). The engine then
  blacked out the ISM Manufacturing PMI window (Feb 3) and the whole **USD Presidents Day** (Feb 17),
  while a pre-cache 2020 bar reported `has_coverage=False` (filter inert).

These stand in for the other engines' Pine parity check (there is no Pine source).

**Source facts / limits (be honest about these):**
- **Live feed:** the faireconomy host currently serves **only `ff_calendar_thisweek.json`**
  (`nextweek`/`lastweek` 404) — ~1 week per pull, no key, no deps. `fetch()` skips a missing feed.
- **History:** the FF website has any date, but behind Cloudflare — `ForexFactoryHistorySource` gets
  past it with `curl_cffi` (browser impersonation). Scraping is against FF ToS and can break if
  Cloudflare tightens; it is for personal backtest data, throttled + cached (static months fetched
  once). Each event uses `dateline` (UTC unix seconds), so times are exact.
- **Coverage boundary:** before the cache's earliest fetched date the filter is inert by design
  (Aaron's call, 2026-07-05: trade without the filter where data is missing; expose the boundary).

## References

- Free feed: `https://nfs.faireconomy.media/ff_calendar_thisweek.json` (current week).
- History: `https://www.forexfactory.com/calendar?month=<mon>.<year>` (scraped via curl_cffi).
- Non-Pine sibling precedent (also not a mpc_assistant port): `engines/regime/CLAUDE.md`.
- Time-driven sibling (shape/precedent): `engines/sessions/CLAUDE.md`.
- Roadmap (this is logged as an off-roadmap engine): `docs/ENGINE_EXTRACTION_ROADMAP.md`.
- Monorepo context: `../../CLAUDE.md`.
