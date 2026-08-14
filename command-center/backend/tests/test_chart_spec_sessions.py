"""
The price chart's session windows are the INDICATOR's, and they were not.

🔴 Fixed 2026-08-08 (Aaron confirmed `mpc_assistant.pine` is the correct source). `chart_spec`
shaded Tokyo `09:00-15:00` and London `08:00-16:30` against the indicator's `09:00-18:00` and
`08:00-17:00` — so two of the three session boxes on a backtest chart were SHORTER than the boxes
on the TradingView chart the run is read against, and nothing on either screen said so. New York
matched.

⚠ **The engines already agreed with the indicator; this file was the only dissenter**, which is what
makes it a third statement of one fact rather than a disagreement between two. So the fix is pinned
by COMPARING the two rather than by restating the windows a third time — a test that hardcoded
`09:00`/`18:00` would be a fourth copy, and the next re-sync would leave it stale and green.

These are the tests in this pass that CAN be watched red against HEAD: the fix changed a value, so
reverting `_FX_SESSIONS` turns `test_the_chart_windows_are_the_engines_windows` red naming Tokyo and
London.
"""

import sys
from pathlib import Path

# engines/ on sys.path so the canonical sessions engine imports by bare name — the same shim the
# overlay services use.
_ENGINES = Path(__file__).resolve().parent.parent.parent.parent / "engines"
if str(_ENGINES) not in sys.path:
    sys.path.insert(0, str(_ENGINES))

from services.chart_spec import _FX_SESSIONS

# The chart's display names against the engine's own. The chart says "Tokyo"/"New York" where the
# engine says "Asia"/"NY", deliberately: the panel keys its per-session toggle state on `name`, so a
# rename would silently reset a reader's switches, and these are legend labels rather than an
# identifier anything resolves through.
_DISPLAY_TO_ENGINE = {"Tokyo": "Asia", "London": "London", "New York": "NY"}


def _engine_specs():
    """The canonical engine's own default windows, read off the class rather than restated."""
    from sessions.engine import SessionEngine

    return {s.name: s for s in SessionEngine.DEFAULT_SESSIONS}


def _hhmm(minute_of_day: int) -> str:
    return f"{minute_of_day // 60:02d}:{minute_of_day % 60:02d}"


def test_the_chart_windows_are_the_engines_windows():
    """🔴 The fix. Every shaded session on the price chart must span the window the canonical engine
    tracks, because that engine is the port of `mpc_assistant.pine`'s session block — so a box on
    this chart and a box on the TradingView chart describe the same hours.

    WATCHED RED against HEAD: reverting `_FX_SESSIONS` fails naming Tokyo (15:00 against 18:00) and
    London (16:30 against 17:00).
    """
    specs = _engine_specs()
    for row in _FX_SESSIONS:
        spec = specs[_DISPLAY_TO_ENGINE[row["name"]]]
        assert row["start"] == _hhmm(spec.start_minute), (
            f"{row['name']} starts {row['start']} on the chart, {_hhmm(spec.start_minute)} in the engine"
        )
        assert row["end"] == _hhmm(spec.end_minute), (
            f"{row['name']} ends {row['end']} on the chart, {_hhmm(spec.end_minute)} in the engine"
        )


def test_each_window_is_stated_in_its_own_citys_clock():
    """The timezone is what makes a window DST-aware: stated in its own city's clock it does not move
    when that city changes its clocks, while its UTC span does — which is why, read on a fixed-offset
    chart, London and New York shift an hour twice a year and Tokyo never does.

    A window re-stated as a fixed GMT offset would be wrong for ~7 months a year and would look right
    for the other five, which is why the zone is pinned rather than left to review.
    """
    specs = _engine_specs()
    for row in _FX_SESSIONS:
        spec = specs[_DISPLAY_TO_ENGINE[row["name"]]]
        assert row["tz"] == spec.tz_name, (
            f"{row['name']} is drawn in {row['tz']}, tracked in {spec.tz_name}"
        )
        assert "GMT" not in row["tz"], "a fixed GMT offset cannot follow that city's DST"


def test_the_chart_covers_every_session_the_engine_tracks():
    """A session the engine tracks and the chart never shades is a window a reader cannot see —
    which reads as a quiet market rather than as a missing layer. Checked in both directions so
    neither side can grow a session alone."""
    specs = _engine_specs()
    assert set(_DISPLAY_TO_ENGINE.values()) == set(specs), (
        f"engine sessions {sorted(specs)} against charted {sorted(_DISPLAY_TO_ENGINE.values())}"
    )
    assert len(_FX_SESSIONS) == len(specs)


def test_no_charted_window_wraps_past_midnight():
    """All three windows are same-day in their own city, and the chart's placement math
    (`ChartPanel/sessions.ts`) resolves one local date to one span on that basis. A window that
    wrapped would need its own handling there, so if one is ever added this fails first — rather
    than the box silently being drawn on the wrong day."""
    specs = _engine_specs()
    for row in _FX_SESSIONS:
        spec = specs[_DISPLAY_TO_ENGINE[row["name"]]]
        assert spec.start_minute < spec.end_minute, (
            f"{row['name']} wraps midnight in its own clock — the chart's placement cannot express it"
        )
