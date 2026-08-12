"""Can you tell, from the files alone, that this bot is healthy — and that it died?

**Why this file exists.** Aaron, 2026-08-05: *"anything that's a log about how the bot is
performing so that if there's a bug, something is silently dying, or something is going wrong,
we should know from the debug logs."* That is a claim about what the files can PROVE, and the
awkward property of every failure it names is that it produces no output. A killed process
writes nothing. A wedged loop writes nothing. A quiet Sunday also writes nothing — which is why
"the file is short today" has never been a signal.

Two mechanisms carry the whole requirement, and the tests here are about both:

1. **Every exit this process CHOOSES writes a `shutdown` record.** That is what makes the
   converse informative: no shutdown record ⇒ it was killed or the box died. Until this pass
   only the clean Ctrl-C path wrote one, so the absence meant *killed, crashed, or any of three
   ordinary refusals* — no signal at all. The tests walk each refusal.

2. **A `pulse` on a fixed cadence.** The health stream's rhythm is what turns a stall into a
   measurable gap rather than an absence somebody has to interpret. It is the record whose
   ABSENCE is the signal, so what matters is that nothing can quietly suppress it.

⚠ Nothing here touches MT5. These are the file-writing seams only.
"""

from __future__ import annotations

import json
import logging
import sys
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace

import pytest

_REPO = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(_REPO / "algos" / "live"))
import live_config  # noqa: E402
import runner  # noqa: E402


@pytest.fixture(autouse=True)
def _fresh_logger():
    """`logging.getLogger(name)` is process-global — see `test_live_runner_startup.py`."""
    yield
    log = logging.getLogger("smoke")
    for h in list(log.handlers):
        h.close()
        log.removeHandler(h)


def _cfg(tmp_path, monkeypatch, **overrides):
    body = {"bot_key": "smoke", "mt5_path": "C:/MT5/terminal64.exe", "account": 1,
            "server": "Demo", "symbol": "XAUUSD", "magic": 1}
    body.update(overrides)
    (tmp_path / "smoke").mkdir(parents=True, exist_ok=True)
    (tmp_path / "smoke" / "config.json").write_text(json.dumps(body))
    monkeypatch.setattr(live_config, "_INSTANCES", tmp_path)
    return live_config.load("smoke")


def _health(cfg) -> list[dict]:
    day = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    path = cfg.instance_dir / "ledger" / f"health-{day}.jsonl"
    if not path.exists():
        return []
    return [json.loads(x) for x in path.read_text(encoding="utf-8").splitlines() if x]


def _events(cfg, name: str) -> list[dict]:
    return [r for r in _health(cfg) if r.get("event") == name]


# ── every chosen exit says so ────────────────────────────────────────────────
def test_a_refusal_to_start_still_records_how_the_run_ended(tmp_path, monkeypatch):
    """🔴 THE invariant. `already_running()` returns before anything else happens, and it used
    to return with the health stream completely silent — so a start that declined to start was
    indistinguishable from a start that was killed. It is also exactly the event somebody is
    looking for when they ask why a restart "did nothing"."""
    cfg = _cfg(tmp_path, monkeypatch)
    r = runner.LiveRunner(cfg)
    monkeypatch.setattr(r, "already_running", lambda: True)

    assert r.run() == 0
    ends = _events(cfg, "shutdown")
    assert len(ends) == 1
    assert ends[0]["exit_code"] == 0
    assert "already running" in ends[0]["reason"]


def test_a_failed_connect_records_its_exit(tmp_path, monkeypatch):
    """Exit 3 wrote nothing until 2026-08-05. A bot that cannot reach its terminal at startup is
    one of the likeliest real failures, and it left the same trace as a `taskkill`."""
    cfg = _cfg(tmp_path, monkeypatch)
    r = runner.LiveRunner(cfg)
    monkeypatch.setattr(r, "already_running", lambda: False)
    monkeypatch.setattr(r, "_bind_code", lambda: None)
    monkeypatch.setattr(runner, "verify_pin", lambda *a, **k: "abc123")
    monkeypatch.setattr(r, "connect", lambda: False)
    monkeypatch.setattr(r, "_notify", lambda *a, **k: None)

    assert r.run() == 3
    ends = _events(cfg, "shutdown")
    assert len(ends) == 1 and ends[0]["exit_code"] == 3
    assert "connect" in ends[0]["reason"]


def test_an_exception_escaping_the_run_is_recorded_and_still_raised(tmp_path, monkeypatch):
    """A crash is an ending too. Recording it must not swallow it — the exit code a supervisor
    reads is how the watchdog decides to restart, and a crash reported as a clean stop is a bot
    nobody brings back."""
    cfg = _cfg(tmp_path, monkeypatch)
    r = runner.LiveRunner(cfg)

    def _boom():
        raise RuntimeError("disk on fire")

    monkeypatch.setattr(r, "already_running", _boom)

    with pytest.raises(RuntimeError, match="disk on fire"):
        r.run()
    ends = _events(cfg, "shutdown")
    assert len(ends) == 1
    assert "disk on fire" in ends[0]["reason"]


