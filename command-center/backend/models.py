"""
Pydantic models — the data contract between backend and frontend.
These shapes are authoritative. Pipeline outputs conform to this; not the reverse.
"""

from __future__ import annotations
from datetime import datetime
from typing import Any, Optional
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
    # The trade's OPEN time (UTC epoch ms) — what the News & Holiday filter card tags against.
    # backtest/output.py has always written it to equity_curve.json and the /news endpoint reads it
    # straight off disk, so the SERVER-side tagging worked; it was missing HERE, so the model dropped
    # it on the way out and the card judged every run "made before trade times were recorded".
    entry_ms: Optional[int] = None
    # The trade's CLOSE time (UTC epoch ms). Same story as entry_ms one line up, same fix: it has
    # always been in equity_curve.json, and it was undeclared here so it never reached the browser.
    # With both times present a consumer can compute duration over ANY SUBSET of trades — which is
    # what lets the News & Holiday filter report Avg Trade instead of a dash. Older runs predate
    # nothing (output.py has always written it), but NT8/MT5 curves carry neither time.
    exit_ms: Optional[int] = None
    direction: Optional[str] = None   # 'Long' | 'Short'
    profit: Optional[float] = None
    exit_name: Optional[str] = None
    # Per-trade excursion (Python runner only for now): the most the trade ever showed in profit
    # (favorable, ≥0) and the deepest it sat against us (adverse, ≤0). Absent on runs without it —
    # this model drops any field it doesn't declare, so these MUST be here to reach the equity chart.
    favorable: Optional[float] = None
    adverse: Optional[float] = None
    # The trade's result in R — its P&L over the risk it was sized to. Same story as entry_ms and
    # favorable above, and this is the FIFTH time this model has dropped a field that was on disk:
    # `backtest/output.py` has written it since 2026-08-03 (`reprice.py` reads it straight off the
    # file) and nothing declared it, so it never reached the browser.
    #
    # It is the one per-trade figure that survives a change of position SIZE, which is what makes it
    # the honest unit for a portfolio stack: a leg posts the same R in a shared book as it does
    # alone, while its DOLLARS differ by whatever the other legs grew the balance to (measured
    # 2026-08-10 on `st_94aeb25f0c` — 17.8674R either way, $47,758,999 against $21,064).
    r: Optional[float] = None
    # Commission + swap + slippage charged to this trade (negative). `profit` is already net of
    # it. Declared here for the SAME reason entry_ms/exit_ms above had to be: this model drops any
    # field it does not declare, so a value that reaches equity_curve.json still never reaches the
    # browser. Third time that trap has been hit — treat it as a rule, not an anecdote.
    costs_usd: Optional[float] = None


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
    # DISABLED is distinct from STOPPED on purpose: switched off deliberately, not broken.
    status: str         # "RUNNING" | "STOPPED" | "DISABLED" | "UNKNOWN"


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

class BotReviewFinding(BaseModel):
    key: str
    level: str              # "alert" | "warn"
    title: str
    detail: str


class BotReview(BaseModel):
    """What the hourly log review found in this bot's own health record.

    Written by `algos/notifications/log_review.py` to `<instance>/review.json` on the VPS and
    read here. It answers the question no other indicator on this page can: **the process can be
    alive, stamping its heartbeat and showing RUNNING while the order bridge is HALTED and the
    bot places nothing.** Nothing in the system reported that before 2026-08-05.
    """
    level: str              # the worst level among the findings
    checked_at: str
    findings: list[BotReviewFinding] = []


