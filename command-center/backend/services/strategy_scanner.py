"""
Strategy parser. Scans strategy source files under strategies/ and extracts
metadata for the strategies table.

Supported runners:
  ninjatrader — .cs files (NinjaScript / C#)
  mt5         — .mq5 files (MQL5)
"""

from __future__ import annotations

import hashlib
import json
import re
import time
from pathlib import Path
from typing import Optional

import config as cfg
from services import lab_db, runner_dispatch

_CATEGORY_MAP = {
    "orb": "breakout",
    "vwap_mr": "mean_reversion",
    "momentum": "momentum",
    "meanreversion": "mean_reversion",
}


def _md5_text(text: str) -> str:
    return hashlib.md5(text.encode("utf-8", errors="replace")).hexdigest()


def source_hash(text: str) -> str:
    """Public content hash for strategy source — the version registry's identity.
    Callers that hold raw bytes should decode utf-8 (errors='replace') first so the
    hash matches what the scanner computes."""
    return _md5_text(text)


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


def _infer_suggested_instrument(class_name: str) -> Optional[str]:
    cfg_path = (
        Path(cfg.MONOREPO_ROOT)
        / "algos" / "nt8" / "backtest_config.json"
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

    Pass 1 style (ORB.cs and later): [Category("Strategy Logic")] or
    [Category("Foundational")] attributes drive the category field directly.

    Legacy style (pre-Pass-1 files): GroupName="Prop Firm" → foundational,
    GroupName="Strategy" (or absent) → strategy_logic.

    All params are included in the schema regardless of category.
    Foundational params are hidden in the UI but present for dispatcher docs.
    """
    params: list[dict] = []
    lines = source.splitlines()
    i = 0
    while i < len(lines):
        if lines[i].strip() == "[NinjaScriptProperty]":
            range_str: Optional[str] = None
            display_str: Optional[str] = None
            category_attr: Optional[str] = None   # value from [Category("...")] if present
            cs_type: Optional[str] = None
            prop_name: Optional[str] = None

            j = i + 1
            # Window of 15 lines covers up to 4 attributes + public declaration
            while j < min(i + 15, len(lines)):
                l = lines[j].strip()
                if l.startswith("[Range("):
                    range_str = l[7:].rstrip(")]")
                elif l.startswith("[Display("):
                    display_str = l[9:].rstrip(")]")
                elif l.startswith("[Category("):
                    cm = re.search(r'\[Category\("([^"]+)"\)\]', l)
                    if cm:
                        category_attr = cm.group(1)
                elif l.startswith("public "):
                    parts = l.split()
                    if len(parts) >= 3:
                        cs_type = parts[1]
                        prop_name = parts[2]
                    break
                j += 1

            if not (prop_name and cs_type):
                i = j + 1
                continue

            # Determine category — [Category] wins; fall back to GroupName heuristic
            if category_attr is not None:
                param_category = "foundational" if category_attr == "Foundational" else "strategy_logic"
                group = category_attr
            elif display_str:
                group_m = re.search(r'GroupName\s*=\s*"([^"]*)"', display_str)
                group = group_m.group(1) if group_m else "Strategy"
                param_category = "foundational" if group == "Prop Firm" else "strategy_logic"
            else:
                group = "Strategy"
                param_category = "strategy_logic"

            # Display name and sort order from [Display(...)]
            display_name = prop_name
            order = 99
            if display_str:
                name_m = re.search(r'(?:^|,\s*)Name\s*=\s*"([^"]*)"', display_str)
                if name_m:
                    display_name = name_m.group(1)
                order_m = re.search(r'Order\s*=\s*(\d+)', display_str)
                if order_m:
                    order = int(order_m.group(1))

            param: dict = {
                "name": prop_name,
                "type": _cs_type(cs_type),
                "display_name": display_name,
                "category": param_category,
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
    if t == "string":
        return "string"
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
            elif param["type"] == "string":
                # Strip surrounding quotes from string literals like "" or "09:30"
                defaults[name] = val_str.strip('"')
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
    overview = _read_strategy_overview(meta_path_for(cs_path))

    return {
        "id": class_name.lower(),
        "name": _infer_name(source) or class_name.replace("_", " "),
        "class_name": class_name,
        "source_path": rel_path,
        "category": _infer_category(class_name),
        "suggested_instrument": _infer_suggested_instrument(class_name),
        "default_params": defaults,
        "param_schema": params,
        "scanned_at": int(time.time()),
        "source_hash": _md5_text(source),
        "runner": "ninjatrader",
        "edge": overview.get("edge"),
        "steps": overview.get("steps", []),
    }


# ── MQL5 parser ───────────────────────────────────────────────────────────────

# Matches single-line input declarations in MQL5 source.
# Group 1: type (int, double, string, bool)
# Group 2: variable name
# Group 3: default value (raw — may include quotes for strings)
# Group 4: trailing comment text (optional)
# Skips extern declarations (legacy MQL4 style) since only `input` is matched.
_MQL5_INPUT_RE = re.compile(
    r'^\s*input\s+(\w+)\s+(\w+)\s*=\s*(.+?)\s*;(?:\s*//(.*))?$',
    re.MULTILINE,
)

# Optional explicit UI group tag in a trailing comment, e.g.
# `// [group: Session Windows] Asian range window start (GMT)`. Parity with
# NinjaScript's [Category("...")] — lets an .mq5 declare its own param sections.
_MQL5_GROUP_RE = re.compile(r'\[group:\s*([^\]]+)\]', re.IGNORECASE)


def _mql5_type(type_str: str) -> str:
    t = type_str.lower()
    if t == "bool":
        return "bool"
    if t == "int":
        return "int"
    if t == "string":
        return "string"
    return "double"  # double, float, color, etc.


def _parse_mql5_params(source: str) -> list[dict]:
    """Parse MQL5 `input` declarations and return param schema dicts.

    Category priority (highest to lowest):
    1. Trailing comment contains "strategy_logic" → strategy_logic (explicit override)
    2. Trailing comment contains "foundational"   → foundational   (explicit override)
    3. Variable name starts with f_               → foundational   (naming convention)
    4. Default                                    → strategy_logic
    """
    params: list[dict] = []
    for order, m in enumerate(_MQL5_INPUT_RE.finditer(source)):
        mql5_type = m.group(1)
        name      = m.group(2)
        raw_val   = m.group(3).strip()
        comment   = (m.group(4) or "").strip()

        # Pull an explicit "[group: ...]" tag out of the comment before anything
        # else reads it, so the tag never leaks into the display_name.
        custom_group = None
        gm = _MQL5_GROUP_RE.search(comment)
        if gm:
            custom_group = gm.group(1).strip()
            comment = _MQL5_GROUP_RE.sub("", comment).strip()

        comment_lower = comment.lower()
        if "strategy_logic" in comment_lower:
            category = "strategy_logic"
        elif "foundational" in comment_lower:
            category = "foundational"
        elif name.startswith("f_"):
            category = "foundational"
        else:
            category = "strategy_logic"

        param_type = _mql5_type(mql5_type)

        default = None
        try:
            if param_type == "bool":
                default = raw_val.lower() == "true"
            elif param_type == "int":
                default = int(float(raw_val))
            elif param_type == "string":
                default = raw_val.strip('"')
            else:
                default = float(raw_val)
        except ValueError:
            pass

        # Use the trailing comment as display_name unless it is purely a category marker
        is_category_marker = "strategy_logic" in comment_lower or "foundational" in comment_lower
        display_name = name if (not comment or is_category_marker) else comment

        param: dict = {
            "name":         name,
            "type":         param_type,
            "display_name": display_name,
            "category":     category,
            "group":        custom_group or ("Foundational" if category == "foundational" else "Strategy Logic"),
            "order":        order,
        }
        if default is not None:
            param["default"] = default

        params.append(param)

    return params


def _mql5_display_name(stem: str, source: str) -> str:
    """Extract a display name from the first descriptive comment line.

    Skips the standard MQL5 header block (//| and //+ lines). Falls back to
    inserting spaces before capitals in the filename stem if no comment is found.
    """
    for line in source.splitlines()[:20]:
        line = line.strip()
        if line.startswith("//") and not line.startswith("//|") and not line.startswith("//+"):
            text = line[2:].strip()
            if len(text) > 5:
                return text.split(" — ")[0].strip() if " — " in text else text
    return re.sub(r"([A-Z])", r" \1", stem).strip()


# UI metadata keys overlaid from a companion <Strategy>.meta.json onto each param.
# These drive the editor UI only — never the compiled strategy or the source hash.
_PARAM_META_KEYS = ("label", "desc", "unit", "core", "widget",
                    "options", "show_if", "guide", "group", "step", "min", "max")


def meta_path_for(source_path: Path) -> Path:
    """Companion metadata file next to a strategy: LondonBreakout.mq5 -> LondonBreakout.meta.json."""
    return source_path.with_name(source_path.stem + ".meta.json")


def _read_strategy_overview(meta_path: Path) -> dict:
    """Strategy-level narrative from a companion meta.json — UI only.

    Returns {edge?: str, steps?: [{label, title, detail}]}. Absent or malformed
    file is a no-op ({}); the detail page degrades to the editable description alone.
    """
    if not meta_path.exists():
        return {}
    try:
        meta = json.loads(meta_path.read_text(encoding="utf-8", errors="replace"))
    except (ValueError, OSError):
        return {}
    if not isinstance(meta, dict):
        return {}
    out: dict = {}
    edge = meta.get("edge")
    if isinstance(edge, str) and edge.strip():
        out["edge"] = edge.strip()
    steps = meta.get("steps")
    if isinstance(steps, list):
        clean = [s for s in steps if isinstance(s, dict) and s.get("title")]
        if clean:
            out["steps"] = clean
    return out


def _apply_param_meta(params: list[dict], meta_path: Path) -> list[dict]:
    """Overlay editor metadata from a companion meta.json onto scanned params.

    Enriches labels, descriptions, units, grouping, the 'essentials' (core) flag,
    conditional visibility (show_if), and toggle option labels. Params absent from
    the meta file keep their scanned values. The meta param order becomes the
    canonical UI order; unlisted params (e.g. foundational f_*) follow in source
    order. A missing or malformed meta file is a no-op — the UI degrades to the
    raw scanned schema.
    """
    if not meta_path.exists():
        return params
    try:
        meta = json.loads(meta_path.read_text(encoding="utf-8", errors="replace"))
    except (ValueError, OSError):
        return params

    meta_list = meta.get("params", []) if isinstance(meta, dict) else []
    order: dict[str, int] = {}
    by_name: dict[str, dict] = {}
    for i, m in enumerate(meta_list):
        name = m.get("name")
        if not name:
            continue
        order[name] = i
        by_name[name] = m

    for p in params:
        m = by_name.get(p["name"])
        if not m:
            continue
        for key in _PARAM_META_KEYS:
            if m.get(key) is not None:
                p[key] = m[key]

    # Stable sort: meta-listed params first (in meta order), the rest keep source order.
    params.sort(key=lambda p: order.get(p["name"], len(order) + 1))
    return params


def _parse_mql5_file(mq5_path: Path, monorepo_root: Path, source: str) -> Optional[dict]:
    """Parse a .mq5 EA file and return a strategy dict ready for lab_db.upsert_strategy.

    Uses the filename stem as both class_name and the basis for the strategy ID
    (lowercased). Returns None if the file has no `input` declarations (not an EA).
    """
    params = _parse_mql5_params(source)
    if not params:
        return None
    meta_path   = meta_path_for(mq5_path)
    params      = _apply_param_meta(params, meta_path)
    overview    = _read_strategy_overview(meta_path)

    stem        = mq5_path.stem          # "MeanReversion"
    strategy_id = stem.lower()           # "meanreversion"
    rel_path    = str(mq5_path.relative_to(monorepo_root)).replace("\\", "/")
    defaults    = {p["name"]: p["default"] for p in params if "default" in p}

    return {
        "id":                   strategy_id,
        "name":                 _mql5_display_name(stem, source),
        "class_name":           stem,
        "source_path":          rel_path,
        "category":             _infer_category(strategy_id),
        "suggested_instrument": None,
        "default_params":       defaults,
        "param_schema":         params,
        "scanned_at":           int(time.time()),
        "source_hash":          _md5_text(source),
        "runner":               "mt5",
        "edge":                 overview.get("edge"),
        "steps":                overview.get("steps", []),
    }


def scan_strategies() -> dict:
    """Scan strategies/**/*.cs and **/*.mq5; upsert changed strategies."""
    monorepo_root  = Path(cfg.MONOREPO_ROOT)
    strategies_dir = monorepo_root / "strategies"

    if not strategies_dir.exists():
        return {"scanned": 0, "added": 0, "updated": 0, "skipped": 0, "warnings": []}

    added = updated = skipped = strategy_count = 0

    # ── NinjaTrader (.cs) ─────────────────────────────────────────────────────
    for cs_path in strategies_dir.rglob("*.cs"):
        source = cs_path.read_text(encoding="utf-8", errors="replace")

        class_m = re.search(r'public\s+class\s+(\w+)\s*:\s*Strategy\b', source)
        if not class_m:
            continue

        strategy_count += 1
        class_name  = class_m.group(1)
        strategy_id = class_name.lower()
        current_hash = _md5_text(source)
        lab_db.ensure_strategy_version(strategy_id, current_hash, len(source.encode("utf-8", errors="replace")))

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

    # ── MT5 (.mq5) ────────────────────────────────────────────────────────────
    for mq5_path in strategies_dir.rglob("*.mq5"):
        source = mq5_path.read_text(encoding="utf-8", errors="replace")

        strategy_id  = mq5_path.stem.lower()
        current_hash = _md5_text(source)

        data = _parse_mql5_file(mq5_path, monorepo_root, source)
        if data is None:
            continue  # no input declarations — skip silently

        strategy_count += 1
        lab_db.ensure_strategy_version(strategy_id, current_hash, len(source.encode("utf-8", errors="replace")))

        # Re-scan when the source OR the companion meta.json changed. The meta file
        # carries no source hash (it must not trigger needs-deploy), so detect its
        # edits by mtime vs the last scan time.
        meta_p = meta_path_for(mq5_path)
        meta_mtime = meta_p.stat().st_mtime if meta_p.exists() else 0
        existing = lab_db.get_strategy(strategy_id)
        if (existing and existing.get("source_hash") == current_hash
                and meta_mtime <= (existing.get("scanned_at") or 0)):
            skipped += 1
            continue

        is_new = existing is None
        lab_db.upsert_strategy(data)
        if is_new:
            added += 1
        else:
            updated += 1

    # Detect — but never delete during a scan — strategies whose source file is
    # gone from the repo. Deleting a source means "remove everywhere" (DB row +
    # deployed VPS file), but that destructive step is gated behind an explicit
    # Reconcile action (POST /strategies/reconcile). A scan is a frequent read; a
    # mis-synced disk (wrong MONOREPO_ROOT, repo not checked out) would otherwise
    # silently wipe every deployed file. So scan only REPORTS the orphans.
    orphans = _detect_orphans(monorepo_root)

    return {"scanned": strategy_count, "added": added, "updated": updated,
            "skipped": skipped, "orphans": orphans, "warnings": []}


def _detect_orphans(monorepo_root: Optional[Path] = None) -> list[str]:
    """IDs of DB strategies whose recorded source_path no longer exists on disk —
    i.e. the source file was deleted from the repo. Strategies with no source_path
    are skipped (they were never tied to a repo file, so they aren't orphans)."""
    root = monorepo_root or Path(cfg.MONOREPO_ROOT)
    orphans: list[str] = []
    for s in lab_db.list_strategies():
        sp = s.get("source_path")
        if sp and not (root / sp).exists():
            orphans.append(s["id"])
    return orphans


def reconcile_strategies() -> dict:
    """Explicit, destructive counterpart to scan_strategies: for every DB strategy
    whose source file was deleted from the repo, remove it everywhere — DB row +
    deployed VPS file. The VPS delete is best-effort (see remove_strategy); a
    failure is surfaced as a warning but never blocks the DB removal. Returns
    {removed, warnings}."""
    removed: list[str] = []
    warnings: list[str] = []
    for sid in _detect_orphans():
        res = remove_strategy(sid)
        removed.append(sid)
        if res["vps_error"]:
            warnings.append(
                f"{sid}: removed from DB, but its VPS file could not be "
                f"deleted — {res['vps_error']}"
            )
    return {"removed": removed, "warnings": warnings}


def remove_strategy(strategy_id: str, *, delete_vps_file: bool = True) -> dict:
    """Remove a strategy everywhere: delete its deployed file from the VPS NT8/MT5
    strategy folder (best-effort) and delete its DB row. The VPS delete is
    best-effort — an unreachable agent or an already-absent file never blocks the
    DB removal (the source is gone, so the strategy is conceptually deleted).
    Returns {removed, vps_deleted, vps_error}.
    """
    row = lab_db.get_strategy(strategy_id)
    if not row:
        return {"removed": False, "vps_deleted": False, "vps_error": None}

    vps_deleted = False
    vps_error: Optional[str] = None
    if delete_vps_file:
        sp = row.get("source_path")
        filename = Path(sp).name if sp else None
        if filename:
            try:
                runner_dispatch.delete_strategy_file(filename)
                vps_deleted = True
            except RuntimeError as exc:
                msg = str(exc)
                # "already gone" is success, not a failure.
                if "HTTP 404" in msg or "not found" in msg.lower():
                    vps_deleted = True
                else:
                    vps_error = msg

    lab_db.delete_strategy(strategy_id)
    return {"removed": True, "vps_deleted": vps_deleted, "vps_error": vps_error}
