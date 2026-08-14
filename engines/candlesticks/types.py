"""
candlesticks/types.py — plain data containers + the pattern REGISTRY for the candlestick engine.

No behaviour lives here except the registry lookups. Three things:

  PatternSpec ....... one row of the registry: the stable `key` a consumer names in config, the
                      `label` the Pine plots, the `direction` the Pine draws it with, and how many
                      bars of history the rule needs before it can be true at all.

  CandlePattern ..... one DETECTION: a spec plus the bar it fired on. This is the event a strategy
                      reads as a confluence point.

  CandlestickEvents . the engine's per-bar OUTPUT: every pattern that fired on THIS bar, in the
                      Pine's own declaration order, with helpers for filtering by key/direction.

⚠ DIRECTION IS THE PINE'S OWN RENDERING, NOT A TRADING OPINION.
`indicators/engines/candle_sticks.pine` draws six patterns as a green up-arrow BELOW the bar, six as a red
down-arrow ABOVE it, and three (Doji, Hammer, Inverted Hammer) as a neutral white cross/diamond. That
split is what `direction` carries: +1 / -1 / 0. **Hammer and Inverted Hammer are conventionally read
as bullish reversals and this source does NOT say so** — it emits them undirected, with no trend
filter on either (see `min_history` = 0), so a "hammer" here can print in the middle of a downtrend,
an uptrend or a range. A consumer that wants them bullish states that itself; the engine will not
decide it, because the moment it did, the engine and the chart would disagree about the same candle.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, Iterable, List, Optional, Tuple

BULLISH = 1
BEARISH = -1
NEUTRAL = 0


@dataclass(frozen=True)
class PatternSpec:
    """One row of the pattern registry — the definition, not a detection.

    `key`         stable snake_case id; this is what a strategy config names.
    `label`       the Pine `plotshape` title, verbatim, so a chart and a config can be lined up.
    `pine_var`    the Pine variable that computes it, so a reader can find the source line.
    `direction`   +1 / -1 / 0 exactly as the Pine DRAWS it (see the module docstring).
    `min_history` how many closed bars must already exist before the rule can be true. Pine
                  comparisons against `na` are false, so a rule reading `open[trend]` or `high[2]`
                  simply cannot fire before that history exists — this makes that explicit rather
                  than leaving it to a None-check somewhere.
    """

    key: str
    label: str
    pine_var: str
    direction: int
    min_history: int


# ── The registry. ORDER IS THE PINE'S DECLARATION ORDER and must stay that way: it is the order
#    `CandlestickEvents.detected` comes out in, so a consumer that takes "the first pattern on this
#    bar" gets the same one the chart lists first. `min_history` marked `trend` below is resolved
#    against the engine's `trend` input at construction. ──
_TREND = -1  # sentinel: "this rule needs `trend` bars of history" (resolved by the engine)

PATTERNS: Tuple[PatternSpec, ...] = (
    PatternSpec("doji", "Doji", "doji", NEUTRAL, 0),
    PatternSpec("bearish_harami", "Bearish Harami", "bearHarami", BEARISH, _TREND),
    PatternSpec("bullish_harami", "Bullish Harami", "bullHarami", BULLISH, _TREND),
    PatternSpec("bearish_engulfing", "Bearish Engulfing", "bearEng", BEARISH, _TREND),
    PatternSpec("bullish_engulfing", "Bullish Engulfing", "bullEng", BULLISH, _TREND),
    PatternSpec("piercing_line", "Piercing Line", "piercing", BULLISH, _TREND),
    PatternSpec("bullish_belt", "Bullish Belt", "bullBelt", BULLISH, _TREND),
    PatternSpec("bullish_kicker", "Bullish Kicker", "bullKick", BULLISH, _TREND),
    PatternSpec("bearish_kicker", "Bearish Kicker", "bearKick", BEARISH, _TREND),
    PatternSpec("hanging_man", "Hanging Man", "hangingMan", BEARISH, _TREND),
    PatternSpec("evening_star", "Evening Star", "eveningStar", BEARISH, 2),
    PatternSpec("morning_star", "Morning Star", "morningStar", BULLISH, 2),
    PatternSpec("shooting_star", "Shooting Star", "shootingStar", BEARISH, 1),
    PatternSpec("hammer", "Hammer", "hammer", NEUTRAL, 0),
    PatternSpec("inverted_hammer", "Inverted Hammer", "invHammer", NEUTRAL, 0),
)

PATTERN_KEYS: Tuple[str, ...] = tuple(p.key for p in PATTERNS)
_BY_KEY: Dict[str, PatternSpec] = {p.key: p for p in PATTERNS}


def spec_for(key: str) -> PatternSpec:
    """Look a pattern up by key, RAISING on an unknown one.

    Deliberately not a `.get()` returning None: a strategy config naming a pattern that does not
    exist is a typo that would otherwise switch a confluence silently off, which reads exactly like
    a filter that is on and never matching.
    """
    try:
        return _BY_KEY[key]
    except KeyError:
        raise KeyError(
            f"unknown candlestick pattern {key!r}. Known keys: {', '.join(PATTERN_KEYS)}"
        ) from None


def resolve_keys(keys: Optional[Iterable[str]]) -> Tuple[str, ...]:
    """Validate a caller's key selection, preserving the REGISTRY's order (never the caller's).

    None means every pattern. Ordering is fixed to the registry so two configs listing the same
    patterns in a different order cannot produce differently-ordered events.
    """
    if keys is None:
        return PATTERN_KEYS
    wanted = {k: None for k in keys}  # dedupe, keep it cheap
    for k in wanted:
        spec_for(k)  # raises on a typo
    return tuple(k for k in PATTERN_KEYS if k in wanted)


# ──────────────────────────────────────────────────────────────────────────────────────
# The traded preset
# ──────────────────────────────────────────────────────────────────────────────────────
# 🔴 THE ENGINE'S OWN DEFAULTS STAY AT THE PINE'S DEFAULTS (trend=5, doji_size=0.05) AND
# MUST NOT BE MOVED TO THESE. That is this repo's standing shape: an engine MIRRORS its
# source Pine, and a CONSUMER pins what it trades — `mpc_sos_fade` pins four FVG engine
# settings explicitly, and the one it forgot to pin was silently inheriting a shared
# default by coincidence until somebody changed it. Moving the defaults here would make
# this engine stop describing `candle_sticks.pine`, and the next reader comparing the two
# would find a fork with nothing recording it.
#
# So the traded configuration lives HERE, named, in one place, and is passed in:
#
#     from candlesticks import CandlestickEngine, CHART_PRESET
#     cs = CandlestickEngine(**CHART_PRESET)
#
# ⚠ VALIDATED at exactly these values: compare_candles.py exit 0 on a 20,138-bar
# VANTAGE_XAUUSD 15m export whose own cfg_ columns read trend=117, doji_size=0.01.
CHART_PRESET = {
    # Aaron's brother's chart settings, taken off the export's own cfg_* columns
    # (2026-08-08) rather than transcribed by hand.
    "trend": 117,
    "doji_size": 0.01,
    # The eleven patterns he reads. The four omitted (piercing_line, bullish_belt, both
    # kickers) are the rarest in the set — bullish_belt fires 19 times in 8 years.
    "patterns": (
        "doji",
        "bearish_harami",
        "bullish_harami",
        "bearish_engulfing",
        "bullish_engulfing",
        "hanging_man",
        "evening_star",
        "morning_star",
        "shooting_star",
        "hammer",
        "inverted_hammer",
    ),
}


@dataclass(frozen=True)
class CandlePattern:
    """One detection — a pattern that fired on one bar.

    `spec` is the registry row (so `p.spec.direction`, `p.spec.label` are always available) and the
    three convenience properties below exist so a consumer never has to reach through it.
    """

    spec: PatternSpec
    bar_index: int

    @property
    def key(self) -> str:
        return self.spec.key

    @property
    def label(self) -> str:
        return self.spec.label

    @property
    def direction(self) -> int:
        return self.spec.direction

    def __repr__(self) -> str:  # pragma: no cover - diagnostics only
        arrow = {BULLISH: "+", BEARISH: "-", NEUTRAL: "0"}[self.spec.direction]
        return f"<CandlePattern {self.spec.key}{arrow} @ {self.bar_index}>"


@dataclass
class CandlestickEvents:
    """The engine's per-bar output: every pattern that fired on THIS bar.

    `detected` is in the Pine's declaration order. There is no "active" list and there must not be
    one — a candlestick pattern is a property of a bar, not a level with a lifecycle, so it has no
    mitigation and nothing to expire. A consumer wanting "a hammer within the last 3 bars" asks the
    ENGINE (`bars_since`), because that is a question about history, not about this bar.
    """

    bar_index: int = 0
    detected: List[CandlePattern] = field(default_factory=list)

    # ── read helpers ──
    @property
    def keys(self) -> Tuple[str, ...]:
        return tuple(p.key for p in self.detected)

    def has(self, key: str) -> bool:
        """Did `key` fire on this bar? Raises on an unknown key (see `spec_for`)."""
        spec_for(key)
        return any(p.key == key for p in self.detected)

    def matching(
        self, keys: Optional[Iterable[str]] = None, direction: Optional[int] = None
    ) -> List[CandlePattern]:
        """This bar's detections filtered by key set and/or direction (+1 / -1 / 0).

        This is the confluence read: `ev.matching(keys=cfg.patterns, direction=+1)` answers "did any
        of the patterns I care about fire bullish on this bar".
        """
        allowed = None if keys is None else set(resolve_keys(keys))
        out = []
        for p in self.detected:
            if allowed is not None and p.key not in allowed:
                continue
            if direction is not None and p.direction != direction:
                continue
            out.append(p)
        return out

    @property
    def bullish(self) -> List[CandlePattern]:
        return [p for p in self.detected if p.direction == BULLISH]

    @property
    def bearish(self) -> List[CandlePattern]:
        return [p for p in self.detected if p.direction == BEARISH]

    @property
    def neutral(self) -> List[CandlePattern]:
        return [p for p in self.detected if p.direction == NEUTRAL]
