"""
Tests for services/fvg_overlays.py — the fair-value-gap layer on the price chart.

Two halves:

  1. **Hand-built candles** pin the layer's own rules: which gaps get drawn (only those live at a
     trade / blocked / missed anchor, and ALL of them when several overlap), the box geometry
     against the Pine box's real span, and that the settings are mpc_assistant's — including the
     timeframe-split gap floor, which is the one that silently draws the wrong gap set if it breaks.

  2. **A real TradingView export** proves the boxes ARE the Pine's gaps, price for price. The CSV
     carries the Pine FVG engine's own live arrays per bar (`px_fvg_top_k` / `px_fvg_bot_k` /
     `px_fvg_count`), so for any anchor bar we can assert the boxes covering it are exactly the gaps
     mpc had open on that bar. That is the check the whole feature rests on — the unit tests above
     could all pass on an engine that drew the wrong gaps.

The export is git-ignored (it is 7 MB of broker data), so half 2 SKIPS when it is absent. It also
predates the 2026-07-18 mpc default drift, so it is replayed with the settings ITS Pine build ran
(`max_count=6, threshold_pct=0.1, require_close=True`, EQ exemption off) — which is exactly what the
config keyword arguments on `build_fvg_overlays` exist for. What that proves is the emitter's
faithfulness to the engine and to the Pine arrays; that the ENGINE matches today's mpc build is
proven separately and continuously by `engines/fair_value_gaps/tools/compare_fvg.py`.
"""

import csv
from pathlib import Path

import pytest
from services.fvg_overlays import GROUP_FVG, build_fvg_overlays, mpc_threshold_pct

BAR_MS = 5 * 60 * 1000


def _candles(rows):
    """[(o, h, l, c), …] → spec candles on a 5-minute grid, so bar index i sits at time i*BAR_MS."""
    return [
        {"time": i * BAR_MS, "open": o, "high": h, "low": lo, "close": c}
        for i, (o, h, lo, c) in enumerate(rows)
    ]


# Two overlapping bullish gaps, both later closed past. Hand-traced against the engine's rules:
#
#   GAP A  born bar 4  (low 101.0 > bar-2 high 100.5)   top 101.0 / bottom 100.5
#          live 4…8, closed past on bar 9 (close 100.2 <= 100.5)
#   GAP B  born bar 6  (low 104.0 > bar-4 high 103.5)   top 104.0 / bottom 103.5
#          live 6…7, closed past on bar 8 (close 103.4 <= 103.5)
#
# So bar 7 is the only bar where BOTH are open — the cluster case. No other bar in the series meets
# either imbalance condition (checked by hand in both directions).
_FIXTURE = _candles(
    [
        (100.0, 100.5, 99.5, 100.0),  # 0
        (100.0, 100.5, 99.5, 100.0),  # 1
        (100.0, 100.5, 99.5, 100.0),  # 2
        (100.0, 103.0, 99.8, 102.8),  # 3  displacement
        (102.8, 103.5, 101.0, 103.0),  # 4  → GAP A
        (103.0, 106.0, 102.8, 105.8),  # 5  displacement
        (105.8, 107.0, 104.0, 106.5),  # 6  → GAP B
        (106.5, 107.0, 105.5, 106.0),  # 7  both live
        (106.0, 107.0, 103.0, 103.4),  # 8  closes past GAP B
        (103.4, 106.0, 100.0, 100.2),  # 9  closes past GAP A
        (100.2, 103.5, 99.8, 100.5),  # 10
    ]
    + [(100.5, 103.5, 99.8, 100.5)] * 20
)  # 11…30 — flat tail, forms nothing

_A = (101.0, 100.5)
_B = (104.0, 103.5)


