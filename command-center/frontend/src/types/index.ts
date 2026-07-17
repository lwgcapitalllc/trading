// Mirror of backend models.py — these are the data contract.

export interface MonthlyPoint {
  month: string
  value: number
}

export interface RankedItem {
  label: string
  count: number
  win_rate?: number
}

export interface EquityPoint {
  index: number
  equity: number
  date?: string
  entry_ms?: number | null   // trade OPEN time, UTC epoch ms — what the news filter tags against
  direction?: 'Long' | 'Short'
  profit?: number
  exit_name?: string
  favorable?: number   // most this trade was ever showing in profit before it closed (≥0)
  adverse?: number     // deepest it sat against us before it closed (≤0)
}

// Post-run news/holiday tagging of a run's trades (GET /backtests/runs/{id}/news).
// The lab runs backtests raw; this marks which trades opened in a news window / on a bank holiday
// so the UI can remove them and recompute KPIs live. Mirrors backend models.NewsTradeTag / RunNewsReport.
export interface NewsTradeTag {
  index: number | null
  entry_ms: number | null
  in_coverage: boolean
  in_news: boolean       // opened inside a high-impact news window — the toggle removes these
  in_holiday: boolean    // opened on a bank holiday — always removed, not part of the toggle
  title: string | null
}

export interface RunNewsReport {
  has_data: boolean                  // false when the calendar cache is empty → filter inert
  coverage_start_ms: number | null   // earliest ms with news data — the "news starts here" boundary
  coverage_end_ms: number | null
  pre_minutes: number
  post_minutes: number
  trades: NewsTradeTag[]
  news_trade_count: number
  holiday_trade_count: number
}

// One trading day of a SIZED run — the dynamic-sizing engine's day-by-day record
// (mirrors backend SizedTimelineDay / sizing_engine.DayTimeline). Drives the sized
// equity curve (eod_balance vs risk_floor) and the timeline view.
export interface SizedTimelineDay {
  date: string
  trades_taken: number
  contracts_total: number
  day_pnl: number
  eod_balance: number
  risk_floor: number | null
  floor_distance: number | null
  consistency_share_pct: number | null
  halt_reason: string | null
}

export interface JobStatus {
  name: string
  schedule: string
  status: 'RUNNING' | 'STOPPED' | 'UNKNOWN'
}

export interface ProcessStatus {
  name: string
  status: 'RUNNING' | 'STOPPED' | 'UNKNOWN'
}

// ── Smart Money ────────────────────────────────────────────────────────────

export interface FunnelStage {
  label: string
  count_in: number
  count_out: number
}

export interface SmartMoneyRun {
  run_id: string
  generated_at: string
  total_scanned: number
  total_qualified: number
  by_market: Record<string, number>
  by_source: Record<string, number>
  funnel: FunnelStage[]
}

export interface SmartMoneyRunSummary {
  run_id: string
  generated_at: string
  total_qualified: number
}

export interface SmartMoneyConfig {
  min_trades: number
  min_win_rate_pct: number
  max_drawdown_pct: number
  min_active_weeks_per_month: number
  max_single_trade_pnl_share_pct: number
  max_avg_hold_hours: number
  min_account_age_days: number
  lookback_min_days: number
  lookback_preferred_days: number
  lookback_elite_days: number
  weight_winrate_consistency: number
  weight_risk_adjusted_return: number
  weight_exit_efficiency: number
  weight_trade_frequency: number
  weight_instrument_consistency: number
  strike_months_to_yellow: number
  strike_months_to_disqualify: number
  strike_months_to_reinstate: number
}

export interface ConfigGitStatus {
  file_path: string
  is_dirty: boolean
  last_commit_hash: string | null
  last_commit_message: string | null
  last_commit_at: string | null
}

