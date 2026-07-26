"""
Backtests router — /backtests/*
"""

from __future__ import annotations

import asyncio
import json
import re
import shutil
import time
import uuid
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, HTTPException, Response
from fastapi.responses import PlainTextResponse
from pydantic import BaseModel

from models import (
    BacktestRunRequest, BacktestSummary, BacktestDetail, EvaluationDetail,
    WorthinessScore, RunningJobStatus, RunningJobInfo, RetryRunRequest, RunNewsReport,
    HistoryLimit,
)
from services import lab_db, runner_dispatch, chart_spec, news_filter, history_limits
from services.backtest_runner import (
    run_backtest_job, read_progress, clear_progress, LAB_RESULTS_DIR, parse_trades_csv,
)
from services.evaluator import evaluate_run
from services.metrics import compute_regime_breakdown
from services.sweep_runner import retry_single_sweep_run
from services.optimization_runner import retry_single_optimization_run, resolve_opt_eval_rulesets
from routers._locks import ensure_platform_idle

router = APIRouter(prefix="/backtests", tags=["backtests"])

# Backtest window dates are plain ISO days everywhere (DB, job specs, both agents)
_DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")


# ── Helpers ────────────────────────────────────────────────────────────────────

def _load_json(path: Optional[str]) -> list:
    if not path:
        return []
    try:
        return json.loads(Path(path).read_text())
    except Exception:
        return []


def _worthiness_from_row(row: dict) -> Optional[WorthinessScore]:
    if not row.get("worthiness_tier"):
        return None
    return WorthinessScore(
        tier=row["worthiness_tier"],
        reason=row.get("worthiness_reason"),
        computed_against_firm=row.get("worthiness_computed_against_firm"),
    )


def _row_to_summary(row: dict) -> BacktestSummary:
    return BacktestSummary(
        run_id=row["run_id"],
        strategy_id=row["strategy_id"],
        strategy_name=row.get("strategy_name", ""),
        instrument=row["instrument"],
        status=row["status"],
        created_at=row["created_at"],
        started_at=row.get("started_at"),
        completed_at=row.get("completed_at"),
        net_pnl=row.get("net_pnl"),
        max_drawdown=row.get("max_drawdown"),
        profit_factor=row.get("profit_factor"),
        win_rate=row.get("win_rate"),
        trade_count=row.get("trade_count"),
        verdicts=lab_db.get_run_verdict_summary(row["run_id"]),
        worthiness=_worthiness_from_row(row),
        sweep_id=row.get("sweep_id"),
        optimization_id=row.get("optimization_id"),
        source_run_id=row.get("source_run_id"),
        sharpe=row.get("sharpe"),
        params=row.get("params") or {},
        error_message=row.get("error_message"),
        start_date=row.get("start_date"),
        end_date=row.get("end_date"),
        runner=row.get("runner", "ninjatrader"),
    )


