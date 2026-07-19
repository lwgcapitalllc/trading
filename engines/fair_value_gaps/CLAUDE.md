# CLAUDE.md — Fair Value Gap Engine Subsystem

**Purpose:** Turn the bar stream into fair-value-gap EVENTS — a price void left by a 3-candle
imbalance (LuxAlgo definition), and the bar a candle later CLOSES fully past it (mitigation). The
signal is the event ("a bull FVG formed at 101–105.5", "a candle closed past it"), not the drawing.
**Scope:** FVG geometry + the single live gap list + its lifecycle (form / mitigate / evict) only.
No trading decisions, no structure detection (this engine is standalone — it reads price patterns
directly), no MT5 ops, no UI, no chart rendering (no boxes, no colours, no directional-visibility
filter — that filter is drawing-only in the Pine and is deliberately not reproduced).
**Status:** BUILT + **Pine-parity RE-VALIDATED 2026-07-19 (exit 0).** Re-synced 2026-07-18 to a mpc
default drift + defaults reconciled: the middle-bar close-cleared check is now the OPTIONAL
`require_close` flag (Pine `fvgRequireClose`, default False): the gate `(not fvgRequireClose or
close[1] > high[2])` landed in mpc on 2026-07-17, AFTER the last (07-14) validation, so the engine and
`fvg_export.pine` had silently gone stale — both hardcoded the close check while the mpc DEFAULT skips
it. Defaults also reconciled to the Pine: `max_count` 6→10, `threshold_pct` 0.1→0.0 (the sub-15m value;
15m+ uses 0.04). `fvg_export.pine` now carries `cfg_fvg_*` columns and `compare_fvg.py` reads them, so
parity survives any Pine input tweak. Unit-tested (17 hand-traced tests, green). Re-validated at the new
behaviour on a fresh 16,639-bar `VANTAGE_XAUUSD, 5m` grand export — `compare_fvg.py` exit 0 (config +
EQ-exemption coupling read from the CSV's `cfg_*` columns). The one canonical implementation — no
consumer builds its own.
**Pine:** ported from `indicators/mpc_assistant.pine` FVG block ("FAIR VALUE GAPS — persist until
mitigated", + the `GRP_FVG` inputs); parity harness is `indicators/fvg_export.pine`, diffed against
this Python by `tools/compare_fvg.py`.
**Last reviewed:** 2026-07-19 (re-synced to the mpc FVG default drift — optional `require_close`,
reconciled defaults, EQ-exemption coupling; unit tests green; Pine-parity re-validated exit 0 on a fresh
grand export)

---

## Key paths

```
engines/fair_value_gaps/
├── engine.py       ← the FVG state machine (FairValueGapEngine): detect + cap, then mitigate
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

A **bullish FVG** is the 3-candle imbalance the LuxAlgo definition describes: the two outer candles
never overlap (`low > high[2]`) and the gap is at least `threshold_pct`% of price (`(low - high[2]) /
high[2] * 100 > threshold_pct`). The middle displacement bar's close clearing the gap
(`close[1] > high[2]`) is **OPTIONAL** — gated by `require_close` (Pine `fvgRequireClose`, default
False), i.e. `(not require_close or close[1] > high[2])`. At the default the close check is skipped =
the classic FVG. There is **no** clean-impulse or progressive-close requirement — any bars that meet
the conditions qualify. The gap spans `bottom = high[2]` up to `top = low`. A **bearish FVG** mirrors
it (`high < low[2]`; optional `close[1] < low[2]`; `top = low[2]`, `bottom = high`). Either way
`top > bottom`.

Two things end a gap:

- **Mitigation** — a candle **CLOSES fully past the gap's far edge** (bull: `close <= bottom`; bear:
  `close >= top`). A mere wick into the gap no longer removes it. This is the real signal — the gap
  was consumed. Emitted as `mitigated`. **Skipped on the gap's own creation bar** (`bar_index >
  born`), so a fresh gap can't self-mitigate. (Pine also gates this on `barstate.isconfirmed`; the
  engine only ever sees closed bars, so that is always true here.)
- **Eviction** — the total list already holds `max_count` (default 10) gaps, so the OLDEST **not
  exempt by the EQ coupling** is dropped when a newer one forms (Pine scans for the oldest non-EQ gap).
  With no `eq_levels` passed the first gap is never exempt → a plain drop-oldest, unchanged. **Not** a
  trading signal — emitted separately as `evicted`. An FVG behind an active EQH/EQL (`eqExemptFvg`,
  default ON in mpc) is kept until mitigated; if every gap is exempt, none are dropped.

Gaps are **not** wiped on a BOS/SOS — the impulse leg that breaks structure is exactly what leaves
the gaps, and the retracement back into them is the entry confluence (this is why the A+ setup reads
them). Only a close fully past the far edge or the FIFO cap removes a gap.

---

## Per-bar order (ported exactly — do not reorder)

Each bar, `update()` runs, mirroring the Pine's two blocks in order:

1. **Detect + cap** — form a bull and/or bear gap on a 3-candle imbalance (void + middle-close
   cleared + size > `threshold_pct`% of price), then FIFO-drop the oldest while the list exceeds
   `max_count`.
2. **Mitigate** — remove any gap a candle closed fully past this bar (far-edge close test, guarded
   off the creation bar).

Detection runs FIRST so a gap created this bar survives the cap and is not mitigated on its own bar.
Keep this order identical to Pine.

---

## Timeframes & what it needs

No timeframe branching and **no upstream engine** — FVG is standalone, driven by OHLC alone. It needs:

1. **The right candles.** Same price feed you chart on (see "Live parity" in `engines/fibonacci/CLAUDE.md`
   — the same rule applies once a bot consumes this engine).
2. **Closed bars, in order, one at a time.** The gap list + the 3-bar rolling window carry
   bar-to-bar; feed one closed bar per `update()`, in sequence, never replayed out of order.
3. **Warm-up.** Nothing forms until the first in-window qualifying imbalance; and the first two bars
   can never form (the two-bars-back candle does not exist yet).

The optional **directional filter** in the Pine (`fvgDirOnly` / `st.dir`) only recolours/hides boxes
— it does not add or remove gaps — so this engine does not consume structure. Every gap is emitted
with its `is_bullish` flag; a consumer (e.g. the A+ setup) decides alignment against structure itself.

---

## Public API

```python
from fair_value_gaps import FairValueGapEngine

fvg = FairValueGapEngine()   # max_count=10, threshold_pct=0.0, require_close=False — the Pine defaults

# Each closed bar, in order:
ev = fvg.update(bar.index, bar.open, bar.high, bar.low, bar.close)
# To model the mpc `eqExemptFvg` coupling (a gap behind an EQH/EQL survives the cap), run the EQ
# engine FIRST and pass its state — the public-output pattern, so FVG never imports EQ:
#   eq_ev = eq.update(i, h, l, c)
#   ev = fvg.update(i, o, h, l, c, eq_levels=eq_ev.active_eqh + eq_ev.active_eql, eq_tol=eq_ev.tolerance)
# Omit eq_levels for the standalone, exemption-off behaviour (plain FIFO) — nothing else changes.

for g in ev.formed:      # gaps formed THIS bar (event)
    g.top, g.bottom, g.is_bullish
    g.born_index         # the bar it formed on
    g.id                 # stable id: match a formed gap to its later mitigation
for g in ev.mitigated:   # gaps closed fully past THIS bar — a candle closed through the far edge (event)
    ...
for g in ev.evicted:     # gaps aged out past the cap THIS bar — NOT a signal
    ...
ev.active                # live gaps, oldest-first (state) — mirrors the Pine fvg* arrays
```

---

## Do

- Port any change to `mpc_assistant.pine`'s FVG block back here line-by-line. Keep the per-bar order
  (detect+cap → mitigate), the imbalance conditions (void `low > high[2]` / `high < low[2]` + the
  OPTIONAL middle-close-cleared gate `(not fvgRequireClose or close[1] > high[2])` / `(... < low[2])` +
  `%`-of-price threshold), the close-past-far-edge mitigation, the `bar_index > born` guard and the
  FIFO cap exact — do not "clean up" or reorder them. Mirror any new `GRP_FVG` input as a constructor
  arg AND a `cfg_fvg_*` column in `fvg_export.pine` (read by `compare_fvg.py`).
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

**Unit tests — GREEN:** `python3 -m pytest engines/fair_value_gaps/tests/ -q` (17 hand-traced tests
pinning formation, the void + optional middle-close-cleared conditions, that a non-clean / non-progressive
sequence now DOES form a gap, the two-bar warm-up, close-past-far-edge mitigation on both sides, that
a wick no longer mitigates, the creation-bar guard, FIFO eviction, the %-of-price threshold, and the
EQ-exemption cap behaviour).

**Full Pine↔Python parity — GREEN (exit 0), 2026-07-19.** Re-validated at the new behaviour
(`require_close` gate + reconciled defaults 10/0.0 + EQ-exemption coupling) on a fresh 16,639-bar
`VANTAGE_XAUUSD, 5m` grand export. The tool reads the settings from the export's `cfg_fvg_*` /
`cfg_eq_*` columns — run it with NO config flags:
`python3 engines/fair_value_gaps/tools/compare_fvg.py "<that.csv>" --warmup N`. The harness:

1. `indicators/fvg_export.pine` — the FVG compute block from `mpc_assistant.pine` (drawing removed,
   the four `fvgTops/fvgBots/fvgIsBull/fvgBorn` arrays kept) + `plot()` columns for the active gap
   arrays (6 slots × top/bottom/is-bull), the count, the formed/mitigated pulses, the `cfg_fvg_*`
   settings columns (thresh / maxcount / requireclose), AND — to reproduce the `eqExemptFvg` coupling —
   the EQ compute block + `f_fvgNearEq` + the exempt eviction, plus `cfg_eq_*` columns (pivotlen /
   atrmult / max / exempt). `compare_fvg.py` reads `cfg_eq_*`, runs the Python EqualHighsLowsEngine, and
   feeds its active levels + tolerance into the FVG cap — so the coupling is validated, not assumed. Put
   it on a chart, Export chart data → CSV, drop it in `engines/fair_value_gaps/exports/` (git-ignored).
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
