"""
Lab SQLite helper — strategies, rulesets, backtest_runs, evaluations.
Single entry point for all lab DB access. No other module touches lab.db.
"""

from __future__ import annotations

import json
import sqlite3
import time
from datetime import date, timedelta
from pathlib import Path
from typing import Any, Optional

_HERE = Path(__file__).parent.parent
DB_PATH = _HERE / "data" / "lab.db"


def _connect() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    return conn


def _parse_json_fields(row: dict, fields: list[str]) -> dict:
    for f in fields:
        if f in row and isinstance(row[f], str):
            try:
                row[f] = json.loads(row[f])
            except (json.JSONDecodeError, TypeError):
                pass
    return row


def init_db() -> None:
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    with _connect() as conn:
        # Rename firms→rulesets for existing DBs (idempotent — fails silently if done or N/A)
        try:
            conn.execute("ALTER TABLE firms RENAME TO rulesets")
        except Exception:
            pass

        conn.executescript("""
            CREATE TABLE IF NOT EXISTS strategies (
                id                   TEXT PRIMARY KEY,
                name                 TEXT NOT NULL,
                class_name           TEXT NOT NULL,
                source_path          TEXT NOT NULL,
                category             TEXT,
                suggested_instrument TEXT,
                default_params       TEXT,
                param_schema         TEXT,
                scanned_at           INTEGER NOT NULL,
                source_hash          TEXT
            );

            CREATE TABLE IF NOT EXISTS rulesets (
                id                          TEXT PRIMARY KEY,
                name                        TEXT NOT NULL,
                account_size                INTEGER NOT NULL,
                profit_target               INTEGER NOT NULL,
                max_loss_eod                INTEGER NOT NULL,
                max_loss_intraday           INTEGER,
                drawdown_type               TEXT NOT NULL,
                consistency_pct             REAL,
                min_trading_days            INTEGER,
                force_flat_time_et          TEXT,
                allowed_instruments         TEXT,
                max_contracts               TEXT,
                platform_support            TEXT,
                account_tier                TEXT NOT NULL DEFAULT 'eval',
                docs_url                    TEXT,
                notes                       TEXT,
                created_at                  INTEGER NOT NULL,
                updated_at                  INTEGER NOT NULL,
                eval_cost_usd               INTEGER,
                activation_fee_usd          INTEGER,
                profit_split_pct            REAL,
                ruleset_type                TEXT NOT NULL DEFAULT 'prop_eval',
                daily_loss_cap              INTEGER,
                weekly_loss_cap             INTEGER,
                daily_profit_goal           INTEGER,
                description                 TEXT,
                risk_per_trade_pct          REAL,
                max_consecutive_losses      INTEGER,
                earliest_entry_time_et      TEXT,
                latest_entry_time_et        TEXT,
                days_of_week_allowed        TEXT,
                daily_profit_target         INTEGER,
                daily_profit_lock_pct       REAL,
                default_commission_per_side REAL,
                default_slippage_ticks      INTEGER,
                daily_halt_fraction         REAL,
                mll_lock_balance            REAL,
                consistency_breach_action   TEXT,
                reference_urls              TEXT,
                max_drawdown_from_peak_pct  REAL,
                max_consecutive_loss_days   INTEGER
            );

            CREATE TABLE IF NOT EXISTS backtest_runs (
                run_id              TEXT PRIMARY KEY,
                strategy_id         TEXT NOT NULL REFERENCES strategies(id),
                instrument          TEXT NOT NULL,
                params              TEXT NOT NULL,
                bar_type            TEXT NOT NULL,
                bar_value           INTEGER NOT NULL,
                start_date          TEXT NOT NULL,
                end_date            TEXT NOT NULL,
                commission_per_side REAL NOT NULL,
                slippage_ticks      INTEGER NOT NULL,
                status              TEXT NOT NULL,
                created_at          INTEGER NOT NULL,
                started_at          INTEGER,
                completed_at        INTEGER,
                error_message       TEXT,
                net_pnl             REAL,
                max_drawdown        REAL,
                profit_factor       REAL,
                win_rate            REAL,
                win_count           INTEGER,
                trade_count         INTEGER,
                sharpe              REAL,
                sortino             REAL,
                cagr                REAL,
                platform_sharpe     REAL,
                sharpe_low_sample   INTEGER,
                profit_concentration_pct REAL,
                avg_win             REAL,
                avg_loss            REAL,
                avg_trade_duration_min REAL,
                worst_day_pnl       REAL,
                worst_losing_streak INTEGER,
                equity_curve_path   TEXT,
                trades_path         TEXT,
                daily_pnl_path      TEXT
            );

            CREATE INDEX IF NOT EXISTS idx_runs_strategy
                ON backtest_runs(strategy_id, created_at DESC);
            CREATE INDEX IF NOT EXISTS idx_runs_status
                ON backtest_runs(status);

            CREATE TABLE IF NOT EXISTS evaluations (
                eval_id               TEXT PRIMARY KEY,
                run_id                TEXT NOT NULL REFERENCES backtest_runs(run_id),
                ruleset_id            TEXT NOT NULL REFERENCES rulesets(id),
                verdict               TEXT NOT NULL,
                drawdown_pass         INTEGER NOT NULL,
                target_pass           INTEGER NOT NULL,
                consistency_pass      INTEGER,
                simulated_eval_days   INTEGER,
                breach_count          INTEGER NOT NULL,
                largest_day_share_pct REAL,
                adjusted_profit_target   REAL,
                contract_cap_status      TEXT,
                mll_final_floor          REAL,
                mll_highest_eod_balance  REAL,
                mll_breach_day           INTEGER,
                mll_min_floor_distance   REAL,
                notes                 TEXT,
                created_at            INTEGER NOT NULL,
                UNIQUE(run_id, ruleset_id)
            );

        """)

        # Idempotent migrations — each wrapped in try/except
        for migration_sql in [
            # Strategy migrations
            "ALTER TABLE strategies RENAME COLUMN default_instrument TO suggested_instrument",
            "ALTER TABLE strategies ADD COLUMN runner TEXT NOT NULL DEFAULT 'ninjatrader'",
            # backtest_runs additions
            "ALTER TABLE backtest_runs ADD COLUMN worthiness_tier TEXT",
            "ALTER TABLE backtest_runs ADD COLUMN worthiness_reason TEXT",
            "ALTER TABLE backtest_runs ADD COLUMN worthiness_computed_against_firm TEXT",
            "ALTER TABLE backtest_runs ADD COLUMN sweep_id TEXT",
            "ALTER TABLE backtest_runs ADD COLUMN optimization_id TEXT",
            "ALTER TABLE backtest_runs ADD COLUMN evaluate_firms TEXT",
            "CREATE INDEX IF NOT EXISTS idx_runs_sweep ON backtest_runs(sweep_id)",
            "CREATE INDEX IF NOT EXISTS idx_runs_optimization ON backtest_runs(optimization_id)",
            "ALTER TABLE backtest_runs ADD COLUMN source_run_id TEXT",
            "CREATE INDEX IF NOT EXISTS idx_runs_source ON backtest_runs(source_run_id)",
            # started_at = actual start of the latest attempt (reset on retry), so Duration
            # measures only the run that produced the result — not back to the first kickoff.
            "ALTER TABLE backtest_runs ADD COLUMN started_at INTEGER",
            "UPDATE backtest_runs SET started_at = created_at WHERE started_at IS NULL",
            # rulesets new columns (existing DBs had them as firms)
            "ALTER TABLE rulesets ADD COLUMN eval_cost_usd INTEGER",
            "ALTER TABLE rulesets ADD COLUMN activation_fee_usd INTEGER",
            "ALTER TABLE rulesets ADD COLUMN profit_split_pct REAL",
            # M3 new columns on rulesets
            "ALTER TABLE rulesets ADD COLUMN ruleset_type TEXT NOT NULL DEFAULT 'prop_eval'",
            "ALTER TABLE rulesets ADD COLUMN daily_loss_cap INTEGER",
            "ALTER TABLE rulesets ADD COLUMN weekly_loss_cap INTEGER",
            "ALTER TABLE rulesets ADD COLUMN daily_profit_goal INTEGER",
            "ALTER TABLE rulesets ADD COLUMN description TEXT",
            # Backfill ruleset_type from account_tier
            "UPDATE rulesets SET ruleset_type = 'prop_funded' WHERE account_tier = 'funded'",
            "UPDATE rulesets SET daily_loss_cap = max_loss_eod WHERE daily_loss_cap IS NULL",
            # Rename firm_id → ruleset_id in evaluations (M3)
            "ALTER TABLE evaluations RENAME COLUMN firm_id TO ruleset_id",
            "CREATE INDEX IF NOT EXISTS idx_evals_ruleset ON evaluations(ruleset_id, verdict)",
            # Compile gate — default 1 (compiled) so existing strategies aren't blocked
            "ALTER TABLE strategies ADD COLUMN is_compiled INTEGER NOT NULL DEFAULT 1",
            # User-editable description
            "ALTER TABLE strategies ADD COLUMN description TEXT",
            # Strategy-level narrative overlaid from <Strategy>.meta.json (UI only):
            # edge = one-paragraph "where the edge is", steps = JSON flow [{label,title,detail}]
            "ALTER TABLE strategies ADD COLUMN edge TEXT",
            "ALTER TABLE strategies ADD COLUMN steps TEXT",
            # Backfill: rows that predate the column (or skipped re-scan) carry NULL,
            # which fails the Strategy.steps list[dict] validation on GET /strategies.
            "UPDATE strategies SET steps = '[]' WHERE steps IS NULL",
            # Runner field on backtest_runs for platform-specific locking
            "ALTER TABLE backtest_runs ADD COLUMN runner TEXT NOT NULL DEFAULT 'ninjatrader'",
            # Strategy version registry — content-addressed (source_hash → monotonic version).
            # The single source of truth for "what versions of this strategy exist."
            # Target-agnostic: lab-VPS deploy/compile state lives on `strategies`;
            # future bot deploys record (strategy_id, target, version) in their own table.
            """CREATE TABLE IF NOT EXISTS strategy_versions (
                strategy_id  TEXT    NOT NULL,
                version      INTEGER NOT NULL,
                source_hash  TEXT    NOT NULL,
                size_bytes   INTEGER,
                created_at   INTEGER NOT NULL,
                PRIMARY KEY (strategy_id, version)
            )""",
            "CREATE UNIQUE INDEX IF NOT EXISTS idx_strategy_versions_hash ON strategy_versions(strategy_id, source_hash)",
            # Lab-VPS deploy/compile content tracking — which version is on the VPS and compiled
            "ALTER TABLE strategies ADD COLUMN deployed_source_hash TEXT",
            "ALTER TABLE strategies ADD COLUMN deployed_at INTEGER",
            "ALTER TABLE strategies ADD COLUMN compiled_source_hash TEXT",
            "ALTER TABLE strategies ADD COLUMN compiled_at INTEGER",
        ]:
            try:
                conn.execute(migration_sql)
            except Exception:
                pass

        conn.executescript("""
            CREATE TABLE IF NOT EXISTS stress_tests (
                stress_test_id     TEXT PRIMARY KEY,
                run_id             TEXT NOT NULL REFERENCES backtest_runs(run_id),
                ruleset_id         TEXT REFERENCES rulesets(id),
                status             TEXT NOT NULL,
                created_at         INTEGER NOT NULL,
                completed_at       INTEGER,
                num_simulations    INTEGER NOT NULL DEFAULT 10000,
                num_bootstrap      INTEGER NOT NULL DEFAULT 1000,
                median_final_pnl   REAL,
                pct5_final_pnl     REAL,
                pct1_final_pnl     REAL,
                median_max_dd      REAL,
                pct5_max_dd        REAL,
                pct1_max_dd        REAL,
                prob_breach        REAL,
                prob_pass_eval     REAL,
                walk_forward_windows   INTEGER NOT NULL DEFAULT 5,
                walk_forward_summary   TEXT,
                walk_forward_degradation REAL,
                sensitivity_summary    TEXT,
                sensitivity_max_degradation REAL,
                grade              TEXT,
                grade_reasons      TEXT,
                equity_paths_path  TEXT,
                distribution_path  TEXT,
                error_message      TEXT
            );
            CREATE INDEX IF NOT EXISTS idx_stress_tests_run ON stress_tests(run_id);
            CREATE INDEX IF NOT EXISTS idx_stress_tests_grade ON stress_tests(grade);

            CREATE TABLE IF NOT EXISTS optimizations (
                optimization_id     TEXT PRIMARY KEY,
                strategy_id         TEXT NOT NULL REFERENCES strategies(id),
                instrument          TEXT NOT NULL,
                start_date          TEXT NOT NULL,
                end_date            TEXT NOT NULL,
                commission_per_side REAL NOT NULL,
                slippage_ticks      INTEGER NOT NULL,
                ruleset_id          TEXT NOT NULL REFERENCES rulesets(id),
                mode                TEXT NOT NULL,
                search_method       TEXT NOT NULL,
                param_grid          TEXT NOT NULL,
                status              TEXT NOT NULL,
                estimated_runs      INTEGER NOT NULL,
                completed_runs      INTEGER NOT NULL DEFAULT 0,
                best_run_id         TEXT,
                source_run_id       TEXT,
                created_at          INTEGER NOT NULL,
                completed_at        INTEGER
            );

            CREATE INDEX IF NOT EXISTS idx_opts_strategy
                ON optimizations(strategy_id, created_at DESC);
        """)

        # Optimizations column rename (existing DBs had firm_id)
        for migration_sql in [
            "ALTER TABLE optimizations RENAME COLUMN firm_id TO ruleset_id",
            "ALTER TABLE optimizations ADD COLUMN source_run_id TEXT",
            "ALTER TABLE backtest_runs ADD COLUMN stress_test_id TEXT",
            "ALTER TABLE backtest_runs ADD COLUMN walk_forward_window_id TEXT",
            "CREATE INDEX IF NOT EXISTS idx_runs_stress ON backtest_runs(stress_test_id)",
            "ALTER TABLE stress_tests ADD COLUMN mc_completed_at INTEGER",
            "ALTER TABLE stress_tests ADD COLUMN wf_completed_at INTEGER",
            "ALTER TABLE optimizations ADD COLUMN regime_filter TEXT",
            # Pass 1 — foundational config columns
            "ALTER TABLE rulesets ADD COLUMN risk_per_trade_pct REAL",
            "ALTER TABLE rulesets ADD COLUMN max_consecutive_losses INTEGER",
            "ALTER TABLE rulesets ADD COLUMN earliest_entry_time_et TEXT",
            "ALTER TABLE rulesets ADD COLUMN latest_entry_time_et TEXT",
            "ALTER TABLE rulesets ADD COLUMN days_of_week_allowed TEXT",
            "ALTER TABLE rulesets ADD COLUMN daily_profit_target INTEGER",
            "ALTER TABLE rulesets ADD COLUMN daily_profit_lock_pct REAL",
            "ALTER TABLE rulesets ADD COLUMN default_commission_per_side REAL",
            "ALTER TABLE rulesets ADD COLUMN default_slippage_ticks INTEGER",
            "ALTER TABLE rulesets ADD COLUMN daily_halt_fraction REAL",
            # Pass 2.5 — update source_path to new strategies/ top-level location
            "UPDATE strategies SET source_path = 'strategies/ninjatrader/ORB.cs' WHERE id = 'orb'",
            "UPDATE strategies SET source_path = 'strategies/ninjatrader/VWAP_MR.cs' WHERE id = 'vwap_mr'",
            "UPDATE strategies SET source_path = 'strategies/ninjatrader/Momentum.cs' WHERE id = 'momentum'",
            # M5 — market and drawdown_unit on rulesets
            # NOT NULL DEFAULT means existing rows get the default automatically in SQLite.
            "ALTER TABLE rulesets ADD COLUMN market TEXT NOT NULL DEFAULT 'futures'",
            "ALTER TABLE rulesets ADD COLUMN drawdown_unit TEXT NOT NULL DEFAULT 'usd'",
            # Prop-firm rule corrections — trailing max-loss lock, consistency action, extra links
            "ALTER TABLE rulesets ADD COLUMN mll_lock_balance REAL",
            "ALTER TABLE rulesets ADD COLUMN consistency_breach_action TEXT",
            "ALTER TABLE rulesets ADD COLUMN reference_urls TEXT",
            # Backfill verified prop-firm rule data on the six prop EVAL rows (funded/personal untouched).
            # None of these firms has a daily loss limit — clear the phantom cap that fed a false grading rule.
            "UPDATE rulesets SET daily_loss_cap = NULL "
            "WHERE id IN ('lucidflex_50k_eval','lucidflex_100k_eval',"
            "'fundednext_flex_50k_eval','fundednext_flex_100k_eval',"
            "'tradeify_50k_eval','tradeify_100k_eval')",
            # Trailing max-loss lock balances — LucidFlex and FundedNext lock; Tradeify does not lock in eval.
            "UPDATE rulesets SET mll_lock_balance = 50100 WHERE id = 'lucidflex_50k_eval'",
            "UPDATE rulesets SET mll_lock_balance = 100100 WHERE id = 'lucidflex_100k_eval'",
            "UPDATE rulesets SET mll_lock_balance = 50100 WHERE id = 'fundednext_flex_50k_eval'",
            "UPDATE rulesets SET mll_lock_balance = 100100 WHERE id = 'fundednext_flex_100k_eval'",
            # Consistency breach action — FundedNext raises the target instead of failing; null = fail elsewhere.
            "UPDATE rulesets SET consistency_breach_action = 'raise_target' "
            "WHERE id IN ('fundednext_flex_50k_eval','fundednext_flex_100k_eval')",
            # Extra rule links (JSON arrays, parsed like the other JSON columns).
            "UPDATE rulesets SET reference_urls = "
            "'[\"https://support.lucidtrading.com/en/articles/12945815-lucidflex-drawdown\","
            "\"https://support.lucidtrading.com/en/articles/12945808-lucidflex-scaling-plan\"]' "
            "WHERE id IN ('lucidflex_50k_eval','lucidflex_100k_eval')",
            "UPDATE rulesets SET reference_urls = "
            "'[\"https://helpfutures.fundednext.com/en/articles/14878830-how-do-i-pass-fundednext-futures-flex-challenge\"]' "
            "WHERE id IN ('fundednext_flex_50k_eval','fundednext_flex_100k_eval')",
            # LucidFlex publishes no 5-day minimum — clear the phantom min_trading_days on both eval rows.
            "UPDATE rulesets SET min_trading_days = NULL "
            "WHERE id IN ('lucidflex_50k_eval','lucidflex_100k_eval')",
            # Trailing-MLL detail columns on evaluations (for the UI).
            "ALTER TABLE evaluations ADD COLUMN mll_final_floor REAL",
            "ALTER TABLE evaluations ADD COLUMN mll_highest_eod_balance REAL",
            "ALTER TABLE evaluations ADD COLUMN mll_breach_day INTEGER",
            "ALTER TABLE evaluations ADD COLUMN mll_min_floor_distance REAL",
            # Consistency breach action — raised profit target when a breach doesn't fail.
            "ALTER TABLE evaluations ADD COLUMN adjusted_profit_target REAL",
            # Contract-cap check status — 'not_evaluable' until per-trade size is captured.
            "ALTER TABLE evaluations ADD COLUMN contract_cap_status TEXT",
            # Canonical daily-√252 Sharpe on single runs; platform's own value kept separately.
            "ALTER TABLE backtest_runs ADD COLUMN platform_sharpe REAL",
            "ALTER TABLE backtest_runs ADD COLUMN sharpe_low_sample INTEGER",
            # Profit concentration (overfit detector) persisted for later grading use.
            "ALTER TABLE backtest_runs ADD COLUMN profit_concentration_pct REAL",
            # Tradeify corrections — current $50k target is $3,000 (old accounts grandfathered at
            # $2,500); and the $50k/$100k eval trailing MLL locks at start+$100.
            "UPDATE rulesets SET profit_target = 3000 WHERE id = 'tradeify_50k_eval'",
            "UPDATE rulesets SET mll_lock_balance = 50100 WHERE id = 'tradeify_50k_eval'",
            "UPDATE rulesets SET mll_lock_balance = 100100 WHERE id = 'tradeify_100k_eval'",
            # Speed Step 3 — grid sensitivity stored on the optimization row
            "ALTER TABLE optimizations ADD COLUMN grid_sensitivity_score REAL",
            "ALTER TABLE optimizations ADD COLUMN grid_sensitivity_summary TEXT",
            # bar_type/bar_value were missing from optimizations table
            "ALTER TABLE optimizations ADD COLUMN bar_type TEXT NOT NULL DEFAULT 'Minute'",
            "ALTER TABLE optimizations ADD COLUMN bar_value INTEGER NOT NULL DEFAULT 5",
            # Personal demo rulesets — fail-condition columns the evaluator reads in a
            # later pass: % drawdown from peak balance, and consecutive capped-loss days.
            "ALTER TABLE rulesets ADD COLUMN max_drawdown_from_peak_pct REAL",
            "ALTER TABLE rulesets ADD COLUMN max_consecutive_loss_days INTEGER",
            # Consolidate the three placeholder personal/demo rows into two clean demo
            # rows (one forex, one futures). The futures id rename
            # (personal_futures_10k_example → personal_futures_demo) lives in
            # _migrate_personal_demo_rename() — it has stress_tests FK references, so
            # the rename needs FK off, which can't be toggled inside this transaction.
            "DELETE FROM rulesets WHERE id = 'personal_forex_main'",
            # Verified personal demo rules on a $10k balance: $500 (5%) daily loss cap,
            # $1,000 (10%) daily profit target, fail at 15% drawdown from peak or 3
            # consecutive capped-loss days. max_loss_eod is NOT NULL in the schema, so
            # 0 is the sentinel for "no trailing EOD rule" — the evaluator pass MUST
            # treat personal max_loss_eod = 0 as rule-absent (today personal/demo types
            # skip the trailing check entirely, so the sentinel is inert).
            # account_tier 'demo' so nothing downstream treats these as live accounts.
            # Guarded one-shot: only fires while the new columns are still NULL, so
            # later manual edits survive restarts.
            "UPDATE rulesets SET ruleset_type = 'personal', account_tier = 'demo', "
            "max_loss_eod = 0, daily_loss_cap = 500, weekly_loss_cap = NULL, "
            "daily_profit_target = 1000, max_drawdown_from_peak_pct = 15.0, "
            "max_consecutive_loss_days = 3, consistency_pct = NULL, "
            "min_trading_days = NULL, mll_lock_balance = NULL, max_contracts = NULL, "
            "daily_profit_goal = NULL "
            "WHERE id IN ('personal_forex_demo','personal_futures_demo') "
            "AND max_drawdown_from_peak_pct IS NULL",
        ]:
            try:
                conn.execute(migration_sql)
            except Exception:
                pass

        # NOTE: Apex EOD rows are seeded in _seed_rulesets (per-id, runs every init_db so it
        # covers both live and fresh DBs). Do NOT insert them here in the migration section —
        # that runs before _seed_rulesets and would make the table non-empty, tripping the
        # legacy `COUNT(*) == 0` guard on the LucidFlex seed block and dropping LucidFlex.

        # Backfill runner on backtest_runs for rows created before the runner column existed.
        # The column defaulted to 'ninjatrader', so MT5 strategy runs got the wrong value.
        conn.execute("""
            UPDATE backtest_runs
            SET runner = 'mt5'
            WHERE runner = 'ninjatrader'
            AND strategy_id IN (SELECT id FROM strategies WHERE runner = 'mt5')
        """)

        # Pass 1 — backfill foundational config for all existing rulesets where null.
        # Personal-specific overrides must run BEFORE the blanket defaults so the
        # blanket update (which only touches NULL rows) doesn't overwrite them.
        _DAYS_JSON = '["mon","tue","wed","thu","fri"]'
        for sql in [
            # personal futures demo: 1.0% risk (higher — smaller account), 0.5 halt fraction
            "UPDATE rulesets SET risk_per_trade_pct = 1.0 "
            "WHERE id = 'personal_futures_demo' AND risk_per_trade_pct IS NULL",
            "UPDATE rulesets SET daily_halt_fraction = 0.5 "
            "WHERE id = 'personal_futures_demo' AND daily_halt_fraction IS NULL",
            # personal futures demo: 80% lock-in on the daily target
            "UPDATE rulesets SET daily_profit_lock_pct = 0.80 "
            "WHERE id = 'personal_futures_demo' AND daily_profit_lock_pct IS NULL",
            # prop_eval rows: $1500 daily target with 80% lock-in, 0.6 halt fraction
            "UPDATE rulesets SET daily_profit_target = 1500, daily_profit_lock_pct = 0.80 "
            "WHERE daily_profit_target IS NULL AND ruleset_type = 'prop_eval'",
            "UPDATE rulesets SET daily_halt_fraction = 0.6 "
            "WHERE daily_halt_fraction IS NULL AND ruleset_type = 'prop_eval'",
            # blanket defaults for all remaining NULL rows
            "UPDATE rulesets SET risk_per_trade_pct = 0.5 WHERE risk_per_trade_pct IS NULL",
            "UPDATE rulesets SET max_consecutive_losses = 3 WHERE max_consecutive_losses IS NULL",
            f"UPDATE rulesets SET earliest_entry_time_et = '09:30' WHERE earliest_entry_time_et IS NULL",
            f"UPDATE rulesets SET latest_entry_time_et = '15:00' WHERE latest_entry_time_et IS NULL",
            f"UPDATE rulesets SET days_of_week_allowed = '{_DAYS_JSON}' WHERE days_of_week_allowed IS NULL",
            "UPDATE rulesets SET default_commission_per_side = 2.25 WHERE default_commission_per_side IS NULL",
            "UPDATE rulesets SET default_slippage_ticks = 1 WHERE default_slippage_ticks IS NULL",
            # prop_funded and demo rows: daily_profit_target, daily_profit_lock_pct, daily_halt_fraction intentionally NULL
        ]:
            conn.execute(sql)

        pass  # strategy rename handled after this block via _migrate_strategy_renames()

        conn.executescript("""
            CREATE TABLE IF NOT EXISTS instrument_daily_ohlc (
                instrument  TEXT NOT NULL,
                date        TEXT NOT NULL,
                open        REAL NOT NULL,
                high        REAL NOT NULL,
                low         REAL NOT NULL,
                close       REAL NOT NULL,
                fetched_at  INTEGER NOT NULL,
                source      TEXT NOT NULL,
                PRIMARY KEY (instrument, date)
            );
            CREATE INDEX IF NOT EXISTS idx_ohlc_instrument
                ON instrument_daily_ohlc(instrument);

            CREATE TABLE IF NOT EXISTS instrument_metadata (
                symbol            TEXT PRIMARY KEY,
                market            TEXT NOT NULL,
                display_name      TEXT NOT NULL,
                tick_size         REAL,
                point_value_usd   REAL,
                broker_suffix     TEXT,
                default_session   TEXT,
                notes             TEXT
            );

            CREATE TABLE IF NOT EXISTS instrument_intraday_ohlc (
                instrument  TEXT NOT NULL,
                timeframe   TEXT NOT NULL,
                timestamp   TEXT NOT NULL,
                open        REAL NOT NULL,
                high        REAL NOT NULL,
                low         REAL NOT NULL,
                close       REAL NOT NULL,
                fetched_at  INTEGER NOT NULL,
                source      TEXT NOT NULL,
                PRIMARY KEY (instrument, timeframe, timestamp)
            );
            CREATE INDEX IF NOT EXISTS idx_intraday_ohlc_instrument
                ON instrument_intraday_ohlc(instrument, timeframe);

            CREATE TABLE IF NOT EXISTS job_queue (
                queue_id    TEXT PRIMARY KEY,
                job_type    TEXT NOT NULL,
                payload     TEXT NOT NULL,
                status      TEXT NOT NULL DEFAULT 'pending',
                position    INTEGER NOT NULL,
                created_at  INTEGER NOT NULL,
                started_at  INTEGER,
                finished_at INTEGER,
                error       TEXT
            );
            CREATE INDEX IF NOT EXISTS idx_queue_status ON job_queue(status, position);
        """)

        # Converge display names on existing DBs (fresh seeds already use these).
        for _rid, _rname in _RULESET_DISPLAY_NAMES.items():
            conn.execute("UPDATE rulesets SET name = ? WHERE id = ?", (_rname, _rid))

        _seed_rulesets(conn)

    # Run outside the main context manager — needs FK enforcement off, which
    # can't be toggled inside an active transaction in SQLite.
    _migrate_strategy_renames()
    _migrate_personal_demo_rename()
    _migrate_optimizations_nullable_ruleset()


