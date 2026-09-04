"""A3 output-adapter tests — hand-computed, offline, no TradingView and no VPS.

These lock the two contracts `backtest/output.py` mirrors by hand (the lab's
equity-curve point, and `sizing_engine.RawTrade`). If the lab's shape drifts, the
round-trip test at the bottom is what fails.
"""

from __future__ import annotations

import sys
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from backtest.output import (
    build_blocked_setups,
    build_daily_pnl,
    build_engine_trades,
    build_equity_curve,
    build_kpis,
    build_missed_setups,
    build_results,
    engine_trades_csv,
)


def _ms(y, mo, d, h=12, mi=0) -> int:
    return int(datetime(y, mo, d, h, mi, tzinfo=timezone.utc).timestamp() * 1000)


@dataclass
class FakeTrade:
    """The duck-type `output` consumes — mirrors execution.Trade's public fields."""

    dir: int
    entry_index: int
    entry_price: float
    exit_index: int
    qty: float
    risk_usd: float
    pnl_usd: float
    r: float
    entry_ms: int
    exit_ms: int
    exit_price: float
    stop_distance: float
    exit_reason: str
    mfe_usd: float = 0.0
    mae_usd: float = 0.0
    costs_usd: float = 0.0
    adds: list = field(default_factory=list)


def _t(
    pnl,
    *,
    day=1,
    dir=1,
    entry=100.0,
    exit=110.0,
    qty=1.0,
    reason="L-TP1",
    stop=5.0,
    hour=12,
    mfe=0.0,
    mae=0.0,
    costs=0.0,
    adds=None,
) -> FakeTrade:
    return FakeTrade(
        dir=dir,
        entry_index=0,
        entry_price=entry,
        exit_index=1,
        qty=qty,
        risk_usd=5.0,
        pnl_usd=pnl,
        r=pnl / 5.0,
        entry_ms=_ms(2026, 1, day, hour),
        exit_ms=_ms(2026, 1, day, hour + 1),
        exit_price=exit,
        stop_distance=stop,
        exit_reason=reason,
        mfe_usd=mfe,
        mae_usd=mae,
        costs_usd=costs,
        adds=adds or [],
    )


# ── equity curve ──────────────────────────────────────────────────────────────


def test_equity_curve_accumulates_and_is_one_point_per_trade():
    curve = build_equity_curve([_t(100.0, day=1), _t(-40.0, day=2), _t(10.0, day=3)])
    assert [p["equity"] for p in curve] == [100.0, 60.0, 70.0]
    assert [p["index"] for p in curve] == [1, 2, 3]
    assert len(curve) == 3


def test_equity_curve_anchors_on_initial_capital():
    curve = build_equity_curve([_t(100.0)], initial_capital=50_000.0)
    assert curve[0]["equity"] == 50_100.0


def test_equity_curve_orders_by_exit_not_input_order():
    curve = build_equity_curve([_t(10.0, day=3), _t(100.0, day=1), _t(-40.0, day=2)])
    assert [p["equity"] for p in curve] == [100.0, 60.0, 70.0]


def test_long_plus_short_equals_trade_count():
    """The invariant the MT5 path had to be rewritten to guarantee."""
    trades = [_t(1.0, day=1, dir=1), _t(1.0, day=2, dir=-1), _t(1.0, day=3, dir=-1)]
    curve = build_equity_curve(trades)
    longs = sum(1 for p in curve if p["direction"] == "Long")
    shorts = sum(1 for p in curve if p["direction"] == "Short")
    assert longs + shorts == len(trades) == 3
    assert (longs, shorts) == (1, 2)


def test_equity_curve_point_has_exactly_the_lab_contract_keys():
    p = build_equity_curve([_t(100.0)])[0]
    assert set(p) == {
        "index",
        "equity",
        "date",
        "entry_ms",
        "exit_ms",
        "direction",
        "profit",
        "exit_name",
        "size",
        "favorable",
        "adverse",
        "costs_usd",
        "entry_price",
        "exit_price",
        "kind",
        "mfe_price",
        "mae_price",
        "stop_price",
        "legs",
        "tp_targets",
        # 2026-08-03 — the trade's own R and the dollars it risked, COPIED from the
        # strategy. Together they describe it exactly (`profit == r * risk_usd`),
        # which is what lets `backtest/reprice.py` re-walk a balance without
        # recovering either from a 2dp profit and a 5dp stop price.
        "r",
        "risk_usd",
    }


