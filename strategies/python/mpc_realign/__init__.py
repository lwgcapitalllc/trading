"""mpc_realign — MPC REALIGN: internal-structure realignment after an external false break.

Spec: docs/MPC_REALIGN_SPEC.md
Full rules: `CLAUDE.md` in this package.

    RealignConfig       — SosFadeConfig superset + the realign levers
    HtfStructure        — the external frame, aggregated from the chart frame
    RealignTracker      — arms on the false break, walks the realignment
    RealignExecution    — the MARKET entry, sizing, the structural stop
    MpcRealignStrategy  — the driver
"""

from __future__ import annotations

import sys
from pathlib import Path

_PYPKGS = Path(__file__).resolve().parents[1]
if str(_PYPKGS) not in sys.path:
    sys.path.insert(0, str(_PYPKGS))

from .config import RealignConfig
from .execution import RealignExecution
from .htf import HtfStructure
from .strategy import MpcRealignStrategy
from .tracker import RealignTracker

__all__ = [
    "HtfStructure",
    "LAB_STRATEGY",
    "MpcRealignStrategy",
    "RealignConfig",
    "RealignExecution",
    "RealignTracker",
]

# ── Lab registration (runner="python") ───────────────────────────────────────────
# 🔴 THIS MUST BE A DICT, AND IT WAS A BARE CLASS UNTIL 2026-08-13.
#
# The scanner and the python runner both do `isinstance(spec, dict) and "config" in spec`
# and `continue` when it fails — with a comment saying that is "the normal state for a
# helper package". So exporting the class alone did not error, did not warn and did not
# appear in `ScanResult.warnings`: this package was simply ABSENT from the lab, looking
# exactly like a directory with no strategy in it. `run_report.py` reads the same contract
# (`spec["strategy"]`, `spec["config"]`), so the strategy was equally undrivable there.
#
# ⚠ The lab keys a strategy off the CLASS NAME, not the package name, so all four register
# and run side by side. `self_sizing` is True because this strategy applies its own risk %
# (`qty = equity·exec_risk_pct / stop_distance`) — the lab must NOT re-size it, or the page
# shows two different P&Ls for one run.
LAB_STRATEGY = {
    "name": "MPC REALIGN",
    "config": RealignConfig,
    "strategy": MpcRealignStrategy,
    "suggested_instrument": "XAUUSD",
    "category": "reversal",
    "self_sizing": True,
}
