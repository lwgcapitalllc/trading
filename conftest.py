"""Repo-root pytest bootstrap.

The canonical engines live under ``engines/`` but are imported by bare
package name (``from market_structure import ...``, ``from sessions import ...``)
to match the rest of the repo's "put the dir on sys.path, import bare" pattern.
Putting ``engines/`` on sys.path here makes every engine importable from any
test in the suite, including the ones that don't bootstrap their own path.
"""

import subprocess
import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parent


# Git hook tripwire. `core.hooksPath` is per-clone LOCAL config that `git clone`
# does not carry, and nothing runs on clone, so a fresh checkout commits with no
# checks and looks exactly like a protected one. Running the test suite is one of
# the first things anybody does here, so it is a good place to notice. Silent when
# already installed; prints once when it had to install.
def _install_git_hooks() -> str:
    script = _ROOT / "scripts" / "install_hooks.sh"
    if not script.is_file() or not (_ROOT / ".git").exists():
        return ""
    try:
        out = subprocess.run([str(script), "--quiet"], capture_output=True, text=True, timeout=10)
    except (OSError, subprocess.SubprocessError):
        return ""  # never let a convenience break the suite
    return out.stdout.strip()


_HOOK_NOTICE = _install_git_hooks()


def pytest_report_header(config) -> str:
    """Report an install through pytest's header.

    Printing from conftest at import time is swallowed by pytest's collection
    capture — the hooks would get installed and nobody would be told, which is
    the same silence this whole mechanism exists to break.
    """
    return _HOOK_NOTICE


_ENGINES = _ROOT / "engines"
if str(_ENGINES) not in sys.path:
    sys.path.insert(0, str(_ENGINES))

# `algos/nt8/test_bt_switch.py` is a VPS DEBUG SCRIPT that happens to be named test_*. It is not
# a test: it needs pywinauto and a running NinjaTrader, and it calls `sys.exit(1)` at import time
# when they are absent — which pytest reports as an INTERNALERROR that aborts the entire run
# before a single test executes. So `pytest algos/` was unusable, and the failure names pytest's
# own internals rather than the file. Ignored here so the directory is collectable now that
# `algos/tests/` holds a real suite.
collect_ignore = ["algos/nt8/test_bt_switch.py"]
