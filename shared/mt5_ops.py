"""
mt5_ops.py — Shared MT5 Operations

Single source of truth for all MT5 market operations used across bots.

FREE FUNCTIONS (stateless, no symbol/magic context):
    now_utc()                  — timezone-aware UTC datetime
    is_market_close()          — True during the 19:45-21:00 UTC close window
    should_close_for_weekend() — True on Friday in the market close window
    is_dead_zone()             — True during 3-7 PM Texas time
    get_atr(df, period)        — Average True Range calculation
    get_ema(df, period)        — Exponential moving average of close

CLASS BotMT5:
    Wraps symbol, magic, credentials, and logger into a single context object.
    One instance per bot. All MT5 operations are methods on this class.

    Connection:
        connect()               — Initialize MT5 terminal and login with retry + file lock

    Market data:
        get_candles(tf, count)  — Fetch OHLCV bars
        get_tick()              — Return (bid, ask)

    Order execution:
        place_order(dir, lots, sl, tp, comment)
        move_sl(ticket, new_sl, tp)
        partial_close(ticket, lots, direction)

    Position lifecycle:
        get_deal_result(ticket) — Fetch (close_price, pnl_usd) from deal history
        close_position(ticket, direction, reason)
        close_all_positions(reason)
        recover_open_positions()
        reconcile_on_startup(open_trades, logger, ai)

    Dead zone:
        handle_dead_zone(open_trades, atr, logger, ai)

    Sizing:
        lot_size(balance, sl_dist, risk_pct, risk_mult)

Usage in a bot:
    from mt5_ops import BotMT5, now_utc, is_market_close, should_close_for_weekend
    from mt5_ops import is_dead_zone, get_atr, get_ema

    _mt5 = BotMT5(SYMBOL, MAGIC, "BOT_SCALPER", _CFG, ACCOUNT, log)

    def connect():              return _mt5.connect()
    def get_candles(tf, n):     return _mt5.get_candles(tf, n)
    def get_tick():             return _mt5.get_tick()
    # ... etc.
"""

import time
from datetime import datetime, timezone, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

import MetaTrader5 as mt5
import pandas as pd

_LOCK_FILE    = Path(r"C:\algos\mt5_connect.lock")
_LOCK_TIMEOUT = 90   # seconds to wait for the file lock
_LOCK_TTL     = 45   # seconds after which a stale lock is removed
_TEXAS        = ZoneInfo("America/Chicago")


# =============================================================================
# FREE FUNCTIONS — stateless, no symbol/magic context required
# =============================================================================

def now_utc() -> datetime:
    """Current UTC time, timezone-aware."""
    return datetime.now(timezone.utc)


def is_market_close() -> bool:
    """True during the gold daily close window: 19:45–21:00 UTC."""
    t = now_utc()
    return (t.hour == 19 and t.minute >= 45) or t.hour == 20


def should_close_for_weekend() -> bool:
    """True on Friday during the market close window — no reopen until Sunday 22:00 UTC."""
    return now_utc().weekday() == 4 and is_market_close()


def is_dead_zone() -> bool:
    """
    True during 3:00 PM–7:00 PM Texas time — no new entries allowed.
    Uses America/Chicago so DST is handled automatically.
    """
    try:
        return 15 <= now_utc().astimezone(_TEXAS).hour < 19
    except Exception:
        t = now_utc()
        return 20 <= t.hour < 24 or t.hour == 0


def get_atr(df: pd.DataFrame, period: int = 14) -> float:
    """Average True Range over the given candle period."""
    h, l, c = df["high"], df["low"], df["close"].shift(1)
    tr = pd.concat([h - l, (h - c).abs(), (l - c).abs()], axis=1).max(axis=1)
    return float(tr.rolling(period).mean().iloc[-1])


def get_ema(df: pd.DataFrame, period: int) -> float:
    """Exponential moving average of close, last value only."""
    return float(df["close"].ewm(span=period, adjust=False).mean().iloc[-1])


# =============================================================================
# BotMT5 — per-bot MT5 context and operations
# =============================================================================

