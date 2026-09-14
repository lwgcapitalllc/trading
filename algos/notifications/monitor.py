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
ALGOS_ROOT = Path(__file__).resolve().parent.parent
STATE_FILE = ALGOS_ROOT / "monitor_state.json"
SUPPRESS_FILE = ALGOS_ROOT / "stop_suppress.json"
TEXAS = ZoneInfo("America/Chicago")

sys.path.insert(0, str(ALGOS_ROOT / "shared"))
import bot_registry as _registry
import bot_state as _bot_state
from alert_format import alert  # noqa: E402

# Telegram credentials are resolved from the environment or the git-ignored
# algos/credentials.json — never pasted here. See algos/shared/credentials.py.
from credentials import telegram_credentials  # noqa: E402
from notify import HEALTH, chat_for  # noqa: E402

TELEGRAM_TOKEN, GROUP_CHAT, ADMIN_CHAT = telegram_credentials()

# Bots emit a log line roughly every ~60s. Some branches (SMC outside kill zone,
# "manage trades only") can sleep up to ~2-3 min. 5 min is a safe floor.
LOG_STALE_SECS = 5 * 60

# Registered bots — {"name", "suppress_key"} per key, DISCOVERED from the bot folders
# (`bot_registry.discover`, read once by `bot_state` — this task is a fresh process every minute,
# so a bot created a minute ago is watched on the next pass).
#
# 🔴 A hand-kept dict until 2026-09-13. A bot missing from it was a bot nothing watched, which has
# no symptom at all — the empty alert channel reads as good news.
#
# ⚠ Every bot is registered, benched or not, and `main` skips a benched one per pass. Being here
# says a bot CAN be watched; having an account says it SHOULD be — so the Bots page can never arm a
# bot this watchdog does not watch.
#
# ⚠ A bot is matched by its KEY, exactly (`bot_registry.is_runner_line`), never as a substring of
# the process list: `sos_fade_2` is a substring of `--bot sos_fade_20`, and every tool that acts on
# a bot carries its key, so a substring read a dead bot as alive whenever one of them ran.
BOTS = {
    key: {"name": _bot_state.BOT_NAMES.get(key, key), "suppress_key": key}
    for key in _bot_state.BOT_INSTANCES
}

# How many times a bot is restarted before this gives up and asks for a human. Same shape as the
# Telegram watchdog's, and the ceiling matters as much as the restart does: a bot that dies on
# startup (a bad config, a broker refusing the login, a failed version pin) would otherwise be
# relaunched every 60 seconds forever, filling the log and hiding the real error behind a
# thousand identical ones. Three tries distinguishes "something killed it" from "it cannot run".
MAX_BOT_RESTARTS = 3


def send_alert(message: str, account=None):
    """Every message this watchdog sends is HEALTH — offline, restarted, stalled, recovered.

    Not one of them is a trade, which is the whole reason the routing exists: this module alone
    can produce nine different alerts about the machinery, and pointing them at the room that
    carries fills is what teaches you to swipe that room away. The chat is resolved PER CALL
    rather than at import, so setting a health channel takes effect on the next alert instead of
    at the next restart of a task that runs every 60 seconds.

    `account` is the broker login the alert is ABOUT, so an account that names its own health
    channel gets its bots' alerts there (2026-09-13). ⚠ It is omitted, deliberately, by the
    alerts about the box itself — the chat bot being down, an unreadable bot list — which belong
    to nobody's account. An account with no health channel of its own keeps the shared room, live
    accounts included.
    """
    dest, _dedicated = chat_for(HEALTH, account=account)
    if not TELEGRAM_TOKEN or not dest:
        print(f"Alert dropped (Telegram not configured): {message[:80]}")
        return
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    data = {"chat_id": dest, "text": message, "parse_mode": "Markdown"}
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


def is_running(script: str):
    """True / False / **None**, and the third value is the whole point.

    🔴 **This returned `False` when it could not ASK, and that is rule 1 in the one place it costs
    the most.** `wmic` misses its 10s timeout on a loaded box — which is exactly when a restart
    storm is happening — and the old body reported a perfectly healthy bot as gone. The watchdog
    then alerted OFFLINE and started a second copy of a process that was never dead. On
    2026-09-09 two copies of the chat bot were found running on the box, and this is the line
    that lets that happen.

    **`None` means the question was not answered.** Every caller must treat it as *do nothing
    this pass*, never as *it is down* — a watchdog that acts on an answer it never received is
    doing the damage it exists to prevent.

    ⚠ **A non-zero exit is also `None`, not `False`.** `wmic` printing nothing because it failed
    and printing nothing because no bot is running are the same empty string, and only the exit
    code separates them.

    ⚠ A SUBSTRING match, so it is for the chat bot (`telegram_bot.py`) only. A trading bot is
    `is_bot_running`, which matches its key exactly.
    """
    procs = _process_list()
    return None if procs is None else script in procs


