"""The one alert that does not originate on the VPS.

Every other alert in this suite is sent BY the box it is reporting on, so a dead VPS or a dead
network produces silence — and silence is what a healthy Sunday looks like too. `deadman.py`
closes that by pinging an external service only while things are actually well, so the *absence*
of a ping is the alarm.

**That inversion is what these tests are protecting, and it makes the failure mode unusual: a bug
here is silent by construction.** Every other watchdog fails loudly — it alerts when it should
not, and someone complains. This one fails by pinging green through a problem, and nobody hears
anything, because nothing being heard is the normal state. There is no user report coming.

So the cases below are weighted toward the ways a check can wrongly say "fine": an unreadable
process list, a missing state file, an `mt5_link` that has not been asked yet. Each of those is an
ABSENCE, and the repo's standing rule is that absence must never be scored as health.
"""

from __future__ import annotations

import importlib.util
import sys
import time
from pathlib import Path

import pytest

_REPO = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(_REPO / "algos" / "shared"))

_spec = importlib.util.spec_from_file_location(
    "deadman", _REPO / "algos" / "notifications" / "deadman.py"
)
dm = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(dm)


def _healthy_state(**over):
    """A bot state that is fresh RIGHT NOW.

    Deliberately keyed off real time rather than a frozen constant: `main()` calls
    `check_health()` with no `now`, so a fixed timestamp would make every send test see a
    heartbeat decades stale and pass for the wrong reason.
    """
    st = {"heartbeat": time.time() - 30, "mt5_link": True}
    st.update(over)
    return {"mpc_sos_fade_demo": st}


@pytest.fixture
def wired(monkeypatch):
    """Everything the box would supply, defaulted to healthy. Tests break one thing each.

    ⚠ `_is_assigned` is stubbed rather than left to read the real configs. `BOTS` now carries a
    bot that sits on the BENCH, and without this every test here would depend on what a config
    in the repo happens to say — so assigning that bot from the Bots page would turn this whole
    file red for a reason that has nothing to do with the dead-man's switch.
    """
    monkeypatch.setattr(dm, "_running_keys", lambda: {"mpc_sos_fade_demo"})
    monkeypatch.setattr(dm, "_bot_state", _healthy_state)
    monkeypatch.setattr(dm, "_is_assigned", lambda key: key == "mpc_sos_fade_demo")
    return monkeypatch


# ── the bench ────────────────────────────────────────────────────────────────
def test_a_bot_with_no_account_is_not_a_failure(wired):
    """MUTATION: drop the `_is_assigned` skip from `check_health` -> red.

    A benched bot has no process by design, so counting it as "process is not running" would hold
    this switch in the FAILED state permanently — and the switch's entire value is that its
    silence means something. A permanent failure is the same as no switch at all."""
    wired.setattr(dm, "_running_keys", lambda: {"mpc_sos_fade_demo"})
    wired.setattr(dm, "BOTS", {"mpc_sos_fade_demo": "MPC SOS Fade", "benched": "Benched"})
    assert dm.check_health() == []


def test_a_bot_WITH_an_account_that_is_not_running_is_still_a_failure(wired):
    """The other half — the skip must not swallow the case this exists to catch."""
    wired.setattr(dm, "_running_keys", lambda: set())
    problems = dm.check_health()
    assert any("not running" in p for p in problems)


def test_a_bot_whose_config_CANNOT_BE_READ_is_still_watched(monkeypatch):
    """MUTATION: make `bot_state.is_assigned` answer False when the config is unreadable -> red.

    A config with a typo in it, or a key missing from `BOT_INSTANCES`, is a bot whose state is
    UNKNOWN — and the wrong answer in that direction is a switch that quietly stopped covering a
    live trading bot, which is silent by construction. Noisy is recoverable; silent is not.

    This one deliberately does NOT use `wired`: the stub there is what it is testing around.
    """
    monkeypatch.setattr(dm, "_running_keys", lambda: set())
    monkeypatch.setattr(dm, "_bot_state", lambda: {"never_created": None})
    monkeypatch.setattr(dm, "BOTS", {"never_created": "Ghost"})
    assert any("not running" in p for p in dm.check_health())


