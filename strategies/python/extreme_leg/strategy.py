"""ExtremeLegStrategy — the run INTO the shift of structure.

    BarState --(5m structure + liquidity)--> LegState --ExtremeLegExecution--> a trade
             --(bars aggregated to 15m)-----> the trend and the swing being aimed at

The A+ bot waits for the shift of structure and fades the retracement after it. This takes the
move that CREATES that shift: stop beyond the extreme, target part of the way to the swing whose
break IS the shift. It is the earlier leg, which is why the two are not expected to be in the
market on the same swing.

⚠ **IT RUNS ON THE 5-MINUTE FRAME AND THAT IS NOT A PREFERENCE.** The 15-minute half is built in
code out of those bars, so the chart timeframe is the frame the trigger is measured on. Handing
this a 15-minute frame does not make it a 15-minute strategy — it makes the trigger and the target
the same series, and the change of character then fires on the bar the target is broken, with no
trade left to take.
"""

from __future__ import annotations

import math
import sys
from collections import deque
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import List, Optional

_PYPKGS = Path(__file__).resolve().parents[1]
if str(_PYPKGS) not in sys.path:
    sys.path.insert(0, str(_PYPKGS))
_ROOT = Path(__file__).resolve().parents[3]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from .config import ExtremeLegConfig  # noqa: E402
from .execution import (  # noqa: E402
    BLK_EXTREME_WRONG_SIDE,
    BLK_FRIDAY,
    BLK_NEWS,
    BLK_NO_SWING,
    BLK_NONE,
    BLK_STOP_UNDER_FLOOR,
    BLK_SWING_WRONG_SIDE,
    BLK_TARGET_TOO_NEAR,
    BLK_TRANSITIONING,
    ExtremeLegExecution,
)
from .filters import REFUSE, NewsCut, TransitioningCut
from .htf import HtfStructure  # noqa: E402

NA = float("nan")

# Which liquidity kinds count as which family. `pwc` — the previous week's CLOSE — is deliberately
# absent: it is a reference price the house engine also emits, and this strategy's Pine never
# watches it. A kind this map does not name is ignored rather than counted as an unknown family.
_FAMILY_OF = {"h4": "h4", "session": "session", "daily": "daily", "weekly": "weekly"}


def _pine_round(x: float) -> int:
    """Pine's `math.round` — half away from zero. Python's `round` is half-to-EVEN.

    ⚠ It changes an answer here: the minutes-to-bars conversions below are `round(minutes / frame)`
    and a half-step lands on one bar more or less of lookback. Both conversions are exported by the
    twin for exactly this reason.
    """
    return int(math.floor(x + 0.5)) if x >= 0 else -int(math.floor(-x + 0.5))


@dataclass
class LegState:
    """What the Pine computed on this bar, whether or not it traded.

    Recorded on every bar rather than on trade bars only. A port that agrees on the trades and
    disagrees on the levels underneath them has a bug that has not surfaced yet.
    """

    index: int = 0
    ts_ms: int = 0
    close: float = NA
    high: float = NA
    low: float = NA
    atr: float = NA
    extreme_low: float = NA
    extreme_high: float = NA
    dir15: int = 0
    swing_high: float = NA
    swing_low: float = NA
    low_armed: bool = False
    high_armed: bool = False
    low_families: int = 0
    high_families: int = 0
    low_age: Optional[int] = None
    high_age: Optional[int] = None
    swept_now: int = 0
    is_friday: bool = False
    raw_long: bool = False
    raw_short: bool = False
    stop_long: float = NA
    stop_short: float = NA
    tgt_long: float = NA
    tgt_short: float = NA
    tp_long: float = NA
    tp_short: float = NA
    r_long: float = NA
    r_short: float = NA
    blk_long: int = BLK_NONE
    blk_short: int = BLK_NONE
    go_long: bool = False
    go_short: bool = False
    entered: int = 0          # +1 long, -1 short, 0 none
    period_closed: bool = False
    htf_bar: Optional[tuple] = None

    def set_block(self, direction: int, code: int) -> None:
        if direction > 0:
            self.blk_long = code
            self.go_long = False
        else:
            self.blk_short = code
            self.go_short = False


