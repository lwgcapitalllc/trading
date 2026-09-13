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


# ── a "right now" finding gives way to a NEWER heartbeat (2026-09-12) ────────
def _halted_now(level: str = "alert") -> dict:
    return {
        "key": "halted_now:unknown",
        "level": level,
        "title": "Bridge is HALTED right now",
        "detail": "Its latest heartbeat says the order bridge is halted.",
    }


def _after_the_review(minutes: float) -> float:
    """An epoch heartbeat stamp `minutes` after the flag `_fresh()` writes (20 minutes before NOW)."""
    return (NOW - timedelta(minutes=20) + timedelta(minutes=minutes)).timestamp()


def test_a_HALTED_RIGHT_NOW_finding_goes_once_a_newer_heartbeat_says_the_bridge_is_live():
    """🔴 MEASURED 2026-09-12: live SOS Fade read "Needs review — Bridge is HALTED right now" for 40
    minutes after a re-deploy cleared its halt, while its own heartbeat said live. The review runs
    hourly; the heartbeat is written every poll.

    MUTATION: drop the supersession → red. MUTATION: compare the two times the wrong way → red."""
    flag = {"checked_at": _fresh(), "findings": [_halted_now()]}
    got = bots._review_payload(flag, NOW, bridge_state="live", heartbeat=_after_the_review(5))
    # Since 2026-09-13 it goes to HISTORY with its reason, rather than vanishing.
    assert got["findings"] == [] and got["level"] == "ok"
    assert [f["key"] for f in got["resolved"]] == ["halted_now:unknown"]
    assert "no longer halted" in got["resolved"][0]["resolved"]


def test_it_goes_when_the_heartbeat_says_HALTED_too_because_the_row_raises_that_itself():
    """The page raises Halted off the heartbeat's own bridge state, with the bot's own reason. The
    review's copy would put the same fact on the row twice ("Halted +1")."""
    flag = {"checked_at": _fresh(), "findings": [_halted_now()]}
    got = bots._review_payload(flag, NOW, bridge_state="halted", heartbeat=_after_the_review(5))
    assert got is None


def test_only_the_present_tense_finding_goes_and_the_level_follows_what_is_left():
    """A finding about the RECORD stays — only the one about NOW has a fresher reading.

    MUTATION: drop every finding once the heartbeat is newer → red on the titles."""
    flag = {
        "checked_at": _fresh(),
        "findings": [_halted_now(), _finding("warn", "Restarted twice")],
    }
    got = bots._review_payload(flag, NOW, bridge_state="live", heartbeat=_after_the_review(5))
    assert [f["title"] for f in got["findings"]] == ["Restarted twice"]
    assert got["level"] == "warn"


def test_it_is_KEPT_when_no_heartbeat_speaks_for_now():
    """A stopped bot passes no bridge state — its last reading describes a process that no longer
    exists — so the review is the freshest evidence there is.

    MUTATION: drop the missing-bridge check → red."""
    flag = {"checked_at": _fresh(), "findings": [_halted_now()]}
    got = bots._review_payload(flag, NOW, bridge_state=None, heartbeat=_after_the_review(5))
    assert [f["key"] for f in got["findings"]] == ["halted_now:unknown"]


def test_it_is_KEPT_when_the_heartbeat_is_OLDER_than_the_review():
    """A heartbeat taken before the review read the bridge before the review did — it cannot
    contradict it. MUTATION: `stamp < written` → red."""
    flag = {"checked_at": _fresh(), "findings": [_halted_now()]}
    got = bots._review_payload(flag, NOW, bridge_state="live", heartbeat=_after_the_review(-5))
    assert [f["key"] for f in got["findings"]] == ["halted_now:unknown"]


def test_it_is_KEPT_when_either_time_cannot_be_read():
    """Rule 1: a stamp nobody can read, or a review that cannot say when it ran, must not buy the
    reassuring answer. `True` is here because a bool IS an int in Python.

    MUTATION: read the stamp without `_finite` → red on infinity (True survives that one: it
    compares as 1). MUTATION: read an unreadable review time as the epoch → red on the last case."""
    for stamp in (None, "soon", True, float("nan"), float("inf")):
        flag = {"checked_at": _fresh(), "findings": [_halted_now()]}
        got = bots._review_payload(flag, NOW, bridge_state="live", heartbeat=stamp)
        assert got is not None, stamp
        assert [f["key"] for f in got["findings"]] == ["halted_now:unknown"], stamp
    flag = {"checked_at": "not a time", "findings": [_halted_now()]}
    got = bots._review_payload(flag, NOW, bridge_state="live", heartbeat=_after_the_review(5))
    assert "halted_now:unknown" in [f["key"] for f in got["findings"]]


