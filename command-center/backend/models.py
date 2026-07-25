"""
Pydantic models — the data contract between backend and frontend.
These shapes are authoritative. Pipeline outputs conform to this; not the reverse.
"""

from __future__ import annotations
from datetime import datetime
from typing import Optional
from pydantic import BaseModel, ConfigDict, Field, field_validator


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
    # Per-trade excursion (Python runner only for now): the most the trade ever showed in profit
    # (favorable, ≥0) and the deepest it sat against us (adverse, ≤0). Absent on runs without it —
    # this model drops any field it doesn't declare, so these MUST be here to reach the equity chart.
    favorable: Optional[float] = None
    adverse: Optional[float] = None


class SizedTimelineDay(BaseModel):
    """One trading day of a SIZED run — the engine's day-by-day record (mirrors
    sizing_engine.DayTimeline). Loaded from engine_timeline.json on disk; drives the
    sized equity curve (eod_balance vs risk_floor) and the timeline view."""
    date: str
    trades_taken: int
    contracts_total: int
    day_pnl: float
    eod_balance: float
    risk_floor: Optional[float] = None
    floor_distance: Optional[float] = None
    consistency_share_pct: Optional[float] = None
    halt_reason: Optional[str] = None


class RegimeBreakdownRow(BaseModel):
    """One market-regime's slice of a run's performance. Built server-side by
    metrics.compute_regime_breakdown — the single source of truth for the table."""
    regime: str
    days: int
    trades: int
    net_pnl: float
    win_rate: Optional[float] = None
    profit_factor: Optional[float] = None
    worst_day: Optional[float] = None


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
    description: Optional[str] = None
    default_params: dict = {}
    # [{name, type, min?, max?, default, group, display_name}] plus optional editor
    # metadata overlaid from a companion <Strategy>.meta.json by the scanner:
    # label, desc, unit, core, widget, options{off,on}, show_if{param:value}, guide[lo,hi], step
    param_schema: list[dict] = []
    scanned_at: datetime
    run_count: int = 0
    runner: str = "ninjatrader"
    # True when the source on disk has changed since the last Scan Strategies — the run modal's
    # param schema is stale until re-scanned. Computed live in the router (strategy_scanner.needs_rescan),
    # never stored. The scan-time analog of needs_deploy/needs_compile.
    needs_scan: bool = False
    # Strategy-level narrative overlaid from <Strategy>.meta.json (UI only).
    edge: Optional[str] = None
    steps: list[dict] = []   # flow: [{label, title, detail}]
    # News-filter default (UI only): 1/true = the News toggle on BacktestDetail starts on "Removed"
    # (this strategy avoids high-impact news); false = starts "Included". From meta.json "avoid_news".
    avoid_news: bool = False
    # Who sizes this strategy. False (default) = it proposes UNIT-size trades and the dynamic
    # sizing engine sizes them per ruleset. True = it sizes itself off its own risk % param, so
    # the engine must not re-size it and the UI hides SIZING MODE (there is nothing to choose).
    self_sizing: bool = False

    @field_validator("steps", mode="before")
    @classmethod
    def _steps_default(cls, v):
        # DB rows predating the column store NULL → coerce to [] so list validation passes.
        return v or []


class ScanResult(BaseModel):
    scanned: int
    added: int
    updated: int
    skipped: int
    orphans: list[str] = []    # DB strategies whose source file is gone from the repo
    warnings: list[str] = []


class ReconcileResult(BaseModel):
    removed: list[str] = []    # orphaned strategies removed from DB + VPS
    warnings: list[str] = []   # per-strategy notes (e.g. VPS file could not be deleted)


class DeployJobStatus(BaseModel):
    deploy_job_id: str
    strategy_id: str
    status: str  # "running" | "complete" | "failed"
    filename: Optional[str] = None
    uploaded_size_bytes: Optional[int] = None
    error: Optional[str] = None


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
    max_contracts: Optional[dict] = None  # null = no contract cap (personal/demo)
    platform_support: list[str] = []
    account_tier: str = "eval"          # "eval" | "funded" | "live" | "demo"
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
    # M5 — market and drawdown unit
    market: str = "futures"       # "futures" | "forex" | "mixed"
    drawdown_unit: str = "usd"    # "usd" | "percent"
    # Personal fail conditions (personal/demo rows; NULL on prop rows)
    max_drawdown_from_peak_pct: Optional[float] = None
    max_consecutive_loss_days: Optional[int] = None


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
    max_contracts: Optional[dict] = None  # null = no contract cap (personal/demo)
    platform_support: list[str] = []
    account_tier: str = "eval"          # "eval" | "funded" | "live" | "demo"
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
    # M5 — market and drawdown unit
    market: str = "futures"
    drawdown_unit: str = "usd"
    # Personal fail conditions (personal/demo rows; NULL on prop rows)
    max_drawdown_from_peak_pct: Optional[float] = None
    max_consecutive_loss_days: Optional[int] = None


