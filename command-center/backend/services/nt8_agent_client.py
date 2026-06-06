"""
Dispatcher + NT8 agent client.

This module serves two roles:
  1. NT8 agent client — typed HTTP wrapper over nt8_agent.py at
     http://localhost:8765 (via SSH tunnel). All NT8-specific calls
     (_get/_post, nt_health, nt_log, export_trades, compile, etc.) live here.
  2. Runner dispatcher — start_backtest, job_status, job_results, job_log,
     and cancel_job route to either this module (ninjatrader) or
     mt5_agent_client (mt5) based on the strategy's runner field.

All callers import `nt8_agent_client` and call the same functions regardless of
runner. The dispatcher is transparent to every call site.
"""

from __future__ import annotations

from typing import Optional
import io
import time
import uuid
import urllib.request
import urllib.error
import json

import config as cfg
from services import lab_db
from services import mt5_agent_client

_TIMEOUT = 10  # seconds for all agent calls


def _get(path: str, timeout: int = _TIMEOUT) -> dict:
    url = cfg.NT8_AGENT_TUNNEL.rstrip("/") + path
    try:
        with urllib.request.urlopen(url, timeout=timeout) as r:
            return json.loads(r.read())
    except Exception as exc:
        raise RuntimeError(f"VPS agent {path}: {exc}") from exc


