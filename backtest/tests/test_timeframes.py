"""Timeframe parsing and base-timeframe resolution."""

import pytest

from backtest.data.timeframes import resolve_base_tf, to_minutes


@pytest.mark.parametrize(
    "value,expected",
    [
        (15, 15),
        ("15", 15),
        ("15m", 15),
        ("M15", 15),
        ("m15", 15),
        ("1h", 60),
        ("H1", 60),
        ("4h", 240),
        ("1d", 1440),
        ("D1", 1440),
        ("  5m ", 5),
    ],
)
def test_to_minutes_accepts_common_forms(value, expected):
    assert to_minutes(value) == expected


@pytest.mark.parametrize("bad", ["", "abc", "0", 0, -5, "-5m", True, "1w"])
def test_to_minutes_rejects_bad(bad):
    with pytest.raises(ValueError):
        to_minutes(bad)


def test_served_timeframe_is_its_own_base():
    assert resolve_base_tf(15) == ("M15", 15)
    assert resolve_base_tf(5) == ("M5", 5)
    assert resolve_base_tf(240) == ("H4", 240)


def test_unserved_timeframe_resolves_to_largest_divisor():
    # 45m is not served; largest served TF dividing 45 is M15.
    assert resolve_base_tf(45) == ("M15", 15)
    # 120m (2h): largest served divisor is H1 (60).
    assert resolve_base_tf(120) == ("H1", 60)
    # 10m: largest served divisor is M5.
    assert resolve_base_tf(10) == ("M5", 5)


def test_indivisible_timeframe_raises():
    # 7m has no served divisor other than M1... actually M1 divides 7, so base=M1.
    assert resolve_base_tf(7) == ("M1", 1)
    # Something below M1 cannot be built.
    with pytest.raises(ValueError):
        resolve_base_tf(0)
