# Backend Build Notes

**Status:** 📦 **ARCHIVE — relocated history, deliberately.** This is implementation detail moved OUT of `command-center/backend/CLAUDE.md` so that file could stay standing-rules-only. It is the pattern the rest of the repo still needs: **the rule lives in the CLAUDE.md, the war story lives here.** Nothing here is current status; it grows and is never pruned.

Implementation-level history and war-story detail relocated out of `command-center/backend/CLAUDE.md` to keep that file to standing rules and current status. Nothing here is deleted from the record — treat this as the detailed appendix.

---

## NT8 Strategy Analyzer UI automation (nt8_backtest_runner.py)

Hard-won rules for pywinauto + NT8 WPF — violating these causes silent wrong-strategy runs or broken SA state:

**PCT:100 hung fix**: In `nt8_agent.py`, the `for line in proc.stdout:` loop never sees EOF on Windows when the subprocess calls `os._exit(0)`. This is because `subprocess.Popen` with `stdout=PIPE` sets `close_fds=False` on Windows — the agent process inherits the write-end of the pipe, keeping it open after the child exits. Fix: mark the job `status="complete"` *inside* the stdout loop the moment `PCT:100` arrives AND the results file exists — never wait for loop exit. Same pattern applies to walk-forward jobs.

**SA auto-open**: `find_strategy_analyzer` opens SA automatically via NT8's New → Strategy Analyzer menu if not already visible. This handles the case where NT8 crashes and restarts without restoring the SA window. Retries once after opening.

**Narrow scan `txtBox` probe**: `_build_opt_grid_map` uses a narrow scan to avoid the ~22s full `sa.descendants()` call. The probe must use `found_index=0` — `sa.child_window(auto_id="txtBox", control_type="Edit", found_index=0)` — because multiple elements match and `child_window()` without `found_index` throws "N elements match." Each `node.parent()` call in the walk must be in its own `try/except` so a COM error on one level doesn't abort the entire walk.

**Strategy compile delays**: After NT8 restart, strategies are compiled lazily. `select_strategy` retries with increasing waits (1.5s → 5s → 10s) to allow NT8 time to compile before giving up.

**ComboBox identification**
- All NT8 WPF ComboBoxes return empty `window_text()` — you cannot identify them by their current value.
- Named ComboBoxes (`auto_id != ''`) are all strategy/config controls (BacktestType, TradingHours, EntryHandling, etc.). **Never click them during trade export** — it corrupts SA configuration for the next run.
- The Display combo (Summary/Analysis/Chart/Trades/…) always has an empty `auto_id`. Only scan unnamed ComboBoxes.
- To identify the Display combo: click it, then look for a "Trades" item in the SA subtree or Desktop. Try `control_type="MenuItem"` first, then `"ListItem"`, then a broad `descendants()` scan by `window_text()`.
- To close a dropdown without selecting: click the same combo again (toggle). **Do not use `send_keys("{ESCAPE}")`** — it sends ESCAPE to the active window and can dismiss unrelated dialogs.

**Strategy selection**
- `select_strategy()` returns `True/False`. If it returns `False`, the SA still has the previous strategy loaded.
- `configure_from_spec()` raises `RuntimeError` on strategy-selection failure; `run_job_mode()` catches it and calls `sys.exit(1)`. **Never let a run proceed if strategy selection failed** — NT8 will silently run whatever was last loaded.
- Strategy dropdown items are `control_type="MenuItem"`, not `ListItem`.
- **WPF popup location changes after first run**: On a fresh SA the dropdown popup is a child of the SA window in the UIA tree. After a backtest completes, subsequent clicks on the selector render the popup as a top-level Desktop element. `select_strategy` uses `_find_strategy_item` which tries both: `sa.child_window(...)` first, then `Desktop(backend="uia").window(...)`. Never search only within SA.

