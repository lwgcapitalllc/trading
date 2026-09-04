"""Re-pricing a stored run must produce the SAME numbers as replaying it charged.

That is the whole claim, and it is the only thing worth testing here — the arithmetic reproducing
is not the point, agreeing with the replay is. So the reference test replays `sos_fade` twice
over real cached bars (free, then charged), throws the charged replay's curve away, rebuilds it
from the free run's stored record, and demands equality to the cent.

The reference test is SKIPPED when the bar cache is absent (it is git-ignored), exactly as the
Pine parity gates skip without a real export. Everything above it runs anywhere.
"""

from __future__ import annotations

import math
from datetime import date
from functools import lru_cache
from pathlib import Path

import pytest

from backtest.fills import PROFILES, AccountProfile
from backtest.reprice import (
    APPROXIMATE_LAYERS,
    EXACT_LAYERS,
    REPRICEABLE_LAYERS,
    RepriceError,
    reprice_curve,
    rollovers_between,
)


def _find_cached_m15() -> Path:
    """The reference bars, wherever the broker partition put them (2026-08-24).

    ⚠ **Searched rather than hardcoded, and this test taught the lesson the hard way**: the
    partition landed and all four real-replay tests here went from passing to SKIPPED in silence,
    because a missing file is indistinguishable from a git-ignored one. The 4 slowest and most
    load-bearing tests in the package stopped running and the suite still printed green.
    """
    base = Path(__file__).resolve().parents[1] / "cache"
    flat = base / "XAUUSD__M15.csv"
    if flat.is_file():
        return flat
    hits = sorted(base.glob("*/XAUUSD__M15.csv"))
    return hits[0] if hits else flat


_CACHE = _find_cached_m15()


def _profile(*, spread: float = 0.0, commission: float = 0.0, swap=None) -> AccountProfile:
    base = PROFILES["vantage_demo"]
    return AccountProfile(
        name="t",
        commission_per_side_per_lot=commission,
        contract_size=base.contract_size,
        mintick=base.mintick,
        latency_ms=base.latency_ms,
        swap=swap,
        spread=spread,
    )


def _row(
    index=1,
    *,
    entry=2000.0,
    stop=1990.0,
    size=10.0,
    profit=100.0,
    entry_ms=1_700_000_000_000,
    exit_ms=1_700_003_600_000,
    direction="Long",
    legs=None,
    legacy=False,
):
    """One equity-curve point as `backtest/output.py` writes it.

    `legacy=True` drops `r` and `risk_usd` to model a run written before 2026-08-03 — the shape
    that has to fall back to recovering both from rounded prices.
    """
    row = {
        "index": index,
        "entry_price": entry,
        "stop_price": stop,
        "size": size,
        "profit": profit,
        "entry_ms": entry_ms,
        "exit_ms": exit_ms,
        "direction": direction,
        "legs": legs if legs is not None else [],
    }
    if not legacy:
        risk = abs(entry - stop) * size
        row.update({"r": profit / risk, "risk_usd": risk})
    return row


# ── the size-independence that makes the whole thing possible ─────────────────────────────────


def test_spread_cost_in_r_is_independent_of_position_size():
    """The theorem the module rests on. A trade risking `dist * qty` and charged `spread * qty`
    loses `spread / dist` of R whatever `qty` is — which is why a cost can be known for a position
    the stored run never sized. If this ever fails, re-pricing is silently about a different run."""
    prof = _profile(spread=0.22)
    small = reprice_curve(
        [_row(size=1.0, profit=10.0)], profile=prof, layers=["spread"], initial_capital=10_000.0
    )
    large = reprice_curve(
        [_row(size=1000.0, profit=10_000.0)],
        profile=prof,
        layers=["spread"],
        initial_capital=10_000.0,
    )
    assert small.trades[0].cost_r == pytest.approx(large.trades[0].cost_r)
    assert small.trades[0].cost_r == pytest.approx(0.22 / 10.0)