class BotStatus(BaseModel):
    # The bot's STABLE identifier — `mpc_sos_fade_demo`, the same string that appears on the
    # VPS process commandline (`runner.py --bot <key>`). Use this for URLs, selection state
    # and API paths; `name` is a label chosen for a human, so it is the field that will
    # eventually be changed, and anything keyed on it breaks when it is.
    key: str
    name: str
    account: str
    account_type: str       # "demo" | "live"
    balance: Optional[float] = None
    # Is the bot's PROCESS still talking to its MT5 terminal? `None` = the bot predates the
    # field or has not stamped one yet — never render an unasked question as a failure.
    #
    # ⚠ This exists because `balance: None` is not a diagnosis, and on 2026-08-04 it was the
    # ONLY symptom of a bot that had been blind for 50 minutes: MetaTrader auto-updated and
    # restarted itself, the running bot's IPC handle died with the old process, and every
    # data call started returning an ABSENCE rather than an error — an empty bar frame reads
    # as a quiet market, so the loop kept beating and this page kept saying RUNNING. A blank
    # balance must always be attributable to one of the two causes, not to either.
    mt5_link: Optional[bool] = None
    # A standing flag raised by `algos/notifications/log_review.py`, which reads the bot's own
    # health record hourly. `None` = nothing to review.
    #
    # ⚠ It exists because a Telegram alert is a MOMENT and this is a STATE. An alert you
    # scrolled past at 3am is gone; this chip is still on the page tomorrow. The pair is
    # deliberate — the notification gets your attention, the flag survives not having it.
    #
    # ⚠ It reads a SEPARATE `review.json`, never `bot_state.json`: the live runner rewrites
    # that file every poll through a read-modify-write, so a review written into it would race
    # the heartbeat and could be lost, or clobber a balance on the way past.
    review: Optional[BotReview] = None
    status: str             # "RUNNING" | "STOPPED" | "ERROR"
    uptime_seconds: Optional[int] = None
    total_pnl_pct: Optional[float] = None
    day_locked: bool = False
    # ── Detail fields (populated from bot_state.json) ─────────────────────────
    # ⚠ The derived P&L fields (daily_pnl, weekly_pnl, peak_balance, trades_today) and the
    # three cap fields (daily_goal_pct / daily_cap_pct / weekly_cap_pct) were REMOVED
    # 2026-08-05 with `algos/notifications/pnl_tracker.py`, which was their only writer and
    # had carried an empty bot registry since June. They would have rendered "+0.00% today"
    # and a cap under fields nothing measures and nothing enforces — the same rule
    # `mt5_link` above states: never let a fabricated value and a measured one look alike.
    # `total_pnl_pct` and `balance` survive because `algos/live/runner.py` writes them.
    lock_reason: Optional[str] = None
    last_updated: Optional[str] = None


class BotSnapshot(BaseModel):
    fetched_at: datetime
    bots: list[BotStatus]
    scheduled_jobs: list[JobStatus]
    telegram: ProcessStatus


# `BotConfigSections` / `BotConfigUpdate` / `BotCapUpdate` were deleted 2026-08-04 with the
# three unused endpoints that took them — see `routers/bots.py`, above `get_bot_params`.
# `BotParamsView` (read) and `BotRuntimeUpdate` (write) are the maintained pair.


class BotParamRow(BaseModel):
    """One line of a live bot's configuration, as rendered on the Bots page."""
    name: str
    value: Any = None
    label: str
    group: str
    desc: Optional[str] = None
    unit: Optional[str] = None
    type: str
    options: Optional[dict] = None
    choices: Optional[list] = None
    core: bool = False
    editable: bool = False
    min: Optional[float] = None
    max: Optional[float] = None
    note: Optional[str] = None


class BotParamsView(BaseModel):
    bot_key: str
    display_name: str
    identity: dict          # account, server, symbol, timeframe, terminal, magic
    version: dict           # package/class/version + source hash + promoted commit
    runtime: list[BotParamRow]      # editable on a running bot
    strategy: list[BotParamRow]     # read-only — changing these needs a re-promote
    notes: dict = {}
    readme: Optional[str] = None


class BotCodeChange(BaseModel):
    """One commit sitting between the deployed version and the backtester's."""
    commit: str
    subject: str
    date: str = ""
    areas: list[str] = []        # which of the bot's trees it touched — NOT a claim about trades


class BotSettingChange(BaseModel):
    """A setting whose DEFAULT moved in the repo since this bot was deployed.

    `stated` True means the bot's instance config pins it, so a promote will NOT move it.
    Those rows are kept rather than filtered: *this changed and your bot is holding it still*
    is the reassuring half of the same question, and dropping it leaves the reader unable to
    tell "not affected" from "not checked".
    """
    name: str
    label: str
    group: str = ""
    desc: str = ""
    is_new: bool = False         # the deployed version had no such setting at all
    was: str = ""                # empty exactly when `is_new` — not "Off", which is a value
    now: str
    stated: bool = False


class BotVersionCompare(BaseModel):
    """How far a bot's deployment is behind the code the backtester runs.

    A version is the number of commits that have touched this bot's trees — see
    `services/bot_versions.py` for why it is that and not the lab's content-addressed
    registry. `comparable` False carries a plain-English `reason`; the page then renders no
    number and no deploy button, because every state that makes this unanswerable has a
    different fix and none of them is "press deploy".
    """
    deployed_version: Optional[int] = None
    local_version: Optional[int] = None
    versions_behind: Optional[int] = None
    uncommitted_files: list[str] = []
    comparable: bool = False
    reason: str = ""
    changes: list[BotCodeChange] = []
    setting_changes: list[BotSettingChange] = []


