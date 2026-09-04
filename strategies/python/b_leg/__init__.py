"""B-LEG — the late-retrace reversal, split out to run PARALLEL to the A+ bot.

Ported from `strategies/tradingview/b_leg_strategy.pine` (Aaron's brother's B-LEG fork of the
MPC-JARVIS strategy). It reuses the canonical engine stack + the A+ SEQUENCE tracker from
`sos_fade` (the B-LEG arms off the A+ death) and adds only the B-LEG tracker + a thin
execution subclass. Full rules: `CLAUDE.md` in this package.

    BLegConfig       — SosFadeConfig superset + `bleg_max_days`
    BLegTracker      — the B-LEG band-freeze / arm / death state machine (BLegState)
    BLegExecution    — A+-entry-disabled, B-LEG-entry-only order layer
    BLegStrategy  — the driver
"""

from __future__ import annotations

import sys
from pathlib import Path

_PYPKGS = Path(__file__).resolve().parents[1]
if str(_PYPKGS) not in sys.path:
    sys.path.insert(0, str(_PYPKGS))

from .bleg import BLegState, BLegTracker
from .config import BLegConfig
from .execution import BLegExecution
from .strategy import BLegStrategy

__all__ = [
    "BLegConfig",
    "BLegState",
    "BLegTracker",
    "BLegExecution",
    "LAB_STRATEGY",
    "BLegStrategy",
]

# ── Lab registration (runner="python") ───────────────────────────────────────────
# Same opt-in contract as sos_fade: the scanner imports the package and reads this dict.
# The lab keys the strategy off the CLASS name ("BLegStrategy"), distinct from the A+ bot,
# so the two register and run side by side — the parallel-stack use case the B-LEG was split
# out for. It sizes ITSELF (qty = equity·exec_risk_pct / stop_distance), like the A+ bot.
LAB_STRATEGY = {
    "name": "B-LEG",
    "config": BLegConfig,
    "strategy": BLegStrategy,
    "suggested_instrument": "XAUUSD",
    # 🔴 THE FRAME THIS BOT WAS MEASURED ON, in minutes — its measured book is M15 (CLAUDE.md:
    # 186,312 M15 bars, 2018-09-13 → 2026-08-05).
    # ⚠ It is a DEFAULT the lab fills in, never a refusal: nothing here stops a run on
    #   another frame, so a figure quoted off one is a different experiment and has to say
    #   so. Before this key existed the stack page ran every leg on ONE frame the reader
    #   picked, so a 5m bot silently replayed on 15m beside a 15m one and the table read
    #   as a portfolio result.
    "suggested_bar_value": 15,
    "category": "reversal",
    "self_sizing": True,
    # This bot's own word for its setup, worn by its trades on the price chart. Until
    # 2026-09-02 that chip was hard-coded to the A+ bot's word on EVERY strategy's chart, so
    # every other bot's trades carried a label belonging to a fourth. 🔴 **It is what tells the
    # legs apart on a STACK**, where several strategies' trades share one chart — that is the
    # case it exists for. ⚠ A LABEL and nothing else: no run, no cost and no decision reads it,
    # so changing it repaints chips and moves no trade. ⚠ Keep it SHORT — it is drawn beside
    # the entry price and a long word pushes the price off the marker. ⚠ the late-retrace leg, which is what the package is named for.
    "chart_tag": "B-LEG",
    # 🔴 DISPLAY GROUPING ONLY — it changes where the row is drawn and NOTHING about what this
    # bot may be run with. B-LEG runs standalone, in any stack, against any instrument, exactly
    # as before; nothing reads this field except the strategies list. It sits under the A+ bot
    # because the suite is carved up by LEG off ONE structure stream (see the root CLAUDE.md's
    # trading philosophy) and a flat alphabetical list hid that relationship entirely.
    # ⚠ Rule 22 gates this file: shipped only after `tools/compare_bleg.py` ran GREEN on
    # `engines/VANTAGE_XAUUSD, 5_f8228.csv` (20,573 M5 bars, identical on every bar from 0).
    "display_under": "sos_fade",
}
