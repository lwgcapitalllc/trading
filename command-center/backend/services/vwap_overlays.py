"""
vwap_overlays.py — the session VWAP line, computed server-side from the run's own bars.

Runs the CANONICAL VWAP engine (`engines/vwap/`) over the candles the chart is about to show and
returns ONE `ChartSpec.indicators` entry: a main-pane line series, one value per bar. The panel
already knows how to draw a shipped series and already gives every indicator its own toggle, so
this layer needed no new template, no new render effect and no new panel concept — the same payoff
`ob_overlays.py` recorded when it reused the generic `box`.

This is NOT a second VWAP implementation. It imports `engines/vwap/` by bare name (the same
`sys.path` shim as regime/news/structure/fvg/ob) and reads only its public events.

WHY IT IS AN INDICATOR AND NOT AN OVERLAY
-----------------------------------------
Every other layer here is a shape at a place — a box, a level, a tag. A VWAP is a VALUE PER BAR,
which is what `ChartIndicator` is for, and what `mapSeriesToCandles` exists to re-time when the
reader zooms to a coarser display timeframe. Emitting ~156k one-bar hlines instead would be the
same picture built out of the wrong primitive, and the panel's overlay budget is superlinear.

IT REFUSES WITHOUT VOLUME, AND THAT IS THE WHOLE CONTRACT
---------------------------------------------------------
A VWAP is a VOLUME-weighted mean. Given bars with no volume the arithmetic still runs — it
degenerates into a plain running mean of hlc3 — and it produces a smooth, plausible, completely
different line that would sit on the chart under the name VWAP and disagree with the one on
Aaron's TradingView chart. So a missing or unknown volume is a REFUSAL, never a fallback:

  * no `volume` key on the candles                → no layer (the feed does not carry it)
  * `volume` present but None/NaN on ANY bar      → no layer (partly-known is not known)
  * every bar has a real figure, some of them 0   → DRAW (a dead session really does trade 0 ticks)

The last line is the distinction that matters and it is this repo's standing rule: a zero-volume
bar is a measurement, an absent one is the absence of a measurement, and collapsing them is how a
chart starts stating things nobody measured. Absence removes the toggle, which is the same way the
Blocked and Missed layers vanish on a runner that cannot report them.

⚠ Bars cached before `backtest/data/cache.py::FEED_VERSION` 3 carry NO volume — the VPS agent
dropped MT5's `tick_volume` at `_rates_to_bars` until 2026-08-06. Those files re-pull themselves on
next use, so an old run's chart grows this layer once its bars have been refetched.

TICK VOLUME, WHICH IS THE RIGHT SERIES RATHER THAN THE AVAILABLE ONE
--------------------------------------------------------------------
`volume` here is MT5's `tick_volume` — the number of price changes in the bar, not contracts. For a
CFD that is the only real answer (`real_volume` is 0 on every broker here, since there is no
exchange behind the quote), and it is also exactly what TradingView plots as `volume` on the same
symbol — which is the series `engines/vwap/` was validated against at 100% Pine parity. So the line
this draws and the line on the TradingView chart are computed from the same numbers.

THE ANCHOR IS THE TRADING DAY, AND IT IS CALIBRATED FOR XAUUSD
---------------------------------------------------------------
The engine re-anchors at 18:00 New York, DST-aware — the same trading-day boundary the liquidity
engine's daily level uses, and the one validated at Pine parity for gold. That default is carried
here rather than re-stated, so there is one place to change it. An instrument that opens at a
different hour would need its own; the engine takes it as a constructor argument.

The reader sees the reset as a jump in the line each session, which is what a session VWAP does.
"""

from __future__ import annotations

import logging
import math
import sys
from pathlib import Path
from typing import Optional

log = logging.getLogger("VWAP_OVERLAYS")

# engines/ on sys.path so the canonical engines import by bare name (same pattern as regime/news).
_ENGINES = Path(__file__).resolve().parent.parent.parent.parent / "engines"
if str(_ENGINES) not in sys.path:
    sys.path.insert(0, str(_ENGINES))

