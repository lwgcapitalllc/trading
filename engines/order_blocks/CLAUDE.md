# CLAUDE.md — Order Block Engine Subsystem

**Purpose:** Turn market-structure output into order-block EVENTS — a supply/demand zone created
off each structure break, and the bar it is later mitigated (tapped out) on. The signal is the
event ("a bull OB formed at 4102–4108", "price mitigated it"), not the drawing.
**Scope:** OB zone geometry + the two live OB lists + their lifecycle (create / mitigate / evict)
only. No trading decisions, no structure detection (it consumes `engines/market_structure/`), no MT5 ops,
no UI, no chart rendering (no boxes, no colours).
**Status:** Production — ported line-by-line from `mpc_assistant.pine`, unit-tested (12 hand-traced
tests), and Pine-parity-validated (100%) on two independent real exports: `VANTAGE_XAUUSD, 5m`
(6,727 bars, `--warmup 594`, exit 0) and `VANTAGE_XAUUSD, 15m` (10,197 bars, `--warmup 207`, exit 0).
Every OB field — active bull/bear arrays slot-by-slot, counts, created/mitigated pulses, and the
internal-break origin — matched on every warm bar of both. Two timeframes with no timeframe-specific
branching re-confirms the engine is timeframe-agnostic. **Re-validated 2026-07-09** after the
2026-07-08 structure re-sync (which shifted internal-break timing): the engine code was untouched, but
its harness `indicators/ob_export.pine` embedded the pre-2026-07-08 structure block and was re-synced
first — then `compare_ob.py` passed exit 0 on a fresh `VANTAGE_XAUUSD, 5m` export (12,618 bars,
`--warmup 1133`). The one canonical implementation — no consumer builds its own.
**Pine:** ported from `indicators/mpc_assistant.pine`; parity harness is `indicators/ob_export.pine`, diffed against this Python by `tools/compare_ob.py`. Pine stays in `indicators/` (shared source, TradingView-only toolchain); the CSV + compare tool are the engine's half.
**Last reviewed:** 2026-07-09

---

## Key paths

```
engines/order_blocks/
├── engine.py       ← the OB state machine (OrderBlockEngine): extend/mitigate + external & internal creation
├── types.py        ← OrderBlock (a zone); StructureSnapshot (input); OrderBlockEvents (output)
├── __init__.py     ← re-exports the public API
├── CLAUDE.md       ← this file
├── tests/
│   └── test_engine.py
└── tools/
    └── compare_ob.py   ← Pine↔Python parity harness (reads a TradingView CSV export)
```

Pine source of truth: `indicators/mpc_assistant.pine` OB blocks — the type + `manageOBs`/`extendOBs`
(lines 38-66), external-break creation (863-895), internal-break creation (1290-1317).
Parity export build: `indicators/ob_export.pine`.

---

## What an order block is (ported semantics)

A **bullish OB** is the last DOWN candle before an up-break of structure — a demand zone to buy
from. A **bearish OB** is the last UP candle before a down-break — a supply zone to sell from. The
zone spans the candle's full high/low (or its body extremes when `body_only=True`).

On each structure break, the engine scans **back from the break-leg origin** (up to +20 bars) for
the first opposite-colour candle and drops an OB across it. Two things kill an OB:

- **Mitigation** — price closes through the far edge (bull OB: `close < bottom`; bear OB:
  `close > top`). This is the real signal: the zone was consumed. Emitted as `mitigated`.
- **Eviction** — the per-direction list already holds `max_active` (default 6) OBs, so the oldest
  is dropped FIFO when a new one is pushed. Pine deletes the box silently; **not** a trading
  signal. Emitted separately as `evicted` so a consumer never confuses the two.

Both the EXTERNAL structure break (BOS/SOS) and the INTERNAL structure break (iBOS/iSOS) create OBs
into the SAME two arrays. That shared-array coupling is why the port includes both paths and why
the per-bar order is fixed (see below) — porting only one path would guarantee a parity mismatch.

---

## Per-bar order (ported exactly — do not reorder)

Each bar, `update()` runs, mirroring `mpc_assistant.pine`'s execution order:

1. **Extend + mitigate both arrays** — mitigation runs FIRST, so a freshly created OB is never
   mitigated on its own creation bar.