def _migrate_optimizations_nullable_ruleset() -> None:
    """Make optimizations.ruleset_id nullable so MT5 optimizations need no ruleset."""
    raw = sqlite3.connect(DB_PATH)
    raw.execute("PRAGMA journal_mode=WAL")
    raw.execute("PRAGMA foreign_keys=OFF")
    try:
        info = raw.execute("PRAGMA table_info(optimizations)").fetchall()
        col = next((c for c in info if c[1] == "ruleset_id"), None)
        if not col or col[3] == 0:
            return  # Already nullable or column missing
        # Use explicit column list so column ordering in the old table never causes
        # data to shift into wrong columns (SELECT * maps by position, not name).
        existing_cols = {c[1] for c in info}
        col_list = ", ".join(
            c for c in [
                "optimization_id", "strategy_id", "instrument", "start_date",
                "end_date", "commission_per_side", "slippage_ticks", "ruleset_id",
                "mode", "search_method", "param_grid", "status", "estimated_runs",
                "completed_runs", "best_run_id", "source_run_id", "created_at",
                "completed_at", "regime_filter",
            ]
            if c in existing_cols
        )
        raw.executescript(f"""
            BEGIN;
            CREATE TABLE optimizations_new (
                optimization_id     TEXT PRIMARY KEY,
                strategy_id         TEXT NOT NULL REFERENCES strategies(id),
                instrument          TEXT NOT NULL,
                start_date          TEXT NOT NULL,
                end_date            TEXT NOT NULL,
                commission_per_side REAL NOT NULL,
                slippage_ticks      INTEGER NOT NULL,
                ruleset_id          TEXT REFERENCES rulesets(id),
                mode                TEXT NOT NULL,
                search_method       TEXT NOT NULL,
                param_grid          TEXT NOT NULL,
                status              TEXT NOT NULL,
                estimated_runs      INTEGER NOT NULL,
                completed_runs      INTEGER NOT NULL DEFAULT 0,
                best_run_id         TEXT,
                source_run_id       TEXT,
                created_at          INTEGER NOT NULL,
                completed_at        INTEGER,
                regime_filter       TEXT
            );
            INSERT INTO optimizations_new ({col_list}) SELECT {col_list} FROM optimizations;
            DROP TABLE optimizations;
            ALTER TABLE optimizations_new RENAME TO optimizations;
            CREATE INDEX IF NOT EXISTS idx_opts_strategy ON optimizations(strategy_id, created_at DESC);
            COMMIT;
        """)
    except Exception:
        try: raw.execute("ROLLBACK")
        except Exception: pass
    finally:
        raw.execute("PRAGMA foreign_keys=ON")
        raw.close()


def _migrate_strategy_renames() -> None:
    """
    Rename strategy rows when .cs files drop the _LucidFlex suffix (Pass 1).
    Uses a raw connection with FK off so we can update the PK and its FK
    references atomically without the constraint firing mid-migration.
    """
    raw = sqlite3.connect(DB_PATH)
    raw.execute("PRAGMA journal_mode=WAL")
    # FK off is only safe here because we immediately update all referencing rows
    # before committing, leaving no dangling references in the final state.
    raw.execute("PRAGMA foreign_keys=OFF")
    try:
        for old_id, new_id, new_class, new_name in [
            ("orb_lucidflex",      "orb",      "ORB",      "Opening Range Breakout"),
            ("vwap_mr_lucidflex",  "vwap_mr",  "VWAP_MR",  "VWAP Mean Reversion"),
            ("momentum_lucidflex", "momentum", "Momentum",  "Intraday Momentum Pullback"),
        ]:
            if not raw.execute("SELECT 1 FROM strategies WHERE id=?", (old_id,)).fetchone():
                continue
            # Update children first so no row references the old PK after commit
            for tbl, col in [("backtest_runs", "strategy_id"), ("optimizations", "strategy_id")]:
                raw.execute(f"UPDATE {tbl} SET {col}=? WHERE {col}=?", (new_id, old_id))
            new_exists = raw.execute("SELECT 1 FROM strategies WHERE id=?", (new_id,)).fetchone()
            if new_exists:
                # new_id already exists (scanner created it first) — drop the stale old row
                raw.execute("DELETE FROM strategies WHERE id=?", (old_id,))
            else:
                raw.execute(
                    "UPDATE strategies SET id=?, class_name=?, name=? WHERE id=?",
                    (new_id, new_class, new_name, old_id),
                )
        raw.commit()
    except Exception:
        raw.rollback()
        raise
    finally:
        raw.execute("PRAGMA foreign_keys=ON")
        raw.close()


def _migrate_personal_demo_rename() -> None:
    """
    Rename ruleset personal_futures_10k_example → personal_futures_demo.
    Same FK-off pattern as _migrate_strategy_renames: the old id has stress_tests
    references, so children are repointed first, then the PK row is renamed — or,
    if the seed already created the new id, the stale old row is dropped.
    """
    old_id, new_id = "personal_futures_10k_example", "personal_futures_demo"
    raw = sqlite3.connect(DB_PATH)
    raw.execute("PRAGMA journal_mode=WAL")
    # FK off is only safe here because we immediately update all referencing rows
    # before committing, leaving no dangling references in the final state.
    raw.execute("PRAGMA foreign_keys=OFF")
    try:
        if raw.execute("SELECT 1 FROM rulesets WHERE id=?", (old_id,)).fetchone():
            for tbl in ("evaluations", "optimizations", "stress_tests"):
                raw.execute(
                    f"UPDATE {tbl} SET ruleset_id=? WHERE ruleset_id=?", (new_id, old_id)
                )
            if raw.execute("SELECT 1 FROM rulesets WHERE id=?", (new_id,)).fetchone():
                # new id already seeded with the verified demo values — drop the stale row
                raw.execute("DELETE FROM rulesets WHERE id=?", (old_id,))
            else:
                raw.execute(
                    "UPDATE rulesets SET id=?, name=?, description=? WHERE id=?",
                    (
                        new_id,
                        "Personal Futures Demo Account",
                        "Futures demo/paper account. No real capital at risk.",
                        old_id,
                    ),
                )
        raw.commit()
    except Exception:
        raw.rollback()
        raise
    finally:
        raw.execute("PRAGMA foreign_keys=ON")
        raw.close()


# Apex EOD eval rows (Rithmic). Verified 2026-06-11. Defined once so the live-DB migration and
# the fresh-build seed insert identical data. daily_loss_cap is a SOFT pause (informational),
# never a verdict input — the ladder uses trailing-MLL + target + consistency only.
_APEX_EOD_NOTES = (
    "Apex EOD eval, Rithmic/Wealthcharts (NinjaTrader). EOD trailing drawdown, locks at "
    "start+profit_target (53k/106k) once highest EOD closes above start+target+drawdown. "
    "Tradovate variant trails forever -- not seeded. DLL is a SOFT rule: hitting it pauses "
    "trading for the day, does NOT fail -- informational only in backtest (needs intraday data "
    "to enforce). No consistency, no min days in eval. 30-day access period to pass (time limit, "
    "not modeled). Contract limit is total contracts mapped to mini/micro. Verified from "
    "docs_url 2026-06-11."
)
_APEX_INSTRUMENTS = '["MES", "MNQ", "MGC", "MCL", "MYM", "M2K", "ES", "NQ", "GC", "CL", "YM", "RTY"]'
_APEX_DOCS = "https://apextraderfunding.com/help-center/eod-trailing-drawdown-accounts/eod-evaluations/"
_APEX_REF = '["https://apextraderfunding.com/help-center/eod-trailing-drawdown-accounts/eod-drawdown-explained/"]'
_APEX_DAYS = '["mon","tue","wed","thu","fri"]'