class BotDeployedVersion(BaseModel):
    """What a bot is ACTUALLY running, read off the VPS.

    Sourced from `deployed.json` beside the bot's frozen code snapshot — written only by
    `algos/tools/promote.py`. Deliberately not from the tracked `config.json`, which states
    INTENT and goes stale the moment the repo moves; a version display that can be wrong is
    worse than none, because it is what you check before deciding anything.
    """
    frozen: bool                 # False = still importing from the repo tree (unpromoted)
    hash: str = ""
    commit: str = ""             # the commit the snapshot was taken from
    promoted_at: str = ""
    strategy_package: str = ""
    strategy_class: str = ""
    strategy_version: int = 0
    files: int = 0
    params: dict = {}            # the parameters AS DEPLOYED, not as config.json reads today
    repo_commit: str = ""        # what the VPS working tree is on now
    commits_ahead: int = 0       # how far the repo has moved past the deployment
    snapshot_ok: bool = True     # on-disk hash still matches the record (tamper check)
    running_hash: str = ""       # what the live PROCESS reports, from bot_state.json
    params_drift: list[str] = []  # settings config.json now states differently from deployed
    # `strategy_version` above is DEAD — `live_config.LiveConfig` defaults it to 0 and nothing
    # writes it, so the card read v0 before a promote and v0 after. `compare` is the real one.
    compare: Optional[BotVersionCompare] = None


class BotPromoteRequest(BaseModel):
    pull: bool = True            # `git pull` on the VPS first
    restart: bool = True         # restart the bot onto the new version
    allow_dirty: bool = False


class BotPromoteResult(BaseModel):
    ok: bool
    output: str                  # promote.py's own text — it is written to be read
    restarted: bool = False


class BotRuntimeUpdate(BaseModel):
    """A change to the levers that may move on a running bot.

    `values` is validated against `services/bot_params.RUNTIME_EDITABLE` — the backend is
    authoritative about what is editable, so a frontend bug cannot widen the set.
    """
    values: dict[str, float]
    deploy: bool = True     # commit + push + VPS pull; False writes locally only


class BotAccountBot(BaseModel):
    """One bot's place in a trading account."""
    key: str
    display: str
    symbol: str
    magic: int
    strategy_package: str
    # Per-TRADE risk, the layer BELOW the cap. Served so the page can put the two side by side:
    # a cap at or under a bot's own risk % makes the bots take turns rather than share, and that
    # is invisible from the cap alone.
    risk_pct: Optional[float] = None
    cap_pct: Optional[float] = None
    unreadable: bool = False       # its config could not be parsed — its cap is UNKNOWN, not absent


class BotAccountGroup(BaseModel):
    """Every bot trading one broker account, and the ceiling they share.

    ⚠ `risk_cap_pct` is only meaningful when `cap_agrees`. When the bots state different values
    there is no account cap to report, and it is deliberately NOT the max or the min — picking one
    would invent a ceiling nobody configured and hide the fault behind a plausible number.
    """
    account: Optional[int] = None
    server: str = ""
    # "account" | "bench" | "unknown". The last two both have no account NUMBER and are not the
    # same thing: `bench` is a bot somebody deliberately took off an account, `unknown` is a
    # config that could not be read. Collapsing them puts a chosen state and a fault under one
    # heading with one set of controls.
    kind: str = "account"
    bots: list[BotAccountBot] = []
    risk_cap_pct: Optional[float] = None
    cap_agrees: bool = True
    cap_unknown: bool = False      # at least one config unreadable, so the cap cannot be confirmed
    stacked: bool = False          # more than one bot on this BALANCE (never true off an account)
    cap_takes_turns: bool = False  # the cap is at or below the largest per-trade risk here
    # Bots here sharing an order tag. Empty is healthy, and the page shows the fact only when it
    # is true rather than printing a raw magic number nobody can interpret.
    magic_clash: list[str] = []


class BotAccountCapUpdate(BaseModel):
    """Set (or clear) the account-level risk cap across EVERY bot on one account.

    `risk_cap_pct` of `None` means UNCAPPED, which is a supported and honest state — not "leave it
    alone". There is no separate clear endpoint precisely so that the absent value keeps meaning
    the one thing.
    """
    risk_cap_pct: Optional[float] = None
    deploy: bool = True            # commit + push + VPS pull; False writes locally only

    @field_validator("risk_cap_pct")
    @classmethod
    def _sane_cap(cls, v):
        if v is None:
            return v
        if v <= 0:
            # 0 refuses every order on the account. If that is what somebody wants, they want the
            # fleet halt, which stops orders WITHOUT making every bot log a risk refusal.
            raise ValueError("risk_cap_pct must be greater than 0 — use null to run uncapped, "
                             "or the fleet halt to stop trading")
        if v > 100:
            raise ValueError("risk_cap_pct is a percentage of the live balance and cannot exceed 100")
        return v


