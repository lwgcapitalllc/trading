"""One open recovery trade, advanced ONE BAR AT A TIME.

This is the whole of the trade-management rule — the soft stop, the breakeven step, the partial,
the +1R lock, the three trails, the CHoCH invalidation and the time stop. It lives here, in a
per-bar shape, for one reason: **there are two drivers and there must not be two rules.**

  * `engine._manage` walks a finished bar frame in a loop. That is the batch path every measured
    number in this package came from.
  * `leg.RecoveryLeg` is stepped by the shared-account simulator, one bar at a time, alongside
    the strategy whose losses it recovers.

A second implementation for the second driver is exactly what this repo forbids, and the failure
mode is not a crash — it is two rules that agree for a year and then quietly disagree on the one
branch nobody replayed. So the loop was turned inside out rather than copied:
`_manage` now feeds bars to this object and returns what it hands back, which means all 32 tests
already pinning `_manage` pin this too. ⚠ **The batch results were checked BYTE-IDENTICAL across
the extraction on real bars, not just assumed from a green suite** — the suite covers the
branches somebody thought of.

⚠ **The caller supplies the per-bar inputs the rule needs but cannot fetch for itself**: ATR at
this bar, the confirmed swing level printed on this bar (if any), and whether an external CHoCH
printed on it. Passing `None` for ATR is legitimate and means *not available*, and every branch
that would have used it is then SKIPPED rather than fed a substitute — see `on_bar`.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

__all__ = ["ManagedExit", "ManagedPosition"]


@dataclass(frozen=True)
class ManagedExit:
    """How one recovery trade ended. Mirrors `_manage`'s old return tuple, in order."""

    index: int
    price: float
    r: float
    reason: str  # stop | soft | be | locked | trail | choch | time | horizon
    locked: bool
    mfe: float  # non-negative magnitude, this trade's own R
    mae: float  # non-negative magnitude, capped at the exit — see the engine's note