2. **External-break creation** — bull, then bear (`st.bull_bos or st.bull_sos` scanning back from
   `bull_bos_l_loc`; bear mirror from `bear_bos_h_loc`).
3. **Internal-break creation** — bull, then bear (`int_bull_break` / `int_bear_break` scanning back
   from the shared `int_break_origin_loc`).

This order drives which OBs survive the `max_active` cap when several are created/evicted on one
bar. Keep it identical to Pine.

---

## Timeframes & what it needs

No timeframe branching — the same code runs on every TF (unlike the Macro fib, which is ≤5m only).
To be accurate the engine needs, exactly like `engines/fibonacci/`:

1. **An accurate structure engine.** OBs are downstream of `engines/market_structure/` — wrong structure →
   wrong OBs. It is the foundation.
2. **The right candles.** Same price feed you chart on (see "Live parity" in `engines/fibonacci/CLAUDE.md`
   — the same rule applies here once a bot consumes this engine).
3. **Closed bars, in order, one at a time.** The two OB lists + the rolling OHLC window carry
   bar-to-bar; feed one closed bar per `update()`, in sequence, never replayed out of order.
4. **Warm-up.** Nothing forms until the first in-window break; and the bars-ago lookback needs
   history (an OB can reference a candle up to 519 bars back). Don't act on events during warm-up.

---

## Public API

```python
from order_blocks import OrderBlockEngine, StructureSnapshot

ob = OrderBlockEngine()   # max_active=6, body_only=False — the Pine defaults

# Each closed bar, right after market_structure's engine.update(bar) -> events:
snap = StructureSnapshot.from_engine(structure_engine, events)
ob_events = ob.update(bar.index, bar.open, bar.high, bar.low, bar.close, snap)

for o in ob_events.created:      # OBs created THIS bar (event)
    o.top, o.bottom, o.is_bullish
    o.origin_index               # bar index of the OB candle itself
    o.created_index              # bar index of the break that made it
    o.id                         # stable id: match a created OB to its later mitigation
for o in ob_events.mitigated:    # OBs tapped out THIS bar — price closed through the far edge (event)
    ...
for o in ob_events.evicted:      # OBs aged out past the cap THIS bar — NOT a signal
    ...
ob_events.active_bull            # live bull OBs, oldest-first (state) — mirrors Pine activeBullOBs
ob_events.active_bear            # live bear OBs, oldest-first (state) — mirrors Pine activeBearOBs
```

Note `update()` takes the bar index + full OHLC (the bars-ago scan needs the candle history and the
origin location); the snapshot carries only the structure engine's break flags + leg locations.

---

## Relationship to `engines/market_structure/`

