"""Backing up the decision record.

The ledger is the only evidence the dry run happened, and this job is the only thing that
moves it off the VPS disk. Two failure modes are worth more than the rest, and both are
quiet: committing a file the bot is still writing (a torn day that reads as a whole one), and
skipping a day the job missed (a hole that nothing ever fills). Everything below is aimed at
those two, plus the rule that a box holding a live MT5 password never gets a blanket `git add`.

Git is exercised for real against a throwaway repo in tmp_path — mocking `subprocess` here
would test the mock, and the thing worth checking is precisely WHICH paths end up staged.
"""

from __future__ import annotations

import subprocess
import sys
from datetime import date
from pathlib import Path

import pytest

_REPO = Path(__file__).resolve().parent.parent.parent
if str(_REPO / "algos" / "tools") not in sys.path:
    sys.path.insert(0, str(_REPO / "algos" / "tools"))

import log_backup  # noqa: E402

TODAY = date(2026, 8, 15)


def _ledger(instances: Path, bot: str, day: str, body: str = '{"kind":"bar"}\n') -> Path:
    d = instances / bot / "ledger"
    d.mkdir(parents=True, exist_ok=True)
    p = d / f"decisions-{day}.jsonl"
    p.write_text(body)
    return p


# ── which files are eligible ────────────────────────────────────────────────────
def test_todays_file_is_left_alone(tmp_path):
    """It is still being appended to. A commit would capture a torn half-day that is
    indistinguishable, later, from a complete one."""
    _ledger(tmp_path, "bot", "2026-08-15")
    closed, _ = log_backup.ledger_files(tmp_path, TODAY)
    assert closed == []


def test_closed_days_are_collected_oldest_first(tmp_path):
    for day in ("2026-08-14", "2026-08-12", "2026-08-13"):
        _ledger(tmp_path, "bot", day)
    closed, _ = log_backup.ledger_files(tmp_path, TODAY)
    assert [p.name for p in closed] == ["decisions-2026-08-12.jsonl",
                                        "decisions-2026-08-13.jsonl",
                                        "decisions-2026-08-14.jsonl"]


def test_every_bot_is_swept_not_just_the_first(tmp_path):
    _ledger(tmp_path, "aplus", "2026-08-14")
    _ledger(tmp_path, "bleg", "2026-08-14")
    closed, _ = log_backup.ledger_files(tmp_path, TODAY)
    assert {p.parent.parent.name for p in closed} == {"aplus", "bleg"}


def test_a_stray_file_is_skipped_and_named(tmp_path):
    """A backup job is the wrong place to discover what an unexpected file was — but
    silently ignoring it is how a real ledger with a typo'd name never gets saved."""
    d = tmp_path / "bot" / "ledger"
    d.mkdir(parents=True)
    (d / "notes.txt").write_text("scratch")
    (d / "decisions-2026-08-14.jsonl").write_text("{}\n")
    closed, skipped = log_backup.ledger_files(tmp_path, TODAY)
    assert [p.name for p in closed] == ["decisions-2026-08-14.jsonl"]
    assert [p.name for p in skipped] == ["notes.txt"]


# ── git: exactly these paths, and nothing else ──────────────────────────────────
@pytest.fixture
def repo(tmp_path):
    """A real git repo with a real 'origin' to push to, so staging is observed not mocked."""
    origin = tmp_path / "origin.git"
    subprocess.run(["git", "init", "--bare", "-q", str(origin)], check=True)

    work = tmp_path / "work"
    work.mkdir()
    run = lambda *a: subprocess.run(["git", "-C", str(work), *a], check=True,
                                    capture_output=True)
    subprocess.run(["git", "init", "-q", "-b", "main", str(work)], check=True)
    run("config", "user.email", "t@t.t")
    run("config", "user.name", "t")
    run("remote", "add", "origin", str(origin))
    (work / "README.md").write_text("x")
    run("add", "README.md")
    run("commit", "-qm", "init")
    run("push", "-q", "origin", "main")
    return work


def _tracked(repo: Path) -> set[str]:
    out = subprocess.run(["git", "-C", str(repo), "ls-files"],
                         capture_output=True, text=True)
    return set(out.stdout.split())


def test_a_ledger_file_reaches_origin(repo):
    p = _ledger(repo / "algos" / "inst", "bot", "2026-08-14")
    assert log_backup.commit_and_push(repo, [p], TODAY) is True

    out = subprocess.run(["git", "-C", str(repo), "log", "--oneline", "origin/main"],
                         capture_output=True, text=True)
    assert "decision record" in out.stdout


def test_a_secret_sitting_in_the_tree_is_not_swept_in(repo):
    """The VPS holds credentials.json with a live MT5 password and a Telegram token. This is
    the test that says `git add -A` is never acceptable in this job, no matter how much
    simpler it reads."""
    (repo / "credentials.json").write_text('{"mt5_password": "hunter2"}')
    (repo / "algos").mkdir(exist_ok=True)
    (repo / "algos" / "monitor_state.json").write_text("{}")
    p = _ledger(repo / "algos" / "inst", "bot", "2026-08-14")

    log_backup.commit_and_push(repo, [p], TODAY)

    tracked = _tracked(repo)
    assert "credentials.json" not in tracked
    assert "algos/monitor_state.json" not in tracked
    assert any("decisions-2026-08-14" in t for t in tracked)


