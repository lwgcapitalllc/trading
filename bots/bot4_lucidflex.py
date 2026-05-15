"""
╔══════════════════════════════════════════════════════════════════════════════╗
║  BOT 4 -- LUCIDFLEX PROP FIRM BOT (MNQ FUTURES)                            ║
║                                                                              ║
║  Two modes in one bot, set via config.json:                                 ║
║                                                                              ║
║  EVALUATION MODE                                                             ║
║  Goal: Pass LucidFlex challenge in 3-5 days                                 ║
║  Rules:                                                                      ║
║    - 50% consistency: no day exceeds 45% of running total (safe buffer)     ║
║    - Targets configurable daily profit (default 2% of account)              ║
║    - Stops trading for day once daily goal hit                               ║
║    - Tracks profit target progress -- slows down near the end               ║
║    - EOD drawdown protection -- monitors max loss limit buffer               ║
║                                                                              ║
║  FUNDED MODE                                                                 ║
║  Goal: Consistent daily payouts, protect EOD drawdown                       ║
║  Rules:                                                                      ║
║    - No consistency rule to worry about (LucidFlex funded)                  ║
║    - No daily loss limit (LucidFlex funded)                                 ║
║    - Dynamic profit engine -- runs until peak protection triggers           ║
║    - EOD drawdown protection always active                                   ║
║    - Payout tracking -- logs when payout is available                       ║
║                                                                              ║
║  FULLY CONFIGURABLE:                                                         ║
║    - Account size auto-detects position sizing                               ║
║    - Works on any account size ($25K, $50K, $100K, $150K)                  ║
║    - Works on any instrument (MNQ, MES, NQ, ES)                            ║
║    - Switch between eval/funded by changing "mode" in config                ║
║                                                                              ║
║  Platform: Tradovate (via executors/tradovate.py)                           ║
║  Install:  pip install aiohttp websockets pandas numpy pytz                 ║
║  Run:      python bots/bot4_lucidflex.py --config                           ║
║            markets/futures/instances/lucid_account1/config.json             ║
╚══════════════════════════════════════════════════════════════════════════════╝
"""

import asyncio
import json
import logging
import sys
import time
from datetime import datetime, date
from pathlib import Path
from zoneinfo import ZoneInfo

import numpy as np
import pandas as pd

# ── Path setup ────────────────────────────────────────────────────────────────
sys.path.insert(0, str(Path(__file__).parent))
sys.path.insert(0, str(Path(__file__).parent.parent / "shared"))
sys.path.insert(0, str(Path(__file__).parent.parent / "executors"))

from bot_utils      import load_config, setup_logging, get_instance_dir
from tradovate      import TradovateExecutor
from shared_ai_brain import AIBrain, TradeLogger, DailyLogger, build_features_trend
from shared_calmar  import CalmarTracker

ET = ZoneInfo("America/New_York")
UTC = ZoneInfo("UTC")

# ── Load config ───────────────────────────────────────────────────────────────
_CFG  = load_config()
log   = setup_logging("BOT4", _CFG)
_INST = get_instance_dir(_CFG)

# Prop firm settings
_PF   = _CFG["prop_firm"]
FIRM_NAME         = _PF["name"]
ACCOUNT_SIZE      = _PF["account_size"]
PROFIT_TARGET     = _PF["profit_target"]
MAX_LOSS_LIMIT    = _PF["max_loss_limit"]
CONSISTENCY_PCT   = _PF.get("consistency_rule_pct", 50)
CLOSE_TIME_ET     = _PF.get("close_time_et", "16:30")
MODE              = _PF.get("mode", "evaluation")
DAILY_GOAL_PCT    = _PF.get("daily_profit_goal_pct", 2.0)
DAILY_GOAL_FLOOR  = _PF.get("daily_profit_goal_floor", 200)
DAILY_GOAL_CEIL   = _PF.get("daily_profit_goal_ceil", 600)
MAX_CONTRACTS     = _PF.get("max_contracts", 4)

# Instrument settings
_INS  = _CFG["instrument"]
SYMBOL       = _INS["symbol"]
TICK_SIZE    = _INS["tick_size"]
TICK_VALUE   = _INS["tick_value"]
POINT_VALUE  = _INS["point_value"]
SESSION_OPEN = _INS.get("session_open_et", "09:30")
SESSION_CLOSE= _INS.get("session_close_et", "16:00")

