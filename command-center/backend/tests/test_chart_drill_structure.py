"""The drill-down window carries its OWN market structure.

🔴 **Structure was computed once, on the timeframe the run TRADED, and drawn over whatever candles
were on screen.** A drill-down replaces the candles and nothing replaced the overlays, so an M5 view
of a 15m run painted M15 swings on M5 bars — every label at a price that is not a swing on anything
visible. Reported by Aaron on 2026-08-08 with two screenshots: the command-center chart's own OHLC
readout was the M5 bar (`C 4,339.80  V 908`, the M5 cache row to the cent) while its labels read
`SOS @4242.99` and `iSL @4247.23`, which are M15 answers. The M5 answer is `SOS @4224.73`, which is
exactly what the TradingView indicator drew for the same window.

Nothing errored, and both halves were internally correct — which is why it read as the ported
structure engine disagreeing with the indicator rather than as a chart drawing the wrong layer.

⚠ **`test_the_unit_is_stated_not_assumed` is the odd one out and is NOT about the drill-down.** It
pins the candle timestamp UNIT, and it is a latent bug rather than a live one: the app's venv is on
pandas 2.3.3, where a parsed `DatetimeIndex` is `datetime64[ns]` and the old nanos-to-millis divide
was right. pandas 3 makes MICROseconds the default, and the same divide then yields epoch SECONDS —
timestamps 1000x too small, under a field named `_ms`. Measured on pandas 3.0.5: `2026-08-05 00:00`
came back as `1785888000` instead of `1785888000000`.
"""

import pandas as pd
import pytest

from services import chart_spec
from services.structure_overlays import (
    GROUP_EXTERNAL,
    GROUP_INTERNAL,
    GROUP_INTERNAL_HISTORIC,
    GROUP_SWING_LABELS,
)

DAY = 24 * 60 * 60 * 1000


def _label(group, t, requires=None):
    ov = {"type": "label", "group": group, "t": t, "price": 1.0, "text": "HH"}
    if requires:
        ov["requires"] = requires
    return ov


def _hline(group, t0, t1):
    return {"type": "hline", "group": group, "t0": t0, "t1": t1, "price": 1.0}


def test_warmup_overlays_are_context_never_content(monkeypatch):
    """Only overlays REACHING INTO the window are returned.

    The engine is a streaming state machine, so a drill-down is replayed over 2,000 bars of older
    context before the window the reader sees. Shipping that context's overlays would draw
    structure off the left edge of the chart, on bars nobody asked for.
    """
    lo, hi = 10 * DAY, 20 * DAY
    built = [
        _label(GROUP_EXTERNAL, 5 * DAY),        # wholly in the warm-up
        _label(GROUP_EXTERNAL, 15 * DAY),       # inside
        _hline(GROUP_EXTERNAL, 5 * DAY, 12 * DAY),   # starts in warm-up, REACHES IN
        _hline(GROUP_EXTERNAL, 1 * DAY, 4 * DAY),    # wholly in the warm-up
    ]
    monkeypatch.setattr(chart_spec, "build_market_structure_overlays", lambda c: built)
    got = chart_spec._drill_structure([{"time": lo}], lo, hi)
    assert len(got) == 2
    assert got[0]["t"] == 15 * DAY
    assert got[1]["t0"] == 5 * DAY  # a line crossing the boundary is kept whole


def test_internal_content_is_demoted_to_historic(monkeypatch):
    """A drill-down window ends at the READER'S VIEWPORT, not at the run.

    `build_market_structure_overlays` calls the newest leg in whatever it replayed "current", so
    paging older would mint a second, third, fourth "current" leg — for a group whose entire meaning
    is *the leg this run is in now*. Same call the deleted `_demote_page_internal` made.
    """
    lo, hi = 0, 100 * DAY
    built = [
        _hline(GROUP_INTERNAL, 10 * DAY, 20 * DAY),
        _label(GROUP_SWING_LABELS, 15 * DAY, requires=[GROUP_INTERNAL]),
        _label(GROUP_SWING_LABELS, 16 * DAY, requires=[GROUP_EXTERNAL]),
    ]
    monkeypatch.setattr(chart_spec, "build_market_structure_overlays", lambda c: built)
    got = chart_spec._drill_structure([{"time": lo}], lo, hi)

    assert got[0]["group"] == GROUP_INTERNAL_HISTORIC
    assert got[0]["requires"] == [GROUP_INTERNAL]
    # An internal swing TAG stays in the labels group and takes the dependency through `requires`.
    assert got[1]["group"] == GROUP_SWING_LABELS
    assert got[1]["requires"] == [GROUP_INTERNAL, GROUP_INTERNAL_HISTORIC]
    # An EXTERNAL tag is untouched — only internal content is ambiguous about which leg is current.
    assert got[2]["requires"] == [GROUP_EXTERNAL]


def test_a_failed_replay_costs_the_page_its_structure_not_its_bars(monkeypatch):
    """A drill-down is about its BARS. Structure is a bonus and may never take the window down."""
    def boom(_):
        raise RuntimeError("engine exploded")
    monkeypatch.setattr(chart_spec, "build_market_structure_overlays", boom)
    assert chart_spec._drill_structure([{"time": 0}], 0, DAY) == []


def test_no_candles_is_no_structure(monkeypatch):
    monkeypatch.setattr(chart_spec, "build_market_structure_overlays",
                        lambda c: pytest.fail("must not replay an empty window"))
    assert chart_spec._drill_structure([], 0, DAY) == []


@pytest.mark.parametrize("unit", ["ns", "us", "ms"])
def test_the_unit_is_stated_not_assumed(monkeypatch, unit):
    """A candle timestamp is epoch MILLIS whatever resolution pandas chose for the index.

    `astype("int64")` yields the index's OWN unit. `// 1_000_000` is only nanos-to-millis on a
    `datetime64[ns]` index — the sole resolution pandas 1.x had, the default in pandas 2, and NOT
    the default in pandas 3, which parses to microseconds. Under `us` the old code returns epoch
    seconds; under `ms` it returns kiloseconds. Both are silent, and both are wrong by a factor of
    1000 in a field called `time` that every consumer reads as ms.
    """
    idx = pd.DatetimeIndex(["2026-08-05 00:00", "2026-08-05 00:15"], name="time").as_unit(unit)
    df = pd.DataFrame({"open": [1.0] * 2, "high": [2.0] * 2, "low": [0.5] * 2, "close": [1.5] * 2},
                      index=idx)
    monkeypatch.setattr(chart_spec.ohlc_fetcher, "get_ohlc", lambda *a, **k: df)
    rows = chart_spec._build_candles("XAUUSD", "2026-08-05", "2026-08-05", "M5", "python")
    assert [r["time"] for r in rows] == [1785888000000, 1785888900000]
