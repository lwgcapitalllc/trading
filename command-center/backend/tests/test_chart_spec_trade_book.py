"""Which BOOK a trade came from, and — for a re-entry — what the trade it FOLLOWED did.

Aaron, 2026-08-21, reading a chart with both re-entry triggers on: *"fix the label line so I could
tell the difference between a secondary that was re-entering from a breakeven versus a secondary
that's re-entering from the original primary trade at a stop loss."* Both wore one `SEC`, and on
that run there are 107 of them.

The chart draws `BE+` / `SL+` off `after`; this file pins the half that decides whether `after`
reaches it at all. ⚠ The tag itself is NOT tested here — the panel is TypeScript and this is the
python side of the wire. What these hold is that the field crosses, and that an ABSENT one stays
absent rather than becoming a word.
"""

from services.chart_spec import _build_trades

_CANDLES = [{"time": 1_000, "open": 100.0, "high": 101.0, "low": 99.0, "close": 100.0}]


def _point(**kw):
    p = {
        "direction": "Long",
        "entry_ms": 1_000,
        "exit_ms": 2_000,
        "entry_price": 100.0,
        "exit_price": 101.0,
        "profit": 100.0,
        "equity": 10_100.0,
    }
    p.update(kw)
    return p


def _one(**kw):
    return _build_trades([_point(**kw)], _CANDLES)[0]


def test_a_reentry_carries_what_the_trade_before_it_did():
    """MUTATION: drop the `after` line from `_build_trades` and both go red."""
    assert _one(kind="secondary", after="stopped")["after"] == "stopped"
    assert _one(kind="secondary", after="breakeven")["after"] == "breakeven"


def test_a_run_that_could_not_tell_carries_NOTHING_rather_than_a_guess():
    """🔴 The half that matters. A re-entry can be armed through a precondition that asks nothing
    of the trade before it, and every run stored before 2026-08-21 has no `after` at all. The
    chart falls back to the plain book tag on an absent one — so an empty string arriving as
    `"after": ""` would make it read a falsy value where it expects a word.

    MUTATION: change the emit to an unconditional `p.get("after")` and this goes red on all three.
    """
    for missing in ({}, {"after": None}, {"after": ""}):
        assert "after" not in _one(kind="secondary", **missing)


def test_a_non_string_after_is_dropped_rather_than_shipped():
    """An equity curve is JSON somebody else wrote. MUTATION: drop the isinstance check."""
    assert "after" not in _one(kind="secondary", after=1)
    assert "after" not in _one(kind="secondary", after=["stopped"])


def test_the_book_tag_itself_still_crosses_untouched():
    """The field this one sits beside, so a regression in either is visible here.
    MUTATION: default `kind` to "secondary" and the last case goes red."""
    assert _one(kind="secondary")["kind"] == "secondary"
    assert _one(kind="recovery")["kind"] == "recovery"
    assert _one(kind="primary")["kind"] == "primary"
    assert (
        _one()["kind"] == "primary"
    )  # absent ⇒ primary, which is what every runner but python sends
