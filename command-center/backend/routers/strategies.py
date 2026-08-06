"""
Strategies router — /strategies/*
"""

from __future__ import annotations

import uuid
from collections import OrderedDict
from pathlib import Path
from typing import Optional
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from models import Strategy, ScanResult, ReconcileResult, InstrumentSummary, InstrumentResult, DeployJobStatus, StrategyVersion


class StrategyPatch(BaseModel):
    description: Optional[str] = None
from services import lab_db, strategy_scanner, runner_dispatch
import config as cfg

# Deploy is synchronous (the upload finishes inside the request), so a job here
# exists only for the status GET the frontend fires straight after. It is capped
# rather than unbounded: nothing ever removed an entry, so a long-lived backend
# accumulated one dict per deploy for ever.
_DEPLOY_JOB_LIMIT = 50
_deploy_jobs: "OrderedDict[str, dict]" = OrderedDict()

router = APIRouter(prefix="/strategies", tags=["strategies"])


@router.get("", response_model=list[Strategy])
def list_strategies():
    rows = lab_db.list_strategies()
    for r in rows:
        r["needs_scan"] = strategy_scanner.needs_rescan(r)
        # ⚠ Computed here rather than only inside a scan's RESULT. The Reconcile
        # button used to be gated on `scan.data?.orphans`, which is mutation
        # state — so a strategy whose source file had been deleted was invisible
        # on a fresh page load and stayed invisible until somebody happened to
        # press Scan. A standing fact belongs on the row that states it.
        r["is_orphan"] = strategy_scanner.is_orphan(r)
    return rows


@router.post("/scan", response_model=ScanResult)
def scan_strategies():
    return strategy_scanner.scan_strategies()


@router.post("/reconcile", response_model=ReconcileResult)
def reconcile_strategies():
    """Explicit, destructive cleanup: remove every strategy whose source file was
    deleted from the repo — DB row + its deployed file on the VPS NT8/MT5 folder.
    Separate from /scan (read-only) so a routine scan never deletes VPS files."""
    return strategy_scanner.reconcile_strategies()


@router.get("/{strategy_id}/param-types")
def get_param_types(strategy_id: str):
    """Return {paramName: 'int'|'double'} — the optimizer uses it to reject decimal ranges on
    an integer param.

    NT8/MT5 are parsed out of the source FILE. A python strategy has no single source file —
    its `source_path` is the package DIRECTORY — and it needs no parsing anyway: the scanner
    already read the real types off the config dataclass into `param_schema`. Reading them back
    is both correct and cheaper than re-deriving them. (Before this, `read_text()` was called on
    the directory and raised IsADirectoryError → 500 on every python strategy.)
    """
    import re
    row = lab_db.get_strategy(strategy_id)
    if not row:
        raise HTTPException(404, f"Strategy '{strategy_id}' not found")

    if row.get("runner") == "python":
        out: dict[str, str] = {}
        for p in row.get("param_schema") or []:
            t = p.get("type")
            if t in ("int", "float"):
                out[p["name"]] = "int" if t == "int" else "double"
        return out

    source_path = (row.get("source_path") or "") if isinstance(row, dict) else (getattr(row, "source_path", "") or "")
    if not source_path:
        return {}
    full_path = Path(cfg.MONOREPO_ROOT) / source_path
    if not full_path.is_file():
        return {}
    content = full_path.read_text(encoding="utf-8", errors="ignore")
    # Match: public int|double|float PropertyName { get; set; }
    pattern = re.compile(r'\bpublic\s+(int|double|float)\s+(\w+)\s*\{')
    # Also match MQL5 style: input int|double Name
    pattern_mql = re.compile(r'\binput\s+(int|double|float)\s+(\w+)')
    result = {}
    for m in pattern.finditer(content):
        result[m.group(2)] = "int" if m.group(1) == "int" else "double"
    for m in pattern_mql.finditer(content):
        result[m.group(2)] = "int" if m.group(1) == "int" else "double"
    return result


