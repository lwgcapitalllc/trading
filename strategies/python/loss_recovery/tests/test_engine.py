"""Tests for loss_recovery.

RULE 12 — every test in this file was watched RED before it was watched green, and the mutation
that reddens it is named in the test's own docstring. A test whose red state nobody has seen is
a test that agrees with the bug.

RULE 13 — the price fixture is 2,400 REAL XAUUSD M15 bars (`fixture_xauusd_m15.csv`), not a
synthetic path. That is not laziness, it is the rule: hand-built ramps and sawtooths were tried
first and the canonical structure engine emitted **zero** events on all of them, because pivot
seeding plus 3-candle pullback confirmation needs price action a straight line does not contain.
A fixture the engine cannot read would have let every assertion below pass vacuously on an empty
list. The slice is committed so the tests do not depend on a bar cache being present, and it is
known to contain 8 external CHoCHs at bars 134/436/527/588/628/783/1065/2084.
"""

from __future__ import annotations

import sys
from dataclasses import dataclass
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

_ROOT = Path(__file__).resolve().parents[3]
for _p in (str(_ROOT), str(_ROOT / "engines"), str(_ROOT / "strategies" / "python")):
    if _p not in sys.path:
        sys.path.insert(0, _p)

from loss_recovery import LossRecoveryEngine, RecoveryConfig  # noqa: E402
from loss_recovery.engine import _bars_per_day  # noqa: E402


@dataclass
class FakeLoss:
    """Satisfies the LossEvent protocol and nothing more — see rule 13 in the module docstring."""

    dir: int
    exit_index: int
    r: float


_FIXTURE = Path(__file__).with_name("fixture_xauusd_m15.csv")

# Bars the fixture is known to print an external CHoCH on, and which way. Hardcoded so a change
# in the structure engine reddens these tests LOUDLY rather than quietly moving what they assert.
_BULL_CHOCH_BARS = (436, 588, 783, 2084)
_BEAR_CHOCH_BARS = (134, 527, 628, 1065)

# The break-leg FAR end the canonical engine reports at each of those bars — i.e. where the stop
# belongs. Hardcoded from a real run so that swapping `bull_bos_low` for `bull_bos_price` (the
# level that BROKE, a different price on a different bar) is caught by value rather than by a
# sign check that both would pass.
_EXPECTED_STOP = {
    436: 2018.16,
    588: 2023.86,
    783: 2013.32,
    2084: 2001.80,
    134: 2067.46,
    527: 2041.92,
    628: 2040.20,
    1065: 2062.19,
}


def real_bars():
    df = pd.read_csv(_FIXTURE, index_col=0, parse_dates=True)
    df.index = pd.DatetimeIndex(df.index)
    return df


def flat_bars(n=400, price=100.0):
    """A dead-flat path. The canonical engine cannot print anything on it — which is the point:
    it is the 'no signal' fixture, and it is honest about being one."""
    idx = pd.date_range("2024-01-01", periods=n, freq="15min", tz="UTC")
    return pd.DataFrame({"open": price, "high": price, "low": price, "close": price}, index=idx)


# ── config refusals ──────────────────────────────────────────────────────────────────────
def test_lock_to_beyond_lock_at_is_refused():
    """RED by deleting the lock_to_r/lock_at_r check in RecoveryConfig.__post_init__.

    A stop placed at +2R the moment price touches +1R is a stop on the far side of a price the
    trade has not reached — it would fill instantly at a price the market never offered, and the
    backtest would print free money.
    """
    with pytest.raises(ValueError, match="cannot exceed"):
        RecoveryConfig(lock_at_r=1.0, lock_to_r=2.0)


def test_horizon_below_time_stop_is_refused():
    """RED by deleting the horizon_days/max_days check.

    If the walk gives up before the time cap, the time stop can never fire and two limits that
    mean different things silently become one — the reader then believes a 30-day cap is being
    enforced by a number that is never reached.
    """
    with pytest.raises(ValueError, match="below max_days"):
        RecoveryConfig(max_days=90.0, horizon_days=30.0)


def test_zero_risk_fraction_is_refused():
    """RED by deleting the risk_fraction check. Zero size is not a setting, it is `enabled=False`
    wearing a disguise, and a journal of `scaled_r == 0.0` reads as "traded and broke even"."""
    with pytest.raises(ValueError, match="must be positive"):
        RecoveryConfig(risk_fraction=0.0)


