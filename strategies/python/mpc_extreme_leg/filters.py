"""The two cuts TradingView cannot make.

🔴 **NEITHER OF THESE HAS A PINE COUNTERPART AND NEITHER EVER WILL.** `engines/regime/` and
`engines/news/` have no Pine source by construction — they are not ports of anything — so no
input, no `cfg_*` column, and nothing a parity gate could ever check. Both cuts default OFF, and
`tools/compare_extreme_leg.py` REFUSES to run with either on. **That refusal is the only reason
this file is allowed to exist**: without it, a gate would compare a filtered Python against an
unfiltered Pine, report a disagreement per refused setup, and send the reader at the wrong code.

⚠ **This is a CONSUMER of two canonical engines, never a second implementation.** Both are
imported by their bare public names, the same seam every other consumer here uses.

⚠ **Each cut is asked only when a setup is about to be taken**, not once per bar. Over eight years
of 5-minute gold that is a few hundred questions rather than half a million, and the classifier
walks its whole frame on every call. Doing it per bar was measured to be the difference between a
one-minute replay and an all-afternoon one.

🔴 **"CANNOT ASK" AND "NO" ARE DIFFERENT ANSWERS AND ARE KEPT DIFFERENT.** Both cuts return a
three-way answer, never a bool: REFUSE, ALLOW, or UNKNOWN. An UNKNOWN allows the trade — a filter
that refused whenever it could not see would silently become a different strategy on any day its
data was thin — but it is COUNTED, and the count is on the strategy so a caller can read it. A
filter that could not answer once in eight years and one that could not answer nine thousand times
must not look the same from outside.

🔴 **EACH CUT COUNTS HOW OFTEN IT WAS ASKED, NOT ONLY HOW OFTEN IT SAID NO.** Without that, a cut
that was never wired up and a cut that was asked two hundred times and allowed every one produce
the same output: a run identical to the baseline with a zero beside it. That happened on the first
run of this file and the numbers looked perfectly reasonable. **`asked` is the field that tells
you the thing is connected**; `refused` is the field that tells you it did something.
"""

from __future__ import annotations

import sys
from collections import deque
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[3]
# ⚠ `engines/` itself, not the two engine folders. `engines/regime/classifier.py` does
# `from . import thresholds`, so it must be imported AS a package — putting `engines/regime/` on
# the path makes `import classifier` succeed and then fail on its own relative import, which reads
# as a broken engine rather than a wrong path. This is the seam `algos/shared/shared_regime.py`
# already uses. `engines/news/` is imported the same way for consistency, by its bare public name.
_ENGINES = _ROOT / "engines"
if str(_ENGINES) not in sys.path:
    sys.path.insert(0, str(_ENGINES))

REFUSE, ALLOW, UNKNOWN = "REFUSE", "ALLOW", "UNKNOWN"

# The classifier needs 34 rows of each frame (`engines/regime/thresholds.py`). This is that with
# room to spare, and it bounds the memory a replay carries. It is NOT a tuning knob — a longer
# window would change the ADX and ATR readings and therefore the labels.
_KEEP = 120


class TransitioningCut:
    """Refuse a setup while `engines/regime/` calls the market TRANSITIONING.

    ⚠ **Which two frames it reads is a CHOICE and is recorded as one.** The classifier takes a
    short frame and a long one; this passes the strategy's OWN two — the 5-minute bars it trades
    and the 15-minute bars it already aggregates for its targets. Nothing else was available
    without giving the strategy a second data source, and a strategy that quietly loads its own
    bars is a strategy whose backtest and live runs can differ.
    """

    def __init__(self) -> None:
        self._short: deque = deque(maxlen=_KEEP)
        self._long: deque = deque(maxlen=_KEEP)
        self.asked = 0
        self.refused = 0
        self.unknown_count = 0

    def on_bar(self, o: float, h: float, low: float, c: float) -> None:
        self._short.append((o, h, low, c))

    def on_htf_bar(self, o: float, h: float, low: float, c: float) -> None:
        self._long.append((o, h, low, c))

    def ask(self) -> str:
        # Imported here rather than at module scope: this module is imported by the package's
        # __init__, and pandas plus the classifier cost real time on a lab that scans every
        # strategy package at startup whether or not a run is coming.
        import pandas as pd
        from regime import classify_regime

        self.asked += 1
        if len(self._short) < 34 or len(self._long) < 34:
            self.unknown_count += 1
            return UNKNOWN

        cols = ["open", "high", "low", "close"]
        label = classify_regime(
            pd.DataFrame(list(self._short), columns=cols),
            pd.DataFrame(list(self._long), columns=cols),
        )
        if label == "UNKNOWN":
            self.unknown_count += 1
            return UNKNOWN
        if label == "TRANSITIONING":
            self.refused += 1
            return REFUSE
        return ALLOW


class NewsCut:
    """Refuse a setup inside a macro-release blackout, per `engines/news/`.

    🔴 **AN EMPTY CALENDAR IS `UNKNOWN`, NEVER `ALLOW`, AND THAT IS THE WHOLE POINT.** The news
    engine reports `has_coverage=False` outside the dates it holds and blacks out nothing there —
    deliberately, so a backtest trades normally where there is no data rather than guessing. Read
    as a bool that is indistinguishable from "checked, and nothing was due", which is precisely
    how a stale calendar cache made the lab's news filter look active for a month while filtering
    nothing (2026-09-01). Here the two are separate answers and the uncovered ones are counted.

    ⚠ **The cache is git-ignored and per-machine.** With no cache at all this cut is inert and
    says so through its count, rather than refusing every setup or allowing every one in silence.
    """

    def __init__(self, before_min: int, after_min: int, symbol: str) -> None:
        self._before, self._after, self._symbol = before_min, after_min, symbol
        self._engine = None
        self._built = False
        self.asked = 0
        self.refused = 0
        self.unknown_count = 0
        self.no_calendar = False

    def _build(self):
        from news import EventStore, Impact, NewsEngine, NewsPolicy

        # ⚠ `load()` returns BOTH the events and the ranges they cover, and the second half is the
        # half that matters here — it is what lets an uncovered date answer UNKNOWN rather than
        # "nothing due". Dropping it would make this cut silently inert outside the cached dates.
        events, covered = EventStore().load()
        if not events:
            self.no_calendar = True
            return None
        # ⚠ High-impact USD, because gold is a USD macro instrument. This mirrors the lab's own
        # tagging policy in `command-center/backend/services/news_filter.py` — it is NOT imported
        # from there: `strategies/` may not depend on `command-center/`. If that policy changes,
        # this one does not follow automatically, and that is a known seam rather than a bug.
        # ⚠ Holidays are blocked too, matching the lab and Aaron's standing always-avoid rule.
        policy = NewsPolicy(
            currencies=frozenset(("USD",)),
            min_impact=Impact.HIGH,
            pre_minutes=self._before,
            post_minutes=self._after,
            block_holidays=True,
        )
        return NewsEngine(events, policy=policy, covered_ranges=covered)

    def ask(self, bar_index: int, timestamp_ms: int) -> str:
        self.asked += 1
        if not self._built:
            self._engine = self._build()
            self._built = True
        if self._engine is None:
            self.unknown_count += 1
            return UNKNOWN
        ev = self._engine.update(bar_index, timestamp_ms)
        if not ev.has_coverage:
            self.unknown_count += 1
            return UNKNOWN
        if ev.in_blackout:
            self.refused += 1
            return REFUSE
        return ALLOW
