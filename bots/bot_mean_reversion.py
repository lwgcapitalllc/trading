"""
╔══════════════════════════════════════════════════════════════════════════════╗
║  BOT 2 — XAUUSD MEAN REVERSION (CASH FLOW LAYER)                           ║
║                                                                              ║
║  Strategy : Bollinger Band extremes + RSI + VWAP deviation + rejection     ║
║             candle → fade the extreme, target BB midline                   ║
║  Capital  : 20–40% of total algo allocation                                 ║
║  Style    : Mean reversion (Jason Video 1 — "best cash flow models")       ║
║  Risk     : 0.5% per trade · 2% daily cap · 5% weekly cap                 ║
║  Sessions : 24 hours — active all sessions, higher score in London/NY      ║
║                                                                              ║
║  Key design: INVERTED regime logic vs Bot 1                                 ║
║    Ranging market  = Bot 2 FULL SIZE (ideal conditions)                    ║
║    Trending market = Bot 2 REDUCED SIZE (trend fights reversion)            ║
║                                                                              ║
║  Shared files required (same folder):                                       ║
║    shared_regime.py   — regime classifier                                   ║
║    shared_ai_brain.py — AI win-probability gate + trade logger              ║
║    shared_calmar.py   — live Calmar ratio tracker                           ║
║                                                                              ║
║  Install : pip install MetaTrader5 pandas numpy pytz scikit-learn joblib    ║
║  Run     : python bot_mean_reversion.py                                    ║
╚══════════════════════════════════════════════════════════════════════════════╝
"""

import MetaTrader5 as mt5
import pandas as pd
import numpy as np
import time, json
from datetime import datetime
from pathlib import Path
import pytz

from bot_utils import load_config, setup_logging, get_instance_dir
from shared_regime   import RegimeClassifier
from shared_ai_brain import AIBrain, TradeLogger, DailyLogger, build_features_reversion
from shared_calmar   import CalmarTracker

# ── Load config + logging (instance-aware) ────────────────────────────────────
_CFG     = load_config()
log      = setup_logging("BOT_MEAN_REVERSION", _CFG)
_INST    = get_instance_dir(_CFG)

ACCOUNT         = _CFG["account"]
SYMBOL          = _CFG["symbol"]
MAGIC           = 20240002

# Risk
RISK_PCT        = _CFG["risk"]["risk_pct_bot2"]
MIN_LOT         = _CFG["risk"]["min_lot_size"]
MAX_LOT         = _CFG["risk"]["max_lot_size"]

# Protection
MAX_DAILY_LOSS       = _CFG["protection"]["max_daily_loss_pct_bot2"]
MAX_WEEKLY_LOSS      = _CFG["protection"]["max_weekly_loss_pct_bot2"]
MAX_CONSEC_LOSSES    = _CFG["protection"]["max_consec_losses"]
NEWS_BLACKOUT_MINS   = _CFG["protection"]["news_blackout_minutes"]
NEWS_EVENTS          = _CFG["protection"]["news_events"]
LOSS_COOLDOWN        = {
    1: _CFG["protection"]["cooldown_1_loss_seconds"],
    2: _CFG["protection"]["cooldown_2_loss_seconds"],
    3: _CFG["protection"]["cooldown_3_loss_seconds"],
}

# Bot 2 strategy
_B2             = _CFG["bot_mean_reversion"]
MIN_RR          = _B2["min_rr"]
ATR_PERIOD      = _B2["atr_period"]
ATR_SL_MULT     = _B2["atr_sl_multiplier"]
BB_PERIOD       = _B2["bb_period"]
BB_STD          = _B2["bb_std_entry"]
BB_STD_EXTREME  = _B2["bb_std_extreme"]
RSI_PERIOD      = _B2["rsi_period"]
RSI_OB          = _B2["rsi_overbought"]
RSI_OS          = _B2["rsi_oversold"]
RSI_EXTREME_OB  = _B2["rsi_extreme_ob"]
RSI_EXTREME_OS  = _B2["rsi_extreme_os"]
RSI_NEUTRAL_LO  = _B2["rsi_neutral_low"]
RSI_NEUTRAL_HI  = _B2["rsi_neutral_high"]
VWAP_STD_MULT   = _B2["vwap_std_multiplier"]
MIN_SCORE       = _B2["min_confluence_score"]
MIN_AI_PROB     = _B2["min_ai_probability"]

# Exit management — aggressive profit protection for mean reversion
BE_ACTIVATION_R     = _B2.get("breakeven_at_r",       0.3)   # fast BE
PARTIAL_CLOSE_R     = _B2.get("partial_close_r",       1.0)   # bank 50% at 1R
PARTIAL_CLOSE_PCT   = _B2.get("partial_close_pct",     0.50)
TRAIL_ATR_MULT      = _B2.get("trail_atr_mult",        0.3)   # tight trail after partial

