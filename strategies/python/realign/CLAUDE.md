# CLAUDE.md — strategies/python/realign/ (the Realign bot)

**Purpose:** The internal-realignment setup as a standalone Python strategy. A bullish external
trend on the 15m (SOS → BOS → BOS) is broken by a **bearish shift of structure that is a FALSE
BREAK** — a structural liquidity grab. On the 5m the internal structure then turns bearish and back
bullish to **realign** with the original external direction, and the trade is taken on that
realignment, **before** the external bullish SOS that later confirms it. Shorts are the exact mirror.
**Sweeps:** `realign_optimization.md`, next to this file — Runs 1-10, and the open questions.
**Scope:** This bot only — its 15m aggregator, tracker, order layer, config, tests. It does NOT own
the engines (`engines/`), the replay runner (`backtest/`), or the SOS Fade machinery it reuses
(`strategies/python/sos_fade/`).
**Status:** ✅ **PARITY GREEN on 2026-09-16, on the second export — and NARROW.** 3.5 months, 10
triggers, 9 trades — and a third export at the RETEST entry is green too (9 fills, 1 expired).
Never reached: a limit cancelled by its stop, and a second same-side setup, so a green says nothing
about either. The first export was red and every cause was fixed (see *The first parity
export*, below). The golden copy runs on every clone. The 2020-2026 figures sit on bars the gate has
never seen. Built + unit-tested
(count them with pytest). Read `docs/REALIGN_SPEC.md` for the setup and the full measurement record.

## 🔴 The first parity export (2026-09-16) — read before quoting ANY figure below

Full record, commands and tables: `realign_optimization.md` → **Run 7**. The rules it leaves:

- 🔴 **The 15m trail anchor was EMPTY on every bar this port ever replayed.** `htf.py` read it off
  the event record, which has no such field. Every "external frame" figure before today measured a
  trail with no anchor, including the −15.68R the section below was built on.
- 🔴 **The default trail is now the 15m (`realign_trail_frame="external"`)** — the design, and what
  the Pine runs. Charged, 2020-2026: **160 trades, +56.39R, PF 1.78, maxDD 11.38R**, against the 5m's
  161 / +36.31R / 1.50 / 15.36R. ⚠ Not a clean test (this window picked everything in Runs 2-4) and
  the lead is mostly second-half. ⚠ **Every Run 2-6 conclusion was measured on the 5m trail.**
