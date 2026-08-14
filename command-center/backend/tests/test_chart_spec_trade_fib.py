"""
Tests for services.chart_spec._trade_fib — the fib LEG the price chart draws under each trade.

Pure over a stored equity-curve point; no DB, no network, no run.

Two contracts live here, and they pull in opposite directions on purpose.

**The levels are PASSED THROUGH.** They are the prices the strategy had in hand when it placed
the order (`backtest/output.py::_trade_fib`), so nothing here may recompute, reorder, round or
"correct" them. A fib rebuilt downstream from anchors and a direction is a second claim about the
same leg, and the repo has been bitten three times by two places claiming one fact.

**The RATIOS are derived here, and they are the reason the layer exists.** A ladder of prices
cannot say where the fill landed on it, which is exactly the question ("what retracement did this
trade go into?"). The derivation is pure geometry off two levels the ladder already carries — a
fib price is linear in its ratio — so it needs no anchor, no direction and no range, and there is
nothing in it that can disagree with the strategy.
"""

from services.chart_spec import _trade_fib

# A real bull leg (high 110 / low 100, so every price is 110 - 10*ratio): 0.0 = the high anchor,
# 1.0 = the low one. These are the A+ bot's own eight ratios at genuine prices — a fixture with
# hand-rounded prices would make every derived ratio here wrong by a hair and prove nothing.
_BULL = [
    [0.0, 110.0],
    [0.382, 106.18],
    [0.5, 105.0],
    [0.618, 103.82],
    [0.702, 102.98],
    [0.786, 102.14],
    [0.886, 101.14],
    [1.0, 100.0],
]
# The bear mirror — 0.0 is the LOW anchor and prices ASCEND with the ratio.
_BEAR = [
    [0.0, 100.0],
    [0.382, 103.82],
    [0.5, 105.0],
    [0.618, 106.18],
    [0.702, 107.02],
    [0.786, 107.86],
    [0.886, 108.86],
    [1.0, 110.0],
]


def _point(levels=None, start_ms=None):
    fib = {"levels": levels if levels is not None else _BULL}
    if start_ms is not None:
        fib["start_ms"] = start_ms
    return {"fib": fib}


# ── optionality ───────────────────────────────────────────────────────────────


def test_a_trade_with_no_fib_gets_none():
    """The honest answer for NT8/MT5, for a Python run finished before the field existed (there
    is no backfill — it would mean replaying the strategy), and for the B-LEG fork, which prices
    its entries off band levels rather than this ladder. It is what makes the chart's Trade fibs
    toggle vanish instead of offering a layer that draws nothing."""
    assert _trade_fib({}, 103.0, 99.0) is None
    assert _trade_fib({"fib": None}, 103.0, 99.0) is None
    assert _trade_fib({"fib": {"levels": []}}, 103.0, 99.0) is None


def test_a_degenerate_leg_gets_none_rather_than_a_division_by_zero():
    """A zero-height leg maps every ratio to one price, so no price has a ratio. Refusing is the
    only honest answer — and the alternative crashes the whole spec build."""
    flat = [[0.0, 100.0], [1.0, 100.0]]
    assert _trade_fib(_point(flat), 100.0, 100.0) is None


# ── the levels are the strategy's, untouched ──────────────────────────────────


def test_the_levels_pass_through_exactly_as_the_strategy_recorded_them():
    out = _trade_fib(_point(), 103.82, 101.5)
    assert out["levels"] == [{"ratio": r, "price": p} for r, p in _BULL]


def test_a_strategy_with_its_own_ladder_is_not_normalised_onto_a_line():
    """Nothing here knows which ratios a fib 'should' have. A strategy shipping a different set
    just ships different pairs, and they arrive as sent."""
    odd = [[0.0, 110.0], [0.236, 107.5], [0.65, 102.9], [1.0, 100.0]]
    out = _trade_fib(_point(odd), 102.9, 101.0)
    assert [(l["ratio"], l["price"]) for l in out["levels"]] == [tuple(x) for x in odd]


def test_the_leg_start_is_carried_as_startTime_and_omitted_when_absent():
    """The x-span the drawing begins at — the bar the LEG started on, so the ladder reaches back
    through the retracement instead of starting at the fill."""
    assert (
        _trade_fib(_point(start_ms=1_700_000_000_000), 103.82, 101.5)["startTime"]
        == 1_700_000_000_000
    )
    assert "startTime" not in _trade_fib(_point(), 103.82, 101.5)


# ── the derived ratios ────────────────────────────────────────────────────────


def test_an_entry_ON_a_level_reports_that_level_s_ratio():
    """The common case: the A+ entry model rests the limit AT a fib on most setups, so a chart
    reading 0.618 where the strategy snapped to 0.618 is the first thing that would be noticed
    if this were wrong."""
    assert _trade_fib(_point(), 103.82, 101.5)["entryRatio"] == 0.618
    assert _trade_fib(_point(), 102.14, 101.5)["entryRatio"] == 0.786


def test_an_entry_BETWEEN_levels_interpolates():
    """The other case: an entry resting on a gap edge lands between two rungs, and its depth is
    still a real number. Midway between 0.5 (105.0) and 0.618 (103.82) is 104.41."""
    assert _trade_fib(_point(), 104.41, 101.5)["entryRatio"] == 0.559


def test_the_bear_mirror_reads_the_same_depths():
    """A short's retracement runs UP, so the prices ascend with the ratio. Depth is a property of
    the leg, not of the direction, and the geometry handles both without a branch — which is the
    point of inverting the ladder rather than reasoning about direction."""
    assert _trade_fib(_point(_BEAR), 106.18, 107.9)["entryRatio"] == 0.618
    assert _trade_fib(_point(_BEAR), 107.86, 108.0)["entryRatio"] == 0.786


def test_deepest_ratio_measures_the_ADVERSE_excursion_not_the_entry():
    """How far the retracement actually ran after the fill — the second half of "what levels did
    it go into". Entering at 0.618 and trading down to the 0.886 is a trade that went most of the
    way to its stop and came back."""
    out = _trade_fib(_point(), 103.82, 101.14)
    assert (out["entryRatio"], out["deepestRatio"]) == (0.618, 0.886)


def test_deepest_ratio_may_exceed_one_and_is_not_clamped():
    """A trade that traded THROUGH the leg origin really did retrace past 1.0 — the stop sits just
    beyond 0.886, so this is what a full stop-out looks like. Clamping it to 1.0 would report
    every stop-out as having stopped exactly at the origin."""
    assert _trade_fib(_point(), 103.82, 99.0)["deepestRatio"] == 1.1


def test_deepest_ratio_is_omitted_when_the_trade_carries_no_adverse_price():
    """Optional in, optional out: a trade duck-type without an MAE price gets no reading rather
    than a zero, which would read as 'it never went against us'."""
    out = _trade_fib(_point(), 103.82, None)
    assert "deepestRatio" not in out
    assert out["entryRatio"] == 0.618


def test_the_ratios_are_read_off_the_LADDER_not_off_assumed_endpoints():
    """The derivation uses the first and last levels it was GIVEN, whatever they are — so a
    partial ladder that never reaches 0.0 or 1.0 still reports correct ratios instead of
    silently rescaling to the range it happens to hold."""
    partial = [[0.5, 105.0], [0.618, 103.82]]  # a 0.118-wide slice of the same leg
    out = _trade_fib(_point(partial), 110.0, 100.0)  # the real 0.0 and 1.0 prices
    assert (out["entryRatio"], out["deepestRatio"]) == (0.0, 1.0)
