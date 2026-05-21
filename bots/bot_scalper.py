"""
╔══════════════════════════════════════════════════════════════════════════════╗
║  BOT 3 — EMA MOMENTUM SCALPER (MULTI-INSTRUMENT)                           ║
║                                                                              ║
║  Goal      : Grow account indefinitely through aggressive compounding       ║
║  Strategy  : 3-EMA stack direction (M5) + M1 pullback entry                ║
║  Timeframe : M5 direction bias · M1 entry timing                           ║
║  Sessions  : All sessions except dead zone (configurable)                  ║
║  Watchlist : Configured per instance in config.json bot_scalper.watchlist  ║
║                                                                              ║
║  5 CORE FEATURES:                                                           ║
║  1. AI self-improvement — learns from every closed trade                   ║
║  2. Hard loss limits — daily -8% floor, weekly -20% cap                   ║
║  3. Dynamic daily profit engine:                                            ║
║       • Runs freely until +10% daily target hit                            ║
║       • After 10% hit: tracks peak profit, keeps trading                   ║
║       • Stops if profit pulls back 10% from day peak                       ║
║       • Hard ceiling at +30% (3x target) — bank it                        ║
║  4. News event control — fully configurable via config.json                ║
║  5. Dynamic momentum reaction — closes trade if M5 bias flips             ║
║                                                                              ║
║  Compounding tiers (auto-scales as balance grows):                         ║
║    $0     → $2,000  : 2.0% risk                                            ║
║    $2,000 → $4,000  : 2.5% risk                                            ║
║    $4,000 → $7,000  : 3.0% risk                                            ║
║    $7,000 → $10,000 : 3.5% risk                                            ║
║    $10,000+         : 2.0% risk (reset after goal, keep compounding)       ║
║                                                                              ║
║  Config    : C:/algos/markets/fx/instances/gold_scalper/config.json      ║
║  Install   : pip install MetaTrader5 pandas numpy pytz scikit-learn joblib ║
║  Run       : python bot_scalper.py                                        ║
╚══════════════════════════════════════════════════════════════════════════════╝
"""

import MetaTrader5 as mt5
import pandas as pd
import numpy as np
import time, json
from datetime import datetime, timedelta
from pathlib import Path

from bot_utils       import load_config, setup_logging, get_instance_dir
from shared_calmar   import CalmarTracker
from shared_ai_brain import AIBrain, TradeLogger
from shared_scanner  import InstrumentScanner, LearningPhaseGate
from shared_risk     import RiskEngine, CorrelationGuard
from bot_state       import write_bot, read_bot, set_started
from notify          import send_telegram
from mt5_ops         import (BotMT5, now_utc, is_market_close,
                              should_close_for_weekend, is_dead_zone, get_atr)

# ── Load config + logging (instance-aware) ────────────────────────────────────
_CFG  = load_config()
log   = setup_logging("BOT_SCALPER", _CFG)
_INST = get_instance_dir(_CFG)

ACCOUNT = _CFG["account"]
SYMBOL  = _CFG["symbol"]
MAGIC   = 20240003

_S = _CFG.get("bot_scalper", {})

WATCHLIST          = _S.get("watchlist", [SYMBOL])
LEARNING_WATCHLIST = _S.get("learning_watchlist", WATCHLIST[:2])
LEARNING_MAX_OPEN  = _S.get("learning_max_open", 1)
MIN_ATR_RATIO      = _S.get("min_atr_ratio", 0.8)
FORCE_TRADE        = _S.get("force_trade", False)
CORR_ACTION        = _S.get("correlation_action", "block")

# EMA stack
EMA_FAST  = _S.get("ema_fast",  9)
EMA_MID   = _S.get("ema_mid",  21)
EMA_SLOW  = _S.get("ema_slow", 50)

# Entry / exit
MIN_RR              = _S.get("min_rr",              1.5)
ATR_PERIOD          = _S.get("atr_period",           14)
ATR_SL_MULT         = _S.get("atr_sl_multiplier",    0.8)
PULLBACK_TOLERANCE  = _S.get("pullback_tolerance",   0.3)
BE_ACTIVATION_R     = _S.get("breakeven_at_r",       0.5)
TRAIL_ATR_MULT      = _S.get("trail_atr_mult",       0.4)
MAX_HOLD_CANDLES    = _S.get("max_hold_candles",      20)

# Dynamic daily profit engine
DAILY_TARGET_PCT    = _S.get("daily_profit_target_pct",    10.0)
DAILY_CEIL_MULT     = _S.get("daily_ceiling_multiplier",    3.0)  # 3× target = hard stop
PEAK_DRAWDOWN_PCT   = _S.get("peak_drawdown_trigger_pct",  10.0)  # 10% pullback from peak
DAILY_LOSS_CAP_PCT  = _S.get("daily_loss_cap_pct",          8.0)
WEEKLY_LOSS_CAP_PCT = _S.get("weekly_loss_cap_pct",         20.0)
DAILY_BUDGET_PCT    = _S.get("daily_budget_pct", DAILY_LOSS_CAP_PCT)

