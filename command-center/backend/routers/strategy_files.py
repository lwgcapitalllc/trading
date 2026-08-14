"""
Strategy file deployment router.

Proxies VPS agent file management and compile endpoints. Also provides
sync-status: for each strategy in the DB, reports whether its source file
exists on the VPS. NT8 strategies use .cs files (NT8 VPS agent on :8765);
MT5 strategies use .mq5 files (MT5 agent on :8766).

Endpoints:
    GET    /strategy-files                  list .cs (NT8) + .mq5 (MT5) files on VPS
    POST   /strategy-files/upload           upload a .cs or .mq5 file
    DELETE /strategy-files/{filename}       delete a file from VPS
    POST   /strategy-files/compile          trigger NT8 recompile (pywinauto F5)
    GET    /strategy-files/compile/{id}     poll NT8 compile status
    POST   /strategy-files/compile-mt5      trigger MetaEditor compile
    GET    /strategy-files/compile-mt5/{id} poll MT5 compile status
    GET    /strategy-files/sync-status      per-strategy file presence on VPS
"""

from pathlib import Path
from typing import Optional

import config as cfg
from fastapi import APIRouter, File, Form, HTTPException, UploadFile
from models import (
    CompileJobStatus,
    StrategyFile,
    StrategyFilesResponse,
    StrategyFileSyncResponse,
    StrategyFileSyncStatus,
)
from services import lab_db, mt5_agent_client, runner_dispatch, strategy_scanner

router = APIRouter(prefix="/strategy-files", tags=["strategy-files"])

_MAX_UPLOAD_BYTES = 256 * 1024  # 256 KB — matches VPS agent limit


def _list_platform_files():
    """Both agents' file listings, plus whichever failed.

    ⚠ NEITHER FAILURE IS FATAL, and that symmetry is the fix. NT8 used to raise
    a 502 that took the whole response down while an MT5 failure was swallowed
    with a bare `pass` — so one dead platform blanked the other's status too,
    and the page could not tell "the box says there are no files" from "nobody
    asked the box". Both are reported now, and the caller renders the gap.
    """
    files: list[dict] = []
    nt8_error: Optional[str] = None
    mt5_error: Optional[str] = None
    try:
        for f in runner_dispatch.list_strategy_files():
            f["platform"] = "NT8"
            files.append(f)
    except Exception as exc:
        nt8_error = str(exc)
    try:
        for f in mt5_agent_client.list_strategy_files():
            f["platform"] = "MT5"
            files.append(f)
    except Exception as exc:
        mt5_error = str(exc)
    return files, nt8_error, mt5_error


@router.get("", response_model=StrategyFilesResponse)
def list_strategy_files():
    files, nt8_error, mt5_error = _list_platform_files()
    return StrategyFilesResponse(files=files, nt8_error=nt8_error, mt5_error=mt5_error)


@router.post("/upload", response_model=StrategyFile)
async def upload_strategy_file(
    file: UploadFile = File(...),
    filename: str = Form(...),
    overwrite: bool = Form(False),
):
    if not (filename.endswith(".cs") or filename.endswith(".mq5")):
        raise HTTPException(status_code=400, detail="Only .cs or .mq5 files are allowed")

    content = await file.read()
    if len(content) > _MAX_UPLOAD_BYTES:
        raise HTTPException(
            status_code=400,
            detail=f"File exceeds 256 KB limit ({len(content)} bytes)",
        )

    try:
        result = runner_dispatch.upload_strategy_file(filename, content, overwrite)
    except RuntimeError as exc:
        msg = str(exc)
        if "HTTP 409" in msg:
            raise HTTPException(status_code=409, detail=f"{filename} already exists on VPS")
        if "HTTP 423" in msg:
            raise HTTPException(status_code=423, detail=msg)
        raise HTTPException(status_code=502, detail=msg)
    # File uploaded — record the deployed content so sync-status is content-aware
    # (set_strategy_deployed also flags needs-compile). class_name → strategy_id by
    # the scanner's convention (lower-cased), matching .cs and .mq5 registration.
    class_name = filename.rsplit(".", 1)[0]
    src_hash = strategy_scanner.source_hash(content.decode("utf-8", errors="replace"))
    lab_db.ensure_strategy_version(class_name.lower(), src_hash, len(content))
    lab_db.set_strategy_deployed(class_name, src_hash)
    return result


@router.delete("/{filename}")
def delete_strategy_file(filename: str):
    if not (filename.endswith(".cs") or filename.endswith((".mq5", ".ex5"))):
        raise HTTPException(status_code=400, detail="Only .cs, .mq5, or .ex5 files are allowed")
    try:
        return runner_dispatch.delete_strategy_file(filename)
    except RuntimeError as exc:
        msg = str(exc)
        if "HTTP 404" in msg:
            raise HTTPException(status_code=404, detail=f"{filename} not found on VPS")
        if "HTTP 423" in msg:
            raise HTTPException(status_code=423, detail=msg)
        raise HTTPException(status_code=502, detail=msg)


@router.post("/compile", status_code=202)
def trigger_compile():
    try:
        return runner_dispatch.trigger_compile()
    except Exception as exc:
        raise HTTPException(status_code=502, detail=str(exc))


@router.get("/compile/{compile_job_id}", response_model=CompileJobStatus)
def get_compile_status(compile_job_id: str):
    try:
        result = runner_dispatch.get_compile_status(compile_job_id)
    except Exception as exc:
        raise HTTPException(status_code=502, detail=str(exc))
    if result.get("status") == "success":
        lab_db.mark_runner_compiled("ninjatrader")
    return result


@router.post("/compile-mt5", status_code=202)
def trigger_compile_mt5():
    try:
        return mt5_agent_client.trigger_compile()
    except Exception as exc:
        raise HTTPException(status_code=502, detail=str(exc))


