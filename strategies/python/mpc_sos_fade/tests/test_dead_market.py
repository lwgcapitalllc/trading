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


def test_the_shipped_default_is_OFF():
    """Pins the SHIPPED value so it cannot move without somebody editing this line.

    ⚠ It briefly stood at 0.08 on 2026-08-26 and was put back to 0.0 the same day (Aaron's call:
    ship the switch down, decide from a run). OFF is also what keeps `compare_strategy.py`
    meaningful — Pine defaults to 0.0 too, so a shipped run is byte-identical to one from before
    this gate existed.
    ⚠ Do NOT read the number as measured-optimal in either direction. The replayed floors came
    back 119.0R / 127.9R / 111.5R / 114.4R at off / 0.08 / 0.09 / 0.10, which is noise with no
    order to it; only the DRAWDOWN column held its order (55.5% / 47.9% / — / 41.5%).
    """
    assert SosFadeConfig().exec_min_atr_pct == 0.0


def test_the_shipped_default_passes_a_market_nothing_could_trade():
    """🔴 The point of shipping it OFF is that it must refuse NOTHING until somebody turns it on.

    An absurdly quiet bar — ATR 0.01 on price 4000, four ten-thousandths of a percent — has to
    come through the shipped config with no kwargs at all, or every baseline measured before
    today silently moved. MUTATION: any non-zero default and this goes red.
    """
    assert _ex(atr=0.01)._market_has_range(4000.0) is True


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


def test_the_PINE_side_ships_the_same_default_and_still_gates_both_entries():
    """🔴 The parity argument for landing this gate is "both sides default OFF", and nothing else
    in this repo can check it — `compare_strategy.py` needs a TradingView export, and an export
    can only ever show the decisions of ONE settings snapshot.

    So this reads the Pine source. It is a weak test and deliberately so: it proves the DEFAULT
    and the two CALL SITES, which is exactly the part that makes a shipped run comparable. It
    proves nothing about whether the two implementations agree once somebody turns it on — only
    a real export can, and this docstring must not be read as if it did.

    MUTATION: change the Pine default to 0.08, or drop either `f_marketHasRange` from the entry
    conditions, and this goes red.
    """
    from pathlib import Path

    pine = (Path(__file__).resolve().parents[4]
            / "indicators" / "strategies" / "mpc_strategy.pine").read_text()

    assert 'execMinAtrPct = input.float(0.0,' in pine, "Pine default moved off 0.0 (off)"
    # Both entry placements, long and short, must carry the gate — one of them is how a setup
    # the strategy means to refuse gets in through the other door.
    assert pine.count("and f_marketHasRange(") == 2, "expected the gate on exactly both entries"
    assert "f_marketHasRange(longEdge)" in pine
    assert "f_marketHasRange(shortEdge)" in pine
