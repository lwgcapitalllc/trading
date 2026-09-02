"""
Backtests router — /backtests/*
"""

from __future__ import annotations

import asyncio
import json
import logging
import re
import shutil
import time
import uuid
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, HTTPException, Query, Response
from fastapi.responses import JSONResponse, PlainTextResponse
from models import (
    BacktestDetail,
    BacktestRunRequest,
    BacktestSummary,
    BrokerProfile,
    EvaluationDetail,
    HistoryLimit,
    RepricedPoint,
    RetryRunRequest,
    RunNewsReport,
    RunningJobInfo,
    RunningJobStatus,
    RunRepriceReport,
    WorthinessScore,
)
from services import (
    chart_spec,
    history_limits,
    lab_db,
    mt5_agent_client,
    news_filter,
    python_runner,
    run_feeds,
    runner_dispatch,
)
from services.backtest_runner import (
    LAB_RESULTS_DIR,
    clear_progress,
    parse_trades_csv,
    read_progress,
    run_backtest_job,
)
from services.metrics import compute_regime_breakdown
from services.optimization_runner import resolve_opt_eval_rulesets, retry_single_optimization_run
from services.sweep_runner import retry_single_sweep_run

from routers import _costs
from routers._locks import ensure_platform_idle
from routers._source_guard import refuse_if_needs_source

log = logging.getLogger(__name__)

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


def _clear_run_dir(run_id: str) -> None:
    """Delete every derived artefact of a run that is about to be re-run.

    A run directory holds nothing but output — the equity curve, the daily P&L, the cached
    `chart_spec.json`, the blocked/missed setup lists, the regime calendar, and the sizing
    engine's timeline. All of it describes the attempt that just ended, so all of it has to go
    before the next one starts; anything left behind is served to the page as the NEW run's
    result. The directory itself is recreated by `_handle_complete`.
    """
    run_dir = Path(LAB_RESULTS_DIR) / run_id
    if run_dir.exists():
        shutil.rmtree(run_dir, ignore_errors=True)


def _json_list(raw) -> Optional[list]:
    """A stored JSON list, or None when the column was never written.

    None and `[]` are DIFFERENT answers for `cost_layers` — "this run predates layers" vs
    "this run deliberately charged nothing" — so a missing column must not collapse to empty.
    A malformed value reads as None: unknown, which is the honest answer and the one the page
    already knows how to caption."""
    if raw is None or raw == "":
        return None
    if isinstance(raw, list):
        return raw
    try:
        parsed = json.loads(raw)
    except Exception:
        return None
    return parsed if isinstance(parsed, list) else None


def _worthiness_from_row(row: dict) -> Optional[WorthinessScore]:
    if not row.get("worthiness_tier"):
        return None
    return WorthinessScore(
        tier=row["worthiness_tier"],
        reason=row.get("worthiness_reason"),
        computed_against_firm=row.get("worthiness_computed_against_firm"),
    )


def _row_to_summary(row: dict, verdicts: Optional[list[dict]] = None) -> BacktestSummary:
    # `verdicts=None` means "fetch it yourself" — kept for the single-row callers. The LIST path
    # passes them in from one bulk query; see `list_backtest_runs`.
    if verdicts is None:
        verdicts = lab_db.get_run_verdict_summary(row["run_id"])
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
        max_drawdown_pct=row.get("max_drawdown_pct"),
        profit_factor=row.get("profit_factor"),
        win_rate=row.get("win_rate"),
        trade_count=row.get("trade_count"),
        verdicts=verdicts,
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


