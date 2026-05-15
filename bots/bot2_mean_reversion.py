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
║  Run     : python bot2_mean_reversion.py                                    ║
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
from shared_ai_brain import AIBrain, TradeLogger, build_features_reversion
from shared_calmar   import CalmarTracker

# ── Load config + logging (instance-aware) ────────────────────────────────────
_CFG     = load_config()
log      = setup_logging("BOT2", _CFG)
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
_B2             = _CFG["bot2_reversion"]
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
    if not mt5.initialize():
        log.error(f"MT5 init failed: {mt5.last_error()}"); return False
    if not mt5.login(ACCOUNT["login"], password=ACCOUNT["password"], server=ACCOUNT["server"]):
        log.error(f"Login failed: {mt5.last_error()}"); mt5.shutdown(); return False
    info = mt5.account_info()
    log.info(f"Connected | #{info.login} | ${info.balance:,.2f} | {info.server}")
    return True

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
               "deviation":30,"magic":MAGIC,"comment":f"BOT2-{reason}",
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
        "comment":      "BOT2-REVERT",
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
           "deviation":20,"magic":MAGIC,"comment":"BOT2-CLOSE",
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
        "comment":      "BOT2-PARTIAL",
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

def run():
    log.info("=" * 65)
    log.info("  BOT 2 — MEAN REVERSION — STARTING")
    log.info("=" * 65)
    if not connect(): return

    acct         = mt5.account_info()
    regime       = RegimeClassifier(bot_name="BOT2")
    logger       = TradeLogger(str(_INST / "bot2_trades.json"))
    ai           = AIBrain(logger, model_file=str(_INST / "bot2_model.pkl"))
    calmar       = CalmarTracker(acct.balance, equity_file=str(_INST / "bot2_equity.json"))

    daily_start  = acct.balance
    weekly_start = acct.balance
    trades_today = 0
    open_trades  = recover_open_positions()   # ← resume any trades from before restart
    last_date    = now_utc().date()
    last_week    = now_utc().isocalendar()[1]
    consec_losses= 0
    trading_halted = False

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
            if date != last_date:
                acct         = mt5.account_info()
                daily_start  = acct.balance
                trades_today = 0
                last_date    = date
                calmar.record(acct.balance)
                calmar.log_report()
                log.info(f"New day {date} | ${acct.balance:,.2f}")

            # ── Weekly reset ──────────────────────────────────────────────
            week = now.isocalendar()[1]
            if week != last_week:
                weekly_start   = acct.balance
                last_week      = week
                trading_halted = False
                consec_losses  = 0
                log.info(f"New week | Weekly balance reset ${weekly_start:,.2f}")

            acct = mt5.account_info()

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
            manage_positions(open_trades)

            # ── Signal detection ──────────────────────────────────────────
            signal = detect_reversion_signal(df_m15, df_m5)
            if not signal:
                log.info("No reversion signal — conditions not met. Waiting 60s.")
                time.sleep(60); continue

            log.info(f"REVERSION SIGNAL | {signal['direction'].upper()} | "
                     f"score={signal['score']} | RSI={signal['rsi']:.1f}")
            for k, v in signal["signals"].items():
                log.info(f"  [{k}] {v}")

            # ── AI gate ───────────────────────────────────────────────────
            bid, ask = get_tick()
            spread   = ask - bid
            feats    = build_features_reversion(
                signal["score"], signal["atr"], signal["price"],
                signal["rsi"], signal["stoch_rsi"],
                signal["bb_mid"], signal["bb_upper"], signal["bb_lower"],
                signal["vwap"] or signal["price"], spread, logger, reg_state
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
                     f"entry={entry:.2f} SL={sl:.2f} TP={tp:.2f} R:R={rr:.2f} "
                     f"regime_mult={risk_mult}")

            # ── Place order ───────────────────────────────────────────────
            ticket, filled = place_order(direction, lots, sl, tp)

            if ticket:
                open_trades.append({
                    "ticket": ticket,
                    "entry":  filled,
                    "sl":     sl,
                    "dir":    direction,
                })
                logger.log_entry(ticket, feats, direction, filled, sl, tp, tp)
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
    print("BOT 2 -- Mean Reversion | XAUUSD")
    print("Always test on DEMO first. Never skip this step.")
    print("")
    if input("Type CONFIRM to start: ").strip().upper() == "CONFIRM":
        run()
    else:
        print("Aborted.")
