"""
╔══════════════════════════════════════════════════════════════════════════════╗
║  BOT 5 — FFT (Fibonacci Fractal Trading) STRATEGY                          ║
║  Instrument: XAUUSD (Gold Spot) | Primary Timeframe: M15                   ║
║                                                                              ║
║  STRATEGY OVERVIEW                                                           ║
║  ─────────────────                                                           ║
║  The FFT strategy uses two Fibonacci tools working together to find          ║
║  high-probability entries in trending markets:                               ║
║                                                                              ║
║  1. FFT FIB (Standard Retracement)                                          ║
║     Drawn from the structural swing that CAUSED the Break of Structure.     ║
║     Bullish: from Higher Low → new Higher High                              ║
║     Bearish: from Lower High → new Lower Low                                ║
║     Defines the ENTRY CONSIDERATION ZONE: 61.8% to 88.6% retracement        ║
║                                                                              ║
║  2. SNIPER FIB (Reverse Fibonacci — Green Zone)                             ║
║     Drawn on the COUNTER MOVE immediately before the BOS candle.            ║
║     Bullish: from Lower High → Higher Low (counter move before BOS)         ║
║     Bearish: from Higher Low → Lower High (counter move before BOS)         ║
║     The 38.2% to 50% zone of this fib = GREEN ZONE                         ║
║                                                                              ║
║  ENTRY RULE (ALL must be true):                                              ║
║  ────────────────────────────────                                            ║
║  1. Confirmed Break of Structure (BOS) on M15                               ║
║  2. H1/H4 trend confirms direction                                          ║
║  3. Price retraces into FFT fib 61.8–88.6% zone                            ║
║  4. Sniper fib GREEN ZONE (38.2–50%) overlaps with the FFT zone             ║
║  5. Entry at sniper 50% (Entry 1) and sniper 38.2% (Entry 2 if lots allow)  ║
║                                                                              ║
║  TRADE MANAGEMENT                                                            ║
║  ─────────────────                                                           ║
║  Stop Loss:   1% of price behind bottom of green zone                       ║
║  Breakeven:   Move to entry as soon as +0.5R profit                         ║
║  TP1 (80%):   FFT fib 50% retracement level                                 ║
║  TP2 (20%):   FFT fib 38.2% retracement level                               ║
║  Deep entry:  If entry at 78.6% or 88.6% → TP1=70.2%, TP2=61.8%           ║
║  Min lots:    Single entry at sniper 50%, full close at FFT 50%             ║
║                                                                              ║
║  REFINEMENT                                                                  ║
║  ───────────                                                                 ║
║  As more chart examples are provided, the detection logic and confluence    ║
║  scoring will be refined. This is version 1.0 — a solid foundation that     ║
║  will improve with real trade data and AI training.                          ║
║                                                                              ║
║  Platform: MetaTrader 5 (MT5)                                               ║
║  Account:  Dedicated MT5_FFT instance                                        ║
║  Run:      python bots/bot_fft.py --config                                 ║
║            markets/fx/instances/gold_fft/config.json                      ║
╚══════════════════════════════════════════════════════════════════════════════╝
"""

import argparse
import json
import logging
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

import MetaTrader5 as mt5
import numpy as np
import pandas as pd

# ── Path setup ────────────────────────────────────────────────────────────────
sys.path.insert(0, str(Path(__file__).parent))
sys.path.insert(0, str(Path(__file__).parent.parent / "shared"))

from bot_utils      import load_config, setup_logging, get_instance_dir
from shared_ai_brain import AIBrain, TradeLogger, DailyLogger, build_features_trend
from shared_calmar   import CalmarTracker
from shared_regime   import RegimeClassifier

# ── Load config ───────────────────────────────────────────────────────────────
_CFG  = load_config()
log   = setup_logging("BOT_FFT", _CFG)
_INST = get_instance_dir(_CFG)

# Symbol and account
SYMBOL   = _CFG.get("symbol", "XAUUSD.s")
ACCOUNT  = _CFG.get("account", {})

# Strategy params (all configurable via config.json)
_S = _CFG.get("bot_fft", {})

# Structure detection
SWING_LOOKBACK      = _S.get("swing_lookback", 3)       # candles each side to confirm swing
BOS_MIN_BODY_MULT   = _S.get("bos_min_body_mult", 1.5)  # BOS candle body >= 1.5x ATR

# Fibonacci levels
FFT_ENTRY_MIN       = _S.get("fft_entry_min", 0.618)    # entry zone bottom (61.8%)
FFT_ENTRY_MAX       = _S.get("fft_entry_max", 0.886)    # entry zone top (88.6%)
FFT_DEEP_THRESHOLD  = _S.get("fft_deep_threshold", 0.786) # deep entry threshold
FFT_TP1_NORMAL      = _S.get("fft_tp1_normal", 0.500)   # TP1 normal entry
FFT_TP2_NORMAL      = _S.get("fft_tp2_normal", 0.382)   # TP2 normal entry
FFT_TP1_DEEP        = _S.get("fft_tp1_deep", 0.702)     # TP1 deep entry (78.6/88.6%)
FFT_TP2_DEEP        = _S.get("fft_tp2_deep", 0.618)     # TP2 deep entry
SNIPER_ENTRY1       = _S.get("sniper_entry1", 0.500)    # sniper 50% = Entry 1
SNIPER_ENTRY2       = _S.get("sniper_entry2", 0.382)    # sniper 38.2% = Entry 2
SNIPER_ZONE_MIN     = _S.get("sniper_zone_min", 0.382)  # green zone bottom
SNIPER_ZONE_MAX     = _S.get("sniper_zone_max", 0.500)  # green zone top

# Trade management
SL_PCT_BEHIND_ZONE  = _S.get("sl_pct_behind_zone", 0.01) # 1% beyond green zone
BE_R                = _S.get("breakeven_at_r", 0.5)       # breakeven at 0.5R
TP1_SIZE_PCT        = _S.get("tp1_size_pct", 0.80)        # 80% at TP1
TP2_SIZE_PCT        = _S.get("tp2_size_pct", 0.20)        # 20% at TP2

# Risk
RISK_PCT            = _S.get("risk_pct", 1.0)
MAX_DAILY_LOSS      = _S.get("max_daily_loss_pct", 5.0)
MAX_WEEKLY_LOSS     = _S.get("max_weekly_loss_pct", 15.0)
MAX_TRADES_DAY      = _S.get("max_trades_per_day", 3)
MIN_AI_PROB         = _S.get("min_ai_probability", 0.52)

# Timeframes
TF_ENTRY  = mt5.TIMEFRAME_M15
TF_TREND  = mt5.TIMEFRAME_H1
TF_HIGHER = mt5.TIMEFRAME_H4

# Magic number for this bot
MAGIC = 20240005

log.info(f"BOT_FFT | FFT Strategy | {SYMBOL} | risk={RISK_PCT}%")


# =============================================================================
# MT5 CONNECTION
# =============================================================================

