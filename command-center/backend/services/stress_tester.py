"""
Stress tester — Monte Carlo (Step 2), walk-forward, sensitivity (Step 3).
Pure Python + numpy for MC. Walk-forward/sensitivity trigger NT8 via VPS.
"""

from __future__ import annotations

import asyncio
import json
import logging
import time
import uuid
from datetime import date, timedelta
from pathlib import Path
from typing import Optional

import numpy as np

from services import lab_db
from services import notify
from services.metrics import daily_sharpe_from_values, apply_canonical_sharpe

log = logging.getLogger("stress_tester")

_RESULTS_DIR = Path(__file__).parent.parent / "reports" / "lab"
_POLL_INTERVAL = 5
_STALL_KILL_SEC = 600


# ── Monte Carlo ────────────────────────────────────────────────────────────────

def run_monte_carlo(
    trade_pnls: list[float],
    ruleset: Optional[dict] = None,
    num_reshuffles: int = 10_000,
    num_bootstrap: int = 1_000,
    num_path_samples: int = 100,
) -> dict:
    """Vectorised Monte Carlo on trade PnL list. Returns percentile stats + sampled paths."""
    if not trade_pnls:
        raise ValueError("No trades to simulate")

    trades = np.array(trade_pnls, dtype=np.float64)
    n = len(trades)
    rng = np.random.default_rng()

    # Vectorised reshuffles: argsort(random) produces a random permutation per row
    idx_rs = np.argsort(rng.random((num_reshuffles, n)), axis=1)
    shuffled = trades[idx_rs]
    equity_rs = np.cumsum(shuffled, axis=1)
    peak_rs = np.maximum.accumulate(equity_rs, axis=1)
    final_pnl_rs = equity_rs[:, -1]
    max_dd_rs = np.max(peak_rs - equity_rs, axis=1)

    # Vectorised bootstrap (sample with replacement)
    idx_bs = rng.integers(0, n, size=(num_bootstrap, n))
    resampled = trades[idx_bs]
    equity_bs = np.cumsum(resampled, axis=1)
    peak_bs = np.maximum.accumulate(equity_bs, axis=1)
    final_pnl_bs = equity_bs[:, -1]
    max_dd_bs = np.max(peak_bs - equity_bs, axis=1)

    all_pnls = np.concatenate([final_pnl_rs, final_pnl_bs])
    all_dds = np.concatenate([max_dd_rs, max_dd_bs])

    # Final-PnL percentiles come from the BOOTSTRAP pool only. Reshuffles keep the same
    # trades, so their sum (final PnL) is order-invariant — every reshuffle ends at the net
    # total, which would collapse median/p5/p1 onto one number. Bootstrap resamples with
    # replacement, so its final PnL genuinely varies. (Drawdown still uses both pools below —
    # order DOES change drawdown, so reshuffles are valid there.)
    median_final_pnl = float(np.percentile(final_pnl_bs, 50))
    pct5_final_pnl   = float(np.percentile(final_pnl_bs, 5))   # worst 5% outcome by PnL
    pct1_final_pnl   = float(np.percentile(final_pnl_bs, 1))   # worst 1% outcome by PnL
    median_max_dd    = float(np.percentile(all_dds, 50))
    pct5_max_dd      = float(np.percentile(all_dds, 95))   # 95th pct = worst-5% drawdown
    pct1_max_dd      = float(np.percentile(all_dds, 99))   # 99th pct = worst-1% drawdown

    prob_breach = 0.0
    prob_pass_eval = 0.0
    if ruleset:
        max_loss = ruleset.get("max_loss_eod") or ruleset.get("daily_loss_cap") or 0
        profit_target = ruleset.get("profit_target") or 0
        rtype = ruleset.get("ruleset_type", "prop_eval")
        if max_loss > 0:
            prob_breach = float(np.mean(all_dds > max_loss))
        if rtype in ("prop_eval", "personal") and profit_target > 0 and max_loss > 0:
            # Pass = hit target AND never breach drawdown, per path. Use the BOOTSTRAP pool only:
            # reshuffle final PnLs are all the net total (order-invariant), so pairing all_pnls
            # with the target collapses the PnL test to a single value and skews the probability.
            # Bootstrap resamples vary both PnL and drawdown, so the pass rate is real.
            prob_pass_eval = float(np.mean((final_pnl_bs >= profit_target) & (max_dd_bs <= max_loss)))
        elif rtype in ("prop_funded", "demo") and max_loss > 0:
            prob_pass_eval = 1.0 - prob_breach

    sampled_paths = equity_rs[:num_path_samples].tolist()

    dd_hist, dd_edges = np.histogram(all_dds, bins=50)
    # Final-PnL histogram uses the bootstrap pool to match the corrected percentiles —
    # reshuffles are order-invariant in sum and would spike the histogram at the net total.
    pnl_hist, pnl_edges = np.histogram(final_pnl_bs, bins=50)
    distribution = {
        "max_dd": {"counts": dd_hist.tolist(), "edges": dd_edges.tolist()},
        "final_pnl": {"counts": pnl_hist.tolist(), "edges": pnl_edges.tolist()},
    }

    return {
        "median_final_pnl": round(median_final_pnl, 2),
        "pct5_final_pnl":   round(pct5_final_pnl, 2),
        "pct1_final_pnl":   round(pct1_final_pnl, 2),
        "median_max_dd":    round(median_max_dd, 2),
        "pct5_max_dd":      round(pct5_max_dd, 2),
        "pct1_max_dd":      round(pct1_max_dd, 2),
        "prob_breach":      round(prob_breach, 4),
        "prob_pass_eval":   round(prob_pass_eval, 4),
        "sampled_paths":    sampled_paths,
        "distribution":     distribution,
    }


