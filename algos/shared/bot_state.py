"""
bot_state.py — Single Source of Truth

Every component reads and writes bot state through this module.
One bot_state.json file per instance directory.

Schema per bot entry:
{
  "name":           "SMC Trend",
  "status":         "running" | "stalled" | "stopped" | "offline",
  "heartbeat":      1779077863.18,      # Unix timestamp — written every loop iteration
  "started":        1779077863.18,      # Unix timestamp of last start
  "account":        "700103491",
  "balance":        2759.28,            # current balance — written by algos/live/runner.py
  "mt5_link":       true,               # None = never asked, false = asked and blind
  "day_locked":     false,
  "last_updated":   "2026-05-18T04:17:43"
}

⚠ **There are no derived P&L fields here any more, and their absence is deliberate.**
`daily_pnl`, `weekly_pnl`, `total_pnl_pct`, `peak_balance` and `trades_today` were written by
`notifications/pnl_tracker.py`, which was DELETED on 2026-08-05 along with `reporter.py` — both
were empty shells left over from the June bot suite (`BOT_TRADES = {}`, `BOTS = {}`), so neither
had produced a number since. Defaulting them to `0.0` here would have put "+0.00% today" on the
Bots page under a field nothing measures, which is this repo's standing rule broken in its usual
direction: **a fabricated zero and a real zero must never be the same value.** A future P&L job
adds them back with a writer attached, not before.
"""

import json
import time
from datetime import datetime
from pathlib import Path

# DERIVED, not hardcoded. This module is imported by algos/live/runner.py, which is
# dry-run-capable off the VPS — a literal "C:/trading/algos" made every state write fail
# on a Mac while looking perfectly correct in the source. The VPS resolves this to the
# same C:/trading/algos it always was.
ALGOS_ROOT = Path(__file__).resolve().parent.parent

# Bot registries — both are keyed by bot_key and must stay in step.
#
# ⚠ An unregistered key is a CRASH, not a no-op: write_bot() does BOT_INSTANCES[key],
# unguarded. algos/live/runner.py calls set_started() at the top of its loop, so a bot
# missing from here dies on startup with a bare KeyError after connecting to MT5 and
# warming the engines.
_INSTANCES = ALGOS_ROOT / "markets" / "fx" / "instances"

# Instance directory for each bot key
BOT_INSTANCES = {
    "mpc_sos_fade_demo": _INSTANCES / "mpc_sos_fade_demo",
    "mpc_bleg_demo":     _INSTANCES / "mpc_bleg_demo",
}

# Display names
BOT_NAMES = {
    "mpc_sos_fade_demo": "MPC SOS Fade",
    "mpc_bleg_demo":     "MPC B-LEG",
}


# 🔴 `BOT_ACCOUNTS` was DELETED 2026-08-09, and it was a second copy of a fact that can now
# move. It hardcoded a login per bot and was stamped into `bot_state.json`, which is what the
# command center's Bots page renders in its Account column — so the moment that page could MOVE
# a bot between accounts (Bots → Accounts), the row would have gone on showing the old number
# while the bot traded the new one. A page stating a value no code reads is this repo's
# most-repeated defect; this is its sibling, a page stating a value that used to be true.
#
# The account is read from the bot's own instance config now — the same file the bot reads, so
# there is one answer rather than two that can drift.


def _instance_config(bot_key: str):
    """A bot's instance config, or **`None` when it could not be read**.

    ⚠ `None` rather than `{}`, and the distinction is the whole point: *this bot states no
    account* and *we could not find out* need different answers from `is_assigned`, and an empty
    dict makes them one value. That is this repo's standing rule — never let "no" and "cannot
    ask" be the same value — and getting it wrong here would silently stop the dead-man's switch
    watching a bot whose config had a typo in it.

    It never raises: every caller is writing a STATUS record or deciding whether to watch, and
    neither may be able to take a bot down. An unregistered key is included in the failure —
    a bot in a watchdog's roster that `BOT_INSTANCES` does not know is a registry mismatch, which
    is a fault to be loud about rather than a bot to quietly ignore.
    """
    try:
        return json.loads(
            (BOT_INSTANCES[bot_key] / "config.json").read_text(encoding="utf-8"))
    except (KeyError, OSError, ValueError):
        return None


def read_account(bot_key: str):
    """The login this bot trades, from its own config. `None` = on the bench, or unreadable.

    ⚠ Those two are not distinguished here and deliberately so: both mean *this bot is not
    trading an account right now*, which is the only thing the status record is claiming. The
    Accounts tab is where the difference matters and it reads the configs directly.
    """
    return (_instance_config(bot_key) or {}).get("account")


