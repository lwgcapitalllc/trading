# `mpc_extreme_leg_strategy.pine` — the run INTO the shift of structure

**Status: COMPILES AND RUNS.** Its first run blew the account and the cause is fixed — see the
defect record below, because the shape it broke in applies to every strategy here. ⚠ **Every number
in this doc still comes from `backtest/tools/pre_sos_leg.py`, not from this file.** The strategy now
takes trades and protects them; nobody has yet checked whether what it books matches the study, and
until somebody does, the table below describes the study rather than the file.

**Run it on a 5-minute chart.** The 15-minute half is aggregated in code, so the chart timeframe
is not a preference — it is the frame the trigger is measured on.

---

## What it trades, and how it differs from A+

The live A+ bot waits for the shift of structure and then fades the retracement into it. This
takes the move that CREATES the shift: from the extreme up to the swing whose break IS the shift.
Same structure stream, different part of the leg — the carve-up the root `CLAUDE.md` describes
under *Trading Philosophy*.

The rule, in full:

1. A liquidity level on the 15-minute chart gets swept — session, previous day, previous week, or
   the previous 4-hour candle.
2. Within 3 hours, the **5-minute** chart puts in its own change of character the other way.
3. The 15-minute trend still points against it, so the swing being aimed at is a change of
   character rather than a continuation.
4. That swing is at least 2 stops away, the stop sitting beyond the extreme of the last 2 hours.

Entry at the 5-minute close. Stop beyond the extreme, plus a fifth of the average range of air.
**Take profit HALF the way to the swing** — the swing is what the setup is measured against, not
where the order rests. The stop does not move.

---

## 🔴 Why the file embeds the structure engine TWICE

The 15-minute half supplies the trend and the target; the 5-minute half supplies the trigger. Both
are the same external state machine on different bars.

**The second instance is DERIVED, never retyped** —
`indicators/strategies/tools/derive_htf_structure.py` regenerates it from the block in
`mpc_h4_sweep_strategy.pine`, renaming the type and method and swapping the four bar globals for
passed-in values. A hand-transcribed copy is a second implementation that drifts the first time
somebody patches one and not the other, which this repo has already had happen across eleven
forked Pine files. **A divergence is now a diff rather than a discovery.** The script asserts the
exact substitution counts and refuses to write on any other number.

### 🔴 What the derivation must NOT swap — the two-clock bug (2026-08-25)

The first generator swapped the bar index along with the four bar values, and that produced an
engine running on two clocks at once: every swing LOCATION became a count of 15-minute bars while
every loop bound and lookback stayed a count of chart bars. **The post-break rescan then searched a
window a third as long as it meant to, and the bootstrap scan could reach past the start of
history. Neither half errors, goes red, or shows on a chart** — a swing simply anchors somewhere
it does not belong.

**The rule that resolves it, and it applies to any aggregated-bar engine here: the extreme of a
span of aggregated bars is the extreme of the chart bars under it.** A 15-minute bar's low IS the
lowest of its three 5-minute lows, so *the lowest low between these two points* returns the same
price whichever series you scan. So the scans, the loop bounds and every stored location stay on
the **chart's** clock and stay consistent with each other, and only the per-bar DECISIONS — is this
bar inside the last one, did this close break the swing — take the aggregated values.

| swapped for the 15-minute values | left on the chart's own series |
|---|---|
| bare `open` / `high` / `low` / `close` | `bar_index` and everything computed from it |
| the pivot's own bar, passed in | an indexed read — `low[i]`, `high[i]` |

⚠ **One consequence to know rather than discover: the rescan's 1490-bar runaway guard is now 1490
CHART bars, about 496 higher-timeframe ones.** It is a guard against a runaway loop, not a rule,
and no swing here spans that far.

⚠ **It surfaced as a single compile error on the first paste** (`CE10272`, an undeclared
identifier) — two helper methods got the rename without getting the parameter. **That was the
harmless half.** The compile error stopped the file; the two-clock defect underneath compiled
perfectly. `indicators/tools/check_scope.py` now catches the narrow half mechanically and cannot
see the other one at all.

⚠ **Regenerate after ANY change to the source block**, including a cross-cutting structure fix:

```
python3 indicators/strategies/tools/derive_htf_structure.py
python3 indicators/strategies/tools/build_extreme_leg.py
```

