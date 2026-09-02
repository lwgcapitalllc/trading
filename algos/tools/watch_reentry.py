#!/usr/bin/env python3
"""Watch for the first live re-entry, audit it, and say so on Telegram. Runs on the trading box.

**Why this exists.** The re-entry went live on 2026-09-02 having never placed a real order, and
Aaron's instruction was that the checking is not his job: *"whenever it happens and whenever it
closes, you execute that script."* `audit_reentry.py` is the grading; this is the thing that
notices. It replaced an hourly job that lived inside one Claude session — which is to say, a watch
that died when a window closed and would have gone on reading as armed.

🔴 **IT REPORTS TWICE PER TRADE, DELIBERATELY: on the OPEN and on the CLOSE.** Half the checks
(the exit reason, R against the prices, the costs, whether anything was banked) cannot be answered
while the position is still on. Reporting once at the open and calling it audited would file a
verdict on the half of the trade that had happened.

🔴 **THE THREE THINGS THIS SENDS, AND THE THIRD IS THE ONE THAT KEEPS IT HONEST:**
  1. a re-entry opened, with the checks that can already be answered;
  2. it closed, with the full grading;
  3. **the watch could not RUN** — a crash, an unreadable config, a ledger it cannot parse.
Without (3) a broken watcher and a quiet market are the same silence, and this repo has paid for
that shape more than once. A watch that cannot run must never read as a watch that found nothing.

⚠ **Silence is the normal state and that is a hazard, not a comfort.** Most days there is no
re-entry, so a person sees nothing for weeks and has no way to tell a working watcher from a dead
one. Every run therefore writes a `reentry_watch` record to the bot's HEALTH ledger — so a GAP in
that file is the evidence, exactly as the ledger's own `pulse` is. Nothing is sent to Telegram for
a quiet run: a message nobody needs, every hour, is how a channel gets muted before the day it
matters.

⚠ **It reports each trade ONCE per half**, keyed by ticket in a small state file beside the bot's
ledger. Re-sending on every run is the same muting problem with extra steps.

⚠ **The GRADING is not implemented here.** It imports `audit_reentry`, so the rules live in one
place; this file decides only *is there something new* and *who is told*.

Usage (the box's scheduled task runs the first form):
    python3 algos/tools/watch_reentry.py --bot mpc_sos_fade_demo
    python3 algos/tools/watch_reentry.py --bot mpc_sos_fade_demo --dry-run   # print, send nothing

Exit codes: 0 ran (whether or not it found anything), 1 the watch itself could not run.
⚠ **Exit 0 does NOT mean the trade passed** — it means the watcher worked. The verdict is in the
message and in the health record, never in the exit code.
"""

from __future__ import annotations

import argparse
import json
import sys
import traceback
from datetime import datetime, timezone
from pathlib import Path

_HERE = Path(__file__).resolve().parent
_REPO = _HERE.parents[1]
for _p in (_HERE, _REPO / "algos" / "live", _REPO / "algos" / "shared"):
    if str(_p) not in sys.path:
        sys.path.insert(0, str(_p))

import audit_reentry as audit  # noqa: E402

STATE_NAME = "reentry_watch.json"


def _instance_dir(bot: str) -> Path:
    return _REPO / "algos" / "markets" / "fx" / "instances" / bot


def _load_state(path: Path) -> dict:
    """What has already been reported. A missing or corrupt file means NOTHING has been.

    ⚠ **Corrupt reads as empty on purpose, and the cost is a repeat rather than a miss.** The two
    failure directions are not equal: re-sending one message is an annoyance, and silently
    treating an unreadable file as *everything already reported* would swallow the one message
    this whole tool exists to send.
    """
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}


def _save_state(path: Path, state: dict) -> None:
    try:
        path.write_text(json.dumps(state, indent=2), encoding="utf-8")
    except OSError as exc:
        # Not fatal: the message has already gone out. Losing the state means one repeat next
        # hour, which is the harmless direction — see `_load_state`.
        print(f"  ⚠ could not write {path}: {exc}", file=sys.stderr)


