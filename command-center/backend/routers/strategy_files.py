"""
Strategy file deployment router.

Proxies VPS agent file management and compile endpoints. Also provides
sync-status: for each strategy in the DB, reports whether its .cs file
exists on the VPS.

Endpoints:
    GET    /strategy-files               list .cs files on VPS
    POST   /strategy-files/upload        upload a .cs file (multipart/form-data)
    DELETE /strategy-files/{filename}    delete a .cs file from VPS
    POST   /strategy-files/compile       trigger NT8 recompile
    GET    /strategy-files/compile/{id}  poll compile status
    GET    /strategy-files/sync-status   per-strategy file presence on VPS
"""

from fastapi import APIRouter, HTTPException, UploadFile, File, Form
from models import StrategyFile, StrategyFileSyncStatus, CompileJobStatus
from services import vps_client, lab_db

router = APIRouter(prefix="/strategy-files", tags=["strategy-files"])

_MAX_UPLOAD_BYTES = 256 * 1024  # 256 KB — matches VPS agent limit


@router.get("", response_model=list[StrategyFile])
def list_strategy_files():
    try:
        return vps_client.list_strategy_files()
    except Exception as exc:
        raise HTTPException(status_code=502, detail=str(exc))


@router.post("/upload", response_model=StrategyFile)
async def upload_strategy_file(
    file: UploadFile = File(...),
    filename: str = Form(...),
    overwrite: bool = Form(False),
):
    if not filename.endswith(".cs"):
        raise HTTPException(status_code=400, detail="Only .cs files are allowed")

    content = await file.read()
    if len(content) > _MAX_UPLOAD_BYTES:
        raise HTTPException(
            status_code=400,
            detail=f"File exceeds 256 KB limit ({len(content)} bytes)",
        )

    try:
        return vps_client.upload_strategy_file(filename, content, overwrite)
    except RuntimeError as exc:
        msg = str(exc)
        if "HTTP 409" in msg:
            raise HTTPException(status_code=409, detail=f"{filename} already exists on VPS")
        if "HTTP 423" in msg:
            raise HTTPException(status_code=423, detail=msg)
        raise HTTPException(status_code=502, detail=msg)


@router.delete("/{filename}")
def delete_strategy_file(filename: str):
    if not filename.endswith(".cs"):
        raise HTTPException(status_code=400, detail="Only .cs files are allowed")
    try:
        return vps_client.delete_strategy_file(filename)
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
        return vps_client.trigger_compile()
    except Exception as exc:
        raise HTTPException(status_code=502, detail=str(exc))


@router.get("/compile/{compile_job_id}", response_model=CompileJobStatus)
def get_compile_status(compile_job_id: str):
    try:
        return vps_client.get_compile_status(compile_job_id)
    except Exception as exc:
        raise HTTPException(status_code=502, detail=str(exc))


@router.get("/sync-status", response_model=list[StrategyFileSyncStatus])
def sync_status():
    """
    For each strategy in the DB, report whether its .cs file exists on the VPS.
    A strategy is "in sync" when the expected .cs file is present on the VPS.
    """
    try:
        vps_files = {f["filename"]: f for f in vps_client.list_strategy_files()}
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"Could not reach VPS agent: {exc}")

    strategies = lab_db.list_strategies()
    result = []
    for s in strategies:
        # Expected filename: <class_name>.cs (class_name comes from the scanner)
        class_name = s.get("class_name") or s.get("id", "")
        expected = f"{class_name}.cs"
        vps_file = vps_files.get(expected)
        result.append(StrategyFileSyncStatus(
            strategy_id=s["id"],
            expected_filename=expected,
            file_exists_on_vps=vps_file is not None,
            file_size_bytes=vps_file["size_bytes"] if vps_file else None,
            file_modified_at=vps_file["modified_at"] if vps_file else None,
            in_sync=vps_file is not None,
        ))
    return result