def test_a_trade_without_r_or_a_stop_omits_those_keys_rather_than_faking_them():
    """Both are optional by design — an NT8/MT5 curve and any trade duck-type lacking them simply
    has no key. Writing a 0.0 would make a re-price read the trade as risking nothing, and it would
    charge the whole account for one spread rather than refusing."""

    class _Bare:
        dir, qty, entry_ms, exit_ms = 1, 1.0, 0, 86_400_000
        pnl_usd, exit_reason, entry_price, exit_price = 100.0, "TP", 2000.0, 2010.0

    p = build_equity_curve([_Bare()])[0]
    assert "r" not in p and "risk_usd" not in p


def test_equity_curve_carries_what_the_trade_was_CHARGED():
    """A run can be priced since 2026-08-01, and what the costs came to was uninspectable — the
    run row carried the SETTINGS and nothing reported the resulting charge. `profit` is already
    net of it, so this is reporting only. 0.0 on an unpriced run is "nothing was priced", which
    is why the page hides the row rather than printing $0 (that would read as "free")."""
    assert build_equity_curve([_t(100.0, costs=-8.25)])[0]["costs_usd"] == -8.25
    assert build_equity_curve([_t(100.0)])[0]["costs_usd"] == 0.0


def test_equity_curve_carries_trade_excursion():
    curve = build_equity_curve([_t(100.0, mfe=250.0, mae=-40.0)])
    assert curve[0]["favorable"] == 250.0
    assert curve[0]["adverse"] == -40.0


def test_equity_curve_carries_the_scale_in_lots_a_trade_bought():
    """`size` is the BASE quantity, so without this the row cannot account for its own P&L.

    Measured on run 295a6ff29d21: eight trades booked exactly $0.00 with the exit BELOW the entry
    on a short — the profit had gone to a scale-in lot bought later and closed at the same exit,
    and no field in the curve, the KPI row or the chart mentioned that lot existed."""
    lots = [{"price": 106.5, "ms": 1_500, "qty": 0.75}]
    point = build_equity_curve([_t(0.0, adds=lots)])[0]
    assert point["adds"] == [{"price": 106.5, "ms": 1500, "qty": 0.75}]


def test_a_trade_that_never_added_omits_the_key_rather_than_writing_an_empty_list():
    """Same rule as `r` / `risk_usd` above: absent means "this run has no such thing", and every
    trade of every strategy without scale-in is that. An empty list on all of them would read as a
    feature that ran and bought nothing."""
    assert "adds" not in build_equity_curve([_t(100.0)])[0]


def test_equity_curve_excursion_defaults_to_zero_when_trade_lacks_it():
    """`output` consumes any trade duck-type; one without mfe/mae reads a clean 0.0, not a crash."""
    curve = build_equity_curve([_t(100.0)])
    assert curve[0]["favorable"] == 0.0
    assert curve[0]["adverse"] == 0.0


# ── the trade's fib leg ───────────────────────────────────────────────────────


class _FakeFib:
    def __init__(self, levels, start_ms=None):
        self.levels, self.start_ms = levels, start_ms


def test_equity_curve_carries_the_trade_s_fib_leg():
    t = _t(100.0)
    t.fib = _FakeFib([(0.0, 110.0), (0.618, 103.82), (1.0, 100.0)], start_ms=1_700_000_000_000)
    p = build_equity_curve([t])[0]
    assert p["fib"] == {
        "levels": [[0.0, 110.0], [0.618, 103.82], [1.0, 100.0]],
        "start_ms": 1_700_000_000_000,
    }


