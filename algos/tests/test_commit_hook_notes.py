"""A notes file beside the owning CLAUDE.md satisfies the commit hook's doc check.

The big CLAUDE.md files were split on 2026-09-13 into a slim rules file plus topic notes in a
`notes/` folder next to it, which load only when opened. The hook used to demand the CLAUDE.md
itself, so every code change appended to the one file that loads in full — which is how the
2026-08-12 cleanup grew back to 574 KB. These drive the REAL hook in a throwaway repo, the same
way `test_commit_hook_ledger_exemption.py` does.

To watch these go red against an older hook, point `COMMIT_MSG_HOOK_UNDER_TEST` at a copy of it.
"""

from __future__ import annotations

import os
import subprocess
from pathlib import Path

import pytest

_REPO = Path(__file__).resolve().parent.parent.parent
_HOOK = Path(os.environ.get("COMMIT_MSG_HOOK_UNDER_TEST", _REPO / ".githooks" / "commit-msg"))


@pytest.fixture
def repo(tmp_path):
    work = tmp_path / "work"
    (work / ".githooks").mkdir(parents=True)
    (work / ".githooks" / "commit-msg").write_bytes(_HOOK.read_bytes())
    (work / ".githooks" / "commit-msg").chmod(0o755)
    (work / "CLAUDE.md").write_text("root\n")
    (work / "sub").mkdir()
    (work / "sub" / "CLAUDE.md").write_text("sub\n")
    # "oth" is the SAME LENGTH as "sub" on purpose — see the another-owner test.
    (work / "oth").mkdir()
    (work / "oth" / "CLAUDE.md").write_text("oth\n")
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


def _commit(repo: Path, rel_paths: list[str]) -> subprocess.CompletedProcess:
    for rel in rel_paths:
        p = repo / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(f"change to {rel}\n")
    subprocess.run(
        ["git", "-C", str(repo), "add", "--", *rel_paths], check=True, capture_output=True
    )
    return subprocess.run(
        ["git", "-C", str(repo), "commit", "-m", "feat: a change"], capture_output=True, text=True
    )


def test_code_with_its_own_claude_md_is_accepted(repo):
    """Control: the rule as it always was still holds."""
    assert _commit(repo, ["sub/code.py", "sub/CLAUDE.md"]).returncode == 0


def test_code_with_no_doc_at_all_is_refused(repo):
    """Control: the check still bites — a hook that accepts everything passes the cases below."""
    out = _commit(repo, ["sub/code.py"])
    assert out.returncode != 0 and "sub/CLAUDE.md" in out.stdout + out.stderr


def test_a_note_in_the_owners_notes_folder_counts_as_the_doc(repo):
    assert _commit(repo, ["sub/code.py", "sub/notes/topic.md"]).returncode == 0


def test_a_root_level_file_is_satisfied_by_the_root_notes_folder(repo):
    """The root owner is `CLAUDE.md`, whose folder is `.` — its notes live at `notes/`."""
    assert _commit(repo, ["tool.py", "notes/topic.md"]).returncode == 0


def test_a_note_belonging_to_ANOTHER_owner_does_not_count(repo):
    """⚠ The other owner's folder is the same length as this one's, and that is the point: with a
    longer name the direct-child check refused it by accident of string offsets, so this case
    stayed green with the owner-prefix check deleted (a mutation survived it on 2026-09-13)."""
    out = _commit(repo, ["sub/code.py", "oth/notes/topic.md"])
    assert out.returncode != 0 and "sub/CLAUDE.md" in out.stdout + out.stderr


def test_only_markdown_directly_inside_notes_counts(repo):
    """A deeper folder or a non-markdown file is not the owner's notes."""
    assert _commit(repo, ["sub/code.py", "sub/notes/deeper/topic.md"]).returncode != 0
    assert _commit(repo, ["sub/code2.py", "sub/notes/topic.txt"]).returncode != 0


def test_a_similarly_named_folder_is_not_the_notes_folder(repo):
    """`sub/notesx/` must not satisfy `sub/`: the prefix ends at the slash."""
    assert _commit(repo, ["sub/code.py", "sub/notesx/topic.md"]).returncode != 0