# Strategy settings
_STR  = _CFG["strategy"]
MIN_SCORE    = _STR.get("min_confluence_score", 5)
MIN_AI_PROB  = _STR.get("min_ai_probability", 0.55)
ATR_PERIOD   = _STR.get("atr_period", 14)
ATR_SL_MULT  = _STR.get("atr_sl_multiplier", 1.2)
MIN_RR       = _STR.get("min_rr", 2.0)
BE_R         = _STR.get("breakeven_at_r", 1.0)
TRAIL_MULT   = _STR.get("trail_atr_mult", 1.0)
LONDON_ET    = _STR.get("london_open_et", "03:00")
NY_ET        = _STR.get("ny_open_et", "09:30")
KZ_END_ET    = _STR.get("kill_zone_end_et", "11:00")

# Risk settings
_RSK  = _CFG["risk"]
RISK_PCT         = _RSK.get("risk_pct_per_trade", 1.0)
MAX_DAILY_LOSS   = _RSK.get("max_daily_loss_pct", 3.0)
DRAWDOWN_BUFFER  = _RSK.get("max_drawdown_buffer", 500)

log.info(f"BOT4 | {FIRM_NAME} | {SYMBOL} | mode={MODE.upper()} | "
         f"account=${ACCOUNT_SIZE:,} | target=${PROFIT_TARGET:,}")


# =============================================================================
# INDICATORS (platform-agnostic, works on any OHLCV DataFrame)
# =============================================================================

def calc_atr(df: pd.DataFrame, period: int = ATR_PERIOD) -> float:
    h, l, c = df["high"], df["low"], df["close"].shift(1)
    tr = pd.concat([h-l, (h-c).abs(), (l-c).abs()], axis=1).max(axis=1)
    return float(tr.rolling(period).mean().iloc[-1])

def calc_ema(df: pd.DataFrame, period: int) -> pd.Series:
    return df["close"].ewm(span=period, adjust=False).mean()

def calc_rsi(df: pd.DataFrame, period: int = 14) -> float:
    delta = df["close"].diff()
    gain  = delta.clip(lower=0).rolling(period).mean()
    loss  = (-delta.clip(upper=0)).rolling(period).mean()
    return float((100 - (100 / (1 + gain/(loss+1e-9)))).iloc[-1])

def get_h4_trend(df_h4: pd.DataFrame, ema_period: int = 200) -> str:
    if len(df_h4) < ema_period:
        return "neutral"
    ema = float(calc_ema(df_h4, ema_period).iloc[-1])
    price = float(df_h4["close"].iloc[-1])
    return "bullish" if price > ema else "bearish"

def get_session_range(df: pd.DataFrame,
                       start_et: str, end_et: str) -> tuple:
    """Get high/low of a session window."""
    now_et = datetime.now(ET)
    sh, sm = map(int, start_et.split(":"))
    eh, em = map(int, end_et.split(":"))
    session = df[
        (df["time"].dt.hour * 60 + df["time"].dt.minute >= sh*60+sm) &
        (df["time"].dt.hour * 60 + df["time"].dt.minute < eh*60+em)
    ]
    if session.empty:
        return None, None
    return float(session["high"].max()), float(session["low"].min())

def detect_judas_sweep(df: pd.DataFrame, session_high: float,
                        session_low: float, atr: float) -> dict | None:
    """
    Detect Judas Swing: price sweeps beyond session range then reverses.
    Returns {"direction": "bullish"|"bearish", "swept": float, "extreme": float}
    """
    if not session_high or not session_low:
        return None
    last   = df.iloc[-1]
    prev   = df.iloc[-2]
    price  = float(last["close"])
    wick_h = float(last["high"])
    wick_l = float(last["low"])

    # Bearish setup: swept above session high then reversed below it
    if wick_h > session_high and price < session_high:
        sweep_size = wick_h - session_high
        if sweep_size >= atr * 0.2:
            return {"direction": "bearish", "swept": session_high,
                    "extreme": wick_h, "size": sweep_size}

    # Bullish setup: swept below session low then reversed above it
    if wick_l < session_low and price > session_low:
        sweep_size = session_low - wick_l
        if sweep_size >= atr * 0.2:
            return {"direction": "bullish", "swept": session_low,
                    "extreme": wick_l, "size": sweep_size}

    return None

