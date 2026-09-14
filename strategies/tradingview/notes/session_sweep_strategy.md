# Notes — The session-sweep strategy

The full write-up of the session-sweep strategy (`smc_session_sweep_strategy.pine`, formerly `m15_playbook_strategy.pine`): its export twin, the sweep-reclaim idea that was built and abandoned the same day, and every rule the 2026-08-14/15 build pass left behind — defaults, tooltips, stripped comments, the trade overlay, the MISSED/BLOCKED distinction, the structure-shift marks, the liquidity-gap gates, and the open questions on step ordering. Moved VERBATIM out of `strategies/tradingview/CLAUDE.md` on 2026-09-13 so it loads only when
needed; nothing was reworded or dropped. **New detail on this topic goes HERE**, and the
CLAUDE.md gets at most one index line.

---

## The session sweep gets an EXPORT TWIN, stage 3 of six (2026-08-17)

`smc_session_sweep_strategy_export.pine` — the parent byte-for-byte, plus one appended block of
59 transparent `editable = false` plots. It draws nothing and trades identically; the series exist
only to leave the chart through *Export chart data*. Built because Aaron asked for a Python port
and a sweep, and **`docs/STRATEGY_WORKFLOW.md` stages 3 and 4 did not exist for this file** — the
two CSVs already on disk are TRADE LISTS, which is the right idea and the wrong artifact: the gate
compares per-bar DECISIONS, not fills.

🔴 **PINE ALLOWS 64 PLOTS PER SCRIPT AND THE PARENT ALREADY SPENDS 2. The first draft was 70 and
would not have compiled** — a ceiling you meet on Aaron's screen, one paste cycle later, not here.
**What got cut is the rule worth keeping: only things that can MOVE A TRADE are exported.** The
comparison-timeframe stream (`cmpDir`, `cmpShifts`, `sosCmpTf`), the SOS marker price and the
confirmation LEVEL are annotation — a parity failure over any of them would be a failure over a
chart drawing. Everything DERIVABLE went too: position size is quantity × direction, the leg id is
the `newLeg` bit counted up. Small integer inputs are packed two to a plot, safe because each
field's `minval`/`maxval` bounds it below its neighbour's multiplier.

🔴 **THE REFUSED SIDE IS EXPORTED, NOT JUST THE TAKEN ONE** (`px_ent_l`/`px_ent_s`, `px_blk_l`/
`px_blk_s`, both zone pairs, both distances). **A port that agrees on the trades and disagrees on
the refusals will diverge the first time an input moves — which is exactly when a sweep is
running.** Gating on fills alone would pass a port that is wrong everywhere the shipped config
happens not to go.

⚠ **A STRING CANNOT CROSS A CSV**, so the session and hour windows are exported as the DECISION
they produced (`inAsia`, `inWinLdn`, … packed into `px_state`) rather than as their text. That is
the better half of the trade: the port is gated on what the window DID, not on whether it parses
`"0200-0500"` the same way, so a timezone bug shows up as a disagreeing bit instead of hiding
behind two strings that match.

⚠ **`*_shifts` IS A COUNTER AND THE TWIN EXPORTS IT AS ONE.** A boolean read back through
`request.security` stays true, so "it JUST shifted" is only recoverable by comparing the count with
its own previous bar. A port that exports or consumes a flag confirms on every bar after the first.

⚠ **THE TWIN IS A SEPARATE TRADINGVIEW SCRIPT AND STARTS AT THE FILE'S DEFAULTS, not at whatever
is saved on Aaron's chart.** That is why every trade-moving input is in the CSV: the harness reads
`cfg_*` and states the config it was gated at rather than assuming one. ⚠ `execFixedQty` is
deliberately absent — a sweep never leaves "Risk % of equity", and `cfg_enum1` carries the MODE, so
a CSV taken in Fixed-contracts mode is DETECTABLE and can be refused rather than silently gated on
a size the harness cannot see.

## The sweep-reclaim strategy was BUILT AND ABANDONED on the same day (2026-08-17)

`smc_sweep_reclaim_strategy.pine` — sweep the previous session's level, close back through it
within three candles on a candle whose body agrees, target the session's other end. 347 lines,
16 inputs, no `request.security`. **Deleted the day it was written, at Aaron's call, and recorded
here so nobody proposes it a third time.**

**Why it was killed, in his words:** *"it does not have much confirmation to know we're ready to
change direction after the sweep. A pattern is not enough. Misleading candle patterns could print
at highs all day long and simply blow past the sweep levels."*

🔴 **THE OBJECTION IS THE ARGUMENT FOR THE SHIFT OF STRUCTURE, AND THAT IS THE FINDING WORTH
KEEPING.** "A candle body is not enough evidence that direction has changed after a sweep" is
precisely the job `pbRequireConf` does in `smc_session_sweep_strategy.pine`. The idea was not a
dead end — it was a rediscovery of why the course's rule exists. ⚠ **It was abandoned on an
impression, never compiled and never run**, which is the same move that kept the +180% alive: the
chart looked good so it was believed, then another chart looked bad so it was not. Neither was a
number. Say so if it comes back.

⚠ **Two things in it are worth stealing rather than rebuilding.** The **leverage refusal** — an
input in units of "times my account" instead of a percent-of-price stop floor, refusing rather than
shrinking — and the **three-candle window** on a reclaim. Both are described in this file's git
history at the commit that deleted them.

## The session sweep strategy — the rules the 2026-08-14/15 pass left behind

**`smc_session_sweep_strategy.pine`, called `m15_playbook_strategy.pine` until 2026-08-15.**
The old name named the timeframe the DIRECTION is read on, said nothing about the setup, and wore
the `mpc_` prefix of a Pine family this file was never part of — it came from a video note, not
from `mpc_jarvis.pine`. Its `indicator()` twin, `../../indicators/engines/m15_playbook.pine`, was deleted
in the same pass: 270 KB of dashboard that placed no orders, so the Strategy Tester could never
score it. ⚠ **That deleted file is where this strategy's structure-engine block was lifted from
byte-for-byte**, so its provenance now points at `engines/market_structure/` — the canonical
implementation and the only other copy. ⚠ **The old names are deliberately left standing in
`HISTORY.md` and the build notes**: a diary entry records what a file was called when the thing
happened, and rewriting it makes the record false.

**Full narrative: `../../indicators/docs/INDICATORS_BUILD_NOTES.md` → *the playbook joins the contract*.** What
is here is the instruction; that file is the evidence. Six rules, each learned by something on a
chart being wrong in a way nothing errored about.

### 🔴 THE SHIPPED DEFAULTS ARE AARON'S CHART, NOT A MEASUREMENT (2026-08-17)

**Six defaults were changed to whatever Aaron had dialled in on his own chart, at his request:
confirmation OFF, first target 3.5R, 80% banked there, 4% risk per trade, minimum stop floor 0.07%,
sessions drawn.** The gap requirement stays ON (`pbPoiTf = "5"`). Table and the reasoning per line:
`../../docs/SMC_SESSION_SWEEP_SPEC.md` → *The shipped defaults*.

✅ **ONE OF THEM NOW IS: the minimum stop became `Fixed $` `4.00` on 2026-08-17 and it was
MEASURED.** The target was the average LOSER, which is −1.27R over 214 positions where a stop that
works gives −1.00R — and that 0.27R of overshoot is more than half the whole edge (break-even 26.1%
against an actual 29.9%). **All 150 losers bucketed by stop width: everything under $4 averages
−1.43R and holds every loss worse than −3R in six years; everything above averages ≈−1.1R whatever
you do.** So $4 is the bend in the curve and a wider floor buys only fewer trades. ⚠ **The MODE
changed too and that is half the fix** — `% of price` is not a constant, and 0.07% was $1.19 at gold
1,700 against $2.80 at 4,000, i.e. loosest exactly where it was needed most. ⚠ **It is a FILTER on a
finished export, not a re-run**: with one position slot a refusal frees the slot, so a real backtest
can take trades this cannot see. **The bias only runs one way — the ~9R it appears to cost is an
upper bound** — and the per-trade ratios are sound while the total-R figures are the approximation.
⚠ **IT DOES NOT FIX THE LEVERAGE.** At 4% risk on gold at 3,500 a $4 stop is still **35x**; the
floor and the risk percent set leverage together, and 20x would need risk near 2.3%. Full table:
`../../docs/SMC_SESSION_SWEEP_SPEC.md` → *The minimum stop is $4*.

