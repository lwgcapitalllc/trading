# Notes — Directory layout

What every router, service and script file is for. Moved VERBATIM out of `command-center/backend/CLAUDE.md` on 2026-09-13 so it loads only when
needed; nothing was reworded or dropped. **New detail on this topic goes HERE**, and the
CLAUDE.md gets at most one index line.

---

## Directory layout

```
backend/
├── main.py                app entry; registers all routers
├── config.py              loads config.json → typed module constants
├── config.json            machine-specific paths only — no business logic here
├── models.py              ALL Pydantic models — one file, never split
├── routers/               thin — validation + status codes only, no business logic
│   ├── smart_money.py
│   ├── bots.py
│   ├── backtests.py       lab — backtest runs; GET /history-limit serves the measured broker history floor (drives the UI date picker); GET /runs/{id}/chart-spec serves the price-chart ChartSpec (chart_spec.py); GET /runs/{id}/news serves the post-run news/holiday trade tags (news_filter.py); GET /runs/{id} takes `?timeline=false` to drop `regime_timeline` (96 KB of a 137 KB detail) for a caller that already has that calendar — default stays `true`, and `[]` is indistinguishable from a run that never had one
│   ├── strategies.py      lab — strategy registry + deploy endpoint + POST /scan (read-only) + POST /reconcile (destructive orphan cleanup) + GET /:id/instrument_summary + GET /:id/param-types
│   ├── rulesets.py        lab — ruleset CRUD (/rulesets); PATCH = guarded personal-rules edit (prop rows locked 403; PUT also 403 on prop)
│   ├── system.py          lab — health + log proxies
│   ├── strategy_files.py  lab — strategy file deployment (list, upload, delete, compile, sync-status)
│   ├── stress_tests.py    lab — stress test CRUD + trigger (GET /stress-tests, GET /running-lock, GET /strategy-grades, GET /:id, POST /run, **POST /:id/cancel**, DELETE /:id). The trigger returns `warnings` (a walk-forward whose windows cannot each hold 20 trades is arithmetic, knowable before ten backtests run); DELETE rmtrees the test's dir AND every child's
│   ├── sweeps.py          lab — instrument sweep (POST /backtests/sweep, GET /backtests/sweeps, GET/DELETE /backtests/sweeps/:id)
│   ├── optimizations.py   lab — optimizer (POST /optimizations/run, GET /optimizations/*, DELETE /optimizations/:id)
│   ├── calendar.py        live News Calendar tab — thin GET /calendar?from&to (ISO); returns the whole week unfiltered, 400 on bad ISO/window, 502 on feed error. GET /calendar/currencies serves the filter roster (static, no upstream call) so the page's chips cannot drift from the query
│   └── settings.py
├── services/              business logic, DB access, external clients
│   ├── lab_db.py          only module that touches lab.db
│   ├── strategy_import.py   the ONE way a Python strategy package is imported — purge the cached
│   │                      `strategies.python.*` modules, then import. This backend is long-running,
│   │                      so `import_module` otherwise pins whatever was on disk at boot; the
│   │                      scanner then writes a fresh source hash beside stale defaults and the row
│   │                      becomes UNCORRECTABLE by scanning. See *The scanner read the module and
│   │                      hashed the files* below
│   ├── strategy_scanner.py  reads from strategies/ (not algos/); scan is READ-ONLY (add/update + report orphans, never deletes). reconcile_strategies() is the explicit destructive counterpart (DB row + VPS file); remove_strategy() is the shared one-strategy delete.
│   │                      ⚠ Its tests state the expected roster ONCE, as `EXPECTED_CLASS_NAMES` in
│   │                      tests/test_strategies.py — added/skipped counts are `len()` of it, never a
│   │                      repeated literal. Adding a strategy used to fail three tests that each had
│   │                      to be traced back to the same cause; now it is a one-line edit
│   ├── evaluator.py       per-ruleset verdict; also exports compute_contract_cap_status()
│   ├── trailing_drawdown.py  compute_trailing_mll() — EOD trailing max-loss engine (the drawdown check)
│   ├── sizing_engine.py     dynamic sizing & risk engine — PURE (no DB/network). run_engine(mode="bullet"|"consistent") sizes each trade off the room left (bullet=max the rules allow; consistent=room÷7), reserves open-trade risk, applies halts, rounds-up-to-min-or-skip, detects breaches; emits size-correct daily_pnl (feeds evaluator) + the decision log. CORE BUILT, not yet wired to a runner — see "Dynamic sizing & risk engine" below
│   ├── decision_log.py      the ONE reusable audit log — TradeDecision/DecisionLog. One JSONL record per signal (taken or not): idea + setup score, every gate's verdict in order, the sizing decision, and the full life of a taken trade. Extensible (new gate = decision.gate(...)); identical in backtest and live
│   ├── metrics.py         shared metric helpers: daily_sharpe / apply_canonical_sharpe / profit_concentration_pct / scratch_count + trade_outcomes (the SAME scratch band, per run and per trade — see "The same bar now grades EACH trade") / compute_regime_breakdown (per-regime P&L table → BacktestDetail.regime_breakdown; rescales direction-point counts to trade_count — after the _normalize_mt5_results fix, MT5 equity curves have one point per trade so scale=1.0, but the rescale is kept for safety)
│   ├── backtest_runner.py background VPS polling task (single run)
│   ├── sweep_runner.py    runs N backtests sequentially (semaphore = 1) for a sweep
│   ├── optimization_runner.py  native NT8/MT5 optimizer (one VPS job, all CPU cores)
│   ├── worthiness.py      Tier 1/2/3 scoring
│   ├── objectives.py      optimizer objective functions
│   ├── stress_tester.py   Monte Carlo + walk-forward + sensitivity + auto-trigger
│   ├── grading.py         compute_grade() → A/B/C/D/F with plain-English reasons
│   ├── scripts/backfill_metrics.py  one-time, idempotent backfill of file-derivable metrics on old runs
│   ├── scripts/backfill_regime_timeline.py  opt-in backfill of `regime_timeline.json` on old runs (`--force`, `--run-id`); kept OUT of backfill_metrics.py because it fetches OHLC
│   ├── scripts/prop_kpi_audit.py    read-only dump of every prop ruleset's core KPIs from lab.db (the saved "is our engine in sync" query); feeds docs/PROP_RULESET_KPIS.md
│   ├── scripts/seed_stress_fixture.py  seeds ONE Monte-Carlo-only stress test so `frontend/tests/stress.spec.ts`
│   │                      has a real payload to mutate. **It exists because that suite's eleven checks
│   │                      silently switched themselves OFF on 2026-08-16 when `stress_tests` held zero
│   │                      rows** — they mock states the live box cannot produce and build every one by
│   │                      mutating a REAL detail response, so an empty table is a dead suite. MC only:
│   │                      no child backtests, no VPS, no platform lock. ⚠ It drives the real
│   │                      `run_stress_test_task` (a shortcut would be a hand-written fixture in a row's
│   │                      clothes) and refuses when the lab already holds one. (It stubbed the
│   │                      Telegram sender until 2026-09-10; a stress test sends nothing now)
│   ├── scripts/run_diff.py          read-only: why do two runs disagree? Prints the MEASUREMENT BASIS
│   │                      difference before the params and the results, and exits 1 when the two were
│   │                      not measured on the same footing — see *Comparing two runs* below
│   ├── ohlc_fetcher.py    fetch and cache daily OHLC per (instrument, date); NT8 first, yfinance fallback
│   ├── chart_spec.py      build the ChartSpec for the price-chart panel (candles + sessions + trades + blocked setups + recomputed strategy structure/ATR + market-structure overlays). Always ships the timeframe the run TRADED and caps the WINDOW instead (`_capped_start` → the newest slice under `_CANDLE_CAP`), with `historyStartMs` telling the panel how far back it may page; see "ChartSpec candles" below. `_build_blocks` reads the run dir's `blocked_setups.json` — see "Blocked setups" below; `_build_misses` reads `missed_setups.json` and ALSO returns the derived `missNoise` list — see "Missed setups" below
│   ├── fvg_overlays.py    replay the CANONICAL engines/fair_value_gaps/ engine (+ engines/equal_highs_lows/
│   │                      for mpc's eqExemptFvg cap coupling) over a run's candles → the "Fair Value Gaps"
│   │                      overlay group. Emits a box ONLY for a gap that was LIVE on a trade-entry / blocked /
│   │                      missed bar (all of them when several overlap); everything else is dropped. Settings
│   │                      are mpc_jarvis.pine's, READ from the engine by timeframe row (the floor and the
│   │                      close test split at 15m) — NOT a strategy's. See "Fair value gaps" below
│   ├── ob_overlays.py     the same shape for ORDER BLOCKS — replay the CANONICAL engines/order_blocks/
│   │                      engine over a run's candles → the "Order Blocks" overlay group, one box per
│   │                      block that was LIVE at a trade-entry / blocked / missed bar. Read
│   │                      fvg_overlays.py first; the differences are the BOX GEOMETRY (a fixed 30-bar
│   │                      stub from the anchor candle, not a box tracking the live bar) and that here
│   │                      there is NO settings fork to warn about. See "Order blocks" below
│   ├── structure_overlays.py  replay the CANONICAL engines/market_structure/ engine over a run's candles → BOS/SOS/swing overlays for the chart, in the 4 groups that ARE structure_engine.pine's 4 toggles (External / Internal / Historic Internal Structure / Swing Point Labels), nesting like the Pine's via each overlay's `requires` list (swing tags need their owning structure; historic internal needs Internal). Never a 2nd engine (bare-name import like regime/news); called by chart_spec on the displayed TF, at the engine's own swing length (read from it, not typed — since 2026-09-10). Break tags anchor at the line MIDPOINT (`_mid`, = Pine's `mid_x`) so they clear the break-bar candles; reversal breaks are labelled SOS/iSOS (not "CHoCH")
│   ├── news_filter.py     post-run news/holiday tagging — composes the canonical engines/news/ engine (never a 2nd impl) to mark which of a run's trades opened in a high-impact news window / on a bank holiday, for the BacktestDetail News filter card. Pure over a trade list; loads the EventStore cache (see "News filter (post-run)")
│   ├── history_limits.py  broker history floors — thin shim over the canonical `backtest/data/history.py`
│   │                      (declares NO dates itself). `limits_for()` → the MEASURED earliest backtestable
│   │                      date for an (instrument, timeframe, runner); `validate_window()` raises ValueError
│   │                      which routers turn into a 400. PYTHON RUNNER ONLY — NT8/MT5 read history from their
│   │                      own terminals, so a Vantage floor must never be imposed on them (see "History floors")
│   ├── calendar_service.py  live News Calendar tab — calls engines/news/ TradingViewSource.fetch_window() (never a 2nd impl), 60s in-memory cache keyed on (from,to,countries) and BOUNDED at 64 entries under one lock, computes beat/miss "surprise" server-side via _LOWER_IS_BETTER. Read-only: does NOT touch the shared EventStore cache. Returns the whole week; the frontend filters client-side. ⚠ Every upstream failure is normalised to RuntimeError in `_fetch` — a JSONDecodeError IS a ValueError and used to surface as a 400. See "The calendar's polarity list" below. Also owns `currencies_for()` — the chip roster the page draws, DERIVED from the queried country list via `_COUNTRY_CURRENCY` (bloc codes and ISO currencies are different namespaces, so only this side can map them)
│   ├── agent_supervisor.py  keeps the SSH tunnel + both VPS agents up — one 60s loop, identical on
│   │                      every pass, so a cold start and a wake-from-sleep are the same code path.
│   │                      Owns `restart_tunnel()` / `schtasks_run()` (moved out of routers/system.py,
│   │                      where main.py was reaching across to call one). Probes the TUNNEL by port
│   │                      binding and the AGENTS by HTTP, because `ssh -L` binds the local port
│   │                      itself — see "The agent supervisor" below
│   ├── readiness.py       boot-time report of the dependencies that fail SILENTLY (news calendar
│   │                      cache, Telegram credentials). Reports, never acts; `GET /system/readiness`
│   ├── runner_dispatch.py      typed HTTP wrapper over NT8 nt8_agent; runner dispatcher (routes mt5 → mt5_agent_client)
│   ├── mt5_agent_client.py  typed HTTP wrapper over MT5 agent (port 8766 via SSH tunnel). `health()`
│   │                      is the AGENT; `status()` is the TERMINAL (mt5_connected/account/server) —
│   │                      two different questions, and only the second says a run can fetch bars
│   ├── account_stack_basis.py what an account's bots RUN, as the stack builder's starting point — each bot's own settings, chart and risk, the account's cap, instrument and cost profile. See *"Backtest these bots"*
│   ├── stack_risk_budget.py do a SHARED stack's legs fit under its risk cap? The form's total and the launch's refusal both ask it; the decision is `bot_accounts.share_overflow`. See *A shared stack's legs may not add up past its cap*
│   ├── python_runner.py     local Python runner — runs strategies/python/ packages in-process via the top-level backtest/ package (backtests + A4 optimizer sweep). No VPS, no agent. Resolves strategies by `strategy_class` (the class `__name__` the scanner stored) — NEVER by package id
│   └── notify.py            Telegram notifier (urllib, no extra deps). Holds NO token: it reads env vars, else the git-ignored `algos/credentials.json`, by PATH (`cfg.MONOREPO_ROOT / "algos" / "credentials.json"`) — the same file `algos/shared/credentials.py` reads, without importing across the app boundary, which the subsystem-independence rule forbids. `routers/bots.py` delegates here; it must never grow its own sender again. `telegram_configured()` answers whether a send would go anywhere. **Every send states a `kind`** (`HEALTH` for everything this app produces) and the kind picks the chat — see the Telegram row in the feature table
├── data/lab.db            strategies, rulesets, runs, evaluations, optimizations, stress_tests
└── reports/lab/           run output files — equity curves, logs, progress.json
```