def detect_fvg(df: pd.DataFrame, direction: str) -> bool:
    """Detect Fair Value Gap in the sweep direction."""
    if len(df) < 3:
        return False
    c1, c2, c3 = df.iloc[-3], df.iloc[-2], df.iloc[-1]
    if direction == "bearish":
        return float(c1["low"]) > float(c3["high"])
    else:
        return float(c1["high"]) < float(c3["low"])

def score_setup(sweep: dict, fvg: bool, h4_trend: str,
                in_kz: bool, atr: float) -> int:
    score = 0
    score += 2  # sweep always confirmed at this point
    if fvg:
        score += 2
    if in_kz:
        score += 1
    if h4_trend == sweep["direction"]:
        score += 2
    else:
        score -= 1
    if sweep["size"] >= atr * 0.5:
        score += 1
    return score


# =============================================================================
# PROP FIRM COMPLIANCE ENGINE
# =============================================================================

class PropFirmCompliance:
    """
    Tracks all prop firm rules and prevents violations.
    Fully configurable — reads account size and rules from config.

    Evaluation mode:
      - Tracks daily P&L vs running total
      - Enforces 45% single-day limit (safe buffer under 50% rule)
      - Stops trading once daily goal hit
      - Monitors EOD drawdown buffer
      - Tracks progress toward profit target

    Funded mode:
      - Dynamic profit engine (runs until peak protection)
      - EOD drawdown protection
      - Payout tracking
    """

    def __init__(self, account_size: float, mode: str):
        self.account_size     = account_size
        self.mode             = mode
        self.start_balance    = account_size
        self.peak_balance     = account_size
        self.daily_start      = account_size

        # Eval tracking
        self.eval_total_profit   = 0.0
        self.eval_best_day       = 0.0
        self.eval_days_traded    = 0
        self.eval_complete       = False

        # Daily tracking
        self.daily_profit        = 0.0
        self.daily_goal_hit      = False
        self.daily_stopped       = False
        self.daily_stop_reason   = ""
        self.trades_today        = 0
        self.max_open_today      = 0
        self.min_balance_today   = account_size

        # Funded peak protection
        self.peak_protection_active = False

    def daily_goal(self, balance: float) -> float:
        """Calculate today's profit goal based on current balance."""
        goal = balance * (DAILY_GOAL_PCT / 100)
        return max(DAILY_GOAL_FLOOR, min(goal, DAILY_GOAL_CEIL))

    def update(self, current_balance: float) -> tuple[bool, str]:
        """
        Call every loop. Returns (should_stop_trading, reason).
        Updates all tracking metrics.
        """
        self.daily_profit     = current_balance - self.daily_start
        self.min_balance_today = min(self.min_balance_today, current_balance)

        # EOD drawdown protection (both modes)
        # Max loss limit = current balance must stay above (start - max_loss_limit)
        floor = self.start_balance - MAX_LOSS_LIMIT + DRAWDOWN_BUFFER
        if current_balance <= floor:
            return True, (f"DRAWDOWN PROTECTION: ${current_balance:,.0f} near "
                          f"max loss limit floor ${floor:,.0f}")

        if self.mode == "evaluation":
            return self._check_eval(current_balance)
        else:
            return self._check_funded(current_balance)

    def _check_eval(self, balance: float) -> tuple[bool, str]:
        """Evaluation mode checks."""
        # Check if profit target already hit
        if self.eval_total_profit >= PROFIT_TARGET:
            self.eval_complete = True
            return True, (f"EVALUATION COMPLETE! Profit target hit: "
                          f"${self.eval_total_profit:,.0f} / ${PROFIT_TARGET:,}")

        # Daily goal
        goal = self.daily_goal(balance)
        if self.daily_profit >= goal and not self.daily_goal_hit:
            self.daily_goal_hit = True
            log.info(f"DAILY GOAL HIT: +${self.daily_profit:,.0f} "
                     f"(target ${goal:,.0f}). Stopping for today.")
            return True, f"DAILY GOAL HIT: +${self.daily_profit:,.0f}"

        # Consistency rule — never let today exceed 45% of running total
        # (safe buffer under the 50% rule)
        running_total = self.eval_total_profit + self.daily_profit
        if running_total > 0:
            today_pct = (self.daily_profit / running_total) * 100
            if today_pct > 45 and self.daily_profit > 200:
                return True, (f"CONSISTENCY GUARD: today={today_pct:.1f}% "
                              f"of total (limit 45%). Stopping.")

        return False, ""

    def _check_funded(self, balance: float) -> tuple[bool, str]:
        """Funded mode checks — dynamic profit engine."""
        goal = self.daily_goal(balance)

        # Activate peak protection once daily goal hit
        if self.daily_profit >= goal and not self.peak_protection_active:
            self.peak_protection_active = True
            self.peak_balance           = balance
            log.info(f"DAILY GOAL HIT: +${self.daily_profit:,.0f}. "
                     f"Peak protection active. Continuing to trade.")

        if self.peak_protection_active:
            self.peak_balance = max(self.peak_balance, balance)
            peak_profit = self.peak_balance - self.daily_start
            pullback    = peak_profit - self.daily_profit

            # Stop if pulled back 10% of peak profit
            if peak_profit > 0 and (pullback / peak_profit) >= 0.10:
                return True, (f"PEAK PROTECTION: pulled back "
                              f"${pullback:,.0f} from peak "
                              f"+${peak_profit:,.0f}. "
                              f"Locked in +${self.daily_profit:,.0f}")

            # Hard ceiling: 3x daily goal
            if self.daily_profit >= goal * 3:
                return True, (f"DAILY CEILING: +${self.daily_profit:,.0f} "
                              f"({DAILY_GOAL_PCT*3:.0f}%). Banking it.")

        return False, ""

    def on_day_close(self, closing_balance: float, daily_logger: DailyLogger):
        """Call at end of each trading day."""
        self.eval_total_profit = max(
            self.eval_total_profit,
            closing_balance - self.start_balance
        )
        self.eval_best_day = max(self.eval_best_day, self.daily_profit)
        self.eval_days_traded += 1

        daily_logger.record_day(str(date.today()), {
            "total_trades":          self.trades_today,
            "max_simultaneous_open": self.max_open_today,
            "max_drawdown_pct":      round(
                (self.daily_start - self.min_balance_today) /
                self.daily_start * 100, 2),
            "final_pnl_pct":         round(
                self.daily_profit / self.daily_start * 100, 2),
            "daily_profit":          round(self.daily_profit, 2),
            "eval_total_profit":     round(self.eval_total_profit, 2),
            "eval_days_traded":      self.eval_days_traded,
            "mode":                  self.mode,
        })

        progress = (self.eval_total_profit / PROFIT_TARGET * 100
                    if self.mode == "evaluation" else 0)
        log.info(f"DAY SUMMARY | "
                 f"P&L=${self.daily_profit:+,.0f} | "
                 f"trades={self.trades_today} | "
                 f"eval_total=${self.eval_total_profit:,.0f}"
                 + (f" ({progress:.0f}% of target)"
                    if self.mode == "evaluation" else ""))

        # Reset daily tracking
        self.daily_start         = closing_balance
        self.daily_profit        = 0.0
        self.daily_goal_hit      = False
        self.peak_protection_active = False
        self.trades_today        = 0
        self.max_open_today      = 0
        self.min_balance_today   = closing_balance

    def status(self) -> str:
        if self.mode == "evaluation":
            pct = (self.eval_total_profit / PROFIT_TARGET * 100
                   if PROFIT_TARGET > 0 else 0)
            return (f"EVAL | day={self.eval_days_traded} | "
                    f"total=${self.eval_total_profit:,.0f} "
                    f"({pct:.0f}%) | today=${self.daily_profit:+,.0f} | "
                    f"best_day=${self.eval_best_day:,.0f}")
        else:
            return (f"FUNDED | today=${self.daily_profit:+,.0f} | "
                    f"peak_protection={'ON' if self.peak_protection_active else 'OFF'}")