export interface Candidate {
  rank: number
  id: string
  market: string
  source: string
  composite_score: number
  lookback_tier: string | null
  lookback_span_days: number | null
  score_breakdown: Record<string, number>
  // leaderboard stats (real values from exchange)
  account_value: number | null
  all_time_pnl: number | null
  all_time_roi: number | null     // fractional, e.g. 3.9 = 390%
  month_roi: number | null
  week_roi: number | null
  // pnl from our fill analysis window
  cum_pnl_usd: number
  monthly_balance: MonthlyPoint[]
  overall_win_rate: number
  monthly_win_rate: MonthlyPoint[]
  win_rate_trend: 'improving' | 'stable' | 'declining'
  avg_win: number
  avg_loss: number
  avg_rr: number | null
  peak_drawdown: number
  trade_count: number
  preferred_days: RankedItem[]
  preferred_instruments: RankedItem[]
  typical_entry_hour_utc: number | null
  avg_hold_time_hours: number | null
  exit_efficiency: number | null
  yellow_flag_count: number
  window_count: number
  windows_below_threshold: number
  is_shortlist: boolean
}

export interface ScanEntry {
  a: string   // wallet address
  s: string   // "pass" | "fail"
}

export interface RunProgress {
  run_id: string
  status: 'idle' | 'running' | 'complete' | 'error'
  stage: number
  stage_name: string
  phase: string
  pct: number
  wallets_scanned: number
  wallets_total: number
  qualified_so_far: number
  disqualified_so_far: number
  message: string
  started_at: string | null
  updated_at: string | null
  elapsed_seconds: number
  recent_addresses: ScanEntry[]
}

export interface DisqualifiedCandidate {
  id: string
  market: string
  source: string
  reason: string
  stage: string
}

export interface CacheStats {
  wallets_cached: number
  oldest_fetched_at: number | null
  newest_fetched_at: number | null
}

export interface CacheClearResult {
  cleared: number
}

// ── Bots ────────────────────────────────────────────────────────────────────

export interface TelegramUser {
  chat_id: string
  name: string
  role: 'admin' | 'readonly'
  added: string
}

export interface TelegramUserCreate {
  chat_id: string
  name: string
  role: string
}

export interface BotStatus {
  name: string
  account: string
  account_type: 'demo' | 'live'
  balance: number | null
  status: 'RUNNING' | 'STOPPED' | 'ERROR'
  uptime_seconds: number | null
  total_pnl_pct: number | null
  day_locked: boolean
  // detail fields
  daily_pnl: number | null
  daily_pnl_pct: number | null
  weekly_pnl: number | null
  weekly_pnl_pct: number | null
  peak_balance: number | null
  trades_today: number | null
  lock_reason: string | null
  last_updated: string | null
  daily_goal_pct: number | null
  daily_cap_pct: number | null
  weekly_cap_pct: number | null
}

export interface BotSnapshot {
  fetched_at: string
  bots: BotStatus[]
  scheduled_jobs: JobStatus[]
  telegram: ProcessStatus
}

export interface BotConfigSections {
  risk: Record<string, unknown>
  protection: Record<string, unknown>
  strategy: Record<string, unknown>
  regime: Record<string, unknown>
  dead_zone: Record<string, unknown>
}

export interface BotConfigUpdate {
  risk?: Record<string, unknown>
  protection?: Record<string, unknown>
  strategy?: Record<string, unknown>
  regime?: Record<string, unknown>
  dead_zone?: Record<string, unknown>
  deploy?: boolean
}

// ── Lab — Strategies ─────────────────────────────────────────────────────────

// How a run's position size is decided. 'consistent'/'bullet' are AUTOMATIC — the ruleset's
// rules decide. 'manual' means you set the risk % and it doesn't move. Mirrors the backend's
// sizing_engine.MODES. Irrelevant for a self_sizing strategy, which sizes its own trades.
export type SizingMode = 'consistent' | 'bullet' | 'manual'

export interface ParamSchemaEntry {
  name: string
  type: string
  min?: number
  max?: number
  default: unknown
  group: string
  display_name: string
  description?: string
  category?: 'strategy_logic' | 'foundational'
  // Closed set of legal values for a string param → renders a dropdown, never free text.
  // From the companion meta.json. Wins over `widget`.
  choices?: string[]
  // Editor metadata overlaid from a strategy's companion <Strategy>.meta.json (optional).
  label?: string            // friendly label, preferred over display_name
  desc?: string             // plain-English explanation for the explainer panel
  unit?: string             // e.g. "× ATR", "pips", "R"
  core?: boolean            // essential knob — shown in the Essentials card up front
  widget?: 'toggle' | 'switch' | 'time' | 'number' | 'text'
  options?: { off: string; on: string }   // labels for a bool rendered as a segmented toggle
  show_if?: Record<string, string | number | boolean>  // show only when another param equals a value
  guide?: [string, string]  // [what lowering does, what raising does]
  step?: number             // input step
}

