"""The identical-rerun cache (`services/run_result_cache.py`).

What is locked: a run can only be served from the cache when EVERY input matches — spec, bars,
conversion rates and code — and anything it cannot fingerprint or cannot store exactly is a miss.
A wrong hit is the failure that matters here: it hands back another run's answer and looks normal.

Proven by mutation, 2026-09-27: dropping the source digest from `key()` turns
`test_a_code_edit_misses` red; dropping the frame digest turns `test_one_changed_bar_misses` red;
removing the type check in `_same()` turns `test_a_result_that_would_come_back_different_is_not_stored`
red.
Storing a cache hit's own timing into the cache turns `test_a_hit_finishes_the_job_with_the_stored_results`
red.
"""

import numpy as np
import pandas as pd
import pytest
from services import python_runner
from services import run_result_cache as rc


@pytest.fixture
def tree(tmp_path, monkeypatch):
    """A throwaway repo tree and cache dir, so the test never reads or writes the real ones."""
    root = tmp_path / "repo"
    (root / "backtest").mkdir(parents=True)
    (root / "backtest" / "fills.py").write_text("SPREAD = 1\n")
    (root / "engines").mkdir()
    (root / "strategies" / "python").mkdir(parents=True)
    monkeypatch.setattr(rc, "_MONOREPO", root)
    monkeypatch.setattr(rc, "_CACHE_DIR", tmp_path / "run_cache")
    return root


def _bars(n=5, bump=0.0):
    idx = pd.date_range("2025-01-01", periods=n, freq="15min", name="time")
    close = np.linspace(2600.0, 2610.0, n)
    close[-1] += bump
    return pd.DataFrame(
        {"open": close, "high": close + 1, "low": close - 1, "close": close}, index=idx
    )


SPEC = {"job_id": "a", "strategy_class": "SosFadeStrategy", "params": {"exec_risk_pct": 5}}


def test_the_same_inputs_give_the_same_key_whatever_the_job_id(tree):
    assert rc.key(SPEC, [_bars()]) == rc.key({**SPEC, "job_id": "b"}, [_bars()])


def test_a_changed_setting_misses(tree):
    other = {**SPEC, "params": {"exec_risk_pct": 6}}
    assert rc.key(SPEC, [_bars()]) != rc.key(other, [_bars()])


def test_one_changed_bar_misses(tree):
    assert rc.key(SPEC, [_bars()]) != rc.key(SPEC, [_bars(bump=0.01)])


def test_a_code_edit_misses(tree):
    before = rc.key(SPEC, [_bars()])
    (tree / "backtest" / "fills.py").write_text("SPREAD = 2\n")
    assert rc.key(SPEC, [_bars()]) != before


def test_an_unreadable_rate_provider_refuses_rather_than_guessing(tree):
    assert rc.key(SPEC, [_bars()], rate=lambda t: 1.0) is None


def test_stored_results_come_back_exactly(tree):
    k = rc.key(SPEC, [_bars()])
    results = {"kpis": {"sharpe": float("nan"), "trades": 3}, "engine_trades": [{"r": 1.5}]}
    rc.write(k, results)
    got = rc.read(k)
    assert rc._same(got, results)


def test_a_result_that_would_come_back_different_is_not_stored(tree):
    k = rc.key(SPEC, [_bars()])
    rc.write(k, {"engine_trades": [(1, 2)]})  # a tuple would come back as a list
    assert rc.read(k) is None


def test_a_corrupt_file_is_a_miss_not_an_error(tree):
    k = rc.key(SPEC, [_bars()])
    rc._CACHE_DIR.mkdir(parents=True)
    (rc._CACHE_DIR / f"{k}.json").write_text("{half a fi")
    assert rc.read(k) is None


def test_a_hit_finishes_the_job_with_the_stored_results(tree):
    k = rc.key(SPEC, [_bars()])
    results = {"engine_trades": [{"r": 1.0}, {"r": -1.0}], "kpis": {}}
    rc.write(k, results)
    python_runner._JOBS["cache_hit_test"] = {"job_id": "cache_hit_test", "status": "running"}
    try:
        clock = python_runner._RunClock()
        assert python_runner._serve_cached("cache_hit_test", k, clock) is True
        job = python_runner._JOBS["cache_hit_test"]
        assert job["status"] == "complete"
        served = dict(job["results"])
        # The hit carries ITS OWN timing, marked as served from the cache...
        assert served.pop("replay_timing")["served_from_cache"] is True
        assert rc._same(served, results)
        # ...and the stored payload never picks one up, so the next hit cannot inherit it.
        assert "replay_timing" not in rc.read(k)
        assert python_runner._serve_cached("cache_hit_test", None, clock) is False
    finally:
        python_runner._JOBS.pop("cache_hit_test", None)


def test_the_run_clock_separates_computing_from_waiting():
    """A starved run shows a CPU share well under 1; a busy one near 1. Sleeping is waiting."""
    import time

    clock = python_runner._RunClock()
    time.sleep(0.6)
    stamp = clock.stamp(served_from_cache=False)
    assert stamp["wall_seconds"] >= 0.6
    assert stamp["cpu_share"] is not None and stamp["cpu_share"] < 0.5
    assert stamp["cpu_count"] and stamp["served_from_cache"] is False
