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
from typing import Any, Optional, Sequence

from .account import (
    DEFAULT_CONTRACT_SIZE,
    DEFAULT_MAX_LOTS,
    PortfolioAccount,
    SoloAccount,
)
from .legs import build_leg
from .simulator import simulate

__all__ = ["LegSpec", "StackRun", "run_stack", "contention_summary"]


@dataclass
class LegSpec:
    """One leg to stack: what to run, on which bars, under which config.

    `source` names ANOTHER leg in the same stack whose closed trades this one reads. It exists
    for a rule that has no setups of its own — `loss_recovery` fires off a primary's losses — and
    it is the one dependency a stack can express. Leave it `None` for an ordinary strategy.

    🔴 **A sourced leg is handed the source's LIVE trade list, not a copy.** The dependent arms
    when a source trade closes, so it reads a list that grows under it during the replay. A copy
    taken at build time is empty forever, and a leg that arms on nothing produces an empty book
    that reads exactly like a rule which found no setups — the failure gives no symptom.
    """

    name: str
    strategy_cls: Any
    config: Any
    df: Any
    cost_profile: Any = None
    source: str | None = None
    # The SECOND bar frame, for a strategy that trades on two (the A+ bot's re-entry fills on a
    # faster clock than its primary). `None` for the single-frame legs, which is most of them.
    # ⚠ It must cover the SAME window as `df`: the leg merges the two itself, and a fast frame
    # that starts later simply produces no re-entries over the part it does not reach — a
    # smaller book that reads exactly like a rule which found fewer setups.
    df_fast: Any = None


@dataclass
class StackRun:
    opening_balance: float
    risk_cap_pct: float
    entry_floor_pct: float
    closing_balance: float  # shared run's realized balance
    trades: list = field(default_factory=list)  # combined, shared run
    per_leg: dict = field(default_factory=dict)  # leg -> its trades in the shared run
    contention: list = field(default_factory=list)  # every shrink and refusal, time-stamped
    solo_per_leg: dict = field(default_factory=dict)  # leg -> its trades run ALONE (control)
    solo_closing: dict = field(default_factory=dict)  # leg -> its own closing balance, alone
    # leg -> the setups its OWN rules refused, and the ones that died partway, in the SHARED run.
    # Reporting-only, exactly as they are on a standalone run: a refused setup places no order, so
    # it is in no trade list and this is its only channel out. They are taken from the SHARED
    # replay rather than the solo control so they line up with `per_leg` — a block recorded in a
    # different replay would sit beside trades it never competed with.
    blocked_per_leg: dict = field(default_factory=dict)
    missed_per_leg: dict = field(default_factory=dict)
    peak_reserved_pct: float = 0.0  # most open risk carried, % of balance
    peak_concurrent: int = 0  # most legs holding a position at once
    cancelled: bool = False  # stopped early — every book is PARTIAL


