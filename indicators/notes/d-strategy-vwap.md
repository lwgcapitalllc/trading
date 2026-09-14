# Notes — d_strategy.pine and the VWAP experiments

Why VWAP was added to the BOS strategy instead of D, the build of `d_strategy.pine` and why "an SOS then an opposite SOS" is not a signal, and the four quiet failures the VWAP add-on exposed. Moved VERBATIM out of `indicators/CLAUDE.md` on 2026-09-13 so it loads only when
needed; nothing was reworded or dropped. **New detail on this topic goes HERE**, and the
CLAUDE.md gets at most one index line.

---

## 2026-08-06 — 🟢 THE VWAP WENT INTO THE BOS STRATEGY INSTEAD, BECAUSE THE MEASUREMENT SAID D'S TRIGGER HAS NO EDGE

Aaron asked which combination of the two continuation strategies to pursue — `bos_strategy.pine`
(fibs + FVG) or `d_strategy.pine` (structure + fake shift + VWAP) — and asked for diagnostics
rather than an opinion. **Neither has a Python port, so neither could be swept.** The question
underneath it did not need one: replay the canonical `market_structure` + `vwap` engines over the
cached bars, find the bar each trigger would actually be IN on, and ask whether price reaches +2R
before −1R. No sizing, no ladder, no costs. **186,384 true-M15 XAUUSD bars, 2018-09-13 → 2026-08-07.**

🔴 **THE CONTROL IS THE LOAD-BEARING PART AND IT IS WHY THE ANSWER IS TRUSTWORTHY.** Gold went
1,200 → 4,300 across this window, so a long-side "edge" is free and any harness without a control
will find one. Every set is scored against **random entries matched on direction AND stop distance**.
The control lands on **33.3% with expectancy 0.000** — exactly the theoretical breakeven at 2R — so
the harness is measurably unbiased before any result is read off it.

| trigger | n | win rate | vs control | expectancy |
|---|---|---|---|---|
| **CONT** — with-trend BOS → 0.5 retrace | 778 | 37.5% | **+4.4% (+2.5σ)** | +0.125R |
| **D** — counter-SOS → VWAP reclaim | 833 | 33.1% | −0.4% (−0.3σ) | −0.007R |
| D — VWAP side only, no reclaim | 838 | 33.5% | −0.0% (−0.0σ) | +0.004R |

🔴 **D's trigger measures as RANDOM** — not losing, indistinguishable from a coin flip on 833 events
across eight years. ⚠ **And the reclaim latch built for it that same afternoon is worth nothing:**
−0.4% with it, −0.0% without. It is neither the problem nor the fix. ⚠ **At longer targets D goes
significantly NEGATIVE** (−2.8%, −2.1σ at 4R), which is the sharper statement: its entries catch
moves that die, so it is not merely edgeless, it is anti-selected for runners.

⚠ **The mechanical reason is the stop, and it is structural rather than tunable.** Median stop:
**CONT $3.43, D $7.24.** D's stop must sit beyond the whole shakeout extreme, so it is 2.1× wider —
same R buys half the position and needs price to travel twice as far.

✅ **VWAP IS A REAL FILTER, AND IT BELONGS ON CONT.** Pro-trend side: **39.9%, +6.8% (+2.8σ)**, median
stop **1.11 ATR**. Wrong side: 34.9%, +2.0% (+0.8σ), stop 1.80 ATR. It roughly doubles the trigger's
edge and cuts the stop 38% — **and the stop is the half that matters more**, because a tighter stop is
more size per unit of risk and is a mechanical gain rather than a statistical one.

🔴 **THE FIRST RUN OF THAT NUMBER WAS +15.9% AT +5.0σ AND IT WAS LOOK-AHEAD.** VWAP side was read off
the close of the bar the limit *fills* on, which selects bars that recovered by their close. Reading
the PREVIOUS closed bar halved it to +6.8%. **The transferable lesson is that the bug's symptom was
being too good, not erroring** — a filter evaluated on the same bar it acts on is look-ahead until
proven otherwise, and the flattering number is the one that survives a careless review.

✅ **Both robustness checks were run rather than skipped.** Across R targets the edge is +5.0% / +6.5%
/ +6.8% / +6.5% / +4.7% at 1R / 1.5R / 2R / 3R / 4R — stable, so not an artefact of the 2R choice —
and expectancy GROWS with distance (+0.094R → +0.257R at 3R), which is what a runner ladder is for.
By year, 7 of 9 positive; 2021 worst (−5.6%), 2022 and 2025 strongest. No single year carries it.

**What was then built:** `bosVwapReq` (F10) in `bos_strategy.pine` — a pro-trend-side gate,
default ON, ANDed into `longArmed`/`shortArmed`, with block code 7 so a refusal shows on the pink
Blocked tag and in the diag log. Full write-up in `docs/BOS_SPEC.md` §4b.

