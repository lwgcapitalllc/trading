"""The crash watchdog, and the heartbeat it depends on.

**Why this file exists.** SYS_MONITOR was written with two checks: the process is gone, and
the process is alive but its loop has stopped turning. The second one had never worked.
Nothing wrote the `heartbeat` field it reads, and the check reads a missing field as 0 and
then asks `0 > 300` — so it was permanently false. Found on 2026-07-31, while enabling the
task, by reading it rather than by running it.

That failure mode is the reason for this file. A watchdog that breaks LOUDLY costs an hour;
a watchdog that breaks SILENTLY costs whatever the unwatched thing does next, because an
empty alert channel is indistinguishable from a healthy system. So the tests below pin the
contract from both ends — the runner writes the stamp, the monitor reads it, and neither
side can quietly stop honouring it without going red.

No MT5 and no Telegram: `send_alert` is stubbed, so a test can never post to a real chat.
"""

from __future__ import annotations

import ast
import os
import sys
import time
from pathlib import Path
from types import SimpleNamespace

import pytest

_REPO = Path(__file__).resolve().parent.parent.parent
for _p in (str(_REPO), str(_REPO / "algos" / "live"), str(_REPO / "algos" / "shared"),
           str(_REPO / "algos" / "notifications")):
    if _p not in sys.path:
        sys.path.insert(0, _p)

import monitor                                                       # noqa: E402
from runner import LiveRunner                                        # noqa: E402


# ── the runner's half of the contract ───────────────────────────────────────────
class _StateModule:
    """Stands in for the `bot_state` module the runner writes through."""

    def __init__(self):
        self.written = {}

    def write_bot(self, bot_key, updates):
        self.written.setdefault(bot_key, {}).update(updates)

    # The two the heartbeat needs to derive total_pnl_pct. `_heartbeat` deliberately does
    # NOT hasattr-guard them: a renamed bot_state function must fail here rather than
    # silently stop reporting P&L on the live box.
    def ensure_starting_balance(self, bot_key, balance):
        self.written.setdefault(bot_key, {}).setdefault("starting_balance", balance)

    def read_bot(self, bot_key):
        return dict(self.written.get(bot_key, {}))


def _runner(monkeypatch, *, balance_raises=False):
    r = LiveRunner.__new__(LiveRunner)
    r.cfg = SimpleNamespace(bot_key="bot", account=1, symbol="XAUUSD.s",
                            strategy_version="1.0.0", strategy_package="demo_pkg",
                            promoted_commit="abc1234", promoted_at="2026-08-03",
                            is_frozen=True)
    r.bridge = SimpleNamespace(state=SimpleNamespace(value="idle"))
    r.source_hash = "0123456789abcdef"
    r.dry_run = True
    r.feed = SimpleNamespace(last_bar_time=None)
    r.warnings = []
    r.log = SimpleNamespace(info=lambda *a, **k: None,
                            warning=lambda m: r.warnings.append(m),
                            error=lambda *a, **k: None)

    # The runner imports MetaTrader5 INSIDE _heartbeat, so a fake module in sys.modules is
    # enough — no MT5 install, and it works identically on the Mac and the VPS.
    def _account_info():
        if balance_raises:
            raise RuntimeError("terminal not connected")
        return SimpleNamespace(balance=2000.0)

    monkeypatch.setitem(sys.modules, "MetaTrader5",
                        SimpleNamespace(account_info=_account_info))
    return r


def test_the_loop_stamps_a_heartbeat(monkeypatch):
    """The whole feature in one assertion: SYS_MONITOR has nothing to read without this."""
    r = _runner(monkeypatch)
    st = _StateModule()
    r._heartbeat(st)

    written = st.written["bot"]
    assert "heartbeat" in written, "no stamp — the stalled-loop check goes permanently blind"
    assert abs(written["heartbeat"] - time.time()) < 5
    assert written["balance"] == 2000.0


