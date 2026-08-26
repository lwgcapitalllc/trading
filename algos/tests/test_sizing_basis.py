"""The balance a strategy sizes against is not always the balance the broker reports.

🔴 **2026-08-25/26.** A broker request that timed out was re-sent five times, five copies of one
order filled, and the account gained **$3,344.80 it had not earned**. The four extra trades were
marked in the record as not-strategy-performance the same night — and the very next trade still
went out at **0.53 lots where the risk percentage called for 0.40**, because the balance they left
behind is what everything sizes off.

**Labelling a windfall in the record does not stop it compounding into the size of every trade
that follows.** That is the whole reason this exists.

⚠ **One seam.** Three places in the live path read the balance — startup capital, the flat-moment
equity re-anchor, and the account-level risk cap — and all three must read ONE number, or the
strategy sizes against one figure while the cap measures another. That is the shape of 2026-08-07,
where the units conversion existed in no single place and was wrong by 221x with every artefact
reading as correct.

Mutations watched RED are named per test.
"""

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "shared"))

from sizing_basis import describe, sizing_basis  # noqa: E402


def test_no_adjustment_is_the_broker_balance_exactly():
    """The default has to be inert. Every live result this repo has measured was taken with no
    adjustment, and one appearing from nowhere would move a bot with no measurement behind it."""
    assert sizing_basis(13_364.92, 0.0) == 13_364.92
    assert sizing_basis(13_364.92, None) == 13_364.92


def test_the_windfall_is_excluded():
    """The real numbers from the incident."""
    assert sizing_basis(13_364.92, -3_344.80) == pytest.approx(10_020.12)


def test_it_is_ADDED_so_an_exclusion_is_written_negative():
    """Addition is unambiguous arithmetic. An 'amount to exclude' invites a sign error, and a sign
    error here makes every position BIGGER rather than smaller."""
    assert sizing_basis(10_000.0, -1_000.0) == 9_000.0
    assert sizing_basis(10_000.0, 1_000.0) == 11_000.0


def test_an_unreadable_balance_stays_unreadable():
    """Rule 1. "The terminal could not be asked" must never become a number - every caller
    already treats None as "cannot size".

    MUTATION: return `adjustment` when `raw_balance is None` and this fails, with the bot sizing
    off an adjustment as though it were a balance.
    """
    assert sizing_basis(None, -3_344.80) is None
    assert sizing_basis(None, 0.0) is None


def test_an_adjustment_that_leaves_nothing_REFUSES_and_never_clamps():
    """A bot that cannot afford its own strategy must refuse, exactly as `order_sizing` refuses an
    order below the broker minimum rather than rounding it up. A floor would be a size nobody
    chose.

    MUTATION: `return max(adjusted, 1.0)` and this fails - the bot trades a made-up basis.
    """
    assert sizing_basis(1_000.0, -1_000.0) is None
    assert sizing_basis(1_000.0, -1_500.0) is None
    assert sizing_basis(1_000.0, -999.99) == pytest.approx(0.01)


def test_the_ordinary_case_says_NOTHING():
    """A line on every poll is noise nobody reads, and this runs on every poll."""
    assert describe(13_364.92, 0.0) == ""
    assert describe(13_364.92, None) == ""


def test_an_adjusted_basis_is_ANNOUNCED_with_both_numbers():
    """An adjusted basis that is not in the log is indistinguishable from a broker balance, and
    whoever reconciles the bot's sizing against the account statement finds a gap with nothing
    anywhere to explain it."""
    note = describe(13_364.92, -3_344.80)
    assert "10,020.12" in note, "the basis it will actually size against is missing"
    assert "13,364.92" in note, "the broker's own figure is missing"
    assert "3,344.80" in note, "the adjustment is missing"


def test_a_refusal_says_so_rather_than_reporting_a_number():
    note = describe(1_000.0, -1_000.0)
    assert "REFUSING" in note
    assert "clamped" in note.lower()


# ── the cap and the sizing must read ONE number ──────────────────────────────
#
# 🔴 The first pass of these tests did not cover this, and the mutation proved it: making the
# account-level risk cap ignore the adjustment left the whole suite green. **A cap measured
# against the broker's balance while the strategy sizes against an adjusted one is a cap that is
# quietly looser than it says**, and the difference only shows up in a month nobody is checking.
# The "one seam" property was claimed in three docstrings and asserted nowhere.

sys.path.insert(0, str(Path(__file__).resolve().parent))

from test_live_bridge import (  # noqa: E402
    _bridge,
    _FakeExecution,
    install_mt5_stub,
)


@pytest.fixture
def _stub(monkeypatch):
    """The stub reports a balance of 2,000."""
    install_mt5_stub(monkeypatch)


def test_the_account_cap_measures_against_the_ADJUSTED_balance(_stub):
    """MUTATION: return the raw balance from `_account_balance` and this fails - the cap would
    allow 10% of 2,000 while the strategy sizes off 1,500."""
    b, _, _, _ = _bridge(_FakeExecution(), account_risk_cap_pct=10.0)
    b._sizing_basis_adjustment = -500.0
    assert b._account_balance() == pytest.approx(1_500.0)


def test_no_adjustment_leaves_the_cap_reading_the_broker_figure(_stub):
    b, _, _, _ = _bridge(_FakeExecution(), account_risk_cap_pct=10.0)
    assert b._account_balance() == pytest.approx(2_000.0)


def test_an_adjustment_that_empties_the_account_makes_the_cap_UNREADABLE(_stub):
    """Not zero. A zero balance would refuse every order forever with a misleading reason; None
    is the value `plan_order` already understands as "cannot check"."""
    b, _, _, _ = _bridge(_FakeExecution(), account_risk_cap_pct=10.0)
    b._sizing_basis_adjustment = -2_000.0
    assert b._account_balance() is None
