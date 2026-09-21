"""The derived streams, and the two paths that consume them.

🔴 **Every test here has been watched go RED for the right reason** — each one names the mutation
that breaks it in its own docstring, because a test that cannot fail proves nothing and this repo
has at least eight that passed against their own bug.

These run off the committed golden export, so they are a real measurement rather than a fixture
more capable than production.
"""

from __future__ import annotations

import csv
from pathlib import Path

import pytest

from strategies.python.smc_session_sweep.config import SessionSweepConfig
from strategies.python.smc_session_sweep.core import BarInput, SessionSweepCore
from strategies.python.smc_session_sweep.levels import PrevPeriodLevels
from strategies.python.smc_session_sweep.structure import ResampledStructure, derive_stream

_GOLDEN = (
    Path(__file__).resolve().parents[1]
    / "exports"
    / "golden"
    / "VANTAGE_XAUUSD_M5_20597bars.csv"
)


def _rows():
    if not _GOLDEN.exists():  # pragma: no cover - the export is committed
        pytest.skip(f"golden export missing: {_GOLDEN}")
    return [r for r in csv.DictReader(_GOLDEN.open()) if r["px_state"]]


def _series(rows):
    f = float
    return (
        [int(f(r["time"])) * 1000 for r in rows],
        [f(r["open"]) for r in rows],
        [f(r["high"]) for r in rows],
        [f(r["low"]) for r in rows],
        [f(r["close"]) for r in rows],
    )


def test_direction_stream_matches_the_pine_after_warmup():
    """The 15m direction, rebuilt from 5m bars, equals the chart's own column.

    RED when: the alignment in `derive_stream` publishes a group's value on the bar AFTER it
    closes instead of on the bar that closes it (scores 20,396 instead of 20,436).
    """
    rows = _rows()
    t, o, h, low, c = _series(rows)
    s = derive_stream(t, o, h, low, c, 15, 5, 15)
    bad = [
        i
        for i in range(500, len(rows))
        if rows[i]["px_dir"] and int(float(rows[i]["px_dir"])) != s.direction[i]
    ]
    assert bad == [], f"{len(bad)} direction disagreements after bar 500, first at {bad[:3]}"


def test_streaming_resampler_equals_the_batch_one():
    """The lab path and the gate path must derive the same stream, bar for bar.

    RED when: `ResampledStructure._closes_group` counts bars instead of reading the clock — a
    single missing bar then holds the whole stream one group behind for the rest of the run.
    """
    rows = _rows()
    t, o, h, low, c = _series(rows)
    batch = derive_stream(t, o, h, low, c, 15, 5, 15)
    live = ResampledStructure(15, 5, 15)
    for i in range(len(rows)):
        d, shifted = live.update(t[i], o[i], h[i], low[i], c[i])
        assert d == batch.direction[i], f"direction differs at bar {i}"
        assert shifted == batch.shifted[i], f"shift flag differs at bar {i}"


def test_previous_period_levels_match_the_pine_after_warmup():
    """Yesterday's and last week's extremes, rebuilt on the 17:00 New York day.

    RED when: the day boundary moves to UTC — which is the obvious guess, looks identical on a
    chart, and disagrees on more than half the bars (8,531 of 20,597 matched).
    """
    rows = _rows()
    t, _, h, low, _ = _series(rows)
    lv = PrevPeriodLevels()
    bad = []
    for i in range(len(rows)):
        lv.update(t[i], h[i], low[i])
        if i < 2100:
            continue
        for attr, col in (("pdh", "px_pdh"), ("pdl", "px_pdl"),
                          ("pwh", "px_pwh"), ("pwl", "px_pwl")):
            pine = float(rows[i][col]) if rows[i][col] else None
            got = getattr(lv, attr)
            if pine is not None and abs(pine - got) > 0.015:
                bad.append((i, col, pine, got))
    assert bad == [], f"{len(bad)} level disagreements, first {bad[:3]}"


def test_a_finer_timeframe_is_refused_rather_than_approximated():
    """Asking for 1-minute structure off a 5-minute replay must RAISE.

    RED when: the guard is dropped — the stream would then silently confirm on the chart's own
    frame and the run would report a different strategy from the one the chart trades.
    """
    with pytest.raises(ValueError, match="not recoverable"):
        ResampledStructure(1, 5, 15)


def test_unreached_targets_are_nan_not_zero():
    """A level that has not existed yet is NaN, never 0.0.

    RED when: `PrevPeriodLevels` seeds its fields at 0.0 — a zero target makes every long's
    reward look infinite and every short's stop look unreachable, and nothing errors.
    """
    lv = PrevPeriodLevels()
    lv.update(0, 100.0, 90.0)
    assert lv.pdh != lv.pdh and lv.pwl != lv.pwl


def test_fixed_contract_exports_are_refused():
    """The twin carries no size column in fixed-contracts mode, so the gate must refuse it.

    RED when: `from_export` accepts any size mode — the gate would then compare a position size
    it cannot see and report PARITY OK over it.
    """
    row = {
        "cfg_bits": "4091", "cfg_enum1": "200010", "cfg_int1": "2002015", "cfg_int2": "80",
        "cfg_poi_tf": "5", "cfg_dir_tf": "15", "cfg_conf_tf": "1", "cfg_tp1_r": "3.5",
        "cfg_risk_pct": "4", "cfg_tp_fallback": "3", "cfg_min_rr": "1",
        "cfg_min_stop_val": "4", "cfg_poi_max_atr": "0", "cfg_time_stop": "0",
    }
    with pytest.raises(ValueError, match="Fixed-contracts"):
        SessionSweepConfig.from_export(row)


def test_the_core_books_a_trade_per_closed_position():
    """The book the lab reads must have one record per position, not per exit rung.

    RED when: `_book_trade` is called from `_close_part` as well — the 80% rung would then be
    reported as its own trade and every R figure would be counted twice.
    """
    rows = _rows()
    cfg = SessionSweepConfig.from_export(rows[len(rows) // 2])
    core = SessionSweepCore(cfg)
    t, o, h, low, c = _series(rows)
    dir_stream = derive_stream(t, o, h, low, c, 15, 5, cfg.pb_struct_len)
    lv = PrevPeriodLevels()
    closes = 0
    for i, r in enumerate(rows):
        lv.update(t[i], h[i], low[i])
        out = core.step(BarInput(
            time_ms=t[i], open=o[i], high=h[i], low=low[i], close=c[i],
            dir_dir=dir_stream.direction[i],
            conf_dir=int(float(r["px_conf_dir"])) if r["px_conf_dir"] else 0,
            conf_shifted=False,
            pdh=lv.pdh, pdl=lv.pdl, pwh=lv.pwh, pwl=lv.pwl,
        ))
        if out.px_exec & 2:
            closes += 1
    assert len(core.trades) == closes
    assert closes > 0, "the export closed no trades — this test would prove nothing"
