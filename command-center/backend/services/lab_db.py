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
                daily_halt_fraction         REAL
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
            # Runner field on backtest_runs for platform-specific locking
            "ALTER TABLE backtest_runs ADD COLUMN runner TEXT NOT NULL DEFAULT 'ninjatrader'",
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
            # Speed Step 3 — grid sensitivity stored on the optimization row
            "ALTER TABLE optimizations ADD COLUMN grid_sensitivity_score REAL",
            "ALTER TABLE optimizations ADD COLUMN grid_sensitivity_summary TEXT",
        ]:
            try:
                conn.execute(migration_sql)
            except Exception:
                pass

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
            # personal example: 1.0% risk (higher — smaller account), 0.5 halt fraction
            "UPDATE rulesets SET risk_per_trade_pct = 1.0 "
            "WHERE id = 'personal_futures_10k_example' AND risk_per_trade_pct IS NULL",
            "UPDATE rulesets SET daily_halt_fraction = 0.5 "
            "WHERE id = 'personal_futures_10k_example' AND daily_halt_fraction IS NULL",
            # personal example: $150 daily target with 80% lock-in
            "UPDATE rulesets SET daily_profit_target = 150, daily_profit_lock_pct = 0.80 "
            "WHERE id = 'personal_futures_10k_example' AND daily_profit_target IS NULL",
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

        _seed_rulesets(conn)

    # Run outside the main context manager — needs FK enforcement off, which
    # can't be toggled inside an active transaction in SQLite.
    _migrate_strategy_renames()
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


