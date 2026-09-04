"""Loss-recovery wiring — turns SOS Fade's own losses into recovery trades in the same book.

The RULE is not here. It lives in `strategies/python/loss_recovery/`, defined against a
`LossEvent` protocol so any strategy in this repo can drive it; `execution.Trade` satisfies that
protocol unchanged. This module is only the adapter: it maps the flat `exec_recovery_*` inputs
onto that engine's config, runs it, and converts what comes back into `Trade` rows tagged
`kind="recovery"` so the lab, the KPIs, the equity curve and the chart all work with no changes
anywhere downstream.

🔴 **The one approximation, stated plainly because it is easy to forget and impossible to see in
the output.** The recovery sizes off the RUNNING balance — every SOS Fade trade and every earlier
recovery trade that has already closed is in it. SOS Fade does NOT size off the recovery. So the two
share a balance in one direction only.

That is a deliberate trade, not an oversight. Making SOS Fade size off the recovery would mean a
lab-only toggle silently moved every SOS Fade trade, every parity number and every figure in the
optimization log — a feature that can rewrite the shipped book is worth more care than this one
earns.

🔴 **The cost is NOT small, and this paragraph said it was until it was measured (2026-08-20, run
`236e206d0142`).** Recovery profit sits BESIDE the curve instead of lifting it, so it never
compounds — and over a run that grows several thousand times, an early gain is rounding by the
end. Identical trades, added up two ways: **+3.8% as this module runs it, +59.9% on one shared
compounding balance.** The leg is worth +5.04R account-weighted either way; only whether that R
compounds differs.

⚠ **Neither figure settles anything, and do not quote the second as this rule's worth.** The 59.9%
also assumes one balance carrying NO risk budget. Put a 10% account cap on it — the number this
bot already runs — and 23 of that run's 160 SOS Fade entries opened while a recovery was still holding
risk, which turns the leg NEGATIVE. The honest range is +45% to -15%, decided by an allocator that
does not exist on the live side. Full bracket, and what would settle it:
`strategies/python/loss_recovery/CLAUDE.md`.

**What a recovery row carries for the CHART, and what it honestly cannot.** It carries the
entry, the exit, the 1R stop, and both excursion extremes — which is everything the price chart's
profit-depth view needs, so a recovery trade is drawn with the same figures as any other trade
rather than degrading to a bare outcome rectangle. 🔴 **That degradation is not a styling choice
and was never meant to distinguish anything** — the chart falls back to a plain box for a record
too thin to draw (an NT8/MT5 trade with no fill prices), so a recovery row missing its excursion
looked like a DIFFERENT KIND OF TRADE when it was really a thinner record of the same kind. The
lesson is the general one: **an absence rendered as a distinct shape becomes a claim**, and a
reader has no way to tell "this is different" from "we recorded less".

It carries no take-profit ladder and no fib leg, and those absences are real: this rule has no
targets (it locks at +1R and trails) and prices nothing off a fib. The chart therefore draws no
TP lines on a recovery trade, which is the correct picture and not a missing field.

⚠ **`r` on a recovery Trade is the trade's OWN R**, exactly as on every other Trade here, so
`pnl_usd / risk_usd` reproduces it. The quarter-sizing is carried in the DOLLARS — `risk_usd` is
a quarter of a normal trade's — which is what makes the equity curve correct without a second
meaning for `r`. Do not "fix" this to `scaled_r`: that would make one row's R mean something
different from its neighbour's, which is the unit error `loss_recovery/types.py` warns about
arriving from the other side.
"""

from __future__ import annotations

import heapq
import sys
from pathlib import Path
from typing import List

# strategies/python on the path so `loss_recovery` imports by bare name — the same shim
# secondary.py uses to reach engines/.
_PY_ROOT = Path(__file__).resolve().parents[1]
if str(_PY_ROOT) not in sys.path:
    sys.path.insert(0, str(_PY_ROOT))

from loss_recovery import LossRecoveryEngine, RecoveryConfig  # noqa: E402
from loss_recovery.costs import hold_cost_r  # noqa: E402

from .execution import Trade  # noqa: E402

RECOVERY_KIND = "recovery"


def recovery_config(cfg) -> RecoveryConfig:
    """Map the strategy's flat inputs onto the engine's config.

    `major_length` is left at the engine's own default on purpose: it is 15 there BECAUSE that is
    what this bot runs, and the recovery must read the SAME structure the primary read — a
    recovery entry off a different structure stream is a different rule that happens to share a
    trigger. If this bot's structure length ever becomes an input, this is the line that has to
    start reading it.

    `soft_stop_r` is 0-means-off on the strategy input and None-means-off in the engine, because
    a UI needs a number where the engine wants an absence. This is the one place that translates.
    """
    return RecoveryConfig(
        enabled=True,
        scratch_r=cfg.exec_scratch_r,
        both_directions=cfg.exec_recovery_both_dirs,
        risk_fraction=cfg.exec_recovery_risk_frac,
        lock_at_r=cfg.exec_recovery_lock_at_r,
        lock_to_r=cfg.exec_recovery_lock_to_r,
        soft_stop_r=(cfg.exec_recovery_soft_stop_r or None),
        max_days=cfg.exec_recovery_max_days,
        # Strictly a measurement bound and it MUST stay above max_days, or the time stop never
        # fires and the two limits silently become one number wearing two names.
        horizon_days=max(90.0, cfg.exec_recovery_max_days * 3.0),
    )


