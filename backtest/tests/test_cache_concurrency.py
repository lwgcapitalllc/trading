"""Two writers must not be able to damage the bar cache.

🔴 **These are regression tests for a real incident, twice on 2026-08-06.** Two backtests wrote
`XAUUSD__M1.csv` at once and produced 2.59M rows that claimed to be one sorted history and
contained two, spliced mid-timestamp; earlier the same day the M15 file quietly lost ~31,000 rows
out of its middle while `ranges.json` still claimed the whole span, so nothing would ever have
re-fetched them.

⚠ **The writers here are real SUBPROCESSES, not threads or mocks, and that is the test.** The
thing being protected against is two `python` processes — a backtest and a chart build, or two
sessions — and a threading-only reproduction would pass against a threading-only fix while the
actual failure mode stayed wide open. `subprocess` also costs nothing in fidelity: it is exactly
how the corruption was produced.
"""

from __future__ import annotations

import json
import subprocess
import sys
import textwrap
from pathlib import Path

import pandas as pd
import pytest

from backtest.data.atomic import atomic_write_csv, atomic_write_text, cache_lock
from backtest.data.cache import BarCache

REPO = str(Path(__file__).resolve().parents[2])

# Big enough that the read-merge-write takes long enough to interleave. Measured against the
# unlocked code: 5 writers x 250k rows reproduces BOTH failures against HEAD — the splice (rows out of order) and the lost span (250k of 1.25M survive). A handful of
# rows would pass on broken code by finishing too fast to overlap, which is the vacuous-test trap
# this repo keeps recording — a green new test proves nothing until you have seen it red.
_WRITERS = 5
_ROWS_EACH = 250_000

_CHILD = textwrap.dedent(
    """
    import sys
    sys.path.insert(0, {repo!r})
    import pandas as pd
    from backtest.data.cache import BarCache

    which = int(sys.argv[1])
    rows = {rows}
    start = pd.Timestamp("2020-01-01") + pd.Timedelta(minutes=which * rows)
    idx = pd.date_range(start, periods=rows, freq="1min")
    df = pd.DataFrame(
        {{"open": 1.0, "high": 2.0, "low": 0.5, "close": 1.5}}, index=idx
    )
    df.index.name = "time"
    BarCache({cache!r}).save("XAUUSD", "M1", df)
    """
)


def _run_writers(cache_dir: Path, n: int = _WRITERS) -> None:
    """Fire `n` independent processes that each save a DISJOINT span into one cache entry."""
    src = _CHILD.format(repo=REPO, rows=_ROWS_EACH, cache=str(cache_dir))
    procs = [subprocess.Popen([sys.executable, "-c", src, str(i)]) for i in range(n)]
    for p in procs:
        assert p.wait(timeout=300) == 0, "a writer subprocess failed"


@pytest.fixture(scope="module")
def contended_cache(tmp_path_factory):
    """One contended write, shared by the three tests that assert on its outcome.

    ⚠ **The writers are the EVENT; the three tests are three properties of one outcome.** Each used
    to fire its own set — 5 processes x 250,000 rows, MEASURED at ~28s a test, 86s for the file —
    to produce a cache it then examined from one angle. Firing it once and asserting three times
    covers exactly the same ground.

    ⚠ **Scoped to the MODULE, so the three share one collision rather than getting one each.** The
    cost of that, stated plainly: a racy test run three times has three chances to catch an
    intermittent regression, and this has one. It is acceptable HERE because the reproduction is
    STRUCTURAL rather than lucky — 250,000 rows makes the read-merge-write window enormous, which
    is why that size was measured in the first place, and against the unlocked code both failures
    appear on every run. ⚠ **If `_ROWS_EACH` is ever reduced, this goes back to per-test.**
    """
    d = tmp_path_factory.mktemp("contended")
    _run_writers(d)
    return d


def test_concurrent_writers_leave_a_readable_cache(contended_cache):
    """The file still parses, and every timestamp is unique and in order.

    Against the unlocked code this fails at `read_csv`: the splice leaves a clipped token like
    `6-17 07:47:00` where a timestamp should be, which is exactly what three real quarter fetches
    died on.
    """
    raw = pd.read_csv(contended_cache / "XAUUSD__M1.csv", parse_dates=["time"])
    assert raw["time"].is_monotonic_increasing, "rows are out of order — two frames were spliced"
    assert not raw["time"].duplicated().any()


def test_concurrent_writers_lose_nobodys_bars(contended_cache):
    """Every writer's span survives.

    This is the half a valid-looking file does NOT give you. Atomic writes alone make the result
    parse cleanly while one writer's whole fetch is silently gone — the M15 shape, where the cache
    reads fine and simply holds less than it claims.
    """
    bars = BarCache(contended_cache).load("XAUUSD", "M1")
    assert len(bars) == _WRITERS * _ROWS_EACH, (
        f"expected {_WRITERS * _ROWS_EACH} bars, found {len(bars)} — "
        "a writer's span was overwritten by another's"
    )
    for which in range(_WRITERS):
        first = pd.Timestamp("2020-01-01") + pd.Timedelta(minutes=which * _ROWS_EACH)
        assert first in bars.index, f"writer {which}'s span is missing entirely"


def test_a_failed_write_leaves_the_previous_file_intact(tmp_path):
    """A write that dies partway must not damage what was already there.

    The temp-file-then-replace shape is what guarantees it; writing in place would leave the
    reader whatever bytes happened to land before the failure.
    """
    target = tmp_path / "thing.csv"
    atomic_write_text(target, "original\n")

    class Exploding(pd.DataFrame):
        def to_csv(self, *a, **k):
            raise RuntimeError("disk full")

    with pytest.raises(RuntimeError):
        atomic_write_csv(target, Exploding())

    assert target.read_text() == "original\n"
    assert not list(tmp_path.glob("*.tmp.*")), "a temp file was left behind"


def test_the_lock_is_reentrant_within_one_process(tmp_path):
    """`BarSource._load_base` holds the lock across save+record while `save` takes it again.

    `flock` is per file DESCRIPTOR, so a nested acquire through a fresh fd deadlocks against the
    lock its own process already holds. Without the depth count this test hangs rather than fails,
    which is why it is worth pinning explicitly.
    """
    with cache_lock(tmp_path, "XAUUSD", "M1"):
        with cache_lock(tmp_path, "XAUUSD", "M1"):
            pass
    # And the lock is genuinely released afterwards, rather than left held by the depth count.
    with cache_lock(tmp_path, "XAUUSD", "M1"):
        pass


def test_different_cache_entries_do_not_block_each_other(tmp_path):
    """The lock is per (symbol, timeframe). One entry's writer must not stall another's —
    otherwise a long M1 fetch would freeze every unrelated backtest on the box."""
    with cache_lock(tmp_path, "XAUUSD", "M1"):
        with cache_lock(tmp_path, "GBPUSD", "M15"):
            pass


def test_the_meta_sidecar_survives_concurrent_writers(contended_cache):
    """A half-written sidecar reads as feed version 1, which silently invalidates the whole file
    and triggers a full re-pull — loud in cost, silent in cause."""
    meta = json.loads((contended_cache / "XAUUSD__M1.meta.json").read_text())
    assert meta["feed_version"] == 3