- **The target is the swing the false break leaves STANDING** (the engine's own read), never a
  level remembered from an earlier break. **One setup per side** — a newer false break replaces
  the live one. Both match the Pine.
- ⚠ **Three changes are on the Pine side and unverified until the next export**: reading the 15m
  close on the first 5m bar of the next 15m bar (it was ten minutes late), disarming on every
  trigger, and the reference ratchet. Plus the stop now goes in with the market order.
- ⚠ **The gate compares a latched field only while both sides are armed**, skips the still-forming
  last bar, and excuses the market entry's one-bar position offset only when the Pine opens on the
  very next bar.
**Last reviewed:** 2026-09-16 — the slower-frame gate measured on PU Prime bars: a lead, OFF, and
measured on the old 5m trail (`realign_optimization.md` Run 14). Earlier: 2026-09-11 — a
5-minute-only arm researched, measured negative and parked off main (last section). 2026-09-10 — swing length and adding to winners pinned to the Pine;
the book re-measured and reproduced exactly. 2026-08-13 — first commit.


## Flat before the close — one field now, spelled as this fork's Pine spells it

🔴 **`realign_flat_before_weekend` IS GONE. Use the inherited `flat_mode`** (`"Off"` /
`"Friday only"` / `"Every day"`, shipped Off), backed by `strategies/python/time_flat.py`.
🔴 **This fork exits at the NEXT bar's open**: `_flat_closes_now` returns False here and
`_arm_weekend_flat` arms the request, because the parent closes at the bar's close and the two
grade different R.
⚠ **MEASURED 2026-09-19, charged, and it confirms Run 10 on a moved baseline — both modes lose
and neither reduces the drawdown.** Numbers, the retired field's story and the cross-bot table:
`strategies/notes/flat-before-the-close.md`.

---

## What it trades

Five steps, and the false break is the whole idea:

1. **External trend** — a bullish external read on the 15m (a `bull_bos` or `bull_sos`).
2. **The false break** — a `bear_sos` against that trend. This is the deviation: price grabs the
   liquidity under the last confirmed low and the external structure flips bearish.
3. **The arm** — the pre-deviation external high (`broken_high_price`) is latched as the TARGET, and
   the setup stays armed for `realign_window_hrs` (72.0 since 2026-09-16; swept in Run 13).
4. **The realignment** — on the 5m, a counter-direction break followed by a with-trend SOS. That
   second break is the trigger.
5. **The entry** — MARKET, immediately, on the trigger bar's close. Stop behind the last counter
   internal shift plus `realign_sl_buf_tk`; target the latched external high.

Shorts mirror it exactly: bearish external trend, a `bull_sos` false break, a bearish realignment.

⚠ **The entry is a MARKET order, which makes this fork structurally different from every other bot
here.** SOS Fade, B-LEG and BOS all rest a limit at a fib-priced edge; this one takes the close of the bar
that triggers it. So `_place_entries` is overridden wholesale, no fib ladder is frozen
(`TradeFib` is `None` on every trade, and the chart's Fibs row is correctly absent), and the
entry-side SOS Fade config fields are inert rather than pinned.

---

## 🔴 "Internal" means the lower frame's OWN swing structure — and the other reading inverts the result

This is the single decision the whole strategy rests on, and both readings are defensible in English.

`engines/market_structure/` publishes two streams per frame: `ExternalEvents` (the swing structure a
chart draws) and `InternalEvents` (the sub-structure *within* it, one level further down).

**Aaron's "internal structure on the 5m" is the 5m's EXTERNAL stream** — the swing structure of the
5m chart, which is internal *relative to the 15m*. It is NOT the engine's `InternalEvents`, which is
one level below what he is pointing at.

That distinction is not cosmetic. **`InternalEvents` tracking RESETS on any external BOS/SOS of its
own frame**, and the false break is precisely such an event — so on **81% of candidates** the
internal stream was blank at the moment the setup armed. Reading it there does not measure a weaker
version of the setup; it measures a different, mostly-empty one.

`realign_long_source` / `realign_short_source` still expose both (`"swing"` / `"internal"`) because
the question was worth keeping open. **Both default to `"swing"`.**

---

## 🔴 The trigger scan got the SHORT side's SIGN wrong, and that is the transferable half

`backtest/tools/internal_realign_scan.py` counts setups and scores each one against a matched random
control. On shorts it reported **`"internal"` at +9.6% over control (+2.1σ)** — its single strongest
result, and the reason `realign_short_source` was originally defaulted there.

**A real replay through the exit ladder says the opposite, and not by a little:**

| shorts, 2020-01-02 → 2026-08-06 | trades | total R | avg R | maxDD |
|---|---|---|---|---|
| `realign_short_source = "swing"` | 85 | **+20.60R** | +0.242R | 6.11R |
| `realign_short_source = "internal"` | 59 | **−12.26R** | −0.208R | 14.35R |

Free, re-measured 2026-09-10. The first build read 87 / +20.22R and 60 / −13.26R — same verdict.

The scan is not broken. It scores every setup **independently, at a FIXED target, with no exit
ladder, no staged stop and no position slot** — and that short edge lived entirely in the tail
(+0.1σ at 1R, +2.1σ at 4R). The real ladder banks at the structural target and stages the stop to
breakeven long before 4R, so **the edge the scan measured is one this strategy never collects.**

⚠ **Standing rule this leaves behind: take COUNTS from the scan, take the direction of anything
exit-sensitive from a REPLAY.** A trigger prior is not a strategy result, and here the two disagree
in sign, which is the one disagreement no amount of care about magnitude protects you from.

---

## The cascade — 5m carries it, 3m is flat, 1m is negative

The internal frame was swept rather than assumed:

- **5m** — the edge. 94 setups over 5.6 years on the single-engine count.
- **3m** — break-even. More setups, none of them better.
- **1m** — negative, **and its stops sit inside gold's spread floor**, so a positive result there
  would have been unbankable anyway.

🔴 **THE 5m-DIRECTION / 1m-ENTRY PAIRING IS MEASURED AND REFUSED (2026-09-15).** Aaron proposed it
by analogy with the shipped 15m/5m. Charged `puprime_standard`, 1m bars, 2020-01-02 → 2026-08-06:
**483 trades, −67.28R, PF 0.74** at market and **313 trades, −87.97R, PF 0.54** on the retest entry.
⚠ Both **destroyed the account** (88–90R drawdown at 10% risk), so those totals are floors, not
quotable figures — the SIGN is the finding. This is the cascade confirmed a third time, and it now
holds with the retest entry ON, which was the one remaining reason to think the 1m arm might be
rescuable. Do not re-open it without a new mechanism. Full record: `realign_optimization.md` Run 2.

⚠ A single-engine M15 run gives only **9 setups in 5.6 years** — the M15 engine emits 3 iSL and zero
iBOS/iSOS across Aaron's own window. The two-frame build is not a refinement; without it there is no
strategy to measure.

## The trail frame — the 15m, and the −15.68R that said otherwise was a bug (2026-09-16)

The Pine always trailed the **15m** swings; this port trailed the **5m** because it was written
against a Pine comment that described the wrong frame. A morning measurement put the 15m at
**−15.68R** and kept the port on the 5m — and the evening's parity export showed the port's 15m
anchor had never been filled, so that number measured no anchor at all. Fixed, the 15m is the
better book and the default (*The first parity export*, above; history in the config docstring).

- **The trail IS the exit here** — nothing banks at a target — so the frame rewrites the book.
- ⚠ **Run 4's "the ratchet is inert" was measured on the 5m anchor** and is not known to hold on
  the 15m, which sits further from price.
- ⚠ **The drawdown disagreement with the Strategy Tester (open question 2) predates the fix** and
  was measured on the 5m book; it needs re-checking on the default before anyone diagnoses it.

## What the exit and entry studies settled — on the 15m trail (Run 10, 2026-09-16)

**Tables: `realign_optimization.md` Runs 2-6 (5m trail) and Run 10 (today's default). Nothing here
moves a default — the shipped configuration is the best tested.** Fitting window 2020-01-02 →
2025-08-05, charged: **139 trades, +49.49R, avg +0.356, PF 1.81, maxDD 11.38R.**

- 🔴 **The pattern beats matched random entry: z +3.58** (real +0.356R a trade, random −0.011R) —
  past the family-wise bar. ⚠ Random timing now roughly BREAKS EVEN on this trail rather than
  losing, so the pattern is the whole edge and the exit is no safety net. Supersedes the 5m-trail
  +2.36, and the trigger scan's older 1.85.
- 🔴 **THREE TO FIVE TRADES CARRY THE BOOK.** Top five = 123% of the total; it goes negative after
  4-5 removals. **Quote this beside any figure.** It is not evidence the edge is fake — the random
  control does not depend on the big winners.
- 🔴 **Three 5m-trail findings DID NOT SURVIVE the move to the 15m trail** — the retest entry
  "beating market everywhere", the 12-hour always-on clock, and flat-before-the-close. On this
  trail the retest is better per trade but worse in total, drawdown and without its best trade; any
  always-on clock (6-48h) and either flat rule LOSES, because the winners run past a day and a half.
  **A hold-time cap on this strategy costs ~20R.** Aaron's hold-time concern is real, and this is
  its price.
- 🔴 **A fixed take-profit loses, and so does banking part early** — monotone, on both trails. The
  1R row is the one to remember (5m trail): **50% win rate and it loses money.**
- ⚠ **The ratchet is no longer inert** on the 15m trail, and 3% looks best — as a SPIKE (2% is below
  1%), carried by one half. Not adopted. The trail buffer is still not a lever.
- 🔴 **NO ENTRY FILTER EXISTS, and every bucketed "signal" was one trade** (5m trail) — winners and
  losers are indistinguishable at entry. No bucketed claim is believable until it survives removing
  the top trade; `backtest/tools/realign_trade_profile.py` does that. ⚠ Not re-run on the 15m trail.
- 🔴 **The retest's cancel runs AFTER the fill phase** — a dip to the limit that carries on to the
  stop is a real losing trade. Pinned by test. Its parity is green (Run 9).
- ⚠ **The held-back year (2025-08-06 → 2026-08-06) is SPENT** — Run 2 used it once. Nothing may be
  validated on it again. Forward data is the only clean test left.

## 🔴 The pattern rule — the ranking INVERTS with costs, and this file had it wrong

`realign_pattern` takes `any` | `opposing` | `strict`. **Default is `any`, the loosest.**

**This section previously said `strict` — the sequence Aaron actually drew — was "the WORST of the
three" and that "the extra specificity carries no information". Both sentences were false, and they
came from the TRIGGER SCAN**, which the section two above says must never decide an exit-sensitive
question. The correction is the same lesson arriving inside the file that states it.

Measured by REPLAY, 467,352 M5 bars 2020-01-02 → 2026-08-06:

| FREE | trades | total R | avg R | win | PF | maxDD |
|---|---|---|---|---|---|---|
| `any` | 162 | +45.14R | +0.279 | 44.4% | 1.658 | 12.15R |
| `opposing` | 43 | +11.36R | +0.264 | 48.8% | 1.832 | 4.58R |
| `strict` | 42 | **+12.36R** | **+0.294** | **50.0%** | **1.977** | **4.15R** |

| CHARGED (`puprime_standard`) | trades | total R | avg R | win | PF | maxDD |
|---|---|---|---|---|---|---|
| `any` | 162 | **+35.81R** | **+0.221** | 33.3% | 1.496 | 15.52R |
| `opposing` | 43 | +6.22R | +0.145 | 30.2% | 1.425 | 5.51R |
| `strict` | 42 | +7.33R | +0.175 | 31.0% | **1.540** | **4.41R** |

**Free, `strict` is the BEST of the three on average R, profit factor and drawdown simultaneously.**
Charged, it is not — costs take **40% of its average R** (+0.294 → +0.175) against `any`'s **21%**
(+0.279 → +0.221), and the order flips. A conclusion drawn on a free book does not survive a charged
one here, which is the practical reason this repo charges costs before ranking anything.

⚠ **The mechanism is NOT measured.** The obvious candidate is that the strict sequence's stops are
tighter, so a fixed spread costs more R. It is plausible, it is one replay away (median stop distance
per pattern), and it is deliberately left as a hypothesis rather than written up as a finding.

**`any` still ships**, on the two figures that survive charging: 5x the total R and more R per unit
of drawdown (2.31 vs 1.66). But `strict` is a real rule with the best per-trade quality in the book,
and it is the one worth revisiting if the cost model or the entry ever gets cheaper — which is
exactly the conclusion the old wording would have prevented anyone from reaching.

---

## Live-capable wiring (2026-09-16) — NOT yet run on the box

🔴 **The live runner never calls `RealignStrategy.step`.** It drives `signals` → `sequence` →
`execution.step(sig, seq)`, and until today the public stages were the real SOS Fade ones — a live
bot would have skipped the 15m frame and the tracker and crashed on the first bar. Now:

- **The public stages are the empty pass-through seams** and `execution.step(sig, seq)` hands the
  bar back to the strategy — the extreme leg bot's pattern. The real stages are private, and the
  strategy's own path calls `step_bar`.
- **`entry_style = "market"`.** Inheriting SOS Fade's "resting" halts the bot on its first trade.
- **The market entry states its stop on the bar it opens.** The parent states it only on bars that
  start in a position, and the bridge refuses a market order with no stop.
- **The live step refuses the retest entry** — a resting limit under a market declaration is a
  state the bridge cannot tell from a divergence.
- ✅ **Proof, `tests/test_live_seams.py`:** the golden export replayed through the runner's three
  calls books the same trades as `run()`, bar for bar. The runner's call shape is parsed from its
  source so the imitation cannot drift. Every test was watched RED by mutation.
- ⚠ **Rule 9 still stands:** nothing has driven it on the box. Instance folder, promote, dry run and
  the shadow diff are the steps left. **The parity gate is unaffected** — the replay path is the
  same calls in the same order, and the golden gate was re-run green.

---

## Single-frame by construction (`htf.py`)

The setup reads two frames and the strategy is **single-frame from the runner's point of view**: it
runs on the 5m stream and builds its own 15m bars in `HtfStructure`.

That is not a stylistic choice. **`backtest.optimizer.run_sweep` REFUSES dual-frame strategies** —
it replays one frame — so a `run_dual` build is locked out of the optimizer, every sweep and the
stress test's sensitivity pass. `run_dual` therefore raises here, by test.

Two correctness properties, both tested, both silent if broken:

- 🔴 **A 15m bar is published only once its last 5m bar has CLOSED.** Feeding a forming HTF bar to
  the engine is lookahead of the flattering kind — the external break would be known one or two 5m
  bars before it could have been, and every entry after it priced on information the trade did not
  have. The aggregator emits on the FIRST bar of the NEXT bucket.
- ⚠ **Buckets align to the wall clock** (:00/:15/:30/:45), never counted three-at-a-time. A counted
  aggregation drifts after any gap — a weekend, a holiday, one missing bar — and then silently
  builds 15m bars straddling two real ones.

---

## Inherited defaults — what had to be refused

`RealignConfig` is a `SosFadeConfig` superset for the same reason `BLegConfig` is: one exit ladder,
one sizing path, one cost model. **The inherited defaults are the risk, not the new fields** — the
`BosConfig` incident (2026-08-07), where two SOS Fade defaults added in the preceding five days silently
broke a new fork.

- **`exec_secondary` PINNED False.** The parent defaults it **True** since 2026-08-07. The 1m
  re-entry needs a second bar stream through `run_dual`, which this fork raises on — so inherited,
  a replay would either refuse outright or, on the paths that do not check, return a primary-only
  book while reporting itself as having re-entries. Turning it on is REFUSED at construction rather
  than ignored.
- **`show_internal` switched back ON.** The parent pins it **False**. Inheriting that blanks the
  internal stream, and with `realign_*_source = "internal"` the bot would simply never trigger on
  that side — **a wrong RESULT with no error anywhere.** Tested.
- ✅ **The chart-frame swing length is the Pine's 10 since 2026-09-10** (`htf.MAJOR_LENGTH`, read
  by both frames); the 5m frame had taken the engine default 15, which the parent never pins.
  🔴 **This line predicted the fix would move every figure, and it moved NONE**: the pivot window
  only places the engine's first swing (`engines/market_structure/CLAUDE.md`), so the 2020-2026
  book is identical at 10 and 15. A prediction written as a fact is rule 4 — measure first.
  `test_both_frames_run_the_charts_swing_length` reads the value out of the Pine.
- 🔴 **Adding to winners is PINNED OFF (2026-09-10).** Inherited from SOS Fade's 2026-09-06
  default, and `realign_strategy.pine` has no scale-in. With it the book read **162 / +61.27R free,
  +49.29R charged** — a candidate, not a result: nobody chose it for this setup and no chart can
  confirm it. Turn it on only in a run that says so, after this bot has a gate.
- ⚠ **The breakeven buffer is a KNOWN chart/Python difference, left alone**: the Pine moves the
  stop to breakeven at 0 ticks, the Python at the parent's 30. The ladder is inherited on purpose
  (below); the parity gate is what settles which is right.
- **The entry-side SOS Fade fields are left alone deliberately** (`exec_fib_nearest`, `exec_deep_fib`,
  `exec_fvg_pre_zone`, `exec_fib_overlap`, `exec_fib_deep_edge`, `exec_sl_deep`). This fork places
  no fib-priced order, so nothing reads them. Pinning them would imply they mean something here.

## 🔴 The shipped baseline moved THREE times on 2026-09-16 — read before quoting a figure

**Now: 114 trades, +88.70R, worst drawdown 6.07R** (PU Prime `XAUUSD.p` 5m, 2020-01-01 →
2026-09-16, `puprime_ecn`, 5% risk) = the 20-day momentum filter ON + the setup armed **72h**
(was 24) + the runner trail **structure only** (was structure + 1% ratchet). Aaron's calls, taken
against the agent's advice on the last two. Every figure above this section predates all three.

- ⚠ **About 37R of the +40R those two added is TWO trades**: 2023-09-25 short (+19.2R, exists only
  at ≥66h) and 2020-11-09 long (+36.6R unratcheted against +18.5R). Without them the two changes
  are roughly +3R. Expect a thinner book than the headline. Record: `realign_optimization.md` → Run 13.
- ✅ **Parity GREEN at the new defaults** (golden `VANTAGE_XAUUSD_M5_20086bars_shipped.csv`, taken
  2026-09-16): 8 momentum refusals, 2 trades, one trailed for 22 bars on the structure-only stop.

## 🔴 The N-day momentum filter — SHIPPED ON at 20 (`realign_mom_days`, 2026-09-16)

- Filter alone (24h, ratchet): **94 trades, +48.50R, worst drawdown 5.07R**, against 163 /
  +54.09R / 14.48R off. Pass `realign_mom_days=None` to reproduce an older figure.
- **Parity GREEN on its own export** (golden `VANTAGE_XAUUSD_M5_20069bars_mom20.csv`, filter at
  20): the momentum sign agreed on 14,368 bars and 8 setups were refused on both sides. The two
  older goldens predate the filter and the gate replays them with it OFF — never at the default.

- **Refuses a trade WITH gold's N-day move** (and any trade before N + 1 completed days exist).
  Reads `strategies/python/daily_momentum.py`, the shared module any bot can reuse. Pine input
  "Skip trades with the N-day move", refusal code 7, exported as `cfg_mom_days` / `px_mom_dir`.
- **Aaron's call, against the agent's advice: "I like steady better."** At 20 days: worst
  drawdown 14.48R → 5.07R, total 54.09R → 48.50R, recent half 18R worse. Run 12 of
  `realign_optimization.md` has every table.
- ⚠ **A live bot needs 21 completed trading days of bars before it can trade** — the filter
  refuses until then. `realign_1` warms on 15,000 M5 bars (about 54 trading days), which covers
  it; a smaller `warmup_bars` would silently refuse every setup after a restart.
- ⚠ `realign_1`'s config lists every setting except this one, so it takes the default (20) at
  its first promote. Its frozen code has never run, so no running bot changes.

## Two optional filters, both shipped OFF (`realign_min_rr`, `realign_trend_minutes`)

Added 2026-08-13. **Both default to `None`, so no figure anywhere in this file moves.** They exist
because the levers they turn are already implied by the data, not because either has earned a value.

**`realign_min_rr` — refuse a setup whose reward-to-risk AT ENTRY is below this.** The stop is the
counter-move extreme and the target is the pre-deviation external high, and those are set
independently — so R:R varies from **−3.68 to 14.92** across the 162-trade book (median 1.69) and is
known at the moment of entry. That is what makes it a filter rather than a hindsight observation.

🔴 **`None` is NOT the same as `0.0`, and the gap between them is an unresolved Pine parity defect.**
`realign_strategy.pine` guards its entry with `tgtLong > close` (and the short mirror). **This
Python has never had that check**, so it takes trades whose target already sits behind the entry —
7 of 162. Those trades are not junk: TP2 is satisfied on the entry bar, the ladder jumps to stage 2,
and they run as pure trailing trades for **+5.67R between them (+0.81R average, against the book's
+0.221)**. So the Pine is refusing the better-performing tail of its own book. **Which side is right
is not settled here** — `0.0` reproduces the Pine, `None` reproduces every Python figure measured
before 2026-08-13, and the parity gate is what decides. The default stays `None` so nothing historic
moves while that is open.

**`realign_trend_minutes` — refuse a trade against the structure direction of a SLOWER frame.** It
gets its own `HtfStructure` aggregator rather than sharing the false-break frame's, because the two
answer different questions and must not share state. Construction REFUSES a value at or below
`realign_htf_minutes`: a "trend" frame that is not slower is the same read under another name, and
it would pass silently while filtering on something the setup already knows.

⚠ **`trend_dir == 0` means the slow frame has not spoken yet, NOT "no trend", and the gate refuses
there deliberately.** Passing everything during warm-up is a filter that reports itself as on while
doing nothing — root rule 1, and the shape this repo keeps getting bitten by.

🔴 **The reason it exists: the profitable DIRECTION flips with gold's own trend, and that is the one
structural finding in this strategy's data.** Split the 162-trade book in half:

| | shorts | longs |
|---|---|---|
| 2020-01 → 2023-04 | **+17.18R** (43 tr) | −8.83R (39 tr) |
| 2023-05 → 2026-08 | +2.90R (42 tr) | **+24.55R** (38 tr) |

Gold was roughly flat-to-down through 2021 (−4.2%) and 2022 (−0.3%), then +12.9% / +27.1% / +64.5%
through 2023–2025. The side that makes money is the side aligned with the prevailing move, and it
reverses when the move does. The mechanism is the setup's own logic rather than a pattern in a
table: a false break is a liquidity grab AGAINST a prevailing direction and the realignment is the
resumption, so taken against the dominant trend the same shape is a genuine reversal being faded —
a different trade with a different expectancy.

⚠ **THAT HYPOTHESIS WAS DERIVED FROM THE SAME 162 TRADES IT WOULD BE TESTED ON, WHICH IS EXACTLY HOW
A SECOND OVERFIT HAPPENS AFTER THE FIRST ONE IS CAUGHT.** `realign_min_rr` looked excellent on the
full history and was then shown to be a fit to one half. Any value here has to clear the same bar:
**it must help in BOTH halves separately, not in the total.** Until it does, the default is `None`.

✅ **MEASURED 2026-09-16 on PU Prime bars (a NEW basis, same 162-trade book): 60 passes that bar,
240 fails it.** At 60: 84 trades, +27.02R, +0.322 avg, PF 1.71, maxDD 9.62R, halves +12.35 / +14.67,
against the shipped 162 / +38.08R / +0.235 / 15.28R / +9.38 / +28.70 on the same bars; and it beats
random timing by +0.407R a trade (z +2.53, a value picked after the sweep, so not Run 5's clean
kind). 1.1 standard errors, no holdout — **a lead, still OFF.** `realign_optimization.md` Run 14.
⚠ **Measured on the 5m trail, before Run 7 made the 15m the default** — like Runs 2-6, it has not
been re-checked on the trail the bot now runs.

⚠ **A positive `realign_min_rr` is a NEW filter that neither implementation has, and it must be
measured by REPLAY — never by dropping rows from a finished trade list.** With one position slot a
refused setup FREES the slot and a different setup takes it. That is precisely how the minimum-stop
guard's cheap estimate got its SIGN wrong: **+1.84R estimated, −1.84R replayed.**

⚠ **Neither input is covered by `tests/test_realign.py`** — the 15 tests there are green and none of
them exercises either field. Both are untested beyond construction-time validation.

## The exit ladder is the parent's, unchanged

Stop staging, the runner trail, TP rungs and the time stop all come from `sos_fade` and move
with it. That is the point of inheriting — but it also means **a change to the SOS Fade ladder moves this
bot's numbers**. ✅ Re-measured 2026-09-10 on today's ladder: the book below reproduces exactly.

---

## Measured — and what is still open

Full-history replay, 5m XAUUSD, 2020-01-02 → 2026-08-06, shipped defaults, warmup 1000, **the 5m
frame resampled from M1** (see *How to re-run this* below — reading the M5 cache is a trap):

| | trades | total R | avg R | win | PF | maxDD |
|---|---|---|---|---|---|---|
| free | 162 (77L/85S) | +45.14R | +0.279 | 44.4% | 1.658 | 12.15R |
| charged (`puprime_standard`) | 162 | +35.81R | +0.221 | 33.3% | 1.496 | 15.52R |

✅ **RE-MEASURED 2026-09-10 after both pins, and it reproduces EXACTLY** — free and charged, all 162
trades, the pattern table and the half split too. Vantage 5m through the lab's own replay (the M5
cache now equals the 1m resample bar for bar, 467,352 bars). ⚠ Its win rate counts a trade inside
±0.25R as a scratch, so it reads 27.8% where this table's older count reads 44.4%.

Cross-checked against the TradingView Strategy Tester on the same instrument and window:

**143 trades · +41.35% (≈35R) · PF 1.617 · maxDD 17.79% (≈19.5R) · win 30.77%**

✅ **Total R agrees within noise** — two implementations, two fill models, one answer about whether
the setup makes money.

⚠ **AN EARLIER REVISION OF THIS SECTION CLAIMED +37.67R / maxDD 14.60R CHARGED AND IT DOES NOT
REPRODUCE.** Same window, same profile, today: +35.81R / 15.52R. **The FREE figure reproduces to the
cent**, so whatever differs is on the charged path alone. `32b633f` was checked and is not the cause
— it touched only tools and docs, no execution code. The candidates are a different warmup or a
different bar set in the original run, and **neither is measured, because the original run's command
was not recorded.** That is the whole argument for the *How to re-run this* section below.

✅ **ONE OF THE TWO PINE/PYTHON DIFFERENCES IS NOW LARGELY CLOSED, AND THE CAUSE WAS THE COMPARISON
RATHER THAN EITHER IMPLEMENTATION.** This section used to report the win-rate gap as "30.77% vs 44%"
and blame scratch classification. **44% is the FREE book.** The charged book — the one the R figure
is quoted from — wins **33.3%**, against the tester's 30.77%. The comparison was reading its R off
one book and its win rate off the other. **Costs move this strategy's win rate 11 points** (44.4% →
33.3%), because it enters at MARKET and pays the spread both ways rather than resting a limit like
every other bot here. ⚠ ~2.5 points remain, scratch classification is still the candidate (11 of 162
counted separately at |r| ≤ 0.02 against a tester that asks only whether P&L > 0), and it is small
and NOT measured.

