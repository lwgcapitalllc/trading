"""
Smart Money router — /smart-money/*

GET endpoints read real pipeline output files (implemented in build step 4).
Config endpoints (read/validate-write/git-status) are also fully implemented.
POST /run is a 501 stub — backend implementation deferred.
"""

from __future__ import annotations

import json
import subprocess
from datetime import datetime
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, HTTPException
from pydantic import ValidationError

import config as cfg
from models import (
    SmartMoneyRun,
    SmartMoneyRunSummary,
    SmartMoneyConfig,
    ConfigGitStatus,
    Candidate,
    DisqualifiedCandidate,
)

router = APIRouter(prefix="/smart-money", tags=["smart-money"])


# ── Helpers ───────────────────────────────────────────────────────────────────

def _pipeline_cfg_to_api(raw: dict) -> SmartMoneyConfig:
    """Map the pipeline's config.json structure to the API model (fractional → pct)."""
    q = raw.get("qualification", {})
    lb = raw.get("lookback", {})
    sc = raw.get("scoring", {})
    w = sc.get("weights", {})
    st = raw.get("strike_system", {})

    return SmartMoneyConfig(
        min_trades=q.get("min_trades", 100),
        min_win_rate_pct=round(q.get("min_win_rate", 0.80) * 100, 4),
        max_drawdown_pct=round(q.get("max_drawdown", 0.20) * 100, 4),
        min_active_weeks_per_month=q.get("min_active_weeks_per_month", 2),
        max_single_trade_pnl_share_pct=round(q.get("max_single_trade_pnl_share", 0.40) * 100, 4),
        max_avg_hold_hours=q.get("max_avg_hold_hours", 72),
        min_account_age_days=q.get("min_wallet_age_days", 90),
        lookback_min_days=lb.get("minimum_days", 90),
        lookback_preferred_days=lb.get("preferred_days", 180),
        lookback_elite_days=lb.get("elite_days", 365),
        weight_winrate_consistency=round(w.get("win_rate_consistency", 0.25) * 100, 4),
        weight_risk_adjusted_return=round(w.get("risk_adjusted_return", 0.25) * 100, 4),
        weight_exit_efficiency=round(w.get("exit_efficiency", 0.20) * 100, 4),
        weight_trade_frequency=round(w.get("trade_frequency", 0.15) * 100, 4),
        weight_instrument_consistency=round(w.get("instrument_day_consistency", 0.15) * 100, 4),
        strike_months_to_yellow=st.get("yellow_flag_threshold", 1),
        strike_months_to_disqualify=st.get("disqualify_consecutive_months", 2),
        strike_months_to_reinstate=st.get("reinstate_consecutive_months", 2),
    )


def _api_cfg_to_pipeline(api_cfg: SmartMoneyConfig, existing_raw: dict) -> dict:
    """Merge API model back into the pipeline config dict (pct → fractional)."""
    raw = dict(existing_raw)
    raw["qualification"] = dict(raw.get("qualification", {}))
    raw["qualification"].update({
        "min_trades": api_cfg.min_trades,
        "min_win_rate": round(api_cfg.min_win_rate_pct / 100, 6),
        "max_drawdown": round(api_cfg.max_drawdown_pct / 100, 6),
        "min_active_weeks_per_month": api_cfg.min_active_weeks_per_month,
        "max_single_trade_pnl_share": round(api_cfg.max_single_trade_pnl_share_pct / 100, 6),
        "max_avg_hold_hours": api_cfg.max_avg_hold_hours,
        "min_wallet_age_days": api_cfg.min_account_age_days,
    })
    raw["lookback"] = dict(raw.get("lookback", {}))
    raw["lookback"].update({
        "minimum_days": api_cfg.lookback_min_days,
        "preferred_days": api_cfg.lookback_preferred_days,
        "elite_days": api_cfg.lookback_elite_days,
    })
    raw["scoring"] = dict(raw.get("scoring", {}))
    raw["scoring"]["weights"] = {
        "win_rate_consistency": round(api_cfg.weight_winrate_consistency / 100, 6),
        "risk_adjusted_return": round(api_cfg.weight_risk_adjusted_return / 100, 6),
        "exit_efficiency": round(api_cfg.weight_exit_efficiency / 100, 6),
        "trade_frequency": round(api_cfg.weight_trade_frequency / 100, 6),
        "instrument_day_consistency": round(api_cfg.weight_instrument_consistency / 100, 6),
    }
    raw["strike_system"] = dict(raw.get("strike_system", {}))
    raw["strike_system"].update({
        "yellow_flag_threshold": api_cfg.strike_months_to_yellow,
        "disqualify_consecutive_months": api_cfg.strike_months_to_disqualify,
        "reinstate_consecutive_months": api_cfg.strike_months_to_reinstate,
    })
    return raw


def _validate_config_logic(c: SmartMoneyConfig) -> None:
    """Business-rule validation beyond field-level checks."""
    weight_sum = (
        c.weight_winrate_consistency + c.weight_risk_adjusted_return +
        c.weight_exit_efficiency + c.weight_trade_frequency + c.weight_instrument_consistency
    )
    if abs(weight_sum - 100.0) > 0.01:
        raise HTTPException(
            status_code=422,
            detail=f"Scoring weights must sum to 100 (got {weight_sum:.2f})"
        )
    if not (c.lookback_min_days <= c.lookback_preferred_days <= c.lookback_elite_days):
        raise HTTPException(
            status_code=422,
            detail="Lookback tiers must be ordered: min ≤ preferred ≤ elite"
        )