# ── the gate ─────────────────────────────────────────────────────────────────────────────
def test_disabled_by_default_returns_nothing():
    """RED by defaulting `enabled` to True. This package is unproven and ungated; importing it
    must not be able to change what anything trades."""
    got = LossRecoveryEngine().run(real_bars(), [FakeLoss(dir=-1, exit_index=300, r=-1.0)])
    assert got == []


def test_scratches_do_not_arm():
    """RED by changing the filter to `t.r < 0`.

    A -0.05R scratch is not a loss to win back. Counting it would inflate the population with
    trades that had nothing to recover, and every per-trade figure would then be diluted by
    them rather than wrong in a way anybody would notice.
    """
    cfg = RecoveryConfig(enabled=True, scratch_r=0.15)
    eng = LossRecoveryEngine(cfg)
    assert eng.run(real_bars(), [FakeLoss(dir=-1, exit_index=300, r=-0.10)]) == []


def test_a_loss_with_no_choch_produces_no_trade_and_shows_as_pending():
    """RED by making `run` fall back to a market entry when no CHoCH is found.

    'No signal' and 'signal, then a losing trade' must never be the same outcome — that is the
    repo's standing rule about a value that means two things. `pending()` is how the difference
    stays visible.
    """
    bars = flat_bars()  # dead flat: the structure engine can never print a CHoCH
    cfg = RecoveryConfig(enabled=True)
    eng = LossRecoveryEngine(cfg)
    loss = FakeLoss(dir=-1, exit_index=50, r=-1.0)
    assert eng.run(bars, [loss]) == []
    assert [p.trigger_index for p in eng.pending(bars, [loss])] == [50]


# ── the money arithmetic ─────────────────────────────────────────────────────────────────
def _one_trade(cfg):
    """Every counter-LONG the fixture can produce: one losing SHORT parked just before each known
    bull CHoCH, so the engine has something to arm on and a signal to find."""
    bars = real_bars()
    losses = [FakeLoss(dir=-1, exit_index=b - 30, r=-1.0) for b in _BULL_CHOCH_BARS]
    return bars, LossRecoveryEngine(cfg).run(bars, losses)


def test_scaled_r_is_r_times_risk_fraction():
    """RED by returning `scaled_r=r` in engine.run.

    These are two different units and a journal adds up the second one. A recovery trade booked
    at full size when it was taken at a quarter would overstate its contribution 4x — the same
    class of unit error as handing MT5 ounces where it wanted lots.
    """
    cfg = RecoveryConfig(enabled=True, risk_fraction=0.25)
    _, got = _one_trade(cfg)
    assert got, "fixture produced no recovery trade; the test cannot say anything"
    for t in got:
        assert t.scaled_r == pytest.approx(t.r * 0.25)


def test_stop_sits_on_the_far_end_of_the_break_leg_not_inside_the_move():
    """RED by using `bull_bos_price` (the level that broke) instead of `bull_bos_low`.

    The two differ by the whole impulse leg. Swapping them gives a much tighter stop, which makes
    every R look bigger while describing a trade nobody placed.

    ⚠ This asserts the stop PRICE, not just its sign. An earlier version checked only that the
    stop sat on the correct side of entry — which the wrong level also satisfies, so the test
    passed against its own bug. Caught by mutation, not by review.
    """
    cfg = RecoveryConfig(enabled=True)
    _, got = _one_trade(cfg)
    assert len(got) == len(_BULL_CHOCH_BARS)
    for t in got:
        assert (t.entry_price - t.stop_price) * t.direction > 0
        assert t.risk == pytest.approx(abs(t.entry_price - t.stop_price))
        assert t.stop_price == pytest.approx(_EXPECTED_STOP[t.signal_index], abs=0.01)