def test_a_trade_with_no_fib_omits_the_key_entirely():
    """Absent, not empty. The chart's Trade fibs toggle is listed off whether trades carry one, so
    an empty object would advertise a layer with nothing in it — the same rule the blocked and
    missed layers follow for a runner that cannot report them."""
    assert "fib" not in build_equity_curve([_t(100.0)])[0]
    t = _t(100.0)
    t.fib = _FakeFib([])
    assert "fib" not in build_equity_curve([t])[0]


def test_the_fib_ladder_is_COPIED_never_recomputed():
    """`output` knows no fib maths and must not learn any: the prices are the ones the strategy
    had in hand at placement. A ladder whose ratios are not evenly spaced (a strategy with its own
    set) passes through untouched rather than being 'corrected' onto a line."""
    t = _t(100.0)
    t.fib = _FakeFib([(0.0, 110.0), (0.236, 108.0), (0.5, 99.0)])  # deliberately NOT linear
    assert build_equity_curve([t])[0]["fib"]["levels"] == [
        [0.0, 110.0],
        [0.236, 108.0],
        [0.5, 99.0],
    ]


def test_stop_price_is_derived_from_distance_and_direction():
    """The profit-depth view's risk line: long stop sits below entry, short above."""
    long_p = build_equity_curve([_t(10.0, dir=1, entry=100.0, stop=5.0)])[0]
    short_p = build_equity_curve([_t(10.0, dir=-1, entry=100.0, stop=5.0)])[0]
    assert long_p["stop_price"] == 95.0
    assert short_p["stop_price"] == 105.0


def test_profit_depth_fields_default_cleanly_when_trade_lacks_them():
    """A trade duck-type without mfe_price/mae_price/legs reads 0.0 / [] — never a crash."""
    p = build_equity_curve([_t(100.0)])[0]
    assert p["mfe_price"] == 0.0
    assert p["mae_price"] == 0.0
    assert p["legs"] == []


def test_legs_pass_through_rounded():
    """The per-rung exit ledger flows to the chart, price-rounded, order preserved."""
    t = _t(100.0)
    t.mfe_price = 90.123456
    t.legs = [
        {"reason": "S-TP1", "price": 95.123456, "ms": 111, "qty": 0.3},
        {"reason": "S-RUN", "price": 90.5, "ms": 222, "qty": 0.7},
    ]
    p = build_equity_curve([t])[0]
    assert p["mfe_price"] == 90.12346
    assert [lg["reason"] for lg in p["legs"]] == ["S-TP1", "S-RUN"]
    assert p["legs"][0]["price"] == 95.12346
    assert p["legs"][0]["ms"] == 111


def test_entry_ms_is_present_for_the_news_filter():
    p = build_equity_curve([_t(100.0, day=4, hour=9)])[0]
    assert p["entry_ms"] == _ms(2026, 1, 4, 9)


def test_two_trades_closing_the_same_minute_stay_separate():
    """Regression twin of the MT5 timestamp-collapse bug."""
    a, b = _t(10.0, day=1), _t(20.0, day=1)
    b.entry_ms = a.entry_ms
    b.exit_ms = a.exit_ms
    assert len(build_equity_curve([a, b])) == 2


# ── daily P&L ─────────────────────────────────────────────────────────────────


def test_daily_pnl_sums_per_day_and_books_on_exit_day():
    days = build_daily_pnl([_t(100.0, day=1), _t(-40.0, day=1), _t(10.0, day=2)])
    assert days == [{"date": "2026-01-01", "pnl": 60.0}, {"date": "2026-01-02", "pnl": 10.0}]


def test_daily_pnl_skips_days_with_no_trades():
    days = build_daily_pnl([_t(1.0, day=1), _t(1.0, day=5)])
    assert [d["date"] for d in days] == ["2026-01-01", "2026-01-05"]


def test_daily_pnl_is_sorted_by_date():
    days = build_daily_pnl([_t(1.0, day=9), _t(1.0, day=2)])
    assert [d["date"] for d in days] == ["2026-01-02", "2026-01-09"]


# ── KPIs ──────────────────────────────────────────────────────────────────────


