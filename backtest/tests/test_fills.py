"""A2 fill & cost model — hand-computed, offline, no VPS and no TradingView.

The numbers here are REAL and sourced, not invented; that is the point of the module under test.
Where a test pins a figure it names where it came from, so a future change that contradicts the
broker fails loudly instead of drifting.
"""

from __future__ import annotations

import datetime

import pytest

from backtest.data.ticks import Tick, TickWindowUnavailable
from backtest.fills import (
    PROFILES,
    SPREAD_UNMEASURED,
    AccountProfile,
    Bar,
    BarPathResolver,
    CostsNotConfigured,
    Level,
    SwapModel,
    TickPathResolver,
)

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
    ECN $1/side/lot. Corroborated by the live demo's FIXED $0.32 gold spread, which is how a
    commission-free tier is priced (raw tiers quote a variable spread near zero).

    ⚠ These commission figures are the broker's PUBLISHED ones and the sources contradict each
    other on which tier carries $1.00 and which $3.50 — see `docs/BROKER_QUESTIONS.md`. They are
    kept because commission is the one of the three costs a page can state unambiguously per lot;
    the spread and swap on those tiers refuse instead."""
    assert PROFILES["puprime_standard"].commission_per_side_per_lot == 0.00
    assert PROFILES["puprime_prime"].commission_per_side_per_lot == 3.50
    assert PROFILES["puprime_ecn"].commission_per_side_per_lot == 1.00


def test_commission_is_per_lot_not_per_unit():
    """The 100x bug: the strategy sizes in OUNCES, commission is quoted per LOT (100oz). Charging
    per unit would overstate commission by the contract size."""
    prime = PROFILES["puprime_prime"]
    assert prime.lots(1485) == 14.85
    assert prime.commission(1485) == pytest.approx(3.50 * 14.85)
    assert prime.commission(100) == pytest.approx(3.50)  # exactly one lot


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
    assert _SWAP.charge(1, 1.0, tue) < 0  # long pays
    assert _SWAP.charge(-1, 1.0, tue) > 0  # short is credited


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
    assert p.swap_charge(1, 100, tue) == pytest.approx(-79.60)  # 100oz = 1 lot
    assert p.swap_charge(1, 1485, tue) == pytest.approx(-79.60 * 14.85)


def test_profile_without_swap_charges_nothing():
    p = AccountProfile("noswap", 0.0)
    assert p.swap_charge(1, 1485, datetime.date(2026, 7, 14)) == 0.0


# ── BarPathResolver: must stay exactly as dumb as the Pine ────────────────────


def test_bar_resolver_ties_resolve_to_targets_first():
    """Byte-for-byte with mpc_sos_fade.execution._intrabar_targets_first, which uses <=. A strict <
    flips every doji-ish bar and silently breaks compare_strategy.py's exit 0."""
    assert BarPathResolver.targets_first(100.0, 101.0, 99.0) is True  # exact tie
    assert BarPathResolver.targets_first(100.9, 101.0, 99.0) is True  # open near high
    assert BarPathResolver.targets_first(99.1, 101.0, 99.0) is False  # open near low


def test_bar_resolver_reports_no_slippage_because_it_cannot_see_any():
    f = BarPathResolver().first_touch(_bar(), {"tp": Level(100.8, falling=False)})
    assert f.key == "tp"
    assert f.price == 100.8  # the level itself — a bar has no price between its extremes
    assert f.slippage == 0.0


def test_bar_resolver_returns_none_when_nothing_reached():
    assert (
        BarPathResolver().first_touch(_bar(h=101.0, l=99.0), {"tp": Level(105.0, falling=False)})
        is None
    )


