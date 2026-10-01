"""param_labels.py — the Command Center's label for a strategy setting, for any message a person reads.

**Why it exists (2026-09-30).** The health room named settings by their code names —
`exec_risk_pct 5.0 -> 4.0` — and nobody reading Telegram reads code. The Command Center already
shows every setting under a plain label, kept in each strategy's own
`strategies/python/<pkg>/<pkg>.meta.json` (`params[] → {name, label}`). This module reads that
same file, so a message and the Configure tab call a setting by the same name.

Generic for any strategy: it is keyed by the strategy PACKAGE, never by a bot or a field list.

⚠ **A promoted bot's snapshot copies only `.py` files**, so the meta.json is NOT beside the frozen
code. The lookup walks UP from this file and takes the first `strategies/python/<pkg>/<pkg>.meta.json`
it finds — inside a snapshot that walk passes the snapshot root (no meta there) and reaches the
repo checkout the snapshot sits in. Labels are display only, so a stale one costs nothing.

⚠ **It never raises.** No file, an unreadable file, a field it does not list: each falls back to a
humanised name (`exec_sl_deep` → `Sl deep`). A notifier that a missing label can bring down is
worse than one printing a plain-ish name.

⚠ `command-center/backend/services/param_labels.py` is a deliberate MIRROR (the two subsystems may
share a data file, never code) — keep the fallback rule the same on both sides.
"""

from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path
from typing import Optional

__all__ = ["label_for", "value_text", "change_text", "humanise"]


def humanise(name: str) -> str:
    """The fallback when no label is known: no `exec_` prefix, `_pct` read as `%`, spaces."""
    n = str(name)
    if n.startswith("exec_"):
        n = n[len("exec_") :]
    if n.endswith("_pct"):
        n = n[: -len("_pct")] + " %"
    n = n.replace("_", " ").strip()
    return n[:1].upper() + n[1:] if n else str(name)


def _meta_path(package: str, start: Optional[Path] = None) -> Optional[Path]:
    here = (start or Path(__file__)).resolve()
    for parent in here.parents:
        candidate = parent / "strategies" / "python" / package / f"{package}.meta.json"
        if candidate.is_file():
            return candidate
    return None


@lru_cache(maxsize=32)
def _labels(package: str) -> dict:
    try:
        path = _meta_path(package)
        if path is None:
            return {}
        params = json.loads(path.read_text(encoding="utf-8")).get("params") or []
        if isinstance(params, dict):  # tolerate a name → entry map
            params = [{"name": k, **(v or {})} for k, v in params.items()]
        out = {}
        for entry in params:
            name, label = entry.get("name"), entry.get("label")
            if name and label:
                # Some labels are indented under a parent in the UI ("   ↳ Risk % per trade").
                out[str(name)] = str(label).replace("↳", "").strip()
        return out
    except Exception:  # noqa: BLE001 — display only, see the docstring
        return {}


def label_for(name: str, package: Optional[str] = None) -> str:
    """The Command Center's label for `name`, or a humanised name when there is none."""
    if package:
        label = _labels(str(package)).get(str(name))
        if label:
            return label
    return humanise(name)


def value_text(value) -> str:
    """`5.0` → `5`, `True` → `on`, `None` → `none`. Readable, never a Python repr."""
    if value is None:
        return "none"
    if isinstance(value, bool):
        return "on" if value else "off"
    if isinstance(value, float):
        return f"{value:g}"
    if isinstance(value, (list, tuple)):
        return ", ".join(value_text(v) for v in value) or "none"
    return str(value)


def change_text(name: str, old, new, package: Optional[str] = None) -> str:
    """`Risk % per trade 5 → 4`."""
    return f"{label_for(name, package)} {value_text(old)} → {value_text(new)}"
