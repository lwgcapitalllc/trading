"""
pnl_tracker.py — Real-Time P&L Engine

Runs every minute via SYS_PNLTRACKER task.
Pure math from trades JSON only — no MT5 connections.
Writes results to bot_state.json (single source of truth).
Sends Telegram alerts when thresholds are crossed.
"""

import json
import sys
from datetime import datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

try:
    import requests
except ImportError:
    print("pip install requests")
    sys.exit(1)

# Add shared dir to path
sys.path.insert(0, str(Path("C:/algos/shared")))
from bot_state import (
    BOT_INSTANCES, BOT_STARTING_BALANCES, BOT_THRESHOLDS, BOT_NAMES,
    read_bot, set_pnl, write_bot
)

TELEGRAM_TOKEN = "8888123776:AAFuWpPoKnHSmGwxNxRB9Qo61kDSk7w0YD8"
ADMIN_CHAT     = "429207285"
ALGOS_ROOT     = Path("C:/algos")
TEXAS          = ZoneInfo("America/Chicago")

# Trades files per bot
BOT_TRADES = {
    "smc_trend":      ALGOS_ROOT / "markets/fx/instances/gold_main/smc_trend_trades.json",
    "mean_reversion": ALGOS_ROOT / "markets/fx/instances/gold_main/mean_reversion_trades.json",
    "scalper":        ALGOS_ROOT / "markets/fx/instances/gold_scalper/scalper_trades.json",
    "fft":            ALGOS_ROOT / "markets/fx/instances/gold_fft/fft_trades.json",
}


def send_alert(message: str):
    try:
        requests.post(
            f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage",
            json={"chat_id": ADMIN_CHAT, "text": message, "parse_mode": "Markdown"},
            timeout=10
        )
    except Exception as e:
        print(f"Alert failed: {e}")


def load_trades(path: Path) -> list:
    if not path.exists():
        return []
    try:
        with open(path) as f:
            return json.load(f)
    except Exception:
        return []


def parse_dt(dt_str: str) -> datetime:
    try:
        return datetime.fromisoformat(dt_str.replace("Z", "+00:00"))
    except Exception:
        return datetime.utcnow().replace(tzinfo=ZoneInfo("UTC"))


def trade_pnl(t: dict, starting_balance: float) -> float:
    """Get dollar P&L for a trade."""
    if t.get("pnl_usd") is not None:
        return float(t["pnl_usd"])
    # Fallback: r_multiple × risk_usd
    r    = float(t.get("r_multiple") or 0)
    risk = float(t.get("risk_usd") or (starting_balance * 0.02))
    return round(r * risk, 2)


def calculate_pnl(bot_key: str) -> dict:
    """Pure math P&L from trades JSON."""
    trades  = load_trades(BOT_TRADES[bot_key])
    start   = BOT_STARTING_BALANCES[bot_key]

    now_tx     = datetime.now(TEXAS)
    today      = now_tx.date()
    week_start = today - timedelta(days=today.weekday())

    closed = [t for t in trades
              if t.get("outcome") in ("win", "loss", "breakeven")
              and t.get("closed_at")]

    # Check if any real pnl_usd data exists
    has_pnl_data = any(t.get("pnl_usd") is not None for t in closed)

    if not has_pnl_data and closed:
        # No pnl_usd yet — read balance from existing bot_state
        # Don't overwrite with bad calculation
        existing = read_bot(bot_key)
        balance  = existing.get("balance", start)
        total_profit = balance - start
    else:
        total_profit = sum(trade_pnl(t, start) for t in closed)

    current_balance = round(start + total_profit, 2)

    # Daily trades
    today_trades  = [t for t in closed
                     if parse_dt(t["closed_at"]).astimezone(TEXAS).date() == today]
    daily_profit  = sum(trade_pnl(t, start) for t in today_trades) if has_pnl_data else 0.0

    # Weekly trades
    week_trades   = [t for t in closed
                     if parse_dt(t["closed_at"]).astimezone(TEXAS).date() >= week_start]
    weekly_profit = sum(trade_pnl(t, start) for t in week_trades) if has_pnl_data else 0.0

    # Starting balances for % calc
    pre_today_profit  = (total_profit - daily_profit) if has_pnl_data else total_profit
    pre_week_profit   = (total_profit - weekly_profit) if has_pnl_data else total_profit
    daily_start       = round(start + pre_today_profit, 2)
    week_start_bal    = round(start + pre_week_profit, 2)

    # Peak balance
    peak    = start
    running = start
    for t in sorted(closed, key=lambda x: x.get("closed_at", "")):
        running += trade_pnl(t, start)
        peak     = max(peak, running)
    peak = max(peak, current_balance)

    return {
        "balance":        current_balance,
        "daily_pnl":      round(daily_profit, 2),
        "daily_pnl_pct":  round(daily_profit / daily_start * 100, 2) if daily_start else 0,
        "weekly_pnl":     round(weekly_profit, 2),
        "weekly_pnl_pct": round(weekly_profit / week_start_bal * 100, 2) if week_start_bal else 0,
        "total_pnl_pct":  round(total_profit / start * 100, 2),
        "peak_balance":   round(peak, 2),
        "trades_today":   len(today_trades),
        "has_pnl_data":   has_pnl_data,
    }


