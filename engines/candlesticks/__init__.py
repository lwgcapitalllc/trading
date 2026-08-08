"""
candlesticks/ — the candlestick-pattern engine subsystem.

Turns the bar stream into CANDLESTICK PATTERN EVENTS: fifteen classic single-, two- and three-bar
patterns (Doji, Harami, Engulfing, Piercing Line, Belt Hold, Kicker, Hanging Man, Morning/Evening
Star, Shooting Star, Hammer, Inverted Hammer), each with the direction the source Pine draws it in.

Ported line-by-line from `indicators/candle_sticks.pine` ("Candlestick Patterns Identified", repo32,
v6). Standalone and OHLC-driven — no upstream engine, no volume, no timestamp. A sibling of
`fair_value_gaps/`, `rsi_divergence/` and `equal_highs_lows/` in shape.

It is a CONFLUENCE source. A pattern is a property of one bar: it fires and it is done. There is no
live list, nothing is mitigated and nothing expires — a consumer either reads this bar's events or
asks the engine how long ago a pattern last fired.

Public API:
    from candlesticks import CandlestickEngine, PATTERN_KEYS, BULLISH, BEARISH

    cs = CandlestickEngine()                     # trend=5, doji_size=0.05 — the Pine defaults
    cs = CandlestickEngine(**CHART_PRESET)       # ...or the settings actually traded, see types.py
    # each closed bar, in order:
    ev = cs.update(bar.index, bar.open, bar.high, bar.low, bar.close)

    ev.detected                                  # every pattern that fired, Pine declaration order
    ev.has("bullish_engulfing")                  # one question about this bar
    ev.matching(keys=("hammer", "morning_star"), direction=BULLISH)   # the confluence read
    ev.bullish / ev.bearish / ev.neutral

    cs.bars_since("bullish_engulfing")           # 0 = this bar, None = never fired

⚠ `direction` is the SOURCE PINE'S rendering, not a trading opinion — Hammer and Inverted Hammer are
emitted NEUTRAL there, with no trend filter behind them. See `types.py`'s docstring before treating
either as bullish.
"""

from .engine import CandlestickEngine
from .types import (
    BEARISH,
    CHART_PRESET,
    BULLISH,
    NEUTRAL,
    PATTERNS,
    PATTERN_KEYS,
    CandlePattern,
    CandlestickEvents,
    PatternSpec,
    resolve_keys,
    spec_for,
)

__all__ = [
    "CandlestickEngine",
    "CandlePattern",
    "CandlestickEvents",
    "PatternSpec",
    "PATTERNS",
    "PATTERN_KEYS",
    "CHART_PRESET",
    "BULLISH",
    "BEARISH",
    "NEUTRAL",
    "spec_for",
    "resolve_keys",
]
