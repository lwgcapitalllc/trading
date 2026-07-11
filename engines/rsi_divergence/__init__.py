"""
rsi_divergence/ — the RSI-divergence engine subsystem.

Turns the bar stream into RSI-DIVERGENCE EVENTS — a confirmed regular divergence at the extremes
(price lower-low while RSI higher-low from oversold = bullish; the overbought mirror = bearish) —
plus the live confluence flags (`bull_active` / `bear_active`) a consumer reads. Colours, dotted
lines and labels are out of scope; this is the trading-signal layer, not the drawing layer.

Ported line-by-line from indicators/mpc_assistant.pine's "RSI DIVERGENCE" block. Standalone — it
depends on no other engine (a sibling of fair_value_gaps in shape): it needs each bar's close (for
Wilder's RSI) plus the bar's high/low (the price anchor at the RSI pivot). Pivots confirm
`pivot_len` bars after the extreme, so a divergence prints a few bars late — non-repainting by design.

Public API:
    from rsi_divergence import RsiDivergenceEngine

    div = RsiDivergenceEngine()          # rsi_len=14, pivot_len=5, oversold=25, overbought=75,
                                         # valid_bars=100 — the Pine defaults
    # each closed bar, in order:
    ev = div.update(bar.index, bar.high, bar.low, bar.close)
    for d in ev.detected:                # divergences confirmed THIS bar (event)
        d.is_bullish, d.pivot_bar, d.pivot_price, d.pivot_rsi
    ev.bull_active                       # live bullish confluence (state)
    ev.bear_active                       # live bearish confluence (state)
    ev.rsi                               # current RSI value (diagnostic)
"""

from .engine import RsiDivergenceEngine
from .types import RsiDivergence, RsiDivEvents

__all__ = [
    "RsiDivergenceEngine",
    "RsiDivergence",
    "RsiDivEvents",
]
