# CLAUDE.md — Loss Recovery

**Purpose:** After a strategy takes a real stop-out, take one counter-trade on the opposing
external CHoCH, secure the loss back at +1R, and trail the rest.
**Scope:** Signal + trade management + R accounting. No sizing in lots, no broker calls, no UI,
no structure detection of its own.
**Status:** 🔴 **LAB ONLY.** `enabled` defaults False. No Pine twin exists, so there is no
`compare_*.py` parity gate and there never will be until one is written. Nothing imports this
package outside its own tests and `backtest/tools/recovery_report.py`. It has never been traded.
**Last reviewed:** 2026-08-18 — built this session from Aaron's question "when I lose, can I get
back in the other way and win the loss back?"

---

## The rule

1. A primary trade takes a real stop-out (`r < -scratch_r`; a scratch is not a loss).
2. Wait for an **external CHoCH** on the same timeframe in the **opposite** direction. Median
   wait ~13 hours. No CHoCH, no trade — and `pending()` reports the losses still waiting.
3. Either direction. See *Why both directions* below; this is not a preference.
4. Enter at the **next bar's open** after the CHoCH bar closes.
5. Stop at the **far end of the break leg** — `bull_bos_low` / `bear_bos_high`. That distance is
   this trade's 1R.
6. Size at **25%** of a normal trade's risk.
7. At **+1R**, move the stop **to +1R**. The loss is now paid back and cannot be given away.
8. Then trail the stop to each new confirmed swing level. **No target.**
9. Hard close at 30 days — a backstop against swap, not a working rule.

---

## MEASURED

`python backtest/tools/recovery_report.py --start 2018-09-14 --end 2026-08-14 --sweep`

XAUUSD M15, 186,910 bars, `mpc_sos_fade` at shipped defaults with `exec_secondary=False`,
warmup 1000, bar fills. **Both sides costed at `puprime_ecn`** — the live account's tier.

| | |
|---|---|
| Primary alone | 181 trades, gross +138.9R → net **+129.0R**, **1,913x** @10%, maxDD **48.8%** |
| Recovery | 62 trades, **+16.2R** at full size, **58%** win, 35 of 62 locked, median hold ~4 days |
| At 25% size | **2,772x** at **48.3%** drawdown — **1.53x** what the same drawdown buys on the risk dial |

**25% is two answers at once**: the largest size that does not raise drawdown above what the bot
already runs, *and* the peak of the efficiency curve. The curve is flat from 20% to 55% (1.53 →
1.48), so it is not a knife edge.

⚠ **Charging costs to the recovery leg and not to the primary is rule 11 broken, and it flips the
verdict.** Uncosted-primary-vs-costed-recovery said the risk dial won; costing both says the
recovery wins by 1.3–1.7x. The primary holds a median **0.3 days** and 100 of its 181 trades are
SHORTS, which gold pays a swap *credit* to hold — so it loses only 7% of gross to costs while the
recovery loses far more. The tool charges both and must keep doing so.

---

## 🔴 It does NOT reduce max drawdown. It buys RETURN.

**MEASURED 2026-08-19, and it is the first thing to say to anyone who reaches for this to make a
losing streak hurt less.** Max drawdown at 25% size is **48.3%** against the primary's **48.8%** —
unchanged. At 100% size it goes **UP**, to 57.2%. **There is no size at which this protects the
account.** The gain is 1,913x → 2,772x at the same drawdown, and that is the whole trade.

The intuition it defeats is a good one, so record why it fails rather than just that it does.
The hope is that a recovery trade fires mid-streak and shortens the hole. It DOES fire mid-streak
and it is not too slow — over 13 losing streaks (longest 4), **76% of recoveries resolved before
the next primary loss landed**, and every streak got a signal. The arithmetic is what kills it:
inside those streaks the recoveries put back **+0.75R** against **−16.4R** of losses they sat
between. **5%.**

⚠ It cannot be fixed by sizing up. A recovery is a quarter-size trade winning 58% of the time; at
full size it wins more R but its 42% of losses arrive at the exact moment the curve is already at
a local low, which is why the drawdown rises faster than the return. `backtest/tools/recovery_report.py --sweep`
prints both columns — read them together, never the balance alone.

**If the goal is a smaller drawdown, the lever is `exec_risk_pct`, not this module.**

### ⚠ Re-measured 2026-08-20 from a real lab run, and the drawdown answer is WEAKER than "unchanged"

Aaron ran the toggle from the Command Center (run `236e206d0142`) and got a 37.8% drawdown where
this section said to expect ~48%. The run was right; the comparison was not. Same settings
(`exec_risk_pct` 10, quarter size), one variable at a time, drawdown on the strategy's own
compounding dollar balance:

| window | costs | A+ alone | + recovery | change |
|---|---|---|---|---|
| 2018-09-14 → 2026-08-14 | none | 45.6% | 44.2% | −1.4 pt |
| 2018-09-14 → 2026-08-14 | `puprime_ecn` | 50.2% | 50.3% | **+0.1 pt** |
| 2020-01-01 → 2026-08-20 | none *(Aaron's run)* | 45.6% | **37.8%** | **−7.8 pt** |
| 2020-01-01 → 2026-08-20 | `puprime_ecn` | 50.2% | 48.7% | −1.5 pt |

🔴 **Same rule, four defensible framings, answers from +0.1 to −7.8 points. The drawdown effect is
NOISE, not an effect that happens to be small** — which is a stronger statement than the "it does
not reduce drawdown" above and replaces it. ⚠ **The run that looks best is the one charging
NOTHING**: `cost_layers` was `[]`, so $0.00 of spread, commission or swap across 213 trades. Costed,
the same window makes $22.5M instead of $51.1M. **Ask what a run priced before reading its drawdown.**

⚠ **Do not compare a lab page's drawdown with the ones above it in this file either.** Those come
from `recovery_report.py`, which compounds a sequence of R at a fixed risk %; the lab walks the
strategy's own dollar sizing, where a trade is sized when its limit is PLACED. Two honest methods,
two different numbers on identical trades.

### 🔴 The 1.53x headline needs ONE ACCOUNT, and the shipped toggle does not give it one

**MEASURED 2026-08-20 on run `236e206d0142`'s own trades, and it is the most important correction
in this file.** The same book, added up two ways:

| | balance multiple | maxDD |
|---|---|---|
| A+ alone, as the lab runs it | 4,921x | 45.6% |
| **+ recovery, as the lab runs it** | **5,107x (+3.8%)** | 37.8% |
| A+ alone, one shared compounding balance | 6,026x | 45.6% |
| **+ recovery, one shared compounding balance** | **9,636x (+59.9%)** | 42.2% |

**+3.8% against +59.9% for the identical trades.** The recovery leg is worth **+5.04R
account-weighted** either way; what differs is whether that R gets to COMPOUND.

🔴 **The cause is a deliberate design choice in the wiring, not a bug** —
`mpc_sos_fade/recovery.py` sizes the recovery off the running balance but never lets A+ size off
the recovery, so a lab toggle cannot move a parity-gated book. The cost is that recovery profit
sits BESIDE the curve instead of lifting it, and over a run that grows 5,000x an early gain is
rounding by the end. ⚠ **That adapter's own note called this understatement "small". It is not —
it is most of the result, and this table is the correction.**

⚠ **Neither column is the answer.** The 3.8% is what the lab prints today and is the number to
quote for anything measured through the Command Center. The 59.9% is what the same trades are worth
if the profit compounds — but it also assumes **one balance with NO risk budget on it**, and that
is the assumption that turns out to decide everything.

### 🔴 Put ONE RISK BUDGET on that balance and the sign flips. This is the real state of the question.

**MEASURED 2026-08-20, same run, re-priced onto one balance at a 10% account cap.** A recovery
holds risk for a median of ~4 days, and **23 of this run's 160 A+ entries opened while one was
already holding**. A+ risks the full 10% and the cap IS 10%, so every one of those 23 competes.

| | multiple | maxDD | vs A+ alone |
|---|---|---|---|
| A+ alone, one balance | 4,921x | 45.6% | — |
| + recovery, every entry granted in full | 7,125x | 42.1% | **+44.8%** |
| + recovery, A+ shrunk to the room left | 4,191x | 39.9% | **−14.8%** |
| + recovery, A+ refused outright | 116x | 43.3% | −97.6% |

🔴 **The plausible range spans +45% to −15%, and which end you land on is decided entirely by an
allocator that DOES NOT EXIST on the live side.** MEASURED on this run: an A+ trade averages
**+0.882R** and a recovery averages **+0.095R account-weighted** — **9.3x** — so giving budget to
the second at the first's expense is a bad swap the moment the cap binds. **"How would
this have behaved?" has no answer yet, and the width of that range IS the finding.**

⚠ **All three rows are RE-PRICES, not replays, and this repo has been bitten by exactly that** — an
entry-side filter estimated at +1.84R replayed at −1.84R, because shrinking or refusing an entry
frees the position slot and a freed slot admits a setup the book does not contain. The −97.6% row
in particular is an artifact of deleting compounding winners, not a forecast. Read the three as a
BRACKET on how much the contention matters, never as results.

⚠ **The middle row is PESSIMISTIC on its own terms**: reservations fall to zero at breakeven, A+
reaches breakeven in a median of one bar, and a recovery reserves nothing once it locks at +1R. So
the real shrink binds far less often than 23 times. **That is a reason to go and measure it, not a
reason to assume the top row.**

### ✅ BUILT AND RUN 2026-08-20 — `leg.py` + `backtest/tools/recovery_stack.py`

The rule now runs as a real LEG through `backtest/portfolio/` — one balance both legs size against,
one live risk budget they compete for, one merged clock, a refusal log. **It is not a second copy
of the rule**: trade management lives in `position.ManagedPosition`, which `engine._manage` also
drives, and the extraction was proved byte-identical over ten configs on real bars. Only the
ARMING side is new, because a stepped driver has to answer bar by bar what the batch engine
pre-computes.

**The sizing defect is closed, and it was CHECKED rather than declared.** Recover the balance each
trade believed it had (its booked risk ÷ its own risk rate) and score it against both models:

| | before (the lab toggle) | after (the leg) |
|---|---|---|
| median gap to the JOINT balance | — | **0.000%** |
| median gap to the SPLIT balance | ~0 (149 of 155 matched it) | **4.947%** |
| trades nearer the JOINT model | — | **206 of 212** |

⚠ **Neither model is exact to the cent and that is not the fix leaking.** A resting limit is SIZED
WHEN PLACED and the balance moves before it fills — on closes, on partial exits, and on costs
booked as they happen. So the test is which model each trade TRACKS, and it flipped completely.

**MEASURED, 186,910 M15 bars 2018-09-14 → 2026-08-14, `puprime_ecn`, A+ 10%, recovery 25% of that:**

| account cap | A+ alone | + recovery leg | verdict |
|---|---|---|---|
| **10%** (A+ alone already fills it) | $13,199,534 · 50.2% | **$9,251,114 · 50.4%** | **−29.9%** |
| **12.5%** (room made for it) | $13,199,534 · 50.2% | **$17,074,731 · 50.4%** | **+29.4%** |

🔴 **The recovery leg is not the variable — HEADROOM is.** A+ risks the full 10% and the cap is
10%, so the two legs at full size want 12.5% of a 10% budget: **every overlap shrinks A+ by
construction, and 25 of its 181 entries were shrunk.** An A+ trade averages 9.3x a recovery trade's
account-weighted R, so trading one for the other is a bad swap. Give the recovery its own 2.5% on
top and the same trades add +29.4%. **The question is not "is the recovery worth taking" — it is
"is it worth 2.5% of account risk that A+ is not already using".**

**The concurrency rule is SHARE, and it is stated in the run's own output.** `PortfolioAccount`
grants `min(desired, room)`; that is the canonical account in this repo and a second allocator is
forbidden. ⚠ **`--on-contention refuse` REFUSES TO RUN rather than fake it**: the account carries
ONE entry floor for every leg while these legs risk different amounts, so any floor that makes A+
all-or-nothing also bans every 2.5% recovery entry outright — measured, 64 refusals and 0 trades,
identical at a 10% and a 12.5% cap. A refusal rule needs a PER-LEG floor on the shared account.

⚠ **Peak open risk 10.9% against a 10% cap, and it is not a hole.** The cap binds AT FILL against
the balance at that moment; the reservation is then a fixed dollar figure while the balance keeps
moving, so a later loss shrinks the denominator under a grant already made. Nothing was ever
granted over the cap.

⚠ **A+'s R moved −0.10R (127.11 → 127.01) on the shrink path and is UNEXPLAINED.** R is normalised
to each trade's own risk, so a pure sizing change must leave it byte-identical — the recovery leg's
R does, to the cent. 0.10R is 0.08% of the book and far under this strategy's 15.06R jitter floor,
so it changes no conclusion, but it is a real disagreement with an invariant and it is written down
rather than rounded away. It appears only where entries are shrunk. **Scale-in is OFF by default,
so the obvious candidate is ruled out.**

⚠ **Three limits of the leg, each refused or counted rather than absorbed**: one position at a time
(the account keys one per leg; 5 setups skipped over 7.9 years, counted separately from budget
refusals), no ATR (a config needing one is refused, naming the batch tool), and no look-ahead by
construction.

### 🔴 THE SPLIT SWEEP — measured 2026-08-20 under a hard 10% exposure ceiling, and it settles the question

Aaron's constraint, verbatim: *"I dont want my exposed risk ever over 10% at a time."* So this
sweep holds TOTAL risk at 10% and moves only the SPLIT, rather than sweeping a recovery size
against a fixed A+. 186,910 M15 bars, 2018-09-14 → 2026-08-14, `puprime_ecn`, rule SHARE. Every
`A+ alone` row is that same run's own solo control, so no two rows come from different code paths.

| plan | final balance | maxDD |
|---|---|---|
| A+ 6% alone | $1,720,547 | 32.4% |
| A+ 7% alone | $3,088,653 | 37.2% |
| A+ 6% + recovery 4% | $2,589,198 | 38.4% |
| A+ 7% + recovery 3% | $4,223,442 | 40.5% |
| A+ 8% alone | $5,256,114 | 41.7% |
| **A+ 8% + recovery 2%** | **$6,506,262** | **42.5%** |
| A+ 9% + recovery 1% | $9,502,543 | 45.8% |
| A+ 9% alone | $8,518,854 | 46.1% |
| A+ 10% alone | $13,199,534 | 50.2% |

**Two pairs DOMINATE outright — more money AND less drawdown — so they read without interpolation,
without a risk-adjusted metric, and without arguing about which axis matters:**

- **A+ 9% + recovery 1% beats A+ 9% alone**: $9.50M vs $8.52M, at 45.8% vs 46.1%.
- **A+ 7% alone beats A+ 6% + recovery 4%**: $3.09M vs $2.59M, at 37.2% vs 38.4%.

🔴 **So the recovery earns its place as a SMALL slice and destroys value as a large one, and the
turn is between 2% and 3%.** A quarter-size recovery under A+ at 8% is on the good side of that
turn; **1% under A+ at 9% is better still.**

🔴 **The headline is that the recovery is not the big lever, and this table is how you see it.**
Under a fixed 10% ceiling A+'s own risk rate moves the result far harder than anything the recovery
does: taking A+ ALONE from 8% to 10% goes $5,256,114 → $13,199,534, while bolting a whole 2%
recovery leg onto the 8% version reaches $6,506,262. **The recovery buys EFFICIENCY at a given
drawdown; it cannot buy HEADROOM.** The most money available under a hard 10% ceiling is A+ alone
at 10% — which is what the live bot already does — so every split here is a decision to spend money
on drawdown, not a decision about whether the recovery rule works.

⚠ **Do NOT read the per-cell "+X% against its own control" figure ACROSS cells.** It climbs
monotonically as the plan gets worse — **+11.5%, +23.8%, +36.7%, +50.5%** at 9/1, 8/2, 7/3, 6/4 —
purely because the control it divides by is shrinking. **The best-looking uplift in the sweep sits
on the worst plan in it.** Compare the absolute column, or compare dominance pairs.

⚠ **The whole table is inside the noise band in R, and that caveat outranks every row above it.**
Put the legs in comparable units (R × that leg's risk rate, i.e. percent of balance): the recovery
contributes **14.8 / 29.5 / 44.3 / 59.1** at 9/1, 8/2, 7/3, 6/4, against an A+ jitter floor of
15.06R × the A+ rate = **136 / 120 / 105 / 90**. That is **0.11 to 0.66 of ONE standard deviation
of A+'s own run-to-run noise, in every cell.** The efficiency gain is real arithmetic on this
history; its SIGN is not established, and 60 recovery trades over 7.9 years will not establish it
soon.

⚠ **The 3% and 4% cells trip the tool's own headroom warning (both legs at full size want 10% of a
10% budget) and still report 0 shrunk, 0 refused.** That is not the warning being wrong — it is
reservations falling to zero at breakeven, which A+ reaches in a median of one bar. **A warning
about what COULD contend is not a measurement of what DID**, and the run prints both on purpose.

⚠ **Peak open risk reads 10.1% against a 10% cap in every cell**, for the reason already recorded
above: the cap binds AT FILL, and a later loss shrinks the balance under a grant already made.
Nothing was ever granted over the cap. **Holding the RATIO under 10% at every instant would mean
part-closing a live position because the account dipped — a different and worse strategy, and not
what the ceiling was asked for.**

⚠ **Adopting any of these splits is a LIVE change, and three things about the live cap differ from
this lab.** They are in `algos/CLAUDE.md`, not here — the short version is that the live side
refuses where this shrinks, counts a RESTING order where this reserves at fill, and compares
without a rounding tolerance, which puts a split summing exactly to the cap on a knife edge.

---

## 🔴 It does not smooth the equity curve either — and this qualifies the 1.53x headline

**MEASURED 2026-08-19.** Max drawdown is one worst moment. Everything describing the REST of the
curve is flat or marginally worse:

| | primary alone | + recovery @25% |
|---|---|---|
| Max drawdown | 48.8% | **48.3%** |
| **Average** drawdown | 16.6% | **17.2%** |
| **Median** drawdown | 11.4% | **12.2%** |
| % of trades under water | 75% | **79%** |
| Longest time under water | 612d | **612d** |
| Losing months | 37 / 86 | 40 / 88 |
| Std dev of monthly R | 4.78R | 4.76R |
| **Monthly mean / std** | **0.314** | **0.318** |

Same cause as the drawdown answer: 62 extra trades losing 42% of the time, opening immediately
after a primary loss — i.e. while the curve is already below its high. More small dips, not fewer.

⚠ **One figure looks like smoothing and is not.** Per-trade R volatility falls 3.32R → 2.88R, but
that is DILUTION from adding quarter-size trades, not a steadier curve. Return per unit of that
volatility goes the other way: **0.215 → 0.190**. Never read a volatility drop without the return
that came with it.

🔴 **What this does to the 1.53x claim, stated plainly rather than left for the next reader to
find.** In R the module adds **+4.1R on top of +129.0R — about 3%.** That compounds to 45% more
money (1,913x → 2,772x) because the extra R lands early enough to lift everything after it. But
**monthly risk-adjusted return is unchanged (0.314 → 0.318).** So "1.53x better than the risk
dial" is true *at matched MAX drawdown*, and max drawdown is a single point on the curve. On every
broader measure it is a wash.

**The honest summary: this buys a small amount of extra R that happens to compound well. It is not
a better-behaved strategy, it does not protect the account, and it does not smooth the ride.** Say
that before quoting the balance.

⚠ **If a smoother curve is the goal, this is the wrong lever** — the ones that would move it are
fewer correlated positions or a second strategy on a different structure stream. See root
CLAUDE.md → *The overlap audit*.

---

## 🔴 A tighter stop does not make the loss smaller. Holding 1R FIXED is what does.

**MEASURED 2026-08-19, from Aaron's question — "the structural stop is nearly as far as the whole
entry travel; can I get out for a small loss instead of a whole R?"**

**The trap first, because the intuitive answer is wrong and expensive.** A position is sized off
its stop distance, so halving the stop buys twice the position and the loss in money is
IDENTICAL. Moving a stop nearer changes how OFTEN you are stopped, never how much it costs.

`soft_stop_r` works because it does not move the stop that SIZED the trade. `risk` stays the
structural distance — 1R stays 1R, the position stays the same — and the rule simply refuses to
sit through more than a fraction of it. That is the only shape in which "take a smaller loss"
means anything. `test_a_soft_stop_does_not_move_the_number_the_trade_was_sized_on` is the guard,
and its named mutation is exactly the mistake above.

### What each of the four candidates actually did

`python backtest/tools/recovery_report.py --start 2018-09-14 --end 2026-08-14 --exits`
(186,910 M15 bars, both sides costed at `puprime_ecn`, 62 recoveries, one lever at a time)

| lever | net R | win | avg loss | vs the risk dial |
|---|---|---|---|---|
| **shipped** — structural stop, lock +1R→+1R | +16.2R | 58% | −1.01R | 1.53x |
| **soft stop, cut at −0.3R** | **+18.5R** | 37% | **−0.30R** | **1.90x** |
| exit on the opposing CHoCH | +9.7R | 52% | −0.61R | 1.23x |
| early breakeven step at +0.5R | +4.2R | 47% | −0.68R | 0.90x |
| lock later — arm +2R, stop to +1R | −2.3R | 37% | −1.04R | 0.53x |

🔴 **Three of the four LOSE, and two of them were my own suggestions to Aaron before anything was
measured.** Recorded rather than quietly dropped:

- **Structural invalidation costs 6.5R.** "Structure broke back, the reason for the trade is
  gone" is a good sentence and it is wrong here: an external CHoCH against a trade that is
  WORKING is a normal pullback, so the rule cuts winners to save losers it had already capped.
- **An early breakeven step is the worst lever on the board** — +16.2R → +4.2R. A structural stop
  is ~4x a normal one, so +0.5R is well inside the noise of the leg, and the step gets tagged on
  the retrace that precedes the run.
- **Separating the lock's trigger from its destination loses monotonically** (1.5→1 gives +3.1R,
  2→1 gives −2.3R). The shipped 1→1 is not a placeholder anyone forgot to split.