🔴 **The drawdown difference is still open and undiagnosed by measurement: 17.79% (≈19.5R) in Pine
against 15.52R here.** The candidate is that TradingView fills a gapped stop at the next bar's OPEN
while the bar-replay model fills at the stop PRICE, which would make Python optimistic — the
direction that matters. Same total R with a deeper drawdown is that signature, but a signature is
not a measurement, and **the parity gate is what settles it.**

## How to re-run this

```
.venv/bin/python -m pytest strategies/python/realign/tests/ -q     # 15 tests
```

The book, asserted — 🔴 **the baseline moved AGAIN on 2026-09-16** (Runs 12 and 13 shipped the 72h
window, the momentum filter ON and the structure-only trail, and this block still read the Run 7
numbers until 2026-09-17). These are today's values:

```
python backtest/tools/axis_sweep.py --strategy realign --symbol XAUUSD --tf 5 \
    --server VantageMarkets_Demo --start 2020-01-02 --end 2026-08-06 --split 2023-05-01 \
    --expect-trades 113 --expect-r 88.02                              # free
    ... --profile puprime_standard --expect-trades 113 --expect-r 82.41  # charged
```

⚠ **A number quoted from this bot goes stale the moment a default ships, and that has now happened
twice.** The Run 7 book (160 trades, +56.39R charged) is reproducible to the cent by pinning the
three settings back — the command is in `realign_optimization.md` → Run 14.