def test_bar_resolver_picks_by_assumed_path():
    bar = _bar(o=100.9, h=101.0, l=99.0)  # open near high -> up first
    f = BarPathResolver().first_touch(
        bar, {"stop": Level(99.5, falling=True), "tp": Level(100.95, falling=False)}
    )
    assert f.key == "tp"
    bar = _bar(o=99.1, h=101.0, l=99.0)  # open near low -> down first
    f = BarPathResolver().first_touch(
        bar, {"stop": Level(99.5, falling=True), "tp": Level(100.95, falling=False)}
    )
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
    ticks = [Tick(10, 100.60, 100.93), Tick(20, 99.40, 99.73)]  # target first, then stop
    r = TickPathResolver(FakeTicks(ticks), "XAUUSD.s")
    f = r.first_touch(
        _bar(h=101.0, l=99.0),
        {"stop": Level(99.50, falling=True), "tp": Level(100.50, falling=False)},
        buying=False,
    )
    assert f.key == "tp"

    ticks = [Tick(10, 99.40, 99.73), Tick(20, 100.60, 100.93)]  # stop first
    r = TickPathResolver(FakeTicks(ticks), "XAUUSD.s")
    f = r.first_touch(
        _bar(h=101.0, l=99.0),
        {"stop": Level(99.50, falling=True), "tp": Level(100.50, falling=False)},
        buying=False,
    )
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
    ticks = [Tick(10, 100.50, 100.83), Tick(20, 86.76, 87.09)]  # a $13.74 hole
    r = TickPathResolver(FakeTicks(ticks), "XAUUSD.s")
    f = r.first_touch(_bar(l=86.0), {"stop": Level(99.90, falling=True)}, buying=False)
    assert f.price == 86.76
    assert f.slippage == pytest.approx(13.14)


# ── honesty guards ────────────────────────────────────────────────────────────


def test_missing_ticks_raise_rather_than_silently_guessing():
    """A backtest that quietly downgrades its own fill model is the failure this module exists to
    prevent."""
    r = TickPathResolver(FakeTicks([], raise_with=TickWindowUnavailable("agent down")), "XAUUSD.s")
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
    f = r.first_touch(
        _bar(ms=1_000_000, h=101.5, l=98.5), {"stop": Level(99.50, falling=True)}, buying=False
    )
    assert f is None, "the 99.0 tick arrived before our order did"


# ── spread (2026-08-02) ──────────────────────────────────────────────────────────


def test_each_brokers_spread_is_its_own_measurement():
    """The two differ by ~45%, so quoting one for the other overstates or understates every
    bar-mode run on that broker. Vantage is the BACKTEST broker; PU Prime is where we trade live.
    Both are measured off that broker's own bid/ask ticks — see the note in fills.py.

    ⚠ These are MEASUREMENTS, so this test failing on a deliberate re-measure is the system
    working. What it exists to catch is the other case: one broker's figure being copied onto the
    other, or a number moving with no measurement behind it. Re-measure with
    `algos/tools/broker_facts.py --history-days N`, then change the value AND the provenance
    comment in fills.py in the same commit.

    PU Prime last measured 2026-08-06 over 1,893,438 ticks / 3 whole days off the live terminal.
    """
    assert PROFILES["vantage_demo"].spread == 0.22
    assert PROFILES["puprime_standard"].spread == 0.32


# ── the spread belongs to an ACCOUNT TIER, not to a broker ────────────────────


def test_the_raw_puprime_tiers_do_not_inherit_standards_measured_spread():
    """🔴 The defect this whole block exists for, shipped until 2026-08-06.

    All four PU Prime tiers carried 0.32 — a figure measured on a STANDARD demo, which is the one
    tier priced by a MARKED-UP spread. So `puprime_ecn` charged ECN's commission on top of
    Standard's spread: a combination no real account offers, which overstates every raw tier and
    makes the commission-free one look better than it is. Nothing errored.

    ⚠ The right fix is a REFUSAL, not a published figure typed into code — a marketing page is not
    a measurement, and the published numbers for these tiers contradict each other across sources
    (their own account-types page puts ECN at $1.00/side and Prime at $3.50; a third-party
    breakdown reverses it). Measure the tier, then replace the sentinel.

    ✅ **ECN was measured on 2026-08-14 (3,033,270 ticks over 5 days) and left this list**, which
    is the sentinel doing its job rather than the rule weakening. What it may NOT do is take ECN's
    figure with it: Prime is indistinguishable from ECN on every field the terminal publishes, so
    "they look the same" is available as an argument again — and it is the same argument that put
    Standard's 0.32 on all four tiers and was wrong by 2.7x. Prime is measured off Prime's own
    tick stream or it keeps refusing.
    """
    assert PROFILES["puprime_standard"].spread_measured is True
    for tier in ("puprime_prime", "puprime_cent"):
        assert PROFILES[tier].spread_measured is False, tier
        assert PROFILES[tier].spread != PROFILES["puprime_standard"].spread, tier
    # The raw tier that IS measured must still not be carrying Standard's marked-up number — the
    # original defect was a shared value, and a tier moving from refusal to 0.32 would satisfy
    # every assertion above while reinstating it exactly.
    assert PROFILES["puprime_ecn"].spread_measured is True
    assert PROFILES["puprime_ecn"].spread != PROFILES["puprime_standard"].spread