_APEX_EOD_EVAL_ROWS = [
    {
        "id": "apex_eod_50k_eval", "name": "EOD $50k Evaluation",
        "account_size": 50000, "profit_target": 3000, "max_loss_eod": 2000,
        "max_loss_intraday": None, "drawdown_type": "trailing_eod",
        "consistency_pct": None, "min_trading_days": None, "force_flat_time_et": None,
        "allowed_instruments": _APEX_INSTRUMENTS,
        "max_contracts": '{"mini_max": 6, "micro_max": 60, "scaling": null}',
        "platform_support": '["NinjaTrader", "Rithmic"]', "account_tier": "eval",
        "docs_url": _APEX_DOCS, "notes": _APEX_EOD_NOTES,
        "eval_cost_usd": None, "activation_fee_usd": None, "profit_split_pct": None,
        "ruleset_type": "prop_eval", "daily_loss_cap": 1000, "weekly_loss_cap": None,
        "daily_profit_goal": None, "description": None,
        "risk_per_trade_pct": 0.5, "max_consecutive_losses": 3,
        "earliest_entry_time_et": "09:30", "latest_entry_time_et": "15:00",
        "days_of_week_allowed": _APEX_DAYS, "daily_profit_target": 1500,
        "daily_profit_lock_pct": 0.8, "default_commission_per_side": 2.25,
        "default_slippage_ticks": 1, "daily_halt_fraction": 0.6,
        "market": "futures", "drawdown_unit": "usd",
        "mll_lock_balance": 53000, "consistency_breach_action": None, "reference_urls": _APEX_REF,
    },
    {
        "id": "apex_eod_100k_eval", "name": "EOD $100k Evaluation",
        "account_size": 100000, "profit_target": 6000, "max_loss_eod": 3000,
        "max_loss_intraday": None, "drawdown_type": "trailing_eod",
        "consistency_pct": None, "min_trading_days": None, "force_flat_time_et": None,
        "allowed_instruments": _APEX_INSTRUMENTS,
        "max_contracts": '{"mini_max": 8, "micro_max": 80, "scaling": null}',
        "platform_support": '["NinjaTrader", "Rithmic"]', "account_tier": "eval",
        "docs_url": _APEX_DOCS, "notes": _APEX_EOD_NOTES,
        "eval_cost_usd": None, "activation_fee_usd": None, "profit_split_pct": None,
        "ruleset_type": "prop_eval", "daily_loss_cap": 1500, "weekly_loss_cap": None,
        "daily_profit_goal": None, "description": None,
        "risk_per_trade_pct": 0.5, "max_consecutive_losses": 3,
        "earliest_entry_time_et": "09:30", "latest_entry_time_et": "15:00",
        "days_of_week_allowed": _APEX_DAYS, "daily_profit_target": 1500,
        "daily_profit_lock_pct": 0.8, "default_commission_per_side": 2.25,
        "default_slippage_ticks": 1, "daily_halt_fraction": 0.6,
        "market": "futures", "drawdown_unit": "usd",
        "mll_lock_balance": 106000, "consistency_breach_action": None, "reference_urls": _APEX_REF,
    },
]


# Canonical display names. The firm name lives in the UI group header (Lucid /
# Tradeify / FundedNext / Apex) so row names carry only the program/challenge —
# "LucidFlex" stays because it is Lucid's PROGRAM name, not the firm name
# (firm: Lucid Trading; verified against the stored docs_url articles).
_RULESET_DISPLAY_NAMES = {
    "lucidflex_50k_eval":          "LucidFlex $50k Evaluation",
    "lucidflex_100k_eval":         "LucidFlex $100k Evaluation",
    "lucidflex_50k_funded":        "LucidFlex $50k Funded",
    "lucidflex_100k_funded":       "LucidFlex $100k Funded",
    "tradeify_50k_eval":           "Select $50k Evaluation",
    "tradeify_100k_eval":          "Select $100k Evaluation",
    "tradeify_50k_funded":         "Select $50k Funded (Flex)",
    "tradeify_100k_funded":        "Select $100k Funded (Flex)",
    "fundednext_flex_50k_eval":    "Futures Flex $50k Challenge",
    "fundednext_flex_100k_eval":   "Futures Flex $100k Challenge",
    "fundednext_flex_50k_funded":  "Futures Flex $50k Funded",
    "fundednext_flex_100k_funded": "Futures Flex $100k Funded",
    "apex_eod_50k_eval":           "EOD $50k Evaluation",
    "apex_eod_100k_eval":          "EOD $100k Evaluation",
}


def _seed_apex_eod_eval(conn: sqlite3.Connection, now: int) -> None:
    """Idempotent per-id insert of the Apex EOD eval rows. Never overwrites edited rows."""
    cols = list(_APEX_EOD_EVAL_ROWS[0].keys())
    sql = (
        "INSERT INTO rulesets (" + ", ".join(cols) + ", created_at, updated_at) "
        "VALUES (" + ", ".join(["?"] * len(cols)) + ", ?, ?)"
    )
    for row in _APEX_EOD_EVAL_ROWS:
        if not conn.execute("SELECT 1 FROM rulesets WHERE id=?", (row["id"],)).fetchone():
            conn.execute(sql, tuple(row[c] for c in cols) + (now, now))