def test_an_already_committed_file_is_not_re_committed(repo):
    p = _ledger(repo / "algos" / "inst", "bot", "2026-08-14")
    log_backup.commit_and_push(repo, [p], TODAY)
    assert log_backup.uncommitted(repo, [p]) == []


def test_a_file_that_grew_after_its_commit_is_picked_up_again(repo):
    p = _ledger(repo / "algos" / "inst", "bot", "2026-08-14")
    log_backup.commit_and_push(repo, [p], TODAY)
    p.write_text('{"kind":"bar"}\n{"kind":"trade"}\n')
    assert log_backup.uncommitted(repo, [p]) == [p]


def test_a_missed_day_is_caught_up_not_lost(repo):
    """THE reason this commits everything outstanding rather than 'yesterday'. A day the VPS
    was off, or the push failed, must become a delay — not a permanent hole."""
    old = _ledger(repo / "algos" / "inst", "bot", "2026-08-02")
    new = _ledger(repo / "algos" / "inst", "bot", "2026-08-14")

    closed, _ = log_backup.ledger_files(repo / "algos" / "inst", TODAY)
    pending = log_backup.uncommitted(repo, closed)
    assert set(pending) == {old, new}

    log_backup.commit_and_push(repo, pending, TODAY)
    assert any("decisions-2026-08-02" in t for t in _tracked(repo))


def test_a_moved_origin_is_rebased_onto_rather_than_giving_up(repo, tmp_path):
    """A deploy from the Mac lands between two backup runs. The ledger commit touches files
    no source change ever touches, so rebasing is safe — and refusing to would strand the
    record on the VPS indefinitely."""
    other = tmp_path / "other"
    subprocess.run(["git", "clone", "-q", str(tmp_path / "origin.git"), str(other)], check=True)
    for a in (("config", "user.email", "o@o.o"), ("config", "user.name", "o")):
        subprocess.run(["git", "-C", str(other), *a], check=True)
    (other / "src.py").write_text("print(1)")
    subprocess.run(["git", "-C", str(other), "add", "src.py"], check=True)
    subprocess.run(["git", "-C", str(other), "commit", "-qm", "deploy"], check=True)
    subprocess.run(["git", "-C", str(other), "push", "-q"], check=True)

    p = _ledger(repo / "algos" / "inst", "bot", "2026-08-14")
    assert log_backup.commit_and_push(repo, [p], TODAY) is True

    out = subprocess.run(["git", "-C", str(repo), "ls-tree", "-r", "--name-only",
                          "origin/main"], capture_output=True, text=True)
    assert "src.py" in out.stdout
    assert any("decisions-2026-08-14" in line for line in out.stdout.splitlines())


# ── the raw logs ────────────────────────────────────────────────────────────────
def test_logs_are_copied_into_a_dated_zip(tmp_path):
    inst = tmp_path / "inst"
    (inst / "bot").mkdir(parents=True)
    (inst / "bot" / "bot.log").write_text("hello")

    z = log_backup.archive_logs(inst, tmp_path / "arch", TODAY)
    assert z.name == "logs-2026-08-15.zip"

    import zipfile
    with zipfile.ZipFile(z) as zf:
        assert zf.read("bot/bot.log").decode() == "hello"


def test_the_live_log_is_left_in_place(tmp_path):
    """It is copied, never rotated. The bot holds it open, and renaming an open file on
    Windows fails — a rotation scheme would pass on the Mac and lose the day on the VPS."""
    inst = tmp_path / "inst"
    (inst / "bot").mkdir(parents=True)
    live = inst / "bot" / "bot.log"
    live.write_text("hello")

    log_backup.archive_logs(inst, tmp_path / "arch", TODAY)
    assert live.exists() and live.read_text() == "hello"


def test_old_archives_are_pruned_by_filename_date(tmp_path):
    arch = tmp_path / "arch"
    arch.mkdir()
    (arch / "logs-2026-01-01.zip").write_text("old")
    (arch / "logs-2026-08-14.zip").write_text("recent")

    dropped = log_backup.prune(arch, TODAY, keep_days=90)
    assert [p.name for p in dropped] == ["logs-2026-01-01.zip"]
    assert (arch / "logs-2026-08-14.zip").exists()


def test_pruning_never_touches_a_ledger(tmp_path):
    """The decision record is the artefact. Only the zipped scratch is disposable, and a
    prune that could reach the ledger would delete the very thing this job exists to keep."""
    arch = tmp_path / "arch"
    arch.mkdir()
    keep = arch / "decisions-2026-01-01.jsonl"
    keep.write_text("{}")

    assert log_backup.prune(arch, TODAY, keep_days=1) == []
    assert keep.exists()


def test_a_dry_run_changes_nothing(tmp_path):
    inst = tmp_path / "inst"
    (inst / "bot").mkdir(parents=True)
    (inst / "bot" / "bot.log").write_text("x")
    arch = tmp_path / "arch"
    arch.mkdir()
    (arch / "logs-2026-01-01.zip").write_text("old")

    log_backup.archive_logs(inst, arch, TODAY, dry_run=True)
    log_backup.prune(arch, TODAY, keep_days=90, dry_run=True)

    assert not (arch / "logs-2026-08-15.zip").exists()
    assert (arch / "logs-2026-01-01.zip").exists()
