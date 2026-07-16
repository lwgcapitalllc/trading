"""MpcAplusStrategy — the top-level driver.

Wires the three layers together over a replay `BarState` stream:

    BarState --SignalAdapter--> Signals --AplusSequence--> SeqState --Execution--> Decision

and collects the per-bar decision stream + the completed trade list. This is the one
object a backtest run (or the parity harness) drives: build it, feed `run(df)` or call
`step(bar_state)` per bar, then read `.decisions` and `.execution.trades`.

It owns nothing the engines own — it consumes `backtest.replay` output. Timeframe and
symbol facts arrive via `AplusConfig` (mintick, point value, close time); the engine
construction params live in the replay `EngineConfig`, not here.
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import List, Optional

# repo-root on path so `backtest.replay` imports standalone (CLI / harness / CI),
# matching backtest/replay/stack.py's own engines-on-path shim.
_ROOT = Path(__file__).resolve().parents[3]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from .config import AplusConfig
from .execution import Decision, Execution
from .sequence import AplusSequence
from .signals import SignalAdapter


class MpcAplusStrategy:
    def __init__(self, config: Optional[AplusConfig] = None,
                 initial_capital: float = 1_000_000.0, tick_source=None) -> None:
        self.config = config or AplusConfig()
        self.signals = SignalAdapter(self.config)
        self.sequence = AplusSequence(self.config)
        resolver, profile = self._fill_model(tick_source)
        self.execution = Execution(self.config, initial_capital=initial_capital,
                                   resolver=resolver, profile=profile)
        self.decisions: List[Decision] = []

    def _fill_model(self, tick_source):
        """Build the A2 resolver + cost profile from config. `(None, None)` is bar mode — the
        Pine's guess with no costs, which is what `compare_strategy.py` must run."""
        cfg = self.config
        if cfg.fill_model == "bar":
            return None, None
        if cfg.fill_model != "tick":
            raise ValueError(f"fill_model must be 'bar' or 'tick', got {cfg.fill_model!r}")
        from backtest.fills import PROFILES, TickPathResolver
        if cfg.account_profile not in PROFILES:
            raise ValueError(
                f"account_profile {cfg.account_profile!r} unknown — tick mode prices real costs, "
                f"so it needs a real account. Pick one of: {sorted(PROFILES)}")
        if not cfg.symbol:
            raise ValueError("tick mode needs config.symbol (the broker symbol to pull ticks for)")
        profile = PROFILES[cfg.account_profile]
        if tick_source is None:
            from backtest.data.mt5_agent import Mt5Agent
            from backtest.data.ticks import TickSource
            tick_source = TickSource(Mt5Agent())
        resolver = TickPathResolver(tick_source, cfg.symbol, latency_ms=profile.latency_ms)
        return resolver, profile

    def step(self, bar_state) -> Decision:
        sig = self.signals.update(bar_state)
        seq = self.sequence.update(sig)
        dec = self.execution.step(sig, seq)
        self.decisions.append(dec)
        return dec

    @staticmethod
    def engine_config():
        """The engine-construction params `mpc_strategy.pine` runs its engines with.
        These are NOT exported in the decision stream, so the bot must pin them to the
        strategy's own input defaults — not the shared engine defaults. Two differ:
        `fvgMaxCount` — mpc_strategy.pine sets it to 7 (the FVG engine's own default is 6),
        and a smaller cap evicts the oldest gap one bar sooner, dropping an entry edge Pine
        still holds. `show_internal` — the Pine strategy's "Show Internal Structure" input
        defaults OFF, and Pine gates the whole internal block behind it (`internalActive =
        showInternal`), so `i_confirmed_*` is never set and the Structure fib never adopts a
        more-extreme internal swing as its anchor. The market_structure engine always
        computes internal structure, so we must switch that adoption off to match the Pine.
        If a bot ever tunes another engine input off its default, add it here (and export it
        if it must vary per run)."""
        from backtest.replay import EngineConfig
        return EngineConfig(fvg_max_count=7, show_internal=False)

    def run(self, df, engine_config=None, warmup: int = 0) -> "MpcAplusStrategy":
        """Replay a canonical bar frame end-to-end. Engines warm on every bar; the
        strategy only records decisions from `warmup` on (same convention as the
        parity harnesses — the engines need history before their output is real)."""
        from backtest.replay import EngineStack, iter_bars

        # Tick mode resolves each bar against [bar_open, bar_open + duration), so it needs the
        # timeframe. Inferred from the frame rather than configured: the data IS the source of
        # truth here, and a hand-set duration that disagreed with it would silently read the
        # wrong tick window.
        if len(df.index) > 1:
            self.execution.bar_ms = int(df.index.to_series().diff().min().total_seconds() * 1000)

        stack = EngineStack(engine_config or self.engine_config())
        for bar in iter_bars(df):
            state = stack.step(bar)
            sig = self.signals.update(state)
            seq = self.sequence.update(sig)
            dec = self.execution.step(sig, seq)
            if bar.index >= warmup:
                self.decisions.append(dec)
        return self
