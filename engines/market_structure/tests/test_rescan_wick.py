"""The post-break rescan must not resurrect a wick the break rule already refused.

THE DEFECT, and it is one root cause behind three separate on-chart symptoms Aaron
reported on 2026-08-21 (a doubled `LL`, an `ASH` printed beside an `HH`, and a later
bogus `HH`):

    Structure BREAKS on a CLOSE through the level — wicks deliberately do not count.
    The rescan that installs the NEXT active swing after a break reads the raw WICK
    (`high[i]` / `low[i]`) over a window bounded by the OPPOSITE side's last confirmed
    bar. That window reaches back BEFORE the swing the break just confirmed, so it can
    find a bar whose wick pierced the level, closed back inside, and was correctly
    refused — and install THAT as the new active swing.

The result is an active swing that is EARLIER than, and MORE EXTREME than, the swing
just confirmed. On the chart that is a second label crowding the first. When the bogus
swing is later broken it is promoted to its own permanent HH/LL, which is the "wrong new
HH" that follows.

⚠ NOT the same defect as the 2026-08-20 tie guard, which fires only on an EXACT price
tie. Here the resurrected wick is STRICTLY more extreme, so that guard cannot see it.
Exact-price adjacent duplicates measured 0 across 600,000 bars — that fix works and is
untouched.

⚠ NOT cosmetic. `mpc_jarvis.pine` does `fibo_ash := st.ash`, so a bogus active swing
moves the External Fib's anchor and with it E1-E4, the TP ladder, the Sniper Zone and the
B-LEG band. One measured case was $8.10 out.

THE FIXTURE IS REAL BARS, NOT SYNTHETIC. 100 XAUUSD M15 bars (cache rows 5225-5324,
2018-2019 era) — the smallest slice that still reproduces; 95 bars does not. Real bars
because the interaction needs a genuine rejected wick sitting inside a genuine rescan
window, and a hand-built series that happens to miss that is a test describing a system
we do not have.

Watched RED before the fix: `HH` confirmed at bar 83 (1241.51) while the new active swing
high was installed at bar 82 (1241.90) — one bar EARLIER and 39c HIGHER.

Run:  python3 -m pytest engines/market_structure/tests/test_rescan_wick.py -q
"""

from __future__ import annotations

import sys
from pathlib import Path

_ENGINES = Path(__file__).resolve().parent.parent.parent
if str(_ENGINES) not in sys.path:
    sys.path.insert(0, str(_ENGINES))

from market_structure import Bar, StructureEngine  # noqa: E402