⚠ **`request.security` was considered and rejected for the 15-minute half.** A state machine has
to be FED; a security call returns a value. Aggregating three closed 5-minute bars is the only way
it sees the same bars a 15-minute chart would, in the same order, with no lookahead. The levels
still use `request.security`, where `[1]` paired with `lookahead_on` is the non-repainting idiom
for a previous completed period — either alone repaints.

⚠ **`ta.pivothigh` cannot see the aggregate**, because the aggregate is not a series. The 15-minute
pivots are the same rule applied by hand over a rolling window of completed 15-minute bars.

---

## ⚠ It breaks the fixed Section 2, and that is a decision for Aaron

The house contract says every strategy carries the same four market-structure toggles. This file
ships **two** — external structure and swing labels. There is no internal engine here, so the
other two would be controls that look like they do something, which is the exact hazard the
contract's own note names.

**Porting the internal engine would be a THIRD copy of a state machine in one file, ~450 lines,
purely to draw with** — in a file that already carries two and has never been compiled. The
compile-token ceiling is the live risk. Left as an open decision rather than done silently: if the
file compiles with room to spare, the internal engine should go in and the section becomes
standard.

---

## 🔴 The first run blew the account — the bracket was cleared on the bar it was set (2026-08-25)

**Symptom:** pasted on a 5-minute chart, the equity curve went to zero.

**Cause, and it is one line.** Orders here are processed on the bar's close, which happens *after*
the script has finished running for that bar — so on the bar an entry is placed, the book still
reads flat everywhere below it. The block that cleared the stop and the target when flat therefore
fired on the entry bar itself and wiped both back to nothing, three lines after the entry set them.
On the next bar the bracket went out with no stop and no target. A new entry needs a flat book, so
the position could never close either: **one trade, unprotected, held to the end of the chart.**

**Sizing is what made it fatal rather than merely wrong.** Every trade is sized to risk a fixed
percentage of equity, so a tight stop buys a large position — MEASURED over the 486 signals the
shipped configuration produces, the median stop is $6.98 and the 1st percentile is $1.26, which on
a $10,000 account at 1% risk is **14 and 79 ounces — $47k and $262k of notional**. Those are
correct sizes for a trade with a stop. With no stop they are the account.

⚠ **The study could never have caught this**, and that is the transferable half. It measures in R
with the stop assumed live, so an absent stop is not a shape it can express. **Everything that
decides whether a position is protected lives only in the strategy file, and nothing upstream
tests it.**