⚠ **A STATE, not a cross**, per Aaron's standing call — and re-read on every bar the limit rests, so
price closing back through VWAP *pulls* a resting order. A one-shot check at arming time would let a
setup fill hours later on the wrong side of the very line that qualified it.

⚠ **`na` VWAP returns FALSE, never true** — "cannot ask" and "no" must not be the same value, and for
a gate about to place money the safe answer is refusal. Costs at most one bar a day.

⚠ **IT IS A DROPDOWN, NOT A CHECKBOX, AND THAT IS THE INTERESTING CONSTRAINT.** TradingView keys saved
input values off declaration order *within each type*. The last `input.bool` in that file sits ~800
lines BELOW the use site, so a bool could not be appended (Pine needs declaration first) and inserting
one would have shifted `execDiagLog` and silently reset it on every chart. **There is no `input.string`
after that point, so a string shifts nothing.** Verified by scanning last-declaration-line per type
before and after. **The paste is safe on a tuned chart and needs no "Reset settings to defaults".**
Generalise it: when a new input must be READ early but must not DISTURB saved values, pick the type
whose last declaration precedes your insertion point.

⚠ **F10, not F9 — and the collision was nearly shipped.** `docs/BOS_SPEC.md` §4 already used F9
for staleness (`bosMaxDays`), while the Pine's inline comments only went up to F8, so "F9" looked
free from inside the file. Caught by reading the spec's table rather than the code's comments. **A
gate's number is a shared label across two documents; free in one is not free.**

⚠ **VWAP had been REMOVED from this file 2026-07-25 under `CE10117` (101,484 > 100,256 tokens)**, and
what came back is deliberately only the VALUE plus one `plot()` — not the settings block, colours and
styles that were cut. The old VWAP spent tokens DRAWING something nothing read; this one is read by
the arming condition. **If CE10117 returns, delete the `plot()` first and the gate last.**

⚠ **NO SLOPE TEST.** `d_strategy.pine` carries `execVwapSlope`/`execVwapSlopeBars`; only the SIDE
test was measured. Adding an unmeasured lever beside a measured one is how the measured one stops
being trustworthy.

⚠ **NOT COMPILED, and the measurement is on a SKELETON.** The probe replayed a plain with-trend BOS →
0.5 retrace → 0.886 stop — **not** this file's FVG-priced entry, the Sniper Zone, F1–F9 or the real
exit ladder. **+6.8% is a strong prior for the filter, never this strategy's own number.** The next
measurement is whether the FVG requirement adds to that edge or merely cuts the sample.

**The standing lesson is about what a diagnostic is FOR.** The request was "which combination should I
use", and the honest answer needed no strategy port at all — the canonical engines plus a control were
enough to say that one trigger has edge, the other does not, and the tool being brought to the table
belongs on the first one. ⚠ **The control is what made it an answer rather than an opinion**: without
it, D's 33.1% and CONT's 37.5% are both just numbers, and gold's own drift would have made the
long-side halves of BOTH look like edges. **Before believing any trigger study in this repo, find the
control — and if there isn't one, the study is a description of gold, not of the trigger.**

---

## 2026-08-06 — `d_strategy.pine`, and why "an SOS then an opposite SOS" is not a signal

Aaron specified a new setup from four hand-marked charts (two long, two short) and named it the
**D strategy** — "D as in dog, the dirty one". The sequence: a MATURE trend, then a counter-trend
SOS that shakes it out, then a with-trend SOS that resumes it. The third SOS is the entry; the
stop sits beyond the extreme the shakeout reached. Full spec + the four worked examples:
`docs/D_STRATEGY_SPEC.md`.

🔴 **The load-bearing finding is that the obvious implementation cannot work, and it fails
silently by firing constantly rather than by erroring.** **An SOS strictly ALTERNATES direction
by construction** — `is_choch = st.dir == -1` gates a bull SOS and the break then sets `dir := 1`,
so the next SOS on that chart can only be a bear one. "An SOS, then an SOS the other way" is
therefore **always true**: every consecutive pair on every chart satisfies it, so coding the
sequence as literally described marks every second SOS and looks like a working indicator.

What actually separates the D sequence from ordinary structure is an **asymmetry in maturity**
across the counter-SOS: the trend being RETURNED to must have printed `>= dMinTrendBos` BOS (it
was a trend), and the counter leg in between must have printed `<= dMaxCtrBos` BOS (it was a
shakeout, not a new trend). Those two integers ARE the strategy; everything else is drawing.
Implementing it needs state reaching **two SOS back**, which is why `dTrendDir`/`dTrendBos` are
read BEFORE the shift that overwrites them — at that instant they still describe the trend the
*previous* SOS killed.

