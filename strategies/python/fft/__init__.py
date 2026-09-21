"""FFT — the first touch of the 61.8 on the 5m's first leg, with the 15m behind it and the 1m against.

The user's hand-traded setup, taught to students as a checklist and traded here by the same rules.
The rules are `docs/FFT_SPEC.md`; version 1 is frozen in `backtest/notes/fft_ledger.md`.

    FftConfig      — every setting, one per spec rule; defaults = version 1
    ClockFrame     — the 5m and 15m candles, built from the 1-minute feed as it arrives
    FftStrategy    — the rules, evaluated at every 1-minute close for the next minute
    FftExecution   — one resting limit, one position, and what it cost

⚠ **NO PINE TWIN AND NO TRADINGVIEW PARITY GATE — BY DECISION.** FFT needs 1-minute bars and the
user cannot export them from TradingView (2026-09-21). The engines it reads are already gated
against MPC Jarvis on Vantage 5m/15m exports; the rule layer is proven by matching the study trade
by trade (`tools/compare_study.py`) and by the user's chart check. See `CLAUDE.md` here.
"""

from __future__ import annotations

import sys
from pathlib import Path

_PYPKGS = Path(__file__).resolve().parents[1]
if str(_PYPKGS) not in sys.path:
    sys.path.insert(0, str(_PYPKGS))

from .config import FftConfig
from .execution import FftExecution, Setup
from .frames import Candle, ClockFrame
from .strategy import FftStrategy

__all__ = [
    "Candle",
    "ClockFrame",
    "FftConfig",
    "FftExecution",
    "FftStrategy",
    "LAB_STRATEGY",
    "Setup",
]

LAB_STRATEGY = {
    "name": "FFT (First Fib Touch)",
    "config": FftConfig,
    "strategy": FftStrategy,
    "suggested_instrument": "XAUUSD",
    # 🔴 ONE-MINUTE BARS, AND NOT AS A PREFERENCE: the 1m trend is one of the rules, and the 5m and
    # 15m are built from the 1m inside the strategy. `set_timeframe_minutes` refuses anything else.
    "suggested_bar_value": 1,
    "category": "continuation",
    "self_sizing": True,
    # A resting limit transacts on the side of the book it names, so the spread is modelled by
    # MOVING fills (a buy limit needs the ask to reach it; a short's exits live on the ask) — the
    # way the study's costed run priced it. The flat round-trip charge is used when that is off.
    "supports_bid_ask_fills": True,
    "chart_tag": "FFT",
}
