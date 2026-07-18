# News Calendar Tab — Design Doc

**Status:** BUILT 2026-07-17 (v1). Backend + frontend in place, 35 news-engine tests green, both
sides compile. Not yet committed. See "Build status" below.
**Owner:** Aaron.
**Last updated:** 2026-07-17

---

## Build status (2026-07-17)

**v2 (2026-07-17, same day)** — three changes after the first click-through:

1. **Impact filter fixed + made TradingView-style.** v1's impact filter was a *minimum* ("Low" = Low
   and above), which read as broken. Now three independent toggles (High / Medium / Low), default all
   on; a subset filters to exactly those levels. Empty set → shows nothing (honest empty state).
2. **Category dropdown added.** TradingView's `category` code (`mny`, `prce`, `lbr`, …) is mapped to
   its human label in `TradingViewSource` (`_CATEGORY_LABELS`) and carried on a new optional
   `NewsEvent.category` field (generic display field, like forecast/actual — the engine never reads
   it; the FF source leaves it None). The dropdown is data-driven from the labels present that week.
3. **Day-summary strip added + all filtering moved client-side.** The endpoint now returns the WHOLE
   week unfiltered (~195 rows — tiny); the frontend does currency/impact/category/day filtering. So
   filter changes are instant, and the 7-day strip (Mon–Sun, per-day counts, click a day to filter,
   "Today" highlighted, "Today" button to jump back) stays consistent with the list. The strip counts
   reflect the active currency/impact/category filters (not the day), so e.g. filtering to CNY shows
   which days actually have CNY events — the fix for the earlier "Thursday looks empty" confusion.

Not built: Earnings / Dividends / Revenue / IPO tabs (those are separate TradingView feeds; this tab
is the Economic calendar only).

---

## Build status — v1 (2026-07-17)

Built to the design below, with three refinements found during the build:

