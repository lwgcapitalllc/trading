"""Nothing in `algos/live/` may import the FROZEN trees at module scope.

🔴 **This test exists because the live bot went down on 2026-08-13 and crash-looped for several
minutes, and a fully green suite had nothing to say about it.**

A promoted bot imports from `instances/<bot>/deployed/` — a frozen snapshot of
`strategies/python/<pkg>`, `engines/` and `backtest/`. `runner._bind_code()` puts that snapshot at
the front of `sys.path`, and it REFUSES to start if any of those modules is already in
`sys.modules`, because `sys.path` only decides where a name is looked up the FIRST time: an
earlier import stays imported, the freeze is silently half-applied, and the bot runs a mix of
deployed and repo code while its startup log says "frozen".

**What happened:** `alerts.py` grew a module-level `from backtest.setups import FILLED`.
`bridge.py` imports `alerts`, `runner.py` imports `bridge` — all at module scope, all before
`_bind_code()` runs. Every start died with `Cannot freeze this deployment: backtest,
backtest.setups was already imported from the repo before the snapshot was bound`, exit code 2,
uptime 1 second, on a ~60s watchdog loop.

**The guard worked perfectly and that is the point of this file.** It named the module, named the
cause, and said what to do. What it could not do is fire before the code reached a live bot —
`is_frozen` is false in every test and in every dry run, so the one configuration that trips it is
the one with real money behind it. `_bind_code`'s own docstring said *"Nothing in `algos/live/`
imports these at module scope (checked)"* — checked by a human, once, and no longer true.

⚠ **This runs in a SUBPROCESS on purpose.** The test session has already imported `backtest` for
other reasons, so asking about the current `sys.modules` would be meaningless — it has to be a
fresh interpreter that imports only what the bot imports.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest

_ROOT = Path(__file__).resolve().parents[2]
_LIVE = _ROOT / "algos" / "live"

#: The three trees a promoted bot freezes. `strategies` is included because the strategy package
#: is pinned too — `_bind_code` checks it by name, and any of its modules leaking has the same
#: effect.
_FROZEN_TOP_LEVEL = ("backtest", "engines", "strategies")

#: What the runner itself imports at module scope. `runner` pulls in `bridge`, `feed` and
#: `ledger`, and `bridge` pulls in `alerts` — which is the chain that broke.
_ENTRY_MODULES = ("runner", "bridge", "feed", "ledger", "alerts", "live_config", "version")

_PROBE = """
import sys
sys.path.insert(0, {live!r})
sys.path.insert(0, {shared!r})
sys.path.insert(0, {root!r})
import {module}
leaked = sorted(m for m in sys.modules if m.split('.')[0] in {frozen!r})
print('LEAKED:' + ','.join(leaked))
"""


@pytest.mark.parametrize("module", _ENTRY_MODULES)
def test_importing_it_does_not_pull_in_a_frozen_tree(module):
    """Fails by NAME on whichever module leaked, and on what it leaked.

    ⚠ **Watched RED against the real bug**: restoring `from backtest.setups import FILLED` to the
    top of `alerts.py` fails this for `alerts`, `bridge` AND `runner` — the whole import chain,
    which is also how the bot experienced it.

    The fix is always the same and is never "add it to an allow-list": move the import INSIDE the
    function that needs it. By the time any function here runs, the snapshot is bound.
    """
    code = _PROBE.format(module=module, live=str(_LIVE),
                         shared=str(_ROOT / "algos" / "shared"), root=str(_ROOT),
                         frozen=_FROZEN_TOP_LEVEL)
    out = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True,
                         cwd=str(_ROOT), timeout=120)
    assert out.returncode == 0, f"importing {module} failed:\n{out.stderr[-2000:]}"
    line = [ln for ln in out.stdout.splitlines() if ln.startswith("LEAKED:")]
    assert line, f"probe produced no verdict for {module}:\n{out.stdout}\n{out.stderr}"
    leaked = [m for m in line[0][len("LEAKED:"):].split(",") if m]
    assert not leaked, (
        f"`algos/live/{module}.py` imports {leaked} at MODULE scope. A promoted bot binds its "
        f"frozen snapshot AFTER these modules load, so this import resolves against the repo and "
        f"`runner._bind_code()` will refuse to start the bot (exit 2, 'version pin mismatch'). "
        f"Move the import inside the function that uses it.")


def test_the_probe_can_actually_detect_a_leak():
    """The guard against a vacuous guard: if the probe were broken it would report "no leak" for
    everything, including a module that genuinely leaks, and this whole file would pass forever
    while protecting nothing.

    Imports `backtest.setups` directly and requires the probe to notice.
    """
    code = _PROBE.format(module="backtest.setups", live=str(_LIVE),
                         shared=str(_ROOT / "algos" / "shared"), root=str(_ROOT),
                         frozen=_FROZEN_TOP_LEVEL)
    out = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True,
                         cwd=str(_ROOT), timeout=120)
    line = [ln for ln in out.stdout.splitlines() if ln.startswith("LEAKED:")][0]
    assert "backtest" in line, f"the probe cannot see a leak it was handed: {line}"