# ── Walk-forward helpers ───────────────────────────────────────────────────────

def _split_windows(start_date: str, end_date: str, n_windows: int) -> list[dict]:
    start = date.fromisoformat(start_date)
    end   = date.fromisoformat(end_date)
    total_days = (end - start).days
    if total_days < n_windows * 10:
        raise ValueError(f"Date range too short for {n_windows} walk-forward windows")
    window_days = total_days // n_windows
    windows = []
    for i in range(n_windows):
        w_start = start + timedelta(days=i * window_days)
        w_end   = (start + timedelta(days=(i + 1) * window_days)) if i < n_windows - 1 else end
        split   = w_start + timedelta(days=int(window_days * 0.7))
        windows.append({
            "window": i + 1,
            "is_start": w_start.isoformat(),
            "is_end":   split.isoformat(),
            "oos_start": split.isoformat(),
            "oos_end":  w_end.isoformat(),
        })
    return windows


def _compute_sharpe(equity_curve_data: list[dict]) -> float:
    """Daily-returns Sharpe from an equity curve's per-trade rows (aggregated by date)."""
    # Aggregate per-trade profit into daily P&L first — Sharpe is a DAILY-returns metric.
    # (Previously this annualized per-trade mean/std as if each trade were a day.)
    daily: dict[str, float] = {}
    for t in equity_curve_data:
        d = t.get("date") or ""
        if not d:
            continue
        daily[d] = daily.get(d, 0.0) + (t.get("profit", 0.0) or 0.0)
    return daily_sharpe_from_values(list(daily.values()))


def _estimate_wf_duration_min(n_windows: int) -> int:
    return n_windows * 2 * 5  # 2 runs per window × ~5 min each


def _estimate_sens_duration_min(n_params: int, runner: str = "ninjatrader") -> int:
    shifts = 2 if runner == "mt5" else 4
    mins_per_job = 1.5 if runner == "mt5" else 5
    return int(n_params * shifts * mins_per_job)


# ── VPS child-run helper (mirrors sweep_runner._run_one) ──────────────────────

