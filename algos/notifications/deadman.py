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
    "sos_fade_demo": "SOS Fade",
    # On the BENCH today (`account: null`). Registered anyway, and skipped per-pass by
    # `_is_assigned` — see the same note in `monitor.py`: registering a bot only once somebody
    # assigns it would let the Bots page arm a bot no switch is watching.
    "b_leg_demo": "B-LEG",
    # Benched too, and registered for the same reason.
    "extreme_leg_demo": "Extreme Leg",
    # The demo copies of the two live bots (2026-09-11), registered from birth for that reason.
    # Same names as the originals: the account's kind tells them apart (`bot_state.bot_label`).
    "sos_fade_2": "SOS Fade",
    "extreme_leg_2": "Extreme Leg",
}

# A bot stamps its heartbeat every poll (~60s). `monitor.py` uses a 5-minute staleness floor
# and this deliberately matches it: two watchdogs disagreeing about what "stalled" means
# would alert on different bars and each look wrong to the other.
HEARTBEAT_STALE_SECS = 5 * 60

# 🔴 **How long a problem must PERSIST before it is worth waking somebody for.**
#
# Every restart — a deploy, or the watchdog recovering a crash — takes a bot away for about a
# minute, and a 5-minute pass landing in that window sent `/fail` and paged for a button
# somebody had just pressed on purpose. **An alarm that fires when you press the button is one
# you learn to scroll past**, which this repo has already paid for twice, and then it cannot
# tell you about the thing it exists for.
#
# ⚠ **MEASURED, not picked** (rule 4). From the bots' own logs on 2026-09-09, a deliberate
# stop-to-online cycle is **~55s** (`sos_fade_demo` 12:19:33 → 12:20:28) and **~60s**
# (`extreme_leg_demo` 12:19:38 → 12:20:38, of which 19.7s is warm-up). The watchdog's own
# recovery is slower and is the real ceiling: up to 60s to notice, then a restart it confirms
# after an 8s settle — **~130s worst case**. 180s clears that with margin and is still well
# inside the time a genuinely dead box stays dead.
CONFIRM_SECS = 180

# Where the first-seen times live. Git-ignored, beside the other watchdog state.
PENDING_FILE = ALGOS_ROOT / "deadman_pending.json"

# Appended to the configured URL to report a detected failure. This is healthchecks.io's
# shape and Cronitor's `?state=fail` is the other common one — if the provider changes, this
# is the single line that changes.
FAIL_SUFFIX = "/fail"

_TIMEOUT = 15


def _is_assigned(bot_key: str) -> bool:
    """Whether this bot has an account, i.e. whether anything should expect it to be running.

    Thin wrapper over `bot_state.is_assigned` — the ONE definition of the bench, shared with the
    boot coordinator and the process watchdog. Imported inside the function for the reason
    `_bot_state` does the same: this module is loaded by tests off the VPS, where `algos/shared`
    reaches the path only once something has put it there.

    ⚠ **Unreadable answers True**, so a config that cannot be parsed keeps being watched. Of the
    two wrong answers, a noisy alarm is recoverable and a switch that quietly stopped covering a
    live trading bot is the failure this whole module exists to prevent.
    """
    try:
        import bot_state as bs

        return bs.is_assigned(bot_key)
    except Exception:
        return True


def _label(bot_key: str, name: str) -> str:
    """`name` plus LIVE or demo, off the account this bot's own config names
    (`bot_state.labelled`). Two copies of one strategy share a name since 2026-09-11, and a failure
    report that says "SOS Fade: process is not running" would not say which one. The plain name if
    the lookup cannot run — a report that cannot say which copy is still worth sending."""
    try:
        import bot_state as bs

        return bs.labelled(name, bs.read_account(bot_key))
    except Exception:
        return name


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
            out[key] = None  # None = could not ask. Never {} — see the docstring above.
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
            capture_output=True,
            text=True,
            timeout=10,
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
        # On the BENCH — no account, so nothing expects it to be running and its absence is not
        # a fault. This switch's whole value is that its silence MEANS something, so a benched
        # bot holding it permanently in the failed state would make the one alarm that fires
        # when the box dies indistinguishable from a configuration choice.
        if not _is_assigned(key):
            continue
        name = _label(key, name)
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


