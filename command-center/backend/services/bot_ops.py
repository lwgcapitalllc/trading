"""What each bot is in the MIDDLE of — the one lock every action that changes a bot goes through.

🔴 **WHY IT EXISTS (Aaron, 2026-09-24): *"if I'm updating a bot I shouldn't be able to stop and
restart it."*** Every action checked only ITSELF. A deploy refused a second deploy of the same bot
and nothing else, so while one ran, Stop, Start and Restart went straight through on both the page
and the server. A deploy stops and starts the bot itself, so a hand-pressed Stop raced two
stop/start sequences against one LIVE process. A deploy likewise started over a restart already in
flight, and an account's cap, shares and priority could be rewritten under a bot halfway through
either.

**The rule: one thing at a time per bot, and an account holds still while any of its bots is
mid-action.** An action that changes a bot CLAIMS it for as long as it runs (`hold`, or
`claim`/`release` for a deploy running on its own thread). A second action on the same bot is
refused with the first one's name (`Busy` → the route answers 409), never queued. An account write
asks `account_busy` first.

⚠ **Short claims are in memory, per backend process; a DEPLOY's is on disk.** A start, stop,
restart, move or settings save runs inside the request, so it dies with a backend restart and its
claim rightly dies too. A deploy runs in its OWN process since 2026-09-24 and outlives a restart,
so its claim is read off its job file (`set_external`, wired by `routers/bots.py`) — a restarted
backend still refuses a Stop mid-deploy. Two clones each run their own backend and do not see each
other's claims; the box itself is the only thing both share, and it has no lock to offer.

⚠ **Refused, never waited for.** A click that silently waits behind a four-minute deploy looks
like a hung page, and one that fires the moment the deploy finishes does something the person
stopped expecting minutes ago.
"""

from __future__ import annotations

import threading
import time
from collections.abc import Callable, Iterable, Iterator
from contextlib import contextmanager

_lock = threading.Lock()
# bot key → (what it is doing, in words; when it started)
_ops: dict[str, tuple[str, float]] = {}
# Claims held OUTSIDE this process — {bot key: what it is doing}. A deploy, read off disk.
_external: Callable[[], dict[str, str]] = dict


def set_external(fn: Callable[[], dict[str, str]]) -> None:
    """Where claims held outside this process are read from. Called once, at import, by the
    router that owns them; a test may swap it."""
    global _external
    _external = fn


def _held_now() -> dict[str, str]:
    """Every claim, in this process and outside it. Caller holds `_lock`."""
    try:
        out = dict(_external())
    except Exception:  # noqa: BLE001 - an unreadable record must not stop every action
        out = {}
    out.update({k: v[0] for k, v in _ops.items()})
    return out


class Busy(Exception):
    """The bot is already in the middle of something. `str()` is a sentence for the person."""


def _sentence(name: str, doing: str) -> str:
    return f"{name} is {doing} — wait for that to finish, then try again."


def claim(bot_key: str, doing: str, name: str | None = None) -> None:
    """Mark `bot_key` as `doing` (a present participle: "deploying", "restarting").
    Raises `Busy` naming what it is already doing."""
    with _lock:
        held = _held_now().get(bot_key)
        if held is not None:
            raise Busy(_sentence(name or bot_key, held))
        _ops[bot_key] = (doing, time.time())


def release(bot_key: str, doing: str | None = None) -> None:
    """Clear the claim — only if it is still `doing`, when given, so an action whose claim was
    handed on (`hand_over`) cannot clear its successor's. Safe to call when there is none."""
    with _lock:
        held = _ops.get(bot_key)
        if held is not None and (doing is None or held[0] == doing):
            del _ops[bot_key]


def hand_over(bot_key: str, doing: str, to: str) -> bool:
    """Turn a claim held as `doing` into one held as `to`, with no gap between them for another
    action to slip into. `False` when the bot is not held as `doing` — nothing is changed.

    For an action that ends by starting a longer one on the same bot: a move that deploys."""
    with _lock:
        held = _ops.get(bot_key)
        if held is None or held[0] != doing:
            return False
        _ops[bot_key] = (to, held[1])
        return True


@contextmanager
def hold(bot_key: str, doing: str, name: str | None = None) -> Iterator[None]:
    """`claim` for the length of a `with` block, released however the block ends — unless it
    was handed over inside it, in which case the new holder releases it."""
    claim(bot_key, doing, name)
    try:
        yield
    finally:
        release(bot_key, doing)


def doing(bot_key: str) -> str | None:
    """What this bot is in the middle of, or `None`."""
    with _lock:
        return _held_now().get(bot_key)


def refuse_if_busy(bot_key: str, name: str | None = None) -> None:
    """Raise `Busy` if the bot is mid-action — for an action too short, or too entangled with
    another claim, to hold one of its own."""
    now = doing(bot_key)
    if now is not None:
        raise Busy(_sentence(name or bot_key, now))


def account_busy(bot_keys: Iterable[str], names: dict[str, str] | None = None) -> str | None:
    """A sentence saying why an ACCOUNT write must wait, or `None` when none of its bots is
    mid-action. An account's cap, shares and priority are read by every bot on it, so none of them
    may move while one of those bots is being deployed, stopped or started."""
    names = names or {}
    with _lock:
        held = _held_now()
    busy = [(k, held[k]) for k in bot_keys if k in held]
    if not busy:
        return None
    k, what = busy[0]
    return (
        f"{names.get(k, k)} is {what} on this account — its settings can be changed once that "
        "has finished."
    )


def snapshot() -> dict[str, str]:
    """Every current claim, bot key → what it is doing. What the page reads to lock its buttons."""
    with _lock:
        return _held_now()
