"""ExtremeLegConfig — every input on `mpc_extreme_leg_strategy.pine`, as a dataclass.

⚠ **NOTHING MAY EXIST HERE WITHOUT A PINE INPUT BEHIND IT.** A field with no input is a setting
the parity gate can never check, because no `cfg_*` column can carry it — the harness would
configure this side from the export and leave that one field at whatever this file happens to say.
The house learned this on `BosConfig` (2026-08-07) and it is the reason the field order below
follows the Pine's own numbered sections rather than any tidier grouping: the two files are read
side by side when one of them changes.

The last block is the exception and is marked as such — those are platform facts (what a lot is
worth, which instrument) that TradingView expresses through the Strategy Properties tab rather than
through an input, so they cannot come from a `cfg_*` column and must not be expected to. Anything
the Pine merely HARDCODES is not in that category and does not belong here at all; see the block
at the bottom for the three that had to be taken back out.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass
class ExtremeLegConfig:
    # ── 3 · What trades ──────────────────────────────────────────────────────
    exec_longs: bool = True
    exec_shorts: bool = True
    # "Risk % of equity" | "Fixed contracts" — the Pine's `sizeMode`, spelled the same way so the
    # lab's dropdown and the chart's read identically.
    size_mode: str = "Risk % of equity"
    # ⚠ 1.0 because that is the PINE's default, not because it is the number to trade. Aaron runs
    # this at 5 and the whole optimisation was ranked in R, which is size-independent — but a
    # default here that disagreed with the chart would make every parity run configure one side
    # differently from the other.
    exec_risk_pct: float = 1.0
    fixed_qty: float = 1.0

    # ── 4 · What arms it ─────────────────────────────────────────────────────
    swept_minutes: int = 180
    req_counter_trend: bool = True
    use_h4_level: bool = True
    use_session_level: bool = True
    use_daily_level: bool = True
    use_weekly_level: bool = True
    min_families: int = 1
    skip_friday: bool = True

    # ── 6 · Stop & targets ───────────────────────────────────────────────────
    extreme_minutes: int = 120
    stop_buffer_atr: float = 0.20
    tp_frac: float = 0.5
    use_breakeven: bool = False
    be_arm_frac: float = 0.7

    # ── 7 · Filters ──────────────────────────────────────────────────────────
    min_r: float = 2.0
    min_stop_usd: float = 0.0

    # ── Platform facts — NOT Pine inputs, and no `cfg_*` column carries them ──
    # These are the Strategy Properties tab and the account behind it. The parity harness leaves
    # every one of them alone; a run that changed one would be comparing two different accounts.
    point_value: float = 1.0
    symbol: str = "XAUUSD"

    # 🔴 THREE CONSTANTS WERE HERE UNTIL THE LAB WAS ACTUALLY ASKED WHAT IT WOULD RENDER, AND THAT
    # IS THE ONLY REASON THEY ARE NOT STILL HERE. `majorLength`, the 15-minute aggregation and
    # `ta.atr(50)` are HARDCODED in the Pine — no input, so no `cfg_*` column and nothing a parity
    # gate could ever check. As config fields they picked up a row on the strategy page each, under
    # their raw field names, and a run that moved one would have diverged from the chart with
    # nothing anywhere to say so. They are now keyword arguments on `MpcExtremeLegStrategy`, which
    # a test can pass and the lab cannot. ⚠ This is the file's own opening rule catching the file:
    # a field with no Pine input behind it is a control the gate is blind to, and the way to find
    # out was to run the scanner rather than to read the registration and agree with it.

    def __post_init__(self) -> None:
        if self.size_mode not in ("Risk % of equity", "Fixed contracts"):
            raise ValueError(
                f"size_mode must be 'Risk % of equity' or 'Fixed contracts', "
                f"got {self.size_mode!r} — spelled exactly as the Pine dropdown spells it"
            )
        # Refuse rather than clamp. A minimum-families setting above the number of families
        # actually switched on can never be satisfied, so the strategy would run, take nothing,
        # and look like a market with no setups in it — the failure shape this repo calls a
        # feature nobody has RUN.
        enabled = sum(
            (self.use_h4_level, self.use_session_level, self.use_daily_level, self.use_weekly_level)
        )
        if self.min_families > enabled:
            raise ValueError(
                f"'Levels that must agree' is {self.min_families} but only {enabled} level "
                f"families are switched on, so nothing can ever arm. Turn a family on or lower "
                f"the requirement — this refuses instead of running silently empty."
            )
