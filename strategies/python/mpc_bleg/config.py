"""BLegConfig — the B-LEG bot's config.

It is a strict SUPERSET of `mpc_sos_fade`'s `SosFadeConfig`: the B-LEG runs the SAME
engine stack + A+ SEQUENCE tracker (it arms off the A+ death), and it keeps the "A+ has
priority" gate — so every A+ input still matters (the priority gate reads the A+ arm
sources, edges, veto, HTF filters). Inheriting keeps the two in lockstep: a new A+ toggle
lands here for free. The only NEW field is `bleg_max_days` — how long a frozen B-LEG band
watches for the late retrace before it goes stale (Pine input "B-Leg: days to activate").

The exit ladder / sizing / cost fields (`exec_risk_pct`, `exec_tp1_pct`, `exec_be_buf_tk`,
`exec_trail_step`, `fill_model`, `account_profile`, …) are reused verbatim — the B-LEG
trades through the SAME execution machinery, only the ENTRY (band edge, custom SL/TP) and
the arm differ. See `bleg.py` / `execution.py`.
"""

from __future__ import annotations

import sys
from dataclasses import dataclass
from pathlib import Path

# strategies/python on path so `mpc_sos_fade` imports by bare name (same shim the tests use).
_PYPKGS = Path(__file__).resolve().parents[1]
if str(_PYPKGS) not in sys.path:
    sys.path.insert(0, str(_PYPKGS))

from mpc_sos_fade.config import SosFadeConfig  # noqa: E402


@dataclass(frozen=True)
class BLegConfig(SosFadeConfig):
    # ── Inherited toggle, re-defaulted to this fork's Pine value ───────────────────
    exec_bleg: bool = True        # "Trade B-Leg setups" — THIS fork's core setup, so ON here
    #   `mpc_b_leg_strategy.pine` ships execBLeg = true (the A+ file ships it false). Turn OFF
    #   only to prove the bot trades nothing without it. `exec_aplus` is inherited and still
    #   matters: A+ never PLACES an order here, but it holds the priority gate — set it False
    #   to drop that gate and read the B leg completely on its own.

    # ── B-LEG-only inputs (Pine group "Strategy Execution") ────────────────────────
    bleg_max_days: float = 2.5    # days a frozen band watches before it goes stale (1-3)
    #   Converted to a BAR count (day ÷ chart timeframe) so weekends and the daily close
    #   don't burn the clock. 2.5 days = 240 bars on 15m. See bleg.py.
    #
    #   **Raised 1.25 → 2.5 on 2026-07-27** — the ONLY adopted result from the first B-LEG
    #   parameter sweep (15 cells, 4.5y XAUUSD M15, `fill_model="bar"`). This is the setup's
    #   binding constraint: the band goes stale before the late retrace arrives, so widening
    #   the window is what produces trades. Measured, same stop, everything else unchanged:
    #       1.0d  25 trades   4.7R   maxDD -4.1   wr 52%
    #       1.25d 35 trades   6.5R   maxDD -6.7   wr 51%   <- the old default
    #       1.75d 44 trades   1.5R   maxDD -8.7   wr 43%   <- see the caveat below
    #       2.5d  55 trades  10.2R   maxDD -5.8   wr 47%   <- ADOPTED: more trades, more R,
    #       3.0d  58 trades   8.9R   maxDD -5.4   wr 47%      SMALLER drawdown, 4 positive years
    #
    #   ⚠ TWO CAVEATS, both load-bearing. (1) The surface is NOT monotonic — 1.75 dips to 1.5R
    #   between two much better neighbours, so a real chunk of the 2.5 result is which trades
    #   happened to land where. Treat it as "probably better than 1.25", not as an optimum, and
    #   do not sweep this finer without more data. (2) **Strip the top 5 trades and EVERY cell in
    #   the grid goes negative** (2.5d: 10.2R → −1.6R). B-LEG's whole result rests on a handful of
    #   winners; it has no broad edge yet. Full grid + the stop-level rows: see the B-LEG section
    #   of this package's CLAUDE.md.

    bleg_sl_level: str = "0.0"    # "B-Leg: SL fib level"  ∈ {0.382, 0.236, 0.0}
    #   Was HARDCODED to the leg origin before 2026-07-27. Declared here (not reused from the
    #   inherited `exec_sl_level`) because the two measure DIFFERENT geometry: `exec_sl_level`
    #   indexes the A+ fib engine's precomputed levels (`sig.fibo_p3..p10`), while the B LEG
    #   has no fib engine behind it — only the frozen band's own origin/range.
    #
    #   ⚠ THE B-LEG ZONE'S FIB IS DRAWN THE OPPOSITE WAY ROUND. Read this before adding a level.
    #   `bleg.py` builds the band as `origin + f·range`, so the zone's fib has **0 at the leg
    #   origin and 1.0 at the expansion extreme** — the mirror of a standard retracement, which
    #   puts 0 at the extreme. Aaron's brother (the setup's author) draws and reasons about it
    #   this way, and THIS FIELD USES HIS FRAME. Concretely:
    #       entry band  = 0.5 (the resting limit) down to 0.382 (the band's far edge)
    #       below it    = 0.236, then 0.0 = the leg origin
    #   so the only real fib levels available to a stop are 0.382 / 0.236 / 0.0. The levels
    #   ABOVE 0.5 — 0.618, 0.786, 0.886 — sit on the WRONG SIDE of the entry here (above it on
    #   a long) and are deliberately not offered. An earlier version of this field mirrored the
    #   standard ladder instead, which priced stops at 0.298 / 0.214 / 0.114 — arithmetically
    #   valid points, but NOT fib levels in this frame, and named for levels on the wrong side.
    #
    #       0.0   -> the leg origin   (DEFAULT = the old hardcoded stop, dist = 0.500·range)
    #       0.236 -> dist = 0.264·range
    #       0.382 -> the band's own far edge (`l_bot`/`s_top`), dist = 0.118·range
    #   To sit BEYOND the origin use `exec_sl_buf_tk`, which pushes the chosen level further out
    #   in ticks. `BLegExecution._sl_price` reads these fractions directly — no conversion.
    #
    #   ⚠ THE STOP IS COUPLED TO TP1. Entry is at 0.5 and TP1 is `2·edge − origin`, so the stop
    #   is `(0.5 − f)·range` while TP1 is ALWAYS `0.5·range`. TP1 measured in R is `0.5/(0.5−f)`:
    #   **1.00R** at 0.0, 1.89R at 0.236, **4.24R** at 0.382. A TP1 touch is the ONLY thing that
    #   stages the stop to breakeven, so a tighter stop pushes protection FURTHER away in R, and
    #   at 0.382 the stop also sits inside the entry band itself. Check `stop_distance` before
    #   adopting one: see mpc_sos_fade_optimization.md Runs 4-5 on degenerate sub-$2 stops.
