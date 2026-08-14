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
**Pine:** ported from `indicators/engines/mpc_assistant.pine`; parity harness is `indicators/engines/sessions_export.pine`, diffed against this Python by `tools/compare_sessions.py`. Pine stays in `indicators/` (shared source, TradingView-only toolchain); the CSV + compare tool are the engine's half.
**Last reviewed:** 2026-07-31 (late) — ✅ **ALL 18 FIELDS GREEN, THE NY OPENING RANGE INCLUDED.**
`compare_sessions.py --warmup 220` (no `--skip-nyr`) → **exit 0** on a real 13,186-bar
`VANTAGE_XAUUSD, 5m` export (2026-05-27 → 2026-07-31), stable at warm-up 500 / 2000 / 6000. **The
last uncovered piece of this engine is now covered.** The 220-bar warm-up is the persisted `var`
extremes and the NY range carrying in from before the window (this export is a mid-history SLICE,
not from bar 0) — **all 10 clock flags matched from bar 0**, since they are pure functions of the
timestamp. Together with the 15m run below, the engine is validated on two timeframes: 15m proves
the DST window behaviour across four changeovers, 5m proves the ≤5m opening range. Earlier the same
evening — ✅ **THE WINDOW RE-SYNC IS VALIDATED.**
`compare_sessions.py --skip-nyr --warmup 1` → **exit 0** on a real 21,691-bar `VANTAGE_XAUUSD, 15m`
export, **2025-09-01 → 2026-07-31**. That window spans **four DST changeovers** (UK Oct-2025 and
Mar-2026, US Nov-2025 and Mar-2026), which is the whole point — a shorter or 5m export can sit
entirely inside one offset and would have re-confirmed the old behaviour without ever exercising the
change. All 14 timeframe-agnostic fields match on every bar, and it stays green at warm-up 500 /
1000 / 2000 / 5000. The single bar-0 mismatch that set the warm-up was `px_new_day`: Pine's
`dayofweek(time) != dayofweek(time[1])` has no `time[1]` on the first bar and answers 1, Python
answers 0 — undefined for both sides, not a defect in either. ⚠ **The 4 NY-opening-range fields were
NOT covered** (`--skip-nyr`) — they are a ≤5m feature and a 15m export cannot test them; a short
sessions-only 5m export closes that. The tool now measures the export's bar interval, warns before
running, and prints a **NOT CHECKED** line on success as well as failure so this can never be
misread as full coverage. Earlier the same day — 🔴 **THE THREE SESSION WINDOWS WERE RE-SYNCED AND TWO OF THEM MOVED.** Found by `/audit-engines` against the 2026-07-31 mpc paste (`mpc_assistant.pine:464-478`). Each window is now stated in its **own city's clock and follows that city's DST**, where all three used to be pinned to a fixed `GMT-4`:

| | old | new |
|---|---|---|
| Tokyo / Asia | `2000-0500` GMT-4 | `0900-1800` **Asia/Tokyo** |
| London | `0400-1300` GMT-4 | `0800-1700` **Europe/London** |
| New York | `0900-1800` GMT-4 | `0800-1700` **America/New_York** |

**Worked through in UTC, because only one of the three is equivalent.** **Asia is IDENTICAL year-round** — both forms are 00:00–09:00 UTC (GMT-4 is a fixed offset, and Japan has no DST), so this is a pure re-expression there. **London and New York are identical only in northern-hemisphere WINTER**; under BST/EDT both open and close **one hour earlier in UTC** (London 08:00–17:00 → 07:00–16:00; New York 13:00–22:00 → 12:00–21:00). That is roughly seven months of every year, so real session boundaries moved. **Kill zones, the NY opening range, new-day and weekday are UNCHANGED** — they were always `America/New_York` and stay exactly as validated. **Cascade:** `engines/liquidity/` needed NO code change (it constructs `SessionEngine()` with no args, so it inherits these windows) but its Asia/London/NY session H/L levels now form over different windows — it is **STALE-BY-INPUT** and must be re-validated. `engines/session_volume_profile/` is **UNAFFECTED** — it composes the Asia window only, and Asia did not move; a new test pins that equivalence so an Asia change can never slip through silently. **Harnesses re-synced in the same pass:** `indicators/engines/sessions_export.pine` and `indicators/engines/liquidity_export.pine` both hardcoded the old strings. 18 unit tests green — `test_session_windows_fixed_offset_same_both_seasons` was REPLACED (it asserted a single time-of-day that happens to fall inside both the old and new windows, so it passed after the change while its name and comments described behaviour that no longer existed) by three tests that pin the UTC boundaries season-by-season. ✅ **Both re-validated later the same day** (this warning is kept only to show what the gate was): `compare_sessions.py` and `compare_liquidity.py` each exit 0 on fresh exports — see the entry at the top of this section. ✅ **Every remaining file was synced later the same day** — `mpc_b_leg_strategy.pine` + its export and `indicators/engines/mpc_m15_playbook.pine`. (`mpc_jarvis_v2.pine` was DELETED instead, superseded by `mpc_strategy_export.pine`.) Earlier: 2026-07-04

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

Pine source of truth: `indicators/engines/mpc_assistant.pine` — session windows (836-838), SESSION H/L
TRACKING (1638-1646), KILL ZONES (1861-1866), NY RANGE BOX (1824-1856), newDay / isMondayToFriday
(808-809). Parity export build: `indicators/engines/sessions_export.pine`.

---

## What this engine is (ported semantics)

Unlike `engines/market_structure/`, `engines/fibonacci/` and `engines/order_blocks/` — all price-driven — this engine is
**time-driven**. Its inputs are the bar's **UTC timestamp (epoch milliseconds, == Pine's `time`)**
plus the bar's high/low (needed only for the running session / NY-range extremes).

