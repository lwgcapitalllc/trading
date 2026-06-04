from pathlib import Path
import json

_HERE = Path(__file__).parent
_CONFIG_PATH = _HERE / "config.json"


def _load() -> dict:
    with open(_CONFIG_PATH) as f:
        return json.load(f)


_cfg = _load()

MONOREPO_ROOT = Path(_cfg["monorepo_root"])
SMART_MONEY_ROOT = Path(_cfg["smart_money_root"])
SMART_MONEY_CONFIG_PATH = Path(_cfg["smart_money_config_path"])
SMART_MONEY_REPORTS_DIR = Path(_cfg["smart_money_reports_dir"])
INSTANCES_DIR = Path(_cfg["instances_dir"])
SSH_ALIAS: str = _cfg["ssh_alias"]
VPS_AGENT_TUNNEL: str = _cfg["vps_agent_tunnel"]
MT5_AGENT_TUNNEL: str = _cfg["mt5_agent_tunnel"]