async def _run_child_backtest(run_id: str, job_spec: dict, runner: str = "ninjatrader") -> bool:
    """Start a VPS backtest and poll to completion. Returns True on success."""
    from services import runner_dispatch
    try:
        await asyncio.to_thread(runner_dispatch.start_backtest, job_spec, runner)
    except Exception as exc:
        lab_db.update_run_status(run_id, "failed_unknown", str(exc))
        return False

    started_at = time.time()
    while True:
        await asyncio.sleep(_POLL_INTERVAL)
        try:
            sd = await asyncio.to_thread(runner_dispatch.job_status, run_id)
        except Exception:
            if time.time() - started_at > _STALL_KILL_SEC:
                lab_db.update_run_status(run_id, "failed_timeout", "Lost VPS contact")
                return False
            continue

        status = sd.get("status", "running")
        if status == "complete":
            try:
                result = await asyncio.to_thread(runner_dispatch.job_results, run_id)
                kpis = result.get("kpis", {})
                equity_curve = result.get("equity_curve", [])
                daily_pnl    = result.get("daily_pnl", [])
                run_dir = _RESULTS_DIR / run_id
                run_dir.mkdir(parents=True, exist_ok=True)
                eq_path = run_dir / "equity_curve.json"
                dp_path = run_dir / "daily_pnl.json"
                eq_path.write_text(json.dumps(equity_curve, default=str))
                dp_path.write_text(json.dumps(daily_pnl, default=str))
                apply_canonical_sharpe(kpis, daily_pnl)  # consistent daily-√252 Sharpe
                lab_db.update_run_complete(run_id, kpis, {
                    "equity_curve": str(eq_path),
                    "trades": None,
                    "daily_pnl": str(dp_path),
                })
            except Exception as exc:
                lab_db.update_run_status(run_id, "failed_unknown", f"Could not fetch results: {exc}")
                return False
            return True

        if status.startswith("failed"):
            lab_db.update_run_status(run_id, status, sd.get("error") or "")
            return False

        if time.time() - started_at > _STALL_KILL_SEC:
            from services import runner_dispatch as vc
            try:
                await asyncio.to_thread(vc.cancel_job, run_id)
            except Exception:
                pass
            lab_db.update_run_status(run_id, "failed_timeout", "Stalled")
            return False


# ── Walk-forward runner ────────────────────────────────────────────────────────

_NATIVE_WF_STALL_SEC = 3600  # 1 hour


async def _run_native_walk_forward(
    stress_test_id: str,
    st: dict,
    source_run: dict,
    strategy: dict,
) -> bool:
    """
    Drive NT8's built-in Walk Forward mode for a strategy with fixed params.
    One VPS call instead of N orchestrated backtests.
    """
    from services import runner_dispatch
    import numpy as np

    job_id = f"nwf_{stress_test_id}"
    wf_windows = st.get("walk_forward_windows", 5)

    spec = {
        "job_id":             job_id,
        "strategy_class":     strategy["class_name"],
        "instrument":         source_run["instrument"],
        "bar_type":           source_run["bar_type"],
        "bar_value":          source_run["bar_value"],
        "start_date":         source_run["start_date"],
        "end_date":           source_run["end_date"],
        "commission_per_side": source_run["commission_per_side"],
        "slippage_ticks":     source_run["slippage_ticks"],
        "params":             source_run.get("params", {}),
        "wf_windows":         wf_windows,
        "oos_pct":            30,
    }

    try:
        await asyncio.to_thread(runner_dispatch.start_native_walkforward, spec)
    except Exception as exc:
        log.warning("Native WF submit failed for stress_test %s: %s — falling back to serial", stress_test_id, exc)
        return False

    started_at = time.time()
    while True:
        await asyncio.sleep(_POLL_INTERVAL)
        try:
            sd = await asyncio.to_thread(runner_dispatch.job_status, job_id)
        except Exception:
            if time.time() - started_at > _NATIVE_WF_STALL_SEC:
                log.error("Native WF %s lost VPS contact", job_id)
                return False
            continue

        status = sd.get("status", "running")
        if status == "complete":
            break
        if status.startswith("failed"):
            log.warning("Native WF %s failed: %s — falling back to serial", job_id, status)
            return False
        if time.time() - started_at > _NATIVE_WF_STALL_SEC:
            try:
                await asyncio.to_thread(runner_dispatch.cancel_job, job_id)
            except Exception:
                pass
            log.error("Native WF %s timed out", job_id)
            return False

    try:
        result = await asyncio.to_thread(runner_dispatch.native_wf_results, job_id)
    except Exception as exc:
        log.warning("Native WF %s results fetch failed: %s", job_id, exc)
        return False

    windows_raw = result.get("windows", [])
    if not windows_raw:
        return False

    # Pair IS and OOS rows by window number and compute Sharpe degradation.
    by_window: dict[int, dict] = {}
    for row in windows_raw:
        w = row.get("window", 0)
        if w not in by_window:
            by_window[w] = {}
        by_window[w][row.get("type", "")] = row

    summary = []
    degradations = []
    for w_num in sorted(by_window):
        pair = by_window[w_num]
        is_row  = pair.get("is", {})
        oos_row = pair.get("oos", {})
        is_pnl  = is_row.get("net_pnl")
        oos_pnl = oos_row.get("net_pnl")
        # Derive a simple per-window Sharpe proxy from PF (no trade-level data from native WF).
        is_pf  = is_row.get("profit_factor") or 0.0
        oos_pf = oos_row.get("profit_factor") or 0.0
        # IS→OOS degradation on PF (consistent with how cumulative mode uses Sharpe)
        if is_pf > 0:
            degradations.append(max(0.0, 1.0 - oos_pf / is_pf))
        summary.append({
            "window":    w_num,
            "is_pnl":    round(is_pnl, 2) if is_pnl is not None else None,
            "oos_pnl":   round(oos_pnl, 2) if oos_pnl is not None else None,
            "is_pf":     round(is_pf, 4),
            "oos_pf":    round(oos_pf, 4),
            # Sharpe fields expected by the existing WF summary schema
            "is_sharpe":  None,
            "oos_sharpe": None,
        })

    avg_deg = float(np.mean(degradations)) if degradations else 0.0
    lab_db.update_stress_test_walk_forward(stress_test_id, summary, avg_deg)
    return True