🔴 **THE OTHER FIVE ARE STILL NOT BACKED BY A RUN, and the reason to write that here is that a default is
indistinguishable from a finding once it is in the file.** The previous set was equally unmeasured
and read for two days as if the course had produced it — 5R was the course's number and 50% was
nobody's. **A default is a CLAIM about what is best, made by whoever typed it last.** These are
Aaron's live settings and they are the ones to reproduce when he reports a number; they are not a
result and must never be quoted as one.

⚠ **Three of the six move RISK, not display, and they compound: 4% per trade with a 0.07% stop
floor sizes larger on a tighter stop than the old 1% / 0.03% pair did in both directions at once.**
The floor is the only thing between the position sizer and a stop a few ticks wide.

⚠ **Changing a default is what re-opens the cascade audit** — see *A CASCADE AUDIT* below for the
`showSosMark` gate this reversed one day after it was written.

### 🔴 The TOOLTIPS are for Aaron, not for the next engineer (2026-08-16)

**Aaron: *"all the tooltip explanations are way too long and way too technical. I can't read that."***
Every tooltip on this file's 44 inputs was rewritten short and plain. They had grown into the same
thing the comments had been — measured numbers, dates, file paths, incident history — except a
tooltip renders in a small hover box on a settings panel, which is the worst possible place to put
any of it.

**The rule: a tooltip answers "what does this do and which way should I move it", in one or two
sentences, in words a non-programmer uses.** No file paths, no dates, no variable names, no bar
counts, no "block code 9". The evidence and the incidents live in this doc; the tooltip is the
label on the dial.

⚠ **This is the same lesson as the comment strip, one layer up: the content was not wrong, the
PLACE was.** Deleting it would have been the mistake; it moved.

⚠ **`showSetups` was also renamed** — it read *"Draw the zone, stop and targets"*, which named a
thing (a "zone") that appears nowhere else in the UI and did not say the drawing belongs to trades
that actually happened. It is now *"Show the gap the order sat in, plus entry, stop and targets"*.
**Renaming a title is safe for saved settings; only insertion and reordering are not.**

### 🔴 The file's comments were STRIPPED 2026-08-16 — this doc is now the only copy

**Aaron: *"realistically I will never read these comments. Unless they're for AI, they're
useless."*** 674 of 1,722 lines were explanation — **45% of the file, 111 KB → 61 KB** — and every
byte of it loaded on every read, in a file that gets read constantly while a chart is being tuned.
All full-line comments below the header are gone. **Tooltips stayed**: those render in TradingView,
so they are the half he actually reads.

⚠ **This makes the doc load-bearing rather than supplementary.** Several facts below are now
unrecoverable from the code — the code is correct and silent about why. Before changing this file,
read the sections here.

⚠ **How it was done, because doing it by hand is how a Pine file breaks.** A script stripped
full-line comments only, after first proving that **no `if`/`else`/function body would be left
empty** — a comment that is the sole member of a block is load-bearing whitespace, and removing it
is a compile error, or worse, a silently re-parented statement. Inline trailing comments were
removed only on lines with no string literal on them. The script is disposable; the CHECK is the
part to repeat.

### The facts that used to live only in the header

**STATUS.** ✅ Compiles — confirmed by Aaron 2026-08-16, on the build carrying the three course
rules, the provenance panel and the rebuilt overlay. ⚠ **That is a fact about that paste only.**
There is no local Pine compiler, so every edit since is unverified; `check_active_order.py` is the
only thing that runs here. 🔴 **NOT MEASURED — no run has been taken at these defaults.** No export
twin, no Python port, so **no `compare_*.py` covers this file at all.**

**The confirmation timeframe is read through a COUNTER, not a flag, and that is not a style
choice.** `request.security` runs the structure engine on every bar of the requested timeframe and
hands back only the value as at the LAST of them. A shift flag is set on the bar that shifted and
cleared at the top of the next, so sampling it once per chart bar reads the fifth 1-minute bar and
misses four out of five shifts. A counter accumulates inside the chart bar and is diffed against the
previous one. ⚠ **The flag goes stale-FALSE through the security call, not stale-true** — an earlier
comment had that backwards, so the code was right for a reason its own note got wrong. ⚠ Residual
cost: the shift is known at the chart bar's CLOSE — up to one chart bar late, never early.

**The drawing budget is TradingView's 500-per-type and nothing here caps itself.** Aaron, 2026-08-15:
*"don't cap it at all."* ⚠ TradingView evicts per OBJECT TYPE, oldest first, with no idea which
drawing an object belonged to — so at the far-left edge a setup dissolves in pieces, its box gone
while its stop line remains. That is the edge running out, not a bug. ⚠ **The families compete**:
sessions draw 3 boxes a day whatever happens, trades 4 each. **Count trades in the Strategy Tester's
list, never off the chart.**

**The session windows are hardcoded and DST-aware** — each session's own city clock, identical in
every Pine file here since 2026-07-31. They DECIDE trades (the pool is read from them), so they are
not inputs, and a change to one belongs in every file carrying the block.

**The point of interest is GAP-ONLY.** The course says "order block OR fair value gap"; only the gap
is modelled, so this file takes strictly fewer setups than he does. ⚠ **TradingView loads limited
1-minute history** — with confirmation on, the far end of a long backtest may see no 1m structure
and simply take no trades there. Check the trade list's FIRST date against the chart's.

### 🔴 Three rules added from the course, 2026-08-16 — and none of them is measured yet

Six runs of this file over 2023-01 → 2026-08 on XAUUSD gave a win rate that never left
**16.7-20.1%**, profit factors **0.85-1.15**, worst drawdowns **24-59%**, and **zero breakeven
trades in 1,961 trades**. The course the model came from
(`education/smc/05-my-full-trading-strategy/`, the data review in transcript 25 — ⚠ its
`summaries/25-*.md` is an empty `to-summarize` stub, the numbers are in the transcript) reports
his own book over 2.5 years: **230 trades, 62 wins, 126 losses, 42 BREAKEVEN**, ~6.2 average
reward-to-risk, worst drawdown **6%**.

🔴 **The setup was never the problem — London-sweeps-Asia is his most traded AND most profitable
play, and it is the one this file implements.** What was missing was rules he has and this file
did not. Three are now in, each behind its own switch, all defaulted ON:

| input | what it does | his number |
|---|---|---|
| `execBeOnShift` | stop to breakeven when the confirmation timeframe shifts against an open trade | 18% of his trades end flat; ours ended 0% flat |
| `execUseWindows` | trade three one-hour windows a session instead of all nine hours | London 2-5am NY, New York 7-10am NY |
| `execTp1Mode` = `Fixed R` | first target at a fixed 5R instead of the nearest liquidity level | his winners average 6.8x, ours 4.7x |

⚠ **ALL THREE ARE HYPOTHESES. Nothing has been run.** They are switches precisely so each can be
turned off and re-measured alone — flipping all three and reading one number says nothing about
which one did the work, and this repo has a rule about exactly that.