def test_locking_caps_the_loss_at_the_locked_level():
    """RED by never re-assigning `stop` when `fav >= lock_at_r`.

    This is the load-bearing line of the whole rule: once the trade has paid the loss back, it
    may not give it away again. If it armed, the outcome cannot be a full -1R.

    ⚠ It runs the counter-SHORT set on purpose. The counter-LONG set contains NO trade that
    reaches +1R, so the earlier version of this test looped over four trades, entered the `if`
    zero times and passed while asserting nothing. The explicit `assert locked` below is what
    stops that recurring.

    ⚠ Trailing is switched OFF here, and that is also a mutation finding rather than a style
    choice. With it on, deleting the lock made the one arming trade book MORE (+1.457 instead of
    +1.000) because the swing trail rescued it — so the test passed against its own bug. Isolating
    the lock is the only way this assertion can speak about the lock.
    """
    cfg = RecoveryConfig(enabled=True, lock_at_r=1.0, lock_to_r=1.0, trail_swings=False)
    bars = real_bars()
    losses = [FakeLoss(dir=1, exit_index=b - 30, r=-1.0) for b in _BEAR_CHOCH_BARS]
    got = LossRecoveryEngine(cfg).run(bars, losses)
    locked = [t for t in got if t.locked]
    assert locked, "no trade armed; this test would assert nothing"
    for t in locked:
        assert t.r >= 1.0 - 1e-9, f"armed at +1R and still booked {t.r}"


def test_a_bar_that_hits_both_the_stop_and_the_lock_books_the_stop():
    """RED by moving the arm/track block ABOVE the stop check in `_manage`.

    This drives `_manage` directly with a two-bar frame whose second bar spans the stop AND +1R,
    because that is the only shape where the ordering is observable at all — and proving that was
    the point. On 2,400 real bars the reordered walk returns BYTE-IDENTICAL results, since no bar
    there both arms and stops. A test asserting the ordering against that fixture could never have
    gone red, and would have been decoration.

    ⚠ A synthetic frame is legitimate HERE and nowhere else in this file: `_manage` runs no
    structure detection, so this is the production code path on chosen prices rather than a double
    that can answer more than the real thing (rule 13).

    Getting it wrong pays you for a bar that stopped you out, which is the most flattering
    arithmetic error a bar-replay can make.
    """
    idx = pd.date_range("2024-01-01", periods=2, freq="15min", tz="UTC")
    # long from 100, stop 99 (1R = 1.0). Bar 2 trades 98 → 102: through the stop AND past +1R.
    bars = pd.DataFrame(
        {
            "open": [100.0, 100.0],
            "high": [100.2, 102.0],
            "low": [99.8, 98.0],
            "close": [100.0, 101.0],
        },
        index=idx,
    )
    eng = LossRecoveryEngine(RecoveryConfig(enabled=True))
    exit_i, exit_px, r, reason, locked, mfe = eng._manage(
        bars, 0, 1, 100.0, 99.0, {}, {}, {}, np.zeros(len(bars)), 96.0
    )
    assert reason == "stop", f"a bar through the stop booked {reason!r}"
    assert r == pytest.approx(-1.0)
    assert not locked


def test_no_trade_books_more_than_its_best_price_or_exits_by_a_route_that_does_not_exist():
    """RED by giving `_manage` a take-profit branch.

    This rule has NO target — it locks and trails. Any exit reason outside the closed set is a
    code path nobody designed, and no trade may book more R than the best price it ever saw.
    """
    cfg = RecoveryConfig(enabled=True)
    _, got = _one_trade(cfg)
    assert got
    for t in got:
        assert t.r >= -1.0 - 1e-9
        assert t.exit_reason in {
            "stop",
            "soft",
            "be",
            "locked",
            "trail",
            "choch",
            "time",
            "horizon",
        }
        assert t.r <= t.max_favourable_r + 1e-9


def test_max_favourable_is_never_below_the_booked_result():
    """RED by initialising `mfe` after the stop check instead of tracking every bar.

    A trade cannot book more than the best price it ever saw.

    ⚠ `mfe >= r` alone is vacuous on this fixture, where every counter-long books exactly -1R and
    any non-negative mfe satisfies it. The assertion with teeth is that mfe is STRICTLY positive:
    a mutation that only tracks excursion after arming leaves every unarmed trade reporting 0.0,
    and a trade that moved in your favour at all cannot have peaked at zero.
    """
    cfg = RecoveryConfig(enabled=True)
    _, got = _one_trade(cfg)
    assert got
    for t in got:
        assert t.max_favourable_r >= t.r - 1e-9
        assert t.max_favourable_r > 0.0, "excursion is not being tracked before the stop arms"


