"""
fibonacci/types.py — plain data containers for the fib engines.

No behavior lives here. Two kinds of container:

  StructureSnapshot — the fibs' INPUT. The exact subset of the market-structure engine's PUBLIC
    output the fibs read each bar (active swing, trend, live pullback extreme, break events + the
    impulse-leg endpoints, last-confirmed swings). Build one per bar with
    StructureSnapshot.from_engine(engine, events). This keeps fibonacci/ decoupled from
    market_structure/'s internals — it depends only on documented reads/events, never private state.

  *FibEvents — the fibs' OUTPUT. What the fib knows this bar: which levels were first-touched
    (edge-triggered, like the JARVIS table's `X and not X[1]`), whether a new leg started, and the
    current level prices. Colours/lines are deliberately absent — those are TradingView visuals; a
    consumer that wants to draw can, but the trading signal is the touch events.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Optional, Set


@dataclass
class StructureSnapshot:
    """Everything the three fibs read out of the structure engine on one bar.

    Mirrors the `st.*` fields mpc_assistant.pine's fib blocks reference. All optional fields are
    None when absent. Built from a StructureEngine + its StructureEvents for that bar.
    """

    # Active swing high/low + their bar locations, and the external trend (1/-1/0).
    ash: Optional[float] = None
    ash_loc: Optional[int] = None
    asl: Optional[float] = None
    asl_loc: Optional[int] = None
    direction: int = 0

    # Live, in-progress pullback extreme — lets the Structure fib follow the high/low during a
    # pullback exactly as Pine does (fibo_ash := st.pb_extreme while pb_mode == 1).
    pb_mode: int = 0
    pb_extreme: Optional[float] = None
    pb_extreme_loc: Optional[int] = None

    # Last CONFIRMED swing high/low + locations — the Macro fib's cycle anchors.
    last_conf_high: Optional[float] = None
    last_conf_high_loc: Optional[int] = None
    last_conf_low: Optional[float] = None
    last_conf_low_loc: Optional[int] = None

    # Break events THIS bar. bos = continuation break, sos = trend-flip (CHoCH) break.
    bull_bos: bool = False
    bear_bos: bool = False
    bull_sos: bool = False
    bear_sos: bool = False

    # The impulse LEG of a BOS (both endpoints), fired on the break bar only — the Sniper fib's
    # anchor. bull: high = broken ASH, low = swing low it launched from; bear mirror.
    bull_bos_high: Optional[float] = None
    bull_bos_h_loc: Optional[int] = None
    bull_bos_low: Optional[float] = None
    bull_bos_l_loc: Optional[int] = None
    bear_bos_high: Optional[float] = None
    bear_bos_h_loc: Optional[int] = None
    bear_bos_low: Optional[float] = None
    bear_bos_l_loc: Optional[int] = None

    # Latest CONFIRMED internal swing (price + loc), fired on the iSH/iSL confirm bar only — the
    # Structure fib adopts a more-extreme internal swing as its pull anchor. Latched + reset by the
    # StructureFib itself (Pine keeps `i_confirmed_*` as a var reset on the fib's origin change).
    i_confirmed_high_price: Optional[float] = None
    i_confirmed_high_loc: Optional[int] = None
    i_confirmed_low_price: Optional[float] = None
    i_confirmed_low_loc: Optional[int] = None

    # Internal-fib SEED — the internal leg (low + high + dir) that just broke, on the iBOS/iSOS bar
    # only. The InternalFib runs its own live-extend + touch machine off this seed.
    ifib_seed_dir: Optional[int] = None
    ifib_seed_asl: Optional[float] = None
    ifib_seed_asl_loc: Optional[int] = None
    ifib_seed_ash: Optional[float] = None
    ifib_seed_ash_loc: Optional[int] = None

    @classmethod
    def from_engine(cls, engine, events) -> "StructureSnapshot":
        """Build the snapshot from a market_structure StructureEngine and the StructureEvents it
        just returned for this bar. `engine` is read AFTER `engine.update(bar)`; `events` is that
        call's return value."""
        ash = engine.active_swing_high
        asl = engine.active_swing_low
        lch = engine.last_confirmed_high
        lcl = engine.last_confirmed_low
        e = events.external
        i = events.internal
        return cls(
            ash=ash.price if ash else None,
            ash_loc=ash.index if ash else None,
            asl=asl.price if asl else None,
            asl_loc=asl.index if asl else None,
            direction=engine.dir,
            pb_mode=engine.pullback_mode,
            pb_extreme=engine.pullback_extreme,
            pb_extreme_loc=engine.pullback_extreme_loc,
            last_conf_high=lch.price if lch else None,
            last_conf_high_loc=lch.index if lch else None,
            last_conf_low=lcl.price if lcl else None,
            last_conf_low_loc=lcl.index if lcl else None,
            bull_bos=e.bull_bos,
            bear_bos=e.bear_bos,
            bull_sos=e.bull_sos,
            bear_sos=e.bear_sos,
            bull_bos_high=e.bull_bos_high,
            bull_bos_h_loc=e.bull_bos_h_loc,
            bull_bos_low=e.bull_bos_low,
            bull_bos_l_loc=e.bull_bos_l_loc,
            bear_bos_high=e.bear_bos_high,
            bear_bos_h_loc=e.bear_bos_h_loc,
            bear_bos_low=e.bear_bos_low,
            bear_bos_l_loc=e.bear_bos_l_loc,
            i_confirmed_high_price=i.i_confirmed_high_price,
            i_confirmed_high_loc=i.i_confirmed_high_loc,
            i_confirmed_low_price=i.i_confirmed_low_price,
            i_confirmed_low_loc=i.i_confirmed_low_loc,
            ifib_seed_dir=i.ifib_seed_dir,
            ifib_seed_asl=i.ifib_seed_asl,
            ifib_seed_asl_loc=i.ifib_seed_asl_loc,
            ifib_seed_ash=i.ifib_seed_ash,
            ifib_seed_ash_loc=i.ifib_seed_ash_loc,
        )


