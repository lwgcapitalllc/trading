"""The New York entry window — ONE definition of "no new entries between these two times".

Aaron, 2026-09-23, picking from the next-step list: refuse New York entries 11:30-15:30.

🔴 BOTH ENTRY PATHS ASK THIS MODULE, AND THAT IS THE REASON IT IS A MODULE. The first entry arms
on the 15m clock and the re-entry on the fast clock. Two copies of "is this inside the window"
would drift the first time either was touched, and a window that refuses first entries while
re-entries still fill inside it is a rule that does half of what its label says.

🔴 THE TIME THAT IS TESTED IS WHEN THE ORDER WOULD BE LIVE, NOT WHEN IT WAS DECIDED. An order is
placed at a bar's CLOSE and can only fill from the next bar on, so a caller passes the close time
of the bar it is deciding on. Testing the bar's OPEN instead would let an order decided on the
bar opening 11:15 rest on — and fill during — the 11:30 bar, which is inside the window.

⚠ A window may wrap midnight (22:00 -> 02:00). New York is how a trader states a session, and
Asia genuinely straddles the day, so it is handled rather than refused — the same rule the
short-hold variant's hour window already follows.

⚠ OFF is both times empty. A half-set window is refused by the config rather than read as the
half that is set.
"""

from __future__ import annotations

import re
from datetime import datetime, timezone
from typing import Optional
from zoneinfo import ZoneInfo

_NY = ZoneInfo("America/New_York")
_HHMM = re.compile(r"^([01]\d|2[0-3]):([0-5]\d)$")


def parse_hhmm(text: str) -> Optional[int]:
    """'11:30' -> 690 minutes past midnight. '' -> None (off). Anything else raises."""
    if text == "":
        return None
    m = _HHMM.match(text)
    if not m:
        raise ValueError(f"{text!r} is not a 24-hour HH:MM time")
    return int(m.group(1)) * 60 + int(m.group(2))


def in_window(from_text: str, to_text: str, live_ms: int) -> bool:
    """Is the New York clock at `live_ms` inside the half-open window [from, to)?"""
    lo, hi = parse_hhmm(from_text), parse_hhmm(to_text)
    if lo is None or hi is None:
        return False
    ny = datetime.fromtimestamp(live_ms / 1000.0, tz=timezone.utc).astimezone(_NY)
    now = ny.hour * 60 + ny.minute
    return (lo <= now < hi) if lo < hi else (now >= lo or now < hi)
