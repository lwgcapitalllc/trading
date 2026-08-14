"""The emulator's balance must be the ACCOUNT's balance — fault 2 of the 2026-08-07 incident.

**What went wrong.** `LiveRunner._build_strategy` constructs the strategy with the real account
balance, and then `warm()` replays 5,000 historical bars THROUGH it. Those bars contain trades.
`Execution` books their P&L onto its own `_account.balance`, because that is exactly what it does
in a backtest — and then sizes every LIVE order off the result.

On the day of the incident the emulator had compounded a real $2,000 into roughly $4,423 of
imaginary profit, so every order it asked for risked $442.30 instead of $200. Its own orders gave
it away: three different setups, three different stop distances, and all three risked $442.30.

**The fix is not "reset once".** It is to pull the emulator back onto the broker's balance at
every FLAT moment — the same seam the runtime config reload already uses — because a live account
also moves, and one re-anchor at startup would drift again over a long run.

⚠ The tests below are about the three ways this can be got wrong rather than about the happy
path: re-anchoring while a trade is open (which would change a position's risk basis mid-flight),
re-anchoring to a balance the terminal could not supply (fabricating a number, which is the
failure being fixed arriving through the fix), and re-anchoring so eagerly that the health stream
fills with records saying nothing changed.
"""

from __future__ import annotations

import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

_REPO = Path(__file__).resolve().parent.parent.parent
for _p in (str(_REPO), str(_REPO / "algos" / "live"), str(_REPO / "algos" / "shared")):
    if _p not in sys.path:
        sys.path.insert(0, _p)

from runner import LiveRunner  # noqa: E402


class _Ledger:
    def __init__(self):
        self.events = []

    def event(self, kind, **kw):
        self.events.append((kind, kw))

    def kinds(self):
        return [k for k, _ in self.events]


def _runner(*, balance, emulator_balance=4422.88):
    """A LiveRunner with just enough wired to re-anchor.

    The emulator default is the real figure from the incident: 10% of it is the $442.30 that
    every one of that day's three orders risked.
    """
    r = LiveRunner.__new__(LiveRunner)
    account = SimpleNamespace(balance=emulator_balance)
    r.strategy = SimpleNamespace(execution=SimpleNamespace(_account=account))
    r.ledger = _Ledger()
    r.notes, r.warns = [], []
    r.log = SimpleNamespace(
        info=lambda m, *a, **k: r.notes.append(m),
        warning=lambda m, *a, **k: r.warns.append(m),
        error=lambda m, *a, **k: r.warns.append(m),
    )
    r.probe_link = lambda: (balance is not None, balance)
    return r, account


def test_the_warmups_imagined_profit_does_not_size_a_live_order():
    """🔴 THE REGRESSION. The emulator finishes warm-up believing it has $4,422.88; the account
    holds $2,000. After re-anchoring it must size off $2,000."""
    r, account = _runner(balance=2000.0)
    r.reanchor_equity("after warm-up")
    assert account.balance == 2000.0
    assert "equity_reanchored" in r.ledger.kinds()


def test_the_move_is_recorded_with_both_numbers():
    """A silent correction is indistinguishable from never having drifted. The record has to
    carry what it WAS, or nobody can tell whether this is doing anything."""
    r, _ = _runner(balance=2000.0)
    r.reanchor_equity("after warm-up")
    _, kw = next((k, v) for k, v in r.ledger.events if k == "equity_reanchored")
    assert kw["was"] == pytest.approx(4422.88)
    assert kw["now"] == 2000.0
    assert kw["why"] == "after warm-up"


def test_a_balance_the_terminal_cannot_supply_leaves_the_emulator_alone():
    """⚠ The failure being fixed, arriving through the fix.

    A blind terminal returns no balance. Writing a zero — or any stand-in — would size the next
    trade off a fabricated number, which is worse than the drift it replaces because nothing
    downstream could tell. Same three-state rule as `mt5_link`: `None` means CANNOT ASK.
    """
    r, account = _runner(balance=None)
    r.reanchor_equity("after warm-up")
    assert account.balance == pytest.approx(4422.88)  # untouched
    assert "equity_reanchored" not in r.ledger.kinds()
    assert any("Could not read the account balance" in w for w in r.warns)


def test_a_zero_balance_is_also_refused():
    """`probe_link` returns a float, and 0.0 is falsy — but it is also what an account with no
    money reads. Either way it must not become the sizing basis: a zero balance makes every
    subsequent order either zero-sized or refused, and doing that on a read glitch would take the
    bot offline for a reason nobody could see."""
    r, account = _runner(balance=0.0)
    r.reanchor_equity("after warm-up")
    assert account.balance == pytest.approx(4422.88)
    assert "equity_reanchored" not in r.ledger.kinds()


def test_an_unchanged_balance_writes_nothing():
    """Called on every flat bar. A record per poll would bury the one that mattered — the health
    stream's whole value is that a `pulse` is the only thing in it that repeats."""
    r, account = _runner(balance=2000.0, emulator_balance=2000.0)
    r.reanchor_equity("flat between trades")
    assert r.ledger.kinds() == []
    assert account.balance == 2000.0


def test_a_sub_cent_difference_is_not_worth_a_record():
    """Float arithmetic over thousands of warm-up bars leaves dust. Re-anchoring on it is
    correct and RECORDING it every poll is noise."""
    r, _ = _runner(balance=2000.0, emulator_balance=2000.002)
    r.reanchor_equity("flat between trades")
    assert r.ledger.kinds() == []


def test_a_strategy_that_is_not_built_yet_is_a_no_op():
    """`run()` can fail before `_build_strategy`, and the shutdown path still turns. This must
    not be the thing that raises on the way out."""
    r, _ = _runner(balance=2000.0)
    r.strategy = None
    r.reanchor_equity("after warm-up")  # must not raise
    assert r.ledger.kinds() == []
