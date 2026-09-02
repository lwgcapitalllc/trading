"""MPC EXTREME LEG — the run INTO the shift of structure, not the fade after it.

Ported from `indicators/strategies/mpc_extreme_leg_strategy.pine`. The A+ bot waits for structure
to shift and then fades the retracement; this takes the move that CREATES the shift — from the
extreme up to the swing whose break IS the shift. Stop beyond the extreme, exit part of the way to
the swing, one position at a time.

    ExtremeLegConfig       — every Pine input, and nothing that is not one
    HtfStructure           — the 15-minute half, aggregated from the chart's own bars
    LegState               — what the Pine computed on a bar, whether or not it traded
    ExtremeLegExecution    — one slot, a frozen bracket, and the costs it paid
    MpcExtremeLegStrategy  — the driver

⚠ **NO PARITY GATE HAS RUN AGAINST THIS YET.** Stage 4 of `docs/STRATEGY_WORKFLOW.md` — a bar-by-
bar CSV off the export twin — is the one step no machine here can take, and until
`tools/compare_extreme_leg.py` exits 0 on one, every number this package produces is a lab finding
and not a measurement. Two known places the two sides may disagree are written down in
`strategy.py::_update_sweeps`; neither has been settled, and neither is guessed at in code.
"""

from __future__ import annotations

import sys
from pathlib import Path

_PYPKGS = Path(__file__).resolve().parents[1]
if str(_PYPKGS) not in sys.path:
    sys.path.insert(0, str(_PYPKGS))

from .config import ExtremeLegConfig
from .execution import Blocked, ExtremeLegExecution
from .htf import HtfStructure
from .strategy import LegState, MpcExtremeLegStrategy

__all__ = [
    "Blocked",
    "ExtremeLegConfig",
    "ExtremeLegExecution",
    "HtfStructure",
    "LAB_STRATEGY",
    "LegState",
    "MpcExtremeLegStrategy",
]

# ── Lab registration (runner="python") ───────────────────────────────────────────
# The scanner imports this package and reads this dict; the lab keys the strategy off the CLASS
# name, so it registers alongside the A+ bot and the B-LEG rather than replacing either.
#
# ⚠ `suggested_instrument` is a suggestion; the 5-minute FRAME is not. See the strategy docstring —
# on a 15-minute frame the trigger and the target become the same series and there is no trade left
# to take. The lab cannot enforce a timeframe, so this is written where somebody reads it.
LAB_STRATEGY = {
    "name": "MPC Extreme Leg",
    "config": ExtremeLegConfig,
    "strategy": MpcExtremeLegStrategy,
    "suggested_instrument": "XAUUSD",
    "category": "reversal",
    "self_sizing": True,
    # Display grouping only — it moves the row and nothing else. It sits under the A+ bot because
    # the suite is carved up by LEG off one structure stream, and this is the leg BEFORE the one
    # the A+ bot trades. A flat alphabetical list hid that relationship entirely.
    "display_under": "mpc_sos_fade",
}
