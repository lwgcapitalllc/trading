"""A sweep GIVEN a second frame runs the two-stream strategy instead of refusing it.

WHY THIS EXISTS. `exec_secondary` has defaulted ON since 2026-08-07, and until 2026-09-20 the
sweep refused every config that had it — which made every parameter of the repo's main strategy
untunable in batch. The refusal was right; the missing half was a way to SATISFY it. Measured on
2026-09-20: a 225-combo exit-ladder grid is ~11 hours one run at a time and well under an hour
across cores, and that gap is the whole reason this path exists.

🔴 THE DANGEROUS OUTCOME IS NOT A REFUSAL, IT IS A SILENT SINGLE-STREAM REPLAY — combos come back
primary-only and get ranked against a baseline that has re-entries. So the tests that matter here
are the ones pinning that `run_dual` is what actually ran, and that the refusal still fires on
every road that does not reach it.

WATCHED RED against HEAD: the two-stream tests failed with the old ValueError (the guard refused
whatever it was handed), and the run_dual-not-double-finalized test failed the same way.
"""

import pytest

from backtest.optimizer import Combo, _replay_one, run_sweep


class _Cfg:
    def __init__(self, secondary=True):
        self.exec_secondary = secondary


class _Dual:
    """A strategy double that records WHICH driver ran. It answers `run_dual` and nothing else,
    so a single-stream replay cannot silently succeed against it — which is the point: a double
    more capable than the thing under test hides the defect being looked for."""

    built = []

    def __init__(self, *a, **k):
        self.calls = []
        self.execution = type("E", (), {"trades": [], "bar_ms": None})()
        _Dual.built.append(self)

    def run_dual(self, df, fast_df, warmup=0):
        self.calls.append(("run_dual", id(df), id(fast_df), warmup))
        return self

    def finalize(self, df):  # pragma: no cover - calling this IS the failure
        raise AssertionError("run_dual finalizes itself; the sweep must not finalize again")


@pytest.fixture(autouse=True)
def _reset():
    _Dual.built = []


def _replay(strategy_cls, fast, cfg=None, monkeypatch=None):
    return _replay_one(
        strategy_cls, "DF", 10_000.0, Combo(params={}, config=cfg or _Cfg()), None, None, fast
    )


def test_a_second_frame_makes_the_sweep_RUN_it_instead_of_refusing(monkeypatch):
    monkeypatch.setattr("backtest.replay.build_strategy", lambda cls, cfg, **k: cls())
    monkeypatch.setattr("backtest.output.build_kpis", lambda trades, initial_capital: {"n": 0})
    row = _replay(_Dual, "FAST")
    assert _Dual.built[0].calls[0][0] == "run_dual"
    assert row["params"] == {}


def test_it_hands_run_dual_BOTH_frames_the_right_way_round(monkeypatch):
    """The fast frame second. Swapped, the primary would replay on the fill clock and every
    structure read would be a different strategy — with no error anywhere."""
    monkeypatch.setattr("backtest.replay.build_strategy", lambda cls, cfg, **k: cls())
    monkeypatch.setattr("backtest.output.build_kpis", lambda trades, initial_capital: {"n": 0})
    _replay(_Dual, "FAST")
    _, slow_id, fast_id, warmup = _Dual.built[0].calls[0]
    assert slow_id == id("DF") and fast_id == id("FAST")
    assert warmup == 0  # matches the single-stream path, which steps the whole frame


def test_it_does_NOT_finalize_again_because_run_dual_already_did(monkeypatch):
    """MUTATION: call `finalize` after `run_dual` and the double raises. Double-finalizing books
    the end-of-book recovery trades twice, which reads as a better combo and not as an error."""
    monkeypatch.setattr("backtest.replay.build_strategy", lambda cls, cfg, **k: cls())
    monkeypatch.setattr("backtest.output.build_kpis", lambda trades, initial_capital: {"n": 0})
    _replay(_Dual, "FAST")  # _Dual.finalize raises if reached


def test_a_fast_frame_with_NO_run_dual_is_still_refused(monkeypatch):
    """The frame is not the permission — the driver is. A strategy that cannot step a second
    stream must not be handed one and replayed single-stream anyway."""

    class _NoDual:
        def __init__(self, *a, **k):  # pragma: no cover
            raise AssertionError("built a strategy that cannot replay this config")

    with pytest.raises(ValueError, match="run_dual"):
        _replay(_NoDual, "FAST")


def test_WITHOUT_a_fast_frame_the_old_refusal_is_untouched():
    class _NeverBuilt:
        def __init__(self, *a, **k):  # pragma: no cover
            raise AssertionError("built a strategy for a config it cannot replay")

    with pytest.raises(ValueError, match="exec_secondary"):
        _replay_one(_NeverBuilt, None, 10_000.0, Combo(params={}, config=_Cfg(True)))


def test_run_sweep_does_not_refuse_UP_FRONT_once_a_fast_frame_is_supplied():
    """The parent's early check is about the frame only — it has a module path, not a class, so
    the run_dual question is the worker's. Handing it a fast frame must get PAST that gate."""
    combos = [Combo(params={"a": i}, config=_Cfg(True)) for i in range(4)]
    with pytest.raises(ValueError, match="run_dual"):
        run_sweep(
            module_path="backtest.tests.test_sweep_second_stream",
            df="DF",
            combos=combos,
            max_workers=1,
            fast_df="FAST",
        )


LAB_STRATEGY = {"strategy": type("_NoDualPkg", (), {}), "config": lambda **k: _Cfg()}