# (open, high, low, close) — XAUUSD M15, cache rows 5225-5324.
BARS = [
    (1234.61, 1234.77, 1233.25, 1234.09),
    (1234.09, 1234.29, 1233.1, 1233.89),
    (1233.89, 1234.4, 1233.71, 1234.01),
    (1234.01, 1234.22, 1233.49, 1233.65),
    (1233.64, 1233.84, 1232.81, 1232.85),
    (1232.9, 1233.08, 1232.34, 1232.95),
    (1232.93, 1233.07, 1232.14, 1232.57),
    (1232.57, 1234.48, 1231.97, 1233.85),
    (1233.85, 1234.02, 1232.09, 1232.13),
    (1232.16, 1232.72, 1232.06, 1232.14),
    (1232.15, 1232.16, 1230.78, 1231.0),
    (1230.99, 1231.54, 1230.68, 1231.36),
    (1231.36, 1231.92, 1231.23, 1231.75),
    (1231.74, 1231.84, 1230.9, 1231.03),
    (1231.03, 1231.32, 1230.74, 1231.31),
    (1231.32, 1231.38, 1230.67, 1231.19),
    (1231.19, 1231.32, 1230.48, 1230.51),
    (1230.51, 1230.88, 1229.97, 1230.76),
    (1230.77, 1231.07, 1230.66, 1230.85),
    (1230.85, 1230.93, 1230.74, 1230.85),
    (1230.86, 1231.14, 1230.68, 1231.05),
    (1231.04, 1231.05, 1230.62, 1230.64),
    (1230.26, 1231.25, 1230.2, 1231.01),
    (1231.01, 1231.62, 1230.81, 1231.26),
    (1231.26, 1231.57, 1231.02, 1231.17),
    (1231.17, 1231.58, 1231.08, 1231.17),
    (1231.16, 1231.33, 1230.45, 1230.69),
    (1230.72, 1231.5, 1230.67, 1231.33),
    (1231.33, 1231.41, 1230.86, 1231.36),
    (1231.37, 1231.73, 1231.22, 1231.36),
    (1231.35, 1232.85, 1231.24, 1232.62),
    (1232.62, 1232.93, 1232.51, 1232.71),
    (1232.71, 1234.37, 1232.61, 1234.17),
    (1234.17, 1235.26, 1233.66, 1234.95),
    (1234.95, 1235.37, 1234.46, 1234.98),
    (1234.98, 1235.06, 1234.27, 1234.79),
    (1234.77, 1235.57, 1234.64, 1234.85),
    (1234.85, 1235.31, 1234.84, 1235.18),
    (1235.17, 1235.38, 1234.55, 1235.26),
    (1235.26, 1235.66, 1235.22, 1235.43),
    (1235.43, 1235.94, 1235.43, 1235.85),
    (1235.85, 1235.91, 1235.3, 1235.49),
    (1235.5, 1235.91, 1235.27, 1235.9),
    (1235.9, 1236.88, 1235.8, 1236.52),
    (1236.52, 1236.94, 1236.14, 1236.63),
    (1236.63, 1236.96, 1236.46, 1236.96),
    (1236.94, 1237.08, 1236.53, 1236.79),
    (1236.78, 1236.86, 1236.28, 1236.32),
    (1236.35, 1237.25, 1236.35, 1237.22),
    (1237.22, 1237.72, 1237.21, 1237.29),
    (1237.29, 1237.82, 1236.93, 1237.79),
    (1237.79, 1238.33, 1237.64, 1237.65),
    (1237.65, 1237.8, 1237.23, 1237.63),
    (1237.63, 1238.08, 1236.78, 1237.25),
    (1237.25, 1238.11, 1236.9, 1237.72),
    (1237.73, 1238.34, 1237.21, 1237.5),
    (1237.51, 1237.63, 1236.62, 1237.05),
    (1237.03, 1237.51, 1236.55, 1236.64),
    (1236.63, 1238.22, 1236.09, 1237.74),
    (1237.77, 1238.82, 1237.69, 1237.97),
    (1238.0, 1239.08, 1237.97, 1238.91),
    (1238.89, 1239.2, 1238.51, 1238.59),
    (1238.58, 1239.68, 1238.49, 1238.73),
    (1238.72, 1239.05, 1238.08, 1238.6),
    (1238.7, 1240.61, 1238.52, 1240.23),
    (1240.23, 1241.12, 1240.12, 1240.54),
    (1240.54, 1240.85, 1239.35, 1239.63),
    (1239.63, 1240.18, 1239.54, 1239.64),
    (1239.63, 1239.65, 1238.68, 1239.25),
    (1239.25, 1239.64, 1238.81, 1239.37),
    (1239.35, 1240.18, 1239.0, 1239.84),
    (1239.85, 1240.17, 1238.69, 1238.79),
    (1238.8, 1239.44, 1238.59, 1239.03),
    (1239.05, 1239.32, 1238.87, 1239.09),
    (1239.09, 1239.23, 1238.57, 1238.6),
    (1238.59, 1239.44, 1238.43, 1238.93),
    (1238.91, 1239.34, 1238.57, 1239.12),
    (1239.11, 1239.82, 1238.9, 1239.39),
    (1239.42, 1239.71, 1238.79, 1239.2),
    (1239.2, 1241.35, 1238.99, 1240.0),
    (1239.99, 1240.18, 1237.65, 1237.91),
    (1237.92, 1239.31, 1237.87, 1239.31),
    (1239.31, 1241.9, 1239.08, 1241.05),
    (1241.05, 1241.51, 1240.5, 1241.35),
    (1241.35, 1241.42, 1240.03, 1240.34),
    (1240.32, 1241.32, 1239.55, 1240.76),
    (1240.74, 1240.95, 1240.1, 1240.44),
    (1240.43, 1240.87, 1238.36, 1238.86),
    (1238.84, 1239.25, 1238.19, 1239.23),
    (1239.2, 1239.22, 1237.95, 1238.27),
    (1238.28, 1238.68, 1237.49, 1238.34),
    (1238.34, 1239.12, 1238.2, 1238.85),
    (1238.85, 1239.39, 1238.21, 1238.22),
    (1238.21, 1238.85, 1237.97, 1238.44),
    (1238.43, 1238.49, 1236.67, 1237.62),
    (1237.61, 1237.91, 1236.99, 1237.78),
    (1237.78, 1238.75, 1237.21, 1238.71),
    (1238.7, 1240.06, 1238.69, 1239.99),
    (1240.0, 1240.73, 1239.08, 1240.27),
    (1240.26, 1241.14, 1239.86, 1241.14),
]


