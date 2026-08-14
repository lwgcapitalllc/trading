"""
The test suite's own interlock: no test may reach the live VPS.

`conftest._no_live_vps` is autouse, so every test in this repo depends on it — which makes
it the one fixture whose failure mode is *silence*. A guard that never fires and a guard
that is not installed look identical from a green suite, so this file drives it directly.

Written 2026-08-05, alongside the SSH half of that guard. The HTTP half had shipped the day
before and the same day found `list_strategy_files` unstubbed — a test that passed only
while the tunnel happened to be up.

⚠ The load-bearing case is `test_a_swallowing_caller_cannot_eat_the_guard`. Every VPS probe
in this backend catches `Exception` and reads the failure as "the box is down", so a guard
raising `AssertionError` would be swallowed by the exact code it is meant to police and the
un-stubbed call would still have been made. That is why `LiveVpsCall` derives from
`BaseException`, and this file is where that stays true.
"""

import subprocess

import pytest

from tests.conftest import LiveVpsCall, _targets_the_vps

# ── The classifier ────────────────────────────────────────────────────────────


def test_an_ssh_argv_is_refused():
    assert _targets_the_vps(["ssh", "forexvps", "echo ok"]) is True


def test_a_copy_to_the_box_is_refused():
    """scp/sftp move files onto a machine that trades real money."""
    assert _targets_the_vps(["scp", "x.cs", "forexvps:C:/trading/"]) is True
    assert _targets_the_vps(["sftp", "somehost"]) is True


def test_an_ssh_to_any_host_is_refused_not_just_the_alias():
    """The program is the signal. A new call site naming a different host is still SSH."""
    assert _targets_the_vps(["ssh", "someotherbox", "whoami"]) is True


def test_pkill_on_the_tunnel_pattern_is_refused():
    """`restart_tunnel`'s first act. The program is not ssh, so only the alias route
    catches it — and it is the call that would kill the developer's own tunnel."""
    assert _targets_the_vps(["pkill", "-f", r"ssh -N.*forexvps"]) is True


def test_a_shell_string_is_classified_like_an_argv():
    assert _targets_the_vps("ssh forexvps echo ok") is True


def test_a_local_command_runs_for_real():
    """The negative half, and the reason this is a classifier rather than a blanket ban on
    `subprocess`. `routers/bots.py::_git_commit_push` really does shell out to git, and the
    smart-money router really does spawn its stage scripts."""
    assert _targets_the_vps(["git", "-C", "/tmp", "status", "--porcelain"]) is False
    assert _targets_the_vps([]) is False

    out = subprocess.run(["git", "--version"], capture_output=True, text=True)
    assert out.returncode == 0 and "git version" in out.stdout


# ── The guard, at the real call sites ─────────────────────────────────────────


def test_the_bots_ssh_helper_is_blocked():
    from routers import bots

    with pytest.raises(LiveVpsCall):
        bots._ssh("whoami")


def test_restarting_the_tunnel_is_blocked_before_it_kills_anything():
    from services import agent_supervisor as sup

    with pytest.raises(LiveVpsCall):
        sup.restart_tunnel()


def test_firing_a_scheduled_task_is_blocked():
    """`schtasks_run` catches `Exception` and re-raises as a 502 — so a catchable guard
    would turn a live call into a tidy error response and let the call happen."""
    from services import agent_supervisor as sup

    with pytest.raises(LiveVpsCall):
        sup.schtasks_run("SYS_STARTUP")


def test_a_swallowing_caller_cannot_eat_the_guard():
    """`vps_reachable` is `try: ssh … except Exception: return False`.

    With an `AssertionError` guard this returns False and the test suite stays green while
    the ssh subprocess was still attempted on the way in. It must RAISE.
    """
    from services import agent_supervisor as sup

    with pytest.raises(LiveVpsCall):
        sup.vps_reachable()


def test_the_http_half_survives_a_swallowing_caller_too():
    """`_agent_ok` is the same shape one channel over: `try: client.health() except
    Exception: return False`."""
    from services import agent_supervisor as sup

    with pytest.raises(LiveVpsCall):
        sup.nt8_agent_ok()
    with pytest.raises(LiveVpsCall):
        sup.mt5_agent_ok()


def test_the_guard_is_not_an_exception():
    """The property every test above rests on, pinned on its own so a future 'tidy-up' to
    `class LiveVpsCall(Exception)` fails HERE rather than by quietly disarming the suite."""
    assert issubclass(LiveVpsCall, BaseException)
    assert not issubclass(LiveVpsCall, Exception)


# ── Named stubs still win ─────────────────────────────────────────────────────


def test_a_stubbed_call_site_still_works(monkeypatch):
    """The guard must not make the VPS untestable — a test that stubs the function it needs
    patches above the fixture, and its patch wins."""
    from routers import bots

    monkeypatch.setattr(bots, "_ssh", lambda _c: "stubbed")
    assert bots._ssh("whoami") == "stubbed"
