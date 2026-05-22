"""
╔══════════════════════════════════════════════════════════════════════════════╗
║  BOT 5 — FFT (Fibonacci Fractal Trading) STRATEGY (MULTI-INSTRUMENT)       ║
║  Watchlist: configured per instance — gold-only until Phase 5 gate.        ║
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

import json
import sys
import time
from datetime import datetime, timezone, timedelta
from pathlib import Path

import MetaTrader5 as mt5
import numpy as np
import pandas as pd

# ── Path setup ────────────────────────────────────────────────────────────────
sys.path.insert(0, str(Path(__file__).parent))
sys.path.insert(0, str(Path(__file__).parent.parent / "shared"))

from bot_utils       import load_config, setup_logging, get_instance_dir, load_weekly_start
from shared_ai_brain import AIBrain, TradeLogger, DailyLogger, build_features_trend
from shared_calmar   import CalmarTracker
from shared_regime   import RegimeClassifier
from shared_scanner  import InstrumentScanner
from shared_risk     import RiskEngine, CorrelationGuard
from bot_state       import write_bot, read_bot, set_started, ensure_starting_balance
from notify          import send_telegram
from mt5_ops         import (BotMT5, now_utc, is_market_close,
                              should_close_for_weekend, is_dead_zone, get_atr, get_ema)
from structure_engine import StructureEngine

# ── Load config ───────────────────────────────────────────────────────────────
_CFG  = load_config()
log   = setup_logging("BOT_FFT", _CFG)
_INST = get_instance_dir(_CFG)

# Symbol and account
SYMBOL   = _CFG.get("symbol", "XAUUSD.s")
ACCOUNT  = _CFG.get("account", {})

# Strategy params (all configurable via config.json)
_S = _CFG.get("bot_fft", {})

WATCHLIST          = _S.get("watchlist", [SYMBOL])
MIN_ATR_RATIO      = _S.get("min_atr_ratio", 0.8)
FORCE_TRADE        = _S.get("force_trade", False)
CORR_ACTION        = _S.get("correlation_action", "block")

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
DAILY_BUDGET_PCT    = _S.get("daily_budget_pct", MAX_DAILY_LOSS)
MAX_WEEKLY_LOSS     = _S.get("max_weekly_loss_pct", 15.0)
MAX_TRADES_DAY      = _S.get("max_trades_per_day", 3)
MIN_AI_PROB         = _S.get("min_ai_probability", 0.52)

# Dead zone (gold market close window — CT local hours, DST-aware)
_DZ             = _CFG.get("dead_zone", {})
DEAD_ZONE_START = _DZ.get("start_ct", 16)
DEAD_ZONE_END   = _DZ.get("end_ct",   17)

# Timeframes
TF_ENTRY  = mt5.TIMEFRAME_M15
TF_TREND  = mt5.TIMEFRAME_H1
TF_HIGHER = mt5.TIMEFRAME_H4

# Magic number for this bot
MAGIC = 20240005

log.info(f"BOT_FFT | FFT Strategy | watchlist={WATCHLIST} | risk={RISK_PCT}%")

_mt5 = BotMT5(SYMBOL, MAGIC, "BOT_FFT", _CFG, ACCOUNT, log)


# =============================================================================
# MT5 HELPERS — delegates to shared BotMT5 instance
# =============================================================================

def connect() -> bool:                   return _mt5.connect()
def get_candles(tf, n, symbol=None):     return _mt5.get_candles(tf, n, symbol)
def get_tick(symbol=None) -> tuple:      return _mt5.get_tick(symbol)
def get_deal_result(t):                  return _mt5.get_deal_result(t)
def close_position(t, d, r=""):          return _mt5.close_position(t, d, r)
def close_all_positions(r=""):           return _mt5.close_all_positions(r, WATCHLIST)
def move_sl(t, sl, tp=None):             return _mt5.move_sl(t, sl, tp)
def handle_dead_zone(ot, atr, logger, ai): return _mt5.handle_dead_zone(ot, atr, logger, ai)
def reconcile_on_startup(ot, logger, ai):  return _mt5.reconcile_on_startup(ot, logger, ai)
def write_live_state(weekly_start, daily_start):
    return _mt5.write_live_state("fft", weekly_start, daily_start)

def lot_size(balance: float, sl_distance: float,
             risk_mult: float = 1.0, symbol: str = None,
             risk_pct: float = None) -> float:
    """Position size. risk_pct overrides RISK_PCT * risk_mult when provided."""
    rp = risk_pct if risk_pct is not None else RISK_PCT * risk_mult
    return _mt5.lot_size(balance, sl_distance, rp, 1.0, symbol)

def place_order(direction: str, lots: float, sl: float,
                tp: float, comment: str = "FFT", symbol: str = None) -> tuple:
    """Place a market order; returns (ticket, fill_price) or (None, None)."""
    return _mt5.place_order(direction, lots, sl, tp, comment=comment, symbol=symbol)


def recover_open_positions() -> list:
    """
    On bot restart, recover any open positions placed by this bot
    so we can continue managing them (breakeven, TP2).
    """
    recovered = []
    for symbol in WATCHLIST:
        positions = mt5.positions_get(symbol=symbol)
        if not positions:
            continue
        for p in positions:
            if p.magic != MAGIC:
                continue
            direction = "bullish" if p.type == mt5.ORDER_TYPE_BUY else "bearish"
            df_m15 = get_candles(TF_ENTRY, 50, symbol)
            atr    = get_atr(df_m15) if not df_m15.empty else None
            recovered.append({
                "ticket":     p.ticket,
                "entry":      p.price_open,
                "sl":         p.sl,
                "tp":         p.tp,
                "dir":        direction,
                "lots":       p.volume,
                "be_done":    False,
                "tp1_done":   False,
                "fft_levels": None,  # recalculated on next signal
                "symbol":     symbol,
                "atr":        atr,
            })
            log.info(f"RECOVERED | {symbol} | ticket={p.ticket} | {direction} @ {p.price_open:.5f}")
    if recovered:
        log.info(f"Recovered {len(recovered)} open FFT position(s).")
    return recovered


# =============================================================================
# STRUCTURE DETECTION — StructureEngine wrapper
# =============================================================================

def _run_structure_engine(df: pd.DataFrame):
    """
    Replay df through StructureEngine and return (engine, result).
    Returns (None, None) if the engine hasn't bootstrapped or the leg isn't
    established with a retracement underway.
    """
    eng = StructureEngine()
    result = eng.replay(df)
    return eng, result


def _build_bos_dict(result, eng) -> dict | None:
    """
    Map a StructureResult to the bos-dict format expected by calc_fft_levels /
    calc_sniper_levels.  Returns None if required anchors are missing.

    Bullish fib anchors:
      fft_low      = prev_swing_low.body  (HL at leg start — body close)
      fft_high     = swing_high.wick      (top wick of new HH)
      counter_high = swing_low.body       (old HH promoted to new HL — sniper top)
      counter_low  = prev_swing_low.body  (same as fft_low — sniper bottom)

    Bearish mirrors the above.
    """
    if not result.leg_established or result.bias == "undecided":
        return None

    if result.swing_high is None or result.swing_low is None:
        return None

    if result.bias == "bullish":
        psl = result.prev_swing_low
        fft_low = psl.body if psl is not None else result.swing_low.body
        return {
            "direction":    "bullish",
            "bos_price":    result.swing_high.body,
            "fft_low":      fft_low,
            "fft_high":     result.swing_high.wick,
            "counter_high": result.swing_low.body,
            "counter_low":  fft_low,
        }
    else:  # bearish
        psh = result.prev_swing_high
        fft_high = psh.body if psh is not None else result.swing_high.body
        return {
            "direction":    "bearish",
            "bos_price":    result.swing_low.body,
            "fft_high":     fft_high,
            "fft_low":      result.swing_low.wick,
            "counter_high": fft_high,
            "counter_low":  result.swing_high.body,
        }


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

def manage_positions(open_trades: list, logger, ai):
    """
    Manage all open FFT positions:
    - Move to breakeven at 0.5R
    - Close TP1 portion at TP1 level (80% of position — handled at order placement)
    - Trail remaining position after TP1

    Note: TP2 is placed as a hard TP on the order. TP1 requires partial close
    which at 0.01 lots means full close. The bot handles this via order monitoring.
    """
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
        price     = p.price_current
        entry     = t["entry"]
        sl        = t["sl"]
        direction = t["dir"]
        sl_dist   = abs(entry - sl)

        if sl_dist == 0:
            continue

        if direction == "bullish":
            profit_r = (price - entry) / sl_dist
        else:
            profit_r = (entry - price) / sl_dist

        # Move to breakeven at 0.5R
        if profit_r >= BE_R and not t.get("be_done"):
            ok = move_sl(t["ticket"], entry)
            if ok:
                t["be_done"] = True
                t["sl"]      = entry
                sym = t.get("symbol", SYMBOL)
                log.info(f"T{t['ticket']} [{sym}] -> BREAKEVEN @ {entry:.5f} ({profit_r:.2f}R)")


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
# SCANNER CALLBACK
# =============================================================================

def detect_setup(symbol: str) -> dict | None:
    """
    InstrumentScanner callback: evaluate `symbol` for an FFT entry setup.
    Returns a dict (with 'score' key) if valid, None otherwise.
    All heavy strategy logic lives here so run() stays clean.
    """
    df_m15 = get_candles(TF_ENTRY,  150, symbol)
    df_h1  = get_candles(TF_TREND,   50, symbol)
    df_h4  = get_candles(TF_HIGHER,  50, symbol)
    if df_m15.empty or df_h1.empty or df_h4.empty:
        return None

    bid, ask = get_tick(symbol)
    price    = (bid + ask) / 2
    if price == 0:
        return None

    atr = get_atr(df_m15)

    h1_trend = get_trend(df_h1, 200)
    h4_trend = get_trend(df_h4, 200)
    if h1_trend == "neutral" or h4_trend == "neutral":
        return None

    eng, result = _run_structure_engine(df_m15)

    if not result.leg_established or result.bias == "undecided":
        return None

    if result.bias != h1_trend:
        return None

    if not eng._retracement_fired:
        return None

    bos = _build_bos_dict(result, eng)
    if not bos:
        return None

    fft     = calc_fft_levels(bos)
    sniper  = calc_sniper_levels(bos)
    overlap = check_green_zone_overlap(fft, sniper)
    if not overlap:
        return None

    if not price_in_entry_zone(price, fft, sniper):
        return None

    session = get_session(now_utc().hour)
    fvg     = detect_fvg(df_m15, bos["direction"])
    score   = score_setup(bos, fft, sniper, overlap, h1_trend, h4_trend, fvg, session)

    if score < 4:
        return None

    return {
        "score":    score,
        "bos":      bos,
        "fft":      fft,
        "sniper":   sniper,
        "overlap":  overlap,
        "h1_trend": h1_trend,
        "h4_trend": h4_trend,
        "fvg":      fvg,
        "session":  session,
        "price":    price,
        "atr":      atr,
        "bid":      bid,
        "ask":      ask,
        "df_h4":    df_h4,
        "df_m15":   df_m15,
    }


# =============================================================================
# MAIN BOT LOOP
# =============================================================================

def run():
    log.info("=" * 65)
    log.info("  BOT 5 — FFT (Fibonacci Fractal Trading) STRATEGY")
    log.info(f"  Symbol: {SYMBOL} | Risk: {RISK_PCT}%")
    log.info(f"  Entry zone: {FFT_ENTRY_MIN*100:.1f}–{FFT_ENTRY_MAX*100:.1f}% | "
             f"Structure engine: event-driven BOS/SOS/RETRACEMENT")
    log.info("=" * 65)
    set_started("fft")
    send_telegram("🟢 *FFT online*")

    if not connect():
        return

    acct = mt5.account_info()
    if not acct or acct.balance <= 0:
        log.error(f"Account balance is ${acct.balance if acct else 0:.2f}. "
                  "Cannot start. Check credentials and MT5_FFT terminal.")
        _mt5.disconnect()
        return
    ensure_starting_balance("fft", acct.balance)

    # Shared components
    regime      = RegimeClassifier(bot_name="BOT_FFT")
    logger      = TradeLogger(str(_INST / "fft_trades.json"))
    ai          = AIBrain(logger, model_file=str(_INST / "fft_model.pkl"))
    calmar      = CalmarTracker(acct.balance,
                                equity_file=str(_INST / "fft_equity.json"))
    daily_log   = DailyLogger(str(_INST / "fft_daily.json"))
    scanner       = InstrumentScanner(WATCHLIST, "BOT_FFT", "fft", _INST, log,
                                      min_atr_ratio=MIN_ATR_RATIO, force_trade=FORCE_TRADE)
    risk_engine   = RiskEngine("BOT_FFT", DAILY_BUDGET_PCT, log)
    corr_guard    = CorrelationGuard(_CFG.get("correlation_map", []), log)

    # State
    daily_start       = acct.balance
    weekly_start      = acct.balance
    trades_today      = 0
    max_open_today    = 0
    min_balance_today = acct.balance
    open_trades       = recover_open_positions()
    reconcile_on_startup(open_trades, logger, ai)
    risk_engine.reset_day(acct.balance)
    last_date         = now_utc().date()
    last_week         = now_utc().isocalendar()[1]
    trading_halted    = False
    consec_losses     = 0

    _cur_week    = now_utc().isocalendar()[1]
    weekly_start = load_weekly_start("fft", _cur_week, acct.balance)
    log.info(f"Weekly start: ${weekly_start:,.2f} (week {_cur_week})")

    log.info(f"Balance ${acct.balance:,.2f} | {ai.status_report()}")

    # Track last detected setup to avoid re-entering same zone
    last_setup_id = None

    try:
        while True:
            now  = now_utc()
            date = now.date()
            week = now.isocalendar()[1]
            write_bot("fft", {"heartbeat": time.time()})

            # ── Market close force-close ──────────────────────────────────
            if is_market_close() and open_trades:
                reason = "WEEKEND-CLOSE" if now.weekday() >= 4 else "DAILY-CLOSE"
                log.warning(f"MARKET CLOSE [{reason}] — closing {len(open_trades)} position(s)")
                for t in open_trades[:]:
                    pos = mt5.positions_get(ticket=t["ticket"])
                    if pos:
                        ok, cp, pnl = close_position(t["ticket"], t["dir"], reason)
                        if ok:
                            logger.log_close(t["ticket"], cp, pnl)
                            ai.on_trade_closed(t["ticket"], cp, pnl)
                open_trades.clear()

            acct = write_live_state(weekly_start, daily_start)
            if acct is None:
                time.sleep(30); continue

            if read_bot("fft").get("reset_requested"):
                weekly_start = daily_start = acct.balance
                write_bot("fft", {
                    "reset_requested":    False,
                    "weekly_start":       weekly_start,
                    "daily_start":        daily_start,
                    "last_week":          now_utc().isocalendar()[1],
                    "weekly_cap_alerted": False,
                    "goal_alerted":       False,
                    "daily_cap_alerted":  False,
                })
                log.info(f"Balance references reset to ${weekly_start:,.2f} (user request)")

            # ── Dead zone: gold market close — no new entries ─────────────
            if is_dead_zone(DEAD_ZONE_START, DEAD_ZONE_END):
                handle_dead_zone(open_trades, 0.0, logger, ai)
                if now.minute == 0:
                    log.info(f"Dead zone ({DEAD_ZONE_START}:00–{DEAD_ZONE_END}:00 CT) — no new FFT entries.")
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
                risk_engine.reset_day(acct.balance)
                calmar.record(acct.balance)
                calmar.log_report()
                write_bot("fft", {"unresolved_symbols_alerted": {}})
                log.info(f"New day {date} | ${acct.balance:,.2f} | {ai.status_report()}")

            # ── Weekly reset ──────────────────────────────────────────────
            if week != last_week:
                weekly_start   = acct.balance
                last_week      = week
                trading_halted = False
                consec_losses  = 0
                write_bot("fft", {"last_week": week, "weekly_start": weekly_start})
                log.info(f"New week {week} | Weekly start: ${weekly_start:,.2f}")

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
                manage_positions(open_trades, logger, ai)
                time.sleep(60)
                continue

            # ── Weekly loss cap ───────────────────────────────────────────
            weekly_dd = (weekly_start - acct.balance) / weekly_start * 100
            if weekly_dd >= MAX_WEEKLY_LOSS:
                if not trading_halted:
                    log.warning(f"WEEKLY CAP: -{weekly_dd:.1f}%. 6hr cooldown.")
                    for _t, _cp, _pnl in close_all_positions("weekly-cap"):
                        _m = next((x for x in open_trades if x["ticket"] == _t), None)
                        if _m:
                            logger.log_close(_t, _cp, _pnl)
                            ai.on_trade_closed(_t, _cp, _pnl)
                            open_trades.remove(_m)
                    calmar.record(acct.balance)
                    write_bot("fft", {
                        "day_locked":     True,
                        "lock_reason":    f"WEEKLY CAP: -{weekly_dd:.1f}% weekly loss",
                        "lock_alerted":   False,
                        "resume_trading": False,
                    })
                    trading_halted  = True
                    cooldown_end = datetime.now(timezone.utc) + timedelta(hours=6)
                    while datetime.now(timezone.utc) < cooldown_end:
                        if read_bot("fft").get("resume_trading"):
                            write_bot("fft", {"day_locked": False, "resume_trading": False})
                            log.warning("WEEKLY CAP RESUME: user override — resuming early.")
                            break
                        time.sleep(60)
                    else:
                        write_bot("fft", {"day_locked": False})
                    trading_halted = False
                continue

            if trading_halted:
                trading_halted = False

            # ── Daily trade limit ─────────────────────────────────────────
            if trades_today >= MAX_TRADES_DAY:
                manage_positions(open_trades, logger, ai)
                if now.minute == 0:
                    log.info(f"Daily trade limit {MAX_TRADES_DAY} reached. "
                             "Managing open positions only.")
                time.sleep(60)
                continue

            # ── Manage open positions ─────────────────────────────────────
            trades_before = len(open_trades)
            manage_positions(open_trades, logger, ai)
            if len(open_trades) < trades_before:
                acct = mt5.account_info()
                if acct:
                    calmar.record(acct.balance)

            # ── Regime check (primary symbol H1/H4 for Phase 1) ───────────
            df_h1_primary = get_candles(TF_TREND,  50)
            df_h4_primary = get_candles(TF_HIGHER, 50)
            if df_h1_primary.empty or df_h4_primary.empty:
                time.sleep(30)
                continue
            reg_result = regime.classify(df_h1_primary, df_h4_primary)
            reg_state  = reg_result["regime"]
            risk_mult  = reg_result["risk_multiplier"]
            if reg_state == "RANGING":
                log.info("Regime RANGING — FFT strategy needs trending. Waiting.")
                time.sleep(60)
                continue

            # ── Risk capacity gate (Phase 3) ───────────────────────────────
            proposed_risk = RISK_PCT * risk_mult
            _allowed, effective_risk = risk_engine.evaluate(open_trades, acct.balance, proposed_risk)
            if not _allowed:
                time.sleep(60); continue

            # ── Wait for breakeven before opening another position ────────
            if open_trades and not all(t.get("be_done", False) for t in open_trades):
                time.sleep(60); continue

            # ── Scanner: find best setup across watchlist ─────────────────
            candidates = scanner.scan(detect_setup, watchlist=WATCHLIST)
            if not candidates:
                time.sleep(60)
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
                log.info("CorrelationGuard: all candidates blocked — waiting 60s.")
                time.sleep(60); continue

            symbol = best.symbol
            setup  = best.setup

            bos     = setup["bos"]
            fft     = setup["fft"]
            sniper  = setup["sniper"]
            overlap = setup["overlap"]
            score   = setup["score"]
            atr     = setup["atr"]
            price   = setup["price"]
            bid     = setup["bid"]
            ask     = setup["ask"]
            df_h4   = setup["df_h4"]
            h4_trend = setup["h4_trend"]
            fvg      = setup["fvg"]
            session  = setup["session"]

            # ── Avoid re-entering same zone ───────────────────────────────
            setup_id = f"{symbol}_{bos['direction']}_{bos['bos_price']:.1f}"
            if setup_id == last_setup_id:
                time.sleep(60)
                continue

            log.info(f"SETUP | {symbol} | {bos['direction'].upper()} | score={score}/10 | "
                     f"session={session} | FVG={fvg} | deep={overlap['is_deep']}")

            # ── Calculate TPs ─────────────────────────────────────────────
            tp1_price, tp2_price = calc_take_profits(fft, overlap)

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
            log.info(f"AI [{symbol}]: {ai_reason}")
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

            lots = lot_size(acct.balance, sl_dist, risk_mult, symbol, risk_pct=effective_risk)
            if lots <= 0:
                time.sleep(60)
                continue

            log.info(f"SIGNAL | {symbol} | {bos['direction'].upper()} | "
                     f"score={score} | AI={ai_prob:.0%} | "
                     f"entry={entry_price:.5f} SL={sl_price:.5f} | "
                     f"TP1={tp1_price:.5f} TP2={tp2_price:.5f} | "
                     f"R:R={rr:.2f} | lots={lots}")

            # ── Place order ───────────────────────────────────────────────
            ticket, filled = place_order(
                bos["direction"], lots, sl_price, tp1_price,
                comment=f"FFT-E1-s{score}", symbol=symbol
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
                    "symbol":     symbol,
                    "atr":        atr,
                })
                risk_usd = acct.balance * (RISK_PCT / 100) * risk_mult
                logger.log_entry(ticket, feats, bos["direction"],
                                 filled, sl_price, tp1_price, tp2_price,
                                 risk_usd=risk_usd)
                trades_today  += 1
                consec_losses  = 0
                last_setup_id  = setup_id

                log.info(f"Trade #{trades_today} today | FFT setup confirmed.")

                # ── Entry 2: sniper 38.2% if lots allow ───────────────────
                if lots >= 0.02:
                    entry2_price = sniper["sniper_38_2"]
                    lots2        = round(lots * 0.5 / 0.01) * 0.01
                    lots2        = max(0.01, lots2)
                    ticket2, filled2 = place_order(
                        bos["direction"], lots2, sl_price, tp2_price,
                        comment=f"FFT-E2-s{score}", symbol=symbol
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
                            "symbol":     symbol,
                            "atr":        atr,
                        })
                        risk_usd2 = acct.balance * (RISK_PCT / 100) * risk_mult * 0.5
                        logger.log_entry(ticket2, feats, bos["direction"],
                                         filled2, sl_price, tp2_price, tp2_price,
                                         risk_usd=risk_usd2)
                        log.info(f"Entry 2 placed @ {filled2:.5f} | "
                                 f"TP={tp2_price:.5f} | lots={lots2}")

                for _ in range(5):
                    time.sleep(60)
                    write_bot("fft", {"heartbeat": time.time()})
            else:
                consec_losses += 1
                log.warning(f"Order failed. Consecutive: {consec_losses}")
                time.sleep(60)

    except KeyboardInterrupt:
        log.info("Stopped by user.")
    except Exception as e:
        log.exception(f"Unexpected error: {e}")
        send_telegram(f"🔴 *FFT crashed*: `{e}`")
    finally:
        _mt5.disconnect()


if __name__ == "__main__":
    run()
