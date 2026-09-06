"""Reading the bot's own record and deciding when to interrupt a human.

**What this module is for.** `monitor.py` asks whether the process is THERE; `deadman.py` asks
whether the box can still talk. Neither reads a line the bot WROTE, so a HALTED bridge — the loop
running, the heartbeat ticking, the Bots page saying RUNNING, and not one order going out — was
invisible to every alert in this system.

**The tests are weighted toward the ways a checker wrongly says "fine",** for the same reason
`test_deadman.py` is: a bug here is silent by construction. Every other alarm in this suite fails
loudly and gets reported; this one fails by having nothing to say, and having nothing to say is
also what a healthy day looks like.

Three properties carry most of the value and each has its own failure mode:

1. **Not reading is not health.** A missing or unreadable record for a bot that is supposed to be
   running has to be a finding. The reassuring answer is the dangerous one here.
2. **Not reading is not a fault either, if the bot is stopped.** A checker that cries wolf every
   time you deliberately stop a bot is one you learn to ignore, which costs you the real alert.
3. **One alert per occurrence, and a NEW occurrence still alerts.** Keys carry the timestamp of
   the thing that happened. Keying on the KIND of thing would alert once and then stay silent
   through every future halt — the classic de-duplicating-alerter bug, and it is silent.
"""

from __future__ import annotations

import json
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

_REPO = Path(__file__).resolve().parent.parent.parent
for _p in (_REPO / "algos" / "notifications", _REPO / "algos" / "shared"):
    if str(_p) not in sys.path:
        sys.path.insert(0, str(_p))

import log_review as lr  # noqa: E402

NOW = datetime(2026, 8, 5, 18, 0, tzinfo=timezone.utc)
RUNNING = {"status": "live"}
STOPPED = {"status": "stopped"}


def _write(inst: Path, rows: list[dict], day: str = "2026-08-05") -> Path:
    led = inst / "ledger"
    led.mkdir(parents=True, exist_ok=True)
    path = led / f"health-{day}.jsonl"
    path.write_text("".join(json.dumps(r) + "\n" for r in rows), encoding="utf-8")
    return path


def _event(name: str, at: str = "2026-08-05T12:00:00+00:00", **kw) -> dict:
    return {"ts": at, "bot": "b", "kind": "event", "event": name, **kw}


def _pulse(at: str, **kw) -> dict:
    base = {"ts": at, "bot": "b", "kind": "pulse", "link": True, "bridge_state": "live"}
    base.update(kw)
    return base


def _keys(findings) -> set:
    return {f.key.split(":")[0] for f in findings}


def _healthy(minutes_back: int = 5) -> list[dict]:
    """A record with nothing wrong in it — one clean start and recent heartbeats."""
    rows = [_event("startup", "2026-08-05T10:00:00+00:00", previous_run_clean=True)]
    for i in (45, 30, 15, minutes_back):
        rows.append(_pulse((NOW - timedelta(minutes=i)).isoformat(timespec="seconds")))
    return rows


# ── a clean day says nothing ─────────────────────────────────────────────────
def test_a_healthy_record_produces_no_findings(tmp_path):
    """Silent when clean, or the channel becomes noise and gets muted — the reason
    `reporter.py` was deleted rather than fixed."""
    _write(tmp_path, _healthy())
    assert lr.review_bot("b", tmp_path, RUNNING, now=NOW) == []


# ── the finding nothing else in the system can see ───────────────────────────
def test_a_halted_bridge_is_an_alert(tmp_path):
    """🔴 THE reason this module exists. The process is alive and stamping, so the watchdog is
    happy, the dead-man's switch is happy and the Bots page says RUNNING — while the bot places
    nothing at all.

    ⚠ The last pulse has to say `halted` too, and that is not fixture noise — it is what the
    real file looks like. A bridge NEVER returns to live without a restart, so a halt event
    followed by live pulses means somebody restarted it in between, which is a recovered halt
    and is reported in the past tense (see the recovered-halt test below). Before 2026-08-07
    this fixture read as an alert either way, which is precisely the bug: the finding could not
    tell an open incident from one that ended hours ago.
    """
    rows = _healthy() + [
        _event("halted", "2026-08-05T17:00:00+00:00", reason="emulator and broker disagree")
    ]
    rows[-2] = _pulse(rows[-2]["ts"], bridge_state="halted")
    _write(tmp_path, rows)
    found = lr.review_bot("b", tmp_path, RUNNING, now=NOW)

    assert "halted" in _keys(found)
    assert all(f.level == lr.ALERT for f in found if f.key.startswith("halted"))
    assert "disagree" in next(f for f in found if f.key.startswith("halted")).detail


def test_a_bridge_halted_right_now_is_caught_from_the_heartbeat_alone(tmp_path):
    """A halt that happened before the window still shows in the CURRENT state. Reading only
    the event would miss a bot that has been halted since yesterday."""
    rows = _healthy()
    rows[-1] = _pulse(rows[-1]["ts"], bridge_state="halted")
    _write(tmp_path, rows)

    assert "halted_now" in _keys(lr.review_bot("b", tmp_path, RUNNING, now=NOW))


# ── cannot read ⇒ a finding, not silence ─────────────────────────────────────
def test_a_missing_record_for_a_running_bot_is_an_alert(tmp_path):
    """⚠ The rule this repo has now met five times: never let "no" and "cannot ask" be the same
    value. Here the reassuring answer is the dangerous one — a checker with nothing to say is
    indistinguishable from a system with nothing wrong."""
    found = lr.review_bot("b", tmp_path, RUNNING, now=NOW)

    assert _keys(found) == {"unreadable"}
    assert found[0].level == lr.ALERT


