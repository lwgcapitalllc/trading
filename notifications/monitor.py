"""
monitor.py — Real-Time Bot Health Monitor + Alert System

Runs every 1 minute via Task Scheduler.
Sends Telegram alerts immediately when:
  - A bot goes offline unexpectedly
  - A bot comes back online
  - Daily profit goal is hit
  - Daily loss cap is hit
  - Weekly loss cap is hit

State is tracked in monitor_state.json so it knows what changed.
The Telegram bot (SYS_TELEGRAM) is watched as a priority watchdog —
auto-restarted up to 3 times before sending a critical alert.

Install: pip install requests
Run:     python notifications/monitor.py
"""

import json
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

try:
    import requests
except ImportError:
    print("pip install requests")
    sys.exit(1)

TELEGRAM_TOKEN = "8888123776:AAFuWpPoKnHSmGwxNxRB9Qo61kDSk7w0YD8"
ADMIN_CHAT     = "429207285"
GROUP_CHAT     = "-1003977707258"   # LWG Capital Algos Notifications — broadcast destination
ALGOS_ROOT     = Path("C:/algos")
STATE_FILE     = ALGOS_ROOT / "monitor_state.json"
SUPPRESS_FILE  = ALGOS_ROOT / "stop_suppress.json"
TEXAS          = ZoneInfo("America/Chicago")

sys.path.insert(0, str(ALGOS_ROOT / "shared"))
import bot_state as _bot_state

# Bots emit a log line roughly every ~60s. Some branches (SMC outside kill zone,
# "manage trades only") can sleep up to ~2-3 min. 5 min is a safe floor.
LOG_STALE_SECS = 5 * 60

BOTS = {
    "smc_trend": {
        "name":        "Bot SMC Trend",
        "suppress_key": "smc",
        "script":      "bot_smc_trend.py",
        "log":         ALGOS_ROOT / "markets/fx/instances/gold_main/bot_smc_trend.log",
        "equity":      ALGOS_ROOT / "markets/fx/instances/gold_main/gold_main_equity.json",
        "weekly":      ALGOS_ROOT / "markets/fx/instances/gold_main/smc_trend_weekly.json",
        "daily_cap":   10.0,
        "weekly_cap":  20.0,
        "daily_goal":  2.0,
    },
    "mean_reversion": {
        "name":        "Bot Mean Reversion",
        "suppress_key": "reversion",
        "script":      "bot_mean_reversion.py",
        "log":         ALGOS_ROOT / "markets/fx/instances/gold_main/bot_mean_reversion.log",
        "equity":      ALGOS_ROOT / "markets/fx/instances/gold_main/gold_main_equity.json",
        "weekly":      ALGOS_ROOT / "markets/fx/instances/gold_main/mean_reversion_weekly.json",
        "daily_cap":   10.0,
        "weekly_cap":  20.0,
        "daily_goal":  2.0,
    },
    "scalper": {
        "name":        "Bot Scalper",
        "suppress_key": "scalper",
        "script":      "bot_scalper.py",
        "log":         ALGOS_ROOT / "markets/fx/instances/gold_scalper/bot_scalper.log",
        "equity":      ALGOS_ROOT / "markets/fx/instances/gold_scalper/scalper_equity.json",
        "weekly":      ALGOS_ROOT / "markets/fx/instances/gold_scalper/scalper_weekly.json",
        "daily_cap":   8.0,
        "weekly_cap":  20.0,
        "daily_goal":  10.0,
    },
    "fft": {
        "name":        "Bot FFT",
        "suppress_key": "fft",
        "script":      "bot_fft.py",
        "log":         ALGOS_ROOT / "markets/fx/instances/gold_fft/bot_fft.log",
        "equity":      ALGOS_ROOT / "markets/fx/instances/gold_fft/fft_equity.json",
        "weekly":      ALGOS_ROOT / "markets/fx/instances/gold_fft/fft_weekly.json",
        "daily_cap":   5.0,
        "weekly_cap":  15.0,
        "daily_goal":  2.0,
    },
}


def send_alert(message: str):
    url  = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    data = {"chat_id": GROUP_CHAT, "text": message, "parse_mode": "Markdown"}
    try:
        requests.post(url, json=data, timeout=10)
    except Exception as e:
        print(f"Alert failed: {e}")


def load_state() -> dict:
    if STATE_FILE.exists():
        with open(STATE_FILE) as f:
            return json.load(f)
    return {}


def save_state(state: dict):
    with open(STATE_FILE, "w") as f:
        json.dump(state, f, indent=2)


def is_running(script: str) -> bool:
    try:
        result = subprocess.run(
            ["wmic", "process", "where", "name='python.exe'",
             "get", "commandline"],
            capture_output=True, text=True, timeout=10
        )
        return script in result.stdout
    except Exception:
        return False


def load_json(path: Path):
    if not path.exists():
        return []
    with open(path) as f:
        return json.load(f)


