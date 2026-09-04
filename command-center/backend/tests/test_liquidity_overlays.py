"""
Tests for services/liquidity_overlays.py — the liquidity-level layer on the price chart.

They pin the EMITTER: which levels get drawn (only those live at a trade / blocked / missed anchor),
where each line starts and stops, and — the reason the layer exists — that a level price has TAKEN
is drawn as taken and labelled with which side of liquidity went.

⚠ **A fail-watch against HEAD is VACUOUS for every test in this file**, because the module did not
exist at HEAD and `ANALYSIS_GROUPS` had no liquidity rows to route them into. Non-vacuity is
established by MUTATION instead, and the mutations that turn each group red are named in the
docstrings below. The one test here that CAN be watched red against HEAD is in
`test_chart_spec_sessions.py` — that fix changed a value rather than adding a file.

⚠ **`test_the_derived_sweep_label_agrees_with_the_engines_own` is the load-bearing one.** The layer
derives BSL/SSL from a level's side for every tier, because the Pine's own liquidity rows do
(`liq_dh := "BSL"`, `liq_ash := "BSL"`, …) while the ENGINE models `sweep_label` on the h4 kind
alone. A derivation sitting beside a value somebody else computed is this repo's most-repeated
defect, so the two are checked against each other on real h4 sweeps rather than assumed to agree.
"""

import sys
from pathlib import Path

# engines/ on sys.path so the tests that drive the canonical engine directly — the sweep-label
# cross-check and the kind roster — import it the same way the module under test does.
_ENGINES = Path(__file__).resolve().parent.parent.parent.parent / "engines"
if str(_ENGINES) not in sys.path:
    sys.path.insert(0, str(_ENGINES))

from services.liquidity_overlays import (
    _KIND_GROUP,
    _SWEPT_COLOR,
    GROUP_LIQ_H4,
    GROUP_LIQ_HTF,
    GROUP_LIQ_SESSION,
    GROUPS,
    build_liquidity_overlays,
    sweep_label_for,
)

BAR_MS = 15 * 60 * 1000
# 2024-01-02 00:00 UTC — a Tuesday, so the feed opens mid-week and the day/H4 trackers roll on
# ordinary boundaries rather than on a weekend the engine treats specially.
START_MS = 1704153600000


def _walk(n, base=2000.0, drift=0.0, rng=3.0, start=START_MS):
    """`n` M15 bars on a real UTC grid, each `drift` above the last.

    A liquidity level needs a COMPLETED period behind it, so a feed has to span real days for the
    daily tier and real sessions for the session tier — hand-typed bars cannot do it.
    """
    out = []
    price = base
    for i in range(n):
        out.append(
            {
                "time": start + i * BAR_MS,
                "open": price,
                "high": price + rng,
                "low": price - rng,
                "close": price + drift,
            }
        )
        price += drift
    return out


def _anchors(candles, *idxs):
    return [candles[i]["time"] for i in idxs]


def _by_group(overlays):
    return {g: [o for o in overlays if o["group"] == g] for g in GROUPS}


# ── what gets drawn at all ───────────────────────────────────────────────────────────────────────


def test_no_anchor_means_no_layer():
    """A run with no trade, block or miss on screen draws nothing — which is what keeps the three
    toggles off an NT8/MT5 chart entirely rather than offering three permanently empty rows.

    MUTATION: drop the `if not bars: return []` guard and this goes red with thousands of levels.
    """
    candles = _walk(400)
    assert build_liquidity_overlays(candles, []) == []


def test_only_levels_live_at_an_anchor_are_drawn():
    """The anchor rule, and the whole reason this layer is affordable.

    A 6.5-year run creates 35,028 levels; anchored it draws 8,174. Both figures are measured on run
    `1bbc8fa7773d` and are in the module docstring.

    MUTATION: mark every level `seen` unconditionally (drop the `if i in bars` branch) and the
    anchored count jumps well past the unanchored one below.
    """
    candles = _walk(700)
    one = build_liquidity_overlays(candles, _anchors(candles, 690))
    many = build_liquidity_overlays(candles, [c["time"] for c in candles])
    assert one, "a real anchor on a multi-day feed must produce levels"
    assert len(one) < len(many), "anchoring must draw strictly fewer levels than every bar would"