def test_time_stop_bounds_the_hold():
    """RED by dropping `time_cap` from the `end` calculation.

    Without it a flat trade sits open for the full horizon. That is not a cosmetic difference:
    the version of this rule with no time bound paid -8.66R of overnight swap on a single trade
    that made +1.25R.
    """
    cfg = RecoveryConfig(enabled=True, max_days=2.0, horizon_days=90.0)
    bars, got = _one_trade(cfg)
    assert got
    per_day = _bars_per_day(bars)
    for t in got:
        assert t.bars_held <= int(round(2.0 * per_day)) + 1


def test_shorts_are_included_by_default_and_excludable():
    """RED by hardcoding `both_directions` True in run().

    Excluding shorts is the one FITTED choice available here, so it has to be a visible switch a
    reader can see set rather than a silent default nobody knows they are relying on.
    """
    bars = real_bars()
    # a LONG lost -> wants a counter-SHORT, so park it just before a known bear CHoCH
    loss = FakeLoss(dir=1, exit_index=_BEAR_CHOCH_BARS[1] - 30, r=-1.0)
    both = LossRecoveryEngine(RecoveryConfig(enabled=True, both_directions=True)).run(bars, [loss])
    longs_only = LossRecoveryEngine(RecoveryConfig(enabled=True, both_directions=False)).run(
        bars, [loss]
    )
    assert longs_only == []
    assert all(t.direction == -1 for t in both)


def test_two_runs_on_one_instance_agree():
    """RED by memoising `_replay_structure` on `self` — the "this pass is slow, cache it" bug.

    ⚠ Two weaker versions of this test were written first and BOTH were vacuous, which is worth
    recording. Re-running the same frame twice cannot fail, because the canonical StructureEngine
    tolerates being re-fed from index 0. Running real bars then FLAT bars cannot fail either — a
    stale signal on a flat frame is refused downstream by the `risk <= 0` guard, so a second
    guard masks the bug. What bites is two DIFFERENT real slices: the stale CHoCHs from slice A
    land on real, tradeable prices in slice B and quietly produce trades that were never signalled.
    """
    cfg = RecoveryConfig(enabled=True)
    bars = real_bars()
    a, b = (
        bars.iloc[:1200],
        bars.iloc[1200:].reset_index(drop=False).set_index(bars.index.name or "index"),
    )
    b = bars.iloc[1200:]
    loss_a = [FakeLoss(dir=-1, exit_index=100, r=-1.0)]
    loss_b = [FakeLoss(dir=-1, exit_index=100, r=-1.0)]

    shared = LossRecoveryEngine(cfg)
    shared.run(a, loss_a)  # warm it up on a different frame
    got_shared = shared.run(b, loss_b)
    got_fresh = LossRecoveryEngine(cfg).run(b, loss_b)
    assert got_fresh, "second slice produced nothing; the test cannot say anything"
    assert got_shared == got_fresh


def test_bars_per_day_is_calendar_not_session():
    """RED by computing bars-per-day from the median inter-bar gap.

    The gap says 96 bars/day for M15 and the calendar says fewer, because gold closes daily and
    at weekends. `max_days` bounds SWAP, which is charged on calendar nights, so the session
    figure would let a trade run about half as long again as the cap claims.
    """
    idx = pd.date_range("2024-01-01", periods=96 * 14, freq="15min", tz="UTC")
    weekdays = idx[idx.dayofweek < 5]  # two weekends removed from a fortnight
    bars = pd.DataFrame({"open": 1.0, "high": 1.0, "low": 1.0, "close": 1.0}, index=weekdays)
    assert _bars_per_day(bars) < 96.0
    assert _bars_per_day(real_bars()) < 96.0


# ── the tighter exits (2026-08-19) ───────────────────────────────────────────────────────────
# Aaron's question was "the structural stop is nearly as far as the whole move — can I get out
# for a small loss instead". These four pin the answer's mechanics; whether it PAYS is measured
# by `backtest/tools/recovery_report.py --soft-curve`, not asserted here.


def test_a_soft_stop_books_a_fraction_of_r_and_never_a_full_one():
    """RED by dropping the `soft_stop_r` branch that seeds `stop` in `_manage`.

    Without it the working stop is the structural one again and the losers book −1.00R, which is
    the entire thing this knob exists to stop.
    """
    plain = RecoveryConfig(enabled=True)
    tight = RecoveryConfig(enabled=True, soft_stop_r=0.3)
    _, base = _one_trade(plain)
    _, cut = _one_trade(tight)
    assert base and cut, "fixture produced no recovery trade; the test cannot say anything"
    assert any(t.r < -0.3 for t in base), (
        "no trade in the plain run loses more than 0.3R, so a 0.3R cut cannot be observed and "
        "this test would pass against a knob that does nothing"
    )
    for t in cut:
        assert t.r >= -0.3 - 1e-9, f"a 0.3R cut booked {t.r:.3f}R"


