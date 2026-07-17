"""A2 fill & cost model — hand-computed, offline, no VPS and no TradingView.

The numbers here are REAL and sourced, not invented; that is the point of the module under test.
Where a test pins a figure it names where it came from, so a future change that contradicts the
broker fails loudly instead of drifting.
"""

from __future__ import annotations

import datetime

import pytest

from backtest.data.ticks import Tick, TickWindowUnavailable
from backtest.fills import (PROFILES, AccountProfile, Bar, BarPathResolver, CostsNotConfigured,
                            Level, SwapModel, TickPathResolver)

_SWAP = SwapModel(swap_long_points=-78.29, swap_short_points=29.49)


def _bar(o=100.0, h=101.0, l=99.0, c=100.5, ms=0, dur=300_000) -> Bar:
    return Bar(time_ms=ms, open=o, high=h, low=l, close=c, duration_ms=dur)


class FakeTicks:
    """Serves a canned tick list for any window; records what was asked for."""

    def __init__(self, ticks, raise_with=None):
        self._ticks = ticks
        self.raise_with = raise_with
        self.calls = []

    def window(self, symbol, start_ms, end_ms):
        self.calls.append((symbol, start_ms, end_ms))
        if self.raise_with:
            raise self.raise_with
        return [t for t in self._ticks if start_ms <= t.ms < end_ms]


# ── cost inputs must be decisions, never defaults ─────────────────────────────

def test_profile_refuses_unset_commission():
    with pytest.raises(CostsNotConfigured, match="commission_per_side_per_lot"):
        AccountProfile("mystery")


def test_zero_commission_is_allowed_and_distinct_from_unset():
    """The whole reason for the sentinel: PU Prime Standard really is $0, and saying so must be
    possible — and must be different from never having said."""
    p = AccountProfile("checked", 0.0)
    assert p.commission(1_000) == 0.0


def test_swap_refuses_unset_points():
    with pytest.raises(CostsNotConfigured, match="swap_long_points"):
        SwapModel()


def test_negative_commission_rejected():
    with pytest.raises(CostsNotConfigured):
        AccountProfile("bad", -1.5)


# ── the verified PU Prime profiles ────────────────────────────────────────────

def test_puprime_standard_is_commission_free():
    """Source: puprime.com/account-types (checked 2026-07-16) — Standard $0, Prime $3.5/side/lot,
    ECN $1/side/lot. Corroborated by the live demo's FIXED $0.33 gold spread, which is how a
    commission-free tier is priced (raw tiers quote a variable spread near zero)."""
    assert PROFILES["puprime_standard"].commission_per_side_per_lot == 0.00
    assert PROFILES["puprime_prime"].commission_per_side_per_lot == 3.50
    assert PROFILES["puprime_ecn"].commission_per_side_per_lot == 1.00


def test_commission_is_per_lot_not_per_unit():
    """The 100x bug: the strategy sizes in OUNCES, commission is quoted per LOT (100oz). Charging
    per unit would overstate commission by the contract size."""
    prime = PROFILES["puprime_prime"]
    assert prime.lots(1485) == 14.85
    assert prime.commission(1485) == pytest.approx(3.50 * 14.85)
    assert prime.commission(100) == pytest.approx(3.50)     # exactly one lot


# ── swap: the broker's own formula ────────────────────────────────────────────

def test_swap_matches_the_brokers_published_formula():
    """PU Prime, fee-charges page, verbatim:
        Swap in points = Swap (long or short) * Contract Size * 10^(-Digits) * Lot * Nights
    XAUUSD.s long: -78.29 * 100 * 10^-2 * 1 * 1 = -78.29
    """
    assert _SWAP.per_lot_per_night(1) == pytest.approx(-78.29)
    assert _SWAP.per_lot_per_night(-1) == pytest.approx(29.49)


def test_long_pays_and_short_earns():
    """The asymmetry that makes swap change the strategy's direction bias, not just its total."""
    tue = datetime.date(2026, 7, 14)
    assert _SWAP.charge(1, 1.0, tue) < 0      # long pays
    assert _SWAP.charge(-1, 1.0, tue) > 0     # short is credited


def test_wednesday_is_triple():
    tue = datetime.date(2026, 7, 14)
    wed = datetime.date(2026, 7, 15)
    assert _SWAP.nights_charged(tue) == 1
    assert _SWAP.nights_charged(wed) == 3
    assert _SWAP.charge(1, 1.0, wed) == pytest.approx(3 * _SWAP.charge(1, 1.0, tue))
    assert _SWAP.charge(1, 1.0, wed) == pytest.approx(-234.87)


