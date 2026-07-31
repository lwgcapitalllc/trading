"""The trade alert templates.

These are the messages Aaron actually reads, so the wording is part of the contract, not an
implementation detail. The tests below assert on the things a person would notice: that the
verdict is honest, that a scratch is not filed as a loss, that the numbers are the ones the
broker reported, and that nothing here can throw inside a trading loop.
"""

from __future__ import annotations

import sys
from datetime import datetime, timezone
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "live"))
import alerts  # noqa: E402

_WHEN = datetime(2026, 7, 31, 1, 45, tzinfo=timezone.utc)


# ── pips ────────────────────────────────────────────────────────────────────────
def test_pip_size_is_derived_from_the_symbol_not_hardcoded():
    """Hardcoding a pip per instrument is how every stop distance in every alert ends up
    quietly wrong on a broker whose quotes carry a different number of digits."""
    assert alerts.pip_size(5, 0.00001) == pytest.approx(0.0001)   # 5-digit major
    assert alerts.pip_size(3, 0.001) == pytest.approx(0.01)       # JPY pair
    assert alerts.pip_size(2, 0.01) == pytest.approx(0.01)        # 2-digit gold
    assert alerts.pip_size(4, 0.0001) == pytest.approx(0.0001)    # 4-digit legacy quote


def test_stop_distance_is_reported_in_pips():
    msg = alerts.format_entry(strategy="MPC SOS Fade", symbol="XAUUSD.s", direction="LONG",
                              entry=4094.87, stop=4077.62, lots=0.05, when=_WHEN)
    assert "1,725 pips" in msg            # $17.25 at one point per pip on 2-digit gold


def test_stop_distance_is_a_distance_not_a_direction():
    """A short's stop sits ABOVE its entry. Subtracting in one fixed order would print a
    negative distance on every short."""
    short = alerts.format_entry(strategy="S", symbol="XAUUSD.s", direction="SHORT",
                                entry=4077.62, stop=4094.87, lots=0.05, when=_WHEN)
    assert "1,725 pips" in short
    assert "-1,725" not in short


# ── entry ───────────────────────────────────────────────────────────────────────
def test_entry_carries_everything_asked_for():
    """Aaron's list: strategy, date, direction, entry, stop, stop distance, lot size."""
    msg = alerts.format_entry(strategy="MPC SOS Fade", symbol="XAUUSD.s", direction="LONG",
                              entry=4094.87, stop=4077.62, lots=0.05, when=_WHEN)
    for expected in ("MPC SOS Fade", "XAUUSD.s", "LONG", "4,094.87", "4,077.62",
                     "1,725 pips", "0.05", "Fri 31 Jul 2026, 01:45 UTC"):
        assert expected in msg, f"missing {expected!r} from:\n{msg}"


def test_direction_is_visible_without_opening_the_message():
    """The first line is what a notification preview shows."""
    first = lambda d: alerts.format_entry(strategy="S", symbol="X", direction=d, entry=1.0,
                                          stop=0.9, lots=1, when=_WHEN).splitlines()[0]
    assert "LONG" in first("LONG") and "📈" in first("LONG")
    assert "SHORT" in first("SHORT") and "📉" in first("SHORT")


def test_lot_size_does_not_print_trailing_zeros():
    msg = alerts.format_entry(strategy="S", symbol="X", direction="LONG", entry=1.0, stop=0.9,
                              lots=0.5, when=_WHEN)
    assert "Lot size: 0.5" in msg


# ── verdict ─────────────────────────────────────────────────────────────────────
def test_win_and_lose_follow_the_money():
    assert alerts.verdict(292.65, 3.39) == alerts.WIN
    assert alerts.verdict(-84.10, -1.0) == alerts.LOSE


def test_a_scratch_is_breakeven_even_though_it_lost_money():
    """The exact case Aaron named. A stop moved to entry and hit is a scratch, but spread and
    commission still leave it a few dollars down. Filing that as a LOSE would put a working risk
    rule in the same bucket as real losers and make the win rate read worse than the strategy
    behaves — while the dollar figure stays honest about the cost."""
    assert alerts.verdict(-0.62, r_multiple=-0.01) == alerts.BREAKEVEN
    msg = alerts.format_exit(strategy="S", symbol="X", exit_price=4094.87, pnl_usd=-0.62,
                             r_multiple=-0.01, when=_WHEN)
    assert "BREAKEVEN" in msg
    assert "-0.62" in msg          # the money is never rounded away to make it look clean


