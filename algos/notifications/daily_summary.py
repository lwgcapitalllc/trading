"""daily_summary.py — once a day, what the health rooms did NOT show you, built from the send log.

**Why it exists (2026-09-26).** The health policy (`shared/alert_policy.py`) now holds repeats,
quick recoveries and routine lifecycle messages, and the whole design rests on one promise: nothing
held becomes invisible. This is where that promise is kept. One message per health room per day, at
08:00 America/Chicago, sent by the every-minute watchdog (`monitor.py` calls `maybe_send`), built
ONLY from the send log (`shared/notify_log.py`) — never from a count kept anywhere else, so the
summary and the record cannot disagree.

It says, for the 24 hours to 08:00:

* what was HELD, by label and by bot;
* the longest time an account could not trade;
* how many times the watchdog restarted a bot (held or not);
* what was delivered LATE, and what the outbox GAVE UP on after 24 hours.

⚠ **Rule 1, three ways.** "Nothing held" is said only when the log was READ and holds no hold. A log
that could not be read says so rather than reporting zero; a window with no log file at all says
that nothing was written — which is not the same as nothing happening.

⚠ **The box's log only.** The Command Center writes its own lines on the laptop it runs on, so a
message it held (a second STOPPED) is never counted here.

⚠ **A trade or setup that arrived late is counted in its ACCOUNT's health room**, as a number only —
never its content, which belongs to the room it was meant for.
"""

from __future__ import annotations

import sys
from collections import Counter, defaultdict
from datetime import datetime, time, timedelta, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

_ALGOS = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_ALGOS / "shared"))

import notify_log  # noqa: E402
from alert_format import INFO, alert  # noqa: E402

TZ = ZoneInfo("America/Chicago")
SEND_AT = time(8, 0)
LABEL = "DAILY SUMMARY"
HEALTH = "health"


def window_for(local_day) -> tuple[datetime, datetime]:
    """The 24 hours ending at 08:00 Chicago on `local_day`, as UTC datetimes."""
    end = datetime.combine(local_day, SEND_AT, tzinfo=TZ)
    return (end - timedelta(days=1)).astimezone(timezone.utc), end.astimezone(timezone.utc)


def _who(row) -> str:
    return row.get("subject") or row.get("bot") or "the box"


def _span(seconds) -> str:
    minutes = int(seconds) // 60
    hours, minutes = divmod(minutes, 60)
    return f"{hours} h {minutes} min" if hours else f"{max(minutes, 1)} min"


def _grouped(rows) -> str:
    """`OFFLINE 5 (SOS Fade · LIVE 3, Extreme Leg · LIVE 2)` per label, biggest first."""
    by_label = defaultdict(Counter)
    for r in rows:
        by_label[r.get("label") or "(no label)"][_who(r)] += 1
    parts = []
    for label, who in sorted(by_label.items(), key=lambda kv: -sum(kv[1].values())):
        inner = ", ".join(f"{name} {n}" for name, n in who.most_common())
        parts.append(f"{label} {sum(who.values())} ({inner})")
    return "; ".join(parts)


