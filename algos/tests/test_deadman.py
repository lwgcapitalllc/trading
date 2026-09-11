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
import json
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
    return {"sos_fade_demo": st}


@pytest.fixture
def wired(monkeypatch, tmp_path):
    """Everything the box would supply, defaulted to healthy. Tests break one thing each.

    ⚠ `_is_assigned` is stubbed rather than left to read the real configs. `BOTS` now carries a
    bot that sits on the BENCH, and without this every test here would depend on what a config
    in the repo happens to say — so assigning that bot from the Bots page would turn this whole
    file red for a reason that has nothing to do with the dead-man's switch.

    ⚠ **`PENDING_FILE` is redirected into a scratch dir.** It is a module constant under the real
    `algos/` tree, so without this every test driving `main()` writes one shared path — which
    both litters the repo and makes tests order-dependent under `-n auto`, the worst failure
    shape a suite has.

    ⚠ **`_label` is stubbed to the plain name, for `_is_assigned`'s reason.** It reads the bot's
    real config and the real account registry, so the LIVE/demo tag on every problem line would
    move with whichever account a bot happens to be on today. What it adds is tested on its own
    below, against a private registry.
    """
    monkeypatch.setattr(dm, "_running_keys", lambda: {"sos_fade_demo"})
    monkeypatch.setattr(dm, "_bot_state", _healthy_state)
    monkeypatch.setattr(dm, "_is_assigned", lambda key: key == "sos_fade_demo")
    monkeypatch.setattr(dm, "_label", lambda key, name: name)
    monkeypatch.setattr(dm, "PENDING_FILE", tmp_path / "deadman_pending.json")
    return monkeypatch


def _already_outstanding(*problems, age=None):
    """Pre-date each problem so it has already outlasted the confirmation window.

    Used by tests whose subject is what an alarm SAYS, not how long it waits — without it they
    would be asserting the holding behaviour by accident.
    """
    age = dm.CONFIRM_SECS + 60 if age is None else age
    dm.PENDING_FILE.write_text(json.dumps({p: time.time() - age for p in problems}))


# ── the bench ────────────────────────────────────────────────────────────────
def test_a_bot_with_no_account_is_not_a_failure(wired):
    """MUTATION: drop the `_is_assigned` skip from `check_health` -> red.

    A benched bot has no process by design, so counting it as "process is not running" would hold
    this switch in the FAILED state permanently — and the switch's entire value is that its
    silence means something. A permanent failure is the same as no switch at all."""
    wired.setattr(dm, "_running_keys", lambda: {"sos_fade_demo"})
    wired.setattr(dm, "BOTS", {"sos_fade_demo": "SOS Fade", "benched": "Benched"})
    assert dm.check_health() == []


def test_a_bot_WITH_an_account_that_is_not_running_is_still_a_failure(wired):
    """The other half — the skip must not swallow the case this exists to catch."""
    wired.setattr(dm, "_running_keys", lambda: set())
    problems = dm.check_health()
    assert any("not running" in p for p in problems)


# ── two copies of one strategy share a name, so a report says WHICH (2026-09-11) ──────────────


@pytest.fixture
def two_copies(monkeypatch, tmp_path):
    """Two bots on the same strategy name — one on a live account, one on a demo — against a
    PRIVATE registry, so nothing here moves when a real bot does."""
    import bot_state

    reg = tmp_path / "accounts.json"
    reg.write_text(
        json.dumps({"accounts": [{"account": 1, "kind": "live"}, {"account": 2, "kind": "demo"}]}),
        encoding="utf-8",
    )
    monkeypatch.setattr(bot_state, "_ACCOUNTS", reg)
    monkeypatch.setattr(bot_state, "read_account", lambda key: {"orig": 1, "copy": 2}.get(key))
    monkeypatch.setattr(dm, "BOTS", {"orig": "SOS Fade", "copy": "SOS Fade"})
    monkeypatch.setattr(dm, "_is_assigned", lambda key: True)
    monkeypatch.setattr(dm, "_bot_state", lambda: {})
    return monkeypatch


def test_a_failure_report_says_which_COPY_by_its_accounts_kind(two_copies):
    """MUTATION: make `_label` return the bare name -> red.

    The dead-man's report is the one message that arrives when the box itself is in trouble, and
    "SOS Fade: process is not running" would not say whether real money is unattended."""
    two_copies.setattr(dm, "_running_keys", lambda: set())
    problems = dm.check_health()
    assert "SOS Fade · LIVE: process is not running" in problems
    assert "SOS Fade · demo: process is not running" in problems


def test_the_label_can_never_stop_the_report(two_copies):
    """A lookup that blows up costs the tag, never the report — this switch's value is that it
    speaks when something is wrong."""
    import bot_state

    def boom(*a, **k):
        raise RuntimeError("registry exploded")

    two_copies.setattr(bot_state, "labelled", boom)
    assert dm._label("orig", "SOS Fade") == "SOS Fade"


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
    wired.setattr(dm, "_bot_state", lambda: {"sos_fade_demo": None})
    problems = dm.check_health()
    assert any("cannot be read" in p for p in problems)


