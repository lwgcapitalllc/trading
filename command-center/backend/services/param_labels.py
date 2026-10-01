"""param_labels.py — a strategy setting's Command Center label, for a Telegram message.

⚠ **A deliberate MIRROR of `algos/shared/param_labels.py`.** The two subsystems may share a data
FILE and may not import each other's code, so both read the same
`strategies/python/<pkg>/<pkg>.meta.json` (`params[] → {name, label}`) — the labels the Configure
tab already shows. The fallback rule (`humanise`) must stay identical on both sides; a test in
`algos/tests/test_param_labels.py` loads this file by path and compares them.

Display only, so it never raises: no file, a bad file or an unknown field all fall back to the
humanised name (`exec_sl_deep` → `Sl deep`), never the raw code name.
"""

from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path
from typing import Optional

__all__ = ["label_for", "value_text", "change_text", "humanise"]

# backend/services/param_labels.py → the monorepo root is three folders up from `backend`.
_REPO = Path(__file__).resolve().parents[3]


def humanise(name: str) -> str:
    """The fallback when no label is known: no `exec_` prefix, `_pct` read as `%`, spaces."""
    n = str(name)
    if n.startswith("exec_"):
        n = n[len("exec_") :]
    if n.endswith("_pct"):
        n = n[: -len("_pct")] + " %"
    n = n.replace("_", " ").strip()
    return n[:1].upper() + n[1:] if n else str(name)


@lru_cache(maxsize=32)
def _labels(package: str) -> dict:
    try:
        path = _REPO / "strategies" / "python" / package / f"{package}.meta.json"
        params = json.loads(path.read_text(encoding="utf-8")).get("params") or []
        if isinstance(params, dict):
            params = [{"name": k, **(v or {})} for k, v in params.items()]
        return {
            str(e["name"]): str(e["label"]).replace("↳", "").strip()
            for e in params
            if e.get("name") and e.get("label")
        }
    except Exception:  # noqa: BLE001 — display only
        return {}


def label_for(name: str, package: Optional[str] = None) -> str:
    """The Configure tab's label for `name`, or a humanised name when there is none."""
    if package:
        label = _labels(str(package)).get(str(name))
        if label:
            return label
    return humanise(name)


def value_text(value) -> str:
    """`5.0` → `5`, `True` → `on`, `None` → `none`."""
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
