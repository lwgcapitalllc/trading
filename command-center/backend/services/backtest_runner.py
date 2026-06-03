"""
Async background poller for VPS backtest jobs.
Spawned as an asyncio.Task from the backtests router after POSTing to the VPS agent.
"""

from __future__ import annotations

import asyncio
import csv
import io
import json
import logging
import sys
import time
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Optional

import pandas as pd

from services import lab_db, evaluator, vps_client, worthiness

# Add repo root so we can import from trading/regime/
_REPO_ROOT = Path(__file__).resolve().parent.parent.parent.parent
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from regime import classify_regime
from services.ohlc_fetcher import get_ohlc

log = logging.getLogger("backtest_runner")


# ── NT8 Trades CSV parser ──────────────────────────────────────────────────────

def _parse_dollar(s: str) -> float:
    """'($2448.00)' → -2448.0, '$594.00' → 594.0"""
    s = s.replace("$", "").replace(",", "").strip()
    if s.startswith("(") and s.endswith(")"):
        try:
            return -float(s[1:-1])
        except ValueError:
            return 0.0
    try:
        return float(s)
    except ValueError:
        return 0.0


def parse_trades_csv(csv_text: str) -> tuple[list[dict], list[dict]]:
    """Parse NT8 Trades export CSV.
    Returns (equity_curve, daily_pnl) ready for JSON serialisation."""
    reader = csv.DictReader(io.StringIO(csv_text))
    equity_curve: list[dict] = []
    daily_map: dict[str, float] = {}

    for row in reader:
        try:
            trade_num = int(float(row.get("Trade number", 0) or 0))
        except (ValueError, TypeError):
            continue

        cum_pnl   = _parse_dollar(row.get("Cum. net profit", "0"))
        profit    = _parse_dollar(row.get("Profit", "0"))
        direction = (row.get("Market pos.", "") or "").strip()
        exit_name = (row.get("Exit name", "") or "").strip()

        exit_date: Optional[str] = None
        for fmt in ("%m/%d/%Y %I:%M:%S %p", "%m/%d/%Y %H:%M:%S"):
            try:
                exit_date = datetime.strptime(
                    (row.get("Exit time", "") or "").strip(), fmt
                ).strftime("%Y-%m-%d")
                break
            except ValueError:
                pass

        equity_curve.append({
            "index":     trade_num,
            "equity":    round(cum_pnl, 2),
            "date":      exit_date,
            "direction": direction or None,
            "profit":    round(profit, 2),
            "exit_name": exit_name or None,
        })

        if exit_date:
            daily_map[exit_date] = round(
                daily_map.get(exit_date, 0.0) + profit, 2
            )

    daily_pnl = [
        {"date": d, "pnl": v} for d, v in sorted(daily_map.items())
    ]
    return equity_curve, daily_pnl

_POLL_INTERVAL   = 5     # seconds between agent polls
_STALL_WARN_SEC  = 120   # 2 min — warn but keep polling
_STALL_KILL_SEC  = 600   # 10 min — cancel job, mark failed_timeout

_LAB_PROGRESS_PATH = Path(__file__).parent.parent / "data" / "lab_progress.json"
_LAB_RESULTS_DIR   = Path(__file__).parent.parent / "reports" / "lab"
LAB_RESULTS_DIR    = _LAB_RESULTS_DIR


# ── Progress file helpers ──────────────────────────────────────────────────────

def _write_progress(data: dict) -> None:
    _LAB_PROGRESS_PATH.parent.mkdir(parents=True, exist_ok=True)
    _LAB_PROGRESS_PATH.write_text(json.dumps(data, default=str))


def read_progress() -> dict:
    try:
        return json.loads(_LAB_PROGRESS_PATH.read_text())
    except Exception:
        return {"status": "idle", "pct": 0, "message": ""}


def clear_progress() -> None:
    _write_progress({"status": "idle", "pct": 0, "message": ""})


# ── Failure path ───────────────────────────────────────────────────────────────

def _fail(run_id: str, job_id: str, status: str, error_msg: str) -> None:
    lab_db.update_run_status(run_id, status, error_msg)
    _write_progress({
        "job_id": job_id,
        "status": status,
        "pct": 0,
        "message": error_msg,
        "error_message": error_msg,
        "updated_at": str(time.time()),
        "heartbeat_age_seconds": 0.0,
    })


# ── Regime classification helper ──────────────────────────────────────────────

_WARMUP_DAYS = 50   # fetch this many extra days before backtest start for classifier warmup
_WINDOW_SIZE = 34   # classifier needs 34 bars to produce a non-UNKNOWN label