# News events — list of [weekday, hour_utc, minute_utc, label]
# weekday: 0=Mon 1=Tue 2=Wed 3=Thu 4=Fri
NEWS_EVENTS         = _S.get("news_events", [])
NEWS_PAUSE_MINS     = _S.get("news_pause_minutes", 30)
NEWS_WIDEN_SL       = _S.get("news_widen_sl_multiplier", 1.0)  # 1.0 = no change

# Dead zone (CT local hours, DST-aware)
DEAD_ZONE_START     = _S.get("dead_zone_start_ct", 15)
DEAD_ZONE_END       = _S.get("dead_zone_end_ct",   19)

# Compounding
COMPOUND_TIERS      = _S.get("compound_tiers", [
    {"from": 0,     "to": 2000,   "risk_pct": 2.0},
    {"from": 2000,  "to": 4000,   "risk_pct": 2.5},
    {"from": 4000,  "to": 7000,   "risk_pct": 3.0},
    {"from": 7000,  "to": 10000,  "risk_pct": 3.5},
    {"from": 10000, "to": 999999, "risk_pct": 2.0},
])
ACCOUNT_GOAL = _S.get("account_goal", 10000)

MIN_LOT = _CFG["risk"]["min_lot_size"]
MAX_LOT = _CFG["risk"]["max_lot_size"]

log.info(f"Config loaded | watchlist={WATCHLIST} | target=+{DAILY_TARGET_PCT}% | "
         f"ceil=+{DAILY_TARGET_PCT*DAILY_CEIL_MULT:.0f}% | loss=-{DAILY_LOSS_CAP_PCT}%")

_mt5 = BotMT5(SYMBOL, MAGIC, "BOT_SCALPER", _CFG, ACCOUNT, log)


# ═════════════════════════════════════════════════════════════════════════════
# FEATURE NAMES FOR AI
# ═════════════════════════════════════════════════════════════════════════════
SCALP_FEATURES = [
    "ema_stack_strength",   # 0–3 how aligned the EMA stack is
    "pullback_depth_r",     # how deep the pullback was relative to ATR
    "momentum_body_r",      # entry candle body size relative to ATR
    "rsi_at_entry",         # RSI value at entry
    "atr_normalized",       # ATR as % of price
    "hour_of_day",          # UTC hour
    "day_of_week",          # 0=Mon
    "prev_trade_won",       # 1 if last trade won
    "rolling_wr_5",         # win rate last 5 trades
    "rolling_wr_10",        # win rate last 10 trades
    "daily_pnl_pct",        # current day P&L % (context awareness)
    "spread_at_entry",      # broker spread
    "bias_direction",       # 1=bullish 0=bearish
]

def build_scalp_features(signal, daily_pnl_pct, logger):
    now = datetime.utcnow()
    return {
        "ema_stack_strength":   signal.get("stack_strength", 1),
        "pullback_depth_r":     round(signal.get("pullback_depth", 0.5), 3),
        "momentum_body_r":      round(signal.get("body_atr_ratio", 0.5), 3),
        "rsi_at_entry":         round(signal["rsi"], 2),
        "atr_normalized":       round((signal["atr"] / signal["price"]) * 100, 4),
        "hour_of_day":          now.hour,
        "day_of_week":          now.weekday(),
        "prev_trade_won":       logger.get_last_outcome(),
        "rolling_wr_5":         round(logger.get_rolling_wr(5), 3),
        "rolling_wr_10":        round(logger.get_rolling_wr(10), 3),
        "daily_pnl_pct":        round(daily_pnl_pct, 3),
        "spread_at_entry":      round(signal.get("spread", 0.3), 2),
        "bias_direction":       1 if signal["direction"] == "bullish" else 0,
    }


# ═════════════════════════════════════════════════════════════════════════════
# MT5 HELPERS — delegates to shared BotMT5 instance
# ═════════════════════════════════════════════════════════════════════════════

def connect():                      return _mt5.connect()
def get_candles(tf, n, symbol=None): return _mt5.get_candles(tf, n, symbol)
def get_tick(symbol=None):           return _mt5.get_tick(symbol)
def get_deal_result(t):              return _mt5.get_deal_result(t)
def close_position(t, d, r=""):      return _mt5.close_position(t, d, r)
def close_all_positions(r="emergency"):
    return _mt5.close_all_positions(r, WATCHLIST)
def move_sl(t, sl, tp=None):        return _mt5.move_sl(t, sl, tp)
def handle_dead_zone(ot, atr, logger, ai): return _mt5.handle_dead_zone(ot, atr, logger, ai)
def reconcile_on_startup(ot, logger, ai):  return _mt5.reconcile_on_startup(ot, logger, ai)

def place_order(direction: str, lots: float, sl: float, tp: float, symbol: str = None):
    return _mt5.place_order(direction, lots, sl, tp,
                            comment="BOT_SCALPER-SCALP", symbol=symbol)


# ═════════════════════════════════════════════════════════════════════════════
# NEWS EVENT HANDLER
# ═════════════════════════════════════════════════════════════════════════════

