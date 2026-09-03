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
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from routers import bots  # noqa: E402

NOW = datetime(2026, 9, 3, 18, 0, tzinfo=timezone.utc)


def _fresh(minutes: int = 20) -> str:
    return (NOW - timedelta(minutes=minutes)).isoformat(timespec="seconds")


def _finding(level: str = "warn", title: str = "something") -> dict:
    return {"key": f"k:{title}", "level": level, "title": title, "detail": "d"}


def _snap(bot_key: str, payload) -> dict:
    return {bots._review_section(bot_key): json.dumps(payload)}


def _a_bot() -> str:
    return bots._BOTS[0].key


def test_a_review_is_parsed_for_the_bot_that_owns_it():
    key = _a_bot()
    got = bots._parse_reviews(
        _snap(
            key,
            {
                "bot": key,
                "level": "alert",
                "checked_at": "2026-08-05T18:00:00+00:00",
                "findings": [
                    {
                        "key": "halted:1",
                        "level": "alert",
                        "title": "Bridge HALTED",
                        "detail": "places nothing",
                    }
                ],
            },
        )
    )

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
    """An unreadable section must not become an alarm about this page's own plumbing.

    ⚠ The docstring here used to say `log_review.py` DELETES the file when clean, so absence was
    the healthy state. It does not any more (2026-09-03) — deleting it made the reviewer's own
    death invisible, because *nothing to review* and *nobody looked* were the same absent file.
    Absence is still quiet, but it is now UNKNOWN rather than healthy, and the Record review
    entry in the scheduled-jobs list is what speaks for it.
    """
    assert bots._parse_reviews({}) == {}


def test_a_clean_flag_is_kept_by_the_parse_and_dropped_by_the_payload():
    """🔴 The two halves that used to be one, and separating them is the whole fix.

    The parse now keeps a clean flag, because its timestamp is the only evidence the reviewer is
    alive. The CHIP gate moved down into `_review_payload`, so nothing on the page changed.

    ⚠ Cannot go red — `_review_payload` did not exist. Proven by MUTATION: making the payload
    return a review for an empty findings list raises a chip that says nothing is wrong, and the
    second assertion goes red.
    """
    key = _a_bot()
    flag = {"level": "ok", "checked_at": _fresh(), "findings": []}

    parsed = bots._parse_reviews(_snap(key, flag))
    assert parsed[key]["checked_at"] == flag["checked_at"]
    assert bots._review_payload(parsed[key], NOW) is None


def test_malformed_json_is_dropped_rather_than_raising():
    """⚠ This page must not invent an alarm out of its own plumbing failing. A torn file is a
    review job problem, and the review job's own state is visible where it belongs — as the
    **Record review** entry in the scheduled-jobs list."""
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


# ── the reviewer's own freshness ─────────────────────────────────────────────
#
# 🔴 Every test below is about ONE failure: the reviewer dies, and the last flag it ever wrote
# sits on the page looking current. Nothing checked the timestamp until 2026-09-03, so a dead
# hourly job and a healthy quiet week rendered identically — this repo's oldest defect shape, in
# the one place whose whole job is to notice that a healthy-looking system is not.
#
# ⚠ None of them can go RED: `_review_payload` did not exist, and the behaviour they assert had
# no seam to grab. Each is proven by MUTATION instead, named in its own docstring, and each
# mutation was run alone.


def test_a_stale_flag_raises_an_alert_of_its_own():
    """Proven by MUTATION: widening the staleness window to a week makes this go red."""
    flag = {"level": "ok", "checked_at": _fresh(minutes=60 * 5), "findings": []}
    got = bots._review_payload(flag, NOW)

    assert got is not None
    assert got["level"] == "alert"
    assert got["findings"][0]["key"].startswith("review_stale:")


def test_three_missed_runs_is_the_line():
    """The reviewer runs hourly, so this is the same three-in-a-row rule its own stale-heartbeat
    check uses. Proven by MUTATION: an off-by-one on the comparison takes down one side or the
    other, and both sides are asserted here."""
    assert bots._review_payload({"checked_at": _fresh(minutes=175), "findings": []}, NOW) is None
    assert bots._review_payload({"checked_at": _fresh(minutes=185), "findings": []}, NOW)


def test_the_stale_finding_comes_first():
    """It is the reason not to trust the findings under it, so it cannot be buried below them.
    Proven by MUTATION: appending instead of prepending goes red."""
    flag = {
        "level": "warn",
        "checked_at": _fresh(minutes=60 * 9),
        "findings": [_finding(title="old news")],
    }
    got = bots._review_payload(flag, NOW)

    assert [f["title"] for f in got["findings"]][0].startswith("The record reviewer")
    assert got["findings"][1]["title"] == "old news"


