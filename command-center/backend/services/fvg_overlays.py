"""
fvg_overlays.py — draw the fair value gaps that were LIVE at a trade, a block or a miss.

Runs the CANONICAL fair-value-gap engine (`engines/fair_value_gaps/`) over the candles the chart is
about to show and turns its gap lifecycle into `ChartSpec.overlays` boxes — the same generic
vocabulary every other overlay uses, so the frontend draws them with zero FVG-specific logic and one
toggle switches the layer off.

This is NOT a second FVG engine. It imports the one in `engines/fair_value_gaps/` by bare name (the
same `sys.path` shim as regime/news/structure) and only reads its public events.

WHAT IS DRAWN, AND WHY IT IS NOT EVERY GAP
------------------------------------------
A 6.5-year run leaves thousands of gaps and a chart carrying all of them is unreadable — and it
would answer a question nobody asked. The question this layer exists for is "when this trade was
taken / refused / missed, where were the gaps?", so a gap is drawn **only if it was in the engine's
live list on the bar of a trade ENTRY, a blocked setup, or a missed setup**. Everything else is
dropped. When several gaps were live at one of those bars, ALL of them are drawn — a cluster is
exactly the thing you want to see.

The anchors come straight off the spec (`trades[].entryTime`, `blocks[].time`, `misses[].time`), so
this module knows nothing about what a trade or a block IS. Give it different anchors and it draws
gaps at those instead.

THE GAPS ARE mpc_assistant.pine's, NOT THE STRATEGY'S
----------------------------------------------------
The settings below mirror `indicators/engines/mpc_assistant.pine` — the indicator the charts are read
against — locked constants, not panel inputs (`mpc_assistant.pine:407-414`, `:420-423`):

    fvgMaxCount      = 8
    fvgRequireClose  = false
    fvgThreshPct     = timeframe.in_seconds() < 900 ? 0.0 : 0.04     ← timeframe-SPLIT
    eqExemptFvg      = true   (eqPivotLen 2, eqAtrMult 0.1, eqMax 6)

⚠ **`mpc_strategy.pine` — and therefore the Python bots — run a DIFFERENT set.**
`strategies/python/mpc_sos_fade/strategy.py` pins `fvg_max_count=7, fvg_require_close=True,
fvg_threshold_pct=0.1`, because the strategy file hardcodes the middle-bar close check and carries
its own count. So a gap drawn here is a gap **the indicator shows**, which is not always a gap the
bot's entry rule counted (the bot sees strictly fewer: `require_close` only ever removes gaps, and
its floor is higher). That fork is real and predates this layer — see
`engines/fair_value_gaps/CLAUDE.md` → the `require_close` callout. Do not "fix" it by pointing this
module at the strategy's config: the request was to match what the chart in TradingView draws.

BOX GEOMETRY MIRRORS THE PINE BOX
---------------------------------
Pine creates the box at `bar_index - 1` on the birth bar and calls `box.set_right(bar_index)` every
bar the gap survives, then DELETES it the bar the gap is mitigated or evicted. So a gap's box spanned
`[born - 1, last bar it was still alive]` and then vanished. That is what is emitted: `t1` is the bar
BEFORE its death, never the death bar itself — on the death bar mpc showed nothing there.
"""

from __future__ import annotations

import bisect
import logging
import sys
from pathlib import Path
from typing import Iterable, Optional

log = logging.getLogger("FVG_OVERLAYS")

# engines/ on sys.path so the canonical engines import by bare name (same pattern as regime/news).
_ENGINES = Path(__file__).resolve().parent.parent.parent.parent / "engines"
if str(_ENGINES) not in sys.path:
    sys.path.insert(0, str(_ENGINES))

# Group name — MUST match ANALYSIS_GROUPS in the frontend overlays.ts (that is what routes the
# toggle into the Analysis dropdown and defaults it OFF).
GROUP_FVG = "Fair Value Gaps"

