# Order block + 1-minute shift of structure — the ledger

**Tool:** `backtest/tools/ob_shift_study.py`
**Question (Aaron, 2026-09-22):** order blocks in MPC Jarvis, and the reversals from them, triggered
by a one-minute shift of structure. What are the win rates and how effective is it?
**Verdict: NO EDGE.** Fails the luck bar in-sample and fails out-of-sample on a pre-declared rule.
**Held-out 2018-09-14 → 2019-12-31 test set: UNSPENT.** Nothing here earned a look at it.

---

## What was measured

Gold (PU Prime `XAUUSD_p`), one 1-minute feed for everything. Higher timeframes are resampled from
it — **verified bit-identical to the broker's native 15m, max difference 0.0000 on all four prices
over 5,783 bars** (2024-01-01 → 2024-03-31), so this is not an assumption.

* Blocks: canonical `engines/order_blocks/` at its defaults, replayed on M5 / M15 / H1.
* Shift: canonical `engines/market_structure/` replayed on 1-minute bars. Four definitions —
  external CHoCH, external any-break, internal CHoCH, and any of the four.
* Entry: the bar AFTER the trigger, at its open (the one-bar order delay every fill model here uses).
* Stop: the block's far edge, or the 1-minute swing — both run.
* Targets: 1R / 1.5R / 2R / 3R, 48h time exit, stop checked before target on the same bar.
* Costs: measured PU Prime ECN — 0.12/oz spread + $1.00/side/lot commission (0.02/oz round turn on
  a 100oz lot) = 0.14/oz, converted to R by each trade's own stop distance.

**Windows.** Search 2020-01-01 → 2024-12-31. Confirm 2025-01-01 → 2026-09-22. The reserved set
(2018-09-14 → 2019-12-31) is cached on this laptop for 1-minute gold, so `load_m1` REFUSES to load
anything before 2020 without `--holdout`. The guard is in the tool, not in anyone's memory.

## The four arms, and why one win rate would have been worthless

    A  block + shift    the ask
    B  block, no shift  blind entry on first touch of the zone   -> what does the SHIFT add?
    C  shift, no block  every 1m shift on the tape               -> what does the BLOCK add?
    D  matched random   same side, month, NY hour, stop, target  -> the luck bar

## Results — search window, 2020-01-01 → 2024-12-31, 96 cells

Best cell: **M15 blocks / internal 1m CHoCH / stop under the block / 1R**
`n=107 · win 63.6% · avgR +0.271 · net avgR +0.223 · z vs matched random +2.46`

At that cell, **each ingredient alone is worth nothing**: block without the shift `avgR +0.004`,
shift without the block `avgR -0.005`. That interaction is exactly what Aaron predicted, and it is
the only reason the idea got as far as an out-of-sample test.

It makes money in BOTH halves of the search window (+17.0R and +12.0R), so it passes that gate.

🔴 **IT FAILS THE LUCK BAR.** 200 re-runs of the whole 96-cell search on entries that are random but
matched to each real trade's side, month, NY hour and stop distance, recording the best cell of each
fake search:

    null best avgR:  median +0.388   95th +0.719   99th +0.909   max +1.137
    real best avgR:  +0.271
    -> a RANDOM search beat the real one in 87% of re-runs

The median random search finds a better cell than the real search did. A z of 2.46 is the right bar
for one pre-declared cell and the wrong bar for the best of 96 — the Loaded Level scalp made exactly
this mistake (best of 3,456 cells, lost on new months).

## Results — confirm window, 2025-01-01 → 2026-09-22, ONE pre-declared cell

Rules fixed before the window was loaded. Same cell as above.

| | search | confirm |
|---|---|---|
| setups | 107 | 36 |
| win rate @1R | 63.6% | **47.2%** |
| avg R @1R | +0.271 | **-0.056** |
| net avg R @1R | +0.223 | **-0.070** |
| z vs matched random | +2.46 | **-0.37** |

**Dead.** The win rate fell 16 points and the expectancy went negative on data the rule had never
seen.

## Three things worth keeping

1. **Costs are not what killed it.** The stop is 3.45/oz median in the search window and 10.99 in
   the confirm one, so the round turn is 4.1% and 1.3% of 1R. This idea died on prediction, not on
   friction — do not try to rescue it with a cheaper broker.
2. **Frequency was never the problem.** 2.6 setups/month in BOTH windows, which is squarely the
   band the trading philosophy asks for. The shape of the setup is right; the edge is absent.
3. **Trend alignment is not the rescue, and it looks like one.** Splitting the setups by whether
   15m structure agreed with the block: in the search window aligned and counter-trend are
   indistinguishable (63.2% / +0.263 vs 64.0% / +0.280 — the filter does NOTHING over 107 trades).
   In the confirm window they split hard (64.3% / +0.286 on n=14 vs 36.4% / -0.273 on n=22). A
   filter that is inert on the large sample and decisive on the small one is noise. Anyone revisiting
   this will find that split and should not believe it.

## Granularity — the one objection, answered

The engine's 1-minute structure shift fires **5.3 times a day**, which is coarser than what a trader
reads off a 1m chart. That was checked rather than waved away: the "any break" definition fires
**~31 times a day** and was in the grid — `M15/any/block/1.0R` over 5 years is `n=464 · win 51.1% ·
avgR +0.022 · z +0.54`. Both granularities are nothing, so the verdict does not rest on the coarse one.

## ⚠ Finding about the structure engine itself — NOT acted on

`engines/market_structure/`'s swing-length setting is read (`engine.py:339`, pivot window
`2L+1`) but changing it barely moves the engine's output. MEASURED on 86,435 1-minute bars
(2021-01-01 → 2021-03-31):

| swing length | 3 | 5 | 15 | 50 |
|---|---|---|---|---|
| external CHoCH | 344 | 343 | 344 | 342 |
| BOS flags | 907 | 907 | 906 | 900 |

A 17x change in the parameter moves the event count by 0.6%, with the pivot window going from 7
bars to 101. **This is reported, not fixed.** The engine is Pine-parity-validated, so if the Pine
behaves the same way this is a property of the original design rather than a port defect — and the
parity gate would not catch it either way, because a faithfully ported inert knob is still green
(rule 14). Worth one look by whoever owns the engine before anyone tunes that setting expecting it
to do something.

## Reproduce

    backtest/tools/ob_shift_study.py --window search --htf-sweep --shift-sweep --stop-sweep --luck-bar 200
    backtest/tools/ob_shift_study.py --window confirm --htf M15 --shift int_choch --stop block
