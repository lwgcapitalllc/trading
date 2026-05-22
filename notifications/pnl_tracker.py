"""
pnl_tracker.py — Real-Time P&L Engine

Runs every minute via SYS_PNLTRACKER task.
Writes results to bot_state.json (single source of truth).
Sends Telegram alerts when thresholds are crossed.

MT5 is the only source of truth. When a bot is offline (last_write stale),
this script does nothing — it preserves the last-known state and skips all alerts.
"""

import json
import sys
from datetime import datetime, timezone
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
    BOT_STARTING_BALANCES, BOT_THRESHOLDS, BOT_NAMES,
    read_bot, set_pnl, write_bot
)

TELEGRAM_TOKEN  = "8888123776:AAFuWpPoKnHSmGwxNxRB9Qo61kDSk7w0YD8"
ADMIN_CHAT      = "429207285"
GROUP_CHAT      = "-1003977707258"
ALGOS_ROOT      = Path("C:/algos")
TEXAS           = ZoneInfo("America/Chicago")
BOT_LIVE_WINDOW = 300  # seconds — treat bot as live if last_write is within this

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
            json={"chat_id": GROUP_CHAT, "text": message, "parse_mode": "Markdown"},
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
        return datetime.now(timezone.utc)


def trade_pnl(t: dict, starting_balance: float) -> float:
    if t.get("pnl_usd") is not None:
        return float(t["pnl_usd"])
    r    = float(t.get("r_multiple") or 0)
    risk = float(t.get("risk_usd") or (starting_balance * 0.02))
    return round(r * risk, 2)


def _bot_is_live(state: dict) -> bool:
    """True if the bot wrote to bot_state within BOT_LIVE_WINDOW seconds."""
    last_write = state.get("last_write")
    if not last_write:
        return False
    try:
        lw = datetime.fromisoformat(last_write)
        if lw.tzinfo is None:
            lw = lw.replace(tzinfo=timezone.utc)
        age = (datetime.now(timezone.utc) - lw).total_seconds()
        return age < BOT_LIVE_WINDOW
    except Exception:
        return False


def _peak_from_trades(bot_key: str, closed: list) -> float:
    """Walk closed trade history to find the peak running balance."""
    start = BOT_STARTING_BALANCES[bot_key]
    peak = running = start
    for t in sorted(closed, key=lambda x: x.get("closed_at", "")):
        running += trade_pnl(t, start)
        peak = max(peak, running)
    return peak


def _calculate_pnl_live(bot_key: str, state: dict) -> dict:
    """
    Bot is running — use MT5-authoritative values from bot_state.
    Computes daily/weekly P&L from bot-written daily_start/weekly_start.
    """
    balance      = float(state["balance"])
    daily_start  = float(state["daily_start"])
    weekly_start = float(state["weekly_start"])

    daily_pnl    = balance - daily_start
    weekly_pnl   = balance - weekly_start

    daily_pnl_pct  = daily_pnl / daily_start * 100 if daily_start else 0.0
    weekly_pnl_pct = weekly_pnl / weekly_start * 100 if weekly_start else 0.0

    start          = BOT_STARTING_BALANCES[bot_key]
    total_pnl_pct  = (balance - start) / start * 100 if start else 0.0

    # Trade count from file (doesn't affect P&L math, just informational)
    trades       = load_trades(BOT_TRADES[bot_key])
    today_tx     = datetime.now(TEXAS).date()
    closed       = [t for t in trades
                    if t.get("outcome") in ("win", "loss", "breakeven")
                    and t.get("closed_at")]
    today_trades = [t for t in closed
                    if parse_dt(t["closed_at"]).astimezone(TEXAS).date() == today_tx]

    peak = max(_peak_from_trades(bot_key, closed), balance)

    return {
        "balance":        round(balance, 2),
        "daily_pnl":      round(daily_pnl, 2),
        "daily_pnl_pct":  round(daily_pnl_pct, 2),
        "weekly_pnl":     round(weekly_pnl, 2),
        "weekly_pnl_pct": round(weekly_pnl_pct, 2),
        "total_pnl_pct":  round(total_pnl_pct, 2),
        "peak_balance":   round(peak, 2),
        "trades_today":   len(today_trades),
    }


def calculate_pnl(bot_key: str) -> dict | None:
    """Returns live P&L dict, or None if the bot is offline. Never infers from trades.json."""
    state = read_bot(bot_key)
    if _bot_is_live(state):
        return _calculate_pnl_live(bot_key, state)
    return None


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
            "day_locked":        False,
            "lock_alerted":      False,
            "lock_reason":       "",
        })
        state = read_bot(bot_key)

    daily_pct  = pnl["daily_pnl_pct"]
    weekly_pct = pnl["weekly_pnl_pct"]

    # Day locked (peak protection or ceiling hit)
    if state.get("day_locked") and not state.get("lock_alerted"):
        reason = state.get("lock_reason", "Daily engine triggered")
        send_alert(
            f"🔒 *Bot {name} — Day Locked*\n"
            f"{reason}\n"
            f"Balance: ${bal:,.2f}\n"
            f"No new trades until midnight UTC\n"
            f"Override: `/resume {bot_key}`\n"
            f"Time: {now_str}"
        )
        write_bot(bot_key, {"lock_alerted": True})

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

            if pnl is None:
                print(f"{bot_key}: offline — skipping alerts, preserving last-known state")
                continue

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
            )

        except Exception as e:
            print(f"Error {bot_key}: {e}")

    print(f"P&L tracker done — {now}")


if __name__ == "__main__":
    main()
