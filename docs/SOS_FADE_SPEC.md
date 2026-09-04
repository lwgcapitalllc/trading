# SOS Fade — Strategy Spec (Step S)

**Source of truth:** `strategies/tradingview/sos_fade_strategy.pine` (the execution layer, lines ~3640–4735).
**Purpose:** the exact, machine-followable rules the Python port reproduces. The parity check
(`compare_strategy.py`) proves the port matches these rules on real data.
**Status:** APPROVED 2026-07-15 — build started (A0 data layer first).

The strategy trades **only** the A+ reversal sequence. It is symbol- and timeframe-agnostic:
everything below is generic logic; instrument facts and account rules are injected by the layers
below it. (`CONT` continuation setups are tracked for the table but **not traded** — out of scope.)

**Toggle parity (hard requirement):** the Python bot declares **every** input toggle the Pine has —
same name, same default (arm-source, require-FVG, FVG-deep-only, veto, HTF filters, longs/shorts,
SL level + buffer, TP1/TP2 %, trail step, risk %, session cutoffs, …). The regression harness drives
these from the export so any config you and your brother pick in TradingView reproduces exactly. See
the regression harness in the build plan.

---

## Inputs it reads from the engines (all already built + Pine-parity-validated)

- **market_structure** — external `bull_sos` / `bear_sos` / `bull_bos` / `bear_bos`, and the break
  legs (`bull_bos_high/low`, `bear_bos_high/low`).
- **fibonacci (Structure fib)** — `fibo_dir`, the level prices `fiboP1..P10`, and the latches
  `fiboHalfReached` (0.5 tapped), `fibo618EverReached`, `fibo7Touched` (TP3 / 0.0 hit).
- **fair_value_gaps** — active gaps (top, bottom, is_bullish).
- **rsi_divergence** — new bull/bear divergence bars + the live veto flags (extreme / opposing div).
- **liquidity** — the sweep source + bar (`recentSSL` / `recentBSL` and their bars).
- **macro fib (fibonacci)** — the HTF POI zones (used as a confluence flag only). On at ≤5m.

---

## The A+ sequence (per side; long shown, short is the mirror)

A **sequence**, not a checklist — each stage counts only if the previous one is done. State is held
per side (`aplusL_*` / `aplusS_*`).

### Stage 1 — ARM (`aplusL_sweepBar` set)
Edge-triggered on the exact bar a **new** trigger fires:
- **Sweep** — a new liquidity sweep (`recentSSL` changed bar), only when nothing is already tracking
  this side (`sweepBar` and `sosBar` both empty). A "Day Low" sweep older than 24h is ignored.
- **Divergence** — a new confirmed bull RSI divergence. A divergence **may take over** a slot a
  sweep is merely holding at Stage 1 (refreshing the arm clock), but may **not** disturb a locked
  Stage-2 setup.
- Records `armTime = bar time`. The staleness window is measured in **time** (`aplusWindow`
  minutes), not bars.
- Session-gap bars (first bar after a market close — a time jump > 2× the normal spacing) do **not**
  arm and do **not** expire arms.

### Stage 2 — SOS (`aplusL_sosBar` set)
An external **bull SOS** (CHoCH in the trade direction) that fires while a Stage-1 arm is live and
within the window (`time − armTime ≤ window`) advances to Stage 2.
- **Retro-link:** a divergence confirms `pivot_len` bars late, so on a fast V-reversal the SOS
  already fired. If the last bull SOS landed **at or after** the divergence's pivot bar and is still
  inside the window, adopt it as the Stage-2 SOS. (Without this a div-armed setup never trades.)
- **Stale-arm clear:** if the window passes with no SOS, clear the arm (not on a session-gap bar).

### Stage 3 — ENTRY ZONE (progress on the SOS leg's fib)
Latched while the SOS is live (survives a fib redraw at the session gap):
- `aplusL_half` = the fib **0.5** was tapped inbound → tier **EARLY** (stage 3).
- `aplusL_618`  = the fib **0.618** was reached → tier **READY** (stage 4, E1–E3 zone live).
- Stage value: SOS present → `618 ? 4 : half ? 3 : 2`; else arm present → `1`; else `0`.

### Sequence death (clears all state on that side)
Any one of:
- **Opposite SOS** — a bear SOS kills the long side (the trend it faded just reversed).
- **TP3 reached** — `fibo7Touched` while `fibo_dir == 1` (cycle complete).
- **Leg invalidated** — `fibo_dir` flipped to −1, or close fell below the fib 1.0 (`fiboP10`).
- **Continuation BOS** — a bull BOS that is *not* also this bar's SOS (structure broke on in the
  same direction without ever giving the fib entry). Excludes the SOS's own bar.
