"""
notify.py — Telegram notification helper for VPS-side components.

Single source of truth for sending Telegram messages from bots, the live runner, monitor,
and any other VPS process. Every message declares its KIND (`TRADE` or `HEALTH`) and the kind
picks the room — see the routing block below.

Credentials come from `credentials.py` (env var, else the git-ignored `algos/credentials.json`)
— never from a literal in this file. The previous token was committed here and in five other
files; it was revoked 2026-07-30 and the constants were replaced by this lookup.

Usage:
    from notify import send_telegram, TRADE, HEALTH
    send_telegram("🟢 *Bot online*", HEALTH)
"""

import sys
from pathlib import Path

try:
    import requests as _requests
except ImportError:
    _requests = None

sys.path.insert(0, str(Path(__file__).resolve().parent))
from credentials import get as _cred, telegram_credentials  # noqa: E402

# ── Where a message goes is decided by WHAT IT IS ────────────────────────────────────────────
#
# Two rooms, because they are read at different times and by a different reflex. A fill is the
# account moving and it is read the moment it arrives; a re-warm after a link blip is a fact
# about the machinery, worth having and worth scrolling past. Mixing them costs the trade alert
# its meaning — a chat that pings nine times a day for routine chatter is one you learn to
# ignore, and the day you mute it you mute your fills with it. The dead-man's switch already
# makes the same call one level out by using EMAIL.
#
# `kind` is a REQUIRED argument on every sender here, deliberately. A default would route
# silently, and "the wrong room, quietly" is precisely the failure this exists to end — the
# same reasoning that makes the ledger's stream routing a table rather than a guess. A new call
# site that states nothing fails at the call, and `test_notification_routing.py` greps every
# call site in the repo so it fails in the SUITE first.
TRADE = "trade"
HEALTH = "health"

#: kind -> the credential key naming its chat. HEALTH falls back to the TRADE chat (see
#: `chat_for`); a message in the wrong room beats a message nobody sends.
CHAT_KEYS = {
    TRADE:  "telegram_chat_id",
    HEALTH: "telegram_health_chat",
}

_warned = False
_warned_keys: set = set()
_warned_kinds: set = set()


def chat_for(kind: str, override: str = ""):
    """`(chat_id, is_dedicated)` for a message of this `kind`.

    `override` is the bot's own instance-config value and wins outright — that is what lets two
    bots on two accounts report into two different rooms.

    HEALTH falls back to the TRADE chat when `telegram_health_chat` is unset, and SAYS SO once.
    That is the opposite call from `deadman_url`, where unset means the check cannot work at
    all: here the message is still worth delivering, just not where you wanted it. The fallback
    is a nuisance you can see, never a silent drop.
    """
    if kind not in CHAT_KEYS:
        raise ValueError(f"unknown notification kind {kind!r} - expected one of "
                         f"{sorted(CHAT_KEYS)}")
    if override:
        return override, True
    dest = _cred(CHAT_KEYS[kind])
    if dest:
        return dest, True
    if kind != TRADE:
        fallback = _cred(CHAT_KEYS[TRADE])
        if fallback and kind not in _warned_kinds:
            _warned_kinds.add(kind)
            print(f"notify: {CHAT_KEYS[kind]} is not set - {kind} messages are going to the "
                  f"main group. Set it in algos/credentials.json to split them out.")
        return fallback, False
    return "", False


def send_telegram(text: str, kind: str, chat_id: str = "", token_key: str = "",
                  reply_to=None) -> bool:
    """Send `text` to the chat this `kind` routes to. Returns True on success.

    `kind` is `TRADE` or `HEALTH` and is required — see the routing block above.

    Use `send_telegram_id` instead when the message id is needed — this wrapper exists so the
    many callers that only care whether it went keep reading cleanly.

    `chat_id` and `token_key` are what make notifications PER BOT. A deployment sets them in its
    own instance config, so two bots on two accounts can report into two different groups, and
    can do it as two different Telegram bots. `token_key` names a key in `algos/credentials.json`
    (e.g. `telegram_token_bleg`) rather than carrying the token itself — the secret never enters
    an instance config, which is a normal committed-ish JSON file.

    A named token that is missing falls back to the default one and WARNS, rather than dropping
    the message: the wrong sender identity is recoverable, a silently missing trade alert is not.
    (It will usually still fail at Telegram — a bot can only post to a chat it belongs to — but
    it fails loudly, with the reason printed.)

    NEVER raises. A notifier that can take down a trading loop is worse than a missed message,
    so every failure path — no requests, no credentials, a dead network, a 4xx from Telegram —
    prints and returns False. Credentials are read per call rather than at import so a bot that
    starts before the file is written picks it up on the next message instead of staying mute
    for its whole session.
    """
    return send_telegram_id(text, kind, chat_id, token_key, reply_to) is not None


def send_telegram_id(text: str, kind: str, chat_id: str = "", token_key: str = "",
                     reply_to=None):
    """Same send, but returns Telegram's `message_id` (or None on failure).

    The id is what lets a later message REPLY to this one — the trade exit replies to the trade
    entry, so both halves of a trade sit in one thread and an outcome is never read apart from
    the setup it came from.

    `reply_to` is best-effort by design: if the message being replied to has been deleted,
    Telegram refuses the send outright. A missing thread link is not a reason to lose a trade
    alert, so that case retries as a standalone message.
    """
    global _warned
    token, _group, _admin = telegram_credentials()
    if token_key:
        named = _cred(token_key)
        if named:
            token = named
        elif token_key not in _warned_keys:
            _warned_keys.add(token_key)
            print(f"notify: credential {token_key!r} is not set - falling back to the default "
                  f"Telegram bot. Add it to algos/credentials.json, or clear telegram_token_key "
                  f"in this bot's instance config.")
    dest, _dedicated = chat_for(kind, chat_id)
    if not token or not dest:
        if not _warned:
            _warned = True
            print("notify: Telegram is not configured (see algos/credentials.template.json) - "
                  "messages will be dropped for the rest of this run")
        return None
    if _requests is None:
        print(f"notify: requests not installed, dropping message: {text}")
        return None
    url = f"https://api.telegram.org/bot{token}/sendMessage"

    def _post(parse_mode, reply):
        body = {"chat_id": dest, "text": text}
        if parse_mode:
            body["parse_mode"] = parse_mode
        if reply:
            body["reply_to_message_id"] = reply
        return _requests.post(url, json=body, timeout=5)

    try:
        r = _post("Markdown", reply_to)
        if reply_to and r.status_code == 400 and "replied" in r.text:
            # The entry message was deleted. Losing the thread link is a cosmetic loss; losing
            # the trade alert is not.
            print("notify: reply target is gone, sending standalone")
            reply_to = None
            r = _post("Markdown", None)
        if r.status_code == 400 and "parse entities" in r.text:
            # Markdown is a nicety; DELIVERY is the point. An underscore in a bot key, a symbol
            # or a file path inside an exception opens an italic that never closes, and Telegram
            # rejects the WHOLE message — so the alert that never arrives is the one reporting a
            # crash, whose text is a traceback full of paths. Measured on the first real send:
            # "MT5_FFT" alone was enough. Retry unformatted rather than lose it.
            print("notify: Markdown rejected, resending as plain text - "
                  f"{r.text[:160]}")
            r = _post(None, reply_to)
        if r.status_code != 200:
            print(f"notify: Telegram returned {r.status_code}: {r.text[:200]}")
            return None
        return (r.json().get("result") or {}).get("message_id")
    except Exception as e:
        print(f"notify: send failed: {e}")
        return None
