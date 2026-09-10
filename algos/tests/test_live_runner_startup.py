"""Constructing the runner, and the order it does things in.

**Why this file exists.** Every other test here exercises a PIECE — the bridge, the feed, the
ledger, the version pin — and each of those passed while `LiveRunner(cfg)` itself raised
`ModuleNotFoundError` on the very first line of `__init__`. The bot could not start on any
machine, and the suite was green. Found on the VPS on 2026-07-31, by running it.

So the point of these tests is unglamorous: build the object, and check the two things that
happen before a bot can report anything about itself. Startup order matters more than it looks —
a failure before the logger exists is a failure with no diagnosis, and a failure before
`verify_pin` is a bot that got further than it should have.

No MT5 here. Everything below stops short of `connect()`.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

_REPO = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(_REPO / "algos" / "live"))
import live_config  # noqa: E402
import runner  # noqa: E402


@pytest.fixture(autouse=True)
def _fresh_logger():
    """`logging.getLogger(name)` is process-global, so a logger built in one test keeps handlers
    pointing at that test's tmp_path and the next test silently writes to a stale file. Harmless
    in production (one process runs one bot) but it makes these tests pass alone and fail
    together, which is worse than failing outright."""
    import logging

    yield
    log = logging.getLogger("smoke")
    for h in list(log.handlers):
        h.close()
        log.removeHandler(h)


def _cfg(tmp_path, monkeypatch, **overrides):
    body = {
        "bot_key": "smoke",
        "mt5_path": "C:/MT5/terminal64.exe",
        "account": 1,
        "server": "Demo",
        "symbol": "XAUUSD",
        "magic": 1,
    }
    body.update(overrides)
    (tmp_path / "smoke").mkdir(parents=True, exist_ok=True)
    (tmp_path / "smoke" / "config.json").write_text(json.dumps(body))
    monkeypatch.setattr(live_config, "_INSTANCES", tmp_path)
    return live_config.load("smoke")


def test_the_runner_can_be_constructed(tmp_path, monkeypatch):
    """The test that was missing. `__init__` builds a logger and a ledger — if either import
    path is wrong the bot dies before it can tell anyone why, which is exactly what happened."""
    r = runner.LiveRunner(_cfg(tmp_path, monkeypatch))
    assert r.log is not None
    assert r.ledger is not None
    assert r.dry_run is True  # sending orders is never the default


def test_a_line_the_console_cannot_encode_is_still_written(tmp_path, monkeypatch):
    """The messages here contain arrows and em-dashes. A Windows console is cp1252 and cannot
    encode them, and `logging` responds by DISCARDING the record and printing a
    UnicodeEncodeError where it should have been — which is how the VPS lost its "Warmed N
    bars" line on 2026-07-31. The log is the audit trail, so an unencodable character must cost
    a glyph, never the line."""
    cfg = _cfg(tmp_path, monkeypatch)
    r = runner.LiveRunner(cfg)
    r.log.info("Warmed 5000 bars (2026-05-15 → 2026-07-31) — holding a position")
    for h in r.log.handlers:
        h.flush()

    # One text log per UTC day (`DailyFileHandler`) — the name is not fixed, so read whichever
    # one this run landed in rather than restating today's date here.
    logs = sorted(cfg.instance_dir.glob(f"{cfg.bot_key}-????-??-??.log"))
    assert len(logs) == 1, f"expected one dated log, found {[p.name for p in logs]}"
    written = logs[0].read_text(encoding="utf-8")
    assert "Warmed 5000 bars" in written
    assert "holding a position" in written  # the END of the line survived, not just the start


def test_constructing_twice_does_not_double_every_log_line(tmp_path, monkeypatch):
    """A duplicated handler turns one trade into two ledger-adjacent log entries, which is the
    kind of thing that makes a post-mortem argue with itself."""
    cfg = _cfg(tmp_path, monkeypatch)
    first = runner.LiveRunner(cfg)
    runner.LiveRunner(cfg)
    assert len(first.log.handlers) == 2  # one file, one stdout


def test_logs_land_in_the_bots_own_instance_dir(tmp_path, monkeypatch):
    """One bot, one directory. Two bots sharing a log file is how you lose the answer to
    "why did this trade not work"."""
    cfg = _cfg(tmp_path, monkeypatch)
    runner.LiveRunner(cfg)
    assert cfg.instance_dir.exists()
    assert cfg.instance_dir == tmp_path / "smoke"


def test_dry_run_is_the_default_and_live_must_be_asked_for(tmp_path, monkeypatch):
    cfg = _cfg(tmp_path, monkeypatch)
    assert runner.LiveRunner(cfg).dry_run is True
    assert runner.LiveRunner(cfg, dry_run=False).dry_run is False


def test_the_version_pin_is_checked_before_anything_connects(tmp_path, monkeypatch):
    """`run()` must refuse on a bad pin WITHOUT touching MT5. If connect() ran first, a bot
    running unpromoted code would already be attached to a live account by the time anyone
    found out."""
    cfg = _cfg(tmp_path, monkeypatch, strategy_source_hash="deadbeef" * 4)
    r = runner.LiveRunner(cfg)

    def _boom():
        raise AssertionError("connect() must not be reached when the pin fails")

    monkeypatch.setattr(r, "connect", _boom)
    monkeypatch.setattr(r, "_notify_health", lambda text: None)
    assert r.run() == 2  # 2 = version mismatch, a distinct exit code


def test_a_version_mismatch_is_recorded_and_announced(tmp_path, monkeypatch):
    """Refusing silently would look identical to a crash. It has to say which hash it wanted."""
    cfg = _cfg(tmp_path, monkeypatch, strategy_source_hash="deadbeef" * 4)
    r = runner.LiveRunner(cfg)
    sent = []
    monkeypatch.setattr(r, "connect", lambda: pytest.fail("unreachable"))
    monkeypatch.setattr(r, "_notify_health", sent.append)
    r.run()

    assert sent and "refused to start" in sent[0]
    rows = [
        json.loads(l)
        for f in (cfg.instance_dir / "ledger").glob("*.jsonl")
        for l in f.read_text().splitlines()
    ]
    assert any(row.get("event") == "version_mismatch" for row in rows)


# ── the bench: a bot with no account must not try to trade ────────────────────
#
# Added 2026-08-09. `account: null` is what removing a bot from an account on the Bots page
# writes, so the runner has to make that state mean something rather than fail obscurely on a
# credentials lookup for account `None`.


def test_a_bot_with_no_account_refuses_before_anything_connects(tmp_path, monkeypatch):
    """MUTATION: delete the `cfg.account is None` block from `_run` -> red.

    Checked ahead of the pin and the process guard, because both of those describe a bot that is
    trying to trade. Refusing later would report a version problem or a credentials problem for a
    bot whose actual state is that nobody has assigned it."""
    cfg = _cfg(tmp_path, monkeypatch, account=None)
    r = runner.LiveRunner(cfg)
    monkeypatch.setattr(r, "connect", lambda: pytest.fail("connect() must not be reached"))
    monkeypatch.setattr(r, "_notify_health", lambda text: pytest.fail("no alert for a bench"))
    assert r.run() == 0


def test_being_on_the_bench_is_an_ORDINARY_ending_not_a_fault(tmp_path, monkeypatch):
    """Exit 0 and NO Telegram alert. A benched bot is a deliberate configuration, and the boot
    task plus the watchdog would otherwise raise the same alarm on every attempt for as long as
    it stayed benched — which is how a channel gets muted."""
    cfg = _cfg(tmp_path, monkeypatch, account=None)
    r = runner.LiveRunner(cfg)
    sent = []
    monkeypatch.setattr(r, "connect", lambda: pytest.fail("unreachable"))
    monkeypatch.setattr(r, "_notify_health", sent.append)
    assert r.run() == 0
    assert sent == []

    rows = [
        json.loads(l)
        for f in (cfg.instance_dir / "ledger").glob("*.jsonl")
        for l in f.read_text().splitlines()
    ]
    # It still leaves a trace: "no shutdown record" must keep meaning "killed or crashed", so a
    # deliberate ending has to write one. Both records are the evidence that it ended on purpose.
    assert any(row.get("event") == "not_assigned" for row in rows)
    assert any(
        row.get("event") == "shutdown" and row.get("reason") == "not assigned to an account"
        for row in rows
    )


# ── the startup contract check ───────────────────────────────────────────────────────────────
#
# 🔴 **`verify_live_ready` was described as the startup gate in FOUR docstrings across this
# package and nothing called it** (grepped, 2026-09-09). A seam the bridge reads but the strategy
# does not provide was therefore an exception mid-bar on a live position, or a `getattr` default
# making *never implemented* and *nothing to do* the same answer. These pin the wiring.


class _Ex:
    """A conformant execution — every attribute the contract names, and nothing else."""

    entry_style = "resting"
    _POSITION_FIELDS = ("dir", "qty")

    def __init__(self):
        import live_contract as lc

        for name in lc.EXECUTION_ATTRS:
            if not hasattr(self, name):
                setattr(self, name, lambda *a, **k: None)


class _Strategy:
    def __init__(self):
        import live_contract as lc

        self.execution = _Ex()
        for name in lc.STRATEGY_ATTRS:
            if not hasattr(self, name):
                setattr(self, name, lambda *a, **k: None)


def test_a_conformant_strategy_is_allowed_through(tmp_path, monkeypatch):
    """MUTATION: make the check raise unconditionally. RUN — red.

    The half that keeps the refusal from being a wall: a strategy that provides every seam must
    start, and today BOTH live bots do (measured on the box, 2026-09-09)."""
    r = runner.LiveRunner(_cfg(tmp_path, monkeypatch))
    r._assert_live_ready(_Strategy())  # must not raise


def test_a_strategy_MISSING_a_seam_is_refused_at_STARTUP_not_mid_bar(tmp_path, monkeypatch):
    """MUTATION: log a warning and return instead of raising. RUN — red.

    🔴 This is the whole fix. Without it the bot starts, runs normally until the first setup, and
    then throws inside the bar loop **with a live position open** — the worst moment available.
    A refusal lands in `run()`'s startup handler and is announced as WILL NOT START."""
    import live_contract as lc

    r = runner.LiveRunner(_cfg(tmp_path, monkeypatch))
    strat = _Strategy()
    seam = lc.EXECUTION_ATTRS[0]
    delattr(strat.execution, seam)

    with pytest.raises(RuntimeError) as e:
        r._assert_live_ready(strat)
    assert seam in str(e.value)


