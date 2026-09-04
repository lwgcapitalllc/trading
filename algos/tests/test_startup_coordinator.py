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

_REPO = Path(__file__).resolve().parent.parent.parent
# `bots/` for the module itself, `shared/` for the `bot_state` it imports bare — the coordinator
# runs from `C:\trading\algos\bots` on the VPS, where both are already on the path.
for _p in (_REPO / "algos" / "bots", _REPO / "algos" / "shared", _REPO / "algos" / "live"):
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
    monkeypatch.setattr(
        sc.subprocess,
        "run",
        _wmic(
            "CommandLine\n"
            "python.exe C:\\trading\\algos\\bots\\startup_coordinator.py --bot sos_fade_demo\n"
        ),
    )

    assert sc.bot_is_running("sos_fade_demo") is False


def test_a_real_runner_process_is_still_detected(monkeypatch):
    """The other direction, and the one that matters more: a second copy of a live bot is two
    positions on one account, sized off the same setup, from a state neither can see."""
    monkeypatch.setattr(
        sc.subprocess,
        "run",
        _wmic(
            "CommandLine\n"
            "python.exe C:\\trading\\algos\\live\\runner.py --bot sos_fade_demo --live\n"
        ),
    )

    assert sc.bot_is_running("sos_fade_demo") is True


def test_another_bots_runner_is_not_this_bot(monkeypatch):
    """Every live bot IS `runner.py`, so the script names the fleet and only the key names the
    bot. Requiring both must not have collapsed that into "any runner will do"."""
    monkeypatch.setattr(
        sc.subprocess,
        "run",
        _wmic(
            "CommandLine\npython.exe C:\\trading\\algos\\live\\runner.py --bot b_leg_demo --live\n"
        ),
    )

    assert sc.bot_is_running("sos_fade_demo") is False


def test_the_pair_is_required_not_either_half(monkeypatch):
    """A line holding the right script and a line holding the right key are not, between them, a
    running bot. The match is per LINE."""
    monkeypatch.setattr(
        sc.subprocess,
        "run",
        _wmic(
            "CommandLine\n"
            "python.exe C:\\trading\\algos\\live\\runner.py --bot other_bot\n"
            "python.exe C:\\trading\\algos\\bots\\startup_coordinator.py --bot sos_fade_demo\n"
        ),
    )

    assert sc.bot_is_running("sos_fade_demo") is False


def test_the_runners_own_guard_does_not_match_the_coordinator_that_launched_it(
    monkeypatch, tmp_path
):
    """🔴 The SAME defect one level down, found by reading rather than by it biting.

    `runner.already_running()` excluded its own PID but matched on `--bot <key>` alone — and
    `startup_coordinator.py --bot <key>` carries that key too. In single-bot mode the coordinator
    Popens the runner and exits, so the runner's check RACES its own launcher and would
    sometimes refuse to start the very bot it was asked for, logging an error and returning 0.

    ⚠ The PID rule and the script+key pair cover different impostors — itself, and its launcher —
    so both stay.
    """
    import json

    import live_config
    import runner as rn

    body = {
        "bot_key": "smoke",
        "mt5_path": "C:/MT5/x.exe",
        "account": 1,
        "server": "Demo",
        "symbol": "XAUUSD",
        "magic": 1,
    }
    (tmp_path / "smoke").mkdir(parents=True)
    (tmp_path / "smoke" / "config.json").write_text(json.dumps(body))
    monkeypatch.setattr(live_config, "_INSTANCES", tmp_path)
    r = rn.LiveRunner.__new__(rn.LiveRunner)
    r.cfg = live_config.load("smoke")
    r.log = type(
        "L", (), {"warning": staticmethod(lambda *a: None), "error": staticmethod(lambda *a: None)}
    )()

    # `already_running` imports subprocess inside the method, so the module itself is the seam.
    monkeypatch.setattr(
        subprocess,
        "run",
        lambda *a, **k: subprocess.CompletedProcess(
            a,
            0,
            stdout="CommandLine  ProcessId\n"
            "python.exe C:\\t\\algos\\bots\\startup_coordinator.py --bot smoke  4242\n",
            stderr="",
        ),
    )

    assert r.already_running() is False, "the runner refused to start because of its own launcher"


