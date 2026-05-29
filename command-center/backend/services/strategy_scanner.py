"""
NinjaScript strategy parser. Scans .cs files under algos/markets/futures/
and extracts metadata for the strategies table.
"""

from __future__ import annotations

import hashlib
import json
import re
import time
from pathlib import Path
from typing import Optional

import config as cfg
from services import lab_db

_CATEGORY_MAP = {
    "orb": "breakout",
    "vwap_mr": "mean_reversion",
    "momentum": "momentum",
}


def _md5_text(text: str) -> str:
    return hashlib.md5(text.encode("utf-8", errors="replace")).hexdigest()


def _infer_category(class_name: str) -> Optional[str]:
    lower = class_name.lower()
    for key, cat in _CATEGORY_MAP.items():
        if key in lower:
            return cat
    return None


def _infer_name(source: str) -> str:
    # Prefer the Description string from SetDefaults — most reliable
    m = re.search(r'Description\s*=\s*"([^"]+)"', source)
    if m:
        return m.group(1)
    # Fallback: first non-trivial comment line
    for line in source.splitlines()[:5]:
        text = line.strip().lstrip("/ ").strip()
        if len(text) > 5 and not text.startswith("#"):
            return text
    return ""


def _infer_default_instrument(class_name: str) -> Optional[str]:
    cfg_path = (
        Path(cfg.MONOREPO_ROOT)
        / "algos" / "markets" / "futures" / "lucid_flex" / "tools" / "backtest_config.json"
    )
    if not cfg_path.exists():
        return None
    try:
        combos = json.loads(cfg_path.read_text())["combos"]
        for combo in combos:
            if combo.get("strategy") == class_name:
                return combo.get("instrument")
    except Exception:
        pass
    return None


def _parse_params(source: str) -> list[dict]:
    """
    Walk lines, collect [NinjaScriptProperty] blocks.
    Skip any block whose [Display] has GroupName = "Prop Firm".
    """
    params: list[dict] = []
    lines = source.splitlines()
    i = 0
    while i < len(lines):
        if lines[i].strip() == "[NinjaScriptProperty]":
            range_str: Optional[str] = None
            display_str: Optional[str] = None
            cs_type: Optional[str] = None
            prop_name: Optional[str] = None

            j = i + 1
            while j < min(i + 10, len(lines)):
                l = lines[j].strip()
                if l.startswith("[Range("):
                    # [Range(5, 60)] — strip the wrapper
                    range_str = l[7:].rstrip(")]")
                elif l.startswith("[Display("):
                    display_str = l[9:].rstrip(")]")
                elif l.startswith("public "):
                    parts = l.split()
                    if len(parts) >= 3:
                        cs_type = parts[1]
                        prop_name = parts[2]
                    break
                j += 1

            if prop_name and display_str and cs_type:
                group_m = re.search(r'GroupName\s*=\s*"([^"]*)"', display_str)
                group = group_m.group(1) if group_m else "Strategy"

                if group == "Prop Firm":
                    i = j + 1
                    continue

                name_m = re.search(r'(?:^|,\s*)Name\s*=\s*"([^"]*)"', display_str)
                display_name = name_m.group(1) if name_m else prop_name

                order_m = re.search(r'Order\s*=\s*(\d+)', display_str)
                order = int(order_m.group(1)) if order_m else 99

                param: dict = {
                    "name": prop_name,
                    "type": _cs_type(cs_type),
                    "display_name": display_name,
                    "group": group,
                    "order": order,
                }

                if range_str:
                    parts = range_str.split(",")
                    if len(parts) == 2:
                        try:
                            lo, hi = float(parts[0].strip()), float(parts[1].strip())
                            if param["type"] == "int":
                                param["min"] = int(lo)
                                param["max"] = int(hi)
                            else:
                                param["min"] = lo
                                param["max"] = hi
                        except ValueError:
                            pass

                params.append(param)

            i = j + 1
        else:
            i += 1

    return sorted(params, key=lambda p: p.get("order", 99))


def _cs_type(cs_type: str) -> str:
    t = cs_type.lower()
    if t == "bool":
        return "bool"
    if t == "int":
        return "int"
    return "double"


def _parse_defaults(source: str, params: list[dict]) -> dict:
    """Pull default values from State.SetDefaults body."""
    m = re.search(
        r'State == State\.SetDefaults\s*\)(.*?)(?:else\s+if|protected\s+override)',
        source,
        re.DOTALL,
    )
    if not m:
        return {}
    block = m.group(1)

    defaults: dict = {}
    for param in params:
        name = param["name"]
        dm = re.search(rf'\b{re.escape(name)}\s*=\s*([^;]+);', block)
        if not dm:
            continue
        val_str = dm.group(1).strip()
        try:
            if param["type"] == "bool":
                defaults[name] = val_str.lower() == "true"
            elif param["type"] == "int":
                defaults[name] = int(float(val_str))
            else:
                defaults[name] = float(val_str)
        except ValueError:
            pass

    return defaults


def _parse_file(cs_path: Path, monorepo_root: Path, source: str) -> Optional[dict]:
    class_m = re.search(r'public\s+class\s+(\w+)\s*:\s*Strategy\b', source)
    if not class_m:
        return None

    class_name = class_m.group(1)
    params = _parse_params(source)
    defaults = _parse_defaults(source, params)

    for p in params:
        if p["name"] in defaults:
            p["default"] = defaults[p["name"]]

    rel_path = str(cs_path.relative_to(monorepo_root)).replace("\\", "/")

    return {
        "id": class_name.lower(),
        "name": _infer_name(source) or class_name.replace("_", " "),
        "class_name": class_name,
        "source_path": rel_path,
        "category": _infer_category(class_name),
        "default_instrument": _infer_default_instrument(class_name),
        "default_params": defaults,
        "param_schema": params,
        "scanned_at": int(time.time()),
        "source_hash": _md5_text(source),
    }


def scan_strategies() -> dict:
    """Scan algos/markets/futures/**/*.cs; upsert changed strategies. Returns counts."""
    monorepo_root = Path(cfg.MONOREPO_ROOT)
    futures_dir = monorepo_root / "algos" / "markets" / "futures"

    if not futures_dir.exists():
        return {"scanned": 0, "added": 0, "updated": 0, "skipped": 0}

    cs_files = list(futures_dir.rglob("*.cs"))
    added = updated = skipped = strategy_count = 0

    for cs_path in cs_files:
        source = cs_path.read_text(encoding="utf-8", errors="replace")

        class_m = re.search(r'public\s+class\s+(\w+)\s*:\s*Strategy\b', source)
        if not class_m:
            continue

        strategy_count += 1
        class_name = class_m.group(1)
        strategy_id = class_name.lower()
        current_hash = _md5_text(source)

        if lab_db.get_strategy_hash(strategy_id) == current_hash:
            skipped += 1
            continue

        data = _parse_file(cs_path, monorepo_root, source=source)
        if data is None:
            continue

        is_new = lab_db.get_strategy(strategy_id) is None
        lab_db.upsert_strategy(data)
        if is_new:
            added += 1
        else:
            updated += 1

    return {"scanned": strategy_count, "added": added, "updated": updated, "skipped": skipped}