export interface Strategy {
  id: string
  name: string
  class_name: string
  source_path: string
  category: string | null
  suggested_instrument: string | null
  description: string | null
  default_params: Record<string, unknown>
  param_schema: ParamSchemaEntry[]
  scanned_at: string
  run_count: number
  runner: string
  // Strategy-level narrative overlaid from <Strategy>.meta.json (optional).
  edge?: string | null
  steps?: StrategyStep[]
  avoid_news?: boolean   // News toggle starts on "Removed" when true (strategy avoids high-impact news)
  // True = the strategy sizes its own trades off its own risk % param, so the sizing engine
  // must not re-size it and SIZING MODE is hidden (there is nothing to choose).
  self_sizing?: boolean
}

export interface StrategyStep {
  label?: string    // e.g. "01 · Asian"
  title: string     // e.g. "Measure the range"
  detail?: string   // one-line explanation
}

export interface ScanResult {
  scanned: number
  added: number
  updated: number
  skipped: number
  orphans: string[]   // DB strategies whose source file is gone from the repo
  warnings: string[]
}

export interface ReconcileResult {
  removed: string[]   // orphaned strategies removed from DB + VPS
  warnings: string[]  // per-strategy notes (e.g. VPS file could not be deleted)
}

export interface DeployJobStatus {
  deploy_job_id: string
  strategy_id: string
  status: 'running' | 'complete' | 'failed'
  filename: string | null
  uploaded_size_bytes: number | null
  error: string | null
}

// ── Lab — Rulesets ────────────────────────────────────────────────────────────

export interface Ruleset {
  id: string
  name: string
  account_size: number
  profit_target: number
  max_loss_eod: number
  max_loss_intraday: number | null
  drawdown_type: string
  consistency_pct: number | null
  min_trading_days: number | null
  force_flat_time_et: string | null
  allowed_instruments: string[]
  max_contracts: Record<string, unknown> | null
  platform_support: string[]
  account_tier: string
  ruleset_type: 'prop_eval' | 'prop_funded' | 'personal' | 'demo'
  daily_loss_cap: number | null
  weekly_loss_cap: number | null
  daily_profit_goal: number | null
  description: string | null
  docs_url: string | null
  eval_cost_usd: number | null
  activation_fee_usd: number | null
  profit_split_pct: number | null
  notes: string | null
  // Pass 1 — foundational config
  risk_per_trade_pct: number | null
  max_consecutive_losses: number | null
  earliest_entry_time_et: string | null
  latest_entry_time_et: string | null
  days_of_week_allowed: string[]
  daily_profit_target: number | null
  daily_profit_lock_pct: number | null
  default_commission_per_side: number | null
  default_slippage_ticks: number | null
  daily_halt_fraction: number | null
  market: string    // "futures" | "forex"
  drawdown_unit: string
  // Personal fail conditions (personal/demo rows; null on prop rows)
  max_drawdown_from_peak_pct: number | null
  max_consecutive_loss_days: number | null
}

export type RulesetCreate = Ruleset

// PATCH /rulesets/{id} — personal/demo rows only; backend rejects anything else
export interface PersonalRulesetPatch {
  account_size?: number
  daily_loss_cap?: number
  daily_profit_target?: number
  max_drawdown_from_peak_pct?: number
  max_consecutive_loss_days?: number
}

// Backward-compat aliases — M3 only
export type Firm = Ruleset
export type FirmCreate = Ruleset

// ── Lab — Backtest Runs ───────────────────────────────────────────────────────

export interface BacktestRunRequest {
  strategy_id: string
  instrument: string
  params: Record<string, unknown>
  bar_type?: string
  bar_value?: number
  start_date: string
  end_date: string
  commission_per_side?: number
  slippage_ticks?: number
  evaluate_rulesets: string[]
  source_run_id?: string | null
  sizing_mode?: SizingMode
  manual_risk_pct?: number | null   // required when sizing_mode === 'manual'
}