async def run_walk_forward_task(stress_test_id: str) -> bool:
    """
    Run walk-forward windows. Uses NT8 native WF mode when the source run comes from
    a native optimization (one data load, all windows); falls back to N orchestrated
    backtests for standalone single runs.
    """
    st = lab_db.get_stress_test(stress_test_id)
    if not st:
        return False

    source_run = lab_db.get_run(st["run_id"])
    if not source_run:
        lab_db.update_stress_test_status(stress_test_id, "failed_no_run")
        return False

    strategy = lab_db.get_strategy(source_run["strategy_id"])
    if not strategy:
        lab_db.update_stress_test_status(stress_test_id, "failed_no_strategy")
        return False

    runner = strategy.get("runner", "ninjatrader")

    # Native WF path: used when source run has optimization_id (winner from native opt).
    if source_run.get("optimization_id") and runner == "ninjatrader":
        return await _run_native_walk_forward(stress_test_id, st, source_run, strategy)

    try:
        windows = _split_windows(
            source_run["start_date"], source_run["end_date"],
            st.get("walk_forward_windows", 5),
        )
    except ValueError as exc:
        lab_db.update_stress_test_status(stress_test_id, "failed_wf_split", str(exc))
        return False

    summary = []
    for w in windows:
        window_data = {"window": w["window"], "is_pnl": None, "oos_pnl": None, "is_sharpe": None, "oos_sharpe": None}

        for period_type, p_start, p_end in [
            ("is",  w["is_start"],  w["is_end"]),
            ("oos", w["oos_start"], w["oos_end"]),
        ]:
            child_id = uuid.uuid4().hex[:16]
            wf_tag = f"wf_{w['window']}_{period_type}"
            lab_db.insert_run_stress_test_child({
                "run_id": child_id,
                "strategy_id": source_run["strategy_id"],
                "instrument": source_run["instrument"],
                "params": source_run.get("params", {}),
                "bar_type": source_run["bar_type"],
                "bar_value": source_run["bar_value"],
                "start_date": p_start,
                "end_date": p_end,
                "commission_per_side": source_run["commission_per_side"],
                "slippage_ticks": source_run["slippage_ticks"],
                "status": "running",
                "created_at": int(time.time()),
                "stress_test_id": stress_test_id,
                "walk_forward_window_id": wf_tag,
                "runner": runner,
            })

            job_spec = {
                "job_id": child_id,
                "strategy_class": strategy["class_name"],
                "instrument": source_run["instrument"],
                "params": source_run.get("params", {}),
                "bar_type": source_run["bar_type"],
                "bar_value": source_run["bar_value"],
                "start_date": p_start,
                "end_date": p_end,
                "commission_per_side": source_run["commission_per_side"],
                "slippage_ticks": source_run["slippage_ticks"],
            }
            ok = await _run_child_backtest(child_id, job_spec, runner)
            if not ok:
                continue  # skip this period if it failed

            child = lab_db.get_run(child_id)
            if not child:
                continue

            eq_path = child.get("equity_curve_path")
            if eq_path and Path(eq_path).exists():
                eq_data = json.loads(Path(eq_path).read_text())
                sharpe = _compute_sharpe(eq_data)
                pnl = child.get("net_pnl") or 0.0
            else:
                sharpe = 0.0
                pnl = child.get("net_pnl") or 0.0

            if period_type == "is":
                window_data["is_pnl"] = round(pnl, 2)
                window_data["is_sharpe"] = round(sharpe, 4)
            else:
                window_data["oos_pnl"] = round(pnl, 2)
                window_data["oos_sharpe"] = round(sharpe, 4)

        summary.append(window_data)

    # Compute avg IS→OOS degradation
    degradations = []
    for w in summary:
        if w.get("is_sharpe") and w["is_sharpe"] != 0:
            deg = 1.0 - (w.get("oos_sharpe") or 0) / w["is_sharpe"]
            degradations.append(deg)
    avg_deg = float(np.mean(degradations)) if degradations else 0.0

    lab_db.update_stress_test_walk_forward(stress_test_id, summary, avg_deg)
    return True


