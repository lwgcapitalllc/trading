# CLAUDE.md — Extreme Leg (Python port)

**Purpose:** The Python side of `strategies/tradingview/extreme_leg_strategy.pine` — the leg
that runs INTO the shift of structure, which is the move the SOS Fade bot's setup begins after.
**Scope:** This package only. The strategy's design and the evidence behind each default live in
`strategies/tradingview/docs/extreme_leg_strategy.md`; the porting process lives in
`docs/STRATEGY_WORKFLOW.md`. Neither is restated here.
**Every sweep run on this bot is `extreme_leg_optimization.md`, next to this file — read it
BEFORE proposing a tuning idea.** Four searches have each landed back on the shipped settings, and
a cut is scored on the setup pool BEFORE the one-position rule or its number is fiction.
**Status:** ✅ **PARITY GREEN — `compare_extreme_leg.py` exits 0 (2026-09-02).** Stage 6 of six is
done: the Python makes the same decisions as the Pine on every one of 20,327 compared bars.
⚠ **READ THE COVERAGE BEFORE QUOTING THAT.** The export is **3.5 months with 7 entries**, and
**four of the eight refusal codes were never reached at all** — a green gate says the two
implementations AGREE, never that either is RIGHT, and says nothing about a branch neither entered.
The 6.6-year figures in this file were measured on the Python alone and are **not** covered by it.
**Last reviewed:** 2026-09-01

---

## The parity gate — GREEN on a fresh export, and the warm-up was the fault (2026-09-03)

🟢 **GREEN on `engines/VANTAGE_XAUUSD, 5_821a8.csv` — 18,248 bars compared, exit 0**, at the
derived warm-up of 2,016 bars.

🔴 **IT READ AS FOUR DIVERGED FIELDS AND IT WAS ONE COLD-START BAR.** The tool's `--warmup` default
was a flat **1000**, which on a 5-minute chart is ~3.5 days — **less than a week**. The weekly
level had therefore not formed on the Python side, while the chart carries history from before the
export window and already had one. MEASURED family by family over 19,265 compared bars: **exactly
ONE disagreement, in the weekly-high family; h4, session, daily and weekly-low were all 0.** The
other three fields (`px_high_age` for 375 bars, the arming and the family count) all cascade from
that single bar.

⚠ **The `--warmup` help text had predicted this exact failure in writing — *"the weekly level needs
a completed week… too LOW is the failure that wastes a day: it reports a cold start as a logic
bug"* — while its own default was too low to satisfy it.** A warning next to a wrong default is
worth nothing; the default is now DERIVED (`derived_warmup`): one calendar week at the export's own
timeframe, floored at the 1000 that seeds the 15m structure, and only widened when the weekly
family is on. ⚠ **A typed number cannot be right for both frames** — 1000 bars is over a week on
15m and a third of one on 5m.

🔴 **THE DERIVATION WAS INSIDE `main()`, WHERE NO TEST COULD REACH IT, AND ALL THREE OF ITS FIRST
MUTATIONS SURVIVED THE WHOLE SUITE** — two were caught only by one real export on one machine and
the third by nothing at all. It is a function now, with four tests, each watched RED. Same lesson
as the trade box and the period window: **logic with no seam a test can grab is logic nobody
checks.**

⚠ **This does NOT widen what the gate covers.** The export still spans 2026-05-24 → 2026-09-03 with
7 entries, and refusal codes 2, 4, 5 and 7 are still never reached. A green run here is a NARROW
green, and the warm-up growing by 1,016 bars made it slightly narrower still.

## The parity gate — RED, then GREEN the same day (2026-09-02)

✅ **THE SECOND RUN IS GREEN.** `engines/VANTAGE_XAUUSD, 5_29058.csv`, 21,328 M5 bars, 20,327
compared: *the Python made the same decisions as the Pine on every compared bar.* The export was
taken off the regenerated twin, so it is the first one that carries the weekly-level fix below —
**the same window, the same shape, and the ten disagreements gone. That is what confirms the fix,
rather than the argument for it.**

⚠ **WHAT A GREEN RUN HERE DOES NOT SAY, stated before the number gets quoted without it:**
**7 entries, 3.5 months, and refusal codes 2, 4, 5 and 7 never reached once.** Everything this
package has measured over 6.6 years — the trade counts, the R, the two cuts, the clash audit — sits
on bars this gate has never seen. **It proves the port, not the numbers.**