class PersonalRulesetPatch(BaseModel):
    """
    PATCH /rulesets/{id} body — personal/demo rows only, personal rule fields only.
    extra="forbid" makes any other field a 422 at the validation layer, so the
    prop-rule lock cannot be bypassed by sneaking fields into this endpoint.
    Explicit nulls are ignored (rules are cleared via PUT, not PATCH).
    """
    model_config = ConfigDict(extra="forbid")

    account_size: Optional[int] = Field(None, gt=0)
    daily_loss_cap: Optional[int] = Field(None, gt=0)
    daily_profit_target: Optional[int] = Field(None, gt=0)
    max_drawdown_from_peak_pct: Optional[float] = Field(None, gt=0, le=100)
    max_consecutive_loss_days: Optional[int] = Field(None, ge=1)


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
    source_run_id: Optional[str] = None # run this was derived from (e.g. a tuning iteration)
    # Dynamic-sizing mode: 'consistent' (room÷7) | 'bullet' (max ladder) | 'manual' (a fixed
    # risk % you set). Ignored entirely for a self-sizing strategy — it sizes its own trades.
    sizing_mode: str = "consistent"
    manual_risk_pct: Optional[float] = None   # required when sizing_mode == 'manual'

    @field_validator("manual_risk_pct")
    @classmethod
    def _manual_pct_sane(cls, v):
        if v is not None and not (0 < v <= 100):
            raise ValueError("manual_risk_pct must be between 0 and 100")
        return v

    @property
    def ruleset_ids(self) -> list[str]:
        return self.evaluate_rulesets or self.evaluate_firms


class RetryRunRequest(BaseModel):
    # Optional rulesets to score against when re-firing an optimizer combo as a full
    # backtest. None = let the backend inherit from the optimization (and prompt the
    # user if nothing is inheritable); a list (even empty) = the user's explicit choice.
    evaluate_rulesets: Optional[list[str]] = None
    # Optional new period for the rerun (YYYY-MM-DD). None = keep the run's stored dates.
    # Standalone runs only — a sweep/optimization child shares its period with its siblings,
    # so the router rejects an override there rather than silently desyncing the set.
    start_date: Optional[str] = None
    end_date: Optional[str] = None


class BacktestSummary(BaseModel):
    run_id: str
    strategy_id: str
    strategy_name: str
    instrument: str
    status: str
    created_at: datetime
    started_at: Optional[datetime] = None
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
    source_run_id: Optional[str] = None
    error_message: Optional[str] = None
    start_date: Optional[str] = None
    end_date: Optional[str] = None
    runner: str = "ninjatrader"