def test_an_anchor_off_the_end_of_the_candles_is_ignored():
    """An anchor outside the loaded window belongs to no bar. Clipping it rather than clamping it to
    the last bar is what stops a trade just past the window drawing every level that was live at the
    end of the run."""
    candles = _walk(400)
    past_end = candles[-1]["time"] + 10 * BAR_MS
    assert build_liquidity_overlays(candles, [past_end]) == []


# ── the swept state, which is the point of the layer ─────────────────────────────────────────────


def test_a_swept_level_is_dashed_grey_and_says_which_side_went():
    """The feature in one assertion: a pool price has taken renders as taken.

    MUTATION: emit `_COLOR[group]` / `"solid"` unconditionally and this goes red.
    """
    # A long steady climb sweeps every high behind it.
    candles = _walk(700, drift=0.6)
    ovs = build_liquidity_overlays(candles, [c["time"] for c in candles])
    swept = [o for o in ovs if o["style"]["lineStyle"] == "dashed"]
    assert swept, "a one-way climb must take out the highs behind it"
    for o in swept:
        assert o["style"]["color"] == _SWEPT_COLOR
        assert "swept" in o["label"]
    assert any(o["label"].endswith("BSL") for o in swept), "a swept HIGH is buy-side liquidity"


def test_a_live_level_is_solid_and_carries_no_sweep_tag():
    """The other half, stated on its own — a rule asserted in one direction is the one that gets
    'simplified' back. A level nothing has reached is drawn in its tier's colour with a bare name."""
    candles = _walk(700)  # flat: nothing is ever taken
    ovs = build_liquidity_overlays(candles, [c["time"] for c in candles])
    live = [o for o in ovs if o["style"]["lineStyle"] == "solid"]
    assert live
    for o in live:
        assert o["style"]["color"] != _SWEPT_COLOR
        assert "swept" not in o["label"]


def test_the_derived_sweep_label_agrees_with_the_engines_own():
    """🔴 The honesty check for the one derivation in this module.

    `sweep_label_for` reads the engine's `sweep_label` where it exists (h4 only) and derives from the
    side otherwise. If the two ever disagreed, every non-h4 tier would be labelled by a rule the
    engine contradicts — and nothing would raise, because the engine never states an opinion about
    those tiers. So the derivation is run against the engine's OWN answer on real h4 sweeps.

    MUTATION: swap the high/low arms of `sweep_label_for` and this goes red naming the tier.
    """
    from liquidity import LiquidityEngine

    candles = _walk(700, drift=0.6)
    liq = LiquidityEngine(hide_mitigated_on_new_day=False)
    checked = 0
    for i, c in enumerate(candles):
        ev = liq.update(i, c["time"], c["high"], c["low"], c["close"])
        for lvl in ev.mitigated:
            if lvl.kind != "h4" or not lvl.sweep_label:
                continue
            derived = sweep_label_for(lvl.side, None)  # what we WOULD have derived
            assert derived == lvl.sweep_label, (
                f"derived {derived!r} for a swept {lvl.side} against the engine's {lvl.sweep_label!r}"
            )
            checked += 1
    assert checked, "the feed produced no h4 sweep, so this test proved nothing — fix the feed"


def test_a_reference_level_with_no_side_gets_no_tag():
    """PWC is the previous week's CLOSE — a reference line, never swept, with no side. It must get
    `None` rather than falling into either arm, or a level that cannot be taken would be labelled
    as though it had been."""
    assert sweep_label_for("close", None) is None
    assert sweep_label_for("high", None) == "BSL"
    assert sweep_label_for("low", None) == "SSL"


def test_the_engines_own_label_wins_over_the_derivation():
    """Where the engine states an answer, it is the answer. Deriving over the top of a value
    something else computed is the defect this whole module is written around."""
    assert sweep_label_for("high", "SSL") == "SSL"


