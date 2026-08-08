"""
candle_overlays.py — highlight the candlestick pattern that turned price, where a setup happened.

Runs the CANONICAL candlestick engine (`engines/candlesticks/`) over the candles the chart is about
to show and paints ONE candle navy per setup: the pattern candle at the reversal.

This is NOT a second candlestick engine. It imports the one in `engines/candlesticks/` by bare name
(the same `sys.path` shim as regime/news/structure/fvg/ob) and reads its public events only.

WHAT IS DRAWN, AND WHY IT IS NOT EVERY PATTERN
---------------------------------------------
Five of the eleven patterns this reads fire on 5-9% of ALL bars (both haramis, both engulfings,
hammer, inverted hammer — see `engines/candlesticks/CLAUDE.md`), so a layer drawing every one of
them would paint roughly one bar in twelve and say nothing. The question this layer exists for is
narrower and is Aaron's: *at the points where a setup existed, which candle turned price?*

So a candle is painted only when it is the reversal candle of an ANCHOR, and the anchor set is
exactly two things (Aaron, 2026-08-08): a trade ENTRY (win or lose), and a MISSED setup that reached
**3 of 3** confluences. Nothing else.

⚠ **BLOCKED setups are deliberately NOT anchors, and they were until this rule was measured on a real
chart.** There are 324 of them on the reference run against 159 trades and 35 three-of-three misses,
so they were two thirds of every mark — and because the Blocked layer defaults OFF, they painted
navy candles in places the reader could see no setup at all. That reads as the layer firing at
random, which is exactly how it was reported. A 2/3 miss is excluded for a different reason: it was
never a setup, so it cannot be asked which candle turned it.

ONE CANDLE PER ANCHOR, AND IT IS THE ONE AT THE TURN
---------------------------------------------------
The mark always lands on the bar where price stopped going AGAINST the setup — the lowest low on a
long, the highest high on a short — because that is the reversal. What differs is how far the search
is allowed to look, and it differs by OUTCOME, because the two cases are different questions:

  **A WINNING trade** is searched over its whole hold, entry → exit. Aaron's words are *"the
  ultimate reversal point before the trade went into my favour"*, and that is exactly the deepest
  adverse price of the hold. ⚠ **MEASURED on run `997c14cc53bc` (106 winners): the adverse extreme
  sits a median of 2 bars past entry, but p90 is 27 and the worst is 112 — so a fixed short window
  finds the real turn on barely half of them.** The candidate must then be within
  `_TURN_TOLERANCE_BARS` of that extreme, or the turn simply printed no pattern and nothing is
  drawn; without that, a 112-bar hold would offer up whichever pattern happened to be nearest.

  **A LOSING trade, a BLOCKED setup or a 3/3 MISS** is searched over `_WINDOW_BARS` from the anchor.
  A loser never reversed in his favour, so it has no such point, and the only question it can answer
  is *what was on screen when I entered* — which is a question about the entry, not about the hold.
  Searching a loser's whole hold would put the mark at its stop-out, which explains nothing.

DIRECTION IS A PREFERENCE, NEVER A FILTER
-----------------------------------------
Candidate bars are ranked in three tiers before anything else is considered:

  1. a pattern pointing the SETUP's way (bullish on a long, bearish on a short) — *"it's really the
     best candle that was going with the direction of the trade"*;
  2. a NEUTRAL pattern (hammer / inverted hammer / doji, which the source Pine draws with no trend
     filter and therefore no direction — see `engines/candlesticks/CLAUDE.md`);
  3. a pattern pointing AGAINST the setup.

⚠ **Tier 3 is kept, and it is half the point of the layer** (Aaron, 2026-08-08): *"if I'm trying to
take a short with a bullish candle printed, and that's why price reversed, yeah, highlight that …
if it lines up with my trades, then great. If not, it will show me why I was wrong."* So an opposing
candle is only ever shown when there is no aligned or neutral one at the turn — which is the honest
answer to *what was actually printing there*, and never a filter that hides it.

⚠ **A bearish engulfing on a long that WON is what this ordering fixes.** It was the mark on the
reference trade because ranking started at nearest-the-extreme, so whichever pattern happened to sit
closest won regardless of which way it pointed. Nearness is now the tie-break WITHIN a tier, not the
first question.

Within a tier: the bar NEAREST the extreme wins; then the bar carrying more patterns (a hammer that
is also a doji says more than either alone); then the earlier bar, so the answer is deterministic.
The chosen bar's patterns are reordered so the one that EARNED the tier is `label` — otherwise a bar
carrying both would be named after the wrong one.

THE SETTINGS ARE THE CHART'S, AND THEY ARE NOT THE ENGINE'S DEFAULTS
-------------------------------------------------------------------
`candlesticks.CHART_PRESET` — trend 117, doji size 0.01, and the eleven patterns Aaron's brother
reads. Those are HIS TradingView inputs, taken off a real export's own `cfg_*` columns rather than
transcribed, and the engine's own defaults stay at the source Pine's (5 / 0.05) because an engine
mirrors its Pine and a CONSUMER pins what it trades. Do not "tidy" this to the defaults — the chart
would stop matching the indicator it is read against.
"""