def test_a_broken_balance_read_does_not_swallow_the_heartbeat(monkeypatch):
    """The balance lookup is best-effort and the stamp is not.

    These were one try block, so any MT5 hiccup dropped the heartbeat too — which would
    have reported a perfectly healthy loop as stalled the moment the watchdog worked at all.
    """
    r = _runner(monkeypatch, balance_raises=True)
    st = _StateModule()
    r._heartbeat(st)

    written = st.written["bot"]
    assert abs(written["heartbeat"] - time.time()) < 5
    assert written["balance"] is None
    assert any("Balance read failed" in w for w in r.warnings)


# ── the monitor's half ──────────────────────────────────────────────────────────
@pytest.fixture
def watch(monkeypatch):
    """Drive `check_bot` with a scripted bot state, capturing alerts instead of sending."""
    sent = []
    monkeypatch.setattr(monitor, "send_alert", lambda msg: sent.append(msg))
    monkeypatch.setattr(monitor, "is_running", lambda script: True)
    monkeypatch.setattr(monitor._bot_state, "set_status", lambda *a, **k: None)

    def run(live_state, carried=None):
        monkeypatch.setattr(monitor._bot_state, "read_bot", lambda k: live_state)
        state = {"running": True, **(carried or {})}
        return monitor.check_bot("mpc_sos_fade_demo", {"mpc_sos_fade_demo": state},
                                 "2026-07-31")

    return SimpleNamespace(run=run, sent=sent)


def test_a_fresh_heartbeat_is_not_stale(watch):
    out = watch.run({"heartbeat": time.time()})
    assert watch.sent == []
    assert not out["stale_alerted"]


def test_an_old_heartbeat_raises_the_stall_alert(watch):
    out = watch.run({"heartbeat": time.time() - 20 * 60})
    assert len(watch.sent) == 1
    assert "Loop Stalled" in watch.sent[0]
    assert out["stale_alerted"]


def test_the_stall_alert_is_sent_once_not_every_minute(watch):
    """The task runs every 60s. Re-alerting on each pass would train Aaron to mute it, and a
    muted channel is the same as no watchdog."""
    watch.run({"heartbeat": time.time() - 20 * 60}, carried={"stale_alerted": True})
    assert watch.sent == []


def test_a_recovered_loop_says_so(watch):
    out = watch.run({"heartbeat": time.time()}, carried={"stale_alerted": True})
    assert len(watch.sent) == 1
    assert "Recovered" in watch.sent[0]
    assert not out["stale_alerted"]


def test_a_running_bot_that_never_stamped_is_stale_not_silent(watch):
    """THE regression. A missing `heartbeat` used to read as 0 and disable the check.

    It now falls back to `started`, so a bot that booted 20 minutes ago and has never
    stamped is reported as the stalled bot it is.
    """
    out = watch.run({"started": time.time() - 20 * 60})
    assert len(watch.sent) == 1
    assert "Loop Stalled" in watch.sent[0]
    assert out["stale_alerted"]


def test_a_bot_that_just_booted_is_given_time_to_warm_up(watch):
    """Connecting to MT5 and replaying 5,000 warmup bars happens before the first stamp.
    A false alarm on every single start is how a watchdog gets turned off."""
    assert watch.run({"started": time.time() - 30}) is not None
    assert watch.sent == []


# ── bringing a dead bot back ────────────────────────────────────────────────────
#
# The gap this closes, measured. On 31 July a blanket `taskkill /f /im python.exe` killed the
# trading bot and the Telegram bot together. Telegram had a watchdog that restarts it, and was
# back within a minute. The trading bot only had an ALERT — one message, at 6pm on a Friday —
# and stayed dead for three days.
@pytest.fixture
def down(monkeypatch):
    """Drive `check_bot` against a bot whose process is gone, capturing the restart attempt."""
    sent, attempts = [], []
    monkeypatch.setattr(monitor, "send_alert", lambda msg: sent.append(msg))
    monkeypatch.setattr(monitor, "is_running", lambda script: False)
    monkeypatch.setattr(monitor._bot_state, "set_status", lambda *a, **k: None)
    monkeypatch.setattr(monitor._bot_state, "read_bot", lambda k: {})

    def run(carried=None, restart_succeeds=True):
        def _restart(bot_key):
            attempts.append(bot_key)
            return restart_succeeds
        monkeypatch.setattr(monitor, "restart_bot", _restart)
        state = {"running": True, **(carried or {})}
        return monitor.check_bot("mpc_sos_fade_demo", {"mpc_sos_fade_demo": state}, "2026-08-03")

    return SimpleNamespace(run=run, sent=sent, attempts=attempts)