def test_the_refusal_names_PROMOTE_because_that_is_the_fix(tmp_path, monkeypatch):
    """MUTATION: drop the remedy from the message. RUN — red.

    `algos/` arrives by `git pull` and a strategy only by `promote.py`, so the overwhelmingly
    likely cause is a box pulled ahead of its promote. A refusal that does not say so sends the
    reader to read the strategy — which is correct, and is not the fix."""
    import live_contract as lc

    r = runner.LiveRunner(_cfg(tmp_path, monkeypatch))
    strat = _Strategy()
    delattr(strat.execution, lc.EXECUTION_ATTRS[0])

    with pytest.raises(RuntimeError) as e:
        r._assert_live_ready(strat)
    msg = str(e.value)
    assert "promote.py" in msg
    assert "smoke" in msg  # the bot key, so the command can be run as printed


def test_the_contract_that_BINDS_is_the_REPOS_own_file(tmp_path, monkeypatch):
    """MUTATION: load it from the bot's snapshot instead. RUN — red.

    🔴 **The repo's contract is the one that has to bind.** Its required-seam list is derived from
    what `algos/live/` actually reads, so it describes the REPO's bridge — and the bridge is what
    the bot runs, since `algos/` arrives by `git pull` while a strategy arrives only by
    `promote.py`. A box pulled ahead of its promote is exactly the gap the check exists for, and
    the frozen contract is structurally blind to it."""
    r = runner.LiveRunner(_cfg(tmp_path, monkeypatch))
    mod = r._repo_live_contract()
    assert Path(mod.__file__) == _REPO / "strategies" / "python" / "live_contract.py"
    assert callable(mod.verify_live_ready)


