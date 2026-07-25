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
    # ── B-LEG-only input (Pine bLegMaxDays, group "Strategy Execution") ─────────────
    bleg_max_days: float = 1.25   # days a frozen band watches before it goes stale (1-3)
    #   Converted to a BAR count (day ÷ chart timeframe) so weekends and the daily close
    #   don't burn the clock. Default 1.25 = the original 120 bars on 15m. See bleg.py.
