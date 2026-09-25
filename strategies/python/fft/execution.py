"""The order layer — one resting limit, one position, a frozen bracket, and what it cost.

🔴 **FFT ENTERS ON A RESTING LIMIT, SO IT DECLARES `entry_style = "resting"`.** The order decided at
a 1-minute close is the order a broker holds for the next minute: the strategy publishes it through
`_pend_long` / `_pend_short`, the live bridge places it, and price comes to it — both books fill off
the same order. That is the SOS Fade shape, and the pending order is SOS Fade's own `_Pending`
record, reused rather than re-declared, because the bridge reads it field by field and a
look-alike class is one renamed field away from a bot that places nothing.

⚠ **ONE POSITION AT A TIME.** Spec rule 10. Measured against the study before it was adopted: it
removes 0 of 157 trades 2020-25 and 0 of 34 in the last year.

⚠ **The fill minute can stop the trade out but only takes profit when the fill was at the open.**
A limit that fills mid-minute has no way to know whether the minute's high came before or after
it, so the target is not credited on that minute — the study's rule, and the conservative one. A
fill AT the open (the minute gapped through the limit) owns the whole minute, so both ends count,
the stop first.

⚠ **A minute that reaches both the stop and the target books the STOP.** Bar data cannot say
which came first; every fill model in this repo takes the answer that does not flatter.
"""

from __future__ import annotations

import math
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Optional, Tuple

_PYPKGS = Path(__file__).resolve().parents[1]
if str(_PYPKGS) not in sys.path:
    sys.path.insert(0, str(_PYPKGS))
_ROOT = Path(__file__).resolve().parents[3]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from live_contract import LiveDecision, LivePositionMixin  # noqa: E402
from sos_fade.execution import Trade, TradeFib, _Pending  # noqa: E402

from backtest.portfolio.account import SoloAccount  # noqa: E402

# The rollover is the broker's day boundary, 17:00 New York, DST-aware — the same instant the
# study's costed run charged swap on (`backtest.reprice.rollovers_between`).
ROLLOVER_HOUR_NY = 17

# The FFT ladder, shallow to deep, for the chart's drawing of each trade's own fib.
_FIB_LADDER = (
    (0.0, "TP3"),
    (0.382, "TP2"),
    (0.5, "TP1"),
    (0.618, "E1"),
    (0.702, "E2"),
    (0.886, "E4"),
    (1.0, "1.0"),
)


@dataclass
class Setup:
    """One spent leg — the 61.8 touched — whether or not it was traded. Reporting only.

    ⚠ The more useful half of the output. The traded ones are also in `trades`; the rest carry
    `why`, the first rule that refused them, which is what the forward log and the study match
    both read. `swept` is the A+ label: a day / session / 4-hour level on the pullback's side was
    taken between the leg's extreme and the touch.
    """

    kind: str  # "first" | "second"
    bar: int
    ts_ms: int
    dir: int
    key: Tuple[int, int]  # (direction, the fib's 1.0 anchor bar on the 5m)
    levels: Dict[str, float]
    nbos: int
    traded: bool
    why: Optional[str]
    fill_price: Optional[float]
    swept: bool
    # The 15m trend's continuation BOS since its shift at the touch (-1 before there is a trend) —
    # the study's `n15`, matched by `tools/compare_study.py`. What the overextension skip reads.
    nbos15: int = -1
    # An active opposite-side 5m equal level (equal highs for a buy) between the 61.8 and TP2, as of
    # the last 5m candle closed before the touch — the lead in `backtest/notes/fft_ledger.md` (11
    # trades 2020-26, all winners, unproven). Reporting only; the forward log grades it.
    eq_target: bool = False


@dataclass
class Fill:
    """The resting order filled on this bar."""

    key: Tuple[int, int]
    price: float
    dir: int


@dataclass
class Miss:
    """A limit that was reached and still did not become a position. Reporting only."""

    ts_ms: int
    dir: int
    reason: str
    price: float


