"""
structure_overlays.py — turn a run's candles into market-structure chart overlays.

Runs the CANONICAL market-structure engine (`engines/market_structure/`) over the candles the
chart is about to show and translates its per-bar events into `ChartSpec.overlays` — the same
generic box/hline/vline/label vocabulary every other overlay uses, so the frontend draws them
with zero structure-specific logic and the Layers dropdown toggles them for free.

This is NOT a second structure engine. It imports the one in `engines/market_structure/` by bare
name (same `sys.path` shim as regime/news) and only reads its public events — never re-implements
BOS/SOS/swing detection.

Four overlay groups, each a Layers checkbox, mapping 1:1 to the TradingView toggles:
  - "External Structure"   — BOS/SOS break lines + labels, and the active (unbroken) swing rays.
  - "Internal Structure"   — iBOS/iSOS break lines + labels, for the CURRENT swing range.
  - "Internal (Historic)"  — the same internal content from PREVIOUS swing ranges.
  - "Swing Point Labels"   — every swing-point text label (HH/HL/LH/LL/ASH/ASL + internal iSH/…).

TF: computed on whatever candles the spec ships (the displayed/base TF), so the lines align 1:1
with the bars on screen. Drill-down (M1/M5) is base-TF only for now — no per-window recompute.

Colours follow the source Pine's convention: a swing HIGH label is drawn in the bearish colour
(resting sell-side liquidity), a swing LOW label in the bullish colour; a break line/label takes
the colour of the direction that broke.

Label COORDINATES mirror the Pine as closely as klinecharts allows, so the chart reads like the
TradingView indicator: a break tag (BOS/SOS/iBOS/iSOS) sits at the horizontal MIDPOINT of its
break line (`_mid`, = Pine's `mid_x`) — in the gap the impulse leg left, clear of the break-bar
candles — above an up-break / below a down-break. A swing-point tag (HH/HL/LH/LL/ASH/ASL + the
internal ones) sits AT its swing bar, above a high / below a low (Pine's style_label_down/up). The
frontend then nudges + de-collides in pixel space so dense clusters stay legible.
"""

from __future__ import annotations

import logging
import sys
from pathlib import Path

log = logging.getLogger("STRUCTURE_OVERLAYS")

# engines/ on sys.path so the canonical engine imports by bare name (same pattern as regime/news).
_ENGINES = Path(__file__).resolve().parent.parent.parent.parent / "engines"
if str(_ENGINES) not in sys.path:
    sys.path.insert(0, str(_ENGINES))

# Group names — MUST match STRUCTURE_GROUPS in the frontend overlays.ts (drives default-off + order).
GROUP_EXTERNAL = "External Structure"
GROUP_INTERNAL = "Internal Structure"
GROUP_INTERNAL_HISTORIC = "Internal (Historic)"
GROUP_SWING_LABELS = "Swing Point Labels"

# Direction colours (raw hex — chart_spec emits hex, the panel consumes it).
_BULL = "#26a69a"        # break UP / swing-low labels
_BEAR = "#ef5350"        # break DOWN / swing-high labels
_INT_BULL = "#80cbc4"    # internal, muted
_INT_BEAR = "#ef9a9a"

# Safety cap per group so a pathological long run can't spawn tens of thousands of overlays.
# Keeps the most RECENT events (what a trader inspects); older ones are dropped.
_MAX_PER_GROUP = 1200


def _hline(group: str, t0: int, t1: int, price: float, color: str, *, dashed: bool = False, width: float = 1) -> dict:
    return {
        "type": "hline", "group": group, "t0": t0, "t1": t1, "price": round(price, 5),
        "style": {"color": color, "lineStyle": "dashed" if dashed else "solid", "lineWidth": width},
    }


def _label(group: str, t: int, price: float, text: str, color: str, placement: str) -> dict:
    return {
        "type": "label", "group": group, "t": t, "price": round(price, 5), "text": text,
        "placement": placement, "style": {"color": color},
    }


def _mid(a: int, b: int) -> int:
    """Bar-index midpoint of a break line (Pine's `round((swing_loc + bar_index) / 2)`), clamped ≥ 0
    so a warmup-era origin can't push it negative. Where the break LABEL is anchored — the open gap
    mid-line, clear of the candle cluster at the break bar."""
    return (max(a, 0) + max(b, 0)) // 2


def _cap_by_group(overlays: list[dict]) -> list[dict]:
    """Drop the oldest overlays in any group over the cap (keep the most recent by anchor time)."""
    counts: dict[str, int] = {}
    for ov in overlays:
        counts[ov["group"]] = counts.get(ov["group"], 0) + 1
    if all(n <= _MAX_PER_GROUP for n in counts.values()):
        return overlays
    kept: list[dict] = []
    seen: dict[str, int] = {}
    # Walk newest→oldest so we keep the recent ones, then restore chronological order.
    def anchor(ov: dict) -> int:
        return ov["t"] if ov["type"] == "label" else ov["t1"]
    for ov in sorted(overlays, key=anchor, reverse=True):
        g = ov["group"]
        if seen.get(g, 0) >= _MAX_PER_GROUP:
            continue
        seen[g] = seen.get(g, 0) + 1
        kept.append(ov)
    kept.sort(key=anchor)
    return kept


