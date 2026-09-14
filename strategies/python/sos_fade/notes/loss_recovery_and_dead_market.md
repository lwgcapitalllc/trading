# Notes — Loss recovery and the dead-market floor

The loss-recovery toggle's own property and cost story, the dead-market ATR floor, and the leg-latch performance fix. Moved VERBATIM out of `strategies/python/sos_fade/CLAUDE.md` on 2026-09-13 so it loads only when
needed; nothing was reworded or dropped. **New detail on this topic goes HERE**, and the
CLAUDE.md gets at most one index line.

---

## Loss recovery — the toggle, and the one property it must never break

Detail, tables and run numbers: `docs/SOS_FADE_BUILD_NOTES.md` → *Loss recovery — the toggle, and the one property it must never break*.

🔴 **Turning it on cannot move one SOS Fade trade, and a test pins that.** The recovery reads SOS Fade's
finished losses and appends rows tagged `kind="recovery"`; it never gates, delays or re-sizes an
SOS Fade entry. That is what makes it safe to ship a lab-only toggle on the LIVE bot's config class — a
feature that could rewrite the shipped book would put every parity number and every figure in
`sos_fade_optimization.md` at the mercy of a switch. `test_turning_it_on_cannot_move_one_aplus_trade`
is the one to keep green; it was watched red by having `apply` re-size a source trade.

🔴 **The cost of that choice was called "slight" here until it was measured, and it is most of
the result (2026-08-20, run `236e206d0142`).** The recovery sizes off the RUNNING balance (every
SOS Fade and earlier recovery trade already closed is in it); SOS Fade does not size off the recovery. **They
share a balance in ONE direction only**, so recovery profit sits BESIDE the curve instead of
lifting it and never compounds. Identical trades, added up two ways: **+3.8% as the lab runs it
against +59.9% on one shared compounding balance.** ⚠ **Neither is this rule's worth.** The
larger figure also assumes one balance with NO risk budget on it; at the 10% account cap this bot
already runs, 23 of that run's 160 SOS Fade entries opened while a recovery was still holding risk and
the leg turns NEGATIVE. **The honest range is +45% to −15%, decided by an allocator that does not
exist on the live side.** Full bracket: `strategies/python/loss_recovery/CLAUDE.md` → *Put ONE RISK
BUDGET on that balance*. It is NOT a shared-account run — `backtest/portfolio/`
is what one of those looks like.

🔴 **`finalize(df)` is a hook three separate drivers have to call, and a missed one is silent.**
`run()` and `run_dual()` call it. Anything that steps bars itself must too: the lab's
`python_runner._replay` and `backtest/optimizer.py::_replay_one` both reproduce the bar loop rather
than calling `run()`, so neither inherits it. A driver that forgets does not error — it reports a
book with the recovery trades missing, which is rule 7 exactly (the toggle is a CLAIM about code
somewhere else). Idempotent via a `_recovery_applied` flag on the strategy.

⚠ **Idempotence is a FLAG, not "are there recovery rows in the book".** Inferring it from the rows
made the `kind != "recovery"` source filter unreachable — a book carrying one returned before that
line, so no test could redden it. Dead code that reads as load-bearing is worse than none.