def connect() -> bool:
    """
    Connect to the correct MT5 terminal instance.

    CRITICAL: Never falls back to no-path initialize when a mt5_path is configured.
    Falling back to no-path allows Python to connect to ANY terminal, which causes
    it to log accounts into the wrong terminal — MT5 remembers all logins.

    Strategy:
    1. Acquire connection lock (prevents race conditions between bots)
    2. Try mt5.initialize(path=...) — retries up to 5 times with delay
    3. If IPC timeout: terminal is already running — retry, don't fallback
    4. Verify account matches expected ID before proceeding
    """
    import time as _time

    LOCK_FILE    = Path(r"C:\algos\mt5_connect.lock")
    LOCK_TIMEOUT = 90
    LOCK_TTL     = 45

    def acquire_lock(bot_id: str) -> bool:
        waited = 0
        while waited < LOCK_TIMEOUT:
            if LOCK_FILE.exists():
                try:
                    age    = _time.time() - LOCK_FILE.stat().st_mtime
                    holder = LOCK_FILE.read_text().strip()
                    if age > LOCK_TTL:
                        log.warning(f"Stale lock ({age:.0f}s old, held by {holder}) — removing")
                        LOCK_FILE.unlink(missing_ok=True)
                    else:
                        log.info(f"Waiting for MT5 lock (held by {holder}, {age:.0f}s)...")
                        _time.sleep(3)
                        waited += 3
                        continue
                except Exception:
                    pass
            try:
                LOCK_FILE.write_text(bot_id)
                _time.sleep(0.5)
                if LOCK_FILE.exists() and LOCK_FILE.read_text().strip() == bot_id:
                    return True
            except Exception as e:
                log.warning(f"Lock write error: {e}")
            _time.sleep(1)
            waited += 1
        log.error(f"Could not acquire MT5 lock after {LOCK_TIMEOUT}s")
        return False

    def release_lock():
        try:
            LOCK_FILE.unlink(missing_ok=True)
        except Exception:
            pass

    startup_delay = _CFG.get("startup_delay", 0)
    if startup_delay > 0:
        log.info(f"Startup delay {startup_delay}s")
        _time.sleep(startup_delay)

    mt5_path    = _CFG.get("mt5_path", "")
    expected_id = ACCOUNT.get("login")
    bot_id      = f"BOT_FFT_{expected_id}"

    if not acquire_lock(bot_id):
        return False

    try:
        MAX_ATTEMPTS = 5
        for attempt in range(1, MAX_ATTEMPTS + 1):
            if attempt > 1:
                log.info(f"Connect attempt {attempt}/{MAX_ATTEMPTS} — waiting 8s...")
                _time.sleep(8)
                try:
                    mt5.shutdown()
                except Exception:
                    pass

            # Initialize
            if mt5_path:
                # Always use explicit path — NEVER fall back to no-path
                # IPC timeout means terminal is already running — just retry
                init_ok = mt5.initialize(path=mt5_path)
                if not init_ok:
                    err = mt5.last_error()
                    if err[0] == -10005:
                        log.info(f"IPC timeout (attempt {attempt}) — terminal running, will retry with path")
                    else:
                        log.warning(f"MT5 init failed (attempt {attempt}): {err}")
                    continue
            else:
                if not mt5.initialize():
                    log.warning(f"MT5 init failed (attempt {attempt}): {mt5.last_error()}")
                    continue

            # Login with explicit credentials
            if not mt5.login(ACCOUNT["login"], password=ACCOUNT["password"],
                             server=ACCOUNT["server"]):
                log.warning(f"Login failed (attempt {attempt}): {mt5.last_error()}")
                mt5.shutdown()
                continue

            # Verify correct account — if wrong, shut down immediately
            # Do NOT retry login on same terminal — shut down and try again
            info = mt5.account_info()
            if not info:
                log.warning(f"No account info (attempt {attempt})")
                mt5.shutdown()
                continue

            if info.login != expected_id:
                log.error(
                    f"ACCOUNT MISMATCH (attempt {attempt}): "
                    f"got #{info.login} expected #{expected_id} — "
                    f"shutting down and retrying"
                )
                mt5.shutdown()
                continue

            log.info(f"Connected | #{info.login} | ${info.balance:,.2f} | {info.server}")
            return True

        log.error(
            f"Failed to connect to #{expected_id} after {MAX_ATTEMPTS} attempts. "
            f"Ensure the correct MT5 terminal is open at: {mt5_path}"
        )
        return False

    finally:
        release_lock()
        log.info("MT5 connection lock released")


def now_utc() -> datetime:
    return datetime.now(timezone.utc)


def get_candles(timeframe: int, count: int) -> pd.DataFrame:
    """Fetch OHLCV candles from MT5."""
    rates = mt5.copy_rates_from_pos(SYMBOL, timeframe, 0, count)
    if rates is None or len(rates) == 0:
        return pd.DataFrame()
    df = pd.DataFrame(rates)
    df["time"] = pd.to_datetime(df["time"], unit="s", utc=True)
    return df


def get_tick() -> tuple:
    """Return (bid, ask) for the symbol."""
    tick = mt5.symbol_info_tick(SYMBOL)
    if not tick:
        return 0.0, 0.0
    return tick.bid, tick.ask


def get_atr(df: pd.DataFrame, period: int = 14) -> float:
    """Average True Range over the given period."""
    h, l, c = df["high"], df["low"], df["close"].shift(1)
    tr = pd.concat([h - l, (h - c).abs(), (l - c).abs()], axis=1).max(axis=1)
    return float(tr.rolling(period).mean().iloc[-1])


def get_ema(df: pd.DataFrame, period: int) -> float:
    """Exponential moving average of close."""
    return float(df["close"].ewm(span=period, adjust=False).mean().iloc[-1])


def lot_size(balance: float, sl_distance: float,
             risk_mult: float = 1.0) -> float:
    """
    Calculate lot size based on account balance and stop loss distance.

    sl_distance: distance in price points (e.g. 5.00 for gold)
    Returns lot size rounded to nearest 0.01, minimum 0.01.
    """
    tick_value = mt5.symbol_info(SYMBOL).trade_tick_value
    tick_size  = mt5.symbol_info(SYMBOL).trade_tick_size
    if tick_size == 0 or sl_distance == 0:
        return 0.01
    risk_amount = balance * (RISK_PCT / 100) * risk_mult
    sl_ticks    = sl_distance / tick_size
    sl_value    = sl_ticks * tick_value
    lots = risk_amount / sl_value if sl_value > 0 else 0.01
    lots = max(0.01, round(lots / 0.01) * 0.01)
    return lots


def place_order(direction: str, lots: float, sl: float,
                tp: float, comment: str = "FFT") -> tuple:
    """
    Place a market order.

    direction: 'bullish' or 'bearish'
    Returns (ticket, filled_price) or (None, None) on failure.
    """
    bid, ask = get_tick()
    order_type = mt5.ORDER_TYPE_BUY if direction == "bullish" else mt5.ORDER_TYPE_SELL
    price      = ask if direction == "bullish" else bid

    request = {
        "action":    mt5.TRADE_ACTION_DEAL,
        "symbol":    SYMBOL,
        "volume":    lots,
        "type":      order_type,
        "price":     price,
        "sl":        sl,
        "tp":        tp,
        "deviation": 20,
        "magic":     MAGIC,
        "comment":   comment,
        "type_time": mt5.ORDER_TIME_GTC,
        "type_filling": mt5.ORDER_FILLING_IOC,
    }
    result = mt5.order_send(request)
    if result.retcode == mt5.TRADE_RETCODE_DONE:
        log.info(f"ORDER FILLED | ticket={result.order} | "
                 f"{direction} {lots}L @ {result.price:.2f}")
        return result.order, result.price
    log.error(f"Order failed: {result.retcode} '{result.comment}'")
    return None, None


