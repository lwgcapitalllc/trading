"""The status file must never be readable in a half-written state.

**Why this file exists.** `bot_state.json` had been written with `open(path, "w")` since the
beginning, which EMPTIES the file and only then refills it. Four separate things read that file
— the dead-man's switch, the process watchdog, the Telegram bot and the Command Center — and
any of them landing inside that window gets a truncated or zero-byte file.

**It cost a false alarm on 2026-08-22 at 03:50 UTC**: the dead-man's switch sent `/fail` saying
*"bot_state.json cannot be read"* and cleared on its next pass five minutes later, while the bot
itself never missed a heartbeat (`health-2026-08-22.jsonl`, pulses at 03:41 and 03:56).

**The alarm was the small half.** `_load_instance_state` swallows the parse error and returns
`{}`, so a `write_bot` landing in that window rebuilds the entry from defaults and saves —
wiping the other bot's entry and this bot's own fields as it goes. That is why the guarantee
being tested is *a reader only ever sees a complete file*, rather than *each reader retries*.

**Watched RED.** Both cases were run against HEAD before the fix landed:
  - `test_reader_never_sees_a_partial_file` — 1,195 unreadable reads out of 6,965.
  - `test_a_crash_mid_write_leaves_the_previous_record_intact` — `JSONDecodeError`, empty file.
Both pass on the fix. The second is the deterministic one and is what keeps this file honest if
the concurrent one ever gets quiet; the first is the one that reproduces what actually happened.
"""

from __future__ import annotations

import importlib.util
import json
import sys
import threading
import time
from pathlib import Path

import pytest

_REPO = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(_REPO / "algos" / "shared"))

_spec = importlib.util.spec_from_file_location(
    "bot_state_under_test", _REPO / "algos" / "shared" / "bot_state.py"
)
bs = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(bs)


def _record(pad: int = 400) -> dict:
    """A state blob big enough that a truncating write has a window worth catching.

    ⚠ The padding is not decoration. A record small enough to land in one filesystem write
    would make a truncate-in-place LOOK atomic on a fast disk, and this file would then pass
    against the bug it exists to catch — the fixture-more-capable-than-production shape.
    """
    return {
        "mpc_sos_fade_demo": {
            "status": "running",
            "heartbeat": 1787000000.0,
            "started": 1786000000.0,
            "account": "700152905",
            "balance": 9996.99,
            "mt5_link": True,
            "day_locked": False,
            "pad": "y" * pad,
        },
        "mpc_bleg_demo": {"status": "stopped", "account": None},
    }


def test_reader_never_sees_a_partial_file(tmp_path):
    """A reader hammering the file while it is rewritten must never fail to parse it.

    This is the incident itself. Against the truncating write it fails on the first few
    hundred reads; there is no timing to tune.
    """
    state = _record()
    bs._save_instance_state(tmp_path, state)
    path = tmp_path / "bot_state.json"

    stop = threading.Event()
    write_errors: list[BaseException] = []

    def writer():
        while not stop.is_set():
            try:
                bs._save_instance_state(tmp_path, state)
            except BaseException as exc:  # noqa: BLE001 - reported, not swallowed
                write_errors.append(exc)
                return

    t = threading.Thread(target=writer, daemon=True)
    t.start()
    try:
        unreadable, reads, deadline = 0, 0, time.time() + 2.0
        while time.time() < deadline:
            reads += 1
            try:
                got = json.loads(path.read_text())
            except Exception:
                unreadable += 1
                continue
            # Complete is not enough — it must also be the RIGHT record, so a writer that
            # published an empty-but-valid `{}` could not pass.
            assert got["mpc_sos_fade_demo"]["balance"] == 9996.99
            assert got["mpc_bleg_demo"]["status"] == "stopped"
    finally:
        stop.set()
        t.join(timeout=5)

    assert not write_errors, f"the writer itself failed: {write_errors[0]!r}"
    assert reads > 500, f"only {reads} reads - too few to have exercised the race"
    assert unreadable == 0, f"{unreadable} of {reads} reads got a half-written file"


def test_a_crash_mid_write_leaves_the_previous_record_intact(tmp_path, monkeypatch):
    """A write that dies partway through must not destroy the record already on disk.

    The deterministic half. A truncating write has already emptied the file by the time
    serialisation runs, so the previous record is gone whatever happens next.
    """
    first = _record()
    bs._save_instance_state(tmp_path, first)
    path = tmp_path / "bot_state.json"

    real_dump = json.dump

    def dump_then_die(obj, fp, **kw):
        real_dump(obj, fp, **kw)
        fp.flush()
        raise OSError("disk full")

    monkeypatch.setattr(bs.json, "dump", dump_then_die)

    second = _record()
    second["mpc_sos_fade_demo"]["balance"] = 1.23
    with pytest.raises(OSError):
        bs._save_instance_state(tmp_path, second)

    got = json.loads(path.read_text())
    assert got["mpc_sos_fade_demo"]["balance"] == 9996.99, "the good record was overwritten"


def test_a_failed_write_leaves_no_temp_file_behind(tmp_path, monkeypatch):
    """A litter check. An instance dir filling with scratch files is how a disk quietly fills.

    ⚠ It asserts on what is left in the DIRECTORY, not on the temp file's name — a test that
    pins the naming scheme would go red on a rename that broke nothing.
    """
    bs._save_instance_state(tmp_path, _record())

    def dump_then_die(obj, fp, **kw):
        raise OSError("disk full")

    monkeypatch.setattr(bs.json, "dump", dump_then_die)
    with pytest.raises(OSError):
        bs._save_instance_state(tmp_path, _record())

    assert [p.name for p in tmp_path.iterdir()] == ["bot_state.json"]


def test_two_writers_do_not_publish_each_others_bytes(tmp_path):
    """Concurrent writers must not share a scratch file.

    ⚠ This is the same defect one level down and it is the reason the temp name carries the
    PID. It cannot go red in-process (one PID), so it is pinned structurally: two writes from
    different PIDs must not name the same scratch path.
    """
    seen = []

    real_replace = bs.os.replace

    def capture(src, dst):
        seen.append(str(src))
        return real_replace(src, dst)

    bs.os.replace = capture
    try:
        bs._save_instance_state(tmp_path, _record())
        real_getpid = bs.os.getpid
        bs.os.getpid = lambda: real_getpid() + 1
        try:
            bs._save_instance_state(tmp_path, _record())
        finally:
            bs.os.getpid = real_getpid
    finally:
        bs.os.replace = real_replace

    assert len(seen) == 2
    assert seen[0] != seen[1], "two processes would write to the same scratch file"
