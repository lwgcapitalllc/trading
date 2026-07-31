"""
Post-run evaluation logic.
Branches on ruleset_type: prop_eval, prop_funded, personal, demo.
"""

from __future__ import annotations

import math
import uuid
from typing import Optional

from services import lab_db
from services.trailing_drawdown import compute_trailing_mll


def _simulated_eval_days(daily_pnl: list[dict]) -> int:
    return len([d for d in daily_pnl if d.get("pnl", 0.0) != 0.0])


def compute_contract_cap_status(max_contracts, runner, instrument, trade_sizes):
    """
    Largest-single-trade contract-cap check. Returns (status, note). INFORMATIONAL ONLY —
    this never feeds the PASS/WARN/DISCARD verdict.

    scaling ladder    → not_applicable (cap varies with profit; can't model statically)
    MT5 (lots)        → not_applicable (volume is lots, not futures contracts)
    NT8, no size data → not_evaluable
    NT8, fixed cap    → real largest-single-trade vs cap (micro for M-prefixed instruments,
                        else mini — a CME-naming heuristic)
    No max_contracts  → (None, None)
    """
    mc = max_contracts or {}
    if not mc:
        return None, None
    if mc.get("scaling"):
        return "not_applicable", "Contract cap not applicable (scaling ladder — cap varies with profit)"
    if runner == "mt5":
        return "not_applicable", "Contract cap not applicable (forex/lots — no futures-contract cap)"
    if not trade_sizes:
        return "not_evaluable", "Contract cap not evaluable — position size not recorded"
    largest = max(trade_sizes)
    is_micro = (instrument or "").upper().startswith("M")
    cap = mc.get("micro_max") if is_micro else mc.get("mini_max")
    unit = "micro" if is_micro else "mini"
    if cap is None:
        return "not_evaluable", "Contract cap not evaluable — no cap for this contract type"
    if largest <= cap:
        return "pass", f"Largest trade {largest:g} {unit} contracts (≤ {cap} cap)"
    return "fail", f"Largest trade {largest:g} {unit} contracts EXCEEDS {cap} cap"


def _notes_prop(
    ruleset: dict,
    drawdown_pass: bool,
    target_pass: bool,
    consistency_pass: Optional[bool],
    largest_day_share: Optional[float],
    mll: Optional[dict],
    net_pnl: float,
    adjusted_profit_target: Optional[float] = None,
) -> str:
    parts = []
    if mll is None:
        parts.append("Drawdown rule not applicable")
    elif drawdown_pass:
        parts.append(
            f"Trailing MLL ok — closest within ${mll['min_floor_distance']:,.0f} of floor "
            f"(final floor ${mll['final_floor']:,.0f})"
        )
    else:
        parts.append(
            f"Trailing MLL BREACHED on day {mll['breach_day']} "
            f"(floor ${mll['final_floor']:,.0f})"
        )

    if ruleset["ruleset_type"] == "prop_funded":
        return "; ".join(parts)

    pt = ruleset["profit_target"]
    raised = adjusted_profit_target is not None
    effective_pt = max(pt, adjusted_profit_target) if raised else pt
    if effective_pt > 0:
        label = f"raised ${effective_pt:,.0f}" if raised else f"${pt:,}"
        if target_pass:
            parts.append(f"Hit {label} profit target (net ${net_pnl:,.0f})")
        else:
            parts.append(f"Did not reach {label} target (net ${net_pnl:,.0f})")

    if consistency_pass is not None and largest_day_share is not None:
        limit = ruleset["consistency_pct"]
        if adjusted_profit_target is not None:
            # Consistency breached but firm raises the target instead of failing.
            parts.append(
                f"Largest single day was {largest_day_share:.1f}% of total profit "
                f"(EXCEEDS {limit:.0f}% limit) — profit target raised to ${adjusted_profit_target:,.0f}"
            )
        else:
            tag = "under" if consistency_pass else "EXCEEDS"
            parts.append(
                f"Largest single day was {largest_day_share:.1f}% of total profit "
                f"({tag} {limit:.0f}% limit)"
            )
    return "; ".join(parts)