def close_position(ticket: int, direction: str, reason: str = "") -> bool:
    """Close an open position at market."""
    pos = mt5.positions_get(ticket=ticket)
    if not pos:
        return True
    p = pos[0]
    bid, ask = get_tick()
    close_type  = mt5.ORDER_TYPE_SELL if direction == "bullish" else mt5.ORDER_TYPE_BUY
    close_price = bid if direction == "bullish" else ask
    request = {
        "action":    mt5.TRADE_ACTION_DEAL,
        "symbol":    SYMBOL,
        "volume":    p.volume,
        "type":      close_type,
        "position":  ticket,
        "price":     close_price,
        "deviation": 20,
        "magic":     MAGIC,
        "comment":   f"FFT-CLOSE-{reason}",
        "type_time": mt5.ORDER_TIME_GTC,
        "type_filling": mt5.ORDER_FILLING_IOC,
    }
    result = mt5.order_send(request)
    ok = result.retcode == mt5.TRADE_RETCODE_DONE
    if ok:
        log.info(f"CLOSED T{ticket} | reason={reason}")
    return ok


def modify_sl(ticket: int, new_sl: float) -> bool:
    """Modify stop loss on an open position."""
    pos = mt5.positions_get(ticket=ticket)
    if not pos:
        return False
    p = pos[0]
    request = {
        "action":   mt5.TRADE_ACTION_SLTP,
        "symbol":   SYMBOL,
        "position": ticket,
        "sl":       new_sl,
        "tp":       p.tp,
    }
    result = mt5.order_send(request)
    return result.retcode == mt5.TRADE_RETCODE_DONE


def is_market_close() -> bool:
    """True when it's the daily market close window (19:45–21:00 UTC)."""
    now = now_utc()
    return (now.hour == 19 and now.minute >= 45) or now.hour == 20



def is_dead_zone() -> bool:
    """
    Returns True during the no-new-entries window: 3:00pm - 7:00pm Texas time.
    Uses America/Chicago timezone so daylight saving is handled automatically.
    CDT (Mar-Nov): 3pm-7pm CT = 20:00-00:00 UTC
    CST (Nov-Mar): 3pm-7pm CT = 21:00-01:00 UTC
    """
    try:
        from zoneinfo import ZoneInfo
        texas = ZoneInfo("America/Chicago")
        now_tx = now_utc().astimezone(texas)
        h = now_tx.hour
        return 15 <= h < 19
    except Exception:
        # Fallback: use UTC offset estimate (CDT = UTC-5)
        t = now_utc()
        return 20 <= t.hour < 24 or t.hour == 0


def handle_dead_zone(open_trades: list, atr: float):
    """
    Dead zone trade management (3:00pm - 7:00pm Texas time).

    Portfolio-level logic — looks at ALL open trades together:

    1. Calculate total floating P&L across all open trades (in $)
    2. If portfolio is NET PROFITABLE → close ALL positions immediately
       (lock in the combined profit, don't risk the dead zone)
    3. If portfolio is NET NEGATIVE:
       a. For any individual trade getting WORSE → close that trade immediately
          at the best possible price (stop the bleeding)
       b. For trades that are improving or at BE → hold and monitor
       c. At 3:45pm TX → close ALL remaining positions regardless
       d. If portfolio flips to net profitable at any point → close ALL immediately
    4. Profitable trades → move to breakeven if not already done

    DST handled automatically via America/Chicago timezone.
    """
    try:
        from zoneinfo import ZoneInfo
        texas   = ZoneInfo("America/Chicago")
        now_tx  = now_utc().astimezone(texas)
        tx_hour = now_tx.hour
        tx_min  = now_tx.minute
        hard_cut = tx_hour > 15 or (tx_hour == 15 and tx_min >= 45)
    except Exception:
        hard_cut = False

    if not open_trades:
        return

    # ── Refresh all positions and calculate portfolio P&L ────────────────
    live_trades = []
    total_pnl   = 0.0

    for t in open_trades[:]:
        pos = mt5.positions_get(ticket=t["ticket"])
        if not pos:
            open_trades.remove(t)
            continue
        p = pos[0]
        total_pnl += p.profit
        live_trades.append((t, p))

    if not live_trades:
        return

    # ── Portfolio is NET PROFITABLE → close everything now ────────────────
    if total_pnl > 0:
        log.info(f"DEAD ZONE PORTFOLIO CLOSE | Net P&L=+${total_pnl:.2f} | "
                 f"Closing all {len(live_trades)} position(s) — locking profit.")
        for t, p in live_trades:
            direction = t["dir"]
            close_position(t["ticket"], direction, "dead-zone-net-profit")
            if t in open_trades:
                open_trades.remove(t)
        return

    # ── Portfolio is NET NEGATIVE ─────────────────────────────────────────
    for t, p in live_trades:
        entry     = t["entry"]
        sl        = t["sl"]
        sl_dist   = abs(entry - sl)
        direction = t["dir"]

        if sl_dist == 0:
            continue

        if direction == "bullish":
            profit_r = (p.price_current - entry) / sl_dist
        else:
            profit_r = (entry - p.price_current) / sl_dist

        if profit_r > 0:
            # This trade is individually profitable — move to BE
            if not t.get("be_done"):
                ok = modify_sl(t["ticket"], entry)
                if ok:
                    t["be_done"] = True
                    t["sl"]      = entry
                    log.info(f"DEAD ZONE BE | T{t['ticket']} "
                             f"-> breakeven @ {entry:.2f}")

        else:
            # This trade is in loss
            prev_r = t.get("_dz_prev_r", profit_r)
            worsening = profit_r < prev_r  # loss is getting bigger
            t["_dz_prev_r"] = profit_r

            if hard_cut:
                # 3:45pm hard cut — close at best available price
                log.warning(f"DEAD ZONE 3:45 CUT | T{t['ticket']} | "
                            f"P&L={profit_r:.2f}R | ${p.profit:.2f} | "
                            f"closing now.")
                close_position(t["ticket"], direction, "dead-zone-3:45-cut")
                if t in open_trades:
                    open_trades.remove(t)

            elif worsening:
                # Loss is getting worse — close at the lowest loss possible now
                log.warning(f"DEAD ZONE WORSENING | T{t['ticket']} | "
                            f"P&L={profit_r:.2f}R -> {prev_r:.2f}R "
                            f"| ${p.profit:.2f} | closing to limit loss.")
                close_position(t["ticket"], direction, "dead-zone-worsening")
                if t in open_trades:
                    open_trades.remove(t)

            else:
                # Loss improving — monitor
                log.info(f"DEAD ZONE MONITOR | T{t['ticket']} | "
                         f"P&L={profit_r:.2f}R improving | "
                         f"Portfolio=${total_pnl:.2f} | "
                         f"Holding to 3:45pm TX.")


