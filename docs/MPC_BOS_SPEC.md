# MPC BOS — Break-of-Structure Continuation Strategy (v1 spec)

**Status:** DRAFT — written 2026-07-27 from Aaron's concept call. Nothing built yet.
**Target file:** `indicators/mpc_bos_strategy.pine` (a strategy fork, same pattern as
`mpc_b_leg_strategy.pine`).
**Engine source:** `indicators/mpc_assistant.pine` — the engine block is copied byte-identical
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
| **F1** | **Which break after the SOS.** 1st (expansion) only / 1st + 2nd / all. | `bosWhich` | `All` | The hunch is that the 3rd+ break of a run is where exhaustion and the terminal fakeout live. It is only a hunch, so v1 trades all of them and the results set the cutoff. Every trade logs its BOS ordinal so the split is readable straight off the run. |
| **F2** | **Displacement.** The breaking bar must close beyond the broken swing by ≥ N × ATR(14). | `bosMinDispAtr` | `0.0` (off) | A one-tick poke through a swing high is a liquidity grab, not a break. Off by default so v1 measures the unfiltered baseline first. |
| **F3** | **Leg size.** The break leg range (`bos_high − bos_low`) must be ≥ N × ATR(14). | `bosMinLegAtr` | `1.0` | A micro leg's 0.5–0.886 band is inside the noise. Its stop is too tight to survive and its targets are inside the spread. |
| **F4** | **The broken level must hold.** A close back through `bos_high` kills the setup. | `bosReqHold` | `true` | The whole premise of a continuation is that broken resistance becomes support. If it does not hold, the break was the fakeout. This is the single most important filter. |
| **F5** | **Opposing divergence veto** — see §4a. | `bosRespectVeto` | `true` | **Aaron's explicit requirement.** |
| **F6** | **Max trades per regime.** After N filled BOS trades since the last SOS, stand down until the next SOS. | `bosMaxPerRegime` | `2` | Stops the strategy stacking three losses into one chop leg. |
| **F7** | **Final hour block.** No new entries 16:00–17:00 NY. | `execNoLateDay` | `true` | Gold closes 17:00 NY. Reused verbatim from the A+/B-LEG files. |
| **F8** | **HTF bias.** Weekly / Daily requirement, four-way dropdown each (Ignore / Must agree / Must not oppose / Must oppose). | `execHtfWeekly`, `execHtfDaily` | `Ignore` | Reused verbatim. For a continuation, "Must agree" is the natural tuning candidate — the opposite of how the A+ reversal uses it. |
| **F9** | **Staleness.** The armed leg expires after N days (converted to bars). | `bosMaxDays` | `1.25` | Same construction and default as the B-LEG. |

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

1. `indicators/mpc_bos_strategy.pine` — fork the engine block from `mpc_assistant.pine`, drop the
   A+ sequence tracker, the B-LEG block, the debug callouts and the confirmation table (compile
   token budget: this script family has already hit CE10117 and CE10295 twice), then write the
   execution layer above.
2. Backtest on XAUUSD 15m, the same window the other two were measured on. Baseline first with
   every optional filter off, then sweep F1 → F4 → the SL model.
3. `indicators/mpc_bos_strategy_export.pine` + a `compare_bos.py` harness, matching the pattern in
   `strategies/python/mpc_bleg/`.
4. Only then the Python port under `strategies/python/mpc_bos/`, and only after a real TradingView
   export has passed exit 0 (the standing rule).

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