def get_news_status():
    """
    Returns: ('clear', 1.0) | ('approaching', widen_mult) | ('active', widen_mult)
    Configured via config.json news_events list.
    """
    if not NEWS_EVENTS:
        return "clear", 1.0
    now  = now_utc()
    mins = now.hour * 60 + now.minute
    for event in NEWS_EVENTS:
        wd, h, m = event[0], event[1], event[2]
        label    = event[3] if len(event) > 3 else "event"
        if now.weekday() != wd:
            continue
        event_mins = h * 60 + m
        diff       = abs(mins - event_mins)
        if diff <= NEWS_PAUSE_MINS:
            log.warning(f"News event: {label} at {h:02d}:{m:02d} UTC "
                        f"({diff} min away) | SL mult={NEWS_WIDEN_SL}")
            return "active", NEWS_WIDEN_SL
    return "clear", 1.0


# ═════════════════════════════════════════════════════════════════════════════
# COMPOUNDING ENGINE
# ═════════════════════════════════════════════════════════════════════════════

def get_risk_pct(balance: float) -> float:
    for tier in COMPOUND_TIERS:
        if tier["from"] <= balance < tier["to"]:
            return tier["risk_pct"]
    return 2.0

def lot_size(balance: float, sl_dist: float,
             sl_multiplier: float = 1.0, symbol: str = None,
             risk_pct: float = None) -> float:
    """Calculate position size. risk_pct overrides the tier-based rate when provided."""
    sym = symbol or SYMBOL
    rp  = risk_pct if risk_pct is not None else get_risk_pct(balance)
    si  = mt5.symbol_info(sym)
    if not si or si.trade_tick_size == 0 or sl_dist == 0: return MIN_LOT
    actual_sl = sl_dist * sl_multiplier
    risk  = balance * (rp / 100)
    ticks = actual_sl / si.trade_tick_size
    lots  = risk / (ticks * si.trade_tick_value)
    lots  = max(MIN_LOT, round(int(lots * 100) / 100, 2))
    lots  = max(si.volume_min, min(si.volume_max, lots))
    lots  = round(round(lots / si.volume_step) * si.volume_step, 2)
    log.info(f"Lot size: {lots}L | {sym} | risk={rp}% (${risk:.2f}) | "
             f"balance=${balance:,.0f} | sl={actual_sl:.5f}pts")
    return lots


# ═════════════════════════════════════════════════════════════════════════════
# DYNAMIC DAILY PROFIT ENGINE
# ═════════════════════════════════════════════════════════════════════════════

class DailyProfitEngine:
    """
    Manages the dynamic daily profit/loss logic:
    - Track peak daily P&L
    - Activate protection once initial target hit
    - Stop if peak pulls back by PEAK_DRAWDOWN_PCT
    - Hard ceiling at DAILY_CEIL_MULT × target
    - Hard floor at DAILY_LOSS_CAP_PCT
    """

    def __init__(self, start_balance: float):
        self.start          = start_balance
        self.peak_balance   = start_balance
        self.target_hit     = False
        self.stopped        = False
        self.stop_reason    = ""

    def update(self, current_balance: float) -> tuple[bool, str]:
        """Call every loop. Returns (should_stop, reason)."""
        if self.stopped:
            return True, self.stop_reason

        pnl_pct  = ((current_balance - self.start) / self.start) * 100
        self.peak_balance = max(self.peak_balance, current_balance)
        peak_pnl = ((self.peak_balance - self.start) / self.start) * 100

        if pnl_pct <= -DAILY_LOSS_CAP_PCT:
            self.stopped     = True
            self.stop_reason = f"DAILY LOSS FLOOR: {pnl_pct:.1f}%"
            return True, self.stop_reason

        ceil_pct = DAILY_TARGET_PCT * DAILY_CEIL_MULT
        if pnl_pct >= ceil_pct:
            self.stopped     = True
            self.stop_reason = f"DAILY CEILING HIT: +{pnl_pct:.1f}% (3x target). Banking it."
            return True, self.stop_reason

        if pnl_pct >= DAILY_TARGET_PCT and not self.target_hit:
            self.target_hit = True
            log.info(f"DAILY TARGET HIT: +{pnl_pct:.1f}%. "
                     f"Peak protection active. Continuing to trade.")

        if self.target_hit and peak_pnl > DAILY_TARGET_PCT:
            pullback = peak_pnl - pnl_pct
            if pullback >= PEAK_DRAWDOWN_PCT:
                self.stopped     = True
                self.stop_reason = (f"PEAK PROTECTION: pulled back {pullback:.1f}% "
                                    f"from peak +{peak_pnl:.1f}%. "
                                    f"Locked in +{pnl_pct:.1f}%.")
                return True, self.stop_reason

        return False, ""

    def get_daily_pnl_pct(self, current_balance: float) -> float:
        return ((current_balance - self.start) / self.start) * 100

    def status(self, current_balance: float) -> str:
        pnl   = self.get_daily_pnl_pct(current_balance)
        peak  = ((self.peak_balance - self.start) / self.start) * 100
        ceil  = DAILY_TARGET_PCT * DAILY_CEIL_MULT
        return (f"P&L={pnl:+.1f}% | peak={peak:+.1f}% | "
                f"target={DAILY_TARGET_PCT}% | ceil={ceil:.0f}% | "
                f"protection={'ON' if self.target_hit else 'OFF'}")