# =============================================================================
# OPEN TRADE TRACKER
# =============================================================================

class OpenTrade:
    def __init__(self, order_id, direction, entry, sl, tp, contracts, atr):
        self.order_id   = order_id
        self.direction  = direction
        self.entry      = entry
        self.sl         = sl
        self.tp         = tp
        self.contracts  = contracts
        self.atr        = atr
        self.sl_dist    = abs(entry - sl)
        self.be_done    = False
        self.peak_price = entry
        self.candles    = 0
        self.is_reentry = False

    def profit_r(self, current_price: float) -> float:
        if self.sl_dist == 0: return 0
        if self.direction == "bullish":
            return (current_price - self.entry) / self.sl_dist
        return (self.entry - current_price) / self.sl_dist


# =============================================================================
# POSITION MANAGEMENT
# =============================================================================

async def manage_open_trades(executor: TradovateExecutor,
                              open_trades: list[OpenTrade],
                              current_price: float, atr: float):
    """Manage all open trades: BE, trail, close."""
    positions = await executor.get_positions()
    live_ids  = {p.get("orderId") for p in positions}

    for t in open_trades[:]:
        if t.order_id not in live_ids:
            # Trade was closed by broker (SL or TP hit)
            log.info(f"Trade {t.order_id} closed by broker.")
            open_trades.remove(t)
            continue

        profit_r = t.profit_r(current_price)

        # Stage 1 — Breakeven at 1R
        if profit_r >= BE_R and not t.be_done:
            new_sl = t.entry
            ok = await executor.modify_sl(t.order_id, new_sl)
            if ok:
                t.be_done    = True
                t.sl         = new_sl
                log.info(f"T{t.order_id} -> BREAKEVEN @ {new_sl:.2f} "
                         f"({profit_r:.2f}R)")

        # Stage 2 — Trailing stop after BE
        if t.be_done:
            trail = atr * TRAIL_MULT
            if t.direction == "bullish":
                t.peak_price = max(t.peak_price, current_price)
                new_sl       = t.peak_price - trail
                if new_sl > t.sl + TICK_SIZE:
                    await executor.modify_sl(t.order_id, new_sl)
                    t.sl = new_sl
            else:
                t.peak_price = min(t.peak_price, current_price)
                new_sl       = t.peak_price + trail
                if new_sl < t.sl - TICK_SIZE:
                    await executor.modify_sl(t.order_id, new_sl)
                    t.sl = new_sl

        t.candles += 1


