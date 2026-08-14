# CLAUDE.md — RSI Divergence Engine Subsystem

**Purpose:** Turn the bar stream into RSI-DIVERGENCE EVENTS — a confirmed regular divergence at the
extremes (price lower-low while RSI higher-low from oversold = bullish; the overbought mirror =
bearish) — plus the live confluence flags (`bull_active` / `bear_active`) a consumer reads. The
signal is the event ("a bullish RSI divergence confirmed, price low 891.4 vs prior 917.3, RSI 11.4
vs 10.0") and the live flag, not the dotted line the indicator draws.
**Scope:** Wilder's RSI + strict RSI pivots + the regular-divergence rule + the live-confluence
window only. No trading decisions, no structure detection (this engine is standalone — it reads
price + RSI directly), no MT5 ops, no UI, no chart rendering (no lines, no labels, no colours).
**Status:** BUILT + PARITY-VALIDATED — ported line-by-line from `mpc_assistant.pine`'s "RSI
DIVERGENCE" block, unit-tested (9 tests, green), and **100% Pine parity confirmed** on a real
`VANTAGE_XAUUSD, 5m` export (`compare_rsi_div.py --warmup 1630`, exit 0, 9,830 bars — every field
matched on all 8,200 warm bars — 2026-07-11, at the then-defaults divOS 30 / divOB 70). The one
canonical implementation — no consumer builds its own.
**Re-validated at divOS 25 / divOB 75 (2026-07-11):** the mpc re-paste changed the divergence-gate
defaults 30→25 / 70→75. Synced here in code (engine defaults + harness + compare tool + tests + docs;
9 tests green), then **re-confirmed 100% parity on a fresh 25/75 `VANTAGE_XAUUSD, 5m` export (16,887
bars): `compare_rsi_div.py --warmup 8762` → exit 0**, every field matching and the divergence pulses
matching from bar 16. The larger warm-up (vs the 1,630 at 30/70) is benign and verified: the `bull/bear_age`
columns cold-start against an off-window divergence Pine carries in from before the export, and at the
stricter 25/75 gate the first mutually-agreed in-window divergence that resets the bear-age counter lands
near bar 8761. **Pivot-tie fix (2026-07-19):** the earlier RSI-pivot "float-ties" (RSI equal to a
neighbour to ~1e-14, which Pine's `ta.pivothigh` confirmed and the old strict-both-sides Python skipped)
were NOT an inherent limitation — they were the same real pivot bug found in the `equal_highs_lows`
engine. Pine's `ta.pivothigh`/`pivotlow` allow an EQUAL bar on the LEFT of the centre but require a
STRICT extreme on the RIGHT (the last bar of an equal run is the pivot); this engine now matches that
(`_pivot_high_rsi` rejects if any LEFT bar is strictly higher OR any RIGHT bar is `>=` it, mirror for
lows). Re-validated exit 0 on the 2026-07-19 16,639-bar grand export with ZERO tie exceptions remaining.
Detection formula unchanged (parameterized threshold); only the default constant moved.
**Pine:** ported from `indicators/engines/mpc_assistant.pine`'s RSI DIVERGENCE block (+ the `GRP_DIV`
inputs); parity harness is `indicators/engines/rsi_div_export.pine`, diffed against this Python by
`tools/compare_rsi_div.py`.
**Last reviewed:** 2026-07-19 (built + unit-tested + Pine-parity-validated exit 0; pivot-tie bug fixed).

---

## Key paths

```
engines/rsi_divergence/
├── engine.py       ← the state machine (RsiDivergenceEngine): Wilder RSI → RSI pivots → divergence
├── types.py        ← RsiDivergence (one divergence); RsiDivEvents (output)
├── __init__.py     ← re-exports the public API
├── CLAUDE.md       ← this file
├── tests/
│   └── test_engine.py
├── tools/
│   └── compare_rsi_div.py   ← Pine↔Python parity harness (reads a TradingView CSV export)
└── exports/                 ← drop folder for the TradingView CSV (git-ignored)
```

Pine source of truth: `mpc_assistant.pine`'s `GRP_DIV` inputs + the "RSI DIVERGENCE" compute block.
Parity export build: `indicators/engines/rsi_div_export.pine`.

---

## What an RSI divergence is (ported semantics)

The engine runs Wilder's RSI (`ta.rsi(close, rsi_len)`, default length 14) and finds its pivots with
`ta.pivotlow` / `ta.pivothigh` (default width 5, both sides). A pivot is only **confirmed
`pivot_len` bars after** the extreme — the signal prints a few bars late, non-repainting by design.

- **Bullish divergence** — on a confirmed RSI pivot LOW, compare it to the *previous* RSI pivot low:
  a LOWER price low (`price < prev_price`) with a HIGHER RSI low (`rsi > prev_rsi`), and the lower of
  the two RSI lows ≤ the **oversold** level (default 25). The price anchor is `low[pivot_len]` — the
  bar's low AT the RSI-pivot bar, not a separately detected price pivot.
- **Bearish divergence** — the mirror on a confirmed RSI pivot HIGH: a HIGHER price high with a LOWER
  RSI high, the higher of the two RSI highs ≥ the **overbought** level (default 75).

Each confirmed pivot becomes the new "previous" for the next comparison (whether or not it fired a
divergence). A divergence stays **live confluence** (`bull_active` / `bear_active`) for `valid_bars`
bars (default 100) after its pivot bar — that is the flag the A+ setup row reads.

Three Pine details are kept exactly (see the module docstring), because dropping any would diverge
from the chart:

1. **Wilder's RSI**, not a simple average of gains — `ta.rma`-smoothed up/down, seeded by the SMA of
   the first `rsi_len` changes. `_RsiState`/`_Rma` reproduce `ta.rma` (SMA seed → recursion) exactly;
   RSI is `None` (Pine na) until bar `rsi_len`.
2. **Pivots with Pine's tie rule** — over the `(2·pivot_len + 1)`-bar window centred on the candidate,
   the centre may EQUAL bars to its LEFT but must be STRICTLY beyond every bar to its RIGHT (so the last
   bar of an equal run is the pivot — Pine's `ta.pivothigh`/`pivotlow` behaviour, NOT strict-both-sides).
   Only resolvable `pivot_len` bars after the fact.
3. **The price anchor is `low[pivot_len]` / `high[pivot_len]`** — the price extreme at the RSI-pivot
   bar (which IS `pivot_len` bars back), not an independent price pivot.

---

## Per-bar order (ported exactly — do not reorder)

Each bar, `update()` runs, mirroring the Pine block:

1. **RSI** — feed the close into Wilder's RSI.
2. **Pivots** — test the centred candidate for a strict RSI pivot low and/or high (needs a full
   window; `None` otherwise).
3. **Bullish block** — on a confirmed pivot low, test the divergence rule against the previous pivot
   low, emit on success, then latch this pivot as the new previous.
4. **Bearish block** — the mirror on a confirmed pivot high.
5. **Live flags** — recompute `bull_active` / `bear_active` from the most recent divergence pivot.

Keep the bull-then-bear order and the "compare-then-latch" order identical to Pine.

---

## Timeframes & what it needs

No timeframe branching and **no upstream engine** — RSI divergence is standalone (a sibling of
`fair_value_gaps` in shape). It needs:

1. **The right candles.** Same price feed you chart on (see "Live parity" in
   `engines/fibonacci/CLAUDE.md` — the same rule applies once a bot consumes this engine).
2. **Closed bars, in order, one at a time.** The RSI recursion, the pivot window and the previous-
   pivot / last-divergence state all carry bar-to-bar; feed one closed bar per `update()`, in
   sequence, never replayed out of order.
3. **Warm-up.** RSI is `None` until bar `rsi_len`; the first pivot needs `2·pivot_len + 1` warm RSI
   bars; the first divergence needs two pivots of the same side.

The `showDiv` input in the Pine gates the whole block (drawing + state). This engine **always
computes** (a consumer that wants it off just ignores the events), which equals `showDiv = true` —
the value the parity harness uses.

---

## Public API

```python
from rsi_divergence import RsiDivergenceEngine

div = RsiDivergenceEngine()  # rsi_len=14, pivot_len=5, oversold=25, overbought=75, valid_bars=100

# Each closed bar, in order:
ev = div.update(bar.index, bar.high, bar.low, bar.close)

for d in ev.detected:  # divergences confirmed THIS bar (event)
    d.is_bullish
    d.pivot_bar, d.pivot_price, d.pivot_rsi  # the newly confirmed pivot (line's "now" end)
    d.prev_bar, d.prev_price, d.prev_rsi  # the previous same-side pivot (other end)
    d.id  # stable id
ev.bull_active  # live bullish confluence (state) — mirrors Pine bullDivActive
ev.bear_active  # live bearish confluence (state) — mirrors Pine bearDivActive
ev.rsi  # current RSI value (diagnostic; None during warm-up)
ev.pivot_low_rsi  # RSI pivot low confirmed THIS bar (Pine divPlRsi), else None
ev.pivot_high_rsi  # RSI pivot high confirmed THIS bar (Pine divPhRsi), else None
```

---

## Do

- Port any change to `mpc_assistant.pine`'s RSI DIVERGENCE block back here line-by-line. Keep the
  Wilder RSI (SMA-seeded RMA), the strict pivot window, the price anchor `low[pivot_len]` /
  `high[pivot_len]`, the divergence rule (direction + oversold/overbought gate), the compare-then-
  latch order and the `valid_bars` window exact — do not "clean up" or reorder them.
- When adding a new event or field, update this file's Public API and the tests in the same commit.

## Never do

- Do not bake in colours, dotted lines, or labels — those are TradingView drawing concerns; this
  layer emits events.
- Do not build a second RSI-divergence implementation elsewhere. This is the canonical one.
- Do not let this engine or the RSI DIVERGENCE block in `mpc_assistant.pine` drift; re-run the parity
  check after any change to either.
- Do not trust this on live money until the Pine-parity export check below is green — it is green as
  of 2026-07-11; re-run it after any change to this engine or the mpc block.

---

## Validation (Pine ↔ Python parity)

**Unit tests — GREEN:** `python3 -m pytest rsi_divergence/tests/ -q` (9 tests) — RSI warm-up, RSI vs
an independent textbook Wilder implementation, pivot timing/offset/strictness, the oversold and
overbought gates, the live-flag window, and a full array-based reference (RSI pivots + divergence
rule + ages) cross-checked against the streaming engine on a multi-swing series that fires several
bullish and bearish divergences.

**Full Pine↔Python parity — GREEN (exit 0).** Confirmed 2026-07-11 on a real `VANTAGE_XAUUSD, 5m`
export (9,830 bars): `python3 engines/rsi_divergence/tools/compare_rsi_div.py "<that.csv>" --warmup 1630`
matched every compared field — the RSI value, both RSI pivots (`px_div_pl`/`px_div_ph`), both
divergence pulses, both live-active flags, and both ages — on all 8,200 warm bars. The 1,630-bar
warm-up is the cold-start: the Pine export opens with its RSI already smoothed and holding off-window
pivots/divergences (its first-bar ages are 471 / 1902), so the cold-started Python engine only aligns
once its Wilder RMA has settled and its own in-window divergences supersede Pine's off-window ones.
The harness:

1. `indicators/engines/rsi_div_export.pine` — the RSI DIVERGENCE compute block from `mpc_assistant.pine`
   (drawing removed) + `plot()` columns: `px_div_rsi`, `px_div_pl` / `px_div_ph` (the confirmed RSI
   pivots), `px_div_bull` / `px_div_bear` (this-bar divergence pulses), `px_div_bull_active` /
   `px_div_bear_active` (the live flags), and `px_div_bull_age` / `px_div_bear_age` (bars since the
   most recent divergence's pivot — an index DIFFERENCE, so it survives Pine's absolute `bar_index`
   vs Python's 0-based row index). Put it on a chart with **showDiv ON**, Export chart data → CSV,
   drop it in `engines/rsi_divergence/exports/` (git-ignored).
   **Gotcha (same as `fvg_export.pine`):** the parity plots use a fully-transparent colour
   (`color = color.new(..., 100)`), NOT `display = display.none` — TradingView's "Export chart data"
   silently excludes `display.none` plots from the CSV.
2. `engines/rsi_divergence/tools/compare_rsi_div.py <that.csv>` — runs `RsiDivergenceEngine` on the
   CSV's candles and diffs against the `px_div_*` columns, bar by bar. Exit 0 = parity. Standard
   library only. Pass `--warmup N` to skip the cold-start bars (the tool prints the last mismatching
   bar to help pick it; `--warmup 1630` on the validated export).

Expect early-bar mismatches to be warm-up: the Pine export opens with its RSI already smoothed and may
hold an off-window pivot / divergence, while the cold-started Python engine seeds its Wilder RMA from
row 0 and has no prior pivots — both converge once the RMA settles (an IIR filter, so the seed
influence decays) and the engine establishes its own in-window pivots. The RSI-value columns use an
abs tolerance (default 1e-2) to absorb CSV rounding; the pulses, flags and ages compare exactly.
**This check must exit 0 on a fresh export before the engine is committed as validated.**

## References

- Pine source of truth: `indicators/engines/mpc_assistant.pine` RSI DIVERGENCE block + `GRP_DIV` inputs.
- Parity export build: `indicators/engines/rsi_div_export.pine`.
- Consumer (not yet built): the A+ setup sequence — reads `bull_active` / `bear_active` as a
  confluence tag on its READY/EARLY row. See `docs/ENGINE_EXTRACTION_ROADMAP.md`.
- Sibling in shape (also standalone, events-not-visuals off the same indicator):
  `engines/fair_value_gaps/CLAUDE.md`.
- Pivot semantics reused from: `engines/market_structure/engine.py` (`_pivot_at_current_bar`).
- Monorepo context: `../CLAUDE.md`.
