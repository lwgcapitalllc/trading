# CLAUDE.md — Fibonacci Engine Subsystem

**Purpose:** Turn market-structure output into fib LEVEL EVENTS — the first-touch of each fib
level (E1–E4 entries, TP1–TP5 targets, 1.0) — for use in entries, take-profits, and grading. The
signal is the event ("price reached E1 / 0.618"), not the drawing.
**Scope:** Fib geometry + per-fib touch state machines only. No trading decisions, no structure
detection (it consumes `market_structure/`), no MT5 ops, no UI, no chart rendering.
**Status:** Structure fib (the main retracement fib, "FFT") ported, unit-tested, and
Pine-parity-validated (100% on a `VANTAGE_XAUUSD, 15m` export — 9,562 warm bars, all 258 touch
events matched). Sniper fib now ported and unit-tested; its Pine-parity export check is wired
(`px_sniper_*` columns added to `fib_export.pine` + `compare_fib.py`) but still needs a fresh
TradingView export to run green — until then it is not validated. Macro fib not yet ported.
**Last reviewed:** 2026-07-03

---

## Key paths

```
fibonacci/
├── geometry.py     ← the one shared fib-math core (fib_level / fib_from_origin / fib_levels / origin_index)
├── engine.py       ← the per-fib state machines (StructureFib + SniperFib now; MacroFib next)
├── types.py        ← StructureSnapshot (input); FibTouch / StructureFibEvents / SniperFibEvents (output)
├── __init__.py     ← re-exports the public API
├── CLAUDE.md       ← this file
└── tests/
    ├── test_structure_fib.py
    └── test_sniper_fib.py
```

---

## The three fibs (all identical geometry; they differ only in anchors + ratios + reset rule)

| Fib | Pine group | Anchors | Ratios drawn | Reset / lifecycle |
|---|---|---|---|---|
| **Structure** ("FFT") | `GRP_FIBO` | active swing high/low, **following the live pullback extreme** while a pullback is in progress | E1–E4 (0.618/0.702/0.786/0.886), TP1–TP5 (0.5/0.382/0.0/−0.27/−0.618), 1.0 | new leg when the origin bar changes → all touches reset |
| **Sniper** (`next`) | `GRP_SNIPER` | the **BOS impulse leg** (`bull/bear_bos_high/low` + locs) | 0.382–0.5 zone box | fires on a BOS, frozen (does not extend), replaced on the next BOS |
| **Macro** (`next`) | `GRP_MACRO` | HH→LL cycle (`last_conf_high/low`, bear-SOS→bull-SOS lock) | 0.0/0.382/0.5/0.618/0.702/0.786/0.886/1.0 | own lock/reset cycle; ≤5m timeframe only |

**Structure** and **Sniper** are implemented; **Macro** is not.

Structure's gating logic (ported exactly): 0.618 (E1) is the gate — it must be reached before
anything else arms; the deeper retrace levels (E2/E3/E4/1.0) only register while price is
at/through 0.618; the targets (TP1–TP5) only register from the bar **after** 0.618 was first
reached; a new leg (origin bar changes) resets every touch.

Sniper's lifecycle (ported exactly): a BOS drops one 0.382–0.5 zone across the impulse leg
(`bull/bear_bos_high/low`), measured **from the leg origin** (`fib_from_origin`), and arms it
(`zone_active = false`). The first bar whose range trades into the zone confirms it once
(`confirmed`), latching `zone_active`. A new BOS replaces the zone and re-arms. One subtlety kept
from Pine: the break bar can latch `zone_active` if its own range already covers the fresh zone,
but it never emits a `confirmed` event for that bar — so that zone then confirms silently and no
later bar re-confirms it.

---

## Public API

```python
from fibonacci import StructureFib, SniperFib, StructureSnapshot

fib = StructureFib()
sniper = SniperFib()

# Each closed bar, right after market_structure's engine.update(bar) -> events:
snap = StructureSnapshot.from_engine(structure_engine, events)
fib_events = fib.update(bar.high, bar.low, snap)

fib_events.active            # anchors valid -> a fib is currently drawn
fib_events.origin_changed    # a new leg started this bar (all touches reset)
fib_events.touched           # list[FibTouch] first-reached THIS bar (edge-triggered events)
fib_events.levels            # dict{name: price} — every level's current price (state)
fib_events.touched_so_far    # set[str] — cumulative touched names on this leg
# FibTouch = (level, ratio, price, role)  role: "entry" (retrace side) | "target" (profit side)

sniper_events = sniper.update(bar.high, bar.low, snap)
sniper_events.active         # a zone exists (a BOS has fired at least once)
sniper_events.direction      # 1 bull zone / -1 bear zone
sniper_events.zone_top       # upper edge (max of the 0.382 / 0.5 levels), .zone_bot = lower edge
sniper_events.created        # a fresh zone was set THIS bar (a BOS fired) — event
sniper_events.confirmed      # price entered the zone for the first time THIS bar — event
sniper_events.zone_active    # cumulative latch: price has entered the current zone
```

