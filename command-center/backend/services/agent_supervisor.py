"""
Agent supervisor — keeps the VPS link up without anyone clicking a red dot.

ONE loop, on a fixed interval, doing the SAME thing on every pass. That is the
whole design: a cold start and a wake-from-sleep are then literally the same
code path, so there is no "first launch" behaviour that can drift from
"recovered after the laptop slept". The predecessor was a one-shot thread that
ran 8 seconds after boot and never again, which is why the MT5 agent had to be
started by hand after every sleep.

WHAT IT PROBES, AND WHY THE DISTINCTION MATTERS

`ssh -L` binds the local port itself, so a TCP connect to 127.0.0.1:8766
succeeds for as long as the ssh process holds the forward — whether or not
anything is alive at the far end. That gives two independent signals:

    port bound   →  the tunnel process is holding its forwards
    HTTP /health →  the agent at the far end is answering

and the pair is what tells the two failures apart:

    neither port bound          →  the tunnel is dead (laptop slept). Restart it.
    ports bound, BOTH agents down →  a stale tunnel forwarding into nothing, or
                                     both agents really are down. Either way the
                                     documented recovery is tunnel first, then
                                     the schtasks — so that is what it does.
    ports bound, ONE agent down →  the tunnel is fine. Fire that agent's task only.

The old health check answered neither question: it ran `ssh forexvps "echo ok"`,
a BRAND NEW connection that has nothing to do with the forwards, so the SSH dot
could sit green while the tunnel was dead and both agent dots were red — which
sends you looking at the VPS when the problem is on this machine.

THE GUARD IS THE POINT, NOT THE LOOP

Restarting the tunnel under a live backtest kills it. Every action here is
skipped when the scope it would disturb has a job running (`lab_db.get_running_job`),
and a python run counts as MT5 traffic because `backtest/data/mt5_agent.py` pulls
its bars through port 8766. A supervisor that heals a red dot by killing a
six-hour optimization is worse than the red dot.

FIRING A TASK IS NOT EVIDENCE IT STARTED. `schtasks /run` reports SUCCESS even
for a task Windows refuses to launch (see algos/CLAUDE.md → the stored-password
trap), so every fire is followed by a re-probe and the outcome is logged either
way. Silence after a fire used to read as success.
"""

from __future__ import annotations

import logging
import socket
import subprocess
import threading
import time
from typing import Callable, Optional

import config as cfg

log = logging.getLogger(__name__)

# Local ends of the two LocalForwards start.sh opens.
NT8_PORT = 8765
MT5_PORT = 8766

# Scheduled task per agent. Both run as InteractiveToken on the VPS desktop
# session — see algos/CLAUDE.md; do not "fix" them to a stored password.
NT8_TASK = "NT8Agent"
MT5_TASK = "MT5AgentRDP"

INTERVAL_SECONDS = 60      # one pass per minute — cheap, and sleep recovery is a minute at worst
AGENT_GRACE_SECONDS = 20   # how long an agent gets to answer after its task is fired
TUNNEL_GRACE_SECONDS = 3   # port-forward establishment after a tunnel restart

_stop = threading.Event()


class SchtaskError(RuntimeError):
    """A scheduled task could not be fired. `status` is the HTTP code a router should use."""

    def __init__(self, message: str, status: int = 502):
        super().__init__(message)
        self.status = status


# ── Primitive actions (moved here from routers/system.py) ─────────────────────
# These are subprocess calls, which the layering rules put in services/ — the
# router used to own them and main.py reached across into the router to call
# one. One definition, in the layer that is allowed to have it.

