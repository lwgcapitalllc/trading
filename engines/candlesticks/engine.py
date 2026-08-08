"""
candlesticks/engine.py — the candlestick-pattern detector.

One stateful streaming engine, fed one CLOSED bar at a time (index + OHLC). It returns every pattern
that fired on that bar. Ported line-by-line from `indicators/candle_sticks.pine` ("Candlestick
Patterns Identified", repo32, v6), which is a flat file of fifteen boolean expressions and their
`plotshape` calls — there is no state machine in the source, so the only state here is the rolling
OHLC window each rule reads back through.

Standalone and OHLC-driven: no upstream engine, no volume, no timestamp. A sibling of
`fair_value_gaps/`, `rsi_divergence/` and `equal_highs_lows/` in shape.

WHAT IT IS FOR
--------------
Confluence. A pattern here is a property of ONE bar — it forms and it is over. Nothing is mitigated,
nothing expires, there is no live list. A strategy asks either "did X fire on this bar"
(`ev.has(...)` / `ev.matching(...)`) or "how long since X last fired" (`bars_since(...)`).

TWO PINE SEMANTICS THAT DECIDE PARITY
-------------------------------------
1. **`na` compares FALSE.** Every rule that reads `open[trend]`, `high[2]` or `ta.lowest(10)[1]`
   is simply false until that history exists, because in Pine any comparison involving `na` is
   false. Each detector below guards on its own `min_history` rather than letting a missing bar
   raise or, worse, be treated as 0.0 — a fabricated zero would make several of these rules fire on
   the first few bars of every chart.

2. **`trend` is a HISTORY OFFSET TAKEN FROM AN INPUT.** Ten of the fifteen rules gate on
   `open[trend] < open` (bearish) or `open[trend] > open` (bullish) — the only trend-context filter
   in the file. `trend` therefore sizes this engine's window, and on the Pine side it sizes the
   history buffer. ⚠ **The source declares it `input.int(5, minval = 1)` with NO `maxval`**, so a
   large value walks straight off Pine's default ~300-bar buffer and throws at runtime — the exact
   shape `indicators/CLAUDE.md` records for `execVwapSlopeBars`. That is a finding about the source
   file, not about this engine (Python sizes its deque from the value), and the export harness pins
   `max_bars_back` to cover it.

ONE ASSUMPTION, NAMED
---------------------
`bullBelt` reads `lower = ta.lowest(10)[1]` — the lowest LOW over the ten bars ENDING ON THE
PREVIOUS BAR. This engine returns "no value" (and therefore no belt) until those ten bars exist,
mirroring Pine returning `na` before its length is satisfied. It is inside any sane warm-up, so it
cannot affect a real parity run; it is written down because an assumption nobody wrote down is one
nobody checks.
"""

from __future__ import annotations

from collections import deque
from typing import Deque, Dict, List, Optional, Tuple

from .types import (
    PATTERNS,
    PATTERN_KEYS,
    CandlePattern,
    CandlestickEvents,
    PatternSpec,
    resolve_keys,
)

_TREND_SENTINEL = -1     # PatternSpec.min_history value meaning "needs `trend` bars"


