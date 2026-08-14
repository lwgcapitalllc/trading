"""Shared-account stack runner tests — the leg adapter, the refusals, and the control.

Offline and fake-driven. The real bots are exercised by `tools/stack_run.py`; what is pinned
here is everything that fails QUIETLY: a leg that silently gets its own uncapped balance, two
legs overwriting each other's reservation, and the solo control not actually being solo.
"""

from __future__ import annotations

import sys
from dataclasses import dataclass
from pathlib import Path

import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from backtest.portfolio.legs import StrategyLeg, build_leg
from backtest.portfolio.runner import LegSpec, contention_summary, run_stack
from backtest.replay import build_strategy


# ── fakes ────────────────────────────────────────────────────────────────────────────
@dataclass
class _Trade:
    r: float


class _FakeExecution:
    def __init__(self, account, leg, entry_bar):
        self._account = account
        self._leg = leg
        self._entry_bar = entry_bar
        self.trades: list = []
        self.bar_ms = 0
        self.is_flat = True
        self.granted = None
        self.balance_at_entry = None  # what this leg would have SIZED against

    def step(self, bar_index: int) -> None:
        if bar_index == self._entry_bar and self.is_flat:
            # desired risk = qty(100) x dist(entry 100 - stop 90) x pv(1) = $1,000
            self.balance_at_entry = self._account.balance
            self.granted = self._account.request_fill(self._leg, 1, 100.0, 90.0, 100.0, 1.0)
            if self.granted > 0.0:
                self.is_flat = False
        elif bar_index == self._entry_bar + 2 and not self.is_flat:
            self._account.on_close(self._leg, 500.0)  # +$500 onto the shared balance
            self.is_flat = True
            self.trades.append(_Trade(r=1.0))


class _FakeStrategy:
    """The smallest thing `build_strategy` and `StrategyLeg` will accept."""

    def __init__(self, config=None, initial_capital=0.0, account=None, leg="strat"):
        self.config = config
        self.execution = _FakeExecution(account, leg, entry_bar=config["entry_bar"])

    @staticmethod
    def engine_config():
        return None

    def step(self, bar_state) -> None:
        self.execution.step(bar_state)


class _NoAccountStrategy:
    def __init__(self, config=None, initial_capital=0.0):
        self.config = config


class _CountingStack:
    """Stands in for EngineStack — passes the bar's index straight to the strategy."""

    def __init__(self, _cfg=None):
        pass

    def step(self, bar):
        return bar.index


@dataclass
class _Bar:
    index: int
    timestamp_ms: int


def _leg(name, account, entry_bar, n_bars=10, offset_ms=0):
    strategy = _FakeStrategy(config={"entry_bar": entry_bar}, account=account, leg=name)
    leg = StrategyLeg.__new__(StrategyLeg)  # bypass the EngineStack build
    leg.name = name
    leg.strategy = strategy
    leg._df = None
    leg._stack = _CountingStack()
    leg._bars = [_Bar(i, offset_ms + i * 900_000) for i in range(n_bars)]
    leg.bars = lambda: iter(leg._bars)  # type: ignore[method-assign]
    return leg


# ── build_strategy refuses a strategy that cannot take the account ────────────────────
def test_a_strategy_that_cannot_take_the_account_is_refused_not_given_a_solo_one():
    """The quiet failure this guards: without the refusal the leg falls back to its own
    SoloAccount, which has an INFINITE budget — so the run reports a capped shared portfolio
    while that leg sized off the whole balance and contended with nobody."""
    with pytest.raises(TypeError) as e:
        build_strategy(_NoAccountStrategy, {}, initial_capital=1000.0, account=object())
    assert "does not accept `account`" in str(e.value)
    assert "uncapped" in str(e.value)


def test_no_account_and_no_costs_constructs_exactly_as_before():
    built = build_strategy(_NoAccountStrategy, {"k": 1}, initial_capital=1000.0)
    assert isinstance(built, _NoAccountStrategy)


def test_the_leg_name_reaches_the_strategy_as_its_account_key():
    """`leg` is the account's key for this leg's open position. If it did not travel, both
    legs would be keyed 'strat' and the second fill would overwrite the first's reservation."""
    from backtest.portfolio.account import SoloAccount

    acct = SoloAccount(balance=1000.0)
    built = build_strategy(
        _FakeStrategy, {"entry_bar": 0}, initial_capital=1000.0, account=acct, leg="bleg"
    )
    assert built.execution._leg == "bleg"


# ── the runner's own refusals ─────────────────────────────────────────────────────────
def test_two_legs_may_not_share_a_name():
    spec = LegSpec("same", _FakeStrategy, {"entry_bar": 0}, pd.DataFrame())
    with pytest.raises(ValueError) as e:
        run_stack([spec, spec], balance=1000.0, risk_cap_pct=0.1)
    assert "share a name" in str(e.value)
    assert "under-counts" in str(e.value)


def test_a_zero_risk_cap_is_refused():
    spec = LegSpec("a", _FakeStrategy, {"entry_bar": 0}, pd.DataFrame())
    with pytest.raises(ValueError) as e:
        run_stack([spec], balance=1000.0, risk_cap_pct=0.0)
    assert "cap of zero" in str(e.value)