def is_assigned(bot_key: str) -> bool:
    """Whether this bot has an account, i.e. whether anything should expect it to be running.

    **This is the one definition of the BENCH, shared by everything that watches a bot** — the
    boot coordinator, the process watchdog and the dead-man's switch. Three copies of "does it
    have an account" is three chances for one of them to alarm about a bot somebody deliberately
    took off an account, which is how an alert channel gets muted.

    ⚠ **Unreadable answers True**, the same call `startup_coordinator.bot_is_assigned` makes: a
    config that cannot be parsed is a bot whose state is UNKNOWN, and of the two wrong answers,
    "watch a bot that is not running and say so" is noisy while "quietly stop watching a live
    trading bot" is the failure with no symptom.
    """
    raw = _instance_config(bot_key)
    if raw is None:
        return True                      # could not ask — keep watching, and be noisy about it
    return raw.get("account") is not None


# ⚠ `BOT_THRESHOLDS` and `shared/thresholds.json` were deleted 2026-08-05 with the P&L
# tracker. They were that job's daily-goal / daily-cap / weekly-cap ALERT levels and had
# no other consumer, so with the job gone they were a cap nothing read and nothing
# enforced. A real risk cap has to live inside the bot's own loop, where it can refuse a
# trade — an alert is a message, not a limit.


def _state_file(bot_key: str) -> Path:
    return BOT_INSTANCES[bot_key] / "bot_state.json"


def _load_instance_state(instance_dir: Path) -> dict:
    path = instance_dir / "bot_state.json"
    if path.exists():
        try:
            with open(path) as f:
                return json.load(f)
        except Exception:
            pass
    return {}


def _save_instance_state(instance_dir: Path, state: dict):
    path = instance_dir / "bot_state.json"
    state["last_updated"] = datetime.utcnow().isoformat()
    with open(path, "w") as f:
        json.dump(state, f, indent=2)


def read_bot(bot_key: str) -> dict:
    """Read state for a single bot."""
    instance_dir = BOT_INSTANCES[bot_key]
    state = _load_instance_state(instance_dir)
    return state.get(bot_key, _default_state(bot_key))


def read_all() -> dict:
    """Read state for all bots. Returns {bot_key: state_dict}."""
    result = {}
    for bot_key in BOT_INSTANCES:
        result[bot_key] = read_bot(bot_key)
    return result


def write_bot(bot_key: str, updates: dict):
    """Update fields for a single bot. Merges with existing state."""
    instance_dir = BOT_INSTANCES[bot_key]
    state = _load_instance_state(instance_dir)
    if bot_key not in state:
        state[bot_key] = _default_state(bot_key)
    state[bot_key].update(updates)
    _save_instance_state(instance_dir, state)


def set_started(bot_key: str):
    """Mark bot as started — called by coordinator."""
    write_bot(bot_key, {
        "status":  "running",
        "started": time.time(),
        "account": read_account(bot_key),
    })


def set_status(bot_key: str, status: str):
    """Update bot status. Called by monitor."""
    write_bot(bot_key, {"status": status})


def get_uptime_str(bot_key: str) -> str:
    """Get human-readable uptime string."""
    state = read_bot(bot_key)
    started = state.get("started", 0)
    if not started:
        return ""
    delta   = time.time() - started
    hours   = int(delta // 3600)
    minutes = int((delta % 3600) // 60)
    if hours >= 24:
        days  = hours // 24
        hours = hours % 24
        return f"{days}d {hours}h {minutes}m"
    elif hours > 0:
        return f"{hours}h {minutes}m"
    else:
        return f"{minutes}m"


def ensure_starting_balance(bot_key: str, balance: float) -> None:
    """Write starting_balance once on first run — never overwritten after that.
    Call this at bot startup after MT5 connects and balance is confirmed."""
    if not read_bot(bot_key).get("starting_balance"):
        write_bot(bot_key, {"starting_balance": round(balance, 2)})


def _default_state(bot_key: str) -> dict:
    """Default state for a bot with no existing data."""
    return {
        "name":           BOT_NAMES.get(bot_key, bot_key),
        "status":         "stopped",
        "started":        0,
        "account":        read_account(bot_key),
        # None, not 0.0 — a bot that has never run has NO balance and NO P&L, and a zero
        # here is the claim "flat account". `live/runner.py` writes both on every poll.
        "balance":        None,
        "total_pnl_pct":  None,
        "day_locked":     False,
        "lock_reason":    "",
        "lock_alerted":   False,
        "resume_trading": False,
        "last_updated":   "",
    }
