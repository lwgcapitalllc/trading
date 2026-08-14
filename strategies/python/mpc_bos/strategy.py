"""MpcBosStrategy — the top-level BOS driver.

Same data flow as the A+ bot, with the BOS tracker spliced in between the sequence and the
execution:

    BarState --SignalAdapter--> Signals --SosFadeSequence--> SeqState
             --BosTracker--> BosState --BosExecution--> Decision

It SUBCLASSES `MpcSosFadeStrategy` to inherit the fill-model plumbing (`_fill_model`), and
overrides `__init__`, `engine_config`, `run` / `step`, and `run_dual`.

⚠ **`SosFadeSequence` is still stepped even though no A+ trade can fire here** (`exec_aplus` is
pinned False). It is cheap, it keeps the `Signals` -> `SeqState` seam identical to the other two
bots, and — the real reason — `Execution.step` reads `seq.l_stage` / `seq.s_stage` into the
decision stream on every bar. Dropping it would leave two parity columns permanently zero and
make a genuine engine drift invisible in exactly the place it would first show up.
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

from mpc_sos_fade.execution import Decision  # noqa: E402
from mpc_sos_fade.sequence import SosFadeSequence  # noqa: E402
from mpc_sos_fade.signals import SignalAdapter  # noqa: E402
from mpc_sos_fade.strategy import MpcSosFadeStrategy  # noqa: E402

from .bos import BosTracker, VolumeUnavailable  # noqa: E402
from .config import BosConfig  # noqa: E402
from .execution import BosExecution  # noqa: E402


class MpcBosStrategy(MpcSosFadeStrategy):
    def __init__(self, config: Optional[BosConfig] = None,
                 initial_capital: float = 1_000_000.0, tick_source=None,
                 cost_profile=None) -> None:
        self.config = config or BosConfig()
        self.signals = SignalAdapter(self.config)
        self.sequence = SosFadeSequence(self.config)
        resolver, profile = self._fill_model(tick_source, cost_profile)
        self.execution = BosExecution(self.config, initial_capital=initial_capital,
                                      resolver=resolver, profile=profile)
        self.tracker: Optional[BosTracker] = None   # built in run() once the timeframe is known
        self.decisions: List[Decision] = []
        # The tracker's per-bar state, recorded alongside the decisions. REPORTING ONLY —
        # nothing reads it back, so it cannot move a decision. `compare_bos.py` diffs it against
        # the export's `px_leg_*` / `px_ord_*` / `px_ready` / `px_vwap` columns: the tracker is
        # where every BOS rule lives, and a bug there shows as a wrong LEG many bars before it
        # becomes a wrong trade. Without it a mismatch says "a trade differs" and nothing more.
        self.bos_states: List = []
        # The exit ladder's stage PER BAR, parallel to `decisions`. Sampled here because the
        # execution object holds one live `_stage` and reading it after the run is reading the
        # last bar — see `_exit_stage`.
        self.exit_stages: List[int] = []

    @staticmethod
    def engine_config():
        """The engine-construction params `mpc_bos_strategy.pine` runs its engines with.

        These are NOT in the decision stream, so they must be pinned to THIS Pine's own input
        defaults — and three of the five differ from the A+ bot's, which is the whole reason
        this override exists rather than inheriting:

        `fvg_max_count` **8** (A+ pins 7) — this fork's Pine keeps the same cap
          `mpc_assistant.pine` draws with, so a gap still on the chart is a gap the strategy
          still holds. A smaller cap evicts the oldest gap one bar sooner and drops an entry
          edge the Pine still has.
        `fvg_threshold_pct` **0.04** (A+ pins 0.1) — the 15m floor. This Pine's tooltip states
          the disagreement explicitly: on gold at $4,155 the A+ 0.1% demands a $4.16 gap and
          throws away most real 15m ones, and this fork chose the indicator's 0.04% instead.
        `fvg_require_close` **False** (A+ pins True) — `mpc_strategy.pine` HARDCODES the
          middle-bar close-cleared check; this fork exposes it as an input defaulting OFF, which
          is the classic FVG the chart draws.
        `show_internal` False and `eq_exempt_fvg` False match this Pine's own defaults.

        ⚠ Every one of the three differences makes this fork hold MORE gaps than the A+ bot, so
        inheriting the parent's pins would silently narrow the gap set — and at the shipped
        defaults (`bos_use_fvg` off) nothing would move at all, which is worse: the pin would
        look correct right up until somebody switched the gap entry back on.
        ⚠ `fvg_threshold_pct` and `fvg_max_count` and the two bools all vary per run and ARE
        exported (`cfg_fvg_thresh`, `cfg_fvg_max`, `cfg_bits`), so `compare_bos.py` configures
        the engines FROM the export rather than trusting this function.
        """
        from backtest.replay import EngineConfig
        return EngineConfig(fvg_max_count=8, show_internal=False, fvg_require_close=False,
                            fvg_threshold_pct=0.04, eq_exempt_fvg=False)

    # ── one bar ──────────────────────────────────────────────────────────────────
    def _step_bar(self, state, bar) -> Decision:
        """The ordering here is the Pine's and is not interchangeable.

        `atr14 = ta.atr(14)` is a single series computed at the TOP of the Pine's execution
        block, before Stage 0/1 reads it for F2/F3 and before the stop model reads it. So the
        ATR is advanced first, stamped onto the signal, and both layers read the same number —
        rather than each keeping its own accumulator and drifting apart on the warmup.
        """
        sig = self.signals.update(state)
        seq = self.sequence.update(sig)
        # Attached rather than passed, because `Signals` is the shared A+ seam and widening it
        # for a field only this fork reads would put a permanently-None column on the other two
        # bots. `bos.py::_atr_of` reads it back with a default, so a hand-built Signals in a
        # test simply behaves as "ATR unknown".
        setattr(sig, "bos_atr14", self.execution.prime_atr(sig))
        bos = self.tracker.update(sig, bar)
        dec = self.execution.step(sig, seq, bos)
        return dec, bos, self._exit_stage()

    def _exit_stage(self) -> int:
        """The EXIT ladder's stage on THIS bar — Pine's `px_stage` (0 flat / 1 TP1 / 2 TP2).

        🔴 It has to be sampled per bar and stored. `compare_bos.py` used to read
        `strat.execution._stage` inside its compare loop, which runs AFTER the whole replay —
        so every bar was diffed against the run's FINAL stage, a constant. The run ends flat,
        so that constant was 0, and the column silently compared nothing at all until a Pine
        bar happened to report 1 or 2. A harness that reads live state after the fact is not
        reading the bar it claims to.
        """
        return self.execution._stage if self.execution._pos_dir != 0 else 0

    def step(self, bar_state) -> Decision:
        if self.tracker is None:
            self.tracker = BosTracker(self.config)
            self.execution._tracker = self.tracker
        dec, bos, stage = self._step_bar(bar_state, bar_state.bar)
        self.decisions.append(dec)
        self.bos_states.append(bos)
        self.exit_stages.append(stage)
        return dec

    def run(self, df, engine_config=None, warmup: int = 0) -> "MpcBosStrategy":
        """Replay a canonical bar frame end-to-end.

        ⚠ The VOLUME check is up front and REFUSES, rather than letting the run start and
        discover it 100,000 bars in. The session-VWAP filter is on by default and cannot be
        computed without volume; both ways of guessing are silent (block everything → an empty
        book that reads like a strategy with no signals; pass everything → a filter reported as
        on and doing nothing). See `bos.VolumeUnavailable`.
        """
        from backtest.replay import EngineStack, iter_bars

        if self.config.bos_vwap_req != "Off" and "volume" not in df.columns:
            raise VolumeUnavailable(
                "bos_vwap_req is on and this bar frame has no 'volume' column, so the session "
                "VWAP cannot be computed. Re-pull the bars with volume (backtest/CLAUDE.md → "
                "the FEED_VERSION 3 note) or set bos_vwap_req='Off' deliberately."
            )

        if len(df.index) > 1:
            tf_seconds = int(df.index.to_series().diff().min().total_seconds())
            self.execution.bar_ms = tf_seconds * 1000
        else:
            tf_seconds = 900
        self.tracker = BosTracker(self.config, tf_seconds=tf_seconds)
        self.execution._tracker = self.tracker

        stack = EngineStack(engine_config or self.engine_config())
        for bar in iter_bars(df):
            state = stack.step(bar)
            dec, bos, stage = self._step_bar(state, bar)
            if bar.index >= warmup:
                self.decisions.append(dec)
                self.bos_states.append(bos)
                self.exit_stages.append(stage)
        return self

    def run_dual(self, *args, **kwargs):
        raise NotImplementedError(
            "MpcBosStrategy has no 1m secondary re-entry — use run(). run_dual is A+-only, and "
            "`BosConfig` pins exec_secondary=False for the same reason."
        )
