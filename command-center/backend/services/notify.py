"""
Command-center Telegram notifier.

Uses urllib so it has no extra dependencies (the backend uses urllib throughout).

**Credentials are read from the same FILE the VPS side uses** — `algos/credentials.json`,
git-ignored — or from the environment, which wins. They are deliberately NOT read by importing
`algos/shared/credentials.py`: `command-center/` and `algos/` are independent by repo rule, and
"read the other domain's files" is the allowed seam while "import the other domain's code" is
not. The cost of that boundary is this small duplicated lookup; the benefit is that neither app
can break the other's imports.

This replaced a hardcoded token that was committed here and in five other files (revoked
2026-07-30). The old standing rule — "keep this in sync with algos/shared/notify.py" — is
gone: there is nothing left to keep in sync, because neither file holds a value.
"""

from __future__ import annotations

import json
import os
import time
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

import config as cfg

_TIMEOUT = 5
_CREDS_PATH = cfg.MONOREPO_ROOT / "algos" / "credentials.json"

_cache: Optional[dict] = None


def _creds() -> dict:
    global _cache
    if _cache is None:
        try:
            _cache = json.loads(Path(_CREDS_PATH).read_text(encoding="utf-8"))
        except Exception:
            _cache = {}  # absent is normal on a fresh clone — the caller no-ops
    return _cache


def _cred(key: str, env: str) -> str:
    v = os.environ.get(env, "")
    if v:
        return v
    return str(_creds().get(key, "") or "")


# ── Routing, mirroring algos/shared/notify.py ────────────────────────────────────────────────
#
# The KIND of a message picks its room: fills in one chat, everything about the machinery in
# another. This app sends no trade alerts at all — the live bot does that — so in practice every
# call here is HEALTH. `TRADE` exists anyway, because the alternative is a module that routes by
# having only one option, which stops being true the first time someone adds a sender.
#
# ⚠ This is a SECOND implementation of one rule, and that is the cost of the `algos/` ↔
# `command-center/` boundary (see the module docstring — a shared FILE is the allowed seam, a
# shared import is not). What keeps the two from drifting is that they read the same credential
# KEYS, and `tests/test_notification_routing.py` on each side pins the same table.
TRADE = "trade"
HEALTH = "health"

CHAT_KEYS = {
    TRADE: ("telegram_chat_id", "LWG_TELEGRAM_CHAT_ID"),
    HEALTH: ("telegram_health_chat", "LWG_TELEGRAM_HEALTH_CHAT"),
}

_warned_kinds: set = set()


def chat_for(kind: str) -> str:
    """The chat a message of this `kind` goes to. HEALTH falls back to the TRADE chat and says
    so once — the wrong room beats no delivery, which is the same call the algos side makes."""
    if kind not in CHAT_KEYS:
        raise ValueError(
            f"unknown notification kind {kind!r} - expected one of {sorted(CHAT_KEYS)}"
        )
    dest = _cred(*CHAT_KEYS[kind])
    if dest:
        return dest
    if kind != TRADE:
        fallback = _cred(*CHAT_KEYS[TRADE])
        if fallback and kind not in _warned_kinds:
            _warned_kinds.add(kind)
            print(
                f"notify: {CHAT_KEYS[kind][0]} is not set - {kind} messages are going to the "
                f"main group. Set it in algos/credentials.json to split them out."
            )
        return fallback
    return ""


def telegram_configured() -> bool:
    """True when a token and a destination both resolve. Useful for a health check that wants
    to say "notifications are off" instead of silently dropping them."""
    return bool(
        _cred("telegram_token", "LWG_TELEGRAM_TOKEN")
        and _cred("telegram_chat_id", "LWG_TELEGRAM_CHAT_ID")
    )


def send_telegram(text: str, kind: str, chat_id: str = "", *, bot=None, account=None) -> bool:
    """Best-effort send. Returns True on success, and NEVER raises — a notification failure
    must not turn a working endpoint into a 500.

    Use `send_telegram_id` when the message id is needed; this wrapper exists so the many
    callers that only care whether it went keep reading cleanly.

    Falls back to UNFORMATTED text when Telegram rejects the Markdown. Formatting is a nicety;
    delivery is the point. A single underscore in a strategy name, a symbol or a file path
    (`sos_fade`, `MT5_FFT`, `live_config.py`) opens an italic that never closes and Telegram
    refuses the whole message — so the alert most likely to be lost is the one carrying an error,
    because error text is full of paths. Measured on the VPS side's first real send, 2026-07-31.
    """
    return send_telegram_id(text, kind, chat_id, bot=bot, account=account) is not None


