"""Tests for the shared-account leg.

RULE 12 — every test here was watched RED before it was watched green, and the mutation that
reddens it is named in its own docstring.

RULE 13 — the price fixture is the same 2,400 REAL XAUUSD M15 bars the engine tests use. A leg
driven by the canonical structure engine cannot be exercised on a synthetic path: the engine emits
nothing at all on one, and every assertion below would then pass on an empty list.

🔴 **The load-bearing test in this file is `test_the_stepped_leg_finds_the_same_setups_as_the_batch_rule`.**
Everything else checks a property of the wiring; that one checks that the second driver did not
become a second RULE. Without it the leg could quietly drift from the engine every measured number
in this package came from, and nothing would fail.
"""

from __future__ import annotations

import sys
from dataclasses import dataclass
from pathlib import Path

import pandas as pd
import pytest

_ROOT = Path(__file__).resolve().parents[3]
for _p in (str(_ROOT), str(_ROOT / "engines"), str(_ROOT / "strategies" / "python")):
    if _p not in sys.path:
        sys.path.insert(0, _p)

from backtest.portfolio.account import PortfolioAccount, SoloAccount  # noqa: E402
from backtest.replay.loop import iter_bars  # noqa: E402
from backtest.replay.stack import EngineStack  # noqa: E402
from loss_recovery import LossRecoveryEngine, RecoveryConfig  # noqa: E402
from loss_recovery.leg import RecoveryLeg, RecoveryLegConfig  # noqa: E402

_FIXTURE = Path(__file__).with_name("fixture_xauusd_m15.csv")
_BULL_CHOCH_BARS = (436, 588, 783, 2084)
_BEAR_CHOCH_BARS = (134, 527, 628, 1065)
POINT_VALUE = 100.0
RISK_PCT = 10.0


@dataclass
class FakeLoss:
    """Satisfies the LossEvent protocol and nothing more."""

    dir: int
    exit_index: int
    r: float
    entry_price: float = 0.0


def real_bars():
    df = pd.read_csv(_FIXTURE, index_col=0, parse_dates=True)
    df.index = pd.DatetimeIndex(df.index)
    return df


def _drive(leg, df, feed):
    """Step the leg over `df`, appending each loss to its watched list on the right bar.

    `feed` is {bar_index: FakeLoss} — the loss is appended BEFORE that bar is stepped, which is
    where a real source leg would have appended it (its trade closed on the previous bar).
    """
    stack = EngineStack(leg.stack_config())
    src: list = []
    leg.watch(src)
    leg.set_horizon(len(df.index) - 1, 96.0)
    for bar in iter_bars(df):
        if bar.index in feed:
            src.append(feed[bar.index])
        leg.step(stack.step(bar))
    return leg.execution.trades


def _leg(account=None, capital=100_000.0, **rule_kw):
    rule = RecoveryConfig(enabled=True, **rule_kw)
    return RecoveryLeg(
        RecoveryLegConfig(rule=rule, point_value=POINT_VALUE, unit_risk_pct=RISK_PCT),
        initial_capital=capital,
        account=account if account is not None else SoloAccount(balance=capital),
        leg="recovery",
    )