def _row_to_detail(row: dict) -> BacktestDetail:
    # Per-ruleset sized results (sized runs only) — each firm's own KPIs, sized daily P&L
    # and sized timeline, keyed by ruleset id. Empty on unit-size runs (file absent).
    ruleset_sizing = _load_json(str(LAB_RESULTS_DIR / row["run_id"] / "ruleset_sizing.json")) or {}
    evals = [
        EvaluationDetail(
            eval_id=e["eval_id"],
            ruleset_id=e["ruleset_id"],
            ruleset_name=e["ruleset_name"],
            net_pnl=(ruleset_sizing.get(e["ruleset_id"], {}).get("kpis") or {}).get("net_pnl"),
            max_drawdown=(ruleset_sizing.get(e["ruleset_id"], {}).get("kpis") or {}).get("max_drawdown"),
            profit_factor=(ruleset_sizing.get(e["ruleset_id"], {}).get("kpis") or {}).get("profit_factor"),
            win_rate=(ruleset_sizing.get(e["ruleset_id"], {}).get("kpis") or {}).get("win_rate"),
            trade_count=(ruleset_sizing.get(e["ruleset_id"], {}).get("kpis") or {}).get("trade_count"),
            avg_win=(ruleset_sizing.get(e["ruleset_id"], {}).get("kpis") or {}).get("avg_win"),
            avg_loss=(ruleset_sizing.get(e["ruleset_id"], {}).get("kpis") or {}).get("avg_loss"),
            daily_pnl=ruleset_sizing.get(e["ruleset_id"], {}).get("daily_pnl") or [],
            sized_timeline=ruleset_sizing.get(e["ruleset_id"], {}).get("timeline") or [],
            equity_curve=ruleset_sizing.get(e["ruleset_id"], {}).get("equity_curve") or [],
            verdict=e["verdict"],
            drawdown_pass=bool(e["drawdown_pass"]),
            target_pass=bool(e["target_pass"]),
            consistency_pass=(
                bool(e["consistency_pass"])
                if e.get("consistency_pass") is not None
                else None
            ),
            simulated_eval_days=e.get("simulated_eval_days"),
            breach_count=e["breach_count"],
            largest_day_share_pct=e.get("largest_day_share_pct"),
            adjusted_profit_target=e.get("adjusted_profit_target"),
            contract_cap_status=e.get("contract_cap_status"),
            mll_final_floor=e.get("mll_final_floor"),
            mll_highest_eod_balance=e.get("mll_highest_eod_balance"),
            mll_breach_day=e.get("mll_breach_day"),
            mll_min_floor_distance=e.get("mll_min_floor_distance"),
            firm_max_loss_eod=e["firm_max_loss_eod"],
            firm_profit_target=e["firm_profit_target"],
            firm_consistency_pct=e.get("firm_consistency_pct"),
            ruleset_type=e.get("ruleset_type") or "prop_eval",
            personal_daily_loss_cap=e.get("personal_daily_loss_cap"),
            personal_max_drawdown_from_peak_pct=e.get("personal_max_drawdown_from_peak_pct"),
            personal_max_consecutive_loss_days=e.get("personal_max_consecutive_loss_days"),
            notes=e.get("notes"),
        )
        for e in lab_db.get_evaluations(row["run_id"])
    ]

    equity_curve = _load_json(row.get("equity_curve_path"))
    daily_pnl = _load_json(row.get("daily_pnl_path"))

    # The sized run's day-by-day engine record (present only when a reshaped strategy
    # emitted engine_trades and the engine sized the run). Its existence IS the `sized`
    # marker — load once and derive the flag from it rather than stat-ing the file twice.
    sized_timeline = _load_json(str(LAB_RESULTS_DIR / row["run_id"] / "engine_timeline.json"))

    # Full-calendar regime labels — every trading day in the window, written at run completion.
    # Absent on runs that finished before it existed; the charts degrade to daily_pnl's tags.
    regime_timeline = _load_json(str(LAB_RESULTS_DIR / row["run_id"] / "regime_timeline.json")) or []

    return BacktestDetail(
        run_id=row["run_id"],
        strategy_id=row["strategy_id"],
        strategy_name=row.get("strategy_name", ""),
        instrument=row["instrument"],
        params=row.get("params", {}),
        bar_type=row["bar_type"],
        bar_value=row["bar_value"],
        start_date=row["start_date"],
        end_date=row["end_date"],
        commission_per_side=row["commission_per_side"],
        slippage_ticks=row["slippage_ticks"],
        status=row["status"],
        error_message=row.get("error_message"),
        created_at=row["created_at"],
        started_at=row.get("started_at"),
        completed_at=row.get("completed_at"),
        net_pnl=row.get("net_pnl"),
        max_drawdown=row.get("max_drawdown"),
        profit_factor=row.get("profit_factor"),
        win_rate=row.get("win_rate"),
        win_count=row.get("win_count"),
        trade_count=row.get("trade_count"),
        sharpe=row.get("sharpe"),
        platform_sharpe=row.get("platform_sharpe"),
        sharpe_low_sample=bool(row.get("sharpe_low_sample")),
        profit_concentration_pct=row.get("profit_concentration_pct"),
        sortino=row.get("sortino"),
        cagr=row.get("cagr"),
        avg_win=row.get("avg_win"),
        avg_loss=row.get("avg_loss"),
        avg_trade_duration_min=row.get("avg_trade_duration_min"),
        worst_day_pnl=row.get("worst_day_pnl"),
        worst_losing_streak=row.get("worst_losing_streak"),
        equity_curve=equity_curve,
        daily_pnl=daily_pnl,
        regime_timeline=regime_timeline,
        regime_breakdown=compute_regime_breakdown(equity_curve, daily_pnl, row.get("trade_count")),
        evaluations=evals,
        worthiness=_worthiness_from_row(row),
        sweep_id=row.get("sweep_id"),
        optimization_id=row.get("optimization_id"),
        source_run_id=row.get("source_run_id"),
        runner=row.get("runner", "ninjatrader"),
        sizing_mode=row.get("sizing_mode", "consistent"),
        manual_risk_pct=row.get("manual_risk_pct"),
        sized=bool(sized_timeline),
        sized_timeline=sized_timeline,
    )