class BotAccountAssign(BaseModel):
    """Put one bot ON an account, or take it OFF one.

    `account` of `None` is the BENCH — registered, configured, trading nothing — and it is the
    whole reason removal is expressible at all. There is no separate remove endpoint, for
    `BotAccountCapUpdate`'s reason: one field, one meaning, and the absent value keeps saying the
    same thing wherever it appears.

    ⚠ **This writes more than `account`** (`bot_accounts.assign_plan`): joining an account also
    adopts its server, its terminal path and its risk cap, because a bot that kept its own cap
    would take every bot already on that account off the box at their next restart. See that
    function for why each field is there.
    """
    account: Optional[int] = None
    deploy: bool = True            # commit + push + VPS pull; False writes locally only


# The roles `algos/notifications/telegram_bot.py` keys `ROLE_COMMANDS` on. A value outside
# this set is not a new role — it is a user with NO permissions, because `get_role` returns
# the string and the command lookup then misses. `"Admin"` is the shape of that mistake.
# The subsystems may not import each other, so this is a mirrored contract, like
# `bot_params.RUNTIME_EDITABLE` mirrors `live_config.RUNTIME_RELOADABLE`.
TELEGRAM_ROLES = ("admin", "readonly")


class TelegramUser(BaseModel):
    chat_id: str
    name: str
    role: str           # "admin" | "readonly"
    added: str          # YYYY-MM-DD


class TelegramUserCreate(BaseModel):
    chat_id: str
    name: str
    role: str

    @field_validator("role")
    @classmethod
    def _known_role(cls, v: str) -> str:
        if v not in TELEGRAM_ROLES:
            raise ValueError(f"role must be one of {TELEGRAM_ROLES}, not {v!r}")
        return v


class TelegramUserRoleUpdate(BaseModel):
    role: str

    @field_validator("role")
    @classmethod
    def _known_role(cls, v: str) -> str:
        if v not in TELEGRAM_ROLES:
            raise ValueError(f"role must be one of {TELEGRAM_ROLES}, not {v!r}")
        return v


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
    # The source file this row was registered from is gone from the repo, so the
    # strategy exists only in the DB (and possibly still on the VPS). Computed
    # live beside needs_scan, never stored — it is a fact about disk right now.
    # It rides on the row so the Reconcile control does not depend on somebody
    # having pressed Scan in this browser session.
    is_orphan: bool = False
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
    # 0/0 by design (2026-08-01, Aaron's call). A request model's default is what ships when the
    # caller states nothing, and a silent 2.25/1 — a FUTURES prop-firm figure — was reaching forex
    # and Python runs that have no such cost. State the costs you want charged; nothing is assumed.
    commission_per_side: float = 0.0
    slippage_ticks: int = 0
    # Layered costs (python runner, 2026-08-02). EMPTY BY DEFAULT and that is Aaron's call: the
    # baseline run is frictionless so it stays directly comparable to the TradingView Strategy
    # Tester, and each cost is switched on deliberately. Known layers live in
    # `services/python_runner.COST_LAYERS`; `broker_profile` names whose MEASURED spread and swap
    # to charge (a key of `backtest.fills.PROFILES`), so neither is ever typed in by hand.
    # ⚠ Nullable, and the default stays `[]`. A caller that says nothing gets "charge nothing"
    # (unchanged); a caller that explicitly sends `null` is saying "this runner has no layer
    # contract" — which is what NT8 and MT5 are. Storing `[]` for them made the run page report
    # a deliberately frictionless run over a tester that charged commission and slippage.
    cost_layers: Optional[list[str]] = []
    broker_profile: str = "vantage_demo"
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


class BrokerProfile(BaseModel):
    """A broker account's MEASURED cost facts, served so the Run modal never retypes one.

    Same discipline as `HistoryLimit` below and for the same reason: a number copied into the
    frontend is a second claim about what the runner charges, and this lab's recurring defect is
    exactly that — a page stating a value nothing downstream reads. These come straight off
    `backtest.fills.PROFILES`, the object the run is billed from.

    `swap_*_points` are null when the profile prices no overnight financing. `spread` is in price
    units and is BAR-MODE only — tick mode has the real bid and ask on every tick.
    """
    id: str
    spread: float
    commission_per_side_per_lot: float
    swap_long_points: Optional[float] = None
    swap_short_points: Optional[float] = None
    contract_size: float


