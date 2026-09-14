# Notes — The market and news cuts, and the cached-history study

The transitioning-market and news filters TradingView cannot make, why one shipped on and one shipped off, what each was measured to be worth, and the earlier cached-history comparison against the study. Moved VERBATIM out of `strategies/python/extreme_leg/CLAUDE.md` on 2026-09-13 so it loads only when
needed; nothing was reworded or dropped. **New detail on this topic goes HERE**, and the
CLAUDE.md gets at most one index line.

---

## The two cuts TradingView cannot make (2026-09-02, Aaron's call)

🔴 **THE MARKET CUT SHIPS ON; THE NEWS CUT SHIPS OFF (Aaron's call, 2026-09-02).** Both were
built OFF and both were measured before either was switched — the table below is why exactly one of
them survived. **So the shipped strategy is no longer the thing the parity gate compares**, and that
sentence is now printed by the gate itself rather than left here for someone to remember.

They read `engines/regime/` and `engines/news/`, neither of which has a Pine source — by
construction, not by omission — so no `cfg_*` column can carry them and this gate can never check
them. That is the thing `config.py`'s opening rule forbids, and it is allowed only because the hole
is closed at the other end.

🔴 **THE GATE USED TO REFUSE TO RUN WITH EITHER CUT ON, AND THAT DESIGN DIED IN THE FIRST
MINUTE IT WAS EVER TRUE.** It was written while both cuts were off, so it had never once run in the
state it existed for; switching the market cut on walled all 14 of the gate's own tests AND made
parity of the SHARED logic unprovable as well. **A guard that blocks the work gets bypassed, and
this one blocked the only check the strategy has.** ✅ **It now forces both cuts OFF for the
comparison** — which is not a climbdown: that IS the configuration every export is taken at, so it
is the only correct one — **and says what it could not check, on the verdict line itself:**

```
✓ PARITY OF THE SHARED LOGIC — the Python made the same decisions as the Pine on every
  compared bar, but this is NOT a check of the shipped strategy: the transitioning-market cut
  is switched ON in config.py, the chart cannot make it, and this run was necessarily measured
  with it OFF. What ships takes FEWER trades than what was just compared.
```

⚠ **A green run with a qualified verdict and a green run with a plain one are DIFFERENT CLAIMS,
and holding them apart is the whole point.** `test_gate_gives_an_UNQUALIFIED_verdict_when_nothing_pine_less_ships_on`
goes red if the qualifier ever prints unconditionally, because a warning on every run is a warning
nobody reads.

⚠ **The reason a filtered Python must never be compared against an unfiltered Pine is unchanged:**
it reports a disagreement per refused setup, on a real column at a real bar, and sends the reader
into the ladder hunting a porting bug that is not there. **Forcing the cuts off is what prevents
that. The refusal was never the part doing the work** — it only decided who got punished for it.

⚠ **They sit LAST in the refusal ladder.** With both off this side's decision stream is
bit-identical to the chart's; with one on, the divergence lands on its own code (8 or 9) rather
than changing which of the Pine's codes a bar records. `test_the_new_cuts_sit_AFTER_every_refusal_the_pine_can_also_make`
pins it and the whole design rests on it.

⚠ **The market cut's history floor is the classifier's own (2026-09-10).** It answers *unknown* without asking while either frame is shorter than `engines/regime/`'s minimum — that only skips building two frames the classifier would refuse anyway — and it typed that minimum as 34. It now reads it, and `test_the_history_floor_is_the_classifiers_own` goes red if a typed copy returns, if the two minimums are swapped, or if the kept window drops below them (all three watched RED). Nothing moves today: the classifier's minimum is still 34.

🔴 **One IS on, so the bot and the chart are now different strategies.** The chart is no longer
a picture of what the bot does — it takes 19 trades the bot refuses. That is the price of the row
below, not a caveat on it, and anyone reading a TradingView result for this strategy is reading the
unfiltered version.

### What they are worth — MEASURED 2026-09-02, 470,995 PU Prime `XAUUSD.p` M5 bars, 2020-01-01 → 2026-08-23

| | trades | R | worst losing run | asked | refused |
|---|---|---|---|---|---|
| neither cut (what the chart does) | 132 | +57.10R | 8.13R | — | — |
| **← SHIPPED: skip a transitioning market** | **113** | **+58.53R** | **6.00R** | 550 | 40 |
| + skip around news | 121 | +51.45R | 8.87R | 550 | 79 |
| both | 104 | +53.18R | 5.99R | — | — |

✅ **The market cut is the one that pays: the worst run drops 26% and the money goes UP.** Cutting
risk without paying for it is rare and is why this was worth building.
🔴 **The news cut is worse on BOTH counts and stays off** — it costs 5.65R and makes the worst run
*deeper*, which is the opposite of what a news filter is for. ⚠ It also could not answer on **51 of
550** setups (the calendar is git-ignored and per-machine, and does not cover ~9% of this window),
so that verdict rests on the other 91%. Re-measure after topping the cache up before treating it as
settled.

⚠ **A refusal is not a lost trade.** The news cut refused 79 setups and cost only 11 trades: a
setup refused at one bar can re-arm later and still be taken. Do not read the two counts as if they
were the same quantity.

🔴 **THE NUMBER THAT JUSTIFIED THE MARKET CUT CANNOT BE REPRODUCED FROM ANYTHING IN THIS REPO.**
`strategies/tradingview/docs/extreme_leg_strategy.md` quotes 24 trades at +0.060R each and a
worst run of 7.9R → 5.9R. **No file in this repository's entire history reads the transitioning
label for this strategy** — searched across `backtest/tools/` and every commit. So the figure has
no committed tooling behind it and the table above was measured from scratch rather than inherited.
✅ **The two agree in direction and roughly in size** (worst run down to ~6R), which corroborates
the original rather than contradicting it — but the windows and brokers differ and they are not the
same measurement. **Quote the table above, not that line.**

### What each cut refuses to guess

🔴 **"Cannot ask" and "no" are different answers and are kept different.** Each returns REFUSE,
ALLOW or UNKNOWN, never a bool. An UNKNOWN **allows** the trade — a filter that refused whenever it
could not see would silently become a different strategy on any day its data was thin — but it is
counted, and the count is readable on the strategy.

🔴 **EACH CUT ALSO COUNTS HOW OFTEN IT WAS ASKED, AND THAT FIELD EXISTS BECAUSE ITS ABSENCE ALREADY
FOOLED THIS SESSION.** Without it, a cut that was never wired up and a cut asked 550 times that
allowed every one print the same zero — the run comes back identical to the baseline and reads as
*nothing to refuse here*. That is exactly what the first run of `filters.py` produced, and the
numbers looked perfectly reasonable. **`asked` says the thing is connected; `refused` says it did
something.**

⚠ **Which two frames the market cut reads is a CHOICE**: the strategy's own 5-minute bars and the
15-minute bars it already aggregates. Nothing else was available without giving the strategy a
second data source, and a strategy that quietly loads its own bars is one whose backtest and live
runs can differ.

⚠ **Asked only when a setup exists, not per bar.** 550 questions over 6.6 years rather than 470,995;
the classifier walks its whole frame on every call.

✅ **THE CLASH AUDIT WAS RE-RUN THE MOMENT THE CUT WENT ON (2026-09-02), AND THE ANSWER HELD.**
Switching it on drops 19 trades, so the previous day's figures stopped describing this bot within a
day of being written. Current figures live in root `CLAUDE.md` → *The extreme-leg bot does not
clash with SOS Fade either* — re-measured 2026-09-10: 1,049 shared bars, ZERO same-side, and ONE
same-direction entry within four hours where there had been none.
⚠ **It does not retire the account-level allocator**: peak concurrent positions is still 2.

🔴 **THE RULE THIS OBEYS IS THE ONE THIS REPO KEEPS RE-LEARNING: a cross-cutting measurement is
re-run by whoever MOVES the inputs, not by whoever wrote the conclusion.** The B-LEG audit went
stale twice exactly that way. Anything that changes what this bot trades — a cut, a threshold, a
ladder change — invalidates the root `CLAUDE.md` clash paragraph, and the person making the change
is the only one who knows it happened.

---

## What it does over the cached history — and what that is and is not

MEASURED 2026-09-01, 562,071 Vantage XAUUSD M5 bars (2018-09-14 → 2026-08-23), shipped defaults,
$10,000, 1% a trade:

```
178 trades   +97.4R   hit 50.6%   worst losing run 7.9R   every year positive
```

The study's tuned equivalent over the same window was **169 trades / +84.0R / worst run 7.9R**, so
the two land in the same place rather than in different places — which is the only claim this
comparison supports. ⚠ **It is NOT a validated result** (no gate), it predates the session fix
above, and it is not a reason to skip stage 4.
