# MPC BOS — Break-of-Structure Continuation Strategy (v1 spec)

**Status:** **§10 step 1 BUILT 2026-07-29 · COMPILES AND RUNS ON TRADINGVIEW SINCE 2026-08-07.**
🔴 **THE SHIPPED DEFAULTS NO LONGER MATCH §4/§5 OF THIS SPEC, DELIBERATELY.** Measurement on
2026-08-07 moved four of them — most importantly **`bosUseFvg` is now OFF**, so the FVG-priced entry
that §5 describes as the core of the setup is not what the file trades. The entry is a plain fib
0.786 limit with a leg-origin stop and the VWAP filter on. Two independent measurements found the
gap entry to be the losing half of the book. **Read `docs/MPC_BOS_OPTIMIZATION.md` → Run 5 before
this spec's §4/§5**, and treat those sections as the ORIGINAL DESIGN rather than the current
behaviour. Steps 2-4 are CLOSED: the export Pine, `compare_bos.py` and the Python port all landed
2026-08-07 and **the gate exits 0** (6,300 bars, warmups 900+). ⚠ It is green at the SHIPPED
defaults only, which have the gap entry OFF — so §4/§5's FVG ladder is still unverified.
⚠ **Aaron confirmed the new defaults beat the old ones in the Strategy Tester, DIRECTIONALLY ONLY —
the numbers were not recorded, so no figure in this repo describes a real run at these settings.**
**2026-08-06 — F10, the session VWAP filter, added and defaulted ON (§4b).** It is the first thing in
this file with a measurement behind it: 186,384 real M15 bars say the pro-trend-side test roughly
doubles this trigger's edge over a matched random control (+4.4% → +6.8%) and cuts the median stop
38%. ⚠ **That measurement is on a SKELETON of the setup — a with-trend BOS retraced to 0.5, stop at
0.886 — not on this file's FVG-priced entry**, so it is a prior for the filter and not this strategy's
own result. ⚠ **The file is still NOT COMPILED**, and VWAP was removed from it in July under
`CE10117`, so the paste is where that risk lands. Set `bosVwapReq = "Off"` to reproduce anything
described before this date.
**Target file:** `strategies/tradingview/mpc_bos_strategy.pine` (a strategy fork, same pattern as
`mpc_b_leg_strategy.pine`).
**Engine source:** `indicators/engines/mpc_assistant.pine` — the engine block is copied byte-identical
(structure + External fib + FVG + Sniper Zone + RSI divergence). Only the EXECUTION layer is new.
**Purpose:** the machine-followable rules, so the Pine can be written and backtested without
re-deriving the concept.

---

## 0. What this is, in one line

**It is the SOS-fade (A+) strategy with the arm swapped.** Entries identical. Take profits
identical. Stops, staging, trail, sizing identical. Three things differ and nothing else:

| | A+ / SOS fade | MPC BOS |
|---|---|---|
| **Arm** | liquidity sweep or divergence → SOS | a **BOS** after an SOS |
| **Liquidity sweeps** | the primary arm source | **not used at all** — no sweep arming, no sweep confluence |
| **Divergence** | a veto that blocks entry, with a post-SOS exemption | a **kill** — blocks entry AND closes an open trade, no exemption (§4a) |

Anything not in that table is the A+ behaviour, unchanged. If a rule below appears to add
something to entries or exits, it is a mistake in this doc — flag it rather than building it.

---

## 1. The concept in one paragraph

A shift of structure (SOS) tells you the trend has turned. What comes after it is where the money
is: the market prints one or more **break of structure (BOS)** events in that same direction until
another SOS ends the run. Each BOS is a fresh continuation leg, and each leg gives a retracement you
can buy (or sell) into. **MPC BOS trades those retracements.** It is the mirror of the A+ setup:
A+ fades the shift, BOS rides what the shift started. Not every BOS is real — some are the last
poke before the reversal — so this is deliberately a filtered setup, not a "take them all" setup.

---

## 2. What the engine already gives us (no new geometry)

Everything the setup needs is already computed in `mpc_assistant.pine`. Nothing new is invented.