⚠ **The two tables above this section are the OLD 5m-trail book** and are kept for the record.

⚠ **Charged it is +0.221R a trade against a standard error of ±0.168R — 1.3 errors, NOT an
established edge.** The halves split +8.35R / +27.46R at 2023-05, which is the direction flip above.
✅ The 26,887-bar 5m file this section used to warn about is gone: `VantageMarkets_Demo`'s 5m cache
now equals the 1m resample bar for bar over this window (467,352 bars, measured 2026-09-10).

**Neither is a reason to trust one side over the other yet. They are the two things the parity gate
exists to settle.** It is green as of Run 8, narrowly.

---

## Rules

- **Quote a number from this bot with the gate's scope beside it.** Green on 3.5 months (Run 8);
  a stop-cancelled retest limit and a second same-side setup have never been compared. Any Pine change needs a
  FRESH export — the golden copy is regression only.
- **Take counts from `internal_realign_scan.py`; take the direction of anything exit-sensitive from
  a replay.** The scan had the short side's sign wrong. See above.
- **Never publish a forming HTF bar** from `htf.py`. It is lookahead, it improves every result, and
  nothing errors.
- **Diff this config against `SosFadeConfig` field by field before touching either.** Inherited
  defaults arrive uninvited and this fork has already had to refuse two of them.
