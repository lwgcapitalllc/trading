"""Starting a bot that is down, and not starting one that is up.

**Why this file exists.** Both halves of that sentence broke on 2026-08-05, in opposite
directions, and both were found by hand rather than by the suite:

🔴 **`bot_is_running` matched the coordinator ITSELF.** In single-bot mode this process is
`startup_coordinator.py --bot <key>`, and the check was a substring search for `--bot <key>`
across the whole `wmic` dump — so it found its own commandline and reported the bot as already
running. **That is the path the command center's Start button drives**, so the button could never
start a bot, and it said the reassuring thing while failing: *"already running — left alone"*.
Found by stopping the live bot for a deploy and being unable to bring it back.

⚠ The anti-duplicate guard it belongs to is a day old and was correct in intent — two copies of
one bot is two positions on one account. **The same guard in `runner.py` got this right** by
excluding its own PID. Two implementations of one check, one of them wrong, is exactly the shape
this repo keeps meeting; the fix makes the coordinator's as specific as the runner's.

🔴 **`wait_for_connection` watched a filename that had stopped being written.** The runner moved
to one text log per UTC day the same day, so the plain `<bot>.log` in `STARTUP_SEQUENCE` never
grew again and a perfectly healthy start would have been declared `offline` after a 180s timeout.
**A healthy start reported as a failure is worse than a silent one — it sends you to fix a bot
that is fine.**
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest

_REPO = Path(__file__).resolve().parent.parent.parent
# `bots/` for the module itself, `shared/` for the `bot_state` it imports bare — the coordinator
# runs from `C:\trading\algos\bots` on the VPS, where both are already on the path.
for _p in (_REPO / "algos" / "bots", _REPO / "algos" / "shared"):
    if str(_p) not in sys.path:
        sys.path.insert(0, str(_p))
import startup_coordinator as sc  # noqa: E402


def _wmic(stdout: str):
    return lambda *a, **k: subprocess.CompletedProcess(a, 0, stdout=stdout, stderr="")


# ── is the bot running? ──────────────────────────────────────────────────────
def test_the_coordinator_does_not_mistake_itself_for_the_bot(monkeypatch):
    """🔴 THE regression. In single-bot mode the coordinator's OWN commandline carries the very
    key it is searching for, so a bare substring match makes every bot permanently "running" and
    the Start button a no-op that reports success."""
    monkeypatch.setattr(sc.subprocess, "run", _wmic(
        "CommandLine\n"
        "python.exe C:\\trading\\algos\\bots\\startup_coordinator.py --bot mpc_sos_fade_demo\n"))

    assert sc.bot_is_running("mpc_sos_fade_demo") is False


def test_a_real_runner_process_is_still_detected(monkeypatch):
    """The other direction, and the one that matters more: a second copy of a live bot is two
    positions on one account, sized off the same setup, from a state neither can see."""
    monkeypatch.setattr(sc.subprocess, "run", _wmic(
        "CommandLine\n"
        "python.exe C:\\trading\\algos\\live\\runner.py --bot mpc_sos_fade_demo --live\n"))

    assert sc.bot_is_running("mpc_sos_fade_demo") is True


def test_another_bots_runner_is_not_this_bot(monkeypatch):
    """Every live bot IS `runner.py`, so the script names the fleet and only the key names the
    bot. Requiring both must not have collapsed that into "any runner will do"."""
    monkeypatch.setattr(sc.subprocess, "run", _wmic(
        "CommandLine\n"
        "python.exe C:\\trading\\algos\\live\\runner.py --bot mpc_bleg_demo --live\n"))

    assert sc.bot_is_running("mpc_sos_fade_demo") is False


def test_the_pair_is_required_not_either_half(monkeypatch):
    """A line holding the right script and a line holding the right key are not, between them, a
    running bot. The match is per LINE."""
    monkeypatch.setattr(sc.subprocess, "run", _wmic(
        "CommandLine\n"
        "python.exe C:\\trading\\algos\\live\\runner.py --bot other_bot\n"
        "python.exe C:\\trading\\algos\\bots\\startup_coordinator.py --bot mpc_sos_fade_demo\n"))

    assert sc.bot_is_running("mpc_sos_fade_demo") is False


def test_an_unreadable_process_list_is_treated_as_running(monkeypatch):
    """⚠ Deliberately the opposite default from `telegram_is_running`, and the asymmetry is the
    design: neither answer is safe in the abstract, each is safe against the failure ITS path
    causes. A duplicate bot is two positions; an unstarted Telegram is silence."""
    def _boom(*a, **k):
        raise OSError("wmic missing")

    monkeypatch.setattr(sc.subprocess, "run", _boom)
    assert sc.bot_is_running("mpc_sos_fade_demo") is True


# ── which log is the bot actually writing? ───────────────────────────────────
def test_the_dated_log_is_found_for_a_plain_configured_path(tmp_path):
    """`STARTUP_SEQUENCE` names `<bot>.log`; the runner writes `<bot>-YYYY-MM-DD.log`. Without
    this the wait watches a file that never grows and calls a healthy start a timeout."""
    (tmp_path / "bot-2026-08-05.log").write_text("Connected | #700107749\n")

    assert sc.live_log(str(tmp_path / "bot.log")).name == "bot-2026-08-05.log"


def test_the_newest_day_wins(tmp_path):
    """A bot runs for months, so several days sit side by side. The one being written is the
    newest, and the names sort lexicographically because the dates are ISO."""
    for day in ("2026-08-03", "2026-08-05", "2026-08-04"):
        (tmp_path / f"bot-{day}.log").write_text("x")

    assert sc.live_log(str(tmp_path / "bot.log")).name == "bot-2026-08-05.log"


def test_a_plain_log_still_works_when_there_is_no_dated_one(tmp_path):
    """The fallback is not politeness — anything still writing an undated log (an older bot, a
    tool) must keep starting."""
    p = tmp_path / "bot.log"
    p.write_text("x")

    assert sc.live_log(str(p)) == p


def test_a_new_days_log_is_read_from_the_start_not_from_yesterdays_size(tmp_path):
    """⚠ The subtle half. The baseline size is taken BEFORE the launch, and on the first start
    of a UTC day the bot then writes a DIFFERENT file. Applying yesterday's size as an offset
    into today's file slices off its front — hiding the exact line being waited for, so a
    healthy bot reads as one that started and never connected."""
    (tmp_path / "bot-2026-08-04.log").write_text("y" * 5000)
    baseline_path, size_before = sc.log_baseline(str(tmp_path / "bot.log"))
    assert size_before == 5000

    # The bot starts and opens today's file.
    (tmp_path / "bot-2026-08-05.log").write_text("Connected | #700107749\n")

    assert sc.wait_for_connection(str(tmp_path / "bot.log"), "Connected | #",
                                  size_before, 5, "bot",
                                  baseline_path=baseline_path) is True


def test_the_baseline_still_suppresses_a_previous_runs_line_in_the_same_file(tmp_path):
    """The offset exists so a restart does not read the PREVIOUS start's "Connected" line and
    declare success instantly. Fixing the new-day case must not have thrown that away."""
    p = tmp_path / "bot-2026-08-05.log"
    p.write_text("Connected | #700107749\n")
    baseline_path, size_before = sc.log_baseline(str(tmp_path / "bot.log"))

    assert sc.wait_for_connection(str(tmp_path / "bot.log"), "Connected | #",
                                  size_before, 1, "bot",
                                  baseline_path=baseline_path) is False
