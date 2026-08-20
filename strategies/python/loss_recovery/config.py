"""loss_recovery/config.py — every knob, with the measured default and the reason for it.

Defaults are the ones MEASURED on XAUUSD M15 2018-09-14 → 2026-08-14 over mpc_sos_fade's 62
losses, both sides charged at `puprime_ecn`. Where a default was chosen rather than swept, the
docstring says so.

⚠ `enabled` defaults to **False**. Nothing that imports this package changes behaviour until a
caller says so — the rule has never been traded and has no parity gate.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional


@dataclass(frozen=True)
class RecoveryConfig:
    enabled: bool = False
    """Off until a caller opts in. See CLAUDE.md → Status."""

    major_length: int = 15
    """Structure engine's swing length. 15 because that is what mpc_sos_fade runs, and the
    recovery trade must read the SAME structure the primary read — a recovery entry off a
    different structure stream is a different rule that happens to share a trigger."""

    scratch_r: float = 0.15
    """Below this (signed, so `r < -scratch_r`) a primary trade counts as a real loss rather
    than a scratch. Matches `SosFadeConfig.exec_scratch_r`; a scratch is not a loss to recover."""

    both_directions: bool = True
    """Take the counter-trade whichever way it points.

    MEASURED: counter-longs +18.9R over 37, counter-shorts -2.9R over 25 — and both directions
    together score 1.49x against the risk dial where longs alone score 1.48x, i.e. the shorts are
    free. 🔴 **Setting this False is not a tuning choice, it is a FITTED one**: `long only` was
    picked after seeing which direction won on this exact record, and it was the only fitted
    element in the rule. Leaving it True is what removes that."""

    risk_fraction: float = 0.25
    """Recovery risk as a fraction of a normal trade's risk.

    MEASURED by a 5% sweep: 0.25 is simultaneously the LARGEST size that does not raise max
    drawdown above what the primary already runs (48.3% against 48.8%) and the peak of the
    efficiency curve (1.53x against the risk dial). The curve is flat from 0.20 to 0.55, so this
    is not a knife edge — see CLAUDE.md."""

    lock_at_r: float = 1.0
    """Move the stop once the trade has travelled this many R in favour.

    1.0 is the whole idea rather than a swept parameter: +1R is the moment the original loss has
    been paid back. MEASURED, the alternatives are worse — arming at +2R nets +11.5R and arming
    at 0 (trail from the start) nets +2.4R, against +18.9R here."""

    lock_to_r: float = 1.0
    """Where the stop goes when it arms. 1.0 SECURES the recovery; 0.0 is plain breakeven.

    MEASURED and the difference is the single biggest one in the whole rule: locking to +1R nets
    +18.9R at a 70% win rate, moving to breakeven instead nets +9.5R at 54%. Breakeven protects
    you from losing; it does not bank the thing you entered for."""

    stop_mode: str = "structural"
    """Where the recovery's stop goes, which is also what defines its 1R.

      `structural`  the far end of the CHoCH break leg. Every measured number here used this.
      `loss_entry`  the LOSING trade's own entry price — Aaron's 2026-08-19 idea: the level the
                    primary was wrong about, and a much nearer one, so the same 25% of risk buys
                    a bigger position and +1R arrives sooner in price terms.

    ⚠ `loss_entry` needs a `LossEventWithEntry`. A loss event without `entry_price` is REFUSED,
    never silently given the structural stop — the two are ~4x apart, so the fallback would report
    a rule nobody ran.

    🔴 **A stop model is never ranked on R.** R = profit / stop, so a model that produces small
    stops inflates every R in the book without one extra dollar being made, and gold's round trip
    is ~$0.14 on `puprime_ecn`. Read the median stop in DOLLARS beside any result from this knob —
    `recovery_report.py --stops` prints it and the cost as a share of R.
    """

    trail_pct: float = 0.0
    """Ratchet the stop to a fixed percentage of PRICE behind the close, once locked. 0 = off,
    leaving `trail_swings` in charge.

    🔴 **A percent of price is not a percent of risk, and this repo has already shipped that bug.**
    `mpc_bleg` inherited `exec_trail_pct = 1.0` while a B leg's whole 1R is 0.13%-1.25% of price —
    one step was larger than the entire risk, so the ratchet was INERT and the runner handed back
    everything past +1R on 9 of 50 trades. Compare the step against the trade's own R before
    believing a number from this."""

    soft_stop_r: Optional[float] = None
    """Cut the trade this many R against, instead of waiting for the structural stop.

    🔴 **This is the only knob here that makes a LOSS smaller, and the reason is worth stating
    because the intuitive one is wrong.** A position is sized off its stop distance, so moving the
    stop nearer buys a bigger position and the loss in money is unchanged. This does not move the
    stop that SIZED the trade — `risk` stays the structural distance, so 1R stays 1R and the
    position stays the same — it just refuses to sit through more than a fraction of it. A trade
    cut at 0.4 books −0.4R, i.e. 40% of what it would otherwise have cost.

    None keeps the structural stop, which is what every number in CLAUDE.md was measured on."""

    invalidate_on_choch: bool = False
    """Exit at the next bar's open when an external CHoCH prints AGAINST the trade.

    The reason for entering was a CHoCH; structure breaking back the other way says that reason
    is gone. Independent of `soft_stop_r` — one is a price bound, this is a structural one, and a
    trade can be wrong in either without being wrong in the other."""

    be_at_r: float = 0.0
    """Move the stop to `be_to_r` once the trade has travelled this many R in favour. 0 = off.

    An EARLIER step than the lock, so full risk is not carried for days while the trade works.
    Without it the stop sits at its opening level until `lock_at_r` fires — which on a structural
    stop is a long way and a long time."""

    be_to_r: float = 0.0
    """Where the early step puts the stop. 0.0 is plain breakeven; a small positive pays costs."""

    trail_swings: bool = True
    """After arming, ratchet the stop to each new CONFIRMED swing level from the same structure
    engine. False leaves the stop parked at `lock_to_r`."""

    max_days: float = 30.0
    """Hard close. A BACKSTOP, not a working rule — MEASURED, 30 / 60 / 90 days return the
    identical result because the median hold is 4 days and nothing reaches the cap.

    🔴 It exists because the earlier 10R-target version of this rule left trades open for 130+
    days and paid -8.66R of overnight swap on one that made +1.25R. Gold swap is charged, not
    free, and a rule with no time bound quietly turns a flat trade into a large loss."""

    horizon_days: float = 90.0
    """How far the simulator will walk before giving up and marking to market. Strictly a
    measurement bound — it must stay LARGER than `max_days` or the time stop never fires and the
    two limits silently become one."""

    def __post_init__(self) -> None:
        if self.risk_fraction <= 0:
            raise ValueError("risk_fraction must be positive; 0 means 'do not trade it'")
        if self.lock_to_r > self.lock_at_r:
            raise ValueError(
                f"lock_to_r ({self.lock_to_r}) cannot exceed lock_at_r ({self.lock_at_r}) — "
                "the stop cannot be placed beyond a price the trade has not reached"
            )
        if self.horizon_days < self.max_days:
            raise ValueError(
                f"horizon_days ({self.horizon_days}) is below max_days ({self.max_days}), so the "
                "time stop can never fire and the two limits are the same number wearing two names"
            )
        if self.stop_mode not in ("structural", "loss_entry"):
            raise ValueError(
                f"stop_mode {self.stop_mode!r} is not one of 'structural' / 'loss_entry' — a "
                "typo here would otherwise pick the default and look like a setting that applied"
            )
        if self.trail_pct < 0:
            raise ValueError("trail_pct is a magnitude; pass 0.5, not -0.5")
        if self.soft_stop_r is not None and not 0.0 < self.soft_stop_r <= 1.0:
            raise ValueError(
                f"soft_stop_r ({self.soft_stop_r}) must be inside (0, 1] — above 1 it sits beyond "
                "the structural stop and can never fire, which is a knob that reads as set and "
                "does nothing"
            )
        if self.be_to_r > self.be_at_r:
            raise ValueError(
                f"be_to_r ({self.be_to_r}) cannot exceed be_at_r ({self.be_at_r}) — the stop "
                "cannot be placed beyond a price the trade has not reached"
            )
        if self.be_at_r > self.lock_at_r:
            raise ValueError(
                f"be_at_r ({self.be_at_r}) is above lock_at_r ({self.lock_at_r}), so the early "
                "step fires after the lock it is meant to precede and one of the two is dead"
            )
        if self.scratch_r < 0:
            raise ValueError("scratch_r is a magnitude; pass 0.15, not -0.15")
