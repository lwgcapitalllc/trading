"""
liquidity/ — the liquidity-levels engine subsystem.

Turns the bar stream into liquidity LEVEL EVENTS — the prices the market runs toward and grabs:
previous day/week highs and lows (PDH/PDL/PWH/PWL), the previous week's close (PWC), the previous-H4
high/low sweep targets (SSH/BSL), and each finished session's high/low (Asia/London/NY). Emits
create / mitigate (sweep-or-break) / evict events, not lines or boxes. (The MONTHLY level PMH/PML was
removed from the source and this engine on 2026-07-09.)

Ported from indicators/engines/mpc_jarvis.pine's liquidity blocks (DAILY/WEEKLY LEVELS, PWC, H4 LIQUIDITY
SWEEP TRACKER, SESSION H/L TRACKING). The session H/L is consumed from the canonical sessions engine
(engines/sessions/), which this engine composes and drives internally; the day/week/H4 levels are
reconstructed from the bar stream.

NON-REPAINTING (Aaron's explicit decision, 2026-07-05): every HTF level is built from a PREVIOUS,
fully-completed period — the engine never forecasts the current period's high/low, so a bot never
trades a level that peeked at the future. See engine.py and CLAUDE.md.

Public API:
    from liquidity import LiquidityEngine, LiquidityLevel, LiquidityEvents

    liq = LiquidityEngine()              # Pine defaults; composes its own sessions engine
    # each closed bar (timestamp is epoch MILLISECONDS, UTC — exactly Pine's `time`):
    ev = liq.update(bar.index, bar.timestamp_ms, bar.high, bar.low, bar.close)
    for lvl in ev.created:               # levels created this bar (edge)
        lvl.kind, lvl.side, lvl.name, lvl.price, lvl.id
    for lvl in ev.mitigated:             # levels price took this bar (edge)
        lvl.name, lvl.mitigated_index, lvl.sweep_label   # sweep_label: "BSL"/"SSL" for H4
    for lvl in ev.evicted:               # levels removed this bar — NOT a signal
        ...
    ev.active                            # every currently-live level (state)
"""

from .engine import LiquidityEngine
from .types import (
    BREAK_HIGH,
    BREAK_LOW,
    NONE,
    SWEEP_HIGH,
    SWEEP_LOW,
    LiquidityEvents,
    LiquidityLevel,
)

__all__ = [
    "LiquidityEngine",
    "LiquidityLevel",
    "LiquidityEvents",
    "SWEEP_HIGH",
    "SWEEP_LOW",
    "BREAK_HIGH",
    "BREAK_LOW",
    "NONE",
]
