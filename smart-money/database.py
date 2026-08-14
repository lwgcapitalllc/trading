"""
SQLite schema and CRUD layer for the Smart Money Replication System.
All pipeline stages read and write through this module.
"""

from __future__ import annotations

import json
import sqlite3
import time
from contextlib import contextmanager
from pathlib import Path

DB_PATH = Path(__file__).parent / "data" / "smart_money.db"


@contextmanager
def get_conn():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def init_db():
    with get_conn() as conn:
        conn.executescript("""
            CREATE TABLE IF NOT EXISTS wallets (
                id              INTEGER PRIMARY KEY AUTOINCREMENT,
                address         TEXT    NOT NULL,
                source          TEXT    NOT NULL,
                trade_count     INTEGER,
                account_age_days INTEGER,
                first_seen_ts   INTEGER,
                scanned_at      INTEGER,
                UNIQUE(address, source)
            );

            CREATE TABLE IF NOT EXISTS trades (
                id                  INTEGER PRIMARY KEY AUTOINCREMENT,
                wallet_id           INTEGER NOT NULL,
                instrument          TEXT    NOT NULL,
                entry_price         REAL,
                exit_price          REAL,
                size                REAL,
                side                TEXT,
                open_ts             INTEGER,
                close_ts            INTEGER NOT NULL,
                hold_time_seconds   INTEGER,
                pnl                 REAL    NOT NULL,
                is_win              INTEGER NOT NULL,
                FOREIGN KEY(wallet_id) REFERENCES wallets(id)
            );

            CREATE INDEX IF NOT EXISTS idx_trades_wallet_ts
                ON trades(wallet_id, close_ts);

            CREATE TABLE IF NOT EXISTS monthly_windows (
                id              INTEGER PRIMARY KEY AUTOINCREMENT,
                wallet_id       INTEGER NOT NULL,
                window_start    INTEGER NOT NULL,
                window_end      INTEGER NOT NULL,
                trade_count     INTEGER,
                win_count       INTEGER,
                loss_count      INTEGER,
                win_rate        REAL,
                total_pnl       REAL,
                peak_cum_pnl    REAL,
                trough_cum_pnl  REAL,
                active_weeks    INTEGER,
                strike_level    INTEGER DEFAULT 0,
                FOREIGN KEY(wallet_id) REFERENCES wallets(id),
                UNIQUE(wallet_id, window_start)
            );

            CREATE TABLE IF NOT EXISTS disqualified (
                id              INTEGER PRIMARY KEY AUTOINCREMENT,
                address         TEXT    NOT NULL,
                source          TEXT    NOT NULL,
                reason          TEXT    NOT NULL,
                disqualified_at INTEGER NOT NULL
            );

            CREATE TABLE IF NOT EXISTS scores (
                id                          INTEGER PRIMARY KEY AUTOINCREMENT,
                wallet_id                   INTEGER NOT NULL UNIQUE,
                win_rate_consistency        REAL,
                risk_adjusted_return        REAL,
                exit_efficiency             REAL,
                trade_frequency             REAL,
                instrument_day_consistency  REAL,
                composite_score             REAL,
                rank                        INTEGER,
                lookback_tier               TEXT,
                scored_at                   INTEGER,
                FOREIGN KEY(wallet_id) REFERENCES wallets(id)
            );

            CREATE TABLE IF NOT EXISTS run_log (
                id                              INTEGER PRIMARY KEY AUTOINCREMENT,
                stage                           TEXT    NOT NULL,
                started_at                      INTEGER NOT NULL,
                completed_at                    INTEGER,
                total_scanned                   INTEGER DEFAULT 0,
                passed_initial_filter           INTEGER DEFAULT 0,
                passed_win_rate_filter          INTEGER DEFAULT 0,
                passed_disqualification_filter  INTEGER DEFAULT 0,
                total_qualified                 INTEGER DEFAULT 0,
                threshold_adjustments           TEXT,
                notes                           TEXT
            );

            -- Raw fills cache: skip re-fetching wallets scanned recently.
            -- TTL controlled by hyperliquid.fills_cache_hours in config (default 24h).
            -- Re-runs within the TTL window skip all API calls and run filter/profile
            -- logic only — typically reduces re-run time from ~15min to ~30s.
            CREATE TABLE IF NOT EXISTS fills_cache (
                address     TEXT    PRIMARY KEY,
                fills_json  TEXT    NOT NULL,
                fetched_at  INTEGER NOT NULL
            );
        """)


