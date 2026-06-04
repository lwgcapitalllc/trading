"""
Pydantic models — the data contract between backend and frontend.
These shapes are authoritative. Pipeline outputs conform to this; not the reverse.
"""

from __future__ import annotations
from datetime import datetime
from typing import Optional
from pydantic import BaseModel, field_validator


# ── Shared ────────────────────────────────────────────────────────────────────

class MonthlyPoint(BaseModel):
    month: str          # e.g. "2025-01"
    value: float


class RankedItem(BaseModel):
    label: str
    count: int
    win_rate: Optional[float] = None


class EquityPoint(BaseModel):
    index: int
    equity: float
    date: Optional[str] = None
    direction: Optional[str] = None   # 'Long' | 'Short'
    profit: Optional[float] = None
    exit_name: Optional[str] = None


class JobStatus(BaseModel):
    name: str
    schedule: str
    status: str         # "RUNNING" | "STOPPED" | "UNKNOWN"


class ProcessStatus(BaseModel):
    name: str
    status: str         # "RUNNING" | "STOPPED" | "UNKNOWN"


# ── Smart Money ───────────────────────────────────────────────────────────────

class FunnelStage(BaseModel):
    label: str
    count_in: int
    count_out: int


class SmartMoneyRun(BaseModel):
    run_id: str
    generated_at: datetime
    total_scanned: int
    total_qualified: int
    by_market: dict[str, int]
    by_source: dict[str, int]
    funnel: list[FunnelStage]


class SmartMoneyRunSummary(BaseModel):
    run_id: str
    generated_at: datetime
    total_qualified: int


class SmartMoneyConfig(BaseModel):
    # qualification thresholds
    min_trades: int
    min_win_rate_pct: float
    max_drawdown_pct: float
    min_active_weeks_per_month: int
    max_single_trade_pnl_share_pct: float
    max_avg_hold_hours: float
    min_account_age_days: int
    # lookback tiers (days) — must be ordered min <= preferred <= elite
    lookback_min_days: int
    lookback_preferred_days: int
    lookback_elite_days: int
    # scoring weights — MUST sum to 100
    weight_winrate_consistency: float
    weight_risk_adjusted_return: float
    weight_exit_efficiency: float
    weight_trade_frequency: float
    weight_instrument_consistency: float
    # strike rules
    strike_months_to_yellow: int
    strike_months_to_disqualify: int
    strike_months_to_reinstate: int

    @field_validator("min_win_rate_pct", "max_drawdown_pct", "max_single_trade_pnl_share_pct")
    @classmethod
    def pct_range(cls, v: float) -> float:
        if not (0 <= v <= 100):
            raise ValueError("Percentage must be between 0 and 100")
        return v

    @field_validator("min_trades", "min_active_weeks_per_month", "min_account_age_days",
                     "lookback_min_days", "lookback_preferred_days", "lookback_elite_days",
                     "strike_months_to_yellow", "strike_months_to_disqualify",
                     "strike_months_to_reinstate")
    @classmethod
    def positive_int(cls, v: int) -> int:
        if v < 1:
            raise ValueError("Must be a positive integer")
        return v

    @field_validator("max_avg_hold_hours")
    @classmethod
    def positive_float(cls, v: float) -> float:
        if v <= 0:
            raise ValueError("Must be positive")
        return v


class ConfigGitStatus(BaseModel):
    file_path: str
    is_dirty: bool
    last_commit_hash: Optional[str] = None
    last_commit_message: Optional[str] = None
    last_commit_at: Optional[datetime] = None


class Candidate(BaseModel):
    rank: int
    id: str                                 # wallet address
    market: str                             # "crypto" | "forex"
    source: str                             # "hyperliquid" | "myfxbook" | ...
    composite_score: float
    lookback_tier: Optional[str] = None
    lookback_span_days: Optional[int] = None
    score_breakdown: dict[str, float]
    # leaderboard stats (real values from exchange, not synthetic)
    account_value: Optional[float] = None
    all_time_pnl: Optional[float] = None
    all_time_roi: Optional[float] = None    # fractional, e.g. 3.9 = 390%
    month_roi: Optional[float] = None
    week_roi: Optional[float] = None
    # pnl from our fill analysis window
    cum_pnl_usd: float = 0.0
    monthly_balance: list[MonthlyPoint]
    # performance
    overall_win_rate: float
    monthly_win_rate: list[MonthlyPoint]
    win_rate_trend: str                     # "improving" | "stable" | "declining"
    avg_win: float
    avg_loss: float
    avg_rr: Optional[float] = None
    peak_drawdown: float
    trade_count: int
    # behavioral
    preferred_days: list[RankedItem]
    preferred_instruments: list[RankedItem]
    typical_entry_hour_utc: Optional[int] = None
    avg_hold_time_hours: Optional[float] = None
    exit_efficiency: Optional[float] = None
    # flags
    yellow_flag_count: int = 0
    window_count: int = 0
    windows_below_threshold: int = 0
    is_shortlist: bool = False


