# CLAUDE.md — MPC Extreme Leg (Python port)

**Purpose:** The Python side of `indicators/strategies/mpc_extreme_leg_strategy.pine` — the leg
that runs INTO the shift of structure, which is the move the A+ bot's setup begins after.
**Scope:** This package only. The strategy's design, its optimisation record and the evidence
behind each default live in `indicators/strategies/docs/mpc_extreme_leg_strategy.md`; the porting
process lives in `docs/STRATEGY_WORKFLOW.md`. Neither is restated here.
**Status:** 🟠 **THE GATE HAS RUN ON A REAL EXPORT AND IS RED FOR ONE KNOWN REASON (2026-09-02).**
Written 2026-09-01. The disagreement is the weekly-level rule this file predicted before the run,
it was traced to the PINE being wrong, and the Pine is fixed — but **a fixed Pine needs a fresh
export, so the gate is still red until somebody re-exports.** Until it exits 0, every number this
package produces is a lab finding, not a measurement.
**Last reviewed:** 2026-09-01

---

## The first real parity run — RED, for the reason written down before it (2026-09-02)

Export: `engines/VANTAGE_XAUUSD, 5_2b302.csv`, 21,320 M5 bars **2026-05-17 → 2026-09-02**,
20,319 compared after warm-up.

```
✗ 7 field(s) diverged — px_high_age, px_swept, high_armed, px_high_fam,
                        px_low_fam, low_armed, px_low_age
```

✅ **EVERY ONE IS THE SAME SINGLE CAUSE, AND IT IS PREDICTED DISAGREEMENT #1 IN THE TABLE BELOW.**
Decoding the sweep column family by family over the 20,319 compared bars:

| family | only the CHART saw it | only PYTHON saw it |
|---|---|---|
| H4 low / high | 0 | 0 |
| session low / high | 0 | 0 |
| daily low / high | 0 | 0 |
| **weekly low** | **3** | **3** |
| **weekly high** | **2** | **2** |

**Ten bars in 20,319, all weekly, and each appears on both sides because the sweep is TIMED
differently rather than missed.** Everything downstream — the ages, the family counts, the two
armings — cascades from those ten.

✅ **PREDICTED DISAGREEMENT #2 IS GONE, WHICH CONFIRMS THE SESSION FIX.** The session families
agree on every one of the 20,319 bars. That fix was made on 2026-09-01 against a cross-map, with no
export to check it; this export checks it.

🔴 **THE PINE WAS THE ONE THAT WAS WRONG, AND IT DISAGREED WITH ITS OWN PARENT.** Its sweep tracker
took EVERY family on a wick. `engines/liquidity/` takes a weekly level only on a **CLOSE** through
it (`engine.py:228`, citing `mpc_assistant.pine` line 1427) and the lower families on a wick — so
the house engine and the parent indicator agreed with each other and this strategy file was the odd
one out. ✅ **Fixed in `indicators/strategies/tools/build_extreme_leg.py`** (`f_track` gained a
close-through mode, passed only for weekly). ⚠ **The direction was decided by the house standard,
not by which rule made more money** — same call as the session clock. Do not re-optimise around it.

⚠ **NO PYTHON BASELINE MOVES.** This side already followed the engine; only the chart changed.
Every figure in this file and in `indicators/strategies/docs/mpc_extreme_leg_strategy.md` stands.

🔴 **NOT ONE TRADE DIVERGED — AND THAT IS A NARROWER CLAIM THAN IT SOUNDS.** No entry, stop,
target, fill, R or equity column appears in the diff, so on this window the ten weekly-sweep
differences never reached a position. But the window is **3.5 months, not 6.6 years**, and it
contains only **7 entries**. **Refusal codes 2, 4, 5 and 7 were never reached at all**, so this run
says nothing whatever about them. A green re-run on this same export would still be a narrow gate.

⚠ **The next export must come from the REGENERATED twin.** The one above predates the weekly fix,
so re-running the gate against it will reproduce the same ten bars for ever.

---

## What is missing, and it is the only thing that matters

**Stage 4 — the CSV.** A human has to open `indicators/strategies/mpc_extreme_leg_strategy_export.pine`
on a XAUUSD **5-minute** chart and take *⋮ → Export chart data → Bar data and indicator values*.
Nothing here can do it. Then:

```bash
python3 strategies/python/mpc_extreme_leg/tools/compare_extreme_leg.py '<export>.csv' --warmup 1000
```

🔴 **A TRADE LIST IS NOT AN EXPORT, and the refusal that says so was UNREACHABLE until 2026-09-02.**
The first real file handed to this gate was a trade list (Strategy Tester → List of Trades), and it
did not refuse — it died with a traceback out of `mpc_sos_fade`'s loader saying *export has no
'time' column*, which points the reader at a different strategy's module. The check ran AFTER the
shared loader, and the loader raises first. It now reads the HEADER before anything else and names
the exact menu to use instead.