# --- Wallets ---


def upsert_wallet(
    address: str,
    source: str,
    trade_count: int = None,
    account_age_days: int = None,
    first_seen_ts: int = None,
) -> int:
    with get_conn() as conn:
        conn.execute(
            """
            INSERT INTO wallets (address, source, trade_count, account_age_days, first_seen_ts, scanned_at)
            VALUES (?, ?, ?, ?, ?, ?)
            ON CONFLICT(address, source) DO UPDATE SET
                trade_count     = excluded.trade_count,
                account_age_days = excluded.account_age_days,
                first_seen_ts   = excluded.first_seen_ts,
                scanned_at      = excluded.scanned_at
        """,
            (address, source, trade_count, account_age_days, first_seen_ts, int(time.time())),
        )
        row = conn.execute(
            "SELECT id FROM wallets WHERE address = ? AND source = ?", (address, source)
        ).fetchone()
        return row["id"]


def get_wallet_id(address: str, source: str) -> int | None:
    with get_conn() as conn:
        row = conn.execute(
            "SELECT id FROM wallets WHERE address = ? AND source = ?", (address, source)
        ).fetchone()
        return row["id"] if row else None


# --- Trades ---


def insert_trades(wallet_id: int, trades: list[dict]):
    """Replaces all trades for a wallet (idempotent rerun support)."""
    with get_conn() as conn:
        conn.execute("DELETE FROM trades WHERE wallet_id = ?", (wallet_id,))
        conn.executemany(
            """
            INSERT INTO trades
                (wallet_id, instrument, entry_price, exit_price, size, side,
                 open_ts, close_ts, hold_time_seconds, pnl, is_win)
            VALUES
                (:wallet_id, :instrument, :entry_price, :exit_price, :size, :side,
                 :open_ts, :close_ts, :hold_time_seconds, :pnl, :is_win)
        """,
            [{"wallet_id": wallet_id, **t} for t in trades],
        )


def get_trades(wallet_id: int) -> list[dict]:
    with get_conn() as conn:
        rows = conn.execute(
            "SELECT * FROM trades WHERE wallet_id = ? ORDER BY close_ts ASC", (wallet_id,)
        ).fetchall()
        return [dict(r) for r in rows]


# --- Monthly windows ---


def insert_monthly_windows(wallet_id: int, windows: list[dict]):
    with get_conn() as conn:
        conn.execute("DELETE FROM monthly_windows WHERE wallet_id = ?", (wallet_id,))
        conn.executemany(
            """
            INSERT INTO monthly_windows
                (wallet_id, window_start, window_end, trade_count, win_count, loss_count,
                 win_rate, total_pnl, peak_cum_pnl, trough_cum_pnl, active_weeks, strike_level)
            VALUES
                (:wallet_id, :window_start, :window_end, :trade_count, :win_count, :loss_count,
                 :win_rate, :total_pnl, :peak_cum_pnl, :trough_cum_pnl, :active_weeks, :strike_level)
        """,
            [{"wallet_id": wallet_id, **w} for w in windows],
        )


def get_monthly_windows(wallet_id: int) -> list[dict]:
    with get_conn() as conn:
        rows = conn.execute(
            "SELECT * FROM monthly_windows WHERE wallet_id = ? ORDER BY window_start ASC",
            (wallet_id,),
        ).fetchall()
        return [dict(r) for r in rows]


# --- Disqualified ---


def log_disqualified(address: str, source: str, reason: str):
    with get_conn() as conn:
        conn.execute(
            """
            INSERT INTO disqualified (address, source, reason, disqualified_at)
            VALUES (?, ?, ?, ?)
        """,
            (address, source, reason, int(time.time())),
        )


def get_disqualified(source: str = None) -> list[dict]:
    with get_conn() as conn:
        if source:
            rows = conn.execute(
                "SELECT * FROM disqualified WHERE source = ? ORDER BY disqualified_at DESC",
                (source,),
            ).fetchall()
        else:
            rows = conn.execute(
                "SELECT * FROM disqualified ORDER BY disqualified_at DESC"
            ).fetchall()
        return [dict(r) for r in rows]


# --- Scores ---