class RunProgress(BaseModel):
    run_id: str
    status: str                             # "idle" | "running" | "complete" | "error"
    stage: int
    stage_name: str
    phase: str
    pct: int
    wallets_scanned: int
    wallets_total: int
    qualified_so_far: int
    disqualified_so_far: int
    message: str
    started_at: Optional[str] = None
    updated_at: Optional[str] = None
    elapsed_seconds: float = 0.0
    recent_addresses: list[dict] = []      # [{a: address, s: "pass"|"fail"}, ...]


class DisqualifiedCandidate(BaseModel):
    id: str
    market: str
    source: str
    reason: str
    stage: str


# ── Bots ─────────────────────────────────────────────────────────────────────

class BotStatus(BaseModel):
    name: str
    account: str
    account_type: str       # "demo" | "live"
    balance: Optional[float] = None
    status: str             # "RUNNING" | "STOPPED" | "ERROR"
    uptime_seconds: Optional[int] = None
    total_pnl_pct: Optional[float] = None
    day_locked: bool = False
    # ── Detail fields (populated from bot_state.json) ─────────────────────────
    daily_pnl: Optional[float] = None
    daily_pnl_pct: Optional[float] = None
    weekly_pnl: Optional[float] = None
    weekly_pnl_pct: Optional[float] = None
    peak_balance: Optional[float] = None
    trades_today: Optional[int] = None
    lock_reason: Optional[str] = None
    last_updated: Optional[str] = None
    daily_goal_pct: Optional[float] = None
    daily_cap_pct: Optional[float] = None
    weekly_cap_pct: Optional[float] = None


class BotSnapshot(BaseModel):
    fetched_at: datetime
    bots: list[BotStatus]
    scheduled_jobs: list[JobStatus]
    telegram: ProcessStatus


class BotConfigSections(BaseModel):
    risk: dict = {}
    protection: dict = {}
    strategy: dict = {}
    regime: dict = {}
    dead_zone: dict = {}


class BotConfigUpdate(BaseModel):
    risk: Optional[dict] = None
    protection: Optional[dict] = None
    strategy: Optional[dict] = None
    regime: Optional[dict] = None
    dead_zone: Optional[dict] = None
    deploy: bool = False


class BotCapUpdate(BaseModel):
    daily_goal_pct: float
    daily_cap_pct: float
    weekly_cap_pct: float


class TelegramUser(BaseModel):
    chat_id: str
    name: str
    role: str           # "admin" | "readonly"
    added: str          # YYYY-MM-DD


class TelegramUserCreate(BaseModel):
    chat_id: str
    name: str
    role: str


class TelegramUserRoleUpdate(BaseModel):
    role: str


# ── Lab — strategies ──────────────────────────────────────────────────────────

class Strategy(BaseModel):
    id: str
    name: str
    class_name: str
    source_path: str
    category: Optional[str] = None
    suggested_instrument: Optional[str] = None
    default_params: dict = {}
    param_schema: list[dict] = []          # [{name, type, min?, max?, default, group, display_name}]
    scanned_at: datetime
    run_count: int = 0
    runner: str = "ninjatrader"


class ScanResult(BaseModel):
    scanned: int
    added: int
    updated: int
    skipped: int


# ── Lab — rulesets ────────────────────────────────────────────────────────────

class Ruleset(BaseModel):
    id: str
    name: str
    account_size: int
    profit_target: int
    max_loss_eod: int
    max_loss_intraday: Optional[int] = None
    drawdown_type: str
    consistency_pct: Optional[float] = None
    min_trading_days: Optional[int] = None
    force_flat_time_et: Optional[str] = None
    allowed_instruments: list[str] = []
    max_contracts: dict = {}
    platform_support: list[str] = []
    account_tier: str = "eval"          # "eval" | "funded" | "live"
    ruleset_type: str = "prop_eval"     # "prop_eval" | "prop_funded" | "personal" | "demo"
    daily_loss_cap: Optional[int] = None
    weekly_loss_cap: Optional[int] = None
    daily_profit_goal: Optional[int] = None
    description: Optional[str] = None
    docs_url: Optional[str] = None
    eval_cost_usd: Optional[int] = None
    activation_fee_usd: Optional[int] = None
    profit_split_pct: Optional[float] = None
    notes: Optional[str] = None
    # Pass 1 — foundational config fields
    risk_per_trade_pct: Optional[float] = None
    max_consecutive_losses: Optional[int] = None
    earliest_entry_time_et: Optional[str] = None
    latest_entry_time_et: Optional[str] = None
    days_of_week_allowed: list[str] = []
    daily_profit_target: Optional[int] = None
    daily_profit_lock_pct: Optional[float] = None
    default_commission_per_side: Optional[float] = None
    default_slippage_ticks: Optional[int] = None
    daily_halt_fraction: Optional[float] = None