# ── the one that matters ─────────────────────────────────────────────────────────────────
def test_the_stepped_leg_finds_the_same_setups_as_the_batch_rule():
    """RED by mutation: change the leg's entry from the NEXT bar's open to the SIGNAL bar's close
    (`_fill_pending`'s `pend["signal_index"] >= i` guard).

    This is the whole justification for a second driver existing. The batch engine pre-computes
    every structure event and matches; the leg answers the same questions one bar at a time. If
    the two disagree about WHICH setups exist, the leg is a second rule wearing this one's name,
    and every measured number in this package would silently stop applying to it.

    Sizes and P&L legitimately differ — the leg sizes off a live account and the batch off a
    passed-in balance — so this compares the SETUPS: direction, entry bar, entry price, the 1R
    stop distance, and how each ended.

    🔴 **The batch list is filtered through the leg's ONE-POSITION rule before comparing, and the
    filter is the test's second assertion rather than a convenience.** The shared account keys one
    position per leg; the batch rule resolves every loss independently and can hold two at once.
    That is a real, documented difference, and it showed up here the first time this ran — the leg
    skipped the setup at bar 589 because its bar-437 trade was still open. Hiding it by choosing
    non-overlapping losses would have made the test agree by construction; asserting the filter
    means the day the leg drops a trade for any OTHER reason, this goes red.
    """
    df = real_bars()
    losses = [FakeLoss(-1, b - 30, -1.0) for b in _BULL_CHOCH_BARS]
    batch = LossRecoveryEngine(RecoveryConfig(enabled=True)).run(df, losses)
    assert batch, "the fixture produced no batch recovery trades; the test cannot say anything"

    kept, busy_until = [], -1
    for b in sorted(batch, key=lambda x: x.entry_index):
        if b.entry_index <= busy_until:
            continue
        kept.append(b)
        busy_until = b.exit_index
    assert len(kept) < len(batch), (
        "no overlap in the fixture, so the one-position rule is never exercised and this test "
        "would pass on a leg that ignored it"
    )

    leg = _leg()
    got = _drive(leg, df, {loss.exit_index: loss for loss in losses})

    assert [(t.dir, t.entry_index, round(t.entry_price, 5), round(t.stop_distance, 5),
             t.exit_index, t.exit_reason) for t in got] == \
           [(b.direction, b.entry_index, round(b.entry_price, 5), round(b.risk, 5),
             b.exit_index, b.exit_reason) for b in kept]
    assert len(leg.execution.skipped_concurrent) == len(batch) - len(kept)


def test_a_loss_the_leg_has_not_seen_yet_cannot_arm_it():
    """RED by mutation: hand the leg the whole loss list up front in `_drive` instead of appending
    it bar by bar — i.e. delete the `watch`-a-growing-list contract.

    A recovery arms when a primary trade CLOSES. Reading the finished list is look-ahead: it would
    let the leg take a counter-trade off a loss that had not happened yet, which is the one thing
    a shared-account replay exists to rule out.
    """
    df = real_bars()
    # The same loss, declared far too late to arm any of the fixture's known CHoCHs.
    late = FakeLoss(-1, len(df) - 2, -1.0)
    assert _drive(_leg(), df, {late.exit_index: late}) == []


# ── the account seam ─────────────────────────────────────────────────────────────────────
def test_the_leg_sizes_off_the_shared_balance_not_a_private_one():
    """RED by mutation: size off `initial_capital` instead of `self._account.balance`.

    This is the entire point of the exercise. If the leg sizes off a private opening balance, it
    is a separate account wearing a shared account's name — which is exactly the defect that made
    the lab's own recovery toggle answer the wrong question.

    ⚠ **It asserts EVERY trade, and the first draft asserted only the first — which was vacuous.**
    Before any trade has closed the running balance still equals the opening capital, so the two
    sizings agree exactly there and the mutation sailed through. The property only becomes
    observable once the balance has MOVED, which is the whole claim being made.
    """
    df = real_bars()
    losses = [FakeLoss(-1, b - 30, -1.0) for b in _BULL_CHOCH_BARS]
    capital = 100_000.0
    got = _drive(_leg(capital=capital), df, {loss.exit_index: loss for loss in losses})
    assert len(got) > 1, "need more than one trade or the balance never moves"

    rate = (RISK_PCT / 100.0) * RecoveryConfig().risk_fraction
    running = capital
    moved = False
    for t in sorted(got, key=lambda x: x.entry_index):
        assert t.risk_usd == pytest.approx(running * rate, rel=1e-9)
        running += t.pnl_usd
        moved = moved or abs(running - capital) > 1e-6
    assert moved, "the balance never moved, so this test cannot tell the two sizings apart"