from __future__ import annotations

import bisect
import logging
import sys
from pathlib import Path
from typing import Iterable, Optional

log = logging.getLogger("CANDLE_OVERLAYS")

# engines/ on sys.path so the canonical engines import by bare name (same pattern as regime/news).
_ENGINES = Path(__file__).resolve().parent.parent.parent.parent / "engines"
if str(_ENGINES) not in sys.path:
    sys.path.insert(0, str(_ENGINES))

# Group name — MUST match ANALYSIS_GROUPS in the frontend overlays.ts (that is what routes the
# toggle into the Analysis dropdown and defaults it OFF).
GROUP_CANDLES = "Candlestick Reversals"

# How far past the anchor bar to look for the turn, when there is no hold to search. 3 bars is 45
# minutes on M15 — long enough for the "price ran a little further, then reversed" case and short
# enough that the mark cannot wander into an unrelated move. Aaron's choice, 2026-08-08.
_WINDOW_BARS = 3

# How close a pattern candle must sit to the adverse extreme of a WINNING hold to be called its
# turn. A hold can run 112 bars (measured), so without this the nearest pattern to the extreme could
# be most of a day away and would be reported as the reversal candle. 2 bars either side.
_TURN_TOLERANCE_BARS = 2

# Navy. ⚠ A true navy (#1e3a8a and darker) is close to INVISIBLE on this theme's near-black plot —
# checked against `bgBase` before picking — so this is the most navy-reading blue that still stands
# out against the up/down candles it sits between, which is what the layer is for.
_NAVY = "#2f5fe0"
_NAVY_EDGE = "#7ea2ff"

# Payload backstop. A run cannot produce more of these than it has anchors (~500 on a 6.5-year M15
# run, and at most one candle each), so this is a bound and not a policy — a truncation is LOGGED,
# never silent. See `fvg_overlays._MAX_BOXES`.
_MAX_MARKS = 20_000


def _anchor_bars(
    times: list[int], anchors: Iterable[tuple[int, str, Optional[int]]],
) -> list[tuple[int, str, Optional[int]]]:
    """Anchor `(timestamp, direction, hold_end_ms)` triples → `(bar index, direction, end bar)`,
    clipped to the loaded candles.

    An anchor between two bars belongs to the bar it is INSIDE (the last bar at or before it), which
    is the bar whose close the engine had just processed when that trade/block/miss happened — the
    same rule `fvg_overlays._anchor_bars` follows.

    `hold_end_ms` is the exit of a WINNING trade and `None` for everything else; see the module
    docstring for why only a winner is searched over its hold. An end that lands before the anchor,
    or off the loaded candles, degrades to `None` rather than being dropped — the anchor is still a
    real setup and still deserves its short-window answer.
    """
    out: list[tuple[int, str, Optional[int]]] = []
    if not times:
        return out
    lo, hi = times[0], times[-1]
    for t, direction, end_ms in anchors:
        if not isinstance(t, (int, float)) or not (lo <= t <= hi):
            continue
        i = bisect.bisect_right(times, int(t)) - 1
        if i < 0:
            continue
        end_bar: Optional[int] = None
        if isinstance(end_ms, (int, float)) and lo <= end_ms <= hi:
            j = bisect.bisect_right(times, int(end_ms)) - 1
            if j > i:
                end_bar = j
        out.append((i, "short" if str(direction).lower().startswith("s") else "long", end_bar))
    return out