⚠ **The breakeven rule implements only the MECHANICAL half of his.** He also requires no reason
left for price to return (no unfilled zone behind it), which is discretionary and is not modelled.
So it fires MORE often than he does: expect scratches he would not have taken and runners cut
early. **Known bias, one direction** — read the breakeven count against his 18% before concluding
the rule failed.

🔴 **Both windows have an INERT first hour, and it is a fact about this file rather than a bug to
chase.** The London session opens 08:00 London = **03:00 New York**, so his 2-3am hour is outside
every session here and dies on block code 3 before the clock is consulted — his 2am hour is the
**Frankfurt** open, and Frankfurt is a session this file does not model. Same shape on the other
side: the New York session window starts 08:00, so his 7-8am hour is refused too. **Effective
windows are 3-5am and 8-10am.** Widening the session windows to match would change what the POOL
is measured over, which is a real change and not a tidy-up.

⚠ **A resting limit is CANCELLED when its window closes** (`cWin`, ungated by `execCancelFlip`).
Without that the window would be decorative — an order placed at 04:55 could fill at 08:30 — and
the trade list would not be comparable to an hour-by-hour read of it.

⚠ **Refusals on the clock are block code 11, chosen instead of renumbering 4-10.** The ladder ORDER
decides which refusal wins; the number is only a label, and renumbering would silently change what
every tag and screenshot already taken means. ⚠ **Code 11 is deliberately NOT tagged on the chart**
— the window is shut for most of every session, so a pink label per leg would drown the five
refusals that mean something. Read its cost off the trade list, windows on against windows off.

⚠ **Under `Fixed R` the first target always exists, so block code 9 can never fire** and the trade
count rises for that reason alone. ⚠ **When no liquidity level sits beyond the fixed target the
WHOLE position exits there** — the runner is lost, deliberately, because the alternative is
inventing a second number nothing measured.

⚠ **INPUTS WERE INSERTED, NOT APPENDED, so every saved chart preset for this script is void.**
TradingView keys saved values off declaration order per type. The panel-order contract and
TradingView's persistence are in genuine conflict here and the contract won, because a panel
nobody can read is the defect this file already has an incident about. Re-set the panel on the
next paste; do not trust a preset from before 2026-08-16.

**Four course rules still NOT modelled**, and two of them gate his best setups: order blocks as
entry objects (this file is gap-only), point-of-interest quality grading, the news blackout, and
six of his eight named setups — including *NY continuation from the London POI* (**63% win rate**)
and *NY sweep of the Lull* (**55%**), both of which need session concepts this file has no idea
exist.

### 🔴 The trade overlay is the Command Center's shape, rebuilt in Pine (2026-08-16)

Aaron, off a side-by-side screenshot of `command-center/`'s trade tracker: *"no borders on
anything… one shade of green for where we took profit, a lighter shade where price ran further and
we didn't… a solid line showing where the entry was and a different one showing where we exited…
I want it exactly like this."* Six pieces, and each one answers a question:

| piece | what it answers |
|---|---|
| entry → **deepest**, red | how far it went against you |
| entry → **furthest**, LIGHT green | how far it ever went your way |
| entry → **exit**, DARK green | the part you actually captured |
| entry line, grey solid | where you got in |
| exit line, result-coloured | where you got out |
| SL line, red dashed | the risk you took it on |

🔴 **DRAW ORDER IS LOAD-BEARING.** The favourable band (`pRan`) is created at the FILL and the
captured band (`pGot`) at the CLOSE, so the later box paints over the earlier one. The captured
band is a SUBSET of the favourable band on any winner, and that layering is the only thing
producing the light-green sliver between the exit and the furthest — *"price ran further but we
didn't take any profit."* Swap them and the whole move reads as captured.

🔴 **ARM and FILL are different bars, and that decides what a drawing may span.** The gap, the entry
and the stop are true from the moment the LIMIT is placed, so they start at the arm bar. A TARGET is
not — nothing aims at it until there is a position — and it was drawn from the arm bar too, so on any
order that rested a while the target line stuck out to the left of the trade block. Aaron: *"it's
overlaying to the left of where the trade traded."* Now clipped to the fill. ⚠ **On a market entry
arm and fill coincide and the clip is a no-op, which is exactly why it survived**: the defect only
exists on the resting-limit path.

⚠ **The swept-level line is GONE** (Aaron, 2026-08-16: *"I want that whole line gone"*). It ran from
the sweep bar across to the setup, so it reached back into the previous session and was the longest
object on any chart — **a line that long reads as a level being respected, not as a one-off event
that already happened.** The pool plot draws that price live for the session hunting it, which is the
honest version. `sweepHi/LoBar` and `sweepHi/LoLvl` went with it: nothing else read them.

🔴 **A `plot()` of a level that JUMPS needs an explicit `na` on the jump bar.** `style_linebr` only
breaks on `na`, and London runs straight into New York with no gap — `rawSess` goes 1 → 2 on adjacent
bars — while the pool underneath jumps from Asia's high to London's. The plot joined them with a
steep diagonal, and **a diagonal on a price chart reads as a trend line**. `newLeg ? na` is the fix
and it costs one bar of the new session's line, which is the right trade: a one-bar gap is legible,
a connector between two unrelated levels asserts something false.

🔴 **Inserting a block ABOVE a trailing, more-indented fragment RE-PARENTS that fragment, and Pine
has no brace to disagree with.** The close-bar stretch was inserted directly above the three lines
that make the setup's stop line follow the staged breakeven, which swallowed them into a branch
gated on `justClosed` — where the position is by definition FLAT, so the guard was never true.
Nothing errored; **the stop line simply froze at the original stop.** ⚠ After inserting into an
indented Pine block, check what now sits UNDER it, not just what you wrote.

🔴 **The right edge of every piece is set in ONE place, on the close bar, and getting that wrong is
what a split drawing looks like.** The live-extend block is gated on `strategy.position_size != 0`,
and on the bar a trade CLOSES the position is already flat — so it does not run, and `pRan`/`pDD`
stopped one bar short while `pGot` and all four lines were born on that bar and ran to it. The
symptom Aaron saw was a light-green margin down the side of the dark box that read as a second,
wider zone. ⚠ **Standing: a drawing assembled from pieces created on DIFFERENT bars has to have its
extents set in one place, or the pieces disagree about where the trade ended.**

⚠ **The SL line reads the ORIGINAL stop, never the live one.** The live stop moves to breakeven, so
drawing it shows a trade at a reward:risk it never had. That is why `posStop0` exists.

⚠ **No borders anywhere, and no direction arrow.** The old build bordered the result box and the
border was the loudest thing on the chart — it read as a level rather than as the edge of a fill.
Direction is carried by the geometry: green above the entry is a long, green below it is a short.

🔴 **The result label anchors at the FURTHEST price and points outward.** It used to hang 1.5 ATR
off the ENTRY, which on any trade that travelled put it in the middle of the move — Aaron: *"this
should be off of the bars. It should never be on top of the bars."* Anchoring at the extreme the
trade reached is what guarantees nothing is beyond it to cover.

⚠ **The gap zone is GREY and BORDERLESS, copied from `sos_fade_strategy.pine:225`** (`color.new(color.gray,
80)`, `border_color = color(na)`, bull and bear identical) rather than chosen here. Aaron, 2026-08-16:
*"no border, make it grey, same as my other fair value gaps."* **It is deliberately not
direction-coloured**: a gap is a price RANGE the limit rests inside, and the trade block drawn on top
of it already says which way the trade went — a green-bordered box under a green trade block is two
claims about one thing. A pulled setup fades one step (`FVG_DEAD`) and takes the ✕; there is no
border left to recolour, which is why the fade carries it.

