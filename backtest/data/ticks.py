"""Real bid/ask ticks — the honest intrabar path for the fill model (A2).

**Why this exists.** A bar says price touched a high and a low; it does not say in what ORDER. When
one bar covers both a target and a stop, the bar cannot tell you which filled — and that single
unknown decides whether the trade was a win or a loss. The bar-level fill model guesses from the
open's proximity to the extremes. Ticks remove the guess.

**Why it fetches so little.** Gold runs ~690k ticks/day (~43MB of JSON, ~90s on the wire, measured
2026-07-14). Replaying a multi-month backtest tick-by-tick over HTTP is not viable and is also
unnecessary: only the few bars where a target and a stop are BOTH in range are ambiguous, and only
those need ticks. `TickSource` is therefore lazy — nothing is fetched until a resolver asks about a
specific window.

**Why the cache is hourly.** A tick window is arbitrary, so caching by exact window would never hit
twice. The hour is the natural bucket: bars within the same hour share one fetch (~30k ticks, ~2MB),
and an hour is stable and enumerable, so a request maps to a deterministic set of files. Buckets are
cached whole; a partially-fetched hour is never written.

Empty is a real answer, not a miss: weekends, holidays, and the 17:00-NY gold break genuinely have
no ticks (the daily break is visible as a hard zero-tick hour). An empty bucket is cached as empty
so we don't re-ask the broker every time — a caller that reads back zero ticks must fall back
rather than assume the fetch failed.
"""

from __future__ import annotations

import datetime as _dt
import json
import os
import re
from pathlib import Path
from typing import List, Optional, Sequence

from .cache import FEED_VERSION, _default_cache_dir

__all__ = ["Tick", "TickCache", "TickSource", "TickWindowUnavailable"]


class TickWindowUnavailable(RuntimeError):
    """Ticks for a window could not be obtained (agent down, or window refused).

    Distinct from "the window is genuinely empty" — that is an empty list. A caller must never
    treat this as "no ticks here": silently continuing would swap a real price path for a guess
    without saying so.
    """


class Tick:
    """One bid/ask quote. __slots__ because a busy hour is ~30k of these."""

    __slots__ = ("ms", "bid", "ask")

    def __init__(self, ms: int, bid: float, ask: float):
        self.ms = ms
        self.bid = bid
        self.ask = ask

    @property
    def spread(self) -> float:
        return self.ask - self.bid

    def __repr__(self) -> str:  # pragma: no cover - debug aid
        return f"Tick({self.ms}, bid={self.bid}, ask={self.ask})"


def _safe(token: str) -> str:
    return re.sub(r"[^A-Za-z0-9]+", "_", token).strip("_")


def _hour_floor(ms: int) -> int:
    return ms - (ms % 3_600_000)


def _iso(ms: int) -> str:
    return _dt.datetime.utcfromtimestamp(ms / 1000.0).isoformat()


def _to_ms(t: _dt.datetime) -> int:
    return int(t.replace(tzinfo=_dt.timezone.utc).timestamp() * 1000)


class TickCache:
    """On-disk tick buckets, one JSON file per (symbol, UTC hour).

    Carries the same FEED_VERSION guard as the bar cache and for the same reason: these timestamps
    came through the agent's broker-clock conversion, so a bucket written before that fix means
    something different from one written after. A stale bucket reads as a MISS (re-fetch), never as
    data — see backtest/data/cache.py for the incident this prevents.
    """

    def __init__(self, cache_dir: str | os.PathLike | None = None):
        base = Path(cache_dir) if cache_dir is not None else _default_cache_dir()
        self.dir = base / "ticks"

    def path(self, symbol: str, hour_ms: int) -> Path:
        stamp = _dt.datetime.utcfromtimestamp(hour_ms / 1000.0).strftime("%Y%m%dT%H")
        return self.dir / f"{_safe(symbol)}__{stamp}.json"

    def load(self, symbol: str, hour_ms: int) -> Optional[List[Tick]]:
        """Cached ticks for the hour, or None on a miss/stale bucket. An empty LIST is a real
        cached answer (a genuinely tickless hour) and is distinct from None."""
        p = self.path(symbol, hour_ms)
        if not p.is_file():
            return None
        try:
            blob = json.loads(p.read_text())
        except (ValueError, OSError):
            return None
        if int(blob.get("feed_version", 1)) != FEED_VERSION:
            return None
        return [Tick(int(ms), float(b), float(a)) for ms, b, a in blob.get("ticks", [])]

    def save(self, symbol: str, hour_ms: int, ticks: Sequence[Tick]) -> None:
        self.dir.mkdir(parents=True, exist_ok=True)
        blob = {
            "feed_version": FEED_VERSION,
            "hour": _iso(hour_ms),
            "ticks": [[t.ms, t.bid, t.ask] for t in ticks],
        }
        tmp = self.path(symbol, hour_ms).with_suffix(".tmp")
        tmp.write_text(json.dumps(blob, separators=(",", ":")))
        tmp.replace(self.path(symbol, hour_ms))  # atomic: never leave a half-written bucket


class TickSource:
    """Lazy, cache-backed tick windows.

    `window(symbol, start_ms, end_ms)` returns the ticks in [start_ms, end_ms), fetching only the
    hour buckets it needs and caching each whole. Ask for the smallest window that answers the
    question — a bar, not a day.
    """

    def __init__(self, agent, cache: TickCache | None = None):
        self.agent = agent
        self.cache = cache if cache is not None else TickCache()

    def window(self, symbol: str, start_ms: int, end_ms: int) -> List[Tick]:
        if end_ms <= start_ms:
            return []
        out: List[Tick] = []
        hour = _hour_floor(start_ms)
        while hour < end_ms:
            for t in self._bucket(symbol, hour):
                if start_ms <= t.ms < end_ms:
                    out.append(t)
            hour += 3_600_000
        out.sort(key=lambda t: t.ms)
        return out

    def _bucket(self, symbol: str, hour_ms: int) -> List[Tick]:
        cached = self.cache.load(symbol, hour_ms)
        if cached is not None:
            return cached
        try:
            raw = self.agent.ticks(symbol, _iso(hour_ms), _iso(hour_ms + 3_600_000))
        except Exception as exc:  # agent down / refused / HTTP
            raise TickWindowUnavailable(
                f"ticks unavailable for {symbol} hour {_iso(hour_ms)}: {exc}"
            ) from exc
        ticks = [
            Tick(_to_ms(_dt.datetime.fromisoformat(r["time"])), float(r["bid"]), float(r["ask"]))
            for r in raw
        ]
        ticks.sort(key=lambda t: t.ms)
        self.cache.save(symbol, hour_ms, ticks)  # empty is cached too — a real, reusable answer
        return ticks