def _adverse_extreme(candles: list[dict], start: int, end: int, direction: str) -> int:
    """The bar in `[start, end]` where price ran furthest AGAINST `direction` — the reversal."""
    extreme = start
    if direction == "short":
        for i in range(start, end + 1):
            if candles[i]["high"] > candles[extreme]["high"]:
                extreme = i
    else:
        for i in range(start, end + 1):
            if candles[i]["low"] < candles[extreme]["low"]:
                extreme = i
    return extreme


def _alignment(patterns: list, direction: str) -> int:
    """How well the best pattern on a bar points the SETUP's way — 0 aligned, 1 neutral, 2 against.

    A long setup wants a bullish reversal (+1) and a short wants a bearish one (-1); the engine emits
    0 for the three patterns its source Pine draws with no trend filter, and a neutral candle at the
    turn says more than an opposing one. Lower is better, so this sorts directly.
    """
    want = -1 if direction == "short" else 1
    best = 2
    for p in patterns:
        if p.direction == want:
            return 0
        if p.direction == 0:
            best = min(best, 1)
    return best


def _pick_reversal_bar(
    candles: list[dict],
    hits: dict[int, list],
    start: int,
    direction: str,
    window: int,
    hold_end: Optional[int],
) -> Optional[int]:
    """The bar that turned price for this anchor, or None if no bar there carries a pattern.

    `hits` maps a bar index to the patterns that fired on it. With a `hold_end` the search runs over
    the whole hold and the answer must sit within `_TURN_TOLERANCE_BARS` of its adverse extreme;
    without one it runs over `window` bars from the anchor and any pattern bar in it qualifies.

    Direction is the FIRST key — see the module docstring. It is a preference and not a filter, so a
    window holding only opposing patterns still returns one.
    """
    last = len(candles) - 1
    if hold_end is not None:
        end = min(hold_end, last)
        extreme = _adverse_extreme(candles, start, end, direction)
        # ⚠ The tolerance is what stops a 112-bar hold reporting whatever pattern happened to be
        # nearest its extreme as "the reversal candle". No pattern at the turn is a real answer.
        lo = max(start, extreme - _TURN_TOLERANCE_BARS)
        hi = min(end, extreme + _TURN_TOLERANCE_BARS)
    else:
        end = min(start + window, last)
        extreme = _adverse_extreme(candles, start, end, direction)
        lo, hi = start, end

    candidates = [i for i in range(lo, hi + 1) if hits.get(i)]
    if not candidates:
        return None
    # Aligned beats neutral beats opposing; THEN nearest the turn; then the bar carrying MORE
    # patterns (a hammer that is also a doji is a stronger statement than either alone); then the
    # earlier bar, so the answer is deterministic.
    return min(candidates, key=lambda i: (
        _alignment(hits[i], direction), abs(i - extreme), -len(hits[i]), i,
    ))


