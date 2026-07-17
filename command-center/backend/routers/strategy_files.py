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

from fastapi import APIRouter, HTTPException, UploadFile, File, Form
from models import StrategyFile, StrategyFileSyncStatus, CompileJobStatus
from services import runner_dispatch, lab_db, mt5_agent_client, strategy_scanner
import config as cfg

router = APIRouter(prefix="/strategy-files", tags=["strategy-files"])

_MAX_UPLOAD_BYTES = 256 * 1024  # 256 KB — matches VPS agent limit


@router.get("", response_model=list[StrategyFile])
def list_strategy_files():
    files: list[dict] = []
    try:
        for f in runner_dispatch.list_strategy_files():
            f["platform"] = "NT8"
            files.append(f)
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"NT8 agent: {exc}")
    try:
        for f in mt5_agent_client.list_strategy_files():
            f["platform"] = "MT5"
            files.append(f)
    except Exception:
        pass  # MT5 agent down — degrade gracefully, show NT8 files only
    return files


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


@router.get("/sync-status", response_model=list[StrategyFileSyncStatus])
def sync_status():
    """
    For each strategy in the DB, report whether its source file exists on the VPS.
    NT8 strategies (.cs) are checked against the NT8 agent; MT5 strategies (.mq5)
    are checked against the MT5 agent.
    """
    try:
        nt8_files = {f["filename"]: f for f in runner_dispatch.list_strategy_files()}
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"Could not reach VPS agent: {exc}")

    mt5_files: dict[str, dict] = {}
    try:
        mt5_files = {f["filename"]: f for f in mt5_agent_client.list_strategy_files()}
    except Exception:
        pass  # MT5 agent unreachable — degrade gracefully, MT5 strategies show not-in-sync

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
        vps_file = (mt5_files if is_mt5 else nt8_files).get(expected)
        if is_mt5:
            is_compiled = mt5_files.get(f"{class_name}.ex5") is not None
        else:
            is_compiled = bool(s.get("is_compiled", 1))

        # Current content hash, read LIVE from disk so a local edit is detected
        # immediately — no re-scan needed. Register the version so it always resolves.
        current_hash = None
        source_path = s.get("source_path")
        if source_path:
            fp = monorepo_root / source_path
            if fp.exists():
                current_hash = strategy_scanner.source_hash(
                    fp.read_text(encoding="utf-8", errors="replace"))
                lab_db.ensure_strategy_version(strategy_id, current_hash, fp.stat().st_size)

        deployed_hash = s.get("deployed_source_hash")
        compiled_hash = s.get("compiled_source_hash")

        # Content-based staleness — the whole point of this endpoint.
        # needs_deploy: local source differs from what's on the VPS (or never deployed).
        # needs_compile: deployed source hasn't been compiled (only meaningful once deployed).
        needs_deploy = (current_hash is not None) and (current_hash != deployed_hash)
        needs_compile = (deployed_hash is not None) and (deployed_hash != compiled_hash)

        result.append(StrategyFileSyncStatus(
            strategy_id=strategy_id,
            expected_filename=expected,
            file_exists_on_vps=vps_file is not None,
            file_size_bytes=vps_file["size_bytes"] if vps_file else None,
            file_modified_at=vps_file["modified_at"] if vps_file else None,
            in_sync=(vps_file is not None) and not needs_deploy,
            is_compiled=is_compiled,
            current_version=lab_db.version_for_hash(strategy_id, current_hash),
            current_source_hash=current_hash,
            deployed_version=lab_db.version_for_hash(strategy_id, deployed_hash),
            deployed_at=s.get("deployed_at"),
            compiled_version=lab_db.version_for_hash(strategy_id, compiled_hash),
            compiled_at=s.get("compiled_at"),
            needs_deploy=needs_deploy,
            needs_compile=needs_compile,
        ))
    return result
