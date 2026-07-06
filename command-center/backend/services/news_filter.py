"""
news_filter.py — tag a backtest's trades against the canonical economic-calendar (news) engine.

The lab runs every backtest RAW (the strategy trades straight through news). This service is the
post-processing view layer the user asked for: given a run's trades, it marks which ones opened
inside a high-impact news window (15 min before → 30 min after, by default) and which opened on a
bank holiday. The frontend uses those tags to REMOVE trades and recompute KPIs/charts live — no VPS
re-run, because taking trades out is just arithmetic on the already-produced trade list.

Two kinds of tag, treated differently in the UI:
  * in_holiday — bank holidays are ALWAYS avoided (Aaron's rule). These trades are removed no matter
                 what; they are not part of the toggle.
  * in_news    — high-impact USD releases. The toggle adds/removes these; its starting position is
                 the strategy's own news rule.

This module owns NO news logic of its own — it composes the single canonical engine in
`engines/news/` (never a second implementation). It only builds the bot-style NewsPolicy the lab
uses and walks the run's trades through the engine.

Coverage honesty: outside the fetched calendar range the engine reports has_coverage=False, so a
trade there is left untagged (we do not claim to know), and the toggle simply can't touch it.
Backfill the tested months (`engines/news/tools/backfill.py`) to get real coverage.
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import List, Optional, Sequence, Tuple

# engines/ on sys.path so the canonical engines import by bare name (same pattern as regime).
_ENGINES = Path(__file__).resolve().parent.parent.parent.parent / "engines"
if str(_ENGINES) not in sys.path:
    sys.path.insert(0, str(_ENGINES))

from news import EventStore, Impact, NewsEngine, NewsEvent, NewsPolicy  # noqa: E402

# Aaron's defaults (2026-07-05): block a high-impact release from 15 min before to 30 min after.
# Asymmetric on purpose — liquidity only dies in the last few minutes before, but the spike +
# reversal + real move run 15–30 min after. A bot/UI can override per run.
NEWS_PRE_DEFAULT = 15
NEWS_POST_DEFAULT = 30

Interval = Tuple[int, int]


def make_policy(
    pre_minutes: int = NEWS_PRE_DEFAULT,
    post_minutes: int = NEWS_POST_DEFAULT,
    currencies: Sequence[str] = ("USD",),
    min_impact: Impact = Impact.HIGH,
) -> NewsPolicy:
    """The lab's NewsPolicy. High-impact USD by default (gold/US-index/crude all trade the USD macro
    calendar). block_holidays is always True here — holidays are Aaron's always-avoid rule — but the
    tagging reads the holiday flag independently, so the two removals stay separable in the UI."""
    return NewsPolicy(
        currencies=frozenset(currencies),
        min_impact=min_impact,
        pre_minutes=pre_minutes,
        post_minutes=post_minutes,
        block_holidays=True,
    )


def load_engine(
    pre_minutes: int = NEWS_PRE_DEFAULT,
    post_minutes: int = NEWS_POST_DEFAULT,
    currencies: Sequence[str] = ("USD",),
    min_impact: Impact = Impact.HIGH,
    store: Optional[EventStore] = None,
) -> Optional[NewsEngine]:
    """Build a NewsEngine from the local calendar cache, or None if the cache is empty. `store` is
    injectable for tests; production reads engines/news/data/events.json."""
    events, covered = (store or EventStore()).load()
    if not events:
        return None
    return NewsEngine(events, policy=make_policy(pre_minutes, post_minutes, currencies, min_impact),
                      covered_ranges=covered)


def tag_trades(engine: NewsEngine, trades: Sequence[dict]) -> List[dict]:
    """Mark each trade in/out of a news window and on/off a bank holiday.

    `trades` is `[{"index": int, "entry_ms": int|None}, ...]` — entry_ms is the trade's OPEN time in
    epoch ms, UTC. Returns one dict per trade (input order preserved):
        {index, entry_ms, in_coverage, in_news, in_holiday, title}
    A trade with no entry_ms, or one in a period the calendar doesn't cover, is left untagged
    (in_coverage False, both flags False) — we never guess.

    We feed the engine trades in time order (its point-in-time answers — in_blackout / active_event /
    is_holiday — are order-independent; only its edge outputs, which we ignore, care about order).
    """
    order = sorted(range(len(trades)), key=lambda i: (trades[i].get("entry_ms") is None,
                                                       trades[i].get("entry_ms") or 0))
    tagged: dict = {}
    for i in order:
        t = trades[i]
        ems = t.get("entry_ms")
        if ems is None:
            tagged[i] = {"index": t.get("index"), "entry_ms": None,
                         "in_coverage": False, "in_news": False, "in_holiday": False, "title": None}
            continue
        out = engine.update(t.get("index", i), int(ems))
        in_news = out.has_coverage and out.active_event is not None
        in_holiday = out.has_coverage and out.is_holiday
        title = (out.active_event.title if in_news
                 else out.active_holiday.title if in_holiday else None)
        tagged[i] = {
            "index": t.get("index"), "entry_ms": int(ems),
            "in_coverage": out.has_coverage, "in_news": in_news,
            "in_holiday": in_holiday, "title": title,
        }
    return [tagged[i] for i in range(len(trades))]


def build_report(
    trades: Sequence[dict],
    *,
    pre_minutes: int = NEWS_PRE_DEFAULT,
    post_minutes: int = NEWS_POST_DEFAULT,
    currencies: Sequence[str] = ("USD",),
    min_impact: Impact = Impact.HIGH,
    store: Optional[EventStore] = None,
) -> dict:
    """The endpoint payload: per-trade news/holiday tags + coverage boundary + a count summary.

    When the calendar cache has no data at all, `has_data` is False and every trade is untagged —
    the UI shows "no news data for this period" and the toggle stays inert.
    """
    engine = load_engine(pre_minutes, post_minutes, currencies, min_impact, store=store)
    if engine is None:
        return {
            "has_data": False, "coverage_start_ms": None, "coverage_end_ms": None,
            "pre_minutes": pre_minutes, "post_minutes": post_minutes,
            "trades": [{"index": t.get("index"), "entry_ms": t.get("entry_ms"),
                        "in_coverage": False, "in_news": False, "in_holiday": False, "title": None}
                       for t in trades],
            "news_trade_count": 0, "holiday_trade_count": 0,
        }
    tagged = tag_trades(engine, trades)
    return {
        "has_data": True,
        "coverage_start_ms": engine.coverage_start_ms,
        "coverage_end_ms": engine.coverage_end_ms,
        "pre_minutes": pre_minutes, "post_minutes": post_minutes,
        "trades": tagged,
        "news_trade_count": sum(1 for t in tagged if t["in_news"]),
        "holiday_trade_count": sum(1 for t in tagged if t["in_holiday"]),
    }