def run_stack(
    specs: Sequence[LegSpec],
    *,
    balance: float,
    risk_cap_pct: float,
    entry_floor_pct: float = 0.0,
    solo_control: bool = True,
    max_lots: Optional[float] = DEFAULT_MAX_LOTS,
    contract_size: float = DEFAULT_CONTRACT_SIZE,
    progress: Any = None,
    should_cancel: Any = None,
) -> StackRun:
    """Replay `specs` together on one account, plus one solo control replay per leg.

    `risk_cap_pct` is a FRACTION of the live balance (0.10 = 10%), matching
    `PortfolioAccount.cap()`. It is the account-level rule the live allocator has to enforce
    too — the same number, or the stacked backtest stops predicting the stacked account.

    `max_lots` is the VENUE ceiling every leg's entries are resized down to, in lots — the
    largest position a broker will accept, defaulting to 100 (see `account.DEFAULT_MAX_LOTS`).
    `None` switches it off, which is what a parity harness wants. ⚠ **It is a resize, not a
    refusal**, so a run above the ceiling still trades — smaller — and stops compounding.

    ⚠ **ONE contract size for the whole account, so a stack mixing INSTRUMENTS would need a
    per-leg figure and does not have one.** Every stack here is gold at 100 oz/lot, which is the
    default; a stack pairing gold with an index would be silently measuring one of them against
    the other's lot size. Refuse that when it first appears rather than passing an average.

    `progress(phase, tick_index)` and `should_cancel()` are for a caller driving this from a
    UI — this is `1 + len(specs)` full replays, so on a full history it is minutes of work.
    ⚠ **A cancelled run RETURNS rather than raising, with `cancelled=True` and a partial
    book.** A caller must branch on that flag: a stack stopped a year in produces a perfectly
    ordinary-looking short result, and persisting it as finished is the "cancel did not
    cancel" defect from the other side — not a run that kept going, but a stopped run
    recorded as a complete one.
    """
    _refuse_duplicate_names(specs)
    _refuse_bad_sources(specs)
    if not 0.0 < risk_cap_pct:
        raise ValueError(
            f"risk_cap_pct must be positive, got {risk_cap_pct!r} — a cap of zero "
            f"refuses every entry, which is not a portfolio, it is a stopped bot."
        )

    account = PortfolioAccount(
        balance=balance,
        risk_cap_pct=risk_cap_pct,
        entry_floor_pct=entry_floor_pct,
        max_lots=max_lots,
        contract_size=contract_size,
    )
    # Sources first, so a dependent can be handed its source's live trade list at build time.
    # `_refuse_bad_sources` has already established that a source has no source of its own, so
    # one pass is the whole ordering — there is no chain to walk and no cycle to detect here.
    ordered = [s for s in specs if s.source is None] + [s for s in specs if s.source is not None]
    built: dict[str, Any] = {}
    for s in ordered:
        leg = build_leg(
            s.name,
            s.strategy_cls,
            s.config,
            s.df,
            account=account,
            initial_capital=balance,
            cost_profile=s.cost_profile,
            df_fast=s.df_fast,
        )
        if s.source is not None:
            _wire_source(leg, built[s.source], s.df)
        built[s.name] = leg
    # Back into the caller's order — `simulate` steps holders before flat legs anyway, but the
    # per-leg reporting and the solo controls read better in the order the caller asked for.
    legs = [built[s.name] for s in specs]
    result = simulate(
        legs,
        account,
        progress=(lambda i: progress("shared", i)) if progress else None,
        should_cancel=should_cancel,
    )

    run = StackRun(
        opening_balance=balance,
        risk_cap_pct=risk_cap_pct,
        entry_floor_pct=entry_floor_pct,
        closing_balance=account.balance,
        trades=list(result.trades),
        per_leg=dict(result.per_leg),
        contention=list(result.contention),
        peak_reserved_pct=account.peak_reserved_pct,
        peak_concurrent=account.peak_concurrent,
        cancelled=result.cancelled,
    )
    # ⚠ `getattr` with a default, never a direct read: `blocks` / `misses` are OPTIONAL on a
    # strategy's execution (`b_leg` records neither by construction — those codes describe why
    # an A+ setup was refused, and A+ never trades in that fork), so requiring them would refuse a
    # legitimate leg. An empty list and an absent attribute mean the same thing HERE — nothing was
    # recorded — which is the one place in this repo where collapsing them is right, because a
    # strategy that records none is a strategy with no such rule rather than one that could not be
    # asked.
    for leg in legs:
        ex = getattr(leg.strategy, "execution", None)
        run.blocked_per_leg[leg.name] = list(getattr(ex, "blocks", None) or [])
        run.missed_per_leg[leg.name] = list(getattr(ex, "misses", None) or [])
    if result.cancelled:
        # No solo controls for a cancelled shared run. A control's whole job is to be
        # comparable to the shared book, and a control over the FULL history beside a shared
        # book that stopped a year in is not a control — it is two different experiments in
        # one table, and the delta column would read as the cap's doing.
        return run
    if solo_control:
        by_name = {s.name: s for s in specs}
        for spec in specs:
            solo = SoloAccount(balance=balance, max_lots=max_lots, contract_size=contract_size)
            leg = build_leg(
                spec.name,
                spec.strategy_cls,
                spec.config,
                spec.df,
                account=solo,
                initial_capital=balance,
                cost_profile=spec.cost_profile,
                df_fast=spec.df_fast,
            )
            # 🔴 A SOURCED LEG ALONE HAS NOTHING TO RECOVER, so its control needs a private copy
            # of its source running beside it — on its OWN account, so only the leg being measured
            # books onto `solo`. Without this the control is an empty book, and an empty control
            # makes the shared result look like the whole of the leg's worth rather than the part
            # of it that survived the competition.
            #
            # ⚠ The private source's trades are DISCARDED on purpose. It exists to lose, so this
            # leg has losses to read; reporting them would put a second copy of the source's book
            # in a run that already has one.
            company = []
            if spec.source is not None:
                src_spec = by_name[spec.source]
                src_leg = build_leg(
                    src_spec.name,
                    src_spec.strategy_cls,
                    src_spec.config,
                    src_spec.df,
                    df_fast=src_spec.df_fast,
                    account=SoloAccount(
                        balance=balance, max_lots=max_lots, contract_size=contract_size
                    ),
                    initial_capital=balance,
                    cost_profile=src_spec.cost_profile,
                )
                _wire_source(leg, src_leg, spec.df)
                company = [src_leg]
            solo_result = simulate(
                company + [leg],
                solo,
                progress=(lambda i, n=spec.name: progress(f"solo:{n}", i)) if progress else None,
                should_cancel=should_cancel,
            )
            if solo_result.cancelled:
                run.cancelled = True
                return run
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
        raise ValueError(
            f"two legs share a name: {sorted(dupes)}. The shared account keys an "
            f"open position by leg name, so duplicates overwrite each other's "
            f"reservation and the risk cap silently under-counts."
        )


