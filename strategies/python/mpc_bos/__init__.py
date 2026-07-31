"""MPC BOS — the break-of-structure CONTINUATION setup.

A+ fades the shift of structure; this rides what the shift started. An SOS opens a regime,
each BOS after it is a fresh continuation leg, and the retracement into that leg's
0.5-0.886 band — onto the fair value gap the break left behind — is the trade.

Ported from `indicators/mpc_bos_strategy.pine` (spec: `docs/MPC_BOS_SPEC.md`). It reuses the
canonical engine stack and the A+ entry ladder / exit ladder from `mpc_sos_fade`, and adds
only the BOS tracker + a thin execution subclass. Full rules: `CLAUDE.md` in this package.

    BosConfig      — SosFadeConfig superset + the BOS setup / filter / stop inputs
    BosTracker     — regime, arm, quality filters, anchor fib, death (BosState)
    BosExecution   — the entry ladder on the BOS leg + the five-way stop model
    MpcBosStrategy — the driver
"""

from __future__ import annotations

import sys
from pathlib import Path

_PYPKGS = Path(__file__).resolve().parents[1]
if str(_PYPKGS) not in sys.path:
    sys.path.insert(0, str(_PYPKGS))

from .bos import BosLeg, BosState, BosTracker
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
]

# ── Lab registration (runner="python") ───────────────────────────────────────────
LAB_STRATEGY = {
    "name": "MPC BOS",
    "config": BosConfig,
    "strategy": MpcBosStrategy,
    "suggested_instrument": "XAUUSD",
    "category": "continuation",
    "self_sizing": True,
}
