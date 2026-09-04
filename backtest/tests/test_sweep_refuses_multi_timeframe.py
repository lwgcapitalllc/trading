"""A sweep replays ONE frame, so it must REFUSE a config needing a second timeframe.

`exec_secondary` (the sos_fade 1m re-entry) defaults ON as of 2026-08-07, and `run_sweep` has
no 1m stream to give it. Replaying it single-stream is the dangerous option, not the safe one: the
combos come back primary-only and get ranked against a baseline that HAS re-entries, which is this
repo's most-repeated defect — a comparison whose two sides were measured on different books.

Same call `reprice.py` makes about `bid_ask_fills`: a thing this shape cannot price is refused and
named, never approximated.
"""

import pytest

from backtest.optimizer import Combo, _replay_one


class _Cfg:
    """Only the field the guard reads — the guard must fire before anything is constructed."""

    def __init__(self, secondary: bool) -> None:
        self.exec_secondary = secondary


class _NeverBuilt:
    def __init__(self, *a, **k):  # pragma: no cover - reaching this IS the failure
        raise AssertionError("the sweep built a strategy for a config it cannot replay")


def test_a_sweep_refuses_a_config_that_needs_a_second_timeframe():
    with pytest.raises(ValueError, match="exec_secondary"):
        _replay_one(_NeverBuilt, None, 10_000.0, Combo(params={}, config=_Cfg(True)))


def test_the_refusal_names_the_way_out():
    """A refusal a reader cannot act on gets worked around rather than fixed."""
    with pytest.raises(ValueError) as err:
        _replay_one(_NeverBuilt, None, 10_000.0, Combo(params={}, config=_Cfg(True)))
    assert "exec_secondary=False" in str(err.value)


def test_a_config_without_the_field_is_not_refused():
    """Every other strategy in this repo lacks the field entirely and must sweep unchanged.

    This one PASSES against the pre-guard code and is kept deliberately: it pins the half of the
    rule that was already right, and a guard reaching for a missing attribute would break every
    NT8/MT5/other-python sweep at once.
    """
    with pytest.raises(AssertionError, match="built a strategy"):
        _replay_one(_NeverBuilt, None, 10_000.0, Combo(params={}, config=object()))


def test_the_refusal_fires_BEFORE_a_pool_is_spawned():
    """`run_sweep` checks combo 0 up front, not one combo into a live process pool.

    Both checks stay: `_replay_one` is the seam every combo goes through (serial and pooled), and
    this one keeps the failure legible — a grid that dies after starting N workers reads as a
    crash rather than as a refusal. Checking combo 0 alone is sound because a sweep varies params,
    never the strategy.
    """
    from backtest.optimizer import run_sweep

    def _never(*a, **k):  # pragma: no cover - reaching this IS the failure
        raise AssertionError("a worker pool was built for a config the sweep cannot replay")

    combos = [Combo(params={"a": i}, config=_Cfg(True)) for i in range(64)]
    with pytest.raises(ValueError, match="exec_secondary"):
        run_sweep(
            module_path="strategies.python.sos_fade",
            df=None,
            combos=combos,
            max_workers=8,
            progress=_never,
        )
