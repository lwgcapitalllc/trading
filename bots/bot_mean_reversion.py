"""
╔══════════════════════════════════════════════════════════════════════════════╗
║  BOT 2 — MEAN REVERSION — Multi-Instrument Scanner                          ║
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
║  Watchlist (verify exact broker symbol strings on VPS before live):         ║
║    bot_mean_reversion.watchlist in config.json                              ║
║    Default: XAUUSD, EURUSD, AUDUSD, USDCAD, EURGBP                        ║
║                                                                              ║
║  Shared files required (same folder):                                       ║
║    shared_regime.py   — regime classifier                                   ║
║    shared_ai_brain.py — AI win-probability gate + trade logger              ║
║    shared_calmar.py   — live Calmar ratio tracker                           ║
║    shared_scanner.py  — multi-instrument watchlist scanner                  ║
║                                                                              ║
║  Install : pip install MetaTrader5 pandas numpy pytz scikit-learn joblib    ║
║  Run     : python bot_mean_reversion.py                                    ║
╚══════════════════════════════════════════════════════════════════════════════╝
"""

import MetaTrader5 as mt5
import pandas as pd
import numpy as np
import time, json
from datetime import datetime, timedelta
from pathlib import Path

from bot_utils       import load_config, setup_logging, get_instance_dir
from shared_regime   import RegimeClassifier
from shared_ai_brain import AIBrain, TradeLogger, DailyLogger, build_features_reversion
from bot_state       import write_bot, read_bot, set_started
from notify          import send_telegram
from shared_calmar   import CalmarTracker
from shared_scanner  import InstrumentScanner, LearningPhaseGate
from shared_risk     import RiskEngine, CorrelationGuard
from mt5_ops         import (BotMT5, now_utc, is_market_close,
                              should_close_for_weekend, is_dead_zone, get_atr)

# ── Load config + logging (instance-aware) ────────────────────────────────────
_CFG     = load_config()
log      = setup_logging("BOT_MEAN_REVERSION", _CFG)
_INST    = get_instance_dir(_CFG)

ACCOUNT         = _CFG["account"]
SYMBOL          = _CFG["symbol"]   # kept as fallback default
MAGIC           = 20240002

# Watchlist — falls back to single symbol if not configured
_B2      = _CFG["bot_mean_reversion"]
WATCHLIST          = _B2.get("watchlist", [SYMBOL])
LEARNING_WATCHLIST = _B2.get("learning_watchlist", WATCHLIST[:2])
LEARNING_MAX_OPEN  = _B2.get("learning_max_open", 1)
MIN_ATR_RATIO      = _B2.get("min_atr_ratio", 0.8)
FORCE_TRADE        = _B2.get("force_trade", False)
CORR_ACTION        = _B2.get("correlation_action", "block")

# Risk
RISK_PCT        = _CFG["risk"]["risk_pct_bot2"]
MIN_LOT         = _CFG["risk"]["min_lot_size"]
MAX_LOT         = _CFG["risk"]["max_lot_size"]

# Protection
MAX_DAILY_LOSS       = _CFG["protection"]["max_daily_loss_pct_bot2"]
DAILY_BUDGET_PCT     = _B2.get("daily_budget_pct", MAX_DAILY_LOSS)
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

# Exit management
BE_ACTIVATION_R   = _B2.get("breakeven_at_r",     0.3)
PARTIAL_CLOSE_R   = _B2.get("partial_close_r",     1.0)
PARTIAL_CLOSE_PCT = _B2.get("partial_close_pct",   0.50)
TRAIL_ATR_MULT    = _B2.get("trail_atr_mult",       0.3)

log.info(f"Config loaded | watchlist={WATCHLIST} | risk={RISK_PCT}% | "
         f"daily_cap={MAX_DAILY_LOSS}% | weekly_cap={MAX_WEEKLY_LOSS}%")

_mt5 = BotMT5(SYMBOL, MAGIC, "BOT_MEAN_REVERSION", _CFG, ACCOUNT, log)


# ═════════════════════════════════════════════════════════════════════════════
# MT5 HELPERS — delegates to shared BotMT5 instance
# ═════════════════════════════════════════════════════════════════════════════