def _seed_rulesets(conn: sqlite3.Connection) -> None:
    now = int(time.time())
    _INSTRUMENTS = ["MES", "MNQ", "MGC", "MCL", "MYM", "M2K"]
    _PLATFORMS = ["NinjaTrader", "Tradovate"]

    # Seed initial LucidFlex rows only on a fresh DB
    if conn.execute("SELECT COUNT(*) FROM rulesets").fetchone()[0] == 0:
        seeds = [
            {
                "id": "lucidflex_50k_eval",
                "name": "LucidFlex $50k Eval",
                "account_size": 50000,
                "profit_target": 3000,
                "max_loss_eod": 2000,
                "max_loss_intraday": None,
                "drawdown_type": "eod",
                "consistency_pct": 50.0,
                "min_trading_days": 5,
                "force_flat_time_et": "15:30",
                "allowed_instruments": _INSTRUMENTS,
                "max_contracts": {"mini_max": 4, "micro_max": 40},
                "platform_support": _PLATFORMS,
                "account_tier": "eval",
                "ruleset_type": "prop_eval",
                "daily_loss_cap": 2000,
                "docs_url": "https://support.lucidtrading.com/en/articles/12945790-lucidflex-evaluation-account",
                "notes": "Verified from docs_url on 2026-05-29",
            },
            {
                "id": "lucidflex_50k_funded",
                "name": "LucidFlex $50k Funded",
                "account_size": 50000,
                "profit_target": 0,
                "max_loss_eod": 2000,
                "max_loss_intraday": None,
                "drawdown_type": "eod",
                "consistency_pct": None,
                "min_trading_days": None,
                "force_flat_time_et": "15:30",
                "allowed_instruments": _INSTRUMENTS,
                "max_contracts": {"mini_max": 4, "micro_max": 40},
                "platform_support": _PLATFORMS,
                "account_tier": "funded",
                "ruleset_type": "prop_funded",
                "daily_loss_cap": 2000,
                "docs_url": "https://support.lucidtrading.com/en/articles/12945795-lucidflex-funded-account",
                "notes": "Verified from docs_url on 2026-05-29",
            },
            {
                "id": "lucidflex_100k_eval",
                "name": "LucidFlex $100k Eval",
                "account_size": 100000,
                "profit_target": 6000,
                "max_loss_eod": 3000,
                "max_loss_intraday": None,
                "drawdown_type": "eod",
                "consistency_pct": 50.0,
                "min_trading_days": 5,
                "force_flat_time_et": "15:30",
                "allowed_instruments": _INSTRUMENTS,
                "max_contracts": {"mini_max": 6, "micro_max": 60},
                "platform_support": _PLATFORMS,
                "account_tier": "eval",
                "ruleset_type": "prop_eval",
                "daily_loss_cap": 3000,
                "docs_url": "https://support.lucidtrading.com/en/articles/12945790-lucidflex-evaluation-account",
                "notes": "Verified from docs_url on 2026-05-29",
            },
            {
                "id": "lucidflex_100k_funded",
                "name": "LucidFlex $100k Funded",
                "account_size": 100000,
                "profit_target": 0,
                "max_loss_eod": 3000,
                "max_loss_intraday": None,
                "drawdown_type": "eod",
                "consistency_pct": None,
                "min_trading_days": None,
                "force_flat_time_et": "15:30",
                "allowed_instruments": _INSTRUMENTS,
                "max_contracts": {"mini_max": 6, "micro_max": 60},
                "platform_support": _PLATFORMS,
                "account_tier": "funded",
                "ruleset_type": "prop_funded",
                "daily_loss_cap": 3000,
                "docs_url": "https://support.lucidtrading.com/en/articles/12945795-lucidflex-funded-account",
                "notes": "Verified from docs_url on 2026-05-29",
            },
        ]
        for f in seeds:
            conn.execute(
                """INSERT INTO rulesets
                   (id, name, account_size, profit_target, max_loss_eod, max_loss_intraday,
                    drawdown_type, consistency_pct, min_trading_days, force_flat_time_et,
                    allowed_instruments, max_contracts, platform_support,
                    account_tier, ruleset_type, daily_loss_cap, docs_url, notes, created_at, updated_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    f["id"], f["name"], f["account_size"], f["profit_target"],
                    f["max_loss_eod"], f.get("max_loss_intraday"), f["drawdown_type"],
                    f.get("consistency_pct"), f.get("min_trading_days"), f.get("force_flat_time_et"),
                    json.dumps(f["allowed_instruments"]), json.dumps(f["max_contracts"]),
                    json.dumps(f["platform_support"]),
                    f["account_tier"], f.get("ruleset_type", "prop_eval"),
                    f.get("daily_loss_cap"), f.get("docs_url"), f.get("notes"),
                    now, now,
                ),
            )

    # Always ensure the personal futures example exists (idempotent)
    if not conn.execute(
        "SELECT 1 FROM rulesets WHERE id=?", ("personal_futures_10k_example",)
    ).fetchone():
        conn.execute(
            """INSERT INTO rulesets
               (id, name, account_size, profit_target, max_loss_eod, max_loss_intraday,
                drawdown_type, consistency_pct, min_trading_days, force_flat_time_et,
                allowed_instruments, max_contracts, platform_support,
                account_tier, ruleset_type, daily_loss_cap, weekly_loss_cap,
                daily_profit_goal, description, notes, created_at, updated_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                "personal_futures_10k_example",
                "Personal $10k Futures (Example)",
                10000, 0, 200, None,
                "static", None, None, "15:50",
                json.dumps(["MES", "MNQ", "MGC", "MCL"]),
                json.dumps({"any": 2}),
                json.dumps(["NinjaTrader", "Tradovate"]),
                "live", "personal",
                200, 700, 150,
                "Example template — adjust limits to match your real capital and risk tolerance.",
                "Seed example for the personal ruleset type. Edit or delete as needed.",
                now, now,
            ),
        )

    # M5 — personal forex rulesets (idempotent)
    _FX_INSTRUMENTS = json.dumps([
        "XAUUSD", "XAGUSD", "EURUSD", "GBPUSD", "GBPJPY",
        "USDJPY", "AUDUSD", "USDCAD", "EURGBP", "NAS100",
    ])
    _FX_DAYS = json.dumps(["sun", "mon", "tue", "wed", "thu"])

    _FX_RULESET_SQL = """
        INSERT INTO rulesets
            (id, name, account_size, profit_target, max_loss_eod, max_loss_intraday,
             drawdown_type, consistency_pct, min_trading_days, force_flat_time_et,
             allowed_instruments, max_contracts, platform_support,
             account_tier, ruleset_type, market, drawdown_unit,
             daily_loss_cap, weekly_loss_cap, daily_profit_target,
             daily_profit_lock_pct, risk_per_trade_pct, max_consecutive_losses,
             earliest_entry_time_et, latest_entry_time_et, days_of_week_allowed,
             default_commission_per_side, default_slippage_ticks, description,
             created_at, updated_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """

    if not conn.execute("SELECT 1 FROM rulesets WHERE id=?", ("personal_forex_main",)).fetchone():
        conn.execute(_FX_RULESET_SQL, (
            "personal_forex_main",
            "Personal Forex Main Account",
            10000, 0, 200, None,
            "static", None, None, None,        # force_flat_time_et null — MT5 strategies manage sessions
            _FX_INSTRUMENTS,
            json.dumps({"any": 5}),
            json.dumps(["MT5"]),
            "live", "personal", "forex", "usd",
            200, 700, 150,
            0.80, 1.0, 3,
            None, None,                         # entry hours null — FX runs 24h
            _FX_DAYS,
            0.0, 1,
            "Personal forex trading account. Edit with real numbers.",
            now, now,
        ))

    if not conn.execute("SELECT 1 FROM rulesets WHERE id=?", ("personal_forex_demo",)).fetchone():
        conn.execute(_FX_RULESET_SQL, (
            "personal_forex_demo",
            "Personal Forex Demo Account",
            10000, 0, 200, None,
            "static", None, None, None,
            _FX_INSTRUMENTS,
            json.dumps({"any": 5}),
            json.dumps(["MT5"]),
            "live", "demo", "forex", "usd",
            200, 700, 150,
            0.80, 1.0, 3,
            None, None,
            _FX_DAYS,
            0.0, 1,
            "Forex demo/paper account. No real capital at risk.",
            now, now,
        ))

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
            LEFT JOIN backtest_runs r ON r.strategy_id = s.id
            GROUP BY s.id
            ORDER BY s.name
        """).fetchall()
    return [_parse_json_fields(dict(r), ["default_params", "param_schema"]) for r in rows]


def get_strategy(strategy_id: str) -> Optional[dict]:
    with _connect() as conn:
        row = conn.execute("""
            SELECT s.*, COUNT(r.run_id) AS run_count
            FROM strategies s
            LEFT JOIN backtest_runs r ON r.strategy_id = s.id
            WHERE s.id = ?
            GROUP BY s.id
        """, (strategy_id,)).fetchone()
    if not row:
        return None
    return _parse_json_fields(dict(row), ["default_params", "param_schema"])


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
                 default_params, param_schema, scanned_at, source_hash, runner)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
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
                runner=excluded.runner
        """, (
            data["id"], data["name"], data["class_name"], data["source_path"],
            data.get("category"), data.get("suggested_instrument"),
            json.dumps(data.get("default_params", {})),
            json.dumps(data.get("param_schema", [])),
            data["scanned_at"], data.get("source_hash"),
            data.get("runner", "ninjatrader"),
        ))


