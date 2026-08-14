"""Timeframe definitions and base-timeframe resolution.

The broker (PU Prime demo, via the MT5 agent) serves a fixed set of bar
timeframes directly. Any timeframe in that set is pulled as-is. Any other
timeframe (e.g. 45m, 2h) is built by pulling the largest served timeframe
that divides it and resampling UP — never down, so we never invent price
path inside a bar.
"""

from __future__ import annotations

import re

# Timeframes the MT5 agent serves directly (name → minutes). Ordered small→large.
# Matches mt5_agent._tf_const / _TF_PERIOD.
SERVED_TF: dict[str, int] = {
    "M1": 1,
    "M5": 5,
    "M15": 15,
    "M30": 30,
    "H1": 60,
    "H4": 240,
    "D1": 1440,
}

_MINUTES_TO_TF: dict[int, str] = {m: name for name, m in SERVED_TF.items()}

# Suffixes on a compact timeframe string, in minutes.
_UNIT_MINUTES = {"m": 1, "h": 60, "d": 1440}


def to_minutes(timeframe: str | int) -> int:
    """Parse a timeframe input to a whole number of minutes.

    Accepts an int (already minutes), an MT5 name ("M15", "H1", "D1"), or a
    compact string ("15m", "1h", "4h", "1d", or a bare "15"). Raises ValueError
    on anything unrecognized or non-positive.
    """
    if isinstance(timeframe, bool):  # bool is an int subclass — reject explicitly
        raise ValueError(f"invalid timeframe: {timeframe!r}")
    if isinstance(timeframe, int):
        minutes = timeframe
    else:
        tf = timeframe.strip()
        if not tf:
            raise ValueError("empty timeframe")
        upper = tf.upper()
        if upper in SERVED_TF:
            return SERVED_TF[upper]
        m = re.fullmatch(r"(\d+)\s*([mhdMHD]?)", tf)
        if not m:
            raise ValueError(f"unrecognized timeframe: {timeframe!r}")
        value = int(m.group(1))
        unit = m.group(2).lower()
        minutes = value * (_UNIT_MINUTES[unit] if unit else 1)
    if minutes <= 0:
        raise ValueError(f"timeframe must be positive minutes, got {minutes}")
    return minutes


def resolve_base_tf(target_minutes: int) -> tuple[str, int]:
    """Return (base_tf_name, base_minutes) to pull for a target timeframe.

    If the target is a served timeframe, it is its own base (no resample).
    Otherwise the base is the LARGEST served timeframe that evenly divides the
    target — so resampling up is exact. Raises ValueError if nothing divides it
    (e.g. a target smaller than M1, or one no served TF divides).
    """
    if target_minutes in _MINUTES_TO_TF:
        name = _MINUTES_TO_TF[target_minutes]
        return name, target_minutes

    best: tuple[str, int] | None = None
    for name, minutes in SERVED_TF.items():
        if minutes < target_minutes and target_minutes % minutes == 0:
            if best is None or minutes > best[1]:
                best = (name, minutes)
    if best is None:
        raise ValueError(
            f"no served timeframe divides {target_minutes}m — served: {sorted(SERVED_TF.values())}"
        )
    return best