1. **Colouring is server-side and robust.** Each TradingView row also carries numeric `actualRaw`/
   `forecastRaw` and a `unit`, and — crucially — an event's actual and forecast always share a unit,
   so comparing them numerically needs no K/M expansion. `calendar_service._surprise()` parses the
   leading number out of the display string and returns `"beat" | "miss" | "inline" | null` using the
   `_LOWER_IS_BETTER` polarity list. The API carries a `surprise` field; the frontend just maps it to
   green/red. The polarity list stays server-side (it's a UI/market judgement, not calendar data).
2. **The Period column is deferred.** It would mean adding a `period` field to the canonical
   `NewsEvent`, which the engine doesn't need. Not worth touching the shared type for a cosmetic
   column in v1. Revisit if wanted.
3. **Day headers are not sticky in v1.** The 22px padded-scroller sticky trap (see frontend
   CLAUDE.md) makes pinning a second element below a variable-height banner fiddly. Skipped for now.

Chosen defaults (Aaron, 2026-07-17): 9 majors (`US,EU,GB,JP,CA,AU,NZ,CH,CN`); prev/next week paging;
impact filter opens on "All". Currency + impact filters and the week offset all live in the URL.

Files: `engines/news/sources/tradingview.py` (+ `tests/test_tradingview.py`),
`backend/services/calendar_service.py`, `backend/routers/calendar.py`, `backend/models.py`
(`CalendarEvent`/`CalendarResponse`), `frontend/src/{hooks/useCalendar.ts, pages/Calendar.tsx,
types/index.ts}`, `App.tsx` route + `Sidebar.tsx` NavItem (WORKSPACE, next to Bots).

---

## 1. Goal

A new tab in the command center that shows a live economic-news calendar, like Forex Factory.

Open the tab and you see the week's events grouped by day. At a glance you can tell what is
upcoming, what is happening now, and what has already passed. Each event shows its result once it is
released (actual vs forecast vs previous), coloured green or red.

Real-time, no scraping. One proper API feed.

---

## 2. Source decision — one feed, not two

We use **TradingView's free economic-calendar API** for the calendar tab. That is the only source
the tab needs.

Why not Forex Factory too? Two different jobs got confused:

- **The calendar tab** (this doc) — TradingView alone covers it. Every event, the result numbers,
  forecast, previous, plus years of history and a forward window. No key, no scraping.
- **The backtest holiday filter** (already built, in `services/news_filter.py`) — that is the only
  thing that ever needed Forex Factory, because TradingView carries no bank holidays and the lab
  always drops holiday trades. It already uses the FF free feed today. Leave it alone.

So there is no "two sources to manage" for this tab. One new feed for the new tab. The old FF feed
keeps doing the one job it already does. They do not overlap.

**TradingView's one gap:** no bank-holiday rows. The calendar tab will not show "French Bank
Holiday"-style entries. Acceptable for now. If we later want them on the calendar, we add FF as a
second source just for holidays — not before.

---

## 3. The TradingView API (hard-won — do not re-research)

Endpoint:

```
https://economic-calendar.tradingview.com/events
  ?from=<ISO8601 UTC>&to=<ISO8601 UTC>
  &countries=US,EU,GB,JP,CA,AU,NZ,CH,CN
```

Required headers (it 403s without the Origin):

```
Origin: https://www.tradingview.com
User-Agent: Mozilla/5.0
```

Response: `{"status":"ok","result":[ {event}, ... ]}`

Fields per event we care about:

| TradingView field | Meaning | Maps to our `NewsEvent` |
|---|---|---|
| `date` | event time, UTC ISO 8601 | `timestamp_ms` (parse ISO → epoch ms) |
| `currency` | currency code (USD, EUR…) | `currency` |
| `importance` | -1 = low, 0 = medium, 1 = high | `impact` (see mapping below) |
| `title` | event name | `title` |
| `forecast` | forecast value (display string) | `forecast` |
| `previous` | previous value (display string) | `previous` |
| `actual` | released result, null until release | `actual` |
| `period` | which month/quarter it is for | (display only — "Period" column) |
| `unit` | %, K, M… | (already in the display strings) |
| `source`, `comment` | provider + blurb | (optional detail expander) |

Importance mapping: `1 → Impact.HIGH`, `0 → Impact.MEDIUM`, `-1 → Impact.LOW`. There are no holiday
rows, so `is_holiday` is always False from this source.

Limits and behaviour:

- No API key. No auth.
- History back to ~2018. Forward roughly two months.
- ~2000-event cap per query — page by narrower date windows if a range exceeds it.
- `actual` is null before release and fills in after. This is the field the FF free feed never had,
  and the reason we switched.

Cross-checked against Forex Factory during research: identical numbers (a CPI print read actual 3.5,
forecast 3.8, previous 4.2 on both). Trust the feed.

**No good/bad flag.** TradingView does not say whether an `actual` beat or missed in a market sense.
Higher is not always better (unemployment, jobless claims, oil inventories, gas storage are
"lower is better"). To colour results we keep a short explicit polarity list — see §5.

---

## 4. Architecture

Three pieces. Each is small.

### 4a. Data source — `engines/news/sources/tradingview.py`

New `CalendarSource` implementation. This is the sanctioned way to extend the news engine — a new
source file, nothing downstream changes. **Do not build a second news engine** (CLAUDE.md rule).

One wrinkle: the existing `CalendarSource.fetch()` takes no arguments — it was built for the weekly
refresh job that always pulls "this week." The calendar tab needs an arbitrary date window (this
week, next week, a past week). So the TradingView source needs a windowed fetch.

Recommendation: add a range-aware method rather than bending the parameterless one.

```python
class TradingViewSource(CalendarSource):
    def fetch(self) -> FetchResult:            # default: current week, satisfies the interface
        ...
    def fetch_window(self, from_ms, to_ms, countries=DEFAULT) -> FetchResult:
        ...                                     # what the calendar endpoint calls
```

The source normalises every TradingView row into a `NewsEvent` (UTC epoch-ms, currency, Impact enum)
and reports covered ranges. Same contract as `forex_factory.py`.

### 4b. Backend endpoint — `GET /calendar`

New router `routers/calendar.py` + service `services/calendar_service.py`. Thin router, logic in the
service (house style).

```
GET /calendar?from=<iso>&to=<iso>&currencies=USD,EUR&impact=HIGH
→ { events: [ {timestamp_ms, currency, impact, title, forecast, previous, actual, released} ],
    server_now_ms }
```

- The service calls `TradingViewSource.fetch_window()` for the requested window.
- Cache the result briefly (in-memory, ~60s TTL keyed by window+filters) so re-polling is cheap and
  TradingView is not hammered. This is a **live view**, so it does NOT write to the shared
  `events.json` the backtest filter reads — keep the two paths separate.
- Return `server_now_ms` so the frontend "now" line and countdown use server time, not the
  browser clock (avoids a wrong clock skewing "upcoming vs passed").
- Register in `main.py` via `include_router`.
- Add the response model to `models.py` (all Pydantic in one file).

### 4c. Frontend — the tab

- Route in `App.tsx`, `NavItem` in `Sidebar.tsx` under **WORKSPACE**, next to Bots. (A route with no
  NavItem is a CLAUDE.md "never do".)
- New page `pages/Calendar.tsx` + hook `hooks/useCalendar.ts` (TanStack Query, one file per domain).
- Types mirrored in `types/index.ts`. All `fetch()` stays in `api/client.ts`.
- Poll every 30–60s for fresh `actual` values. A 1s local ticker drives the countdown between polls
  (no need to poll every second).

---

## 5. UX spec

Model the layout on Forex Factory; steal the good bits from FXStreet.

**Layout:** events grouped by day, one row each, in time order. Sticky day headers.

**Row contents:** time · currency · impact dot · title · actual · forecast · previous. Optionally a
"Period" column (e.g. "Jun") from TradingView's `period`.

**The "now" line:** a horizontal marker between the last passed event and the next upcoming one
(FXStreet does this). Everything above it is done; everything below is upcoming. This is the "know at
a glance if it's passed" requirement.

**Countdown:** for the next high-impact event, a live "time left" (e.g. "in 42m"). Ticks locally
every second off `server_now_ms`.

**Impact colour:** high = red/orange, medium = amber, low = yellow/grey. Match FF's folder colours.

**Actual colouring (green/red):** compare `actual` to `forecast`. Green = better than forecast, red =
worse. Default "higher is better." Keep an explicit **"lower is better" list** for the exceptions:

```
Unemployment Rate, Initial/Continuing Jobless Claims, Crude Oil Inventories,
Natural Gas Storage, Trade Deficit, Inflation-where-target-is-lower (judgement call)
```

Start with ~a dozen entries, grow as we spot misses. If forecast or actual is missing, no colour.

**Filters:** by currency (multi-select) and by impact (high-only toggle at least). FF and FXStreet
both lead with these.

**Nice-to-haves (later, not v1):** a detail expander per event ("Why traders care"), a deviation
ratio (actual − forecast, FXStreet), revision handling.

---

## 6. Known bugs found during research (out of scope here, but recorded)

These are in the existing FF path. They do NOT affect the calendar tab (which uses TradingView), but
they do affect the backtest holiday/news filter. Fix separately.

1. **The store silently wipes actuals.** `EventStore.upsert()` replaces an event by `key()`. Saving
   CPI with `actual='3.5%'`, then running `tools/refresh.py` (free feed, which has no actual),
   overwrites it back to None. Reproduced. Fix: upsert should not blank a non-null field with null.

2. **The FF website history scraper is dead.** `forex_factory_history.py` defaults to
   `impersonate="chrome"`, which Cloudflare now 403s. The FF free *feed* (`thisweek`) still works;
   the *website scrape* does not. So deep FF history is currently unavailable — another reason the
   calendar uses TradingView for history.

---

## 7. Build checklist (v1 done 2026-07-17)

- [x] `engines/news/sources/tradingview.py` — `TradingViewSource(CalendarSource)` with `fetch()` +
      `fetch_window(from_ms, to_ms)`; normalise to `NewsEvent`; exported from `sources/__init__.py`.
- [x] Offline parser tests (`tests/test_tradingview.py`, 6) + live smoke test — `actual` populates.
- [x] `models.py` — `CalendarEvent` (+ `surprise`) + `CalendarResponse`.
- [x] `services/calendar_service.py` — window fetch + 60s cache + filters + `server_now_ms` + surprise.
- [x] `routers/calendar.py` — `GET /calendar`; registered in `main.py`.
- [x] `frontend/src/types/index.ts` — mirrors the models.
- [x] `frontend/src/hooks/useCalendar.ts` — TanStack Query, 45s poll.
- [x] `frontend/src/pages/Calendar.tsx` — day groups, now line, countdown, filters, actual colouring.
- [x] `App.tsx` route + `Sidebar.tsx` NavItem under WORKSPACE next to Bots.
- [x] Polarity list for actual colouring (`_LOWER_IS_BETTER`, 11 entries) — in `calendar_service.py`.

Not done in v1 (deliberate): Period column, sticky day headers, the "why traders care" detail
expander, deviation ratio, revisions. Not yet committed. Not yet exercised in the running browser —
worth a manual click-through (start the backend + frontend) before commit.

---

## 8. Open questions

- Countries list: start with `US,EU,GB,JP,CA,AU,NZ,CH,CN`? Or gold-focused (mostly US)?
- Default window on open: current week (Mon–Sun)? With prev/next week paging.
- Do we want past weeks browsable in v1, or only current + next?
- Impact filter default: all, or high-only?
