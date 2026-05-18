"""
╔══════════════════════════════════════════════════════════════════════════════╗
║  BOT 3 — XAUUSD EMA MOMENTUM SCALPER (FULL BUILD)                          ║
║                                                                              ║
║  Goal      : Grow account indefinitely through aggressive compounding       ║
║  Strategy  : 3-EMA stack direction (M5) + M1 pullback entry                ║
║  Timeframe : M5 direction bias · M1 entry timing                           ║
║  Sessions  : All sessions except dead zone (configurable)                  ║
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
from datetime import datetime
from pathlib import Path
import pytz

from bot_utils import load_config, setup_logging, get_instance_dir
from shared_calmar   import CalmarTracker
from shared_ai_brain import AIBrain, TradeLogger

# ── Load config + logging (instance-aware) ────────────────────────────────────
_CFG  = load_config()
log   = setup_logging("BOT_SCALPER", _CFG)
_INST = get_instance_dir(_CFG)

ACCOUNT = _CFG["account"]
SYMBOL  = _CFG["symbol"]
MAGIC   = 20240003

_S = _CFG.get("bot_scalper", {})

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

# News events — list of [weekday, hour_utc, minute_utc, label]
# weekday: 0=Mon 1=Tue 2=Wed 3=Thu 4=Fri
NEWS_EVENTS         = _S.get("news_events", [])
NEWS_PAUSE_MINS     = _S.get("news_pause_minutes", 30)
NEWS_WIDEN_SL       = _S.get("news_widen_sl_multiplier", 1.0)  # 1.0 = no change

# Dead zone
DEAD_ZONE_START     = _S.get("dead_zone_start_utc", 15)
DEAD_ZONE_END       = _S.get("dead_zone_end_utc",   19)

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

log.info(f"Config loaded | {SYMBOL} | target=+{DAILY_TARGET_PCT}% | "
         f"ceil=+{DAILY_TARGET_PCT*DAILY_CEIL_MULT:.0f}% | loss=-{DAILY_LOSS_CAP_PCT}%")


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
    bot_id      = f"BOT_SCALPER_{expected_id}"

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

def is_dead_zone() -> bool:
    """
    Returns True during 3:00pm - 7:00pm Texas time.
    Uses America/Chicago timezone so DST is handled automatically.
    CDT (Mar-Nov): 3-7pm CT = 20:00-00:00 UTC
    CST (Nov-Mar): 3-7pm CT = 21:00-01:00 UTC
    """
    try:
        from zoneinfo import ZoneInfo
        texas = ZoneInfo("America/Chicago")
        now_tx = now_utc().astimezone(texas)
        return 15 <= now_tx.hour < 19
    except Exception:
        return DEAD_ZONE_START <= now_utc().hour < DEAD_ZONE_END


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


def is_market_close() -> bool:
    """Returns True at 21:45 UTC — 15 min before gold market closes at 22:00 UTC."""
    t = now_utc()
    return (t.hour == 19 and t.minute >= 45) or t.hour == 20

def should_close_for_weekend() -> bool:
    """Friday 21:45 UTC — no reopening until Sunday 22:00 UTC."""
    t = now_utc()
    return t.weekday() == 4 and ((t.hour == 19 and t.minute >= 45) or t.hour == 20)


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

def lot_size(balance: float, sl_dist: float, sl_multiplier: float = 1.0) -> float:
    """Calculate position size. sl_multiplier widens stop during news."""
    risk_pct = get_risk_pct(balance)
    si = mt5.symbol_info(SYMBOL)
    if not si or si.trade_tick_size == 0 or sl_dist == 0: return MIN_LOT
    actual_sl = sl_dist * sl_multiplier
    risk  = balance * (risk_pct / 100)
    ticks = actual_sl / si.trade_tick_size
    lots  = risk / (ticks * si.trade_tick_value)
    lots  = max(MIN_LOT, round(int(lots * 100) / 100, 2))
    lots  = max(si.volume_min, min(si.volume_max, lots))
    lots  = round(round(lots / si.volume_step) * si.volume_step, 2)
    log.info(f"Lot size: {lots}L | risk={risk_pct}% (${risk:.2f}) | "
             f"balance=${balance:,.0f} | sl={actual_sl:.2f}pts")
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
        """
        Call every loop. Returns (should_stop, reason).
        """
        if self.stopped:
            return True, self.stop_reason

        pnl_pct  = ((current_balance - self.start) / self.start) * 100
        self.peak_balance = max(self.peak_balance, current_balance)
        peak_pnl = ((self.peak_balance - self.start) / self.start) * 100

        # Hard floor — always active
        if pnl_pct <= -DAILY_LOSS_CAP_PCT:
            self.stopped     = True
            self.stop_reason = f"DAILY LOSS FLOOR: {pnl_pct:.1f}%"
            return True, self.stop_reason

        # Hard ceiling — 3x target
        ceil_pct = DAILY_TARGET_PCT * DAILY_CEIL_MULT
        if pnl_pct >= ceil_pct:
            self.stopped     = True
            self.stop_reason = f"DAILY CEILING HIT: +{pnl_pct:.1f}% (3x target). Banking it."
            return True, self.stop_reason

        # Activate peak protection once initial target is hit
        if pnl_pct >= DAILY_TARGET_PCT and not self.target_hit:
            self.target_hit = True
            log.info(f"DAILY TARGET HIT: +{pnl_pct:.1f}%. "
                     f"Peak protection active. Continuing to trade.")

        # Peak drawdown protection — only after target hit
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
    h, l, c = df["high"], df["low"], df["close"].shift(1)
    tr = pd.concat([h-l, (h-c).abs(), (l-c).abs()], axis=1).max(axis=1)
    return float(tr.rolling(period).mean().iloc[-1])

def calc_rsi(df: pd.DataFrame, period: int = 14) -> float:
    delta = df["close"].diff()
    gain  = delta.clip(lower=0).rolling(period).mean()
    loss  = (-delta.clip(upper=0)).rolling(period).mean()
    return float((100 - (100 / (1 + gain/(loss+1e-9)))).iloc[-1])

def get_m5_bias(df_m5: pd.DataFrame) -> tuple[str | None, int]:
    """
    Returns (bias, stack_strength).
    stack_strength 0-3: how many EMA conditions are met.
    """
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
                         spread: float) -> dict | None:
    """
    M5 EMA stack bias + M1 pullback to EMA9 + momentum candle.
    """
    if df_m1.empty or len(df_m1) < EMA_SLOW + 5:
        return None

    bias, stack_strength = get_m5_bias(df_m5)
    if not bias:
        return None

    bid, ask = get_tick()
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
            "direction":     "bullish",
            "price":         price,
            "atr":           atr,
            "ema9":          ema9_m1,
            "rsi":           rsi,
            "stack_strength": stack_strength,
            "pullback_depth": abs(pullback),
            "body_atr_ratio": body_ratio,
            "spread":         spread,
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
            "direction":     "bearish",
            "price":         price,
            "atr":           atr,
            "ema9":          ema9_m1,
            "rsi":           rsi,
            "stack_strength": stack_strength,
            "pullback_depth": abs(pullback),
            "body_atr_ratio": body_ratio,
            "spread":         spread,
        }


# ═════════════════════════════════════════════════════════════════════════════
# ORDER MANAGEMENT
# ═════════════════════════════════════════════════════════════════════════════

def place_order(direction: str, lots: float, sl: float, tp: float):
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
        "comment":      "BOT_SCALPER-SCALP",
        "type_time":    mt5.ORDER_TIME_GTC,
        "type_filling": mt5.ORDER_FILLING_IOC,
    }
    res = mt5.order_send(req)
    if res and res.retcode == mt5.TRADE_RETCODE_DONE:
        log.info(f"FILLED | ticket={res.order} | {direction} {lots}L @ {res.price:.2f} "
                 f"SL={sl:.2f} TP={tp:.2f}")
        return res.order, res.price
    log.error(f"Order failed: {mt5.last_error()}")
    return None, None

def move_sl(ticket: int, new_sl: float):
    pos = mt5.positions_get(ticket=ticket)
    if not pos: return
    req = {"action":mt5.TRADE_ACTION_SLTP, "symbol":SYMBOL,
           "position":ticket, "sl":round(new_sl, 2), "tp":pos[0].tp}
    mt5.order_send(req)

def close_position(ticket: int, direction: str, reason: str = ""):
    pos = mt5.positions_get(ticket=ticket)
    if not pos: return False
    p          = pos[0]
    bid, ask   = get_tick()
    price      = bid if direction == "bullish" else ask
    close_type = mt5.ORDER_TYPE_SELL if direction == "bullish" else mt5.ORDER_TYPE_BUY
    req = {
        "action":       mt5.TRADE_ACTION_DEAL,
        "symbol":       SYMBOL,
        "volume":       p.volume,
        "type":         close_type,
        "position":     ticket,
        "price":        price,
        "deviation":    20,
        "magic":        MAGIC,
        "comment":      f"BOT_SCALPER-{reason}",
        "type_time":    mt5.ORDER_TIME_GTC,
        "type_filling": mt5.ORDER_FILLING_IOC,
    }
    res = mt5.order_send(req)
    if res and res.retcode == mt5.TRADE_RETCODE_DONE:
        log.info(f"CLOSED ticket={ticket} | reason={reason} @ {price:.2f}")
        return True
    return False

def close_all_positions(reason: str = "emergency"):
    positions = mt5.positions_get(symbol=SYMBOL)
    if not positions: return
    log.warning(f"CLOSE ALL — {reason} | {len(positions)} position(s)")
    for pos in positions:
        if pos.magic != MAGIC: continue
        bid, ask   = get_tick()
        price      = bid if pos.type == mt5.ORDER_TYPE_BUY else ask
        close_type = mt5.ORDER_TYPE_SELL if pos.type == mt5.ORDER_TYPE_BUY else mt5.ORDER_TYPE_BUY
        req = {
            "action":       mt5.TRADE_ACTION_DEAL,
            "symbol":       SYMBOL,
            "volume":       pos.volume,
            "type":         close_type,
            "position":     pos.ticket,
            "price":        price,
            "deviation":    30,
            "magic":        MAGIC,
            "comment":      f"BOT_SCALPER-{reason}",
            "type_time":    mt5.ORDER_TIME_GTC,
            "type_filling": mt5.ORDER_FILLING_IOC,
        }
        mt5.order_send(req)

def manage_positions(open_trades: list, atr: float, df_m5: pd.DataFrame):
    """
    Full position management:
    1. Breakeven at BE_ACTIVATION_R
    2. Trailing stop after breakeven
    3. Max hold time force close
    4. MOMENTUM REVERSAL — close if M5 bias flips against position while in profit
    5. Force close everything at 21:45 UTC (15 min before market close)
    """
    # Force close before market close
    if is_market_close() and open_trades:
        reason = "WEEKEND-CLOSE" if should_close_for_weekend() else "DAILY-CLOSE"
        log.info(f"Market closing in 15 min — closing all {len(open_trades)} scalp(s). [{reason}]")
        for t in open_trades[:]:
            pos = mt5.positions_get(ticket=t["ticket"])
            if pos:
                close_position(t["ticket"], t["dir"], reason)
            open_trades.remove(t)
        return

    current_bias, _ = get_m5_bias(df_m5)

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

        # FEATURE 5 — Momentum reversal detection
        # Close immediately if M5 bias fully flips against our position
        if current_bias is not None and current_bias != direction:
            if profit_r > 0:  # only close early if we're in profit
                log.info(f"T{t['ticket']} MOMENTUM FLIP — M5 bias now {current_bias}, "
                         f"we are {direction}. Closing at {profit_r:.1f}R.")
                if close_position(t["ticket"], direction, "MOMENTUM-FLIP"):
                    open_trades.remove(t)
                    continue

        # Breakeven at BE_ACTIVATION_R
        if profit_r >= BE_ACTIVATION_R and not t.get("be_done"):
            be = t["entry"]
            if direction == "bullish" and p.sl < be - 0.05:
                move_sl(t["ticket"], be)
                t["be_done"] = True
                t["peak"]    = price
                log.info(f"T{t['ticket']} BE @ {be:.2f} ({profit_r:.1f}R)")
            elif direction == "bearish" and p.sl > be + 0.05:
                move_sl(t["ticket"], be)
                t["be_done"] = True
                t["peak"]    = price
                log.info(f"T{t['ticket']} BE @ {be:.2f} ({profit_r:.1f}R)")

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
            log.info(f"T{t['ticket']} MAX HOLD ({MAX_HOLD_CANDLES} candles). Closing.")
            if close_position(t["ticket"], direction, "MAX-HOLD"):
                open_trades.remove(t)

def recover_open_positions() -> list:
    positions = mt5.positions_get(symbol=SYMBOL)
    if not positions: return []
    recovered = []
    for pos in positions:
        if pos.magic != MAGIC: continue
        direction = "bullish" if pos.type == mt5.ORDER_TYPE_BUY else "bearish"
        recovered.append({
            "ticket":       pos.ticket,
            "entry":        pos.price_open,
            "sl":           pos.sl,
            "dir":          direction,
            "peak":         pos.price_current,
            "be_done":      False,
            "candles_held": 0,
        })
        log.info(f"RECOVERED | ticket={pos.ticket} | {direction} @ {pos.price_open:.2f}")
    if recovered:
        log.info(f"Recovered {len(recovered)} position(s)")
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
    log.info("  BOT 3 — EMA MOMENTUM SCALPER")
    log.info(f"  Target: +{DAILY_TARGET_PCT}% daily | Ceil: +{DAILY_TARGET_PCT*DAILY_CEIL_MULT:.0f}% | "
             f"Trail: -{PEAK_DRAWDOWN_PCT}% from peak | Loss floor: -{DAILY_LOSS_CAP_PCT}%")
    log.info("=" * 65)

    if not connect(): return

    acct          = mt5.account_info()
    if acct.balance <= 0:
        log.error(f"Account balance is ${acct.balance:.2f} — demo account may have been reset. "
                  "Please restore balance before running BOT_SCALPER.")
        mt5.shutdown(); return
    calmar        = CalmarTracker(acct.balance, equity_file=str(_INST / "scalper_equity.json"))
    logger        = TradeLogger(str(_INST / "scalper_trades.json"))
    ai            = AIBrain(logger, model_file=str(_INST / "scalper_model.pkl"))

    start_balance = acct.balance
    daily_engine  = DailyProfitEngine(acct.balance)
    weekly_start  = acct.balance
    open_trades   = recover_open_positions()
    last_date     = now_utc().date()
    last_week     = now_utc().isocalendar()[1]
    consec_losses = 0

    log.info(f"Balance ${acct.balance:,.2f} | Risk tier: {get_risk_pct(acct.balance)}%")
    log_progress(acct.balance, start_balance)

    try:
        while True:
            now  = now_utc()

            # ── Market close — highest priority check ─────────────────────
            if is_market_close() and open_trades:
                reason = "WEEKEND-CLOSE" if should_close_for_weekend() else "DAILY-CLOSE"
                log.warning(f"MARKET CLOSE in 15 min [{reason}] — "
                            f"closing all {len(open_trades)} scalp(s) now.")
                for t in open_trades[:]:
                    pos = mt5.positions_get(ticket=t["ticket"])
                    if pos:
                        close_position(t["ticket"], t["dir"], reason)
                    if t in open_trades:
                        open_trades.remove(t)
                log.info("Positions closed. Bot stays running — no new entries during close window.")
            date = now.date()

            # ── Daily reset ───────────────────────────────────────────────
            if date != last_date:
                acct          = mt5.account_info()
                daily_engine  = DailyProfitEngine(acct.balance)
                last_date     = date
                consec_losses = 0
                calmar.record(acct.balance)
                calmar.log_report()
                log_progress(acct.balance, start_balance)
                log.info(f"New day | ${acct.balance:,.2f} | "
                         f"risk={get_risk_pct(acct.balance)}%")

            # ── Weekly reset ──────────────────────────────────────────────
            week = now.isocalendar()[1]
            if week != last_week:
                weekly_start = acct.balance
                last_week    = week
                log.info(f"New week | Reset ${weekly_start:,.2f}")

            acct = mt5.account_info()

            # ── Daily P&L engine check ────────────────────────────────────
            should_stop, stop_reason = daily_engine.update(acct.balance)
            if should_stop:
                log.warning(f"DAILY ENGINE: {stop_reason}")
                close_all_positions("daily-engine")
                # Log final day status
                log.info(f"Day locked | {daily_engine.status(acct.balance)}")
                calmar.record(acct.balance)
                log_progress(acct.balance, start_balance)
                # Wait until midnight UTC for daily reset
                while now_utc().date() == date:
                    df_m1 = get_candles(mt5.TIMEFRAME_M1, 50)
                    df_m5 = get_candles(mt5.TIMEFRAME_M5, 50)
                    if not df_m1.empty and not df_m5.empty:
                        manage_positions(open_trades,
                                         calc_atr(df_m1), df_m5)
                    time.sleep(60)
                continue

            # ── Weekly loss cap ───────────────────────────────────────────
            weekly_dd = ((weekly_start - acct.balance) / weekly_start) * 100
            if weekly_dd >= WEEKLY_LOSS_CAP_PCT:
                log.warning(f"WEEKLY CAP: -{weekly_dd:.1f}%. 6hr cooldown.")
                close_all_positions("weekly-cap")
                time.sleep(21600)
                continue

            # ── Consecutive loss cooldown ─────────────────────────────────
            if consec_losses >= 3:
                log.warning(f"{consec_losses} consecutive losses. 1hr cooldown.")
                time.sleep(3600)
                consec_losses = 0
                continue

            # ── Dead zone: 3pm-7pm Texas time ────────────────────────────
            if is_dead_zone():
                df_m1 = get_candles(mt5.TIMEFRAME_M1, 50)
                df_m5 = get_candles(mt5.TIMEFRAME_M5, 50)
                if not df_m1.empty and not df_m5.empty:
                    atr_dz = calc_atr(df_m1)
                    manage_positions(open_trades, atr_dz, df_m5)
                    handle_dead_zone(open_trades, atr_dz)
                if now.minute == 0:
                    log.info(f"Dead zone (3-7pm TX). No new entries. "
                             f"{daily_engine.status(acct.balance)}")
                time.sleep(60)
                continue

            # ── News event check ──────────────────────────────────────────
            news_status, sl_mult = get_news_status()
            if news_status == "active" and NEWS_PAUSE_MINS > 0 and NEWS_WIDEN_SL == 1.0:
                # Only pause if news_widen_sl is 1.0 (user chose not to widen)
                # If they set a widen mult, keep trading with wider SL
                log.warning("News blackout active. Pausing entries.")
                time.sleep(60)
                continue

            # ── Market data ───────────────────────────────────────────────
            df_m1 = get_candles(mt5.TIMEFRAME_M1, 120)
            df_m5 = get_candles(mt5.TIMEFRAME_M5, 120)
            if df_m1.empty or df_m5.empty:
                log.warning("No data from MT5. Retrying...")
                time.sleep(30)
                continue

            bid, ask = get_tick()
            spread   = ask - bid
            atr      = calc_atr(df_m1)

            # ── Manage existing positions ─────────────────────────────────
            manage_positions(open_trades, atr, df_m5)

            # ── Log status every hour ─────────────────────────────────────
            if now.minute == 0:
                log.info(daily_engine.status(acct.balance))

            # ── Signal detection ──────────────────────────────────────────
            signal = detect_scalp_signal(df_m1, df_m5, spread)
            if not signal:
                time.sleep(10)
                continue

            # ── AI gate ───────────────────────────────────────────────────
            daily_pnl = daily_engine.get_daily_pnl_pct(acct.balance)
            feats     = build_scalp_features(signal, daily_pnl, logger)
            take, ai_prob, ai_reason = ai.should_take_trade(feats, threshold=0.52)
            log.info(f"AI: {ai_reason}")
            if not take:
                time.sleep(10)
                continue

            # ── Entry, SL, TP (SL widens during news if configured) ───────
            direction = signal["direction"]
            sl_dist   = atr * ATR_SL_MULT * sl_mult  # sl_mult=1.0 normally, >1 during news

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
            lots = lot_size(acct.balance, sl_dist)

            log.info(f"SCALP SIGNAL | {direction.upper()} | "
                     f"price={signal['price']:.2f} | RSI={signal['rsi']:.1f} | "
                     f"stack={signal['stack_strength']}/3 | AI={ai_prob:.0%} | "
                     f"entry={entry:.2f} SL={sl:.2f} TP={tp:.2f} | "
                     f"{daily_engine.status(acct.balance)}")

            ticket, filled = place_order(direction, lots, sl, tp)

            if ticket:
                open_trades.append({
                    "ticket":       ticket,
                    "entry":        filled,
                    "sl":           sl,
                    "dir":          direction,
                    "peak":         filled,
                    "be_done":      False,
                    "candles_held": 0,
                })
                logger.log_entry(ticket, feats, direction, filled, sl, tp, tp)
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
    print("BOT SCALPER | XAUUSD Gold | XAUUSD")
    print("Dynamic compounding: $1,000 -> unlimited")
    print("Daily engine: runs until +30% OR 10% peak drawdown OR -8% floor\n")
    # Auto-confirm when running non-interactively (coordinator/Task Scheduler)
    # Prompt only when launched directly in a terminal
    import sys as _sys
    if not _sys.stdin.isatty() or input("Type CONFIRM to start: ").strip().upper() == "CONFIRM":
        run()
    else:
        print("Aborted.")