export interface VerdictSummary {
  ruleset_id: string
  verdict: 'PASS' | 'WARN' | 'DISCARD' | 'INFO'
  notes: string | null
}

export interface WorthinessScore {
  tier: 'TIER_1_STRESS_TEST' | 'TIER_2_OPTIMIZE' | 'TIER_3_DISCARD'
  reason: string | null
  computed_against_firm: string | null
}

export interface BacktestSummary {
  run_id: string
  strategy_id: string
  strategy_name: string
  instrument: string
  status: string
  created_at: string
  started_at: string | null
  completed_at: string | null
  net_pnl: number | null
  max_drawdown: number | null
  profit_factor: number | null
  win_rate: number | null
  trade_count: number | null
  sharpe: number | null
  params: Record<string, unknown>
  verdicts: VerdictSummary[]
  worthiness: WorthinessScore | null
  sweep_id: string | null
  optimization_id: string | null
  source_run_id: string | null
  error_message: string | null
  start_date: string | null
  end_date: string | null
  runner: string
}

export interface EvaluationDetail {
  eval_id: string
  ruleset_id: string
  ruleset_name: string
  verdict: 'PASS' | 'WARN' | 'DISCARD' | 'INFO'
  drawdown_pass: boolean
  target_pass: boolean
  consistency_pass: boolean | null
  simulated_eval_days: number | null
  breach_count: number
  largest_day_share_pct: number | null
  firm_max_loss_eod: number
  firm_profit_target: number
  firm_consistency_pct: number | null
  // Ruleset context — personal/demo cards render personal chips, never the $0 sentinel
  ruleset_type: 'prop_eval' | 'prop_funded' | 'personal' | 'demo'
  personal_daily_loss_cap: number | null
  personal_max_drawdown_from_peak_pct: number | null
  personal_max_consecutive_loss_days: number | null
  notes: string | null
  // Per-ruleset sized results — each firm's own contract ladder sizes the run differently,
  // so its KPIs, daily P&L and sized timeline differ. Populated only for sized runs; null/empty
  // on unit-size runs (the UI falls back to the run-level headline).
  net_pnl: number | null
  max_drawdown: number | null
  profit_factor: number | null
  win_rate: number | null
  trade_count: number | null
  avg_win: number | null
  avg_loss: number | null
  daily_pnl: DailyPnlPoint[]
  sized_timeline: SizedTimelineDay[]
  equity_curve: EquityPoint[]              // sized trade-by-trade curve (drawdown, long/short, calmar…)
}

export interface DailyPnlPoint {
  date: string
  pnl: number
  regime_tag?: string
}

export interface RegimeBreakdownRow {
  regime: string
  days: number
  trades: number
  net_pnl: number
  win_rate: number | null
  profit_factor: number | null
  worst_day: number | null
}

export interface BacktestDetail {
  run_id: string
  strategy_id: string
  strategy_name: string
  instrument: string
  params: Record<string, unknown>
  bar_type: string
  bar_value: number
  start_date: string
  end_date: string
  commission_per_side: number
  slippage_ticks: number
  status: string
  error_message: string | null
  created_at: string
  started_at: string | null
  completed_at: string | null
  net_pnl: number | null
  max_drawdown: number | null
  profit_factor: number | null
  win_rate: number | null
  win_count: number | null
  trade_count: number | null
  sharpe: number | null               // canonical daily-√252 Sharpe
  platform_sharpe: number | null      // NT8/MT5's own reported Sharpe (reference)
  sharpe_low_sample: boolean          // < 10 trading days — daily Sharpe is noisy
  profit_concentration_pct: number | null  // backend-persisted; frontend prefers it when present
  sortino: number | null
  cagr: number | null
  avg_win: number | null
  avg_loss: number | null
  avg_trade_duration_min: number | null
  worst_day_pnl: number | null
  worst_losing_streak: number | null
  equity_curve: EquityPoint[]
  daily_pnl: DailyPnlPoint[]
  regime_breakdown: RegimeBreakdownRow[]
  evaluations: EvaluationDetail[]
  worthiness: WorthinessScore | null
  sweep_id: string | null
  optimization_id: string | null
  source_run_id: string | null
  runner: string
  sizing_mode: SizingMode              // engine sizing mode this run used
  manual_risk_pct?: number | null      // the risk % used, when sizing_mode === 'manual'
  sized: boolean                          // true once the engine sized the run (reshaped strategy emitted engine_trades)
  sized_timeline: SizedTimelineDay[]      // the engine's day-by-day record (sized runs only)
}

