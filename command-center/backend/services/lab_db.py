"""
Lab SQLite helper — strategies, firms, backtest_runs, evaluations.
Single entry point for all lab DB access. No other module touches lab.db.
"""

from __future__ import annotations

import json
import sqlite3
import time
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

            CREATE TABLE IF NOT EXISTS firms (
                id                  TEXT PRIMARY KEY,
                name                TEXT NOT NULL,
                account_size        INTEGER NOT NULL,
                profit_target       INTEGER NOT NULL,
                max_loss_eod        INTEGER NOT NULL,
                max_loss_intraday   INTEGER,
                drawdown_type       TEXT NOT NULL,
                consistency_pct     REAL,
                min_trading_days    INTEGER,
                force_flat_time_et  TEXT,
                allowed_instruments TEXT,
                max_contracts       TEXT,
                platform_support    TEXT,
                account_tier        TEXT NOT NULL DEFAULT 'eval',
                docs_url            TEXT,
                notes               TEXT,
                created_at          INTEGER NOT NULL,
                updated_at          INTEGER NOT NULL
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
                firm_id               TEXT NOT NULL REFERENCES firms(id),
                verdict               TEXT NOT NULL,
                drawdown_pass         INTEGER NOT NULL,
                target_pass           INTEGER NOT NULL,
                consistency_pass      INTEGER,
                simulated_eval_days   INTEGER,
                breach_count          INTEGER NOT NULL,
                largest_day_share_pct REAL,
                notes                 TEXT,
                created_at            INTEGER NOT NULL,
                UNIQUE(run_id, firm_id)
            );

            CREATE INDEX IF NOT EXISTS idx_evals_firm
                ON evaluations(firm_id, verdict);
        """)
        # Migration: rename column on existing databases
        try:
            conn.execute(
                "ALTER TABLE strategies RENAME COLUMN default_instrument TO suggested_instrument"
            )
        except Exception:
            pass
        _seed_firms(conn)


def _seed_firms(conn: sqlite3.Connection) -> None:
    if conn.execute("SELECT COUNT(*) FROM firms").fetchone()[0] > 0:
        return
    now = int(time.time())
    _INSTRUMENTS = ["MES", "MNQ", "MGC", "MCL", "MYM", "M2K"]
    _PLATFORMS = ["NinjaTrader", "Tradovate"]
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
            "docs_url": "https://support.lucidtrading.com/en/articles/12945795-lucidflex-funded-account",
            "notes": "Verified from docs_url on 2026-05-29",
        },
    ]
    for f in seeds:
        conn.execute(
            """INSERT INTO firms
               (id, name, account_size, profit_target, max_loss_eod, max_loss_intraday,
                drawdown_type, consistency_pct, min_trading_days, force_flat_time_et,
                allowed_instruments, max_contracts, platform_support,
                account_tier, docs_url, notes, created_at, updated_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                f["id"], f["name"], f["account_size"], f["profit_target"],
                f["max_loss_eod"], f["max_loss_intraday"], f["drawdown_type"],
                f["consistency_pct"], f["min_trading_days"], f["force_flat_time_et"],
                json.dumps(f["allowed_instruments"]), json.dumps(f["max_contracts"]),
                json.dumps(f["platform_support"]),
                f["account_tier"], f.get("docs_url"), f.get("notes"),
                now, now,
            ),
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


def upsert_strategy(data: dict) -> None:
    with _connect() as conn:
        conn.execute("""
            INSERT INTO strategies
                (id, name, class_name, source_path, category, suggested_instrument,
                 default_params, param_schema, scanned_at, source_hash)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(id) DO UPDATE SET
                name=excluded.name,
                class_name=excluded.class_name,
                source_path=excluded.source_path,
                category=excluded.category,
                suggested_instrument=excluded.suggested_instrument,
                default_params=excluded.default_params,
                param_schema=excluded.param_schema,
                scanned_at=excluded.scanned_at,
                source_hash=excluded.source_hash
        """, (
            data["id"], data["name"], data["class_name"], data["source_path"],
            data.get("category"), data.get("suggested_instrument"),
            json.dumps(data.get("default_params", {})),
            json.dumps(data.get("param_schema", [])),
            data["scanned_at"], data.get("source_hash"),
        ))


def delete_strategy(strategy_id: str) -> bool:
    with _connect() as conn:
        cur = conn.execute("DELETE FROM strategies WHERE id = ?", (strategy_id,))
    return cur.rowcount > 0


# ── Firms ─────────────────────────────────────────────────────────────────────

_FIRM_JSON_FIELDS = ["allowed_instruments", "max_contracts", "platform_support"]


def list_firms() -> list[dict]:
    with _connect() as conn:
        rows = conn.execute("SELECT * FROM firms ORDER BY account_size").fetchall()
    return [_parse_json_fields(dict(r), _FIRM_JSON_FIELDS) for r in rows]


def get_firm(firm_id: str) -> Optional[dict]:
    with _connect() as conn:
        row = conn.execute("SELECT * FROM firms WHERE id = ?", (firm_id,)).fetchone()
    if not row:
        return None
    return _parse_json_fields(dict(row), _FIRM_JSON_FIELDS)