def connect():                         return _mt5.connect()
def get_candles(tf, n, symbol=None):   return _mt5.get_candles(tf, n, symbol)
def get_tick(symbol=None):             return _mt5.get_tick(symbol)
def get_deal_result(t):                return _mt5.get_deal_result(t)
def close_position(t, d, r=""):        return _mt5.close_position(t, d, r)
def close_all_positions(r="emergency", symbols=None):
    return _mt5.close_all_positions(r, symbols or WATCHLIST)
def move_sl(t, sl, tp=None):           return _mt5.move_sl(t, sl, tp)
def handle_dead_zone(ot, atr, logger, ai): return _mt5.handle_dead_zone(ot, atr, logger, ai)
def reconcile_on_startup(ot, logger, ai): return _mt5.reconcile_on_startup(ot, logger, ai)


# ═════════════════════════════════════════════════════════════════════════════
# PROTECTION HELPERS
# ═════════════════════════════════════════════════════════════════════════════

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
# SIGNAL DETECTION (per-symbol)
# ═════════════════════════════════════════════════════════════════════════════

def detect_reversion_signal(df_m15, df_m5, symbol: str) -> dict | None:
    """
    Detect mean reversion setup on M15 for the given symbol.
    Bullish: price below lower BB + RSI oversold + VWAP deviation + rejection candle
    Bearish: price above upper BB + RSI overbought + VWAP deviation + rejection candle
    Returns signal dict or None.
    """
    if df_m15.empty or len(df_m15) < 30: return None

    bid, ask = get_tick(symbol)
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
                "signals":signals,"tp_target":mid,"bid":bid,"ask":ask}

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
                "signals":signals,"tp_target":mid,"bid":bid,"ask":ask}

    return None


# ═════════════════════════════════════════════════════════════════════════════
# SETUP DETECTION — called by InstrumentScanner per symbol
# ═════════════════════════════════════════════════════════════════════════════

def detect_setup(symbol: str) -> dict | None:
    """
    Evaluate a single symbol for a mean reversion setup.
    Called by InstrumentScanner.scan() for each watchlist symbol.
    Returns a setup dict (with "score" key) or None.
    """
    df_m15 = get_candles(mt5.TIMEFRAME_M15, 100, symbol)
    df_m5  = get_candles(mt5.TIMEFRAME_M5,   50, symbol)
    if df_m15.empty:
        return None
    return detect_reversion_signal(df_m15, df_m5, symbol)


# ═════════════════════════════════════════════════════════════════════════════
# ORDER MANAGEMENT — delegates to shared BotMT5 instance
# ═════════════════════════════════════════════════════════════════════════════

def lot_size(balance, sl_dist, regime_mult=1.0, symbol=None, risk_pct=None):
    """Position size. risk_pct overrides RISK_PCT * regime_mult when provided."""
    rp = risk_pct if risk_pct is not None else RISK_PCT * regime_mult
    return _mt5.lot_size(balance, sl_dist, rp, 1.0, symbol)

def place_order(direction, lots, sl, tp, symbol=None):
    """Place a market order; returns (ticket, fill_price) or (None, None)."""
    return _mt5.place_order(direction, lots, sl, tp,
                            comment="BOT_MEAN_REVERSION-REVERT", symbol=symbol)

def partial_close(ticket, close_lots, direction):
    """Close a portion of an open position to bank profit; returns True on success."""
    return _mt5.partial_close(ticket, close_lots, direction)