class RulesetCreate(BaseModel):
    id: str
    name: str
    account_size: int
    profit_target: int
    max_loss_eod: int
    max_loss_intraday: Optional[int] = None
    drawdown_type: str = "eod"
    consistency_pct: Optional[float] = None
    min_trading_days: Optional[int] = None
    force_flat_time_et: Optional[str] = None
    allowed_instruments: list[str] = []
    max_contracts: dict = {}
    platform_support: list[str] = []
    account_tier: str = "eval"          # "eval" | "funded" | "live"
    ruleset_type: str = "prop_eval"     # "prop_eval" | "prop_funded" | "personal" | "demo"
    daily_loss_cap: Optional[int] = None
    weekly_loss_cap: Optional[int] = None
    daily_profit_goal: Optional[int] = None
    description: Optional[str] = None
    docs_url: Optional[str] = None
    eval_cost_usd: Optional[int] = None
    activation_fee_usd: Optional[int] = None
    profit_split_pct: Optional[float] = None
    notes: Optional[str] = None
    # Pass 1 — foundational config fields
    risk_per_trade_pct: Optional[float] = None
    max_consecutive_losses: Optional[int] = None
    earliest_entry_time_et: Optional[str] = None
    latest_entry_time_et: Optional[str] = None
    days_of_week_allowed: list[str] = []
    daily_profit_target: Optional[int] = None
    daily_profit_lock_pct: Optional[float] = None
    default_commission_per_side: Optional[float] = None
    default_slippage_ticks: Optional[int] = None
    daily_halt_fraction: Optional[float] = None


# Backward-compat aliases — used in M3 only; removed in M4
Firm = Ruleset
FirmCreate = RulesetCreate


# ── Lab — worthiness scoring ──────────────────────────────────────────────────

class WorthinessScore(BaseModel):
    tier: str                               # "TIER_1_STRESS_TEST" | "TIER_2_OPTIMIZE" | "TIER_3_DISCARD"
    reason: Optional[str] = None
    computed_against_firm: Optional[str] = None


# ── Lab — backtest runs ───────────────────────────────────────────────────────

class BacktestRunRequest(BaseModel):
    strategy_id: str
    instrument: str
    params: dict
    bar_type: str = "Minute"
    bar_value: int = 5
    start_date: str                 # 'YYYY-MM-DD'
    end_date: str
    commission_per_side: float = 2.25
    slippage_ticks: int = 1
    evaluate_rulesets: list[str] = []   # ruleset_ids to evaluate against
    evaluate_firms: list[str] = []      # backward-compat alias; prefer evaluate_rulesets

    @property
    def ruleset_ids(self) -> list[str]:
        return self.evaluate_rulesets or self.evaluate_firms


class BacktestSummary(BaseModel):
    run_id: str
    strategy_id: str
    strategy_name: str
    instrument: str
    status: str
    created_at: datetime
    completed_at: Optional[datetime] = None
    net_pnl: Optional[float] = None
    max_drawdown: Optional[float] = None
    profit_factor: Optional[float] = None
    win_rate: Optional[float] = None
    trade_count: Optional[int] = None
    sharpe: Optional[float] = None
    params: dict = {}
    verdicts: list[dict] = []       # [{firm_id, verdict, notes}]
    worthiness: Optional[WorthinessScore] = None
    sweep_id: Optional[str] = None
    optimization_id: Optional[str] = None
    error_message: Optional[str] = None
    start_date: Optional[str] = None
    end_date: Optional[str] = None


class EvaluationDetail(BaseModel):
    eval_id: str
    ruleset_id: str
    ruleset_name: str
    verdict: str                    # 'PASS' | 'WARN' | 'DISCARD'
    drawdown_pass: bool
    target_pass: bool
    consistency_pass: Optional[bool] = None
    simulated_eval_days: Optional[int] = None
    breach_count: int
    largest_day_share_pct: Optional[float] = None
    firm_max_loss_eod: int
    firm_profit_target: int
    firm_consistency_pct: Optional[float] = None
    notes: Optional[str] = None