class HistoryLimit(BaseModel):
    """How far back a backtest of a given (instrument, timeframe, runner) may start.

    Served by `GET /backtests/history-limit` so the date picker's minimum comes from the
    same declaration `backtest/data/history.py` enforces — a second hardcoded date in the
    frontend would drift, and the drift would show up as a run that passes the UI and
    then 400s (or, before this existed, one that silently replayed substituted bars).
    A null response means no declared floor, not "unlimited".
    """
    instrument: str
    runner: str
    timeframe_minutes: int
    earliest_date: str          # 'YYYY-MM-DD' — the first date with REAL bars
    broker: str = ""            # the terminal's server, e.g. 'VantageMarkets-Demo'
    verified: str = ""          # when the floor was last measured
    source: str = ""            # 'probed' (measured off this broker) | 'seed' (offline fallback)
    note: str = ""              # plain-English reason, shown under the date field


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
    # The SAME worst drawdown as a percent of the peak it fell from. Shipped on the summary
    # because the list is where runs get compared, and $1.7M of drawdown beside $14M of profit
    # reads as ~12% when the honest figure is 56%. A negative value is the backfill's
    # "measured, no answer" sentinel — see lab_db._backfill_run_shape_metrics.
    max_drawdown_pct: Optional[float] = None
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
    # `None` = a run made before layers existed, which is NOT the same as an empty list ("charged
    # nothing on purpose"). The page must be able to say which, so the Optional is load-bearing.
    cost_layers: Optional[list[str]] = None
    broker_profile: Optional[str] = None
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
    # Added 2026-08-01 — the companions to three numbers that were true and got misread.
    # Reasoning for each is in services/metrics.py; in one line: a drawdown in dollars only hides
    # its own magnitude, a win rate counts a breakeven scratch as a win, and a concentration
    # measured over QUARTERS answers a different question from the one its name suggests.
    max_drawdown_pct: Optional[float] = None      # worst drop as % of the peak it fell from
    scratch_count: Optional[int] = None           # trades under 15% of the run's median full loss
    trade_concentration_pct: Optional[float] = None   # top-5 winners' share of gross profit
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


class RepricedPoint(BaseModel):
    """One trade on the re-priced equity curve. Mirrors the `EquityPoint` fields the charts read,
    so the frontend can swap this in where the stored curve was without a second code path."""
    index: int
    equity: float
    profit: float
    r: float
    r_before: float
    cost_usd: float


