"""
liquidity_overlays.py — draw the liquidity levels that were LIVE when something happened, and say
which of them price had already TAKEN.

Runs the CANONICAL liquidity engine (`engines/liquidity/`) over the candles the chart is about to
show and turns its level lifecycle into `ChartSpec.overlays` hlines — the same generic vocabulary
every other overlay uses, so the frontend draws them with zero liquidity-specific logic and a toggle
switches each tier off.

This is NOT a second liquidity engine. It imports the one in `engines/liquidity/` by bare name (the
same `sys.path` shim as regime/news/structure/fvg/ob) and reads only its public events. It is the
FIRST consumer that engine has ever had — it was written, Pine-parity-validated and then imported by
nothing for a year.

WHY IT IS ANCHORED, AND THE NUMBER THAT DECIDED IT
--------------------------------------------------
A liquidity level is not rare the way an order block is. Every day mints a PDH and a PDL, every
session close a high and a low, and the H4 tier rolls SIX TIMES A DAY. MEASURED over the full
history of run `1bbc8fa7773d` (155,891 M15 candles, 2020 → 2026): **35,028 levels created**, of
which 20,376 — 58% — are H4. That is past `_MAX_PER_GROUP` (20,000), so drawing all of them would
have been a silent truncation of the OLDEST levels, which is the half a reader scrolls back to.

So the same anchor rule the gap and block layers use applies here: a level is drawn only if it was
in the engine's live set on the bar of a trade ENTRY, a blocked setup or a missed setup. On that
same run that is **7,106 levels** — the same order as the gap layer's 2,822 and the block layer's
579 — and it answers the question actually being asked, which is *what liquidity was in play when
this setup fired, and had it already been swept?*

⚠ **This is therefore NOT the same view as the indicator's.** `mpc_assistant.pine` draws the ~13
levels that are live RIGHT NOW and nothing else; it never shows you a level from 2021, because
there is no 2021 on a live chart. This layer shows the historical set at the bars that matter. The
two agree about what a level IS and disagree about which ones are on screen, and that difference is
structural rather than a fork to be closed.

THREE GROUPS, NOT ONE
---------------------
The tiers are toggled separately because they differ by an order of magnitude in volume and by a lot
in what they mean. H4 alone is 58% of the levels; a reader following daily and session sweeps wants
it off, and a reader timing an entry off the last H4 candle wants only it. The indicator gets away
with one switch because it only ever draws the live set.

SWEPT IS THE POINT, AND IT IS DRAWN THE WAY THE INDICATOR DRAWS IT
------------------------------------------------------------------
`showMitLiq` went TRUE in `mpc_assistant.pine` on 2026-08-07: a level price has taken is not deleted,
it FREEZES at the break bar, turns dotted and greys out. That is the whole feature here — a swept
level is where a pool was taken, which is the read — so a taken level is emitted dotted, grey, and
ending at the bar it was taken on.

⚠ **The engine must therefore be constructed with `hide_mitigated_on_new_day=False`.** Its default is
`True`, which is the Pine's `i_currentDayOnly` tidy — and that tidy is GATED on `not showMitLiq`, so
today's indicator never runs it. Left at the default, every swept level older than the current NY day
would be evicted before it could be drawn, and the layer would show almost nothing but live levels:
it would look like it worked, on the one thing it exists to show.
"""

from __future__ import annotations

import bisect
import logging
import sys
from pathlib import Path
from typing import Iterable, Optional

log = logging.getLogger("LIQ_OVERLAYS")

# engines/ on sys.path so the canonical engines import by bare name (same pattern as regime/news).
_ENGINES = Path(__file__).resolve().parent.parent.parent.parent / "engines"
if str(_ENGINES) not in sys.path:
    sys.path.insert(0, str(_ENGINES))