def _seed_rulesets(conn: sqlite3.Connection) -> None:
    now = int(time.time())
    # LucidFlex prop rows are seeded via the per-id _PROP_SEED_ROWS block below (same
    # idempotent pattern as FundedNext/Tradeify) — the legacy COUNT(*)==0 all-or-nothing
    # guard was removed so they reproduce on a fresh build with the corrected values.

    # Personal demo rulesets (idempotent, per-id) — exactly two: one forex, one futures.
    # Relaxed but real, gradeable rules on a $10k balance: $500 (5%) daily loss cap,
    # $1,000 (10%) daily profit target; fail at 15% drawdown from peak balance or 3
    # consecutive capped-loss days (enforcement lands in a later evaluator pass).
    # max_loss_eod is NOT NULL in the schema, so 0 is the sentinel for "no trailing
    # EOD rule on personal accounts" — the evaluator must treat it as rule-absent.
    # account_tier 'demo' so nothing downstream treats these as live accounts.
    _FX_INSTRUMENTS = json.dumps([
        "XAUUSD", "XAGUSD", "EURUSD", "GBPUSD", "GBPJPY",
        "USDJPY", "AUDJPY", "CADJPY", "AUDUSD", "USDCAD", "EURGBP", "NAS100",
    ])
    _FX_DAYS = json.dumps(["sun", "mon", "tue", "wed", "thu"])
    _FUT_DAYS = json.dumps(["mon", "tue", "wed", "thu", "fri"])

    _PERSONAL_DEMO_SQL = """
        INSERT INTO rulesets
            (id, name, account_size, profit_target, max_loss_eod, max_loss_intraday,
             drawdown_type, consistency_pct, min_trading_days, force_flat_time_et,
             allowed_instruments, max_contracts, platform_support,
             account_tier, ruleset_type, market, drawdown_unit,
             daily_loss_cap, weekly_loss_cap, daily_profit_target,
             daily_profit_lock_pct, risk_per_trade_pct, max_consecutive_losses,
             earliest_entry_time_et, latest_entry_time_et, days_of_week_allowed,
             default_commission_per_side, default_slippage_ticks, daily_halt_fraction,
             max_drawdown_from_peak_pct, max_consecutive_loss_days, description,
             created_at, updated_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """

    if not conn.execute("SELECT 1 FROM rulesets WHERE id=?", ("personal_forex_demo",)).fetchone():
        conn.execute(_PERSONAL_DEMO_SQL, (
            "personal_forex_demo",
            "Personal Forex Demo Account",
            10000, 0, 0, None,                  # max_loss_eod 0 = sentinel, no trailing EOD rule
            "static", None, None, None,         # force_flat_time_et null — MT5 strategies manage sessions
            _FX_INSTRUMENTS,
            None,                               # max_contracts null — no scaling on personal
            json.dumps(["MT5"]),
            "demo", "personal", "forex", "usd",
            500, None, 1000,
            0.80, 1.0, 3,
            None, None,                         # entry hours null — FX runs 24h
            _FX_DAYS,
            0.0, 1, None,
            15.0, 3,
            "Forex demo/paper account. No real capital at risk.",
            now, now,
        ))

    if not conn.execute("SELECT 1 FROM rulesets WHERE id=?", ("personal_futures_demo",)).fetchone():
        conn.execute(_PERSONAL_DEMO_SQL, (
            "personal_futures_demo",
            "Personal Futures Demo Account",
            10000, 0, 0, None,                  # max_loss_eod 0 = sentinel, no trailing EOD rule
            "static", None, None, "15:50",
            json.dumps(["MES", "MNQ", "MGC", "MCL"]),
            None,                               # max_contracts null — no scaling on personal
            json.dumps(["NinjaTrader", "Tradovate"]),
            "demo", "personal", "futures", "usd",
            500, None, 1000,
            0.80, 1.0, 3,
            "09:30", "15:00",
            _FUT_DAYS,
            2.25, 1, 0.5,
            15.0, 3,
            "Futures demo/paper account. No real capital at risk.",
            now, now,
        ))

    # ── FundedNext + Tradeify prop rows (cleanup) ────────────────────────────────
    # Seeded from the corrected live-DB values so a from-scratch rebuild reproduces all
    # three firms (LucidFlex seeded above). Full column set, so the rows are correct
    # regardless of backfill ordering. Per-id existence check → idempotent; never
    # overwrites edited rows (same pattern as the personal rows).
    _PROP_SEED_COLS = ['id', 'name', 'account_size', 'profit_target', 'max_loss_eod', 'max_loss_intraday', 'drawdown_type', 'consistency_pct', 'min_trading_days', 'force_flat_time_et', 'allowed_instruments', 'max_contracts', 'platform_support', 'account_tier', 'docs_url', 'notes', 'eval_cost_usd', 'activation_fee_usd', 'profit_split_pct', 'ruleset_type', 'daily_loss_cap', 'weekly_loss_cap', 'daily_profit_goal', 'description', 'risk_per_trade_pct', 'max_consecutive_losses', 'earliest_entry_time_et', 'latest_entry_time_et', 'days_of_week_allowed', 'daily_profit_target', 'daily_profit_lock_pct', 'default_commission_per_side', 'default_slippage_ticks', 'daily_halt_fraction', 'market', 'drawdown_unit', 'mll_lock_balance', 'consistency_breach_action', 'reference_urls']
    _PROP_SEED_ROWS = [
        {'id': 'lucidflex_50k_eval', 'name': 'LucidFlex $50k Evaluation', 'account_size': 50000, 'profit_target': 3000, 'max_loss_eod': 2000, 'max_loss_intraday': None, 'drawdown_type': 'trailing_eod', 'consistency_pct': 50.0, 'min_trading_days': None, 'force_flat_time_et': '16:45', 'allowed_instruments': '["MES", "MNQ", "MGC", "MCL", "MYM", "M2K"]', 'max_contracts': '{"mini_max": 4, "micro_max": 40, "scaling": null}', 'platform_support': '["NinjaTrader", "Tradovate"]', 'account_tier': 'eval', 'docs_url': 'https://support.lucidtrading.com/en/articles/12945790-lucidflex-evaluation-account', 'notes': "Verified from docs_url on 2026-05-29 CORRECTED 2026-05-31: drawdown_type -> trailing_eod (was flat); force_flat_time_et -> 16:45 (was 15:30); eval contracts set to fixed full size (50k 4/40, 100k 6/60); funded contract scaling added. Drawdown is EOD trailing, floor max-loss distance below highest EOD close, trails up never down, locks once account clears Initial Trail Balance; EXACT LOCK VALUE UNVERIFIED (confirm at support.lucidtrading.com). Funded scaling is BIDIRECTIONAL (limits rise AND fall with EOD simulated-profit band; can drop after payouts). Microscalping flag threshold is 5 SECONDS. Auto-close 4:45pm ET, no overnight. TODO/VERIFY: sources conflict on whether 50k/100k carry a fixed DAILY LOSS LIMIT in eval + early funded (converting to a 60%-of-highest-EOD-profit LucidScale DLL above the Initial Trail Balance). max_loss_intraday left UNCHANGED -- confirm the DLL dollar amounts against Lucid's DLL article and backfill if real.", 'eval_cost_usd': None, 'activation_fee_usd': None, 'profit_split_pct': None, 'ruleset_type': 'prop_eval', 'daily_loss_cap': None, 'weekly_loss_cap': None, 'daily_profit_goal': None, 'description': None, 'risk_per_trade_pct': 0.5, 'max_consecutive_losses': 3, 'earliest_entry_time_et': '09:30', 'latest_entry_time_et': '15:00', 'days_of_week_allowed': '["mon","tue","wed","thu","fri"]', 'daily_profit_target': 1500, 'daily_profit_lock_pct': 0.8, 'default_commission_per_side': 2.25, 'default_slippage_ticks': 1, 'daily_halt_fraction': 0.6, 'market': 'futures', 'drawdown_unit': 'usd', 'mll_lock_balance': 50100.0, 'consistency_breach_action': None, 'reference_urls': '["https://support.lucidtrading.com/en/articles/12945815-lucidflex-drawdown","https://support.lucidtrading.com/en/articles/12945808-lucidflex-scaling-plan"]'},
        {'id': 'lucidflex_100k_eval', 'name': 'LucidFlex $100k Evaluation', 'account_size': 100000, 'profit_target': 6000, 'max_loss_eod': 3000, 'max_loss_intraday': None, 'drawdown_type': 'trailing_eod', 'consistency_pct': 50.0, 'min_trading_days': None, 'force_flat_time_et': '16:45', 'allowed_instruments': '["MES", "MNQ", "MGC", "MCL", "MYM", "M2K"]', 'max_contracts': '{"mini_max": 6, "micro_max": 60, "scaling": null}', 'platform_support': '["NinjaTrader", "Tradovate"]', 'account_tier': 'eval', 'docs_url': 'https://support.lucidtrading.com/en/articles/12945790-lucidflex-evaluation-account', 'notes': "Verified from docs_url on 2026-05-29 CORRECTED 2026-05-31: drawdown_type -> trailing_eod (was flat); force_flat_time_et -> 16:45 (was 15:30); eval contracts set to fixed full size (50k 4/40, 100k 6/60); funded contract scaling added. Drawdown is EOD trailing, floor max-loss distance below highest EOD close, trails up never down, locks once account clears Initial Trail Balance; EXACT LOCK VALUE UNVERIFIED (confirm at support.lucidtrading.com). Funded scaling is BIDIRECTIONAL (limits rise AND fall with EOD simulated-profit band; can drop after payouts). Microscalping flag threshold is 5 SECONDS. Auto-close 4:45pm ET, no overnight. TODO/VERIFY: sources conflict on whether 50k/100k carry a fixed DAILY LOSS LIMIT in eval + early funded (converting to a 60%-of-highest-EOD-profit LucidScale DLL above the Initial Trail Balance). max_loss_intraday left UNCHANGED -- confirm the DLL dollar amounts against Lucid's DLL article and backfill if real.", 'eval_cost_usd': None, 'activation_fee_usd': None, 'profit_split_pct': None, 'ruleset_type': 'prop_eval', 'daily_loss_cap': None, 'weekly_loss_cap': None, 'daily_profit_goal': None, 'description': None, 'risk_per_trade_pct': 0.5, 'max_consecutive_losses': 3, 'earliest_entry_time_et': '09:30', 'latest_entry_time_et': '15:00', 'days_of_week_allowed': '["mon","tue","wed","thu","fri"]', 'daily_profit_target': 1500, 'daily_profit_lock_pct': 0.8, 'default_commission_per_side': 2.25, 'default_slippage_ticks': 1, 'daily_halt_fraction': 0.6, 'market': 'futures', 'drawdown_unit': 'usd', 'mll_lock_balance': 100100.0, 'consistency_breach_action': None, 'reference_urls': '["https://support.lucidtrading.com/en/articles/12945815-lucidflex-drawdown","https://support.lucidtrading.com/en/articles/12945808-lucidflex-scaling-plan"]'},
        {'id': 'lucidflex_50k_funded', 'name': 'LucidFlex $50k Funded', 'account_size': 50000, 'profit_target': 0, 'max_loss_eod': 2000, 'max_loss_intraday': None, 'drawdown_type': 'trailing_eod', 'consistency_pct': None, 'min_trading_days': None, 'force_flat_time_et': '16:45', 'allowed_instruments': '["MES", "MNQ", "MGC", "MCL", "MYM", "M2K"]', 'max_contracts': '{"mini_max": 2, "micro_max": 20, "scaling": {"mode": "bidirectional_band", "trigger_basis": "eod_simulated_profit", "bands": [{"profit_min": 0, "profit_max": 999, "mini": 2, "micro": 20}, {"profit_min": 1000, "profit_max": 1999, "mini": 3, "micro": 30}, {"profit_min": 2000, "profit_max": null, "mini": 4, "micro": 40}], "ceiling": {"mini": 4, "micro": 40}}}', 'platform_support': '["NinjaTrader", "Tradovate"]', 'account_tier': 'funded', 'docs_url': 'https://support.lucidtrading.com/en/articles/12945795-lucidflex-funded-account', 'notes': "Verified from docs_url on 2026-05-29 CORRECTED 2026-05-31: drawdown_type -> trailing_eod (was flat); force_flat_time_et -> 16:45 (was 15:30); eval contracts set to fixed full size (50k 4/40, 100k 6/60); funded contract scaling added. Drawdown is EOD trailing, floor max-loss distance below highest EOD close, trails up never down, locks once account clears Initial Trail Balance; EXACT LOCK VALUE UNVERIFIED (confirm at support.lucidtrading.com). Funded scaling is BIDIRECTIONAL (limits rise AND fall with EOD simulated-profit band; can drop after payouts). Microscalping flag threshold is 5 SECONDS. Auto-close 4:45pm ET, no overnight. TODO/VERIFY: sources conflict on whether 50k/100k carry a fixed DAILY LOSS LIMIT in eval + early funded (converting to a 60%-of-highest-EOD-profit LucidScale DLL above the Initial Trail Balance). max_loss_intraday left UNCHANGED -- confirm the DLL dollar amounts against Lucid's DLL article and backfill if real.", 'eval_cost_usd': None, 'activation_fee_usd': None, 'profit_split_pct': None, 'ruleset_type': 'prop_funded', 'daily_loss_cap': 2000, 'weekly_loss_cap': None, 'daily_profit_goal': None, 'description': None, 'risk_per_trade_pct': 0.5, 'max_consecutive_losses': 3, 'earliest_entry_time_et': '09:30', 'latest_entry_time_et': '15:00', 'days_of_week_allowed': '["mon","tue","wed","thu","fri"]', 'daily_profit_target': None, 'daily_profit_lock_pct': None, 'default_commission_per_side': 2.25, 'default_slippage_ticks': 1, 'daily_halt_fraction': None, 'market': 'futures', 'drawdown_unit': 'usd', 'mll_lock_balance': None, 'consistency_breach_action': None, 'reference_urls': None},
        {'id': 'lucidflex_100k_funded', 'name': 'LucidFlex $100k Funded', 'account_size': 100000, 'profit_target': 0, 'max_loss_eod': 3000, 'max_loss_intraday': None, 'drawdown_type': 'trailing_eod', 'consistency_pct': None, 'min_trading_days': None, 'force_flat_time_et': '16:45', 'allowed_instruments': '["MES", "MNQ", "MGC", "MCL", "MYM", "M2K"]', 'max_contracts': '{"mini_max": 3, "micro_max": 30, "scaling": {"mode": "bidirectional_band", "trigger_basis": "eod_simulated_profit", "bands": [{"profit_min": 0, "profit_max": 999, "mini": 3, "micro": 30}, {"profit_min": 1000, "profit_max": 1999, "mini": 4, "micro": 40}, {"profit_min": 2000, "profit_max": 2999, "mini": 5, "micro": 50}, {"profit_min": 3000, "profit_max": null, "mini": 6, "micro": 60}], "ceiling": {"mini": 6, "micro": 60}}}', 'platform_support': '["NinjaTrader", "Tradovate"]', 'account_tier': 'funded', 'docs_url': 'https://support.lucidtrading.com/en/articles/12945795-lucidflex-funded-account', 'notes': "Verified from docs_url on 2026-05-29 CORRECTED 2026-05-31: drawdown_type -> trailing_eod (was flat); force_flat_time_et -> 16:45 (was 15:30); eval contracts set to fixed full size (50k 4/40, 100k 6/60); funded contract scaling added. Drawdown is EOD trailing, floor max-loss distance below highest EOD close, trails up never down, locks once account clears Initial Trail Balance; EXACT LOCK VALUE UNVERIFIED (confirm at support.lucidtrading.com). Funded scaling is BIDIRECTIONAL (limits rise AND fall with EOD simulated-profit band; can drop after payouts). Microscalping flag threshold is 5 SECONDS. Auto-close 4:45pm ET, no overnight. TODO/VERIFY: sources conflict on whether 50k/100k carry a fixed DAILY LOSS LIMIT in eval + early funded (converting to a 60%-of-highest-EOD-profit LucidScale DLL above the Initial Trail Balance). max_loss_intraday left UNCHANGED -- confirm the DLL dollar amounts against Lucid's DLL article and backfill if real.", 'eval_cost_usd': None, 'activation_fee_usd': None, 'profit_split_pct': None, 'ruleset_type': 'prop_funded', 'daily_loss_cap': 3000, 'weekly_loss_cap': None, 'daily_profit_goal': None, 'description': None, 'risk_per_trade_pct': 0.5, 'max_consecutive_losses': 3, 'earliest_entry_time_et': '09:30', 'latest_entry_time_et': '15:00', 'days_of_week_allowed': '["mon","tue","wed","thu","fri"]', 'daily_profit_target': None, 'daily_profit_lock_pct': None, 'default_commission_per_side': 2.25, 'default_slippage_ticks': 1, 'daily_halt_fraction': None, 'market': 'futures', 'drawdown_unit': 'usd', 'mll_lock_balance': None, 'consistency_breach_action': None, 'reference_urls': None},
        {'id': 'fundednext_flex_50k_eval', 'name': 'Futures Flex $50k Challenge', 'account_size': 50000, 'profit_target': 2500, 'max_loss_eod': 1500, 'max_loss_intraday': None, 'drawdown_type': 'trailing_eod', 'consistency_pct': 40.0, 'min_trading_days': None, 'force_flat_time_et': '16:10', 'allowed_instruments': '["MES", "MNQ", "MGC", "MCL", "MYM", "M2K", "ES", "NQ", "GC", "CL", "YM", "RTY"]', 'max_contracts': '{"mini_max": 3, "micro_max": 30, "scaling": null, "mix_allowed": true, "mix_ratio_micro_per_mini": 10}', 'platform_support': '["NinjaTrader", "Tradovate"]', 'account_tier': 'eval', 'docs_url': 'https://helpfutures.fundednext.com/en/articles/14878751-what-is-fundednext-futures-flex-challenge', 'notes': 'One-time fee (base ~$134; promo code FLEX ~$69.99; reset ~$78). No activation fee to funded. DRAWDOWN: EOD trailing $1,500, locks permanently at $50,100 ($100 above start), then stops trailing. NO daily loss limit (MLL only). CONSISTENCY 40% CHALLENGE-PHASE ONLY -- UNUSUAL MECHANIC: breaching it does NOT fail the account; it RAISES the profit target instead. 40% rule mathematically forces >=3 winning days (no separate min-days rule found). CONTRACTS fixed (no scaling), 3 mini / 30 micro, mixable at 1:10; exceeding = excess-contract profit voided (penalty, not breach). Intraday only: flat by 3:10pm CT (16:10 ET, DST-adjusted), no overnight/weekend, auto-closed if left open. News trading allowed. Automated/EA/bots allowed (no latency abuse / order flooding). PROHIBITED: tight-bracket/no-slippage exploitation, grid, hedging, correlated-instrument hedging, trading within 2% of CME price limit. Platforms NinjaTrader + Tradovate. allowed_instruments = standard CME set we trade; verify exact FundedNext product list. Verified from docs_url on 2026-05-31.', 'eval_cost_usd': 134, 'activation_fee_usd': None, 'profit_split_pct': None, 'ruleset_type': 'prop_eval', 'daily_loss_cap': None, 'weekly_loss_cap': None, 'daily_profit_goal': None, 'description': None, 'risk_per_trade_pct': 0.5, 'max_consecutive_losses': 3, 'earliest_entry_time_et': '09:30', 'latest_entry_time_et': '15:00', 'days_of_week_allowed': '["mon","tue","wed","thu","fri"]', 'daily_profit_target': 1500, 'daily_profit_lock_pct': 0.8, 'default_commission_per_side': 2.25, 'default_slippage_ticks': 1, 'daily_halt_fraction': 0.6, 'market': 'futures', 'drawdown_unit': 'usd', 'mll_lock_balance': 50100.0, 'consistency_breach_action': 'raise_target', 'reference_urls': '["https://helpfutures.fundednext.com/en/articles/14878830-how-do-i-pass-fundednext-futures-flex-challenge"]'},
        {'id': 'fundednext_flex_100k_eval', 'name': 'Futures Flex $100k Challenge', 'account_size': 100000, 'profit_target': 5000, 'max_loss_eod': 2500, 'max_loss_intraday': None, 'drawdown_type': 'trailing_eod', 'consistency_pct': 40.0, 'min_trading_days': None, 'force_flat_time_et': '16:10', 'allowed_instruments': '["MES", "MNQ", "MGC", "MCL", "MYM", "M2K", "ES", "NQ", "GC", "CL", "YM", "RTY"]', 'max_contracts': '{"mini_max": 5, "micro_max": 50, "scaling": null, "mix_allowed": true, "mix_ratio_micro_per_mini": 10}', 'platform_support': '["NinjaTrader", "Tradovate"]', 'account_tier': 'eval', 'docs_url': 'https://helpfutures.fundednext.com/en/articles/14878751-what-is-fundednext-futures-flex-challenge', 'notes': 'One-time fee (base ~$250; promo ~$129.99; reset ~$145). No activation fee. DRAWDOWN: EOD trailing $2,500, locks at $100,100 ($100 above start). NO daily loss limit. CONSISTENCY 40% CHALLENGE-ONLY; breaching RAISES the target (not a fail); forces >=3 winning days. CONTRACTS fixed 5 mini / 50 micro, mixable 1:10; excess = profit-void penalty. Intraday only, flat 3:10pm CT (16:10 ET), no overnight. News allowed. Automated/EA OK (no latency abuse). PROHIBITED: tight-bracket exploitation, grid, hedging, within 2% of CME price limit. Platforms NinjaTrader + Tradovate. allowed_instruments = standard CME set; verify exact list. Verified from docs_url on 2026-05-31.', 'eval_cost_usd': 250, 'activation_fee_usd': None, 'profit_split_pct': None, 'ruleset_type': 'prop_eval', 'daily_loss_cap': None, 'weekly_loss_cap': None, 'daily_profit_goal': None, 'description': None, 'risk_per_trade_pct': 0.5, 'max_consecutive_losses': 3, 'earliest_entry_time_et': '09:30', 'latest_entry_time_et': '15:00', 'days_of_week_allowed': '["mon","tue","wed","thu","fri"]', 'daily_profit_target': 1500, 'daily_profit_lock_pct': 0.8, 'default_commission_per_side': 2.25, 'default_slippage_ticks': 1, 'daily_halt_fraction': 0.6, 'market': 'futures', 'drawdown_unit': 'usd', 'mll_lock_balance': 100100.0, 'consistency_breach_action': 'raise_target', 'reference_urls': '["https://helpfutures.fundednext.com/en/articles/14878830-how-do-i-pass-fundednext-futures-flex-challenge"]'},
        {'id': 'fundednext_flex_50k_funded', 'name': 'Futures Flex $50k Funded', 'account_size': 50000, 'profit_target': 0, 'max_loss_eod': 1500, 'max_loss_intraday': None, 'drawdown_type': 'trailing_eod', 'consistency_pct': None, 'min_trading_days': None, 'force_flat_time_et': '16:10', 'allowed_instruments': '["MES", "MNQ", "MGC", "MCL", "MYM", "M2K", "ES", "NQ", "GC", "CL", "YM", "RTY"]', 'max_contracts': '{"mini_max": 3, "micro_max": 30, "scaling": null, "mix_allowed": true, "mix_ratio_micro_per_mini": 10}', 'platform_support': '["NinjaTrader", "Tradovate"]', 'account_tier': 'funded', 'docs_url': 'https://helpfutures.fundednext.com/en/articles/14878751-what-is-fundednext-futures-flex-challenge', 'notes': 'FundedNext (funded) stage. NO consistency rule, NO daily loss limit. Reward split base 80%; 90% available only if the 90% add-on was bought at challenge purchase. DRAWDOWN: EOD trailing $1,500, locks at $50,100; first withdrawal also sets/locks the MLL. Payout requires 5 Benchmark (winning) days; withdrawal caps apply (50%-of-growth style, capped by size -- VERIFY exact amounts). Intraday only, flat 3:10pm CT (16:10 ET). Automated/EA OK (no HFT). Contracts fixed 3/30, mixable 1:10, excess = profit-void penalty. VERIFY: contract-limit policy says limits can differ by STAGE; funded-stage limit assumed same as challenge (3/30) -- confirm against the contract-limit policy doc. Verified from docs_url on 2026-05-31.', 'eval_cost_usd': None, 'activation_fee_usd': 0, 'profit_split_pct': 80.0, 'ruleset_type': 'prop_funded', 'daily_loss_cap': 1500, 'weekly_loss_cap': None, 'daily_profit_goal': None, 'description': None, 'risk_per_trade_pct': 0.5, 'max_consecutive_losses': 3, 'earliest_entry_time_et': '09:30', 'latest_entry_time_et': '15:00', 'days_of_week_allowed': '["mon","tue","wed","thu","fri"]', 'daily_profit_target': None, 'daily_profit_lock_pct': None, 'default_commission_per_side': 2.25, 'default_slippage_ticks': 1, 'daily_halt_fraction': None, 'market': 'futures', 'drawdown_unit': 'usd', 'mll_lock_balance': None, 'consistency_breach_action': None, 'reference_urls': None},
        {'id': 'fundednext_flex_100k_funded', 'name': 'Futures Flex $100k Funded', 'account_size': 100000, 'profit_target': 0, 'max_loss_eod': 2500, 'max_loss_intraday': None, 'drawdown_type': 'trailing_eod', 'consistency_pct': None, 'min_trading_days': None, 'force_flat_time_et': '16:10', 'allowed_instruments': '["MES", "MNQ", "MGC", "MCL", "MYM", "M2K", "ES", "NQ", "GC", "CL", "YM", "RTY"]', 'max_contracts': '{"mini_max": 5, "micro_max": 50, "scaling": null, "mix_allowed": true, "mix_ratio_micro_per_mini": 10}', 'platform_support': '["NinjaTrader", "Tradovate"]', 'account_tier': 'funded', 'docs_url': 'https://helpfutures.fundednext.com/en/articles/14878751-what-is-fundednext-futures-flex-challenge', 'notes': 'FundedNext (funded) stage. NO consistency rule, NO daily loss limit. Split base 80% (90% only with add-on bought at purchase). DRAWDOWN: EOD trailing $2,500, locks at $100,100; first withdrawal also locks MLL. Payout: 5 Benchmark days; withdrawal caps apply -- VERIFY amounts. Intraday only, flat 3:10pm CT (16:10 ET). Automated/EA OK (no HFT). Contracts fixed 5/50, mixable 1:10, excess = profit-void penalty. VERIFY: funded-stage contract limit assumed same as challenge (5/50) -- policy says limits can differ by stage; confirm. Verified from docs_url on 2026-05-31.', 'eval_cost_usd': None, 'activation_fee_usd': 0, 'profit_split_pct': 80.0, 'ruleset_type': 'prop_funded', 'daily_loss_cap': 2500, 'weekly_loss_cap': None, 'daily_profit_goal': None, 'description': None, 'risk_per_trade_pct': 0.5, 'max_consecutive_losses': 3, 'earliest_entry_time_et': '09:30', 'latest_entry_time_et': '15:00', 'days_of_week_allowed': '["mon","tue","wed","thu","fri"]', 'daily_profit_target': None, 'daily_profit_lock_pct': None, 'default_commission_per_side': 2.25, 'default_slippage_ticks': 1, 'daily_halt_fraction': None, 'market': 'futures', 'drawdown_unit': 'usd', 'mll_lock_balance': None, 'consistency_breach_action': None, 'reference_urls': None},
        {'id': 'tradeify_50k_eval', 'name': 'Select $50k Evaluation', 'account_size': 50000, 'profit_target': 3000, 'max_loss_eod': 2000, 'max_loss_intraday': None, 'drawdown_type': 'trailing_eod', 'consistency_pct': 40.0, 'min_trading_days': 3, 'force_flat_time_et': '16:59', 'allowed_instruments': '["MES", "MNQ", "MGC", "MCL", "MYM", "M2K", "ES", "NQ", "GC", "CL", "YM", "RTY"]', 'max_contracts': '{"mini_max": 4, "micro_max": 40, "scaling": null}', 'platform_support': '["Tradovate", "Rithmic"]', 'account_tier': 'eval', 'docs_url': 'https://help.tradeify.co/en/articles/12853921-select-evaluation-accounts', 'notes': 'One-time purchase (Tradeify 3.0). Price ~$165 / reset ~$95 UNVERIFIED (confirm at checkout). CONTRACTS: eval full day one, no scaling = 4/40. Cannot hold minis+micros at once (hedging); can switch between sessions. DRAWDOWN: EOD trailing $2,000, trails up never down, real-time enforced, NO lock during eval. No DLL during eval. 40% consistency => min 3 days. Activity rule: >50% of trades AND >50% of profit from trades held >10s. No overnight; flat 4:59pm ET (12:59 holidays). News allowed. Bots/algos OK (sole owner, no HFT). Tradovate+Rithmic day one; native NinjaTrader Elite-only. Verified 2026-05-31.', 'eval_cost_usd': 165, 'activation_fee_usd': None, 'profit_split_pct': None, 'ruleset_type': 'prop_eval', 'daily_loss_cap': None, 'weekly_loss_cap': None, 'daily_profit_goal': None, 'description': None, 'risk_per_trade_pct': 0.5, 'max_consecutive_losses': 3, 'earliest_entry_time_et': '09:30', 'latest_entry_time_et': '15:00', 'days_of_week_allowed': '["mon","tue","wed","thu","fri"]', 'daily_profit_target': 1500, 'daily_profit_lock_pct': 0.8, 'default_commission_per_side': 2.25, 'default_slippage_ticks': 1, 'daily_halt_fraction': 0.6, 'market': 'futures', 'drawdown_unit': 'usd', 'mll_lock_balance': 50100.0, 'consistency_breach_action': None, 'reference_urls': None},
        {'id': 'tradeify_100k_eval', 'name': 'Select $100k Evaluation', 'account_size': 100000, 'profit_target': 6000, 'max_loss_eod': 3000, 'max_loss_intraday': None, 'drawdown_type': 'trailing_eod', 'consistency_pct': 40.0, 'min_trading_days': 3, 'force_flat_time_et': '16:59', 'allowed_instruments': '["MES", "MNQ", "MGC", "MCL", "MYM", "M2K", "ES", "NQ", "GC", "CL", "YM", "RTY"]', 'max_contracts': '{"mini_max": 8, "micro_max": 80, "scaling": null}', 'platform_support': '["Tradovate", "Rithmic"]', 'account_tier': 'eval', 'docs_url': 'https://help.tradeify.co/en/articles/12853921-select-evaluation-accounts', 'notes': 'One-time purchase. Price ~$265 / reset ~$169 UNVERIFIED. CONTRACTS: eval full day one = 8/80, no scaling. Cannot hold minis+micros at once. DRAWDOWN: EOD trailing $3,000, trails up never down, NO lock during eval. No DLL during eval. 40% consistency, min 3 days. >10-sec activity rule. No overnight; flat 4:59pm ET. News allowed. Bots/algos OK (no HFT). Tradovate+Rithmic day one; native NinjaTrader Elite-only. Note: Select 100k drawdown ($3,000) TIGHTER than Growth 100k ($3,500). Verified 2026-05-31.', 'eval_cost_usd': 265, 'activation_fee_usd': None, 'profit_split_pct': None, 'ruleset_type': 'prop_eval', 'daily_loss_cap': None, 'weekly_loss_cap': None, 'daily_profit_goal': None, 'description': None, 'risk_per_trade_pct': 0.5, 'max_consecutive_losses': 3, 'earliest_entry_time_et': '09:30', 'latest_entry_time_et': '15:00', 'days_of_week_allowed': '["mon","tue","wed","thu","fri"]', 'daily_profit_target': 1500, 'daily_profit_lock_pct': 0.8, 'default_commission_per_side': 2.25, 'default_slippage_ticks': 1, 'daily_halt_fraction': 0.6, 'market': 'futures', 'drawdown_unit': 'usd', 'mll_lock_balance': 100100.0, 'consistency_breach_action': None, 'reference_urls': None},
        {'id': 'tradeify_50k_funded', 'name': 'Select $50k Funded (Flex)', 'account_size': 50000, 'profit_target': 0, 'max_loss_eod': 2000, 'max_loss_intraday': None, 'drawdown_type': 'trailing_eod', 'consistency_pct': None, 'min_trading_days': None, 'force_flat_time_et': '16:59', 'allowed_instruments': '["MES", "MNQ", "MGC", "MCL", "MYM", "M2K", "ES", "NQ", "GC", "CL", "YM", "RTY"]', 'max_contracts': '{"mini_max": 2, "micro_max": 20, "scaling": {"mode": "cumulative_ratchet", "trigger_basis": "eod_profit_above_start", "start": {"mini": 2, "micro": 20}, "tiers": [{"profit_trigger": 1500, "mini": 3, "micro": 30}, {"profit_trigger": 2000, "mini": 4, "micro": 40}], "ceiling": {"mini": 4, "micro": 40}}}', 'platform_support': '["Tradovate", "Rithmic"]', 'account_tier': 'funded', 'docs_url': 'https://help.tradeify.co/en/articles/12853966-select-flex-and-select-daily-payout-policies', 'notes': 'Select FLEX funded. No consistency rule, no DLL. 90/10. CONTRACTS scale CUMULATIVELY (retained once reached): start 2/20; +$1,500 -> 3/30; +$2,000 -> 4/40 (max). Tiers from Tradeify support assistant; re-confirm vs funded payout doc. Cannot hold minis+micros at once. DRAWDOWN: EOD trailing $2,000, LOCKS at $100 above start ($50,100) once EOD clears $52,100 or first payout. Payout: 5 winning days; Flex cap up to 50% of profit, max $3,000/payout. >10-sec activity rule. No overnight; flat 4:59pm ET. Verified 2026-05-31.', 'eval_cost_usd': None, 'activation_fee_usd': 0, 'profit_split_pct': 90.0, 'ruleset_type': 'prop_funded', 'daily_loss_cap': 2000, 'weekly_loss_cap': None, 'daily_profit_goal': None, 'description': None, 'risk_per_trade_pct': 0.5, 'max_consecutive_losses': 3, 'earliest_entry_time_et': '09:30', 'latest_entry_time_et': '15:00', 'days_of_week_allowed': '["mon","tue","wed","thu","fri"]', 'daily_profit_target': None, 'daily_profit_lock_pct': None, 'default_commission_per_side': 2.25, 'default_slippage_ticks': 1, 'daily_halt_fraction': None, 'market': 'futures', 'drawdown_unit': 'usd', 'mll_lock_balance': None, 'consistency_breach_action': None, 'reference_urls': None},
        {'id': 'tradeify_100k_funded', 'name': 'Select $100k Funded (Flex)', 'account_size': 100000, 'profit_target': 0, 'max_loss_eod': 3000, 'max_loss_intraday': None, 'drawdown_type': 'trailing_eod', 'consistency_pct': None, 'min_trading_days': None, 'force_flat_time_et': '16:59', 'allowed_instruments': '["MES", "MNQ", "MGC", "MCL", "MYM", "M2K", "ES", "NQ", "GC", "CL", "YM", "RTY"]', 'max_contracts': '{"mini_max": 3, "micro_max": 30, "scaling": {"mode": "cumulative_ratchet", "trigger_basis": "eod_profit_above_start", "start": {"mini": 3, "micro": 30}, "tiers": [{"profit_trigger": 1500, "mini": 4, "micro": 40}, {"profit_trigger": 2000, "mini": 5, "micro": 50}, {"profit_trigger": 3000, "mini": 8, "micro": 80}], "ceiling": {"mini": 8, "micro": 80}}}', 'platform_support': '["Tradovate", "Rithmic"]', 'account_tier': 'funded', 'docs_url': 'https://help.tradeify.co/en/articles/12853966-select-flex-and-select-daily-payout-policies', 'notes': 'Select FLEX funded. No consistency rule, no DLL. 90/10. CONTRACTS scale CUMULATIVELY: start 3/30; +$1,500 -> 4/40; +$2,000 -> 5/50; +$3,000 -> 8/80 (max). Tiers from Tradeify support assistant; re-confirm vs funded payout doc. Cannot hold minis+micros at once. DRAWDOWN: EOD trailing $3,000, LOCKS at $100 above start ($100,100) once EOD clears $103,100 or first payout. Payout: 5 winning days; Flex cap up to 50% of profit, max $4,000/payout. >10-sec activity rule. No overnight; flat 4:59pm ET. Verified 2026-05-31.', 'eval_cost_usd': None, 'activation_fee_usd': 0, 'profit_split_pct': 90.0, 'ruleset_type': 'prop_funded', 'daily_loss_cap': 3000, 'weekly_loss_cap': None, 'daily_profit_goal': None, 'description': None, 'risk_per_trade_pct': 0.5, 'max_consecutive_losses': 3, 'earliest_entry_time_et': '09:30', 'latest_entry_time_et': '15:00', 'days_of_week_allowed': '["mon","tue","wed","thu","fri"]', 'daily_profit_target': None, 'daily_profit_lock_pct': None, 'default_commission_per_side': 2.25, 'default_slippage_ticks': 1, 'daily_halt_fraction': None, 'market': 'futures', 'drawdown_unit': 'usd', 'mll_lock_balance': None, 'consistency_breach_action': None, 'reference_urls': None},
    ]
    _prop_seed_sql = (
        "INSERT INTO rulesets (" + ", ".join(_PROP_SEED_COLS) + ", created_at, updated_at) "
        "VALUES (" + ", ".join(["?"] * len(_PROP_SEED_COLS)) + ", ?, ?)"
    )
    for _prow in _PROP_SEED_ROWS:
        if not conn.execute("SELECT 1 FROM rulesets WHERE id=?", (_prow["id"],)).fetchone():
            conn.execute(_prop_seed_sql, tuple(_prow[_c] for _c in _PROP_SEED_COLS) + (now, now))

    # Apex EOD eval rows (same idempotent helper the live-DB migration uses).
    _seed_apex_eod_eval(conn, now)

    _seed_instrument_metadata(conn)


