"""BOS — the break-of-structure CONTINUATION setup, the third bot off the shared engine.

SOS Fade fades the shift of structure; this rides what the shift started. An SOS opens a regime, and
every later BOS in that direction is a fresh continuation leg whose retracement is the entry.
Ported from `strategies/tradingview/bos_strategy.pine`. Full rules: `CLAUDE.md` in this package.

    BosConfig       — SosFadeConfig superset + the BOS setup's own inputs
    BosTracker      — regime / arm / anchor-fib / death state machine (BosState)
    BosExecution    — the BOS order layer (SOS Fade exit ladder + a third TP rung)
    BosStrategy  — the driver

🔴 **NOTHING IN THIS PACKAGE IS PARITY-VALIDATED YET.** `tools/compare_bos.py` exists and has
never been run green, because no TradingView CSV export of `bos_strategy_export.pine` is on
disk. Until it is, every number this bot produces is a LAB FINDING, not a validated one — read
the direction, never the decimals. `docs/BOS_OPTIMIZATION.md` carries the same banner, and
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
from .strategy import BosStrategy

__all__ = [
    "BosConfig",
    "BosLeg",
    "BosState",
    "BosTracker",
    "BosExecution",
    "LAB_STRATEGY",
    "BosStrategy",
    "VolumeUnavailable",
]

# ── Lab registration (runner="python") ───────────────────────────────────────────
# Same opt-in contract as the other two: the scanner imports the package and reads this dict.
# The lab keys the strategy off the CLASS name, so all three register and run side by side.
# It sizes ITSELF (qty = equity·exec_risk_pct / stop_distance), like both siblings.
LAB_STRATEGY = {
    "name": "BOS",
    "config": BosConfig,
    "strategy": BosStrategy,
    "suggested_instrument": "XAUUSD",
    # 🔴 THE FRAME THIS BOT WAS MEASURED ON, in minutes — its parity export is 7,200 closed M15
    # bars (CLAUDE.md, 2026-08-07).
    # ⚠ It is a DEFAULT the lab fills in, never a refusal: nothing here stops a run on
    #   another frame, so a figure quoted off one is a different experiment and has to say
    #   so. Before this key existed the stack page ran every leg on ONE frame the reader
    #   picked, so a 5m bot silently replayed on 15m beside a 15m one and the table read
    #   as a portfolio result.
    "suggested_bar_value": 15,
    "category": "continuation",
    "self_sizing": True,
    # This bot's own word for its setup, worn by its trades on the price chart. Until
    # 2026-09-02 that chip was hard-coded to the SOS Fade bot's word on EVERY strategy's chart, so
    # every other bot's trades carried a label belonging to a fourth. 🔴 **It is what tells the
    # legs apart on a STACK**, where several strategies' trades share one chart — that is the
    # case it exists for. ⚠ A LABEL and nothing else: no run, no cost and no decision reads it,
    # so changing it repaints chips and moves no trade. ⚠ Keep it SHORT — it is drawn beside
    # the entry price and a long word pushes the price off the marker. ⚠ the break of structure it continues into.
    "chart_tag": "BOS",
}
