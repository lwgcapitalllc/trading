"""The order layer — one position at a time, a frozen bracket, and the costs it paid.

🔴 **PINE'S `na` IS REPRODUCED AS A FLOAT NaN, NOT AS `None`, AND THAT IS THE MOST LOAD-BEARING
DECISION IN THIS PACKAGE.** Every refusal in the ladder below is a COMPARISON against a value that
may not exist yet — no swing to aim at, no average range for the first 49 bars, a stop the wrong
side of the entry. Pine evaluates `na < 2.0` as `na` and a conditional reads that as **false**, so
a missing value silently declines to refuse. Python's `None < 2.0` raises, and Python's
`nan < 2.0` is **False** — the same answer Pine gives, for the same reason, with no special-casing
anywhere in the ladder. Writing this with `None` means a dozen `is not None` guards, and the first
one anybody forgets is a parity failure that only shows up on the rare bar where the value is
missing. ⚠ This is a PARITY DEVICE and nothing else: it is not the repo's "no answer vs measured
zero" rule arriving through the back door. A NaN here means *Pine would have had `na` here*, and
the only code allowed to produce one is code mirroring a Pine expression.

⚠ **ONE POSITION AT A TIME IS NOT A PREFERENCE.** Every number this strategy has ever produced was
measured with a single slot, and the whole reason a filter pays here is that refusing a setup
genuinely buys the next one. Allowing a second position changes the population every result
describes, so it is not a setting.
"""

from __future__ import annotations

import math
import sys
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import List, Optional

_PYPKGS = Path(__file__).resolve().parents[1]
if str(_PYPKGS) not in sys.path:
    sys.path.insert(0, str(_PYPKGS))

from mpc_sos_fade.execution import Trade  # noqa: E402

NA = float("nan")

# The refusal ladder, mirroring `[doc 12d]` in the Pine one-for-one. 0 means nothing refused it.
BLK_NONE = 0
BLK_FRIDAY = 1
BLK_NO_SWING = 2
BLK_SWING_WRONG_SIDE = 3
BLK_EXTREME_WRONG_SIDE = 4
BLK_STOP_UNDER_FLOOR = 5
BLK_TARGET_TOO_NEAR = 6
# 🔴 CODE 7 HAS NO PINE COUNTERPART AND IS A DELIBERATE DIVERGENCE — read this before "fixing" it.
# The stop is `extreme - buffer * ATR(50)`, so for the first 49 bars the ATR is `na` and the stop,
# the risk and the R are all `na` too. Every refusal above then declines to fire (see the NaN note
# in the module docstring) and the Pine reaches `strategy.entry` with an `na` quantity. That is a
# bug in the Pine's warm-up, not a trade, and reproducing it faithfully would mean inventing a
# position size out of nothing. So this side REFUSES and says why. It can only ever fire inside the
# ATR warm-up, which every parity run excludes by warm-up anyway — but it fires LOUDLY into the
# blocked-setup list rather than silently, because a divergence nobody can see is the worse half.
BLK_ATR_NOT_READY = 7
# 🔴 CODES 8 AND 9 HAVE NO PINE COUNTERPART EITHER, AND FOR A DIFFERENT REASON FROM 7's.
# 7 is a warm-up bug the Pine has and this side refuses to reproduce. These two are CUTS THE PINE
# CANNOT MAKE AT ALL: `engines/regime/` and `engines/news/` have no Pine source by construction, so
# there is no input, no `cfg_*` column, and nothing a parity gate could ever check. Both are OFF by
# default and `compare_extreme_leg.py` REFUSES to run with either on — that refusal is the only
# reason they are allowed to exist here. See `config.py` → section 8.
# ⚠ They sit LAST in the ladder on purpose. With both off the code stream is bit-identical to the
# chart's; with one on, a setup the Pine accepts records 8 or 9 here, which is the divergence made
# visible rather than hidden.
BLK_TRANSITIONING = 8
BLK_NEWS = 9

