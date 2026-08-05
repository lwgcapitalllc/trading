"""
Objective functions for the optimizer.
Each returns a float where higher = better.
The optimizer ranks param sets by the chosen objective.
"""

from __future__ import annotations

from typing import Optional

from services.metrics import effective_dd_limit_usd


OBJECTIVES = {}


def _register(name: str):
    def decorator(fn):
        OBJECTIVES[name] = fn
        return fn
    return decorator


@_register("eval_pass_probability")
def eval_pass_probability(run: dict, firm: dict) -> float:
    """
    For eval mode. Score 0.0–1.5.
    1.0 = drawdown ok + target hit; bonus up to 0.5 for hitting target quickly.
    Partial credit (0–0.5) if drawdown passes but target is not reached.
    0.0 if drawdown breached.
    """
    evals = run.get("_evaluations", [])
    target_eval = next((e for e in evals if e["ruleset_id"] == firm["id"]), None)

    if target_eval is None:
        # Fall back to KPI-only heuristic when eval record not loaded
        dd = abs(run.get("max_drawdown") or 0.0)
        pf = run.get("profit_factor") or 0.0
        net = run.get("net_pnl") or 0.0
        # Personal/demo: max_loss_eod = 0 is a sentinel, not a $0 limit. The helper
        # returns their drawdown-from-peak rule in dollars; 0 = no limit, skip the gate.
        dd_limit = effective_dd_limit_usd(firm)
        if dd_limit > 0 and dd > dd_limit:
            return 0.0
        if net >= firm.get("profit_target", 0):
            return 1.0
        if firm.get("profit_target", 0) > 0:
            return 0.5 * (net / firm["profit_target"])
        return 0.5 if pf > 1.0 else 0.0

    if not target_eval.get("drawdown_pass"):
        return 0.0
    if not target_eval.get("target_pass"):
        net = run.get("net_pnl") or 0.0
        pt  = firm.get("profit_target") or 1
        return 0.5 * min(1.0, net / pt) if pt > 0 else 0.0

    sim_days = target_eval.get("simulated_eval_days") or 30
    speed_bonus = max(0.0, 1.0 - (sim_days / 30))
    return 1.0 + 0.5 * speed_bonus


@_register("funded_sharpe_under_drawdown")
def funded_sharpe_under_drawdown(run: dict, firm: dict) -> float:
    """
    For funded mode. Sharpe ratio if drawdown is within limit, -inf if breached.
    """
    dd = abs(run.get("max_drawdown") or 0.0)
    # Personal/demo sentinel handling — see eval_pass_probability above.
    dd_limit = effective_dd_limit_usd(firm)
    if dd_limit > 0 and dd > dd_limit:
        return float("-inf")
    return run.get("sharpe") or 0.0


@_register("raw_profit_factor")
def raw_profit_factor(run: dict, firm) -> float:
    """For MT5/Python/no-ruleset mode. Maximise profit factor directly.

    ⚠ Profit factor alone has no sample-size opinion: two lucky trades at PF 8.0 outrank two
    hundred trades at PF 2.0, and the optimizer would hand you the two. The floor that stops
    that is `min_trades` on the optimization row, applied in `_pick_best_run` rather than here
    — a combo below the floor is still SCORED and still listed, it just cannot win.
    """
    return run.get("profit_factor") or 0.0


def choose_objective(mode: str):
    """Return the appropriate objective function for the given mode."""
    if mode == "funded":
        return OBJECTIVES["funded_sharpe_under_drawdown"]
    if mode == "raw":
        return OBJECTIVES["raw_profit_factor"]
    return OBJECTIVES["eval_pass_probability"]