def build_market_structure_overlays(candles: list[dict], major_length: int = 15) -> list[dict]:
    """Replay `candles` through the canonical StructureEngine and emit structure overlays.

    `candles` are the spec's candles: dicts with time/open/high/low/close, sorted by time.
    Returns a list of ChartOverlay dicts (hline / label), grouped for the four Layers toggles.
    Best-effort: any failure returns [] so the rest of the chart still renders.
    """
    if len(candles) < major_length + 5:
        return []
    try:
        from market_structure import Bar, StructureEngine
    except Exception as exc:  # noqa: BLE001 — engine import is best-effort
        log.warning("structure overlays: engine import failed: %s", exc)
        return []

    times = [c["time"] for c in candles]
    n = len(candles)

    def t(idx) -> int:
        """Bar index → candle timestamp, clamped into range (events can reference warmup bars)."""
        if idx is None:
            return times[-1]
        i = 0 if idx < 0 else (n - 1 if idx >= n else idx)
        return times[i]

    eng = StructureEngine(major_length=major_length)
    ext_overlays: list[dict] = []
    swing_overlays: list[dict] = []
    # Internal overlays collected with their anchor bar index, so current-vs-historic can be
    # decided AFTER the walk against the final "most recent external swing" boundary.
    int_pending: list[tuple[int, dict]] = []

    active_high: tuple[float, int] | None = None   # (price, bar) unbroken swing high
    active_low: tuple[float, int] | None = None
    ext_break_bars: list[int] = []                  # bars where an external BOS/SOS printed (leg starts)

    try:
        for i, c in enumerate(candles):
            ev = eng.update(Bar(index=i, open=c["open"], high=c["high"], low=c["low"], close=c["close"]))
            ext, intl = ev.external, ev.internal

            # ── External: track the active (unbroken) swings for the right-edge rays ──
            if ext.unconfirmed_high_set and ext.unconfirmed_high_price is not None:
                active_high = (ext.unconfirmed_high_price, ext.unconfirmed_high_index or i)
            if ext.new_swing_high and ext.new_swing_high_price is not None:
                active_high = (ext.new_swing_high_price, ext.new_swing_high_index or i)
            if ext.unconfirmed_low_set and ext.unconfirmed_low_price is not None:
                active_low = (ext.unconfirmed_low_price, ext.unconfirmed_low_index or i)
            if ext.new_swing_low and ext.new_swing_low_price is not None:
                active_low = (ext.new_swing_low_price, ext.new_swing_low_index or i)

            # ── External breaks: BOS (continuation) / SOS (reversal) ──
            # The break LABEL sits at the horizontal MIDPOINT of the break line (Pine's
            # `mid_x = round((swing_loc + bar_index) / 2)`), NOT at the break bar. The midpoint lands
            # in the open gap the impulse leg left behind, so the chip clears the candle cluster at the
            # break bar — the fix for tags sitting on top of the bars. Above for an up-break, below for
            # a down-break (Pine's style_label_down / style_label_up).
            if ext.bull_bos and ext.bull_bos_price is not None:
                origin = ext.bull_bos_h_loc if ext.bull_bos_h_loc is not None else i
                ext_overlays.append(_hline(GROUP_EXTERNAL, t(origin), t(i), ext.bull_bos_price, _BULL, dashed=ext.bull_sos))
                ext_overlays.append(_label(GROUP_EXTERNAL, t(_mid(origin, i)), ext.bull_bos_price, "SOS" if ext.bull_sos else "BOS", _BULL, "above"))
                active_high = None
                ext_break_bars.append(i)
            if ext.bear_bos and ext.bear_bos_price is not None:
                origin = ext.bear_bos_l_loc if ext.bear_bos_l_loc is not None else i
                ext_overlays.append(_hline(GROUP_EXTERNAL, t(origin), t(i), ext.bear_bos_price, _BEAR, dashed=ext.bear_sos))
                ext_overlays.append(_label(GROUP_EXTERNAL, t(_mid(origin, i)), ext.bear_bos_price, "SOS" if ext.bear_sos else "BOS", _BEAR, "below"))
                active_low = None
                ext_break_bars.append(i)

            # ── External swing-point labels (final classification, fired at the break) ──
            if ext.broken_high_label and ext.broken_high_price is not None:
                swing_overlays.append(_label(GROUP_SWING_LABELS, t(ext.broken_high_index), ext.broken_high_price, ext.broken_high_label, _BEAR, "above"))
            if ext.broken_low_label and ext.broken_low_price is not None:
                swing_overlays.append(_label(GROUP_SWING_LABELS, t(ext.broken_low_index), ext.broken_low_price, ext.broken_low_label, _BULL, "below"))

            # ── Internal swing-point labels (iSH/iHH, iSL/iLL, and the iHL/iLH demotions) ──
            if intl.new_swing_high and intl.new_swing_high_price is not None and intl.swing_high_label:
                swing_overlays.append(_label(GROUP_SWING_LABELS, t(intl.new_swing_high_index), intl.new_swing_high_price, intl.swing_high_label, _INT_BEAR, "above"))
            if intl.new_swing_low and intl.new_swing_low_price is not None and intl.swing_low_label:
                swing_overlays.append(_label(GROUP_SWING_LABELS, t(intl.new_swing_low_index), intl.new_swing_low_price, intl.swing_low_label, _INT_BULL, "below"))
            if intl.demoted_high_label and intl.demoted_high_price is not None:
                swing_overlays.append(_label(GROUP_SWING_LABELS, t(intl.demoted_high_index), intl.demoted_high_price, intl.demoted_high_label, _INT_BEAR, "above"))
            if intl.demoted_low_label and intl.demoted_low_price is not None:
                swing_overlays.append(_label(GROUP_SWING_LABELS, t(intl.demoted_low_index), intl.demoted_low_price, intl.demoted_low_label, _INT_BULL, "below"))

            # ── Internal breaks: iBOS / iSOS. Anchor the line at the internal swing WICK that broke
            # — the ifib_seed leg anchors (ash for an up-break, asl for a down-break) land exactly on
            # that wick. NOT int_break_origin_loc: that's the order-block scan origin and floats off the
            # wick, which is what made the internal lines miss their candles. Grouped current/historic
            # after the walk. ──
            if (intl.bull_bos or intl.bull_sos) and intl.ifib_seed_ash is not None and intl.ifib_seed_ash_loc is not None:
                price, loc, sos = intl.ifib_seed_ash, intl.ifib_seed_ash_loc, bool(intl.bull_sos)
                int_pending.append((i, _hline("", t(loc), t(i), price, _INT_BULL, dashed=sos)))
                int_pending.append((i, _label("", t(_mid(loc, i)), price, "iSOS" if sos else "iBOS", _INT_BULL, "above")))
            if (intl.bear_bos or intl.bear_sos) and intl.ifib_seed_asl is not None and intl.ifib_seed_asl_loc is not None:
                price, loc, sos = intl.ifib_seed_asl, intl.ifib_seed_asl_loc, bool(intl.bear_sos)
                int_pending.append((i, _hline("", t(loc), t(i), price, _INT_BEAR, dashed=sos)))
                int_pending.append((i, _label("", t(_mid(loc, i)), price, "iSOS" if sos else "iBOS", _INT_BEAR, "below")))

        # Active (unbroken) external swings → a ray to the last bar + its ASH/ASL label.
        if active_high is not None:
            price, bar = active_high
            ext_overlays.append(_hline(GROUP_EXTERNAL, t(bar), times[-1], price, _BEAR, dashed=True))
            swing_overlays.append(_label(GROUP_SWING_LABELS, t(bar), price, "ASH", _BEAR, "above"))
        if active_low is not None:
            price, bar = active_low
            ext_overlays.append(_hline(GROUP_EXTERNAL, t(bar), times[-1], price, _BULL, dashed=True))
            swing_overlays.append(_label(GROUP_SWING_LABELS, t(bar), price, "ASL", _BULL, "below"))

        # Current vs historic internal: the "current swing range" is the latest external LEG. A leg
        # starts at a BOS/SOS, so the boundary is the second-to-last external break (the developing
        # leg plus the one just completed — a substantive recent set, robust to the pivot-confirmation
        # cluster that piles several swings up at the data's end). Internal inside it is current;
        # everything older is a previous range (the "Show Historic Internal" toggle). Empty current is
        # honest — it just means no internal structure has printed since the last break.
        if len(ext_break_bars) >= 2:
            boundary = ext_break_bars[-2]
        elif ext_break_bars:
            boundary = ext_break_bars[-1]
        else:
            boundary = 0
        for bar, ov in int_pending:
            ov["group"] = GROUP_INTERNAL if bar >= boundary else GROUP_INTERNAL_HISTORIC
    except Exception as exc:  # noqa: BLE001 — never let a structure hiccup break the whole chart
        log.warning("structure overlays: replay failed at build time: %s", exc)
        return []

    overlays = ext_overlays + swing_overlays + [ov for _, ov in int_pending]
    overlays = _cap_by_group(overlays)
    log.info("structure overlays: %d bars -> %d overlays (%d ext, %d swing-labels, %d internal)",
             n, len(overlays), len(ext_overlays), len(swing_overlays), len(int_pending))
    return overlays