class ManagedPosition:
    """The state of one open recovery trade between bars.

    ⚠ `risk` is always the STRUCTURAL distance, whatever `soft_stop_r` does to the working stop.
    That is what makes a soft stop a smaller LOSS rather than a bigger POSITION: 1R is the number
    the trade was sized on, and cutting early books a fraction of it.
    """

    def __init__(
        self,
        cfg,
        *,
        entry_index: int,
        direction: int,
        entry_price: float,
        stop_price: float,
        bars_per_day: float,
        last_index: int,
    ) -> None:
        self.cfg = cfg
        self.entry_index = int(entry_index)
        self.d = int(direction)
        self.entry_price = float(entry_price)
        self.risk = abs(float(entry_price) - float(stop_price))
        # The WORKING stop. A soft stop starts nearer than the structural one; `risk` above does
        # not move with it.
        self.stop = (
            self.entry_price - self.d * cfg.soft_stop_r * self.risk
            if cfg.soft_stop_r is not None
            else float(stop_price)
        )
        self.stage = "init"
        self.trailed = False
        self.locked = False
        self.mfe = 0.0
        self.mae = 0.0
        self._cut_at_open = False
        self.banked = 0.0  # R already taken off the table by a partial
        self.live = 1.0  # fraction of the position still open
        self._best = self.entry_price  # best price seen, for the chandelier
        self.time_cap = self.entry_index + int(round(cfg.max_days * bars_per_day))
        horizon = self.entry_index + int(round(cfg.horizon_days * bars_per_day))
        # The last bar this trade may be held on, inclusive. `last_index` is the final bar the
        # driver can offer — the frame's end in batch, and the frame's end in a stack too, since
        # both replay a fixed history.
        self.end = min(int(last_index) + 1, self.time_cap, horizon)

    # ── the rule, one bar ────────────────────────────────────────────────────────────────
    def _reason(self) -> str:
        if self.stage == "lock":
            return "trail" if self.trailed else "locked"
        if self.stage == "be":
            return "be"
        return "soft" if self.cfg.soft_stop_r is not None else "stop"

    def _r_at(self, price: float) -> float:
        return self.banked + self.live * ((price - self.entry_price) * self.d) / self.risk

    def on_bar(
        self,
        j: int,
        o: float,
        h: float,
        low: float,
        c: float,
        *,
        atr: Optional[float] = None,
        swing: Optional[float] = None,
        choch: int = 0,
    ) -> Optional[ManagedExit]:
        """Advance one bar. Returns the exit when this bar closes the trade, else None.

        ⚠ **The stop is checked BEFORE the favourable excursion.** On a bar holding both, that
        books the loss — the pessimistic read, and the same one every fill model in this repo
        uses. It makes the result slightly worse than reality, which is the safe direction.

        ⚠ `atr=None` means the ATR is NOT AVAILABLE, never zero: the chandelier is skipped rather
        than fed a substitute, because a trail computed off a stand-in stop is a stop nobody set.
        """
        cfg, d = self.cfg, self.d
        if j >= self.end:  # past the time stop / horizon — the driver should have finished it
            return self.expire(j, c)

        # The open comes first in the bar, so an invalidation raised on the PREVIOUS close is
        # settled before this bar's range is read.
        if self._cut_at_open:
            self.mae = max(self.mae, (self.entry_price - o) * d / self.risk)
            return self._exit(j, float(o), self._r_at(o), "choch")

        hit_stop = (low <= self.stop) if d > 0 else (h >= self.stop)
        if hit_stop:
            r = self._r_at(self.stop)
            self.mae = max(self.mae, (self.entry_price - self.stop) * d / self.risk)
            return self._exit(j, self.stop, r, self._reason())

        fav = ((h - self.entry_price) if d > 0 else (self.entry_price - low)) / self.risk
        self.mfe = max(self.mfe, fav)
        # The bar did not reach the stop, so its whole adverse range was survived.
        self.mae = max(
            self.mae, ((self.entry_price - low) if d > 0 else (h - self.entry_price)) / self.risk
        )

        if self.stage == "init" and cfg.be_at_r > 0 and fav >= cfg.be_at_r:
            be = self.entry_price + d * cfg.be_to_r * self.risk
            if (be - self.stop) * d > 0:
                self.stop = be
            self.stage = "be"

        # Bank part of it with a FILL rather than by parking the stop on the market. This is the
        # lever that lets the runner keep a stop somewhere price has not already been.
        if self.live == 1.0 and cfg.partial_at_r > 0 and fav >= cfg.partial_at_r:
            self.banked = cfg.partial_frac * cfg.partial_at_r
            self.live = 1.0 - cfg.partial_frac

        if not self.locked and fav >= cfg.lock_at_r:
            lock = self.entry_price + d * cfg.lock_to_r * self.risk
            if (lock - self.stop) * d > 0:
                self.stop = lock
            self.stage = "lock"
            self.locked = True

        self._best = max(self._best, h) if d > 0 else min(self._best, low)

        if self.locked and cfg.trail_atr_mult > 0 and atr is not None:
            # Chandelier: a fixed distance behind the BEST price, scaled by volatility rather
            # than by price level — the objection that made the percent ratchet inert.
            chand = self._best - d * cfg.trail_atr_mult * float(atr)
            if (chand - self.stop) * d > 0 and (chand - c) * d < 0:
                self.stop = chand
                self.trailed = True

        if self.locked and cfg.trail_pct > 0:
            # A percent of PRICE, which is a different unit from R — see the config's warning.
            pct = c * (1.0 - d * cfg.trail_pct / 100.0)
            if (pct - self.stop) * d > 0:
                self.stop = pct
                self.trailed = True

        if self.locked and cfg.trail_swings and swing is not None:
            # Only ratchet FORWARD, and never to a level the bar has already traded through — a
            # swing on the wrong side of the close would stop the trade out on the next tick at a
            # price it never actually offered.
            if (swing - self.stop) * d > 0 and (swing - c) * d < 0:
                self.stop = swing
                self.trailed = True

        if cfg.invalidate_on_choch and choch == -d:
            self._cut_at_open = True

        # Last bar this trade may be held on: close it at the close, exactly as the batch loop's
        # tail did after falling out of `range(entry_index, end)`.
        if j + 1 >= self.end:
            return self.expire(j, c)
        return None

    def expire(self, j: int, close: float) -> ManagedExit:
        """Close at `close` because the trade ran out of bars it was allowed to hold."""
        reason = "time" if self.end == self.time_cap else "horizon"
        return self._exit(j, float(close), self._r_at(close), reason)

    def _exit(self, j: int, price: float, r: float, reason: str) -> ManagedExit:
        return ManagedExit(
            index=j,
            price=float(price),
            r=float(r),
            reason=reason,
            locked=self.locked,
            mfe=self.mfe,
            mae=self.mae,
        )