def test_a_dead_bot_is_restarted_not_just_reported(down):
    out = down.run()
    assert down.attempts == ["mpc_sos_fade_demo"]
    assert out["running"] is True
    assert out["restart_tries"] == 0
    assert any("Restarted" in m for m in down.sent)


def test_a_deliberate_stop_is_not_fought(down, monkeypatch):
    """Stopping a bot has to be possible. Without this the watchdog relaunches it every 60
    seconds and the Stop button on the Bots page silently does nothing.

    Two passes, because suppression is CONSUMED at the offline transition: the pass that sees
    the bot go down reads the suppress key, and every pass after that reads the flag it left
    behind. Both have to decline to restart, or the bot comes back a minute after you stop it.
    """
    monkeypatch.setattr(monitor, "_is_stop_suppressed", lambda key: True)
    out = down.run()
    assert down.attempts == []
    assert out["stop_suppressed"] is True
    assert not any("Offline" in m for m in down.sent)     # asked for, so not an alarm

    steady = down.run(carried={"running": False, "stop_suppressed": True})
    assert down.attempts == []
    assert steady["running"] is False


def test_a_failed_restart_counts_toward_the_ceiling(down):
    out = down.run(restart_succeeds=False)
    assert out["restart_tries"] == 1
    assert out["running"] is False


def test_a_bot_that_will_not_start_gives_up_and_says_so_once(down):
    """A bot that dies on startup — a bad version pin, a refused MT5 login — must not be
    relaunched forever. The log fills with identical failures and the real error is buried."""
    out = down.run(carried={"running": False,
                            "restart_tries": monitor.MAX_BOT_RESTARTS},
                   restart_succeeds=False)
    assert down.attempts == []
    assert len(down.sent) == 1
    assert "Will Not Start" in down.sent[0]
    assert out["max_retry_alerted"]

    down.sent.clear()
    down.run(carried={"running": False,
                      "restart_tries": monitor.MAX_BOT_RESTARTS,
                      "max_retry_alerted": True})
    assert down.sent == []


def test_coming_back_clears_the_counter(watch):
    """Otherwise three lifetime restarts is the budget forever, and the fourth crash months
    later goes unattended."""
    out = watch.run({"heartbeat": time.time()},
                    carried={"running": False, "restart_tries": 2})
    assert out["restart_tries"] == 0
    assert not out["max_retry_alerted"]


# ── the two sides agree about which bots exist ──────────────────────────────────
def _coordinator_sequence():
    """Read STARTUP_SEQUENCE out of the launcher WITHOUT importing it.

    `startup_coordinator.py` hardcodes `Path("C:/trading/algos")` and imports from it at
    module scope, so it cannot be imported anywhere but the VPS. Parsing keeps this check
    running on the machine where the mistake actually gets made.
    """
    src = (_REPO / "algos" / "bots" / "startup_coordinator.py").read_text()
    for node in ast.walk(ast.parse(src)):
        if isinstance(node, ast.Assign) and getattr(node.targets[0], "id", "") == "STARTUP_SEQUENCE":
            out = []
            for elt in node.value.elts:
                bot_key = elt.elts[0].value
                argv = [a.value for a in elt.elts[3].elts]
                out.append((bot_key, argv))
            return out
    raise AssertionError("STARTUP_SEQUENCE not found in startup_coordinator.py")


def test_every_bot_the_vps_starts_is_watched():
    """A bot added to the launcher and forgotten here is a bot that can die unnoticed —
    and it fails in the quietest possible way, because everything still looks fine."""
    for bot_key, _ in _coordinator_sequence():
        assert bot_key in monitor.BOTS, f"{bot_key} boots on the VPS but nothing watches it"