⚠ **Measured on Aaron's own four examples, entering at the return-SOS CLOSE with the stop at the
counter extreme gives roughly 0.5R / 0.75R / 0.95R / 1.2R.** All four were directionally right
and only one cleared 1R. The cause is structural rather than bad luck: **an SOS confirms at the
TOP of the reclaim leg**, so the entry is at the expensive end and the stop is the whole leg away
— the same problem SOS Fade solves by resting a limit on the retrace instead of buying the break. A
`Retrace` entry mode is therefore shipped alongside, but `SOS close` is the DEFAULT so the tool
can be checked against the four reference setups before the entry is changed. Which one pays is
a measurement, not an argument.

⚠ **`dMaxCtrBos` is deliberately not 0.** Two of the four examples show a counter leg that broke
structure in its own direction before turning back — example D's ran ~33 hours and printed its
own higher highs — so a zero would refuse half the setups it was written from. ⚠ **`dMaxCtrBars`
is in BARS and does not transfer between timeframes**; the four reference charts span at least
two. ⚠ **"Sweep" here means a real CLOSE through the protected swing**, not a wick-and-reclaim —
the engine's SOS requires it, and every example prints a genuine LL/HH that stays. The wick
version would be a different strategy.

Two Pine details worth carrying: the drawing uses a **fixed stride** of 5 lines + 1 box + 1 label
per setup, with disabled TPs and a hidden box created TRANSPARENT rather than skipped, because a
variable stride splits a setup across an eviction and leaves orphaned levels on the chart with
nothing to explain them; and the alert is `alert.freq_once_per_bar_close` because the engine's
break test reads the LIVE close, so an SOS can appear and vanish intrabar.