🔴 **Every label sits behind `execShowLabels` and it SHIPS OFF.** Aaron asked for the pills, saw
them, and said *"take off the labels — I can use the colour code to determine that."* The zones and
lines do carry the picture alone. ⚠ **What that costs is stated on the input rather than left to be
found: colour can say won/lost/breakeven and it cannot say 4.46R**, so with labels off there is no
per-trade R on the chart at all and no hover. On for reading individual trades, off for reading the
shape of a run. ⚠ It is also the entire label budget — six a trade against Pine's 500-label ceiling
is ~80 trades, and blocked-setup tags compete for the same 500, so OFF is what lets the chart run
back as far as it does. **Count trades in the Strategy Tester's list, never off the chart.**

### 🔴 MISSED and BLOCKED are different things, and one pink tag said both

**Aaron, on a refusal whose gap sat twenty dollars from price: *"it was never blocked, it was
missed… you could have said two out of three — the session was swept but the fair value gap was too
far."*** Every refusal from the zone onward wore one pink **SETUP BLOCKED** tag, which reads as the
strategy turning away a trade it could have taken. In codes 6-9 there was never a trade to turn
away: the model's own fourth step did not happen.

| tag | codes | means |
|---|---|---|
| **orange `3/4 MISSED`** | 6-9 | direction, sweep and confirmation ALL landed; the point of interest failed |
| **pink `BLOCKED`** | 10 | all four confluences were there and OUR one-position rule refused it |

🔴 **THE TICK-LIST IS READ FROM THE INPUTS AND ITS FIRST VERSION WAS HARDCODED.** It shipped
printing a fixed *"3 of 4 · ✓ Confirmation — the 1-minute changed character"* — on charts with
lower-timeframe confirmation switched **off**. Aaron, within minutes: *"how could it have met the
1-minute confirmation if I have it off? That tells me the annotations are not reading my inputs."*
He was right, and the same line hardcoded *15-minute* for a direction timeframe that is also an
input. Now: the denominator is 4 or 3 depending on `pbRequireConf`, the confirmation row reads **NOT
REQUIRED** when it is off, and every timeframe named is the one actually set.

⚠ **`sos_fade_strategy.pine` had already solved this and the pattern was not carried over** — its
2-of-3 callout takes every gate as a PARAMETER from the caller precisely so *"the callout always
describes the strategy you are actually running"*. **A confluence tick-list is a CLAIM about the
config, so it has to be built from the config.** A hardcoded one is worse than no tick-list: it
reads as a diagnostic and is a decoration, and it will be believed over the settings panel.

🔴 **THE SCORE ITSELF WAS STILL ASSERTED, AND THAT COST A ROUND.** `cfMet` was
`str.tostring(isMiss ? cfTot - 1 : cfTot)` — pure arithmetic off the gate code, reading none of
`dirDir`, `sweptHi/Lo` or `confShort/Long`. The reasoning was sound (the ladder cannot reach a
point-of-interest refusal without the earlier steps passing) and the OUTPUT was therefore correct,
which is exactly why it survived. It failed the moment Aaron asked a question of it: a 3/4 MISSED
tag claimed *"✓ Confirmation"* while the confirmation MARKER was absent from the chart, and there
was **no way to tell which one was lying, because only one of them was measuring anything.**

✅ **Every tick is now read from the live flag** (`okDir`/`okSwp`/`okConf`), the count is their sum,
and a failed step prints ✗ rather than being omitted. The confirmation line also prints the price it
broke at, so it ties to the cyan SOS line by number and not by eye. ⚠ **This will now DISAGREE with
the ladder if the ladder is ever wrong — which is the point.** A tick list derived from the thing it
is supposed to check can only ever agree with it.

**The standing lesson, and this file has now hit it three times: a derived diagnostic is not a
diagnostic.** It cannot catch the bug it sits next to, and its confidence is indistinguishable from
evidence. The cost is a few extra reads of variables already in scope.

🔴 **Code 8's wording named the CONSEQUENCE and hid the CAUSE.** *"The stop is too tight"* is what
happens; *the gap is too thin* is why. Aaron read the old text as the strategy refusing a good
trade, and it cost a full round of explanation. ⚠ **When a gate refuses on a derived quantity, say
what it was derived FROM** — the stop distance is downstream of the gap height, and only the gap
height is something you can look at on the chart.

⚠ **Pink is now the only refusal you can buy back by changing a setting**, which is what pink should
have meant all along. ⚠ **Colours are `sos_fade_strategy.pine`'s and mean the same there** — orange
2-of-3 callout, pink TRADE BLOCKED — so one glance reads the same on either chart. ⚠ **That orange
is also this file's BREAKEVEN colour**, an overlap SOS Fade has too; it is tolerable only because the two
never share an object (breakeven orange is always a filled trade band, missed orange is always a tag
with no trade under it). **Do not use it for a third thing.**

### A refusal is DRAWN now, not just tooltipped (`showBlockDraw`, 2026-08-16)

**Aaron, reading a *"the stop is too tight"* tag: *"if it was a fair value gap, still draw the fair
value gap so I could visually see it, and draw where the stop loss would have been."*** The tag
carried the reason and the would-be entry price in a tooltip, and that made the guard unauditable by
eye — you had to take *too tight* on trust. A blocked setup now draws the **same three objects a
taken setup draws**: the gap as the identical grey borderless box, the entry it would have rested
at, and the stop it would have carried. The tooltip also prints the stop distance next to the floor
that refused it.

### The shift of structure is MARKED now, and a second timeframe is marked beside it (`showSosMark`, 2026-08-16)

**Aaron: *"if we do take the one minute shift of structure, give me an indicator on the chart exactly
where that happens… and add the equivalent on a five minute shift. I just want to see if five minute
works better than one minute."*** The confirmation step was the one part of the model with no mark on
the chart at all — every other step draws something — so *"the small timeframe turned"* was a claim
with nothing to check it against.

🔴 **THE FIRST BUILD MARKED EVERY SHIFT AND WAS USELESS FOR EXACTLY THAT REASON.** Aaron:
*"I only want to see the confirmation shift where there was either a missed trade, a blocked trade,
or a successfully taken trade. I don't want to see any other shifts in between."* A structure engine
on a 1-minute chart shifts constantly, so marking them all buries the handful that mattered under
hundreds that did not — **a marker that fires on everything carries no information, and it is worse
than none, because the chart now LOOKS annotated.** Same failure shape as the editor guard that
warned on every large file.

**So the marker is drawn RETROSPECTIVELY, at the moment the setup resolves.** The shift that
confirmed a setup is recorded when it happens (`cfBar`/`cfDir`/`cfPx`, set inside the same branch
that latches `confShort`/`confLong`, so it is by construction the shift the gate consumed, never a
re-derivation). Nothing is drawn then. The marker is placed back at that bar only once the setup
becomes one of the three things worth looking at — `justFilled`, or the MISSED/BLOCKED tag firing.
⚠ **A setup whose order was pulled before filling gets no marker**, by decision: it is not one of
the three cases named.