# ── geometry ─────────────────────────────────────────────────────────────────────────────────────


def test_a_swept_levels_line_stops_at_the_bar_it_was_taken():
    """The Pine freezes a broken level's line at the break bar. A line that ran on past it would
    read as a level still being watched — which is the opposite of what it is saying.

    MUTATION: use the eviction bar for a swept level too and this goes red.
    """
    candles = _walk(700, drift=0.6)
    times = [c["time"] for c in candles]
    ovs = build_liquidity_overlays(candles, times)
    for o in (x for x in ovs if x["style"]["lineStyle"] == "dashed"):
        assert o["t1"] < times[-1], "a swept level must not run to the last bar"


def test_no_line_runs_backwards_or_leaves_the_candles():
    """A degenerate span is invisible on a chart and is drawn from the plot edge by klinecharts, so
    it fails as a wrong picture rather than as an error."""
    candles = _walk(700, drift=0.4)
    lo, hi = candles[0]["time"], candles[-1]["time"]
    for o in build_liquidity_overlays(candles, [c["time"] for c in candles]):
        assert o["t0"] <= o["t1"]
        assert lo <= o["t0"] <= hi
        assert lo <= o["t1"] <= hi


def test_a_lines_origin_is_the_candle_that_made_the_level_not_the_bar_it_appeared_on():
    """A level is CREATED on the first bar of the period AFTER the one that produced it, so anchoring
    the line there starts it a whole period right of the candle it describes. The Pine scans back for
    the bar that reached the price; so does this.

    MUTATION: return `created_index` from `_origin_bar` unconditionally and this goes red.

    ⚠ **The feed MUST TREND, and a flat one makes this test vacuous — measured, not reasoned.** On
    `_walk(700)` with no drift every bar spans the same high and low, so the creation bar satisfies
    `low <= price <= high` exactly as the true origin does and the assertion cannot tell them apart:
    the mutation above left it GREEN. A drifting feed puts real distance between the bar that made a
    level and the bar the level appears on, which is the whole thing being pinned.
    """
    candles = _walk(700, drift=0.5)
    ovs = build_liquidity_overlays(candles, [c["time"] for c in candles])
    by_time = {c["time"]: c for c in candles}
    checked = 0
    for o in ovs:
        if o["label"].startswith("PWC"):
            continue  # a close need never have been touched as a high or a low
        bar = by_time[o["t0"]]
        assert bar["low"] - 1e-9 <= o["price"] <= bar["high"] + 1e-9, (
            f"{o['label']} at {o['price']} anchored on a bar spanning {bar['low']}–{bar['high']}"
        )
        checked += 1
    assert checked, "no non-PWC level was drawn, so this proved nothing"


# ── contract ─────────────────────────────────────────────────────────────────────────────────────


def test_the_label_is_a_top_level_field_not_a_style_key():
    """🔴 The panel reads `ov.label` and spreads `style` separately, so a label nested inside `style`
    type-checks here, survives the round trip and simply never draws — leaving unlabelled lines on
    the one layer whose job is naming which pool was taken. It fails as a missing feature with
    nothing raising, which is why it is pinned rather than left to review."""
    candles = _walk(700)
    ovs = build_liquidity_overlays(candles, [c["time"] for c in candles])
    assert ovs
    for o in ovs:
        assert isinstance(o.get("label"), str) and o["label"]
        assert "label" not in o["style"]


def test_every_engine_kind_has_a_group():
    """A level kind missing from `_KIND_GROUP` would be a level type that never reaches the chart,
    and an absent layer reads exactly like a market that never printed one. `_group_for` raises, and
    this is the test that catches it before a user does."""
    candles = _walk(700, drift=0.4)
    # Drive the engine directly so the assertion covers every kind it CAN emit, not only the kinds
    # this particular feed happened to anchor.
    from liquidity import LiquidityEngine

    liq = LiquidityEngine(hide_mitigated_on_new_day=False)
    seen = set()
    for i, c in enumerate(candles):
        for lvl in liq.update(i, c["time"], c["high"], c["low"], c["close"]).created:
            seen.add(lvl.kind)
    assert seen, "the feed created no levels at all"
    missing = seen - set(_KIND_GROUP)
    assert not missing, f"engine kinds with no group: {sorted(missing)}"


