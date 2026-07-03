"""
market_structure/engine.py — StructureEngine: stateful port of indicators/structure_engine.pine.

This is a line-by-line port of the Pine v6 `SMCStructure` type (external structure) and the
i_-prefixed internal-structure state machine. See MARKET_STRUCTURE_ENGINE.md for the plain-English
algorithm explanation and CLAUDE.md for why this is a stateful class rather than the stateless
df -> label pattern used by regime/.

Porting rules followed throughout:
  - A "break" is a body close beyond the active level (close > ash / close < asl), never a wick touch.
  - ta.pivothigh(high, L, L) / ta.pivotlow(low, L, L) is only known L bars after the fact — that lag
    is preserved via a rolling bar buffer, not optimized away.
  - Every branch, field mutation, and reset in the Pine source is preserved even where it looks
    redundant or odd. Anything that looked like a possible bug in the source is flagged with a
    `# NOTE:` comment rather than silently fixed.

No pandas/numpy import in the update() hot path — replay() imports pandas lazily and only if the
caller passes a DataFrame.
"""

from __future__ import annotations

from collections import deque
from typing import Iterable, List, Optional, Union

from .types import Bar, ExternalEvents, InternalEvents, StructureEvents, SwingLevel

# Pine: max_bars_back = 2000 (indicator-level buffer bound)
_MAX_BARS_BACK = 2000
# Pine: int lb = math.min(bar_index, 500)  (seeding scan bound)
_SEED_SCAN_BOUND = 500
# Pine: int max_lb = math.min(math.min(bars_back, 1490), bar_index)  (post-break rescan bound)
_RESCAN_BOUND = 1490


class _ExternalState:
    """Mirrors the Pine `SMCStructure` type's non-drawing fields exactly (one instance = one `st`)."""

    def __init__(self, length: int):
        self.length = length

        self.ash: Optional[float] = None
        self.ash_loc: Optional[int] = None
        self.ash_type: str = ""  # "" or "LOCKED"

        self.asl: Optional[float] = None
        self.asl_loc: Optional[int] = None
        self.asl_type: str = ""

        self.last_conf_high: Optional[float] = None
        self.last_conf_high_loc: Optional[int] = None
        self.last_conf_low: Optional[float] = None
        self.last_conf_low_loc: Optional[int] = None

        self.dir: int = 0
        self.choch_lock: bool = False

        self.pb_mode: int = 0
        self.pb_count: int = 0
        self.pb_extreme: Optional[float] = None
        self.pb_extreme_loc: Optional[int] = None
        self.pb_started: bool = False
        self.pb_last_qualify_close: Optional[float] = None
        self.pb_last_qualify_high: Optional[float] = None

        self.prev_close: Optional[float] = None
        self.prev_high: Optional[float] = None
        self.prev_low: Optional[float] = None

        self.seeded: bool = False

        # Per-bar break outputs (reset at the top of process(), mirrors st.bull_bos etc.)
        self.bull_bos: bool = False
        self.bull_bos_price: Optional[float] = None
        self.bear_bos: bool = False
        self.bear_bos_price: Optional[float] = None
        self.bull_sos: bool = False
        self.bear_sos: bool = False

        # Full break-leg endpoints (Pine st.bull_bos_high/h_loc/low/l_loc + bear mirror). Set on
        # the break bar in _on_ash_broken/_on_asl_broken, reset each bar like the other break
        # outputs. Needed by the Sniper-fib anchor. See types.ExternalEvents for semantics.
        self.bull_bos_high: Optional[float] = None
        self.bull_bos_h_loc: Optional[int] = None
        self.bull_bos_low: Optional[float] = None
        self.bull_bos_l_loc: Optional[int] = None
        self.bear_bos_high: Optional[float] = None
        self.bear_bos_h_loc: Optional[int] = None
        self.bear_bos_low: Optional[float] = None
        self.bear_bos_l_loc: Optional[int] = None

        self.new_swing_high: bool = False
        self.new_swing_high_price: Optional[float] = None
        self.new_swing_high_index: Optional[int] = None
        self.new_swing_low: bool = False
        self.new_swing_low_price: Optional[float] = None
        self.new_swing_low_index: Optional[int] = None

        self.unconfirmed_high_set: bool = False
        self.unconfirmed_high_price: Optional[float] = None
        self.unconfirmed_high_index: Optional[int] = None
        self.unconfirmed_low_set: bool = False
        self.unconfirmed_low_price: Optional[float] = None
        self.unconfirmed_low_index: Optional[int] = None

        # Per-bar label outputs (numeric equivalents of the Pine label text)
        self.broken_high_label: Optional[str] = None
        self.broken_high_price: Optional[float] = None
        self.broken_high_index: Optional[int] = None
        self.broken_low_label: Optional[str] = None
        self.broken_low_price: Optional[float] = None
        self.broken_low_index: Optional[int] = None


class _InternalState:
    """Mirrors the i_-prefixed internal-structure vars exactly."""

    def __init__(self):
        self.mode: int = 0
        self.seeded: bool = False

        self.pb_extreme: Optional[float] = None
        self.pb_extreme_loc: Optional[int] = None
        self.pb_count: int = 0
        self.pb_started: bool = False
        self.pb_lqc: Optional[float] = None  # last-qualify-close
        self.pb_lqh: Optional[float] = None  # last-qualify-high/low
        self.prev_high: Optional[float] = None
        self.prev_low: Optional[float] = None

        self.sw_price: Optional[float] = None
        self.sw_loc: Optional[int] = None
        self.sw_locked: bool = False  # tracks whether the active i_sw_* came from pullback confirmation

        self.tracked_ext: Optional[float] = None
        self.tracked_ext_loc: Optional[int] = None
        self.last_mode: int = 0
        self.had_bos: bool = False
        self.bos_dir: int = 0

        self.last_hl: Optional[float] = None
        self.last_hl_loc: Optional[int] = None
        self.last_lh: Optional[float] = None
        self.last_lh_loc: Optional[int] = None

        self.sos_watch_hh: Optional[float] = None
        self.sos_watch_hh_loc: Optional[int] = None
        self.sos_watch_ll: Optional[float] = None
        self.sos_watch_ll_loc: Optional[int] = None


