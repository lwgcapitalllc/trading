"""The local sweep (A4).

Offline: a fake strategy package is built in a tmp dir, so nothing here loads engines, touches the
broker, or needs the tunnel. What's locked is the sweep's CONTRACT — one row per combo, in order,
fresh state per combo, cancellation, and the parallel path agreeing with the serial one.
"""

import sys
import textwrap

import pandas as pd
import pytest

from backtest.optimizer import Combo, default_workers, run_sweep

# A strategy package the sweep can import for real. It must live on disk (the parallel path spawns
# worker processes that re-import it by name), and it must satisfy exactly the surface the sweep
# uses: LAB_STRATEGY, a config dataclass, .execution.trades, .engine_config(), .step().
_FAKE_PKG = textwrap.dedent('''
    import dataclasses

    @dataclasses.dataclass
    class FakeConfig:
        multiplier: float = 1.0
        offset: float = 0.0
        point_value: float = 1.0

    class _Trade:
        def __init__(self, pnl):
            self.pnl_usd = pnl
            self.r = pnl / 100.0
            self.entry_ms = 0
            self.exit_ms = 60_000
            self.dir = 1
            self.entry_price = 1.0
            self.exit_price = 2.0
            self.qty = 1.0
            self.risk_usd = 100.0
            self.exit_reason = "L-TP1"
            self.stop_distance = 1.0
            self.costs_usd = 0.0
            self.entry_index = 0
            self.exit_index = 1

    class _Exec:
        def __init__(self):
            self.trades = []
            self.bar_ms = 0

    class FakeStrategy:
        """One trade per bar, worth multiplier*10 + offset — so KPIs are a pure function of params."""
        def __init__(self, config, initial_capital=0.0):
            self.config = config
            self.execution = _Exec()
        def engine_config(self):
            return None
        def step(self, bar_state):
            self.execution.trades.append(
                _Trade(self.config.multiplier * 10.0 + self.config.offset))

    LAB_STRATEGY = {
        "name": "Fake",
        "config": FakeConfig,
        "strategy": FakeStrategy,
    }
''')


@pytest.fixture
def fake_pkg(tmp_path, monkeypatch):
    """Create `fakestrat/` on disk, importable as a top-level package, and yield its module path."""
    pkg = tmp_path / "fakestrat"
    pkg.mkdir()
    (pkg / "__init__.py").write_text(_FAKE_PKG)
    monkeypatch.syspath_prepend(str(tmp_path))
    for mod in [m for m in sys.modules if m.startswith("fakestrat")]:
        del sys.modules[mod]
    yield "fakestrat"


@pytest.fixture(autouse=True)
def stub_engines(monkeypatch):
    """The sweep drives EngineStack/iter_bars; the fake strategy ignores both. Stub them so the
    test stays about the sweep and not about the engine stack."""
    import backtest.replay as replay

    class _Bar:
        def __init__(self, i):
            self.index = i

    class _Stack:
        def __init__(self, _cfg):
            pass

        def step(self, bar):
            return bar

    monkeypatch.setattr(replay, "EngineStack", _Stack, raising=False)
    monkeypatch.setattr(
        replay, "iter_bars", lambda df: [_Bar(i) for i in range(len(df))], raising=False
    )


@pytest.fixture
def df():
    idx = pd.date_range("2026-01-01", periods=5, freq="15min")
    return pd.DataFrame({"open": 1.0, "high": 2.0, "low": 0.5, "close": 1.5}, index=idx)


def _combos(pkg_mod, values):
    from importlib import import_module

    cfg_cls = import_module(pkg_mod).LAB_STRATEGY["config"]
    return [Combo(params={"multiplier": v}, config=cfg_cls(multiplier=v)) for v in values]


def _serial(pkg, df, combos, **kw):
    return run_sweep(module_path=pkg, df=df, combos=combos, max_workers=1, **kw)


# ── the contract ──────────────────────────────────────────────────────────────


def test_one_row_per_combo_in_combo_order(fake_pkg, df):
    rows = _serial(fake_pkg, df, _combos(fake_pkg, [1.0, 2.0, 3.0]))
    assert [r["params"]["multiplier"] for r in rows] == [1.0, 2.0, 3.0]


def test_kpis_track_the_params(fake_pkg, df):
    """5 bars => 5 trades; multiplier 2 => 20/trade => net 100. If a combo's config were ignored,
    every row would carry the same net — the failure mode a sweep must never have."""
    rows = _serial(fake_pkg, df, _combos(fake_pkg, [1.0, 2.0]))
    assert rows[0]["kpis"]["net_pnl"] == 50.0
    assert rows[1]["kpis"]["net_pnl"] == 100.0
    assert rows[0]["kpis"]["trade_count"] == 5


def test_each_combo_gets_fresh_state(fake_pkg, df):
    """Trades must not accumulate across combos — a leak would make results depend on grid order."""
    rows = _serial(fake_pkg, df, _combos(fake_pkg, [1.0, 1.0, 1.0]))
    assert [r["kpis"]["trade_count"] for r in rows] == [5, 5, 5]


def test_empty_grid_returns_nothing(fake_pkg, df):
    assert run_sweep(module_path=fake_pkg, df=df, combos=[]) == []


def test_cancellation_stops_early_and_keeps_finished_rows(fake_pkg, df):
    """A cancelled sweep returns the partial grid rather than raising — the combos that finished
    are real results, and the caller already knows it asked to stop."""
    seen = {"n": 0}

    def cancel_after_two():
        seen["n"] += 1
        return seen["n"] > 2

    rows = _serial(
        fake_pkg, df, _combos(fake_pkg, [1.0, 2.0, 3.0, 4.0]), should_cancel=cancel_after_two
    )
    assert len(rows) == 2