def test_loading_it_LEAVES_THE_NAME_FREE_so_the_freeze_stays_whole(tmp_path, monkeypatch):
    """MUTATION: register it as `live_contract`, or import it plainly at module scope. RUN — red.

    🔴 **THIS IS THE DEFECT THIS DESIGN EXISTS TO AVOID, AND IT WAS WALKED INTO BEFORE IT WAS
    CAUGHT.** `strategies/python` is on `sys.path` as a ROOT, so that module imports as the BARE
    name `live_contract`. `_bind_code` refuses a leak of the strategy package, `engines` or
    `backtest` **by name** and cannot see a bare name from that tree — MEASURED: with it in
    `sys.modules`, `_bind_code` did not refuse, the module-scope guard did not catch it, and a
    later import from a bound snapshot returned the REPO object.

    **`extreme_leg` inherits two base classes from that module**, so a promoted bot would have run
    repo classes inside a frozen strategy while its banner said *frozen* — the freeze silently
    half-applied, which `_bind_code`'s own docstring calls the worst outcome available."""
    r = runner.LiveRunner(_cfg(tmp_path, monkeypatch))
    monkeypatch.delitem(sys.modules, "live_contract", raising=False)
    monkeypatch.delitem(sys.modules, "_lwg_repo_live_contract", raising=False)

    r._repo_live_contract()
    assert "live_contract" not in sys.modules, (
        "the snapshot's own copy must still be able to claim this name"
    )


