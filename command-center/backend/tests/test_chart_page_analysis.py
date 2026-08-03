"""
Tests for services.chart_spec._page_analysis — the ANALYSIS served alongside a paged-in window of
older bars (structure overlays, fair value gaps, blocked and missed setups).

Why it exists: everything the price chart draws EXCEPT the trades is emitted per-window. The spec
ships only the newest slice of a long run (`_capped_start`) and the panel pages the rest in on
scroll-left, so before this path a Structure / Fair Value Gaps / Blocked / Missed layer went
silently empty the moment the chart scrolled past the shipped candles — with its toggle still
reading ON, which is indistinguishable from the panel having forgotten the setting.

The candles are synthetic, so these tests pin the CONTRACT (window clipping, the warm-up prefix,
the historic demotion, graceful degradation), not the engines' own output — those have their own
Pine-parity harnesses.
"""

import json
from unittest.mock import patch

import pytest

from services import chart_spec
from services.structure_overlays import GROUP_INTERNAL, GROUP_INTERNAL_HISTORIC

_MIN = 60_000
_T0 = 1_700_000_000_000          # a round epoch; exact date is irrelevant


def _candles(n, start=_T0, step=15 * _MIN):
    """A gently zig-zagging M15 series — enough shape for the structure engine to find swings."""
    out = []
    for i in range(n):
        base = 2000.0 + (i % 40) * (1.0 if (i // 40) % 2 == 0 else -1.0)
        out.append({
            "time": start + i * step,
            "open": base, "high": base + 1.5, "low": base - 1.5, "close": base + 0.5,
        })
    return out


@pytest.fixture
def run_row(tmp_path):
    return {"equity_curve_path": None, "instrument": "XAUUSD", "runner": "python"}


def _analysis(candles, from_ms, to_ms, run_id="R1"):
    with patch.object(chart_spec, "_build_candles", return_value=candles):
        return chart_spec._page_analysis(
            run_id, {"equity_curve_path": None}, "XAUUSD", "python", "M15", from_ms, to_ms,
        )


def test_a_page_carries_its_own_overlays(run_row):
    """The whole point: a window the spec never shipped still gets its structure."""
    candles = _candles(1200)
    from_ms = candles[400]["time"]
    out = _analysis(candles, from_ms, candles[-1]["time"])
    assert out["overlays"], "a paged window with real structure must not come back bare"


def test_warmup_bars_are_context_not_content(run_row):
    """The engines replay over `_PAGE_WARMUP_BARS` of older bars so a page does not open cold — but
    an overlay that lives entirely inside that prefix belongs to the PREVIOUS page and must not be
    served twice."""
    candles = _candles(1200)
    from_ms = candles[600]["time"]
    out = _analysis(candles, from_ms, candles[-1]["time"])
    assert out["overlays"], "nothing to clip means this test proves nothing"
    for ov in out["overlays"]:
        end = ov["t"] if ov["type"] in ("vline", "label") else ov["t1"]
        assert end >= from_ms


def test_internal_structure_is_demoted_to_historic():
    """`build_market_structure_overlays` calls the newest leg in whatever it replayed "current", so
    a page would file its own last leg under `Internal Structure` — the group that means "the leg
    the run is in NOW", which only ever lives in the shipped window. Several pages each claiming a
    current leg would make that toggle describe something that does not exist."""
    out = chart_spec._demote_page_internal([
        {"type": "hline", "group": GROUP_INTERNAL, "t0": 1, "t1": 2, "price": 1.0},
        {"type": "label", "group": "Swing Point Labels", "t": 3, "price": 1.0, "text": "iSH",
         "requires": [GROUP_INTERNAL]},
        {"type": "hline", "group": "External Structure", "t0": 1, "t1": 2, "price": 1.0},
    ])
    assert out[0]["group"] == GROUP_INTERNAL_HISTORIC
    assert out[0]["requires"] == [GROUP_INTERNAL]           # historic break: needs Internal on
    assert out[1]["requires"] == [GROUP_INTERNAL, GROUP_INTERNAL_HISTORIC]  # tag: needs both
    assert out[2] == {"type": "hline", "group": "External Structure", "t0": 1, "t1": 2, "price": 1.0}


def test_a_page_never_claims_a_current_internal_leg(run_row):
    """The same rule, end to end through `_page_analysis`."""
    candles = _candles(1200)
    out = _analysis(candles, candles[300]["time"], candles[-1]["time"])
    assert GROUP_INTERNAL not in {ov["group"] for ov in out["overlays"]}


def test_no_candles_degrades_to_empty(run_row):
    """A feed that cannot serve the window still delivers a well-formed (empty) analysis — the page
    is about its BARS; the layers are a bonus that must never break it."""
    out = _analysis([], _T0, _T0 + 100 * _MIN)
    assert out == {"overlays": [], "blocks": [], "misses": [], "missNoise": []}


def test_unknown_timeframe_is_refused_rather_than_guessed(run_row):
    """The warm-up span is measured in BARS, so it needs the bar size. A timeframe we cannot size
    would silently get no warm-up at all — better to serve nothing than a cold, wrong replay."""
    with patch.object(chart_spec, "_build_candles", return_value=_candles(500)):
        out = chart_spec._page_analysis(
            "R1", {"equity_curve_path": None}, "XAUUSD", "python", "W1", _T0, _T0 + 500 * 15 * _MIN,
        )
    assert out == {"overlays": [], "blocks": [], "misses": [], "missNoise": []}


def test_blocks_and_misses_come_from_the_run_dir_clipped_to_the_window(tmp_path, monkeypatch):
    """Blocks and misses are read out of the run's own JSON files and clipped to the page. Their
    ids are the record's index in that file, which is what lets the panel merge overlapping pages
    without double-drawing a marker."""
    monkeypatch.setattr(chart_spec, "LAB_RESULTS_DIR", tmp_path)
    run_dir = tmp_path / "R1"
    run_dir.mkdir()
    candles = _candles(600)
    inside = candles[400]["time"]
    before = candles[100]["time"]
    (run_dir / "blocked_setups.json").write_text(json.dumps([
        {"time_ms": before, "direction": "Long", "edge": 1.0,
         "reasons": [{"label": "Final hour", "reason": "x"}]},
        {"time_ms": inside, "direction": "Short", "edge": 2.0,
         "reasons": [{"label": "Final hour", "reason": "x"}]},
    ]))
    (run_dir / "missed_setups.json").write_text(json.dumps([
        {"time_ms": inside, "direction": "Long", "edge": 3.0, "met": 2, "of": 3, "near": True,
         "reasons": [{"label": "No FVG", "reason": "y"}]},
    ]))
    out = _analysis(candles, candles[300]["time"], candles[-1]["time"])
    assert [b["id"] for b in out["blocks"]] == ["B2"]      # index in the FILE, not in the page
    assert [m["id"] for m in out["misses"]] == ["M1"]