def test_a_missing_record_for_a_STOPPED_bot_is_not_a_fault(tmp_path):
    """The other half, and it is what keeps the alert credible. A bot you stopped on purpose has
    no record to write, and an alarm that fires every time you stop one is an alarm you mute."""
    assert lr.review_bot("b", tmp_path, STOPPED, now=NOW) == []


def test_an_unreadable_file_is_reported_rather_than_skipped(tmp_path, monkeypatch):
    _write(tmp_path, _healthy())

    def _boom(*a, **k):
        raise OSError("permission denied")

    monkeypatch.setattr(Path, "read_text", _boom)
    found = lr.review_bot("b", tmp_path, RUNNING, now=NOW)

    assert _keys(found) == {"unreadable"}


def test_a_torn_last_line_is_not_treated_as_a_fault(tmp_path):
    """The sync copies these files while the bot appends to them, and the bot itself can be
    mid-write. A half-record is expected, not a symptom."""
    path = _write(tmp_path, _healthy())
    with path.open("a", encoding="utf-8") as f:
        f.write('{"ts": "2026-08-05T17:59:00+00:00", "kind": "pu')

    assert lr.review_bot("b", tmp_path, RUNNING, now=NOW) == []


# ── things that already recovered still get reported ─────────────────────────
def test_a_link_outage_that_recovered_is_still_reported(tmp_path):
    """⚠ The charter: `monitor.py` owns NOW, this owns THE RECORD. An outage at 3am that healed
    by 4am leaves no trace anywhere else — `bot_state.json` is overwritten in place and only ever
    describes the present."""
    _write(
        tmp_path,
        _healthy()
        + [
            _event("mt5_link_lost", "2026-08-05T03:00:00+00:00"),
            _event("mt5_link_restored", "2026-08-05T03:50:00+00:00", down_seconds=3000),
        ],
    )
    found = lr.review_bot("b", tmp_path, RUNNING, now=NOW)

    assert "mt5_outage" in _keys(found)
    assert "50 minutes" in next(f for f in found if f.key.startswith("mt5_outage")).detail


def test_a_gap_between_heartbeats_that_has_closed_is_reported(tmp_path):
    """A stall the watchdog restarted at 3am: its alert has been and gone, and nothing kept the
    fact that it happened."""
    _write(
        tmp_path,
        [
            _event("startup", "2026-08-05T10:00:00+00:00", previous_run_clean=True),
            _pulse("2026-08-05T12:00:00+00:00"),
            _pulse("2026-08-05T14:00:00+00:00"),  # two hours, no beat
            _pulse((NOW - timedelta(minutes=5)).isoformat(timespec="seconds")),
        ],
    )
    found = lr.review_bot("b", tmp_path, RUNNING, now=NOW)

    assert "pulse_gap" in _keys(found)


def test_a_normal_heartbeat_cadence_is_not_a_gap(tmp_path):
    """The threshold is three missed beats, deliberately generous, so this never becomes a
    second and vaguer version of the watchdog's stall alert."""
    _write(tmp_path, _healthy())
    assert "pulse_gap" not in _keys(lr.review_bot("b", tmp_path, RUNNING, now=NOW))


def test_a_running_bot_whose_record_went_quiet_is_an_alert(tmp_path):
    """Alive according to `bot_state.json`, writing nothing to the record. The two disagreeing
    is itself the signal."""
    _write(
        tmp_path,
        [
            _event("startup", "2026-08-05T10:00:00+00:00", previous_run_clean=True),
            _pulse("2026-08-05T11:00:00+00:00"),
        ],
    )
    found = lr.review_bot("b", tmp_path, RUNNING, now=NOW)

    assert "silent" in _keys(found)
    assert next(f for f in found if f.key.startswith("silent")).level == lr.ALERT


# ── lifecycle ────────────────────────────────────────────────────────────────
def test_a_kill_is_reported_on_the_next_start(tmp_path):
    _write(
        tmp_path,
        _healthy() + [_event("startup", "2026-08-05T16:00:00+00:00", previous_run_clean=False)],
    )

    assert "unclean" in _keys(lr.review_bot("b", tmp_path, RUNNING, now=NOW))


def test_a_clean_restart_is_not_reported(tmp_path):
    """Restarting a bot on purpose is ordinary. Only an ending nobody recorded is news."""
    _write(
        tmp_path,
        _healthy()
        + [
            _event("shutdown", "2026-08-05T15:00:00+00:00", exit_code=0, reason="stop requested"),
            _event("startup", "2026-08-05T15:01:00+00:00", previous_run_clean=True),
        ],
    )

    assert "unclean" not in _keys(lr.review_bot("b", tmp_path, RUNNING, now=NOW))


def test_repeated_restarts_are_an_alert(tmp_path):
    """Four ends nobody recorded is a loop: something is killing it, or it keeps failing."""
    rows = _healthy()
    for h in (11, 12, 13, 14):
        rows.append(_event("startup", f"2026-08-05T{h}:00:00+00:00", previous_run_clean=False))
    _write(tmp_path, rows)
    found = lr.review_bot("b", tmp_path, RUNNING, now=NOW)

    assert "restart_loop" in _keys(found)
    assert next(f for f in found if f.key.startswith("restart_loop")).level == lr.ALERT