def insert_firm(data: dict) -> None:
    now = int(time.time())
    with _connect() as conn:
        conn.execute(
            """INSERT INTO firms
               (id, name, account_size, profit_target, max_loss_eod, max_loss_intraday,
                drawdown_type, consistency_pct, min_trading_days, force_flat_time_et,
                allowed_instruments, max_contracts, platform_support,
                account_tier, docs_url, notes, created_at, updated_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                data["id"], data["name"], data["account_size"], data["profit_target"],
                data["max_loss_eod"], data.get("max_loss_intraday"), data["drawdown_type"],
                data.get("consistency_pct"), data.get("min_trading_days"),
                data.get("force_flat_time_et"),
                json.dumps(data.get("allowed_instruments", [])),
                json.dumps(data.get("max_contracts", {})),
                json.dumps(data.get("platform_support", [])),
                data.get("account_tier", "eval"), data.get("docs_url"), data.get("notes"),
                now, now,
            ),
        )


def update_firm(firm_id: str, data: dict) -> bool:
    now = int(time.time())
    with _connect() as conn:
        cur = conn.execute(
            """UPDATE firms SET
               name=?, account_size=?, profit_target=?, max_loss_eod=?,
               max_loss_intraday=?, drawdown_type=?, consistency_pct=?,
               min_trading_days=?, force_flat_time_et=?, allowed_instruments=?,
               max_contracts=?, platform_support=?, account_tier=?,
               docs_url=?, notes=?, updated_at=?
               WHERE id=?""",
            (
                data["name"], data["account_size"], data["profit_target"],
                data["max_loss_eod"], data.get("max_loss_intraday"), data["drawdown_type"],
                data.get("consistency_pct"), data.get("min_trading_days"),
                data.get("force_flat_time_et"),
                json.dumps(data.get("allowed_instruments", [])),
                json.dumps(data.get("max_contracts", {})),
                json.dumps(data.get("platform_support", [])),
                data.get("account_tier", "eval"), data.get("docs_url"), data.get("notes"),
                now, firm_id,
            ),
        )
    return cur.rowcount > 0


def delete_firm(firm_id: str) -> bool:
    with _connect() as conn:
        cur = conn.execute("DELETE FROM firms WHERE id = ?", (firm_id,))
    return cur.rowcount > 0


# ── Backtest runs ─────────────────────────────────────────────────────────────

def list_runs(
    strategy_id: Optional[str] = None,
    firm_id: Optional[str] = None,
    status: Optional[str] = None,
) -> list[dict]:
    base_clauses: list[str] = []
    params: list[Any] = []

    if firm_id:
        sql = """
            SELECT r.*, s.name AS strategy_name
            FROM backtest_runs r
            JOIN strategies s ON s.id = r.strategy_id
            JOIN evaluations e ON e.run_id = r.run_id AND e.firm_id = ?
        """
        params.append(firm_id)
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
            SELECT r.*, s.name AS strategy_name
            FROM backtest_runs r
            JOIN strategies s ON s.id = r.strategy_id
            WHERE r.run_id = ?
        """, (run_id,)).fetchone()
    if not row:
        return None
    return _parse_json_fields(dict(row), ["params"])


def insert_run(data: dict) -> None:
    with _connect() as conn:
        conn.execute("""
            INSERT INTO backtest_runs
                (run_id, strategy_id, instrument, params, bar_type, bar_value,
                 start_date, end_date, commission_per_side, slippage_ticks,
                 status, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            data["run_id"], data["strategy_id"], data["instrument"],
            json.dumps(data["params"]), data["bar_type"], data["bar_value"],
            data["start_date"], data["end_date"],
            data["commission_per_side"], data["slippage_ticks"],
            data["status"], data["created_at"],
        ))


def update_run_chart_paths(run_id: str, paths: dict) -> None:
    with _connect() as conn:
        conn.execute(
            "UPDATE backtest_runs SET equity_curve_path=?, daily_pnl_path=? WHERE run_id=?",
            (paths.get("equity_curve"), paths.get("daily_pnl"), run_id),
        )


def update_run_status(run_id: str, status: str, error_message: Optional[str] = None) -> None:
    with _connect() as conn:
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
        conn.execute("DELETE FROM evaluations WHERE run_id = ?", (run_id,))
        cur = conn.execute("DELETE FROM backtest_runs WHERE run_id = ?", (run_id,))
    return cur.rowcount > 0


def get_run_verdict_summary(run_id: str) -> list[dict]:
    with _connect() as conn:
        rows = conn.execute(
            "SELECT firm_id, verdict, notes FROM evaluations WHERE run_id = ?", (run_id,)
        ).fetchall()
    return [dict(r) for r in rows]


# ── Evaluations ───────────────────────────────────────────────────────────────

def get_evaluations(run_id: str) -> list[dict]:
    with _connect() as conn:
        rows = conn.execute("""
            SELECT e.*,
                   f.name             AS firm_name,
                   f.max_loss_eod     AS firm_max_loss_eod,
                   f.profit_target    AS firm_profit_target,
                   f.consistency_pct  AS firm_consistency_pct
            FROM evaluations e
            JOIN firms f ON f.id = e.firm_id
            WHERE e.run_id = ?
        """, (run_id,)).fetchall()
    return [dict(r) for r in rows]


def insert_evaluation(data: dict) -> None:
    now = int(time.time())
    with _connect() as conn:
        conn.execute("""
            INSERT OR REPLACE INTO evaluations
                (eval_id, run_id, firm_id, verdict, drawdown_pass, target_pass,
                 consistency_pass, simulated_eval_days, breach_count,
                 largest_day_share_pct, notes, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            data["eval_id"], data["run_id"], data["firm_id"],
            data["verdict"],
            int(data["drawdown_pass"]), int(data["target_pass"]),
            int(data["consistency_pass"]) if data.get("consistency_pass") is not None else None,
            data.get("simulated_eval_days"), data["breach_count"],
            data.get("largest_day_share_pct"), data.get("notes"),
            now,
        ))
