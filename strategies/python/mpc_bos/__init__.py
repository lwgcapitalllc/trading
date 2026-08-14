"""MPC BOS — the break-of-structure CONTINUATION setup, the third bot off the shared engine.

A+ fades the shift of structure; this rides what the shift started. An SOS opens a regime, and
every later BOS in that direction is a fresh continuation leg whose retracement is the entry.
Ported from `indicators/strategies/mpc_bos_strategy.pine`. Full rules: `CLAUDE.md` in this package.

    BosConfig       — SosFadeConfig superset + the BOS setup's own inputs
    BosTracker      — regime / arm / anchor-fib / death state machine (BosState)
    BosExecution    — the BOS order layer (A+ exit ladder + a third TP rung)
    MpcBosStrategy  — the driver

🔴 **NOTHING IN THIS PACKAGE IS PARITY-VALIDATED YET.** `tools/compare_bos.py` exists and has
never been run green, because no TradingView CSV export of `mpc_bos_strategy_export.pine` is on
disk. Until it is, every number this bot produces is a LAB FINDING, not a validated one — read
the direction, never the decimals. `docs/MPC_BOS_OPTIMIZATION.md` carries the same banner, and
`backtest/tools/bos_sweep.py` was falsified by a single Strategy Tester run for exactly this
reason. Take the export, run the gate, then trust the numbers.
"""

from __future__ import annotations

import sys
from pathlib import Path

_PYPKGS = Path(__file__).resolve().parents[1]
if str(_PYPKGS) not in sys.path:
    sys.path.insert(0, str(_PYPKGS))

from .bos import BosLeg, BosState, BosTracker, VolumeUnavailable
from .config import BosConfig
from .execution import BosExecution
from .strategy import MpcBosStrategy

__all__ = [
    "BosConfig",
    "BosLeg",
    "BosState",
    "BosTracker",
    "BosExecution",
    "LAB_STRATEGY",
    "MpcBosStrategy",
    "VolumeUnavailable",
]

# ── Lab registration (runner="python") ───────────────────────────────────────────
# Same opt-in contract as the other two: the scanner imports the package and reads this dict.
# The lab keys the strategy off the CLASS name, so all three register and run side by side.
# It sizes ITSELF (qty = equity·exec_risk_pct / stop_distance), like both siblings.
LAB_STRATEGY = {
    "name": "MPC BOS",
    "config": BosConfig,
    "strategy": MpcBosStrategy,
    "suggested_instrument": "XAUUSD",
    "category": "continuation",
    "self_sizing": True,
}
