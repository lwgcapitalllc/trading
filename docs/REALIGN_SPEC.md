# Realign — spec

**Stage 1 of `docs/STRATEGY_WORKFLOW.md`.** Rules with no discretion left in them, so the Pine can
be written straight off this file.

**The idea in one line:** a bullish trend prints a *false* bearish break; the lower-timeframe
structure realigns bullish before the higher timeframe does; you enter on that realignment and are
already positioned when the external bullish SOS confirms it.

**Status:** spec only. No Pine, no export twin, no Python port, no parity gate.
**Author:** Aaron's setup, read off a 2026-08-05/07 XAUUSD chart.
**Instrument / frames:** XAUUSD. External **15m**, internal **5m**. **NO CASCADE** — see below.

🔴 **THE TWO SIDES READ STRUCTURE AT DIFFERENT DEPTHS, AND THAT IS THE CENTRAL FINDING.**
MEASURED over 6.5 years, each side is positive on its own trigger and negative on the other's:

| side | trigger stream | setups | best edge |
|---|---|---|---|
| **SHORT** | the 5m **internal** structure (`iBOS`/`iSOS`) | 100 | **+9.6% (+2.1σ)** at 4R |
| **LONG** | the 5m **swing** structure (one level coarser) | 171 | **+5.0% (+1.3σ)** to the pre-deviation high |

Longs on the fine internal stream are negative at EVERY target (−2.3 / −4.1 / −0.6 / −1.7%); longs
on the coarse stream are positive at every target (+5.0 / +3.7 / +4.3 / +2.4%). Two further tests
point the same way — delaying the long entry by one confirmation moved it from −4.1% to ≈0, and
widening the long stop to the deviation low moved it to +2.7%. **On the long side the fine internal
structure triggers too early and stops too tight.** This is a measured asymmetry, not a fudge.

---

## The sequence

Written long. **Shorts are the exact mirror** and are part of the strategy, not an extension.

### 1 — External trend, on the 15m

A bullish external break establishes the trend: a bullish SOS or a bullish BOS
(`ExternalEvents.bull_sos` / `bull_bos` from `engines/market_structure/`).

### 2 — The false break, on the 15m

A **bearish external SOS** (`bear_sos`) fires, and it is the FIRST bearish external break since the
bullish break in step 1. That "first" is the rule that makes it a deviation rather than a trend
that is already down — if a bearish break has already printed since step 1, this is not a setup.

The **pre-deviation high** is captured here: `broken_high_price` on the bearish SOS bar. That is the
external high that stood before the break, and it is the level the whole setup is aiming at.

The setup is now **armed** and lives for `realign_window_hrs` (default **24.0**). If step 4 has not
fired inside that window the setup dies and is never re-armed off this SOS — the deviation is
accepted as a genuine trend change.

### 3 — Internal goes bearish, on the 5m

After the 15m bearish SOS, the 5m structure prints a bearish break of its own — a bearish SOS or a
bearish BOS on the 5m stream.

⚠ **"Internal" here means the 5m chart's OWN structure**, which is the internal structure of the
15m. It is NOT `InternalEvents` from a 5m engine — that state machine resets on the 5m's own
external breaks and was wiped before the trigger on 81% of candidates when measured, so it does not
describe what is on the chart. Read the 5m engine's EXTERNAL stream.

The bar of the most recent bearish 5m break is retained; it anchors the stop in step 5.

**The cascade.** If no realignment fires on the 5m inside the window, drop to the 3m and look
again; `realign_cascade` (default `"5,3"`). This is Aaron's own reading — when there is no internal
structure to read on the 5m, he drops a frame to find it — and it is the common case, not the
exception: the setup completes on the 5m for only 55% of deviations.

⚠ **Do NOT extend the cascade to the 1m.** MEASURED per rung, the 5m carries the edge (+5.0% over
control) and each deeper rung dilutes it: the 3m is break-even on hit rate (+0.9%) and the 1m is
negative (−2.0%), so pooling all three takes the book from +1.3σ to +0.8σ. 138 extra setups, no
extra edge — Run 12's queue effect, where a marginal setup takes the slot rather than adding to it.
The 3m is kept as a toggle because its expectancy is positive (+0.206R); the 1m is off.