MAX_TRADES_DAY  = 999   # unlimited — daily loss cap governs

log.info(f"Config loaded | symbol={SYMBOL} | risk={RISK_PCT}% | "
         f"daily_cap={MAX_DAILY_LOSS}% | weekly_cap={MAX_WEEKLY_LOSS}%")


# ═════════════════════════════════════════════════════════════════════════════
# MT5 HELPERS
# ═════════════════════════════════════════════════════════════════════════════

def connect():
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
    bot_id      = f"BOT_MEAN_REVERSION_{expected_id}"

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


def get_candles(tf, count):
    r = mt5.copy_rates_from_pos(SYMBOL, tf, 0, count)
    if r is None or len(r) == 0: return pd.DataFrame()
    df = pd.DataFrame(r)
    df["time"] = pd.to_datetime(df["time"], unit="s", utc=True)
    return df

def get_tick():
    t = mt5.symbol_info_tick(SYMBOL)
    return (t.bid, t.ask) if t else (0.0, 0.0)

def now_utc():
    return datetime.now(pytz.utc)

def is_market_close() -> bool:
    """Returns True at 21:45 UTC — 15 min before gold market closes at 22:00 UTC."""
    t = now_utc()
    return (t.hour == 19 and t.minute >= 45) or t.hour == 20

def should_close_for_weekend() -> bool:
    """Friday 21:45 UTC — no reopening until Sunday 22:00 UTC."""
    t = now_utc()
    return t.weekday() == 4 and ((t.hour == 19 and t.minute >= 45) or t.hour == 20)


# ═════════════════════════════════════════════════════════════════════════════
# PROTECTION HELPERS
# ═════════════════════════════════════════════════════════════════════════════


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


def close_all_positions(reason="emergency"):
    positions = mt5.positions_get(symbol=SYMBOL)
    if not positions: return
    log.warning(f"CLOSE ALL — {reason} | {len(positions)} position(s)")
    for pos in positions:
        bid, ask   = get_tick()
        price      = bid if pos.type == mt5.ORDER_TYPE_BUY else ask
        close_type = mt5.ORDER_TYPE_SELL if pos.type == mt5.ORDER_TYPE_BUY else mt5.ORDER_TYPE_BUY
        req = {"action":mt5.TRADE_ACTION_DEAL,"symbol":SYMBOL,"volume":pos.volume,
               "type":close_type,"position":pos.ticket,"price":price,
               "deviation":30,"magic":MAGIC,"comment":f"BOT_MEAN_REVERSION-{reason}",
               "type_time":mt5.ORDER_TIME_GTC,"type_filling":mt5.ORDER_FILLING_IOC}
        res = mt5.order_send(req)
        if res and res.retcode == mt5.TRADE_RETCODE_DONE:
            log.warning(f"  Closed {pos.ticket} @ {price:.2f}")
        else:
            log.error(f"  Failed to close {pos.ticket}: {mt5.last_error()}")

def is_news_blackout():
    now = now_utc()
    for event in NEWS_EVENTS:
        wd, h, m = event[0], event[1], event[2]
        if now.weekday() == wd:
            if abs((now.hour*60 + now.minute) - (h*60 + m)) <= NEWS_BLACKOUT_MINS:
                log.warning(f"News blackout: {h:02d}:{m:02d} UTC +/-{NEWS_BLACKOUT_MINS}min")
                return True
    return False


# ═════════════════════════════════════════════════════════════════════════════
# INDICATORS
# ═════════════════════════════════════════════════════════════════════════════

def calc_bollinger(df, period=BB_PERIOD, std_dev=BB_STD):
    close = df["close"]
    mid   = close.rolling(period).mean()
    std   = close.rolling(period).std()
    return (float((mid + std*std_dev).iloc[-1]),
            float(mid.iloc[-1]),
            float((mid - std*std_dev).iloc[-1]),
            float(std.iloc[-1]))

def calc_rsi(df, period=RSI_PERIOD):
    delta = df["close"].diff()
    gain  = delta.clip(lower=0).rolling(period).mean()
    loss  = (-delta.clip(upper=0)).rolling(period).mean()
    return float((100 - (100 / (1 + gain/(loss+1e-9)))).iloc[-1])

def calc_atr(df, period=ATR_PERIOD):
    h, l, c = df["high"], df["low"], df["close"].shift(1)
    tr = pd.concat([h-l, (h-c).abs(), (l-c).abs()], axis=1).max(axis=1)
    return float(tr.rolling(period).mean().iloc[-1])