class RunRepriceReport(BaseModel):
    """A completed run's trades re-priced at a different cost profile, WITHOUT replaying it.

    Post-processing off the stored equity curve, in the same spirit as `RunNewsReport` — but the
    two answer different kinds of question and the distinction is what decides where a control
    belongs. The news filter REMOVES trades the run already made, so every number it produces is
    still derived from that run. A cost changes what the trades would have been, so this can only
    exist because each chargeable cost is, in R, independent of position size (see
    `backtest/reprice.py`). Where that stops being true — `bid_ask_fills`, which changes WHICH
    setups fill — the layer is refused and named in `needs_rerun` rather than approximated.

    ⚠ `is_exact` False means the figures are ~0.02%-0.3% off a real replay, never that they are
    indicative. It is False for two distinct reasons — a `swap` layer (whose real charge depends on
    which bars existed) or a run predating the stored `r`/`risk_usd` — and the UI must caption it.
    """
    layers: list[str] = []
    broker_profile: str
    is_exact: bool
    derived_basis: bool = False          # run predates the stored per-trade R
    approximate_layers: list[str] = []   # chosen layers that cannot be exact (today: swap)
    needs_rerun: list[str] = []          # requested layers that cannot be re-priced at all
    #: Layers the RUN ITSELF already charged at replay time, so they are baked into the stored
    #: trades. Re-pricing one on top would bill it TWICE, and the page has no way to notice: the
    #: numbers would move by a plausible amount and simply be wrong. They are reported, dropped
    #: from `layers`, and the UI shows them as already-on rather than as available to tick.
    #: ⚠ There is no way to charge one OFF from here either — the stored trades were measured with
    #: it, so removing it is a re-run, not arithmetic.
    already_charged: list[str] = []
    initial_capital: float
    final_equity: float
    sum_r: float
    total_cost_usd: float
    total_cost_r: float = 0.0
    #: Every re-priceable layer's own price in R, ticked or not, so the UI can show what turning
    #: one on would cost before it is turned on. **R, not dollars, and that is load-bearing:**
    #: charging a layer changes the balance and therefore every later position's SIZE, so a layer's
    #: dollar cost depends on which others are on and three dollar figures would not sum to the
    #: total beneath them. In R the size cancels and they add up exactly.
    layer_cost_r: dict[str, float] = {}
    trades: list[RepricedPoint] = []


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
    # Both LocalForwards are bound — i.e. the tunnel process is really holding
    # them. Until 2026-08-02 this field carried a fresh `ssh echo ok`, which has
    # nothing to do with the forwards and could report green over a dead tunnel.
    ssh_tunnel: bool = False
    vps_reachable: bool = False   # the VPS answers SSH at all — separates a dead tunnel from a dead network
    nt8_agent: bool = False    # NT8 agent (port 8765)
    mt5_agent: bool = False    # MT5 agent (port 8766)
    # MT5 TERMINAL state, not the agent's. None = the agent could not be asked,
    # which is not the same as a disconnected terminal and must not render as one.
    mt5_connected: Optional[bool] = None
    mt5_server: Optional[str] = None
    mt5_account: Optional[int] = None
    # ⚠ `None` = the NT8 agent could not be ASKED, which is not the claim
    # "NinjaTrader is not running". Read `=== false` on the frontend, never
    # falsy — the same contract `mt5_connected` above carries, and for the same
    # reason: an unanswered question rendered as a failure invents a measurement.
    nt8_running: Optional[bool] = None
    nt8_sa_visible: Optional[bool] = None
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
    # 0/0 by design (2026-08-01, Aaron's call). A request model's default is what ships when the
    # caller states nothing, and a silent 2.25/1 — a FUTURES prop-firm figure — was reaching forex
    # and Python runs that have no such cost. State the costs you want charged; nothing is assumed.
    commission_per_side: float = 0.0
    slippage_ticks: int = 0
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

    # Which of the two things this stack IS. They answer different questions and must not be
    # confused for one another:
    #   "screen" — N standalone runs added together. Fast, reuses finished runs, and every leg
    #              traded a full account with nothing able to block it, so it is an UPPER BOUND.
    #   "shared" — one balance and one risk budget the legs COMPETE for, replayed together on a
    #              merged clock. This is the demo-account question.
    # ⚠ Default "screen", deliberately. It is what every stack in this app has always been, and
    # a caller that states nothing must keep getting the behaviour it already had.
    mode: str = "screen"
    # The shared account. Read ONLY when mode == "shared"; ignored on a screen, where there is
    # no account because each leg had its own.
    account_size: float = 10_000.0
    risk_cap_pct: float = 10.0              # max OPEN risk across all legs, % of the LIVE balance
    entry_floor_pct: float = 0.0            # skip an entry granted less than this % in risk

    @field_validator("mode")
    @classmethod
    def _known_mode(cls, v: str) -> str:
        if v not in ("screen", "shared"):
            raise ValueError('mode must be "screen" or "shared"')
        return v

    @field_validator("risk_cap_pct")
    @classmethod
    def _positive_cap(cls, v: float) -> float:
        # A cap of zero refuses every entry, which is not a portfolio — it is a stopped bot, and
        # it would render as a completed stack that took no trades. `run_stack` raises on it; the
        # refusal is repeated here so it is a 400 at the request rather than a failed background
        # job the reader has to open a log to understand.
        if v <= 0:
            raise ValueError("risk_cap_pct must be greater than 0 — a cap of zero refuses "
                             "every entry, which is a stopped bot rather than a portfolio")
        return v


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
    # A SHARED stack reuses nothing — a finished standalone run was measured on its own full
    # account with nothing able to block it, so dropping one in would put an un-contended leg
    # beside contended ones. The preview has to say that, or the modal offers a reuse count for
    # a run that will re-run every leg regardless.
    mode: str = "screen"


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
    # A screen and a shared simulation are different experiments over the same legs, so the row
    # has to say which. Without it two rows sit side by side reporting different numbers with
    # nothing on screen explaining the gap.
    mode: str = "screen"
    risk_cap_pct: Optional[float] = None     # None on a screen — there is no account to cap


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
    # The SOLO CONTROL's book — this leg replayed ALONE on its own full account, which is the only
    # answer to "what would this have made if the other strategies never existed". On a SHARED stack
    # the two curves hold the same trades at the same R and wildly different DOLLARS, because the
    # shared one is sized off a balance every leg compounded onto (measured: 17.8674R either way,
    # $47,758,999 vs $21,064). `None` = not stored — a screen has no control, and a shared stack run
    # before 2026-08-10 kept only the scalars. It must never be rendered as a leg that made nothing.
    solo_equity_curve: Optional[list[EquityPoint]] = None
    solo_daily_pnl: Optional[list[dict]] = None


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
    # ── Shared-account mode ──────────────────────────────────────────────────
    mode: str = "screen"
    account_size: Optional[float] = None     # None on a screen: each leg had its own account
    risk_cap_pct: Optional[float] = None
    entry_floor_pct: Optional[float] = None


class StackContentionEvent(BaseModel):
    """One entry the shared risk budget refused or shrank."""
    leg: str
    time: Optional[int] = None               # epoch ms
    blocked: bool = False                    # False = shrunk to fit, True = refused outright
    desired_risk: float = 0.0
    granted_risk: float = 0.0


class StackLegContention(BaseModel):
    strategy_id: str
    run_id: str
    shared_trades: int = 0
    shared_r: float = 0.0
    solo_trades: int = 0
    solo_r: float = 0.0
    solo_closing_balance: float = 0.0
    shrunk: int = 0
    blocked: int = 0
    risk_refused: float = 0.0


