"""
Settings router — /settings

Read/write the backend config.json (machine-specific paths).
"""

import json
from pathlib import Path

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

router = APIRouter(prefix="/settings", tags=["settings"])

_CONFIG_PATH = Path(__file__).parent.parent / "config.json"


class AppSettings(BaseModel):
    monorepo_root: str
    smart_money_root: str
    smart_money_config_path: str
    smart_money_reports_dir: str
    instances_dir: str
    ssh_alias: str
    nt8_agent_tunnel: str
    mt5_agent_tunnel: str


@router.get("", response_model=AppSettings)
def get_settings():
    if not _CONFIG_PATH.exists():
        raise HTTPException(status_code=404, detail="config.json not found")
    with open(_CONFIG_PATH) as f:
        return AppSettings(**json.load(f))


@router.put("", response_model=AppSettings)
def update_settings(body: AppSettings):
    with open(_CONFIG_PATH, "w") as f:
        json.dump(body.model_dump(), f, indent=2)
        f.write("\n")
    return body