🔴 **AN ARROW BESIDE THE BAR WAS ALSO WRONG, AND THE REASON IS THE ONE THAT MAKES THIS FEATURE WORTH
HAVING.** Aaron: *"if we have a wick, I don't know which part of the wick the shift of structure
happened at. Show me a horizontal line right where it happened."* An arrow says WHEN. On a long
wick the question is WHERE — and a shift of structure has an exact price: **the swing level the
close broke through.** So `f_pbStruct` now returns that level as a third value (`bull_bos_high` on a
bull shift, `bear_bos_low` on a bear one, read straight from the engine's own fields), and the
marker is a **horizontal line at that price** with an `SOS <tf>m` label on its right end. Solid
cyan for the confirmation timeframe, dashed purple for the comparison one.

⚠ **`dirLvl` is destructured and unused** — the direction call shares the function, so it returns
the level too. Pine warns; it does not error.

⚠ **The price is recorded at the shift bar, not looked up later.** Drawing at a past `bar_index`
with `low[bar_index - cfBar]` would be a dynamic history offset — the class of bug that throws
*"beyond the historical buffer's limit"* at runtime and only on some charts. Storing the price when
the bar is current costs one float and cannot fail.

🔴 **A HORIZONTAL LINE ANSWERS "AT WHAT PRICE" AND SAYS NOTHING ABOUT "ON WHICH CANDLE".** Aaron,
on the next screenshot: *"the line runs across ten fifteen-minute candles. I don't know which one
the shift was on."* Its left end IS the bar, but a reader does not measure a line's endpoint — they
see a band. **The two questions need two marks.** The marker is now three objects: the flat line at
the broken price running right, a **thick vertical stub on the shift bar itself**, and the label
anchored to that stub with a pointer style (`label.style_label_up` on a bull shift,
`_down` on a bear one) so it points at exactly one candle. The label also carries the price, so the
candle and the level are both readable without hovering.

⚠ **The stub is drawn AWAY from the break** — below the level on a bull shift, above on a bear one —
because the candles right after a break sit on the other side and the marker would be buried in
them.

⚠ **The LINE is the level; the BAR is when we learned about it.** `request.security` reports on the
chart bar where the higher timeframe's bar closed, so the break happened somewhere inside that bar.
The price is exact, the x-position is *the bar the strategy could act on* — which is the honest one
for a strategy chart, and would be the wrong one for a study of the engine.

**The comparison timeframe** (`sosCmpTf`, default 5, `"Off"` available) marks the FIRST time it
turned the sweep's way in that session leg — the earliest that timeframe could have confirmed.
⚠ **It is MARKING ONLY and feeds nothing** — no gate, no arm, no order — which is what makes it
usable as a comparison: it shows what a different confirmation timeframe would have said on the same
bars, without changing the bars. ⚠ **It is not a verdict.** It says where and when the other
timeframe turned, not whether turning there was better; that is a backtest.

🔴 **AND IT ONLY EVER DREW ON TAKEN TRADES, BECAUSE THE RECORDING SAT INSIDE THE CONFIRMING
BRANCH.** Aaron: *"you only show it on trades we actually took. I want it on missed and blocked
too."* `cfBar`/`cfPx` were assigned in the same `if` that latches `confShort`/`confLong` — the
branch that fires only when a shift genuinely confirms. **With `pbRequireConf` OFF, step 5 passes on
the sweep alone (`confOkLong = sweptLo`), so a leg can reach a MISSED or BLOCKED refusal having
never entered that branch: nothing recorded, nothing to draw, and no error.** The same hole opens
under `"At the zone"`, where `placeOk` needs `armTouched` and a missed setup never touches the zone.

✅ **Recording is now SPLIT from confirming.** Every confirmation-timeframe shift on the swept side
is recorded, whatever the toggles say; a separate `cfUsed` flag records whether that shift was the
one the gate consumed. ⚠ **The flag is not bookkeeping — it is what keeps the tooltip honest.** The
same cyan line now means two different things, and it says which: *"this is the shift that confirmed
the setup"* when `cfUsed`, and *"it did NOT confirm anything — you have confirmation switched off,
or the setup was refused before it mattered"* when not. **A marker that looked identical in both
cases would be the label-vs-code failure this file keeps recording, drawn instead of written.**

⚠ **When no shift happened on that side at all there is still nothing to draw**, and that is
correct rather than a gap — there is no price to put a line at.

⚠ **The comparison draws NOTHING when it is set to the same timeframe as the confirmation.** Both
lines would sit on one price and the purple one — drawn second — would hide the cyan. That is not
hypothetical: a screenshot showing a lone purple `SOS 1m` and *"where is the confirmation
indicator?"* is what found it. The suppression is named in the input's own tooltip, because a
drawing that silently does not appear is the failure it is meant to prevent.

⚠ **One line plus one label per marker, and the budget is why the toggle DEFAULTS OFF.** The labels
share the 500-per-type ceiling with the MISSED/BLOCKED tags, the cancel ✕ and the trade labels, and
eviction is per-type and silent.

⚠ **Both inputs are appended AFTER the last existing input of their own type** (the bool after
`pbShowSess`, the string after `execMinStopMode`) even though both display in group 8. Group is a
display label; TradingView keys saved values off declaration order within each type, and the two are
unrelated.

⚠ **It adds a fifth `request.security` call.** The comparison timeframe is resolved to the
confirmation timeframe when it is `"Off"` so the call always has a valid argument, and the drawing is
gated instead — the call cost is paid either way.

⚠ **With confirmation switched off there is no confirming shift and no cyan triangle**, which is
correct rather than broken. The purple comparison one still draws.

### 🔴 A GATE NAME IS NOT AN EXPLANATION — "too thin" read as "we got there and it was too thin"

**Aaron, third round on the same tag: *"it says the gap is too thin. But price never got to it. All
this time I was thinking we got to one and it was too thin. Your messages have to be very clear on
exactly what happened."*** The gate name was accurate and the SENTENCE it formed was not. Nothing
says a refusal happened BEFORE any order existed, so a reader supplies the missing half — that price
arrived, then something went wrong there. It never arrived. No order was ever placed.

**The tooltip is now a story with an ending, not a gate name plus loose numbers.** It reads: what
lined up, then `WHY THERE WAS NO TRADE`, then a `THE GAP` block with the gap's location, height,
distance from price and the stop maths.

⚠ **The reason strings are now SENTENCES with full stops, not fragments.** A fragment gets read as
the end of whatever sentence the reader started, and they do not all start the same one.

🔴 **AND THE FIRST FIX WAS STILL NOT PRECISE — it appended "no order was ever placed" to a reason
that still LED with "the gap is too thin".** Aaron, immediately: *"It should say why there was no
trade. Point of interest was never met. That's it. Nothing more… only if we met it, and it was too
thin, and I could see that."* A disclaimer under a wrong headline does not fix the headline.

✅ **So the tag now KNOWS whether price ever traded into that gap, rather than inferring it.**
`f_poiScan` returns the selected zone's own tap flag alongside its prices (`poiBullTap`/`poiBearTap`,
`armTouched` on the at-the-zone path). `WHY THERE WAS NO TRADE` is then one line, chosen from the
FACT rather than from the gate: no zone at all → *"There was no gap on this side of price."*; a zone
price never entered → *"Price never reached the gap. The point of interest was never met."*; a zone
price DID enter → the real gate sentence, which now opens *"Price reached the gap, but…"*.

⚠ **With `pbPoiUntouched` ON — the shipped default — a tapped zone is excluded from selection, so
the tag can only ever say "price never reached the gap".** That is not the message being lazy; it is
the setting. The thin/target reasons become reachable only when untouched-only is turned off.

⚠ **Code 7 (too far) is deliberately EXEMPT from the tap test and always states its own reason.**
It is a filter the reader switched on, and by construction its gap is far away — routing it through
"price never reached it" would hide the filter that actually did the refusing.

⚠ **The stop maths is kept, one line, and it is worded as a HYPOTHETICAL when the zone was never
entered** (*"Had price reached it: entry …, stop …, your floor is …"*). It is the only way to see
whether a gap really was too thin, which is what Aaron asked for two rounds earlier — but it lives
under `THE GAP`, never under `WHY`, because a fact and a cause are different things.

**The standing lesson, and it is the sharper form of the section below: a first-refusal-wins ladder
tells you which CHECK refused, and a reader is asking what HAPPENED. Those coincide only when the
check ran on something real. When it ran on a hypothetical — an order that was never placed at a
price never traded — the gate name is the wrong sentence no matter how much you append to it.**

### 🔴 A DISABLED GATE MAKES THE NEXT ONE LIE — the "too thin" that was really "too far"