def restart_tunnel() -> None:
    """Kill any stale `ssh -N` tunnel and spawn a fresh one with both forwards.

    The remote target must be 127.0.0.1, never `localhost`: the VPS resolves
    `localhost` to ::1 and both Flask agents bind IPv4 only, so a `localhost`
    forward connects to nothing while looking perfectly correct.
    """
    subprocess.run(["pkill", "-f", r"ssh -N.*forexvps"], capture_output=True)
    subprocess.Popen(
        ["ssh", "-N",
         "-L", f"{NT8_PORT}:127.0.0.1:{NT8_PORT}",
         "-L", f"{MT5_PORT}:127.0.0.1:{MT5_PORT}",
         "-o", "ServerAliveInterval=30",
         "-o", "ServerAliveCountMax=3",
         cfg.SSH_ALIAS],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    time.sleep(TUNNEL_GRACE_SECONDS)


def schtasks_run(task_name: str) -> dict:
    """Fire a Windows scheduled task over SSH.

    ⚠ A zero exit code means the REQUEST was accepted, not that the task ran.
    Callers must verify the effect (the supervisor re-probes /health).
    """
    try:
        result = subprocess.run(
            ["ssh", "-o", "ConnectTimeout=5", "-o", "BatchMode=yes",
             cfg.SSH_ALIAS, f"schtasks /run /tn {task_name}"],
            capture_output=True, text=True, timeout=15,
        )
    except subprocess.TimeoutExpired:
        raise SchtaskError("SSH timed out", status=504)
    except Exception as exc:
        raise SchtaskError(str(exc), status=502)
    if result.returncode != 0:
        raise SchtaskError(f"schtasks failed: {result.stderr.strip()}", status=502)
    return {"status": "ok", "output": result.stdout.strip()}


# ── Probes ────────────────────────────────────────────────────────────────────

def port_bound(port: int, timeout: float = 1.0) -> bool:
    """Is something listening on 127.0.0.1:<port> — i.e. is ssh holding the forward?

    Deliberately NOT an HTTP call: this answers "is the tunnel there", and the
    agent's own /health answers "is the far end alive". Collapsing the two is
    how the SSH indicator ended up unable to describe the tunnel at all.
    """
    try:
        with socket.create_connection(("127.0.0.1", port), timeout=timeout):
            return True
    except OSError:
        return False


def tunnel_up() -> bool:
    return port_bound(NT8_PORT) and port_bound(MT5_PORT)


def vps_reachable() -> bool:
    """A fresh SSH connection to the VPS — separate from the tunnel on purpose.

    This is what distinguishes "the VPS is down / the network is out" (nothing
    the supervisor can fix) from "the tunnel died on this laptop" (which it can).
    """
    try:
        result = subprocess.run(
            ["ssh", "-o", "ConnectTimeout=3", "-o", "BatchMode=yes",
             cfg.SSH_ALIAS, "echo ok"],
            capture_output=True, text=True, timeout=5,
        )
        return result.returncode == 0 and "ok" in result.stdout
    except Exception:
        return False


def _agent_ok(client) -> bool:
    try:
        return client.health().get("status") == "ok"
    except Exception:
        return False


def nt8_agent_ok() -> bool:
    from services import runner_dispatch
    return _agent_ok(runner_dispatch)


def mt5_agent_ok() -> bool:
    from services import mt5_agent_client
    return _agent_ok(mt5_agent_client)


def mt5_terminal_status() -> Optional[dict]:
    """`{mt5_connected, account, server, error}` — or None when the agent is unreachable.

    None is NOT "disconnected". An agent we cannot ask has told us nothing, and
    reporting that as a disconnected terminal would be inventing a measurement.
    """
    from services import mt5_agent_client
    try:
        raw = mt5_agent_client.status()
    except Exception:
        return None
    return {
        "connected": bool(raw.get("mt5_connected")),
        "account": raw.get("account"),
        "server": raw.get("server"),
        "error": raw.get("error"),
    }


def busy_scopes() -> set[str]:
    """Lock scopes with a job in flight — the supervisor must not disturb these.

    A `python` run belongs in the MT5 set as well: the local runner pulls its
    bars from the MT5 agent through the same tunnel, so restarting either kills
    the fetch mid-run.
    """
    from services import lab_db
    try:
        running = lab_db.get_running_job()
    except Exception:
        # Cannot tell → assume busy. Doing nothing is always safe; the wrong
        # guess in the other direction kills a live run.
        return {"nt8", "mt5", "python"}
    return {scope for scope, info in running.items() if info.get("running")}


# ── One pass ──────────────────────────────────────────────────────────────────

def supervise_once(sleeper: Callable[[float], None] = time.sleep) -> dict:
    """Probe, repair what is safe to repair, and return what happened.

    The return value is the whole point of it being a function rather than a
    loop body: it is what the tests assert on, and what the log line is built
    from. `sleeper` is injected so a test does not wait 20 real seconds.
    """
    actions: list[str] = []
    tunnel = tunnel_up()
    nt8 = nt8_agent_ok()
    mt5 = mt5_agent_ok()
    busy = busy_scopes()

    # A tunnel holding its ports while BOTH agents are silent is the stale case
    # backend/CLAUDE.md documents: the old `ssh -N -L` survives and forwards
    # into a dead agent, so restarting the agents alone never recovers.
    stale = tunnel and not nt8 and not mt5

    # ⚠ THE BUSY GUARD APPLIES TO THE STALE CASE ONLY, AND THE ASYMMETRY IS THE
    # POINT. An UNBOUND port is unambiguous: nothing can connect, so every call
    # through that tunnel is already failing and rebuilding it cannot make a
    # running job worse — it is the only route by which one survives. A BOUND
    # port with silent agents is a guess, and it has a real false positive: an
    # agent driving a heavy backtest can stop answering /health while working
    # perfectly (the NT8 agent does exactly this under pywinauto). Killing the
    # tunnel there would break the job it was mid-way through reporting on.
    if not tunnel:
        if not vps_reachable():
            actions.append("tunnel-skipped (VPS unreachable)")
        else:
            restart_tunnel()
            actions.append("tunnel-reopened" + (f" (job running: {','.join(sorted(busy))})" if busy else ""))
            nt8 = nt8_agent_ok()
            mt5 = mt5_agent_ok()
    elif stale:
        if busy:
            actions.append(f"stale-tunnel-skipped (busy: {','.join(sorted(busy))})")
        elif not vps_reachable():
            actions.append("tunnel-skipped (VPS unreachable)")
        else:
            restart_tunnel()
            actions.append("tunnel-restarted")
            nt8 = nt8_agent_ok()
            mt5 = mt5_agent_ok()

    for name, ok, task, scopes in (
        ("nt8", nt8, NT8_TASK, {"nt8"}),
        ("mt5", mt5, MT5_TASK, {"mt5", "python"}),
    ):
        if ok:
            continue
        if busy & scopes:
            # ⚠ ORPHAN. The agent is silent AND its scope holds a running job,
            # so that job cannot be progressing — but the supervisor still will
            # not restart the agent, because "dead" and "busy driving my job and
            # too loaded to answer /health" look identical from here and the
            # wrong guess kills a live run. It is stated rather than repaired:
            # clear the lock (Stop, or restart the backend, which resets stale
            # rows on boot) and the next pass restarts the agent by itself.
            actions.append(f"{name}-DOWN-with-a-job-running (lock held by "
                           f"{','.join(sorted(busy & scopes))} — Stop it or restart the backend)")
            continue
        if not port_bound(NT8_PORT if name == "nt8" else MT5_PORT):
            # No forward to reach the agent through — firing its task would
            # "succeed" and change nothing observable.
            actions.append(f"{name}-skipped (no tunnel)")
            continue
        try:
            schtasks_run(task)
        except SchtaskError as exc:
            actions.append(f"{name}-fire-failed ({exc})")
            continue
        sleeper(AGENT_GRACE_SECONDS)
        # schtasks lies about success — the re-probe is the only real evidence.
        came_up = nt8_agent_ok() if name == "nt8" else mt5_agent_ok()
        actions.append(f"{name}-started" if came_up else f"{name}-fired-but-still-down")
        if name == "nt8":
            nt8 = came_up
        else:
            mt5 = came_up

    return {"tunnel": tunnel_up(), "nt8": nt8, "mt5": mt5, "actions": actions}


# ── The loop ──────────────────────────────────────────────────────────────────

def run_forever(interval: int = INTERVAL_SECONDS) -> None:
    while not _stop.is_set():
        try:
            result = supervise_once()
            if result["actions"]:
                log.info("agent supervisor: %s", "; ".join(result["actions"]))
        except Exception:
            # A supervisor that dies on one bad pass is a supervisor that is off
            # for the rest of the session, and its failure mode is silence.
            log.exception("agent supervisor pass failed")
        _stop.wait(interval)


def start(interval: int = INTERVAL_SECONDS) -> threading.Thread:
    _stop.clear()
    thread = threading.Thread(target=run_forever, args=(interval,), daemon=True,
                              name="agent-supervisor")
    thread.start()
    return thread


def stop() -> None:
    _stop.set()
