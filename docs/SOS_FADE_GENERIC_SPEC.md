# SOS Fade Generic — spec

**Status:** stages 1 and 5 done 2026-09-27. Stage 6 (the parity check) is waiting on a TradingView
export — see *How it is proven*. **Lab results are unverified until then.**
**Code:** `strategies/python/sos_fade_generic/` · **Lab name:** SOS Fade Generic

## What it is

SOS Fade with everything but the core switched off, so it can be run on other instruments and read
plainly. Aaron, 2026-09-27: *"armed on divergence or a sweep, then a shift of structure, then a
retracement into a fair value gap or not, same Fibonacci entry zones, take profit back to the high
or 1, 2 or 3R, stop at the 100% fib. That's it."*

🔴 **It is not a second implementation.** Every decision is made by the SOS Fade code, which already
passes its parity check against `sos_fade_strategy.pine`. This bot is that code with a small settings
panel on top, and every other SOS Fade feature pinned off. So a fix to SOS Fade's arming, zone or
fill logic reaches this bot automatically.

## The rules

| Step | Rule |
|---|---|
| Arm | A liquidity sweep OR an RSI divergence arms that side. Both on by default. |
| Arm lifetime | An arm waits up to **Max time: sweep → SOS** (default 3 days) for the shift, else it is dropped. |
| Shift | Structure breaks the other way. The fib is drawn on that break leg: 0.0 = the swing extreme, 1.0 = where the leg started. |
| Entry | A resting limit on the pullback, placed by SOS Fade's own zone rules. **Require an FVG in the zone** ON = only when a gap sits past the 0.5, resting on the fib nearest the gap. OFF = the same when there is a gap, and at the 0.618 when there is none. |
| Stop | The 1.0 fib. Not a setting. |
| Target | **Take profit at**: Swing high/low (the 0.0 fib), 1R, 2R or 3R. The whole position closes there. |
| Size | Risk % of the balance per trade, sized off the stop distance. One trade at a time. |
| The one guard kept | The minimum stop distance (0.08% of price). It is a sizing safety — a stop on top of the entry would buy an enormous position — not an entry filter. |

**Switched off:** the veto, higher-timeframe filters, the final-hour block, the dead-market filter,
entry time blocks, breakeven, the time stop, give-back and reversal exits, closing on an opposite
shift, adding to winners, the flat-before-close switch, and every extra trade type (B-leg,
re-entries, loss recovery, short-hold, level memory). The test file holds this list against the code.

## TradingView settings

There is no separate Pine file: in TradingView this bot IS `sos_fade_strategy.pine` with these set.
Anything not listed stays at its default.

| Section | Setting | Value |
|---|---|---|
| 3 · What trades | Trade SOS Fade setups | on |
| 3 · What trades | Trade B-Leg setups | off |
| 4 · What arms it | Arm on liquidity sweep | on |
| 4 · What arms it | Arm on RSI divergence | on |
| 5 · Entry | Require an FVG in the zone | your choice |
| 5 · Entry | No-FVG entries need | Any |
| 6 · Stop & targets | Stop fib level (deep side of 0.5) | 1.0 |
| 6 · Stop & targets | Stop buffer beyond the level (ticks) | 0 |
| 6 · Stop & targets | Target 1 level | 0.0 for the swing, else leave Auto |
| 6 · Stop & targets | First target, in R | -1 for the swing, else 1, 2 or 3 |
| 6 · Stop & targets | TP1 size % | 100 |
| 6 · Stop & targets | Close on opposite SOS | off |
| 6 · Stop & targets | Time stop | Off |
| 6 · Stop & targets | Add to the runner (scale in) | off |
| 7 · Filters | Respect divergence/extreme veto | off |
| 7 · Filters | Weekly / Daily bias requirement | Ignore |
| 7 · Filters | Only fade HTF exhaustion, not breakouts | off |
| 7 · Filters | No entries in the final hour | off |
| 7 · Filters | Minimum market volatility (% of price) | 0 |

## How it is proven

1. Open `sos_fade_strategy_export.pine` on a **15-minute** chart with the settings above, and export
   the chart data (*⋮ → Export chart data*). Scroll all the way left first.
2. `python strategies/python/sos_fade_generic/tools/compare_generic.py <export.csv> --warmup 100`

The tool refuses an export taken at any other settings and names each wrong one. It then runs SOS
Fade's own bar-by-bar check with this bot's config. ⚠ **Take one export with the gap required and
one without** — the no-gap entry is a branch the shipped SOS Fade gate has never exercised.

## What it measured

All runs 2020-01-01 → 2026-09-26, M15, PU Prime ECN costs (bid/ask fills, commission, swap), 5% risk,
$10,000 start, defaults (both arms, gap required, swing target). R is each trade's profit over 5% of
the balance at its entry, so costs are inside it. **Unverified until stage 6 is green.**

| Run | Instrument | Trades | Net R | R per trade | Worst drawdown | Profit factor |
|---|---|---|---|---|---|---|
| `15858c94cd93` | XAUUSD.p | 162 | +36.9 | +0.23 | 7.1R / 30.8% | 1.59 |
| `8790c4dd2fb6` (full SOS Fade, for reference) | XAUUSD.p | 245 | +207.8 | +0.85 | 6.0R / 26.9% | 4.65 |
| `55541e54da00` | GBPUSD.p | 79 | -6.6 | -0.08 | 9.6R / 42.0% | 0.81 |
| `58d992c5fd42` | GBPJPY.p | 73 | -14.3 | -0.20 | 17.7R / 61.9% | 0.64 |

