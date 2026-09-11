"""The box refuses SSH before login when it is crowded — only that refusal is asked again.

MEASURED 2026-09-11: 3 of 8 single connections refused with `kex_exchange_identification`, from
an internet address holding 19 half-open connections against the box's default `MaxStartups`.
Every Bots-page load lost a bot or two to a 500. Rules: `services/vps_ssh.py`.

⚠ A fail-watch against HEAD is VACUOUS — the module did not exist — so non-vacuity is by
MUTATION, named per test.
"""

from __future__ import annotations

import ast
import subprocess
from pathlib import Path

import pytest
from routers import bots
from services import agent_supervisor, vps_ssh

REFUSED = (
    b"kex_exchange_identification: read: Connection reset by peer\r\n"
    b"Connection reset by 45.82.164.112 port 22"
)
# Seen the same day and NOT provably before login, so NOT retried.
CLOSED = b"Connection closed by 45.82.164.112 port 22"


def _done(rc: int, out: bytes = b"", err: bytes = b"") -> subprocess.CompletedProcess:
    return subprocess.CompletedProcess(["ssh"], rc, out, err)


@pytest.fixture
def box(monkeypatch):
    """Script what `subprocess.run` answers, one result per call, and record every wait."""
    state = {"answers": [], "calls": 0, "waits": []}

    def fake_run(argv, **kwargs):
        state["calls"] += 1
        a = state["answers"].pop(0)
        if isinstance(a, BaseException):
            raise a
        return a

    monkeypatch.setattr(subprocess, "run", fake_run)
    monkeypatch.setattr(vps_ssh, "_sleep", lambda s: state["waits"].append(s))
    return state


# ── the rule ────────────────────────────────────────────────────────────────────


def test_a_refusal_before_login_is_recognised_in_bytes_and_in_text():
    """MUTATION: drop the bytes decode — the bytes case reddens (killed 2026-09-11)."""
    assert vps_ssh.refused_before_login(_done(255, err=REFUSED))
    assert vps_ssh.refused_before_login(_done(255, err=REFUSED.decode()))


def test_only_ssh_s_own_failure_code_counts():
    """A remote program that prints the same words and exits 1 ran — it must not be retried.
    MUTATION: drop the 255 check — this reddens (killed 2026-09-11)."""
    assert not vps_ssh.refused_before_login(_done(1, err=REFUSED))


def test_a_close_later_in_the_handshake_is_not_a_refusal_before_login():
    """It can come after the protocol started, so a write could have run.
    MUTATION: match any 255 — this reddens (killed 2026-09-11)."""
    assert not vps_ssh.refused_before_login(_done(255, err=CLOSED))


def test_a_result_with_no_stderr_is_not_a_refusal():
    assert not vps_ssh.refused_before_login(_done(255, err=None))


# ── the retry ───────────────────────────────────────────────────────────────────


def test_a_refused_call_is_asked_again_and_the_answer_comes_back(box):
    """MUTATION: return the first result unconditionally — this reddens (killed 2026-09-11)."""
    box["answers"] = [_done(255, err=REFUSED), _done(255, err=REFUSED), _done(0, b"ok")]
    r = vps_ssh.run(["ssh", "forexvps", "echo ok"], capture_output=True, timeout=30)
    assert (r.returncode, r.stdout) == (0, b"ok")
    assert box["calls"] == 3
    assert box["waits"] == [0.5, 1.0], "it waited between tries, shortest first"


def test_it_gives_up_after_the_last_wait_and_hands_back_the_refusal(box):
    """Never loops for ever: one try per wait plus the last one, then the refusal is returned
    for the caller to report. MUTATION: drop the final attempt — the call count reddens
    (killed 2026-09-11)."""
    n = len(vps_ssh.RETRY_DELAYS) + 1
    box["answers"] = [_done(255, err=REFUSED) for _ in range(n)]
    r = vps_ssh.run(["ssh", "forexvps", "x"], capture_output=True, timeout=30)
    assert r.returncode == 255 and vps_ssh.refused_before_login(r)
    assert box["calls"] == n
    assert box["waits"] == list(vps_ssh.RETRY_DELAYS)


def test_any_other_failure_is_handed_back_after_ONE_try(box):
    """A later-handshake close, a remote exit code — asked once, never again."""
    box["answers"] = [_done(255, err=CLOSED)]
    assert vps_ssh.run(["ssh", "forexvps", "x"], capture_output=True).returncode == 255
    box["answers"] = [_done(1, err=REFUSED)]
    assert vps_ssh.run(["ssh", "forexvps", "x"], capture_output=True).returncode == 1
    assert box["calls"] == 2 and box["waits"] == []


def test_a_timeout_is_never_retried(box):
    """A command that timed out may be RUNNING. MUTATION: catch it and retry — this reddens
    (killed 2026-09-11)."""
    box["answers"] = [subprocess.TimeoutExpired(["ssh"], 30), _done(0, b"ok")]
    with pytest.raises(subprocess.TimeoutExpired):
        vps_ssh.run(["ssh", "forexvps", "x"], capture_output=True, timeout=30)
    assert box["calls"] == 1


# ── the callers ─────────────────────────────────────────────────────────────────


