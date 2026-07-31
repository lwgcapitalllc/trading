"""credentials.py — the ONE place VPS-side code resolves secrets from.

**Why this exists.** The Telegram bot token was pasted into six files and committed. It was
revoked on 2026-07-30, which is the cheap version of this lesson; the expensive version is a
token that stays live in git history while the repo is shared. Nothing here may ever hold a
literal credential — this module only knows where to LOOK.

Resolution order, first hit wins:

1. **Environment variables** — `LWG_TELEGRAM_TOKEN`, `LWG_TELEGRAM_CHAT_ID`,
   `LWG_TELEGRAM_ADMIN_CHAT_ID`. Scheduled tasks and one-off shells set these; they also make
   a container or a second account trivial without touching a file.
2. **`algos/credentials.json`** — git-ignored (the repo-root `.gitignore` matches
   `credentials.json` at any depth), so it exists per machine and never travels. Committed
   alongside it is `credentials.template.json`, which carries the SHAPE and no values.

A missing credential is returned as an empty string, never a guess and never an exception at
import time. The senders treat empty as "not configured", log it once, and carry on — a bot
must not refuse to trade because a notification channel is unset, and it must not crash at
2am for it either. `require()` is there for the callers that genuinely cannot proceed.

The command center reads the SAME FILE from its own side (`services/notify.py`) rather than
importing this module: `command-center/` and `algos/` are independent by repo rule, and a
shared data file is the allowed seam — a shared import is not.
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Optional

__all__ = ["telegram_credentials", "credentials_path", "env_name", "get", "require"]

# algos/shared/credentials.py -> algos/credentials.json
_PATH = Path(__file__).resolve().parent.parent / "credentials.json"

_ENV_KEYS = {
    "telegram_token":           "LWG_TELEGRAM_TOKEN",
    "telegram_chat_id":         "LWG_TELEGRAM_CHAT_ID",
    "telegram_admin_chat_id":   "LWG_TELEGRAM_ADMIN_CHAT_ID",
}

_cache: Optional[dict] = None


def env_name(key: str) -> str:
    """The environment variable a credential key maps to. The three canonical keys keep their
    historical names; anything else follows the `LWG_<KEY>` rule, so a per-bot secret
    (`telegram_token_bleg` -> `LWG_TELEGRAM_TOKEN_BLEG`) needs no registration here."""
    return _ENV_KEYS.get(key) or f"LWG_{key.upper()}"


def credentials_path() -> Path:
    """Where the file is looked for. Exposed so an error message can name it."""
    return _PATH


def _load() -> dict:
    global _cache
    if _cache is None:
        try:
            _cache = json.loads(_PATH.read_text(encoding="utf-8"))
        except Exception:
            # Absent or unreadable is a NORMAL state (fresh clone, env-only host) — the caller
            # decides whether that is fatal. Never raise from a module-level read.
            _cache = {}
    return _cache


def get(key: str, default: str = "") -> str:
    """One credential by key. Env var wins, then the file, then `default`. Any key works, not
    just the canonical three — that is what lets one bot carry its own Telegram identity
    (`telegram_token_bleg`) without a second resolver or a literal in an instance config."""
    v = os.environ.get(env_name(key), "")
    if v:
        return v
    v = _load().get(key, "")
    return str(v) if v else default


def require(key: str) -> str:
    """`get`, but raise with an actionable message. For callers that cannot proceed without it
    (e.g. the Telegram command bot, whose entire job is the connection)."""
    v = get(key)
    if not v:
        raise RuntimeError(
            f"Missing credential {key!r}. Set {env_name(key)} in the "
            f"environment, or add it to {_PATH} (copy credentials.template.json)."
        )
    return v


def telegram_credentials() -> tuple[str, str, str]:
    """`(token, group_chat_id, admin_chat_id)` — the trio every notifier needs. Any of them may
    be empty; senders no-op rather than raising."""
    return (get("telegram_token"),
            get("telegram_chat_id"),
            get("telegram_admin_chat_id"))
