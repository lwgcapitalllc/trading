"""deadman.py — the ONE alert that does not originate on the VPS.

**The gap this closes.** Every other alert in this suite is sent BY the VPS: the bot's own
Telegram messages, `monitor.py`'s watchdog, the bot's own entry/exit pings. So the box has
to be alive and networked to tell you it is in trouble — and if it is neither, you get
silence, which looks exactly like everything being fine. On 2026-08-04 the live bot went
blind for 50 minutes with its heartbeat ticking and the Bots page reading RUNNING; that was
survivable because the box was up. Nothing in this system covers the case where it is not.

**How it works.** A scheduled task runs this every few minutes. It checks the things that
have to be true, and pings an external URL only when they ALL are. An external service
(healthchecks.io, Cronitor, anything with the same shape) expects that ping on a schedule
and alerts YOU when it stops arriving. The alerting lives off the box, so a dead VPS, a dead
network, a dead Task Scheduler and a dead Python all produce the same outcome: an alert.

**Two signals, deliberately, and the difference matters.**

- **ping** (silence ⇒ timeout alert): sent only when everything checks out. Missing pings
  mean "nothing on that box can talk to me", and the receiving end cannot tell you why —
  it does not know why, and pretending otherwise would be a made-up diagnosis.
- **/fail** (immediate alert, with a reason): sent when this script RUNS and finds something
  wrong. The box is fine, the problem is named, and you get told at once rather than after
  the grace period.

Without the second signal a dead bot and a dead box would be the same silence, which throws
away a distinction the script is standing right next to.

⚠ **The ping is CONDITIONAL on health, and it has to be.** A task that pings unconditionally
proves only that Task Scheduler is alive — and a healthy system and a bot that died an hour
ago would produce the identical green tick. `CLAUDE.md`'s standing rule: never trust a probe
whose negative result a healthy system can also produce. The mirror is just as true — never
trust a POSITIVE result a broken system can produce.

⚠ **This never restarts anything, and that is not laziness.** `monitor.py` owns recovery.
Two independent things issuing starts for one bot is how you get two copies of it on one
account, which is exactly what happened on 2026-08-04 when the startup coordinator and a
running bot disagreed. A checker that also repairs is a second recovery path nobody is
counting.

⚠ **It is a SEPARATE task from `monitor.py` on purpose.** The watchdog is the more complex
program and the more likely to break; a dead-man's switch that shares a process with it
shares its failure modes and stops being an independent check.

**Configuration.** `deadman_url` in the git-ignored `algos/credentials.json`, or the
`LWG_DEADMAN_URL` environment variable. The URL is a SECRET — anyone holding it can send
your pings for you and keep the alert permanently green — so it is resolved through
`credentials.py` like every other secret and never written into a file git can see.

Unset is a valid, supported state: the script says so and exits 0. It must not become a
scheduled task that fails every five minutes, because a task everyone has learned to ignore
is worse than no task.

Run:
    python C:/trading/algos/notifications/deadman.py
    python C:/trading/algos/notifications/deadman.py --status   # is it configured? no ping
    python C:/trading/algos/notifications/deadman.py --dry-run  # check + print, never send
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
import time
from pathlib import Path

ALGOS_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ALGOS_ROOT / "shared"))

from credentials import env_name, get  # noqa: E402

# Which bots must be alive for this box to count as healthy. Keyed the same way
# `monitor.py` and `startup_coordinator.py` key theirs, and for the same reason: every live
# bot is `runner.py`, so `--bot <key>` in the commandline is the only thing that identifies
# ONE of them. Keep the three registries in step.
BOTS = {
    "mpc_sos_fade_demo": "MPC SOS Fade",
}

# A bot stamps its heartbeat every poll (~60s). `monitor.py` uses a 5-minute staleness floor
# and this deliberately matches it: two watchdogs disagreeing about what "stalled" means
# would alert on different bars and each look wrong to the other.
HEARTBEAT_STALE_SECS = 5 * 60

# Appended to the configured URL to report a detected failure. This is healthchecks.io's
# shape and Cronitor's `?state=fail` is the other common one — if the provider changes, this
# is the single line that changes.
FAIL_SUFFIX = "/fail"

_TIMEOUT = 15


def _bot_state() -> dict:
    """The whole bot_state.json, or {} if it cannot be read.

    ⚠ Unreadable is NOT empty, and the caller must not conflate them — `check_health` reports
    a missing file as a FAILURE rather than as "no bots to check", which would ping green on
    a box whose state file had been deleted.
    """
    import bot_state as bs

    out: dict = {}
    for key in BOTS:
        try:
            path = bs.BOT_INSTANCES[key] / "bot_state.json"
            out[key] = json.loads(path.read_text()).get(key) or {}
        except Exception:
            out[key] = None      # None = could not ask. Never {} — see the docstring above.
    return out


def _running_keys() -> set[str] | None:
    """Which registered bots have a live process. None when the process list is unreadable.

    None is a third answer and the callers treat it as a failure, not as "nothing running":
    reporting a box we cannot inspect as either healthy or dead is a guess, and one of those
    guesses is silent.
    """
    try:
        r = subprocess.run(
            ["wmic", "process", "where", "name='python.exe'", "get", "commandline"],
            capture_output=True, text=True, timeout=10,
        )
    except Exception:
        return None
    return {k for k in BOTS if f"--bot {k}" in r.stdout}


def check_health(now: float | None = None) -> list[str]:
    """Everything currently wrong, as human sentences. Empty list = healthy.

    Returns REASONS rather than a bool so the /fail body can say what happened — an
    immediate alert that only says "something is wrong" sends you to the box to find out
    what, which is the trip the alert exists to save.
    """
    now = time.time() if now is None else now
    problems: list[str] = []

    running = _running_keys()
    if running is None:
        return ["cannot read the process list - the box is not answering wmic"]

    states = _bot_state()
    for key, name in BOTS.items():
        if key not in running:
            problems.append(f"{name}: process is not running")
            continue

        st = states.get(key)
        if st is None:
            problems.append(f"{name}: bot_state.json cannot be read")
            continue

        hb = st.get("heartbeat")
        if not isinstance(hb, (int, float)):
            problems.append(f"{name}: no heartbeat recorded")
        elif now - hb > HEARTBEAT_STALE_SECS:
            problems.append(f"{name}: heartbeat is {int(now - hb)}s old (stalled)")

        # `mt5_link` is Optional[bool] and None means UNASKED — read it `is False`, never
        # falsy. A bot on a build that predates the field, or one that has not completed a
        # poll yet, must not be reported as having a dead terminal link.
        if st.get("mt5_link") is False:
            problems.append(f"{name}: MT5 link is down (the terminal is not answering)")

    return problems


def deadman_url() -> str:
    return (get("deadman_url") or "").strip()


def _send(url: str, body: str = "") -> bool:
    import urllib.error
    import urllib.request

    data = body.encode("utf-8", errors="replace") if body else None
    try:
        with urllib.request.urlopen(url, data=data, timeout=_TIMEOUT) as r:
            return 200 <= r.status < 300
    except Exception as e:
        # A failed ping is loud in the log and fatal to nothing. The external service will
        # raise the alarm on its own when the pings stop, which is precisely the job — this
        # script crashing here would just be one more thing that has to work.
        print(f"  ! ping failed: {e}")
        return False


def main(argv=None) -> int:
    # ⚠ Everything PRINTED below is plain ASCII on purpose. The VPS console is cp1252 and cannot
    # encode an em-dash; `logging` responds by DISCARDING the record (which is how the live bot
    # silently lost log lines on 2026-07-31) and a bare print mangles it. The docstrings and
    # comments in this file are unrestricted — they are never written to that console.
    ap = argparse.ArgumentParser(description="External dead-man's switch")
    ap.add_argument("--status", action="store_true", help="report configuration, send nothing")
    ap.add_argument("--dry-run", action="store_true", help="run the checks, send nothing")
    args = ap.parse_args(argv)

    url = deadman_url()

    if args.status:
        if url:
            print(f"configured: yes  ({url[:28]}...)")
        else:
            print("configured: NO - there is no external dead-man's switch on this box.")
            print(f"  set `deadman_url` in {ALGOS_ROOT / 'credentials.json'}"
                  f" or {env_name('deadman_url')}")
        return 0

    problems = check_health()

    if problems:
        print("UNHEALTHY:")
        for p in problems:
            print(f"  - {p}")
    else:
        print("healthy")

    if not url:
        # Not an error. A box with no switch configured is a known gap, and a task that
        # fails every five minutes teaches everyone to ignore it — which is how a real
        # failure gets ignored too.
        print("no deadman_url configured - nothing sent (see --status)")
        return 0

    if args.dry_run:
        print(f"dry run - would have pinged {url}{FAIL_SUFFIX if problems else ''}")
        return 0

    if problems:
        ok = _send(url + FAIL_SUFFIX, "\n".join(problems))
    else:
        ok = _send(url)
    print("  sent" if ok else "  NOT sent")

    # Exit 0 either way. The exit code is read by Task Scheduler, which reports it to nobody;
    # the real signal is whether the external service heard from us, and that is the whole
    # point of putting it off the box.
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