🔴 **THAT COVERAGE IS A CEILING, NOT A FIRST ATTEMPT — STOP CHASING A WIDER EXPORT**
(Aaron, 2026-09-02: *"I gave you as much export as TV allows"*). Both exports taken for this gate
came back at ~21,300 M5 bars over the same ~3.5 months, and scrolling further loads no more history
on that account. ⚠ **Earlier revisions of this very file called a wider export the single most
valuable thing anyone could add to this strategy, which sends the next reader at a door that does
not open.** ⚠ **It does not retire the warning above — it makes the warning PERMANENT.** The
only two routes to wider gate coverage are a COARSER frame (the same Pine on 15m reaches three
times the calendar for the same bar count, but that is no longer the strategy that ships) or a
fresh export taken months from now and read as a NEW window rather than a longer one.

### The first run, and why it was worth reading rather than explaining away

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
it (`engine.py:228`, citing `mpc_jarvis.pine` line 1427) and the lower families on a wick — so
the house engine and the parent indicator agreed with each other and this strategy file was the odd
one out. ✅ **Fixed in `strategies/tradingview/tools/build_extreme_leg.py`** (`f_track` gained a
close-through mode, passed only for weekly). ⚠ **The direction was decided by the house standard,
not by which rule made more money** — same call as the session clock. Do not re-optimise around it.

⚠ **NO PYTHON BASELINE MOVES.** This side already followed the engine; only the chart changed.
Every figure in this file and in `strategies/tradingview/docs/extreme_leg_strategy.md` stands.

🔴 **NOT ONE TRADE DIVERGED — AND THAT IS A NARROWER CLAIM THAN IT SOUNDS.** No entry, stop,
target, fill, R or equity column appears in the diff, so on this window the ten weekly-sweep
differences never reached a position. But the window is **3.5 months, not 6.6 years**, and it
contains only **7 entries**. **Refusal codes 2, 4, 5 and 7 were never reached at all**, so this run
says nothing whatever about them. A green re-run on this same export would still be a narrow gate.

⚠ **The next export must come from the REGENERATED twin.** The one above predates the weekly fix,
so re-running the gate against it will reproduce the same ten bars for ever.

---

## Re-running the gate (stage 4 is the one step only a human can do)

✅ **Done once, green, 2026-09-02** — but it must be re-run after ANY change to either side, and
the export cannot be regenerated by anything here. A human opens
`strategies/tradingview/extreme_leg_strategy_export.pine` on a XAUUSD **5-minute** chart, scrolls
LEFT until the chart stops loading history (the export only holds what the chart has loaded — this
is the lever that widens the narrow coverage above), and takes *⋮ → Export chart data → Bar data and
indicator values*. Then:

```bash
python3 strategies/python/extreme_leg/tools/compare_extreme_leg.py '<export>.csv' --warmup 1000
```

🔴 **A TRADE LIST IS NOT AN EXPORT, and the refusal that says so was UNREACHABLE until 2026-09-02.**
The first real file handed to this gate was a trade list (Strategy Tester → List of Trades), and it
did not refuse — it died with a traceback out of `sos_fade`'s loader saying *export has no
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
`strategies/tradingview/tools/build_extreme_leg.py`, so they cannot drift. Edit the generator, never
either `.pine`. The build asserts the bodies are identical apart from the title and the appended
export block.

---

## The one known disagreement left, and the two that were fixed

Found 2026-09-01 by diffing the Pine against the study that measured this strategy. Three root
causes; the port inherits only the first, and it was fixed on the Pine side.

| | What differed | Where it is now |
|---|---|---|
| **Session clocks** | The Pine read three fixed session strings with **no timezone**, so all three resolved in the symbol's EXCHANGE clock (New York). Two windows tracked no real session; the one labelled "London" was the New York session under a wrong name — its high and low equalled the house NY session's on **100.0%** of 38,747 M15 bars, while the other eight pairings agreed on 0.0–8.0%. | ✅ **FIXED IN THE PINE.** Each window now names its own city, matching `indicators/engines/mpc_jarvis.pine` — which always passed the timezone — and `engines/sessions/`. |
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
It is one of TWO models of the same cost — flat round-trip charge, or moved fills — never a layer
on top, so a run that asks for both is billing the spread twice.

