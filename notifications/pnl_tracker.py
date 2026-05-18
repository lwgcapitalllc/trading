"""
pnl_tracker.py — Real-Time P&L Engine

Runs every minute via SYS_PNLTRACKER task.
Reads ONLY from trades JSON files — pure math, no MT5 connections,
no dependency on equity files or stdout logs.

For each bot:
1. Loads all closed trades from trades JSON
2. Calculates from scratch:
   - Starting balance (from config: account_starting_balance)
   - Current balance = starting + sum of all closed trade P&L
   - Daily P&L = sum of today's closed trade P&L
   - Weekly P&L = sum of this week's closed trade P&L
   - Peak balance since week start
   - Drawdown from peak
3. Writes updated equity file
4. Writes updated weekly file
5. Sends Telegram alerts if thresholds crossed
6. Updates monitor_state so other tools see accurate data

Install: pip install requests
Run:     python notifications/pnl_tracker.py
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

TELEGRAM_TOKEN = "8888123776:AAFuWpPoKnHSmGwxNxRB9Qo61kDSk7w0YD8"
ADMIN_CHAT     = "429207285"
ALGOS_ROOT     = Path("C:/algos")
STATE_FILE     = ALGOS_ROOT / "pnl_state.json"
TEXAS          = ZoneInfo("America/Chicago")

# ── Bot definitions ──────────────────────────────────────────────────────────
# starting_balance: the very first deposit — used as the base for all calculations
BOTS = {
    "smc_trend": {
        "name":              "Bot SMC Trend",
        "trades":            ALGOS_ROOT / "markets/fx/instances/gold_main/smc_trend_trades.json",
        "equity":            ALGOS_ROOT / "markets/fx/instances/gold_main/gold_main_equity.json",
        "weekly":            ALGOS_ROOT / "markets/fx/instances/gold_main/smc_trend_weekly.json",
        "starting_balance":  1000.0,   # original deposit
        "daily_cap_pct":     10.0,
        "weekly_cap_pct":    20.0,
        "daily_goal_pct":    2.0,
    },
    "mean_reversion": {
        "name":              "Bot Mean Reversion",
        "trades":            ALGOS_ROOT / "markets/fx/instances/gold_main/mean_reversion_trades.json",
        "equity":            ALGOS_ROOT / "markets/fx/instances/gold_main/gold_main_equity.json",
        "weekly":            ALGOS_ROOT / "markets/fx/instances/gold_main/mean_reversion_weekly.json",
        "starting_balance":  1000.0,
        "daily_cap_pct":     10.0,
        "weekly_cap_pct":    20.0,
        "daily_goal_pct":    2.0,
    },
    "scalper": {
        "name":              "Bot Scalper",
        "trades":            ALGOS_ROOT / "markets/fx/instances/gold_scalper/scalper_trades.json",
        "equity":            ALGOS_ROOT / "markets/fx/instances/gold_scalper/scalper_equity.json",
        "weekly":            ALGOS_ROOT / "markets/fx/instances/gold_scalper/scalper_weekly.json",
        "starting_balance":  1000.0,
        "daily_cap_pct":     8.0,
        "weekly_cap_pct":    20.0,
        "daily_goal_pct":    10.0,
    },
    "fft": {
        "name":              "Bot FFT",
        "trades":            ALGOS_ROOT / "markets/fx/instances/gold_fft/fft_trades.json",
        "equity":            ALGOS_ROOT / "markets/fx/instances/gold_fft/fft_equity.json",
        "weekly":            ALGOS_ROOT / "markets/fx/instances/gold_fft/fft_weekly.json",
        "starting_balance":  1000.0,
        "daily_cap_pct":     5.0,
        "weekly_cap_pct":    15.0,
        "daily_goal_pct":    2.0,
    },
}

# SMC and Mean Reversion share the same account — equity file is shared
# but each tracks its own trade contributions separately
SHARED_EQUITY_BOTS = {"smc_trend", "mean_reversion"}


# ── Helpers ──────────────────────────────────────────────────────────────────

def send_alert(message: str):
    try:
        requests.post(
            f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage",
            json={"chat_id": ADMIN_CHAT, "text": message, "parse_mode": "Markdown"},
            timeout=10
        )
    except Exception as e:
        print(f"Alert failed: {e}")


def load_json(path: Path):
    if not path.exists():
        return []
    with open(path) as f:
        return json.load(f)


def save_json(path: Path, data):
    with open(path, "w") as f:
        json.dump(data, f, indent=2)


def load_state() -> dict:
    if STATE_FILE.exists():
        with open(STATE_FILE) as f:
            return json.load(f)
    return {}


def save_state(state: dict):
    with open(STATE_FILE, "w") as f:
        json.dump(state, f, indent=2)


def parse_dt(dt_str: str) -> datetime:
    """Parse ISO datetime string to UTC datetime."""
    try:
        return datetime.fromisoformat(dt_str.replace("Z", "+00:00"))
    except Exception:
        return datetime.utcnow()


# ── Core calculation engine ───────────────────────────────────────────────────

def calculate_pnl(bot_key: str) -> dict:
    """
    Pure math P&L calculation from trades JSON only.

    Returns dict with:
    - current_balance: starting_balance + sum of ALL closed trade profits
    - daily_pnl:       sum of today's closed trade profits ($ and %)
    - weekly_pnl:      sum of this week's closed trade profits ($ and %)
    - total_pnl:       total profit since inception ($ and %)
    - peak_balance:    highest balance ever reached
    - drawdown_from_peak: current drawdown from peak (%)
    - trades_today:    count of closed trades today
    - trades_week:     count of closed trades this week
    """
    cfg     = BOTS[bot_key]
    trades  = load_json(cfg["trades"])
    start   = cfg["starting_balance"]

    now_tx  = datetime.now(TEXAS)
    today   = now_tx.date()
    # Week starts Monday
    week_start = today - timedelta(days=today.weekday())

    # Only closed trades contribute to balance
    closed = [t for t in trades if t.get("outcome") in ("win", "loss", "breakeven")
              and t.get("closed_at")]

    # Sum all profits from trades
    def trade_pnl(t: dict) -> float:
        """
        Get dollar P&L for a trade.
        New trades: use stored pnl_usd field (set by log_close).
        Old trades: estimate from r_multiple × risk_usd if available,
                    otherwise use r_multiple × (2% of starting balance).
        """
        if t.get("pnl_usd") is not None:
            return float(t["pnl_usd"])
        r = float(t.get("r_multiple") or 0)
        risk = float(t.get("risk_usd") or (start * 0.02))
        return round(r * risk, 2)

    # Check if we have any real pnl_usd data at all
    has_pnl_data = any(t.get("pnl_usd") is not None for t in closed)

    # If no pnl_usd data exists yet (old trades only), fall back to equity file
    # to get the actual current balance rather than calculating from R multiples
    # which may be inaccurate for dollar amounts
    if not has_pnl_data and closed:
        equity_records = load_json(cfg["equity"])
        if equity_records:
            actual_balance = float(equity_records[-1]["balance"])
            # Use equity file for balance but still calculate daily/weekly from trades
            total_profit = actual_balance - start
        else:
            total_profit = sum(trade_pnl(t) for t in closed)
    else:
        total_profit = sum(trade_pnl(t) for t in closed)
    current_balance = round(start + total_profit, 2)

    # Today's trades
    today_trades = [t for t in closed
                    if parse_dt(t["closed_at"]).astimezone(TEXAS).date() == today]
    daily_profit = sum(trade_pnl(t) for t in today_trades)

    # This week's trades
    week_trades = [t for t in closed
                   if parse_dt(t["closed_at"]).astimezone(TEXAS).date() >= week_start]
    weekly_profit = sum(trade_pnl(t) for t in week_trades)

    # Calculate daily start balance = starting + sum of profits before today
    pre_today_profit = total_profit - daily_profit
    daily_start_balance = round(start + pre_today_profit, 2)

    # Calculate week start balance = starting + sum of profits before this week
    pre_week_profit = total_profit - weekly_profit
    week_start_balance = round(start + pre_week_profit, 2)

    # Peak balance — highest point reached across all time
    # Reconstruct balance timeline
    peak = start
    running = start
    for t in sorted(closed, key=lambda x: x.get("closed_at", "")):
        running += trade_pnl(t)
        peak = max(peak, running)

    drawdown_from_peak = ((peak - current_balance) / peak * 100) if peak > 0 else 0

    return {
        "current_balance":    current_balance,
        "daily_start":        daily_start_balance,
        "week_start":         week_start_balance,
        "daily_profit":       round(daily_profit, 2),
        "weekly_profit":      round(weekly_profit, 2),
        "total_profit":       round(total_profit, 2),
        "daily_pnl_pct":      round(daily_profit / daily_start_balance * 100, 2) if daily_start_balance else 0,
        "weekly_pnl_pct":     round(weekly_profit / week_start_balance * 100, 2) if week_start_balance else 0,
        "total_pnl_pct":      round(total_profit / start * 100, 2),
        "peak_balance":       round(peak, 2),
        "drawdown_from_peak": round(drawdown_from_peak, 2),
        "trades_today":       len(today_trades),
        "trades_week":        len(week_trades),
        "trades_total":       len(closed),
        "starting_balance":   start,
    }


def update_equity_file(bot_key: str, pnl: dict):
    """
    Update the equity file with current balance.
    Appends a new record only if balance changed since last record.
    Shared bots (SMC + Mean Reversion) update the same gold_main_equity.json
    but only write if the balance changed — prevents duplicate writes.
    """
    cfg  = BOTS[bot_key]
    path = cfg["equity"]
    records = load_json(path) if path.exists() else []

    last_balance = records[-1]["balance"] if records else 0
    new_balance  = pnl["current_balance"]

    if abs(new_balance - last_balance) > 0.001:
        records.append({
            "date":    datetime.utcnow().isoformat(),
            "balance": new_balance,
        })
        # Keep last 1000 records
        save_json(path, records[-1000:])
        return True
    return False


def update_weekly_file(bot_key: str, pnl: dict):
    """Update the weekly tracking file."""
    cfg  = BOTS[bot_key]
    path = cfg["weekly"]
    now  = datetime.now(TEXAS)
    week = now.isocalendar()[1]
    save_json(path, {
        "week":         week,
        "weekly_start": pnl["week_start"],
        "current":      pnl["current_balance"],
        "weekly_pnl":   pnl["weekly_profit"],
        "weekly_pnl_pct": pnl["weekly_pnl_pct"],
        "updated":      datetime.utcnow().isoformat(),
    })


# ── Alert logic ───────────────────────────────────────────────────────────────

def check_alerts(bot_key: str, pnl: dict, state: dict) -> dict:
    """
    Check thresholds and send alerts if crossed.
    Uses state to avoid duplicate alerts for the same event.
    Resets daily alerts at midnight Texas time.
    """
    cfg      = BOTS[bot_key]
    bot_st   = state.get(bot_key, {})
    now_tx   = datetime.now(TEXAS)
    today    = now_tx.date().isoformat()
    now_str  = now_tx.strftime("%I:%M %p CT")

    # Reset daily alerts if new day
    if bot_st.get("alert_date") != today:
        bot_st = {
            "alert_date":         today,
            "goal_alerted":       False,
            "daily_cap_alerted":  False,
            "weekly_cap_alerted": bot_st.get("weekly_cap_alerted", False),
        }

    daily_pct  = pnl["daily_pnl_pct"]
    weekly_pct = pnl["weekly_pnl_pct"]
    name       = cfg["name"]
    bal        = pnl["current_balance"]
    daily_start = pnl["daily_start"]

    # Daily goal hit
    if daily_pct >= cfg["daily_goal_pct"] and not bot_st.get("goal_alerted"):
        send_alert(
            f"🎯 *ALERT — Daily Goal Hit*\n"
            f"{name}\n"
            f"Today: +{daily_pct:.1f}% (+${pnl['daily_profit']:.2f})\n"
            f"Balance: ${bal:,.2f}\n"
            f"Time: {now_str}"
        )
        bot_st["goal_alerted"] = True

    # Daily loss cap hit
    if daily_pct <= -cfg["daily_cap_pct"] and not bot_st.get("daily_cap_alerted"):
        send_alert(
            f"🛑 *ALERT — Daily Loss Cap Hit*\n"
            f"{name}\n"
            f"Today: {daily_pct:.1f}% (-${abs(pnl['daily_profit']):.2f})\n"
            f"Balance: ${bal:,.2f}\n"
            f"No new entries until tomorrow\n"
            f"Time: {now_str}"
        )
        bot_st["daily_cap_alerted"] = True

    # Weekly loss cap hit
    if weekly_pct <= -cfg["weekly_cap_pct"] and not bot_st.get("weekly_cap_alerted"):
        send_alert(
            f"🚫 *ALERT — Weekly Loss Cap Hit*\n"
            f"{name}\n"
            f"Weekly: {weekly_pct:.1f}% (-${abs(pnl['weekly_profit']):.2f})\n"
            f"Balance: ${bal:,.2f}\n"
            f"Time: {now_str}"
        )
        bot_st["weekly_cap_alerted"] = True

    state[bot_key] = bot_st
    return state


# ── Main ─────────────────────────────────────────────────────────────────────

def main():
    state = load_state()
    now   = datetime.now(TEXAS).strftime("%I:%M %p CT")

    # Track if shared gold_main equity already written this run
    gold_main_written = False

    for bot_key, cfg in BOTS.items():
        try:
            pnl = calculate_pnl(bot_key)

            # Update equity file
            # For shared bots use the highest calculated balance
            if bot_key in SHARED_EQUITY_BOTS:
                if not gold_main_written:
                    updated = update_equity_file(bot_key, pnl)
                    if updated:
                        gold_main_written = True
            else:
                update_equity_file(bot_key, pnl)

            # Update weekly file
            update_weekly_file(bot_key, pnl)

            # Check and send alerts
            state = check_alerts(bot_key, pnl, state)

            print(
                f"{bot_key}: ${pnl['current_balance']:,.2f} | "
                f"day={pnl['daily_pnl_pct']:+.1f}% | "
                f"week={pnl['weekly_pnl_pct']:+.1f}% | "
                f"trades_today={pnl['trades_today']}"
            )

        except Exception as e:
            print(f"Error processing {bot_key}: {e}")

    save_state(state)
    print(f"P&L tracker complete — {now}")


if __name__ == "__main__":
    main()