BLOCK_TEXT = {
    BLK_FRIDAY: "Friday - refused by the calendar",
    BLK_NO_SWING: "no 15m swing to aim at",
    BLK_SWING_WRONG_SIDE: "the swing is already the wrong side of the entry",
    BLK_EXTREME_WRONG_SIDE: "the extreme is the wrong side of the entry",
    BLK_STOP_UNDER_FLOOR: "stop tighter than the floor",
    BLK_TARGET_TOO_NEAR: "the swing is nearer than the minimum",
    BLK_ATR_NOT_READY: "the average range is not known yet (warm-up)",
    BLK_TRANSITIONING: "the market is transitioning - refused (not a Pine rule)",
    BLK_NEWS: "a macro release is inside the blackout window - refused (not a Pine rule)",
}

# Gold rolls at 21:00 UTC (17:00 New York), and Wednesday's roll is charged three times. Both
# mirror `backtest.fills.SwapModel`; they are here only to count the nights a position spanned.
ROLLOVER_UTC_HOUR = 21


@dataclass
class Blocked:
    """A setup that armed and was then refused. Reporting only — no decision reads it back.

    ⚠ It is the more valuable half of the output when a port is being checked. Two runs that agree
    on every trade and disagree on what they REFUSED have a filter bug that has not surfaced yet,
    and it will surface on a bar neither side has been shown.
    """

    index: int
    ts_ms: int
    dir: int
    reason: str
    code: int
    entry_price: float
    stop_price: float
    target_price: float


@dataclass
class _Open:
    dir: int
    entry_index: int
    entry_ms: int
    entry_price: float
    qty: float
    stop: float           # LIVE — breakeven may move it
    open_stop: float      # FROZEN at placement: the 1R the trade was sized against
    take_profit: float
    be_armed: bool = False
    costs_usd: float = 0.0