# Group names — MUST match ANALYSIS_GROUPS in the frontend overlays.ts (that is what routes each
# toggle into the Analysis dropdown and defaults it OFF).
GROUP_LIQ_HTF = "Liquidity — Daily/Weekly"
GROUP_LIQ_SESSION = "Liquidity — Sessions"
GROUP_LIQ_H4 = "Liquidity — H4"

GROUPS = (GROUP_LIQ_HTF, GROUP_LIQ_SESSION, GROUP_LIQ_H4)

# The engine's `kind` → the group it is drawn in. Every kind the engine can emit must appear here;
# `_group_for` RAISES on an unknown one rather than dropping it, because a new level kind silently
# missing from the chart is indistinguishable from a market that never printed one.
_KIND_GROUP = {
    "daily": GROUP_LIQ_HTF,
    "weekly": GROUP_LIQ_HTF,
    "pwc": GROUP_LIQ_HTF,
    "session": GROUP_LIQ_SESSION,
    "h4": GROUP_LIQ_H4,
}

# ── Colours ──
# mpc_assistant.pine draws the daily, weekly and session levels in BLACK (`i_dailyColor` etc.) and
# the H4 pair in `#FF6B35`. The H4 orange is reproduced exactly — it is the colour Aaron reads those
# levels in. The black is NOT, and that is a deliberate deviation rather than an oversight: this
# chart renders on a dark background, where black is invisible, so the two black tiers take a hue
# each. They are picked away from every colour already on this chart — structure teal (#26a69a),
# fair-value-gap slate (#94a3b8) and order-block orange (#E65100).
_COLOR = {
    GROUP_LIQ_HTF: "#38bdf8",  # sky — the daily/weekly pools
    GROUP_LIQ_SESSION: "#a78bfa",  # violet — Asia / London / NY
    GROUP_LIQ_H4: "#FF6B35",  # mpc's own H4_ACTIVE_COLOR, reproduced
}
# mpc's H4_SWEPT_COLOR hue. One grey for every taken level, whatever tier it came from: once a pool
# is gone, which tier it belonged to is on the label, and colouring spent levels by tier would give
# the loudest visual weight to the thing that is finished with.
_SWEPT_COLOR = "#999999"

# How far back the origin scan may look for the candle that MADE a level, mirroring the Pine's
# `LIQ_ORIGIN_CAP`. See `_origin_bar`.
_ORIGIN_CAP = 1500

# Payload backstop, per group, matching `structure_overlays._MAX_PER_GROUP`. A truncation is LOGGED
# and keeps the most RECENT levels — never silent. On the measured run the largest group lands at
# ~4,100, so this is headroom rather than a working limit.
_MAX_PER_GROUP = 20_000


def _group_for(kind: str) -> str:
    try:
        return _KIND_GROUP[kind]
    except KeyError:  # pragma: no cover — guarded by test_every_engine_kind_has_a_group
        raise KeyError(
            f"liquidity overlays: engine emitted kind {kind!r}, which no group claims. Add it to "
            f"_KIND_GROUP (and to ANALYSIS_GROUPS in the frontend if it needs its own toggle)."
        ) from None


def sweep_label_for(side: str, engine_label: Optional[str]) -> Optional[str]:
    """The BSL/SSL tag a taken level carries.

    BSL = buy-side liquidity, the pool of stops resting ABOVE a high; SSL = sell-side, below a low.
    So a swept HIGH is BSL and a swept LOW is SSL — definitional, not a measurement, and it is the
    vocabulary `mpc_assistant.pine`'s own liquidity rows use for EVERY tier (`liq_dh := "BSL"`,
    `liq_ash := "BSL"`, …).

    The engine models `sweep_label` on the **h4 kind only**, because that is the one tier whose Pine
    block prints the tag on the chart. Where it gives one, it WINS — deriving over the top of a value
    the engine already computed is exactly the second-claim defect this repo keeps meeting. Where it
    gives none, the side is used. `test_the_derived_sweep_label_agrees_with_the_engines_own` pins the
    two against each other on real h4 sweeps, which is what keeps the derivation honest.
    """
    if engine_label:
        return engine_label
    if side == "high":
        return "BSL"
    if side == "low":
        return "SSL"
    return None  # PWC — a reference close, never swept, so it has no side and no tag