class StackSharedReport(BaseModel):
    """What the shared account actually did — the answer a screen cannot give.

    ⚠ `events: []` with `summary` present is a REAL RESULT and the most likely one: open risk is
    measured to each trade's CURRENT stop, so a stop moved to breakeven releases its room, and
    the measured 6.5-year two-bot run refused nothing at all. Read an empty log as *the budget
    would rarely have had anything to arbitrate*, never as *the cap is not working* — and never
    as *not measured*, which is what a missing `summary` means instead.
    """
    stack_id: str
    available: bool                          # False = this stack is a screen, or has not finished
    opening_balance: Optional[float] = None
    closing_balance: Optional[float] = None
    risk_cap_pct: Optional[float] = None
    entry_floor_pct: Optional[float] = None
    peak_open_risk_pct: Optional[float] = None
    peak_concurrent_legs: Optional[int] = None
    leg_count: Optional[int] = None
    combined_trades: Optional[int] = None
    combined_r: Optional[float] = None
    contention_events: Optional[int] = None
    legs: list[StackLegContention] = []
    events: list[StackContentionEvent] = []
    neutral: Optional[dict] = None           # the shared-vs-solo R check; see portfolio_runner
    progress: Optional[dict] = None          # live while replaying: {phase, pct, message}


# ── Lab — optimizations ───────────────────────────────────────────────────────

class OptimizationRequest(BaseModel):
    strategy_id: str
    instrument: str
    bar_type: str = "Minute"
    bar_value: int = 5
    start_date: str
    end_date: str
    # 0/0 by design (2026-08-01, Aaron's call). A request model's default is what ships when the
    # caller states nothing, and a silent 2.25/1 — a FUTURES prop-firm figure — was reaching forex
    # and Python runs that have no such cost. State the costs you want charged; nothing is assumed.
    commission_per_side: float = 0.0
    slippage_ticks: int = 0
    ruleset_id: Optional[str] = None    # null for MT5 / "raw" mode
    mode: str = "eval"                  # "eval" | "funded" | "raw"
    search_method: str = "native"
    param_grid: dict                    # {param: {min, max, step} | [val, ...]}
    source_run_id: Optional[str] = None
    regime_filter: Optional[str] = None  # TRENDING | TRANSITIONING | RANGING | HIGH_VOLATILITY | LOW_VOLATILITY
    # Layered costs, same contract as BacktestRunRequest — python runner only, and NULL is not
    # []: nothing stated keeps the old free-book behaviour rather than silently charging.
    cost_layers: Optional[list[str]] = None
    broker_profile: Optional[str] = None
    # A combo below this trade count is still run, scored and listed — it just cannot WIN.
    # 0 = no floor, which is what a caller stating nothing gets (nothing is assumed, the same
    # rule the 0/0 commission default follows). The optimize modal states it explicitly.
    min_trades: int = 0


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
    runner: str = "ninjatrader"
    strategy_name: Optional[str] = None
    winner_note: Optional[str] = None
    grid_sensitivity_score: Optional[float] = None


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
    source_run_id: Optional[str] = None
    cost_layers: Optional[list[str]] = None
    broker_profile: Optional[str] = None
    min_trades: int = 0
    # Set when the ★ was picked by a fallback rather than by the rule the page names.
    winner_note: Optional[str] = None
    # How isolated the winner is in the grid: 0 = a flat plateau (robust), 1 = a lone spike
    # (overfit). Computed on every native run since the grid-sensitivity pass landed and stored
    # on the row ever since — nothing displayed it until 2026-08-04, which made it the one
    # number the page exists to produce and the one number it did not show.
    grid_sensitivity_score: Optional[float] = None
    grid_sensitivity_summary: Optional[dict] = None


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
    """⚠ Every count here is BOUNDED, and the bounds are the point.

    `run_monte_carlo` allocates `(num_simulations, n_trades)` float64 arrays — several of them —
    so an extra typed zero is not a slow test, it is gigabytes in a worker thread. That is the same
    shape as the optimizer's `step: 0`, which hung the entire backend until 2026-08-04, and the
    same fix: refuse it at the REQUEST, before anything is allocated. `walk_forward_windows` is
    bounded for a different reason — each window is TWO real backtests on the VPS, so the number
    is a multiplier on wall-clock time and on the platform lock.
    """
    run_id: str
    ruleset_id: Optional[str] = None
    include_walk_forward: bool = False
    include_sensitivity: bool = False
    num_simulations: int = Field(10_000, ge=100, le=100_000)
    num_bootstrap: int = Field(1_000, ge=100, le=100_000)
    walk_forward_windows: int = Field(5, ge=2, le=20)


