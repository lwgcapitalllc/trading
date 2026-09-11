"""The live-VPS guard, in this process and in every process a test starts.

⚠ **Every case is built so a BROKEN guard fails it without reaching the box.** The port cases point
the guard at a spare local port (a broken guard gets a refused connection, not the tunnel), and the
ssh cases run `ssh -V`, which prints a version and connects to nothing.

Mutation map, RUN 2026-09-10 through scripts/testing/mutate.py (5 planted, 5 killed):
  the socket half of install() removed               -> a_child_process_refuses_a_tunnel_port
  the process half of install() removed               -> a_child_process_refuses_ssh
  arm_children() no longer sets the environment flag  -> a_child_process_refuses_a_tunnel_port
  only-loopback check dropped (every host refused)    -> only_a_loopback_tunnel_port_is_refused
  the config's ports ignored                          -> read_from_the_backends_config
🔴 TWO SURVIVED THE FIRST PASS. The start-up hook loaded the guard BEFORE installing the bug planter,
so a bug planted in the guard never reached a child - a real ordering defect in the hook, fixed
there. And the real config holds exactly the fallback ports, so reading it and ignoring it gave the
same answer; the case now also reads a config whose ports differ.
"""

from __future__ import annotations

import json
import os
import socket
import subprocess
import sys
from urllib.parse import urlparse

import pytest

from scripts.testing import vps_guard


def _spare_port() -> int:
    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    port = s.getsockname()[1]
    s.close()
    return port


def test_the_ports_and_the_alias_are_read_from_the_backends_config(monkeypatch, tmp_path):
    monkeypatch.delenv("LWG_TEST_GUARD_PORTS", raising=False)
    cfg = json.loads((vps_guard.REPO / "command-center/backend/config.json").read_text())
    alias, ports = vps_guard.targets()
    assert alias == cfg["ssh_alias"]
    assert ports == {urlparse(cfg[k]).port for k in ("nt8_agent_tunnel", "mt5_agent_tunnel")}
    # The real file holds exactly the fallback values, so it cannot show the file was READ - a
    # guard ignoring it would pass the lines above. A moved tunnel must move the guard.
    moved = tmp_path / "config.json"
    moved.write_text(
        json.dumps(
            {
                "ssh_alias": "elsewhere",
                "nt8_agent_tunnel": "http://127.0.0.1:9001",
                "mt5_agent_tunnel": "http://127.0.0.1:9002",
            }
        )
    )
    assert vps_guard.targets(moved) == ("elsewhere", {9001, 9002})


def test_extra_ports_can_only_be_ADDED(monkeypatch):
    monkeypatch.delenv("LWG_TEST_GUARD_PORTS", raising=False)
    _, base = vps_guard.targets()
    monkeypatch.setenv("LWG_TEST_GUARD_PORTS", "12345")
    _, more = vps_guard.targets()
    assert more == base | {12345}


def test_an_ssh_program_or_the_alias_is_refused_and_an_ordinary_command_is_not():
    assert vps_guard.refuses_argv(["ssh", "-V"], "forexvps")
    assert vps_guard.refuses_argv(["/usr/bin/scp", "a", "b"], "forexvps")
    assert vps_guard.refuses_argv(["pkill", "-f", "ssh -N.*forexvps"], "forexvps")
    assert not vps_guard.refuses_argv(["git", "status"], "forexvps")


def test_only_a_loopback_tunnel_port_is_refused():
    ports = {8766}
    assert vps_guard.refuses_address(("127.0.0.1", 8766), ports)
    assert vps_guard.refuses_address(("::1", 8766, 0, 0), ports)
    assert not vps_guard.refuses_address(("127.0.0.1", 8000), ports)
    # A service elsewhere on the same port number is not the box's tunnel.
    assert not vps_guard.refuses_address(("example.com", 8766), ports)


def test_the_guard_is_not_an_exception():
    """Every probe on this path catches Exception and reports "the box is down"."""
    assert not issubclass(vps_guard.LiveVpsCall, Exception)


def test_a_child_process_refuses_a_tunnel_port():
    port = _spare_port()
    env = dict(os.environ, LWG_TEST_GUARD_PORTS=str(port))
    code = f"import socket; socket.socket().connect(('127.0.0.1', {port}))"
    proc = subprocess.run([sys.executable, "-c", code], env=env, capture_output=True, text=True)
    assert proc.returncode != 0 and "LiveVpsCall" in proc.stderr, proc.stderr[-400:]


def test_a_child_process_refuses_ssh():
    code = "import subprocess; subprocess.run(['ssh', '-V'])"
    proc = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True)
    assert proc.returncode != 0 and "LiveVpsCall" in proc.stderr, proc.stderr[-400:]


def test_this_process_refuses_ssh_too():
    with pytest.raises(BaseException) as caught:
        subprocess.run(["ssh", "-V"], capture_output=True)
    assert type(caught.value).__name__ == "LiveVpsCall"