**Optimization results export**
- Right-click CSV export from the SA results grid is the **only** way to get optimization results. Native optimize writes `.cs` files per combo — no `.xml`. Never look for an output file; always export via the context menu.
- `_export_optimization_results` uses a two-pass right-click: Pass 1 opens the context menu and scans the UIA tree to find Export coordinates (the scan causes WPF to close the popup), Pass 2 right-clicks again and immediately clicks Export at the recorded coordinates.
- Sleep **1.0 s** (not 0.3 s) after `sa.restore()` before right-clicking — the SA needs time to finish restoring before WM_RBUTTONDOWN lands on the right element.
- Right-click at `y = sa_rect.top + int(sa_h * 0.20)` — 20% skips the Display dropdown and column headers. y=5% lands in the header row (no Export option). y=50%+ lands in the performance summary tab (wrong export format). The print log shows `[opt-export] Right-click at (x, y)  sa=WxH` for debugging.
- **0-trade combos kill Export**: when all optimization combos produce 0 trades, NT8 shows no results in the grid and the Export context menu item does not appear. Root cause: NinjaScript `int` parameters (e.g. `MaPeriod`) silently truncate decimal values — a step of 2.5 generates values like 22.5 → cast to 22, but NT8 skips the combo because the effective value doesn't match. The `param-types` endpoint + frontend validation (see frontend CLAUDE.md) prevents users from entering non-integer steps on `int` params.
- When the same 3 persistent items (`Momentum`, `Select`, `Trades ($)`) appear in the UIA scan, the right-click is NOT opening a context menu — it landed on a different element. These are persistent WPF dropdown elements, not context menu items.

**Param setting in Optimize mode — confirmed behavior**
- NT8 does NOT automatically reset BacktestType after `select_strategy`. It stays in whatever mode was active. Always call `_set_backtest_type("Backtest")` explicitly after `select_strategy` + 3s sleep to get a clean state.
- String and bool params: set via PDEX `set_edit_typed`/`set_checkbox` in Backtest mode. These persist through Backtest→Optimize switch (no Optimize-grid entry for them).
- Numeric params: DO NOT persist through Backtest→Optimize switch. NT8 resets all Optimize-grid params to their NinjaScript defaults on the mode switch. Must be set via the Optimize grid (`_set_range_in_grid` with lo=hi=value, step=1) AFTER switching to Optimize mode.
- One-time re-render: the first write to ANY txtBox in the Optimize grid triggers NT8's WPF property-change event, rebuilding the entire grid (stale elements). Set RANGE params first — they absorb the re-render. Then rebuild `grid_map` (0.5s sleep) and set fixed numeric params. They will stick because the re-render has already fired.
- Confirmed flow in `run_native_optimize_mode`: select_strategy → 3s → `_set_backtest_type("Backtest")` → 1.5s → set str/bool via PDEX → `_set_backtest_type("Optimize")` → set instrument/dates → build grid_map → set range params → 0.5s → rebuild grid_map → set fixed numeric params (lo=hi=value, step=1).
- `set_edit_text` does not trigger NT8's WPF LostFocus commit handler. Always use `set_edit_typed` (click_input + type_keys with `~`) for strategy PDEX fields.

**Timing**
- After `select_strategy`, sleep 2–3 s — NT8 fully rebuilds the property grid and the UIA tree is temporarily invalid.
- After clicking a WPF ComboBox to open it, sleep ≥ 0.7 s before searching for items — the popup renders asynchronously.

---

## Dynamic sizing & risk engine + decision log — build history

The mechanism behind the LWG gated-layer model (`docs/LWG_Strategy_Framework.md`, `docs/dynamic_sizing_engine.md`): the strategy proposes setups at unit size; gates decide *whether* a trade is allowed; the engine decides *how big* from the room left now. No strategy manages risk.

Core pieces:

- **`services/sizing_engine.py`** — PURE (no DB/network/clock). `run_engine(trades, ruleset, *, is_micro, mode)` where mode is the per-run **bullet/consistent** switch: bullet = the most the rules allow (with a one-loss-can't-breach guard); consistent = **room ÷ 7** per trade. Room is measured to the **trailing floor** (highest-EOD-based, capped at the firm lock — NOT balance−start, so growth doesn't fake a buffer). It reserves **open-trade risk** (a running trade holds its risk; the next signal shrinks or is blocked), rounds a sub-minimum size **up to 1 only if 1 still fits the room** else skips, applies the daily-loss / profit-target halts, and detects breaches. Output: `daily_pnl` (size-correct — feeds `evaluator.evaluate_run` unchanged, so no second grader), a day-by-day `timeline`, `sized_trades`, and `decisions`. Sizing is goal-driven, NOT % of balance and NOT `daily-loss ÷ trade-count` (both dead).
- **`services/decision_log.py`** — `TradeDecision` / `DecisionLog`, the one reusable audit log. One JSONL record per signal (taken or not): idea + setup score, every gate's verdict in order (which one shut it down, or that all passed), the sizing decision (size + what bound it, or why skipped), and the full life of a taken trade (entry, exit, exit reason, P&L). Gates are an ordered list — a new gate just calls `decision.gate(name, passed, reason)`, no schema change. Pure stdlib, identical in backtest and live.
- **Tests:** `tests/test_sizing_engine.py` (20), `tests/test_decision_log.py` (7) — all green.
- **`services/sizing_pipeline.py`** — the FS/IO wiring: `run_sizing_engine(run_id, trade_records, ruleset, *, mode, instrument, strategy, results_dir)` builds `RawTrade`s from a runner's export, runs the engine, and persists `decisions.jsonl` + `engine_timeline.json` + `engine_daily_pnl.json` to the run dir. `size_run_for_rulesets(...)` sizes once per ruleset and additionally writes every firm's `{kpis, daily_pnl, timeline}` to `ruleset_sizing.json` (see "Per-firm sized results" below). Locks the runner→engine column contract. `tests/test_sizing_pipeline.py` (7) green.

**2026-06-21 — `ORB.cs` reshaped to the rules.** It now trades **unit size (1 contract)**, its self-policing halts are **removed** (daily-loss halt, profit-target stop, profit lock-in, consecutive-loss halt all moved to the engine), and it keeps only signal + stop/target + time rules (force-flat, entry hours, allowed days). It emits the per-trade record — the runner→engine contract columns — to `engine_trades.csv` (`strategy_results.csv` is still written but is now a unit-size reference only). `build_foundational_params` was trimmed to match: it injects only `CommissionPerSide`, `ForceFlatTimeET`, `EarliestEntryTimeET`, `LatestEntryTimeET`, `DaysOfWeekAllowed` (the removed NinjaScriptProperties no longer exist). Needed VPS compile + backtest to verify — could not be tested locally. ORB is the only NT8 strategy carried forward (VWAP_MR, Momentum deleted 2026-06-21).

