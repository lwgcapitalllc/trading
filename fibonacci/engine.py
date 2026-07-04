"""
fibonacci/engine.py — the fib state machines.

This module holds one small state machine per fib type. Each is fed one closed bar at a time
plus a StructureSnapshot (the structure engine's public output for that bar) and returns the
fib's events for that bar. The geometry itself is shared — see geometry.py.

Ported line-by-line from indicators/mpc_assistant.pine. As with market_structure/, do not
"clean up" or reorder the ported logic: the gating (0.618 must be reached before targets arm,
targets only from the NEXT bar, retrace levels only while price is at/through 0.618) is exact and
any change breaks parity with the chart.

Currently implemented:
  - StructureFib  (GRP_FIBO "Structure Fibonacci", Pine ~2009-2114) — the main retracement fib.
  - SniperFib     (GRP_SNIPER "Sniper Fib", Pine ~2510-2551 + zone-touch ~2788-2797) — the
                  BOS impulse-leg 0.382-0.5 confirmation zone.
  - MacroFib      (GRP_MACRO "Macro Cycle Fib", Pine ~2290-2432) — the multi-BOS bull-cycle fib.

All three fibs are ported.
"""

from __future__ import annotations

from typing import Dict, List, Optional, Tuple

from .geometry import fib_from_origin, fib_level, origin_index
from .types import FibTouch, MacroFibEvents, SniperFibEvents, StructureFibEvents, StructureSnapshot

# ── Structure fib levels, in Pine's own check order within each group ──
# Gate: 0.618 (E1) must be reached before anything else arms.
# Retrace group (checked while price is at/through 0.618, on the retracement side):
_STRUCT_RETRACE: Tuple[Tuple[str, float], ...] = (
    ("E1", 0.618),   # the gate itself, marked first
    ("E2", 0.702),
    ("E3", 0.786),
    ("E4", 0.886),
    ("1.0", 1.000),
)
# Target group (checked only from the bar AFTER 0.618 was first reached, on the profit side):
_STRUCT_TARGET: Tuple[Tuple[str, float], ...] = (
    ("TP1", 0.500),
    ("TP2", 0.382),
    ("TP3", 0.000),
    ("TP4", -0.270),
    ("TP5", -0.618),
)
_GATE = "E1"  # 0.618

_ROLE = {name: "entry" for name, _ in _STRUCT_RETRACE}
_ROLE.update({name: "target" for name, _ in _STRUCT_TARGET})
_RATIO = {name: r for name, r in (_STRUCT_RETRACE + _STRUCT_TARGET)}


