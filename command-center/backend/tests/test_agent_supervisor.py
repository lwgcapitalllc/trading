"""
Agent supervisor — what it repairs, and (more importantly) what it refuses to.

The dangerous failure of a supervisor is not that it misses a repair; it is that
it performs one at the wrong moment. Restarting the tunnel under a six-hour
optimization kills the run and reports a healed dot. So most of these tests are
about the guard, not the loop.
"""

import pytest

from services import agent_supervisor as sup


@pytest.fixture
def rig(monkeypatch):
    """Fake every probe and action; record what got called."""
    state = {
        "ports": {sup.NT8_PORT: True, sup.MT5_PORT: True},
        "nt8": True,
        "mt5": True,
        "vps": True,
        "busy": set(),
        "fired": [],
        "tunnel_restarts": 0,
        # Agents that come up once their task is fired. Anything not listed
        # stays down, which is the schtasks-lied case.
        "recovers": {"nt8", "mt5"},
        # Scripts kill_agent_process was asked to terminate, in order.
        "killed": [],
        # Scripts that have a WEDGED process to find — alive, not serving. These
        # are the ones a kill can actually clear; anything else means the task
        # never started and killing finds nothing.
        "wedged": set(),
        # Agents that come up on the SECOND fire, i.e. once the corpse is gone.
        "recovers_after_kill": {"nt8", "mt5"},
    }

    def restart_tunnel():
        state["tunnel_restarts"] += 1
        state["ports"] = {sup.NT8_PORT: True, sup.MT5_PORT: True}

    # Resolved with fallbacks so the fixture still builds against a supervisor
    # that predates the wedged-agent recovery — see the `raising=False` note below.
    nt8_script = getattr(sup, "NT8_SCRIPT", "nt8_agent.py")
    mt5_script = getattr(sup, "MT5_SCRIPT", "mt5_agent.py")

    def schtasks_run(task):
        state["fired"].append(task)
        name = "nt8" if task == sup.NT8_TASK else "mt5"
        # A wedged process is why Windows refuses the task, so firing it while
        # one exists changes nothing — that is the whole defect being modelled.
        script = nt8_script if name == "nt8" else mt5_script
        if script in state["wedged"]:
            return {"status": "ok", "output": ""}
        if name in state["recovers"]:
            state[name] = True
        return {"status": "ok", "output": ""}

    def kill_agent_process(script):
        state["killed"].append(script)
        if script not in state["wedged"]:
            return False
        state["wedged"].discard(script)
        name = "nt8" if script == nt8_script else "mt5"
        if name in state["recovers_after_kill"]:
            state["recovers"].add(name)
        return True

    monkeypatch.setattr(sup, "port_bound", lambda p, timeout=1.0: state["ports"][p])
    monkeypatch.setattr(sup, "nt8_agent_ok", lambda: state["nt8"])
    monkeypatch.setattr(sup, "mt5_agent_ok", lambda: state["mt5"])
    monkeypatch.setattr(sup, "vps_reachable", lambda: state["vps"])
    monkeypatch.setattr(sup, "busy_scopes", lambda: state["busy"])
    monkeypatch.setattr(sup, "restart_tunnel", restart_tunnel)
    monkeypatch.setattr(sup, "schtasks_run", schtasks_run)
    # ⚠ `raising=False` so this fixture still builds against a supervisor that has
    # no `kill_agent_process` — which is what makes the wedged-agent tests below a
    # MEANINGFUL red rather than a vacuous one. Without it every test in the file
    # errors at setup on a missing attribute, which proves the attribute is
    # missing and says nothing about behaviour. With it, the reds are the
    # assertions themselves: no kill attempted, one fire instead of two.
    monkeypatch.setattr(sup, "kill_agent_process", kill_agent_process, raising=False)
    return state


def run(state):
    return sup.supervise_once(sleeper=lambda _: None)


# ── The happy path does nothing at all ────────────────────────────────────────

def test_everything_up_takes_no_action(rig):
    result = run(rig)
    assert result["actions"] == []
    assert rig["tunnel_restarts"] == 0
    assert rig["fired"] == []


# ── The two tunnel failures ───────────────────────────────────────────────────