def _post(path: str, body: Optional[dict] = None, timeout: int = _TIMEOUT) -> dict:
    url = cfg.NT8_AGENT_TUNNEL.rstrip("/") + path
    data = json.dumps(body or {}).encode()
    req = urllib.request.Request(url, data=data, headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return json.loads(r.read())
    except Exception as exc:
        raise RuntimeError(f"VPS agent POST {path}: {exc}") from exc


# ── Observability ─────────────────────────────────────────────────────────────

def health() -> dict:
    return _get("/health", timeout=5)


def nt_health() -> dict:
    return _get("/nt-health", timeout=8)


def nt_compile_status() -> dict:
    return _get("/nt-compile-status", timeout=8)


def agent_log(lines: int = 100) -> str:
    try:
        data = _get(f"/agent-log?lines={lines}")
        return data.get("log", "")
    except Exception:
        return ""


def nt_log(lines: int = 100) -> str:
    try:
        data = _get(f"/nt-log?lines={lines}")
        return data.get("log", "")
    except Exception:
        return ""


# ── Foundational config injection ────────────────────────────────────────────

def build_foundational_params(ruleset: dict) -> dict:
    """Return the strategy-param key/value pairs sourced from a ruleset's foundational config.

    These map directly to [Category("Foundational")] NinjaScriptProperty names.
    Call inject_foundational() rather than this directly.
    """
    days = ruleset.get("days_of_week_allowed") or []
    return {
        "AccountSize":          float(ruleset.get("account_size") or 0),
        "RiskPerTradePct":      float(ruleset.get("risk_per_trade_pct") or 0),
        "MaxDailyLoss":         float(ruleset.get("daily_loss_cap") or 0),
        "DailyHaltFraction":    float(ruleset.get("daily_halt_fraction") or 0),
        "MaxConsecutiveLosses": int(ruleset.get("max_consecutive_losses") or 0),
        "CommissionPerSide":    float(ruleset.get("default_commission_per_side") or 0),
        "ForceFlatTimeET":      ruleset.get("force_flat_time_et") or "",
        "EarliestEntryTimeET":  ruleset.get("earliest_entry_time_et") or "",
        "LatestEntryTimeET":    ruleset.get("latest_entry_time_et") or "",
        "DaysOfWeekAllowed":    ",".join(days) if isinstance(days, list) else (days or ""),
        "DailyProfitTarget":    float(ruleset.get("daily_profit_target") or 0),
        "DailyProfitLockPct":   float(ruleset.get("daily_profit_lock_pct") or 0),
    }


def inject_foundational(user_params: dict, ruleset: Optional[dict]) -> dict:
    """Merge foundational config from ruleset into user-provided strategy params.

    Primary ruleset rule: only the primary (first evaluate) ruleset injects config.
    User-provided strategy-logic params override foundational if names collide
    (the UI prevents this in practice by hiding foundational params from users).
    Returns user_params unchanged when ruleset is None (backward compat for
    strategies that don't use foundational config, or runs with no evaluate list).
    """
    if ruleset is None:
        return user_params
    merged = build_foundational_params(ruleset)
    merged.update(user_params)
    return merged


# ── Runner dispatcher ─────────────────────────────────────────────────────────

def _resolve_runner(job_id: str, explicit_runner: Optional[str] = None) -> str:
    """Return the runner for a job, preferring an explicit value over a DB lookup.

    Falls back to "ninjatrader" when the job_id isn't in the DB (legacy rows
    predate the runner column on strategies, or the strategy was deleted).
    """
    if explicit_runner:
        return explicit_runner
    run = lab_db.get_run(job_id)
    if run and run.get("runner"):
        return run["runner"]
    return "ninjatrader"


# ── Job control ───────────────────────────────────────────────────────────────

def _nt8_to_mt5_spec(spec: dict) -> dict:
    """
    Translate the NT8-style job_spec to the MT5 agent's expected format.
    NT8: instrument, params, start_date/end_date, bar_type/bar_value
    MT5: symbol, inputs, from_date/to_date, timeframe, deposit, currency, leverage

    job_id is passed through so the MT5 agent stores the job under our run_id —
    without this the agent generates its own UUID and status polls return 404.
    """
    bar_type  = spec.get("bar_type", "Minute")
    bar_value = int(spec.get("bar_value") or 60)

    if bar_type == "Day":
        timeframe = "D1"
    elif bar_type == "Minute":
        if bar_value >= 240:
            timeframe = "H4"
        elif bar_value >= 60:
            timeframe = "H1"
        elif bar_value >= 30:
            timeframe = "M30"
        elif bar_value >= 15:
            timeframe = "M15"
        elif bar_value >= 5:
            timeframe = "M5"
        else:
            timeframe = "M1"
    else:
        timeframe = "H1"

    params = spec.get("params", {})
    # Derive deposit from foundational param if present (MT5 uses f_ prefix convention)
    deposit = float(
        params.get("f_AccountSize") or params.get("AccountSize") or 10000
    )

    # MeanReversion.mq5 (and all MT5 EAs) call ValidateFoundationalParams() in OnInit and
    # return INIT_FAILED if any f_ param is still at its sentinel value of -1.
    # MT5 backtests have no ruleset, so inject_foundational is never called — provide
    # sensible standalone defaults here. User strategy params override these.
    foundational_defaults = {
        "f_AccountSize":           deposit,
        "f_RiskPerTradePct":       1.0,
        "f_DailyLossCap":          round(deposit * 0.05, 2),
        "f_DailyHaltFraction":     0.6,
        "f_MaxConsecutiveLosses":  0,    # 0 = disabled
        "f_DailyProfitTarget":     0,    # 0 = disabled
        "f_DailyProfitLockPct":    0,    # 0 = disabled
        "f_BrokerToEtOffsetHours": 99,   # 99 = auto-detect
        "f_CommissionPerSide":     float(spec.get("commission_per_side") or 0),
        "f_SlippageTicks":         int(spec.get("slippage_ticks") or 0),
    }
    inputs = {**foundational_defaults, **params}

    return {
        "job_id":         spec.get("job_id"),
        "strategy_class": spec["strategy_class"],
        "symbol":         spec["instrument"],
        "timeframe":      timeframe,
        "from_date":      spec["start_date"],
        "to_date":        spec["end_date"],
        "model":          0,
        "deposit":        deposit,
        "currency":       "USD",
        "leverage":       100,
        "inputs":         inputs,
    }


def start_backtest(job_spec: dict, runner: str = "ninjatrader") -> dict:
    """Submit a backtest job. Routes to the NT8 or MT5 agent based on runner."""
    if runner == "ninjatrader":
        return _post("/backtest", job_spec, timeout=30)
    elif runner == "mt5":
        return mt5_agent_client.start_backtest(_nt8_to_mt5_spec(job_spec))
    else:
        raise ValueError(f"Unknown runner: {runner!r}")


def _normalize_mt5_status(raw: dict) -> dict:
    """
    MT5 agent uses "done"/"cancelled"; polling loop expects "complete"/"failed_*".
    Sets updated_at to now so the heartbeat stall detector sees a live agent response.
    """
    status = raw.get("status", "running")
    if status == "done":
        status = "complete"
    elif status == "cancelled":
        status = "failed_cancelled"
    return {
        "status":     status,
        "pct":        100 if status == "complete" else 30,
        "message":    raw.get("error", "") or ("MT5 Strategy Tester running…" if status not in ("complete", "failed_cancelled") else ""),
        "updated_at": str(time.time()),
        "error":      raw.get("error"),
    }


def job_status(job_id: str, runner: Optional[str] = None) -> dict:
    if _resolve_runner(job_id, runner) == "mt5":
        return _normalize_mt5_status(mt5_agent_client.job_status(job_id))
    return _get(f"/jobs/{job_id}/status")


def _normalize_mt5_results(raw: dict) -> dict:
    """MT5 agent returns KPIs flat; translate to the NT8 nested {kpis, equity_curve, daily_pnl} shape."""
    _KPI_KEYS = {"net_pnl", "profit_factor", "win_rate", "max_drawdown", "sharpe", "trade_count"}
    trades = raw.get("trades", [])

    # Compute avg_win / avg_loss from the trades list (MT5 agent doesn't report these)
    profits = [t["profit"] for t in trades if "profit" in t]
    wins   = [p for p in profits if p > 0]
    losses = [p for p in profits if p < 0]
    kpis   = {k: raw[k] for k in _KPI_KEYS if k in raw}
    if wins:
        kpis["avg_win"]  = round(sum(wins)   / len(wins),   2)
    if losses:
        kpis["avg_loss"] = round(sum(losses) / len(losses), 2)

    # Build a timestamp → {direction, profit} map so equity curve points at trade-close
    # timestamps get direction/profit fields (used by the Long vs Short pie charts).
    _DIR = {"buy": "Long", "sell": "Short"}
    trade_by_ts: dict[str, dict] = {}
    for t in trades:
        ts = t.get("time", "")
        if ts and t.get("direction"):
            trade_by_ts[ts] = t

    equity_curve = []
    for i, pt in enumerate(raw.get("equity_curve", [])):
        ep: dict = {"index": i, **pt}
        td = trade_by_ts.get(pt.get("date", ""))
        if td:
            ep["direction"] = _DIR.get(td["direction"].lower(), td["direction"].capitalize())
            ep["profit"]    = td.get("profit")
        equity_curve.append(ep)

    return {
        "kpis":         kpis,
        "equity_curve": equity_curve,
        "daily_pnl":    raw.get("daily_pnl", []),
        "trades":       trades,
    }


def job_results(job_id: str, runner: Optional[str] = None) -> dict:
    if _resolve_runner(job_id, runner) == "mt5":
        return _normalize_mt5_results(mt5_agent_client.job_results(job_id))
    return _get(f"/jobs/{job_id}/results")


def job_log(job_id: str, lines: int = 200, runner: Optional[str] = None) -> str:
    if _resolve_runner(job_id, runner) == "mt5":
        return mt5_agent_client.job_log(job_id, lines)
    try:
        data = _get(f"/jobs/{job_id}/log?lines={lines}")
        return data.get("log", "")
    except Exception:
        return ""


def cancel_job(job_id: str, runner: Optional[str] = None) -> dict:
    if _resolve_runner(job_id, runner) == "mt5":
        return mt5_agent_client.cancel_job(job_id)
    return _post(f"/jobs/{job_id}/cancel")


def export_trades() -> dict:
    """Call /export-trades on the VPS agent. Returns {ok, csv, total_lines, log}.
    Longer timeout because the export automation takes ~12-15s."""
    return _get("/export-trades", timeout=60)


# ── Strategy file management ──────────────────────────────────────────────────

def list_strategy_files() -> list[dict]:
    return _get("/files/strategies")


def upload_strategy_file(filename: str, content: bytes, overwrite: bool) -> dict:
    if filename.endswith(".mq5"):
        return mt5_agent_client.upload_strategy_file(filename, content, overwrite)
    url = cfg.NT8_AGENT_TUNNEL.rstrip("/") + f"/files/strategies/{filename}"
    boundary = uuid.uuid4().hex
    body_parts = [
        f"--{boundary}\r\nContent-Disposition: form-data; name=\"file\"; "
        f"filename=\"{filename}\"\r\nContent-Type: application/octet-stream\r\n\r\n".encode(),
        content,
        f"\r\n--{boundary}\r\nContent-Disposition: form-data; name=\"overwrite\"\r\n\r\n"
        f"{'true' if overwrite else 'false'}\r\n--{boundary}--\r\n".encode(),
    ]
    body = b"".join(body_parts)
    req = urllib.request.Request(
        url, data=body,
        headers={"Content-Type": f"multipart/form-data; boundary={boundary}"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            return json.loads(r.read())
    except urllib.error.HTTPError as exc:
        raise RuntimeError(f"Upload {filename}: HTTP {exc.code} — {exc.read().decode()}") from exc
    except Exception as exc:
        raise RuntimeError(f"Upload {filename}: {exc}") from exc


def delete_strategy_file(filename: str) -> dict:
    if filename.endswith((".mq5", ".ex5")):
        return mt5_agent_client.delete_strategy_file(filename)
    url = cfg.NT8_AGENT_TUNNEL.rstrip("/") + f"/files/strategies/{filename}"
    req = urllib.request.Request(url, method="DELETE")
    try:
        with urllib.request.urlopen(req, timeout=10) as r:
            return json.loads(r.read())
    except urllib.error.HTTPError as exc:
        raise RuntimeError(f"Delete {filename}: HTTP {exc.code} — {exc.read().decode()}") from exc
    except Exception as exc:
        raise RuntimeError(f"Delete {filename}: {exc}") from exc


def trigger_compile() -> dict:
    return _post("/compile", timeout=10)


def get_compile_status(compile_job_id: str) -> dict:
    return _get(f"/compile/{compile_job_id}", timeout=10)