def calc_vwap(df):
    """Intraday VWAP — uses today's candles only."""
    today = now_utc().date()
    mask  = df["time"].dt.date == today
    d     = df[mask]
    if len(d) < 5: return None, None
    tp    = (d["high"] + d["low"] + d["close"]) / 3
    vwap  = (tp * d["tick_volume"]).cumsum() / d["tick_volume"].cumsum()
    return float(vwap.iloc[-1]), float((d["close"] - vwap).std())

def calc_stoch_rsi(df, period=14):
    delta = df["close"].diff()
    gain  = delta.clip(lower=0).rolling(period).mean()
    loss  = (-delta.clip(upper=0)).rolling(period).mean()
    rsi   = 100 - (100 / (1 + gain/(loss+1e-9)))
    lo    = rsi.rolling(period).min()
    hi    = rsi.rolling(period).max()
    return float(((rsi - lo) / (hi - lo + 1e-9)).iloc[-1])

def in_active_session():
    """London or NY = higher-confidence sessions for reversion."""
    h = now_utc().hour
    return (7 <= h < 10) or (12 <= h < 15)


# ═════════════════════════════════════════════════════════════════════════════
# SIGNAL DETECTION
# ═════════════════════════════════════════════════════════════════════════════

def detect_reversion_signal(df_m15, df_m5):
    """
    Detect mean reversion setup on M15.
    Bullish (go long after oversold extreme):
      Price below lower BB + RSI oversold + VWAP deviation + rejection candle
    Bearish (go short after overbought extreme):
      Price above upper BB + RSI overbought + VWAP deviation + rejection candle
    Returns signal dict or None.
    """
    if df_m15.empty or len(df_m15) < 30: return None

    bid, ask = get_tick()
    price    = (bid + ask) / 2
    if price == 0: return None

    upper, mid, lower, bb_std = calc_bollinger(df_m15)
    rsi      = calc_rsi(df_m15)
    atr      = calc_atr(df_m15)
    vwap, vstd = calc_vwap(df_m15)
    srsi     = calc_stoch_rsi(df_m5) if not df_m5.empty else 0.5
    active   = in_active_session()
    last     = df_m15.iloc[-1]

    # ── Bullish reversion ─────────────────────────────────────────────────
    score, signals = 0, {}

    if price < lower:
        score += 2; signals["bb"] = f"Below lower BB ({price:.2f} < {lower:.2f})"
        if price < lower - bb_std * 0.5:
            score += 1; signals["bb_extreme"] = "Extreme extension (+1)"

    if rsi < RSI_OS:
        score += 2; signals["rsi"] = f"Oversold RSI={rsi:.1f}"
        if rsi < RSI_EXTREME_OS:
            score += 1; signals["rsi_extreme"] = f"Extreme oversold (+1)"

    if vwap and vstd and price < vwap - vstd * VWAP_STD_MULT:
        score += 1; signals["vwap"] = f"Below VWAP by {(vwap-price)/max(vstd,0.01):.1f}std"

    if last["close"] > last["open"]:
        score += 1; signals["candle"] = "Bullish rejection candle"

    if active:
        score += 1; signals["session"] = "Active session bonus"

    if score >= MIN_SCORE:
        return {"direction":"bullish","score":score,"price":price,"atr":atr,
                "bb_upper":upper,"bb_mid":mid,"bb_lower":lower,"bb_std":bb_std,
                "rsi":rsi,"vwap":vwap,"vstd":vstd,"stoch_rsi":srsi,
                "signals":signals,"tp_target":mid}

    # ── Bearish reversion ─────────────────────────────────────────────────
    score, signals = 0, {}

    if price > upper:
        score += 2; signals["bb"] = f"Above upper BB ({price:.2f} > {upper:.2f})"
        if price > upper + bb_std * 0.5:
            score += 1; signals["bb_extreme"] = "Extreme extension (+1)"

    if rsi > RSI_OB:
        score += 2; signals["rsi"] = f"Overbought RSI={rsi:.1f}"
        if rsi > RSI_EXTREME_OB:
            score += 1; signals["rsi_extreme"] = "Extreme overbought (+1)"

    if vwap and vstd and price > vwap + vstd * VWAP_STD_MULT:
        score += 1; signals["vwap"] = f"Above VWAP by {(price-vwap)/max(vstd,0.01):.1f}std"

    if last["close"] < last["open"]:
        score += 1; signals["candle"] = "Bearish rejection candle"

    if active:
        score += 1; signals["session"] = "Active session bonus"

    if score >= MIN_SCORE:
        return {"direction":"bearish","score":score,"price":price,"atr":atr,
                "bb_upper":upper,"bb_mid":mid,"bb_lower":lower,"bb_std":bb_std,
                "rsi":rsi,"vwap":vwap,"vstd":vstd,"stoch_rsi":srsi,
                "signals":signals,"tp_target":mid}

    return None


