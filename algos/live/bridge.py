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

import sys
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import Optional

# `notify` lives in algos/shared. The runner puts it on sys.path before importing this module,
# but a test that imports the bridge alone must not have to know that — an import path is not a
# contract worth restating in every caller.
_SHARED = Path(__file__).resolve().parent.parent / "shared"
if str(_SHARED) not in sys.path:
    sys.path.insert(0, str(_SHARED))

import alerts        # noqa: E402
import notify        # noqa: E402  (for the TRADE/HEALTH routing kinds only)

# A sibling module, imported the same flat way the runner imports this one — `algos/live/` is put
# on the path by whoever loads the package, and a test that imports the bridge alone must not have
# to know that either.
_HERE = Path(__file__).resolve().parent
if str(_HERE) not in sys.path:
    sys.path.insert(0, str(_HERE))

import position_state  # noqa: E402
from alert_format import alert, joined  # noqa: E402
from order_sizing import (  # noqa: E402
    DEFAULT_MARGIN_SAFETY_PCT, SizedOrder, plan_order,
)


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
                 notify=None, dry_run: bool = True,
                 margin_safety_pct: float = DEFAULT_MARGIN_SAFETY_PCT,
                 account_risk_cap_pct: Optional[float] = None,
                 instance_dir: Optional[Path] = None) -> None:
        self._mt5 = bot_mt5
        # Where `position.json` lives. `None` disables the whole restore path — the bridge then
        # behaves exactly as it did before it existed, which is what every offline test that does
        # not care about restarts gets, and what a caller with no instance directory deserves.
        self._instance_dir = instance_dir
        # Set by `adopt_broker_state` when it has VERIFIED a recorded position against the broker,
        # and consumed by `apply_restore` after the warm-up. It is held rather than applied on the
        # spot because the warm-up replays 5,000 bars through this same emulator and would
        # overwrite anything written before it — see `apply_restore`.
        self._pending_restore: Optional[dict] = None
        self._restored = False
        self._ex = execution
        self._ledger = ledger
        self._log = log
        self._notify = notify or (lambda text, kind, reply_to=None: None)
        self.dry_run = dry_run
        self._margin_safety_pct = float(margin_safety_pct)
        # The ACCOUNT-level cap: max open risk across EVERY bot on this account, as a % of the
        # live balance. `None` = uncapped, which is the honest state for a one-bot account and
        # is what every result measured before it existed was taken on — inventing a default
        # would change a live bot's behaviour with no measurement behind it. The runner SAYS
        # which state it is in at startup, so "no cap" is a reported fact rather than an
        # absence nobody noticed (the `deadman_url` precedent). See G10.
        self._risk_cap_pct = (None if account_risk_cap_pct is None
                              else float(account_risk_cap_pct))
        self._strategy_name = getattr(bot_mt5, "bot_label", "") or "strategy"

        self.state = BridgeState.LIVE
        self._rest: dict[int, Optional[_Rest]] = {1: None, -1: None}
        # Why the LAST refusal is remembered per side, rather than just logged and dropped.
        # A refused order is not by itself a broken state — the setup may never fill, and
        # halting on every unaffordable setup would stop a bot for a trade that never happened.
        # But if the EMULATOR then fills that same setup, the two ledgers part, and the halt
        # message must say *why the broker had no order* instead of the generic "your limit
        # filled here and not there". On 2026-08-07 that generic message was all Aaron got.
        self._refused: dict[int, str] = {1: "", -1: ""}
        # One alert per distinct refusal per side. Re-stating an unaffordable setup every bar
        # for the six hours it rests is how a channel gets muted before the day it matters.
        self._refusal_alerted: dict[int, str] = {1: "", -1: ""}
        self._pos_ticket: Optional[int] = None
        self._pos_dir: int = 0
        self._pos_entry: float = 0.0
        self._pos_lots: float = 0.0
        self._pos_stop: float = 0.0
        self._pos_intended: float = 0.0
        self._pos_risk_usd: float = 0.0
        self._pos_opened_bar: Optional[int] = None
        # Telegram's id for THIS position's entry message. The exit replies to it, so the two
        # halves of a trade read as one thread. None means the entry alert never landed, and the
        # exit then goes out standalone rather than not at all.
        self._pos_alert_id = None
        self.halt_reason: str = ""

    @property
    def is_flat(self) -> bool:
        """No position open AND nothing resting at the broker.

        Stricter than "no position" on purpose. This is the seam a runtime config change
        is applied on (see `runner._maybe_reload_runtime`), and a resting limit is an
        order the OLD settings sized and priced. Waiting for it to fill or be cancelled is
        what keeps every trade attributable to exactly one configuration — otherwise the
        ledger records a trade at 5% risk that was actually sized at 10%.
        """
        return self._pos_ticket is None and not any(self._rest.values())

    # ── startup ──────────────────────────────────────────────────────────────
    def begin_live(self) -> None:
        """Called once, after warmup, before the first live bar.

        If the emulator finished warmup holding a position, that trade's ENTRY happened in the
        past at a price that is gone. Opening it now at market would be a different trade — so
        the bridge sits in WARMING and places nothing until the emulator flattens naturally.
        This is why a bot's first live trade is always one whose entry decision was made on a
        live bar.
        """
        if self._restored:
            # A RESTORED position is not a warm-up artefact: its entry is a real fill this bot
            # made and recorded, and the broker is holding it right now. The bridge must go
            # straight to LIVE so the very next bar can ratchet its stop — sitting in WARMING
            # would reproduce the exact failure the restore exists to end, one layer up.
            self.state = BridgeState.LIVE
            return
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

        **The one exception is a position this bot wrote down itself** (`position_state.py`): a
        restart with a trade open used to halt and leave that trade unmanaged overnight — its
        broker stop stood, but nothing ratcheted it and the time stop never fired. If the record
        matches the broker on ticket, direction, size, entry and stop, the position is held for
        `apply_restore` to hand back to the emulator after the warm-up. **Every other shape still
        halts**, including a torn record, a ticket that does not match, and a single field that
        disagrees.
        """
        positions = self._mt5.get_open_positions()
        orders = self._mt5.get_pending_orders()
        if positions:
            if not self._stage_restore(positions):
                return
        for o in orders:
            # Resting orders from a previous run are stale by construction — the strategy
            # recomputes its limit every bar off state we no longer have.
            self._log.info(f"Cancelling stale pending order T{o.ticket} from a previous run")
            self._exec(lambda t=o.ticket: self._mt5.cancel_pending(t),
                       f"cancel stale pending T{o.ticket}")

    def _stage_restore(self, positions) -> bool:
        """Can this broker position be proved to be the one we wrote down? Halt if not.

        Returns True when a restore has been staged, False when the bridge has halted. The five
        refusals below are deliberately separate messages: "the two disagreed" is true of every
        cause at once and sends the reader to the wrong half of the system — the same defect the
        halt message for a vanished order was fixed for on 2026-08-07.
        """
        magic = self._mt5.magic
        if len(positions) > 1:
            self._halt(f"MT5 holds {len(positions)} positions under magic {magic} at startup; "
                       f"this strategy takes one at a time, so no record can describe them. "
                       f"Close them by hand before starting the bot.")
            return False

        p = positions[0]
        if self._instance_dir is None:
            self._halt(f"MT5 already holds a position under magic {magic} at startup and this "
                       f"bridge was built with no instance directory, so it cannot read the "
                       f"position record. Close it by hand before starting the bot.")
            return False

        record = position_state.read(self._instance_dir)
        if record is None:
            self._halt(
                f"MT5 already holds position T{p.ticket} under magic {magic} at startup, and "
                f"there is no usable record of it in "
                f"{position_state.path_for(self._instance_dir)}. The bot will NOT take it over — "
                f"it would size its next entry with no idea it is already exposed. The position "
                f"keeps its broker-side stop. Close it by hand, or clear it, before restarting.")
            return False

        symbol = getattr(self._mt5, "symbol", "") or ""
        if record.magic != magic or (symbol and record.symbol != symbol):
            self._halt(
                f"The position record in {position_state.path_for(self._instance_dir)} was "
                f"written for {record.symbol} magic {record.magic}, and this bot is "
                f"{symbol or '?'} magic {magic}. It describes a different bot's trade.")
            return False

        if int(p.ticket) != record.ticket:
            self._halt(
                f"MT5 holds position T{p.ticket} under magic {magic}, but the record describes "
                f"T{record.ticket}. Whatever is open is not the trade this bot wrote down, so it "
                f"will not be managed. The position keeps its broker-side stop.")
            return False

        diffs = position_state.disagreements(record, p, point=self._point())
        if diffs:
            self._halt(
                f"The recorded position T{record.ticket} and the one MT5 holds do not match: "
                + "; ".join(diffs)
                + ". Something changed it outside the bot — a hand edit in the terminal is the "
                  "usual cause. It will NOT be adopted: every later stop move would be computed "
                  "off a level the strategy never chose. The position keeps its broker-side "
                  "stop; fix it by hand, or close it, then restart.")
            return False

        # Verified. The bridge's own bookkeeping can be set now; the EMULATOR's cannot, because
        # the warm-up has not run yet and would overwrite it (see `apply_restore`).
        self._pending_restore = record.strategy
        self._pos_ticket = int(p.ticket)
        self._pos_dir = record.broker.dir
        self._pos_entry = record.broker.entry
        self._pos_lots = record.broker.lots
        self._pos_stop = record.broker.stop
        # NOT known across a restart, and each is left at the value that reads as "unknown"
        # rather than at a plausible stand-in. `_pos_intended` would otherwise report a slippage
        # of zero, which is a measurement nobody took; `_pos_opened_bar` counts from wherever
        # this process's warm-up stopped, so a held-bars figure derived from it would be an
        # arbitrary integer wearing a real field's name.
        self._pos_intended = 0.0
        self._pos_opened_bar = None
        # No entry alert exists in this process, so the exit posts standalone instead of as a
        # reply. One orphaned exit message beats no exit message.
        self._pos_alert_id = None
        self._pos_risk_usd = abs(record.broker.entry - record.broker.stop) * \
            record.broker.lots * self._contract_size()
        return True

    def stage_rewarm(self) -> None:
        """Carry an OPEN position across a re-warm. Call BEFORE the strategy is rebuilt.

        🔴 **A re-warm mid-trade used to lose the position and halt the bot, and it is the more
        likely door onto the same failure than a process restart.** `_recover_link` and the
        `gap > 4` branch both rebuild the strategy and replay 5,000 bars through a fresh
        emulator — so a link outage while a trade was open (MetaTrader auto-updated under the
        bot for 50 minutes on 2026-08-04) left the broker holding a position the emulator knew
        nothing about, and `_agrees` halted on the very next bar. The bot survived the outage and
        then stopped managing the trade because of the recovery.

        Nothing is verified against the broker here, and nothing needs to be: this is the same
        process that has been holding the position all along, so the state is not a claim being
        re-read off disk — it is being handed from one emulator instance to the next.
        """
        if self._pos_ticket is None:
            self._pending_restore = None
            return
        try:
            self._pending_restore = self._ex.snapshot_position()
        except Exception as e:
            # Deliberately not a halt: the re-warm has not happened yet, so halting here would
            # stop a bot that is still perfectly coherent. `_agrees` halts on the next bar if the
            # position really is lost, which is the existing, tested path.
            self._pending_restore = None
            self._log.error(
                f"Could not carry the open position across the re-warm: {e}. The bridge will "
                f"halt on the next bar if the strategy and the broker have parted.")

    def apply_restore(self, *, announce: bool = True) -> bool:
        """Hand the verified position back to the emulator. Call AFTER the warm-up.

        ⚠ **The ORDER is the whole reason this is a second method.** `warm()` replays ~5,000 bars
        through this same `Execution` object, and that replay opens and closes imaginary trades of
        its own — so anything written into the emulator before it is overwritten by a fiction.
        Staging at `adopt_broker_state` (which must read the broker before anything else can take
        time) and applying here is what keeps the real position the last word.
        """
        if self._pending_restore is None:
            return False
        snap = self._pending_restore
        self._pending_restore = None
        try:
            self._ex.restore_position(snap)
        except Exception as e:
            # A record that got past every check above and still cannot be applied means the
            # emulator's own state shape moved under a record written by an older build. Halting
            # is the same answer as an unreadable record, for the same reason.
            self._halt(f"The recorded position T{self._pos_ticket} passed every broker check and "
                       f"the strategy refused to restore it: {e}. This usually means the record "
                       f"was written by a different version of the strategy. The position keeps "
                       f"its broker-side stop; close it by hand, or clear the record, then "
                       f"restart.")
            return False
        self._restored = True
        self._log.info(
            f"Restored position T{self._pos_ticket} — {self._side(self._pos_dir)} "
            f"{self._pos_lots} lots @ {self._pos_entry}, stop {self._pos_stop}, "
            f"stage {getattr(self._ex, '_stage', '?')}. It will be managed from the next bar.")
        self._ledger.event("position_restored", ticket=self._pos_ticket, dir=self._pos_dir,
                           lots=self._pos_lots, entry=self._pos_entry, stop=self._pos_stop,
                           stage=getattr(self._ex, "_stage", None),
                           reason="restart" if announce else "rewarm")
        # ⚠ A re-warm passes `announce=False` and the record above still lands. `_recover_link`
        # and the gap branch each already send their own message for the SAME event, and two
        # alerts for one event is how a channel gets muted — but the ledger has to carry it
        # either way, because "the position survived the re-warm" is exactly what a later audit
        # needs and it is invisible from the outside.
        if announce:
            self._notify(alert(
                "🔄", "TRADE RESUMED", self._strategy_name,
                joined([f"{self._side(self._pos_dir)} {self._pos_lots} lots @ {self._pos_entry}",
                        f"stop {self._pos_stop}"]),
                "The bot restarted and picked its open trade back up. It manages it from the "
                "next bar. Nothing to do."),
                notify.HEALTH)
        return True

    def _save_position(self) -> None:
        """Write the open position down, so a restart can pick it up. Never raises.

        Called after every change to the position — the fill, and every stop move — because the
        stop is the field that moves, and a record holding last hour's stop would be REFUSED at
        the next start (the broker's real stop would disagree with it). A stale record does not
        adopt a wrong stop; it costs the restore.
        """
        if self._instance_dir is None or self._pos_ticket is None:
            return
        try:
            snap = self._ex.snapshot_position()
        except Exception as e:
            self._log.warning(f"Could not snapshot the position for the restart record: {e}")
            return
        ok = position_state.write(
            self._instance_dir,
            bot=getattr(self._ledger, "bot_key", "") or self._strategy_name,
            symbol=getattr(self._mt5, "symbol", "") or "",
            magic=self._mt5.magic,
            ticket=self._pos_ticket,
            broker=position_state.BrokerFacts(
                dir=self._pos_dir, lots=self._pos_lots,
                entry=self._pos_entry, stop=self._pos_stop),
            strategy=snap,
        )
        if not ok:
            self._log.warning(
                "Could not write the position record. The trade is unaffected; a restart before "
                "it closes would halt rather than resume it.")

    # ── the per-bar entry point ──────────────────────────────────────────────
    def sync(self, dec, sig) -> None:
        """Reconcile once, for the bar that just closed. Order matters: observe what the broker
        did during the bar, THEN compare, THEN act."""
        if self.state is BridgeState.HALTED:
            return

        positions = self._mt5.get_open_positions()
        self._observe_close(positions, dec, sig)
        self._observe_open(positions, dec, sig)
        # AFTER `_observe_open`, which consumes `_rest[d]` when a position appears — otherwise a
        # perfectly ordinary fill reads as a vanished order.
        self._observe_vanished()

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
        # NET of swap and commission, with the parts kept separate — see
        # `mt5_ops.get_deal_breakdown`. The R below is therefore the R the ACCOUNT got, not the
        # R the price move implies, which is the only version worth alerting on: a scratch that
        # is +0.02R gross and −0.06R after an overnight swap is a loss, and reporting the gross
        # would make the live record disagree with the balance for no stated reason.
        #
        # `get_deal_breakdown` is optional on the handle on purpose. This bridge is driven by
        # test doubles and by an older `mt5_ops` on any box that has not pulled, and a missing
        # method must degrade to the previous behaviour rather than crash out of an EXIT path —
        # losing the exit record is far worse than losing the cost breakdown.
        costs = None
        if hasattr(self._mt5, "get_deal_breakdown"):
            b = self._mt5.get_deal_breakdown(self._pos_ticket)
            # `deals: 0` is "not found", not "free" — fall back rather than book zero costs.
            if b and b.get("deals"):
                costs = b
        if costs is not None:
            price, pnl = costs["close_price"], costs["net_usd"]
        else:
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
            pnl_usd=pnl, r_multiple=r, reason=reason, lots=self._pos_lots, held_bars=held,
            # The measurement this bot was armed to take. `entry_price`/`intended_price` give
            # entry slippage, gross-vs-net gives the real cost of the hold, and both are needed
            # per trade because a single netted figure cannot be taken apart afterwards.
            gross_usd=costs["gross_usd"] if costs else None,
            swap_usd=costs["swap_usd"] if costs else None,
            commission_usd=costs["commission_usd"] if costs else None,
            entry_price=self._pos_entry, intended_price=self._pos_intended)
        self._notify(alerts.format_exit(
            strategy=self._strategy_name, symbol=self._mt5.symbol, exit_price=price,
            pnl_usd=pnl, r_multiple=r, digits=self._digits(),
            # Nested getattr on purpose: this package reads the strategy defensively everywhere
            # else, and a strategy without a `cfg` must not be able to stop an exit alert.
            scratch_r=getattr(getattr(self._ex, "cfg", None), "exec_scratch_r", 0.15),
            threaded=self._pos_alert_id is not None,
            # The SAME reason the ledger records, so the message and the audit trail cannot
            # disagree. It is what separates a -0.02R scratch from a -1.00R loser on a screen
            # where both say "exited at a stop", and only one of them is the risk rule working.
            exit_reason="" if reason == "closed" else reason,
            when=self._bar_time(sig)),
            notify.TRADE, reply_to=self._pos_alert_id)
        self._pos_ticket = None
        self._pos_dir = 0
        self._pos_risk_usd = 0.0
        self._pos_opened_bar = None
        self._pos_alert_id = None
        # The trade is over, so the restart record describes a ticket that no longer exists. It
        # could not restore anything (the ticket cannot match a position that is not there), but
        # leaving it would put a dead trade in front of the next person reading the instance
        # directory. `_restored` is cleared too: the NEXT position is an ordinary live fill.
        self._restored = False
        if self._instance_dir is not None:
            position_state.clear(self._instance_dir)

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
            # Read off the strategy LIVE, not cached at construction — the runner mutates
            # this same config object when a runtime change is applied, so caching it here
            # would record the risk the bot started with rather than the one it sized on.
            # `Execution.cfg` is a real property; the nested getattr is only so a test
            # double without one does not break an alert.
            risk_pct=getattr(getattr(self._ex, "cfg", None), "exec_risk_pct", None),
            confluences=self._confluences(dec, sig))
        self._pos_alert_id = self._notify(alerts.format_entry(
            strategy=self._strategy_name, symbol=self._mt5.symbol, direction=side,
            entry=p.price_open, stop=p.sl, lots=p.volume,
            digits=self._digits(), point=self._point(),
            # The dollars already computed above, and the % that produced them. This is the ONLY
            # message that states the risk — the exit replies to it, so repeating it there is
            # repeating what is one tap up the thread.
            risk_usd=self._pos_risk_usd or None,
            risk_pct=getattr(getattr(self._ex, "cfg", None), "exec_risk_pct", None),
            when=self._bar_time(sig)),
            notify.TRADE)
        # Record it the moment it exists, not at the end of the bar: a process that dies between
        # the fill and the next stop move must still leave a resumable trade behind.
        self._save_position()

    def _observe_vanished(self) -> None:
        """A resting order that is gone from the broker WITHOUT having filled.

        🔴 **Built 2026-08-07 because nothing could see this.** The bot's sell limit was deleted
        by the broker with `deleted [no money]` — it could not afford to activate 54.82 lots on a
        $2,000 account — and the bot had no idea. It kept believing the order was resting, the
        emulator filled itself on the same bar, and the only symptom anywhere in the system was a
        generic halt six hours later saying the two disagreed.

        A pending order can leave the book three ways: it FILLS (a position appears, handled one
        method up), WE cancel it (`_rest[d]` is cleared at the same moment), or the BROKER removes
        it — margin, expiry, an admin action, a manual delete in the terminal. Only the third
        reaches here, and it is always worth a message: it means an order the strategy is still
        counting on does not exist.
        """
        if not any(self._rest.values()):
            return
        live = {o.ticket for o in (self._mt5.get_pending_orders() or [])}
        for d, held in list(self._rest.items()):
            if held is None or held.ticket in live:
                continue
            self._rest[d] = None
            why = (f"The {self._side(d)} limit T{held.ticket} ({held.lots} lots @ {held.price}) "
                   f"is no longer at the broker and never filled. The broker removed it — the "
                   f"usual cause is that the account could not afford to activate it.")
            self._log.error(why)
            self._ledger.event("order_vanished", dir=d, ticket=held.ticket, lots=held.lots,
                               price=held.price, stop=held.sl)
            # HEALTH, not TRADE: no trade happened. It is the machinery failing to carry out an
            # instruction, which is the same class of fact as a halt.
            self._notify(alert(
                "⚠️", "ORDER GONE", self._mt5.bot_label,
                why,
                "The strategy still expects it. Check the account's free margin."),
                notify.HEALTH)

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
            # Name the refusal if there was one. The generic sentence below is true but useless
            # on its own — it describes the symptom of every cause at once, and on 2026-08-07 it
            # sent the reader looking at the fill logic when the answer was the order size.
            because = self._refused.get(self._ex._pos_dir, "") or \
                self._refused.get(1, "") or self._refused.get(-1, "")
            self._halt(
                "The strategy believes it is in a position but MT5 has none. Its resting "
                "limit filled in the emulator and not at the broker (or the position was "
                "closed outside the bot). Every later decision would be computed against "
                "a trade that does not exist."
                + (f"\nThe last order on this side was REFUSED: {because}" if because else ""))
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
            self._refused[direction] = ""
            self._refusal_alerted[direction] = ""
            return

        plan = self._plan(direction, pend)
        if not plan.ok:
            self._record_refusal(direction, plan, pend)
            if held is not None:
                # The strategy still wants this trade, but we cannot place it at the size it
                # asked for. Leaving a stale order resting would mean the broker carries a size
                # nobody currently endorses.
                self._exec(lambda t=held.ticket: self._mt5.cancel_pending(t),
                           f"cancel {self._side(direction)} limit T{held.ticket} (refused)")
                self._rest[direction] = None
            return

        self._refused[direction] = ""
        self._refusal_alerted[direction] = ""
        lots = plan.lots

        if held is None:
            self._place(direction, lots, pend, sig, plan)
            return

        # MODIFY cannot change volume (see mt5_ops) — a size change is a cancel + re-place.
        if abs(lots - held.lots) > 1e-9:
            self._exec(lambda t=held.ticket: self._mt5.cancel_pending(t),
                       f"re-size {self._side(direction)} limit T{held.ticket}")
            self._rest[direction] = None
            self._place(direction, lots, pend, sig, plan)
            return

        if self._moved(held.price, pend.edge) or self._moved(held.sl, pend.sl):
            ok = self._exec(
                lambda t=held.ticket: self._mt5.modify_pending(t, pend.edge, pend.sl),
                f"move {self._side(direction)} limit T{held.ticket} → {pend.edge} SL {pend.sl}")
            if ok:
                self._rest[direction] = _Rest(held.ticket, pend.edge, lots, pend.sl)

    # ── sizing ───────────────────────────────────────────────────────────────
    #
    # 🔴 EVERY order goes through `_plan`, and `_plan` is the ONLY place a lot count is
    # produced. That single-seam rule is the fix for 2026-08-07: before it, the conversion from
    # the strategy's units to MT5's lots did not exist anywhere, and there was no one place a
    # reviewer could have looked to notice.

    def _plan(self, direction: int, pend):
        """How many lots, or why not. See `algos/shared/order_sizing.py` for the reasoning."""
        spec = self._mt5.symbol_spec()
        if spec is None:
            from order_sizing import SizingRefusal
            return SizingRefusal(
                "symbol_unreadable",
                f"the terminal returned no symbol info for {self._mt5.symbol}, so nothing is "
                f"known about lot size, tick value or the volume band.")

        side = "bullish" if direction > 0 else "bearish"
        cfg = getattr(self._ex, "cfg", None)
        plan = plan_order(
            qty_units=pend.qty,
            entry=pend.edge,
            stop=pend.sl,
            spec=spec,
            # Read LIVE off the strategy, never cached at construction — the runner mutates this
            # same config object when a runtime risk change is applied, and a cached copy would
            # size against the risk the bot started with.
            point_value=float(getattr(cfg, "point_value", 1.0) or 1.0),
            # The BROKER's balance, not the emulator's. This is the second half of the
            # 2026-08-07 fix: the emulator compounds its warm-up replay, so its equity had drifted
            # to ~$4,423 against a real $2,000 and it sized every order off the fiction.
            account_equity=self._account_balance(),
            risk_pct=getattr(cfg, "exec_risk_pct", None),
            free_margin=self._mt5.free_margin(),
            margin_for=lambda lots: self._mt5.margin_for(side, lots, pend.edge),
            margin_safety_pct=self._margin_safety_pct,
        )
        # The ACCOUNT-level cap runs LAST, on a plan that already passed every per-order check.
        # Order matters: a refusal should name the first thing wrong with the order itself
        # (a collapsed stop, an unaffordable margin, a size below the broker minimum) before it
        # starts talking about what OTHER bots are holding.
        return self._account_cap_check(plan, spec)

    def _account_cap_check(self, plan, spec):
        """Does this order fit inside the whole ACCOUNT's risk budget?

        This is the one check that reads past this bot's own magic number, and it is the reason
        `mt5_ops.account_exposure()` exists. Every other read in the live path is magic-filtered —
        correct for isolation, and precisely what makes a bot blind to the account it shares.

        ⚠ **This bot's OWN exposure is excluded, and that is not a shortcut.** The strategy has
        ONE position slot, so anything of ours already on the book is the thing this order
        REPLACES (`_sync_side` cancels and re-places on a size change), never something it adds
        to. Counting it would make the bot refuse its own re-sizes as soon as it was near the cap,
        which reads exactly like a broken strategy.

        ⚠ **It refuses; it never shrinks.** `algos/shared/account_risk.py` records why at length:
        a resized order is not the trade the strategy's emulator is holding, the two grade
        different R, and `_agrees` eventually halts the bot on a divergence the safety feature
        created. The backtest allocator SHRINKS instead, which is coherent there because the
        account hands the granted size back; nothing hands a size back across a process boundary.
        """
        from account_risk import RiskUnmeasurable, check_account_cap, measure_exposure

        if self._risk_cap_pct is None or not plan.ok:
            return plan

        from order_sizing import SizingRefusal
        items = self._mt5.account_exposure()
        if items is None:
            # The terminal could not be asked. Same call as an uncomputable margin: "cannot ask"
            # is never "affordable", and a cap that opens itself when the terminal wobbles is a
            # cap that is absent exactly when the account is least healthy.
            return SizingRefusal(
                "account_risk_unreadable",
                "the account's open positions and orders could not be read, so the account-level "
                "risk cap cannot be checked. Refusing rather than assuming the account is empty.")
        try:
            open_risk = measure_exposure(
                [it for it in items if it.magic != self._mt5.magic], spec)
        except RiskUnmeasurable as e:
            return SizingRefusal("account_risk_unmeasurable", str(e))

        # `risk_ccy`, not `intended_risk_ccy` — the cap bounds what actually goes ON THE BOOK,
        # and rounding to the broker's volume step is always DOWN, so the intended figure would
        # refuse orders that genuinely fit. The two differ by less than one volume step, but a
        # refusal a reader cannot reproduce from the order that was placed is a refusal nobody
        # can act on.
        verdict = check_account_cap(
            new_order_risk_ccy=plan.risk_ccy, open_risk=open_risk,
            balance=self._account_balance(), cap_pct=self._risk_cap_pct)
        if verdict.allowed:
            return plan
        return SizingRefusal(verdict.code, verdict.detail)

    def _account_balance(self):
        """The broker's balance, or None if it cannot be read.

        `None` is passed straight through to `plan_order`, which then simply skips the
        authorised-risk check rather than comparing against a fabricated zero — the same
        three-state rule as `mt5_link`. A zero here would refuse every order forever.
        """
        try:
            import MetaTrader5 as mt5
            info = mt5.account_info()
            return float(info.balance) if info else None
        except Exception:
            return None

    def _record_refusal(self, direction: int, plan, pend) -> None:
        """A refused order is loud once, then quiet — but never forgotten."""
        detail = f"[{plan.code}] {plan.detail}"
        self._refused[direction] = detail
        self._ledger.event("order_refused", dir=direction, code=plan.code, detail=plan.detail,
                           wanted_units=pend.qty, price=pend.edge, stop=pend.sl,
                           sos_bar=getattr(pend, "sos_bar", None))
        self._log.error(f"Order REFUSED ({self._side(direction)}): {detail}")
        if self._refusal_alerted.get(direction) == plan.code:
            return
        self._refusal_alerted[direction] = plan.code
        self._notify(alert(
            "⚠️", "ORDER REFUSED", self._mt5.bot_label,
            f"A {self._side(direction)} setup was ready and no order was placed.\n{plan.detail}",
            "No position was opened. The strategy will keep re-offering it while the setup "
            "lives, and this will not alert again for the same reason."),
            notify.HEALTH)

    def _place(self, direction: int, lots: float, pend, sig, plan=None) -> None:
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
                               sos_bar=getattr(pend, "sos_bar", None),
                               # The sizing WORKING is now part of the record, not just the
                               # sizing failing. `risk_ccy` is what this order really puts at
                               # risk in account currency — the number that was wrong by 221x
                               # and that no artefact anywhere would have revealed.
                               risk_ccy=getattr(plan, "risk_ccy", None),
                               intended_risk_ccy=getattr(plan, "intended_risk_ccy", None),
                               margin_ccy=getattr(plan, "margin_ccy", None),
                               units=pend.qty)
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
            # Re-record: the stop is the field that moves, and a record holding the previous
            # stop would be REFUSED at the next start because the broker's real one disagrees.
            self._save_position()

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

    def halt(self, reason: str) -> None:
        """Halt this bridge on an OUTSIDE authority's instruction — today, the fleet switch.

        A public seam rather than letting a caller reach into `_halt`, because the two have
        genuinely different causes and only one of them is a defect: `_halt` means *this bot's
        emulator and the broker disagree*, which is a fault to investigate, while this means
        *somebody, or something, told the whole fleet to stop*, which is a decision to honour.
        The EFFECT is identical on purpose — no further orders, open positions keep their
        broker stops — so there is exactly one state a reader has to reason about.
        """
        self._halt(reason)

    def _halt(self, reason: str) -> None:
        if self.state is BridgeState.HALTED:
            return
        self.state = BridgeState.HALTED
        self.halt_reason = reason
        self._log.error(f"HALTED: {reason}")
        self._ledger.event("halted", reason=reason)
        # HEALTH, not TRADE, and the call is worth defending: a halt is the bot refusing to place
        # orders, which is a fact about the machinery. It is also the single most consequential
        # message here — which is why it must not sit in a room that is only checked when a fill
        # arrives. `log_review.py` raises it AGAIN as a standing chip on the Bots page precisely
        # because one Telegram line, in any room, is not enough for this one.
        self._notify(alert(
            "⛔", "HALTED", self._mt5.bot_label,
            reason,
            "Anything open keeps its broker stop. Check the account, then restart it."),
            notify.HEALTH)

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

    def _symbol_attr(self, name: str, fallback):
        """One symbol property off the terminal, with a fallback that only applies when MT5 is
        not there to ask (tests, dry runs on a machine without it). Never hardcoded per symbol —
        `digits` and `point` differ by broker, and a wrong pip size makes every stop distance in
        every alert wrong in a way nobody would question."""
        try:
            import MetaTrader5 as mt5
            si = mt5.symbol_info(self._mt5.symbol)
            return getattr(si, name) if si else fallback
        except Exception:
            return fallback

    def _digits(self) -> int:
        return int(self._symbol_attr("digits", 2))

    def _point(self) -> float:
        return float(self._symbol_attr("point", 0.01))

    @staticmethod
    def _bar_time(sig):
        """The BAR's timestamp, not the wall clock — an alert should be stamped with when the
        trade happened. Falls back to None, which `alerts` reads as "now"."""
        from datetime import datetime, timezone
        ms = getattr(sig, "time_ms", None)
        return datetime.fromtimestamp(ms / 1000, tz=timezone.utc) if ms else None

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
