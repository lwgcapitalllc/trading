"""
Tests for the two chart-spec fields that make a scaled trade READABLE: the `outcome` verdict and
the `adds` ledger. Pure over stored equity-curve points — no DB, no network, no run.

**Why either exists.** `pnl > 0` grades a trade that netted exactly $0.00 as a LOSS, and the
chart said "Lost" over a short whose exit sat plainly BELOW its entry (run 295a6ff29d21, trade
T137, 2025-11-19). Both halves of that were wrong to draw: the trade was flat, not lost, and the
lot that took the profit back — a scale-in add, bought after the entry at a better price and
closed at the same exit — appeared in no field of the record at all.

The verdict is graded in `services.metrics`, against the run's own median full loss, so the chart
and the run's `scratch_count` KPI cannot tell two stories about the same trade.
"""

from services.chart_spec import _build_trades

# One 15m candle, only so `_build_trades` has a price to fall back on. Every point below carries
# its own fills, so nothing here reads it.
_CANDLES = [{"time": 1_000, "open": 100.0, "high": 101.0, "low": 99.0, "close": 100.0}]


def _point(profit, equity, *, adds=None, entry=100.0, exit_=101.0):
    p = {
        "direction": "Long",
        "entry_ms": 1_000,
        "exit_ms": 2_000,
        "entry_price": entry,
        "exit_price": exit_,
        "profit": profit,
        "equity": equity,
    }
    if adds is not None:
        p["adds"] = adds
    return p


# A curve whose losses are all -1000 (median full loss 1000, so the scratch band is 150) on a
# cum-P&L-from-zero basis — the dollars ARE the weights, which keeps every number here hand-checkable.
def _curve(extra):
    base = [
        _point(-1000.0, -1000.0),
        _point(2000.0, 1000.0),
        _point(-1000.0, 0.0),
    ]
    return base + [extra]


# ── the verdict ───────────────────────────────────────────────────────────────


def test_a_trade_that_netted_nothing_is_a_scratch_and_not_a_loss():
    """The reported bug, at its smallest. $0.00 is not a loss, and the sign test calls it one."""
    trades = _build_trades(_curve(_point(0.0, 0.0)), _CANDLES)
    assert trades[-1]["outcome"] == "scratch"
    assert trades[-1]["pnl"] == 0.0


def test_a_full_winner_and_a_full_loser_still_grade_the_obvious_way():
    """The band must not swallow real outcomes — it is 15% of the median loss, not a shrug."""
    assert _build_trades(_curve(_point(900.0, 900.0)), _CANDLES)[-1]["outcome"] == "won"
    assert _build_trades(_curve(_point(-900.0, -900.0)), _CANDLES)[-1]["outcome"] == "lost"


def test_the_band_is_the_run_s_own_median_loss_and_not_a_typed_in_figure():
    """$149 of a $1,000 median loss is a scratch; $151 is a real loser. Same trade, same sign —
    the difference is the run's own scale, which is what makes this work on any instrument."""
    assert _build_trades(_curve(_point(-149.0, -149.0)), _CANDLES)[-1]["outcome"] == "scratch"
    assert _build_trades(_curve(_point(-151.0, -151.0)), _CANDLES)[-1]["outcome"] == "lost"


def test_a_run_with_no_losing_trade_carries_no_verdict_at_all():
    """⚠ Absent, never `won` — there is no scale to grade against, and a fabricated verdict would
    be indistinguishable from a measured one. The chart falls back to the sign of the P&L."""
    curve = [_point(500.0, 500.0), _point(700.0, 1200.0)]
    assert all("outcome" not in t for t in _build_trades(curve, _CANDLES))


# ── the add ledger ────────────────────────────────────────────────────────────


def test_the_scale_in_lots_reach_the_chart():
    """The chart draws one line per lot, and it has to: entry / exit / pnl alone describe a trade
    whose arithmetic does not close."""
    lots = [{"price": 102.5, "ms": 1_500, "qty": 3.0}]
    trades = _build_trades(_curve(_point(0.0, 0.0, adds=lots)), _CANDLES)
    assert trades[-1]["adds"] == [{"price": 102.5, "ms": 1500, "qty": 3.0}]


def test_a_trade_that_never_added_carries_no_adds_key():
    """Absent rather than `[]`: every trade of every strategy without scale-in is this one, and an
    empty list on all of them would read as a feature that ran and found nothing."""
    trades = _build_trades(_curve(_point(500.0, 500.0)), _CANDLES)
    assert "adds" not in trades[-1]