- **Session windows** — Tokyo `0900-1800` **Asia/Tokyo**, London `0800-1700` **Europe/London**,
  New York `0800-1700` **America/New_York**. Each is stated in its own city's clock and is DST-aware
  (re-synced 2026-07-31 from a fixed `GMT-4` — see *Last reviewed*). A bar is in-session when its
  timestamp, in the session's timezone, falls in `[start, end)` (end exclusive). **None of the three
  wraps midnight any more** (Tokyo used to), but the wrap rule is still implemented — a custom
  `SessionSpec` may need it.
  In UTC: Asia is 00:00–09:00 year-round; London is 07:00–16:00 under BST and 08:00–17:00 under GMT;
  New York is 12:00–21:00 under EDT and 13:00–22:00 under EST.
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
   computed unconditionally, so the output is reproducible bar-for-bar. `indicators/engines/sessions_export.pine`
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

se = (
    SessionEngine()
)  # Pine defaults: Tokyo/London/NY each in its own city's zone; KZ + NY range on NY time

# Each closed bar (timestamp is epoch MILLISECONDS, UTC — exactly Pine's `time`):
ev = se.update(bar.index, bar.timestamp_ms, bar.high, bar.low)

ev.in_asia, ev.in_london, ev.in_ny  # session flags (state)
ev.in_kz1, ev.in_kz2, ev.in_kz3, ev.in_killzone  # kill-zone flags (state)
ev.in_ny_range_window, ev.in_ny_range_extend
ev.ny_range_high, ev.ny_range_low  # live NY opening range (None until first formed)
ev.is_new_day, ev.is_weekday
for name in ev.opened:  # sessions that opened THIS bar (edge)
    ...
for r in ev.closed:  # sessions that closed THIS bar, finalized (edge)
    r.name, r.high, r.low, r.start_index, r.end_index

se.current_range("NY")  # live running high/low for a session (read)
```

Custom windows: pass `SessionEngine(sessions=[SessionSpec.from_pine("Asia", "0900-1800", "Asia/Tokyo"), ...])`.
A fixed GMT offset (`"GMT-4"`) is still accepted — the mpc sessions used one until 2026-07-31.

---

## Relationship to the other engines

**Standalone** — depends on nothing but the bar's timestamp + high/low (not on `engines/market_structure/`).
It is the **prerequisite** the roadmap calls out: **`engines/liquidity/`** (now built) consumes the
session H/L emitted here (adding sweep/mitigation tracking — a liquidity concern kept out of this
engine). **`engines/vwap/`** (now built) turned out to anchor on the **trading-day** boundary (Pine
`ta.vwap`'s default anchor), not the Asia/London/NY session windows, so it reconstructs that
boundary directly rather than composing this engine. Session H/L is *computed* here; sweep tracking
is not.

---

## Do

- Port any change to `mpc_assistant.pine`'s session / kill-zone / NY-range blocks back here
  line-by-line. Keep the `[start, end)` window rule, the overnight-wrap support, each session's own
  timezone (and the fact that kill zones / NY range are separately pinned to NY time),
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

1. `indicators/engines/sessions_export.pine` — the session / kill-zone / NY-range clock lifted from
   `mpc_assistant.pine` (drawing + the two days-back gates removed) with `px_*` `plot()` columns
   for every flag, running session H/L, and the NY range. Put it on a **5-minute** chart (the NY
   range reads a 5m security), Export chart data → CSV, drop it in `engines/sessions/exports/` (git-ignored).
2. `python3 engines/sessions/tools/compare_sessions.py <that.csv>` — feeds each bar's timestamp + high/low
   through `SessionEngine` and diffs against the `px_*` columns, bar by bar. Exit 0 = parity.
   Standard library only.

**`--skip-nyr` (added 2026-07-31) — for a coarser-than-5m export.** The 4 NY-opening-range fields are
the only ones that are not timeframe-agnostic, and on a 15m export they mismatch for a reason that is
not a bug. The tool now measures the export's bar interval (the MODE of the timestamp gaps, so a
weekend or a data hole can't skew it), WARNS up front when it exceeds 5m, and says so again in the
failure report when every mismatching field is a NY-range field. `--skip-nyr` drops those four and
prints a **NOT CHECKED** line on success as well as failure, so a green can never be misread as full
coverage. **A 15m export is the better test of the session WINDOWS** — TradingView caps an export at
roughly 20k bars, which at 15m spans a DST changeover and at 5m may not, and the DST behaviour is
exactly what the 2026-07-31 window re-sync changed. Validate the opening range on a separate 5m run.

Early-bar mismatches are warm-up (the Pine `var` extremes / NY range persisted from before the
export window); the tool prints the last mismatching bar so you can pick `--warmup N`. **If the
ONLY mismatches are on Sunday-evening / weekend bars**, Pine's session day default is weekday-only
rather than all-7 — add a dayofweek gate in `_SessionTracker.contains` (see the `# NOTE:` there).
Re-run `compare_sessions.py` after any change to the session blocks in `mpc_assistant.pine` or here.

## References

- Pine source of truth: `indicators/engines/mpc_assistant.pine` (session blocks listed under Key paths).
- Parity export build: `indicators/engines/sessions_export.pine`.
- Downstream consumers: `engines/liquidity/` (session H/L levels — built). `engines/vwap/` (built)
  anchors on the trading-day boundary, not this engine's session windows — see `docs/ENGINE_EXTRACTION_ROADMAP.md`.
- Sibling engines / the shared porting pattern: `engines/order_blocks/CLAUDE.md`, `engines/fibonacci/CLAUDE.md`.
- Monorepo context: `../CLAUDE.md`.
