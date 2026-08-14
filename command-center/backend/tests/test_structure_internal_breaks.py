"""An internal break line runs from the WICK THAT BROKE to the bar that broke it.

🔴 **It used to take both its price and its bar from `ifib_seed_ash`/`_asl`, and that is wrong at
one of the engine's six internal-break sites.** The seed is a fib LEG — a low and a high — and at
five sites the end of that leg happens to be the level that broke. At the FIRST bear-iSOS branch it
is not: the break is `i_last_hl` while the seed's bottom is `i_tracked_ext`, a different price on a
different bar.

⚠ **The reported symptom was the LINE, not the price.** Aaron, 2026-08-08, off the chart: *"the
Command center internal SOS is not showing the horizontal lines like the mpc_assistant"*. A wrong
anchor bar can land on the break bar itself, and a zero-width `hline` draws NOTHING — so the `iSOS`
tag rendered with no line beneath it while the price it named was also wrong. On his own window one
iSOS spanned 0 bars and another spanned 1.

MEASURED over 2.5 years of real cached M5 bars, 169 internal breaks:

    branch      total   anchor on the broken wick (before -> after)
    iBOS bull      65   65/65  ->  65/65
    iBOS bear      57   57/57  ->  57/57
    iSOS bull      22   22/22  ->  22/22
    iSOS bear      25    3/25  ->  25/25          <-- 22 drawn at the wrong price, by up to $18.47
    lines <=1 bar long (invisible):  21/169 -> 0/169

⚠ **`int_break_origin_loc` is not a substitute and must never be used here** — it is the
order-block scan origin, and over the same 169 breaks it lands on the broken wick ZERO times in
every category. That is why the engine had to grow `*_bos_loc` / `*_sos_loc` rather than the
overlay picking a different existing field.
"""

import sys
from pathlib import Path

import pytest

_ENGINES = Path(__file__).resolve().parent.parent.parent.parent / "engines"
if str(_ENGINES) not in sys.path:
    sys.path.insert(0, str(_ENGINES))

from services.structure_overlays import (  # noqa: E402
    GROUP_INTERNAL,
    GROUP_INTERNAL_HISTORIC,
    build_market_structure_overlays,
)

_M5_CACHE = (
    Path(__file__).resolve().parent.parent.parent.parent / "backtest" / "cache" / "XAUUSD__M5.csv"
)
_INTERNAL_GROUPS = {GROUP_INTERNAL, GROUP_INTERNAL_HISTORIC}


def _real_candles(start: str, end: str) -> list[dict]:
    """Real cached bars. The defect lives in a branch that fires on genuine price action, and a
    hand-built fixture asserting the shape it ALREADY produces is how a fixture ends up more
    complete than production."""
    import csv
    from datetime import datetime, timezone

    if not _M5_CACHE.exists():
        pytest.skip(f"no bar cache at {_M5_CACHE}")
    out = []
    with open(_M5_CACHE) as f:
        for r in csv.DictReader(f):
            if not (start <= r["time"] <= end):
                continue
            ts = datetime.strptime(r["time"], "%Y-%m-%d %H:%M:%S").replace(tzinfo=timezone.utc)
            out.append(
                {
                    "time": int(ts.timestamp() * 1000),
                    "open": float(r["open"]),
                    "high": float(r["high"]),
                    "low": float(r["low"]),
                    "close": float(r["close"]),
                }
            )
    return out


def _internal_break_lines(overlays, candles):
    """Every internal break LINE, paired with the candle its left edge sits on."""
    by_time = {c["time"]: c for c in candles}
    out = []
    for ov in overlays:
        if ov["type"] != "hline" or ov["group"] not in _INTERNAL_GROUPS:
            continue
        start = by_time.get(ov["t0"])
        if start is not None:
            out.append((ov, start))
    return out


# Aaron's own window, plus a long sample so the verdict is not about one screenshot.
_WINDOWS = [
    pytest.param("2026-08-05 06:00:00", "2026-08-07 17:00:00", id="aarons-window"),
    pytest.param("2025-01-01 00:00:00", "2026-08-07 20:55:00", id="19-months"),
]


def _engine_breaks(candles):
    """{break bar time -> {prices the ENGINE says broke on that bar}}, replayed independently."""
    from market_structure import StructureEngine
    from market_structure.types import Bar

    eng = StructureEngine()
    out: dict[int, set[float]] = {}
    for i, c in enumerate(candles):
        n = eng.update(
            Bar(index=i, open=c["open"], high=c["high"], low=c["low"], close=c["close"])
        ).internal
        prices = {
            p
            for fired, p in (
                (n.bull_bos, n.bull_bos_price),
                (n.bear_bos, n.bear_bos_price),
                (n.bull_sos, n.bull_sos_price),
                (n.bear_sos, n.bear_sos_price),
            )
            if fired and p is not None
        }
        if prices:
            out[c["time"]] = prices
    return out