def test_deliberate_restarts_are_not_a_restart_loop(tmp_path):
    """🔴 The finding this test exists for fired on a normal week of deploying.

    Four promotes inside the window is ordinary, and while every start was counted the chip on
    the Bots page never went out — the old text even ended "Expected if you deployed today",
    which is an alarm apologising for itself. Watched RED against HEAD: it reported a loop.
    """
    rows = _healthy()
    for h in (11, 12, 13, 14):
        rows.append(
            _event("shutdown", f"2026-08-05T{h}:59:00+00:00", exit_code=0, reason="stop requested")
        )
        rows.append(_event("startup", f"2026-08-05T{h}:00:00+00:00", previous_run_clean=True))
    _write(tmp_path, rows)

    assert "restart_loop" not in _keys(lr.review_bot("b", tmp_path, RUNNING, now=NOW))


def test_a_start_that_cannot_say_how_the_last_run_ended_is_counted(tmp_path):
    """`None` is UNKNOWN, and unknown may not buy the reassuring answer — rule 1.

    ⚠ Cannot go red against HEAD, which counted every start regardless. Proven by MUTATION:
    relaxing the test to `is False` makes this pass silently on four unexplained restarts, and
    the assertion below goes red.
    """
    rows = _healthy()
    for h in (11, 12, 13, 14):
        rows.append(_event("startup", f"2026-08-05T{h}:00:00+00:00", previous_run_clean=None))
    _write(tmp_path, rows)

    assert "restart_loop" in _keys(lr.review_bot("b", tmp_path, RUNNING, now=NOW))


def test_a_refused_config_change_is_reported(tmp_path):
    """The page can show settings the bot is not using. That is a wrong-number problem, and it
    is exactly the class this repo keeps meeting."""
    _write(
        tmp_path,
        _healthy()
        + [_event("config_change_refused", "2026-08-05T14:00:00+00:00", changes="exec_risk_pct")],
    )

    assert "config_refused" in _keys(lr.review_bot("b", tmp_path, RUNNING, now=NOW))


def test_a_refused_change_stops_being_reported_once_it_has_restarted(tmp_path):
    """🔴 It told you to restart for two days after you had restarted.

    A start reads the settings file fresh, so the refusal has been answered and the finding's own
    instruction has been carried out. It is the same defect as the halt wording (2026-08-07): a
    sticky present-tense claim that has stopped being true. Watched RED against HEAD.
    """
    _write(
        tmp_path,
        _healthy()
        + [
            _event("config_change_refused", "2026-08-05T14:00:00+00:00", changes="exec_secondary"),
            _event("startup", "2026-08-05T14:05:00+00:00", previous_run_clean=True),
        ],
    )

    assert "config_refused" not in _keys(lr.review_bot("b", tmp_path, RUNNING, now=NOW))


def test_an_ungraceful_restart_still_takes_the_settings(tmp_path):
    """A start loads the file however the run before it ended, so this must suppress too.

    Watched RED against HEAD, which never suppressed at all. It also pins the seam: asking how
    the previous run ENDED is the restart-loop question, not this one, and conflating them would
    suppress nothing while looking careful.
    """
    _write(
        tmp_path,
        _healthy()
        + [
            _event("config_change_refused", "2026-08-05T14:00:00+00:00", changes="exec_secondary"),
            _event("startup", "2026-08-05T14:05:00+00:00", previous_run_clean=False),
        ],
    )

    assert "config_refused" not in _keys(lr.review_bot("b", tmp_path, RUNNING, now=NOW))


def test_a_restart_at_the_same_second_does_not_clear_the_refusal(tmp_path):
    """The refusal is written by the already-running bot, so a start on the same second cannot
    be shown to have loaded the new settings. Ambiguity keeps the finding.

    ⚠ Cannot go red against HEAD. Proven by MUTATION: loosening the comparison to `>=` drops
    the finding and this goes red.
    """
    _write(
        tmp_path,
        _healthy()
        + [
            _event("config_change_refused", "2026-08-05T14:00:00+00:00", changes="exec_secondary"),
            _event("startup", "2026-08-05T14:00:00+00:00", previous_run_clean=True),
        ],
    )

    assert "config_refused" in _keys(lr.review_bot("b", tmp_path, RUNNING, now=NOW))


def test_a_refusal_with_an_unreadable_time_is_never_suppressed(tmp_path):
    """A refusal that cannot be placed in time is precisely the one not to drop.

    ⚠ Cannot go red against HEAD. Proven by MUTATION: dropping the guard on the parsed
    timestamp suppresses it (or raises), and this goes red either way.
    """
    _write(
        tmp_path,
        _healthy()
        + [
            {"ts": "?", "bot": "b", "kind": "event", "event": "config_change_refused"},
            _event("startup", "2026-08-05T14:05:00+00:00", previous_run_clean=True),
        ],
    )

    assert "config_refused" in _keys(lr.review_bot("b", tmp_path, RUNNING, now=NOW))


def test_a_failed_start_and_a_version_mismatch_are_alerts(tmp_path):
    _write(
        tmp_path,
        _healthy()
        + [
            _event("startup_failed", "2026-08-05T13:00:00+00:00", error="bad config"),
            _event("version_mismatch", "2026-08-05T13:05:00+00:00", detail="hash differs"),
        ],
    )
    found = lr.review_bot("b", tmp_path, RUNNING, now=NOW)

    assert {"startup_failed", "version_mismatch"} <= _keys(found)
    assert all(
        f.level == lr.ALERT
        for f in found
        if f.key.split(":")[0] in {"startup_failed", "version_mismatch"}
    )


