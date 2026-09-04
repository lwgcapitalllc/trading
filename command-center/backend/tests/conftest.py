"""
Shared fixtures for the lab test suite.

DB isolation: every test gets a fresh SQLite DB via monkeypatching lab_db.DB_PATH
to a temp path before any lab_db function runs.

VPS isolation: the client fixture stubs the runner_dispatch calls a test is meant
to exercise, and `_no_live_vps` (autouse, below) makes any call it MISSED fail
loudly instead of quietly reaching the live box. It covers BOTH channels the
backend can reach the VPS on — HTTP to the two agents, and `ssh` shelled out of
`routers/bots.py` and `services/agent_supervisor.py`.

The agent supervisor is disabled process-wide (see below) — the `client` fixture
runs the real startup hook, and a supervisor loose in a test run would restart
the SSH tunnel and fire scheduled tasks on the live VPS.
"""

import os
import subprocess
import time
from unittest.mock import AsyncMock, patch

import pytest

# Set before `main` is ever imported: the startup hook reads it, and every
# endpoint test triggers that hook via TestClient. A module-scope env write is
# the only thing that lands early enough — a fixture runs too late for a module
# imported at collection time.
os.environ["CC_DISABLE_SUPERVISOR"] = "1"


# ── DB isolation ──────────────────────────────────────────────────────────────


@pytest.fixture
def fresh_db(tmp_path, monkeypatch):
    """
    Patches lab_db.DB_PATH to a temp file and calls init_db().
    All fixtures that depend on this share the same temp DB within one test.
    """
    from services import lab_db

    db = tmp_path / "lab.db"
    monkeypatch.setattr(lab_db, "DB_PATH", db)
    lab_db.init_db()
    return db


# ── VPS isolation, enforced ───────────────────────────────────────────────────


class LiveVpsCall(BaseException):
    """A test reached for the live VPS. Deliberately NOT an `Exception`.

    ⚠ Every probe on this path catches `Exception` and reports a failure as "the box is
    down" — `agent_supervisor.vps_reachable`, `_agent_ok`, `schtasks_run` and six bare
    `except Exception: pass` blocks in `routers/system.py::_build_health`. An
    `AssertionError` raised inside any of them is SWALLOWED, so the guard would sit inert
    in exactly the code whose job is to tolerate a dead box — green suite, no warning, and
    the un-stubbed call still made on the way in.

    Deriving from `BaseException` is what makes it uncatchable by that code while pytest
    still reports it as a failure. Same rule the runtime side of this repo keeps meeting:
    the check has to be able to fail where the failure actually happens.
    """


_SSH_PROGRAMS = {"ssh", "scp", "sftp"}


def _targets_the_vps(cmd) -> bool:
    """Is this argv about to reach the VPS?

    Two independent tests, because one alone misses half the surface:

    - the PROGRAM is an ssh client — covers `_ssh`, `restart_tunnel`, `schtasks_run`
      and anything written later, whatever host it names;
    - the SSH ALIAS appears anywhere in the argv — covers `pkill -f "ssh -N.*forexvps"`,
      whose program is not ssh at all and which would otherwise kill the developer's
      real tunnel from inside a unit test.

    Everything else runs for real. `git` in `routers/bots.py::_git_commit_push` and the
    smart-money stage scripts are ordinary local subprocesses and must stay that way —
    a blanket ban on `subprocess` would be easier to write and would test nothing about
    the VPS.
    """
    argv = [str(a) for a in cmd] if isinstance(cmd, (list, tuple)) else str(cmd).split()
    if not argv:
        return False
    if os.path.basename(argv[0]) in _SSH_PROGRAMS:
        return True
    import config as cfg

    alias = getattr(cfg, "SSH_ALIAS", "")
    return bool(alias) and any(alias in a for a in argv)


