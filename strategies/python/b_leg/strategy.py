"""BLegStrategy — the top-level B-LEG driver.

Same data flow as the SOS Fade bot, with the B-LEG tracker spliced in between the sequence and
the execution:

    BarState --SignalAdapter--> Signals --SosFadeSequence--> SeqState
             --BLegTracker--> BLegState --BLegExecution--> Decision

It SUBCLASSES `SosFadeStrategy` to inherit the fill-model plumbing (`_fill_model`) and
the engine-construction pins (`engine_config`: fvg_max_count=7 + show_internal=False — the
B-LEG reads the SAME structure/fib engines, so those pins matter identically). It overrides
`__init__` (to build `BLegExecution` + hold a tracker), `run` / `step` (to step the tracker
and pass its `BLegState` to `execution.step`), and disables `run_dual` (no 1m secondary here).
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import List, Optional

_ROOT = Path(__file__).resolve().parents[3]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))
_PYPKGS = Path(__file__).resolve().parents[1]
if str(_PYPKGS) not in sys.path:
    sys.path.insert(0, str(_PYPKGS))

from sos_fade.execution import Decision  # noqa: E402
from sos_fade.sequence import SosFadeSequence  # noqa: E402
from sos_fade.signals import SignalAdapter  # noqa: E402
from sos_fade.strategy import SosFadeStrategy  # noqa: E402

from .bleg import BLegTracker  # noqa: E402
from .config import BLegConfig  # noqa: E402
from .execution import BLegExecution  # noqa: E402


class BLegStrategy(SosFadeStrategy):
    def __init__(self, config: Optional[BLegConfig] = None,
                 initial_capital: float = 1_000_000.0, tick_source=None,
                 cost_profile=None, account=None, leg: str = "strat") -> None:
        self.config = config or BLegConfig()
        self.signals = SignalAdapter(self.config)
        self.sequence = SosFadeSequence(self.config)
        resolver, profile = self._fill_model(tick_source, cost_profile)
        # The shared-account seam, identical to the parent's — this fork overrides only
        # `_place_entries`, and every line that touches the account (the fill gate, the stop
        # reservation, the P&L booking, `equity`) is the parent's, so the seam works here for
        # free. It has to be threaded through this constructor because this one does not call
        # super().__init__. See the parent's __init__ for what `leg` must satisfy.
        self.execution = BLegExecution(self.config, initial_capital=initial_capital,
                                       resolver=resolver, profile=profile,
                                       account=account, leg=leg)
        self.tracker: Optional[BLegTracker] = None   # built in run() once the timeframe is known
        self.decisions: List[Decision] = []
        # The tracker's per-bar state, recorded alongside the decisions. REPORTING ONLY —
        # nothing reads it back, so it cannot move a decision. `compare_bleg.py` diffs it
        # against the export's `bl_*` columns: the tracker is where every new B-LEG rule
        # lives (band freeze, deepest-band migration, target track, tap, staleness death),
        # and a bug there shows as a wrong band price MANY bars before it becomes a wrong
        # trade. Without it a mismatch says "a trade differs" and nothing about why.
        self.bleg_states: List = []

    @staticmethod
    def engine_config():
        """The parent's pins, with the EQ/FVG coupling FORCED OFF — this fork's Pine keeps it off.

        `eqExemptFvg` defaults **true** in `sos_fade_strategy.pine` and **false** in
        `b_leg_strategy.pine`, so inheriting the parent's pin would replay this bot against a
        gap set its own Pine never held and put `compare_bleg.py` red. Same shape as the
        `exec_min_stop_mode = "Off"` pin in `config.py`: the two forks genuinely disagree, and the
        disagreement has to be written down on this side or it is silently resolved the wrong way.
        Re-check it against `b_leg_strategy.pine`'s own default before changing it — a fork
        that has caught up is a config change here, not a reason to delete the override.
        """
        import dataclasses
        return dataclasses.replace(SosFadeStrategy.engine_config(), eq_exempt_fvg=False)

    def step(self, bar_state) -> Decision:
        if self.tracker is None:
            self.tracker = BLegTracker(self.config)
        sig = self.signals.update(bar_state)
        seq = self.sequence.update(sig)
        bleg = self.tracker.update(sig, seq)
        dec = self.execution.step(sig, seq, bleg)
        self.decisions.append(dec)
        self.bleg_states.append(bleg)
        return dec

    def run(self, df, engine_config=None, warmup: int = 0) -> "BLegStrategy":
        """Replay a canonical bar frame end-to-end. The B-LEG's staleness cap is in bars-per-
        day, so the tracker needs the timeframe — inferred from the frame's bar spacing (the
        data is the source of truth, same as the tick-mode bar_ms inference in the SOS Fade driver)."""
        from backtest.replay import EngineStack, iter_bars

        if len(df.index) > 1:
            tf_seconds = int(df.index.to_series().diff().min().total_seconds())
            self.execution.bar_ms = tf_seconds * 1000
        else:
            tf_seconds = 900
        self.tracker = BLegTracker(self.config, tf_seconds=tf_seconds)

        stack = EngineStack(engine_config or self.engine_config())
        for bar in iter_bars(df):
            state = stack.step(bar)
            sig = self.signals.update(state)
            seq = self.sequence.update(sig)
            bleg = self.tracker.update(sig, seq)
            dec = self.execution.step(sig, seq, bleg)
            if bar.index >= warmup:
                self.decisions.append(dec)
                self.bleg_states.append(bleg)
        return self

    def run_dual(self, *args, **kwargs):
        raise NotImplementedError(
            "BLegStrategy has no 1m secondary re-entry — use run(). run_dual is SOS Fade-only.")
