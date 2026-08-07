# MPC BOS — optimization log

One entry per sweep, so a question already answered is not re-measured. Same convention as
`strategies/python/mpc_sos_fade/mpc_sos_fade_optimization.md`.

**Where the old log went.** Runs 1–4 (2026-07-31) lived in `strategies/python/mpc_bos/`, which was
deleted on 2026-08-04 as a half-built port with no parity harness (commit `1946f8b`). Their
findings are summarised in Run 5 below and the full text is recoverable at `1946f8b^`. They are
not restated here in full; they are cited, because Run 5 only makes sense against them.

⚠ **NO NUMBER IN THIS FILE COMES FROM A PINE↔PYTHON PARITY-VALIDATED RUN.** There is still no
`mpc_bos_strategy_export.pine` and no `compare_bos.py` (spec §10 steps 3–4 are open). Runs 1–4 came
from a Python port that was never validated; Run 5 comes from a deliberately simplified skeleton
that is not the strategy at all. Read the DIRECTION of everything here, never the decimals.

---

## Run 5 (2026-08-07) — the first configuration that beats a control, and the FVG entry comes OFF

**The question Aaron asked:** *"use everything in the parameters to give me a profitable strategy,
optimize it."* Runs 1–4 had already answered the literal version of that and the answer was no —
82 configurations, profit factor below 1.0 in every one. So this run did not re-search the same
space. It asked what had CHANGED since, and one thing had: **the session VWAP filter (F10), which
was in none of the earlier runs.**

That matters because of what Run 3 concluded:

> *"Every input the strategy has describes the SETUP... Not one of them separated winners from
> losers consistently. What did was the state of the market at the moment of the setup, which no
> existing input can express."*

**VWAP is a context variable.** It is the axis Run 3 said was missing, and unlike Run 3's own
volatility split it has not gone dark with the regime.

### Method — and the three guards, because 564 configurations is how a fit gets manufactured

`backtest/tools/trigger_edge.py` + `bos_sweep.py` (session scratch, grid transcribed below). The
canonical `market_structure` + `vwap` engines are replayed ONCE over **186,384 true-M15 XAUUSD bars
(2018-09-13 → 2026-08-07)**; only the cheap entry logic runs per configuration. Scored **+2R before
−1R**, no sizing, no ladder, no compounding.

1. **A matched random CONTROL per configuration**, on direction *and* stop distance. Gold ran
   1,200 → 4,300 across this window, so a long-side "edge" is free and any harness without a
   control will find one. The control lands on the theoretical breakeven with expectancy ~0.000.
2. **A half-split** — must be positive in BOTH halves of history. This is precisely the test that
   killed Run 3's volatility rule and Run 4's regime labels.
3. **The configuration count is reported**, so the multiple-comparison exposure is visible rather
   than implied. 564 scored.

### The result

| configuration | n | win rate | vs control | net expR after spread | PF |
|---|---|---|---|---|---|
| **0.786 entry · fib 1.0 stop · VWAP on** | 201 | 46.8% | **+14.5% (+4.1σ)** | **+0.276R** | 1.76 |
| 0.786 entry · fib 1.0 stop · VWAP off | 578 | 40.1% | +7.8% (+3.8σ) | +0.101R | 1.34 |
| 0.5 entry (old depth) · VWAP on | 509 | 36.7% | +3.7% (+1.7σ) | +0.056R | 1.16 |
| **0.5 entry · VWAP off — WHAT SHIPPED BEFORE TODAY** | 793 | 36.1% | +2.8% (+1.7σ) | +0.040R | 1.13 |

✅ **Positive in 9 of 9 years.** ✅ **Each switch degrades smoothly** rather than falling off a
cliff, which is the shape a real effect has and a fitted one does not.

✅ **The strongest single piece of evidence is the direction split: shorts +17.7% beat longs
+12.3%.** Gold tripled across this window, so a drift artefact shows up as longs carrying
everything — `mpc_sos_fade/CLAUDE.md` records that exact trap, and Run 3 flagged its own
longs-vs-shorts slice as confounded and unusable. This one points the other way.

✅ **VWAP was tested PAIRED across the whole grid, not cherry-picked from the top:** 276 matched
on/off pairs, VWAP improves expectancy in **210** of them, median ΔexpR **+0.054**.