def _list_run_dirs() -> list[Path]:
    """Return sorted list of run output directories, newest first."""
    reports_dir = cfg.SMART_MONEY_REPORTS_DIR
    if not reports_dir.exists():
        return []
    dirs = [d for d in reports_dir.iterdir() if d.is_dir()]
    dirs.sort(key=lambda d: d.name, reverse=True)
    return dirs


def _load_run(run_id: str) -> dict:
    run_dir = cfg.SMART_MONEY_REPORTS_DIR / run_id
    report_path = run_dir / "full_report.json"
    if not report_path.exists():
        raise HTTPException(status_code=404, detail=f"Run '{run_id}' not found")
    with open(report_path) as f:
        return json.load(f)


# ── Runs ──────────────────────────────────────────────────────────────────────

@router.get("/runs", response_model=list[SmartMoneyRunSummary])
def list_runs():
    dirs = _list_run_dirs()
    summaries: list[SmartMoneyRunSummary] = []
    for d in dirs:
        report = d / "full_report.json"
        if not report.exists():
            continue
        try:
            with open(report) as f:
                data = json.load(f)
            summaries.append(SmartMoneyRunSummary(
                run_id=d.name,
                generated_at=datetime.fromisoformat(data.get("generated_at", d.name)),
                total_qualified=data.get("total_qualified", 0),
            ))
        except Exception:
            pass
    return summaries


@router.get("/runs/{run_id}", response_model=SmartMoneyRun)
def get_run(run_id: str):
    data = _load_run(run_id)
    try:
        return SmartMoneyRun(**data)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to parse run data: {e}")


@router.get("/runs/{run_id}/candidates", response_model=list[Candidate])
def list_candidates(run_id: str):
    data = _load_run(run_id)
    candidates = data.get("candidates", [])
    try:
        return [Candidate(**c) for c in candidates]
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to parse candidates: {e}")


@router.get("/runs/{run_id}/candidates/{candidate_id}", response_model=Candidate)
def get_candidate(run_id: str, candidate_id: str):
    data = _load_run(run_id)
    for c in data.get("candidates", []):
        if c.get("id") == candidate_id:
            return Candidate(**c)
    raise HTTPException(status_code=404, detail=f"Candidate '{candidate_id}' not found in run '{run_id}'")


@router.get("/runs/{run_id}/disqualified", response_model=list[DisqualifiedCandidate])
def list_disqualified(run_id: str):
    run_dir = cfg.SMART_MONEY_REPORTS_DIR / run_id
    disq_path = run_dir / "disqualified.json"
    if not disq_path.exists():
        return []
    with open(disq_path) as f:
        data = json.load(f)
    try:
        return [DisqualifiedCandidate(**d) for d in data]
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to parse disqualified log: {e}")


# ── Config ────────────────────────────────────────────────────────────────────

@router.get("/config", response_model=SmartMoneyConfig)
def get_config():
    if not cfg.SMART_MONEY_CONFIG_PATH.exists():
        raise HTTPException(status_code=404, detail="Smart money config file not found")
    with open(cfg.SMART_MONEY_CONFIG_PATH) as f:
        raw = json.load(f)
    return _pipeline_cfg_to_api(raw)


@router.put("/config", response_model=SmartMoneyConfig)
def update_config(body: SmartMoneyConfig):
    _validate_config_logic(body)
    if not cfg.SMART_MONEY_CONFIG_PATH.exists():
        raise HTTPException(status_code=404, detail="Smart money config file not found")
    with open(cfg.SMART_MONEY_CONFIG_PATH) as f:
        existing = json.load(f)
    merged = _api_cfg_to_pipeline(body, existing)
    with open(cfg.SMART_MONEY_CONFIG_PATH, "w") as f:
        json.dump(merged, f, indent=2)
        f.write("\n")
    return body


@router.get("/config/git-status", response_model=ConfigGitStatus)
def config_git_status():
    path = cfg.SMART_MONEY_CONFIG_PATH
    if not path.exists():
        raise HTTPException(status_code=404, detail="Smart money config file not found")

    # Check if file has uncommitted changes
    result = subprocess.run(
        ["git", "status", "--porcelain", str(path)],
        capture_output=True, text=True,
        cwd=cfg.MONOREPO_ROOT,
    )
    is_dirty = bool(result.stdout.strip())

    # Get last commit info for this file
    log_result = subprocess.run(
        ["git", "log", "-1", "--format=%H%n%s%n%ai", "--", str(path)],
        capture_output=True, text=True,
        cwd=cfg.MONOREPO_ROOT,
    )
    lines = log_result.stdout.strip().splitlines()
    commit_hash = lines[0] if len(lines) > 0 else None
    commit_msg = lines[1] if len(lines) > 1 else None
    commit_at: Optional[datetime] = None
    if len(lines) > 2:
        try:
            commit_at = datetime.fromisoformat(lines[2].strip().replace(" ", "T", 1))
        except Exception:
            pass

    return ConfigGitStatus(
        file_path=str(path),
        is_dirty=is_dirty,
        last_commit_hash=commit_hash,
        last_commit_message=commit_msg,
        last_commit_at=commit_at,
    )


# ── Pipeline trigger (stub) ───────────────────────────────────────────────────

@router.post("/run", status_code=501)
def run_pipeline(stage: Optional[str] = None):
    return {
        "status": "not_implemented",
        "message": "Pipeline trigger not yet implemented. Use run_stage*.py scripts directly.",
    }
