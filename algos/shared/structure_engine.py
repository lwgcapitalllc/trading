"""
FFT Structure Engine — event-driven market structure detection.

Swing-high/low and BOS detection, extracted into a shared engine.

Core rules:
  - Body closes confirm breaks; wick-only moves never register.
  - BOS  = body-close beyond the current swing extreme (trend continuation).
  - SOS  = body-close beyond the opposite swing point (trend failure / flip).
  - RETRACEMENT_BEGAN = first opposing candle body-closing back past the new HH/LL close.
  - SOS takes priority over RETRACEMENT on the same candle.

Bootstrap: seeds HH/HL from the first BOOTSTRAP_CANDLES candles (heuristic).
`leg_established` stays False until the first confirmed BOS fires.

Fib anchor derivation (bullish):
  - fib_anchor_high   = swing_high.wick       (top wick of confirmed HH)
  - fib_anchor_low    = prev_swing_low.body   (HL before the BOS leg — leg start)
  - sniper_fib_top    = swing_low.body        (old HH promoted to new HL)
  - sniper_fib_bottom = prev_swing_low.body   (HL before BOS — same as fib_anchor_low)
Bearish mirrors the above.
"""

from dataclasses import dataclass, field
from typing import Optional

try:
    import pandas as pd
    _PANDAS = True
except ImportError:
    _PANDAS = False


@dataclass
class SwingPoint:
    wick: float    # primary extreme: top wick for HH/LH, bottom wick for HL/LL
    body: float    # body close — used for break detection
    index: int


@dataclass
class StructureResult:
    bias: str                               # "bullish" | "bearish" | "undecided"
    swing_high: Optional[SwingPoint]        # confirmed HH (bullish) or LH (bearish)
    swing_low:  Optional[SwingPoint]        # confirmed HL (bullish) or LL (bearish)
    prev_swing_high: Optional[SwingPoint]   # LH before the last bearish BOS
    prev_swing_low:  Optional[SwingPoint]   # HL before the last bullish BOS
    fib_anchor_high: Optional[float]        # top wick of swing_high
    fib_anchor_low:  Optional[float]        # body of prev_swing_low (leg start)
    provisional_extreme: Optional[float]    # running extreme since last BOS
    bos: bool                               # BOS fired on this candle
    sos: bool                               # SOS fired on this candle
    retracement_began: bool                 # RETRACEMENT_BEGAN fired on this candle
    leg_established: bool                   # True after the first confirmed BOS


