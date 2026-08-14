# CLAUDE.md — Liquidity Levels Engine Subsystem

**Purpose:** Turn the bar stream into liquidity LEVEL EVENTS — the prices the market runs toward and
grabs: previous day/week highs & lows (PDH/PDL/PWH/PWL), the previous week's close
(PWC), the previous-H4 high/low sweep targets (SSH/BSL), and each finished session's high/low
(Asia/London/NY). The signal is the event ("PDH created at 2358", "H4 high swept — BSL"), not the
line or box.
**Scope:** Level geometry + lifecycle (create on a completed period / session close → mitigate
(sweep or break) → evict) only. No trading decisions, no MT5 ops, no UI, no chart rendering (no
lines, labels or colours). Session high/low is CONSUMED from `engines/sessions/`, not recomputed.
**Status:** Production — ported from `mpc_assistant.pine`'s liquidity blocks, unit-tested (14
hand-traced tests, green), and **100% Pine-parity-validated**. The **MONTHLY level (PMH/PML) was
removed from the source and this engine on 2026-07-09**; the check now covers 28 fields (13 level
prices, their 12 mitigation flags, 3 boundary-roll pulses) and RE-PASSED exit 0 on a fresh
`VANTAGE_XAUUSD, 5m` export (13,759 bars, `--htf-rollover 18 --warmup 1742` — the warm-up is now just
the weekly cold-start, not the old monthly one). The one canonical implementation — no consumer builds
its own.
**Pine:** ported from `indicators/engines/mpc_assistant.pine` (DAILY/WEEKLY LEVELS, PWC, H4
LIQUIDITY SWEEP, SESSION H/L); parity harness is `indicators/engines/liquidity_export.pine`, diffed against
this Python by `tools/compare_liquidity.py`. Pine stays in `indicators/` (shared source,
TradingView-only toolchain); the CSV + compare tool are the engine's half.
**Last reviewed:** 2026-07-31 (late) — ✅ **RE-CONFIRMED ON A SECOND TIMEFRAME.** `compare_liquidity.py --htf-rollover 18 --warmup 862` → exit 0 on a 13,186-bar `VANTAGE_XAUUSD, 5m` export (2026-05-27 → 2026-07-31), stable at warm-up 2000 / 6000. All 28 fields. The prev-WEEK levels are the long pole in the warm-up, as expected on a two-month window. Earlier the same evening — ✅ **RE-VALIDATED ON THE NEW WINDOWS.**
`compare_liquidity.py --htf-rollover 18 --warmup 449` → **exit 0** on a real 21,691-bar
`VANTAGE_XAUUSD, 15m` export (2025-09-01 → 2026-07-31, spanning four DST changeovers). All 28 fields
match on every warm bar, and it stays green at warm-up 1000 / 2000 / 5000. The 449-bar warm-up is
entirely the `_mit` flags reading `None` in Python against `0.0` in Pine — Python has not formed the
level yet where Pine's `var bool` initialised false — not a disagreement about any level's price.
**The STALE-BY-INPUT flag below is cleared:** the Asia/London/NY session H/L levels now form over the
re-synced windows and agree with Pine across all four changeovers. Earlier the same day — 🔴 **STALE-BY-INPUT: the session windows underneath this engine moved.** `/audit-engines` found the 2026-07-31 mpc paste re-stated all three session windows in their own cities' clocks (see `engines/sessions/CLAUDE.md`). **NO code changed here** — `LiquidityEngine` constructs `SessionEngine()` with no args, so it picked the new windows up automatically — but the **Asia / London / NY session high-low levels this engine creates now form over different windows**: Asia is unchanged, while London and New York both shift **one hour earlier in UTC** under BST/EDT (~7 months a year). Every non-session level (PDH/PDL, PWH/PWL, PWC, H4 SSH/BSL) is untouched, as are all the mitigation rules and the per-bar order. `indicators/engines/liquidity_export.pine` hardcoded the OLD session strings and was re-synced in the same pass. 14 unit tests green. ⚠ **The 2026-07-09 GREEN parity run predates this and no longer describes the session levels** — re-run `compare_liquidity.py --htf-rollover 18` on a fresh export off the re-synced harness, exit 0, before trusting any session-level result or committing this as validated. Earlier: 2026-07-05

---

## NON-REPAINTING — Aaron's explicit decision (2026-07-05)

The Pine source reads the day/week high/low with `request.security(..., high, lookahead_on)`,
which **peeks at the developing period's future extreme** and freezes it at the period's first bar
(a repaint the source itself hides on the live bar via `not isLastDaily`). Aaron's decision: **the
engine must only ever use PAST, completed data — never forecast the current period's high/low.** A
live bot must not trade a level built from information it could not have had at the time.

