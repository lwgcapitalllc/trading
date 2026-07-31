# MPC BOS — optimization log

One entry per sweep, so a question already answered is not re-measured. Same convention as
`strategies/python/mpc_sos_fade/mpc_sos_fade_optimization.md`.

⚠ **Every number here was produced by `strategies/python/mpc_bos/`, which has NOT passed a
Pine↔Python parity check** — there is no `mpc_bos_strategy_export.pine` and no `compare_bos.py`
yet (spec §10 steps 3-4 are open). The port is anchored, not validated: at the pre-2026-07-29
defaults over the same 365-day window it takes **12 trades where the spec's real TradingView run
(§10b) took 13**, so trade SELECTION is close. Treat the direction of these results as sound and
the decimals as provisional.

Data: local MT5 cache, `XAUUSD 15m`, **186,027 bars, 2018-09-13 → 2026-07-31** (7.9 years).
Fill model `"bar"` (the Pine's own intrabar guess, zero costs). `exec_risk_pct = 10`, $100k start.

---

## Run 1 (2026-07-31) — 82 configurations. Nothing is profitable.

**Profit factor is below 1.0 in every one of the 82 configurations tested.** The best final
equity in the whole sweep is **$42,604 on $100,000** (`bos_which = "1st only"`, guard on) — the
least-bad way to lose 57% of the account. The shipped defaults give **193 trades, +2.4R, and
$17,729 of $100,000 left** at 91.2% max drawdown.

### The headline finding: every profitable-looking row is the collapsing-stop hazard

Phase 2 ranked `bos_sl_model = "Fib 0.886"` far above everything else — up to **+80.7R**. It is
not an edge. It is Run 4's defect from the A+ file, reproduced exactly here and for the same
structural reason: **the entry is a resting limit anywhere in 0.5-0.886 of the leg, and every stop
option except `"Fib 1.0 (leg origin)"` sits inside or barely outside that same band.** A limit that
fills deep leaves cents of stop distance, `qty = risk / dist` balloons, and price runs straight
through what was supposed to be 1R.

| config | min stop $ | worst trade | trades < −1.5R | sum R | final equity |
|---|---|---|---|---|---|
| shipped (stop = fib 1.0) | 0.76 | −1.94R | 4 | +2.4 | $17,729 |
| stop = fib 0.886 | **0.109** | **−7.61R** | 11 (−31.4R) | +46.1 | $7,284 |
| …+ min-stop guard 0.1% | 1.05 | −3.38R | 4 | **+0.2** | $17,484 |
| 0.886 + disp 0.0 + 1st+2nd (top row) | **0.109** | **−14.33R** | 13 (−48.9R) | +80.7 | **−$3,186** |
| …+ min-stop guard 0.1% | 1.05 | −4.11R | 4 | **−21.1** | $2,828 |

Installing the guard removes the entire +46R / +80.7R. **Sum R is not a safe metric on this
strategy until `exec_min_stop_mode` is on** — an oversized position books a huge R on a win and a
blow-through on a loss, so R rises while the account dies. Every phase-3 row has the guard on.

### Phase 3 — all levers, guard installed, sorted by sum R

Best rows: `ATR stop + disp 0.0` +51.7R / PF 0.98 / equity $9,378 · `0.886 + disp 0.0` +20.4R /
PF 0.95 · `fib 1.0 + disp 0.0` +19.8R / PF 0.94. **Baseline with the guard: −14.9R, PF 0.74.**
Note what the top rows have in common — they all need `bos_min_disp_atr = 0.0`, i.e. dropping the
displacement requirement entirely and taking 320-473 trades. Going LOOSER is the only direction
that improves the number, and it still never reaches PF 1.0.

### Where the book loses (shipped defaults + guard, 187 trades, −14.9R)

**By the source that priced the entry, measured AT PLACEMENT** — the gap is routinely mitigated by
the very tap that fills the order, so reading the source at fill time mis-attributes ~46 trades:

| entry source | n | sum R | R/trade | win | best | worst |
|---|---|---|---|---|---|---|
| **FVG** | 98 | **−15.1** | −0.154 | 0.58 | **+3.3** | −1.6 |
| **Sniper Zone** | 89 | **+0.2** | +0.002 | 0.46 | **+11.2** | −1.9 |

**The FVG entry — the core of the spec — is the entire loss, and it has no tail at all: 98 trades
and not one bigger than +3.3R.** The Sniper Zone half breaks even and holds every large winner.

**By BOS ordinal:** 1st −5.0R (83) · 2nd −7.9R (48) · 3rd −12.3R (27) · 4th+ **+10.4R** (29).
The 4th+ row is ONE trade (+11.2R best) — a description of a single day, not a rule. F1's real
reading is that 2nd and 3rd breaks are the worst part of the book, not that 4th+ is good.

### Levers that do nothing (guard on, vs the −14.9R baseline)

`bos_max_per_regime` 2 · `bos_min_leg_atr` 1.0 · `exec_fvg_50` — all three are **byte-identical to
baseline**. The leg-size floor never binds (break legs are already >1 ATR), the regime cap rarely
binds, and the straddle-0.5 entry only fires where the Sniper Zone already priced the leg.

### The confluences do not rescue it

Divergence veto −16.3R · divergence exit −17.1R · both −19.6R · require FVG strictly (`exec_conf_sz2
= False`) −14.9R at 104 trades · drop deep-fib −14.2R · break-leg anchor −16.7R · measured-move TP2
−28.2R · daily/weekly bias gate **untestable in Python** (`w_est_state`/`d_est_state` are not
computed in the port, so `"Must agree"` blocks every trade — 0 trades, not a result).

### The structural read

The entry band and the setup disagree. Entering at 0.5-0.886 of the **expansion** leg on a
**continuation** setup means buying only after price has given back most of the break — the same
conflict F4 exposed in §10b, generalised. The Sniper Zone (0.382-0.5 of the **break** leg) is the
shallower, genuinely-continuation pocket, and it is the only half of the book that is not losing.
**The obvious next experiment is to invert the ladder: make the Sniper Zone the primary entry and
test the 0.382-0.5 band instead of 0.5-0.886.** That is a change to spec §5, so it is Aaron's call,
not a tuning run.

Reproduce: the scripts are session scratch (`sweep.py` / `sweep2.py` / `sweep3.py` / `diag.py` /
`split2.py`); the grids are transcribed above.

---

## Run 2 (2026-07-31) — a dialled risk-reward on each entry half. Still no edge, and it
## CORRECTS Run 1's read of which half is better.

Run 1 had no way to ask "what if I risk 1 to make 2": the stop and both targets are fibs, so the
ratio is an OUTPUT of leg geometry. Three research dials were added to make the question
expressible — `bos_entry_source`, `bos_exit_mode = "Fixed R"` (+ `bos_rr_tp1`/`bos_rr_tp2`), and a
`"Break leg origin"` stop. **None of them exist in `mpc_bos_strategy.pine`**, so any run using a
non-default value is research and cannot go through the parity gate until the Pine matches.

### ⚠ Correction to Run 1: the Sniper Zone is NOT the better half

Run 1 reported SZ +0.2R vs FVG −15.1R and recommended promoting the zone. **That gap was the fib
ladder, not the entry.** An SZ entry is shallower, so its fib targets sit further away in R — it
inherited a better risk-reward for free. Control for that (same ATR stop, same R target on both)
and the ranking inverts: median MFE is **1.11R for FVG vs 0.83R for SZ**, and FVG beats SZ at
every ratio at every stop size tested. The Run 1 split is still true as measured; the CAUSAL read
drawn from it was wrong.

### The answer to "make it a 1:2"

At the best stop for it (3 × ATR14), **Sniper Zone at 1:2 wins 25.6% where it needs 33.3%** —
137 trades, −14.8R, $2,112 left of $100,000. It loses at 2, 3 and 4 ATR alike. The best 1:2
anywhere in the study is FVG-only on a 2 × ATR stop at **33.0% vs the 33.3% needed** — dead level,
not profitable.

**A wider target is monotonically worse, and the shortfall grows with it** (SZ, 3 × ATR stop —
`edge` = achieved win rate minus the rate that ratio needs to break even):

| target | 1:0.75 | 1:1 | 1:1.5 | 1:2 | 1:2.5 | 1:3 |
|---|---|---|---|---|---|---|
| win rate | 0.522 | 0.449 | 0.343 | 0.256 | 0.228 | 0.178 |
| needs | 0.571 | 0.500 | 0.400 | 0.333 | 0.286 | 0.250 |
| **edge** | −0.050 | −0.051 | −0.057 | **−0.078** | −0.058 | −0.072 |

The curve tracks the break-even line and sits **just under it everywhere**. That is the signature
of no edge — not of a mis-set target. Why 1:2 specifically fails: the median SZ trade's best-ever
excursion is **0.83R**, so a 2R target sits above the 75th percentile of what these trades ever
reach (p75 = 2.12R). Only ~26% get there.

### The best row in the whole study, and why it is still not a finding

`FVG only + 2 × ATR stop`: 1:0.75 → 61.3% (needs 57.1%), 1:1 → 55.7% (needs 50.0%), 1:1.5 → 41.5%
(needs 40.0%). Sum R +3.2 / +3.6 / +0.7 and PF 0.97-0.98 — **still under 1.0**. With n = 106 the
standard error on a ~50% win rate is ±4.9 points, so the biggest beat (5.7 points at 1:1) is
**1.2 standard errors**. It is a coin flip, and +3.6R over 106 trades is +0.034R per trade.

**A tighter stop beat a wider one**, which is worth recording because it is the opposite of the
premise: FVG 2 × ATR beats 3 × and 4 × at every ratio. Widening the stop does not buy survival —
the win rate barely moves while every loss gets bigger in price.

### A real defect this run exposed — the minimum-stop guard has a hole

The first fixed-R grid produced absurd rows: `ATR 0.5, 1:1.5` at **+61.9R** (one trade worth
**+71.4R = 75% of all gross R**, on a **7-cent** stop) and `ATR 1.0, 1:1` at −107.6R (one trade at
**−103R**). Both from the same mechanism: **`_stop_clears_floor` is checked against the LIMIT
price, but `risk_usd` is measured at the FILL.** A limit that gaps to a much better fill lands
almost on top of its own stop, the R denominator collapses, and that trade's R becomes meaningless
in both directions. The guard passed a $2.00 floor and the trade realised a $0.07 stop.

**This is inherited from `mpc_sos_fade`, not introduced here** (same `_open_position`, same
placement of the check), so it applies to the A+ bot as well — worth a look before that bot goes
live, given `docs/LIVE_TRADING_PIPELINE.md` is active. Practical rule for reading any run on this
family: **when the stop can land near the entry, trust the equity curve, not sum R.**

---

## Run 3 (2026-07-31) — hunting a CHARACTERISTIC instead of a parameter.

Runs 1-2 tuned global settings. This asks the different question: measure a set of properties at
the moment each order is placed, take EVERY break (`bos_min_disp_atr = 0`, 452 trades) so nothing
is pre-filtered, and look for a property that sorts outcomes **in both halves of history**.
Thirteen features: BOS ordinal, expansion past the broken swing, displacement, leg size, entry
depth in the band, bars waited, regime age, entry source, volatility, live divergence, direction,
NY hour, weekday.

### The headline: NO SETUP property sorted the outcomes. The ENVIRONMENT did.

This is the finding, and it is a negative result about the whole parameter set. **Every input the
strategy has describes the SETUP** — which break, how big, how far it displaced, which gap priced
it, how deep the entry sits. Not one of them separated winners from losers consistently. What did
was **the state of the market at the moment of the setup**, which no existing input can express.

| volatility at entry (ATR14 as % of price) | n | sum R | R/trade | H1 | H2 |
|---|---|---|---|---|---|
| **< 0.15%** | 258 | **+49.4** | +0.192 | +17.4 | +32.0 |
| 0.15 - 0.25% | 157 | **−27.9** | −0.178 | −13.3 | −14.6 |

Re-tested as a live rule (`bos_max_atr_pct`, which had to be built — F10), it produced **the first
profit factor above 1.0 in the entire study**, and it degrades SMOOTHLY, which is the shape a real
characteristic has:

| cap | ≤0.10 | ≤0.12 | ≤0.15 | ≤0.18 | ≤0.20 | none | **≥0.15 (inverse)** |
|---|---|---|---|---|---|---|---|
| n | 151 | 243 | 314 | 369 | 400 | 452 | 249 |
| sum R | +56.2 | +52.6 | +50.7 | +45.2 | +15.1 | +19.8 | **−109.9** |
| PF | **1.17** | **1.08** | 0.99 | 0.97 | 0.93 | 0.94 | **0.48** |

The inverse is the strong half of the evidence: the filter is not dropping random trades, it is
isolating a systematically losing population. Per-year, the ≤0.15 rule is positive in **6 of 9
years** (2018, 2019, 2020, 2022, 2023, 2025), so it is not carried by one era.

### Why it is NOT a green light — three reasons, and the third is the serious one

1. **PF only clears 1.0 at the tightest caps**, which are also the thinnest.
2. **The market has left the regime the rule needs.** Gold's median 15m ATR ran 0.081% of price in
   2018 and **0.216% in 2026** — 90% of 2026 bars are above the 0.15% line and the 0.10% cap took
   **zero trades in 2026**. An absolute threshold has gone dark.
3. **The regime-RELATIVE reformulation fails, and that undercuts the mechanism.** `bos_max_atr_rel`
   (F10c — ATR against its own ~10-day EMA, i.e. "quiet FOR THIS MARKET") should have reproduced
   the effect and kept it alive across regimes. It does not: PF runs 1.23 / 0.95 / 0.94 / 1.01 /
   1.02 / 0.99 / 0.97 across caps 0.7 → 1.5 — **non-monotonic**, and only 4-6 of 9 years positive.
   A threshold whose result flips between 0.7 and 0.8 is a fit. If the story were really "quiet
   markets respect structure", the relative form should have been the STRONGER one.

**Read it as: this setup is conditional on a market state, and that state is currently absent** —
not as a filter to switch on. Also note the multiple-comparison exposure: 13 features were examined
and then a threshold was tuned on the winner. The half-split, the smooth sensitivity curve and the
inverse test are the defences; they are decent, not proof.

### Two other consistent slices, one of them confounded

- **NY 12:00-16:00 is negative in BOTH halves** (n=52, −22.1R, H1 −10.3 / H2 −11.8) — the only
  clock slice that is. Built as F11 (`bos_no_ny_pm`); mildly positive in combination.
- **Longs +32.9R (both halves) vs shorts −13.1R.** ⚠ **Confounded — do not act on it.** Gold ran
  1,200 → 4,100 across this window. "Longs work on a 3x bull market" is the regime talking, and
  `mpc_sos_fade/CLAUDE.md` records the mirror-image trap on the A+'s short skew.
- Weekday (Thursday +32.8R both halves) is almost certainly noise on 84 trades — recorded so it is
  not rediscovered and believed.

### The constructive read

The gap in the parameter set is **context, not setup quality**. `engines/regime/` already exists in
this repo (TRENDING / TRANSITIONING / RANGING / HIGH_VOLATILITY / LOW_VOLATILITY), is used by the
lab, and has **never been wired to this strategy**. The measurement above says a coarse volatility
split already separates this book better than any setup property does — so the canonical classifier
is the obvious next thing to test, and it is a shim away rather than new logic.

---

## Run 4 (2026-07-31) — the canonical regime classifier. It does NOT sort this book.

Run 3's follow-up, and the answer is no. `engines/regime/classifier.py` was called (never
reimplemented — it is the single implementation and a second one is forbidden) once per H1 bar on
a trailing window, with the bots' own inputs (`df_short` = H1, `df_long` = H4), and mapped onto the
15m stream with **no lookahead**: a 15m bar at time t may only read an H1 bar that has already
CLOSED (H1 timestamp + 1h ≤ t).

