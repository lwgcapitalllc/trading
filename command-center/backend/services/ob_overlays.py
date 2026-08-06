"""
ob_overlays.py — draw the ORDER BLOCKS that were LIVE at a trade, a block or a miss.

Runs the CANONICAL order-block engine (`engines/order_blocks/`) over the candles the chart is about
to show and turns its block lifecycle into `ChartSpec.overlays` boxes — the same generic vocabulary
every other overlay uses, so the frontend draws them with zero OB-specific logic and one toggle
switches the layer off.

This is NOT a second OB engine. It imports the one in `engines/order_blocks/` by bare name (the same
`sys.path` shim as regime/news/structure/fvg) and only reads its public events.

The sibling of `fvg_overlays.py` in every respect — same anchor rule, same best-effort contract,
same "these are the INDICATOR's zones" caveat. Read that module first; only the differences are
spelled out here.

WHAT IS DRAWN, AND WHY IT IS NOT EVERY BLOCK
-------------------------------------------
A block is drawn **only if it was in the engine's live list on the bar of a trade ENTRY, a blocked
setup, or a missed setup** — all of them when several were open at once. Everything else is dropped,
for the reason the FVG layer states: the question this layer exists for is "when this trade was
taken / refused / missed, where were the order blocks?", not "paper the chart".

MEASURED on the shipped 161-trade run (`75ccc776d10c`, 32,978 M15 candles, 217 anchor bars): the run
created **2,567** blocks and **579** of them were live at an anchor. So the filter is doing the same
work here as it does for gaps (655 boxes from 215 anchor bars there), and the two layers together sit
at a readable ~1,200 boxes instead of ~3,200.

THE BLOCKS ARE mpc_assistant.pine's — AND HERE THERE IS NO FORK
--------------------------------------------------------------
Unlike the fair value gaps, this needs no "the bot ran different settings" warning: the strategy
files DROPPED order blocks entirely on 2026-07-24/25, so `mpc_assistant.pine` is the only source and
the engine defaults ARE its constants. Nothing in `mpc_sos_fade` reads a block, which also means a
drawn block never explains an entry — it is context the reader brings, not a rule the bot applied.

The one Pine input deliberately not modelled is `obDirOnly` ("Trend-Aligned Zones Only", default
**off**), which HIDES blocks opposing the current external structure. It is a drawing filter, it is
off in the panel Aaron reads, and `engines/order_blocks/CLAUDE.md` names it as something this layer
must not bake in.

BOX GEOMETRY MIRRORS THE PINE BOX, AND IT IS NOT THE FVG's
----------------------------------------------------------
A gap box tracks the live bar; an order block box is a fixed-width STUB. Pine creates it at
`[origin_index, created_index]`, then every surviving bar sets

    right = obNear ? max(bar_index + 1, origin + OB_STUB) : origin + OB_STUB

— i.e. always at least `OB_STUB` (30) bars long, and stretched out to the live bar only while price
has come back within one block-height of the zone. It is DELETED on the bar the block is mitigated,
expires or is evicted. So what is emitted is the span the box held on the last bar it was drawn.
"""

from __future__ import annotations

import bisect
import logging
import sys
from pathlib import Path
from typing import Iterable

log = logging.getLogger("OB_OVERLAYS")

# engines/ on sys.path so the canonical engines import by bare name (same pattern as regime/news).
_ENGINES = Path(__file__).resolve().parent.parent.parent.parent / "engines"
if str(_ENGINES) not in sys.path:
    sys.path.insert(0, str(_ENGINES))

# Group name — MUST match ANALYSIS_GROUPS in the frontend overlays.ts (that is what routes the
# toggle into the Analysis dropdown and defaults it OFF).
GROUP_OB = "Order Blocks"

# ── mpc_assistant.pine's locked OB drawing constants (mpc_assistant.pine:140-183) ──
MPC_OB_STUB = 30             # OB_STUB — the box's minimum width in bars

# One deep orange for BOTH directions — `OB_ACCENT #E65100`, drawn as an OUTLINE with a whisper of
# fill (`colBullOB`/`colBearOB` = 94% transparent, `OB_EDGE` = 25%). The blue/red directional
# experiment was tried and REVERTED (mpc_assistant.pine:140-143), so bull and bear look identical
# here exactly as they do on the indicator; the "OB" tag is what names the shape. That also keeps
# this layer visually distinct from the borderless grey FVG boxes sitting beside it.
_FILL = "rgba(230,81,0,0.06)"
_EDGE = "#E65100"
_LABEL = "OB"