def test_a_real_loss_is_not_excused_as_breakeven():
    assert alerts.verdict(-410.0, r_multiple=-1.0) == alerts.LOSE


def test_the_scratch_band_comes_from_the_strategy():
    """`exec_scratch_r` is the strategy's own definition of "nothing happened". Hardcoding a
    band here would disagree with the backtest that produced the numbers being compared."""
    assert alerts.verdict(-5.0, r_multiple=-0.30, scratch_r=0.15) == alerts.LOSE
    assert alerts.verdict(-5.0, r_multiple=-0.30, scratch_r=0.50) == alerts.BREAKEVEN


def test_verdict_falls_back_to_the_pnl_when_r_is_unknown():
    """R needs the risk that was actually attached. When that is missing, the sign of the money
    is the most that can honestly be claimed."""
    assert alerts.verdict(50.0, None) == alerts.WIN
    assert alerts.verdict(-50.0, None) == alerts.LOSE
    assert alerts.verdict(0.0, None) == alerts.BREAKEVEN


# ── exit ────────────────────────────────────────────────────────────────────────
def test_exit_carries_everything_asked_for():
    """Aaron's list: date, verdict, dollar amount, exit price."""
    msg = alerts.format_exit(strategy="MPC SOS Fade", symbol="XAUUSD.s", exit_price=4153.40,
                             pnl_usd=292.65, r_multiple=3.39, when=_WHEN)
    for expected in ("WIN", "+292.65 USD", "4,153.40", "Fri 31 Jul 2026, 01:45 UTC"):
        assert expected in msg, f"missing {expected!r} from:\n{msg}"


def test_a_loss_shows_its_sign():
    msg = alerts.format_exit(strategy="S", symbol="X", exit_price=1.0, pnl_usd=-84.10,
                             r_multiple=-1.0, when=_WHEN)
    assert "-84.10" in msg
    assert "❌" in msg


def test_the_outcome_is_the_first_thing_on_the_line():
    msg = alerts.format_exit(strategy="S", symbol="X", exit_price=1.0, pnl_usd=292.65,
                             r_multiple=3.0, when=_WHEN)
    assert msg.splitlines()[0].startswith("✅ WIN")


# ── robustness ──────────────────────────────────────────────────────────────────
def test_no_markdown_syntax_in_either_template():
    """These messages carry strategy names and broker symbols, which are full of underscores.
    Telegram rejects an unbalanced Markdown entity and drops the WHOLE message — so an alert
    must not depend on the sender's plain-text rescue."""
    entry = alerts.format_entry(strategy="mpc_sos_fade_demo", symbol="XAUUSD.s",
                                direction="LONG", entry=1.0, stop=0.9, lots=1, when=_WHEN)
    exit_ = alerts.format_exit(strategy="mpc_sos_fade_demo", symbol="XAUUSD.s", exit_price=1.0,
                               pnl_usd=1.0, r_multiple=1.0, when=_WHEN)
    for msg in (entry, exit_):
        assert "*" not in msg
        assert msg.count("_") == msg.count("mpc_sos_fade_demo") * 3   # only the name's own


def test_a_naive_timestamp_is_read_as_utc_not_as_local_time():
    """A bar time that arrives without a timezone must not silently shift by the machine's
    offset — the same trade would be stamped differently on the Mac and the VPS."""
    naive = datetime(2026, 7, 31, 1, 45)
    msg = alerts.format_entry(strategy="S", symbol="X", direction="LONG", entry=1.0, stop=0.9,
                              lots=1, when=naive)
    assert "01:45 UTC" in msg


def test_a_zero_width_stop_does_not_crash_the_alert():
    """It should never happen — the minimum-stop guard and the broker both refuse it — but an
    alert that raises would take down the loop that was reporting a trade."""
    msg = alerts.format_entry(strategy="S", symbol="X", direction="LONG", entry=1.0, stop=1.0,
                              lots=1, when=_WHEN)
    assert "0 pips" in msg