**2026-06-21 — wired (code-complete, needed a VPS run to verify):** the NT8 runner (`nt8_backtest_runner.run_job_mode`) clears `engine_trades.csv` before the run and reads it back after, shipping the rows as `result["engine_trades"]`. `backtest_runner._handle_complete` then, **only when `engine_trades` is present**, sizes the run PER RULESET via `sizing_pipeline.size_run_for_rulesets` (each firm's ladder/floor differ), uses the first ruleset as the headline, grades each ruleset against its OWN sized P&L, and persists the primary's audit log + timeline. Native (unit-size) runs carry no `engine_trades` → unchanged. The per-run **bullet/consistent** switch is plumbed: `BacktestRunRequest.sizing_mode` → `backtest_runs.sizing_mode` column (`DEFAULT 'consistent'`) → read back in `_handle_complete`. The `BacktestDetail` model exposes `sizing_mode` (off the run row), `sized` (a bool), and `sized_timeline` (`list[SizedTimelineDay]` — the engine's day-by-day record). `_row_to_detail` loads `reports/lab/<run_id>/engine_timeline.json` ONCE: its content becomes `sized_timeline` and `sized = bool(sized_timeline)` (the persisted marker of a real sized run) — no second `.exists()` stat. `SizedTimelineDay` mirrors `sizing_engine.DayTimeline` (date, trades_taken, contracts_total, day_pnl, eod_balance, risk_floor, floor_distance, consistency_share_pct, halt_reason); it drives the frontend's Sized equity curve AND the day-by-day Sizing Timeline table (both built).

**2026-06-30 — per-firm sized results.** The strategy makes the SAME trades for every firm — only the contract count differs (each firm's ladder/floor), so every firm has its own dollar P&L, sized daily P&L, and sized timeline. `size_run_for_rulesets` now writes **all** of them to `reports/lab/<run_id>/ruleset_sizing.json` (`_persist_ruleset_sizing`) — one map keyed by ruleset id, each `{kpis, daily_pnl, timeline}` — not just the primary. `EvaluationDetail` carries the per-firm KPI fields (`net_pnl`, `max_drawdown`, `profit_factor`, `win_rate`, `trade_count`, `avg_win`, `avg_loss`) + `daily_pnl` + `sized_timeline` + **`equity_curve`** (`engine_result_to_equity_curve` — the sized trade-by-trade curve, EquityPoint shape, excluding skipped/blocked signals); `_row_to_detail` loads `ruleset_sizing.json` and attaches each firm's slice to its evaluation (null/empty on unit-size + pre-2026-06-30 runs, which have no file → the UI falls back to the run-level headline). This is what lets BacktestDetail switch **everything ruleset-dependent** per firm when clicking through evaluations: KPI cards (incl. the equity-derived Calmar / Max DD % / Z-Score, off `equity_curve`), Sized-account chart, Daily P&L bars, Sizing Timeline table, **Drawdown chart** and **Long-vs-Short breakdown**. Only the "Strategy (1 unit)" equity tab + Price chart stay firm-independent by design (the bare 1-unit strategy). Firms skip different trades on halt/breach days, so `equity_curve` length (trade count) and its long/short split genuinely differ per firm. The primary's `engine_timeline.json`/`engine_daily_pnl.json` stay the run headline (unchanged); `ruleset_sizing.json` is the per-firm superset.

**2026-06-22 — MT5 reshaped too.** `LondonBreakout.mq5` is now reshaped like ORB: it trades UNIT size = the broker minimum lot (the forex analog of "1 micro" — always tradeable, finest legal granularity), strips all account governance, and writes the per-trade record to `engine_trades.csv` with `FILE_CSV` (no `FILE_COMMON`). **Gotcha (fixed 2026-06-24):** under a single backtest the EA runs in a local tester *agent*, so the file lands in the agent sandbox `%APPDATA%\MetaQuotes\Tester\<hash>\Agent-*\MQL5\Files`, NOT the terminal data dir's `MQL5\Files` (that path only ever gets `opt_results.csv`, which `OnTesterPass` writes from the collecting terminal, not the agent). The MT5 agent (`algos/.../mt5_agent.py`) reads that file back after a single backtest (`_read_engine_trades` → `_engine_trades_candidates`, which globs every `Tester\*\Agent-*\MQL5\Files\engine_trades.csv` and takes the freshest by mtime; all candidates cleared pre-run so a failed run ships nothing) and attaches it as `result["engine_trades"]`; `runner_dispatch._normalize_mt5_results` passes the key through at the top level, so `_handle_complete` sizes the run runner-agnostically — the SAME gate as NT8 (`if engine_trades and firm_ids`). MT5 forex runs size against the personal/demo forex ruleset (no prop firm covers forex); the engine reads `max_drawdown_from_peak_pct × account_size` as the floor, so personal rulesets size fine (`EngineRuleset.from_ruleset` is `.get()`-safe). The forex `point_value` recorded is value of one price point for one min-lot (`tickValue/tickSize × unitLots`), so `risk_per_contract` is real USD. Both ORB and LondonBreakout needed a VPS compile + backtest to verify — neither could run locally. The whole sized path stays dormant until a reshaped strategy actually emits `engine_trades.csv` on the VPS; both the curve and the table render only once a real sized run exists.

---

## What's built (status) — drained from `command-center/backend/CLAUDE.md` (2026-08-13)

Same shape as the frontend's: 13 KB of status column, 57% of it dated, where each
domain's row had absorbed its own build history.

**Every entry is reproduced here verbatim, nothing summarised away.** The index
in the CLAUDE.md keeps each entry's identity and lead sentence and links here for
the rest. ⚠ Where an entry explains something another file owns, the file next to
that code is the one that is right.

### Bots

**Status:** ✅ Live

SSH monitor + control. **One bot registered — `mpc_sos_fade_demo`** (this row said "none currently registered" until 2026-08-04; it has run since 2026-07-31). Global + per-bot controls, cap deploy, Telegram users. `GET /{bot}/version` reads the VPS deployment record (`deployed.json`) + git HEAD + the LIVE process's own `source_hash`, so the page reports what is RUNNING rather than what `config.json` intends; `POST /{bot}/promote[/preview]` stages, verifies and deploys. ⚠ **`BotStatus.mt5_link` is `Optional[bool]` and `None` means UNASKED** — a stopped bot, or one predating the field — so it is read `=== false` on the frontend, never falsy. Same rule as `mt5_connected` on the health strip, and for the same reason: rendering an unanswered question as a failure invents a measurement. It exists because `balance: None` is not a diagnosis — see the 2026-08-04 entry in `algos/CLAUDE.md`. ⚠ **Every kill goes through `_kill_bot`, which matches on BOTH `name='python.exe'` and `--bot <key>`** — never `taskkill /f /im python.exe` (that blanket kill takes out both backtest agents and the Telegram bot with it, and is what killed the live bot for three days in July), and never a bare commandline match either: without the process-name clause it matches the `cmd.exe`/`wmic.exe` running the command itself, and without the `--bot ` prefix it matches `promote.py` and `startup_coordinator.py`. Four per-bot routes built their own unscoped version until 2026-08-04; `tests/test_bot_kill_scope.py` now fails the build if a fifth appears.

### Strategies

**Status:** ✅ Live

Registry scanned from `strategies/`. Param schema from `[NinjaScriptProperty]`. `runner` field per strategy. `run_count` (shown in the Strategies-tab Runs column) joins `backtest_runs` with `r.stress_test_id IS NULL` — same "real run" filter as `list_runs`, so hidden stress-test child runs don't inflate the count. **Strategy-level narrative** (`edge` TEXT, `steps` JSON) is overlaid from the companion `<Strategy>.meta.json` **top-level** `edge`/`steps` keys by `strategy_scanner._read_strategy_overview` and stored on `strategies`; drives the StrategyDetail Overview. UI-only (no source-hash impact). NULL-safe: a backfill migration sets `steps='[]'` and `Strategy.steps` has a `mode="before"` validator coercing `None→[]` (a NULL would otherwise fail the `list[dict]` response validation on `GET /strategies`). `.mq5` re-scans on meta mtime change; `.cs` only on source change. **`needs_scan`** (2026-07-23) — the scan-time twin of `needs_deploy`/`needs_compile`: `strategy_scanner.needs_rescan(row)` recomputes the on-disk source hash (Python = whole-package `_python_source_hash`; `.cs`/`.mq5` = file md5) + meta mtime and returns True when either diverged from what the DB last scanned, i.e. the param schema the Run modal shows is stale. Computed LIVE and enriched onto every row in `routers/strategies.list_strategies`/`get_strategy` (NOT stored — a circular import if `lab_db` computed it, and it must reflect disk right now). This is what surfaces the "Needs scan" pill so a Python strategy (which has no deploy/compile step) still tells the user to re-scan after a `config.py`/meta edit — the gap that let a run fire on the old divergence-armed defaults.

### Rulesets

**Status:** ✅ Live

CRUD at `/rulesets`. 4 types: `prop_eval`, `prop_funded`, `personal`, `demo`. 18 seeded rows (14 prop + 2 personal demo + `unconstrained` + `personal_forex_risk`). Prop rows locked server-side (PATCH/PUT 403); `PATCH` edits the 5 personal rule fields only (`PersonalRulesetPatch` extra=forbid + SQL allowlist).

### Stress Tests

**Status:** ✅ Live

MC (10k reshuffles + 1k bootstrap), walk-forward (IS/OOS windows), sensitivity (±10%/±25%). A–F grade. **Audited 2026-08-05** — child runs now carry the baseline's `cost_layers`/`broker_profile`/`sizing_mode`, a phase that ran and CRASHED is distinguishable from one never requested, `prob_pass_eval` is measured on the basis the grade reads, cancel actually cancels, delete removes the files, and unreachable params are not perturbed. See *Stress tests — the 2026-08-05 audit*

### Regime Tags

**Status:** ✅ Live

`backtest_runner.build_regime_timeline_and_tag()` classifies **every trading day in the run's window** once (via the existing `build_date_regime_map`), writes it to `reports/lab/<run_id>/regime_timeline.json` → `BacktestDetail.regime_timeline` `[{date, regime}]`, and tags `daily_pnl` from that same map (a P&L day with no bar carries the last classified day). Regime is a property of the MARKET on a date, not of a run — tagging only traded days left the equity charts banding off a sparse calendar, so two runs over the same window disagreed about the regime. Cheaper too: one classification per day, reused. Old runs: `scripts/backfill_regime_timeline.py` (opt-in — it fetches OHLC, so it's not in `backfill_metrics.py`). Optimizer `regime_filter` unchanged.

### MT5 runner

**Status:** ✅ Live

`mt5_agent.py` port 8766: Strategy Tester driver (ini+set, terminal64, HTML report). `mt5_agent_client.py` typed wrapper. Runner dispatch via `runner_dispatch`. `/historical_data` maps M5/M15/M30 (was M1/H1/H4/D1 only), `symbol_select()`s before reading bars, **preserves symbol case** and tries the symbol **as given then its root** (terminals vary — GBPJPY is only `GBPJPY.s`, USDJPY both ways). `ohlc_fetcher._resolve_mt5_symbol` passes the run's broker symbol through; `chart_spec._capped_start` caps candle volume by trimming the WINDOW, never the timeframe.

### MT5 native optimizer

**Status:** ✅ Live

`mt5_agent.py` `POST /native-optimize` + `POST /native-walkforward`; `mt5_agent_client.py` typed wrappers. `runner_dispatch` dispatcher + `optimization_runner.run_native_optimization` route by `runner`. Native single-job `Optimization=1` run — MQL5 frame callbacks (`OnTesterInit/OnTester/OnTesterPass/OnTesterDeinit`) collect per-combo KPIs into `opt_results.csv`; the tester distributes combos across its local agents. **The EA MUST implement those callbacks** — without them the optimizer runs every pass but harvests nothing (single backtests work, optimization yields an empty CSV → "OnTesterPass may not have fired"). CSV columns must match `_parse_opt_csv` / `_OPT_KPI_COLS` (net_pnl/profit_factor/max_drawdown/trade_count/win_trades/sharpe[/gross_profit/gross_loss]) and the param column names must equal the grid keys. Combos rank on MT5's platform Sharpe (the native path has no `daily_pnl`, so canonical Sharpe isn't computed) — re-validate a winner with a single full backtest.

### Python runner + optimizer

**Status:** ✅ Live

`services/python_runner.py` — runs `strategies/python/` packages LOCALLY, in-process, via the top-level `backtest/` package (data cache → engine replay → `output.build_results`). No VPS, no agent, no compile. Scanner registers packages declaring `LAB_STRATEGY` (`strategy_scanner._parse_python_package`); the runner resolves by `strategy_class` = the strategy class's `__name__` — the same job-spec key NT8/MT5 use, locked by `test_python_runner.py`'s scanner↔runner agreement test. Optimizer: `runner_dispatch.start_native_optimization(spec, "python")` → `backtest/optimizer.run_sweep` fans combos across cores (lab still owns grid expansion + ranking — `expand_grid`, `objectives.py`). Sweeps run in bar mode; validate the winner in tick mode. Third lock scope: `has_running_python_job()`, surfaced through `get_running_job()`'s `python` bucket and consumed by the frontend's `lib/runner.ts` (wired 2026-07-16). Price charts AND regime tagging both read `ohlc_fetcher.get_ohlc(runner="python")` → `backtest.data.BarSource`, the SAME disk cache the run replayed, and deliberately never fall back to another feed: yfinance maps XAUUSD.s → GC=F, so a fallback would chart/label a spot-gold run off Yahoo's gold FUTURES daily bars. **Feature parity with the native runners is otherwise inherited, not re-implemented** — `run_backtest_job`/`_handle_complete` are runner-agnostic, so sizing (via `engine_trades`, which `backtest/output.py` emits), evaluations, worthiness, canonical Sharpe, regime tagging, the news/holiday filter (needs `entry_ms`, which the Python output carries) and stress tests all work unchanged.

### Portfolio stacks

**Status:** ✅ Live

`routers/stacks.py` + `services/lab_db.py` — layer 2+ **Python** strategies over ONE shared instrument/timeframe/window/cost profile to see combined P&L (summed client-side from each leg's `daily_pnl`; toggling a leg off never re-runs). **Smart reuse** (2026-07-25): on create, each leg that already has a COMPLETED standalone run at the EXACT same settings is reused as-is; only legs with no match are backtested fresh. `POST /backtests/stacks/preview` reports reuse-vs-run per leg without running anything (drives the modal's badges). See "Portfolio stacks (smart reuse)" below.

### Telegram notifications

**Status:** ✅ Live

`services/notify.py` — urllib Telegram sender, no extra deps. **No token in the source (2026-07-30):** env var, else the git-ignored `algos/credentials.json` read by path. `stress_tester` fires after grade is written. **`send_telegram(text, kind)` — the `kind` is REQUIRED and picks the chat (2026-08-05).** Every message this app sends is `HEALTH` (bot started/stopped/restarted/promoted, runtime params applied, stress test finished); none is a fill, because only the bot on the VPS can know a trade happened — and `tests/test_notification_routing.py` **refuses a `TRADE` here by test**, as well as greping every sender for a stated kind. ⚠ **This is a SECOND implementation of `algos/shared/notify.py`'s routing table**, which the subsystem boundary requires (shared FILE, never a shared import); the two are pinned together by routing on the same credential keys, checked by a test that reads that file. **`services/alert_format.py` (2026-08-05) is the same arrangement for the message SHAPE** — `<icon> <LABEL> · <subject>` then grouped facts then what to act on, plain text, and **no timestamp** because Telegram already prints the send time in each reader's own local clock. `algos/tests/test_alert_format.py` loads this app's copy BY PATH and asserts both files render byte-identical output, including the cases where two hand-written copies diverge first (an absent fact, a whitespace-only one).

### Live calendar tab

**Status:** ✅ Live

`routers/calendar.py` (`GET /calendar?from&to`) → `services/calendar_service.py` → `engines/news/` `TradingViewSource.fetch_window()` (never a 2nd impl). Returns the whole week's events unfiltered + `server_now_ms` (drives the frontend "now" line off the server clock); 60s in-memory cache; beat/miss `surprise` computed server-side (`_LOWER_IS_BETTER`). Read-only — does NOT write the shared EventStore cache (separate path from the post-run news filter). Feed only, no DB.

### History floors

**Status:** ✅ Live

`services/history_limits.py` + `GET /backtests/history-limit`. Refuses (400) any backtest window starting before the broker's REAL history for that timeframe — MT5 silently substitutes coarser bars, which would produce a plausible but fictional run. Floor is MEASURED off the live terminal (probed by bar density, cached per broker) via the canonical `backtest/data/history.py`, so a broker swap re-measures instead of inheriting. Enforced at run / retry / sweep / optimization / stack, and again in `BarSource.load`. Python runner only.

