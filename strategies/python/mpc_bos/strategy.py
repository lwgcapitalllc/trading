"""MpcBosStrategy — the top-level MPC BOS driver.

Same data flow as the B-LEG bot, with the BOS tracker in place of the B-LEG one:

    BarState --SignalAdapter--> Signals --BosTracker--> BosState --BosExecution--> Decision

The A+ SEQUENCE is not stepped at all. The B-LEG needs it (it arms off the A+ leg's death);
the BOS does not — its arm is a structure event the `Signals` adapter already carries. A
`_NoSeq` placeholder satisfies the parent `Execution.step`'s signature without pretending an
A+ setup exists.

It SUBCLASSES `MpcSosFadeStrategy` for the fill-model plumbing (`_fill_model`) and the
engine-construction pins (`engine_config`) — the BOS reads the SAME structure / fib / FVG /
sniper engines, so those pins matter identically.
"""

from __future__ import annotations

import sys
from dataclasses import dataclass
from pathlib import Path
from typing import List, Optional

_ROOT = Path(__file__).resolve().parents[3]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))
_PYPKGS = Path(__file__).resolve().parents[1]
if str(_PYPKGS) not in sys.path:
    sys.path.insert(0, str(_PYPKGS))

from mpc_sos_fade.execution import Decision  # noqa: E402
from mpc_sos_fade.signals import SignalAdapter  # noqa: E402
from mpc_sos_fade.strategy import MpcSosFadeStrategy  # noqa: E402

from .bos import BosTracker  # noqa: E402
from .config import BosConfig  # noqa: E402
from .execution import BosExecution  # noqa: E402


@dataclass(frozen=True)
class _NoSeq:
    """The A+ sequence state, permanently empty. The parent `Execution.step` reads exactly
    these four fields before handing control to `_place_entries`, which this fork overrides
    and which never looks at them."""

    l_stage: int = 0
    s_stage: int = 0
    l_sos_bar: Optional[int] = None
    s_sos_bar: Optional[int] = None


_NO_SEQ = _NoSeq()


class MpcBosStrategy(MpcSosFadeStrategy):
    def __init__(self, config: Optional[BosConfig] = None,
                 initial_capital: float = 1_000_000.0, tick_source=None) -> None:
        self.config = config or BosConfig()
        self.signals = SignalAdapter(self.config)
        resolver, profile = self._fill_model(tick_source)
        self.execution = BosExecution(self.config, initial_capital=initial_capital,
                                      resolver=resolver, profile=profile)
        self.tracker: Optional[BosTracker] = None   # built in run() once the timeframe is known
        self.decisions: List[Decision] = []
        # The tracker's per-bar state, recorded alongside the decisions. REPORTING ONLY —
        # nothing reads it back, so it cannot move a decision. Every BOS rule lives in the
        # tracker (regime, arm, the quality filters, the anchor fib, the four deaths), and a
        # bug there shows as a wrong anchor price MANY bars before it becomes a wrong trade.
        self.bos_states: List = []

    def _wire(self) -> None:
        self.execution._tracker = self.tracker

    def step(self, bar_state) -> Decision:
        if self.tracker is None:
            self.tracker = BosTracker(self.config)
            self._wire()
        sig = self.signals.update(bar_state)
        bos = self.tracker.update(sig)
        dec = self.execution.step(sig, _NO_SEQ, bos)
        self.decisions.append(dec)
        self.bos_states.append(bos)
        return dec

    def run(self, df, engine_config=None, warmup: int = 0) -> "MpcBosStrategy":
        """Replay a canonical bar frame end-to-end. F9's staleness cap is set in DAYS, so the
        tracker needs the timeframe — inferred from the frame's bar spacing (the data is the
        source of truth, same as the B-LEG driver)."""
        from backtest.replay import EngineStack, iter_bars

        if len(df.index) > 1:
            tf_seconds = int(df.index.to_series().diff().min().total_seconds())
            self.execution.bar_ms = tf_seconds * 1000
        else:
            tf_seconds = 900
        self.tracker = BosTracker(self.config, tf_seconds=tf_seconds)
        self._wire()

        stack = EngineStack(engine_config or self.engine_config())
        for bar in iter_bars(df):
            state = stack.step(bar)
            sig = self.signals.update(state)
            bos = self.tracker.update(sig)
            dec = self.execution.step(sig, _NO_SEQ, bos)
            if bar.index >= warmup:
                self.decisions.append(dec)
                self.bos_states.append(bos)
        return self

    def run_dual(self, *args, **kwargs):
        raise NotImplementedError(
            "MpcBosStrategy has no 1m secondary re-entry — use run(). run_dual is A+-only.")
