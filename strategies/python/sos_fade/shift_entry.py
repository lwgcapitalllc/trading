"""The 1-MINUTE SOS-THEN-BOS ENTRY (`exec_shift_entry`) — enter a zone touch only once the
1-minute structure has turned. Aaron, 2026-09-28: *"can you prove it?"*

THE TRADE (long side; shorts mirror), exactly as `backtest/tools/generic_ltf_trigger.py` screened
it — `docs/SOS_FADE_GENERIC_SPEC.md` → "With costs, and GBPUSD on 1-minute":

  SETUP    a live 15m setup — armed by an enabled source, SOS'd, and its pullback has tagged the
           0.5. Its 15m 1.0 (stop) and 0.0 (extreme) are FROZEN at the first 15m close that
           reports the tag, which is the fib the screen used.
  SIGNAL   on the fill-clock (1-minute) structure feed: an external SOS in the trade's direction,
           then a later external BOS on a bar that is not itself an SOS.
  ENTRY    at market — the next 1-minute open — through the re-entry's order path.
  EXITS    stop at the 15m 1.0; the whole position off at the 15m 0.0, or at the R multiple the
           first target is set to (`exec_tp1_r`), off the real fill.
  RETIRE   the setup dies on the first 1-minute bar whose wick reaches the 1.0 or the 0.0, and on
           its FIRST SOS-then-BOS whether or not it could be taken — a later one is a different
           trade from the one the screen graded.

⚠ **The tag is only KNOWN at the 15m close that reports it.** An SOS printed inside that 15m bar
still counts (its time is kept), but a BOS inside it is not seen. The screen could see both; the
difference is part of what the lab run measures.
⚠ **Owns no position logic.** It emits a `SecArm` tagged `SRC`; `Execution` sizes, floors, fills
and manages it. It never moves the stop before the target (`Execution._protect_rule` maps this
source to the PRIMARY's rule, because this is the first trade on the setup, not a re-entry).
⚠ Holds only times and prices, never fast bar numbers, so it survives a fast-feed rebuild.
⚠ No Pine counterpart. The parity gate is blind to it; every number is a lab finding.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, Optional, Tuple

from .secondary import SecArm

SRC = "1m SOS then BOS"


@dataclass(frozen=True)
class ShiftCtx:
    """One live 15m setup, as `Execution.step` reports it after each 15m close."""

    dir: int         # +1 long, -1 short
    sos_ms: int      # the setup's 15m SOS time — its identity
    from_ms: int     # open time of the 15m bar that reported the tag; SOS from here on counts
    stop: float      # the 15m 1.0
    extreme: float   # the 15m 0.0


@dataclass
class _Live:
    stop: float
    extreme: float
    sos_seen: bool


class ShiftEntry:
    def __init__(self, config) -> None:
        self._cfg = config
        self._live: Dict[Tuple[int, int], _Live] = {}
        self._dead: set = set()
        self._last_sos_ms: Dict[int, Optional[int]] = {1: None, -1: None}

    def update(self, ctxs, *, now_ms: int, m1, high: float, low: float, close: float,
               flat: bool) -> SecArm:
        """Step one fill-clock bar. `ctxs` is the (long, short) pair from the last 15m close."""
        sos = {1: bool(m1.new_bull_sos), -1: bool(m1.new_bear_sos)}
        bos = {1: bool(m1.new_bull_bos), -1: bool(m1.new_bear_bos)}
        for d in (1, -1):
            if sos[d]:
                self._last_sos_ms[d] = now_ms
        keys = set()
        kw: dict = {}
        for ctx in ctxs:
            if ctx is None:
                continue
            key = (ctx.dir, ctx.sos_ms)
            if key in self._dead:
                continue
            keys.add(key)
            d = ctx.dir
            st = self._live.get(key)
            if st is None:
                last = self._last_sos_ms[d]
                # A setup first seen on THIS bar: an SOS on this bar is recorded as seen, and the
                # BOS test below needs one on an EARLIER bar, so the two never share a bar.
                seen_before = last is not None and ctx.from_ms <= last < now_ms
                st = self._live[key] = _Live(ctx.stop, ctx.extreme, seen_before)
            # The window closes on the first wick to either level — checked BEFORE the signal,
            # so a shift on the touching bar belongs to a setup that is already over.
            touched = ((low <= st.stop or high >= st.extreme) if d > 0
                       else (high >= st.stop or low <= st.extreme))
            if touched:
                self._retire(key)
                continue
            if st.sos_seen and bos[d] and not sos[d]:
                self._retire(key)      # the FIRST completion is the trade, taken or not
                dist = (close - st.stop) * d
                if flat and dist > 0:
                    kw.update(self._arm(d, close, st, dist, ctx.sos_ms))
                continue
            st.sos_seen = st.sos_seen or sos[d]
        # A setup the 15m side no longer reports is gone; drop its window with it.
        self._live = {k: v for k, v in self._live.items() if k in keys}
        return SecArm(**kw)

    def _arm(self, d: int, close: float, st: _Live, dist: float, sos_ms: int) -> dict:
        tp_r = float(getattr(self._cfg, "exec_tp1_r", -1.0))
        # The rung is re-priced off the real fill by `Execution._first_rung` when it is in R.
        tp = close + d * tp_r * dist if tp_r > 0 else st.extreme
        # The second rung is parked beyond the first so the stop ladder, which climbs rungs in
        # distance order, never stages off it; with the whole position banked at the first,
        # nothing reaches it.
        far = close + 2 * (tp - close)
        p = "l_" if d > 0 else "s_"
        return {p + "armed": True, p + "edge": close, p + "sl": st.stop, p + "tp1": tp,
                p + "tp2": far, p + "leg": sos_ms, p + "src": SRC}

    def _retire(self, key) -> None:
        self._dead.add(key)
        self._live.pop(key, None)

    @property
    def watching(self) -> int:
        """How many setups are waiting for their shift. Reporting only."""
        return len(self._live)