# ── Endpoints ─────────────────────────────────────────────────────────────────

@router.get("/running-job", response_model=RunningJobStatus)
def get_running_job() -> RunningJobStatus:
    jobs = lab_db.get_running_job()
    return RunningJobStatus(
        nt8=RunningJobInfo(**jobs["nt8"]),
        mt5=RunningJobInfo(**jobs["mt5"]),
    )


@router.get("/history-limit", response_model=Optional[HistoryLimit])
def get_history_limit(
    instrument: str,
    bar_type: str = "Minute",
    bar_value: int = 15,
    runner: str = "python",
    refresh: bool = False,
) -> Optional[HistoryLimit]:
    """The earliest date a backtest of this shape may start, or null if unbounded.

    MEASURED off the live terminal and cached per broker — swap the terminal to a broker
    with deeper history and this widens by itself. The date picker reads this instead of
    hardcoding a date, so the UI minimum and the data layer's refusal can never drift
    apart. Null = unknown (every non-python runner, an unreachable agent, or an instrument
    on a broker we cannot identify) — the UI then leaves the range open, because refusing
    on a guess would be worse than letting the data layer's spacing check catch it.

    `refresh=true` re-probes (~15s) — use after a broker back-fills history.
    """
    lim = history_limits.limits_for(instrument, bar_type, bar_value, runner, refresh=refresh)
    return HistoryLimit(**lim) if lim else None


@router.get("/runs")
def list_backtest_runs(
    strategy_id: Optional[str] = None,
    ruleset_id:  Optional[str] = None,
    firm_id:     Optional[str] = None,  # backward-compat alias
    status:      Optional[str] = None,
) -> list[BacktestSummary]:
    effective_ruleset_id = ruleset_id or firm_id
    rows = lab_db.list_runs(strategy_id=strategy_id, ruleset_id=effective_ruleset_id, status=status)
    return [_row_to_summary(r) for r in rows]


@router.get("/runs/{run_id}")
def get_backtest_run(run_id: str) -> BacktestDetail:
    row = lab_db.get_run(run_id)
    if not row:
        raise HTTPException(404, "Run not found")
    return _row_to_detail(row)


@router.get("/runs/{run_id}/news", response_model=RunNewsReport)
def get_run_news(
    run_id: str,
    pre: int = news_filter.NEWS_PRE_DEFAULT,
    post: int = news_filter.NEWS_POST_DEFAULT,
) -> RunNewsReport:
    """Tag this run's trades against the economic calendar so the UI can remove news-window and
    bank-holiday trades and recompute KPIs/charts live. Pure post-processing off the stored equity
    curve — no VPS re-run. `pre`/`post` are the block window in minutes (default 15/30); slide them
    and re-call to re-tag. A trade with no stored entry time (old run) comes back untagged."""
    row = lab_db.get_run(run_id)
    if not row:
        raise HTTPException(404, "Run not found")
    equity_curve = _load_json(row.get("equity_curve_path"))
    trades = [{"index": p.get("index"), "entry_ms": p.get("entry_ms")} for p in equity_curve]
    report = news_filter.build_report(trades, pre_minutes=max(0, pre), post_minutes=max(0, post))
    return RunNewsReport(**report)


@router.get("/runs/{run_id}/log", response_class=PlainTextResponse)
def get_run_log(run_id: str, lines: int = 200) -> str:
    if not lab_db.get_run(run_id):
        raise HTTPException(404, "Run not found")
    return runner_dispatch.job_log(run_id, lines=lines)