def _evaluate_personal(
    ruleset: dict,
    daily_pnl: list[dict],
    net_pnl: float,
) -> tuple[str, bool, str, int]:
    """
    Personal/demo verdict — relaxed but real rules (no trailing MLL, no consistency,
    no profit-target requirement). Two DISCARD conditions; either one fails the run:

      1. Consecutive capped days — max_consecutive_loss_days days IN A ROW whose loss
         hit daily_loss_cap. The streak resets on any non-capped day.
      2. Drawdown from peak — EOD equity dropping max_drawdown_from_peak_pct or more
         from its running peak at any point in the run.

    daily_profit_target is a halt, not a rule: a day reaching it would have stopped
    trading for that day — noted, never failed.

    Honesty limits: backtest daily P&L can't distinguish a day halted AT the cap from
    one that simply lost that much, so "day's loss >= daily_loss_cap" is the capped-day
    trigger. Granularity is end-of-day (same convention as the trailing-MLL engine):
    an intraday dip through the drawdown limit that recovers by the close is invisible.

    A ruleset that configures NEITHER condition returns INFO, not PASS — see the verdict
    line at the end of this function.

    Returns (verdict, drawdown_pass, notes, breach_count) where breach_count is the
    number of DISCARD conditions that fired (0-2).
    """
    account_size = ruleset.get("account_size")
    daily_cap = ruleset.get("daily_loss_cap")
    streak_limit = ruleset.get("max_consecutive_loss_days")
    dd_limit_pct = ruleset.get("max_drawdown_from_peak_pct")
    profit_halt = ruleset.get("daily_profit_target")

    failures: list[str] = []
    info: list[str] = []

    # ── 1. Consecutive capped-loss days ────────────────────────────────────
    if daily_cap and streak_limit:
        streak = 0
        worst_streak = 0
        capped_days = 0
        breach_date = None
        for d in daily_pnl:
            if (d.get("pnl") or 0.0) <= -daily_cap:
                capped_days += 1
                streak += 1
                if streak > worst_streak:
                    worst_streak = streak
                if streak >= streak_limit and breach_date is None:
                    breach_date = d.get("date")
            else:
                streak = 0
        if worst_streak >= streak_limit:
            failures.append(
                f"{worst_streak} consecutive days hit the ${daily_cap:,.0f} daily cap"
                + (f" (streak completed {breach_date})" if breach_date else "")
            )
        elif capped_days:
            info.append(
                f"{capped_days} day(s) hit the ${daily_cap:,.0f} daily cap "
                f"(worst streak {worst_streak} of {streak_limit} allowed)"
            )

    # ── 2. Drawdown from peak (EOD equity) ─────────────────────────────────
    drawdown_pass = True
    if account_size and dd_limit_pct:
        balance = float(account_size)
        peak = balance
        worst_dd_pct = 0.0
        breach = None  # (dd_pct, date) at first crossing
        for d in daily_pnl:
            balance += d.get("pnl") or 0.0
            if balance > peak:
                peak = balance
            dd_pct = (peak - balance) / peak * 100 if peak > 0 else 0.0
            if dd_pct > worst_dd_pct:
                worst_dd_pct = dd_pct
            if dd_pct >= dd_limit_pct and breach is None:
                breach = (dd_pct, d.get("date"))
        if breach is not None:
            drawdown_pass = False
            failures.append(
                f"drew down {breach[0]:.1f}% from peak on {breach[1]} "
                f"(limit {dd_limit_pct:.0f}%)"
            )
        else:
            info.append(
                f"max drawdown from peak {worst_dd_pct:.1f}% "
                f"(limit {dd_limit_pct:.0f}%)"
            )

    # ── 3. Daily profit-target halts — informational only ──────────────────
    if profit_halt:
        halt_days = sum(1 for d in daily_pnl if (d.get("pnl") or 0.0) >= profit_halt)
        if halt_days:
            info.append(
                f"{halt_days} day(s) reached the ${profit_halt:,.0f} daily profit "
                f"target (would halt the day — informational)"
            )

    # ── Was anything actually checked? ─────────────────────────────────────
    # Mirrors the two guards above EXACTLY: check 1 runs only on `daily_cap and
    # streak_limit`, check 2 only on `account_size and dd_limit_pct`. A ruleset missing
    # the second half of either pair silently skips that check, so testing the caps alone
    # (as this note used to) called a run graded when nothing had graded it.
    graded_streak = bool(daily_cap and streak_limit)
    graded_dd = bool(account_size and dd_limit_pct)
    ungraded = not graded_streak and not graded_dd
    if ungraded:
        info.append("no personal fail conditions configured on this ruleset")

    # Zero failures out of zero checks is NOT a pass — it is the absence of a verdict, and
    # saying PASS there means "passed nothing". `unconstrained` is the ruleset this exists
    # for: it deliberately states no daily cap and no drawdown limit, so both checks are
    # skipped and `failures` is empty by construction — a run that lost 95% of the account
    # was graded PASS. services/lab_db.py already states the intended rule on that row:
    # "a run against it cannot be graded — every grade is a statement about drawdown vs a
    # limit, and there is no honest default to substitute". INFO is that absence; the
    # frontend renders it neutrally and skips the rule rows.
    verdict = "DISCARD" if failures else ("INFO" if ungraded else "PASS")
    parts = [f"net P&L ${net_pnl:,.0f}"] + failures + info
    return verdict, drawdown_pass, "; ".join(parts), len(failures)