class EvaluationDetail(BaseModel):
    eval_id: str
    ruleset_id: str
    ruleset_name: str
    verdict: str                    # prop: 'PASS' | 'WARN' | 'DISCARD'; personal/demo: 'INFO'
    drawdown_pass: bool
    target_pass: bool
    consistency_pass: Optional[bool] = None
    simulated_eval_days: Optional[int] = None
    breach_count: int
    largest_day_share_pct: Optional[float] = None
    adjusted_profit_target: Optional[float] = None
    contract_cap_status: Optional[str] = None   # 'not_evaluable' | (future: 'pass' | 'fail')
    # Trailing-MLL detail
    mll_final_floor: Optional[float] = None
    mll_highest_eod_balance: Optional[float] = None
    mll_breach_day: Optional[int] = None
    mll_min_floor_distance: Optional[float] = None
    firm_max_loss_eod: int
    firm_profit_target: int
    firm_consistency_pct: Optional[float] = None
    # Ruleset context for rendering — personal/demo cards show the personal rule
    # chips and must not render firm_max_loss_eod (0 = sentinel, not a $0 limit).
    ruleset_type: str = "prop_eval"
    personal_daily_loss_cap: Optional[int] = None
    personal_max_drawdown_from_peak_pct: Optional[float] = None
    personal_max_consecutive_loss_days: Optional[int] = None
    notes: Optional[str] = None
    # Per-ruleset sized results — each firm's own contract ladder sizes the run differently,
    # so its KPIs, daily P&L and sized timeline differ. Populated only for sized runs (from
    # ruleset_sizing.json); the UI switches the KPI cards and sized/breakdown charts per firm.
    # None/empty on unit-size runs — the UI falls back to the run-level headline.
    net_pnl: Optional[float] = None
    max_drawdown: Optional[float] = None
    profit_factor: Optional[float] = None
    win_rate: Optional[float] = None
    trade_count: Optional[int] = None
    avg_win: Optional[float] = None
    avg_loss: Optional[float] = None
    daily_pnl: list[dict] = []                       # [{date, pnl}] sized for this ruleset
    sized_timeline: list[SizedTimelineDay] = []      # engine day-by-day, sized for this ruleset
    equity_curve: list[EquityPoint] = []             # sized trade-by-trade curve (drawdown, long/short, calmar…)


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
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    # KPIs
    net_pnl: Optional[float] = None
    max_drawdown: Optional[float] = None
    profit_factor: Optional[float] = None
    win_rate: Optional[float] = None
    win_count: Optional[int] = None
    trade_count: Optional[int] = None
    sharpe: Optional[float] = None              # canonical daily-√252 Sharpe
    platform_sharpe: Optional[float] = None     # NT8/MT5's own reported Sharpe (reference)
    sharpe_low_sample: bool = False             # < 10 trading days — daily Sharpe is noisy
    profit_concentration_pct: Optional[float] = None  # largest quarter's share of gross profit
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
    # EVERY trading day in the run's window with its regime label — [{date, regime}] — not just
    # the days that traded. This is what the equity charts band from: regime is a property of the
    # market on a date, so two runs over the same window must agree about it. Empty on runs that
    # completed before the timeline was introduced (charts fall back to daily_pnl's tags).
    regime_timeline: list[dict] = []
    # Per-regime performance, computed server-side from equity_curve + tagged daily_pnl
    regime_breakdown: list[RegimeBreakdownRow] = []
    # Per-firm verdicts
    evaluations: list[EvaluationDetail] = []
    worthiness: Optional[WorthinessScore] = None
    sweep_id: Optional[str] = None
    optimization_id: Optional[str] = None
    source_run_id: Optional[str] = None
    runner: str = "ninjatrader"
    sizing_mode: str = "consistent"   # 'consistent' | 'bullet' | 'manual' — mode this run used
    manual_risk_pct: Optional[float] = None   # the risk % used, when sizing_mode == 'manual'
    sized: bool = False               # True once a reshaped strategy emitted engine_trades and the engine sized the run
    sized_timeline: list[SizedTimelineDay] = []   # the engine's day-by-day record (sized runs only) — sized equity curve + timeline


# ── Lab — news filter (post-run trade tagging) ───────────────────────────────

class NewsTradeTag(BaseModel):
    index: Optional[int] = None      # trade number, matches the equity-curve point
    entry_ms: Optional[int] = None   # trade OPEN time, UTC epoch ms (null on old runs with no stored time)
    in_coverage: bool = False        # calendar data covers this date (else we don't guess)
    in_news: bool = False            # opened inside a high-impact news window — the toggle removes these
    in_holiday: bool = False         # opened on a bank holiday — always removed, not part of the toggle
    title: Optional[str] = None      # the event that tagged it


class RunNewsReport(BaseModel):
    has_data: bool                             # False when the calendar cache is empty → filter inert
    coverage_start_ms: Optional[int] = None    # earliest ms with news data — the "news starts here" line
    coverage_end_ms: Optional[int] = None
    pre_minutes: int                           # block window before an event (default 15)
    post_minutes: int                          # block window after an event (default 30)
    trades: list[NewsTradeTag] = []
    news_trade_count: int = 0
    holiday_trade_count: int = 0


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
    nt8_agent: bool = False    # NT8 agent (port 8765)
    mt5_agent: bool = False    # MT5 agent (port 8766)
    nt8_running: bool = False
    nt8_sa_visible: bool = False
    last_compile_ok: bool = False
    last_compile_at: Optional[str] = None
    last_compile_errors: list[str] = []
    checked_at: str