def build_candle_overlays(
    candles: list[dict],
    anchors: Iterable[tuple[int, str, Optional[int]]],
    *,
    window: int = _WINDOW_BARS,
    trend: Optional[int] = None,
    doji_size: Optional[float] = None,
    patterns: Optional[Iterable[str]] = None,
) -> list[dict]:
    """Replay `candles` through the canonical candlestick engine and emit one `candle` overlay per
    anchor's reversal candle.

    `candles` are the spec's candles (time/open/high/low/close, sorted by time). `anchors` are
    `(time_ms, direction, hold_end_ms)` triples — trade entries, blocked setups and 3/3 missed
    setups — where `hold_end_ms` is a WINNING trade's exit and `None` for everything else.

    The keyword arguments exist so a test can drive different settings; production callers pass none
    of them and get `CHART_PRESET`. Returns a list of ChartOverlay `candle` dicts, all in one group.
    Best-effort: any failure returns [] so the rest of the chart still renders.
    """
    if len(candles) < 2:
        return []
    bars = _anchor_bars([c["time"] for c in candles], anchors)
    if not bars:
        return []      # no trade, block or 3/3 miss on screen ⇒ nothing to explain ⇒ nothing to draw

    try:
        from candlesticks import CHART_PRESET, CandlestickEngine
    except Exception as exc:  # noqa: BLE001 — engine import is best-effort
        log.warning("candle overlays: engine import failed: %s", exc)
        return []

    cfg = dict(CHART_PRESET)
    if trend is not None:
        cfg["trend"] = trend
    if doji_size is not None:
        cfg["doji_size"] = doji_size
    if patterns is not None:
        cfg["patterns"] = tuple(patterns)

    # bar index → the patterns that fired on it. Only bars that fired are keyed, so this is small.
    hits: dict[int, list] = {}
    try:
        cs = CandlestickEngine(**cfg)
        for i, c in enumerate(candles):
            ev = cs.update(i, c["open"], c["high"], c["low"], c["close"])
            if ev.detected:
                hits[i] = list(ev.detected)
    except Exception as exc:  # noqa: BLE001 — never let a candle hiccup break the whole chart
        log.warning("candle overlays: replay failed at build time: %s", exc)
        return []

    # bar index → the patterns to name on it, the one matching the setup's direction FIRST. Several
    # anchors can resolve to ONE candle (two setups a bar apart), and that is one mark, not two
    # stacked; the first anchor to claim it names it.
    marked: dict[int, list] = {}
    for start, direction, hold_end in bars:
        i = _pick_reversal_bar(candles, hits, start, direction, window, hold_end)
        if i is None:
            continue
        want = -1 if direction == "short" else 1
        # Stable sort: aligned, then neutral, then opposing — so `label` names the pattern that
        # earned the bar its rank rather than whichever the engine happened to emit first.
        ordered = sorted(hits[i], key=lambda p: 0 if p.direction == want else (1 if p.direction == 0 else 2))
        marked.setdefault(i, ordered)

    overlays: list[dict] = []
    for i in sorted(marked):
        c = candles[i]
        found = marked[i]
        overlays.append({
            "type": "candle", "group": GROUP_CANDLES,
            "t": c["time"],
            "open": c["open"], "high": c["high"], "low": c["low"], "close": c["close"],
            # The label is the pattern's own name from the registry — nothing here words it, so a
            # chart and a config can be lined up on one string.
            "label": found[0].label,
            "extra": len(found) - 1,
            # +1 / -1 / 0 exactly as the source Pine DRAWS it. The chart uses it to say which way a
            # pattern points; it never decides WHETHER the candle is painted.
            "patternDir": found[0].direction,
            "patterns": [p.label for p in found],
            "style": {"color": _NAVY_EDGE, "fillColor": _NAVY},
        })

    if len(overlays) > _MAX_MARKS:
        dropped = len(overlays) - _MAX_MARKS
        overlays = overlays[-_MAX_MARKS:]
        log.info("candle overlays: capped at %d marks — dropped the %d oldest", _MAX_MARKS, dropped)
    log.info("candle overlays: %d bars, %d anchor(s) -> %d marked candle(s) (trend=%s doji=%s)",
             len(candles), len(bars), len(overlays), cfg["trend"], cfg["doji_size"])
    return overlays