def test_kpis_hand_computed():
    # wins 100 + 50 = 150; losses 40 + 10 = 50 → PF 3.0, win rate 50%
    trades = [_t(100.0, day=1), _t(-40.0, day=2), _t(50.0, day=3), _t(-10.0, day=4)]
    k = build_kpis(trades)
    assert k["net_pnl"] == 100.0
    assert k["gross_profit"] == 150.0
    assert k["gross_loss"] == 50.0
    assert k["profit_factor"] == 3.0
    assert k["trade_count"] == 4
    assert k["win_count"] == 2
    assert k["win_rate"] == 0.5  # fraction, not percent — lab-wide convention
    assert k["avg_win"] == 75.0
    assert k["avg_loss"] == -25.0


def test_max_drawdown_is_positive_peak_to_trough():
    # equity: 100 → 20 → 60. Peak 100, trough 20 → DD 80.
    trades = [_t(100.0, day=1), _t(-80.0, day=2), _t(40.0, day=3)]
    assert build_kpis(trades)["max_drawdown"] == 80.0


def test_max_drawdown_zero_when_never_below_start():
    trades = [_t(10.0, day=1), _t(20.0, day=2)]
    assert build_kpis(trades)["max_drawdown"] == 0.0


def test_max_drawdown_measures_from_initial_capital_peak():
    """A first losing trade draws down from the opening balance, not from 0."""
    k = build_kpis([_t(-30.0, day=1)], initial_capital=1000.0)
    assert k["max_drawdown"] == 30.0


def test_worst_day_and_streak():
    trades = [_t(-10.0, day=1), _t(-20.0, day=2), _t(-30.0, day=3), _t(5.0, day=4)]
    k = build_kpis(trades)
    assert k["worst_day_pnl"] == -30.0
    assert k["worst_losing_streak"] == 3


def test_profit_factor_zero_not_inf_when_no_losses():
    assert build_kpis([_t(10.0)])["profit_factor"] == 0.0


def test_empty_trades_produce_zeroed_kpis_not_a_crash():
    k = build_kpis([])
    assert k["trade_count"] == 0
    assert k["net_pnl"] == 0.0
    assert k["win_rate"] == 0.0
    assert k["max_drawdown"] == 0.0


def test_kpis_omit_sharpe_the_lab_owns_it():
    k = build_kpis([_t(10.0)])
    for owned_by_lab in ("sharpe", "platform_sharpe", "sharpe_low_sample", "cagr"):
        assert owned_by_lab not in k


def test_avg_duration_minutes():
    assert build_kpis([_t(10.0)])["avg_trade_duration_min"] == 60.0


# ── engine_trades ─────────────────────────────────────────────────────────────


def test_engine_trades_carry_stop_distance_and_iso_times():
    rows = build_engine_trades([_t(100.0, stop=7.5)], point_value=2.0)
    r = rows[0]
    assert r["stop_distance"] == 7.5
    assert r["point_value"] == 2.0
    assert r["direction"] == 1
    assert r["entry_time"].startswith("2026-01-01T12:00")


def test_engine_trades_short_direction_is_minus_one():
    rows = build_engine_trades([_t(10.0, dir=-1)], point_value=1.0)
    assert rows[0]["direction"] == -1


def test_engine_trades_csv_roundtrips():
    import csv
    import io

    rows = build_engine_trades([_t(100.0), _t(-40.0, day=2)], point_value=1.0)
    text = engine_trades_csv(rows)
    back = list(csv.DictReader(io.StringIO(text)))
    assert len(back) == 2
    assert back[0]["exit_reason"] == "L-TP1"
    assert float(back[0]["stop_distance"]) == 5.0


# ── build_results ─────────────────────────────────────────────────────────────


def test_build_results_has_the_lab_keys():
    res = build_results([_t(100.0)], point_value=1.0)
    assert set(res) == {
        "equity_curve",
        "daily_pnl",
        "kpis",
        "engine_trades",
        "blocked_setups",
        "missed_setups",
        # 2026-09-03. Present on EVERY run, `None` when nothing recorded it — a clamp leaves no
        # other trace, so an absent key would make "the sizes were cut" unaskable.
        "lot_capped",
    }


