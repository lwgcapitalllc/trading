# CLAUDE.md — Fibonacci Engine Subsystem

**Purpose:** Turn market-structure output into fib LEVEL EVENTS — the first-touch of each fib
level (E1–E4 entries, TP1–TP5 targets, 1.0) — for use in entries, take-profits, and grading. The
signal is the event ("price reached E1 / 0.618"), not the drawing.
**Scope:** Fib geometry + per-fib touch state machines only. No trading decisions, no structure
detection (it consumes `market_structure/`), no MT5 ops, no UI, no chart rendering.
**Status:** All three fibs ported, unit-tested, and Pine-parity-validated (100%). Structure ("FFT")
and Sniper on `VANTAGE_XAUUSD, 15m` exports; Macro on a `VANTAGE_XAUUSD, 5m` export (Pine gates the
Macro to ≤5m). The one canonical implementation — no consumer builds its own.
**Last reviewed:** 2026-07-04

---

## Key paths

```
fibonacci/
├── geometry.py     ← the one shared fib-math core (fib_level / fib_from_origin / fib_levels / origin_index)
├── engine.py       ← the per-fib state machines (StructureFib + SniperFib + MacroFib)
├── types.py        ← StructureSnapshot (input); FibTouch / StructureFibEvents / SniperFibEvents / MacroFibEvents (output)
├── __init__.py     ← re-exports the public API
├── CLAUDE.md       ← this file
└── tests/
    ├── test_structure_fib.py
    ├── test_sniper_fib.py
    └── test_macro_fib.py
```

---

## The three fibs (all identical geometry; they differ only in anchors + ratios + reset rule)

| Fib | Pine group | Anchors | Ratios drawn | Reset / lifecycle |
|---|---|---|---|---|
| **Structure** ("FFT") | `GRP_FIBO` | active swing high/low, **following the live pullback extreme** while a pullback is in progress | E1–E4 (0.618/0.702/0.786/0.886), TP1–TP5 (0.5/0.382/0.0/−0.27/−0.618), 1.0 | new leg when the origin bar changes → all touches reset |
| **Sniper** (`next`) | `GRP_SNIPER` | the **BOS impulse leg** (`bull/bear_bos_high/low` + locs) | 0.382–0.5 zone box | fires on a BOS, frozen (does not extend), replaced on the next BOS |
| **Macro** | `GRP_MACRO` | HH→LL cycle (`last_conf_high/low`, bear-SOS→bull-SOS lock) | 0.0/0.382/0.5/0.618/0.702/0.786/0.886/1.0 | own lock/reset/extend cycle; ≤5m timeframe only |

All three fibs are implemented.

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

Macro's lifecycle (ported exactly): a bull-only cycle. The bottom (LL, the 1.0 level) locks on a
bullish SOS that follows a bearish SOS; the top (HH, the 0.0 level) then extends on every new
confirmed higher-high (`new_cycle` / `extended` events). The cycle **resets** when price closes
below the locked bottom, and **hides** (stays locked, `active`=false) when price closes above the
top. Level touches use the same 0.618 gate as Structure. Two subtleties kept from Pine: (1) the
macro spans multiple BOS legs — the top keeps extending, it does not reset per leg; (2) unlike
Structure, the Macro does NOT skip its checks on a lock/extend bar, so a level can be reset and
re-touched on the same bar — touch events are therefore edge-detected against the previous bar's
state (`X and not X[1]`), so that same-bar retouch emits no event. **≤5m only** — that timeframe
gate is the caller's job (feed `MacroFib` only ≤5m bars).

---

## Public API

```python
from fibonacci import StructureFib, SniperFib, MacroFib, StructureSnapshot

fib = StructureFib()
sniper = SniperFib()
macro = MacroFib()   # only feed this <=5m bars

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

macro_events = macro.update(bar.index, bar.high, bar.low, bar.close, snap)  # note: needs index + close
macro_events.active          # levels currently computed (cycle locked + visible + range>0)
macro_events.top             # the HH (0.0), .bot = the LL (1.0)
macro_events.locked          # a cycle bottom is locked (may be hidden), .visible = currently shown
macro_events.new_cycle       # a fresh cycle locked THIS bar — event
macro_events.extended        # the top pushed to a new HH THIS bar — event
macro_events.touched         # list[FibTouch] first-reached THIS bar (edge-triggered)
macro_events.levels          # dict{name: price}; names: HH/TP2/TP1/E1/E2/E3/E4/LL
```

---

## Relationship to `market_structure/`

The fib engine is **downstream** of the structure engine and depends only on its PUBLIC output —
never its internals. `StructureSnapshot.from_engine(engine, events)` reads the documented
properties (`active_swing_high/low`, `dir`, `pullback_mode/extreme/extreme_loc`,
`last_confirmed_high/low`) and the documented `ExternalEvents` (`bull/bear_bos`, `bull/bear_sos`,
and the break-leg `bull/bear_bos_high/low` + locs). If you need a new field from structure, add a
read property there (as was done for the pullback getters) — do not reach into `_ext`/`_int`.

The Macro fib also reads `last_confirmed_high/low` (+ locs) and needs the current bar index and
close, so its signature is `macro.update(bar_index, high, low, close, snap)` — the others take only
`(high, low, snap)`.

Same stateful-streaming rationale as `market_structure/` (see its CLAUDE.md): the touch/gate/zone
state carries bar-to-bar and cannot be recomputed from a single bar. Build one `StructureFib`, one
`SniperFib` and one `MacroFib` per symbol/timeframe, feed one closed bar per `update()`.

---

## Do

