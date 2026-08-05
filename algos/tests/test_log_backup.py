"""Preserving the decision record — both halves.

The ledger is the only evidence the dry run happened. It lives on one VPS disk, and the two
scripts under test are the only things that bound it and move it. Two failure modes matter
more than the rest, and both are quiet: copying a file the bot is still writing (a torn day
that later reads exactly like a whole one), and skipping a day (a hole nothing ever fills).

`log_backup.py` runs on the VPS and does housekeeping. `ledger_sync.py` runs on the Mac and
does git. The split exists because the VPS cannot push — see either module's docstring.

Git is exercised for real against a throwaway repo in tmp_path. Mocking `subprocess` would
test the mock, and the thing worth pinning is precisely WHICH paths end up staged.
"""

from __future__ import annotations

import subprocess
import sys
import zipfile
from datetime import date
from pathlib import Path

import pytest

_REPO = Path(__file__).resolve().parent.parent.parent
if str(_REPO / "algos" / "tools") not in sys.path:
    sys.path.insert(0, str(_REPO / "algos" / "tools"))

import ledger_sync  # noqa: E402
import log_backup  # noqa: E402

TODAY = date(2026, 8, 15)


def _ledger(instances: Path, bot: str, day: str, body: str = '{"kind":"bar"}\n') -> Path:
    d = instances / bot / "ledger"
    d.mkdir(parents=True, exist_ok=True)
    p = d / f"decisions-{day}.jsonl"
    p.write_text(body)
    return p


# ── which days are eligible (the VPS side) ──────────────────────────────────────
def test_todays_file_is_left_alone(tmp_path):
    """It is still being appended to. Copying it captures a torn half-day that is
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
    """A backup job is the wrong place to guess what an unexpected file was — but silently
    ignoring it is how a real ledger with a typo'd name never gets saved."""
    d = tmp_path / "bot" / "ledger"
    d.mkdir(parents=True)
    (d / "notes.txt").write_text("scratch")
    (d / "decisions-2026-08-14.jsonl").write_text("{}\n")
    closed, skipped = log_backup.ledger_files(tmp_path, TODAY)
    assert [p.name for p in closed] == ["decisions-2026-08-14.jsonl"]
    assert [p.name for p in skipped] == ["notes.txt"]


def test_the_health_stream_is_collected_too(tmp_path):
    """🔴 The regression the 2026-08-05 split could most easily have shipped: the health file is
    a SECOND filename shape, and a backup that only knew the first would have gone on reporting
    success while never once committing the record of starts, stops and crashes. Nothing would
    look wrong — a stream that is never fetched is indistinguishable from one never written."""
    d = tmp_path / "bot" / "ledger"
    d.mkdir(parents=True)
    (d / "decisions-2026-08-14.jsonl").write_text("{}\n")
    (d / "health-2026-08-14.jsonl").write_text("{}\n")
    closed, skipped = log_backup.ledger_files(tmp_path, TODAY)

    assert sorted(p.name for p in closed) == ["decisions-2026-08-14.jsonl",
                                              "health-2026-08-14.jsonl"]
    assert skipped == []


def test_the_dated_text_log_is_collected_too(tmp_path):
    """The prose log carries the tracebacks, and it lives in the instance dir rather than in
    `ledger/`. It became per-day so that it could be committed at all."""
    inst = tmp_path / "bot"
    (inst / "ledger").mkdir(parents=True)
    (inst / "bot-2026-08-14.log").write_text("hello\n")
    closed, _ = log_backup.ledger_files(tmp_path, TODAY)

    assert [p.name for p in closed] == ["bot-2026-08-14.log"]


def test_todays_files_are_reported_as_OPEN_not_as_closed(tmp_path):
    """⚠ The distinction survives the move to a 12-hourly sync rather than being dropped by it.
    Today's file is committed now, but it is a BEST COPY that will be committed again — calling
    it closed is what lets a torn half-day later read exactly like a whole one."""
    d = tmp_path / "bot" / "ledger"
    d.mkdir(parents=True)
    (d / "decisions-2026-08-15.jsonl").write_text("{}\n")
    (d / "decisions-2026-08-14.jsonl").write_text("{}\n")

    closed, _ = log_backup.ledger_files(tmp_path, TODAY)
    assert [p.name for p in closed] == ["decisions-2026-08-14.jsonl"]
    assert [p.name for p in log_backup.open_files(tmp_path, TODAY)] == \
        ["decisions-2026-08-15.jsonl"]


def test_the_backup_reads_the_writers_own_filename_pattern():
    """Two regexes would drift, and the drift's symptom is a whole stream that is silently never
    committed. `log_backup` imports `STREAM_RE` from the module that WRITES the files."""
    from ledger import STREAM_RE

    assert log_backup.STREAM_RE is STREAM_RE


# ── a file copied while it was being written (the Mac side) ────────────────────
def test_a_torn_last_line_is_dropped_before_it_is_committed(tmp_path):
    """Fetching today's file races the bot appending to it, so the copy can end mid-record.
    Half a record cannot be parsed, and committing one means every later reader has to defend
    against it."""
    p = tmp_path / "decisions-2026-08-15.jsonl"
    p.write_text('{"kind":"bar","i":1}\n{"kind":"bar","i":2}\n{"kind":"ba')
    ledger_sync._whole_lines(p)

    assert p.read_text() == '{"kind":"bar","i":1}\n{"kind":"bar","i":2}\n'


