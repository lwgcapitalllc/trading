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
  direction?: 'Long' | 'Short'
  profit?: number
  exit_name?: string
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

export interface ParamSchemaEntry {
  name: string
  type: string
  min?: number
  max?: number
  default: unknown
  group: string
  display_name: string
  description?: string
}

export interface Strategy {
  id: string
  name: string
  class_name: string
  source_path: string
  category: string | null
  suggested_instrument: string | null
  default_params: Record<string, unknown>
  param_schema: ParamSchemaEntry[]
  scanned_at: string
  run_count: number
  runner: string
}

export interface ScanResult {
  scanned: number
  added: number
  updated: number
  skipped: number
}

// ── Lab — Firms ───────────────────────────────────────────────────────────────

export interface Firm {
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
  max_contracts: Record<string, unknown>
  platform_support: string[]
  account_tier: 'eval' | 'funded'
  docs_url: string | null
  notes: string | null
}

export type FirmCreate = Firm

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
  evaluate_firms: string[]
}

export interface VerdictSummary {
  firm_id: string
  verdict: 'PASS' | 'WARN' | 'DISCARD'
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
}

export interface EvaluationDetail {
  eval_id: string
  firm_id: string
  firm_name: string
  verdict: 'PASS' | 'WARN' | 'DISCARD'
  drawdown_pass: boolean
  target_pass: boolean
  consistency_pass: boolean | null
  simulated_eval_days: number | null
  breach_count: number
  largest_day_share_pct: number | null
  firm_max_loss_eod: number
  firm_profit_target: number
  firm_consistency_pct: number | null
  notes: string | null
}

export interface DailyPnlPoint {
  date: string
  pnl: number
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
  completed_at: string | null
  net_pnl: number | null
  max_drawdown: number | null
  profit_factor: number | null
  win_rate: number | null
  win_count: number | null
  trade_count: number | null
  sharpe: number | null
  sortino: number | null
  cagr: number | null
  avg_win: number | null
  avg_loss: number | null
  avg_trade_duration_min: number | null
  worst_day_pnl: number | null
  worst_losing_streak: number | null
  equity_curve: EquityPoint[]
  daily_pnl: DailyPnlPoint[]
  evaluations: EvaluationDetail[]
  worthiness: WorthinessScore | null
  sweep_id: string | null
  optimization_id: string | null
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
  vps_agent: boolean
  nt8_running: boolean
  nt8_sa_visible: boolean
  last_compile_ok: boolean
  last_compile_at: string | null
  last_compile_errors: string[]
  checked_at: string
}

// ── Stress Tests ─────────────────────────────────────────────────────────────

export interface StressTestResult {
  strategy: string
  instrument: string
  runs: number
  max_dd_median: number
  max_dd_p95: number
  max_dd_p99: number
  prob_breach: number
  prob_pass_eval: number
  final_pnl_median: number
  final_pnl_p10: number
  final_pnl_worst: number
  equity_paths: EquityPoint[][]
}

// ── App Settings ─────────────────────────────────────────────────────────────

export interface AppSettings {
  monorepo_root: string
  smart_money_root: string
  smart_money_config_path: string
  smart_money_reports_dir: string
  instances_dir: string
  ssh_alias: string
  vps_agent_tunnel: string
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
  firm_ids: string[]
  instruments: string[]
}

export interface SweepResponse {
  sweep_id: string
  run_ids: string[]
  status: string
}

export interface SweepDetail {
  sweep_id: string
  strategy_id: string
  strategy_name: string
  start_date: string
  end_date: string
  firm_ids: string[]
  total_instruments: number
  completed_instruments: number
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
  firm_id: string
  mode: 'eval' | 'funded'
  search_method: 'auto' | 'brute' | 'genetic'
  param_grid: Record<string, ParamAxisSpec>
}

export interface OptimizationSummary {
  optimization_id: string
  strategy_id: string
  instrument: string
  start_date: string
  end_date: string
  firm_id: string
  mode: string
  search_method: string
  status: string
  estimated_runs: number
  completed_runs: number
  best_run_id: string | null
  created_at: string
  completed_at: string | null
}

export interface OptimizationDetail extends OptimizationSummary {
  strategy_name: string
  param_grid: Record<string, ParamAxisSpec>
  runs: BacktestSummary[]
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
