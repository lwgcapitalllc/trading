"""
equal_highs_lows/engine.py — the Equal Highs/Lows (EQH/EQL) state machine.

One stateful streaming engine, fed one closed bar at a time (index + high/low/close). It maintains
ATR(50) (for the equality tolerance), detects strict price pivots, forms an EQH/EQL when two
consecutive same-side pivots land within tolerance of each other, and mitigates a level when price
CLOSES through it.

Ported line-by-line from indicators/engines/mpc_assistant.pine's "EQUAL HIGHS / LOWS (EQH / EQL)" block
(+ the `GRP_EQ` inputs). The Pine runs, each bar:

  eqAtr = ta.atr(50)
  eqTol = na(eqAtr) ? 0.0 : eqAtr * eqAtrMult            // equality band (ATR × mult)
  eqPh  = ta.pivothigh(high, eqPivotLen, eqPivotLen)     // strict price pivot high, confirmed L late
  eqPl  = ta.pivotlow(low,  eqPivotLen, eqPivotLen)      // strict price pivot low

  on a confirmed pivot high:  if a previous pivot high exists and |eqPh - eqPrevPh| <= eqTol, form an
    EQH at max(eqPh, eqPrevPh), anchored at the previous pivot's bar; FIFO-evict past eqMax. Then latch
    this pivot as the new "previous" (whether or not it formed). (EQL mirrors from the pivot-low side.)

  mitigation each bar: an EQH is removed when close > level; an EQL when close < level. Survivors just
    extend right (a drawing concern this engine drops).

Three Pine details kept exactly, because dropping any would diverge from the chart:

  1. ATR(50) is Wilder's (`ta.rma` of the True Range) — `_Atr`/`_Rma` reproduce `ta.atr` exactly,
     including the first-bar TR = high - low (Pine `ta.tr(true)`) and the na warm-up (tol = 0 until the
     50-bar seed completes, so early levels need EXACTLY-equal pivots).
  2. `ta.pivothigh`/`ta.pivotlow` use a STRICT extreme over the (2·L+1)-bar window centred on the
     candidate (candidate strictly greater/less than every other bar, both sides) — the same semantics
     the validated market_structure and rsi_divergence engines port. The pivot is only known `L` bars
     after the fact; that lag is preserved.
  3. Per-bar ORDER is Pine's: form-EQH → form-EQL → mitigate-EQH → mitigate-EQL. Both formations
     happen before either mitigation, and a level formed this bar is subject to mitigation this bar.

The line/label drawing and the `showEq` toggle are TradingView visuals — this engine always computes
(a consumer that wants it off just ignores the events). Standalone: it needs only high/low/close, no
upstream engine, no volume, no timestamp — a sibling of `fair_value_gaps` and `rsi_divergence`.

Note on the FVG-persistence exemption: the Pine's `f_fvgNearEq` / `eqExemptFvg` lets an FVG sitting
behind an active EQ level survive the FVG cap. That coupling lives on the FVG side; this engine only
publishes the active level prices (`active_eqh` / `active_eql`) a consumer would test against.
"""

from __future__ import annotations

from collections import deque
from typing import Deque, List, Optional

from .types import EqLevel, EqEvents


class _Rma:
    """Wilder's running moving average — an exact port of Pine's `ta.rma(src, length)`.

    Seeds with `ta.sma(src, length)` (mean of the first `length` sources) then recurses
    `rma = alpha*src + (1-alpha)*rma[1]` with `alpha = 1/length`. Returns None until the seed
    completes. (Shared shape with rsi_divergence's `_Rma`; kept local so the engine is self-contained.)
    """

    def __init__(self, length: int) -> None:
        self._length = length
        self._alpha = 1.0 / length
        self._value: Optional[float] = None
        self._seed: List[float] = []
        self._seeded = False

    def update(self, src: float) -> Optional[float]:
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


class _Atr:
    """Streaming ATR — an exact port of Pine's `ta.atr(length)` = `ta.rma(ta.tr(true), length)`.

    True Range on the first bar (no prior close) is `high - low` — Pine's `ta.tr(true)` na-handling.
    Thereafter `max(high-low, |high-close[1]|, |low-close[1]|)`. Returns None until the RMA seed
    completes (bar `length`), matching Pine's na warm-up.
    """

    def __init__(self, length: int) -> None:
        self._rma = _Rma(length)
        self._prev_close: Optional[float] = None

    def update(self, high: float, low: float, close: float) -> Optional[float]:
        if self._prev_close is None:
            tr = high - low
        else:
            tr = max(high - low, abs(high - self._prev_close), abs(low - self._prev_close))
        self._prev_close = close
        return self._rma.update(tr)


class _Bar:
    """One bar's fields the EQ logic needs: absolute index and price extremes."""
    __slots__ = ("index", "high", "low")

    def __init__(self, index: int, high: float, low: float) -> None:
        self.index = index
        self.high = high
        self.low = low


