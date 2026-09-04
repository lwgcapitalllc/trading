"""The warm-up must not write its replay into the live decision ledger.

🔴 **The defect this file exists for, found 2026-08-05 by reading the live record.**
`LiveRunner.warm()` replays ~5,000 bars of history through the strategy to build engine state.
`execution.step()` appends every blocked and missed setup it sees to `execution.blocks` /
`.misses`, and it cannot tell a replay from a live bar — it is the same object either way,
which is the property that earns Pine parity and is not going to change. Nothing cleared those
lists at the end of the warm-up, so `_drain_records()` wrote the whole accumulation on the
**first live bar**, stamped with the live timestamp.

**MEASURED on the real ledger before the fix, and it was not a corner case — it was all of it:**

| day | blocked+missed rows | from that day | duplicate rows | starts |
|---|---|---|---|---|
| 2026-07-31 | 122 | **0** | 81 | 3 |
| 2026-08-04 | 217 | **0** | 171 | 5 |
| 2026-08-05 | 221 | **0** | 178 | 5 |

Ages ran 6 to 75 days. The duplicates are there because every restart re-dumps the same
warm-up, so a setup from May was written once per start.

⚠ **Why it matters more than a noisy log: this is the only record of a refusal that exists.**
No broker statement contains a trade that was declined. `algos/tools/ledger_sync.py` commits
this file precisely because it is the sole copy — and "what did the bot refuse today" was
answerable only by comparing each row's own `bar_time` against its `ts`, which nothing did.

⚠ **It never affected trading.** `blocks`/`misses` are reporting-only; nothing reads a record
back, and `bridge.sync` is driven by the decision object, not by these lists.

The fix DISCARDS rather than tags: a warm-up setup is not a decision this bot made, it is
history it replayed to build state, and a backtest already reports it properly. The count goes
onto the `warmed` event so a drop to zero is visible rather than silent.
"""

from __future__ import annotations

import sys
import types
from pathlib import Path
from types import SimpleNamespace

import pandas as pd

# MetaTrader5 is Windows-only and imported lazily. A stub keeps this runnable on the Mac.
sys.modules.setdefault(
    "MetaTrader5",
    types.SimpleNamespace(
        TIMEFRAME_M1=1,
        TIMEFRAME_M5=5,
        TIMEFRAME_M15=15,
        TIMEFRAME_M30=30,
        TIMEFRAME_H1=60,
        TIMEFRAME_H4=240,
        TIMEFRAME_D1=1440,
    ),
)

_REPO = Path(__file__).resolve().parent.parent.parent
for _p in (str(_REPO), str(_REPO / "algos" / "live"), str(_REPO / "algos" / "shared")):
    if _p not in sys.path:
        sys.path.insert(0, _p)

from runner import LiveRunner  # noqa: E402


class _Execution:
    """Stands in for the strategy's Execution: it accumulates and never prunes, which is
    correct for a backtest and is exactly what makes the live warm-up dangerous."""

    def __init__(self):
        self.blocks, self.misses = [], []
        self.bar_ms = 0

    def step(self, sig, seq):
        self.blocks.append(f"blocked@{len(self.blocks)}")
        self.misses.append(f"missed@{len(self.misses)}")
        return SimpleNamespace()


class _Ledger:
    def __init__(self):
        self.events, self.blocked, self.missed = [], [], []

    def event(self, name, **kw):
        self.events.append((name, kw))

    def blocked_(self, b):  # pragma: no cover - name kept distinct from the list
        self.blocked.append(b)


