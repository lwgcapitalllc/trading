# CLAUDE.md — strategies/python/mpc_sos_fade/ (the MPC SOS Fade bot)

**Purpose:** The MPC SOS Fade strategy in Python — a line-for-line port of the A+ block +
execution layer in `indicators/mpc_strategy.pine` (Aaron's brother's "MPC-JARVIS" script). It reads
the canonical engine stack's per-bar output and turns the A+ sequence into trades.
**Scope:** This strategy only — its state machine, order logic, config, and parity harness. It does
NOT own the engines (`engines/`), the replay runner (`backtest/`), or the lab (`command-center/`).
**Status:** Built + unit-tested + **logic-parity GREEN (exit 0) 2026-07-16** on a full-history
`VANTAGE_XAUUSD, 5m` export (20,076 bars, `compare_strategy.py` with no warmup — the export starts at
bar 0). Bar-for-bar identical decision stream vs `mpc_strategy.pine`. Runs real-tick fills + costs
(`fill_model="tick"`), and is registered in the command-center lab as `runner="python"` (see
`LAB_STRATEGY` in `__init__.py`) — risk % is editable in the Run modal. 51 offline tests green.
**RE-VALIDATED GREEN 2026-07-22** after the Pine changed (SOS-aware veto + `execConfSZ` + CONT
removal): the export was regenerated, the veto was ported, and `compare_strategy.py` matches Pine's
decision stream on a fresh 19,863-bar `VANTAGE_XAUUSD, 15m` grand export — every `px_dec_bits` /
`px_stages` / `px_edge` / `px_entry_price` bar-for-bar, one lone 25-cent `px_exit_run` difference on
a single Nov-2025 runner (an intrabar trail-fill guess, not a decision). See `## The 2026-07-22 re-sync`.
**RE-VALIDATED GREEN 2026-07-29** on a fresh 21,494-bar `VANTAGE_XAUUSD, 15m` export taken at the
shipped `exec_tp1_pct = exec_tp2_pct = 0` and carrying the swing ratchet through `cfg_exitmode`/
`cfg_trail_pct` — exit 0 at warmup 100 and at every warmup up to 2000. See
`### PARITY GREEN 2026-07-29`.
**Open question — sample size, NOT correctness:** the validated 365d 15m run is only 22 trades (2yr:
40), and the runners alone make >100% of the net in both windows. Read `## The 2026-07-16 year run`
below before trusting any tuning done against it.
**Last reviewed:** 2026-07-29 — **parity re-run GREEN on a fresh export that finally carries the
ratchet AND the shipped 0/0 rungs** (`### PARITY GREEN 2026-07-29`). Every "the export is stale"
warning in this file is cleared, with one exception that is NOT cleared: the export still has no
`execMinStopMode`/`execMinStopVal` column, so nothing here validates the minimum-stop filter.
Earlier: 2026-07-27 — `exec_sl_level` defaulted **"1.0" → "0.886"** in lockstep with both
A+ Pine files (Aaron's call — it is what he trades, and Run 6 rode it over the full history). The
⚠ block below is AMENDED, not retracted: 0.886 is still inside the entry band and neither Run 4
defect is fixed; 0.618 / 0.702 / 0.786 stay unsupported. `mpc_bleg` PINS "1.0" rather than
inheriting, because its own Pine still ships 1.0. Earlier the same day: `Execution` now also
records MISSED SETUPS (the Pine's orange 2-of-3
callout, reporting-only) for the lab price chart's Missed layer; see `## The missed-setup watch`.
Earlier the same day: `exec_tp1_pct`/`exec_tp2_pct` defaulted 30/40 → **0/0** (Run 1
adopted; the whole position rides the runner), and **PARITY RE-VALIDATED GREEN (exit 0)** on a fresh
21,320-bar 15m export taken at the settings Aaron trades — SL fib 0.886, TP1 0%, TP2 0%, structure
trail. First run of the 0/0 exit path against the Pine. See `## The exit ladder`. Earlier the same
day: `Execution` now records BLOCKED SETUPS (the Pine's pink TRADE
BLOCKED tag, reporting-only) for the lab price chart's Blocked layer. Earlier: 2026-07-26 — the
exit levers (structure runner trail, TP2 stop floor, the three
setup toggles) ported from the Pine, the export's config columns completed, and **PARITY RE-VALIDATED
GREEN (exit 0)** on a fresh 21,230-bar `VANTAGE_XAUUSD, 15m` export — which caught a real unpinned-
engine-input bug (`fvg_require_close`). See `## The exit ladder` and `## The 2026-07-26 exit-lever sync`.

---

## The name (renamed 2026-07-16 — was `mpc_aplus` / `MpcAplusStrategy`)

`MPC` = Mental Peak Consulting (Aaron's brother's company) and prefixes every strategy in the
house. The suffix names the **narrative** the strategy trades off the shared `engines/` — here:
a **shift of structure (SOS)**, faded. The old name described the *grade filter* it happens to
use, not what it does, and "A+" would collide the moment a second MPC bot also traded A+ setups.

**"A+" is still correct vocabulary and is deliberately kept** wherever it names the brother's own
Pine concept — the A+/B/C/D grade dropdown, the "A+ SETUP SEQUENCE" block this ports, and the
`aplus_window` config field (which mirrors the Pine input "Max Time: Sweep → SOS (minutes)" and is
a lab param-grid key). Renaming those would break the line-for-line traceability to the Pine, and
`aplus_window` is also an optimizer grid key. The Pine files themselves are NEVER renamed: they are
the brother's source and the parity reference.

## Sizing — this bot sizes ITSELF

`LAB_STRATEGY` declares `self_sizing: True`, so the command-center lab does NOT run its dynamic
sizing engine over this bot's trades. `exec_risk_pct` (Pine default **10%** per trade) IS the risk
knob: it is a normal strategy param, so it is editable in the Run modal and sweepable in the
optimizer grid — that is the "manual %" for this strategy, and the SIZING MODE control is hidden
because there is nothing for it to decide. Pair a run with the **Unconstrained (No Limits)**
ruleset to see the raw behaviour with no halts and no drawdown floor cutting a day short.

**Input range (2026-07-27):** the Pine input's `maxval` was raised **10 → 100** across all four
strategy Pine files at Aaron's request — the old 10 was an arbitrary UI cap, not a safety rule, and
`exec_risk_pct` in `config.py` never had one. The DEFAULT is still 10 on both sides, so no run
changes. Two things the raised ceiling exposes and neither side checks: the `margin_long/short =
0.2` pin means TradingView rejects (or partially fills) an entry whose notional exceeds 5x equity —
silently, as a missing trade rather than an error — and the **no-minimum-stop-distance hazard**
below scales linearly with the risk %, so a degenerate stop that realised ~180% of equity at
`exec_risk_pct = 10` realises the same multiple of whatever is typed here.

## The portfolio-account seam (2026-07-17)

`Execution.__init__` takes an injected `account` (default `SoloAccount`) and a `leg` name — the seam
for stacking this bot with others on ONE shared account (`backtest/portfolio/`). What changed:
`self.equity` now reads `account.balance` (the shared balance the bot sizes against); the leg-local
`_equity_realized` is kept for R. The fill gate in `_open_position` calls `account.request_fill`,
which **scales** the bot's own desired qty to the shared room (solo → full size); partial exits and
costs `book_pnl` onto the shared balance; the full close frees the reservation; each bar reports the
live stop via `update_stop`. **Parity is unchanged:** a `SoloAccount` grants full size always, so
`compare_strategy.py` stays exit 0 — re-verified on the 20,076-bar export after the seam landed. The
account scales the bot's qty rather than recomputing it precisely so parity holds (the bot sizes off
the limit price at placement, not the fill). Do not route qty computation through the account.

## What it is (one paragraph)

A counter-trend reversal that fades exhaustion at HTF liquidity. Three-stage A+ sequence: **Arm**
(liquidity sweep by default, or an RSI divergence) → **SOS** (a same-side external structure break in
the trade direction, inside a staleness window) → **Zone+FVG** (price retraces into the 0.5–0.886 fib
band and a live FVG overlaps it; default requires the gap fully past 0.5). Entry is a resting limit — a
deep gap re-prices to the nearest shallower fib (Method 3), else the FVG's near edge, clamped into the
band; stop = fib 1.0 (leg origin) + buffer; exit = the fib TP ladder (30/40/runner) with stop→BE on
TP1, stop→TP1 on TP2, and a ratcheting trail on the runner. Full rules: `docs/MPC_SOS_FADE_SPEC.md`.

