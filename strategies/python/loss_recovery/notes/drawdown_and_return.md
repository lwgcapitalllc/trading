# Notes — Drawdown and compounding — measured effects

The measured evidence that this leg does not reduce drawdown, only adds return, plus the compounding and account-level-budget corrections that qualify the 1.53x headline. Moved VERBATIM out of `strategies/python/loss_recovery/CLAUDE.md` on 2026-09-13 so it loads only when
needed; nothing was reworded or dropped. **New detail on this topic goes HERE**, and the
CLAUDE.md gets at most one index line.

---

## MEASURED

`python backtest/tools/recovery_report.py --start 2018-09-14 --end 2026-08-14 --sweep`

XAUUSD M15, 186,910 bars, `sos_fade` at shipped defaults with `exec_secondary=False`,
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

| window | costs | SOS Fade alone | + recovery | change |
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
| SOS Fade alone, as the lab runs it | 4,921x | 45.6% |
| **+ recovery, as the lab runs it** | **5,107x (+3.8%)** | 37.8% |
| SOS Fade alone, one shared compounding balance | 6,026x | 45.6% |
| **+ recovery, one shared compounding balance** | **9,636x (+59.9%)** | 42.2% |

**+3.8% against +59.9% for the identical trades.** The recovery leg is worth **+5.04R
account-weighted** either way; what differs is whether that R gets to COMPOUND.

🔴 **The cause is a deliberate design choice in the wiring, not a bug** —
`sos_fade/recovery.py` sizes the recovery off the running balance but never lets SOS Fade size off
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
holds risk for a median of ~4 days, and **23 of this run's 160 SOS Fade entries opened while one was
already holding**. SOS Fade risks the full 10% and the cap IS 10%, so every one of those 23 competes.

| | multiple | maxDD | vs SOS Fade alone |
|---|---|---|---|
| SOS Fade alone, one balance | 4,921x | 45.6% | — |
| + recovery, every entry granted in full | 7,125x | 42.1% | **+44.8%** |
| + recovery, SOS Fade shrunk to the room left | 4,191x | 39.9% | **−14.8%** |
| + recovery, SOS Fade refused outright | 116x | 43.3% | −97.6% |

🔴 **The plausible range spans +45% to −15%, and which end you land on is decided entirely by an
allocator that DOES NOT EXIST on the live side.** MEASURED on this run: an SOS Fade trade averages
**+0.882R** and a recovery averages **+0.095R account-weighted** — **9.3x** — so giving budget to
the second at the first's expense is a bad swap the moment the cap binds. **"How would
this have behaved?" has no answer yet, and the width of that range IS the finding.**

⚠ **All three rows are RE-PRICES, not replays, and this repo has been bitten by exactly that** — an
entry-side filter estimated at +1.84R replayed at −1.84R, because shrinking or refusing an entry
frees the position slot and a freed slot admits a setup the book does not contain. The −97.6% row
in particular is an artifact of deleting compounding winners, not a forecast. Read the three as a
BRACKET on how much the contention matters, never as results.

⚠ **The middle row is PESSIMISTIC on its own terms**: reservations fall to zero at breakeven, SOS Fade
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

**MEASURED, 186,910 M15 bars 2018-09-14 → 2026-08-14, `puprime_ecn`, SOS Fade 10%, recovery 25% of that:**

| account cap | SOS Fade alone | + recovery leg | verdict |
|---|---|---|---|
| **10%** (SOS Fade alone already fills it) | $13,199,534 · 50.2% | **$9,251,114 · 50.4%** | **−29.9%** |
| **12.5%** (room made for it) | $13,199,534 · 50.2% | **$17,074,731 · 50.4%** | **+29.4%** |

🔴 **The recovery leg is not the variable — HEADROOM is.** SOS Fade risks the full 10% and the cap is
10%, so the two legs at full size want 12.5% of a 10% budget: **every overlap shrinks SOS Fade by
construction, and 25 of its 181 entries were shrunk.** An SOS Fade trade averages 9.3x a recovery trade's
account-weighted R, so trading one for the other is a bad swap. Give the recovery its own 2.5% on
top and the same trades add +29.4%. **The question is not "is the recovery worth taking" — it is
"is it worth 2.5% of account risk that SOS Fade is not already using".**