def _tag_daily_pnl_with_regime(
    instrument: str,
    start_date: str,
    end_date: str,
    daily_pnl: list[dict],
) -> list[dict]:
    """
    Fetch OHLC for the backtest period (extended back by _WARMUP_DAYS for warmup),
    then classify each daily_pnl entry by running the rolling 34-bar window through
    classify_regime(). Returns the daily_pnl list with 'regime_tag' added to every entry.
    """
    try:
        warmup_start = (
            date.fromisoformat(start_date) - timedelta(days=_WARMUP_DAYS)
        ).isoformat()
        ohlc_df = get_ohlc(instrument, warmup_start, end_date)
    except Exception as exc:
        log.warning("OHLC fetch failed for %s [%s, %s]: %s — all regime_tags = UNKNOWN",
                    instrument, start_date, end_date, exc)
        return [{**entry, "regime_tag": "UNKNOWN"} for entry in daily_pnl]

    if ohlc_df.empty:
        log.warning("No OHLC rows for %s [%s, %s] — all regime_tags = UNKNOWN",
                    instrument, start_date, end_date)
        return [{**entry, "regime_tag": "UNKNOWN"} for entry in daily_pnl]

    result = []
    for entry in daily_pnl:
        entry_date = entry.get("date")
        if not entry_date:
            result.append({**entry, "regime_tag": "UNKNOWN"})
            continue

        try:
            cutoff = pd.Timestamp(entry_date)
        except Exception:
            result.append({**entry, "regime_tag": "UNKNOWN"})
            continue

        window = ohlc_df[ohlc_df.index <= cutoff].tail(_WINDOW_SIZE)
        if len(window) < _WINDOW_SIZE:
            result.append({**entry, "regime_tag": "UNKNOWN"})
            continue

        try:
            label = classify_regime(window, window)
        except Exception as exc:
            log.warning("classify_regime failed for %s on %s: %s", instrument, entry_date, exc)
            label = "UNKNOWN"

        result.append({**entry, "regime_tag": label})

    tagged = sum(1 for r in result if r.get("regime_tag") != "UNKNOWN")
    log.info("Regime classification: %d/%d days tagged (instrument=%s)",
             tagged, len(result), instrument)
    return result


def build_date_regime_map(
    instrument: str,
    start_date: str,
    end_date: str,
) -> dict[str, str]:
    """
    Fetch OHLC for the given range (with warmup) and classify each trading day.
    Returns {date_str: regime_label} for all dates within [start_date, end_date].
    Intended for optimizer scoring — called once per optimization, not once per child run.
    """
    warmup_start = (
        date.fromisoformat(start_date) - timedelta(days=_WARMUP_DAYS)
    ).isoformat()
    try:
        ohlc_df = get_ohlc(instrument, warmup_start, end_date)
    except Exception as exc:
        log.warning("build_date_regime_map: OHLC fetch failed for %s: %s", instrument, exc)
        return {}

    if ohlc_df.empty:
        return {}

    result: dict[str, str] = {}
    for ts in ohlc_df.index:
        date_str = str(ts.date())
        if date_str < start_date or date_str > end_date:
            continue
        window = ohlc_df[ohlc_df.index <= ts].tail(_WINDOW_SIZE)
        if len(window) < _WINDOW_SIZE:
            result[date_str] = "UNKNOWN"
        else:
            try:
                result[date_str] = classify_regime(window, window)
            except Exception:
                result[date_str] = "UNKNOWN"

    log.info("build_date_regime_map: %d trading days classified for %s [%s, %s]",
             len(result), instrument, start_date, end_date)
    return result


# ── Backfill tracker ─────────────────────────────────────────────────────────

_backfill_jobs: dict[str, dict] = {}


def get_backfill_status(run_id: str) -> dict:
    return _backfill_jobs.get(run_id, {"status": "idle", "tagged": 0, "total": 0})


async def run_backfill(
    run_id: str,
    instrument: str,
    start_date: str,
    end_date: str,
    daily_pnl_path: Path,
) -> None:
    _backfill_jobs[run_id] = {"status": "running", "tagged": 0, "total": 0}
    try:
        raw: list[dict] = json.loads(daily_pnl_path.read_text())
    except Exception as exc:
        log.warning("Backfill: could not read daily_pnl for %s: %s", run_id, exc)
        _backfill_jobs[run_id] = {"status": "failed", "tagged": 0, "total": 0}
        return

    _backfill_jobs[run_id]["total"] = len(raw)
    tagged = await asyncio.to_thread(
        _tag_daily_pnl_with_regime,
        instrument,
        start_date,
        end_date,
        raw,
    )
    daily_pnl_path.write_text(json.dumps(tagged, default=str))
    n_tagged = sum(1 for r in tagged if r.get("regime_tag") != "UNKNOWN")
    _backfill_jobs[run_id] = {"status": "complete", "tagged": n_tagged, "total": len(tagged)}
    log.info("Backfill complete for %s: %d/%d days tagged", run_id, n_tagged, len(tagged))


# ── Completion path ────────────────────────────────────────────────────────────

