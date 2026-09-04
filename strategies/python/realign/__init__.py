"""realign — Realign: internal-structure realignment after an external false break.

Spec: docs/REALIGN_SPEC.md
Full rules: `CLAUDE.md` in this package.

    RealignConfig       — SosFadeConfig superset + the realign levers
    HtfStructure        — the external frame, aggregated from the chart frame
    RealignTracker      — arms on the false break, walks the realignment
    RealignExecution    — the MARKET entry, sizing, the structural stop
    RealignStrategy  — the driver
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
from .strategy import RealignStrategy
from .tracker import RealignTracker

__all__ = [
    "HtfStructure",
    "LAB_STRATEGY",
    "RealignStrategy",
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
    "name": "Realign",
    "config": RealignConfig,
    "strategy": RealignStrategy,
    "suggested_instrument": "XAUUSD",
    # 🔴 THE FRAME THIS BOT WAS MEASURED ON, in minutes — it trades the 5m and reads the 15m
    # through its own aggregator — every figure here is a 5m replay (CLAUDE.md: 467,352 M5 bars,
    # 2020-01-02 → 2026-08-06). A single-frame M15 run gives 9 setups in 5.6 years, i.e. no
    # strategy to measure.
    # ⚠ It is a DEFAULT the lab fills in, never a refusal: nothing here stops a run on
    #   another frame, so a figure quoted off one is a different experiment and has to say
    #   so. Before this key existed the stack page ran every leg on ONE frame the reader
    #   picked, so a 5m bot silently replayed on 15m beside a 15m one and the table read
    #   as a portfolio result.
    "suggested_bar_value": 5,
    "category": "reversal",
    "self_sizing": True,
    # This bot's own word for its setup, worn by its trades on the price chart. Until
    # 2026-09-02 that chip was hard-coded to the SOS Fade bot's word on EVERY strategy's chart, so
    # every other bot's trades carried a label belonging to a fourth. 🔴 **It is what tells the
    # legs apart on a STACK**, where several strategies' trades share one chart — that is the
    # case it exists for. ⚠ A LABEL and nothing else: no run, no cost and no decision reads it,
    # so changing it repaints chips and moves no trade. ⚠ Keep it SHORT — it is drawn beside
    # the entry price and a long word pushes the price off the marker. ⚠ the re-alignment with the higher-frame trend.
    "chart_tag": "REALIGN",
}