def send_telegram_id(
    text: str, kind: str, chat_id: str = "", reply_to=None, *, bot=None, account=None
):
    """The same send, returning Telegram's `message_id` (or None on failure).

    The id is what lets a LATER message reply to this one, which is how a deploy's STOPPED and
    ONLINE land under the PROMOTED that caused them instead of loose in the feed. Mirrors
    `algos/shared/notify.py::send_telegram_id`, which the bot on the VPS uses for the same
    reason — the two are the same shape on purpose, because they thread into each other.

    ⚠ **0 is returned for DELIVERED-BUT-UNREADABLE.** The send is what matters; a thread root
    nobody can name is a missing reply, not a missing message, and returning None there would
    read as a failure and invite a caller to send it twice.

    ⚠ `reply_to` is BEST EFFORT: Telegram refuses the whole send when the message being replied
    to has been deleted, and a missing thread link is never a reason to lose an alert. This side
    only ever ROOTS a thread, so it does not retry standalone; the bot's copy does.
    """
    token = _cred("telegram_token", "LWG_TELEGRAM_TOKEN")
    dest = chat_id or chat_for(kind)
    if not token or not dest:
        log_send(kind, "dropped", text, dest, bot=bot, account=account, reason="not configured")
        return None

    def _post(parse_mode):
        body = {"chat_id": dest, "text": text}
        if parse_mode:
            body["parse_mode"] = parse_mode
        if reply_to:
            body["reply_to_message_id"] = reply_to
        req = urllib.request.Request(
            f"https://api.telegram.org/bot{token}/sendMessage",
            data=json.dumps(body).encode(),
            headers={"Content-Type": "application/json"},
        )
        with urllib.request.urlopen(req, timeout=_TIMEOUT) as r:
            try:
                return json.loads(r.read().decode()).get("result", {}).get("message_id")
            except Exception:
                return 0

    def _sent(mid):
        log_send(kind, "sent", text, dest, bot=bot, account=account, message_id=mid)
        return mid

    def _dropped(why):
        log_send(kind, "dropped", text, dest, bot=bot, account=account, reason=why)
        return None

    try:
        return _sent(_post("Markdown"))
    except urllib.error.HTTPError as e:
        if e.code != 400:
            return _dropped(f"HTTP {e.code}")
        try:
            detail = e.read().decode("utf-8", "replace")
        except Exception:
            detail = ""
        if "parse entities" not in detail:
            return _dropped("HTTP 400")
    except Exception as e:
        return _dropped(f"send failed: {e}")

    try:
        return _sent(_post(None))
    except Exception as e:
        return _dropped(f"send failed: {e}")


# ── the send log, mirroring algos/shared/notify_log.py (2026-09-26) ─────────────────────────
#
# Every send this app makes is written as one JSON line in the SAME folder format the VPS side
# uses (`algos/logs/notify/<UTC date>.jsonl`, never committed), so one reader reads either
# machine's. ⚠ It is the LAPTOP's copy: this app runs there, so its lines land in the laptop's
# folder and the box's daily summary never sees them. Deliberately no outbox here — a Command
# Center action is a person at a screen, who sees the result on the page.
#
# ⚠ A copy, not an import, for the boundary reason in the module docstring. The line format is
# pinned to the algos side by `tests/test_notification_routing.py`, which reads that file.


def notify_dir() -> Path:
    override = os.environ.get("LWG_NOTIFY_DIR", "").strip()
    return Path(override) if override else cfg.MONOREPO_ROOT / "algos" / "logs" / "notify"


def parse_header(text: str) -> tuple:
    """`(LABEL, subject)` off `<icon> <LABEL> · <subject>` — the same split the algos side makes."""
    try:
        first = str(text or "").strip().splitlines()[0].strip()
    except IndexError:
        return "", ""
    parts = first.split(" ", 1)
    if len(parts) == 2 and not any(ch.isascii() and ch.isalnum() for ch in parts[0]):
        first = parts[1].strip()
    label, _, subject = first.partition(" · ")
    return label.strip(), subject.strip()


def log_send(kind, outcome, text, room, *, bot=None, account=None, message_id=None, reason=None):
    """Append one send-log line. NEVER raises — a log line may never cost the message."""
    try:
        now = datetime.fromtimestamp(time.time(), tz=timezone.utc)
        label, subject = parse_header(text)
        row = {
            "ts": now.isoformat(timespec="seconds"),
            "kind": kind,
            "outcome": outcome,
            "label": label,
            "subject": subject,
            "bot": bot,
            "account": account,
            "room": str(room or ""),
            "source": "command-center",
        }
        if message_id is not None:
            row["message_id"] = message_id
        if reason:
            row["reason"] = reason
        folder = notify_dir()
        folder.mkdir(parents=True, exist_ok=True)
        with open(folder / f"{now:%Y-%m-%d}.jsonl", "a", encoding="utf-8") as fh:
            fh.write(json.dumps(row, ensure_ascii=False, default=str) + "\n")
    except Exception as e:  # noqa: BLE001
        print(f"notify: could not write the send log ({e})")