def is_bot_running(bot_key: str, fresh: bool = False):
    """True / False / **None** for ONE trading bot — its runner with `--bot <key>` exactly.

    `None` is CANNOT ASK and every caller treats it as `is_running`'s does. `fresh=True` re-reads
    the list rather than using this pass's — the one caller is the post-restart confirmation, whose
    whole question is what changed since the pass began.
    """
    procs = _process_list(fresh)
    if procs is None:
        return None
    return bool(_registry.runner_keys(procs, [bot_key]))


# ONE read of the process list per watchdog pass, held only while `main` runs it. Outside a pass
# every read is fresh, so a caller outside `main` can never be handed a stale list. It was one
# `wmic` per bot until 2026-09-13 — a pass that grows by a process query per bot, on a task that
# must finish inside its own one-minute cadence.
_PASS: dict = {}


def _process_list(fresh: bool = False):
    """The python process list, `None` when it could not be asked — cached for the pass."""
    if not fresh and "procs" in _PASS:
        return _PASS["procs"]
    procs = _query_process_list()
    if "procs" in _PASS:
        _PASS["procs"] = procs
    return procs


def _query_process_list():
    try:
        result = subprocess.run(
            ["wmic", "process", "where", "name='python.exe'", "get", "commandline"],
            capture_output=True,
            text=True,
            timeout=10,
        )
    except Exception as e:
        print(f"  ! could not read the process list ({e}) - not treating that as a dead bot")
        return None
    if result.returncode != 0:
        print(f"  ! process list query failed (exit {result.returncode}) - answering 'cannot ask'")
        return None
    return result.stdout


# The exact closing line `runner._run` writes when a stop was ASKED for — the `stop.request`
# path, which is what the Bots page, the Telegram bot and the documented CLI all drive. Every
# other ending (a crash, a failed connect, a halted bridge, ten loop errors) writes a different
# reason or a non-zero code and is left to the restart logic exactly as before.
_REQUESTED_STOP = ("stop requested", 0)


def _newest_shutdown(bot_key: str):
    """The bot's own last closing record as `(reason, exit_code, when)`, or `None`.

    ⚠ **`None` is CANNOT ASK and must never be read as "it was stopped on purpose".** Of the two
    wrong answers here, restarting a bot somebody stopped is a nuisance they can see and undo;
    DECLINING to restart a bot that crashed is the failure this watchdog exists to prevent, and
    it is silent. So an unreadable record falls through to today's behaviour.
    """
    try:
        ledger_dir = _bot_state.BOT_INSTANCES[bot_key] / "ledger"
        # Two files, because a bot stopped at 23:58 is read at 00:02 from the previous day's.
        files = sorted(ledger_dir.glob("health-*.jsonl"))[-2:]
    except Exception:
        return None
    if not files:
        return None

    newest = None
    for path in files:
        try:
            lines = path.read_text().splitlines()
        except Exception:
            return None  # a file we cannot read may hold the very record that matters
        for line in lines:
            try:
                rec = json.loads(line)
            except Exception:
                continue  # a torn last line is ordinary; the file is written live
            if rec.get("event") != "shutdown":
                continue
            try:
                when = datetime.fromisoformat(rec["ts"]).timestamp()
            except Exception:
                continue
            if newest is None or when > newest[2]:
                newest = (rec.get("reason"), rec.get("exit_code"), when)
    return newest