def test_the_groups_match_the_frontends_analysis_groups():
    """The group string is the ONLY thing routing a layer into the Analysis dropdown and defaulting
    it OFF. A name that differs by a character produces overlays nothing can toggle and nothing can
    see, with no error on either side — so the two sides are compared rather than kept in step by
    memory. Same guard shape as the fair-value-gap and order-block groups."""
    ts = (
        Path(__file__).resolve().parent.parent.parent
        / "frontend"
        / "src"
        / "components"
        / "ChartPanel"
        / "overlays.ts"
    ).read_text()
    for group in GROUPS:
        assert f"'{group}'" in ts, f"{group!r} is not in the frontend's ANALYSIS_GROUPS/colours"


def test_a_swept_level_survives_the_new_day_tidy():
    """🔴 The engine defaults `hide_mitigated_on_new_day=True` — the Pine's `i_currentDayOnly` tidy —
    and that tidy is GATED on `not showMitLiq`, which went TRUE in mpc_jarvis.pine on 2026-08-07.
    So today's indicator never runs it, and left at the default every swept level older than the
    current NY day would be evicted before it could be drawn.

    The layer would still work. It would draw live levels, and almost nothing swept — i.e. it would
    look correct while missing the one thing it exists to show.

    MUTATION: drop the keyword from the `LiquidityEngine(...)` call and this goes red.

    ⚠ **The anchor set has to be SPARSE, and that is the trap this test fell into first.** Anchored
    on EVERY bar the two settings agree exactly (measured: 72 swept either way), because a level is
    marked seen on the bar it is swept — before any later new-day tidy can evict it. The tidy only
    bites on a level that was taken on one day and is still being asked about on a later one, which
    is what a real anchor set looks like: 944 anchors over 155,891 bars on the measured run. So an
    every-bar feed would have produced a test that passed against the defect. Measured here with a
    single realistic anchor: **6 swept levels kept against 1 tidied.**
    """
    candles = _walk(700, drift=0.6)
    late = [candles[-1]["time"]]
    kept = build_liquidity_overlays(candles, late)
    tidied = build_liquidity_overlays(candles, late, hide_mitigated_on_new_day=True)
    swept_kept = sum(1 for o in kept if o["style"]["lineStyle"] == "dashed")
    swept_tidied = sum(1 for o in tidied if o["style"]["lineStyle"] == "dashed")
    assert swept_kept > swept_tidied, (
        "production must keep swept levels the new-day tidy would drop "
        f"(kept {swept_kept}, tidied {swept_tidied})"
    )


def test_the_tiers_are_separable():
    """Three groups rather than one, because H4 rolls six times a day and is 58% of the levels on the
    measured run — a reader following daily and session sweeps needs it off, and a reader timing an
    entry needs only it."""
    candles = _walk(900, drift=0.3)
    groups = _by_group(build_liquidity_overlays(candles, [c["time"] for c in candles]))
    assert groups[GROUP_LIQ_H4], "no H4 levels on a multi-day feed"
    assert groups[GROUP_LIQ_HTF], "no daily/weekly levels on a multi-day feed"
    assert groups[GROUP_LIQ_SESSION], "no session levels on a multi-day feed"


def test_a_broken_feed_degrades_to_no_layer_rather_than_breaking_the_chart():
    """Best-effort, like every other overlay module here: the price chart is worth more than any one
    of its layers, so a malformed candle costs the layer and not the page."""
    assert build_liquidity_overlays([], [1, 2, 3]) == []
    assert build_liquidity_overlays([{"time": 0, "high": 1, "low": 0, "close": 0.5}], [0]) == []