⚠ **On gold, the features this bot strips out are worth about 170R** over the same window.
⚠ **Both FX pairs lose at these defaults, and they trade half as often as gold.** Setups that
reached the zone and found no qualifying gap: 179 on gold, 362 on GBPUSD, 322 on GBPJPY. A tight
stop refused only 1, 9 and 9 — so the stop floor is not what starves FX.
⚠ **The likely cause, NOT yet measured: the minimum gap size is a fixed 0.1% of price**, an engine
pin set for gold (`SosFadeStrategy.engine_config`). A pair that moves less in percentage terms has
fewer gaps that size. Testing it means changing that pin for FX runs, which moves the engine setting
and needs its own measurement — not a tidy-up.

### Does price turn from the zone? (2026-09-27, `backtest/tools/generic_zone_turn.py`)

Every setup whose pullback reached the 0.5-0.886 zone, 2020-01-01 → 2026-09-26, M15. TURN = price made
a new high/low (the 0.0) before breaking the start of the move (the 1.0). A bar touching both = fail.
Setups that traded are scored by their own result; the rest are walked forward from the zone touch.

| | Gap, traded | No gap | All |
|---|---|---|---|
| GBPUSD.p | 45.6% (79) | 44.8% (362) | **46.5%** (456) |
| GBPJPY.p | 41.7% (72) | 50.3% (320) | **50.0%** (408) |
| XAUUSD.p | 57.6% (165) | 45.5% (178) | **55.0%** (373) |

⚠ Setups with a gap whose limit never filled turned 81-97% — SELECTION, not signal: price turned
before reaching the fill. They are in "All" and not shown on their own.
**Read:** on both pairs a zone touch is a coin flip, and a gap does not improve it. On gold a gap
lifts the turn rate 12 points, which is where this bot's gold profit comes from.

### Does the leg's volume point of control mark the turn? (2026-09-27, `backtest/tools/generic_poc_study.py`)

Aaron's idea: a fixed-range volume profile over the move; its point of control (the busiest price)
is where the pullback should turn. Rules fixed before the result — see the tool's docstring. The
profile is 50 rows over the leg, 5-minute bars, MetaTrader TICK volume, the canonical engine's
arithmetic. Each setup alone, stop 1.0, target 0.0, **gross R (no costs)**, 2020-01-01 → 2026-09-04.

| R per fill | fib 0.5 | fib 0.618 | fib 0.786 | fib 0.886 | **at the POC** | **nearest fib, same setups** |
|---|---|---|---|---|---|---|
| GBPUSD.p | -0.11 (451) | -0.11 (379) | -0.15 (306) | -0.11 (276) | **-0.23** (204) | **-0.17** (208) |
| GBPJPY.p | -0.02 (408) | -0.01 (334) | +0.04 (266) | +0.14 (238) | **-0.16** (190) | **-0.08** (196) |
| XAUUSD.p | -0.04 (368) | +0.03 (314) | -0.05 (240) | -0.17 (211) | **-0.12** (162) | **-0.17** (162) |

Where the POC sits: in the 0.5-0.886 zone on 53-56% of legs, shallower than 0.5 on 38-40%.
**Read:** the POC is WORSE than a plain fib of the same depth on both pairs and marginally better
on gold, where both are negative. It does not find the turn. ⚠ GBPJPY at 0.886 (+0.14R, 31 wins in
238) is one of twelve cells, t ≈ 0.75 before costs — noise, not a lead.
⚠ **No fixed entry depth has an edge on its own, on any of the three.** Stop at 1.0 and target at
0.0 is roughly break-even gross everywhere; what makes SOS Fade pay on gold is the selection and
trade management this bot strips out.

### Where, when and which days do FX setups turn? (2026-09-27, `backtest/tools/generic_fx_patterns.py`)

Aaron: *"Where does price reject from, where not, which times of day and days to avoid?"* Every
setup that tagged the zone, M15, measured alone, gross, TURN = new high/low before the 1.0. Each
bucket is compared with the pair's own turn rate; a "pattern" must be ≥ 2 standard errors off it
AND on the same side in both date halves. ~35 buckets per pair, so ~1 false hit per pair is
expected by luck. GBPUSD 2000 → 2026 (1,606 setups, baseline 45.4%); GBPJPY 2016 → 2026 (653,
baseline 48.2%).

**Verdict: no bucket on either pair passes.** Zero patterns in ~70 tests.

| Depth reached | GBPUSD turned | GBPJPY turned | break-even for an entry there |
|---|---|---|---|
| 0.618 | 36.1% | 37.2% | 38.2% |
| 0.702 | 27.5% | 30.7% | 29.8% |
| 0.786 | 19.5% | 20.7% | 21.4% |
| 0.886 | 9.7% | 11.1% | 11.4% |

**Read:** the chance of turning from each depth is what a random walk gives (b/(a+b)) — there is
no fib level price rejects from on these pairs at M15. Strongest leads, all under z 2, **none
usable as a filter**: GBPUSD 18-21 NY 37.8% (82, z -1.4, low in both halves); GBPUSD Wednesday
50.3% (366, z +1.9, 50.3% in both halves); GBPUSD H4-level sweeps 38-41% (z -1.0 / -1.4); GBPJPY
H4 High sweeps 35.4% (48, z -1.8). Long vs short, sweep vs sweep+divergence, gap vs no gap and leg
size: all flat.
