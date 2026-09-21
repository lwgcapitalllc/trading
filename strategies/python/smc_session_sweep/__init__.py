"""The session-sweep Python port — the decision core, its lab driver and its parity gate.

A session hunts the previous session's high or low and this trades the reversal off it. London
hunts Asia, New York hunts London. Ported from
`strategies/tradingview/smc_session_sweep_strategy.pine`; full rules in `CLAUDE.md` here.

    SessionSweepConfig     — every Pine input that can move a trade, and nothing else
    SessionSweepCore       — the bar-for-bar transcription, including Pine's broker
    SessionSweepStrategy   — the lab driver
    ResampledStructure     — the direction stream, rebuilt from the replayed frame
    PrevPeriodLevels       — yesterday's and last week's extremes, rebuilt the same way

🔴 **The confirmation timeframe must EQUAL the bar frame the run replays, and the direction
timeframe must be a whole multiple of it.** The strategy reads both through `request.security` on
the chart; here they are rebuilt from the replayed bars, and a finer timeframe cannot be rebuilt
from a coarser one. The shipped config confirms on 1 minute, so a lab run of it needs 1-minute
bars — or the confirmation moved to the frame you are replaying, which is a DIFFERENT strategy
from the one the chart trades and needs its own export before any number off it is believed.
`SessionSweepStrategy` refuses by name rather than quietly confirming on the wrong frame.
"""

from __future__ import annotations

from .config import SessionSweepConfig
from .core import BarInput, BarOutput, SessionSweepCore, SweepTrade
from .levels import PrevPeriodLevels
from .strategy import SessionSweepStrategy
from .structure import ResampledStructure, derive_stream

__all__ = [
    "SessionSweepConfig",
    "SessionSweepCore",
    "SessionSweepStrategy",
    "ResampledStructure",
    "PrevPeriodLevels",
    "BarInput",
    "BarOutput",
    "SweepTrade",
    "derive_stream",
    "LAB_STRATEGY",
]

# ── Lab registration (runner="python") ───────────────────────────────────────────
LAB_STRATEGY = {
    "name": "SMC Session Sweep",
    "config": SessionSweepConfig,
    "strategy": SessionSweepStrategy,
    "suggested_instrument": "XAUUSD",
    # It sizes ITSELF — quantity is equity x risk% / stop distance, truncated to the lot step —
    # so the lab's dynamic sizing engine must leave the result alone.
    "self_sizing": True,
    # 🔴 THE FRAME THIS BOT WAS GATED ON, in minutes. Its parity export is 20,597 closed M5 bars.
    # ⚠ Here it is more than a default: the confirmation timeframe is read off the replayed frame
    #    itself, so running on another frame is refused rather than silently rescaled.
    "suggested_bar_value": 5,
    # It prices no spread, so a charged run would bill a flat one. Declared rather than assumed.
    "supports_bid_ask_fills": False,
    "chart_tag": "SWEEP",
}