### 🔴 The headline is not VWAP — it is that the GAP ENTRY comes OFF

**Entry depth is a bigger lever than the filter**, and the two compound. Moving the limit from the
0.5 band to a plain fib 0.786 is what takes the configuration from +3.7% to +14.5%.

That is the same conclusion Run 1 reached from the opposite direction, seven days earlier and with
a different tool:

> *"**The FVG entry — the core of the spec — is the entire loss**, and it has no tail at all: 98
> trades and not one bigger than +3.3R."*

**Two independent measurements, different implementations, same verdict.** The mechanism is that
the GAP decides where the limit rests, and it rests too shallow for a continuation trade — which is
Run 1's structural read ("the entry band and the setup disagree") arriving with a number attached.

⚠ Note this does NOT vindicate Run 1's proposed fix. Run 1 recommended inverting the ladder to the
*shallower* 0.382–0.5 Sniper-Zone pocket; Run 2 then corrected itself and withdrew that read. The
measured answer is **deeper**, not shallower.

### 🔴 The top row of the raw sweep was DISCARDED, and this is the important part

Ranked on expectancy alone the winner was **0.786 entry + 0.886 stop at +0.563R**. It is not in the
shipped defaults, and the reason is a cost measurement rather than a judgement call:

| stop model | median stop | p10 stop | spread as % of R | expR | **net of spread** |
|---|---|---|---|---|---|
| fib 0.886 | **$0.74** | **$0.31** | **29.8%** | +0.563 | +0.265 |
| **fib 1.0 (leg origin)** | $1.73 | $0.73 | 12.7% | +0.403 | **+0.276** |

At a $0.22 Vantage spread the 0.886 stop gives back 30% of R before the trade starts, and the
deepest tenth of its trades rest stops under $0.31 — untradeable. **After costs the ranking
inverts.** This is Run 1's collapsing-stop hazard reached from a new direction: there it inflated
sum-R through position sizing, here it inflates win rate through an unpayable stop distance.

⚠ **Standing rule this run adds: rank on expectancy NET of the spread, not on expectancy.** On this
strategy the two orderings disagree at the top, and the gross ordering picks the configuration you
cannot trade.

### Shipped defaults changed (2026-08-07)

| input | was | now |
|---|---|---|
| `bosUseFvg` | `true` | **`false`** |
| `bosEntryFib` | `"0.618"` | **`"0.786"`** — now the PRIMARY entry, not a fallback |
| `bosWhich` | `"1st only"` | **`"All"`** |
| `bosMinDispAtr` | `0.5` | **`0.0`** |
| `bosSlModel` | `"Fib 1.0 (leg origin)"` | unchanged — **and it must stay** |
| `bosVwapReq` | (new, 2026-08-06) | `"Trend's side"` |

⚠ **Changing a default does not change a chart that already has saved values.** These take effect
on a fresh paste or after "Reset settings to defaults".

### What this run does NOT establish

⚠ **The exit model is not the strategy's.** The skeleton scores a flat +2R-or-−1R. The Pine runs a
30/30/20 ladder with a staged stop and a runner. **The direction transfers; the magnitude does
not**, and `+0.276R per trade` must never be quoted as this strategy's expectancy.

⚠ **564 configurations were searched.** The defences are the 9-of-9 years, the half-split, the
shorts-beat-longs direction check, the smooth degradation across switches, and the paired VWAP
test. They are decent. They are not proof, and this is exactly the exposure Run 3 named in itself.

⚠ **Aaron confirmed on 2026-08-07 that the new defaults beat the old ones in the TradingView
Strategy Tester — DIRECTIONALLY ONLY. The three numbers (net profit, profit factor, trade count)
were not recorded, so no figure anywhere in this repo describes a real run at these settings.**
Record them on the next run; until then the Strategy Tester's agreement is a fact about the sign
and nothing more.

⚠ **Still no parity harness.** Everything above is a claim about a model of the strategy, checked
once against the strategy by eye.

### The next three questions, in order

1. **Record the six numbers** — A vs B, net profit / PF / trade count. Cheapest thing on this list
   and it is the only one that would put a real figure against these defaults.