- **A change to the SOS Fade exit ladder changes this bot.** The ladder is shared, not copied.

## Key paths

| Path | What |
|---|---|
| `config.py` | `RealignConfig` — the levers, and every pin with its reason |
| `htf.py` | `HtfStructure` — the 15m aggregator, and the no-lookahead argument |
| `tracker.py` | `RealignTracker` — arming on the false break, walking the realignment |
| `execution.py` | `RealignExecution` — the market and retest entries, sizing, the stop |
| `strategy.py` | `RealignStrategy` — wiring, `engine_config()`, `run_dual` refusal |
| `tests/test_realign.py` | 32 tests, weighted toward the silent failures |
| `tools/compare_realign.py` | the parity gate — **green 2026-09-16, narrow** (Runs 7-8) |
| `exports/golden/` | the committed passing export + `golden.json`; step 15 of the full test run replays it |
| `exports/` | every other real export — git-ignored |
| `strategies/tradingview/realign_strategy.pine` | the TradingView side |
| `docs/REALIGN_SPEC.md` | the stage-1 spec and the full measurement record |
| `backtest/tools/internal_realign_scan.py` | the counting/geometry scan |

## `exec_min_atr_pct` is PINNED off (2026-08-26)

The parent gained a dead-market entry floor
(`strategies/python/sos_fade/CLAUDE.md` → *The DEAD-MARKET floor*). This fork pins it to 0.0
rather than inheriting.

