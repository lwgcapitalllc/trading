"""
Typed HTTP wrapper over the VPS agent (http://localhost:8765 via SSH tunnel).
All outbound calls to the agent go through this module.
"""

from __future__ import annotations

from typing import Any, Optional
import io
import uuid
import urllib.request
import urllib.error
import json

import config as cfg

_TIMEOUT = 10  # seconds for all agent calls


def _get(path: str, timeout: int = _TIMEOUT) -> dict:
    url = cfg.VPS_AGENT_TUNNEL.rstrip("/") + path
    try:
        with urllib.request.urlopen(url, timeout=timeout) as r:
            return json.loads(r.read())
    except Exception as exc:
        raise RuntimeError(f"VPS agent {path}: {exc}") from exc


def _post(path: str, body: Optional[dict] = None, timeout: int = _TIMEOUT) -> dict:
    url = cfg.VPS_AGENT_TUNNEL.rstrip("/") + path
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


# ── Job control ───────────────────────────────────────────────────────────────

def _dispatch_backtest(strategy_runner: str, job_spec: dict) -> dict:
    """Route a backtest job to the correct backend based on the strategy's runner field."""
    if strategy_runner == "ninjatrader":
        return _post("/backtest", job_spec, timeout=30)
    elif strategy_runner == "mt5":
        raise NotImplementedError("MT5 runner planned for forex; not built yet")
    else:
        raise ValueError(f"Unknown runner: {strategy_runner!r}")


def start_backtest(job_spec: dict, runner: str = "ninjatrader") -> dict:
    return _dispatch_backtest(runner, job_spec)


def job_status(job_id: str) -> dict:
    return _get(f"/jobs/{job_id}/status")


def job_results(job_id: str) -> dict:
    return _get(f"/jobs/{job_id}/results")


def job_log(job_id: str, lines: int = 200) -> str:
    try:
        data = _get(f"/jobs/{job_id}/log?lines={lines}")
        return data.get("log", "")
    except Exception:
        return ""


def cancel_job(job_id: str) -> dict:
    return _post(f"/jobs/{job_id}/cancel")


def export_trades() -> dict:
    """Call /export-trades on the VPS agent. Returns {ok, csv, total_lines, log}.
    Longer timeout because the export automation takes ~12-15s."""
    return _get("/export-trades", timeout=60)


# ── Strategy file management ──────────────────────────────────────────────────

def list_strategy_files() -> list[dict]:
    return _get("/files/strategies")


def upload_strategy_file(filename: str, content: bytes, overwrite: bool) -> dict:
    url = cfg.VPS_AGENT_TUNNEL.rstrip("/") + f"/files/strategies/{filename}"
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
    url = cfg.VPS_AGENT_TUNNEL.rstrip("/") + f"/files/strategies/{filename}"
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
