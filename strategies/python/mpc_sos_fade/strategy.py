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
    def __init__(
        self,
        config: Optional[SosFadeConfig] = None,
        initial_capital: float = 1_000_000.0,
        tick_source=None,
        cost_profile=None,
        account=None,
        leg: str = "strat",
    ) -> None:
        self.config = config or SosFadeConfig()
        self.signals = SignalAdapter(self.config)
        self.sequence = SosFadeSequence(self.config)
        resolver, profile = self._fill_model(tick_source, cost_profile)
        # `account` is the SHARED account when this bot is one leg of a stack — it owns the
        # balance every leg sizes against and the risk budget they compete for. Omit it (the
        # default) and Execution builds its own SoloAccount, which is byte-identical to the
        # standalone behaviour this bot's parity gate was measured on. `leg` is this leg's key
        # in that account and MUST be distinct per leg: the account holds one open position per
        # key, so two legs sharing a name would overwrite each other's reservation and the cap
        # would silently under-count the open risk. See backtest/portfolio/.
        self.execution = Execution(
            self.config,
            initial_capital=initial_capital,
            resolver=resolver,
            profile=profile,
            account=account,
            leg=leg,
        )
        # What a pre-trade setup alert calls this bot. REPORTING ONLY — it names the STRATEGY,
        # which `Execution` cannot know: `mpc_bleg` and `mpc_bos` share this execution layer, so
        # its own class name would label all three "Execution" in Telegram. Set here because the
        # strategy is the only object that knows which of them it is.
        self.execution.strategy_name = type(self).__name__
        self.decisions: List[Decision] = []

    def _fill_model(self, tick_source, cost_profile=None):
        """Build the A2 resolver + cost profile from config. `(None, None)` is bar mode — the
        Pine's guess with no costs, which is what `compare_strategy.py` must run.

        `cost_profile` is the caller's own `AccountProfile`, and it is how a BAR-mode run gets
        priced: bar mode is the Pine's fill guess, not a claim that trading is free, so a caller
        that knows its commission and slippage may state them and have them charged. It is
        ignored in tick mode, where the profile is a property of the account being simulated and
        the slippage is measured off the tape. Omit it (the default) and bar mode is byte-identical
        to what it has always been — which is what keeps `compare_strategy.py` a valid gate.
        """
        cfg = self.config
        if cfg.fill_model == "bar":
            return None, cost_profile
        if cfg.fill_model != "tick":
            raise ValueError(f"fill_model must be 'bar' or 'tick', got {cfg.fill_model!r}")
        from backtest.fills import PROFILES, TickPathResolver

        if cfg.account_profile not in PROFILES:
            raise ValueError(
                f"account_profile {cfg.account_profile!r} unknown — tick mode prices real costs, "
                f"so it needs a real account. Pick one of: {sorted(PROFILES)}"
            )
        if not cfg.symbol:
            raise ValueError("tick mode needs config.symbol (the broker symbol to pull ticks for)")
        profile = PROFILES[cfg.account_profile]
        if tick_source is None:
            from backtest.data.mt5_agent import Mt5Agent
            from backtest.data.ticks import TickSource

            tick_source = TickSource(Mt5Agent())
        resolver = TickPathResolver(tick_source, cfg.symbol, latency_ms=profile.latency_ms)
        return resolver, profile

    def stack_config(self, engine_config=None):
        """The `EngineConfig` this instance's own settings require.

        `engine_config()` is a STATIC description of the Pine's engine constants and stays that way
        — `compare_strategy.py`, `mpc_bleg` and the parity tests all call it off the class. This is
        the per-INSTANCE layer on top: `exec_poi_source` decides whether the order-block engine has
        to run, and only an instance knows its own config.

        ⚠ **A caller that drives `step()` with its own stack must apply this too.** `step()` takes a
        pre-built `BarState`, so the live runner and the optimizer build the stack themselves; one
        that skips this hands the strategy a state with `order_blocks=None`. That does not silently
        degrade — `pois_for()` raises — which is the whole reason this returns a config rather than
        mutating something later.
        """
        base = engine_config or self.engine_config()
        if self.config.exec_poi_source != "FVG" and not base.order_blocks:
            import dataclasses

            return dataclasses.replace(base, order_blocks=True)
        return base

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
        `fvgRequireClose` — `mpc_strategy.pine` HARDCODES the middle-bar close-cleared check
        (`close[1] > high[2]` / `close[1] < low[2]`, lines 1686/1688), i.e. it is permanently ON
        there, while the FVG engine defaults it OFF (mirroring `mpc_assistant.pine`, which
        exposes it as an input defaulting off). Left unpinned, the engine creates gaps the Pine
        never did — caught 2026-07-26 as the single parity mismatch on a fresh export: a
        weekend-gap bar whose middle candle never closed past the void produced a Python-only
        entry edge. Do not "simplify" this back to the engine default.
        `fvgThreshPct` — the minimum-gap floor. `mpc_strategy.pine` splits it by timeframe
        (`fvgThreshLTF` 0.0 below 15m / `fvgThreshHTF` **0.1** at 15m and above, lines 116-118)
        and this bot trades 15m, so 0.1 is the value that must reach the engine. Note the
        indicator uses **0.04** at 15m and the engine default mirrors the indicator, so the two
        Pines genuinely disagree here and neither default can be right for both.
        **This pin was MISSING until 2026-07-31** — the bot happened to work only because
        `EngineConfig` carried 0.1 as its own default, which was never a decision. Proven
        load-bearing by removing it: `compare_strategy.py` failed on the first compared bar
        (`px_edge` py=3478.99 vs pine=3475.43). Same class as `fvg_require_close` below.
        `eqExemptFvg` — a gap sitting on an active EQH/EQL is exempt from the cap above and lives
        until price mitigates it, so `fvg_max_count` bounds the ORDINARY gaps only. It is an input
        in `mpc_strategy.pine` and has DEFAULTED ON there since 2026-08-03 (`b1b461b`).
        🔴 **Left unpinned it put this gate RED for three days**, and nothing could say why: at bar
        11031 of the 21,999-bar export Pine still held a bearish gap born 143 bars earlier, pinned
        by liquidity, and rested the limit on its edge at 4965.73, while Python — having FIFO-
        dropped it — snapped to fib 0.702 at 4990.02. The mismatch reads as an entry-rule
        disagreement and is not one; `_fib_snap` is line-for-line identical on both sides.
        ⚠ **This one DOES vary per run** (unlike the four above, which mirror Pine constants), so
        it is exported as `cfg_eq_exempt` and `compare_strategy.py` configures the bot FROM the
        export. A run replaying an export that predates that column is configured OFF.
        If a bot ever tunes another engine input off its default, add it here (and export it
        if it must vary per run)."""
        from backtest.replay import EngineConfig

        return EngineConfig(
            fvg_max_count=7,
            show_internal=False,
            fvg_require_close=True,
            fvg_threshold_pct=0.1,
            eq_exempt_fvg=True,
        )

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

        stack = EngineStack(self.stack_config(engine_config))
        for bar in iter_bars(df):
            state = stack.step(bar)
            sig = self.signals.update(state)
            seq = self.sequence.update(sig)
            dec = self.execution.step(sig, seq)
            if bar.index >= warmup:
                self.decisions.append(dec)
        return self

    def run_dual(
        self, df15, df1m, engine_config=None, warmup: int = 0, progress=None, should_cancel=None
    ) -> "MpcSosFadeStrategy":
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

        # `last_conf_high`/`last_conf_low` are the STRUCTURE runner trail's anchors, read by the
        # shared `_advance_stage` on every managed bar — primary or secondary. They were missing
        # here until 2026-08-06, so the FIRST 1m bar after any secondary fill raised
        # `AttributeError`: the re-entry had never once opened a position on real data. They come
        # from the last-CLOSED 15m signal, deliberately: the secondary's whole ladder is 15m fibs
        # (TP1 0.5, TP2 0.382) and it shares the parent's exit ladder, so its runner must trail the
        # same 15m confirmed swings the primary does. `Structure1m` is for the 1m SOS latch only.
        _Bar1mSig = namedtuple(
            "_Bar1mSig", "index time_ms open high low close last_conf_high last_conf_low"
        )
        ny = ZoneInfo("America/New_York")

        if len(df15.index) > 1:
            tf15_ms = int(df15.index.to_series().diff().min().total_seconds() * 1000)
            self.execution.bar_ms = tf15_ms
        else:
            tf15_ms = 900_000

        stack = EngineStack(self.stack_config(engine_config))
        bars15 = list(iter_bars(df15))
        close15 = [b.timestamp_ms + tf15_ms for b in bars15]  # when each 15m bar is known
        n15 = len(bars15)
        struct1m = Structure1m(major_length=(engine_config or self.engine_config()).major_length)
        arm_sm = SecondaryArm(self.config)

        last_sig = last_seq = None
        last_close15 = (
            None  # the last-CLOSED 15m bar's close — the zone gate reads this (Pine's 15m `close`)
        )
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
                ny_hour = (
                    datetime.fromtimestamp(b1.timestamp_ms / 1000.0, tz=timezone.utc)
                    .astimezone(ny)
                    .hour
                )
                arm = arm_sm.update(
                    m1,
                    last_sig,
                    last_seq,
                    last_close15,
                    ny_hour,
                    self.execution.is_flat,
                    self.execution.be_sos_l,
                    self.execution.be_sos_s,
                )
                sig1m = _Bar1mSig(
                    b1.index,
                    b1.timestamp_ms,
                    b1.open,
                    b1.high,
                    b1.low,
                    b1.close,
                    last_sig.last_conf_high,
                    last_sig.last_conf_low,
                )
                filled = self.execution.step_secondary(sig1m, arm)
                if filled is not None:
                    arm_sm.mark_traded(filled)  # retire the just-filled 1m leg
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
