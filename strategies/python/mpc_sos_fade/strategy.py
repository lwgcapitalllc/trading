"""MpcSosFadeStrategy — the top-level driver.

Wires the three layers together over a replay `BarState` stream:

    BarState --SignalAdapter--> Signals --SosFadeSequence--> SeqState --Execution--> Decision

and collects the per-bar decision stream + the completed trade list. This is the one
object a backtest run (or the parity harness) drives: build it, feed `run(df)` or call
`step(bar_state)` per bar, then read `.decisions` and `.execution.trades`.

It owns nothing the engines own — it consumes `backtest.replay` output. Timeframe and
symbol facts arrive via `SosFadeConfig` (mintick, point value, close time); the engine
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

from .config import SosFadeConfig
from .execution import Decision, Execution
from .sequence import SosFadeSequence
from .signals import SignalAdapter


class MpcSosFadeStrategy:
    def __init__(self, config: Optional[SosFadeConfig] = None,
                 initial_capital: float = 1_000_000.0, tick_source=None) -> None:
        self.config = config or SosFadeConfig()
        self.signals = SignalAdapter(self.config)
        self.sequence = SosFadeSequence(self.config)
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

    def run(self, df, engine_config=None, warmup: int = 0) -> "MpcSosFadeStrategy":
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

    def run_dual(self, df15, df1m, engine_config=None, warmup: int = 0,
                 progress=None, should_cancel=None) -> "MpcSosFadeStrategy":
        """Replay the PRIMARY on 15m and the SECONDARY (1m sniper re-entry) on 1m, on one merged
        clock. The primary path is byte-identical to `run(df15)` — 15m bars are stepped in the same
        order with the same OHLC and `step_secondary` never touches a primary position — so
        `compare_strategy.py` parity is unaffected (and with `exec_secondary` OFF this is just a
        slower `run`). The secondary latches its 1m leg, arms off the LAST-CLOSED 15m context, and
        fills/manages on real 1m bars. Full design: docs/MPC_SOS_FADE_SECONDARY.md.

        `df15` / `df1m` are canonical frames (UTC DatetimeIndex, open/high/low/close) over the same
        window. Bars are timestamped at OPEN; a 15m bar closes at `open + tf15`, so a 1m bar reads
        the 15m context of the bar that has already CLOSED by its open time — non-repainting, and
        the same `lookahead_off` semantics the Pine used.
        """
        from collections import namedtuple
        from datetime import datetime, timezone
        from zoneinfo import ZoneInfo

        from backtest.replay import EngineStack, iter_bars
        from .secondary import SecondaryArm, Structure1m

        _Bar1mSig = namedtuple("_Bar1mSig", "index time_ms open high low close")
        ny = ZoneInfo("America/New_York")

        if len(df15.index) > 1:
            tf15_ms = int(df15.index.to_series().diff().min().total_seconds() * 1000)
            self.execution.bar_ms = tf15_ms
        else:
            tf15_ms = 900_000

        stack = EngineStack(engine_config or self.engine_config())
        bars15 = list(iter_bars(df15))
        close15 = [b.timestamp_ms + tf15_ms for b in bars15]   # when each 15m bar is known
        n15 = len(bars15)
        struct1m = Structure1m(major_length=(engine_config or self.engine_config()).major_length)
        arm_sm = SecondaryArm(self.config)

        last_sig = last_seq = None
        last_close15 = None     # the last-CLOSED 15m bar's close — the zone gate reads this (Pine's 15m `close`)
        i15 = 0
        # progress/cancel are optional hooks so a lab run keeps a live bar + a working Stop button
        # (the 1m stream is the long one — ~50k bars over a month). Both no-ops when not supplied.
        n1 = len(df1m.index)
        step1 = max(1, n1 // 100)
        for b1 in iter_bars(df1m):
            if b1.index % step1 == 0:
                if should_cancel is not None and should_cancel():
                    return self
                if progress is not None:
                    progress(b1.index, n1)
            # Flush every 15m bar that has CLOSED by the time this 1m bar opens — the primary path,
            # unchanged from run(). Its output becomes the 15m context the secondary reads next.
            while i15 < n15 and close15[i15] <= b1.timestamp_ms:
                b15 = bars15[i15]
                state = stack.step(b15)
                last_sig = self.signals.update(state)
                last_seq = self.sequence.update(last_sig)
                dec = self.execution.step(last_sig, last_seq)
                last_close15 = b15.close
                if b15.index >= warmup:
                    self.decisions.append(dec)
                i15 += 1

            m1 = struct1m.update(b1.index, b1.open, b1.high, b1.low, b1.close)
            if self.config.exec_secondary and last_sig is not None:
                ny_hour = datetime.fromtimestamp(b1.timestamp_ms / 1000.0, tz=timezone.utc) \
                    .astimezone(ny).hour
                arm = arm_sm.update(m1, last_sig, last_seq, last_close15, ny_hour,
                                    self.execution.is_flat, self.execution.be_sos_l,
                                    self.execution.be_sos_s)
                sig1m = _Bar1mSig(b1.index, b1.timestamp_ms, b1.open, b1.high, b1.low, b1.close)
                filled = self.execution.step_secondary(sig1m, arm)
                if filled is not None:
                    arm_sm.mark_traded(filled)   # retire the just-filled 1m leg
                elif self.execution.sec_stop_dir is not None:
                    # a re-entry hit its initial stop → kill this 15m leg (no more re-entries)
                    arm_sm.mark_dead(self.execution.sec_stop_dir, last_seq)

        # Flush any 15m bars after the last 1m bar (window tail).
        while i15 < n15:
            b15 = bars15[i15]
            state = stack.step(b15)
            last_sig = self.signals.update(state)
            last_seq = self.sequence.update(last_sig)
            dec = self.execution.step(last_sig, last_seq)
            if b15.index >= warmup:
                self.decisions.append(dec)
            i15 += 1
        return self