class WalkForwardWindow(BaseModel):
    """⚠ Every field the engine writes must be DECLARED here or Pydantic drops it silently on the
    way to the browser — the trap `entry_ms`, `exit_ms` and `favorable`/`adverse` each hit on
    `EquityPoint`. `is_trades`/`oos_trades` were written by the engine and missing here, so the
    page could never show that a window's out-of-sample half closed six trades — the single most
    important fact about a walk-forward on a low-frequency strategy, and the reason its degradation
    is refused. `is_pf`/`oos_pf` are the NATIVE path's metric (it has no trade-level data, so it
    degrades on profit factor and leaves both Sharpes null), so without them that path had nothing
    renderable at all."""
    window: int
    is_pnl: Optional[float] = None
    oos_pnl: Optional[float] = None
    is_sharpe: Optional[float] = None
    oos_sharpe: Optional[float] = None
    is_trades: Optional[int] = None
    oos_trades: Optional[int] = None
    is_pf: Optional[float] = None
    oos_pf: Optional[float] = None


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
    # The same drawdowns against the ACCOUNT, as a percent, and which of the two bases the grade
    # read. Percent once the run compounds (a fixed dollar limit stops being comparable to a
    # growing account); dollars otherwise. Null on fixed-size runs and on rows predating this.
    # These MUST be declared here or Pydantic drops them silently on the way to the browser —
    # the same trap `entry_ms` and `favorable`/`adverse` hit on EquityPoint.
    median_max_dd_pct: Optional[float] = None
    pct5_max_dd_pct: Optional[float] = None
    pct1_max_dd_pct: Optional[float] = None
    dd_basis: Optional[str] = None
    prob_breach: Optional[float] = None
    prob_pass_eval: Optional[float] = None
    walk_forward_windows: int = 5
    walk_forward_summary: Optional[list[WalkForwardWindow]] = None
    walk_forward_degradation: Optional[float] = None
    sensitivity_summary: Optional[dict] = None
    sensitivity_max_degradation: Optional[float] = None
    # What the sensitivity phase could NOT measure. A page reporting "12 params tested" over a run
    # that refused 30 shifts is describing coverage that never happened.
    sensitivity_coverage: Optional[dict] = None
    # Which phases were ASKED for, and which of them failed. The ONLY thing separating "walk-forward
    # was not requested" from "walk-forward ran and crashed" — a NULL summary means both, and
    # grading read both as not-run, so a failed phase cost the test nothing and left no mark.
    phases_requested: Optional[list[str]] = None
    phase_failures: Optional[dict[str, str]] = None
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
    # A results file that is PRESENT and unreadable is not the same fact as one that was never
    # written, and both used to arrive as `None` — so a corrupt result rendered as a test that
    # simply had no chart. Same rule as `mt5_link`: never let "no" and "cannot ask" be one value.
    results_error: Optional[str] = None


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
    # ⚠ `None` = the agent for this platform could not be reached, so whether the
    # file is on the VPS is UNKNOWN. `False` is the positive claim that it is
    # missing — a real and alarming state — and collapsing the two would render
    # an unreachable agent as a deleted deployment (or, as it did before this,
    # render nothing at all and let a stale green "In sync" stand).
    file_exists_on_vps: Optional[bool] = None
    file_size_bytes: Optional[int] = None
    file_modified_at: Optional[str] = None
    # `None` for the same reason: it is `file_exists_on_vps AND not needs_deploy`,
    # so it cannot be answered when the first term cannot be.
    in_sync: Optional[bool] = None
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


class StrategyFilesResponse(BaseModel):
    """The VPS file listing, WITH which platform failed to answer.

    ⚠ An envelope rather than a bare list, because the two failures are not the
    same fact: an empty `files` with both errors null means the VPS genuinely
    holds no strategy files, and an empty `files` with `nt8_error` set means
    nobody asked it. Returning `[]` for both is what let the Deployed tab render
    "No files deployed — drop a strategy file above" over an unreachable box.
    """
    files: list[StrategyFile] = []
    nt8_error: Optional[str] = None
    mt5_error: Optional[str] = None


class StrategyFileSyncResponse(BaseModel):
    """Per-strategy sync state, WITH which platform could not be reached.

    The rows are still served when an agent is down: `needs_deploy` and
    `needs_compile` are computed from the LOCAL source hash and this app's own
    deploy record, so they remain true and useful. Only the questions that
    genuinely need the agent (`file_exists_on_vps`, `in_sync`, and MT5's
    `is_compiled`) go `None`.
    """
    statuses: list[StrategyFileSyncStatus] = []
    nt8_error: Optional[str] = None
    mt5_error: Optional[str] = None


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


class CalendarCurrencies(BaseModel):
    """The ISO currencies the calendar's own query can return, in query order.

    Served so the page's currency chips are DERIVED from the backend's country list rather than
    hand-copied beside it. The two are different namespaces — TradingView is queried by bloc code
    (US/EU/GB) and answers with a currency (USD/EUR/GBP) — so only the backend can state this."""
    currencies: list[str] = []