🔴 **Its test passed the whole time, and that is the part to keep.** The fixture was a bar CSV with
a `time` column and no sequence column — a shape TradingView never produces. **A fixture more
capable than the real thing describes a system you do not have**, and the assertion happened to
match text in the old message, so nothing looked wrong. The fixture is now the real header from the
file that arrived, BOM included, and there is a second case for a wrong-script export that is *not*
a trade list, because naming a fault a file does not have sends somebody to the wrong menu.

The twin plots 62 per-bar columns so a disagreement lands on a named column at a named bar; a trade
list says two runs disagree and nothing about where.

⚠ **The twin and the strategy are GENERATED FROM ONE BODY** by
`indicators/strategies/tools/build_extreme_leg.py`, so they cannot drift. Edit the generator, never
either `.pine`. The build asserts the bodies are identical apart from the title and the appended
export block.

---

## The one known disagreement left, and the two that were fixed

Found 2026-09-01 by diffing the Pine against the study that measured this strategy. Three root
causes; the port inherits only the first, and it was fixed on the Pine side.

| | What differed | Where it is now |
|---|---|---|
| **Session clocks** | The Pine read three fixed session strings with **no timezone**, so all three resolved in the symbol's EXCHANGE clock (New York). Two windows tracked no real session; the one labelled "London" was the New York session under a wrong name — its high and low equalled the house NY session's on **100.0%** of 38,747 M15 bars, while the other eight pairings agreed on 0.0–8.0%. | ✅ **FIXED IN THE PINE.** Each window now names its own city, matching `indicators/engines/mpc_assistant.pine` — which always passed the timezone — and `engines/sessions/`. |
| **When a sweep is stamped** | The study dates a sweep at the 15-minute bar's CLOSE; the strategy dates it on the 5-minute bar that crossed. The study's freshness window reaches 5–15 minutes further back. | ⚠ **STUDY ONLY.** This port runs the liquidity engine on the chart's own bars, so it stamps where the Pine does. Recorded in `backtest/tools/pre_sos_leg.py`. |
| **What freshness is counted in** | The study counts wall-clock MINUTES; the strategy counts BARS. They part company across a weekend. | ⚠ **STUDY ONLY.** This port counts bars. Same record. |

🔴 **THE CONSEQUENCE FOR EVERY NUMBER THIS STRATEGY HAS: the grid, the timeframe answer, the two
filters and the cost bill were all taken through the study, so they describe an arming rule
marginally LOOSER than the file being traded.** They are not wrong and they are not re-measured
here — the gate is what settles it.

⚠ **The session fix CHANGES WHAT THE STRATEGY TRADES.** It is a correction, not a tuning: the
direction was decided by the house standard and by the Pine's own parent, never by which clock made
more money. **Do not re-optimise around it** — picking a session clock for its P&L is picking a
result and calling it a rule.

---

## What this side does that the Pine does not, and why

🔴 **Pine's `na` is a float NaN here, not `None`.** Every refusal in the ladder is a comparison
against a value that may not exist — no swing, no average range for the first 49 bars. Pine reads
`na < 2.0` as false; Python's `None < 2.0` raises and `nan < 2.0` is **False**, the same answer for
the same reason with no guard anywhere. ⚠ **Adding an `isnan` check to any branch of
`_ladder` makes this side refuse where the chart does not** — there is a test that goes red on
exactly that. It is a parity device and nothing else; the repo's "no answer vs measured zero" rule
still uses `None`, which is why the sweep ages do.

🔴 **Refusal code 7 has no Pine counterpart, deliberately.** With no average range yet the stop is
`na`, every refusal above declines to fire, and the Pine reaches its entry call with an `na`
quantity. That is a warm-up bug, not a trade. This side refuses and records why, loudly, into the
blocked list — a divergence nobody can see is the worse half. It can only fire inside the ATR
warm-up, which every gate run excludes anyway.

⚠ **The 15-minute half instantiates the canonical structure engine a second time** rather than
copying it, and reads one private field (`_ext.ash` / `_ext.asl`) behind a guard, because the
public event stream fires on CHANGE and a target is a live STATE. Same call, same reason, as
`backtest/tools/pre_sos_leg.py`. A rename upstream fails on construction rather than scoring
nothing.

⚠ **A profile with `bid_ask_fills` on is REFUSED, not approximated.** That flag moves fills rather
than charging a cost, so honouring half of it would report a trade list neither model produces.

---

## Registering in the lab — and what running the scanner found

`LAB_STRATEGY` in `__init__.py` is the whole opt-in; the scanner imports the package and reads it.
MEASURED by actually calling `services.strategy_scanner._parse_python_package` on it rather than by
reading the dict and agreeing with it: **22 settings, 20 of them labelled from
`mpc_extreme_leg.meta.json`, 12 marked core, 4 steps, `display_under` honoured.**

🔴 **IT WAS 25 SETTINGS UNTIL THAT CALL, AND THREE OF THEM SHOULD NEVER HAVE BEEN THERE.** The
structure length, the 15-minute aggregation and the ATR length are HARDCODED in the Pine — no
input, therefore no `cfg_*` column, therefore nothing a parity gate could ever check. As config
fields each drew a row on the strategy page under its raw field name, and a run that moved one
would have diverged from the chart with nothing anywhere to say so. They are keyword arguments on
the strategy now: a test can pass one, the lab cannot see one. ⚠ **This is `config.py`'s own
opening rule catching `config.py`** — and the only reason it was caught is that the registration
was RUN. A dict that looks right is rule 7 exactly: a label is a claim about code somewhere else.

