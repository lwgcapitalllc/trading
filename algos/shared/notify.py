"""
notify.py — Telegram notification helper for VPS-side components.

Single source of truth for sending Telegram messages from bots,
monitor, and any other VPS process. Sends to GROUP_CHAT by default.

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

TELEGRAM_TOKEN = "8888123776:AAFuWpPoKnHSmGwxNxRB9Qo61kDSk7w0YD8"
GROUP_CHAT     = "-1003977707258"   # LWG Capital Algos Notifications


def send_telegram(text: str, chat_id: str = GROUP_CHAT):
    if _requests is None:
        print(f"notify: requests not installed, dropping message: {text}")
        return
    try:
        _requests.post(
            f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage",
            json={"chat_id": chat_id, "text": text, "parse_mode": "Markdown"},
            timeout=5,
        )
    except Exception as e:
        print(f"notify: send failed: {e}")