def test_a_keyboard_interrupt_is_recorded_as_an_ending(tmp_path, monkeypatch):
    """`KeyboardInterrupt` is a `BaseException`, so a bare `except Exception` misses it — and
    Ctrl-C is how this bot most often stops by hand. Catching `BaseException` here is deliberate
    and the exception continues on its way."""
    cfg = _cfg(tmp_path, monkeypatch)
    r = runner.LiveRunner(cfg)

    def _interrupt():
        raise KeyboardInterrupt()

    monkeypatch.setattr(r, "already_running", _interrupt)

    with pytest.raises(KeyboardInterrupt):
        r.run()
    assert len(_events(cfg, "shutdown")) == 1


def test_exactly_one_shutdown_record_per_run(tmp_path, monkeypatch):
    """⚠ The clean path used to write its own `shutdown` inside the loop, and `run()` now writes
    one for every path. Both would put TWO closing lines on the one exit that always worked, and
    a count of runs that disagrees with a count of stops is the sort of thing that makes a
    post-mortem argue with itself."""
    cfg = _cfg(tmp_path, monkeypatch)
    r = runner.LiveRunner(cfg)
    monkeypatch.setattr(r, "already_running", lambda: True)
    r.run()

    assert len(_events(cfg, "shutdown")) == 1


def test_a_ledger_failure_cannot_change_the_exit_code(tmp_path, monkeypatch):
    """The record is best-effort by design. A logging problem that changed what a trading
    process returns would let the audit trail decide whether the watchdog restarts the bot."""
    cfg = _cfg(tmp_path, monkeypatch)
    r = runner.LiveRunner(cfg)
    monkeypatch.setattr(r, "already_running", lambda: True)
    monkeypatch.setattr(r.ledger, "event",
                        lambda *a, **k: (_ for _ in ()).throw(OSError("disk full")))

    assert r.run() == 0


# ── the silent-death detector, end to end ────────────────────────────────────
def test_a_start_after_a_kill_says_the_previous_run_was_not_clean(tmp_path, monkeypatch):
    """The whole point, exercised through the runner rather than the ledger: the evidence of a
    hard kill has to be written by the NEXT process, because the killed one wrote nothing."""
    cfg = _cfg(tmp_path, monkeypatch)
    killed = runner.LiveRunner(cfg)
    killed.ledger.event("startup")          # ...and then the process vanished

    r = runner.LiveRunner(cfg)
    monkeypatch.setattr(r, "already_running", lambda: False)
    monkeypatch.setattr(r, "_bind_code", lambda: None)
    monkeypatch.setattr(runner, "verify_pin", lambda *a, **k: "abc123")
    monkeypatch.setattr(r, "connect", lambda: False)
    monkeypatch.setattr(r, "_notify", lambda *a, **k: None)
    r.run()

    assert _events(cfg, "startup")[-1]["previous_run_clean"] is False


def test_the_first_ever_start_reports_unknown_not_clean(tmp_path, monkeypatch):
    """⚠ Three states, not two — the rule `mt5_link` wrote. There being no history is not
    evidence of a tidy shutdown, and `False` here would raise an alarm on every new bot."""
    cfg = _cfg(tmp_path, monkeypatch)
    r = runner.LiveRunner(cfg)
    monkeypatch.setattr(r, "already_running", lambda: False)
    monkeypatch.setattr(r, "_bind_code", lambda: None)
    monkeypatch.setattr(runner, "verify_pin", lambda *a, **k: "abc123")
    monkeypatch.setattr(r, "connect", lambda: False)
    monkeypatch.setattr(r, "_notify", lambda *a, **k: None)
    r.run()

    assert _events(cfg, "startup")[0]["previous_run_clean"] is None


# ── the pulse ────────────────────────────────────────────────────────────────
def _pulse_ready(tmp_path, monkeypatch):
    cfg = _cfg(tmp_path, monkeypatch)
    r = runner.LiveRunner(cfg)
    r.bridge = SimpleNamespace(state=SimpleNamespace(value="live"), _pos_ticket=None)
    r.feed = SimpleNamespace(last_bar_time="2026-08-05 12:00", gap_bars=lambda: 0)
    r._bar_index = 7
    return cfg, r


def test_the_first_poll_pulses_immediately(tmp_path, monkeypatch):
    """A run that starts and dies inside its first quarter hour must not leave a health stream
    with no pulse in it at all — that window is exactly where a start-up problem shows up."""
    cfg, r = _pulse_ready(tmp_path, monkeypatch)
    r._maybe_pulse(link_up=True, balance=2000.0)

    beats = [x for x in _health(cfg) if x["kind"] == "pulse"]
    assert len(beats) == 1
    assert beats[0]["link"] is True and beats[0]["balance"] == 2000.0
    assert beats[0]["bars_seen"] == 7 and beats[0]["bridge_state"] == "live"