# ── a refusal to start is ANSWERED by a start (2026-09-04) ───────────────────
#
# 🔴 `extreme_leg_demo` failed three times on one unknown setting, the setting was removed, and it
# started and traded — while the Bots page showed NEEDS REVIEW (3) beside a green RUNNING pill.
# That pair cannot be resolved by the person reading it, and Aaron asked why. It is the halt-tense
# defect a third time: a past event rendered as a standing state.
#
# The rule already existed two blocks down for `config_change_refused`. These cases extend it to
# both refused-to-start findings, which is the same claim with a different cause.
#
# Watched RED, and the map was RUN:
#     against HEAD                                  -> 3 red (both suppressions + the loop case)
#     loosen the comparison to `>=`                 -> 2 red
#     suppress on ANY start rather than a LATER one -> 5 red
#     treat an unreadable timestamp as suppressible -> 2 red (this file's case and its sibling)
#     restore                                       -> 46 green, re-run after every mutation
#
# 🔴 **THE FIRST ATTEMPT AT THE UNREADABLE-TIMESTAMP MUTATION SURVIVED, AND THE MUTATION WAS THE
# THING AT FAULT.** It moved the `at is not None` test into the generator, where a `None` still
# yields nothing and `any()` is still False — behaviour identical to the original. **A mutation
# that does not change behaviour is indistinguishable from a test that cannot catch one**, and it
# reads as the more alarming of the two. The real mutation substitutes an epoch floor for the
# missing timestamp, so every start looks later, and both cases go red.


def test_a_failed_start_stops_being_reported_once_it_has_STARTED_since(tmp_path):
    """🔴 The chip Aaron asked about. Watched RED against HEAD, which reported it for the full
    two-day window however well the bot was running."""
    _write(
        tmp_path,
        _healthy()
        + [
            _event("startup_failed", "2026-08-05T13:00:00+00:00", error="unknown param"),
            _event("startup", "2026-08-05T13:05:00+00:00", previous_run_clean=True),
        ],
    )

    assert "startup_failed" not in _keys(lr.review_bot("b", tmp_path, RUNNING, now=NOW))


def test_a_failed_start_AFTER_the_last_good_one_is_still_reported(tmp_path):
    """The bot is down NOW, which is the whole point of the finding. MUTATION: suppress on any
    start rather than a LATER one and this goes red — the chip would go dark on a bot that cannot
    start at all, which is strictly worse than the defect being fixed."""
    _write(
        tmp_path,
        _healthy()
        + [
            _event("startup", "2026-08-05T13:00:00+00:00", previous_run_clean=True),
            _event("startup_failed", "2026-08-05T13:05:00+00:00", error="unknown param"),
        ],
    )

    assert "startup_failed" in _keys(lr.review_bot("b", tmp_path, RUNNING, now=NOW))


def test_a_VERSION_refusal_also_clears_once_it_has_started(tmp_path):
    """It is *it refused to start* with the pin as the cause. Leaving one of the three
    refused-to-start findings sticky while the others clear is the inconsistency this fixes.
    Watched RED against HEAD."""
    _write(
        tmp_path,
        _healthy()
        + [
            _event("version_mismatch", "2026-08-05T13:00:00+00:00", detail="hash differs"),
            _event("startup", "2026-08-05T13:05:00+00:00", previous_run_clean=True),
        ],
    )

    assert "version_mismatch" not in _keys(lr.review_bot("b", tmp_path, RUNNING, now=NOW))


def test_a_start_at_the_same_second_does_not_clear_a_failed_start(tmp_path):
    """Ambiguity keeps the finding, matching the settings refusal.

    ⚠ Cannot go red against HEAD. Proven by MUTATION: loosening the comparison to `>=` drops the
    finding and this goes red."""
    _write(
        tmp_path,
        _healthy()
        + [
            _event("startup_failed", "2026-08-05T13:00:00+00:00", error="unknown param"),
            _event("startup", "2026-08-05T13:00:00+00:00", previous_run_clean=True),
        ],
    )

    assert "startup_failed" in _keys(lr.review_bot("b", tmp_path, RUNNING, now=NOW))


def test_a_failed_start_with_an_unreadable_time_is_never_suppressed(tmp_path):
    """A failure that cannot be placed in time is precisely the one not to drop.

    ⚠ Cannot go red against HEAD. Proven by MUTATION: dropping the guard on the parsed timestamp
    suppresses it (or raises), and this goes red either way."""
    _write(
        tmp_path,
        _healthy()
        + [
            {"ts": "?", "bot": "b", "kind": "event", "event": "startup_failed", "error": "x"},
            _event("startup", "2026-08-05T13:05:00+00:00", previous_run_clean=True),
        ],
    )

    assert "startup_failed" in _keys(lr.review_bot("b", tmp_path, RUNNING, now=NOW))


def test_clearing_a_failed_start_does_not_silence_the_RESTART_LOOP(tmp_path):
    """The two ask different questions: this counts STARTS, that counts failures. A bot flapping
    its way to a start must still be reported, and suppressing both from one signal would hide
    exactly the case where a bot keeps dying and coming back."""
    rows = _healthy() + [_event("startup_failed", "2026-08-05T13:00:00+00:00", error="x")]
    for i in range(lr.RESTART_LOOP):
        rows.append(_event("startup", f"2026-08-05T14:0{i}:00+00:00", previous_run_clean=False))
    _write(tmp_path, rows)
    found = _keys(lr.review_bot("b", tmp_path, RUNNING, now=NOW))

    assert "startup_failed" not in found
    assert "restart_loop" in found


