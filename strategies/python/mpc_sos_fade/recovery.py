"""Loss-recovery wiring — turns A+'s own losses into recovery trades in the same book.

The RULE is not here. It lives in `strategies/python/loss_recovery/`, defined against a
`LossEvent` protocol so any strategy in this repo can drive it; `execution.Trade` satisfies that
protocol unchanged. This module is only the adapter: it maps the flat `exec_recovery_*` inputs
onto that engine's config, runs it, and converts what comes back into `Trade` rows tagged
`kind="recovery"` so the lab, the KPIs, the equity curve and the chart all work with no changes
anywhere downstream.

🔴 **The one approximation, stated plainly because it is easy to forget and impossible to see in
the output.** The recovery sizes off the RUNNING balance — every A+ trade and every earlier
recovery trade that has already closed is in it. A+ does NOT size off the recovery. So the two
share a balance in one direction only.

That is a deliberate trade, not an oversight. Making A+ size off the recovery would mean a
lab-only toggle silently moved every A+ trade, every parity number and every figure in the
optimization log — a feature that can rewrite the shipped book is worth more care than this one
earns. The cost is that the equity curve slightly UNDERSTATES a winning recovery's compounding
and overstates a losing one's, by the amount A+ would have re-sized. With the recovery at a
quarter size and +4.8R over eight years, that is small — but it is not zero, and nobody should
read this curve as a shared-account run. See `backtest/portfolio/` for what a real one is.

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
from datetime import timedelta
from pathlib import Path
from typing import List

# strategies/python on the path so `loss_recovery` imports by bare name — the same shim
# secondary.py uses to reach engines/.
_PY_ROOT = Path(__file__).resolve().parents[1]
if str(_PY_ROOT) not in sys.path:
    sys.path.insert(0, str(_PY_ROOT))

from loss_recovery import LossRecoveryEngine, RecoveryConfig  # noqa: E402

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
    """Swap + spread + commission for one recovery trade, in R. Lot size cancels out of the ratio.

    Returns an honest 0.0 when no cost profile is configured — meaning "nothing was priced",
    never a claim that trading was free. The recovery engine models price only, so unlike an A+
    trade (whose costs are charged inside `Execution` as it goes) these have to be priced here.
    """
    swap = getattr(profile, "swap", None)
    if profile is None or swap is None or risk_price <= 0:
        return 0.0
    nights, day = 0, index[i0].date()
    while day < index[j].date():
        day += timedelta(days=1)
        if day.weekday() >= 5:      # the broker books no rollover at the weekend
            continue
        nights += 3 if day.weekday() == swap.triple_weekday else 1
    return (
        (swap.per_lot_per_night(direction) * nights) / (risk_price * swap.contract_size)
        - getattr(profile, "spread", 0.0) / risk_price
        - 2.0 * getattr(profile, "commission_per_side_per_lot", 0.0)
        / (risk_price * swap.contract_size)
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
    # because a recovery trade's own loss is not an A+ loss, and recovering a recovery is a rule
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
    # opens — A+ trades and earlier recovery trades alike. A heap rather than a sorted list
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
        ))
        heapq.heappush(closes, (rt.exit_index, pnl_usd))

    ex.trades.extend(out)
    ex.trades.sort(key=lambda t: (t.entry_index, t.exit_index))
    strategy._recovery_applied = True
    return out