def test_dead_tunnel_is_reopened(rig):
    """Laptop slept: ssh is gone, so neither port is bound."""
    rig["ports"] = {sup.NT8_PORT: False, sup.MT5_PORT: False}
    rig["nt8"] = rig["mt5"] = False
    result = run(rig)
    assert rig["tunnel_restarts"] == 1
    assert result["tunnel"] is True


def test_stale_tunnel_is_restarted_even_though_the_ports_are_bound(rig):
    """The case a port check alone cannot see, and the reason both signals exist.

    `ssh -N -L` keeps holding its forwards after the far end dies, so the ports
    look healthy while every request into them fails. Restarting the agents
    alone never recovers this — the documented fix is to rebuild the tunnel
    first, which is what the supervisor does.
    """
    rig["nt8"] = rig["mt5"] = False   # ports still bound
    run(rig)
    assert rig["tunnel_restarts"] == 1


def test_one_agent_down_does_not_touch_the_tunnel(rig):
    """A working tunnel is evidence enough — only the dead agent gets restarted."""
    rig["mt5"] = False
    run(rig)
    assert rig["tunnel_restarts"] == 0
    assert rig["fired"] == [sup.MT5_TASK]


# ── The guard: never act under a live job ─────────────────────────────────────

def test_a_running_job_does_NOT_block_reopening_a_dead_tunnel(rig):
    """The asymmetry, and it is deliberate.

    An unbound port is unambiguous — nothing can connect, so every call the
    running job makes is ALREADY failing. Rebuilding is the only route by which
    that job survives; refusing to would protect a run that is already broken.
    """
    rig["ports"] = {sup.NT8_PORT: False, sup.MT5_PORT: False}
    rig["nt8"] = rig["mt5"] = False
    rig["busy"] = {"python"}
    result = run(rig)
    assert rig["tunnel_restarts"] == 1
    assert any("tunnel-reopened" in a and "python" in a for a in result["actions"])


def test_a_running_job_DOES_block_restarting_a_merely_stale_tunnel(rig):
    """The other half of the asymmetry. Bound ports with silent agents is a
    GUESS, and it has a real false positive: an agent driving a heavy backtest
    stops answering /health while working perfectly (the NT8 agent does this
    under pywinauto). Killing the tunnel there breaks a live run."""
    rig["nt8"] = rig["mt5"] = False   # ports still bound
    rig["busy"] = {"nt8"}
    result = run(rig)
    assert rig["tunnel_restarts"] == 0
    assert any("stale-tunnel-skipped" in a for a in result["actions"])


def test_a_running_python_job_protects_the_MT5_agent(rig):
    """Python runs locally but pulls its BARS through the MT5 agent on 8766.

    Treating `python` as an MT5-free scope would let the supervisor restart the
    agent mid-fetch and kill a local run that never touched the VPS directly.
    """
    rig["mt5"] = False
    rig["busy"] = {"python"}
    result = run(rig)
    assert rig["fired"] == []
    assert any("mt5-DOWN-with-a-job-running" in a for a in result["actions"])


def test_an_orphaned_job_is_named_rather_than_silently_skipped(rig):
    """Observed live 2026-08-02: the NT8 agent died on a submission, the run row
    stayed `running`, and the supervisor correctly refused to restart the agent
    — forever, with nothing saying why. The skip has to name the deadlock and
    the way out of it."""
    rig["nt8"] = False
    rig["busy"] = {"nt8"}
    result = run(rig)
    assert rig["fired"] == []
    msg = next(a for a in result["actions"] if a.startswith("nt8-DOWN"))
    assert "Stop it or restart the backend" in msg


def test_a_running_python_job_does_not_protect_the_NT8_agent(rig):
    """The scopes are independent — a python run is no reason to leave NT8 down."""
    rig["nt8"] = False
    rig["busy"] = {"python"}
    run(rig)
    assert rig["fired"] == [sup.NT8_TASK]