- Not applied on a session-gap bar.

---

## Entry (Stage-4 READY → resting limit)

A trade arms when **all** hold (`longArmed`):
`trade-longs enabled` · `arm source enabled AND live at the SOS` · not late-day · not HTF-blocked ·
SOS present · `fibo_dir == 1` · an entry edge exists · not vetoed · **flat** · this SOS leg not
already traded.

- **Entry edge** — the near edge of a **live FVG that overlaps the 0.5–0.886 band**, clamped into
  the band (never buy above 0.5). If several qualify, the one price reaches first (highest edge for
  longs). With "Require FVG" off, the edge falls back to the 0.618 fib. Order is a **resting limit**
  at that edge — a wick fills it intrabar even though the FVG box is consumed on the tap.
- **Deep vs shallow:** deep = edge at/below 0.618. Deep → TP1 = 0.5, TP2 = 0.382. Shallow (rests on
  0.5) → TP1 = 0.382, TP2 = 0.0 (swing extreme). TP3 = the runner (no fixed target).
- **Stop** = the chosen SL fib level (default 1.0 = leg origin) ∓ buffer. If the level lands at/inside
  the entry, SL distance ≤ 0 and the setup simply does not fire.
- **Size** — see **Sizing** below.
- **One trade per SOS leg** — once the leg fills, that `sosBar` is marked traded and won't re-fire.

---

## Filters (whether to enter)

- **Direction toggles** — trade longs / shorts independently.
- **Arm-source toggle** — a setup trades only if a source you enabled (sweep and/or divergence) was
  live at the SOS. Default: divergence-only.
- **Veto** — suppress a long on live bearish divergence or extreme-overbought RSI (mirror for
  shorts). On by default.
- **Entry cutoff (configurable)** — no new entries in the last **N minutes** before the instrument's
  daily close. Default **60 min** (gold close = 17:00 NY → cutoff 16:00 NY / 3 PM Central). The close
  time is a per-instrument Layer-B fact.
- **HTF exhaustion (optional, off)** — block a reversal that fights a *fresh* HTF breakout close;
  allow one that fades an exhaustion sweep.
- **HTF bias (optional, off)** — Weekly/Daily bias gates (agree / not-oppose / oppose-reversal).

---

## Trade management (after entry)

- **Scale-out** — TP1 30%, TP2 40%, runner 30% (defaults).
- **Stop staging** — TP1 touched → stop to breakeven + buffer; TP2 touched → stop to the TP1 price;
  runner ratchets: once price runs one full trail step past TP2, the stop climbs one step per further
  step of favorable move.
- **Opposite-SOS close (optional, off)** — force-close on an opposite SOS instead of riding to stop.

---

## Sizing (ruleset governs, else you set it)

- **Ruleset attached** (loss limits defined) → the **dynamic sizing engine** sizes each trade from
  the room left to the drawdown floor (bullet = max the rules allow; consistent = room ÷ 7), per the
  framework. No manual risk knob applies.
- **No ruleset** (raw exploratory backtest) → a **manual risk % override** you set. Size =
  `equity × risk% / stopDistance`. This is the "sweep risk levels to see the P&L at each" mode —
  run the same test at 0.5% / 1% / 2% / 5% and compare. Default 1%.
- The **parity check** uses the manual % (it matches the Pine's fixed-% sizing).

The stop always comes from the strategy (the fib SL level); sizing only ever sizes *around* it.

## Deviations from the Pine (deliberate, per framework)

1. **Flat-by-close (configurable)** — force-close all open trades **N minutes** before the
   instrument's daily close. Default **15 min** (gold → 16:45 NY / 3:45 PM Central). Stops the gold
   close-gap + slippage from giving back profit over the 1-hour break. The Pine holds the runner
   across the break; the intraday rule wins. *(Backtest numbers will differ from the raw Pine —
   expected. The parity check runs this OFF to match the Pine, then it's ON for real runs.)*
2. **Sizing** — see the Sizing section above (manual % with no ruleset; dynamic engine under one).

Everything else reproduces the Pine exactly. The parity check enforces that.

---

## Open question for sign-off

- **Parity target timeframe.** The Pine was validated/backtested on XAUUSD 5m. The parity export
  should be 5m (so the Macro-fib POI is exercised). Confirm 5m for the parity check, with the real
  runs then free to use any timeframe. OK?
