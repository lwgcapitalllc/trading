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
    # balance
    starting_balance: float
    ending_balance: float
    net_growth_pct: float
    peak_balance: float
    lowest_balance: float
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
    daily_pnl_pct: Optional[float] = None
    day_locked: bool = False


class BotSnapshot(BaseModel):
    fetched_at: datetime
    bots: list[BotStatus]
    scheduled_jobs: list[JobStatus]
    telegram: ProcessStatus


# ── Backtests ─────────────────────────────────────────────────────────────────

class BacktestResult(BaseModel):
    strategy: str
    instrument: str
    verdict: str            # "KEEP" | "WARN" | "DISCARD"
    max_drawdown: float
    max_loss_limit: float
    drawdown_pass: bool
    eval_result: str        # "would_pass" | "would_fail"
    eval_days: Optional[int] = None
    daily_pnl: list[float]
    worst_day: float
    worst_losing_streak: int
    win_rate: float
    profit_factor: float
    avg_win: float
    avg_loss: float
    trade_count: int
    expectancy: float
    total_return: float
    cagr: float
    sharpe: float
    sortino: float
    avg_trade_duration_min: float
    equity_curve: list[EquityPoint]


class BacktestRun(BaseModel):
    run_id: str
    generated_at: datetime
    combos: list[BacktestResult]


# ── Stress Tests ──────────────────────────────────────────────────────────────

class StressTestResult(BaseModel):
    strategy: str
    instrument: str
    runs: int
    max_dd_median: float
    max_dd_p95: float
    max_dd_p99: float
    prob_breach: float
    prob_pass_eval: float
    final_pnl_median: float
    final_pnl_p10: float
    final_pnl_worst: float
    equity_paths: list[list[EquityPoint]]