def manage_positions(open_trades, logger, ai):
    """
    0.01-lot-safe mean reversion management across all open trades (any symbol):
      1. Breakeven at 0.3R (fast)
      2. Full close at 1R — bank the entire trade
      3. Early close when RSI returns to neutral (checked per trade's symbol)
      4. Force close everything at 21:45 UTC (15 min before market close)

    ATR for trailing uses t["atr"] stored at entry, or falls back to live fetch.
    """
    if is_market_close() and open_trades:
        reason = "WEEKEND-CLOSE" if should_close_for_weekend() else "DAILY-CLOSE"
        log.info(f"Market closing in 15 min — closing all {len(open_trades)} position(s). [{reason}]")
        for t in open_trades[:]:
            pos = mt5.positions_get(ticket=t["ticket"])
            if pos:
                ok, cp, pnl = close_position(t["ticket"], t["dir"])
                if ok:
                    logger.log_close(t["ticket"], cp, pnl)
                    ai.on_trade_closed(t["ticket"], cp, pnl)
            open_trades.remove(t)
        return

    for t in open_trades[:]:
        sym = t.get("symbol", SYMBOL)

        pos = mt5.positions_get(ticket=t["ticket"])
        if not pos:
            cp, pnl = get_deal_result(t["ticket"])
            if cp:
                logger.log_close(t["ticket"], cp, pnl)
                ai.on_trade_closed(t["ticket"], cp, pnl)
                if t.get("be_done"):
                    log.info(f"T{t['ticket']} stopped at BREAKEVEN. "
                             f"Re-entry available if conditions still met.")
                    _last_be_direction[0] = t["dir"]
                open_trades.remove(t)
            else:
                t["_missing_count"] = t.get("_missing_count", 0) + 1
                if t["_missing_count"] >= 3:
                    log.warning(
                        f"T{t['ticket']} missing from MT5 for 3 consecutive checks "
                        "with no deal history — marking orphaned."
                    )
                    logger.mark_orphaned(t["ticket"])
                    open_trades.remove(t)
                else:
                    log.warning(
                        f"T{t['ticket']} not found in MT5 "
                        f"({t['_missing_count']}/3 checks) — "
                        "possible connection glitch, retaining."
                    )
            continue

        t["_missing_count"] = 0
        p         = pos[0]
        price     = p.price_current
        direction = t["dir"]
        sl_dist   = abs(t["entry"] - t["sl"])
        if sl_dist == 0: continue

        profit_r = (
            (price - t["entry"]) / sl_dist if direction == "bullish"
            else (t["entry"] - price) / sl_dist
        )

        # ATR: stored at entry, or fetch fresh if missing
        atr = t.get("atr")
        if not atr:
            df_tmp = get_candles(mt5.TIMEFRAME_M15, 30, sym)
            atr    = calc_atr(df_tmp) if not df_tmp.empty else 10.0

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
            ok, cp, pnl = close_position(t["ticket"], direction)
            if ok:
                logger.log_close(t["ticket"], cp, pnl)
                ai.on_trade_closed(t["ticket"], cp, pnl)
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

        # Stage 4 — Early RSI close (per trade's symbol)
        df_tmp     = get_candles(mt5.TIMEFRAME_M15, 30, sym)
        rsi_now    = calc_rsi(df_tmp) if not df_tmp.empty else 50.0
        rsi_neutral = RSI_NEUTRAL_LO <= rsi_now <= RSI_NEUTRAL_HI
        if rsi_neutral and profit_r > 0.3 and not t.get("closed"):
            log.info(f"T{t['ticket']} EARLY CLOSE — RSI neutral ({rsi_now:.1f}) | "
                     f"profit={profit_r:.1f}R. Mean reached.")
            ok, cp, pnl = close_position(t["ticket"], direction)
            if ok:
                logger.log_close(t["ticket"], cp, pnl)
                ai.on_trade_closed(t["ticket"], cp, pnl)
                if t in open_trades:
                    open_trades.remove(t)


# ═════════════════════════════════════════════════════════════════════════════
# POSITION RECOVERY — reconnects to trades open before a restart
# ═════════════════════════════════════════════════════════════════════════════

