"""Deterministic synthetic bars for the replay tests — a multi-day 15-minute
XAUUSD-like series with clear impulse legs (so structure/fib/FVG fire) spanning
several UTC days and sessions (so sessions/liquidity fire). No randomness that
depends on platform: a fixed LCG, seeded, reproducible everywhere. Offline only."""

from __future__ import annotations

import pandas as pd


def synth_bars(n_days: int = 10, start: str = "2025-01-06") -> pd.DataFrame:
    """Build ~ n_days of 15-minute bars as a canonical frame (DatetimeIndex
    'time' UTC-naive + float OHLC). Price walks with a seeded LCG and periodic
    sharp 3-bar impulses that leave fair-value gaps."""
    bars_per_day = 96
    n = n_days * bars_per_day
    times = pd.date_range(start=start, periods=n, freq="15min")

    price = 2000.0
    seed = 12345
    rows = []
    for i in range(n):
        seed = (1103515245 * seed + 12345) & 0x7FFFFFFF
        drift = ((seed >> 8) % 1000) / 1000.0 - 0.5  # -0.5..0.5

        # Every 24 bars, fire a clean 3-bar bullish or bearish impulse that leaves
        # a displacement gap the FVG engine will catch.
        phase = i % 24
        if phase in (0, 1, 2):
            step = 6.0 if (i // 24) % 2 == 0 else -6.0
        else:
            step = drift * 1.5

        o = price
        c = price + step
        hi = max(o, c) + abs(drift) * 0.8
        lo = min(o, c) - abs(drift) * 0.8
        rows.append((o, hi, lo, c))
        price = c

    df = pd.DataFrame(rows, columns=["open", "high", "low", "close"], index=times)
    df.index.name = "time"
    return df