def upsert_score(wallet_id: int, scores: dict):
    with get_conn() as conn:
        conn.execute(
            """
            INSERT INTO scores
                (wallet_id, win_rate_consistency, risk_adjusted_return, exit_efficiency,
                 trade_frequency, instrument_day_consistency, composite_score,
                 rank, lookback_tier, scored_at)
            VALUES
                (:wallet_id, :win_rate_consistency, :risk_adjusted_return, :exit_efficiency,
                 :trade_frequency, :instrument_day_consistency, :composite_score,
                 :rank, :lookback_tier, :scored_at)
            ON CONFLICT(wallet_id) DO UPDATE SET
                win_rate_consistency       = excluded.win_rate_consistency,
                risk_adjusted_return       = excluded.risk_adjusted_return,
                exit_efficiency            = excluded.exit_efficiency,
                trade_frequency            = excluded.trade_frequency,
                instrument_day_consistency = excluded.instrument_day_consistency,
                composite_score            = excluded.composite_score,
                rank                       = excluded.rank,
                lookback_tier              = excluded.lookback_tier,
                scored_at                  = excluded.scored_at
        """,
            {"wallet_id": wallet_id, "scored_at": int(time.time()), **scores},
        )


def get_ranked_wallets(source: str = None, limit: int = None) -> list[dict]:
    with get_conn() as conn:
        base = """
            SELECT w.address, w.source, w.trade_count, w.account_age_days,
                   s.composite_score, s.win_rate_consistency, s.risk_adjusted_return,
                   s.exit_efficiency, s.trade_frequency, s.instrument_day_consistency,
                   s.rank, s.lookback_tier, w.id as wallet_id
            FROM scores s
            JOIN wallets w ON w.id = s.wallet_id
        """
        params: list = []
        if source:
            base += " WHERE w.source = ?"
            params.append(source)
        base += " ORDER BY s.composite_score DESC"
        if limit:
            base += " LIMIT ?"
            params.append(limit)
        return [dict(r) for r in conn.execute(base, params).fetchall()]


# --- Run log ---


def start_run(stage: str) -> int:
    with get_conn() as conn:
        cur = conn.execute(
            "INSERT INTO run_log (stage, started_at) VALUES (?, ?)", (stage, int(time.time()))
        )
        return cur.lastrowid


def finish_run(run_id: int, counts: dict, notes: str = None, threshold_adjustments: dict = None):
    with get_conn() as conn:
        conn.execute(
            """
            UPDATE run_log SET
                completed_at                    = ?,
                total_scanned                   = ?,
                passed_initial_filter           = ?,
                passed_win_rate_filter          = ?,
                passed_disqualification_filter  = ?,
                total_qualified                 = ?,
                threshold_adjustments           = ?,
                notes                           = ?
            WHERE id = ?
        """,
            (
                int(time.time()),
                counts.get("total_scanned", 0),
                counts.get("passed_initial_filter", 0),
                counts.get("passed_win_rate_filter", 0),
                counts.get("passed_disqualification_filter", 0),
                counts.get("total_qualified", 0),
                json.dumps(threshold_adjustments) if threshold_adjustments else None,
                notes,
                run_id,
            ),
        )


def get_run_log(stage: str = None) -> list[dict]:
    with get_conn() as conn:
        if stage:
            rows = conn.execute(
                "SELECT * FROM run_log WHERE stage = ? ORDER BY started_at DESC", (stage,)
            ).fetchall()
        else:
            rows = conn.execute("SELECT * FROM run_log ORDER BY started_at DESC").fetchall()
        return [dict(r) for r in rows]


# --- Fills cache ---


def get_cached_fills(address: str, max_age_seconds: int) -> list | None:
    """
    Return cached fills for `address` if they were fetched within `max_age_seconds`.
    Returns None on cache miss or stale entry.
    """
    with get_conn() as conn:
        row = conn.execute(
            "SELECT fills_json, fetched_at FROM fills_cache WHERE address = ?", (address,)
        ).fetchone()
    if not row:
        return None
    if int(time.time()) - row["fetched_at"] > max_age_seconds:
        return None
    return json.loads(row["fills_json"])


def cache_fills(address: str, fills: list) -> None:
    """Store or refresh fills for `address`.  Overwrites any existing entry."""
    with get_conn() as conn:
        conn.execute(
            """
            INSERT INTO fills_cache (address, fills_json, fetched_at)
            VALUES (?, ?, ?)
            ON CONFLICT(address) DO UPDATE SET
                fills_json = excluded.fills_json,
                fetched_at = excluded.fetched_at
        """,
            (address, json.dumps(fills), int(time.time())),
        )