### The soft stop is a PLATEAU, not a peak — and it buys nothing

`--soft-curve` prints it in 0.05 steps with both halves and the top five winners deleted:

| cut at | net R | 1st half | 2nd half | less top 5 | win | maxDD |
|---|---|---|---|---|---|---|
| −0.15R | +8.5R | +4.1R | +4.4R | **−4.7R** | 15% | 49.6% |
| −0.2R | +11.8R | +6.4R | +5.3R | **−1.4R** | 23% | 48.7% |
| −0.25R | +17.1R | +9.5R | +7.7R | +3.3R | 32% | 46.5% |
| **−0.3R** | **+18.5R** | +12.1R | +6.5R | +4.7R | 37% | 47.0% |
| −0.5R | +13.8R | +9.2R | +4.6R | +0.0R | 40% | 49.1% |
| −0.75R | +18.0R | +10.6R | +7.4R | +4.1R | 53% | 47.4% |
| structural | +16.2R | +7.5R | +8.6R | +2.3R | 58% | 48.3% |

🔴 **Read the net-R column before the ranking: every value from −0.25R to structural sits between
+12.9R and +18.5R.** That is one flat region, not a curve with a winner in it, and the run-to-run
spread on this strategy is **sd 15.06R** (`jitter_audit.py`). **So the honest claim is that
cutting early is FREE, never that it earns more.** The `vs dial` column ranks them 1.90x against
1.53x and that ratio is driven by max drawdown, which is one moment.