def test_charging_an_unmeasured_spread_refuses_and_names_the_tool():
    """It must RAISE, never fall back. Two things make a silent fallback worse than a crash here:
    0.0 would run a raw-tier backtest charging commission and no spread at all, and the sentinel
    is NEGATIVE, so passing it through pays the trader half a spread on every fill.

    ⚠ Reads `puprime_prime` since 2026-08-14 — it was `puprime_ecn` until that tier was measured.
    The tier here has to be one that genuinely still refuses, or this becomes a test of nothing."""
    with pytest.raises(CostsNotConfigured) as exc:
        PROFILES["puprime_prime"].spread_or_refuse()
    assert "broker_facts.py" in str(exc.value)
    assert "puprime_prime" in str(exc.value)


def test_a_measured_spread_is_returned_unchanged():
    """The other half of the rule, stated on purpose — a guard that refuses everything is not a
    guard. Pinned because a rule written in one direction is the one that gets 'simplified'.

    ⚠ **ECN's 0.12 is asserted as a VALUE, not just as 'measured'.** The whole failure this file
    documents is a tier silently carrying a number that belongs to a different tier, and
    `spread_measured is True` cannot tell 0.12 from 0.32."""
    assert PROFILES["puprime_standard"].spread_or_refuse() == 0.32
    assert PROFILES["puprime_ecn"].spread_or_refuse() == 0.12
    assert PROFILES["vantage_demo"].spread_or_refuse() == 0.22


def test_modelling_fills_on_an_unmeasured_spread_is_refused_at_construction():
    """`bid_ask_fills` decides WHICH TRADES EXIST, so it is caught at construction rather than at
    the first fill — the same reasoning as the existing spread<=0 guard beside it, and the earliest
    point the mistake can be reported.

    ⚠ **It asserts the MESSAGE, and that is the whole test.** The sentinel is -1.0, so the older
    `spread <= 0` guard one line below already raises — with the words *"spread is 0 — the ask
    would equal the bid"*, which is a confident FALSE DIAGNOSIS: the spread is not zero, it is
    unknown. Proven by neutering this guard alone, which leaves the raise intact and the wording
    wrong. Never let a nearby guard's message stand in for a distinct failure."""
    with pytest.raises(CostsNotConfigured) as exc:
        AccountProfile("ecn-like", 1.00, spread=SPREAD_UNMEASURED, bid_ask_fills=True)
    assert "never been measured" in str(exc.value)


def test_an_unmeasured_tier_still_builds_a_profile_for_the_cost_it_does_know():
    """The refusal is at the point of CHARGING, not construction. Commission is the one of the
    three costs that is stated per lot and unambiguous, so a raw tier can still be charged it.
    Refusing to build the profile at all would make the honest part unusable.

    ⚠ Reads `puprime_prime` since 2026-08-14, for the same reason as the refusal test above: ECN's
    spread is measured now, so asserting this on ECN would no longer exercise an unmeasured tier."""
    prime = PROFILES["puprime_prime"]
    assert prime.spread_measured is False
    assert prime.commission(100) == pytest.approx(3.50)


# ── swap is NOT tier-invariant, and that was measured rather than assumed ─────


def test_the_raw_puprime_tiers_refuse_their_swap_too():
    """🔴 The assumption this replaces was written down on 2026-08-06 and overturned the same day.

    Every tier borrowed Standard's swap on the reasoning that overnight financing is a fact about
    the SYMBOL. **Measured on PU Prime's own terminal, that fails on the broker's own products:**
    `XAUUSD.s` and `XAUUSD.crp` are the same market quoted twice on ONE account (median M15 close
    difference $0.08 over 200 shared bars) and carry swaps 8.5x apart — long -79.60 vs -9.35 —
    with the short CREDIT gone entirely, +30.25 vs +0.04.

    That credit is what makes this strategy's swap arithmetic work at all (it trades both sides and
    the short credit nearly cancels the long charge), so borrowing another product's swap is not a
    small approximation. A tier is measured or it refuses.

    ⚠ **RE-AIMED 2026-08-08, and read the reason before widening it back.** Prime and ECN were
    MEASURED on that date — Aaron opened a demo of each tier, MT5_Lab was logged into all three in
    turn, and all three read long -79.60 / short +30.25 on their own symbol (`.s` on Standard,
    `.p` on both raw tiers, and neither account can see the other's). So those two are no longer
    unmeasured and asserting that they refuse would be asserting something false.

    **`puprime_cent` is still genuinely unread — there is no Cent account — so the guard moves
    there rather than being deleted.** The rule it protects is unchanged and is not about which
    tiers happen to agree today: a tier is measured, or it refuses. Three tiers agreeing is a
    RESULT, and if it were also the assumption there would be nothing left to catch the next
    product that does not.
    """
    for tier in ("puprime_standard", "puprime_prime", "puprime_ecn"):
        assert PROFILES[tier].swap.unmeasured is False, tier
    assert PROFILES["puprime_cent"].swap.unmeasured is True