def _seed_instrument_metadata(conn: sqlite3.Connection) -> None:
    """Seed instrument_metadata with forex + futures instruments.

    Uses INSERT OR IGNORE so existing rows (including user edits) are never overwritten.
    Run on every startup — idempotent.
    """
    rows = [
        # ── Forex ────────────────────────────────────────────────────────────
        # broker_suffix is blank — user populates after checking PU Prime symbol names.
        # point_value_usd is per standard lot (100k units) where applicable; null where
        # it depends heavily on the current exchange rate (JPY pairs, NAS100).
        ("XAUUSD",  "forex", "Gold (XAU/USD)",                 0.01,    1.0,    "", "24h",     "Spread-based; point value per 0.01 move per lot"),
        ("XAGUSD",  "forex", "Silver (XAG/USD)",               0.001,   None,   "", "24h",     "Highly variable point value; update after testing"),
        ("EURUSD",  "forex", "Euro / US Dollar",               0.00001, 10.0,   "", "london",  "Majors pair; $10/pip per std lot"),
        ("GBPUSD",  "forex", "British Pound / US Dollar",      0.00001, 10.0,   "", "london",  "Majors pair; $10/pip per std lot"),
        ("GBPJPY",  "forex", "British Pound / Japanese Yen",   0.001,   None,   "", "london",  "Cross pair; pip value varies with JPY rate"),
        ("USDJPY",  "forex", "US Dollar / Japanese Yen",       0.001,   None,   "", "london",  "Majors pair; pip value varies with JPY rate"),
        ("AUDUSD",  "forex", "Australian Dollar / US Dollar",  0.00001, 10.0,   "", "london",  "Majors pair; $10/pip per std lot"),
        ("USDCAD",  "forex", "US Dollar / Canadian Dollar",    0.00001, None,   "", "newyork", "Pip value varies with CAD rate"),
        ("EURGBP",  "forex", "Euro / British Pound",           0.00001, None,   "", "london",  "Cross pair; pip value varies with GBP rate"),
        ("NAS100",  "forex", "Nasdaq 100 (Index CFD)",         0.01,    None,   "", "newyork", "Index CFD; contract size broker-specific"),
        # ── Futures ──────────────────────────────────────────────────────────
        # point_value_usd = dollar value of one full point (not tick).
        ("MES",     "futures", "Micro E-mini S&P 500",         0.25,    5.0,    "", "newyork", "$1.25/tick; $5/point"),
        ("ES",      "futures", "E-mini S&P 500",               0.25,    50.0,   "", "newyork", "$12.50/tick; $50/point"),
        ("MNQ",     "futures", "Micro E-mini Nasdaq 100",      0.25,    2.0,    "", "newyork", "$0.50/tick; $2/point"),
        ("NQ",      "futures", "E-mini Nasdaq 100",            0.25,    20.0,   "", "newyork", "$5.00/tick; $20/point"),
        ("MGC",     "futures", "Micro Gold",                   0.10,    1.0,    "", "newyork", "$0.10/tick; $1/point"),
        ("GC",      "futures", "Gold (full)",                  0.10,    10.0,   "", "newyork", "$1.00/tick; $10/point"),
        ("MCL",     "futures", "Micro Crude Oil",              0.01,    1.0,    "", "newyork", "$0.01/tick; $1/point"),
        ("CL",      "futures", "Crude Oil (full)",             0.01,    10.0,   "", "newyork", "$0.10/tick; $10/point"),
        ("MYM",     "futures", "Micro E-mini Dow",             1.0,     0.5,    "", "newyork", "$0.50/tick; $0.50/point"),
        ("YM",      "futures", "E-mini Dow",                   1.0,     5.0,    "", "newyork", "$5.00/tick; $5/point"),
        ("M2K",     "futures", "Micro E-mini Russell 2000",    0.10,    0.5,    "", "newyork", "$0.05/tick; $0.50/point"),
        ("RTY",     "futures", "E-mini Russell 2000",          0.10,    5.0,    "", "newyork", "$0.50/tick; $5/point"),
    ]
    conn.executemany(
        """INSERT OR IGNORE INTO instrument_metadata
           (symbol, market, display_name, tick_size, point_value_usd,
            broker_suffix, default_session, notes)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
        rows,
    )


# ── Strategies ────────────────────────────────────────────────────────────────

def list_strategies() -> list[dict]:
    with _connect() as conn:
        rows = conn.execute("""
            SELECT s.*, COUNT(r.run_id) AS run_count
            FROM strategies s
            LEFT JOIN backtest_runs r
              ON r.strategy_id = s.id AND r.stress_test_id IS NULL
            GROUP BY s.id
            ORDER BY s.name
        """).fetchall()
    return [_parse_json_fields(dict(r), ["default_params", "param_schema", "steps"]) for r in rows]


def get_strategy(strategy_id: str) -> Optional[dict]:
    with _connect() as conn:
        row = conn.execute("""
            SELECT s.*, COUNT(r.run_id) AS run_count
            FROM strategies s
            LEFT JOIN backtest_runs r
              ON r.strategy_id = s.id AND r.stress_test_id IS NULL
            WHERE s.id = ?
            GROUP BY s.id
        """, (strategy_id,)).fetchone()
    if not row:
        return None
    return _parse_json_fields(dict(row), ["default_params", "param_schema", "steps"])


def get_strategy_hash(strategy_id: str) -> Optional[str]:
    with _connect() as conn:
        row = conn.execute(
            "SELECT source_hash FROM strategies WHERE id = ?", (strategy_id,)
        ).fetchone()
    return row["source_hash"] if row else None


def update_strategy_description(strategy_id: str, description: Optional[str]) -> bool:
    with _connect() as conn:
        result = conn.execute(
            "UPDATE strategies SET description = ? WHERE id = ?", (description, strategy_id)
        )
    return result.rowcount > 0


def upsert_strategy(data: dict) -> None:
    with _connect() as conn:
        conn.execute("""
            INSERT INTO strategies
                (id, name, class_name, source_path, category, suggested_instrument,
                 default_params, param_schema, scanned_at, source_hash, runner, edge, steps)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(id) DO UPDATE SET
                name=excluded.name,
                class_name=excluded.class_name,
                source_path=excluded.source_path,
                category=excluded.category,
                suggested_instrument=excluded.suggested_instrument,
                default_params=excluded.default_params,
                param_schema=excluded.param_schema,
                scanned_at=excluded.scanned_at,
                source_hash=excluded.source_hash,
                runner=excluded.runner,
                edge=excluded.edge,
                steps=excluded.steps
        """, (
            data["id"], data["name"], data["class_name"], data["source_path"],
            data.get("category"), data.get("suggested_instrument"),
            json.dumps(data.get("default_params", {})),
            json.dumps(data.get("param_schema", [])),
            data["scanned_at"], data.get("source_hash"),
            data.get("runner", "ninjatrader"),
            data.get("edge"),
            json.dumps(data.get("steps", [])),
        ))


def mark_strategy_needs_compile(class_name: str) -> None:
    """Called after a source file is uploaded — marks that strategy as needing compile."""
    with _connect() as conn:
        conn.execute(
            "UPDATE strategies SET is_compiled = 0 WHERE class_name = ?", (class_name,)
        )


def mark_runner_compiled(runner: str) -> None:
    """Called after a successful compile — marks all strategies for that runner as compiled
    and stamps the compiled content hash to whatever is currently deployed (a compile builds
    the deployed source), so `needs_compile` can be judged by content, not a coarse boolean."""
    with _connect() as conn:
        conn.execute(
            "UPDATE strategies SET is_compiled = 1, "
            "compiled_source_hash = deployed_source_hash, compiled_at = ? "
            "WHERE runner = ?",
            (int(time.time()), runner),
        )


# ── Strategy version registry ───────────────────────────────────────────────
# Versions are content-addressed: a given source_hash always maps to the same
# monotonic version per strategy, so reverting to earlier content reuses its
# original version number. This is the source of truth for "what version is X".

def ensure_strategy_version(strategy_id: str, source_hash: str,
                            size_bytes: Optional[int] = None) -> int:
    """Return the version for this (strategy, content hash), creating it if new."""
    with _connect() as conn:
        row = conn.execute(
            "SELECT version FROM strategy_versions WHERE strategy_id = ? AND source_hash = ?",
            (strategy_id, source_hash),
        ).fetchone()
        if row:
            return row["version"]
        nxt = conn.execute(
            "SELECT COALESCE(MAX(version), 0) + 1 AS v FROM strategy_versions WHERE strategy_id = ?",
            (strategy_id,),
        ).fetchone()["v"]
        try:
            conn.execute(
                "INSERT INTO strategy_versions (strategy_id, version, source_hash, size_bytes, created_at) "
                "VALUES (?, ?, ?, ?, ?)",
                (strategy_id, nxt, source_hash, size_bytes, int(time.time())),
            )
            return nxt
        except sqlite3.IntegrityError:
            # Concurrent writer registered it first — re-read.
            row = conn.execute(
                "SELECT version FROM strategy_versions WHERE strategy_id = ? AND source_hash = ?",
                (strategy_id, source_hash),
            ).fetchone()
            return row["version"] if row else nxt


def version_for_hash(strategy_id: str, source_hash: Optional[str]) -> Optional[int]:
    """Resolve a stored content hash to its version number, or None if unknown."""
    if not source_hash:
        return None
    with _connect() as conn:
        row = conn.execute(
            "SELECT version FROM strategy_versions WHERE strategy_id = ? AND source_hash = ?",
            (strategy_id, source_hash),
        ).fetchone()
    return row["version"] if row else None


def list_strategy_versions(strategy_id: str) -> list[dict]:
    with _connect() as conn:
        rows = conn.execute(
            "SELECT strategy_id, version, source_hash, size_bytes, created_at "
            "FROM strategy_versions WHERE strategy_id = ? ORDER BY version DESC",
            (strategy_id,),
        ).fetchall()
    return [dict(r) for r in rows]


def set_strategy_deployed(class_name: str, source_hash: str) -> None:
    """Stamp the content hash + time deployed to the lab VPS, and flag needs-compile.
    A deploy always invalidates the compiled artifact until a fresh compile runs."""
    with _connect() as conn:
        conn.execute(
            "UPDATE strategies SET deployed_source_hash = ?, deployed_at = ?, is_compiled = 0 "
            "WHERE class_name = ?",
            (source_hash, int(time.time()), class_name),
        )


def delete_strategy(strategy_id: str) -> bool:
    with _connect() as conn:
        cur = conn.execute("DELETE FROM strategies WHERE id = ?", (strategy_id,))
    return cur.rowcount > 0


# ── Rulesets ──────────────────────────────────────────────────────────────────

_RULESET_JSON_FIELDS = ["allowed_instruments", "max_contracts", "platform_support", "days_of_week_allowed", "reference_urls"]


def list_rulesets() -> list[dict]:
    with _connect() as conn:
        rows = conn.execute("SELECT * FROM rulesets ORDER BY account_size").fetchall()
    return [_parse_json_fields(dict(r), _RULESET_JSON_FIELDS) for r in rows]


def get_ruleset(ruleset_id: str) -> Optional[dict]:
    with _connect() as conn:
        row = conn.execute("SELECT * FROM rulesets WHERE id = ?", (ruleset_id,)).fetchone()
    if not row:
        return None
    return _parse_json_fields(dict(row), _RULESET_JSON_FIELDS)


def insert_ruleset(data: dict) -> None:
    now = int(time.time())
    with _connect() as conn:
        conn.execute(
            """INSERT INTO rulesets
               (id, name, account_size, profit_target, max_loss_eod, max_loss_intraday,
                drawdown_type, consistency_pct, min_trading_days, force_flat_time_et,
                allowed_instruments, max_contracts, platform_support,
                account_tier, ruleset_type, market, drawdown_unit,
                daily_loss_cap, weekly_loss_cap,
                daily_profit_goal, description, docs_url, eval_cost_usd,
                activation_fee_usd, profit_split_pct, notes,
                risk_per_trade_pct, max_consecutive_losses,
                earliest_entry_time_et, latest_entry_time_et, days_of_week_allowed,
                daily_profit_target, daily_profit_lock_pct,
                default_commission_per_side, default_slippage_ticks,
                daily_halt_fraction,
                created_at, updated_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                data["id"], data["name"], data["account_size"], data["profit_target"],
                data["max_loss_eod"], data.get("max_loss_intraday"), data["drawdown_type"],
                data.get("consistency_pct"), data.get("min_trading_days"),
                data.get("force_flat_time_et"),
                json.dumps(data.get("allowed_instruments", [])),
                json.dumps(data.get("max_contracts", {})),
                json.dumps(data.get("platform_support", [])),
                data.get("account_tier", "eval"),
                data.get("ruleset_type", "prop_eval"),
                data.get("market", "futures"),
                data.get("drawdown_unit", "usd"),
                data.get("daily_loss_cap"), data.get("weekly_loss_cap"),
                data.get("daily_profit_goal"), data.get("description"),
                data.get("docs_url"), data.get("eval_cost_usd"),
                data.get("activation_fee_usd"), data.get("profit_split_pct"),
                data.get("notes"),
                data.get("risk_per_trade_pct"), data.get("max_consecutive_losses"),
                data.get("earliest_entry_time_et"), data.get("latest_entry_time_et"),
                json.dumps(data.get("days_of_week_allowed", [])) if data.get("days_of_week_allowed") is not None else None,
                data.get("daily_profit_target"), data.get("daily_profit_lock_pct"),
                data.get("default_commission_per_side"), data.get("default_slippage_ticks"),
                data.get("daily_halt_fraction"),
                now, now,
            ),
        )