def test_an_unreadable_job_table_is_treated_as_busy(monkeypatch):
    """Assume busy when the DB cannot be read.

    Doing nothing is always safe; guessing "idle" wrongly kills a live run. Uses
    the real `busy_scopes` rather than the rig's stub — the fallback IS the
    behaviour under test.
    """
    def boom():
        raise RuntimeError("db locked")
    monkeypatch.setattr("services.lab_db.get_running_job", boom)
    assert sup.busy_scopes() == {"nt8", "mt5", "python"}


def test_only_scopes_reporting_running_are_busy(monkeypatch):
    monkeypatch.setattr(
        "services.lab_db.get_running_job",
        lambda: {"nt8": {"running": False}, "mt5": {"running": True},
                 "python": {"running": False}},
    )
    assert sup.busy_scopes() == {"mt5"}


# ── schtasks lies, so the fire is always verified ─────────────────────────────

def test_a_task_that_fires_but_does_not_start_is_reported_as_such(rig):
    """`schtasks /run` returns SUCCESS for a task Windows refuses to launch.

    Without the re-probe the loop would report a healed agent every minute
    forever and the dot would stay red with nothing explaining it.

    With NO wedged process to clear, the kill finds nothing and the loop says so
    rather than pretending it did something — this is the genuine "the task did
    not start" case (stored-password trap, no interactive session).
    """
    rig["mt5"] = False
    rig["recovers"] = set()
    result = run(rig)
    assert rig["fired"] == [sup.MT5_TASK]
    assert rig["killed"] == [sup.MT5_SCRIPT]
    assert "mt5-fired-but-still-down (no process to clear)" in result["actions"]
    assert result["mt5"] is False


def test_a_successful_start_is_reported_as_started(rig):
    rig["nt8"] = False
    result = run(rig)
    assert "nt8-started" in result["actions"]
    assert result["nt8"] is True
    # Nothing to clear when the ordinary fire worked.
    assert rig["killed"] == []


# ── The wedged agent — alive, not serving, and un-restartable by task ─────────
# MEASURED on the live box 2026-08-06: the NT8 agent sat in this state for two
# days while both the supervisor and the sidebar's Start button fired the task
# once a minute and Windows refused every one of them (0x800710E0).

def test_a_wedged_agent_is_killed_and_restarted(rig):
    rig["nt8"] = False
    rig["recovers"] = set()               # the first fire cannot work…
    rig["wedged"] = {sup.NT8_SCRIPT}      # …because a corpse holds the task
    result = run(rig)

    assert rig["killed"] == [sup.NT8_SCRIPT]
    # Fired TWICE: once refused, once after the corpse was cleared.
    assert rig["fired"] == [sup.NT8_TASK, sup.NT8_TASK]
    assert "nt8-wedged-process-killed" in result["actions"]
    assert "nt8-restarted-after-kill" in result["actions"]
    assert result["nt8"] is True


def test_the_kill_targets_only_that_agents_own_script(rig):
    """The second clause of the kill match is the safety property.

    `mt5_agent.py` must never be handed to the NT8 branch — on the real box the
    match is `name='python.exe' AND commandline LIKE '%<script>%'`, and the
    script name is the ONLY thing separating one agent from the live trading bot.
    """
    rig["mt5"] = False
    rig["recovers"] = set()
    rig["wedged"] = {sup.MT5_SCRIPT}
    run(rig)
    assert rig["killed"] == [sup.MT5_SCRIPT]
    assert sup.NT8_SCRIPT not in rig["killed"]


def test_a_kill_that_does_not_bring_it_back_says_so(rig):
    """Clearing the corpse is not a guarantee — and reporting one would be the
    same lie as trusting schtasks."""
    rig["nt8"] = False
    rig["recovers"] = set()
    rig["recovers_after_kill"] = set()
    rig["wedged"] = {sup.NT8_SCRIPT}
    result = run(rig)
    assert "nt8-still-down-after-kill" in result["actions"]
    assert result["nt8"] is False


def test_a_busy_scope_is_never_killed(rig):
    """The busy guard runs FIRST, so the kill can never reach an agent whose
    scope holds a running job. That ordering is the whole reason a kill is safe
    here at all — 'dead' and 'too loaded to answer /health' are indistinguishable
    from this side, and the wrong guess would terminate a live run's agent."""
    rig["nt8"] = False
    rig["busy"] = {"nt8"}
    rig["wedged"] = {sup.NT8_SCRIPT}
    result = run(rig)
    assert rig["killed"] == []
    assert rig["fired"] == []
    assert any("nt8-DOWN-with-a-job-running" in a for a in result["actions"])