**Aaron, on a 2/3 MISSED tag: *"it says the gap is too thin. But we haven't even touched the gap
yet — how could that be valid?"*** He was reading a refusal on a gap **twenty dollars below price**,
reported as a thinness problem. Both facts were true. The ORDER was wrong.

**The ladder checks "too far" (code 7) BEFORE "too thin" (code 8) — and code 7 ships DISABLED**
(`pbPoiMaxAtr = 0`, no limit). So the first thing wrong with that setup was never evaluated, the
second thing was, and the tag named the second. 🔴 **A first-refusal-wins ladder reports the first
gate that FIRES, which is not the first gate that MATTERS when an earlier one is switched off.**
Every such ladder in this repo has the same shape.

**The fix is not to reorder the ladder** — the order is right, and code 8 genuinely did refuse it.
The fix is that **the tooltip now always prints the distance to the gap, in dollars and in ATR, and
says so explicitly when the distance filter is off.** A refusal reason is a summary; the geometry
next to it is what stops the summary being mistaken for the whole story.

⚠ **The setting that would refuse these honestly already exists** — *Maximum distance to the zone (x
ATR14)*, group 7 — and it is **0 = off** out of the box. Nothing is measured about what it should
be. A gap that far away is one the model offers and price rarely reaches, so it costs setups to no
purpose; that is a hypothesis, not a finding, and it needs a run each way.

🔴 **A REFUSED GAP GETS A BORDER; A TAKEN ONE DOES NOT, AND THAT IS NOT AN INCONSISTENCY.** Aaron,
looking at a *"gap too thin"* tag: *"I need to see a gap to know that it's too thin. If I can't see
it, the annotation doesn't add up."* The box was being drawn correctly the whole time — **a
one-dollar box on a chart at 4360 is under a pixel tall, and a borderless box of sub-pixel height
renders as literally nothing.** A border renders as a line at any height, so the thing the tag is
talking about is now always visible at its true size. ⚠ **The borderless rule it appears to break
exists for a DIFFERENT case**: a gap under a trade block, where the border would read as a second
claim about the same thing. A refusal has no trade block over it, so there is no conflict.

🔴 **THE LEADER LINE RUNS TO THE GAP, NOT TO THE CANDLE, AND THE FIRST FIX GOT THIS BACKWARDS.**
Aaron, after the border landed: *"I still can't see it. Look at the chart. I can't see it
literally."* A bordered box IS drawn — but the tag sits 1.5 ATR off the bar, the gap can be twenty
dollars the other way, and the line between them stopped at the candle. So the tag pointed at
nothing and the box was a grey line lost among the session shading. **The leader now ends on the
gap's near edge**, so following it always arrives somewhere. ⚠ **This does NOT reintroduce the
scale blow-up** — that came from padding the LABEL past the zone, and the label is still anchored to
the bar. The leader only spans a range the box already forced onto the scale.

⚠ **The tooltip also prints the gap's HEIGHT and both edges.** A line tells you where; only a number
tells you how thin, and "measure it by eye at this zoom" was never a real instruction.

🔴 **The stop is PINK and dashed, never the red a real stop gets.** Nothing was ever working there.
A red line says a trade existed, and a chart full of red lines at prices no order was ever placed at
is how a refusal gets read back as a loss.

**The tag itself moved OFF the candles.** It was anchored at the bar's high/low, which put it over
the very candles you are trying to read — Aaron: *"it's literally on top of the candle."* It is now
parked 1.5 ATR clear of the BAR with a dotted leader back to the candle.

🔴 **The pad is measured off the BAR ALONE, and the first version measured it off the ZONE too.**
That reads as the safer choice — a stop below the bar would otherwise be drawn through the label —
and it **blew up the price scale**. The zone is the nearest *untouched* gap, which after a long
one-way move can be twenty dollars from price; padding past it put the label another 1.5 ATR beyond
that, TradingView auto-scaled to include it, and the candles were squashed into the top fifth of the
chart. Aaron: *"the gap is off the chart now."* ⚠ **A label positioned relative to a value with no
bound on it inherits that lack of bound.** Anchor to the bar — it is the one thing on screen that
cannot run away. Same reason the leader now points at the candle rather than at the would-be entry
price.

⚠ **A far-off gap box is NOT the bug and must not be "fixed" by clamping it.** It is the honest
answer to why nothing traded, and the setting that refuses those already exists — *Maximum distance
to the zone (x ATR14)* in group 7, which ships at 0 = off.

⚠ **Costs 3 more drawings per tag against the 500-per-type ceiling**, so the chart goes back less
far with it on. ⚠ **Block code 6 has no zone at all** (that IS its refusal), so it draws the leader
and nothing else — guarded on the zone being non-`na` rather than assumed present.

⚠ **Inserting this bool shifted `pbShowSess` by one declaration slot**, so *Show sessions* resets on
every saved chart. Both are draw-only; it was accepted rather than missed. It is the last bool in
the file, which is why the damage stopped at one.

### 🔴 "BLOCKED" beside a running trade reads as a bug, and the reason string was three reasons at once

**Aaron, on a pink BLOCKED tag sitting under a trade that was clearly open: *"I don't understand
what was blocked. I'm in a trade."*** He is describing the tag correctly and it still told him
nothing. Code 10's string was *"You were already in a trade, already had an order waiting, or had
already traded this session"* — **a list of the three things `busy` is made of, offered because the
code did not know which one fired.** It does know: `strategy.position_size`, `pendDir` and `tookLeg`
are all in scope at the tag, and they are mutually distinguishable.

✅ **Four sentences now, picked from live state, and each one names the SECOND setup explicitly** —
that is the missing noun. The tag is not about the trade you can see; it is about another setup that
appeared while that trade held the only slot. ⚠ **The cross-session case is separated out**
(`position_size != 0 and not tookLeg` — a trade from an EARLIER session leg still running), because
that is a genuinely different fact about the strategy and gets read as the same one.

🔴 **AND THE PLAN WAS NESTED INSIDE THE GAP BLOCK, SO A SETUP WITH NO GAP SHOWED NO PRICES AT ALL.**
`tipGeom` was concatenated onto `tipGap`, which is `""` when there is no zone — invisible for every
`pbPoiTf = "Off"` refusal, i.e. exactly the mode added the same day. It is its own `THE TRADE THAT
DID NOT HAPPEN` section now. ⚠ **A string built by appending to a conditionally-empty string
inherits that condition**, and nothing errors — the section simply is not there.

### 🔴 The gap can be switched OFF entirely — `pbPoiTf = "Off"` (2026-08-16)

**Aaron: *"I want an option where I don't require a point of interest. I'd still require the shift of
structure confirmation."*** The course's third step is the gap; this drops it. Sweep, then the
confirmation timeframe turns, then **enter at market on that bar**, stop behind the sweep extreme.

🔴 **IT IS AN OPTION ON THE EXISTING DROPDOWN, NOT A NEW INPUT, AND THAT WAS THE DESIGN CONSTRAINT
RATHER THAN A TIDINESS PREFERENCE.** A new `input.bool` has to be appended after the LAST bool in
the file to avoid resetting saved values — which would have put "do I need a gap?" at the bottom of
the panel, three groups away from the gap settings it governs. **Widening an existing dropdown moves
nothing, resets nothing, and lands the control exactly where it belongs.** ⚠ **Reach for this before
reaching for a new input**: ask whether an existing control of the right type already sits in the
right place. ⚠ It also let `pbPoiUntouched` be gated on it, which a bottom-of-file input could never
have done — `active =` may only name inputs declared above.

⚠ **`"Off"` is not a timeframe**, so the scan's `request.security` resolves it to `"5"` and the
result is discarded by the flag instead. The call cost is paid either way.