So every HTF level here is built from the **previous, fully-completed period only**: on the first bar
of a new day/week the just-finished period's high/low (and, for PWC, its final close) become
the new level. This is exactly what the source shows in real time (yesterday's completed high), made
deterministic and streamable. The parity export mirrors the same non-repainting reads
(`high[1]/low[1]/close[1]`), so the Python↔Pine check still validates at 100% — the same "deliberate
deviation, mirrored in the export" move `engines/sessions/` used for its render gates.

---

## Key paths

```
engines/liquidity/
├── engine.py       ← LiquidityEngine: the streaming state machine (+ _PeriodTracker for HTF buckets)
├── types.py        ← LiquidityLevel (a price line), LiquidityEvents (output), the mitigation-rule constants
├── __init__.py     ← re-exports the public API
├── CLAUDE.md       ← this file
├── tests/
│   └── test_engine.py       ← 14 hand-traced tests
└── tools/
    └── compare_liquidity.py ← Pine↔Python parity harness (reads a TradingView CSV export)
```

Pine source of truth: `indicators/engines/mpc_assistant.pine` — DAILY/WEEKLY LEVELS (1334-1506),
PREVIOUS WEEKLY CLOSE (1508-1533), H4 LIQUIDITY SWEEP TRACKER (1535-1591), SESSION H/L TRACKING
(1593-1760), the HTF securities (811-817) and the newDay tidy (1344 / 1402 / 1460 / 1618).
Parity export build: `indicators/engines/liquidity_export.pine`.

---

## What a liquidity level is (ported semantics)

A **level** is a price line price is drawn to and grabs. Six kinds, each with a mitigation rule
ported exactly from the source:

| kind | levels | mitigation rule (how it is "taken") |
|---|---|---|
| daily | PDH / PDL | **sweep** — wick through: `high>lvl` (H) / `low<lvl` (L) |
| weekly | PWH / PWL | **break** — `close>lvl` (H) / `close<lvl` (L) |
| pwc | PWC | none — a reference close, never mitigated (source only recolours it) |
| h4 | H4 H / H4 L | **sweep**; the sweep emits the source's label — high→`BSL`, low→`SSL` |
| session | Asia/London/NY H & L | **sweep** |

Note the deliberate asymmetry: daily / session / H4 use the **sweep** rule (a wick through the
level); weekly uses the **break** rule (a plain close through). Keep it exact.

**Close-back guard dropped 2026-07-06.** The sweep rule used to also require price to close back the
other side of the level (`high>lvl and close<lvl` for a high — a grab-and-reject). A re-pasted
`mpc_assistant.pine` removed that guard: the daily/session/H4 sweeps now fire on the **wick alone**.
Weekly break rule is unchanged.

A level's price is **frozen at creation** and never repainted. A level created on a period roll or a
session close **evicts** the previous same-slot level (a create→evict pair). A mitigated level stays
in `active` (flagged) until the next roll, or until the new-day tidy drops it.

---

## Per-bar order (ported — do not reorder)

Each bar, `update()` runs:

1. **Drive the composed sessions engine** (gives the NY new-day flag + the finished SessionRange).
2. **New-day tidy** (Pine `i_currentDayOnly`, keyed on NY `newDay`) — drop already-mitigated
   day/week/session levels. H4 and PWC are excluded (source hides neither here).
3. **Create** — day/week rolls, then PWC, then H4 roll, then session-close levels.
4. **Mitigate** — every active level, AFTER all creation, so a fresh level can be taken on its own
   creation bar (mirrors Pine's create-then-mitigate order within each block).

---

## HTF period boundaries (the calibration knob)

Day / week / H4 buckets are cut in a configurable timezone (`htf_timezone`), keyed on a clock
shifted so the session-open hour (`htf_rollover_hours`) lands at midnight — which correctly rolls an
EVENING open (whose pre-midnight bar is the first bar of the new week) into the next period.
TradingView's "D"/"W"/"240" resolutions align to the instrument's **exchange session**, which is
broker-dependent. **Validated for VANTAGE:XAUUSD: the session opens 18:00 New York** — its Sunday
18:00 bar is the first bar of the new week → `htf_timezone="America/New_York", htf_rollover_hours=18`
(the baked-in default; the `px_*_roll` columns were the calibration signal). The new-day tidy keys off NY
`newDay` (a separate, non-configurable clock the composed sessions engine already computes).

---

## Public API

```python
from liquidity import LiquidityEngine

liq = LiquidityEngine()   # Pine defaults; composes its own sessions engine internally

# Each closed bar (timestamp is epoch MILLISECONDS, UTC — exactly Pine's `time`):
ev = liq.update(bar.index, bar.timestamp_ms, bar.high, bar.low, bar.close)

for lvl in ev.created:      # levels created THIS bar (a period completed / a session closed) — edge
    lvl.kind, lvl.side, lvl.name, lvl.price, lvl.rule, lvl.id
for lvl in ev.mitigated:    # levels price TOOK this bar — edge
    lvl.name, lvl.mitigated_index, lvl.sweep_label   # sweep_label: "BSL"/"SSL" for H4
for lvl in ev.evicted:      # levels removed this bar (roll / new-day tidy) — NOT a signal
    ...
ev.active                   # every currently-live level, incl. mitigated-but-shown (state)
liq.active_levels()         # same as ev.active (read)
```

Feature toggles (`enable_daily`/`enable_weekly`/…/`enable_sessions`), `hide_mitigated_on_new_day`,
`htf_timezone`, `htf_rollover_hours`, and an injectable `session_engine` are all constructor args.

---

## Relationship to the other engines

- **Consumes `engines/sessions/`** for the Asia/London/NY session H/L. It composes and drives its own
  `SessionEngine` (or one you inject), and turns each `closed` `SessionRange` into a pair of session
  levels. Session H/L is *computed* by the sessions engine; the **sweep/mitigation tracking is added
  here** — exactly the split the roadmap called for.
- **Time-driven**, like `engines/sessions/` — it needs the bar's UTC timestamp (for the HTF/period
  boundaries + newDay), plus high/low/close. It does **not** depend on `engines/market_structure/`.
- Downstream of nothing yet. A bot consuming it will get an `algos/shared/` shim (none built yet).

---

## Do

- Port any change to `mpc_assistant.pine`'s liquidity blocks back here. Keep the sweep-vs-break rule
  split, the per-bar order (tidy → create → mitigate), and the previous-completed-period reads exact.
- Keep every HTF level **non-repainting** (previous completed period only) — this is Aaron's explicit
  decision; do not "improve" it into a live-period read.
- When adding a level kind or field, update this file's Public API and the tests in the same commit.

## Never do

- Do not read the developing period's high/low (no `request.security(high, lookahead_on)` semantics,
  no future peeking). Past data only.
