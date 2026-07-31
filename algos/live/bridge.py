"""bridge.py — the strategy's intent, mirrored onto MT5.

**The design decision this file implements** (`docs/LIVE_TRADING_PIPELINE.md` D3): the strategy
stays AUTHORITATIVE and the bridge only makes the broker match it. The bridge never decides
whether to trade, what size, or where a stop belongs — every one of those is already computed
by the same `Execution` object the backtest runs, which is what preserves the bar-for-bar parity
with the Pine that was expensive to earn. If a change here would require a trading judgement,
the split is wrong.

**Why a mirror and not a rewrite of the execution layer.** `Execution` is a broker EMULATOR: it
holds its own resting limits (`_pend_long` / `_pend_short`), its own position, and fills them
against bar OHLC. Live, MT5 is the broker. The two could have been merged by tearing the fills
out of the strategy — and that would have thrown away the one thing that makes a live number
comparable to a backtest number. So both run, and this file reconciles them once per closed bar.

**The reconciliation happens at BAR CLOSE, and the timing is load-bearing.** Inside a bar MT5
fills the moment price touches a level, while the emulator only evaluates when `step()` is next
called. Comparing them mid-bar would report a disagreement on every single fill. At bar close,
both have seen the same bar, so a difference that survives is a real one.

**A real difference HALTS the bot.** Not "log and continue", not "adopt the broker's view". A
position the strategy does not know about, or a strategy position the broker does not have,
means the two ledgers have parted and every subsequent decision is computed against a fiction.
The position keeps its broker-side stop (see D4 — the stop always lives at the broker, so a
halt is never an unprotected position), Telegram fires, and a human decides. On a demo, with
Aaron watching, "stop and tell me" is the honest response; silently continuing is how a live
system loses the ability to explain itself.

**What is deliberately NOT supported yet:** partial take-profits. At the shipped
`exec_tp1_pct = exec_tp2_pct = 0` the whole position rides the runner, so each trade is one
entry limit and one ratcheting stop. `assert_supported()` refuses to start with non-zero rungs
rather than silently ignoring them.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Optional


class BridgeState(str, Enum):
    WARMING = "warming"   # the emulator opened a position during warmup — wait for it to flatten
    LIVE = "live"
    HALTED = "halted"     # emulator and broker disagree; no further orders


@dataclass
class _Rest:
    """What we believe is resting at the broker on one side."""
    ticket: int
    price: float
    lots: float
    sl: float


class UnsupportedStrategyConfig(RuntimeError):
    """The strategy is configured to do something the live bridge cannot mirror."""


def assert_supported(strategy_config) -> None:
    """Refuse a configuration the bridge would silently mis-execute.

    Better to not start than to run a strategy whose scale-outs quietly never happen — the
    equity curve would diverge from every backtest and nothing would say why.
    """
    tp1 = float(getattr(strategy_config, "exec_tp1_pct", 0) or 0)
    tp2 = float(getattr(strategy_config, "exec_tp2_pct", 0) or 0)
    if tp1 or tp2:
        raise UnsupportedStrategyConfig(
            f"exec_tp1_pct={tp1} / exec_tp2_pct={tp2} configure partial take-profits, which the "
            f"live bridge does not place yet — it mirrors one entry limit and one ratcheting "
            f"stop. Set both to 0 (the shipped default: bank nothing, ride the runner), or "
            f"build the scale-out path first."
        )
    if getattr(strategy_config, "exec_secondary", False):
        raise UnsupportedStrategyConfig(
            "exec_secondary needs a 1-minute bar stream alongside the 15m one (run_dual). The "
            "live runner drives a single timeframe. Turn it off, or build the dual feed."
        )
    if getattr(strategy_config, "fill_model", "bar") != "bar":
        raise UnsupportedStrategyConfig(
            "fill_model must be 'bar' live. 'tick' is a BACKTEST cost model that resolves fills "
            "against historical tick data; live, the broker resolves fills and its real prices "
            "are recorded by the ledger."
        )


class OrderBridge:
    def __init__(self, bot_mt5, execution, ledger, log, *,
                 notify=None, dry_run: bool = True) -> None:
        self._mt5 = bot_mt5
        self._ex = execution
        self._ledger = ledger
        self._log = log
        self._notify = notify or (lambda text: None)
        self.dry_run = dry_run

        self.state = BridgeState.LIVE
        self._rest: dict[int, Optional[_Rest]] = {1: None, -1: None}
        self._pos_ticket: Optional[int] = None
        self._pos_dir: int = 0
        self._pos_entry: float = 0.0
        self._pos_lots: float = 0.0
        self._pos_stop: float = 0.0
        self._pos_intended: float = 0.0
        self._pos_risk_usd: float = 0.0
        self._pos_opened_bar: Optional[int] = None
        self.halt_reason: str = ""

    # ── startup ──────────────────────────────────────────────────────────────
    def begin_live(self) -> None:
        """Called once, after warmup, before the first live bar.

        If the emulator finished warmup holding a position, that trade's ENTRY happened in the
        past at a price that is gone. Opening it now at market would be a different trade — so
        the bridge sits in WARMING and places nothing until the emulator flattens naturally.
        This is why a bot's first live trade is always one whose entry decision was made on a
        live bar.
        """
        if self._ex._pos_dir != 0:
            self.state = BridgeState.WARMING
            self._log.warning(
                "Warmup ended with the strategy holding a simulated position — its entry is in "
                "the past, so it will NOT be opened live. Waiting for it to close before "
                "placing anything."
            )
            self._ledger.event("warmup_position_skipped", dir=self._ex._pos_dir,
                               entry=self._ex._entry)
        else:
            self.state = BridgeState.LIVE

    def adopt_broker_state(self) -> None:
        """Read what MT5 already holds for this bot's magic, at startup.

        A position we have no record of is NOT adopted — it is a halt. Silently taking over an
        unknown position is how a restart doubles a book: the strategy would size a fresh entry
        with no idea it is already exposed.
        """
        positions = self._mt5.get_open_positions()
        orders = self._mt5.get_pending_orders()
        if positions:
            self._halt(f"MT5 already holds {len(positions)} position(s) under magic "
                       f"{self._mt5.magic} at startup, with no local record of them. Close them "
                       f"by hand (or clear them into the ledger) before starting the bot.")
            return
        for o in orders:
            # Resting orders from a previous run are stale by construction — the strategy
            # recomputes its limit every bar off state we no longer have.
            self._log.info(f"Cancelling stale pending order T{o.ticket} from a previous run")
            self._exec(lambda t=o.ticket: self._mt5.cancel_pending(t),
                       f"cancel stale pending T{o.ticket}")

    # ── the per-bar entry point ──────────────────────────────────────────────
    def sync(self, dec, sig) -> None:
        """Reconcile once, for the bar that just closed. Order matters: observe what the broker
        did during the bar, THEN compare, THEN act."""
        if self.state is BridgeState.HALTED:
            return

        positions = self._mt5.get_open_positions()
        self._observe_close(positions, dec, sig)
        self._observe_open(positions, dec, sig)

        if self.state is BridgeState.WARMING:
            if self._ex._pos_dir == 0:
                self.state = BridgeState.LIVE
                self._log.info("Warmup position closed — the bot is now LIVE and will place orders.")
                self._ledger.event("went_live")
            else:
                return

        if not self._agrees(positions):
            return

        if self._ex._pos_dir != 0:
            self._cancel_all_rest("a position is open")
            self._sync_stop(dec)
        else:
            self._sync_side(1, self._ex._pend_long, sig)
            self._sync_side(-1, self._ex._pend_short, sig)

    # ── observation ──────────────────────────────────────────────────────────
    def _observe_close(self, positions, dec, sig) -> None:
        if self._pos_ticket is None:
            return
        if any(p.ticket == self._pos_ticket for p in positions):
            return
        price, pnl = self._mt5.get_deal_result(self._pos_ticket)
        r = (pnl / self._pos_risk_usd) if self._pos_risk_usd else None
        reason = getattr(dec, "exit_reason", "") or self._infer_exit_reason(price)
        held = None
        if self._pos_opened_bar is not None and getattr(sig, "index", None) is not None:
            held = sig.index - self._pos_opened_bar
        side = "LONG" if self._pos_dir > 0 else "SHORT"
        self._log.info(f"POSITION CLOSED | T{self._pos_ticket} {side} @ {price} | "
                       f"P&L ${pnl:,.2f}" + (f" ({r:+.2f}R)" if r is not None else ""))
        self._ledger.trade_closed(
            ticket=self._pos_ticket, direction=side, symbol=self._mt5.symbol, price=price,
            pnl_usd=pnl, r_multiple=r, reason=reason, lots=self._pos_lots, held_bars=held)
        self._notify(
            f"🔴 *EXIT* {self._mt5.symbol}\n"
            f"{side} {self._pos_lots} lots closed @ {price}\n"
            f"P&L  *${pnl:,.2f}*" + (f"   ({r:+.2f}R)" if r is not None else "") + "\n"
            f"Reason: {reason}"
        )
        self._pos_ticket = None
        self._pos_dir = 0
        self._pos_risk_usd = 0.0
        self._pos_opened_bar = None

    def _observe_open(self, positions, dec, sig) -> None:
        if self._pos_ticket is not None or not positions:
            return
        p = positions[0]
        side = "LONG" if p.type == 0 else "SHORT"
        d = 1 if p.type == 0 else -1
        rest = self._rest.get(d)
        intended = rest.price if rest else 0.0
        # The order that filled is no longer resting.
        self._rest[d] = None
        self._pos_ticket = p.ticket
        self._pos_dir = d
        self._pos_entry = p.price_open
        self._pos_lots = p.volume
        self._pos_stop = p.sl
        self._pos_intended = intended
        self._pos_opened_bar = getattr(sig, "index", None)
        # Risk in dollars, for the R on the exit message. Measured off the BROKER's fill and the
        # stop that was actually attached, not off the strategy's intended price — R has to
        # describe the trade that happened.
        self._pos_risk_usd = abs(p.price_open - p.sl) * p.volume * self._contract_size()
        self._log.info(f"POSITION OPENED | T{p.ticket} {side} {p.volume}L @ {p.price_open} "
                       f"| SL={p.sl}")
        self._ledger.trade_opened(
            ticket=p.ticket, direction=side, symbol=self._mt5.symbol, lots=p.volume,
            price=p.price_open, stop=p.sl, intended_price=intended,
            tp1=getattr(dec, "tp1", 0.0) or 0.0, tp2=getattr(dec, "tp2", 0.0) or 0.0,
            confluences=self._confluences(dec, sig))
        self._notify(
            f"🟢 *ENTRY* {self._mt5.symbol}\n"
            f"{side} {p.volume} lots @ {p.price_open}\n"
            f"Stop {p.sl}\n"
            f"{self._stamp(sig)}"
        )

    def _agrees(self, positions) -> bool:
        """Both ledgers must tell the same story. Anything else halts — see the module
        docstring for why this is not 'log and continue'."""
        emu = self._ex._pos_dir != 0
        broker = bool(positions)
        if len(positions) > 1:
            self._halt(f"MT5 holds {len(positions)} positions under magic {self._mt5.magic}; "
                       f"this strategy takes one at a time.")
            return False
        if emu and not broker:
            self._halt("The strategy believes it is in a position but MT5 has none. Its resting "
                       "limit filled in the emulator and not at the broker (or the position was "
                       "closed outside the bot). Every later decision would be computed against "
                       "a trade that does not exist.")
            return False
        if broker and not emu:
            self._halt("MT5 holds a position the strategy does not know about. It will keep its "
                       "broker-side stop, but the bot will not manage it.")
            return False
        return True

    # ── action ───────────────────────────────────────────────────────────────
    def _sync_side(self, direction: int, pend, sig) -> None:
        """Make the broker's resting order on one side match the strategy's intent."""
        held = self._rest[direction]
        if pend is None:
            if held is not None:
                self._exec(lambda t=held.ticket: self._mt5.cancel_pending(t),
                           f"cancel {self._side(direction)} limit T{held.ticket}")
                self._rest[direction] = None
            return

        lots = self._mt5.normalize_volume(pend.qty)
        if lots <= 0:
            # Not an error — the account is too small for this stop distance. Recorded so the
            # gap between "the strategy wanted a trade" and "no trade exists" is never silent.
            self._ledger.event("order_too_small", dir=direction, wanted_lots=pend.qty,
                               price=pend.edge, stop=pend.sl)
            if held is not None:
                self._exec(lambda t=held.ticket: self._mt5.cancel_pending(t),
                           f"cancel {self._side(direction)} limit T{held.ticket}")
                self._rest[direction] = None
            return

        if held is None:
            self._place(direction, lots, pend, sig)
            return

        # MODIFY cannot change volume (see mt5_ops) — a size change is a cancel + re-place.
        if abs(lots - held.lots) > 1e-9:
            self._exec(lambda t=held.ticket: self._mt5.cancel_pending(t),
                       f"re-size {self._side(direction)} limit T{held.ticket}")
            self._rest[direction] = None
            self._place(direction, lots, pend, sig)
            return

        if self._moved(held.price, pend.edge) or self._moved(held.sl, pend.sl):
            ok = self._exec(
                lambda t=held.ticket: self._mt5.modify_pending(t, pend.edge, pend.sl),
                f"move {self._side(direction)} limit T{held.ticket} → {pend.edge} SL {pend.sl}")
            if ok:
                self._rest[direction] = _Rest(held.ticket, pend.edge, lots, pend.sl)

    def _place(self, direction: int, lots: float, pend, sig) -> None:
        side = "bullish" if direction > 0 else "bearish"
        ticket = self._exec(
            lambda: self._mt5.place_pending_limit(side, lots, pend.edge, pend.sl),
            f"place {self._side(direction)} limit {lots}L @ {pend.edge} SL {pend.sl}")
        if isinstance(ticket, tuple):
            ticket = ticket[0]
        if ticket:
            self._rest[direction] = _Rest(ticket, pend.edge, lots, pend.sl)
            self._ledger.event("order_placed", dir=direction, ticket=ticket, lots=lots,
                               price=pend.edge, stop=pend.sl,
                               sos_bar=getattr(pend, "sos_bar", None))
        elif not self.dry_run:
            # place_pending_limit already logged WHY; record it so a refused setup is countable
            # next to the strategy's own blocked setups.
            self._ledger.event("order_refused", dir=direction, lots=lots,
                               price=pend.edge, stop=pend.sl)

    def _sync_stop(self, dec) -> None:
        """Keep the broker's stop on the open position equal to the strategy's current stop.

        The stop lives AT THE BROKER by design (D4): a crash, a reboot or a dropped network must
        not leave a position unprotected. The bot's job is only to ratchet it.
        """
        want = getattr(dec, "stop", None)
        if want is None or self._pos_ticket is None:
            return
        if not self._moved(self._pos_stop, want):
            return
        ok = self._exec(lambda: self._mt5.move_sl(self._pos_ticket, want),
                        f"move stop T{self._pos_ticket} {self._pos_stop} → {want}")
        if ok:
            self._ledger.event("stop_moved", ticket=self._pos_ticket,
                               was=self._pos_stop, now=want)
            self._pos_stop = want

    def _cancel_all_rest(self, why: str) -> None:
        for d, held in list(self._rest.items()):
            if held is not None:
                self._exec(lambda t=held.ticket: self._mt5.cancel_pending(t),
                           f"cancel {self._side(d)} limit T{held.ticket} ({why})")
                self._rest[d] = None

    # ── plumbing ─────────────────────────────────────────────────────────────
    def _exec(self, action, description: str):
        """Every mutating broker call goes through here, so `--dry-run` is a property of the
        bridge rather than something each call site has to remember."""
        if self.dry_run:
            self._log.info(f"[DRY RUN] would {description}")
            self._ledger.event("dry_run_action", action=description)
            return True
        self._log.info(description)
        return action()

    def _halt(self, reason: str) -> None:
        if self.state is BridgeState.HALTED:
            return
        self.state = BridgeState.HALTED
        self.halt_reason = reason
        self._log.error(f"HALTED: {reason}")
        self._ledger.event("halted", reason=reason)
        self._notify(f"⛔️ *HALTED* {self._mt5.bot_label}\n{reason}\n\n"
                     f"No further orders will be placed. Open positions keep their broker stop.")

    def _moved(self, a: float, b: float) -> bool:
        """Price comparison at the symbol's own precision — a float that differs in the 9th
        decimal is not a moved order, and treating it as one would rewrite every order every
        bar for nothing."""
        try:
            import MetaTrader5 as mt5
            si = mt5.symbol_info(self._mt5.symbol)
            tick = si.point if si and si.point else 0.01
        except Exception:
            tick = 0.01
        return abs(float(a or 0) - float(b or 0)) >= tick

    def _contract_size(self) -> float:
        try:
            import MetaTrader5 as mt5
            si = mt5.symbol_info(self._mt5.symbol)
            return float(si.trade_contract_size) if si else 1.0
        except Exception:
            return 1.0

    def _infer_exit_reason(self, price: float) -> str:
        if not self._pos_stop or not price:
            return "closed"
        hit_stop = (self._pos_dir > 0 and price <= self._pos_stop) or \
                   (self._pos_dir < 0 and price >= self._pos_stop)
        return "stop" if hit_stop else "closed"

    @staticmethod
    def _side(direction: int) -> str:
        return "LONG" if direction > 0 else "SHORT"

    @staticmethod
    def _stamp(sig) -> str:
        from datetime import datetime, timezone
        ms = getattr(sig, "time_ms", None)
        if not ms:
            return ""
        return datetime.fromtimestamp(ms / 1000, tz=timezone.utc).strftime("%Y-%m-%d %H:%M UTC")

    @staticmethod
    def _confluences(dec, sig) -> dict:
        """What was true when the trade opened. Read defensively — this is the record that makes
        "why did this not work" answerable later, and a strategy without one of these fields
        should log the rest rather than nothing."""
        return {
            "l_stage": getattr(dec, "l_stage", None),
            "s_stage": getattr(dec, "s_stage", None),
            "long_edge": getattr(dec, "long_edge", None),
            "short_edge": getattr(dec, "short_edge", None),
            "long_veto": getattr(dec, "long_veto", None),
            "short_veto": getattr(dec, "short_veto", None),
            "tp1": getattr(dec, "tp1", None),
            "tp2": getattr(dec, "tp2", None),
            "bull_div_active": getattr(sig, "bull_div_active", None),
            "bear_div_active": getattr(sig, "bear_div_active", None),
            "recent_ssl": getattr(sig, "recent_ssl", None),
            "recent_bsl": getattr(sig, "recent_bsl", None),
            "ny_hour": getattr(sig, "ny_hour", None),
        }