class BacktestDetail(BaseModel):
    run_id: str
    strategy_id: str
    strategy_name: str
    instrument: str
    params: dict
    bar_type: str
    bar_value: int
    start_date: str
    end_date: str
    commission_per_side: float
    slippage_ticks: int
    status: str
    error_message: Optional[str] = None
    created_at: datetime
    completed_at: Optional[datetime] = None
    # KPIs
    net_pnl: Optional[float] = None
    max_drawdown: Optional[float] = None
    profit_factor: Optional[float] = None
    win_rate: Optional[float] = None
    win_count: Optional[int] = None
    trade_count: Optional[int] = None
    sharpe: Optional[float] = None
    sortino: Optional[float] = None
    cagr: Optional[float] = None
    avg_win: Optional[float] = None
    avg_loss: Optional[float] = None
    avg_trade_duration_min: Optional[float] = None
    worst_day_pnl: Optional[float] = None
    worst_losing_streak: Optional[int] = None
    # Heavy data (loaded from JSON files on disk)
    equity_curve: list[EquityPoint] = []
    daily_pnl: list[dict] = []     # [{date: 'YYYY-MM-DD', pnl: float}]
    # Per-firm verdicts
    evaluations: list[EvaluationDetail] = []
    worthiness: Optional[WorthinessScore] = None
    sweep_id: Optional[str] = None
    optimization_id: Optional[str] = None


# ── Lab — progress + system health ───────────────────────────────────────────

class LabProgress(BaseModel):
    job_id: Optional[str] = None
    job_type: Optional[str] = None          # 'backtest' | 'optimize' | 'stress' | 'overfit'
    status: str = "idle"                    # 'idle' | 'running' | 'complete' | 'failed_*'
    strategy_id: Optional[str] = None
    instrument: Optional[str] = None
    pct: int = 0
    message: str = ""
    started_at: Optional[str] = None
    updated_at: Optional[str] = None
    heartbeat_age_seconds: float = 0.0
    error_message: Optional[str] = None


class SystemHealth(BaseModel):
    backend: bool = True
    ssh_tunnel: bool = False
    vps_agent: bool = False
    nt8_running: bool = False
    nt8_sa_visible: bool = False
    last_compile_ok: bool = False
    last_compile_at: Optional[str] = None
    last_compile_errors: list[str] = []
    checked_at: str


# ── Lab — running job status ─────────────────────────────────────────────────

class RunningJobStatus(BaseModel):
    running: bool
    job_type: Optional[str] = None   # "backtest" | "sweep" | "optimization"
    job_id: Optional[str] = None
    description: Optional[str] = None


# ── Lab — sweeps ──────────────────────────────────────────────────────────────

class SweepRequest(BaseModel):
    strategy_id: str
    params: dict
    bar_type: str = "Minute"
    bar_value: int = 5
    start_date: str
    end_date: str
    commission_per_side: float = 2.25
    slippage_ticks: int = 1
    ruleset_ids: list[str] = []
    firm_ids: list[str] = []            # backward-compat alias
    instruments: list[str]
    source_run_id: Optional[str] = None

    @property
    def effective_ruleset_ids(self) -> list[str]:
        return self.ruleset_ids or self.firm_ids


class SweepResponse(BaseModel):
    sweep_id: str
    run_ids: list[str]
    status: str


class SweepSummary(BaseModel):
    sweep_id: str
    strategy_id: str
    strategy_name: str
    start_date: str
    end_date: str
    total_instruments: int
    completed_instruments: int
    failed_instruments: int
    status: str
    created_at: datetime
    source_run_id: Optional[str] = None
    best_worthiness: Optional[str] = None
    ruleset_ids: list[str] = []


class SweepDetail(BaseModel):
    sweep_id: str
    strategy_id: str
    strategy_name: str
    start_date: str
    end_date: str
    ruleset_ids: list[str]
    total_instruments: int
    completed_instruments: int
    status: str
    created_at: datetime
    completed_at: Optional[datetime] = None
    runs: list[BacktestSummary] = []


# ── Lab — optimizations ───────────────────────────────────────────────────────