🔴 **`poiOff` REQUIRES CONFIRMATION AND SILENTLY STAYS OFF WITHOUT IT** (`pbPoiTf == "Off" and
pbRequireConf`). With both switched off nothing is left but the sweep, which is a different and much
looser strategy that nobody asked for. ⚠ **The refusal is the safe direction but it IS silent** —
the dropdown's own tooltip is the only place it is stated, because a greyed-out `active =` is a
display hint and does not stop the value being read.

**What changes downstream, and every one of these was a place the gap was assumed to exist:**
the entry becomes `close` and the order goes in at MARKET rather than as a resting limit; the stop
comes from the sweep extreme alone (`execStopFrom` is bypassed — there is no gap edge to choose
between); gate 6 stops asking "is there a gap" and asks "is there a sweep extreme to stop behind";
the grey zone box is skipped, so the setup drawing's update passes now key off the ENTRY LINE rather
than the box; and the tag's tick list drops to 3 steps with the point-of-interest row reading
*"not required"*.

⚠ **The minimum-stop floor becomes the load-bearing guard in this mode.** A sweep extreme one tick
from the entry is a huge position, and there is no gap height standing between the two any more.

⚠ **NOT MEASURED.** This is a different entry model — market fill at the turn instead of a limit in
a gap — so it pays the spread and gets no retrace. Run it against the shipped default before
believing anything about it.

### 🔴 A CASCADE AUDIT, and the three inputs that stayed editable while doing nothing (2026-08-16)

**Aaron: *"why is 'mark the shift of structure' still editable when I have confirmation off? Is
there anything else we are not disabling correctly from a cascading perspective?"*** The question is
worth more than the one input that prompted it. **An input with no `active =` is a PROMISE that it
does something**, and three here were breaking it — silently, because a control that changes nothing
looks identical to one that works.

| input | inert when | why |
|---|---|---|
| `execZoneEntry` | `"At the zone (enter at market)"` | the entry is `close`, so where the limit rests in the gap is never read |
| `execTpFallbackR` | `execTp1Mode == "Fixed R"` | a fixed-R target is never `na`, so the `na(t1)` fallback is unreachable |
| `pbPoiMaxAtr` | `"At the zone"` | its own gate is guarded by `not confAtZone` |
| ~~`showSosMark`~~ | ~~confirmation off~~ | **REVERSED 2026-08-17 — see below** |

⚠ **`execCancelBars` and `execCancelFlip` were CHECKED AND DELIBERATELY LEFT UNGATED.** They look
inert at market — no resting limit — but Pine fills a market entry on the NEXT bar's open, so the
order is pending for one bar and the session/window cancels can genuinely fire on it. **A control
that acts once is not a control that acts never.**

🔴 **THAT `showSosMark` GATE WAS WRONG AND WAS REVERSED ONE DAY LATER (2026-08-17), AND THE
REVERSAL IS THE LESSON.** The trade-off was named honestly at the time — gating it made the
confirmation-off mode unreachable from the panel — and the name was allowed to win anyway. Then
`pbRequireConf` shipped defaulting **OFF**, and the control that answers *"what would requiring
confirmation have cost me?"* was greyed out for every user on the default settings, at exactly the
moment it was most useful. **A cascade gate is a claim about which settings are worth reaching, and
it goes stale the instant a DEFAULT moves.** The input is now ungated and renamed *"Mark the shift
of structure next to a setup"*, which is true in both modes. ⚠ **Re-read every `active =` in a file
whenever you change a default in it** — nothing fails, nothing goes red, the control just quietly
stops being available.

🔴 **THE SAME AUDIT MISSED A GATE POINTING THE OTHER WAY: `pbConfTf` WAS GREYED WHILE THREE THINGS
STILL READ IT.** Turning confirmation off does not stop the confirmation timeframe being consumed —
`execBeOnShift` (breakeven when the small timeframe turns against the trade), `execCancelFlip`
(pull a resting order on an opposite shift) and `showSosMark` all read `newConfShift`, which is
derived from `pbConfTf` with no reference to `pbRequireConf`. So the panel greyed a live control and
the user had no way to change a timeframe that was still deciding where their stop went. Now
ungated, with the three consumers named in its tooltip. ⚠ **An audit that only asks "is this input
inert?" finds half the defects. Ask the other direction too: "is anything still READING an input I
have greyed?"** The first shape is a dead control; the second is a lie about what the strategy is
doing, and it is the worse of the two.

⚠ `pbConfWhen` was re-checked in the same pass and its gate is CORRECT — it is read only inside
`confAtZone = pbRequireConf and ...`, so confirmation off makes it genuinely inert.

⚠ **The grouping was done by CHANGING `group =` STRINGS, never by moving declarations.** A new
`GS` group pulls the four confirmation inputs and the two marker inputs together, and TradingView
places a group where its FIRST input is declared — so it lands second without a single `input.*`
call changing position. **Moving the declarations would have reset every later input of that type
on Aaron's charts; changing a group string resets nothing.** That is the only safe way to reorganise
this panel and it should be the default move.

### 🔴 This file's panel is ordered by PROVENANCE, and it is the only one here that is

**Aaron, 2026-08-16: *"rearrange the inputs into things that came from him 100% and things that
came from us… so I could see them logically."*** Groups **1-4 are HIS MODEL**, groups **5-10 are
OURS**. The other five strategy files keep the house contract that groups by what a setting
CHANGES; this one does not, and the exception is deliberate rather than drift.

**Why it was worth breaking the contract.** This file is a PORT of somebody else's documented
model, and its six flat backtests were explained almost entirely by rules of his we had not built
and rules of ours he does not have. Grouping by function hid exactly that — his 5R target and our
minimum-stop guard sat in one box called *Stop & targets*, so nothing on the panel said one was the
model and the other was our own scar tissue. ⚠ **Do NOT propagate this layout to the other files.**
They are not ports of an outside model and the provenance split would mean nothing there.

⚠ **Group 6, *choices his method leaves open*, is where to look first when a result disagrees with
his book.** Every input in it is a number standing in for a decision he makes by eye and never
states. ⚠ **Groups 8-10 cannot move a trade** — if a result differs, it is in 5, 6 or 7.

### 🔴 What invalidates the trade — the gap, or the sweep? (`execStopFrom`, 2026-08-16)

**Aaron: *"I don't think the size of a fair value gap should ever matter. If we had a shift of
structure and that gap was one dollar, I don't care — put the stop behind the low of the session
that swept."*** He is describing a different theory of invalidation, and he is right that it is a
theory rather than a fact, so it is a switch and **neither setting has been measured.**

| setting | stop sits past | consequence |
|---|---|---|
| **The gap** (default, and what this file always did) | the far edge of the entry zone | a $1 gap gives a $1 stop; thin gaps get refused by the minimum-stop floor |
| **The sweep extreme** | the high (short) / low (long) the session made taking the pool | gap size stops mattering; stops widen a lot |

🔴 **It takes the FURTHER of the two, never the sweep alone.** A gap that extends past the sweep
extreme would otherwise put the stop INSIDE the entry zone, where price simply filling the gap you
entered on takes you out. That case is rare and silent, which is exactly why it is handled here
rather than left to be discovered in a trade list.

🔴 **THE TARGETS MOVE WITH IT, and this is the thing that will mislead a comparison.** Under Fixed R
the first target is 5× the stop distance — so a $10 stop aims fifty dollars away where a $1 stop
aimed five. **Switching this changes the entry, the size, the target and the refusal rate at once**,
so a single before/after number tells you almost nothing about which effect did the work. Read the R
distribution and the trade count, not the net.

⚠ **The sweep extreme is the RUNNING extreme of the leg**, snapshotted when the limit is armed —
not the single bar that first crossed the pool. A session that keeps pushing moves the level, which
is the honest reading of "the session's low" and also means an order armed late carries a wider stop
than one armed early.

### 🔴 The minimum-stop floor: 0.08% → 0.03%, and why it is not zero