⚠ **There is a COST FLOOR under this and it decides the 1m rung independently of the edge.** The
1m rung's median stop is $3.19 on the internal reading against a $0.22–0.32 XAUUSD spread — 7–10%
of every R gone before the signal speaks. `tools/intraday_edge.py` measured that as the structural
reason gold has no intraday edge at all. The 5m's $11.36 stop is clear of it; the 1m is inside it.

### 4 — The realignment, on the 5m — THIS IS THE TRIGGER

A **bullish SOS on the 5m** fires. The internal read is now bullish again and has realigned with
the external bullish direction from step 1.

This is the entry signal. **The external bullish SOS has not happened yet** — it typically prints
later, and it is the target and the confirmation, never the trigger. Being in before it is the
entire point of the setup.

### 5 — Entry and stop

**Entry — immediate.** A market entry at the close of the bar the 5m bullish SOS confirms on.
`realign_entry_mode = "Immediate"` (default). The `"Retrace"` alternative rests a limit instead —
specified in *Open*, not built.

**Stop — behind the last bearish internal shift.** The lowest low from the bar of the most recent
bearish 5m break (step 3) up to and including the trigger bar, minus `realign_sl_buf_tk` ticks.

That is the low of the internal leg the bullish SOS has just reversed. It is deliberately NOT the
low of the whole deviation: measured, that wider stop is 65% larger ($15.70 against $9.53 median)
and halves the reward:risk for nothing.

**Refuse the setup** if the stop distance is ≤ 0, or if `exec_min_stop_mode` is on and the distance
is under the floor. A refusal records a block code and places no order.

---

## The exit ladder

**Inherited from `strategies/python/sos_fade/CLAUDE.md` → *The exit ladder*, with the stop
overridden.** This is the `b_leg` pattern: that fork replaces TP1, TP2 and the SL with its own
band prices and inherits everything from the staging down. Here only the STOP is replaced.

**The fib leg is the deviation** — anchored on the pre-deviation high (step 2) and the deviation
low. On that leg `0.0` is the high, so the A+ rungs land exactly where this setup wants them:

| | |
|---|---|
| **Stop** | **OVERRIDDEN** — the internal structure low from step 5, not `exec_sl_level`. `exec_sl_deep` does not apply. |
| **TP1 / TP2** | A+ rule unchanged: chosen automatically by entry depth. Deep → TP1 0.5, TP2 0.382. Shallow → TP1 0.382, TP2 **0.0 = the pre-deviation high**. |
| **Rung sizes** | `exec_tp1_pct` / `exec_tp2_pct`, default **0 / 0** — bank nothing, ride the runner. 0 does not disable the target: touching TP1 still stages the stop, touching TP2 still installs the floor. |
| **Staging** | A+ unchanged: (0) full stop → (1) after TP1, breakeven + `exec_be_buf_tk` → (2) after TP2, the floor, then the trail. |
| **TP2 floor** | `exec_tp2_stop_mode`, default `"TP1 price"`. |
| **Runner trail** | `exec_runner_trail`, default `"Structure + % ratchet"`, `exec_trail_pct` 1.0, `exec_struct_trail_buf_tk` 20. |
| **Time stop** | `exec_time_stop_mode` `"Before TP1 only"`, `exec_time_stop_hrs` 36.0. |
| **Min stop guard** | `exec_min_stop_mode` `"% of price"`, `exec_min_stop_val` 0.08. |