🔴 **It shipped as an `indicator()` and had to be converted to a `strategy()` the same day** —
found by Aaron asking why there were no Properties to test. An indicator has no Properties tab
and no Strategy Tester, so the thing could mark the sequence and could not be SCORED, which is
the only reason it exists. ⚠ **The file was named `d_strategy.pine` throughout: the name is
not the declaration, and nothing in the repo checks that the two agree.** The conversion brought
a real execution layer — %-of-equity sizing, a TP1/TP2/runner ladder, breakeven-at-TP1, and a
cancel path for a resting Retrace order (stale, invalidated before the fill, or superseded by a
newer SOS). Three traps this repo has already recorded were guarded on the way in rather than
discovered again: **a `qty_percent = 0` rung is SKIPPED, never issued** (Pine reads 0 as
"unspecified" and closes the WHOLE position), **a rung stops being issued once touched**
(re-calling `strategy.exit` with a FILLED id places a NEW order rather than modifying it, so a
re-issued TP1 banks another slice every bar), and **the fill bar may not stage its own stop**
(BUG_exit_fill_price_mismatch — a resting limit is reached from the wrong side, so the fill
bar's favourable extreme is the approach to the order, not a move the trade made).

**The stop is FOUR anchors, not one** (Aaron's ask the same day, and the reason is that none of
them is known to be right). The sequence hands over three prices, so every sensible stop is a
point on the line between them: the **sweep extreme** (the honest invalidation, widest), the
**counter-SOS line** — the level the counter-SOS BROKE and price then reclaimed, which is
tighter and sits INSIDE the shakeout so a wick back in stops you out — a **percentage between
the two**, and a plain **percentage of the entry-to-sweep distance** for when the structural
stops are too wide to size against. The SOS line is the engine's own `st.bull_bos_high` /
`st.bear_bos_low`, captured at the counter-SOS and read at the entry on the SAME one-SOS lag as
`dTrendDir`, never re-derived from prices. ⚠ **A tighter stop is not a better trade** — it buys
a bigger position on the same risk budget and pays in stop-outs on setups that later worked, and
the two do not cancel at a fixed rate. ⚠ The ordering cannot invert: the counter-SOS bar closed
THROUGH its level and then went further, so sweep is always beyond SOS line is always beyond
entry, which is what makes the interpolation well-defined.

**The drawing is per FILLED TRADE, not per signal** — under `Retrace` those are different bars,
and a position block starting before the position existed would be drawing a trade nobody was
in. Each one gets the shaded shakeout, a red risk block that tracks the LIVE stop (so it
visibly collapses when breakeven lands), three reward blocks that **brighten on the bar their
target was reached**, and an entry callout whose TOOLTIP carries the whole breakdown — stop,
which anchor produced it, all three targets with R and size, the shakeout extreme, the SOS line,
and how many bars the shakeout ran. ⚠ **The drawing updates are na-guarded and guarded
SEPARATELY from the exits**: a drawing call on an `na` id is a runtime error that takes the
script down, and an order that stopped being issued because a BOX could not be drawn would turn
a chart bug into a trading bug.

**RESTYLED TO `sos_fade_strategy.pine`'s CONVENTIONS the same day** (Aaron: *"follow the mpc strategy
styling for all inputs and debugging annotations and take profits too"*). Same five input groups
— `D Setup` for the sequence gates (as SOS Fade uses `SOS Fade Setup`), `Strategy Execution` for everything
that decides what a trade DOES, plus `D Debug`, `Result Stats` and `Diagnostic Log`. Same
`d`-prefix / `exec`-prefix split, same `"   ↳ "` sub-input with `active =` on its parent, same
tooltip rule: what it does, ON vs OFF, and the one fact that changes the decision — never a
measurement essay, those live here. ⚠ **Declaration order is now FROZEN** for the same reason
that file records at its own time-stop pair: TradingView keys saved input values off declaration
order WITHIN EACH TYPE, so inserting a string or float above an existing one silently resets
every later input of that type on every chart running the script.

**The exit ladder is a PORT, not a lookalike.** `f_dRatchet` is `f_swingRatchet` unchanged, and
the staged stop, the three TP2 floor modes, the three trail methods, the time stop and
close-on-opposite-SOS all keep their shapes and defaults. 🔴 **One deliberate divergence, and it
is the interesting one: `sos_fade_strategy.pine` re-issues every exit rung unguarded on every bar,
which is safe THERE only because it ships both rungs at 0% — the rung is then skipped entirely
and the bug is unreachable at its defaults.** Calling `strategy.exit` with an id whose order
already FILLED places a NEW order rather than modifying it, so a re-issued TP1 banks another
slice of the remainder every bar. This file ships a real 50/25 scale-out, so it guards. ⚠ The
generalisation is worth more than the fix: **a latent bug held off by a DEFAULT is not fixed, and
copying the code without copying the default is how it gets discovered.** ⚠ `execTp1Pct`/
`execTp2Pct` are 50/25 here rather than mpc's 0/0 — riding the whole position to the runner
tested best on the SOS Fade bot over 6.6 years, which is a fact about THAT strategy, so it is stated in
the tooltip rather than copied as a default. ✅ **`execMinStopMode` is now present and ON at
`% of price` 0.08**, which the first build did not have at all: three of the four stop anchors
can land arbitrarily close to the entry, and `qty = risk / dist` is what detonated SOS Fade Run 4 and
BOS Run 1.

**The debug layer follows the same file too**: a pink `SETUP BLOCKED` tag with seven reason codes
in PRECEDENCE order (so a tag can never blame a downstream gate for an upstream refusal), bounded
by `debugDays`; an entry callout that recolours by result and appends the trade's R, with a
`keep for which results` filter; a `Result Stats` breakeven band, because the breakeven buffer
books a few cents and the Strategy Tester therefore files every scratch as a winner; and
`execDiagLog` writing one `log.info` per entry, result and block. ⚠ **"Ready" for the block tag
is `okDir` ALONE** — the one structural fact the sequence is built on. Every other gate is a
CHOICE and those are precisely what the tag exists to report; folding any of them into readiness
would hide the refusals worth seeing, which is the same rule stated at that file's own block tag.

**Status: not compiled, not measured, no Python port, no parity harness.** The state panel
reports the GATES rather than just the outcome, so a quiet market can be told apart from a gate
set too tight — those need opposite responses.

### 2026-08-06 (later still) — 🔴 THE VWAP ENTRY HAD NO RECLAIM IN IT, SO IT WAS NEVER THE SETUP ON THE CHART

Aaron pasted the D strategy with `execEntryMode = "VWAP side"` shipped as the default (set the
previous day) and read the trades off a real chart: *"they were not accurate… I specifically sent
you an image of the type of setups I would like to have, that pro trend."*

**He is right, and the file had it BOTH ways in writing.** `execEntryMode`'s own tooltip promises
*"enter on the first close **back** on the trend's own side of VWAP"* — and the word *back* was
doing all the work with none of the code behind it. Meanwhile `execVwapReq`'s tooltip states the
truth outright: *"It does NOT need price to have crossed back; a shakeout that never lost VWAP
passes on the same terms as one that reclaimed it."* That sentence was written about the FILTER
and was equally true of the ENTRY MODE, where it is not a caveat but the whole trade.
⚠ **So the two tooltips CONTRADICTED each other, fifty lines apart, and the wrong one was the
one describing the shipped default.** This is the repo's label-vs-code refrain arriving with the
label present in duplicate: one claim was aspiration, one was a confession, and nothing checked
either against the line that decides.

🔴 **`f_dVwapOk()` is a pure STATE test — `close > dVwap` for a long — and nothing anywhere
tracked whether price had ever been on the WRONG side.** So the sequence was:

1. Bull trend, bearish counter-SOS prints the shakeout.
2. On a 15m chart price is very often STILL ABOVE VWAP when that SOS confirms.
3. `f_dVwapOk(1)` is therefore already true on the very next bar, and the trade opens THERE.

No pullback, no basing, no reclaim — an entry at the top of the shakeout with the stop down at the
sweep extreme. ⚠ **And it is worse than one bad bar: the block gets a FREE LOOK EVERY BAR for
`dCtrBarsMax` (133 bars ≈ 33 hours on 15m), so a trade could also open a day and a half later on
an unrelated bar that happened to close on the right side of the line.** That is the second half
of "I don't know why some of those trades would take on".

**The setup in Aaron's image is a ROUND TRIP**: bullish structure → bearish SOS printing the LL →
price falls and BASES ON VWAP → closes back ABOVE it → that reclaim is the entry, stop behind the
counter-trend shift. Two events, on two different bars.

✅ **Fixed with `execVwapReclaim` (new, defaults ON) + a `dVwapLost` latch.** Price must close on
the wrong side of VWAP after the counter-SOS before a close back across it can be an entry.

⚠ **A LATCH, NOT `ta.crossover`, and the distinction is load-bearing.** A crossover is true on
exactly one bar, so any other gate refusing that bar — a stop too tight, a position still open —
would lose the setup permanently. The latch remembers the line was lost and lets the entry fire on
the first bar every gate agrees. This is also why Aaron's earlier "make it a STATE, not an event"
instruction is not contradicted: the SIDE test is still a state; what was added is a memory.

⚠ **The latch updates AFTER the SOS shift, deliberately**, so on an SOS bar it reads the direction
that bar just established rather than the one it killed — which is what lets the shakeout's own
SOS candle count as the start of losing VWAP, usually exactly where it starts. It is also tracked
UNCONDITIONALLY, whatever the switch is set to: a latch that only runs while its own switch is on
cannot be switched on mid-chart without lying about the bars it never watched.

⚠ **The new input is declared AFTER THE LAST `input.bool` IN THE FILE and must stay there.**
TradingView keys saved values off declaration order within each type, so a bool inserted beside its
siblings in `GRP_EXEC` would silently reset every later bool on every chart running the script.
✅ **Verified mechanically: all 45 HEAD inputs diff identical in type, order and title; exactly one
appended.** No "Reset settings to defaults" needed.

✅ The state panel stops merging two different states — `Waiting for price to lose VWAP` (the
pullback has not happened) vs `Waiting on VWAP reclaim` (it has, and price has not come back), and
the VWAP row now reads **`reclaimed`** rather than `pro-trend` once both halves are in. The old
wording let the panel look armed when it had nothing to enter on.

✅ Export twin REGENERATED from the parent rather than hand-edited, then re-verified: body
byte-identical except line 72's title, 51 plot columns.

🔴 **NOT COMPILED, NOT RUN, NOT MEASURED.** ⚠ **Two things to check before blaming the rule again,
and neither is a defect:** `dCtrBarsMax = 133` is **PINNED FOR 15m** (it is ~33h there and ~5.5
DAYS on 1H — running this on another timeframe measures a different strategy), and
`dTrendBosMin = 1` accepts a "trend" that printed a single continuation, which is far looser than
the multi-leg run in the reference image; **2 is the honest value for that picture** and is a
tuning decision, not a fix, so it was left alone.

**The standing lesson is one this repo has met from the label side and meets here from the
BEHAVIOUR side: a correct, specific warning was sitting in a tooltip fifty lines from the code it
described, attached to the wrong control.** It documented the filter and was fatal to the entry
mode, and nobody read it as being about the entry mode — including the person who wrote it. When a
caveat explains why something is *acceptable* for one consumer, check every other consumer before
the same sentence becomes the bug report.

### 2026-08-06 (later) — VWAP, and the four quiet failures adding it exposed

Aaron asked for an EARLIER entry: after the shakeout, take the trade when the close is back on
the pro-trend side of VWAP, without waiting for the with-trend SOS — plus, explicitly, *"if it
is already supported by the VWAP and it does not have to cross back over, take those trades."*
**So it is a STATE test, not a cross event**: a shakeout that reclaimed VWAP and one that never
lost it are the same signal, and a `ta.crossover` would have silently refused half of what was
asked for. Shipped two ways because they are two questions — `execEntryMode = "VWAP side"` (the
trigger) and `execVwapReq` (a filter on any mode), **both off by default so the morning's
baseline stays reproducible**, with `execVwapSlope` / `execVwapSlopeBars` as the sub-gate and
`execShowVwap` drawing the exact line the rule reads. It is **`ta.vwap(hlc3)`, the session
VWAP** — an anchored-at-the-shakeout variant would be a second VWAP implementation, which this
repo forbids, and would not be the line "already supported by" describes.

🔴 **It is a DIFFERENT TRADE, not a cheaper D, and that has to be said in the results**: the
with-trend SOS is the only evidence the shakeout failed, and this drops it.

**Four things would each have failed quietly, and three of them are this file's own recorded
traps arriving from a new direction.** (1) **Direction could no longer be read off
`st.bull_sos`** — the block tag and the `B|` log line both inferred a candidate's side from the
SOS on the same bar, correct only while every candidate arrived on one, so **every VWAP
candidate, long or short, would have drawn and logged as a SHORT**; `dCandDir` now carries it.
(2) 🔴 **`cfg_modes`' entry digit was 2-way** (`SOS close ? 0 : 1`), so `"VWAP side"` decoded as
**Retrace** — a stored run described as a different entry model, with total confidence. **This
is the `execRunnerTrail` trap of 2026-07-26 exactly: a code that collapses a widened dropdown
does not fail, it lies. Whenever an option is added to any input, find its cfg digit in the same
commit.** (3) 🔴 **The export's `f_xCand()` rebuilt candidate direction from `st.bull_sos`**, so
it returned 0 on every VWAP candidate and **would have blanked px_cand_dir, px_ctr_ext,
px_rcl_ext, px_sos_lvl and all three px_gate_\* columns for the whole mode** — a clean CSV with
nothing in it, the failure an export is least able to report. It is **deleted, not repaired**:
the parent already records `dCand*` for every candidate at decision time, so there was never a
second claim worth maintaining, only one that could disagree. Its `[1]` lookups were wrong for a
second reason too — `[1]` means "before the shift" only on a bar where the shift RAN, and
`dCurBos` can be incremented by a plain BOS on a non-SOS bar. (4) **A state test re-fires**: the
SOS trigger is self-limiting because an SOS is one bar, but a state is true on every bar, so with
only `bBusy` stopping it a stopped-out sequence would re-enter immediately and keep going until
the bar cap expired — `dSeqTaken` latches, released only by the next SOS shift.

⚠ **The minimum-stop guard stops being optional in this mode.** Entering early means entering
close to the sweep extreme and the stop is anchored at that extreme, so the better the entry the
smaller `dist`, and `qty = risk / dist` grows as it shrinks. On the SOS path the whole reclaim
leg sits in between and the hazard is rare; here it is the normal case. ⚠ **The new inputs are
declared at the END of the file, after `execDiagLog`, and must not be tidied into `GRP_EXEC`** —
the last input of every type sits at or before it, so this shifts nothing and **no "Reset
settings to defaults" is needed**; moving them up would silently reset every later bool and int
on Aaron's charts. ⚠ **VWAP resets at the trading-day open** and `dCtrBarsMax` allows ~33h on
15m, so a sequence can straddle the reset — that is what the chart's line does, and a filter
quietly reading a different VWAP would be the worse failure. ⚠ **`ta.vwap` needs volume** and
raises rather than returning `na` on a symbol without it. ✅ The export was **regenerated by its
own recipe**, body re-diffed to exactly line 60's title, **plot count 48 → 51** (`px_vwap`
ungated on every bar — which is what makes the rule re-priceable offline from a run taken with
the gate OFF — plus `cfg_vwap_slope_bars`, plus the parent's new visible VWAP plot). Block reason
**9** added, numbered last and ranked fifth, raised by the filter only. **NOT COMPILED, NOT RUN,
NOT MEASURED.** Full write-up: `docs/D_STRATEGY_SPEC.md` → *The VWAP entry*.

### 2026-08-06 (later still) — the sweep was already there, and a chart said the EXIT is the problem

🔴 **THE COUNTER-SOS *IS* THE LIQUIDITY SWEEP, AND SETTLING THAT DELETED A 500-LINE FEATURE
BEFORE IT WAS WRITTEN.** Aaron describes D as *"a liquidity sweep and a fake break of
structure"*, and the near-miss was reading that as two conditions: a liquidity-pool port
(previous day/week high-low, H4, session high-low, EQH/EQL) lifted out of `sos_fade_strategy.pine`
to gate the shakeout on having *taken* something. **It is one event, not two.** The
counter-SOS closes through the trend's last protected swing — the HL in an uptrend, the LH in
a downtrend — and a protected swing is exactly where the stops rest. The break and the sweep
are the same bar. ⚠ **A pool test would have been a SECOND claim about one event**, and the
two disagree constantly: a shakeout can break the trend's HL without reaching the previous
day's low, and that is still the setup — so the gate would have refused real trades while
looking like a quality filter. ⚠ **`dSosLvl` is therefore the swept level itself**, captured
from the engine's own `st.bull_bos_high`/`st.bear_bos_low`, which is what makes the
`Counter-SOS line` stop anchor mean *"back above the liquidity that was taken"*. ⚠ **D needs
no liquidity engine and must not grow one** — this file embeds only `structure_engine.pine`.

🔴 **A REAL DEFECT WAS FOUND BY READING THE NEVER-RUN VWAP CODE, AND IT IS LATENT AT THE
DEFAULT AND LIVE THE MOMENT YOU TUNE.** `dVwapSlope` is `dVwap - dVwap[execVwapSlopeBars]` — a
history offset taken from an **INPUT**, not a literal. Pine sizes each series' history buffer
from the offsets it observes on the first bars, so at the shipped 4 it sizes for 4, and raising
the slope input toward its own declared `maxval` of **200** throws *"the requested historical
offset is beyond the historical buffer's limit"* **at runtime**. ✅ Fixed with
**`max_bars_back = 300`** on the `strategy()` call in BOTH files, covering the whole declared
range; the export twin took the identical edit and its body re-diffed to **exactly line 68's
title**. ⚠ **It is not cosmetic — do not drop it on a future regen.** **The standing lesson is
the repo's own from a new angle: a `maxval` is a promise that the whole range works, and here
only the default did.** Anywhere an input feeds a `[]` offset, the buffer has to cover `maxval`,
not the default.

🟢 **AARON MARKED A LIVE EXAMPLE AND IT VALIDATED THE ENTRY WHILE CONDEMNING THE EXIT.**
XAUUSD 19→23 Aug: bullish structure, a bear SOS printing the **LL at ~3,996** (the shakeout),
price basing along VWAP for a dozen-plus bars, then a **close back above it at ~4,012**, stop
behind the LL, run to **4,166**. ✅ **The tool already expresses it exactly** — `execEntryMode
= "VWAP side"` with the shipped `execSlMode = "Sweep extreme"`; nothing needed building. 🔴
**But 1R is $16, the full run is 9.62R, and the shipped ladder caps it at 2.10R** — TP1/TP2/TP3
land at 4,028 / 4,044 / 4,060 and **all three fill on 21 Aug**, so the 4,060 → 4,166 leg never
happens. **7.53R left on the table on the one trade the strategy exists to catch.** That is the
`0.3×1 + 0.3×2 + 0.4×3` arithmetic ceiling the 8.3-year run already found BINDING (max R
**+2.11**, 16 trades on it); the chart supplies the size of the miss. ⚠ **So "catch the entire
run" is an EXIT change, not an entry one, and it is the answer SOS Fade already reached** — that bot
ships both rungs at **0/0** and rides to the runner trail because its money lives in the tail.
D pairs a continuation premise with a scale-out exit. ⚠ **Do not read 9.62R as achievable**: a
structure trail exits on the turn, not the high, so 5–7R is the honest expectation.

🟢 **THE DEFAULTS WERE THEN MOVED TO THAT CONFIGURATION (Aaron's request, same day), SO A FRESH
PASTE *IS* THE RUN.** Four values in BOTH files: `execEntryMode` **"SOS close" → "VWAP side"**,
`execTp3R` **3.0 → 0**, `execTp1Pct` **30 → 0**, `execTp2Pct` **30 → 0**. `execSlMode` was
already `Sweep extreme` — the stop Aaron drew — and the trail, risk %, min-stop and time stop
are untouched. ⚠ **THE BASELINE THEREFORE MOVED: pin `"SOS close"` with 30/30/40 and TP3 = 3.0
to reproduce the 218-trade / +14.03R run.** ⚠ **VALUES AND TOOLTIP STRINGS ONLY — no input was
added, removed or reordered, verified mechanically** (the 45 `input.*` declarations diff
byte-identical to HEAD on type, order and title), so TradingView's saved-value keying is
untouched and **no "Reset settings to defaults" is needed**; the flip side is that an EXISTING
chart keeps whatever is already set, so confirm on the panel rather than assuming. ⚠ **The
export twin took every edit and re-diffed to exactly line 72's title**, plot count still 51.
🔴 **Three comments and four tooltips had to move with them, and that is not tidying** — the
header asserted *"the default stays SOS close"*, and the rung comment said *"these ship as a
real scale-out"*. Both were about to become the exact `eqExemptFvg` failure this file records
from three days earlier: a correct, specific warning left standing directly above the line that
invalidated it. ⚠ **`execTp1R`/`execTp2R` must stay above 0** — at 0% size the TP *prices* are
still what stages the stop to breakeven and hands the runner to the trail. ⚠ **The
`qty_percent = 0` guard is now LOAD-BEARING rather than latent**: it was unreachable while the
rungs shipped at 30, and it is the only thing between this default and `strategy.exit` closing
the WHOLE position at TP1. **That is the lesson the same section already carries from the other
direction — a latent bug held off by a default is not fixed — met here as its mirror: changing
a default is what ARMS the guard, so check what the old value was hiding.**

⚠ **One hazard is NAMED and NOT FIXED, and it must be read out of the trade list.** The VWAP
entry fires on the first qualifying bar after the counter-SOS and nothing requires the shakeout
to have DEVELOPED — so if price is already on the pro-trend side of the session VWAP one bar
after the break, the entry fires with `ctrExt` a bar or two old. That is the smallest stop this
strategy can make and `qty = risk / dist` makes it the largest position. Aaron's example based
for a dozen-plus bars, so it did not bite. The only guard is `execMinStopMode` at 0.08% —
**$3.20 on $4,000 gold, measured on SOS Fade and never here.** Check for any trade whose 1R is under
about $5; the fix would be a minimum shakeout length, not a bigger floor.

### 2026-08-06 (later still) — the JARVIS REV row stuck on TAKE PROFIT after a 0.5 entry

🔴 **A short entered at 0.5 banked TP3 and the row never cleared — it sat on `TAKE PROFIT SHORT ·
TP3 · close the rest` indefinitely.** `mpc_jarvis.pine` only; nothing here reaches a trade.

**Two flags describe one event and only one of them survives a shallow entry.** The SOS Fade leg's
completion death reads the DRAWN FIB's `fibo7Touched`, and that flag is gated — the fib block
checks its three TP levels inside `if fibo618EverReached`. An EARLY 0.5 entry never reaches
0.618, so on that leg `fibo618EverReached` stays false, `fibo7Touched` can NEVER be set, and the
completion death is **unreachable**. The leg then survives until an opposite SOS or a
continuation BOS happens along, which can be hours. Meanwhile the SOS Fade engine's own `aplusX_tp0`
fires perfectly well on that same leg, because its gate is `aplusX_618[1] or aplusX_half[1]` —
half is enough. **The row knew the trade was finished and the death did not.**

✅ Fixed by adding `or aplusL_tp0` / `or aplusS_tp0` to the two death conditions. `aplusX_tp0`
**is** TP3 — it is set on price reaching `fiboP7`, the 0.0 leg origin, the level the drawn fib
labels TP3 — so it is the identical death read from the side that can see it. `fibo7Touched` is
KEPT: it still fires first on a deep entry (the fib block runs earlier in the bar) and it covers
a leg that returned to 0.0 without the engine banking the rungs in order.

⚠ **This is the SAME defect `f_rev15` was fixed for on 2026-08-04, from the opposite side.** That
pass found the 15m security engine missing the win death that the chart-side engine had, and
recorded the chart side as complete. It was not — it was complete only for a deep entry. **A
death condition that has been checked on one entry tier has been checked on one entry tier.**

⚠ It kills one bar LATE (the death block runs before the TP tracking that sets the latch) — the
same lag `f_rev15` already accepts for its own `or S_tp0`, and left the same way rather than
adding a second clear site that can drift from this one. ⚠ It cannot arm a B leg (`bLegArmL/S`
require the continuation-BOS branch plus `not aplusX_half and not aplusX_618`). ⚠ RE-ENTRY after
TP1/TP2 is unaffected — only `tp0` kills, and after TP3 the row's own instruction is "close the
rest", so there is nothing left to re-enter.

⚠ **The death ALERT had to move with it or the fix would have shipped a new wrong message**: the
chain's last branch fires on any drop out of the SOS stages, so a leg now retiring on a WIN would
have announced `SETUP DEAD - died at stage 4 of 4`. It reads `_alDone` (`aplusX_tp0[1]`, at `[1]`
because the death cleared the latches earlier the same bar) and says `COMPLETE - TP3 banked, leg
closed` instead. **A new death is a new alert, whatever the alert block looks like it says.**

⚠ **NOT COMPILED** — there is no local Pine compiler and this file has hit CE10117; the change is
two boolean terms, one local and one ternary, so it is small but not free. No input was added,
renamed or reordered, so **no "Reset settings to defaults" is needed.** ⚠ No parity harness can
see this: the SOS Fade sequence tracker exists only in `mpc_jarvis.pine` and `sos_fade_strategy.pine`. ✅
**Checked rather than assumed — `sos_fade_strategy.pine` and `b_leg_strategy.pine` carry ZERO
references to `aplusL_tp0`/`aplusS_tp0` and have no TAKE PROFIT row**: their restored table is the
EXT/INT structure pair only, so the stuck row cannot occur there and neither file was touched.