def _refuse_bad_sources(specs: Sequence[LegSpec]) -> None:
    """Every `source` must name another leg in this stack, and that leg must have none itself.

    Three refusals, and each one has a silent failure behind it:

    * **A source that is not in the stack** would leave the dependent with nothing to read. It
      arms on nothing, produces an empty book, and that is indistinguishable from a rule which
      genuinely found no setups.
    * **A leg sourcing itself** would have it read its own trade list as it writes to it.
    * **A chain** (A sources B, B sources C) is refused rather than supported, because the moment
      chains are legal so are cycles, and a cycle here is an infinite build rather than an error.
      Nothing in this repo wants one; when something does, it arrives with its own ordering.
    """
    names = {s.name for s in specs}
    sourced = {s.name for s in specs if s.source is not None}
    for s in specs:
        if s.source is None:
            continue
        if s.source == s.name:
            raise ValueError(
                f"leg {s.name!r} names itself as its source — it would read its own trade "
                f"list as it writes to it."
            )
        if s.source not in names:
            raise ValueError(
                f"leg {s.name!r} sources {s.source!r}, which is not in this stack. It would "
                f"read nothing and return an empty book, which reads exactly like a rule that "
                f"found no setups. Add that leg, or drop this one."
            )
        if s.source in sourced:
            raise ValueError(
                f"leg {s.name!r} sources {s.source!r}, which is itself sourced. Chained sources "
                f"are refused: once a chain is legal so is a cycle, and a cycle here builds "
                f"forever rather than raising."
            )


def _wire_source(leg: Any, source_leg: Any, df: Any) -> None:
    """Hand `leg` the source's LIVE trade list and the frame's end.

    ⚠ `source_leg.trades` is the list the source APPENDS to — passing `list(...)` here is the
    one mistake this whole mechanism exists to avoid, and it fails silently.

    ⚠ `bar_ms` is read off the leg's own execution rather than recomputed from `df`, because
    `StrategyLeg.__init__` has already measured it there and two readings of one fact are how
    they come to disagree. A leg whose frame has one bar leaves it 0; the `or 1` keeps the
    division safe and the horizon is meaningless on a one-bar frame either way.
    """
    for method in ("watch", "set_horizon"):
        if not hasattr(leg.strategy, method):
            raise TypeError(
                f"leg {leg.name!r} was given a source but does not implement {method}(). Only a "
                f"leg that reads another's closed trades can take one — see "
                f"strategies/python/loss_recovery/leg.py for the contract."
            )
    leg.strategy.watch(source_leg.trades)
    per_day = 86_400_000.0 / max(int(leg.strategy.execution.bar_ms) or 1, 1)
    leg.strategy.set_horizon(len(df.index) - 1, per_day)


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