class CandlestickEngine:
    """Streaming candlestick-pattern detector.

    Build one per symbol/timeframe and feed it closed candles in order.

    Defaults mirror the Pine inputs exactly: `trend = 5` (Pine "Trend in Bars") and
    `doji_size = 0.05` (Pine "Doji size"). `patterns` selects which rules are evaluated — None means
    all fifteen, which is what the parity harness always runs. Narrowing it is a CONSUMER choice
    (a strategy that only reads engulfings), and it never changes what a given rule decides: the
    unselected ones are skipped, not redefined.
    """

    def __init__(self, trend: int = 5, doji_size: float = 0.05,
                 patterns: Optional[List[str]] = None) -> None:
        if trend < 1:
            raise ValueError(f"trend must be >= 1 (Pine minval), got {trend}")
        if doji_size <= 0:
            # Pine declares minval = 0.01. A zero or negative body tolerance makes `doji` mean
            # "open == close exactly", which is a different rule wearing the same name.
            raise ValueError(f"doji_size must be > 0 (Pine minval 0.01), got {doji_size}")

        self._trend = trend
        self._doji_size = doji_size
        self._enabled: Tuple[str, ...] = resolve_keys(patterns)
        self._specs: Tuple[PatternSpec, ...] = tuple(
            p for p in PATTERNS if p.key in set(self._enabled)
        )

        # Rolling OHLC window, newest LAST. Deepest reads: `open[trend]` and the ten lows behind
        # `ta.lowest(10)[1]` (bars [1]..[10]), so the window must hold max(trend, 10) + 1 bars.
        self._window: Deque[Tuple[float, float, float, float]] = deque(
            maxlen=max(trend, 10) + 1
        )

        self._bar_index: int = -1
        self._bars_seen: int = 0
        self._last_bar: Dict[str, int] = {}       # key -> bar index it last fired on

    # ------------------------------------------------------------------
    # public
    # ------------------------------------------------------------------
    @property
    def trend(self) -> int:
        return self._trend

    @property
    def doji_size(self) -> float:
        return self._doji_size

    @property
    def enabled(self) -> Tuple[str, ...]:
        """The pattern keys this instance evaluates, in registry order."""
        return self._enabled

    def update(self, bar_index: int, open_: float, high: float, low: float,
               close: float) -> CandlestickEvents:
        """Feed one closed bar (index + OHLC). Returns the patterns that fired on it."""
        self._window.append((open_, high, low, close))
        self._bar_index = bar_index
        self._bars_seen += 1

        events = CandlestickEvents(bar_index=bar_index)
        for spec in self._specs:
            if not self._has_history(spec):
                continue
            if self._DETECTORS[spec.key](self):
                events.detected.append(CandlePattern(spec=spec, bar_index=bar_index))
                self._last_bar[spec.key] = bar_index
        return events

    def bars_since(self, key: str) -> Optional[int]:
        """How many bars ago `key` last fired — 0 = this bar, None = never seen.

        This is the confluence-window read ("a bullish engulfing within the last 3 bars"). It counts
        BAR INDICES as handed in, so it is only meaningful if the caller feeds a monotonic index.
        ⚠ Returns None rather than a large number when the pattern has never fired: "never" and "a
        long time ago" are different answers and a sentinel integer would collapse them.
        """
        if key not in set(self._enabled):
            raise KeyError(
                f"pattern {key!r} is not enabled on this engine (enabled: {', '.join(self._enabled)})"
            )
        last = self._last_bar.get(key)
        return None if last is None else self._bar_index - last

    # ------------------------------------------------------------------
    # window access — Pine's `x[k]`, returning None where Pine would return `na`
    # ------------------------------------------------------------------
    def _bar(self, k: int) -> Optional[Tuple[float, float, float, float]]:
        """The bar `k` back (`k = 0` is this bar). None when that bar is not in history yet."""
        if k >= self._bars_seen or k >= len(self._window):
            return None
        return self._window[-1 - k]

    def _o(self, k: int = 0) -> Optional[float]:
        b = self._bar(k)
        return None if b is None else b[0]

    def _h(self, k: int = 0) -> Optional[float]:
        b = self._bar(k)
        return None if b is None else b[1]

    def _l(self, k: int = 0) -> Optional[float]:
        b = self._bar(k)
        return None if b is None else b[2]

    def _c(self, k: int = 0) -> Optional[float]:
        b = self._bar(k)
        return None if b is None else b[3]

    def _has_history(self, spec: PatternSpec) -> bool:
        """Is there enough history for this rule to be true at all? (Pine: `na` compares false.)"""
        need = self._trend if spec.min_history == _TREND_SENTINEL else spec.min_history
        if spec.key == "bullish_belt":
            # Belt reads BOTH `open[trend]` and ta.lowest(10)[1], so it needs the deeper of the two.
            need = max(need, 10)
        return self._bars_seen > need

    def _lowest10_prev(self) -> Optional[float]:
        """Pine `ta.lowest(10)[1]` — the lowest LOW over the ten bars ending on the PREVIOUS bar.

        None until those ten bars exist (see the module docstring's named assumption).
        """
        lows = [self._l(k) for k in range(1, 11)]
        if any(v is None for v in lows):
            return None
        return min(lows)          # type: ignore[arg-type]

    # ------------------------------------------------------------------
    # the fifteen rules — each one line-for-line against candle_sticks.pine
    # ------------------------------------------------------------------
    def _doji(self) -> bool:
        # doji = math.abs(open - close) <= (high - low) * dojiSize
        o, h, l, c = self._o(), self._h(), self._l(), self._c()
        return abs(o - c) <= (h - l) * self._doji_size          # type: ignore[operator]

    def _bearish_harami(self) -> bool:
        # close[1] > open[1] and open > close and open <= close[1] and open[1] <= close
        #   and open - close < close[1] - open[1] and open[trend] < open
        o, c = self._o(), self._c()
        o1, c1 = self._o(1), self._c(1)
        ot = self._o(self._trend)
        return (c1 > o1 and o > c and o <= c1 and o1 <= c            # type: ignore[operator]
                and (o - c) < (c1 - o1) and ot < o)                 # type: ignore[operator]

    def _bullish_harami(self) -> bool:
        # open[1] > close[1] and close > open and close <= open[1] and close[1] <= open
        #   and close - open < open[1] - close[1] and open[trend] > open
        o, c = self._o(), self._c()
        o1, c1 = self._o(1), self._c(1)
        ot = self._o(self._trend)
        return (o1 > c1 and c > o and c <= o1 and c1 <= o            # type: ignore[operator]
                and (c - o) < (o1 - c1) and ot > o)                 # type: ignore[operator]

    def _bearish_engulfing(self) -> bool:
        # close[1] > open[1] and open > close and open >= close[1] and open[1] >= close
        #   and open - close > close[1] - open[1] and open[trend] < open
        o, c = self._o(), self._c()
        o1, c1 = self._o(1), self._c(1)
        ot = self._o(self._trend)
        return (c1 > o1 and o > c and o >= c1 and o1 >= c            # type: ignore[operator]
                and (o - c) > (c1 - o1) and ot < o)                 # type: ignore[operator]

    def _bullish_engulfing(self) -> bool:
        # open[1] > close[1] and close > open and close >= open[1] and close[1] >= open
        #   and close - open > open[1] - close[1] and open[trend] > open
        # ⚠ `close[1] >= open`, NOT `<=`. It is the exact mirror of bearEng's `open[1] >= close`
        # and it is what makes this ENGULF: this bar's open must sit at or BELOW the prior close as
        # well as its close being at or above the prior open. Reading it the intuitive way round
        # (`c1 <= o`) still passes on plenty of real bars, so the rule would look like it worked.
        o, c = self._o(), self._c()
        o1, c1 = self._o(1), self._c(1)
        ot = self._o(self._trend)
        return (o1 > c1 and c > o and c >= o1 and c1 >= o            # type: ignore[operator]
                and (c - o) > (o1 - c1) and ot > o)                 # type: ignore[operator]

    def _piercing_line(self) -> bool:
        # close[1] < open[1] and open < low[1] and close > close[1] + ((open[1] - close[1]) / 2)
        #   and close < open[1] and open[trend] > open
        o, c = self._o(), self._c()
        o1, c1, l1 = self._o(1), self._c(1), self._l(1)
        ot = self._o(self._trend)
        return (c1 < o1 and o < l1                                   # type: ignore[operator]
                and c > c1 + ((o1 - c1) / 2) and c < o1              # type: ignore[operator]
                and ot > o)                                          # type: ignore[operator]

    def _bullish_belt(self) -> bool:
        # lower = ta.lowest(10)[1]
        # low == open and open < lower and open < close
        #   and close > ((high[1] - low[1]) / 2) + low[1] and open[trend] > open
        o, l, c = self._o(), self._l(), self._c()
        h1, l1 = self._h(1), self._l(1)
        ot = self._o(self._trend)
        lower = self._lowest10_prev()
        if lower is None:
            return False
        return (l == o and o < lower and o < c                        # type: ignore[operator]
                and c > ((h1 - l1) / 2) + l1 and ot > o)              # type: ignore[operator]

    def _bullish_kicker(self) -> bool:
        # open[1] > close[1] and open >= open[1] and close > open and open[trend] > open
        o, c = self._o(), self._c()
        o1, c1 = self._o(1), self._c(1)
        ot = self._o(self._trend)
        return o1 > c1 and o >= o1 and c > o and ot > o                # type: ignore[operator]

    def _bearish_kicker(self) -> bool:
        # open[1] < close[1] and open <= open[1] and close <= open and open[trend] < open
        o, c = self._o(), self._c()
        o1, c1 = self._o(1), self._c(1)
        ot = self._o(self._trend)
        return o1 < c1 and o <= o1 and c <= o and ot < o                # type: ignore[operator]

    def _hanging_man(self) -> bool:
        # (high - low > 4 * math.abs(open - close))
        #   and ((close - low) / (0.001 + high - low) >= 0.75)
        #   and ((open  - low) / (0.001 + high - low) >= 0.75)
        #   and open[trend] < open and high[1] < open and high[2] < open
        o, h, l, c = self._o(), self._h(), self._l(), self._c()
        h1, h2 = self._h(1), self._h(2)
        ot = self._o(self._trend)
        rng = 0.001 + h - l                                            # type: ignore[operator]
        return ((h - l > 4 * abs(o - c))                               # type: ignore[operator]
                and ((c - l) / rng >= 0.75)                            # type: ignore[operator]
                and ((o - l) / rng >= 0.75)                            # type: ignore[operator]
                and ot < o and h1 < o and h2 < o)                      # type: ignore[operator]

    def _evening_star(self) -> bool:
        # close[2] > open[2] and math.min(open[1], close[1]) > close[2]
        #   and open < math.min(open[1], close[1]) and close < open
        o, c = self._o(), self._c()
        o1, c1 = self._o(1), self._c(1)
        o2, c2 = self._o(2), self._c(2)
        return (c2 > o2 and min(o1, c1) > c2                           # type: ignore[operator]
                and o < min(o1, c1) and c < o)                         # type: ignore[operator]

    def _morning_star(self) -> bool:
        # close[2] < open[2] and math.max(open[1], close[1]) < close[2]
        #   and open > math.max(open[1], close[1]) and close > open
        o, c = self._o(), self._c()
        o1, c1 = self._o(1), self._c(1)
        o2, c2 = self._o(2), self._c(2)
        return (c2 < o2 and max(o1, c1) < c2                           # type: ignore[operator]
                and o > max(o1, c1) and c > o)                         # type: ignore[operator]

    def _shooting_star(self) -> bool:
        # open[1] < close[1] and open > close[1]
        #   and high - math.max(open, close) >= math.abs(open - close) * 3
        #   and math.min(close, open) - low <= math.abs(open - close)
        o, h, l, c = self._o(), self._h(), self._l(), self._c()
        o1, c1 = self._o(1), self._c(1)
        body = abs(o - c)                                              # type: ignore[operator]
        return (o1 < c1 and o > c1                                     # type: ignore[operator]
                and h - max(o, c) >= body * 3                          # type: ignore[operator]
                and min(c, o) - l <= body)                             # type: ignore[operator]

    def _hammer(self) -> bool:
        # (high - low > 3 * math.abs(open - close))
        #   and ((close - low) / (0.001 + high - low) > 0.6)
        #   and ((open  - low) / (0.001 + high - low) > 0.6)
        o, h, l, c = self._o(), self._h(), self._l(), self._c()
        rng = 0.001 + h - l                                            # type: ignore[operator]
        return ((h - l > 3 * abs(o - c))                               # type: ignore[operator]
                and ((c - l) / rng > 0.6)                              # type: ignore[operator]
                and ((o - l) / rng > 0.6))                             # type: ignore[operator]

    def _inverted_hammer(self) -> bool:
        # (high - low > 3 * math.abs(open - close))
        #   and ((high - close) / (0.001 + high - low) > 0.6)
        #   and ((high - open)  / (0.001 + high - low) > 0.6)
        o, h, l, c = self._o(), self._h(), self._l(), self._c()
        rng = 0.001 + h - l                                            # type: ignore[operator]
        return ((h - l > 3 * abs(o - c))                               # type: ignore[operator]
                and ((h - c) / rng > 0.6)                              # type: ignore[operator]
                and ((h - o) / rng > 0.6))                             # type: ignore[operator]

    # Bound at class level so `update()` dispatches by key without a fifteen-branch chain. Keys are
    # the registry's, so a pattern added to PATTERNS with no detector here fails loudly at import.
    _DETECTORS = {
        "doji": _doji,
        "bearish_harami": _bearish_harami,
        "bullish_harami": _bullish_harami,
        "bearish_engulfing": _bearish_engulfing,
        "bullish_engulfing": _bullish_engulfing,
        "piercing_line": _piercing_line,
        "bullish_belt": _bullish_belt,
        "bullish_kicker": _bullish_kicker,
        "bearish_kicker": _bearish_kicker,
        "hanging_man": _hanging_man,
        "evening_star": _evening_star,
        "morning_star": _morning_star,
        "shooting_star": _shooting_star,
        "hammer": _hammer,
        "inverted_hammer": _inverted_hammer,
    }


# A registry row with no detector would be a pattern that silently never fires — the quietest
# failure available here — so it is a hard error at import time rather than a runtime absence.
_missing = [k for k in PATTERN_KEYS if k not in CandlestickEngine._DETECTORS]
if _missing:      # pragma: no cover - import-time guard
    raise RuntimeError(f"candlesticks: PATTERNS rows with no detector: {_missing}")
_orphan = [k for k in CandlestickEngine._DETECTORS if k not in PATTERN_KEYS]
if _orphan:       # pragma: no cover - import-time guard
    raise RuntimeError(f"candlesticks: detectors with no PATTERNS row: {_orphan}")
