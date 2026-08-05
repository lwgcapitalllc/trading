"""Every file the sync fetches must be one git will actually commit.

🔴 **The defect this file exists for, and it is the third silent break of the same backup in one
day.** `.gitignore` carries a blanket `*.log`. The first real run of the 12-hourly sync copied the
bot's daily text log down from the VPS, `git status` did not list it — an ignored file is not a
changed one — `pending()` dropped it without a word, and the run printed **"2 file(s) pushed"**
having committed two of the three streams it fetched.

⚠ **From the commit side, an ignored file and a file that was never written are identical.** That
is this repo's own rule — never let two different things be the same value — arriving through
git's own config, where nothing in the pipeline was looking.

Two guards, because either alone leaves the hole open:

* the `.gitignore` negation, pinned here against the REAL repo, so deleting it fails the suite;
* `ledger_sync.ignored()`, which NAMES an unbackupable fetch and refuses to report success — so a
  future ignore rule that catches a new artefact is loud instead of silent.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest

_REPO = Path(__file__).resolve().parent.parent.parent
if str(_REPO / "algos" / "tools") not in sys.path:
    sys.path.insert(0, str(_REPO / "algos" / "tools"))

import ledger_sync  # noqa: E402

# The three per-day artefacts `ledger_sync.py` fetches, under the archive root it writes to.
ARCHIVED = [
    "algos/ledger_archive/mpc_sos_fade_demo/ledger/decisions-2026-08-05.jsonl",
    "algos/ledger_archive/mpc_sos_fade_demo/ledger/health-2026-08-05.jsonl",
    "algos/ledger_archive/mpc_sos_fade_demo/mpc_sos_fade_demo-2026-08-05.log",
]


@pytest.mark.parametrize("rel", ARCHIVED)
def test_the_real_repo_does_not_ignore_what_the_sync_fetches(rel):
    """Run against THIS repo's actual `.gitignore`, not a fixture. The rule that broke the backup
    was a real line in a real file, and a fixture would have been written to pass.

    ⚠ **Plain `check-ignore`, deliberately NOT `-v`.** With `-v` git reports the last matching
    pattern *including negations*, and exits 0 for a path a `!` rule has re-included — so the
    first version of this test failed on a correctly-committable file. Without it, exit 0 and a
    printed path mean ignored and nothing else. `ledger_sync.ignored()` reads it the same way.
    """
    out = subprocess.run(["git", "-C", str(_REPO), "check-ignore", "--", rel],
                         capture_output=True, text=True)
    if out.returncode == 0:
        why = subprocess.run(["git", "-C", str(_REPO), "check-ignore", "-v", "--", rel],
                             capture_output=True, text=True).stdout.strip()
        pytest.fail(f"{rel} is ignored by git, so the backup can fetch it and never commit "
                    f"it:\n  {why}")


def test_an_ignored_fetch_is_reported_rather_than_dropped(tmp_path, monkeypatch):
    """The second guard, and the one that survives a `.gitignore` nobody predicted. `pending()`
    cannot see an ignored file at all, so the check has to be its own question."""
    repo = tmp_path / "repo"
    (repo / "arch").mkdir(parents=True)
    subprocess.run(["git", "-C", str(repo), "init", "-q", "-b", "main"], check=True)
    (repo / ".gitignore").write_text("*.log\n")
    target = repo / "arch" / "bot-2026-08-05.log"
    target.write_text("hello\n")

    monkeypatch.setattr(ledger_sync, "REPO_ROOT", repo)
    assert ledger_sync.ignored([target]) == [target]


def test_a_committable_file_is_not_reported_as_ignored(tmp_path, monkeypatch):
    """`git check-ignore` exits 1 when nothing matches, which is the ordinary case — reading its
    return code instead of its output would call every healthy sync a failure."""
    repo = tmp_path / "repo"
    (repo / "arch").mkdir(parents=True)
    subprocess.run(["git", "-C", str(repo), "init", "-q", "-b", "main"], check=True)
    (repo / ".gitignore").write_text("*.log\n")
    target = repo / "arch" / "decisions-2026-08-05.jsonl"
    target.write_text("{}\n")

    monkeypatch.setattr(ledger_sync, "REPO_ROOT", repo)
    assert ledger_sync.ignored([target]) == []
