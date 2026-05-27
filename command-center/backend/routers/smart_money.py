"""
Smart Money router — /smart-money/*

All endpoints are fully implemented:
- GET /runs, /runs/{id}, /runs/{id}/candidates, /runs/{id}/disqualified — read pipeline output files
- GET /config, PUT /config, GET /config/git-status — config read/write with bidirectional conversion
- GET /progress — polls reports/progress.json written by the pipeline
- POST /run — spawns run_stage1.py as a subprocess (--profile bot|human); 409 guard if already running
- POST /stop — SIGTERMs the pipeline process and resets progress.json to idle
"""

from __future__ import annotations

import json
import os
import signal
import subprocess
from datetime import datetime
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, ValidationError

import config as cfg
from models import (
    SmartMoneyRun,
    SmartMoneyRunSummary,
    SmartMoneyConfig,
    ConfigGitStatus,
    Candidate,
    DisqualifiedCandidate,
    RunProgress,
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
    """Return run directories that have a meta.json, newest first."""
    reports_dir = cfg.SMART_MONEY_REPORTS_DIR
    if not reports_dir.exists():
        return []
    dirs = [d for d in reports_dir.iterdir() if d.is_dir() and (d / "meta.json").exists()]
    dirs.sort(key=lambda d: d.name, reverse=True)
    return dirs


def _load_meta(run_id: str) -> dict:
    meta_path = cfg.SMART_MONEY_REPORTS_DIR / run_id / "meta.json"
    if not meta_path.exists():
        raise HTTPException(status_code=404, detail=f"Run '{run_id}' not found")
    with open(meta_path) as f:
        return json.load(f)


# ── Runs ──────────────────────────────────────────────────────────────────────

@router.get("/runs", response_model=list[SmartMoneyRunSummary])
def list_runs():
    summaries: list[SmartMoneyRunSummary] = []
    for d in _list_run_dirs():
        try:
            with open(d / "meta.json") as f:
                meta = json.load(f)
            summaries.append(SmartMoneyRunSummary(
                run_id=d.name,
                generated_at=meta.get("generated_at", d.name),
                total_qualified=meta.get("total_qualified", 0),
            ))
        except Exception:
            pass
    return summaries


@router.get("/runs/{run_id}", response_model=SmartMoneyRun)
def get_run(run_id: str):
    meta = _load_meta(run_id)
    # Pipeline writes run_id into meta.json — pop it to avoid passing twice
    meta.pop("run_id", None)
    try:
        return SmartMoneyRun(run_id=run_id, **meta)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to parse run data: {e}")


@router.get("/runs/{run_id}/candidates", response_model=list[Candidate])
def list_candidates(run_id: str):
    cand_path = cfg.SMART_MONEY_REPORTS_DIR / run_id / "candidates.json"
    if not cand_path.exists():
        raise HTTPException(status_code=404, detail=f"Run '{run_id}' not found")
    with open(cand_path) as f:
        data = json.load(f)
    try:
        return [Candidate(**c) for c in data]
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to parse candidates: {e}")


@router.get("/runs/{run_id}/candidates/{candidate_id}", response_model=Candidate)
def get_candidate(run_id: str, candidate_id: str):
    cand_path = cfg.SMART_MONEY_REPORTS_DIR / run_id / "candidates.json"
    if not cand_path.exists():
        raise HTTPException(status_code=404, detail=f"Run '{run_id}' not found")
    with open(cand_path) as f:
        data = json.load(f)
    for c in data:
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


# ── Live run progress ─────────────────────────────────────────────────────────

@router.get("/progress", response_model=RunProgress)
def get_progress():
    progress_path = cfg.SMART_MONEY_REPORTS_DIR / "progress.json"
    if not progress_path.exists():
        return RunProgress(
            run_id="", status="idle", stage=0, stage_name="",
            phase="", pct=0, wallets_scanned=0, wallets_total=0,
            qualified_so_far=0, disqualified_so_far=0,
            message="No pipeline run in progress", elapsed_seconds=0.0,
        )
    with open(progress_path) as f:
        data = json.load(f)
    return RunProgress(**data)


# ── Pipeline trigger ─────────────────────────────────────────────────────────

_PID_FILE = cfg.SMART_MONEY_REPORTS_DIR / "pipeline.pid"


class _RunRequest(BaseModel):
    profile: Optional[str] = None  # "bot" | "human" | None (uses config/config.json)


@router.post("/run", status_code=202)
def run_pipeline(body: _RunRequest = None):
    if body is None:
        body = _RunRequest()

    if body.profile is not None and body.profile not in ("bot", "human"):
        raise HTTPException(status_code=422, detail=f"Invalid profile '{body.profile}'. Use 'bot' or 'human'.")

    progress_path = cfg.SMART_MONEY_REPORTS_DIR / "progress.json"
    if progress_path.exists():
        with open(progress_path) as f:
            data = json.load(f)
        if data.get("status") == "running":
            raise HTTPException(status_code=409, detail="Pipeline is already running")

    script = cfg.SMART_MONEY_ROOT / "run_stage1.py"
    log_path = cfg.SMART_MONEY_REPORTS_DIR / "pipeline_run.log"
    log_file = open(log_path, "w")
    # Strip the backend venv from PATH so python3 resolves to the system
    # interpreter that has the smart-money pipeline dependencies.
    clean_env = os.environ.copy()
    clean_env["PATH"] = ":".join(
        p for p in clean_env.get("PATH", "").split(":") if ".venv/bin" not in p
    )
    cmd = ["python3", str(script)]
    if body.profile:
        cmd += ["--profile", body.profile]

    proc = subprocess.Popen(
        cmd,
        cwd=str(cfg.SMART_MONEY_ROOT),
        stdout=log_file,
        stderr=log_file,
        env=clean_env,
    )
    _PID_FILE.write_text(str(proc.pid))
    return {"status": "started", "stage": 1, "profile": body.profile}


@router.post("/stop", status_code=200)
def stop_pipeline():
    progress_path = cfg.SMART_MONEY_REPORTS_DIR / "progress.json"

    pid: int | None = None
    if _PID_FILE.exists():
        try:
            pid = int(_PID_FILE.read_text().strip())
        except ValueError:
            pass

    killed = False
    if pid is not None:
        try:
            os.kill(pid, signal.SIGTERM)
            killed = True
        except ProcessLookupError:
            pass  # already finished
        finally:
            _PID_FILE.unlink(missing_ok=True)

    # Reset progress to idle so the UI clears immediately
    idle = {
        "run_id": "", "status": "idle", "stage": 0, "stage_name": "",
        "phase": "", "pct": 0, "wallets_scanned": 0, "wallets_total": 0,
        "qualified_so_far": 0, "disqualified_so_far": 0, "message": "",
        "started_at": None, "updated_at": None, "elapsed_seconds": 0.0,
    }
    tmp = progress_path.with_suffix(".tmp")
    tmp.write_text(json.dumps(idle))
    os.replace(str(tmp), str(progress_path))

    return {"status": "stopped", "killed": killed}