# ═════════════════════════════════════════════════════════════════════════════
# INDICATORS
# ═════════════════════════════════════════════════════════════════════════════

def calc_ema(df: pd.DataFrame, period: int) -> pd.Series:
    return df["close"].ewm(span=period, adjust=False).mean()

def calc_atr(df: pd.DataFrame, period: int = ATR_PERIOD) -> float:
    return get_atr(df, period)

def calc_rsi(df: pd.DataFrame, period: int = 14) -> float:
    delta = df["close"].diff()
    gain  = delta.clip(lower=0).rolling(period).mean()
    loss  = (-delta.clip(upper=0)).rolling(period).mean()
    return float((100 - (100 / (1 + gain/(loss+1e-9)))).iloc[-1])

def get_m5_bias(df_m5: pd.DataFrame) -> tuple[str | None, int]:
    """Returns (bias, stack_strength). stack_strength 0-3: EMA alignment count."""
    if len(df_m5) < EMA_SLOW + 5:
        return None, 0

    ema9  = float(calc_ema(df_m5, EMA_FAST).iloc[-1])
    ema21 = float(calc_ema(df_m5, EMA_MID).iloc[-1])
    ema50 = float(calc_ema(df_m5, EMA_SLOW).iloc[-1])
    price = float(df_m5["close"].iloc[-1])

    bull_conditions = [ema9 > ema21, ema21 > ema50, price > ema50]
    bear_conditions = [ema9 < ema21, ema21 < ema50, price < ema50]

    bull_score = sum(bull_conditions)
    bear_score = sum(bear_conditions)

    if bull_score >= 2: return "bullish", bull_score
    if bear_score >= 2: return "bearish", bear_score
    return None, 0


# ═════════════════════════════════════════════════════════════════════════════
# SIGNAL DETECTION
# ═════════════════════════════════════════════════════════════════════════════

def detect_scalp_signal(df_m1: pd.DataFrame, df_m5: pd.DataFrame,
                         spread: float, symbol: str) -> dict | None:
    """
    M5 EMA stack bias + M1 pullback to EMA9 + momentum candle.
    """
    if df_m1.empty or len(df_m1) < EMA_SLOW + 5:
        return None

    bias, stack_strength = get_m5_bias(df_m5)
    if not bias:
        return None

    bid, ask = get_tick(symbol)
    price    = (bid + ask) / 2
    if price == 0: return None

    atr       = calc_atr(df_m1)
    ema9_m1   = float(calc_ema(df_m1, EMA_FAST).iloc[-1])
    rsi       = calc_rsi(df_m1)
    last      = df_m1.iloc[-1]
    prev      = df_m1.iloc[-2]
    body      = abs(last["close"] - last["open"])
    min_body  = atr * 0.3
    body_ratio= body / atr if atr > 0 else 0

    if bias == "bullish":
        if rsi > 75: return None
        dist      = price - ema9_m1
        pullback  = dist / atr if atr > 0 else 0
        if dist > atr * PULLBACK_TOLERANCE: return None
        if dist < -atr * 1.5: return None
        if last["close"] <= last["open"]: return None
        if body < min_body: return None
        if prev["low"] > ema9_m1 + atr * 0.5: return None

        return {
            "direction":      "bullish",
            "price":          price,
            "atr":            atr,
            "ema9":           ema9_m1,
            "rsi":            rsi,
            "stack_strength": stack_strength,
            "pullback_depth": abs(pullback),
            "body_atr_ratio": body_ratio,
            "spread":         spread,
            "score":          float(stack_strength),
        }

    else:  # bearish
        if rsi < 25: return None
        dist     = ema9_m1 - price
        pullback = dist / atr if atr > 0 else 0
        if dist > atr * PULLBACK_TOLERANCE: return None
        if dist < -atr * 1.5: return None
        if last["close"] >= last["open"]: return None
        if body < min_body: return None
        if prev["high"] < ema9_m1 - atr * 0.5: return None

        return {
            "direction":      "bearish",
            "price":          price,
            "atr":            atr,
            "ema9":           ema9_m1,
            "rsi":            rsi,
            "stack_strength": stack_strength,
            "pullback_depth": abs(pullback),
            "body_atr_ratio": body_ratio,
            "spread":         spread,
            "score":          float(stack_strength),
        }


def detect_setup(symbol: str) -> dict | None:
    """
    Scanner callback: fetch data for `symbol` and return a setup dict or None.
    The `score` key is used by InstrumentScanner to rank candidates.
    """
    df_m1 = get_candles(mt5.TIMEFRAME_M1, 120, symbol)
    df_m5 = get_candles(mt5.TIMEFRAME_M5, 120, symbol)
    if df_m1.empty or df_m5.empty:
        return None

    bid, ask = get_tick(symbol)
    spread   = ask - bid

    return detect_scalp_signal(df_m1, df_m5, spread, symbol)


