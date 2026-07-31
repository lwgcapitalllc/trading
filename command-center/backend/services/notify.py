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
import urllib.request
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
            _cache = {}     # absent is normal on a fresh clone — the caller no-ops
    return _cache


def _cred(key: str, env: str) -> str:
    v = os.environ.get(env, "")
    if v:
        return v
    return str(_creds().get(key, "") or "")


def telegram_configured() -> bool:
    """True when a token and a destination both resolve. Useful for a health check that wants
    to say "notifications are off" instead of silently dropping them."""
    return bool(_cred("telegram_token", "LWG_TELEGRAM_TOKEN")
                and _cred("telegram_chat_id", "LWG_TELEGRAM_CHAT_ID"))


def send_telegram(text: str, chat_id: str = "") -> bool:
    """Best-effort send. Returns True on success, and NEVER raises — a notification failure
    must not turn a working endpoint into a 500."""
    token = _cred("telegram_token", "LWG_TELEGRAM_TOKEN")
    dest = chat_id or _cred("telegram_chat_id", "LWG_TELEGRAM_CHAT_ID")
    if not token or not dest:
        return False
    try:
        data = json.dumps({"chat_id": dest, "text": text, "parse_mode": "Markdown"}).encode()
        req = urllib.request.Request(
            f"https://api.telegram.org/bot{token}/sendMessage",
            data=data,
            headers={"Content-Type": "application/json"},
        )
        urllib.request.urlopen(req, timeout=_TIMEOUT).close()
        return True
    except Exception:
        return False