def update_ruleset(ruleset_id: str, data: dict) -> bool:
    now = int(time.time())
    with _connect() as conn:
        cur = conn.execute(
            """UPDATE rulesets SET
               name=?, account_size=?, profit_target=?, max_loss_eod=?,
               max_loss_intraday=?, drawdown_type=?, consistency_pct=?,
               min_trading_days=?, force_flat_time_et=?, allowed_instruments=?,
               max_contracts=?, platform_support=?, account_tier=?,
               ruleset_type=?, market=?, drawdown_unit=?,
               daily_loss_cap=?, weekly_loss_cap=?,
               daily_profit_goal=?, description=?, docs_url=?,
               eval_cost_usd=?, activation_fee_usd=?, profit_split_pct=?, notes=?,
               risk_per_trade_pct=?, max_consecutive_losses=?,
               earliest_entry_time_et=?, latest_entry_time_et=?, days_of_week_allowed=?,
               daily_profit_target=?, daily_profit_lock_pct=?,
               default_commission_per_side=?, default_slippage_ticks=?,
               daily_halt_fraction=?,
               updated_at=?
               WHERE id=?""",
            (
                data["name"], data["account_size"], data["profit_target"],
                data["max_loss_eod"], data.get("max_loss_intraday"), data["drawdown_type"],
                data.get("consistency_pct"), data.get("min_trading_days"),
                data.get("force_flat_time_et"),
                json.dumps(data.get("allowed_instruments", [])),
                json.dumps(data.get("max_contracts", {})),
                json.dumps(data.get("platform_support", [])),
                data.get("account_tier", "eval"),
                data.get("ruleset_type", "prop_eval"),
                data.get("market", "futures"),
                data.get("drawdown_unit", "usd"),
                data.get("daily_loss_cap"), data.get("weekly_loss_cap"),
                data.get("daily_profit_goal"), data.get("description"),
                data.get("docs_url"), data.get("eval_cost_usd"),
                data.get("activation_fee_usd"), data.get("profit_split_pct"),
                data.get("notes"),
                data.get("risk_per_trade_pct"), data.get("max_consecutive_losses"),
                data.get("earliest_entry_time_et"), data.get("latest_entry_time_et"),
                json.dumps(data.get("days_of_week_allowed", [])) if data.get("days_of_week_allowed") is not None else None,
                data.get("daily_profit_target"), data.get("daily_profit_lock_pct"),
                data.get("default_commission_per_side"), data.get("default_slippage_ticks"),
                data.get("daily_halt_fraction"),
                now, ruleset_id,
            ),
        )
    return cur.rowcount > 0


# Fields PATCH /rulesets/{id} may touch — the personal rule set. Defense in depth:
# the router validates the body shape (PersonalRulesetPatch, extra=forbid) and the
# personal-row guard; this allowlist makes the SQL layer refuse anything else even
# if a future caller bypasses the router.
_PERSONAL_PATCH_FIELDS = frozenset({
    "account_size", "daily_loss_cap", "daily_profit_target",
    "max_drawdown_from_peak_pct", "max_consecutive_loss_days",
})


def update_ruleset_fields(ruleset_id: str, fields: dict) -> bool:
    """Surgical UPDATE of allowlisted personal rule fields only."""
    bad = set(fields) - _PERSONAL_PATCH_FIELDS
    if bad:
        raise ValueError(f"Fields not editable via PATCH: {sorted(bad)}")
    if not fields:
        return False
    # Column names come from the frozen allowlist above, never from user input.
    set_clause = ", ".join(f"{col} = ?" for col in fields)
    with _connect() as conn:
        cur = conn.execute(
            f"UPDATE rulesets SET {set_clause}, updated_at = ? WHERE id = ?",
            (*fields.values(), int(time.time()), ruleset_id),
        )
    return cur.rowcount > 0


def delete_ruleset(ruleset_id: str) -> bool:
    with _connect() as conn:
        cur = conn.execute("DELETE FROM rulesets WHERE id = ?", (ruleset_id,))
    return cur.rowcount > 0


# ── Instrument metadata ───────────────────────────────────────────────────────

def get_instrument_metadata(symbol: str) -> Optional[dict]:
    with _connect() as conn:
        row = conn.execute(
            "SELECT * FROM instrument_metadata WHERE symbol = ?", (symbol.upper(),)
        ).fetchone()
    return dict(row) if row else None


# ── Backtest runs ─────────────────────────────────────────────────────────────

def list_runs(
    strategy_id: Optional[str] = None,
    ruleset_id: Optional[str] = None,
    status: Optional[str] = None,
) -> list[dict]:
    base_clauses: list[str] = []
    params: list[Any] = []

    if ruleset_id:
        sql = """
            SELECT r.*, s.name AS strategy_name
            FROM backtest_runs r
            JOIN strategies s ON s.id = r.strategy_id
            JOIN evaluations e ON e.run_id = r.run_id AND e.ruleset_id = ?
        """
        params.append(ruleset_id)
    else:
        sql = """
            SELECT r.*, s.name AS strategy_name
            FROM backtest_runs r
            JOIN strategies s ON s.id = r.strategy_id
        """

    if strategy_id:
        base_clauses.append("r.strategy_id = ?")
        params.append(strategy_id)
    if status == "failed":
        base_clauses.append("r.status LIKE 'failed_%'")
    elif status:
        base_clauses.append("r.status = ?")
        params.append(status)

    base_clauses.append("r.stress_test_id IS NULL")

    sql += " WHERE " + " AND ".join(base_clauses)
    sql += " ORDER BY r.created_at DESC"

    with _connect() as conn:
        rows = conn.execute(sql, params).fetchall()
    return [_parse_json_fields(dict(r), ["params"]) for r in rows]


def get_run(run_id: str) -> Optional[dict]:
    with _connect() as conn:
        row = conn.execute("""
            SELECT r.*, s.runner, s.name AS strategy_name
            FROM backtest_runs r
            JOIN strategies s ON s.id = r.strategy_id
            WHERE r.run_id = ?
        """, (run_id,)).fetchone()
    if not row:
        return None
    return _parse_json_fields(dict(row), ["params", "evaluate_firms"])


def insert_run(data: dict) -> None:
    with _connect() as conn:
        conn.execute("""
            INSERT INTO backtest_runs
                (run_id, strategy_id, instrument, params, bar_type, bar_value,
                 start_date, end_date, commission_per_side, slippage_ticks,
                 status, created_at, started_at, evaluate_firms, runner, optimization_id, source_run_id)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            data["run_id"], data["strategy_id"], data["instrument"],
            json.dumps(data["params"]), data["bar_type"], data["bar_value"],
            data["start_date"], data["end_date"],
            data["commission_per_side"], data["slippage_ticks"],
            data["status"], data["created_at"], data.get("started_at", data["created_at"]),
            json.dumps(data.get("evaluate_rulesets") or data.get("evaluate_firms") or []),
            data.get("runner", "ninjatrader"),
            data.get("optimization_id"),
            data.get("source_run_id"),
        ))


def update_run_chart_paths(run_id: str, paths: dict) -> None:
    with _connect() as conn:
        conn.execute(
            "UPDATE backtest_runs SET equity_curve_path=?, daily_pnl_path=? WHERE run_id=?",
            (paths.get("equity_curve"), paths.get("daily_pnl"), run_id),
        )


def update_run_status(run_id: str, status: str, error_message: Optional[str] = None) -> None:
    now = int(time.time())
    with _connect() as conn:
        if status.startswith("failed"):
            conn.execute(
                "UPDATE backtest_runs SET status=?, error_message=?, completed_at=? WHERE run_id=?",
                (status, error_message, now, run_id),
            )
        else:
            conn.execute(
                "UPDATE backtest_runs SET status=?, error_message=? WHERE run_id=?",
                (status, error_message, run_id),
            )


def update_run_complete(run_id: str, kpis: dict, file_paths: dict) -> None:
    now = int(time.time())
    with _connect() as conn:
        conn.execute("""
            UPDATE backtest_runs SET
                status='complete', completed_at=?,
                net_pnl=?, max_drawdown=?, profit_factor=?, win_rate=?,
                win_count=?, trade_count=?, sharpe=?, sortino=?, cagr=?,
                avg_win=?, avg_loss=?, avg_trade_duration_min=?,
                worst_day_pnl=?, worst_losing_streak=?,
                platform_sharpe=?, sharpe_low_sample=?, profit_concentration_pct=?,
                equity_curve_path=?, trades_path=?, daily_pnl_path=?
            WHERE run_id=?
        """, (
            now,
            kpis.get("net_pnl"), kpis.get("max_drawdown"), kpis.get("profit_factor"),
            kpis.get("win_rate"), kpis.get("win_count"), kpis.get("trade_count"),
            kpis.get("sharpe"), kpis.get("sortino"), kpis.get("cagr"),
            kpis.get("avg_win"), kpis.get("avg_loss"), kpis.get("avg_trade_duration_min"),
            kpis.get("worst_day_pnl"), kpis.get("worst_losing_streak"),
            kpis.get("platform_sharpe"),
            int(kpis["sharpe_low_sample"]) if kpis.get("sharpe_low_sample") is not None else None,
            kpis.get("profit_concentration_pct"),
            file_paths.get("equity_curve"), file_paths.get("trades"),
            file_paths.get("daily_pnl"), run_id,
        ))


def _purge_stress_tests_for_runs(conn, run_ids: list[str]) -> list[str]:
    """Delete any stress tests attached to the given runs, plus each test's child runs/evals.

    stress_tests.run_id is a FOREIGN KEY into backtest_runs, so a run that has a stress test
    cannot be deleted until that test (and its walk-forward/sensitivity child runs) is gone —
    otherwise the DELETE raises IntegrityError. A stress test's child runs never carry their own
    stress test (auto-trigger is parent-only), so a single level of cascade is sufficient.

    Returns the run_ids of the deleted stress-test child runs so the caller can clean up their
    on-disk report directories.
    """
    if not run_ids:
        return []
    ph = ",".join("?" * len(run_ids))
    st_ids = [
        r["stress_test_id"] for r in conn.execute(
            f"SELECT stress_test_id FROM stress_tests WHERE run_id IN ({ph})", run_ids
        ).fetchall()
    ]
    deleted_child_ids: list[str] = []
    for st_id in st_ids:
        child_ids = [
            r["run_id"] for r in conn.execute(
                "SELECT run_id FROM backtest_runs WHERE stress_test_id = ?", (st_id,)
            ).fetchall()
        ]
        if child_ids:
            cph = ",".join("?" * len(child_ids))
            conn.execute(f"DELETE FROM evaluations WHERE run_id IN ({cph})", child_ids)
            conn.execute(f"DELETE FROM backtest_runs WHERE run_id IN ({cph})", child_ids)
            deleted_child_ids.extend(child_ids)
        conn.execute("DELETE FROM stress_tests WHERE stress_test_id = ?", (st_id,))
    return deleted_child_ids


def delete_run(run_id: str) -> list[str]:
    """Delete a run and everything that cascades from it.

    Returns the run_ids of every backtest_run actually deleted (the target plus any
    optimization/sweep/stress-test child runs), so the caller can remove their on-disk report
    directories. An empty list means the run did not exist (nothing was deleted).
    """
    deleted: list[str] = []
    with _connect() as conn:
        # Cascade: delete associated optimizations (and their child runs/evals)
        opt_ids = [
            r["optimization_id"] for r in conn.execute(
                "SELECT optimization_id FROM optimizations WHERE source_run_id = ?", (run_id,)
            ).fetchall()
        ]
        for oid in opt_ids:
            child_ids = [
                r["run_id"] for r in conn.execute(
                    "SELECT run_id FROM backtest_runs WHERE optimization_id = ?", (oid,)
                ).fetchall()
            ]
            if child_ids:
                # A winner backtest among these can carry its own stress test — purge first.
                deleted.extend(_purge_stress_tests_for_runs(conn, child_ids))
                ph = ",".join("?" * len(child_ids))
                conn.execute(f"DELETE FROM evaluations WHERE run_id IN ({ph})", child_ids)
                conn.execute(f"DELETE FROM backtest_runs WHERE run_id IN ({ph})", child_ids)
                deleted.extend(child_ids)
            conn.execute("DELETE FROM optimizations WHERE optimization_id = ?", (oid,))

        # Cascade: delete associated sweeps (runs where source_run_id = this run)
        sweep_child_ids = [
            r["run_id"] for r in conn.execute(
                "SELECT run_id FROM backtest_runs WHERE source_run_id = ?", (run_id,)
            ).fetchall()
        ]
        if sweep_child_ids:
            deleted.extend(_purge_stress_tests_for_runs(conn, sweep_child_ids))
            ph = ",".join("?" * len(sweep_child_ids))
            conn.execute(f"DELETE FROM evaluations WHERE run_id IN ({ph})", sweep_child_ids)
            conn.execute(f"DELETE FROM backtest_runs WHERE run_id IN ({ph})", sweep_child_ids)
            deleted.extend(sweep_child_ids)

        # Delete the run itself (and any stress test attached to it)
        deleted.extend(_purge_stress_tests_for_runs(conn, [run_id]))
        conn.execute("DELETE FROM evaluations WHERE run_id = ?", (run_id,))
        cur = conn.execute("DELETE FROM backtest_runs WHERE run_id = ?", (run_id,))
        if cur.rowcount > 0:
            deleted.append(run_id)
    return deleted


def delete_optimization(optimization_id: str) -> bool:
    with _connect() as conn:
        child_ids = [
            r["run_id"] for r in conn.execute(
                "SELECT run_id FROM backtest_runs WHERE optimization_id = ?", (optimization_id,)
            ).fetchall()
        ]
        if child_ids:
            placeholders = ",".join("?" * len(child_ids))
            conn.execute(f"DELETE FROM evaluations WHERE run_id IN ({placeholders})", child_ids)
            conn.execute(f"DELETE FROM backtest_runs WHERE run_id IN ({placeholders})", child_ids)
        cur = conn.execute(
            "DELETE FROM optimizations WHERE optimization_id = ?", (optimization_id,)
        )
    return cur.rowcount > 0, child_ids


def get_run_verdict_summary(run_id: str) -> list[dict]:
    with _connect() as conn:
        rows = conn.execute(
            "SELECT ruleset_id, verdict, notes FROM evaluations WHERE run_id = ?", (run_id,)
        ).fetchall()
    return [dict(r) for r in rows]


# ── Evaluations ───────────────────────────────────────────────────────────────

def get_evaluations(run_id: str) -> list[dict]:
    with _connect() as conn:
        rows = conn.execute("""
            SELECT e.*,
                   rs.name            AS ruleset_name,
                   rs.ruleset_type    AS ruleset_type,
                   rs.max_loss_eod    AS firm_max_loss_eod,
                   rs.profit_target   AS firm_profit_target,
                   rs.consistency_pct AS firm_consistency_pct,
                   rs.daily_loss_cap              AS personal_daily_loss_cap,
                   rs.max_drawdown_from_peak_pct  AS personal_max_drawdown_from_peak_pct,
                   rs.max_consecutive_loss_days   AS personal_max_consecutive_loss_days
            FROM evaluations e
            JOIN rulesets rs ON rs.id = e.ruleset_id
            WHERE e.run_id = ?
        """, (run_id,)).fetchall()
    return [dict(r) for r in rows]


def insert_evaluation(data: dict) -> None:
    now = int(time.time())
    with _connect() as conn:
        conn.execute("""
            INSERT OR REPLACE INTO evaluations
                (eval_id, run_id, ruleset_id, verdict, drawdown_pass, target_pass,
                 consistency_pass, simulated_eval_days, breach_count,
                 largest_day_share_pct, adjusted_profit_target, contract_cap_status,
                 mll_final_floor, mll_highest_eod_balance,
                 mll_breach_day, mll_min_floor_distance, notes, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            data["eval_id"], data["run_id"], data["ruleset_id"],
            data["verdict"],
            int(data["drawdown_pass"]), int(data["target_pass"]),
            int(data["consistency_pass"]) if data.get("consistency_pass") is not None else None,
            data.get("simulated_eval_days"), data["breach_count"],
            data.get("largest_day_share_pct"), data.get("adjusted_profit_target"),
            data.get("contract_cap_status"),
            data.get("mll_final_floor"), data.get("mll_highest_eod_balance"),
            data.get("mll_breach_day"), data.get("mll_min_floor_distance"),
            data.get("notes"),
            now,
        ))