@router.get("/compile-mt5/{compile_job_id}", response_model=CompileJobStatus)
def get_compile_mt5_status(compile_job_id: str):
    try:
        result = mt5_agent_client.get_compile_status(compile_job_id)
    except Exception as exc:
        raise HTTPException(status_code=502, detail=str(exc))
    if result.get("status") == "success":
        lab_db.mark_runner_compiled("mt5")
    return result


@router.get("/sync-status", response_model=StrategyFileSyncResponse)
def sync_status():
    """
    For each strategy in the DB, report whether its source file exists on the VPS.
    NT8 strategies (.cs) are checked against the NT8 agent; MT5 strategies (.mq5)
    are checked against the MT5 agent.

    ⚠ AN UNREACHABLE AGENT NO LONGER TAKES THE WHOLE ENDPOINT DOWN. It used to
    502 on any NT8 failure, so the page lost every row — and a row with no sync
    object renders no status pill and a Run button, i.e. a strategy that needs
    deploying looked ready to run. `needs_deploy`/`needs_compile` come from the
    LOCAL hash and this app's own deploy record, so they are answerable with the
    box switched off; only the agent-dependent fields go `None`.
    """
    nt8_files: dict[str, dict] = {}
    mt5_files: dict[str, dict] = {}
    nt8_error: Optional[str] = None
    mt5_error: Optional[str] = None
    try:
        nt8_files = {f["filename"]: f for f in runner_dispatch.list_strategy_files()}
    except Exception as exc:
        nt8_error = str(exc)
    try:
        mt5_files = {f["filename"]: f for f in mt5_agent_client.list_strategy_files()}
    except Exception as exc:
        mt5_error = str(exc)

    strategies = lab_db.list_strategies()
    monorepo_root = Path(cfg.MONOREPO_ROOT)
    result = []
    for s in strategies:
        # A python strategy is never deployed — it runs in this process — so it has no VPS file
        # to be in or out of sync with, and no row here. The UI reads a missing row as "nothing
        # to deploy or compile" and offers Run directly. Including it also CRASHED the endpoint:
        # its source_path is the package directory, and the hash read below does read_text() on
        # it (IsADirectoryError → 500), which took the sync status of EVERY strategy down with it.
        if s.get("runner") == "python":
            continue
        class_name = s.get("class_name") or s.get("id", "")
        strategy_id = s["id"]
        is_mt5 = s.get("runner") == "mt5"
        expected = f"{class_name}.mq5" if is_mt5 else f"{class_name}.cs"
        # Did the agent that owns this platform actually answer? Everything below
        # that reads the file listing is unanswerable when it did not.
        agent_answered = (mt5_error is None) if is_mt5 else (nt8_error is None)
        vps_file = (mt5_files if is_mt5 else nt8_files).get(expected) if agent_answered else None

        if not agent_answered:
            is_compiled = None
        elif is_mt5:
            # MT5 runs the compiled .ex5, so its presence IS the question.
            is_compiled = mt5_files.get(f"{class_name}.ex5") is not None
        else:
            # ⚠ `None`, never a default of 1. `.get("is_compiled", 1)` defaulted a
            # missing column to COMPILED — a fabricated healthy answer, and this
            # repo's own rule against letting an unknown look like a measurement.
            raw_compiled = s.get("is_compiled")
            is_compiled = None if raw_compiled is None else bool(raw_compiled)

        # Current content hash, read LIVE from disk so a local edit is detected
        # immediately — no re-scan needed. Register the version so it always resolves.
        current_hash = None
        source_path = s.get("source_path")
        if source_path:
            fp = monorepo_root / source_path
            if fp.exists():
                current_hash = strategy_scanner.source_hash(
                    fp.read_text(encoding="utf-8", errors="replace")
                )
                lab_db.ensure_strategy_version(strategy_id, current_hash, fp.stat().st_size)

        deployed_hash = s.get("deployed_source_hash")
        compiled_hash = s.get("compiled_source_hash")

        # Content-based staleness — the whole point of this endpoint.
        # needs_deploy: local source differs from what's on the VPS (or never deployed).
        # needs_compile: deployed source hasn't been compiled (only meaningful once deployed).
        needs_deploy = (current_hash is not None) and (current_hash != deployed_hash)
        needs_compile = (deployed_hash is not None) and (deployed_hash != compiled_hash)
        # MT5 loads the .ex5, so a source that matches its deploy record but has
        # no compiled sibling still needs compiling. Reading hashes alone missed
        # that: delete the .ex5 and the row went on reading "In sync".
        if is_mt5 and is_compiled is False and deployed_hash is not None:
            needs_compile = True

        result.append(
            StrategyFileSyncStatus(
                strategy_id=strategy_id,
                expected_filename=expected,
                file_exists_on_vps=(vps_file is not None) if agent_answered else None,
                file_size_bytes=vps_file["size_bytes"] if vps_file else None,
                file_modified_at=vps_file["modified_at"] if vps_file else None,
                in_sync=((vps_file is not None) and not needs_deploy) if agent_answered else None,
                is_compiled=is_compiled,
                current_version=lab_db.version_for_hash(strategy_id, current_hash),
                current_source_hash=current_hash,
                deployed_version=lab_db.version_for_hash(strategy_id, deployed_hash),
                deployed_at=s.get("deployed_at"),
                compiled_version=lab_db.version_for_hash(strategy_id, compiled_hash),
                compiled_at=s.get("compiled_at"),
                needs_deploy=needs_deploy,
                needs_compile=needs_compile,
            )
        )
    return StrategyFileSyncResponse(statuses=result, nt8_error=nt8_error, mt5_error=mt5_error)