---

## Relationship to `market_structure/`

The fib engine is **downstream** of the structure engine and depends only on its PUBLIC output —
never its internals. `StructureSnapshot.from_engine(engine, events)` reads the documented
properties (`active_swing_high/low`, `dir`, `pullback_mode/extreme/extreme_loc`,
`last_confirmed_high/low`) and the documented `ExternalEvents` (`bull/bear_bos`, `bull/bear_sos`,
and the break-leg `bull/bear_bos_high/low` + locs). If you need a new field from structure, add a
read property there (as was done for the pullback getters) — do not reach into `_ext`/`_int`.

Same stateful-streaming rationale as `market_structure/` (see its CLAUDE.md): the touch/gate/zone
state carries bar-to-bar and cannot be recomputed from a single bar. Build one `StructureFib` and
one `SniperFib` per symbol/timeframe, feed one closed bar per `update()`.

---

## Do

- Port any change to `mpc_assistant.pine`'s fib blocks back here line-by-line. Keep the gating
  exact — do not reorder or "simplify" the 0.618-gate / targets-from-next-bar / origin-reset logic,
  nor the Sniper's arm-on-BOS / confirm-once / break-bar-clears-confirm interaction.
- When adding a new event or level, update this file's Public API and the tests in the same commit.
- Keep `geometry.py` pure (no state, no I/O) — it is the one core shared by all three fibs.

## Never do

- Do not bake in colours, lines, boxes, or any TradingView drawing concern. This layer emits
  events and prices; drawing is a separate consumer's job.
- Do not reach into `market_structure` engine internals — consume its public reads/events only.
- Do not build a second fib implementation elsewhere. This is the canonical one.
- Do not trust this on live money until the Pine-parity export check below is green.

---

## Validation (Pine ↔ Python parity) — Structure fib GREEN, Sniper PENDING an export

**Structure fib — GREEN (2026-07-02):** full parity on a `VANTAGE_XAUUSD, 15m` export
(9,724 bars). Every field — each level's price, its first-touch pulse, active/dir/origin — matched
Python↔Pine on all 9,562 warm bars (`--warmup 162`, exit 0), across 258 real touch events (E1×52,
E2×44, E3×38, E4×34, 1.0×13, TP1×41, TP2×31, TP3×5; TP4/TP5 never reached in-window). The first
162 bars mismatch only because the Pine export begins warm (chart history before the window) while
the Python engines start cold — the same cold-start pattern as `market_structure/`.

**Sniper fib — PENDING (2026-07-03):** ported + unit-tested; Python-exercised on the 15m candles
above (92 zones created / 45 confirmed) so the logic runs end-to-end. The parity harness is wired
(`px_sniper_*` columns in `fib_export.pine`, compared in `compare_fib.py`) but the existing export
predates those columns, so the Sniper is **not yet Pine-validated**. To close it: re-export
`fib_export.pine` (now with the Sniper block + `px_sniper_*` plots) and re-run `compare_fib.py`.
The tool auto-detects whether the CSV carries the Sniper columns and reports its scope; the Sniper
zone_active latch also has to converge before it matches, so expect the same warmup as Structure.

Re-run `compare_fib.py` after any change to `StructureFib` / `SniperFib` or the fib blocks in
`mpc_assistant.pine`.

Wired up, mirrors `market_structure/`'s flow. Two pieces:

1. `indicators/fib_export.pine` — the external structure engine (byte-identical to
   `structure_engine_export.pine`) + the real Structure fib and Sniper fib lifted from
   `mpc_assistant.pine` (compute + state machines, drawing removed) + `plot()` columns for both
   fibs' outputs (`px_fib_<lvl>_price/_touch`, `px_fib_active/dir/origin`; `px_sniper_top/bot`,
   `px_sniper_active/dir/created/confirmed/zone_active`). Put it on a chart, export chart data to
   CSV, drop it in `fibonacci/exports/` (git-ignored).
2. `fibonacci/tools/compare_fib.py <that.csv>` — runs the REAL pipeline (StructureEngine →
   StructureSnapshot → StructureFib + SniperFib) on the CSV's candles and diffs against the
   `px_fib_*` / `px_sniper_*` columns, bar by bar. Exit 0 = parity. Standard library only.
   `--warmup N` skips cold-start bars (the tool prints the last mismatching bar to help pick N).

Until the Sniper export check is green on real candles, no live consumer should trade off it.
Expect early-bar mismatches to be warmup (structure not yet converged, or a leg/zone that began
before the export window) — parity should hold from the first full in-window leg onward.

## References

- Pine source of truth: `indicators/mpc_assistant.pine` (fib blocks `GRP_FIBO` ~2009-2114,
  `GRP_SNIPER` compute ~2510-2551 + zone-touch ~2788-2797, `GRP_MACRO` ~2290+) and its live
  "MPC - JARVIS" confirmation table, which defines the event model this engine reproduces.
- Upstream structure engine: `market_structure/CLAUDE.md`.
- Monorepo context: `../CLAUDE.md`.
