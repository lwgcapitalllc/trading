"""The quote-to-dollar conversion at the one seam every replay builds through.

`build_strategy` installs a run's conversion rate, and refuses the two ways a non-dollar symbol
could otherwise run silently in dollars: a strategy that cannot take a rate, and a caller that
forgot to give one. Offline — fake strategies, no bars.

RED BY MUTATION (watched, 2026-09-27): with the install and the refusal removed from
`build_strategy`, the four tests that exercise them fail; the four dollar-symbol tests stay green,
as they must — they pin that nothing changes for gold.
"""

from __future__ import annotations

import dataclasses

import pytest

from backtest.data.fx import constant_rate
from backtest.replay import build_strategy


@dataclasses.dataclass
class _Cfg:
    symbol: str = "XAUUSD"
    point_value: float = 1.0


class _Exec:
    def __init__(self):
        self.installed = None

    def set_rate_provider(self, fn):
        self.installed = fn


class _Convertible:
    def __init__(self, config, initial_capital=10_000.0, account=None, leg="strat"):
        self.config = config
        self.account = account
        self.execution = _Exec()


class _NoSeam:
    """A strategy written before the conversion existed: nowhere to install a rate."""

    def __init__(self, config, initial_capital=10_000.0, account=None, leg="strat"):
        self.config = config
        self.execution = object()


def test_the_rate_is_installed_through_the_execution_layer():
    rate = lambda t: 0.0064  # noqa: E731
    s = build_strategy(
        _Convertible, _Cfg("GBPJPY.p", 0.0064), initial_capital=1.0, rate_provider=rate
    )
    assert s.execution.installed is rate


def test_a_strategy_that_cannot_take_a_rate_REFUSES_rather_than_pricing_yen_as_dollars():
    with pytest.raises(TypeError) as exc:
        build_strategy(
            _NoSeam, _Cfg("GBPJPY.p"), initial_capital=1.0, rate_provider=lambda t: 0.0064
        )
    assert "set_rate_provider" in str(exc.value)


def test_a_yen_symbol_with_NO_conversion_REFUSES():
    """The caller that forgot is exactly the caller that would otherwise run silently wrong."""
    with pytest.raises(ValueError) as exc:
        build_strategy(_Convertible, _Cfg("GBPJPY.p", 0.0064), initial_capital=1.0)
    assert "USDJPY.p" in str(exc.value)


def test_the_configured_snapshot_is_allowed_when_it_is_SAID():
    s = build_strategy(
        _Convertible,
        _Cfg("GBPJPY.p", 0.0064),
        initial_capital=1.0,
        rate_provider=constant_rate(0.0064),
    )
    assert s.execution.installed(0) == 0.0064


@pytest.mark.parametrize("symbol", ["XAUUSD", "XAUUSD.p", "GBPUSD.p"])
def test_a_dollar_symbol_builds_exactly_as_before_with_nothing_installed(symbol):
    s = build_strategy(_Convertible, _Cfg(symbol), initial_capital=1.0)
    assert s.execution.installed is None
    # A strategy with no seam at all still builds on a dollar symbol — nothing asks it to convert.
    build_strategy(_NoSeam, _Cfg(symbol), initial_capital=1.0)


def test_a_non_pair_name_keeps_its_configured_constant_at_build():
    """An index or future predates this rule. The LAB path refuses those in rate_provider_for."""
    s = build_strategy(_Convertible, _Cfg("US30"), initial_capital=1.0)
    assert s.execution.installed is None


# ── the lot ceiling counts THIS instrument's lots (2026-09-27) ────────────────
# RED BY MUTATION (watched): with `_contract_size` answering the account default, the yen tests
# see 100 units a lot — a 100-lot ceiling of 10,000 units, 0.1 of a real currency lot.


class _Profile:
    def __init__(self, contract_size):
        self.contract_size = contract_size


class _Costed(_Convertible):
    def __init__(
        self, config, initial_capital=10_000.0, cost_profile=None, account=None, leg="strat"
    ):
        super().__init__(config, initial_capital, account, leg)


def test_a_currency_pair_with_no_ceiling_stated_still_counts_a_lot_as_100000_units():
    s = build_strategy(
        _Convertible,
        _Cfg("GBPJPY.p", 0.0064),
        initial_capital=1.0,
        rate_provider=constant_rate(0.0064),
    )
    assert s.account.contract_size == 100_000.0
    assert s.account.max_lots == 100.0


def test_a_stated_ceiling_counts_the_instruments_lots_too():
    s = build_strategy(_Convertible, _Cfg("GBPUSD.p"), initial_capital=1.0, max_lots=50.0)
    assert s.account.contract_size == 100_000.0
    assert s.account.max_lots == 50.0


def test_the_cost_profiles_measured_lot_size_wins():
    s = build_strategy(
        _Costed,
        _Cfg("GBPJPY.p", 0.0064),
        initial_capital=1.0,
        cost_profile=_Profile(100_000.0),
        rate_provider=constant_rate(0.0064),
    )
    assert s.account.contract_size == 100_000.0


def test_gold_with_no_ceiling_stated_builds_NO_account_exactly_as_before():
    """The strategy keeps building its own, which is what every stored gold run was made on."""
    s = build_strategy(_Convertible, _Cfg("XAUUSD"), initial_capital=1.0)
    assert s.account is None
    s = build_strategy(_Convertible, _Cfg("XAUUSD.p"), initial_capital=1.0, max_lots=100.0)
    assert s.account.contract_size == 100.0