def test_a_soft_stop_does_not_move_the_number_the_trade_was_sized_on():
    """RED by recomputing `risk` from the soft stop (`risk = abs(entry - stop)` after seeding).

    🔴 This is the load-bearing one and it is the thing that makes the knob honest. A position is
    sized off its stop distance, so re-deriving 1R from a nearer stop would buy a bigger position
    and the loss in money would be UNCHANGED — the exact opposite of what was asked for. 1R must
    stay the structural distance; only the willingness to sit through it changes.
    """
    _, base = _one_trade(RecoveryConfig(enabled=True))
    _, cut = _one_trade(RecoveryConfig(enabled=True, soft_stop_r=0.3))
    assert len(base) == len(cut), "a soft stop changed which trades were TAKEN; it is an exit only"
    for a, b in zip(base, cut):
        assert a.entry_index == b.entry_index
        assert b.stop_price == pytest.approx(a.stop_price)
        assert b.risk == pytest.approx(a.risk)


def test_structural_invalidation_exits_at_the_next_bars_open():
    """RED by deleting the `cut_at_open` early return in `_manage`.

    The CHoCH is only known when its bar CLOSES, so the fill is the next open. Acting on the same
    bar's close would be reading a decision off the bar it was made on — the look-ahead this repo
    has already paid for once in `trigger_edge.py`.
    """
    idx = pd.date_range("2024-01-01", periods=3, freq="15min", tz="UTC")
    bars = pd.DataFrame(
        {
            "open": [100.0, 100.3, 100.3],
            "high": [100.5, 100.4, 100.4],
            "low": [99.5, 100.1, 100.1],
            "close": [100.2, 100.2, 100.2],
        },
        index=idx,
    )
    cfg = RecoveryConfig(enabled=True, invalidate_on_choch=True)
    eng = LossRecoveryEngine(cfg)
    # long from 100, stop 99 (1R = 1.0). A bear CHoCH closes on bar 0.
    exit_i, exit_px, r, reason, _, _ = eng._manage(
        bars, 0, 1, 100.0, 99.0, {}, {}, {0: -1}, np.zeros(len(bars)), 96.0
    )
    assert reason == "choch", f"an opposing CHoCH booked {reason!r}"
    assert exit_i == 1 and exit_px == pytest.approx(100.3)
    assert r == pytest.approx(0.3)


def test_the_early_step_moves_the_stop_before_the_lock_does():
    """RED by deleting the `be_at_r` block in `_manage`.

    Without it the stop sits at its opening level until `lock_at_r` fires, which on a structural
    stop is a long way and — measured — several days. This bar reaches +0.6R and comes back; the
    step is the only thing that can be out at breakeven rather than still carrying full risk.
    """
    idx = pd.date_range("2024-01-01", periods=2, freq="15min", tz="UTC")
    bars = pd.DataFrame(
        {
            "open": [100.0, 100.4],
            "high": [100.6, 100.4],
            "low": [99.9, 99.5],
            "close": [100.5, 99.6],
        },
        index=idx,
    )
    cfg = RecoveryConfig(enabled=True, be_at_r=0.5, be_to_r=0.0, trail_swings=False)
    exit_i, exit_px, r, reason, locked, _ = LossRecoveryEngine(cfg)._manage(
        bars, 0, 1, 100.0, 99.0, {}, {}, {}, np.zeros(len(bars)), 96.0
    )
    assert reason == "be", f"the early step booked {reason!r}"
    assert exit_i == 1 and exit_px == pytest.approx(100.0)
    assert r == pytest.approx(0.0)
    assert not locked, "the trade never reached +1R and must not report itself locked"


