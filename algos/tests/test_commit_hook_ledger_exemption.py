"""The unattended ledger sync must be able to commit what it fetches.

🔴 **This has broken the backup TWICE, and the second time is why this file exists.** The
commit-msg hook refuses any commit whose changed files have no owning CLAUDE.md in the same
commit — which is right for code and wrong for recorded data, so `*/ledger/decisions-*.jsonl`
was exempted on the morning of 2026-08-05 after the sync was found refusing with a day
outstanding. The same afternoon the record was split into two streams and the text log went
per-day, and **the sync broke again on its very first run**, because an exemption enumerates the
shapes that existed when somebody wrote it.

⚠ **The property that makes this class of bug expensive: a rule that fires on a robot's commit
has no human to read its message.** It does not nag. It silently stops the job, and the symptom
is a backup that quietly stops happening — which looks exactly like a backup with nothing to do.

So the hook is driven for real, against the exact paths `ledger_sync.py` writes. A new per-day
artefact added to the sync without a matching exemption fails here instead of in production at
midnight.
"""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

_REPO = Path(__file__).resolve().parent.parent.parent
_HOOK = _REPO / ".githooks" / "commit-msg"

# Exactly what `ledger_sync.commit()` stages, rooted at `LOCAL_ARCHIVE`.
SYNCED = [
    "algos/ledger_archive/sos_fade_demo/ledger/decisions-2026-08-05.jsonl",
    "algos/ledger_archive/sos_fade_demo/ledger/health-2026-08-05.jsonl",
    "algos/ledger_archive/sos_fade_demo/sos_fade_demo-2026-08-05.log",
]


@pytest.fixture
def repo(tmp_path):
    """A throwaway repo with the REAL hook installed. Mocking the hook would test the mock, and
    the thing worth pinning is whether this exact script accepts these exact paths."""
    work = tmp_path / "work"
    (work / ".githooks").mkdir(parents=True)
    (work / ".githooks" / "commit-msg").write_bytes(_HOOK.read_bytes())
    (work / ".githooks" / "commit-msg").chmod(0o755)
    (work / "CLAUDE.md").write_text("root\n")

    for args in (
        ["init", "-q", "-b", "main"],
        ["config", "user.email", "t@t"],
        ["config", "user.name", "t"],
        ["config", "core.hooksPath", ".githooks"],
    ):
        subprocess.run(["git", "-C", str(work), *args], check=True, capture_output=True)
    subprocess.run(["git", "-C", str(work), "add", "-A"], check=True, capture_output=True)
    subprocess.run(
        ["git", "-C", str(work), "commit", "-qm", "init", "--no-verify"],
        check=True,
        capture_output=True,
    )
    return work


def _commit(repo: Path, rel_paths: list[str], message: str) -> subprocess.CompletedProcess:
    for rel in rel_paths:
        p = repo / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text('{"kind":"bar"}\n')
    subprocess.run(
        ["git", "-C", str(repo), "add", "--", *rel_paths], check=True, capture_output=True
    )
    return subprocess.run(
        ["git", "-C", str(repo), "commit", "-m", message], capture_output=True, text=True
    )


@pytest.mark.parametrize("rel", SYNCED)
def test_each_file_the_sync_commits_is_accepted_alone(repo, rel):
    out = _commit(repo, [rel], "chore(ledger): bot record 2026-08-05")
    assert out.returncode == 0, f"the hook refused {rel}:\n{out.stdout}{out.stderr}"


def test_a_whole_days_record_commits_in_one_go(repo):
    """The real shape of a sync run: all three streams for one day, one commit, no human."""
    out = _commit(repo, SYNCED, "chore(ledger): bot record 2026-08-05")
    assert out.returncode == 0, f"the hook refused a day's record:\n{out.stdout}{out.stderr}"


def test_the_exemption_is_a_path_and_not_the_extension(repo):
    """⚠ Deliberately narrow. `*.jsonl` and `*.log` are generic — a future file holding a
    CONTRACT under either extension must still demand its doc, the same way `*.meta.json` is
    explicitly not exempt. Only the sync's own shapes are waved through."""
    out = _commit(
        repo, ["algos/live/schema-2026-08-05.jsonl"], "feat: a contract that happens to be jsonl"
    )
    assert out.returncode != 0, "a stray .jsonl outside the ledger paths was exempted"


def test_a_code_change_is_still_refused(repo):
    """The hook's actual job, pinned alongside — widening an exemption is exactly the change
    that could quietly disable the rule for everything."""
    out = _commit(repo, ["algos/live/runner.py"], "feat: something real")
    assert out.returncode != 0, "the hook stopped asking for docs on code"