def test_an_unbound_port_is_never_killed_either(rig):
    """No tunnel means the /health probe proves nothing about the far end, so a
    silent agent is not evidence of a wedged one."""
    rig["nt8"] = False
    rig["ports"] = {sup.NT8_PORT: False, sup.MT5_PORT: True}
    rig["wedged"] = {sup.NT8_SCRIPT}
    rig["vps"] = False        # keep the tunnel branch from rebuilding the port
    result = run(rig)
    assert rig["killed"] == []
    assert "nt8-skipped (no tunnel)" in result["actions"]


def test_a_failed_fire_does_not_abort_the_other_agent(rig, monkeypatch):
    """One bad schtask must not leave the second agent unattended."""
    def only_nt8_fails(task):
        rig["fired"].append(task)
        if task == sup.NT8_TASK:
            raise sup.SchtaskError("schtasks failed: access denied")
        rig["mt5"] = True
        return {"status": "ok", "output": ""}
    monkeypatch.setattr(sup, "schtasks_run", only_nt8_fails)
    rig["nt8"] = rig["mt5"] = False
    rig["ports"] = {sup.NT8_PORT: True, sup.MT5_PORT: True}
    rig["vps"] = False   # keep the stale-tunnel branch out of the way
    result = run(rig)
    assert rig["fired"] == [sup.NT8_TASK, sup.MT5_TASK]
    assert any("nt8-fire-failed" in a for a in result["actions"])
    assert result["mt5"] is True


# ── Nothing to reach the agent through ────────────────────────────────────────

def test_no_tunnel_means_no_pointless_schtask(rig):
    """Firing a task we cannot then observe would 'succeed' and change nothing."""
    rig["ports"] = {sup.NT8_PORT: False, sup.MT5_PORT: False}
    rig["nt8"] = rig["mt5"] = False
    rig["vps"] = False   # so the tunnel cannot be rebuilt either
    result = run(rig)
    assert rig["fired"] == []
    assert "nt8-skipped (no tunnel)" in result["actions"]
    assert "mt5-skipped (no tunnel)" in result["actions"]


def test_an_unreachable_vps_is_not_something_the_supervisor_can_fix(rig):
    rig["ports"] = {sup.NT8_PORT: False, sup.MT5_PORT: False}
    rig["nt8"] = rig["mt5"] = False
    rig["vps"] = False
    result = run(rig)
    assert rig["tunnel_restarts"] == 0
    assert "tunnel-skipped (VPS unreachable)" in result["actions"]


# ── The MT5 terminal question is separate from the MT5 agent question ─────────

def test_terminal_status_is_None_when_the_agent_cannot_be_asked(monkeypatch):
    """None is 'we did not find out', never 'disconnected'. Rendering an
    unanswered question as a failure invents a measurement."""
    def boom():
        raise RuntimeError("unreachable")
    monkeypatch.setattr("services.mt5_agent_client.status", boom)
    assert sup.mt5_terminal_status() is None


def test_terminal_status_reports_the_account_it_is_bound_to(monkeypatch):
    monkeypatch.setattr(
        "services.mt5_agent_client.status",
        lambda: {"mt5_connected": True, "account": 25893735,
                 "server": "VantageMarkets-Demo", "error": None},
    )
    st = sup.mt5_terminal_status()
    assert st == {"connected": True, "account": 25893735,
                  "server": "VantageMarkets-Demo", "error": None}


def test_a_responding_agent_with_a_disconnected_terminal_is_not_ok(monkeypatch):
    """The gap this closed: /health says 'ok' whether or not MT5 is logged in,
    so an agent up with a dead terminal showed green and failed at fetch time."""
    monkeypatch.setattr(
        "services.mt5_agent_client.status",
        lambda: {"mt5_connected": False, "account": None, "server": None,
                 "error": "IPC timeout"},
    )
    st = sup.mt5_terminal_status()
    assert st["connected"] is False
    assert st["error"] == "IPC timeout"
