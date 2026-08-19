"""loss_recovery — take a counter-trade after a strategy loses, to win the loss back.

Generic by construction: the trigger is "a primary trade lost", which every strategy here can
state, so the engine is defined against the `LossEvent` protocol rather than any one strategy's
Trade class. `mpc_sos_fade.execution.Trade` satisfies it as-is.

    from loss_recovery import LossRecoveryEngine, RecoveryConfig

    cfg = RecoveryConfig(enabled=True)
    recoveries = LossRecoveryEngine(cfg).run(bars_m15, strat.execution.trades)
    journal_r  = [t.scaled_r for t in recoveries]   # scaled_r, never r — see types.py

⚠ Disabled by default and NOT wired into any bot. No Pine twin exists, so there is no parity
gate. Everything it has produced is a lab finding. See CLAUDE.md → Status.
"""

from __future__ import annotations

from .config import RecoveryConfig
from .engine import LossRecoveryEngine
from .types import ArmedSignal, LossEvent, RecoveryTrade

__all__ = [
    "ArmedSignal",
    "LossEvent",
    "LossRecoveryEngine",
    "RecoveryConfig",
    "RecoveryTrade",
]
