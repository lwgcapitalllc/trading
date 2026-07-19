"""
equal_highs_lows — canonical Equal Highs/Lows (EQH/EQL) engine.

Turns the bar stream into EQH/EQL LEVEL EVENTS: when two consecutive same-side strict price pivots
land within an ATR(50)×mult band of each other, a horizontal liquidity level prints (EQH = buy-side
liquidity resting above; EQL = sell-side below) and lives until price CLOSES through it. Standalone
and price-driven — no upstream engine, no volume, no timestamp; a sibling of `fair_value_gaps` and
`rsi_divergence`. Events, not visuals: the dotted line/label the indicator draws is out of scope.

Ported line-by-line from indicators/mpc_assistant.pine's "EQUAL HIGHS / LOWS" block. This is the one
canonical implementation — no consumer builds its own.

    from equal_highs_lows import EqualHighsLowsEngine

    eq = EqualHighsLowsEngine()   # pivot_len=2, atr_mult=0.1, max_levels=6 — the mpc defaults

    # Each closed bar, in order:
    ev = eq.update(bar.index, bar.high, bar.low, bar.close)
    for lvl in ev.formed:        # levels that printed THIS bar (event)
        lvl.is_high, lvl.price, lvl.left_bar, lvl.formed_bar, lvl.id
    for lvl in ev.mitigated:     # levels taken (closed through) THIS bar
        ...
    ev.active_eqh, ev.active_eql  # live level prices, oldest→newest (state)
    ev.tolerance                  # eqTol this bar (diagnostic)
    ev.pivot_high, ev.pivot_low   # strict price pivots confirmed this bar (diagnostic)
"""

from .engine import EqualHighsLowsEngine
from .types import EqLevel, EqEvents

__all__ = ["EqualHighsLowsEngine", "EqLevel", "EqEvents"]
