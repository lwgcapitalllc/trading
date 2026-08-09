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

EVERY PATTERN CANDLE IN THE SETUP'S SPAN, NOT JUST THE DEEPEST ONE
-----------------------------------------------------------------
An anchor is a SPAN — `(start, direction, end)` — and the layer paints every bar in it that carries
a pattern, from `start` up to and including the bar price ran FURTHEST AGAINST the setup (lowest low
on a long, highest high on a short). That last bar is the turn; everything before it is the
retracement the setup was entered into.

Aaron's words, 2026-08-08: *"you don't only have to give me the deepest candle — you could give me
all the candles that would have shown a possible reversal all the way up to the deepest one … so
let's say I entered at the fifty, but there was no reversal candles until 0.702, and then maybe
0.786. I could see, wow, I could have taken a trade at 0.702 or 0.786."* Read with the **Fibs**
layer on, each mark sits on a rung, and the layer answers which entry level had a candle behind it.

⚠ **It used to paint ONE candle per anchor and that lost the whole question.** The single mark could
only ever say *the turn had a pattern* / *it did not*; it could not say *there were three, and the
deepest two were better entries than the one I took*.

  - **A TRADE** spans entry → exit, win or lose. ⚠ **MEASURED on run `997c14cc53bc` (106 winners):
    the adverse extreme sits a median of 2 bars past entry, but p90 is 27 and the worst is 112**, so
    a fixed short window from the entry would truncate the retracement on half of them.
  - **A 3/3 MISS** spans the bar price first tagged the ZONE → the bar the setup died. 🔴 **NOT the
    bar the miss was recorded on** — see `chart_spec.reversal_anchors` for why that bar is a median
    $22 away from the setup and what it looked like on the chart.

Nothing is drawn past the turn: after it, price is moving the setup's way and a reversal candle
there is a different subject.

DIRECTION IS A PREFERENCE, NEVER A FILTER
-----------------------------------------
A bar carrying several patterns is NAMED after the one that best points the SETUP's way, in three
tiers: a pattern pointing the setup's way (bullish on a long, bearish on a short), then a NEUTRAL
one (hammer / inverted hammer / doji, which the source Pine draws with no trend filter and therefore
no direction — see `engines/candlesticks/CLAUDE.md`), then one pointing AGAINST it.

⚠ **Tier 3 is kept, and it is half the point of the layer** (Aaron, 2026-08-08): *"if I'm trying to
take a short with a bullish candle printed, and that's why price reversed, yeah, highlight that …
if it lines up with my trades, then great. If not, it will show me why I was wrong."* An opposing
candle in the span is drawn like any other — this ordering decides the NAME on a bar, never whether
the bar is painted.

⚠ **A bearish engulfing was once the sole mark on a long that WON**, because selection started at
nearest-the-extreme and whichever pattern sat closest won regardless of which way it pointed. That
class of error is gone by construction now: nothing is selected, so nothing is suppressed.

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

# How far past the anchor bar to search when an anchor states no END. Every anchor the chart builds
# today carries one (a trade's exit, a miss's death bar), so this is the floor for a caller that
# cannot supply one rather than a policy. 3 bars is 45 minutes on M15. Aaron's choice, 2026-08-08.
_WINDOW_BARS = 3

# How far PAST the turn a pattern may still complete and count as that turn's reversal.
#
# 🔴 **This is not a fudge factor and it must not be tuned — it is the length of the longest pattern
# the engine reads, minus the bar it starts on.** A pattern is reported on the bar it COMPLETES, and
# the engine's longest are three bars (Morning/Evening Star, Three White Soldiers), so the bar that
# MADE the extreme is usually the pattern's first bar rather than its last.
#
# ✅ **MEASURED on run `997c14cc53bc`, 194 anchors: 37.1% carry a pattern ON the turn bar and a
# further 40.2% complete 1-2 bars after it.** Ending the span at the turn therefore threw away the
# reversal candle on FOUR IN TEN setups — reported off the chart as *"it's not showing the deepest
# candle pattern that would have been the most perfect entry."*
_CONFIRM_BARS = 2

# Navy. ⚠ A true navy (#1e3a8a and darker) is close to INVISIBLE on this theme's near-black plot —
# checked against `bgBase` before picking — so this is the most navy-reading blue that still stands
# out against the up/down candles it sits between, which is what the layer is for.
_NAVY = "#2f5fe0"
_NAVY_EDGE = "#7ea2ff"

# Payload backstop. Each anchor is a SPAN now rather than one candle, so this is a real bound and
# not a formality — a truncation is LOGGED, never silent. See `fvg_overlays._MAX_BOXES`.
_MAX_MARKS = 20_000