# ── saying it once ───────────────────────────────────────────────────────────
def test_the_same_halt_keeps_one_key_across_runs(tmp_path):
    """Run hourly, alert once. A key per KIND of problem would do this correctly and then never
    alert again — including for a completely new halt next week."""
    _write(tmp_path, _healthy() + [_event("halted", "2026-08-05T17:00:00+00:00", reason="x")])
    first = lr.review_bot("b", tmp_path, RUNNING, now=NOW)
    second = lr.review_bot("b", tmp_path, RUNNING, now=NOW + timedelta(hours=1))

    assert {f.key for f in first} & {f.key for f in second}, "the same halt changed its key"


def test_the_still_halted_finding_keys_on_the_HALT_not_on_the_heartbeat(tmp_path):
    """🔴 THE 2026-08-07 NOTIFICATION SPAM. Watched red against HEAD.

    `halted_now` fires off the LATEST PULSE, and a pulse is written every 15 minutes — so keying
    it on the pulse's timestamp minted a brand-new dedup key on every hourly run. Aaron got one
    Telegram message an hour, all night, about a single halt that started at 06:15.

    ⚠ **The test above did not catch it and could not have**, which is the part worth carrying:
    it asserts the two runs SHARE a key (an intersection), and they do — the stable `halted:` key
    is in both. A finding that re-keys itself every run is invisible to a test that only asks
    whether *something* matched. Assert on the key that is supposed to be stable, by name.
    """

    def _now_key(at):
        # 🔴 The pulse is re-stamped for each run, and that is the FIXTURE being realistic rather
        # than a convenience. A halted bot is still turning its loop — that is the entire point of
        # this finding — so it keeps heartbeating every 15 minutes and its newest pulse is always
        # recent. The first version of this test wrote the pulses ONCE and moved the clock an hour,
        # i.e. a halted bot that stopped heartbeating, which is a different incident with its own
        # ALERT. It went red when the present tense started requiring a current heartbeat
        # (2026-09-03), and satisfying it would have meant claiming "right now" off a stale row.
        # **A fixture LESS capable than production hides the fix the same way an over-capable one
        # hides the defect.**
        rows = _healthy() + [_event("halted", "2026-08-05T14:00:00+00:00", reason="x")]
        rows[-2] = _pulse(
            (at - timedelta(minutes=5)).isoformat(timespec="seconds"), bridge_state="halted"
        )
        _write(tmp_path, rows)
        found = lr.review_bot("b", tmp_path, RUNNING, now=at)
        return next(f.key for f in found if f.key.startswith("halted_now:"))

    # Two runs an hour apart, reading the same file. Same incident, so: the same key.
    assert _now_key(NOW) == _now_key(NOW + timedelta(hours=1))
    # And it names the HALT's own timestamp, so a NEW halt still gets a new key.
    assert _now_key(NOW).endswith("2026-08-05T14:00:00+00:00")


def test_a_second_distinct_halt_gets_its_own_key(tmp_path):
    """🔴 The dedup bug that is silent: keying on the kind of thing means the second incident is
    never reported."""
    _write(
        tmp_path,
        _healthy()
        + [
            _event("halted", "2026-08-05T14:00:00+00:00", reason="first"),
            _event("halted", "2026-08-05T17:00:00+00:00", reason="second"),
        ],
    )
    keys = {
        f.key for f in lr.review_bot("b", tmp_path, RUNNING, now=NOW) if f.key.startswith("halted:")
    }

    assert len(keys) == 2


def test_an_unreadable_state_file_re_announces_rather_than_suppressing(monkeypatch, tmp_path):
    """⚠ The failure direction matters. Re-announcing a live finding is noisy exactly once;
    swallowing one is silent for ever."""
    monkeypatch.setattr(lr, "STATE_FILE", tmp_path / "nope" / "state.json")
    assert lr.load_state() == {}


# ── the standing flag ────────────────────────────────────────────────────────
def test_the_flag_file_is_written_and_carries_the_worst_level(tmp_path):
    """The chip on the Bots page. It survives a notification you scrolled past."""
    lr.write_flag(
        tmp_path,
        "b",
        [lr.Finding("a:1", lr.WARN, "warn", "d"), lr.Finding("b:2", lr.ALERT, "alert", "d")],
    )
    got = json.loads((tmp_path / "review.json").read_text())

    assert got["level"] == lr.ALERT
    assert len(got["findings"]) == 2


def test_a_clean_run_still_writes_the_flag_so_its_own_death_is_visible(tmp_path):
    """🔴 It DELETED the file when clean until 2026-09-03, which hid this reviewer's own death.

    An absent file meant *nothing to review* and it also meant *nobody looked*, so a dead hourly
    task left its last flag sitting on the page looking current and no reader could tell. Now the
    timestamp is the evidence the reviewer is alive, and an empty findings list is a positive
    statement that a run happened and found nothing. Watched RED against HEAD, which deleted it.
    """
    lr.write_flag(tmp_path, "b", [lr.Finding("a:1", lr.ALERT, "t", "d")])
    lr.write_flag(tmp_path, "b", [])
    got = json.loads((tmp_path / "review.json").read_text())

    assert got["findings"] == []
    assert got["checked_at"]