**The concurrency rule is SHARE, and it is stated in the run's own output.** `PortfolioAccount`
grants `min(desired, room)`; that is the canonical account in this repo and a second allocator is
forbidden. ⚠ **`--on-contention refuse` REFUSES TO RUN rather than fake it**: the account carries
ONE entry floor for every leg while these legs risk different amounts, so any floor that makes SOS Fade
all-or-nothing also bans every 2.5% recovery entry outright — measured, 64 refusals and 0 trades,
identical at a 10% and a 12.5% cap. A refusal rule needs a PER-LEG floor on the shared account.

⚠ **Peak open risk 10.9% against a 10% cap, and it is not a hole.** The cap binds AT FILL against
the balance at that moment; the reservation is then a fixed dollar figure while the balance keeps
moving, so a later loss shrinks the denominator under a grant already made. Nothing was ever
granted over the cap.

⚠ **SOS Fade's R moved −0.10R (127.11 → 127.01) on the shrink path and is UNEXPLAINED.** R is normalised
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
against a fixed SOS Fade. 186,910 M15 bars, 2018-09-14 → 2026-08-14, `puprime_ecn`, rule SHARE. Every
`SOS Fade alone` row is that same run's own solo control, so no two rows come from different code paths.

| plan | final balance | maxDD |
|---|---|---|
| SOS Fade 6% alone | $1,720,547 | 32.4% |
| SOS Fade 7% alone | $3,088,653 | 37.2% |
| SOS Fade 6% + recovery 4% | $2,589,198 | 38.4% |
| SOS Fade 7% + recovery 3% | $4,223,442 | 40.5% |
| SOS Fade 8% alone | $5,256,114 | 41.7% |
| **SOS Fade 8% + recovery 2%** | **$6,506,262** | **42.5%** |
| SOS Fade 9% + recovery 1% | $9,502,543 | 45.8% |
| SOS Fade 9% alone | $8,518,854 | 46.1% |
| SOS Fade 10% alone | $13,199,534 | 50.2% |

**Two pairs DOMINATE outright — more money AND less drawdown — so they read without interpolation,
without a risk-adjusted metric, and without arguing about which axis matters:**

- **SOS Fade 9% + recovery 1% beats SOS Fade 9% alone**: $9.50M vs $8.52M, at 45.8% vs 46.1%.
- **SOS Fade 7% alone beats SOS Fade 6% + recovery 4%**: $3.09M vs $2.59M, at 37.2% vs 38.4%.

🔴 **So the recovery earns its place as a SMALL slice and destroys value as a large one, and the
turn is between 2% and 3%.** A quarter-size recovery under SOS Fade at 8% is on the good side of that
turn; **1% under SOS Fade at 9% is better still.**

🔴 **The headline is that the recovery is not the big lever, and this table is how you see it.**
Under a fixed 10% ceiling SOS Fade's own risk rate moves the result far harder than anything the recovery
does: taking SOS Fade ALONE from 8% to 10% goes $5,256,114 → $13,199,534, while bolting a whole 2%
recovery leg onto the 8% version reaches $6,506,262. **The recovery buys EFFICIENCY at a given
drawdown; it cannot buy HEADROOM.** The most money available under a hard 10% ceiling is SOS Fade alone
at 10% — which is what the live bot already does — so every split here is a decision to spend money
on drawdown, not a decision about whether the recovery rule works.

⚠ **Do NOT read the per-cell "+X% against its own control" figure ACROSS cells.** It climbs
monotonically as the plan gets worse — **+11.5%, +23.8%, +36.7%, +50.5%** at 9/1, 8/2, 7/3, 6/4 —
purely because the control it divides by is shrinking. **The best-looking uplift in the sweep sits
on the worst plan in it.** Compare the absolute column, or compare dominance pairs.

⚠ **The whole table is inside the noise band in R, and that caveat outranks every row above it.**
Put the legs in comparable units (R × that leg's risk rate, i.e. percent of balance): the recovery
contributes **14.8 / 29.5 / 44.3 / 59.1** at 9/1, 8/2, 7/3, 6/4, against an SOS Fade jitter floor of
15.06R × the SOS Fade rate = **136 / 120 / 105 / 90**. That is **0.11 to 0.66 of ONE standard deviation
of SOS Fade's own run-to-run noise, in every cell.** The efficiency gain is real arithmetic on this
history; its SIGN is not established, and 60 recovery trades over 7.9 years will not establish it
soon.

⚠ **The 3% and 4% cells trip the tool's own headroom warning (both legs at full size want 10% of a
10% budget) and still report 0 shrunk, 0 refused.** That is not the warning being wrong — it is
reservations falling to zero at breakeven, which SOS Fade reaches in a median of one bar. **A warning
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
