"""BLegExecution — the B-LEG order layer.

The B-LEG trades through the EXACT SAME fill / TP-ladder / stop-staging / %-risk-sizing /
R-grading machinery as the A+ bot — everything from `_open_position` onward is direction-
and setup-agnostic (it only reads a resting `_Pending`'s edge/sl/tp1/tp2/qty). So this is a
thin SUBCLASS of `mpc_sos_fade.execution.Execution` that overrides only entry placement:

  * A+ entries are DISABLED — the parent's A+ `_armed` gate is still computed (so the
    "A+ has priority" stand-down holds, matching mpc_b_leg_strategy.pine), but no A+ order
    is ever placed.
  * The B-LEG rests a limit at the frozen band's near (0.5) edge, with SL beyond the leg
    origin (fib 1.0) and TP1 = the broken swing extreme (2·edge − origin), TP2 = the
    expansion extreme (`tgt`), TP3 = runner. Ports mpc_b_leg_strategy.pine 4429-4506.

`step(sig, seq, bleg)` takes the extra `BLegState` (from `bleg.BLegTracker`); it stashes it
and delegates to the parent `step`, which calls this class's `_place_entries` when flat.
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Optional

_PYPKGS = Path(__file__).resolve().parents[1]
if str(_PYPKGS) not in sys.path:
    sys.path.insert(0, str(_PYPKGS))
# repo-root on path for `engines`, the same shim the parent carries. Stated here rather than
# leaned on: importing the parent first happens to set it up, and an import reorder would turn
# that accident into an ImportError.
_ROOT = Path(__file__).resolve().parents[3]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from mpc_sos_fade.execution import Execution, TradeFib, _Pending  # noqa: E402

# The canonical ratio->price helper, and the only one allowed here for the same reason the parent
# gives: re-deriving `ext - range*ratio` inline would be a second implementation free to drift.
from engines.fibonacci.geometry import fib_level  # noqa: E402

# The ladder a recorded B-LEG fib carries, shallow -> deep. Byte-identical to the A+ bot's
# `_FIB_RATIOS`, deliberately: both bots' fibs are drawn on ONE chart, so a ratio has to mean the
# same thing on both or the reader is asked to hold two conventions at once.
_FIB_RATIOS = (0.0, 0.382, 0.5, 0.618, 0.702, 0.786, 0.886, 1.0)


def _band_fib(ext, inv, direction, leg_ms):
    """The frozen leg's fib ladder -> a `TradeFib`, or None when the leg is not fully priced.

    ⚠ THE CONVENTION IS THE WHOLE POINT OF THIS FUNCTION, because this bot's own vocabulary uses
    the other one. `bleg.py` and the Pine call the entry band "the 0.382-0.5 pocket", measuring UP
    from the leg ORIGIN (the Sniper Zone convention, `fib_from_origin`). A drawn fib measures DOWN
    from the leg EXTREME (`fib_level`), which is what the A+ bot records and what `1.0 = the leg
    origin` in `BLegState`'s own docstring already assumes.

    Same two prices, two namings. This records the `fib_level` one, so on a chart carrying both
    bots' fibs the entry reads 0.5, the stop 1.0 and TP1 0.0 on either. The one visible consequence
    is that the band's far edge (`*_bot`) draws as **0.618**, not 0.382 — it is the same line the
    code calls 0.382, named from the other end of the same leg.

    All-or-nothing, like the A+ bot: a partial ladder reads as "this trade had no 0.786" rather
    than "this record is incomplete"."""
    if ext is None or inv is None or leg_ms is None or ext == inv:
        return None
    hi, lo = (ext, inv) if direction == 1 else (inv, ext)
    return TradeFib(levels=[(r, float(fib_level(hi, lo, direction, r))) for r in _FIB_RATIOS],
                    start_ms=leg_ms)


class BLegExecution(Execution):
    """A+-entry-disabled, B-LEG-entry-only execution. Reuses the parent's whole broker
    emulator + exit ladder; only `_place_entries` differs."""

    _bleg = None   # set by step() before the parent calls _place_entries

    # No A+ diagnostic markers in this fork. The parent's BLOCKED codes and MISSED-setup
    # confluences both answer "how far did this **A+** setup get before it was refused" — and
    # here A+ never places an order, so both would report the near-misses of a trade that was
    # never on the table. The blocked markers are already excluded by construction (the recording
    # hangs off `_place_entries`, overridden below); the miss watch runs from `step()`, which this
    # fork delegates to the parent, so it needs this explicit opt-out. A B-LEG version of either
    # needs its own code set — new design work, not a port. Same call as
    # `indicators/mpc_b_leg_strategy.pine`, which drops the pink tags for the same reason.
    _records_misses = False

    def step(self, sig, seq, bleg):  # type: ignore[override]
        self._bleg = bleg
        return super().step(sig, seq)

    # ── entry placement — B-LEG only (Pine 4429-4506) ────────────────────────────
    def _place_entries(self, sig, seq, dec, long_edge, short_edge) -> None:
        cfg = self._cfg
        bleg = self._bleg

        # A+ priority gate: compute longArmed/shortArmed EXACTLY as the A+ bot would (this
        # also sets dec.long_armed/short_armed), but never place an A+ order. A live A+ arm
        # on a side stands the B-LEG down there — the parent's B leg behaviour.
        long_armed, short_armed = self._armed(sig, seq, dec, long_edge, short_edge)

        late = cfg.exec_no_late_day and 16 <= sig.ny_hour < 18   # 16:00-17:59 NY block

        # B-LEG arm (Pine 4429-4430): the frozen band is live, untapped and valid, we're flat,
        # A+ is not armed on this side, not late-day, and this band is not already traded.
        bleg_l_arm = (cfg.exec_bleg and cfg.exec_longs and not long_armed and bleg.l_on and not bleg.l_tap
                      and not late and bleg.l_top is not None and bleg.l_inv is not None
                      and bleg.l_tgt is not None and self._pos_dir == 0
                      and (self._traded_sos_l is None or bleg.l_bar != self._traded_sos_l))
        bleg_s_arm = (cfg.exec_bleg and cfg.exec_shorts and not short_armed and bleg.s_on and not bleg.s_tap
                      and not late and bleg.s_bot is not None and bleg.s_inv is not None
                      and bleg.s_tgt is not None and self._pos_dir == 0
                      and (self._traded_sos_s is None or bleg.s_bar != self._traded_sos_s))

        # Report the B-LEG's OWN arm + entry price (this is the B-LEG bot's decision stream,
        # not the never-placed A+ one). Overwrites what _armed / the parent step() set.
        dec.long_armed, dec.short_armed = bleg_l_arm, bleg_s_arm
        dec.long_edge = bleg.l_top if bleg_l_arm else None
        dec.short_edge = bleg.s_bot if bleg_s_arm else None

        # deliberate deviation (real runs only): no NEW entry inside the flat-by-close window
        if cfg.flat_by_close and self._in_flat_window(sig):
            bleg_l_arm = bleg_s_arm = False

        self._pend_long = None
        self._pend_short = None

        # ── Long B-LEG entry (Pine 4480-4490) ──
        if bleg_l_arm:
            sl = bleg.l_inv - cfg.exec_sl_buf_tk * cfg.mintick
            dist = bleg.l_top - sl
            tp1 = 2 * bleg.l_top - bleg.l_inv     # broken swing extreme (fib 0.0 of the band)
            tp2 = bleg.l_tgt                      # expansion extreme
            if dist > 0 and tp1 > bleg.l_top and tp2 >= tp1:
                qty = (self.equity * cfg.exec_risk_pct / 100.0) / dist
                fib = _band_fib(bleg.l_ext, bleg.l_inv, 1, bleg.l_leg_ms)
                self._pend_long = _Pending(1, bleg.l_top, qty, sl, tp1, tp2, bleg.l_bar, fib)

        # ── Short B-LEG entry (Pine 4494-4504) ──
        if bleg_s_arm:
            sl = bleg.s_inv + cfg.exec_sl_buf_tk * cfg.mintick
            dist = sl - bleg.s_bot
            tp1 = 2 * bleg.s_bot - bleg.s_inv
            tp2 = bleg.s_tgt
            if dist > 0 and tp1 < bleg.s_bot and tp2 <= tp1:
                qty = (self.equity * cfg.exec_risk_pct / 100.0) / dist
                fib = _band_fib(bleg.s_ext, bleg.s_inv, -1, bleg.s_leg_ms)
                self._pend_short = _Pending(-1, bleg.s_bot, qty, sl, tp1, tp2, bleg.s_bar, fib)
