"""A setup that has had its re-entry stays USED across a live restart and a feed re-warm.

🔴 2026-10-02: both SOS Fade bots took a SECOND re-entry on one setup. The 08:17 re-entry on the
05:00 long used its one allowed re-entry; a restart at 15:52 and a feed re-warm at 22:15 rebuilt
the re-entry's state empty (the live warm-up does not replay it), and a trigger at 00:46 the next
day fired the same setup again. These pin the runner half: the memory is WRITTEN when it changes
and PUT BACK after every rebuild of the fast side. The strategy half is pinned in
`strategies/python/sos_fade/tests/test_secondary.py`.
"""

from __future__ import annotations

import sys
import types
from pathlib import Path
from types import SimpleNamespace

sys.modules.setdefault("MetaTrader5", types.SimpleNamespace(TIMEFRAME_M1=1, TIMEFRAME_M15=15))

_REPO = Path(__file__).resolve().parent.parent.parent
for p in (str(_REPO), str(_REPO / "algos" / "live"), str(_REPO / "algos" / "shared")):
    if p not in sys.path:
        sys.path.insert(0, p)

import position_state  # noqa: E402
from runner import LiveRunner  # noqa: E402


class _Clock:
    """Holds a memory the way `DualClock` does: a rebuild empties it, a restore fills it."""

    def __init__(self):
        self.memory = {}
        self.resets = 0

    def snapshot_reentry_memory(self):
        return dict(self.memory)

    def restore_reentry_memory(self, record):
        if not record:
            return 0
        self.memory = dict(record)
        return len(record)

    def reset_fast(self):
        self.memory = {}
        self.resets += 1


class _Log:
    def __init__(self):
        self.lines = []

    def info(self, m):
        self.lines.append(m)

    warning = error = info


class _Ledger:
    def __init__(self):
        self.rows = []

    def event(self, kind, **kw):
        self.rows.append((kind, kw))


def _runner(tmp_path, clock=None):
    r = LiveRunner.__new__(LiveRunner)
    r.cfg = SimpleNamespace(instance_dir=tmp_path)
    r.clock = clock or _Clock()
    r.log, r.ledger = _Log(), _Ledger()
    r.fast_feed = object()
    r._warm_fast = lambda: None
    return r


def test_the_memory_is_written_when_it_changes_and_put_back_on_a_RESTART(tmp_path):
    """The 15:52 restart. MUTATION: make `_restore_reentry_memory` pass `None` to the clock -> the
    new process starts empty. The two CALL SITES are pinned by the source test below."""
    before = _runner(tmp_path)
    before.clock.memory = {"arm": {"l": {"used_ms": 1_790_830_800_000, "used_n": 1}}}
    before._save_reentry_memory()
    assert position_state.read_reentry_memory(tmp_path) == before.clock.memory

    after = _runner(tmp_path)  # a new process, a new empty clock
    after._restore_reentry_memory()
    assert after.clock.memory == before.clock.memory
    assert [k for k, _ in after.ledger.rows] == ["reentry_memory_restored"]


def test_a_FEED_RE_WARM_puts_the_memory_back_after_emptying_it(tmp_path):
    """The 22:15 re-warm, which needs no restart at all. MUTATION: drop the restore in
    `_rewarm_fast` -> red."""
    r = _runner(tmp_path)
    r.clock.memory = {"arm": {"l": {"used_ms": 5, "used_n": 1}}}
    r._save_reentry_memory()
    r._rewarm_fast()
    assert r.clock.resets == 1
    assert r.clock.memory == {"arm": {"l": {"used_ms": 5, "used_n": 1}}}


def test_an_unchanged_memory_is_not_rewritten_every_bar(tmp_path):
    r = _runner(tmp_path)
    r.clock.memory = {"arm": {"l": {"used_ms": 5, "used_n": 1}}}
    r._save_reentry_memory()
    path = tmp_path / position_state.REENTRY_MEMORY_FILENAME
    path.write_text('{"memory": {"arm": "sentinel"}}')  # would be overwritten by a write
    r._save_reentry_memory()
    assert "sentinel" in path.read_text(), "rewrote an unchanged memory"


def test_a_missing_or_torn_record_restores_nothing_and_never_raises(tmp_path):
    """Rule 1 the safe way round: no record is the behaviour before this existed."""
    r = _runner(tmp_path)
    r._restore_reentry_memory()
    assert r.clock.memory == {}
    (tmp_path / position_state.REENTRY_MEMORY_FILENAME).write_text("{not json")
    r._restore_reentry_memory()
    assert r.clock.memory == {}


def test_a_bot_whose_clock_has_no_re_entry_memory_is_left_alone(tmp_path):
    r = _runner(tmp_path, clock=SimpleNamespace())
    r._save_reentry_memory()
    r._restore_reentry_memory()
    assert not (tmp_path / position_state.REENTRY_MEMORY_FILENAME).exists()


def test_every_fast_rebuild_restores_and_every_fast_bar_saves():
    """The call sites, read off the source — a restore nobody calls is the 2026-10-02 bug again.
    MUTATION: delete the restore in `warm()` or the save in `_observe_secondary` -> red."""
    import inspect

    warm = inspect.getsource(LiveRunner.warm)
    assert warm.index("self._restore_reentry_memory()") > warm.index("self._warm_fast()")
    assert "self._restore_reentry_memory()" in inspect.getsource(LiveRunner._rewarm_fast)
    assert "self._save_reentry_memory()" in inspect.getsource(LiveRunner._observe_secondary)