def _anchor_bars(
    times: list[int], anchors: Iterable[tuple],
) -> list[tuple[int, int, str, Optional[int], str]]:
    """Anchor `(start_ms, direction, end_ms[, outcome])` → `(anchor index, bar index, direction, end
    bar, outcome)`, clipped to the loaded candles.

    An anchor with no outcome reads as `"win"` — the aligned preference, which is what every anchor
    wanted before outcomes existed, so an older caller keeps its behaviour rather than silently
    switching every trade it draws to the loser rule.

    🔴 **The anchor's ORIGINAL index rides along, and it must.** This drops anchors that fall off the
    loaded candles, so enumerating the RESULT renumbers every anchor after the first drop — and the
    chart uses that index to say which trade a mark belongs to. It would have mislabelled trades on
    any paged window, silently and plausibly.

    An anchor between two bars belongs to the bar it is INSIDE (the last bar at or before it), which
    is the bar whose close the engine had just processed when that trade/miss reached that point —
    the same rule `fvg_overlays._anchor_bars` follows.

    An end that lands before the start, or off the loaded candles, degrades to `None` rather than
    dropping the anchor: a trade whose exit is off the right edge of a paged window is still a real
    setup and still deserves the short-window answer at its entry.
    """
    out: list[tuple[int, int, str, Optional[int], str]] = []
    if not times:
        return out
    lo, hi = times[0], times[-1]
    for n, anchor in enumerate(anchors):
        t, direction, end_ms = anchor[0], anchor[1], anchor[2]
        outcome = str(anchor[3]) if len(anchor) > 3 else "win"
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
        out.append((
            n, i, "short" if str(direction).lower().startswith("s") else "long", end_bar, outcome,
        ))
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


def _deepest_bar(candles: list[dict], bars: list[int], direction: str) -> int:
    """Whichever of `bars` price ran FURTHEST AGAINST the setup on — the DEEPEST one.

    🔴 **"Deepest" is a price, and it was being read as a time.** The fallback below used to take
    the LAST pattern bar in the span (`pool[-1]`) whenever none reached the turn, which is *most
    recent*, not *deepest*. MEASURED on the reference run's 2026-06-16 short: the span holds three
    Bearish Engulfings and the last pattern bar is a Bearish Harami at 12:15 (high 4345.02), while
    the genuinely deepest aligned candle is the 11:00 Bearish Engulfing at **4349.27 — $4.25
    higher, i.e. a better short entry**. Aaron reported it as exactly that: *"the deepest best entry
    was on a bearish engulfing yet you did not highlight it."*

    ⚠ **Ties keep the EARLIER bar** (strict `>`), because the earlier one is the entry you could
    actually have taken.
    """
    best = bars[0]
    key = "high" if direction == "short" else "low"
    for i in bars:
        if (candles[i][key] > candles[best][key]) if direction == "short" else (candles[i][key] < candles[best][key]):
            best = i
    return best


def _wanted_direction(direction: str, outcome: str) -> int:
    """The pattern direction this anchor's NAMED candle should carry: +1 bullish, -1 bearish.

    **Aaron's rule, 2026-08-08, off two screenshots of winners named with the opposing candle** (a
    long reading `Won · Bearish Engulfing`, a short reading `Won · Bullish Harami`): *"if I won it
    should default to the BEST candle that helped or COULD HAVE HELPED signal the reversal… If I
    lost it should default to the candle that signaled why I lost. If I missed the trade it should
    default to the DEEPEST CORRECT candle that I could have used to enter."*

    So the question is always **which candle explains what happened to this setup**, and the answer
    flips on the outcome rather than on the side:

      - a WINNER or a MISS wants the candle ALIGNED with the setup — bullish on a long, bearish on
        a short. That is the reversal that turned price the setup's way, or would have.
      - a LOSER wants the OPPOSING one, because on a trade that failed the informative candle is
        the one that turned price against it.

    ⚠ **This orders the NAME and never decides what is PAINTED.** Every pattern candle in the span
    is still drawn in every direction — the opposing tier is half the point of the layer (*"if not,
    it will show me why I was wrong"*) — so this is a preference, exactly as the within-bar ordering
    below is, and the chart's own direction filter is the only thing that hides anything.

    ⚠ **An unknown outcome reads as a WIN.** Aligned is the answer for two of the three cases and is
    the one a reader expects by default; guessing "loser" would name a healthy trade after the
    candle that beat it.
    """
    aligned = -1 if direction == "short" else 1
    return -aligned if str(outcome).lower().startswith("los") else aligned


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