def close_all_positions(reason: str = ""):
    """Force-close all open FFT positions."""
    positions = mt5.positions_get(symbol=SYMBOL)
    if not positions:
        return
    for p in positions:
        if p.magic != MAGIC:
            continue
        direction = "bullish" if p.type == mt5.ORDER_TYPE_BUY else "bearish"
        close_position(p.ticket, direction, reason)


def recover_open_positions() -> list:
    """
    On bot restart, recover any open positions placed by this bot
    so we can continue managing them (breakeven, trailing, TP2).
    """
    positions = mt5.positions_get(symbol=SYMBOL)
    if not positions:
        return []
    recovered = []
    for p in positions:
        if p.magic != MAGIC:
            continue
        direction = "bullish" if p.type == mt5.ORDER_TYPE_BUY else "bearish"
        recovered.append({
            "ticket":       p.ticket,
            "entry":        p.price_open,
            "sl":           p.sl,
            "tp":           p.tp,
            "dir":          direction,
            "lots":         p.volume,
            "be_done":      False,
            "tp1_done":     False,
            "fft_levels":   None,  # will be recalculated on next signal
        })
    if recovered:
        log.info(f"Recovered {len(recovered)} open FFT position(s).")
    return recovered


# =============================================================================
# STRUCTURE DETECTION
# =============================================================================

def find_swing_highs(df: pd.DataFrame, lookback: int = 3) -> list:
    """
    Find swing highs: candles where 'high' is greater than 'lookback'
    candles on both sides.

    Returns list of (index, price) tuples, most recent last.
    """
    highs = []
    for i in range(lookback, len(df) - lookback):
        hi = df["high"].iloc[i]
        left  = all(df["high"].iloc[i - j] < hi for j in range(1, lookback + 1))
        right = all(df["high"].iloc[i + j] < hi for j in range(1, lookback + 1))
        if left and right:
            highs.append((i, float(hi)))
    return highs


def find_swing_lows(df: pd.DataFrame, lookback: int = 3) -> list:
    """
    Find swing lows: candles where 'low' is less than 'lookback'
    candles on both sides.

    Returns list of (index, price) tuples, most recent last.
    """
    lows = []
    for i in range(lookback, len(df) - lookback):
        lo = df["low"].iloc[i]
        left  = all(df["low"].iloc[i - j] > lo for j in range(1, lookback + 1))
        right = all(df["low"].iloc[i + j] > lo for j in range(1, lookback + 1))
        if left and right:
            lows.append((i, float(lo)))
    return lows


def detect_bos(df: pd.DataFrame, atr: float) -> dict | None:
    """
    Detect a Break of Structure on the given dataframe.

    A bullish BOS occurs when:
    - There are at least 2 swing lows (higher lows in an uptrend) and
    - The last impulsive candle closes above the most recent swing high
    - The BOS candle body is significant (>= BOS_MIN_BODY_MULT * ATR)

    A bearish BOS occurs when:
    - There are at least 2 swing highs (lower highs in a downtrend) and
    - The last impulsive candle closes below the most recent swing low
    - The BOS candle body is significant

    Returns dict with:
        direction:     'bullish' or 'bearish'
        bos_price:     price level that was broken
        bos_candle_idx: index of the BOS candle
        swing_high:    price of the relevant swing high (for FFT draw)
        swing_low:     price of the relevant swing low (for FFT draw)
        counter_high:  price of counter move high (for sniper draw)
        counter_low:   price of counter move low (for sniper draw)
    Or None if no BOS detected.
    """
    if len(df) < 20:
        return None

    swing_highs = find_swing_highs(df, SWING_LOOKBACK)
    swing_lows  = find_swing_lows(df, SWING_LOOKBACK)

    if len(swing_highs) < 2 or len(swing_lows) < 2:
        return None

    last_candle = df.iloc[-1]
    prev_candle = df.iloc[-2]
    body_size   = abs(last_candle["close"] - last_candle["open"])

    # ── BULLISH BOS ────────────────────────────────────────────────────────
    # Structure: lower low → higher low → impulsive push breaks above swing high
    # FFT draw:  from the higher low UP to the new higher high
    # Sniper:    from the lower high DOWN to the higher low (counter move before BOS)

    # Get the two most recent swing lows
    sl1_idx, sl1_price = swing_lows[-2]  # older swing low (lower low)
    sl2_idx, sl2_price = swing_lows[-1]  # recent swing low (higher low = FFT start)

    # Get the most recent swing high between the two lows (= BOS level)
    sh_between = [sh for sh in swing_highs if sl1_idx < sh[0] < sl2_idx]
    if not sh_between:
        sh_between = [sh for sh in swing_highs if sh[0] > sl1_idx]

    if sh_between and sl2_price > sl1_price:  # higher low confirms uptrend attempt
        sh_idx, sh_price = sh_between[-1]
        # Check if last candle closes above the swing high (BOS)
        if (last_candle["close"] > sh_price and
                body_size >= BOS_MIN_BODY_MULT * atr):
            # Counter move: from the swing high (sh_price) down to the higher low (sl2)
            # This is the sniper fib draw range
            return {
                "direction":     "bullish",
                "bos_price":     sh_price,
                "bos_candle_idx": len(df) - 1,
                "fft_low":       sl2_price,   # FFT fib start (higher low)
                "fft_high":      last_candle["high"],  # FFT fib end (new high being formed)
                "counter_high":  sh_price,    # sniper fib top (lower high before BOS)
                "counter_low":   sl2_price,   # sniper fib bottom (higher low)
            }

    # ── BEARISH BOS ────────────────────────────────────────────────────────
    # Structure: higher high → lower high → impulsive push breaks below swing low
    # FFT draw:  from the lower high DOWN to the new lower low
    # Sniper:    from the higher low UP to the lower high (counter move before BOS)

    sh1_idx, sh1_price = swing_highs[-2]  # older swing high (higher high)
    sh2_idx, sh2_price = swing_highs[-1]  # recent swing high (lower high = FFT start)

    sl_between = [sl for sl in swing_lows if sh1_idx < sl[0] < sh2_idx]
    if not sl_between:
        sl_between = [sl for sl in swing_lows if sl[0] > sh1_idx]

    if sl_between and sh2_price < sh1_price:  # lower high confirms downtrend attempt
        sl_idx, sl_price = sl_between[-1]
        if (last_candle["close"] < sl_price and
                body_size >= BOS_MIN_BODY_MULT * atr):
            return {
                "direction":     "bearish",
                "bos_price":     sl_price,
                "bos_candle_idx": len(df) - 1,
                "fft_high":      sh2_price,   # FFT fib start (lower high)
                "fft_low":       last_candle["low"],  # FFT fib end (new low being formed)
                "counter_high":  sh2_price,   # sniper fib top (lower high)
                "counter_low":   sl_price,    # sniper fib bottom (higher low before BOS)
            }

    return None


# =============================================================================
# FIBONACCI CALCULATIONS
# =============================================================================