# ═════════════════════════════════════════════════════════════════════════════
# ORDER MANAGEMENT — delegates to shared BotMT5
# ═════════════════════════════════════════════════════════════════════════════

def manage_positions(open_trades: list, m5_cache: dict, logger, ai):
    """
    Full position management across all open trades (any symbol).

    m5_cache: {symbol: df_m5} for momentum flip detection.

    Per-trade atr is read from t["atr"] (stored at entry time) so trailing
    stop distances are correct for each instrument's volatility.

    1. Breakeven at BE_ACTIVATION_R
    2. Trailing stop after breakeven
    3. Max hold time force close
    4. MOMENTUM REVERSAL — close if M5 bias flips against position while in profit
    5. Force close everything at 21:45 UTC (15 min before market close)
    """
    if is_market_close() and open_trades:
        reason = "WEEKEND-CLOSE" if should_close_for_weekend() else "DAILY-CLOSE"
        log.info(f"Market closing in 15 min — closing all {len(open_trades)} scalp(s). [{reason}]")
        for t in open_trades[:]:
            pos = mt5.positions_get(ticket=t["ticket"])
            if pos:
                ok, cp, pnl = close_position(t["ticket"], t["dir"], reason)
                if ok:
                    logger.log_close(t["ticket"], cp, pnl)
                    ai.on_trade_closed(t["ticket"], cp, pnl)
            open_trades.remove(t)
        return

    for t in open_trades[:]:
        pos = mt5.positions_get(ticket=t["ticket"])
        if not pos:
            cp, pnl = get_deal_result(t["ticket"])
            if cp:
                logger.log_close(t["ticket"], cp, pnl)
                ai.on_trade_closed(t["ticket"], cp, pnl)
            open_trades.remove(t)
            continue

        p         = pos[0]
        sym       = t.get("symbol", SYMBOL)
        price     = p.price_current
        direction = t["dir"]
        sl_dist   = abs(t["entry"] - t["sl"])
        if sl_dist == 0: continue

        profit_r = (
            (price - t["entry"]) / sl_dist if direction == "bullish"
            else (t["entry"] - price) / sl_dist
        )

        # FEATURE 5 — Momentum reversal detection per trade's symbol
        df_m5 = m5_cache.get(sym, pd.DataFrame())
        if not df_m5.empty:
            current_bias, _ = get_m5_bias(df_m5)
            if current_bias is not None and current_bias != direction:
                if profit_r > 0:  # only close early if we're in profit
                    log.info(f"T{t['ticket']} MOMENTUM FLIP [{sym}] — "
                             f"M5 bias now {current_bias}, we are {direction}. "
                             f"Closing at {profit_r:.1f}R.")
                    ok, cp, pnl = close_position(t["ticket"], direction, "MOMENTUM-FLIP")
                    if ok:
                        logger.log_close(t["ticket"], cp, pnl)
                        ai.on_trade_closed(t["ticket"], cp, pnl)
                        open_trades.remove(t)
                        continue

        # Per-trade ATR for trailing stop (each instrument has its own volatility)
        atr = t.get("atr") or 1.0

        # Breakeven at BE_ACTIVATION_R
        if profit_r >= BE_ACTIVATION_R and not t.get("be_done"):
            be = t["entry"]
            if direction == "bullish" and p.sl < be - 0.05:
                move_sl(t["ticket"], be)
                t["be_done"] = True
                t["peak"]    = price
                log.info(f"T{t['ticket']} BE [{sym}] @ {be:.5f} ({profit_r:.1f}R)")
            elif direction == "bearish" and p.sl > be + 0.05:
                move_sl(t["ticket"], be)
                t["be_done"] = True
                t["peak"]    = price
                log.info(f"T{t['ticket']} BE [{sym}] @ {be:.5f} ({profit_r:.1f}R)")

        # Trail after breakeven
        if t.get("be_done"):
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

        # Max hold time
        t["candles_held"] = t.get("candles_held", 0) + 1
        if t["candles_held"] >= MAX_HOLD_CANDLES:
            log.info(f"T{t['ticket']} MAX HOLD [{sym}] ({MAX_HOLD_CANDLES} candles). Closing.")
            ok, cp, pnl = close_position(t["ticket"], direction, "MAX-HOLD")
            if ok:
                logger.log_close(t["ticket"], cp, pnl)
                ai.on_trade_closed(t["ticket"], cp, pnl)
                open_trades.remove(t)