def update_run_worthiness(run_id: str, tier: str, reason: Optional[str], ruleset_id: str) -> None:
    with _connect() as conn:
        conn.execute(
            """UPDATE backtest_runs
               SET worthiness_tier=?, worthiness_reason=?, worthiness_computed_against_firm=?
               WHERE run_id=?""",
            (tier, reason, ruleset_id, run_id),
        )


# ── Sweeps ────────────────────────────────────────────────────────────────────

def list_sweep_runs(sweep_id: str) -> list[dict]:
    with _connect() as conn:
        rows = conn.execute("""
            SELECT r.*, s.name AS strategy_name
            FROM backtest_runs r
            JOIN strategies s ON s.id = r.strategy_id
            WHERE r.sweep_id = ?
            ORDER BY r.created_at ASC
        """, (sweep_id,)).fetchall()
    return [_parse_json_fields(dict(r), ["params"]) for r in rows]


def list_sweeps(strategy_id: Optional[str] = None) -> list[dict]:
    where = "WHERE r.sweep_id IS NOT NULL"
    params: list = []
    if strategy_id:
        where += " AND r.strategy_id = ?"
        params.append(strategy_id)
    with _connect() as conn:
        rows = conn.execute(f"""
            SELECT
                r.sweep_id,
                r.strategy_id,
                COALESCE(s.name, r.strategy_id) AS strategy_name,
                r.start_date,
                r.end_date,
                MIN(r.created_at) AS created_at,
                MIN(r.source_run_id) AS source_run_id,
                COUNT(*)          AS total_instruments,
                SUM(CASE WHEN r.status = 'complete'       THEN 1 ELSE 0 END) AS completed_instruments,
                SUM(CASE WHEN r.status LIKE 'failed%'     THEN 1 ELSE 0 END) AS failed_instruments,
                CASE
                    WHEN SUM(CASE WHEN r.status = 'running'      THEN 1 ELSE 0 END) > 0 THEN 'running'
                    WHEN COUNT(*) = SUM(CASE WHEN r.status = 'complete'    THEN 1 ELSE 0 END) THEN 'complete'
                    WHEN COUNT(*) = SUM(CASE WHEN r.status LIKE 'failed%'  THEN 1 ELSE 0 END) THEN 'failed'
                    ELSE 'partial'
                END AS status,
                CASE MIN(CASE
                    WHEN r.worthiness_tier = 'TIER_1_STRESS_TEST' THEN 1
                    WHEN r.worthiness_tier = 'TIER_2_OPTIMIZE'    THEN 2
                    WHEN r.worthiness_tier = 'TIER_3_DISCARD'     THEN 3
                    ELSE NULL
                END)
                    WHEN 1 THEN 'TIER_1_STRESS_TEST'
                    WHEN 2 THEN 'TIER_2_OPTIMIZE'
                    WHEN 3 THEN 'TIER_3_DISCARD'
                    ELSE NULL
                END AS best_worthiness,
                (SELECT GROUP_CONCAT(DISTINCT e.ruleset_id)
                 FROM evaluations e
                 JOIN backtest_runs br2 ON br2.run_id = e.run_id
                 WHERE br2.sweep_id = r.sweep_id) AS ruleset_ids_csv
            FROM backtest_runs r
            LEFT JOIN strategies s ON s.id = r.strategy_id
            {where}
            GROUP BY r.sweep_id
            ORDER BY created_at DESC
        """, params).fetchall()
    result = []
    for r in rows:
        d = dict(r)
        d['ruleset_ids'] = [f for f in (d.pop('ruleset_ids_csv') or '').split(',') if f]
        result.append(d)
    return result


def delete_sweep(sweep_id: str) -> tuple[bool, list[str]]:
    with _connect() as conn:
        child_ids = [
            r["run_id"] for r in conn.execute(
                "SELECT run_id FROM backtest_runs WHERE sweep_id = ?", (sweep_id,)
            ).fetchall()
        ]
        if child_ids:
            placeholders = ",".join("?" * len(child_ids))
            conn.execute(f"DELETE FROM evaluations WHERE run_id IN ({placeholders})", child_ids)
            cur = conn.execute(f"DELETE FROM backtest_runs WHERE run_id IN ({placeholders})", child_ids)
        else:
            cur = conn.execute("SELECT 1 WHERE 0")
    return len(child_ids) > 0, child_ids


def has_running_job(runner: str) -> bool:
    """Canonical platform-scoped lock check. One physical terminal per platform
    (one NT8 Strategy Analyzer, one MT5 Strategy Tester), so a platform runs at most
    one job — backtest, sweep, or optimization — at a time. The two platforms are
    fully independent: an MT5 job never blocks an NT8 job and vice versa.

    `runner` is 'mt5' or anything else (treated as NT8 / 'ninjatrader')."""
    return has_running_mt5_job() if runner == "mt5" else has_running_nt8_job()


def has_running_nt8_job() -> bool:
    """True if any NT8 job (backtest, sweep, or optimization) is currently running."""
    with _connect() as conn:
        run_count = conn.execute(
            "SELECT COUNT(*) FROM backtest_runs WHERE status = 'running' AND COALESCE(runner, 'ninjatrader') != 'mt5'",
        ).fetchone()[0]
        opt_count = conn.execute("""
            SELECT COUNT(*) FROM optimizations o
            LEFT JOIN strategies s ON s.id = o.strategy_id
            WHERE o.status = 'running' AND COALESCE(s.runner, 'ninjatrader') != 'mt5'
        """).fetchone()[0]
    return (run_count + opt_count) > 0


def has_running_mt5_job() -> bool:
    """True if any MT5 job (backtest or optimization) is currently running."""
    with _connect() as conn:
        run_count = conn.execute(
            "SELECT COUNT(*) FROM backtest_runs WHERE status = 'running' AND runner = 'mt5'",
        ).fetchone()[0]
        opt_count = conn.execute("""
            SELECT COUNT(*) FROM optimizations o
            LEFT JOIN strategies s ON s.id = o.strategy_id
            WHERE o.status = 'running' AND s.runner = 'mt5'
        """).fetchone()[0]
    return (run_count + opt_count) > 0


def delete_run_evaluations(run_id: str) -> None:
    with _connect() as conn:
        conn.execute("DELETE FROM evaluations WHERE run_id = ?", (run_id,))


def get_running_job() -> dict:
    """Returns info about any running NT8 and MT5 jobs separately."""
    result = {"nt8": {"running": False}, "mt5": {"running": False}}
    with _connect() as conn:
        # NT8 standalone backtest
        row = conn.execute("""
            SELECT 'backtest' AS job_type, r.run_id AS job_id,
                   COALESCE(s.name, r.strategy_id) || ' on ' || r.instrument AS description
            FROM backtest_runs r
            LEFT JOIN strategies s ON s.id = r.strategy_id
            WHERE r.status = 'running' AND r.sweep_id IS NULL AND r.optimization_id IS NULL
              AND COALESCE(r.runner, 'ninjatrader') != 'mt5'
            LIMIT 1
        """).fetchone()
        if row:
            result["nt8"] = {"running": True, **dict(row)}

        # MT5 standalone backtest
        row = conn.execute("""
            SELECT 'backtest' AS job_type, r.run_id AS job_id,
                   COALESCE(s.name, r.strategy_id) || ' on ' || r.instrument AS description
            FROM backtest_runs r
            LEFT JOIN strategies s ON s.id = r.strategy_id
            WHERE r.status = 'running' AND r.runner = 'mt5'
            LIMIT 1
        """).fetchone()
        if row:
            result["mt5"] = {"running": True, **dict(row)}

        # NT8 sweep
        if not result["nt8"]["running"]:
            row = conn.execute("""
                SELECT 'sweep' AS job_type, r.sweep_id AS job_id,
                       COALESCE(s.name, r.strategy_id) || ' sweep' AS description
                FROM backtest_runs r
                LEFT JOIN strategies s ON s.id = r.strategy_id
                WHERE r.status = 'running' AND r.sweep_id IS NOT NULL
                  AND COALESCE(r.runner, 'ninjatrader') != 'mt5'
                LIMIT 1
            """).fetchone()
            if row:
                result["nt8"] = {"running": True, **dict(row)}

        # MT5 sweep
        if not result["mt5"]["running"]:
            row = conn.execute("""
                SELECT 'sweep' AS job_type, r.sweep_id AS job_id,
                       COALESCE(s.name, r.strategy_id) || ' sweep' AS description
                FROM backtest_runs r
                LEFT JOIN strategies s ON s.id = r.strategy_id
                WHERE r.status = 'running' AND r.sweep_id IS NOT NULL
                  AND r.runner = 'mt5'
                LIMIT 1
            """).fetchone()
            if row:
                result["mt5"] = {"running": True, **dict(row)}

        # NT8 optimization
        if not result["nt8"]["running"]:
            row = conn.execute("""
                SELECT 'optimization' AS job_type, o.optimization_id AS job_id,
                       COALESCE(s.name, o.strategy_id) || ' optimization on ' || o.instrument
                       || ' (' || o.completed_runs || '/' || o.estimated_runs || ')' AS description
                FROM optimizations o
                LEFT JOIN strategies s ON s.id = o.strategy_id
                WHERE o.status = 'running' AND COALESCE(s.runner, 'ninjatrader') != 'mt5'
                LIMIT 1
            """).fetchone()
            if row:
                result["nt8"] = {"running": True, **dict(row)}

        # MT5 optimization
        if not result["mt5"]["running"]:
            row = conn.execute("""
                SELECT 'optimization' AS job_type, o.optimization_id AS job_id,
                       COALESCE(s.name, o.strategy_id) || ' optimization on ' || o.instrument
                       || ' (' || o.completed_runs || '/' || o.estimated_runs || ')' AS description
                FROM optimizations o
                LEFT JOIN strategies s ON s.id = o.strategy_id
                WHERE o.status = 'running' AND s.runner = 'mt5'
                LIMIT 1
            """).fetchone()
            if row:
                result["mt5"] = {"running": True, **dict(row)}

    return result


def insert_run_sweep(data: dict) -> None:
    with _connect() as conn:
        conn.execute("""
            INSERT INTO backtest_runs
                (run_id, strategy_id, instrument, params, bar_type, bar_value,
                 start_date, end_date, commission_per_side, slippage_ticks,
                 status, created_at, started_at, sweep_id, source_run_id, runner)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            data["run_id"], data["strategy_id"], data["instrument"],
            json.dumps(data["params"]), data["bar_type"], data["bar_value"],
            data["start_date"], data["end_date"],
            data["commission_per_side"], data["slippage_ticks"],
            data["status"], data["created_at"], data.get("started_at", data["created_at"]),
            data["sweep_id"],
            data.get("source_run_id"), data.get("runner", "ninjatrader"),
        ))


# ── Optimizations ─────────────────────────────────────────────────────────────

def insert_optimization(data: dict) -> None:
    now = int(time.time())
    with _connect() as conn:
        conn.execute("""
            INSERT INTO optimizations
                (optimization_id, strategy_id, instrument, start_date, end_date,
                 commission_per_side, slippage_ticks, ruleset_id, mode, search_method,
                 param_grid, status, estimated_runs, completed_runs, created_at,
                 source_run_id, regime_filter, bar_type, bar_value)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 0, ?, ?, ?, ?, ?)
        """, (
            data["optimization_id"], data["strategy_id"], data["instrument"],
            data["start_date"], data["end_date"],
            data["commission_per_side"], data["slippage_ticks"],
            data["ruleset_id"], data["mode"], data["search_method"],
            json.dumps(data["param_grid"]), data["status"], data["estimated_runs"],
            now, data.get("source_run_id"), data.get("regime_filter"),
            data.get("bar_type", "Minute"), data.get("bar_value", 5),
        ))


def get_optimization(optimization_id: str) -> Optional[dict]:
    with _connect() as conn:
        row = conn.execute(
            "SELECT * FROM optimizations WHERE optimization_id = ?", (optimization_id,)
        ).fetchone()
    if not row:
        return None
    return _parse_json_fields(dict(row), ["param_grid"])


def list_optimizations(strategy_id: Optional[str] = None) -> list[dict]:
    sql = "SELECT * FROM optimizations"
    params: list[Any] = []
    if strategy_id:
        sql += " WHERE strategy_id = ?"
        params.append(strategy_id)
    sql += " ORDER BY created_at DESC"
    with _connect() as conn:
        rows = conn.execute(sql, params).fetchall()
    return [_parse_json_fields(dict(r), ["param_grid"]) for r in rows]


def increment_optimization_completed(optimization_id: str) -> None:
    with _connect() as conn:
        conn.execute(
            "UPDATE optimizations SET completed_runs = completed_runs + 1 WHERE optimization_id = ?",
            (optimization_id,),
        )


def update_optimization_estimated_runs(optimization_id: str, n: int) -> None:
    with _connect() as conn:
        conn.execute(
            "UPDATE optimizations SET estimated_runs = ? WHERE optimization_id = ?",
            (n, optimization_id),
        )


def set_optimization_completed_runs(optimization_id: str, completed: int) -> None:
    with _connect() as conn:
        conn.execute(
            "UPDATE optimizations SET completed_runs = ? WHERE optimization_id = ?",
            (completed, optimization_id),
        )


def update_optimization_grid_sensitivity(optimization_id: str, score: float, summary: dict) -> None:
    with _connect() as conn:
        conn.execute(
            "UPDATE optimizations SET grid_sensitivity_score=?, grid_sensitivity_summary=? WHERE optimization_id=?",
            (score, json.dumps(summary), optimization_id),
        )


def complete_optimization(optimization_id: str, best_run_id: Optional[str]) -> None:
    now = int(time.time())
    with _connect() as conn:
        conn.execute(
            "UPDATE optimizations SET status='complete', best_run_id=?, completed_at=? WHERE optimization_id=?",
            (best_run_id, now, optimization_id),
        )


def fail_optimization(optimization_id: str, error: str) -> None:
    with _connect() as conn:
        conn.execute(
            "UPDATE optimizations SET status=? WHERE optimization_id=?",
            (f"failed: {error[:200]}", optimization_id),
        )


def cancel_sweep_runs(sweep_id: str) -> None:
    with _connect() as conn:
        conn.execute(
            "UPDATE backtest_runs SET status='failed_cancelled', error_message='Sweep cancelled' "
            "WHERE sweep_id=? AND status IN ('running', 'pending')",
            (sweep_id,),
        )


def reset_optimization_for_rerun(optimization_id: str) -> list[str]:
    """Delete all child runs and reset the optimization row to running. Returns deleted run_ids."""
    with _connect() as conn:
        run_ids = [r["run_id"] for r in conn.execute(
            "SELECT run_id FROM backtest_runs WHERE optimization_id=?",
            (optimization_id,),
        ).fetchall()]
        conn.execute("DELETE FROM backtest_runs WHERE optimization_id=?", (optimization_id,))
        conn.execute(
            """UPDATE optimizations
               SET status='running', completed_runs=0, completed_at=NULL, best_run_id=NULL
               WHERE optimization_id=?""",
            (optimization_id,),
        )
    return run_ids


def cancel_optimization(optimization_id: str) -> None:
    now = int(time.time())
    with _connect() as conn:
        conn.execute(
            "UPDATE optimizations SET status='failed_cancelled', completed_at=? WHERE optimization_id=?",
            (now, optimization_id),
        )
        conn.execute(
            "UPDATE backtest_runs SET status='failed_cancelled', error_message='Optimization cancelled' "
            "WHERE optimization_id=? AND status IN ('running', 'pending')",
            (optimization_id,),
        )


def reset_run_for_retry(run_id: str) -> None:
    # started_at moves to now so Duration counts only this fresh attempt, not back to the
    # original kickoff (created_at stays put — it still anchors list order + "first created").
    now = int(time.time())
    with _connect() as conn:
        conn.execute(
            "UPDATE backtest_runs SET status='running', error_message=NULL, completed_at=NULL, started_at=? WHERE run_id=?",
            (now, run_id),
        )


def decrement_optimization_completed(optimization_id: str, count: int, set_running: bool = True) -> None:
    if set_running:
        sql = "UPDATE optimizations SET completed_runs = MAX(0, completed_runs - ?), status='running', completed_at=NULL WHERE optimization_id=?"
    else:
        sql = "UPDATE optimizations SET completed_runs = MAX(0, completed_runs - ?) WHERE optimization_id=?"
    with _connect() as conn:
        conn.execute(sql, (count, optimization_id))


def list_optimization_failed_runs(optimization_id: str) -> list[dict]:
    with _connect() as conn:
        rows = conn.execute(
            "SELECT r.*, s.name AS strategy_name FROM backtest_runs r "
            "JOIN strategies s ON s.id = r.strategy_id "
            "WHERE r.optimization_id=? AND r.status LIKE 'failed%'",
            (optimization_id,),
        ).fetchall()
    return [_parse_json_fields(dict(r), ["params"]) for r in rows]


def list_sweep_failed_runs(sweep_id: str) -> list[dict]:
    with _connect() as conn:
        rows = conn.execute(
            "SELECT r.*, s.name AS strategy_name FROM backtest_runs r "
            "JOIN strategies s ON s.id = r.strategy_id "
            "WHERE r.sweep_id=? AND r.status LIKE 'failed%'",
            (sweep_id,),
        ).fetchall()
    return [_parse_json_fields(dict(r), ["params"]) for r in rows]


def insert_run_optimization(data: dict) -> None:
    with _connect() as conn:
        conn.execute("""
            INSERT INTO backtest_runs
                (run_id, strategy_id, instrument, params, bar_type, bar_value,
                 start_date, end_date, commission_per_side, slippage_ticks,
                 status, created_at, started_at, optimization_id, runner)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            data["run_id"], data["strategy_id"], data["instrument"],
            json.dumps(data["params"]), data["bar_type"], data["bar_value"],
            data["start_date"], data["end_date"],
            data["commission_per_side"], data["slippage_ticks"],
            data["status"], data["created_at"], data.get("started_at", data["created_at"]),
            data["optimization_id"],
            data.get("runner", "ninjatrader"),
        ))


