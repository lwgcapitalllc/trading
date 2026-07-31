"""The version pin — "which code is trading" must be answerable, and provable.

The single most important test here is `test_hash_matches_the_labs_scanner`: the pin is only
useful if the hash the VPS computes is the SAME number the lab recorded when the version was
promoted. Two independent implementations of "hash a package" that drift by one rule (skip
tests? hash the filename too?) produce a pin that never matches and a bot that never starts —
or worse, one that matches by luck on the day it is set up and stops matching later.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

_REPO = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(_REPO / "algos" / "live"))
import version as live_version  # noqa: E402


def test_hash_matches_the_labs_scanner():
    """`algos/live/version.py` and `command-center/.../strategy_scanner.py` compute the same
    hash for the same package. They are separate implementations on purpose (the two apps may
    not import each other), so this is the only thing keeping them honest."""
    sys.path.insert(0, str(_REPO / "command-center" / "backend"))
    from services.strategy_scanner import _python_source_hash

    pkg = _REPO / "strategies" / "python" / "mpc_sos_fade"
    assert live_version.python_source_hash(pkg) == _python_source_hash(pkg)


def test_hash_changes_when_a_module_changes(tmp_path):
    pkg = tmp_path / "pkg"
    pkg.mkdir()
    (pkg / "__init__.py").write_text("A = 1")
    (pkg / "config.py").write_text("RISK = 10")
    before = live_version.python_source_hash(pkg)
    (pkg / "config.py").write_text("RISK = 25")
    assert live_version.python_source_hash(pkg) != before


def test_hash_ignores_test_edits(tmp_path):
    """Editing a test does not change what the strategy DOES, so it must not invalidate a
    deployment — otherwise every test commit stops the live bot."""
    pkg = tmp_path / "pkg"
    (pkg / "tests").mkdir(parents=True)
    (pkg / "__init__.py").write_text("A = 1")
    (pkg / "tests" / "test_a.py").write_text("def test_x(): pass")
    before = live_version.python_source_hash(pkg)
    (pkg / "tests" / "test_a.py").write_text("def test_x(): assert True")
    assert live_version.python_source_hash(pkg) == before


def test_hash_notices_a_rename(tmp_path):
    """The file NAME is hashed alongside its bytes — moving logic between modules is a real
    change even when the total bytes are identical."""
    pkg = tmp_path / "pkg"
    pkg.mkdir()
    (pkg / "__init__.py").write_text("A = 1")
    (pkg / "signals.py").write_text("X = 2")
    before = live_version.python_source_hash(pkg)
    (pkg / "signals.py").rename(pkg / "signal_adapter.py")
    assert live_version.python_source_hash(pkg) != before


def test_verify_pin_passes_when_the_code_matches(tmp_path):
    pkg = tmp_path / "pkg"
    pkg.mkdir()
    (pkg / "__init__.py").write_text("A = 1")
    h = live_version.python_source_hash(pkg)
    assert live_version.verify_pin(pkg, h) == h


def test_verify_pin_refuses_when_the_repo_moved_underneath(tmp_path):
    """This is the whole point: a `git pull` that changes the strategy must STOP the bot, not
    silently start trading code nobody promoted."""
    pkg = tmp_path / "pkg"
    pkg.mkdir()
    (pkg / "__init__.py").write_text("A = 1")
    pinned = live_version.python_source_hash(pkg)
    (pkg / "__init__.py").write_text("A = 2")
    with pytest.raises(live_version.VersionMismatch) as e:
        live_version.verify_pin(pkg, pinned)
    assert "never promoted" in str(e.value)
    assert pinned in str(e.value)          # the message names both hashes, so it is diagnosable


def test_an_unpinned_bot_is_allowed_and_returns_its_hash(tmp_path):
    """Unpinned is a state to pass through on the way to a promotion, not an error — but the
    caller gets the real hash back so it can log exactly what it is running."""
    pkg = tmp_path / "pkg"
    pkg.mkdir()
    (pkg / "__init__.py").write_text("A = 1")
    assert live_version.verify_pin(pkg, "") == live_version.python_source_hash(pkg)
    assert live_version.verify_pin(pkg, None) == live_version.python_source_hash(pkg)
