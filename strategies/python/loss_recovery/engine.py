"""loss_recovery/engine.py — the state machine.

    a primary trade loses
      -> arm, wanting an EXTERNAL CHoCH in the opposite direction
      -> it prints; enter at the next bar's open
      -> stop at the far end of the break leg  (that distance IS this trade's 1R)
      -> price reaches +lock_at_r; move the stop to +lock_to_r  (the loss is now banked)
      -> trail the stop to each new confirmed swing level
      -> exit on the stop, or on the time cap

Two things this file will NOT do, both deliberate:

⚠ It does not build a structure detector. `engines/market_structure` is the canonical one and
  this consumes its public events only (rule 21). The CHoCH it waits for is `external.bull_sos` /
  `external.bear_sos`, and the break leg is `bull_bos_low` / `bear_bos_high` — the same fields
  mpc_sos_fade's own entry reads.

⚠ It does not size positions or touch money. It returns R, and `RecoveryTrade.scaled_r` is the
  only figure a journal may add up. Lots, balances and broker minimums belong to the runner.
"""

from __future__ import annotations

from typing import Dict, Iterable, List, Optional, Tuple

import pandas as pd

from .config import RecoveryConfig
from .types import ArmedSignal, LossEvent, RecoveryTrade

try:  # the engines/ shim layout differs between the repo root and a bot's deployed snapshot
    from market_structure import Bar, StructureEngine
except ImportError:  # pragma: no cover - exercised only by the deployed-path layout
    from engines.market_structure import Bar, StructureEngine  # type: ignore


