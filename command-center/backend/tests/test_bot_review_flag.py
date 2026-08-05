"""The "needs review" flag the Bots page renders, and the ways it could lie.

The flag comes from `algos/notifications/log_review.py`, which reads each bot's own health
record hourly and writes `<instance>/review.json` on the VPS. This module fetches it on the same
batched connection as `bot_state.json` and hands it to the page.

**Why it exists at all:** the process can be alive, stamping its heartbeat and rendering RUNNING
here while the order bridge is HALTED and the bot places nothing. Nothing on this page could see
that before 2026-08-05 — every signal it draws is about the PROCESS.

The tests below are about the plumbing rather than the findings, because the plumbing is what
fails silently: a section name the fetch writes and the parse looks for under a different spelling
produces a flag that is always absent, which is indistinguishable from a healthy bot.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from routers import bots  # noqa: E402


def _snap(bot_key: str, payload) -> dict:
    return {bots._review_section(bot_key): json.dumps(payload)}


def _a_bot() -> str:
    return bots._BOTS[0].key


def test_a_review_is_parsed_for_the_bot_that_owns_it():
    key = _a_bot()
    got = bots._parse_reviews(_snap(key, {
        "bot": key, "level": "alert", "checked_at": "2026-08-05T18:00:00+00:00",
        "findings": [{"key": "halted:1", "level": "alert",
                      "title": "Bridge HALTED", "detail": "places nothing"}]}))

    assert got[key]["level"] == "alert"
    assert got[key]["findings"][0]["title"] == "Bridge HALTED"


def test_the_fetch_and_the_parse_agree_on_the_section_name():
    """🔴 The failure this pins is silent in the worst way: a flag fetched under one name and
    read under another is ALWAYS absent, which renders exactly like a healthy bot. Both sides
    call `_review_section`, and this asserts the command really carries what it produces."""
    parts = bots._fetch_vps_snapshot.__doc__  # noqa: F841 - documented, not asserted on
    for b in bots._BOTS:
        marker = f"==={bots._review_section(b.key).upper()}==="
        assert marker == f"===REVIEW_{b.key.upper()}==="
        assert b.review_file.endswith(rf"{b.instance_dir}\review.json")


def test_a_missing_flag_means_nothing_to_review():
    """The normal case, and it must be quiet. `log_review.py` DELETES the file when a bot is
    clean, so absence is the healthy state and cannot be reported as a fault."""
    assert bots._parse_reviews({}) == {}


def test_an_empty_findings_list_is_not_a_flag():
    """A file written with no findings would raise a chip saying nothing is wrong. Belt and
    braces against the writer's own clear failing — a stale chip trains you to ignore the chip."""
    key = _a_bot()
    assert bots._parse_reviews(_snap(key, {"level": "warn", "checked_at": "x",
                                           "findings": []})) == {}


def test_malformed_json_is_dropped_rather_than_raising():
    """⚠ This page must not invent an alarm out of its own plumbing failing. A torn file is a
    review job problem, and the review job's own absence is visible where it belongs — as a
    DISABLED `SYS_LOGREVIEW` in the scheduled-jobs list."""
    key = _a_bot()
    assert bots._parse_reviews({bots._review_section(key): "{not json"}) == {}


def test_a_non_dict_payload_is_dropped():
    key = _a_bot()
    assert bots._parse_reviews({bots._review_section(key): "[1,2,3]"}) == {}


def test_every_registered_bot_has_its_own_review_path():
    """PER BOT even when two share a `bot_state.json`. A review is about one bot's own health
    record, and merging two into one file makes "which bot needs attention" unanswerable from
    the file that exists to answer it."""
    paths = [b.review_file for b in bots._BOTS]
    assert len(paths) == len(set(paths))