**What DOES move monotonically is the size of a loss** — avg −1.01R → −0.30R, worst −1.27R →
−0.44R — **paid for in win rate**, 58% → 37%. That is the whole trade, and it is a preference
about how a losing recovery should feel rather than a return decision.

⚠ **It collapses below −0.25R and the top-5 column is what shows it.** At −0.2R and −0.15R the
rule goes NEGATIVE once its five best trades are removed — the stop is now inside the noise of
the entry bar and the winners are the only thing holding it up. **−0.25R is one step from the
cliff; −0.3R is the shallowest value with room under it.**

⚠ **The defaults are UNCHANGED and `soft_stop_r` ships as `None`.** Every number elsewhere in this
file was measured on the structural stop, and moving the default would restate all of them to buy
a difference the jitter cannot resolve. It is Aaron's call, and the evidence for making it is the
loss-size column above, not the balance.

---

## 🔴 The stop on the LOSING TRADE'S ENTRY — Aaron's idea, and it loses 14R

**MEASURED 2026-08-19.** The reasoning was: the primary's entry is much nearer than the break
leg, so the same 25% of risk buys a bigger position, +1R arrives sooner, breakeven arrives sooner,
and a ratchet takes it from there. **Every step of that mechanism is CORRECT and the result is
still much worse.** `stop_mode="loss_entry"` exists so this stays re-runnable rather than
remembered.

