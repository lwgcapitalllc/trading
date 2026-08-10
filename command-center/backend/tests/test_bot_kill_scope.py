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
    """Capture every command the router sends, and send nothing.

    The bot answers the liveness probe as GONE, so the graceful stop succeeds and no kill is
    issued — see `stubborn_ssh` for the escalation path. `_time.sleep` is neutered so the
    30-second grace window costs nothing here.
    """
    sent: list[str] = []

    def fake_ssh(cmd: str) -> str:
        sent.append(cmd)
        return ""              # `get processid` with no digits = the process is gone

    monkeypatch.setattr(bots, "_ssh", fake_ssh)
    monkeypatch.setattr(bots, "_notify_telegram", lambda *_a, **_k: None)
    monkeypatch.setattr(bots._time, "sleep", lambda *_a: None)
    return sent


@pytest.fixture
def stubborn_ssh(monkeypatch):
    """A bot that ignores its stop request, so every route escalates to the kill.

    This is the fixture the SCOPE tests need: the safety property they protect is about the
    terminate command, and after 2026-08-07 a healthy bot never reaches it.
    """
    sent: list[str] = []

    def fake_ssh(cmd: str) -> str:
        sent.append(cmd)
        return "ProcessId\n9620\n" if "get processid" in cmd else ""

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

def test_stop_bot_kills_only_this_bots_python_process(stubborn_ssh):
    bots.stop_bot("MPC SOS Fade")
    kills = _kills(stubborn_ssh)
    assert len(kills) == 1
    _assert_scoped(kills[0], "mpc_sos_fade_demo")


def test_restart_bot_kills_only_this_bots_python_process(stubborn_ssh):
    bots.restart_bot("MPC SOS Fade")
    kills = _kills(stubborn_ssh)
    assert len(kills) == 1
    _assert_scoped(kills[0], "mpc_sos_fade_demo")


def test_stop_all_kills_only_registered_bots_python_processes(stubborn_ssh):
    """Every kill stop-all issues is scoped to a bot in the REGISTRY, and there is one per bot.

    ⚠ The roster is READ from `bots._BOTS` rather than restated here. This test named
    `mpc_sos_fade_demo` literally until 2026-08-09 and went red the moment a second bot was
    registered — a roster stated twice is two rosters, and the one in the test is the one nobody
    updates. What is being checked is the SCOPING rule, which is per-bot; which bots exist is the
    registry's business.
    """
    bots.stop_bots()
    kills = _kills(stubborn_ssh)
    assert kills, "stop-all issued no kill at all"
    registered = [b.key for b in bots._BOTS]
    assert len(kills) == len(registered)
    for cmd, key in zip(kills, registered):
        _assert_scoped(cmd, key)


# ── asking first (2026-08-07) ────────────────────────────────────────────────
#
# 🔴 Stop was a hard kill, so the bot never wrote its `shutdown` record and the NEXT startup
# reported "the previous run ended WITHOUT a shutdown record: it was killed, it crashed, or the
# box went down." That is the silent-death detector, and it fired on every deliberate restart.

def test_a_bot_that_shuts_itself_down_is_never_killed(ssh):
    """The whole point. A clean stop must leave no terminate command behind at all — otherwise
    the bot is killed a moment after it exited and the record is ambiguous again."""
    bots.stop_bot("MPC SOS Fade")
    assert _kills(ssh) == []


def test_the_stop_request_is_written_before_anything_waits(ssh):
    """Order matters as much as it does for the suppress marker: waiting first would just be a
    30-second pause in front of a kill."""
    bots.stop_bot("MPC SOS Fade")
    writes = [i for i, c in enumerate(ssh) if "stop.request" in c and "del " not in c]
    assert writes, "no stop request was written"
    probes = [i for i, c in enumerate(ssh) if "get processid" in c]
    assert not probes or writes[0] < probes[0]


def test_the_request_file_is_removed_on_the_clean_path(ssh):
    """⚠ A stop file that outlives its stop would halt the NEXT start seconds after boot, and a
    bot that will not stay up is a far worse failure than the noisy chip this replaces. The bot
    clears it at startup too; this is the belt to that brace."""
    bots.stop_bot("MPC SOS Fade")
    assert any("del " in c and "stop.request" in c for c in ssh)


def test_the_request_file_is_removed_after_an_escalation_too(stubborn_ssh):
    """The path where the bot never noticed. Leaving the file here is the likelier of the two —
    the bot that ignored it is also the bot that will not clear it."""
    bots.stop_bot("MPC SOS Fade")
    assert any("del " in c and "stop.request" in c for c in stubborn_ssh)


def test_the_suppress_write_happens_before_the_kill(stubborn_ssh):
    """Order matters — the crash monitor alerts on a bot that dies unannounced.

    ⚠ Uses the STUBBORN fixture, because after 2026-08-07 a healthy bot is never killed and
    there would be no kill to order against. The suppression still has to precede it on the one
    path that still terminates something.
    """
    bots.stop_bot("MPC SOS Fade")
    suppress = next(i for i, c in enumerate(stubborn_ssh) if "stop_suppress.json" in c)
    kill     = next(i for i, c in enumerate(stubborn_ssh) if "call terminate" in c)
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


def test_kill_bot_carries_both_clauses(stubborn_ssh):
    """The escalation command itself, in isolation.

    ⚠ It selects the terminate command by name rather than taking the last thing sent. It used
    to take the last, which was the kill — it is now the `del` of the stop request, and a test
    that reads position rather than content starts asserting the wrong string the moment the
    sequence grows.
    """
    bots._kill_bot("some_bot_key")
    kills = _kills(stubborn_ssh)
    assert len(kills) == 1
    _assert_scoped(kills[0], "some_bot_key")
