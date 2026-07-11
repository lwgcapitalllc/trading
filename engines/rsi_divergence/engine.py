"""
rsi_divergence/engine.py — the RSI-divergence state machine.

One stateful streaming engine, fed one closed bar at a time (index + close, plus the bar's high/low
for the price-side anchor). It maintains Wilder's RSI, detects RSI pivots, and confirms regular
divergence at the extremes.

Ported line-by-line from indicators/mpc_assistant.pine's "RSI DIVERGENCE — regular divergence at the
extremes" block (+ the `GRP_DIV` inputs). The Pine runs, each bar:

  divRsi   = ta.rsi(close, divRsiLen)
  divPlRsi = ta.pivotlow(divRsi, divPivotLen, divPivotLen)   // RSI pivot low, confirmed L bars late
  divPhRsi = ta.pivothigh(divRsi, divPivotLen, divPivotLen)  // RSI pivot high

  on a confirmed RSI pivot low:  compare the pivot's price low + RSI low against the *previous* pivot
    low; a LOWER price low + HIGHER RSI low, with the lower RSI ≤ oversold, is a bullish divergence.
    Then latch this pivot as the new "previous". (Bearish mirrors from the pivot-high side.)

  bullDivActive / bearDivActive: the most recent divergence's pivot is within divValidBars bars.

Three Pine details kept exactly, because dropping any would diverge from the chart:

  1. RSI is Wilder's (`ta.rma`-smoothed up/down), seeded by the SMA of the first `divRsiLen` changes —
     not a simple SMA of gains. `RsiState` reproduces `ta.rma` (SMA seed → recursive) exactly.
  2. `ta.pivotlow`/`ta.pivothigh` use a STRICT extreme over the (2·L+1)-bar window centred on the
     candidate (candidate strictly less/greater than every other bar, both sides) — the same semantics
     the validated market_structure engine ports. The pivot is only known `L` bars after the fact;
     that lag is preserved, not optimised away.
  3. The price anchor is `low[divPivotLen]` / `high[divPivotLen]` — the price extreme at the RSI-pivot
     bar (which IS `divPivotLen` bars back), NOT a separately detected price pivot.

The line/label drawing and the `showDiv` toggle are TradingView visuals — this engine always computes
(a consumer that wants it off just ignores the events), and emits the divergence + the live flags.
Standalone: it needs only close (for RSI) + the bar's high/low (for the anchor), no upstream engine.
"""

from __future__ import annotations

from collections import deque
from typing import Deque, List, Optional

from .types import RsiDivergence, RsiDivEvents


class _Rma:
    """Wilder's running moving average — an exact port of Pine's `ta.rma(src, length)`.

    `ta.rma` seeds with `ta.sma(src, length)` (the mean of the first `length` non-na sources) and
    then recurses `rma = alpha*src + (1-alpha)*rma[1]` with `alpha = 1/length`. na sources before
    the seed completes are ignored (they never occur mid-stream here — only `change` on bar 0 is na).
    """

    def __init__(self, length: int) -> None:
        self._length = length
        self._alpha = 1.0 / length
        self._value: Optional[float] = None
        self._seed: List[float] = []
        self._seeded = False

    def update(self, src: Optional[float]) -> Optional[float]:
        if src is None:
            return self._value          # na source (only bar-0 change): leave state untouched
        if not self._seeded:
            self._seed.append(src)
            if len(self._seed) == self._length:
                self._value = sum(self._seed) / self._length
                self._seeded = True
            else:
                self._value = None
            return self._value
        self._value = self._alpha * src + (1.0 - self._alpha) * self._value
        return self._value


class _RsiState:
    """Streaming Wilder RSI — an exact port of Pine's `ta.rsi(close, length)`.

    rsi = 100 - 100/(1 + up/down), where up = rma(max(change,0)) and down = rma(max(-change,0)).
    Returns None until both rma seeds complete (bar `length`), matching Pine's na warm-up.
    """

    def __init__(self, length: int) -> None:
        self._up = _Rma(length)
        self._down = _Rma(length)
        self._prev_close: Optional[float] = None

    def update(self, close: float) -> Optional[float]:
        if self._prev_close is None:
            change = None               # ta.change(close) is na on the first bar
        else:
            change = close - self._prev_close
        self._prev_close = close

        u = max(change, 0.0) if change is not None else None
        d = max(-change, 0.0) if change is not None else None
        up = self._up.update(u)
        down = self._down.update(d)

        if up is None or down is None:
            return None
        if down == 0.0:
            return 100.0
        if up == 0.0:
            return 0.0
        return 100.0 - 100.0 / (1.0 + up / down)


class _Bar:
    """One bar's fields the divergence logic needs: absolute index, price extremes, RSI value."""
    __slots__ = ("index", "high", "low", "rsi")

    def __init__(self, index: int, high: float, low: float, rsi: Optional[float]) -> None:
        self.index = index
        self.high = high
        self.low = low
        self.rsi = rsi


