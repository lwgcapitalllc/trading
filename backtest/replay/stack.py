"""EngineStack — drives the canonical engines bar-by-bar in Pine order.

One `step(bar)` call feeds a single closed bar through every engine the A+ setup
reads, in the exact order the Pine evaluates them:

    structure -> fib (structure/sniper/macro/internal) -> FVG -> RSI-divergence
    -> liquidity -> sessions

and returns a `BarState` bundling this bar plus every engine's events for it. The
stack owns the engine instances (so a consumer can also read live engine state —
active fib levels, active FVGs, active liquidity levels — off the event objects),
and it NEVER reimplements any detection: it imports the canonical `engines/` and
calls them, matching the "replay, don't reinvent" rule in this package's CLAUDE.md.
"""

from __future__ import annotations

import sys
from dataclasses import dataclass, field
from pathlib import Path

# Put engines/ on sys.path so the canonical engines import by bare name, matching
# the repo-wide "dir-on-path, import bare" convention (see algos/shared shims and
# the root conftest.py). backtest/ is a top-level sibling of engines/.
_ENGINES = Path(__file__).resolve().parent.parent.parent / "engines"
if str(_ENGINES) not in sys.path:
    sys.path.insert(0, str(_ENGINES))

from market_structure import Bar, StructureEngine, StructureEvents  # noqa: E402
from fibonacci import (  # noqa: E402
    InternalFib,
    InternalFibEvents,
    MacroFib,
    MacroFibEvents,
    SniperFib,
    SniperFibEvents,
    StructureFib,
    StructureFibEvents,
    StructureSnapshot,
)
from fair_value_gaps import FairValueGapEngine, FvgEvents  # noqa: E402
from rsi_divergence import RsiDivergenceEngine, RsiDivEvents  # noqa: E402
from liquidity import LiquidityEngine, LiquidityEvents  # noqa: E402
from sessions import SessionEngine, SessionEvents  # noqa: E402

import pandas as pd  # noqa: E402

from .loop import ReplayBar, iter_bars


@dataclass(frozen=True)
class EngineConfig:
    """Construction parameters for the engine stack — each defaults to the same
    value the underlying engine (and the Pine) defaults to, so the stack is
    Pine-faithful out of the box. Full input-toggle parity is deliberately left
    to the strategy layer (Deliverable B); this covers what the engines expose at
    construction time."""

    # market_structure
    major_length: int = 15
    # Internal-structure exposure. The market_structure engine ALWAYS computes internal
    # structure, but the Pine gates the whole internal block behind `showInternal`
    # (`internalActive = showInternal`) — and when it is OFF, the internal-confirmed swings
    # (`i_confirmed_*`) are never set, so the Structure fib never adopts a more-extreme
    # internal swing as its pull anchor. Mirror that here: False blanks the snapshot's
    # internal-derived fields before the fibs read them. Default True keeps the canonical
    # behaviour the fib-parity harness (fib_export.pine, showInternal ON) was validated at.
    show_internal: bool = True
    # fair_value_gaps. These mirror the ENGINE defaults (== `mpc_assistant.pine`, the indicator),
    # NOT any one strategy — this package is strategy-agnostic and cannot encode one bot's tuning.
    # A consumer replaying a specific Pine must pin every value that Pine does not leave at the
    # engine default; see the unpinned-engine-input rule in `backtest/CLAUDE.md`.
    #
    # ⚠ `fvg_threshold_pct` is LOAD-BEARING and was 0.1 here until 2026-07-31 — not as a considered
    # default but because `mpc_sos_fade` silently relied on it (it pins max_count and require_close
    # and forgot this one). `mpc_strategy.pine`'s 15m floor is 0.1 while the indicator's is 0.04,
    # so the bot now pins 0.1 explicitly and this default is free to mirror the engine again.
    # Verified the hard way: setting this to 0.0 while the bot was unpinned broke
    # `compare_strategy.py` on the first compared bar (`px_edge` 3478.99 vs 3475.43).
    fvg_max_count: int = 8
    fvg_threshold_pct: float = 0.0
    # Middle-bar close-cleared requirement (Pine `fvgRequireClose`). `mpc_assistant.pine`
    # exposes it as an input defaulting OFF — the classic 3-candle FVG — which is why this
    # defaults False. But `mpc_strategy.pine` HARDCODES the check (`close[1] > high[2]` /
    # `close[1] < low[2]`), so a consumer replaying THAT Pine must pin this True or it will
    # hold gaps the Pine never created. Same class of trap as `fvg_max_count`: an engine
    # input the decision stream does not export, so the consumer has to know it.
    fvg_require_close: bool = False
    # rsi_divergence
    rsi_len: int = 14
    rsi_pivot_len: int = 5
    rsi_oversold: float = 25.0
    rsi_overbought: float = 75.0
    rsi_valid_bars: int = 100
    # liquidity — XAUUSD trading day opens 18:00 NY (the baked-in engine default)
    htf_rollover_hours: int = 18