@pytest.fixture(autouse=True)
def _no_live_vps(request):
    """Any un-stubbed call to the live VPS — over HTTP or over SSH — RAISES here.

    ⚠ **This exists because the `client` fixture's docstring was a claim nobody checked.**
    It said "all outbound VPS calls stubbed" while `list_strategy_files` was not, so
    `GET /strategy-files/sync-status` really did reach the NT8 agent over the live SSH
    tunnel — and the test around it PASSED whenever the box happened to be up. That is the
    worst shape for this defect: green on the machine that has the tunnel open, red on a
    fresh clone or a slept laptop, and pointing at the wrong thing either way.

    **HTTP:** both agent clients funnel through `_get`/`_post`, so patching those four is
    the whole surface.

    **SSH:** there is no funnel — `routers/bots.py::_ssh` is one, but
    `services/agent_supervisor.py` shells out three more times on its own, and the next
    module to need the box will shell out again. So the guard sits on `subprocess.run` and
    `subprocess.Popen` themselves and decides per-argv (`_targets_the_vps`), which is the
    only placement a NEW call site cannot walk around. That matters more here than on the
    HTTP side: an un-stubbed HTTP call reads state, while `restart_tunnel` kills the
    developer's ssh process and `schtasks_run` fires a scheduled task on a box that trades
    real money.

    A test that legitimately needs one of these stubs the named function (`bots._ssh`,
    `sup.vps_reachable`) above this fixture, and its patch wins.

    ⚠ Tests marked `integration` are EXEMPT — driving the live VPS is their entire job, and
    they are already interlocked by `pytest.ini`'s `-m "not integration"`.
    """

    def refuse_http(*a, **kw):
        raise LiveVpsCall(
            "A test tried to call the live VPS agent over HTTP. Stub the specific "
            "runner_dispatch / mt5_agent_client function it needs — do not let a unit "
            "test's result depend on whether the SSH tunnel happens to be up."
        )

    if request.node.get_closest_marker("integration"):
        yield
        return

    real_run, real_popen = subprocess.run, subprocess.Popen

    def guard(real, kind):
        def wrapper(cmd, *a, **kw):
            if _targets_the_vps(cmd):
                raise LiveVpsCall(
                    f"A test tried to reach the live VPS over SSH "
                    f"(subprocess.{kind}: {cmd!r}). Stub the function that shells out — "
                    "`bots._ssh`, `agent_supervisor.vps_reachable`, `schtasks_run`, "
                    "`restart_tunnel` — do not let a unit test start a tunnel, fire a "
                    "scheduled task, or kill an ssh process on the machine running it."
                )
            return real(cmd, *a, **kw)

        return wrapper

    with (
        patch("services.runner_dispatch._get", side_effect=refuse_http),
        patch("services.runner_dispatch._post", side_effect=refuse_http),
        patch("services.mt5_agent_client._get", side_effect=refuse_http),
        patch("services.mt5_agent_client._post", side_effect=refuse_http),
        patch("subprocess.run", new=guard(real_run, "run")),
        patch("subprocess.Popen", new=guard(real_popen, "Popen")),
    ):
        yield


@pytest.fixture(autouse=True)
def _no_live_bot_config(request):
    """A test may not WRITE a live bot's instance config. This is `_no_live_vps`'s local twin.

    🔴 **Found on 2026-08-12 by running a mutation, not by reading anything.** Neutering the
    account-move endpoint's password pre-check let `test_moving_a_bot_to_an_account_with_no_stored_password_is_REFUSED`
    fall through to the write, and it moved the REAL `b_leg_demo` off the bench and onto the ECN
    account — in the working tree, on the machine running the suite. Nothing errored; it was caught
    only because `git status` was checked afterwards.

    ⚠ **The point is not that one test. The point is which direction the exposure runs.** The VPS
    interlock covers HTTP and SSH because those are how a test reaches the box — and an instance
    config is a plain file in this repo, so a test reaches a live bot's settings with no network at
    all. `deploy: False` skips the commit and the push, which is exactly the shape somebody writing
    a refusal test reaches for, and it is the shape that leaves the change ON DISK and unnoticed
    until it is committed with something else.

    ⚠ **A test that genuinely exercises the write stubs `_write_instance_config` itself**, and its
    patch wins because it is applied after this fixture. That is deliberate: the guard should cost
    one line to opt out of, so nobody is tempted to delete it.
    """
    if request.node.get_closest_marker("integration"):
        yield
        return

    def refuse(bot_key, data):
        raise LiveVpsCall(
            f"A test tried to write the live instance config for {bot_key!r}. That file decides "
            f"which account, symbol and strategy version a real bot trades. Stub "
            f"`routers.bots._write_instance_config` in the test that needs the write."
        )

    with patch("routers.bots._write_instance_config", side_effect=refuse):
        yield