`python backtest/tools/recovery_report.py --start 2018-09-14 --end 2026-08-14 --stops`

| stop | took | refused | median stop | cost/R | net R | win | maxDD | vs dial |
|---|---|---|---|---|---|---|---|---|
| break leg (shipped) | 62 | 0 | **$38.18** | 0.4% | **+16.2R** | 58% | 48.3% | 1.53x |
| the losing trade's entry | 57 | 5 | **$16.05** | 0.9% | **+1.8R** | 49% | 51.3% | 0.78x |

**The mechanism did exactly what it promised.** The stop is **2.4x tighter**, so the same risk
buys 2.4x the position, and the median trade now resolves in **43 bars against 294** — eleven
hours instead of three days. **Cost is not the objection either**: at $16 the round trip is still
only 0.9% of R.

🔴 **What broke it is WHERE that stop sits.** The primary's entry is a price the market has just
been trading around — it went there, filled an order, and reversed through it. It is the single
most likely level to be revisited. So the recovery rests its stop in the middle of fresh
congestion, and the tell is in the excursion rather than the P&L: **median MFE falls 1.01R →
0.89R**. Shrinking the stop 2.4x should have made every dollar of travel worth 2.4x more R; it
made it worth LESS, which can only mean the trades are dying before the move they were entered
for. `locked` falls 56% → 49% for the same reason.