def recover_open_positions() -> list:
    recovered = []
    for symbol in WATCHLIST:
        positions = mt5.positions_get(symbol=symbol)
        if not positions:
            continue
        for pos in positions:
            if pos.magic != MAGIC:
                continue
            direction = "bullish" if pos.type == mt5.ORDER_TYPE_BUY else "bearish"
            # Fetch ATR at recover time for accurate trailing stop distances
            df_m1 = get_candles(mt5.TIMEFRAME_M1, 50, symbol)
            atr   = calc_atr(df_m1) if not df_m1.empty else None
            recovered.append({
                "ticket":       pos.ticket,
                "entry":        pos.price_open,
                "sl":           pos.sl,
                "dir":          direction,
                "peak":         pos.price_current,
                "be_done":      False,
                "candles_held": 0,
                "symbol":       symbol,
                "atr":          atr,
            })
            log.info(f"RECOVERED | {symbol} | ticket={pos.ticket} | "
                     f"{direction} @ {pos.price_open:.5f}")
    if recovered:
        log.info(f"Recovered {len(recovered)} position(s) across watchlist")
    return recovered


# ═════════════════════════════════════════════════════════════════════════════
# PROGRESS LOGGER
# ═════════════════════════════════════════════════════════════════════════════

def log_progress(balance: float, start_balance: float):
    pct_to_goal = (balance / ACCOUNT_GOAL) * 100
    growth      = ((balance / start_balance) - 1) * 100
    risk_pct    = get_risk_pct(balance)
    next_tier   = next((t["to"] for t in COMPOUND_TIERS
                        if t["from"] <= balance < t["to"]), ACCOUNT_GOAL)
    log.info(f"PROGRESS | ${balance:,.2f} -> ${ACCOUNT_GOAL:,} ({pct_to_goal:.0f}%) | "
             f"total growth={growth:+.1f}% | risk={risk_pct}% | next tier ${next_tier:,}")
    if balance >= ACCOUNT_GOAL:
        log.info("GOAL REACHED! Continuing to compound at 2% risk.")


# ═════════════════════════════════════════════════════════════════════════════
# MAIN LOOP
# ═════════════════════════════════════════════════════════════════════════════