@router.post("/run", status_code=202)
async def trigger_backtest(req: BacktestRunRequest) -> dict:
    strategy = lab_db.get_strategy(req.strategy_id)
    if not strategy:
        raise HTTPException(404, f"Strategy '{req.strategy_id}' not found")

    ruleset_ids = req.ruleset_ids
    for rid in ruleset_ids:
        if not lab_db.get_ruleset(rid):
            raise HTTPException(404, f"Ruleset '{rid}' not found")

    runner = strategy.get("runner", "ninjatrader")

    # Refuse a window the broker has no real bars for BEFORE taking the lock or inserting
    # a row. MT5 answers a too-early request with coarser bars mislabelled as the
    # timeframe asked for, so this would otherwise complete as a plausible fiction.
    try:
        history_limits.validate_window(
            req.instrument, req.start_date, req.end_date,
            req.bar_type, req.bar_value, runner,
        )
    except ValueError as exc:
        raise HTTPException(400, str(exc))

    ensure_platform_idle(runner)

    run_id = uuid.uuid4().hex[:12]
    job_id = run_id

    # Inject foundational config from primary ruleset (first in evaluate list).
    # Merged params are stored in the DB so retries pick them up without re-injection.
    # NinjaScript-only: foundational params map to [Category("Foundational")] properties
    # that MT5/MQL5 strategies don't have, so never inject for the mt5 runner — a forex run
    # now carries a (personal) ruleset for evaluation, but its config must not be injected.
    # `python` is excluded for the same reason: a Python strategy's config is a dataclass with
    # a fixed field set, so an injected AccountSize/EarliestEntryTimeET is not a field it has —
    # it would be a TypeError at construction, not a silently ignored input.
    primary_ruleset = (
        lab_db.get_ruleset(ruleset_ids[0])
        if ruleset_ids and runner not in ("mt5", "python")
        else None
    )
    merged_params = runner_dispatch.inject_foundational(req.params, primary_ruleset)

    lab_db.insert_run({
        "run_id":             run_id,
        "strategy_id":        req.strategy_id,
        "instrument":         req.instrument,
        "params":             merged_params,
        "bar_type":           req.bar_type,
        "bar_value":          req.bar_value,
        "start_date":         req.start_date,
        "end_date":           req.end_date,
        "commission_per_side": req.commission_per_side,
        "slippage_ticks":     req.slippage_ticks,
        "status":             "running",
        "created_at":         int(time.time()),
        "evaluate_rulesets":  ruleset_ids,
        "runner":             runner,
        "source_run_id":      req.source_run_id,
        "sizing_mode":        req.sizing_mode,
        "manual_risk_pct":    req.manual_risk_pct,
    })

    job_spec = {
        "job_id":            job_id,
        "strategy_class":    strategy["class_name"],
        "instrument":        req.instrument,
        "params":            merged_params,
        "bar_type":          req.bar_type,
        "bar_value":         req.bar_value,
        "start_date":        req.start_date,
        "end_date":          req.end_date,
        "commission_per_side": req.commission_per_side,
        "slippage_ticks":    req.slippage_ticks,
    }

    try:
        await asyncio.to_thread(runner_dispatch.start_backtest, job_spec, runner)
    except Exception as exc:
        lab_db.update_run_status(run_id, "failed_unknown", str(exc))
        raise HTTPException(502, f"VPS agent unreachable: {exc}")

    asyncio.create_task(
        run_backtest_job(run_id, job_id, req.strategy_id, req.instrument, ruleset_ids, runner)
    )

    return {"run_id": run_id, "status": "started"}


@router.post("/runs/{run_id}/stop", status_code=200)
async def stop_backtest_run(run_id: str) -> dict:
    row = lab_db.get_run(run_id)
    if not row:
        raise HTTPException(404, "Run not found")
    if row["status"] != "running":
        raise HTTPException(400, f"Run is not running (status: {row['status']})")

    progress = read_progress()
    job_id   = progress.get("job_id") or run_id

    try:
        await asyncio.to_thread(runner_dispatch.cancel_job, job_id)
    except Exception:
        pass  # best-effort — still mark cancelled locally

    lab_db.update_run_status(run_id, "failed_cancelled", "Cancelled by user")
    clear_progress()
    return {"run_id": run_id, "status": "failed_cancelled"}