- Port any change to `mpc_assistant.pine`'s fib blocks back here line-by-line. Keep the gating
  exact — do not reorder or "simplify" the 0.618-gate / targets-from-next-bar / origin-reset logic,
  the Sniper's arm-on-BOS / confirm-once / break-bar-clears-confirm interaction, nor the Macro's
  lock/reset/extend cycle and its edge-vs-previous-bar touch detection.
- When adding a new event or level, update this file's Public API and the tests in the same commit.
- Keep `geometry.py` pure (no state, no I/O) — it is the one core shared by all three fibs.

## Never do

- Do not bake in colours, lines, boxes, or any TradingView drawing concern. This layer emits
  events and prices; drawing is a separate consumer's job.
- Do not reach into `market_structure` engine internals — consume its public reads/events only.
- Do not build a second fib implementation elsewhere. This is the canonical one.
- Do not trust this on live money until the Pine-parity export check below is green.

---

## Validation (Pine ↔ Python parity) — all three fibs GREEN

**Structure fib — GREEN (2026-07-02):** full parity on a `VANTAGE_XAUUSD, 15m` export. Every field
— each level's price, its first-touch pulse, active/dir/origin — matched Python↔Pine across 258
real touch events (E1×52, E2×44, E3×38, E4×34, 1.0×13, TP1×41, TP2×31, TP3×5; TP4/TP5 never reached
in-window).

**Sniper fib — GREEN (2026-07-03):** full parity on a fresh `VANTAGE_XAUUSD, 15m` export (5,431
bars, `--warmup 1116`, exit 0). Every `px_sniper_*` field matched on all 4,315 warm bars, across 57
zones created / 26 confirmed in-window.

**Macro fib — GREEN (2026-07-04):** full parity on a `VANTAGE_XAUUSD, 5m` export (6,862 bars,
`--warmup 2242`, exit 0). Every `px_macro_*` field matched on all 4,620 warm bars, across 3 cycles
locked / 17 top-extends / 15 touch events (2,502 active bars) in-window. The long warmup is
expected: a macro cycle can span thousands of bars, and this export opens mid-cycle (bottom 4098.87
/ top 4889.43 both locked off-window), which cold-started Python can't reproduce until that cycle
ends and an in-window one takes over. The tool only compares Macro when the export actually
exercised it (`px_macro_active` hits 1); on a higher-TF export it prints "Macro present but never
active — export on ≤5m".

The first N bars always mismatch because the Pine export begins warm (chart history before the
window) while the Python engines start cold — the same cold-start pattern as `market_structure/`;
`--warmup N` skips them (the tool prints the last mismatching bar to help pick N). Re-run
`compare_fib.py` after any change to a fib or the fib blocks in `mpc_assistant.pine`.

Wired up, mirrors `market_structure/`'s flow. Two pieces:

1. `indicators/fib_export.pine` — the external structure engine (byte-identical to
   `structure_engine_export.pine`) + the real Structure, Sniper and Macro fibs lifted from
   `mpc_assistant.pine` (compute + state machines, drawing removed) + `plot()` columns for all
   three fibs' outputs (`px_fib_*`, `px_sniper_*`, `px_macro_*`). Put it on a chart, export chart
   data to CSV, drop it in `fibonacci/exports/` (git-ignored). Export on ≤5m to also cover Macro.
2. `fibonacci/tools/compare_fib.py <that.csv>` — runs the REAL pipeline (StructureEngine →
   StructureSnapshot → StructureFib + SniperFib + MacroFib) on the CSV's candles and diffs against
   the `px_fib_*` / `px_sniper_*` / `px_macro_*` columns, bar by bar. Exit 0 = parity. Standard
   library only. Sniper and Macro columns are optional, so the tool also runs on older/higher-TF
   exports (skipping whatever that export doesn't carry).

All three fibs are green. Expect early-bar mismatches on any re-run to be warmup (structure not yet
converged, or a leg/zone/cycle that began before the export window) — parity holds from the first
full in-window leg onward; the Macro needs the longest warmup because a cycle spans many bars.

## Live parity (build this when a bot first consumes the fib engine)

The export check above proves the Python == TradingView **on the same candles**. Live, the bot's
own price feed is the input, so the same math can still land on different numbers if the feed
differs from the chart. Two rules and one check keep the live bot honest:

1. **Same data source.** Point the bot at the feed you chart on. Different broker/feed = different
   candles = different fibs, even with identical code.
2. **Respect warm-up.** The bot starts cold; it must stream enough bars for structure to converge
   before its fib events mean anything (the export check needed ~1,116 warm bars). Don't act on
   fib events during warm-up.
3. **Log every event + re-check.** Have the bot append each fib event it fires (bar time, level,
   price, direction) AND the closed candle it saw, to a small log. Periodically put
   `fib_export.pine` on that same chart/feed and re-run `compare_fib.py` against the bot's logged
   candles. Green = the live bot is measuring exactly what the chart shows. This is the only way to
   catch a silent live drift once there is no chart to eyeball.

Not built yet — there is no bot consuming this engine. Wire it up together with the eventual
`algos/shared/` fib shim.

## References

- Pine source of truth: `indicators/mpc_assistant.pine` (fib blocks `GRP_FIBO` ~2009-2114,
  `GRP_SNIPER` compute ~2510-2551 + zone-touch ~2788-2797, `GRP_MACRO` ~2290-2432) and its live
  "MPC - JARVIS" confirmation table, which defines the event model this engine reproduces.
- Upstream structure engine: `market_structure/CLAUDE.md`.
- Monorepo context: `../CLAUDE.md`.