# ── Lab — running job status ─────────────────────────────────────────────────

class RunningJobInfo(BaseModel):
    running: bool
    job_type: Optional[str] = None   # "backtest" | "sweep" | "optimization"
    job_id: Optional[str] = None
    description: Optional[str] = None


class RunningJobStatus(BaseModel):
    nt8: RunningJobInfo = RunningJobInfo(running=False)
    mt5: RunningJobInfo = RunningJobInfo(running=False)
    python: RunningJobInfo = RunningJobInfo(running=False)


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


# ── Lab — portfolio stacks ────────────────────────────────────────────────────
# A "stack" layers 2+ Python strategies over ONE shared instrument/window. Each strategy
# runs as a normal single-strategy Python backtest (grouped by stack_id); the combined
# portfolio P&L is composed CLIENT-SIDE by summing each child's daily_pnl, and toggling a
# strategy off is a re-sum without it. Python strategies only.

class StackRequest(BaseModel):
    strategy_ids: list[str]                 # 2+ Python strategy ids to layer
    instrument: str                         # one shared instrument for the whole stack
    bar_type: str = "Minute"
    bar_value: int = 15
    start_date: str
    end_date: str
    # Zero costs by default — matches the Pine strategies (all pinned commission=0, slippage=0)
    # for honest TV↔Python parity. The Python fill engine takes real cost from the account
    # profile (vantage_demo = 0 commission) + measured/bar slippage, so these fields are the
    # displayed/leg-matching values, not the applied ones.
    commission_per_side: float = 0.0
    slippage_ticks: int = 0
    ruleset_ids: list[str] = []             # optional — scored per child run, like a normal run
    # Optional per-strategy param override, keyed by strategy id. A strategy not present here
    # uses its stored default_params. Lets the two sleeves carry different risk knobs.
    params_by_strategy: dict[str, dict] = {}


class StackPreviewRequest(BaseModel):
    """Ask, without running anything, which legs would be REUSED from an existing
    completed run vs RE-RUN fresh, for a given shared instrument/timeframe/window/costs."""
    strategy_ids: list[str]
    instrument: str
    bar_type: str = "Minute"
    bar_value: int = 15
    start_date: str
    end_date: str
    commission_per_side: float = 0.0        # match the Pine (0/0) — see StackRequest
    slippage_ticks: int = 0


class StackPreviewLeg(BaseModel):
    strategy_id: str
    strategy_name: str
    action: str                             # "reuse" | "run"
    matched_run_id: Optional[str] = None    # set when action == "reuse"
    net_pnl: Optional[float] = None
    trade_count: Optional[int] = None
    profit_factor: Optional[float] = None


class StackPreviewResponse(BaseModel):
    legs: list[StackPreviewLeg]
    reuse_count: int
    run_count: int


class StackResponse(BaseModel):
    stack_id: str
    run_ids: list[str]
    status: str


class StackSummary(BaseModel):
    stack_id: str
    instrument: str
    start_date: str
    end_date: str
    total_strategies: int
    completed_strategies: int
    failed_strategies: int
    status: str
    created_at: datetime
    strategy_names: str = ""                 # " + "-joined display names


class StackStrategyLeg(BaseModel):
    run_id: str
    strategy_id: str
    strategy_name: str
    status: str
    net_pnl: Optional[float] = None
    max_drawdown: Optional[float] = None
    trade_count: Optional[int] = None
    sharpe: Optional[float] = None
    avg_trade_duration_min: Optional[float] = None   # trade-weighted into the stack's AVG TRADE KPI
    error_message: Optional[str] = None
    daily_pnl: list[dict] = []              # [{date, pnl}]
    equity_curve: list[EquityPoint] = []