def check_alerts(bot_key: str, pnl: dict):
    """Send alerts if thresholds crossed. Uses bot_state for alert dedup."""
    state    = read_bot(bot_key)
    thresh   = BOT_THRESHOLDS[bot_key]
    now_tx   = datetime.now(TEXAS)
    today    = now_tx.date().isoformat()
    now_str  = now_tx.strftime("%I:%M %p CT")
    name     = BOT_NAMES[bot_key]
    bal      = pnl["balance"]

    # Reset daily alerts on new day
    if state.get("alert_date") != today:
        write_bot(bot_key, {
            "alert_date":        today,
            "goal_alerted":      False,
            "daily_cap_alerted": False,
        })
        state = read_bot(bot_key)

    daily_pct  = pnl["daily_pnl_pct"]
    weekly_pct = pnl["weekly_pnl_pct"]

    if not pnl["has_pnl_data"]:
        return  # Don't send alerts if data isn't reliable yet

    # Daily goal
    if daily_pct >= thresh["daily_goal"] and not state.get("goal_alerted"):
        send_alert(
            f"🎯 *ALERT — Daily Goal Hit*\n"
            f"{name}\n"
            f"Today: +{daily_pct:.1f}% (+${pnl['daily_pnl']:.2f})\n"
            f"Balance: ${bal:,.2f}\n"
            f"Time: {now_str}"
        )
        write_bot(bot_key, {"goal_alerted": True})

    # Daily loss cap
    if daily_pct <= -thresh["daily_cap"] and not state.get("daily_cap_alerted"):
        send_alert(
            f"🛑 *ALERT — Daily Loss Cap Hit*\n"
            f"{name}\n"
            f"Today: {daily_pct:.1f}% (-${abs(pnl['daily_pnl']):.2f})\n"
            f"Balance: ${bal:,.2f}\n"
            f"No new entries until tomorrow\n"
            f"Time: {now_str}"
        )
        write_bot(bot_key, {"daily_cap_alerted": True})

    # Weekly loss cap
    if weekly_pct <= -thresh["weekly_cap"] and not state.get("weekly_cap_alerted"):
        send_alert(
            f"🚫 *ALERT — Weekly Loss Cap Hit*\n"
            f"{name}\n"
            f"Weekly: {weekly_pct:.1f}% (-${abs(pnl['weekly_pnl']):.2f})\n"
            f"Balance: ${bal:,.2f}\n"
            f"Time: {now_str}"
        )
        write_bot(bot_key, {"weekly_cap_alerted": True})


def main():
    now = datetime.now(TEXAS).strftime("%I:%M %p CT")
    for bot_key in BOT_TRADES:
        try:
            pnl = calculate_pnl(bot_key)

            set_pnl(
                bot_key,
                balance        = pnl["balance"],
                daily_pnl      = pnl["daily_pnl"],
                daily_pnl_pct  = pnl["daily_pnl_pct"],
                weekly_pnl     = pnl["weekly_pnl"],
                weekly_pnl_pct = pnl["weekly_pnl_pct"],
                total_pnl_pct  = pnl["total_pnl_pct"],
                peak_balance   = pnl["peak_balance"],
                trades_today   = pnl["trades_today"],
            )

            check_alerts(bot_key, pnl)

            print(
                f"{bot_key}: ${pnl['balance']:,.2f} | "
                f"day={pnl['daily_pnl_pct']:+.1f}% | "
                f"week={pnl['weekly_pnl_pct']:+.1f}% | "
                f"trades={pnl['trades_today']}"
                + (" [estimated]" if not pnl["has_pnl_data"] else "")
            )

        except Exception as e:
            print(f"Error {bot_key}: {e}")

    print(f"P&L tracker done — {now}")


if __name__ == "__main__":
    main()