# ── mpc_assistant.pine's locked FVG + EQ constants (mpc_assistant.pine:407-414, :420-423) ──
MPC_MAX_COUNT = 8            # fvgMaxCount
MPC_REQUIRE_CLOSE = False    # fvgRequireClose
MPC_THRESH_LTF = 0.0         # fvgThreshLTF — below 15m
MPC_THRESH_HTF = 0.04        # fvgThreshHTF — 15m and above
MPC_TF_SPLIT_SECONDS = 900   # timeframe.in_seconds() < 900
MPC_EQ_PIVOT_LEN = 2         # eqPivotLen
MPC_EQ_ATR_MULT = 0.1        # eqAtrMult
MPC_EQ_MAX = 6               # eqMax
MPC_EQ_EXEMPT = True         # eqExemptFvg — a gap behind an EQH/EQL survives the FIFO cap

# Colours. mpc paints BOTH directions the SAME grey (`color.new(color.gray, 80)`) and explicitly no
# border (`border_color = color(na)`), so that is what is emitted: one flat tint, `lineWidth: 0` (the
# panel's "no border" signal — see the BOX template in overlays.ts). Bull and bear are therefore
# indistinguishable, which is exactly how the indicator's boxes look; mpc's only direction cue is a
# green/red "FVG" caption, and drawing a border here instead would be a shape the chart doesn't have.
_FILL = "rgba(148,163,184,0.16)"     # slate, ~80% transparent — the Pine's grey body

# Payload backstop. Keeps the most RECENT gaps; a truncation is LOGGED, never silent.
#
# Raised from 1500 on 2026-08-06 with `_capped_start`'s retirement: the spec now carries the whole
# run, and the full history of a 6.5-year M15 run holds **2,822** anchored gaps — so the old value
# dropped the oldest ~47% of them, which is the half a reader scrolls back to. The render-cost
# reason for a low cap is gone (the panel creates overlays for the viewport, not for the loaded
# history); this is now purely a bound on the payload. See `structure_overlays._MAX_PER_GROUP`.
_MAX_BOXES = 20_000

_TF_MINUTES = {"M1": 1, "M5": 5, "M15": 15, "M30": 30, "H1": 60, "H4": 240, "D1": 1440}


def mpc_threshold_pct(timeframe: str) -> float:
    """The minimum-gap floor mpc_assistant would run on this timeframe.

    `fvgThreshPct = timeframe.in_seconds() < 900 ? fvgThreshLTF : fvgThreshHTF` — 0.0 below 15m,
    0.04 at 15m and above. An unrecognised timeframe falls to the HTF branch: over-filtering drops a
    marginal gap, under-filtering INVENTS gaps the indicator never drew, and only one of those two
    errors puts something on the chart that isn't there.
    """
    minutes = _TF_MINUTES.get((timeframe or "").upper())
    if minutes is None:
        log.warning("fvg overlays: unknown timeframe %r — using the 15m+ gap floor", timeframe)
        return MPC_THRESH_HTF
    return MPC_THRESH_LTF if minutes * 60 < MPC_TF_SPLIT_SECONDS else MPC_THRESH_HTF


def _anchor_bars(times: list[int], anchors_ms: Iterable[int]) -> set[int]:
    """Anchor timestamps → the bar index each one falls on, clipped to the loaded candles.

    An anchor between two bars belongs to the bar it is INSIDE (the last bar at or before it), which
    is the bar whose close the engine had just processed when that trade/block/miss happened.
    """
    out: set[int] = set()
    if not times:
        return out
    lo, hi = times[0], times[-1]
    for t in anchors_ms:
        if not isinstance(t, (int, float)) or not (lo <= t <= hi):
            continue
        i = bisect.bisect_right(times, int(t)) - 1
        if i >= 0:
            out.add(i)
    return out