# ═════════════════════════════════════════════════════════════════════════════
# ORDER MANAGEMENT
# ═════════════════════════════════════════════════════════════════════════════

def lot_size(balance, sl_dist, regime_mult=1.0):
    si = mt5.symbol_info(SYMBOL)
    if not si or si.trade_tick_size == 0 or sl_dist == 0: return 0.01
    risk  = balance * (RISK_PCT / 100)
    ticks = sl_dist / si.trade_tick_size
    lots  = (risk / (ticks * si.trade_tick_value)) * regime_mult
    # Round DOWN to nearest micro lot (0.01)
    lots  = max(0.01, round(int(lots * 100) / 100, 2))
    # Enforce broker hard limits
    lots  = max(si.volume_min, min(si.volume_max, lots))
    # Round to broker volume step
    lots  = round(round(lots / si.volume_step) * si.volume_step, 2)
    log.info(f"Lot size calculated: {lots} lots (risk=${balance*RISK_PCT/100:.2f} sl={sl_dist:.2f}pts)")
    return lots

def place_order(direction, lots, sl, tp):
    bid, ask = get_tick()
    price    = ask if direction == "bullish" else bid
    otype    = mt5.ORDER_TYPE_BUY if direction == "bullish" else mt5.ORDER_TYPE_SELL
    req = {
        "action":       mt5.TRADE_ACTION_DEAL,
        "symbol":       SYMBOL,
        "volume":       lots,
        "type":         otype,
        "price":        price,
        "sl":           round(sl, 2),
        "tp":           round(tp, 2),
        "deviation":    20,
        "magic":        MAGIC,
        "comment":      "BOT_MEAN_REVERSION-REVERT",
        "type_time":    mt5.ORDER_TIME_GTC,
        "type_filling": mt5.ORDER_FILLING_IOC,
    }
    res = mt5.order_send(req)
    if res and res.retcode == mt5.TRADE_RETCODE_DONE:
        log.info(f"ORDER FILLED | ticket={res.order} | {direction} {lots}L @ {res.price:.2f}")
        return res.order, res.price
    log.error(f"Order failed: {mt5.last_error()}")
    return None, None

def move_sl(ticket, new_sl, tp=None):
    pos = mt5.positions_get(ticket=ticket)
    if not pos: return
    req = {"action":mt5.TRADE_ACTION_SLTP,"symbol":SYMBOL,
           "position":ticket,"sl":round(new_sl, 2),
           "tp":tp if tp else pos[0].tp}
    mt5.order_send(req)

def close_position(ticket, direction, volume=None):
    pos = mt5.positions_get(ticket=ticket)
    if not pos: return False
    p          = pos[0]
    vol        = volume if volume else p.volume
    bid, ask   = get_tick()
    price      = bid if direction == "bullish" else ask
    close_type = mt5.ORDER_TYPE_SELL if direction == "bullish" else mt5.ORDER_TYPE_BUY
    req = {"action":mt5.TRADE_ACTION_DEAL,"symbol":SYMBOL,"volume":vol,
           "type":close_type,"position":ticket,"price":price,
           "deviation":20,"magic":MAGIC,"comment":"BOT_MEAN_REVERSION-CLOSE",
           "type_time":mt5.ORDER_TIME_GTC,"type_filling":mt5.ORDER_FILLING_IOC}
    res = mt5.order_send(req)
    return res and res.retcode == mt5.TRADE_RETCODE_DONE

def partial_close(ticket, close_lots, direction):
    """Close a portion of an open position to bank profit."""
    pos = mt5.positions_get(ticket=ticket)
    if not pos: return False
    si = mt5.symbol_info(SYMBOL)
    if not si: return False
    bid, ask   = get_tick()
    price      = bid if direction == "bullish" else ask
    close_type = mt5.ORDER_TYPE_SELL if direction == "bullish" else mt5.ORDER_TYPE_BUY
    close_lots = round(round(close_lots / si.volume_step) * si.volume_step, 2)
    close_lots = max(si.volume_min, min(close_lots, pos[0].volume))
    req = {
        "action":       mt5.TRADE_ACTION_DEAL,
        "symbol":       SYMBOL,
        "volume":       close_lots,
        "type":         close_type,
        "position":     ticket,
        "price":        price,
        "deviation":    20,
        "magic":        MAGIC,
        "comment":      "BOT_MEAN_REVERSION-PARTIAL",
        "type_time":    mt5.ORDER_TIME_GTC,
        "type_filling": mt5.ORDER_FILLING_IOC,
    }
    res = mt5.order_send(req)
    if res and res.retcode == mt5.TRADE_RETCODE_DONE:
        log.info(f"PARTIAL CLOSE | ticket={ticket} | {close_lots}L @ {price:.2f}")
        return True
    log.error(f"Partial close failed: {mt5.last_error()}")
    return False

