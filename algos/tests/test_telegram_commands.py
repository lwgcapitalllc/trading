"""What the Telegram bot can be asked to do — and what it deliberately cannot.

🔴 **Six commands were deleted on 2026-08-05 and this file is why they stay deleted.** Every one
of them depended on `BOTS` / `TASK_NAMES`, which had been empty dicts since the four
first-attempt bots were removed in June:

* `/restart` and `/stop` asked for a confirmation, acted on an empty list, and **reported
  success** — a control that appears to work is worse than a missing one;
* `/trades` read a per-bot trades file the live runner has never written, so it always said 0;
* `/resume` and `/resetweek` drove `day_locked` and the weekly counters, written by
  `pnl_tracker.py`, deleted the same week;
* `/emergency` matched the same empty registry;
* `/confirm` went with them because nothing can create a pending action any more — keeping it
  would have left exactly the same defect, one level quieter.

Aaron asked which of these were still in use. The answer was none of them, and the reason is the
transferable part: **a command that resolves through a registry can go dead without changing, and
from outside it looks identical to one that works.**

The tests are therefore in two halves: the deleted ones are gone from every surface at once (the
router, the role table, the help text), and `/status` reads state the RUNNER writes rather than a
registry in this file, which is the same failure that killed the others.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

_ALGOS = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_ALGOS / "shared"))
sys.path.insert(0, str(_ALGOS / "notifications"))


@pytest.fixture
def bot(monkeypatch, tmp_path):
    """Import the module with its credentials stubbed and its VPS paths pointed at tmp_path."""
    monkeypatch.setenv("LWG_TELEGRAM_TOKEN", "T")
    monkeypatch.setenv("LWG_TELEGRAM_CHAT_ID", "-100trades")
    for name in ("telegram_bot",):
        sys.modules.pop(name, None)
    import telegram_bot as tb

    monkeypatch.setattr(tb, "ALGOS_ROOT", tmp_path, raising=False)
    monkeypatch.setattr(tb, "USERS_FILE", tmp_path / "users.json", raising=False)
    # The real file shape — `load_users` reads the "users" key, and a flat dict would silently
    # fall through to the admin-only default and test something else.
    (tmp_path / "users.json").write_text(
        json.dumps({"users": {"1": {"name": "Aaron", "role": "admin"}}})
    )
    return tb


DELETED = ["/restart", "/stop", "/emergency", "/trades", "/resume", "/resetweek", "/confirm"]


# ── the deleted six (and /confirm) ───────────────────────────────────────────────
@pytest.mark.parametrize("cmd", DELETED)
def test_a_deleted_command_is_not_answered(bot, cmd):
    """It must say it does not know the command. The failure being prevented is the opposite:
    `/stop` used to reply "Confirm Required", then do nothing."""
    reply = bot.handle_message(cmd, "-100", "1")
    assert "Unknown command" in reply


@pytest.mark.parametrize("cmd", DELETED)
def test_a_deleted_command_is_in_no_role(bot, cmd):
    """A role granting a command that does not dispatch reads as a working permission — the same
    reason `/force` and the report shortcuts were pulled out of this table in the first place."""
    for role, allowed in bot.ROLE_COMMANDS.items():
        assert cmd not in allowed, f"{role} still holds {cmd}"


@pytest.mark.parametrize("cmd", DELETED)
def test_a_deleted_command_is_not_advertised(bot, cmd):
    """A help text is a promise. The old one listed nine commands that could not work, which is
    how you find out at the moment you need one."""
    assert cmd not in bot.cmd_help()


def test_the_helpers_behind_them_are_gone_too(bot):
    """Left in place they are dead code wearing a working name, and the next person wires a new
    command to `do_stop` and gets an empty-list no-op all over again."""
    for gone in (
        "do_restart",
        "do_stop",
        "do_emergency_stop",
        "cmd_trades",
        "cmd_confirm",
        "request_confirm",
        "parse_bot_key",
        "task_start",
        "task_stop",
        "get_today_trades",
        "BOTS",
        "TASK_NAMES",
        "pending_actions",
    ):
        assert not hasattr(bot, gone), f"{gone} survived the deletion"


def test_this_module_cannot_stop_a_bot(bot):
    """The load-bearing one. Control lives in the command center, which can see how many copies
    of a bot are running — the guard against a duplicate had to live with the PROCESS
    (`startup_coordinator.py`, 2026-08-04), so a phone command that cannot count processes cannot
    be made safe by adding a confirmation step."""
    src = (_ALGOS / "notifications" / "telegram_bot.py").read_text()
    assert "taskkill" not in src
    assert 'call", "terminate' not in src
    assert "schtasks" not in src


# ── what remains ─────────────────────────────────────────────────────────────────
def test_the_surviving_commands_still_answer(bot, monkeypatch):
    monkeypatch.setattr(bot, "cmd_status", lambda: "STATUS")
    monkeypatch.setattr(bot, "cmd_balance", lambda: "BALANCE")
    assert bot.handle_message("/status", "-100", "1") == "STATUS"
    assert bot.handle_message("/balance", "-100", "1") == "BALANCE"
    assert "/help" in bot.handle_message("/help", "-100", "1")


def test_help_lists_exactly_what_dispatches(bot):
    """The check that keeps this honest as commands come and go: every command the help text
    names must be one the router answers, and vice versa."""
    advertised = {w.strip("`,.") for w in bot.cmd_help().split() if w.startswith("`/")}
    advertised = {a.strip("`") for a in advertised}
    for cmd in advertised:
        assert "Unknown command" not in bot.handle_message(cmd, "-100", "1"), (
            f"{cmd} is advertised but not answered"
        )


# ── /status reads the runner's own state ─────────────────────────────────────────
def _state(**over):
    st = {
        "name": "SOS Fade",
        "status": "live",
        "balance": 2000.0,
        "heartbeat": 1e12,
        "mt5_link": True,
    }
    st.update(over)
    return {"sos_fade_demo": st}


def test_status_lists_a_bot_that_is_running(bot, monkeypatch):
    """🔴 It could not, until this pass: `cmd_status` looped over a `BOT_SCRIPTS = {}` literal
    declared two lines above the loop, so it printed a heading with nothing under it. The state
    files are written by the runner every poll, so a bot appears here by RUNNING — the only
    registry that cannot go stale."""
    import bot_state

    monkeypatch.setattr(bot_state, "read_all", lambda: _state())
    monkeypatch.setattr(bot_state, "get_uptime_str", lambda k: "3h 12m")
    monkeypatch.setattr(bot, "is_running", lambda s: True)
    out = bot.cmd_status()
    assert "SOS Fade" in out
    assert "3h 12m" in out
    assert "$2,000.00" in out


def test_status_separates_alive_from_blind(bot, monkeypatch):
    """A bot can be running and seeing no market at all — that is exactly what happened on
    2026-08-04, when MetaTrader restarted underneath it and every check in the system still said
    RUNNING. Two facts, never merged."""
    import bot_state

    monkeypatch.setattr(bot_state, "read_all", lambda: _state(mt5_link=False))
    monkeypatch.setattr(bot_state, "get_uptime_str", lambda k: "3h 12m")
    monkeypatch.setattr(bot, "is_running", lambda s: True)
    out = bot.cmd_status()
    assert "no MT5 link" in out
    assert "stopped" not in out  # it IS running; that is the other fact


def test_an_unasked_link_is_not_reported_as_disconnected(bot, monkeypatch):
    """`mt5_link` is Optional[bool] and None means the bot never said. Read falsy rather than
    `is False` and a bot that has simply not stamped one yet is painted as disconnected — the
    repo's standing rule, from the reassuring side this time.

    ⚠ **This one passed VACUOUSLY against the code at HEAD** and is kept with the label on: the
    old `cmd_status` listed no bots at all, so "no MT5 link" was trivially absent from its output.
    It is a real check only now that the command lists something. Recorded because the same trap
    cost two browser checks on the Stress Tests audit the same week — a green test proves nothing
    until you have seen it red for the right reason.
    """
    import bot_state

    monkeypatch.setattr(bot_state, "read_all", lambda: _state(mt5_link=None))
    monkeypatch.setattr(bot_state, "get_uptime_str", lambda k: "1m")
    monkeypatch.setattr(bot, "is_running", lambda s: True)
    assert "no MT5 link" not in bot.cmd_status()


def test_status_matches_the_bot_key_not_the_script_name(bot, monkeypatch):
    """Every live bot IS `runner.py`, so the script identifies the FLEET and only the key
    identifies the bot. Matching on the script would call every bot running as soon as any one
    of them was."""
    seen = []
    import bot_state

    monkeypatch.setattr(bot_state, "read_all", lambda: _state())
    monkeypatch.setattr(bot_state, "get_uptime_str", lambda k: "1m")
    monkeypatch.setattr(bot, "is_running", lambda s: seen.append(s) or True)
    bot.cmd_status()
    assert "--bot sos_fade_demo" in seen


def test_status_says_so_when_nothing_has_written_a_state_file(bot, monkeypatch):
    """Silence would read as "all quiet". An empty answer and a broken one must not look
    alike — the rule this repo has now met six times."""
    import bot_state

    monkeypatch.setattr(bot_state, "read_all", lambda: {})
    monkeypatch.setattr(bot, "is_running", lambda s: False)
    out = bot.cmd_status()
    assert "No bot has written a state file" in out