2. **Does the real TP ladder keep the edge?** A 0.786 entry lands `longTier = 2` (deep), so TP1
   becomes fib 0.5 at ~1.34R. That is a different trade from the flat 2R the skeleton scored.
3. **Build `mpc_bos_strategy_export.pine` + `compare_bos.py`** (spec §10 steps 3–4). Until then
   nothing here can be validated, and the last port was deleted for exactly that reason.

Reproduce: `python3 backtest/tools/trigger_edge.py` for the trigger study; the grid script is
session scratch (`bos_sweep.py`) and its grid is `entry ∈ {0.382, 0.5, 0.618, 0.786} ×
stop ∈ {fib1.0, fib0.886, ATR2, ATR3} × which ∈ {all, 1st, 1st+2nd} × disp ∈ {0.0, 0.5} ×
RR ∈ {1.0, 1.5, 2.0} × vwap ∈ {off, on}`.

---

## Run 6 (2026-08-07) — the real exit ladder, and why the TP rungs went to 0/0/100

Run 5 scored every configuration as "+2R before −1R". The Pine does nothing of the sort, so the
question it left open — *does the real ladder keep the edge?* — is answered here by running it.

Measured on **186,384 true-M15 bars (2018-09-13 → 2026-08-07)**, one position slot, spread and
swap charged, at the 0.786 entry:

| rungs (TP1/TP2/TP3 %) | n | sumR | expR | PF | maxDD |
|---|---|---|---|---|---|
| **0 / 0 / 100** | 168 | **+107.5R** | +0.640 | 2.23 | 8.7R |
| 0 / 0 / 0 (pure runner) | 165 | +81.9R | +0.496 | 1.95 | 11.3R |
| 0 / 50 / 50 | 168 | +79.1R | +0.471 | 1.90 | 8.4R |
| 30 / 30 / 20 (the old default) | 165 | +58.2R | +0.352 | 1.67 | 9.0R |
| 50 / 50 / 0 | 168 | +36.9R | +0.219 | 1.42 | 10.0R |
| 100 / 0 / 0 | 168 | +23.1R | +0.137 | 1.26 | 14.6R |

**Banking early is what costs, and it costs a lot** — the old 30/30/20 default gives up nearly
half the total against holding to TP3.

⚠ **The stop protection is NOT what you give up by setting the rungs to zero, and that is the
whole reason 0/0/100 is safe.** Touching TP1 stages the stop to breakeven and touching TP2 lifts
it to the TP1 price *whatever the rung sizes are* — the PRICES drive the staged stop, the SIZES
only decide how much is banked there. So 0/0/100 is a ratcheting hold, not an unprotected one.

⚠ **A pure runner (0/0/0) is worse than exiting at TP3**, which is the counter-intuitive half:
TP3 is fib 0.000, the leg's own extreme, and past it the structure trail hands back more than the
tail pays.

## Run 7 (2026-08-07) — the stop model was the whole game, and R was flattering the old default

**35,000+ configurations** over the same 186,384 bars, via `backtest/tools/bos_sweep.py`.
This run changed the shipped defaults.

### The finding

🔴 **The old `Fib 1.0 (leg origin)` stop makes the stop distance a FRACTION OF THE LEG, so a small
leg produces a tiny stop mechanically — and R = profit / stop, so a tiny stop inflates every R in
the book without one extra dollar being made.** Measured on the old default: **median stop $1.58,
tightest tenth $0.64**, where the $0.22 spread is **34% of R** and a 15-minute bar's low simply
cannot say whether the stop was touched — inside that bar price crosses the spread constantly.

The first leaderboard of this sweep was **entirely** such configurations: every top-15 row had a
median stop of **$0.74** and read +250R to +450R. None of them is a strategy; they are a
measurement artefact, and they are exactly the trap `bosEntryFib`'s own tooltip already warned
about. **Ranking on R alone cannot see this, which is why every mode of the tool now prints the
tightest-tenth stop beside the result.**

### What replaced it

`bosSlModel = "ATR"`, `bosSlAtr = 1.3`, plus `execMinStopMode = "% of price"` at `0.10` as a
second line of defence. An ATR stop does not care how big the leg was: **median $3.89, tightest
tenth $2.06**, spread 10.7% of R there.