@router.get("/{strategy_id}", response_model=Strategy)
def get_strategy(strategy_id: str):
    row = lab_db.get_strategy(strategy_id)
    if not row:
        raise HTTPException(404, f"Strategy '{strategy_id}' not found")
    row["needs_scan"] = strategy_scanner.needs_rescan(row)
    row["is_orphan"] = strategy_scanner.is_orphan(row)
    return row


@router.patch("/{strategy_id}", response_model=Strategy)
def patch_strategy(strategy_id: str, body: StrategyPatch):
    if not lab_db.get_strategy(strategy_id):
        raise HTTPException(404, f"Strategy '{strategy_id}' not found")
    lab_db.update_strategy_description(strategy_id, body.description or None)
    row = lab_db.get_strategy(strategy_id)
    return row


@router.delete("/{strategy_id}", status_code=204)
def delete_strategy(strategy_id: str):
    if not lab_db.get_strategy(strategy_id):
        raise HTTPException(404, f"Strategy '{strategy_id}' not found")
    # Deleting a strategy removes it everywhere — DB row + the deployed file on
    # the VPS NT8/MT5 folder. VPS delete is best-effort (see remove_strategy).
    strategy_scanner.remove_strategy(strategy_id)


@router.post("/{strategy_id}/deploy", status_code=202)
def deploy_strategy(strategy_id: str):
    strategy = lab_db.get_strategy(strategy_id)
    if not strategy:
        raise HTTPException(404, f"Strategy '{strategy_id}' not found")

    # A python strategy is a PACKAGE DIRECTORY that runs in this process — there
    # is nothing to upload and no VPS folder it belongs in. Without this guard
    # the read_bytes() below hit a directory and raised IsADirectoryError, i.e.
    # an unhandled 500 on a request whose honest answer is "that is not a thing
    # this endpoint does". The UI never offers the button, so it was latent —
    # which is exactly the kind of endpoint that gets called by something else
    # later. Same shape as the guards in `sync_status` and `get_param_types`.
    if strategy.get("runner") == "python":
        raise HTTPException(
            400,
            "Python strategies are not deployed — they run locally in the backend "
            "process. Nothing to upload to the VPS.",
        )

    source_path = strategy.get("source_path")
    if not source_path:
        raise HTTPException(400, "Strategy has no source_path. Set it first or use the Deployed tab to upload manually.")

    file_path = Path(cfg.MONOREPO_ROOT) / source_path
    if not file_path.is_file():
        raise HTTPException(404, f"Source file not found on disk: {source_path}")

    filename = file_path.name
    content = file_path.read_bytes()

    job_id = str(uuid.uuid4())
    _deploy_jobs[job_id] = {
        "deploy_job_id": job_id,
        "strategy_id": strategy_id,
        "status": "running",
        "filename": filename,
        "uploaded_size_bytes": None,
        "error": None,
    }
    while len(_deploy_jobs) > _DEPLOY_JOB_LIMIT:
        _deploy_jobs.popitem(last=False)

    try:
        result = runner_dispatch.upload_strategy_file(filename, content, overwrite=True)
        # Record exactly what content is now on the VPS: register its version and
        # stamp the deployed hash so sync-status can detect future local edits and
        # flag the strategy as needing redeploy (and, after deploy, recompile).
        src_hash = strategy_scanner.source_hash(content.decode("utf-8", errors="replace"))
        class_name = strategy.get("class_name") or strategy_id
        lab_db.ensure_strategy_version(strategy_id, src_hash, len(content))
        lab_db.set_strategy_deployed(class_name, src_hash)
        _deploy_jobs[job_id].update({
            "status": "complete",
            "uploaded_size_bytes": result.get("size_bytes"),
        })
    except RuntimeError as exc:
        msg = str(exc)
        _deploy_jobs[job_id].update({"status": "failed", "error": msg})
        if "HTTP 423" in msg:
            raise HTTPException(423, detail=msg)
        raise HTTPException(502, detail=msg)

    return {"deploy_job_id": job_id, "status": "started"}


