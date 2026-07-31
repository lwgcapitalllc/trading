"""The two halves of "what may change on a running bot" must agree.

`services/bot_params.RUNTIME_EDITABLE` decides what the Bots page will let you edit.
`algos/live/live_config.RUNTIME_RELOADABLE` decides what the bot will actually pick up.
They are separate files in separate subsystems because the command center may not import
`algos/` source (root CLAUDE.md), so they are duplicated — and duplication drifts.

Drift is silent and one-directional-bad: the UI offers an edit, the user makes it, the git
push and VPS pull all succeed, and the bot ignores the value forever. Nothing errors.

So this reads the algos file as TEXT — no import, no sys.path games, no dependency on the
other subsystem being importable — and pins the two sets equal.
"""

import ast
from pathlib import Path

import config as cfg
from services import bot_params

_LIVE_CONFIG = Path(cfg.MONOREPO_ROOT) / "algos" / "live" / "live_config.py"


def _reloadable_from_source() -> set[str]:
    """Pull RUNTIME_RELOADABLE out of algos/live/live_config.py without importing it."""
    tree = ast.parse(_LIVE_CONFIG.read_text(encoding="utf-8"))
    for node in tree.body:
        if not isinstance(node, ast.Assign):
            continue
        names = [t.id for t in node.targets if isinstance(t, ast.Name)]
        if "RUNTIME_RELOADABLE" not in names:
            continue
        # frozenset({...}) — take the literal inside the call
        value = node.value
        if isinstance(value, ast.Call) and value.args:
            value = value.args[0]
        return set(ast.literal_eval(value))
    raise AssertionError(f"RUNTIME_RELOADABLE not found in {_LIVE_CONFIG}")


def test_the_bot_file_still_declares_the_set():
    assert _reloadable_from_source()


def test_what_the_ui_lets_you_edit_is_what_the_bot_picks_up():
    """If this fails, one side was changed without the other. Fix BOTH — do not relax it.

    Editable-here-but-not-there = an edit that appears to work and silently does nothing.
    Reloadable-there-but-not-here = a lever the bot honours that nobody can reach.
    """
    assert bot_params.RUNTIME_EDITABLE == _reloadable_from_source()
