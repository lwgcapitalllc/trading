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


# ── the per-lot detail (2026-08-19) ───────────────────────────────────────────
#
# A lot is a POSITION: it has its own entry, runs its own distance, goes its own distance against,
# and comes off somewhere. The three keys above say only that one was BOUGHT, which is why the
# chart could draw a dotted `Add` line and nothing else. These carry the rest through so the panel
# can draw a lot the way it draws a trade.


def _lot(**over):
    lot = {
        "price": 102.5,
        "ms": 1_500,
        "qty": 3.0,
        "mfe_price": 104.0,
        "mae_price": 101.0,
        "exit_price": 103.0,
        "exit_ms": 1_800,
        "exit_reason": "L-ATP",
        "pnl_usd": 1.5,
    }
    lot.update(over)
    return lot


def test_a_lots_own_excursion_and_exit_reach_the_chart():
    """Renamed to the panel's camelCase on the way through, because the chart defines this shape.

    Watched RED by mutation: dropping the per-lot passthrough block from `_build_trades` leaves the
    three original keys and this fails naming every missing one."""
    trades = _build_trades(_curve(_point(0.0, 0.0, adds=[_lot()])), _CANDLES)
    assert trades[-1]["adds"] == [
        {
            "price": 102.5,
            "ms": 1500,
            "qty": 3.0,
            "mfePrice": 104.0,
            "maePrice": 101.0,
            "exitPrice": 103.0,
            "exitTime": 1800,
            "exitReason": "L-ATP",
            "pnl": 1.5,
        }
    ]


def test_a_lot_that_recorded_nothing_past_its_fill_gains_no_zeroes():
    """🔴 THE RULE THIS FILE EXISTS TO KEEP: absent must not become measured.

    A run stored before the strategy recorded per-lot detail carries `{price, ms, qty}` and nothing
    backfills it. Defaulting the rest to 0.0 would put the lot's exit at price ZERO and its
    drawdown at zero — a chart drawing a box from 102.5 down to 0.00, stated with the same
    confidence as a real one. The honest output is the three keys it actually has, which is what
    makes the panel's `Scale-in detail` row vanish for that run instead of lying in it.

    This is the same shape as the bar cache recording a REQUESTED range as received, and as the
    live bot reading an empty bar frame as a quiet market.

    Watched RED by mutation: replacing the `isinstance(...)` guards with `a.get(src) or 0.0` makes
    every one of these keys appear at 0.0 and this goes red."""
    trades = _build_trades(
        _curve(_point(0.0, 0.0, adds=[{"price": 102.5, "ms": 1_500, "qty": 3.0}])), _CANDLES
    )
    assert trades[-1]["adds"] == [{"price": 102.5, "ms": 1500, "qty": 3.0}]


def test_a_lot_nothing_closed_keeps_its_excursion_and_omits_the_exit():
    """The two halves are independent: a lot can have been MEASURED all the way and still never
    have been closed. Reporting `exitPrice: 0.0` there would say it came off at zero; omitting it
    says nothing closed it, which is true and is what the panel needs to skip drawing a box."""
    lot = _lot()
    del lot["exit_price"], lot["exit_ms"], lot["exit_reason"], lot["pnl_usd"]
    got = _build_trades(_curve(_point(0.0, 0.0, adds=[lot])), _CANDLES)[-1]["adds"][0]
    assert got["mfePrice"] == 104.0 and got["maePrice"] == 101.0
    assert not {"exitPrice", "exitTime", "exitReason", "pnl"} & set(got)
