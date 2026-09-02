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
    # 🔴 **NO `display_under` — THIS ROW IS TOP LEVEL, AND THAT IS A DECISION (Aaron, 2026-09-02:
    # "move it to root").** It was listed under the A+ bot until then, on the reasoning that the
    # suite is carved up by LEG off one structure stream and this is the leg BEFORE the one A+
    # trades. That reasoning is still true and it is still the wrong thing to draw as an indent:
    # **nesting reads as "child of", and this bot is a SIBLING, not a descendant.** It has its own
    # Pine source, its own parity gate, its own config, and it runs standalone, in any stack, on
    # any instrument. Measured over 6.6 years it holds ZERO same-side overlap with A+, correlates
    # +0.035 month to month, and on one shared account the two refuse each other essentially never.
    #
    # ⚠ **The indent was carrying two different relationships at one level, which is what made it
    # misread.** `loss_recovery` sits under A+ too and genuinely CANNOT run without it — it arms
    # off that bot's closed losses and declares `requires_source`. A row that cannot exist alone
    # and a row that competes for the account as an equal were drawn identically.
    #
    # ⚠ **Do not re-add the field without saying why here.** Its failure mode is silent in both
    # directions: a dropped declaration and a typo'd parent both render at the top level, so
    # nothing on screen would show the decision had been reversed. `tests/` pins it.
}