# Display name — this is the string the panel's toggle carries, and it is the identity klinecharts
# registers the indicator template under. Keep it stable: the reader's on/off choice is keyed on it.
INDICATOR_VWAP = "Session VWAP"

# Prices here are ~4,000 with a 2dp tick, so 5dp is already past the instrument's resolution and is
# the same rounding `_build_structure` gives its ATR series. It is worth doing: unrounded floats
# serialise to 17 significant digits and this series has one point per bar.
_PRICE_DP = 5


def build_vwap_indicator(candles: list[dict]) -> Optional[dict]:
    """The session-VWAP series for `candles`, or None when it cannot honestly be computed.

    `candles` are the ChartSpec candle dicts, which carry `volume` only when the run's feed did.
    Returns a `ChartIndicator`: main pane, `defaultOn` False, one `{time, value}` per bar that has
    a value (the bars before a session's first traded tick have none, exactly as Pine's `na`).

    Best-effort like every other layer builder — any failure logs and returns None, because a chart
    is worth more than a line on it.
    """
    if not candles:
        return None
    try:
        from vwap import VwapEngine  # canonical engine, bare-name import
    except Exception:                                     # noqa: BLE001 — layer is optional
        log.warning("vwap_overlays: canonical VWAP engine unavailable; layer skipped", exc_info=True)
        return None

    volumes = _volumes_or_none(candles)
    if volumes is None:
        return None

    try:
        engine = VwapEngine()
        series: list[dict] = []
        for i, (c, vol) in enumerate(zip(candles, volumes)):
            ev = engine.update(i, c["time"], c["high"], c["low"], c["close"], vol)
            if ev.value is not None:
                series.append({"time": c["time"], "value": round(ev.value, _PRICE_DP)})
    except Exception:                                     # noqa: BLE001 — layer is optional
        log.warning("vwap_overlays: VWAP replay failed; layer skipped", exc_info=True)
        return None

    if not series:
        # Every bar in the run had zero volume. Real (a symbol whose feed reports none) rather than
        # a bug, and there is no line to draw — so no toggle, rather than an empty one.
        log.info("vwap_overlays: no VWAP value on any of %d candles (all zero volume)", len(candles))
        return None

    log.info("vwap_overlays: %d VWAP points over %d candles", len(series), len(candles))
    return {
        "name": INDICATOR_VWAP,
        "params": {"anchor": "trading day (18:00 America/New_York)", "source": "hlc3 × tick volume"},
        "pane": "main",
        # OFF on arrival, like every analysis layer added since the fair value gaps. A chart should
        # open on the run, and each extra reading is something the reader asks for.
        "defaultOn": False,
        "series": series,
    }


def _volumes_or_none(candles: list[dict]) -> Optional[list[float]]:
    """Every candle's volume as a float, or None if ANY bar's is missing or not a number.

    ⚠ All-or-nothing on purpose. A run whose bars are half re-fetched would otherwise get a line
    that is a true VWAP over part of its history and a plain hlc3 mean over the rest, with the
    seam invisible — which is worse than no line, because the wrong half is not marked.
    """
    out: list[float] = []
    for i, c in enumerate(candles):
        v = c.get("volume")
        if v is None or (isinstance(v, float) and math.isnan(v)):
            log.info(
                "vwap_overlays: candle %d of %d has no volume; layer skipped. Bars cached before "
                "FEED_VERSION 3 carry none and re-pull themselves — but a file fetched AFTER that "
                "bump and BEFORE the VPS agent was deployed is stamped current while holding no "
                "volume, and will not re-pull. Check BarCache.has_volume(); if it is False, delete "
                "that pair's .csv and .meta.json.",
                i, len(candles),
            )
            return None
        try:
            out.append(float(v))
        except (TypeError, ValueError):
            log.warning("vwap_overlays: candle %d has a non-numeric volume %r; layer skipped", i, v)
            return None
    return out