def _replay(major_length: int = 15):
    """Drive the engine and collect every break that confirmed a swing, paired with the
    active swing the SAME break then installed."""
    eng = StructureEngine(major_length=major_length)
    pairs = []
    for i, (o, h, low, c) in enumerate(BARS):
        ev = eng.update(Bar(index=i, open=o, high=h, low=low, close=c))
        e = ev.external
        if e.bear_bos and e.broken_high_label in ("HH", "LH"):
            a = eng.active_swing_high
            pairs.append(
                (
                    "high",
                    e.broken_high_label,
                    e.broken_high_index,
                    e.broken_high_price,
                    a.index if a else None,
                    a.price if a else None,
                )
            )
        if e.bull_bos and e.broken_low_label in ("HL", "LL"):
            a = eng.active_swing_low
            pairs.append(
                (
                    "low",
                    e.broken_low_label,
                    e.broken_low_index,
                    e.broken_low_price,
                    a.index if a else None,
                    a.price if a else None,
                )
            )
    return pairs


def test_the_fixture_actually_exercises_the_path():
    """Guard against a vacuous pass. If the slice stops producing breaks — a refactor, a
    changed default — every assertion below would pass by finding nothing to check."""
    pairs = _replay()
    assert len(pairs) >= 2, (
        f"fixture produced only {len(pairs)} confirmed swings; it is not exercising the rescan"
    )


def test_a_break_never_installs_a_swing_earlier_and_more_extreme_than_the_one_it_confirmed():
    """THE regression. A rescan may only install a swing that is genuinely NEWER than the
    one just confirmed. Anything at-or-before it that ties or exceeds it is either the same
    swing or a wick the close-based break rule already refused."""
    for side, label, conf_loc, conf_px, act_loc, act_px in _replay():
        if act_loc is None or conf_loc is None:
            continue
        if act_loc >= conf_loc:
            continue
        more_extreme = act_px > conf_px if side == "high" else act_px < conf_px
        assert not more_extreme, (
            f"{side}: confirmed {label} @bar{conf_loc} {conf_px} but installed the new active "
            f"swing @bar{act_loc} {act_px} — {conf_loc - act_loc} bars EARLIER and more extreme. "
            "That is a wick the break rule refused, resurrected by the rescan."
        )


def test_the_specific_reported_case():
    """The exact pair off Aaron's chart, pinned by value so a future change that reopens it
    fails with the real numbers rather than a generic message."""
    for side, _label, conf_loc, conf_px, act_loc, act_px in _replay():
        if side == "high" and conf_loc == 83:
            assert conf_px == 1241.51
            # bar 82 wicked to 1241.90 and CLOSED at 1241.05, below the then-active
            # swing high of 1241.12 — correctly not a break, and so never a swing.
            assert not (act_loc == 82 and act_px == 1241.90), (
                "bar 82's refused wick was installed as the active swing high"
            )
            return
    raise AssertionError("the reported case is no longer in the fixture — re-derive it")