def test_no_layers_charges_nothing_and_reproduces_the_stored_curve():
    """The free run has to survive its own re-pricer untouched, or the page's OFF state would
    disagree with the run it is showing."""
    rows = [_row(1, profit=1_000.0), _row(2, profit=-500.0), _row(3, profit=2_500.0)]
    out = reprice_curve(rows, profile=_profile(spread=0.22), layers=[], initial_capital=10_000.0)
    assert out.total_cost_usd == 0.0
    assert out.final_equity == pytest.approx(10_000.0 + 1_000.0 - 500.0 + 2_500.0)
    assert [t.r for t in out.trades] == [pytest.approx(t.r_before) for t in out.trades]


def test_commission_is_charged_per_lot_per_side_on_entry_and_every_rung():
    """Per LOT per SIDE, and a three-rung exit pays four sides, not two. Reading it per-unit
    overcharges gold 100x and nothing downstream looks wrong."""
    legs = [{"qty": 4.0, "ms": 1}, {"qty": 3.0, "ms": 2}, {"qty": 3.0, "ms": 3}]
    prof = _profile(commission=3.0)  # $3 per lot per side, 100 units per lot
    out = reprice_curve(
        [_row(size=10.0, legs=legs)], profile=prof, layers=["commission"], initial_capital=10_000.0
    )
    # entry 10 units = 0.1 lot, plus three rungs summing to the same 0.1 lot → 0.2 lot of sides.
    assert out.trades[0].cost_r * (10.0 * 10.0) == pytest.approx(3.0 * 0.2)


def test_a_trade_with_no_exit_rungs_still_pays_both_sides():
    """A single-exit trade stores no `legs`. Charging only the entry would halve every commission
    on the most common shape there is."""
    out = reprice_curve(
        [_row(size=10.0, legs=[])],
        profile=_profile(commission=3.0),
        layers=["commission"],
        initial_capital=10_000.0,
    )
    assert out.trades[0].cost_r * 100.0 == pytest.approx(3.0 * 0.2)


# ── what it must refuse ───────────────────────────────────────────────────────────────────────


def test_bid_ask_fills_is_refused_rather_than_approximated():
    """It changes WHICH setups fill (161 → 159 on the reference run, with four that never existed
    on the free path). No arithmetic over a stored trade list can invent a trade it lacks."""
    with pytest.raises(RepriceError, match="cannot be re-priced"):
        reprice_curve(
            [_row()],
            profile=_profile(spread=0.22),
            layers=["bid_ask_fills"],
            initial_capital=10_000.0,
        )


def test_slippage_is_refused_too():
    """Charged on MARKET exits only, and which exits were market rather than limit is a property
    of the fill model at replay time — the curve does not record it."""
    with pytest.raises(RepriceError, match="cannot be re-priced"):
        reprice_curve([_row()], profile=_profile(), layers=["slippage"], initial_capital=10_000.0)


@pytest.mark.parametrize("missing", ["entry_price", "stop_price", "size"])
def test_an_incomplete_record_raises_instead_of_pricing_it_anyway(missing):
    """A run predating these fields must be told to re-run. Every alternative — assuming a stop,
    skipping the trade — yields a complete-looking curve about a different run."""
    row = _row()
    row[missing] = 0
    with pytest.raises(RepriceError, match="re-run"):
        reprice_curve(
            [row], profile=_profile(spread=0.22), layers=["spread"], initial_capital=10_000.0
        )


def test_swap_without_trade_times_raises():
    row = _row(entry_ms=0, exit_ms=0)
    with pytest.raises(RepriceError, match="nights"):
        reprice_curve(
            [row],
            profile=_profile(swap=PROFILES["vantage_demo"].swap),
            layers=["swap"],
            initial_capital=10_000.0,
        )


def test_exactness_is_declared_per_layer():
    """A caller must be able to ask, rather than having to know. Swap is accurate, not exact."""
    assert set(EXACT_LAYERS) | set(APPROXIMATE_LAYERS) == set(REPRICEABLE_LAYERS)
    prof = _profile(spread=0.22, swap=PROFILES["vantage_demo"].swap)
    assert reprice_curve(
        [_row()], profile=prof, layers=["spread"], initial_capital=10_000.0
    ).is_exact
    approx = reprice_curve(
        [_row()], profile=prof, layers=["spread", "swap"], initial_capital=10_000.0
    )
    assert not approx.is_exact and approx.approximate_layers == ("swap",)


