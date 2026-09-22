"""The lab driver — what `command-center`'s python runner and `backtest.optimizer` actually hold.

🔴 **This strategy runs off ONE bar stream, and that is the whole point of the 2026-09-20 work.**
The Pine reads three timeframes through `request.security`; the lab replays one frame (`run_sweep`)
or two (`run_dual`), so the strategy was unrunnable here. It is runnable now because both reads
are rebuilt from the chart's own bars:

* the **direction** (15-minute by default) is resampled from the chart and run through the
  canonical `engines/market_structure/` — MEASURED against the Pine's own column on 20,096 bars;
* the **confirmation** is the stack's structure engine on the chart frame itself, so no second
  engine is built and nothing is resampled.

⚠ **Therefore the confirmation timeframe may not be FINER than the bar frame the run replays.**
A one-minute confirmation on a five-minute replay is not a setting, it is a request for bars that
were never loaded — so `__init__` REFUSES it by name rather than silently confirming on the chart
frame and reporting the result as the strategy the chart trades. That refusal is the honest form
of the old blocker: the strategy is not crippled, it is told what frame it needs.
"""

from __future__ import annotations

from typing import Any, Optional

from backtest.replay.stack import EngineConfig

from strategies.python.extreme_leg.filters import REFUSE, UNKNOWN, NewsCut

from .config import SessionSweepConfig
from .core import BarInput, SessionSweepCore
from .levels import PrevPeriodLevels
from .structure import ResampledStructure

__all__ = ["SessionSweepStrategy"]


class _Execution:
    """The surface the lab reads off a strategy after a run.

    ⚠ `blocks` and `misses` are real empty lists, never missing attributes — this strategy does
    not yet record its refusals in the lab's shape, and an empty list here says "recorded nothing"
    rather than "was never asked". The block ladder itself is fully exercised and gated; what is
    absent is the REPORTING of it, and that is stated rather than implied.
    """

    def __init__(self, core: SessionSweepCore):
        self._core = core
        self.blocks: list = []
        self.misses: list = []
        self.bar_ms: int = 0

    @property
    def trades(self):
        return self._core.trades


