#!/usr/bin/env python3
"""Notice when the broker re-quotes its overnight financing. Runs on the trading box.

**Why this exists.** The lab hardcodes this symbol's overnight swap and the broker moves it
whenever it likes. It has been caught drifting FOUR times in seven weeks — -78.29 (2026-07-16),
-79.60 (2026-08-06), -81.18 (2026-08-14), -80.54 (2026-09-02) — and **every one was found by a
person who happened to look.** On a strategy designed to hold overnight it is the largest
re-priceable cost. Aaron's call, 2026-09-03: the noticing is not a person's job.

🔴 **IT FIRES ON THE EVENT, NOT ON A THRESHOLD, AND THAT IS THE WHOLE DESIGN.** A threshold would
be a guessed number (rule 4) and this repo has no measurement that says which drift matters — the
one drift that HAS been replayed came to +0.09R, which argues for a big threshold, and one
measurement is not a rule. So this reports when the broker's number CHANGES from the last reading
on record, which is an event that either happened or did not. Silence therefore means *the broker
has not moved it*, never *we decided it was small enough*.

⚠ **The message carries the gap to the LAB's constant, which is a different question** and the one
a reader actually acts on: the broker moving from -80.54 to -80.60 matters far less than the lab
still charging -79.60. Both numbers are in every message; neither is editorialised into a verdict.

⚠ **Silence is the normal state and that is a hazard, not a comfort** — the same shape as the
dead-man's switch and the re-entry watch. So EVERY run writes a health record carrying the reading
itself, whether or not anything moved. A gap in that file is the evidence this stopped, and the
record is also the only place the SERIES of readings lives: they were previously scattered across
`backtest/fills.py` comments, the bot's instance config, and chat logs, and a doc paragraph
restating that series from two of the three got a value wrong.

⚠ **It reads through `broker_facts.py` rather than calling MT5 itself.** That module already
refuses to report the wrong terminal's numbers, and this box runs two — MT5_FFT (PU Prime, the
live bot) and MT5_Lab (Vantage). Reporting Vantage's swap as PU Prime's is precisely the error
being guarded against, and it would look completely ordinary.

⚠ **It writes NOTHING to `backtest/fills.py`.** Re-pricing re-bases every charged figure in the
repo and is a deliberate act with its own commit; a tool that silently updated the constant would
make a fresh reading indistinguishable from a stale one, which is the same reason `broker_facts.py`
does not write the instance config.

Usage (the box's scheduled task runs the first form):
    python3 algos/tools/watch_broker_costs.py --bot sos_fade_demo
    python3 algos/tools/watch_broker_costs.py --bot sos_fade_demo --dry-run

Exit codes: 0 ran (whether or not anything moved), 1 the watch itself could not run.
⚠ **Exit 0 does NOT mean the costs are current** — it means the watcher worked. The verdict is in
the message and the health record, never in the exit code.
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
for _p in (_HERE, _REPO, _REPO / "algos" / "live", _REPO / "algos" / "shared"):
    if str(_p) not in sys.path:
        sys.path.insert(0, str(_p))

STATE_NAME = "broker_costs_watch.json"

#: What the lab holds for a tier nobody has read. Distinct from a number, and it must stay
#: distinct: "we refuse to charge this" and "we charge 0.00" are different claims (rule 1).
UNMEASURED = "unmeasured"


def _instance_dir(bot: str) -> Path:
    return _REPO / "algos" / "markets" / "fx" / "instances" / bot


def lab_swap(profile_key: str) -> dict:
    """What `backtest/fills.py` would charge for this account tier, per lot per night.

    Returns `{"long": float|UNMEASURED, "short": float|UNMEASURED}`. The sentinel is carried
    through rather than converted to a number or to None — a tier whose swap the lab REFUSES to
    charge is a real state, and reporting it as 0.00 would invent agreement with any broker
    reading that happened to be near zero.
    """
    from backtest.fills import PROFILES

    prof = PROFILES.get(profile_key)
    if prof is None:
        raise SystemExit(
            f"account_profile {profile_key!r} is not a key of backtest.fills.PROFILES — the bot's "
            f"config names a tier the lab has never heard of, so there is nothing to compare "
            f"against. Known: {sorted(PROFILES)}"
        )
    swap = getattr(prof, "swap", None)
    if swap is None:
        # A deliberate "charge no swap" profile. Also a real state, and not a drift question.
        return {"long": None, "short": None}
    out = {}
    for side, attr in (("long", "swap_long_points"), ("short", "swap_short_points")):
        val = getattr(swap, attr)
        out[side] = UNMEASURED if not _is_measured(val) else float(val)
    return out


def _is_measured(val) -> bool:
    """Is this a reading, or the sentinel meaning nobody has read it?

    ⚠ Asked of the VALUE rather than by importing the sentinel's name, so a rename in `fills.py`
    cannot make an unmeasured tier quietly read as a measurement. The sentinel is deliberately a
    value no real swap can take.
    """
    from backtest.fills import SENTINEL

    try:
        return float(val) != float(SENTINEL)
    except (TypeError, ValueError):
        return False


def profile_key_for(cfg: dict):
    """Which `backtest.fills.PROFILES` tier this bot's account is priced by, or None.

    🔴 **It lives under `strategy_params`, NOT at the top level, and this is a FUNCTION so a test
    can exercise the real lookup.** MEASURED by running the watcher against the live bot's own
    config: it refused, saying no tier was named, while that config plainly names one. An inline
    `cfg.get("account_profile")` had read the wrong level.

    ⚠ The top-level read is kept as a fallback rather than replaced — it costs nothing, and a
    config is free to state it either way.
    """
    return (cfg.get("strategy_params") or {}).get("account_profile") or cfg.get("account_profile")


def read_live(cfg: dict) -> dict:
    """The terminal's CURRENT swap for this bot's symbol. The only part that needs MT5.

    Delegates the attach and the account assertion to `broker_facts` — this box runs two
    terminals and reporting one broker's costs as another's is the error that module exists to
    refuse. Read-only: it attaches to a running terminal, reads the specification, detaches.
    """
    import broker_facts
    import MetaTrader5 as mt5  # noqa: N813 — the vendor's own import name

    broker_facts.attach(mt5, cfg["mt5_path"], int(cfg["account"]))
    try:
        s = broker_facts.spec(mt5, cfg["symbol"])
    finally:
        mt5.shutdown()
    return {
        "long": float(s["swap_long"]),
        "short": float(s["swap_short"]),
        "symbol": s["symbol"],
        "swap_mode": s["swap_mode"],
        "rollover_3days": s["swap_rollover_3days"],
    }


def assess(reading: dict, previous: dict | None, lab: dict) -> dict:
    """Did the BROKER move, and how far is the LAB from where the broker is now?

    Two independent questions and the return keeps them apart:
      * `moved`      — the broker re-quoted since the last reading on record. The trigger.
      * `lab_gap`    — how stale `backtest/fills.py` is. The thing a reader acts on.

    ⚠ `previous is None` (a first run, or a lost state file) is NOT "nothing moved". It is
    reported once, because a watcher whose first act is silence is indistinguishable from one
    that never ran — and because the first reading is the only one that establishes the series.
    """
    moved = {}
    if previous is not None:
        for side in ("long", "short"):
            was, now = previous.get(side), reading[side]
            if was is not None and float(was) != float(now):
                moved[side] = {"was": float(was), "now": float(now), "by": float(now) - float(was)}

    lab_gap = {}
    for side in ("long", "short"):
        held = lab.get(side)
        if held is None or held == UNMEASURED:
            # Nothing to be adrift FROM. Carried explicitly so the message can say which.
            lab_gap[side] = {"held": held, "pct": None}
            continue
        now = float(reading[side])
        pct = None if now == 0 else abs(now - held) / abs(now) * 100.0
        lab_gap[side] = {"held": held, "now": now, "diff": now - held, "pct": pct}

    return {
        "moved": moved,
        "first_reading": previous is None,
        "lab_gap": lab_gap,
        "reading": reading,
    }


def _fmt_pct(pct) -> str:
    return "—" if pct is None else f"{pct:.1f}%"


def summarise(verdict: dict, bot: str, profile_key: str) -> str:
    """One Telegram message. Plain words — somebody reads this on a phone.

    ⚠ Both numbers appear on every side, always, and neither is turned into a verdict. What a
    drift is WORTH depends on how long the strategy holds and how big the bill is, and this tool
    has measured neither.
    """
    r = verdict["reading"]
    if verdict["first_reading"]:
        head = "🔵 OVERNIGHT COST WATCH — FIRST READING"
        why = "This is the first reading on record, so there is nothing to compare it against yet."
    else:
        head = "🟠 THE BROKER MOVED ITS OVERNIGHT COST"
        parts = [
            f"{side}: {m['was']:+.2f} → {m['now']:+.2f} ({m['by']:+.2f})"
            for side, m in verdict["moved"].items()
        ]
        why = "Changed since the last reading — " + "; ".join(parts) + "."

    lines = [f"*{head}*", f"{bot}, {r['symbol']}, per lot per night.", "", why, ""]
    lines.append(f"Broker now: long {r['long']:+.2f}, short {r['short']:+.2f}")

    gaps = []
    for side in ("long", "short"):
        g = verdict["lab_gap"][side]
        held = g["held"]
        if held is None:
            gaps.append(f"{side}: the lab charges no overnight cost on this tier")
        elif held == UNMEASURED:
            gaps.append(f"{side}: the lab refuses to charge this tier — nobody has read it")
        else:
            gaps.append(f"{side}: lab holds {held:+.2f}, {_fmt_pct(g['pct'])} away")
    lines.append(f"Backtests ({profile_key}) — " + "; ".join(gaps))
    lines += [
        "",
        "Nothing has been changed. Updating the lab's number re-prices every charged figure in "
        "the repo, so it is a deliberate job with its own commit.",
    ]
    return "\n".join(lines)


def _load_state(path: Path) -> dict:
    """What was last read. Corrupt or missing reads as EMPTY, and that is the safe direction.

    An unreadable file then means "no previous reading", which sends one extra message. Treating
    it as "already up to date" would swallow the one message this tool exists to send.
    """
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}


def _save_state(path: Path, state: dict) -> None:
    try:
        path.write_text(json.dumps(state, indent=2), encoding="utf-8")
    except OSError as exc:
        # Not fatal — the message has gone. Losing this costs one repeat, the harmless direction.
        print(f"  warning: could not write {path}: {exc}", file=sys.stderr)


def _send(text: str, dry_run: bool) -> None:
    if dry_run:
        print("\n--- would send ---\n" + text + "\n------------------")
        return
    from notify import HEALTH, send_telegram

    send_telegram(text, HEALTH)


def _health(bot: str, **fields) -> None:
    """A record on EVERY run, so a gap in the file is the evidence this stopped.

    ⚠ It carries the READING, not just a verdict. These numbers previously lived in three
    different places and no two agreed on the series; this is the one place that accumulates it.
    ⚠ HEALTH stream, not the decision one — an observation about the machinery, never a decision
    the bot made.
    """
    try:
        from ledger import Ledger

        Ledger(_instance_dir(bot) / "ledger", bot).event("broker_costs_watch", **fields)
    except Exception as exc:
        print(f"  warning: could not write the health record: {exc}", file=sys.stderr)


def console_line(reading: dict, verdict: dict) -> str:
    """The line a person reads in the TASK LOG — a different output from the Telegram message.

    \U0001f534 It has to keep apart the same three states `assess` does, and it did not. It said
    "nothing moved since the last reading" on a FIRST reading for its whole life: an assertion
    about a previous reading that does not exist, printed in the one place somebody scrolling a
    scheduled task's log actually looks. The Telegram half was correct throughout, which is
    exactly why nothing caught it — the tests all read the message.

    \u26a0 Found by RUNNING it against the live terminal (2026-09-03), not by reading it. That is
    the second defect in this file found that way and the third overall; treat "it reads
    correctly" as unproven here.
    """
    if verdict["first_reading"]:
        tail = "first reading on record, nothing to compare against"
    else:
        tail = f"{', '.join(verdict['moved']) or 'nothing'} moved since the last reading"
    return (
        f"{reading['symbol']}: long {reading['long']:+.2f} short {reading['short']:+.2f} ({tail})"
    )


def run(bot: str, dry_run: bool = False) -> int:
    import broker_facts

    cfg = broker_facts.load_instance(bot)
    profile_key = profile_key_for(cfg)
    if not profile_key:
        raise SystemExit(
            f"{bot}'s config names no account_profile, so there is no lab tier to compare the "
            f"broker's reading against. Refusing rather than guessing one."
        )

    reading = read_live(cfg)
    lab = lab_swap(profile_key)
    state_path = _instance_dir(bot) / STATE_NAME
    state = _load_state(state_path)
    previous = state.get("last_reading")

    verdict = assess(reading, previous, lab)
    speak = verdict["first_reading"] or bool(verdict["moved"])
    if speak:
        _send(summarise(verdict, bot, profile_key), dry_run)

    if not dry_run:
        state["last_reading"] = {"long": reading["long"], "short": reading["short"]}
        state["last_run"] = datetime.now(timezone.utc).isoformat(timespec="seconds")
        _save_state(state_path, state)

    _health(
        bot,
        symbol=reading["symbol"],
        swap_long=reading["long"],
        swap_short=reading["short"],
        lab_profile=profile_key,
        lab_long=lab["long"],
        lab_short=lab["short"],
        broker_moved=bool(verdict["moved"]),
        message_sent=bool(speak),
    )
    print(console_line(reading, verdict))
    return 0


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--bot", required=True)
    ap.add_argument("--dry-run", action="store_true", help="print the message, send nothing")
    args = ap.parse_args(argv)

    try:
        return run(args.bot, args.dry_run)
    except (Exception, SystemExit) as exc:
        # 🔴 BROAD ON PURPOSE, and it is the third thing this tool reports. Any failure here
        # leaves the watch not watching, and the visible symptom is silence — which is also what
        # "the broker has not moved it" looks like. So it says so, once, rather than dying into a
        # log nobody opens.
        #
        # 🔴 `SystemExit` IS NAMED BECAUSE IT IS NOT AN `Exception`, AND WITHOUT IT THIS ALARM
        # COULD NOT FIRE ON THE MOST LIKELY FAILURE. `broker_facts.attach()` raises `SystemExit`
        # for every reason the terminal cannot be read — not running, not logged in, logged into
        # the WRONG ACCOUNT — and a bare `except Exception` lets all three straight past. MEASURED
        # by running it: the message reached stderr and no alert was sent. ⚠ `KeyboardInterrupt`
        # is deliberately still excluded; a person stopping this by hand needs no Telegram alert.
        detail = f"{type(exc).__name__}: {exc}"
        print(detail, file=sys.stderr)
        traceback.print_exc(file=sys.stderr)
        try:
            _send(
                "*⚠️ OVERNIGHT COST WATCH IS NOT RUNNING*\n"
                f"The check on {args.bot} failed: {detail}\n\n"
                "Until this is fixed, a change in the broker's overnight cost will pass "
                "unnoticed — silence from this watch no longer means the rate held.",
                args.dry_run,
            )
        except Exception:  # noqa: BLE001 — a failed alarm must not mask the failure it reports
            pass
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
