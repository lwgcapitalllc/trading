"""
Tests for services.chart_spec._build_blocks — the blocked-setup markers the price chart draws.

Pure over a temp run dir + a candle list; no DB, no network, no run.

The point of this file is the RECORD-SHAPE contract. `blocked_setups.json` is written once at run
completion and then lives on disk forever, while the shape it is read with keeps moving — so every
shape ever written has to keep reading. It already broke once: `reasons` became a list, the reader
started requiring it, and every run already on disk silently lost all 312 of its markers with no
error anywhere.
"""

import json

from services.chart_spec import _build_blocks

_T0 = 1_700_000_000_000
_CANDLES = [{"time": _T0 + i * 900_000, "close": 100.0} for i in range(10)]


def _write(tmp_path, rows):
    (tmp_path / "blocked_setups.json").write_text(json.dumps(rows))
    return tmp_path


def test_no_file_means_no_blocks(tmp_path):
    """The honest answer for a runner that cannot report them (NT8/MT5) — and what makes the
    chart's Blocked toggle vanish instead of showing an empty switch."""
    assert _build_blocks(tmp_path, _CANDLES) == []


def test_current_shape_keeps_every_reason_in_order(tmp_path):
    d = _write(
        tmp_path,
        [
            {
                "time_ms": _T0 + 900_000,
                "direction": "Short",
                "edge": 123.5,
                "codes": [1, 3],
                "reasons": [
                    {"label": "Direction off", "reason": "a"},
                    {"label": "Final hour", "reason": "b"},
                ],
            }
        ],
    )
    out = _build_blocks(d, _CANDLES)
    assert len(out) == 1
    assert out[0]["dir"] == "short" and out[0]["price"] == 123.5
    assert [r["label"] for r in out[0]["reasons"]] == ["Direction off", "Final hour"]


def test_pre_list_shape_still_reads(tmp_path):
    """THE REGRESSION. A file written before `reasons` was a list carries one `label`/`reason`
    pair; it must read as a one-item list, not vanish. Runs already on disk cannot be rewritten."""
    d = _write(
        tmp_path,
        [
            {
                "time_ms": _T0 + 900_000,
                "direction": "Long",
                "edge": 99.0,
                "code": 3,
                "label": "Final hour",
                "reason": "no new entries 16:00-18:00 NY",
            }
        ],
    )
    out = _build_blocks(d, _CANDLES)
    assert len(out) == 1
    assert out[0]["dir"] == "long"
    assert out[0]["reasons"] == [{"label": "Final hour", "reason": "no new entries 16:00-18:00 NY"}]


def test_a_record_naming_no_rule_is_dropped(tmp_path):
    """It could be neither filtered nor explained, so drawing it would be a tag that says
    nothing when hovered."""
    d = _write(tmp_path, [{"time_ms": _T0, "direction": "Long", "edge": 99.0, "reasons": []}])
    assert _build_blocks(d, _CANDLES) == []


def test_blocks_outside_the_candle_window_are_clipped(tmp_path):
    """klinecharts clamps an out-of-range overlay onto the plot edge, so an unclipped marker
    would pile up in the no-data region instead of sitting on its bar."""
    rows = [
        {
            "time_ms": _T0 - 10 * 900_000,
            "direction": "Long",
            "edge": 1.0,
            "reasons": [{"label": "Final hour", "reason": "x"}],
        },
        {
            "time_ms": _T0 + 900_000,
            "direction": "Long",
            "edge": 2.0,
            "reasons": [{"label": "Final hour", "reason": "x"}],
        },
    ]
    out = _build_blocks(_write(tmp_path, rows), _CANDLES)
    assert [b["price"] for b in out] == [2.0]


def test_a_corrupt_file_degrades_to_no_blocks(tmp_path):
    (tmp_path / "blocked_setups.json").write_text("{not json")
    assert _build_blocks(tmp_path, _CANDLES) == []
