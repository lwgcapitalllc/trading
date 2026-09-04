"""The recovery rule as a LEG of a shared account — one balance, one risk budget.

**Why this exists, stated first because the number it replaces was wrong in a way nobody could
see.** The batch adapter (`sos_fade/recovery.py`) appends recovery trades to a finished book.
It sizes them off the running balance, but the primary never sizes off THEM, so recovery profit
sits beside the curve instead of lifting it. Measured on run `236e206d0142`: the identical trades
are worth **+3.8%** that way and **+44.8%** on one compounding balance. A real account is one
balance. **The lab was answering a question nobody asked.**

Put a risk BUDGET on that balance and it moves again — 23 of that run's 160 primary entries opened
while a recovery was still holding risk, and a primary trade is worth 9.3x a recovery trade. So
neither the batch number nor a naive re-price settles it, and only a replay through
`backtest/portfolio/` — one balance, one budget, arrival-order grants, a contention log — can.
This is the adapter that lets the recovery BE one of those legs.

🔴 **It is not a second copy of the rule.** Everything about managing an open trade lives in
`position.ManagedPosition`, which `engine._manage` also drives; the extraction was proved
byte-identical over ten configs on real bars. What is genuinely new here is only the ARMING side —
the batch engine pre-computes every structure event and then matches, and a stepped leg has to
answer the same questions one bar at a time.

⚠ **Three deliberate differences from the batch rule, each REFUSED or COUNTED rather than
silently absorbed:**

1. **One position at a time.** The shared account keys one open position per leg name, and the
   batch rule has no such limit — it resolves each loss independently, so two recoveries can
   overlap. MEASURED on run `236e206d0142`: 3 overlapping pairs out of 53 trades, never more than
   2 open at once. The second is skipped and COUNTED in `skipped_concurrent`, so the difference is
   visible in the result rather than inferred from a trade count.
2. **No ATR.** The engine stack does not carry one, and this module will not compute a private
   copy — that is a second implementation of an indicator, and the repo has one canonical answer
   for everything else. A config whose stop or trail needs ATR is REFUSED at construction, naming
   the batch tool. The shipped defaults need none.
3. **No look-ahead by construction.** The batch driver can see the whole frame; this one cannot.
   That is the point of running it — anything only the batch can do is something a live account
   could not have done either.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from .config import RecoveryConfig
from .costs import hold_cost_r
from .position import ManagedPosition
from .types import LossEvent

__all__ = ["LegTrade", "RecoveryLegConfig", "RecoveryLeg"]

# Stop modes and trails that need an ATR this driver has no canonical source for.
_ATR_STOPS = ("atr", "swing", "signal_bar")


@dataclass
class LegTrade:
    """One booked recovery trade, in the shape `backtest/output.py` reads.

    Deliberately its OWN type rather than a strategy's `Trade`: this package is defined against a
    protocol so any bot can drive it, and importing one bot's concrete class to emit a row would
    undo that. Every field here is one `build_equity_curve` reads by name.
    """

    dir: int
    entry_index: int
    entry_price: float
    exit_index: int
    qty: float
    risk_usd: float
    pnl_usd: float
    r: float
    entry_ms: int = 0
    exit_ms: int = 0
    costs_usd: float = 0.0
    exit_price: float = 0.0
    stop_distance: float = 0.0
    exit_reason: str = ""
    kind: str = "recovery"
    mfe_price: float = 0.0
    mae_price: float = 0.0
    mfe_usd: float = 0.0
    mae_usd: float = 0.0
    legs: List[dict] = field(default_factory=list)
    adds: List[dict] = field(default_factory=list)


@dataclass
class RecoveryLegConfig:
    """What the leg needs on top of the RULE: the instrument's contract size and the account's
    full-size risk, neither of which is a property of the rule itself.

    `unit_risk_pct` is the percentage a NORMAL trade risks (10.0, not 0.10) — the recovery takes
    `rule.risk_fraction` of it. It is stated here rather than read off the primary's config
    because a leg must be runnable beside any strategy, including one that sizes some other way.
    """

    rule: RecoveryConfig
    point_value: float
    unit_risk_pct: float
    major_length: int = 15
    bars_per_day: float = 96.0  # M15. The driver overwrites this from the frame it is given.
    # `exec_secondary` is read by `portfolio/legs._refuse_unreplayable`, which refuses any config
    # needing a second bar stream. This leg needs one stream; saying so explicitly is cheaper than
    # relying on a getattr default in another package.
    exec_secondary: bool = False


class _LegExecution:
    """The order layer, reduced to what one always-market position needs.

    It exists to satisfy the leg contract (`trades`, `is_flat`) and to be the ONE place that talks
    to the shared account, so every call the account expects — grant at fill, re-reserve on a stop
    move, book the P&L, release the position — happens in the same order the strategy layer does
    it. A leg that books P&L without releasing its reservation under-reports the room forever.
    """

    def __init__(self, account, leg: str) -> None:
        self._account = account
        self._leg = leg
        self.trades: List[LegTrade] = []
        self.bar_ms: int = 0
        self.open: Optional[ManagedPosition] = None
        self._qty = 0.0
        self._risk_usd = 0.0
        self._entry_ms = 0
        # Setups the account refused outright, and ones this leg skipped because it was already
        # holding. Reporting-only and SEPARATE, because "the budget was full" and "the rule only
        # takes one at a time" are different facts about a run.
        self.blocked: List[dict] = []
        self.skipped_concurrent: List[dict] = []

    @property
    def is_flat(self) -> bool:
        return self.open is None

    @property
    def equity(self) -> float:
        return self._account.balance


class RecoveryLeg:
    """The loss-recovery rule, stepped one bar at a time against a shared account.

    Constructed the way `backtest/replay.build_strategy` constructs any leg, so
    `portfolio.legs.build_leg` can build it with no special case.
    """

    def __init__(
        self,
        config: RecoveryLegConfig,
        *,
        initial_capital: float = 0.0,
        cost_profile: Any = None,
        account: Any = None,
        leg: str = "recovery",
    ) -> None:
        rule = config.rule
        if rule.stop_mode in _ATR_STOPS or rule.trail_atr_mult > 0:
            raise ValueError(
                f"stop_mode={rule.stop_mode!r} / trail_atr_mult={rule.trail_atr_mult} needs an "
                f"ATR, and a shared-account leg has no canonical source for one — the engine "
                f"stack does not carry it and computing a private copy here would be a second "
                f"implementation of an indicator this repo keeps exactly one of. Use "
                f"backtest/tools/recovery_report.py for those modes, or run the leg on a "
                f"structural stop."
            )
        self.config = config
        self._rule = rule
        self._cost_profile = cost_profile
        from backtest.portfolio.account import SoloAccount  # local: keeps the package importable

        self._account = account if account is not None else SoloAccount(balance=initial_capital)
        self._leg = leg
        self.execution = _LegExecution(self._account, leg)

        # Losses whose opposing CHoCH has not arrived yet: direction wanted -> how many are
        # waiting. A COUNT rather than a flag — two losses in the same direction are two armed
        # signals, and collapsing them would silently drop the second recovery.
        self._armed: Dict[int, int] = {1: 0, -1: 0}
        # The source leg's trade list, and how far down it we have already read. A leg cannot be
        # handed its losses up front — that is the look-ahead this whole exercise removes.
        self._source: Optional[List[LossEvent]] = None
        self._read = 0
        # Set on the bar a signal fires; the entry is the NEXT bar's open.
        self._pending: Optional[dict] = None
        self._last_index = 0

    # ── wiring ───────────────────────────────────────────────────────────────────────────
    def watch(self, source_trades: List[LossEvent]) -> None:
        """Read losses from this list as it GROWS — it is the other leg's live trade list.

        ⚠ It must be the list object the source leg appends to, not a copy: a copy taken before
        the run is empty forever, and a leg that arms on nothing produces an empty book that
        reads exactly like a rule that found no setups.
        """
        self._source = source_trades

    def set_horizon(self, last_index: int, bars_per_day: float) -> None:
        """The frame's final bar and its bar-per-day rate, for the time stop."""
        self._last_index = int(last_index)
        self.config.bars_per_day = float(bars_per_day)

    # ── the leg contract ─────────────────────────────────────────────────────────────────
    def stack_config(self):
        from backtest.replay import EngineConfig

        return EngineConfig(major_length=self.config.major_length)

    engine_config = stack_config

    def step(self, state) -> None:
        """One bar: manage what is open, then arm on new losses, then act on a signal."""
        bar = state.bar
        ext = state.structure.external
        i = int(bar.index)

        if self.execution.open is not None:
            self._manage_open(i, bar, ext)
        self._arm(i)
        # A position closed on this bar frees the slot, but the entry is always the NEXT bar's
        # open, so nothing can enter on the bar it exited on. Order still matters: the pending
        # fill from the PREVIOUS bar is taken before this bar can create a new one.
        self._fill_pending(i, bar)
        self._look_for_signal(i, ext)

    # ── management ───────────────────────────────────────────────────────────────────────
    def _manage_open(self, i: int, bar, ext) -> None:
        pos = self.execution.open
        d = pos.d
        swing = None
        if d > 0 and ext.new_swing_low and ext.new_swing_low_price is not None:
            swing = float(ext.new_swing_low_price)
        elif d < 0 and ext.new_swing_high and ext.new_swing_high_price is not None:
            swing = float(ext.new_swing_high_price)
        choch = 1 if ext.bull_sos else (-1 if ext.bear_sos else 0)

        before = pos.stop
        done = pos.on_bar(
            i, bar.open, bar.high, bar.low, bar.close, atr=None, swing=swing, choch=choch
        )
        if done is None:
            # A stop that moved releases budget — a trade at breakeven reserves nothing. Told to
            # the account every time it moves, not only at the end, or the room it freed stays
            # invisible to the other leg for the whole hold.
            if pos.stop != before:
                self._account.update_stop(self._leg, pos.stop, self.execution._qty)
            return
        self._book(done, bar)

    def _book(self, done, bar) -> None:
        ex = self.execution
        pos = ex.open
        risk_usd = ex._risk_usd
        exit_ms = int(bar.timestamp_ms)
        cost_r = hold_cost_r(self._cost_profile, ex._entry_ms, exit_ms, pos.d, pos.risk)
        costs_usd = cost_r * risk_usd
        pnl_usd = done.r * risk_usd + costs_usd

        self._account.book_pnl(self._leg, pnl_usd)
        self._account.close_position(self._leg)

        ex.trades.append(
            LegTrade(
                dir=pos.d,
                entry_index=pos.entry_index,
                entry_price=pos.entry_price,
                exit_index=done.index,
                qty=ex._qty,
                risk_usd=risk_usd,
                pnl_usd=pnl_usd,
                r=(pnl_usd / risk_usd) if risk_usd > 0 else 0.0,
                entry_ms=ex._entry_ms,
                exit_ms=exit_ms,
                costs_usd=costs_usd,
                exit_price=done.price,
                stop_distance=pos.risk,
                exit_reason=done.reason,
                mfe_price=pos.entry_price + pos.d * done.mfe * pos.risk,
                mae_price=pos.entry_price - pos.d * done.mae * pos.risk,
                mfe_usd=done.mfe * risk_usd,
                mae_usd=-done.mae * risk_usd,
            )
        )
        ex.open = None
        ex._qty = 0.0
        ex._risk_usd = 0.0

    # ── arming ───────────────────────────────────────────────────────────────────────────
    def _arm(self, i: int) -> None:
        """Read any newly CLOSED source trades and arm on the real losses among them.

        The loss filter is the engine's, by value (`r < -scratch_r`), so a scratch never arms —
        counting one would fill the population with trades that had nothing to recover.
        """
        if self._source is None:
            return
        while self._read < len(self._source):
            t = self._source[self._read]
            self._read += 1
            if t.r >= -self._rule.scratch_r:
                continue
            want = -int(t.dir)
            if not self._rule.both_directions and want < 0:
                continue
            self._armed[want] = self._armed.get(want, 0) + 1

    def _look_for_signal(self, i: int, ext) -> None:
        """An external CHoCH in a direction something is waiting for arms the next bar's entry.

        ⚠ The stop is the break leg's FAR end (`bull_bos_low` / `bear_bos_high`), never the level
        that broke — using the broken level puts the stop inside the move that just happened,
        which is a different and much tighter trade.
        """
        if self._pending is not None:
            return
        for want, sos, far in ((1, ext.bull_sos, ext.bull_bos_low),
                               (-1, ext.bear_sos, ext.bear_bos_high)):
            if not sos or far is None or self._armed.get(want, 0) <= 0:
                continue
            self._armed[want] -= 1
            self._pending = {"want": want, "stop": float(far), "signal_index": i}
            return

    def _fill_pending(self, i: int, bar) -> None:
        """Enter at this bar's OPEN, one bar after the signal — the batch rule's fill exactly."""
        pend = self._pending
        if pend is None or pend["signal_index"] >= i:
            return
        self._pending = None
        entry = float(bar.open)
        stop = pend["stop"]
        want = pend["want"]
        risk_price = abs(entry - stop)

        # A stop on the wrong side of the fill is not a tight trade, it is a broken one. Refuse
        # rather than clamp (rule 17) — the batch driver refuses the same setups.
        if risk_price <= 0 or (entry - stop) * want <= 0:
            return
        if self.execution.open is not None:
            self.execution.skipped_concurrent.append(
                {"index": i, "dir": want, "reason": "already holding a recovery"}
            )
            return

        risk_usd = (
            self._account.balance
            * (self.config.unit_risk_pct / 100.0)
            * self._rule.risk_fraction
        )
        desired_qty = risk_usd / (risk_price * self.config.point_value)
        granted = self._account.request_fill(
            self._leg, want, entry, stop, desired_qty, self.config.point_value
        )
        if granted <= 0.0:
            self.execution.blocked.append({"index": i, "dir": want, "reason": "no room"})
            return

        ex = self.execution
        ex._qty = granted
        # The risk this trade ACTUALLY carries after the account scaled it — never the desired
        # figure. Booking R against a size the account refused to grant is the unit error that
        # makes a capped run report an uncapped one's numbers.
        ex._risk_usd = granted * risk_price * self.config.point_value
        ex._entry_ms = int(bar.timestamp_ms)
        ex.open = ManagedPosition(
            self._rule,
            entry_index=i,
            direction=want,
            entry_price=entry,
            stop_price=stop,
            bars_per_day=self.config.bars_per_day,
            last_index=self._last_index,
        )
        self._account.update_stop(self._leg, ex.open.stop, granted)