class StructureFib:
    """The main structure retracement fib ("FFT").

    Anchors on the active swing high/low, and follows the live pullback extreme while a pullback
    is in progress — so it extends with the move exactly like the chart, then locks. Emits a
    first-touch event for each level, gated on 0.618. See mpc_assistant.pine GRP_FIBO.
    """

    def __init__(self) -> None:
        # Persistent anchors (Pine `var fibo_ash/asl/loc/dir`).
        self._ash: Optional[float] = None
        self._asl: Optional[float] = None
        self._ash_loc: Optional[int] = None
        self._asl_loc: Optional[int] = None
        self._dir: int = 0

        # Touched flags + the 0.618 gate latch + previous origin (Pine `var ...Touched`, etc.).
        self._touched = {name: False for name in _RATIO}
        self._gate_ever_reached = False
        self._start_index_prev: Optional[int] = None

    # ------------------------------------------------------------------
    def update(self, high: float, low: float, snap: StructureSnapshot) -> StructureFibEvents:
        """Feed one closed bar (its high/low) plus this bar's structure snapshot."""

        # ── Anchor update (Pine 2009-2023, runs unconditionally) ──
        if snap.ash is not None:
            self._ash = snap.ash
            self._ash_loc = snap.ash_loc
        if snap.asl is not None:
            self._asl = snap.asl
            self._asl_loc = snap.asl_loc
        if snap.direction != 0:
            self._dir = snap.direction

        # Follow the in-progress pullback extreme (Pine 2018-2023).
        if snap.pb_mode == 1 and snap.pb_extreme is not None:
            self._ash = snap.pb_extreme
            self._ash_loc = snap.pb_extreme_loc
        if snap.pb_mode == -1 and snap.pb_extreme is not None:
            self._asl = snap.pb_extreme
            self._asl_loc = snap.pb_extreme_loc

        # ── Guard: no fib until both anchors and a direction exist (Pine 2029) ──
        if self._ash is None or self._asl is None or self._dir == 0:
            return StructureFibEvents(active=False, direction=self._dir)

        d = self._dir
        # ── All level prices (Pine 2039-2048) ──
        levels = {name: fib_level(self._ash, self._asl, d, r) for name, r in _RATIO.items()}
        start_index = origin_index(d, self._ash_loc, self._asl_loc)

        # ── Origin change -> new leg: reset every touched flag + gate, skip checks this bar ──
        origin_changed = start_index != self._start_index_prev
        if origin_changed:
            for name in self._touched:
                self._touched[name] = False
            self._gate_ever_reached = False
        self._start_index_prev = start_index

        touched_now: List[FibTouch] = []

        if not origin_changed:
            # 0.618 reached? retracement-side test (Pine 2073).
            gate_price = levels[_GATE]
            gate_reached = (low <= gate_price) if d == 1 else (high >= gate_price)

            if gate_reached:
                # Mark the gate itself, then the deeper retrace levels — retracement-side test.
                for name, _ in _STRUCT_RETRACE:
                    if self._touched[name]:
                        continue
                    price = levels[name]
                    hit = (low <= price) if d == 1 else (high >= price)
                    if hit:
                        self._touched[name] = True
                        touched_now.append(FibTouch(name, _RATIO[name], price, _ROLE[name]))

            # Targets only after 0.618 was reached on a PREVIOUS bar — profit-side test (Pine 2095).
            if self._gate_ever_reached:
                for name, _ in _STRUCT_TARGET:
                    if self._touched[name]:
                        continue
                    price = levels[name]
                    hit = (high >= price) if d == 1 else (low <= price)
                    if hit:
                        self._touched[name] = True
                        touched_now.append(FibTouch(name, _RATIO[name], price, _ROLE[name]))

            # Latch the gate AFTER all checks, so targets never fire on the bar 0.618 was first hit.
            if gate_reached and not self._gate_ever_reached:
                self._gate_ever_reached = True

        return StructureFibEvents(
            active=True,
            origin_changed=origin_changed,
            direction=d,
            touched=touched_now,
            levels=levels,
            touched_so_far={name for name, hit in self._touched.items() if hit},
        )


# ── Sniper fib ratios (the two zone edges, measured from the impulse-leg origin) ──
_SNIPER_382 = 0.382
_SNIPER_500 = 0.500


class SniperFib:
    """The Sniper confirmation zone.

    On each BOS, drops a fresh 0.382-0.5 zone across the impulse leg (`bull/bear_bos_high/low`)
    and arms it. When price later trades into that zone for the first time, it "confirms". A new
    BOS replaces the zone and re-arms it. Only one zone lives at a time. Line-by-line port of
    mpc_assistant.pine GRP_SNIPER (compute + zone-touch), drawing removed.
    """

    def __init__(self) -> None:
        # Persistent zone (Pine `var sniperZoneTop/Bot/Active`) + the zone's direction.
        self._zone_top: Optional[float] = None
        self._zone_bot: Optional[float] = None
        self._zone_active: bool = False
        self._dir: int = 0

    # ------------------------------------------------------------------
    def update(self, high: float, low: float, snap: StructureSnapshot) -> SniperFibEvents:
        """Feed one closed bar (its high/low) plus this bar's structure snapshot."""

        # Pine gates on barstate.isconfirmed; on closed/historical bars that is always true, so a
        # BOS event this bar is the whole trigger (Pine 2512-2513).
        bull_bos = snap.bull_bos
        bear_bos = snap.bear_bos
        is_bos = bull_bos or bear_bos

        created = False
        # ── New zone on a BOS (Pine 2515-2544) ──
        if is_bos:
            bull = bull_bos  # Pine keys every ternary off _snBullBOS -> bull takes precedence
            snh = snap.bull_bos_high if bull else snap.bear_bos_high
            snl = snap.bull_bos_low if bull else snap.bear_bos_low
            d = 1 if bull else -1
            sn382 = fib_from_origin(snh, snl, d, _SNIPER_382)  # bull: snl + r*0.382 ; bear: snh - r*0.382
            sn50 = fib_from_origin(snh, snl, d, _SNIPER_500)
            self._zone_top = max(sn382, sn50)
            self._zone_bot = min(sn382, sn50)
            self._zone_active = False  # re-arm the entry flag on a new zone (Pine 2544)
            self._dir = d
            created = True

        # ── Zone touch -> confirm (Pine 2791-2797) ──
        confirmed = False
        if self._zone_top is not None and self._zone_bot is not None:
            if (not self._zone_active) and high >= self._zone_bot and low <= self._zone_top:
                self._zone_active = True
                confirmed = True
        # A BOS this bar clears the confirmation (Pine 2796-2797): the fresh zone can't count its
        # own break bar as a confirm, even though the flag above may have latched.
        if is_bos:
            confirmed = False

        return SniperFibEvents(
            active=self._zone_top is not None,
            direction=self._dir,
            zone_top=self._zone_top,
            zone_bot=self._zone_bot,
            created=created,
            confirmed=confirmed,
            zone_active=self._zone_active,
        )


