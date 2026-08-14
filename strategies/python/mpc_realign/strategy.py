"""MpcRealignStrategy — the top-level MPC REALIGN driver.

Data flow, one 5m bar at a time:

    ReplayBar --EngineStack--> BarState  (5m external + internal structure)
              --HtfStructure--> 15m ExternalEvents, on 15m closes only
              --RealignTracker--> RealignState
              --RealignExecution--> Decision

It SUBCLASSES `MpcSosFadeStrategy` for the fill-model plumbing and the engine pins, the
same way `MpcBLegStrategy` does, and overrides construction and the step loop.

⚠ SINGLE-FRAME BY CONSTRUCTION. The 15m structure is aggregated from the 5m stream inside
`HtfStructure`, so the runner hands this one frame and `run_sweep` can replay it. A
dual-frame build would be refused by the optimizer outright.

⚠ `show_internal` MUST be True here — the parent pins it False (its Pine hides internal
structure), and this fork's SHORT trigger reads the internal stream. Inheriting the
parent's pin would blank the very events the short side trades on, and the symptom would
be a bot that simply never goes short.
"""

from __future__ import annotations

import dataclasses
import sys
from pathlib import Path
from typing import List, Optional

_ROOT = Path(__file__).resolve().parents[3]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))
_PYPKGS = Path(__file__).resolve().parents[1]
if str(_PYPKGS) not in sys.path:
    sys.path.insert(0, str(_PYPKGS))

from mpc_sos_fade.execution import Decision  # noqa: E402
from mpc_sos_fade.sequence import SosFadeSequence  # noqa: E402
from mpc_sos_fade.signals import SignalAdapter  # noqa: E402
from mpc_sos_fade.strategy import MpcSosFadeStrategy  # noqa: E402

from .config import RealignConfig  # noqa: E402
from .execution import RealignExecution  # noqa: E402
from .htf import HtfStructure  # noqa: E402
from .tracker import RealignTracker  # noqa: E402


class MpcRealignStrategy(MpcSosFadeStrategy):
    def __init__(
        self,
        config: Optional[RealignConfig] = None,
        initial_capital: float = 1_000_000.0,
        tick_source=None,
        cost_profile=None,
        account=None,
        leg: str = "strat",
    ) -> None:
        self.config = config or RealignConfig()
        self.signals = SignalAdapter(self.config)
        self.sequence = SosFadeSequence(self.config)
        resolver, profile = self._fill_model(tick_source, cost_profile)
        self.execution = RealignExecution(
            self.config,
            initial_capital=initial_capital,
            resolver=resolver,
            profile=profile,
            account=account,
            leg=leg,
        )
        self.tracker = RealignTracker(self.config)
        self.htf = HtfStructure(self.config.realign_htf_minutes)
        self.decisions: List[Decision] = []
        self.states: List = []

    @staticmethod
    def engine_config():
        """The parent's pins, with internal structure switched back ON.

        The short side triggers on the engine's `InternalEvents`; the parent pins
        `show_internal=False` because its own Pine hides the internal block. Inheriting
        that would blank the short trigger and the bot would simply never short.
        """
        return dataclasses.replace(MpcSosFadeStrategy.engine_config(), show_internal=True)

    def _step_core(self, state, bar_time_ms: int) -> Decision:
        b = state.bar
        closed = self.htf.update(bar_time_ms, b.open, b.high, b.low, b.close)
        if closed is not None:
            self.tracker.on_htf(closed, bar_time_ms, self.htf.broken_high, self.htf.broken_low)
        rs = self.tracker.update(
            bar_time_ms, b.high, b.low, state.structure.external, state.structure.internal
        )
        sig = self.signals.update(state)
        seq = self.sequence.update(sig)
        dec = self.execution.step(sig, seq, rs)
        self._last_state = rs
        return dec

    def step(self, bar_state) -> Decision:
        dec = self._step_core(bar_state, bar_state.bar.timestamp_ms)
        self.decisions.append(dec)
        self.states.append(self._last_state)
        return dec

    def run(self, df, engine_config=None, warmup: int = 0) -> "MpcRealignStrategy":
        from backtest.replay import EngineStack, iter_bars

        if len(df.index) > 1:
            tf_seconds = int(df.index.to_series().diff().min().total_seconds())
            self.execution.bar_ms = tf_seconds * 1000

        stack = EngineStack(engine_config or self.engine_config())
        for bar in iter_bars(df):
            state = stack.step(bar)
            dec = self._step_core(state, bar.timestamp_ms)
            if bar.index >= warmup:
                self.decisions.append(dec)
                self.states.append(self._last_state)
        return self

    def run_dual(self, *args, **kwargs):
        raise NotImplementedError(
            "MpcRealignStrategy is single-frame — the 15m is aggregated internally. Use run()."
        )