⚠ **It matters more here than on the other forks, because this one's parity gate is the
narrowest** (Run 8). Nothing on this bot would ever report having silently acquired
an entry filter, so an inherited default is not something a run could tell you about afterwards.

---

## Its chips say `REALIGN` on the price chart (2026-09-02)

`LAB_STRATEGY["chart_tag"] = "REALIGN"` — the re-alignment with the higher-frame trend. ⚠ **A LABEL: no run, no cost and no decision reads
it**, so changing it repaints chips and moves no trade. ⚠ **Keep it SHORT** — it is drawn beside the
entry price. Why it exists, what it does on a STACK, and why rule 22 is silent for it:
`command-center/backend/CLAUDE.md` → *A strategy names its own setup on the chart*.

## The frame it is measured on is DECLARED (2026-09-03)

`LAB_STRATEGY["suggested_bar_value"] = 5` — it trades the 5m and reads the 15m through its own aggregator; a single-frame M15 run gives 9 setups in 5.6 years, i.e. no strategy to measure. The lab reads it and every form fills a leg's
timeframe box from it, so nobody has to remember which bot runs on which frame.

⚠ **It is a DEFAULT, never a refusal** — a faster frame (1m, 2m) still runs, and a figure quoted
off one is a DIFFERENT EXPERIMENT from every number in this file, and has to say so.
🔴 **But a frame as slow as the false-break frame IS refused (2026-09-16)**: on 15m bars the 15m
aggregator is 1:1 with the chart, the two reads collapse, and run 57514f2bb21c completed green with
ZERO trades. `run()` now raises instead (`tests/test_realign.py`, watched red without it).