⚠ **5 of 62 are REFUSED outright** — by the time the CHoCH prints, price is back on the wrong side
of the primary's entry and a stop there would be above a long's fill. Refusing is correct (rule
17) and `refused()` counts them separately from `pending()`, because *the signal never came* and
*the stop was unusable* say opposite things about a rule.

⚠ **It does not combine with the soft cut either** — `loss_entry` + a −0.3R cut is **−1.7R**,
the only negative variant measured on this rule.

### The percent ratchet loses to the swing trail on BOTH stops

| trail | on the break leg | on the loss entry |
|---|---|---|
| confirmed swings (shipped) | **+16.2R** | +1.8R |
| 0.05% of price | +8.5R | +4.3R |
| 0.1% | +8.3R | **+4.7R** |
| 0.5% | +9.7R | +4.6R |
| 1% | +9.2R | +5.3R |

⚠ **Read the flatness, not the ranking.** A 20x range of step sizes returns the same answer on
each stop, and the reason is the `mpc_bleg` trap from both ends: at 1% the step is **$40 against a
$38 median stop**, so the ratchet cannot bind until the trade is already 2R out; at 0.05% it binds
constantly and hands back the runners. **A percent of PRICE is not a percent of RISK, and this
rule's whole result lives in the trades that run.** A swing level is where the market says the
move is still intact; a fixed percentage is where arithmetic says so.

---

## The stop search — six placements, and the one that beat the default was five trades

**MEASURED 2026-08-19, after Aaron pointed out that the previous pass tested only the ideas he
and I had already named and called that a search.** `recovery_report.py --search` is the actual
sweep: every stop the engines can name, scored against a structure-BLIND ATR control.

| stop | median stop | cost/R | net R | maxDD | net less its best 5 |
|---|---|---|---|---|---|
| **break leg (shipped)** | $37.91 | 0.4% | **+16.2R** | 48.3% | **+2.3R** |
| the CHoCH bar's own extreme + 0.1 ATR | $5.18 | 2.6% | **+24.4R** | 46.3% | 🔴 **−7.4R** |
| break leg x 0.25 | $9.55 | 1.5% | +2.7R | 48.8% | |
| break leg x 0.5 | $19.09 | 0.7% | −3.1R | 51.2% | |
| the last confirmed swing | $5.16 | 2.7% | −12.3R | 58.6% | |
| the losing trade's entry | $16.05 | 0.9% | +1.8R | 51.3% | |
| 1.5 / 2 / 3 x ATR(14) — **control** | $4.71 / $6.29 / $9.43 | 3.0% / 2.2% / 1.5% | +3.3R / +2.3R / −2.9R | | |

🔴 **The signal-bar stop looked like the answer and is not. +24.4R with a LOWER drawdown on a
stop 7x tighter — and deleting its five best trades takes it to −7.4R, where the shipped stop
survives the same deletion at +2.3R.** Its median hold is **4 bars**, so it is not a better
version of this rule; it is a different, hour-long rule that happened to catch five big moves in
a record where gold ran. ⚠ **Its pad is a cliff too** — 0 ATR gives −2.2R and 1.0 ATR gives −5.4R,
either side of a wide flat middle. **Two independent robustness checks failing on the row with the
best headline is the whole reason to run them before reporting the headline.**

✅ **The ATR control earned its place**: at a matched $5–6 stop it scores +3.3R against the signal
bar's +24.4R, which is what says the structure is doing something rather than the tightness. It
also says nothing else here is — every other structural placement loses to it or ties.

⚠ **`swing` is the worst row on the board (−12.3R at a 58.6% drawdown)** at almost exactly the
same stop SIZE as `signal_bar`. Size is not the variable. **Where the level came from is.**

## 🔴 The +1R exit is not what costs the runners — and the money after it is a RE-ENTRY, not a trail

Aaron's second objection was that locking at +1R gives up the continuation. **He is right that the
move is there and wrong about how to collect it, and the two facts sit in the same table.**

Of the **35 recoveries that reached +1R**:

| | |
|---|---|
| median booked | **+1.00R** |
| median MFE **while the trade was open** | **+1.06R** |
| ever saw +2R while open | **3 of 35** |
| ever saw +3R while open | 2 of 35 |
| median extra R price offered **after the exit** (30d) | **+2.33R** |
| offered more than 1R after the exit | **22 of 35** |
| offered more than 3R after the exit | 15 of 35 |

**Price ticks to +1R, takes the stop, and THEN runs.** So a wider trail cannot reach it: only 3
of 35 trades were ever above +2R *while still open*, and every attempt to hold for them pays 32
trades' worth of given-back R to catch 3. That is exactly what the measured alternatives do —
lock to +0.5R **+7.9R**, lock to breakeven **+9.5R**, a 1–4 ATR chandelier **+8.3R to +10.4R**,
banking 25/50/75% at +1R and running the rest to breakeven **+5.6R to +6.4R**, all against
**+16.2R**.

🔴 **The lead worth writing down: +2.33R median, on 22 of 35 trades, arriving AFTER the position
closed is a RE-ENTRY signal, not a trailing-stop problem.** Nothing in this rule takes a second
trade on the same premise. That is a new rule with its own spec and its own arming condition, and
it is the only unexplored direction the numbers actually point at.

## Why this is a package and not a flag on `mpc_sos_fade`

The trigger is "a primary trade lost", which every strategy in this repo can state. Wiring it to
one strategy's concrete `Trade` class would make the second consumer a rewrite, so the engine is
defined against the `LossEvent` **Protocol** (`dir`, `exit_index`, `r`).
`mpc_sos_fade.execution.Trade` satisfies it unchanged.

⚠ **`scaled_r`, never `r`.** A recovery trade is taken at a FRACTION of normal size, so `r` (its
outcome in its own risk units) and `scaled_r` (`r * risk_fraction`, what the account sees) are
different units. A journal adds up `scaled_r`. Booking `r` overstates the contribution 4x at the
default size — the same class of error as handing MT5 ounces where it wanted lots.

---

## Why both directions

**`both_directions=False` is the one FITTED choice available here, and it is off by default.**
"Longs only" was picked after seeing that longs beat shorts on this exact record.

The earlier finding that counter-shorts lose −11.8R was measured with a **10R target**, and that
was the wrong test: gold drifts up over this record, so a counter-short almost never travels ten
times its risk. Re-run with the lock-and-trail exit, counter-shorts are **−2.9R over 25 trades**
with no era pattern (−2.6R first half, −0.4R second) — noise around zero, not a losing edge. And
both directions together score **1.49x** against the risk dial where longs alone score **1.48x**.

The shorts are free, they lower the drawdown slightly (the two directions do not lose at the same
moments), and taking them removes the only fitted element in the rule. Take both.

---

## Why the exit is the whole thing

Four exits were measured on the same 62 trades, net of costs:

| Exit | Net | Win | Median hold | Swap |
|---|---|---|---|---|
| 10R target, unmanaged | +13.3R | 35% | 17d | −19.7R |
| Breakeven at +1R, then trail | +9.5R | 54% | 7d | −6.1R |
| **Lock +1R at +1R, then trail** | **+18.9R** | **70%** | **4d** | **−4.7R** |
| Trail from the start | +2.4R | 49% | 5d | −5.6R |

🔴 **The 10R version only worked in the 2022–26 gold run and its whole result was five trades** —
removing its best five sent it to −0.7R, and its first half lost 7.8R. Locking at +1R made
**+9.2R in the first half and +9.6R in the second**, and still nets +6.6R with its best five
deleted. The difference is what the trade has to ASK of the market: 10R needs a 10–24% gold move,
+1R needs price to travel one R — and 97% of losses do that within a month.

🔴 **Swap is why the time stop exists.** Gold costs **$79.60 per lot per night** to hold long on
`puprime_ecn` (triple on Wednesday) and pays **+$30.25** to hold short. The 10R version left
trades open for 130+ days and paid **−8.66R** of swap on one that made +1.25R — 77% of its gross
went to costs. With the lock-and-trail exit nothing reaches the cap, and 30 / 60 / 90 days all
return the identical number.

⚠ **Liquidity levels were tested as targets and they lose.** Because the structural stop is ~4x a
normal stop, the nearest PDH/PDL/session/swing level sits a median **0.13R** from entry and 91%
are inside a single R — banking there risks a full R to make a fraction of one. Best level-based
version made +6.4R against +49.3R for letting it run.

---

## Tests

`command-center/backend/.venv/bin/python -m pytest strategies/python/loss_recovery/tests/ -q`
→ **32 passed.**

🔴 **Every one was watched RED by a named mutation, and the harness earned its keep: 5 of the
first 15 were VACUOUS.** They passed against their own bugs. What the mutation pass found, kept
here because each is a general trap:

| Vacuous because | Fix |
|---|---|
| `if t.locked:` never entered — the counter-LONG fixture has no trade that reaches +1R | run the counter-SHORT set, and `assert locked` first |
| deleting the lock made the trade book MORE (+1.457 vs +1.000) — the swing trail rescued it | switch trailing OFF so the assertion is about the lock |
| `r >= -1` still holds when a mutation books +3R | assert the exit reason is in the closed set, and `r <= mfe` |
| `mfe >= r` is trivially true when every trade books exactly −1R | assert `mfe > 0` — the mutation leaves unarmed trades at 0.0 |
| re-running the SAME frame cannot fail (StructureEngine tolerates a re-feed), and real-then-FLAT cannot either (a second guard refuses it) | two DIFFERENT real slices |

