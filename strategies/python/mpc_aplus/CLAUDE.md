# CLAUDE.md — strategies/python/mpc_aplus/ (the MPC A+ bot)

**Purpose:** The MPC A+ reversal strategy in Python — a line-for-line port of the A+ block +
execution layer in `indicators/mpc_strategy.pine` (Aaron's brother's "MPC-JARVIS" script). It reads
the canonical engine stack's per-bar output and turns the A+ sequence into trades.
**Scope:** This strategy only — its state machine, order logic, config, and parity harness. It does
NOT own the engines (`engines/`), the replay runner (`backtest/`), or the lab (`command-center/`).
**Status:** Built + unit-tested + **logic-parity GREEN (exit 0) 2026-07-16** on a full-history
`VANTAGE_XAUUSD, 5m` export (20,076 bars, `compare_strategy.py` with no warmup — the export starts at
bar 0). Bar-for-bar identical decision stream vs `mpc_strategy.pine`. Runs real-tick fills + costs
(`fill_model="tick"`), and is registered in the command-center lab as `runner="python"` (see
`LAB_STRATEGY` in `__init__.py`) — risk % is editable in the Run modal. 102 offline tests green.
**Open question — sample size, NOT correctness:** the validated 365d 15m run is only 22 trades (2yr:
40), and the runners alone make >100% of the net in both windows. Read `## The 2026-07-16 year run`
below before trusting any tuning done against it.
**Last reviewed:** 2026-07-16

---

## What it is (one paragraph)

A counter-trend reversal that fades exhaustion at HTF liquidity. Three-stage A+ sequence: **Arm**
(RSI divergence by default, or a liquidity sweep) → **SOS** (a same-side external structure break in
the trade direction, inside a staleness window) → **Zone+FVG** (price retraces into the 0.5–0.886 fib
band and a live FVG overlaps it). Entry is a resting limit at the FVG's near edge, clamped into the
band; stop = fib 1.0 (leg origin) + buffer; exit = the fib TP ladder (30/40/runner) with stop→BE on
TP1, stop→TP1 on TP2, and a ratcheting trail on the runner. Full rules: `docs/MPC_APLUS_SPEC.md`.

## The five modules (the data flow)

```
BarState  --SignalAdapter-->  Signals  --AplusSequence-->  SeqState  --Execution-->  Decision
(backtest.replay)             (Pine-named inputs)          (A+ stages)               (orders + fills + R)
```

- **`config.py`** — `AplusConfig`: every trade-affecting Pine input toggle, same name + default
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
- **`sequence.py`** — `AplusSequence`: the Stage 1→4 state machine, retro-link (a late-confirming
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
- **`strategy.py`** — `MpcAplusStrategy`: the driver. `run(df, warmup=…)` replays a canonical frame
  end-to-end; `step(bar_state)` does one bar. Collects `.decisions` (the per-bar stream) and
  `.execution.trades`.

## Deliberate deviations from the Pine (per the framework)

All OFF for the parity check (to match the Pine); each is a real-run choice:
1. **Flat-by-close** — force-flat + no new entries N minutes before the daily close (`flat_by_close`).
   **Default False, and measured 2026-07-16: leave it that way.** A/B over 6.5 months: OFF $39,454 /
   PF 1.444 vs ON $19,813 / PF 1.253 on the same 32 trades. Only 4 trades ever held overnight, they
   were all winners, and they made 70% of the profit; total swap for the period was −$36.80. Flatting
   early buys a smaller drawdown for half the profit. (This param was DEAD CODE until 2026-07-16 —
   `_in_flat_window` read only `sig.ny_hour`, so "minutes left" was always a multiple of 60 and never
   hit the ≤15 window. Any A/B run before that date compared a flag against itself.)
2. **Sizing** — the parity check uses the manual %-risk (matches the Pine's fixed-% sizing); real runs
   swap in the dynamic sizing engine under a ruleset.
3. **Fill model** — parity REQUIRES `fill_model="bar"` (the Pine's own intrabar guess, zero costs).
   Real runs set `fill_model="tick"` + `account_profile` + `symbol` for real bid/ask fills and costs.
   See `backtest/CLAUDE.md` A2 — tick mode disagreeing with the Pine is correct, not drift.

## Engine-construction pins (`MpcAplusStrategy.engine_config`)

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
command-center/backend/.venv/bin/python strategies/python/mpc_aplus/tools/compare_strategy.py <export.csv> --warmup N
```

**When the Pine changes:** brother re-pastes `mpc_strategy.pine` → regenerate `mpc_strategy_export.pine`
(re-copy + re-append the parity block) → re-export → re-run until exit 0. A new trade-affecting input =
a new `config.py` field + a new `cfg_*` plot + a new `compare_strategy._TOGGLE_COLS` entry.

**One-shot sync check:** `backtest/tools/verify_parity.py <export.csv> [more.csv ...]` runs EVERY parity
check (all nine engines + this strategy) whose columns are present in the CSV(s) and prints one
GREEN/RED/SKIP table with auto-detected cold-start warmup. It is the "is everything in sync?" command
to run after any re-paste; it reports drift, it does not fix it (a real logic change is still a hand
port). Engines are the foundation — sync them first (`/audit-engines`), then this strategy.

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
- **NEW, unexplained: the strategy is ~83% short** (33 shorts / 7 longs), and the single worst trade
  is a long (−$2,929, −1.01R). Over a window where gold trended up. A counter-trend fade shorting a
  bull market and winning deserves a look before it is trusted — either the arm conditions are
  asymmetric, or two years of gold is one regime wearing a disguise.

Open threads (Aaron is on the edge work as of 2026-07-16): whether stop→BE on TP1 caps runners; the
direction skew above; and why 15m is reportedly the only winning timeframe (a real edge usually
survives on neighbouring timeframes — if 5m and 30m lose, suspect luck). 40 trades is still a thin
sample; treat the KPIs as directional, not settled.

## Tests

```
command-center/backend/.venv/bin/python -m pytest strategies/python/mpc_aplus/tests/ -q
```
Offline, no network, no TradingView. `test_sequence.py` (state machine on the real engine stack +
hand-checked Pine rules), `test_execution.py` (fills / ladder / stop-out / sizing, hand-checked),
`test_strategy_driver.py` (end-to-end), `test_compare_strategy.py` (the parity tool round-trips its
own output). These prove the plumbing; the Pine diff is the live gate.

## Do / Never

- **Do** port any change to `mpc_strategy.pine`'s A+ block or execution layer here line-for-line, then
  re-run `compare_strategy.py`. Keep the Pine the source of truth — never edit it to match the Python.
- **Do** read engine OUTPUT only (`backtest.replay` `BarState`) — never reach into an engine's internals.
- **Never** build a second copy of any engine here — this consumes the canonical `engines/`.
- **Never** trust a backtest number until `compare_strategy.py` is exit 0 on a fresh export.
- **Never** commit a real TradingView export or backtest cache into git.

## References

- Spec: `docs/MPC_APLUS_SPEC.md`; build plan + order: `docs/MPC_APLUS_BUILD_PLAN.md`.
- Pine source of truth: `indicators/mpc_strategy.pine` (A+ block ~3708-3972, execution ~4112-4735).
- Upstream runner: `backtest/CLAUDE.md`; engines: `engines/*/CLAUDE.md`.
