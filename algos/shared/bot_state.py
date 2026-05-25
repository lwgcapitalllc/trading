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
  "balance":        2759.28,            # current balance (from pnl_tracker)
  "daily_pnl":      45.20,              # today's P&L in dollars
  "daily_pnl_pct":  1.64,              # today's P&L as %
  "weekly_pnl":     120.50,
  "weekly_pnl_pct": 4.37,
  "total_pnl_pct":  175.9,             # total growth since $1,000 start
  "peak_balance":   2759.28,
  "trades_today":   3,
  "day_locked":     false,
  "last_updated":   "2026-05-18T04:17:43"
}
"""

import json
import time
from datetime import datetime
from pathlib import Path

ALGOS_ROOT = Path("C:/trading/algos")

# Instance directory for each bot key
BOT_INSTANCES = {
    "smc_trend":      ALGOS_ROOT / "markets/fx/instances/gold_main",
    "mean_reversion": ALGOS_ROOT / "markets/fx/instances/gold_main",
    "scalper":        ALGOS_ROOT / "markets/fx/instances/gold_scalper",
    "fft":            ALGOS_ROOT / "markets/fx/instances/gold_fft",
}

# Account numbers for each bot
BOT_ACCOUNTS = {
    "smc_trend":      "700103491",
    "mean_reversion": "700103491",
    "scalper":        "700107520",
    "fft":            "700107749",
}

# Display names
BOT_NAMES = {
    "smc_trend":      "SMC Trend",
    "mean_reversion": "Mean Reversion",
    "scalper":        "Scalper",
    "fft":            "FFT",
}


# Thresholds
BOT_THRESHOLDS = {
    "smc_trend":      {"daily_goal": 2.0,  "daily_cap": 10.0, "weekly_cap": 20.0},
    "mean_reversion": {"daily_goal": 2.0,  "daily_cap": 10.0, "weekly_cap": 20.0},
    "scalper":        {"daily_goal": 10.0, "daily_cap": 8.0,  "weekly_cap": 20.0},
    "fft":            {"daily_goal": 2.0,  "daily_cap": 5.0,  "weekly_cap": 15.0},
}


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
        "account": BOT_ACCOUNTS[bot_key],
    })


def set_status(bot_key: str, status: str):
    """Update bot status. Called by monitor."""
    write_bot(bot_key, {"status": status})


def set_pnl(bot_key: str, balance: float, daily_pnl: float, daily_pnl_pct: float,
             weekly_pnl: float, weekly_pnl_pct: float, total_pnl_pct: float,
             peak_balance: float, trades_today: int, day_locked: bool = False):
    """Update all P&L fields. Called by pnl_tracker."""
    write_bot(bot_key, {
        "balance":        round(balance, 2),
        "daily_pnl":      round(daily_pnl, 2),
        "daily_pnl_pct":  round(daily_pnl_pct, 2),
        "weekly_pnl":     round(weekly_pnl, 2),
        "weekly_pnl_pct": round(weekly_pnl_pct, 2),
        "total_pnl_pct":  round(total_pnl_pct, 2),
        "peak_balance":   round(peak_balance, 2),
        "trades_today":   trades_today,
        "day_locked":     day_locked,
    })


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
        "account":        BOT_ACCOUNTS.get(bot_key, ""),
        "balance":        0.0,
        "daily_pnl":      0.0,
        "daily_pnl_pct":  0.0,
        "weekly_pnl":     0.0,
        "weekly_pnl_pct": 0.0,
        "total_pnl_pct":  0.0,
        "peak_balance":   0.0,
        "trades_today":   0,
        "day_locked":     False,
        "lock_reason":    "",
        "lock_alerted":   False,
        "resume_trading": False,
        "last_updated":   "",
    }