def test_the_monitor_matches_the_commandline_the_launcher_actually_produces():
    """`is_running` greps the process commandline for `BOTS[key]["script"]`.

    Every live bot is `runner.py`, so the match has to be the bot_key in argv. If the two
    drift apart the watchdog reports a healthy bot as permanently offline (alert fatigue),
    or worse, matches a DIFFERENT bot's process and reports a dead one as alive.
    """
    for bot_key, argv in _coordinator_sequence():
        needle = monitor.BOTS[bot_key]["script"]
        assert needle in " ".join(argv), (
            f"{bot_key}: monitor greps for {needle!r}, which never appears in {argv}")


def test_no_bot_is_watched_that_nothing_can_start():
    """The mirror of the above — a stale entry alerts forever about a bot that does not
    exist, which is the other way to get the channel muted."""
    started = {k for k, _ in _coordinator_sequence()}
    assert set(monitor.BOTS) <= started, (
        f"watched but never launched: {set(monitor.BOTS) - started}")


# ── starting a bot must not take the alert channel down with it ─────────────────
def _coordinator_telegram_fns(proc_stdout, spawns):
    """Load the launcher's REAL telegram functions without importing the module.

    Same constraint as `_coordinator_sequence` above — `startup_coordinator.py` hardcodes
    `Path("C:/trading/algos")` and imports from it at module scope, so it only imports on the
    VPS. Pulling the two function bodies out of the AST and exec'ing them tests the shipped
    code rather than a copy of it that can drift.
    """
    src = (_REPO / "algos" / "bots" / "startup_coordinator.py").read_text()
    tree = ast.parse(src)
    wanted = {"telegram_is_running", "start_telegram_if_needed"}
    fns = [n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name in wanted]
    assert {f.name for f in fns} == wanted, f"missing from the launcher: {wanted - {f.name for f in fns}}"

    ns = {
        "subprocess": SimpleNamespace(
            run=lambda *a, **k: SimpleNamespace(stdout=proc_stdout),
            Popen=lambda *a, **k: spawns.append(a),
            CREATE_NEW_PROCESS_GROUP=0,
        ),
        "PYTHON": "python.exe",
        "ALGOS": Path("C:/trading/algos"),
        "print": lambda *a, **k: None,
    }
    exec(compile(ast.Module(body=fns, type_ignores=[]), "<launcher>", "exec"), ns)
    return ns


def test_starting_a_bot_leaves_a_healthy_telegram_alone():
    """THE regression, and it had been running for weeks reading as a crash.

    This ran `start_telegram.py` unconditionally, and that script force-kills any running
    telegram_bot.py before starting a fresh one. So every Start/Restart from the Bots page —
    and every documented bot restart — killed the alert channel and rebuilt it, after which
    SYS_MONITOR noticed the gap and sent "Telegram Bot Restarted". Nothing was ever wrong with
    it. An alert channel that cries wolf stops being read, and a bot restart is exactly when
    you want to hear from it.
    """
    spawns = []
    ns = _coordinator_telegram_fns("python.exe  C:\\trading\\algos\\notifications\\telegram_bot.py  123",
                                   spawns)
    ns["start_telegram_if_needed"]()
    assert spawns == [], "restarted a Telegram bot that was already running"


def test_a_missing_telegram_is_still_started():
    """The other half — the skip must not turn into never starting it at boot."""
    spawns = []
    ns = _coordinator_telegram_fns("python.exe  C:\\trading\\algos\\live\\runner.py --bot x  456", spawns)
    ns["start_telegram_if_needed"]()
    assert len(spawns) == 1
    assert "start_telegram.py" in str(spawns[0])


def test_an_unreadable_process_list_starts_one_rather_than_assuming_it_is_up():
    """The safe direction is not symmetric here. An extra Telegram is refused by
    telegram_bot.py's own singleton guard; a missing one is silence."""
    spawns = []
    src = (_REPO / "algos" / "bots" / "startup_coordinator.py").read_text()
    tree = ast.parse(src)
    fns = [n for n in tree.body if isinstance(n, ast.FunctionDef)
           and n.name in {"telegram_is_running", "start_telegram_if_needed"}]

    def _boom(*a, **k):
        raise OSError("wmic unavailable")

    ns = {
        "subprocess": SimpleNamespace(run=_boom, Popen=lambda *a, **k: spawns.append(a),
                                      CREATE_NEW_PROCESS_GROUP=0),
        "PYTHON": "python.exe", "ALGOS": Path("C:/trading/algos"),
        "print": lambda *a, **k: None,
    }
    exec(compile(ast.Module(body=fns, type_ignores=[]), "<launcher>", "exec"), ns)
    ns["start_telegram_if_needed"]()
    assert len(spawns) == 1