class RsiDivergenceEngine:
    """Streaming RSI-divergence detector.

    Build one per symbol/timeframe, feed it one closed candle at a time as they close, in order.
    Mirrors mpc_assistant.pine's default `GRP_DIV` settings: RSI length 14, pivot width 5, oversold
    25, overbought 75, and a divergence stays "live" confluence for 100 bars after its pivot.
    """

    def __init__(self, rsi_len: int = 14, pivot_len: int = 5, oversold: float = 25.0,
                 overbought: float = 75.0, valid_bars: int = 100) -> None:
        self._rsi_len = rsi_len            # Pine divRsiLen (default 14)
        self._pivot_len = pivot_len        # Pine divPivotLen (default 5)
        self._oversold = oversold          # Pine divOS (default 25)
        self._overbought = overbought      # Pine divOB (default 75)
        self._valid_bars = valid_bars      # Pine divValidBars (default 100)

        self._rsi = _RsiState(rsi_len)

        # Rolling window of the last (2·pivot_len + 1) bars — enough to test the centred candidate.
        self._window: Deque[_Bar] = deque(maxlen=2 * pivot_len + 1)

        # Previous confirmed pivots (Pine divPrev* vars) — the anchor a new pivot is compared to.
        self._prev_low_rsi: Optional[float] = None
        self._prev_low_price: Optional[float] = None
        self._prev_low_bar: Optional[int] = None
        self._prev_high_rsi: Optional[float] = None
        self._prev_high_price: Optional[float] = None
        self._prev_high_bar: Optional[int] = None

        # Most recent divergence pivot bar (Pine lastBull|BearDivBar) — drives the live flags.
        self._last_bull_bar: Optional[int] = None
        self._last_bear_bar: Optional[int] = None

        self._next_id = 0

    # ------------------------------------------------------------------
    def update(self, bar_index: int, high: float, low: float, close: float) -> RsiDivEvents:
        """Feed one closed bar (index + high/low/close). Returns this bar's divergence events."""
        rsi = self._rsi.update(close)
        self._window.append(_Bar(bar_index, high, low, rsi))
        events = RsiDivEvents(rsi=rsi)

        pl_rsi = self._pivot_low_rsi()    # ta.pivotlow(divRsi, L, L): candidate RSI or None
        ph_rsi = self._pivot_high_rsi()   # ta.pivothigh(divRsi, L, L)
        events.pivot_low_rsi = pl_rsi
        events.pivot_high_rsi = ph_rsi

        # The candidate bar is L bars back — it is the centre of the window, and its own high/low are
        # exactly Pine's low[divPivotLen] / high[divPivotLen].
        candidate = self._window[self._pivot_len] if len(self._window) == self._window.maxlen else None

        # ── Bullish divergence: confirmed RSI pivot LOW ──
        if pl_rsi is not None and candidate is not None:
            p_low = candidate.low
            p_bar = candidate.index
            if self._prev_low_rsi is not None:
                # Lower price low, higher RSI low, the lower RSI coming from oversold.
                if (p_low < self._prev_low_price and pl_rsi > self._prev_low_rsi
                        and min(pl_rsi, self._prev_low_rsi) <= self._oversold):
                    self._last_bull_bar = p_bar
                    events.detected.append(RsiDivergence(
                        is_bullish=True,
                        pivot_bar=p_bar, pivot_price=p_low, pivot_rsi=pl_rsi,
                        prev_bar=self._prev_low_bar, prev_price=self._prev_low_price,
                        prev_rsi=self._prev_low_rsi, id=self._take_id(),
                    ))
            self._prev_low_rsi = pl_rsi
            self._prev_low_price = p_low
            self._prev_low_bar = p_bar

        # ── Bearish divergence: confirmed RSI pivot HIGH ──
        if ph_rsi is not None and candidate is not None:
            p_high = candidate.high
            p_bar = candidate.index
            if self._prev_high_rsi is not None:
                # Higher price high, lower RSI high, the higher RSI coming from overbought.
                if (p_high > self._prev_high_price and ph_rsi < self._prev_high_rsi
                        and max(ph_rsi, self._prev_high_rsi) >= self._overbought):
                    self._last_bear_bar = p_bar
                    events.detected.append(RsiDivergence(
                        is_bullish=False,
                        pivot_bar=p_bar, pivot_price=p_high, pivot_rsi=ph_rsi,
                        prev_bar=self._prev_high_bar, prev_price=self._prev_high_price,
                        prev_rsi=self._prev_high_rsi, id=self._take_id(),
                    ))
            self._prev_high_rsi = ph_rsi
            self._prev_high_price = p_high
            self._prev_high_bar = p_bar

        # ── Live confluence flags (Pine bullDivActive / bearDivActive) ──
        events.bull_active = (self._last_bull_bar is not None
                              and bar_index - self._last_bull_bar <= self._valid_bars)
        events.bear_active = (self._last_bear_bar is not None
                              and bar_index - self._last_bear_bar <= self._valid_bars)
        return events

    # ------------------------------------------------------------------
    # Pivot detection on the RSI series — ta.pivotlow / ta.pivothigh (strict, both sides).
    # ------------------------------------------------------------------
    def _pivot_low_rsi(self) -> Optional[float]:
        cand = self._centred_candidate()
        if cand is None:
            return None
        L = self._pivot_len
        window = self._window
        c = cand.rsi
        for i, b in enumerate(window):
            if i == L:
                continue
            if b.rsi is None or c >= b.rsi:      # strictly lower than every other bar
                return None
        return c

    def _pivot_high_rsi(self) -> Optional[float]:
        cand = self._centred_candidate()
        if cand is None:
            return None
        L = self._pivot_len
        window = self._window
        c = cand.rsi
        for i, b in enumerate(window):
            if i == L:
                continue
            if b.rsi is None or c <= b.rsi:      # strictly higher than every other bar
                return None
        return c

    def _centred_candidate(self) -> Optional[_Bar]:
        """The candidate pivot bar (centre of a full 2·L+1 window) with a defined RSI, else None."""
        if len(self._window) < self._window.maxlen:
            return None
        cand = self._window[self._pivot_len]
        return cand if cand.rsi is not None else None

    def _take_id(self) -> int:
        self._next_id += 1
        return self._next_id
