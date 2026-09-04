# SMC Session Sweep — strategy spec

**File:** `strategies/tradingview/smc_session_sweep_strategy.pine`
**Source of the idea:** `education/learned/2026-08-11-smc-strategy-too-simple-to-ignore-1150-trades.md`
(Lewis Kelly, "This SMC Strategy Is Too Simple to Ignore", https://youtu.be/lTrDQPVfJyI)
**Status:** built 2026-08-11; standardised onto the house input panel and colour palette
2026-08-14; renamed 2026-08-15. **Not compiled, not measured, no Python port, no parity
harness.**

---

## The rename, and the file that went with it (2026-08-15)

Both were Aaron's call, in the same breath as *"I think we need to port over to Python"*.

**`m15_playbook_strategy.pine` → `smc_session_sweep_strategy.pine`, and this spec moved
from `M15_PLAYBOOK_SPEC.md`.** The old name named the timeframe the DIRECTION is read on
and said nothing about the setup, and it wore the `mpc_` prefix of a Pine family this file was
never part of — it came from a video note, not from `mpc_jarvis.pine`. The new name is the
setup: a session sweeps the previous session's level, and the model trades the reversal off it.

🔴 **`indicators/engines/m15_playbook.pine` was DELETED.** It was the 270 KB indicator half
of the pair — structure, sessions, gaps, order blocks and a confirmation table, drawing only,
no orders, so the Strategy Tester could never score it. ⚠ **It was also the file the strategy's
structure engine was lifted byte-for-byte OUT of**, so that block's provenance now points at
`engines/market_structure/`, which is the canonical implementation and the only other copy.
Recover it from git if a drawing is ever wanted back.

⚠ **The old names are NOT scrubbed from `HISTORY.md` or the build notes.** A diary entry
records what a file was called when the thing happened; rewriting it makes the record false.
Grep either name.

---

## The five steps, as implemented

| # | Video | This file |
|---|---|---|
| 1 | Direction — 15m swing structure only | `pbDirTf` (default `15`) run through the canonical structure engine; `dir` +1/−1 gates the side |
| 2 | Location — the current session sweeps the previous session's high/low | pool **frozen at the session open**: London takes Asia's, New York takes London's. Sweep = any trade through it |
| 3 | Confirmation — the 1m flips to agree with the 15m | `pbConfTf` (default `1`) run through the same engine; a **new** CHoCH in the direction timeframe's direction, after the sweep |
| 4 | Point of interest — nearest untouched 5m OB or FVG | `pbPoiTf` (default `5`) fair value gaps. Nearest LIVE gap on the far side of price, skipping any price has already traded into |
| 5 | Targets — TP1 previous day's low, TP2 previous week's low | `pdl`/`pdh` and `pwl`/`pwh`, ordered by distance and validated against the entry |

Entry is a **limit into the zone** (`execZoneEntry`: proximal edge by default), stop
beyond the zone's far edge plus a buffer, size = risk% ÷ stop distance.

---

## The decisions the video does not make, and what was chosen

**The pool is frozen at the session open.** Asia and London overlap, and so do London
and New York, so "the previous session's high" is ambiguous while both are running. It
is read once, at the moment the new session opens, and never again — a level that moves
under the setup watching it is not a level.

**New York wins the overlap.** It is the later session and its pool is whatever London
had made by the time it opened.

**A shift only counts after the sweep.** The sequence is location *then* confirmation; a
1m flip before the sweep is a different setup wearing the same flag.

🔴 **Whether the shift comes BEFORE or AT the zone is not decided, and is a switch
(`pbConfWhen`, 2026-08-15).** The video lists direction → location → confirmation → point of
interest, so the shipped default finds the zone *after* the shift and rests a limit in it. Aaron's
objection is that the standard SMC sequence is the other way round — price reaches the zone, and
the shift happens *inside* it — and on the mechanics he is right: under the listed order the lower
timeframe turns against the move and price then has to push further to reach the order. **The note
this was built from is a transcript, and its own header records that the chart walkthrough was
largely missed, so the ORDER of the five steps is established and the mechanics are not.** Run both
and let the tester decide. ⚠ At-the-zone freezes the zone at the sweep — the live scan would drop
it the moment price traded into it — and enters at market.

**The confirmation is a COUNTER, not a flag.** A change of character is an edge, and a
flag read back through `request.security` is a level that stays true — so the engine
returns how many shifts it has seen and the strategy compares it with its own previous
bar. Nothing else can tell "it just shifted" from "it shifted at some point".

**The proximal edge depends on the direction.** It is the bottom of a zone above price
and the top of a zone below it. Written without the direction, every long rests at the
far edge of its gap.

**A limit must rest on the far side of the market.** If the chosen zone is no longer
beyond price by the time the setup completes, the setup is refused (block code 6) rather
than sent as a limit that fills immediately at market.

**Targets are ordered by distance, not by name.** Whether the previous day's low is
nearer than the previous week's is a fact about the week. A target on the wrong side of
the entry, or nearer than `execMinRr`, is not a target — `execTpFallbackR` substitutes a
fixed R multiple, or the setup is refused if that is 0.

**One trade per session.** A fill latches the session; the next arm waits for the next
session open.

**The fill bar may not stage its own stop.** A resting limit is reached by price coming
to it from the wrong side, so the fill bar's favourable extreme is the approach to the
order, not a move the trade made. (`indicators/docs/BUG_exit_fill_price_mismatch.md`.)

**A rung is issued only while unfilled.** Calling `strategy.exit` again with an id whose
order has already filled places a NEW order rather than modifying it, which banks another
slice of the remainder every bar.

---

## The panel and the palette (2026-08-14)

The inputs use the numbered groups every strategy in `strategies/tradingview/` uses, so section 5
is Entry whichever file you open. The contract, and the rule deciding which section a new toggle
goes in, live in `strategies/tradingview/CLAUDE.md` — not here.

**Sections 3, 4, 5, 6, 7, 8, 10, 11 are present. 1, 2, 9 and 12 are absent and the numbering does
not close up**, because the number is the address:

| absent | why |
|---|---|
| `1 · Confirmation table` | this strategy reads no JARVIS table — same as BOS, D and H4 |
| `2 · Market structure` | its engine runs INSIDE `request.security` and Pine cannot draw from there. A chart-frame copy would draw the 5m's swings while the strategy trades the 15m's. **Open — Aaron's call**, and the fix is a feature (return the swing prices through the security call) rather than a port |
| `9 · Drawing: fibs` | no fibs |
| `12 · Debug` | held one per-event Pine Logs line; cut 2026-08-14 (*"for events, we don't need that"*). Everything it reported is on the chart, read from the same `sBlk`/`lBlk` |

**The session drawing is a BOX per session round its own high and low, not a full-height stripe,
and that is a fact about the model rather than about taste: the box's top and bottom ARE the pool.**
What London sweeps is the top of Asia's box. A box is also left standing when its session ends —
it is the level the next session hunts.

**`Show the previous session's high / low` defaults ON**, unlike the other draw toggles. It is
step 2 drawn — the single line that explains why the strategy did or did not act on a given day.

⚠ **The chart shows the last 100 trading days of sessions and the last 40 trades, and neither
limit is a bug.** TradingView allows 500 drawing objects per script, shared across all three
families; the split is at the top of the Pine and both tooltips state their own limit. **Read trade
counts off the Strategy Tester's list, never off the boxes on the chart.**

**The six session strings are hardcoded, not inputs.** They DECIDE trades — the sweep pool is read
off them — which normally means they belong in a trade group rather than being collapsed away. They
are frozen anyway because every Pine file in this repo has carried the identical DST-aware values
since 2026-07-31, so a divergence here would be a bug and not a setting. ⚠ **A change to them
belongs in every file that carries the block.**

**Every colour a trade is drawn in is `sos_fade_strategy.pine`'s.** Change a value there and copy it
down, never pick one here. ⚠ **The TABLE palette is gone with the state panel** — if a table ever
returns, copy A+'s table colours rather than reusing the position ones.

**The panel trim, 2026-08-16** (Aaron: *"there are too many inputs now… so I could focus on the
strategy"*). The **pool-line toggle** went and the LINE is now always drawn — it decides nothing,
but it is step 2, and it is the one line that says why the strategy did or did not act on a given
day. The **state panel** went with it. 43 inputs → 42.

🔴 **The panel was removed, restored, and removed again inside one session, and the round trip is
worth more than the feature was.** Aaron cut it, then said *"let's add it back — I just didn't
understand how to read it"*, so it came back relabelled; then, seeing it: *"just the pool lines."*
**The relabelling was still the right read of the middle step** — the original rows were named after
the code (DIRECTION, POOL, SWEPT, SHIFT, ZONE), which is a dump of internal state rather than
anything a person reads. ⚠ **The actual lesson is upstream of that: "add it back" arrived in a
sentence whose first clause was about the POOL LINE, and it was read as being about the panel.**
An ambiguous referent was resolved silently instead of asked about, and the cost was two rebuilds.
⚠ **Second, standing: "I don't need this" and "I can't read this" look identical from outside and
have opposite fixes** — ask which one before deleting a diagnostic.

⚠ **What was lost with it, stated so it is a decision rather than a discovery.** The panel was the
only place two things appeared on screen: a refusal caused by the **execution clock** (block code 11
is deliberately untagged), and the split between *price never reached the zone* and *it got there
and no shift came*. Both now have to be read off the trade list.

⚠ **The first paste costs one "Reset settings to defaults"** (every input moved), and in the same
visit untick Style → **"Trades on chart"** — this file draws its own position box, entry triangles
and result callout, so the built-in markers double-draw at a second set of exit prices.

---

## Known gaps — read before quoting a number

**Only the FAIR VALUE GAP half of step 4 is modelled.** The video's point of interest is
"an order block OR a fair value gap". A gap-only rule takes strictly FEWER setups than he
does, so a low trade count here is partly this. Adding order blocks means either a second
OB implementation inside `request.security` (which this repo forbids) or running the
strategy on the zone timeframe itself.

**Everything crosses a `request.security` boundary.** The 1m confirmation and the 5m zone
are observed at the CHART bar's close — up to one chart bar late, never early. Run it on
5m for fidelity; 15m buys more history and a coarser trigger.

**TradingView loads limited 1-minute history.** With the confirmation ON, the far end of a
long backtest may see no 1m structure at all and simply take no trades there. Read the
trade list's first date against the chart's, and never read the tester's window header as
what arrived — it states what you asked for. (`indicators/CLAUDE.md`, 2026-08-07.)

**No control.** Gold tripled across any window this will be run on, so a long-side result
is free. Before believing any edge here, score it against random entries matched on
direction and stop distance — `backtest/tools/trigger_edge.py` is the shape that has
already caught this twice in this repo.

**The video's own numbers are two different books.** The 6.14 average win/loss and 3.07
profit factor are the 230-trade subset; across all 1,154 trades it is 3.93 and 1.92. The
title quotes one and the headline stats the other.

---

## Measured: six runs, and the course book they were compared against (2026-08-16)

Six TradingView Strategy Tester exports, XAUUSD, 2023-01 → 2026-08, git-ignored scratch under
`engines/*VANTAGE*.csv`. ⚠ **Which export used which settings is NOT recorded** — the inference
that the two best runs had the confirmation OFF rests on their trade counts and is unconfirmed.

| file | chart | trades | win rate | profit factor | net on $10k | max drawdown | payoff |
|---|---|---|---|---|---|---|---|
| `b6b58` | 15m | 224 | 20.1% | 1.02 | +$291 | 31.4% | 4.06 |
| `9f31e` | 5m | 323 | 16.7% | 1.11 | +$2,586 | 47.7% | 5.53 |
| `e5c52` | 5m | 287 | 19.5% | 0.91 | −$1,272 | 27.3% | 3.75 |
| `de22c` | 15m | 288 | 19.8% | 0.85 | −$1,947 | 24.3% | 3.43 |
| `8bf94` | 5m | 485 | 17.1% | 1.02 | +$791 | 59.5% | 4.93 |
| `65746` | 15m | 354 | 19.8% | **1.15** | **+$4,820** | 33.2% | 4.67 |

**The win rate never leaves 16.7-20.1% across six configurations.** Break-even at a 4.7 payoff is
~17.6%, so every run straddles the line. Every run's profit is 1-3 trades — `b6b58` minus its
single best trade is −$790. All six lean short (~170 short against ~120 long) in a market that
tripled. The confirmation IS wired (switching it off moved the 15m count 288 → 354); it just does
not move the hit rate.

**The course book, for comparison** — `education/smc/05-my-full-trading-strategy/`, the data review
in `transcripts/25-full-data-synopsis.txt`. ⚠ **`summaries/25-full-data-synopsis.md` is an empty
`to-summarize` stub — the numbers are only in the transcript.** 2.5 years, 1% of the INITIAL
balance per trade, no commission or swap: **230 trades — 62 wins, 126 losses, 42 breakeven.** ~33%
wins excluding the scratches, average reward-to-risk 6.2, profit factor ~3.07, **worst drawdown
6%**, average +9%/month, best month +25% (Apr 2024), worst −3.7%, max 7 losses in a row. He redid
all of 2024 to strip a compounding skew.

⚠ **The 1,154-trade figure is from the YouTube video, not the course.** The course book is 230.

**His setup table, after he removed the miscounted 2024 data:**

| setup | trades | win rate | note |
|---|---|---|---|
| London sweeps Asia | most traded | 30% | profit factor 3, payoff 6.8 — **the one this file implements** |
| London sweeps Frankfurt | 60 | 26% | +31% return, payoff 5.85 |
| NY continuation from the London POI | 19-20 | **63%** | his A+ |
| NY sweep of the Lull | — | **55%** | |
| NY sweeps Asia | 3 | — | his only losing setup |
| Frankfurt sweep continuation | 2 | — | −1.5% |

Strong points of interest beat weak ones (33% against 29%). New York setups are rarer and better
(+105% against London's +93%).

**Entry-hour distribution, pooled across all 1,961 trades in the six exports.** ⚠ The timezone is
INFERRED as New York — London 08:00 local is 03:00 NY and the trades start at hour 3 — and ~2% (40
trades at hours 18-19) is unexplained.

Restricted to his execution hours: **490 trades, +$17,716.** The 1,471 trades outside them lost
**−$12,448.** 🔴 **Read that as a lead, not a result.** It pools six overlapping configurations so
trades are counted more than once; it is a slice chosen AFTER seeing the data, which is the exact
overfitting trap the course itself warns about; and one hour carries +$21,753 of it, which is the
same concentration problem the table above already flags. Hour 19's 14 trades at a 100% win rate
look like an edge case rather than a result.

### The minimum-stop floor, measured

Read off the same six exports. A trade whose every exit slice is a loss exited at its stop, so
`|entry − exit|` on those is the stop distance. **1,596 such trades**, entry prices $1,814-$5,432.

| | in dollars of gold | as % of price |
|---|---|---|
| smallest | 0.28 | 0.0105% |
| bottom tenth | 1.91 | 0.0851% |
| lower quarter | 2.58 | 0.0961% |
| median | 3.93 | 0.1293% |
| upper quarter | 6.28 | 0.2094% |
| top tenth | 10.90 | 0.3560% |

🔴 **The distribution is sheared off almost exactly at the old 0.08% floor** — the bottom tenth sits
at 0.085%. That is what a binding floor looks like. ⚠ **It is evidence the floor was CUTTING, and
not evidence of what it cost**: a refused setup never reaches a trade list, so the cost cannot be
recovered from this data by anyone.

**Why 0.03% and not 0.** Vantage's measured XAUUSD spread is **$0.22** (`backtest/fills.py`,
1,494,459 ticks) and these runs charge none of it. Spread as a share of risk: **6%** at the median
$3.93 stop, **22%** at $1, **over half** at $0.40. Script:
`scratchpad/stopdist.py` (session-local, not committed).

**What changed in the file on 2026-08-16, and what did not:** three switches added
(`execBeOnShift`, `execUseWindows`, `execTp1Mode = Fixed R`), all defaulted ON, all UNMEASURED.
Four course rules still absent: order blocks as entry objects, POI quality grading, the news
blackout, and six of his eight setups. Detail and the caveats on each:
`strategies/tradingview/CLAUDE.md` → *Three rules added from the course*.

---

## The shipped defaults (2026-08-17)

Aaron's own chart settings, moved into the file at his request so a fresh paste starts where he is
actually trading rather than where the course is.

| input | was | now | what it means in English |
|---|---|---|---|
| `pbRequireConf` | `true` | **`false`** | No lower-timeframe change of character required. Entry rests in the gap on the sweep alone. |
| `execTp1R` | `5.0` | **`3.5`** | First target at 3.5x risk. 5 is the course's number. |
| `execTp1Pct` | `50` | **`80`** | Four fifths banked at the first target; the runner is a fifth. |
| `execRiskPct` | `1.0` | **`4.0`** | 4% of equity lost if the stop is hit. |
| `execMinStopVal` | `0.03` | **`4.00`**, mode **Fixed $** | Refuse a trade whose stop is nearer than $4 of gold. ⚠ **Changed again 2026-08-17 and this one IS measured** — see below. |
| `pbShowSess` | `false` | **`true`** | Session boxes drawn. |
| `pbPoiTf` | `"5"` | `"5"` | **Unchanged** — the 5m gap is still required. |

🔴 **NONE OF THESE IS MEASURED.** No sweep produced them and no run compares them to what they
replaced. They are recorded here because a default in a file is indistinguishable from a finding
six weeks later, and the set they replaced had already been read that way — `5.0` was the course's
first target, but `50` was nobody's number and had been sitting there since the file was written.

⚠ **Three of them are the risk path and they move together.** 4% per trade is four times the old
figure, and the stop floor rising 0.03% → 0.07% cuts off the tightest stops — the ones that would
have produced the largest positions. The two changes push size in opposite directions and the net
effect on drawdown is unknown until someone runs it. **The floor is the only guard between the
sizer and a stop a few ticks wide**, so it is the number to check first if a result looks wrong.

⚠ **Turning confirmation off does NOT retire the confirmation timeframe.** `pbConfTf` still drives
breakeven-on-shift, cancel-on-flip, and the SOS marker. Both it and `showSosMark` were ungated in
the same pass for exactly that reason — see `strategies/tradingview/CLAUDE.md` → *A CASCADE AUDIT*.

⚠ **A default change resets nothing on an existing chart.** TradingView keeps whatever is saved
there, so Aaron's chart already shows these and someone else's will keep the old ones until they
press *Reset settings to defaults*.

---

## 🔴 THE MINIMUM STOP IS $4 AND IT IS THE FIRST MEASURED DEFAULT IN THIS FILE (2026-08-17)

**The problem it fixes is the AVERAGE LOSER, not the win rate.** Over 214 positions the average
losing trade is **−1.27R**, when a stop that works makes it exactly −1.00R. That 0.27R of overshoot
is more than half the strategy's entire edge: break-even needs a 26.1% win rate against the actual
29.9%, a margin of **3.9 percentage points**. Hold losers to −1R and break-even drops to 21.7% — the
margin **more than doubles to 8.2 points without touching a single entry rule.**

**Where the overshoot lives, all 150 losing positions bucketed by how wide the stop was:**

| stop distance | n | average loser | worst | broke −1R |
|---|---|---|---|---|
| under $2 | 6 | **−1.42R** | −2.94R | 33% |
| $2 – $4 | 66 | **−1.43R** | **−10.97R** | 24% |
| $4 – $6 | 37 | −1.08R | −2.01R | 16% |
| $6 – $10 | 34 | −1.15R | −3.29R | 18% |
| over $10 | 7 | −1.13R | −2.52R | 14% |

🔴 **It flattens at $4 and does not keep improving.** Everything under $4 averages −1.43R and holds
every loss worse than −3R in six years; everything above averages about −1.1R whatever you do. **So
$4 is where the curve bends, and a bigger floor buys nothing but fewer trades** — at an $8 floor
only 32 trades survive six years for +15.1R, against 214 for +40.2R.

⚠ **THE MODE CHANGED TOO, AND THAT IS HALF THE FIX.** It was `% of price`, which is not a constant:
0.07% is $1.19 with gold at 1,700 and $2.80 at 4,000. The whole 6-year window sat below the $4 bend
at both ends, and the floor got *looser* in exactly the low-price years. `Fixed $` is the unit the
measurement was taken in, so it is the unit the default is stated in. ⚠ **`x ATR(14)` is arguably
more correct still** — the right stop scales with volatility rather than price — but no ATR multiple
has been measured here, and a plausible one is a guess wearing a unit.

🔴 **IT IS A FILTER ON A FINISHED RUN, NOT A RE-RUN, AND THE DIFFERENCE CUTS ONE WAY.** The table
above was produced by dropping trades from an export. With ONE position slot a refused trade FREES
that slot, so a real backtest can take trades this analysis cannot see — it can only ever remove.
**The direction of the bias is knowable and it is optimistic about the cost:** the −9R the $4 floor
appears to cost is an upper bound. ⚠ **The margin figures are the trustworthy half** (they are
per-trade ratios); **the total-R figures are the approximation.** Re-run it properly before quoting
either.

⚠ **IT DOES NOT FIX THE LEVERAGE, and reading it as though it does is the trap.** At 4% risk on gold
at 3,500, a $4 stop is still **35x** the account. The floor and the risk percent set leverage
*together*: `leverage = riskPct × price / stop_distance`. To reach 20x with a $4 floor the risk has
to come down to about **2.3%**. That is a separate decision and it has not been made.

---

## What would make this trustworthy

1. Compile it and run it. Read the tail of the trade list before anything else.
2. Read a handful of setups on the chart against the indicator's own drawing — the state
   panel reports which gate the sequence is sitting on.
3. A control run (`trigger_edge.py` shape) on the sweep-plus-confirmation trigger alone.
4. ✅ **The export twin landed 2026-08-17** (`smc_session_sweep_strategy_export.pine`, stage 3 of
   six). Still needed: the bar-level CSV, the Python port under `strategies/python/`, and a
   `compare_*.py` gate. `docs/STRATEGY_WORKFLOW.md` has the six stages.

⚠ Step 4 is a real lift here and nothing else in the repo has needed it: this strategy
reads THREE bar streams (1m, 5m, 15m) and `backtest/optimizer.run_sweep` replays one
frame, `run_dual` two. The lab cannot sweep it as built.
