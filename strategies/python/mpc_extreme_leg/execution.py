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
# Repo root on the path so `backtest.portfolio` imports standalone. ⚠ Added explicitly rather
# than leaning on `mpc_sos_fade.execution` (imported below) having already done it — that works
# today and breaks silently the day this file's import order changes or that shim moves.
_ROOT = Path(__file__).resolve().parents[3]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from backtest.portfolio.account import SoloAccount  # noqa: E402
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
# there is no input, no `cfg_*` column, and nothing a parity gate could ever check. 8 SHIPS ON and
# 9 ships off; `compare_extreme_leg.py` forces both off for its comparison — the configuration
# every export is taken at — and prints a verdict naming what it therefore could not check. That
# is the only reason these two are allowed to exist here. See `config.py` → section 8.
# ⚠ They sit LAST in the ladder on purpose. With both off the code stream is bit-identical to the
# chart's; with one on, a setup the Pine accepts records 8 or 9 here, which is the divergence made
# visible rather than hidden. **That ordering is what makes the gate's forced-off run a valid
# comparison and not a convenient one, so do not move these two up the ladder.**
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
    # Reporting-only excursion: the highest and lowest price this hold ever reached. Seeded at the
    # entry FILL and widened once per bar in `resolve` — never read by a decision, so it cannot
    # move the trade list the parity gate compares. Resolved into `mfe_price`/`mae_price` by
    # direction at close. See `_widen_hold` for why the adverse side is bounded by the stop.
    ext_high: float = 0.0
    ext_low: float = 0.0