def test_build_results_reports_no_blocked_setups_when_none_were_recorded():
    """A strategy that records no refusals still emits the key — an EMPTY list, never a
    missing one, so a consumer never has to tell "none" apart from "not reported"."""
    assert build_results([_t(100.0)], point_value=1.0)["blocked_setups"] == []


def test_build_results_reports_no_missed_setups_when_none_were_recorded():
    """Same contract as the blocked key — present and empty, never absent."""
    assert build_results([_t(100.0)], point_value=1.0)["missed_setups"] == []


def test_build_results_is_json_serialisable():
    import json

    res = build_results([_t(100.0), _t(-40.0, day=2)], point_value=1.0)
    assert json.loads(json.dumps(res))["kpis"]["net_pnl"] == 60.0


def test_exit_price_reproduces_pnl():
    """The laddered-exit VWAP contract: (exit-entry)*dir*qty*point_value == pnl_usd."""
    t = _t(20.0, entry=100.0, exit=110.0, qty=2.0)
    row = build_engine_trades([t], point_value=1.0)[0]
    implied = (row["exit_price"] - row["entry_price"]) * row["direction"] * t.qty * 1.0
    assert implied == pytest.approx(t.pnl_usd)


# ── blocked setups ────────────────────────────────────────────────────────────


class _Blk:
    """The duck-type `build_blocked_setups` consumes — deliberately NOT the strategy's own
    class, so the test proves the adapter needs nothing but these attributes."""

    def __init__(self, dir_, time_ms, codes, edge, labels, reasons):
        self.dir, self.time_ms, self.codes = dir_, time_ms, codes
        self.edge, self.labels, self.reasons = edge, labels, reasons


def test_blocked_setups_map_direction_and_sort_by_time():
    rows = build_blocked_setups(
        [
            _Blk(-1, 2_000, [3], 1234.5678, ["Final hour"], ["no new entries 16:00-18:00 NY"]),
            _Blk(1, 1_000, [4], 1200.0, ["Divergence / RSI veto"], ["opposing divergence"]),
        ]
    )
    assert [r["time_ms"] for r in rows] == [1_000, 2_000]
    assert [r["direction"] for r in rows] == ["Long", "Short"]
    assert rows[1]["edge"] == 1234.5678
    assert rows[1]["reasons"] == [
        {"label": "Final hour", "reason": "no new entries 16:00-18:00 NY"}
    ]


def test_blocked_setups_carry_every_reason_in_order():
    """A setup can be refused by several rules at once — the row keeps them ALL, in the
    strategy's precedence order, which is what lets the chart filter by reason."""
    rows = build_blocked_setups(
        [
            _Blk(1, 1_000, [1, 3], 1200.0, ["Direction off", "Final hour"], ["a", "b"]),
        ]
    )
    assert [r["label"] for r in rows[0]["reasons"]] == ["Direction off", "Final hour"]
    assert rows[0]["codes"] == [1, 3]


def test_blocked_setups_tolerates_none():
    assert build_blocked_setups(None) == []


class _Miss:
    """The duck-type `build_missed_setups` consumes — again deliberately NOT the strategy's
    own class, so the test proves the adapter needs nothing but these attributes."""

    def __init__(self, dir_, time_ms, met, edge, labels, reasons, met_lines, near=True):
        self.dir, self.time_ms, self.met, self.edge = dir_, time_ms, met, edge
        self.labels, self.reasons, self.met_lines, self.near = labels, reasons, met_lines, near


def test_missed_setups_map_direction_score_and_sort_by_time():
    rows = build_missed_setups(
        [
            _Miss(
                -1,
                2_000,
                3,
                1234.5678,
                ["Never filled"],
                ["price never touched it"],
                ["Arm — Sweep", "SOS — confirmed", "Zone — 0.5-0.886 tagged"],
            ),
            _Miss(
                1,
                1_000,
                2,
                1200.0,
                ["No retrace"],
                ["never came back"],
                ["SOS — confirmed"],
                near=False,
            ),
        ]
    )
    assert [r["time_ms"] for r in rows] == [1_000, 2_000]
    assert [r["direction"] for r in rows] == ["Long", "Short"]
    assert [(r["met"], r["of"]) for r in rows] == [(2, 3), (3, 3)]
    assert rows[1]["met_lines"][0] == "Arm — Sweep"
    assert rows[1]["reasons"] == [{"label": "Never filled", "reason": "price never touched it"}]