✅ Fixed by a per-bar just-entered flag, which is what `mpc_h4_sweep_strategy.pine` has always
carried and what the derivation of this file dropped. The flag does two jobs: the bracket now goes
out on the entry bar (so it is live for the next bar's range rather than the one after it), and the
reset only fires when the book is flat *and* nothing was opened this bar.

✅ **`indicators/tools/check_flat_reset.py` now refuses this shape mechanically.** It was watched
RED against the exact file that blew the account, naming both cleared values and their lines, and
all thirteen strategy files pass it. ⚠ It knows this one shape and nothing else — it cannot tell
you a bracket is correct.

---

## The numbers behind every default

All from `backtest/tools/pre_sos_leg.py`, Vantage XAUUSD, 2018-09-13 → 2026-08-23. Full study:
`docs/PRE_SOS_LEG_STUDY.md`.

| default | value | why |
|---|---|---|
| chart / confirmation frame | 5m | 15m confirms too late (target closer than the stop); 1m collapses to +0.002R once the round trip is charged |
| levels must be swept within | 180 min | a sharp peak — 120 min scores +0.185R and 240 min +0.168R against its +0.276R |
| levels that must agree | 1 | ⚠ two looked best ALONE and is the worst change in the sweep once the half-target exit is in — see below |
| only against the 15m trend | on | the with-trend half is where the edge is not |
| refuse a target nearer than | 2R | below it the setups have no room to pay. Measured on the whole distance to the swing, not on the take profit |
| look back for the extreme | 120 min | 90 min scores marginally better alone and adds nothing once the stop is wider; left alone to move one knob fewer |
| **air under the stop** | **0.20 ATR** | ⚠ **changed from 0.05 on 2026-08-25.** A smooth hill: 0.0 → +0.227R, 0.1 → +0.301R, **0.2 → +0.357R**, 0.3 → +0.331R, 0.5 → +0.292R |
| **take profit** | **half the way to the swing** | ⚠ **new on 2026-08-25.** A plateau from 0.44 to 0.54, peaking at 0.50 |
| move the stop to breakeven | **off** | arming at 30% costs −0.217R; the best point (~70%) is worth +0.024R |

🔴 **The breakeven default is OFF and that is the measurement, not caution.** A breakeven stop on
this setup converts winners into scratches — the win rate falls 28.1% → 16.2% while losses only
fall 71.9% → 50.9%, because the retracements happen INSIDE the leg rather than before it. Leaving
the stop alone is within noise of the best possible setting and is one less thing to get wrong.

⚠ **Entering on the 15-minute close instead costs about a quarter of the edge** (+0.296R →
+0.223R) and was measured, because it decides whether the file needs two engines at all. It does.
The single-frame stand-in — a bar closing back beyond the sweep bar's extreme — scores +0.082R.
**The faster engine is not a convenience; it is what carries the result.**

---

## 🔴 The tuning pass, and the two settings that changed (2026-08-25)

**Everything above the table was measured with NO POSITION SLOT, and that is not this strategy.**
`backtest/tools/pre_sos_leg.py` says so in its own docstring — it scores every setup on its own, as
though the account could hold all of them at once. This file holds ONE. Measured by
`backtest/tools/pre_sos_leg_queued.py`: **228 setups → 200 taken**, +0.296R → +0.276R. The 28 it
cannot reach are BETTER than average (32.1% hit, +0.441R) and worth +12.3R, so the slot costs real
money — it just does not break the setup. ⚠ **The study gives up on a stuck trade after ~4 days and
this file has no time stop, so the true slot cost is worse than 12.3R.**

**The sweep is `backtest/tools/pre_sos_leg_tune.py`, and it moves one knob at a time with the slot
ON.** Shipped scored n=200, 27.5% hit, +0.276R, +55.2R, worst drawdown 18.1R. Two changes landed:

| | shipped | tuned |
|---|---|---|
| air under the stop | 0.05 ATR | **0.20 ATR** |
| take profit | the swing | **half the way to it** |
| trades / hit rate | 200 / 27.5% | **208 / 47.6%** |
| expectancy | +0.276R | **+0.400R** |
| total | +55.2R | **+83.3R** |
| worst peak-to-trough | 18.1R | **9.7R** |
| each half of the history | +0.194 / +0.339 | **+0.386 / +0.414** |

🔴 **WHY THE EARLIER EXIT WINS IS THE SLOT, NOT THE EXIT.** Booking half the distance gives up
reward per trade — the parent study, which has no slot, rates 0.5 at +0.349R against 1.0's +0.310R,
a modest gap. With one position it is +0.400R against +0.276R, because **a trade that ends sooner
hands the slot back and the strategy catches setups it used to be busy for** (200 → 208 taken).
**A rule scored one-trade-at-a-time cannot see that, and every number above the table was scored
that way.**

⚠ **Neither change is a lone spike, which is the whole reason they were kept.** The stop buffer is a
smooth hill (0.0/0.1/0.2/0.3/0.5 → +0.227/+0.301/+0.357/+0.331/+0.292R) and the exit is a plateau
(0.44→6.36, 0.46→6.77, 0.48→7.81, **0.50→8.53**, 0.52→8.21, 0.54→8.46 return-over-drawdown). ✅ The
re-walk reproduces the untouched baseline EXACTLY at a fraction of 1.0 — a built-in control that
would catch the harness rather than the setting.

🔴 **REQUIRING TWO LIQUIDITY LEVELS TO AGREE IS THE FINDING TO REMEMBER, AND IT IS A WARNING ABOUT
SWEEPS.** Measured alone it is the single best change available — return-over-drawdown 5.19 against
1's 3.04, on half the trades. Combined with the half-target exit it **cuts the return by more than
half** (+78.5R → +38.6R) and its two halves fall apart (+0.133 / +0.547). ⚠ **A one-at-a-time sweep
cannot see an interaction, so its winners are candidates and never conclusions** — the combination
has to be run before anything is believed.

### What risk percent this supports

Compounded over the tuned trade list, constant fraction per trade:

| risk each trade | grows to | worst drawdown | if a future run is twice as deep |
|---|---|---|---|
| 2.0% | 4.7x | 17.9% | 32.7% |
| 2.5% | 6.7x | 22.0% | 39.2% |
| 5.0% | 32.1x | 40.0% | 64.0% |
| 10.0% | 304.0x | 65.8% | **88.3%** |

⚠ **9.7R is the worst drawdown IN THIS SAMPLE and the real worst is still ahead** — that is what the
last column is for, and it is why 10% is not recommended however good the multiple looks. The worst
run of consecutive losers was **6**. ⚠ **The smallest stop is still $0.88 even with the wider
buffer**, so the sizing hazard in the section above has not gone away; the minimum-stop refusal is
still shipped OFF.

⚠ **These are the STUDY's numbers under this file's settings, not this file's numbers.** Nobody has
yet compared a TradingView run against them.

---

## What this file does NOT have

No export twin, so **no parity gate can ever run on it** — the same hole
`mpc_realign_strategy.pine` has, and every number it produces will be a lab finding until a twin
exists. No Python port. No confirmation table. No fibs, sessions or internal structure drawing. No
news filter. No scale-in, no TP ladder, no time stop. One position at a time, which is not a
preference: every number behind this file was measured with one slot.

---

## Before this is believed

- ✅ It compiles and runs (2026-08-25, 1,443 lines). The token ceiling was the risk and it cleared.
- **208 trades in 9 years**, and it has never been run on a chart long enough to compare against
  that.
- ⚠ **EVERY YEAR IS POSITIVE AT THE TUNED SETTINGS, AND THAT IS A REASON FOR MORE SUSPICION, NOT
  LESS.** The three losing years the shipped settings had (2018 −2.4R, 2021 −1.8R, 2024 −11.6R) all
  turn: +7.6R, +4.8R, +3.4R. Nine from nine is the shape an over-fitted result has. **What argues
  against that here is that only TWO knobs moved, each sits on a smooth hill rather than a spike,
  and each holds up on both halves of the history separately** — but the honest reading is that the
  earlier exit converts the marginal years, not that this strategy cannot have a losing one.

| year | shipped | tuned |
|---|---|---|
| 2018 | −2.4R | **+7.6R** |
| 2019 | +12.5R | +17.9R |
| 2020 | +4.6R | +7.2R |
| 2021 | −1.8R | **+4.8R** |
| 2022 | +4.6R | +1.4R |
| 2023 | +3.5R | +11.6R |
| 2024 | −11.6R | **+3.4R** |
| 2025 | +22.0R | +15.5R |
| 2026 | +23.7R | +13.8R |

⚠ **2025 and 2026 are LOWER tuned than shipped** — the earlier exit gives up the big runners, and in
the two years that had them that costs real money. It buys back more than it costs everywhere else.

- The rule set was found by testing ~20 combinations and reporting what scored. It survived a time
  split, a knob sweep and a change of broker feed; it is not out-of-sample.
- It reads the same structure stream as A+ on the same instrument, so the two are **not**
  independent. `backtest/tools/overlap_audit.py` has not been run against it.

---

## 🔴 The exhaustive search, and the two filters that came out of it (2026-09-01)

**Aaron's ask: run every combination, find the best settings, and pick the timeframe.** Then, once
those came back: *"I like 5% and I want more quality trades — see how to decrease the losing trade
count while keeping the highest quality trades."* Both halves are recorded here.

**509,000 configurations were searched and NOT ONE BEAT THE SHIPPED SETTINGS.** That is the whole
headline and it deserves to be said before anything else, because it is the outcome a search is
least likely to produce and most likely to be doubted.

| search | what moved | configurations | best found |
|---|---|---|---|
| coarse grid, 15m/5m | 9 axes at once | 252,000 | the shipped settings |
| fine grid, 15m/5m | the winner's own square | 5,040 | the shipped settings |
| coarse grid, 30m/5m | the same 9 axes, re-tuned | 252,000 | +35.9R vs +83.3R |
| small grid, 15m/1m | exits and filters, re-tuned | 144 | +38.0R against a 37R hole |
| every pair of charts | nothing — the rules held | 14 | 15m with a 5m trigger |

⚠ **The fine pass DID name a winner and it was rejected on purpose.** Requiring the sweep within
165 minutes instead of 180 scored +86.8R against +83.3R. Its neighbours across single 15-minute
steps run **74 / 87 / 83 / 75 / 77 / 74** — the axis moves 10R between adjacent values, so 165 is a
coin landing well, not a setting. **Every other axis is a smooth hill with the shipped value on
top.** This is why the tool prints neighbours at all: without them, that row is a 4% improvement.

### The timeframe question, answered

| base / trigger | trades/yr | hit | total | worst run | R over drawdown |
|---|---|---|---|---|---|
| **15m / 5m** | **26.2** | **47.6%** | **+83.3R** | **9.7R** | **8.60** |
| 30m / 5m | 39.4 | 35.1% | +17.6R | 27.7R | 0.64 |
| 15m / 1m | 270.4 | 30.1% | −9.0R | 78.7R | −0.11 |
| 1-hour and 4-hour bases | — | — | every configuration loses | | |

🔴 **The 30-minute chart was RE-TUNED from scratch before being dismissed**, because a sweep that
holds one chart's settings and applies them to another only proves settings do not transfer, which
nobody doubted. Its own best of 252,000 is +35.9R against an 18.6R hole, and its exit curve swings
+36R → −28R between neighbouring values. ⚠ **The 1-minute trigger is the answer to "can this pay me
every day": it fires 270 times a year and the edge is gone.** Frequency is available here; it is
just not worth having.

### The edge is not gold's trend

At the shipped settings the setup wins **30.2%** against **18.2%** for random entries matched on
direction, hour of day and stop distance — **+12.0%, 3.9 standard deviations**. ⚠ Setups where NO
level was swept run at −0.203R and score −3.3% against their control, so the sweep requirement is
carrying real weight rather than decorating the entry.

### Fewer losers: two filters, and only one of them can ship today

| rule | trades | losers | hit | total | worst run | at 5% risk |
|---|---|---|---|---|---|---|
| what shipped on 2026-08-25 | 208 | 109 | 47.6% | +83.3R | 9.7R | 32.1x, 40.0% down |
| **+ never trade Friday** | **169** | **84** | **50.3%** | **+84.0R** | **7.9R** | **36.4x, 33.5% down** |
| + also refuse a transitioning market | 148 | 70 | 52.7% | +83.9R | 5.9R | 38.3x, 26.4% down |

✅ **The Friday refusal is IN the file and defaults to ON.** 40 Friday setups over eight years
returned **+1.1R between them** while supplying 25 of the losses — the money is unchanged and the
worst run drops by a fifth. ⚠ **The day is read in UTC because that is how it was measured**; a
chart opened in another timezone would otherwise refuse a different set of bars, silently and only
for part of the day. ⚠ **Friday is NOT reliably bad** — it lost 8.5R in the first half of the
history and made 9.6R in the second. The case for skipping it is that it adds risk without adding
return, not that the data proves Friday is cursed. ⚠ Weekend carry is not the mechanism: 18 Friday
trades ran past Friday and they booked **+5.2R**.

🔴 **The transitioning-market refusal is the bigger win and it CANNOT be built here yet.**
`engines/regime/` is Python-only — it has no Pine source, by construction, so putting it in this
file means writing a second implementation of a canonical engine in another language with no parity
gate to hold it honest. That is a project, not an input. What it is worth, measured: 24 trades over
eight years, +0.060R each — near-free, and removing them takes the worst run from 7.9R to 5.9R and
**the 5%-risk drawdown from 33.5% to 26.4%.**

⚠ **Both cuts are applied BEFORE the position slot**, so refusing a setup genuinely buys whatever
came next. Scoring a cut by deleting rows from a finished result measures a strategy that could see
the future, and it flatters every cut ever tried.

### What was tried and did NOT work — recorded so it is not tried again

- **Every session filter loses money.** Asia is the best session per trade (+0.534R on 68 trades);
  refusing it drops the average to +0.335R.
- **Capping how far the swing may be loses money.** Nearby targets win most often (53.4% at 2–3
  stops) and pay least (+0.178R); the 8 setups aiming 9+ stops away pay **+1.83R each**.
- **A floor or ceiling on the stop size does nothing** — 198 of 208 stops already sit above three
  times the 5-minute average range, so the axis has nothing to cut.
- **Moving the stop to breakeven costs money at every arming point**, confirming the 2026-08-25 pass.
- **Trading one side only is worse than both.** Longs alone +47.4R on 69 trades, shorts alone
  +35.9R on 139, together +83.3R — they do not compete for the slot.
- **Demanding two levels agree** halves the take, +83.3R → +38.6R, and does not raise the edge
  (1 family +12.3%, 2 families +11.7%, 3 families +12.7% against control).

### Risk, at Aaron's chosen 5%

| rule | multiple | worst drop | if the worst run is twice as deep |
|---|---|---|---|
| shipped 2026-08-25 | 32.1x | 40.0% | **98.3%** |
| + no Friday | 36.4x | 33.5% | 95.1% |
| + no transitioning market | 38.3x | 26.4% | 85.1% |

🔴 **The last column is the one that decides whether 5% is survivable, and on the shipped rules it
is not.** A worst run twice the deepest one measured is an ordinary thing for a 200-trade sample to
produce, and at 5% that is a 98.3% drawdown — an account that no longer exists. The Friday refusal
moves it to 95.1% and the regime refusal to 85.1%. **Neither is comfortable.** Aaron's stated plan
is to dial the risk back by hand as the account grows (2026-09-01); that is a decision to manage
this actively rather than a reason the number is wrong.

⚠ **Every year stays positive under both filters** — 2018 +7.1, 2019 +21.9, 2020 +13.2, 2021 +6.5,
2022 +3.8, 2023 +5.9, 2024 +1.5, 2025 +15.5, 2026 +8.6. The caution above the earlier per-year
table applies here unchanged and with more force: this is now a rule set that has been shown nine
positive years twice.

⚠ **It holds a position 5.76% of the time** (32,397 of 562,071 5-minute bars), median hold about six
hours. That is the closest thing to an overlap number this strategy has, and it is **not** the
overlap audit — `backtest/tools/overlap_audit.py` needs a Python package and none exists.

Full tooling and how to re-run any of it: `backtest/tools/pre_sos_leg_grid.py`.

---

## The two remaining optimisations, both now measured (2026-09-01)

### A two-stage exit does not beat one exit

**160 ladders — take part of the position at one distance and let the rest run to another,
with and without moving the stop up after the first fill.** The best of them scores **+85.8R
against the single exit's +84.0R**: a 2% gain for three new inputs.

⚠ **It is inside the noise of its own neighbours and that is why it is refused.** The four
ladders nearest the winner score +81.8R, +82.1R, +84.5R and +85.8R — the shipped single exit
sits in the middle of that band. **A winner you cannot distinguish from the configurations
beside it is not a winner.**

🔴 **THE FIRST SEARCH GOT THE ANSWER WRONG BECAUSE OF ITS AXES, AND THAT IS THE LESSON.** It
only offered ladders whose second leg ran FURTHER than the shipped exit — 70%, 80%, the whole
swing. Every one of those lost, by up to 5.5R, and they lost for a reason that took the slot to
see: **the runner keeps the position open 625 minutes against 400, and blocks ten setups doing
it.** Only when the axes were widened to allow a ladder that finishes SOONER did anything come
close. **A search that can only move a setting one way has decided the answer before it runs.**

⚠ For the record, since the temptation will come back: the best ladder is 75% off at half way
with the rest at 60% and the stop moved up after the first fill. It is not shipped.

### The real bill, on the account this will actually trade

🔴 **EVERY NUMBER IN THIS DOCUMENT ABOVE THIS LINE CHARGES HALF THE SPREAD AT ENTRY AND NOTHING
ELSE** — no commission, no financing, nothing on the way out. That was the parent study's model
and it was honest for a study. Quoted at a strategy about to trade money it is optimistic, and
by how much had never been measured.

| | Vantage demo (what everything above used) | **PU Prime ECN (the live account)** |
|---|---|---|
| spread / commission | $0.22 / none | **$0.12 / $1.00 a side a lot** |
| trades | 169 | **171** |
| gross | +84.01R | **+86.19R** |
| the spread paid getting stopped out | −1.56R | **−0.90R** |
| commission | −0.00R | **−0.63R** |
| overnight financing | −2.44R | **−2.46R** |
| **net** | **+80.01R** | **+82.19R** |
| worst run, after costs | 8.4R | **8.18R** |
| at 5% risk | 30.2x, 34.5% down | **33.3x, 34.4% down** |

✅ **The headline survives: the whole bill is 4.0R over eight years, about 4.6% of the gross.**
✅ **And the live broker is CHEAPER than the one every number was measured on** — half the
spread, which is worth more than its commission costs. It also clears two extra setups, because
a tighter entry leaves the target marginally further away in stops.

⚠ **Financing is the largest single cost, not commission** — 2.46R against 0.63R. That is the
price of a six-hour median hold that sometimes crosses a rollover, and it is charged at the
measured −79.60 / +30.25 per lot per night with Wednesday carrying the weekend.
⚠ **Costs are charged in R, which makes them size-independent AND makes a tight stop expensive**:
one lot risks the stop distance times the contract size, so the same commission is a far larger
slice of a small risk. The 88-cent stop noted earlier pays roughly eight times the commission,
in R, that a $7 stop does.
⚠ **The spread is charged twice for a loser and once for a winner, on purpose.** Entry is a
market fill and pays the offer; the target is a resting limit and fills at its own price; the
stop is a market order and pays again on the way out.
⚠ **The swap figures move** — this symbol read 1.7% adrift in three weeks with nothing to
announce it. Re-read with `algos/tools/broker_facts.py` before quoting this table again.

### What is still not done

🔴 **NOTHING HAS COMPARED THE STRATEGY FILE AGAINST ANY OF THIS.** There is no TradingView export
of its trades, so no check exists that the file books what the model measured. It is the largest
outstanding item on this strategy and no amount of further searching substitutes for it.

---

## 🔴 The session windows were on the wrong clock, and the port that found it (2026-09-01)

The Python port landed (`strategies/python/mpc_extreme_leg/`), which meant the Pine's decisions and
the study's decisions could be diffed against each other for the first time. It found three
differences. **Only one of them is in the file you trade, and it had been there since the file was
written.**

### 1. Every session window sat 4–5 hours later than its own name — FIXED

The file built its session highs and lows from three fixed clock strings with **no timezone**, and
a session string with no timezone resolves in the SYMBOL'S EXCHANGE clock — New York for gold,
daylight saving and all. So:

| the input said | it actually tracked |
|---|---|
| Asia `0000-0900` | 05:00–14:00 UTC in winter — the London morning |
| London `0800-1700` | 13:00–22:00 UTC — **the New York session** |
| New York `1300-2200` | 18:00–03:00 UTC — the New York evening and the Asian open |

**MEASURED over 38,747 M15 bars: the old "London" high and low equalled the house New York
session's on 100.0% of bars.** The other eight pairings agreed on 0.0–8.0%. So two of the three
windows tracked no real session at all, and the third was the right session under the wrong name.

Each window now names its own city, which is what `indicators/engines/mpc_assistant.pine` — the
file this was ported from — has always passed, and what `engines/sessions/` carries. Three sources
now agree where two used to disagree with one.

⚠ **It changes what this strategy trades**, and the direction was decided by the house standard and
by the parent file, **never by which clock made more money**. Do not re-optimise around it: picking
a session clock for its profit is picking a result and calling it a rule.

⚠ **Nothing failed, nothing repainted, and the chart looked right the whole time.** A session box in
the wrong place still looks like a session box. The generalisation is worth more than the fix:
**an omitted argument is a default you did not choose** — a wrong timezone gets noticed because
somebody typed it, while a missing one inherits whatever the platform decides, silently, and the
platform's choice here depends on the SYMBOL.

### 2 and 3. The STUDY's arming rule is slightly looser than this file's — NOT a defect

Both differences are in `backtest/tools/pre_sos_leg.py`, and both are recorded there rather than
fixed. It dates a sweep at the 15-minute bar's CLOSE where the strategy dates it on the 5-minute bar
that crossed (so its window reaches 5–15 minutes further back), and it counts wall-clock MINUTES
where the strategy counts BARS (they part company across a weekend).

🔴 **Every number in this document came through that study, so every one of them describes an
arming rule marginally LOOSER than the file being traded.** They are not wrong and they are not
re-measured here. The thing that settles it is the parity gate, which is why the gate exists.

### One dead input was removed in the same pass

**"Enter on the change-of-character close"** appeared exactly once in 1,443 lines — its own
declaration — and nothing read it. Its tooltip promised that turning it off would wait for the next
15-minute close; turning it off did nothing at all. It was DELETED rather than wired, because the
branch it promised was measured and is worth **8R less** (+75.1R against +83.3R over the same bars).

⚠ A control that does nothing costs nothing to ship and is indistinguishable from one that works.

### Where the port stands

Five of the six porting stages are done (`docs/STRATEGY_WORKFLOW.md`). **Stage 4 — a bar-by-bar CSV
off `mpc_extreme_leg_strategy_export.pine` — is the one step no machine here can take**, and until
`compare_extreme_leg.py` exits 0 on one, the port's numbers are lab findings rather than
measurements. Over the full cached history at the shipped defaults it replays **178 trades /
+97.4R / 50.6% hit / worst losing run 7.9R, every year positive** — the same place the study landed
(169 / +84.0R / 7.9R), which is the only claim that comparison supports.