def mark_strategy_needs_compile(class_name: str) -> None:
    """Called after a source file is uploaded — marks that strategy as needing compile."""
    with _connect() as conn:
        conn.execute(
            "UPDATE strategies SET is_compiled = 0 WHERE class_name = ?", (class_name,)
        )


def mark_runner_compiled(runner: str) -> None:
    """Called after a successful compile — marks all strategies for that runner as compiled."""
    with _connect() as conn:
        conn.execute(
            "UPDATE strategies SET is_compiled = 1 WHERE runner = ?", (runner,)
        )


def delete_strategy(strategy_id: str) -> bool:
    with _connect() as conn:
        cur = conn.execute("DELETE FROM strategies WHERE id = ?", (strategy_id,))
    return cur.rowcount > 0


# ── Rulesets ──────────────────────────────────────────────────────────────────

_RULESET_JSON_FIELDS = ["allowed_instruments", "max_contracts", "platform_support", "days_of_week_allowed"]


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


# Keep old name as alias for any callers not yet updated (will remove post-M3)
def get_firm(firm_id: str) -> Optional[dict]:
    return get_ruleset(firm_id)


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


def delete_ruleset(ruleset_id: str) -> bool:
    with _connect() as conn:
        cur = conn.execute("DELETE FROM rulesets WHERE id = ?", (ruleset_id,))
    return cur.rowcount > 0


# ── Instrument metadata ───────────────────────────────────────────────────────

def list_instrument_metadata() -> list[dict]:
    with _connect() as conn:
        rows = conn.execute(
            "SELECT * FROM instrument_metadata ORDER BY market, symbol"
        ).fetchall()
    return [dict(r) for r in rows]


def get_instrument_metadata(symbol: str) -> Optional[dict]:
    with _connect() as conn:
        row = conn.execute(
            "SELECT * FROM instrument_metadata WHERE symbol = ?", (symbol.upper(),)
        ).fetchone()
    return dict(row) if row else None