| Engine value | What it is |
|---|---|
| `st.bull_sos` / `st.bear_sos` | the shift — arms the regime |
| `st.bull_bos` / `st.bear_bos` | the break — the trade trigger |
| `st.bull_bos_high` / `st.bull_bos_low` | the **break leg**: the swing high that was broken, and the leg origin (the low the leg started from). Bear is the mirror. |
| `fibo_dir`, `fiboP1..fiboP10` | the drawn External fib on the **expansion leg** (origin → running extreme). `fiboP2` = 0.5, `fiboP3` = 0.618, `fiboP6` = 0.886, `fiboP7` = 0.0, `fiboP10` = 1.0. |
| `fiboHalfReached`, `fibo618EverReached`, `fibo7Touched` | retrace latches: 0.5 tapped, 0.618 reached, TP3 (0.0) hit |
| `fvgTops` / `fvgBots` / `fvgIsBull` | live fair value gaps |
| `sniperZoneTop` / `sniperZoneBot` / `sz_bar` / `sz_bullish` | the 0.382–0.5 pocket of the break leg, re-anchored on every BOS |
| `bullDivActive` / `bearDivActive`, `divRsi` | RSI divergence + extreme readings — the veto |
| `st.last_conf_low` / `st.last_conf_high` | the structure trail reference for the runner |

**One critical distinction — two legs, two fibs.**

- **Break leg** = `bos_low → bos_high`. Its 0.382–0.5 pocket is the drawn **Sniper Zone**. Frozen at
  the BOS bar; it never moves.
- **Expansion leg** = `bos_low → the running extreme after the break`. This is what the **drawn
  External fib** measures, and its 0.5–0.886 band is the A+ entry band. Its 0 keeps extending while
  the expansion runs, so the levels move until the pullback confirms.

The two are the same thing until price runs past the broken high — then the expansion band sits
higher than the SZ pocket. Both are usable and both are offered (input `bosFibAnchor`), with the
expansion leg as the default because it is the band the whole A+ entry machinery already prices off.

Also note: **the engine sets `bull_bos = true` on every `bull_sos` bar too** — they are not mutually
exclusive. Every BOS test in this strategy must read `st.bull_bos and not st.bull_sos`.

---

## 3. The setup, stage by stage (long shown; short is the mirror)

### Stage 0 — REGIME
A `st.bull_sos` sets the long regime and resets the BOS counter to 0. The regime is self-locking:
once direction is bullish, a bull break is a BOS and a bear break is an SOS, so a "bull BOS in a
bear trend" cannot exist. The regime ends on the opposite SOS.

**Requirement:** at least one SOS must have fired on this side before any BOS is tradeable. At the
start of history the engine seeds a direction with no SOS behind it; those breaks are not setups.

### Stage 1 — ARM (the BOS)
On a bar where `st.bull_bos and not st.bull_sos`:

1. increment `bosCountL` (1 = the **expansion** break, 2+ = **continuation** breaks),
2. drop any older armed BOS on this side and re-anchor to this one — **the newest leg owns the
   setup** (this mirrors the drawn fib, which re-anchors the same way),
3. snapshot `bosL_high = st.bull_bos_high`, `bosL_low = st.bull_bos_low`, `bosL_bar = bar_index`,
4. run the **quality filters** (§4). Failing any of them means no arm at all — the leg is skipped,
   but the counter still increments.

### Stage 2 — RETRACE
Price must come back into the entry band of the anchor leg (§2). The A+ latches
(`fiboHalfReached` / `fibo618EverReached`) are re-used and latched per-BOS so a fib redraw at the
session gap cannot drop the stage.

### Stage 3 — ENTRY
A resting **limit** at the entry price from §5. The tap is the entry — we never wait for a bar to
close inside the band (a wick fills the order, and the order survives the FVG box being deleted on
the tap because the order is already placed).