## The five modules (the data flow)

```
BarState  --SignalAdapter-->  Signals  --SosFadeSequence-->  SeqState  --Execution-->  Decision
(backtest.replay)             (Pine-named inputs)          (A+ stages)               (orders + fills + R)
```

- **`config.py`** — `SosFadeConfig`: every trade-affecting Pine input toggle, same name + default
  (**toggle parity is a hard requirement**). Instrument facts (mintick, point value, close time) are
  Layer-B injections, also here. Cosmetic Pine inputs (debug labels, boxes, table styling) are
  deliberately absent — they don't touch a trade decision.
- **`signals.py`** — `SignalAdapter`: turns a replay `BarState` into the exact Pine-named globals the
  A+ block reads. Two reconstructions are non-trivial and must stay faithful:
  1. `recentSSL` / `recentBSL` — the most-recent swept pool per side, from ten per-source slots
     (H4 / Day / Asia / London / NY high & low) resolved by latest sweep bar, sessions suppressed
     once Day is filled. Rebuilt from the liquidity engine's `mitigated` / `evicted` events.
  2. `bullDivActive` / `longVeto` — recomputed WITH the structure-break staleness (`lastExtBreakBar`)
     the standalone RSI engine can't see. **Do NOT use the RSI engine's convenience `bull_active`** —
     it omits the stale check and would diverge from the Pine.
- **`sequence.py`** — `SosFadeSequence`: the Stage 1→4 state machine, retro-link (a late-confirming
  divergence adopting an SOS that already fired), sequence death (opposite SOS / TP3 / invalidation /
  continuation BOS), and the arm-source snapshot (which Stage-1 source was live at the SOS).
- **`execution.py`** — `Execution`: entry edge → resting limit → TP1/TP2/runner ladder → staged stop
  + ratchet → %-risk sizing → graded R, on a small broker emulator (`_Broker`-style) that reproduces
  the two TradingView fill assumptions logic parity depends on:
  1. **calc-on-close, one-bar delay** — an order placed at a bar's close is active only next bar (a
     resting limit never fills the bar it was placed; an exit never fills the bar the entry filled).
  2. **intrabar path** — when a bar covers both a TP and the stop, the open's proximity to the
     extremes decides which fills first (open nearer high ⇒ price travels open→high→low→close ⇒
     targets first; nearer low ⇒ stop first). **This is the single most parity-sensitive assumption
     — it is a GUESS until `compare_strategy.py` is exit 0.**
  Each closed `Trade` also carries **reporting-only excursion** — `mfe_usd` (favorable: the most it
  ever showed in profit) and `mae_usd` (adverse: the deepest it sat against us), tracked across the
  whole hold on bar high/low (`_ext_high`/`_ext_low`) and converted to USD at close. NO decision
  reads them, so they are parity-safe (`compare_strategy.py` diffs the `px_*` decision stream, not
  `Trade`); they flow through `backtest/output.py` to the lab's equity-chart excursion overlay.
  `Execution` also records **blocked setups** (`BlockedSetup`, `execution.blocks`) — a port of the
  Pine's pink `TRADE BLOCKED` tag (`mpc_strategy.pine` 4025-4086): a setup price and the engine had
  READY (SOS in, fib agreeing, an entry edge to rest on, flat, this leg untraded) that one of the
  strategy's OWN toggles refused. Same six reason codes in the same PRECEDENCE (`f_blkCode`: 1
  direction off · 2 arm source off · 3 final hour · 4 divergence/extreme veto · 5 HTF breakout · 6
  HTF bias), the same hover text as `f_blkWhy`, and the Pine's `sosBar*10 + code` dedupe generalised
  to the reason SET — one record per setup per distinct COMBINATION, so a setup blocked for twenty
  bars is one record but a set that changes is a genuinely different refusal.
  **ONE DELIBERATE DEVIATION:** the Pine reports only the FIRST blocker (a chart tag has room for one
  line); we record EVERY rule refusing the setup, because the lab filters by reason and "blocked by
  the veto" has to stay true when the final hour was also blocking. Precedence survives as the ORDER,
  so `codes[0]` (exposed as `.code`) is exactly what `f_blkCode` would have returned alone — a
  per-reason count taken off the primary still reconciles with TradingView.
  **Reporting-only and parity-safe**, exactly like the excursion fields:
  nothing reads a record back, so no decision can move and `compare_strategy.py` diffs the same
  `px_*` stream as before. The recording hangs off `_place_entries` (reading gates `_armed`
  computed, never recomputing them), which is why `mpc_bleg` gets none — it overrides that method,
  and those codes describe why an *A+* setup was refused. Surfaced on the lab price chart's Blocked
  layer; the full path is in `command-center/backend/CLAUDE.md` → *Blocked setups*.
  `Execution` also records **missed setups** (`MissedSetup`, `execution.misses`) — the OTHER half of
  "why didn't this trade", and a port of the Pine's orange 2-of-3 callout (`f_w23Arm` / `f_w23`,
  `mpc_strategy.pine` 3064-3194 + 4022-4023). See *The missed-setup watch* below.
- **`strategy.py`** — `MpcSosFadeStrategy`: the driver. `run(df, warmup=…)` replays a canonical frame
  end-to-end; `step(bar_state)` does one bar. Collects `.decisions` (the per-bar stream) and
  `.execution.trades`.
- **`secondary.py`** — the 1m sniper re-entry (below). `Structure1m` (1m structure feed, port of Pine
  `f_struct1m`) + `SecondaryArm` (the latch/arm, port of Pine `f_secArm`). Consumed by `run_dual`.

## The missed-setup watch (2026-07-27) — the setups that died, not the ones that were refused

A **block** and a **miss** answer the same question one step apart in a setup's life, and mixing
them up makes both useless. A block is a trade the strategy had FULLY READY and one of its own
toggles refused. A miss never got that far: it reached 2 or 3 of the three confluences and then
DIED. Neither places an order, so neither is in any trade list, any equity curve, or any broker
report — the only place either is countable is here.

The three confluences, and what "met" means (Pine `f_w23`):

| # | Confluence | Met when |
|---|---|---|
| 1 | **ARM** | a liquidity sweep or an RSI divergence armed Stage 1 — and the source that fired is one you have ENABLED |
| 2 | **SOS** | always: it is why the watch is open at all |
| 3 | **ZONE** | price tagged the 0.5-0.886 band AND (with Require-FVG on) a gap was live in it while price was there |

**Exactly one thing is ever missing**, which is why `MissedSetup` carries a single `code` where
`BlockedSetup` carries a list. At 2 of 3 it is the arm or the zone (codes 1-3); at 3 of 3 every
confluence was there and the entry still never happened, so the record names the ENTRY-side reason
instead, in the Pine's precedence: veto → final hour → HTF → "the limit rested and price never
touched it" (codes 4-7). `reasons` is still exposed as a one-item LIST purely so a miss and a block
read identically all the way downstream.

**Three deliberate deviations from the Pine, all reporting-side:**

1. **Every miss is recorded; nothing is filtered at write time.** The Pine has three view filters
   (`debugShow23`, `debug23Filter`, `debugShow23Disarmed`) plus a `debugDays` recency window because
   TradingView caps a chart at 500 labels. The lab has neither problem, and a miss filtered away at
   write time can never be counted later. The chart filters BY REASON instead, which is strictly
   more expressive than the Pine's three presets.
2. **`near` replaces those presets.** Each record carries the Pine's own near-miss test
   (`metN == 3 or (zone reached and zone not met)`). The chart derives its DEFAULT view from it —
   see `command-center/backend/CLAUDE.md` → *Missed setups* — so the layer opens on the Pine's
   default and one click widens it, which the Pine's radio buttons cannot do.
3. **A setup that filled this bar closes as TRADED immediately.** The Pine assigns `tradedSosL`
   further down its script than it reads it, so on the fill bar it still reads the previous value.
   Both end with no callout; ours gets there a bar sooner, and it is the correct answer on the one
   bar where they differ (a trade that opened and closed inside the same bar, which the Pine would
   have booked as a miss).