@router.get("/{strategy_id}/deploy/{deploy_job_id}", response_model=DeployJobStatus)
def get_deploy_status(strategy_id: str, deploy_job_id: str):
    job = _deploy_jobs.get(deploy_job_id)
    if not job:
        raise HTTPException(404, "Deploy job not found")
    # The path names a strategy, so it has to mean one. Without this any job was
    # readable from any strategy's URL, which makes the path segment decoration.
    if job.get("strategy_id") != strategy_id:
        raise HTTPException(404, "Deploy job not found for this strategy")
    return job


@router.get("/{strategy_id}/versions", response_model=list[StrategyVersion])
def list_versions(strategy_id: str):
    """Version history for a strategy — newest first. Each row is a distinct
    content hash with its monotonic version number."""
    if not lab_db.get_strategy(strategy_id):
        raise HTTPException(404, f"Strategy '{strategy_id}' not found")
    return lab_db.list_strategy_versions(strategy_id)


@router.get("/{strategy_id}/instrument_summary", response_model=InstrumentSummary)
def instrument_summary(
    strategy_id: str,
    ruleset_id:  Optional[str] = None,
    firm_id:     Optional[str] = None,   # backward-compat alias
    start_date:  Optional[str] = None,
    end_date:    Optional[str] = None,
) -> InstrumentSummary:
    """Return best worthiness per instrument for this strategy, and untested instruments."""
    if not lab_db.get_strategy(strategy_id):
        raise HTTPException(404, f"Strategy '{strategy_id}' not found")

    # Collect all allowed instruments from ruleset (or default list)
    rid = ruleset_id or firm_id
    ruleset = lab_db.get_ruleset(rid) if rid else None
    if ruleset and ruleset.get("allowed_instruments"):
        all_instruments = ruleset["allowed_instruments"]
    else:
        all_instruments = ["MES", "MNQ", "MGC", "MCL", "MYM", "M2K"]

    runs = lab_db.list_runs(strategy_id=strategy_id, status="complete")

    TIER_ORDER = {
        "TIER_1_STRESS_TEST": 0,
        "TIER_2_OPTIMIZE":    1,
        "TIER_3_DISCARD":     2,
        None:                 3,
    }

    best_by_instrument: dict[str, dict] = {}
    for run in runs:
        inst = run["instrument"]
        # Strip contract month (e.g. "MES 06-26" → "MES")
        base = inst.split()[0] if " " in inst else inst
        tier = run.get("worthiness_tier")
        if base not in best_by_instrument:
            best_by_instrument[base] = {
                "instrument":      inst,
                "best_worthiness": tier,
                "best_run_id":     run["run_id"],
                "tested_at":       run.get("completed_at"),
            }
        else:
            current_order = TIER_ORDER.get(best_by_instrument[base]["best_worthiness"], 3)
            new_order     = TIER_ORDER.get(tier, 3)
            if new_order < current_order:
                best_by_instrument[base] = {
                    "instrument":      inst,
                    "best_worthiness": tier,
                    "best_run_id":     run["run_id"],
                    "tested_at":       run.get("completed_at"),
                }

    instrument_results = []
    tested_bases: set[str] = set()
    for base, info in best_by_instrument.items():
        tested_bases.add(base)
        instrument_results.append(InstrumentResult(
            instrument=info["instrument"],
            best_worthiness=info["best_worthiness"],
            best_run_id=info["best_run_id"],
            tested_at=info["tested_at"],
        ))

    # Sort by tier (best first)
    instrument_results.sort(key=lambda r: TIER_ORDER.get(r.best_worthiness, 3))

    # Untested instruments (base symbols not yet seen)
    untested = [i for i in all_instruments if i not in tested_bases]

    return InstrumentSummary(
        instrument_results=instrument_results,
        untested_instruments=untested,
    )