class ExtremeLegExecution:
    """Places one order, brackets it, and books what came back.

    ⚠ **The bar that opens a trade can neither stop out nor take profit, and that mirrors the
    platform rather than being a simplification.** The Pine places its bracket on the entry bar
    (`or tookLong` — see `[doc 12a]`), which makes it live for the NEXT bar's range. A replay that
    resolved the bracket against the entry bar's own high and low would close trades the chart
    holds, and it would do it most often on exactly the fast bars this strategy enters on.
    """

    def __init__(self, config, initial_capital: float = 10_000.0, profile=None, *,
                 account=None, leg: str = "strat") -> None:
        self._cfg = config
        # `account` is the SHARED account when this bot is one leg of a stack: it owns the balance
        # every leg sizes against and the risk budget they compete for. Omit it (the default) and
        # this builds its own uncapped SoloAccount, which is byte-identical to the standalone
        # behaviour every figure in this package was measured on. `leg` is this leg's key in that
        # account and MUST be distinct per leg — the account holds one open position per key, so
        # two legs sharing a name overwrite each other's reservation and the cap silently
        # under-counts the open risk while reporting itself enforced. See `backtest/portfolio/`.
        self._account = account if account is not None else SoloAccount(balance=initial_capital)
        self._leg = leg
        self._profile = profile
        if profile is not None and getattr(profile, "bid_ask_fills", False):
            # Refusing, rather than charging the spread twice or ignoring the flag. `bid_ask_fills`
            # MOVES FILLS — it tests a long's entry against bid+spread — so honouring it changes
            # which trades exist, and half-honouring it would report a trade list nothing produced.
            #
            # 🔴 **NAME THE RUN'S COST OPTIONS, NEVER THE BROKER ACCOUNT.** This message used to
            # read "account profile 'lab:puprime_ecn' has bid_ask_fills on … use a profile with
            # bid_ask_fills off", and it sent a real reader at the broker for a whole session. The
            # broker contributes the spread's SIZE; the flag is switched on by the run's own cost
            # layers (`python_runner._profile_for`), so EVERY broker fails identically and no
            # amount of changing accounts can clear it. **A refusal that names the wrong dial is
            # worse than a bare stack trace — the reader trusts it and searches where it points.**
            raise ValueError(
                f"this run asked for 'bid/ask fills', which pays the spread by MOVING the fill "
                f"price. This strategy pays it the other way — it fills at the bar price and "
                f"deducts the spread as a flat round-trip charge — so the two are alternative "
                f"models of one cost, never layers, and honouring half of either would report a "
                f"trade list neither produces. Moving fills also changes WHICH setups trigger, so "
                f"this is not a pricing difference that could be corrected afterwards. Fix it in "
                f"the run's cost options, NOT on the broker account: untick 'bid/ask fills' and "
                f"tick 'spread'. The spread is still charged. (Changing broker would not help — "
                f"{profile.name!r} only supplies the spread's size, and every account fails the "
                f"same way while this option is on.)"
            )
        self.trades: List[Trade] = []
        self.blocks: List[Blocked] = []
        self.misses: List = []
        self.pos: Optional[_Open] = None
        # Set by the lab's replay loop and by `run()`. Unused here — carried so the object matches
        # the shape every other strategy's execution layer presents to the runner.
        self.bar_ms: int = 0

    @property
    def equity(self) -> float:
        """The balance this bot sizes against.

        🔴 **A PROPERTY, NEVER A STORED NUMBER, AND THAT IS THE WHOLE POINT OF THE SEAM.** Solo,
        it is this leg's own ledger and behaves exactly as the plain attribute it replaced. In a
        stack it is the account ALL legs share, so a loss on the other leg shrinks this one's next
        trade — which is the thing a shared-account run exists to measure. A cached copy updated at
        close would be right on a solo run and quietly stale on every stacked one, and the run
        would look completely ordinary.
        """
        return self._account.balance

    @property
    def is_flat(self) -> bool:
        """Whether this leg is holding nothing. Part of the contract a portfolio leg must meet.

        ⚠ **Read by the simulator to ORDER the legs within one tick**, so that a leg already
        holding a position is stepped BEFORE one that might open — a closing trade frees its room
        before the other leg is sized against it. Getting it inverted would not raise anything: it
        would quietly deny room that had just come free, and the run would look ordinary.
        """
        return self.pos is None

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
    def _widen_hold(self, pos: _Open, high: float, low: float, open_: float) -> None:
        """This bar's contribution to the hold's high and low, BOUNDED BY BOTH BRACKETS.

        🔴 **NEITHER EXTREME MAY SIT BEYOND A LEVEL THAT CLOSED THE TRADE.** This runs before the
        bar's exits resolve, so the raw range includes price AFTER the position is flat — and the
        chart draws the deepest and best prices as its `DD` and `Best` chips, so an unbounded
        extreme puts a marker outside the trade's own stop or target line. That exact defect was
        MEASURED on the A+ bot: 77 of 77 stopped-out trades reported a deepest price beyond their
        stop, one of them 2.22R against a 1.0R loss. It is not an intrabar-ordering guess — a
        bracket is triggered BY the move that reaches it, so anything past it happened at or after
        the fill.

        ⚠ **BOTH sides are bounded here, and that is the one place this differs from the A+ bot.**
        There the favourable side is deliberately left alone, because its first target is PARTIAL
        and the runner stays open, so price beyond it is still the trade's move. This bot's target
        closes the whole position, which makes the favourable side determinate in exactly the way
        the adverse side is. ⚠ Copying either bot's shape onto the other would be wrong.

        ⚠ **The bound is the bracket EXCEPT on a bar that opens already past it** — there the fill
        is the open, worse (or better) than the order asked for, and that fill is real. Taking the
        `min`/`max` against the open covers both cases without asking which happened.

        ⚠ On a bar that touches BOTH brackets the two bounds together are the trade's full possible
        range, which is the honest answer: bar data cannot say which came first, and the stop is
        what books by convention.

        ⚠ Neither extreme can be better or worse than the ENTRY, because both are seeded there —
        so a trade that only ever ran one way reports a zero on the other side, meaning "it never
        went that way" rather than "not measured". Reporting only; no decision reads either.
        """
        if pos.dir > 0:
            lo = max(low, min(pos.stop, open_))
            hi = min(high, max(pos.take_profit, open_)) if math.isfinite(pos.take_profit) else high
        else:
            hi = min(high, max(pos.stop, open_))
            lo = max(low, min(pos.take_profit, open_)) if math.isfinite(pos.take_profit) else low
        pos.ext_high = max(pos.ext_high, hi)
        pos.ext_low = min(pos.ext_low, lo)

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
        # Excursion widens BEFORE the exits resolve, so the closing bar's own extreme counts.
        # Reporting only — nothing below reads it, so the trade list cannot move.
        self._widen_hold(pos, high, low, open_)
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
        # Realized onto the SHARED balance as it happens, so a leg entering later in the same bar
        # sizes off the result rather than off a stale number.
        self._account.book_pnl(self._leg, pnl)
        # Resolved by DIRECTION, not by which number is larger: a short's best price is the low.
        mfe_price = pos.ext_high if pos.dir > 0 else pos.ext_low
        mae_price = pos.ext_low if pos.dir > 0 else pos.ext_high
        pv = self._cfg.point_value
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
                # ── everything below is REPORTING ONLY: the chart's entry / DD / best / exit ──
                # No decision reads any of it, so the decision stream the parity gate compares
                # cannot move. They are here because without them the price chart has nothing to
                # draw but a flat entry→exit box — `backtest.output` degrades silently when a
                # trade does not carry them, so a missing field costs a blank chart and no error.
                mfe_price=round(mfe_price, 5),
                mae_price=round(mae_price, 5),
                mfe_usd=round((mfe_price - pos.entry_price) * pos.dir * pos.qty * pv, 2),
                mae_usd=round((mae_price - pos.entry_price) * pos.dir * pos.qty * pv, 2),
                # ONE leg, because this bot closes in ONE piece — there is no ladder and no
                # runner. The chart draws the exit at a real FILL rather than at an average, and
                # for a single-fill trade the two are the same number; recording it anyway is what
                # tells the chart that the fills are KNOWN, which is a different statement from
                # having none. `qty` is the whole position for the same reason.
                legs=[{"reason": reason, "price": round(price, 5), "ms": ts_ms, "qty": pos.qty}],
                # The single target, and it banks 100% — this rung closes the position rather than
                # stepping a stop. ⚠ The percentage is not decoration: `backtest.output` uses it to
                # tell a real profit target from a level that banks nothing, and a rung reported
                # without it is drawn as an unknown rather than as a target.
                tp_rungs=((pos.take_profit, 100.0),) if math.isfinite(pos.take_profit) else (),
            )
        )
        # P&L is already booked above; this frees the RESERVATION so the other leg can use the
        # room on the very next tick. Two calls rather than one because the account separates
        # money from budget — a trade can book P&L (a partial) without giving its room back.
        self._account.close_position(self._leg)
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
            # The budget gate runs HERE, at the fill — this bot enters at market on the close, so
            # there is no resting order and nothing reserves room before this moment. The account
            # scales this leg's OWN desired size down to the room it has; solo it grants the lot.
            granted = self._account.request_fill(
                self._leg, direction, entry, stop, qty, self._cfg.point_value
            )
            if granted <= 0.0:
                # Refused: no room, or the grant fell under the stack's entry floor. Take nothing
                # and let the setup re-arm next bar if it still holds.
                #
                # ⚠ **Deliberately NOT recorded as a refusal code.** Those codes are the decision
                # stream the parity gate compares against the chart, and an account refusal is not
                # a decision this strategy made — it is one the portfolio made about it. Adding a
                # code here would put a Pine-less value in the one stream that must stay
                # comparable. The account's own contention log is where a stack reader looks, and
                # it records every refusal and every shrink with a timestamp.
                return False
            self.pos = _Open(
                dir=direction, entry_index=state.index, entry_ms=state.ts_ms,
                entry_price=entry, qty=granted, stop=stop, open_stop=stop, take_profit=tp,
                # Excursion seeds BOTH sides at the fill, and that is a fact about THIS entry
                # rather than a simplification. This bot enters at market on the bar's CLOSE, so
                # no part of the entry bar's range happens after the fill — none of it is the
                # trade's move. ⚠ The A+ bot seeds asymmetrically because its entry is a resting
                # limit filled mid-bar, where the rest of the bar IS the trade's move; do not
                # copy that shape here, and do not copy this one there.
                ext_high=entry, ext_low=entry,
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
            # The account reserves risk to the CURRENT stop, so a move to breakeven frees this
            # leg's room for the other one. Without this call the reservation stays at the
            # original stop for the life of the trade and the cap binds on risk nobody carries.
            self._account.update_stop(self._leg, pos.stop, pos.qty)

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
