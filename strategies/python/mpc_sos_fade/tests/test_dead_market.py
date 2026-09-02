"""`exec_min_atr_pct` — refuse a setup when the market has no range to travel into.

Why it exists: of 245 trades on run c868358c5177, 86 never reached +0.5R and cost 67.6R
between them. The one entry feature that separates them and survives a per-year check is the
volatility at the fill. Every other cut I measured — stop width, hour of day, entry kind —
looked good in aggregate and refused trades that carry the return.

Watched RED against HEAD in a scratch worktree: the config key did not exist, so the tests
failed at construction. The behavioural guarantees were then re-proved BY MUTATION, because
"the field is new" cannot tell a working gate from a present one.

🔴 The test this file exists for is `test_an_unseeded_ATR_REFUSES_rather_than_passes`. A gate
that waves through what it could not measure is the defect this repo keeps paying for: never
let "no" and "cannot ask" be the same value.
"""
from strategies.python.mpc_sos_fade.config import SosFadeConfig
from strategies.python.mpc_sos_fade.execution import Execution


def _ex(atr, **cfg_kw):
    ex = Execution(SosFadeConfig(**cfg_kw))
    ex._atr = atr
    return ex


def test_the_shipped_default_is_ON_at_the_value_that_was_CHOSEN():
    """Pins the SHIPPED value so it cannot move without somebody editing this line.

    ⚠ It landed at 0.0 (off) on 2026-08-26 and was switched ON at 0.08 the same day, once the
    run it was shipped-down to wait for had been read (Aaron's call).
    ⚠ Do NOT read 0.08 as a measured optimum. The replayed floors came back 119.0R / 127.9R /
    111.5R / 114.4R at off / 0.08 / 0.09 / 0.10, which is noise with no order to it. **What
    chose 0.08 is the DRAWDOWN column, which does hold its order** — 55.5% / 47.9% / — / 41.5%
    worst drawdown, and the smoothness measure bottoming at 0.08 (20.8% / 17.2% / — / 18.6%).
    What this test protects is that the value is DELIBERATE.
    """
    assert SosFadeConfig().exec_min_atr_pct == 0.08


def test_the_shipped_default_actually_REFUSES_a_dead_market():
    """🔴 A non-zero default is worth nothing if it does not bite, and a default that bites is
    worth nothing if nobody can see where the line is.

    ATR 1.60 on price 4000 is 0.04% — half the shipped floor — so the shipped config must refuse
    it with no kwargs at all, and a market at twice the floor must still come through.
    MUTATION: put the default back to 0.0 and the first assertion goes red.
    """
    assert _ex(atr=1.60)._market_has_range(4000.0) is False
    assert _ex(atr=6.40)._market_has_range(4000.0) is True


def test_zero_passes_everything():
    """Turning it off must not refuse one setup any earlier run took — that is what every test
    predating this gate relies on when it pins the field to 0.0."""
    ex = _ex(atr=0.01, exec_min_atr_pct=0.0)     # absurdly quiet
    assert ex._market_has_range(4000.0) is True


def test_it_refuses_a_market_quieter_than_the_floor():
    """ATR 3.20 on price 4000 = 0.08%. A 0.10% floor must refuse it."""
    ex = _ex(atr=3.20, exec_min_atr_pct=0.10)
    assert ex._market_has_range(4000.0) is False


def test_it_passes_a_market_at_or_above_the_floor():
    ex = _ex(atr=4.00, exec_min_atr_pct=0.10)      # 0.10% exactly
    assert ex._market_has_range(4000.0) is True
    ex = _ex(atr=8.00, exec_min_atr_pct=0.10)      # 0.20%
    assert ex._market_has_range(4000.0) is True


def test_an_unseeded_ATR_REFUSES_rather_than_passes():
    """🔴 THE TEST THIS FILE EXISTS FOR.

    The first 14 bars of any run cannot answer "is the market quiet". Passing there would let
    the gate's silence read as approval on exactly the bars it knows least about.

    MUTATION: `return True` on the None branch, and this goes red.
    """
    ex = _ex(atr=None, exec_min_atr_pct=0.10)
    assert ex._market_has_range(4000.0) is False


def test_it_is_INDEPENDENT_of_the_stop_distance():
    """🔴 The distinction the whole feature rests on. A dead market throws up wide stops as
    happily as tight ones, so the minimum-STOP floor cannot catch this and never could.

    Here the stop is 20.00 wide — miles clear of the 0.08%-of-price floor (3.20) — and the
    setup is still refused, because the market itself is not moving.
    """
    ex = _ex(atr=3.20, exec_min_atr_pct=0.10)      # 0.08% market, below the 0.10% floor
    assert ex._stop_clears_floor(20.00, 4000.0) is False
    off = _ex(atr=3.20)                             # same bar, gate off
    assert off._stop_clears_floor(20.00, 4000.0) is True


def test_it_gates_the_entry_path_through_the_shared_floor_check():
    """Both the 15m setup path and the re-entry go through `_stop_clears_floor`, so gating there
    is what stops a refused setup coming in through the other door. The re-entry's fill clock is
    `exec_sec_fill_tf_min` (5 minutes by default) and this test must not depend on that number.

    MUTATION: move the check out of `_stop_clears_floor` into only one call site and this
    passes while the secondary path quietly keeps trading dead markets.
    """
    ex = _ex(atr=3.20, exec_min_atr_pct=0.10)
    assert ex._stop_clears_floor(5.00, 4000.0) is False
    ex._atr = 8.00                                  # market wakes up, same stop
    assert ex._stop_clears_floor(5.00, 4000.0) is True


def test_the_PINE_side_ships_the_SAME_value_and_still_gates_both_entries():
    """🔴 THIS TEST GOT WEAKER THE DAY THE GATE WAS SWITCHED ON, AND SAYING SO IS THE POINT.

    While both sides shipped at 0.0 the gate could not fire, so "the two agree" was true by
    construction and this file was a cheap way to keep it that way. At 0.08 the gate fires on
    real bars in the SHIPPED configuration, and whether the two implementations then make the
    same decision is a question only `compare_strategy.py` on a fresh export can answer.

    So read this for exactly what it checks: the two DEFAULTS are the same number, and the Pine
    gates BOTH entry placements. It is the floor under the claim, never the claim itself, and it
    would pass happily against a Pine whose comparison ran the wrong way round.

    ⚠ Until an export lands carrying `cfg_min_atr`, the shipped configuration is one the parity
    gate has never verified. Rule 22 is not satisfied by this file.

    MUTATION: move either default, or drop either `f_marketHasRange` from the entry conditions,
    and this goes red.
    """
    from pathlib import Path

    pine = (Path(__file__).resolve().parents[4]
            / "strategies" / "tradingview" / "mpc_strategy.pine").read_text()

    assert 'execMinAtrPct = input.float(0.08,' in pine, "Pine default no longer matches Python's"
    assert SosFadeConfig().exec_min_atr_pct == 0.08, "Python default no longer matches Pine's"
    # Both entry placements, long and short, must carry the gate — one of them is how a setup
    # the strategy means to refuse gets in through the other door.
    assert pine.count("and f_marketHasRange(") == 2, "expected the gate on exactly both entries"
    assert "f_marketHasRange(longEdge)" in pine
    assert "f_marketHasRange(shortEdge)" in pine