def stopped_on_request(bot_key: str, started) -> bool:
    """Whether this bot's absence is a stop somebody ASKED for, per the bot's own record.

    🔴 **This exists because the watchdog was RACING deliberate stops.** The suppression flag
    beside it is written by whoever issues the stop, so it only covers the routes that remember
    to write it — the Bots page does, and the documented CLI (`echo stop > stop.request`) does
    not. MEASURED on the health channel: a clean `STOPPED` was followed by `OFFLINE ... restarting
    it now` three times between 2026-09-08 and 2026-09-09, so a promote-then-restart had the
    watchdog start the bot before the operator could. **Two things issuing starts for one bot is
    how a book gets doubled**, which this module's own restart function is written against.

    ✅ **It reads the BOT's record rather than a flag somebody had to remember to write**, so
    every stop route is covered by construction — that is the whole point, and it is why this is
    not simply another suppress key.

    🔴 **The record has to belong to the run that just ENDED, or a stale one suppresses a real
    crash.** A bot stopped on purpose, started again, then hard-killed leaves the old *stop
    requested* line as the newest shutdown on file — and restarting it is exactly what should
    happen. So the record is only believed when it is NEWER than this run's start. **Same shape
    as the `max(heartbeat, started)` rule above: two fields that are not the same age across a
    restart.**

    ⚠ **An unreadable record, an unparseable timestamp, or a missing `started` all answer
    False** — meaning *restart it*, which is today's behaviour and the recoverable direction.
    """
    rec = _newest_shutdown(bot_key)
    if rec is None:
        return False
    reason, code, when = rec
    if (reason, code) != _REQUESTED_STOP:
        return False
    if not isinstance(started, (int, float)):
        # Cannot place the record against this run. Believing it would let one deliberate stop
        # suppress every later crash for as long as the file survives.
        return False
    return when > started


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
        if hasattr(subprocess, "DETACHED_PROCESS"):  # Windows only; harmless elsewhere
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
    confirmed = is_bot_running(bot_key, fresh=True)
    # ⚠ CANNOT ASK reports NOT CONFIRMED, which is the conservative direction here and the
    # opposite of the call `check_bot` makes. There, an unread process list must not trigger a
    # restart; here the restart has ALREADY been launched, so the only question left is whether
    # to claim it worked — and claiming a start nobody verified is what `schtasks` does, which
    # this repo has been bitten by twice.
    if confirmed is None:
        print(f"Restarted {bot_key} but could not confirm the process - not claiming success")
        return False
    return confirmed


