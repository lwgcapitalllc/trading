"""
Tests for services.chart_spec._build_misses — the missed-setup markers the price chart draws.

Pure over a temp run dir + a candle list; no DB, no network, no run.

Two contracts live here. The first is the same RECORD-SHAPE discipline as
`test_chart_spec_blocks.py`: `missed_setups.json` is written once at run completion and then
lives on disk forever, so a reader that starts requiring a field silently empties every run
already written. The second is the NOISE LIST — the reason labels the chart starts with
unticked. It is DERIVED from the strategy's own `near` flag, never named here, which is the only
reason the panel can reproduce the Pine's default view without knowing what a confluence is.
"""

import json

from services.chart_spec import _build_misses

_T0 = 1_700_000_000_000
_CANDLES = [{"time": _T0 + i * 900_000, "close": 100.0} for i in range(10)]


def _row(t_off, label, *, near=True, met=3, direction="Long", edge=99.0, met_lines=None):
    return {
        "time_ms": _T0 + t_off * 900_000, "direction": direction, "edge": edge,
        "met": met, "of": 3, "near": near,
        "met_lines": met_lines if met_lines is not None else ["SOS — confirmed"],
        "reasons": [{"label": label, "reason": f"why: {label}"}],
    }


def _write(tmp_path, rows):
    (tmp_path / "missed_setups.json").write_text(json.dumps(rows))
    return tmp_path


def test_no_file_means_no_misses(tmp_path):
    """The honest answer for a runner that cannot report them (NT8/MT5) — and what makes the
    chart's Missed toggle vanish instead of showing an empty switch."""
    assert _build_misses(tmp_path, _CANDLES) == ([], [])


def test_score_and_met_lines_reach_the_chart(tmp_path):
    d = _write(tmp_path, [_row(1, "Never filled", met=3, direction="Short",
                               met_lines=["Arm — Sweep · Day Low", "SOS — confirmed"])])
    out, _ = _build_misses(d, _CANDLES)
    assert len(out) == 1
    assert out[0]["dir"] == "short" and (out[0]["met"], out[0]["of"]) == (3, 3)
    assert out[0]["metLines"] == ["Arm — Sweep · Day Low", "SOS — confirmed"]
    assert out[0]["reasons"] == [{"label": "Never filled", "reason": "why: Never filled"}]


def test_noise_list_is_the_labels_that_never_appear_on_a_near_miss(tmp_path):
    """This is what reproduces the Pine's "Near misses only" default. A label earns its place on
    the chart's opening view by appearing on at least ONE miss the strategy called near; nothing
    here knows or cares which label that is."""
    d = _write(tmp_path, [
        _row(1, "No retrace", near=False, met=2),
        _row(2, "No retrace", near=False, met=2),
        _row(3, "Never filled", near=True),
        _row(4, "Final hour", near=True),
    ])
    out, noise = _build_misses(d, _CANDLES)
    assert len(out) == 4
    assert noise == ["No retrace"]


def test_a_label_seen_on_even_one_near_miss_is_not_noise(tmp_path):
    """A reason is noise only if the strategy NEVER flagged it as worth looking at. One near
    miss is enough to keep it in the opening view — hiding a reason that sometimes matters is a
    worse failure than showing one that usually doesn't."""
    d = _write(tmp_path, [_row(1, "No FVG in zone", near=False, met=2),
                          _row(2, "No FVG in zone", near=True, met=2)])
    _, noise = _build_misses(d, _CANDLES)
    assert noise == []


def test_near_defaults_to_true_on_a_record_that_predates_the_flag(tmp_path):
    """A file written before `near` existed must not have every one of its reasons filed as
    noise and hidden on open — an old run would look like it had no misses at all."""
    d = _write(tmp_path, [{
        "time_ms": _T0 + 900_000, "direction": "Long", "edge": 99.0, "met": 3, "of": 3,
        "reasons": [{"label": "Never filled", "reason": "x"}],
    }])
    out, noise = _build_misses(d, _CANDLES)
    assert out[0]["near"] is True and noise == []


def test_a_record_naming_no_reason_is_dropped(tmp_path):
    """It could be neither filtered nor explained, so drawing it would be a tag that says
    nothing when hovered."""
    d = _write(tmp_path, [{"time_ms": _T0, "direction": "Long", "edge": 99.0, "reasons": []}])
    assert _build_misses(d, _CANDLES) == ([], [])


def test_misses_outside_the_candle_window_are_clipped(tmp_path):
    """klinecharts clamps an out-of-range overlay onto the plot edge, so an unclipped marker
    would pile up in the no-data region instead of sitting on its bar."""
    rows = [_row(-10, "Final hour", edge=1.0), _row(1, "Final hour", edge=2.0)]
    out, _ = _build_misses(_write(tmp_path, rows), _CANDLES)
    assert [m["price"] for m in out] == [2.0]


def test_a_corrupt_file_degrades_to_no_misses(tmp_path):
    (tmp_path / "missed_setups.json").write_text("{not json")
    assert _build_misses(tmp_path, _CANDLES) == ([], [])