def calc_fft_levels(bos: dict) -> dict:
    """
    Calculate all FFT fib retracement levels from the BOS structure.

    Bullish: fib drawn from fft_low (higher low) to fft_high (new higher high)
             Retracement levels measure how far price pulls BACK DOWN from the high
             0% = fft_high (top), 100% = fft_low (bottom)

    Bearish: fib drawn from fft_high (lower high) to fft_low (new lower low)
             Retracement levels measure how far price pulls BACK UP from the low
             0% = fft_low (bottom), 100% = fft_high (top)

    Returns dict of price levels for each fib %.
    """
    if bos["direction"] == "bullish":
        high  = bos["fft_high"]
        low   = bos["fft_low"]
        rng   = high - low
        # Retracement from high back down:
        # 61.8% retrace = high - 0.618 * rng (price is below high)
        return {
            "0":    high,
            "23.6": high - 0.236 * rng,
            "38.2": high - 0.382 * rng,  # TP2 (normal) / TP1 (deep)
            "50.0": high - 0.500 * rng,  # TP1 (normal)
            "61.8": high - 0.618 * rng,  # entry zone top (bullish)
            "61.8_deep_tp2": high - 0.618 * rng,  # TP2 deep entry
            "70.2": high - 0.702 * rng,  # sweet spot / TP1 deep entry
            "78.6": high - 0.786 * rng,  # deep entry
            "88.6": high - 0.886 * rng,  # deep entry (adjust TPs)
            "100":  low,
            "direction": "bullish",
            "high": high,
            "low":  low,
        }
    else:
        high  = bos["fft_high"]
        low   = bos["fft_low"]
        rng   = high - low
        # Retracement from low back UP:
        # 61.8% retrace = low + 0.618 * rng (price is above low)
        return {
            "0":    low,
            "23.6": low + 0.236 * rng,
            "38.2": low + 0.382 * rng,  # TP2 (normal)
            "50.0": low + 0.500 * rng,  # TP1 (normal)
            "61.8": low + 0.618 * rng,  # entry zone bottom (bearish retracement is UP)
            "61.8_deep_tp2": low + 0.618 * rng,
            "70.2": low + 0.702 * rng,  # sweet spot
            "78.6": low + 0.786 * rng,  # deep entry
            "88.6": low + 0.886 * rng,  # deep entry
            "100":  high,
            "direction": "bearish",
            "high": high,
            "low":  low,
        }


def calc_sniper_levels(bos: dict) -> dict:
    """
    Calculate the Sniper fib levels on the counter move before BOS.

    Bullish counter move: from counter_high DOWN to counter_low
    Sniper measures how far back UP the counter move went before BOS
    50%   of counter move = sniper 50% = Entry 1 (top of green zone)
    38.2% of counter move = sniper 38.2% = Entry 2 (bottom of green zone)

    Bearish counter move: from counter_low UP to counter_high
    Sniper measures how far back DOWN the counter move went before BOS
    Same levels, mirrored.

    Returns dict with green zone boundaries.
    """
    high = bos["counter_high"]
    low  = bos["counter_low"]
    rng  = high - low

    if bos["direction"] == "bullish":
        # Counter move went DOWN (high to low)
        # After BOS, price retraces back DOWN toward this counter move
        # Sniper levels measured FROM the counter high downward
        sniper_50   = high - 0.500 * rng  # Entry 1 — top of green zone
        sniper_38_2 = high - 0.382 * rng  # Entry 2 — bottom of green zone
        sl_price    = sniper_38_2 * (1 - SL_PCT_BEHIND_ZONE)  # 1% below zone bottom
    else:
        # Counter move went UP (low to high)
        # After BOS, price retraces back UP into this counter move
        # Sniper levels measured FROM the counter low upward
        sniper_50   = low + 0.500 * rng   # Entry 1 — bottom of green zone (lower price)
        sniper_38_2 = low + 0.382 * rng   # Entry 2 — top of green zone (higher price)
        sl_price    = sniper_38_2 * (1 + SL_PCT_BEHIND_ZONE)  # 1% above zone top

    return {
        "sniper_50":   sniper_50,    # Entry 1 price
        "sniper_38_2": sniper_38_2,  # Entry 2 price
        "zone_top":    max(sniper_50, sniper_38_2),
        "zone_bottom": min(sniper_50, sniper_38_2),
        "sl":          sl_price,
        "direction":   bos["direction"],
    }


def check_green_zone_overlap(fft: dict, sniper: dict) -> dict | None:
    """
    Check whether the sniper green zone (38.2–50%) overlaps with the
    FFT entry consideration zone (61.8–88.6%).

    This is the CRITICAL check. No overlap = no trade.

    Returns dict with overlap details if valid, None if no overlap.
    """
    direction = fft["direction"]

    if direction == "bullish":
        # In bullish: FFT entry zone = fft[61.8] to fft[88.6] (lower prices, below high)
        fft_zone_top    = fft["61.8"]   # higher price (closest to high)
        fft_zone_bottom = fft["88.6"]   # lower price (deepest retracement)
    else:
        # In bearish: FFT entry zone = fft[61.8] to fft[88.6]
        # (higher prices since measuring UP from low)
        fft_zone_top    = fft["88.6"]   # highest price in entry zone
        fft_zone_bottom = fft["61.8"]   # lowest price in entry zone

    sniper_top    = sniper["zone_top"]
    sniper_bottom = sniper["zone_bottom"]

    # Check overlap: the green zone must intersect with FFT entry zone
    overlap_top    = min(sniper_top, fft_zone_top)
    overlap_bottom = max(sniper_bottom, fft_zone_bottom)

    if overlap_top <= overlap_bottom:
        # No overlap
        return None

    # Overlap confirmed — determine if it's a deep entry
    mid_overlap = (overlap_top + overlap_bottom) / 2
    fft_range   = abs(fft["100"] - fft["0"])

    if fft_range > 0:
        if direction == "bullish":
            retrace_pct = (fft["0"] - mid_overlap) / fft_range
        else:
            retrace_pct = (mid_overlap - fft["0"]) / fft_range
    else:
        retrace_pct = 0.7

    is_deep = retrace_pct >= FFT_DEEP_THRESHOLD

    log.info(f"GREEN ZONE OVERLAP | retrace={retrace_pct:.1%} | "
             f"deep={'YES' if is_deep else 'NO'} | "
             f"overlap={overlap_bottom:.2f}–{overlap_top:.2f}")

    return {
        "overlap_top":    overlap_top,
        "overlap_bottom": overlap_bottom,
        "retrace_pct":    retrace_pct,
        "is_deep":        is_deep,
        "fft_zone_top":   fft_zone_top,
        "fft_zone_bottom": fft_zone_bottom,
    }


def price_in_entry_zone(price: float, fft: dict, sniper: dict) -> bool:
    """True when current price is within the green zone overlap."""
    overlap = check_green_zone_overlap(fft, sniper)
    if not overlap:
        return False
    return overlap["overlap_bottom"] <= price <= overlap["overlap_top"]


# =============================================================================
# TAKE PROFIT CALCULATION
# =============================================================================

