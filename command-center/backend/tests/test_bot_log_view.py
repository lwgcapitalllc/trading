"""The log panel must read the file the bot is actually writing.

**Why this file exists.** The runner moved to one log file per UTC day on 2026-08-05
(`algos/live/runner.py`, `DailyFileHandler`). This router went on reading the old fixed
`<key>.log`, which nothing has appended to since. **The panel served 5 August content for
nineteen days and looked live** — the bot placed thirteen orders in that window and not one of
them appeared. Nothing failed, nothing went red; the only symptom was a page that had quietly
stopped being about today.

That is rule 7 in its purest form: the field carried a comment stating what the runner writes,
the statement was true when written, and no test tied it to the runner. So these cases assert
on the COMMAND that goes to the box, not on a filename constant — a constant can agree with
itself forever.

**Watched RED against HEAD** (before the fix):
  - `test_the_newest_daily_file_is_the_one_read` — read `…\\mpc_sos_fade_demo.log`.
  - `test_the_view_spans_the_midnight_roll` — same, one stale file.
  - `test_a_bot_with_no_daily_files_falls_back_to_the_old_fixed_name` — passed on HEAD by
    accident (HEAD only ever reads that name), so it is pinned by mutation instead; see its
    docstring.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from routers import bots  # noqa: E402

KEY = "mpc_sos_fade_demo"


@pytest.fixture
def box(monkeypatch):
    """A fake trading box. `listing` is what `dir` returns; every command is recorded."""

    state = {"listing": "", "content": "line one\nline two", "cmds": []}

    def fake_ssh(cmd: str) -> str:
        state["cmds"].append(cmd)
        if cmd.startswith("dir "):
            return state["listing"]
        return state["content"]

    monkeypatch.setattr(bots, "_ssh", fake_ssh)
    return state


def _read_cmd(state) -> str:
    reads = [c for c in state["cmds"] if c.startswith("type ")]
    assert reads, f"nothing was read; commands were {state['cmds']}"
    return reads[-1]


def test_the_newest_daily_file_is_the_one_read(box):
    """`dir /b /o-n` returns newest first. The newest name must appear in the read."""
    box["listing"] = "\n".join(
        [
            f"{KEY}-2026-08-23.log",
            f"{KEY}-2026-08-22.log",
            f"{KEY}-2026-08-05.log",
        ]
    )
    bots.get_bot_log(KEY, lines=500)

    cmd = _read_cmd(box)
    assert f"{KEY}-2026-08-23.log" in cmd
    assert f"{KEY}-2026-08-05.log" not in cmd, "an ancient file was stitched into the view"
    assert rf"\{KEY}.log" not in cmd, "still reading the file the runner abandoned"


def test_the_view_spans_the_midnight_roll(box):
    """Two days, oldest first, so a request at 00:05 UTC is not four lines long.

    ⚠ The ORDER is the assertion. Reading them newest-first would interleave yesterday's tail
    after today's, and the tail below would then chop today's lines off the view.
    """
    box["listing"] = "\n".join([f"{KEY}-2026-08-24.log", f"{KEY}-2026-08-23.log"])
    bots.get_bot_log(KEY, lines=500)

    cmd = _read_cmd(box)
    assert cmd.index("2026-08-23") < cmd.index("2026-08-24"), "days read newest-first"


def test_only_this_bots_files_are_picked_up(box):
    """A shared instance directory must not leak another bot's log into this one's view."""
    box["listing"] = "\n".join(
        [
            "mpc_bleg_demo-2026-08-24.log",
            f"{KEY}-2026-08-23.log",
            "review-2026-08-23.log",
        ]
    )
    bots.get_bot_log(KEY, lines=500)

    cmd = _read_cmd(box)
    assert f"{KEY}-2026-08-23.log" in cmd
    assert "mpc_bleg_demo" not in cmd
    assert "review-" not in cmd


def test_a_bot_with_no_daily_files_falls_back_to_the_old_fixed_name(box):
    """A bot running pre-2026-08-05 code still writes one fixed file, and must stay readable.

    ⚠ **This cannot go red against HEAD** — HEAD reads that name unconditionally, so it passed
    there for the wrong reason. Killed by mutation instead: dropping the `or [f"{bot_key}.log"]`
    fallback makes the read command empty and this goes red. Recorded because a test that only
    ever agrees with both the bug and the fix is worth nothing.
    """
    box["listing"] = ""
    bots.get_bot_log(KEY, lines=500)

    assert rf"\{KEY}.log" in _read_cmd(box)


def test_an_explicit_filename_in_the_registry_still_wins(box, monkeypatch):
    """The override exists for a bot that breaks the convention. It must skip discovery.

    ⚠ Passed on HEAD for the wrong reason (HEAD always used this field), so it is pinned by
    mutation: forcing the discovery branch makes the read name the dated file and this goes red.
    """
    reg = bots._BY_KEY[KEY]
    monkeypatch.setattr(reg, "log_file", "custom.log", raising=False)
    box["listing"] = f"{KEY}-2026-08-23.log"

    bots.get_bot_log(KEY, lines=500)

    assert "custom.log" in _read_cmd(box)
    assert not [c for c in box["cmds"] if c.startswith("dir ")], "discovered despite an override"


def test_the_tail_is_still_bounded(box):
    """Stitching two files must not hand the browser the whole history."""
    box["listing"] = "\n".join([f"{KEY}-2026-08-24.log", f"{KEY}-2026-08-23.log"])
    box["content"] = "\n".join(f"line {i}" for i in range(4000))

    out = bots.get_bot_log(KEY, lines=500)

    assert len(out.splitlines()) == 500
    assert out.splitlines()[-1] == "line 3999"


def test_a_box_that_will_not_answer_the_listing_is_not_read_as_no_log(box, monkeypatch):
    """Cannot-ask must not become nothing-there. The error has to reach the caller.

    ⚠ This is the standing rule this repo keeps re-learning, and the log panel is exactly where
    it would hurt quietly: an unreachable box rendering as "Log file not found or empty" reads
    as a bot that has never logged anything.
    """

    def dead_box(cmd: str) -> str:
        raise bots.VpsUnreachable("connection refused")

    monkeypatch.setattr(bots, "_ssh", dead_box)

    with pytest.raises(bots.VpsUnreachable):
        bots.get_bot_log(KEY, lines=500)