def test_the_measured_raw_tiers_carry_the_rate_that_was_actually_read():
    """The three tiers agreeing is the FINDING, so pin the numbers rather than pinning
    `unmeasured is False` — the latter would stay green if somebody swapped in a plausible
    stand-in, which is the exact move the sentinel exists to prevent.

    Read 2026-08-08 off accounts 700119432 (Standard), 700152904 (Prime) and 700152905 (ECN) with
    `algos/tools/broker_facts.py`. The SIGN of the short value is the load-bearing half: gold's
    short swap is a CREDIT, and this strategy trades both sides."""
    for tier in ("puprime_standard", "puprime_prime", "puprime_ecn"):
        swap = PROFILES[tier].swap
        assert swap.per_lot_per_night(1) == pytest.approx(-79.60), tier
        assert swap.per_lot_per_night(-1) == pytest.approx(+30.25), tier


def test_charging_an_unmeasured_swap_refuses_rather_than_borrowing():
    """Both the per-night rate and the full charge refuse — `charge()` routes through
    `per_lot_per_night`, so one guard covers the two entry points a caller might reach for."""
    swap = PROFILES["puprime_cent"].swap
    with pytest.raises(CostsNotConfigured):
        swap.per_lot_per_night(1)
    with pytest.raises(CostsNotConfigured) as exc:
        swap.charge(1, 1.0, datetime.date(2026, 8, 6))
    assert "never been read" in str(exc.value)


def test_the_profile_level_swap_charge_refuses_too():
    """`AccountProfile.swap_charge` is the seam both real consumers use (`execution.py` and
    `reprice.py`), so the refusal has to survive that hop rather than only living on the model."""
    with pytest.raises(CostsNotConfigured):
        PROFILES["puprime_cent"].swap_charge(1, 100.0, datetime.date(2026, 8, 6))


def test_an_unmeasured_swap_is_NOT_the_same_as_charging_no_swap():
    """The distinction the whole sentinel exists for. `swap = None` means *deliberately charge no
    swap* and must stay silent; an unmeasured swap must refuse. Collapsing them would run a raw-tier
    backtest with the single largest cost on this strategy quietly set to zero."""
    free = AccountProfile("free", 0.00, swap=None)
    assert free.swap_charge(1, 100.0, datetime.date(2026, 8, 6)) == 0.0


def test_a_measured_swap_still_charges_normally():
    """The other direction of the rule, stated on purpose — a guard that refuses everything is not
    a guard. -79.60 * 100 * 10^-2 = -$79.60 per lot per night, one night."""
    charged = PROFILES["puprime_standard"].swap_charge(1, 100.0, datetime.date(2026, 8, 6))
    assert charged == pytest.approx(-79.60)


def test_bid_ask_fills_refuses_to_run_with_no_spread():
    """The ask would equal the bid, so the setting would change nothing while claiming the fills
    are modelled — the same silent-no-op class as the costs the lab collected and never charged."""
    with pytest.raises(CostsNotConfigured):
        AccountProfile("x", 0.0, spread=0.0, bid_ask_fills=True)


def test_a_negative_spread_is_refused():
    """It is a WIDTH, not a signed cost. A negative one would pay you to trade."""
    with pytest.raises(CostsNotConfigured):
        AccountProfile("x", 0.0, spread=-0.1)


def test_spread_defaults_to_not_priced():
    """0.0 means 'not priced', the same honest default `slippage_ticks` carries — which is what
    keeps a profile built before this field existed byte-identical."""
    assert AccountProfile("x", 0.0).spread == 0.0
    assert AccountProfile("x", 0.0).bid_ask_fills is False