@dataclass
class _Open:
    dir: int
    entry_index: int
    entry_ms: int
    entry_price: float
    qty: float
    stop: float
    open_stop: float
    take_profit: float
    key: List[int]
    kind: str
    levels: Dict[str, float]
    ext_high: float = 0.0
    ext_low: float = 0.0


@dataclass
class _LiveFill:
    """One fill this bar, in the shape `algos/live/bridge.py` reads (`f.kind`, `f.order_id`)."""

    kind: str  # "entry" | "exit"
    order_id: str  # "Long" | "Short" | "L-TP1" | "L-STOP" | "L-CMD" | short mirror
    price: float
    qty: float
    dir: int


class FftExecution(LivePositionMixin):
    """Holds the one resting order and the one position, and books every close."""

    #: Resting limits — see the module docstring and `live_contract.ENTRY_STYLES`.
    entry_style = "resting"

    #: The whole open position; `_Open` is flat, so one entry covers it.
    _POSITION_FIELDS = ("pos",)

    #: A stop is already a broker order and closes itself; the TARGET is sent with the order too
    #: (`planned_full_exit_price`), but a target hit here is still tagged as owned so a broker that
    #: missed it is caught up rather than left holding the position.
    _EXIT_TAGS = {"stop": "STOP", "target": "TP1"}

    def __init__(
        self,
        config,
        initial_capital: float = 10_000.0,
        profile=None,
        *,
        account=None,
        leg: str = "strat",
    ) -> None:
        self._cfg = config
        self._account = account if account is not None else SoloAccount(balance=initial_capital)
        self._leg = leg
        self._profile = profile
        self.trades: List[Trade] = []
        self.blocks: List = []
        self.misses: List[Miss] = []
        self.pos: Optional[_Open] = None
        self.pend: Optional[_Pending] = None
        self._pend_ctx: Optional[dict] = None
        self._close_request: Optional[str] = None
        self._strategy = None
        self.bar_ms: int = 0
        #: How a setup's key is spelled, read by the live alert layer across a promote. Set by
        #: the strategy from `FftSetupWatch.key_scheme`.
        self.setup_key_scheme = ""

    # ── what the bridge reads ────────────────────────────────────────────────
    @property
    def _pend_long(self) -> Optional[_Pending]:
        return self.pend if self.pend is not None and self.pend.dir > 0 else None

    @property
    def _pend_short(self) -> Optional[_Pending]:
        return self.pend if self.pend is not None and self.pend.dir < 0 else None

    @property
    def _pos_dir(self) -> int:
        return 0 if self.pos is None else int(self.pos.dir)

    @property
    def _entry(self) -> Optional[float]:
        return None if self.pos is None else float(self.pos.entry_price)

    @property
    def _entry_ms(self) -> Optional[int]:
        return None if self.pos is None else int(self.pos.entry_ms)

    @property
    def equity(self) -> float:
        return self._account.balance

    @property
    def is_flat(self) -> bool:
        return self.pos is None

    def _encode_position_field(self, name, value):
        if name == "pos" and value is not None:
            return dict(value.__dict__)
        return value

    def _decode_position_field(self, name, value):
        if name == "pos" and value is not None:
            return _Open(**value)
        return value

    def full_exit_price(self) -> Optional[float]:
        """FFT closes the whole position at its one target."""
        if self.pos is None:
            return None
        tp = float(self.pos.take_profit)
        return tp if math.isfinite(tp) and tp > 0 else None

    def planned_full_exit_price(self, pend) -> Optional[float]:
        """The target the resting order would carry if it filled — sent WITH the order, so no
        trade is ever open at the broker without it."""
        if pend is None:
            return None
        tp = float(pend.tp1)
        return tp if math.isfinite(tp) and tp > 0 else None

    def request_close(self, reason: str = "commanded") -> bool:
        if self.pos is None:
            return False
        self._close_request = reason or "commanded"
        return True

    # ── the spread (AccountProfile) ──────────────────────────────────────────
    def _spread(self) -> float:
        p = self._profile
        if p is None or not p.spread_measured:
            return 0.0
        return float(p.spread)

    def _bid_ask(self) -> bool:
        return bool(getattr(self._profile, "bid_ask_fills", False)) and self._spread() > 0

    def _adj(self, direction: int, *, entry: bool) -> float:
        """What to ADD to the chart's BID prices before testing a level. A buy transacts at the
        ask: a long's entry and everything a short does after its entry. 0 with bid/ask fills off.
        """
        if not self._bid_ask():
            return 0.0
        return self._spread() if (direction > 0 if entry else direction < 0) else 0.0

    # ── the order ────────────────────────────────────────────────────────────
    def _qty(self, risk: float) -> float:
        cfg = self._cfg
        if cfg.size_mode == "Fixed contracts":
            return cfg.fixed_qty
        if risk <= 0:
            return float("nan")
        return (self.equity * cfg.exec_risk_pct / 100.0) / (risk * cfg.point_value)

    def size(self, entry: float, stop: float, mult: float = 1.0) -> Optional[float]:
        """The order's size. `None` = no size (a zero stop distance); `0.0` = the account's risk
        budget has no room for it right now. `mult` scales the risk-sized quantity BEFORE the
        budget sees it (a sweep setup's 1.5x), so the account judges the size actually wanted.

        🔴 **The budget is decided HERE, at PLACEMENT, never at the fill** — SOS Fade's
        `_fit_to_budget`, for the same reason: a live order is already resting at the broker by
        the fill, so shrinking or refusing the emulator's copy there leaves the two holding
        different books and the bridge halts. Every minute re-decides the order, so the resting
        size follows the room minute by minute. Inert with no budget stated — every backtest and
        the study gate — so it returns the risk-sized quantity untouched.
        """
        qty = self._qty(abs(entry - stop)) * mult
        if not math.isfinite(qty) or qty <= 0:
            return None
        return self._account.affordable_qty(self._leg, entry, stop, self._cfg.point_value, qty)

    def build_order(
        self,
        direction: int,
        entry: float,
        stop: float,
        target: float,
        *,
        key: Tuple[int, int],
        kind: str,
        levels: Dict[str, float],
        qty: Optional[float] = None,
    ) -> Optional[dict]:
        if qty is None:
            qty = self.size(entry, stop)
        if qty is None or not math.isfinite(qty) or qty <= 0:
            return None
        pend = _Pending(
            dir=direction,
            edge=entry,
            qty=qty,
            sl=stop,
            tp1=target,
            tp2=target,
            sos_bar=None,
            fib=None,
            kind="primary",
        )
        return {"pend": pend, "key": key, "kind": kind, "levels": dict(levels)}

    def set_pending(self, order: Optional[dict]) -> None:
        """What rests for the next minute. `None` cancels."""
        if order is None or self.pos is not None:
            self.pend, self._pend_ctx = None, None
            return
        self.pend, self._pend_ctx = order["pend"], order

    # ── one bar ──────────────────────────────────────────────────────────────
    def resolve(
        self, index: int, ts_ms: int, open_: float, high: float, low: float
    ) -> Optional[Fill]:
        """This bar's prices against the position placed earlier, or else the resting order."""
        if self.pos is not None:
            # 🔴 BY TIME, NEVER BY BAR NUMBER — a live re-warm renumbers bars, so a restored
            # trade's number is from another count and can sit above every bar after it (the
            # 2026-09-24 extreme-leg halt). In a replay the two orders are identical.
            if self.pos.entry_ms < ts_ms:
                self._exits(self.pos, index, ts_ms, open_, high, low)
            self.pend, self._pend_ctx = None, None
            return None
        pend, ctx = self.pend, self._pend_ctx
        self.pend, self._pend_ctx = None, None
        if pend is None:
            return None
        d = pend.dir
        adj = self._adj(d, entry=True)
        if d > 0:
            if low + adj > pend.edge:
                return None
            at_open = open_ + adj <= pend.edge
            price = open_ + adj if at_open else pend.edge
        else:
            if high < pend.edge:
                return None
            at_open = open_ >= pend.edge
            price = open_ if at_open else pend.edge
        if (price - pend.sl) * d <= 0:
            # The minute opened through the stop as well — the study counts no trade here.
            self.misses.append(Miss(ts_ms, d, "opened through the stop", price))
            return None
        granted = self._account.request_fill(
            self._leg, d, price, pend.sl, pend.qty, self._cfg.point_value
        )
        if granted <= 0.0:
            self.misses.append(Miss(ts_ms, d, "no room under the account's risk cap", price))
            return None
        pos = _Open(
            dir=d,
            entry_index=index,
            entry_ms=ts_ms,
            entry_price=price,
            qty=granted,
            stop=pend.sl,
            open_stop=pend.sl,
            take_profit=pend.tp1,
            key=list(ctx["key"]),
            kind=ctx["kind"],
            levels=ctx["levels"],
            ext_high=price,
            ext_low=price,
        )
        self.pos = pos
        # The fill minute: the stop always counts; the target only when the fill was at the open.
        xadj = self._adj(d, entry=False)
        if d > 0:
            hit_stop = low <= pos.stop
            hit_tp = at_open and high >= pos.take_profit
        else:
            hit_stop = high + xadj >= pos.stop
            hit_tp = at_open and low + xadj <= pos.take_profit
        self._widen(pos, high + (xadj if d < 0 else 0.0), low + (xadj if d < 0 else 0.0))
        if hit_stop:
            self._close(pos, index, ts_ms, pos.stop, "stop", market_exit=True)
        elif hit_tp:
            self._close(pos, index, ts_ms, pos.take_profit, "target", market_exit=False)
        return Fill(key=tuple(ctx["key"]), price=price, dir=d)

    def _widen(self, pos: _Open, high: float, low: float) -> None:
        """Reporting-only excursion, bounded by both brackets (a bracket is reached BY the move
        that closes the trade, so nothing beyond it belongs to the trade)."""
        if pos.dir > 0:
            lo, hi = max(low, pos.stop), min(high, pos.take_profit)
        else:
            hi, lo = min(high, pos.stop), max(low, pos.take_profit)
        pos.ext_high = max(pos.ext_high, hi)
        pos.ext_low = min(pos.ext_low, lo)

    def _exits(
        self, pos: _Open, index: int, ts_ms: int, open_: float, high: float, low: float
    ) -> None:
        if self._close_request is not None:
            reason, self._close_request = self._close_request, None
            self._close(pos, index, ts_ms, open_, reason, market_exit=True)
            return
        adj = self._adj(pos.dir, entry=False)
        h, lo, o = high + adj, low + adj, open_ + adj
        self._widen(pos, h, lo)
        if pos.dir > 0:
            hit_stop, hit_tp = lo <= pos.stop, h >= pos.take_profit
            stop_fill, tp_fill = min(pos.stop, o), max(pos.take_profit, o)
        else:
            hit_stop, hit_tp = h >= pos.stop, lo <= pos.take_profit
            stop_fill, tp_fill = max(pos.stop, o), min(pos.take_profit, o)
        if hit_stop:
            self._close(pos, index, ts_ms, stop_fill, "stop", market_exit=True)
        elif hit_tp:
            self._close(pos, index, ts_ms, tp_fill, "target", market_exit=False)

    # ── booking ──────────────────────────────────────────────────────────────
    def _charge(self, pos: _Open, exit_ms: int, market_exit: bool) -> float:
        """Everything this trade paid, as positive dollars. Zero means nothing was priced."""
        p = self._profile
        if p is None:
            return 0.0
        pv = self._cfg.point_value
        cost = p.commission(pos.qty) * 2.0
        s = self._spread()
        if s > 0 and not self._bid_ask():
            cost += s * pos.qty * pv
        if market_exit and getattr(p, "slippage_ticks", 0):
            cost += p.slippage_ticks * p.mintick * pos.qty * pv
        from backtest.reprice import rollovers_between

        for day in rollovers_between(pos.entry_ms, exit_ms, ROLLOVER_HOUR_NY):
            cost -= p.swap_charge(pos.dir, pos.qty, day)
        return cost

    def _close(
        self, pos: _Open, index: int, ts_ms: int, price: float, reason: str, *, market_exit: bool
    ) -> None:
        pv = self._cfg.point_value
        costs = self._charge(pos, ts_ms, market_exit)
        pnl = (price - pos.entry_price) * pos.dir * pos.qty * pv - costs
        risk_usd = abs(pos.entry_price - pos.open_stop) * pos.qty * pv
        self._account.book_pnl(self._leg, pnl)
        mfe = pos.ext_high if pos.dir > 0 else pos.ext_low
        mae = pos.ext_low if pos.dir > 0 else pos.ext_high
        lv = pos.levels
        self.trades.append(
            Trade(
                dir=pos.dir,
                entry_index=pos.entry_index,
                entry_price=pos.entry_price,
                exit_index=index,
                qty=pos.qty,
                risk_usd=risk_usd,
                pnl_usd=pnl,
                r=(pnl / risk_usd) if risk_usd > 0 else 0.0,
                entry_ms=pos.entry_ms,
                exit_ms=ts_ms,
                costs_usd=-costs,
                exit_price=price,
                stop_distance=abs(pos.entry_price - pos.open_stop),
                exit_reason=reason,
                kind="primary",
                mfe_price=round(mfe, 5),
                mae_price=round(mae, 5),
                mfe_usd=round((mfe - pos.entry_price) * pos.dir * pos.qty * pv, 2),
                mae_usd=round((mae - pos.entry_price) * pos.dir * pos.qty * pv, 2),
                legs=[{"reason": reason, "price": round(price, 5), "ms": ts_ms, "qty": pos.qty}],
                tp_rungs=((pos.take_profit, 100.0),),
                fib=TradeFib(levels=[(r, float(lv[k])) for r, k in _FIB_LADDER if k in lv]),
            )
        )
        self._account.close_position(self._leg)
        self.pos = None

    # ── pre-trade setup snapshots (backtest/setups.py) — reporting only ───────
    def live_setups(self):
        """What the strategy's setup watch holds — `setups.py`. Read AFTER `step()`."""
        return self._strategy.setup_watch.live_setups()

    def drain_setups(self):
        """`live_setups()`, then forget the ended ones. The live runner calls it once per bar."""
        return self._strategy.setup_watch.drain_setups()

    # ── the live contract ────────────────────────────────────────────────────
    def step(self, sig, seq) -> LiveDecision:
        """One bar through the live contract — delegates to the strategy's own `step`."""
        if self._strategy is None:
            raise RuntimeError("FftExecution.step() needs the strategy that owns it")
        before_trades = len(self.trades)
        before_pos = self.pos
        self._strategy.step(sig)
        dec = LiveDecision(index=getattr(getattr(sig, "bar", None), "index", 0))
        # An entry that appeared on THIS bar, by identity — a trade opened and closed inside one
        # minute must still report its entry.
        opened = [t for t in self.trades[before_trades:] if t.entry_index == dec.index]
        if self.pos is not None and self.pos is not before_pos:
            side = "Long" if self.pos.dir > 0 else "Short"
            dec.fills.append(
                _LiveFill(
                    "entry",
                    side,
                    float(self.pos.entry_price),
                    float(self.pos.qty),
                    int(self.pos.dir),
                )
            )
        for t in opened:
            side = "Long" if t.dir > 0 else "Short"
            dec.fills.append(
                _LiveFill("entry", side, float(t.entry_price), float(t.qty), int(t.dir))
            )
        for t in self.trades[before_trades:]:
            side = "L" if t.dir > 0 else "S"
            dec.fills.append(
                _LiveFill(
                    "exit",
                    f"{side}-{self._EXIT_TAGS.get(t.exit_reason, 'CMD')}",
                    float(t.exit_price),
                    float(t.qty),
                    int(t.dir),
                )
            )
            dec.exit_reason = t.exit_reason
        dec.stop = None if self.pos is None else float(self.pos.stop)
        dec.tp1 = None if self.pos is None else float(self.pos.take_profit)
        dec.long_armed = self._pend_long is not None
        dec.short_armed = self._pend_short is not None
        dec.long_edge = None if self._pend_long is None else float(self._pend_long.edge)
        dec.short_edge = None if self._pend_short is None else float(self._pend_short.edge)
        return dec