class BotMT5:
    """
    MT5 context for a single bot instance.

    Encapsulates the symbol, magic number, credentials, and logger so that
    all MT5 operations can be called without passing those values every time.
    Create one instance per bot after loading config; pass it into run().

    bot_label (e.g. "BOT_SCALPER") appears in MT5 order comments and log
    messages so positions can be identified in the broker terminal.
    """

    def __init__(self, symbol: str, magic: int, bot_label: str,
                 config: dict, account: dict, log):
        self.symbol    = symbol
        self.magic     = magic
        self.bot_label = bot_label
        self._cfg      = config
        self._account  = account
        self.log       = log

    # ── Connection ────────────────────────────────────────────────────────────

    def connect(self) -> bool:
        """
        Initialize MT5 terminal and login. Retries up to 5 times with an
        8-second pause between attempts. Uses a file lock so concurrent bot
        startups don't race against the same terminal.

        CRITICAL: never falls back to no-path initialize when mt5_path is set.
        Falling back connects to ANY open terminal — MT5 remembers all logins,
        so the wrong account could be used.
        """
        log = self.log

        def _acquire_lock(bot_id: str) -> bool:
            waited = 0
            while waited < _LOCK_TIMEOUT:
                if _LOCK_FILE.exists():
                    try:
                        age    = time.time() - _LOCK_FILE.stat().st_mtime
                        holder = _LOCK_FILE.read_text().strip()
                        if age > _LOCK_TTL:
                            log.warning(f"Stale lock ({age:.0f}s, held by {holder}) — removing")
                            _LOCK_FILE.unlink(missing_ok=True)
                        else:
                            log.info(f"Waiting for MT5 lock (held by {holder}, {age:.0f}s)...")
                            time.sleep(3)
                            waited += 3
                            continue
                    except Exception:
                        pass
                try:
                    _LOCK_FILE.write_text(bot_id)
                    time.sleep(0.5)
                    if _LOCK_FILE.exists() and _LOCK_FILE.read_text().strip() == bot_id:
                        return True
                except Exception as e:
                    log.warning(f"Lock write error: {e}")
                time.sleep(1)
                waited += 1
            log.error(f"Could not acquire MT5 lock after {_LOCK_TIMEOUT}s")
            return False

        startup_delay = self._cfg.get("startup_delay", 0)
        if startup_delay > 0:
            log.info(f"Startup delay {startup_delay}s")
            time.sleep(startup_delay)

        mt5_path    = self._cfg.get("mt5_path", "")
        expected_id = self._account.get("login")
        bot_id      = f"{self.bot_label}_{expected_id}"

        if not _acquire_lock(bot_id):
            return False

        try:
            for attempt in range(1, 6):
                if attempt > 1:
                    log.info(f"Connect attempt {attempt}/5 — waiting 8s...")
                    time.sleep(8)
                    try:
                        mt5.shutdown()
                    except Exception:
                        pass

                if mt5_path:
                    if not mt5.initialize(path=mt5_path):
                        err = mt5.last_error()
                        if err[0] == -10005:
                            log.info(f"IPC timeout (attempt {attempt}) — terminal running, retrying")
                        else:
                            log.warning(f"MT5 init failed (attempt {attempt}): {err}")
                        continue
                else:
                    if not mt5.initialize():
                        log.warning(f"MT5 init failed (attempt {attempt}): {mt5.last_error()}")
                        continue

                if not mt5.login(self._account["login"],
                                 password=self._account["password"],
                                 server=self._account["server"]):
                    log.warning(f"Login failed (attempt {attempt}): {mt5.last_error()}")
                    mt5.shutdown()
                    continue

                info = mt5.account_info()
                if not info:
                    log.warning(f"No account info (attempt {attempt})")
                    mt5.shutdown()
                    continue

                if info.login != expected_id:
                    log.error(
                        f"ACCOUNT MISMATCH (attempt {attempt}): "
                        f"got #{info.login} expected #{expected_id} — retrying"
                    )
                    mt5.shutdown()
                    continue

                log.info(f"Connected | #{info.login} | ${info.balance:,.2f} | {info.server}")
                return True

            log.error(f"Failed to connect to #{expected_id} after 5 attempts. Path: {mt5_path}")
            return False

        finally:
            try:
                _LOCK_FILE.unlink(missing_ok=True)
            except Exception:
                pass
            log.info("MT5 connection lock released")

    # ── Market data ───────────────────────────────────────────────────────────

    def get_candles(self, tf: int, count: int) -> pd.DataFrame:
        """Fetch OHLCV bars from MT5. Returns empty DataFrame on failure."""
        rates = mt5.copy_rates_from_pos(self.symbol, tf, 0, count)
        if rates is None or len(rates) == 0:
            return pd.DataFrame()
        df = pd.DataFrame(rates)
        df["time"] = pd.to_datetime(df["time"], unit="s", utc=True)
        return df

    def get_tick(self) -> tuple[float, float]:
        """Return (bid, ask) for the symbol. Returns (0.0, 0.0) on failure."""
        tick = mt5.symbol_info_tick(self.symbol)
        return (tick.bid, tick.ask) if tick else (0.0, 0.0)

    # ── Order execution ───────────────────────────────────────────────────────

    def place_order(self, direction: str, lots: float, sl: float, tp: float,
                    comment: str = "") -> tuple:
        """
        Send a market order.

        direction: 'bullish' or 'bearish'
        comment: optional override for the MT5 order comment field
        Returns (ticket, filled_price) or (None, None) on failure.
        """
        bid, ask   = self.get_tick()
        order_type = mt5.ORDER_TYPE_BUY if direction == "bullish" else mt5.ORDER_TYPE_SELL
        price      = ask if direction == "bullish" else bid
        result = mt5.order_send({
            "action":       mt5.TRADE_ACTION_DEAL,
            "symbol":       self.symbol,
            "volume":       lots,
            "type":         order_type,
            "price":        price,
            "sl":           round(sl, 2),
            "tp":           round(tp, 2),
            "deviation":    20,
            "magic":        self.magic,
            "comment":      comment or f"{self.bot_label}-ENTRY",
            "type_time":    mt5.ORDER_TIME_GTC,
            "type_filling": mt5.ORDER_FILLING_IOC,
        })
        if result and result.retcode == mt5.TRADE_RETCODE_DONE:
            self.log.info(
                f"ORDER FILLED | ticket={result.order} | "
                f"{direction} {lots}L @ {result.price:.2f} | SL={sl:.2f} TP={tp:.2f}"
            )
            return result.order, result.price
        self.log.error(f"Order failed: {mt5.last_error()}")
        return None, None

    def move_sl(self, ticket: int, new_sl: float, tp: float = None) -> bool:
        """
        Modify the stop loss on an open position.

        Preserves the existing TP unless tp is explicitly provided.
        Returns True if MT5 accepted the modification.
        """
        pos = mt5.positions_get(ticket=ticket)
        if not pos:
            return False
        result = mt5.order_send({
            "action":   mt5.TRADE_ACTION_SLTP,
            "symbol":   self.symbol,
            "position": ticket,
            "sl":       round(new_sl, 2),
            "tp":       tp if tp is not None else pos[0].tp,
        })
        return result is not None and result.retcode == mt5.TRADE_RETCODE_DONE

    def partial_close(self, ticket: int, close_lots: float, direction: str) -> bool:
        """
        Close a portion of an open position to bank partial profit.

        close_lots is rounded to the symbol's volume step and clamped to the
        position's current volume.
        Returns True if MT5 accepted the order.
        """
        pos = mt5.positions_get(ticket=ticket)
        if not pos:
            return False
        si = mt5.symbol_info(self.symbol)
        if not si:
            return False
        bid, ask   = self.get_tick()
        price      = bid if direction == "bullish" else ask
        close_type = mt5.ORDER_TYPE_SELL if direction == "bullish" else mt5.ORDER_TYPE_BUY
        close_lots = round(round(close_lots / si.volume_step) * si.volume_step, 2)
        close_lots = max(si.volume_min, min(close_lots, pos[0].volume))
        result = mt5.order_send({
            "action":       mt5.TRADE_ACTION_DEAL,
            "symbol":       self.symbol,
            "volume":       close_lots,
            "type":         close_type,
            "position":     ticket,
            "price":        price,
            "deviation":    20,
            "magic":        self.magic,
            "comment":      f"{self.bot_label}-PARTIAL",
            "type_time":    mt5.ORDER_TIME_GTC,
            "type_filling": mt5.ORDER_FILLING_IOC,
        })
        if result and result.retcode == mt5.TRADE_RETCODE_DONE:
            self.log.info(f"PARTIAL CLOSE | T{ticket} | {close_lots}L @ {price:.2f}")
            return True
        self.log.error(f"Partial close failed T{ticket}: {mt5.last_error()}")
        return False

    # ── Position lifecycle ────────────────────────────────────────────────────

    def get_deal_result(self, ticket: int) -> tuple[float, float]:
        """
        Fetch (close_price, pnl_usd) from MT5 deal history for a closed position.

        Uses a 7-day lookback window so deals from over the weekend are found.
        Returns (0.0, 0.0) if no closing deal is found.
        """
        to    = datetime.utcnow()
        from_ = to - timedelta(days=7)
        deals = mt5.history_deals_get(from_, to, position=ticket)
        if deals:
            closing = [d for d in deals if d.entry == 1]  # DEAL_ENTRY_OUT
            if closing:
                d = closing[-1]
                return float(d.price), float(d.profit)
        return 0.0, 0.0

    def close_position(self, ticket: int, direction: str,
                       reason: str = "") -> tuple[bool, float, float]:
        """
        Close an open position at market price.

        Waits 0.3s after the order executes then fetches the actual realised P&L
        from MT5 deal history. Falls back to the pre-close floating P&L only if
        deal history is not yet available.

        Returns (success, close_price, pnl_usd).
        """
        pos = mt5.positions_get(ticket=ticket)
        if not pos:
            return False, 0.0, 0.0
        p          = pos[0]
        bid, ask   = self.get_tick()
        close_type = mt5.ORDER_TYPE_SELL if direction == "bullish" else mt5.ORDER_TYPE_BUY
        price      = bid if direction == "bullish" else ask
        result = mt5.order_send({
            "action":       mt5.TRADE_ACTION_DEAL,
            "symbol":       self.symbol,
            "volume":       p.volume,
            "type":         close_type,
            "position":     ticket,
            "price":        price,
            "deviation":    20,
            "magic":        self.magic,
            "comment":      f"{self.bot_label}-CLOSE-{reason}",
            "type_time":    mt5.ORDER_TIME_GTC,
            "type_filling": mt5.ORDER_FILLING_IOC,
        })
        if result and result.retcode == mt5.TRADE_RETCODE_DONE:
            self.log.info(f"CLOSED T{ticket} | reason={reason} @ {price:.2f}")
            time.sleep(0.3)
            cp, pnl = self.get_deal_result(ticket)
            if cp == 0.0:
                cp, pnl = price, p.profit  # fallback: pre-close floating value
            return True, cp, pnl
        return False, 0.0, 0.0

    def close_all_positions(self, reason: str = "") -> None:
        """
        Force-close all open positions belonging to this bot (filtered by magic number).

        Uses raw MT5 order_send (not close_position) for speed — this is called
        during emergency stops and weekly caps where latency matters.
        """
        positions = mt5.positions_get(symbol=self.symbol)
        if not positions:
            return
        own = [p for p in positions if p.magic == self.magic]
        if not own:
            return
        self.log.warning(f"CLOSE ALL — {reason} | {len(own)} position(s)")
        for p in own:
            bid, ask   = self.get_tick()
            price      = bid if p.type == mt5.ORDER_TYPE_BUY else ask
            close_type = mt5.ORDER_TYPE_SELL if p.type == mt5.ORDER_TYPE_BUY else mt5.ORDER_TYPE_BUY
            result = mt5.order_send({
                "action":       mt5.TRADE_ACTION_DEAL,
                "symbol":       self.symbol,
                "volume":       p.volume,
                "type":         close_type,
                "position":     p.ticket,
                "price":        price,
                "deviation":    30,
                "magic":        self.magic,
                "comment":      f"{self.bot_label}-{reason}",
                "type_time":    mt5.ORDER_TIME_GTC,
                "type_filling": mt5.ORDER_FILLING_IOC,
            })
            if result and result.retcode == mt5.TRADE_RETCODE_DONE:
                self.log.warning(f"  Closed T{p.ticket} @ {price:.2f}")
            else:
                self.log.error(f"  Failed T{p.ticket}: {mt5.last_error()}")

    def lot_size(self, balance: float, sl_dist: float, risk_pct: float,
                 risk_mult: float = 1.0) -> float:
        """
        Calculate MT5 lot size for the given risk parameters.

        risk_pct: percentage of balance to risk (e.g. 1.0 for 1%)
        risk_mult: multiplier applied to sl_dist (e.g. for news stop widening)
        Rounds to the symbol's volume step and clamps to min/max lot.
        """
        si = mt5.symbol_info(self.symbol)
        if not si or si.trade_tick_size == 0 or sl_dist == 0:
            return si.volume_min if si else 0.01
        actual_sl = sl_dist * risk_mult
        risk      = balance * (risk_pct / 100)
        ticks     = actual_sl / si.trade_tick_size
        lots      = risk / (ticks * si.trade_tick_value)
        lots      = max(si.volume_min, min(si.volume_max, lots))
        lots      = round(round(lots / si.volume_step) * si.volume_step, 2)
        self.log.info(
            f"Lot size: {lots}L | risk={risk_pct}% (${risk:.2f}) | "
            f"balance=${balance:,.0f} | sl={actual_sl:.2f}pts"
        )
        return lots

    def recover_open_positions(self) -> list:
        """
        On bot restart, scan MT5 for positions opened by this bot (by magic number)
        and rebuild a minimal open_trades list so position management resumes.

        Returns list of dicts with keys: ticket, entry, sl, dir, lots.
        Bot-specific fields (tp, be_done, etc.) should be set by the caller.
        """
        positions = mt5.positions_get(symbol=self.symbol)
        if not positions:
            return []
        recovered = []
        for p in positions:
            if p.magic != self.magic:
                continue
            direction = "bullish" if p.type == mt5.ORDER_TYPE_BUY else "bearish"
            recovered.append({
                "ticket": p.ticket,
                "entry":  p.price_open,
                "sl":     p.sl,
                "dir":    direction,
                "lots":   p.volume,
            })
            self.log.info(
                f"RECOVERED T{p.ticket} | {direction} {p.volume}L @ {p.price_open:.2f} "
                f"| P&L=${p.profit:.2f} | SL={p.sl:.2f}"
            )
        if recovered:
            self.log.info(f"Position recovery complete — {len(recovered)} trade(s).")
        else:
            self.log.info("Position recovery — no open positions found.")
        return recovered

    def reconcile_on_startup(self, open_trades: list, logger, ai) -> None:
        """
        Ground-truth reconciliation after any restart or VPS reboot.

        Missed close (in trades.json as open, gone from MT5):
            Bot was down when the trade closed. Fetches actual P&L from deal history.
            If deal history unavailable, marks the trade orphaned so it is excluded
            from all P&L calculations.

        Phantom position (in MT5, not in trades.json):
            trades.json was wiped. Creates a stub entry so the position is managed.
        """
        pending = {t["ticket"] for t in logger.trades if t.get("outcome") is None}
        live    = {t["ticket"] for t in open_trades}

        missed = pending - live
        if missed:
            self.log.info(f"RECONCILE: {len(missed)} position(s) closed while bot was down.")
        for ticket in missed:
            cp, pnl = self.get_deal_result(ticket)
            if cp:
                logger.log_close(ticket, cp, pnl)
                ai.on_trade_closed(ticket, cp, pnl)
                self.log.info(f"RECONCILE: Logged missed close | T{ticket} | pnl=${pnl:+.2f}")
            else:
                logger.mark_orphaned(ticket)
                self.log.warning(f"RECONCILE: No deal history T{ticket} — marked orphaned")

        phantom = live - pending
        if phantom:
            self.log.info(f"RECONCILE: {len(phantom)} position(s) have no trades.json entry.")
        for t in open_trades:
            if t["ticket"] in phantom:
                logger.log_entry(
                    ticket    = t["ticket"],
                    features  = {},
                    direction = t["dir"],
                    entry     = t["entry"],
                    sl        = t["sl"],
                    tp1       = t.get("tp", 0.0),
                    tp2       = 0.0,
                    is_reentry= True,
                    risk_usd  = 0.0,
                )
                self.log.warning(
                    f"RECONCILE: Stub entry created | T{t['ticket']} | "
                    f"{t['dir']} @ {t['entry']:.2f}"
                )

    # ── Dead zone management ──────────────────────────────────────────────────

    def handle_dead_zone(self, open_trades: list, atr: float, logger, ai) -> None:
        """
        Portfolio-level trade management during 3:00 PM–7:00 PM Texas time.

        1. Net profitable → close ALL positions immediately (lock in combined profit).
        2. Net negative per-trade:
           a. Trade worsening → close immediately (stop the bleeding).
           b. Trade improving or at BE → hold and monitor.
           c. 3:45 PM TX hard cut → close all remaining regardless.
        3. Individually profitable trades → move to breakeven.
        """
        try:
            now_tx   = now_utc().astimezone(_TEXAS)
            hard_cut = now_tx.hour > 15 or (now_tx.hour == 15 and now_tx.minute >= 45)
        except Exception:
            hard_cut = False

        if not open_trades:
            return

        live_trades, total_pnl = [], 0.0
        for t in open_trades[:]:
            pos = mt5.positions_get(ticket=t["ticket"])
            if not pos:
                cp, pnl = self.get_deal_result(t["ticket"])
                if cp:
                    logger.log_close(t["ticket"], cp, pnl)
                    ai.on_trade_closed(t["ticket"], cp, pnl)
                open_trades.remove(t)
                continue
            p = pos[0]
            total_pnl += p.profit
            live_trades.append((t, p))

        if not live_trades:
            return

        if total_pnl > 0:
            self.log.info(
                f"DEAD ZONE PORTFOLIO CLOSE | Net P&L=+${total_pnl:.2f} | "
                f"Closing {len(live_trades)} position(s) — locking profit."
            )
            for t, _ in live_trades:
                ok, cp, pnl = self.close_position(t["ticket"], t["dir"], "dead-zone-net-profit")
                if ok:
                    logger.log_close(t["ticket"], cp, pnl)
                    ai.on_trade_closed(t["ticket"], cp, pnl)
                if t in open_trades:
                    open_trades.remove(t)
            return

        for t, p in live_trades:
            sl_dist   = abs(t["entry"] - t["sl"])
            direction = t["dir"]
            if sl_dist == 0:
                continue

            profit_r = (
                (p.price_current - t["entry"]) / sl_dist if direction == "bullish"
                else (t["entry"] - p.price_current) / sl_dist
            )

            if profit_r > 0:
                if not t.get("be_done"):
                    if self.move_sl(t["ticket"], t["entry"]):
                        t["be_done"] = True
                        t["sl"]      = t["entry"]
                        self.log.info(
                            f"DEAD ZONE BE | T{t['ticket']} -> breakeven @ {t['entry']:.2f}"
                        )
            else:
                prev_r    = t.get("_dz_prev_r", profit_r)
                worsening = profit_r < prev_r
                t["_dz_prev_r"] = profit_r

                if hard_cut:
                    self.log.warning(
                        f"DEAD ZONE 3:45 CUT | T{t['ticket']} | "
                        f"P&L={profit_r:.2f}R | closing now."
                    )
                    ok, cp, pnl = self.close_position(
                        t["ticket"], direction, "dead-zone-3:45-cut"
                    )
                    if ok:
                        logger.log_close(t["ticket"], cp, pnl)
                        ai.on_trade_closed(t["ticket"], cp, pnl)
                    if t in open_trades:
                        open_trades.remove(t)

                elif worsening:
                    self.log.warning(
                        f"DEAD ZONE WORSENING | T{t['ticket']} | "
                        f"P&L={profit_r:.2f}R | closing to limit loss."
                    )
                    ok, cp, pnl = self.close_position(
                        t["ticket"], direction, "dead-zone-worsening"
                    )
                    if ok:
                        logger.log_close(t["ticket"], cp, pnl)
                        ai.on_trade_closed(t["ticket"], cp, pnl)
                    if t in open_trades:
                        open_trades.remove(t)

                else:
                    self.log.info(
                        f"DEAD ZONE MONITOR | T{t['ticket']} | "
                        f"P&L={profit_r:.2f}R improving | Portfolio=${total_pnl:.2f}"
                    )