def test_a_leg_needing_a_second_bar_stream_is_refused_not_replayed_primary_only():
    """`exec_secondary` needs `run_dual`; a leg is one frame. Replaying it single-stream
    returns a primary-only book that is then compared against controls that have re-entries."""

    @dataclass
    class _Cfg:
        exec_secondary: bool = True

    from backtest.portfolio.account import SoloAccount

    with pytest.raises(ValueError) as e:
        build_leg(
            "a",
            _FakeStrategy,
            _Cfg(),
            pd.DataFrame(),
            account=SoloAccount(balance=1.0),
            initial_capital=1.0,
        )
    assert "exec_secondary" in str(e.value)
    assert "primary-only" in str(e.value)


# ── the shared account genuinely shares ───────────────────────────────────────────────
def test_the_legs_size_off_ONE_balance_that_both_of_them_move():
    """The whole point of the shared view, and the half a risk cap does not give you. Leg A
    closes +$500 on bar 4; leg B enters on bar 6 and reads 10,500 — the money leg A made.
    Solo, each leg compounds a private ledger and never sees the other's result at all."""
    from backtest.portfolio.account import PortfolioAccount
    from backtest.portfolio.simulator import simulate

    acct = PortfolioAccount(balance=10_000.0, risk_cap_pct=1.0)
    a = _leg("a", acct, entry_bar=2)
    b = _leg("b", acct, entry_bar=6)
    simulate([a, b], acct)

    assert a.strategy.execution.balance_at_entry == 10_000.0
    assert b.strategy.execution.balance_at_entry == 10_500.0
    assert acct.balance == 11_000.0  # both legs booked onto ONE balance
    assert a.strategy.execution.granted == 100.0
    assert b.strategy.execution.granted == 100.0  # full size — the cap never bound


def test_the_cap_shrinks_the_second_leg_when_the_first_is_still_holding():
    """Both legs want $1,000 of risk and the cap allows $1,500 of a $10,000 balance. The
    second one in gets the remaining $500 — half its size — and the shrink is logged."""
    from backtest.portfolio.account import PortfolioAccount
    from backtest.portfolio.simulator import simulate

    acct = PortfolioAccount(balance=10_000.0, risk_cap_pct=0.15)
    a = _leg("a", acct, entry_bar=2)
    b = _leg("b", acct, entry_bar=3)  # a is still open (it closes on bar 4)
    simulate([a, b], acct)

    assert a.strategy.execution.granted == 100.0
    assert b.strategy.execution.granted == 50.0
    assert [r["leg"] for r in acct.contention] == ["b"]
    assert acct.contention[0]["blocked"] is False
    assert acct.contention[0]["granted_risk"] == 500.0


def test_a_leg_with_no_room_at_all_is_BLOCKED_and_takes_no_trade():
    from backtest.portfolio.account import PortfolioAccount
    from backtest.portfolio.simulator import simulate

    acct = PortfolioAccount(balance=10_000.0, risk_cap_pct=0.10)  # exactly one leg's worth
    a = _leg("a", acct, entry_bar=2)
    b = _leg("b", acct, entry_bar=3)
    simulate([a, b], acct)

    assert b.strategy.execution.granted == 0.0
    assert b.trades == []
    assert acct.contention[0]["blocked"] is True


def test_contention_summary_counts_shrinks_and_blocks_separately():
    from backtest.portfolio.runner import StackRun

    run = StackRun(opening_balance=1.0, risk_cap_pct=0.1, entry_floor_pct=0.0, closing_balance=1.0)
    run.contention = [
        {"leg": "a", "blocked": True, "desired_risk": 100.0, "granted_risk": 0.0},
        {"leg": "a", "blocked": False, "desired_risk": 100.0, "granted_risk": 40.0},
        {"leg": "b", "blocked": False, "desired_risk": 50.0, "granted_risk": 10.0},
    ]
    assert contention_summary(run) == {
        "a": {"shrunk": 1, "blocked": 1, "risk_refused": 160.0},
        "b": {"shrunk": 1, "blocked": 0, "risk_refused": 40.0},
    }


# ── the contention log reports contention, not float noise ────────────────────────────
def test_a_grant_one_ULP_short_of_the_desired_risk_is_not_a_shrink():
    """MEASURED: before this rule a 6.5-year two-leg run logged **11 contention events totalling
    $0.00 of refused risk**, and afterwards ZERO — every one was float noise. `granted =
    min(desired, cap - reserved)`, and the leg derives its qty by DIVIDING by the stop distance
    while the account re-MULTIPLIES by it, so the two sides of an entry that exactly fills the
    cap disagree in the last bit. Downstream that marks trades as shrunk that were granted in
    full. Tested at the seam rather than by synthesising a balance, because which arithmetic
    happens to round is not the rule — the rule is that one ULP is not contention."""
    import math

    from backtest.portfolio.account import PortfolioAccount

    desired = 1234.5678
    assert PortfolioAccount._is_shrunk(desired, math.nextafter(desired, 0.0)) is False