⚠ **The two remaining unlabelled settings are deliberate** — what a lot is worth and which
instrument. TradingView puts both on the Strategy Properties tab rather than in an input, so no
export column can carry them; the A+ bot exposes the same pair the same way.

## The tests, and what they are worth

```bash
python3 -m pytest strategies/python/mpc_extreme_leg/tests -q       # 54 tests
# ~2 min serial. Under the suite's own `-n auto --dist load` it MEASURED 24s on an idle machine and
# 52s on a busy one — quoted as a range because both readings are real and a single number here
# would be the tighter one, which is the reading nobody reproduces.
```

`tests/test_extreme_leg.py` — 39 hand-traced rules, ~2s. **Every one was watched RED, and each
docstring names the mutation that does it**, so the next reader can repeat it in ten seconds
instead of trusting a sentence.

`tests/test_compare_extreme_leg.py` — does the GATE work. 🔴 **It cannot prove Pine parity and must
never be read as if it did**: it builds a synthetic export from this side's own decisions and feeds
it back, so it only checks the gate's plumbing — column names, the two bit schemes, settings
decoding, row alignment — and that a disagreement is DETECTED AND NAMED. Each case moves one column
or flips one bit and asserts the gate fails and says which.

⚠ **The twenty column checks are ONE process, not twenty, and that is a stronger test rather than a
cheaper one.** Each case re-runs the strategy in a subprocess; twenty of those cost more wall clock
than everything else here put together, on a suite whose speed is a standing rule. Moving every
column at once also proves the gate's reporting is neither capped nor first-only, which a
per-column loop cannot show at all. Three columns keep an isolated case, one per KIND that fails
differently: a price carried through the whole ladder, a bit-packed column, and a refusal code.

🔴 **The fixture's WINDOW IS MEASURED, and the first version of it was wrong in the way this repo
keeps meeting.** Bars 0–6,000 of the cache contain armings and refusals but **not one accepted
setup**, so the test that raises the minimum-target setting passed against a gate that could not
have failed. Bars 12,000–20,000 carry 6 acceptances and refusal codes 0/1/3/6, and the fixture now
ASSERTS an acceptance, a refusal and an opened trade rather than hoping for them. Re-measure before
moving those numbers.

---

## The two cuts TradingView cannot make (2026-09-02, Aaron's call)

**Both default OFF and the parity gate REFUSES to run with either on.** They read
`engines/regime/` and `engines/news/`, neither of which has a Pine source — by construction, not
by omission — so no `cfg_*` column can carry them and this gate can never check them. That is the
thing `config.py`'s opening rule forbids, and it is allowed only because the hole is closed at the
other end. **A gate that quietly compared a filtered Python against an unfiltered Pine would report
a disagreement per refused setup, on a real column at a real bar, and send the reader into the
ladder to hunt for a porting bug that is not there.**

⚠ **They sit LAST in the refusal ladder.** With both off this side's decision stream is
bit-identical to the chart's; with one on, the divergence lands on its own code (8 or 9) rather
than changing which of the Pine's codes a bar records. `test_the_new_cuts_sit_AFTER_every_refusal_the_pine_can_also_make`
pins it and the whole design rests on it.

⚠ **Turning one on makes the bot and the chart different strategies.** The chart stops being a
picture of what the bot does. That is the cost, not a caveat.

### What they are worth — MEASURED 2026-09-02, 470,995 PU Prime `XAUUSD.p` M5 bars, 2020-01-01 → 2026-08-23

| | trades | R | worst losing run | asked | refused |
|---|---|---|---|---|---|
| **shipped (both off)** | 132 | +57.10R | 8.13R | — | — |
| + skip a transitioning market | 113 | **+58.53R** | **6.00R** | 550 | 40 |
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
`indicators/strategies/docs/mpc_extreme_leg_strategy.md` quotes 24 trades at +0.060R each and a
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

⚠ **If either cut is ever switched on, RE-RUN `backtest/tools/overlap_audit.py`.** It changes what
this bot trades, so the clash figures against the live A+ bot stop describing it. That audit has
already gone stale twice in this repo by being left until afterwards.

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

---

## Never do

- Quote a number from this package as a measurement before `compare_extreme_leg.py` exits 0.
- Allow a second concurrent position. Every result this strategy has was measured with one slot,
  and the reason a filter pays here is that refusing a setup genuinely buys the next one.
- Fork `engines/liquidity/` or `engines/sessions/` to make this side agree with a Pine. When they
  disagree, one of them is wrong and the gate says which — see the table above for how that went.
- Add a field to `ExtremeLegConfig` that has no Pine input behind it. No `cfg_*` column can carry
  it, so the gate would leave it at this side's default and never see a disagreement about it.