**The trail anchors on the 15m swing** (Aaron's call, 2026-08-12). You enter off the 5m and ride
the 15m: the 5m swing sits close enough that the first pullback scratches the runner, and the
`exec_trail_pct` ratchet already tightens the 15m anchor as price moves.

---

## Config levers

Every one needs a Pine `input.*` behind it, or the export cannot carry it and no parity gate can
ever check it.

| Field | Default | Meaning |
|---|---|---|
| `realign_htf` | `"15"` | External frame |
| `realign_cascade` | `"5"` | Internal frames tried in order. **MEASURED: adding `3` cancels the edge, adding `1` is worse** |
| `realign_window_hrs` | `24.0` | How long the setup stays armed after the 15m bearish SOS |
| `realign_entry_mode` | `"Immediate"` | `"Immediate"` \| `"Retrace"` |
| `realign_pattern` | `"any"` | `"any"` \| `"opposing"` \| `"strict"`. MEASURED: `strict` is the worst |
| `realign_sl_buf_tk` | `20` | Ticks beyond the internal low |
| `realign_longs` / `realign_shorts` | `true` / `true` | Both sides trade |
| `realign_long_source` | `"swing"` | LONG trigger stream — coarse. Measured: `internal` is negative |
| `realign_short_source` | `"swing"` | SHORT trigger stream. MEASURED BY REPLAY: `internal` gives −13.26R against +20.22R |

Plus the whole inherited A+ exec block.

⚠ `realign_require_internal_bear` was **measured free** — on/off gave an identical 94 setups and an
identical hit rate, because after a 15m bearish SOS the 5m always goes bearish before it turns. It
is kept as a lever rather than deleted so the Pine and the port stay honest about the rule, but do
not expect it to bind.

---

## What is measured so far

`backtest/tools/internal_realign_scan.py`, XAUUSD, 186,488 M15 bars and 467,616 M5 bars resampled
from M1, 2020-01-01 → 2026-08-07. **Longs only — the short mirror is not implemented in the scan.**

**Short side, 15m external / 5m internal, `opposing` pattern, 100 setups in 6.5 years (~15/yr)**,
scored against random entries matched on direction, stop distance and reward:risk.

| target | hit | control | edge | sigma | expectancy edge |
|---|---|---|---|---|---|
| 1R | 49.0% | 48.5% | +0.5% | +0.1 | +0.010R |
| 2R | 36.0% | 31.2% | +4.8% | +1.0 | +0.144R |
| 3R | 30.3% | 22.1% | +8.2% | +1.8 | +0.327R |
| **4R** | **26.5%** | **16.9%** | **+9.6%** | **+2.1** | **+0.478R** |

**The edge grows MONOTONICALLY with the target, and that shape is the finding.** This is not a
hit-rate edge — at 1R it is nothing. It is a *when it works it runs* edge, which is exactly the
fat-tail shape the A+ ladder exists to harvest and the reason the runner is the right exit here.
One +2.1σ cell on its own would be noise-shopping; five target choices trending the same way is not.

**Long side, same rule, same window:** 1R −6.7% (−1.4σ), 2R −4.1% (−0.9σ), 3R −0.6% (−0.1σ),
4R −1.7% (−0.4σ). No target positive, and worst at the short target — longs fail to reach even 1R
more often than random does. That is an anti-signal, not an absence of signal, and it needs its own
investigation before the long side is built.

**Pattern selectivity — the scan ranks the STRICT sequence last.** Requiring the with-trend
iBOS before the opposing pair cuts the book from 183 to 121 and moves both directions the wrong way
*by this measure*:

| pattern | setups | long/short | long edge | short edge |
|---|---|---|---|---|
| `strict` iBOS → iSOS → iSOS | 121 | 69 / 52 | −5.7% | +4.4% |
| `opposing` the two iSOS only | 125 | 71 / 54 | −3.8% | +4.3% |
| **`any`** counter break → with-trend iSOS | **183** | 94 / 89 | −2.3% | **+6.1%** |

🔴 **THE REPLAY OVERTURNS THIS ROW, AND THE TABLE IS KEPT SO THE DISAGREEMENT IS ON THE RECORD.**
Run through the real exit ladder over the same history (467,352 M5 bars), **free**, `strict` is the
**BEST** of the three on average R (+0.294 vs `any`'s +0.279), profit factor (1.977 vs 1.658) and
drawdown (4.15R vs 12.15R) at once. It only loses the ranking once **costs are charged**, where its
average R falls 40% against `any`'s 21% and the order flips. Full tables in
`strategies/python/realign/CLAUDE.md` → *The pattern rule*.

⚠ **This is the SECOND time this scan's ordering has failed to survive a replay** — the first was
the short trigger stream, where it was wrong in SIGN. Both failures point the same way: the scan
scores each setup independently at a fixed target with no ladder and no position slot, so it ranks
**trigger quality**, and a strategy is ranked on what its exits actually bank. **Nothing in this
section may be used to choose a default.**

🔴 **NO CASCADE. The 5m rung is the whole result and the 3m rung destroys it.** At a 4R target on
the short side: M5 100 setups **+9.6% (+2.1σ)**, M3 103 setups **−5.4% (−1.6σ)**, and pooling the
two washes the book down to +0.6σ. The 3m does not dilute the edge, it cancels it.

⚠ **That is a prior on the TRIGGER, not a strategy result.** The scan has no exit ladder, no
sizing, no costs, and it scores every setup independently while a real strategy holds one position
at a time.

---

## Open — the fluid parts, in the order worth testing

1. **The short mirror.** Doubles the sample. Nothing else moves the significance as cheaply, and
   at +1.3σ on longs alone that is what decides whether this clears the bar.
2. **Confluence gates, one at a time.** The trigger currently has none. A fair-value gap at the
   entry, an RSI divergence on the deviation low, the session, the pro-trend VWAP side. This is the
   path that found VWAP was worth +2.4% on the BOS bot.
3. **The timeframe pairing.** 15m/5m is where the setup was read off a chart, not where it was
   proven best. 30m/5m is the obvious neighbour; 15m/1m is measured and worse.
4. **The retrace entry.** Rest a limit into the trigger leg instead of entering at the close. Needs
   its own rule for where the limit sits and when it expires.
5. **The arming window.** 24h was chosen, not measured.

---

## Measured by REAL REPLAY — the first end-to-end result

`strategies/python/realign/`, 467,352 M5 bars (2020-01-02 → 2026-08-06), full A+ exit
ladder, one position slot, $10,000 start, **no costs charged**.

| config | trades | total | avg | maxDD | equity |
|---|---|---|---|---|---|
| **both sides on `swing`** | **162** (77L/85S) | **+45.14R** | +0.279R | 12.15R | **$73,265** |
| long `swing` + short `internal` | 139 | +17.74R | +0.128R | 15.13R | $12,571 |
| longs only (`swing`) | 80 | +30.00R | +0.375R | 7.65R | $58,621 |
| shorts only (`swing`) | 87 | +20.22R | +0.232R | 6.39R | $18,201 |
| shorts only (`internal`) | 60 | −13.26R | −0.221R | 14.61R | $1,930 |

🔴 **THE TRIGGER SCAN GOT THE SHORT SIDE'S SIGN WRONG, AND THAT IS THE LESSON OF THIS
BUILD.** The scan reported shorts-on-`internal` at +9.6% over control (+2.1σ) — its
strongest single result — and a real replay gives −13.26R. The scan scores every setup
independently at a fixed target with no ladder, no staged stop and no position slot, and
that short edge existed ONLY at a 4R target (+0.1σ at 1R). The shipped ladder banks at the
structural target, so it never collects it. **Take counts from the scan; take the direction
of anything exit-sensitive from a replay.**

⚠ The time stop was tested as the cause and REFUTED — shorts-on-`internal` are worse with
it off (−14.06R), so the ladder's target placement is the mechanism, not the clock.

⚠ **No costs in these figures, and this fork cannot inherit A+'s cost profile.** A+ enters
on a resting limit and measures ~0 spread cost under `bid_ask_fills`; this fork enters at
MARKET and pays the spread both ways. Charge it before quoting any of these numbers.

---

## The TradingView Strategy Tester run — 2026-08-12

The Pine compiles and runs. XAUUSD 5m, 2020-01-01 → 2026-08-12, $10,000, **risk 1%**:

| | TradingView | Python (charged) | Python (free) |
|---|---|---|---|
| trades | 143 | 162 | 162 |
| total | +41.35% ≈ **35R** | **+35.81R** | +45.14R |
| max drawdown | 17.79% ≈ 19.5R | 15.52R | 12.15R |
| profit factor | 1.617 | 1.496 | 1.658 |
| win rate | 30.77% | **33.3%** | 44.4% |

✅ **Total R agrees within noise across two independent implementations.** That is the first
real cross-check this strategy has had, and it is on TradingView's own tester rather than ours.

✅ **THE WIN-RATE COLUMN IS WHY THE FREE BOOK IS SHOWN BESIDE THE CHARGED ONE.** The first version
of this table quoted 30.77% against **44%** and recorded the gap as an open difference blamed on
scratch classification — but 44% is the FREE book, sitting in a row whose R came from the CHARGED
one. **Read like for like it is 30.77% against 33.3%, and the difference is mostly gone.** Costs
move this strategy's win rate 11 points because it enters at MARKET and pays the spread both ways.
⚠ **A comparison table with two books in it will produce exactly this kind of false finding.** One
row, one book.

⚠ **The charged column previously read +37.67R / 14.60R and does not reproduce** — same window, same
`puprime_standard` profile, 5m resampled from M1, warmup 1000. The free column reproduces to the
cent, and Aaron's `32b633f` was checked and touched no execution code. **The original run's command
was not recorded, so this cannot be settled** — which is the reason the re-run recipe now lives in
`strategies/python/realign/CLAUDE.md` → *How to re-run this*.

🔴 **RISK % IS A MEASUREMENT SETTING HERE, NOT A PREFERENCE.** The first run was taken at 10%
with `margin = 0` and read **−98.10% / PF 0.193** over 2009–2026: the account died in the first
months and every later trade was sized off dust, so the run measured almost none of the history
while reporting seventeen years. R is scale-free — 1% and 10% give identical R, win rate,
drawdown-in-R and PF — so **measure at 1 and size the account after the R distribution is known.**
This is the same lesson `d_strategy.pine` recorded on 2026-08-06, met again five days later.

⚠ **`margin_long/short = 0` is not a neutral setting, it is unbounded leverage.** Pine's default
is 100% (full cash), which REFUSES every order here and shows an empty tester with no error —
that is what "nothing shows in the backtest" meant. The fix is 500x (`0.2`), matching every other
strategy file in this repo, not zero.

⚠ **Two differences from the Python are open and DIAGNOSED RATHER THAN MEASURED.** Drawdown is
worse in Pine and Pine is probably right — TradingView fills a gapped stop at the next bar's OPEN
where the bar-model replay fills at the stop price, which undercounts gap risk. Win rate differs
because the tester asks only whether P&L > 0 while the Python counts 11 scratches separately.
**Neither is confirmed; the parity gate (stage 6) is what settles them.**

---

## Architecture — it is SINGLE-frame, and that matters

The obvious build is dual-frame (a 15m stream and a 5m stream), which would hit
`run_sweep`'s refusal and lock the strategy out of the optimizer, the sweeps and the stress test.

**It does not have to be.** Run the strategy on the **5m** stream and let it AGGREGATE its own 15m
bars — three 5m bars to a 15m bar, aligned to :00/:15/:30/:45 — feeding a second `StructureEngine`.
That is exactly what the Pine does with `request.security`, it is deterministic, and it makes the
strategy single-frame from the runner's point of view.

⚠ **A 15m bar may only be published once its THIRD 5m bar has closed.** Publishing a forming 15m
bar is lookahead, and it is the flattering kind — the external break would be known before it could
have been.

---

## Next stages

| # | Stage | Artefact |
|---|---|---|
| 2 | Pine strategy | `strategies/tradingview/realign_strategy.pine` |
| 3 | Pine export twin | `strategies/tradingview/realign_strategy_export.pine` |
| 4 | A real CSV export | **Aaron only** — Claude has no TradingView session |
| 5 | Python port | `strategies/python/realign/` |
| 6 | Parity harness | `strategies/python/realign/tools/compare_realign.py`, exit 0 |