class LossRecoveryEngine:
    """Turns a primary strategy's losses into recovery trades over the same bars.

    Stateless between `run` calls: everything lives in locals, so one instance can be reused and
    two runs on the same bars return equal results. That is asserted by a test rather than
    assumed, because a cached structure engine leaking between runs is exactly the kind of defect
    that only shows up on the second caller.
    """

    def __init__(self, config: Optional[RecoveryConfig] = None) -> None:
        self.config = config or RecoveryConfig()

    # ── structure ────────────────────────────────────────────────────────────────────────
    def _replay_structure(
        self, bars: pd.DataFrame
    ) -> Tuple[List[Tuple[int, int, float]], Dict[int, float], Dict[int, float]]:
        """One pass of the canonical engine. Returns:

            chochs    [(bar_index, direction, break_leg_far_end), ...] in bar order
            swing_low  {bar_index: price} confirmed swing lows, for trailing a long
            swing_high {bar_index: price} confirmed swing highs, for trailing a short

        ⚠ The break leg's FAR end is the stop, not the level that broke. For a bull CHoCH that is
        `bull_bos_low` (where the impulse launched from), never `bull_bos_price` (the swing it
        closed through). Using the broken level would put the stop inside the move that just
        happened, which is a different and much tighter trade.
        """
        eng = StructureEngine(major_length=self.config.major_length)
        o, h, l, c = (bars[k].to_numpy(dtype=float) for k in ("open", "high", "low", "close"))
        chochs: List[Tuple[int, int, float]] = []
        swing_low: Dict[int, float] = {}
        swing_high: Dict[int, float] = {}
        for i in range(len(bars)):
            ev = eng.update(
                Bar(index=i, open=float(o[i]), high=float(h[i]), low=float(l[i]), close=float(c[i]))
            ).external
            if ev.bull_sos and ev.bull_bos_low is not None:
                chochs.append((i, 1, float(ev.bull_bos_low)))
            if ev.bear_sos and ev.bear_bos_high is not None:
                chochs.append((i, -1, float(ev.bear_bos_high)))
            if ev.new_swing_low and ev.new_swing_low_price is not None:
                swing_low[i] = float(ev.new_swing_low_price)
            if ev.new_swing_high and ev.new_swing_high_price is not None:
                swing_high[i] = float(ev.new_swing_high_price)
        return chochs, swing_low, swing_high

    # ── one trade ────────────────────────────────────────────────────────────────────────
    def _manage(
        self,
        bars: pd.DataFrame,
        entry_index: int,
        direction: int,
        entry_price: float,
        stop_price: float,
        swing_low: Dict[int, float],
        swing_high: Dict[int, float],
        bars_per_day: float,
    ) -> Tuple[int, float, float, str, bool, float]:
        """Walk bars from `entry_index`. Returns (exit_index, exit_price, r, reason, locked, mfe).

        The stop is checked BEFORE the favourable excursion on every bar. On a bar that holds
        both, that books the loss — the pessimistic read, and the same one every fill model in
        this repo uses. It makes the result slightly worse than reality, which is the safe
        direction.
        """
        cfg = self.config
        d = direction
        risk = abs(entry_price - stop_price)
        hi = bars["high"].to_numpy(dtype=float)
        lo = bars["low"].to_numpy(dtype=float)
        cl = bars["close"].to_numpy(dtype=float)

        stop = stop_price
        locked = False
        mfe = 0.0
        time_cap = entry_index + int(round(cfg.max_days * bars_per_day))
        horizon = entry_index + int(round(cfg.horizon_days * bars_per_day))
        end = min(len(hi), time_cap, horizon)

        for j in range(entry_index, end):
            hit_stop = (lo[j] <= stop) if d > 0 else (hi[j] >= stop)
            if hit_stop:
                r = ((stop - entry_price) * d) / risk
                reason = "locked" if locked and r > 0 else ("trail" if locked else "stop")
                return j, stop, r, reason, locked, mfe

            fav = ((hi[j] - entry_price) if d > 0 else (entry_price - lo[j])) / risk
            mfe = max(mfe, fav)

            if not locked and fav >= cfg.lock_at_r:
                stop = entry_price + d * cfg.lock_to_r * risk
                locked = True

            if locked and cfg.trail_swings:
                level = swing_low.get(j) if d > 0 else swing_high.get(j)
                # Only ratchet FORWARD, and never to a level the bar has already traded through —
                # a swing on the wrong side of the close would stop the trade out on the next tick
                # at a price it never actually offered.
                if level is not None and (level - stop) * d > 0 and (level - cl[j]) * d < 0:
                    stop = level

        j = max(entry_index, end - 1)
        r = ((cl[j] - entry_price) * d) / risk
        reason = "time" if end == time_cap else "horizon"
        return j, float(cl[j]), r, reason, locked, mfe

    # ── driver ───────────────────────────────────────────────────────────────────────────
    def run(self, bars: pd.DataFrame, trades: Iterable[LossEvent]) -> List[RecoveryTrade]:
        """Every recovery trade the config would have taken, in entry order.

        `trades` may be the primary's FULL trade list — the loss filter lives here, so a caller
        cannot accidentally hand over a list somebody else already filtered on a different
        scratch band and get a silently different population.
        """
        cfg = self.config
        if not cfg.enabled:
            return []

        losses = sorted((t for t in trades if t.r < -cfg.scratch_r), key=lambda t: t.exit_index)
        if not losses:
            return []

        chochs, swing_low, swing_high = self._replay_structure(bars)
        op = bars["open"].to_numpy(dtype=float)
        bars_per_day = _bars_per_day(bars)
        out: List[RecoveryTrade] = []

        for loss in losses:
            want = -loss.dir
            if not cfg.both_directions and want < 0:
                continue
            sig = next(
                (s for s in chochs if s[0] > loss.exit_index and s[1] == want),
                None,
            )
            if sig is None:
                continue
            signal_index, _, stop_price = sig
            entry_index = signal_index + 1
            if entry_index >= len(bars):
                continue
            entry_price = float(op[entry_index])
            risk = abs(entry_price - stop_price)
            # A stop on the wrong side of the fill is not a tight trade, it is a broken one.
            # Refuse it rather than clamping — see the repo's rule 17.
            if risk <= 0 or (entry_price - stop_price) * want <= 0:
                continue

            exit_index, exit_price, r, reason, locked, mfe = self._manage(
                bars,
                entry_index,
                want,
                entry_price,
                stop_price,
                swing_low,
                swing_high,
                bars_per_day,
            )
            out.append(
                RecoveryTrade(
                    trigger_index=loss.exit_index,
                    signal_index=signal_index,
                    entry_index=entry_index,
                    entry_price=entry_price,
                    stop_price=stop_price,
                    direction=want,
                    risk=risk,
                    exit_index=exit_index,
                    exit_price=exit_price,
                    r=r,
                    scaled_r=r * cfg.risk_fraction,
                    exit_reason=reason,
                    locked=locked,
                    max_favourable_r=mfe,
                    bars_held=exit_index - entry_index,
                )
            )
        return out

    def pending(self, bars: pd.DataFrame, trades: Iterable[LossEvent]) -> List[ArmedSignal]:
        """Losses that armed but never got their CHoCH. For a live runner's status line, and for
        answering "why did nothing fire" without re-reading the whole run."""
        cfg = self.config
        if not cfg.enabled:
            return []
        chochs, _, _ = self._replay_structure(bars)
        pend: List[ArmedSignal] = []
        for loss in (t for t in trades if t.r < -cfg.scratch_r):
            want = -loss.dir
            if not cfg.both_directions and want < 0:
                continue
            if not any(s[0] > loss.exit_index and s[1] == want for s in chochs):
                pend.append(ArmedSignal(loss.exit_index, want, None))
        return pend


def _bars_per_day(bars: pd.DataFrame) -> float:
    """Bars per calendar day, MEASURED off the index rather than assumed from a timeframe name.

    ⚠ Not `86400 / median_gap`: a gold week has a daily break and a weekend, so the median gap
    says 96 bars/day for M15 while the calendar span says fewer. `max_days` is a CALENDAR cap
    (swap is charged on calendar nights), so the conversion has to come from the span.
    """
    if not isinstance(bars.index, pd.DatetimeIndex) or len(bars) < 2:
        return 96.0
    span_days = (bars.index[-1] - bars.index[0]).total_seconds() / 86400.0
    if span_days <= 0:
        return 96.0
    return len(bars) / span_days