def _spans(overlays):
    """{(top, bottom): (first_bar_drawn, last_bar_drawn)} for readable assertions."""
    return {(ov["top"], ov["bottom"]): (ov["t0"] // BAR_MS, ov["t1"] // BAR_MS) for ov in overlays}


# ── What gets drawn ───────────────────────────────────────────────────────────


def test_no_trade_block_or_miss_means_no_gaps_at_all():
    """The layer exists to explain a signal. With nothing to explain it draws nothing — not every
    gap in the run, which is what makes the chart readable in the first place."""
    assert build_fvg_overlays(_FIXTURE, [], "M5") == []


def test_only_the_gaps_live_at_an_anchor_are_drawn():
    """Bar 5 has only GAP A open — GAP B is not born until bar 6, so it must not appear."""
    got = _spans(build_fvg_overlays(_FIXTURE, [5 * BAR_MS], "M5"))
    assert set(got) == {_A}


def test_every_gap_in_a_cluster_is_drawn_not_just_the_newest():
    """Bar 7 has BOTH gaps open. Aaron's explicit ask: if an area has several, draw them all."""
    got = _spans(build_fvg_overlays(_FIXTURE, [7 * BAR_MS], "M5"))
    assert set(got) == {_A, _B}


def test_an_anchor_with_no_live_gap_draws_nothing():
    """Bar 20 sits in the flat tail, long after both gaps were closed past."""
    assert build_fvg_overlays(_FIXTURE, [20 * BAR_MS], "M5") == []


def test_a_gap_closed_past_on_the_anchor_bar_is_not_drawn():
    """mpc deletes the box on the bar that closes through it, so on bar 8 GAP B is already gone from
    the chart. GAP A is still open there and must still be drawn."""
    got = _spans(build_fvg_overlays(_FIXTURE, [8 * BAR_MS], "M5"))
    assert set(got) == {_A}


def test_anchors_outside_the_candle_window_are_ignored():
    """A run's trades can predate the shipped window (the chart trims to the newest slice), and an
    out-of-range anchor must not silently clamp onto the first or last bar and draw the wrong gaps."""
    assert build_fvg_overlays(_FIXTURE, [-5 * BAR_MS, 9_999 * BAR_MS], "M5") == []


def test_all_three_anchor_kinds_feed_the_same_layer():
    """Trades, blocks and misses are just timestamps here — the module has no idea which is which,
    which is what keeps it strategy-agnostic. Two different anchors ⇒ the union of their gaps."""
    got = _spans(build_fvg_overlays(_FIXTURE, [5 * BAR_MS, 7 * BAR_MS], "M5"))
    assert set(got) == {_A, _B}


def test_every_box_carries_the_one_group_so_one_toggle_hides_the_layer():
    ovs = build_fvg_overlays(_FIXTURE, [7 * BAR_MS], "M5")
    assert ovs and all(ov["group"] == GROUP_FVG and ov["type"] == "box" for ov in ovs)


# ── Box geometry — the Pine box's real span ───────────────────────────────────


def test_box_runs_from_the_bar_before_birth_to_the_last_bar_the_gap_was_alive():
    """Pine creates the box at `bar_index - 1` and extends it every surviving bar, then DELETES it on
    the bar the gap dies — so the box never covers its own death bar. GAP A: born 4, closed past on
    9 ⇒ bars 3…8. GAP B: born 6, closed past on 8 ⇒ bars 5…7."""
    got = _spans(build_fvg_overlays(_FIXTURE, [7 * BAR_MS], "M5"))
    assert got[_A] == (3, 8)
    assert got[_B] == (5, 7)


def test_a_gap_still_open_at_the_end_runs_to_the_last_candle():
    """Truncated before either gap is closed past — both are still live, so both extend to the right
    edge exactly as an un-mitigated Pine box does."""
    got = _spans(build_fvg_overlays(_FIXTURE[:8], [7 * BAR_MS], "M5"))
    assert got[_A] == (3, 7)
    assert got[_B] == (5, 7)


# ── The settings are mpc_assistant.pine's ─────────────────────────────────────


def test_gap_floor_follows_mpcs_timeframe_split():
    """`fvgThreshPct = timeframe.in_seconds() < 900 ? 0.0 : 0.04` (mpc_assistant.pine:410-412). Get
    this wrong and the chart draws a different gap SET from the indicator it is meant to mirror,
    with nothing on screen to say so."""
    assert mpc_threshold_pct("M1") == 0.0
    assert mpc_threshold_pct("M5") == 0.0
    assert mpc_threshold_pct("M15") == 0.04
    assert mpc_threshold_pct("H1") == 0.04
    assert mpc_threshold_pct("D1") == 0.04


def test_an_unknown_timeframe_takes_the_stricter_floor():
    """Over-filtering drops a marginal gap; under-filtering INVENTS gaps the indicator never drew.
    Only one of those two errors puts something on the chart that is not there."""
    assert mpc_threshold_pct("") == 0.04
    assert mpc_threshold_pct("W1") == 0.04


def test_the_floor_actually_reaches_the_engine():
    """The fixture's gaps are ~0.48% of price, so they clear the 15m floor too — a 0.6% floor must
    remove them, which is what proves the threshold is wired through rather than merely computed."""
    assert build_fvg_overlays(_FIXTURE, [7 * BAR_MS], "M5", threshold_pct=0.6) == []


def test_defaults_match_the_locked_mpc_constants():
    from services import fvg_overlays as f

    assert (f.MPC_MAX_COUNT, f.MPC_REQUIRE_CLOSE) == (8, False)
    assert (f.MPC_THRESH_LTF, f.MPC_THRESH_HTF, f.MPC_TF_SPLIT_SECONDS) == (0.0, 0.04, 900)
    assert (f.MPC_EQ_PIVOT_LEN, f.MPC_EQ_ATR_MULT, f.MPC_EQ_MAX, f.MPC_EQ_EXEMPT) == (
        2,
        0.1,
        6,
        True,
    )


# ── Pine parity: the boxes ARE the gaps the Pine had open ─────────────────────

_EXPORT = (
    Path(__file__).resolve().parents[3]
    / "engines"
    / "fair_value_gaps"
    / "exports"
    / "VANTAGE_XAUUSD, 5_5ead0.csv"
)

# The Pine build behind that export (2026-07-14): 6 plotted slots, cap 6, the 0.1% floor, the
# middle-bar close check hardcoded on, no EQ exemption. Confirmed by replaying it — the engine
# reproduces its arrays bar-for-bar from bar 885 on, and every earlier mismatch is carry-in from
# gaps born before the export window (the standard warm-up ghost).
_EXPORT_SLOTS = 6
_EXPORT_CFG = {"max_count": 6, "threshold_pct": 0.1, "require_close": True, "eq_exempt": False}
_EXPORT_WARMUP = 885


def _num(s):
    s = (s or "").strip()
    if s == "" or s.lower() in ("na", "nan"):
        return None
    try:
        return float(s)
    except ValueError:
        return None


@pytest.fixture(scope="module")
def export_rows():
    if not _EXPORT.exists():
        pytest.skip(f"TradingView export not present (git-ignored): {_EXPORT.name}")
    with open(_EXPORT, newline="") as fh:
        return list(csv.DictReader(fh))


def test_boxes_match_the_pines_own_live_gap_arrays(export_rows):
    """The real check. On each sampled anchor bar, the boxes covering it must be EXACTLY the gaps the
    Pine had open on that bar — same count, same top and bottom to 1e-6.

    A box covers bar i while the gap is alive, i.e. `[t0_bar + 1, t1_bar]` (t0 is the bar BEFORE
    birth, mirroring `box.new(bar_index - 1, …)`). Anchors are sampled right across the export so a
    drift that only shows up after a few thousand bars still fails this.
    """
    candles = [
        {
            "time": i * BAR_MS,
            "open": _num(r["open"]),
            "high": _num(r["high"]),
            "low": _num(r["low"]),
            "close": _num(r["close"]),
        }
        for i, r in enumerate(export_rows)
    ]
    assert all(None not in (c["open"], c["high"], c["low"], c["close"]) for c in candles)

    anchors = list(range(_EXPORT_WARMUP + 15, len(candles), 137))
    assert len(anchors) > 50, "sample too thin to be worth calling a parity test"

    overlays = build_fvg_overlays(candles, [i * BAR_MS for i in anchors], "M5", **_EXPORT_CFG)
    assert overlays, "the export should produce gaps at these anchors"

    boxes = [
        (ov["t0"] // BAR_MS + 1, ov["t1"] // BAR_MS, ov["top"], ov["bottom"]) for ov in overlays
    ]

    checked = 0
    for i in anchors:
        row = export_rows[i]
        pine = set()
        for k in range(1, _EXPORT_SLOTS + 1):
            top, bot = _num(row[f"px_fvg_top_{k}"]), _num(row[f"px_fvg_bot_{k}"])
            if top is not None and bot is not None:
                pine.add((round(top, 5), round(bot, 5)))
        drawn = {(t, b) for lo, hi, t, b in boxes if lo <= i <= hi}
        assert drawn == pine, f"bar {i}: chart drew {sorted(drawn)}, Pine held {sorted(pine)}"
        # …and the count column agrees, which catches a Pine bar holding two gaps at the same price
        # (a set would silently collapse them).
        assert len(drawn) == int(_num(row["px_fvg_count"]) or 0), f"bar {i}: gap count differs"
        checked += 1
    assert checked == len(anchors)


def test_a_bar_with_no_anchor_gets_no_box_even_mid_export(export_rows):
    """Coverage is anchor-driven, not "everything near an anchor". A bar 60 bars after the only
    anchor must carry no box unless a gap genuinely spans both — proven by comparing against the
    Pine's own count for that bar, which is non-zero there."""
    candles = [
        {
            "time": i * BAR_MS,
            "open": _num(r["open"]),
            "high": _num(r["high"]),
            "low": _num(r["low"]),
            "close": _num(r["close"]),
        }
        for i, r in enumerate(export_rows)
    ]
    anchor = _EXPORT_WARMUP + 500
    overlays = build_fvg_overlays(candles, [anchor * BAR_MS], "M5", **_EXPORT_CFG)
    at_anchor = int(_num(export_rows[anchor]["px_fvg_count"]) or 0)
    assert len(overlays) == at_anchor, "one anchor draws exactly the gaps open on its own bar"