def test_an_entry_the_budget_refuses_is_not_taken_and_is_recorded():
    """RED by mutation: ignore the granted qty and open the position anyway in `_fill_pending`.

    A leg that books a trade the account refused reports a capped run's trades at an uncapped
    run's size — the risk cap claimed on screen and enforced nowhere.
    """
    df = real_bars()
    losses = [FakeLoss(-1, b - 30, -1.0) for b in _BULL_CHOCH_BARS]
    # A cap of essentially zero: there is never room for anything.
    account = PortfolioAccount(balance=100_000.0, risk_cap_pct=1e-9)
    leg = _leg(account=account)
    got = _drive(leg, df, {loss.exit_index: loss for loss in losses})
    assert got == []
    assert leg.execution.blocked, "refused every entry and recorded none of them"


def test_a_closed_trade_releases_its_reservation():
    """RED by mutation: drop the `close_position` call in `_book`.

    A leg that books P&L without releasing its reservation holds budget it is not using for the
    rest of the run, and every later entry — its own and the other leg's — is shrunk against risk
    nobody is carrying. Nothing errors; the account just quietly stops granting.
    """
    df = real_bars()
    losses = [FakeLoss(-1, b - 30, -1.0) for b in _BULL_CHOCH_BARS]
    account = PortfolioAccount(balance=100_000.0, risk_cap_pct=0.10)
    leg = _leg(account=account)
    got = _drive(leg, df, {loss.exit_index: loss for loss in losses})
    assert got, "no trades; the test cannot say anything"
    assert not account.has_position("recovery")
    assert account.reserved() == pytest.approx(0.0)


def test_a_second_setup_while_holding_is_skipped_and_COUNTED():
    """RED by mutation: delete the `skipped_concurrent` record (keep the skip).

    The shared account keys one position per leg, and the batch rule has no such limit — it
    resolves each loss independently. That difference is small (3 overlapping pairs in 53 trades
    on the real book) but it is a difference, and a silently smaller trade count is exactly how a
    rule change disguises itself as a market outcome.
    """
    df = real_bars()
    # Two losses in the same direction close together, so the second arms while the first's
    # recovery is still open.
    losses = [FakeLoss(-1, 400, -1.0), FakeLoss(-1, 437, -1.0)]
    leg = _leg()
    _drive(leg, df, {loss.exit_index: loss for loss in losses})
    assert leg.execution.skipped_concurrent, "no skip recorded on overlapping setups"


# ── refusals ─────────────────────────────────────────────────────────────────────────────
def test_a_config_needing_an_ATR_is_refused_rather_than_approximated():
    """RED by mutation: fall back to the structural stop instead of raising.

    The engine stack carries no ATR and this module will not compute a private one. Falling back
    would report a rule nobody ran, on a stop up to 7x the size — the same shape as the engine's
    own `_stop_for` refusal, which this mirrors deliberately.
    """
    for kw in ({"stop_mode": "atr"}, {"stop_mode": "signal_bar"}, {"trail_atr_mult": 2.0}):
        with pytest.raises(ValueError, match="ATR"):
            _leg(**kw)


def test_a_stop_on_the_wrong_side_of_the_fill_is_refused_not_clamped():
    """RED by mutation: take `abs(entry - stop)` and open anyway.

    Rule 17. A stop past the fill is not a tight trade, it is a broken one, and clamping it
    produces a position the strategy never asked for. The batch driver refuses the same setups —
    if only one of them did, the two books would differ by trades nobody could account for.
    """
    df = real_bars()
    leg = _leg()
    stack = EngineStack(leg.stack_config())
    leg.watch([])
    leg.set_horizon(len(df.index) - 1, 96.0)
    bars = list(iter_bars(df))
    for bar in bars[:10]:
        leg.step(stack.step(bar))
    # A long whose stop sits ABOVE the next bar's open.
    leg._pending = {"want": 1, "stop": float(bars[10].open) + 5.0, "signal_index": 9}
    leg._fill_pending(10, bars[10])
    assert leg.execution.open is None
    assert leg.execution.trades == []
