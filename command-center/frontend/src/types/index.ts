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

export interface BotStatus {
  name: string
  account: string
  account_type: 'demo' | 'live'
  balance: number | null
  status: 'RUNNING' | 'STOPPED' | 'ERROR'
  uptime_seconds: number | null
  daily_pnl_pct: number | null
  day_locked: boolean
}

export interface BotSnapshot {
  fetched_at: string
  bots: BotStatus[]
  scheduled_jobs: JobStatus[]
  telegram: ProcessStatus
}

// ── Backtests ────────────────────────────────────────────────────────────────

export interface BacktestResult {
  strategy: string
  instrument: string
  verdict: 'KEEP' | 'WARN' | 'DISCARD'
  max_drawdown: number
  max_loss_limit: number
  drawdown_pass: boolean
  eval_result: 'would_pass' | 'would_fail'
  eval_days: number | null
  daily_pnl: number[]
  worst_day: number
  worst_losing_streak: number
  win_rate: number
  profit_factor: number
  avg_win: number
  avg_loss: number
  trade_count: number
  expectancy: number
  total_return: number
  cagr: number
  sharpe: number
  sortino: number
  avg_trade_duration_min: number
  equity_curve: EquityPoint[]
}

export interface BacktestRun {
  run_id: string
  generated_at: string
  combos: BacktestResult[]
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