def test_swap_scales_with_lots():
    tue = datetime.date(2026, 7, 14)
    assert _SWAP.charge(1, 14.85, tue) == pytest.approx(-78.29 * 14.85)


def test_profile_swap_converts_units_to_lots():
    p = PROFILES["puprime_standard"]
    tue = datetime.date(2026, 7, 14)
    assert p.swap_charge(1, 100, tue) == pytest.approx(-78.29)     # 100oz = 1 lot
    assert p.swap_charge(1, 1485, tue) == pytest.approx(-78.29 * 14.85)


def test_profile_without_swap_charges_nothing():
    p = AccountProfile("noswap", 0.0)
    assert p.swap_charge(1, 1485, datetime.date(2026, 7, 14)) == 0.0


# ── BarPathResolver: must stay exactly as dumb as the Pine ────────────────────

def test_bar_resolver_ties_resolve_to_targets_first():
    """Byte-for-byte with mpc_sos_fade.execution._intrabar_targets_first, which uses <=. A strict <
    flips every doji-ish bar and silently breaks compare_strategy.py's exit 0."""
    assert BarPathResolver.targets_first(100.0, 101.0, 99.0) is True    # exact tie
    assert BarPathResolver.targets_first(100.9, 101.0, 99.0) is True    # open near high
    assert BarPathResolver.targets_first(99.1, 101.0, 99.0) is False    # open near low


def test_bar_resolver_reports_no_slippage_because_it_cannot_see_any():
    f = BarPathResolver().first_touch(_bar(), {"tp": Level(100.8, falling=False)})
    assert f.key == "tp"
    assert f.price == 100.8      # the level itself — a bar has no price between its extremes
    assert f.slippage == 0.0


def test_bar_resolver_returns_none_when_nothing_reached():
    assert BarPathResolver().first_touch(_bar(h=101.0, l=99.0), {"tp": Level(105.0, falling=False)}) is None


def test_bar_resolver_picks_by_assumed_path():
    bar = _bar(o=100.9, h=101.0, l=99.0)          # open near high -> up first
    f = BarPathResolver().first_touch(bar, {"stop": Level(99.5, falling=True), "tp": Level(100.95, falling=False)})
    assert f.key == "tp"
    bar = _bar(o=99.1, h=101.0, l=99.0)           # open near low -> down first
    f = BarPathResolver().first_touch(bar, {"stop": Level(99.5, falling=True), "tp": Level(100.95, falling=False)})
    assert f.key == "stop"


# ── TickPathResolver: the truth, and the measured slippage ───────────────────

def test_tick_resolver_fills_at_the_real_next_price_not_the_level():
    """THE point of tick mode. A long's stop at 99.90 that finds the next bid at 99.78 slipped
    $0.12 — reporting the level as the fill would erase the exact cost this exists to measure."""
    ticks = [Tick(10, 100.50, 100.83), Tick(20, 99.78, 100.11)]
    r = TickPathResolver(FakeTicks(ticks), "XAUUSD.s")
    f = r.first_touch(_bar(l=99.0), {"stop": Level(99.90, falling=True)}, buying=False)
    assert f.key == "stop"
    assert f.price == 99.78
    assert f.slippage == pytest.approx(0.12)


def test_tick_resolver_long_transacts_on_the_bid():
    """A long exits by SELLING. Testing the ask (or the mid) quietly refunds spread on all 4 of
    the ladder's fills."""
    ticks = [Tick(10, 100.50, 100.83), Tick(20, 99.95, 99.88)]
    # Second tick's ASK (99.88) is through a 99.90 stop, but its BID (99.95) is not. A long exits
    # by selling, so this must NOT fill.
    r = TickPathResolver(FakeTicks(ticks), "XAUUSD.s")
    assert r.first_touch(_bar(l=99.0), {"stop": Level(99.90, falling=True)}, buying=False) is None


def test_tick_resolver_short_transacts_on_the_ask():
    """A short exits by BUYING, so its stop above the market is tested on the ask."""
    ticks = [Tick(10, 99.50, 99.83), Tick(20, 99.90, 100.23)]
    r = TickPathResolver(FakeTicks(ticks), "XAUUSD.s")
    f = r.first_touch(_bar(h=101.0), {"stop": Level(100.00, falling=False)}, buying=True)
    assert f.key == "stop"
    assert f.price == 100.23
    assert f.slippage == pytest.approx(0.23)