// ── Lab — Progress + System Health ───────────────────────────────────────────

export interface LabProgress {
  job_id: string | null
  job_type: string | null
  // 'idle' | 'running' | 'complete' | 'failed_timeout' | 'failed_unknown'
  status: string
  strategy_id: string | null
  instrument: string | null
  pct: number
  message: string
  started_at: string | null
  updated_at: string | null
  heartbeat_age_seconds: number
  error_message: string | null
}

export interface SystemHealth {
  backend: boolean
  ssh_tunnel: boolean
  nt8_agent: boolean   // NT8 agent (port 8765)
  mt5_agent: boolean   // MT5 agent (port 8766)
  nt8_running: boolean
  nt8_sa_visible: boolean
  last_compile_ok: boolean
  last_compile_at: string | null
  last_compile_errors: string[]
  checked_at: string
}

// ── Stress Tests ─────────────────────────────────────────────────────────────

export interface WalkForwardWindow {
  window: number
  is_pnl: number | null
  oos_pnl: number | null
  is_sharpe: number | null
  oos_sharpe: number | null
}

export interface SensitivityShift {
  // Perturbation sensitivity (run_sensitivity_task) — signed PnL delta vs baseline.
  run_id?: string
  new_value?: number
  pnl_delta?: number
  pnl_delta_pct?: number
  // Grid sensitivity (auto-injected from an optimization) — PF degradation (0..1, always ≥ 0).
  value?: number
  profit_factor?: number
  degradation?: number
}

export interface StressTest {
  stress_test_id: string
  run_id: string
  ruleset_id: string | null
  status: string
  created_at: number
  completed_at: number | null
  mc_completed_at: number | null
  wf_completed_at: number | null
  num_simulations: number
  num_bootstrap: number
  median_final_pnl: number | null
  pct5_final_pnl: number | null
  pct1_final_pnl: number | null
  median_max_dd: number | null
  pct5_max_dd: number | null
  pct1_max_dd: number | null
  prob_breach: number | null
  prob_pass_eval: number | null
  walk_forward_windows: number
  walk_forward_summary: WalkForwardWindow[] | null
  walk_forward_degradation: number | null
  sensitivity_summary: Record<string, Record<string, SensitivityShift>> | null
  sensitivity_max_degradation: number | null
  grade: 'A' | 'B' | 'C' | 'D' | 'F' | null
  grade_reasons: string[] | null
  equity_paths_path: string | null
  distribution_path: string | null
  error_message: string | null
  strategy_name: string | null
  strategy_id: string | null
  instrument: string | null
}

export interface StressTestDetail extends StressTest {
  equity_paths: number[][] | null
  distribution: {
    max_dd: { counts: number[]; edges: number[] }
    final_pnl: { counts: number[]; edges: number[] }
  } | null
}

export interface StressTestCreate {
  run_id: string
  ruleset_id?: string
  include_walk_forward: boolean
  include_sensitivity: boolean
  num_simulations: number
  num_bootstrap: number
  walk_forward_windows: number
}

export interface StressTestTriggerResponse {
  stress_test_id: string
  status: string
  estimated_duration_min: number | null
  notes: string[]
}

export interface StressLock {
  futures: boolean
  forex: boolean
  run_ids: string[]
}

// ── App Settings ─────────────────────────────────────────────────────────────

export interface AppSettings {
  monorepo_root: string
  smart_money_root: string
  smart_money_config_path: string
  smart_money_reports_dir: string
  instances_dir: string
  ssh_alias: string
  nt8_agent_tunnel: string
  mt5_agent_tunnel: string
}

// ── Lab — Sweeps ──────────────────────────────────────────────────────────────