def _anchor_bars(times: list[int], anchors_ms: Iterable[int]) -> set[int]:
    """Anchor timestamps → the bar index each one falls on, clipped to the loaded candles.

    An anchor between two bars belongs to the bar it is INSIDE (the last bar at or before it), which
    is the bar whose close the engine had just processed when that trade/block/miss happened. Same
    rule and same reasoning as `fvg_overlays._anchor_bars`.
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


def _origin_bar(candles: list[dict], created_index: int, price: float, side: str) -> int:
    """The bar that MADE this level — the Pine's `f_originHigh` / `f_originLow`.

    A level is CREATED on the first bar of the period after the one that produced it, so anchoring
    its line there would start every line a full period to the right of the candle it describes. The
    Pine scans back for the most recent bar that REACHED the price and starts the line there, which
    is what makes a PDH line visibly begin at yesterday's high.

    This is geometry over candles the caller already holds, not a second opinion about what the level
    is: the engine owns the PRICE and this only asks which bar touched it.

    ⚠ It scans from `created_index` BACKWARDS, never from the live bar. The Pine calls its scan on
    the creation bar, and scanning from anywhere later would find a bar that re-touched the level
    long afterwards — drawing the line from the sweep instead of from the origin.

    Falls back to `created_index` when nothing within `_ORIGIN_CAP` reached the price (a `pwc` level,
    whose price is a CLOSE and need never have been touched as a high or a low — the Pine does not
    scan an origin for it either — or a level whose origin has aged out of the window).
    """
    if side not in ("high", "low"):
        return created_index
    lo = max(0, created_index - _ORIGIN_CAP)
    for i in range(created_index, lo - 1, -1):
        c = candles[i]
        if (c["high"] >= price) if side == "high" else (c["low"] <= price):
            return i
    return created_index


def build_liquidity_overlays(
    candles: list[dict],
    anchors_ms: Iterable[int],
    *,
    hide_mitigated_on_new_day: bool = False,
) -> list[dict]:
    """Replay `candles` through the canonical liquidity engine and emit an hline per level that was
    LIVE at one of the `anchors_ms` bars.

    `candles` are the spec's candles (time/high/low/close, sorted by time). `anchors_ms` are the
    trade-entry / blocked / missed timestamps.

    A level's line runs from the candle that made it to the bar it stopped being drawn on: the bar it
    was SWEPT on if price took it, otherwise the last bar before its period rolled (or the final
    candle if it is still live). A swept level is dotted and grey and its label carries BSL/SSL; a
    live one is solid in its tier's colour.

    `hide_mitigated_on_new_day` exists so a test can drive the engine's other branch; production
    passes nothing and gets `False`, which is what today's indicator does. Returns a list of
    ChartOverlay `hline` dicts across the three groups. Best-effort: any failure returns [] so the
    rest of the chart still renders.
    """
    if len(candles) < 2:
        return []
    times = [c["time"] for c in candles]
    bars = _anchor_bars(times, anchors_ms)
    if not bars:
        return []  # no trade, block or miss on screen ⇒ nothing to explain ⇒ nothing to draw

    try:
        from liquidity import LiquidityEngine
    except Exception as exc:  # noqa: BLE001 — engine import is best-effort
        log.warning("liquidity overlays: engine import failed: %s", exc)
        return []

    n = len(candles)
    # level id → its whole life. `gone` is the bar it was evicted on (None = still live at the last
    # candle); `swept` is the bar price took it (None = never taken); `seen` marks it as live on at
    # least one anchor bar, which is what gets drawn.
    lives: dict[int, dict] = {}

    try:
        liq = LiquidityEngine(hide_mitigated_on_new_day=hide_mitigated_on_new_day)
        for i, c in enumerate(candles):
            ev = liq.update(i, c["time"], c["high"], c["low"], c["close"])
            for lv in ev.created:
                lives[lv.id] = {
                    "name": lv.name,
                    "kind": lv.kind,
                    "side": lv.side,
                    "price": lv.price,
                    "born": lv.created_index,
                    "swept": None,
                    "sweep_label": None,
                    "gone": None,
                    "seen": False,
                }
            for lv in ev.mitigated:
                rec = lives.get(lv.id)
                if rec is not None and rec["swept"] is None:
                    rec["swept"] = i
                    rec["sweep_label"] = sweep_label_for(lv.side, lv.sweep_label)
            for lv in ev.evicted:
                rec = lives.get(lv.id)
                if rec is not None and rec["gone"] is None:
                    rec["gone"] = i
            if i in bars:
                # `ev.active` is post-mitigation and INCLUDES levels already taken — which is the
                # point: a pool that had been swept before this setup fired is the read, not noise.
                for lv in ev.active:
                    rec = lives.get(lv.id)
                    if rec is not None:
                        rec["seen"] = True
    except Exception as exc:  # noqa: BLE001 — never let a liquidity hiccup break the whole chart
        log.warning("liquidity overlays: replay failed at build time: %s", exc)
        return []

    by_group: dict[str, list[dict]] = {g: [] for g in GROUPS}
    for rec in lives.values():
        if not rec["seen"]:
            continue
        group = _group_for(rec["kind"])
        born = rec["born"]
        swept = rec["swept"]
        # Where the line STOPS. Swept ⇒ it froze at the break bar (the Pine stops advancing its x2
        # there). Otherwise it ran until its period rolled, so the last bar it was drawn on is the
        # one BEFORE the eviction; still live ⇒ the last candle.
        if swept is not None:
            right = swept
        elif rec["gone"] is not None:
            right = max(born, rec["gone"] - 1)
        else:
            right = n - 1
        left = _origin_bar(candles, min(born, n - 1), rec["price"], rec["side"])
        right = min(max(right, left), n - 1)

        label = rec["name"]
        if swept is not None and rec["sweep_label"]:
            label = f"{rec['name']} swept · {rec['sweep_label']}"
        # ⚠ `label` is a TOP-LEVEL field on the overlay, NOT part of `style` — the panel reads
        # `ov.label` and spreads `style` separately (`ChartPanel/index.tsx`, the `hline` branch of
        # the overlay effect). Putting it inside `style` type-checks on this side, survives the
        # round trip, and simply never draws: the levels would render as unlabelled lines, which on
        # a layer whose entire job is naming which pool was taken is the whole feature missing with
        # nothing raising. Same shape as `HLineOverlay` in the frontend's `types.ts`.
        by_group[group].append(
            {
                "type": "hline",
                "group": group,
                "t0": times[left],
                "t1": times[right],
                "price": round(rec["price"], 5),
                "label": label,
                "style": {
                    "color": _SWEPT_COLOR if swept is not None else _COLOR[group],
                    "lineStyle": "dashed" if swept is not None else "solid",
                    "lineWidth": 1,
                },
            }
        )

    overlays: list[dict] = []
    for group in GROUPS:
        rows = sorted(by_group[group], key=lambda ov: ov["t0"])
        if len(rows) > _MAX_PER_GROUP:
            dropped = len(rows) - _MAX_PER_GROUP
            rows = rows[-_MAX_PER_GROUP:]
            log.info(
                "liquidity overlays: %s capped at %d — dropped the %d oldest",
                group,
                _MAX_PER_GROUP,
                dropped,
            )
        overlays.extend(rows)

    swept_n = sum(1 for ov in overlays if ov["style"]["lineStyle"] == "dashed")
    log.info(
        "liquidity overlays: %d bars, %d anchor bar(s) -> %d levels (%d swept) across %s",
        n,
        len(bars),
        len(overlays),
        swept_n,
        {g: sum(1 for ov in overlays if ov["group"] == g) for g in GROUPS},
    )
    return overlays