class EqualHighsLowsEngine:
    """Streaming Equal Highs/Lows detector.

    Build one per symbol/timeframe, feed it one closed candle at a time as they close, in order.
    Mirrors mpc_assistant.pine's default `GRP_EQ` settings: pivot width 2, tolerance 0.1×ATR(50),
    up to 6 active levels per side (oldest evicted first).
    """

    def __init__(self, pivot_len: int = 2, atr_mult: float = 0.1, max_levels: int = 6,
                 atr_len: int = 50) -> None:
        self._pivot_len = pivot_len        # Pine eqPivotLen (default 2)
        self._atr_mult = atr_mult          # Pine eqAtrMult (default 0.1)
        self._max_levels = max_levels      # Pine eqMax (default 6, per side)
        self._atr = _Atr(atr_len)          # Pine ta.atr(50)

        # Rolling window of the last (2·pivot_len + 1) bars — enough to test the centred candidate.
        self._window: Deque[_Bar] = deque(maxlen=2 * pivot_len + 1)

        # Previous confirmed pivots (Pine eqPrev* vars) — the anchor a new pivot is compared to.
        self._prev_ph: Optional[float] = None
        self._prev_ph_bar: Optional[int] = None
        self._prev_pl: Optional[float] = None
        self._prev_pl_bar: Optional[int] = None

        # Active levels, oldest→newest (Pine eqhLines/eqhPx and eqlLines/eqlPx, same order).
        self._eqh: List[EqLevel] = []
        self._eql: List[EqLevel] = []

        self._next_id = 0

    # ------------------------------------------------------------------
    def update(self, bar_index: int, high: float, low: float, close: float) -> EqEvents:
        """Feed one closed bar (index + high/low/close). Returns this bar's EQ events + live state."""
        atr = self._atr.update(high, low, close)
        tol = 0.0 if atr is None else atr * self._atr_mult   # Pine eqTol
        self._window.append(_Bar(bar_index, high, low))

        events = EqEvents(tolerance=tol)

        ph = self._pivot_high()   # ta.pivothigh(high, L, L): candidate high or None
        pl = self._pivot_low()    # ta.pivotlow(low,  L, L)
        events.pivot_high = ph
        events.pivot_low = pl

        # The candidate bar is L bars back — the centre of a full window.
        candidate = self._window[self._pivot_len] if len(self._window) == self._window.maxlen else None

        # ── EQH: on a confirmed pivot high ──
        if ph is not None and candidate is not None:
            ph_bar = candidate.index
            if self._prev_ph is not None and abs(ph - self._prev_ph) <= tol:
                level = EqLevel(is_high=True, price=max(ph, self._prev_ph),
                                left_bar=self._prev_ph_bar, formed_bar=bar_index, id=self._take_id())
                self._eqh.append(level)
                events.formed.append(level)
                while len(self._eqh) > self._max_levels:       # FIFO-evict oldest past the cap
                    self._eqh.pop(0)
            self._prev_ph = ph
            self._prev_ph_bar = ph_bar

        # ── EQL: on a confirmed pivot low ──
        if pl is not None and candidate is not None:
            pl_bar = candidate.index
            if self._prev_pl is not None and abs(pl - self._prev_pl) <= tol:
                level = EqLevel(is_high=False, price=min(pl, self._prev_pl),
                                left_bar=self._prev_pl_bar, formed_bar=bar_index, id=self._take_id())
                self._eql.append(level)
                events.formed.append(level)
                while len(self._eql) > self._max_levels:
                    self._eql.pop(0)
            self._prev_pl = pl
            self._prev_pl_bar = pl_bar

        # ── Mitigation: EQH taken on a close ABOVE it, EQL on a close BELOW it ──
        survivors_h: List[EqLevel] = []
        for lvl in self._eqh:
            if close > lvl.price:
                events.mitigated.append(lvl)
            else:
                survivors_h.append(lvl)
        self._eqh = survivors_h

        survivors_l: List[EqLevel] = []
        for lvl in self._eql:
            if close < lvl.price:
                events.mitigated.append(lvl)
            else:
                survivors_l.append(lvl)
        self._eql = survivors_l

        events.active_eqh = [lvl.price for lvl in self._eqh]
        events.active_eql = [lvl.price for lvl in self._eql]
        return events

    # ------------------------------------------------------------------
    # Pivot detection on the price series — ta.pivothigh(high) / ta.pivotlow(low).
    # Pine's `ta.pivothigh` tie semantics (verified on a real XAUUSD export): the
    # centre may EQUAL bars to its LEFT but must be STRICTLY beyond every bar to its
    # RIGHT — so the LAST bar of a run of equal extremes is the pivot. Raw-price ties
    # are common on gold, so this asymmetry matters here (unlike the RSI engine, where
    # ties to ~1e-14 are rare). Reject the candidate if any LEFT bar is strictly higher
    # or any RIGHT bar is >= it (mirror for lows).
    # ------------------------------------------------------------------
    def _pivot_high(self) -> Optional[float]:
        if len(self._window) < self._window.maxlen:
            return None
        L = self._pivot_len
        c = self._window[L].high
        for i, b in enumerate(self._window):
            if i < L:
                if b.high > c:               # left: an equal high is allowed, a higher one disqualifies
                    return None
            elif i > L:
                if b.high >= c:              # right: an equal (or higher) bar disqualifies — later bar wins ties
                    return None
        return c

    def _pivot_low(self) -> Optional[float]:
        if len(self._window) < self._window.maxlen:
            return None
        L = self._pivot_len
        c = self._window[L].low
        for i, b in enumerate(self._window):
            if i < L:
                if b.low < c:                # left: an equal low is allowed, a lower one disqualifies
                    return None
            elif i > L:
                if b.low <= c:               # right: an equal (or lower) bar disqualifies — later bar wins ties
                    return None
        return c

    def _take_id(self) -> int:
        self._next_id += 1
        return self._next_id
