"""EngineStack — drives the canonical engines bar-by-bar in Pine order.

One `step(bar)` call feeds a single closed bar through every engine the A+ setup
reads, in the exact order the Pine evaluates them:

    structure -> order blocks -> fib (structure/sniper/macro/internal) -> FVG
    -> RSI-divergence -> liquidity -> sessions

and returns a `BarState` bundling this bar plus every engine's events for it. The
stack owns the engine instances (so a consumer can also read live engine state —
active fib levels, active FVGs, active liquidity levels — off the event objects),
and it NEVER reimplements any detection: it imports the canonical `engines/` and
calls them, matching the "replay, don't reinvent" rule in this package's CLAUDE.md.
"""

from __future__ import annotations

import sys
from dataclasses import dataclass
from pathlib import Path

# Put engines/ on sys.path so the canonical engines import by bare name, matching
# the repo-wide "dir-on-path, import bare" convention (see algos/shared shims and
# the root conftest.py). backtest/ is a top-level sibling of engines/.
_ENGINES = Path(__file__).resolve().parent.parent.parent / "engines"
if str(_ENGINES) not in sys.path:
    sys.path.insert(0, str(_ENGINES))

import pandas as pd  # noqa: E402
from equal_highs_lows import EqualHighsLowsEngine  # noqa: E402
from fair_value_gaps import FairValueGapEngine, FvgEvents  # noqa: E402
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
from liquidity import LiquidityEngine, LiquidityEvents  # noqa: E402
from market_structure import Bar, StructureEngine, StructureEvents  # noqa: E402
from order_blocks import OrderBlockEngine, OrderBlockEvents  # noqa: E402
from rsi_divergence import RsiDivergenceEngine, RsiDivEvents  # noqa: E402
from sessions import SessionEngine, SessionEvents  # noqa: E402

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
    # fair_value_gaps. These mirror the ENGINE defaults (== `mpc_jarvis.pine`, the indicator),
    # NOT any one strategy — this package is strategy-agnostic and cannot encode one bot's tuning.
    # A consumer replaying a specific Pine must pin every value that Pine does not leave at the
    # engine default; see the unpinned-engine-input rule in `backtest/CLAUDE.md`.
    #
    # ⚠ `fvg_threshold_pct` is LOAD-BEARING and was 0.1 here until 2026-07-31 — not as a considered
    # default but because `sos_fade` silently relied on it (it pins max_count and require_close
    # and forgot this one). `sos_fade_strategy.pine`'s 15m floor is 0.1 while the indicator's is 0.04,
    # so the bot now pins 0.1 explicitly and this default is free to mirror the engine again.
    # Verified the hard way: setting this to 0.0 while the bot was unpinned broke
    # `compare_strategy.py` on the first compared bar (`px_edge` 3478.99 vs 3475.43).
    fvg_max_count: int = 8
    fvg_threshold_pct: float = 0.0
    # Middle-bar close-cleared requirement (Pine `fvgRequireClose`). `mpc_jarvis.pine`
    # exposes it as an input defaulting OFF — the classic 3-candle FVG — which is why this
    # defaults False. But `sos_fade_strategy.pine` HARDCODES the check (`close[1] > high[2]` /
    # `close[1] < low[2]`), so a consumer replaying THAT Pine must pin this True or it will
    # hold gaps the Pine never created. Same class of trap as `fvg_max_count`: an engine
    # input the decision stream does not export, so the consumer has to know it.
    fvg_require_close: bool = False
    # Pine `eqExemptFvg` — an FVG sitting on an active EQH/EQL is exempt from the FVG cap and lives
    # until price mitigates it. OFF here because it is an input in every Pine that has it, and
    # because turning it on CHANGES WHICH GAPS EXIST, hence which entries fire. `sos_fade_strategy.pine`
    # has defaulted it ON since 2026-08-03 and `sos_fade` pins it True to match.
    #
    # 🔴 This is what put `compare_strategy.py` RED for three days (found 2026-08-06). The Pine
    # defaulted it on while nothing here wired the EQ engine into the FVG engine at all, so the two
    # sides evicted different gaps: at bar 11031 of the 21,999-bar export Pine still held a bearish
    # gap born 143 bars earlier, pinned by liquidity, and rested the limit on its edge at 4965.73
    # while Python — having FIFO-dropped it — snapped to fib 0.702 at 4990.02. **No `cfg_` column
    # carried the input, so the harness could not see the difference and blamed the entry rule.**
    # A trade-affecting Pine input with no export column is invisible to the gate by construction.
    eq_exempt_fvg: bool = False
    # equal_highs_lows — LOCKED to mpc's constants (`eqPivotLen` / `eqAtrMult` / `eqMax`), which are
    # hardcoded in the Pine rather than exposed, so the indicator and the strategy cannot draw
    # different levels. Only read when `eq_exempt_fvg` is on.
    eq_pivot_len: int = 2
    eq_atr_mult: float = 0.1
    eq_max_levels: int = 6
    # order_blocks — OPT-IN, and off by default for the same reason the EQ engine is: no strategy
    # in this repo reads an order block today (`sos_fade`, `b_leg` and `bos` all ignore
    # them), and an unused engine still costs a per-bar ATR, two pivot scans and a live-zone walk on
    # every replay, sweep combo and optimizer core in the repo.
    # ⚠ MEASURED rather than assumed, because "it is probably cheap" is how a default gets chosen
    # badly: 5,760 synthetic bars, best of 3 — 328.5 ms off vs 386.7 ms on, **+17.7%** (57.0 → 67.1
    # us/bar). That is per combo, so a 1,000-combo sweep pays it a thousand times for output nothing
    # reads. Off keeps every existing result byte-identical AND costing exactly what it did before;
    # a future strategy that wants blocks turns it on and pays for them.
    #
    # ⚠ THERE ARE DELIBERATELY NO OB TUNING FIELDS HERE, and that is the repo's own rule rather than
    # laziness: "nothing in the config may exist without a Pine input behind it" (the BosConfig
    # lesson, 2026-08-07). Every OB constant — max_age, min_back, max_atr, dupe_overlap, disp_mult,
    # the turn/push windows — is HARDCODED in `mpc_jarvis.pine`, not exposed as an input, so a
    # field here could never be carried by an export column and no parity gate could ever check it.
    # `maxActiveOB` was the last real input and it was locked to 10 on 2026-07-31. The engine
    # defaults therefore ARE the Pine constants, and there is nothing to pin. If mpc ever re-exposes
    # one as an `input.*`, add the field THEN, with the export column in the same commit.
    order_blocks: bool = False
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
    # None = the stack was built with `order_blocks=False`, i.e. the question was never asked.
    # An OrderBlockEvents with empty lists means the engine RAN and found nothing this bar.
    # Those are different facts and must not share a value — the `mt5_link` rule, which this repo
    # has now met on the live bot's terminal probe, the optimizer's sensitivity score and the news
    # calendar's coverage. A strategy that reads `state.order_blocks.active_bull` on a stack that
    # never ran the engine gets an AttributeError, which is the loud failure; an empty list would
    # silently read as "no blocks here" and the strategy would take no trades while looking healthy.
    order_blocks: OrderBlockEvents | None = None


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
            max_count=c.fvg_max_count,
            threshold_pct=c.fvg_threshold_pct,
            require_close=c.fvg_require_close,
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
        # Only built when the coupling is on: an unused engine still costs a per-bar ATR and a
        # pivot scan on every replay in the repo, and the flag is off for every consumer but one.
        self.eq = (
            EqualHighsLowsEngine(
                pivot_len=c.eq_pivot_len,
                atr_mult=c.eq_atr_mult,
                max_levels=c.eq_max_levels,
            )
            if c.eq_exempt_fvg
            else None
        )
        # Same opt-in shape as `eq`, same reason — see `EngineConfig.order_blocks`. Built with no
        # kwargs: the engine's defaults ARE mpc_jarvis.pine's constants (max_active=10,
        # body_only=False, …), and that Pine is the only OB source left in the repo since the
        # strategy files dropped order blocks on 2026-07-24/25.
        self.order_blocks = OrderBlockEngine() if c.order_blocks else None

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

        # Order blocks sit HERE, immediately after the structure engine and before everything else,
        # because that is where mpc_jarvis.pine runs them (`extendOBs` then the push/turn
        # creation sites, ~L2158-2790 — after `st.process`, before the internal block, EQ and FVG).
        # ⚠ The position is currently behaviour-NEUTRAL and it is worth knowing why, so nobody
        # "tidies" it later: this engine is STANDALONE (plain OHLC in, no snapshot since the
        # 2026-07-31 re-port) and nothing downstream reads its output, so no other engine can see
        # it move. It is placed faithfully anyway — the day something does read it, the order is
        # already the Pine's and not a thing to rediscover.
        ob_ev = self.order_blocks.update(i, o, h, l, c) if self.order_blocks else None

        fib_ev = self.fib.update(h, l, snap)
        sniper_ev = self.sniper.update(h, l, snap)
        macro_ev = self.macro.update(i, h, l, c, snap)
        internal_ev = self.internal.update(i, h, l, snap)

        # EQ runs BEFORE FVG, the Pine order — the exemption tests this bar's active levels, and
        # the tolerance is this bar's ATR(50). Passing None/0.0 is the exemption-off path and leaves
        # the cap a plain FIFO, byte-identical to a stack built without the EQ engine.
        eq_levels, eq_tol = None, 0.0
        if self.eq is not None:
            eq_ev = self.eq.update(i, h, l, c)
            eq_levels = eq_ev.active_eqh + eq_ev.active_eql
            eq_tol = eq_ev.tolerance
        fvg_ev = self.fvg.update(i, o, h, l, c, eq_levels=eq_levels, eq_tol=eq_tol)
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
            order_blocks=ob_ev,
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
