"""NinjaTrader switched off ON PURPOSE — read off the box's NT8Agent task, and every reader after it.

The failure this ends: NinjaTrader shut down deliberately and NinjaTrader crashed looked
identical, so the app complained about the first as though it were the second. The dangerous
misreadings are the reassuring ones — an unfamiliar status or an unreadable box read as "off" would
silence a real outage — so most of these tests pin what must NOT count as off.
"""

import subprocess

import pytest
from services import nt8_switch


@pytest.fixture(autouse=True)
def fresh():
    """The answer is module memory shared by every test on this worker."""
    nt8_switch._reset()
    yield
    nt8_switch._reset()


def _row(state, status="Running"):
    """The box's own `schtasks /query /tn NT8Agent /v /fo LIST`, trimmed — copied from the VPS on
    2026-09-11 minutes after the task was disabled, which is why `Status` still says Running. It
    keeps the two OTHER lines that end in 'Disabled', because they are the trap."""
    return (
        "\r\nFolder: \\\r\n"
        "TaskName:                             \\NT8Agent\r\n"
        "Next Run Time:                        N/A\r\n"
        f"Status:                               {status}\r\n"
        "Last Run Time:                        9/11/2026 2:27:50 PM\r\n"
        f"Scheduled Task State:                 {state}\r\n"
        "Idle Time:                            Disabled\r\n"
        "Delete Task If Not Rescheduled:       Disabled\r\n"
        "Repeat: Every:                        N/A\r\n"
    )


# ── Reading schtasks ──────────────────────────────────────────────────────────


def test_a_disabled_task_is_off_even_while_its_agent_is_still_RUNNING():
    """MEASURED on the box: disabling a task whose agent is alive leaves `Status: Running`, so the
    short status column says 'running' at the moment it was switched off. The state flag is what
    counts. MUTATION: read the `Status` line instead — reddens this."""
    assert nt8_switch.parse_task_state(0, _row("Disabled"), "") == nt8_switch.DISABLED


def test_the_OTHER_lines_ending_in_Disabled_do_not_switch_it_off():
    """`Idle Time: Disabled` and `Delete Task If Not Rescheduled: Disabled` are on every task.
    MUTATION: search the whole output for 'Disabled' — reddens this."""
    assert nt8_switch.parse_task_state(0, _row("Enabled", "Ready"), "") == nt8_switch.ENABLED


@pytest.mark.parametrize("state", ["Enabled", "", "Some future word"])
def test_every_state_but_disabled_is_ON(state):
    """An unfamiliar word must never switch NT8 off here — that would turn a real outage quiet.
    MUTATION: treat anything not 'Enabled' as disabled — reddens the blank and the future word."""
    assert nt8_switch.parse_task_state(0, _row(state), "") == nt8_switch.ENABLED


@pytest.mark.parametrize(
    "stderr",
    [
        "ERROR: The system cannot find the file specified.",
        'ERROR: The specified task name "\\NT8Agent" does not exist in the system.',
    ],
)
def test_a_task_the_box_does_not_have_is_MISSING(stderr):
    assert nt8_switch.parse_task_state(1, "", stderr) == nt8_switch.MISSING


@pytest.mark.parametrize(
    "rc,out,err",
    [
        (255, "", "kex_exchange_identification: read: Connection reset by peer"),
        (255, "", "ssh: connect to host forexvps: cannot find route"),  # ssh's own failure
        (0, "", ""),  # ran, printed nothing
        (0, "garbage with no columns", ""),
        (1, "", "ERROR: Access is denied."),
    ],
)
def test_anything_short_of_an_answer_is_NONE_never_a_guess(rc, out, err):
    """`None` = could not ask. ssh's own 255 is excluded from MISSING even when its message says
    'cannot find', because that is ssh failing to reach the box, not the box lacking a task.
    MUTATION: drop the `!= 255` guard — reddens the route case."""
    assert nt8_switch.parse_task_state(rc, out, err) is None