def calc_take_profits(fft: dict, overlap: dict) -> tuple:
    """
    Calculate TP1 and TP2 prices based on FFT fib levels.

    Normal entry (< 78.6%): TP1 = FFT 50%, TP2 = FFT 38.2%
    Deep entry  (>= 78.6%): TP1 = FFT 70.2%, TP2 = FFT 61.8%

    In both bullish and bearish:
    - TPs are in the direction of the trade (with the trend)
    - For bullish: TPs are ABOVE entry (higher prices)
    - For bearish: TPs are BELOW entry (lower prices)
    """
    if overlap["is_deep"]:
        tp1_level = fft["70.2"]
        tp2_level = fft["61.8_deep_tp2"]
        tp_label  = "deep (70.2 / 61.8)"
    else:
        tp1_level = fft["50.0"]
        tp2_level = fft["38.2"]
        tp_label  = "normal (50 / 38.2)"

    log.info(f"Take profits: {tp_label} | TP1={tp1_level:.2f} | TP2={tp2_level:.2f}")
    return tp1_level, tp2_level


# =============================================================================
# POSITION MANAGEMENT
# =============================================================================

def manage_positions(open_trades: list, atr: float):
    """
    Manage all open FFT positions:
    - Move to breakeven at 0.5R
    - Close TP1 portion at TP1 level (80% of position — handled at order placement)
    - Trail remaining position after TP1

    Note: TP2 is placed as a hard TP on the order. TP1 requires partial close
    which at 0.01 lots means full close. The bot handles this via order monitoring.
    """
    bid, ask = get_tick()

    for t in open_trades[:]:
        pos = mt5.positions_get(ticket=t["ticket"])
        if not pos:
            open_trades.remove(t)
            continue

        p         = pos[0]
        price     = p.price_current
        entry     = t["entry"]
        sl        = t["sl"]
        direction = t["dir"]
        sl_dist   = abs(entry - sl)

        if sl_dist == 0:
            continue

        # Calculate current profit in R
        if direction == "bullish":
            profit_r = (price - entry) / sl_dist
        else:
            profit_r = (entry - price) / sl_dist

        # Move to breakeven at 0.5R
        if profit_r >= BE_R and not t.get("be_done"):
            ok = modify_sl(t["ticket"], entry)
            if ok:
                t["be_done"] = True
                t["sl"]      = entry
                log.info(f"T{t['ticket']} -> BREAKEVEN @ {entry:.2f} ({profit_r:.2f}R)")


# =============================================================================
# CONFLUENCE SCORING
# =============================================================================

def score_setup(bos: dict, fft: dict, sniper: dict, overlap: dict,
                h1_trend: str, h4_trend: str,
                fvg_present: bool, session: str) -> int:
    """
    Score the FFT setup on a 0–10 scale.

    Core requirements (always needed — handled before scoring):
    - BOS confirmed
    - Green zone overlap confirmed

    Bonus points:
    - H1 trend aligned:  +2
    - H4 trend aligned:  +2
    - FVG at green zone: +2
    - Session kill zone: +1
    - Deep overlap (tight): +1
    - Sniper 50% exact hit: +1
    - H1 + H4 both aligned: +1 extra
    """
    score = 0
    direction = bos["direction"]

    if h1_trend == direction:
        score += 2
    if h4_trend == direction:
        score += 2
    if h1_trend == direction and h4_trend == direction:
        score += 1  # extra for full alignment
    if fvg_present:
        score += 2
    if session in ("london", "ny"):
        score += 1
    if overlap["is_deep"]:
        score += 1  # deep entries have tighter SL

    # Overlap tightness bonus
    overlap_range = overlap["overlap_top"] - overlap["overlap_bottom"]
    sniper_range  = sniper["zone_top"] - sniper["zone_bottom"]
    if sniper_range > 0 and (overlap_range / sniper_range) > 0.7:
        score += 1  # >70% of sniper zone is in FFT zone = very tight confluence

    return score


# =============================================================================
# TREND AND SESSION DETECTION
# =============================================================================

def get_trend(df: pd.DataFrame, ema_period: int = 200) -> str:
    """
    Determine trend direction using EMA.
    Returns 'bullish', 'bearish', or 'neutral'.
    """
    if len(df) < ema_period:
        return "neutral"
    ema   = get_ema(df, ema_period)
    price = float(df["close"].iloc[-1])
    if price > ema:
        return "bullish"
    elif price < ema:
        return "bearish"
    return "neutral"


def detect_fvg(df: pd.DataFrame, direction: str) -> bool:
    """
    Detect a Fair Value Gap (3-candle imbalance) in the trade direction.

    Bullish FVG: candle[-3] high < candle[-1] low (gap up)
    Bearish FVG: candle[-3] low > candle[-1] high (gap down)
    """
    if len(df) < 3:
        return False
    c1, c2, c3 = df.iloc[-3], df.iloc[-2], df.iloc[-1]
    if direction == "bullish":
        return float(c1["high"]) < float(c3["low"])
    else:
        return float(c1["low"]) > float(c3["high"])


def get_session(hour_utc: int) -> str:
    """Return the current trading session name based on UTC hour."""
    if 7 <= hour_utc < 10:
        return "london"
    elif 12 <= hour_utc < 15:
        return "ny"
    elif 20 <= hour_utc < 24 or 0 <= hour_utc < 3:
        return "asian"
    return "other"


# =============================================================================
# MAIN BOT LOOP
# =============================================================================