def _summarise(rep: audit.Report, when: str) -> str:
    """One Telegram message for one trade. Plain words — a person reads this on a phone."""
    fails = [f"❌ {rule} — {detail}" for _v, rule, detail in rep.rows if _v == audit.FAIL]
    unknown = [rule for _v, rule, _d in rep.rows if _v == audit.UNKNOWN]
    passed = len(rep.rows) - len(fails) - len(unknown)

    head = "🔴 RE-ENTRY — SOMETHING IS WRONG" if fails else "🟢 RE-ENTRY CHECKED"
    lines = [f"*{head}*", f"Trade {rep.ticket}, {when}.", ""]
    if fails:
        lines += fails + [""]
    lines.append(
        f"{passed} checks passed, {len(fails)} failed, {len(unknown)} could not be checked."
    )
    if unknown:
        # ⚠ NAMED, not counted. "2 could not be checked" tells a reader nothing about whether the
        # unchecked half is the half that matters.
        lines.append("Not checked: " + "; ".join(unknown))
    if fails:
        lines.append("")
        lines.append("This is the first live re-entry work — read it before the next one arms.")
    return "\n".join(lines)


def _send(text: str, dry_run: bool) -> None:
    if dry_run:
        print("\n--- would send ---\n" + text + "\n------------------")
        return
    from notify import HEALTH, send_telegram

    send_telegram(text, HEALTH)


def _health(bot: str, **fields) -> None:
    """A record every run, so a GAP in the file is the evidence that this stopped.

    ⚠ It is written to the HEALTH stream rather than the decision one: this is an observation
    about the machinery that watches, never a decision the bot made. Same subject test the ledger
    applies everywhere else.
    """
    try:
        from ledger import Ledger

        Ledger(_instance_dir(bot) / "ledger", bot).event("reentry_watch", **fields)
    except Exception as exc:
        print(f"  ⚠ could not write the health record: {exc}", file=sys.stderr)


def run(bot: str, dry_run: bool = False) -> int:
    state_path = _instance_dir(bot) / STATE_NAME
    state = _load_state(state_path)
    reported = state.setdefault("reported", {})

    rows = audit.load_ledger(bot, None)
    params = audit.load_config(bot, None).get("strategy_params", {})
    trades = [r for r in rows if r.get("kind") == "trade"]
    opens = {t["ticket"]: t for t in trades if t.get("event") == "opened"}
    closes = {t["ticket"]: t for t in trades if t.get("event") == "closed"}

    secondaries = {k: v for k, v in opens.items() if v.get("intent") == "secondary"}
    sent = 0
    for ticket, op in sorted(secondaries.items(), key=lambda kv: kv[1].get("ts", "")):
        closed = closes.get(ticket)
        # The two halves are reported separately — see the module docstring.
        half = "closed" if closed else "open"
        if reported.get(str(ticket)) == "closed" or reported.get(str(ticket)) == half:
            continue
        events = [r for r in rows if r.get("ticket") == ticket and r.get("kind") != "trade"]
        rep = audit.audit_trade(op, closed, events, params)
        _send(_summarise(rep, "now closed" if closed else "still open"), dry_run)
        sent += 1
        if not dry_run:
            reported[str(ticket)] = half

    if not dry_run:
        state["last_run"] = datetime.now(timezone.utc).isoformat(timespec="seconds")
        _save_state(state_path, state)

    _health(
        bot,
        re_entries_seen=len(secondaries),
        messages_sent=sent,
        # ⚠ RECORDED because a watcher that finds nothing and a watcher pointed at an empty
        # directory look identical from the outside. This says the file was actually read.
        ledger_rows=len(rows),
    )
    print(f"{len(secondaries)} re-entry trade(s) on record, {sent} message(s) sent.")
    return 0


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--bot", required=True)
    ap.add_argument("--dry-run", action="store_true", help="print the messages, send nothing")
    args = ap.parse_args(argv)

    try:
        return run(args.bot, args.dry_run)
    except Exception as exc:
        # 🔴 THE THIRD MESSAGE, AND THE REASON THIS BLOCK IS BROAD ON PURPOSE. Any failure here
        # leaves the watch not watching, and the visible symptom is silence — which is also what
        # a quiet market looks like. So it SAYS SO, once, rather than dying into a log nobody
        # opens. It is deliberately the last thing that can go wrong: everything above it already
        # degrades gracefully.
        detail = f"{type(exc).__name__}: {exc}"
        print(detail, file=sys.stderr)
        traceback.print_exc(file=sys.stderr)
        try:
            _send(
                "*⚠️ RE-ENTRY WATCH IS NOT RUNNING*\n"
                f"The hourly check on {args.bot} failed: {detail}\n\n"
                "Nothing is watching for the first re-entry until this is fixed. "
                "Silence from here does NOT mean nothing happened.",
                args.dry_run,
            )
        except Exception:
            pass  # a broken notifier must not hide the exit code below
        _health(args.bot, error=detail)
        return 1


if __name__ == "__main__":
    sys.exit(main())