def summarise(rows, problem, found: int, start: datetime, end: datetime) -> str:
    """The body for ONE room from its rows. Pure — no I/O — so every sentence can be tested."""
    period = (
        f"The 24 hours to {end.astimezone(TZ).strftime('%I:%M %p').lstrip('0')} "
        f"{end.astimezone(TZ).strftime('%Z')}, {end.astimezone(TZ):%b %d}."
    )
    if problem:
        return alert(
            INFO,
            LABEL,
            "Health room",
            period,
            f"The send log could not be read ({problem}), so this cannot say what was held, late "
            f"or lost. Check algos/logs/notify on the box.",
        )
    if not found:
        return alert(
            INFO,
            LABEL,
            "Health room",
            period,
            "There is no send log for this period — either nothing was sent at all, or nothing is "
            "writing it. Check algos/logs/notify on the box.",
        )
    rows = [r for r in rows if r.get("label") != LABEL]
    held = [r for r in rows if r.get("outcome") == notify_log.HELD]
    late = [r for r in rows if r.get("outcome") == notify_log.SENT and r.get("delayed")]
    gave_up = [r for r in rows if r.get("outcome") == notify_log.DROPPED and r.get("gave_up")]
    refused = [r for r in rows if r.get("outcome") == notify_log.DROPPED and not r.get("gave_up")]
    # An in-place edit (`edit_of`) is a bot finishing a restart somebody PRESSED in the Command
    # Center, never the watchdog's — counting it called Aaron's own deploys "auto-restarts".
    restarts = [
        r
        for r in rows
        if r.get("label") == "RESTARTED" and _who(r) != "Telegram bot" and not r.get("edit_of")
    ]
    chat_bot = [r for r in rows if r.get("label") == "RESTARTED" and _who(r) == "Telegram bot"]
    offs = [
        r
        for r in rows
        if r.get("duration_s") is not None
        and (r.get("label") == "TRADING OFF" or r.get("recovers") == "TRADING OFF")
    ]

    lines = [period]
    lines.append(f"Held {len(held)}: {_grouped(held)}." if held else "Nothing held.")
    if offs:
        worst = max(offs, key=lambda r: r.get("duration_s") or 0)
        acct = worst.get("account")
        lines.append(
            f"Longest trading-off: {_span(worst['duration_s'])}"
            f"{f' (account {acct})' if acct is not None else ''}."
        )
    if restarts:
        who = Counter(_who(r) for r in restarts)
        lines.append(
            f"Auto-restarts: {len(restarts)} ("
            + ", ".join(f"{n} {c}" for n, c in who.most_common())
            + ")."
        )
    if chat_bot:
        lines.append(f"The Telegram bot was restarted {len(chat_bot)} time(s).")
    trades = [r for r in late + gave_up if r.get("kind") != HEALTH]
    lines.append(
        f"Delivered late: {len(late)} · Given up after 24 h: {len(gave_up)}"
        + (f" (of them {len(trades)} trade or setup message(s))" if trades else "")
        + "."
    )
    if refused:
        lines.append(
            f"Refused by Telegram or no room to send to: {len(refused)} — {_grouped(refused)}."
        )
    return alert(INFO, LABEL, "Health room", *lines)


def _health_room_of(row, shared: str, rooms_by_account: dict) -> str:
    """A HEALTH row counts in the room it went to; a trade or setup row in its ACCOUNT's health room."""
    if row.get("kind") == HEALTH:
        return str(row.get("room") or "") or shared
    return rooms_by_account.get(row.get("account")) or shared


def build(now: datetime) -> dict:
    """`{room: text}` for every health room, for the window ending at today's 08:00 Chicago."""
    import notify

    start, end = window_for(now.astimezone(TZ).date())
    rows, problem, found = notify_log.read_window(start, end)
    shared, _dedicated = notify.chat_for(notify.HEALTH)
    rooms_by_account = {}
    try:
        import bot_state as _bot_state

        for key in _bot_state.BOT_INSTANCES:
            acct = _bot_state.read_account(key)
            if acct is not None:
                own = (notify.account_rooms(acct) or {}).get(notify.HEALTH, "")
                rooms_by_account[acct] = own or shared
    except Exception as e:  # noqa: BLE001 — the shared room still gets its summary
        print(f"daily summary: could not list the accounts' rooms ({e})")
    rooms = {shared, *rooms_by_account.values()} - {""}
    per_room = defaultdict(list)
    for r in rows:
        per_room[_health_room_of(r, shared, rooms_by_account)].append(r)
    return {room: summarise(per_room.get(room, []), problem, found, start, end) for room in rooms}


def due(state: dict, now: datetime) -> bool:
    local = now.astimezone(TZ)
    return local.time() >= SEND_AT and state.get("sent_for") != local.date().isoformat()


def maybe_send(state: dict, now: datetime | None = None) -> dict:
    """Send today's summaries once, on the first watchdog pass at or after 08:00 Chicago. NEVER raises.

    `state` is this job's slice of `monitor_state.json`; the day is recorded once every room has
    been ATTEMPTED — a room whose send failed transiently is in the outbox and will arrive late.
    """
    now = now or datetime.now(timezone.utc)
    try:
        if not due(state, now):
            return state
        import notify

        for room, text in build(now).items():
            notify.send_telegram_id(
                text, notify.HEALTH, chat_id=room, markdown=False, bot="daily_summary"
            )
        state["sent_for"] = now.astimezone(TZ).date().isoformat()
    except Exception as e:  # noqa: BLE001 — a summary may never stop the watchdog's pass
        print(f"daily summary failed: {e}")
    return state