def _warmed_runner(monkeypatch, bars=300):
    """A LiveRunner with only `warm()`'s collaborators wired.

    `__new__` rather than `__init__`: a real one imports the strategy package and opens a log
    file, and none of this behaviour depends on either.
    """
    r = LiveRunner.__new__(LiveRunner)
    ex = _Execution()
    r.strategy = SimpleNamespace(
        execution=ex,
        signals=SimpleNamespace(update=lambda s: SimpleNamespace()),
        sequence=SimpleNamespace(update=lambda s: SimpleNamespace()),
        engine_config=lambda: {},
    )
    r.ledger = _Ledger()
    r.log = SimpleNamespace(
        info=lambda *a, **k: None, warning=lambda *a, **k: None, error=lambda *a, **k: None
    )
    r.cfg = SimpleNamespace(warmup_bars=bars, timeframe="M15", symbol="XAUUSD.s")

    idx = pd.date_range("2026-05-01", periods=bars, freq="15min", tz="UTC")
    df = pd.DataFrame(
        {"open": 1.0, "high": 2.0, "low": 0.5, "close": 1.5, "volume": 1.0}, index=idx
    )
    r.feed = SimpleNamespace(history=lambda n: df, mark_seen=lambda d: None, bar_seconds=900)
    # No re-entry, so no second bar stream — `warm()` builds the degenerate `_SingleFeedClock`
    # and the fast half of it is never reached. Set explicitly rather than left off: a missing
    # attribute and a deliberate "this bot has one feed" must not be the same thing.
    r.fast_feed = None
    r._fast_pending = []

    # `warm()` imports these from backtest.replay at call time.
    import backtest.replay as replay

    monkeypatch.setattr(
        replay, "EngineStack", lambda cfg: SimpleNamespace(step=lambda bar: SimpleNamespace())
    )
    monkeypatch.setattr(
        replay, "iter_bars", lambda d: [SimpleNamespace(index=i) for i in range(len(d))]
    )
    return r, ex


def test_the_warmup_leaves_no_setups_for_the_first_live_bar_to_write(monkeypatch):
    """THE regression, stated as the thing that was wrong: after warming, the strategy must be
    holding nothing, so `_drain_records()` on the first live bar writes nothing."""
    r, ex = _warmed_runner(monkeypatch, bars=300)
    r.warm()

    assert ex.blocks == [], "300 bars of replayed refusals are queued for the live ledger"
    assert ex.misses == [], "300 bars of replayed misses are queued for the live ledger"


def test_the_discarded_count_is_reported_not_silent(monkeypatch):
    """A silent drop is how somebody later 'tidies up' the clear and nobody notices, and it is
    equally how a strategy that stopped recording refusals goes unseen. The number rides on the
    `warmed` event both ways."""
    r, ex = _warmed_runner(monkeypatch, bars=300)
    r.warm()

    warmed = [kw for name, kw in r.ledger.events if name == "warmed"]
    assert len(warmed) == 1
    assert warmed[0]["replayed_setups"] == 600, "300 blocked + 300 missed"
    assert warmed[0]["bars"] == 300


def test_a_second_warm_does_not_re_queue_the_first_ones(monkeypatch):
    """Every restart re-warms, and the duplicates are what made the real record unusable —
    5 starts on 2026-08-05 wrote every historical setup 5 times."""
    r, ex = _warmed_runner(monkeypatch, bars=300)
    r.warm()
    r.warm()

    assert ex.blocks == [] and ex.misses == []
    counts = [kw["replayed_setups"] for name, kw in r.ledger.events if name == "warmed"]
    assert counts == [600, 600], "a re-warm must report its own replay, not a running total"


def test_a_strategy_without_the_lists_is_not_a_crash(monkeypatch):
    """`b_leg` overrides `_place_entries` and records nothing by construction, and a future
    strategy may too. The clear is defensive on purpose — an AttributeError here would take out
    the warm-up, i.e. kill the bot at startup over a reporting field."""
    r, ex = _warmed_runner(monkeypatch, bars=300)  # 200 is warm()'s own floor
    del ex.blocks
    del ex.misses
    ex.step = lambda sig, seq: SimpleNamespace()

    r.warm()  # must not raise
    warmed = [kw for name, kw in r.ledger.events if name == "warmed"]
    assert warmed[0]["replayed_setups"] == 0
