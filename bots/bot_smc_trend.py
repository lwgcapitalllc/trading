"""
╔══════════════════════════════════════════════════════════════════════════════╗
║  BOT SMC TREND — XAUUSD Gold Spot                                          ║
║                                                                              ║
║  Strategy : Asian range build → Judas Swing sweep → FVG entry              ║
║             London + NY kill zones only                                     ║
║  Capital  : 60–80% of total algo allocation                                 ║
║  Style    : Trend following / momentum (Jason Video 1)                      ║
║  Risk     : 1% per trade · 3% daily cap · 6% weekly cap                    ║
║  Exits    : 50% partial close at 3R · runner trails dynamically             ║
║                                                                              ║
║  Shared files required (same folder):                                       ║
║    shared_regime.py   — regime classifier                                   ║
║    shared_ai_brain.py — AI win-probability gate + trade logger              ║
║    shared_calmar.py   — live Calmar ratio tracker                           ║
║                                                                              ║
║  Install : pip install MetaTrader5 pandas numpy pytz scikit-learn joblib    ║
║  Run     : python bot_smc_trend.py                                         ║
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
from shared_ai_brain import AIBrain, TradeLogger, DailyLogger, build_features_trend
from shared_calmar   import CalmarTracker
from bot_state       import write_bot, read_bot, set_started
from notify          import send_telegram
from mt5_ops         import (BotMT5, now_utc, is_market_close,
                              should_close_for_weekend, is_dead_zone, get_atr, get_ema)

# ── Load config + logging (instance-aware) ────────────────────────────────────
_CFG     = load_config()
log      = setup_logging("BOT_SMC_TREND", _CFG)
_INST    = get_instance_dir(_CFG)

ACCOUNT         = _CFG["account"]
SYMBOL          = _CFG["symbol"]
MAGIC           = 20240001

# Risk
RISK_PCT        = _CFG["risk"]["risk_pct_bot1"]
MIN_LOT         = _CFG["risk"]["min_lot_size"]
MAX_LOT         = _CFG["risk"]["max_lot_size"]

# Protection
MAX_DAILY_LOSS  = _CFG["protection"]["max_daily_loss_pct_bot1"]
MAX_WEEKLY_LOSS = _CFG["protection"]["max_weekly_loss_pct_bot1"]
MAX_CONSEC_LOSSES    = _CFG["protection"]["max_consec_losses"]
NEWS_BLACKOUT_MINS   = _CFG["protection"]["news_blackout_minutes"]
NEWS_EVENTS          = _CFG["protection"]["news_events"]
LOSS_COOLDOWN        = {
    1: _CFG["protection"]["cooldown_1_loss_seconds"],
    2: _CFG["protection"]["cooldown_2_loss_seconds"],
    3: _CFG["protection"]["cooldown_3_loss_seconds"],
}

# Bot 1 strategy
_B1             = _CFG["bot_smc_trend"]
MIN_RR          = _B1["min_rr"]
ATR_PERIOD      = _B1["atr_period"]
ATR_SL_MULT     = _B1["atr_sl_multiplier"]
EMA_TREND       = _B1["ema_trend_period"]
MIN_SCORE       = _B1["min_confluence_score"]
MIN_AI_PROB     = _B1["min_ai_probability"]
PARTIAL_CLOSE_R = _B1["partial_close_r"]
PARTIAL_CLOSE_PCT    = _B1["partial_close_pct"]
RUNNER_KEY_LEVEL_EXIT = _B1["runner_key_level_exit"]
RUNNER_SESSION_EXIT   = _B1["runner_session_exit"]
RUNNER_TRAIL_R  = {
    0: _B1["runner_trail_wide"],
    5: _B1["runner_trail_mid"],
    8: _B1["runner_trail_tight"],
}

# Kill zones
LONDON  = ((_B1["london_kz_start_utc"], 0), (_B1["london_kz_end_utc"], 0))
NY      = ((_B1["ny_kz_start_utc"],     0), (_B1["ny_kz_end_utc"],     0))

MAX_TRADES_DAY  = 999   # unlimited — daily loss cap governs

log.info(f"Config loaded | symbol={SYMBOL} | risk={RISK_PCT}% | "
         f"daily_cap={MAX_DAILY_LOSS}% | weekly_cap={MAX_WEEKLY_LOSS}%")

_mt5 = BotMT5(SYMBOL, MAGIC, "BOT_SMC_TREND", _CFG, ACCOUNT, log)


# ═════════════════════════════════════════════════════════════════════════════
# MT5 HELPERS — delegates to shared BotMT5 instance
# ═════════════════════════════════════════════════════════════════════════════

def connect():              return _mt5.connect()
def get_candles(tf, n):     return _mt5.get_candles(tf, n)
def get_tick():             return _mt5.get_tick()
def get_deal_result(t):     return _mt5.get_deal_result(t)
def close_position(t, d, r=""): return _mt5.close_position(t, d, r)
def close_all_positions(r="emergency"): return _mt5.close_all_positions(r)
def move_sl(t, sl, tp=None): return _mt5.move_sl(t, sl, tp)
def handle_dead_zone(ot, atr, logger, ai): return _mt5.handle_dead_zone(ot, atr, logger, ai)
def reconcile_on_startup(ot, logger, ai): return _mt5.reconcile_on_startup(ot, logger, ai)

def in_kill_zone() -> str | None:
    """Return 'london', 'ny', or None based on current kill zone."""
    t = now_utc()
    m = t.hour * 60 + t.minute
    if LONDON[0][0]*60 <= m < LONDON[1][0]*60: return "london"
    if NY[0][0]*60    <= m < NY[1][0]*60:      return "ny"
    return None

def is_ny_session_close() -> bool:
    """True from 3 PM UTC onward — runner exits and session-end logic."""
    return now_utc().hour >= 15


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
# STRATEGY SIGNALS
# ═════════════════════════════════════════════════════════════════════════════

def get_asian_range(df_m15):
    now   = now_utc()
    end   = now.replace(hour=0, minute=0, second=0, microsecond=0)
    start = end - timedelta(hours=4)
    mask  = (df_m15["time"] >= start) & (df_m15["time"] < end)
    s     = df_m15[mask]
    if len(s) < 4: return None
    return float(s["high"].max()), float(s["low"].min())

def detect_sweep(df_m15, asian_high, asian_low):
    """Detect Judas Swing — wick through Asian range that closes back inside."""
    for c in df_m15.tail(8).iloc[::-1].itertuples():
        # Bullish sweep: wick below Asian low, close back above
        if c.low < asian_low and c.close > asian_low and (asian_low - c.low) > 0.3:
            return {"direction":"bullish","swept":asian_low,"extreme":c.low,"time":c.time}
        # Bearish sweep: wick above Asian high, close back below
        if c.high > asian_high and c.close < asian_high and (c.high - asian_high) > 0.3:
            return {"direction":"bearish","swept":asian_high,"extreme":c.high,"time":c.time}
    return None

def detect_fvg(df_m5):
    """Fair Value Gap — 3-candle imbalance pattern on M5."""
    r = df_m5.tail(20).reset_index(drop=True)
    for i in range(len(r)-1, 1, -1):
        c0, c2 = r.iloc[i-2], r.iloc[i]
        if c0["high"] < c2["low"]:
            return {"type":"bullish","top":c2["low"],"bottom":c0["high"],
                    "mid":(c2["low"]+c0["high"])/2}
        if c0["low"] > c2["high"]:
            return {"type":"bearish","top":c0["low"],"bottom":c2["high"],
                    "mid":(c0["low"]+c2["high"])/2}
    return None

def score_setup(sweep, fvg, h4_trend, kz, price):
    s, reasons = 0, []
    if sweep:
        s += 2; reasons.append("sweep(+2)")
    if fvg:
        if sweep and fvg["type"] == sweep["direction"]:
            s += 2; reasons.append("FVG-aligned(+2)")
        else:
            s += 1; reasons.append("FVG(+1)")
    if kz in ("london","ny"):
        s += 1; reasons.append(f"{kz}(+1)")
    if sweep and h4_trend == sweep["direction"]:
        s += 2; reasons.append("H4-aligned(+2)")
    else:
        s -= 1; reasons.append("H4-counter(-1)")
    if fvg and abs(price - fvg["mid"]) < 1.0:
        s += 1; reasons.append("at-FVG-mid(+1)")
    log.info(f"Confluence score {s}/8 | {' | '.join(reasons)}")
    return s


# ═════════════════════════════════════════════════════════════════════════════
# ORDER MANAGEMENT — delegates to shared BotMT5 instance
# ═════════════════════════════════════════════════════════════════════════════

def lot_size(balance, sl_dist, regime_mult=1.0):
    """Position size using fixed RISK_PCT with optional regime multiplier."""
    return _mt5.lot_size(balance, sl_dist, RISK_PCT, regime_mult)

def place_order(direction, lots, sl, tp):
    """Place a market order; returns (ticket, fill_price) or (None, None)."""
    return _mt5.place_order(direction, lots, sl, tp, comment="BOT_SMC-SMC")

def partial_close(ticket, close_lots, direction):
    """Close a portion of an open position; returns True on success."""
    return _mt5.partial_close(ticket, close_lots, direction)

def get_dynamic_trail_mult(profit_r):
    for threshold in sorted(RUNNER_TRAIL_R.keys(), reverse=True):
        if profit_r >= threshold:
            return RUNNER_TRAIL_R[threshold]
    return 2.0

def get_key_levels(df_h4):
    """Weekly high/low from last 5 H4 candles as runner exit targets."""
    if df_h4 is None or df_h4.empty: return []
    return [
        float(df_h4["high"].tail(5).max()),
        float(df_h4["low"].tail(5).min()),
    ]

def manage_positions(open_trades, atr, logger, ai, df_h4=None):
    """
    0.01-lot-safe profit management:
      1. Breakeven at 1R
      2. Full close at 2R — bank the entire trade (works at minimum lot size)
      3. Keep only the single best trade as a runner with dynamic trail
      4. Force close everything at 21:45 UTC (15 min before market close)
      5. Runner exits at weekly key levels
    """
    key_levels  = get_key_levels(df_h4)
    mkt_close   = is_market_close()

    # Force close everything 15 min before market close
    if mkt_close and open_trades:
        reason = "WEEKEND-CLOSE" if should_close_for_weekend() else "DAILY-CLOSE"
        log.info(f"Market closing in 15 min — closing all {len(open_trades)} position(s). [{reason}]")
        for t in open_trades[:]:
            pos = mt5.positions_get(ticket=t["ticket"])
            if pos:
                ok, cp, pnl = close_position(t["ticket"], t["dir"], reason)
                if ok:
                    logger.log_close(t["ticket"], cp, pnl)
                    ai.on_trade_closed(t["ticket"], cp, pnl)
            open_trades.remove(t)
        return

    # Find the best performing open trade to keep as runner
    best_ticket = None
    best_r      = -999
    for t in open_trades:
        pos = mt5.positions_get(ticket=t["ticket"])
        if not pos: continue
        sl_dist = abs(t["entry"] - t["sl"])
        if sl_dist == 0: continue
        p = pos[0]
        profit_r = (
            (p.price_current - t["entry"]) / sl_dist if t["dir"] == "bullish"
            else (t["entry"] - p.price_current) / sl_dist
        )
        if profit_r > best_r:
            best_r      = profit_r
            best_ticket = t["ticket"]

    for t in open_trades[:]:
        pos = mt5.positions_get(ticket=t["ticket"])
        if not pos:
            # Trade was closed by broker (stop loss hit)
            cp, pnl = get_deal_result(t["ticket"])
            if cp:
                logger.log_close(t["ticket"], cp, pnl)
                ai.on_trade_closed(t["ticket"], cp, pnl)
            # Check if it was at breakeven — if so, flag for re-entry
            if t.get("be_done"):
                log.info(f"T{t['ticket']} stopped at BREAKEVEN. "
                         f"Re-entry available if bias unchanged.")
                # Store setup details globally for re-entry check
                manage_positions._last_be_setup = {
                    "direction": t["dir"],
                    "entry":     t["entry"],
                }
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

        # Stage 1 — Breakeven at 1R
        if profit_r >= 1.0:
            if direction == "bullish" and p.sl < t["entry"] - 0.05:
                move_sl(t["ticket"], t["entry"])
                log.info(f"T{t['ticket']} -> BREAKEVEN @ {t['entry']:.2f}")
            elif direction == "bearish" and p.sl > t["entry"] + 0.05:
                move_sl(t["ticket"], t["entry"])
                log.info(f"T{t['ticket']} -> BREAKEVEN @ {t['entry']:.2f}")

        # Stage 2 — Full close at 2R for non-runner trades
        # Keep the best performing trade as the runner
        if profit_r >= 2.0 and t["ticket"] != best_ticket:
            log.info(f"T{t['ticket']} FULL CLOSE @ {profit_r:.1f}R — banking profit. "
                     f"(runner kept: T{best_ticket})")
            ok, cp, pnl = close_position(t["ticket"], direction, "2R-BANK")
            if ok:
                logger.log_close(t["ticket"], cp, pnl)
                ai.on_trade_closed(t["ticket"], cp, pnl)
                open_trades.remove(t)
            continue

        # Stage 3 — Runner management (best trade only)
        if t["ticket"] == best_ticket and profit_r >= 2.0:
            if not t.get("runner_active"):
                t["runner_active"] = True
                t["peak"]          = price
                log.info(f"T{t['ticket']} RUNNER active @ {profit_r:.1f}R")

        if t.get("runner_active"):
            trail_mult = get_dynamic_trail_mult(profit_r)
            trail_dist = atr * trail_mult

            if direction == "bullish":
                t["peak"] = max(t.get("peak", price), price)
                runner_sl = t["peak"] - trail_dist
                if runner_sl > p.sl + 0.05:
                    move_sl(t["ticket"], runner_sl)
                    log.info(f"T{t['ticket']} RUNNER trail SL={runner_sl:.2f} "
                             f"(peak={t['peak']:.2f} {trail_mult}×ATR)")
            else:
                t["peak"] = min(t.get("peak", price), price)
                runner_sl = t["peak"] + trail_dist
                if runner_sl < p.sl - 0.05:
                    move_sl(t["ticket"], runner_sl)
                    log.info(f"T{t['ticket']} RUNNER trail SL={runner_sl:.2f}")

            # Key level exit
            if RUNNER_KEY_LEVEL_EXIT:
                for level in key_levels:
                    if direction == "bullish" and price >= level - 0.5:
                        log.info(f"T{t['ticket']} RUNNER -> weekly high {level:.2f}. Closing.")
                        ok, cp, pnl = close_position(t["ticket"], direction, "KEY-LEVEL")
                        if ok:
                            logger.log_close(t["ticket"], cp, pnl)
                            ai.on_trade_closed(t["ticket"], cp, pnl)
                        if t in open_trades: open_trades.remove(t)
                        break
                    elif direction == "bearish" and price <= level + 0.5:
                        log.info(f"T{t['ticket']} RUNNER -> weekly low {level:.2f}. Closing.")
                        ok, cp, pnl = close_position(t["ticket"], direction, "KEY-LEVEL")
                        if ok:
                            logger.log_close(t["ticket"], cp, pnl)
                            ai.on_trade_closed(t["ticket"], cp, pnl)
                        if t in open_trades: open_trades.remove(t)
                        break


# ═════════════════════════════════════════════════════════════════════════════
# POSITION RECOVERY — reconnects to trades open before a restart
# ═════════════════════════════════════════════════════════════════════════════

def recover_open_positions() -> list:
    """
    On startup, scan MT5 for any positions this bot opened previously
    (identified by MAGIC number). Rebuilds the open_trades list so the
    trailing stop and partial close logic resumes immediately.

    For recovered trades we don't know the original entry SL distance,
    so we recalculate it from the current broker SL on the position.
    Partial close is assumed NOT done yet for safety — better to bank
    profit twice than miss it.
    """
    positions = mt5.positions_get(symbol=SYMBOL)
    if not positions:
        return []

    recovered = []
    for pos in positions:
        if pos.magic != MAGIC:
            continue  # belongs to a different bot or manual trade

        direction = "bullish" if pos.type == mt5.ORDER_TYPE_BUY else "bearish"
        entry     = pos.price_open
        sl        = pos.sl

        # Recalculate SL distance from broker position
        sl_dist = abs(entry - sl) if sl and sl != 0 else 0

        trade = {
            "ticket":       pos.ticket,
            "entry":        entry,
            "sl":           sl,
            "dir":          direction,
            "peak":         pos.price_current,
            "partial_done": False,   # assume not done — safer to re-check
        }
        recovered.append(trade)
        log.info(f"RECOVERED position | ticket={pos.ticket} | "
                 f"{direction} {pos.volume}L @ {entry:.2f} | "
                 f"current P&L=${pos.profit:.2f} | SL={sl:.2f}")

    if recovered:
        log.info(f"Position recovery complete — {len(recovered)} trade(s) resumed.")
    else:
        log.info("Position recovery — no open positions found from previous session.")

    return recovered


# ═════════════════════════════════════════════════════════════════════════════
# MAIN LOOP
# ═════════════════════════════════════════════════════════════════════════════

manage_positions._last_be_setup = None


def run():
    log.info("=" * 65)
    log.info("  BOT SMC TREND — STARTING")
    log.info("=" * 65)
    set_started("smc_trend")
    send_telegram("🟢 *SMC Trend online*")
    if not connect(): return

    acct         = mt5.account_info()
    if acct.balance <= 0:
        log.error(f"Account balance is ${acct.balance:.2f} — demo account may have been reset. Please restore balance before running BOT_SMC.")
        mt5.shutdown(); return
    regime       = RegimeClassifier(bot_name="BOT_SMC_TREND")
    logger       = TradeLogger(str(_INST / "smc_trend_trades.json"))
    ai           = AIBrain(logger, model_file=str(_INST / "smc_trend_model.pkl"))
    calmar       = CalmarTracker(acct.balance, equity_file=str(_INST / "gold_main_equity.json"))
    daily_log    = DailyLogger(str(_INST / "smc_trend_daily.json"))

    daily_start  = acct.balance
    # Load weekly_start from equity file so restarts don't reset it
    # Only reset weekly_start if it's a new week
    _eq_file = _INST / "gold_main_equity.json"
    _week_file = _INST / "smc_trend_weekly.json"
    current_week = now_utc().isocalendar()[1]
    if _week_file.exists():
        import json as _json
        _wdata = _json.loads(_week_file.read_text())
        if _wdata.get("week") == current_week:
            weekly_start = _wdata.get("weekly_start", acct.balance)
            log.info(f"Weekly start restored: ${weekly_start:,.2f} (week {current_week})")
        else:
            weekly_start = acct.balance
            _week_file.write_text(_json.dumps({"week": current_week, "weekly_start": weekly_start}))
            log.info(f"New week {current_week} — weekly start: ${weekly_start:,.2f}")
    else:
        weekly_start = acct.balance
        import json as _json
        _week_file.write_text(_json.dumps({"week": current_week, "weekly_start": weekly_start}))
        log.info(f"Week file created — weekly start: ${weekly_start:,.2f}")
    trades_today = 0
    max_open_today    = 0
    min_balance_today = acct.balance
    open_trades  = recover_open_positions()
    reconcile_on_startup(open_trades, logger, ai)
    last_date    = now_utc().date()
    last_week    = now_utc().isocalendar()[1]
    consec_losses= 0
    trading_halted = False
    last_be_setup    = None   # tracks setup details after a breakeven stop

    log.info(f"Balance ${acct.balance:,.2f} | Risk {RISK_PCT}% | "
             f"Daily cap {MAX_DAILY_LOSS}% | Weekly cap {MAX_WEEKLY_LOSS}%")

    try:
        while True:
            now  = now_utc()
            date = now.date()
            write_bot("smc_trend", {"heartbeat": time.time()})

            # ── Market close — highest priority check ─────────────────────
            # Runs every loop iteration so it can never be missed
            if is_market_close() and open_trades:
                reason = "WEEKEND-CLOSE" if should_close_for_weekend() else "DAILY-CLOSE"
                log.warning(f"MARKET CLOSE in 15 min [{reason}] — "
                            f"closing all {len(open_trades)} position(s) now.")
                for t in open_trades[:]:
                    pos = mt5.positions_get(ticket=t["ticket"])
                    if pos:
                        ok, cp, pnl = close_position(t["ticket"], t["dir"], reason)
                        if ok:
                            logger.log_close(t["ticket"], cp, pnl)
                            ai.on_trade_closed(t["ticket"], cp, pnl)
                    if t in open_trades:
                        open_trades.remove(t)
                log.info("Positions closed. Bot stays running — no new entries during close window.")

            # ── Dead zone: 3pm-7pm Texas time — no new entries ────────────
            # Profitable trades moved to breakeven, losing trades closed
            if is_dead_zone():
                handle_dead_zone(open_trades, get_atr(get_candles(mt5.TIMEFRAME_M15, 20)), logger, ai)
                if now.minute == 0:
                    log.info("Dead zone (3-7pm TX) — no new entries. Managing open positions.")
                time.sleep(60)
                continue

            # ── Daily reset ───────────────────────────────────────────────
            if date != last_date:
                # Save yesterday's performance before resetting
                closed_today = [t for t in logger.get_closed()
                                if t.get("closed_at", "")[:10] == str(last_date)]
                wins  = sum(1 for t in closed_today if t["outcome"] == "win")
                losses= sum(1 for t in closed_today if t["outcome"] == "loss")
                dd    = (daily_start - min_balance_today) / daily_start * 100
                pnl   = (acct.balance - daily_start) / daily_start * 100
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
                last_be_setup     = None
                last_date         = date
                calmar.record(acct.balance)
                calmar.log_report()
                log.info(f"New day {date} | ${acct.balance:,.2f} | "
                         f"{ai.status_report()}")

            # ── Weekly reset ──────────────────────────────────────────────
            week = now.isocalendar()[1]
            if week != last_week:
                weekly_start   = acct.balance
                last_week      = week
                trading_halted = False
                consec_losses  = 0
                import json as _json
                _week_file.write_text(_json.dumps({"week": week, "weekly_start": weekly_start}))
                log.info(f"New week {week} | Weekly balance reset ${weekly_start:,.2f}")

            acct = mt5.account_info()

            # Sanity check — if balance is 0 MT5 returned a bad reading
            if not acct or acct.balance <= 0:
                log.warning("MT5 returned zero balance — skipping iteration (bad reading).")
                time.sleep(30); continue

            # Publish ground-truth balance so pnl_tracker and /balance stay accurate
            write_bot("smc_trend", {
                "balance":      acct.balance,
                "status":       "running",
                "weekly_start": weekly_start,
                "daily_start":  daily_start,
                "last_write":   datetime.utcnow().isoformat(),
            })

            # ── Weekly loss guard — 6hr cooldown + regime check ───────────
            weekly_dd = (weekly_start - acct.balance) / weekly_start * 100
            if weekly_dd >= MAX_WEEKLY_LOSS:
                if not trading_halted:
                    log.warning(f"WEEKLY CAP: -{weekly_dd:.1f}%. Closing all. 6hr cooldown.")
                    close_all_positions("weekly-cap")
                    trading_halted = True
                    write_bot("smc_trend", {
                        "day_locked":     True,
                        "lock_reason":    f"WEEKLY CAP: -{weekly_dd:.1f}% weekly loss",
                        "lock_alerted":   False,
                        "resume_trading": False,
                    })
                    cooldown_end = datetime.utcnow() + timedelta(hours=6)
                    while datetime.utcnow() < cooldown_end:
                        if read_bot("smc_trend").get("resume_trading"):
                            write_bot("smc_trend", {"day_locked": False, "resume_trading": False})
                            log.warning("WEEKLY CAP RESUME: user override — resuming early.")
                            trading_halted = False
                            break
                        time.sleep(60)
                    else:
                        write_bot("smc_trend", {"day_locked": False})
                    df_h1 = get_candles(mt5.TIMEFRAME_H1, 60)
                    df_h4 = get_candles(mt5.TIMEFRAME_H4, 50)
                    if not df_h1.empty and not df_h4.empty:
                        regime.classify(df_h1, df_h4)
                    ok, _, reason = regime.is_trade_allowed()
                    if ok:
                        trading_halted = False
                        consec_losses  = 0
                        log.info(f"Regime OK ({reason}). Resuming.")
                    else:
                        log.warning(f"Regime still bad ({reason}). Waiting 1hr.")
                        for _ in range(60):
                            time.sleep(60)
                            write_bot("smc_trend", {"heartbeat": time.time()})
                    continue
                else:
                    trading_halted = False

            if trading_halted:
                trading_halted = False

            # ── Consecutive loss cooldown — escalating, never permanent ───
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
                df_m15 = get_candles(mt5.TIMEFRAME_M15, 50)
                df_h4  = get_candles(mt5.TIMEFRAME_H4,  50)
                if not df_m15.empty:
                    manage_positions(open_trades, get_atr(df_m15),
                                     logger, ai, df_h4 if not df_h4.empty else None)
                for _ in range(60):
                    time.sleep(60)
                    write_bot("smc_trend", {"heartbeat": time.time()})
                continue

            # ── Kill zone gate ────────────────────────────────────────────
            kz = in_kill_zone()
            if not kz:
                now_h = now_utc().hour
                # Log once per hour when outside kill zone so we know bot is alive
                if now_utc().minute == 0:
                    log.info(f"Outside kill zone (UTC {now_h:02d}:00) — waiting. "
                             f"London opens 07:00, NY opens 12:00")
                if open_trades:
                    df_m15 = get_candles(mt5.TIMEFRAME_M15, 50)
                    df_h4  = get_candles(mt5.TIMEFRAME_H4,  50)
                    if not df_m15.empty:
                        manage_positions(open_trades, get_atr(df_m15),
                                         logger, ai, df_h4 if not df_h4.empty else None)
                time.sleep(60); continue

            log.info(f"In {kz.upper()} kill zone — scanning for setup...")

            # ── Regime check (every hour) ─────────────────────────────────
            if regime.needs_update():
                df_h1 = get_candles(mt5.TIMEFRAME_H1, 60)
                df_h4 = get_candles(mt5.TIMEFRAME_H4, 50)
                if not df_h1.empty and not df_h4.empty:
                    regime.classify(df_h1, df_h4)

            ok, risk_mult, reason = regime.is_trade_allowed()
            if not ok:
                log.info(f"Regime block: {reason}")
                time.sleep(60); continue

            # ── Track max simultaneous open and min balance ───────────────
            max_open_today    = max(max_open_today, len(open_trades))
            min_balance_today = min(min_balance_today, acct.balance)
            daily_pnl_pct     = (acct.balance - daily_start) / daily_start * 100

            # ── Market data ───────────────────────────────────────────────
            df_m15 = get_candles(mt5.TIMEFRAME_M15, 100)
            df_h4  = get_candles(mt5.TIMEFRAME_H4,   50)
            df_m5  = get_candles(mt5.TIMEFRAME_M5,   50)
            if df_m15.empty or df_h4.empty or df_m5.empty:
                time.sleep(30); continue

            bid, ask = get_tick()
            price    = (bid + ask) / 2
            atr      = get_atr(df_m15)
            ema200   = get_ema(df_h4, EMA_TREND)
            h4_trend = "bullish" if price > ema200 else "bearish"
            log.info(f"Scanning | price={price:.2f} | H4={h4_trend} | ATR={atr:.2f}")

            # ── Manage open positions every loop ──────────────────────────
            trades_before = len(open_trades)
            manage_positions(open_trades, atr, logger, ai, df_h4)
            if len(open_trades) < trades_before:
                _acct = mt5.account_info()
                if _acct: calmar.record(_acct.balance)

            # ── Asian range ───────────────────────────────────────────────
            ar = get_asian_range(df_m15)
            if not ar:
                log.info("No Asian range found — not enough candles. Waiting 60s.")
                time.sleep(60); continue
            asian_high, asian_low = ar
            log.info(f"Asian range: H={asian_high:.2f} L={asian_low:.2f} | "
                     f"price={price:.2f} {'ABOVE' if price > asian_high else 'BELOW' if price < asian_low else 'INSIDE'} range")

            # ── Judas Swing detection ─────────────────────────────────────
            sweep = detect_sweep(df_m15, asian_high, asian_low)
            if not sweep:
                log.info("No Judas Swing detected — no sweep of Asian range. Waiting 60s.")
                time.sleep(60); continue

            # ── Hard H4 trend filter — only trade WITH the trend ──────────
            if sweep["direction"] != h4_trend:
                log.info(f"H4 FILTER: sweep={sweep['direction']} but H4={h4_trend}. "
                         f"Counter-trend entry blocked.")
                time.sleep(60); continue

            # ── FVG detection ─────────────────────────────────────────────
            fvg = detect_fvg(df_m5)

            # ── Confluence score ──────────────────────────────────────────
            score = score_setup(sweep, fvg, h4_trend, kz, price)
            if score < MIN_SCORE:
                log.info(f"Score {score} < {MIN_SCORE}. Skip.")
                time.sleep(60); continue

            # ── Re-entry check ────────────────────────────────────────────
            # If last trade was a breakeven stop-out and bias still valid,
            # allow one re-entry with same setup direction
            is_reentry = False
            be_setup = manage_positions._last_be_setup
            if (be_setup is not None and
                    be_setup["direction"] == sweep["direction"] and
                    h4_trend == sweep["direction"]):
                is_reentry = True
                log.info(f"RE-ENTRY: bias unchanged after BE stop. "
                         f"Same direction {sweep['direction'].upper()}. Allowing re-entry.")
                manage_positions._last_be_setup = None  # one re-entry per setup

            # ── AI gate ───────────────────────────────────────────────────
            feats = build_features_trend(
                score, atr, price,
                abs(sweep["extreme"] - sweep["swept"]),
                kz, h4_trend == sweep["direction"],
                fvg is not None, ask - bid,
                float(df_h4["high"].iloc[-1]),
                float(df_h4["low"].iloc[-1]),
                logger,
                daily_trades=trades_today,
                daily_pnl_pct=daily_pnl_pct,
                simultaneous_open=len(open_trades),
                is_reentry=is_reentry,
            )
            take, ai_prob, ai_reason = ai.should_take_trade(feats, MIN_AI_PROB)
            log.info(f"AI: {ai_reason}")
            if not take: time.sleep(60); continue

            # ── Entry, SL, TP ─────────────────────────────────────────────
            direction = sweep["direction"]
            sl_buf    = atr * ATR_SL_MULT

            if direction == "bullish":
                entry  = ask
                sl     = sweep["extreme"] - sl_buf
                sl_d   = entry - sl
                tp     = entry + sl_d * MIN_RR
            else:
                entry  = bid
                sl     = sweep["extreme"] + sl_buf
                sl_d   = sl - entry
                tp     = entry - sl_d * MIN_RR

            if sl_d <= 0 or abs(tp - entry) / sl_d < MIN_RR:
                log.info("R:R check failed. Skip."); time.sleep(60); continue

            # ── Position sizing (adjusted by regime multiplier) ───────────
            lots = lot_size(acct.balance, sl_d, risk_mult)
            if lots <= 0: time.sleep(60); continue

            log.info(f"SIGNAL | {direction.upper()} | score={score} | "
                     f"AI={ai_prob:.0%} | R:R={abs(tp-entry)/sl_d:.1f} | "
                     f"entry={entry:.2f} SL={sl:.2f} TP={tp:.2f}"
                     + (" [RE-ENTRY]" if is_reentry else ""))

            # ── Place order ───────────────────────────────────────────────
            ticket, filled = place_order(direction, lots, sl, tp)

            if ticket:
                open_trades.append({
                    "ticket":       ticket,
                    "entry":        filled,
                    "sl":           sl,
                    "dir":          direction,
                    "peak":         filled,
                    "partial_done": False,
                })
                risk_usd = acct.balance * (RISK_PCT / 100)
                logger.log_entry(ticket, feats, direction, filled, sl, tp, tp,
                                 is_reentry=is_reentry, risk_usd=risk_usd)
                trades_today  += 1
                consec_losses  = 0
                log.info(f"Trade #{trades_today} today. Runner system armed.")
                for _ in range(5):
                    time.sleep(60)
                    write_bot("smc_trend", {"heartbeat": time.time()})
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
