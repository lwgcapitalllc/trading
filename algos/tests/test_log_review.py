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

import pytest

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
    nothing at all."""
    _write(tmp_path, _healthy() + [_event("halted", "2026-08-05T17:00:00+00:00",
                                          reason="emulator and broker disagree")])
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
    _write(tmp_path, _healthy() + [
        _event("mt5_link_lost", "2026-08-05T03:00:00+00:00"),
        _event("mt5_link_restored", "2026-08-05T03:50:00+00:00", down_seconds=3000),
    ])
    found = lr.review_bot("b", tmp_path, RUNNING, now=NOW)

    assert "mt5_outage" in _keys(found)
    assert "50 minutes" in next(f for f in found if f.key.startswith("mt5_outage")).detail


def test_a_gap_between_heartbeats_that_has_closed_is_reported(tmp_path):
    """A stall the watchdog restarted at 3am: its alert has been and gone, and nothing kept the
    fact that it happened."""
    _write(tmp_path, [
        _event("startup", "2026-08-05T10:00:00+00:00", previous_run_clean=True),
        _pulse("2026-08-05T12:00:00+00:00"),
        _pulse("2026-08-05T14:00:00+00:00"),          # two hours, no beat
        _pulse((NOW - timedelta(minutes=5)).isoformat(timespec="seconds")),
    ])
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
    _write(tmp_path, [
        _event("startup", "2026-08-05T10:00:00+00:00", previous_run_clean=True),
        _pulse("2026-08-05T11:00:00+00:00"),
    ])
    found = lr.review_bot("b", tmp_path, RUNNING, now=NOW)

    assert "silent" in _keys(found)
    assert next(f for f in found if f.key.startswith("silent")).level == lr.ALERT


# ── lifecycle ────────────────────────────────────────────────────────────────
def test_a_kill_is_reported_on_the_next_start(tmp_path):
    _write(tmp_path, _healthy() + [
        _event("startup", "2026-08-05T16:00:00+00:00", previous_run_clean=False)])

    assert "unclean" in _keys(lr.review_bot("b", tmp_path, RUNNING, now=NOW))


def test_a_clean_restart_is_not_reported(tmp_path):
    """Restarting a bot on purpose is ordinary. Only an ending nobody recorded is news."""
    _write(tmp_path, _healthy() + [
        _event("shutdown", "2026-08-05T15:00:00+00:00", exit_code=0, reason="stop requested"),
        _event("startup", "2026-08-05T15:01:00+00:00", previous_run_clean=True)])

    assert "unclean" not in _keys(lr.review_bot("b", tmp_path, RUNNING, now=NOW))


def test_repeated_restarts_are_an_alert(tmp_path):
    rows = _healthy()
    for h in (11, 12, 13, 14):
        rows.append(_event("startup", f"2026-08-05T{h}:00:00+00:00", previous_run_clean=True))
    _write(tmp_path, rows)
    found = lr.review_bot("b", tmp_path, RUNNING, now=NOW)

    assert "restart_loop" in _keys(found)
    assert next(f for f in found if f.key.startswith("restart_loop")).level == lr.ALERT


def test_a_refused_config_change_is_reported(tmp_path):
    """The page can show settings the bot is not using. That is a wrong-number problem, and it
    is exactly the class this repo keeps meeting."""
    _write(tmp_path, _healthy() + [
        _event("config_change_refused", "2026-08-05T14:00:00+00:00", changes="exec_risk_pct")])

    assert "config_refused" in _keys(lr.review_bot("b", tmp_path, RUNNING, now=NOW))


def test_a_failed_start_and_a_version_mismatch_are_alerts(tmp_path):
    _write(tmp_path, _healthy() + [
        _event("startup_failed", "2026-08-05T13:00:00+00:00", error="bad config"),
        _event("version_mismatch", "2026-08-05T13:05:00+00:00", detail="hash differs")])
    found = lr.review_bot("b", tmp_path, RUNNING, now=NOW)

    assert {"startup_failed", "version_mismatch"} <= _keys(found)
    assert all(f.level == lr.ALERT for f in found
               if f.key.split(":")[0] in {"startup_failed", "version_mismatch"})


# ── saying it once ───────────────────────────────────────────────────────────
def test_the_same_halt_keeps_one_key_across_runs(tmp_path):
    """Run hourly, alert once. A key per KIND of problem would do this correctly and then never
    alert again — including for a completely new halt next week."""
    _write(tmp_path, _healthy() + [_event("halted", "2026-08-05T17:00:00+00:00", reason="x")])
    first = lr.review_bot("b", tmp_path, RUNNING, now=NOW)
    second = lr.review_bot("b", tmp_path, RUNNING, now=NOW + timedelta(hours=1))

    assert {f.key for f in first} & {f.key for f in second}, "the same halt changed its key"


def test_a_second_distinct_halt_gets_its_own_key(tmp_path):
    """🔴 The dedup bug that is silent: keying on the kind of thing means the second incident is
    never reported."""
    _write(tmp_path, _healthy() + [
        _event("halted", "2026-08-05T14:00:00+00:00", reason="first"),
        _event("halted", "2026-08-05T17:00:00+00:00", reason="second")])
    keys = {f.key for f in lr.review_bot("b", tmp_path, RUNNING, now=NOW)
            if f.key.startswith("halted:")}

    assert len(keys) == 2


def test_an_unreadable_state_file_re_announces_rather_than_suppressing(monkeypatch, tmp_path):
    """⚠ The failure direction matters. Re-announcing a live finding is noisy exactly once;
    swallowing one is silent for ever."""
    monkeypatch.setattr(lr, "STATE_FILE", tmp_path / "nope" / "state.json")
    assert lr.load_state() == {}


# ── the standing flag ────────────────────────────────────────────────────────
def test_the_flag_file_is_written_and_carries_the_worst_level(tmp_path):
    """The chip on the Bots page. It survives a notification you scrolled past."""
    lr.write_flag(tmp_path, "b", [
        lr.Finding("a:1", lr.WARN, "warn", "d"),
        lr.Finding("b:2", lr.ALERT, "alert", "d")])
    got = json.loads((tmp_path / "review.json").read_text())

    assert got["level"] == lr.ALERT
    assert len(got["findings"]) == 2


def test_the_flag_is_cleared_when_the_bot_is_clean(tmp_path):
    """A stale flag is worse than none — it trains you to ignore the chip."""
    lr.write_flag(tmp_path, "b", [lr.Finding("a:1", lr.ALERT, "t", "d")])
    lr.write_flag(tmp_path, "b", [])

    assert not (tmp_path / "review.json").exists()


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
    _write(tmp_path, _healthy() + [
        _event("halted", "2026-08-05T17:00:00+00:00", reason="emulator — broker disagree ⚠")])

    monkeypatch.setattr(lr._bot_state, "BOT_INSTANCES", {"b": tmp_path})
    monkeypatch.setattr(lr._bot_state, "BOT_NAMES", {"b": "Bot — One"})
    monkeypatch.setattr(lr._bot_state, "read_bot", lambda k: RUNNING)
    monkeypatch.setattr(lr, "STATE_FILE", tmp_path / "state.json")

    assert lr.main(["--dry-run"]) == 0
    assert "needs review" in capsys.readouterr().out