class ExtremeLegStrategy:
    # The three constants the Pine hardcodes. Keyword-only and defaulted, so `build_strategy` and
    # the lab never see them and a test can still move one — see the block in `config.py` for why
    # they are not config fields.
    def __init__(self, config: Optional[ExtremeLegConfig] = None,
                 initial_capital: float = 10_000.0, cost_profile=None, *,
                 account=None, leg: str = "strat",
                 major_length: int = 15, htf_minutes: int = 15, atr_length: int = 50) -> None:
        self.config = config or ExtremeLegConfig()
        self.major_length = major_length
        self.htf_minutes = htf_minutes
        self.atr_length = atr_length
        # `account` is the SHARED account when this bot is one leg of a stack; omit it and the
        # execution layer builds its own uncapped one, which is the standalone behaviour every
        # figure in this package was measured on. `leg` must be distinct per leg — see
        # `execution.py`. The stack REFUSES a strategy that does not accept these two rather than
        # replaying it with a private balance, so leaving them off is not a quiet half-feature.
        self.execution = ExtremeLegExecution(
            self.config, initial_capital=initial_capital, profile=cost_profile,
            account=account, leg=leg,
        )
        self.states: List[LegState] = []
        self.htf = HtfStructure(htf_minutes, major_length)
        # ⚠ Built whether or not they are switched on, so that turning one on mid-session is not a
        # different code path from starting with it on — but they are only ASKED when their config
        # flag is set AND a setup exists, so an off filter costs one attribute and nothing else.
        # Both default off; see `config.py` → section 8 and `filters.py`.
        self.cut_regime = TransitioningCut()
        self.cut_news = NewsCut(self.config.news_before_min, self.config.news_after_min,
                                self.config.symbol)
        self._tf_min: Optional[int] = None
        self._prev_ms: Optional[int] = None
        # ATR(50), Wilder — `na` until it has 50 true ranges, then seeded with their mean. The NA
        # phase is reproduced rather than skipped because the Pine has it too, and the refusals it
        # causes are part of what the two sides have to agree about.
        self._atr: float = NA
        self._trs: List[float] = []
        self._prev_close: Optional[float] = None
        self._highs: deque = deque()
        self._lows: deque = deque()
        # Sweep state, per side. `None` = no level has ever been taken on this side, which is a
        # different fact from "the last one has expired" and is kept as a different value.
        self._low_bar: Optional[int] = None
        self._high_bar: Optional[int] = None
        self._low_fam: int = 0
        self._high_fam: int = 0

    # ── the stack this strategy needs ────────────────────────────────────────
    @staticmethod
    def engine_config():
        """The engine constants the Pine runs with, pinned rather than inherited.

        Both happen to equal the stack's own defaults today, and they are written down anyway: an
        engine input a strategy leaves unpinned is one the parity gate cannot see, because no
        `cfg_*` column carries it. That is how a three-day red gate happened here once already.

        `major_length` 15 is the Pine's own `majorLength`. `htf_rollover_hours` 18 is gold's
        session open in New York, which is what decides where the previous DAY and WEEK levels cut
        — a level family this strategy arms on.
        """
        from backtest.replay import EngineConfig
        return EngineConfig(major_length=15, htf_rollover_hours=18)

    def set_timeframe_minutes(self, minutes: int) -> None:
        """Tell the strategy what frame it is on, rather than letting it infer.

        The two minutes-to-bars conversions need the frame from the first bar, and inference needs
        two. A caller that knows should say; `step` learns it from the first gap otherwise, and
        nothing can arm before then because no level has been created yet either.
        """
        self._tf_min = int(minutes)

    # ── one bar ──────────────────────────────────────────────────────────────
    def step(self, bar_state) -> LegState:
        cfg = self.config
        bar = bar_state.bar
        st = LegState(index=bar.index, ts_ms=bar.timestamp_ms,
                      close=bar.close, high=bar.high, low=bar.low)

        # 1. The bracket placed on an earlier bar meets this bar's range. It happens before the
        #    script would run on the platform, so it happens before anything below.
        self.execution.resolve(bar.index, bar.timestamp_ms, bar.high, bar.low, bar.open)

        if self._prev_ms is not None and self._tf_min is None:
            gap = (bar.timestamp_ms - self._prev_ms) // 60_000
            if gap > 0:
                self._tf_min = int(gap)
        self._prev_ms = bar.timestamp_ms

        # 2. The 15-minute half.
        # ⚠ Both frames are fed on EVERY bar even when the cuts are off. Feeding only when a cut
        # is enabled would give it 34 bars of history starting from whenever somebody flipped the
        # switch, so the first hours after a restart would answer UNKNOWN and read as "nothing to
        # refuse". Cheap: two four-float tuples into bounded deques.
        self.cut_regime.on_bar(bar.open, bar.high, bar.low, bar.close)
        self.htf.update(bar.timestamp_ms, bar.open, bar.high, bar.low, bar.close)
        if self.htf.period_closed and self.htf.done is not None:
            self.cut_regime.on_htf_bar(*self.htf.done)
        st.period_closed = self.htf.period_closed
        st.htf_bar = self.htf.done
        st.dir15 = self.htf.dir
        st.swing_high = self.htf.swing_high
        st.swing_low = self.htf.swing_low

        # 3. Average range and the rolling extreme.
        self._update_atr(bar.high, bar.low, bar.close)
        st.atr = self._atr
        tf = self._tf_min or 1
        lookback = max(1, _pine_round(cfg.extreme_minutes / tf))
        self._highs.append(bar.high)
        self._lows.append(bar.low)
        while len(self._highs) > lookback:
            self._highs.popleft()
            self._lows.popleft()
        st.extreme_high = max(self._highs)
        st.extreme_low = min(self._lows)

        # 4. The sweep, and what it armed.
        bars_back = max(1, _pine_round(cfg.swept_minutes / tf))
        self._update_sweeps(bar_state, bar.index, bars_back, st)

        # 5. The setup.
        self._build_setup(st, bar_state.structure.external)

        # 6. The order.
        if self.execution.enter(st):
            st.entered = 1 if st.go_long else -1
        self.execution.arm_breakeven(bar.index, bar.high, bar.low)
        self.execution.record_blocks(st)

        self.states.append(st)
        return st

    # ── the pieces ───────────────────────────────────────────────────────────
    def _update_atr(self, high: float, low: float, close: float) -> None:
        """Pine `ta.atr(50)` = `ta.rma(ta.tr(true), 50)`, reproduced exactly — including the
        warm-up, where the value is `na` and every comparison against it reads false."""
        n = self.atr_length
        prev = self._prev_close
        tr = (high - low) if prev is None else max(high - low, abs(high - prev), abs(low - prev))
        self._prev_close = close
        if math.isnan(self._atr):
            self._trs.append(tr)
            if len(self._trs) == n:
                self._atr = sum(self._trs) / float(n)
        else:
            self._atr += (tr - self._atr) / float(n)

    def _update_sweeps(self, bar_state, index: int, bars_back: int, st: LegState) -> None:
        """Which level families price took on THIS bar, and whether that leaves a side armed.

        ⚠ **The count is the one from the most recent sweep BAR, not a running total.** "Two
        families agreeing" means two were taken on the same bar — an accumulating count would make
        the setting mean something else entirely and would arm far more often.

        ⚠ **The levels come from the canonical liquidity engine, never from a copy of the Pine's
        own tracking.** The two are not guaranteed to agree and are not assumed to: the Pine reads
        a wick through the previous WEEK's high as a sweep while the house engine wants a close
        through it, and the Pine's session windows are fixed strings where the house engine's are
        daylight-saving aware. Both differences are real, both are visible in the export twin's
        per-level columns, and both are for the gate to settle — not for this file to paper over
        by forking the engine.
        """
        cfg = self.config
        enabled = {
            "h4": cfg.use_h4_level,
            "session": cfg.use_session_level,
            "daily": cfg.use_daily_level,
            "weekly": cfg.use_weekly_level,
        }
        low_fams, high_fams = set(), set()
        bits = 0
        _BIT = {("h4", "low"): 1, ("h4", "high"): 2, ("session", "low"): 4,
                ("session", "high"): 8, ("daily", "low"): 16, ("daily", "high"): 32,
                ("weekly", "low"): 64, ("weekly", "high"): 128}
        for lvl in bar_state.liquidity.mitigated:
            fam = _FAMILY_OF.get(lvl.kind)
            if fam is None or not enabled[fam]:
                continue
            (low_fams if lvl.side == "low" else high_fams).add(fam)
            bits |= _BIT.get((fam, lvl.side), 0)
        st.swept_now = bits

        if low_fams:
            self._low_bar, self._low_fam = index, len(low_fams)
        elif self._low_bar is not None and index - self._low_bar > bars_back:
            self._low_fam = 0
        if high_fams:
            self._high_bar, self._high_fam = index, len(high_fams)
        elif self._high_bar is not None and index - self._high_bar > bars_back:
            self._high_fam = 0

        st.low_families, st.high_families = self._low_fam, self._high_fam
        st.low_age = None if self._low_bar is None else index - self._low_bar
        st.high_age = None if self._high_bar is None else index - self._high_bar
        st.low_armed = (self._low_bar is not None and index - self._low_bar <= bars_back
                        and self._low_fam >= cfg.min_families)
        st.high_armed = (self._high_bar is not None and index - self._high_bar <= bars_back
                         and self._high_fam >= cfg.min_families)

    def _build_setup(self, st: LegState, ext) -> None:
        """The candidate and the refusal ladder — `[doc 11]` to `[doc 12d]` of the Pine.

        ⚠ **The R is measured on the WHOLE distance to the swing, and the exit rests part of the
        way there.** The minimum-target refusal is judging how much ROOM the setup has, which is a
        different question from where the order is placed. Measuring it on the exit instead would
        refuse setups for the size of the exit we chose rather than the size of the move available.
        """
        cfg = self.config
        st.is_friday = datetime.fromtimestamp(
            st.ts_ms / 1000.0, tz=timezone.utc
        ).weekday() == 4

        st.raw_long = bool(ext.bull_sos) and cfg.exec_longs and st.low_armed and (
            not cfg.req_counter_trend or st.dir15 == -1)
        st.raw_short = bool(ext.bear_sos) and cfg.exec_shorts and st.high_armed and (
            not cfg.req_counter_trend or st.dir15 == 1)

        entry = st.close
        st.tgt_long, st.tgt_short = st.swing_high, st.swing_low
        st.stop_long = st.extreme_low - cfg.stop_buffer_atr * st.atr
        st.stop_short = st.extreme_high + cfg.stop_buffer_atr * st.atr
        risk_long = entry - st.stop_long
        risk_short = st.stop_short - entry
        st.r_long = ((st.tgt_long - entry) / risk_long) if risk_long > 0 else NA
        st.r_short = ((entry - st.tgt_short) / risk_short) if risk_short > 0 else NA
        st.tp_long = entry + (st.tgt_long - entry) * cfg.tp_frac
        st.tp_short = entry - (entry - st.tgt_short) * cfg.tp_frac

        # ⚠ Asked ONCE per bar and only when a setup exists, not per side and not per bar. The
        # classifier walks its whole frame on every call; per bar over eight years of 5-minute
        # gold that is half a million walks. An answer of UNKNOWN allows the trade and is counted
        # on the cut — see `filters.py` for why those are three answers rather than a bool.
        transitioning = news_blocked = False
        if (st.raw_long or st.raw_short) and cfg.skip_transitioning:
            transitioning = self.cut_regime.ask() == REFUSE
        if (st.raw_long or st.raw_short) and cfg.skip_news:
            news_blocked = self.cut_news.ask(st.index, st.ts_ms) == REFUSE

        if st.raw_long:
            st.blk_long = self._ladder(cfg, st.is_friday, st.tgt_long, entry, risk_long,
                                       st.r_long, above=True, transitioning=transitioning,
                                       news=news_blocked)
        if st.raw_short:
            st.blk_short = self._ladder(cfg, st.is_friday, st.tgt_short, entry, risk_short,
                                        st.r_short, above=False, transitioning=transitioning,
                                        news=news_blocked)
        st.go_long = st.raw_long and st.blk_long == BLK_NONE
        st.go_short = st.raw_short and st.blk_short == BLK_NONE

    @staticmethod
    def _ladder(cfg, is_friday: bool, target: float, entry: float, risk: float,
                r: float, *, above: bool, transitioning: bool = False,
                news: bool = False) -> int:
        """The refusal ladder, in the Pine's order. First match wins; 0 means nothing refused it.

        ⚠ **Every comparison here is deliberately allowed to be NaN and read as false**, which is
        what Pine does with `na`. Adding an `isnan` guard to any line below would make this side
        refuse where the chart does not.
        """
        if cfg.skip_friday and is_friday:
            return BLK_FRIDAY
        if math.isnan(target):
            return BLK_NO_SWING
        if (target <= entry) if above else (target >= entry):
            return BLK_SWING_WRONG_SIDE
        if risk <= 0:
            return BLK_EXTREME_WRONG_SIDE
        if cfg.min_stop_usd > 0 and risk < cfg.min_stop_usd:
            return BLK_STOP_UNDER_FLOOR
        if r < cfg.min_r:
            return BLK_TARGET_TOO_NEAR
        # ── past this line the CHART would have taken the trade ──────────────────────────────
        # Both cuts are last on purpose: with them off the code stream is bit-identical to the
        # Pine's, and with one on the divergence lands on its own code rather than changing which
        # of the Pine's codes gets recorded. See `config.py` → section 8.
        if cfg.skip_transitioning and transitioning:
            return BLK_TRANSITIONING
        if cfg.skip_news and news:
            return BLK_NEWS
        return BLK_NONE

    # ── drivers ──────────────────────────────────────────────────────────────
    def run(self, df, engine_config=None, warmup: int = 0) -> "ExtremeLegStrategy":
        """Replay a bar frame end to end. Engines warm on every bar; states are kept from
        `warmup` on, the same convention every parity harness here uses."""
        from backtest.replay import EngineStack, iter_bars

        if len(df.index) > 1:
            tf = int(df.index.to_series().diff().min().total_seconds() // 60)
            if tf > 0:
                self.set_timeframe_minutes(tf)
            self.execution.bar_ms = tf * 60_000
        stack = EngineStack(engine_config or self.engine_config())
        for bar in iter_bars(df):
            self.step(stack.step(bar))
        # Trimmed AFTER the run, never during it: the warm-up hides the engines' cold start from
        # the comparison, and it must not change a single decision the run made.
        if warmup:
            self.states = [s for s in self.states if s.index >= warmup]
        return self
