"""MPC A+ — the reversal strategy ported from indicators/mpc_strategy.pine.

Reads the canonical engine stack's per-bar `BarState` (backtest.replay) and turns the
A+ sequence into orders. Public API grows as Deliverable B lands:

    AplusConfig      — every Pine input toggle (toggle parity), with Pine defaults
    Signals          — one bar's Pine-named inputs; SignalAdapter builds them
    SeqState         — the A+ sequence's per-bar output; AplusSequence runs it

Build status: config + signal adapter + sequence state machine landed. Execution
(orders / fills / stop-staging) and the top-level driver are next.
"""

from __future__ import annotations

from .config import AplusConfig
from .execution import Decision, Execution, Fill, Trade
from .sequence import AplusSequence, SeqState
from .signals import SignalAdapter, Signals
from .strategy import MpcAplusStrategy

__all__ = [
    "AplusConfig",
    "AplusSequence",
    "Decision",
    "Execution",
    "Fill",
    "MpcAplusStrategy",
    "SeqState",
    "SignalAdapter",
    "Signals",
    "Trade",
]
