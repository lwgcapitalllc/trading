"""Follower mode: the trades room never states lot sizes or dollar amounts.

⚠ **PROVEN BY MUTATION, not by watching it go red on a bug** (rule 12). The behaviour these assert
shipped in the same change, so there was never a red state to observe. Instead each test is checked
by flipping `alerts.SHOW_SIZE` back to True — `test_mutation_*` below does exactly that and asserts
the leak REAPPEARS, so a future edit that quietly restores sizes fails here.
"""

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
for p in (ROOT, ROOT / "algos" / "live", ROOT / "algos" / "shared"):
    if str(p) not in sys.path:
        sys.path.insert(0, str(p))

import alerts  # noqa: E402

ENTRY = dict(
    strategy="SOS Fade",
    symbol="XAUUSD.p",
    direction="LONG",
    entry=3290.0,
    stop=3280.0,
    lots=0.25,
    risk_usd=250.0,
    risk_pct=5,
)
EXIT = dict(
    strategy="SOS Fade",
    symbol="XAUUSD.p",
    exit_price=3320.0,
    pnl_usd=712.50,
    r_multiple=2.85,
    exit_reason="target",
)


def test_policy_default_is_follower_mode():
    assert alerts.SHOW_SIZE is False


def test_entry_states_prices_and_no_size():
    m = alerts.format_entry(show_size=False, **ENTRY)
    assert "3,290.00" in m and "3,280.00" in m  # the two prices a follower needs
    assert "lots" not in m and "$" not in m and "Risking" not in m


def test_exit_keeps_r_and_drops_dollars():
    m = alerts.format_exit(show_size=False, **EXIT)
    assert "+2.85R" in m and "3,320.00" in m
    assert "$" not in m and "712" not in m


def test_exit_with_no_r_still_names_the_price():
    m = alerts.format_exit(show_size=False, **{**EXIT, "r_multiple": None})
    assert "3,320.00" in m and "$" not in m


def test_partial_bank_says_that_it_banked_not_how_much():
    m = alerts.format_partial_banked(
        lots_banked=0.12, lots_before=0.37, lots_after=0.25, show_size=False
    )
    assert "rest is still running" in m
    assert "lots" not in m and "0.12" not in m and "0.37" not in m


def test_manual_close_drops_dollars_keeps_r():
    m = alerts.format_manual_close(
        symbol="XAUUSD.p", exit_price=3300.0, pnl_usd=-50.0, r_multiple=-0.4, show_size=False
    )
    assert "-0.4R" in m and "$" not in m


def test_stop_moves_are_untouched_they_never_carried_a_size():
    m = alerts.format_stop_moved(
        direction=1, entry=3290.0, was=3280.0, now=3301.5, opening_stop=3280.0
    )
    assert "locking +1.15R" in m and "$" not in m and "lots" not in m


def test_mutation_turning_sizes_back_on_reintroduces_the_leak():
    """The red state, induced: with show_size True every leak this file forbids comes back."""
    e = alerts.format_entry(show_size=True, **ENTRY)
    x = alerts.format_exit(show_size=True, **EXIT)
    p = alerts.format_partial_banked(
        lots_banked=0.12, lots_before=0.37, lots_after=0.25, show_size=True
    )
    assert "lots" in e and "Risking" in e and "$" in e
    assert "$" in x and "712" in x
    assert "0.12" in p and "lots" in p