⚠ **One assertion could not be made red at all and was replaced rather than kept.** Reordering
the stop check against the arm block returns **byte-identical** results over 2,400 real bars,
because no bar there both arms and stops. It is now a direct two-bar test of `_manage` where the
ordering is observable. **A test that cannot go red is decoration, and the honest move is to say
so in the docstring or delete it.**

✅ **The five tests added 2026-08-19 for the tighter exits were watched RED the same way, and the pass caught a FALSE GREEN in its own harness**: the first mutation was written against a multi-line `if/else` that `ruff format` had already collapsed onto one line, so the string replacement silently matched nothing and the suite stayed green. ⚠ **A mutation that does not apply is indistinguishable from a test that survived it** — assert the replacement landed before believing the red.

🔴 **The 2026-08-19 stop-search pass produced another VACUOUS test and it is the same shape as the original five.** `swing`'s refusal branch was tested by running the mode over the real fixture — where every signal HAS a usable swing, so the branch was never reached and a mutation making it borrow the structural stop passed. **A refusal is only testable by constructing the state that triggers it**; it is now a direct `_stop_for` call with an empty swing book.

⚠ **The price fixture is 2,400 REAL XAUUSD M15 bars** (`tests/fixture_xauusd_m15.csv`, committed
so the tests need no bar cache). Hand-built ramps and sawtooths were tried first and the canonical
structure engine emitted **zero** events on every one — pivot seeding plus 3-candle pullback
confirmation needs price action a straight line does not contain, and a fixture the engine cannot
read would have let every assertion pass on an empty list.

---

## What would have to happen before this trades

1. A Pine implementation and a green parity gate. **It cannot be bolted onto
   `mpc_strategy.pine`** — that file assumes one position at a time (`closedR` at line 3869,
   `openRiskUsd`, `netAtEntry` and 13 separate `strategy.position_size == 0` arming gates), so a
   concurrent recovery position makes the primary mis-grade its own trades. It needs a fork, the
   same shape as `mpc_b_leg_strategy.pine`.
2. `/live-safety`, in full.
3. **The account-level risk cap.** A recovery trade can open while a primary is still on — that
   is the point of it — and the live allocator that would refuse the second one does not exist
   (root CLAUDE.md → *Risk is budgeted per ACCOUNT*; `docs/LIVE_TRADING_PIPELINE.md` → G10).
4. Re-run `backtest/tools/overlap_audit.py`. This adds a third source of concurrent positions on
   one instrument off one structure stream, and that audit's conclusion is about today's config.

## Key paths

| | |
|---|---|
| `config.py` | every knob, with the measured default and why |
| `--exits` / `--soft-curve` | the exit grid and the soft-stop curve on `recovery_report.py` |
| `types.py` | `LossEvent` protocol, `RecoveryTrade`, `ArmedSignal` |
| `engine.py` | the state machine; consumes `engines/market_structure` public events only |
| `tests/` | 32 tests + the real-bar fixture |
| `backtest/tools/recovery_report.py` | the runner that produced every number above |

---

## It is drivable from the Command Center (2026-08-20)

Until now this package could only be run from `backtest/tools/recovery_report.py`, a terminal tool
— there was no config field, so the lab's form (built from `dataclasses.fields` of a strategy's
config) had nothing to render, and `build_results` reads `strategy.execution.trades`, which never
contained a recovery row.

`mpc_sos_fade` now carries seven `exec_recovery_*` inputs and a `recovery.py` adapter that maps
them onto `RecoveryConfig`, runs this engine over that bot's finished losses, and appends the
result as `Trade(kind="recovery")`. Everything downstream — KPIs, equity curve, trades table,
chart — then works with no change. **Defaults are unchanged and `exec_recovery` is OFF**; nothing
measured in this file moved.

⚠ **The wiring's facts live in `strategies/python/mpc_sos_fade/CLAUDE.md`**, not here — including
the one that matters (turning it on cannot move an A+ trade) and the one approximation it buys
(the two share a balance in one direction only). This file stays the owner of the RULE.

**A resolved trade now reports how far it went AGAINST as well as how far it ran** — `max_adverse_r`
beside `max_favourable_r`, both non-negative magnitudes in the trade's own R, both reporting-only.
Added 2026-08-20 because the lab's price chart draws a trade's deepest point and had nothing to draw
it from.

🔴 **`max_adverse_r` is CAPPED at the exit on the closing bar, and that cap is the whole care in
it.** The stop check runs before the range is read, so the bar that stops a trade out can trade far
past the stop — but the position was already gone at the stop. Measuring the full bar would report a
drawdown the trade never lived through, and a chart would then draw its deepest point BEYOND its own
stop, which is not a thing that can happen. ⚠ **It is only testable on a SYNTHETIC frame**: every
recovery in the real fixture exits locked and in profit, so the reordered walk returns identical
numbers there. A wiring-level version of the test was written, watched still-green, and deleted —
same trap as the five vacuous tests above, found the same way.