def _is_stop_suppressed(suppress_key: str) -> bool:
    """Consume and return True if this bot's offline alert should be suppressed."""
    try:
        if SUPPRESS_FILE.exists():
            keys = json.loads(SUPPRESS_FILE.read_text())
            if suppress_key in keys:
                keys.remove(suppress_key)
                SUPPRESS_FILE.write_text(json.dumps(keys))
                return True
    except Exception:
        pass
    return False


def get_balance(equity) -> float:
    records = equity if isinstance(equity, list) else []
    if not records:
        return 0.0
    return float(records[-1].get("balance", records[-1].get("equity", 0)))


def get_weekly_start(weekly_path: Path) -> float:
    if not weekly_path.exists():
        return 0.0
    with open(weekly_path) as f:
        data = json.load(f)
    return float(data.get("weekly_start", 0))


def check_bot(bot_key: str, state: dict, today: str) -> dict:
    """
    Check one bot's health and send alerts if anything changed.

    Daily cap/goal calculations use day_start_balance which is set at
    midnight each day. On first run, day_start_balance is set to current
    balance to avoid false positives from stale equity data.
    """
    cfg       = BOTS[bot_key]
    bot_state = state.get(bot_key, {})

    running     = is_running(cfg["script"])
    was_running = bot_state.get("running", None)

    # ── Running state change alerts ───────────────────────────────────────
    if was_running is not None and running != was_running:
        now_str = datetime.now(TEXAS).strftime("%I:%M %p CT")
        if not running:
            suppress_key = cfg.get("suppress_key", "")
            suppressed   = _is_stop_suppressed(suppress_key) if suppress_key else False
            bot_state["stop_suppressed"] = suppressed
            if not suppressed:
                send_alert(
                    f"🚨 *ALERT — Bot Offline*\n"
                    f"{cfg['name']} stopped unexpectedly\n"
                    f"Time: {now_str}\n"
                    f"Action: run `algo restart` or use /restart"
                )
            _bot_state.set_status(bot_key, "offline")
        else:
            if not bot_state.get("stop_suppressed"):
                send_alert(
                    f"🟢 *ALERT — Bot Online*\n"
                    f"{cfg['name']} is running again\n"
                    f"Time: {now_str}"
                )
            bot_state["stop_suppressed"] = False
            _bot_state.set_status(bot_key, "running")

    bot_state["running"] = running
    if not running:
        bot_state["stale_alerted"] = False
        return bot_state

    # ── Log staleness check — catches alive-but-frozen bots ───────────────
    log_path = cfg.get("log")
    if log_path and log_path.exists():
        stale_secs = time.time() - log_path.stat().st_mtime
        if stale_secs > LOG_STALE_SECS:
            if not bot_state.get("stale_alerted"):
                last_line = ""
                try:
                    with open(log_path, "rb") as _f:
                        _f.seek(max(0, log_path.stat().st_size - 500))
                        chunk = _f.read().decode("utf-8", errors="replace").strip()
                        last_line = chunk.split("\n")[-1]
                        if " | " in last_line:
                            last_line = last_line.split(" | ", 3)[-1]
                except Exception:
                    pass
                now_str = datetime.now(TEXAS).strftime("%I:%M %p CT")
                send_alert(
                    f"⚠️ *{cfg['name']} — Loop Stalled*\n"
                    f"Process alive but log silent {stale_secs / 60:.0f} min\n"
                    f"Last: `{last_line[:120]}`\n"
                    f"Time: {now_str}\n"
                    f"Action: /restart or check `algo logs`"
                )
                bot_state["stale_alerted"] = True
                _bot_state.set_status(bot_key, "stalled")
        else:
            if bot_state.get("stale_alerted"):
                now_str = datetime.now(TEXAS).strftime("%I:%M %p CT")
                send_alert(
                    f"🟢 *{cfg['name']} — Loop Recovered*\n"
                    f"Log activity resumed. Bot is scanning again.\n"
                    f"Time: {now_str}"
                )
                _bot_state.set_status(bot_key, "running")
            bot_state["stale_alerted"] = False

    # ── Balance and P&L checks ────────────────────────────────────────────
    equity       = load_json(cfg["equity"])
    balance      = get_balance(equity)
    weekly_start = get_weekly_start(cfg["weekly"])

    if balance <= 0:
        return bot_state

    # Reset day tracking at midnight or on first run
    if bot_state.get("last_date") != today:
        bot_state["day_start_balance"] = balance
        bot_state["last_date"]         = today
        bot_state["goal_alerted"]      = False
        bot_state["daily_cap_alerted"] = False
        bot_state["weekly_cap_alerted"]= False
        print(f"{bot_key}: New day — day start balance set to ${balance:,.2f}")

    day_start = bot_state.get("day_start_balance", balance)

    # Guard: if day_start is 0 or not set, set it now and skip this check
    if not day_start or day_start <= 0:
        bot_state["day_start_balance"] = balance
        return bot_state

    daily_gain = (balance - day_start) / day_start * 100
    weekly_dd  = (weekly_start - balance) / weekly_start * 100 if weekly_start > 0 else 0

    now_str = datetime.now(TEXAS).strftime("%I:%M %p CT")

    # ── Daily goal hit ─────────────────────────────────────────────────────
    if daily_gain >= cfg["daily_goal"] and not bot_state.get("goal_alerted"):
        send_alert(
            f"🎯 *ALERT — Daily Goal Hit*\n"
            f"{cfg['name']}\n"
            f"Today: +{daily_gain:.1f}% (+${balance - day_start:.2f})\n"
            f"Balance: ${balance:,.2f}\n"
            f"Time: {now_str}"
        )
        bot_state["goal_alerted"] = True

    # ── Daily loss cap hit ─────────────────────────────────────────────────
    if daily_gain <= -cfg["daily_cap"] and not bot_state.get("daily_cap_alerted"):
        send_alert(
            f"🛑 *ALERT — Daily Loss Cap Hit*\n"
            f"{cfg['name']}\n"
            f"Today: {daily_gain:.1f}% (-${day_start - balance:.2f})\n"
            f"Balance: ${balance:,.2f}\n"
            f"No new entries until tomorrow\n"
            f"Time: {now_str}"
        )
        bot_state["daily_cap_alerted"] = True

    # ── Weekly loss cap hit ────────────────────────────────────────────────
    if weekly_dd >= cfg["weekly_cap"] and not bot_state.get("weekly_cap_alerted"):
        send_alert(
            f"🚫 *ALERT — Weekly Loss Cap Hit*\n"
            f"{cfg['name']}\n"
            f"Weekly drawdown: -{weekly_dd:.1f}%\n"
            f"Balance: ${balance:,.2f} (week start: ${weekly_start:,.2f})\n"
            f"6-hour cooldown activated\n"
            f"Time: {now_str}"
        )
        bot_state["weekly_cap_alerted"] = True

    bot_state["last_balance"] = balance
    return bot_state


