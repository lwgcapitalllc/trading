"""How far the code a bot's RUN started on is behind what a restart would load — on a SCRIPTED repo.

🔴 **The version counts the strategy only (2026-09-12).** The runner — the code that talks to the
broker and writes what the Bots page reads — is repo code loaded at process start, so it moves only
on a restart. Nothing counted it, and both live bots read "up to date" eight fixes behind.
`bot_versions.running_code` is that count: the commits between the checkout the run started on and
the branch a restart would pull, that change a file the runner loads.

⚠ **A REAL git repo, never a mocked `subprocess`** — the claim under test is *this number IS the
git history*, which is what `test_bot_versions_history.py` holds to for the same reason. A local
branch stands in for origin: all `@{upstream}` needs is a branch to track.

Mutation map, RUN 2026-09-12 through scripts/testing/mutate.py — each named in its test.
"""

from __future__ import annotations

import re
import subprocess
from pathlib import Path

import config as cfg
import pytest
from services import bot_versions as bv

_IDENTITY = ("-c", "user.email=t@t", "-c", "user.name=T", "-c", "commit.gpgsign=false")
_RUNNER_PY = Path(__file__).resolve().parents[3] / "algos" / "live" / "runner.py"


def _git(root, *args: str) -> str:
    out = subprocess.run(["git", "-C", str(root), *args], capture_output=True, text=True)
    assert out.returncode == 0, f"git {' '.join(args)} failed: {out.stderr}"
    return out.stdout.strip()


def _commit(root, files: dict, message: str) -> str:
    for rel, body in files.items():
        path = root / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(body, encoding="utf-8")
    _git(root, "add", "-A")
    _git(root, *_IDENTITY, "commit", "-q", "-m", message)
    return _git(root, "rev-parse", "HEAD")


def _track(root, at: str) -> None:
    """Point a branch called `upstream` at `at` and make the current branch track it."""
    _git(root, "branch", "-f", "upstream", at)
    _git(root, "branch", "--set-upstream-to=upstream")


@pytest.fixture
def repo(tmp_path, monkeypatch):
    root = tmp_path / "repo"
    root.mkdir()
    _git(root, "init", "-q")
    monkeypatch.setattr(cfg, "MONOREPO_ROOT", root)
    return root


def test_it_counts_ONLY_commits_that_change_code_the_runner_loads(repo):
    """The runner's own package, the shared modules and the one contract file it reads out of the
    strategies tree — and nothing else: a page change and a frozen strategy change are not it.
    MUTATION: drop `_specs` from the log (count every commit) → red on the count.
    MUTATION: drop `algos/shared` from RUNNER_TREES → red on the count."""
    start = _commit(repo, {"algos/live/runner.py": "a = 1\n"}, "start")
    _commit(repo, {"algos/live/bridge.py": "b = 1\n"}, "live fix")
    _commit(repo, {"command-center/frontend/page.ts": "c\n"}, "page only")
    _commit(repo, {"strategies/python/live_contract.py": "d = 1\n"}, "contract")
    _commit(repo, {"strategies/python/sos_fade/execution.py": "e = 1\n"}, "frozen strategy")
    _commit(repo, {"algos/shared/order_sizing.py": "f = 1\n"}, "shared")
    _track(repo, _git(repo, "rev-parse", "HEAD"))

    out = bv.running_code(start)
    assert out["reason"] == ""
    assert out["changes_waiting"] == 3
    assert [c.split(" ", 1)[1] for c in out["changes"]] == ["shared", "contract", "live fix"]


def test_a_notes_edit_beside_the_runner_is_not_a_change_it_loads(repo):
    """The rule is the deploy's own (`version_pathspecs`): a CLAUDE.md edit is not code.
    MUTATION: log the raw trees instead of `_specs(...)` → red."""
    start = _commit(repo, {"algos/live/runner.py": "a = 1\n"}, "start")
    _commit(repo, {"algos/live/CLAUDE.md": "notes\n"}, "notes only")
    _track(repo, _git(repo, "rev-parse", "HEAD"))
    assert bv.running_code(start)["changes_waiting"] == 0


def test_nothing_waiting_is_a_MEASURED_zero_with_no_reason(repo):
    """Zero is a real answer when the run started on what a restart would load.
    MUTATION: report `None` for an empty range → red."""
    start = _commit(repo, {"algos/live/runner.py": "a = 1\n"}, "start")
    _track(repo, start)
    out = bv.running_code(start)
    assert out["changes_waiting"] == 0
    assert out["changes"] == []
    assert out["reason"] == ""


def test_the_LIST_is_capped_and_the_COUNT_is_not(repo):
    """A bot left running for months would ship its whole backlog on every read.
    MUTATION: count the capped list → red on the count."""
    start = _commit(repo, {"algos/live/runner.py": "a = 0\n"}, "start")
    for i in range(bv._RUNNER_CHANGES_SHOWN + 5):
        _commit(repo, {"algos/live/runner.py": f"a = {i + 1}\n"}, f"fix {i}")
    _track(repo, _git(repo, "rev-parse", "HEAD"))
    out = bv.running_code(start)
    assert out["changes_waiting"] == bv._RUNNER_CHANGES_SHOWN + 5
    assert len(out["changes"]) == bv._RUNNER_CHANGES_SHOWN


@pytest.mark.parametrize(
    "commit, upstream, needle",
    [
        ("", True, "did not record"),
        ("deadbeefdeadbeef", True, "fetched"),
        (None, False, "tracks nothing"),
    ],
)
def test_every_could_not_tell_is_None_with_its_own_reason(repo, commit, upstream, needle):
    """Each has a different fix, so each says which (rule 1: never 0 for *could not tell*).
    MUTATION: answer 0 for an unfetched commit → red on its case."""
    start = _commit(repo, {"algos/live/runner.py": "a = 1\n"}, "start")
    if upstream:
        _track(repo, start)
    out = bv.running_code(start if commit is None else commit)
    assert out["changes_waiting"] is None
    assert out["changes"] == []
    assert needle in out["reason"]


def test_RUNNER_TREES_names_every_path_runner_py_loads_from_the_checkout():
    """The runner puts its own package, the shared modules and the strategies root on `sys.path`,
    and loads ONE file out of that root by path — the strategy packages beside it are shadowed by
    the frozen snapshot. A path added there that is not counted here is a change that reaches a bot
    on restart while the page says nothing is waiting.
    MUTATION: drop `algos/shared` from RUNNER_TREES → red."""
    src = _RUNNER_PY.read_text(encoding="utf-8")
    block = re.search(r"for _p in \((.*?)\):", src, re.S)
    assert block, "runner.py no longer builds its sys.path from a `for _p in (...)` loop"
    entries = re.findall(r'str\(_REPO((?:\s*/\s*"[^"]+")*)\)', block.group(1))
    paths = ["/".join(re.findall(r'"([^"]+)"', e)) for e in entries]
    assert paths, "parsed no `str(_REPO ...)` entries — the check would pass for free"
    for p in paths:
        # "" is the repo root; the strategies root is shadowed by the snapshot, and the one file
        # the runner reads from it by path is asserted below.
        if p in ("", "strategies/python"):
            continue
        assert p in bv.RUNNER_TREES, f"runner.py loads {p} and RUNNER_TREES does not count it"
    assert "str(_HERE)" in block.group(1) and "algos/live" in bv.RUNNER_TREES
    assert '"strategies" / "python" / "live_contract.py"' in src
    assert "strategies/python/live_contract.py" in bv.RUNNER_TREES