🔴 **THE REFUSAL NAMED THE WRONG DIAL FOR ITS WHOLE LIFE, AND THAT COST A READER A SESSION
(2026-09-02).** It read *"account profile 'lab:puprime_ecn' has bid_ask_fills on … Use a profile
with bid_ask_fills off"*, so the reader went looking at the BROKER. The broker supplies only the
spread's SIZE; the flag is switched on by the run's own cost options
(`python_runner._profile_for`), which means **every account fails identically and no amount of
changing brokers can clear it.** The message now names the run's cost options, says which box to
untick, and says plainly that the spread is still charged — because *"it refuses costs"* was the
other conclusion a reader reasonably drew from it. ⚠ **The generalisation is worth more than the
wording: a refusal that names the wrong dial is WORSE than a bare stack trace, because the reader
trusts it and searches where it points.** A refusal must name the control the reader can actually
move. Pinned by `test_the_refusal_points_at_the_run_option_and_not_at_the_broker_account`, watched
RED by restoring the old string.

---

## Registering in the lab — and what running the scanner found

`LAB_STRATEGY` in `__init__.py` is the whole opt-in; the scanner imports the package and reads it.
MEASURED by actually calling `services.strategy_scanner._parse_python_package` on it rather than by
reading the dict and agreeing with it: **22 settings, 20 of them labelled from
`extreme_leg.meta.json`, 12 marked core, 4 steps, `display_under` honoured.**

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
export column can carry them; the SOS Fade bot exposes the same pair the same way.

## The tests, and what they are worth