# ── one bot, one process ────────────────────────────────────────────────────────
def _coordinator_fn(name, proc_stdout, *, raises=False):
    """Exec one launcher function out of its AST, as above."""
    src = (_REPO / "algos" / "bots" / "startup_coordinator.py").read_text()
    fns = [n for n in ast.parse(src).body if isinstance(n, ast.FunctionDef) and n.name == name]
    assert fns, f"{name} missing from startup_coordinator.py"

    def _run(*a, **k):
        if raises:
            raise OSError("wmic unavailable")
        return SimpleNamespace(stdout=proc_stdout)

    ns = {"subprocess": SimpleNamespace(run=_run), "print": lambda *a, **k: None}
    exec(compile(ast.Module(body=fns, type_ignores=[]), "<launcher>", "exec"), ns)
    return ns[name]


def test_the_launcher_does_not_start_a_bot_that_is_already_running():
    """MEASURED 2026-08-04: `schtasks /run /tn SYS_STARTUP` on a box where the bot was already
    up produced TWO `runner.py --bot mpc_sos_fade_demo` processes four minutes apart, and
    nothing anywhere reported it. They share an account, a magic number and a strategy, so both
    size a full position off the same setup — double the risk from a state neither can see."""
    fn = _coordinator_fn("bot_is_running",
                         "python.exe C:\\trading\\algos\\live\\runner.py --bot mpc_sos_fade_demo 8892")
    assert fn("mpc_sos_fade_demo") is True


def test_a_bot_that_is_genuinely_down_is_started():
    fn = _coordinator_fn("bot_is_running", "python.exe C:\\trading\\algos\\notifications\\telegram_bot.py 12780")
    assert fn("mpc_sos_fade_demo") is False


def test_a_different_bot_running_does_not_block_this_one():
    """Matched on the KEY, not the script. Every live bot is `runner.py`, so matching the script
    name would stop a second, different bot from ever starting."""
    fn = _coordinator_fn("bot_is_running",
                         "python.exe C:\\trading\\algos\\live\\runner.py --bot other_bot_demo 4242")
    assert fn("mpc_sos_fade_demo") is False


def test_an_unreadable_process_list_leaves_the_bot_alone():
    """The safe direction is the OPPOSITE of the Telegram case, and deliberately so: a duplicate
    bot is two positions on one account, while a duplicate Telegram is refused by its own
    singleton guard. `runner.py`'s guard is the backstop if this one is over-cautious."""
    fn = _coordinator_fn("bot_is_running", "", raises=True)
    assert fn("mpc_sos_fade_demo") is True


def test_both_launch_paths_are_guarded():
    """`main()` has TWO launch paths and the single-bot one is the dangerous one — it is what
    the command center's per-bot Start button drives, and pressing Start on a running bot is a
    perfectly reasonable thing to do. It was missed on the first pass of this fix.

    Asserted structurally rather than behaviourally because `main()` cannot be exec'd in
    isolation (it reaches module-scope state and `bot_state`); this at least fails when a third
    launch path is added without a guard.
    """
    src = (_REPO / "algos" / "bots" / "startup_coordinator.py").read_text()
    fn = next(n for n in ast.parse(src).body
              if isinstance(n, ast.FunctionDef) and n.name == "main")
    guards = [n for n in ast.walk(fn)
              if isinstance(n, ast.Call) and getattr(n.func, "id", "") == "bot_is_running"]
    assert len(guards) == 2, (
        f"{len(guards)} launch path(s) check whether the bot is already running — full startup "
        f"and single-bot mode both need it")