def run():
    log.info("=" * 65)
    log.info("  BOT 5 — FFT (Fibonacci Fractal Trading) STRATEGY")
    log.info(f"  Symbol: {SYMBOL} | Risk: {RISK_PCT}%")
    log.info(f"  BOS lookback: {SWING_LOOKBACK} candles | "
             f"Entry zone: {FFT_ENTRY_MIN*100:.1f}–{FFT_ENTRY_MAX*100:.1f}%")
    log.info("=" * 65)

    if not connect():
        return

    acct = mt5.account_info()
    if not acct or acct.balance <= 0:
        log.error(f"Account balance is ${acct.balance if acct else 0:.2f}. "
                  "Cannot start. Check credentials and MT5_FFT terminal.")
        mt5.shutdown()
        return

    # Shared components
    regime      = RegimeClassifier(bot_name="BOT_FFT")
    logger      = TradeLogger(str(_INST / "fft_trades.json"))
    ai          = AIBrain(logger, model_file=str(_INST / "fft_model.pkl"))
    calmar      = CalmarTracker(acct.balance,
                                equity_file=str(_INST / "fft_equity.json"))
    daily_log   = DailyLogger(str(_INST / "fft_daily.json"))

    # State
    daily_start       = acct.balance
    weekly_start      = acct.balance
    trades_today      = 0
    max_open_today    = 0
    min_balance_today = acct.balance
    open_trades       = recover_open_positions()
    last_date         = now_utc().date()
    last_week         = now_utc().isocalendar()[1]
    trading_halted    = False
    consec_losses     = 0

    # Weekly persistence
    _week_file = _INST / "fft_weekly.json"
    _cur_week  = now_utc().isocalendar()[1]
    if _week_file.exists():
        import json as _json
        _wd = _json.loads(_week_file.read_text())
        if _wd.get("week") == _cur_week:
            weekly_start = _wd.get("weekly_start", acct.balance)
            log.info(f"Weekly start restored: ${weekly_start:,.2f}")
        else:
            _week_file.write_text(
                _json.dumps({"week": _cur_week, "weekly_start": weekly_start})
            )
    else:
        import json as _json
        _week_file.write_text(
            _json.dumps({"week": _cur_week, "weekly_start": weekly_start})
        )

    log.info(f"Balance ${acct.balance:,.2f} | {ai.status_report()}")

    # Track last detected setup to avoid re-entering same zone
    last_setup_id = None

    try:
        while True:
            now  = now_utc()
            date = now.date()
            week = now.isocalendar()[1]

            # ── Market close force-close ──────────────────────────────────
            if is_market_close() and open_trades:
                reason = "WEEKEND-CLOSE" if now.weekday() >= 4 else "DAILY-CLOSE"
                log.warning(f"MARKET CLOSE [{reason}] — closing {len(open_trades)} position(s)")
                close_all_positions(reason)
                open_trades.clear()

            # ── Dead zone: 3pm-7pm Texas time — no new entries ────────────
            if is_dead_zone():
                handle_dead_zone(open_trades, get_atr(get_candles(TF_ENTRY, 20)))
                if now.minute == 0:
                    log.info("Dead zone (3-7pm TX) — no new FFT entries. Managing open positions.")
                time.sleep(60)
                continue

            # ── Daily reset ───────────────────────────────────────────────
            if date != last_date:
                closed_today = [t for t in logger.get_closed()
                                if t.get("closed_at", "")[:10] == str(last_date)]
                wins   = sum(1 for t in closed_today if t["outcome"] == "win")
                losses = sum(1 for t in closed_today if t["outcome"] == "loss")
                dd     = (daily_start - min_balance_today) / daily_start * 100
                pnl    = (acct.balance - daily_start) / daily_start * 100
                daily_log.record_day(str(last_date), {
                    "total_trades":          trades_today,
                    "wins":                  wins,
                    "losses":                losses,
                    "breakevens":            trades_today - wins - losses,
                    "max_simultaneous_open": max_open_today,
                    "max_drawdown_pct":      round(dd, 2),
                    "final_pnl_pct":         round(pnl, 2),
                    "day_of_week":           last_date.weekday(),
                })
                acct              = mt5.account_info()
                daily_start       = acct.balance
                min_balance_today = acct.balance
                max_open_today    = 0
                trades_today      = 0
                last_date         = date
                last_setup_id     = None
                trading_halted    = False
                calmar.record(acct.balance)
                calmar.log_report()
                log.info(f"New day {date} | ${acct.balance:,.2f} | {ai.status_report()}")

            # ── Weekly reset ──────────────────────────────────────────────
            if week != last_week:
                import json as _json
                weekly_start   = acct.balance
                last_week      = week
                trading_halted = False
                consec_losses  = 0
                _week_file.write_text(
                    _json.dumps({"week": week, "weekly_start": weekly_start})
                )
                log.info(f"New week {week} | Weekly start: ${weekly_start:,.2f}")

            # ── Account refresh with sanity check ─────────────────────────
            acct = mt5.account_info()
            if not acct or acct.balance <= 0:
                log.warning("MT5 returned zero balance — skipping (bad reading).")
                time.sleep(30)
                continue

            max_open_today    = max(max_open_today, len(open_trades))
            min_balance_today = min(min_balance_today, acct.balance)
            daily_pnl_pct     = (acct.balance - daily_start) / daily_start * 100

            # ── Daily loss cap ────────────────────────────────────────────
            daily_dd = (daily_start - acct.balance) / daily_start * 100
            if daily_dd >= MAX_DAILY_LOSS:
                if not trading_halted:
                    log.warning(f"DAILY CAP: -{daily_dd:.1f}%. "
                                "Managing open trades only.")
                    trading_halted = True
                manage_positions(open_trades, 10)
                time.sleep(60)
                continue

            # ── Weekly loss cap ───────────────────────────────────────────
            weekly_dd = (weekly_start - acct.balance) / weekly_start * 100
            if weekly_dd >= MAX_WEEKLY_LOSS:
                if not trading_halted:
                    log.warning(f"WEEKLY CAP: -{weekly_dd:.1f}%. 6hr cooldown.")
                    close_all_positions("weekly-cap")
                    trading_halted = True
                    time.sleep(21600)
                    trading_halted = False
                continue

            if trading_halted:
                trading_halted = False

            # ── Daily trade limit ─────────────────────────────────────────
            if trades_today >= MAX_TRADES_DAY:
                manage_positions(open_trades, 10)
                if now.minute == 0:
                    log.info(f"Daily trade limit {MAX_TRADES_DAY} reached. "
                             "Managing open positions only.")
                time.sleep(60)
                continue

            # ── Get market data ───────────────────────────────────────────
            df_m15 = get_candles(TF_ENTRY,  150)
            df_h1  = get_candles(TF_TREND,   50)
            df_h4  = get_candles(TF_HIGHER,  50)

            if df_m15.empty or df_h1.empty or df_h4.empty:
                time.sleep(30)
                continue

            bid, ask = get_tick()
            price    = (bid + ask) / 2
            atr      = get_atr(df_m15)

            # ── Manage open positions ─────────────────────────────────────
            trades_before = len(open_trades)
            manage_positions(open_trades, atr)
            # Record equity immediately after any trade closes
            if len(open_trades) < trades_before:
                acct = mt5.account_info()
                if acct:
                    calmar.record(acct.balance)

            # ── Trend filters (H1 and H4) ─────────────────────────────────
            h1_trend = get_trend(df_h1, 200)
            h4_trend = get_trend(df_h4, 200)

            if h1_trend == "neutral" or h4_trend == "neutral":
                log.info(f"Trend neutral — H1={h1_trend} H4={h4_trend}. Waiting.")
                time.sleep(60)
                continue

            log.info(f"Scanning | price={price:.2f} | H1={h1_trend} | "
                     f"H4={h4_trend} | ATR={atr:.2f}")

            # ── Regime check ──────────────────────────────────────────────
            reg_state, risk_mult = regime.classify(df_h1, df_h4)
            if reg_state == "RANGING":
                log.info("Regime RANGING — FFT strategy needs trending. Waiting.")
                time.sleep(60)
                continue

            # ── BOS detection on M15 ──────────────────────────────────────
            bos = detect_bos(df_m15, atr)
            if not bos:
                log.info("No BOS detected. Waiting 60s.")
                time.sleep(60)
                continue

            # ── Trend alignment check ─────────────────────────────────────
            if bos["direction"] != h1_trend:
                log.info(f"BOS {bos['direction']} conflicts with H1 {h1_trend}. Skip.")
                time.sleep(60)
                continue

            # ── Generate setup ID to avoid re-entering same zone ──────────
            setup_id = f"{bos['direction']}_{bos['bos_price']:.1f}"
            if setup_id == last_setup_id:
                manage_positions(open_trades, atr)
                time.sleep(60)
                continue

            # ── Calculate FFT and Sniper levels ───────────────────────────
            fft    = calc_fft_levels(bos)
            sniper = calc_sniper_levels(bos)

            log.info(f"BOS {bos['direction'].upper()} @ {bos['bos_price']:.2f} | "
                     f"FFT zone: {fft['61.8']:.2f}–{fft['88.6']:.2f} | "
                     f"Green zone: {sniper['zone_bottom']:.2f}–{sniper['zone_top']:.2f}")

            # ── Check green zone overlap (CRITICAL) ───────────────────────
            overlap = check_green_zone_overlap(fft, sniper)
            if not overlap:
                log.info("No green zone overlap with FFT entry zone. Skip.")
                time.sleep(60)
                continue

            # ── Check if price has retraced INTO the entry zone ───────────
            if not price_in_entry_zone(price, fft, sniper):
                log.info(f"Price {price:.2f} not yet in entry zone "
                         f"({overlap['overlap_bottom']:.2f}–{overlap['overlap_top']:.2f}). "
                         "Waiting for retracement.")
                time.sleep(60)
                continue

            # ── Additional confluence ─────────────────────────────────────
            session   = get_session(now.hour)
            fvg       = detect_fvg(df_m15, bos["direction"])
            score     = score_setup(bos, fft, sniper, overlap,
                                    h1_trend, h4_trend, fvg, session)

            log.info(f"SETUP | {bos['direction'].upper()} | score={score}/10 | "
                     f"session={session} | FVG={fvg} | "
                     f"deep={overlap['is_deep']}")

            # Minimum score: 4 (BOS + overlap + at least H1 alignment)
            if score < 4:
                log.info(f"Score {score} < 4. Insufficient confluence. Skip.")
                time.sleep(60)
                continue

            # ── Calculate TPs ─────────────────────────────────────────────
            tp1_price, tp2_price = calc_take_profits(fft, overlap)

            # Validate TP direction makes sense
            if bos["direction"] == "bullish":
                if tp1_price <= price or tp2_price <= price:
                    log.info("TP levels below entry for bullish trade. Skip.")
                    time.sleep(60)
                    continue
            else:
                if tp1_price >= price or tp2_price >= price:
                    log.info("TP levels above entry for bearish trade. Skip.")
                    time.sleep(60)
                    continue

            # ── AI gate ───────────────────────────────────────────────────
            feats = build_features_trend(
                score, atr, price,
                abs(bos["fft_high"] - bos["fft_low"]),
                session,
                h4_trend == bos["direction"],
                fvg,
                ask - bid,
                float(df_h4["high"].max()),
                float(df_h4["low"].min()),
                logger,
                daily_trades=trades_today,
                daily_pnl_pct=daily_pnl_pct,
                simultaneous_open=len(open_trades),
                is_reentry=False,
            )
            take, ai_prob, ai_reason = ai.should_take_trade(feats, MIN_AI_PROB)
            log.info(f"AI: {ai_reason}")
            if not take:
                time.sleep(60)
                continue

            # ── Entry: sniper 50% (Entry 1) ───────────────────────────────
            entry_price = sniper["sniper_50"]
            sl_price    = sniper["sl"]
            sl_dist     = abs(entry_price - sl_price)

            if sl_dist <= 0:
                log.info("Zero SL distance. Skip.")
                time.sleep(60)
                continue

            rr = abs(tp1_price - entry_price) / sl_dist
            if rr < 1.0:
                log.info(f"R:R {rr:.2f} < 1.0. Skip.")
                time.sleep(60)
                continue

            lots = lot_size(acct.balance, sl_dist, risk_mult)
            if lots <= 0:
                time.sleep(60)
                continue

            log.info(f"SIGNAL | {bos['direction'].upper()} | "
                     f"score={score} | AI={ai_prob:.0%} | "
                     f"entry={entry_price:.2f} SL={sl_price:.2f} | "
                     f"TP1={tp1_price:.2f} TP2={tp2_price:.2f} | "
                     f"R:R={rr:.2f} | lots={lots}")

            # ── Place order ───────────────────────────────────────────────
            ticket, filled = place_order(
                bos["direction"], lots, sl_price, tp1_price,
                comment=f"FFT-E1-s{score}"
            )

            if ticket:
                open_trades.append({
                    "ticket":     ticket,
                    "entry":      filled,
                    "sl":         sl_price,
                    "tp1":        tp1_price,
                    "tp2":        tp2_price,
                    "dir":        bos["direction"],
                    "lots":       lots,
                    "be_done":    False,
                    "tp1_done":   False,
                    "fft_levels": fft,
                    "sniper":     sniper,
                })
                logger.log_entry(ticket, feats, bos["direction"],
                                 filled, sl_price, tp1_price, tp2_price)
                trades_today  += 1
                consec_losses  = 0
                last_setup_id  = setup_id

                log.info(f"Trade #{trades_today} today | FFT setup confirmed.")

                # ── Entry 2: sniper 38.2% if lots allow ───────────────────
                # Only if we can trade 0.02+ lots (otherwise single entry)
                if lots >= 0.02:
                    entry2_price = sniper["sniper_38_2"]
                    lots2        = round(lots * 0.5 / 0.01) * 0.01
                    lots2        = max(0.01, lots2)
                    ticket2, filled2 = place_order(
                        bos["direction"], lots2, sl_price, tp2_price,
                        comment=f"FFT-E2-s{score}"
                    )
                    if ticket2:
                        open_trades.append({
                            "ticket":     ticket2,
                            "entry":      filled2,
                            "sl":         sl_price,
                            "tp1":        tp2_price,
                            "tp2":        tp2_price,
                            "dir":        bos["direction"],
                            "lots":       lots2,
                            "be_done":    False,
                            "tp1_done":   False,
                            "fft_levels": fft,
                            "sniper":     sniper,
                        })
                        logger.log_entry(ticket2, feats, bos["direction"],
                                         filled2, sl_price, tp2_price, tp2_price)
                        log.info(f"Entry 2 placed @ {filled2:.2f} | "
                                 f"TP={tp2_price:.2f} | lots={lots2}")

                time.sleep(300)  # 5 min cooldown after entry
            else:
                consec_losses += 1
                log.warning(f"Order failed. Consecutive: {consec_losses}")
                time.sleep(60)

    except KeyboardInterrupt:
        log.info("Stopped by user.")
    except Exception as e:
        log.exception(f"Unexpected error: {e}")
    finally:
        mt5.shutdown()
        log.info("Bot 5 shut down.")


if __name__ == "__main__":
    print("BOT FFT | XAUUSD Gold (Fibonacci Fractal Trading) | XAUUSD")
    print("Timeframe: M15 | Trend filter: H1 + H4")
    print("Entry: Sniper green zone overlap with FFT 61.8-88.6%\n")
    # Auto-confirm when running non-interactively (coordinator/Task Scheduler)
    # Prompt only when launched directly in a terminal
    import sys as _sys
    if not _sys.stdin.isatty() or input("Type CONFIRM to start: ").strip().upper() == "CONFIRM":
        run()
    else:
        print("Aborted.")