def manage_positions(open_trades):
    """
    0.01-lot-safe mean reversion management:
      1. Breakeven at 0.3R (fast)
      2. Full close at 1R — bank the entire trade (works at minimum lot size)
      3. Early close when RSI returns to neutral
      4. Force close everything at 21:45 UTC (15 min before market close)
    """
    # Force close everything before market close
    if is_market_close() and open_trades:
        reason = "WEEKEND-CLOSE" if should_close_for_weekend() else "DAILY-CLOSE"
        log.info(f"Market closing in 15 min — closing all {len(open_trades)} position(s). [{reason}]")
        for t in open_trades[:]:
            pos = mt5.positions_get(ticket=t["ticket"])
            if pos:
                close_position(t["ticket"], t["dir"])
            open_trades.remove(t)
        return

    df_m15 = get_candles(mt5.TIMEFRAME_M15, 30)
    if df_m15.empty: return
    rsi_now = calc_rsi(df_m15)
    atr     = calc_atr(df_m15)

    for t in open_trades[:]:
        pos = mt5.positions_get(ticket=t["ticket"])
        if not pos:
            # Trade closed by broker — check if it was at BE
            if t.get("be_done"):
                log.info(f"T{t['ticket']} stopped at BREAKEVEN. "
                         f"Re-entry available if conditions still met.")
                _last_be_direction[0] = t["dir"]
            open_trades.remove(t)
            continue

        p         = pos[0]
        price     = p.price_current
        direction = t["dir"]
        sl_dist   = abs(t["entry"] - t["sl"])
        if sl_dist == 0: continue

        profit_r = (
            (price - t["entry"]) / sl_dist if direction == "bullish"
            else (t["entry"] - price) / sl_dist
        )

        # Stage 1 — Breakeven at 0.3R (fast)
        if profit_r >= BE_ACTIVATION_R and not t.get("be_done"):
            be = t["entry"]
            if direction == "bullish" and p.sl < be - 0.05:
                move_sl(t["ticket"], be)
                t["be_done"] = True
                log.info(f"T{t['ticket']} -> BREAKEVEN @ {be:.2f} ({profit_r:.2f}R)")
            elif direction == "bearish" and p.sl > be + 0.05:
                move_sl(t["ticket"], be)
                t["be_done"] = True
                log.info(f"T{t['ticket']} -> BREAKEVEN @ {be:.2f} ({profit_r:.2f}R)")

        # Stage 2 — Full close at 1R — bank entire trade
        if profit_r >= PARTIAL_CLOSE_R and not t.get("closed"):
            log.info(f"T{t['ticket']} FULL CLOSE @ {profit_r:.1f}R — banking profit.")
            if close_position(t["ticket"], direction):
                t["closed"] = True
                open_trades.remove(t)
            continue

        # Stage 3 — Tight trail after breakeven
        if t.get("be_done") and not t.get("closed"):
            trail = atr * TRAIL_ATR_MULT
            if direction == "bullish":
                t["peak"] = max(t.get("peak", price), price)
                new_sl    = t["peak"] - trail
                if new_sl > p.sl + 0.05:
                    move_sl(t["ticket"], new_sl)
            else:
                t["peak"] = min(t.get("peak", price), price)
                new_sl    = t["peak"] + trail
                if new_sl < p.sl - 0.05:
                    move_sl(t["ticket"], new_sl)

        # Stage 4 — Early RSI close (mean reached)
        rsi_neutral = RSI_NEUTRAL_LO <= rsi_now <= RSI_NEUTRAL_HI
        if rsi_neutral and profit_r > 0.3 and not t.get("closed"):
            log.info(f"T{t['ticket']} EARLY CLOSE — RSI neutral ({rsi_now:.1f}) | "
                     f"profit={profit_r:.1f}R. Mean reached.")
            if close_position(t["ticket"], direction):
                if t in open_trades:
                    open_trades.remove(t)


# ═════════════════════════════════════════════════════════════════════════════
# POSITION RECOVERY — reconnects to trades open before a restart
# ═════════════════════════════════════════════════════════════════════════════