# =============================================================================
# MAIN BOT LOOP
# =============================================================================

async def run():
    log.info("=" * 65)
    log.info(f"  BOT 4 -- {FIRM_NAME} | {SYMBOL} | {MODE.upper()}")
    log.info(f"  Account: ${ACCOUNT_SIZE:,} | Target: ${PROFIT_TARGET:,}")
    log.info(f"  Daily goal: {DAILY_GOAL_PCT}% "
             f"(${DAILY_GOAL_FLOOR}-${DAILY_GOAL_CEIL})")
    log.info("=" * 65)

    # Load credentials from merged config (bot_utils merges credentials.json → cfg["account"])
    creds = _CFG.get("account")
    if not creds:
        log.error("No credentials found. Check credentials.json exists in instance dir.")
        return

    if not creds.get("username") or not creds.get("password"):
        log.error("credentials.json must contain 'username', 'password', "
                  "'account_id', and 'environment'.")
        return

    # Initialise components
    executor    = TradovateExecutor(creds, environment=creds.get("environment","demo"))
    logger      = TradeLogger(str(_INST / "bot4_trades.json"))
    daily_log   = DailyLogger(str(_INST / "bot4_daily.json"))
    ai          = AIBrain(logger, model_file=str(_INST / "bot4_model.pkl"))
    calmar      = CalmarTracker(ACCOUNT_SIZE, equity_file=str(_INST / "bot4_equity.json"))
    compliance  = PropFirmCompliance(ACCOUNT_SIZE, MODE)

    await executor.connect()
    balance = await executor.get_account_balance()
    log.info(f"Connected | Balance: ${balance:,.2f} | {ai.status_report()}")

    open_trades   : list[OpenTrade] = []
    last_date     = executor.now_et().date()
    be_setup      = [None]   # [{"direction": str}] for re-entry tracking

    try:
        while True:
            now_et = executor.now_et()
            today  = now_et.date()

            # ── Daily reset ───────────────────────────────────────────────
            if today != last_date:
                balance = await executor.get_account_balance()
                compliance.on_day_close(balance, daily_log)
                calmar.record(balance)
                calmar.log_report()
                last_date = today
                be_setup[0] = None
                log.info(f"New day | ${balance:,.2f} | {compliance.status()}")

            # ── Force close at session end ────────────────────────────────
            if executor.should_force_close(CLOSE_TIME_ET) and open_trades:
                log.warning(f"FORCE CLOSE: {CLOSE_TIME_ET} ET reached. "
                            f"Closing {len(open_trades)} position(s).")
                await executor.close_all_positions(SYMBOL, reason="EOD-CLOSE")
                open_trades.clear()
                await asyncio.sleep(60)
                continue

            # ── Compliance check ──────────────────────────────────────────
            balance = await executor.get_account_balance()
            compliance.max_open_today = max(
                compliance.max_open_today, len(open_trades)
            )
            should_stop, stop_reason = compliance.update(balance)

            if should_stop:
                log.warning(f"COMPLIANCE: {stop_reason}")
                if open_trades:
                    await executor.close_all_positions(SYMBOL, reason="compliance")
                    open_trades.clear()
                log.info(f"Status: {compliance.status()}")
                # Wait for next day
                while executor.now_et().date() == today:
                    await asyncio.sleep(60)
                continue

            # ── Session check ─────────────────────────────────────────────
            in_session = executor.is_session_open(SESSION_OPEN, SESSION_CLOSE)

            # Manage open trades regardless of session
            if open_trades:
                try:
                    df_m1 = await executor.get_candles(SYMBOL, "1min", 30)
                    if not df_m1.empty:
                        price = float(df_m1["close"].iloc[-1])
                        atr   = calc_atr(df_m1)
                        await manage_open_trades(executor, open_trades,
                                                  price, atr)
                except Exception as e:
                    log.warning(f"Position management error: {e}")

            if not in_session:
                if now_et.minute == 0:
                    log.info(f"Outside session ({now_et.hour:02d}:00 ET). "
                             f"{compliance.status()}")
                await asyncio.sleep(60)
                continue

            # ── Kill zone check ───────────────────────────────────────────
            h, m    = now_et.hour, now_et.minute
            cur_min = h * 60 + m
            ny_h, ny_m   = map(int, NY_ET.split(":"))
            kz_h, kz_m   = map(int, KZ_END_ET.split(":"))
            in_kz = (ny_h * 60 + ny_m) <= cur_min < (kz_h * 60 + kz_m)

            # ── Market data ───────────────────────────────────────────────
            try:
                df_m5  = await executor.get_candles(SYMBOL, "5min",  100)
                df_h4  = await executor.get_candles(SYMBOL, "60min", 50)
                df_m1  = await executor.get_candles(SYMBOL, "1min",  30)
                if df_m5.empty or df_h4.empty:
                    await asyncio.sleep(30); continue
            except Exception as e:
                log.warning(f"Data error: {e}")
                await asyncio.sleep(30); continue

            bid, ask = await executor.get_price(SYMBOL)
            price    = (bid + ask) / 2
            atr      = calc_atr(df_m5)
            h4_trend = get_h4_trend(df_h4)

            log.info(f"Scanning | {SYMBOL}={price:.2f} | H4={h4_trend} | "
                     f"ATR={atr:.2f} | {compliance.status()}")

            # ── Asian session range (00:00-09:30 ET) ──────────────────────
            asian_h, asian_l = get_session_range(df_m5, "00:00", "09:30")
            if not asian_h:
                await asyncio.sleep(60); continue
            log.info(f"Asian range: H={asian_h:.2f} L={asian_l:.2f}")

            # ── Judas Swing detection ─────────────────────────────────────
            sweep = detect_judas_sweep(df_m5, asian_h, asian_l, atr)
            if not sweep:
                log.info("No Judas Swing detected. Waiting 60s.")
                await asyncio.sleep(60); continue

            # ── Hard H4 filter ────────────────────────────────────────────
            if sweep["direction"] != h4_trend:
                log.info(f"H4 FILTER: sweep={sweep['direction']} "
                         f"H4={h4_trend}. Counter-trend blocked.")
                await asyncio.sleep(60); continue

            # ── FVG + scoring ─────────────────────────────────────────────
            fvg   = detect_fvg(df_m5, sweep["direction"])
            score = score_setup(sweep, fvg, h4_trend, in_kz, atr)
            if score < MIN_SCORE:
                log.info(f"Score {score} < {MIN_SCORE}. Skip.")
                await asyncio.sleep(60); continue

            # ── Re-entry check ────────────────────────────────────────────
            is_reentry = False
            if (be_setup[0] is not None and
                    be_setup[0]["direction"] == sweep["direction"]):
                is_reentry = True
                log.info(f"RE-ENTRY: same bias after BE stop. "
                         f"{sweep['direction'].upper()}.")
                be_setup[0] = None

            # ── AI gate ───────────────────────────────────────────────────
            daily_pnl_pct = compliance.daily_profit / compliance.daily_start * 100
            feats = build_features_trend(
                score, atr, price,
                sweep["size"], "ny" if in_kz else "other",
                h4_trend == sweep["direction"], fvg,
                ask - bid,
                float(df_h4["high"].max()),
                float(df_h4["low"].min()),
                logger,
                daily_trades=compliance.trades_today,
                daily_pnl_pct=daily_pnl_pct,
                simultaneous_open=len(open_trades),
                is_reentry=is_reentry,
            )
            take, ai_prob, ai_reason = ai.should_take_trade(feats, MIN_AI_PROB)
            log.info(f"AI: {ai_reason}")
            if not take:
                await asyncio.sleep(60); continue

            # ── Entry, SL, TP ─────────────────────────────────────────────
            direction = sweep["direction"]
            sl_buf    = atr * ATR_SL_MULT

            if direction == "bullish":
                entry = ask
                sl    = sweep["extreme"] - sl_buf
                sl_d  = entry - sl
                tp    = entry + sl_d * MIN_RR
            else:
                entry = bid
                sl    = sweep["extreme"] + sl_buf
                sl_d  = sl - entry
                tp    = entry - sl_d * MIN_RR

            if sl_d <= 0 or abs(tp - entry) / sl_d < MIN_RR:
                log.info("R:R check failed. Skip.")
                await asyncio.sleep(60); continue

            # ── Contracts (account-size-aware) ────────────────────────────
            sl_points   = sl_d / POINT_VALUE * POINT_VALUE
            contracts   = executor.calculate_contracts(
                balance, RISK_PCT, sl_d / POINT_VALUE,
                POINT_VALUE, MAX_CONTRACTS
            )

            log.info(f"SIGNAL | {direction.upper()} | score={score} | "
                     f"AI={ai_prob:.0%} | R:R={abs(tp-entry)/sl_d:.1f} | "
                     f"entry={entry:.2f} SL={sl:.2f} TP={tp:.2f} | "
                     f"contracts={contracts}"
                     + (" [RE-ENTRY]" if is_reentry else ""))

            # ── Place order ───────────────────────────────────────────────
            result = await executor.place_order(
                SYMBOL,
                "Buy" if direction == "bullish" else "Sell",
                contracts, sl=sl, tp=tp
            )

            if result:
                trade = OpenTrade(
                    result.get("orderId"),
                    direction, entry, sl, tp, contracts, atr
                )
                trade.is_reentry = is_reentry
                open_trades.append(trade)
                logger.log_entry(
                    trade.order_id, feats, direction,
                    entry, sl, tp, tp, is_reentry=is_reentry
                )
                compliance.trades_today += 1
                log.info(f"Trade #{compliance.trades_today} today.")
                await asyncio.sleep(300)
            else:
                log.warning("Order failed.")
                await asyncio.sleep(60)

    except KeyboardInterrupt:
        log.info("Stopped by user.")
    except Exception as e:
        log.exception(f"Unexpected error: {e}")
    finally:
        await executor.disconnect()
        log.info("Bot 4 shut down.")


if __name__ == "__main__":
    print(f"BOT 4 -- {FIRM_NAME} Challenge Bot | {SYMBOL}")
    print(f"Mode: {MODE.upper()} | Account: ${ACCOUNT_SIZE:,}")
    print(f"Target: ${PROFIT_TARGET:,} | Daily goal: {DAILY_GOAL_PCT}%\n")
    if input("Type CONFIRM to start: ").strip().upper() == "CONFIRM":
        asyncio.run(run())
    else:
        print("Aborted.")