def check_telegram_bot(state: dict) -> dict:
    """
    Watchdog for SYS_TELEGRAM — most critical system process.
    Auto-restarts up to 3 times. Sends alert when back online.
    After 3 failures sends a critical alert requiring manual intervention.
    """
    tg_state  = state.get("telegram_bot", {})
    running   = is_running("telegram_bot.py")
    max_tries = 3
    now_str   = datetime.now(TEXAS).strftime("%I:%M %p CT")

    if not running:
        tries = tg_state.get("restart_tries", 0)
        print(f"Telegram bot is DOWN. Restart attempt {tries+1}/{max_tries}...")

        if tries < max_tries:
            try:
                result = subprocess.run(
                    ["schtasks", "/run", "/tn", "SYS_TELEGRAM"],
                    capture_output=True, text=True, timeout=15
                )
                if result.returncode == 0:
                    import time; time.sleep(5)
                    if is_running("telegram_bot.py"):
                        print("Telegram bot restarted successfully.")
                        send_alert(
                            f"🟢 *ALERT — Telegram Bot Restarted*\n"
                            f"Was offline\\. Auto-restarted at {now_str}\\.\n"
                            f"Commands are available again\\."
                        )
                        tg_state["restart_tries"] = 0
                        tg_state["running"]        = True
                    else:
                        tg_state["restart_tries"] = tries + 1
                        tg_state["running"]        = False
            except Exception as e:
                print(f"Restart error: {e}")
                tg_state["restart_tries"] = tries + 1
        else:
            if not tg_state.get("max_retry_alerted"):
                send_alert(
                    f"🚨 *CRITICAL — Telegram Bot Down*\n"
                    f"Failed to restart after {max_tries} attempts\\.\n"
                    f"Manual action required\\.\n"
                    f"RDP into VPS: `schtasks /run /tn SYS_TELEGRAM`\n"
                    f"Time: {now_str}"
                )
                tg_state["max_retry_alerted"] = True
    else:
        tg_state["running"]           = True
        tg_state["restart_tries"]     = 0
        tg_state["max_retry_alerted"] = False

    return tg_state


def main():
    state = load_state()
    today = datetime.now(TEXAS).date().isoformat()

    # Telegram bot watchdog — always check first
    try:
        state["telegram_bot"] = check_telegram_bot(state)
    except Exception as e:
        print(f"Telegram watchdog error: {e}")

    # Trading bot checks
    for bot_key in BOTS:
        try:
            state[bot_key] = check_bot(bot_key, state, today)
        except Exception as e:
            print(f"Error checking {bot_key}: {e}")

    save_state(state)
    print(f"Monitor check complete — {datetime.now(TEXAS).strftime('%I:%M %p CT')}")


if __name__ == "__main__":
    main()