⚠ **`r` on a recovery Trade is that trade's own R**, so `pnl_usd / risk_usd` reproduces it exactly
as on every other row. The quarter-sizing is carried in the DOLLARS (`risk_usd` is a quarter of a
normal trade's), which is what makes the equity curve right without giving one row's R a different
meaning from its neighbour's. Do not "fix" this to `scaled_r`.

🔴 **A recovery row carries its EXCURSION, and it had to be added — the chart was drawing these
as bare rectangles (2026-08-20).** Every reporting field a chart reads is optional by design, so a
trade that carries none degrades to a plain entry→exit box; that fallback exists for an NT8/MT5
trade with no fill prices in it at all. The first version of this adapter left `mfe_price` and
`mae_price` at their `0.0` defaults, so **every recovery trade took that path** and appeared beside
a normal loser — which was wearing entry, stop, both excursion bands and its outcome chip — as a
featureless green block. **It read as a different KIND of trade and it was the same kind of trade
with a thinner record.** The general rule, and it is the one this repo keeps relearning from the
other direction: **an absence rendered as a distinct shape becomes a claim.** A missing measurement
must degrade into something that reads as *less information*, never as *a different answer*.

✅ **The outcome CHIP grades a recovery correctly, checked rather than assumed.** The verdict comes
from the run's scratch band, which is scaled to a full-size loss — so a quarter-size trade could
plausibly have been painted orange all the way down. It is not: over the **62 recoveries of the
UNCOSTED run** on the window below — see the cost-tier note under it before comparing that count
with the 65 — **26 of 26 losers grade `Lost` and none grades `Scratch`**, because the band is a
fraction of the run's median loss rather than a fixed dollar figure. ⚠ Worth re-checking if the size
knob is ever taken far below a quarter.

⚠ **Both excursion prices are stepped off the recovery engine's OWN R figures, never re-read from
the bars.** The engine already measured them, on the same bars, with the exit-bar cap that keeps
them inside what the trade lived through — a second reading here would be a second answer free to
disagree with the first. `max_adverse_r` was added to that engine for this; `max_favourable_r` was
already there. **A recovery row carries no target ladder and no fib leg, and both absences are
real** — the rule has no targets and prices nothing off a fib — so the chart correctly draws no
`TP1`/`TP2` on one.

⚠ **No Pine twin exists**, so `compare_strategy.py` can never gate this. With the toggle OFF the
bot is byte-identical to the gated one — which is why it defaults OFF, and why an export made with
it ON is not a parity input.

### 🔴 The toggle's warning text was WRONG in the direction that flatters the rule (rewritten 2026-08-21)

Detail, tables and run numbers: `docs/SOS_FADE_BUILD_NOTES.md` → *🔴 The toggle's warning text was WRONG in the direction that flatters the rule (rewritten 2026-08-21)*.

1. **"Does not model one account" overstates the defect.** Half the sharing is real — a recovery
   trade IS sized off a balance carrying every SOS Fade trade that had closed by then (`recovery.py`'s
   heap walk). What is missing is the way BACK: SOS Fade never sizes off the recovery. Saying neither
   direction works sends the reader looking for a bug that is not there.
2. **"Added AFTER the main book is finished"** describes the PASS correctly and reads as though the
   rows are appended at the end of the timeline. They are interleaved by entry bar.
3. 🔴 **+44.8% was the most optimistic row of a bracket the same measurement calls a BRACKET, and
   it is a RE-PRICE rather than a replay.** The real leg replayed on one balance under one 10%
   budget — the cap this bot already runs — measures **−29.9%** ($13,199,534 → $9,251,114 over
   186,910 M15 bars). **So the warning pointed the reader at "the real answer is much better" when
   the measured answer at the shipped cap is negative.** Both numbers are in
   `strategies/python/loss_recovery/CLAUDE.md`; the desc quoted the wrong one.

✅ **Rewritten to describe the MECHANISM and carry no figures at all**, which is also this file's own
house rule (`_comment` → COPY STYLE: no measurement dumps, no counts, no dates). It now says the
printed result is wrong in BOTH directions, names which half understates (profit that never
compounds) and which half flatters (nothing competes for one risk budget), states that the rule
loses money at the cap this bot runs and only pays on risk the main bot is not using, and points at
`backtest/tools/recovery_stack.py` and the package CLAUDE.md for the numbers.

🔴 **The standing lesson is about WHERE a number lives, not about this switch.** The stale figure
was in a UI string nobody re-measures, four files away from the table that would have corrected it.
**A warning that carries its own numbers goes stale silently and keeps being read as current** —
put the direction in the warning and leave the arithmetic in the doc that owns the measurement.

**13 tests in `tests/test_recovery.py`, all watched RED by a named mutation** (the mutation is in
each docstring). ⚠ **A fourteenth was written for the excursion cap, watched STILL-GREEN, and
deleted** — every recovery in the synthetic fixture exits LOCKED and in profit, so the mutation it
named changed nothing. The assertion now lives in `loss_recovery/tests/test_engine.py` as a direct
two-bar `_manage` call, which is the only shape where the ordering is observable.

⚠ **Quote the COST TIER with the recovery count or the number looks like a regression.** The rule
arms on a real loss, and a cost tier moves a borderline scratch across that line — same bars, same
window, same settings: **uncosted gives 62 recovery trades and `puprime_ecn` gives 65**, because
the primary's real-loss population goes 62 → 65 with the friction charged. Nothing changed in the
rule between those two runs.

## The DEAD-MARKET floor — `exec_min_atr_pct` (2026-08-26, ON at 0.08)

Detail, tables and run numbers: `docs/SOS_FADE_BUILD_NOTES.md` → *The DEAD-MARKET floor — `exec_min_atr_pct` (2026-08-26, ON at 0.08)*.

🔴 **READ ITS DRAWDOWN, NEVER ITS R, AND THE REASON GENERALISES TO EVERY ENTRY FILTER HERE.** Across
off / 0.08 / 0.10 the drawdown falls in order (55.5% → 47.9% → 41.5%) and the R does not (119.0 →
127.9 → 114.4), swinging ±8R on a 0.01 nudge. With one position slot, refusing a setup changes
which LATER trade gets the slot, so total R and the ending balance are a reshuffle; **removing
losing stretches is what survives the reshuffle.** The smoothness measure bottoms at 0.08.

🔴 **ORDER AN EQUITY PATH BY EXIT TIMESTAMP, NEVER BY BAR INDEX — this trade list mixes two
clocks.** A 15m setup carries a 15m index and a re-entry a fill-clock one, so an index sort puts a
2026 setup before a 2021 re-entry. **A SUM is order-independent, so the ending balance and the R
total come out byte-identical either way and give no signal at all**; only the path-dependent
numbers are wrong, and they are the only ones anybody reads. Refuse when the timestamp was never
populated rather than falling back to the index.

🔴 **"IT OVERRIDES THE METHOD" IS A CLAIM ABOUT ONE CALL SITE — FIND THE LINE THAT CONSUMES THE
VALUE.** The gate rides inside `_stop_clears_floor` because TWO entry paths call it (the 15m setup
and the re-entry's own fill clock), and a filter guarding one path is how a refused setup gets in
through the other door. `bos` defines its own `_place_entries` and still calls that shared
check from inside it (`bos/execution.py:401`), so it would have acquired a volatility filter
with **no error, no failing test and no Pine input to catch it**. All three forks now PIN it off
with the reason attached.

⚠ **An unseeded ATR REFUSES rather than passes** — the first 14 bars cannot answer *is the market
quiet*, and a gate whose silence reads as approval on the bars it knows least about is rule 1.

✅ **PORTED TO THE PINE THE SAME DAY** (`execMinAtrPct` + `f_marketHasRange`), with a `cfg_min_atr`
column in the export twin and the decode in `compare_strategy.py` — so this is **not** another
Python-only field the gate is structurally blind to. ⚠ **The Pine gates the 15m setup path only,
because that is the only entry path Pine has**; the re-entry is Python-only and has nothing to be
compared against. ⚠ **The Pine input is APPENDED after the last `input.float`** rather than sitting
beside the stop floor it belongs with, because declaration order is what TradingView keys a saved
chart's values off.

🔴 **ON AT 0.08 ON BOTH SIDES (Aaron's call, 2026-08-26), SO THE SHIPPED BOOK IS 240 TRADES AND
NOT 245.** It landed OFF earlier the same day and was switched on once the run was read — the
switch and the value were two separate decisions and the history is kept that way on purpose.
⚠ **PIN IT TO 0.0 TO REPRODUCE ANY BASELINE IN THIS FILE MEASURED BEFORE TODAY.** Not a formality:
the floor removes 5 entries, and with one position slot a removed entry changes which LATER setup
gets the slot, so a stored figure does not merely shift by the refused trades' R.
⚠ **The live bot does not have it until somebody PROMOTES.** ✅ **The SOS Fade/B-LEG overlap audit was
RE-RUN on 2026-09-01** against the shipped 240-trade book, discharging the stale reading measured
on the logic that took 245: **45 shared bars in 157,004, ZERO of them same-side**, monthly r
+0.072. Figures and caveats live in ONE place — root `CLAUDE.md` → *Trading Philosophy*, with the
gate record at `docs/LIVE_TRADING_PIPELINE.md` → G14. ⚠ **It has now gone stale TWICE by not being
re-run at the moment the inputs moved. Re-run it inside the change that moves them.**

✅ **RULE 22 IS SATISFIED (2026-08-26), AND IT TOOK TWO EXPORTS — THE SECOND ONE IS THE PROOF.**

🔴 **THE FIRST RUN WAS GREEN AND PROVED NOTHING ABOUT THIS FEATURE, AND ONLY A COVERAGE CHECK
COULD HAVE TOLD YOU.** At the shipped 0.08 the floor refused **nothing** on that window: replaying
its own bars with the floor OFF gave the same 26 trades and the same +29.06R. **That is not bad
luck, it is arithmetic** — the floor refuses 5 setups in 6.6 years, so an 11-month export expects
about 0.2 of one. A shipped-value export can never gate this.

⚠ **So export at a value that FIRES, then put the chart back.** It is the identical code path, and
it is the move the time stop already documents (shipped at 36 hours, exported at 4). Measured on
these bars: 0.08 and 0.10 refuse nothing, 0.20 refuses 6, **0.30 refuses 17–21** — the spread is
because the two exports are not the same bar set. **Re-export at 0.30 after any change here.**

🔴 **AND THE REASON A REFUSAL IS INVISIBLE IS WORTH KNOWING BEFORE SOMEBODY LOOKS FOR IT IN THE
DECISION STREAM: this gate emits NO block code on either side, deliberately** — `_stop_is_tight`
excludes it, matching Pine's `lBlkTight`, so a refused setup is untagged and shows up only as an
entry that is not there. **A coverage check here therefore cannot read a counter; it has to replay
the same bars with the floor off and diff the entries.** Four lines, and it is the only thing
standing between a green run and a false claim.

⚠ **What stands in meanwhile is deliberately weak and its own docstring says so**:
`test_the_PINE_side_ships_the_SAME_value_and_still_gates_both_entries` reads the Pine source and
pins that the two defaults are the same number and that both entry placements carry the gate. **It
would pass against a Pine whose comparison ran the wrong way round.**

**TESTED:** 10 in `tests/test_dead_market.py`, watched RED against HEAD and re-proved BY MUTATION,
because "the field is new" cannot tell a working gate from a present one. ⚠ **Turning it on broke
71 pre-existing tests and not one was a defect** — those fixtures feed two to four bars, so the ATR
never seeds and the gate refuses by design. **They were fixed by having each DECLARE its basis, not
by teaching a fixture to fake an ATR** — a fixture more capable than production describes a system
you do not have.

## 🔴 The leg latch's bar-time map was re-sorting 20,000 keys EVERY BAR (fixed 2026-08-26)

Detail, tables and run numbers: `docs/SOS_FADE_BUILD_NOTES.md` → *🔴 The leg latch's bar-time map was re-sorting 20,000 keys EVERY BAR (fixed 2026-08-26)*.

✅ **A dict preserves INSERTION order, `step` inserts one strictly increasing index per bar, and
the map is rebuilt empty on every restart (it is deliberately NOT in `_POSITION_FIELDS`) — so the
earliest-inserted key IS the smallest key** and `next(iter(...))` is the same answer the sort was
recomputing from scratch. O(n log n) per bar became O(1).

⚠ **The equivalence is a fact about the ORDER keys arrive in, so `_bar_ms_ordered` CHECKS it
rather than trusting it.** Any out-of-order or repeated index latches the flag False and the
original sort takes over, which is correct at any order. The latch is deliberately one-way:
re-arming it would be a second claim about the same thing.

✅ **Same keys survive, so no decision can move — PROVEN ON REAL BARS**, 62,468 of them, both
algorithms giving a byte-identical 66-trade book (`0c4250ab`).

🔴 **THE FIRST VERSION OF THAT PROOF WAS VACUOUS AND THE TIMING IS WHAT CAUGHT IT.** The script
patched `Execution` imported by package path; **the lab instantiates a DIFFERENT class object
loaded from the same file**, so the patch hit nothing, both runs took the new path, and
`TRADES IDENTICAL` was a run compared against itself. Nothing in the verdict looked wrong — the
tell was that the supposedly-slower run came out FASTER, which no amount of machine noise
explains. ⚠ **Patch `type(strategy.execution)`, never the imported name**, and this is the same
double-load this file already records under the 2.5× sweep arm that silently replayed stale code.
⚠ **A performance number is a CHECK on a correctness claim here, not just a headline** — the
identity result alone could not tell the two apart.