Compared at a **MATCHED 25% drawdown budget** — the only fair way to rank a 55-trade book against
a 600-trade one, since summing R treats a 25R drawdown as three times worse than an 8R one when at
10% risk it is the difference between giving back 30% and giving back 93%:

| | trades | sumR | PF | win% | mult @25%dd | half A | half B |
|---|---|---|---|---|---|---|---|
| before Run 7 (fib 1.0, no floor) | 168 | +107.5R | 2.23 | 56% | 23.0x | 3.4x | 8.6x |
| **shipped today (ATR 1.3 + 0.10%)** | **161** | +54.4R | 2.27 | 75% | **65.4x** | 7.3x | 13.8x |

⚠ **The sumR column goes DOWN and that is not a loss** — a wider stop means each R is a bigger
dollar amount, so the same money is fewer R. The multiple at a matched drawdown is the comparison.

### Why this is not just a leaderboard

* **Half-split.** Configurations chosen on 2018-2022 score **+0.243 expR** on 2022-2026 against a
  survivor average of **+0.123**; chosen on the later half they score **+0.566** on the earlier
  against **+0.096**. The search transfers rather than fits.
* **Paired jitter, 40 replays.** The unpaired medians had the old and new defaults TIED (42.8x vs
  42.3x) because the real price series is unlucky for one and lucky for the other. Scoring BOTH on
  the SAME jittered series separates them: **the new default wins 32 of 40**, and clears 4x on
  **both** halves in **28 of 40** against the old default's **4 of 40**.
* **Matched random control**, 400 draws, same directions and same stop/target distances on random
  bars: the trigger clears the control at **p = 0.04**. ⚠ This is the weakest number here and it
  is stated rather than buried — the ATR geometry is high-win-rate by construction (75%), so
  random entries with the same geometry also score positively and the trigger's contribution is
  diluted. The old fib default measures a *stronger* control edge (2.5σ) on the same 168 entries,
  which is a fact about the exit geometry and not about the trigger.
* **Plateau, not peak.** ATR 1.2 → 60.9x, 1.3 → 65.4x, 1.4 → 47.4x, 1.5 → 55.2x. Anything from
  1.2 to 1.5 is one answer inside the noise; 1.3 is the middle of the shelf, not the top of a spike.
* **Positive in 9 of 9 years**, longest losing streak 3, top 5 trades 28% of the total.

### What did NOT change, and was re-confirmed

`bosUseFvg` off, entry `0.786`, `bosWhich` "All", VWAP filter on, `bosMinDispAtr` 0.

⚠ **VWAP is the single most load-bearing filter in the file and it is not close.** Off, the book
goes to 533 trades for +51.5R at PF **1.23** — and its second half is **1.0x**, i.e. it stopped
working. The filter is what makes everything else measurable.

⚠ **`max_days`, `min_leg`, `late`, `per_regime` and the runner trail all measured as NO-OPS** at
these settings, and `min_disp` above 0 actively costs. They are not tuned values; nothing is
riding on them.

### Standing caveats

⚠ **Still no parity harness.** `mpc_bos_strategy_export.pine` exists and a real 20,079-bar export
has been taken, but `compare_bos.py` is not written, so **everything here is a claim about a model
of the strategy rather than about the strategy**. The model reproduces the Pine's structure engine,
VWAP engine, entry model, staged stop and TP ladder, and it holds one position — but it has never
been diffed against the Pine's own decision stream. **Read Run 7 as a strong prior, not as a
validated result, until that gate is green.**

⚠ **No TradingView Strategy Tester figure describes these defaults either.** The six numbers are
still unrecorded.

⚠ **These defaults do not move any chart you have saved settings on.** TradingView keeps a chart's
saved input values; changing a default only affects a fresh paste. Use *Reset settings to defaults*
to pick them up.

Reproduce: `python backtest/tools/bos_sweep.py sensitivity | frontier | settle`.

---

## Run 8 (2026-08-07) — 🔴 RUN 7 IS FALSIFIED. Read this before believing anything above it.

Aaron pasted the new defaults into TradingView and ran the Strategy Tester. **The model Run 7
was built on does not agree with the Pine, and the gap is not a rounding difference.**