# ── Sensitivity runner ─────────────────────────────────────────────────────────

async def run_sensitivity_task(stress_test_id: str) -> bool:
    """Run ±10%/±25% param perturbations sequentially through NT8. Updates DB when done."""
    st = lab_db.get_stress_test(stress_test_id)
    if not st:
        return False

    source_run = lab_db.get_run(st["run_id"])
    if not source_run:
        return False

    strategy = lab_db.get_strategy(source_run["strategy_id"])
    if not strategy:
        return False

    runner = strategy.get("runner", "ninjatrader")
    base_params: dict = source_run.get("params") or {}
    param_schema: list = strategy.get("param_schema") or []

    if not base_params or not param_schema:
        lab_db.update_stress_test_sensitivity(stress_test_id, {}, 0.0)
        return True

    # Only perturb numeric params
    numeric_params = [
        p for p in param_schema
        if p.get("type") in ("int", "float", "double") and p.get("name") in base_params
    ]

    # Baseline metrics
    baseline_pnl = source_run.get("net_pnl") or 0.0

    # MT5 runs one VPS job at a time — 4 shifts × N params = very long queues.
    # Use 2 shifts for slow runners; ±10% is sufficient to flag parameter sensitivity.
    if runner == "mt5":
        SHIFTS = [("+10%", 1.10), ("-10%", 0.90)]
    else:
        SHIFTS = [("+10%", 1.10), ("-10%", 0.90), ("+25%", 1.25), ("-25%", 0.75)]
    sensitivity: dict = {}
    max_degradation = 0.0

    for param in numeric_params:
        pname = param["name"]
        baseline_val = base_params[pname]
        param_result = {}

        for shift_label, factor in SHIFTS:
            new_val = baseline_val * factor
            # Respect int type
            if param.get("type") == "int":
                new_val = int(round(new_val))

            perturbed_params = {**base_params, pname: new_val}
            child_id = uuid.uuid4().hex[:16]
            sens_tag = f"sens_{pname}_{shift_label}"

            lab_db.insert_run_stress_test_child({
                "run_id": child_id,
                "strategy_id": source_run["strategy_id"],
                "instrument": source_run["instrument"],
                "params": perturbed_params,
                "bar_type": source_run["bar_type"],
                "bar_value": source_run["bar_value"],
                "start_date": source_run["start_date"],
                "end_date": source_run["end_date"],
                "commission_per_side": source_run["commission_per_side"],
                "slippage_ticks": source_run["slippage_ticks"],
                "status": "running",
                "created_at": int(time.time()),
                "stress_test_id": stress_test_id,
                "walk_forward_window_id": sens_tag,
                "runner": runner,
            })

            job_spec = {
                "job_id": child_id,
                "strategy_class": strategy["class_name"],
                "instrument": source_run["instrument"],
                "params": perturbed_params,
                "bar_type": source_run["bar_type"],
                "bar_value": source_run["bar_value"],
                "start_date": source_run["start_date"],
                "end_date": source_run["end_date"],
                "commission_per_side": source_run["commission_per_side"],
                "slippage_ticks": source_run["slippage_ticks"],
            }
            ok = await _run_child_backtest(child_id, job_spec, runner)
            child = lab_db.get_run(child_id) if ok else None
            child_pnl = child.get("net_pnl") or 0.0 if child else 0.0
            pnl_delta = child_pnl - baseline_pnl

            param_result[shift_label] = {
                "run_id": child_id,
                "new_value": new_val,
                "pnl_delta": round(pnl_delta, 2),
                "pnl_delta_pct": round(pnl_delta / abs(baseline_pnl) * 100, 2) if baseline_pnl else 0.0,
            }

            if baseline_pnl and abs(pnl_delta / baseline_pnl) > max_degradation:
                max_degradation = abs(pnl_delta / baseline_pnl)

        sensitivity[pname] = param_result

    lab_db.update_stress_test_sensitivity(stress_test_id, sensitivity, round(max_degradation, 4))
    return True