export interface SweepRequest {
  strategy_id: string
  params: Record<string, unknown>
  bar_type?: string
  bar_value?: number
  start_date: string
  end_date: string
  commission_per_side?: number
  slippage_ticks?: number
  ruleset_ids: string[]
  instruments: string[]
  source_run_id?: string | null
}

export interface SweepResponse {
  sweep_id: string
  run_ids: string[]
  status: string
}

export interface SweepSummary {
  sweep_id: string
  strategy_id: string
  strategy_name: string
  start_date: string
  end_date: string
  total_instruments: number
  completed_instruments: number
  failed_instruments: number
  status: string
  created_at: string
  source_run_id: string | null
  best_worthiness: string | null
  ruleset_ids: string[]
}

export interface SweepDetail {
  sweep_id: string
  strategy_id: string
  strategy_name: string
  start_date: string
  end_date: string
  ruleset_ids: string[]
  total_instruments: number
  completed_instruments: number
  status: string
  created_at: string
  completed_at: string | null
  runs: BacktestSummary[]
}

// ── Lab — Optimizations ───────────────────────────────────────────────────────

export type ParamAxisSpec = { min: number; max: number; step: number } | unknown[]

export interface OptimizationRequest {
  strategy_id: string
  instrument: string
  bar_type?: string
  bar_value?: number
  start_date: string
  end_date: string
  commission_per_side?: number
  slippage_ticks?: number
  ruleset_id: string | null
  mode: 'eval' | 'funded' | 'raw'
  search_method: 'native'
  param_grid: Record<string, ParamAxisSpec>
  source_run_id?: string | null
  regime_filter?: string | null
}

export interface OptimizationSummary {
  optimization_id: string
  strategy_id: string
  instrument: string
  start_date: string
  end_date: string
  ruleset_id: string | null
  mode: string
  search_method: string
  status: string
  estimated_runs: number
  completed_runs: number
  best_run_id: string | null
  source_run_id: string | null
  regime_filter: string | null
  created_at: string
  completed_at: string | null
}

export interface OptimizationDetail extends OptimizationSummary {
  strategy_name: string
  param_grid: Record<string, ParamAxisSpec>
  runner: string
  runs: BacktestSummary[]
  live_pct: number | null
  live_message: string | null
}

// ── Lab — Instrument Summary ──────────────────────────────────────────────────

export interface InstrumentResult {
  instrument: string
  best_worthiness: string | null
  best_run_id: string | null
  tested_at: string | null
}

export interface InstrumentSummary {
  instrument_results: InstrumentResult[]
  untested_instruments: string[]
}

export interface RunningJobInfo {
  running: boolean
  job_type: 'backtest' | 'sweep' | 'optimization' | null
  job_id: string | null
  description: string | null
}

export interface RunningJobStatus {
  nt8: RunningJobInfo
  mt5: RunningJobInfo
  python: RunningJobInfo
}

// ── Strategy files (Pass 2 — deployment manager) ─────────────────────────────

export interface StrategyFile {
  filename: string
  size_bytes: number
  modified_at: string
  platform: string
}

export interface StrategyFileSyncStatus {
  strategy_id: string
  expected_filename: string
  file_exists_on_vps: boolean
  file_size_bytes: number | null
  file_modified_at: string | null
  in_sync: boolean
  is_compiled: boolean | null
  // Version tracking — which content version is local vs deployed vs compiled
  current_version: number | null
  current_source_hash: string | null
  deployed_version: number | null
  deployed_at: number | null
  compiled_version: number | null
  compiled_at: number | null
  needs_deploy: boolean
  needs_compile: boolean
}

export interface StrategyVersion {
  strategy_id: string
  version: number
  source_hash: string
  size_bytes: number | null
  created_at: number
}

export interface CompileJobStatus {
  compile_job_id: string
  status: 'running' | 'success' | 'failed'
  errors: string[]
  warnings: string[]
  started_at: number | null
  completed_at: number | null
}

// ── Job queue (Step 6) ────────────────────────────────────────────────────────

export interface QueueItem {
  queue_id: string
  job_type: 'optimization' | 'stress_test'
  payload: Record<string, unknown>
  status: 'pending' | 'running' | 'done' | 'failed'
  position: number
  created_at: number
  started_at: number | null
  finished_at: number | null
  error: string | null
}