def test_per_layer_cost_in_R_is_additive_but_in_dollars_it_is_not():
    """Why the pill lists each layer's price in R and only totals in dollars.

    Charging a layer changes the balance, which changes every later position's SIZE, so a layer's
    DOLLAR cost depends on which others are on — three dollar figures under one dollar total would
    not add up, and the panel would look broken while every number in it was right. R has the size
    cancelled out, so the rows sum to the total exactly.
    """
    prof = _profile(spread=0.22, commission=3.0)
    rows = [_row(1, profit=1_000.0), _row(2, profit=-400.0), _row(3, profit=2_000.0)]
    only_spread = reprice_curve(rows, profile=prof, layers=["spread"], initial_capital=10_000.0)
    only_comm = reprice_curve(rows, profile=prof, layers=["commission"], initial_capital=10_000.0)
    both = reprice_curve(
        rows, profile=prof, layers=["spread", "commission"], initial_capital=10_000.0
    )

    assert only_spread.total_cost_r + only_comm.total_cost_r == pytest.approx(both.total_cost_r)
    # ...and the dollars deliberately do NOT, which is the reason the rule above exists.
    assert only_spread.total_cost_usd + only_comm.total_cost_usd != pytest.approx(
        both.total_cost_usd, rel=1e-9
    )


def test_a_run_predating_the_stored_r_is_flagged_as_derived():
    """Not exact, and it must SAY so — an approximate figure rendered identically to an exact one
    is how a number nobody measured comes to be trusted. The values are still right to ~0.02%; the
    flag is about what the page is allowed to claim."""
    prof = _profile(spread=0.22)
    legacy = reprice_curve(
        [_row(legacy=True)], profile=prof, layers=["spread"], initial_capital=10_000.0
    )
    assert legacy.derived_basis and not legacy.is_exact
    assert not reprice_curve(
        [_row()], profile=prof, layers=["spread"], initial_capital=10_000.0
    ).derived_basis


# ── the rollover schedule ─────────────────────────────────────────────────────────────────────


def _ms(y, m, d, h):
    from datetime import datetime
    from zoneinfo import ZoneInfo

    return int(datetime(y, m, d, h, tzinfo=ZoneInfo("America/New_York")).timestamp() * 1000)


def test_friday_and_saturday_rollovers_book_nothing():
    """Gold shuts AT Friday's rollover and the weekend rides on the triple-swap weekday. Charging
    Friday books 8 nights a week instead of 7 — measured at 0.74R too expensive over 161 trades,
    ~20x the holiday residual the module documents."""
    # Thursday 12:00 → Monday 12:00 spans Thu, Fri, Sat and Sun rollovers; only two are charged.
    got = rollovers_between(_ms(2024, 6, 6, 12), _ms(2024, 6, 10, 12), 17)
    assert got == [date(2024, 6, 6), date(2024, 6, 9)]  # Thursday and Sunday
    assert all(d.weekday() not in (4, 5) for d in got)


def test_a_rollover_at_or_before_the_fill_is_not_charged():
    """It predates the position — the replay's own guard, and the reason a trade opened just after
    the boundary is not billed for a night it never held."""
    assert rollovers_between(_ms(2024, 6, 6, 17), _ms(2024, 6, 6, 20), 17) == []
    assert rollovers_between(_ms(2024, 6, 6, 16), _ms(2024, 6, 6, 20), 17) == [date(2024, 6, 6)]


def test_an_intraday_trade_crosses_no_rollover():
    assert rollovers_between(_ms(2024, 6, 6, 9), _ms(2024, 6, 6, 15), 17) == []