def test_a_clean_run_is_not_stamped_WARN(tmp_path):
    """A clean flag carrying the worst-of-nothing level is a wrong value waiting for a reader.

    The Bots page never sees it (it gates on a non-empty findings list), which is exactly why it
    has to be right here — nothing downstream would correct it. Watched RED against HEAD, where
    an empty list fell through the worst-of test onto WARN.
    """
    lr.write_flag(tmp_path, "b", [])

    assert json.loads((tmp_path / "review.json").read_text())["level"] == lr.OK
    assert lr.OK not in (lr.WARN, lr.ALERT)


def test_the_flag_is_not_written_into_bot_state(tmp_path):
    """⚠ Its own file on purpose: the runner rewrites `bot_state.json` every poll through a
    read-modify-write, so a review written there would race the heartbeat and could be lost —
    or could clobber a balance on its way past."""
    lr.write_flag(tmp_path, "b", [lr.Finding("a:1", lr.ALERT, "t", "d")])

    assert (tmp_path / "review.json").exists()
    assert not (tmp_path / "bot_state.json").exists()


# ── the console it has to survive ────────────────────────────────────────────
def test_findings_print_on_a_cp1252_console(tmp_path, monkeypatch, capsys):
    """🔴 Found by RUNNING it on the VPS, not by reading it. A Windows console is cp1252 and
    cannot encode the arrows, dashes and icons a finding is written with — and Python does not
    degrade, it raises `UnicodeEncodeError`. So the first real run died while PRINTING a finding,
    which means a scheduled task that detects a halted bridge crashes on its way to telling you.

    ⚠ `algos/live/runner._make_logger` carries the identical fix for the identical reason. This is
    the second module here to need it, so it is a rule for anything that prints on that box: an
    unencodable character must cost a glyph, never the message.
    """
    _write(
        tmp_path,
        _healthy()
        + [_event("halted", "2026-08-05T17:00:00+00:00", reason="emulator — broker disagree ⚠")],
    )

    monkeypatch.setattr(lr._bot_state, "BOT_INSTANCES", {"b": tmp_path})
    monkeypatch.setattr(lr._bot_state, "BOT_NAMES", {"b": "Bot — One"})
    monkeypatch.setattr(lr._bot_state, "read_bot", lambda k: RUNNING)
    monkeypatch.setattr(lr, "STATE_FILE", tmp_path / "state.json")

    assert lr.main(["--dry-run"]) == 0
    assert "REVIEW" in capsys.readouterr().out


# ── a halt that RECOVERED reads as history, not as an open incident ───────────
def test_a_recovered_halt_is_reported_in_the_past_tense(tmp_path):
    """🔴 Watched red against HEAD.

    These findings are sticky by design — `review.json` keeps a chip on the Bots page so a
    Telegram line you scrolled past at 3am is not the only record. That stickiness is exactly
    what made the wording a defect: a halt that ended hours ago went on saying *"the bot is
    placing nothing … Check the account"*, so a recovered bot was indistinguishable from a
    broken one. Aaron read that chip on 2026-08-07 and asked why a running bot was flagged.
    """
    rows = _healthy() + [_event("halted", "2026-08-05T14:00:00+00:00", reason="they disagree")]
    _write(tmp_path, rows)  # the LAST pulse still says bridge_state live
    found = [
        f for f in lr.review_bot("b", tmp_path, RUNNING, now=NOW) if f.key.startswith("halted:")
    ]

    assert len(found) == 1
    assert found[0].level == lr.WARN  # not ALERT: nothing to act on right now
    assert "again" in found[0].title
    assert "is placing nothing" not in found[0].detail
    # ...and the reason is still carried, because "why did it halt" is the open question.
    assert "they disagree" in found[0].detail


def test_a_halt_that_is_STILL_halted_keeps_the_urgent_wording(tmp_path):
    """The other half. Softening a live halt would be far worse than the noise being fixed —
    this is the one finding nothing else in the system can see."""
    rows = _healthy() + [_event("halted", "2026-08-05T14:00:00+00:00", reason="they disagree")]
    rows[-2] = _pulse(rows[-2]["ts"], bridge_state="halted")
    _write(tmp_path, rows)
    found = [
        f for f in lr.review_bot("b", tmp_path, RUNNING, now=NOW) if f.key.startswith("halted:")
    ]

    assert len(found) == 1
    assert found[0].level == lr.ALERT
    assert "is placing nothing" in found[0].title


def test_the_key_is_the_SAME_whether_it_recovered_or_not(tmp_path):
    """⚠ Load-bearing, not incidental. The tense follows the CURRENT bridge state, so the same
    incident is rendered both ways over its life — and if the key moved with the wording, the
    moment a bot recovered it would re-announce a halt you had already been told about.

    This is the `_ts` / `_at` split doing its job: the key names the occurrence, the text
    describes it. Improving wording must never wake the channel up.
    """
    halted = _healthy() + [_event("halted", "2026-08-05T14:00:00+00:00", reason="x")]
    recovered = list(halted)
    halted[-2] = _pulse(halted[-2]["ts"], bridge_state="halted")

    _write(tmp_path, halted)
    a = {
        f.key for f in lr.review_bot("b", tmp_path, RUNNING, now=NOW) if f.key.startswith("halted:")
    }
    _write(tmp_path, recovered)
    b = {
        f.key for f in lr.review_bot("b", tmp_path, RUNNING, now=NOW) if f.key.startswith("halted:")
    }

    assert a == b