# ── Macro cycle fib levels (bull-only: HH sits at 0.0, LL at 1.0, retraces measured down) ──
# Retrace group — gated by 0.618, tested on the pullback (low) side, same order as Pine:
_MACRO_RETRACE: Tuple[Tuple[str, float], ...] = (
    ("E1", 0.618),   # the gate
    ("E2", 0.702),
    ("E3", 0.786),
    ("E4", 0.886),
    ("LL", 1.000),
)
# Target group — armed only after 0.618 was reached, tested on the push (high) side:
_MACRO_TARGET: Tuple[Tuple[str, float], ...] = (
    ("TP1", 0.500),
    ("TP2", 0.382),
    ("HH", 0.000),
)
_MACRO_GATE = "E1"  # 0.618
_MACRO_ORDER = _MACRO_RETRACE + _MACRO_TARGET
_MACRO_ROLE = {name: "entry" for name, _ in _MACRO_RETRACE}
_MACRO_ROLE.update({name: "target" for name, _ in _MACRO_TARGET})
_MACRO_RATIO = {name: r for name, r in _MACRO_ORDER}


class MacroFib:
    """The Macro cycle fib.

    A bull-cycle retracement that spans multiple BOS legs. Its bottom (LL, the 1.0 level) locks on
    a bullish SOS that follows a bearish SOS; its top (HH, the 0.0 level) extends on every new
    confirmed higher-high; the whole cycle resets when price closes back below the locked bottom,
    and hides (but stays locked) when price closes above the top. Level touches are gated on 0.618
    exactly like the Structure fib. Line-by-line port of mpc_assistant.pine GRP_MACRO, drawing
    removed. Pine restricts it to <=5m timeframes — that gate is the CALLER's job (feed this only
    <=5m bars), mirroring how the bot selects its data.

    NOTE on touch events: unlike the Structure fib, the Macro does NOT skip its checks on the bar a
    cycle locks/extends (its `macroExtChanged` guard is effectively always false in the source), so
    a level can be reset and re-touched on the same bar. To match Pine's plotted `X and not X[1]`
    pulse exactly, touches are edge-detected against the PREVIOUS bar's end state, not "flipped this
    update".
    """

    def __init__(self) -> None:
        # Cycle anchors + direction (Pine `var macro_*`). Locs kept for parity of the anchor bar;
        # the drawing-only `time` fields are dropped.
        self._dir: int = 0
        self._origin: Optional[float] = None       # locked bottom (LL)
        self._origin_loc: Optional[int] = None
        self._extreme: Optional[float] = None       # extending top (HH)
        self._extreme_loc: Optional[int] = None
        self._origin_locked: bool = False
        self._visible: bool = False
        self._last_conf_high: Optional[float] = None
        self._prev_extreme: Optional[float] = None

        # Bottom-tracking since the last bearish SOS (Pine macro_ll_since_bear_sos*).
        self._last_bear_sos_bar: Optional[int] = None
        self._ll_since: Optional[float] = None
        self._ll_since_bar: Optional[int] = None

        # Touched flags + the 0.618 latch. `_touched_prev` = last bar's end state, for the edge.
        self._touched = {name: False for name in _MACRO_RATIO}
        self._touched_prev = {name: False for name in _MACRO_RATIO}
        self._gate_ever = False

        self._prev_st_dir: int = 0  # Pine macro_prev_st_dir — tracked but unused, kept for fidelity

    def _reset_touched(self) -> None:
        for name in self._touched:
            self._touched[name] = False
        self._gate_ever = False

    # ------------------------------------------------------------------
    def update(self, bar_index: int, high: float, low: float, close: float,
               snap: StructureSnapshot) -> MacroFibEvents:
        """Feed one closed bar (index + high/low/close) plus this bar's structure snapshot.

        Only feed <=5m bars — the Pine timeframe gate is the caller's responsibility.
        """

        # ── 1. Track the most recent bearish SOS; start tracking the low from there (Pine 2293) ──
        if snap.bear_sos:
            self._last_bear_sos_bar = bar_index
            self._ll_since = low
            self._ll_since_bar = bar_index

        # ── 2. While unlocked, keep the lowest low since that bear SOS (Pine 2301) ──
        if not self._origin_locked and self._last_bear_sos_bar is not None:
            if self._ll_since is None or low < self._ll_since:
                self._ll_since = low
                self._ll_since_bar = bar_index

        # ── 3. RESET: price closed below the locked bottom (Pine 2307) ──
        if self._origin_locked and self._origin is not None and close < self._origin:
            self._dir = 0
            self._origin = None
            self._origin_loc = None
            self._extreme = None
            self._extreme_loc = None
            self._origin_locked = False
            self._last_conf_high = None
            self._visible = False
            self._last_bear_sos_bar = bar_index
            self._ll_since = low
            self._ll_since_bar = bar_index

        # ── 4. BOTTOM LOCKS on a bullish SOS (Pine 2331) ──
        ll_after_sos = (
            snap.last_conf_low is not None
            and self._last_bear_sos_bar is not None
            and snap.last_conf_low_loc is not None
            and snap.last_conf_low_loc > self._last_bear_sos_bar
        )
        bottom_anchor = snap.last_conf_low if ll_after_sos else self._ll_since
        bottom_anchor_bar = snap.last_conf_low_loc if ll_after_sos else self._ll_since_bar
        new_cycle = False
        if (snap.bull_sos and not self._origin_locked and bottom_anchor is not None
                and snap.last_conf_high is not None):
            self._dir = 1
            self._origin = bottom_anchor
            self._origin_loc = bottom_anchor_bar
            self._extreme = snap.last_conf_high
            self._extreme_loc = snap.last_conf_high_loc
            self._origin_locked = True
            self._last_conf_high = snap.last_conf_high
            self._visible = True
            self._prev_extreme = snap.last_conf_high
            self._reset_touched()
            new_cycle = True

        # ── 5. HIDE when price closes above the locked top (Pine 2358) ──
        if (self._origin_locked and self._visible and self._extreme is not None
                and close > self._extreme):
            self._visible = False

        # ── 6. TOP EXTENDS on every new confirmed HH (Pine 2370) ──
        extended = False
        if (self._origin_locked and snap.last_conf_high is not None
                and self._last_conf_high is not None and snap.last_conf_high > self._last_conf_high):
            self._extreme = snap.last_conf_high
            self._extreme_loc = snap.last_conf_high_loc
            self._last_conf_high = snap.last_conf_high
            self._visible = True
            self._prev_extreme = snap.last_conf_high
            self._reset_touched()
            extended = True

        # ── 7. Touched tracking — same gated logic as the Structure fib (Pine 2390) ──
        levels: Dict[str, float] = {}
        active = False
        if (self._visible and self._origin_locked and self._origin is not None
                and self._extreme is not None):
            mH = self._extreme
            mL = self._origin
            if mH - mL > 0:
                active = True
                levels = {name: fib_level(mH, mL, 1, r) for name, r in _MACRO_ORDER}
                ext_changed = self._extreme != self._prev_extreme  # source no-op; kept for fidelity
                gate_reached = low <= levels[_MACRO_GATE]

                if not ext_changed:
                    if gate_reached:
                        for name, _ in _MACRO_RETRACE:
                            if not self._touched[name] and low <= levels[name]:
                                self._touched[name] = True
                    if self._gate_ever:
                        for name, _ in _MACRO_TARGET:
                            if not self._touched[name] and high >= levels[name]:
                                self._touched[name] = True
                    if gate_reached and not self._gate_ever:
                        self._gate_ever = True

        self._prev_st_dir = snap.direction  # Pine 2432 (unused)

        # Edge-detect touches against the PREVIOUS bar's end state (Pine `X and not X[1]`).
        touched_now: List[FibTouch] = [
            FibTouch(name, _MACRO_RATIO[name], levels[name], _MACRO_ROLE[name])
            for name, _ in _MACRO_ORDER
            if self._touched[name] and not self._touched_prev[name]
        ]
        self._touched_prev = dict(self._touched)

        return MacroFibEvents(
            active=active,
            direction=self._dir,
            top=self._extreme if active else None,
            bot=self._origin if active else None,
            locked=self._origin_locked,
            visible=self._visible,
            new_cycle=new_cycle,
            extended=extended,
            touched=touched_now,
            levels=levels,
            touched_so_far={name for name, hit in self._touched.items() if hit},
        )