def test_no_module_in_algos_live_imports_the_contract_by_its_BARE_NAME():
    """MUTATION: put `from live_contract import verify_live_ready` at the top of `runner.py`.
    RUN — red here AND in the module-scope guard.

    ⚠ Pinned in TWO places on purpose: that guard answers *did anything from a frozen tree reach
    `sys.modules`*, and this answers *does this package name it at all* — which is the thing a
    reader greps for and the thing a well-meaning tidy-up would restore."""
    import ast

    live = _REPO / "algos" / "live"
    for path in sorted(live.glob("*.py")):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom) and node.module == "live_contract":
                raise AssertionError(f"{path.name} imports live_contract by its bare name")
            if isinstance(node, ast.Import):
                for a in node.names:
                    assert a.name != "live_contract", f"{path.name} imports live_contract"


def test_importing_the_contract_early_cannot_trip_the_snapshot_LEAK_GUARD():
    """MUTATION: give `live_contract` an `engines` import. RUN — red.

    🔴 `_bind_code` REFUSES to start any frozen bot if a strategy, `engines` or `backtest` module
    reached `sys.modules` before the snapshot was bound. The contract is imported at module scope,
    i.e. before that — so the day it grows one of those imports, **every promoted bot on the box
    stops starting.** That is a whole fleet, from an import that looks harmless."""
    import ast

    src = (_REPO / "strategies" / "python" / "live_contract.py").read_text(encoding="utf-8")
    banned = {"engines", "backtest"}
    for node in ast.walk(ast.parse(src)):
        if isinstance(node, ast.ImportFrom) and node.module:
            assert node.module.split(".")[0] not in banned, node.module
        if isinstance(node, ast.Import):
            for a in node.names:
                assert a.name.split(".")[0] not in banned, a.name