def test_an_unreadable_process_list_is_treated_as_running(monkeypatch):
    """⚠ Deliberately the opposite default from `telegram_is_running`, and the asymmetry is the
    design: neither answer is safe in the abstract, each is safe against the failure ITS path
    causes. A duplicate bot is two positions; an unstarted Telegram is silence."""

    def _boom(*a, **k):
        raise OSError("wmic missing")

    monkeypatch.setattr(sc.subprocess, "run", _boom)
    assert sc.bot_is_running("sos_fade_demo") is True


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

    assert (
        sc.wait_for_connection(
            str(tmp_path / "bot.log"),
            "Connected | #",
            size_before,
            5,
            "bot",
            baseline_path=baseline_path,
        )
        is True
    )


def test_the_baseline_still_suppresses_a_previous_runs_line_in_the_same_file(tmp_path):
    """The offset exists so a restart does not read the PREVIOUS start's "Connected" line and
    declare success instantly. Fixing the new-day case must not have thrown that away."""
    p = tmp_path / "bot-2026-08-05.log"
    p.write_text("Connected | #700107749\n")
    baseline_path, size_before = sc.log_baseline(str(tmp_path / "bot.log"))

    assert (
        sc.wait_for_connection(
            str(tmp_path / "bot.log"),
            "Connected | #",
            size_before,
            1,
            "bot",
            baseline_path=baseline_path,
        )
        is False
    )


# ── the bench: a bot with no account must not be launched ─────────────────────
#
# Added 2026-08-09. `runner.run()` refuses too, but it refuses AFTER the process has been
# spawned — so without this the boot task and the watchdog would go on spawning a process every
# 60 seconds for a bot somebody deliberately took off an account.


def _instance(tmp_path, monkeypatch, key, body):
    import json

    d = tmp_path / "markets" / "fx" / "instances" / key
    d.mkdir(parents=True, exist_ok=True)
    (d / "config.json").write_text(json.dumps(body))
    monkeypatch.setattr(sc, "ALGOS", tmp_path)
    return d


def test_a_bot_with_an_account_is_assigned(tmp_path, monkeypatch):
    _instance(tmp_path, monkeypatch, "b1", {"bot_key": "b1", "account": 700107749})
    assert sc.bot_is_assigned("b1") is True


def test_a_bot_with_a_null_account_is_NOT_assigned(tmp_path, monkeypatch):
    """MUTATION: return True unconditionally -> red. This is the whole bench."""
    _instance(tmp_path, monkeypatch, "b1", {"bot_key": "b1", "account": None})
    assert sc.bot_is_assigned("b1") is False


def test_a_missing_account_key_is_NOT_assigned(tmp_path, monkeypatch):
    """A config with no `account` at all cannot trade one either. `live_config.load` refuses it
    outright; here the honest answer is the same as the bench's."""
    _instance(tmp_path, monkeypatch, "b1", {"bot_key": "b1"})
    assert sc.bot_is_assigned("b1") is False


def test_an_UNREADABLE_config_is_treated_as_assigned(tmp_path, monkeypatch):
    """MUTATION: return False on the exception -> red.

    The OPPOSITE default to a missing account, and deliberately so. A config this cannot parse is
    a bot whose state is unknown, and every one of the runner's own checks is still in front of
    it. Of the two wrong answers, "spawn a process that refuses and says why" is recoverable and
    "quietly never start a live bot" is the failure with no symptom."""
    d = _instance(tmp_path, monkeypatch, "b1", {"bot_key": "b1", "account": None})
    (d / "config.json").write_text("{not json")
    assert sc.bot_is_assigned("b1") is True


def test_a_config_that_does_not_exist_is_treated_as_assigned(tmp_path, monkeypatch):
    monkeypatch.setattr(sc, "ALGOS", tmp_path)
    assert sc.bot_is_assigned("never_created") is True


def test_every_bot_in_the_startup_sequence_has_an_instance_config():
    """The two lists are edited separately and a bot listed here with no config would be
    launched, fail on the missing file, and be reported `offline` by the boot task."""
    from pathlib import Path

    algos = Path(__file__).resolve().parent.parent
    for entry in sc.STARTUP_SEQUENCE:
        key = entry[0]
        cfg = algos / "markets" / "fx" / "instances" / key / "config.json"
        assert cfg.exists(), f"{key} is in STARTUP_SEQUENCE with no instance config at {cfg}"