def test_an_unreachable_soft_stop_and_a_backwards_early_step_are_refused():
    """RED by deleting either validation in `RecoveryConfig.__post_init__`.

    A `soft_stop_r` above 1 sits BEYOND the structural stop, so it can never fire — a knob that
    reads as set and does nothing, which is worse than one that is off. `be_to_r > be_at_r` puts
    the stop past a price the trade has not reached.
    """
    with pytest.raises(ValueError, match="soft_stop_r"):
        RecoveryConfig(soft_stop_r=1.5)
    with pytest.raises(ValueError, match="soft_stop_r"):
        RecoveryConfig(soft_stop_r=0.0)
    with pytest.raises(ValueError, match="be_to_r"):
        RecoveryConfig(be_at_r=0.5, be_to_r=0.75)
    with pytest.raises(ValueError, match="be_at_r"):
        RecoveryConfig(be_at_r=1.5, be_to_r=0.5)


# ── where the stop GOES (2026-08-19) ─────────────────────────────────────────────────────────
# Aaron's idea: put the recovery's stop on the LOSING trade's entry. Much nearer, so the same
# 25% of risk buys a bigger position and +1R arrives sooner. These pin the mechanics; whether it
# PAYS is measured by `recovery_report.py --stops`, not asserted here.


@dataclass
class FakeLossWithEntry:
    """A LossEvent that also knows where the primary got in."""

    dir: int
    exit_index: int
    r: float
    entry_price: float


def _losses_with_entry(bars, offset):
    """One losing SHORT before each known bull CHoCH, its entry placed `offset` from the bar's
    low — below the eventual counter-long fill when negative, above it when positive."""
    return [
        FakeLossWithEntry(
            dir=-1,
            exit_index=b - 30,
            r=-1.0,
            entry_price=float(bars["low"].iloc[b - 30]) + offset,
        )
        for b in _BULL_CHOCH_BARS
    ]


def test_the_loss_entry_stop_is_the_primarys_entry_and_not_the_break_leg():
    """RED by leaving `stop_price = break_leg_far_end` in `run` regardless of `stop_mode`.

    The two are ~4x apart (measured: median $38.18 against $16.05), so a mode that silently kept
    the structural stop would report the shipped rule under a new name.
    """
    bars = real_bars()
    losses = _losses_with_entry(bars, -50.0)
    cfg = RecoveryConfig(enabled=True, stop_mode="loss_entry")
    got = LossRecoveryEngine(cfg).run(bars, losses)
    assert got, "fixture produced no recovery trade; the test cannot say anything"
    wanted = {ls.exit_index: ls.entry_price for ls in losses}
    for t in got:
        assert t.stop_price == pytest.approx(wanted[t.trigger_index])
        assert t.risk == pytest.approx(abs(t.entry_price - t.stop_price))


def test_a_loss_event_with_no_entry_price_is_refused_never_given_the_structural_stop():
    """RED by `getattr(loss, "entry_price", break_leg_far_end)` in `run`.

    🔴 The fallback shape this repo keeps paying for: *cannot ask* and *the answer is the break
    leg* becoming the same value. It would report a rule nobody ran, on a stop 4x the size, and
    nothing would error.
    """
    bars = real_bars()
    plain = [FakeLoss(dir=-1, exit_index=b - 30, r=-1.0) for b in _BULL_CHOCH_BARS]
    eng = LossRecoveryEngine(RecoveryConfig(enabled=True, stop_mode="loss_entry"))
    with pytest.raises(AttributeError, match="entry_price"):
        eng.run(bars, plain)


def test_a_stop_on_the_wrong_side_is_counted_as_refused_and_not_as_pending():
    """RED by folding `refused` into `pending`, or by returning [] from it.

    ⚠ Two ways to take no trade that mean opposite things. `pending` = the CHoCH never came, so
    the market did not offer the setup. `refused` = it came and the stop was unusable, which is a
    fact about THIS config. A count of trades alone cannot tell them apart, and under
    `loss_entry` it is `refused` that moves.
    """
    bars = real_bars()
    # Entries placed ABOVE the eventual counter-long fill: a long cannot rest its stop up there.
    losses = _losses_with_entry(bars, +500.0)
    eng = LossRecoveryEngine(RecoveryConfig(enabled=True, stop_mode="loss_entry"))
    assert eng.run(bars, losses) == [], "an upside-down stop produced a trade"
    assert len(eng.refused(bars, losses)) == len(_BULL_CHOCH_BARS)
    assert eng.pending(bars, losses) == [], "a refused stop is not a missing signal"


