"""RealignConfig — the MPC REALIGN bot's config.

A strict SUPERSET of `mpc_sos_fade`'s `SosFadeConfig`, for the same reason `BLegConfig` is:
this fork trades through the SAME exit ladder, sizing and cost machinery, and only the
ENTRY differs. Inheriting keeps the exit levers in lockstep.

🔴 **THE INHERITED DEFAULTS ARE THE RISK, NOT THE NEW FIELDS.** Every A+ default this class
does not re-declare arrives uninvited — the `BosConfig` incident (2026-08-07), where two
A+ defaults added in the preceding five days silently broke a new fork. The pins below are
the result of diffing this fork against the parent field by field, and each one records WHY.

⚠ The entry-side A+ fields (`exec_fib_nearest`, `exec_deep_fib`, `exec_fvg_pre_zone`,
`exec_fib_overlap`, `exec_fib_deep_edge`, `exec_sl_deep`) are INERT here and are
deliberately left alone rather than pinned: this fork places no fib-priced order, so
nothing reads them. Pinning them would imply they mean something here.

See `docs/MPC_REALIGN_SPEC.md` for the setup and every measurement behind these defaults.
"""

from __future__ import annotations

import sys
from dataclasses import dataclass
from pathlib import Path

# strategies/python on path so `mpc_sos_fade` imports by bare name (the shim the tests use).
_PYPKGS = Path(__file__).resolve().parents[1]
if str(_PYPKGS) not in sys.path:
    sys.path.insert(0, str(_PYPKGS))

from mpc_sos_fade.config import SosFadeConfig  # noqa: E402


@dataclass(frozen=True)
class RealignConfig(SosFadeConfig):
    # ── the setup ────────────────────────────────────────────────────────────────
    realign_htf_minutes: int = 15
    """The EXTERNAL frame, aggregated from the chart frame inside the strategy.

    The strategy runs on the 5m stream and builds its own 15m bars, which is what keeps it
    SINGLE-frame from the runner's point of view. A genuinely dual-frame strategy needs
    `run_dual`, and `backtest.optimizer.run_sweep` refuses those outright — it would be
    locked out of the optimizer, the sweeps and the stress test.
    """

    realign_window_hrs: float = 24.0
    """How long a setup stays armed after the external false break. Chosen, not measured."""

    realign_pattern: str = "any"
    """Which internal sequence counts as the realignment.

    "any"      — a counter-direction internal break, then a with-trend internal SOS
    "opposing" — the two opposing internal SOS specifically
    "strict"   — with-trend iBOS, then counter iSOS, then with-trend iSOS

    ⚠ MEASURED: `strict` is the WORST of the three. It cuts the book 183 -> 121 and moves
    BOTH directions the wrong way (long −2.3% -> −5.7%, short +6.1% -> +4.4%). The extra
    specificity carries no information. Default is the loosest rule for that reason.
    """

    realign_long_source: str = "swing"
    realign_short_source: str = "swing"
    """WHICH STRUCTURE STREAM EACH SIDE TRIGGERS ON — and they genuinely differ.

    🔴 **BOTH SIDES WANT "swing", AND THE TRIGGER SCAN SAID OTHERWISE.** Measured by real
    replay through the full exit ladder, 2020-01-02 -> 2026-08-06, shorts alone:

      SHORT on "swing"     87 trades   +20.22R   avg +0.232R   maxDD  6.39R
      SHORT on "internal"  60 trades   -13.26R   avg -0.221R   maxDD 14.61R

    ⚠ The standalone TRIGGER scan (`backtest/tools/internal_realign_scan.py`) reported the
    OPPOSITE for shorts — "internal" at +9.6% over control (+2.1σ) against a 4R target.
    That scan scores every setup independently at a FIXED target, with no exit ladder, no
    staged stop and no position slot. Its short edge was entirely in the tail (+0.1σ at 1R,
    +2.1σ at 4R), and the real ladder banks at the structural target, so the edge it
    measured is one this strategy never collects. **A trigger prior is not a strategy
    result, and here the two disagree in SIGN.** Keep the scan for counting setups; take
    the direction of any exit-sensitive question from a replay.

    ⚠ "swing" is the frame's EXTERNAL stream, which is the internal structure OF THE 15m.
    It is not the engine's `InternalEvents`, which is the sub-structure of the 5m itself,
    one level further down than a chart draws.
    """

    realign_longs: bool = True
    realign_shorts: bool = True

    realign_sl_buf_tk: int = 20
    """Ticks beyond the internal leg extreme the stop sits."""

    # ── inherited defaults this fork must REFUSE ─────────────────────────────────
    exec_secondary: bool = False
    """PINNED OFF — the 1-minute re-entry needs a second bar stream through `run_dual`.

    The parent defaults this **True** (2026-08-07). Inherited, every replay of this fork
    would either refuse outright or — worse, on the paths that do not check — return a
    primary-only book while reporting itself as having re-entries. Same call `mpc_bleg`
    makes, for the same reason.
    """

    def __post_init__(self) -> None:  # type: ignore[override]
        parent = getattr(super(), "__post_init__", None)
        if parent is not None:
            parent()
        if self.realign_pattern not in ("any", "opposing", "strict"):
            raise ValueError(f"realign_pattern must be any|opposing|strict, "
                             f"got {self.realign_pattern!r}")
        for name in ("realign_long_source", "realign_short_source"):
            val = getattr(self, name)
            if val not in ("swing", "internal"):
                raise ValueError(f"{name} must be swing|internal, got {val!r}")
        if self.realign_window_hrs <= 0:
            raise ValueError("realign_window_hrs must be > 0")
        if self.exec_secondary:
            # Refuse rather than silently produce a primary-only book — the distinction
            # this repo has been bitten by twice.
            raise ValueError(
                "mpc_realign has no 1m secondary re-entry; exec_secondary must stay False")
        if 60 % self.realign_htf_minutes and self.realign_htf_minutes % 60:
            raise ValueError("realign_htf_minutes must divide or be a multiple of an hour")
