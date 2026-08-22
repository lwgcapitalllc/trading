"""The lab's view of this rule — a FLAT config the strategy scanner can render, and the one
place that turns it into the leg's real config.

Why a second config exists at all, stated plainly because two configs for one thing is normally a
smell. `RecoveryLegConfig` is what the LEG needs: the rule plus the instrument's contract size,
the account's full-size risk, the structure length and the frame's bar rate. **Four of those five
are not the user's to choose** — they are facts about the leg this rule is attached to and the
bars it is being replayed on. The scanner builds its form from `dataclasses.fields`, so handing it
`RecoveryLegConfig` would put a nested rule object and four derived numbers on the page.

So: this module owns the flat, user-facing half, and `leg_config()` is the ONE place that joins it
to the parent's facts. Nothing else may assemble a `RecoveryLegConfig` from lab input.

🔴 **This rule cannot run standalone and `LAB_STRATEGY` says so** (`requires_source`). It has no
setups — it arms off another leg's closed losses — so a run without a parent is not a quiet empty
book, it is a question that cannot be asked. The lab filters it out of every picker on that flag
and only the stack builder's tick box can create one.
"""

from __future__ import annotations

from dataclasses import dataclass

from .config import RecoveryConfig

__all__ = ["RecoveryLabConfig", "STOP_MODES", "leg_config"]

# The stop models a SHARED-ACCOUNT leg may use. `swing`, `signal_bar` and `atr` are absent
# because each needs an ATR and a stack has no canonical source for one — `RecoveryLeg.__init__`
# refuses them, and offering them on a form that cannot run them is worse than not offering them.
STOP_MODES = ("structural", "loss_entry", "leg_frac")


@dataclass(frozen=True)
class RecoveryLabConfig:
    """The rule's user-settable half. Defaults ARE the measured configuration — selecting the
    leg and touching nothing reproduces the runs recorded in this package's CLAUDE.md."""

    rec_risk_frac: float = 0.25
    rec_both_dirs: bool = True
    rec_stop_mode: str = "structural"
    rec_stop_leg_frac: float = 0.5
    rec_lock_at_r: float = 1.0
    rec_lock_to_r: float = 1.0
    rec_soft_stop_r: float = 0.0
    rec_scratch_r: float = 0.15
    rec_max_days: float = 30.0
    rec_invalidate_on_choch: bool = False
    rec_trail_swings: bool = True

    def __post_init__(self) -> None:
        if self.rec_stop_mode not in STOP_MODES:
            raise ValueError(
                f"rec_stop_mode={self.rec_stop_mode!r} is not one of {STOP_MODES}. The three "
                f"ATR-based models this rule also has cannot run as a shared-account leg — a "
                f"stack has no canonical ATR and a private copy would be a second implementation "
                f"of an indicator this repo keeps exactly one of. Use "
                f"backtest/tools/recovery_report.py for those."
            )
        if self.rec_risk_frac <= 0:
            raise ValueError(
                f"rec_risk_frac={self.rec_risk_frac!r} must be positive. A zero-size recovery "
                f"still fills, closes and lands in the trade list at 0R — a trade that looks "
                f"taken and moved nothing. The way to stop taking them is to remove the leg."
            )
        if self.rec_max_days <= 0:
            raise ValueError(f"rec_max_days={self.rec_max_days!r} must be positive.")


def rule_config(lab: RecoveryLabConfig) -> RecoveryConfig:
    """Map the flat lab fields onto the engine's rule.

    ⚠ `soft_stop_r` is 0-means-off on the form and None-means-off in the engine, because a UI
    needs a number where the engine wants an absence. This is the one place that translates, and
    it mirrors `mpc_sos_fade/recovery.py` deliberately — the two adapters must agree or the same
    setting means two things.

    ⚠ `horizon_days` is a measurement bound and MUST stay above `max_days`, or the time stop never
    fires and the two limits silently become one number wearing two names.
    """
    return RecoveryConfig(
        enabled=True,
        scratch_r=lab.rec_scratch_r,
        both_directions=lab.rec_both_dirs,
        risk_fraction=lab.rec_risk_frac,
        stop_mode=lab.rec_stop_mode,
        stop_leg_frac=lab.rec_stop_leg_frac,
        lock_at_r=lab.rec_lock_at_r,
        lock_to_r=lab.rec_lock_to_r,
        soft_stop_r=(lab.rec_soft_stop_r or None),
        invalidate_on_choch=lab.rec_invalidate_on_choch,
        trail_swings=lab.rec_trail_swings,
        max_days=lab.rec_max_days,
        horizon_days=max(90.0, lab.rec_max_days * 3.0),
    )


def leg_config(lab: RecoveryLabConfig, parent_config, *, bars_per_day: float, major_length: int):
    """Join the user's half to the PARENT leg's facts. The only sanctioned way to build one.

    🔴 `unit_risk_pct` is the parent's FULL-SIZE risk, and the recovery takes `rec_risk_frac` of
    it. It is read off the parent rather than typed because the two must move together: raise the
    parent's risk and a quarter-size recovery is still a quarter, which is what every measured
    figure in this package assumes.

    🔴 `major_length` must be the structure length the PARENT read. A recovery armed off a
    different structure stream is a different rule that happens to share a trigger.
    """
    from .leg import RecoveryLegConfig

    return RecoveryLegConfig(
        rule=rule_config(lab),
        point_value=parent_config.point_value,
        unit_risk_pct=parent_config.exec_risk_pct,
        major_length=major_length,
        bars_per_day=bars_per_day,
    )
