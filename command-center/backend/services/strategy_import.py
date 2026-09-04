"""Importing a Python strategy package so that what you read is what is on DISK.

🔴 **Why this module exists.** `strategies/python/<pkg>` is imported with
`importlib.import_module`, which returns whatever is already in `sys.modules`. The backend is a
long-running process, so the FIRST import of a strategy pins its config dataclass, its defaults and
its logic for the life of that process — every later scan and every later backtest reads the version
that was on disk when the backend last booted.

That alone would be an ordinary staleness bug. What makes it worth its own module is that it is
**self-sealing in the scanner**: `_python_source_hash` reads the FILES, while `_py_param_schema`
reads the cached MODULE. So a scan after an edit writes the NEW hash beside the OLD defaults, and
`needs_rescan` — which compares only the hash — is satisfied for ever. The stale row can never be
corrected by scanning again, and nothing anywhere reports a problem: the "Needs scan" pill clears,
the scan says `updated`, and the Run modal goes on offering a default the strategy no longer has.

Measured 2026-08-06: `exec_time_stop_mode` was flipped `"Off"` → `"Before TP1 only"` in
`config.py`, the scan reported success, and the Run modal kept offering `Off`. Clearing
`source_hash` by hand was the only way out.

**The fix is to make the two halves read the same thing: drop the cached modules, then import.**

⚠ **Purge the whole `strategies.python` namespace, never one package.** `b_leg` imports
`sos_fade`'s execution module, and packages are scanned in alphabetical order — so purging one
at a time would re-import `b_leg` against a still-cached, still-stale `sos_fade` and produce
exactly the mixed reading this module exists to prevent. Purge once, then import the set.

⚠ **Dropping a module from `sys.modules` does not invalidate references anything already holds.** A
backtest in flight keeps the classes it was built with and finishes on them; only the NEXT import
sees new objects. That is what makes this safe to call from a request handler.
"""

from __future__ import annotations

import importlib
import sys
from pathlib import Path
from types import ModuleType

_PKG_ROOT = "strategies.python"


def purge_strategy_modules() -> int:
    """Drop every cached `strategies.python.*` module. Returns how many were dropped.

    Call ONCE before a loop that imports several packages — see the namespace warning above.
    """
    stale = [name for name in sys.modules if name == _PKG_ROOT or name.startswith(_PKG_ROOT + ".")]
    for name in stale:
        del sys.modules[name]
    return len(stale)


def import_strategy_package(pkg_name: str, monorepo_root: Path) -> ModuleType:
    """Import `strategies.python.<pkg_name>`, with the monorepo root on `sys.path`.

    The path entry is left in place deliberately: a strategy may import a submodule lazily at
    replay time, long after this call has returned.
    """
    root = str(monorepo_root)
    if root not in sys.path:
        sys.path.insert(0, root)
    return importlib.import_module(f"{_PKG_ROOT}.{pkg_name}")