def run():
    log.info("=" * 65)
    log.info("  BOT 3 — EMA MOMENTUM SCALPER (MULTI-INSTRUMENT)")
    log.info(f"  Watchlist: {WATCHLIST}")
    log.info(f"  Target: +{DAILY_TARGET_PCT}% daily | Ceil: +{DAILY_TARGET_PCT*DAILY_CEIL_MULT:.0f}% | "
             f"Trail: -{PEAK_DRAWDOWN_PCT}% from peak | Loss floor: -{DAILY_LOSS_CAP_PCT}%")
    log.info("=" * 65)
    set_started("scalper")
    send_telegram("🟢 *Scalper online*")

    if not connect(): return

    acct = mt5.account_info()
    if acct.balance <= 0:
        log.error(f"Account balance is ${acct.balance:.2f} — demo account may have been reset. "
                  "Please restore balance before running BOT_SCALPER.")
        mt5.shutdown(); return

    calmar        = CalmarTracker(acct.balance, equity_file=str(_INST / "scalper_equity.json"))
    logger        = TradeLogger(str(_INST / "scalper_trades.json"))
    ai            = AIBrain(logger, model_file=str(_INST / "scalper_model.pkl"))
    scanner       = InstrumentScanner(WATCHLIST, "BOT_SCALPER", "scalper", _INST, log,
                                      min_atr_ratio=MIN_ATR_RATIO, force_trade=FORCE_TRADE)
    risk_engine   = RiskEngine("BOT_SCALPER", DAILY_BUDGET_PCT, log)
    corr_guard    = CorrelationGuard(_CFG.get("correlation_map", []), log)
    learning_gate = LearningPhaseGate(LEARNING_WATCHLIST, LEARNING_MAX_OPEN, log)

    start_balance = acct.balance
    daily_engine  = DailyProfitEngine(acct.balance)

    _week_file   = _INST / "scalper_weekly.json"
    current_week = now_utc().isocalendar()[1]
    if _week_file.exists():
        _wdata = json.loads(_week_file.read_text())
        if _wdata.get("week") == current_week:
            weekly_start = _wdata.get("weekly_start", acct.balance)
            log.info(f"Weekly start restored: ${weekly_start:,.2f} (week {current_week})")
        else:
            weekly_start = acct.balance
            _week_file.write_text(json.dumps({"week": current_week, "weekly_start": weekly_start}))
            log.info(f"New week {current_week} — weekly start: ${weekly_start:,.2f}")
    else:
        weekly_start = acct.balance
        _week_file.write_text(json.dumps({"week": current_week, "weekly_start": weekly_start}))
        log.info(f"Week file created — weekly start: ${weekly_start:,.2f}")

    open_trades   = recover_open_positions()
    reconcile_on_startup(open_trades, logger, ai)
    risk_engine.reset_day(acct.balance)
    last_date     = now_utc().date()
    last_week     = current_week
    consec_losses = 0

    log.info(f"Balance ${acct.balance:,.2f} | Risk tier: {get_risk_pct(acct.balance)}%")
    log_progress(acct.balance, start_balance)

    try:
        while True:
            now  = now_utc()
            write_bot("scalper", {"heartbeat": time.time()})

            # ── Market close — highest priority check ─────────────────────
            if is_market_close() and open_trades:
                reason = "WEEKEND-CLOSE" if should_close_for_weekend() else "DAILY-CLOSE"
                log.warning(f"MARKET CLOSE in 15 min [{reason}] — "
                            f"closing all {len(open_trades)} scalp(s) now.")
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
            date = now.date()

            # ── Daily reset ───────────────────────────────────────────────
            if date != last_date:
                acct          = mt5.account_info()
                daily_engine  = DailyProfitEngine(acct.balance)
                risk_engine.reset_day(acct.balance)
                last_date     = date
                consec_losses = 0
                calmar.record(acct.balance)
                calmar.log_report()
                log_progress(acct.balance, start_balance)
                write_bot("scalper", {"unresolved_symbols_alerted": {}})
                log.info(f"New day | ${acct.balance:,.2f} | "
                         f"risk={get_risk_pct(acct.balance)}%")

            # ── Weekly reset ──────────────────────────────────────────────
            week = now.isocalendar()[1]
            if week != last_week:
                weekly_start = acct.balance
                last_week    = week
                _week_file.write_text(json.dumps({"week": week, "weekly_start": weekly_start}))
                log.info(f"New week | Reset ${weekly_start:,.2f}")

            acct = mt5.account_info()
            if not acct:
                log.warning("MT5 returned no account info — retrying.")
                time.sleep(30); continue

            write_bot("scalper", {
                "balance":      acct.balance,
                "status":       "running",
                "weekly_start": weekly_start,
                "daily_start":  daily_engine.start,
                "last_write":   datetime.utcnow().isoformat(),
            })

            # ── Daily P&L engine check ────────────────────────────────────
            should_stop, stop_reason = daily_engine.update(acct.balance)
            if should_stop:
                log.warning(f"DAILY ENGINE: {stop_reason}")
                for _t, _cp, _pnl in close_all_positions("daily-engine"):
                    _m = next((x for x in open_trades if x["ticket"] == _t), None)
                    if _m:
                        logger.log_close(_t, _cp, _pnl)
                        ai.on_trade_closed(_t, _cp, _pnl)
                        open_trades.remove(_m)
                log.info(f"Day locked | {daily_engine.status(acct.balance)}")
                calmar.record(acct.balance)
                log_progress(acct.balance, start_balance)
                write_bot("scalper", {
                    "day_locked":     True,
                    "lock_reason":    stop_reason,
                    "lock_alerted":   False,
                    "resume_trading": False,
                })
                while now_utc().date() == date:
                    active_syms = {t.get("symbol", SYMBOL) for t in open_trades}
                    m5_cache    = {sym: get_candles(mt5.TIMEFRAME_M5, 50, sym)
                                   for sym in active_syms}
                    if m5_cache:
                        manage_positions(open_trades, m5_cache, logger, ai)
                    if read_bot("scalper").get("resume_trading"):
                        write_bot("scalper", {
                            "day_locked":     False,
                            "resume_trading": False,
                        })
                        log.warning("RESUME OVERRIDE: resuming trading by user request")
                        daily_engine.stopped = False
                        break
                    time.sleep(60)
                continue

            # ── Weekly loss cap ───────────────────────────────────────────
            weekly_dd = ((weekly_start - acct.balance) / weekly_start) * 100
            if weekly_dd >= WEEKLY_LOSS_CAP_PCT:
                log.warning(f"WEEKLY CAP: -{weekly_dd:.1f}%. 6hr cooldown.")
                for _t, _cp, _pnl in close_all_positions("weekly-cap"):
                    _m = next((x for x in open_trades if x["ticket"] == _t), None)
                    if _m:
                        logger.log_close(_t, _cp, _pnl)
                        ai.on_trade_closed(_t, _cp, _pnl)
                        open_trades.remove(_m)
                calmar.record(acct.balance)
                write_bot("scalper", {
                    "day_locked":     True,
                    "lock_reason":    f"WEEKLY CAP: -{weekly_dd:.1f}% weekly loss",
                    "lock_alerted":   False,
                    "resume_trading": False,
                })
                cooldown_end = datetime.utcnow() + timedelta(hours=6)
                while datetime.utcnow() < cooldown_end:
                    if read_bot("scalper").get("resume_trading"):
                        write_bot("scalper", {"day_locked": False, "resume_trading": False})
                        log.warning("WEEKLY CAP RESUME: user override — resuming early.")
                        break
                    time.sleep(60)
                else:
                    write_bot("scalper", {"day_locked": False})
                continue

            # ── Consecutive loss cooldown ─────────────────────────────────
            if consec_losses >= 3:
                log.warning(f"{consec_losses} consecutive losses. 1hr cooldown.")
                for _ in range(60):
                    time.sleep(60)
                    write_bot("scalper", {"heartbeat": time.time()})
                consec_losses = 0
                continue

            # ── Dead zone: gold market close ──────────────────────────────
            if is_dead_zone(DEAD_ZONE_START, DEAD_ZONE_END):
                active_syms = {t.get("symbol", SYMBOL) for t in open_trades}
                m5_cache    = {sym: get_candles(mt5.TIMEFRAME_M5, 50, sym)
                               for sym in active_syms}
                if m5_cache:
                    manage_positions(open_trades, m5_cache, logger, ai)
                    # handle_dead_zone operates on ticket-level, atr is vestigial
                    handle_dead_zone(open_trades, 0.0, logger, ai)
                if now.minute == 0:
                    log.info(f"Dead zone. No new entries. "
                             f"{daily_engine.status(acct.balance)}")
                time.sleep(60)
                continue

            # ── News event check ──────────────────────────────────────────
            news_status, sl_mult = get_news_status()
            if news_status == "active" and NEWS_PAUSE_MINS > 0 and NEWS_WIDEN_SL == 1.0:
                log.warning("News blackout active. Pausing entries.")
                time.sleep(60)
                continue

            # ── Manage existing positions ─────────────────────────────────
            active_syms = {t.get("symbol", SYMBOL) for t in open_trades}
            m5_cache    = {sym: get_candles(mt5.TIMEFRAME_M5, 120, sym)
                           for sym in active_syms}
            trades_before = len(open_trades)
            manage_positions(open_trades, m5_cache, logger, ai)
            if len(open_trades) < trades_before:
                _acct = mt5.account_info()
                if _acct:
                    acct = _acct
                    calmar.record(acct.balance)

            # ── Log status every hour ─────────────────────────────────────
            if now.minute == 0:
                log.info(daily_engine.status(acct.balance))

            # ── Risk capacity gate (Phase 3) ───────────────────────────────
            proposed_risk = get_risk_pct(acct.balance)
            _allowed, effective_risk = risk_engine.evaluate(open_trades, acct.balance, proposed_risk)
            if not _allowed:
                time.sleep(10); continue

            # ── Phase 5: learning-phase gate ──────────────────────────────
            if not learning_gate.check_max_open(open_trades, ai):
                time.sleep(10); continue
            _active_watchlist = learning_gate.active_watchlist(WATCHLIST, ai)

            # ── Scanner: find best setup across watchlist ─────────────────
            candidates = scanner.scan(detect_setup, watchlist=_active_watchlist)
            if not candidates:
                time.sleep(10)
                continue

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
                log.info("CorrelationGuard: all candidates blocked — waiting 10s.")
                time.sleep(10); continue

            symbol = best.symbol
            signal = best.setup

            # ── AI gate ───────────────────────────────────────────────────
            daily_pnl = daily_engine.get_daily_pnl_pct(acct.balance)
            feats     = build_scalp_features(signal, daily_pnl, logger)
            take, ai_prob, ai_reason = ai.should_take_trade(feats, threshold=0.52)
            log.info(f"AI [{symbol}]: {ai_reason}")
            if not take:
                time.sleep(10)
                continue

            # ── Entry, SL, TP ─────────────────────────────────────────────
            direction = signal["direction"]
            atr       = signal["atr"]
            sl_dist   = atr * ATR_SL_MULT * sl_mult  # sl_mult > 1 during news

            bid, ask = get_tick(symbol)
            if direction == "bullish":
                entry = ask
                sl    = entry - sl_dist
                tp    = entry + sl_dist * MIN_RR
            else:
                entry = bid
                sl    = entry + sl_dist
                tp    = entry - sl_dist * MIN_RR

            if abs(tp - entry) / sl_dist < MIN_RR:
                time.sleep(10)
                continue

            # ── Position sizing ───────────────────────────────────────────
            lots = lot_size(acct.balance, sl_dist, sl_mult, symbol, risk_pct=effective_risk)

            log.info(f"SCALP SIGNAL | {symbol} | {direction.upper()} | "
                     f"price={signal['price']:.5f} | RSI={signal['rsi']:.1f} | "
                     f"stack={signal['stack_strength']}/3 | AI={ai_prob:.0%} | "
                     f"entry={entry:.5f} SL={sl:.5f} TP={tp:.5f} | "
                     f"{daily_engine.status(acct.balance)}")

            ticket, filled = place_order(direction, lots, sl, tp, symbol)

            if ticket:
                open_trades.append({
                    "ticket":       ticket,
                    "entry":        filled,
                    "sl":           sl,
                    "dir":          direction,
                    "peak":         filled,
                    "be_done":      False,
                    "candles_held": 0,
                    "symbol":       symbol,
                    "atr":          atr,
                    "lots":         lots,
                })
                risk_usd = acct.balance * (get_risk_pct(acct.balance) / 100)
                logger.log_entry(ticket, feats, direction, filled, sl, tp, tp,
                                 risk_usd=risk_usd)
                consec_losses = 0
                time.sleep(10)
            else:
                consec_losses += 1
                time.sleep(30)

    except KeyboardInterrupt:
        log.info("Stopped by user.")
    except Exception as e:
        log.exception(f"Unexpected error: {e}")
    finally:
        mt5.shutdown()
        log.info("MT5 disconnected.")


if __name__ == "__main__":
    run()
