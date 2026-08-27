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
from typing import Optional

# strategies/python on path so `mpc_sos_fade` imports by bare name (the shim the tests use).
_PYPKGS = Path(__file__).resolve().parents[1]
if str(_PYPKGS) not in sys.path:
    sys.path.insert(0, str(_PYPKGS))

from mpc_sos_fade.config import SosFadeConfig  # noqa: E402


@dataclass(frozen=True)
class RealignConfig(SosFadeConfig):
    exec_min_atr_pct: float = 0.0   # pinned OFF, and INERT here — this fork overrides `_place_entries`
    """The parent's dead-market floor, pinned to the inert value.

    The parent turned it ON at 0.08 on 2026-08-26. It is enforced inside the parent's
    `_place_entries`, which this fork overrides, so it never runs on this path. Pinned so a
    parent default change cannot silently claim a filter this fork does not run.

    ⚠ It has never been swept here, and this fork has NO parity gate at all, so there is nothing
    that would catch it starting to bite. Do not read the pin as a measured choice for this setup.
    """

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

    🔴 **THE RANKING INVERTS WHEN COSTS ARE CHARGED, AND AN EARLIER NOTE HERE HAD IT
    FLATLY WRONG.** This docstring said `strict` was "the WORST of the three" and cited
    percentages that came from the TRIGGER SCAN — the one thing the note below
    `realign_long_source` says must never decide an exit-sensitive question. Measured by
    REPLAY instead, 467,352 M5 bars 2020-01-02 -> 2026-08-06:

        FREE                trades   total R    avg R    win     PF     maxDD
          any                 162    +45.14R   +0.279   44.4%   1.658   12.15R
          opposing             43    +11.36R   +0.264   48.8%   1.832    4.58R
          strict               42    +12.36R   +0.294   50.0%   1.977    4.15R

        CHARGED (puprime_standard)
          any                 162    +35.81R   +0.221   33.3%   1.496   15.52R
          opposing             43     +6.22R   +0.145   30.2%   1.425    5.51R
          strict               42     +7.33R   +0.175   31.0%   1.540    4.41R

    **Free, `strict` is the BEST of the three on avg R, profit factor AND drawdown.**
    Charged, it is not: costs take 40% of its average R (+0.294 -> +0.175) against `any`'s
    21% (+0.279 -> +0.221), and the order flips.

    ⚠ **The mechanism is NOT measured.** The obvious candidate is that the strict
    sequence's stops are tighter, so a fixed spread costs more R — plausible, cheap to
    check (median stop distance per pattern) and deliberately NOT asserted here.

    **`any` still ships**, on the two figures that survive charging: 5x the total R
    (+35.81R vs +7.33R) and more R per unit of drawdown (2.31 vs 1.66). But the sequence
    Aaron drew is a REAL rule with the best per-trade quality in the book, not a filter
    that "carries no information" — which is what the old note claimed and what would have
    stopped anyone looking at it again.
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

    realign_min_rr: Optional[float] = None
    """Refuse a setup whose reward-to-risk at ENTRY is below this. `None` = no filter.

    The stop is the counter-move extreme and the target is the pre-deviation external
    high. **Those two are set independently, so R:R varies enormously per trade and is
    KNOWN AT ENTRY** — which is what makes it a filter rather than a hindsight
    observation. Measured over the 162-trade book: min **-3.68**, median 1.69, max 14.92.

    🔴 **`None` IS NOT THE SAME AS 0.0, AND THE DIFFERENCE IS A PINE PARITY DEFECT.**
    `mpc_realign_strategy.pine` guards its entry with `tgtLong > close` (and the short
    mirror); **this Python has never had that check**, so it takes trades whose target is
    already BEHIND the entry — 7 of 162, R:R down to -3.68. Those trades are not junk:
    TP2 is satisfied on the entry bar, the ladder jumps to stage 2 and they run as pure
    trailing trades, making **+5.67R between them (+0.81R average, against the book's
    +0.221)**. So the Pine is refusing the better-performing tail of its own book.
    **Which side is right is NOT settled here** — `0.0` reproduces the Pine, `None`
    reproduces every Python figure measured before 2026-08-13, and the parity gate is what
    decides. Default stays `None` so no historical number moves.

    ⚠ Any positive value is a NEW filter that neither implementation has. Measure it by
    REPLAY, never by dropping rows from a finished trade list: with one position slot a
    refused setup FREES the slot and a different setup takes it, which is how the
    minimum-stop guard's cheap estimate got its SIGN wrong (+1.84R estimated, -1.84R
    replayed).
    """

    realign_trend_minutes: Optional[int] = None
    """Refuse a trade against the structure direction of THIS slower frame. `None` = off.

    🔴 **THE PROFITABLE DIRECTION FLIPS WITH GOLD'S OWN TREND, AND THAT IS THE ONE
    STRUCTURAL FINDING IN THIS STRATEGY'S DATA.** Split the 162-trade book in half:

        2020-01 -> 2023-04   shorts +17.18R (43 tr)   longs  -8.83R (39 tr)
        2023-05 -> 2026-08   shorts  +2.90R (42 tr)   longs +24.55R (38 tr)

    Gold over those halves: roughly flat-to-down through 2021 (-4.2%) and 2022 (-0.3%),
    then +12.9% / +27.1% / +64.5% through 2023-2025. **The side that makes money is the
    side aligned with the prevailing move, and it reverses when the move does.**

    The mechanism is the setup's own logic rather than a pattern in a table: a false break
    is a liquidity grab AGAINST a prevailing direction, and the realignment is the
    resumption. Taken against the dominant trend, the same shape is a genuine reversal
    being faded — which is a different trade with a different expectancy.

    ⚠ **THIS HYPOTHESIS WAS DERIVED FROM THE SAME 162 TRADES IT WOULD BE TESTED ON, AND
    THAT IS EXACTLY HOW A SECOND OVERFIT HAPPENS AFTER THE FIRST ONE IS CAUGHT.**
    `realign_min_rr` looked excellent on the full history and was then shown to be a fit to
    one half. Any value here must clear the same bar: it has to help in BOTH halves
    separately, not in the total. Default is `None` until it does.
    """

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
        if self.realign_trend_minutes is not None and self.realign_trend_minutes <= self.realign_htf_minutes:
            # A "trend" frame at or below the frame the false break is read on is not a
            # slower context, it is the same read under another name — and it would pass
            # silently while filtering on something the setup already knows.
            raise ValueError(
                f"realign_trend_minutes ({self.realign_trend_minutes}) must be SLOWER than "
                f"realign_htf_minutes ({self.realign_htf_minutes})")
        if self.realign_min_rr is not None and self.realign_min_rr < 0:
            # A negative floor is indistinguishable from `None` in effect but states
            # something false — that a minimum was chosen. Refuse rather than accept it.
            raise ValueError(
                f"realign_min_rr must be >= 0 or None, got {self.realign_min_rr!r}")
        if self.exec_secondary:
            # Refuse rather than silently produce a primary-only book — the distinction
            # this repo has been bitten by twice.
            raise ValueError(
                "mpc_realign has no 1m secondary re-entry; exec_secondary must stay False")
        if 60 % self.realign_htf_minutes and self.realign_htf_minutes % 60:
            raise ValueError("realign_htf_minutes must divide or be a multiple of an hour")