# ── the tense the record can actually support ────────────────────────────────
#
# 🔴 Every test below is one failure: the newest row on file said HALTED, and the finding read that
# as the present tense whatever else was true. A bot that halted and was then STOPPED went on
# saying *"Bridge is HALTED right now … it is still running and still looks healthy everywhere
# else"* for the rest of the two-day window — every clause false. Third time a sticky present-tense
# claim has been reported here, after the halt wording (2026-08-07) and the refused settings
# (2026-09-03), which is why the answer is a named function with three values instead of a bool.


def _halted_last(at_minutes_ago: int = 5) -> list:
    """A record whose newest heartbeat says the bridge is halted."""
    rows = _healthy(minutes_back=at_minutes_ago) + [
        _event("halted", "2026-08-05T14:00:00+00:00", reason="they disagree")
    ]
    rows[-2] = _pulse(rows[-2]["ts"], bridge_state="halted")
    return rows


def _halt_finding(tmp_path, rows, state):
    _write(tmp_path, rows)
    found = lr.review_bot("b", tmp_path, state, now=NOW)
    return [f for f in found if f.key.startswith("halted:")], _keys(found)


def test_a_STOPPED_bot_is_not_reported_as_halted_RIGHT_NOW(tmp_path):
    """🔴 The reported defect, watched RED against HEAD.

    A bot that halted and was then stopped is not running, so nothing about it is happening right
    now — but the chip claimed it was, in the present tense, for up to two days.
    """
    halted, keys = _halt_finding(tmp_path, _halted_last(), STOPPED)

    assert "halted_now" not in keys
    assert len(halted) == 1
    assert halted[0].level == lr.WARN
    assert "cannot say" in halted[0].title
    assert "is placing nothing" not in halted[0].detail


def test_a_STALE_heartbeat_cannot_support_the_present_tense(tmp_path):
    """A bot that is meant to be running and has not heartbeat in hours cannot be described as
    halted *now* off a row that old. Watched RED against HEAD.

    ⚠ No severity is lost: a running bot that went quiet raises its own ALERT (`silent:`), so
    demoting this one removes a second, over-confident alarm for one event rather than a warning.
    """
    halted, keys = _halt_finding(tmp_path, _halted_last(at_minutes_ago=200), RUNNING)

    assert "halted_now" not in keys
    assert "silent" in keys
    assert (
        next(
            f for f in lr.review_bot("b", tmp_path, RUNNING, now=NOW) if f.key.startswith("silent")
        ).level
        == lr.ALERT
    )
    assert halted[0].level == lr.WARN


def test_a_FRESH_halted_heartbeat_on_a_running_bot_is_still_urgent(tmp_path):
    """The half that must not soften. This is the one finding nothing else in the system sees.

    ⚠ Cannot go red against HEAD, which reported the present tense unconditionally. Proven by
    MUTATION: forcing the tense to unknown reddens it.
    """
    halted, keys = _halt_finding(tmp_path, _halted_last(), RUNNING)

    assert "halted_now" in keys
    assert halted[0].level == lr.ALERT
    assert "is placing nothing" in halted[0].title


def test_a_heartbeat_with_an_unreadable_TIME_keeps_the_present_tense(tmp_path):
    """Of the two wrong answers, over-reporting a halt sends somebody to look at an account and
    under-reporting hides a bot placing nothing. This one fails loud on purpose.

    ⚠ Cannot go red against HEAD. Proven by MUTATION: treating an unreadable timestamp as stale
    reddens it.
    """
    rows = _halted_last()
    rows[-2] = {"ts": "?", "bot": "b", "kind": "pulse", "link": True, "bridge_state": "halted"}
    halted, keys = _halt_finding(tmp_path, rows, RUNNING)

    assert "halted_now" in keys
    assert halted[0].level == lr.ALERT


def test_a_STOPPED_bot_whose_last_heartbeat_was_LIVE_still_reads_as_RECOVERED(tmp_path):
    """ "It recovered" and "the record cannot say" are the two values that must not merge, and this
    is the reassuring side. Its last heartbeat said live, which stays true after a deliberate stop.

    ⚠ Cannot go red against HEAD. Proven by MUTATION: deciding the tense from the bot's status
    before reading the heartbeat reddens it.
    """
    rows = _healthy() + [_event("halted", "2026-08-05T14:00:00+00:00", reason="they disagree")]
    halted, keys = _halt_finding(tmp_path, rows, STOPPED)

    assert "halted_now" not in keys
    assert "again" in halted[0].title
    assert halted[0].level == lr.WARN


def test_the_three_tenses_are_three_distinct_values(tmp_path):
    """A bool cannot express "the record cannot say", which is why this used to be one.

    ⚠ It "fails" against HEAD with an AttributeError, which proves the constants are missing and
    nothing about behaviour — a vacuous red. Proven by MUTATION instead: collapsing unknown onto
    recovered reddens it, and reddens the stopped-bot case beside it.
    """
    assert len({lr.HALT_NOW, lr.HALT_RECOVERED, lr.HALT_UNKNOWN}) == 3


# ── the orphaned opening balance reaches a person (2026-09-06) ───────────────
#
# 🔴 `bot_state.suspect_anchors` has spotted this since 2026-09-05 and wrote it to a file NOBODY
# READ. The guard fired into an empty room, which is worth less than no guard at all — the next
# reader takes the silence for a clean check. These cover the half that tells somebody.

