"""Every kill this router issues must name the process it is allowed to kill.

`_kill_bot` matches on **both** `name='python.exe'` and the `--bot <key>` flag, and that pair
is the whole safety property. Drop either half and the match widens in a way nothing on the
page can show you:

- without `name='python.exe'` the pattern matches the `cmd.exe` and `wmic.exe` hosting the
  very command being run (their commandline contains the bot key, because the key is in the
  query), so the kill can terminate itself — and any other non-python process that merely
  mentions the key.
- without the `--bot ` prefix it matches `promote.py --bot <key>` and
  `startup_coordinator.py --bot <key>`, i.e. the deploy and the launcher, not the bot.

This was live until 2026-08-04: the fleet Stop was fixed on 2026-08-03 and the four PER-BOT
call sites were not, while the commit that fixed the fleet asserted "the per-bot routes
already did this correctly." That is why the last test here is a SOURCE check rather than a
behavioural one — a behavioural test only covers the routes somebody remembered to write one
for, and the defect was in the routes nobody thought to check.

Same class as `taskkill /f /im python.exe`, which killed the live bot for three days in July.
"""

import pytest

from routers import bots


@pytest.fixture
def ssh(monkeypatch):
    """Capture every command the router sends, and send nothing."""
    sent: list[str] = []

    def fake_ssh(cmd: str) -> str:
        sent.append(cmd)
        return ""

    monkeypatch.setattr(bots, "_ssh", fake_ssh)
    monkeypatch.setattr(bots, "_notify_telegram", lambda *_a, **_k: None)
    monkeypatch.setattr(bots._time, "sleep", lambda *_a: None)
    return sent


def _kills(sent: list[str]) -> list[str]:
    return [c for c in sent if "call terminate" in c]


def _assert_scoped(cmd: str, bot_key: str) -> None:
    assert "name='python.exe'" in cmd, f"kill is not limited to python: {cmd}"
    assert f"--bot {bot_key}" in cmd, f"kill does not match the --bot flag: {cmd}"


# ── The routes ────────────────────────────────────────────────────────────────

def test_stop_bot_kills_only_this_bots_python_process(ssh):
    bots.stop_bot("MPC SOS Fade")
    kills = _kills(ssh)
    assert len(kills) == 1
    _assert_scoped(kills[0], "mpc_sos_fade_demo")


def test_restart_bot_kills_only_this_bots_python_process(ssh):
    bots.restart_bot("MPC SOS Fade")
    kills = _kills(ssh)
    assert len(kills) == 1
    _assert_scoped(kills[0], "mpc_sos_fade_demo")


def test_stop_all_kills_only_registered_bots_python_processes(ssh):
    bots.stop_bots()
    kills = _kills(ssh)
    assert kills, "stop-all issued no kill at all"
    for cmd in kills:
        _assert_scoped(cmd, "mpc_sos_fade_demo")


def test_the_suppress_write_happens_before_the_kill(ssh):
    """Order matters — the crash monitor alerts on a bot that dies unannounced."""
    bots.stop_bot("MPC SOS Fade")
    suppress = next(i for i, c in enumerate(ssh) if "stop_suppress.json" in c)
    kill     = next(i for i, c in enumerate(ssh) if "call terminate" in c)
    assert suppress < kill


# ── The routes nobody wrote a test for ────────────────────────────────────────

def test_no_call_site_builds_its_own_terminate_command():
    """One kill, one place. A second `call terminate` anywhere in this module is a second
    chance to omit a clause, which is exactly how the four per-bot routes drifted.

    Reads the AST rather than the raw text, so the phrase may appear freely in comments and
    docstrings (it does — that is where the reasoning lives) and only a real string LITERAL
    being built into a command counts.
    """
    import ast
    import inspect

    tree = ast.parse(inspect.getsource(bots))
    guilty = set()
    for fn in ast.walk(tree):
        if not isinstance(fn, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        body = fn.body[1:] if ast.get_docstring(fn) else fn.body
        for node in ast.walk(ast.Module(body=body, type_ignores=[])):
            if isinstance(node, ast.Constant) and isinstance(node.value, str) \
                    and "call terminate" in node.value:
                guilty.add(fn.name)

    assert guilty == {"_kill_bot"}, (
        f"a `call terminate` command is built in {sorted(guilty - {'_kill_bot'})} — route it "
        f"through _kill_bot instead, so the process-name and --bot clauses cannot be forgotten"
    )


def test_kill_bot_carries_both_clauses():
    cmd = None

    def capture(c: str) -> str:
        nonlocal cmd
        cmd = c
        return ""

    real = bots._ssh
    bots._ssh = capture
    try:
        bots._kill_bot("some_bot_key")
    finally:
        bots._ssh = real
    _assert_scoped(cmd, "some_bot_key")
