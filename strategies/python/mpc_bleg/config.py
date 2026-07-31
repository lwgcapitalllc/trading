"""BLegConfig — the B-LEG bot's config.

It is a strict SUPERSET of `mpc_sos_fade`'s `SosFadeConfig`: the B-LEG runs the SAME
engine stack + A+ SEQUENCE tracker (it arms off the A+ death), and it keeps the "A+ has
priority" gate — so every A+ input still matters (the priority gate reads the A+ arm
sources, edges, veto, HTF filters). Inheriting keeps the two in lockstep: a new A+ toggle
lands here for free. The only NEW field is `bleg_max_days` — how long a frozen B-LEG band
watches for the late retrace before it goes stale (Pine input "B-Leg: days to activate").

The exit ladder / sizing / cost fields (`exec_risk_pct`, `exec_tp1_pct`, `exec_be_buf_tk`,
`exec_trail_step`, `fill_model`, `account_profile`, …) are reused verbatim — the B-LEG
trades through the SAME execution machinery, only the ENTRY (band edge, custom SL/TP) and
the arm differ. See `bleg.py` / `execution.py`.
"""

from __future__ import annotations

import sys
from dataclasses import dataclass
from pathlib import Path

# strategies/python on path so `mpc_sos_fade` imports by bare name (same shim the tests use).
_PYPKGS = Path(__file__).resolve().parents[1]
if str(_PYPKGS) not in sys.path:
    sys.path.insert(0, str(_PYPKGS))

from mpc_sos_fade.config import SosFadeConfig  # noqa: E402


@dataclass(frozen=True)
class BLegConfig(SosFadeConfig):
    # ── Inherited toggle, re-defaulted to this fork's Pine value ───────────────────
    exec_bleg: bool = True        # "Trade B-Leg setups" — THIS fork's core setup, so ON here
    #   `mpc_b_leg_strategy.pine` ships execBLeg = true (the A+ file ships it false). Turn OFF
    #   only to prove the bot trades nothing without it. `exec_aplus` is inherited and still
    #   matters: A+ never PLACES an order here, but it holds the priority gate — set it False
    #   to drop that gate and read the B leg completely on its own.
    exec_sl_level: str = "1.0"    # "SL fib level" — pinned, NOT inherited
    #   The parent defaulted this "1.0" → "0.886" on 2026-07-27 to match the A+ Pine. This fork's
    #   Pine (`mpc_b_leg_strategy.pine`) still ships "1.0", and toggle-default parity with its OWN
    #   Pine is the contract, so the value is pinned here rather than inherited. It is also unused
    #   on this path — a B leg's stop is the frozen band's origin, never the fib anchor — so the
    #   pin costs nothing and only stops a silent drift between this config and its export.
    exec_min_stop_mode: str = "Off"   # "Minimum stop distance" — pinned OFF, and INERT here
    #   Inherited from the parent, which added it 2026-07-30 as the guard for a stop that collapses
    #   onto the entry. It does NOT apply on this path: the floor is enforced in the parent's
    #   `_place_entries`, which `BLegExecution` overrides, and `mpc_b_leg_strategy.pine` has no such
    #   input to be parity-checked against. Pinned to the inert value so a future parent default
    #   change cannot silently claim a guard this fork does not run. The hazard it protects against
    #   is also structurally absent here — a B leg's stop is the band ORIGIN, always a full band
    #   away from the 0.5 entry edge, never a fib that can land on top of it.
    #   Porting it means adding the input to that Pine, the floor check to `_place_entries`, and a
    #   `cfg_min_stop` column to the B-LEG export — in one commit, then re-run `compare_bleg.py`.

    #   `exec_runner_trail` was PINNED to "Structure (swing)" here from 2026-07-28 until later the
    #   same day, because the parent had moved to "Structure + % ratchet" while this fork's Pine
    #   still shipped the two-option dropdown — inheriting would have moved every B-LEG runner exit
    #   against a Pine that stood still, and `compare_bleg.py` would have reported the drift as a
    #   bug. `mpc_b_leg_strategy.pine` now carries the ratchet (same `f_swingRatchet`, same default),
    #   so the pin is GONE and `exec_runner_trail` / `exec_trail_pct` are inherited again. The
    #   43% → 53% run-capture number behind that default was measured on the parent's A+ trades,
    #   never on B legs — it is inherited for ONE-LADDER consistency, not as a proven B-LEG result.
    #   Sweep it here before treating it as tuned.

    # ── B-LEG-only input (Pine bLegMaxDays, group "Strategy Execution") ─────────────
    bleg_max_days: float = 1.25   # days a frozen band watches before it goes stale (1-3)
    #   Converted to a BAR count (day ÷ chart timeframe) so weekends and the daily close
    #   don't burn the clock. Default 1.25 = the original 120 bars on 15m. See bleg.py.
