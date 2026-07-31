"""
notify.py — Telegram notification helper for VPS-side components.

Single source of truth for sending Telegram messages from bots, the live runner, monitor,
and any other VPS process. Sends to the group chat by default.

Credentials come from `credentials.py` (env var, else the git-ignored `algos/credentials.json`)
— never from a literal in this file. The previous token was committed here and in five other
files; it was revoked 2026-07-30 and the constants were replaced by this lookup.

Usage:
    from notify import send_telegram
    send_telegram("🟢 *Bot online*")
"""

import sys
from pathlib import Path

try:
    import requests as _requests
except ImportError:
    _requests = None

sys.path.insert(0, str(Path(__file__).resolve().parent))
from credentials import get as _cred, telegram_credentials  # noqa: E402

_warned = False
_warned_keys: set = set()


def send_telegram(text: str, chat_id: str = "", token_key: str = "") -> bool:
    """Send `text` to `chat_id` (default: the configured group). Returns True on success.

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
    global _warned
    token, group, _admin = telegram_credentials()
    if token_key:
        named = _cred(token_key)
        if named:
            token = named
        elif token_key not in _warned_keys:
            _warned_keys.add(token_key)
            print(f"notify: credential {token_key!r} is not set - falling back to the default "
                  f"Telegram bot. Add it to algos/credentials.json, or clear telegram_token_key "
                  f"in this bot's instance config.")
    dest = chat_id or group
    if not token or not dest:
        if not _warned:
            _warned = True
            print("notify: Telegram is not configured (see algos/credentials.template.json) - "
                  "messages will be dropped for the rest of this run")
        return False
    if _requests is None:
        print(f"notify: requests not installed, dropping message: {text}")
        return False
    url = f"https://api.telegram.org/bot{token}/sendMessage"

    def _post(parse_mode):
        body = {"chat_id": dest, "text": text}
        if parse_mode:
            body["parse_mode"] = parse_mode
        return _requests.post(url, json=body, timeout=5)

    try:
        r = _post("Markdown")
        if r.status_code == 400 and "parse entities" in r.text:
            # Markdown is a nicety; DELIVERY is the point. An underscore in a bot key, a symbol
            # or a file path inside an exception opens an italic that never closes, and Telegram
            # rejects the WHOLE message — so the alert that never arrives is the one reporting a
            # crash, whose text is a traceback full of paths. Measured on the first real send:
            # "MT5_FFT" alone was enough. Retry unformatted rather than lose it.
            print("notify: Markdown rejected, resending as plain text - "
                  f"{r.text[:160]}")
            r = _post(None)
        if r.status_code != 200:
            print(f"notify: Telegram returned {r.status_code}: {r.text[:200]}")
            return False
        return True
    except Exception as e:
        print(f"notify: send failed: {e}")
        return False