**Where it runs, and why not where the blocks run.** `_record_misses` is called from `step()`,
between the fills and the placement — the same slot the Pine calls `f_w23` from. It CANNOT hang off
`_place_entries` like the block recorder does: a setup keeps accumulating state while a position
from the other side is open, and that path never runs then. That is also why `_bar_gates` was
extracted from `_armed` (the final-hour / HTF / bias gates are needed on every bar, not only when
flat) and why `mpc_bleg` needs the explicit `_records_misses = False` opt-out rather than getting
the exclusion for free.

**Two additions this needed elsewhere, both parity-neutral.** `SeqState` gained `l_arm_src` /
`s_arm_src` (Pine `armHolderL`/`armHolderS`) — the source holding the Stage-1 slot, which is the one
thing the live `sos_*_swp`/`sos_*_div` flags cannot tell you once the execution layer has filtered
them through the toggles, and without it a "your arm source is off" reason could not say WHICH one.
`build_results` gained `missed_setups`.

**Measured on the shipped window** (XAUUSD M15, 2025-03-04 → 2026-07-27, 33,041 bars, defaults):
46 trades, 80 blocks, **93 misses** — 50 "No retrace" (none near), 35 "No FVG in zone" (all near),
4 "Never filled", 4 "Final hour". So the chart opens on 43 markers and the routine 50 are one click
away. The 35 is the actionable number this whole layer exists to produce.

## Secondary (1m sniper) re-entry — `exec_secondary` (built 2026-07-19, NOT committed)

The 1-minute re-entry Aaron prototyped in Pine, built as the *exact* version here (Pine can only
sample the 1m engine once per 15m bar — its own tooltip says "the exact version is the Python port").
**Full rules + design: `docs/MPC_SOS_FADE_SECONDARY.md`.** One paragraph: after the **primary** 15m
A+ trade on a leg has traded and gone flat, while the 15m div + SOS are still live and price is back
in the 0.618-0.886 zone, a **1m shift of structure** in the trade direction rests a limit at a 38.2%
retrace of that tight 1m leg (stop = 1m leg origin; TP1/TP2 = 15m 0.5/0.382; runner = TP3). One
re-entry per 1m leg; a re-entry is never the first trade on a leg.

- **`run_dual(df15, df1m)`** merges the two streams on a close-time clock: the **primary** is stepped
  on 15m bars exactly as `run(df15)` (so parity is untouched); the **secondary** latches/arms/fills/
  manages on real **1m** bars — the sniper "in and out fast" a 15m bar can't express.
- **Execution** grows an `_entry_kind` tag + `step_secondary(bar1m, arm)`. A 15m bar only ever
  touches a `primary` position; a 1m bar only a `secondary`. They share the one position slot but
  never the same trade (the secondary arms only when flat), so the tag is all that separates them.
  With `exec_secondary` OFF, no secondary ever opens, so `step()` is byte-identical to before.
- **NO Pine parity gate** — the Pine is only the approximate version, so this is verified **visually**
  (the lab price chart + the 15m→1m drill-down). The offline guard is
  `test_run_dual_primary_is_identical_to_run_when_secondary_off` + the hand-traced arm/exec tests in
  `tests/test_secondary.py`, and OFF parity was re-confirmed on the real M15/M1 cache (`run` ==
  `run_dual`, 40 trades byte-identical). `compare_strategy.py` (which runs `run`, not `run_dual`)
  stays the primary's gate.
- **Sparse-data note:** the secondary is rare (a live leg + zone + a 1m SOS + div, all at once). Over
  the ~4 days of local 1m cache it fired 0 times — expected, not a bug (see the arm trace). A real
  visual verification needs a longer 1m window (broker serves ~35d direct; older via ticks).

## The exit ladder — every TP/SL lever, and which ones are switchable

The register of how this bot (and `mpc_bleg`, which reuses the whole ladder) decides where the
stop and the targets sit. Keep it current: a new exit lever in the Pine lands here, in `config.py`,
in `mpc_strategy_export.pine`, and in `compare_strategy.py` in ONE commit.