def _reversal_span(
    candles: list[dict],
    start: int,
    direction: str,
    window: int,
    hold_end: Optional[int],
) -> tuple[int, int]:
    """The inclusive bar range this anchor may paint in, and the TURN inside it.

    Returns `(lo, hi, turn)`: `lo` → `turn` is the retracement the setup was entered into, and `hi`
    is `turn + _CONFIRM_BARS` — the window a pattern that turned price is still allowed to COMPLETE
    in. See `_CONFIRM_BARS`; ending at the turn dropped the reversal candle on four setups in ten.

    Nothing beyond that: further past the turn price is moving the setup's way and a reversal candle
    there is a different subject. An anchor stating no `hold_end` falls back to `window` bars.
    """
    last = len(candles) - 1
    end = min(hold_end if hold_end is not None else start + window, last)
    turn = _adverse_extreme(candles, start, max(start, end), direction)
    return start, min(turn + _CONFIRM_BARS, last), turn


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
    `(start_ms, direction, end_ms)` triples — a trade's entry → exit, or a 3/3 miss's zone touch →
    death. Each becomes the span `start` → the turn inside it, and every pattern bar in that span is
    painted.

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

    # bar index → the patterns to name on it, the one matching the setup's direction FIRST. Spans
    # OVERLAP freely (two setups on one leg, a miss inside a trade's hold), and an overlapped bar is
    # ONE mark, not two stacked; the first anchor to reach it names it.
    marked: dict[int, list] = {}
    # bar index → the anchors whose span covers it, and whether it is the TURN of any of them.
    #
    # ⚠ These are collected for EVERY anchor a bar belongs to, not just the first — the dedupe above
    # decides which anchor NAMES the bar, and using that same anchor here would make a trade whose
    # only pattern bar was already claimed report as "no pattern at all", which is the one thing the
    # trade badge exists to say.
    spans: dict[int, list[int]] = {}
    at_turn: dict[int, list[int]] = {}
    # bar index → {anchor index: the pattern name to NAME that anchor with}. Keyed per anchor
    # because one bar can be the deepest of two anchors that want OPPOSITE directions (a losing
    # trade and a 3/3 miss on the same leg), and a single `label` cannot answer both — it is
    # whatever the first anchor to reach the bar ordered it as, which is nobody's answer in
    # particular. The chart reads this for a trade's chip and falls back to `label`.
    deepest_names: dict[int, dict[str, str]] = {}
    aligned: dict[int, str] = {}
    for n, start, direction, hold_end, outcome in bars:
        lo, hi, turn = _reversal_span(candles, start, direction, window, hold_end)
        # `want` is SETUP-relative and stays that way: it is what `align` is reported in, and the
        # chart's direction filter asks "with the setup / neutral / against it". `prefer` is
        # OUTCOME-relative and decides which candle gets named — the two are the same thing on a
        # winner and a miss, and opposites on a loser. See `_wanted_direction`.
        want = -1 if direction == "short" else 1
        prefer = _wanted_direction(direction, outcome)
        in_span = [i for i in range(lo, hi + 1) if hits.get(i)]
        for i in in_span:
            spans.setdefault(i, []).append(n)
            if i in marked:
                continue
            # Stable sort: the direction this anchor is asking about, then neutral, then the
            # opposite — so `label` names the pattern that answers the question rather than
            # whichever the engine happened to emit first. On a winner or a miss that is the
            # setup-aligned one; on a loser it is the candle that beat it.
            marked[i] = sorted(
                hits[i],
                key=lambda p: 0 if p.direction == prefer else (1 if p.direction == 0 else 2),
            )
            # ...and RECORD which of the three it was. ⚠ It cannot be derived from `patternDir`
            # downstream: that is the pattern's own direction, and whether a bullish candle points
            # the setup's way depends on the SETUP's side — which a mark does not carry, and cannot,
            # because one bar can sit inside a long's span and a short's at once. The anchor that
            # names the bar is the one that answers for it.
            top = marked[i][0].direction
            aligned[i] = "with" if top == want else ("neutral" if top == 0 else "against")
        # The DEEPEST mark of this span — the first pattern bar at or after the turn, because a
        # reversal pattern COMPLETES after the bar that made the extreme (see `_CONFIRM_BARS`).
        # ⚠ It falls back to the last mark BEFORE the turn rather than to nothing: a span that has
        # marks must have a deepest one, or "only the deepest" hides a setup that plainly had
        # candles in it and reads as the layer being broken.
        #
        # 🔴 **The bars carrying a pattern in the PREFERRED direction are searched first, and that
        # is the fix for the defect this was reported as**: ranking on nearness alone put a
        # `Bearish Engulfing` on a long that WON and a `Bullish Harami` on a short that won, because
        # whichever candle sat closest to the turn won whichever way it pointed. Aaron: *"I should
        # see BULLISH candle for long trades or BEARISH candle for short trades."*
        # ⚠ **It FALLS BACK to the whole span rather than to nothing.** A setup whose only candles
        # point the other way still has a deepest one, and drawing none there would report "no
        # reversal candle" for a setup that plainly had one — the same failure the fallback above
        # exists to prevent, and the layer's whole opposing tier says the reader wants to see it.
        # ⚠ THREE TIERS, the same preference the within-bar ordering uses one level down — preferred,
        # then NEUTRAL, then whatever is left. Two tiers is not enough and the gap is not academic:
        # MEASURED on the reference run, 59 of 194 spans contain no directional candle at all, so a
        # `preferred or anything` pool picks an OPPOSING bar over a neutral one whenever the opposing
        # one happens to sit nearer the turn. The neutral tier does most of the work here because ten
        # of the source Pine's fifteen rules gate on a trend lookback — see the engine's CLAUDE.md.
        tier_pref = [i for i in in_span if any(p.direction == prefer for p in hits[i])]
        tier_neut = [i for i in in_span if any(p.direction == 0 for p in hits[i])]
        pool = tier_pref or tier_neut or in_span
        if pool:
            # A pattern that COMPLETES at or after the turn IS the turn candle, so it wins outright
            # (see `_CONFIRM_BARS`). Only when nothing in the pool reaches the turn does "deepest"
            # become a question, and then it is a question about PRICE — see `_deepest_bar`.
            after = [i for i in pool if i >= turn]
            pick = after[0] if after else _deepest_bar(candles, pool, direction)
            at_turn.setdefault(pick, []).append(n)
            # Name THIS anchor after a pattern pointing the way IT asked about, not after whichever
            # the bar's `label` ordering happened to settle on for somebody else.
            #
            # 🔴 **An OPPOSING candle is never the name, and there is deliberately no third
            # fallback.** Aaron, off a winning short named `Bullish Harami`: *"Shouldn't it be a
            # neutral candle, no candle or best yet a bearish candle?"* — so the preference order
            # ends at neutral and the honest answer below it is silence. MEASURED: 9 of 166 anchors
            # on the reference run have nothing but opposing candles in their span, and every one of
            # them was being named after the candle that argues AGAINST the setup.
            # ⚠ **The bar is still `deepestOf` and still PAINTED** — dropping it would hide the
            # opposing candle behind "Only the deepest", and showing it is half the point of the
            # layer (*"it will show me why I was wrong"*). Only the NAME is withheld, and the chart
            # says `no matching candle` rather than `no candle`, because the two are different facts.
            chosen = next(
                (p for p in hits[pick] if p.direction == prefer),
                next((p for p in hits[pick] if p.direction == 0), None),
            )
            if chosen is not None:
                deepest_names.setdefault(pick, {})[str(n)] = chosen.label

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
            # +1 / -1 / 0 exactly as the source Pine DRAWS it. The chart uses it to say which way a
            # pattern points and to offer a direction filter; it never decides WHETHER the candle is
            # painted — that call is Aaron's, made in the menu.
            "patternDir": found[0].direction,
            "patterns": [p.label for p in found],
            # Which anchors' spans cover this bar (index into `anchors`). The chart reads it to
            # badge a trade; it is not derivable downstream, because a span is a bar RANGE and the
            # spec ships only the marks.
            "spans": spans.get(i, []),
            # Which anchors this bar is the DEEPEST mark of. A list, not a flag: one bar can be the
            # turn of one setup and an ordinary mark inside another's span, and a bare boolean would
            # let the chart name it as the second setup's reversal.
            "deepestOf": at_turn.get(i, []),
            # {anchor index (as a string key): the pattern to NAME that anchor with}. One bar can be
            # the deepest of two anchors wanting opposite directions, and the bar's single `label` is
            # whichever the first anchor to reach it ordered — nobody's answer in particular. The
            # chart reads this for a trade's outcome chip and falls back to `label`.
            "deepestNames": deepest_names.get(i, {}),
            # "with" / "neutral" / "against" — the named pattern's direction relative to the SETUP,
            # which is what the chart's direction filter is asked in. See above for why the chart
            # cannot work it out from `patternDir`.
            "align": aligned.get(i, "against"),
            "style": {"color": _NAVY_EDGE, "fillColor": _NAVY},
        })

    if len(overlays) > _MAX_MARKS:
        dropped = len(overlays) - _MAX_MARKS
        overlays = overlays[-_MAX_MARKS:]
        log.info("candle overlays: capped at %d marks — dropped the %d oldest", _MAX_MARKS, dropped)
    log.info("candle overlays: %d bars, %d anchor(s) -> %d marked candle(s) (trend=%s doji=%s)",
             len(candles), len(bars), len(overlays), cfg["trend"], cfg["doji_size"])
    return overlays