async def _handle_complete(
    run_id: str,
    job_id: str,
    strategy_id: str,
    instrument: str,
    firm_ids: list[str],
) -> None:
    try:
        result = await asyncio.to_thread(vps_client.job_results, job_id)
    except Exception as exc:
        _fail(run_id, job_id, "failed_unknown", f"Could not fetch results from agent: {exc}")
        return

    kpis         = result.get("kpis", {})
    equity_curve = result.get("equity_curve", [])
    daily_pnl    = result.get("daily_pnl", [])

    # persist JSON files
    run_dir = _LAB_RESULTS_DIR / run_id
    run_dir.mkdir(parents=True, exist_ok=True)
    equity_path   = run_dir / "equity_curve.json"
    daily_pnl_path = run_dir / "daily_pnl.json"
    equity_path.write_text(json.dumps(equity_curve, default=str))
    daily_pnl_path.write_text(json.dumps(daily_pnl, default=str))

    lab_db.update_run_complete(run_id, kpis, {
        "equity_curve": str(equity_path),
        "trades":       None,
        "daily_pnl":    str(daily_pnl_path),
    })

    evaluator.evaluate_run(run_id, firm_ids, kpis, equity_curve, daily_pnl)

    w = worthiness.score_run_after_evals(
        run_id, firm_ids,
        kpis.get("profit_factor"), kpis.get("max_drawdown"), kpis.get("trade_count"),
    )
    if w:
        lab_db.update_run_worthiness(run_id, w[0], w[1], w[2])

    # Auto-trigger Monte Carlo stress test on Tier 1 results
    if w and w[0] == "TIER_1_STRESS_TEST":
        from services import stress_tester
        asyncio.create_task(stress_tester.trigger_auto_stress_test(run_id, firm_ids))

    # Regime classification — tag each daily_pnl entry with its regime label
    run_row = lab_db.get_run(run_id)
    if run_row and daily_pnl:
        tagged_pnl = await asyncio.to_thread(
            _tag_daily_pnl_with_regime,
            instrument,
            run_row.get("start_date", ""),
            run_row.get("end_date", ""),
            daily_pnl,
        )
        daily_pnl_path.write_text(json.dumps(tagged_pnl, default=str))

    _write_progress({
        "job_id":               job_id,
        "job_type":             "backtest",
        "status":               "complete",
        "strategy_id":          strategy_id,
        "instrument":           instrument,
        "pct":                  100,
        "message":              "Complete",
        "started_at":           None,
        "updated_at":           str(time.time()),
        "heartbeat_age_seconds": 0.0,
        "error_message":        None,
    })


# ── Main poller ────────────────────────────────────────────────────────────────

async def run_backtest_job(
    run_id:      str,
    job_id:      str,
    strategy_id: str,
    instrument:  str,
    firm_ids:    list[str],
) -> None:
    started_at = time.time()
    stall_warned = False

    _write_progress({
        "job_id":               job_id,
        "job_type":             "backtest",
        "status":               "running",
        "strategy_id":          strategy_id,
        "instrument":           instrument,
        "pct":                  0,
        "message":              "Waiting for VPS…",
        "started_at":           str(started_at),
        "updated_at":           str(started_at),
        "heartbeat_age_seconds": 0.0,
        "error_message":        None,
    })

    while True:
        await asyncio.sleep(_POLL_INTERVAL)

        try:
            status_data = await asyncio.to_thread(vps_client.job_status, job_id)
        except Exception as exc:
            elapsed = time.time() - started_at
            if elapsed > _STALL_KILL_SEC:
                _fail(run_id, job_id, "failed_timeout",
                      f"Lost contact with VPS agent after {elapsed:.0f}s: {exc}")
                return
            # transient network error — keep trying
            continue

        status     = status_data.get("status", "running")
        pct        = status_data.get("pct", 0)
        message    = status_data.get("message", "")
        updated_at = status_data.get("updated_at", time.time())

        now = time.time()
        try:
            heartbeat_age = now - float(updated_at)
        except Exception:
            heartbeat_age = 0.0

        if heartbeat_age > _STALL_WARN_SEC and not stall_warned:
            stall_warned = True
            message = f"[STALL] No agent heartbeat for {int(heartbeat_age)}s"

        _write_progress({
            "job_id":               job_id,
            "job_type":             "backtest",
            "status":               "running" if not status.startswith("failed") else status,
            "strategy_id":          strategy_id,
            "instrument":           instrument,
            "pct":                  pct,
            "message":              message,
            "started_at":           str(started_at),
            "updated_at":           str(now),
            "heartbeat_age_seconds": heartbeat_age,
            "error_message":        None,
        })

        if status == "complete":
            await _handle_complete(run_id, job_id, strategy_id, instrument, firm_ids)
            return

        if status.startswith("failed"):
            _fail(run_id, job_id, status, status_data.get("error") or message)
            return

        # kill if stalled too long
        if heartbeat_age > _STALL_KILL_SEC or (now - started_at) > _STALL_KILL_SEC:
            try:
                await asyncio.to_thread(vps_client.cancel_job, job_id)
            except Exception:
                pass
            _fail(run_id, job_id, "failed_timeout",
                  f"No heartbeat for {int(heartbeat_age)}s — job cancelled")
            return
