"""
Strategy file deployment router.

Proxies VPS agent file management and compile endpoints. Also provides
sync-status: for each strategy in the DB, reports whether its source file
exists on the VPS. NT8 strategies use .cs files (NT8 VPS agent on :8765);
MT5 strategies use .mq5 files (MT5 agent on :8766).

Endpoints:
    GET    /strategy-files                  list .cs files on NT8 VPS
    POST   /strategy-files/upload           upload a .cs or .mq5 file
    DELETE /strategy-files/{filename}       delete a file from VPS
    POST   /strategy-files/compile          trigger NT8 recompile (pywinauto F5)
    GET    /strategy-files/compile/{id}     poll NT8 compile status
    POST   /strategy-files/compile-mt5      trigger MetaEditor compile
    GET    /strategy-files/compile-mt5/{id} poll MT5 compile status
    GET    /strategy-files/sync-status      per-strategy file presence on VPS
"""

from fastapi import APIRouter, HTTPException, UploadFile, File, Form
from models import StrategyFile, StrategyFileSyncStatus, CompileJobStatus
from services import nt8_agent_client, lab_db, mt5_agent_client

router = APIRouter(prefix="/strategy-files", tags=["strategy-files"])

_MAX_UPLOAD_BYTES = 256 * 1024  # 256 KB — matches VPS agent limit


@router.get("", response_model=list[StrategyFile])
def list_strategy_files():
    try:
        return nt8_agent_client.list_strategy_files()
    except Exception as exc:
        raise HTTPException(status_code=502, detail=str(exc))


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
        return nt8_agent_client.upload_strategy_file(filename, content, overwrite)
    except RuntimeError as exc:
        msg = str(exc)
        if "HTTP 409" in msg:
            raise HTTPException(status_code=409, detail=f"{filename} already exists on VPS")
        if "HTTP 423" in msg:
            raise HTTPException(status_code=423, detail=msg)
        raise HTTPException(status_code=502, detail=msg)


@router.delete("/{filename}")
def delete_strategy_file(filename: str):
    if not (filename.endswith(".cs") or filename.endswith((".mq5", ".ex5"))):
        raise HTTPException(status_code=400, detail="Only .cs, .mq5, or .ex5 files are allowed")
    try:
        return nt8_agent_client.delete_strategy_file(filename)
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
        return nt8_agent_client.trigger_compile()
    except Exception as exc:
        raise HTTPException(status_code=502, detail=str(exc))


@router.get("/compile/{compile_job_id}", response_model=CompileJobStatus)
def get_compile_status(compile_job_id: str):
    try:
        return nt8_agent_client.get_compile_status(compile_job_id)
    except Exception as exc:
        raise HTTPException(status_code=502, detail=str(exc))


@router.post("/compile-mt5", status_code=202)
def trigger_compile_mt5():
    try:
        return mt5_agent_client.trigger_compile()
    except Exception as exc:
        raise HTTPException(status_code=502, detail=str(exc))


@router.get("/compile-mt5/{compile_job_id}", response_model=CompileJobStatus)
def get_compile_mt5_status(compile_job_id: str):
    try:
        return mt5_agent_client.get_compile_status(compile_job_id)
    except Exception as exc:
        raise HTTPException(status_code=502, detail=str(exc))


@router.get("/sync-status", response_model=list[StrategyFileSyncStatus])
def sync_status():
    """
    For each strategy in the DB, report whether its source file exists on the VPS.
    NT8 strategies (.cs) are checked against the NT8 agent; MT5 strategies (.mq5)
    are checked against the MT5 agent.
    """
    try:
        nt8_files = {f["filename"]: f for f in nt8_agent_client.list_strategy_files()}
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"Could not reach VPS agent: {exc}")

    mt5_files: dict[str, dict] = {}
    try:
        mt5_files = {f["filename"]: f for f in mt5_agent_client.list_strategy_files()}
    except Exception:
        pass  # MT5 agent unreachable — degrade gracefully, MT5 strategies show not-in-sync

    strategies = lab_db.list_strategies()
    result = []
    for s in strategies:
        class_name = s.get("class_name") or s.get("id", "")
        is_mt5 = s.get("runner") == "mt5"
        expected = f"{class_name}.mq5" if is_mt5 else f"{class_name}.cs"
        vps_file = (mt5_files if is_mt5 else nt8_files).get(expected)
        result.append(StrategyFileSyncStatus(
            strategy_id=s["id"],
            expected_filename=expected,
            file_exists_on_vps=vps_file is not None,
            file_size_bytes=vps_file["size_bytes"] if vps_file else None,
            file_modified_at=vps_file["modified_at"] if vps_file else None,
            in_sync=vps_file is not None,
        ))
    return result