| Stage | What sets it | Switchable? |
|---|---|---|
| **Stop loss** | A fib on the deep side of 0.5, `exec_sl_level` ∈ {0.618, 0.702, 0.786, **0.886**, 1.0}, then `exec_sl_buf_tk` ticks beyond it. **Default 0.886 since 2026-07-27** (the deep edge of the entry band, and what Aaron trades); 1.0 = the leg origin. | **0.886 and 1.0 only** — the three shallower levels are unsupported, see the warning below |
| **TP1 / TP2** | Fibs, chosen AUTOMATICALLY by how deep the entry was. Deep entry → TP1 = 0.5, TP2 = 0.382. Shallow → TP1 = 0.382, TP2 = 0.0 (the swing extreme). | **No** — only the sizes (`exec_tp1_pct` / `exec_tp2_pct`, **both default 0** since 2026-07-27: bank nothing, ride the runner) |
| **TP3 (the runner)** | No target at all. It rides a trailing stop, and it is where the strategy's money is (>100% of net in every window measured). | **Yes** — see below |
| **Stop staging** | Three phases, always on: (0) the full stop → (1) after TP1, breakeven + `exec_be_buf_tk` → (2) after TP2, a floor, then the trail. | **No** |
| **The TP2 floor** | `exec_tp2_stop_mode`: **"TP1 price"** (tight, can scratch the runner on the first pullback) / "Breakeven" (most room) / "One trail step behind" (never below breakeven). | **Yes** — dropdown |
| **The runner trail** | `exec_runner_trail`: "Fixed step" (a `exec_trail_step` grid ratchet anchored on TP2) / "Structure (swing)" (park the stop at the structure engine's last confirmed swing low/high, offset by `exec_struct_trail_buf_tk`) / **"Structure + % ratchet"** (same anchor, then climb one `exec_trail_pct`-of-price step per step of favourable move). | **Yes** — dropdown |
| **The ratchet step** | `exec_trail_pct`, default **1.0**. Only read in "Structure + % ratchet" mode. A PERCENT of price, never dollars — see below. | **Yes** |
| **Early bail-out** | `exec_close_opp_sos` (default OFF) force-closes on an opposite SOS instead of riding to the stop. **Measured INERT** (Run 5): turning it on produced a byte-identical trade list — an opposite SOS never fires before SL/TP has already resolved the position. There is nothing on the other end of this lever. | toggle exists, **does nothing** |

The floor and the trail compose: past TP2 the stop is the floor, and the trail may only tighten
it further, never loosen it. With Structure selected and no confirmed swing yet, the trail is
absent and the floor alone holds the stop.

**The TP rungs default to 0/0 (2026-07-27) — and 0 does NOT disable the target.** The rung SIZE and
the target PRICE are separate things. At 0 no size leaves at TP1/TP2, but `_advance_stage` still
watches those prices, so touching TP1 still stages the stop to breakeven and touching TP2 still
installs the floor and hands the runner to the trail. The whole position then exits as one runner leg.
This is the shipped behaviour because it is what Run 1 measured as best AND what Aaron actually trades.
`test_zero_pct_rungs_bank_nothing_but_still_stage_the_stop` locks both halves of that.
Python needs no special case (`_remaining_brackets` computes p1 = p2 = 0 and emits neither bracket);
**the Pine does** — `strategy.exit(qty_percent = 0)` closes the WHOLE position, so both Pine files skip
the call when the rung is 0. If you ever port a new rung, port that guard with it.

**`mpc_bleg` overrides TP1, TP2 and the SL** with its own band prices (SL = band origin, TP1 =
the broken swing extreme, TP2 = the expansion extreme). Everything from the staging down —
floor, trail, both dropdowns — is this table, inherited unchanged.

**Aaron's brother's tested best combo (the shipped default 2026-07-26):** Structure trail +
buffer 20 ticks + TP2 floor = TP1 price.

### The swing ratchet (`"Structure + % ratchet"`, DEFAULT since 2026-07-28)

**The problem it fixes.** The plain structure trail PARKS the stop at the last confirmed swing.
That swing is a LAGGING anchor: in a strong leg it ends up a long way behind, and the gap between
it and the high IS the runner's give-back. Measured over 6.6y / 164 trades (XAUUSD 15m, SL 0.886):
the strategy banked **27.5% of the total profit it ever showed open**, and on the 78 trades that
ran ≥$10 of gold it captured $2,283 of the $5,300 they moved — **57% handed back**.

**What it does.** Same anchor (`last_conf_swing ± exec_struct_trail_buf_tk`), but from there the
stop climbs one `exec_trail_pct`-of-price step for every step of favourable move. It falls back to
the bare anchor until the move is one full step past it, so it is **never LOOSER than the plain
structure trail — only equal or tighter** (`test_swing_ratchet_is_never_looser_than_the_plain_structure_trail`).

**Measured, vs the plain structure trail** (same 6.6y window, same 164 trades, same entries):

| | order-free edge | net | run actually banked | max DD |
|---|---|---|---|---|
| Structure (swing) | 107.6R | $2.82M | **43%** | 54.7% |
| Structure + 1% ratchet | 109.3R | $3.81M | **53%** | 54.7% |

⚠ **Both rows were measured at `exec_tp1_pct = exec_tp2_pct = 1`, NOT at the shipped 0/0** (found
2026-07-28). The A/B is apples-to-apples so the comparison stands, but the absolute figures are not
the shipped configuration: at the true 0/0 default the same window gives **110.65R**, and the 1%+1%
rungs cost 1.4R. Quote 110.65R as "the current bot", not 109.3R — and run `compare_strategy.py` at
0/0 so the parity gate tests what the Pine actually ships.

**Read this honestly.** The EDGE is unchanged — +1.7R over 164 trades is noise, and 1.5% (106.3R)
/ 2.5% (110.4R) bounce either side of it, which is the signature of randomness rather than an
optimum. What is real is the 10-point jump in how much of each run survives to the close, and it
costs nothing: **percentage drawdown is IDENTICAL (54.7%, same day)** — the bigger DOLLAR drawdown
in an early write-up was a compounding-account artifact, not a risk increase. Only 11 exits change:
8 better (+13.2R), 3 worse (−11.5R), and ONE trade (2025-10-21, +25.23R → +16.27R) is nearly the
whole downside.

**Why PERCENT and not dollars.** Gold ran 1,500 → 3,400 across the test window, so no fixed $ step
is right at both ends ($20 is a 1.3% trail at 1,500 and 0.6% at 3,400). The dollar version tops out
at **100.4R vs the percent version's 109.3R** for exactly that reason, and it only ever climbs
toward the plain structure trail as the step widens — in dollars this dial cannot beat what it
replaced. Do not "simplify" it back to a $ step.

**Do NOT add a hard take-profit on top of it.** Tested (2026-07-28): a target is either too loose to
fire (40R was byte-identical to no target — no trade in 6.6y ever reached it) or tight enough to cut
the tail that IS the profit (15R → 86.4R, a fifth of the edge gone). The 25R row looks best on the
table and is three lucky trades — only 3 of 164 ever reached 25R peak. There is no useful middle.

**Extension fibs (NEGATIVE fibs past 0.0) — measured 2026-07-28, REJECTED in every form.** This is
the most natural-looking idea on the list and the one Aaron trades by hand, so it gets its own record
rather than a line in the list below. Past the 0.0 fib the runner has no target at all, so the
proposal was to bank at the standard extensions the way a discretionary trader would.

*As TAKE-PROFIT rungs, shallow* (0.0 / −0.272 / −0.414 / −0.618, all off at −0.618 — Aaron's hand
rule): **109.3R → 69.1R**, a third of the edge gone. Every one of 14 allocations lost, and the
ranking was perfectly monotonic in how much was banked — the limit of "bank less" is the shipped
runner. Best of them (50% at −0.618 only) still only reached 92.4R.

*As a STOP FLOOR* (bank nothing, but ratchet the stop up the extension ladder one rung behind price):
**worse than the targets — 109.3R → 56.1R at best**, roughly half the strategy. A fib level is a
FIXED price and does not breathe; the structure trail moves with the market and survives an ordinary
retrace, a horizontal line does not. The 23.5R trade became 10.5R, cut on a pullback six legs before
it actually finished. Same lesson as every other tightening experiment above.

*As DEEP rungs* (−1 / −2 / −3 / −4 / −6 — take nothing until the trade is already a monster, then
trim): far better than the shallow version and still not an improvement. Aaron's −1:10% / −4:50% /
−6:rest ladder = **106.3R**. The only rows that beat the baseline sit at −6, and **exactly ONE trade
in 6.6 years ever reached −6** (−6 take 100% = 112.2R, i.e. +1.55R over the true 110.65R baseline,
from a single 2020 trade). That is a description of July 2020, not a rule.

**The pattern, and why there is no ceiling to find.** Rule cost tracks how OFTEN the rule fires:
−1 touches 8 trades and costs 7–14R, −4 touches 2 and costs 1–3R, −6 touches 1 and costs nothing.
Every candidate converges on the baseline from below as it stops doing anything. There is no depth
at which banking becomes profitable — there is only a depth at which it becomes harmless.

**The shape of the book, which is the real reason.** Of 164 trades only **29 ever reach the 0.0 fib**,
11 reach −0.618, 8 reach −1, 2 reach −4, 1 reaches −6. Those **11 trades past −0.618 make 106R of the
109R total**. The two biggest ran to −4.77 and −6.74 and the trail paid −3.69 and −5.68. Any fixed
ceiling is applied to every trade, so it necessarily caps the handful that carry the strategy. Eight
trades DO run past 0.0 and hand the whole extension back (they exit at the 0.382 floor) — that leak
is real, but it is worth 5.7R and the cheapest rule that plugs it costs 17R.

**Four other exit ideas measured and REJECTED the same day, so they are not re-tried:** tightening
the trail in any form (fixed step $2–$40, chandelier 2–8×ATR, giveback caps 25–50%) costs 60–90% of
net; banking at the TP rungs (25/25, 33/33, 50/0) costs 60%; "stay loose then clamp once it is a
monster" (>3R/5R/8R/15R → a tight trail) costs 20–45%; and exiting on an opposing RSI divergence past
TP2 costs 77% — only 18 of 164 trades ever print one, the six biggest give-back trades print ZERO,
and where it does fire it fires 2–4 times so you can only ever act on the earliest and worst one.

**⚠ `exec_sl_level` — `"0.886"` (the default since 2026-07-27) and `"1.0"` only. Do NOT sweep or
ship 0.618 / 0.702 / 0.786** (Run 4, 2026-07-26). The entry is a resting limit inside the
**0.5–0.886 fib band**, and all four sub-1.0 levels sit inside that SAME band — so the stop can be
placed at, or past, the entry price. Nothing validates the result.

**Why 0.886 is nonetheless the shipped default.** It is what Aaron trades, the 2026-07-27 parity
run went GREEN at it, and Run 6 rode it over the broker's whole intraday history (188 trades,
107.7R, 293x, −54.9% maxDD) with no degenerate stop. That is 0.886 being the SHALLOWEST point the
entry limit can itself rest at — the stop is just past the deep edge of the band, so the collapse
mode needs the entry to fill at almost exactly 0.886. **It is evidence of absence, not a
guarantee:** both defects below are still OPEN at this level, so treat a sudden outsized loss as
this hazard until proven otherwise, and turn the Pine's "Minimum stop distance" on for live use.

⚠ **But know what turning it on costs: the guard exists ONLY in the Pine.** `mpc_strategy.pine`
has `execMinStopMode` / `execMinStopVal` and applies them as a real entry filter; `config.py` has
**no equivalent at all**, `mpc_strategy_export.pine` emits **no `cfg_min_stop*` column**, and
`compare_strategy.py` therefore cannot see the setting. At the `"Off"` default the two sides agree
and parity holds. **The moment the filter is switched on in TradingView, the Pine refuses setups the
Python still takes, and the comparator reports GREEN anyway** — it is diffing against a config it
cannot read. This is the one known Pine↔Python divergence on the A+ pair. Closing it is Run 7's
"what adoption requires": `exec_min_stop_mode` / `exec_min_stop_val` in `config.py`, a `cfg_min_stop`
column in the export, and a `_TOGGLE_COLS` decode — one commit, then re-run parity.

