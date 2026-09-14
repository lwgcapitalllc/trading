# Notes — Stop and exit search

Every stop placement and exit variant that was tried against the shipped structural-stop, lock-at-+1R design, and why each alternative loses. Moved VERBATIM out of `strategies/python/loss_recovery/CLAUDE.md` on 2026-09-13 so it loads only when
needed; nothing was reworded or dropped. **New detail on this topic goes HERE**, and the
CLAUDE.md gets at most one index line.

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
each stop, and the reason is the `b_leg` trap from both ends: at 1% the step is **$40 against a
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