# ── API client ────────────────────────────────────────────────────────────────


@pytest.fixture
def client(fresh_db):
    """
    FastAPI TestClient with:
    - isolated DB (via fresh_db)
    - all outbound VPS calls stubbed
    - background backtest job mocked (no-op AsyncMock)

    Use this for all endpoint tests. Tests that only need the service layer
    directly can use fresh_db + seeded_run without this fixture.
    """
    from fastapi.testclient import TestClient
    from main import app

    with (
        patch("services.runner_dispatch.start_backtest", return_value={"status": "ok"}),
        patch("services.runner_dispatch.job_log", return_value=""),
        patch("services.runner_dispatch.health", return_value={"status": "ok"}),
        # ⚠ These two were NOT stubbed until 2026-08-05, so `GET /strategy-files/sync-status`
        # really did call the NT8 agent over the live SSH tunnel — `test_sync_status_skips_
        # python_and_still_reports_the_others` passed only while the VPS happened to be up and
        # 502'd otherwise. The docstring above has claimed "all outbound VPS calls stubbed"
        # the whole time, which is what made it invisible: a fixture is a CLAIM about what a
        # test can reach, and nothing was checking it.
        # `[]` is the honest stub — sync-status emits a row per strategy either way, with
        # `file_exists_on_vps` False, so the assertions stay about what the endpoint decides
        # rather than about what happens to be deployed on the box today.
        patch("services.runner_dispatch.list_strategy_files", return_value=[]),
        patch("services.mt5_agent_client.list_strategy_files", return_value=[]),
        patch("routers.backtests.run_backtest_job", new_callable=AsyncMock),
        patch("routers.backtests.read_progress", return_value={"status": "idle", "pct": 0}),
    ):
        with TestClient(app, raise_server_exceptions=True) as c:
            yield c


# ── Seeded data helpers ───────────────────────────────────────────────────────


def _insert_strategy(lab_db):
    lab_db.upsert_strategy(
        {
            "id": "test_strategy",
            "name": "Test Strategy",
            "class_name": "TestStrategy",
            "source_path": "test/TestStrategy.cs",
            "scanned_at": int(time.time()),
            "default_params": {},
            "param_schema": [],
        }
    )
    return "test_strategy"


@pytest.fixture
def seeded_run(fresh_db):
    """
    Seeds a minimal strategy + a completed run with known KPIs.
    net_pnl=4000, max_drawdown=1500, no equity/daily_pnl files.

    Used by evaluator unit tests and reevaluate endpoint tests.
    """
    from services import lab_db

    strategy_id = _insert_strategy(lab_db)
    run_id = "testrun12abc"

    lab_db.insert_run(
        {
            "run_id": run_id,
            "strategy_id": strategy_id,
            "instrument": "MNQ 06-26",
            "params": {},
            "bar_type": "Minute",
            "bar_value": 5,
            "start_date": "2024-01-01",
            "end_date": "2024-12-31",
            "commission_per_side": 0.50,
            "slippage_ticks": 1,
            "status": "running",
            "created_at": int(time.time()),
        }
    )
    lab_db.update_run_complete(
        run_id,
        {
            "net_pnl": 4000.0,
            "max_drawdown": 1500.0,
            "profit_factor": 1.8,
            "win_rate": 0.55,
            "win_count": 80,
            "trade_count": 145,
            "sharpe": 1.2,
            "sortino": 1.5,
            "cagr": 0.22,
            "avg_win": 120.0,
            "avg_loss": -85.0,
            "avg_trade_duration_min": 43.0,
            "worst_day_pnl": -400.0,
            "worst_losing_streak": 5,
        },
        {},
    )
    return run_id
