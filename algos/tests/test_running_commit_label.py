"""The startup line names the commit the RUNNING code came from — or says "unknown".

2026-09-16, `sos_fade_demo`: it printed `commit c8cdd64e` (the box repo's HEAD) while the frozen
snapshot it was running had been promoted from `4f87809d`. **Watched RED at HEAD**: there was no
`running_commit`, and the line read `current_commit(repo_root)` for every bot.
"""

from __future__ import annotations

import sys
import types
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[2]
for _p in (_ROOT / "algos" / "live", _ROOT / "algos" / "shared"):
    if str(_p) not in sys.path:
        sys.path.insert(0, str(_p))

import runner as live_runner  # noqa: E402


def _cfg(frozen, promoted):
    return types.SimpleNamespace(
        is_frozen=frozen, promoted_commit=promoted, repo_root=Path("/nonexistent")
    )


def test_a_frozen_bot_reports_the_commit_it_was_PROMOTED_from(monkeypatch):
    """MUTATION: return HEAD for a frozen bot and this reddens."""
    monkeypatch.setattr(live_runner, "current_commit", lambda root: "c8cdd64e")
    assert live_runner.running_commit(_cfg(True, "4f87809d")) == "4f87809d"


def test_a_frozen_bot_with_no_record_says_unknown_never_HEAD(monkeypatch):
    monkeypatch.setattr(live_runner, "current_commit", lambda root: "c8cdd64e")
    assert live_runner.running_commit(_cfg(True, "")) == "unknown"


def test_a_bot_running_from_the_repo_reports_HEAD_or_unknown(monkeypatch):
    monkeypatch.setattr(live_runner, "current_commit", lambda root: "c8cdd64e")
    assert live_runner.running_commit(_cfg(False, "4f87809d")) == "c8cdd64e"
    monkeypatch.setattr(live_runner, "current_commit", lambda root: "")
    assert live_runner.running_commit(_cfg(False, "")) == "unknown"


def test_the_startup_line_uses_it():
    src = (_ROOT / "algos" / "live" / "runner.py").read_text(encoding="utf-8")
    assert "commit = running_commit(self.cfg)" in src
    assert "commit = current_commit(" not in src
