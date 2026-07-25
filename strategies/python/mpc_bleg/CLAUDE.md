# CLAUDE.md — strategies/python/mpc_bleg/ (the MPC B-LEG bot)

**Purpose:** The B-LEG setup as a standalone Python strategy — a port of
`indicators/mpc_b_leg_strategy.pine` (Aaron's brother's B-LEG fork of MPC-JARVIS). The
B LEG is the SOS whose retrace arrived LATE: an A+ reversal dies at 2/3 on a continuation
BOS before it retraces, the Sniper-Zone band (0.382–0.5) of that break is frozen, and a
resting limit at the 0.5 edge waits for the late return.
**Scope:** This bot only — its tracker, order layer, config, tests. It does NOT own the
engines (`engines/`), the replay runner (`backtest/`), or the A+ machinery it reuses
(`strategies/python/mpc_sos_fade/`).
**Status:** Built + unit-tested (9 tests green). **NO Pine-parity harness yet** — same
position mpc_sos_fade was in before its `compare_strategy.py` landed. Verified so far by the
hand-traced tracker tests + an end-to-end driver run on the synthetic stack. A
`compare_bleg.py` + a `mpc_b_leg_strategy_export.pine` are the follow-up to prove bar-for-bar
parity, once Aaron exports a decision stream (see "Parity — the follow-up" below).
**Last reviewed:** 2026-07-24.

## Why it exists (the split, 2026-07-24)

The B LEG lived inside `mpc_strategy.pine` as a second setup type (`execBLeg`, default OFF).
Turned ON alongside A+ it made significantly more money, and Aaron wants to run it PARALLEL
to the A+ bot on the shared account (the portfolio-stacking seam he built). Decision:
**abstract it into its own strategy that shares the READ layer** (the engine stack + the A+
sequence tracker) and owns its OWN entry/stop/TP — because he intends to tune those
independently, which is the textbook signal to split. The coupling is only on the A+
sequence STATE (a clean read dependency, like depending on an engine), never on the A+ entry
logic. See the Pine file's header for the same reasoning.

## What it reuses vs what is new

It is deliberately ~90% the A+ bot. The fill / TP-ladder / stop-staging / %-risk-sizing /
R-grading machinery is direction- and setup-agnostic, so it is REUSED wholesale:

- **Reused from `mpc_sos_fade`:** `SignalAdapter` → `Signals`, `SosFadeSequence` → `SeqState`
  (the whole A+ engine + sequence), and `Execution` (the broker emulator + exit ladder).
- **New here:**
  - `bleg.py` `BLegTracker` → `BLegState` — the band-freeze / target-track / arm / tap /
    death state machine (Pine 3683-3758). Standalone; reads `Signals` + the `bleg_arm_*`
    flags off `SeqState`.
  - `execution.py` `BLegExecution(Execution)` — a thin subclass: `step(sig, seq, bleg)`
    stashes the `BLegState`; `_place_entries` is the ONLY override — A+ entries disabled,
    B-LEG limit rested at the band's 0.5 edge (SL beyond the leg origin, TP1 = broken swing
    extreme `2·edge−inv`, TP2 = expansion extreme `tgt`, TP3 runner). Everything from
    `_open_position` onward is the parent's.
  - `config.py` `BLegConfig(SosFadeConfig)` — a strict superset, adds only `bleg_max_days`.
  - `strategy.py` `MpcBLegStrategy(MpcSosFadeStrategy)` — inherits `_fill_model` +
    `engine_config` (the SAME `fvg_max_count=7` + `show_internal=False` pins — the B-LEG reads
    the same structure/fib engines), overrides `__init__`/`run`/`step` to splice the tracker.
    `run_dual` is disabled (no 1m secondary).

## The "A+ has priority" gate (kept for baseline; first tuning candidate)

`BLegExecution._place_entries` still computes the A+ `longArmed`/`shortArmed` via the parent's
`_armed()` and stands the B-LEG down on a side where A+ is armed — faithful to the Pine fork.
A+ never PLACES an order (the fork's whole point), it just holds the priority. When stacked
with the real A+ bot on one account the account layer re-does this arbitration, so **dropping
this gate is the first thing to try when tuning** (Aaron's own note in the Pine tooltip). Run
SOLO, the bot fires MORE B-legs than the parent did with `execBLeg` on, because no A+ position
occupies the account — that is correct and expected, not drift.

## Three parity-safe additions to `mpc_sos_fade` (do not revert)

The reuse needed three ADDITIVE, decision-neutral changes there (all re-verified: the A+'s
55 offline tests stay green):

1. **`signals.py`** — `Signals` gained `bull_bos_high/low` + `bear_bos_high/low` (the break-
   leg endpoints the band-freeze reads). Nothing in the A+ path reads them.
2. **`sequence.py`** — `SeqState` gained `bleg_arm_l`/`bleg_arm_s`, computed at the EXACT Pine
   point (Pine 3661): after the opposite-SOS death, BEFORE the continuation-BOS death clears
   `l_sos_bar` and BEFORE the half/618 latch update. This is the whole reason the sequence had
   to expose them — by the time `update()` returns, the state the B-LEG arms off is gone.
3. **`execution.py`** — the A+ arm decision was extracted from `_place_entries` into `_armed()`
   (a pure refactor) so the B-LEG subclass can reuse the priority gate. No behaviour change.

## Sizing — sizes ITSELF

`LAB_STRATEGY` declares `self_sizing: True` (like the A+ bot): `qty = equity·exec_risk_pct /
stop_distance`, so the lab's dynamic sizing engine leaves it alone and `exec_risk_pct` is the
risk knob. Registered as class `MpcBLegStrategy` (distinct from `MpcSosFadeStrategy`), so both
register and run side by side — the parallel-stack use case.

## Parity — the follow-up (not done yet)

There is NO `compare_bleg.py` and no export Pine. To build it, mirror the A+ harness:
`mpc_b_leg_strategy_export.pine` = the strategy + an appended block that plots the per-bar
decision stream (`px_*`) and toggles (`cfg_*`); `tools/compare_bleg.py` reads the toggles,
configures `BLegConfig`, replays, and diffs. Until then, treat backtest numbers as
directional, per Aaron's standing "no trade off an unvalidated port" rule.

## Tests

```
command-center/backend/.venv/bin/python -m pytest strategies/python/mpc_bleg/tests/ -q
```
Offline. Hand-traced `BLegTracker` (band maths, arm, tap, staleness + invalidation death,
deepest-band migration, BLEG_MAX conversion) + end-to-end driver run + longs/shorts-off.

## Do / Never

- **Do** port any change to `mpc_b_leg_strategy.pine`'s B-LEG block or execution here
  line-for-line, and any change to its A+ engine into `mpc_sos_fade` first.
- **Do** keep `BLegConfig` a superset of `SosFadeConfig` — a new A+ toggle should flow in for free.
- **Never** build a second copy of any engine or of the A+ sequence here — reuse `mpc_sos_fade`.
- **Never** trust a backtest number until a `compare_bleg.py` is green on a fresh export.

## References

- Pine source of truth: `indicators/mpc_b_leg_strategy.pine` (B-LEG block ~3683-3758,
  execution ~4429-4506).
- The A+ bot it reuses: `strategies/python/mpc_sos_fade/CLAUDE.md`.
- Upstream runner: `backtest/CLAUDE.md`; engines: `engines/*/CLAUDE.md`.