class ExtremeLegExecution:
    """Places one order, brackets it, and books what came back.

    ⚠ **The bar that opens a trade can neither stop out nor take profit, and that mirrors the
    platform rather than being a simplification.** The Pine places its bracket on the entry bar
    (`or tookLong` — see `[doc 12a]`), which makes it live for the NEXT bar's range. A replay that
    resolved the bracket against the entry bar's own high and low would close trades the chart
    holds, and it would do it most often on exactly the fast bars this strategy enters on.
    """

    def __init__(self, config, initial_capital: float = 10_000.0, profile=None) -> None:
        self._cfg = config
        self.equity = float(initial_capital)
        self._profile = profile
        if profile is not None and getattr(profile, "bid_ask_fills", False):
            # Refusing, rather than charging the spread twice or ignoring the flag. `bid_ask_fills`
            # MOVES FILLS — it tests a long's entry against bid+spread — so honouring it changes
            # which trades exist, and half-honouring it would report a trade list nothing produced.
            raise ValueError(
                f"account profile {profile.name!r} has bid_ask_fills on, which moves fills rather "
                f"than charging a cost. This strategy prices the spread as a flat round-trip "
                f"charge and does not model ask-side fills, so running it here would report a "
                f"trade list neither model produces. Use a profile with bid_ask_fills off."
            )
        self.trades: List[Trade] = []
        self.blocks: List[Blocked] = []
        self.misses: List = []
        self.pos: Optional[_Open] = None
        # Set by the lab's replay loop and by `run()`. Unused here — carried so the object matches
        # the shape every other strategy's execution layer presents to the runner.
        self.bar_ms: int = 0

    # ── sizing ───────────────────────────────────────────────────────────────
    def _qty(self, risk: float) -> float:
        """Pine `f_qty`. `risk` is the stop distance in price.

        ⚠ Returns NaN where the Pine would compute one, so the caller refuses rather than
        inventing a size. See `BLK_ATR_NOT_READY`.
        """
        cfg = self._cfg
        if cfg.size_mode == "Fixed contracts" or risk <= 0:
            return cfg.fixed_qty
        return (self.equity * cfg.exec_risk_pct / 100.0) / risk

    # ── costs ────────────────────────────────────────────────────────────────
    def _nights(self, entry_ms: int, exit_ms: int) -> List[datetime]:
        """The rollover instants a position was held through, as dates.

        Counted rather than approximated from elapsed hours: a position opened at 20:00 and closed
        at 22:00 spans one roll while one opened at 22:00 and closed 23 hours later spans one too,
        and an hours-based estimate gets both wrong in opposite directions.
        """
        out: List[datetime] = []
        t = datetime.fromtimestamp(entry_ms / 1000.0, tz=timezone.utc)
        end = datetime.fromtimestamp(exit_ms / 1000.0, tz=timezone.utc)
        roll = t.replace(hour=ROLLOVER_UTC_HOUR, minute=0, second=0, microsecond=0)
        if roll <= t:
            roll += timedelta(days=1)
        while roll <= end:
            out.append(roll)
            roll += timedelta(days=1)
        return out

    def _charge(self, pos: _Open, exit_ms: int, market_exit: bool) -> float:
        """Everything this trade paid, as a positive number of dollars.

        ⚠ **Zero is an honest "nothing was priced", never a claim that trading is free.** A run
        with no cost profile charges nothing and says so through this field; it does not pretend
        the number was measured.
        """
        p = self._profile
        if p is None:
            return 0.0
        cost = p.commission(pos.qty) * 2.0
        if p.spread_measured and p.spread > 0:
            # One spread on the round trip, charged flat. This is the market-order reading of the
            # cost; the alternative (moving the fills) is refused in __init__ because it changes
            # which trades exist. `backtest.fills.AccountProfile` documents why the two disagree.
            cost += p.spread * pos.qty * self._cfg.point_value
        if market_exit and p.slippage_ticks:
            # Charged on a STOP only. A take-profit is a resting limit: it fills at its price or
            # better or not at all, so it cannot slip against you.
            cost += p.slippage_ticks * p.mintick * pos.qty * self._cfg.point_value
        for roll in self._nights(pos.entry_ms, exit_ms):
            cost -= p.swap_charge(pos.dir, pos.qty, roll.date())
        return cost

    # ── the bar ──────────────────────────────────────────────────────────────
    def resolve(self, index: int, ts_ms: int, high: float, low: float, open_: float) -> None:
        """Fill the bracket placed on an EARLIER bar against this bar's range.

        ⚠ **A bar that touches both ends books the STOP.** Bar data cannot say which came first, so
        the choice is between a guess that flatters the result and one that does not. This is the
        same convention the study that measured the strategy used, and the same one every fill
        model in this repo uses — it makes the backtest slightly worse than reality, which is the
        safe direction.
        """
        pos = self.pos
        if pos is None or pos.entry_index >= index:
            return
        if pos.dir > 0:
            hit_stop = low <= pos.stop
            hit_tp = high >= pos.take_profit
            # A bar that GAPS past the level fills at the open, not at the level — for the stop
            # that is worse than the order asked for and for the target it is better. Both are what
            # the platform does, and pessimism on the limit side would put the gate red on the gap
            # bars rather than making the result safer.
            stop_fill = min(pos.stop, open_)
            tp_fill = max(pos.take_profit, open_)
        else:
            hit_stop = high >= pos.stop
            hit_tp = low <= pos.take_profit
            stop_fill = max(pos.stop, open_)
            tp_fill = min(pos.take_profit, open_)
        if hit_stop:
            self._close(pos, index, ts_ms, stop_fill, "stop", market_exit=True)
        elif hit_tp:
            self._close(pos, index, ts_ms, tp_fill, "target", market_exit=False)

    def _close(self, pos: _Open, index: int, ts_ms: int, price: float,
               reason: str, *, market_exit: bool) -> None:
        costs = self._charge(pos, ts_ms, market_exit)
        gross = (price - pos.entry_price) * pos.dir * pos.qty * self._cfg.point_value
        pnl = gross - costs
        risk_usd = abs(pos.entry_price - pos.open_stop) * pos.qty * self._cfg.point_value
        self.equity += pnl
        self.trades.append(
            Trade(
                dir=pos.dir,
                entry_index=pos.entry_index,
                entry_price=pos.entry_price,
                exit_index=index,
                qty=pos.qty,
                risk_usd=risk_usd,
                pnl_usd=pnl,
                # R against the risk the trade was SIZED to, so a breakeven exit reads ~0 and a
                # target reads the fraction of the swing that was booked. Guarded because a
                # zero-risk trade cannot exist but a divide by one can still reach here.
                r=(pnl / risk_usd) if risk_usd > 0 else 0.0,
                entry_ms=pos.entry_ms,
                exit_ms=ts_ms,
                costs_usd=-costs,
                exit_price=price,
                stop_distance=abs(pos.entry_price - pos.open_stop),
                exit_reason=reason,
                kind="primary",
            )
        )
        self.pos = None

    def enter(self, state) -> bool:
        """Take the setup on `state` if one fired and the slot is free. Returns whether it did."""
        if self.pos is not None:
            return False
        for go, direction, entry, stop, tp, blk in (
            (state.go_long, 1, state.close, state.stop_long, state.tp_long, state.blk_long),
            (state.go_short, -1, state.close, state.stop_short, state.tp_short, state.blk_short),
        ):
            if not go:
                continue
            risk = abs(entry - stop)
            qty = self._qty(risk)
            if not math.isfinite(qty) or qty <= 0 or not math.isfinite(stop):
                # See BLK_ATR_NOT_READY. Recorded rather than skipped: a bar where this side
                # diverges from the Pine must be visible in the output, not inferred from a gap.
                state.set_block(direction, BLK_ATR_NOT_READY)
                self.blocks.append(
                    Blocked(state.index, state.ts_ms, direction,
                            BLOCK_TEXT[BLK_ATR_NOT_READY], BLK_ATR_NOT_READY,
                            entry, stop, tp)
                )
                return False
            self.pos = _Open(
                dir=direction, entry_index=state.index, entry_ms=state.ts_ms,
                entry_price=entry, qty=qty, stop=stop, open_stop=stop, take_profit=tp,
            )
            return True
        return False

    def arm_breakeven(self, index: int, high: float, low: float) -> None:
        """Pine's breakeven block. Runs only on a bar where a position was ALREADY open.

        ⚠ The Pine gates this on `strategy.position_size != 0`, which is still 0 on the bar the
        order is placed — so the stop cannot move to breakeven on the entry bar. That is not a
        rounding detail: at the shipped exit the target is half the way to the swing, so a fast bar
        would otherwise arm and scratch the trade on the bar it opened.
        """
        cfg = self._cfg
        pos = self.pos
        if pos is None or pos.entry_index >= index or not cfg.use_breakeven or pos.be_armed:
            return
        if not math.isfinite(pos.take_profit) or not math.isfinite(pos.stop):
            return
        span = abs(pos.take_profit - pos.entry_price)
        if span <= 0:
            return
        reached = (high >= pos.entry_price + cfg.be_arm_frac * span) if pos.dir > 0 \
            else (low <= pos.entry_price - cfg.be_arm_frac * span)
        if reached:
            pos.be_armed = True
            pos.stop = pos.entry_price

    def record_blocks(self, state) -> None:
        """Book every refusal the ladder made on this bar."""
        for direction, code in ((1, state.blk_long), (-1, state.blk_short)):
            if code == BLK_NONE:
                continue
            entry = state.close
            stop = state.stop_long if direction > 0 else state.stop_short
            tgt = state.tgt_long if direction > 0 else state.tgt_short
            self.blocks.append(
                Blocked(state.index, state.ts_ms, direction, BLOCK_TEXT[code], code,
                        entry, stop, tgt)
            )