🔴 **Why it had to be declared: the stack page had ONE timeframe for the whole stack**, so a 5m
bot and a 15m bot on one account meant one of the two was replayed on a frame nobody has ever
measured it on — and the combined table said *portfolio*. Rules for the lab side:
`command-center/backend/CLAUDE.md` → *A stack leg runs on its own frame*.

## The 5-minute-only arm — researched 2026-09-11, measured NEGATIVE, parked off main

Aaron's question: on the 5m ALONE — a trend (SOS, then BOS), one counter shift, the shift back —
which version is worth entering? An arm reading the whole sequence on one frame was built and a
36-combination study run, pre-declared, with costs, a split and matched random-entry controls.

- 🔴 **All 36 lose after ECN costs, none is positive in both halves, and the four that differ from
  random past the family-wise bar are all WORSE than random.** Entering on the next break after the
  realignment is worse per trade in all 18 pairs. Full table: `realign_optimization.md` → Run 1.
- ⚠ **This line said the shipped two-frame setup "does not clear the bar either: z 1.85" and that is
  SUPERSEDED as of 2026-09-16 — it clears it.** That 1.85 came from a TRIGGER SCAN on a different
  basis (ECN, 1% risk, full window), and this repo's own standing rule is that a trigger prior is
  not a strategy result. Replayed through the real strategy and the real exit ladder
  (`backtest/tools/realign_control.py`, 20 reps, `puprime_standard`, 2020-01-02 → 2025-08-05):
  **z +3.58 on the shipped setup with the 15m trail** (Run 10; +2.36 on the old 5m trail). The
  higher frame setting the trap is the version worth proving, and it is now the version that has
  been proven.
