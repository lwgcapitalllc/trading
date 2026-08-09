"""Run a stack of real bots through ONE shared account — the SHARED view.

This is the other half of the pair `combine.py` opens. `combine_runs` adds up finished
standalone runs; it is a screen and an UPPER BOUND, because every leg in it traded a full
account and was never blocked. This runs the legs together: one balance they all size against,
one live risk budget they compete for, one merged clock. It is the view that answers "what
would this have done on my demo account".

Two facts about the shared account decide everything downstream, and both are the point rather
than side effects:

  * **One balance.** Every leg's `equity` reads `account.balance` and every leg's P&L books
    onto it, so a loss on one leg shrinks the next trade of the other. Solo, each leg compounds
    its own private ledger and the two never meet.
  * **One budget.** An open trade reserves risk to its CURRENT stop, so the reservation falls to
    zero when a stop reaches breakeven and the room is released. An entry is granted full size,
    shrunk to what fits, or refused — and every shrink and refusal lands in the contention log,
    which is the record of what sharing actually cost.

`run_stack` also runs each leg SOLO, on the same bars, and returns both. That is not a
convenience: without the solo control a difference in the shared book is a mixture of *the cap
bit* and *the shared balance re-sized everything*, and nothing afterwards separates them. The
control costs one extra replay per leg and it is what makes the delta attributable.

Pure and offline. The lab wiring (a `mode` on the stacks table, an endpoint, the contention
markers on the chart) is Phase 2 and lives in `command-center/`.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Sequence

from .account import PortfolioAccount, SoloAccount
from .legs import build_leg
from .simulator import simulate

__all__ = ["LegSpec", "StackRun", "run_stack", "contention_summary"]


@dataclass
class LegSpec:
    """One leg to stack: what to run, on which bars, under which config."""
    name: str
    strategy_cls: Any
    config: Any
    df: Any
    cost_profile: Any = None


@dataclass
class StackRun:
    opening_balance: float
    risk_cap_pct: float
    entry_floor_pct: float
    closing_balance: float                              # shared run's realized balance
    trades: list = field(default_factory=list)          # combined, shared run
    per_leg: dict = field(default_factory=dict)         # leg -> its trades in the shared run
    contention: list = field(default_factory=list)      # every shrink and refusal, time-stamped
    solo_per_leg: dict = field(default_factory=dict)    # leg -> its trades run ALONE (control)
    solo_closing: dict = field(default_factory=dict)    # leg -> its own closing balance, alone
    peak_reserved_pct: float = 0.0                      # most open risk carried, % of balance
    peak_concurrent: int = 0                            # most legs holding a position at once


def run_stack(specs: Sequence[LegSpec], *, balance: float, risk_cap_pct: float,
              entry_floor_pct: float = 0.0, solo_control: bool = True) -> StackRun:
    """Replay `specs` together on one account, plus one solo control replay per leg.

    `risk_cap_pct` is a FRACTION of the live balance (0.10 = 10%), matching
    `PortfolioAccount.cap()`. It is the account-level rule the live allocator has to enforce
    too — the same number, or the stacked backtest stops predicting the stacked account.
    """
    _refuse_duplicate_names(specs)
    if not 0.0 < risk_cap_pct:
        raise ValueError(f"risk_cap_pct must be positive, got {risk_cap_pct!r} — a cap of zero "
                         f"refuses every entry, which is not a portfolio, it is a stopped bot.")

    account = PortfolioAccount(balance=balance, risk_cap_pct=risk_cap_pct,
                               entry_floor_pct=entry_floor_pct)
    legs = [build_leg(s.name, s.strategy_cls, s.config, s.df, account=account,
                      initial_capital=balance, cost_profile=s.cost_profile) for s in specs]
    result = simulate(legs, account)

    run = StackRun(opening_balance=balance, risk_cap_pct=risk_cap_pct,
                   entry_floor_pct=entry_floor_pct, closing_balance=account.balance,
                   trades=list(result.trades), per_leg=dict(result.per_leg),
                   contention=list(result.contention),
                   peak_reserved_pct=account.peak_reserved_pct,
                   peak_concurrent=account.peak_concurrent)
    if solo_control:
        for spec in specs:
            solo = SoloAccount(balance=balance)
            leg = build_leg(spec.name, spec.strategy_cls, spec.config, spec.df, account=solo,
                            initial_capital=balance, cost_profile=spec.cost_profile)
            simulate([leg], solo)
            run.solo_per_leg[spec.name] = list(leg.trades)
            run.solo_closing[spec.name] = solo.balance
    return run


def _refuse_duplicate_names(specs: Sequence[LegSpec]) -> None:
    """Two legs may not share a name.

    The account keys an open position by leg name, so a duplicate does not raise anywhere — the
    second leg's fill silently REPLACES the first leg's reservation, the cap under-counts the
    open risk from that moment on, and the run reports a risk budget it was not enforcing. That
    is the quiet direction, so it is refused up front.
    """
    seen: set[str] = set()
    dupes: set[str] = set()
    for spec in specs:
        if spec.name in seen:
            dupes.add(spec.name)
        seen.add(spec.name)
    if dupes:
        raise ValueError(f"two legs share a name: {sorted(dupes)}. The shared account keys an "
                         f"open position by leg name, so duplicates overwrite each other's "
                         f"reservation and the risk cap silently under-counts.")


def contention_summary(run: StackRun) -> dict:
    """Per-leg tally of what sharing cost this leg: how often it was shrunk, and blocked."""
    out: dict[str, dict] = {}
    for row in run.contention:
        leg = out.setdefault(row["leg"], {"shrunk": 0, "blocked": 0, "risk_refused": 0.0})
        if row["blocked"]:
            leg["blocked"] += 1
            leg["risk_refused"] += row["desired_risk"]
        else:
            leg["shrunk"] += 1
            leg["risk_refused"] += row["desired_risk"] - row["granted_risk"]
    for leg in out.values():
        leg["risk_refused"] = round(leg["risk_refused"], 2)
    return out