def test_progress_reports_done_and_total(fake_pkg, df):
    calls = []
    _serial(
        fake_pkg, df, _combos(fake_pkg, [1.0, 2.0, 3.0]), progress=lambda d, t: calls.append((d, t))
    )
    assert calls == [(1, 3), (2, 3), (3, 3)]


# ── the parallel path ─────────────────────────────────────────────────────────


def test_parallel_matches_serial(fake_pkg, df, tmp_path):
    """The whole point of workers is that they change only the wall clock. Spawned workers re-import
    the package by name, so this also proves the sys.path handoff into a fresh interpreter works."""
    combos = _combos(fake_pkg, [1.0, 2.0, 3.0, 4.0])
    serial = _serial(fake_pkg, df, combos)
    parallel = run_sweep(
        module_path=fake_pkg, df=df, combos=combos, max_workers=2, monorepo_root=str(tmp_path)
    )
    assert [r["params"] for r in parallel] == [r["params"] for r in serial]
    assert [r["kpis"]["net_pnl"] for r in parallel] == [r["kpis"]["net_pnl"] for r in serial]


# ── worker sizing ─────────────────────────────────────────────────────────────


def test_never_more_workers_than_combos(monkeypatch):
    monkeypatch.setattr("backtest.optimizer.os.cpu_count", lambda: 16)
    assert default_workers(3) == 3


def test_leaves_a_core_free_on_a_multicore_box(monkeypatch):
    """This runs inside the backend serving the UI that displays its own progress."""
    monkeypatch.setattr("backtest.optimizer.os.cpu_count", lambda: 8)
    assert default_workers(100) == 7


def test_always_at_least_one_worker(monkeypatch):
    monkeypatch.setattr("backtest.optimizer.os.cpu_count", lambda: 1)
    assert default_workers(100) == 1
    monkeypatch.setattr("backtest.optimizer.os.cpu_count", lambda: None)
    assert default_workers(100) == 1


# ── the `extract` hook (2026-09-07) ───────────────────────────────────────────
#
# It exists so a caller needing something `build_kpis` does not carry — an out-of-sample split
# needs each trade's own entry time, and the KPI dict reports totals — can have it WITHOUT
# reproducing `_replay_one`. That matters because `_replay_one` is not `strategy.run()`: it sets
# `bar_ms` off the frame and calls `finalize()` afterwards, and a second bar loop that forgets
# either is wrong in silence.
#
# The extractors are module-level because they are PICKLED to the worker processes.

# A package whose end-of-book pass adds a trade — the only way to tell "extract sees the finished
# strategy" apart from "extract sees the strategy mid-flight". The distinction is the whole reason
# `_replay_one` calls `finalize` at all.
_ANCHOR = "    def step(self, bar_state):"
_FINALIZING_PKG = _FAKE_PKG.replace(
    _ANCHOR,
    "    def finalize(self, df):\n        self.execution.trades.append(_Trade(999.0))\n" + _ANCHOR,
)
# A fixture that quietly fails to patch is a fixture describing a strategy with no end-of-book
# pass — and the test built on it then passes against the very bug it names. Refuse instead.
assert "def finalize" in _FINALIZING_PKG, "the finalizing fixture did not patch — check _ANCHOR"


def _count_trades(strategy):
    return len(strategy.execution.trades)


def _first_pnl(strategy):
    return strategy.execution.trades[0].pnl_usd


@pytest.fixture
def finalizing_pkg(tmp_path, monkeypatch):
    pkg = tmp_path / "finalstrat"
    pkg.mkdir()
    (pkg / "__init__.py").write_text(_FINALIZING_PKG)
    monkeypatch.syspath_prepend(str(tmp_path))
    for mod in [m for m in sys.modules if m.startswith("finalstrat")]:
        del sys.modules[mod]
    yield "finalstrat"


def test_extract_rides_on_each_row_and_tracks_that_combo(fake_pkg, df):
    """Every row carries its OWN extraction, not the last combo's."""
    rows = _serial(fake_pkg, df, _combos(fake_pkg, [1.0, 2.0, 3.0]), extract=_first_pnl)
    assert [r["extra"] for r in rows] == [10.0, 20.0, 30.0]


def test_no_extractor_means_the_key_is_ABSENT_not_None(fake_pkg, df):
    """`extra: None` could not be told apart from an extractor that genuinely found nothing —
    the "no" versus "cannot ask" distinction root rule 1 is about. Absence is the answer."""
    rows = _serial(fake_pkg, df, _combos(fake_pkg, [1.0]))
    assert "extra" not in rows[0]


def test_extract_sees_the_FINISHED_strategy_not_the_mid_flight_one(finalizing_pkg, df):
    """5 bars = 5 trades, plus the one the end-of-book pass adds. An extractor called before
    `finalize()` would report 5 and rank every combo on a book missing that pass's trades."""
    rows = _serial(finalizing_pkg, df, _combos(finalizing_pkg, [1.0]), extract=_count_trades)
    assert rows[0]["extra"] == len(df) + 1


def test_extract_survives_the_process_pool(fake_pkg, df, tmp_path):
    """The parallel path pickles the extractor to the workers and the result back. A hook that
    only works serially is a hook that silently stops working the moment a grid is big enough."""
    combos = _combos(fake_pkg, [1.0, 2.0, 3.0])
    parallel = run_sweep(
        module_path=fake_pkg,
        df=df,
        combos=combos,
        max_workers=2,
        monorepo_root=str(tmp_path),
        extract=_first_pnl,
    )
    assert [r["extra"] for r in parallel] == [10.0, 20.0, 30.0]