# Payload backstop. Keeps the most RECENT blocks; a truncation is LOGGED, never silent.
#
# Raised from 1500 on 2026-08-06 alongside the fair-value-gap cap and for the same reason: the spec
# now carries the whole run (2,468 anchored blocks over 6.5 years, measured), the panel creates
# overlays for the viewport rather than for the loaded history, so the render-cost argument for a
# low cap is gone and only the payload bound remains. See `structure_overlays._MAX_PER_GROUP`.
_MAX_BOXES = 20_000


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


def build_ob_overlays(
    candles: list[dict],
    anchors_ms: Iterable[int],
    *,
    stub_bars: int = MPC_OB_STUB,
    **engine_kwargs,
) -> list[dict]:
    """Replay `candles` through the canonical OB engine and emit a box per block that was LIVE at
    one of the `anchors_ms` bars.

    `candles` are the spec's candles (time/open/high/low/close, sorted by time). `anchors_ms` are the
    trade-entry / blocked / missed timestamps. Unlike the FVG layer there is no timeframe argument —
    every OB constant is bar-counted or ATR-relative, so the engine needs no per-timeframe branch.

    `stub_bars` and `**engine_kwargs` exist so a parity test can replay an export whose Pine build
    ran different settings; production callers pass neither and get mpc_assistant's. Returns a list
    of ChartOverlay `box` dicts, all in one group. Best-effort: any failure returns [] so the rest of
    the chart still renders.
    """
    if len(candles) < 3:
        return []
    bars = _anchor_bars([c["time"] for c in candles], anchors_ms)
    if not bars:
        return []      # no trade, block or miss on screen ⇒ nothing to explain ⇒ nothing to draw

    try:
        from order_blocks import OrderBlockEngine
    except Exception as exc:  # noqa: BLE001 — engine import is best-effort
        log.warning("ob overlays: engine import failed: %s", exc)
        return []

    times = [c["time"] for c in candles]
    n = len(candles)

    # block id → its whole life. `right` is the box's right edge as the Pine last set it (see the
    # module docstring); `seen` marks it as live on at least one anchor bar, which is what gets drawn.
    lives: dict[int, dict] = {}

    def _open(o) -> None:
        lives[o.id] = {
            # Direction is deliberately NOT kept: mpc paints bull and bear identically, so there is
            # nothing here for it to change.
            "top": o.top, "bottom": o.bottom,
            "left": o.origin_index,
            # Pine's own `box.new(bar_index - off, …, bar_index, …)` — born spanning origin → the
            # bar it was added on. `_extend` overwrites this from the next bar onward.
            "right": o.created_index,
            "seen": False,
        }

    try:
        ob = OrderBlockEngine(**engine_kwargs)
        for i, c in enumerate(candles):
            h, l, cl = c["high"], c["low"], c["close"]
            ev = ob.update(i, c["open"], h, l, cl)

            for o in ev.created:
                _open(o)
            # The box's right edge, recomputed for every block still alive AFTER this bar's
            # mitigation pass — mirroring Pine `extendOBs`, which runs before creation and therefore
            # never touches a block born on this bar.
            for o in (*ev.active_bull, *ev.active_bear):
                rec = lives.get(o.id)
                if rec is None:
                    continue
                if i in bars:
                    rec["seen"] = True
                if i == o.created_index:
                    continue
                height = o.top - o.bottom
                near = (l <= o.top + height) if o.is_bullish else (h >= o.bottom - height)
                stub = o.origin_index + stub_bars
                rec["right"] = max(i + 1, stub) if near else stub
    except Exception as exc:  # noqa: BLE001 — never let an OB hiccup break the whole chart
        log.warning("ob overlays: replay failed at build time: %s", exc)
        return []

    overlays: list[dict] = []
    for rec in lives.values():
        if not rec["seen"]:
            continue
        # The stub deliberately runs PAST the live bar into empty space on the indicator; a chart
        # anchored to candle timestamps has no such space, so it clamps to the last candle.
        left = max(0, min(rec["left"], n - 1))
        right = max(left, min(rec["right"], n - 1))
        overlays.append({
            "type": "box", "group": GROUP_OB,
            "t0": times[left], "t1": times[right],
            "top": round(rec["top"], 5), "bottom": round(rec["bottom"], 5),
            "label": _LABEL, "labelAlign": "right",
            "style": {"color": _EDGE, "fillColor": _FILL, "lineWidth": 1},
        })

    overlays.sort(key=lambda ov: ov["t0"])
    if len(overlays) > _MAX_BOXES:
        dropped = len(overlays) - _MAX_BOXES
        overlays = overlays[-_MAX_BOXES:]
        log.info("ob overlays: capped at %d boxes — dropped the %d oldest", _MAX_BOXES, dropped)
    log.info("ob overlays: %d bars, %d anchor bar(s) -> %d order-block boxes",
             n, len(bars), len(overlays))
    return overlays