def test_the_runner_refuses_to_be_a_second_copy(monkeypatch):
    """The backstop, covering every path the launcher does not own — the command center, this
    watchdog, and a hand-typed command."""
    import subprocess as _sp

    r = LiveRunner.__new__(LiveRunner)
    r.cfg = SimpleNamespace(bot_key="mpc_sos_fade_demo", display_name="Bot")
    r.errors = []
    r.log = SimpleNamespace(error=lambda m: r.errors.append(m),
                            warning=lambda m: None, info=lambda m: None)

    other = str(os.getpid() + 1)
    monkeypatch.setattr(_sp, "run", lambda *a, **k: SimpleNamespace(
        stdout=f"python.exe C:\\trading\\algos\\live\\runner.py --bot mpc_sos_fade_demo  {other}"))
    assert r.already_running() is True
    assert any("already running" in e for e in r.errors)


def test_the_runner_does_not_mistake_itself_for_a_duplicate(monkeypatch):
    """It appears in its own `wmic` output. Comparing PIDs is what stops every bot on the box
    refusing to start."""
    import subprocess as _sp

    r = LiveRunner.__new__(LiveRunner)
    r.cfg = SimpleNamespace(bot_key="mpc_sos_fade_demo", display_name="Bot")
    r.log = SimpleNamespace(error=lambda m: None, warning=lambda m: None, info=lambda m: None)

    monkeypatch.setattr(_sp, "run", lambda *a, **k: SimpleNamespace(
        stdout=f"python.exe C:\\trading\\algos\\live\\runner.py --bot mpc_sos_fade_demo  {os.getpid()}"))
    assert r.already_running() is False


def test_sys_telegram_still_force_restarts():
    """The skip is about COLLATERAL damage only. `SYS_TELEGRAM` exists to recover a bot that is
    alive but wedged, and it is what this watchdog fires — so `start_telegram.py` must keep its
    kill-then-start behaviour, or a hung Telegram can never be recovered automatically."""
    src = (_REPO / "algos" / "notifications" / "start_telegram.py").read_text()
    assert "def kill_existing" in src
    assert "kill_existing()" in src, "SYS_TELEGRAM lost its force-restart"


def test_the_stall_threshold_is_well_clear_of_the_poll_interval():
    """`LOG_STALE_SECS` has to be a large multiple of how often the loop actually turns, or
    one slow broker call becomes a 3am alert."""
    import live_config

    poll = live_config.LiveConfig.__dataclass_fields__["poll_seconds"].default
    assert monitor.LOG_STALE_SECS >= poll * 10


# ── Overall P&L ───────────────────────────────────────────────────────────────
# `total_pnl_pct` was written by `notifications/pnl_tracker.py`, deleted 2026-08-05 having
# carried an empty bot registry since June. Nothing wrote the field after that, while the
# Bots page's "Overall P&L" column and Telegram's /balance BOTH defaulted it to 0.0 — so a
# live account up 5% reported dead flat in two places, and neither could say the number was
# never measured. The runner writes it now, because it is the only process that can.

def test_the_runner_reports_overall_pnl_because_nothing_else_can(monkeypatch):
    r = _runner(monkeypatch)
    st = _StateModule()

    r._heartbeat(st)                                   # first poll anchors the start
    assert st.written["bot"]["starting_balance"] == 2000.0
    assert st.written["bot"]["total_pnl_pct"] == 0.0

    monkeypatch.setitem(sys.modules, "MetaTrader5",
                        SimpleNamespace(account_info=lambda: SimpleNamespace(balance=2100.0)))
    r._heartbeat(st)
    assert st.written["bot"]["total_pnl_pct"] == 5.0
    assert st.written["bot"]["starting_balance"] == 2000.0, \
        "the anchor must be written ONCE — re-anchoring makes every account read flat forever"


def test_an_unreadable_balance_reports_no_pnl_rather_than_flat(monkeypatch):
    """The whole point of the field. A blind terminal returns no balance, and 0.0 there is
    the CLAIM 'flat' — the same fabricated-vs-measured collapse `mt5_link` exists to stop."""
    r = _runner(monkeypatch)
    st = _StateModule()
    r._heartbeat(st, link_up=False, balance=None)

    assert st.written["bot"]["total_pnl_pct"] is None
    assert "starting_balance" not in st.written["bot"], \
        "a None balance must never anchor the account at zero"