def upsert_instrument_metadata(data: dict) -> None:
    with _connect() as conn:
        conn.execute(
            """INSERT INTO instrument_metadata
               (symbol, market, display_name, tick_size, point_value_usd,
                broker_suffix, default_session, notes)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?)
               ON CONFLICT(symbol) DO UPDATE SET
                   market=excluded.market,
                   display_name=excluded.display_name,
                   tick_size=excluded.tick_size,
                   point_value_usd=excluded.point_value_usd,
                   broker_suffix=excluded.broker_suffix,
                   default_session=excluded.default_session,
                   notes=excluded.notes""",
            (
                data["symbol"].upper(), data["market"], data["display_name"],
                data.get("tick_size"), data.get("point_value_usd"),
                data.get("broker_suffix", ""), data.get("default_session"),
                data.get("notes"),
            ),
        )


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

    if base_clauses:
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
                 status, created_at, evaluate_firms, runner, optimization_id, source_run_id)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            data["run_id"], data["strategy_id"], data["instrument"],
            json.dumps(data["params"]), data["bar_type"], data["bar_value"],
            data["start_date"], data["end_date"],
            data["commission_per_side"], data["slippage_ticks"],
            data["status"], data["created_at"],
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
                equity_curve_path=?, trades_path=?, daily_pnl_path=?
            WHERE run_id=?
        """, (
            now,
            kpis.get("net_pnl"), kpis.get("max_drawdown"), kpis.get("profit_factor"),
            kpis.get("win_rate"), kpis.get("win_count"), kpis.get("trade_count"),
            kpis.get("sharpe"), kpis.get("sortino"), kpis.get("cagr"),
            kpis.get("avg_win"), kpis.get("avg_loss"), kpis.get("avg_trade_duration_min"),
            kpis.get("worst_day_pnl"), kpis.get("worst_losing_streak"),
            file_paths.get("equity_curve"), file_paths.get("trades"),
            file_paths.get("daily_pnl"), run_id,
        ))


def delete_run(run_id: str) -> bool:
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
                ph = ",".join("?" * len(child_ids))
                conn.execute(f"DELETE FROM evaluations WHERE run_id IN ({ph})", child_ids)
                conn.execute(f"DELETE FROM backtest_runs WHERE run_id IN ({ph})", child_ids)
            conn.execute("DELETE FROM optimizations WHERE optimization_id = ?", (oid,))

        # Cascade: delete associated sweeps (runs where source_run_id = this run)
        sweep_child_ids = [
            r["run_id"] for r in conn.execute(
                "SELECT run_id FROM backtest_runs WHERE source_run_id = ?", (run_id,)
            ).fetchall()
        ]
        if sweep_child_ids:
            ph = ",".join("?" * len(sweep_child_ids))
            conn.execute(f"DELETE FROM evaluations WHERE run_id IN ({ph})", sweep_child_ids)
            conn.execute(f"DELETE FROM backtest_runs WHERE run_id IN ({ph})", sweep_child_ids)

        # Delete the run itself
        conn.execute("DELETE FROM evaluations WHERE run_id = ?", (run_id,))
        cur = conn.execute("DELETE FROM backtest_runs WHERE run_id = ?", (run_id,))
    return cur.rowcount > 0


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
                   rs.max_loss_eod    AS firm_max_loss_eod,
                   rs.profit_target   AS firm_profit_target,
                   rs.consistency_pct AS firm_consistency_pct
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
                 largest_day_share_pct, notes, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            data["eval_id"], data["run_id"], data["ruleset_id"],
            data["verdict"],
            int(data["drawdown_pass"]), int(data["target_pass"]),
            int(data["consistency_pass"]) if data.get("consistency_pass") is not None else None,
            data.get("simulated_eval_days"), data["breach_count"],
            data.get("largest_day_share_pct"), data.get("notes"),
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


def has_running_sweep(strategy_id: str) -> bool:
    with _connect() as conn:
        count = conn.execute(
            "SELECT COUNT(*) FROM backtest_runs WHERE sweep_id IS NOT NULL AND strategy_id = ? AND status = 'running'",
            (strategy_id,),
        ).fetchone()[0]
    return count > 0


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


def has_any_running_vps_job() -> bool:
    """True if any sweep run, optimization run, or standalone backtest is currently running."""
    with _connect() as conn:
        run_count = conn.execute(
            "SELECT COUNT(*) FROM backtest_runs WHERE status = 'running'",
        ).fetchone()[0]
        opt_count = conn.execute(
            "SELECT COUNT(*) FROM optimizations WHERE status = 'running'",
        ).fetchone()[0]
    return (run_count + opt_count) > 0


def has_running_nt8_job() -> bool:
    """True if any NT8 job (backtest, sweep, or optimization) is currently running."""
    with _connect() as conn:
        run_count = conn.execute(
            "SELECT COUNT(*) FROM backtest_runs WHERE status = 'running' AND COALESCE(runner, 'ninjatrader') != 'mt5'",
        ).fetchone()[0]
        opt_count = conn.execute(
            "SELECT COUNT(*) FROM optimizations WHERE status = 'running'",
        ).fetchone()[0]
    return (run_count + opt_count) > 0


def has_running_mt5_job() -> bool:
    """True if any MT5 backtest is currently running."""
    with _connect() as conn:
        count = conn.execute(
            "SELECT COUNT(*) FROM backtest_runs WHERE status = 'running' AND runner = 'mt5'",
        ).fetchone()[0]
    return count > 0


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

        # NT8 sweep (sweeps are NT8-only for now)
        if not result["nt8"]["running"]:
            row = conn.execute("""
                SELECT 'sweep' AS job_type, r.sweep_id AS job_id,
                       COALESCE(s.name, r.strategy_id) || ' sweep' AS description
                FROM backtest_runs r
                LEFT JOIN strategies s ON s.id = r.strategy_id
                WHERE r.status = 'running' AND r.sweep_id IS NOT NULL
                LIMIT 1
            """).fetchone()
            if row:
                result["nt8"] = {"running": True, **dict(row)}

        # NT8 optimization
        if not result["nt8"]["running"]:
            row = conn.execute("""
                SELECT 'optimization' AS job_type, o.optimization_id AS job_id,
                       COALESCE(s.name, o.strategy_id) || ' optimization on ' || o.instrument
                       || ' (' || o.completed_runs || '/' || o.estimated_runs || ')' AS description
                FROM optimizations o
                LEFT JOIN strategies s ON s.id = o.strategy_id
                WHERE o.status = 'running'
                LIMIT 1
            """).fetchone()
            if row:
                result["nt8"] = {"running": True, **dict(row)}

    return result


def insert_run_sweep(data: dict) -> None:
    with _connect() as conn:
        conn.execute("""
            INSERT INTO backtest_runs
                (run_id, strategy_id, instrument, params, bar_type, bar_value,
                 start_date, end_date, commission_per_side, slippage_ticks,
                 status, created_at, sweep_id, source_run_id)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            data["run_id"], data["strategy_id"], data["instrument"],
            json.dumps(data["params"]), data["bar_type"], data["bar_value"],
            data["start_date"], data["end_date"],
            data["commission_per_side"], data["slippage_ticks"],
            data["status"], data["created_at"], data["sweep_id"],
            data.get("source_run_id"),
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
                 source_run_id, regime_filter)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 0, ?, ?, ?)
        """, (
            data["optimization_id"], data["strategy_id"], data["instrument"],
            data["start_date"], data["end_date"],
            data["commission_per_side"], data["slippage_ticks"],
            data["ruleset_id"], data["mode"], data["search_method"],
            json.dumps(data["param_grid"]), data["status"], data["estimated_runs"],
            now, data.get("source_run_id"), data.get("regime_filter"),
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
    with _connect() as conn:
        conn.execute(
            "UPDATE backtest_runs SET status='running', error_message=NULL, completed_at=NULL WHERE run_id=?",
            (run_id,),
        )


def decrement_optimization_completed(optimization_id: str, count: int) -> None:
    with _connect() as conn:
        conn.execute(
            "UPDATE optimizations SET completed_runs = MAX(0, completed_runs - ?), status='running', completed_at=NULL "
            "WHERE optimization_id=?",
            (count, optimization_id),
        )


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
                 status, created_at, optimization_id, runner)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            data["run_id"], data["strategy_id"], data["instrument"],
            json.dumps(data["params"]), data["bar_type"], data["bar_value"],
            data["start_date"], data["end_date"],
            data["commission_per_side"], data["slippage_ticks"],
            data["status"], data["created_at"], data["optimization_id"],
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


def get_latest_stress_test_for_run(run_id: str) -> Optional[dict]:
    with _connect() as conn:
        row = conn.execute(
            "SELECT * FROM stress_tests WHERE run_id = ? ORDER BY created_at DESC LIMIT 1",
            (run_id,),
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
                 status, created_at, stress_test_id, walk_forward_window_id)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            data["run_id"], data["strategy_id"], data["instrument"],
            json.dumps(data["params"]), data["bar_type"], data["bar_value"],
            data["start_date"], data["end_date"],
            data["commission_per_side"], data["slippage_ticks"],
            data["status"], data["created_at"],
            data["stress_test_id"], data.get("walk_forward_window_id"),
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