class StackDetail(BaseModel):
    stack_id: str
    instrument: str
    start_date: str
    end_date: str
    bar_type: str
    bar_value: int
    commission_per_side: float = 0.0
    slippage_ticks: int = 0
    total_strategies: int
    completed_strategies: int
    status: str
    created_at: datetime
    completed_at: Optional[datetime] = None
    # Full-calendar regime timeline for the shared window (from a leg — regime is a property of the
    # market on a date, identical for every leg). Drives the equity chart's regime overlay, same as
    # a single backtest's `regime_timeline`.
    regime_timeline: list[dict] = []
    # One entry per strategy sleeve — carries the child run id + its daily P&L and equity curve
    # so the frontend can sum enabled sleeves into a portfolio line and recompute KPIs on toggle.
    strategies: list[StackStrategyLeg] = []


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
    ruleset_id: Optional[str] = None    # null for MT5 / "raw" mode
    mode: str = "eval"                  # "eval" | "funded" | "raw"
    search_method: str = "native"
    param_grid: dict                    # {param: {min, max, step} | [val, ...]}
    source_run_id: Optional[str] = None
    regime_filter: Optional[str] = None  # TRENDING | TRANSITIONING | RANGING | HIGH_VOLATILITY | LOW_VOLATILITY


class OptimizationSummary(BaseModel):
    optimization_id: str
    strategy_id: str
    instrument: str
    start_date: str
    end_date: str
    ruleset_id: Optional[str] = None
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
    ruleset_id: Optional[str] = None
    mode: str
    search_method: str
    param_grid: dict
    status: str
    estimated_runs: int
    completed_runs: int
    best_run_id: Optional[str] = None
    regime_filter: Optional[str] = None
    runner: str = "ninjatrader"
    created_at: datetime
    completed_at: Optional[datetime] = None
    runs: list[BacktestSummary] = []
    live_pct: Optional[int] = None
    live_message: Optional[str] = None


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


class StrategyVersion(BaseModel):
    strategy_id: str
    version: int
    source_hash: str
    size_bytes: Optional[int] = None
    created_at: int  # unix seconds


class StrategyFileSyncStatus(BaseModel):
    strategy_id: str
    expected_filename: str
    file_exists_on_vps: bool
    file_size_bytes: Optional[int] = None
    file_modified_at: Optional[str] = None
    in_sync: bool
    is_compiled: Optional[bool] = None  # MT5 only: True if .ex5 exists alongside .mq5
    # Version tracking — which content version is local vs deployed vs compiled.
    current_version: Optional[int] = None     # version of the current local source
    current_source_hash: Optional[str] = None
    deployed_version: Optional[int] = None    # version last deployed to the lab VPS
    deployed_at: Optional[int] = None         # unix seconds
    compiled_version: Optional[int] = None    # version last compiled on the lab VPS
    compiled_at: Optional[int] = None         # unix seconds
    needs_deploy: bool = False                # local source differs from deployed
    needs_compile: bool = False               # deployed source not yet compiled


class CompileJobStatus(BaseModel):
    compile_job_id: str
    status: str        # "running" | "success" | "failed"
    errors: list[str] = []
    warnings: list[str] = []
    started_at: Optional[float] = None
    completed_at: Optional[float] = None


# ── News calendar (live tab) ────────────────────────────────────────────────────

class CalendarEvent(BaseModel):
    """One economic-calendar row for the live News Calendar tab. `forecast`/`previous`/`actual` are
    the source's display strings (e.g. "2.6%", "$125.62"), null until published. `impact` is the
    Impact enum name (HIGH/MEDIUM/LOW/NONE). `category` is TradingView's grouping label (Labor,
    Prices, …) for the categories dropdown. `surprise` is the backend's beat/miss call once actual
    is out: "beat" | "miss" | "inline" | null (null = not enough data / not released) — the frontend
    colours the actual green/red from it, so the currency-lower-is-better polarity stays server-side.

    The endpoint returns the WHOLE week unfiltered; the frontend does the currency/impact/category/day
    filtering client-side (a week is only a few hundred rows), so filter changes are instant and the
    day-summary counts stay consistent with the list."""
    timestamp_ms: int          # event time, UTC epoch ms
    currency: str              # ISO currency the event moves (USD/EUR/…)
    impact: str                # "HIGH" | "MEDIUM" | "LOW" | "NONE"
    title: str
    category: Optional[str] = None
    forecast: Optional[str] = None
    previous: Optional[str] = None
    actual: Optional[str] = None
    surprise: Optional[str] = None   # "beat" | "miss" | "inline" | None


class CalendarResponse(BaseModel):
    """The /calendar payload: the window's events plus server time (so the frontend "now" line and
    countdown run off the server clock, not a possibly-wrong browser clock)."""
    events: list[CalendarEvent] = []
    server_now_ms: int
    from_ms: int
    to_ms: int
