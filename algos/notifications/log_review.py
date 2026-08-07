"""log_review.py — read the bot's own record and say when something needs a human.

**The gap this closes, and it is a specific one.** `monitor.py` asks whether the bot process is
THERE and stamping; `deadman.py` asks whether the box can still talk to the outside world.
Neither reads a single line the bot WROTE. So until 2026-08-05 every one of these was invisible:

* **the bridge is HALTED** — the loop runs, the heartbeat ticks, the Bots page says RUNNING, and
  the bot places nothing. Nothing in this system reported it. This is the finding this module
  exists for.
* the terminal link dropped four times overnight and recovered each time;
* bars were dropped and the engines re-warmed repeatedly;
* the bot restarted five times in a day, none of them cleanly;
* a runtime config change was REFUSED and the bot is running the old settings;
* the version pin refused a start.

Every one of those leaves a record in `<instance>/ledger/health-YYYY-MM-DD.jsonl` and every one
of them was, before this, something you could only find by opening the file.

## The charter, stated so this does not grow into a second watchdog

**`monitor.py` owns NOW; this owns THE RECORD.** The watchdog answers *is it alive this minute*
and restarts it if not. This answers *what does the day's record say happened*, including things
that already recovered before anyone looked. That split is why this deliberately does NOT alert
on "process gone" or "heartbeat stale" — those are the watchdog's, and two alerts for one event
trains you to mute the channel.

⚠ **It restarts nothing, and starts nothing.** `monitor.py` owns recovery. Two independent things
issuing starts for one bot is how a book gets doubled — measured 2026-08-04. A checker that also
repairs is a second recovery path nobody is counting.

⚠ **Silent when clean.** No "nothing to report" message, ever. A daily report on a strategy that
takes ~2 trades a month says nothing 95% of the time, and a channel that is noise is the one
nobody reads on the day it matters — the reason `reporter.py` was deleted rather than fixed.

⚠ **One alert per finding, not one per run.** Findings carry a stable key that includes the
timestamp of the thing that happened, so the same halt does not ping 24 times a day while a NEW
halt still does. State lives in `algos/log_review_state.json`.

⚠ **Being unable to read is a FINDING, never silence.** An unreadable or missing health file for
a bot that is supposed to be running is reported as a problem. The standing rule this repo has
now met five times: never let "no" and "cannot ask" be the same value — and here the reassuring
answer is the dangerous one, because a checker that says nothing is indistinguishable from a
system with nothing wrong.

## Where it reports

Two places, deliberately, because they fail differently:

* **Telegram** — one message per new finding. An alert you scrolled past is gone.
* **`<instance>/review.json`** — a standing flag the command center renders as a *needs review*
  chip on the Bots page. It is still there tomorrow. ⚠ Written as its OWN file rather than into
  `bot_state.json`, because the runner rewrites that file every poll and `write_bot` is a
  read-modify-write: a review written into it would race the heartbeat and could be lost, or
  could clobber a balance.

**Which chat.** `telegram_health_chat` in the git-ignored `algos/credentials.json`, if set —
a SEPARATE chat from the one carrying fills, because these messages are routine chatter
("reconnected twice, re-warmed") and the day you mute them you must not also mute your trades.
Unset falls back to the main group and says so on stdout: an alert in the wrong room beats no
alert, which is the opposite call from `deadman.py`'s URL only because there the unset state
means the check cannot work at all.

Run:
    python C:/trading/algos/notifications/log_review.py
    python C:/trading/algos/notifications/log_review.py --dry-run   # find + print, send nothing
    python C:/trading/algos/notifications/log_review.py --all       # ignore the alerted-already state
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

ALGOS_ROOT = Path(__file__).resolve().parent.parent
STATE_FILE = ALGOS_ROOT / "log_review_state.json"

sys.path.insert(0, str(ALGOS_ROOT / "shared"))
sys.path.insert(0, str(ALGOS_ROOT / "notifications"))

import bot_state as _bot_state                                     # noqa: E402
from credentials import telegram_credentials                       # noqa: E402
from notify import chat_for, HEALTH                                # noqa: E402
from alert_format import alert, when                               # noqa: E402

# How far back a run looks. Two days so a problem late yesterday is still reported this morning,
# and so a run that crosses midnight sees the record either side of the roll.
WINDOW_DAYS = 2

# The runner pulses every 15 minutes (`live/runner._PULSE_SECONDS`). Three of those is the point
# at which a missing beat stops being a slow poll and starts being a hole. It is deliberately
# generous: this check must not become a second, vaguer version of the watchdog's stall alert.
PULSE_SECONDS = 15 * 60
PULSE_GAP_ALERT = 3 * PULSE_SECONDS

# Restarts in the window that stop looking like maintenance and start looking like a loop.
RESTART_LOOP = 4
REWARM_STORM = 4

ALERT, WARN = "alert", "warn"


class Finding:
    """One thing worth a human's attention.

    `key` must be STABLE for one occurrence and DIFFERENT for the next, which is why it carries
    the timestamp of the event rather than just its type. A key of `"halted"` would alert once
    and then never again, including for a completely new halt a week later — the failure mode of
    every de-duplicating alerter that keys on the kind of thing rather than the thing.
    """

    def __init__(self, key: str, level: str, title: str, detail: str) -> None:
        self.key, self.level, self.title, self.detail = key, level, title, detail

    def as_dict(self) -> Dict[str, str]:
        return {"key": self.key, "level": self.level,
                "title": self.title, "detail": self.detail}


# ── reading the record ───────────────────────────────────────────────────────
def health_rows(instance_dir: Path, now: datetime,
                window_days: int = WINDOW_DAYS) -> tuple[List[dict], Optional[str]]:
    """Every health record in the window, oldest first, plus a reason it could not be read.

    ⚠ Returns `(rows, problem)` rather than raising or returning `[]`. An empty list and an
    unreadable directory are different facts, and collapsing them is what would let this module
    report a healthy silence for a bot whose record it could not open at all.
    """
    ledger = instance_dir / "ledger"
    if not ledger.is_dir():
        return [], f"no ledger directory at {ledger}"

    wanted = {(now - timedelta(days=d)).strftime("%Y-%m-%d") for d in range(window_days)}
    rows: List[dict] = []
    found_any = False
    for day in sorted(wanted):
        path = ledger / f"health-{day}.jsonl"
        if not path.exists():
            continue
        found_any = True
        try:
            lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
        except OSError as e:
            return rows, f"could not read {path.name}: {e}"
        for line in lines:
            line = line.strip()
            if not line:
                continue
            try:
                rows.append(json.loads(line))
            except ValueError:
                # A torn last line is expected while the bot is appending. It is not a fault.
                continue
    if not found_any:
        return [], "no health file for today or yesterday"
    return rows, None


def _ts(row: dict) -> str:
    """The RAW timestamp, used to build a finding's dedup key.

    ⚠ Deliberately not the display form. A key carries the timestamp of the thing that happened,
    so the same halt does not ping every hour and a NEW halt still does — which means changing
    this function's output re-announces every outstanding finding exactly once. Render with
    `_at()` instead; the two are separate so the wording can be improved without waking the
    channel up.
    """
    return str(row.get("ts", "?"))


def _at(row: dict) -> str:
    """The timestamp a HUMAN reads — the box's local clock, zone named.

    A message about the past is the one case that needs an explicit time (Telegram's own stamp
    says when the message was SENT, which for an hourly reviewer is a different thing). The zone
    is named because the ledger and the logs are UTC, and a bare "6:06" would be an hour of
    guessing away from the record it points at.
    """
    return when(row.get("ts", "?"))


def _parse_ts(row: dict) -> Optional[datetime]:
    try:
        return datetime.fromisoformat(str(row.get("ts")))
    except (TypeError, ValueError):
        return None


# ── the checks ───────────────────────────────────────────────────────────────
def review_bot(bot_key: str, instance_dir: Path, state: dict,
               now: Optional[datetime] = None) -> List[Finding]:
    """Everything in this bot's record that a person should look at.

    `state` is the bot's `bot_state.json` entry — used ONLY to know whether the bot is supposed
    to be running, so that a stopped bot does not report a missing record as a fault.
    """
    now = now or datetime.now(timezone.utc)
    findings: List[Finding] = []
    supposed_to_run = str(state.get("status", "")).lower() not in ("", "stopped", "offline")

    rows, problem = health_rows(instance_dir, now)
    if problem:
        # 🔴 Only a fault if the bot is meant to be running. A deliberately stopped bot has no
        # record to write, and alerting on that would make the channel cry wolf every time you
        # stop a bot on purpose — which is how a real alert gets ignored.
        if supposed_to_run:
            findings.append(Finding(
                f"unreadable:{now:%Y-%m-%d}", ALERT,
                "No readable health record",
                f"{bot_key} is marked `{state.get('status')}` but its record cannot be read: "
                f"{problem}. Either it is not writing, or something is wrong with the disk."))
        return findings

    pulses = [r for r in rows if r.get("kind") == "pulse"]
    events = [r for r in rows if r.get("kind") == "event"]

    def _of(name: str) -> List[dict]:
        return [r for r in events if r.get("event") == name]

    # ── the bridge stopped placing orders, and nothing else can see this ─────
    for row in _of("halted"):
        findings.append(Finding(
            f"halted:{_ts(row)}", ALERT,
            "Bridge HALTED — the bot is placing nothing",
            f"It stopped placing orders at {_at(row)}: {row.get('reason', 'no reason recorded')}.\n"
            f"It is still running and still looks healthy everywhere else — the watchdog and "
            f"the Bots page both read RUNNING. Check the account."))

    if pulses and str(pulses[-1].get("bridge_state", "")).lower() == "halted":
        # 🔴 The key is the timestamp of the HALT, never of the pulse that reports it.
        #
        # It was `_ts(pulses[-1])` until 2026-08-07, and a pulse is written every 15 minutes —
        # so this finding minted a brand-new dedup key on every hourly run and re-alerted for
        # as long as the bot stayed halted. Aaron got one Telegram message an hour, all night,
        # about a single incident. **That is precisely the de-duplicating-alerter bug this
        # module's own docstring warns about, committed in the module that warns about it**:
        # the key has to name the OCCURRENCE, and the occurrence here is the halt.
        #
        # ⚠ It deliberately does NOT fall back to the pulse timestamp when no halt event is on
        # today's file. A halt from yesterday whose event has rotated out is still ONE halt, and
        # the whole point of the standing `review.json` chip is that it is still there tomorrow
        # without needing to shout again. `unknown` is stable, which is the property that
        # matters — a NEW halt writes a new `halted` event and gets its own key.
        halts = _of("halted")
        occurrence = _ts(halts[-1]) if halts else "unknown"
        findings.append(Finding(
            f"halted_now:{occurrence}", ALERT,
            "Bridge is HALTED right now",
            f"Its latest heartbeat, at {_at(pulses[-1])}, says the order bridge is halted, so it is "
            f"placing nothing.\n"
            f"It will not resume until it is restarted and agrees with the broker again."))

    # ── refused to start at all ──────────────────────────────────────────────
    for row in _of("startup_failed"):
        findings.append(Finding(f"startup_failed:{_ts(row)}", ALERT,
                                "It failed to start",
                                f"At {_at(row)}: {row.get('error', '?')}"))
    for row in _of("version_mismatch"):
        findings.append(Finding(f"version_mismatch:{_ts(row)}", ALERT,
                                "It refused to start — the code is not the promoted version",
                                f"At {_at(row)}: {row.get('detail', '?')}"))

    # ── died without saying so ───────────────────────────────────────────────
    for row in _of("startup"):
        if row.get("previous_run_clean") is False:
            findings.append(Finding(
                f"unclean:{_ts(row)}", WARN,
                "Previous run ended without shutting down",
                f"The run before {_at(row)} was killed, crashed, or the box went down — it wrote no "
                f"shutdown record.\n"
                f"Expected if you restarted it yourself."))

    starts = _of("startup")
    if len(starts) >= RESTART_LOOP:
        findings.append(Finding(
            f"restart_loop:{_ts(starts[-1])}", ALERT,
            f"Restarted {len(starts)} times",
            f"{len(starts)} starts since {_at(starts[0])}.\n"
            f"Either something is killing it, or it is failing and being brought back. "
            f"Expected if you deployed today."))

    # ── it stopped seeing the market ─────────────────────────────────────────
    outages = _of("mt5_link_lost")
    if outages:
        back = _of("mt5_link_restored")
        total = sum(int(r.get("down_seconds") or 0) for r in back)
        findings.append(Finding(
            f"mt5_outage:{_ts(outages[-1])}", WARN,
            f"Lost the MT5 link {len(outages)} time(s)",
            f"Last at {_at(outages[-1])}, {len(back)} recovered, {total // 60} minutes blind in "
            f"total.\n"
            f"While blind it sees no bars at all. If it keeps happening, check MetaTrader on "
            f"the VPS."))

    # ── the bar stream had holes ─────────────────────────────────────────────
    bar_errors = _of("bar_error")
    if bar_errors:
        findings.append(Finding(
            f"bar_error:{_ts(bar_errors[-1])}", WARN,
            f"{len(bar_errors)} bar(s) failed to process",
            f"Last at {_at(bar_errors[-1])}: {bar_errors[-1].get('error', '?')}\n"
            f"Each one is a hole in the bar stream. It re-warms rather than carrying on, so "
            f"nothing is silently skipped."))

    loop_errors = _of("loop_error")
    if loop_errors:
        findings.append(Finding(
            f"loop_error:{_ts(loop_errors[-1])}", WARN,
            f"{len(loop_errors)} loop error(s)",
            f"Last at {_at(loop_errors[-1])}: {loop_errors[-1].get('error', '?')}"))

    rewarms = _of("rewarm")
    if len(rewarms) >= REWARM_STORM:
        findings.append(Finding(
            f"rewarm_storm:{_ts(rewarms[-1])}", WARN,
            f"Re-warmed {len(rewarms)} times",
            f"Last at {_at(rewarms[-1])}.\n"
            f"Repeated re-warms mean the bar stream keeps breaking."))

    # ── a settings change did not take ──────────────────────────────────────
    for row in _of("config_change_refused"):
        findings.append(Finding(
            f"config_refused:{_ts(row)}", WARN,
            "A settings change was refused",
            f"At {_at(row)}: {row.get('changes', '?')}\n"
            f"It is still trading the OLD settings, so the Bots page may show what you asked "
            f"for rather than what it is using. Restart it to take them."))

    # ── it went quiet without stopping ──────────────────────────────────────
    findings.extend(_pulse_gaps(pulses))

    if supposed_to_run and pulses:
        last = _parse_ts(pulses[-1])
        if last and (now - last).total_seconds() > PULSE_GAP_ALERT:
            findings.append(Finding(
                f"silent:{_ts(pulses[-1])}", ALERT,
                "No heartbeat in the record",
                f"{bot_key} is marked `{state.get('status')}` but its last recorded heartbeat "
                f"was {_ts(pulses[-1])}, over "
                f"{int((now - last).total_seconds() // 60)} minutes ago."))

    return findings


def _pulse_gaps(pulses: List[dict]) -> List[Finding]:
    """Holes between heartbeats that have already closed.

    ⚠ **This is a HISTORICAL finding on purpose.** `monitor.py` alerts on a stall while it is
    happening and restarts the bot; by the time anyone reads the record that alert has been and
    gone. What nothing kept was the fact that it happened at all — a gap that opened at 3am and
    closed by 4am leaves no trace anywhere else, because `bot_state.json` is overwritten in place
    and only ever describes now.
    """
    out: List[Finding] = []
    for prev, cur in zip(pulses, pulses[1:]):
        a, b = _parse_ts(prev), _parse_ts(cur)
        if not a or not b:
            continue
        gap = (b - a).total_seconds()
        if gap > PULSE_GAP_ALERT:
            out.append(Finding(
                f"pulse_gap:{_ts(cur)}", WARN,
                f"Went quiet for {int(gap // 60)} minutes",
                f"No heartbeat between {_ts(prev)} and {_ts(cur)}. Either the process was down "
                f"in that window or it was not turning its loop."))
    return out


# ── remembering what has already been said ───────────────────────────────────
def load_state() -> dict:
    try:
        return json.loads(STATE_FILE.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        # ⚠ An unreadable state file must not SUPPRESS alerts. Starting from empty re-announces
        # findings that are still true, which is noisy exactly once; the other direction would
        # silently swallow a real halt.
        return {}


def save_state(state: dict) -> None:
    try:
        STATE_FILE.write_text(json.dumps(state, indent=2), encoding="utf-8")
    except OSError as e:
        print(f"  ! could not save review state ({e}) — findings may be re-announced")


def prune(seen: List[str], keep: int = 200) -> List[str]:
    """Bound the remembered keys. They carry timestamps, so old ones can never recur."""
    return seen[-keep:]


# ── reporting ────────────────────────────────────────────────────────────────
def write_flag(instance_dir: Path, bot_key: str, findings: List[Finding]) -> None:
    """The standing flag the Bots page renders. Always written, cleared when clean.

    ⚠ Its own file, NOT `bot_state.json`: the runner rewrites that every poll through a
    read-modify-write, so a review written into it would race the heartbeat.
    """
    path = instance_dir / "review.json"
    try:
        if not findings:
            if path.exists():
                path.unlink()
            return
        worst = ALERT if any(f.level == ALERT for f in findings) else WARN
        path.write_text(json.dumps({
            "bot": bot_key,
            "level": worst,
            "checked_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "findings": [f.as_dict() for f in findings],
        }, indent=2), encoding="utf-8")
    except OSError as e:
        print(f"  ! could not write the review flag for {bot_key} ({e})")


def health_chat() -> tuple[str, str, bool]:
    """(token, chat_id, is_dedicated). Falls back to the main group and says which it used.

    ⚠ The lookup goes through `notify.chat_for`, NOT a direct read of `credentials.json`. It read
    the file itself until 2026-08-05, which silently ignored `LWG_TELEGRAM_HEALTH_CHAT` — an env
    override this repo's own template documented and nothing honoured, so setting it routed every
    finding to the main group while the docs said otherwise. One resolver, one answer.
    """
    token, _group, _admin = telegram_credentials()
    chat, dedicated = chat_for(HEALTH)
    return token, chat, dedicated


def send(text: str, dry_run: bool = False) -> bool:
    token, chat, dedicated = health_chat()
    where = "health chat" if dedicated else "main group (set telegram_health_chat to split)"
    if dry_run:
        print(f"  [dry run] would send to the {where}:\n{text}\n")
        return True
    if not token or not chat:
        print("  ! no Telegram credentials — finding not sent")
        return False
    try:
        import requests
        r = requests.post(f"https://api.telegram.org/bot{token}/sendMessage",
                          data={"chat_id": chat, "text": text, "parse_mode": "Markdown"},
                          timeout=10)
        if r.status_code != 200:
            print(f"  ! Telegram refused ({r.status_code}): {r.text[:200]}")
            return False
        return True
    except Exception as e:
        print(f"  ! Telegram send failed ({e})")
        return False


def main(argv=None) -> int:
    # 🔴 A Windows console is cp1252 and cannot encode the arrows, dashes and icons these
    # findings are written with. Python does not degrade — it raises UnicodeEncodeError and
    # takes the whole run down, so a scheduled task that finds a HALTED bridge dies while
    # printing it and nobody is told. Measured on the VPS the first time this ran there.
    # `algos/live/runner._make_logger` carries the identical fix and the identical comment;
    # this is the second module to need it, so treat it as a rule for anything that prints
    # here. A character it cannot encode must cost a glyph, never the message.
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")
        except (AttributeError, ValueError):
            pass

    ap = argparse.ArgumentParser(description="Review the bots' own health record.")
    ap.add_argument("--dry-run", action="store_true", help="find and print, send nothing")
    ap.add_argument("--all", action="store_true",
                    help="report every finding, not just ones not yet announced")
    args = ap.parse_args(argv)

    now = datetime.now(timezone.utc)
    state = load_state()
    total_new = 0

    for bot_key, instance_dir in _bot_state.BOT_INSTANCES.items():
        name = _bot_state.BOT_NAMES.get(bot_key, bot_key)
        try:
            bs = _bot_state.read_bot(bot_key)
        except Exception as e:
            print(f"{bot_key}: could not read bot_state ({e})")
            bs = {}

        findings = review_bot(bot_key, Path(instance_dir), bs, now=now)
        write_flag(Path(instance_dir), bot_key, findings)

        seen = state.get(bot_key, [])
        fresh = findings if args.all else [f for f in findings if f.key not in seen]
        print(f"{bot_key}: {len(findings)} finding(s), {len(fresh)} new")

        for f in fresh:
            # The house shape (`shared/alert_format.py`): icon, LABEL, subject, then the facts,
            # then what to do. The old form put "needs review" on the header and the actual
            # finding on line two, so every message opened with the same four words and the
            # thing that differed was below the fold on a lock screen.
            icon = "🔴" if f.level == ALERT else "⚠️"
            if send(alert(icon, "REVIEW", name, f.title, f.detail), args.dry_run):
                total_new += 1
                if not args.dry_run:
                    seen.append(f.key)
        state[bot_key] = prune(seen)

    if not args.dry_run:
        save_state(state)
    # Silent when clean is about TELEGRAM, not about stdout — a scheduled task with no output
    # is one you cannot tell ran from one that did not.
    print(f"log_review {now:%Y-%m-%d %H:%M} — {total_new} new finding(s) reported")
    return 0


if __name__ == "__main__":
    sys.exit(main())