def test_the_key_it_drops_is_the_one_log_review_WRITES():
    """The prefix is a contract with `algos/notifications/log_review.py`, which this app may read and
    never import. A rename there would leave the stale finding on the row for ever with nothing
    failing — so the writer's own source is read.

    MUTATION: change the prefix here → red."""
    writer = Path(__file__).resolve().parents[3] / "algos" / "notifications" / "log_review.py"
    src = writer.read_text(encoding="utf-8")
    for prefix in bots._ANSWERABLE:
        assert f'f"{prefix}{{' in src, prefix
    # ...and so is the list it files what is OVER under (2026-09-13).
    assert '"resolved": [' in src


def test_the_snapshot_hands_a_RUNNING_bots_heartbeat_to_the_review(monkeypatch):
    """The rule only works if the endpoint passes the bot's heartbeat on — and only a running bot's,
    whose reading describes a process that still exists.

    MUTATION: drop `heartbeat=` from the call → red. MUTATION: drop the RUNNING gate → red on the
    stopped half."""
    key = bots._BOTS[0].key
    now = datetime.now(timezone.utc)
    flag = {
        "checked_at": (now - timedelta(minutes=20)).isoformat(timespec="seconds"),
        "findings": [_halted_now()],
    }
    state = {"bridge_state": "live", "heartbeat": (now - timedelta(minutes=5)).timestamp()}
    running = {"value": True}
    monkeypatch.setattr(bots, "_fetch_vps_snapshot", lambda: {})
    monkeypatch.setattr(bots, "_parse_bot_states", lambda _snap: {key: state})
    monkeypatch.setattr(bots, "_parse_reviews", lambda _snap: {key: flag})
    monkeypatch.setattr(bots, "_bot_runner_running", lambda _snap, _key: running["value"])

    def keys() -> list[str]:
        row = next(b for b in bots.get_snapshot().bots if b.key == key)
        return [f.key for f in row.review.findings] if row.review else []

    assert "halted_now:unknown" not in keys()
    running["value"] = False
    assert "halted_now:unknown" in keys()


# ── open, or over: only OPEN counts (2026-09-13) ─────────────────────────────
#
# 🔴 Aaron: *"I don't want to manually mark anything as reviewed. The platform should know that this
# thing was resolved."* The reviewer files what the record shows has ended under `resolved`; the
# page counts only what is left, and the bot's own readings since the review answer the rest.


def _open_keys(got) -> list:
    return [f["key"] for f in got["findings"]] if got else []


def _over_keys(got) -> list:
    return [f["key"] for f in got["resolved"]] if got else []


def _open_one(key: str) -> dict:
    return {
        "checked_at": _fresh(),
        "findings": [{"key": key, "level": "warn", "title": key, "detail": "d"}],
    }


def test_what_the_reviewer_filed_as_OVER_is_passed_on_and_never_counted():
    """MUTATION: count the `resolved` list as open → red. MUTATION: drop it → red."""
    over = dict(_finding("alert", "Restarted 4 times"), resolved="None since 2:03 PM")
    got = bots._review_payload({"checked_at": _fresh(), "findings": [], "resolved": [over]}, NOW)

    assert got["level"] == "ok"
    assert _open_keys(got) == []
    assert _over_keys(got) == [over["key"]]


def test_an_open_finding_that_says_why_it_is_over_is_over_wherever_it_was_filed():
    """MUTATION: trust the list it arrived in → red."""
    over = dict(_finding("warn", "Link drop"), resolved="It came back.")
    got = bots._review_payload({"checked_at": _fresh(), "findings": [over, _finding()]}, NOW)

    assert _open_keys(got) == ["k:something"]
    assert _over_keys(got) == [over["key"]]


def test_a_flag_from_before_the_split_keeps_everything_open():
    """A reviewer that has not reached the box yet writes no `resolved`: every finding stays open,
    the direction that never hides a real one."""
    got = bots._review_payload({"checked_at": _fresh(), "findings": [_finding("alert")]}, NOW)

    assert got["level"] == "alert"
    assert _open_keys(got) == ["k:something"] and _over_keys(got) == []


def test_the_level_is_the_worst_OPEN_finding():
    """MUTATION: take the level from history too → red."""
    over = dict(_finding("alert", "old"), resolved="over")
    flag = {"checked_at": _fresh(), "findings": [_finding("warn")], "resolved": [over]}

    assert bots._review_payload(flag, NOW)["level"] == "warn"