class SessionSweepStrategy:
    """Drive the session-sweep core over the lab's per-bar `BarState`."""

    def __init__(
        self,
        config: Optional[SessionSweepConfig] = None,
        *,
        initial_capital: float = 10_000.0,
        cost_profile: Any = None,
        account: Any = None,
        leg: Optional[str] = None,
    ):
        cfg = config or SessionSweepConfig()
        if cost_profile is not None:
            # An unmeasured cost REFUSES rather than being silently dropped — the lab collected
            # commission and slippage for months and charged neither, and that is the bug the
            # `cost_profile` kwarg exists to make impossible. This core prices no costs yet.
            raise NotImplementedError(
                "the session sweep does not price costs yet, and this run states some. Charging "
                "nothing while reporting a cost profile is the defect build_strategy refuses — "
                "run it at zero commission and slippage, or add costs to core.py first."
            )
        if account is not None:
            raise NotImplementedError(
                "the session sweep does not take a shared account yet, so it cannot be a leg of "
                "a portfolio stack. Falling back to its own budget would report a capped, shared "
                "portfolio while this leg sized off the whole balance."
            )
        cfg.initial_capital = initial_capital
        self.config = cfg
        self.core = SessionSweepCore(cfg)
        self.execution = _Execution(self.core)
        self.levels = PrevPeriodLevels()
        self._dir_stream: Optional[ResampledStructure] = None
        self._htf_stream: Optional[ResampledStructure] = None
        self._chart_min: Optional[int] = None
        #: The first bar, HELD rather than dropped. The chart's frame is only knowable once two
        #: timestamps exist, and a strategy that quietly skips bar 0 is a strategy whose first
        #: session is missing from every run it will ever produce.
        self._held = None
        #: The news filter is the extreme leg's own, reused rather than rebuilt — same policy
        #: (high-impact USD, holidays blocked), same three-way answer. Its counts are the proof it
        #: was connected: `asked` says it ran, `unknown_count` says how often it could not see.
        self.news: Optional[NewsCut] = None
        if cfg.news_before_min > 0 or cfg.news_after_min > 0:
            self.news = NewsCut(cfg.news_before_min, cfg.news_after_min, "XAUUSD")

    # ── the lab's contract ────────────────────────────────────────────────────────────

    def engine_config(self) -> EngineConfig:
        """Only the structure engine, at the strategy's own pivot length.

        Every other engine is left OFF: the gap scan is the Pine's own arithmetic inside `core.py`
        (transcribed so the parity gate compares like with like), and nothing else is read. A
        stack builds only what its config asks for, so this costs no per-bar work for engines this
        strategy never consults.
        """
        return EngineConfig(major_length=self.config.pb_struct_len,
                            order_blocks=self.config.ob_confluence)

    def step(self, bar_state):
        bar = bar_state.bar
        ms = int(bar.timestamp_ms)

        # The chart's frame is MEASURED off the feed, never assumed, and it is what decides
        # whether the configured timeframes are reachable at all.
        if self._chart_min is None:
            if self._held is None:
                self._held = bar_state
                return None
            held_ms = int(self._held.bar.timestamp_ms)
            self._chart_min = max(1, (ms - held_ms) // 60_000)
            self._check_reachable(self._chart_min)
            self._dir_stream = ResampledStructure(
                int(self.config.pb_dir_tf), self._chart_min, self.config.pb_struct_len
            )
            if self.config.htf_trend_tf != "Off":
                self._htf_stream = ResampledStructure(
                    int(self.config.htf_trend_tf), self._chart_min, self.config.pb_struct_len
                )
            held, self._held = self._held, None
            self._feed(held)          # the held bar goes through FIRST, in order

        return self._feed(bar_state)

    def _feed(self, bar_state):
        bar = bar_state.bar
        ev = bar_state.structure.external
        ms = int(bar.timestamp_ms)
        dir_dir, _ = self._dir_stream.update(ms, bar.open, bar.high, bar.low, bar.close)
        # ⚠ The levels advance BEFORE the core steps, so a bar sees the previous period's
        # extreme — the same thing `lookahead_on` gives the Pine, and no bar that has not closed.
        self.levels.update(ms, bar.high, bar.low)
        htf_dir = 0
        if self._htf_stream is not None:
            htf_dir, _ = self._htf_stream.update(ms, bar.open, bar.high, bar.low, bar.close)
        lv = self.levels
        ob_bull = ob_bear = None
        if self.config.ob_confluence:
            obe = bar_state.order_blocks
            if obe is None:
                raise RuntimeError("the order-block filter is on but the stack built no order "
                                   "blocks — refusing rather than letting every setup through")
            ob_bull = tuple((o.top, o.bottom) for o in obe.active_bull)
            ob_bear = tuple((o.top, o.bottom) for o in obe.active_bear)
        blackout = None
        if self.news is not None:
            ans = self.news.ask(bar.index, ms)
            blackout = None if ans == UNKNOWN else (ans == REFUSE)
        return self.core.step(BarInput(
            time_ms=ms,
            open=bar.open, high=bar.high, low=bar.low, close=bar.close,
            dir_dir=dir_dir,
            conf_dir=bar_state.snapshot.direction,
            conf_shifted=bool(ev.bull_sos or ev.bear_sos),
            pdh=lv.pdh, pdl=lv.pdl, pwh=lv.pwh, pwl=lv.pwl,
            htf_dir=htf_dir,
            ob_bull=ob_bull, ob_bear=ob_bear,
            news_blackout=blackout,
        ))

    # ── the refusals ──────────────────────────────────────────────────────────────────

    def _check_reachable(self, chart_min: int) -> None:
        pairs = [("direction", self.config.pb_dir_tf), ("confirmation", self.config.pb_conf_tf)]
        if self.config.htf_trend_tf != "Off":
            pairs.append(("slower trend", self.config.htf_trend_tf))
        for name, tf in pairs:
            minutes = int(tf)
            if minutes % chart_min != 0:
                raise ValueError(
                    f"the {name} timeframe is {minutes}m but this run replays {chart_min}m bars. "
                    "A finer timeframe cannot be rebuilt from a coarser one — replay the finer "
                    "frame, or move the input. Confirming on the chart's frame instead would "
                    "report a different strategy from the one the chart trades."
                )
        conf = int(self.config.pb_conf_tf)
        if conf != chart_min:
            raise ValueError(
                f"the confirmation timeframe is {conf}m and this run replays {chart_min}m bars. "
                "The confirmation is read off the replayed frame itself, so the two must match "
                f"— replay {conf}m bars, or set the confirmation to {chart_min}m and re-gate it."
            )