def test_a_complete_last_line_without_a_newline_is_kept(tmp_path):
    """⚠ The check is "does it parse", NOT "does it end in a newline". A write can be flushed
    complete a moment before its newline lands, and truncating on the newline would throw away a
    good record on every single sync — quietly, and most often the newest one."""
    p = tmp_path / "decisions-2026-08-15.jsonl"
    p.write_text('{"kind":"bar","i":1}\n{"kind":"bar","i":2}')
    ledger_sync._whole_lines(p)

    assert p.read_text() == '{"kind":"bar","i":1}\n{"kind":"bar","i":2}\n'


def test_a_text_log_is_never_truncated(tmp_path):
    """Prose is not records. Half a sentence still says what was happening, and the last line of
    a log being written is exactly the line somebody is reading it for."""
    p = tmp_path / "bot-2026-08-15.log"
    p.write_text("starting up\nWarmed 5000 ba")
    ledger_sync._whole_lines(p)

    assert p.read_text() == "starting up\nWarmed 5000 ba"


def test_the_sync_accepts_both_stream_names_and_the_text_log(monkeypatch):
    """The path anchor was WIDENED to two shapes, not loosened. Traversal must still be
    impossible — a filename-only check passes `../../../health-2026-08-14.jsonl`, which is a
    perfectly valid name landing outside the repo."""
    monkeypatch.setattr(ledger_sync, "_run", lambda *a: subprocess.CompletedProcess(
        a, 0, stdout="bot/ledger/decisions-2026-08-15.jsonl\n"
                     "bot/ledger/health-2026-08-15.jsonl\n"
                     "bot/bot-2026-08-15.log\n"
                     "../../../../tmp/health-2026-08-15.jsonl\n"
                     "bot/ledger/../../../etc/health-2026-08-15.jsonl\n"
                     "bot/../../etc/bot-2026-08-15.log\n"
                     "/etc/health-2026-08-15.jsonl\n", stderr=""))

    assert ledger_sync.remote_files("host", "open") == [
        "bot/ledger/decisions-2026-08-15.jsonl",
        "bot/ledger/health-2026-08-15.jsonl",
        "bot/bot-2026-08-15.log",
    ]


# ── the raw logs (the VPS side) ─────────────────────────────────────────────────
def test_logs_are_copied_into_a_dated_zip(tmp_path):
    inst = tmp_path / "inst"
    (inst / "bot").mkdir(parents=True)
    (inst / "bot" / "bot.log").write_text("hello")

    z = log_backup.archive_logs(inst, tmp_path / "arch", TODAY)
    assert z.name == "logs-2026-08-15.zip"
    with zipfile.ZipFile(z) as zf:
        assert zf.read("bot/bot.log").decode() == "hello"


def test_the_live_log_is_left_in_place(tmp_path):
    """It is copied, never rotated. The bot holds it open, and renaming an open file on
    Windows fails — a rotation scheme would pass here and lose the day on the VPS."""
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
    """The decision record is the artefact; only the zipped scratch is disposable. A prune
    that could reach the ledger would delete the very thing this exists to keep."""
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


# ── git: exactly these paths, and nothing else (the Mac side) ───────────────────
@pytest.fixture
def repo(tmp_path, monkeypatch):
    """A real git repo with a real 'origin', with ledger_sync pointed at it.

    Staging is observed rather than mocked because the property worth pinning is which paths
    reach the index — the one thing a mock would happily agree with and get wrong.
    """
    origin = tmp_path / "origin.git"
    subprocess.run(["git", "init", "--bare", "-q", str(origin)], check=True)

    work = tmp_path / "work"
    work.mkdir()
    subprocess.run(["git", "init", "-q", "-b", "main", str(work)], check=True)
    for a in (("config", "user.email", "t@t.t"), ("config", "user.name", "t"),
              ("remote", "add", "origin", str(origin))):
        subprocess.run(["git", "-C", str(work), *a], check=True)
    (work / "README.md").write_text("x")
    subprocess.run(["git", "-C", str(work), "add", "README.md"], check=True)
    subprocess.run(["git", "-C", str(work), "commit", "-qm", "init"], check=True)
    subprocess.run(["git", "-C", str(work), "push", "-q", "origin", "main"], check=True)

    monkeypatch.setattr(ledger_sync, "REPO_ROOT", work)
    # `LOCAL_ARCHIVE`, not the bot's own instance dir — the sync writes to a SEPARATE tree
    # (`algos/ledger_archive/`) because committing into the live path made `git pull` on the
    # VPS abort on its own untracked files. Renamed 2026-08-05; this line still said
    # LOCAL_INSTANCES and every test in the file errored at setup.
    monkeypatch.setattr(ledger_sync, "LOCAL_ARCHIVE", work / "algos" / "ledger_archive")
    return work