@pytest.mark.parametrize("start,end", _WINDOWS)
def test_an_internal_break_line_names_the_price_the_engine_says_broke(start, end):
    """The line's PRICE must be the engine's own break price for that bar.

    ⚠ **The obvious version of this test is VACUOUS and was caught passing against the defect.**
    Asserting only that the line starts on a bar whose wick carries the line's own price checks the
    anchor against ITSELF — and under the defect the price and the bar are a matched pair taken
    from the fib seed, so it sits perfectly on a wick while describing a level that never broke.
    A comparator that agrees with the thing it is checking is not a comparator.

    So the engine is replayed independently and the drawing is diffed against it.
    """
    candles = _real_candles(start, end)
    truth = _engine_breaks(candles)
    lines = _internal_break_lines(build_market_structure_overlays(candles), candles)
    assert lines, "no internal breaks in this window — the check would be vacuous"

    wrong = []
    for ov, _ in lines:
        # `t1` is the bar that broke; `t0` is the wick that made the level.
        expected = truth.get(ov["t1"], set())
        if not any(abs(p - ov["price"]) < 0.005 for p in expected):
            wrong.append((ov["t1"], ov["price"], sorted(expected)))
    assert not wrong, (
        f"{len(wrong)} of {len(lines)} internal break lines are drawn at a price the engine never "
        f"reported as broken on that bar; first three (bar, drawn, engine): {wrong[:3]}"
    )


@pytest.mark.parametrize("start,end", _WINDOWS)
def test_an_internal_break_line_starts_on_the_wick_that_broke(start, end):
    """And the left edge is the bar carrying that price — so the line spans the real leg.

    Kept BESIDE the price check rather than merged into it: the price test would still pass if the
    bar were right and the price wrong, and this one would still pass if both were wrong together.
    Only the pair pins the drawing.
    """
    candles = _real_candles(start, end)
    lines = _internal_break_lines(build_market_structure_overlays(candles), candles)
    assert lines, "no internal breaks in this window — the check would be vacuous"

    misses = []
    for ov, start_candle in lines:
        # An up-break breaks a HIGH, so its level is that bar's high; a down-break, its low.
        bull = ov["style"]["color"] in ("#80cbc4", "#26a69a")
        wick = start_candle["high"] if bull else start_candle["low"]
        if abs(wick - ov["price"]) >= 0.005:
            misses.append((ov["t0"], ov["price"], wick))
    assert not misses, (
        f"{len(misses)} of {len(lines)} internal break lines start on a bar that does not carry "
        f"the broken level; first three: {misses[:3]}"
    )


@pytest.mark.parametrize("start,end", _WINDOWS)
def test_no_internal_break_line_is_invisible(start, end):
    """A zero-width hline draws nothing, which is the symptom that was actually reported.

    ⚠ This is a SEPARATE assertion from the one above and not a duplicate of it: a line can start
    on the correct wick and still be short, and — the case that matters — a wrongly-anchored line
    is only reported as a bug when it collapses to nothing. Pinning the price alone would leave the
    reader's actual complaint uncovered.
    """
    candles = _real_candles(start, end)
    lines = _internal_break_lines(build_market_structure_overlays(candles), candles)
    assert lines, "no internal breaks in this window — the check would be vacuous"

    degenerate = [ov["t0"] for ov, _ in lines if ov["t1"] <= ov["t0"]]
    assert not degenerate, (
        f"{len(degenerate)} of {len(lines)} internal break lines have zero or negative width and "
        f"would render as nothing: {degenerate[:3]}"
    )


def test_the_break_bar_is_the_engines_own_and_not_the_fib_seed():
    """Pins WHICH engine field the anchor comes from, at the one site where they disagree.

    The two assertions above are properties of the drawing and would both pass if a future edit
    re-derived the bar some other plausible way. This one names the contract: on a bear iSOS the
    engine's `bear_sos_loc` is the bar of `bear_sos_price`, and `ifib_seed_asl` is a DIFFERENT
    price — so a consumer reading the seed is reading the wrong thing by construction.
    """
    from market_structure import StructureEngine
    from market_structure.types import Bar

    candles = _real_candles("2024-01-01 00:00:00", "2026-08-07 20:55:00")
    eng = StructureEngine()
    disagreements = 0
    checked = 0
    for i, c in enumerate(candles):
        n = eng.update(
            Bar(index=i, open=c["open"], high=c["high"], low=c["low"], close=c["close"])
        ).internal
        if not n.bear_sos:
            continue
        checked += 1
        assert n.bear_sos_loc is not None, "a bear iSOS must carry the bar of the level it broke"
        assert abs(candles[n.bear_sos_loc]["low"] - n.bear_sos_price) < 0.005
        if n.ifib_seed_asl is not None and abs(n.ifib_seed_asl - n.bear_sos_price) >= 0.005:
            disagreements += 1

    assert checked, "no bear iSOS in the sample — the check would be vacuous"
    assert disagreements, (
        "the fib seed agreed with the break price on every bear iSOS in this sample, so this test "
        "cannot show that reading the seed is wrong — widen the window"
    )
