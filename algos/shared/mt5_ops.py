"""
mt5_ops.py — Shared MT5 Operations

Single source of truth for all MT5 market operations used across bots.

FREE FUNCTIONS (stateless, no symbol/magic context):
    now_utc()                  — timezone-aware UTC datetime
    is_market_close()          — True during the 19:45-21:00 UTC close window
    should_close_for_weekend() — True on Friday in the market close window
    is_dead_zone(start_hour, end_hour) — True during configured CT window (default 16–17)
    get_atr(df, period)        — Average True Range calculation
    get_ema(df, period)        — Exponential moving average of close
    get_rsi(df, period)        — Wilder RSI, last value

CLASS BotMT5:
    Wraps symbol, magic, credentials, and logger into a single context object.
    One instance per bot. All MT5 operations are methods on this class.

    Connection:
        connect()               — Initialize MT5 terminal and login with retry + file lock

    Market data:
        get_candles(tf, count)  — Fetch OHLCV bars, timestamped in TRUE UTC (see the method:
                                  MT5 returns BROKER-server time and labelling it UTC shifts
                                  every session boundary the time-driven engines depend on)
        get_tick()              — Return (bid, ask)

    Order execution — market:
        place_order(dir, lots, sl, tp, comment)
        move_sl(ticket, new_sl, tp)
        partial_close(ticket, lots, direction)

    Order execution — pending / resting limits (the MPC strategies enter this way):
        place_pending_limit(dir, lots, price, sl, tp, comment)
        modify_pending(ticket, price, sl, tp)   — price/SL/TP only, NEVER volume
        cancel_pending(ticket) / cancel_all_pending()
        get_pending_orders() / get_open_positions()  — both filtered by this bot's MAGIC
        min_stop_distance() / normalize_volume(lots)

    Position lifecycle:
        get_deal_result(ticket) — Fetch (close_price, pnl_usd) from deal history
        close_position(ticket, direction, reason)
        close_all_positions(reason)
        recover_open_positions()
        reconcile_on_startup(open_trades, logger, ai)
        disconnect()            — mt5.shutdown() + log

    Dead zone:
        handle_dead_zone(open_trades, atr, logger, ai)

    Sizing:
        lot_size(balance, sl_dist, risk_pct, risk_mult)

    State:
        write_live_state(state_key, weekly_start, daily_start)
            — Fetch acct.balance, guard zero, write balance+last_write to bot_state.
              Call before any early-continue so P&L tracker stays in LIVE mode.

Usage in a bot:
    from mt5_ops import BotMT5, now_utc, is_market_close, should_close_for_weekend
    from mt5_ops import is_dead_zone, get_atr, get_ema

    _mt5 = BotMT5(SYMBOL, MAGIC, "BOT_EXAMPLE", _CFG, ACCOUNT, log)

    def connect():              return _mt5.connect()
    def get_candles(tf, n):     return _mt5.get_candles(tf, n)
    def get_tick():             return _mt5.get_tick()
    # ... etc.
"""

import sys
import time
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Optional
from zoneinfo import ZoneInfo

import MetaTrader5 as mt5
import pandas as pd

from bot_state import write_bot

# The broker-server-clock → true-UTC rule. It lives under markets/fx/tools/ because the MT5 lab
# agent (which is not on shared/'s path) was its first consumer; imported here by the repo-wide
# "put the dir on sys.path, import bare" convention rather than copied, because a second copy of
# a DST rule is a second thing to get wrong. See get_candles() for what it fixes.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "markets" / "fx" / "tools"))
import broker_clock as _broker_clock  # noqa: E402

_LOCK_FILE    = Path(r"C:\trading\algos\mt5_connect.lock")
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


def is_dead_zone(start_hour: int = 16, end_hour: int = 17) -> bool:
    """
    True during the configured dead zone window (Texas/CT local time).

    start_hour / end_hour are CT local hours (0–23). America/Chicago is used
    so DST transitions (CST↔CDT) are handled automatically — callers just
    supply the local clock hours they see in Texas with no UTC math needed.

    Gold market daily close is 16:00–17:00 CT (4–5 PM).
    Configure via config.json: dead_zone.start_ct / dead_zone.end_ct.
    """
    try:
        return start_hour <= now_utc().astimezone(_TEXAS).hour < end_hour
    except Exception:
        t = now_utc()
        return 21 <= t.hour < 22


def get_atr(df: pd.DataFrame, period: int = 14) -> float:
    """Average True Range over the given candle period."""
    h, l, c = df["high"], df["low"], df["close"].shift(1)
    tr = pd.concat([h - l, (h - c).abs(), (l - c).abs()], axis=1).max(axis=1)
    return float(tr.rolling(period).mean().iloc[-1])


def get_ema(df: pd.DataFrame, period: int) -> float:
    """Exponential moving average of close, last value only."""
    return float(df["close"].ewm(span=period, adjust=False).mean().iloc[-1])