SUSPECT = {
    "status": "live",
    "starting_balance": 14538.88,
    "starting_balance_suspect": {"old": 9996.99},
}


def _anchor_titles(state, inst=None):
    return [f.title for f in lr._suspect_anchor("b", state)]


def test_an_orphaned_opening_balance_is_reported(tmp_path):
    """WATCHED RED against HEAD — `_suspect_anchor` did not exist, so this raised AttributeError.

    MUTATION: return `[]` unconditionally and this goes red.
    """
    assert _anchor_titles(SUSPECT), "the guard's finding never reaches a person"


def test_a_bot_with_NO_suspect_record_reports_nothing():
    """The control. A finding that fires on every bot is one nobody reads.

    MUTATION: drop the emptiness test and this goes red.
    """
    assert _anchor_titles({"status": "live", "starting_balance": 9996.99}) == []


def test_an_EMPTY_suspect_record_is_not_a_finding():
    """`{}` means the guard ran and found nothing — the opposite of a problem. Reporting it would
    make *checked and clean* and *something is wrong* the same message.

    MUTATION: test only for the key's presence and this goes red.
    """
    assert _anchor_titles({"status": "live", "starting_balance_suspect": {}}) == []


def test_a_STOPPED_bot_still_reports_it(tmp_path):
    """🔴 This is a fact about the STATE FILE, not about the health record, so the *do not cry
    wolf over a deliberately stopped bot* rule does not apply — a wrong opening balance is just
    as wrong while the bot is off, and it is on screen the whole time.

    ⚠ **It drives `review_bot`, not the helper.** The gate being guarded against lives in the
    CALLER, so a test calling `_suspect_anchor` directly passes with the gate in place — measured,
    not reasoned: the first version of this test did exactly that and survived its own mutation.

    MUTATION: gate the call behind `supposed_to_run` and this goes red.
    """
    inst = tmp_path / "inst"
    inst.mkdir()
    stopped = dict(SUSPECT, status="stopped")
    titles = [f.title for f in lr.review_bot("b", inst, stopped, now=NOW)]
    assert any("opening balance" in t for t in titles), titles


def test_an_UNREADABLE_health_record_does_not_swallow_it(tmp_path):
    """🔴 The path that would have hidden it. `review_bot` RETURNS EARLY when the record cannot
    be read, so a finding raised after that point is lost for exactly the bot most likely to need
    looking at.

    MUTATION: move the call below the `rows, problem` block and this goes red.
    """
    inst = tmp_path / "inst"
    inst.mkdir()  # no ledger directory at all — unreadable
    titles = [f.title for f in lr.review_bot("b", inst, SUSPECT, now=NOW)]
    assert any("opening balance" in t for t in titles), titles


def test_the_message_names_BOTH_readings_and_states_neither(tmp_path):
    """🔴 The property that keeps this honest. A rename and an ordinary second bot joining a
    grown account are the SAME signature, and the second one is CORRECT — so a message reading
    *this is wrong* sends somebody to break a good number.

    MUTATION: drop either branch from the sentence and this goes red.
    """
    detail = lr._suspect_anchor("b", SUSPECT)[0].detail.lower()
    assert "renamed" in detail
    assert "second bot" in detail
    assert "nothing to do" in detail


def test_the_message_carries_BOTH_figures():
    """A finding naming no numbers sends the reader to go and find them, which is the work the
    alert exists to save.

    MUTATION: drop either figure from the sentence and this goes red.
    """
    detail = lr._suspect_anchor("b", SUSPECT)[0].detail
    assert "14,538.88" in detail
    assert "9,996.99" in detail


def test_a_RE_ANCHOR_AT_A_DIFFERENT_FIGURE_is_a_new_occurrence():
    """🔴 The de-duplicating-alerter bug this module's own `Finding` class warns about. Keying on
    the bot alone announces the first orphaning and then stays silent through every later one.

    MUTATION: key on `bot_key` alone and this goes red.
    """
    first = lr._suspect_anchor("b", SUSPECT)[0].key
    moved = lr._suspect_anchor("b", dict(SUSPECT, starting_balance=20000.0))[0].key
    assert first != moved


def test_THE_SAME_orphaning_keeps_ONE_key():
    """The other half of the same rule — an unchanged finding must not re-announce hourly."""
    assert lr._suspect_anchor("b", SUSPECT)[0].key == lr._suspect_anchor("b", dict(SUSPECT))[0].key


def test_an_UNREADABLE_figure_does_not_take_the_message_down():
    """🔴 This runs unattended. A malformed number raising inside the one message written to
    report a problem is how `watch_broker_costs.py` became unable to announce its own failure.

    MUTATION: format with a bare f-string conversion and this goes red with ValueError/TypeError.
    """
    broken = {"status": "live", "starting_balance": None, "starting_balance_suspect": {"old": "x"}}
    detail = lr._suspect_anchor("b", broken)[0].detail
    assert "unreadable" in detail.lower(), detail


def test_a_suspect_record_of_the_WRONG_SHAPE_is_ignored_rather_than_crashing():
    """A hand-edited state file, or a future writer changing the shape. Refusing to read it is
    right; taking the hourly reviewer down over it is not."""
    for bad in ("nonsense", 5, [1, 2], None):
        assert _anchor_titles({"status": "live", "starting_balance_suspect": bad}) == []