def test_missed_setups_carry_the_near_flag_verbatim():
    """`near` is the STRATEGY's own judgement about which misses are worth opening on. The
    adapter must pass it through untouched — the chart derives its default filters from it,
    so a dropped or defaulted flag silently changes what the reader sees first."""
    rows = build_missed_setups(
        [
            _Miss(1, 1_000, 2, 1.0, ["No retrace"], ["…"], [], near=False),
            _Miss(1, 2_000, 3, 1.0, ["Final hour"], ["…"], [], near=True),
        ]
    )
    assert [r["near"] for r in rows] == [False, True]


def test_missed_setups_tolerates_none():
    assert build_missed_setups(None) == []


# ── the real contract: does the lab's sizing engine accept our rows? ───────────


def test_engine_trades_feed_the_real_sizing_engine_RawTrade():
    """Constructs the ACTUAL `sizing_engine.RawTrade` from our rows — this is what
    proves the contract, not a mirrored dataclass in this file."""
    sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "command-center" / "backend"))
    try:
        from services.sizing_engine import RawTrade
    except ImportError:
        pytest.skip("command-center backend not importable in this environment")

    rows = build_engine_trades([_t(100.0, stop=5.0)], point_value=2.0)
    rt = RawTrade(
        index=rows[0]["index"],
        entry_time=datetime.fromisoformat(rows[0]["entry_time"]),
        exit_time=datetime.fromisoformat(rows[0]["exit_time"]),
        direction=rows[0]["direction"],
        entry_price=rows[0]["entry_price"],
        exit_price=rows[0]["exit_price"],
        stop_distance=rows[0]["stop_distance"],
        point_value=rows[0]["point_value"],
        commission_per_side=rows[0]["commission_per_side"],
        exit_reason=rows[0]["exit_reason"],
    )
    # 100→110 long at $2/point = $20 per contract gross.
    assert rt.gross_per_contract() == pytest.approx(20.0)


def test_a_lots_own_excursion_and_exit_reach_the_curve_point():
    """A lot is a POSITION: it runs its own distance, goes its own distance against, and comes off
    somewhere. The three keys above say only that one was BOUGHT, which is all a reader could learn
    from a scaled trade until 2026-08-20.

    Watched RED by mutation: deleting the per-lot copy block from `build_equity_curve` leaves the
    original three keys and this fails naming the six that vanished."""
    lots = [
        {
            "price": 106.5,
            "ms": 1_500,
            "qty": 0.75,
            "mfe_price": 108.25,
            "mae_price": 105.0,
            "exit_price": 107.0,
            "exit_ms": 1_800,
            "exit_reason": "L-ATP",
            "pnl_usd": 0.375,
        }
    ]
    assert build_equity_curve([_t(0.0, adds=lots)])[0]["adds"] == [
        {
            "price": 106.5,
            "ms": 1500,
            "qty": 0.75,
            "mfe_price": 108.25,
            "mae_price": 105.0,
            "exit_price": 107.0,
            "exit_ms": 1800,
            "exit_reason": "L-ATP",
            "pnl_usd": 0.38,
        }
    ]


def test_a_lot_that_recorded_nothing_past_its_fill_is_not_given_zeroes():
    """🔴 The rule the whole file keeps: absent must not become measured.

    A strategy that adds without tracking its lots — and every run stored before 2026-08-20 —
    carries `{price, ms, qty}`. Defaulting the rest to 0.0 puts the lot's exit at price ZERO and
    its drawdown at zero, stated as confidently as a real reading. This is the bar cache recording
    a REQUESTED range as received, one layer down.

    Watched RED by mutation: changing the comprehension's `if a.get(k) is not None` guard to a
    plain `a.get(k, 0.0)` makes all six keys appear at zero and this goes red."""
    lots = [{"price": 106.5, "ms": 1_500, "qty": 0.75}]
    assert build_equity_curve([_t(0.0, adds=lots)])[0]["adds"] == [
        {"price": 106.5, "ms": 1500, "qty": 0.75}
    ]