def test_swap_is_charged_on_the_size_still_open_at_each_rollover():
    """A runner banks in rungs, so a trade held three nights may carry a third of its position into
    the last one. Charging the entry size overcharges every scale-out."""
    prof = _profile(swap=PROFILES["vantage_demo"].swap)
    entry, exit_ = _ms(2024, 6, 4, 12), _ms(2024, 6, 6, 12)  # crosses Tue and Wed rollovers
    banked = [{"qty": 9.0, "ms": _ms(2024, 6, 5, 9)}, {"qty": 1.0, "ms": exit_}]
    whole = reprice_curve(
        [_row(size=10.0, entry_ms=entry, exit_ms=exit_, legs=[])],
        profile=prof,
        layers=["swap"],
        initial_capital=10_000.0,
    )
    scaled = reprice_curve(
        [_row(size=10.0, entry_ms=entry, exit_ms=exit_, legs=banked)],
        profile=prof,
        layers=["swap"],
        initial_capital=10_000.0,
    )
    assert scaled.trades[0].cost_r < whole.trades[0].cost_r


def test_a_short_is_credited_swap_rather_than_charged():
    """Gold's short swap is POSITIVE on both broker profiles. A re-pricer that took the absolute
    value would turn a credit into a cost and get the strategy's direction bias backwards."""
    prof = _profile(swap=PROFILES["vantage_demo"].swap)
    entry, exit_ = _ms(2024, 6, 4, 12), _ms(2024, 6, 6, 12)
    long_ = reprice_curve(
        [_row(entry_ms=entry, exit_ms=exit_, direction="Long")],
        profile=prof,
        layers=["swap"],
        initial_capital=10_000.0,
    )
    short = reprice_curve(
        [_row(entry_ms=entry, exit_ms=exit_, direction="Short")],
        profile=prof,
        layers=["swap"],
        initial_capital=10_000.0,
    )
    assert long_.trades[0].cost_r > 0 > short.trades[0].cost_r


# ── the reference: does it agree with a real replay? ───────────────────────────────────────────
#
# ⚠ **The replays below are CACHED, and the FREE one is why.** Every case here replays
# `sos_fade` twice over two years of M15 bars — free, then charged — and the free replay is
# character-for-character the same run in all four. MEASURED before caching: 8 full replays and 4
# reads of the bar cache, 182s for this file; the four distinct replays it actually needs are the
# free one plus one per cost layer.
#
# ⚠ **Keyed on the cost kwargs, not on the built profile.** `_profile()` returns a fresh object per
# call, so a cache keyed on it would depend on `AccountProfile` hashing by VALUE — true today and
# not something this file should be pinning. The kwargs are what the parametrize block states, and
# `test_the_sizing_fraction...` below deliberately states the SAME spread as the first case so the
# two share a replay rather than repeating one.
#
# ⚠ **An execution is handed to every caller as-is, so nothing may mutate one.** Both tests read
# `.trades` and neither writes; a copy per call would replace the saving with a deep copy of the
# thing that was expensive to build.


@lru_cache(maxsize=None)
def _window_df():
    """The reference window: two years of real cached M15 bars."""
    import pandas as pd

    df = pd.read_csv(_CACHE, parse_dates=["time"])
    df = df[(df["time"] >= "2021-01-01") & (df["time"] <= "2023-01-01")]
    return df.set_index("time").tz_localize("UTC")


@lru_cache(maxsize=None)
def _replay(cost_kwargs: tuple = ()):
    """One replay of the reference strategy over that window. `()` is the FREE run."""
    from backtest.replay import build_strategy
    from strategies.python.sos_fade import LAB_STRATEGY

    profile = _profile(**dict(cost_kwargs)) if cost_kwargs else None
    cfg = LAB_STRATEGY["config"]()
    s = build_strategy(
        LAB_STRATEGY["strategy"], cfg, initial_capital=10_000.0, cost_profile=profile
    )
    s.run(_window_df(), warmup=200)
    return s.execution


