# FB — Failed Break (the "Riz" liquidity model) — v0 spec

**Status:** 🔴 **SPEC ONLY. NOTHING IS BUILT AND NOTHING HAS BEEN MEASURED.** This is stage 1 of
the six in `docs/STRATEGY_WORKFLOW.md`. No Pine, no export twin, no CSV, no Python port, no parity
gate. Every number in this file is a DEFAULT PROPOSED FOR MEASUREMENT, not a measured value.

**Source:** ["The FULL 1:20RR Liquidity Trading Strategy ($140,000+ Part-Time)"](https://www.youtube.com/watch?v=ml2O5EuX6E0)
— Riz, on the Prop Firm Trader channel, 2026. Full transcript pulled and read (≈20,000 words).
Claimed record: **$140,000 in FTMO payouts over 12 months, part-time, two 200k accounts, 0.5% risk
per trade, almost entirely EURUSD**, plus one XAUUSD trade.

⚠ **That record is a CLAIM in a podcast, not evidence.** He posts trades to a public Discord, which
is better than nothing and is still not a verified track record. Nothing in this repo should treat
it as a prior strong enough to skip a measurement.

---

## 0. What this is, in one line

**It is the SOS Fade SOS Fade with a harder arm and a much longer target.** The entry geometry, the stop
logic and the sizing are the ones this repo already ships. Three things differ:

| | SOS Fade SOS Fade (`sos_fade`) | FB |
|---|---|---|
| **Arm** | liquidity sweep or divergence → SOS | a **failed** LTF break — SOS, then the SOS's own origin gets swept, then a second SOS the same way |
| **Target** | fib TP ladder off the entry leg (TP1/TP2/TP3) | the nearest **un-swept higher-timeframe liquidity pool** — held for days to weeks |
| **Book** | one position, one slot | up to N **stacked** positions on one HTF idea, but never more than **one at risk** |

Everything else — the fib entry band, the stop at the leg origin, the staged stop, R sizing — is SOS Fade
behaviour and should be inherited, not rewritten. If a rule below appears to invent new geometry,
that is a defect in this doc; flag it rather than building it.

---

## 1. The concept in one paragraph

Price does not reverse because a level is pretty. It reverses where the most orders are trapped.
The densest trap available is a **break of structure that fails**: the break brings in a wave of
traders with their stops just behind it, price then runs those stops, and the traders who were
stopped out on the *other* side pile in the wrong way at the same moment. Both sides are wrong
within a handful of bars — Riz calls it "early buyers / early sellers", and calls that moment peak
emotion. The trade is to wait for that double-kill and then buy the *real* break that follows, with
a stop below the swept low. Because the stop sits on a one- or five-minute low while the target sits
on a monthly liquidity pool, the reward-to-risk is structurally large — 1:10 and up — and the
strategy earns its money from a handful of those a year rather than from a hit rate.

---

## 2. Provenance — what is his, and what I mechanised

Riz's method is discretionary at six joints. This spec pins each one. **The pinned choice is mine,
not his**, and each is a real fork in the road that a measurement could reject.

| # | His words | The mechanical rule in this spec | Risk if wrong |
|---|---|---|---|
| J1 | "the significant low to the significant high" | the engine's **External fib leg** (§4.2) | a different range moves the 50% and therefore every trade's eligibility |
| J2 | "extend the range if price never got to a discount" | falls out of the engine's expansion leg — it re-extends its own 0 (§4.2) | none obvious; this one fits well |
| J3 | "significant liquidity has been taken" | a named level from `engines/liquidity/` or `engines/equal_highs_lows/` swept within `fb_sweep_window` bars (§4.3) | too loose = every bar qualifies; too tight = no trades |
| J4 | "the nearest 20/50/80 above the 0.618" | a price grid at `{0.0, 0.2, 0.5, 0.8} × fb_round_block` (§4.4) | the block size is instrument-specific and **must be measured, never assumed** |
| J5 | "early buyers get swept, then an aggressive break" | a three-event structure sequence with two bar windows (§4.6) | this is the whole strategy — see §10 Q1 |
| J6 | "hold to the significant liquidity to the left" | a priority-ordered target picker (§4.9) | decides whether the 1:15s exist at all |

⚠ **The headline "1:20RR" is not a per-trade figure and must never be reported as one.** It is what
a *stack* of three ~1:10 positions on one idea totals in R (§4.10). Individual trades in his own
walkthrough are 1:2, 1:3, 1:7, 1:10, 1:11 and 1:15.

---

## 3. What the engine already gives us — no new geometry

Everything the setup needs already exists in `engines/`. Nothing new is invented except §4.4.

| Engine value | What it is | Used for |
|---|---|---|
| `ExternalEvents.bull_sos` / `bear_sos` | the shift — a break that flips the trend | §4.6, all three events |
| `ExternalEvents.bull_bos` / `bear_bos` | a continuation break | §4.1 bias |
| `bull_bos_low` / `bull_bos_l_loc` (+ bear mirror) | the **break leg** — both endpoints and their bars | §4.6 origin, §4.8 stop |
| `broken_high_label` / `broken_low_label` | `HH`/`HL`/`LH`/`LL`, or `ASH`/`ASL` = **not yet classified** | §4.1 bias |
| `last_conf_high` / `last_conf_low` | the confirmed-swing trail reference | §4.9 runner trail |
| `engines/fibonacci/` structure fib `fiboP1..P10` | `P2` = 0.5, `P3` = 0.618, `P6` = 0.886, `P7` = 0.0, `P10` = 1.0 | §4.2 discount, §4.7 entry |
| `engines/liquidity/` `LiquidityLevel` | PDH/PDL, PWH/PWL, PWC, H4 sweep high/low, Asia/London/NY H/L, each with `mitigated` + `mitigated_index` | §4.3 precondition, §4.9 target |
| `engines/equal_highs_lows/` | EQH/EQL levels, alive until a body closes through | §4.3, §4.9 |
| `engines/fair_value_gaps/` | live FVGs with born bar | §4.5 confluence, §4.9 target |
| `engines/order_blocks/` | live order blocks | §4.5 confluence |
| `engines/candlesticks/` | fifteen reversal patterns, `bars_since` | §4.5 confluence (optional, default OFF) |

⚠ **`broken_*_label` can be `ASH`/`ASL`, which means *not yet classified*, not *unknown*.** A bias
rule that treats it as a missing value will read a fresh post-SOS swing as neutral. See
`engines/market_structure/types.py`.

⚠ **Liquidity levels are non-repainting by design** — every HTF level is built from a *previous,
completed* period. That is exactly what this setup needs and it is not negotiable.

---

## 4. The rules

Direction is written long. Short is the mirror throughout.

### 4.1 Bias — the anchor timeframe

Read `engines/market_structure/` on `fb_bias_tf` (default **4H**).

- **Bullish** if the last classified break was `bull_bos` or `bull_sos` and the last classified low
  label is `HL`.
- **Bearish** is the mirror.
- Anything else → **no bias, no trade** (block code 1).

Trades are taken **with the bias only**. Riz permits counter-trend scalps at half size to the 50%;
that is a separate mode and is **out of scope for v1** — see §10 Q6.

### 4.2 Range — the discount filter (J1, J2)

The range is the **External fib leg on `fb_bias_tf`**: origin (the swing the impulse launched from)
→ the running extreme. This is the leg `engines/fibonacci/` already draws, and its 0 keeps extending
while no new confirmed swing prints — which is Riz's "extend the range until price gives you a
discount" rule, for free.

- Long is eligible only while **price ≤ `fiboP2` (the 0.5)**.
- Short only while **price ≥ 0.5**.
- Not in the zone → block code 2.

⚠ **Do not re-anchor this leg on the entry timeframe.** The discount is an HTF statement. Reading
it off the 5m turns "buy cheap" into "buy any pullback".

### 4.3 Liquidity precondition (J3)

At least one of these must have been **swept within the last `fb_sweep_window` bars** (default
**48** bars of `fb_trap_tf`), on the correct side:

1. a `LiquidityLevel` with `mitigated == True` and `side == "low"` (for a long) — PDL, PWL, H4 L, or
   a session low;
2. an **EQL** level taken;
3. the origin low of the failed break itself (§4.6 event B). **This one always qualifies**, which is
   why the setup can still fire with no named level nearby.

No sweep → block code 3.

⚠ **Rule 3 makes rules 1 and 2 a *confluence*, not a gate.** That is deliberate and it is a choice:
Riz says liquidity is mandatory, but his own trigger *is* a liquidity sweep, so requiring a second,
named level on top would refuse most of his own examples. `fb_require_named_liquidity` (default
**False**) flips this to the strict reading, and it is the first thing to sweep.

### 4.4 Institutional numbers (J4) — the only new geometry

A price grid. Levels sit at `floor(price / block) * block + offset × block` for each
`offset ∈ {0.0, 0.2, 0.5, 0.8}`.

| Input | Default | Note |
|---|---|---|
| `fb_round_block` | **0.0100** (EURUSD) | ⚠ **MUST BE SET PER INSTRUMENT AND MEASURED, NEVER INHERITED.** A gold default of 0.01 puts a level every 2 cents and the filter becomes a no-op that reports as ON. Proposed XAUUSD start: **100.0** → levels at x000/x020/x050/x080. |
| `fb_round_tol` | **0.15 × block** | how close is "at" a level |
| `fb_round_mode` | **"Confluence"** | `"Off"` · `"Confluence"` (scores it, never refuses) · `"Required"` (block code 4) |

Used two ways, exactly as he describes:
- **Entry refinement** — find the nearest grid level *above* `fiboP3` (0.618) and *above* `fiboP6`
  region. Those become preferred resting prices in §4.7.
- **Targets** — a grid level sitting just short of a liquidity pool is where a hard TP goes (§4.9).

🔴 **This input is the one place a wrong default is silent.** A block size too large finds no levels
and the filter refuses everything; too small finds a level everywhere and it refuses nothing. Both
look like a working filter from outside. **A build must print a histogram of how often
`fb_round_mode = "Required"` raised block code 4 before any result off it is believed** — this is
the exact shape of the 2026-08-04 minimum-stop incident, where a guard passed parity having refused
nothing in 21,897 bars.

### 4.5 Left-side confluence — optional

Scored, never required, unless `fb_limit_orders` is on (§4.7).

- a live **FVG** overlapping the entry band;
- a live **order block** overlapping it;
- an un-swept **PDL/PWL** within `fb_round_tol` of it;
- a `engines/candlesticks/` reversal pattern within `fb_candle_window` bars (default **3**),
  direction-aligned. Default **OFF** — the 2026-08-08 measurement puts the useful patterns at
  5–9% of all bars, so on their own they filter nothing.

### 4.6 The trigger — the failed break (J5) 🔴 **this is the strategy**

Read `engines/market_structure/` on `fb_trap_tf` (default **15m**). Three events, in order:

⚠ **The trap timeframe was corrected from 5m to 15m after re-reading the source.** He marks the
pattern on the **15m** throughout his own walkthrough ("all these 15-minute lows", "this is on the
15-minute", "we're on the 15 right now"), occasionally 30m, and drops to 5m/1m only to refine the
fill. His ranking is explicit: *"If you're doing this on a 15, a five, it's going to hold a bit more
weight. An hourly, it's going to hold even more weight."* And on the 1m: *"more tricky… it gets so
noisy… expect you could take more stop losses."* **A 1m default would have measured the noisiest
version of his setup and reported it as his setup.**

| | Event | Engine signal | Window |
|---|---|---|---|
| **A** | the **early break** — structure breaks up, buyers commit | `bull_sos` on `fb_trap_tf`. Record `origin = bull_bos_low`, `origin_bar = bull_bos_l_loc` | — |
| **B** | the **sweep** — those buyers are stopped out | a bar whose **low < `origin`** | within `fb_fail_window` bars of A (default **20**) |
| **C** | the **real break** — price breaks up again | the next `bull_sos` on `fb_trap_tf` | within `fb_confirm_window` bars of B (default **12**) |

On C: **armed**. Record `swept_low` = the lowest low between A and C. That is the protected low.

Three shaping rules:

- **A must be a genuine trap, not noise.** Require the A→B leg to be at least
  `fb_min_trap_atr` × ATR(14) tall (default **0.5**), else discard and wait. Without this, every
  5m wiggle in a range is an "early break".
- **B is a wick sweep, not a close.** `low < origin` — a close-through would be a real trend
  continuation, not a stop run. This mirrors the liquidity engine's `SWEEP_LOW` rule.
- **C must be aggressive.** The breaking candle's range ≥ `fb_impulse_atr` × ATR(14)
  (default **1.0**). Riz says "aggressively" every time he describes it, and an aggressive break is
  the only part of his trigger that is a *measurement* rather than a shape.

✅ **The SOS Fade version, and it is worth building as a flag rather than a separate strategy.**
`fb_htf_stack` (default **False**): require the same A/B/C sequence to have completed on
`fb_stack_tf` (default **1H**) within `fb_stack_window` bars, before the entry-timeframe one. Riz
names this as his highest-conviction shape. It will be rare. **Measure trade count before believing
any R figure off it** — see §9.

### 4.7 Entry

Two modes.

| `fb_entry_mode` | Behaviour |
|---|---|
| **`"Break"`** (default) | market/stop entry on the close of event C |
| **`"Retrace"`** | rest a limit inside the C leg. Preferred price = the nearest `fb_round` grid level inside the band; failing that, `fiboP2` (0.5) of the C leg; failing that, the C leg's FVG or order block midpoint. Order cancelled if unfilled after `fb_limit_bars` (default **8**) or if the swept low is taken. |

Riz's own rule of thumb, which `"Retrace"` encodes: if the C impulse is small, just take it; if it
is large, wait for the pullback so the stop is not paying for the impulse.

`fb_limit_orders` (default **False**) — allow arming a resting limit **before** event C, with no
confirmation, only when §4.5 carries ≥ `fb_limit_confluence` (default **2**) layers. Riz does this
and it is how he trades while away from the screen. Stop is then fixed at `fb_limit_stop` (default
**35 pips**, his figure) unless structure allows tighter.

⚠ **Nothing in this repo may express a stop in pips.** Convert at the seam
(`algos/shared/order_sizing.py`'s rule: money → lots), and state the instrument. A 35-pip default
inherited onto gold is the 54.82-lot incident's exact shape.

### 4.8 Stop

`entry` → **below `swept_low` − `fb_stop_buffer`** (default **0.05 × ATR(14)**).

- `exec_min_stop_mode` is **inherited from SOS Fade and stays ON at 0.08 "% of price"**. A stop this tight
  is precisely where `qty = risk / stop_distance` detonates.
- If the resulting stop is wider than `fb_max_stop_atr` × ATR(14) (default **2.0**), **refuse the
  trade** (block code 6). Never shrink the stop to fit — a resized order is not the trade the
  emulator holds.

### 4.9 Targets and management (J6)

**Target picker**, first match wins, searching in the trade direction from entry:

1. the nearest **un-swept** HTF `LiquidityLevel` (PWH/PDH/H4 H/session H) on `fb_target_tf`
   (default **1D**);
2. failing that, the nearest **un-mitigated HTF FVG** far edge;
3. failing that, the nearest **EQH** cluster;
4. failing that, `fiboP10` (1.0) of the §4.2 range.

If the chosen target is within `fb_min_rr` × stop distance (default **6.0R**), **refuse the trade**
(block code 7). The whole thesis is that the target is far; a 1:2 version of this is a different
strategy and should be measured as one, not shipped as this one.

**Ladder** — his, mechanised:

| Trigger | Action |
|---|---|
| **+3.0R** | close `fb_tp1_pct` (default **20%**), move stop to breakeven |
| interim swing high / previous HH | close `fb_tp2_pct` (default **30%**) |
| target | close the rest |

Two exceptions, both his:

- **No breakeven when there is no structure.** If price ran to +3R without printing a new confirmed
  swing (`last_conf_low` unchanged since entry), take the partial but **tighten the stop under the
  last minor low** instead of moving to breakeven. He is explicit that the partial has already paid
  for the trade.
- **A hard TP is mandatory at the target.** `fb_hard_tp` default **True**. He lost 50 pips holding
  for a squeeze that did not come, and later gave back ~$20k of open profit on three 1:9–1:11
  positions by holding past a completed idea.

**Re-fib on completion.** When the §4.2 range completes (target hit, or `fiboP10` reached), the
range is redrawn and the new 50% governs. 🔴 **This is the rule whose absence cost him the $20k** —
he kept buying a discount that had become a premium of a newer range. It must be a rule, not a
habit.

### 4.10 Stacking

`fb_max_stack` (default **3**), `fb_stack_risk_free` (default **True**).

A second position on the same HTF idea may be opened only when:

1. every existing position has its stop at breakeven or better — **at most ONE position carries risk
   at any moment**; and
2. the new entry passes §4.1–§4.8 in full, on the next HTF higher low; and
3. all positions share the §4.9 target.

✅ **Rule 1 is why this does not need the unbuilt account allocator (G10).** The repo's standing rule
is that risk is budgeted per account and never layered. "Never add while the first is at risk" is
that rule, satisfied by construction — the account's live risk never exceeds one `fb_risk_pct`. This
is worth stating out loud because "pyramiding" reads like a violation and is not one.

🔴 **It is still an architecture change.** `sos_fade`'s `Execution` holds ONE position and every
sizing, staging and exit path assumes it. Multi-position support is the single largest build item in
this spec — see §7.

### 4.11 Risk and caps

| Input | Default | Source |
|---|---|---|
| `fb_risk_pct` | **0.5** | his funded figure |
| `fb_max_attempts_day` | **3** | his rule; he blew an account ignoring it |
| `fb_max_stack` | **3** | §4.10 |
| `fb_time_stop_mode` | **"Off"** | ⚠ SOS Fade defaults this to `"Before TP1 only"` at 36h. **This strategy holds for weeks by design and must pin it Off**, or the whole thesis is cut at hour 36. |

⚠ **`exec_secondary` must be pinned `False`.** It is a 1-minute re-entry designed for SOS Fade's exit
ladder and there is no 1m stream in a swing book.

---

## 5. Block codes — why no trade

The export twin and the Python port must both emit these, same numbering, or the parity gate cannot
tell "refused" from "never saw it".

| Code | Meaning |
|---|---|
| 1 | no HTF bias |
| 2 | not in discount / premium |
| 3 | no liquidity swept in window |
| 4 | not at an institutional level (`fb_round_mode = "Required"` only) |
| 5 | trigger incomplete — A without B, or B without C in window |
| 6 | stop too wide / too tight |
| 7 | target closer than `fb_min_rr` |
| 8 | daily attempt cap reached |
| 9 | stack full, or an existing position still carries risk |

---

## 6. Config — every input with its default

```
fb_bias_tf                 "4H"        anchor timeframe
fb_trap_tf                 "15m"       where the failed break is read  (was 5m — corrected §4.6)
fb_fill_tf                 "5m"        where the fill is refined; 1m allowed, noisier
fb_stack_tf                "1H"        the SOS Fade stacked-trap timeframe (his highest-conviction shape)
fb_target_tf               "1D"        where the final target is read from

fb_sweep_window            48          bars, §4.3
fb_require_named_liquidity False       strict reading of §4.3
fb_fail_window             20          bars A→B
fb_confirm_window          12          bars B→C
fb_min_trap_atr            0.5         × ATR(14), A→B leg height
fb_impulse_atr             1.0         × ATR(14), the C candle
fb_htf_stack               False       require the 1H trap first
fb_stack_window            96          bars

fb_round_block             0.0100      ⚠ PER INSTRUMENT, MEASURED
fb_round_tol               0.15        × block
fb_round_mode              "Confluence"  Off | Confluence | Required

fb_candle_window           3           bars; candlestick confluence
fb_use_candles             False

fb_entry_mode              "Break"     Break | Retrace
fb_limit_bars              8
fb_limit_orders            False
fb_limit_confluence        2
fb_limit_stop_money        —           ⚠ money, never pips; unset = refuse

fb_stop_buffer             0.05        × ATR(14)
fb_max_stop_atr            2.0         × ATR(14)
fb_min_rr                  6.0         R
fb_tp1_r                   3.0         R
fb_tp1_pct                 20
fb_tp2_pct                 30
fb_hard_tp                 True

fb_max_stack               3
fb_stack_risk_free         True
fb_risk_pct                0.5
fb_max_attempts_day        3

exec_min_stop_mode         "% of price" / 0.08     inherited from SOS Fade, stays ON
exec_time_stop_mode        "Off"                   ⚠ pinned, not inherited
exec_secondary             False                   ⚠ pinned
```

⚠ **Every field above must have a Pine input behind it before it is built.** A field the export
cannot carry is a field the gate can never check — that is what killed the first BOS port.

---

## 7. Build cost — what already exists and what does not

| Piece | Status |
|---|---|
| Structure, fib, liquidity, EQH/EQL, FVG, OB, candlestick engines | ✅ built, Pine-parity validated |
| Discount/premium filter | ✅ the fib's `P2`, already there |
| Fib-band entry, leg-origin stop, staged stop, R sizing | ✅ `sos_fade`'s exit ladder, inheritable |
| Multi-timeframe read (4H bias + 5m trigger + 1D target) | ⚠ **partial** — `run_dual` exists for SOS Fade 15m/1m and has exactly one caller; `backtest/optimizer.run_sweep` replays a SINGLE frame and **refuses** a dual-stream strategy. A three-stream strategy cannot be swept today. |
| **Institutional-number grid** | ❌ **new** — small, ~40 lines, plus a Pine overlay. `mpc_jarvis.pine` is at the compile-token ceiling, so the paste needs a matching dead-code trim. |
| **Failed-break trigger (§4.6)** | ❌ **new** — the core. A three-event state machine over `ExternalEvents`. |
| **Target picker (§4.9)** | ❌ **new** — reads the liquidity engine; modest. |
| **Multi-position book (§4.10)** | 🔴 **new and large.** `Execution` is single-slot end to end. |

🔴 **The sweep/optimizer blocker is the one that decides the order of work.** Until a
multi-timeframe strategy can be swept, no parameter in §6 can be tuned. Either build the target
picker to read HTF levels off the *same* frame (resample inside the strategy), or extend
`run_sweep`. That decision comes before the Pine.

---

## 8. The backtest plan

### Stage 0 — the cheap study, BEFORE any Pine 🟢 do this first

`backtest/tools/fb_trigger_study.py`. Replay the cached XAUUSD M15/M5 history through the structure
engine, detect §4.6 A/B/C, and measure the trigger with a **skeleton exit** — entry on C, stop under
`swept_low`, fixed 10R target, no filters. Report:

- how many triggers fire, per year and per month;
- hit rate and expectancy against a **matched random control** (same bar count, same direction
  distribution) — this is the shape the VWAP filter used on 2026-08-06 and it is what makes a
  weak result readable;
- the distribution of stop distance in ATR;
- how far the nearest HTF liquidity pool actually is, in R, at trigger time. **This one number
  decides whether the strategy exists**: if the median is 3R, there are no 1:15s here.

Then the same for each filter added one at a time (discount, named liquidity, round numbers, HTF
stack), so each is priced separately rather than as a bundle.

**Cost: hours. It requires no TradingView, no export and no human.** If stage 0 says the trigger is
indistinguishable from a random entry, the other five stages are not worth Aaron's five minutes.

### Stages 1–6 — the real gate

Per `docs/STRATEGY_WORKFLOW.md`, unchanged:

| # | Artefact |
|---|---|
| 1 | this file |
| 2 | `strategies/tradingview/fb_strategy.pine` — compiles, runs in the Strategy Tester |
| 3 | `strategies/tradingview/fb_strategy_export.pine` — plots `px_*` decisions and `cfg_*` inputs |
| 4 | **a real CSV export — the one step only Aaron can do** |
| 5 | `strategies/python/fb/` |
| 6 | `strategies/python/fb/tools/compare_fb.py` — **exit 0** |

⚠ **The export twin is at risk on this one.** Pine caps a script at 64 `plot()` calls and the SOS Fade
export block is already near it. A three-timeframe strategy with a three-event trigger and a stack
of three positions needs more decision columns than SOS Fade does. **Plan the `px_*` column budget before
writing the Pine**, not after.

⚠ **A green gate proves nothing about a branch neither side entered.** If the export is taken with
`fb_htf_stack` off and `fb_round_mode = "Confluence"`, the gate says nothing about the stacked trap
or the round-number filter. Take a second export with them on, and read the coverage table before
the exit code.

---

## 9. What a measurement here can and cannot answer 🔴 read before asking for numbers

**Sample size is the binding constraint and it is worse than B-LEG's.** Riz's $140,000 came from
roughly a dozen HTF ideas on ONE pair in twelve months. This setup is designed to fire a few times a
month at best, and the *stacked* SOS Fade version will fire a handful of times a year. This repo has
already learned twice what that means: B-LEG's 50 trades over 6.5 years gave a 95% CI on mean R of
−0.40 to +0.37, which is a measurement that has not started. **Expect the same shape here, and do
not accept a total R as evidence without its error bars and its largest-trade-removed figure.**

**The result will be tail-heavy by construction, and that is not a defence.** A strategy whose thesis
is 1:15 winners *should* have a fat tail. The test the repo already applies stands: strip the single
best trade and check the remainder is still positive. Riz's own 1m re-entry cousin failed exactly
that test.

🔴 **Swap is first-order here, not a rounding error.** Holds are 43 trading days in his own example.
He reports FTMO swaps reaching **2% of the account** on a single position. This repo's swap figures
for PU Prime's raw tiers are **UNMEASURED and now raise** (2026-08-06), and on one account
`XAUUSD.s` and `XAUUSD.crp` were measured **8.5× apart** on swap with the short credit gone
entirely. **A free-book backtest of this strategy is not a conservative estimate — it is the wrong
number.** Charge `swap` from the first run, and state the broker profile on every result.

⚠ **The instrument is wrong for the cached data.** He trades EURUSD; this repo's cache and every
measured cost is XAUUSD on Vantage. Either fetch EURUSD history (and re-measure its history floor —
never hardcode it) or accept that the result describes gold, which is a different animal: he
explicitly says he traded gold once because he had not learned its personality.

⚠ **One position slot changes what a filter costs.** Run 12's lesson applies directly — with a
single slot, a refused setup is not a subtraction, it is a queue, and the sign of the effect can
flip. §4.10 makes this a three-slot book, which changes the arithmetic again. **Any filter here must
be priced by a real replay, never by deleting rows from a finished trade list.**

⚠ **Do not report a per-trade RR from the stack.** §2.

---

## 10. Open questions — decisions before a line is written

| # | Question | Why it blocks |
|---|---|---|
| **Q1** | Does §4.6's three-event sequence actually reproduce what Riz points at on a chart? | It is my reading of a video. **The cheapest check is visual**: emit the triggers onto the command-center price chart over a year and look at fifty of them. Everything downstream is worthless if this is the wrong pattern. |
| **Q2** | `fb_round_block` for XAUUSD — 100, 50, or 10? | §4.4. Measure it: how often does price turn within tolerance of each grid, against a random-offset control? |
| **Q3** | EURUSD or XAUUSD first? | §9. EURUSD is his instrument and needs new history + a re-measured floor and new cost figures. XAUUSD is cached and priced but is not the thing he traded. |
| **Q4** | Extend `run_sweep` to multi-frame, or resample inside the strategy? | §7. Nothing can be tuned until this is answered. |
| **Q5** | Build the multi-position book, or ship v1 single-slot? | Single-slot v1 measures the *trigger and the target*, which is the interesting half, and defers the largest build item. My recommendation: **v1 single-slot.** |
| **Q6** | Counter-trend scalps (his half-size mode) — in or out? | Out for v1. It is a second strategy sharing a chart. |
| **Q7** | Is the `fb_htf_stack` version separable at all? | If it fires four times a year, it can be described but never measured. Say so rather than reporting its R. |

---

## 11. Where this deliberately departs from Riz

| His | This spec | Why |
|---|---|---|
| "eyeball the significant low" | the engine's fib leg | a spec with discretion in it cannot be backtested |
| liquidity always required | the trigger's own sweep counts (§4.3) | his own examples fail the strict reading |
| stop in pips | stop in money, converted at one seam | the 54.82-lot incident |
| discretionary partial at "a high" | a rule at the previous HH | otherwise it is unmeasurable |
| hold for the squeeze | `fb_hard_tp = True` by default | he names this as the mistake that cost him twice |
| counter-trend scalps | out of scope v1 | §10 Q6 |
| 1:20RR headline | a stack total, never a per-trade figure | §2 |

---

## 12. Recommended order of work

1. **Q1 — visual check.** Emit §4.6 triggers onto the price chart. Look at them. *(hours)*
2. **Stage 0 study.** Trigger expectancy vs a random control; the R-to-nearest-liquidity
   distribution. *(hours)* — **stop here if it is flat.**
3. Answer Q2, Q3, Q4, Q5 from what stage 0 shows.
4. Stage 2 Pine, stage 3 export twin — with the `plot()` budget planned first.
5. Aaron takes the CSV *(five minutes, and it is the step that finds the defects)*.
6. Stage 5 port, stage 6 gate green, **then** sweep §6 and write
   `docs/FB_OPTIMIZATION.md`.

**Nothing between step 2 and step 6 produces a number anyone may act on.** A table of results from a
strategy without a green gate reads as a finding no matter what caveat sits under it —
`bos_sweep.py` was falsified by a single Strategy Tester run on the day it was written.
