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
    "LAB_STRATEGY",
    "MpcAplusStrategy",
    "SeqState",
    "SignalAdapter",
    "Signals",
    "Trade",
]

# ── Lab registration (runner="python") ───────────────────────────────────────────
# The command-center scanner discovers a Python strategy by importing its package and
# reading this dict — a package OPTS IN by declaring it. Explicit rather than inferred:
# `strategies/python/` also holds test packages and helpers, and a scanner that registered
# every package it could import would put non-strategies in front of the user.
#
# `config` is read with dataclasses.fields() to build the lab's param form, so the form is
# generated from the SAME dataclass the bot runs on and cannot drift from it.
LAB_STRATEGY = {
    "name": "MPC A+ (Python)",
    "config": AplusConfig,
    "strategy": MpcAplusStrategy,
    "suggested_instrument": "XAUUSD.s",
    "category": "reversal",
}