class StructureEngine:
    """
    Candle-by-candle market structure tracker for the FFT strategy.

    Usage:
        eng = StructureEngine()
        result = eng.replay(df)          # process a full DataFrame
        # or feed candle by candle:
        for c in candles:
            result = eng.update(c)       # c: dict with open/high/low/close

    Key state readable after replay:
        eng._retracement_fired   True when price has pulled back from the current HH
        eng.leg_established      True once the first BOS has fired
        eng.bias                 "bullish" | "bearish" | "undecided"
    """

    BOOTSTRAP_CANDLES = 20

    def __init__(self):
        self.bias: str = "undecided"
        self.swing_high: Optional[SwingPoint] = None
        self.swing_low:  Optional[SwingPoint] = None
        self.prev_swing_high: Optional[SwingPoint] = None  # LH before last bearish BOS
        self.prev_swing_low:  Optional[SwingPoint] = None  # HL before last bullish BOS
        self.leg_established: bool = False
        self._bos_level: Optional[float] = None   # new HH/LL close — RETRACEMENT level
        self._retracement_fired: bool = False
        self._provisional_extreme: Optional[float] = None
        self._candle_count: int = 0
        self._bootstrap_buf: list = []
        self.bootstrapped: bool = False

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def update(self, candle: dict) -> StructureResult:
        """Process one candle. Returns per-candle StructureResult."""
        self._candle_count += 1
        idx = self._candle_count

        if not self.bootstrapped:
            self._bootstrap_buf.append(candle)
            if len(self._bootstrap_buf) >= self.BOOTSTRAP_CANDLES:
                self._bootstrap(self._bootstrap_buf)
                self._bootstrap_buf.clear()
            return self._make_result()

        close = float(candle["close"])
        open_ = float(candle["open"])
        high  = float(candle["high"])
        low   = float(candle["low"])

        is_bearish_candle = close < open_
        is_bullish_candle = close > open_
        bos = sos = retracement_began = False

        if self.bias == "bullish":
            bos, sos, retracement_began = self._process_bullish(
                close, open_, high, low, idx, is_bearish_candle
            )
        elif self.bias == "bearish":
            bos, sos, retracement_began = self._process_bearish(
                close, open_, high, low, idx, is_bullish_candle
            )

        if self.bias == "bullish" and self.swing_high is not None:
            if self._provisional_extreme is None or close > self._provisional_extreme:
                self._provisional_extreme = close
        elif self.bias == "bearish" and self.swing_low is not None:
            if self._provisional_extreme is None or close < self._provisional_extreme:
                self._provisional_extreme = close

        if bos:
            self._provisional_extreme = close

        return self._make_result(bos=bos, sos=sos, retracement_began=retracement_began)

    def replay(self, df) -> StructureResult:
        """Process all rows in df (must have open/high/low/close). Returns final state."""
        result = self._make_result()
        for _, row in df.iterrows():
            result = self.update({k: float(row[k]) for k in ("open", "high", "low", "close")})
        return result

    def reset(self) -> None:
        self.__init__()

    # ------------------------------------------------------------------
    # Bias-specific update logic
    # ------------------------------------------------------------------

    def _process_bullish(self, close, open_, high, low, idx, is_bearish_candle):
        bos = sos = retracement_began = False
        sh = self.swing_high
        sl = self.swing_low

        if sh is not None and close > sh.body:
            # BOS: body-close above current HH
            old_hh = sh
            self.prev_swing_low = sl                                          # save HL before this BOS
            self.swing_high = SwingPoint(wick=high, body=close, index=idx)
            self.swing_low  = SwingPoint(wick=old_hh.wick, body=old_hh.body, index=old_hh.index)
            self._bos_level = close                                           # new HH close
            self._retracement_fired = False
            self.leg_established = True
            bos = True

        elif (self.leg_established and sl is not None and close < sl.body):
            # SOS: body-close below current HL → flip to bearish
            self.bias = "bearish"
            self.swing_low  = SwingPoint(wick=low, body=close, index=idx)
            self.leg_established = False
            self._retracement_fired = False
            self._bos_level = None
            self._provisional_extreme = close
            sos = True

        elif (self.leg_established and
              not self._retracement_fired and
              self._bos_level is not None and
              is_bearish_candle and
              close < self._bos_level):
            # RETRACEMENT_BEGAN: first bearish close back under the new HH close
            retracement_began = True
            self._retracement_fired = True

        return bos, sos, retracement_began

    def _process_bearish(self, close, open_, high, low, idx, is_bullish_candle):
        bos = sos = retracement_began = False
        sh = self.swing_high
        sl = self.swing_low

        if sl is not None and close < sl.body:
            # BOS: body-close below current LL
            old_ll = sl
            self.prev_swing_high = sh                                         # save LH before this BOS
            self.swing_low  = SwingPoint(wick=low,  body=close, index=idx)
            self.swing_high = SwingPoint(wick=old_ll.wick, body=old_ll.body, index=old_ll.index)
            self._bos_level = close                                           # new LL close
            self._retracement_fired = False
            self.leg_established = True
            bos = True

        elif (self.leg_established and sh is not None and close > sh.body):
            # SOS: body-close above current LH → flip to bullish
            self.bias = "bullish"
            self.swing_high = SwingPoint(wick=high, body=close, index=idx)
            self.leg_established = False
            self._retracement_fired = False
            self._bos_level = None
            self._provisional_extreme = close
            sos = True

        elif (self.leg_established and
              not self._retracement_fired and
              self._bos_level is not None and
              is_bullish_candle and
              close > self._bos_level):
            # RETRACEMENT_BEGAN: first bullish close back above the new LL close
            retracement_began = True
            self._retracement_fired = True

        return bos, sos, retracement_began

    # ------------------------------------------------------------------
    # Bootstrap
    # ------------------------------------------------------------------

    def _bootstrap(self, candles: list) -> None:
        """Seed initial structure from the first BOOTSTRAP_CANDLES candles."""
        closes = [float(c["close"]) for c in candles]
        highs  = [float(c["high"])  for c in candles]
        lows   = [float(c["low"])   for c in candles]

        max_close = max(closes)
        min_close = min(closes)
        max_idx   = closes.index(max_close)
        min_idx   = closes.index(min_close)

        if max_idx >= min_idx:
            self.bias = "bullish"
            self.swing_low  = SwingPoint(wick=lows[min_idx],  body=min_close, index=min_idx + 1)
            self.swing_high = SwingPoint(wick=highs[max_idx], body=max_close, index=max_idx + 1)
            self._bos_level = max_close
        else:
            self.bias = "bearish"
            self.swing_high = SwingPoint(wick=highs[max_idx], body=max_close, index=max_idx + 1)
            self.swing_low  = SwingPoint(wick=lows[min_idx],  body=min_close, index=min_idx + 1)
            self._bos_level = min_close

        self.leg_established = False
        self.bootstrapped = True
        self._provisional_extreme = closes[-1]

    # ------------------------------------------------------------------
    # Result builder
    # ------------------------------------------------------------------

    def _make_result(self, bos=False, sos=False, retracement_began=False) -> StructureResult:
        # fib_anchor_low: body of prev_swing_low (HL at leg start); fallback to current swing_low
        if self.prev_swing_low is not None:
            anchor_low = self.prev_swing_low.body
        elif self.swing_low is not None:
            anchor_low = self.swing_low.wick
        else:
            anchor_low = None

        return StructureResult(
            bias=self.bias,
            swing_high=self.swing_high,
            swing_low=self.swing_low,
            prev_swing_high=self.prev_swing_high,
            prev_swing_low=self.prev_swing_low,
            fib_anchor_high=self.swing_high.wick if self.swing_high else None,
            fib_anchor_low=anchor_low,
            provisional_extreme=self._provisional_extreme,
            bos=bos,
            sos=sos,
            retracement_began=retracement_began,
            leg_established=self.leg_established,
        )
