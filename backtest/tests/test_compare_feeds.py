"""Offline tests for the pure feed-comparison math in tools/compare_feeds.py.

No network: the MT5 pull lives only in `main`; parse / infer-tf / detect-offset /
diff are exercised here with synthetic frames.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "tools"))
import compare_feeds as cf  # noqa: E402


def _frame(start: str, n: int, freq: str = "15min", base: float = 2000.0) -> pd.DataFrame:
    idx = pd.date_range(start=start, periods=n, freq=freq, name="time")
    o = [base + i for i in range(n)]
    return pd.DataFrame(
        {"open": o, "high": [x + 1 for x in o], "low": [x - 1 for x in o], "close": o},
        index=idx,
    )


# --------------------------------------------------------------- parse_tv ----
def test_parse_tv_csv_iso_z(tmp_path):
    p = tmp_path / "tv.csv"
    p.write_text(
        "time,open,high,low,close\n"
        "2025-01-06T00:00:00Z,2000,2001,1999,2000.5\n"
        "2025-01-06T00:15:00Z,2000.5,2002,2000,2001\n"
    )
    df = cf.parse_tv_csv(p)
    assert list(df.columns) == ["open", "high", "low", "close"]
    assert df.index[0] == pd.Timestamp("2025-01-06 00:00:00")  # naive UTC
    assert df.index.tz is None
    assert df["close"].iloc[1] == 2001.0


def test_parse_tv_csv_tz_aware_converts_to_utc(tmp_path):
    p = tmp_path / "tv.csv"
    # 05:00 at -05:00 == 10:00 UTC
    p.write_text("time,open,high,low,close\n2025-01-06T05:00:00-05:00,1,2,0,1\n")
    df = cf.parse_tv_csv(p)
    assert df.index[0] == pd.Timestamp("2025-01-06 10:00:00")


def test_parse_tv_csv_unix_seconds(tmp_path):
    p = tmp_path / "tv.csv"
    p.write_text("time,open,high,low,close\n1736121600,1,2,0,1\n")  # 2025-01-06 00:00 UTC
    df = cf.parse_tv_csv(p)
    assert df.index[0] == pd.Timestamp("2025-01-06 00:00:00")


# ------------------------------------------------------------ infer_tf -------
def test_infer_timeframe_snaps_to_served():
    assert cf.infer_timeframe(_frame("2025-01-06", 20, "15min")) == ("M15", 15)
    assert cf.infer_timeframe(_frame("2025-01-06", 20, "5min")) == ("M5", 5)
    assert cf.infer_timeframe(_frame("2025-01-06", 20, "1h")) == ("H1", 60)


# ----------------------------------------------------------- detect_offset ---
def test_detect_offset_aligned_is_zero():
    tv = _frame("2025-01-06", 50)
    mt5 = _frame("2025-01-06", 50)
    shift, overlap = cf.detect_offset(tv, mt5)
    assert shift == 0
    assert overlap == 50


def test_detect_offset_finds_broker_ahead():
    tv = _frame("2025-01-06 00:00", 50)
    mt5 = _frame("2025-01-06 02:00", 50)  # MT5 stamped 2h ahead of TV
    shift, _ = cf.detect_offset(tv, mt5)
    # MT5 must move -2h to line up -> reported as broker running +2h ahead
    assert shift == -2


# ------------------------------------------------------------ align_diff -----
def test_align_and_diff_identical_feeds():
    tv = _frame("2025-01-06", 30)
    mt5 = _frame("2025-01-06", 30)
    d = cf.align_and_diff(tv, mt5, 0)
    assert d.matched == 30
    assert d.tv_only == 0 and d.mt5_only == 0
    assert d.mean_abs["close"] == 0.0
    assert d.mean_abs_pct == 0.0


def test_align_and_diff_measures_price_drift():
    tv = _frame("2025-01-06", 20, base=2000.0)
    mt5 = _frame("2025-01-06", 20, base=2000.3)  # +0.30 everywhere
    d = cf.align_and_diff(tv, mt5, 0)
    assert d.matched == 20
    assert abs(d.mean_abs["close"] - 0.30) < 1e-9
    assert d.mean_abs_pct > 0


def test_offset_profile_constant_offset():
    tv = _frame("2025-01-06", 400)
    mt5 = _frame("2025-01-06 03:00", 400)  # constant +3h ahead
    prof = cf.offset_profile(tv, mt5, chunks=4)
    assert prof  # non-empty
    assert {c.shift_hours for c in prof} == {-3}


def test_offset_profile_detects_dst_change():
    # MT5 is a price-faithful copy of TV, +2h ahead in the first half and +3h in
    # the second (a DST boundary in the middle).
    tv = _frame("2025-01-06 00:00", 400, freq="1h")
    winter = tv.iloc[:200].copy(); winter.index = winter.index + pd.Timedelta(hours=2)
    summer = tv.iloc[200:].copy(); summer.index = summer.index + pd.Timedelta(hours=3)
    mt5 = pd.concat([winter, summer])
    prof = cf.offset_profile(tv, mt5, chunks=8)
    assert {-2, -3}.issubset({c.shift_hours for c in prof})


def test_dst_correct_removes_variable_offset():
    tv = _frame("2025-01-06 00:00", 400, freq="1h")
    winter = tv.iloc[:200].copy(); winter.index = winter.index + pd.Timedelta(hours=2)
    summer = tv.iloc[200:].copy(); summer.index = summer.index + pd.Timedelta(hours=3)
    mt5 = pd.concat([winter, summer])
    prof = cf.offset_profile(tv, mt5, chunks=8)
    corrected = cf.dst_correct(tv, mt5, prof)
    d = cf.align_and_diff(tv, corrected, 0)
    # after per-chunk correction, essentially all bars line up and prices match
    assert d.matched >= 380
    assert d.mean_abs["close"] < 1e-9


def test_align_and_diff_applies_shift_before_join():
    tv = _frame("2025-01-06 00:00", 20)
    mt5 = _frame("2025-01-06 02:00", 20)  # 2h ahead; shifting -2h realigns the grids
    assert cf.align_and_diff(tv, mt5, 0).matched == 12   # unshifted: only the overlap
    assert cf.align_and_diff(tv, mt5, -2).matched == 20  # shifted: grids coincide
