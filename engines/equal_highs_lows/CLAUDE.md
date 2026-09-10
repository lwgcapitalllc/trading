# CLAUDE.md — Equal Highs/Lows (EQH/EQL) Engine Subsystem

**Purpose:** Turn the bar stream into EQH/EQL LEVEL EVENTS — when two consecutive same-side strict
price pivots land within an ATR(50)×mult band of each other, a horizontal liquidity level prints
(EQH = buy-side liquidity resting above; EQL = sell-side below) and lives until a candle TRADES
through it. The signal is the level event ("an EQH formed at 4312.5", "a candle closed above it =
liquidity taken") and the live active-level list, not the dotted line the indicator draws.
**Scope:** ATR(50) tolerance + strict price pivots + the equality rule + FIFO cap + wick-through
mitigation only. No trading decisions, no structure detection (this engine is standalone — it reads
price directly), no MT5 ops, no UI, no chart rendering (no lines, no labels, no colours).
**Status:** BUILT + unit-tested (11 tests, green) + **Pine-parity VALIDATED 2026-07-19 (`compare_eq.py`
exit 0** on a fresh 16,639-bar `VANTAGE_XAUUSD, 5m` grand export). The one canonical implementation —
no consumer builds its own. **The real-export run caught a genuine pivot bug** (see "Pivot tie
semantics" below): `ta.pivothigh`/`pivotlow` allow an EQUAL bar on the LEFT of the centre but require a
STRICT extreme on the RIGHT, so the LAST bar of an equal-price run is the pivot; the engine had used
strict-both-sides and silently dropped the frequent raw-price ties on gold. Fixed and re-validated.
**Pine:** ported line-by-line from `indicators/engines/mpc_jarvis.pine`'s "EQUAL HIGHS / LOWS (EQH / EQL)"
block (+ the `GRP_EQ` inputs); parity harness is `indicators/engines/eq_export.pine`, diffed against this
Python by `tools/compare_eq.py`.
**Last reviewed:** 2026-09-09 (mitigation moved close → wick, defaults synced to the indicator, gate re-run green on two fresh exports).

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

Pine source of truth: `mpc_jarvis.pine`'s `GRP_EQ` inputs + the "EQUAL HIGHS / LOWS" compute block.
Parity export build: `indicators/engines/eq_export.pine`.

---

## What an EQ level is (ported semantics)

Each bar the engine runs `ta.atr(50)` (Wilder) for the equality band `eqTol = atr × eqAtrMult`
(default mult 0.25; 0.0 during the 50-bar ATR warm-up, so early levels need EXACTLY-equal pivots), and
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
(default 14, oldest FIFO-evicted). A level is **mitigated** when a candle TRADES through it — EQH when
the HIGH goes above, EQL when the LOW goes below (liquidity taken).

🔴 **THIS WAS A CLOSE RULE UNTIL 2026-09-09, AND THE INDICATOR HAD BEEN AHEAD OF IT SINCE
2026-08-04.** The Pine comment at that block recorded the split as deliberate and named this engine
as a copy left behind — **written down, then never carried, which is how a KNOWN divergence becomes
an unknown one.** The Pine's reason for the wick is stability on the live bar: a high only grows
within a bar, so once it clears it stays cleared, while a close test can delete a level intrabar and
restore it on the next tick.
⚠ **MEASURED before it was applied, because this engine feeds the LIVE SOS Fade bot's entry filter**
(its levels exempt gaps from the FVG cap). 157,004 M15 bars, PU Prime `XAUUSD.p`, 2020-01-01 →
2026-08-23, both rules replayed off ONE cache: levels FORMED identical at 3,552, mitigations
3,400 → 3,470, total level lifetime −10% (698,476 → 628,956 level-bars). **SOS Fade's trade list is
byte-identical (245 rows); one setup row moves, in its recorded edge price alone.**
⚠ **That is THIS window and THIS strategy, not a general safety claim** — the rule kills 70 more
levels, so any consumer reading level LIFETIME rather than the gap cap will move.
⚠ **The other two bots are unaffected by construction, checked not assumed:** B-LEG pins the
coupling off and the extreme leg never pins it, so it inherits the stack default of off.
⚠ **`indicators/engines/eq_export.pine` moved in the SAME commit.** It is the file `compare_eq.py`
diffs against, so fixing the engine alone would turn the gate red and read as the engine being
wrong. ✅ **GATE GREEN on a fresh export, 2026-09-09** — `compare_eq.py` exit 0 over 20,148 bars of
`VANTAGE_XAUUSD, 15_75653.csv` at the engine's own defaults (pivot 2 / mult 0.1 / max 6). ⚠ **The
green was checked for MEANING, not just taken:** the pre-fix close-rule engine was run against the
SAME file and goes RED across every level slot, so this gate can tell the two rules apart rather
than passing whatever it is handed.
✅ **AND THE ENGINE REPRODUCES THE INDICATOR AT ITS OWN SETTINGS TOO** — a second export
(`15_808e9.csv`, mult 0.25) is exit 0 at `--atr-mult 0.25 --max-levels 14`. 🔴 **So the engine's
LOGIC is right at both settings and the 0.1/6-vs-0.25/14 gap is a DEFAULTS choice, not a parity
break** — worth stating plainly, because a red gate at the wrong cap looks exactly like a broken
engine: at `--max-levels 6` against the 0.25 export every slot mismatches on ~half the bars, purely
because the harness plots the FIRST six of a fourteen-deep array while a six-cap engine keeps the
NEWEST six.
✅ **THE DEFAULTS GAP IS CLOSED (2026-09-09, Aaron's call): everything here now ships the
INDICATOR's 2 / 0.25 / 14.** It had been 0.1 / 6 in the engine, the stack, the gate and this
harness, so the live bot was running a DIFFERENT equality band and a DIFFERENT level cap from the
chart the setups are read off — and the harness comment claimed the two matched.
⚠ **MEASURED BEFORE THE SWITCH over the same 157,004 bars: SOS Fade's trade list is IDENTICAL
either way (244 rows), and exactly four setup rows move.** Those four are the whole reason the run
is trustworthy — a change that moved NOTHING would equally mean the setting never reached the
engine, which is the trap this repo has paid for before.
🔴 **SIX copies of these three numbers had to move together** — `engine.py`, `backtest/replay/
stack.py`, `tools/compare_eq.py`, `indicators/engines/eq_export.pine`, and the Command Center's
`services/fvg_overlays.py` constants plus the test that pins them. **A default duplicated six ways
is a default that drifts**, and this one drifted for as long as it existed.

## Per-bar order (ported exactly — do not reorder)

Mirrors the Pine `f_processEq()`: **ATR/tol → form EQH → form EQL → mitigate EQH → mitigate EQL.**
Both formations happen before either mitigation, and a level formed this bar is subject to mitigation
this bar. Keep the EQH-then-EQL order and the compare-then-latch order identical to Pine.

## Timeframes & what it needs

No timeframe branching and **no upstream engine** — standalone, a sibling of `fair_value_gaps` and
`rsi_divergence`. It needs the bar's high/low/close (close for ATR True Range; high/low for mitigation), closed
bars in order one at a time, and warm-up (ATR is na until bar 50; the first pivot needs `2·L+1` bars;
the first level needs two same-side pivots).

The `showEq` / `showTradeTools` toggles gate the Pine block (drawing + state); this engine **always
computes** (a consumer that wants it off ignores the events) = `showEq = true`, the harness value.

---

## Public API

```python
from equal_highs_lows import EqualHighsLowsEngine

eq = EqualHighsLowsEngine()   # pivot_len=2, atr_mult=0.25, max_levels=14 — the mpc defaults

ev = eq.update(bar.index, bar.high, bar.low, bar.close)   # each closed bar, in order
for lvl in ev.formed:        # levels that printed THIS bar (event)
    lvl.is_high, lvl.price, lvl.left_bar, lvl.formed_bar, lvl.id
for lvl in ev.mitigated:     # levels taken (traded through) THIS bar (event)
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
state (plain FIFO).
🔴 **THAT NOTE SAID `backtest/replay/EngineStack` DOES NOT YET WIRE EQ→FVG AND IT HAS FOR SOME TIME
(corrected 2026-09-09).** The stack carries `eq_exempt_fvg` and builds this engine when it is on, and
`strategies/python/sos_fade` turns it ON — so this coupling is in the LIVE bot's decision path, not a
follow-up. **That stale sentence is why the wick change was nearly treated as a lab-only tidy-up**;
the doc said the live path could not reach this engine. ⚠ B-LEG pins it OFF and the extreme leg never
pins it, so both inherit the stack default of off — checked, not assumed.

---

## Do / Never do

**Do**
- Port any change to `mpc_jarvis.pine`'s EQ block back here line-by-line. Keep the ATR(50) Wilder
  tolerance, the strict pivot window, `max`/`min` level price, the compare-then-latch order, the FIFO
  cap and the wick-through mitigation exact.
- When adding a new event or field, update this file's Public API and the tests in the same commit.

**Never do**
- Do not bake in colours, dotted lines, or labels — those are TradingView drawing concerns.
- Do not build a second EQH/EQL implementation elsewhere. This is the canonical one.
- Do not let this engine or the EQ block in `mpc_jarvis.pine` drift; re-run the parity check after
  any change to either.
- Do not trust this on live money until `compare_eq.py` is exit 0 on a fresh export.

---

## Validation (Pine ↔ Python parity)

**Unit tests — GREEN:** `python3 -m pytest equal_highs_lows/tests/ -q` (11 tests) — the ATR warm-up
tolerance, pivot confirmation lag, single-pivot-no-form → equal-second-pivot-forms (level = max/min +
left anchor), EQH/EQL wick-through mitigation, the FIFO cap, and a full array-based reference
cross-check on a random walk (per-bar equality + positive paths, incl. a nonzero-tolerance formation).
🔴 **Only TWO of them can tell a wick rule from a close rule, and they were added in 2026-09-09
because the rest could not.** Every pre-existing mitigation case used a bar where the high AND the
close cleared the level, so it passes under either implementation and says nothing about which one is
running — the arithmetic version of a fixture more capable than production. The two that discriminate
use a bar that wicks through and closes back, and both were watched RED against the close-rule engine.
⚠ **The array reference inside the test file is a SECOND COPY of the rule and it earned its keep**:
left on `close` it disagreed with the fixed engine on the random walk, which is exactly the failure a
reference model exists to produce.

**Full Pine↔Python parity — GREEN (exit 0), 2026-07-19.** Confirmed on a fresh 16,639-bar
`VANTAGE_XAUUSD, 5m` grand export (all 11 engine checks on one CSV via `backtest/tools/verify_parity.py`):
`compare_eq.py --warmup 3500` → exit 0, every `px_eq*` column matching after the cold-start. A narrower
9,469-bar export first surfaced the problem as unmatchable pre-window ghost levels (EQH levels above the
window's price ceiling that never mitigate); the wider re-export both cleared those and exposed the real
pivot-tie bug now fixed (see "Pivot tie semantics" above). The harness:

1. `indicators/engines/eq_export.pine` — the EQ compute block from `mpc_jarvis.pine` (drawing removed, the
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

- Pine source of truth: `indicators/engines/mpc_jarvis.pine` EQ block + `GRP_EQ` inputs.
- Parity export build: `indicators/engines/eq_export.pine`.
- Siblings in shape (also standalone, events-not-visuals off the same indicator):
  `engines/fair_value_gaps/CLAUDE.md`, `engines/rsi_divergence/CLAUDE.md`.
- Pivot semantics reused from: `engines/market_structure/engine.py` / `engines/rsi_divergence/engine.py`.
- Monorepo context: `../CLAUDE.md`.