Same symbol, same timeframe, same window (2025-09-30 → 2026-08-07), config confirmed identical by
the Pine's own `[CFG]` echo — `useFvg=false entryFib=0.786 anchor=Break leg which=All minDisp=0
slModel=ATR slAtr=1.3 minStop=% of price/0.1 tp=0/0/100 vwap=Trend's side risk=10`:

| | `bos_sweep.py` model | TradingView Strategy Tester |
|---|---|---|
| trades | 20 | **24** |
| win rate | 80.0% | **66.67%** |
| profit factor | 2.97 | **1.04** |
| return on 10K @ 10% risk | +102.5% | **+5.01%** |
| max drawdown | 27.1% | **34.11%** |

**The Strategy Tester is the ground truth. The model is wrong.**

### What this invalidates

Everything in Run 7 that is a NUMBER: the 65.4x at a matched drawdown budget, the 32-of-40 paired
jitter win, the 28-of-40 both-halves result, the ATR plateau figures, and the R totals in Run 6.
All of them came out of `backtest/tools/bos_sweep.py`. **None of them may be quoted.**

⚠ It does NOT automatically make the shipped defaults wrong. Run 7 compared two configurations
measured by the SAME model, so a shared bias could cancel and leave the RANKING intact — or it
could not. **That is unknown, and unknown is what it must be recorded as.** The defaults stay as
shipped and are labelled unvalidated until the A/B below is run.

### Where the disagreement is

**Entries roughly agree** — 20 against 24 over the same ten months. **Exits do not.** The model
averages +0.73R per win against a −1.02R loss; the Tester's 66.67% win rate at PF 1.043 implies
its winners are roughly HALF its losers. So the model is extracting materially more from its
winners than the Pine does, and the fault is in the exit ladder — the staged stop, the structure
trail, or how the position actually leaves at TP3.

### The second finding, and it is the one that generalises

🔴 **The Strategy Tester header read "Mar 8, 2018 — Aug 7, 2026 DEEP" and the strategy received
bars from 2025-09-30.** Ten months, not eight years. The `[CFG]` line is stamped
`2025-09-30T18:00:00` because it fires on `barstate.isfirst` — the first bar the script ever saw.
The chart is capped at ~20,000 bars, which is exactly the size of the export CSV taken the same
day, same first bar to the minute.

⚠ **This repo has now met that defect in three places** — the hardcoded history floor at the start
of a window, `run_report.py`'s default `--start`, the bar cache recording its REQUESTED range, and
now a vendor UI advertising a range it does not deliver. **Never read what you requested as what
you received.** The date range in that header is what TradingView will let you ASK for. Nothing on
the panel says what arrived, and every statistic beside it describes ten months while looking like
it describes eight years.

### What must happen next, in order

1. **The A/B in the real engine, which needs no model at all.** Same chart, revert only
   `bosSlModel` → `Fib 1.0 (leg origin)` and `execMinStopMode` → `Off`, and read the four numbers
   against today's `24 trades / +5.01% / PF 1.043 / 34.11% DD`. That answers "did Run 7's change
   help or hurt" in TradingView's own engine. **Do this before trusting either configuration.**
2. **Build `strategies/python/mpc_bos/` and `backtest/tools/compare_bos.py`** and get it to exit 0.
   The export already exists (20,079 bars, 2025-09-30 → 2026-08-07, taken at the pre-Run-7 config).
   Until that gate is green, no Python measurement of this strategy means anything.
3. **Re-run the sweep against the PORT**, not against a skeleton, and rewrite Run 7.

⚠ **Ten months is not enough history to conclude anything either way.** PF 1.043 over 24 trades is
indistinguishable from noise in both directions. The 20,000-bar ceiling is a hard constraint on
every question that can be asked on this chart; a 1H chart reaches back about two and a half years
for the same bar budget.

### The standing lesson

**A model of a strategy is not the strategy, and the giveaway was available the whole time.** Run 7
carried its own caveat — "NOT PARITY-VALIDATED, read as a strong prior" — and that caveat was
correct and was still not enough, because a table of numbers reads as a finding no matter what
sentence sits under it. The repo's rule already says a feature nobody has RUN is not a feature.
The sharper version this adds: **a measurement nobody has CHECKED AGAINST THE THING IT MEASURES is
not a measurement, and the cheapest possible check — one Strategy Tester run — was one paste away
for the entire day it went unrun.** Run the ground truth first, then optimise.