| regime | n | sum R | R/trade | win | 1st half | 2nd half |
|---|---|---|---|---|---|---|
| TRENDING | 373 | +11.0 | +0.029 | 0.53 | **−18.0** | **+29.0** |
| TRANSITIONING | 77 | +8.7 | +0.113 | 0.64 | **+21.9** | **−13.1** |
| RANGING | 2 | +0.1 | — | — | — | — |

**Both labels flip sign between the halves** — the same out-of-sample test Run 3's volatility split
passed, and this fails it.

### Why, and this part matters beyond the BOS strategy

**The classifier is very nearly a constant on XAUUSD H1/H4.** Over 47,378 H1 bars (2018-2026):

| TRENDING | TRANSITIONING | RANGING | HIGH_VOLATILITY | LOW_VOLATILITY | UNKNOWN |
|---|---|---|---|---|---|
| 36,818 (78%) | 9,908 (21%) | 524 (1.1%) | **0** | **0** | 128 |

**The two volatility labels never fire once in eight years**, which is exactly the pair that would
have matched Run 3's finding. The mechanism is structural, not a data problem: both require
`score_norm <= 1`, which needs ADX < 20 *and* ATR ratio < 0.8 *and* RSI-range < 20 together, and
that happens on 1.1% of H1 gold bars. Even then the label only leaves RANGING if the ATR ratio
clears 1.5 or falls under 0.5 — and `atr_ratio` is ATR(14) against its own 20-period mean, which
sits near 1.0 by construction and essentially never reaches those bounds.

**So the regime layer cannot supply the context dimension Run 3 identified — not for this strategy
and not, on this evidence, for any strategy on XAUUSD H1/H4 as currently configured.** Worth
knowing for the A+ bot and the lab, which both consume the same classifier. Note this is a
statement about its DISCRIMINATION on this instrument, not about its correctness: labelling a gold
chart that ran 1,200 → 4,100 as mostly TRENDING is defensible. It just carries almost no
information for filtering a trade list.

**Where that leaves the context idea:** Run 3's raw ATR-percent split still sorts the book better
than anything else tested, and it is not reachable through `engines/regime/`. Making it usable
would mean either new thresholds on the classifier (a change to a canonical shared engine, with
every other consumer to re-validate) or keeping it strategy-local as F10. Neither is worth doing
until the underlying edge is established — and Run 3's own relative-form failure says it is not.