# ── the exit RUNGS a trade reports ────────────────────────────────────────────
# A rung price alone does not say whether the trade places an ORDER there. At sos_fade's
# shipped settings the second rung banks 0% of the position on every trade — nothing is ever sold
# at that price and a touch only steps the stop — yet the chart drew it as `TP2` on every trade of
# every run until 2026-08-21. See `command-center/backend/tests/test_chart_spec_tp_rungs.py` for
# the picture that found it.


def _targets(**extra):
    """A minimal closed trade, plus whatever rung fields the case is about."""
    t = FakeTrade(
        dir=1,
        entry_index=0,
        entry_price=100.0,
        exit_index=1,
        qty=1.0,
        risk_usd=10.0,
        pnl_usd=1.0,
        r=0.1,
        entry_ms=_ms(2026, 1, 1),
        exit_ms=_ms(2026, 1, 2),
        exit_price=101.0,
        stop_distance=10.0,
        exit_reason="RUN",
    )
    for k, v in extra.items():
        setattr(t, k, v)
    return build_equity_curve([t])[0]["tp_targets"]


def test_a_reported_rung_says_whether_it_actually_banks():
    assert _targets(tp_rungs=((110.0, 50.0), (120.0, 0.0))) == [
        {"price": 110.0, "banks": True},
        {"price": 120.0, "banks": False},
    ]


def test_a_strategy_that_reports_only_PRICES_says_nothing_about_banking():
    """🔴 "no" and "cannot ask" must not be one value. Every run stored before rungs existed
    carries bare prices, and emitting `banks: False` for them would tell the chart to redraw
    their targets as stop steps off a measurement nobody made."""
    out = _targets(tp1=110.0, tp2=120.0)
    assert out == [110.0, 120.0]
    assert not any(isinstance(t, dict) for t in out)


def test_a_strategy_that_reports_neither_ships_no_ladder_rather_than_an_invented_one():
    assert _targets() == []


def test_an_unset_rung_is_dropped_rather_than_reported_at_price_zero():
    assert _targets(tp_rungs=((110.0, 50.0), (0.0, 0.0))) == [{"price": 110.0, "banks": True}]


# ── the venue lot ceiling's own record (2026-09-03) ───────────────────────────────────
#
# 🔴 A clamp leaves NO other trace. A resized entry is still a trade, on the equity curve, with
# the SAME R as a full-size one — R is profit over risk and both scale with quantity. So a run
# whose sizes were quietly halved looks completely healthy, and this list is the only thing in
# the whole pipeline that can say otherwise.
def test_an_unrecorded_clamp_and_a_clamp_that_never_FIRED_are_different_answers():
    """Rule 1 at the reporting layer. `None` = nobody looked; `[]` = looked, never bit. The
    second is a reassuring MEASUREMENT and must not be indistinguishable from the first.
    RED on `if not records: return []`."""
    from backtest.output import build_lot_capped

    assert build_lot_capped(None) is None
    assert build_lot_capped([]) == []


def test_a_clamp_is_carried_verbatim_rather_than_recomputed():
    """What the account WROTE is what is stored — recomputing here would let the report drift
    from what the clamp actually did to the order."""
    from backtest.output import build_lot_capped

    rec = {"leg": "strat", "desired_lots": 742.6, "max_lots": 100.0, "over_x": 7.426}
    assert build_lot_capped([rec]) == [rec]


def test_build_results_always_carries_the_clamp_key():
    """The key must exist even when the value is None, or a consumer cannot tell "this run
    recorded nothing" from "this pipeline version had no such field"."""
    from backtest.output import build_results

    r = build_results([], point_value=1.0)
    assert "lot_capped" in r
    assert r["lot_capped"] is None

    r2 = build_results([], point_value=1.0, lot_capped=[])
    assert r2["lot_capped"] == []