def test_the_pulse_is_rate_limited_not_written_every_poll(tmp_path, monkeypatch):
    """The loop polls every few seconds. An unthrottled pulse would bury the lifecycle records
    it sits beside, which is the "nothing overlapping" requirement failing from the inside."""
    cfg, r = _pulse_ready(tmp_path, monkeypatch)
    for _ in range(50):
        r._maybe_pulse(link_up=True, balance=2000.0)

    assert len([x for x in _health(cfg) if x["kind"] == "pulse"]) == 1


def test_a_blind_bot_still_pulses_and_says_it_is_blind(tmp_path, monkeypatch):
    """⚠ The 2026-08-04 outage in one line. A pulse that stopped when the link died would make a
    blind bot and a dead bot the same silence — and the balance must read `None`, never 0.0,
    because a fabricated zero and a measured zero are different facts."""
    cfg, r = _pulse_ready(tmp_path, monkeypatch)
    r._maybe_pulse(link_up=False, balance=None)

    beat = [x for x in _health(cfg) if x["kind"] == "pulse"][0]
    assert beat["link"] is False
    assert beat["balance"] is None


def test_every_pulse_names_the_account_its_other_fields_belong_to(tmp_path, monkeypatch):
    """🔴 The gap the 2026-08-12 account move left in the record.

    The health stream is one file per bot per DAY — nothing about it is keyed by account — and
    only `startup` named one, 2 rows out of 77 that day. When the terminal was logged onto a
    different account under a running bot, every pulse for the next two hours reported the NEW
    account's balance while the newest `startup` above them still said the OLD number. Reading
    back to the last startup is the only way to attribute a row, and for that whole window it
    gives the wrong answer; the single clue was the balance jumping five-fold mid-file, which is
    an inference rather than a record.

    `_check_account_identity` halts on that disagreement now, so it can last at most one poll —
    but a guard that makes a thing RARE does not make an unlabelled record CORRECT, and the rows
    written before the halt would still be mislabelled.
    """
    cfg, r = _pulse_ready(tmp_path, monkeypatch)
    r._observed_account = 700152905                 # what the terminal just said

    r._maybe_pulse(link_up=True, balance=9996.99)

    beat = [x for x in _health(cfg) if x["kind"] == "pulse"][0]
    assert beat["account"] == 700152905
    assert beat["balance"] == 9996.99, "the account named is the one this balance belongs to"


def test_a_pulse_that_could_not_ask_reports_no_account_rather_than_the_configured_one(
        tmp_path, monkeypatch):
    """The blind case. Falling back to `cfg.account` here would write the bot's BELIEF into a
    record whose whole job is saying what was OBSERVED — and it would do it at exactly the moment
    the belief is least likely to be checkable."""
    cfg, r = _pulse_ready(tmp_path, monkeypatch)
    r._observed_account = None

    r._maybe_pulse(link_up=False, balance=None)

    beat = [x for x in _health(cfg) if x["kind"] == "pulse"][0]
    assert beat["account"] is None


# ── the text log rolls by day ────────────────────────────────────────────────
def test_the_text_log_rolls_onto_a_new_file_at_midnight(tmp_path):
    """A bot runs for months without restarting, so the roll has to happen under it. It works by
    choosing a different NAME — nothing is renamed, because renaming a file Windows holds open
    raises a sharing violation, which is the trap `log_backup.py` records."""
    h = runner.DailyFileHandler(tmp_path, "smoke")
    h.setFormatter(logging.Formatter("%(message)s"))
    rec = logging.LogRecord("smoke", logging.INFO, __file__, 1, "before", None, None)

    h.emit(rec)
    h._day = "2026-08-04"          # pretend the last write was yesterday
    h.emit(logging.LogRecord("smoke", logging.INFO, __file__, 1, "after", None, None))
    h.close()

    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    assert (tmp_path / f"smoke-{today}.log").read_text(encoding="utf-8").splitlines() == [
        "before", "after"]


def test_a_log_write_failure_never_takes_the_bot_down(tmp_path, monkeypatch):
    """Same rule as the ledger: a logger that can kill the loop it observes is worse than a
    missing line."""
    h = runner.DailyFileHandler(tmp_path / "nope", "smoke")
    h.setFormatter(logging.Formatter("%(message)s"))
    monkeypatch.setattr(Path, "mkdir",
                        lambda *a, **k: (_ for _ in ()).throw(OSError("read-only")))
    monkeypatch.setattr(logging, "raiseExceptions", False)

    h.emit(logging.LogRecord("smoke", logging.INFO, __file__, 1, "x", None, None))
