# CLAUDE.md — Sessions Engine Subsystem

**Purpose:** Turn a bar's wall-clock timestamp into session CLOCK EVENTS — which sessions
(Tokyo/London/New York) and NY kill zones are open, session open/close edges carrying each
session's finalized high/low, and the NY opening-range high/low. The signal is the flag/edge
("NY just opened, its range was 3980–3994", "we are in kill zone 1", "NY opening range = 4001/3997"),
not the box or line.
**Scope:** Session-window detection + running session H/L + kill zones + NY opening range + the
new-day / weekday clock flags. No trading decisions, no price-structure detection, no MT5 ops, no
UI, no chart rendering (no boxes, lines, labels or colours).
**Status:** Production — ported from `mpc_assistant.pine`, unit-tested (17 hand-traced tests,
green), and **100% Pine-parity-validated on a real `VANTAGE_XAUUSD, 5m` export** (7,319 bars): all
18 fields — the 10 clock flags, the 6 session-H/L fields, and the 2 NY-opening-range fields — match
on every warm bar (`--warmup 263`, exit 0). Independently re-confirmed on a `VANTAGE_XAUUSD, 15m`
export where the 16 timeframe-agnostic fields matched (all 10 flags zero-warmup, 6 session-H/L from
bar 66); only the NY opening range differs on 15m because it is a ≤5m feature. Two timeframes
confirm the clock/session logic is timeframe-agnostic. The one canonical implementation — no
consumer builds its own.
**Pine:** ported from `indicators/mpc_assistant.pine`; parity harness is `indicators/sessions_export.pine`, diffed against this Python by `tools/compare_sessions.py`. Pine stays in `indicators/` (shared source, TradingView-only toolchain); the CSV + compare tool are the engine's half.
**Last reviewed:** 2026-07-04

---

## Key paths

```
engines/sessions/
├── engine.py       ← SessionEngine: the time-driven state machine
├── types.py        ← SessionSpec (a window), SessionRange (a session H/L), SessionEvents (output)
├── __init__.py     ← re-exports the public API
├── CLAUDE.md       ← this file
├── tests/
│   └── test_engine.py
└── tools/
    └── compare_sessions.py   ← Pine↔Python parity harness (reads a TradingView CSV export)
```

Pine source of truth: `indicators/mpc_assistant.pine` — session windows (836-838), SESSION H/L
TRACKING (1638-1646), KILL ZONES (1861-1866), NY RANGE BOX (1824-1856), newDay / isMondayToFriday
(808-809). Parity export build: `indicators/sessions_export.pine`.

---

## What this engine is (ported semantics)

Unlike `engines/market_structure/`, `engines/fibonacci/` and `engines/order_blocks/` — all price-driven — this engine is
**time-driven**. Its inputs are the bar's **UTC timestamp (epoch milliseconds, == Pine's `time`)**
plus the bar's high/low (needed only for the running session / NY-range extremes).

- **Session windows** — Tokyo `2000-0500`, London `0400-1300`, New York `0900-1800`, all in
  **GMT-4** (a fixed offset — season-independent). A bar is in-session when its timestamp, in the
  session's timezone, falls in `[start, end)` (end exclusive); Tokyo wraps past midnight.
- **Running session H/L** — while a session is open, track its high/low; the value persists (Pine
  `var`) after close until the next open. Emitted as a finalized `SessionRange` on the close edge —
  this is what the future Liquidity engine will turn into a swept level.
- **Kill zones** — three NY-time windows: KZ1 = 10:00–10:59, KZ2 = 11:45–12:14, KZ3 = 13:00–13:30,
  all in **America/New_York** (DST-aware — 10:00 NY is KZ1 in both EDT and EST).
- **NY opening range** — the high/low of the `0930-0935` NY window (one 5-minute bar), frozen for
  the rest of the day. **≤5m feature** (Pine reads it off a 5m security): feed 5-minute-or-finer
  bars if you rely on `ny_range_high/low`. The session windows and kill zones are timeframe-agnostic.

### Two deliberate deviations from the Pine source (both = "emit events, not visuals")

1. **All drawing is dropped** — no boxes/lines/labels/colours.
2. **The two "days-back" render gates are dropped** (`withinKZDays` / `withinNYRangeDays`, Pine
   847-850). They only limit how far back Pine draws boxes from `timenow`, and depend on the
   non-reproducible export wall-clock. The underlying time flags + running extremes they gate are
   computed unconditionally, so the output is reproducible bar-for-bar. `indicators/sessions_export.pine`
   drops them identically, so parity holds.

---

## Timeframes & what it needs

- **A UTC timestamp per bar.** Pass `bar.time` as epoch **milliseconds**, UTC (Pine `time`). This
  is the one input the price engines don't take — a bot must feed the broker bar's open time.
- **Closed bars, in order, one at a time.** The session trackers + NY-range state + previous-day
  memory carry bar-to-bar; feed one closed bar per `update()`, in sequence.
- **`zoneinfo` (stdlib, 3.9+).** IANA zones (`America/New_York`) need it for DST; fixed GMT offsets
  are resolved arithmetically. No pip dependency.
- **A ≤5m feed only if you use the NY opening range** (see above). Everything else is TF-agnostic.
- **Warm-up.** The running session extremes are `na` until each session first opens fresh inside
  the fed window; the clock flags need no warm-up (pure function of the timestamp).

---

## Public API