@router.post("/runs/{run_id}/retry", status_code=202)
async def retry_backtest_run(run_id: str, body: Optional[RetryRunRequest] = None) -> dict:
    row = lab_db.get_run(run_id)
    if not row:
        raise HTTPException(404, "Run not found")
    if row["status"] == "running":
        raise HTTPException(409, "Run is still in progress")

    # runner is not set on some legacy child rows — derive from the strategy
    strategy = lab_db.get_strategy(row["strategy_id"])
    runner = row.get("runner") or (strategy or {}).get("runner", "ninjatrader")

    # Optional period override (standalone runs only — see below)
    new_start = (body.start_date or "").strip() if body else ""
    new_end = (body.end_date or "").strip() if body else ""
    period_override = bool(new_start or new_end)
    if period_override:
        if not (new_start and new_end):
            raise HTTPException(400, "Both start_date and end_date are required to change the period")
        if not (_DATE_RE.match(new_start) and _DATE_RE.match(new_end)):
            raise HTTPException(400, "Dates must be YYYY-MM-DD")
        if new_start >= new_end:
            raise HTTPException(400, "start_date must be before end_date")
        # A sweep/optimization child shares one period with every sibling in its set — moving
        # one of them would make the comparison meaningless. Reject rather than silently ignore.
        if row.get("sweep_id") or row.get("optimization_id"):
            raise HTTPException(400, "The period can only be changed on a standalone run")
        # Same broker-history floor the initial trigger enforces — a rerun is a new window.
        try:
            history_limits.validate_window(
                row["instrument"], new_start, new_end,
                row.get("bar_type", "Minute"), row.get("bar_value", 15), runner,
            )
        except ValueError as exc:
            raise HTTPException(400, str(exc))

    # A retry reuses the run_id, so the failed attempt's progress entry — error text and all — is
    # still filed under it and the live banner would render that error while the rerun ran. Wipe it
    # here rather than waiting for the new attempt's first update. Only when the entry is OURS: the
    # progress file is shared across runners, and this run is not running (checked above), so its
    # entry is stale by definition while another platform's may be live.
    if read_progress().get("job_id") == run_id:
        clear_progress()

    # Sweep run — reset in place and re-fire via sweep runner
    if row.get("sweep_id"):
        ensure_platform_idle(runner)
        lab_db.reset_run_for_retry(run_id)
        asyncio.create_task(retry_single_sweep_run(run_id))
        return {"run_id": run_id, "status": "running"}

    # Optimization combo — re-fire as a full backtest. It needs a ruleset to be scored
    # against: prefer the user's explicit choice, else inherit from the optimization, else
    # ask the UI to prompt (status="needs_ruleset", no run started).
    if row.get("optimization_id"):
        explicit = body.evaluate_rulesets if body else None
        if explicit is not None:
            rulesets = explicit
        else:
            opt = lab_db.get_optimization(row["optimization_id"])
            rulesets = resolve_opt_eval_rulesets(opt) if opt else []
            if not rulesets:
                # Nothing inheritable and no explicit choice — the UI prompts, then re-fires
                # with body.evaluate_rulesets. Returned as 202; the caller keys off this status.
                return {"run_id": run_id, "status": "needs_ruleset"}
        ensure_platform_idle(runner)
        lab_db.reset_run_for_retry(run_id)
        lab_db.delete_run_evaluations(run_id)
        asyncio.create_task(retry_single_optimization_run(run_id, evaluate_rulesets=rulesets))
        return {"run_id": run_id, "status": "running"}

    # Standalone run — reset the existing record in place and re-fire
    if not strategy:
        raise HTTPException(404, f"Strategy '{row['strategy_id']}' not found")

    ensure_platform_idle(runner)

    evaluate_rulesets = row.get("evaluate_firms") or []

    # A rerun over a new window: persist it before firing so the row (and the detail page's
    # period chip) describes the result the runner is about to produce.
    if period_override:
        lab_db.update_run_period(run_id, new_start, new_end)
        row["start_date"], row["end_date"] = new_start, new_end

    # Reset the existing row (clears status, error, completed_at, worthiness)
    lab_db.reset_run_for_retry(run_id)
    lab_db.delete_run_evaluations(run_id)

    # Clear stale report files so the UI starts fresh
    run_dir = Path(LAB_RESULTS_DIR) / run_id
    for fname in ("equity_curve.json", "daily_pnl.json"):
        p = run_dir / fname
        if p.exists():
            p.unlink()

    job_spec = {
        "job_id":            run_id,
        "strategy_class":    strategy["class_name"],
        "instrument":        row["instrument"],
        "params":            row["params"],
        "bar_type":          row["bar_type"],
        "bar_value":         row["bar_value"],
        "start_date":        row["start_date"],
        "end_date":          row["end_date"],
        "commission_per_side": row["commission_per_side"],
        "slippage_ticks":    row["slippage_ticks"],
    }

    try:
        await asyncio.to_thread(runner_dispatch.start_backtest, job_spec, runner)
    except Exception as exc:
        lab_db.update_run_status(run_id, "failed_unknown", str(exc))
        raise HTTPException(502, f"VPS agent unreachable: {exc}")

    asyncio.create_task(
        run_backtest_job(run_id, run_id, row["strategy_id"], row["instrument"], evaluate_rulesets, runner)
    )

    return {"run_id": run_id, "status": "running"}


