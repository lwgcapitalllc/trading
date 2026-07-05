"""
structure_engine.py — Thin shim over trading/engines/market_structure/engine.py

Preserves a bot-friendly update(candle: dict) interface. All BOS/CHoCH/swing detection logic now
lives in trading/engines/market_structure/ — this file does not reimplement any of it.

Replaces a prior, unrelated "FFT Structure Engine" implementation (left over from the deleted FFT
bot) that nothing in the repo imported. See algos/CLAUDE.md's Shared Components table.
"""

import sys
from pathlib import Path
from typing import Optional

# Add engines/ to sys.path so we can import from trading/engines/market_structure/
_ENGINES = Path(__file__).resolve().parent.parent.parent / "engines"
if str(_ENGINES) not in sys.path:
    sys.path.insert(0, str(_ENGINES))

from market_structure import Bar, StructureEngine as _StructureEngine, StructureEvents


class StructureEngine:
    """
    Bot-facing wrapper over market_structure.StructureEngine.

    Usage:
        eng = StructureEngine(major_length=15)
        events = eng.update({"open": o, "high": h, "low": l, "close": c})   # one closed candle
        # or, for backtesting:
        all_events = eng.replay(candles)   # list of dicts, or a pandas DataFrame

        eng.dir                  # 1 bullish, -1 bearish, 0 undetermined
        eng.active_swing_high    # SwingLevel | None
        eng.active_swing_low
    """

    def __init__(self, major_length: int = 15):
        self._engine = _StructureEngine(major_length=major_length)
        self._bar_index = 0

    def update(self, candle: dict) -> StructureEvents:
        """Process one closed candle. candle must have open/high/low/close keys; index is
        auto-incremented if not supplied."""
        idx = candle["index"] if "index" in candle else self._bar_index
        bar = Bar(
            index=idx,
            open=float(candle["open"]),
            high=float(candle["high"]),
            low=float(candle["low"]),
            close=float(candle["close"]),
        )
        self._bar_index = idx + 1
        return self._engine.update(bar)

    def replay(self, candles) -> list:
        """Convenience for backtesting — see market_structure.StructureEngine.replay."""
        return self._engine.replay(candles)

    @property
    def dir(self) -> int:
        return self._engine.dir

    @property
    def active_swing_high(self):
        return self._engine.active_swing_high

    @property
    def active_swing_low(self):
        return self._engine.active_swing_low

    @property
    def last_confirmed_high(self):
        return self._engine.last_confirmed_high

    @property
    def last_confirmed_low(self):
        return self._engine.last_confirmed_low

    @property
    def internal_mode(self) -> int:
        return self._engine.internal_mode

    @property
    def internal_swing(self):
        return self._engine.internal_swing
