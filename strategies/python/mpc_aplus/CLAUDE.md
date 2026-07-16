# CLAUDE.md — strategies/python/mpc_aplus/ (the MPC A+ bot)

**Purpose:** The MPC A+ reversal strategy in Python — a line-for-line port of the A+ block +
execution layer in `indicators/mpc_strategy.pine` (Aaron's brother's "MPC-JARVIS" script). It reads
the canonical engine stack's per-bar output and turns the A+ sequence into trades.
**Scope:** This strategy only — its state machine, order logic, config, and parity harness. It does
NOT own the engines (`engines/`), the replay runner (`backtest/`), or the lab (`command-center/`).
**Status:** Built + unit-tested 2026-07-15 (18 offline tests). Logic-parity NOT yet run against a
real TradingView export — that is the gate before any result is trusted.
**Last reviewed:** 2026-07-15

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

Both OFF for the parity check (to match the Pine), ON for real runs:
1. **Flat-by-close** — force-flat + no new entries N minutes before the daily close (`flat_by_close`).
2. **Sizing** — the parity check uses the manual %-risk (matches the Pine's fixed-% sizing); real runs
   swap in the dynamic sizing engine under a ruleset.

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