def test_the_percent_ratchet_moves_a_locked_stop_past_where_the_lock_put_it():
    """RED by deleting the `trail_pct` block in `_manage`.

    Without it the stop stays at `lock_to_r` and this bar books exactly +1.000R. ⚠ The step is a
    percent of PRICE, so it is NOT in R — see the config warning and the `mpc_bleg` trail that was
    inert for months because one step exceeded the whole risk.
    """
    idx = pd.date_range("2024-01-01", periods=2, freq="15min", tz="UTC")
    bars = pd.DataFrame(
        {
            "open": [100.0, 101.4],
            "high": [101.5, 101.4],
            "low": [99.5, 101.0],
            "close": [101.4, 101.1],
        },
        index=idx,
    )
    cfg = RecoveryConfig(enabled=True, trail_pct=0.1, trail_swings=False)
    _, exit_px, r, reason, locked, _ = LossRecoveryEngine(cfg)._manage(
        bars, 0, 1, 100.0, 99.0, {}, {}, {}, np.zeros(len(bars)), 96.0
    )
    assert locked and reason == "trail", f"the ratchet booked {reason!r}"
    assert exit_px == pytest.approx(101.4 * 0.999)
    assert r > 1.0, f"the ratchet left the stop at the lock ({r:.4f}R)"


def test_an_unknown_stop_mode_and_a_negative_ratchet_are_refused():
    """RED by deleting either validation in `RecoveryConfig.__post_init__`.

    An unrecognised `stop_mode` string would otherwise fall through to the structural branch and
    read as a setting that applied — a typo that silently selects the default.
    """
    with pytest.raises(ValueError, match="stop_mode"):
        RecoveryConfig(stop_mode="loss-entry")
    with pytest.raises(ValueError, match="trail_pct"):
        RecoveryConfig(trail_pct=-0.5)


# ── the stop search (2026-08-19) ─────────────────────────────────────────────────────────────
# Six stop placements and two more ways to trail, built so the search could be run at all rather
# than argued. `recovery_report.py --search` scores them; these pin what each one DOES.


def test_each_stop_mode_places_the_stop_where_it_says_and_they_all_differ():
    """RED by returning `break_leg_far_end` from any branch of `_stop_for`.

    🔴 The failure this guards is silent: a mode that fell through to the structural stop would
    produce a full, plausible result table with several rows secretly measuring one rule. The
    distances here are 7x apart, so the assertion is not delicate.
    """
    bars = real_bars()
    losses = [FakeLoss(dir=-1, exit_index=b - 30, r=-1.0) for b in _BULL_CHOCH_BARS]
    got = {}
    for mode in ("structural", "leg_frac", "swing", "signal_bar", "atr"):
        cfg = RecoveryConfig(enabled=True, stop_mode=mode)
        rs = LossRecoveryEngine(cfg).run(bars, losses)
        assert rs, f"{mode} produced no trade; it cannot be compared"
        got[mode] = {t.signal_index: t.stop_price for t in rs}

    common = set.intersection(*(set(v) for v in got.values()))
    assert common, "no signal is shared by every mode; the comparison is empty"
    for sig in common:
        assert len({round(got[m][sig], 6) for m in got}) == len(got), (
            f"two stop modes placed the same stop at signal {sig}: "
            f"{ {m: round(got[m][sig], 4) for m in got} }"
        )

    for sig in common:
        # leg_frac 0.5 sits exactly halfway from the fill to the structural stop.
        t = next(
            t
            for t in LossRecoveryEngine(RecoveryConfig(enabled=True)).run(bars, losses)
            if t.signal_index == sig
        )
        assert got["leg_frac"][sig] == pytest.approx(
            t.entry_price - 0.5 * (t.entry_price - t.stop_price)
        )
        # the CHoCH bar's low, minus its pad
        assert got["signal_bar"][sig] < float(bars["low"].iloc[sig])


