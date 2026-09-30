"""setup_feed.py — every setup a strategy reports, stamped with the bar it reported it on.

The POINT-IN-TIME feed a research study reads, so it sees each setup at the bar the strategy itself
learns of it — never from a record written after the setup is over.

🔴 **Why it exists (2026-09-28).** A study said the 1-minute SOS-then-BOS entry on SOS Fade Generic
made +0.26R a trade on GBPJPY after costs; built and run in the lab it made -0.06R. The match-up
found 105 trades only the lab took, averaging -0.34R, 100 of them entering BEFORE the time the
study started watching. The study had read each setup's start from its MISS record, whose zone time
brackets the DEEPEST visit to the zone — known only once the setup is over — so it skipped the early
entries that lose. The write-up is in `docs/SOS_FADE_GENERIC_SPEC.md` → "The lab run".

**It builds nothing new about a setup.** Every row is a `SetupSnapshot` the strategy already emits for
the live alert channel (`backtest/setups.py`), read after each bar exactly as the live runner reads
it. A second tracker here would be a second claim about one setup, and two claims can disagree.

⚠ **Generic by construction.** It drives the strategy through its OWN `run()` and listens on its
execution's `step`, so any strategy that implements the setup contract gets a feed and none has to
be taught to this module. ⚠ **It REFUSES a strategy that cannot answer** — an empty feed from a
strategy with no snapshots would read as a strategy with no setups (root `CLAUDE.md` rule 1).

⚠ **A row's `bar_ms` is the bar's OPEN time and the strategy knows it at that bar's CLOSE.** A study
must not act on a row before `bar_ms` + the bar length — `known_ms` spells that out.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, Dict, Iterable, List, Optional, Tuple

from backtest.setups import SetupSnapshot, implements_contract


@dataclass(frozen=True)
class FeedRow:
    """One setup as the strategy reported it on one bar."""

    index: int  #: the bar's position in the frame that was replayed
    bar_ms: int  #: the bar's OPEN time, UTC ms
    known_ms: int  #: its CLOSE — the first instant the strategy had this row
    snap: SetupSnapshot


@dataclass(frozen=True)
class Episode:
    """One unbroken run of bars on which a setup met a study's condition.

    A setup can meet a condition, stop meeting it and meet it again. Those are separate episodes on
    purpose: that is how the strategy's own 1-minute entry reads its setups — it drops a window the
    15-minute side stops reporting and opens a fresh one, with fresh levels, if it comes back.
    """

    key: str
    rows: Tuple[FeedRow, ...]

    @property
    def first(self) -> FeedRow:
        return self.rows[0]


def replay_setups(strategy, df, warmup: int = 0) -> List[FeedRow]:
    """Replay `df` through `strategy.run()` and return every setup snapshot, bar by bar.

    Snapshots are drained after EVERY bar (warm-up included) so a resolved setup is never re-read,
    and only bars at or after `warmup` are returned — the same split the live runner makes.
    """
    ex = getattr(strategy, "execution", None)
    if ex is None or not implements_contract(ex):
        raise TypeError(
            f"{type(strategy).__name__} does not report its setups (no live_setups(), or it "
            f"declares it cannot), so there is no point-in-time feed to read. That is not a "
            f"strategy with no setups — it is a question this strategy cannot answer."
        )
    if not callable(getattr(ex, "drain_setups", None)):
        raise TypeError(f"{type(ex).__name__} has live_setups() but no drain_setups()")

    times = df.index.values.astype("datetime64[ms]").astype("int64")
    step_ms = int(min(times[1:] - times[:-1])) if len(times) > 1 else 0
    rows: List[FeedRow] = []
    calls = {"n": 0}
    step = ex.step

    def listened(*args, **kwargs):
        out = step(*args, **kwargs)
        i = calls["n"]
        calls["n"] += 1
        snaps = ex.drain_setups()
        if warmup <= i < len(times):  # past the end is caught by the count check below
            t = int(times[i])
            rows.extend(FeedRow(i, t, t + step_ms, s) for s in snaps)
        return out

    ex.step = listened
    try:
        strategy.run(df, warmup=warmup)
    finally:
        del ex.step  # the instance attribute; the class method shows through again
    # The bar time comes from COUNTING steps, so one step per bar is what makes it right. A strategy
    # whose run() steps its execution any other way would stamp every row with the wrong bar.
    if calls["n"] != len(df):
        raise RuntimeError(
            f"{type(strategy).__name__}.run() stepped its execution {calls['n']} times over "
            f"{len(df)} bars, so rows cannot be stamped with their bar. Not a feed."
        )
    return rows


def episodes(rows: Iterable[FeedRow], qualifies: Callable[[SetupSnapshot], bool]) -> List[Episode]:
    """Group `rows` into per-setup runs of CONSECUTIVE bars on which `qualifies` held.

    Ordered by the first bar of each episode. A setup's episode ends on the first bar it is not
    reported or does not qualify.
    """
    open_: Dict[str, List[FeedRow]] = {}
    last_ix: Dict[str, int] = {}
    done: List[Episode] = []
    for r in rows:
        k = r.snap.key
        if not qualifies(r.snap):
            continue
        if k in open_ and last_ix[k] == r.index - 1:
            open_[k].append(r)
        else:
            if k in open_:
                done.append(Episode(k, tuple(open_[k])))
            open_[k] = [r]
        last_ix[k] = r.index
    done.extend(Episode(k, tuple(v)) for k, v in open_.items())
    done.sort(key=lambda e: (e.first.index, e.key))
    return done


def leg_side(leg: Optional[Tuple[float, float]]) -> int:
    """+1 if `(extreme, origin)` is an UP leg (a long's retrace), -1 if down, 0 if none."""
    if leg is None or leg[0] == leg[1]:
        return 0
    return 1 if leg[0] > leg[1] else -1