class StructureEngine:
    """
    Streaming port of indicators/structure_engine.pine.

    Call update(bar) once per closed candle, in ascending bar order. State (active swing,
    pullback counters, trend direction) carries forward between calls — this is a state machine,
    not a pure function. See CLAUDE.md for why.
    """

    def __init__(self, major_length: int = 15):
        self.major_length = major_length

        # Rolling OHLC history, bounded like the Pine indicator's max_bars_back=2000.
        # Also used for the pivot detector and the bounded backward scans.
        self._bars: deque = deque(maxlen=_MAX_BARS_BACK)
        # index -> position-in-_bars lookup is unnecessary; we always append in order and the
        # deque's rightmost element is bar_index. We keep a separate index counter since callers
        # may not supply bar.index (replay() assigns sequential indices when absent).
        self._next_index: int = 0

        self._ext = _ExternalState(major_length)
        self._int = _InternalState()

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def update(self, bar: Bar) -> StructureEvents:
        """Process one new bar. Call once per closed candle, in order. Returns what fired on this bar."""
        self._bars.append(bar)
        self._next_index = bar.index + 1

        ph_val, pl_val = self._pivot_at_current_bar()

        ext_events = self._process_external(bar, ph_val, pl_val)
        int_events = self._process_internal(bar)

        return StructureEvents(external=ext_events, internal=int_events)

    def replay(self, bars) -> List[StructureEvents]:
        """
        Convenience for backtesting: bars can be an iterable of Bar, an iterable of dicts with
        open/high/low/close(/index) keys, or (if pandas is installed) a DataFrame with those
        columns. Feeds them through update() in order and returns the full per-bar event list.
        """
        try:
            import pandas as pd
            _PANDAS = True
        except ImportError:
            pd = None
            _PANDAS = False

        results: List[StructureEvents] = []

        if _PANDAS and isinstance(bars, pd.DataFrame):
            for i, (_, row) in enumerate(bars.iterrows()):
                idx = int(row["index"]) if "index" in row else i
                b = Bar(
                    index=idx,
                    open=float(row["open"]),
                    high=float(row["high"]),
                    low=float(row["low"]),
                    close=float(row["close"]),
                )
                results.append(self.update(b))
            return results

        for i, item in enumerate(bars):
            if isinstance(item, Bar):
                b = item
            elif isinstance(item, dict):
                idx = int(item["index"]) if "index" in item else i
                b = Bar(
                    index=idx,
                    open=float(item["open"]),
                    high=float(item["high"]),
                    low=float(item["low"]),
                    close=float(item["close"]),
                )
            else:
                raise TypeError(
                    f"replay() bars must be Bar, dict, or DataFrame rows; got {type(item)!r}"
                )
            results.append(self.update(b))

        return results

    # ------------------------------------------------------------------
    # Current-state read properties
    # ------------------------------------------------------------------

    @property
    def dir(self) -> int:
        """External trend: 1 bullish, -1 bearish, 0 undetermined."""
        return self._ext.dir

    @property
    def active_swing_high(self) -> Optional[SwingLevel]:
        if self._ext.ash is None:
            return None
        return SwingLevel(price=self._ext.ash, index=self._ext.ash_loc, locked=self._ext.ash_type == "LOCKED")

    @property
    def active_swing_low(self) -> Optional[SwingLevel]:
        if self._ext.asl is None:
            return None
        return SwingLevel(price=self._ext.asl, index=self._ext.asl_loc, locked=self._ext.asl_type == "LOCKED")

    @property
    def last_confirmed_high(self) -> Optional[SwingLevel]:
        if self._ext.last_conf_high is None:
            return None
        return SwingLevel(price=self._ext.last_conf_high, index=self._ext.last_conf_high_loc, locked=True)

    @property
    def last_confirmed_low(self) -> Optional[SwingLevel]:
        if self._ext.last_conf_low is None:
            return None
        return SwingLevel(price=self._ext.last_conf_low, index=self._ext.last_conf_low_loc, locked=True)

    @property
    def internal_mode(self) -> int:
        """Internal trend/tracking mode: 1 tracking up (seeking iSH), -1 tracking down (seeking iSL), 0 idle/watching."""
        return self._int.mode

    @property
    def internal_swing(self) -> Optional[SwingLevel]:
        if self._int.sw_price is None:
            return None
        return SwingLevel(price=self._int.sw_price, index=self._int.sw_loc, locked=self._int.sw_locked)

    # ------------------------------------------------------------------
    # Pivot detection — ta.pivothigh(high, L, L) / ta.pivotlow(low, L, L)
    # ------------------------------------------------------------------

    def _pivot_at_current_bar(self):
        """
        Returns (ph_val, pl_val) for the *current* bar, exactly mirroring
        ta.pivothigh(high, majorLength, majorLength) / ta.pivotlow(low, majorLength, majorLength).

        The candidate pivot bar is `majorLength` bars behind the current bar. It qualifies as a
        pivot high iff its high is strictly greater than the highs of the majorLength bars before
        it AND the majorLength bars after it (current bar included as the last "after" bar) — i.e.
        it is the unique local extreme in a (2*majorLength + 1)-bar window centered on it. Mirrors
        for pivot low with "low" and "strictly less than".

        This is only resolvable once majorLength bars have elapsed since the candidate — the same
        lag Pine has, preserved here rather than optimized away.
        """
        L = self.major_length
        n = len(self._bars)
        if n < 2 * L + 1:
            return None, None

        # self._bars[-1] is the current bar; the candidate pivot bar is L bars before it.
        window = list(self._bars)[n - (2 * L + 1):n]
        candidate = window[L]  # centered element
        left = window[:L]
        right = window[L + 1:]

        ph_val = None
        if all(candidate.high > b.high for b in left) and all(candidate.high > b.high for b in right):
            ph_val = candidate.high

        pl_val = None
        if all(candidate.low < b.low for b in left) and all(candidate.low < b.low for b in right):
            pl_val = candidate.low

        return ph_val, pl_val

    def _bar_index_minus(self, offset: int) -> Optional[float]:
        """Mirrors low[i] / high[i] / close[i] — value `offset` bars before the current bar. None if out of buffer."""
        n = len(self._bars)
        pos = n - 1 - offset
        if pos < 0:
            return None
        return self._bars[pos]

    # ------------------------------------------------------------------
    # External structure — port of `method process(SMCStructure st, ...)`
    # ------------------------------------------------------------------

    def _process_external(self, bar: Bar, ph_val: Optional[float], pl_val: Optional[float]) -> ExternalEvents:
        st = self._ext
        close, high, low, open_ = bar.close, bar.high, bar.low, bar.open
        bar_index = bar.index

        # Reset per-bar flags (Pine lines 120-125)
        st.bull_bos = False
        st.bull_bos_price = None
        st.bear_bos = False
        st.bear_bos_price = None
        st.bull_sos = False
        st.bear_sos = False
        st.bull_bos_high = None
        st.bull_bos_h_loc = None
        st.bull_bos_low = None
        st.bull_bos_l_loc = None
        st.bear_bos_high = None
        st.bear_bos_h_loc = None
        st.bear_bos_low = None
        st.bear_bos_l_loc = None
        st.new_swing_high = False
        st.new_swing_high_price = None
        st.new_swing_high_index = None
        st.new_swing_low = False
        st.new_swing_low_price = None
        st.new_swing_low_index = None
        st.unconfirmed_high_set = False
        st.unconfirmed_high_price = None
        st.unconfirmed_high_index = None
        st.unconfirmed_low_set = False
        st.unconfirmed_low_price = None
        st.unconfirmed_low_index = None
        st.broken_high_label = None
        st.broken_high_price = None
        st.broken_high_index = None
        st.broken_low_label = None
        st.broken_low_price = None
        st.broken_low_index = None

        is_inside = False
        if st.prev_high is not None and st.prev_low is not None:
            is_inside = high < st.prev_high and low > st.prev_low

        # choch_lock release (lines 131-135)
        if st.choch_lock:
            if st.dir == 1 and pl_val is not None:
                st.choch_lock = False
            elif st.dir == -1 and ph_val is not None:
                st.choch_lock = False

        # ── Pullback mode 1: tracking up toward a new ASH (lines 137-177) ──
        if st.pb_mode == 1:
            if not st.pb_started:
                st.pb_started = True
                st.pb_extreme = high
                st.pb_extreme_loc = bar_index
                st.pb_count = 0
                st.pb_last_qualify_close = None
                st.pb_last_qualify_high = None
            else:
                extreme_updated_1 = False
                if st.pb_extreme is None or high > st.pb_extreme:
                    st.pb_extreme = high
                    st.pb_extreme_loc = bar_index
                    st.pb_count = 0
                    st.pb_last_qualify_close = None
                    st.pb_last_qualify_high = None
                    extreme_updated_1 = True
                extreme_is_bearish_1 = extreme_updated_1 and close < open_
                is_candle1_1 = st.pb_last_qualify_close is None and not extreme_updated_1
                if (not is_inside or is_candle1_1) and (not extreme_updated_1 or extreme_is_bearish_1):
                    threshold = st.pb_extreme if st.pb_last_qualify_high is None else st.pb_last_qualify_high
                    if close < threshold:  # pbBuffer == 0.0
                        st.pb_count += 1
                        st.pb_last_qualify_close = close
                        st.pb_last_qualify_high = low
                if st.pb_count >= 3 and st.pb_extreme is not None and st.pb_extreme_loc is not None:
                    st.ash = st.pb_extreme
                    st.ash_loc = st.pb_extreme_loc
                    st.ash_type = "LOCKED"
                    st.new_swing_high = True
                    st.new_swing_high_price = st.ash
                    st.new_swing_high_index = st.ash_loc
                    st.pb_mode = 0
                    st.pb_count = 0
                    st.choch_lock = False

        # ── Pullback mode -1: tracking down toward a new ASL (lines 179-219) ──
        elif st.pb_mode == -1:
            if not st.pb_started:
                st.pb_started = True
                st.pb_extreme = low
                st.pb_extreme_loc = bar_index
                st.pb_count = 0
                st.pb_last_qualify_close = None
                st.pb_last_qualify_high = None
            else:
                extreme_updated_m1 = False
                if st.pb_extreme is None or low < st.pb_extreme:
                    st.pb_extreme = low
                    st.pb_extreme_loc = bar_index
                    st.pb_count = 0
                    st.pb_last_qualify_close = None
                    st.pb_last_qualify_high = None
                    extreme_updated_m1 = True
                extreme_is_bullish_m1 = extreme_updated_m1 and close > open_
                is_candle1_m1 = st.pb_last_qualify_close is None and not extreme_updated_m1
                if (not is_inside or is_candle1_m1) and (not extreme_updated_m1 or extreme_is_bullish_m1):
                    threshold = st.pb_extreme if st.pb_last_qualify_high is None else st.pb_last_qualify_high
                    if close > threshold:  # pbBuffer == 0.0
                        st.pb_count += 1
                        st.pb_last_qualify_close = close
                        st.pb_last_qualify_high = high
                if st.pb_count >= 3 and st.pb_extreme is not None and st.pb_extreme_loc is not None:
                    st.asl = st.pb_extreme
                    st.asl_loc = st.pb_extreme_loc
                    st.asl_type = "LOCKED"
                    st.new_swing_low = True
                    st.new_swing_low_price = st.asl
                    st.new_swing_low_index = st.asl_loc
                    st.pb_mode = 0
                    st.pb_count = 0
                    st.choch_lock = False

        st.prev_close = close
        st.prev_high = high
        st.prev_low = low

        # ── Initial seed from a pivot (lines 225-231) ──
        if st.ash is None and st.asl is None and not st.seeded:
            if ph_val is not None:
                st.ash = ph_val
                st.ash_loc = bar_index - st.length
                st.ash_type = ""
                st.dir = -1
                st.unconfirmed_high_set = True
                st.unconfirmed_high_price = st.ash
                st.unconfirmed_high_index = st.ash_loc
            elif pl_val is not None:
                st.asl = pl_val
                st.asl_loc = bar_index - st.length
                st.asl_type = ""
                st.dir = 1
                st.unconfirmed_low_set = True
                st.unconfirmed_low_price = st.asl
                st.unconfirmed_low_index = st.asl_loc

        # ── Bootstrap the opposite side via bounded backward scan (lines 233-265) ──
        if not st.seeded:
            if st.ash is not None and st.asl is None:
                seed_low = low
                seed_loc = bar_index
                lb = min(bar_index, _SEED_SCAN_BOUND)
                for i in range(0, lb + 1):
                    b = self._bar_index_minus(i)
                    if b is not None and b.low < seed_low:
                        seed_low = b.low
                        seed_loc = bar_index - i
                if seed_low < st.ash:
                    st.asl = seed_low
                    st.asl_loc = seed_loc
                    st.asl_type = ""
                    st.seeded = True
                    st.unconfirmed_low_set = True
                    st.unconfirmed_low_price = st.asl
                    st.unconfirmed_low_index = st.asl_loc
            elif st.asl is not None and st.ash is None:
                seed_high = high
                seed_loc = bar_index
                lb = min(bar_index, _SEED_SCAN_BOUND)
                for i in range(0, lb + 1):
                    b = self._bar_index_minus(i)
                    if b is not None and b.high > seed_high:
                        seed_high = b.high
                        seed_loc = bar_index - i
                if seed_high > st.asl:
                    st.ash = seed_high
                    st.ash_loc = seed_loc
                    st.ash_type = ""
                    st.seeded = True
                    st.unconfirmed_high_set = True
                    st.unconfirmed_high_price = st.ash
                    st.unconfirmed_high_index = st.ash_loc
            elif st.ash is not None and st.asl is not None:
                st.seeded = True

        # ── Let ash/asl float to a bigger unconfirmed pivot before any break has occurred (lines 267-273) ──
        if st.last_conf_high is None and st.last_conf_low is None:
            if ph_val is not None and st.ash is not None and st.ash_type == "" and st.pb_mode == 0:
                if ph_val > st.ash:
                    st.ash = ph_val
                    st.ash_loc = bar_index - st.length
                    st.ash_type = ""
                    st.unconfirmed_high_set = True
                    st.unconfirmed_high_price = st.ash
                    st.unconfirmed_high_index = st.ash_loc
            if pl_val is not None and st.asl is not None and st.asl_type == "" and st.pb_mode == 0:
                if pl_val < st.asl:
                    st.asl = pl_val
                    st.asl_loc = bar_index - st.length
                    st.asl_type = ""
                    st.unconfirmed_low_set = True
                    st.unconfirmed_low_price = st.asl
                    st.unconfirmed_low_index = st.asl_loc

        ash_broken = st.ash is not None and close > st.ash
        asl_broken = st.asl is not None and close < st.asl

        if ash_broken:
            self._on_ash_broken(st, bar)
        elif asl_broken:
            self._on_asl_broken(st, bar)

        events = ExternalEvents(
            bull_bos=st.bull_bos,
            bull_bos_price=st.bull_bos_price,
            bull_sos=st.bull_sos,
            bear_bos=st.bear_bos,
            bear_bos_price=st.bear_bos_price,
            bear_sos=st.bear_sos,
            bull_bos_high=st.bull_bos_high,
            bull_bos_h_loc=st.bull_bos_h_loc,
            bull_bos_low=st.bull_bos_low,
            bull_bos_l_loc=st.bull_bos_l_loc,
            bear_bos_high=st.bear_bos_high,
            bear_bos_h_loc=st.bear_bos_h_loc,
            bear_bos_low=st.bear_bos_low,
            bear_bos_l_loc=st.bear_bos_l_loc,
            new_swing_high=st.new_swing_high,
            new_swing_high_price=st.new_swing_high_price,
            new_swing_high_index=st.new_swing_high_index,
            new_swing_low=st.new_swing_low,
            new_swing_low_price=st.new_swing_low_price,
            new_swing_low_index=st.new_swing_low_index,
            unconfirmed_high_set=st.unconfirmed_high_set,
            unconfirmed_high_price=st.unconfirmed_high_price,
            unconfirmed_high_index=st.unconfirmed_high_index,
            unconfirmed_low_set=st.unconfirmed_low_set,
            unconfirmed_low_price=st.unconfirmed_low_price,
            unconfirmed_low_index=st.unconfirmed_low_index,
            broken_high_label=st.broken_high_label,
            broken_high_price=st.broken_high_price,
            broken_high_index=st.broken_high_index,
            broken_low_label=st.broken_low_label,
            broken_low_price=st.broken_low_price,
            broken_low_index=st.broken_low_index,
        )
        return events

    def _on_ash_broken(self, st: _ExternalState, bar: Bar) -> None:
        """Port of Pine lines 278-397 (the `if ash_broken` branch)."""
        bar_index = bar.index
        st.bull_bos = True
        st.bull_bos_price = st.ash
        st.bull_bos_high = st.ash          # Pine: st.bull_bos_high  := st.ash
        st.bull_bos_h_loc = st.ash_loc     # Pine: st.bull_bos_h_loc := st.ash_loc

        was_in_bear_pb = st.pb_mode == -1 and st.pb_extreme is not None and st.pb_extreme_loc is not None
        st.pb_mode = 0
        st.pb_count = 0

        is_choch = st.dir == -1 and not st.choch_lock
        if is_choch:
            st.bull_sos = True
        if is_choch:
            st.choch_lock = True

        brk_already_conf_high = (st.ash == st.last_conf_high and st.ash_loc == st.last_conf_high_loc)
        if not brk_already_conf_high:
            brk_is_hh = st.last_conf_high is None or st.ash >= st.last_conf_high
            st.broken_high_label = "HH" if brk_is_hh else "LH"
            st.broken_high_price = st.ash
            st.broken_high_index = st.ash_loc

        st.last_conf_high = st.ash
        st.last_conf_high_loc = st.ash_loc
        st.ash = None
        st.dir = 1

        if was_in_bear_pb:
            # Immediate promotion of an in-progress (possibly <3-candle) bearish pullback.
            # Pine LOCKS a new ASL here and draws its line + HL/LL label (broken_low_label
            # below), but it does NOT set st.new_swing_low — that flag is reserved for the
            # 3-candle pullback-confirm block only (Pine line 216). new_swing_low is what seeds
            # the internal engine, and Pine deliberately never seeds internal off a
            # break-promotion swing. Setting it here diverged from Pine (validated on the
            # XAUUSD-15m export at bar 1947) — so it is intentionally not set.
            st.bull_bos_low = st.pb_extreme        # Pine: st.bull_bos_low  := st.pb_extreme
            st.bull_bos_l_loc = st.pb_extreme_loc  # Pine: st.bull_bos_l_loc := st.pb_extreme_loc

            pb_is_hl = False if is_choch else (st.last_conf_low is None or st.pb_extreme >= st.last_conf_low)
            st.broken_low_label = "HL" if pb_is_hl else "LL"
            st.broken_low_price = st.pb_extreme
            st.broken_low_index = st.pb_extreme_loc

            st.asl = st.pb_extreme
            st.asl_loc = st.pb_extreme_loc
            st.asl_type = "LOCKED"
            st.last_conf_low = st.pb_extreme
            st.last_conf_low_loc = st.pb_extreme_loc

            st.pb_extreme = bar.high
            st.pb_extreme_loc = bar_index
            st.pb_last_qualify_close = None
            st.pb_last_qualify_high = None
            st.pb_started = True
            st.pb_count = 0
            st.pb_mode = 1
        else:
            if st.asl is not None:
                already_conf_low = (st.asl == st.last_conf_low and st.asl_loc == st.last_conf_low_loc)
                if not already_conf_low:
                    old_is_hl = False if is_choch else (st.last_conf_low is None or st.asl >= st.last_conf_low)
                    st.broken_low_label = "HL" if old_is_hl else "LL"
                    st.broken_low_price = st.asl
                    st.broken_low_index = st.asl_loc
                    st.last_conf_low = st.asl
                    st.last_conf_low_loc = st.asl_loc
                st.asl = None

            lowest_val = bar.low
            lowest_loc = bar_index
            bars_back = bar_index if st.last_conf_high_loc is None else bar_index - st.last_conf_high_loc
            if bars_back > 0:
                max_lb = min(min(bars_back, _RESCAN_BOUND), bar_index)
                for i in range(0, max_lb + 1):
                    b = self._bar_index_minus(i)
                    if b is not None and b.low < lowest_val:
                        lowest_val = b.low
                        lowest_loc = bar_index - i

            st.bull_bos_low = lowest_val       # Pine: st.bull_bos_low  := lowest_val
            st.bull_bos_l_loc = lowest_loc     # Pine: st.bull_bos_l_loc := lowest_loc

            st.asl = lowest_val
            st.asl_loc = lowest_loc
            st.asl_type = ""
            st.unconfirmed_low_set = True
            st.unconfirmed_low_price = lowest_val
            st.unconfirmed_low_index = lowest_loc

            st.pb_mode = 1
            st.pb_count = 0
            st.pb_extreme = bar.high
            st.pb_extreme_loc = bar_index
            st.pb_last_qualify_close = None
            st.pb_last_qualify_high = None
            st.pb_started = True

    def _on_asl_broken(self, st: _ExternalState, bar: Bar) -> None:
        """Port of Pine lines 399-517 (the `else if asl_broken` branch). Mirror image of _on_ash_broken."""
        bar_index = bar.index
        st.bear_bos = True
        st.bear_bos_price = st.asl
        st.bear_bos_low = st.asl           # Pine: st.bear_bos_low  := st.asl
        st.bear_bos_l_loc = st.asl_loc     # Pine: st.bear_bos_l_loc := st.asl_loc

        was_in_bull_pb = st.pb_mode == 1 and st.pb_extreme is not None and st.pb_extreme_loc is not None
        st.pb_mode = 0
        st.pb_count = 0

        is_choch = st.dir == 1 and not st.choch_lock
        if is_choch:
            st.bear_sos = True
        if is_choch:
            st.choch_lock = True

        brk_already_conf_low = (st.asl == st.last_conf_low and st.asl_loc == st.last_conf_low_loc)
        if not brk_already_conf_low:
            brk_is_hl = st.last_conf_low is None or st.asl >= st.last_conf_low
            st.broken_low_label = "HL" if brk_is_hl else "LL"
            st.broken_low_price = st.asl
            st.broken_low_index = st.asl_loc

        st.last_conf_low = st.asl
        st.last_conf_low_loc = st.asl_loc
        st.asl = None
        st.dir = -1

        if was_in_bull_pb:
            # Immediate promotion of an in-progress (possibly <3-candle) bullish pullback.
            # Pine LOCKS a new ASH here and draws its line + HH/LH label (broken_high_label
            # below), but it does NOT set st.new_swing_high — that flag is reserved for the
            # 3-candle pullback-confirm block only (Pine line 174). new_swing_high is what seeds
            # the internal engine, and Pine deliberately never seeds internal off a
            # break-promotion swing. Setting it here diverged from Pine (validated on the
            # XAUUSD-15m export) — so it is intentionally not set. Mirror of _on_ash_broken.
            st.bear_bos_high = st.pb_extreme       # Pine: st.bear_bos_high  := st.pb_extreme
            st.bear_bos_h_loc = st.pb_extreme_loc  # Pine: st.bear_bos_h_loc := st.pb_extreme_loc

            pb_is_hh = st.last_conf_high is None or st.pb_extreme >= st.last_conf_high
            st.broken_high_label = "HH" if pb_is_hh else "LH"
            st.broken_high_price = st.pb_extreme
            st.broken_high_index = st.pb_extreme_loc

            st.ash = st.pb_extreme
            st.ash_loc = st.pb_extreme_loc
            st.ash_type = "LOCKED"
            st.last_conf_high = st.pb_extreme
            st.last_conf_high_loc = st.pb_extreme_loc

            st.pb_extreme = bar.low
            st.pb_extreme_loc = bar_index
            st.pb_last_qualify_close = None
            st.pb_last_qualify_high = None
            st.pb_started = True
            st.pb_count = 0
            st.pb_mode = -1
        else:
            if st.ash is not None:
                already_conf_high = (st.ash == st.last_conf_high and st.ash_loc == st.last_conf_high_loc)
                if not already_conf_high:
                    # NOTE: Pine hardcodes old_is_hh = true when is_choch (line 470), asymmetric
                    # with the mirror-image branch in _on_ash_broken (which hardcodes False for
                    # old_is_hl when is_choch). Ported faithfully — not "fixed" to be symmetric.
                    old_is_hh = True if is_choch else (st.last_conf_high is None or st.ash >= st.last_conf_high)
                    st.broken_high_label = "HH" if old_is_hh else "LH"
                    st.broken_high_price = st.ash
                    st.broken_high_index = st.ash_loc
                    st.last_conf_high = st.ash
                    st.last_conf_high_loc = st.ash_loc
                st.ash = None

            highest_val = bar.high
            highest_loc = bar_index
            bars_back = bar_index if st.last_conf_low_loc is None else bar_index - st.last_conf_low_loc
            if bars_back > 0:
                max_lb = min(min(bars_back, _RESCAN_BOUND), bar_index)
                for i in range(0, max_lb + 1):
                    b = self._bar_index_minus(i)
                    if b is not None and b.high > highest_val:
                        highest_val = b.high
                        highest_loc = bar_index - i

            st.bear_bos_high = highest_val     # Pine: st.bear_bos_high  := highest_val
            st.bear_bos_h_loc = highest_loc    # Pine: st.bear_bos_h_loc := highest_loc

            st.ash = highest_val
            st.ash_loc = highest_loc
            st.ash_type = ""
            st.unconfirmed_high_set = True
            st.unconfirmed_high_price = highest_val
            st.unconfirmed_high_index = highest_loc

            st.pb_mode = -1
            st.pb_count = 0
            st.pb_extreme = bar.low
            st.pb_extreme_loc = bar_index
            st.pb_last_qualify_close = None
            st.pb_last_qualify_high = None
            st.pb_started = True

    # ------------------------------------------------------------------
    # Internal structure — port of the i_-prefixed state machine (lines 539-937)
    # ------------------------------------------------------------------

    def _process_internal(self, bar: Bar) -> InternalEvents:
        ist = self._int
        st = self._ext  # to read st.new_swing_low / st.new_swing_high / st.bull_sos / st.bear_sos
        close, high, low, open_ = bar.close, bar.high, bar.low, bar.open
        bar_index = bar.index

        events = InternalEvents()

        # ── Stop internal tracking on external SOS (lines 590-606) ──
        if st.bull_sos or st.bear_sos:
            ist.sw_price = None
            ist.sw_loc = None
            ist.sw_locked = False
            ist.mode = 0
            ist.seeded = False
            ist.pb_count = 0
            ist.pb_started = False
            ist.tracked_ext = None
            ist.tracked_ext_loc = None
            ist.last_hl = None
            ist.last_lh = None
            ist.had_bos = False
            ist.sos_watch_hh = None
            ist.sos_watch_ll = None

        # ── Track prev bar (lines 609-611) ──
        ist.prev_high = high
        ist.prev_low = low

        # ── Seed on new external swing (lines 615-649) ──
        if st.new_swing_low and not st.bull_sos and not st.bear_sos:
            ist.mode = 1
            ist.seeded = True
            ist.had_bos = False
            ist.bos_dir = 0
            ist.pb_started = False
            ist.pb_extreme = None
            ist.pb_count = 0
            ist.pb_lqc = None
            ist.pb_lqh = None
            ist.tracked_ext = None
            ist.tracked_ext_loc = None
            ist.last_mode = 1
            ist.last_hl = None
            ist.last_lh = None
            ist.sos_watch_hh = None
            ist.sos_watch_ll = None
        elif st.new_swing_high and not st.bull_sos and not st.bear_sos:
            ist.mode = -1
            ist.seeded = True
            ist.had_bos = False
            ist.bos_dir = 0
            ist.pb_started = False
            ist.pb_extreme = None
            ist.pb_count = 0
            ist.pb_lqc = None
            ist.pb_lqh = None
            ist.tracked_ext = None
            ist.tracked_ext_loc = None
            ist.last_mode = -1
            ist.last_hl = None
            ist.last_lh = None
            ist.sos_watch_hh = None
            ist.sos_watch_ll = None

        # NOTE: this re-reads ist.prev_high/prev_low that were just set to THIS bar's high/low
        # above (lines 609-611 run every bar, before the is_inside checks below use them) —
        # ported faithfully from the Pine source's execution order, which means is_inside always
        # evaluates False on the bar it's computed (prev == current). Preserved as written.

        # ── Mode 1: track upward move → confirm iSH (lines 652-695) ──
        if ist.seeded and ist.mode == 1:
            if not ist.pb_started:
                ist.pb_started = True
                ist.pb_extreme = high
                ist.pb_extreme_loc = bar_index
                ist.pb_count = 0
                ist.pb_lqc = None
                ist.pb_lqh = None
            else:
                ext_chg = False
                if ist.pb_extreme is not None and high > ist.pb_extreme:
                    ist.pb_extreme = high
                    ist.pb_extreme_loc = bar_index
                    ist.pb_count = 0
                    ist.pb_lqc = None
                    ist.pb_lqh = None
                    ext_chg = True
                is_inside = (
                    ist.prev_high is not None and ist.prev_low is not None
                    and high < ist.prev_high and low > ist.prev_low
                )
                ext_dir = ext_chg and close < open_
                is_c1 = ist.pb_lqc is None and not ext_chg
                if (not is_inside or is_c1) and (not ext_chg or ext_dir):
                    thresh = ist.pb_extreme if ist.pb_lqh is None else ist.pb_lqh
                    if close < thresh:  # pbBuffer == 0.0
                        ist.pb_count += 1
                        ist.pb_lqc = close
                        ist.pb_lqh = low
                if ist.pb_count >= 3 and ist.pb_extreme is not None:
                    ist.sw_price = ist.pb_extreme
                    ist.sw_loc = ist.pb_extreme_loc
                    ist.sw_locked = True
                    # NOTE: Pine's comment at this site says "iHH if higher than last, iLH if
                    # lower" but the actual code (line 689: i_h_lbl := not i_had_bos ? "iSH" :
                    # "iHH") never compares against the previous internal high — it always labels
                    # "iHH" once i_had_bos is true, never "iLH". Ported exactly as written, not
                    # as commented.
                    events.swing_high_label = "iSH" if not ist.had_bos else "iHH"
                    events.new_swing_high = True
                    events.new_swing_high_price = ist.sw_price
                    events.new_swing_high_index = ist.sw_loc
                    ist.mode = 0
                    ist.pb_count = 0
                    ist.pb_started = False

        # ── Mode -1: track downward move → confirm iSL (lines 698-741) ──
        elif ist.seeded and ist.mode == -1:
            if not ist.pb_started:
                ist.pb_started = True
                ist.pb_extreme = low
                ist.pb_extreme_loc = bar_index
                ist.pb_count = 0
                ist.pb_lqc = None
                ist.pb_lqh = None
            else:
                ext_chg = False
                if ist.pb_extreme is not None and low < ist.pb_extreme:
                    ist.pb_extreme = low
                    ist.pb_extreme_loc = bar_index
                    ist.pb_count = 0
                    ist.pb_lqc = None
                    ist.pb_lqh = None
                    ext_chg = True
                is_inside = (
                    ist.prev_high is not None and ist.prev_low is not None
                    and high < ist.prev_high and low > ist.prev_low
                )
                ext_dir = ext_chg and close > open_
                is_c1 = ist.pb_lqc is None and not ext_chg
                if (not is_inside or is_c1) and (not ext_chg or ext_dir):
                    thresh = ist.pb_extreme if ist.pb_lqh is None else ist.pb_lqh
                    if close > thresh:  # pbBuffer == 0.0
                        ist.pb_count += 1
                        ist.pb_lqc = close
                        ist.pb_lqh = high
                if ist.pb_count >= 3 and ist.pb_extreme is not None:
                    ist.sw_price = ist.pb_extreme
                    ist.sw_loc = ist.pb_extreme_loc
                    ist.sw_locked = True
                    # NOTE: same discrepancy as the mode==1 branch above, mirrored — the Pine
                    # comment says "iLL if lower than last, iHL if higher" but line 735 only
                    # checks i_had_bos, never comparing prices. Ported exactly as written.
                    events.swing_low_label = "iSL" if not ist.had_bos else "iLL"
                    events.new_swing_low = True
                    events.new_swing_low_price = ist.sw_price
                    events.new_swing_low_index = ist.sw_loc
                    ist.mode = 0
                    ist.pb_count = 0
                    ist.pb_started = False

        # ── Track extreme while watching (mode 0) (lines 744-752) ──
        if ist.seeded and ist.mode == 0:
            if ist.last_mode == 1:
                if ist.tracked_ext is None or low < ist.tracked_ext:
                    ist.tracked_ext = low
                    ist.tracked_ext_loc = bar_index
            elif ist.last_mode == -1:
                if ist.tracked_ext is None or high > ist.tracked_ext:
                    ist.tracked_ext = high
                    ist.tracked_ext_loc = bar_index

        # ── iBOS detection (lines 755-816); barstate.isconfirmed is always True here — we only
        # ever call update() on closed candles ──
        if ist.mode == 0 and ist.seeded and ist.sw_price is not None:
            if close > ist.sw_price and ist.last_mode == 1:
                events.bull_bos = True
                events.bull_bos_price = ist.sw_price

                if ist.tracked_ext is not None:
                    ist.last_hl = ist.tracked_ext
                    ist.last_hl_loc = ist.tracked_ext_loc
                    events.demoted_low_label = "iHL"
                    events.demoted_low_price = ist.tracked_ext
                    events.demoted_low_index = ist.tracked_ext_loc

                ist.sw_price = None
                ist.sw_loc = None
                ist.sw_locked = False
                ist.tracked_ext = None
                ist.tracked_ext_loc = None
                ist.pb_count = 0
                ist.pb_started = False
                ist.pb_lqc = None
                ist.pb_lqh = None
                ist.had_bos = True
                ist.bos_dir = 1
                ist.last_mode = 1
                ist.mode = 1
                ist.sos_watch_ll = None

            elif close < ist.sw_price and ist.last_mode == -1:
                events.bear_bos = True
                events.bear_bos_price = ist.sw_price

                if ist.tracked_ext is not None:
                    ist.last_lh = ist.tracked_ext
                    ist.last_lh_loc = ist.tracked_ext_loc
                    events.demoted_high_label = "iLH"
                    events.demoted_high_price = ist.tracked_ext
                    events.demoted_high_index = ist.tracked_ext_loc

                ist.sw_price = None
                ist.sw_loc = None
                ist.sw_locked = False
                ist.tracked_ext = None
                ist.tracked_ext_loc = None
                ist.pb_count = 0
                ist.pb_started = False
                ist.pb_lqc = None
                ist.pb_lqh = None
                ist.had_bos = True
                ist.bos_dir = -1
                ist.last_mode = -1
                ist.mode = -1
                ist.sos_watch_hh = None

        # ── iSOS detection (watches last iHL / iLH) (lines 821-928) ──
        if ist.seeded and ist.had_bos:
            if ist.last_mode == 1 and ist.last_hl is not None and close < ist.last_hl and ist.mode == 0:
                ist.sos_watch_hh = ist.sw_price
                ist.sos_watch_hh_loc = ist.sw_loc
                ist.sos_watch_ll = None

                events.bear_sos = True
                events.bear_sos_price = ist.last_hl

                ist.sw_price = None
                ist.sw_loc = None
                ist.sw_locked = False
                ist.tracked_ext = None
                ist.tracked_ext_loc = None
                ist.last_hl = None
                ist.pb_count = 0
                ist.pb_started = False
                ist.pb_lqc = None
                ist.pb_lqh = None
                ist.last_mode = -1
                ist.mode = -1

            elif ist.last_mode == -1 and ist.last_lh is not None and close > ist.last_lh and ist.mode == 0:
                ist.sos_watch_ll = ist.sw_price
                ist.sos_watch_ll_loc = ist.sw_loc
                ist.sos_watch_hh = None

                events.bull_sos = True
                events.bull_sos_price = ist.last_lh

                ist.sw_price = None
                ist.sw_loc = None
                ist.sw_locked = False
                ist.tracked_ext = None
                ist.tracked_ext_loc = None
                ist.last_lh = None
                ist.pb_count = 0
                ist.pb_started = False
                ist.pb_lqc = None
                ist.pb_lqh = None
                ist.last_mode = 1
                ist.mode = 1

            elif ist.last_mode == -1 and ist.sos_watch_hh is not None and close > ist.sos_watch_hh and ist.mode == 0:
                events.bull_sos = True
                events.bull_sos_price = ist.sos_watch_hh

                ist.sos_watch_ll = ist.sw_price
                ist.sos_watch_ll_loc = ist.sw_loc

                ist.sw_price = None
                ist.sw_loc = None
                ist.sw_locked = False
                ist.tracked_ext = None
                ist.tracked_ext_loc = None
                ist.last_lh = None
                ist.pb_count = 0
                ist.pb_started = False
                ist.pb_lqc = None
                ist.pb_lqh = None
                ist.last_mode = 1
                ist.mode = 1
                ist.sos_watch_hh = None

            elif ist.last_mode == 1 and ist.sos_watch_ll is not None and close < ist.sos_watch_ll and ist.mode == 0:
                events.bear_sos = True
                events.bear_sos_price = ist.sos_watch_ll

                ist.sos_watch_hh = ist.sw_price
                ist.sos_watch_hh_loc = ist.sw_loc

                ist.sw_price = None
                ist.sw_loc = None
                ist.sw_locked = False
                ist.tracked_ext = None
                ist.tracked_ext_loc = None
                ist.last_hl = None
                ist.pb_count = 0
                ist.pb_started = False
                ist.pb_lqc = None
                ist.pb_lqh = None
                ist.last_mode = -1
                ist.mode = -1
                ist.sos_watch_ll = None

        # ── Update last_mode when mode changes (lines 931-932) ──
        if ist.mode != 0:
            ist.last_mode = ist.mode

        return events
