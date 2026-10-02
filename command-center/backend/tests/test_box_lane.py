"""The trading box builds one deploy at a time — `services/box_lane.py`.

The lane is an OS file lock because every deploy runs in its OWN process. These pin the two
properties the deploys depend on: a second holder waits and is told whose turn it is, and a
holder that DIES lets the next one in — a crashed deploy may never leave the box shut.
"""

import subprocess
import sys
import threading
import time

from services import box_lane


def test_a_second_holder_waits_and_is_told_who_has_it():
    """MUTATION: drop the blocking `flock` after the non-blocking one fails → red (both hold)."""
    inside = threading.Event()
    release = threading.Event()
    order: list[str] = []
    told: list[str] = []

    def first():
        with box_lane.hold("SOS Fade"):
            inside.set()
            order.append("first in")
            release.wait(5)
            order.append("first out")

    t = threading.Thread(target=first)
    t.start()
    assert inside.wait(5)
    threading.Timer(0.2, release.set).start()
    with box_lane.hold("Realign", on_wait=told.append):
        order.append("second in")
    t.join(5)
    assert told == ["SOS Fade"]
    assert order == ["first in", "first out", "second in"]


def test_a_free_lane_never_calls_on_wait():
    told: list[str] = []
    with box_lane.hold("FFT", on_wait=told.append):
        pass
    assert told == []


def test_a_holder_that_DIES_lets_the_next_one_in(tmp_path, monkeypatch):
    """A deploy's process can be killed mid-build. The OS drops a dead process's `flock`, which is
    the whole reason the lane is one. MUTATION: replace the lock with a marker FILE that is
    deleted on exit → red (the killed holder never deletes it, and this hangs past the limit)."""
    path = tmp_path / "lane.lock"
    monkeypatch.setenv("CC_BOX_LANE_LOCK", str(path))
    holder = subprocess.Popen(
        [
            sys.executable,
            "-c",
            "import fcntl,sys,time\n"
            f"f=open({str(path)!r},'a+'); fcntl.flock(f, fcntl.LOCK_EX); f.write('dead'); "
            "f.flush(); print('held', flush=True); time.sleep(60)",
        ],
        stdout=subprocess.PIPE,
        text=True,
    )
    try:
        assert holder.stdout.readline().strip() == "held"
        holder.kill()
        holder.wait(5)
        got = threading.Event()

        def take():
            with box_lane.hold("Extreme Leg"):
                got.set()

        threading.Thread(target=take, daemon=True).start()
        start = time.monotonic()
        assert got.wait(5), "the lane stayed shut after its holder died"
        assert time.monotonic() - start < 5
    finally:
        if holder.poll() is None:
            holder.kill()