```python
from sessions import SessionEngine, SessionSpec, SessionEvents, SessionRange

se = SessionEngine()   # Pine defaults: Tokyo/London/NY in GMT-4; kill zones + NY range on NY time

# Each closed bar (timestamp is epoch MILLISECONDS, UTC — exactly Pine's `time`):
ev = se.update(bar.index, bar.timestamp_ms, bar.high, bar.low)

ev.in_asia, ev.in_london, ev.in_ny          # session flags (state)
ev.in_kz1, ev.in_kz2, ev.in_kz3, ev.in_killzone   # kill-zone flags (state)
ev.in_ny_range_window, ev.in_ny_range_extend
ev.ny_range_high, ev.ny_range_low           # live NY opening range (None until first formed)
ev.is_new_day, ev.is_weekday
for name in ev.opened:                       # sessions that opened THIS bar (edge)
    ...
for r in ev.closed:                          # sessions that closed THIS bar, finalized (edge)
    r.name, r.high, r.low, r.start_index, r.end_index

se.current_range("NY")                       # live running high/low for a session (read)
```

Custom windows: pass `SessionEngine(sessions=[SessionSpec.from_pine("Asia", "2000-0500", "GMT-4"), ...])`.

---

## Relationship to the other engines

**Standalone** — depends on nothing but the bar's timestamp + high/low (not on `engines/market_structure/`).
It is the **prerequisite** the roadmap calls out: the future **Liquidity** engine consumes the
session H/L emitted here (adding sweep/mitigation tracking — a liquidity concern kept out of this
engine), and the future **VWAP** engine uses the session open as its anchor. Session H/L is
*computed* here; sweep tracking is not.

---

## Do

- Port any change to `mpc_assistant.pine`'s session / kill-zone / NY-range blocks back here
  line-by-line. Keep the `[start, end)` window rule, the overnight wrap, the GMT-4-vs-NY-time split,
  the KZ minute windows and the NY-range reset/expand order exact — do not "clean up" or reorder.
- If you find a bug/inconsistency in the ported Pine logic, leave a `# NOTE:` in `engine.py`
  flagging it rather than silently correcting it (one already exists — the session day-of-week
  default).
- When adding an event or field, update this file's Public API and the tests in the same commit.

## Never do

- Do not bake in colours, boxes, lines or labels — this layer emits flags + edges.
- Do not add the sweep/mitigation tracking of session H/L here — that is the Liquidity engine's job.
- Do not re-add the `withinKZDays` / `withinNYRangeDays` render gates — they are a drawing concern
  and make the output non-reproducible.
- Do not build a second sessions implementation elsewhere. This is the canonical one.
- Do not let this engine or the session blocks in `mpc_assistant.pine` drift; re-run the parity
  check after any change to either.

---

## Validation (Pine ↔ Python parity)

**Unit tests — GREEN:** `python3 -m pytest engines/sessions/tests/ -q` (17 hand-traced tests pinning the
GMT-offset parsing, the overnight-wrap window rule, fixed-offset-vs-DST behaviour, session H/L
open/expand/close edges, the kill-zone windows + DST, the NY opening range, and new-day/weekday).

**Full Pine↔Python parity — GREEN (2026-07-04).** 100% match on a real `VANTAGE_XAUUSD, 5m`
export (7,319 bars): all 18 fields matched on every warm bar (`--warmup 263`, exit 0). The 263-bar
warm-up is because the export opened mid-Asia-session and Asia is a once-per-day window, so
`px_asia_high/low` only converge when the next Asia session opens fresh inside the export (the flag
fields need no warm-up — they matched from bar 0). Independently re-confirmed on a
`VANTAGE_XAUUSD, 15m` export (10,722 bars): the 16 timeframe-agnostic fields matched (10 flags
zero-warmup, 6 session-H/L from bar 66); the 2 NY-range fields differ there only because the NY
opening range reads a 5-minute security in Pine — a ≤5m feature — so it is validated on the 5m
export, not 15m. The harness mirrors the other engines:

1. `indicators/sessions_export.pine` — the session / kill-zone / NY-range clock lifted from
   `mpc_assistant.pine` (drawing + the two days-back gates removed) with `px_*` `plot()` columns
   for every flag, running session H/L, and the NY range. Put it on a **5-minute** chart (the NY
   range reads a 5m security), Export chart data → CSV, drop it in `engines/sessions/exports/` (git-ignored).
2. `python3 engines/sessions/tools/compare_sessions.py <that.csv>` — feeds each bar's timestamp + high/low
   through `SessionEngine` and diffs against the `px_*` columns, bar by bar. Exit 0 = parity.
   Standard library only.

Early-bar mismatches are warm-up (the Pine `var` extremes / NY range persisted from before the
export window); the tool prints the last mismatching bar so you can pick `--warmup N`. **If the
ONLY mismatches are on Sunday-evening / weekend bars**, Pine's session day default is weekday-only
rather than all-7 — add a dayofweek gate in `_SessionTracker.contains` (see the `# NOTE:` there).
Re-run `compare_sessions.py` after any change to the session blocks in `mpc_assistant.pine` or here.

## References

- Pine source of truth: `indicators/mpc_assistant.pine` (session blocks listed under Key paths).
- Parity export build: `indicators/sessions_export.pine`.
- Downstream consumers (future): Liquidity engine (session H/L levels), VWAP engine (session anchor)
  — see `docs/ENGINE_EXTRACTION_ROADMAP.md`.
- Sibling engines / the shared porting pattern: `engines/order_blocks/CLAUDE.md`, `engines/fibonacci/CLAUDE.md`.
- Monorepo context: `../CLAUDE.md`.