- Do not recompute session high/low here — consume `engines/sessions/`'s `closed` SessionRange.
- Do not bake in lines, labels or colours — this layer emits events.
- Do not build a second liquidity implementation elsewhere. This is the canonical one.
- Do not let this engine or the liquidity blocks in `mpc_assistant.pine` drift; re-run the parity
  check after any change to either.

---

## Validation (Pine ↔ Python parity)

**Unit tests — GREEN:** `python3 -m pytest engines/liquidity/tests/ -q` (14 hand-traced tests pinning
non-repainting creation, the sweep-vs-break rules, PWC, the H4 SSH/BSL sweep, session levels via the
composed sessions engine, the new-day tidy, and eviction on a roll).

**Full Pine↔Python parity — GREEN (2026-07-09, monthly removed).** 100% match on a fresh
`VANTAGE_XAUUSD, 5m` export (13,759 bars): all **28 fields** (13 level prices + 12 mitigation flags + 3
boundary-roll pulses) matched on every warm bar (`--htf-rollover 18 --warmup 1742`, exit 0). Removing
the monthly level dropped the harness's `px_pmh/px_pml(_mit)` + `px_month_roll` columns. The 1,742-bar
warm-up is now just the **weekly** cold-start (Pine's HTF security opens holding a pre-window weekly
value while Python forms its first in-window weekly level at bar 1742) — far shorter than the old
4,653-bar warm-up, which the monthly level dominated. (Pre-removal run for the record: GREEN 2026-07-05,
33 fields, `--warmup 4653`.) The harness:

1. `indicators/engines/liquidity_export.pine` — the liquidity levels lifted from `mpc_assistant.pine` with
   drawing removed, using the **non-repainting** `high[1]/low[1]/close[1]` reads, plus `px_*` columns
   for each level's price + mitigation flag and `px_*_roll` boundary pulses. Put it on the same
   `VANTAGE_XAUUSD` chart/timeframe (5m), Export chart data → CSV, drop it in
   `engines/liquidity/exports/` (git-ignored).
2. `python3 engines/liquidity/tools/compare_liquidity.py <that.csv> --warmup N` — feeds each bar
   through `LiquidityEngine` and diffs the active-level prices + mitigation flags against the `px_*`
   columns, bar by bar. Exit 0 = parity. Standard library only. **Boundary calibration** (already
   done — baked in as `htf_rollover_hours=18`): the `px_*_roll` columns are the signal; if they ever
   mismatch on a different instrument, sweep `--htf-rollover` (the session-open hour) and/or
   `--htf-tz` until they match, then the level prices follow.

The parity run uses `hide_mitigated_on_new_day=False` (the export drops that drawing-only tidy; it is
covered by the unit tests). Re-run `compare_liquidity.py` after any change to the liquidity blocks in
`mpc_assistant.pine` or here.

## References

- Pine source of truth: `indicators/engines/mpc_assistant.pine` (liquidity blocks listed under Key paths).
- Parity export build: `indicators/engines/liquidity_export.pine`.
- Upstream (consumed): `engines/sessions/CLAUDE.md` (session H/L).
- Sibling / the shared non-repainting-port pattern: `engines/sessions/CLAUDE.md`,
  `engines/order_blocks/CLAUDE.md`.
- Roadmap: `docs/ENGINE_EXTRACTION_ROADMAP.md` (Liquidity was the #1 remaining engine).
- Monorepo context: `../CLAUDE.md`.