def test_a_real_shrink_is_still_logged():
    """The other half — the tolerance must not swallow a genuine refusal. It is RELATIVE and
    1e-9, so a thousandth of a percent of the size is still contention."""
    from backtest.portfolio.account import PortfolioAccount

    desired = 1234.5678
    assert PortfolioAccount._is_shrunk(desired, desired * 0.9999999) is True
    assert PortfolioAccount._is_shrunk(desired, desired * 0.5) is True


def test_a_real_shrink_is_logged_end_to_end():
    from backtest.portfolio.account import PortfolioAccount

    acct = PortfolioAccount(balance=10_000.0, risk_cap_pct=0.10)
    acct.request_fill("a", 1, 100.0, 99.0, 999.0, 1.0)  # takes $999 of the $1,000 cap
    granted = acct.request_fill("b", 1, 100.0, 99.0, 100.0, 1.0)  # wants $100, $1 is left
    assert granted == pytest.approx(1.0)
    assert [(r["leg"], r["blocked"]) for r in acct.contention] == [("b", False)]


# ── Cancel (2026-08-09) ───────────────────────────────────────────────────────


def _stub_build_leg(monkeypatch, n_bars=4_000, built=None):
    """Point `run_stack` at the scripted leg the rest of this file uses.

    The real `build_leg` constructs an `EngineStack` from a strategy's engine config, which needs
    a real strategy and a real bar frame — neither of which says anything about the control flow
    under test here. What IS under test is what `run_stack` does with a cancelled simulation, so
    the leg is stubbed and `simulate` is the real one.
    """
    from backtest.portfolio import runner as runner_mod

    def _fake(name, strategy_cls, config, df, *, account, initial_capital, cost_profile=None):
        if built is not None:
            built.append(name)
        return _leg(name, account, entry_bar=1, n_bars=n_bars)

    monkeypatch.setattr(runner_mod, "build_leg", _fake)


def test_a_cancelled_shared_run_skips_the_solo_CONTROLS(monkeypatch):
    """⚠ This is the load-bearing half of the cancel path.

    A control's whole job is to be comparable to the shared book. A control replayed over the
    FULL history, beside a shared book that stopped a year in, is not a control — it is two
    different experiments in one table, and the screen-vs-shared delta would report the missing
    year as the cap's doing.
    """
    built: list = []
    _stub_build_leg(monkeypatch, built=built)
    specs = [
        LegSpec("a", _FakeStrategy, {"entry_bar": 1}, pd.DataFrame()),
        LegSpec("b", _FakeStrategy, {"entry_bar": 1}, pd.DataFrame()),
    ]
    calls = {"n": 0}

    def _cancel():
        calls["n"] += 1
        return calls["n"] > 1  # clear on the first poll, cancelled on the second

    run = run_stack(specs, balance=10_000.0, risk_cap_pct=1.0, should_cancel=_cancel)
    assert run.cancelled is True
    assert run.solo_per_leg == {} and run.solo_closing == {}
    # ⚠ The two assertions above are NOT enough on their own and this one is why. Removing the
    # skip leaves them BOTH TRUE: each solo replay polls `should_cancel` on its own first tick,
    # gets True, and bails before recording anything — so the run does the extra work and looks
    # identical from the outside. Counting the legs BUILT is what distinguishes "the controls
    # were skipped" from "the controls ran and threw their results away".
    assert built == ["a", "b"], "the solo controls were replayed after a cancel"


def test_an_uncancelled_run_still_produces_a_control_per_leg(monkeypatch):
    """The direction that would go unnoticed if the skip were made unconditional — a run with no
    controls reports a shared book nothing can be compared against."""
    _stub_build_leg(monkeypatch, n_bars=10)
    specs = [
        LegSpec("a", _FakeStrategy, {"entry_bar": 1}, pd.DataFrame()),
        LegSpec("b", _FakeStrategy, {"entry_bar": 1}, pd.DataFrame()),
    ]
    run = run_stack(specs, balance=10_000.0, risk_cap_pct=1.0, should_cancel=lambda: False)
    assert run.cancelled is False
    assert set(run.solo_per_leg) == {"a", "b"}


def test_progress_names_the_PHASE_so_a_reader_can_tell_control_from_book(monkeypatch):
    """`1 + len(legs)` full replays is minutes of work on a real history, and "bar 8,704 of
    23,712" three times over says nothing about how far through the run is. The phase is what
    turns the tick index into progress."""
    _stub_build_leg(monkeypatch, n_bars=10)
    specs = [
        LegSpec("a", _FakeStrategy, {"entry_bar": 1}, pd.DataFrame()),
        LegSpec("b", _FakeStrategy, {"entry_bar": 1}, pd.DataFrame()),
    ]
    phases: list = []
    run_stack(
        specs, balance=10_000.0, risk_cap_pct=1.0, progress=lambda phase, i: phases.append(phase)
    )
    assert phases[0] == "shared"
    assert set(phases) == {"shared", "solo:a", "solo:b"}