def _read_pending() -> dict:
    """When each outstanding problem was FIRST seen, or `None` if that cannot be read.

    ⚠ **`None` is CANNOT ASK and the caller must not read it as "nothing outstanding".** Not
    knowing how long a problem has been going on may never buy the reassuring answer — that is
    rule 1, and here it decides whether a real failure is held quiet.
    """
    try:
        data = json.loads(PENDING_FILE.read_text())
    except FileNotFoundError:
        return {}  # genuinely nothing outstanding — different from unreadable
    except Exception:
        return None
    return data if isinstance(data, dict) else None


def confirmed_problems(problems: list, now: float | None = None, persist: bool = True) -> list:
    """The problems that have lasted longer than `CONFIRM_SECS`, and therefore deserve an alarm.

    **A problem seen for the first time is RECORDED and withheld**, so the ~60s hole a restart
    punches in the world does not page anybody. One that is still there on the next pass is
    real and goes out with its full age attached.

    🔴 **This is deliberately NOT flap detection, and that boundary is the module's charter.**
    A bot dying and being restarted repeatedly is `monitor.py`'s finding — it already sends an
    OFFLINE and a RESTARTED message per occurrence, into the room somebody reads. **This switch
    answers one question: can anything on that box still talk to me.** Teaching it a second
    question is how one event becomes two alarms and the channel gets muted.

    ⚠ **An unreadable state file ALARMS rather than suppressing.** Noisy once beats silent
    forever, and it is the same call `log_review.py` makes for the same reason.

    ⚠ **`persist=False` for a dry run**, so a preview cannot start somebody's grace clock and
    make the next real pass alarm early — the same call `watch_broker_costs.py` makes about not
    consuming tomorrow's first reading.
    """
    now = time.time() if now is None else now
    if not problems:
        # Nothing wrong: forget everything, so the next problem earns its own grace rather than
        # inheriting a stale timestamp and alarming instantly.
        if persist:
            try:
                PENDING_FILE.unlink()
            except FileNotFoundError:
                pass
            except Exception as e:
                print(f"  ! could not clear the pending file: {e}")
        return []

    pending = _read_pending()
    if pending is None:
        print("  ! pending file unreadable - reporting everything rather than holding it quiet")
        return list(problems)

    fresh, confirmed = {}, []
    for p in problems:
        first_seen = pending.get(p)
        if not isinstance(first_seen, (int, float)):
            first_seen = now
        fresh[p] = first_seen
        age = now - first_seen
        if age >= CONFIRM_SECS:
            confirmed.append(f"{p} (for {int(age)}s)")
        else:
            print(f"  holding (only {int(age)}s old, confirming at {CONFIRM_SECS}s): {p}")

    if persist:
        try:
            PENDING_FILE.write_text(json.dumps(fresh))
        except Exception as e:
            # We still hold a correct verdict for THIS pass; we just cannot remember it. Say so —
            # silently forgetting would reset every problem's age on every pass and mean nothing
            # ever reaches CONFIRM_SECS, i.e. an alarm that can never fire.
            print(f"  ! could not record pending problems ({e}) - ages will restart next pass")

    return confirmed


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
            print(
                f"  set `deadman_url` in {ALGOS_ROOT / 'credentials.json'}"
                f" or {env_name('deadman_url')}"
            )
        return 0

    found = check_health()

    if found:
        print("PROBLEMS SEEN:")
        for p in found:
            print(f"  - {p}")
    else:
        print("healthy")

    # Only a problem that OUTLASTS a restart is worth an alarm. Everything below reads
    # `problems`, so a held-back problem pings healthy exactly as a clean pass does — which is
    # the point: the box is answering, and the thing that is briefly wrong is already being
    # dealt with by the watchdog that owns recovery.
    problems = confirmed_problems(found, persist=not args.dry_run)
    if found and not problems:
        print("nothing confirmed yet - too new to alarm on")

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
