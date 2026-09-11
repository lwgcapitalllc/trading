"""Is NinjaTrader switched off ON PURPOSE? The box says so — by its agent's scheduled task.

Aaron shut NinjaTrader down on the VPS on 2026-09-11 to save memory, and this app went on treating
that as a fault: a yellow dot telling him to open NT8 over RDP, and — once the agent is stopped
too — a red "click to start", a supervisor re-firing the task every minute, and every NT8 call
failing with a bare connection error. **A platform that is off on purpose and a platform that has
died looked identical, because nothing recorded the intent.**

🔴 **THE INTENT LIVES ON THE BOX, AS THE `NT8Agent` TASK BEING DISABLED — never in this app.** A
setting on this laptop would be one machine's opinion about the VPS: the other clone would go on
complaining, and the day NT8 is switched back on the stale copy would refuse NT8 jobs with a
confident wrong reason. Disabling the task is also what actually KEEPS it off — it is the task
Windows fires at logon and the supervisor fires to recover the agent — so the marker and the
mechanism are one thing and cannot disagree.

    enabled   the task can run — NT8 is meant to be on, and a dead agent is a fault
    disabled  switched off on purpose
    missing   no such task on the box — nothing there can start the agent either
    None      the box could not be ASKED. Not "enabled" and not "off" (rule 1).

⚠ **Read in the BACKGROUND, served from memory.** The supervisor's loop calls `refresh()`; the
health endpoint and every other reader call `switched_off()`, which never touches the network —
a request handler must not make an SSH call that can take seconds. Before the first answer
lands, every reader gets `None` and behaves exactly as it did before this existed.

⚠ **A failed read KEEPS the last answer.** The task only changes when somebody changes it, and
the box refuses a third of new SSH connections when it is crowded (`vps_ssh.py`); forgetting a
good answer on one refused connection would flip the sidebar back to red for a platform that is
still off.
"""

from __future__ import annotations

import subprocess
import threading
import time
from typing import Optional

import config as cfg

from services import vps_ssh

# How stale an answer may get before the supervisor asks again. The task changes only by hand, so
# this bounds how long switching NT8 back on takes to be noticed — two minutes, at one tiny SSH
# call per two minutes against a box that sees far more than that from the internet.
MAX_AGE_S = 120

ENABLED, DISABLED, MISSING = "enabled", "disabled", "missing"
_OFF = (DISABLED, MISSING)

_lock = threading.Lock()
_state: Optional[str] = None  # the last answer the box gave
_asked_at: float = 0.0  # when we last TRIED, answered or not — so a dead box is not hammered


def parse_task_state(returncode: int, stdout: str, stderr: str) -> Optional[str]:
    """`schtasks /query /tn <task> /v /fo LIST` → one of the three answers, or None.

    🔴 **It reads `Scheduled Task State`, never `Status`, and the difference was MEASURED on the
    box the day this was built.** Disabling a task whose agent is still alive leaves `Status:
    Running` until that process ends — so the short `Status` column said the task was running at
    the very moment it was switched off. `Scheduled Task State` is the Enabled/Disabled flag itself.
    ⚠ **Match that LABEL exactly**: the same output carries `Idle Time: Disabled` and `Delete Task
    If Not Rescheduled: Disabled`, which say nothing about whether the task can run.
    ⚠ `Disabled` is the ONLY value that means off — anything else is an enabled task, so an
    unfamiliar word can never silence a real outage. ⚠ A missing task is recognised by its message;
    any other failure (ssh's own 255, a refusal, garbage) is `None`, never a guess.
    """
    if returncode == 0:
        for line in (stdout or "").splitlines():
            label, sep, value = line.partition(":")
            if sep and label.strip().lower() == "scheduled task state":
                return DISABLED if value.strip().lower() == "disabled" else ENABLED
        return None
    text = f"{stdout or ''}\n{stderr or ''}".lower()
    # Windows words it two ways depending on the build.
    if returncode != 255 and ("cannot find" in text or "does not exist" in text):
        return MISSING
    return None


def _task_name() -> str:
    # Imported here, not at module load: agent_supervisor imports this module.
    from services import agent_supervisor

    return agent_supervisor.NT8_TASK


def _read_from_box() -> Optional[str]:
    """One SSH round trip. `None` on anything short of a readable answer."""
    try:
        result = vps_ssh.run(
            [
                "ssh",
                "-o",
                "ConnectTimeout=5",
                "-o",
                "BatchMode=yes",
                cfg.SSH_ALIAS,
                f"schtasks /query /tn {_task_name()} /v /fo LIST",
            ],
            capture_output=True,
            text=True,
            timeout=15,
        )
    except (subprocess.TimeoutExpired, OSError):
        return None
    return parse_task_state(result.returncode, result.stdout, result.stderr)


def refresh(max_age: float = MAX_AGE_S, now: Optional[float] = None) -> Optional[str]:
    """Ask the box if the last attempt is older than `max_age`. Returns the current answer.

    The SSH call runs OUTSIDE the lock, so a slow box never holds up a reader.
    """
    global _state, _asked_at
    now = time.time() if now is None else now
    with _lock:
        if _asked_at and now - _asked_at < max_age:
            return _state
        _asked_at = now
    answer = _read_from_box()
    with _lock:
        if answer is not None:
            _state = answer
        return _state


def state() -> Optional[str]:
    """The last answer the box gave, from memory. Never touches the network."""
    with _lock:
        return _state


def switched_off() -> Optional[bool]:
    """True = off on purpose, False = meant to be on, None = the box has not been asked yet."""
    s = state()
    return None if s is None else s in _OFF


def off_reason() -> Optional[str]:
    """The sentence a reader sees for WHY it cannot connect — or None when NT8 is not off."""
    s = state()
    if s == DISABLED:
        return (
            "NinjaTrader is switched off on the VPS on purpose — its NT8Agent task is disabled, "
            "so nothing starts or restarts it. To bring it back: enable and run that task, then "
            "open NinjaTrader over RDP."
        )
    if s == MISSING:
        return (
            "NinjaTrader is not set up on the VPS — there is no NT8Agent task, so nothing can "
            "start its agent."
        )
    return None


def _reset() -> None:
    """Forget everything — for tests, which share this module's memory within a worker."""
    global _state, _asked_at
    with _lock:
        _state, _asked_at = None, 0.0