def recover_open_positions() -> list:
    """
    On startup, scan MT5 for any positions this bot opened previously
    across all watchlist symbols (identified by MAGIC number).
    """
    recovered = []
    for symbol in WATCHLIST:
        positions = mt5.positions_get(symbol=symbol)
        if not positions:
            continue
        for pos in positions:
            if pos.magic != MAGIC:
                continue
            direction = "bullish" if pos.type == mt5.ORDER_TYPE_BUY else "bearish"
            trade = {
                "ticket": pos.ticket,
                "entry":  pos.price_open,
                "sl":     pos.sl,
                "dir":    direction,
                "symbol": symbol,
            }
            recovered.append(trade)
            log.info(f"RECOVERED position | ticket={pos.ticket} | symbol={symbol} | "
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

_last_be_direction = [None]


def run():
    log.info("=" * 65)
    log.info("  BOT 2 — MEAN REVERSION — STARTING")
    log.info(f"  Watchlist: {WATCHLIST}")
    log.info("=" * 65)
    set_started("mean_reversion")
    send_telegram("🟢 *Mean Reversion online*")
    if not connect(): return

    acct = mt5.account_info()
    if acct.balance <= 0:
        log.error(f"Account balance is ${acct.balance:.2f} — demo account may have been "
                  "reset. Please restore balance before running BOT_MEAN_REVERSION.")
        mt5.shutdown(); return

    regime       = RegimeClassifier(bot_name="BOT_MEAN_REVERSION")
    logger       = TradeLogger(str(_INST / "mean_reversion_trades.json"))
    ai           = AIBrain(logger, model_file=str(_INST / "mean_reversion_model.pkl"))
    calmar       = CalmarTracker(acct.balance, equity_file=str(_INST / "gold_main_equity.json"))
    daily_log    = DailyLogger(str(_INST / "mean_reversion_daily.json"))
    scanner       = InstrumentScanner(WATCHLIST, "BOT_MEAN_REVERSION", "mean_reversion",
                                      _INST, log,
                                      min_atr_ratio=MIN_ATR_RATIO, force_trade=FORCE_TRADE)
    risk_engine   = RiskEngine("BOT_MEAN_REVERSION", DAILY_BUDGET_PCT, log)
    corr_guard    = CorrelationGuard(_CFG.get("correlation_map", []), log)
    learning_gate = LearningPhaseGate(LEARNING_WATCHLIST, LEARNING_MAX_OPEN, log)

    daily_start       = acct.balance
    _week_file2       = _INST / "mean_reversion_weekly.json"
    current_week2     = now_utc().isocalendar()[1]
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
    reconcile_on_startup(open_trades, logger, ai)
    risk_engine.reset_day(acct.balance)
    last_date         = now_utc().date()
    last_week         = now_utc().isocalendar()[1]
    consec_losses     = 0
    trading_halted    = False

    log.info(f"Balance ${acct.balance:,.2f} | Risk {RISK_PCT}% | "
             f"Daily cap {MAX_DAILY_LOSS}% | Weekly cap {MAX_WEEKLY_LOSS}%")

    try:
        while True:
            now  = now_utc()
            date = now.date()
            write_bot("mean_reversion", {"heartbeat": time.time()})

            # ── Market close — highest priority check ─────────────────────
            if is_market_close() and open_trades:
                reason = "WEEKEND-CLOSE" if should_close_for_weekend() else "DAILY-CLOSE"
                log.warning(f"MARKET CLOSE in 15 min [{reason}] — "
                            f"closing all {len(open_trades)} position(s) now.")
                for t in open_trades[:]:
                    pos = mt5.positions_get(ticket=t["ticket"])
                    if pos:
                        ok, cp, pnl = close_position(t["ticket"], t["dir"])
                        if ok:
                            logger.log_close(t["ticket"], cp, pnl)
                            ai.on_trade_closed(t["ticket"], cp, pnl)
                    if t in open_trades:
                        open_trades.remove(t)
                log.info("Positions closed. Bot stays running — no new entries during close window.")

            # ── Dead zone: 3pm-7pm Texas time — no new entries ────────────
            if is_dead_zone():
                df_tmp = get_candles(mt5.TIMEFRAME_M15, 20)
                handle_dead_zone(open_trades,
                                 calc_atr(df_tmp) if not df_tmp.empty else 10.0, logger, ai)
                if now.minute == 0:
                    log.info("Dead zone (3-7pm TX) — no new entries. Managing open positions.")
                time.sleep(60)
                continue

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
                _last_be_direction[0] = None
                risk_engine.reset_day(acct.balance)
                calmar.record(acct.balance)
                calmar.log_report()
                # Reset unresolved symbol alerts for new day
                write_bot("mean_reversion", {"unresolved_symbols_alerted": {}})
                log.info(f"New day {date} | ${acct.balance:,.2f} | {ai.status_report()}")
                last_date = date

            # ── Weekly reset ──────────────────────────────────────────────
            week = now.isocalendar()[1]
            if week != last_week:
                weekly_start   = acct.balance
                last_week      = week
                trading_halted = False
                import json as _json2
                _week_file2.write_text(_json2.dumps({"week": week, "weekly_start": weekly_start}))
                log.info(f"New week {week} | Weekly balance reset ${weekly_start:,.2f}")
                consec_losses = 0

            acct = mt5.account_info()

            if not acct or acct.balance <= 0:
                log.warning("MT5 returned zero balance — skipping iteration (bad reading).")
                time.sleep(30); continue

            write_bot("mean_reversion", {
                "balance":      acct.balance,
                "status":       "running",
                "weekly_start": weekly_start,
                "daily_start":  daily_start,
                "last_write":   datetime.utcnow().isoformat(),
            })

            # ── Weekly loss guard ─────────────────────────────────────────
            weekly_dd = (weekly_start - acct.balance) / weekly_start * 100
            if weekly_dd >= MAX_WEEKLY_LOSS:
                if not trading_halted:
                    log.warning(f"WEEKLY CAP: -{weekly_dd:.1f}%. Closing all. 6hr cooldown.")
                    close_all_positions("weekly-cap")
                    trading_halted = True
                    write_bot("mean_reversion", {
                        "day_locked":     True,
                        "lock_reason":    f"WEEKLY CAP: -{weekly_dd:.1f}% weekly loss",
                        "lock_alerted":   False,
                        "resume_trading": False,
                    })
                    cooldown_end = datetime.utcnow() + timedelta(hours=6)
                    while datetime.utcnow() < cooldown_end:
                        if read_bot("mean_reversion").get("resume_trading"):
                            write_bot("mean_reversion", {"day_locked": False, "resume_trading": False})
                            log.warning("WEEKLY CAP RESUME: user override — resuming early.")
                            trading_halted = False
                            break
                        write_bot("mean_reversion", {"heartbeat": time.time()})
                        time.sleep(60)
                    else:
                        write_bot("mean_reversion", {"day_locked": False})
                    df_h1 = get_candles(mt5.TIMEFRAME_H1, 60)
                    df_h4 = get_candles(mt5.TIMEFRAME_H4, 50)
                    if not df_h1.empty and not df_h4.empty:
                        regime.classify(df_h1, df_h4)
                    if regime.current_regime in ("RANGING", "TRANSITIONING"):
                        trading_halted = False
                        consec_losses  = 0
                        log.info(f"Regime={regime.current_regime}. Bot 2 resuming.")
                    else:
                        log.warning("Regime TRENDING. Waiting 1 more hour.")
                        for _ in range(60):
                            time.sleep(60)
                            write_bot("mean_reversion", {"heartbeat": time.time()})
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
                manage_positions(open_trades, logger, ai)
                write_bot("mean_reversion", {
                    "day_locked":     True,
                    "lock_reason":    f"DAILY CAP: -{dd:.1f}% daily loss",
                    "lock_alerted":   False,
                    "resume_trading": False,
                })
                for _ in range(60):
                    time.sleep(60)
                    write_bot("mean_reversion", {"heartbeat": time.time()})
                    if read_bot("mean_reversion").get("resume_trading"):
                        write_bot("mean_reversion", {"day_locked": False, "resume_trading": False})
                        log.warning("DAILY CAP RESUME: user override — resuming early.")
                        break
                else:
                    write_bot("mean_reversion", {"day_locked": False})
                continue

            # ── Regime check — INVERTED logic for mean reversion ──────────
            if regime.needs_update():
                df_h1 = get_candles(mt5.TIMEFRAME_H1, 60)
                df_h4 = get_candles(mt5.TIMEFRAME_H4, 50)
                if not df_h1.empty and not df_h4.empty:
                    regime.classify(df_h1, df_h4)

            reg_state = regime.current_regime
            if reg_state == "RANGING":
                risk_mult = 1.0
            elif reg_state == "TRANSITIONING":
                risk_mult = 0.75
            else:  # TRENDING
                risk_mult = 0.4
                log.info(f"Regime TRENDING — Bot 2 using 40% size")

            # ── Track metrics ─────────────────────────────────────────────
            max_open_today    = max(max_open_today, len(open_trades))
            min_balance_today = min(min_balance_today, acct.balance)
            daily_pnl_pct     = (acct.balance - daily_start) / daily_start * 100

            bid_primary, ask_primary = get_tick()
            price_primary = (bid_primary + ask_primary) / 2
            log.info(f"Scanning watchlist {WATCHLIST} | regime={reg_state} | "
                     f"risk_mult={risk_mult}")

            # ── Manage open positions ─────────────────────────────────────
            trades_before = len(open_trades)
            manage_positions(open_trades, logger, ai)
            if len(open_trades) < trades_before:
                _acct = mt5.account_info()
                if _acct:
                    acct = _acct
                    calmar.record(acct.balance)

            # ── Risk capacity gate (Phase 3) ───────────────────────────────
            proposed_risk = RISK_PCT * risk_mult
            _allowed, effective_risk = risk_engine.evaluate(open_trades, acct.balance, proposed_risk)
            if not _allowed:
                time.sleep(60); continue

            # ── Phase 5: learning-phase gate ──────────────────────────────
            if not learning_gate.check_max_open(open_trades, ai):
                time.sleep(60); continue
            _active_watchlist = learning_gate.active_watchlist(WATCHLIST, ai)

            # ── Multi-instrument scan ─────────────────────────────────────
            candidates = scanner.scan(detect_setup, watchlist=_active_watchlist)
            if not candidates:
                log.info("No reversion signal on any watchlist instrument. Waiting 60s.")
                time.sleep(60); continue

            # ── Correlation filter (Phase 4) ──────────────────────────────
            _budget_risk = effective_risk
            best = None
            for _cand in candidates:
                _ok, effective_risk = corr_guard.check(
                    _cand.symbol, open_trades, _budget_risk, CORR_ACTION, acct.balance
                )
                if _ok:
                    best = _cand
                    break
            if best is None:
                log.info("CorrelationGuard: all candidates blocked — waiting 60s.")
                time.sleep(60); continue

            symbol = best.symbol
            signal = best.setup

            log.info(f"Best reversion: {symbol} | {signal['direction'].upper()} | "
                     f"score={signal['score']} | RSI={signal['rsi']:.1f}")
            for k, v in signal["signals"].items():
                log.info(f"  [{k}] {v}")

            # ── Re-entry check ────────────────────────────────────────────
            is_reentry = False
            if (_last_be_direction[0] is not None and
                    _last_be_direction[0] == signal["direction"]):
                is_reentry = True
                log.info(f"RE-ENTRY: price still at extreme after BE stop. "
                         f"Re-entering {signal['direction'].upper()} on {symbol}.")
                _last_be_direction[0] = None

            # ── AI gate ───────────────────────────────────────────────────
            bid, ask = signal["bid"], signal["ask"]
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

            # Ensure SL distance is at least 1× ATR. When price barely crosses
            # the BB the raw sl_d can be near-zero, producing an enormous lot count.
            min_sl_d = atr * ATR_SL_MULT
            if sl_d < min_sl_d:
                sl_d = min_sl_d
                sl   = entry - sl_d if direction == "bullish" else entry + sl_d

            rr = abs(tp - entry) / sl_d
            if rr < MIN_RR:
                log.info(f"R:R {rr:.2f} < {MIN_RR}. Skip.")
                time.sleep(60); continue

            # ── Position sizing ───────────────────────────────────────────
            lots = lot_size(acct.balance, sl_d, risk_mult, symbol, risk_pct=effective_risk)
            if lots <= 0: time.sleep(60); continue

            log.info(f"ENTRY | {symbol} | {direction} | lots={lots} | "
                     f"entry={entry:.2f} SL={sl:.2f} TP={tp:.2f} R:R={rr:.2f}"
                     + (" [RE-ENTRY]" if is_reentry else ""))

            # ── Place order ───────────────────────────────────────────────
            ticket, filled = place_order(direction, lots, sl, tp, symbol)

            if ticket:
                open_trades.append({
                    "ticket":  ticket,
                    "entry":   filled,
                    "sl":      sl,
                    "dir":     direction,
                    "symbol":  symbol,
                    "atr":     atr,
                    "be_done": False,
                    "lots":    lots,
                })
                risk_usd = acct.balance * (RISK_PCT / 100)
                logger.log_entry(ticket, feats, direction, filled, sl, tp, tp,
                                 is_reentry=is_reentry, risk_usd=risk_usd)
                trades_today  += 1
                consec_losses  = 0
                log.info(f"Trade #{trades_today} today on {symbol}.")
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