def test_a_flag_that_cannot_say_when_it_was_written_is_stale():
    """ "No" and "cannot ask" may not share a value, and here the reassuring answer is the
    dangerous one. Proven by MUTATION: treating an unreadable timestamp as fresh returns None
    for all three of these and every assertion goes red."""
    for stamp in (None, "", "not a time", "2026-13-45"):
        got = bots._review_payload({"checked_at": stamp, "findings": []}, NOW)
        assert got is not None, stamp
        assert got["level"] == "alert", stamp


def test_a_timestamp_with_no_zone_is_read_as_utc():
    """The box writes UTC. A naive stamp compared against an aware clock raises rather than
    answering, and an exception here would take out the whole Bots page — not just this chip.
    Proven by MUTATION: dropping the zone fill-in raises TypeError and this goes red."""
    naive = NOW.replace(tzinfo=None).isoformat(timespec="seconds")

    assert bots._review_payload({"checked_at": naive, "findings": []}, NOW) is None


def test_an_absent_flag_stays_quiet():
    """Deliberate: the reviewer writes one per bot per run, so an absence WOULD mean something
    after one pass — but it also looks exactly like a change that has not reached the box yet,
    and a false alarm on the hour after a deploy is how a chip gets ignored."""
    assert bots._review_payload(None, NOW) is None


def test_a_fresh_flag_passes_its_findings_through_untouched():
    """The chip has always meant "the reviewer found something". That must not change.
    Proven by MUTATION: prepending the stale finding unconditionally goes red."""
    flag = {
        "level": "alert",
        "checked_at": _fresh(),
        "findings": [_finding("alert", "Bridge HALTED"), _finding("warn", "re-warmed")],
    }
    got = bots._review_payload(flag, NOW)

    assert [f["title"] for f in got["findings"]] == ["Bridge HALTED", "re-warmed"]
    assert got["level"] == "alert"


def test_the_level_is_the_worst_of_the_findings():
    """Proven by MUTATION: hardcoding either level takes down one of these two."""
    fresh = _fresh()
    assert (
        bots._review_payload({"checked_at": fresh, "findings": [_finding("warn")]}, NOW)["level"]
        == "warn"
    )
    assert (
        bots._review_payload({"checked_at": fresh, "findings": [_finding("alert")]}, NOW)["level"]
        == "alert"
    )


def test_a_finding_that_is_not_an_object_is_dropped():
    """A torn or hand-edited file must not reach the response model as a string.
    Proven by MUTATION: removing the type filter lets it through and this goes red."""
    got = bots._review_payload({"checked_at": _fresh(), "findings": ["oops", 3]}, NOW)

    assert got is None


# ── the two silent watchers ──────────────────────────────────────────────────
def test_the_two_silent_watchers_are_on_the_jobs_list():
    """🔴 They were missing until 2026-09-03, and they are the only two jobs on that box whose
    normal state is SILENCE — so their death looks exactly like a quiet week. Worse, this
    module's own docstring promised a dead reviewer would show up there.

    ⚠ Cannot go red — it is a list entry, not a branch. Proven by MUTATION: removing either
    entry goes red, which is the whole point of pinning a list nobody would otherwise notice
    shrinking.
    """
    listed = {j.name for j in bots._SCHEDULED_JOBS}

    assert "Record review" in listed
    assert "Re-entry watch" in listed


def test_every_listed_job_resolves_to_a_real_task():
    """The file's own rule: a name with no task resolves to a permanent UNKNOWN, which reads as
    a job the page cannot see rather than one it never asked about. Nothing enforced it until
    now. Proven by MUTATION: renaming one entry goes red."""
    for job in bots._SCHEDULED_JOBS:
        assert job.name in bots._SYS_TASK_BY_JOB, job.name
        assert bots._SYS_TASK_BY_JOB[job.name] in bots._SYS_DISPLAY_NAMES


def test_the_parse_only_keeps_tasks_the_page_knows_about():
    """The snapshot pulls EVERY task on the box. A new one appearing there must not silently
    become a row here. Proven by MUTATION: dropping the membership test lets it through."""
    csv = '"\\SYS_LOGREVIEW","N/A","Ready"\n"\\SOMETHING_ELSE","N/A","Ready"'
    got = bots._parse_tasks({"tasks": csv})

    assert got == {"SYS_LOGREVIEW": "Ready"}
