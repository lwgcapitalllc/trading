"""No test may reach the live trading box - enforced in EVERY process a test run starts.

The backend suite has always refused an agent call or an ssh command from INSIDE a test
(`command-center/backend/tests/conftest.py::_no_live_vps`). 🔴 **It could not follow a test into a
process it started, and one did: a stress-test case spawns a real worker pool, and each worker asked
the trading box's terminal which broker was attached before failing** (2026-09-10). A fixture lives
in one process; this module is loaded into every Python process a test run starts, through the
`sitecustomize` beside it, so a worker pool, an xdist worker or a script run by subprocess inherits
the refusal without anybody remembering to pass it on.

Two doors, the same two the fixture guards:

- **a socket connect to an agent TUNNEL port on this machine** - `ssh -L` binds 8765 and 8766
  locally, so a connection there is a connection to the box whenever the tunnel is up;
- **a process start naming an ssh client, or the box's ssh alias anywhere in its argv** - which is
  also what catches `pkill -f "ssh -N.*forexvps"` killing the developer's own tunnel.

⚠ **It raises a `BaseException`**, like the fixture, because every probe on this path catches
`Exception` and reports "the box is down" - a catchable guard is swallowed by the code it polices.

⚠ **The ports and the alias are READ from the backend's own config**, never typed here, so a moved
tunnel moves the guard. If that file cannot be read the guard still refuses the values it has always
had: a safety check that turns itself off when a file is missing is not a safety check.

Standard library only: it is loaded by path into processes that have not imported anything yet.
"""

from __future__ import annotations

import json
import os
import socket
import subprocess
from pathlib import Path
from urllib.parse import urlparse

REPO = Path(__file__).resolve().parents[2]
ENV = "LWG_TEST_NO_LIVE_VPS"
HOOKS = Path(__file__).resolve().parent / "child_hooks"
_LOOPBACK = {"127.0.0.1", "localhost", "::1", "0.0.0.0", ""}
_SSH_PROGRAMS = {"ssh", "scp", "sftp"}


class LiveVpsCall(BaseException):
    """A test (or a process a test started) tried to reach the live trading box."""


def targets(config_path=None):
    """(ssh alias, {tunnel ports}) - read off command-center/backend/config.json.

    `LWG_TEST_GUARD_PORTS` ADDS ports and can never remove one: the guard's own tests point it at a
    spare local port, so a broken guard fails them on a refused connection rather than by reaching
    the box. `config_path` exists for the same tests: the real file holds exactly the fallback
    values, so only a different file can show the guard READ it.
    """
    alias, ports = (
        "forexvps",
        {8765, 8766},
    )  # what the file has always held; used only if unreadable
    path = config_path or REPO / "command-center" / "backend" / "config.json"
    try:
        cfg = json.loads(Path(path).read_text())
        alias = cfg.get("ssh_alias") or alias
        read = {urlparse(cfg.get(k) or "").port for k in ("nt8_agent_tunnel", "mt5_agent_tunnel")}
        read.discard(None)
        ports = read or ports
    except (OSError, ValueError):
        pass
    extra = os.environ.get("LWG_TEST_GUARD_PORTS", "")
    ports = set(ports) | {int(p) for p in extra.split(",") if p.strip().isdigit()}
    return alias, ports


def refuses_argv(args, alias: str) -> bool:
    argv = [str(a) for a in args] if isinstance(args, (list, tuple)) else str(args).split()
    if not argv:
        return False
    if os.path.basename(argv[0]) in _SSH_PROGRAMS:
        return True
    return bool(alias) and any(alias in a for a in argv)


def refuses_address(address, ports) -> bool:
    return (
        isinstance(address, tuple)
        and len(address) >= 2
        and address[1] in ports
        and str(address[0]) in _LOOPBACK
    )


def install() -> None:
    """Refuse both doors in THIS process. Idempotent."""
    if getattr(socket.socket.connect, "_lwg_guard", False):
        return
    alias, ports = targets()
    real_connect, real_connect_ex = socket.socket.connect, socket.socket.connect_ex
    real_init = subprocess.Popen.__init__

    def connect(self, address):
        if refuses_address(address, ports):
            raise LiveVpsCall(
                f"A test process tried to connect to {address} - an agent tunnel port on this "
                "machine, i.e. the live trading box whenever the tunnel is up. Stub the call."
            )
        return real_connect(self, address)

    def connect_ex(self, address):
        if refuses_address(address, ports):
            raise LiveVpsCall(
                f"A test process tried to probe {address} - an agent tunnel port. Stub the probe."
            )
        return real_connect_ex(self, address)

    def popen_init(self, args, *a, **kw):
        if refuses_argv(args, alias):
            raise LiveVpsCall(
                f"A test process tried to start {args!r}, which reaches the live trading box "
                "over ssh. Stub the function that shells out."
            )
        return real_init(self, args, *a, **kw)

    for fn in (connect, connect_ex, popen_init):
        fn._lwg_guard = True
    socket.socket.connect = connect
    socket.socket.connect_ex = connect_ex
    subprocess.Popen.__init__ = popen_init


def arm_children() -> None:
    """Every Python process started from here on loads the guard at start-up."""
    os.environ[ENV] = "1"
    parts = [p for p in os.environ.get("PYTHONPATH", "").split(os.pathsep) if p]
    if str(HOOKS) not in parts:
        os.environ["PYTHONPATH"] = os.pathsep.join([str(HOOKS), *parts])
