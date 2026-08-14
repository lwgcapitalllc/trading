# CLAUDE.md — Equal Highs/Lows (EQH/EQL) Engine Subsystem

**Purpose:** Turn the bar stream into EQH/EQL LEVEL EVENTS — when two consecutive same-side strict
price pivots land within an ATR(50)×mult band of each other, a horizontal liquidity level prints
(EQH = buy-side liquidity resting above; EQL = sell-side below) and lives until a candle CLOSES
through it. The signal is the level event ("an EQH formed at 4312.5", "a candle closed above it =
liquidity taken") and the live active-level list, not the dotted line the indicator draws.
**Scope:** ATR(50) tolerance + strict price pivots + the equality rule + FIFO cap + close-through
mitigation only. No trading decisions, no structure detection (this engine is standalone — it reads
price directly), no MT5 ops, no UI, no chart rendering (no lines, no labels, no colours).
**Status:** BUILT + unit-tested (7 tests, green) + **Pine-parity VALIDATED 2026-07-19 (`compare_eq.py`
exit 0** on a fresh 16,639-bar `VANTAGE_XAUUSD, 5m` grand export). The one canonical implementation —
no consumer builds its own. **The real-export run caught a genuine pivot bug** (see "Pivot tie
semantics" below): `ta.pivothigh`/`pivotlow` allow an EQUAL bar on the LEFT of the centre but require a
STRICT extreme on the RIGHT, so the LAST bar of an equal-price run is the pivot; the engine had used
strict-both-sides and silently dropped the frequent raw-price ties on gold. Fixed and re-validated.
**Pine:** ported line-by-line from `indicators/engines/mpc_assistant.pine`'s "EQUAL HIGHS / LOWS (EQH / EQL)"
block (+ the `GRP_EQ` inputs); parity harness is `indicators/engines/eq_export.pine`, diffed against this
Python by `tools/compare_eq.py`.
**Last reviewed:** 2026-07-19 (built + unit-tested + Pine-parity-validated, exit 0; pivot-tie bug fixed).

---

## Key paths

```
engines/equal_highs_lows/
├── engine.py       ← the state machine (EqualHighsLowsEngine): ATR → strict pivots → EQ formation → mitigation
├── types.py        ← EqLevel (one level); EqEvents (output)
├── __init__.py     ← re-exports the public API
├── CLAUDE.md       ← this file
├── tests/
│   └── test_engine.py
├── tools/
│   └── compare_eq.py        ← Pine↔Python parity harness (reads a TradingView CSV export)
└── exports/                 ← drop folder for the TradingView CSV (git-ignored)
```

Pine source of truth: `mpc_assistant.pine`'s `GRP_EQ` inputs + the "EQUAL HIGHS / LOWS" compute block.
Parity export build: `indicators/engines/eq_export.pine`.

---

## What an EQ level is (ported semantics)

Each bar the engine runs `ta.atr(50)` (Wilder) for the equality band `eqTol = atr × eqAtrMult`
(default mult 0.1; 0.0 during the 50-bar ATR warm-up, so early levels need EXACTLY-equal pivots), and
finds price pivots with `ta.pivothigh(high, L, L)` / `ta.pivotlow(low, L, L)` (default width 2, both
sides). A pivot is only **confirmed `L` bars after** the extreme — non-repainting by design.

**Pivot tie semantics (do not "simplify" back to strict-both-sides):** Pine's `ta.pivothigh`/`pivotlow`
are NOT symmetric-strict. The centre may EQUAL bars to its LEFT but must be STRICTLY beyond every bar
to its RIGHT — so the LAST bar of a run of equal-price extremes is the pivot. Raw-price ties are common
on gold (repeated tick values), so this asymmetry is load-bearing: the engine originally used strict on
both sides and dropped every tied pivot, which failed the 2026-07-19 real-export parity until fixed.
`_pivot_high` rejects the candidate if any LEFT bar is strictly higher OR any RIGHT bar is `>=` it (and
the mirror for lows).

- **EQH** — on a confirmed pivot HIGH, compare it to the *previous* confirmed pivot high: if
  `|ph − prev_ph| ≤ eqTol`, a level prints at `max(ph, prev_ph)` (buy-side liquidity resting above),
  anchored at the previous pivot's bar.
- **EQL** — the mirror on a confirmed pivot LOW: a level at `min(pl, prev_pl)` (sell-side below).

Each confirmed pivot becomes the new "previous" for the next comparison (whether or not it formed a
level — the compare-then-latch order, same as `rsi_divergence`). Levels are capped per side at `eqMax`
(default 6, oldest FIFO-evicted). A level is **mitigated** when a candle CLOSES through it — EQH on a
close ABOVE, EQL on a close BELOW (liquidity taken).

## Per-bar order (ported exactly — do not reorder)

Mirrors the Pine `f_processEq()`: **ATR/tol → form EQH → form EQL → mitigate EQH → mitigate EQL.**
Both formations happen before either mitigation, and a level formed this bar is subject to mitigation
this bar. Keep the EQH-then-EQL order and the compare-then-latch order identical to Pine.

## Timeframes & what it needs

No timeframe branching and **no upstream engine** — standalone, a sibling of `fair_value_gaps` and
`rsi_divergence`. It needs the bar's high/low/close (close for ATR True Range + mitigation), closed
bars in order one at a time, and warm-up (ATR is na until bar 50; the first pivot needs `2·L+1` bars;
the first level needs two same-side pivots).

The `showEq` / `showTradeTools` toggles gate the Pine block (drawing + state); this engine **always
computes** (a consumer that wants it off ignores the events) = `showEq = true`, the harness value.

---

## Public API

```python
from equal_highs_lows import EqualHighsLowsEngine

eq = EqualHighsLowsEngine()   # pivot_len=2, atr_mult=0.1, max_levels=6 — the mpc defaults

ev = eq.update(bar.index, bar.high, bar.low, bar.close)   # each closed bar, in order
for lvl in ev.formed:        # levels that printed THIS bar (event)
    lvl.is_high, lvl.price, lvl.left_bar, lvl.formed_bar, lvl.id
for lvl in ev.mitigated:     # levels taken (closed through) THIS bar (event)
    ...
ev.active_eqh, ev.active_eql  # live level prices, oldest→newest (state)
ev.tolerance                  # eqTol this bar (diagnostic)
ev.pivot_high, ev.pivot_low   # strict price pivots confirmed this bar (diagnostic)
```

---

## The FVG-persistence coupling (WIRED 2026-07-18 — Aaron's "exact match" call)

The Pine's EQ block also feeds `f_fvgNearEq` / `eqExemptFvg`: an FVG sitting behind an active EQ level
is EXEMPT from the FVG Max-Active cap (it persists until mitigated). That coupling makes the Pine's FVG
eviction **EQ-aware**, and it is now modelled — via the public-output pattern, NOT by the FVG engine
reaching into this one. This engine only PUBLISHES the active level prices (`active_eqh` / `active_eql`)
+ `tolerance`; the CONSUMER runs EQ first, then passes those into `FairValueGapEngine.update(...,
eq_levels=active_eqh + active_eql, eq_tol=tolerance)`, which skips exempt gaps in its cap. Run EQ BEFORE
FVG (the Pine order). `compare_fvg.py` wires both engines from the `cfg_eq_*` columns `fvg_export.pine`
now carries, and validates the coupling against mpc. Consumers that don't need the exemption pass no EQ
state (plain FIFO). NOTE: `backtest/replay/EngineStack` does not yet wire EQ→FVG (exemption off there) —
a follow-up; the mpc_sos_fade strategy parity is unaffected while it stays off.

---

## Do / Never do

**Do**
- Port any change to `mpc_assistant.pine`'s EQ block back here line-by-line. Keep the ATR(50) Wilder
  tolerance, the strict pivot window, `max`/`min` level price, the compare-then-latch order, the FIFO
  cap and the close-through mitigation exact.
- When adding a new event or field, update this file's Public API and the tests in the same commit.

**Never do**
- Do not bake in colours, dotted lines, or labels — those are TradingView drawing concerns.
- Do not build a second EQH/EQL implementation elsewhere. This is the canonical one.
- Do not let this engine or the EQ block in `mpc_assistant.pine` drift; re-run the parity check after
  any change to either.
- Do not trust this on live money until `compare_eq.py` is exit 0 on a fresh export.

---

## Validation (Pine ↔ Python parity)

**Unit tests — GREEN:** `python3 -m pytest equal_highs_lows/tests/ -q` (7 tests) — the ATR warm-up
tolerance, pivot confirmation lag, single-pivot-no-form → equal-second-pivot-forms (level = max/min +
left anchor), EQH/EQL close-through mitigation, the FIFO cap, and a full array-based reference
cross-check on a random walk (per-bar equality + positive paths, incl. a nonzero-tolerance formation).

**Full Pine↔Python parity — GREEN (exit 0), 2026-07-19.** Confirmed on a fresh 16,639-bar
`VANTAGE_XAUUSD, 5m` grand export (all 11 engine checks on one CSV via `backtest/tools/verify_parity.py`):
`compare_eq.py --warmup 3500` → exit 0, every `px_eq*` column matching after the cold-start. A narrower
9,469-bar export first surfaced the problem as unmatchable pre-window ghost levels (EQH levels above the
window's price ceiling that never mitigate); the wider re-export both cleared those and exposed the real
pivot-tie bug now fixed (see "Pivot tie semantics" above). The harness:

1. `indicators/engines/eq_export.pine` — the EQ compute block from `mpc_assistant.pine` (drawing removed, the
   `eqhPx` / `eqlPx` price arrays kept) + `px_eq*` `plot()` columns: `px_eq_tol`, `px_eq_ph` /
   `px_eq_pl` (confirmed pivots), `px_eqh_new` / `px_eql_new` (this-bar formation price), `px_eqh_cnt`
   / `px_eql_cnt` (active counts) and `px_eqh_0..5` / `px_eql_0..5` (active-level prices, oldest→
   newest slots). Put it on a chart with **showEq ON**, Export chart data → CSV, drop it in
   `engines/equal_highs_lows/exports/` (git-ignored). **Gotcha (same as fvg/rsi_div export):** the
   parity plots use a fully-transparent COLOUR (`color.new(..., 100)`), NOT `display = display.none` —
   TradingView's "Export chart data" excludes `display.none` plots from the CSV.
2. `engines/equal_highs_lows/tools/compare_eq.py <that.csv>` — runs `EqualHighsLowsEngine` on the CSV's
   candles and diffs against the `px_eq*` columns, bar by bar. Exit 0 = parity. Standard library only.
   Pass `--warmup N` (the tool prints the last mismatching bar to help pick it) — the Pine export opens
   with its ATR already warm and may hold active levels + a prior pivot from before the window, so the
   cold-started Python engine converges once its ATR settles and those off-window levels mitigate.

## References

- Pine source of truth: `indicators/engines/mpc_assistant.pine` EQ block + `GRP_EQ` inputs.
- Parity export build: `indicators/engines/eq_export.pine`.
- Siblings in shape (also standalone, events-not-visuals off the same indicator):
  `engines/fair_value_gaps/CLAUDE.md`, `engines/rsi_divergence/CLAUDE.md`.
- Pivot semantics reused from: `engines/market_structure/engine.py` / `engines/rsi_divergence/engine.py`.
- Monorepo context: `../CLAUDE.md`.