def recover_open_positions() -> list:
    """
    On startup, scan MT5 for any positions this bot opened previously
    (identified by MAGIC number). Rebuilds the open_trades list so
    position management (breakeven, early RSI close) resumes immediately.
    """
    positions = mt5.positions_get(symbol=SYMBOL)
    if not positions:
        return []

    recovered = []
    for pos in positions:
        if pos.magic != MAGIC:
            continue  # belongs to a different bot or manual trade

        direction = "bullish" if pos.type == mt5.ORDER_TYPE_BUY else "bearish"

        trade = {
            "ticket": pos.ticket,
            "entry":  pos.price_open,
            "sl":     pos.sl,
            "dir":    direction,
        }
        recovered.append(trade)
        log.info(f"RECOVERED position | ticket={pos.ticket} | "
                 f"{direction} {pos.volume}L @ {pos.price_open:.2f} | "
                 f"current P&L=${pos.profit:.2f} | SL={pos.sl:.2f}")

    if recovered:
        log.info(f"Position recovery complete — {len(recovered)} trade(s) resumed.")
    else:
        log.info("Position recovery — no open positions found from previous session.")

    return recovered


# ═════════════════════════════════════════════════════════════════════════════
# MAIN LOOP
# ═════════════════════════════════════════════════════════════════════════════

_last_be_direction = [None]  # mutable container for BE direction tracking