Order Blocks is a **sibling** of `engines/fibonacci/`, not downstream of it: both consume
`engines/market_structure/` directly and keep their own decoupled `StructureSnapshot`. It reads only the
structure engine's PUBLIC output — never its internals. `StructureSnapshot.from_engine(engine,
events)` reads the documented `ExternalEvents` (`bull/bear_bos`, `bull/bear_sos`, and the break-leg
`bull_bos_l_loc` / `bear_bos_h_loc`) and `InternalEvents` (`int_bull_break`, `int_bear_break`,
`int_break_origin_loc`).

**The three internal-break fields were added to `engines/market_structure/` for this engine.** They are a
purely additive, capture-only exposure of state the structure engine already computed (mirroring
Pine's `int_bull_break` / `int_bear_break` / `int_break_origin_loc`), set at the six internal-break
sites — no structure logic changed, and structure parity was re-confirmed unbroken. If you need a
new field from structure, add a capture like that — do not reach into `_ext`/`_int`.

Same stateful-streaming rationale as `engines/market_structure/` and `engines/fibonacci/`: build one
`OrderBlockEngine` per symbol/timeframe, feed one closed bar per `update()`.

---

## Do

- Port any change to `mpc_assistant.pine`'s OB blocks back here line-by-line. Keep the per-bar
  order (mitigate → external create → internal create), the +20-bar first-opposite-colour scan, the
  `lookbackIdx < 500` guard, the mitigation edges (`close < bottom` / `close > top`) and the FIFO
  cap exact — do not "clean up" or reorder them.
- When adding a new event or field, update this file's Public API and the tests in the same commit.

## Never do

- Do not bake in colours, boxes, or any TradingView drawing concern. This layer emits events; the
  Pine `box bg` field and every `box.*` call are deliberately dropped.
- Do not reach into `market_structure` engine internals — consume its public reads/events only.
- Do not build a second OB implementation elsewhere. This is the canonical one.
- Do not let this engine or the OB blocks in `mpc_assistant.pine` drift; re-run the parity check
  (below) after any change to either.

---

## Validation (Pine ↔ Python parity)

**Unit tests — GREEN:** `python3 -m pytest engines/order_blocks/tests/ -q` (12 hand-traced tests pinning
creation, the first-opposite-colour scan, body-only geometry, the lookback guards, mitigation, FIFO
eviction, and the shared internal-break path).

**Smoke — GREEN:** run over a real `VANTAGE_XAUUSD, 15m` export the engine produced 196 OBs / 153
mitigations / 40 evictions, and the new `int_bull_break` / `int_bear_break` fields matched Pine's
existing `px_i_bull_break` / `px_i_bear_break` export columns on every warm bar (0 mismatches).

**Full Pine↔Python parity — GREEN (2026-07-04).** 100% match on a real `VANTAGE_XAUUSD, 5m` export
(6,727 bars): every OB field matched on all 6,133 warm bars (`--warmup 594`, exit 0). The first 594
bars mismatch only because the TradingView chart had history before the export window, so Pine's
arrays opened already holding 3 bull + 5 bear OBs whose origin candles were off-screen; the Python
engine starts cold and cannot know them. Those phantom OBs flush (mitigate or FIFO-evict) out of
Pine's arrays by bar 594, and the two engines are bar-for-bar identical from there — the same
warm-start offset the structure engine has.

**Re-validated — GREEN (2026-07-09).** After the 2026-07-08 structure re-sync shifted internal-break
timing, `indicators/ob_export.pine` (which embeds the structure engine) was found still on the
2026-07-04 structure block. It was re-synced with the two f2a8411 changes — the bear-BOS fallback
swing-high scan and the internal-reset now firing on an external BOS too — leaving its `process`
method byte-identical to the current `structure_engine_export.pine` and its internal state machine
differing only by the OB creation blocks. `compare_ob.py` then passed on a fresh `VANTAGE_XAUUSD, 5m`
export (12,618 bars, `--warmup 1133`, exit 0): every OB field matched on every warm bar. The OB
**engine code was untouched** — only the harness was re-synced. The 1133-bar warm-up is the cold-start
(Pine opened holding 6 pre-window bull OBs; the bull side flushed them by bar 1132, bear by bar 29).

The harness mirrors the `engines/market_structure/` and
`engines/fibonacci/` flow:

1. `indicators/ob_export.pine` — `structure_engine_export.pine` (the byte-identical structure
   engine, external + internal) + the OB blocks from `mpc_assistant.pine` (drawing removed) +
   `plot()` columns for the active OB arrays (6 slots × top/bottom per direction), counts,
   created/mitigated pulses, and `px_i_break_origin_ago` (the one internal field with no prior
   column). Put it on a chart, Export chart data → CSV, drop it in `engines/order_blocks/exports/`
   (git-ignored).
2. `engines/order_blocks/tools/compare_ob.py <that.csv>` — runs the REAL pipeline (StructureEngine →
   StructureSnapshot → OrderBlockEngine) on the CSV's candles and diffs against the `px_ob_*`
   columns, bar by bar. The active arrays are compared slot-by-slot (oldest first), which proves
   creation, mitigation AND eviction at once. Exit 0 = parity. Standard library only.

Early-bar mismatches are warmup (structure not yet converged, or a pre-window OB still lingering in
Pine's arrays); the tool prints the last mismatching bar so you can pick `--warmup N`. Re-run
`compare_ob.py` after any change to the OB blocks in `mpc_assistant.pine` or to this engine.

## References

- Pine source of truth: `indicators/mpc_assistant.pine` OB blocks (38-66 / 863-895 / 1290-1317).
- Parity export build: `indicators/ob_export.pine`.
- Upstream structure engine: `engines/market_structure/CLAUDE.md`.
- Sibling engine (same pattern, downstream of the same structure engine): `engines/fibonacci/CLAUDE.md`.
- Monorepo context: `../CLAUDE.md`.