# ── Grid sensitivity injection (Step 3A) ──────────────────────────────────────

async def _apply_grid_sensitivity_if_available(st: dict, stress_test_id: str) -> bool:
    """
    If the source run came from a native optimization that already has grid sensitivity,
    populate the stress test's sensitivity fields from that data — no NT8 backtests.
    Returns True if sensitivity was applied.
    """
    run = lab_db.get_run(st["run_id"])
    if not run:
        return False
    opt_id = run.get("optimization_id")
    if not opt_id:
        return False
    opt = lab_db.get_optimization(opt_id)
    if not opt:
        return False
    score = opt.get("grid_sensitivity_score")
    summary_raw = opt.get("grid_sensitivity_summary")
    if score is None or summary_raw is None:
        return False

    try:
        import json as _json
        summary = _json.loads(summary_raw) if isinstance(summary_raw, str) else summary_raw
    except Exception:
        return False

    lab_db.update_stress_test_sensitivity(stress_test_id, summary, float(score))
    return True


# ── Telegram grade notification ───────────────────────────────────────────────

def _fire_grade_notification(stress_test_id: str, run: dict, st: dict, grade: str, reasons: list[str]) -> None:
    strategy = lab_db.get_strategy(run.get("strategy_id", ""))
    strat_name = (strategy.get("name") or strategy.get("class_name") or "Unknown") if strategy else "Unknown"
    instrument = run.get("instrument", "?")
    prob_pass  = st.get("prob_pass_eval")
    p1_dd      = st.get("pct1_max_dd")

    lines = [f"*Lab stress test complete*"]
    lines.append(f"Strategy: `{strat_name}` | `{instrument}`")
    lines.append(f"Grade: *{grade}*")
    if prob_pass is not None:
        lines.append(f"Pass probability: {round(prob_pass * 100, 1)}%")
    if p1_dd is not None:
        lines.append(f"Worst-1% drawdown: ${p1_dd:,.0f}")
    if reasons:
        lines.append("Reasons: " + "; ".join(reasons[:3]))

    notify.send_telegram("\n".join(lines))


# ── Main stress test background task ──────────────────────────────────────────

