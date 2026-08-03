"""
Readiness report — the checks whose failure mode is SILENCE.

The supervisor next door watches things that announce themselves: a dead agent
turns a dot red, a dead tunnel fails a run. This module covers the opposite
class — dependencies whose absence produces no error anywhere, just a feature
that quietly does nothing:

  * an un-backfilled news calendar makes the News & Holiday filter INERT. The
    engine reports `has_coverage=False` outside the fetched range and tags
    nothing, so a correctly-wired filter over an unbackfilled period looks
    identical to a broken one.
  * missing `algos/credentials.json` makes every Telegram notification a no-op.
    That is deliberate (a notifier must never be able to stop a trading loop)
    and it means a stress-test grade can finish with nobody told.

Neither is worth failing startup over and neither can be repaired from here, so
this REPORTS and does not act. It runs once, on boot, and writes one line per
finding — the point is that the first time you wonder "why did the filter do
nothing", the answer is already in the log.
"""

from __future__ import annotations

import logging
import sys
from datetime import datetime, timezone
from pathlib import Path

import config as cfg

log = logging.getLogger(__name__)

_ENGINES = Path(__file__).resolve().parent.parent.parent.parent / "engines"
if str(_ENGINES) not in sys.path:
    sys.path.insert(0, str(_ENGINES))


def _news_calendar() -> str | None:
    """Warn when the news cache is empty or stops before today.

    The cache is git-ignored, so a fresh clone starts with nothing and every
    machine backfills its own — which is exactly why this is worth stating out
    loud rather than discovering through a filter that removes zero trades.
    """
    try:
        from news import EventStore  # type: ignore
        events, _ = EventStore().load()
    except Exception as exc:
        return f"news calendar cache unreadable ({exc}) — the News & Holiday filter will be inert"
    if not events:
        return ("news calendar cache is EMPTY — the News & Holiday filter will tag nothing. "
                "Backfill with engines/news/tools/backfill.py --from YYYY-MM")
    newest = max(e.timestamp_ms for e in events)
    days_behind = (datetime.now(timezone.utc).timestamp() * 1000 - newest) / 86_400_000
    if days_behind > 30:
        end = datetime.fromtimestamp(newest / 1000, tz=timezone.utc).date()
        return (f"news calendar cache ends {end} ({int(days_behind)}d ago) — trades after that "
                f"date come back untagged, not unaffected")
    return None


def _telegram() -> str | None:
    from services import notify
    if notify.telegram_configured():
        return None
    path = cfg.MONOREPO_ROOT / "algos" / "credentials.json"
    return (f"Telegram not configured — stress-test grades and bot alerts will be dropped "
            f"silently. Set LWG_TELEGRAM_TOKEN / LWG_TELEGRAM_CHAT_ID or fill {path}")


def check() -> list[str]:
    """Every warning, worst-first. An empty list means nothing is silently degraded."""
    return [w for w in (_news_calendar(), _telegram()) if w]


def report() -> list[str]:
    warnings = check()
    for w in warnings:
        log.warning("readiness: %s", w)
    return warnings