Measured consequence at `0.786` + 20 ticks
over full history: stop distance collapses to **$0.20** on 15m gold, `qty = risk / stop_distance`
builds a **39,033 oz (~$78M notional)** position, one bar takes **18× the intended risk**, and
equity ends at **−$63,726** — after which the bot stops trading entirely. Two defects behind it,
both still OPEN and both live-trading hazards:
1. No validation that the chosen SL fib is on the correct side of the entry, or a sane distance
   from it. Assume `mpc_strategy.pine` has the same exposure (same dropdown) until checked.
2. **No minimum stop distance.** `execution.py:329` sizes correctly —
   `qty = (equity * exec_risk_pct / 100) / dist` — so risk IS dynamic and a wider stop DOES give a
   smaller lot. The formula is not the bug. What it assumes is: `exec_risk_pct` is only the real
   risk **if the exit actually happens at the stop price**. That holds when the stop is wider than
   a typical bar (which `"1.0"` = leg origin always is) and fails completely when it is narrower —
   price gaps straight through and the realised loss is unbounded. At a $0.20 stop on 15m gold the
   nominal 10% risk was realised as **~180% in one bar**. So the guard needed is a floor on
   `dist` (e.g. ≥ some ATR multiple), NOT a change to the sizing math. A position/margin cap is
   worth adding as a second backstop, but it treats the symptom.

**This bot has no R:R dial.** Targets are fibs and the stop is a fib, so the risk-reward ratio is
an OUTPUT of leg geometry, never an input — no combination of existing parameters can express
"risk 1 to make 3". Answering that question needs an ATR-based stop distance + fixed-R targets,
which is new code here AND in the Pine. See Run 4's writeup for the two proposed routes.

**Every sweep of these levers is logged in `mpc_sos_fade_optimization.md`** — one entry per run,
with the full grid, per-year and per-half R, and whether it was adopted. Read it before tuning
anything here so a question already answered is not re-measured. Seven runs are recorded; **Run 1 is
now ADOPTED (2026-07-27)**, the other six are measured and unadopted — Runs 1–3 on the same
185,530 M15 bars / 187 trades, Runs 6–7 on the full 185,668-bar history at 188 trades:

1. **TP split** (21 combos) — monotonic; best is `exec_tp1_pct=0, exec_tp2_pct=0` (100% on the
   runner) at 70.7R vs 47.9R for the shipped 30/40 split. **ADOPTED 2026-07-27 as the default**, in
   lockstep across `config.py` and both A+ Pine files. The tick-mode re-run this entry originally
   asked for was overtaken by better evidence: Aaron's own TradingView chart had been running the
   rungs at 1% each (the closest the input would take to 0) for the whole 2020-2026 Deep Backtest,
   so the setting has a real 162-trade out-of-sample record, not just a bar-mode sweep. Adopting it
   also FIXED a live hazard — see the `qty_percent = 0` guard note in `## The exit ladder`.
2. **The whole ladder** (525 combos) — re-confirms (1), and finds **both dropdowns are already at
   their best value**: structure trail beats every fixed step (best fixed = 62.5R), the trail
   buffer is nearly irrelevant (0.4R across 10→80 ticks), and `exec_tp2_stop_mode="One trail step
   behind"` is actively harmful (caps out at 42.3R). The TP split is the only lever with real
   variance: ~−2R per 10% moved off the runner.
3. **Stop TIMING** (35 combos, research-only dials — both moments are hardcoded in Python AND
   Pine) — **the shipped timing wins; nothing to adopt.** Delaying breakeven grows the average
   winner 3.7x (0.80R → 2.96R) but total R falls 25% and drawdown grows 3.5x, monotonically bad.
   **This settles the open question below about whether stop→BE on TP1 caps runners: it does not.**
   It converts full losses to scratches (avg loss −0.73R with it, −0.99R without) and that is worth
   more than the upside it forgoes. The biggest winner was +15.03R in all 35 combos — the trade
   that makes the money never traded against its stop, so this lever cannot reach it.
4. **Stop PLACEMENT** (40 combos) — **INVALID, discard the numbers.** Four of the five
   `exec_sl_level` values put the stop on top of the entry; equity ended at −$63,726. See the ⚠
   warning above — it is this run's writeup.
5. **"How do I cut the losers quicker?"** (2022+ cache, 118 trades) — **there is nothing to cut
   quicker with.** Both early-exit toggles measured at exactly zero effect (`exec_close_opp_sos`
   and `exec_htf_exhaust_only` each produced byte-identical trade lists), and a time stop would
   cut the WINNERS (all net comes from trades held past 20 bars). The diagnosis is the value:
   **every loss is a trade that never touched TP1**, and TP1 sits ~0.45R away while the stop sits
   1R away, so a losing trade dies a median 0.34R short of the level that would have staged it to
   breakeven. That makes this a stop-DISTANCE problem, not a stop-timing one. Re-running
   `exec_sl_level` on a clean window scored **59.3R at 0.786 vs 33.6R shipped at the same
   drawdown** — but 8 of its 108 trades reproduced Run 4's sub-$2-stop hazard, so it stays
   unadoptable. ~~The minimum-stop-distance guard is worth a measured ~+26R.~~ **That ~+26R figure
   is WRONG — superseded by Run 7**, which replayed the guard properly instead of filtering rows out
   of a finished trade list.
6. **"Cut trades early / block the losing pattern"** (2026-07-27; 8 years, per-bar R paths, ~40 cut
   variants + 10 entry blocks) — **the question is CLOSED, do not build it.** No loser runs straight
   to its stop (min MFE **+0.09R**, median +0.51R) and winners sit underwater just as deep (median
   MAE −0.36R), so the two populations are indistinguishable while the trade is live. Every cut
   family loses money. The −54.9% drawdown is a **losing streak at 10% risk**, not give-back —
   **risk % is the only lever that moves it.**
7. **The minimum-stop guard, measured properly** (2026-07-27; 17 real replays, three independent
   definitions: fixed $, % of price, ×ATR) — **it PASSES, at a MILD threshold only, as a SAFETY
   rule.** All three definitions agree: light (blocks 3–6 of 188 trades) = **+0.7 to +2.7R**;
   medium/heavy = **−12 to −39R**. Best is **`pct 0.1`** — the stop must be ≥ 0.1% of price
   (self-scaling, one line in Pine): 182 trades, **+2.5R**, blocks the −1.98R trade, and leaves
   2021/2024/2025/2026 **byte-identical**. Two cautions: the +2.5R is **noise-level** (ship it to
   close the hazard, not for the money — read sumR, never the ragged x-multiple), and it does
   **NOT** fix drawdown (−54.9% → −54.3%). **Not adopted — awaiting Aaron's go.** The follow-up it
   unblocks: re-run Run 5's `exec_sl_level` sweep with the guard installed, to see whether 0.786
   becomes adoptable.

## The 2026-07-26 exit-lever sync

`mpc_strategy.pine` gained a structure-based runner trail, a TP2 stop-floor dropdown, an SL fib
dropdown and three setup toggles. Ported here, with the Pine's defaults adopted verbatim:

- **New config fields** — `exec_runner_trail` (**"Structure (swing)"**), `exec_struct_trail_buf_tk`
  (20), `exec_tp2_stop_mode` ("TP1 price"), `exec_aplus` (True), `exec_bleg` (False here, True in
  `BLegConfig`), `exec_fvg_50` (False). `exec_sl_level` already existed.
- **`signals.py`** — `Signals` gained `last_conf_high` / `last_conf_low`, passed straight through
  from the structure snapshot. Only `_advance_stage` reads them, and only past TP2.
- **`execution.py`** — `_trail()` gained the structure branch; the stage-2 floor moved out of
  `_current_stop()` into `_stage2_floor()`. Both anchors are snapshotted at the bar's CLOSE, the
  same one-bar delay `_max_fav` already had, because the stop placed at bar N's close is what bar
  N+1 trades against. Reading the live swing instead would silently make the trail clairvoyant.
- **`exec_fvg_50` is NOT ported** (same standing as `exec_conf_sz`) — `compare_strategy.py` refuses
  an export taken with it on. `exec_bleg` on is refused too: those trades belong to `mpc_bleg`.

### PARITY GREEN 2026-07-29 (exit 0) — the ratchet build, at the shipped rungs

`compare_strategy.py "VANTAGE_XAUUSD, 15_7b2f3.csv" --warmup 100` → **exit 0**. 21,494 bars,
2025-08-31 → 2026-07-29. Green at warmup 200, 500, 1000 and 2000 too.

