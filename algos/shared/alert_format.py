"""alert_format.py — the ONE shape every Telegram message this suite sends.

**Why it exists.** Each notifier had grown its own voice. The bot wrote seven-line trade slips
with blank lines between the sections; the watchdog wrote bold headlines with a bullet list under
them; the log reviewer wrote a title and a paragraph. Read together in one chat they looked like
five different systems, and — worse — each one buried the thing you would act on somewhere
different. Aaron's brief (2026-08-05): concise but never so concise you cannot diagnose it, facts
that belong together on one line, facts that do not on the next.

The shape:

    <icon> <LABEL> · <subject>
    <the facts, grouped>
    <what to do about it>

Rules that are worth more than the shape:

**The LABEL is the whole message in two words.** `HALTED`, `NO MT5 LINK`, `WILL NOT START`. It is
what you read on a lock screen, so it names the STATE rather than the event that produced it —
`WILL NOT START` rather than `CRITICAL`, because the first tells you what is true now.

**A health message ends with the consequence, and "nothing to do" counts.** The old messages
stated a fact and left the reader to work out whether it mattered. `RECONNECTED … Nothing to do`
is not padding: it is the difference between a glance and an investigation at 3am.

**No timestamp on a message about NOW.** Telegram already stamps every message in the reader's
own local time, right above it, and a bot cannot do better — it sends one string to a group and
has no idea where anyone is reading it. So a second clock is duplication. The exception is a
message about the PAST — the log reviewer at 21:20 reporting a restart at 18:06 — where the time
is the fact, and `when()` renders it in the box's local clock with the zone named.

**Plain text, no Markdown, ever.** Every message here carries a strategy name, a symbol or a
broker string, and those are full of underscores (`mpc_sos_fade`, `MT5_FFT`, `XAUUSD.s`). A lone
underscore opens an italic that never closes and Telegram rejects the WHOLE message — measured on
the first real send, 2026-07-31. `notify.send_telegram` retries unformatted, but an alert should
never need rescuing, and the alert most likely to trip it is the one carrying an exception.

⚠ **`command-center/backend/services/alert_format.py` is a deliberate MIRROR of this file.** The
two subsystems may share a data file and may not import each other's code. `SPEC` below is the
contract both sides render, and a test on each side reads the other file to pin them together.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Iterable, Optional

try:                                    # 3.9+ on the VPS; the fallback keeps the Mac tests honest
    from zoneinfo import ZoneInfo
except ImportError:                     # pragma: no cover
    ZoneInfo = None                     # type: ignore

__all__ = ["alert", "when", "LOCAL_TZ", "SPEC"]

#: The box's own clock, used ONLY for a message about something that happened earlier. Telegram
#: renders the send time in each reader's local zone already, so "now" never needs stamping.
LOCAL_TZ = "America/Chicago"

#: The contract, in one string, so both implementations and their tests quote the same thing.
SPEC = "<icon> <LABEL> · <subject>\\n<facts>\\n<what to do>"


def alert(icon: str, label: str, subject: str = "", *lines: str) -> str:
    """One message, in the house shape.

    `lines` are already-grouped: each one is a set of facts that belong together. Empty entries
    are dropped rather than rendering a blank line, so a caller may pass a value it might not
    have (`None` for an unknown balance) without branching at the call site — the alternative is
    every sender growing its own layout logic again, which is what this file exists to end.
    """
    head = f"{icon} {label}"
    if subject:
        head = f"{head} · {subject}"
    body = [str(x).strip() for x in lines if x is not None and str(x).strip()]
    return "\n".join([head, *body])


def when(ts, tz: str = LOCAL_TZ) -> str:
    """A PAST moment, in the box's local clock with the zone named.

    Only for a message about something that already happened. Naming the zone is not decoration:
    the ledger, the logs and the bar times are all UTC, so a bare "18:06" in a Telegram message
    would be one hour of guessing away from the record it refers to.

    Accepts a datetime or an ISO string, and never raises — a notifier that can be brought down by
    an unparseable timestamp is worse than one printing a stamp it could not read.
    """
    if isinstance(ts, str):
        try:
            ts = datetime.fromisoformat(ts.replace("Z", "+00:00"))
        except ValueError:
            return ts
    if not isinstance(ts, datetime):
        return str(ts)
    if ts.tzinfo is None:
        ts = ts.replace(tzinfo=timezone.utc)
    if ZoneInfo is not None:
        try:
            ts = ts.astimezone(ZoneInfo(tz))
        except Exception:
            ts = ts.astimezone(timezone.utc)
    else:                               # pragma: no cover
        ts = ts.astimezone(timezone.utc)
    # ⚠ NOT `%-I`. That is a glibc extension: it strips the leading zero on Linux and macOS and
    # raises `ValueError: Invalid format string` on Windows, where the equivalent is `%#I`. This
    # code runs on BOTH — the tests on a Mac, the scheduled tasks on the VPS — so it formats with
    # the portable `%I` and strips the zero itself. Found by running `log_review.py` on the box
    # after a green suite on the Mac, which is the second time in two days that a Windows-only
    # crash reached a scheduled task through a passing test run.
    stamp = ts.strftime("%I:%M %p").lstrip("0")
    return f"{stamp} {ts.strftime('%Z')}"


def money(value: Optional[float], currency: str = "$") -> str:
    """`$2,000.00`, or an honest dash. `None` means NOT KNOWN — a blind terminal returns no
    balance — and printing `$0.00` for it would report a measurement nobody made. The repo's
    standing rule: never let "no" and "cannot ask" be the same value."""
    if value is None:
        return "unknown"
    return f"{currency}{value:,.2f}"


def joined(parts: Iterable[Optional[str]], sep: str = " · ") -> str:
    """Facts that belong on one line, with the ones that are missing simply absent."""
    return sep.join([str(p) for p in parts if p is not None and str(p).strip()])
