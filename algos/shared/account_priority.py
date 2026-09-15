"""account_priority.py — which bot on an account sizes FIRST when two close a bar together.

Aaron, 2026-09-15: bots on one account share one risk budget, and when two signal at the same
moment the one higher in the account's priority order takes its full share first; the other sizes
into whatever is left (or is refused below half its share, `backtest/portfolio/account.py`).

**The mechanism is TIME, and that is deliberate.** A lower bot simply waits long enough for every
higher bot to have put its order at the broker. The budget is read off the BROKER
(`bridge.refresh_account_room`), where a resting or filled order already counts, so by the time the
lower bot reads it the higher bot's risk is in it. Every alternative needs the bots to trust each
other — a shared file, a lock, a message — and each has the failure `account_risk.py` records: a
bot that crashed or was never told leaves a stale reservation or none. Waiting leaves nothing
behind.

**Timed from the bar's CLOSE, never from when this bot noticed it.** Each bot polls on its own
clock, so two bots notice the same close up to one poll apart; a wait measured from noticing would
not order them at all.

⚠ **Only bars that COINCIDE wait.** An M5 bot below an M15 bot waits on the M5 closes that are
also M15 closes, and on no other — waiting every bar would cost a market bot slippage for nothing.

⚠ **Cannot tell = wait as if every higher rank is there.** An unreadable registry or a peer config
that will not read is never "nobody ahead" (rule 1); it costs a few seconds, the other answer costs
the cap.

Pure standard library apart from the registry read, which is injected-root for tests.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path
from typing import List, Optional

try:  # pragma: no cover - import shim
    from bot_registry import RegistryUnreadable, discover, read_config
except ImportError:  # pragma: no cover
    from .bot_registry import RegistryUnreadable, discover, read_config  # type: ignore

__all__ = [
    "Peer",
    "STEP_MARGIN_SECONDS",
    "MAX_WAIT_SECONDS",
    "bar_seconds",
    "peers",
    "wait_seconds",
]

# Seconds a higher bot is given, ON TOP of one poll, to step its bar and reach the broker. Stepping
# the engines and one order send are each well under a few seconds; ten is the margin.
STEP_MARGIN_SECONDS = 10
# Never hold a bar longer than this, whatever the ranks say — the stop is at the broker, but a bot
# that sat for minutes would be managing its open trade late.
MAX_WAIT_SECONDS = 120


@dataclass(frozen=True)
class Peer:
    """Another bot on the same account. `rank` None = no order set (it never waits, so it is
    always ahead); `bar_seconds` None = cannot say when its bars close (treated as every bar)."""

    key: str
    rank: Optional[int]
    bar_seconds: Optional[int]


def bar_seconds(timeframe: Optional[str]) -> Optional[int]:
    """`M5` → 300, `H1` → 3600. `None` for anything whose closes may not sit on the UTC clock —
    H4 and D1 follow the broker's day — so the caller treats it as closing on every bar."""
    m = re.fullmatch(r"([MH])(\d+)", (timeframe or "").strip().upper())
    if not m:
        return None
    secs = int(m.group(2)) * (60 if m.group(1) == "M" else 3600)
    return secs if 0 < secs <= 3600 else None


def _rank(raw) -> Optional[int]:
    return raw if isinstance(raw, int) and not isinstance(raw, bool) and raw > 0 else None


def peers(me: str, root: Optional[Path] = None):
    """`(my_rank, [Peer, ...])` for the bots sharing `me`'s account, read FRESH off disk.

    `None` for the peer list when it cannot be told who else is there — an unreadable registry,
    or any config on the box that will not read (it might be on this account)."""
    try:
        folders = discover(root)
    except RegistryUnreadable:
        return None, None
    mine = read_config(folders[me]) if me in folders else None
    if mine is None:
        return None, None
    account = mine.get("account")
    out: List[Peer] = []
    for key, folder in folders.items():
        if key == me:
            continue
        cfg = read_config(folder)
        if cfg is None:
            return _rank(mine.get("account_priority")), None
        if account is None or cfg.get("account") != account:
            continue
        out.append(Peer(key, _rank(cfg.get("account_priority")), bar_seconds(cfg.get("timeframe"))))
    return _rank(mine.get("account_priority")), out


def wait_seconds(
    *,
    my_rank: Optional[int],
    others: Optional[List[Peer]],
    bar_close_ms: int,
    now_ms: float,
    poll_seconds: float,
) -> float:
    """How long this bot must wait before sizing the bar that closed at `bar_close_ms`.

    One STEP (a poll plus `STEP_MARGIN_SECONDS`) per tier ahead of this bot that also closes a bar
    now. Unranked bots never wait, so together they are one tier at the front.
    """
    if my_rank is None:
        return 0.0
    if others is None:
        tiers = my_rank - 1  # cannot tell who is there — assume every better rank is
    else:
        ahead = {
            (p.rank or 0)
            for p in others
            if (p.rank is None or p.rank < my_rank)
            and (p.bar_seconds is None or bar_close_ms % (p.bar_seconds * 1000) == 0)
        }
        tiers = len(ahead)
    if tiers <= 0:
        return 0.0
    due_ms = bar_close_ms + tiers * (float(poll_seconds) + STEP_MARGIN_SECONDS) * 1000.0
    return max(0.0, min(float(MAX_WAIT_SECONDS), (due_ms - now_ms) / 1000.0))