def _tracked(repo: Path) -> set[str]:
    out = subprocess.run(["git", "-C", str(repo), "ls-files"], capture_output=True, text=True)
    return set(out.stdout.split())


def test_a_ledger_file_reaches_origin(repo):
    p = _ledger(repo / "algos" / "inst", "bot", "2026-08-14")
    assert ledger_sync.commit([p], push=True) is True

    out = subprocess.run(["git", "-C", str(repo), "log", "--oneline", "origin/main"],
                         capture_output=True, text=True)
    assert "bot record" in out.stdout


def test_a_secret_sitting_in_the_tree_is_not_swept_in(repo):
    """Says `git add -A` is never acceptable here, however much simpler it reads. The VPS
    tree this mirrors holds credentials.json with a live MT5 password and a Telegram token."""
    (repo / "credentials.json").write_text('{"mt5_password": "hunter2"}')
    (repo / "algos").mkdir(exist_ok=True)
    (repo / "algos" / "monitor_state.json").write_text("{}")
    p = _ledger(repo / "algos" / "inst", "bot", "2026-08-14")

    ledger_sync.commit([p], push=True)

    tracked = _tracked(repo)
    assert "credentials.json" not in tracked
    assert "algos/monitor_state.json" not in tracked
    assert any("decisions-2026-08-14" in t for t in tracked)


def test_an_already_committed_file_is_not_re_committed(repo):
    p = _ledger(repo / "algos" / "inst", "bot", "2026-08-14")
    ledger_sync.commit([p], push=True)
    assert ledger_sync.pending([p]) == []


def test_a_file_that_grew_after_its_commit_is_picked_up_again(repo):
    """A day can be fetched before the bot has finished writing it only if the clock is
    wrong — but a re-fetch that git ignores would silently keep the truncated version."""
    p = _ledger(repo / "algos" / "inst", "bot", "2026-08-14")
    ledger_sync.commit([p], push=True)
    p.write_text('{"kind":"bar"}\n{"kind":"trade"}\n')
    assert ledger_sync.pending([p]) == [p]


def test_a_missed_day_is_caught_up_not_lost(repo):
    """The reason the VPS reports ALL closed days rather than just yesterday. A day the Mac
    was off must become a delay, not a permanent hole."""
    old = _ledger(repo / "algos" / "inst", "bot", "2026-08-02")
    new = _ledger(repo / "algos" / "inst", "bot", "2026-08-14")

    closed, _ = log_backup.ledger_files(repo / "algos" / "inst", TODAY)
    assert set(ledger_sync.pending(closed)) == {old, new}

    ledger_sync.commit(closed, push=True)
    assert any("decisions-2026-08-02" in t for t in _tracked(repo))


def test_no_push_commits_locally_and_says_it_did_not_push(repo):
    """`--no-push` must not report success — the record is not safe until it is at origin."""
    p = _ledger(repo / "algos" / "inst", "bot", "2026-08-14")
    assert ledger_sync.commit([p], push=False) is False
    assert any("decisions-2026-08-14" in t for t in _tracked(repo))

    out = subprocess.run(["git", "-C", str(repo), "log", "--oneline", "origin/main"],
                         capture_output=True, text=True)
    assert "bot record" not in out.stdout


# ── the two halves agree ────────────────────────────────────────────────────────
def test_the_sync_only_accepts_ledger_shaped_paths(repo, monkeypatch):
    """`remote_files` validates what the VPS reports rather than trusting it.

    Each reported line becomes a local WRITE TARGET, and the remote is a different machine
    running whatever it last pulled. The traversal case is the one that matters: a filename-
    only check passes `../../../decisions-2026-08-14.jsonl` — a perfectly valid ledger name
    that lands outside the repo — so the whole path shape is anchored instead.
    """
    monkeypatch.setattr(ledger_sync, "_run", lambda *a: subprocess.CompletedProcess(
        a, 0, stdout="bot/ledger/decisions-2026-08-14.jsonl\n"
                     "../../../../../tmp/decisions-2026-08-14.jsonl\n"
                     "bot/ledger/../../../etc/decisions-2026-08-14.jsonl\n"
                     "bot/ledger/notes.txt\n"
                     "/etc/decisions-2026-08-14.jsonl\n", stderr=""))
    assert ledger_sync.remote_files("host", "closed") == ["bot/ledger/decisions-2026-08-14.jsonl"]


def test_a_fetched_path_always_lands_inside_the_repo(repo, monkeypatch):
    """The property the shape check buys, stated directly against the write target."""
    monkeypatch.setattr(ledger_sync, "_run", lambda *a: subprocess.CompletedProcess(
        a, 0, stdout="bot/ledger/decisions-2026-08-14.jsonl\n", stderr=""))
    for rel in ledger_sync.remote_files("host", "closed"):
        target = (ledger_sync.LOCAL_ARCHIVE / rel).resolve()
        assert target.is_relative_to(repo.resolve())


def test_both_halves_share_one_definition_of_a_ledger_filename():
    """Two regexes would drift, and the drift would show up as a day that is silently never
    synced — the exact failure this whole pipeline exists to prevent."""
    assert ledger_sync.LEDGER_RE is log_backup.LEDGER_RE