**The guard came from THIS REPO, not from the course** — it is in all ten strategy files here, and
it is scar tissue from a sizing bug that once put a 54-lot order on a $2,000 account. **He does the
opposite**: *"you'll see tight stops when there's no room, but there's no wiggle room."* A tight
stop is how a 6.8x average winner happens at all, so the guard could only ever delete his best
trades.

🔴 **It is LOWERED, not removed, and the rule generalises past this file: a floor on stop distance
is a proxy for a COST, so it must be set from the measured cost and not from a round number.** The
runs bill no spread and no commission; Vantage's measured XAUUSD spread is **$0.22**
(`backtest/fills.py`). That is 6% of a median stop here, 22% of a $1 stop, over half of a $0.40 one
— **so the tightest setups are exactly the ones a zero-cost backtest flatters most.** 0.03% ≈ $1 of
gold today: his stops get through, the unpayable ones still do not. ⚠ **Turn the spread on in the
tester before reading the trades this gains you**, or you are scoring against a book that never
paid to enter. ⚠ **What the floor COST is unmeasurable from a trade list** — a refused setup never
appears in one. Numbers behind all of this: `../../docs/SMC_SESSION_SWEEP_SPEC.md`.

**1 · A drawing on a strategy chart is a CLAIM, and a claim about a PLAN must be withdrawn when
the plan does not happen.** Reward bands are painted at the fill, entry → target, because that is
what the trade is aiming at. Nothing removed them on the close, so a −1R stop-out left a
full-height green band running to a price nothing went near — the chart said won, the result said
−1R. On the close the target bands are deleted, the body band is repainted entry → the REAL exit,
and the red band is clipped to the worst price the trade actually SAW rather than the stop it never
reached. ⚠ `sos_fade_strategy.pine` already carried this in writing (*"every band comes from the
strategy's own closed-trade log… never a fib level it merely aimed at"*) and the palette pass
copied its COLOURS without copying the rule.

**2 · A setup that never filled must not look like one that traded.** Most armed setups die — the
session rolls, the direction flips, price never returns. Each used to leave a full-colour drawing
identical to a real trade's, so a long setup that never happened sat beside a short that did.
Cancelled setups fade to grey and take a `✕`. An armed setup draws no text at all; the `✕` is the
only text a setup ever gets, because it is the only case with nothing else to speak for it.

**3 · A label naming a precondition that every drawn setup already satisfies is noise.** Each setup
carried `London sweep` / `Asia sweep`, overlapping the result label — and a setup here cannot arm
without a sweep, so the words restated the drawing's own existence. Replaced by the thing the label
alluded to: **a dashed double-width line at the price actually taken, from the bar it was taken
on.** The precondition is noise; the level it fired on is information.

**4 · A self-imposed cap that truncates history is indistinguishable from a bug.** Session boxes
were capped at 30 — three a day, so ten trading days — and simply stopped mid-chart. Nothing here
evicts anything now; TradingView's own 500-object ceiling is the only limit, and it drops the
oldest object of a type. ⚠ That trades whole-drawing eviction for per-object, so the far-left edge
can dissolve in pieces. ⚠ The families compete for that 500: **count trades in the Strategy
Tester's list, never off the chart.**

**5 · Never put two numbering systems on one panel.** Group headings carry the contract's numbers;
input titles carried the video's five step numbers. Reading down, the panel counted 4, 1, 2, 3, 5,
4, 6 and a strictly ordered model looked like it had none. ⚠ The tension is real and general: **the
contract groups by what a setting CHANGES, and a sequential model's steps do not map onto that
one-to-one.** Both orderings are right. Carry the group NUMBER and the step NAME — never both
numbers. Worth checking on any strategy here whose rules are a named sequence.

**6 · If a limit bounds what a reader can SEE, say so where it is seen.** Both affected tooltips
state their own limit. A cap discovered on the chart reads as a defect; a cap stated in the panel
reads as a boundary.

### 🔴 The ORDER of steps 3 and 4 is an OPEN QUESTION, and it is now a switch

Aaron, 2026-08-15: *"Why would I look for the gap after a one-minute shift? Shouldn't I look for
the point of interest first, and then once price is in it, look for the shift?"* He is describing
the standard SMC sequence, and **the objection is a good one on the mechanics**: under the video's
listed order the lower timeframe turns AGAINST the move and price then has to push FURTHER to reach
the resting limit.

`pbConfWhen` ships **Before the zone** (the video's listed order — shift, then rest a limit) with
**At the zone** as the alternative (freeze the zone at the sweep, price must travel into it, only a
shift that happens *inside* it counts, entry at MARKET).

⚠ **Neither branch is the "correct" one and the file says so at the input.** `education/learned/`'s
note is a transcript of what he SAID, and **its own header records that frame selection largely
missed the chart walkthrough** — so the five steps' ORDER is established and the MECHANICS are not.
**The honest move was a switch and a measurement, not a rewrite in either direction.**

⚠ **AT-THE-ZONE has to FREEZE the zone and could not reuse the live scan**, and the reason is the
kind that produces zero trades with nothing to debug: a gap price has traded into is marked
touched, so with untouched-only on **the scan drops the zone at the exact moment price arrives in
it** — the condition you are waiting for destroys the thing you are waiting on. `armDir` is stored
beside the frozen zone so a direction flip mid-session cannot hand a bear zone to a long.

⚠ **Two gates change meaning in that mode and both were adjusted rather than left to misfire**: the
"limit must rest on the far side of the market" test (block 6) is about a RESTING order and does
not apply to a market entry, and "maximum distance to the zone" is meaningless once price is inside
it. ⚠ **That one gate hides TWO waits that need opposite responses** — *price never reached the zone*
(a market fact) against *it got there and no shift came* (a rule fact). The state panel used to split
them and **the panel was removed 2026-08-16**, so nothing reports the difference now. Read it off the
chart, or put the panel back.

🔴 **THE MOVE THAT ALMOST SHIPPED A COMPILE ERROR IS THE REUSABLE PART.** The new block was written
into the LOCATION section, where the rest of the sweep state lives — and it reads the zone scan,
which is defined further down the file. Pine resolves top-down, so that is `CE10272`, and it would
only have appeared on the paste. **It was caught by a mechanical check, not by reading**: for every
top-level global, assert its first textual use is not before its declaration line. 185 globals, run
in seconds, and it is the same defect class `check_active_order.py` exists for arriving through a
different door. ⚠ **Run both after any block move in a Pine file.** The organising instinct — put
new state with the state it belongs to — is exactly what puts a read above its write.

### What this file does NOT have, and why

⚠ **`1 · Confirmation table`** — no JARVIS table, same as BOS, D and H4.
⚠ **`9 · Drawing: fibs`** — no fibs.
⚠ **`12 · Debug`** — held one per-event Pine Logs line; cut on Aaron's call. What it reported is on
the chart already, from the same state.
🔴 **`2 · Market structure` — the one place "the same four toggles everywhere" cannot be honoured
by porting.** Every other file runs its engine on the CHART frame, so drawing it is free; H4 ported
~1,000 lines in on that basis. This one runs the engine inside `request.security` on the 15m and
1m, and **Pine cannot draw from in there.** A chart-frame copy would paint the 5m's swings while
the strategy trades the 15m's — a chart that disagrees with the file under it, which is worse than
no drawing. The honest fix is a FEATURE (return the swing prices through the security call and draw
those), not a port. **Open — Aaron's call.**

⚠ **The six session strings are hardcoded, not inputs, and that is the exception to the collapse
rule rather than an example of it** — they DECIDE trades (the sweep pool is read off them). It is
safe only because every Pine file here has carried the identical DST-aware values since
2026-07-31, so a divergence would be a bug and not a setting. **A change to them belongs in every
file that carries the block.**