def get_rsi(df: pd.DataFrame, period: int = 14) -> float:
    """Wilder RSI, last value only."""
    delta = df["close"].diff()
    gain  = delta.clip(lower=0).rolling(period).mean()
    loss  = (-delta.clip(upper=0)).rolling(period).mean()
    return float((100 - (100 / (1 + gain / (loss + 1e-9)))).iloc[-1])


# =============================================================================
# BotMT5 — per-bot MT5 context and operations
# =============================================================================

class BotMT5:
    """
    MT5 context for a single bot instance.

    Encapsulates the symbol, magic number, credentials, and logger so that
    all MT5 operations can be called without passing those values every time.
    Create one instance per bot after loading config; pass it into run().

    bot_label (e.g. "BOT_EXAMPLE") appears in MT5 order comments and log
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

    def get_candles(self, tf: int, count: int,
                    symbol: str = None) -> pd.DataFrame:
        """Fetch OHLCV bars from MT5, timestamped in TRUE UTC.

        **The bug this signature hides, and why the conversion is not optional.** MT5's `time`
        field is an epoch-looking integer that actually carries the BROKER SERVER's local wall
        clock. The old implementation did `pd.to_datetime(..., unit="s", utc=True)`, which
        labels that local time as UTC — every bar 2-3 hours off, with nothing downstream able
        to notice because the result is a perfectly valid-looking UTC timestamp. That is the
        exact defect `broker_clock.py` was written for after `compare_feeds.py` found it on the
        lab agent in 2026-07-15.

        It matters more here than anywhere else: the sessions, liquidity, VWAP and SVP engines
        are TIME-DRIVEN, and they are precisely the engines the A+ strategy trades off. A
        three-hour shift moves every session boundary and every daily level, so the live bot
        would take different trades from the backtest while both looked healthy.

        The offset rule is MEASURED, not assumed (see `broker_clock.py`'s docstring — an
        earlier EU-rule version passed its own unit tests and was still wrong). Re-measure with
        `backtest/tools/compare_feeds.py` whenever the broker or terminal changes; override with
        the `BROKER_TZ_OFFSETS` env var if the offsets (not the rule) differ.

        Returns an empty DataFrame on failure, never None.
        """
        sym   = symbol or self.symbol
        rates = mt5.copy_rates_from_pos(sym, tf, 0, count)
        if rates is None or len(rates) == 0:
            return pd.DataFrame()
        df = pd.DataFrame(rates)
        df["time"] = pd.to_datetime(
            [_broker_clock.to_utc(_broker_clock.broker_naive_from_epoch(t)) for t in df["time"]],
            utc=True,
        )
        return df

    def get_tick(self, symbol: str = None) -> tuple[float, float]:
        """Return (bid, ask) for the symbol. Returns (0.0, 0.0) on failure."""
        sym  = symbol or self.symbol
        tick = mt5.symbol_info_tick(sym)
        return (tick.bid, tick.ask) if tick else (0.0, 0.0)

    # ── Order execution ───────────────────────────────────────────────────────

    def place_order(self, direction: str, lots: float, sl: float, tp: float,
                    comment: str = "", symbol: str = None) -> tuple:
        """
        Send a market order.

        direction: 'bullish' or 'bearish'
        symbol:  override the instance symbol (for multi-instrument scanning)
        comment: optional override for the MT5 order comment field
        Returns (ticket, filled_price) or (None, None) on failure.
        """
        sym        = symbol or self.symbol
        si         = mt5.symbol_info(sym)
        digits     = si.digits if si else 2
        bid, ask   = self.get_tick(sym)
        order_type = mt5.ORDER_TYPE_BUY if direction == "bullish" else mt5.ORDER_TYPE_SELL
        price      = ask if direction == "bullish" else bid

        # Broker minimum stop-distance guard
        if si and si.trade_stops_level > 0:
            min_dist = si.trade_stops_level * si.point
            if abs(price - sl) < min_dist:
                self.log.warning(
                    f"SL too close: |{price:.{digits}f} - {sl:.{digits}f}| = "
                    f"{abs(price-sl):.{digits}f} < stops_level {min_dist:.{digits}f} ({sym}). Skip."
                )
                return None, None

        result = mt5.order_send({
            "action":       mt5.TRADE_ACTION_DEAL,
            "symbol":       sym,
            "volume":       lots,
            "type":         order_type,
            "price":        price,
            "sl":           round(sl, digits),
            "tp":           round(tp, digits),
            "deviation":    20,
            "magic":        self.magic,
            "comment":      comment or f"{self.bot_label}-ENTRY",
            "type_time":    mt5.ORDER_TIME_GTC,
            "type_filling": mt5.ORDER_FILLING_IOC,
        })
        if result and result.retcode == mt5.TRADE_RETCODE_DONE:
            self.log.info(
                f"ORDER FILLED | ticket={result.order} | "
                f"{direction} {lots}L @ {result.price:.{digits}f} | "
                f"SL={sl:.{digits}f} TP={tp:.{digits}f}"
            )
            return result.order, result.price
        self.log.error(f"Order failed: {mt5.last_error()}")
        return None, None

    # ── Pending (resting limit) orders ────────────────────────────────────────
    #
    # Added 2026-07-30 for the live runner. `place_order` above sends a MARKET order, which is
    # all the first bot suite ever needed — but the MPC strategies enter on a RESTING LIMIT at a
    # fib/FVG edge, and a market order at signal time is a different trade entirely (it pays the
    # spread at the wrong price and fills where the strategy never wanted to be).
    #
    # Three constraints MT5 imposes that a caller must know about, because each one turns into a
    # silently-missing trade rather than an exception:
    #
    #  1. **`TRADE_ACTION_MODIFY` cannot change VOLUME.** It moves price/SL/TP only. The A+ bot
    #     re-sizes every bar (qty = equity·risk% / stop distance, and equity moves), so a size
    #     change means CANCEL + RE-PLACE, which is what `algos/live/bridge.py` does. Never
    #     "fix" a volume drift with a modify — MT5 accepts the call and ignores the volume.
    #  2. **`SYMBOL_TRADE_STOPS_LEVEL` applies twice** — the pending price must sit at least that
    #     far from the CURRENT market, and the SL/TP must sit at least that far from the pending
    #     price. Both are checked here and refused with a log line naming the number, because
    #     MT5's own rejection reaches you as a bare retcode.
    #  3. **Volume must land on `volume_step`** and inside `[volume_min, volume_max]`. A strategy
    #     computing 0.4237 lots gets 0.42; one computing 0.004 gets refused rather than silently
    #     rounded up to the minimum, which would be a bigger position than the risk allowed.

    def min_stop_distance(self, symbol: str = None) -> float:
        """The broker's minimum distance (in PRICE) between an order and its stop/limit.

        This is the BROKER's floor and is unrelated to the strategy's own minimum-stop setting
        (`exec_min_stop_mode`): that one refuses a setup because the position would be
        oversized; this one refuses an order because the venue will not accept it. Both can
        fire, for different reasons, and the log must say which.
        """
        si = mt5.symbol_info(symbol or self.symbol)
        if not si or si.trade_stops_level <= 0:
            return 0.0
        return si.trade_stops_level * si.point

    # ── what one lot of this symbol IS (added 2026-08-07) ─────────────────────
    #
    # Read together with `algos/shared/order_sizing.py`, which is the reason these exist. Before
    # that date nothing in the live path ever asked the broker what a lot was worth: the bridge
    # took the strategy's quantity — in OUNCES — and sent it as LOTS. Every order was 100x.
    #
    # These three are deliberately thin and deliberately honest. They return `None` rather than a
    # guess, because every fallback available here is a number that would size a real position.

    def symbol_spec(self, symbol: str = None):
        """The broker's facts about one symbol, as an `order_sizing.SymbolSpec`.

        Returns `None` when the terminal cannot answer — a wrong suffix, a symbol not in Market
        Watch, or a terminal still loading all produce that, and each one has to REFUSE the
        order rather than fall back to a plausible-looking gold-shaped default.

        ⚠ **It returns the same dataclass the tests' fake returns.** That is deliberate: this
        repo has already been bitten by a test fixture that was MORE COMPLETE than production
        (`tests/test_secondary.py`, 2026-08-06 — the fake 1m bar carried two fields the real one
        did not, so every test exercised a shape the code never produced). Sharing the type
        makes that impossible here: a field the fake supplies is a field this method must supply.
        """
        from order_sizing import SymbolSpec

        sym = symbol or self.symbol
        si = mt5.symbol_info(sym)
        if not si:
            self.log.error(f"No symbol info for {sym} — cannot size an order for it.")
            return None
        return SymbolSpec(
            symbol=sym,
            contract_size=float(si.trade_contract_size),
            tick_size=float(si.trade_tick_size or si.point),
            # ⚠ `trade_tick_value` is in the ACCOUNT's currency, which is the whole reason this
            # generalises past gold. Do not substitute `point` arithmetic here: on a JPY-quoted
            # pair, price units and account dollars are not the same thing and the difference is
            # a factor of ~150.
            tick_value=float(si.trade_tick_value),
            volume_min=float(si.volume_min),
            volume_max=float(si.volume_max),
            volume_step=float(si.volume_step),
            digits=int(si.digits),
        )

    def margin_for(self, direction: str, lots: float, price: float,
                   symbol: str = None) -> Optional[float]:
        """Margin the broker would require for this order, in the account's currency.

        `None` = the terminal declined to compute it. The caller must treat that as a REFUSAL,
        never as "affordable" — this is the `mt5_link` three-state rule applied to money.
        """
        sym = symbol or self.symbol
        order_type = (mt5.ORDER_TYPE_BUY if direction == "bullish" else mt5.ORDER_TYPE_SELL)
        try:
            m = mt5.order_calc_margin(order_type, sym, float(lots), float(price))
        except Exception as e:
            self.log.error(f"order_calc_margin failed for {sym} {lots}L @ {price}: {e}")
            return None
        if m is None:
            self.log.error(f"order_calc_margin returned None for {sym} {lots}L @ {price}: "
                           f"{mt5.last_error()}")
            return None
        return float(m)

    def free_margin(self) -> Optional[float]:
        """The account's free margin, or `None` if the terminal cannot be asked.

        Free margin rather than balance or equity on purpose: it is the number the broker
        actually checks when it activates a pending order, and it is already net of whatever
        else this account is carrying.
        """
        info = mt5.account_info()
        return float(info.margin_free) if info else None

    def normalize_volume(self, lots: float, symbol: str = None) -> float:
        """Round `lots` DOWN to the symbol's volume step and clamp to its max.

        Rounds DOWN, never to nearest: rounding up crosses the risk the strategy sized for, and
        this function is called on every entry. Returns 0.0 when the result is below
        `volume_min` — the caller must treat that as "too small to trade", not as an error, and
        must not substitute the minimum (that is a bigger bet than was asked for).
        """
        si = mt5.symbol_info(symbol or self.symbol)
        if not si or si.volume_step <= 0:
            return round(lots, 2)
        steps = int(lots / si.volume_step + 1e-9)
        v = round(steps * si.volume_step, 8)
        if v < si.volume_min:
            return 0.0
        return round(min(v, si.volume_max), 8)

    def get_pending_orders(self, symbol: str = None) -> list:
        """This bot's resting orders — filtered by MAGIC, so another bot (or a hand-placed
        order) on the same terminal and symbol is invisible here and can never be cancelled by
        this bot. Returns [] when there are none or the call fails."""
        orders = mt5.orders_get(symbol=symbol or self.symbol)
        return [o for o in (orders or []) if o.magic == self.magic]

    def get_open_positions(self, symbol: str = None) -> list:
        """This bot's open positions, filtered by MAGIC. Same isolation rule as
        `get_pending_orders` — one terminal can host several bots and a human."""
        pos = mt5.positions_get(symbol=symbol or self.symbol)
        return [p for p in (pos or []) if p.magic == self.magic]

    # ── The ONE unfiltered read, and it is the account-level allocator's whole foundation ──
    #
    # Every other read in this file is MAGIC-filtered, and that rule is right: it is what stops
    # two bots on one terminal cancelling each other's orders and what keeps a hand trade
    # invisible to the reconciler. **It is also exactly what makes an account-level risk cap
    # impossible** — a bot that can only see its own orders cannot know the account is already
    # full. `exec_risk_pct` is per-trade with nothing above it, so two bots at 10% put 20% at
    # risk from a state neither of them can see (`docs/LIVE_TRADING_PIPELINE.md` → G10).
    #
    # So this reads EVERYTHING on the symbol, whoever placed it, and it is deliberately the only
    # one that does. Note what it does NOT do: it never cancels, modifies or closes anything it
    # can see. It is a read for arithmetic. The isolation rule is about WRITES, and nothing here
    # writes.
    def account_exposure(self, symbol: str = None) -> Optional[list]:
        """Everything open or resting on this symbol, across EVERY magic, as `Exposure` rows.

        `None` means the terminal could not be asked — MT5 returns `None` from `positions_get`
        on an error and an empty tuple when there genuinely is nothing, and those two must not
        collapse: an unreadable account read as "nothing on" is a cap that opens itself the
        moment the terminal wobbles. The caller REFUSES on `None`, exactly as it does for a
        `None` margin.

        ⚠ **`sl` is passed through as the broker reports it, zero included.** A position with no
        stop arrives here as `sl = 0.0`, and `account_risk.measure_exposure` refuses on it rather
        than scoring it as zero risk — a stopless position's risk is unbounded, not absent.
        Do not "tidy" a missing stop into a default here.
        """
        from account_risk import Exposure

        sym = symbol or self.symbol
        try:
            pos = mt5.positions_get(symbol=sym)
            orders = mt5.orders_get(symbol=sym)
        except Exception as e:
            self.log.error(f"Could not read the account's exposure on {sym}: {e}")
            return None
        if pos is None or orders is None:
            self.log.error(f"positions_get/orders_get returned None for {sym}: {mt5.last_error()}")
            return None

        out = []
        for p in pos:
            out.append(Exposure(
                ticket=int(p.ticket), symbol=sym, magic=int(p.magic),
                # POSITION_TYPE_BUY is 0 and SELL is 1 — not +1/-1, and reading `p.type` as a
                # sign would make every long a short and every short a flat position.
                direction=1 if int(p.type) == mt5.POSITION_TYPE_BUY else -1,
                volume=float(p.volume), entry=float(p.price_open), stop=float(p.sl),
                resting=False))
        for o in orders:
            buy = int(o.type) in (mt5.ORDER_TYPE_BUY_LIMIT, mt5.ORDER_TYPE_BUY_STOP,
                                  mt5.ORDER_TYPE_BUY_STOP_LIMIT)
            out.append(Exposure(
                ticket=int(o.ticket), symbol=sym, magic=int(o.magic),
                direction=1 if buy else -1,
                # `volume_current` is what is LEFT on a partially-filled order; `volume_initial`
                # would double-count the filled part, which is already in `positions_get` above.
                volume=float(o.volume_current), entry=float(o.price_open), stop=float(o.sl),
                resting=True))
        return out

    def place_pending_limit(self, direction: str, lots: float, price: float,
                            sl: float, tp: float = 0.0, comment: str = "",
                            symbol: str = None) -> tuple:
        """Rest a buy-limit (below market) or sell-limit (above market).

        direction: 'bullish' → BUY LIMIT, 'bearish' → SELL LIMIT
        Returns (ticket, price) or (None, None) — every refusal is logged with its reason.
        """
        sym = symbol or self.symbol
        si  = mt5.symbol_info(sym)
        if not si:
            self.log.error(f"Pending refused: no symbol info for {sym}")
            return None, None
        digits = si.digits
        price  = round(price, digits)
        sl     = round(sl, digits)
        tp     = round(tp, digits) if tp else 0.0

        vol = self.normalize_volume(lots, sym)
        if vol <= 0:
            self.log.warning(
                f"Pending refused: {lots} lots rounds below the {sym} minimum "
                f"({si.volume_min}). Position too small to place — NOT rounding up."
            )
            return None, None

        bid, ask = self.get_tick(sym)
        if not bid or not ask:
            self.log.error(f"Pending refused: no tick for {sym}")
            return None, None

        is_buy = direction == "bullish"
        order_type = mt5.ORDER_TYPE_BUY_LIMIT if is_buy else mt5.ORDER_TYPE_SELL_LIMIT
        market = ask if is_buy else bid

        # A buy-limit must be BELOW the ask, a sell-limit ABOVE the bid. If price has already
        # traded through the level the order is not a limit any more — refuse rather than let
        # MT5 reject it as an "invalid price" the caller then has to decode.
        if (is_buy and price >= market) or ((not is_buy) and price <= market):
            self.log.warning(
                f"Pending refused: {direction} limit {price:.{digits}f} is on the wrong side of "
                f"the market ({market:.{digits}f}) — price already reached the level."
            )
            return None, None

        min_dist = self.min_stop_distance(sym)
        if min_dist > 0:
            if abs(market - price) < min_dist:
                self.log.warning(
                    f"Pending refused: limit {price:.{digits}f} is {abs(market-price):.{digits}f} "
                    f"from market {market:.{digits}f}, inside the broker stops_level "
                    f"{min_dist:.{digits}f} ({sym})."
                )
                return None, None
            if abs(price - sl) < min_dist:
                self.log.warning(
                    f"Pending refused: SL {sl:.{digits}f} is {abs(price-sl):.{digits}f} from the "
                    f"limit {price:.{digits}f}, inside the broker stops_level "
                    f"{min_dist:.{digits}f} ({sym})."
                )
                return None, None

        result = mt5.order_send({
            "action":       mt5.TRADE_ACTION_PENDING,
            "symbol":       sym,
            "volume":       vol,
            "type":         order_type,
            "price":        price,
            "sl":           sl,
            "tp":           tp,
            "magic":        self.magic,
            "comment":      comment or f"{self.bot_label}-LIMIT",
            "type_time":    mt5.ORDER_TIME_GTC,
            "type_filling": mt5.ORDER_FILLING_RETURN,
        })
        if result and result.retcode == mt5.TRADE_RETCODE_DONE:
            self.log.info(
                f"PENDING PLACED | ticket={result.order} | {direction} {vol}L "
                f"@ {price:.{digits}f} | SL={sl:.{digits}f}"
            )
            return result.order, price
        rc = result.retcode if result else None
        self.log.error(f"Pending failed ({sym} {direction} {vol}L @ {price}): "
                       f"retcode={rc} {mt5.last_error()}")
        return None, None

    def modify_pending(self, ticket: int, price: float, sl: float,
                       tp: float = 0.0, symbol: str = None) -> bool:
        """Move a resting order's price / SL / TP. **Cannot change volume** — see the block
        comment above. Returns True if MT5 accepted it."""
        sym = symbol or self.symbol
        si  = mt5.symbol_info(sym)
        digits = si.digits if si else 2
        result = mt5.order_send({
            "action": mt5.TRADE_ACTION_MODIFY,
            "order":  ticket,
            "price":  round(price, digits),
            "sl":     round(sl, digits),
            "tp":     round(tp, digits) if tp else 0.0,
        })
        ok = result is not None and result.retcode == mt5.TRADE_RETCODE_DONE
        if ok:
            self.log.info(f"PENDING MOVED | T{ticket} → {price:.{digits}f} SL={sl:.{digits}f}")
        else:
            rc = result.retcode if result else None
            self.log.error(f"Pending modify failed T{ticket}: retcode={rc} {mt5.last_error()}")
        return ok

    def cancel_pending(self, ticket: int) -> bool:
        """Remove a resting order. A ticket that is already gone (filled or cancelled) counts
        as SUCCESS — the caller's intent is "there should be no order here", and treating a
        race with a fill as a failure would make the bridge retry forever."""
        result = mt5.order_send({"action": mt5.TRADE_ACTION_REMOVE, "order": ticket})
        if result and result.retcode == mt5.TRADE_RETCODE_DONE:
            self.log.info(f"PENDING CANCELLED | T{ticket}")
            return True
        if not mt5.orders_get(ticket=ticket):
            return True     # already gone
        rc = result.retcode if result else None
        self.log.error(f"Pending cancel failed T{ticket}: retcode={rc} {mt5.last_error()}")
        return False

    def cancel_all_pending(self, symbol: str = None) -> int:
        """Cancel every resting order this bot owns. Returns how many were removed."""
        return sum(1 for o in self.get_pending_orders(symbol) if self.cancel_pending(o.ticket))

    def move_sl(self, ticket: int, new_sl: float, tp: float = None) -> bool:
        """
        Modify the stop loss on an open position.

        Reads the position's own symbol from MT5 — works correctly for any
        instrument, not just the bot's default symbol.
        Preserves the existing TP unless tp is explicitly provided.
        Returns True if MT5 accepted the modification.
        """
        pos = mt5.positions_get(ticket=ticket)
        if not pos:
            return False
        sym = pos[0].symbol
        result = mt5.order_send({
            "action":   mt5.TRADE_ACTION_SLTP,
            "symbol":   sym,
            "position": ticket,
            "sl":       round(new_sl, 2),
            "tp":       tp if tp is not None else pos[0].tp,
        })
        return result is not None and result.retcode == mt5.TRADE_RETCODE_DONE

    def partial_close(self, ticket: int, close_lots: float, direction: str) -> bool:
        """
        Close a portion of an open position to bank partial profit.

        Reads the position's own symbol from MT5 — works correctly for any
        instrument. close_lots is rounded to the symbol's volume step and
        clamped to the position's current volume.
        Returns True if MT5 accepted the order.
        """
        pos = mt5.positions_get(ticket=ticket)
        if not pos:
            return False
        sym = pos[0].symbol
        si  = mt5.symbol_info(sym)
        if not si:
            return False
        bid, ask   = self.get_tick(sym)
        price      = bid if direction == "bullish" else ask
        close_type = mt5.ORDER_TYPE_SELL if direction == "bullish" else mt5.ORDER_TYPE_BUY
        close_lots = round(round(close_lots / si.volume_step) * si.volume_step, 2)
        close_lots = max(si.volume_min, min(close_lots, pos[0].volume))
        result = mt5.order_send({
            "action":       mt5.TRADE_ACTION_DEAL,
            "symbol":       sym,
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
        Fetch (close_price, GROSS pnl_usd) from MT5 deal history for a closed position.

        Uses a 7-day lookback window so deals from over the weekend are found.
        Returns (0.0, 0.0) if no closing deal is found.

        Explicitly re-filters by position_id == ticket to guard against MT5
        returning deals from a different position during connection instability.

        ⚠ `d.profit` is the PRICE MOVE ONLY. MT5 carries swap and commission in sibling
        fields on the same deals, and commission is usually booked on the ENTRY deal this
        function does not even look at — so what comes back here is what the trade would have
        made at a frictionless broker. On gold that is not a rounding error: an overnight hold
        pays or earns real swap, and the whole reason this repo is running a live demo bot is
        to measure those costs rather than assume them. Use `get_deal_breakdown` when the
        number is going into a record somebody will later read as "what this trade made".

        Kept as-is on purpose — five other callers unpack this 2-tuple, and widening it to
        smuggle costs into `pnl` would silently redefine every one of them.
        """
        to    = datetime.utcnow()
        from_ = to - timedelta(days=7)
        deals = mt5.history_deals_get(from_, to, position=ticket)
        if deals:
            closing = [d for d in deals if d.entry == 1 and d.position_id == ticket]
            if closing:
                d = closing[-1]
                return float(d.price), float(d.profit)
        return 0.0, 0.0

    def get_deal_breakdown(self, ticket: int) -> dict:
        """
        Fetch a closed position's FULL money result, costs separated from the price move.

        Returns a dict with `close_price`, `gross_usd` (price move), `swap_usd`,
        `commission_usd`, `net_usd` (the three summed — what the balance actually moved by),
        and `deals` (how many deals were summed). All zeros if the position is not found.

        **Why this exists rather than a wider `get_deal_result`.** G5 in the live pipeline is
        "PU Prime's broker facts are assumed, never measured" — every spread, swap and
        commission figure in this repo was measured on VANTAGE, and the bot trades PU Prime.
        A live trade is the only instrument that can settle it, and it can only settle it if
        the costs are recorded SEPARATELY. A single net number cannot be decomposed later;
        gross + swap + commission can always be re-netted.

        ⚠ It sums EVERY deal of the position, not just the closing one. Commission is
        typically charged on the entry deal, swap accrues onto the position and lands on the
        exit — reading the closing deal alone loses the entry-side commission entirely, which
        is exactly the half a "we charge no commission" broker claim would hide.

        ⚠ Swap is reported with MT5's OWN SIGN and is deliberately not abs()'d. Gold's short
        swap is a CREDIT at most brokers, and the command center booked exactly that credit as
        a charge on 2026-08-03 by taking `-abs(cost)` — 39 of 161 backtest trades were net
        credits and the page overstated fees by 25%. A cost field that cannot be positive
        cannot measure a broker that pays you.

        ⚠ Zeros mean NOT FOUND, not free. `deals: 0` is the tell, and a reader must check it —
        this repo's standing rule is that "no data" and "cannot ask" must never be the same
        value, and a dict of zeros is what an unreachable terminal returns too.
        """
        empty = {"close_price": 0.0, "gross_usd": 0.0, "swap_usd": 0.0,
                 "commission_usd": 0.0, "net_usd": 0.0, "deals": 0}
        to    = datetime.utcnow()
        from_ = to - timedelta(days=7)
        deals = mt5.history_deals_get(from_, to, position=ticket)
        if not deals:
            return empty

        mine = [d for d in deals if d.position_id == ticket]
        if not mine:
            return empty

        gross = sum(float(getattr(d, "profit", 0.0) or 0.0) for d in mine)
        swap = sum(float(getattr(d, "swap", 0.0) or 0.0) for d in mine)
        comm = sum(float(getattr(d, "commission", 0.0) or 0.0) for d in mine)
        closing = [d for d in mine if d.entry == 1]
        price = float(closing[-1].price) if closing else 0.0

        return {"close_price": price, "gross_usd": gross, "swap_usd": swap,
                "commission_usd": comm, "net_usd": gross + swap + comm,
                "deals": len(mine)}

    def close_position(self, ticket: int, direction: str,
                       reason: str = "") -> tuple[bool, float, float]:
        """
        Close an open position at market price.

        Reads the position's own symbol from MT5 — works correctly for any
        instrument. Waits 0.3s after the order executes then fetches the actual
        realised P&L from MT5 deal history. Falls back to the pre-close
        floating P&L only if deal history is not yet available.

        Returns (success, close_price, pnl_usd).
        """
        pos = mt5.positions_get(ticket=ticket)
        if not pos:
            return False, 0.0, 0.0
        p          = pos[0]
        sym        = p.symbol
        bid, ask   = self.get_tick(sym)
        close_type = mt5.ORDER_TYPE_SELL if direction == "bullish" else mt5.ORDER_TYPE_BUY
        price      = bid if direction == "bullish" else ask
        result = mt5.order_send({
            "action":       mt5.TRADE_ACTION_DEAL,
            "symbol":       sym,
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

    def close_all_positions(self, reason: str = "",
                            symbols: list = None) -> list:
        """
        Force-close all open positions belonging to this bot (filtered by magic number).

        Returns list of (ticket, close_price, pnl_usd) for each successfully closed position
        so callers can log trade outcomes immediately — avoids stale deal-history cross-
        contamination that occurs when get_deal_result is called later for batch closes.

        symbols: list of symbol strings to scan. Defaults to [self.symbol].
                 Pass the full watchlist to close across all instruments.
        """
        syms = symbols if symbols else [self.symbol]
        all_own = []
        for sym in syms:
            positions = mt5.positions_get(symbol=sym)
            if positions:
                all_own.extend([p for p in positions if p.magic == self.magic])
        if not all_own:
            return []
        self.log.warning(f"CLOSE ALL — {reason} | {len(all_own)} position(s)")
        results = []
        for p in all_own:
            bid, ask   = self.get_tick(p.symbol)
            price      = bid if p.type == mt5.ORDER_TYPE_BUY else ask
            close_type = mt5.ORDER_TYPE_SELL if p.type == mt5.ORDER_TYPE_BUY else mt5.ORDER_TYPE_BUY
            result = mt5.order_send({
                "action":       mt5.TRADE_ACTION_DEAL,
                "symbol":       p.symbol,
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
                self.log.warning(f"  Closed T{p.ticket} {p.symbol} @ {price:.2f}")
                time.sleep(0.3)
                cp, pnl = self.get_deal_result(p.ticket)
                if cp == 0.0:
                    cp, pnl = price, p.profit  # fallback: pre-close floating value
                results.append((p.ticket, cp, pnl))
            else:
                self.log.error(f"  Failed T{p.ticket}: {mt5.last_error()}")
        return results

    def lot_size(self, balance: float, sl_dist: float, risk_pct: float,
                 risk_mult: float = 1.0, symbol: str = None) -> float:
        """
        Calculate MT5 lot size for the given risk parameters.

        risk_pct: percentage of balance to risk (e.g. 1.0 for 1%)
        risk_mult: multiplier applied to sl_dist (e.g. for news stop widening)
        symbol:   override instance symbol (for multi-instrument scanning)
        Rounds to the symbol's volume step and clamps to min/max lot.
        """
        sym = symbol or self.symbol
        si  = mt5.symbol_info(sym)
        if not si or si.trade_tick_size == 0 or sl_dist == 0:
            return si.volume_min if si else 0.01
        actual_sl = sl_dist * risk_mult
        risk      = balance * (risk_pct / 100)
        ticks     = actual_sl / si.trade_tick_size
        lots      = risk / (ticks * si.trade_tick_value)
        lots      = max(si.volume_min, min(si.volume_max, lots))
        lots      = round(round(lots / si.volume_step) * si.volume_step, 2)
        digits = si.digits if si else 5
        self.log.info(
            f"Lot size: {lots}L | risk={risk_pct:.2f}% (${risk:.2f}) | "
            f"balance=${balance:,.0f} | sl={actual_sl:.{digits}f}pts"
        )
        return lots

    def write_live_state(self, state_key: str, weekly_start: float,
                         daily_start: float):
        """
        Fetch account balance from MT5, guard against bad readings, and write
        the live state fields (balance, last_write, weekly_start, daily_start)
        to bot_state.json.

        Returns the AccountInfo object on success, or None if MT5 returned a
        zero/missing balance (callers should sleep + continue the loop).

        Call this BEFORE any early-continue paths (dead zone, market close) so
        the P&L tracker always sees a fresh last_write and stays in LIVE mode.
        """
        acct = mt5.account_info()
        if not acct or acct.balance <= 0:
            self.log.warning("MT5 returned zero balance — skipping iteration (bad reading).")
            return None
        write_bot(state_key, {
            "balance":      acct.balance,
            "status":       "running",
            "weekly_start": weekly_start,
            "daily_start":  daily_start,
            "last_write":   datetime.now(timezone.utc).isoformat(),
        })
        return acct

    def recover_open_positions(self, symbols: list = None) -> list:
        """
        On bot restart, scan MT5 for positions opened by this bot (by magic number)
        and rebuild a minimal open_trades list so position management resumes.

        symbols: list of symbol strings to scan. Defaults to [self.symbol].
                 Pass the full watchlist to recover positions across all instruments.
        Returns list of dicts with keys: ticket, entry, sl, dir, lots, symbol.
        Bot-specific fields (tp, be_done, etc.) should be set by the caller.
        """
        syms      = symbols if symbols else [self.symbol]
        recovered = []
        for sym in syms:
            positions = mt5.positions_get(symbol=sym)
            if not positions:
                continue
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
                    "symbol": sym,
                })
                self.log.info(
                    f"RECOVERED T{p.ticket} {sym} | {direction} {p.volume}L "
                    f"@ {p.price_open:.2f} | P&L=${p.profit:.2f} | SL={p.sl:.2f}"
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

    def disconnect(self) -> None:
        """Shut down MT5 and log."""
        mt5.shutdown()
        self.log.info("MT5 disconnected.")

    # ── Dead zone management ──────────────────────────────────────────────────

    def handle_dead_zone(self, open_trades: list, atr: float, logger, ai) -> None:
        """
        Portfolio-level trade management during the configured dead zone window.

        Window is set per-bot via config.json (dead_zone.start_ct / end_ct).
        Scalper: 3–7pm CT. SMC Trend / Mean Reversion / FFT: 4–5pm CT (gold close).

        1. Net profitable → close ALL positions immediately (lock in combined profit).
        2. Net negative per-trade:
           a. Trade worsening → close immediately (stop the bleeding).
           b. Trade improving or at BE → hold and monitor.
           c. 3:45 PM TX hard cut → close all remaining regardless.
              (Only fires when dead zone starts at or before 3:45pm — i.e. Scalper only.)
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
                else:
                    t["_missing_count"] = t.get("_missing_count", 0) + 1
                    if t["_missing_count"] >= 3:
                        self.log.warning(
                            f"T{t['ticket']} missing from MT5 for 3 dead-zone checks "
                            "with no deal history — marking orphaned."
                        )
                        logger.mark_orphaned(t["ticket"])
                        open_trades.remove(t)
                    else:
                        self.log.warning(
                            f"T{t['ticket']} not found in MT5 "
                            f"({t['_missing_count']}/3 dead-zone checks) — "
                            "possible connection glitch, retaining."
                        )
                continue
            t["_missing_count"] = 0
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
