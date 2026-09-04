"""loss_recovery — take a counter-trade after a strategy loses, to win the loss back.

Generic by construction: the trigger is "a primary trade lost", which every strategy here can
state, so the engine is defined against the `LossEvent` protocol rather than any one strategy's
Trade class. `sos_fade.execution.Trade` satisfies it as-is.

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
from .lab import STOP_MODES, RecoveryLabConfig, leg_config, rule_config
from .leg import RecoveryLeg, RecoveryLegConfig
from .types import ArmedSignal, LossEvent, RecoveryTrade

__all__ = [
    "STOP_MODES",
    "ArmedSignal",
    "LAB_STRATEGY",
    "LossEvent",
    "LossRecoveryEngine",
    "RecoveryConfig",
    "RecoveryLabConfig",
    "RecoveryLeg",
    "RecoveryLegConfig",
    "RecoveryTrade",
    "leg_config",
    "rule_config",
]

# 🔴 THIS PACKAGE IS REGISTERED WITH THE LAB, AND `requires_source` IS THE WHOLE POINT OF THE
# ENTRY. It has no setups of its own — it arms off another leg's closed losses — so it cannot be
# picked like an ordinary strategy and cannot be run on its own. The flag is what lets the lab
# state that as a FACT rather than leaving each picker to remember it: the Run modal, the
# optimizer and the stack's own strategy list all filter on it, and the only thing that can
# create one is the stack builder's tick box on a parent.
#
# ⚠ Without the flag this would appear beside the real strategies, and picking it would produce
# an empty book — a rule that was handed nothing looks exactly like a rule that found nothing.
#
# ⚠ `config` is the FLAT lab half (`lab.py`), never `RecoveryLegConfig`: the scanner builds its
# form from `dataclasses.fields`, and the leg's own config carries a nested rule plus four numbers
# derived from the parent and the frame, none of which is the user's to choose.
#
# ⚠ `self_sizing` is True — the leg sizes off the parent's risk % times its own fraction, so the
# lab's sizing engine must not re-size it.
LAB_STRATEGY = {
    "strategy": RecoveryLeg,
    "config": RecoveryLabConfig,
    "name": "Loss Recovery",
    "category": "mean_reversion",
    "self_sizing": True,
    "requires_source": True,
    # 🔴 DISPLAY GROUPING ONLY, and it does NOT pin which parent it may recover. It is listed
    # under the SOS Fade bot because that is the only leg it has been measured against, and a flat
    # alphabetical list put a rule that cannot run alone beside four that can. The stack builder
    # still offers it under ANY ticked parent — `recovery_parent` is what decides that, and it is
    # read off the request, never from here.
    "display_under": "sos_fade",
}