def test_a_missing_heartbeat_field_is_a_FAILURE_not_a_pass(wired):
    # An empty state dict must not sail through the freshness check by having nothing to check.
    wired.setattr(dm, "_bot_state", lambda: {"sos_fade_demo": {}})
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
    st["sos_fade_demo"].pop("mt5_link")
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
    # The whole point of the second signal: a CONFIRMED failure says what it is, instead of a
    # silence you decode after the external service's grace period.
    #
    # ⚠ The problem is pre-dated because since 2026-09-09 a failure has to OUTLAST a restart
    # before it alarms. This test's subject is what the alarm SAYS; the waiting has its own
    # tests below, and leaving this one to assert both would mean it pinned neither clearly.
    wired.setattr(dm, "deadman_url", lambda: "https://hc-ping.com/abc")
    wired.setattr(dm, "_running_keys", lambda: set())
    _already_outstanding("SOS Fade: process is not running")
    assert dm.main([]) == 0
    url, body = sent[0]
    assert url == "https://hc-ping.com/abc" + dm.FAIL_SUFFIX
    assert "not running" in body


def test_every_problem_reaches_the_body_not_just_the_first(wired, sent):
    wired.setattr(dm, "deadman_url", lambda: "https://hc-ping.com/abc")
    wired.setattr(
        dm, "_bot_state", lambda: _healthy_state(heartbeat=time.time() - 99_999, mt5_link=False)
    )
    _already_outstanding(*dm.check_health())
    dm.main([])
    body = sent[0][1]
    assert "stalled" in body and "MT5 link" in body


# ── a problem has to OUTLAST a restart before it alarms ──────────────────────
#
# 🔴 Every restart — a deploy, or the watchdog recovering a crash — takes a bot away for about a
# minute, and a 5-minute pass landing in that hole sent `/fail` and paged for a button somebody
# had just pressed. MEASURED from the health channel, 2026-09-04 → 2026-09-09: every one of those
# pages tracked a restart. **An alarm that fires when you press the button is one you learn to
# scroll past**, and then it cannot tell you about the thing it exists for.
#
# The cases below are weighted the same way the rest of this file is — toward the ways the new
# holding logic could wrongly say "fine", because that is still the failure nobody hears.


def test_a_brand_new_problem_is_held_rather_than_paged(wired, sent):
    """The restart hole. The box is plainly answering, so it pings HEALTHY."""
    wired.setattr(dm, "deadman_url", lambda: "https://hc-ping.com/abc")
    wired.setattr(dm, "_running_keys", lambda: set())
    assert dm.main([]) == 0
    assert sent == [("https://hc-ping.com/abc", "")], "paged on a problem one pass old"


def test_a_problem_that_outlasts_the_window_still_alarms(wired, sent):
    """🔴 The half that must not be lost. Holding a REAL failure quiet is this module's one
    unrecoverable bug, because its silence is also what health looks like."""
    wired.setattr(dm, "deadman_url", lambda: "https://hc-ping.com/abc")
    wired.setattr(dm, "_running_keys", lambda: set())
    _already_outstanding("SOS Fade: process is not running")
    dm.main([])
    url, body = sent[0]
    assert url.endswith(dm.FAIL_SUFFIX), "a confirmed failure did not reach the FAIL url"
    assert "not running" in body
    assert "for " in body, "the alarm does not say how long it has been going on"


def test_a_problem_that_clears_does_not_leave_its_clock_running(wired, sent):
    """Otherwise the NEXT problem inherits a stale timestamp and pages instantly — turning the
    fix into a different false alarm rather than removing one."""
    wired.setattr(dm, "deadman_url", lambda: "https://hc-ping.com/abc")
    _already_outstanding("SOS Fade: process is not running")

    dm.main([])  # healthy pass: forgets everything
    assert not dm.PENDING_FILE.exists()

    wired.setattr(dm, "_running_keys", lambda: set())
    sent.clear()
    dm.main([])
    assert sent == [("https://hc-ping.com/abc", "")], "a fresh problem inherited an old clock"


def test_an_unreadable_pending_file_alarms_rather_than_holding_quiet(wired, sent):
    """Rule 1. *Cannot tell how long this has been wrong* may not buy the reassuring answer —
    noisy once beats silent forever, the same call `log_review.py` makes."""
    wired.setattr(dm, "deadman_url", lambda: "https://hc-ping.com/abc")
    wired.setattr(dm, "_running_keys", lambda: set())
    dm.PENDING_FILE.write_text("{not json")
    dm.main([])
    assert sent[0][0].endswith(dm.FAIL_SUFFIX)


def test_a_dry_run_does_not_start_the_clock(wired, sent):
    """A preview that starts somebody's grace clock makes the next REAL pass alarm early — the
    same reason `watch_broker_costs.py` refuses to consume tomorrow's first reading."""
    wired.setattr(dm, "deadman_url", lambda: "https://hc-ping.com/abc")
    wired.setattr(dm, "_running_keys", lambda: set())
    dm.main(["--dry-run"])
    assert not dm.PENDING_FILE.exists()
    assert sent == []


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