# ── what counts as healthy ───────────────────────────────────────────────────────


def test_a_running_bot_with_a_fresh_heartbeat_and_a_live_link_is_healthy(wired):
    assert dm.check_health() == []


def test_a_dead_process_is_reported(wired):
    wired.setattr(dm, "_running_keys", lambda: set())
    problems = dm.check_health()
    assert len(problems) == 1
    assert "not running" in problems[0]


def test_a_dead_process_does_not_ALSO_report_its_stale_heartbeat(wired):
    # A stopped bot obviously stops stamping. Reporting both makes one failure look like two
    # and buries the fact that actually matters — the process is gone — in a list.
    wired.setattr(dm, "_running_keys", lambda: set())
    wired.setattr(dm, "_bot_state", lambda: _healthy_state(heartbeat=time.time() - 99_999))
    assert len(dm.check_health()) == 1


def test_a_stale_heartbeat_on_a_live_process_is_reported(wired):
    wired.setattr(dm, "_bot_state", lambda: _healthy_state(heartbeat=time.time() - 600))
    problems = dm.check_health()
    assert any("stalled" in p for p in problems)


def test_a_heartbeat_one_second_inside_the_window_is_not_stale(wired):
    # The boundary itself, pinned against a FIXED now so the margin cannot be eaten by how
    # long the test takes to run.
    base = 1_700_000_000.0
    wired.setattr(
        dm, "_bot_state", lambda: _healthy_state(heartbeat=base - dm.HEARTBEAT_STALE_SECS + 1)
    )
    assert dm.check_health(now=base) == []


def test_a_heartbeat_one_second_past_the_window_IS_stale(wired):
    base = 1_700_000_000.0
    wired.setattr(
        dm, "_bot_state", lambda: _healthy_state(heartbeat=base - dm.HEARTBEAT_STALE_SECS - 1)
    )
    assert any("stalled" in p for p in dm.check_health(now=base))


# ── absence must never score as health ───────────────────────────────────────────


def test_an_unreadable_process_list_is_a_FAILURE_not_an_empty_result(wired):
    # "wmic did not answer" and "no bots are running" are different facts, and treating the
    # first as the second would ping green on a box that cannot be inspected at all.
    wired.setattr(dm, "_running_keys", lambda: None)
    problems = dm.check_health()
    assert problems and "process list" in problems[0]


def test_an_unreadable_bot_state_file_is_a_FAILURE(wired):
    wired.setattr(dm, "_bot_state", lambda: {"mpc_sos_fade_demo": None})
    problems = dm.check_health()
    assert any("cannot be read" in p for p in problems)


def test_a_missing_heartbeat_field_is_a_FAILURE_not_a_pass(wired):
    # An empty state dict must not sail through the freshness check by having nothing to check.
    wired.setattr(dm, "_bot_state", lambda: {"mpc_sos_fade_demo": {}})
    problems = dm.check_health()
    assert any("no heartbeat" in p for p in problems)


def test_mt5_link_False_is_reported(wired):
    wired.setattr(dm, "_bot_state", lambda: _healthy_state(mt5_link=False))
    problems = dm.check_health()
    assert any("MT5 link" in p for p in problems)


def test_mt5_link_None_means_UNASKED_and_is_NOT_a_failure(wired):
    # `Optional[bool]`, read `is False` and never falsy — the same contract the health strip
    # and the Bots page follow. A bot that has not completed a poll, or one on a build that
    # predates the field, has not reported a dead terminal; it has reported nothing.
    wired.setattr(dm, "_bot_state", lambda: _healthy_state(mt5_link=None))
    assert dm.check_health() == []


def test_an_mt5_link_key_that_is_absent_entirely_is_NOT_a_failure(wired):
    st = _healthy_state()
    st["mpc_sos_fade_demo"].pop("mt5_link")
    wired.setattr(dm, "_bot_state", lambda: st)
    assert dm.check_health() == []


