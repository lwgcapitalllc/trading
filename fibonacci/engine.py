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

Next (not yet ported): SniperFib (BOS impulse-leg 0.382-0.5 zone) and MacroFib (HH->LL cycle).
"""

from __future__ import annotations

from typing import List, Optional, Tuple

from .geometry import fib_level, origin_index
from .types import FibTouch, StructureFibEvents, StructureSnapshot

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
