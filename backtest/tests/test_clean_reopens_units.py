"""The reopen-spike clip must find the reopen whatever unit pandas stores the timestamps in.

pandas 3 (the repo's `.venv`) parses the bar caches' `time` column to MICROSECONDS; pandas 2 (the
Command Center's venv) to nanoseconds. The clip read `index.asi8 // 10**9` as seconds, which is only
true for nanoseconds — under pandas 3 every gap looked 1,000x shorter, no bar was ever a reopen, and
the tool printed "reopen spikes clipped 0" as though the market had been clean (found 2026-09-21:
gold 2020-25 clipped 97 under one interpreter and 0 under the other). Mutation: restore the old line
→ the microsecond case clips nothing and goes RED; it did, 2026-09-21.
"""

import sys
from pathlib import Path

import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))

from loaded_level_study import clean_reopens  # noqa: E402


def _frame(unit: str) -> pd.DataFrame:
    # 30 quiet minutes, a 60-minute closure, then a reopen bar whose low spikes $15 under both closes
    t = list(pd.date_range("2026-07-22 15:00", periods=30, freq="1min"))
    t.append(t[-1] + pd.Timedelta(minutes=61))
    idx = pd.DatetimeIndex(t).as_unit(unit)
    n = len(idx)
    o = [100.0] * n
    h = [100.5] * n
    lo = [99.5] * n
    c = [100.0] * n
    lo[-1] = 85.0
    return pd.DataFrame({"open": o, "high": h, "low": lo, "close": c}, index=idx)


@pytest.mark.parametrize("unit", ["ns", "us", "ms", "s"])
def test_the_reopen_spike_is_clipped_in_every_timestamp_unit(unit):
    out, fixed = clean_reopens(_frame(unit))
    assert len(fixed) == 1, f"{unit}: the reopen bar was not recognised"
    assert out["low"].iloc[-1] == 100.0


def test_a_normal_minute_is_never_a_reopen():
    df = _frame("us")
    df = df.iloc[:-1]  # drop the reopen: no gap left
    df.iloc[-1, df.columns.get_loc("low")] = 85.0  # the same spike, mid-session
    _, fixed = clean_reopens(df)
    assert fixed == []