- **The code is on branch `research/realign-chart-frame`, not here** — five settings with no
  TradingView inputs, for an arm with no edge. Check it out to re-run the study; do not merge it.
- ⚠ **Two facts it measured about the engine stream hold on main too** (467,352 5m bars, 5,265
  breaks, at swing length 15 and 10): no bar ever breaks both ways, and once a run has printed its
  first break every counter break is flagged SOS. The first break itself can be a plain BOS.

## Risk per trade is PINNED at 10 (2026-09-13)

`sos_fade`'s default moved 10 → 5 to match its live share; `RealignConfig` inherits the field, so
it is pinned at 10.0 — the value every figure in this file was measured at. ⚠ **The Pine ships 1.0,
so the two sides disagreed before this**; R does not depend on it and dollars do, and this bot's
parity gate (still unbuilt) is what settles which side moves.

## A new setting needs a line in `realign.meta.json` (2026-09-16)

A setting with no label and description there shows as a raw name on the strategy page, and the
backend test that caps realign's undocumented settings (now 119) goes red. The page summary there
is capped at seven bullets, hidden ones included, and each bullet's condition must hold at the
defaults — so a default change means rewriting the bullet it hides.
⚠ Keep a line about settings the bullet's condition does not cover OUT of a conditional bullet — the
page hides the whole bullet. That is why breakeven sits in the always-shown stop bullet.

## SOS Fade target-level settings inherited (2026-09-20)

This strategy builds on the SOS Fade config, so it inherits three new exit-ladder settings: "Target 1 level", "Target 2 level" and "First target, in R". They are off by default and change nothing here. They are listed in this meta file so the lab page shows them rather than silently accepting them. They have not been measured for this strategy. SOS Fade results: `strategies/python/sos_fade/sos_fade_optimization.md` Run 40.

## Two inherited exit rules, both OFF — never measured on this bot (2026-09-23)

⚠ The give-back guard and the reversal exit arrive from SOS Fade's config and default OFF, so
nothing here moved. 🔴 **Neither was measured on this bot**; on SOS Fade's book the reversal exit
lost on all six settings. Switching one on here is a new experiment, and neither has a Pine side.
Evidence: `strategies/python/sos_fade/notes/exit_ladder_history.md`.
