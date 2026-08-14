# MPC SOS Fade — Bug Register

**Every known logic defect in this bot goes here, newest at the bottom, and stays until it is
fixed AND the fix is parity-verified.** This file is for things the code gets *wrong*. Parameter
sweeps and "which setting is better" questions belong in `mpc_sos_fade_optimization.md`.

A bug is only closed when all four are true: the fix is in `execution.py` (or wherever it lives),
the same fix is in `indicators/strategies/mpc_strategy.pine` AND `indicators/strategies/mpc_strategy_export.pine`,
`compare_strategy.py` is exit 0 on a fresh export taken after the change, and the affected numbers
in the optimization log carry a stale-baseline note.

| # | Found | Defect | Blast radius | Status |
|---|---|---|---|---|
| 1 | 2026-07-31 | Stop staging reads the **entry bar's own** high/low, so a limit that fills on the way down is promoted to breakeven on a move the position was never in | 44 of 164 trades (27%) over 6.6y | **OPEN** — measured, fix not designed |

---

# Bug 1 — The entry bar stages its own stop (2026-07-31)

**Status: OPEN. Measured, not fixed. Do not "fix" it for the +14.91R — see *Read the number
honestly* below.**

Present identically in three places, which is why nothing has caught it:

| where | line |
|---|---|
| `strategies/python/mpc_sos_fade/execution.py` | `_advance_stage`, ~1312 (`if self._stage < 1 and sig.high >= self._tp1`) |
| `indicators/strategies/mpc_strategy.pine` | 4546 (`if lStage < 1 and high >= lTP1`) |
| the live bridge | inherits `execution.py` — it decides on closed bars, so it sends the same stop-modify |

## Symptom

A trade is reported as a loss having never reached its stop loss. Aaron found it on the
2025-10-02 A+ long: SL was 3804.82 (fib 0.886) and price never traded below 3825, yet the trade
closed at −0.12R.

## The mechanism, walked through the bar that caused it

```
bar 12057   2025-10-02 10:30 NY   O 3864.01  H 3866.09  L 3836.38  C 3837.94

  10:30:00   3864.01   FLAT — a limit rests at 3842.60
     ...     3866.09   FLAT — the bar's high
     ...     3856.29   FLAT — this is TP1 (fib 0.5). Nobody is in a trade.
     ...     3842.60   LIMIT FILLS — now long
     ...     3836.38   underwater
  10:44:59   3837.94   close. staging asks "high >= TP1?"  3866.09 >= 3856.29  ->  stage 1
                       stop 3804.82  ->  breakeven + 30tk = 3842.90

bar 12058   O 3838.07  ->  already through 3842.90, stop fills at the open.   -0.12R
```

The position's best price while open was its own fill, 3842.60. It went straight from there to
3836.38. It was never one cent in profit.

## Why it is a defect and not a tuning choice

Breakeven staging is a **reward for progress**: "this trade ran my way as far as TP1, so it has
earned the right not to risk the full stop any more." That is the entire meaning of the rule. Here
the trade made no progress at all — it was handed the reward for a move that happened while the
account was flat.

**The error has a sign; it does not average out.** The entry is a resting limit BELOW the market,
so price crossing TP1 on the way down is not an unlucky coincidence — it is the normal mechanics of
getting filled. The deeper the retrace that reaches the limit, the more likely the bar's high sits
above TP1. So the rule fires hardest on exactly the fills that got the best price and had the most
room to run. It is anti-correlated with what it claims to reward, which is why the blast radius is
27% of the book and not 3%.

**It is not a backtesting artifact.** The live bot decides on closed bars, so at 10:45 it computes
the same stage and sends a real stop-modify to 3842.90 to the broker. Pine, Python and the live
bridge all agree — they are just all wrong in the same way, so `compare_strategy.py` can never see
it. This is the class of bug a parity gate is structurally blind to.

## Blast radius — measured 2020-01-01 → 2026-07-29, 155,255 M15 bars, shipped config

```
trades staged by their OWN entry bar     44 / 164   (27%)
  -> stage 1 (breakeven)                 34
  -> stage 2 (TP2 floor)                 10    stop jumps PAST breakeven on the entry bar
  died within 3 bars                     35
  their combined result                  +20.5R
```

Counterfactual — staging may only start on the bar AFTER the fill:

| | trades | sumR |
|---|---|---|
| baseline (shipped) | 164 | **110.65** |
| staging starts the bar after the fill | 164 | **125.56** |

Entries are byte-identical in both runs; only the stop moves. 30 outcomes change.

## Read the number honestly — it is NOT the reason to fix this

**Three trades carry 81% of the +14.91R** (+12.05R of it). Past the top seven movers the remaining
18 changed trades net to roughly zero. That is the same concentration signature the optimization
log has already called noise twice (Run 12's "40% of the gross is one 2020 trade", Run 9's "11
trades carry 106R of 109R"). A result resting on three trades in 6.6 years is not a measured edge.

Four scratches also become full −1.00R stops. Run 3 measured that delaying breakeven grows drawdown
3.5x, and this is a milder version of the same lever — so **drawdown is expected to move the wrong
way, and it was not measured.**

**Fix it because the rule fires on the wrong event. If it had measured at −5R the answer would be
the same.**

## Before anything changes

1. **Measure drawdown** on the counterfactual. Runs 6/10/11 jointly established that nothing moves
   this bot's drawdown; this would be the first thing that does, in either direction. It is the
   number that decides whether the fix is free.
2. **Decide the correct rule.** Two candidates, and they are not equivalent:
   - **(a) staging cannot advance on the entry bar at all** — one line each side, simple, but it
     also throws away genuine post-fill progress made inside that bar.
   - **(b) stage against the post-fill extreme** — correct, but the **tick fill model has the
     intrabar path and bar mode does not**, so (b) makes the two fill models disagree by design.
3. **Port to `mpc_strategy.pine` AND `mpc_strategy_export.pine` in the same commit**, then re-run
   `compare_strategy.py` to exit 0 on a fresh export. Every historical figure in the optimization
   log moves, so that file needs a stale-baseline banner the day this ships.
4. **Check `mpc_bleg`.** It inherits this exit ladder unchanged, and its band-entry geometry may put
   the entry and TP1 inside one bar more or less often than A+. Unmeasured.

## The wider question this raises

`_advance_stage` is not the only place a decision compares a bar EXTREME against a level while the
position's state changed mid-bar. Anything with that shape has the same defect available to it.
Worth one deliberate sweep of `execution.py` for the pattern rather than fixing this instance and
assuming it was the only one.

## Reproduction

`scratchpad/why_trade.py`, `why_trade2.py`, `why_exit.py`, `stage_audit.py` (throwaway, not
committed). The audit monkey-patches `Execution._advance_stage` to skip the entry bar and re-runs
the full history; **no repo file was modified to produce any number here.** Data is the local
`backtest/cache/XAUUSD__M15.csv`, bar-mode fills, `SosFadeConfig()` defaults.

Measurement record: `mpc_sos_fade_optimization.md` → Run 13.