@dataclass(frozen=True)
class FibTouch:
    """One fib level being reached for the first time on this leg."""
    level: str        # "E1", "TP1", "1.0", ...
    ratio: float      # 0.618, 0.500, ...
    price: float      # the level's price
    role: str         # "entry" (retracement side) | "target" (profit side)


@dataclass
class StructureFibEvents:
    """The Structure fib's per-bar output."""

    active: bool = False                              # anchors valid -> a fib is currently drawn
    origin_changed: bool = False                      # new leg started this bar (touched all reset)
    direction: int = 0                                # 1 bull, -1 bear, 0 none
    touched: List[FibTouch] = field(default_factory=list)   # levels first-touched THIS bar (events)
    levels: Dict[str, float] = field(default_factory=dict)  # current price of every level (state)
    touched_so_far: Set[str] = field(default_factory=set)   # cumulative touched names this leg
    reset_active: bool = False                        # TP3 (0.0) hit -> leg spent/hidden until new leg


@dataclass
class MacroFibEvents:
    """The Macro cycle fib's per-bar output.

    The Macro fib spans a whole bull cycle: its bottom (LL / 1.0) locks on a bullish SOS after a
    bearish SOS, and its top (HH / 0.0) extends across every new confirmed higher-high until price
    closes back below the locked bottom (which resets the cycle). It emits the same first-touch
    level events as the Structure fib, plus two lifecycle events: `new_cycle` (the cycle locked
    this bar) and `extended` (the top pushed to a new HH this bar). Only runs on <=5m timeframes.
    See mpc_assistant.pine GRP_MACRO.
    """

    active: bool = False                              # levels currently computed (visible + locked + range>0)
    direction: int = 0                                # 1 while a cycle is live (bull-only), 0 otherwise
    top: Optional[float] = None                       # macro_extreme — the HH (0.0 level)
    bot: Optional[float] = None                       # macro_origin — the LL (1.0 level)
    locked: bool = False                              # a cycle bottom is locked (may be hidden)
    visible: bool = False                             # the fib is currently shown (hidden above the top)
    new_cycle: bool = False                           # a fresh cycle locked THIS bar — event
    extended: bool = False                            # the top extended to a new HH THIS bar — event
    touched: List[FibTouch] = field(default_factory=list)   # levels first-touched THIS bar (events)
    levels: Dict[str, float] = field(default_factory=dict)  # current price of every level (state)
    touched_so_far: Set[str] = field(default_factory=set)   # cumulative touched names this cycle-range


@dataclass
class SniperFibEvents:
    """The Sniper fib's per-bar output.

    The Sniper fib is a single 0.382-0.5 zone drawn off the BOS impulse leg. It has no per-level
    touch machine like the Structure fib — just two events: `created` (a BOS fired, a fresh zone
    replaced any old one) and `confirmed` (price entered the zone for the first time on this
    zone). `zone_active` is the cumulative latch behind `confirmed`; once a zone is entered it
    cannot re-confirm until the next BOS resets it. See mpc_assistant.pine GRP_SNIPER.
    """

    active: bool = False                 # a zone currently exists (a BOS has fired at least once)
    direction: int = 0                   # 1 bull zone, -1 bear zone, 0 none
    zone_top: Optional[float] = None     # upper edge (max of the 0.382 / 0.5 levels)
    zone_bot: Optional[float] = None     # lower edge (min of the 0.382 / 0.5 levels)
    created: bool = False                # a fresh zone was set THIS bar (a BOS fired) — event
    confirmed: bool = False              # price entered the zone for the first time THIS bar — event
    zone_active: bool = False            # cumulative latch: price has entered the current zone


@dataclass
class InternalFibEvents:
    """The Internal fib's per-bar output (the 4th fib, GRP_IFIB).

    Anchored to the internal-structure leg that just broke (an iBOS/iSOS). Its anchor extends live
    with the move; its 8 levels (E1-E4, 1.0, TP1-TP3) register first touches on the same 0.618
    gate as the other fibs. Hitting TP3 (0.0) latches `reset_active` (the leg is spent). ANY
    external BOS/SOS clears the whole fib, which then waits for the next iBOS/iSOS. See
    mpc_assistant.pine's Internal Fib block.
    """

    active: bool = False                              # anchors valid -> a fib is currently drawn
    direction: int = 0                                # 1 bull leg, -1 bear leg, 0 none
    top: Optional[float] = None                       # iFib_ash — the 0.0 anchor (bull) / 1.0 (bear)
    bot: Optional[float] = None                       # iFib_asl — the 1.0 anchor (bull) / 0.0 (bear)
    seeded: bool = False                              # a fresh internal leg seeded THIS bar — event
    cleared: bool = False                             # an external BOS/SOS wiped the fib THIS bar — event
    reset_active: bool = False                        # TP3 (0.0) hit -> leg spent until re-seed/clear
    touched: List[FibTouch] = field(default_factory=list)   # levels first-touched THIS bar (events)
    levels: Dict[str, float] = field(default_factory=dict)  # current price of every level (state)
    touched_so_far: Set[str] = field(default_factory=set)   # cumulative touched names this leg
