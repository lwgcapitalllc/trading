"""
monitor.py — Bot Availability + Heartbeat Monitor

Runs every 1 minute via Task Scheduler.
Sends Telegram alerts for:
  - Bot offline / back online
  - Bot loop stalled (alive but no heartbeat for 5+ min)
  - Watchlist symbol not found on broker

⚠ There are NO P&L threshold alerts anywhere any more. Daily goal, daily cap and weekly
cap belonged to pnl_tracker.py (SYS_PNLTRACKER), deleted 2026-08-05 — it had been an empty
shell since the June bot suite went. Do not add them back here: this is the watchdog, and
a cap that only sends a message is not a cap. A real one refuses the trade, which means it
belongs in the bot's own loop.

State is tracked in monitor_state.json.
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

# DERIVED, not hardcoded — same reason as algos/shared/bot_state.py. A literal
# "C:/trading/algos" is correct on the VPS and silently wrong everywhere else, which makes
# this file untestable off the box.
ALGOS_ROOT     = Path(__file__).resolve().parent.parent
STATE_FILE     = ALGOS_ROOT / "monitor_state.json"
SUPPRESS_FILE  = ALGOS_ROOT / "stop_suppress.json"
TEXAS          = ZoneInfo("America/Chicago")

sys.path.insert(0, str(ALGOS_ROOT / "shared"))
import bot_state as _bot_state

# Telegram credentials are resolved from the environment or the git-ignored
# algos/credentials.json — never pasted here. See algos/shared/credentials.py.
from credentials import telegram_credentials  # noqa: E402

TELEGRAM_TOKEN, GROUP_CHAT, ADMIN_CHAT = telegram_credentials()

# Bots emit a log line roughly every ~60s. Some branches (SMC outside kill zone,
# "manage trades only") can sleep up to ~2-3 min. 5 min is a safe floor.
LOG_STALE_SECS = 5 * 60

# Registered bots — {"name", "suppress_key", "script", "log"}.
#
# ⚠ SYS_MONITOR itself is DISABLED (algos/CLAUDE.md → "On hold, by Aaron's call"), so
# nothing below runs yet. It is filled in anyway so re-enabling is one schtasks command
# and not a code change — a watchdog that has to be written at the moment you need it is
# a watchdog you do not have.
#
# `script` is matched as a SUBSTRING of the process commandline. The bot_key is what
# appears there (`runner.py --bot mpc_sos_fade_demo`), so it is the match — never the
# script filename, which is `runner.py` for every live bot and would make them
# indistinguishable the moment a second one exists.
BOTS = {
    "mpc_sos_fade_demo": {
        "name":         "MPC SOS Fade",
        "suppress_key": "mpc_sos_fade_demo",
        "script":       "mpc_sos_fade_demo",
        "log":          str(ALGOS_ROOT / "markets/fx/instances/mpc_sos_fade_demo"
                                         "/mpc_sos_fade_demo.log"),
    },
}

# How many times a bot is restarted before this gives up and asks for a human. Same shape as the
# Telegram watchdog's, and the ceiling matters as much as the restart does: a bot that dies on
# startup (a bad config, a broker refusing the login, a failed version pin) would otherwise be
# relaunched every 60 seconds forever, filling the log and hiding the real error behind a
# thousand identical ones. Three tries distinguishes "something killed it" from "it cannot run".
MAX_BOT_RESTARTS = 3


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


def restart_bot(bot_key: str) -> bool:
    """Relaunch one bot, detached, and report whether it came up.

    **Why a trading bot may be auto-restarted at all.** It looks riskier than restarting a chat
    bot, and it is not, because of what the restart walks into: the stop-loss lives AT THE BROKER
    from the moment the order is placed, so a dead bot never leaves a naked position; and
    `OrderBridge.adopt_broker_state()` HALTS rather than adopting a position it has no record of,
    so a restart can never double the book. The genuine risk is the opposite one — a bot that
    stays dead. It managed nothing for three days in July while the watchdog alerted once and
    then went quiet.

    Launched via the coordinator's single-bot mode, DETACHED, so the new process does not belong
    to this one. The monitor is a short-lived scheduled task: a child would be torn down with it
    seconds later, which looks exactly like the bot dying again.
    """
    coordinator = ALGOS_ROOT / "bots" / "startup_coordinator.py"
    try:
        flags = 0
        if hasattr(subprocess, "DETACHED_PROCESS"):        # Windows only; harmless elsewhere
            flags = subprocess.DETACHED_PROCESS | subprocess.CREATE_NEW_PROCESS_GROUP
        subprocess.Popen(
            [sys.executable, str(coordinator), "--bot", bot_key],
            cwd=str(ALGOS_ROOT / "bots"),
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            creationflags=flags,
        )
    except Exception as e:
        print(f"Restart launch failed for {bot_key}: {e}")
        return False

    # The bot connects to MT5 and warms thousands of bars before it is meaningfully alive, but
    # the PROCESS exists almost immediately, and that is all this needs to confirm. Waiting for
    # the warm-up would hold the whole monitor pass open for a minute every time.
    time.sleep(8)
    return is_running(BOTS[bot_key]["script"])


def check_bot(bot_key: str, state: dict, today: str) -> dict:
    """Check bot availability and heartbeat. Nothing here alerts on P&L — see the header."""
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
                    f"Restarting automatically…"
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
            bot_state["restart_tries"] = 0
            bot_state["max_retry_alerted"] = False
            _bot_state.set_status(bot_key, "running")

    bot_state["running"] = running

    # ── Bring it back ────────────────────────────────────────────────────
    #
    # Until 2026-08-03 this function ALERTED and stopped there, while the Telegram bot below
    # got a real watchdog that restarts it up to three times. That asymmetry is backwards: a
    # dead chat bot costs you commands, a dead trading bot stops managing open positions. The
    # live bot was killed on 31 July by a blanket `taskkill /f /im python.exe` — the same one
    # that took Telegram down. Telegram was back in a minute. The trading bot stayed dead for
    # three days, because one alert fired at 6pm on a Friday and nothing said it again.
    #
    # A DELIBERATE stop is never fought. `stop_suppressed` is set when the offline transition
    # consumed a suppress key (the Bots page / Telegram asked for the stop), and it survives
    # until the bot is started again — otherwise stopping a bot would be impossible, the
    # watchdog relaunching it every 60 seconds.
    if not running:
        bot_state["stale_alerted"] = False
        if bot_state.get("stop_suppressed"):
            return bot_state

        tries = bot_state.get("restart_tries", 0)
        now_str = datetime.now(TEXAS).strftime("%I:%M %p CT")
        if tries < MAX_BOT_RESTARTS:
            print(f"{bot_key} is DOWN. Restart attempt {tries+1}/{MAX_BOT_RESTARTS}...")
            if restart_bot(bot_key):
                bot_state["restart_tries"] = 0
                bot_state["running"] = True
                send_alert(
                    f"🟢 *ALERT — {cfg['name']} Restarted*\n"
                    f"Was offline\\. Auto\\-restarted at {now_str}\\.\n"
                    f"Check the log for why it stopped\\."
                )
                _bot_state.set_status(bot_key, "running")
            else:
                bot_state["restart_tries"] = tries + 1
        elif not bot_state.get("max_retry_alerted"):
            # It will not come up on its own. Say so ONCE and stop — a bot that cannot start
            # needs a person to read the log, and repeating the alert every minute trains you
            # to mute the channel that also carries the trade alerts.
            bot_state["max_retry_alerted"] = True
            send_alert(
                f"🚨 *CRITICAL — {cfg['name']} Will Not Start*\n"
                f"Failed {MAX_BOT_RESTARTS} restart attempts\\.\n"
                f"It is NOT trading and will not retry\\.\n"
                f"Check `{cfg['name']}` log — likely a version pin or MT5 login\\.\n"
                f"Time: {now_str}"
            )
        return bot_state

    # ── Heartbeat check — catches alive-but-frozen loops ─────────────────
    #
    # Falls back to `started` when no stamp exists yet, and that fallback is the point.
    # Reading a missing heartbeat as 0 makes this check compare 0 > 300 and never fire —
    # which is what happened between the runner being written and 2026-07-31, when nothing
    # wrote the field at all. A watchdog whose failure mode is SILENCE is worse than no
    # watchdog, because the empty alert channel reads as good news. Anchoring on the start
    # time means a bot that boots and never stamps alerts like the stalled bot it is.
    bot_live    = _bot_state.read_bot(bot_key)
    heartbeat   = bot_live.get("heartbeat") or bot_live.get("started") or 0
    stale_secs  = (time.time() - heartbeat) if heartbeat else 0
    if stale_secs > LOG_STALE_SECS:
        if not bot_state.get("stale_alerted"):
            now_str = datetime.now(TEXAS).strftime("%I:%M %p CT")
            send_alert(
                f"⚠️ *{cfg['name']} — Loop Stalled*\n"
                f"Process alive but heartbeat missing {stale_secs / 60:.0f} min\n"
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
                f"Heartbeat resumed. Bot is scanning again.\n"
                f"Time: {now_str}"
            )
            _bot_state.set_status(bot_key, "running")
        bot_state["stale_alerted"] = False

    # ── Unresolved symbol alerts (once per symbol per day) ───────────────
    unresolved    = bot_live.get("unresolved_symbols", [])
    alerted_today = bot_state.get("unresolved_symbols_alerted", {})
    if unresolved:
        now_str = datetime.now(TEXAS).strftime("%I:%M %p CT")
        for entry in unresolved:
            sym = entry.get("symbol", "")
            if not sym or alerted_today.get(sym) == today:
                continue
            send_alert(
                f"⚠️ *{cfg['name']}: Watchlist Symbol Not Found*\n"
                f"Symbol `{sym}` not found on broker — skipped this cycle\\.\n"
                f"Fix `watchlist` in config\\.json\\.\n"
                f"Time: {now_str}"
            )
            alerted_today[sym] = today
    bot_state["unresolved_symbols_alerted"] = alerted_today

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