def _cost_r(profile, index, direction: int, i0: int, j: int, risk_price: float) -> float:
    """Swap + spread + commission for one recovery trade, in R.

    A thin shim over `loss_recovery.costs.hold_cost_r` — the arithmetic lives there because the
    shared-account leg prices the same trade and two copies is how they come to disagree. This
    end owns only the translation from bar INDEX to timestamp.
    """
    return hold_cost_r(
        profile,
        int(index[i0].timestamp() * 1000),
        int(index[j].timestamp() * 1000),
        direction,
        risk_price,
    )


def apply(strategy, df) -> List[Trade]:
    """Run the recovery over this strategy's finished book and append what it takes.

    Returns the recovery trades (empty when the toggle is off). IDEMPOTENT: calling it twice does
    not double the book — the second call sees the first call's rows and refuses. That matters
    because more than one caller drives this (`run`, `run_dual`, and the lab's own bar loop), and
    a strategy object that had been finalized twice would otherwise report a book nobody traded.
    """
    cfg = strategy.config
    ex = strategy.execution
    if not cfg.exec_recovery:
        return []
    # Idempotence is tracked on the STRATEGY, not inferred from "are there recovery rows in the
    # book". Inferring it made the source filter below unreachable — a book with recovery rows
    # returned here, so the filter could never be exercised and no test could redden it. Dead
    # code that reads as load-bearing is worse than no code: the next reader trusts it.
    if getattr(strategy, "_recovery_applied", False):
        return []

    # The engine owns the loss filter, so it is handed the full book rather than a pre-filtered
    # one — a caller cannot then accidentally supply a list somebody else already filtered on a
    # different scratch band and get a silently different population. Recovery rows are excluded
    # because a recovery trade's own loss is not an SOS Fade loss, and recovering a recovery is a rule
    # nobody has measured.
    source = [t for t in ex.trades if t.kind != RECOVERY_KIND]
    if not source:
        return []

    found = LossRecoveryEngine(recovery_config(cfg)).run(df, source)
    if not found:
        return []

    index = df.index
    point_value = cfg.point_value
    unit_risk_pct = cfg.exec_risk_pct / 100.0
    frac = cfg.exec_recovery_risk_frac

    # Walk the balance forward through every trade that has already CLOSED when each recovery
    # opens — SOS Fade trades and earlier recovery trades alike. A heap rather than a sorted list
    # because recovery closes are discovered as we go, so the sequence is not known up front.
    closes = [(t.exit_index, t.pnl_usd) for t in ex.trades]
    heapq.heapify(closes)
    balance = ex.initial_capital

    out: List[Trade] = []
    for rt in sorted(found, key=lambda x: x.entry_index):
        while closes and closes[0][0] <= rt.entry_index:
            balance += heapq.heappop(closes)[1]
        risk_usd = max(balance, 0.0) * unit_risk_pct * frac
        qty = risk_usd / (rt.risk * point_value) if rt.risk > 0 else 0.0
        costs_usd = _cost_r(ex._profile, index, rt.direction,
                            rt.entry_index, rt.exit_index, rt.risk) * risk_usd
        pnl_usd = rt.r * risk_usd + costs_usd
        # Excursion, carried as both PRICES and DOLLARS so a recovery row answers the same
        # questions on the chart and the equity view that a primary row does — `Furthest`,
        # `Deepest`, and the excursion band. Both are stepped off the engine's OWN R figures
        # rather than re-read from the bars: the engine already measured them, on the same bars,
        # with the exit-bar caps that keep them inside what the trade actually lived through, and
        # a second reading here would be a second answer free to disagree with the first.
        mfe_price = rt.entry_price + rt.direction * rt.max_favourable_r * rt.risk
        mae_price = rt.entry_price - rt.direction * rt.max_adverse_r * rt.risk
        out.append(Trade(
            dir=rt.direction,
            entry_index=rt.entry_index,
            entry_price=rt.entry_price,
            exit_index=rt.exit_index,
            qty=qty,
            risk_usd=risk_usd,
            pnl_usd=pnl_usd,
            r=(pnl_usd / risk_usd) if risk_usd > 0 else 0.0,
            entry_ms=int(index[rt.entry_index].timestamp() * 1000),
            exit_ms=int(index[rt.exit_index].timestamp() * 1000),
            costs_usd=costs_usd,
            exit_price=rt.exit_price,
            stop_distance=rt.risk,
            exit_reason=rt.exit_reason,
            kind=RECOVERY_KIND,
            mfe_price=mfe_price,
            mae_price=mae_price,
            # Same sign convention as every other Trade here: favourable ≥ 0, adverse ≤ 0.
            mfe_usd=rt.max_favourable_r * risk_usd,
            mae_usd=-rt.max_adverse_r * risk_usd,
        ))
        heapq.heappush(closes, (rt.exit_index, pnl_usd))

    ex.trades.extend(out)
    ex.trades.sort(key=lambda t: (t.entry_index, t.exit_index))
    strategy._recovery_applied = True
    return out