### Death (the arm is dropped, no trade)
Any one of:
- an **opposite SOS** (the regime is over),
- a **newer same-side BOS** (re-anchor, see Stage 1),
- `fibo7Touched` on the anchor leg — TP3/0.0 reached, the cycle is complete,
- a **close past fib 1.0** (`close < fiboP10` long) — the leg is invalidated,
- optionally, a **close back through the broken swing** (`close < bosL_high`) — see filter F4,
- the **staleness cap** — `bosMaxDays` converted to bars (same construction as the B-LEG's
  `BLEG_MAX`, so weekends and the daily close don't burn the clock).

**One trade per BOS leg.** A `tradedBosL` guard holds the `bosL_bar` we already traded; a new BOS
resets it.

---

## 4. The fakeout filters — which BOS we actually take

The point of the setup is that we are NOT trying to catch every break. These are the levers; each
one is an input so it can be swept, and the defaults below are the starting model.

| # | Filter | Input | Default | Why |
|---|---|---|---|---|
| **F1** | **Which break after the SOS.** 1st (expansion) only / 1st + 2nd / all. | `bosWhich` | `All` (re-confirmed by measurement 2026-08-07) | The hunch is that the 3rd+ break of a run is where exhaustion and the terminal fakeout live. It is only a hunch, so v1 trades all of them and the results set the cutoff. Every trade logs its BOS ordinal so the split is readable straight off the run. |
| **F2** | **Displacement.** The breaking bar must close beyond the broken swing by ≥ N × ATR(14). | `bosMinDispAtr` | **`0.0` (off) — measured 2026-08-07: the filter costs more than it saves** | A one-tick poke through a swing high is a liquidity grab, not a break. Off by default so v1 measures the unfiltered baseline first. |
| **F3** | **Leg size.** The break leg range (`bos_high − bos_low`) must be ≥ N × ATR(14). | `bosMinLegAtr` | `1.0` | A micro leg's 0.5–0.886 band is inside the noise. Its stop is too tight to survive and its targets are inside the spread. |
| **F4** | **The broken level must hold.** A close back through `bos_high` kills the setup. | `bosReqHold` | `true` | The whole premise of a continuation is that broken resistance becomes support. If it does not hold, the break was the fakeout. This is the single most important filter. |
| **F5** | **Opposing divergence veto** — see §4a. | `bosRespectVeto` | `true` | **Aaron's explicit requirement.** |
| **F6** | **Max trades per regime.** After N filled BOS trades since the last SOS, stand down until the next SOS. | `bosMaxPerRegime` | `2` | Stops the strategy stacking three losses into one chop leg. |
| **F7** | **Final hour block.** No new entries 16:00–17:00 NY. | `execNoLateDay` | `true` | Gold closes 17:00 NY. Reused verbatim from the A+/B-LEG files. |
| **F8** | **HTF bias.** Weekly / Daily requirement, four-way dropdown each (Ignore / Must agree / Must not oppose / Must oppose). | `execHtfWeekly`, `execHtfDaily` | `Ignore` | Reused verbatim. For a continuation, "Must agree" is the natural tuning candidate — the opposite of how the A+ reversal uses it. |
| **F9** | **Staleness.** The armed leg expires after N days (converted to bars). | `bosMaxDays` | `1.25` | Same construction and default as the B-LEG. |
| **F10** | **Session VWAP, pro-trend side.** Refuse while price is not closing above VWAP (long) / below it (short). | `bosVwapReq` | **`Trend's side` (ON)** | **The only filter here that was measured before it was switched on — see §4b.** |

### 4b. F10 — the session VWAP filter (added 2026-08-06, and the only MEASURED default)

🔴 **This is the one filter in §4 that defaults ON, and the reason is evidence rather than
preference.** Every other filter in that table is an untested idea shipped Off as an open
question. F10 was measured first.

**What it is.** At each bar, price must be closing on the trend's own side of the session
VWAP — above for a long, below for a short. `ta.vwap(hlc3)`, the same line
`mpc_assistant.pine` draws and `engines/vwap/` is the canonical Python port of.

⚠ **A STATE, not a cross.** It never asks whether price *crossed* the line, only which side
the bar closed on. This is Aaron's standing call on VWAP tests, and it is why a leg that
never lost VWAP qualifies on the same terms as one that reclaimed it.

⚠ **It is re-read on every bar the limit rests**, exactly like the divergence kill — so price
closing back through VWAP *pulls* a resting order, and closing back across lets it be placed
again while the leg is alive. A one-shot check at arming time would let a setup fill hours
later on the wrong side of the very line that qualified it.

**The measurement.** 186,384 real M15 XAUUSD bars, 2018-09-13 → 2026-08-07, scored as
"+2R before −1R" against a **random control matched on direction and stop distance** — the
control is load-bearing, because gold went 1,200 → 4,300 in this window and an unmatched
long-side "edge" is free. Control lands on 33.3% with expectancy 0.000, i.e. the harness is
unbiased.

| set | n | win rate | vs control | median stop |
|---|---|---|---|---|
| with-trend BOS → 0.5 retrace, no filter | 778 | 37.5% | +4.4% (+2.5σ) | 1.34 ATR |
| …**pro-trend side of VWAP** | 404 | 39.9% | **+6.8% (+2.8σ)** | **1.11 ATR** |
| …wrong side of VWAP | 374 | 34.9% | +2.0% (+0.8σ) | 1.80 ATR |

✅ **The stop distance is the half that matters more.** A 38% tighter stop is more size per
unit of risk, and it is a *mechanical* gain rather than a statistical one.

✅ **Robustness, both checks run.** The edge holds at every R target — +5.0% at 1R, +6.5% at
1.5R, +6.8% at 2R, +6.5% at 3R, +4.7% at 4R — so it is not an artefact of the 2R choice, and
expectancy *grows* with distance (+0.094R → +0.257R at 3R), which is what a runner ladder is
built for. By year, 7 of 9 positive; 2021 is the bad one (−5.6%), 2022 and 2025 strongest.
No single year carries it.

⚠ **THE MEASUREMENT IS ON A SKELETON, NOT ON THIS FILE.** It replayed the canonical structure
and VWAP engines with a plain with-trend BOS → 0.5 retrace → 0.886 stop. It did **not** include
this file's FVG-priced entry, the Sniper Zone, F1–F9, or the real exit ladder. Treat +6.8% as a
strong prior for the filter, **never as this strategy's own number.** The obvious next
measurement is whether the FVG requirement adds to that edge or merely cuts the sample.

🔴 **A look-ahead bug inflated this before it was caught, and it is worth recording because the
wrong number was the believable one.** The first run read VWAP side off the close of the bar
the limit *fills* on — selecting bars that recovered by their close — and reported **+15.9% at
+5.0σ**. Reading the *previous* closed bar instead halved it to +6.8%. In the Pine this is
structurally safe (`longArmed` is computed at a bar's close and gates the *next* bar's fill),
but the general lesson stands: **a filter evaluated on the same bar it acts on is look-ahead
until proven otherwise, and it fails by being too good rather than by erroring.**

⚠ **Deliberately NOT added: a slope test.** `mpc_d_strategy.pine` carries
`execVwapSlope`/`execVwapSlopeBars`, and only the SIDE test was measured here. Adding an
unmeasured lever alongside a measured one is how the measured one stops being trustworthy.

⚠ **Token cost.** VWAP was removed from this file 2026-07-25 under `CE10117` (101,484 >
100,256 compiled tokens). What came back is one `ta.vwap`, one helper, two booleans and one
`plot()` — not the settings block, colours and styles that were cut. **If CE10117 returns,
delete the `plot()` first and the gate last.**

⚠ **Panel placement.** `bosVwapReq` is a two-option **dropdown**, not a checkbox, and it sits
at the end of the Strategy Execution group. TradingView keys saved input values off
declaration order *within each type*; the last `input.bool` in this file is ~800 lines below
the use site, so a new bool would have shifted it and silently reset it on every chart. There
is no `input.string` after this point, so a string shifts nothing. **The paste is safe on a
tuned chart and needs no "Reset settings to defaults".**

### 4a. The divergence KILL (required, default ON)

Divergence is the one filter that gets more power here than in the A+, and Aaron's reason is the
whole point of the setup: **an opposing divergence means the move is overextended and setting up the
NEXT shift of structure.** A continuation trade is the worst thing to be holding into that. So it
does two jobs, not one:

- **Blocks the entry** (and pulls a resting limit) — the veto below.
- **Closes an open trade** — input `bosCloseOppDiv`, default **on**. This is the single addition to
  the exit side; everything else about the exits is the A+ ladder untouched. It must therefore be
  registered in `strategies/python/mpc_sos_fade/CLAUDE.md → ## The exit ladder`, `config.py`, the
  export Pine and the compare harness in one commit, per the standing rule.
  (Note the neighbouring `execCloseOppSOS` lever was measured **inert** in the A+ — an opposite SOS
  never fires before SL/TP has resolved the position. Divergence fires *earlier* than the SOS, which
  is exactly why this version should have something on the other end of it. Measure it, don't assume.)

**No BOS trade may fire while a divergence is live AGAINST the trade direction.**

- A **long** BOS is blocked when `bearDivActive` is true, or `divRsi >= divExtremeOB` (80).
- A **short** BOS is blocked when `bullDivActive` is true, or `divRsi <= divExtremeOS` (20).

This is a **live gate, checked on the bar the limit would rest** — not a one-time check at the BOS
bar. If the divergence appears while the setup is waiting for its retrace, the resting limit is
**pulled**. If the divergence goes stale (the engine's own staleness rule: a divergence dies at the
next external break after it fired, with `divValidBars` as an outer cap) the setup may re-place its
limit while the leg is otherwise still alive.

**This is deliberately NOT the A+ rule.** The A+ has a "post-SOS exemption": a divergence printing
after its SOS is treated as the retrace itself and does not veto. That exemption does not apply
here and must not be copied. The reasoning is the opposite way round: for a reversal setup an
opposing divergence during the pullback is weakness in the counter-move; for a **continuation**
setup an opposing divergence is weakness in the move we are trying to ride — it is exactly the
fakeout signature. So: **no exemption, live veto, both directions.**

---

## 5. Entry — the A+ ladder, unchanged

**Decision (Aaron, 2026-07-27): use the A+ strategy's entry methods exactly as they are. Do not
invent tiers for this strategy.** The block is lifted from `mpc_strategy.pine` / `mpc_b_leg_strategy.pine`
(the `longEdge` / `shortEdge` computation) and only the leg it prices off changes — the BOS leg
instead of the SOS leg. Same code, same inputs, same names, so any behaviour proven in the A+ file
carries over and the three strategies stay comparable.

**The two rules it already enforces** — worth stating because they are exactly what Aaron specified,
and they are already in the A+ code, not additions:

- **0.5 is the floor.** The band is 0.5 → 0.886. Every candidate price is clamped so it can never
  rest shallower than 0.5, and rejected if it falls past 0.886.
- **A fib alone is never an entry.** With `execReqFVG` on, a price only exists when a gap or the
  Sniper Zone is there. Turning `execReqFVG` off lets a bare 0.618 fib price the leg with nothing
  behind it — that is off-spec here, not a baseline.

### The ladder — first source that prices the leg wins

1. **FVG edge.** A live gap overlapping the band; the limit rests at the gap's near edge, clamped to
   0.5. With `execFvgDeepOnly` (default **on**) the WHOLE gap must sit past 0.5 — no straddle.
2. **Deep-fib re-price (Method 3).** When the qualifying gap's near edge sits deeper than 0.618, the
   limit rests instead at the nearest fib just *shallower* than the gap (0.618 / 0.702 / 0.786) —
   the level price reaches first. `execDeepFib`, default **on**.
3. **Sniper Zone.** Used on a leg where no qualifying gap exists. The limit rests at the far side of
   the SZ pocket, clamped to 0.5, rejected past 0.886, and the SZ must be anchored at or after this
   BOS's bar (`sz_bar >= bosL_bar`). `execConfSZ`.
4. **Gap straddling 0.5.** A gap with the 0.5 line inside its body → limit at 0.5. Ranks last, so it
   only ever prices a leg no better source already did. `execFvg50`.

### The two default flips from the A+ file

`execConfSZ` and `execFvg50` are default **off** in the A+ file and default **on** here. Aaron named
both as entry methods for this setup — the sniper zone explicitly, and the 0.5-with-a-gap-on-it
entry explicitly. The mechanisms are identical; only the toggle position differs. Everything else
keeps the A+ default.

### Shallow vs deep is derived, not chosen

There is no entry-model input. The A+ decides the tier from **where the limit actually filled** —
at the 0.5 clamp = shallow, at 0.618 or deeper = deep — and the TP ladder reads that (§7). Same
rule here.

---

## 6. Stop loss — the configurable part Aaron asked for

`bosSlModel` (dropdown), plus `execSlBufTk` ticks beyond whichever is chosen.

| Option | Where the stop sits | Note |
|---|---|---|
| **`Fib 1.0 (leg origin)`** — default | The anchor leg's origin (`fiboP10` / `bos_low`). | The A+ behaviour. Widest, most survivable, and the level the engine itself uses to invalidate the leg. Start here so the baseline is comparable to the other two strategies. |
| `Broken swing level` | Just beyond `bos_high` (the flipped level). | The natural continuation stop: if the broken level does not hold, the trade is wrong. Much tighter, so R per trade is much larger — the primary tuning candidate. |
| `Fib 0.886` | `fiboP6`. | Tight, sits on the far edge of the entry band. |
| `Last confirmed swing` | `st.last_conf_low` (long) / `st.last_conf_high` (short). | Structure-based, breathes with the leg. |
| `ATR` | `entry − bosSlAtr × ATR(14)`, `bosSlAtr` default `1.5`. | Volatility-normalised, ignores structure. |

**Warning to carry into the Pine, verbatim in spirit from the B-LEG file:** the TP rungs are fixed
fib levels, so a tighter stop pushes TP1 further away *in R*, and TP1 is the only thing that stages
the stop to breakeven. A tighter stop therefore means protection arrives later, not sooner. Measure
that, don't assume it.

---

## 7. Targets and exits — the shared exit ladder, unchanged

Reuse the ladder registered in `strategies/python/mpc_sos_fade/CLAUDE.md → ## The exit ladder`. Do
not fork it. Any new lever added here must land in that table, `config.py`, the export Pine and
`compare_strategy.py` in one commit.

- **TP1 / TP2** chosen by how deep the entry filled (this is why §5 snapshots the tier):
  - **deep** entry → TP1 = 0.5 (`fiboP2`), TP2 = 0.382 (`fiboP1`),
  - **shallow** entry → TP1 = 0.382 (`fiboP1`), TP2 = 0.0 (`fiboP7`).
  A shallow entry must never use 0.5 as TP1 — the limit rests at 0.5, so the trade would "hit TP1"
  on its own fill bar, stage to breakeven and die a scratch. (This bug is already documented in the
  A+ file; do not re-introduce it.)
- **TP3** is a runner — no target, rides the trail.
- **Sizes** `execTp1Pct` 30 / `execTp2Pct` 40 / remainder runner.
- **Stop staging:** full stop → TP1 touched → breakeven + `execBeBufTk` → TP2 touched → the
  `execTp2StopMode` floor, then the trail.
- **Runner trail:** `execRunnerTrail` — `Structure (swing)` (default, `execStructTrailBufTk` 20) or
  `Fixed step` (`execTrailStep` 5.0).
- **Sizing:** `execRiskPct` fixed fraction of equity off the stop distance, default 10%.

Optional v1 extra, off by default: `bosTp2Measured` — replace TP2 with a measured move (the break
leg's range projected from the broken level). It is the classic continuation target and worth one
sweep, but it is not the default because it is outside the shared ladder.

---

## 8. Full input list (the panel, in order)

**Setup**
`bosWhich` (1st only / 1st + 2nd / All) · `bosMinDispAtr` · `bosMinLegAtr` · `bosReqHold` ·
`bosMaxPerRegime` · `bosMaxDays` · `bosFibAnchor` (Expansion leg / Break leg)

**Entry** — the A+ inputs verbatim, no new ones. Only `execConfSZ` and `execFvg50` flip to on.
`execReqFVG` (on; off = off-spec) · `execFvgDeepOnly` (on) · `execDeepFib` (on) ·
`execConfSZ` (**on**) · `execFvg50` (**on**)

**Filters**
`bosRespectVeto` · `bosCloseOppDiv` (**new** — the divergence exit, §4a) · `execNoLateDay` ·
`execHtfWeekly` · `execHtfDaily` · `execLongs` · `execShorts`
*(No `execArmSweep` / `execArmDiv` — there are no arm sources here. The BOS is the arm.)*

**Risk / exits**
`bosSlModel` · `bosSlAtr` · `execSlBufTk` · `execRiskPct` · `execTp1Pct` · `execTp2Pct` ·
`execBeBufTk` · `execTp2StopMode` · `execRunnerTrail` · `execTrailStep` · `execStructTrailBufTk` ·
`bosTp2Measured`

**Diagnostics** (all cosmetic, never affect a trade)
`execShowPosBox` · `execShowConfLabel` · `execLabelWhich` · `execShowExitLines` · `execDiagLog`

---

## 9. What is deliberately NOT in v1

Listed so they don't get smuggled in, and so the next iteration has somewhere to start.

- **Liquidity sweeps — excluded outright** (Aaron, 2026-07-27), not deferred. No sweep arming, no
  sweep confluence, no sweep filter. The BOS is the arm. The liquidity block can therefore be
  stripped from the Pine along with the A+ tracker, which also buys compile-token headroom.
- **Order-block entries.** The OB engine exists; the entry ladder here is fib / FVG / SZ only.
- **Internal structure (iBOS) triggers.** External only.
- **Cycle-fib POI gating.** Tracked by the engine, not read here.
- **Multi-timeframe confirmation** (the assistant's 1m FVG entry trigger).
- **A+ / B-LEG interaction.** This file trades BOS only and does not know about the other two.
  Whether they should stand each other down is a portfolio question, answered after all three have
  their own numbers.

---

## 10. Build order

1. ~~`strategies/tradingview/mpc_bos_strategy.pine`~~ — **DONE 2026-07-29.** Engine block = lines 1-3028 of
   `mpc_strategy.pine`, byte-identical. The A+ sequence tracker, the B-LEG tracker and the
   missed-setup callout were not copied (nothing here reads them, and the compile-token budget is
   why). Execution layer written to this spec. Awaiting a TradingView compile.
2. Backtest on XAUUSD 15m, the same window the other two were measured on. Baseline first with
   every optional filter off, then sweep F1 → F4 → the SL model.
3. ~~`strategies/tradingview/mpc_bos_strategy_export.pine` + a `compare_bos.py` harness~~ — **BOTH DONE.**
   The export twin landed 2026-08-07 (59 plots: the full decision stream, the two anchor
   endpoints, every input as `cfg_*`); `strategies/python/mpc_bos/tools/compare_bos.py` landed
   the same day and is unit-tested. ✅ **RUN 2026-08-07 and GREEN** — see below.
4. ~~Only then the Python port under `strategies/python/mpc_bos/`~~ — **BUILT 2026-08-07, and
   the order in this list was deliberately broken.** The rule ("port only after a real export
   has passed exit 0") assumes the export is the cheap half; here the CSV is a human step nobody
   had taken for a week and the port was blocking Aaron's brother from sweeping anything at all.
   So the port was written first and shipped **loudly unvalidated** — a red banner in the package
   `__init__`, its CLAUDE.md, `docs/MPC_BOS_OPTIMIZATION.md` and `docs/STRATEGY_WORKFLOW.md`.
   ⚠ **That is a defensible trade only because the gate was written in the same pass.** A port
   with no harness is what got the last one deleted (`1946f8b`, 2026-08-04).

**5. The gate — RUN 2026-08-07, exit 0.** Aaron took the export;
`compare_bos.py` compared **6,300 bars with no divergence** at warmups 900 / 1000 / 2000 / 3000
over 7,200 closed M15 bars (2026-04-21 → 2026-08-07).

```bash
python strategies/python/mpc_bos/tools/compare_bos.py '<export>.csv' --warmup 900
```

🔴 **It went RED first, and the three defects it found are the argument for step 5 existing at
all** — a dead leg that cleared numbers the Pine keeps, a harness column that had been comparing
a constant, and the still-forming last bar raising an error that blamed the bar feed. Full
write-up in `strategies/python/mpc_bos/CLAUDE.md`.

⚠ **Green does not backdate.** The port changed to get green, so nothing in
`docs/MPC_BOS_OPTIMIZATION.md` is retroactively trustworthy — re-measure what matters.
⚠ **And the green is narrow:** with `bosUseFvg` off (today's default) the gap-entry rules,
Method 3 and the Sniper Zone never ran on either side, block codes 1/3/4/5/6 never fired, and 6
trades closed in the window. A green gate is only green about the branches both sides entered.

### 10b. Run 1 (2026-07-29) — and the F4 design conflict it exposed

**XAUUSD 15m, 365 days, shipped defaults: 13 trades, −2.65%.**

13 trades in a year is not a selective setup, it is a broken one, and the cause is
**F4 (`bosReqHold`) fighting the entry**. F4 kills an armed leg when a candle CLOSES back
through the broken swing. But the entry is a retrace to **0.618–0.886 of the leg**, and that
band sits **below** the broken swing on almost every leg — the expansion has to run more than
twice the distance from the leg origin to the broken swing for the band to clear it. So price
cannot reach the entry without first closing back through the level, and F4 dropped the setup
a few bars before its own limit would have filled. The only fills that survived were legs
where a single bar wicked into the band and closed back above the swing.

This is a conflict in §4 itself, not a build error: F4 as written is only coherent with a very
shallow entry on a leg that expanded a long way past the broken swing. **F4 now defaults OFF**,
with that reasoning on its tooltip.

**Defaults changed (2026-07-29) so the baseline measures the BOS idea and nothing else:**

| | was | now |
|---|---|---|
| entry | FVG edge required, fib fallback off | **plain fib `bosEntryFib`, default 0.618** |
| FVG / Sniper Zone | required | `bosUseFvg` master toggle, **off** |
| F3 leg-size floor | 1.0 × ATR | **0.0 (off)** |
| F4 broken level must hold | on | **off** — see above |
| F5 / F5b divergence | on | **off** (spec §4a wants on; tuning candidate #1) |
| F6 max trades/regime | 2 | **10 (effectively off)** |
| F9 staleness | 1.25 days | **3.0 days** |
| F7 final hour | on | **on** — a market-hours fact, not a strategy opinion |

Every filter is KEPT as an input, not deleted. Finding which of them pays is the point of the
file; each is now switched on alone against a baseline that trades.

New input `bosEntryFib` (0.5 / 0.618 / 0.702 / 0.786 / 0.886) is the entry level. Deep/shallow
is still derived from where the limit lands, so picking 0.5 moves TP1 to 0.382 automatically and
the trade cannot scratch itself on its own fill bar.

---

### 10a. Deviations taken during the build — read before judging a run

Three, all flagged in the Pine's own header per §0:

- **`fibo7Touched` is re-implemented per-anchor, not read from the engine.** The engine's latch is
  keyed to the fib ORIGIN, which does not change across a run of breaks, so the latch set by break
  #1's round trip would kill breaks #2 and #3 on their arm bar — every continuation after the first
  would be untradeable. The Pine tracks the anchor's own 0.5 tap and its own return to 0.0 instead.
  This is what §3 means by "on the anchor leg".
- **The divergence CLOSE (§4a) fires on a confirmed opposing divergence only, not on extreme RSI.**
  The entry BLOCK still reads both, exactly as §4a specifies. An overbought RSI is the normal state
  of a healthy long continuation; closing on it would flatten the runner on every winner.
- **`execMinStopMode` / `execMinStopVal` are carried over from the A+ risk block** and are not in
  §8's input list. They default Off, so the baseline run is exactly this spec's baseline.

One thing §3's Stage 2 describes that the code does NOT gate on: the retrace latch. A resting limit
inside the band IS the retrace test — the A+ does not gate on `aplus*_half` either, and adding a
gate here would only delay the order past the price it was meant to catch.

---

## 11. Decisions — spec locked

**Decided (Aaron, 2026-07-27):**
- **Stop = fib 1.0, the leg origin.** Deliberately the same stop the other two bots use, so the
  first run measures whether the BOS idea makes money rather than measuring a stop change. The
  broken swing level is tuning candidate #1 and is already wired as a `bosSlModel` option.
- **Anchor = the expansion leg** — the entry fib moves with the run. `bosFibAnchor` still offers the
  frozen break leg, but expansion is the default and the baseline.
- **`bosWhich` = All** — v1 trades every break after the shift and lets the run show where the
  cutoff belongs, rather than assuming the 3rd+ is worse.

**Nothing open.** The spec is complete and ready to build — see §10 for the build order.