def test_the_bots_page_s_ssh_rides_through_a_refusal(box):
    """The Bots page's every read and write goes through `_ssh`.
    MUTATION: `_ssh` back to `subprocess.run` — this reddens (killed 2026-09-11)."""
    box["answers"] = [_done(255, err=REFUSED), _done(0, b"677e7ce\r\n")]
    assert bots._ssh("git rev-parse --short HEAD") == "677e7ce"


def test_after_every_try_is_refused_the_page_is_told_the_box_could_not_be_asked(box):
    """Still `VpsUnreachable` — never an empty answer, which reads as 'nothing there'.
    MUTATION: `_ssh` returns the empty output instead of raising — this reddens (killed
    2026-09-11)."""
    box["answers"] = [_done(255, err=REFUSED) for _ in range(len(vps_ssh.RETRY_DELAYS) + 1)]
    with pytest.raises(bots.VpsUnreachable, match="kex_exchange_identification"):
        bots._ssh("echo ok")


def test_the_supervisor_does_not_read_a_refusal_as_the_vps_being_down(box):
    """`vps_reachable` decides between 'the VPS is down' and 'the tunnel died here'.
    MUTATION: `vps_reachable` back to `subprocess.run` — this reddens (killed 2026-09-11)."""
    box["answers"] = [
        _done(255, err=REFUSED.decode()),
        subprocess.CompletedProcess([], 0, "ok\n", ""),
    ]
    assert agent_supervisor.vps_reachable() is True


def _calls_skipping_the_retry(source: str, name: str) -> tuple[int, list[str]]:
    """Every call whose first argument is a list starting `"ssh"`, and which of them is not
    `vps_ssh.run`. The tunnel's long-lived `Popen` is exempt — the supervisor rebuilds it every
    pass, and a retry inside one start would change nothing."""
    seen, offenders = 0, []
    for node in ast.walk(ast.parse(source)):
        if not (isinstance(node, ast.Call) and node.args):
            continue
        first = node.args[0]
        if not (
            isinstance(first, ast.List)
            and first.elts
            and isinstance(first.elts[0], ast.Constant)
            and first.elts[0].value == "ssh"
        ):
            continue
        seen += 1
        f = node.func
        who = f"{getattr(f.value, 'id', '?')}.{f.attr}" if isinstance(f, ast.Attribute) else "?"
        if who not in ("vps_ssh.run", "subprocess.Popen"):
            offenders.append(f"{name}:{node.lineno} {who}")
    return seen, offenders


def test_NO_call_to_the_box_bypasses_the_retry():
    """A new call site running `["ssh", ...]` through `subprocess.run` directly misses the retry,
    and on a crowded box a third of its calls fail.
    ⚠ It reads SOURCE, so an in-memory mutation never reaches it — MEASURED: putting
    `_scan_terminals` back on `subprocess.run` in memory SURVIVED. The positive control below is
    what proves the scan can see a bypass."""
    root = Path(__file__).resolve().parent.parent
    seen, offenders = 0, []
    for path in sorted([*root.glob("routers/*.py"), *root.glob("services/*.py")]):
        if path.name != "vps_ssh.py":
            n, bad = _calls_skipping_the_retry(path.read_text(encoding="utf-8"), path.name)
            seen, offenders = seen + n, offenders + bad
    assert seen >= 6, f"found only {seen} ssh call sites — the scan stopped matching"
    assert not offenders, "calls to the box that skip vps_ssh.run: " + ", ".join(offenders)


def test_the_bypass_scan_can_SEE_a_bypass():
    """The positive control for the scan above: a direct `subprocess.run(["ssh", ...])` is
    flagged by its line, and neither the helper nor the tunnel's `Popen` is."""
    src = (
        "import subprocess\n"
        'subprocess.run(["ssh", host, cmd], capture_output=True)\n'
        'vps_ssh.run(["ssh", host, cmd], capture_output=True)\n'
        'subprocess.Popen(["ssh", "-N", host])\n'
    )
    assert _calls_skipping_the_retry(src, "x.py") == (3, ["x.py:2 subprocess.run"])


# ── the answer the page gets ────────────────────────────────────────────────────


def test_a_box_that_cannot_be_asked_is_a_502_not_a_500(client, monkeypatch):
    """It was a 500 with a traceback — 'this backend is broken' — for the box not answering.
    MUTATION: remove the handler — the TestClient raises instead (killed 2026-09-11)."""

    def refused(cmd):
        raise bots.VpsUnreachable("kex_exchange_identification: read: Connection reset by peer")

    monkeypatch.setattr(bots, "_ssh", refused)
    r = client.get("/bots/sos_fade_demo/version")
    assert r.status_code == 502
    assert r.json()["detail"].startswith("Cannot reach the VPS — kex_exchange_identification")


def test_a_box_that_did_not_answer_in_time_is_a_504(client, monkeypatch):
    """MUTATION: remove the timeout handler — the TestClient raises instead (killed 2026-09-11)."""

    def slow(cmd):
        raise subprocess.TimeoutExpired(["ssh", "forexvps", cmd], 30)

    monkeypatch.setattr(bots, "_ssh", slow)
    r = client.get("/bots/sos_fade_demo/version")
    assert r.status_code == 504
    assert r.json()["detail"] == "ssh did not answer within 30s"
