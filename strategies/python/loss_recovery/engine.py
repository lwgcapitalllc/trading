"""loss_recovery/engine.py — the state machine.

    a primary trade loses
      -> arm, wanting an EXTERNAL CHoCH in the opposite direction
      -> it prints; enter at the next bar's open
      -> stop at the far end of the break leg  (that distance IS this trade's 1R)
      -> optionally cut at -soft_stop_r, or when structure breaks back, before that stop is reached
      -> price reaches +be_at_r; step the stop to +be_to_r   (optional, off by default)
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
from .position import ManagedPosition
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
        choch_dir: Dict[int, int],
        atr,
        bars_per_day: float,
    ) -> Tuple[int, float, float, str, bool, float, float]:
        """Walk bars from `entry_index`.

        Returns (exit_index, exit_price, r, reason, locked, mfe, mae).

        `mfe` and `mae` are both NON-NEGATIVE magnitudes in this trade's own R — the furthest
        it ever ran in favour, and the deepest it ever sat against. They are reporting-only
        and no decision reads either, which is what keeps them parity-safe.

        ⚠ `mae` is capped at the EXIT on the bar that closes the trade, and that is the whole
        care in it: the stop bar's low can sit far below the stop, but the position was gone
        at the stop, so reading the bar's full range would report an excursion this trade
        never experienced — and a chart would then draw its deepest point BEYOND its own stop.

        The stop is checked BEFORE the favourable excursion on every bar. On a bar that holds
        both, that books the loss — the pessimistic read, and the same one every fill model in
        this repo uses. It makes the result slightly worse than reality, which is the safe
        direction.

        ⚠ `risk` is always the STRUCTURAL distance, whatever `soft_stop_r` does to the working
        stop. That is what makes a soft stop a smaller loss rather than a bigger position: 1R is
        the number the trade was sized on, and cutting early books a fraction of it.
        """
        op = bars["open"].to_numpy(dtype=float)
        hi = bars["high"].to_numpy(dtype=float)
        lo = bars["low"].to_numpy(dtype=float)
        cl = bars["close"].to_numpy(dtype=float)

        pos = ManagedPosition(
            self.config,
            entry_index=entry_index,
            direction=direction,
            entry_price=entry_price,
            stop_price=stop_price,
            bars_per_day=bars_per_day,
            last_index=len(hi) - 1,
        )
        book = swing_low if direction > 0 else swing_high
        for j in range(entry_index, pos.end):
            done = pos.on_bar(
                j,
                op[j],
                hi[j],
                lo[j],
                cl[j],
                atr=float(atr[j]),
                swing=book.get(j),
                choch=choch_dir.get(j, 0),
            )
            if done is not None:
                return done.index, done.price, done.r, done.reason, done.locked, done.mfe, done.mae
        # `end <= entry_index` — the trade was opened on or past its own time cap. Unreachable
        # with any shipped config (the cap is days and the entry is one bar after its signal),
        # and kept because the alternative is falling off the end of the function returning None.
        j = max(entry_index, pos.end - 1)
        done = pos.expire(j, float(cl[j]))
        return done.index, done.price, done.r, done.reason, done.locked, done.mfe, done.mae

    def _stop_for(
        self,
        loss,
        bars,
        atr,
        swing_low,
        swing_high,
        want,
        signal_index,
        entry_price,
        break_leg_far_end,
    ):
        """The opening stop, per `stop_mode`. `None` means this mode cannot place one here.

        ⚠ `None` is a REFUSAL, not a fallback. A mode that quietly handed back the structural stop
        when its own level was missing would report a rule nobody ran, on a stop ~4x the size.
        """
        cfg = self.config
        mode = cfg.stop_mode
        if mode == "structural":
            return break_leg_far_end
        if mode == "loss_entry":
            return _loss_entry(loss)
        if mode == "leg_frac":
            return entry_price - want * cfg.stop_leg_frac * abs(entry_price - break_leg_far_end)
        a = float(atr[signal_index])
        if not a > 0:  # also catches the NaN of the warm-up bars
            return None
        if mode == "atr":
            return entry_price - want * cfg.stop_atr_mult * a
        pad = cfg.stop_pad_atr * a
        if mode == "swing":
            book = swing_low if want > 0 else swing_high
            # The NEAREST confirmed swing still on the protective side of the fill. Taking the
            # most recent one instead would sometimes hand a long a level above its own entry.
            cand = sorted(
                (abs(px - entry_price), px)
                for i, px in book.items()
                if i <= signal_index and (entry_price - px) * want > 0
            )
            return None if not cand else cand[0][1] - want * pad
        if mode == "signal_bar":
            lo = float(bars["low"].iloc[signal_index])
            hi = float(bars["high"].iloc[signal_index])
            return (lo - pad) if want > 0 else (hi + pad)
        raise ValueError(f"unhandled stop_mode {mode!r}")

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
        choch_dir: Dict[int, int] = {i: dirn for i, dirn, _ in chochs}
        atr = _atr(bars).to_numpy(dtype=float)
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
            signal_index, _, break_leg_far_end = sig
            entry_index = signal_index + 1
            if entry_index >= len(bars):
                continue
            entry_price = float(op[entry_index])
            stop_price = self._stop_for(
                loss,
                bars,
                atr,
                swing_low,
                swing_high,
                want,
                signal_index,
                entry_price,
                break_leg_far_end,
            )
            if stop_price is None:
                continue
            risk = abs(entry_price - stop_price)
            # A stop on the wrong side of the fill is not a tight trade, it is a broken one.
            # Refuse it rather than clamping — see the repo's rule 17.
            if risk <= 0 or (entry_price - stop_price) * want <= 0:
                continue

            exit_index, exit_price, r, reason, locked, mfe, mae = self._manage(
                bars,
                entry_index,
                want,
                entry_price,
                stop_price,
                swing_low,
                swing_high,
                choch_dir,
                atr,
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
                    max_adverse_r=mae,
                    bars_held=exit_index - entry_index,
                )
            )
        return out

    def refused(self, bars: pd.DataFrame, trades: Iterable[LossEvent]) -> List[ArmedSignal]:
        """Losses whose CHoCH DID arrive but whose stop was unusable — it sat on the wrong side of
        the fill, or on it.

        🔴 A third state, and it has to be countable separately. `run` returning 40 trades where
        another config returns 62 could mean the signal never came (`pending`) or that the stop was
        refused, and those say opposite things about the rule. Under `stop_mode="loss_entry"` this
        is the one that moves: the primary's entry is only a valid stop if price is still on the
        far side of it when the CHoCH prints.
        """
        cfg = self.config
        if not cfg.enabled:
            return []
        chochs, _, _ = self._replay_structure(bars)
        op = bars["open"].to_numpy(dtype=float)
        out: List[ArmedSignal] = []
        for loss in sorted((t for t in trades if t.r < -cfg.scratch_r), key=lambda t: t.exit_index):
            want = -loss.dir
            if not cfg.both_directions and want < 0:
                continue
            sig = next((s for s in chochs if s[0] > loss.exit_index and s[1] == want), None)
            if sig is None or sig[0] + 1 >= len(bars):
                continue
            stop = _loss_entry(loss) if cfg.stop_mode == "loss_entry" else sig[2]
            if (float(op[sig[0] + 1]) - stop) * want <= 0:
                out.append(ArmedSignal(loss.exit_index, want, sig[0]))
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


def _atr(bars: pd.DataFrame, length: int = 14):
    """Wilder's ATR over the whole frame, once.

    ⚠ NOT a canonical engine and not pretending to be one — rule 21 names thirteen engines and
    ATR is not among them; `equal_highs_lows` and `order_blocks` each carry their own private copy
    for the same reason. If ATR is ever promoted to `engines/`, this is a consumer to move.
    """
    h, lo, c = bars["high"], bars["low"], bars["close"]
    pc = c.shift(1)
    tr = pd.concat([h - lo, (h - pc).abs(), (lo - pc).abs()], axis=1).max(axis=1)
    return tr.ewm(alpha=1.0 / length, adjust=False).mean()


def _loss_entry(loss) -> float:
    """The losing trade's own entry price, or a refusal naming what is missing.

    ⚠ Deliberately not `getattr(loss, "entry_price", <structural>)`. A loss event that cannot
    answer and one whose stop happens to sit at the break leg are different facts, and the two
    stops are ~4x apart — collapsing them reports a rule nobody ran, which is this repo's most
    expensive recurring defect.
    """
    px = getattr(loss, "entry_price", None)
    if px is None:
        raise AttributeError(
            "stop_mode='loss_entry' needs a LossEventWithEntry, and this loss event carries no "
            "`entry_price`. Pass the strategy's own trade objects, or use stop_mode='structural' "
            "— it will not be substituted for you"
        )
    return float(px)


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
