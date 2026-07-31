"""Repo-root pytest bootstrap.

The canonical engines live under ``engines/`` but are imported by bare
package name (``from market_structure import ...``, ``from sessions import ...``)
to match the rest of the repo's "put the dir on sys.path, import bare" pattern.
Putting ``engines/`` on sys.path here makes every engine importable from any
test in the suite, including the ones that don't bootstrap their own path.
"""
import sys
from pathlib import Path

_ENGINES = Path(__file__).resolve().parent / "engines"
if str(_ENGINES) not in sys.path:
    sys.path.insert(0, str(_ENGINES))

# `algos/nt8/test_bt_switch.py` is a VPS DEBUG SCRIPT that happens to be named test_*. It is not
# a test: it needs pywinauto and a running NinjaTrader, and it calls `sys.exit(1)` at import time
# when they are absent — which pytest reports as an INTERNALERROR that aborts the entire run
# before a single test executes. So `pytest algos/` was unusable, and the failure names pytest's
# own internals rather than the file. Ignored here so the directory is collectable now that
# `algos/tests/` holds a real suite.
collect_ignore = ["algos/nt8/test_bt_switch.py"]