@router.delete("/runs/{run_id}", status_code=204)
def delete_backtest_run(run_id: str) -> Response:
    deleted_ids = lab_db.delete_run(run_id)
    if not deleted_ids:
        raise HTTPException(404, "Run not found")
    # Remove the on-disk report dir for the run AND every child run that cascaded
    # (optimization/sweep/stress-test children) so no orphan folders are left behind.
    for rid in deleted_ids:
        run_dir = LAB_RESULTS_DIR / rid
        if run_dir.exists():
            shutil.rmtree(run_dir)
    return Response(status_code=204)


@router.post("/runs/{run_id}/reload-charts")
async def reload_charts(run_id: str) -> dict:
    """Re-export trades from NT8 SA and repopulate equity_curve + daily_pnl for a run."""
    row = lab_db.get_run(run_id)
    if not row:
        raise HTTPException(404, "Run not found")
    if row["status"] != "complete":
        raise HTTPException(409, f"Run status is '{row['status']}' — can only reload charts for completed runs")

    try:
        export = await asyncio.to_thread(runner_dispatch.export_trades)
    except Exception as exc:
        raise HTTPException(502, f"VPS agent error: {exc}")

    csv_text = export.get("csv", "")
    if not csv_text:
        raise HTTPException(502, "VPS agent returned no CSV data")

    equity_curve, daily_pnl = parse_trades_csv(csv_text)

    run_dir = LAB_RESULTS_DIR / run_id
    run_dir.mkdir(parents=True, exist_ok=True)
    eq_path  = run_dir / "equity_curve.json"
    dpnl_path = run_dir / "daily_pnl.json"
    eq_path.write_text(json.dumps(equity_curve))
    dpnl_path.write_text(json.dumps(daily_pnl))

    lab_db.update_run_chart_paths(run_id, {
        "equity_curve": str(eq_path),
        "daily_pnl":    str(dpnl_path),
    })

    return {"equity_points": len(equity_curve), "daily_bars": len(daily_pnl)}


@router.get("/runs/{run_id}/chart-spec")
async def get_chart_spec(run_id: str, refresh: bool = False) -> dict:
    """ChartSpec for the price-chart panel — candles + sessions + trades (Phase 7a).

    Returns the camelCase contract the frontend ChartPanel reads (the one place the backend
    emits camelCase, since the shape is defined by the chart, not a DB model). Built lazily and
    cached to the run dir; `refresh=true` rebuilds. Candle fetch is backgrounded (network I/O)."""
    spec = await asyncio.to_thread(chart_spec.build_chart_spec, run_id, refresh)
    if spec is None:
        raise HTTPException(404, "Run not found")
    return spec


@router.get("/runs/{run_id}/candles")
async def get_run_candles(run_id: str, tf: str, from_ms: int, to_ms: int) -> dict:
    """Candles for a bounded [from_ms, to_ms] window at an arbitrary timeframe — the chart's
    drill-down data path (e.g. 1m under a 15m run, to see a trade's exact entry).

    Pulls from the run's OWN feed/runner (same bars the run traded). `available: false` with an
    empty `candles` list means the feed can't serve that window — most often 1m older than the
    broker's ~35-day 1m history. Backgrounded (network I/O)."""
    out = await asyncio.to_thread(chart_spec.build_run_candles, run_id, tf, from_ms, to_ms)
    if out is None:
        raise HTTPException(404, "Run not found")
    return out