async def run_stress_test_task(
    stress_test_id: str,
    include_walk_forward: bool = False,
    include_sensitivity: bool = False,
) -> None:
    """Background coroutine: MC → (optionally WF → sensitivity) → grade."""
    from services.grading import compute_grade

    try:
        st = lab_db.get_stress_test(stress_test_id)
        if not st:
            return

        run = lab_db.get_run(st["run_id"])
        if not run:
            lab_db.update_stress_test_status(stress_test_id, "failed_no_run", "Source run not found")
            return

        eq_path = run.get("equity_curve_path")
        if not eq_path or not Path(eq_path).exists():
            lab_db.update_stress_test_status(stress_test_id, "failed_no_data", "No equity curve data")
            return

        equity_curve = json.loads(Path(eq_path).read_text())
        trade_pnls = [t["profit"] for t in equity_curve if t.get("profit") is not None]
        if not trade_pnls:
            lab_db.update_stress_test_status(stress_test_id, "failed_no_trades", "No trades in equity curve")
            return

        ruleset = lab_db.get_ruleset(st["ruleset_id"]) if st.get("ruleset_id") else None

        # ── Monte Carlo ──
        mc = await asyncio.to_thread(
            run_monte_carlo, trade_pnls, ruleset,
            st.get("num_simulations", 10_000),
            st.get("num_bootstrap", 1_000),
        )

        st_dir = _RESULTS_DIR / stress_test_id
        st_dir.mkdir(parents=True, exist_ok=True)
        paths_file = st_dir / "equity_paths.json"
        dist_file  = st_dir / "distribution.json"
        paths_file.write_text(json.dumps(mc.pop("sampled_paths"), default=str))
        dist_file.write_text(json.dumps(mc.pop("distribution"), default=str))

        lab_db.update_stress_test_mc(stress_test_id, mc, {
            "equity_paths_path": str(paths_file),
            "distribution_path": str(dist_file),
        })

        # ── Step 3A: inject grid sensitivity if available (no NT8 backtests) ──
        grid_sens_applied = False
        if not include_sensitivity:
            grid_sens_applied = await _apply_grid_sensitivity_if_available(st, stress_test_id)

        if not include_walk_forward and not include_sensitivity:
            # MC-only (or MC + grid sensitivity): compute grade
            st_updated = lab_db.get_stress_test(stress_test_id)
            if st_updated and ruleset:
                sens_summary = st_updated.get("sensitivity_summary") if grid_sens_applied else None
                grade, reasons = compute_grade(st_updated, None, sens_summary, ruleset)
                lab_db.update_stress_test_grade(stress_test_id, grade, reasons)
                _fire_grade_notification(stress_test_id, run, st_updated, grade, reasons)
            return

        # ── Walk-forward ──
        if include_walk_forward:
            lab_db.update_stress_test_status(stress_test_id, "running_wf")
            await run_walk_forward_task(stress_test_id)

        # ── Sensitivity (NT8 perturbation backtests) ──
        if include_sensitivity and not grid_sens_applied:
            lab_db.update_stress_test_status(stress_test_id, "running_sens")
            await run_sensitivity_task(stress_test_id)

        # ── Grade ──
        st_updated = lab_db.get_stress_test(stress_test_id)
        if st_updated and ruleset:
            has_sens = include_sensitivity or grid_sens_applied
            grade, reasons = compute_grade(
                st_updated,
                st_updated.get("walk_forward_summary") if include_walk_forward else None,
                st_updated.get("sensitivity_summary") if has_sens else None,
                ruleset,
            )
            lab_db.update_stress_test_grade(stress_test_id, grade, reasons)
            _fire_grade_notification(stress_test_id, run, st_updated, grade, reasons)
        else:
            lab_db.update_stress_test_status(stress_test_id, "complete")

    except Exception as exc:
        lab_db.update_stress_test_status(stress_test_id, "failed_error", str(exc))


# ── Auto-trigger (called by backtest_runner and optimization_runner) ───────────

async def trigger_auto_stress_test(run_id: str, ruleset_ids: list[str]) -> None:
    """MC-only auto-trigger after Tier 1 backtest or optimizer winner."""
    primary_ruleset_id = None
    if ruleset_ids:
        candidates = [lab_db.get_ruleset(rid) for rid in ruleset_ids]
        candidates = [r for r in candidates if r]
        if candidates:
            primary = min(candidates, key=lambda r: r.get("max_loss_eod") or float("inf"))
            primary_ruleset_id = primary["id"]

    st_id = uuid.uuid4().hex[:16]
    lab_db.insert_stress_test({
        "stress_test_id": st_id,
        "run_id": run_id,
        "ruleset_id": primary_ruleset_id,
        "status": "running",
        "created_at": int(time.time()),
    })
    # Fire and forget (no walk-forward for auto-triggers — MC only)
    asyncio.create_task(run_stress_test_task(st_id, False, False))
