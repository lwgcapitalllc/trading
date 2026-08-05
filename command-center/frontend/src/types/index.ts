// Mirror of backend models.py — these are the data contract.
import type { ChartSpec } from '@/components/ChartPanel/types'

export interface MonthlyPoint {
  month: string
  value: number
}

export interface RankedItem {
  label: string
  count: number
  win_rate?: number
}

export interface RegimeDay {
  date: string
  regime: string
}

export interface EquityPoint {
  index: number
  equity: number
  date?: string
  entry_ms?: number | null   // trade OPEN time, UTC epoch ms — what the news filter tags against
  exit_ms?: number | null    // trade CLOSE time — with entry_ms, gives duration over any SUBSET
  direction?: 'Long' | 'Short'
  profit?: number
  exit_name?: string
  favorable?: number   // most this trade was ever showing in profit before it closed (≥0)
  adverse?: number     // deepest it sat against us before it closed (≤0)
  costs_usd?: number   // commission + swap + slippage charged to this trade (negative)
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

// How far back a backtest may start for a given instrument + timeframe + runner.
// MEASURED off the live broker terminal (probed by bar density, cached per broker), never
// hardcoded — so pointing the terminal at a broker with deeper history widens this by
// itself. `null` from the API means UNKNOWN (non-python runner, agent down, unidentified
// broker), and the UI must then leave the range open rather than guess.
export interface HistoryLimit {
  instrument: string
  runner: string
  timeframe_minutes: number
  earliest_date: string        // 'YYYY-MM-DD' — first date with REAL bars
  broker: string               // terminal server, e.g. 'VantageMarkets-Demo'
  verified: string             // when the floor was last measured
  source: string               // 'probed' | 'seed'
  note: string                 // plain-English reason, shown under the date field
}

/** A broker account's MEASURED cost facts, served by `GET /backtests/broker-profiles`.
 *  Never retype one of these numbers into a component — they come off the same object the
 *  runner bills from, which is what stops the page and the charge disagreeing. */
export interface BrokerProfile {
  id: string
  spread: number                     // price units, BAR MODE only (tick mode has the real book)
  commission_per_side_per_lot: number
  swap_long_points: number | null    // null = this profile prices no overnight financing
  swap_short_points: number | null
  contract_size: number
}

/** One trade on a re-priced equity curve — `GET /backtests/runs/{id}/repriced`. */
export interface RepricedPoint {
  index: number
  equity: number
  profit: number
  r: number
  r_before: number                   // the R the run stored, before this charge
  cost_usd: number
}

/** A completed run's trades re-priced at a different cost profile, without replaying it.
 *
 *  Sibling of `RunNewsReport`, and the difference between them is why costs are toggled here at
 *  all: the news filter REMOVES trades the run already made, while this changes what each trade
 *  would have been worth. That is only possible because every chargeable cost is, in R,
 *  independent of position size — see `backtest/reprice.py`.
 *
 *  ⚠ `is_exact` false does NOT mean indicative. It means ~0.02%–0.3% off a real replay, for one of
 *  two reasons the UI has to caption: a `swap` layer (whose real charge depends on which bars
 *  existed) or `derived_basis` (a run predating the stored per-trade R). */
export interface RunRepriceReport {
  layers: CostLayer[]
  broker_profile: string
  is_exact: boolean
  derived_basis: boolean
  approximate_layers: CostLayer[]
  needs_rerun: CostLayer[]           // asked for but un-repriceable — say so, never drop silently
  /** Layers the RUN ITSELF charged at replay time. Already baked into the stored trades, so
   *  re-pricing one on top would bill it twice; the server drops them from `layers` and the pill
   *  shows them as already-on. There is no way to charge one OFF from here — that is a re-run. */
  already_charged: CostLayer[]
  initial_capital: number
  final_equity: number
  sum_r: number
  total_cost_usd: number
  total_cost_r: number
  /** Each re-priceable layer's own price in R, ticked or not — what turning it on would cost.
   *  R rather than dollars because charging one layer changes the balance and so every later
   *  position's SIZE: dollar costs per layer would not sum to the total. In R they do. */
  layer_cost_r: Record<string, number>
  trades: RepricedPoint[]
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
  /** DISABLED is distinct from STOPPED: switched off deliberately, not broken. */
  status: 'RUNNING' | 'STOPPED' | 'DISABLED' | 'UNKNOWN'
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
  /** The bot's STABLE identifier (`mpc_sos_fade_demo`) — the same string on the VPS process
   *  commandline. Use it for URLs, selection state and API paths. `name` is a label chosen
   *  for a human, so it is the field that will eventually change, and anything keyed on it
   *  breaks when it does. Both are accepted by the API; new code passes the key. */
  key: string
  name: string
  account: string
  account_type: 'demo' | 'live'
  balance: number | null
  /** Is the bot's process still talking to its MT5 terminal?
   *
   *  `null` means UNANSWERED — a stopped bot, or one predating the field — and must never be
   *  rendered as a failure (same rule as `mt5_connected` on the sidebar's MT5 dot). Check it
   *  `=== false`, never falsy.
   *
   *  ⚠ It exists because `balance: null` is not a diagnosis. On 2026-08-04 a blank balance was
   *  the ONLY thing on this page that reflected a bot which had been blind for 50 minutes —
   *  MetaTrader auto-updated and restarted itself, and the running bot's link died with the old
   *  process. Every data call then returned an ABSENCE rather than an error, and an empty bar
   *  frame is what a quiet market looks like, so the loop kept beating and the row kept saying
   *  RUNNING. */
  mt5_link: boolean | null
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

// `BotConfigSections` / `BotConfigUpdate` deleted 2026-08-04 with the endpoints they typed —
// see the note in `hooks/useBots.ts`. `BotParamsView` below is what reads a bot's settings.

/** One line of a live bot's configuration. Mirrors `models.BotParamRow`. */
export interface BotParamRow {
  name: string
  value: unknown
  label: string
  group: string
  desc: string | null
  unit: string | null
  type: string
  options: Record<string, string> | null
  choices: unknown[] | null
  core: boolean
  /** Decided by the BACKEND. Never infer it from the param name here — the whole
   *  point is that one list governs what a running bot will actually pick up. */
  editable: boolean
  min: number | null
  max: number | null
  /** The `_`-prefixed prose from the instance config explaining why the value is what
   *  it is — written when the decision was made, which is when it was accurate. */
  note: string | null
}

export interface BotParamsView {
  bot_key: string
  display_name: string
  identity: {
    account: number | null
    server: string | null
    symbol: string | null
    timeframe: string | null
    mt5_path: string | null
    magic: number | null
  }
  version: {
    strategy_package: string | null
    strategy_class: string | null
    strategy_version: number | null
    strategy_source_hash: string | null
    promoted_commit: string | null
    promoted_at: string | null
  }
  runtime: BotParamRow[]
  strategy: BotParamRow[]
  notes: Record<string, string>
  readme: string | null
}

/**
 * What a bot is ACTUALLY running, read off the VPS.
 *
 * Distinct from `BotParamsView.version`, which reads the tracked `config.json` — that states
 * intent and goes stale the moment the repo moves. This comes from the deployment record
 * written beside the bot's frozen code snapshot, so it describes the disk the bot is on.
 * A version display that can be wrong is worse than none: it is what you check before
 * deciding anything.
 */
export interface BotDeployedVersion {
  frozen: boolean          // false = unpromoted, still importing from the repo tree
  hash: string
  commit: string           // the commit the snapshot was taken from
  promoted_at: string
  strategy_package: string
  strategy_class: string
  strategy_version: number
  files: number
  params: Record<string, unknown>   // the parameters AS DEPLOYED
  repo_commit: string      // what the VPS working tree is on now
  commits_ahead: number    // how far the repo has moved past the deployment
  snapshot_ok: boolean     // the snapshot still hashes to its record
  running_hash: string     // what the live PROCESS reports — may lag after a promote
  params_drift: string[]   // settings config.json now states differently
}

export interface BotPromoteResult {
  ok: boolean
  output: string
  restarted: boolean
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
  // show only when another param equals a value — or, with an array, equals ANY of them
  show_if?: Record<string, string | number | boolean | Array<string | number | boolean>>
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
  // True = the source on disk changed since the last Scan Strategies, so the param schema the
  // Run modal shows is stale. Computed live by the backend; the scan-time twin of needs_deploy.
  needs_scan?: boolean
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
  cost_layers?: CostLayer[]
  broker_profile?: string
  evaluate_rulesets: string[]
  source_run_id?: string | null
  sizing_mode?: SizingMode
  manual_risk_pct?: number | null   // required when sizing_mode === 'manual'
}

/** Which costs a python run charges. Empty = free, and that is the DEFAULT: the baseline run
 *  stays directly comparable to the TradingView Strategy Tester, and each cost is a deliberate
 *  choice. `spread` and `swap` are charged from the broker profile's own MEASUREMENTS; only
 *  `slippage` is a number anyone types, because it is the only one that cannot be measured.
 *  ⚠ `bid_ask_fills` is the odd one out — it REPLACES the spread cost rather than adding to it,
 *  and it is the only layer that can change which trades exist. */
export type CostLayer = 'spread' | 'swap' | 'commission' | 'slippage' | 'bid_ask_fills'

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
  /** The same worst drawdown as a % of the PEAK it fell from. Negative = measured, no answer. */
  max_drawdown_pct: number | null
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
  /** `null` = the run predates layered costs, which is NOT the same as `[]` ("charged nothing
   *  on purpose"). Keep the distinction when captioning it. */
  cost_layers: CostLayer[] | null
  broker_profile: string | null
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
  max_drawdown_pct: number | null          // worst drop as % of the peak it fell from
  scratch_count: number | null             // trades under 15% of the run's median full loss
  trade_concentration_pct: number | null   // top-5 winners' share of gross profit
  sortino: number | null
  cagr: number | null
  avg_win: number | null
  avg_loss: number | null
  avg_trade_duration_min: number | null
  worst_day_pnl: number | null
  worst_losing_streak: number | null
  equity_curve: EquityPoint[]
  daily_pnl: DailyPnlPoint[]
  /** EVERY trading day in the run's window with its regime label — not just the days that traded.
   *  Regime is a property of the market on a date, so both equity charts band from this. Empty on
   *  runs completed before it existed (charts fall back to daily_pnl's sparse tags). */
  regime_timeline: RegimeDay[]
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
  ssh_tunnel: boolean       // both LocalForwards are bound — the TUNNEL, not a fresh ssh connection
  vps_reachable: boolean    // the VPS answers SSH at all — tells a dead tunnel from a dead network
  nt8_agent: boolean   // NT8 agent (port 8765)
  mt5_agent: boolean   // MT5 agent (port 8766)
  // MT5 TERMINAL state. null = the agent could not be asked — NOT "disconnected".
  mt5_connected: boolean | null
  mt5_server: string | null
  mt5_account: number | null
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
  // BOTH sensitivity paths — the perturbation runner and the optimizer-grid injection — now score
  // `degradation`: a PROFIT-FACTOR change as a fraction (0..1). They used to disagree (perturbation
  // reported a net-P&L delta) while writing the same `sensitivity_max_degradation` and being judged
  // against the same grading thresholds, so one strategy could get two verdicts depending on which
  // path produced its score. P&L is also a dollar figure, which let any position-sizing parameter
  // swamp the score by arithmetic rather than by fragility.
  degradation?: number
  profit_factor?: number
  run_id?: string
  new_value?: number
  value?: number
  // Dollar effect of the shift, for reference only. `pnl_delta_pct` is written by NOTHING now and
  // survives on records from before 2026-07-30; the chart still reads it so those stay renderable.
  pnl_delta?: number
  pnl_delta_pct?: number
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
  // The same Monte Carlo drawdowns against the ACCOUNT, as a percent, and which basis the grade
  // read. 'percent' once the run compounds — a fixed dollar limit is not comparable to an account
  // that grew away from it. Null on fixed-size runs and on tests run before 2026-07-30.
  median_max_dd_pct: number | null
  pct5_max_dd_pct: number | null
  pct1_max_dd_pct: number | null
  dd_basis: 'percent' | 'dollars' | null
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

// ── Lab — Portfolio stacks ────────────────────────────────────────────────────
// A stack layers 2+ Python strategies over one shared instrument/window. The combined
// portfolio P&L is composed CLIENT-SIDE by summing each leg's daily_pnl; toggling a leg
// off is a re-sum without it (min one leg always on).

export interface StackRequest {
  strategy_ids: string[]
  instrument: string
  bar_type?: string
  bar_value?: number
  start_date: string
  end_date: string
  commission_per_side?: number
  slippage_ticks?: number
  ruleset_ids?: string[]
  params_by_strategy?: Record<string, Record<string, unknown>>
}

export interface StackResponse {
  stack_id: string
  run_ids: string[]
  status: string
}

export interface StackPreviewRequest {
  strategy_ids: string[]
  instrument: string
  bar_type?: string
  bar_value?: number
  start_date: string
  end_date: string
  commission_per_side?: number
  slippage_ticks?: number
}

export interface StackPreviewLeg {
  strategy_id: string
  strategy_name: string
  action: 'reuse' | 'run'
  matched_run_id: string | null
  net_pnl: number | null
  trade_count: number | null
  profit_factor: number | null
}

export interface StackPreviewResponse {
  legs: StackPreviewLeg[]
  reuse_count: number
  run_count: number
}

export interface StackSummary {
  stack_id: string
  instrument: string
  start_date: string
  end_date: string
  total_strategies: number
  completed_strategies: number
  failed_strategies: number
  status: string
  created_at: string
  strategy_names: string
}

export interface StackStrategyLeg {
  run_id: string
  strategy_id: string
  strategy_name: string
  status: string
  net_pnl: number | null
  max_drawdown: number | null
  trade_count: number | null
  sharpe: number | null
  avg_trade_duration_min: number | null
  error_message: string | null
  daily_pnl: Array<{ date: string; pnl: number }>
  equity_curve: EquityPoint[]
}

export interface StackDetail {
  stack_id: string
  instrument: string
  start_date: string
  end_date: string
  bar_type: string
  bar_value: number
  commission_per_side: number
  slippage_ticks: number
  total_strategies: number
  completed_strategies: number
  status: string
  created_at: string
  completed_at: string | null
  regime_timeline: RegimeDay[]
  strategies: StackStrategyLeg[]
}

// A layer in the merged stack price chart — one completed leg.
export interface StackChartLayer {
  strategy_id: string
  strategy_name: string
  run_id: string
}

// Merged ChartSpec for the stack candle chart: shared candles + every leg's trades (each `layer`-
// tagged with its strategy_id), plus the layer roster. Frontend filters trades to the toggled-on
// strategies and tints each by its equity-chart colour before handing the spec to ChartPanel.
export interface StackChartSpec extends ChartSpec {
  layers: StackChartLayer[]
  base_run_id: string | null   // the leg whose feed backs the shared candles — drives drill-down
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
  // Python runner only. Omitted (undefined) means "charge nothing stated" — NOT the same as
  // [], which is an explicit empty layer set. Mirrors BacktestRunRequest.
  cost_layers?: CostLayer[] | null
  broker_profile?: string | null
  // A combo below this many trades is still run and listed — it just cannot be the winner.
  min_trades?: number
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
  runner: string
  strategy_name: string | null
  winner_note: string | null
  grid_sensitivity_score: number | null
}

export interface GridSensitivityNeighbor {
  value: number
  profit_factor: number
  degradation: number
}

export interface OptimizationDetail extends OptimizationSummary {
  strategy_name: string
  param_grid: Record<string, ParamAxisSpec>
  runner: string
  runs: BacktestSummary[]
  live_pct: number | null
  live_message: string | null
  cost_layers: CostLayer[] | null
  broker_profile: string | null
  min_trades: number
  grid_sensitivity_summary: Record<string, Partial<Record<'up' | 'down', GridSensitivityNeighbor>>> | null
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

// ── News calendar (live tab) ──────────────────────────────────────────────────

export type Impact = 'HIGH' | 'MEDIUM' | 'LOW' | 'NONE'
export type Surprise = 'beat' | 'miss' | 'inline'

export interface CalendarEvent {
  timestamp_ms: number       // event time, UTC epoch ms
  currency: string           // ISO currency the event moves (USD/EUR/…)
  impact: Impact
  title: string
  category: string | null    // grouping label (Labor, Prices, …) for the categories dropdown
  forecast: string | null
  previous: string | null
  actual: string | null
  surprise: Surprise | null  // backend's beat/miss call once actual is out
}

export interface CalendarResponse {
  events: CalendarEvent[]
  server_now_ms: number      // drive the "now" line + countdown off server time, not the browser clock
  from_ms: number
  to_ms: number
}
