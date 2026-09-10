"""The lab stack's entry-band wiring reproduces Pine's gap list, bar for bar, on a real export.

WHAT THIS PROVES THAT NOTHING ELSE CAN
--------------------------------------
`compare_fvg.py` validates the ENGINE, fed the band Pine exported. This validates the STACK: its own
structure engine and its own Structure fib compute the band, the stack lags it by one bar, and the
FVG cap reads it - and the resulting gap list must equal the one TradingView drew.

🔴 The one-bar lag is the whole reason this file exists. In `mpc_jarvis.pine` the FVG block runs ~800
lines ABOVE the fib block, so the cap only ever sees LAST bar's band. In the stack the fib runs BEFORE
the FVG inside one step, so the natural wiring is a one-bar look-AHEAD. Both readings are reasonable,
both pass every unit test in the engine, and only one matches the chart. MUTATION-PROVEN: feeding
this bar's band instead of last bar's diverges on 2,972 of 20,187 bars, throughout the file.

The export is `engines/fair_value_gaps/exports/golden/..._zone.csv`, taken off
`indicators/engines/fvg_zone_export.pine`. Its settings are that HARNESS's (cap 8, 0.04 floor, no
middle-bar close test, EQ exemption on) - neither the indicator's (cap 7, a 0.1 floor and the close
test from 15m up) nor any bot's. So this pins the wiring, and says nothing about what the band does
to a strategy. That is a separate measurement.
"""

from __future__ import annotations

import csv
from pathlib import Path

import pandas as pd
import pytest

from backtest.replay import iter_bars
from backtest.replay.stack import EngineConfig, EngineStack

_REPO = Path(__file__).resolve().parents[2]
_EXPORT = _REPO / "engines/fair_value_gaps/exports/golden/VANTAGE_XAUUSD_M15_20187bars_zone.csv"


def _num(s):
    s = (s or "").strip()
    return float(s) if s not in ("", "nan", "NaN") else None


def _load():
    rows = list(csv.DictReader(open(_EXPORT, newline="")))[:-1]  # live final bar: gate_common
    cols = {}
    for h in rows[0]:
        cols[h.strip().lower().split(":")[-1].strip()] = h
    df = pd.DataFrame({k: [float(r[k]) for r in rows] for k in ("open", "high", "low", "close")})
    df["volume"] = 0.0
    df.index = pd.to_datetime([int(r["time"]) for r in rows], unit="s", utc=True)
    return rows, cols, df


def _harness_config(zone_on=True):
    # The harness's own settings, read off its cfg_* columns when it was taken - the INDICATOR's.
    # Engines the band and the gap cap never read are switched off: they cannot change the answer
    # (they feed nothing below), and they are most of the replay's cost.
    return EngineConfig(
        fvg_max_count=8,
        fvg_threshold_pct=0.04,
        fvg_require_close=False,
        eq_exempt_fvg=True,
        fvg_exempt_zone=zone_on,
        show_internal=True,
        sniper=False,
        macro=False,
        internal=False,
        rsi=False,
        liquidity=False,
        sessions=False,
    )


@pytest.mark.skipif(not _EXPORT.exists(), reason="golden zone export not present")
def test_stack_reproduces_pines_gap_list_with_the_band_on_every_bar():
    rows, cols, df = _load()
    stack = EngineStack(_harness_config())
    bad = []
    for i, (row, bar) in enumerate(zip(rows, iter_bars(df))):
        band = stack._zone_band  # what the cap is about to read: LAST bar's publish
        active = stack.step(bar).fvg.active

        count = int(float(row[cols["px_fvg_count"]]))
        ok = count == len(active)
        ok = ok and abs(sum(g.top for g in active) - _num(row[cols["px_fvg_topsum"]])) < 1e-3
        ok = ok and abs(sum(g.bottom for g in active) - _num(row[cols["px_fvg_botsum"]])) < 1e-3
        for k in range(min(18, count, len(active))):
            ok = ok and abs(active[k].top - _num(row[cols[f"px_fvg_top_{k + 1}"]])) < 1e-6
            ok = ok and abs(active[k].bottom - _num(row[cols[f"px_fvg_bot_{k + 1}"]])) < 1e-6

        # The band itself, as consumed - so a wrong band cannot hide behind a lucky gap list.
        zd = _num(row[cols["px_fvgzone_dir"]])
        ok = ok and int(zd or 0) == band[2]
        zl = _num(row[cols["px_fvgzone_lo"]])
        if zl is not None or band[0] is not None:
            ok = ok and zl is not None and band[0] is not None and abs(zl - band[0]) < 1e-6
        if not ok:
            bad.append(i)
    assert not bad, f"{len(bad)} bars disagree with Pine; first {bad[:5]}"


@pytest.mark.skipif(not _EXPORT.exists(), reason="golden zone export not present")
def test_the_band_actually_changes_the_gap_list_on_this_export():
    """Non-vacuity. Without it the test above would pass for a stack that ignores the band.

    Measured on this export the band changes the live gap list on most bars; this asserts only that
    it changes it at all, and by a real margin, so the pairing cannot quietly collapse into two runs
    of the same thing.
    """
    _, _, df = _load()
    on, off = EngineStack(_harness_config(True)), EngineStack(_harness_config(False))
    differ = sum(len(on.step(b).fvg.active) != len(off.step(b).fvg.active) for b in iter_bars(df))
    assert differ > 5_000, f"the band changed the gap count on only {differ} bars"


def test_the_exemption_is_refused_without_the_engines_it_reads():
    with pytest.raises(ValueError, match="fvg_exempt_zone"):
        EngineStack(EngineConfig(fvg_exempt_zone=True, fib=False))
    with pytest.raises(ValueError, match="fvg_exempt_zone"):
        EngineStack(EngineConfig(fvg_exempt_zone=True, fvg=False))