```bash
python3 -m pytest strategies/python/extreme_leg/tests -q       # 54 tests
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

## It is a TOP-LEVEL row on the Strategies page, not a child of the SOS Fade bot (2026-09-02)

**Aaron's call, and the reasoning is worth keeping because the version it replaced was not wrong.**
This package declared `display_under: "sos_fade"` until today, on the grounds that the suite is
carved up by LEG off one structure stream and this is the leg BEFORE the one SOS Fade trades. That is
still true. It is still the wrong thing to draw as an indent.

🔴 **AN INDENT READS AS "CHILD OF", AND THIS BOT IS A SIBLING.** It has its own Pine source, its own
parity gate, its own config, and it runs standalone, in any stack, on any instrument. Measured over
6.6 years it holds ZERO same-side overlap with SOS Fade, correlates +0.035 month to month, and on one
shared account the two refuse each other essentially never.

🔴 **What made it misread is that ONE VISUAL LEVEL WAS CARRYING TWO RELATIONSHIPS.** `loss_recovery`
sits under SOS Fade as well and genuinely cannot run without it — it arms off that bot's closed losses and
declares `requires_source`, so the page refuses to run it alone. A row that cannot exist without its
parent and a row that competes with it as an equal were drawn identically, and nothing on screen
separated them.

⚠ **Do not re-add the field without recording why.** Its failure mode is silent in BOTH directions —
a dropped declaration and a typo'd parent both render at the top level, so reversing this decision by
accident would show up nowhere. `command-center/backend/tests/test_strategy_nesting.py` pins it, and
a second check pins that the move took nothing else away (the row must still be standalone-runnable).
Both watched RED by mutation.

⚠ **B-LEG still nests, and that was NOT changed here.** Only the row Aaron asked about moved.
Whether the same argument applies to it is an open question, not something this change decided.

---

## It can share an account now (2026-09-02)

**`backtest/portfolio/run_stack` REFUSED this bot outright until today**, and the refusal was the
right one: its execution layer owned a private balance and entered whenever its own ladder said
yes, so replaying it as a leg would have given it an uncapped account **while the run reported the
risk budget enforced.** Nothing would have raised. The seam is now the same one `sos_fade` has
— `account=None, leg="strat"`, defaulting to an uncapped solo account.

⚠ **Solo behaviour is unchanged and that was PROVEN, not reasoned.** The parity gate was re-run on
the same export after the wiring: still green on all 20,327 compared bars, so not one decision
moved. Every 6.6-year figure in this file still describes the same strategy.

**Five points carry the seam, and each one fails silently if it is dropped:**

| | what it does | what breaking it looks like |
|---|---|---|
| the balance is a PROPERTY, never a stored number | solo → own ledger; stacked → the shared one | solo run fine, every stacked run quietly sizes off a stale balance |
| the entry asks before it opens | the account scales the size down to the room | the position appears, the cap is breached, nothing reports it |
| breakeven reports the new stop | risk is reserved to the CURRENT stop, so the room comes back | the cap binds on risk nobody carries and the other leg is refused affordable entries |
| close books P&L **and** frees the reservation | two calls, because money and budget are separate | balance right, budget permanently spent, the account slowly grants nothing |
| it can say whether it is flat | the simulator steps a holding leg FIRST, so closing frees room before the other is sized | room that just came free is silently denied |

🔴 **AN ACCOUNT REFUSAL IS DELIBERATELY NOT A REFUSAL CODE.** Those codes are the decision stream
the parity gate compares against the chart, and a portfolio refusal is a decision made ABOUT this
strategy rather than BY it. Writing one there would put a Pine-less value in the one stream that
has to stay comparable, and the gate would then report a divergence at a real bar and send the
reader hunting a porting bug that does not exist. The account's own contention log is where a stack
reader looks — it timestamps every refusal and every shrink.

⚠ **8 mutations watched RED, each on exactly its own test** (the balance one reddens two, correctly
— solo and stacked). A stub account that granted whatever it was asked would have passed all ten
tests while describing an account nobody has, so they are written against the real
`PortfolioAccount`.

### What it does stacked against the live SOS Fade bot — MEASURED 2026-09-02

470,995 PU Prime `XAUUSD.p` M5 bars + 157,004 M15, one $10,000 account, 10% cap.
**At a matched 5% per trade each: +190.30R together, and every leg posts the SAME R shared as solo
— zero contention, not one decision moved.** At the two configs' own defaults (10% and 1%) it is
+191.30R with the budget binding twice in 6.6 years.

🔴 **READ THE RISK COLUMN BEFORE THE R COLUMN. The first mixed stack ran SOS Fade at 10% against this bot
at 1% — a 10:1 gap that came from each config's default and that the tool printed NOWHERE.** The
bigger leg then fills the budget alone and the smaller one reads as harmless, which is a fact about
the SETTINGS and not about the strategies. `stack_run.py` prints per-leg risk now and `--risk-pct`
matches them. 🔴 **THE PLACEHOLDER IS GONE: `exec_risk_pct` is 5.0 as of 2026-09-02, Aaron's
explicit call.** This line read *"1.0 is a placeholder, not a measurement — nothing here has chosen
it"*, and now something has.

⚠ **What that change moves, and what it does not — CHECKED against the code path rather than
assumed.** `_qty` scales the lot and the only size refusal beside it tests finite-and-positive, so
**solo it cannot change a single decision**: every trade count and every R figure in this file
stands, and so does the clash audit, which replays each bot off its OWN equity. **Every STACKED
figure moves**, because a shared account grants `granted` rather than `qty`. ⚠ **The mixed stack
above is now 10% + 5% against a 10% cap** — the "zero contention" row was measured at 5% for BOTH
legs, which saturates that cap exactly, and 10 + 5 does not fit it at all. Re-run before quoting it.
⚠ **The parity gate is unaffected and that was checked, not reasoned**:
`compare_extreme_leg.config_from_export` builds the port's config from the export's own `cfg_*`
columns and never reads this side's defaults.

⚠ **Two legs at 5% each SATURATE a 10% cap exactly**, so "no contention" above sits on a knife
edge rather than describing headroom. Anything higher and they start refusing each other.

⚠ **A shrunk entry is INVISIBLE IN R.** R is measured against each trade's own risk, so a trade cut
to half size reports the same R — the SOS Fade leg's shared and solo R are identical despite being
shrunk once. This repo's standing rule is to compare R rather than dollars, and this is the one
place R cannot see what the cap did. Read the contention log for that.

⚠ **The SOS Fade leg in ANY stack is not the live SOS Fade**: its 1-minute re-entry is pinned off, because a
leg is one bar frame. Its figures here sit below the live bot's by construction.

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

✅ **THE CLASH AUDIT WAS RE-RUN THE MOMENT THE CUT WENT ON (2026-09-02), AND THE ANSWER HOLDS.**
Switching it on drops 19 trades, so the previous day's figures stopped describing this bot within a
day of being written. Re-measured over the same 470,995 PU Prime `XAUUSD.p` M5 bars: **1,049 shared
bars** with the live SOS Fade bot — 3.5% of SOS Fade's hold time, down from 1,066 / 3.6% — of which **ZERO are
same-side**, 6 trade pairs touch at all, none same-direction, and no same-direction entry lands
within four hours of the other's in 6.6 years. Monthly R correlation +0.035 over 79 months.
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

---

## What the CHART draws: entry, DD, best, exit (2026-09-02)

🔴 **THIS BOT'S TRADES DREW AS A FLAT BOX WITH NOTHING ON IT, AND NOTHING ANYWHERE REPORTED THAT.**
`backtest/output.py` reads the chart's rich fields off the trade with a `getattr` DEFAULT, so a
strategy that records none ships zeros and the price chart **degrades in silence** to a plain
entry→exit rectangle. Its own comment says so out loud — *"All optional — a runner/trade that
doesn't carry them degrades to the plain entry→exit box"* — and this bot was the one hitting it.
Aaron, looking at two of its trades beside the SOS Fade bot's: *"they should be the exact same style as
sos fade trades and annotations where applicable."*

**MEASURED on all 115 trades of run `29444bb4cbea` before the fix**: the best price, the deepest
price, the exit-fill ledger and the target ladder were empty on **every single one**; only the stop
was recorded. So the chips built from them — best, deepest, the exit marker, the target lines — had
nothing to draw from, and the faint bands that make an SOS Fade trade read as layered had no extremes to
span.

⚠ **It is the ONLY strategy here that was affected, and that was CHECKED rather than assumed.**
`b_leg`, `bos` and `realign` all SUBCLASS `sos_fade`'s execution layer and inherit
its recording; `loss_recovery` records its own. This bot is the only one with an execution layer of
its own, which is exactly why it is the only one that had to be taught separately — **a fact worth
carrying forward: the next strategy with its own execution layer starts here too.**

**What it records now, all of it REPORTING ONLY:** the best and worst price of the hold
(`mfe_price` / `mae_price`, plus their dollar twins), the exit as a real FILL rather than as an
average, and its single target as a rung that banks 100%.

✅ **PROVEN NOT TO HAVE MOVED A TRADE, rather than argued.** The decision stream was digested over
**189,331 M5 bars** (PU Prime `XAUUSD.p`, 2024-01-01 → 2026-09-01) before and after: **51 trades and
174 refusals, byte-identical sha both sides.** ⚠ **The digest is `sha256` over the serialised
stream, NOT python's `hash()`** — string hashing is randomised per process, so two `hash()` values
disagree on identical code, and the first attempt here did exactly that and read as a real
difference.

### The three rules that decide what those numbers MEAN

🔴 **NEITHER EXTREME MAY SIT BEYOND A LEVEL THAT CLOSED THE TRADE.** The widen runs before the
bar's exits resolve, so the raw range includes price *after* the position is flat — and the chart
draws these as its `DD` and `Best` chips, so an unbounded extreme puts a marker outside the trade's
own stop or target line. **MEASURED on the SOS Fade bot when it hit this: 77 of 77 stopped-out trades
reported a deepest price beyond their stop, one of them 2.22R against a 1.0R loss.** It is not an
intrabar-ordering guess — a bracket is triggered BY the move that reaches it.

⚠ **BOTH sides are bounded here, and that is the one place this differs from the SOS Fade bot.** There the
favourable side is deliberately left alone, because its first target is PARTIAL and the runner stays
open, so price beyond it is still the trade's move. **This bot's target closes the whole position**,
which makes the favourable side determinate in exactly the way the adverse side is. ⚠ **Copying
either bot's shape onto the other is wrong in both directions.**

⚠ **The bound is the bracket AS IT STOOD ON EACH BAR, never the price the trade finally exited at.**
A trade that sits deep, recovers far enough to arm breakeven and then scratches really did trade
down there, and that is the single most useful thing its chart can show. Clamping at close instead
collapses that drawdown to the exit and the trade reads as though it never went against you.

⚠ **The entry bar contributes NOTHING, and that is a fact about this entry rather than a
simplification.** This bot enters at market on the bar's CLOSE, so no part of that bar's range
happens after the fill — none of it is the trade's move, and both extremes seed AT the fill. The SOS Fade
bot seeds asymmetrically for the opposite reason: its entry is a resting limit filled mid-bar, so
the rest of that bar IS its move.

⚠ **Best and worst are resolved by DIRECTION, not by which number is larger** — a short's best price
is its low. Getting it inverted puts both chips on the wrong side of the entry and nothing raises.

⚠ **Recording the exit fill matters even though it equals the average here.** This bot closes in one
piece, so the two are the same number — but a leg list is how the chart is told the fills are
KNOWN, which is a different statement from having none, and it draws the exit at a fill rather than
at an average of one.

⚠ **The target's 100% is not decoration.** `backtest/output.py` uses it to tell a real profit target
from a level that banks nothing and only steps a stop; a rung reported without it is drawn as an
unknown rather than as a target.

⚠ **A run finished before this landed carries none of it, and there is no backfill** — recovering
the numbers means replaying the strategy. Re-run it. A run that HAS them but a cached `chart_spec.json`
needs **Reload charts**.

## Its chips say XLEG, not SOS Fade (2026-09-02)

`LAB_STRATEGY["chart_tag"]`. 🔴 **The price chart hard-coded `SOS Fade` — the SOS Fade bot's own word for ITS
setup — onto every strategy's primary trades**, so this bot's trades wore a label belonging to a
different bot. The panel's own comment had named the cost and the fix since it was written; this is
that fix. ⚠ **A LABEL and nothing else** — no run, no cost and no decision reads it, so changing it
repaints chips and moves no trade. ⚠ **Keep it SHORT**: it is drawn in a chip beside the entry price
and a long word pushes the price off the marker. ⚠ **Undeclared is still `SOS Fade`**, because a package
that has not declared one must not lose its chip entirely — so a chart reading `SOS Fade` now means
EITHER the SOS Fade bot or a strategy that has yet to declare its own word.

---

## It can be a LIVE bot now — the seams, and why they cost the replay nothing (2026-09-03)

**This package satisfies `strategies/python/live_contract.py`.** `verify_live_ready()` returns an
empty list; before today it named four missing things and this strategy could not be a bot at all.

🔴 **NOT ONE TRADE MOVED, AND THAT IS MEASURED RATHER THAN ARGUED.** 470,995 PU Prime `XAUUSD.p`
M5 bars, 2020-01-01 → 2026-08-23, default config: **113 trades, digest `e4183861407c6b1e`, before
and after.** Every 6.6-year figure in this file still describes this strategy. ✅ **Parity gate
re-run and GREEN** on `engines/VANTAGE_XAUUSD, 5_29058.csv` with the seams in place.

⚠ **The replay cannot reach any of it, and that is the design rather than a happy accident.** The
per-bar `step`, the position snapshot and the commanded close are only ever called by `algos/live/`;
the one flag that could change an exit is set exclusively by `request_close`, which nothing in the
backtest path calls. **A test asserts that flag starts `None`, and the digest proves the rest.**

**What was added, and the rule each one carries:**

| seam | the rule |
|---|---|
| `signals` / `sequence` | Honest EMPTY stages. The runner drives three; this strategy decides in one. **Splitting its logic to suit the caller would be rewriting the strategy.** |
| `step(sig, seq)` | DELEGATES to `strategy.step` and adds nothing but a report. The four calls per bar are sequenced there, in an order that is part of the strategy — re-sequencing here would be a second implementation of what the gate checks. |
| `request_close` | ARMS a request; `resolve` exits on the next bar through the path a stop or target already takes. **No second closing path.** Refuses while flat rather than latching onto a trade nobody had an opinion about. |
| `snapshot_position` / `restore_position` | Via `LivePositionMixin`. Restore REFUSES an incomplete record — a record missing a field is not a position at the default. |
| `_pos_dir` / `_entry` / `_pend_*` | Read DIRECTLY by the bridge. `_entry` is `None` while flat, never 0.0 — that is a price. |

🔴 **`_EXIT_TAGS` IS A LIVE-BEHAVIOUR DECISION WEARING A NAMING TABLE'S CLOTHES.** The tag's SUFFIX
decides whether the bridge acts. **A target MUST be owned** — this bot sends no broker take-profit
and manages its own target, so nothing else would ever close the position. **A stop must NOT be** —
it is already an order resting at the broker, and mirroring it sends a market close on top of a
stop that is already filling. Both directions are pinned by tests that read the bridge's own list
from source. ⚠ **An exit reason this table has never heard of falls back to a tag the bridge OWNS**,
which is the safe direction: a halt at worst, rather than a position nobody closes.

⚠ **The account-budget seam was ALREADY here and is untouched** — `enter()` has asked the account
before opening since 2026-09-02, and it clamps at the DECISION, before any order exists. That is
the coherent side of the rule the SOS Fade bot had to be moved onto.

⚠ **`_POSITION_FIELDS` is one entry today because the whole position is one object.** A latch added
BESIDE `_Open` rather than inside it would be dropped by a restart in silence. The test compares the
record against `_Open`'s own fields so that day fails loudly.

🔴 **NOTHING HERE HAS RUN AGAINST A BROKER. Rule 9.** What changed is that the blockers are gone,
not that it is deployed. ⚠ **It HAS an instance directory since 2026-09-03** —
`algos/markets/fx/instances/extreme_leg_demo/`, registered and BENCHED (`account: null`), so it
trades nothing and the runner refuses to start it. The rules for that file live beside it in
`algos/CLAUDE.md`; the two that reach back into this package are the frame (**M5** — on M15 the
trigger and the target collapse into one series and it never fires) and the fact that
`skip_transitioning` is ON in its params, which is the half no parity gate can ever check.

### It DECLARES that it enters at market, and without that it could not open a position at all

`entry_style = "market"`, read by `algos/live/` and by nothing else — no replay, no cost and no
decision reads it, and the digest above is unchanged with it in place.

🔴 **IT IS THE ONE THING THAT SEPARATES THIS BOT FROM A BROKEN ONE, AND NOTHING OBSERVABLE COULD
HAVE TOLD THEM APART.** `enter()` fills inside this emulator DURING the step, so by the time the
bridge reconciles, the position exists here and the broker holds nothing. For a strategy that rests
a limit, that state means the limit filled in one book and not the other — the 2026-08-07
divergence — and the bridge must HALT. Here it is one instant old and the bridge must place the
order. **Same position, same direction, same entry fill on the decision, same empty broker book.**
So the bridge asks; it does not guess. Rules: `strategies/CLAUDE.md` → *Every order layer DECLARES
how it opens a position*.

⚠ **The bridge's own fallback is `"resting"`, i.e. the HALTING one.** A typo here does not disable
a feature — it stops the bot on its first setup. `verify_live_ready` refuses an unrecognised value
by name at startup so that fallback stays a backstop.

⚠ **It does NOT mean this strategy sizes its own live order.** The broker's lot count still comes
from the live sizing seam, off the BROKER's balance and under the account's remaining risk. What
this decides is which ORDER is sent.

🔴 **THE BOT MUST NOT BE GIVEN A SECOND BAR STREAM.** The bridge mirrors a market entry on the
primary clock only; a fill clock would reach the same disagreement with no path to open it and
halt. It has no re-entry to ask for one, and the bridge REFUSES the combination rather than
running one clock inert.

**Tests: 18 in `tests/test_live_seams.py`, 9 mutations watched RED.** ⚠ **They parse
`BRIDGE_OWNED_EXITS` out of the bridge's source rather than importing it** — importing
`algos.live.bridge` from a strategy test drags in the whole live import graph, and this repo already
forbids the reverse coupling for the same reason.

## Never do

- Quote a number from this package as a measurement before `compare_extreme_leg.py` exits 0.
- ⚠ **Or read the green run of 2026-09-02 as covering the 6.6-year figures.** It compared 3.5 months
  and 7 entries; every headline number here was measured on bars it never saw. The gate proves the
  PORT, not the numbers, and those are different claims.
- Allow a second concurrent position. Every result this strategy has was measured with one slot,
  and the reason a filter pays here is that refusing a setup genuinely buys the next one.
- Fork `engines/liquidity/` or `engines/sessions/` to make this side agree with a Pine. When they
  disagree, one of them is wrong and the gate says which — see the table above for how that went.
- Add a field to `ExtremeLegConfig` that has no Pine input behind it. No `cfg_*` column can carry
  it, so the gate would leave it at this side's default and never see a disagreement about it.

## The frame it is measured on is DECLARED (2026-09-03)

`LAB_STRATEGY["suggested_bar_value"] = 5` — its Pine is exported from a 5-minute chart and its gate is 21,328 M5 bars. The lab reads it and every form fills a leg's
timeframe box from it, so nobody has to remember which bot runs on which frame.

⚠ **It is a DEFAULT, never a refusal.** Nothing rejects a run on another frame — sweeping a bot
across frames is a real question — so a figure quoted off a different frame is a DIFFERENT
EXPERIMENT from every number in this file, and has to say so.

🔴 **Why it had to be declared: the stack page had ONE timeframe for the whole stack**, so a 5m
bot and a 15m bot on one account meant one of the two was replayed on a frame nobody has ever
measured it on — and the combined table said *portfolio*. Rules for the lab side:
`command-center/backend/CLAUDE.md` → *A stack leg runs on its own frame*.