def list_optimization_runs(optimization_id: str) -> list[dict]:
    with _connect() as conn:
        rows = conn.execute("""
            SELECT r.*, s.name AS strategy_name
            FROM backtest_runs r
            JOIN strategies s ON s.id = r.strategy_id
            WHERE r.optimization_id = ?
            ORDER BY r.created_at ASC
        """, (optimization_id,)).fetchall()
    return [_parse_json_fields(dict(r), ["params"]) for r in rows]


# ── Stress Tests ──────────────────────────────────────────────────────────────

def insert_stress_test(data: dict) -> None:
    with _connect() as conn:
        conn.execute("""
            INSERT INTO stress_tests
                (stress_test_id, run_id, ruleset_id, status, created_at,
                 num_simulations, num_bootstrap, walk_forward_windows)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            data["stress_test_id"], data["run_id"], data.get("ruleset_id"),
            data["status"], data["created_at"],
            data.get("num_simulations", 10_000),
            data.get("num_bootstrap", 1_000),
            data.get("walk_forward_windows", 5),
        ))


def get_stress_test(stress_test_id: str) -> Optional[dict]:
    with _connect() as conn:
        row = conn.execute(
            "SELECT * FROM stress_tests WHERE stress_test_id = ?", (stress_test_id,)
        ).fetchone()
    if not row:
        return None
    return _parse_json_fields(dict(row), ["walk_forward_summary", "sensitivity_summary", "grade_reasons"])


def list_stress_tests(run_id: Optional[str] = None, grade: Optional[str] = None) -> list[dict]:
    clauses, params = [], []
    if run_id:
        clauses.append("st.run_id = ?"); params.append(run_id)
    if grade:
        clauses.append("st.grade = ?"); params.append(grade)
    where = ("WHERE " + " AND ".join(clauses)) if clauses else ""
    with _connect() as conn:
        rows = conn.execute(f"""
            SELECT st.*, r.strategy_id, r.instrument,
                   COALESCE(s.name, r.strategy_id) AS strategy_name
            FROM stress_tests st
            JOIN backtest_runs r ON r.run_id = st.run_id
            LEFT JOIN strategies s ON s.id = r.strategy_id
            {where}
            ORDER BY st.created_at DESC
        """, params).fetchall()
    return [_parse_json_fields(dict(r), ["walk_forward_summary", "sensitivity_summary", "grade_reasons"]) for r in rows]


_GRADE_ORDER = ['A', 'B', 'C', 'D', 'F']

def best_grades_by_strategy() -> dict:
    """Returns {strategy_id: {grade, stress_test_id}} for the best completed grade per strategy."""
    with _connect() as conn:
        rows = conn.execute("""
            SELECT r.strategy_id, st.grade, st.stress_test_id
            FROM stress_tests st
            JOIN backtest_runs r ON r.run_id = st.run_id
            WHERE st.grade IS NOT NULL
            ORDER BY st.created_at DESC
        """).fetchall()
    result: dict = {}
    for row in rows:
        sid, g, stid = row["strategy_id"], row["grade"], row["stress_test_id"]
        if sid not in result or _GRADE_ORDER.index(g) < _GRADE_ORDER.index(result[sid]["grade"]):
            result[sid] = {"grade": g, "stress_test_id": stid}
    return result


def reset_stale_stress_tests() -> int:
    """Mark any in-progress stress tests and their child runs as failed_crashed.
    Called on startup to recover from backend restarts mid-run."""
    now = int(time.time())
    with _connect() as conn:
        stale = conn.execute(
            "SELECT stress_test_id FROM stress_tests WHERE status LIKE 'running%'"
        ).fetchall()
        if not stale:
            return 0
        ids = [r["stress_test_id"] for r in stale]
        ph  = ",".join("?" * len(ids))
        conn.execute(
            f"UPDATE backtest_runs SET status='failed_timeout', error_message='Backend restarted mid-run' "
            f"WHERE stress_test_id IN ({ph}) AND status = 'running'",
            ids,
        )
        conn.execute(
            f"UPDATE stress_tests SET status='failed_crashed', error_message='Backend restarted mid-run', completed_at=? "
            f"WHERE stress_test_id IN ({ph})",
            [now] + ids,
        )
    return len(ids)


def reset_stale_runs() -> int:
    """Mark any orphaned 'running' backtest runs and optimizations as failed.

    The asyncio task that polls a VPS job dies with the backend process, so any row
    still 'running' after a restart can never complete on its own — and now that the
    per-platform job lock reads these rows as the single source of truth, a stale
    'running' row would block the platform forever. Called on startup, after
    reset_stale_stress_tests() (which handles stress-test child runs)."""
    now = int(time.time())
    with _connect() as conn:
        runs = conn.execute(
            "UPDATE backtest_runs SET status='failed_crashed', error_message='Backend restarted mid-run' "
            "WHERE status='running'"
        ).rowcount
        opts = conn.execute(
            "UPDATE optimizations SET status='failed_crashed', completed_at=? "
            "WHERE status='running'",
            (now,),
        ).rowcount
    return runs + opts


def update_stress_test_status(stress_test_id: str, status: str, error_message: Optional[str] = None) -> None:
    now = int(time.time())
    with _connect() as conn:
        if status in ("complete", ) or status.startswith("failed"):
            conn.execute(
                "UPDATE stress_tests SET status=?, error_message=?, completed_at=? WHERE stress_test_id=?",
                (status, error_message, now, stress_test_id),
            )
        else:
            conn.execute(
                "UPDATE stress_tests SET status=?, error_message=? WHERE stress_test_id=?",
                (status, error_message, stress_test_id),
            )


def update_stress_test_mc(stress_test_id: str, mc: dict, paths: dict) -> None:
    now = int(time.time())
    with _connect() as conn:
        conn.execute("""
            UPDATE stress_tests SET
                status='complete', completed_at=?, mc_completed_at=?,
                median_final_pnl=?, pct5_final_pnl=?, pct1_final_pnl=?,
                median_max_dd=?, pct5_max_dd=?, pct1_max_dd=?,
                prob_breach=?, prob_pass_eval=?,
                equity_paths_path=?, distribution_path=?
            WHERE stress_test_id=?
        """, (
            now, now,
            mc.get("median_final_pnl"), mc.get("pct5_final_pnl"), mc.get("pct1_final_pnl"),
            mc.get("median_max_dd"), mc.get("pct5_max_dd"), mc.get("pct1_max_dd"),
            mc.get("prob_breach"), mc.get("prob_pass_eval"),
            paths.get("equity_paths_path"), paths.get("distribution_path"),
            stress_test_id,
        ))


def update_stress_test_walk_forward(stress_test_id: str, summary: list, degradation: float) -> None:
    now = int(time.time())
    with _connect() as conn:
        conn.execute(
            "UPDATE stress_tests SET status='running_sens', wf_completed_at=?, walk_forward_summary=?, walk_forward_degradation=? WHERE stress_test_id=?",
            (now, json.dumps(summary), degradation, stress_test_id),
        )


def update_stress_test_sensitivity(stress_test_id: str, summary: dict, max_degradation: float) -> None:
    with _connect() as conn:
        conn.execute(
            "UPDATE stress_tests SET sensitivity_summary=?, sensitivity_max_degradation=? WHERE stress_test_id=?",
            (json.dumps(summary), max_degradation, stress_test_id),
        )


def update_stress_test_grade(stress_test_id: str, grade: str, reasons: list[str]) -> None:
    now = int(time.time())
    with _connect() as conn:
        conn.execute(
            "UPDATE stress_tests SET status='complete', completed_at=?, grade=?, grade_reasons=? WHERE stress_test_id=?",
            (now, grade, json.dumps(reasons), stress_test_id),
        )


def running_stress_test_markets() -> dict:
    """Returns {futures, forex, run_ids} for currently running stress tests."""
    with _connect() as conn:
        rows = conn.execute("""
            SELECT st.run_id, COALESCE(s.runner, 'ninjatrader') AS runner
            FROM stress_tests st
            JOIN backtest_runs r ON r.run_id = st.run_id
            LEFT JOIN strategies s ON s.id = r.strategy_id
            WHERE st.status LIKE 'running%'
        """).fetchall()
    result: dict = {"futures": False, "forex": False, "run_ids": []}
    for row in rows:
        result["run_ids"].append(row["run_id"])
        if row["runner"] == "mt5":
            result["forex"] = True
        else:
            result["futures"] = True
    return result


def delete_stress_test(stress_test_id: str) -> bool:
    with _connect() as conn:
        # cascade: delete stress-test child runs
        child_ids = [
            r["run_id"] for r in conn.execute(
                "SELECT run_id FROM backtest_runs WHERE stress_test_id=?", (stress_test_id,)
            ).fetchall()
        ]
        if child_ids:
            ph = ",".join("?" * len(child_ids))
            conn.execute(f"DELETE FROM evaluations WHERE run_id IN ({ph})", child_ids)
            conn.execute(f"DELETE FROM backtest_runs WHERE run_id IN ({ph})", child_ids)
        cur = conn.execute("DELETE FROM stress_tests WHERE stress_test_id=?", (stress_test_id,))
    return cur.rowcount > 0


# ── OHLC Cache ────────────────────────────────────────────────────────────────

def get_cached_ohlc(instrument: str, start_date: str, end_date: str) -> list[dict]:
    """Return cached OHLC rows for instrument in [start_date, end_date], sorted by date asc."""
    with _connect() as conn:
        rows = conn.execute(
            "SELECT date, open, high, low, close FROM instrument_daily_ohlc "
            "WHERE instrument = ? AND date BETWEEN ? AND ? ORDER BY date ASC",
            (instrument, start_date, end_date),
        ).fetchall()
    return [dict(r) for r in rows]


def upsert_ohlc_rows(rows: list[dict]) -> None:
    """Insert or replace OHLC rows. Each row: instrument, date, open, high, low, close, source."""
    if not rows:
        return
    now = int(time.time())
    with _connect() as conn:
        conn.executemany(
            "INSERT OR REPLACE INTO instrument_daily_ohlc "
            "(instrument, date, open, high, low, close, fetched_at, source) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            [
                (r["instrument"], r["date"], r["open"], r["high"],
                 r["low"], r["close"], now, r["source"])
                for r in rows
            ],
        )


def get_cached_intraday_ohlc(
    instrument: str, timeframe: str, start_date: str, end_date: str
) -> list[dict]:
    """Return cached intraday OHLC rows for (instrument, timeframe) in [start_date, end_date].

    Uses ISO string ordering: timestamp >= start_date works because
    "2025-01-01" < "2025-01-01T00:00:00", and timestamp < next day covers
    the last day inclusive (end_date "2025-01-31" → < "2025-02-01").
    """
    next_day = (date.fromisoformat(end_date) + timedelta(days=1)).isoformat()
    with _connect() as conn:
        rows = conn.execute(
            "SELECT timestamp, open, high, low, close FROM instrument_intraday_ohlc "
            "WHERE instrument = ? AND timeframe = ? AND timestamp >= ? AND timestamp < ? "
            "ORDER BY timestamp ASC",
            (instrument, timeframe, start_date, next_day),
        ).fetchall()
    return [dict(r) for r in rows]


def upsert_intraday_ohlc_rows(rows: list[dict]) -> None:
    """Insert or replace intraday OHLC rows.

    Each row must have: instrument, timeframe, timestamp, open, high, low, close, source.
    """
    if not rows:
        return
    now = int(time.time())
    with _connect() as conn:
        conn.executemany(
            "INSERT OR REPLACE INTO instrument_intraday_ohlc "
            "(instrument, timeframe, timestamp, open, high, low, close, fetched_at, source) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
            [
                (r["instrument"], r["timeframe"], r["timestamp"],
                 r["open"], r["high"], r["low"], r["close"], now, r["source"])
                for r in rows
            ],
        )


def insert_run_stress_test_child(data: dict) -> None:
    with _connect() as conn:
        conn.execute("""
            INSERT INTO backtest_runs
                (run_id, strategy_id, instrument, params, bar_type, bar_value,
                 start_date, end_date, commission_per_side, slippage_ticks,
                 status, created_at, started_at, stress_test_id, walk_forward_window_id, runner)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            data["run_id"], data["strategy_id"], data["instrument"],
            json.dumps(data["params"]), data["bar_type"], data["bar_value"],
            data["start_date"], data["end_date"],
            data["commission_per_side"], data["slippage_ticks"],
            data["status"], data["created_at"], data.get("started_at", data["created_at"]),
            data["stress_test_id"], data.get("walk_forward_window_id"),
            data.get("runner", "ninjatrader"),
        ))


# ── Job queue ──────────────────────────────────────────────────────────────────

def queue_enqueue(queue_id: str, job_type: str, payload: dict) -> dict:
    """Append a job to the end of the queue. Returns the new row."""
    now = int(time.time())
    with _connect() as conn:
        max_pos = conn.execute(
            "SELECT COALESCE(MAX(position), 0) FROM job_queue WHERE status IN ('pending', 'running')"
        ).fetchone()[0]
        pos = max_pos + 1
        conn.execute(
            "INSERT INTO job_queue (queue_id, job_type, payload, status, position, created_at) "
            "VALUES (?, ?, ?, 'pending', ?, ?)",
            (queue_id, job_type, json.dumps(payload), pos, now),
        )
    return queue_get(queue_id)  # type: ignore[return-value]


def queue_list() -> list[dict]:
    with _connect() as conn:
        rows = conn.execute(
            "SELECT * FROM job_queue ORDER BY position ASC"
        ).fetchall()
    return [_parse_json_fields(dict(r), ["payload"]) for r in rows]


def queue_get(queue_id: str) -> Optional[dict]:
    with _connect() as conn:
        row = conn.execute(
            "SELECT * FROM job_queue WHERE queue_id = ?", (queue_id,)
        ).fetchone()
    if not row:
        return None
    return _parse_json_fields(dict(row), ["payload"])


def queue_next_pending() -> Optional[dict]:
    """Return the lowest-position pending job, or None if the queue is empty."""
    with _connect() as conn:
        row = conn.execute(
            "SELECT * FROM job_queue WHERE status = 'pending' ORDER BY position ASC LIMIT 1"
        ).fetchone()
    if not row:
        return None
    return _parse_json_fields(dict(row), ["payload"])


def queue_set_running(queue_id: str) -> None:
    with _connect() as conn:
        conn.execute(
            "UPDATE job_queue SET status = 'running', started_at = ? WHERE queue_id = ?",
            (int(time.time()), queue_id),
        )


def queue_set_done(queue_id: str) -> None:
    with _connect() as conn:
        conn.execute(
            "UPDATE job_queue SET status = 'done', finished_at = ? WHERE queue_id = ?",
            (int(time.time()), queue_id),
        )


def queue_set_failed(queue_id: str, error: str) -> None:
    with _connect() as conn:
        conn.execute(
            "UPDATE job_queue SET status = 'failed', finished_at = ?, error = ? WHERE queue_id = ?",
            (int(time.time()), error, queue_id),
        )


def queue_delete(queue_id: str) -> bool:
    """Remove a job. Only pending jobs can be deleted. Returns True if deleted."""
    with _connect() as conn:
        n = conn.execute(
            "DELETE FROM job_queue WHERE queue_id = ? AND status = 'pending'",
            (queue_id,),
        ).rowcount
    return n > 0


def queue_has_running() -> bool:
    with _connect() as conn:
        n = conn.execute(
            "SELECT COUNT(*) FROM job_queue WHERE status = 'running'"
        ).fetchone()[0]
    return n > 0