class OptimizationRequest(BaseModel):
    strategy_id: str
    instrument: str
    bar_type: str = "Minute"
    bar_value: int = 5
    start_date: str
    end_date: str
    commission_per_side: float = 2.25
    slippage_ticks: int = 1
    ruleset_id: str
    mode: str = "eval"                  # "eval" | "funded"
    search_method: str = "auto"         # "auto" | "brute" | "genetic"
    param_grid: dict                    # {param: {min, max, step} | [val, ...]}
    source_run_id: Optional[str] = None
    regime_filter: Optional[str] = None  # TRENDING | TRANSITIONING | RANGING | HIGH_VOLATILITY | LOW_VOLATILITY


class OptimizationSummary(BaseModel):
    optimization_id: str
    strategy_id: str
    instrument: str
    start_date: str
    end_date: str
    ruleset_id: str
    mode: str
    search_method: str
    status: str
    estimated_runs: int
    completed_runs: int
    best_run_id: Optional[str] = None
    source_run_id: Optional[str] = None
    regime_filter: Optional[str] = None
    created_at: datetime
    completed_at: Optional[datetime] = None


class OptimizationDetail(BaseModel):
    optimization_id: str
    strategy_id: str
    strategy_name: str
    instrument: str
    start_date: str
    end_date: str
    ruleset_id: str
    mode: str
    search_method: str
    param_grid: dict
    status: str
    estimated_runs: int
    completed_runs: int
    best_run_id: Optional[str] = None
    regime_filter: Optional[str] = None
    created_at: datetime
    completed_at: Optional[datetime] = None
    runs: list[BacktestSummary] = []


# ── Lab — instrument summary (for Tier 3 modal) ───────────────────────────────

class InstrumentResult(BaseModel):
    instrument: str
    best_worthiness: Optional[str] = None
    best_run_id: Optional[str] = None
    tested_at: Optional[datetime] = None


class InstrumentSummary(BaseModel):
    instrument_results: list[InstrumentResult]
    untested_instruments: list[str]


# ── Stress Tests ──────────────────────────────────────────────────────────────

class StressTestCreate(BaseModel):
    run_id: str
    ruleset_id: Optional[str] = None
    include_walk_forward: bool = False
    include_sensitivity: bool = False
    num_simulations: int = 10_000
    num_bootstrap: int = 1_000
    walk_forward_windows: int = 5


class WalkForwardWindow(BaseModel):
    window: int
    is_pnl: Optional[float] = None
    oos_pnl: Optional[float] = None
    is_sharpe: Optional[float] = None
    oos_sharpe: Optional[float] = None


class StressTest(BaseModel):
    stress_test_id: str
    run_id: str
    ruleset_id: Optional[str] = None
    status: str
    created_at: int
    completed_at: Optional[int] = None
    mc_completed_at: Optional[int] = None
    wf_completed_at: Optional[int] = None
    num_simulations: int = 10_000
    num_bootstrap: int = 1_000
    median_final_pnl: Optional[float] = None
    pct5_final_pnl: Optional[float] = None
    pct1_final_pnl: Optional[float] = None
    median_max_dd: Optional[float] = None
    pct5_max_dd: Optional[float] = None
    pct1_max_dd: Optional[float] = None
    prob_breach: Optional[float] = None
    prob_pass_eval: Optional[float] = None
    walk_forward_windows: int = 5
    walk_forward_summary: Optional[list[WalkForwardWindow]] = None
    walk_forward_degradation: Optional[float] = None
    sensitivity_summary: Optional[dict] = None
    sensitivity_max_degradation: Optional[float] = None
    grade: Optional[str] = None
    grade_reasons: Optional[list[str]] = None
    equity_paths_path: Optional[str] = None
    distribution_path: Optional[str] = None
    error_message: Optional[str] = None
    # From JOIN
    strategy_name: Optional[str] = None
    strategy_id: Optional[str] = None
    instrument: Optional[str] = None


class StressTestDetail(StressTest):
    equity_paths: Optional[list] = None
    distribution: Optional[dict] = None


# ── Strategy files (Pass 2 — deployment manager) ─────────────────────────────

class StrategyFile(BaseModel):
    filename: str
    size_bytes: int
    modified_at: str  # ISO-8601 from the VPS agent
    platform: str = "NT8"


class StrategyFileSyncStatus(BaseModel):
    strategy_id: str
    expected_filename: str
    file_exists_on_vps: bool
    file_size_bytes: Optional[int] = None
    file_modified_at: Optional[str] = None
    in_sync: bool


class CompileJobStatus(BaseModel):
    compile_job_id: str
    status: str        # "running" | "success" | "failed"
    errors: list[str] = []
    warnings: list[str] = []
    started_at: Optional[float] = None
    completed_at: Optional[float] = None