This clears the 2026-07-28 stale warning. Two things make it the run that was actually needed:

1. **It carries the ratchet through the export.** `cfg_exitmode = 20` — the tens digit is the trail
   method, and it went 2-way → 3-way when `"Structure + % ratchet"` landed. Plus `cfg_trail_pct = 1`.
   An export taken before that change would decode the ratchet as the plain structure trail and go
   green while silently comparing two different exit ladders.
2. **It was taken at `cfg_tp1_pct = cfg_tp2_pct = 0`** — what the bot actually ships. The previous
   green run and the 109.3R ratchet headline were both at 1%/1%, which is not the shipped config.

26 trades graded, **sum 30.29R** over the ~11 months. Note this is the TradingView window, not the
6.6-year MT5 window the 110.65R baseline and the extension-fib work were measured on — the two
numbers are not comparable and neither supersedes the other.

⚠ **Not covered by this run:** `mpc_strategy_export.pine` still has no `execMinStopMode` /
`execMinStopVal` column. The run was taken at the `"Off"` default where the gate is inert, so it
proves nothing about the minimum-stop filter. Turn that filter on and this green goes meaningless.

### PARITY GREEN 2026-07-26 (exit 0) — and the bug the run caught

`compare_strategy.py "VANTAGE_XAUUSD, 15_e8beb.csv" --warmup 100` → **exit 0**, bar-for-bar identical
on 21,130 of 21,230 bars (20,730 15m bars, 2025-09-01 → 2026-07-25). The export starts mid-history, so
the ~100-bar warmup is genuine engine cold start, not a mask: every warmup from 100 up is green and the
first mismatch at warmup 0 is bar 16.

The first run came back with ONE mismatch, and it was a real bug, not noise:

> `bar 20315 2026-07-12 23:00:00 px_edge: py=4100.94376 pine=None`

Python computed a short entry edge on a bar where the Pine had none. The fib matched to the decimal
(`dbg_fib_p2`/`p6`/`ash`/`asl` all identical), so it was an **FVG lifetime** difference: Python held a
bearish gap created on the first bar after the weekend gap that the Pine never created at all.

**Root cause — an unpinned engine input.** `mpc_strategy.pine` HARDCODES the middle-bar close-cleared
check in its FVG detection (`close[1] > high[2]` / `close[1] < low[2]`, lines 1686/1688). The
`fair_value_gaps` engine has that as the OPTIONAL `require_close` flag, defaulting **False** (it mirrors
`mpc_assistant.pine`, where it IS an input and IS off). Nothing exported it, so nothing caught it — the
engine happily created gaps whose middle candle never cleared the void.

Fixed by making it explicit rather than implicit: `EngineConfig` gained `fvg_require_close` (default
False, so no other consumer moves) and `MpcSosFadeStrategy.engine_config()` pins it **True**, alongside
the `fvg_max_count=7` and `show_internal=False` pins that were already there for exactly this reason.
`test_engine_config_pins_every_input_the_pine_moved_off_its_default` locks all three.

**The lesson is the class of bug, not the flag.** An engine input the decision stream does not export
is invisible to the parity check until a fresh export happens to disagree — and this one had been wrong
since the FVG engine made the gate optional on 2026-07-18. Any time an engine's default changes, check
every `engine_config()` that replays a Pine which does NOT share that default.

**What the new export columns immediately paid for:** they revealed the Pine was running
`execTp1Pct = 20` / `execTp2Pct = 20`, not the 30/40 defaults. Before this change no column carried
them, so the bot would have silently replayed 30/40 against a 20/20 Pine and the diff would have been
blamed on logic.

**The export had a real hole while this was in flight.** `execRunnerTrail` defaulted to Structure in
the Pine on 2026-07-25, but no `cfg_*` column carried it, so `compare_strategy.py` configured the
bot to the fixed-step fallback and diffed two different strategies. Any parity result from that
window is drift, not a bug. `mpc_strategy_export.pine` now carries `cfg_bits` bits 16384 /
32768 / 65536 (`execAplus` / `execBLeg` / `execFvg50`), `cfg_exitmode` (both exit dropdowns), and
one raw column each for the six exit numerics + the scratch band. An export WITHOUT `cfg_exitmode`
is pre-2026-07-26 and `compare_strategy.py` prints a loud warning rather than guessing.

## Deliberate deviations from the Pine (per the framework)

All OFF for the parity check (to match the Pine); each is a real-run choice:
1. **Flat-by-close** — force-flat + no new entries N minutes before the daily close (`flat_by_close`).
   **Default False, and measured 2026-07-16: leave it that way.** A/B over 6.5 months: OFF $39,454 /
   PF 1.444 vs ON $19,813 / PF 1.253 on the same 32 trades. Only 4 trades ever held overnight, they
   were all winners, and they made 70% of the profit; total swap for the period was −$36.80. Flatting
   early buys a smaller drawdown for half the profit. (This param was DEAD CODE until 2026-07-16 —
   `_in_flat_window` read only `sig.ny_hour`, so "minutes left" was always a multiple of 60 and never
   hit the ≤15 window. Any A/B run before that date compared a flag against itself.)
2. ~~**Sizing** — real runs swap in the dynamic sizing engine under a ruleset.~~ **No longer true
   as of 2026-07-16:** the bot declares `self_sizing: True`, so real runs keep the Pine's own fixed-%
   sizing (`exec_risk_pct`) and the engine never re-sizes them — this is NOT a deviation any more,
   parity and real runs size identically. See `## Sizing — this bot sizes ITSELF` above.
