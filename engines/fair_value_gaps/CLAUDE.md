# CLAUDE.md — Fair Value Gap Engine Subsystem

**Purpose:** Turn the bar stream into fair-value-gap EVENTS — a price void left by a clean 3-candle
displacement, and the bar it is later mitigated (tapped) on. The signal is the event ("a bull FVG
formed at 101–105.5", "price tapped it"), not the drawing.
**Scope:** FVG geometry + the single live gap list + its lifecycle (form / mitigate / evict) only.
No trading decisions, no structure detection (this engine is standalone — it reads price patterns
directly), no MT5 ops, no UI, no chart rendering (no boxes, no colours, no directional-visibility
filter — that filter is drawing-only in the Pine and is deliberately not reproduced).
**Status:** BUILT + PARITY-VALIDATED — ported line-by-line from `mpc_assistant.pine`'s FVG block,
unit-tested (12 hand-traced tests, green), and **100% Pine parity confirmed** on a real `VANTAGE_XAUUSD, 5m`
export (`compare_fvg.py --warmup 20`, exit 0, 8,578 bars — 2026-07-10). The one canonical implementation —
no consumer builds its own.
**Pine:** ported from `indicators/mpc_assistant.pine` FVG block ("FAIR VALUE GAPS — persist until
mitigated", + the `GRP_FVG` inputs); parity harness is `indicators/fvg_export.pine`, diffed against
this Python by `tools/compare_fvg.py`.
**Last reviewed:** 2026-07-10 (built + Pine-parity-validated, exit 0)

---

## Key paths

```
engines/fair_value_gaps/
├── engine.py       ← the FVG state machine (FairValueGapEngine): detect + cap, then tap/mitigate
├── types.py        ← FairValueGap (a gap); FvgEvents (output)
├── __init__.py     ← re-exports the public API
├── CLAUDE.md       ← this file
├── tests/
│   └── test_engine.py
└── tools/
    └── compare_fvg.py   ← Pine↔Python parity harness (reads a TradingView CSV export)
```

Pine source of truth: `mpc_assistant.pine`'s `GRP_FVG` inputs + the "FAIR VALUE GAPS" compute block.
Parity export build: `indicators/fvg_export.pine`.

---

## What a fair value gap is (ported semantics)

A **bullish FVG** is the void a clean upward 3-candle displacement leaves behind: three consecutive
candles that all close up (`close > open`) with progressively higher closes (`close > close[1] >
close[2]`), and whose displacement bar's low sits above the two-bars-back high (`low > high[2]`). The
gap spans `bottom = high[2]` up to `top = low`. A **bearish FVG** mirrors it (`high < low[2]`; `top =
low[2]`, `bottom = high`). Either way `top > bottom`.

Two things end a gap:

- **Mitigation** — price taps the gap's near edge (bull: `low <= top`; bear: `high >= bottom`). This
  is the real signal — the gap was entered/filled. Emitted as `mitigated`. **Skipped on the gap's own
  creation bar** (`bar_index > born`): a bull gap's top IS that bar's low, so without the guard every
  gap would self-mitigate instantly.
- **Eviction** — the total list already holds `max_count` (default 3) gaps, so the oldest is dropped
  FIFO when a newer one forms. Pine `array.shift`s it silently; **not** a trading signal. Emitted
  separately as `evicted` so a consumer never confuses the two.

Gaps are **not** wiped on a BOS/SOS — the impulse leg that breaks structure is exactly what leaves
the gaps, and the retracement back into them is the entry confluence (this is why the A+ setup reads
them). Only a tap or the FIFO cap removes a gap.

---

## Per-bar order (ported exactly — do not reorder)

Each bar, `update()` runs, mirroring the Pine's two blocks in order:

1. **Detect + cap** — form a bull and/or bear gap on a clean displacement with a real void (and a
   size ≥ `min_ticks * mintick`), then FIFO-drop the oldest while the list exceeds `max_count`.
2. **Tap / mitigate** — remove any gap price tapped this bar (near-edge test, guarded off the
   creation bar).

Detection runs FIRST so a gap created this bar survives the cap and is not tapped on its own bar.
Keep this order identical to Pine.

---

## Timeframes & what it needs

No timeframe branching and **no upstream engine** — FVG is standalone, driven by OHLC alone. It needs:

1. **The right candles.** Same price feed you chart on (see "Live parity" in `engines/fibonacci/CLAUDE.md`
   — the same rule applies once a bot consumes this engine).
2. **Closed bars, in order, one at a time.** The gap list + the 3-bar rolling window carry
   bar-to-bar; feed one closed bar per `update()`, in sequence, never replayed out of order.
3. **Warm-up.** Nothing forms until the first in-window clean displacement; and the first two bars
   can never form (the two-bars-back candle does not exist yet).

The optional **directional filter** in the Pine (`fvgDirOnly` / `st.dir`) only recolours/hides boxes
— it does not add or remove gaps — so this engine does not consume structure. Every gap is emitted
with its `is_bullish` flag; a consumer (e.g. the A+ setup) decides alignment against structure itself.

---

## Public API

```python
from fair_value_gaps import FairValueGapEngine

fvg = FairValueGapEngine()   # max_count=3, min_ticks=0, mintick=0.01 — the Pine defaults

# Each closed bar, in order:
ev = fvg.update(bar.index, bar.open, bar.high, bar.low, bar.close)

for g in ev.formed:      # gaps formed THIS bar (event)
    g.top, g.bottom, g.is_bullish
    g.born_index         # the bar it formed on
    g.id                 # stable id: match a formed gap to its later mitigation
for g in ev.mitigated:   # gaps tapped out THIS bar — price hit the near edge (event)
    ...
for g in ev.evicted:     # gaps aged out past the cap THIS bar — NOT a signal
    ...
ev.active                # live gaps, oldest-first (state) — mirrors the Pine fvg* arrays
```

---

## Do

- Port any change to `mpc_assistant.pine`'s FVG block back here line-by-line. Keep the per-bar order
  (detect+cap → tap), the clean-displacement conditions (all-same-direction + progressive closes),
  the void tests (`low > high[2]` / `high < low[2]`), the near-edge tap edges, the `bar_index > born`
  guard, the size filter and the FIFO cap exact — do not "clean up" or reorder them.
- When adding a new event or field, update this file's Public API and the tests in the same commit.

## Never do

- Do not bake in colours, boxes, or the directional-visibility filter — those are TradingView
  drawing concerns; this layer emits events.
- Do not build a second FVG implementation elsewhere. This is the canonical one.
- Do not let this engine or the FVG block in `mpc_assistant.pine` drift; re-run the parity check
  after any change to either.
- Do not trust this on live money until the Pine-parity export check below is green.

---

## Validation (Pine ↔ Python parity)

**Unit tests — GREEN:** `python3 -m pytest engines/fair_value_gaps/tests/ -q` (12 hand-traced tests
pinning formation, the void + clean-displacement + progressive-close conditions, the two-bar warm-up,
mitigation on both sides, the creation-bar guard, FIFO eviction, and the size filter).

**Full Pine↔Python parity — GREEN (exit 0).** Confirmed 2026-07-10 on a real `VANTAGE_XAUUSD, 5m`
export (8,578 bars): `python3 engines/fair_value_gaps/tools/compare_fvg.py "<that.csv>" --warmup 20`
matched every compared field (all 3 gap slots × top/bottom/is-bull, the count, and the formed/mitigated
pulses) on every bar past warm-up. The 20-bar warm-up is a lingering bear gap in the Pine export whose
displacement began before the export window (price never revisited its near edge, so it never tapped out) —
the cold-started Python engine can't know an off-screen gap; it flushes and realigns by bar 20. The harness:

1. `indicators/fvg_export.pine` — the FVG compute block from `mpc_assistant.pine` (drawing removed,
   the four `fvgTops/fvgBots/fvgIsBull/fvgBorn` arrays kept) + `plot()` columns for the active gap
   arrays (3 slots × top/bottom/is-bull), the count, and the formed/mitigated pulses. Put it on a
   chart, Export chart data → CSV, drop it in `engines/fair_value_gaps/exports/` (git-ignored).
   **Gotcha (fixed 2026-07-10):** the parity plots MUST use a fully-transparent colour
   (`color = color.new(..., 100)`), NOT `display = display.none` — TradingView's "Export chart data"
   silently excludes `display.none` plots from the CSV, so the FVG columns never exported the first
   time. The harness now uses transparent colours (the same trick `fib_export.pine` uses).
2. `engines/fair_value_gaps/tools/compare_fvg.py <that.csv>` — runs `FairValueGapEngine` on the CSV's
   candles and diffs against the `px_fvg_*` columns, bar by bar. The active arrays are compared
   slot-by-slot (oldest first), which proves formation, mitigation AND eviction at once. Exit 0 =
   parity. Standard library only.

Expect early-bar mismatches to be warm-up (the Pine export opens with gaps whose displacement began
before the export window; the cold-started Python engine can't know them — they flush out as they
tap or evict). Use `--warmup N`; the tool prints the last mismatching bar to help pick it. **This
check must exit 0 on a fresh export before the engine is committed as validated.**

## References

- Pine source of truth: `indicators/mpc_assistant.pine` FVG block + `GRP_FVG` inputs.
- Parity export build: `indicators/fvg_export.pine`.
- Consumer (not yet built): the A+ setup sequence — reads live gaps overlapping the fib entry zone
  as confluence. See `docs/ENGINE_EXTRACTION_ROADMAP.md`.
- Sibling in shape (also events-not-visuals off the same indicator): `engines/order_blocks/CLAUDE.md`.
- Monorepo context: `../CLAUDE.md`.