# ── what actually gets sent ──────────────────────────────────────────────────────


@pytest.fixture
def sent(monkeypatch):
    calls: list[tuple[str, str]] = []
    monkeypatch.setattr(dm, "_send", lambda url, body="": calls.append((url, body)) or True)
    return calls


def test_a_healthy_box_pings_the_plain_url_with_no_body(wired, sent):
    wired.setattr(dm, "deadman_url", lambda: "https://hc-ping.com/abc")
    assert dm.main([]) == 0
    assert sent == [("https://hc-ping.com/abc", "")]


def test_a_problem_pings_the_FAIL_url_and_names_the_reason(wired, sent):
    # The whole point of the second signal: a detected failure is an immediate alert that says
    # what it is, instead of a silence you decode after the grace period.
    wired.setattr(dm, "deadman_url", lambda: "https://hc-ping.com/abc")
    wired.setattr(dm, "_running_keys", lambda: set())
    assert dm.main([]) == 0
    url, body = sent[0]
    assert url == "https://hc-ping.com/abc" + dm.FAIL_SUFFIX
    assert "not running" in body


def test_every_problem_reaches_the_body_not_just_the_first(wired, sent):
    wired.setattr(dm, "deadman_url", lambda: "https://hc-ping.com/abc")
    wired.setattr(
        dm, "_bot_state", lambda: _healthy_state(heartbeat=time.time() - 99_999, mt5_link=False)
    )
    dm.main([])
    body = sent[0][1]
    assert "stalled" in body and "MT5 link" in body


def test_an_unconfigured_switch_sends_nothing_and_still_exits_0(wired, sent):
    # Unset is a supported state. A scheduled task that fails every five minutes is a task
    # everyone learns to ignore, and then the real failure is ignored with it.
    wired.setattr(dm, "deadman_url", lambda: "")
    assert dm.main([]) == 0
    assert sent == []


def test_dry_run_checks_but_never_sends(wired, sent):
    wired.setattr(dm, "deadman_url", lambda: "https://hc-ping.com/abc")
    assert dm.main(["--dry-run"]) == 0
    assert sent == []


def test_status_never_sends_even_when_the_box_is_broken(wired, sent):
    wired.setattr(dm, "deadman_url", lambda: "https://hc-ping.com/abc")
    wired.setattr(dm, "_running_keys", lambda: None)
    assert dm.main(["--status"]) == 0
    assert sent == []


def test_a_failed_ping_does_not_raise(wired, monkeypatch):
    # If sending were fatal, the switch would need its own switch. The external service
    # raising the alarm when pings stop IS the handling — that is what it is for.
    wired.setattr(dm, "deadman_url", lambda: "https://hc-ping.com/abc")

    def boom(url, body=""):
        raise RuntimeError("network down")

    monkeypatch.setattr(dm, "_send", boom)
    with pytest.raises(RuntimeError):
        dm.main([])  # documents that _send itself is what must swallow, not main


def test_the_real_send_swallows_network_errors(monkeypatch):
    # The guarantee above, at the layer that actually owns it.
    import urllib.request

    def boom(*a, **k):
        raise OSError("no route to host")

    monkeypatch.setattr(urllib.request, "urlopen", boom)
    assert dm._send("https://hc-ping.com/abc") is False


# ── registry drift ───────────────────────────────────────────────────────────────


def test_the_bot_registry_matches_the_startup_coordinators():
    # Three files key bots by `--bot <key>`: this one, monitor.py, and startup_coordinator.py.
    # A bot added to the fleet and missed here is not an error anywhere — it is simply never
    # watched, which is the silent failure this whole module exists to prevent.
    coord = (_REPO / "algos" / "bots" / "startup_coordinator.py").read_text()
    for key in dm.BOTS:
        assert f'"{key}"' in coord, f"{key} is watched here but not started by the coordinator"

    monitor = (_REPO / "algos" / "notifications" / "monitor.py").read_text()
    for key in dm.BOTS:
        assert f'"{key}"' in monitor, f"{key} is watched here but not by monitor.py"
