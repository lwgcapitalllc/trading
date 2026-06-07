"""
Command-center Telegram notifier.

Mirrors the token/chat from algos/shared/notify.py but uses urllib so it
has no extra dependencies (command-center already uses urllib throughout).
"""

from __future__ import annotations

import json
import urllib.request

_TOKEN    = "8888123776:AAFuWpPoKnHSmGwxNxRB9Qo61kDSk7w0YD8"
_CHAT_ID  = "-1003977707258"
_TIMEOUT  = 5


def send_telegram(text: str, chat_id: str = _CHAT_ID) -> None:
    try:
        data = json.dumps({"chat_id": chat_id, "text": text, "parse_mode": "Markdown"}).encode()
        req  = urllib.request.Request(
            f"https://api.telegram.org/bot{_TOKEN}/sendMessage",
            data=data,
            headers={"Content-Type": "application/json"},
        )
        urllib.request.urlopen(req, timeout=_TIMEOUT).close()
    except Exception:
        pass  # never block the caller; Telegram is best-effort