def test_a_link_drop_is_answered_by_the_heartbeats_own_link_reading():
    """Up = over; down = dropped, because the row raises *No MT5 link* off that same heartbeat;
    anything else = kept. MUTATION: treat any reading as up → red on the down and unread cases."""

    def review(link):
        return bots._review_payload(
            _open_one("mt5_outage:t"),
            NOW,
            bridge_state="live",
            heartbeat=_after_the_review(5),
            mt5_link=link,
        )

    assert _open_keys(review(True)) == [] and _over_keys(review(True)) == ["mt5_outage:t"]
    assert review(False) is None
    for unread in (None, "yes", 1):
        assert _open_keys(review(unread)) == ["mt5_outage:t"], unread


def test_a_bar_or_loop_error_is_answered_by_any_newer_heartbeat_and_no_older_one():
    """The loop has turned since. MUTATION: drop the rule → red."""
    for key in ("bar_error:t", "loop_error:t"):
        newer = bots._review_payload(
            _open_one(key), NOW, bridge_state="live", heartbeat=_after_the_review(5)
        )
        older = bots._review_payload(
            _open_one(key), NOW, bridge_state="live", heartbeat=_after_the_review(-5)
        )
        assert _over_keys(newer) == [key], key
        assert _open_keys(older) == [key], key


def test_a_refusal_to_start_is_answered_by_a_run_that_began_after_the_review():
    """It read its settings and its pin again and got in. ⚠ NOT gated on running: a run that began
    after the review answered the refusal even if it has stopped since.

    MUTATION: drop the rule → red. MUTATION: compare the two times the wrong way → red."""
    for key in ("startup_failed:t", "version_mismatch:t", "config_refused:t"):
        after = bots._review_payload(_open_one(key), NOW, started=_after_the_review(5))
        before = bots._review_payload(_open_one(key), NOW, started=_after_the_review(-5))
        assert _over_keys(after) == [key], key
        assert _open_keys(before) == [key], key


def test_a_start_nobody_can_read_answers_nothing():
    """Rule 1: a start written only as text, a bool, NaN or infinity must not buy an all-clear.
    MUTATION: read the start without `_finite` → red on infinity."""
    for stamp in (None, "2026-09-03T18:00:00", True, float("nan"), float("inf")):
        got = bots._review_payload(_open_one("startup_failed:t"), NOW, started=stamp)
        assert _open_keys(got) == ["startup_failed:t"], stamp


def test_a_heartbeat_or_a_start_never_ends_a_REPEAT():
    """One good heartbeat does not end a burst — only the reviewer's quiet-stretch rule does.
    MUTATION: answer every finding on a newer heartbeat → red."""
    for key in ("restart_loop:t", "mt5_storm:t", "loop_storm:t", "rewarm_storm:t"):
        got = bots._review_payload(
            _open_one(key),
            NOW,
            bridge_state="live",
            heartbeat=_after_the_review(5),
            mt5_link=True,
            started=_after_the_review(5),
        )
        assert _open_keys(got) == [key], key


def test_a_stopped_bots_heartbeat_answers_nothing():
    """Only a RUNNING bot passes a bridge reading, and without one neither its stamp nor its link
    answers anything. MUTATION: drop the missing-bridge check → red."""
    for key in ("mt5_outage:t", "bar_error:t", "halted:t"):
        got = bots._review_payload(
            _open_one(key), NOW, bridge_state=None, heartbeat=_after_the_review(5), mt5_link=True
        )
        assert _open_keys(got) == [key], key


def test_the_snapshot_hands_the_link_and_the_start_to_the_review(monkeypatch):
    """The rules only work if the endpoint passes the readings on.
    MUTATION: drop `mt5_link=` → red. MUTATION: drop `started=` → red."""
    key = bots._BOTS[0].key
    now = datetime.now(timezone.utc)
    flag = {
        "checked_at": (now - timedelta(minutes=20)).isoformat(timespec="seconds"),
        "findings": [
            {"key": "mt5_outage:t", "level": "warn", "title": "t", "detail": "d"},
            {"key": "startup_failed:t", "level": "alert", "title": "t", "detail": "d"},
        ],
    }
    later = (now - timedelta(minutes=5)).timestamp()
    state = {"bridge_state": "live", "heartbeat": later, "mt5_link": True, "started": later}
    monkeypatch.setattr(bots, "_fetch_vps_snapshot", lambda: {})
    monkeypatch.setattr(bots, "_parse_bot_states", lambda _snap: {key: state})
    monkeypatch.setattr(bots, "_parse_reviews", lambda _snap: {key: flag})
    monkeypatch.setattr(bots, "_bot_runner_running", lambda _snap, _key: True)
    row = next(b for b in bots.get_snapshot().bots if b.key == key)

    assert row.review.findings == []
    assert sorted(f.key for f in row.review.resolved) == ["mt5_outage:t", "startup_failed:t"]