# ── Asking the box, and remembering ───────────────────────────────────────────


class _Box:
    def __init__(self, *answers):
        self.answers = list(answers)
        self.calls = []

    def run(self, argv, **kwargs):
        self.calls.append(argv)
        rc, out, err = self.answers.pop(0)
        return subprocess.CompletedProcess(argv, rc, out, err)


def test_it_asks_for_the_supervisors_task_by_name(monkeypatch):
    from services import agent_supervisor

    box = _Box((0, _row("Disabled"), ""))
    monkeypatch.setattr(nt8_switch.vps_ssh, "run", box.run)
    nt8_switch.refresh(now=1000.0)
    assert f"schtasks /query /tn {agent_supervisor.NT8_TASK} /v /fo LIST" in box.calls[0][-1]


def test_nothing_is_known_until_the_box_is_asked():
    """Before the first answer every reader must behave as though this did not exist."""
    assert nt8_switch.switched_off() is None
    assert nt8_switch.off_reason() is None


def test_a_fresh_answer_is_served_from_memory_without_asking_again(monkeypatch):
    """One SSH call per window, however many readers. MUTATION: drop the age check — the second
    refresh asks again and the fake box has no second answer to give."""
    box = _Box((0, _row("Disabled"), ""))
    monkeypatch.setattr(nt8_switch.vps_ssh, "run", box.run)
    nt8_switch.refresh(now=1000.0)
    nt8_switch.refresh(now=1000.0 + nt8_switch.MAX_AGE_S - 1)
    assert len(box.calls) == 1
    assert nt8_switch.switched_off() is True


def test_a_stale_answer_is_asked_again_and_can_turn_NT8_back_on(monkeypatch):
    box = _Box((0, _row("Disabled"), ""), (0, _row("Enabled", "Ready"), ""))
    monkeypatch.setattr(nt8_switch.vps_ssh, "run", box.run)
    nt8_switch.refresh(now=1000.0)
    nt8_switch.refresh(now=1000.0 + nt8_switch.MAX_AGE_S + 1)
    assert nt8_switch.switched_off() is False
    assert nt8_switch.off_reason() is None


def test_a_failed_read_KEEPS_the_last_answer(monkeypatch):
    """The box refuses a third of new connections when crowded. Forgetting a good answer on one
    refusal would flip a deliberately-off NT8 back to a red 'click to start'.
    MUTATION: store the failed read's None — reddens this."""
    box = _Box(
        (0, _row("Disabled"), ""),
        (255, "", "kex_exchange_identification: read: Connection reset by peer"),
    )
    monkeypatch.setattr(nt8_switch.vps_ssh, "run", box.run)
    nt8_switch.refresh(now=1000.0)
    nt8_switch.refresh(now=1000.0 + nt8_switch.MAX_AGE_S + 1)
    assert len(box.calls) == 2  # it did ask
    assert nt8_switch.switched_off() is True


def test_a_timeout_is_a_failed_read_not_a_crash(monkeypatch):
    def slow(argv, **kwargs):
        raise subprocess.TimeoutExpired(argv, kwargs.get("timeout"))

    monkeypatch.setattr(nt8_switch.vps_ssh, "run", slow)
    assert nt8_switch.refresh(now=1000.0) is None
    assert nt8_switch.switched_off() is None


def test_disabled_and_missing_are_both_off_and_say_DIFFERENT_things(monkeypatch):
    """Two causes, two sentences — one says it was switched off, the other that it was never set
    up, and they call for different work."""
    monkeypatch.setattr(nt8_switch, "_state", nt8_switch.DISABLED)
    disabled = nt8_switch.off_reason()
    assert nt8_switch.switched_off() is True
    monkeypatch.setattr(nt8_switch, "_state", nt8_switch.MISSING)
    missing = nt8_switch.off_reason()
    assert nt8_switch.switched_off() is True
    assert "disabled" in disabled and "no NT8Agent task" in missing
    assert disabled != missing