def build_fvg_overlays(
    candles: list[dict],
    anchors_ms: Iterable[int],
    timeframe: str,
    *,
    max_count: int = MPC_MAX_COUNT,
    threshold_pct: Optional[float] = None,
    require_close: bool = MPC_REQUIRE_CLOSE,
    eq_exempt: bool = MPC_EQ_EXEMPT,
) -> list[dict]:
    """Replay `candles` through the canonical FVG engine and emit a box per gap that was LIVE at one
    of the `anchors_ms` bars.

    `candles` are the spec's candles (time/open/high/low/close, sorted by time). `anchors_ms` are the
    trade-entry / blocked / missed timestamps. `timeframe` picks mpc's timeframe-split gap floor.

    The keyword arguments exist so a parity test can replay an export whose Pine build ran different
    settings; production callers pass none of them and get mpc_assistant's. Returns a list of
    ChartOverlay `box` dicts, all in one group. Best-effort: any failure returns [] so the rest of
    the chart still renders.
    """
    if len(candles) < 3:
        return []
    bars = _anchor_bars([c["time"] for c in candles], anchors_ms)
    if not bars:
        return []      # no trade, block or miss on screen ⇒ nothing to explain ⇒ nothing to draw

    try:
        from fair_value_gaps import FairValueGapEngine
        eq_engine = None
        if eq_exempt:
            from equal_highs_lows import EqualHighsLowsEngine
            eq_engine = EqualHighsLowsEngine(
                pivot_len=MPC_EQ_PIVOT_LEN, atr_mult=MPC_EQ_ATR_MULT, max_levels=MPC_EQ_MAX,
            )
    except Exception as exc:  # noqa: BLE001 — engine import is best-effort
        log.warning("fvg overlays: engine import failed: %s", exc)
        return []

    thresh = mpc_threshold_pct(timeframe) if threshold_pct is None else threshold_pct
    times = [c["time"] for c in candles]
    n = len(candles)

    # gap id → its whole life. `died` is the bar it was mitigated or evicted on (None = still live at
    # the last candle); `seen` marks it as live on at least one anchor bar, which is what gets drawn.
    lives: dict[int, dict] = {}

    try:
        fvg = FairValueGapEngine(max_count=max_count, threshold_pct=thresh, require_close=require_close)
        for i, c in enumerate(candles):
            o, h, l, cl = c["open"], c["high"], c["low"], c["close"]
            # EQ runs BEFORE FVG (the mpc order) and its levels feed the cap: a gap behind an
            # EQH/EQL is exempt from FIFO eviction and lives until mitigated.
            eq_levels, eq_tol = None, 0.0
            if eq_engine is not None:
                eq_ev = eq_engine.update(i, h, l, cl)
                eq_levels = eq_ev.active_eqh + eq_ev.active_eql
                eq_tol = eq_ev.tolerance
            ev = fvg.update(i, o, h, l, cl, eq_levels=eq_levels, eq_tol=eq_tol)

            for g in ev.formed:
                # Direction is deliberately NOT kept: mpc draws bull and bear boxes identically, so
                # there is nothing here for it to change.
                lives[g.id] = {
                    "top": g.top, "bottom": g.bottom,
                    "born": g.born_index, "died": None, "seen": False,
                }
            for g in (*ev.mitigated, *ev.evicted):
                rec = lives.get(g.id)
                if rec is not None:
                    rec["died"] = i
            if i in bars:
                # `ev.active` is post-mitigation, so a gap the anchor bar CLOSED past is correctly
                # not counted — mpc had already deleted its box by then.
                for g in ev.active:
                    rec = lives.get(g.id)
                    if rec is not None:
                        rec["seen"] = True
    except Exception as exc:  # noqa: BLE001 — never let an FVG hiccup break the whole chart
        log.warning("fvg overlays: replay failed at build time: %s", exc)
        return []

    overlays: list[dict] = []
    for rec in lives.values():
        if not rec["seen"]:
            continue
        born = rec["born"]
        # Pine: created at `born - 1`, right edge pushed to the current bar each surviving bar, box
        # DELETED on the death bar — so the last bar it was drawn on is `died - 1`, never `died`.
        left = max(born - 1, 0)
        right = (n - 1) if rec["died"] is None else max(born, rec["died"] - 1)
        right = min(right, n - 1)
        overlays.append({
            "type": "box", "group": GROUP_FVG,
            "t0": times[left], "t1": times[right],
            "top": round(rec["top"], 5), "bottom": round(rec["bottom"], 5),
            "style": {"fillColor": _FILL, "lineWidth": 0},
        })

    overlays.sort(key=lambda ov: ov["t0"])
    if len(overlays) > _MAX_BOXES:
        dropped = len(overlays) - _MAX_BOXES
        overlays = overlays[-_MAX_BOXES:]
        log.info("fvg overlays: capped at %d boxes — dropped the %d oldest", _MAX_BOXES, dropped)
    log.info("fvg overlays: %d bars, %d anchor bar(s) -> %d gap boxes (tf=%s, threshold=%s)",
             n, len(bars), len(overlays), timeframe, thresh)
    return overlays