@dataclass
class BarState:
    """Everything the engine stack produced for one bar — the seam the strategy
    reads. `snapshot` is the structure engine's public read for this bar; the fib /
    fvg / rsi / liquidity / sessions events each also carry their live `active`
    state where the engine exposes it."""

    bar: ReplayBar
    structure: StructureEvents
    snapshot: StructureSnapshot
    fib: StructureFibEvents
    sniper: SniperFibEvents
    macro: MacroFibEvents
    internal: InternalFibEvents
    fvg: FvgEvents
    rsi: RsiDivEvents
    liquidity: LiquidityEvents
    sessions: SessionEvents


class EngineStack:
    """Owns one instance of each canonical engine and steps them all per bar."""

    def __init__(self, config: EngineConfig | None = None) -> None:
        self.config = config or EngineConfig()
        c = self.config

        self.structure = StructureEngine(major_length=c.major_length)
        self.fib = StructureFib()
        self.sniper = SniperFib()
        self.macro = MacroFib()
        self.internal = InternalFib()
        self.fvg = FairValueGapEngine(
            max_count=c.fvg_max_count, threshold_pct=c.fvg_threshold_pct,
            require_close=c.fvg_require_close
        )
        self.rsi = RsiDivergenceEngine(
            rsi_len=c.rsi_len,
            pivot_len=c.rsi_pivot_len,
            oversold=c.rsi_oversold,
            overbought=c.rsi_overbought,
            valid_bars=c.rsi_valid_bars,
        )
        self.liquidity = LiquidityEngine(htf_rollover_hours=c.htf_rollover_hours)
        self.sessions = SessionEngine()

    def step(self, bar: ReplayBar) -> BarState:
        """Feed one closed bar through the whole stack in Pine order and return
        its combined state."""
        i, ts = bar.index, bar.timestamp_ms
        o, h, l, c = bar.open, bar.high, bar.low, bar.close

        structure_ev = self.structure.update(Bar(index=i, open=o, high=h, low=l, close=c))
        snap = StructureSnapshot.from_engine(self.structure, structure_ev)

        # Pine's internal block only runs when `showInternal` is on. With it off, the
        # internal-confirmed swings and the internal-fib seed are never set, so the
        # Structure fib never adopts an internal swing and the Internal fib stays inactive.
        if not self.config.show_internal:
            snap.i_confirmed_high_price = None
            snap.i_confirmed_high_loc = None
            snap.i_confirmed_low_price = None
            snap.i_confirmed_low_loc = None
            snap.ifib_seed_asl = None
            snap.ifib_seed_asl_loc = None
            snap.ifib_seed_ash = None
            snap.ifib_seed_ash_loc = None

        fib_ev = self.fib.update(h, l, snap)
        sniper_ev = self.sniper.update(h, l, snap)
        macro_ev = self.macro.update(i, h, l, c, snap)
        internal_ev = self.internal.update(i, h, l, snap)

        fvg_ev = self.fvg.update(i, o, h, l, c)
        rsi_ev = self.rsi.update(i, h, l, c)
        liq_ev = self.liquidity.update(i, ts, h, l, c)
        sess_ev = self.sessions.update(i, ts, h, l)

        return BarState(
            bar=bar,
            structure=structure_ev,
            snapshot=snap,
            fib=fib_ev,
            sniper=sniper_ev,
            macro=macro_ev,
            internal=internal_ev,
            fvg=fvg_ev,
            rsi=rsi_ev,
            liquidity=liq_ev,
            sessions=sess_ev,
        )


def run(df: pd.DataFrame, config: EngineConfig | None = None, warmup: int = 0):
    """Replay a canonical bar frame through a fresh EngineStack, yielding one
    BarState per bar. The first `warmup` bars still feed the engines (so their
    state is fully warm) but are not yielded — the same convention the parity
    harnesses use with `--warmup`. Consumers that want to own the stack should
    build an EngineStack and call `step` per `iter_bars(df)` bar instead."""
    stack = EngineStack(config)
    for bar in iter_bars(df):
        state = stack.step(bar)
        if bar.index >= warmup:
            yield state