def test_every_bot_with_an_instance_config_SATISFIES_the_contract_today():
    """MEASURED, and it is the guard that stops this refusal becoming a wall.

    A seam added to `algos/live/` grows `EXECUTION_ATTRS` automatically (it is measured off that
    package), so this goes RED the moment the bridge starts reading something a live strategy
    does not provide — **before** a promote takes it to the box, rather than as a bot that will
    not start. ⚠ Scoped to bots that have an instance config: a lab-only strategy is not required
    to be live-ready, and demanding it would be a claim nobody made."""
    import importlib

    sys.path.insert(0, str(_REPO / "strategies" / "python"))
    sys.path.insert(0, str(_REPO / "engines"))
    import live_contract as lc

    instances = _REPO / "algos" / "markets" / "fx" / "instances"
    checked = 0
    for d in sorted(p for p in instances.iterdir() if p.is_dir()):
        cfgf = d / "config.json"
        if not cfgf.is_file():
            continue
        cfg = json.loads(cfgf.read_text(encoding="utf-8"))
        pkg_name = cfg.get("strategy_package")
        if not pkg_name:
            continue
        lab = importlib.import_module(pkg_name).LAB_STRATEGY
        params = dict(cfg.get("strategy_params") or {})
        params.setdefault("symbol", cfg.get("symbol"))
        strat = lab["strategy"](lab["config"](**params), initial_capital=10_000.0)
        assert lc.verify_live_ready(strat) == [], f"{d.name} would be refused at startup"
        checked += 1
    assert checked >= 2, "this test stopped covering anything"


def _fake_package(monkeypatch, strategy):
    """A minimal strategy package the runner can import, wrapping `strategy`."""
    import types
    from dataclasses import dataclass

    @dataclass
    class _Cfg:
        symbol: str = "XAUUSD"

    mod = types.ModuleType("fake_pkg")
    mod.LAB_STRATEGY = {
        "strategy": lambda cfg, initial_capital: strategy,
        "config": _Cfg,
    }
    mod.LAB_STRATEGY["strategy"].__name__ = "FakeStrategy"
    monkeypatch.setitem(sys.modules, "fake_pkg", mod)
    # Different guards, not the subject here — each has its own tests.
    monkeypatch.setattr(runner, "assert_supported", lambda *a, **k: None)
    monkeypatch.setattr(runner, "assert_hedging_for_scale_in", lambda *a, **k: None)
    return mod


def test_BUILDING_a_strategy_runs_the_contract_check(tmp_path, monkeypatch):
    """MUTATION: delete the `_assert_live_ready` call from `_build_strategy`. RUN — red.

    🔴 **THIS TEST EXISTS BECAUSE THAT MUTATION SURVIVED THE FIRST SIX.** Every other case here
    calls `_assert_live_ready` directly, so all of them stayed green with the check WIRED TO
    NOTHING — which is precisely the defect being fixed, reproduced one level up while I was
    fixing it. **A guard is only as real as its call site**, and a test that drives the guard
    rather than the thing that should invoke it proves the guard works and nothing about whether
    it runs. Rule 7, in a test file written for rule 7.

    So this drives `_build_strategy` itself and asserts the refusal comes out of it."""
    import live_contract as lc

    r = runner.LiveRunner(
        _cfg(
            tmp_path,
            monkeypatch,
            strategy_package="fake_pkg",
            strategy_class="FakeStrategy",
            initial_capital=10_000.0,
        )
    )
    strat = _Strategy()
    delattr(strat.execution, lc.EXECUTION_ATTRS[0])
    _fake_package(monkeypatch, strat)

    with pytest.raises(RuntimeError) as e:
        r._build_strategy()
    assert lc.EXECUTION_ATTRS[0] in str(e.value)


def test_BUILDING_a_conformant_strategy_still_returns_it(tmp_path, monkeypatch):
    """MUTATION: make `_build_strategy` raise whatever the check says. RUN — red.

    The other half, and it is not decoration: a wiring test that only ever asserts a refusal
    passes beautifully against a build path that refuses EVERYTHING — the shape
    `.claude/mcp/check_tradingbox.py` records, where a tool with no working happy path satisfied
    every sad-path case."""
    r = runner.LiveRunner(
        _cfg(
            tmp_path,
            monkeypatch,
            strategy_package="fake_pkg",
            strategy_class="FakeStrategy",
            initial_capital=10_000.0,
        )
    )
    strat = _Strategy()
    _fake_package(monkeypatch, strat)

    built, _ = r._build_strategy()
    assert built is strat