@pytest.mark.skipif(not _CACHE.exists(), reason="bar cache absent (git-ignored)")
@pytest.mark.parametrize(
    "layers,kwargs,tolerance,equity_rel",
    [
        (["spread"], {"spread": 0.22}, 1e-5, 1e-6),
        (["commission"], {"commission": 3.0}, 1e-5, 1e-6),
        # ⚠ **SWAP WAS NOT COVERED HERE UNTIL 2026-08-03, AND IT IS THE BIGGEST LAYER** — 6.41R of the
        # reference run's 12.08R, against the spread's 5.67R. The two rows above are the exact ones, so
        # a suite containing only them proved the cheap half and left the approximate half — the one
        # whose docstring makes a numeric accuracy claim — resting on nothing.
        #
        # The tolerance is a MEASURED fact, not a loosened bound. Audited over the full 2020→2026 run
        # (155,453 M15 bars, 161 trades) against a real charged replay: **exactly ONE trade disagrees**,
        # by 0.0376R — the long held 2022-12-28 → 2023-01-03, where `rollovers_between` books a New Year
        # night the replay never charged because no bar existed to charge it on. That is the holiday
        # supersede the module docstring names, and it is the whole of the error: spread 0.0000R,
        # commission 0.0000R, swap −0.0376R (0.03% of R, 0.32% of the final balance).
        #
        # So this asserts agreement to well under a tenth of an R over a two-year window. If it starts
        # failing, the cause is a real divergence in the swap model — do NOT widen it.
        (["swap"], {"swap": PROFILES["vantage_demo"].swap}, 0.05, 5e-3),
    ],
)
def test_repricing_reproduces_a_real_charged_replay(layers, kwargs, tolerance, equity_rel):
    """The claim, tested the only way that means anything: replay it charged for real, then rebuild
    that replay from the FREE run's stored curve and demand they agree.

    Tolerance is 1e-5 R for the EXACT layers because `output.py` rounds stored prices to 5dp — the
    re-price sees exactly what the page sees, so this pins that the rounding is all that separates
    them. `swap` carries its own measured bound and its own equity bound; see the parametrize block.

    ⚠ `equity_rel` is separate from `tolerance` on purpose. A tiny R error COMPOUNDS through the
    balance re-walk — swap's 0.0376R lands as 0.32% of the final balance on the full run — so one
    shared bound would either let a real R divergence through or fail the exact layers on dollars.
    """
    from backtest.output import build_equity_curve

    free = _replay()
    charged = _replay(tuple(sorted(kwargs.items())))
    curve = build_equity_curve(free.trades, initial_capital=10_000.0)

    rebuilt = reprice_curve(
        curve, profile=_profile(**kwargs), layers=layers, initial_capital=10_000.0, close_hour_ny=17
    )

    assert len(rebuilt.trades) == len(charged.trades)
    replayed_r = sum(t.r for t in charged.trades)
    assert rebuilt.sum_r == pytest.approx(replayed_r, abs=tolerance)

    # Equity is the number the page actually shows, so it gets its own assertion — a curve can
    # match on R and still diverge in dollars if the sizing fraction is modelled instead of read.
    #
    # ⚠ Compared against the CLOSED-TRADE balance, not `execution.equity`. A window can end with a
    # position still open, and its entry-side charge has already hit the account while no closed
    # trade accounts for it — $6.40 adrift on this window. The equity CURVE has one point per
    # closed trade and so does the re-price, which makes this the like-for-like comparison; using
    # the raw balance would fail the re-pricer for reproducing exactly what it is asked to.
    closed_balance = 10_000.0 + sum(t.pnl_usd for t in charged.trades)
    assert rebuilt.final_equity == pytest.approx(closed_balance, rel=equity_rel)


@pytest.mark.skipif(not _CACHE.exists(), reason="bar cache absent (git-ignored)")
def test_the_sizing_fraction_is_a_property_of_the_trade_not_of_the_cost_layer():
    """The load-bearing assumption behind the dollars. Six of the reference run's 161 trades size
    at 5.9%-9.8% instead of the configured 10%, because a resting limit is SIZED WHEN PLACED and
    the balance moves before it fills. Re-pricing reads that fraction off the stored run; this pins
    that reading it is legitimate, i.e. that charging a cost does not change it."""

    def fractions(execution):
        bal, out = 10_000.0, []
        for t in sorted(execution.trades, key=lambda x: (x.exit_ms, x.entry_ms)):
            out.append((t.stop_distance * t.qty) / bal)
            bal += t.pnl_usd
        return out

    # The same 0.22 the first reference case states, so the two share one charged replay.
    free, charged = fractions(_replay()), fractions(_replay((("spread", 0.22),)))
    assert len(free) == len(charged)
    assert all(math.isclose(a, b, rel_tol=1e-9) for a, b in zip(free, charged))