def _row_to_detail(row: dict, *, include_timeline: bool = True) -> BacktestDetail:
    # Per-ruleset sized results (sized runs only) — each firm's own KPIs, sized daily P&L
    # and sized timeline, keyed by ruleset id. Empty on unit-size runs (file absent).
    ruleset_sizing = _load_json(str(LAB_RESULTS_DIR / row["run_id"] / "ruleset_sizing.json")) or {}
    evals = [
        EvaluationDetail(
            eval_id=e["eval_id"],
            ruleset_id=e["ruleset_id"],
            ruleset_name=e["ruleset_name"],
            net_pnl=(ruleset_sizing.get(e["ruleset_id"], {}).get("kpis") or {}).get("net_pnl"),
            max_drawdown=(ruleset_sizing.get(e["ruleset_id"], {}).get("kpis") or {}).get(
                "max_drawdown"
            ),
            profit_factor=(ruleset_sizing.get(e["ruleset_id"], {}).get("kpis") or {}).get(
                "profit_factor"
            ),
            win_rate=(ruleset_sizing.get(e["ruleset_id"], {}).get("kpis") or {}).get("win_rate"),
            trade_count=(ruleset_sizing.get(e["ruleset_id"], {}).get("kpis") or {}).get(
                "trade_count"
            ),
            avg_win=(ruleset_sizing.get(e["ruleset_id"], {}).get("kpis") or {}).get("avg_win"),
            avg_loss=(ruleset_sizing.get(e["ruleset_id"], {}).get("kpis") or {}).get("avg_loss"),
            daily_pnl=ruleset_sizing.get(e["ruleset_id"], {}).get("daily_pnl") or [],
            sized_timeline=ruleset_sizing.get(e["ruleset_id"], {}).get("timeline") or [],
            equity_curve=ruleset_sizing.get(e["ruleset_id"], {}).get("equity_curve") or [],
            verdict=e["verdict"],
            drawdown_pass=bool(e["drawdown_pass"]),
            target_pass=bool(e["target_pass"]),
            consistency_pass=(
                bool(e["consistency_pass"]) if e.get("consistency_pass") is not None else None
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
    #
    # ⚠ `include_timeline=False` returns `[]`, which is INDISTINGUISHABLE from a run that has no
    # timeline — so it is only safe for a caller that already holds the timeline it needs from
    # somewhere else and is asking for this run's other fields. It is the single biggest slice of
    # this payload (measured: 96 KB of 137 KB on a 165-trade run) and it is identical for every run
    # over the same window, so the tuning workbench fetches it once and slims the rest. Do NOT
    # default it to False, and do NOT cache a slimmed response under the same key as a full one.
    regime_timeline = (
        _load_json(str(LAB_RESULTS_DIR / row["run_id"] / "regime_timeline.json")) or []
        if include_timeline
        else []
    )

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
        cost_layers=_json_list(row.get("cost_layers")),
        broker_profile=row.get("broker_profile"),
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
        max_drawdown_pct=row.get("max_drawdown_pct"),
        scratch_count=row.get("scratch_count"),
        trade_concentration_pct=row.get("trade_concentration_pct"),
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
    """Which of the three independent lock scopes is busy, and with what.

    🔴 **This endpoint named `nt8` and `mt5` and silently dropped `python` (fixed 2026-08-06).**
    Every other layer of that scope was built and correct — `lab_db.get_running_job` computes it,
    `RunningJobStatus` DECLARES it, `lib/runner.ts` resolves it and `runningJobFor` reads it — and
    the response never carried the field, so Pydantic filled in the declared default,
    `running=False`. **A python backtest therefore reported its platform free for its entire run.**
    The GATE was never affected (`ensure_platform_idle` reads `has_running_job`, which was right,
    and a second run really was refused with a 409) — so nothing could double-run. What broke is
    every control the UI gates on this: the Runs list's Rerun, the detail page's Retry and Rerun,
    the Run modal, the Optimize button. All of them stayed enabled through a python run and could
    only ever produce a 409 toast, which is a button whose single outcome is an error.

    ⚠ **The response is DERIVED from the scope map, never restated field by field.** Naming the
    keys is what let one go missing, and the default on the model is what made it silent — this is
    the `entry_ms` / `favorable` / `is_trades` trap arriving from the opposite direction: not a
    field the model failed to declare, but a declared field the constructor failed to fill, whose
    default is the most reassuring answer available. A fourth scope added to `_SCOPE_RUNNER_SQL`
    now reaches the API by construction.
    """
    jobs = lab_db.get_running_job()
    return RunningJobStatus(**{scope: RunningJobInfo(**info) for scope, info in jobs.items()})


@router.get("/broker-profiles", response_model=list[BrokerProfile])
def list_broker_profiles() -> list[BrokerProfile]:
    """The account profiles a python run can charge its costs from, with their MEASURED numbers.

    This endpoint exists so the Run modal never retypes a spread. Every number here was measured
    (`backtest/fills.py` records the tick counts and the Specification window behind each), and a
    figure copied into a form is a second claim that can silently disagree with the one actually
    charged — the failure this lab has now hit three times. The UI displays what the run will be
    billed, because it is reading the same object the runner bills from.
    """
    from backtest.fills import PROFILES

    # Which terminal the lab is actually attached to, so the page can say whether the costs it is
    # about to charge belong to the broker whose bars it is about to replay.
    # ⚠ **An unreachable agent yields NO attachment, never a default one.** "Cannot ask" and "the
    # usual broker" must not take the same value — rule 1 — so every profile comes back
    # `attached: False` and the page says it cannot tell rather than blessing one.
    attached_server, attached_account = "", None
    try:
        st = mt5_agent_client.status()
        if st.get("mt5_connected") is True:
            attached_server = str(st.get("server") or "")
            attached_account = st.get("account")
    except Exception:  # noqa: BLE001 - any failure means "cannot ask"
        attached_server, attached_account = "", None

    def _is_attached(p) -> bool:
        """Does this profile describe the attached terminal?

        ⚠ **The ACCOUNT decides it whenever both sides have one**, because the SERVER cannot: PU
        Prime's Prime and ECN logins share `PUPrime-Demo`, and blessing a tier on the server alone
        would hand a run ECN's $0.12 spread while it sat on Prime — the exact 2.7x error the
        unmeasured-spread sentinel exists to prevent, arriving through the front door.
        ⚠ **A blank on EITHER side is "cannot tell", never a match.**
        """
        if not attached_server or not p.server or p.server != attached_server:
            return False
        if p.account is not None and attached_account is not None:
            return int(p.account) == int(attached_account)
        # Server matches and nobody can narrow it further. That is an honest maybe, and the page
        # renders it as one — never as a confirmed match.
        return p.account is None and attached_account is None

    return [
        BrokerProfile(
            id=key,
            spread=p.spread,
            commission_per_side_per_lot=p.commission_per_side_per_lot,
            server=p.server,
            account=p.account,
            symbol_suffix=p.symbol_suffix,
            attached=_is_attached(p),
            swap_long_points=p.swap.swap_long_points if p.swap else None,
            swap_short_points=p.swap.swap_short_points if p.swap else None,
            contract_size=p.contract_size,
        )
        for key, p in sorted(PROFILES.items())
    ]


@router.get("/history-limit", response_model=Optional[HistoryLimit])
def get_history_limit(
    instrument: str,
    bar_type: str = "Minute",
    bar_value: int = 15,
    runner: str = "python",
    refresh: bool = False,
    flags: Optional[list[str]] = Query(default=None),
    pv: Optional[list[str]] = Query(default=None),
) -> Optional[HistoryLimit]:
    """The earliest date a backtest of this shape may start, or null if unbounded.

    MEASURED off the live terminal and cached per broker — swap the terminal to a broker
    with deeper history and this widens by itself. The date picker reads this instead of
    hardcoding a date, so the UI minimum and the data layer's refusal can never drift
    apart. Null = unknown (every non-python runner, an unreachable agent, or an instrument
    on a broker we cannot identify) — the UI then leaves the range open, because refusing
    on a guess would be worse than letting the data layer's spacing check catch it.

    `flags` = the names of the run's params that are switched ON. A run can load more than
    its chart timeframe (`exec_secondary` adds a second feed) and each feed has its own
    floor, so the answer depends on the params, not just the timeframe. The UI sends every
    truthy param name and `run_feeds` keeps the ones that mean a feed — so the frontend never
    carries its own copy of that list, which is what would drift.

    `pv` = the same idea for NUMBERS, as `name:value` pairs, added 2026-09-01. A feed's
    timeframe can come from a run param (`exec_sec_fill_tf_min`), and a flag alone would have
    bounded every run at the DEFAULT while the run itself loaded something else — the
    2026-08-15 defect one level down. Same rule as `flags`: the UI sends what it holds and
    this keeps only what a feed reads.

    ⚠ Omitting `flags` answers the CHART-ONLY question, which is a real question and a
    dangerous default: it is what shipped a floor one day too early on run `50331c7cbe96`.

    `refresh=true` re-probes (~15s) — use after a broker back-fills history.
    """
    lim = history_limits.limits_for(
        instrument,
        bar_type,
        bar_value,
        runner,
        refresh=refresh,
        params=run_feeds.feeds_from_flags(flags, pv),
    )
    return HistoryLimit(**lim) if lim else None


@router.get("/runs")
def list_backtest_runs(
    strategy_id: Optional[str] = None,
    ruleset_id: Optional[str] = None,
    firm_id: Optional[str] = None,  # backward-compat alias
    status: Optional[str] = None,
    source_run_id: Optional[str] = None,
) -> list[BacktestSummary]:
    effective_ruleset_id = ruleset_id or firm_id
    rows = lab_db.list_runs(
        strategy_id=strategy_id,
        ruleset_id=effective_ruleset_id,
        status=status,
        source_run_id=source_run_id,
    )
    # ONE query for every row's verdicts, not one per row — see get_run_verdict_summaries.
    verdicts = lab_db.get_run_verdict_summaries([r["run_id"] for r in rows])
    return [_row_to_summary(r, verdicts.get(r["run_id"], [])) for r in rows]


@router.get("/runs/{run_id}")
def get_backtest_run(run_id: str, timeline: bool = True) -> BacktestDetail:
    """`timeline=false` drops `regime_timeline` from the response — see `_row_to_detail`. The
    default is True so no existing caller changes shape; only a caller that already has the
    timeline may ask for it to be left out."""
    row = lab_db.get_run(run_id)
    if not row:
        raise HTTPException(404, "Run not found")
    return _row_to_detail(row, include_timeline=timeline)


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


@router.get("/runs/{run_id}/repriced", response_model=RunRepriceReport)
def get_run_repriced(run_id: str, layers: str = "", broker: str = "") -> RunRepriceReport:
    """Re-price this run's stored trades at `layers`, so the detail page can switch costs on and
    off without re-running. Pure post-processing off the stored equity curve — no replay, no VPS.

    `layers` is a comma-separated subset of `backtest.reprice.REPRICEABLE_LAYERS`; empty means
    charge nothing, which reproduces the run exactly as stored. `broker` defaults to the profile
    the run was made against, so a re-price is billed at the same measured facts the run was.

    ⚠ **Layers that cannot be re-priced are REPORTED, never silently dropped.** `bid_ask_fills`
    changes which setups fill, and `slippage` depends on which exits were market orders — neither
    is recoverable from a trade list, so both come back in `needs_rerun` for the UI to say so. A
    400 would be wrong here: the caller asked a reasonable question and the honest answer is "that
    one needs a re-run", not a failure.
    """
    from backtest.fills import PROFILES
    from backtest.reprice import REPRICEABLE_LAYERS, RepriceError, reprice_curve

    row = lab_db.get_run(run_id)
    if not row:
        raise HTTPException(404, "Run not found")

    # ⚠ **A layer the RUN already charged must never be charged again here.** The stored trades were
    # measured with it baked in, so re-pricing it on top bills one cost twice — and nothing
    # downstream can tell, because the result is a plausible number rather than an error. `[]` and
    # `None` both mean "charged none of these" (the second is a row predating the layers), so the
    # distinction the rest of the lab keeps does not matter at this seam.
    # ⚠ Through `_json_list`, NEVER `set(row["cost_layers"])` — the column is stored as raw JSON
    # TEXT, so setting the string directly iterates its CHARACTERS and every layer name silently
    # fails to match while `'s'`, `'p'`, `'r'`… all appear to be charged.
    already = set(_json_list(row.get("cost_layers")) or [])
    # 🔴 **`bid_ask_fills` IMPLIES `spread`, and forgetting that here DOUBLE-BILLS a spread.**
    # A run that transacted at the ask has already paid it — in the fills themselves rather than as
    # a line item — so `spread` is absent from its stored layer list while being fully charged. The
    # naive membership test then reports it as available, and ticking it adds a second flat charge
    # on top of a book that already carries one. Nothing downstream can tell: the result is a
    # plausible number, which is this repo's most expensive failure shape.
    # ⚠ It became reachable on 2026-08-24, when the charged default made `bid_ask_fills` the
    # ordinary case rather than a layer nobody ticked. The same implication is stated in
    # `python_runner._cost_profile`; this is the READING side of it.
    if "bid_ask_fills" in already:
        already.add("spread")
    wanted = [l.strip() for l in layers.split(",") if l.strip()]
    # Reported off the RUN, not off what the caller ticked, because the UI has to render those rows
    # as already-on whether or not anyone asked for them — a row that looks available and does
    # nothing when clicked is the failure this replaces.
    already_charged = [l for l in REPRICEABLE_LAYERS if l in already]
    priceable = [l for l in wanted if l in REPRICEABLE_LAYERS and l not in already]
    needs_rerun = [l for l in wanted if l not in REPRICEABLE_LAYERS and l not in already]

    broker_id = broker or row.get("broker_profile") or "vantage_demo"
    if broker_id not in PROFILES:
        raise HTTPException(400, f"Unknown broker profile '{broker_id}'")
    profile = PROFILES[broker_id]

    curve = _load_json(row.get("equity_curve_path"))
    if not curve:
        raise HTTPException(400, "This run stored no equity curve, so it cannot be re-priced")

    # The starting balance is not a stored column — recover it from the curve's own first point,
    # which is exact arithmetic (`equity` is cumulative and anchored on it) rather than a guess at
    # a default deposit. Getting it wrong rescales every dollar on the page while leaving R right.
    first = curve[0]
    initial = float(first.get("equity", 0.0)) - float(first.get("profit", 0.0))

    try:
        out = reprice_curve(curve, profile=profile, layers=priceable, initial_capital=initial)
        # Every layer's own price, whether or not it is currently ticked — the same discipline the
        # news filter's rows follow, so you can see what turning one on would cost before you turn
        # it on. In **R**, because that is the additive unit: a layer's DOLLAR cost depends on which
        # other layers are on (they change the balance, which changes every later position's size),
        # so three per-layer dollar figures would not sum to the total shown beneath them.
        # A layer the run already charged is priced at 0.0 rather than at what it WOULD cost —
        # the honest answer to "what does turning this on cost from here" is nothing, because it
        # is already on. Quoting its price would invite exactly the double charge refused above.
        per_layer = {
            l: (
                0.0
                if l in already
                else reprice_curve(
                    curve, profile=profile, layers=[l], initial_capital=initial
                ).total_cost_r
            )
            for l in REPRICEABLE_LAYERS
        }
    except RepriceError as exc:
        raise HTTPException(400, str(exc))

    return RunRepriceReport(
        layers=list(out.layers),
        broker_profile=broker_id,
        is_exact=out.is_exact,
        derived_basis=out.derived_basis,
        approximate_layers=list(out.approximate_layers),
        needs_rerun=needs_rerun,
        already_charged=already_charged,
        initial_capital=out.initial_capital,
        final_equity=out.final_equity,
        sum_r=out.sum_r,
        total_cost_usd=out.total_cost_usd,
        total_cost_r=out.total_cost_r,
        layer_cost_r=per_layer,
        trades=[
            RepricedPoint(
                index=t.index,
                equity=round(t.equity, 2),
                profit=round(t.profit, 2),
                r=round(t.r, 6),
                r_before=round(t.r_before, 6),
                cost_usd=round(t.cost_usd, 2),
            )
            for t in out.trades
        ],
    )


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

    # A rule with no setups of its own cannot be run alone — it would return an empty book
    # that reads as "found nothing". See routers/_source_guard.py.
    refuse_if_needs_source(strategy)

    ruleset_ids = req.ruleset_ids
    for rid in ruleset_ids:
        if not lab_db.get_ruleset(rid):
            raise HTTPException(404, f"Ruleset '{rid}' not found")

    runner = strategy.get("runner", "ninjatrader")

    # ── The symbol: the strategy states the base, the BROKER states the suffix ───────────
    # 🔴 Resolved at creation, exactly like the costs below, and for the same reason (rule 3):
    # the row must record what the run was actually MEASURED on. PU Prime quotes gold as
    # `XAUUSD.p` and Vantage quotes it bare, so a strategy's suggested `XAUUSD` is right on one
    # broker and unanswerable on the other — and until 2026-08-26 that mismatch surfaced only as
    # *"the agent returned no bars"* four chunks deep, with nothing naming the symbol as the cause.
    # ⚠ PYTHON-ONLY, same as the cost switch below. NT8 and MT5 route through their own agents and
    # have no broker profile to resolve against, so their instrument stays exactly as sent.
    # ⚠ A broker whose symbol naming was never recorded leaves the name exactly as typed — see
    # `python_runner.run_symbol`.
    # ⚠ **It resolves BEFORE the history floor check below, not after.** That check is per
    # BROKER and per SYMBOL, so asking it about the typed name would clear a window for a
    # symbol this run is never going to load — a green check about the wrong thing.
    instrument = (
        python_runner.run_symbol(req.instrument, req.broker_profile)
        if runner == "python"
        else req.instrument
    )

    # Refuse a window the broker has no real bars for BEFORE taking the lock or inserting
    # a row. MT5 answers a too-early request with coarser bars mislabelled as the
    # timeframe asked for, so this would otherwise complete as a plausible fiction.
    # `params` is REQUIRED here, not decoration: a run with `exec_secondary` on also loads
    # 1m, whose floor is later, and checking the chart alone is what let run `50331c7cbe96`
    # through to die at 8%.
    try:
        history_limits.validate_window(
            instrument,
            req.start_date,
            req.end_date,
            req.bar_type,
            req.bar_value,
            runner,
            params=req.params or {},
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

    # ── Costs: one switch, resolved HERE so the row records what was CHARGED ─────────────
    # What this run is CHARGED. Resolved by `routers/_costs.py`, which the stack path calls too —
    # the rules, and why they are shared rather than copied, are in that module's docstring.
    cost_layers, commission_per_side = _costs.resolve_costs(
        runner=runner,
        charge_costs=req.charge_costs,
        broker_profile=req.broker_profile,
        cost_layers=req.cost_layers,
        commission_per_side=req.commission_per_side,
        slippage_ticks=req.slippage_ticks,
        # The strategy decides which of the SPREAD's two models it can be charged under — see
        # `_costs`. Omitting it charges the moved-fill model to a strategy that refuses one at
        # construction, which is a job that dies seconds in under a switch saying costs are on.
        strategies=[strategy],
    )

    lab_db.insert_run(
        {
            "run_id": run_id,
            "strategy_id": req.strategy_id,
            "instrument": instrument,
            "params": merged_params,
            "bar_type": req.bar_type,
            "bar_value": req.bar_value,
            "start_date": req.start_date,
            "end_date": req.end_date,
            "commission_per_side": commission_per_side,
            "slippage_ticks": req.slippage_ticks,
            "status": "running",
            "created_at": int(time.time()),
            "evaluate_rulesets": ruleset_ids,
            "runner": runner,
            "source_run_id": req.source_run_id,
            "sizing_mode": req.sizing_mode,
            "manual_risk_pct": req.manual_risk_pct,
            "cost_layers": cost_layers,
            "broker_profile": req.broker_profile,
        }
    )

    job_spec = {
        "job_id": job_id,
        "strategy_class": strategy["class_name"],
        "instrument": instrument,
        "params": merged_params,
        "bar_type": req.bar_type,
        "bar_value": req.bar_value,
        "start_date": req.start_date,
        "end_date": req.end_date,
        "commission_per_side": commission_per_side,
        "slippage_ticks": req.slippage_ticks,
        "cost_layers": cost_layers,
        "broker_profile": req.broker_profile,
    }

    try:
        await asyncio.to_thread(runner_dispatch.start_backtest, job_spec, runner)
    except Exception as exc:
        lab_db.update_run_status(run_id, "failed_unknown", str(exc))
        raise HTTPException(502, f"VPS agent unreachable: {exc}")

    asyncio.create_task(
        run_backtest_job(run_id, job_id, req.strategy_id, instrument, ruleset_ids, runner)
    )

    return {"run_id": run_id, "status": "started"}


@router.post("/runs/{run_id}/stop", status_code=200)
async def stop_backtest_run(run_id: str) -> dict:
    row = lab_db.get_run(run_id)
    if not row:
        raise HTTPException(404, "Run not found")
    if row["status"] != "running":
        raise HTTPException(400, f"Run is not running (status: {row['status']})")

    # 🔴 The job id IS the run id for every backtest this app starts (see trigger_backtest, which
    # sets `job_id = run_id`). It used to be read out of `lab_progress.json` — ONE file shared by
    # every runner — so the id cancelled here was whatever had most recently written progress.
    # With two platforms busy that is the OTHER platform's job; with a stale file it is a job that
    # no longer exists. Either way the failure was swallowed, this run was marked cancelled, its
    # platform lock released, and the real job kept running.
    job_id = run_id
    runner = row.get("runner") or "ninjatrader"

    # Mark FIRST, cancel second: `backtest_runner.run_backtest_job` reads this row every poll and
    # stands down when it is no longer `running`. Doing it the other way round leaves a window in
    # which the job finishes and writes `complete` over the cancellation.
    lab_db.update_run_status(run_id, "failed_cancelled", "Cancelled by user")

    job_stopped = True
    try:
        await asyncio.to_thread(runner_dispatch.cancel_job, job_id, runner)
    except Exception as exc:  # noqa: BLE001 — the row is cancelled regardless
        job_stopped = False
        log.warning("stop %s: could not reach the %s runner to cancel: %s", run_id, runner, exc)

    # Only clear progress if the entry is OURS. The file is shared, and blanking another
    # platform's live progress would blank the banner of a run nobody asked to stop.
    if read_progress().get("job_id") == run_id:
        clear_progress()

    # `job_stopped` is reported separately on purpose: the row is cancelled either way, but
    # "the runner acknowledged" and "we could not tell it" are different facts, and only the
    # first means the machine is actually free. Same contract as the optimizer's cancel.
    return {"run_id": run_id, "status": "failed_cancelled", "job_stopped": job_stopped}


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
            raise HTTPException(
                400, "Both start_date and end_date are required to change the period"
            )
        if not (_DATE_RE.match(new_start) and _DATE_RE.match(new_end)):
            raise HTTPException(400, "Dates must be YYYY-MM-DD")
        if new_start >= new_end:
            raise HTTPException(400, "start_date must be before end_date")
        # A sweep/optimization child shares one period with every sibling in its set — moving
        # one of them would make the comparison meaningless. Reject rather than silently ignore.
        if row.get("sweep_id") or row.get("optimization_id"):
            raise HTTPException(400, "The period can only be changed on a standalone run")
        # Same broker-history floor the initial trigger enforces — a rerun is a new window.
        # The STORED params decide which feeds this run loads, so they are what the floor is
        # measured against; checking the chart timeframe alone is what made Retry unable to
        # fix run `50331c7cbe96` (its `exec_secondary` needs 1m, whose history starts a day
        # later) — the modal offered the same illegal date and the rerun failed identically.
        try:
            history_limits.validate_window(
                row["instrument"],
                new_start,
                new_end,
                row.get("bar_type", "Minute"),
                row.get("bar_value", 15),
                runner,
                params=row.get("params") or {},
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
        _clear_run_dir(run_id)
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
        _clear_run_dir(run_id)
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

    # Clear stale report files so the UI starts fresh.
    #
    # 🔴 This used to delete `equity_curve.json` and `daily_pnl.json` only, and every OTHER
    # artefact a run produces survived into the next attempt. The consequences were not stale
    # numbers — they were the PREVIOUS run's data rendered as this one's: `chart_spec.json` is
    # cached, so the Price tab drew the old candles and the old trades until somebody clicked
    # Reload charts; `blocked_setups.json` / `missed_setups.json` are written only when non-empty,
    # so the old refusals stayed on the chart; `regime_timeline.json` described the old window on
    # a rerun over a new one; and `engine_timeline.json` kept `sized` true on a run that no longer
    # was. Wipe the directory — everything in it is derived from the run and the run is restarting.
    _clear_run_dir(run_id)

    job_spec = {
        "job_id": run_id,
        "strategy_class": strategy["class_name"],
        "instrument": row["instrument"],
        "params": row["params"],
        "bar_type": row["bar_type"],
        "bar_value": row["bar_value"],
        "start_date": row["start_date"],
        "end_date": row["end_date"],
        "commission_per_side": row["commission_per_side"],
        "slippage_ticks": row["slippage_ticks"],
        # Read back off the ROW, so a retry re-prices exactly as the original run did. NULL stays
        # NULL here on purpose — a pre-layer run must retry on the pre-layer contract.
        "cost_layers": _json_list(row.get("cost_layers")),
        "broker_profile": row.get("broker_profile"),
    }

    try:
        await asyncio.to_thread(runner_dispatch.start_backtest, job_spec, runner)
    except Exception as exc:
        lab_db.update_run_status(run_id, "failed_unknown", str(exc))
        raise HTTPException(502, f"VPS agent unreachable: {exc}")

    asyncio.create_task(
        run_backtest_job(
            run_id, run_id, row["strategy_id"], row["instrument"], evaluate_rulesets, runner
        )
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
        raise HTTPException(
            409, f"Run status is '{row['status']}' — can only reload charts for completed runs"
        )

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
    eq_path = run_dir / "equity_curve.json"
    dpnl_path = run_dir / "daily_pnl.json"
    eq_path.write_text(json.dumps(equity_curve))
    dpnl_path.write_text(json.dumps(daily_pnl))

    lab_db.update_run_chart_paths(
        run_id,
        {
            "equity_curve": str(eq_path),
            "daily_pnl": str(dpnl_path),
        },
    )

    return {"equity_points": len(equity_curve), "daily_bars": len(daily_pnl)}


@router.get("/runs/{run_id}/chart-spec")
async def get_chart_spec(run_id: str, refresh: bool = False) -> Response:
    """ChartSpec for the price-chart panel — candles + sessions + trades (Phase 7a).

    Returns the camelCase contract the frontend ChartPanel reads (the one place the backend
    emits camelCase, since the shape is defined by the chart, not a DB model). Built lazily and
    cached to the run dir; `refresh=true` rebuilds. Candle fetch is backgrounded (network I/O).

    **A warm cache is streamed as BYTES, never as a dict.** Returning a dict makes FastAPI
    `json.dumps` a structure this function had just `json.loads`ed off disk — MEASURED at 0.089s +
    0.171s of the endpoint's 0.40s on a real 4 MB spec, for a round trip whose output is
    byte-equivalent to its input. See `chart_spec.cached_chart_spec_bytes`.

    ⚠ **The 404 must be decided by the DB, not by the cache being absent.** A real run that has
    simply never had its spec built is the normal first-open case, and answering 404 there would
    report a healthy run as missing — so a cache miss falls through to the build, which is the only
    thing that can tell an unbuilt spec from an unknown run."""
    if not refresh:
        cached = await asyncio.to_thread(chart_spec.cached_chart_spec_bytes, run_id)
        if cached is not None:
            return Response(content=cached, media_type="application/json")
    spec = await asyncio.to_thread(chart_spec.build_chart_spec, run_id, refresh)
    if spec is None:
        raise HTTPException(404, "Run not found")
    return JSONResponse(content=spec)


@router.get("/runs/{run_id}/candles")
async def get_run_candles(run_id: str, tf: str, from_ms: int, to_ms: int) -> dict:
    """Candles for a bounded [from_ms, to_ms] window at an arbitrary timeframe — the chart's
    DRILL-DOWN data path (e.g. 1m under a 15m run, to see a trade's exact entry).

    Pulls from the run's OWN feed/runner (same bars the run traded). `available: false` with an
    empty `candles` list means the feed can't serve that window — most often 1m older than the
    broker's ~35-day 1m history. Backgrounded (network I/O).

    ⚠ **The `analysis=true` parameter was DELETED on 2026-08-06 along with the scroll-left paging
    path it served.** The ChartSpec carries the whole run now, so the panel pages from memory and
    no window needs its own analysis — see `chart_spec.build_run_candles`."""
    out = await asyncio.to_thread(chart_spec.build_run_candles, run_id, tf, from_ms, to_ms)
    if out is None:
        raise HTTPException(404, "Run not found")
    return out
