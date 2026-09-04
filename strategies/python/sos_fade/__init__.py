"""SOS Fade — the reversal strategy ported from strategies/tradingview/sos_fade_strategy.pine.

Reads the canonical engine stack's per-bar `BarState` (backtest.replay) and turns the
SOS Fade sequence into orders. Public API grows as Deliverable B lands:

    SosFadeConfig      — every Pine input toggle (toggle parity), with Pine defaults
    Signals          — one bar's Pine-named inputs; SignalAdapter builds them
    SeqState         — the SOS Fade sequence's per-bar output; SosFadeSequence runs it

Build status: config + signal adapter + sequence state machine landed. Execution
(orders / fills / stop-staging) and the top-level driver are next.
"""

from __future__ import annotations

from .config import SosFadeConfig
from .execution import Decision, Execution, Fill, Trade
from .sequence import SosFadeSequence, SeqState
from .signals import SignalAdapter, Signals
from .strategy import SosFadeStrategy

__all__ = [
    "SosFadeConfig",
    "SosFadeSequence",
    "Decision",
    "Execution",
    "Fill",
    "LAB_STRATEGY",
    "SosFadeStrategy",
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
    "name": "SOS Fade",   # display name; the Platform column already says it's Python
    "config": SosFadeConfig,
    "strategy": SosFadeStrategy,
    "suggested_instrument": "XAUUSD",   # Vantage demo name (no ".s"; that was PU Prime) — backtests pull from MT5_Lab = Vantage
    # 🔴 THE FRAME THIS BOT WAS MEASURED ON, in minutes — every parity export and every shipped
    # figure is M15 (CLAUDE.md: the 21,060-bar `VANTAGE_XAUUSD, 15m` gate, the 155,807-bar full-
    # history replays).
    # ⚠ It is a DEFAULT the lab fills in, never a refusal: nothing here stops a run on
    #   another frame, so a figure quoted off one is a different experiment and has to say
    #   so. Before this key existed the stack page ran every leg on ONE frame the reader
    #   picked, so a 5m bot silently replayed on 15m beside a 15m one and the table read
    #   as a portfolio result.
    "suggested_bar_value": 15,
    "category": "reversal",
    # This bot sizes ITSELF: qty = equity * exec_risk_pct / stop_distance, every trade (the Pine
    # does the same). So the lab's dynamic sizing engine must not re-size it — `exec_risk_pct` IS
    # the risk knob, editable per run and sweepable in the optimizer. Contrast ORB/LondonBreakout,
    # which propose unit-size trades and let the engine size them against a firm's ladder.
    "self_sizing": True,
    # This bot's own word for its setup, worn by its trades on the price chart. Until
    # 2026-09-02 that chip was hard-coded to the SOS Fade bot's word on EVERY strategy's chart, so
    # every other bot's trades carried a label belonging to a fourth. 🔴 **It is what tells the
    # legs apart on a STACK**, where several strategies' trades share one chart — that is the
    # case it exists for. ⚠ A LABEL and nothing else: no run, no cost and no decision reads it,
    # so changing it repaints chips and moves no trade. ⚠ Keep it SHORT — it is drawn beside
    # the entry price and a long word pushes the price off the marker. ⚠ the grade this bot's own Pine calls its setup.
    "chart_tag": "SOS FADE",
}