def test_a_stop_mode_that_cannot_find_its_level_refuses_rather_than_borrowing_one():
    """RED by `return break_leg_far_end` in place of `return None` in `_stop_for`.

    ⚠ **This test replaced a VACUOUS one and the replacement is the lesson.** The first version
    ran `swing` over the real fixture and compared its stops to the structural run — but every
    signal in that fixture HAS a usable swing, so the refusal branch was never reached and the
    mutation could not be observed. It passed against its own bug. The branch is only testable by
    handing the mode a book with nothing in it, which is what this does.

    `swing` needs a confirmed swing on the protective side of the fill and there is not always
    one. Borrowing the structural stop would report a 4x wider trade inside a swing-stop row.
    """
    bars = real_bars()
    eng = LossRecoveryEngine(RecoveryConfig(enabled=True, stop_mode="swing"))
    atr = np.full(len(bars), 1.0)
    assert eng._stop_for(None, bars, atr, {}, {}, 1, 200, 100.0, 90.0) is None, (
        "an empty swing book must refuse, not fall back to the break leg"
    )
    # and with a usable level it does place one, so the None above is the branch and not a stub
    assert eng._stop_for(None, bars, atr, {50: 98.0}, {}, 1, 200, 100.0, 90.0) == pytest.approx(
        98.0 - 0.1
    )
    # a level on the WRONG side of the fill is not a stop for a long, and is also refused
    assert eng._stop_for(None, bars, atr, {50: 101.0}, {}, 1, 200, 100.0, 90.0) is None


def test_a_partial_blends_the_two_legs_and_never_books_the_runners_r_on_the_whole_position():
    """RED by dropping `banked`/`live` from `_manage`'s returns (booking `live=1.0` throughout).

    Taking half off at +1R and then stopping the rest at breakeven is +0.50R, not 0.00R and not
    +1.00R. Booking the runner's result on the full position is the scale-in accounting error
    `output.py` already carries a warning about.
    """
    idx = pd.date_range("2024-01-01", periods=3, freq="15min", tz="UTC")
    bars = pd.DataFrame(
        {
            "open": [100.0, 101.2, 100.4],
            "high": [101.3, 101.3, 100.4],
            "low": [99.5, 100.6, 99.6],
            "close": [101.2, 100.9, 99.8],
        },
        index=idx,
    )
    cfg = RecoveryConfig(
        enabled=True, partial_at_r=1.0, partial_frac=0.5, lock_to_r=0.0, trail_swings=False
    )
    _, exit_px, r, _, locked, _ = LossRecoveryEngine(cfg)._manage(
        bars, 0, 1, 100.0, 99.0, {}, {}, {}, np.zeros(len(bars)), 96.0
    )
    assert locked and exit_px == pytest.approx(100.0), "the runner should stop at breakeven"
    assert r == pytest.approx(0.5), f"half banked at +1R then a breakeven runner is +0.5R, got {r}"


def test_the_chandelier_trails_from_the_best_price_not_from_the_close():
    """RED by using `cl[j]` instead of `best` in the chandelier.

    A close-based trail gives ground back whenever price pulls in; a chandelier is a ratchet off
    the extreme. This bar prints its high, then the next closes lower — the two disagree by
    exactly that difference, which is the whole reason to prefer one.
    """
    idx = pd.date_range("2024-01-01", periods=3, freq="15min", tz="UTC")
    bars = pd.DataFrame(
        {
            "open": [100.0, 103.0, 102.0],
            "high": [103.0, 103.0, 102.0],
            "low": [99.5, 101.5, 100.0],
            "close": [102.9, 101.6, 100.5],
        },
        index=idx,
    )
    atr = np.full(len(bars), 1.0)
    cfg = RecoveryConfig(enabled=True, trail_atr_mult=1.0, trail_swings=False)
    _, exit_px, r, reason, _, _ = LossRecoveryEngine(cfg)._manage(
        bars, 0, 1, 100.0, 99.0, {}, {}, {}, atr, 96.0
    )
    assert reason == "trail"
    assert exit_px == pytest.approx(102.0), "the stop should sit 1 ATR under the 103.0 high"
    assert r == pytest.approx(2.0)


def test_the_new_stop_and_partial_knobs_refuse_nonsense():
    """RED by deleting the matching check in `RecoveryConfig.__post_init__`."""
    with pytest.raises(ValueError, match="stop_leg_frac"):
        RecoveryConfig(stop_leg_frac=1.5)
    with pytest.raises(ValueError, match="stop_atr_mult"):
        RecoveryConfig(stop_atr_mult=0.0)
    with pytest.raises(ValueError, match="partial"):
        RecoveryConfig(partial_frac=1.0)
    with pytest.raises(ValueError, match="trail_atr_mult"):
        RecoveryConfig(trail_atr_mult=-1.0)