def test_tick_resolver_order_is_chronological_not_by_price():
    """The ambiguous bar: both a target and a stop are in range. The bar guesses; ticks KNOW."""
    ticks = [Tick(10, 100.60, 100.93), Tick(20, 99.40, 99.73)]   # target first, then stop
    r = TickPathResolver(FakeTicks(ticks), "XAUUSD.s")
    f = r.first_touch(_bar(h=101.0, l=99.0), {"stop": Level(99.50, falling=True), "tp": Level(100.50, falling=False)}, buying=False)
    assert f.key == "tp"

    ticks = [Tick(10, 99.40, 99.73), Tick(20, 100.60, 100.93)]   # stop first
    r = TickPathResolver(FakeTicks(ticks), "XAUUSD.s")
    f = r.first_touch(_bar(h=101.0, l=99.0), {"stop": Level(99.50, falling=True), "tp": Level(100.50, falling=False)}, buying=False)
    assert f.key == "stop"


def test_a_better_than_asked_fill_is_not_negative_slippage():
    """A gap in your favour is a gift, not a cost. Slippage is adverse-only."""
    ticks = [Tick(10, 100.90, 101.23)]
    r = TickPathResolver(FakeTicks(ticks), "XAUUSD.s")
    f = r.first_touch(_bar(h=101.5), {"tp": Level(100.50, falling=False)}, buying=False)
    assert f.price == 100.90
    assert f.slippage == 0.0


def test_the_fat_tail_lands_where_it_belongs():
    """Measured on XAUUSD.s: the worst single tick gap in one day was $13.74. No flat parameter can
    express that; the tape just does."""
    ticks = [Tick(10, 100.50, 100.83), Tick(20, 86.76, 87.09)]   # a $13.74 hole
    r = TickPathResolver(FakeTicks(ticks), "XAUUSD.s")
    f = r.first_touch(_bar(l=86.0), {"stop": Level(99.90, falling=True)}, buying=False)
    assert f.price == 86.76
    assert f.slippage == pytest.approx(13.14)


# ── honesty guards ────────────────────────────────────────────────────────────

def test_missing_ticks_raise_rather_than_silently_guessing():
    """A backtest that quietly downgrades its own fill model is the failure this module exists to
    prevent."""
    r = TickPathResolver(FakeTicks([], raise_with=TickWindowUnavailable("agent down")),
                         "XAUUSD.s")
    with pytest.raises(TickWindowUnavailable):
        r.first_touch(_bar(), {"tp": Level(100.8, falling=False)}, buying=False)


def test_an_empty_tick_window_also_raises():
    r = TickPathResolver(FakeTicks([]), "XAUUSD.s")
    with pytest.raises(TickWindowUnavailable, match="no ticks"):
        r.first_touch(_bar(), {"tp": Level(100.8, falling=False)}, buying=False)


def test_fallback_is_explicit_and_recorded():
    """Opting into the guess is allowed — silently doing it is not. Every blind bar is logged so a
    run can report how often it was flying blind."""
    r = TickPathResolver(FakeTicks([]), "XAUUSD.s", fallback=True)
    f = r.first_touch(_bar(ms=7_000), {"tp": Level(100.8, falling=False)}, buying=False)
    assert f.key == "tp"
    assert r.fallback_bars == [7_000]


# ── latency: the one assumption ──────────────────────────────────────────────

def test_latency_shifts_the_window_start():
    """An order is not live until it reaches the broker."""
    fake = FakeTicks([])
    r = TickPathResolver(fake, "XAUUSD.s", fallback=True, latency_ms=75)
    r.first_touch(_bar(ms=1_000_000), {"tp": Level(100.8, falling=False)}, buying=False)
    _, start, end = fake.calls[0]
    assert start == 1_000_075
    assert end == 1_000_000 + 300_000


def test_zero_latency_reads_the_bar_from_its_open():
    fake = FakeTicks([])
    r = TickPathResolver(fake, "XAUUSD.s", fallback=True, latency_ms=0)
    r.first_touch(_bar(ms=1_000_000), {"tp": Level(100.8, falling=False)}, buying=False)
    assert fake.calls[0][1] == 1_000_000


def test_latency_can_skip_an_early_fill():
    """The assumption has teeth: a fill inside the latency window is one you would not have got."""
    ticks = [Tick(1_000_010, 99.0, 99.33), Tick(1_000_200, 100.9, 101.23)]
    fake = FakeTicks(ticks)
    r = TickPathResolver(fake, "XAUUSD.s", latency_ms=75)
    f = r.first_touch(_bar(ms=1_000_000, h=101.5, l=98.5), {"stop": Level(99.50, falling=True)}, buying=False)
    assert f is None, "the 99.0 tick arrived before our order did"