def run():
    log.info("=" * 65)
    log.info("  BOT 2 — MEAN REVERSION — STARTING")
    log.info("=" * 65)
    if not connect(): return

    acct         = mt5.account_info()
    if acct.balance <= 0:
        log.error(f"Account balance is ${acct.balance:.2f} — demo account may have been reset. Please restore balance before running BOT_MEAN_REVERSION.")
        mt5.shutdown(); return
    regime       = RegimeClassifier(bot_name="BOT_MEAN_REVERSION")
    logger       = TradeLogger(str(_INST / "mean_reversion_trades.json"))
    ai           = AIBrain(logger, model_file=str(_INST / "mean_reversion_model.pkl"))
    calmar       = CalmarTracker(acct.balance, equity_file=str(_INST / "gold_main_equity.json"))
    daily_log    = DailyLogger(str(_INST / "mean_reversion_daily.json"))

    daily_start       = acct.balance
    # Load weekly_start from file so restarts don't reset it
    _week_file2 = _INST / "mean_reversion_weekly.json"
    current_week2 = now_utc().isocalendar()[1]
    if _week_file2.exists():
        import json as _json2
        _wdata2 = _json2.loads(_week_file2.read_text())
        if _wdata2.get("week") == current_week2:
            weekly_start = _wdata2.get("weekly_start", acct.balance)
            log.info(f"Weekly start restored: ${weekly_start:,.2f} (week {current_week2})")
        else:
            weekly_start = acct.balance
            _week_file2.write_text(_json2.dumps({"week": current_week2, "weekly_start": weekly_start}))
    else:
        weekly_start = acct.balance
        import json as _json2
        _week_file2.write_text(_json2.dumps({"week": current_week2, "weekly_start": weekly_start}))
    trades_today      = 0
    max_open_today    = 0
    min_balance_today = acct.balance
    open_trades       = recover_open_positions()
    last_date         = now_utc().date()
    last_week         = now_utc().isocalendar()[1]
    consec_losses     = 0
    trading_halted    = False
    # re-entry handled via _last_be_direction module variable

    log.info(f"Balance ${acct.balance:,.2f} | Risk {RISK_PCT}% | "
             f"Daily cap {MAX_DAILY_LOSS}% | Weekly cap {MAX_WEEKLY_LOSS}%")

    try:
        while True:
            now  = now_utc()
            date = now.date()

            # ── Market close — highest priority check ─────────────────────
            if is_market_close() and open_trades:
                reason = "WEEKEND-CLOSE" if should_close_for_weekend() else "DAILY-CLOSE"
                log.warning(f"MARKET CLOSE in 15 min [{reason}] — "
                            f"closing all {len(open_trades)} position(s) now.")
                for t in open_trades[:]:
                    pos = mt5.positions_get(ticket=t["ticket"])
                    if pos:
                        close_position(t["ticket"], t["dir"])
                    if t in open_trades:
                        open_trades.remove(t)
                log.info("Positions closed. Bot stays running — no new entries during close window.")

            # ── Dead zone: 3pm-7pm Texas time — no new entries ────────────
            if is_dead_zone():
                df_tmp = get_candles(mt5.TIMEFRAME_M15, 20)
                handle_dead_zone(open_trades,
                                 calc_atr(df_tmp) if not df_tmp.empty else 10.0)
                if now.minute == 0:
                    log.info("Dead zone (3-7pm TX) — no new entries. Managing open positions.")
                time.sleep(60)
                continue
            if date != last_date:
                # Save yesterday's performance
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
                _last_be_direction[0] = None
                calmar.record(acct.balance)
                calmar.log_report()
                log.info(f"New day {date} | ${acct.balance:,.2f} | {ai.status_report()}")

            # ── Weekly reset ──────────────────────────────────────────────
            week = now.isocalendar()[1]
            if week != last_week:
                weekly_start   = acct.balance
                last_week      = week
                trading_halted = False
                import json as _json2
                _week_file2.write_text(_json2.dumps({"week": week, "weekly_start": weekly_start}))
                log.info(f"New week {week} | Weekly balance reset ${weekly_start:,.2f}")
                consec_losses  = 0
                log.info(f"New week | Weekly balance reset ${weekly_start:,.2f}")

            acct = mt5.account_info()

            # Sanity check — if balance is 0 MT5 returned a bad reading
            # (can happen if wrong terminal responds). Skip this iteration.
            if not acct or acct.balance <= 0:
                log.warning("MT5 returned zero balance — skipping iteration (bad reading).")
                time.sleep(30); continue

            # ── Weekly loss guard — 6hr cooldown then regime check ────────
            weekly_dd = (weekly_start - acct.balance) / weekly_start * 100
            if weekly_dd >= MAX_WEEKLY_LOSS:
                if not trading_halted:
                    log.warning(f"WEEKLY CAP: -{weekly_dd:.1f}%. Closing all. 6hr cooldown.")
                    close_all_positions("weekly-cap")
                    trading_halted = True
                    time.sleep(21600)
                    df_h1 = get_candles(mt5.TIMEFRAME_H1, 60)
                    df_h4 = get_candles(mt5.TIMEFRAME_H4, 50)
                    if not df_h1.empty and not df_h4.empty:
                        regime.classify(df_h1, df_h4)
                    # Bot 2 resumes when regime is ranging or transitioning
                    if regime.current_regime in ("RANGING", "TRANSITIONING"):
                        trading_halted = False
                        consec_losses  = 0
                        log.info(f"Regime={regime.current_regime}. Bot 2 resuming.")
                    else:
                        log.warning("Regime TRENDING. Waiting 1 more hour.")
                        time.sleep(3600)
                    continue
                else:
                    trading_halted = False

            if trading_halted:
                trading_halted = False

            # ── Consecutive loss cooldown ─────────────────────────────────
            if consec_losses > 0 and consec_losses <= MAX_CONSEC_LOSSES:
                cooldown = LOSS_COOLDOWN.get(consec_losses, 10800)
                log.warning(f"{consec_losses} consecutive loss(es). "
                            f"Cooling {cooldown//60} min then regime check.")
                time.sleep(cooldown)
                df_h1 = get_candles(mt5.TIMEFRAME_H1, 60)
                df_h4 = get_candles(mt5.TIMEFRAME_H4, 50)
                if not df_h1.empty and not df_h4.empty:
                    regime.classify(df_h1, df_h4)
                consec_losses = 0
                continue

            # ── News blackout ─────────────────────────────────────────────
            if is_news_blackout():
                time.sleep(60); continue

            # ── Daily loss guard ──────────────────────────────────────────
            dd = (daily_start - acct.balance) / daily_start * 100
            if dd >= MAX_DAILY_LOSS:
                log.warning(f"Daily cap hit ({dd:.1f}%). Managing open trades only.")
                manage_positions(open_trades)
                time.sleep(3600); continue

            # ── Regime check — INVERTED logic for mean reversion ──────────
            if regime.needs_update():
                df_h1 = get_candles(mt5.TIMEFRAME_H1, 60)
                df_h4 = get_candles(mt5.TIMEFRAME_H4, 50)
                if not df_h1.empty and not df_h4.empty:
                    regime.classify(df_h1, df_h4)

            reg_state = regime.current_regime
            # Bot 2 is OPPOSITE to Bot 1:
            # Ranging = ideal (full size), Trending = caution (reduced size)
            if reg_state == "RANGING":
                risk_mult = 1.0
            elif reg_state == "TRANSITIONING":
                risk_mult = 0.75
            else:  # TRENDING
                risk_mult = 0.4
                log.info(f"Regime TRENDING — Bot 2 using 40% size")

            # ── Market data ───────────────────────────────────────────────
            df_m15 = get_candles(mt5.TIMEFRAME_M15, 100)
            df_m5  = get_candles(mt5.TIMEFRAME_M5,   50)
            if df_m15.empty:
                log.warning("No M15 data returned from MT5. Retrying...")
                time.sleep(30); continue

            bid, ask = get_tick()
            price    = (bid + ask) / 2
            log.info(f"Scanning | price={price:.2f} | regime={reg_state} | risk_mult={risk_mult}")

            # ── Manage open positions ─────────────────────────────────────
            trades_before = len(open_trades)
            manage_positions(open_trades)
            if len(open_trades) < trades_before:
                _acct = mt5.account_info()
                if _acct: calmar.record(_acct.balance)

            # ── Signal detection ──────────────────────────────────────────
            signal = detect_reversion_signal(df_m15, df_m5)
            if not signal:
                log.info("No reversion signal — conditions not met. Waiting 60s.")
                time.sleep(60); continue

            log.info(f"REVERSION SIGNAL | {signal['direction'].upper()} | "
                     f"score={signal['score']} | RSI={signal['rsi']:.1f}")
            for k, v in signal["signals"].items():
                log.info(f"  [{k}] {v}")

            # ── Track drawdown metrics ────────────────────────────────────
            max_open_today    = max(max_open_today, len(open_trades))
            min_balance_today = min(min_balance_today, acct.balance)
            daily_pnl_pct     = (acct.balance - daily_start) / daily_start * 100

            # ── Re-entry check ────────────────────────────────────────────
            is_reentry = False
            if (_last_be_direction[0] is not None and
                    _last_be_direction[0] == signal["direction"]):
                is_reentry = True
                log.info(f"RE-ENTRY: price still at extreme after BE stop. "
                         f"Re-entering {signal['direction'].upper()}.")
                _last_be_direction[0] = None

            # ── AI gate ───────────────────────────────────────────────────
            bid, ask = get_tick()
            spread   = ask - bid
            feats    = build_features_reversion(
                signal["score"], signal["atr"], signal["price"],
                signal["rsi"], signal["stoch_rsi"],
                signal["bb_mid"], signal["bb_upper"], signal["bb_lower"],
                signal["vwap"] or signal["price"], spread, logger, reg_state,
                daily_trades=trades_today,
                daily_pnl_pct=daily_pnl_pct,
                simultaneous_open=len(open_trades),
                is_reentry=is_reentry,
            )
            take, ai_prob, ai_reason = ai.should_take_trade(feats, MIN_AI_PROB)
            log.info(f"AI: {ai_reason}")
            if not take:
                time.sleep(60); continue

            # ── Entry, SL, TP ─────────────────────────────────────────────
            direction = signal["direction"]
            atr       = signal["atr"]
            sl_buf    = atr * ATR_SL_MULT
            bid, ask  = get_tick()

            if direction == "bullish":
                entry = ask
                sl    = signal["bb_lower"] - sl_buf
                sl_d  = entry - sl
                tp    = signal["tp_target"]
            else:
                entry = bid
                sl    = signal["bb_upper"] + sl_buf
                sl_d  = sl - entry
                tp    = signal["tp_target"]

            if sl_d <= 0: time.sleep(60); continue

            rr = abs(tp - entry) / sl_d
            if rr < MIN_RR:
                log.info(f"R:R {rr:.2f} < {MIN_RR}. Skip.")
                time.sleep(60); continue

            # ── Position sizing ───────────────────────────────────────────
            lots = lot_size(acct.balance, sl_d, risk_mult)
            if lots <= 0: time.sleep(60); continue

            log.info(f"ENTRY | {direction} | lots={lots} | "
                     f"entry={entry:.2f} SL={sl:.2f} TP={tp:.2f} R:R={rr:.2f}"
                     + (" [RE-ENTRY]" if is_reentry else ""))

            # ── Place order ───────────────────────────────────────────────
            ticket, filled = place_order(direction, lots, sl, tp)

            if ticket:
                open_trades.append({
                    "ticket": ticket,
                    "entry":  filled,
                    "sl":     sl,
                    "dir":    direction,
                    "be_done": False,
                })
                logger.log_entry(ticket, feats, direction, filled, sl, tp, tp,
                                 is_reentry=is_reentry)
                trades_today  += 1
                consec_losses  = 0
                log.info(f"Trade #{trades_today} today.")
                time.sleep(180)
            else:
                consec_losses += 1
                log.warning(f"Order failed. Consecutive issues: {consec_losses}")
                time.sleep(60)

    except KeyboardInterrupt:
        log.info("Stopped by user.")
    except Exception as e:
        log.exception(f"Unexpected error: {e}")
    finally:
        mt5.shutdown()
        log.info("MT5 disconnected.")


if __name__ == "__main__":
    run()