def evaluate_run(
    run_id: str,
    ruleset_ids: list[str],
    kpis: dict,
    equity_curve: list[dict],
    daily_pnl: list[dict],
) -> list[dict]:
    """
    Evaluate a completed backtest run against the given rulesets.
    Inserts rows into `evaluations` table (INSERT OR REPLACE).
    Returns list of evaluation dicts.
    """
    results = []

    net_pnl = kpis.get("net_pnl") or 0.0

    # Run-level facts for the contract-cap check (per-trade size lives on equity_curve).
    run_row = lab_db.get_run(run_id) or {}
    runner = run_row.get("runner") or "ninjatrader"
    instrument = run_row.get("instrument") or ""
    trade_sizes = [t.get("size") for t in equity_curve if t.get("size") is not None]

    for rid in ruleset_ids:
        ruleset = lab_db.get_ruleset(rid)
        if ruleset is None:
            continue

        rtype = ruleset.get("ruleset_type", "prop_eval")

        # ── Drawdown check — end-of-day trailing max-loss (all types) ──────
        # Floor trails the highest EOD balance, capped at mll_lock_balance when set.
        # See services/trailing_drawdown.compute_trailing_mll.
        # No drawdown rule (max_loss_eod / account_size null) → not applicable:
        # mll stays None, drawdown_pass stays True so it neither fails nor false-passes.
        account_size = ruleset.get("account_size")
        mll_amount = ruleset.get("max_loss_eod")
        lock_balance = ruleset.get("mll_lock_balance")

        # Personal/demo accounts get no verdict, so no trailing reference line is drawn.
        skip_drawdown = rtype in ("personal", "demo")
        mll = None
        if not skip_drawdown and mll_amount is not None and account_size is not None:
            mll = compute_trailing_mll(daily_pnl, account_size, mll_amount, lock_balance)

        drawdown_pass = (not mll["breached"]) if mll is not None else True
        breach_count = (1 if mll["breached"] else 0) if mll is not None else 0
        adjusted_profit_target = None  # set only when a consistency breach raises the target

        # ── Contract-cap check — informational only, never moves the verdict ──
        contract_cap_status, contract_cap_note = compute_contract_cap_status(
            ruleset.get("max_contracts"), runner, instrument, trade_sizes
        )

        # ── Branch on ruleset_type ─────────────────────────────────────────
        if rtype == "prop_funded":
            target_pass = True
            consistency_pass = None
            largest_day_share = None
            verdict = "PASS" if drawdown_pass else "DISCARD"
            notes = _notes_prop(ruleset, drawdown_pass, True, None, None, mll, net_pnl)

        elif rtype == "prop_eval":
            # Consistency first — it may raise the profit target the target check uses.
            consistency_pass = None
            largest_day_share = None
            if (
                ruleset.get("consistency_pct") is not None
                and net_pnl > 0
            ):
                pos_days = [d.get("pnl", 0.0) for d in daily_pnl if d.get("pnl", 0.0) > 0]
                biggest_day = max(pos_days, default=0.0)
                largest_day_share = biggest_day / net_pnl * 100
                raw_breach = largest_day_share > ruleset["consistency_pct"]
                # consistency_breach_action: null/'fail' fails the account; 'raise_target'
                # passes-with-adjustment and raises the target the run must clear instead.
                breach_action = ruleset.get("consistency_breach_action") or "fail"
                if raw_breach and breach_action == "raise_target":
                    consistency_pass = True  # passed-with-adjustment
                    # Target needed for this day to satisfy the limit: biggest_day / (pct/100).
                    # No obvious firm increment, so use the raw figure rounded up to the dollar.
                    adjusted_profit_target = float(
                        math.ceil(biggest_day / (ruleset["consistency_pct"] / 100))
                    )
                else:
                    consistency_pass = not raw_breach

            # Profit target — compare net P&L against the effective (possibly raised) target.
            effective_target = ruleset["profit_target"]
            if adjusted_profit_target is not None:
                effective_target = max(ruleset["profit_target"], adjusted_profit_target)
            if effective_target == 0:
                target_pass = True
            else:
                target_pass = net_pnl >= effective_target

            if not drawdown_pass:
                verdict = "DISCARD"
            elif not target_pass:
                verdict = "WARN"
            elif consistency_pass is False:
                verdict = "WARN"
            else:
                verdict = "PASS"

            notes = _notes_prop(ruleset, drawdown_pass, target_pass, consistency_pass,
                                largest_day_share, mll, net_pnl, adjusted_profit_target)

        elif rtype in ("personal", "demo"):
            # Personal/demo verdict — two DISCARD conditions (consecutive capped-loss
            # days, drawdown from peak) evaluated against the relaxed personal rules.
            # No trailing MLL (max_loss_eod = 0 sentinel, skipped above), no profit
            # target requirement, no consistency rule. See _evaluate_personal.
            target_pass = True
            consistency_pass = None
            largest_day_share = None
            verdict, drawdown_pass, notes, breach_count = _evaluate_personal(
                ruleset, daily_pnl, net_pnl
            )

        else:
            # Unknown type — fall back to prop_eval logic
            target_pass = net_pnl >= ruleset.get("profit_target", 0)
            consistency_pass = None
            largest_day_share = None
            verdict = "DISCARD" if not drawdown_pass else ("PASS" if target_pass else "WARN")
            notes = f"Unknown ruleset_type '{rtype}'"

        sim_days = _simulated_eval_days(daily_pnl) if target_pass else None

        if contract_cap_note:
            notes = f"{notes}; {contract_cap_note}" if notes else contract_cap_note

        eval_data = {
            "eval_id": uuid.uuid4().hex[:12],
            "run_id": run_id,
            "ruleset_id": rid,
            "verdict": verdict,
            "drawdown_pass": drawdown_pass,
            "target_pass": target_pass,
            "consistency_pass": consistency_pass,
            "simulated_eval_days": sim_days,
            "breach_count": breach_count,
            "largest_day_share_pct": largest_day_share,
            "adjusted_profit_target": adjusted_profit_target,
            "contract_cap_status": contract_cap_status,
            # Trailing-MLL detail (for the UI; None when the rule is not applicable)
            "mll_final_floor": mll["final_floor"] if mll is not None else None,
            "mll_highest_eod_balance": mll["highest_eod_balance"] if mll is not None else None,
            "mll_breach_day": mll["breach_day"] if mll is not None else None,
            "mll_min_floor_distance": mll["min_floor_distance"] if mll is not None else None,
            "notes": notes,
        }
        lab_db.insert_evaluation(eval_data)
        results.append(eval_data)

    return results