3. **Fill model** — parity REQUIRES `fill_model="bar"` (the Pine's own intrabar guess, zero costs).
   Real runs set `fill_model="tick"` + `account_profile` + `symbol` for real bid/ask fills and costs.
   See `backtest/CLAUDE.md` A2 — tick mode disagreeing with the Pine is correct, not drift.

## Engine-construction pins (`MpcSosFadeStrategy.engine_config`)

Two engine inputs are NOT in the decision stream, so the bot pins them to the Pine STRATEGY's own
input defaults rather than the shared engine defaults — miss either and the fib the bot reads drifts:
1. **`fvg_max_count=7`** — `mpc_strategy.pine` sets Max Active FVGs to 7 (the FVG engine default is 6);
   a smaller cap evicts the oldest gap one bar sooner and drops an entry edge Pine still holds.
2. **`show_internal=False`** — the Pine's "Show Internal Structure" input defaults OFF, and Pine gates
   the ENTIRE internal block behind it (`internalActive = showInternal`), so `i_confirmed_*` is never
   set and the **Structure fib never adopts a more-extreme internal swing** as its anchor. The
   `market_structure` engine ALWAYS computes internal structure, so the `EngineStack` must be told to
   suppress the internal-derived snapshot fields (it blanks `i_confirmed_*` + `ifib_seed_*` when this
   is off). This is a real "a drawing toggle changes trade logic" coupling in the Pine — do not drop it.

## The three parity fixes (2026-07-16) — read before touching signals/fib

The port went green after fixing three faithful-translation gaps; each is a class of bug to watch for:
1. **Internal-swing adoption** (the `show_internal` pin above) — the engine's always-on internal
   structure fed the fib an anchor the Pine strategy never had (internal display off).
2. **Sweep double-count at the daily/session rollover** — Pine records a sweep on `d_lMit and not
   d_lMit[1]` (a bar-to-bar edge of a persistent VARIABLE). When a daily/session/H4 level rolls at
   18:00 and is re-taken on its own creation bar, `d_lMit[1]` (the old level, already swept) is still
   true, so no edge fires. The engine models levels (create / mitigate / EVICT) and the naive
   reconstruction latched on every `mitigated` event, re-recording the rollover sweep — which made a
   stale sweep look fresh and armed a trade Pine didn't. `signals.py` now reconstructs the Pine
   variable: reset on `created`, set on `mitigated`, **left alone on `evicted`**, edge vs the prior bar.
3. **The forming last bar** — TradingView exports the final (still-forming) bar's plotted series as
   NaN. `compare_strategy.py` now marks that bar `_px_present=False` and skips it, instead of reading
   `fillna(0)` as a real "stage 0" and flagging a phantom mismatch.

## The parity gate — `tools/compare_strategy.py` + `/audit-strategy`

The standing regression harness (same pattern as the engines' `compare_*.py`). `mpc_strategy_export.pine`
(in `indicators/`) = `mpc_strategy.pine` + an appended block that plots the per-bar decision stream
(`px_*`) and every toggle (`cfg_*`). Export it to CSV on a 5m XAUUSD chart; `compare_strategy.py` reads
the toggles, configures the bot identically, replays the same bars, and diffs the decision stream. Exit
0 = bar-for-bar identical. On a mismatch it names the first diverging bar + field. Run it via
`/audit-strategy`, or:
```
command-center/backend/.venv/bin/python strategies/python/mpc_sos_fade/tools/compare_strategy.py <export.csv> --warmup N
```

### The 2026-07-22 re-sync (the export was 7 days stale)

`mpc_strategy_export.pine` was last regenerated 2026-07-15 and had drifted on three trade-affecting
Pine changes, so any diff it produced was July-15 drift, not a bug. Regenerated from
`mpc_strategy.pine` @ `361f007`:

1. **The veto is now SOS-aware** (Pine `longVetoA`/`shortVetoA`, ~3701). A divergence printing AFTER
   the SOS no longer vetoes its own setup — once stage 2 is live the setup is waiting on a retrace,
   and an opposing divergence formed during that retrace IS the pullback. Only one already live at
   or before the SOS bar still blocks. Extreme RSI keeps blocking LIVE. **Ported here**: the veto
   moved out of `SignalAdapter.update()` (which has no sequence state) into `signals.sos_aware_veto()`,
   which `execution.py` and `secondary.py` both call. `Signals` now carries the veto PARTS
   (`veto_on`, `veto_rsi_ob`, `veto_rsi_os`) instead of the finished `long_veto`/`short_veto`.
   The old, stricter rule is why a lab run can miss a long TradingView took.
2. **`execConfSZ`** — "Allow Sniper Zone as entry confirmation", a second accepted entry
   confirmation alongside the FVG. **NOT ported.** `config.exec_conf_sz` exists (default False) and
   the export packs it as `cfg_bits` bit 4096, so `compare_strategy.py` REFUSES an export taken with
   it on rather than diffing against logic this bot lacks. Port = read `BarState.sniper`'s
   0.5-0.618 pocket as an entry edge on any leg with no qualifying FVG.
3. **CONT trades removed** from the Pine — the export used to carry `contL_ok`/`contS_ok`.
4. **`execDeepFib`** (Method 3, added 2026-07-23) — "Entry: deep gap enters on nearest fib (not gap
   edge)". A qualifying FVG whose NEAR edge (long = gap top, short = gap bottom) sits deeper than
   0.618 rests its limit at the nearest fib just SHALLOWER (0.618/0.702/0.786) — the level price
   reaches first — instead of chasing a gap edge price may never tap. **PORTED here**: `config.exec_deep_fib`
   (default **True** as of 2026-07-23 — see the prime-combo defaults note below), `execution._deep_fib_edge()`
   + the override in `_entry_edges()`, the export packs it as `cfg_bits` bit 8192, and `compare_strategy.py`
   reads it (no refusal — it is fully ported). ONLY the near edge's position decides it; what the gap body
   crosses is irrelevant (an earlier "body contains a level" gate was WRONG and dropped exactly the deep
   multi-level gaps this targets).

**Prime-combo defaults (2026-07-23).** Aaron's TradingView-tested "prime" settings are now the shipped
defaults in BOTH Pine files and `config.py`, in lockstep so `compare_strategy.py` parity holds:
`exec_arm_sweep` False→**True**, `exec_arm_div` True→**False** (arm on liquidity sweeps, not divergence),
`exec_fvg_deep_only` False→**True**, `exec_deep_fib` (new) → **True**. `exec_req_fvg` stays True. Combo
result on Aaron's Strategy Tester: ≈+237% / PF 6.2 / 85% win / 13% max DD over ~2yr gold at 84 trades.
This SUPERSEDES the old divergence-armed default — the "2-year run" analysis further down was measured
under that old default and predates Method 3 + deep-only; keep it as the historical baseline only.

**Slippage pinned to 0 in the Pine (2026-07-23).** Both `mpc_strategy.pine` and `mpc_strategy_export.pine`
now declare `slippage = 0` in the `strategy()` call, so the TradingView Properties tab defaults to zero
instead of Aaron's old 25-tick setting. Reason: for HONEST parity the Pine's `fill_model="bar"` (zero
costs) must line up with a TV run that also charges nothing, so `compare_strategy.py` and a hand
trade-diff compare like-for-like. Real costs belong in the LAB's `fill_model="tick"` run (real bid/ask +
spread + slippage + commission + swap), not smeared as a flat 25-tick charge on every TV fill. The
breakeven buffer (`execBeBufTk`, default 30) is a STRATEGY input and is unchanged — it is signal logic,
not a cost. So the old note that TV's number is "slightly PESSIMISTIC because TV charges 25 ticks" no
longer applies to a fresh export: at slippage 0 the TV bar-mode number and our bar-mode number are the
honest apples-to-apples pair; the tick-mode lab run is the real tradeable number.

**When the Pine changes:** brother re-pastes `mpc_strategy.pine` → regenerate `mpc_strategy_export.pine`
(re-copy + re-append the parity block) → re-export → re-run until exit 0. A new trade-affecting input =
a new `config.py` field + a new `cfg_*` plot + a new `compare_strategy._TOGGLE_COLS` entry.

**One-shot sync check:** `backtest/tools/verify_parity.py <export.csv> [more.csv ...]` runs EVERY parity
check (all nine engines + this strategy) whose columns are present in the CSV(s) and prints one
GREEN/RED/SKIP table with auto-detected cold-start warmup. It is the "is everything in sync?" command
to run after any re-paste; it reports drift, it does not fix it (a real logic change is still a hand
port). Engines are the foundation — sync them first (`/audit-engines`), then this strategy.

## LOGIC parity vs RESULT parity — two different tools, two different questions

`compare_strategy.py` answers "is our CODE the Pine's code?" — it replays TradingView's OWN bars and
diffs the per-bar `px_*` decision stream, so the data feed is out of the equation. That is the gate.

`tools/compare_trades.py` answers a different question: "why does a LAB RUN's finished trade list
differ from what I got in the TradingView Strategy Tester?" It pairs the two trade lists by entry TIME
(not price — different brokers legitimately differ by cents on the same bar) and reports matched /
TV-only / ours-only. **It is a diagnosis tool, not a parity gate** — a diff here is usually the DATA
FEED, not the code (proven 2026-07-22: run `f455b21faabe` came in ~110% vs TradingView's 142%; the whole
gap was two longs Vantage's wick swept a level our PU-Prime feed's wick fell ~10 cents short of, so the
sweep never armed. `compare_strategy.py` was green on TradingView's bars, i.e. our code took both those
longs on Vantage data — the lab missed them purely on the feed). Two counting conventions also confuse
the comparison and are NOT bugs: TradingView counts each TP rung as its own "trade" (41 positions × 3
rungs = 123) and its max-DD % is vs peak equity where ours is vs starting capital. Usage:
`compare_trades.py <tv_trades.csv> <run_id>` — `--tz` defaults to `Etc/GMT+4` (the Vantage XAUUSD chart
is a FIXED UTC-4, no US DST); it prints a hint if the median pairing offset says otherwise.

## The 2026-07-16 year run — what the numbers actually say

365d, 15m, XAUUSD.s, `exec_risk_pct=10`, $10k start. Both fill models, same 22 trades:

| | bar (Pine guess, no costs) | tick (real bid/ask + costs) |
|---|---|---|
| net | $11,525.41 (115.25%) | **$11,374.78 (113.75%)** |
| PF | 4.426 | 4.228 |
| win% | 72.73% | 72.73% |

Real fills cost 1.3%; **0 bars fell back to the guess**, so every fill is a real tick. TradingView's
110.19% on the same setup is slightly PESSIMISTIC, not optimistic — TV charges a flat 25 ticks of
slippage on every fill, and the real broker is better than that (the entry is a resting limit, which
never slips; only stops pay).

**TradingView's 66 trades = our 22.** Each `strategy.exit` leg (TP1/TP2/runner) is a separate closed
trade in TV's stats: 22 × 3 = 66 exactly, and the filtered 16 winners × 3 = 48 exactly. Net / return /
drawdown mean the same thing in both; **profit factor and average-trade do NOT** — splitting one
winner into three legs changes the ratio (TV 4.155 vs the real 4.426). Don't compare those two.