def check_bot(bot_key: str, state: dict, today: str) -> dict:
    """Check bot availability and heartbeat. Nothing here alerts on P&L — see the header."""
    cfg = BOTS[bot_key]
    bot_state = state.get(bot_key, {})
    # What every alert below calls this bot: its name plus LIVE or demo, off the account its own
    # config names. Two copies of one strategy share a name, and this is what tells them apart in
    # the one health room both kinds share (2026-09-11).
    # Read ONCE and used by the label AND by every alert's routing below. Deciding it twice is how
    # a message comes to name one account in its subject and land in another account's room.
    account = _bot_state.read_account(bot_key)
    name = _bot_state.labelled(cfg["name"], account)

    running = is_bot_running(bot_key)
    # 🔴 CANNOT ASK. Leave every stored fact exactly as it was and take no action: alerting would
    # cry wolf and restarting would start a second copy of a bot that is probably still running.
    # The next pass is 60 seconds away, so the cost of doing nothing is one minute of not knowing;
    # the cost of guessing has already been paid once (2026-09-09, two chat bots on one token).
    if running is None:
        print(f"{bot_key}: could not read the process list - skipping this pass")
        return bot_state

    was_running = bot_state.get("running", None)

    # Did the bot itself record that it was ASKED to stop? Read once, used by BOTH the alert and
    # the restart below — deciding it twice is how the two come to disagree and the bot is
    # relaunched under a message saying nothing is wrong.
    asked_to_stop = False
    if not running:
        try:
            asked_to_stop = stopped_on_request(bot_key, _bot_state.read_bot(bot_key).get("started"))
        except Exception as e:
            # Never let reading a record stop the watchdog doing its job.
            print(f"{bot_key}: could not check for a requested stop ({e})")

    # ── Running state change alerts ───────────────────────────────────────
    if was_running is not None and running != was_running:
        if not running:
            suppress_key = cfg.get("suppress_key", "")
            suppressed = _is_stop_suppressed(suppress_key) if suppress_key else False
            if asked_to_stop and not suppressed:
                # The stop was deliberate and whoever issued it did not write the flag — the
                # documented CLI route does not. Say so on the console so the difference between
                # "suppressed by the button" and "recognised from the record" stays visible.
                print(f"{bot_key}: its own record says it was asked to stop - not fighting it")
                suppressed = True
            bot_state["stop_suppressed"] = suppressed
            if not suppressed:
                send_alert(
                    alert("🔴", "OFFLINE", name, "The process is gone. Restarting it now."),
                    account,
                )
            _bot_state.set_status(bot_key, "offline")
        else:
            if not bot_state.get("stop_suppressed"):
                send_alert(
                    alert("🟢", "BACK ONLINE", name, "It is running again. Nothing to do."),
                    account,
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

        # 🔴 `asked_to_stop` is re-checked HERE and not left to the flag above, because the
        # transition block only runs when the state CHANGED. A pass whose first ever sight of
        # this bot is "down" — a fresh `monitor_state.json`, a new bot, the file deleted — sets
        # no flag at all, and would restart a bot somebody had deliberately stopped. Reading the
        # bot's own record needs no memory of a previous pass, which is the point of using it.
        if asked_to_stop:
            bot_state["stop_suppressed"] = True
            return bot_state

        tries = bot_state.get("restart_tries", 0)
        if tries < MAX_BOT_RESTARTS:
            print(f"{bot_key} is DOWN. Restart attempt {tries + 1}/{MAX_BOT_RESTARTS}...")
            if restart_bot(bot_key):
                bot_state["restart_tries"] = 0
                bot_state["running"] = True
                send_alert(
                    alert(
                        "🟢",
                        "RESTARTED",
                        name,
                        "It was offline and has been restarted automatically.",
                        "Worth checking the log for why it stopped.",
                    ),
                    account,
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
                alert(
                    "🚨",
                    "WILL NOT START",
                    name,
                    f"{MAX_BOT_RESTARTS} restart attempts have failed. It is not trading and will "
                    f"not retry.",
                    "It will stay down until someone looks. Usually a version pin or the MT5 login "
                    "— check its log.",
                ),
                account,
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
    # 🔴 The LATER of the two, never `heartbeat or started`. They are not the same age across a
    # RESTART: `bot_state.json` outlives the process, so `set_started` refreshes `started` and
    # leaves the dead run's `heartbeat` in place — and a stale-but-truthy stamp wins an `or`
    # outright. Measured 2026-08-13: the bot was restarted at 20:38 after stopping at 20:31:11
    # and this sent `STALLED — 7 minutes`, then `RECOVERED` a minute later, on a healthy bot.
    # `max` keeps the fallback above intact (a bot that boots and never stamps still ages from
    # `started`) while a fresh start can no longer be judged on the previous run's clock.
    bot_live = _bot_state.read_bot(bot_key)
    heartbeat = max(bot_live.get("heartbeat") or 0, bot_live.get("started") or 0)
    stale_secs = (time.time() - heartbeat) if heartbeat else 0
    if stale_secs > LOG_STALE_SECS:
        if not bot_state.get("stale_alerted"):
            send_alert(
                alert(
                    "⚠️",
                    "STALLED",
                    name,
                    f"The process is alive but has not stamped its heartbeat for "
                    f"{stale_secs / 60:.0f} minutes, so it is not working through bars.",
                    "Restart it from the command center, or check its log.",
                ),
                account,
            )
            bot_state["stale_alerted"] = True
            _bot_state.set_status(bot_key, "stalled")
    else:
        if bot_state.get("stale_alerted"):
            send_alert(
                alert(
                    "🟢",
                    "RECOVERED",
                    name,
                    "The heartbeat resumed and it is working through bars again.",
                    "Nothing to do.",
                ),
                account,
            )
            _bot_state.set_status(bot_key, "running")
        bot_state["stale_alerted"] = False

    # ── Unresolved symbol alerts (once per symbol per day) ───────────────
    unresolved = bot_live.get("unresolved_symbols", [])
    alerted_today = bot_state.get("unresolved_symbols_alerted", {})
    if unresolved:
        for entry in unresolved:
            sym = entry.get("symbol", "")
            if not sym or alerted_today.get(sym) == today:
                continue
            send_alert(
                alert(
                    "⚠️",
                    "SYMBOL NOT FOUND",
                    name,
                    f"The broker does not list {sym}, so it was skipped this cycle.",
                    "Fix the watchlist in config.json.",
                ),
                account,
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
    tg_state = state.get("telegram_bot", {})
    running = is_running("telegram_bot.py")
    max_tries = 3

    # 🔴 CANNOT ASK — do nothing. This is the exact path that produced TWO chat bots on one
    # Telegram token (2026-09-09): an unread process list read as "it is down", so this fired
    # SYS_TELEGRAM beside a bot that was running fine. Two long-pollers then knock each other
    # off the connection, and each death looks to this watchdog like an ordinary crash worth
    # restarting — a loop that sustains itself.
    if running is None:
        print("Telegram bot: could not read the process list - skipping this pass")
        return tg_state

    if not running:
        tries = tg_state.get("restart_tries", 0)
        print(f"Telegram bot is DOWN. Restart attempt {tries + 1}/{max_tries}...")

        if tries < max_tries:
            try:
                result = subprocess.run(
                    ["schtasks", "/run", "/tn", "SYS_TELEGRAM"],
                    capture_output=True,
                    text=True,
                    timeout=15,
                )
                if result.returncode == 0:
                    import time

                    time.sleep(5)
                    # ⚠ CANNOT ASK counts as NOT CONFIRMED here (falsy), the same conservative
                    # call `restart_bot` makes: the restart has already been requested, so the
                    # only question left is whether to claim it worked, and an unverified claim
                    # is exactly what `schtasks`'s own SUCCESS means and is worth nothing.
                    if is_running("telegram_bot.py") is True:
                        print("Telegram bot restarted successfully.")
                        send_alert(
                            alert(
                                "🟢",
                                "RESTARTED",
                                "Telegram bot",
                                "It was offline and has been restarted. Commands work again.",
                                "Nothing to do.",
                            )
                        )
                        tg_state["restart_tries"] = 0
                        tg_state["running"] = True
                    else:
                        tg_state["restart_tries"] = tries + 1
                        tg_state["running"] = False
            except Exception as e:
                print(f"Restart error: {e}")
                tg_state["restart_tries"] = tries + 1
        else:
            if not tg_state.get("max_retry_alerted"):
                send_alert(
                    alert(
                        "🚨",
                        "WILL NOT START",
                        "Telegram bot",
                        f"{max_tries} restart attempts have failed, so commands are unavailable.",
                        "RDP into the VPS and run: schtasks /run /tn SYS_TELEGRAM",
                    )
                )
                tg_state["max_retry_alerted"] = True
    else:
        tg_state["running"] = True
        tg_state["restart_tries"] = 0
        tg_state["max_retry_alerted"] = False

    return tg_state


def _say_if_the_bots_cannot_be_seen(state: dict) -> None:
    """Alert ONCE per distinct reason when the bot folders could not be read, and forget it once
    they can. A watchdog handed an empty list watches nothing and says nothing, which reads exactly
    like a quiet night (rule 8)."""
    err = _bot_state.REGISTRY_ERROR
    if not err:
        state.pop("registry_error", None)
        return
    print(f"Cannot see the bots: {err}")
    if state.get("registry_error") != err:
        send_alert(
            alert(
                "🚨",
                "CANNOT SEE THE BOTS",
                "Watchdog",
                f"The bot folders could not be read ({err}), so no bot is being watched.",
                "Check the box's disk and the algos folder.",
            )
        )
    state["registry_error"] = err


def main():
    state = load_state()
    today = datetime.now(TEXAS).date().isoformat()

    # One process list for the whole pass — see `_PASS`.
    _PASS.clear()
    _PASS["procs"] = _query_process_list()
    try:
        _say_if_the_bots_cannot_be_seen(state)

        # Telegram bot watchdog — always check first
        try:
            state["telegram_bot"] = check_telegram_bot(state)
        except Exception as e:
            print(f"Telegram watchdog error: {e}")

        # Trading bot checks
        for bot_key in BOTS:
            # A bot on the BENCH (`account: null`) is not supposed to be running, so "the process
            # is gone" is not a finding about it — it is the state somebody chose from the Bots
            # page. Alerting and then RESTARTING it would be worse than noisy: this watchdog's
            # response to an offline bot is to start it, and it would start a bot with no account
            # to trade, every sixty seconds, for ever.
            if not _bot_state.is_assigned(bot_key):
                continue
            try:
                state[bot_key] = check_bot(bot_key, state, today)
            except Exception as e:
                print(f"Error checking {bot_key}: {e}")
    finally:
        _PASS.clear()

    save_state(state)
    print(f"Monitor check complete — {datetime.now(TEXAS).strftime('%I:%M %p CT')}")


if __name__ == "__main__":
    main()