**The distribution is the real story** (`|R| < 0.25` = scratch):

| outcome | n | $ pnl | % of net | avg R |
|---|---|---|---|---|
| reached the runner (TP1+TP2 banked) | 8 | +12,510 | **110%** | 1.19 |
| TP1 only, rest stopped at BE | 8 | +2,389 | 21% | 0.19 |
| never reached TP1 | 6 | −3,524 | −31% | −0.42 |

The 72.73% win rate is arithmetically right and analytically misleading: **10 of the 22 trades are
near-scratch** (together +$749), six of the eight "TP1 only" winners made under $300, only 2 trades
lost a full R (the stop→BE rule converts most losses to scratches), and the **top 3 trades are 57% of
net**. The edge is the runner. Treat the win rate as a byproduct of the BE stop, not as the edge.

### The 2-year run (2024-07-16 → 2026-07-16, tick mode) — the shape HOLDS

> **⚠️ Pre-combo baseline (superseded 2026-07-23).** Everything in this subsection was measured under
> the OLD default (divergence-armed, gap-edge entry, no deep-only). The shipped default is now the
> deep-entry combo (sweep-arm + deep-only + deep-fib → ≈+237%/PF6.2/85%/13%DD at 84 trades). The
> numbers below still stand as the divergence-only baseline, but they are no longer the default's
> results. Read them as history, not as what the bot does out of the box today.

40 trades, net **$21,536.60** on $10k. The distribution is the same story with a bigger sample:

| outcome | n | $ pnl | % of net | avg R |
|---|---|---|---|---|
| reached the runner | 15 | +26,565 | **123%** | 1.13 |
| TP1 only | 12 | +4,032 | 19% | 0.16 |
| never reached TP1 | 13 | −9,060 | −42% | −0.45 |

What the second year of data changed, and what it didn't:
- **Win rate fell 72.73% → 67.5%** (27/40) and losers went 6→13 — the 1-year window was the kinder half.
- **Concentration improved**: top 3 = 45% of net (was 57%) — still above the framework's <60% floor
  but no longer resting on three trades.
- **Still 17 of 40 near-scratch**, and still exactly the runner carrying everything (123% of net).
- **Full-R losses scale with the sample** (2 → 5), i.e. the stop→BE rule keeps converting most losses
  to scratches; that behaviour is stable, not a one-year artifact.
- **The ~83% short skew (33 shorts / 7 longs) is EXPLAINED as of 2026-07-16 — it is not a bug.**
  The port is parity-green, so the Pine skews identically. Measured per-side over the same 2yr
  window (48,246 bars, gold +75%):
  - **Root cause — the arm-source filter.** The sequence arms on a sweep OR a divergence, but
    `exec_arm_sweep` defaults **False**: only DIVERGENCE-armed setups may enter. Bearish
    divergences outnumber bullish **142:73 (66%)** in an uptrend — price keeps making higher
    highs on weakening RSI, while bullish divergences need lower lows a bull market rarely gives.
    The skew is inherited almost entirely from that 2:1. Sweeps, by contrast, are near-symmetric
    (1,505 S / 1,308 L), and the raw structure is *dead even* — external SOS is **125/125**. So
    nothing upstream of the arm filter is asymmetric.
  - **Amplified by fib geometry.** Episodes reaching Stage 4 READY: **37 L vs 67 S**. After a bull
    SOS a long waits for a retrace to 0.5/0.618 — in a strong uptrend the pullback is too shallow
    to reach it (51 long episodes die at peak stage 2, vs 25 short), while the deep counter-trend
    rallies a short setup needs arrive reliably.
  - **The default filter is the profitable subset, and it is a strict SUBSET.** Every
    divergence-armed trade is also sweep-armed, so `both` is bit-identical to `sweep only`.
    Arm source → trades / short% / net / PF (bar mode, 2yr, no costs):
    divergence-only (OLD default) 40 / 82.5% / +190% / **3.27** · sweep-only (= both) 79 / 69.6% /
    +144% / **1.87**. Enabling sweeps adds 39 trades that lose money net and drags PF down ~43%.
  - **Longs are not broken, just rare** — 7 trades, **86% win**, profitable (+21% of capital).
    Nothing is blocking longs incorrectly; there simply are few bullish divergences up here.
  - **What to actually worry about is concentration, not the count.** Shorts carry **89% of net**.
    Every HTF bias filter is `Ignore` (`exec_htf_weekly`/`exec_htf_daily`), so this is an
    unfiltered counter-trend fade that shorted a +75% bull market and won at 70%. That is the
    claim needing a second regime to confirm — the direction split itself is now accounted for.

Open threads (Aaron is on the edge work as of 2026-07-16): ~~whether stop→BE on TP1 caps runners~~
(**ANSWERED 2026-07-26, Run 3 in `mpc_sos_fade_optimization.md`: it does not — it pays for itself**); and
why 15m is reportedly the only winning timeframe (a real edge usually survives on neighbouring
timeframes — if 5m and 30m lose, suspect luck). 40 trades is still a thin sample; treat the KPIs as
directional, not settled. (Superseded note: an earlier version warned "do not flip `exec_arm_sweep` — it
breaks parity". That was wrong on the mechanism — parity is driven by the export's `cfg_bits`, not the
default — and moot now: the default flipped to sweep-arm on 2026-07-23, in lockstep across both Pine
files and `config.py`, so parity holds. Flip toggles freely per run; just keep the two Pine files and
`config.py` defaults identical when you change a DEFAULT.)

## Tests

```
command-center/backend/.venv/bin/python -m pytest strategies/python/mpc_sos_fade/tests/ -q
```
Offline, no network, no TradingView. `test_sequence.py` (state machine on the real engine stack +
hand-checked Pine rules), `test_execution.py` (fills / ladder / stop-out / sizing, hand-checked),
`test_strategy_driver.py` (end-to-end), `test_compare_strategy.py` (the parity tool round-trips its
own output). These prove the plumbing; the Pine diff is the live gate.

## The B-LEG bot reuses this one — three parity-safe additions (2026-07-24, do NOT revert)

`strategies/python/mpc_bleg/` (the standalone B-LEG bot) reuses this package's engine + A+ sequence +
fill machinery, so it needed three ADDITIVE, decision-neutral changes here. All three are safe (this
bot's offline tests stay green) and must not be reverted:

1. **`signals.py`** — `Signals` gained `bull_bos_high/low` + `bear_bos_high/low` (the break-leg
   endpoints the B-LEG band-freeze reads). Nothing in the A+ path reads them.
2. **`sequence.py`** — `SeqState` gained `bleg_arm_l`/`bleg_arm_s`, computed at the EXACT Pine point:
   after the opposite-SOS death, BEFORE the continuation-BOS death clears `l_sos_bar` and before the
   half/618 latch update. The B leg arms off state that `update()` has already cleared by the time it
   returns, so the sequence has to expose it here.
3. **`execution.py`** — the A+ arm decision was extracted from `_place_entries` into `_armed()` (a pure
   refactor) so the B-LEG subclass can reuse the "A+ has priority" gate. No behaviour change.

Full context in `strategies/python/mpc_bleg/CLAUDE.md`.

## Do / Never

- **Do** port any change to `mpc_strategy.pine`'s A+ block or execution layer here line-for-line, then
  re-run `compare_strategy.py`. Keep the Pine the source of truth — never edit it to match the Python.
- **Do** read engine OUTPUT only (`backtest.replay` `BarState`) — never reach into an engine's internals.
- **Never** build a second copy of any engine here — this consumes the canonical `engines/`.
- **Never** trust a backtest number until `compare_strategy.py` is exit 0 on a fresh export.
- **Never** commit a real TradingView export or backtest cache into git.
- **Never** revert the three B-LEG parity-safe additions above without also updating `mpc_bleg/`.

## References

- Spec: `docs/MPC_SOS_FADE_SPEC.md`; build plan + order: `docs/MPC_SOS_FADE_BUILD_PLAN.md`.
- Pine source of truth: `indicators/mpc_strategy.pine` (A+ block ~3708-3972, execution ~4112-4735).
- Upstream runner: `backtest/CLAUDE.md`; engines: `engines/*/CLAUDE.md`.
